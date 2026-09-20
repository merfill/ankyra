"""Build the committed ProntoQA-OOD compositional samples (L2 gate).

Source: ``tasksource/prontoqa``, the OOD release (Saparov & He, NeurIPS 2023). Each
JSON file holds 100 entries; the scored item is ``test_example``. This builder selects
a deterministic sample **stratified by rule type and by the L2 capability the goal
needs** (``horn`` / ``l2_decomp`` / ``l2_reductio`` / ``l2_reductio+decomp``; the
classification is ``evals.recon_l2``). Recon: ``docs/prontoqa.md`` §9.

The whole collection is downloaded once into ``evals/data/.cache/prontoqa_ood`` (no
LLM); the committed sample is ``evals/data/prontoqa_ood_tier_<tier>.jsonl``.

    uv run python -m evals.build_prontoqa_ood_sample --tier a
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from evals.recon_l2 import SOURCE_URL, _download_files, classify, goal_of, rule_type

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TIERS: dict[str, int] = {
    "a": 4,  # per (rule type, class) bucket
    "b": 12,
}


def _proof_text(example: dict) -> str:
    return " ".join(step.strip() for step in example["chain_of_thought"])


def _record(path: Path, key: str, example: dict, rule: str) -> dict:
    goal = goal_of(example["query"])
    kind = classify(goal, _proof_text(example))
    return {
        "id": f"{path.stem}#{key}",
        "source": "tasksource/prontoqa",
        "source_url": SOURCE_URL,
        "rule_type": rule,
        "class": kind,
        "l2_required": kind != "horn",
        "question": example["question"],
        "query": example["query"],
        "statement": goal,
        "statement_negative": bool(re.search(r"\bnot\b|\bn't\b", goal, re.IGNORECASE)),
        "chain_of_thought": example["chain_of_thought"],
        "answer": "A",  # a "Prove: ..." statement is asserted true
    }


def _load_rows() -> list[dict]:
    rows: list[dict] = []
    for path in _download_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        rule = rule_type(path)
        for key, entry in data.items():
            example = entry.get("test_example")
            if example:
                rows.append(_record(path, key, example, rule))
    return rows


def select(rows: list[dict], tier: str = "a") -> list[dict]:
    """Stratify by (rule type, L2 class) and take a fixed number per bucket."""
    if tier not in TIERS:
        raise SystemExit(f"unknown tier {tier!r}; choose from {', '.join(TIERS)}")
    per_bucket = TIERS[tier]
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        buckets[(row["rule_type"], row["class"])].append(row)
    selected: list[dict] = []
    for key in sorted(buckets):
        selected.extend(sorted(buckets[key], key=lambda r: r["id"])[:per_bucket])
    selected.sort(key=lambda r: (r["rule_type"], r["class"], r["id"]))
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a ProntoQA-OOD tier sample.")
    parser.add_argument("--tier", default="a", choices=sorted(TIERS))
    parser.add_argument("--out", default="", help="Output JSONL (default: data/prontoqa_ood_tier_<tier>.jsonl)")
    args = parser.parse_args(argv)

    selected = select(_load_rows(), args.tier)
    out = Path(args.out) if args.out else DATA / f"prontoqa_ood_tier_{args.tier}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    tally = Counter((r["rule_type"], r["class"]) for r in selected)
    for key, count in sorted(tally.items()):
        print(f"  {key[0]:14} {key[1]:20} {count}")
    print(f"wrote {len(selected)} problems to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
