"""ProntoQA eval adapter over the committed Tier A sample (L0 + explicit negation).

Source: Saparov & He, ProntoQA v1, mirrored at ``smoorsmith/prontoqa`` (Logic-LLM
format). ``evals/data/prontoqa_tier_a.jsonl`` is a deterministic stratified subset
produced by ``evals.build_prontoqa_sample`` (48 problems: positive/negation chains x
statement polarity). Recon and proof-shape notes: ``docs/prontoqa.md`` §8.

Mapping (benchmark semantics stay out of the engine): the engine answers whether the
statement, extracted as a POSITIVE ask, is derivable under an open world:

    A (True)  -> the statement holds   -> answer.kind "yes"  (after the polarity flip)
    B (False) -> the statement fails   -> answer.kind "no"

When the statement is negative ("X is not Y"), the extracted positive ask inverts
the expected kind; the flip is reported per problem.

The v1 negation subset needs only explicit negative rule consequents; the declared
closed world (NAF/CWA) is exercised by the synthetic gate, not here. The adapter sets
``world_assumption="open"`` explicitly.

Usage:
    uv run python -m evals.prontoqa [--tier a|b] [--ids a,b] [--limit N] [--no-write]
        [--hypotheses] [--jobs N]

Running this invokes the real LLM extractor and costs tokens; the synthetic gate
(``evals.l1_synthetic``) is the LLM-free primary gate.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ankyra.core.models import Query
from evals.run import iter_run_many

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "prontoqa_tier_a.jsonl"
OUT = ROOT / "out" / "prontoqa"
TIERS = ["a", "b"]


def sample_path(tier: str = "a") -> Path:
    return ROOT / "data" / f"prontoqa_tier_{tier}.jsonl"


_TRUTH = {"A": True, "B": False}


def load_sample(path: Path = SAMPLE) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def problem_text(record: dict) -> str:
    """Theory plus the question, unchanged from the collection."""
    return f"{record['context'].strip()}\n\n{record['question'].strip()}"


def expected_kind(label: str, flipped: bool) -> str:
    """Expected ``Answer.kind`` for an A/B label, polarity-aware."""
    kind = "yes" if _TRUTH[label] else "no"
    if not flipped:
        return kind
    return {"yes": "no", "no": "yes"}[kind]


def score_record(record: dict, result: object) -> dict:
    """Detailed per-problem score; ``result`` is a ``run_problem`` result."""
    query: Query | None = getattr(result, "query", None)
    target = query.target if query is not None else None
    statement_negative = bool(record["statement_negative"])
    if target is not None:
        polarity_known = True
        flipped = statement_negative != bool(target.negated)
        expected = expected_kind(record["answer"], flipped)
    else:
        polarity_known = False
        flipped = None
        expected = "yes" if _TRUTH[record["answer"]] else "no"
    answer = getattr(result, "answer", None)
    actual = answer.kind if answer is not None else None
    return {
        "id": record["id"],
        "proof_shape": record["proof_shape"],
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
    """Classify an answer mismatch (mirrors the ProofWriter adapter)."""
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
    by_shape: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for score in known:
        bucket = by_shape[score["proof_shape"]]
        bucket[1] += 1
        bucket[0] += int(score["kind_match"])
    for name in sorted(by_shape):
        hit, total = by_shape[name]
        print(f"  {name:10} {hit}/{total} ({hit / total:.0%})")
    failures = [s for s in known if not s["kind_match"]]
    if failures:
        print(f"  mismatches ({len(failures)}):")
        for score in failures:
            print(
                f"    {score['id']:24} {score['proof_shape']:9} want {score['expected_label']} "
                f"-> {score['expected_kind']:5} got {score['actual_kind']:5} "
                f"({score['status']}) [{score.get('shape')}]"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ProntoQA eval.")
    parser.add_argument("--tier", default="a", choices=TIERS, help="Committed sample tier (default: a).")
    parser.add_argument("--ids", default="", help="Comma-separated problem ids (default: all).")
    parser.add_argument("--limit", type=int, default=0, help="Run at most N problems.")
    parser.add_argument("--out", default=str(OUT), help="Directory for per-problem traces.")
    parser.add_argument("--no-write", action="store_true", help="Do not write trace files.")
    parser.add_argument("--hypotheses", action="store_true", help="Abductive mode: allow hypotheses.")
    parser.add_argument("--jobs", type=int, default=1, help="Run up to N problems concurrently (default: 1).")
    args = parser.parse_args(argv)

    wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
    records = [r for r in load_sample(sample_path(args.tier)) if not wanted or r["id"] in wanted]
    if args.limit:
        records = records[: args.limit]
    out_dir = Path(args.out)
    if not args.no_write:
        out_dir.mkdir(parents=True, exist_ok=True)

    problems = [_to_problem(record, allow_hypotheses=args.hypotheses) for record in records]
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
        flip = " flip" if score["polarity_flipped"] else ""
        print(
            f"[{flag}] {record['id']:24} {record['proof_shape']:9} {record['answer']} "
            f"kind={score['actual_kind']} status={score['status']} waves={len(trace['waves'])}{flip}"
        )
    _report(scores)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
