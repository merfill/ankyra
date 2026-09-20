"""ProntoQA-OOD eval adapter over the committed compositional sample (L2 gate).

Source: ``tasksource/prontoqa`` (the OOD release). ``evals/data/prontoqa_ood_tier_a.jsonl``
is a deterministic sample stratified by rule type and L2 class, produced by
``evals.build_prontoqa_ood_sample``. Recon: ``docs/prontoqa.md`` §9.

Mapping (benchmark semantics stay out of the engine): a ``Prove: <statement>`` query
asserts its statement is true, so the engine answer is scored polarity-aware exactly
like ProntoQA v1 (``evals.prontoqa.expected_kind``): the extracted positive ask is
derivable when the statement is positive, and refuted when the statement is negative.

This adapter runs the engine at ``logic="ground"`` (``ANKYRA_LOGIC``). It needs
compound-goal extraction (``ask_all``/``ask_any``) from Phase 0 to form ``and``/``or``
targets; until the extraction prompt teaches those forms, compound cases report no
target and are not scored on kind (``out_of_fragment`` and undecided are counted, not
failed).

Usage:
    uv run python -m evals.prontoqa_ood [--tier a|b] [--ids ...] [--limit N] [--no-write]
        [--jobs N]

Running this invokes the real LLM extractor and costs tokens; the synthetic gate
(``evals.l2_synthetic``) is the LLM-free primary gate.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ankyra.core.models import Query
from evals.prontoqa import expected_kind, mismatch_shape
from evals.run import iter_run_many

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "prontoqa_ood_tier_a.jsonl"
OUT = ROOT / "out" / "prontoqa_ood"
TIERS = ["a", "b"]


def sample_path(tier: str = "a") -> Path:
    return ROOT / "data" / f"prontoqa_ood_tier_{tier}.jsonl"


def load_sample(path: Path = SAMPLE) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def problem_text(record: dict) -> str:
    """Theory (``question``) plus the ``Prove:`` query, unchanged from the collection."""
    return f"{record['question'].strip()}\n\n{record['query'].strip()}"


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
        expected = expected_kind(record["answer"], False)
    answer = getattr(result, "answer", None)
    actual = answer.kind if answer is not None else None
    status = getattr(result, "status", None)
    return {
        "id": record["id"],
        "rule_type": record["rule_type"],
        "class": record["class"],
        "expected_kind": expected,
        "actual_kind": actual,
        "kind_match": polarity_known and expected == actual,
        "polarity_known": polarity_known,
        "statement_negative": statement_negative,
        "target_negated": bool(target.negated) if target is not None else None,
        "polarity_flipped": flipped,
        "status": status,
        "strength": answer.strength if answer is not None else None,
        "out_of_fragment": status == "out_of_fragment",
    }


def _to_problem(record: dict, *, allow_hypotheses: bool) -> dict:
    return {
        "id": record["id"],
        "text": problem_text(record),
        "builtins": False,
        "defeasible": False,
        "logic": "ground",
        "allow_hypotheses": allow_hypotheses,
        "max_waves": 4,
        "world_assumption": "open",
    }


def _report(scores: list[dict]) -> None:
    known = [s for s in scores if s["polarity_known"]]
    hits = sum(1 for s in known if s["kind_match"])
    accuracy = f"{hits}/{len(known)} ({hits / len(known):.0%})" if known else "n/a"
    print()
    print(f"kind accuracy: {accuracy}")
    print(f"out_of_fragment: {sum(1 for s in scores if s['out_of_fragment'])}")
    print(f"unknown polarity (no target extracted): {len(scores) - len(known)}")
    print(f"statuses: {dict(Counter(s['status'] for s in scores).most_common())}")
    print(f"strengths: {dict(Counter(s['strength'] for s in scores).most_common())}")
    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for score in known:
        bucket = by_type[score["rule_type"]]
        bucket[1] += 1
        bucket[0] += int(score["kind_match"])
    for name in sorted(by_type):
        hit, total = by_type[name]
        print(f"  {name:14} {hit}/{total} ({hit / total:.0%})")
    failures = [s for s in known if not s["kind_match"]]
    if failures:
        print(f"  mismatches ({len(failures)}):")
        for score in failures:
            print(
                f"    {score['id']:40} {score['rule_type']:14} want {score['expected_kind']:5} "
                f"got {score['actual_kind']:5} ({score['status']}) [{score.get('shape')}]"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ProntoQA-OOD eval.")
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
            (out_dir / f"{record['id'].replace('#', '_')}.json").write_text(
                json.dumps({"record": record, "score": score, "trace": trace}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        flag = "OK " if score["kind_match"] else "ERR"
        print(
            f"[{flag}] {record['id']:40} {record['rule_type']:14} {record['class']:20} "
            f"kind={score['actual_kind']} status={score['status']} waves={len(trace['waves'])}"
        )
    _report(scores)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
