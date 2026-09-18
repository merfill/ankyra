"""Build the committed ProofWriter Tier A sample.

Source: Tafjord et al., "ProofWriter" (2021), open-world (OWA) synthetic core,
mirrored at ``tasksource/proofwriter`` on the Hugging Face Hub. The sample is a
small stratified subset committed to ``evals/data/proofwriter_tier_a.jsonl`` so
eval runs need no network.

Run once (pyarrow is not a project dependency):

    uv run --with pyarrow python -m evals.build_proofwriter_sample

Selection: the synthetic core only (config ``depth-<n>``; the NatLang and
``depth-3ext`` variants are excluded), three questions per answer label
(True/False/Unknown) per depth, rotating over the id prefix families
(AttNeg/RelNeg/AttNoneg/RelNoneg). For depth >= 1 only questions that need at
least one rule application (``QDep >= 1``) are eligible; depth-0 has no such
non-trivial True/False questions. Deterministic: candidates are id-sorted and
the first unseen one per (depth, label, prefix) is taken.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = DATA / ".cache"
DEFAULT_OUT = DATA / "proofwriter_tier_a.jsonl"

DATASET = "tasksource/proofwriter"
SPLIT = "validation"
SOURCE_URL = "https://huggingface.co/datasets/tasksource/proofwriter"
PREFIX_ROTATION = ["AttNeg", "RelNeg", "AttNoneg", "RelNoneg"]
LABELS = ["True", "False", "Unknown"]
PER_GROUP = 3


def _api(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_shards() -> list[Path]:
    info = _api(f"https://huggingface.co/api/datasets/{DATASET}")
    shards = sorted(
        sibling["rfilename"]
        for sibling in info["siblings"]
        if re.fullmatch(rf"data/{SPLIT}-.*\.parquet", sibling["rfilename"])
    )
    if not shards:
        raise SystemExit(f"no {SPLIT} parquet shards found for {DATASET}")
    CACHE.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for shard in shards:
        path = CACHE / Path(shard).name
        if not path.exists():
            url = f"{SOURCE_URL}/resolve/main/{shard}"
            print(f"downloading {url}")
            with urllib.request.urlopen(url, timeout=300) as response:
                path.write_bytes(response.read())
        paths.append(path)
    return paths


def _load_rows() -> list[dict]:
    rows: list[dict] = []
    for path in _download_shards():
        rows.extend(pq.read_table(path).to_pylist())
    return rows


def _prefix(record_id: str) -> str:
    return record_id.split("-", 1)[0]


def _depth(config: str) -> int:
    return int(config.split("-", 1)[1])


def _eligible(rows: list[dict]) -> list[dict]:
    core = [row for row in rows if re.fullmatch(r"depth-\d+", row["config"])]
    kept = []
    for row in core:
        if _depth(row["config"]) > 0 and row["QDep"] < 1:
            continue
        row = dict(row)
        row["prefix"] = _prefix(row["id"])
        kept.append(row)
    return kept


def select(rows: list[dict]) -> list[dict]:
    """Deterministic Tier A selection from the validation rows."""
    eligible = _eligible(rows)
    by_group: dict[tuple[str, str, str], list[dict]] = {}
    for row in eligible:
        by_group.setdefault((row["config"], row["answer"], row["prefix"]), []).append(row)
    for bucket in by_group.values():
        bucket.sort(key=lambda row: row["id"])

    selected: list[dict] = []
    seen: set[str] = set()
    groups = sorted(
        {(row["config"], row["answer"]) for row in eligible},
        key=lambda item: (_depth(item[0]), LABELS.index(item[1])),
    )
    for index, (config, label) in enumerate(groups):
        offset = index % len(PREFIX_ROTATION)
        taken = 0
        for step in range(len(PREFIX_ROTATION)):
            if taken >= PER_GROUP:
                break
            prefix = PREFIX_ROTATION[(offset + step) % len(PREFIX_ROTATION)]
            for row in by_group.get((config, label, prefix), []):
                if row["id"] in seen:
                    continue
                selected.append(row)
                seen.add(row["id"])
                taken += 1
                break
    selected.sort(key=lambda row: (_depth(row["config"]), LABELS.index(row["answer"]), row["id"]))
    return selected


def _record(row: dict) -> dict:
    return {
        "id": row["id"],
        "source": DATASET,
        "source_url": SOURCE_URL,
        "config": row["config"],
        "depth": _depth(row["config"]),
        "prefix": row["prefix"],
        "answer": row["answer"],
        "maxD": row["maxD"],
        "QDep": row["QDep"],
        "NFact": row["NFact"],
        "NRule": row["NRule"],
        "theory": row["theory"],
        "question": row["question"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the ProofWriter Tier A sample.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    selected = select(_load_rows())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps(_record(row), ensure_ascii=False) + "\n")

    counts: dict[tuple[str, str], int] = {}
    for row in selected:
        key = (row["config"], row["answer"])
        counts[key] = counts.get(key, 0) + 1
    for (config, label), count in sorted(
        counts.items(), key=lambda item: (_depth(item[0][0]), LABELS.index(item[0][1]))
    ):
        print(f"  {config:9} {label:8} {count}")
    print(f"wrote {len(selected)} problems to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
