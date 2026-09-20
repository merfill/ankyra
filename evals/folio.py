"""FOLIO eval adapter over the committed negation-subset sample (L1 cross-check).

Source: Han et al., FOLIO, ``github.com/Yale-LILY/FOLIO`` (MIT), ``data/v0.0``.
``evals/data/folio_negation_tier_a.jsonl`` is the deterministic L1 slice (explicit
negation, universal implications, conjunction, atomic facts; no disjunction,
existential, equality, XOR, biconditional or multi-variable quantification), built by
``evals.build_folio_sample``. Notes and fragment rules: ``docs/folio.md``.

The FOLIO label is three-way with an open-world ``Uncertain``:

    True      -> entailed      -> answer.kind "yes"
    False     -> refuted       -> answer.kind "no"
    Uncertain -> neither       -> answer.kind "unknown"

The world stays open: ``Uncertain`` must never be turned into a decision by closing
the world. This is the secondary L1 gate (real text); the primary gate is the
synthetic collection. Running the adapter invokes the LLM extractor and costs
tokens.

Usage:
    uv run python -m evals.folio [--ids a,b] [--limit N] [--no-write] [--hypotheses]
        [--jobs N]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ankyra.core.models import Query
from evals.run import iter_run_many

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "folio_negation_tier_a.jsonl"
OUT = ROOT / "out" / "folio"

_LABEL_TO_KIND = {"True": "yes", "False": "no", "Uncertain": "unknown"}
_SUBSETS = {"negation": "negation", "l2": "l2"}


def sample_path(subset: str = "negation", tier: str = "a") -> Path:
    stem = _SUBSETS.get(subset, "negation")
    return ROOT / "data" / f"folio_{stem}_tier_{tier}.jsonl"


def load_sample(path: Path = SAMPLE) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def problem_text(record: dict) -> str:
    premises = " ".join(premise.strip() for premise in record["premises"])
    return f"{premises}\n\nIs it true that {record['conclusion'].strip().rstrip('.')}?"


def expected_kind(label: str, flipped: bool) -> str:
    kind = _LABEL_TO_KIND[label]
    if not flipped:
        return kind
    return {"yes": "no", "no": "yes", "unknown": "unknown"}[kind]


def score_record(record: dict, result: object) -> dict:
    query: Query | None = getattr(result, "query", None)
    target = query.target if query is not None else None
    statement_negative = bool(record["statement_negative"])
    if target is not None:
        polarity_known = True
        flipped = statement_negative != bool(target.negated)
        expected = expected_kind(record["label"], flipped)
    else:
        polarity_known = False
        flipped = None
        expected = _LABEL_TO_KIND[record["label"]]
    answer = getattr(result, "answer", None)
    actual = answer.kind if answer is not None else None
    return {
        "id": record["id"],
        "label": record["label"],
        "expected_kind": expected,
        "actual_kind": actual,
        "kind_match": polarity_known and expected == actual,
        "polarity_known": polarity_known,
        "statement_negative": statement_negative,
        "target_negated": bool(target.negated) if target is not None else None,
        "polarity_flipped": flipped,
        "status": getattr(result, "status", None),
        "strength": answer.strength if answer is not None else None,
        "value": answer.value if answer is not None else None,
    }


def mismatch_shape(score: dict, trace: dict) -> str:
    if score.get("kind_match"):
        return "match"
    if score.get("strength") == "proven":
        return "grounded_mismatch"
    if score.get("strength") != "proven_under":
        return "undecided_mismatch"
    target = (trace.get("query") or {}).get("target") or {}
    for hypothesis in trace.get("hypotheses") or []:
        payload = hypothesis.get("payload") or {}
        if (
            payload.get("predicate") == target.get("predicate")
            and payload.get("subject") == target.get("subject")
            and payload.get("object") == target.get("object")
        ):
            return "question_begging"
    return "hypothetical_decision"


def _to_problem(record: dict, *, allow_hypotheses: bool, logic: str = "off") -> dict:
    return {
        "id": record["id"],
        "text": problem_text(record),
        "builtins": False,
        "defeasible": False,
        "logic": logic,
        "allow_hypotheses": allow_hypotheses,
        "max_waves": 4,
        "world_assumption": "open",
    }


def _report(scores: list[dict]) -> None:
    known = [s for s in scores if s["polarity_known"]]
    hits = sum(1 for s in known if s["kind_match"])
    print()
    print(f"kind accuracy: {hits}/{len(known)} ({hits / len(known):.0%})")
    print(f"unknown polarity (no target extracted): {len(scores) - len(known)}")
    print(f"statuses: {dict(Counter(s['status'] for s in scores).most_common())}")
    print(f"strengths: {dict(Counter(s['strength'] for s in scores).most_common())}")
    by_label: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for score in known:
        bucket = by_label[score["label"]]
        bucket[1] += 1
        bucket[0] += int(score["kind_match"])
    for name in sorted(by_label):
        hit, total = by_label[name]
        print(f"  {name:10} {hit}/{total} ({hit / total:.0%})")
    failures = [s for s in known if not s["kind_match"]]
    if failures:
        print(f"  mismatches ({len(failures)}):")
        for score in failures:
            print(
                f"    {score['id']:20} want {score['label']:9} -> {score['expected_kind']:7} "
                f"got {score['actual_kind']:7} ({score['status']}) [{score.get('shape')}]"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the FOLIO eval (L1 negation or L2).")
    parser.add_argument("--subset", default="negation", choices=sorted(_SUBSETS), help="Committed subset (default: negation).")
    parser.add_argument("--tier", default="a", help="Committed tier (default: a).")
    parser.add_argument("--logic", default="", help="Logic level override (default: ground for the L2 subset, off otherwise).")
    parser.add_argument("--ids", default="", help="Comma-separated ids (default: all).")
    parser.add_argument("--limit", type=int, default=0, help="Run at most N problems.")
    parser.add_argument("--out", default=str(OUT), help="Directory for per-problem traces.")
    parser.add_argument("--no-write", action="store_true", help="Do not write trace files.")
    parser.add_argument("--hypotheses", action="store_true", help="Abductive mode: allow hypotheses.")
    parser.add_argument("--jobs", type=int, default=1, help="Run up to N problems concurrently (default: 1).")
    args = parser.parse_args(argv)

    logic = args.logic or ("ground" if args.subset == "l2" else "off")
    wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
    records = [r for r in load_sample(sample_path(args.subset, args.tier)) if not wanted or r["id"] in wanted]
    if args.limit:
        records = records[: args.limit]
    out_dir = Path(args.out)
    if not args.no_write:
        out_dir.mkdir(parents=True, exist_ok=True)

    problems = [
        _to_problem(record, allow_hypotheses=args.hypotheses, logic=logic)
        for record in records
    ]
    scores: list[dict | None] = [None] * len(records)
    for index, trace, result in iter_run_many(problems, jobs=args.jobs):
        record = records[index]
        score = score_record(record, result)
        score["shape"] = mismatch_shape(score, trace)
        scores[index] = score
        if not args.no_write:
            (out_dir / f"{record['id']}.json").write_text(
                json.dumps({"record": record, "score": score, "trace": trace}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        flag = "OK " if score["kind_match"] else "ERR"
        print(
            f"[{flag}] {record['id']:20} {record['label']:9} kind={score['actual_kind']} "
            f"status={score['status']} waves={len(trace['waves'])}"
        )
    _report(scores)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
