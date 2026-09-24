"""L4 synthetic collection: determinism and the gate itself (``docs/l4_plan.md`` §13.1)."""

from __future__ import annotations

import json

from evals import build_l4_synthetic
from evals.l4_synthetic import SAMPLE, evaluate, load_sample, run_all

_EXPR_OPS = {"const", "quantity", "neg", "add", "sub", "mul", "div", "max", "min"}


def test_committed_sample_is_deterministic():
    committed = load_sample(SAMPLE)
    rebuilt = json.loads(json.dumps(build_l4_synthetic.cases(), ensure_ascii=False))
    assert rebuilt == committed


def test_all_cases_pass_the_gate():
    results = run_all(load_sample(SAMPLE))
    failures = [result for result in results if not result["match"]]
    assert not failures, failures


def test_collection_covers_every_expression_op_and_outcome():
    cases = load_sample(SAMPLE)
    used = {op for case in cases for op in case["uses"]}
    assert _EXPR_OPS <= used
    statuses = {result["actual"].get("status") for result in run_all(cases)}
    assert {"determined", "underdetermined", "inconsistent", "out_of_fragment", "insufficient"} <= statuses
    assert any(not case["expected"].get("status") for case in cases)  # build-error controls


def test_collection_has_negative_controls():
    results = {result["id"]: result for result in run_all(load_sample(SAMPLE))}
    # A free target (one equation, two unknowns) is never answered.
    assert results["linear-underdetermined"]["actual"]["status"] == "underdetermined"
    assert results["linear-underdetermined-free-sibling"]["actual"]["status"] == "underdetermined"
    # A contradictory pair is reported as inconsistent, never a value.
    assert results["linear-inconsistent"]["actual"]["status"] == "inconsistent"
    # A non-linear equation is refused, never approximated.
    assert results["oof-nonlinear-square"]["actual"]["status"] == "out_of_fragment"
    # An exhausted budget is insufficient, never a guessed value.
    assert results["budget-insufficient"]["actual"]["status"] == "insufficient"
    # Division by zero is a build error, not a value.
    assert "division by zero" in results["err-division-by-zero"]["actual"]["raises"]


def test_evaluate_reports_a_mismatch():
    case = {
        "id": "bogus",
        "mechanism": "test",
        "game": {
            "quantities": [{"id": "x", "unit": None}],
            "equations": [{"lhs": {"op": "quantity", "quantity": "x"}, "rhs": {"op": "const", "value": "7"}}],
            "source_text": "",
        },
        "query": {"target": "x"},
        "expected": {"status": "determined", "value": "8"},
    }
    result = evaluate(case)
    assert not result["match"]
    assert result["mismatches"] == ["value"]
