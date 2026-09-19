"""Build the committed ProofWriter samples.

Source: Tafjord et al., "ProofWriter" (2021), open-world (OWA) synthetic core,
mirrored at ``tasksource/proofwriter`` on the Hugging Face Hub. Each tier is a
small stratified subset committed to ``evals/data/proofwriter_tier_<x>.jsonl`` so
eval runs need no network.

Run once (pyarrow is not a project dependency):

    uv run --with pyarrow python -m evals.build_proofwriter_sample --tier a

Tiers (see ``docs/proofwriter.md``):

    a  45  core: 5 depths x 3 labels x 3, rotating over the four families
    b  75  a + 30 NatLang (10 distinct theories x 3 labels)
    c 150  75 core (5 x 3 labels x 5) + 75 NatLang (25 theories x 3 labels)
    d 300  c + 150 depth-3ext (50 theories x 3 labels)

Selection is deterministic. The synthetic core uses only the ``depth-<n>``
configs, three/five questions per (depth, label) group round-robined over the
``AttNeg``/``RelNeg``/``AttNoneg``/``RelNoneg`` families; a core id's ``-D<n>-``
matches its config depth. ``NatLang`` and ``depth-3ext`` are selected by id
prefix and config because the mirror's ``config`` tag is not a clean partition
(the same ``AttNonegNatLang`` rows appear under both ``NatLang`` and
``depth-3ext-NatLang``). For depth >= 1 only questions that need at least one
rule application (``QDep >= 1``) are eligible; depth-0 has no such non-trivial
True/False questions. Every id is used at most once per tier.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = DATA / ".cache"

DATASET = "tasksource/proofwriter"
SPLIT = "validation"
SOURCE_URL = "https://huggingface.co/datasets/tasksource/proofwriter"

CORE_PREFIXES = ["AttNeg", "RelNeg", "AttNoneg", "RelNoneg"]
CORE_DEPTHS = [0, 1, 2, 3, 5]
LABELS = ["True", "False", "Unknown"]
NATLANG_PREFIX = "AttNonegNatLang"

# Per tier: core questions per (depth, label) group; NatLang / depth-3ext
# distinct theories per label (x 3 labels).
TIERS: dict[str, dict[str, int]] = {
    "a": {"core_per_group": 3, "natlang": 0, "ext": 0},
    "b": {"core_per_group": 3, "natlang": 10, "ext": 0},
    "c": {"core_per_group": 5, "natlang": 25, "ext": 0},
    "d": {"core_per_group": 5, "natlang": 25, "ext": 50},
}


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
    import pyarrow.parquet as pq  # optional dependency, only for building

    rows: list[dict] = []
    for path in _download_shards():
        rows.extend(pq.read_table(path).to_pylist())
    return rows


def _prefix(record_id: str) -> str:
    return record_id.split("-", 1)[0]


def _depth(config: str) -> int | None:
    match = re.fullmatch(r"depth-(\d+)", config)
    return int(match.group(1)) if match else None


def _core_rows(rows: list[dict]) -> list[dict]:
    """The synthetic core: clean ``depth-<n>`` configs in the four families."""
    kept: list[dict] = []
    for row in rows:
        if _depth(row["config"]) not in CORE_DEPTHS:
            continue
        if _prefix(row["id"]) not in CORE_PREFIXES:
            continue
        if _depth(row["config"]) > 0 and row["QDep"] < 1:
            continue
        row = dict(row)
        row["prefix"] = _prefix(row["id"])
        kept.append(row)
    return kept


def _round_robin(buckets, count, offset, seen, prefixes) -> list[dict]:
    """Take ``count`` rows round-robined over ``prefixes``, skipping ``seen`` ids.

    ``buckets`` maps prefix -> id-sorted rows. Deterministic: always the first
    unseen row of the next prefix in rotation.
    """
    picked: list[dict] = []
    pointers: dict[str, int] = defaultdict(int)
    step = 0
    limit = count * len(prefixes) + len(prefixes)
    while len(picked) < count and step < limit:
        prefix = prefixes[(offset + step) % len(prefixes)]
        bucket = buckets.get(prefix, [])
        pointer = pointers[prefix]
        while pointer < len(bucket) and bucket[pointer]["id"] in seen:
            pointer += 1
        if pointer < len(bucket):
            row = bucket[pointer]
            picked.append(row)
            seen.add(row["id"])
            pointers[prefix] = pointer + 1
        step += 1
    return picked


def _select_core(rows: list[dict], per_group: int, seen: set[str]) -> list[dict]:
    by_group: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_group[(row["config"], row["answer"])][row["prefix"]].append(row)
    for buckets in by_group.values():
        for bucket in buckets.values():
            bucket.sort(key=lambda row: row["id"])

    groups = sorted(by_group, key=lambda key: (_depth(key[0]), LABELS.index(key[1])))
    selected: list[dict] = []
    for index, key in enumerate(groups):
        selected += _round_robin(by_group[key], per_group, index % len(CORE_PREFIXES), seen, CORE_PREFIXES)
    return selected


def _select_natlang(rows: list[dict], per_label: int) -> list[dict]:
    """Distinct NatLang theories per label; ids are partitioned across labels."""
    by_id_label: dict[tuple[str, str], dict] = {}
    for row in rows:
        if _prefix(row["id"]) != NATLANG_PREFIX:
            continue
        by_id_label.setdefault((row["id"], row["answer"]), dict(row))

    selected: list[dict] = []
    used: set[str] = set()
    for label in LABELS:
        available = sorted(i for (i, answer) in by_id_label if answer == label and i not in used)
        for record_id in available[:per_label]:
            row = by_id_label[(record_id, label)]
            row["prefix"] = NATLANG_PREFIX
            selected.append(row)
            used.add(record_id)
    return selected


def _select_ext(rows: list[dict], per_label: int, seen: set[str]) -> list[dict]:
    """depth-3ext theories, round-robined over the four core families."""
    by_label: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["config"] != "depth-3ext" or _prefix(row["id"]) not in CORE_PREFIXES:
            continue
        row = dict(row)
        row["prefix"] = _prefix(row["id"])
        by_label[row["answer"]][row["prefix"]].append(row)
    for buckets in by_label.values():
        for bucket in buckets.values():
            bucket.sort(key=lambda row: row["id"])

    selected: list[dict] = []
    for index, label in enumerate(LABELS):
        selected += _round_robin(by_label[label], per_label, index, seen, CORE_PREFIXES)
    return selected


def _sort_key(row: dict):
    depth = _depth(row["config"])
    return (depth if depth is not None else 99, LABELS.index(row["answer"]), row["id"])


def select(rows: list[dict], tier: str = "a") -> list[dict]:
    """Deterministic selection for one tier from the validation rows."""
    if tier not in TIERS:
        raise SystemExit(f"unknown tier {tier!r}; choose from {', '.join(TIERS)}")
    spec = TIERS[tier]
    seen: set[str] = set()
    selected = _select_core(_core_rows(rows), spec["core_per_group"], seen)
    if spec["natlang"]:
        selected += _select_natlang(rows, spec["natlang"])
    if spec["ext"]:
        selected += _select_ext(rows, spec["ext"], seen)
    selected.sort(key=_sort_key)
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
    parser = argparse.ArgumentParser(description="Build a ProofWriter tier sample.")
    parser.add_argument("--tier", default="a", choices=sorted(TIERS))
    parser.add_argument("--out", default="", help="Output JSONL (default: data/proofwriter_tier_<tier>.jsonl)")
    args = parser.parse_args(argv)

    selected = select(_load_rows(), args.tier)
    out = Path(args.out) if args.out else DATA / f"proofwriter_tier_{args.tier}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps(_record(row), ensure_ascii=False) + "\n")

    counts: dict[tuple[str, str], int] = {}
    for row in selected:
        key = (row["config"], row["answer"])
        counts[key] = counts.get(key, 0) + 1
    for (config, label), count in sorted(
        counts.items(), key=lambda item: (_sort_key({"config": item[0][0], "answer": item[0][1], "id": ""}))
    ):
        print(f"  {config:20} {label:8} {count}")
    print(f"wrote {len(selected)} problems to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
