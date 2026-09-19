"""Live eval harness: run every problem and assert engine invariants.

Expectations from ``problems.jsonl`` are soft metrics reported by ``evals.run``
and deliberately not asserted here.
"""

from __future__ import annotations

import os

import pytest

from evals.evaluators import ExpectationEvaluator, invariant_violations
from evals.run import load_problems, run_one

live = pytest.mark.skipif(
    not os.getenv("ANKYRA_LIVE"),
    reason="set ANKYRA_LIVE=1 to call the LLM",
)

_PROBLEMS = load_problems()
_BUILTIN_PROBLEMS = [problem for problem in _PROBLEMS if problem.get("builtins")]
_PRESUPPOSITION_PROBLEMS = [p for p in _PROBLEMS if p.get("presupposition")]


@pytest.mark.live
@live
@pytest.mark.parametrize("problem", _PROBLEMS, ids=[p["id"] for p in _PROBLEMS])
def test_invariants_hold(problem):
    _trace, result = run_one(problem)
    assert invariant_violations(problem, result) == []


@pytest.mark.live
@live
@pytest.mark.parametrize(
    "problem", _BUILTIN_PROBLEMS, ids=[p["id"] for p in _BUILTIN_PROBLEMS]
)
def test_builtin_expectations_are_met(problem):
    """The numeric-threshold case must really reach its expected verdict, not just
    satisfy the engine invariants: the point of the case is that ``gte`` fires."""
    _trace, result = run_one(problem)
    score = ExpectationEvaluator().evaluate(problem, result, {})
    assert score.passed, score.notes


@pytest.mark.live
@live
@pytest.mark.parametrize(
    "problem", _PRESUPPOSITION_PROBLEMS, ids=[p["id"] for p in _PRESUPPOSITION_PROBLEMS]
)
def test_presupposition_expectations_are_met(problem):
    """Explicit presuppositions (RU/EN) become question conditions; a comma
    declarative is read as a descriptive fact. The point is the honest status."""
    _trace, result = run_one(problem)
    score = ExpectationEvaluator().evaluate(problem, result, {})
    assert score.passed, score.notes
