"""Tests for the L2 ground clause IR and the bounded-resolution procedure."""

from __future__ import annotations

from ankyra.core.models import Constraint, Morphism, Rule, Theory
from ankyra.engine.clause import clausify, literal_of
from ankyra.engine.resolution import prove


def _lit(predicate, subject="", obj="", *, neg=False):
    return (predicate, subject, obj, neg, "neutral")


def _m(predicate, subject=None, obj=None, *, neg=False):
    return Morphism(predicate=predicate, subject=subject, object=obj, negated=neg)


def _rule(conditions, consequence, alternatives=()):
    return Rule(conditions=list(conditions), consequence=consequence, alternatives=list(alternatives))


def test_modus_ponens_is_entailed():
    theory = Theory(
        morphisms=[_m("p")],
        rules=[_rule([_m("p")], _m("q"))],
    )
    assert prove(theory, _lit("q")).status == "entailed"
    assert prove(theory, _lit("q", neg=True)).status == "not_entailed"


def test_a_disjunctive_fact_with_case_split_entails_the_common_consequent():
    theory = Theory(
        rules=[
            _rule([], _m("a"), alternatives=[_m("b")]),
            _rule([_m("a")], _m("c")),
            _rule([_m("b")], _m("c")),
        ]
    )
    assert prove(theory, _lit("c")).status == "entailed"


def test_a_disjunctive_fact_does_not_entail_a_disjunct():
    theory = Theory(rules=[_rule([], _m("a"), alternatives=[_m("b")])])
    assert prove(theory, _lit("a")).status == "not_entailed"
    assert prove(theory, _lit("b")).status == "not_entailed"


def test_contrapositive_is_entailed_by_refutation():
    theory = Theory(
        morphisms=[_m("b", neg=True)],
        rules=[_rule([_m("a")], _m("b"))],
    )
    assert prove(theory, _lit("a", neg=True)).status == "entailed"


def test_is_a_transitivity_is_entailed_from_clauses():
    theory = Theory(morphisms=[_m("is_a", "a", "b"), _m("is_a", "b", "c")])
    assert prove(theory, _lit("is_a", "a", "c")).status == "entailed"


def test_a_disjointness_constraint_entails_the_negative_side():
    theory = Theory(
        morphisms=[_m("is_a", "x", "real")],
        constraints=[Constraint(left="real", right="imaginary")],
    )
    assert prove(theory, _lit("is_a", "x", "imaginary", neg=True)).status == "entailed"
    assert prove(theory, _lit("is_a", "x", "imaginary")).status == "not_entailed"


def test_budget_exhaustion_is_honest_not_entailed():
    theory = Theory(
        morphisms=[_m("p")],
        rules=[_rule([_m("p")], _m("q"))],
    )
    result = prove(theory, _lit("q"), budget=1)
    assert result.status == "budget"
    assert result.proof is None


def test_unsupported_for_a_builtin_condition():
    theory = Theory(rules=[_rule([_m("gte", "?p", "50")], _m("big", "?p"))])
    assert prove(theory, _lit("big", "x")).status == "unsupported"


def test_unsupported_for_an_unsafe_rule():
    theory = Theory(
        morphisms=[_m("p", "x")],
        rules=[_rule([_m("p", "x")], _m("q", "?y"))],
    )
    assert prove(theory, _lit("q", "x")).status == "unsupported"


def test_clausify_marks_the_unsupported_constructs():
    theory = Theory(rules=[_rule([_m("gte", "?p", "50")], _m("big", "?p"))])
    result = clausify(theory)
    assert result.unsupported == ["builtin:rule:1"]


def test_proof_derivation_is_premises_first():
    theory = Theory(morphisms=[_m("p")], rules=[_rule([_m("p")], _m("q"))])
    result = prove(theory, _lit("q"))
    assert result.status == "entailed" and result.proof is not None
    derivation = result.proof.derivation()
    assert derivation[-1] == ()
    origins = {source for key in derivation for source in result.proof.origins[key]}
    assert "axiom:p()" in origins
    assert "goal" in origins


def test_literal_of_matches_the_morphism():
    assert literal_of(_m("is_a", "x", "y")) == ("is_a", "x", "y", False, "neutral")
