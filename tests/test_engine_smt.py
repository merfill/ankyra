"""Offline tests for the Z3/SMT backend of the L2 clause procedure.

``ankyra.engine.smt.prove`` has the contract of ``ankyra.engine.resolution``, so most
tests here are parity tests: the same theory and goal must reach the same status from
both backends, and differ only in ``proof`` (Z3 builds no resolution DAG). Z3 lives in
the optional ``smt`` extra, so tests that need the solver start with
``pytest.importorskip("z3")``; the backend-selection and refusal tests do not.
"""

from __future__ import annotations

import pytest

from ankyra.config.settings import setting_overrides
from ankyra.core.models import Constraint, Morphism, Query, Rule, Theory
from ankyra.engine import backends, resolution
from ankyra.engine.clause import clausify
from ankyra.engine.smt import prove as smt
from ankyra.engine.verify import verify


def _lit(predicate, subject="", obj="", *, neg=False):
    return (predicate, subject, obj, neg, "neutral")


def _m(predicate, subject=None, obj=None, *, neg=False):
    return Morphism(predicate=predicate, subject=subject, object=obj, negated=neg)


def _rule(conditions, consequence, alternatives=()):
    return Rule(conditions=list(conditions), consequence=consequence, alternatives=list(alternatives))


def _parity(theory, goal, **kwargs):
    """Prove ``goal`` with both backends and assert they agree on the status."""
    expected = resolution.prove(theory, goal, **kwargs)
    actual = smt.prove(theory, goal, **kwargs)
    assert actual.status == expected.status, (actual, expected)
    assert actual.proof is None
    return expected, actual


def _forbid_solver(monkeypatch):
    """Fail loudly if the backend reaches Z3 at all."""

    def _raise():
        raise AssertionError("Z3 must not be loaded for this input")

    monkeypatch.setattr("ankyra.engine.smt.prove.require_z3", _raise)


def test_modus_ponens_parity():
    pytest.importorskip("z3")
    theory = Theory(morphisms=[_m("p")], rules=[_rule([_m("p")], _m("q"))])
    _, entailed = _parity(theory, _lit("q"))
    _, not_entailed = _parity(theory, _lit("q", neg=True))
    assert entailed.status == "entailed"
    assert not_entailed.status == "not_entailed"


def test_a_disjunctive_fact_with_case_split_parity():
    pytest.importorskip("z3")
    theory = Theory(
        rules=[
            _rule([], _m("a"), alternatives=[_m("b")]),
            _rule([_m("a")], _m("c")),
            _rule([_m("b")], _m("c")),
        ]
    )
    _, result = _parity(theory, _lit("c"))
    assert result.status == "entailed"


def test_a_disjunctive_fact_does_not_entail_a_disjunct():
    pytest.importorskip("z3")
    theory = Theory(rules=[_rule([], _m("a"), alternatives=[_m("b")])])
    _, first = _parity(theory, _lit("a"))
    _, second = _parity(theory, _lit("b"))
    assert first.status == second.status == "not_entailed"


def test_contrapositive_and_transitivity_parity():
    pytest.importorskip("z3")
    contrapositive = Theory(
        morphisms=[_m("b", neg=True)],
        rules=[_rule([_m("a")], _m("b"))],
    )
    _, negative = _parity(contrapositive, _lit("a", neg=True))
    assert negative.status == "entailed"

    transitivity = Theory(morphisms=[_m("is_a", "a", "b"), _m("is_a", "b", "c")])
    _, chained = _parity(transitivity, _lit("is_a", "a", "c"))
    assert chained.status == "entailed"


def test_a_disjointness_constraint_parity():
    pytest.importorskip("z3")
    theory = Theory(
        morphisms=[_m("is_a", "x", "real")],
        constraints=[Constraint(left="real", right="imaginary")],
    )
    _, negative = _parity(theory, _lit("is_a", "x", "imaginary", neg=True))
    _, positive = _parity(theory, _lit("is_a", "x", "imaginary"))
    assert negative.status == "entailed"
    assert positive.status == "not_entailed"


def test_a_conjunction_refutation_parity():
    pytest.importorskip("z3")
    theory = Theory(rules=[_rule([_m("q")], _m("p", neg=True))])
    clausification = clausify(theory)
    literals = [_lit("p"), _lit("q")]
    assert smt.prove(theory, _lit("p")).status == "not_entailed"
    assert smt.prove(theory, _lit("q")).status == "not_entailed"
    expected = resolution.refute_conjunction(clausification, literals)
    actual = smt.refute_conjunction(clausification, literals)
    assert actual.status == expected.status == "entailed"


def test_refute_support_accepts_a_multi_clause_assumption():
    pytest.importorskip("z3")
    theory = Theory(morphisms=[_m("a", "x"), _m("b", "x"), _m("c", "x", neg=True)])
    clausification = clausify(theory)
    assumed = [
        frozenset({_lit("a", "x", neg=True), _lit("c", "x")}),
        frozenset({_lit("b", "x", neg=True), _lit("c", "x")}),
    ]
    expected = resolution.refute_support(clausification, assumed)
    actual = smt.refute_support(clausification, assumed)
    assert actual.status == expected.status == "entailed"
    assert actual.proof is None


def test_a_budget_too_small_to_encode_never_loads_the_solver(monkeypatch):
    pytest.importorskip("z3")
    theory = Theory(
        morphisms=[_m("p")],
        rules=[_rule([_m("p")], _m("q")), _rule([_m("q")], _m("r"))],
    )
    _forbid_solver(monkeypatch)
    result = smt.prove(theory, _lit("r"), budget=1)
    assert result.status == "budget"
    assert result.proof is None
    assert result.steps > 1
    assert resolution.prove(theory, _lit("r"), budget=1).status == "budget"


def test_prove_with_assumptions_parity():
    pytest.importorskip("z3")
    theory = Theory(rules=[_rule([_m("p")], _m("q"))])
    goal = _lit("q")
    _, without = _parity(theory, goal)
    assert without.status == "not_entailed"
    _, with_gamma = _parity(theory, goal, assumptions=[_m("p")])
    assert with_gamma.status == "entailed"


def test_unsupported_for_a_builtin_condition(monkeypatch):
    # ``unsupported`` is decided from the clausification alone, before Z3 is loaded;
    # the forbidden solver proves it (and this test also runs without the extra).
    _forbid_solver(monkeypatch)
    theory = Theory(rules=[_rule([_m("gte", "?p", "50")], _m("big", "?p"))])
    result = smt.prove(theory, _lit("big", "x"))
    assert result.status == "unsupported"
    assert result.steps == 0 and result.proof is None
    assert resolution.prove(theory, _lit("big", "x")).status == "unsupported"


def test_smt_records_no_proof_dag_where_resolution_does():
    pytest.importorskip("z3")
    theory = Theory(morphisms=[_m("p")], rules=[_rule([_m("p")], _m("q"))])
    proven = resolution.prove(theory, _lit("q"))
    decided = smt.prove(theory, _lit("q"))
    assert proven.status == decided.status == "entailed"
    assert proven.proof is not None
    assert decided.proof is None
    # ``steps`` counts the added clauses: the theory's clauses plus the negated goal.
    assert decided.steps == len(clausify(theory).clauses) + 1


def test_verify_with_the_smt_backend_agrees_with_resolution():
    pytest.importorskip("z3")
    entailed = Theory(morphisms=[_m("p")], rules=[_rule([_m("p")], _m("q"))])
    refuted = Theory(
        morphisms=[_m("is_a", "x", "real")],
        constraints=[Constraint(left="real", right="imaginary")],
    )
    cases = [
        (entailed, Query(target=_m("q")), "supported"),
        (refuted, Query(target=_m("is_a", "x", "imaginary")), "refuted"),
    ]
    for theory, query, expected in cases:
        with setting_overrides(LOGIC="l2", LOGIC_BUDGET=10):
            baseline = verify(theory, query)
        with setting_overrides(LOGIC="l2", LOGIC_BUDGET=10, L2_BACKEND="smt"):
            assert backends.select_backend().backend == "smt"
            chosen = verify(theory, query)
        assert baseline.status == chosen.status == expected
        assert chosen.shelf == baseline.shelf


def test_an_unknown_backend_value_is_refused_not_decided():
    theory = Theory(morphisms=[_m("p")])
    clausification = clausify(theory)
    with setting_overrides(LOGIC="l2", L2_BACKEND="nonsense"):
        decision = backends.select_backend()
        refused = backends.refute(clausification, _lit("p"))
        verdict = verify(theory, Query(target=_m("p")))
    assert decision.refusal == backends.L2_BACKEND_UNKNOWN
    assert not decision.compatible
    assert refused.status == "unsupported" and refused.steps == 0
    assert refused.refusal == "out_of_fragment:l2_backend_unknown"
    assert verdict.status == "out_of_fragment"
    assert verdict.gaps == ["out_of_fragment:l2_backend_unknown"]
    assert verdict.shelf == "refused"


def test_a_missing_solver_is_refused_not_raised(monkeypatch):
    # No ``importorskip``: the refusal must hold with and without the smt extra.
    def _missing():
        raise ImportError("The Z3 solver is not installed.")

    monkeypatch.setattr("ankyra.engine.smt.require_z3", _missing)
    theory = Theory(morphisms=[_m("p")])
    clausification = clausify(theory)
    with setting_overrides(LOGIC="l2", L2_BACKEND="smt"):
        refused = backends.refute(clausification, _lit("p"))
        verdict = verify(theory, Query(target=_m("p")))
    assert refused.status == "unsupported" and refused.proof is None
    assert refused.refusal == "out_of_fragment:l2_backend_unavailable"
    assert verdict.status == "out_of_fragment"
    assert verdict.gaps == ["out_of_fragment:l2_backend_unavailable"]
    assert verdict.shelf == "refused"
