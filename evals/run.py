"""Eval harness CLI: run live problems, dump full traces, print metrics.

Usage (from the repo root, real LLM calls):
    ANKYRA_LIVE=1 uv run python -m evals.run
    uv run python -m evals.run --ids rain,chain
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from ankyra.build.symbolic import symbolic_check
from ankyra.config.settings import settings
from ankyra.graph.build import run_problem
from ankyra.llm.trace import tracing

from evals.evaluators import ExpectationEvaluator, InvariantEvaluator, VocabularyEvaluator

ROOT = Path(__file__).resolve().parent
PROBLEMS = ROOT / "problems.jsonl"
OUT = ROOT / "out"


def load_problems(path: Path = PROBLEMS) -> list[dict]:
    problems = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            problems.append(json.loads(line))
    return problems


def run_one(problem: dict) -> tuple[dict, object]:
    """Run one problem with LLM tracing, returning its trace dict and result."""
    previous_builtins = settings.get("BUILTINS", False)
    previous_defeasible = settings.get("DEFEASIBLE", False)
    settings.set("BUILTINS", bool(problem.get("builtins", False)))
    settings.set("DEFEASIBLE", bool(problem.get("defeasible", False)))
    started = time.perf_counter()
    try:
        with tracing() as llm_trace:
            result = run_problem(
                problem["text"],
                allow_hypotheses=problem.get("allow_hypotheses", True),
                max_waves=problem.get("max_waves", 6),
            )
    finally:
        settings.set("BUILTINS", previous_builtins)
        settings.set("DEFEASIBLE", previous_defeasible)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)

    trace = {
        "id": problem.get("id"),
        "level": problem.get("level"),
        "text": problem["text"],
        "status": result.status,
        "structure": result.structure.model_dump() if result.structure else None,
        "theory": result.theory.model_dump() if result.theory else None,
        "symbolic": asdict(symbolic_check(result.theory)) if result.theory else None,
        "query": result.query.model_dump() if result.query else None,
        "verdict": result.verdict.model_dump() if result.verdict else None,
        "answer": result.answer.model_dump() if result.answer else None,
        "explanation": result.explanation.model_dump() if result.explanation else None,
        "waves": [w.model_dump() for w in result.history],
        "hypotheses": [h.model_dump() for h in result.hypotheses],
        "revisions": [r.model_dump() for r in result.revisions],
        "llm_calls": [asdict(call) for call in llm_trace.calls],
        "duration_ms": duration_ms,
    }
    scores = [
        InvariantEvaluator().evaluate(problem, result, trace),
        ExpectationEvaluator().evaluate(problem, result, trace),
        VocabularyEvaluator().evaluate(problem, result, trace),
    ]
    trace["scores"] = [asdict(score) for score in scores]
    return trace, result


def _summary(traces: list[dict]) -> str:
    total = len(traces)
    supported = sum(1 for t in traces if t["status"] == "supported")
    proven = sum(1 for t in traces if t["answer"] and t["answer"]["strength"] == "proven")
    invariant_ok = sum(
        1 for t in traces if next(s for s in t["scores"] if s["name"] == "invariants")["passed"]
    )
    calls = sum(len(t["llm_calls"]) for t in traces)
    reuses = [
        next(s for s in t["scores"] if s["name"] == "vocabulary")["metrics"][
            "condition_predicate_reuse"
        ]
        for t in traces
    ]
    vocab = f" vocab_reuse={sum(reuses) / len(reuses):.2f}" if reuses else ""
    return (
        f"summary: {total} problems | supported={supported} proven={proven} "
        f"invariant_ok={invariant_ok}{vocab} | llm_calls={calls}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Ankyra eval harness.")
    parser.add_argument("--ids", default="", help="Comma-separated problem ids (default: all).")
    parser.add_argument("--out", default=str(OUT), help="Directory for trace JSON files.")
    parser.add_argument("--no-write", action="store_true", help="Do not write trace files.")
    args = parser.parse_args(argv)

    wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
    problems = [p for p in load_problems() if not wanted or p.get("id") in wanted]
    out_dir = Path(args.out)
    if not args.no_write:
        out_dir.mkdir(parents=True, exist_ok=True)

    traces = []
    for problem in problems:
        trace, _ = run_one(problem)
        traces.append(trace)
        if not args.no_write:
            (out_dir / f"{problem['id']}.json").write_text(
                json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        answer = trace["answer"] or {}
        print(
            f"[{problem.get('id')}] L{problem.get('level', '?')} "
            f"status={trace['status']} strength={answer.get('strength', '?')} "
            f"hyps={answer.get('hypotheses_used', [])} waves={len(trace['waves'])} "
            f"calls={len(trace['llm_calls'])} {trace['duration_ms']}ms"
        )
        for score in trace["scores"]:
            label = {"invariants": "INVARIANT", "expectations": "EXPECT"}.get(
                score["name"], score["name"].upper()
            )
            for note in score["notes"]:
                print(f"    {label}: {note}")

    if traces:
        print()
        print(_summary(traces))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
