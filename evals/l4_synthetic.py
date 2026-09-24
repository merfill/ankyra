"""Run the L4 synthetic collection (structural, LLM-free) and report the gate.

Each case is a fully structured numeric game/query with an independently written
expected decision. The runner builds the engine models directly, calls ``solve`` (with
an optional per-case budget override) and compares the outcome; no extraction, no LLM,
no provider variance.

Usage:
    uv run python -m evals.l4_synthetic [--sample PATH] [--ids a,b] [--limit N]

Exit code is non-zero when any case mismatches, so it works as a gate.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ankyra.engine.numeric import NumericError, NumericGame, NumericQuery, solve

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "l4_synthetic.jsonl"


def load_sample(path: Path = SAMPLE) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate(case: dict) -> dict:
    """Run one structured case and compare the decision to the expectation."""
    game = NumericGame.model_validate(case["game"])
    query = NumericQuery.model_validate(case["query"])
    budget = case.get("budget")
    kwargs = {} if budget is None else {"budget": budget}

    expected = case["expected"]
    decision = None
    try:
        decision = solve(game, query, **kwargs)
    except NumericError as exc:
        actual = {"raises": str(exc)}
        match = "raises" in expected and expected["raises"] in str(exc)
        mismatches = [] if match else ["raises"]
    else:
        actual = {"status": decision.status}
        if decision.value is not None:
            actual["value"] = str(decision.value)
        mismatches = [field for field, value in expected.items() if actual.get(field) != value]
        match = not mismatches

    return {
        "id": case["id"],
        "mechanism": case["mechanism"],
        "expected": expected,
        "actual": actual,
        "match": match,
        "mismatches": mismatches,
        "detail": decision.detail if decision is not None else None,
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
    statuses = Counter(result["actual"].get("status", "raises") for result in results)
    print(f"  actual statuses: {dict(statuses.most_common())}")
    failures = [result for result in results if not result["match"]]
    if failures:
        print(f"  mismatches ({len(failures)}):")
        for result in failures:
            print(
                f"    {result['id']:32} want {result['expected']} got {result['actual']} "
                f"[{result['mismatches']}] {result['detail'] or ''}"
            )
    return not failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the L4 synthetic gate.")
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
        shown = result["actual"].get("status", result["actual"].get("raises"))
        print(f"[{flag}] {result['id']:32} {result['mechanism']:16} {shown}")
    return 0 if _report(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
