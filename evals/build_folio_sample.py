"""Build the committed FOLIO negation subset (L1 cross-check on real text).

Source: Han et al., FOLIO, ``github.com/Yale-LILY/FOLIO`` (MIT), ``data/v0.0``.
The corpus is not one fragment; ``docs/folio.md`` §4 stratifies by the constructs the
FOL annotation uses. This builder selects the **negation** slice that stays inside
L1: explicit negation, universal implications, conjunction and atomic facts — no
disjunction, existential, equality, XOR, biconditional or function terms, which are
L2 or beyond.

This is the secondary L1 gate (real data); the primary gate is the synthetic
collection (``evals.l1_synthetic``). Running the adapter costs LLM tokens.

Run once (no extra dependencies):

    uv run python -m evals.build_folio_sample --tier a
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
CACHE = DATA / ".cache" / "folio"

SOURCE = "Yale-LILY/FOLIO"
# Only the v0.0 validation split carries ``conclusion-FOL`` on GitHub; the train
# split omits it, so the negation slice is built from validation.
SPLITS = {
    "validation": "https://raw.githubusercontent.com/Yale-LILY/FOLIO/main/data/v0.0/folio-validation.jsonl",
}
TIERS: dict[str, int] = {"a": 15}  # rows per label

_CONSTRUCTS = {
    "disjunction": "∨",
    "existential": "∃",
    "equality": "=",
    "xor": "⊕",
    "biconditional": "↔",
    "negation": "¬",
}
_BEYOND_L1 = {"disjunction", "existential", "equality", "xor", "biconditional", "multivar"}
# Constructs beyond the committed L2 fragment (functions/equality/schemas + XOR/bicond).
_BEYOND_L2 = {"equality", "xor", "biconditional", "multivar"}
# A quantified or compound conclusion is an L2 target; the L1 query path expects a
# ground literal (a negated atom is fine).
_CONCLUSION_COMPOUND = ("∀", "∃", "→", "∧", "∨", "↔", "⊕")


def _download(split: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{split}.jsonl"
    if not path.exists():
        url = SPLITS[split]
        print(f"downloading {url}")
        with urllib.request.urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
    return path


def _load_rows() -> list[dict]:
    rows: list[dict] = []
    for split in SPLITS:
        text = _download(split).read_text(encoding="utf-8")
        for index, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            row = json.loads(line)
            row["split"] = split
            row["index"] = index
            rows.append(row)
    return rows


def constructs(row: dict) -> set[str]:
    """FOL constructs used by an example (over premises and conclusion).

    Function terms are not separately detected: FOLIO v0.0 has no clean function
    field and a regex over quantifier-scope parentheses false-fires. Multi-variable
    quantification and the beyond-L1 operators are excluded instead.
    """
    formulas = [*row["premises-FOL"], row["conclusion-FOL"]]
    joined = " ".join(formulas)
    found = {name for name, token in _CONSTRUCTS.items() if token in joined}
    if any(formula.count("∀") > 1 for formula in formulas):
        found.add("multivar")
    return found


def in_l1_negation(row: dict) -> bool:
    """True when the example stays inside the L1 negation fragment.

    The conclusion must be a ground literal: a universally/existentially quantified
    or compound conclusion is an L2 target, not a yes/no question about a ground
    atom (docs/folio.md §4).
    """
    used = constructs(row)
    if "negation" not in used or (used & _BEYOND_L1):
        return False
    return not any(token in row["conclusion-FOL"] for token in _CONCLUSION_COMPOUND)


def in_l2(row: dict) -> bool:
    """True when the example stays inside the L2 fragment (``∨``/``∃``, no functions).

    L2 adds disjunction and the existential quantifier to L1; equality, XOR,
    biconditional and multi-variable quantification remain beyond the committed
    fragment (``docs/folio.md`` §4, ``docs/l2_plan.md`` D-L2-4).
    """
    used = constructs(row)
    if not (used & {"disjunction", "existential"}):
        return False
    return not (used & _BEYOND_L2)


def _record(row: dict) -> dict:
    return {
        "id": f"folio-{row['split']}-{row['index']:04d}",
        "source": SOURCE,
        "split": row["split"],
        "index": row["index"],
        "premises": row["premises"],
        "premises_fol": row["premises-FOL"],
        "conclusion": row["conclusion"],
        "conclusion_fol": row["conclusion-FOL"],
        "label": row["label"],
        "statement_negative": bool(re.search(r"\bnot\b|\bno\b|\bnever\b", row["conclusion"], re.IGNORECASE)),
        "constructs": sorted(constructs(row)),
    }


def select(rows: list[dict], tier: str = "a") -> list[dict]:
    if tier not in TIERS:
        raise SystemExit(f"unknown tier {tier!r}; choose from {', '.join(TIERS)}")
    per_label = TIERS[tier]
    by_label: dict[str, list[dict]] = defaultdict(list)
    for raw in rows:
        if in_l1_negation(raw):
            by_label[raw["label"]].append(_record(raw))
    selected: list[dict] = []
    for label in sorted(by_label):
        selected.extend(sorted(by_label[label], key=lambda r: r["id"])[:per_label])
    selected.sort(key=lambda r: (r["label"], r["id"]))
    return selected


def select_l2(rows: list[dict], tier: str = "a") -> list[dict]:
    """The L2 slice: disjunction and/or existential, no equality/XOR/biconditional."""
    if tier not in TIERS:
        raise SystemExit(f"unknown tier {tier!r}; choose from {', '.join(TIERS)}")
    per_label = TIERS[tier]
    by_label: dict[str, list[dict]] = defaultdict(list)
    for raw in rows:
        if in_l2(raw):
            by_label[raw["label"]].append(_record(raw))
    selected: list[dict] = []
    for label in sorted(by_label):
        selected.extend(sorted(by_label[label], key=lambda r: r["id"])[:per_label])
    selected.sort(key=lambda r: (r["label"], r["id"]))
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a FOLIO sample (L1 negation or L2).")
    parser.add_argument("--tier", default="a", choices=sorted(TIERS))
    parser.add_argument("--subset", default="negation", choices=["negation", "l2"])
    parser.add_argument("--out", default="", help="Output JSONL (default: data/folio_<subset>_tier_<tier>.jsonl)")
    args = parser.parse_args(argv)

    rows = _load_rows()
    predicate = in_l2 if args.subset == "l2" else in_l1_negation
    selector = select_l2 if args.subset == "l2" else select
    tally = Counter()
    for row in rows:
        for name in constructs(row):
            tally[name] += 1
        if predicate(row):
            tally[f"in_{args.subset}"] += 1
    selected = selector(rows, args.tier)
    default_name = f"folio_{'l2' if args.subset == 'l2' else 'negation'}_tier_{args.tier}.jsonl"
    out = Path(args.out) if args.out else DATA / default_name
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"  rows: {len(rows)}, construct tally: {dict(tally.most_common())}")
    print(f"  by label: {dict(Counter(r['label'] for r in selected).most_common())}")
    print(f"wrote {len(selected)} problems to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
