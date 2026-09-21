"""Run the routing synthetic collection (structural, LLM-free) and report the gate.

Each case is a fully structured theory/query pair with an independently written
expected ``RoutingDecision`` and verdict. The runner sets the per-run flags
(``LOGIC``/``DEFEASIBLE``/``BUILTINS``) in an isolated context, builds the engine
models directly, calls ``analyze_routing`` + ``verify`` + ``build_answer``. No
extraction, no LLM, no provider variance.

Usage:
    uv run python -m evals.routing_synthetic [--sample PATH] [--ids a,b] [--limit N]

Exit code is non-zero when any case mismatches, so it works as a gate.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ankyra.config.settings import setting_overrides
from ankyra.core.models import Query, Theory
from ankyra.engine.answer import build_answer
from ankyra.engine.inference import analyze_routing
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.verify import verify

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "routing_synthetic.jsonl"
_FIELDS = ("fragment", "procedure", "refusal", "status", "kind")


def load_sample(path: Path = SAMPLE) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate(case: dict) -> dict:
    """Run one structured case and compare the decision + verdict to the expectation."""
    theory = Theory.model_validate(case["theory"])
    query = Query.model_validate(case["query"])
    overrides = {
        "LOGIC": case.get("logic", "ground"),
        "DEFEASIBLE": bool(case.get("defeasible", False)),
        "BUILTINS": bool(case.get("builtins", False)),
    }
    with setting_overrides(**overrides):
        decision = analyze_routing(theory, query)
        verdict = verify(theory, query)
        answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    actual = {
        "fragment": sorted(decision.fragment),
        "procedure": decision.procedure,
        "refusal": decision.refusal,
        "status": verdict.status,
        "kind": answer.kind,
    }
    expected = case["expected"]
    mismatches = [field for field in _FIELDS if actual[field] != expected[field]]
    return {
        "id": case["id"],
        "mechanism": case["mechanism"],
        "expected": expected,
        "actual": actual,
        "match": not mismatches,
        "mismatches": mismatches,
        "gaps": list(verdict.gaps),
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
        print(f"  {name:14} {hit}/{total}")
    procedures = Counter(result["actual"]["procedure"] for result in results)
    print(f"  actual procedures: {dict(procedures.most_common())}")
    failures = [result for result in results if not result["match"]]
    if failures:
        print(f"  mismatches ({len(failures)}):")
        for result in failures:
            print(
                f"    {result['id']:32} want {result['expected']} got {result['actual']} "
                f"[{result['mismatches']}]"
            )
    return not failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the routing synthetic gate.")
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
            f"[{flag}] {result['id']:32} {result['mechanism']:12} "
            f"proc={result['actual']['procedure']:7} status={result['actual']['status']:15} "
            f"refusal={result['actual']['refusal']}"
        )
    return 0 if _report(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
