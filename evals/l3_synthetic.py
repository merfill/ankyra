"""Run the L3 synthetic collection (structural, LLM-free) and report the gate.

Each case is a fully structured CSP game/question with an independently written
expected decision. The runner builds the engine models directly, calls
``decide_question`` (with an optional per-case budget override) and compares the
outcome; no extraction, no LLM, no provider variance.

Usage:
    uv run python -m evals.l3_synthetic [--sample PATH] [--ids a,b] [--limit N]

Exit code is non-zero when any case mismatches, so it works as a gate.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ankyra.engine.csp import CspGame, CspQuestion, decide_question

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "l3_synthetic.jsonl"


def load_sample(path: Path = SAMPLE) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate(case: dict) -> dict:
    """Run one structured case and compare the decision to the expectation."""
    game = CspGame.model_validate(case["game"])
    question = CspQuestion.model_validate(case["question"])
    budget = case.get("budget")
    kwargs = {} if budget is None else {"budget": budget}
    decision = decide_question(game, question, **kwargs)

    actual = {"status": decision.status, "index": decision.index}
    if decision.complete_list:
        actual["complete_list"] = decision.complete_list

    expected = case["expected"]
    mismatches = [field for field, value in expected.items() if actual.get(field) != value]
    return {
        "id": case["id"],
        "mechanism": case["mechanism"],
        "expected": expected,
        "actual": actual,
        "match": not mismatches,
        "mismatches": mismatches,
        "verified": decision.verified,
        "detail": decision.detail,
    }


def run_all(cases: list[dict]) -> list[dict]:
    return [evaluate(case) for case in cases]


def _report(results: list[dict]) -> bool:
    by_mechanism: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for result in results:
        bucket = by_mechanism[result["mechanism"]]
        bucket[1] += 1
        bucket[0] += int(result["match"])
    hits = sum(1 for result in results if result["match"])
    print()
    print(f"gate: {hits}/{len(results)} matched")
    for name in sorted(by_mechanism):
        hit, total = by_mechanism[name]
        print(f"  {name:26} {hit}/{total}")
    statuses = Counter(result["actual"]["status"] for result in results)
    print(f"  actual statuses: {dict(statuses.most_common())}")
    failures = [result for result in results if not result["match"]]
    if failures:
        print(f"  mismatches ({len(failures)}):")
        for result in failures:
            print(
                f"    {result['id']:32} want {result['expected']} got {result['actual']} "
                f"[{result['mismatches']}] verified={result['verified']} {result['detail']}"
            )
    return not failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the L3 synthetic gate.")
    parser.add_argument("--sample", default=str(SAMPLE))
    parser.add_argument("--ids", default="", help="Comma-separated case ids (default: all).")
    parser.add_argument("--limit", type=int, default=0, help="Run at most N cases.")
    args = parser.parse_args(argv)

    wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
    cases = [c for c in load_sample(Path(args.sample)) if not wanted or c["id"] in wanted]
    if args.limit:
        cases = cases[: args.limit]

    results = run_all(cases)
    for result in results:
        flag = "OK " if result["match"] else "ERR"
        print(
            f"[{flag}] {result['id']:32} {result['mechanism']:16} "
            f"{result['actual']['status']:12} index={result['actual']['index']}"
        )
    return 0 if _report(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
