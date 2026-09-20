"""Build the committed ProntoQA samples (L0 + explicit negation).

Source: ``smoorsmith/prontoqa`` on the Hugging Face Hub — the Logic-LLM mirror of
the original ProntoQA v1 release (Saparov & He). Rows carry ``context``,
``question``, ``answer`` and ``chain_of_thought``. The mirror is small (500 rows per
split), so the whole collection is downloaded and a deterministic stratified subset
is committed to ``evals/data/prontoqa_tier_<x>.jsonl``.

Recon (``docs/prontoqa.md`` §8): v1 is **L0 positive chains** plus **L1 explicit
negated-property rules**; there is no disjointness in the surface text and no
composition (that is the OOD release, i.e. L2).

Run once (pyarrow is not a project dependency):

    uv run --with pyarrow python -m evals.build_prontoqa_sample --tier a

Selection is deterministic: rows sorted by id, grouped by (proof shape, hop count),
taking a fixed number per bucket.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = DATA / ".cache" / "prontoqa"

DATASET = "smoorsmith/prontoqa"
SOURCE_URL = f"https://huggingface.co/datasets/{DATASET}"
SPLITS = ["train", "val", "test"]
TIERS: dict[str, int] = {
    "a": 12,  # 48 problems
    "b": 40,  # 160 problems
}


def _download(split: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{split}.parquet"
    if not path.exists():
        url = f"{SOURCE_URL}/resolve/main/data/{split}-00000-of-00001.parquet"
        print(f"downloading {url}")
        with urllib.request.urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
    return path


def _load_rows() -> list[dict]:
    import pyarrow.parquet as pq  # optional dependency, only for building

    rows: list[dict] = []
    for split in SPLITS:
        for row in pq.read_table(_download(split)).to_pylist():
            row = dict(row)
            row["split"] = split
            rows.append(row)
    return rows


def _statement(question: str) -> str:
    return question.split("?", 1)[-1].strip() or question


def _hops(cot: str) -> int:
    steps = [line for line in cot.splitlines() if line.strip()]
    return max(len(steps) - 1, 0)


def _shape(cot: str) -> str:
    return "negation" if re.search(r"\bnot\b", cot, re.IGNORECASE) else "positive"


def _record(row: dict) -> dict:
    statement = _statement(row["question"])
    return {
        "id": row["id"],
        "source": DATASET,
        "source_url": SOURCE_URL,
        "split": row.get("split", ""),
        "context": row["context"],
        "question": row["question"],
        "statement": statement,
        "statement_negative": bool(re.search(r"\bnot\b", f" {statement} ")),
        "answer": row["answer"],
        "proof_shape": _shape(row["chain_of_thought"]),
        "hops": _hops(row["chain_of_thought"]),
        "chain_of_thought": row["chain_of_thought"],
    }


def _sentence_count(context: str) -> int:
    return len([s for s in re.split(r"(?<=\.)\s+", context.strip()) if s])


def select(rows: list[dict], tier: str = "a") -> list[dict]:
    """Stratify by proof shape and question polarity, diversify by context size.

    ProntoQA v1 has a fixed chain depth (all rows are 10 hops), so the useful axes
    are L0/L1 (``proof_shape``), the statement polarity, and the ontology size.
    """
    if tier not in TIERS:
        raise SystemExit(f"unknown tier {tier!r}; choose from {', '.join(TIERS)}")
    per_bucket = TIERS[tier]
    buckets: dict[tuple[str, bool], list[dict]] = defaultdict(list)
    for raw in rows:
        record = _record(raw)
        record["context_size"] = _sentence_count(record["context"])
        buckets[(record["proof_shape"], record["statement_negative"])].append(record)

    selected: list[dict] = []
    seen_contexts: set[str] = set()
    for key in sorted(buckets):
        bucket = sorted(buckets[key], key=lambda record: (record["context_size"], record["id"]))
        taken = 0
        for record in bucket:
            if taken >= per_bucket:
                break
            if record["context"] in seen_contexts:
                continue
            seen_contexts.add(record["context"])
            selected.append(record)
            taken += 1
    selected.sort(key=lambda record: (record["proof_shape"], record["statement_negative"], record["id"]))
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a ProntoQA tier sample.")
    parser.add_argument("--tier", default="a", choices=sorted(TIERS))
    parser.add_argument("--out", default="", help="Output JSONL (default: data/prontoqa_tier_<tier>.jsonl)")
    args = parser.parse_args(argv)

    selected = select(_load_rows(), args.tier)
    out = Path(args.out) if args.out else DATA / f"prontoqa_tier_{args.tier}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    counts = Counter((r["proof_shape"], r["hops"]) for r in selected)
    for (shape, hops), count in sorted(counts.items()):
        print(f"  {shape:9} hops={hops} {count}")
    print(f"wrote {len(selected)} problems to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
