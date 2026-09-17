"""Live eval harness: run every problem and assert engine invariants.

Expectations from ``problems.jsonl`` are soft metrics reported by ``evals.run``
and deliberately not asserted here.
"""

from __future__ import annotations

import os

import pytest

from evals.evaluators import invariant_violations
from evals.run import load_problems, run_one

live = pytest.mark.skipif(
    not os.getenv("ANKYRA_LIVE"),
    reason="set ANKYRA_LIVE=1 to call the LLM",
)

_PROBLEMS = load_problems()


@pytest.mark.live
@live
@pytest.mark.parametrize("problem", _PROBLEMS, ids=[p["id"] for p in _PROBLEMS])
def test_invariants_hold(problem):
    _trace, result = run_one(problem)
    assert invariant_violations(problem, result) == []
