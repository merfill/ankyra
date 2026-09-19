"""ProofWriter eval adapter over the committed Tier A sample.

Source: Tafjord et al., "ProofWriter" (2021), open-world synthetic core (OWA),
mirrored at ``tasksource/proofwriter``. ``evals/data/proofwriter_tier_a.jsonl``
is a deterministic stratified subset produced by
``evals.build_proofwriter_sample`` (45 problems: depth 0/1/2/3/5 x
True/False/Unknown x prefix rotation).

Mapping (benchmark semantics stay out of the engine): the engine answers
"is the statement, as written, derivable?" under strict deduction
(``DEFEASIBLE=False``):

    True    -> answer.kind "yes"      (the statement is entailed)
    False   -> answer.kind "no"       (its negation is entailed)
    Unknown -> answer.kind "unknown"  (neither)

Strict deduction is the default (``allow_hypotheses=False``): hypotheses let the
proposal wave abduce the missing links and "prove" statements the benchmark marks
Unknown, which is not what this benchmark measures. Pass ``--hypotheses`` for the
abductive mode, where a repair that reuses an already-grounded quote is ledgered
as a hypothesis (never silently ``cited``) and the report splits matched
determinate answers into ``proven`` and ``proven_under``.

When the extractor rewrites a negated statement into a positive ask, the
expected label is inverted to match the ask that was actually verified; the flip
is reported per problem.

Usage:
    uv run python -m evals.proofwriter [--ids a,b] [--limit N] [--no-write]
        [--hypotheses]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ankyra.core.models import Query
from evals.run import run_one

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "proofwriter_tier_a.jsonl"
OUT = ROOT / "out" / "proofwriter"

_LABEL_TO_KIND = {"True": "yes", "False": "no", "Unknown": "unknown"}
_DEPTHS = ["depth-0", "depth-1", "depth-2", "depth-3", "depth-5"]
_LABELS = ["True", "False", "Unknown"]


def load_sample(path: Path = SAMPLE) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def problem_text(record: dict) -> str:
    """Theory plus the question as an explicit yes/no about the statement."""
    statement = record["question"].strip().rstrip(".")
    return f"{record['theory']}\n\nIs it true that {statement}?"


def is_negative(statement: str) -> bool:
    """The ProofWriter questions use explicit ``is not`` / ``does not``."""
    return " not " in f" {statement.strip().rstrip('.')} " or "n't" in statement


def expected_kind(label: str, flipped: bool) -> str:
    """Expected ``Answer.kind`` for a ProofWriter label, polarity-aware."""
    kind = _LABEL_TO_KIND[label]
    if not flipped:
        return kind
    return {"yes": "no", "no": "yes", "unknown": "unknown"}[kind]


def score_record(record: dict, result: object) -> dict:
    """Detailed per-problem score; ``result`` is a ``run_problem`` result."""
    query: Query | None = getattr(result, "query", None)
    target = query.target if query is not None else None
    statement_negative = is_negative(record["question"])
    if target is not None:
        polarity_known = True
        flipped = statement_negative != bool(target.negated)
        expected = expected_kind(record["answer"], flipped)
    else:
        polarity_known = False
        flipped = None
        expected = _LABEL_TO_KIND[record["answer"]]
    answer = getattr(result, "answer", None)
    actual = answer.kind if answer is not None else None
    return {
        "id": record["id"],
        "expected_label": record["answer"],
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
    """Classify an answer mismatch so the abductive report is not a flat list.

    ``grounded_mismatch`` is the serious one (a strict proof against the label);
    ``hypothetical_decision`` means abduction supplied a hypothesis to decide an
    Unknown; ``question_begging`` means a hypothesis restates the target itself.
    """
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


def _to_problem(record: dict, *, allow_hypotheses: bool) -> dict:
    return {
        "id": record["id"],
        "text": problem_text(record),
        "builtins": False,
        "defeasible": False,
        "allow_hypotheses": allow_hypotheses,
        "max_waves": 4,
    }


def _accuracy(scores: list[dict], key) -> dict[str, tuple[int, int]]:
    buckets: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for score in scores:
        bucket = buckets[str(key(score))]
        bucket[1] += 1
        bucket[0] += int(score["kind_match"])
    return {name: (hit, total) for name, (hit, total) in buckets.items()}


def _print_accuracy(title: str, table: dict[str, tuple[int, int]]) -> None:
    if not table:
        return
    print(f"  {title}:")
    for name in sorted(table, key=lambda item: (_DEPTHS.index(item) if item in _DEPTHS else 99, item)):
        hit, total = table[name]
        print(f"    {name:22} {hit}/{total} ({hit / total:.0%})")


def _report(scores: list[dict], records: dict[str, dict]) -> None:
    known = [s for s in scores if s["polarity_known"]]
    hits = sum(1 for s in known if s["kind_match"])
    print()
    print(f"kind accuracy: {hits}/{len(known)} ({hits / len(known):.0%})")
    print(f"unknown polarity (no target extracted): {len(scores) - len(known)}")
    flips = [s for s in scores if s["polarity_flipped"]]
    print(f"polarity flips: {len(flips)}")
    print(f"statuses: {dict(Counter(s['status'] for s in scores).most_common())}")
    print(f"strengths: {dict(Counter(s['strength'] for s in scores).most_common())}")
    print(f"shapes: {dict(Counter(s.get('shape') for s in scores).most_common())}")
    determinate = [s for s in known if s["expected_label"] in {"True", "False"}]
    matched = [s for s in determinate if s["kind_match"]]
    proven = sum(1 for s in matched if s["strength"] == "proven")
    under = sum(1 for s in matched if s["strength"] == "proven_under")
    print(f"determinate matches: {len(matched)}/{len(determinate)} (proven={proven}, proven_under={under})")
    print(f"contradiction/no_progress: {dict(Counter(s['status'] for s in scores if s['status'] in {'contradiction', 'no_progress', 'budget', 'insufficient'}).most_common())}")

    _print_accuracy("by depth", _accuracy(known, lambda s: records[s["id"]]["config"]))
    _print_accuracy("by label", _accuracy(known, lambda s: s["expected_label"]))
    _print_accuracy("by prefix", _accuracy(known, lambda s: records[s["id"]]["prefix"]))
    _print_accuracy("by question polarity", _accuracy(known, lambda s: "negative" if s["statement_negative"] else "positive"))

    failures = [s for s in known if not s["kind_match"]]
    if failures:
        print(f"  mismatches ({len(failures)}):")
        for s in failures:
            record = records[s["id"]]
            print(
                f"    {s['id']:28} {record['config']:9} want {s['expected_label']:8} "
                f"-> {s['expected_kind']:7} got {s['actual_kind']:7} ({s['status']}) "
                f"[{s.get('shape')}]"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ProofWriter Tier A eval.")
    parser.add_argument("--ids", default="", help="Comma-separated problem ids (default: all).")
    parser.add_argument("--limit", type=int, default=0, help="Run at most N problems.")
    parser.add_argument("--out", default=str(OUT), help="Directory for per-problem traces.")
    parser.add_argument("--no-write", action="store_true", help="Do not write trace files.")
    parser.add_argument(
        "--hypotheses", action="store_true", help="Abductive mode: allow hypotheses."
    )
    args = parser.parse_args(argv)

    wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
    records = [r for r in load_sample() if not wanted or r["id"] in wanted]
    if args.limit:
        records = records[: args.limit]
    out_dir = Path(args.out)
    if not args.no_write:
        out_dir.mkdir(parents=True, exist_ok=True)

    by_id = {r["id"]: r for r in records}
    scores: list[dict] = []
    allow_hypotheses = args.hypotheses
    for record in records:
        trace, result = run_one(_to_problem(record, allow_hypotheses=allow_hypotheses))
        score = score_record(record, result)
        score["shape"] = mismatch_shape(score, trace)
        scores.append(score)
        if not args.no_write:
            (out_dir / f"{record['id']}.json").write_text(
                json.dumps({"record": record, "score": score, "trace": trace}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        flag = "OK " if score["kind_match"] else "ERR"
        flip = " flip" if score["polarity_flipped"] else ""
        print(
            f"[{flag}] {record['id']:28} {record['config']:9} {record['answer']:8} "
            f"kind={score['actual_kind']} status={score['status']} waves={len(trace['waves'])}{flip}"
        )
    _report(scores, by_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
