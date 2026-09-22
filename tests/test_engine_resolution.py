"""Tests for the L2 ground clause IR and the bounded-resolution procedure."""

from __future__ import annotations

from ankyra.core.models import Constraint, Existential, Morphism, Rule, Theory
from ankyra.engine.clause import clausify, literal_of
from ankyra.engine.resolution import prove, refute_conjunction, refute_support


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


def test_head_only_variable_is_grounded_over_individuals():
    # T5: ``p(x) -> q(?y)`` reads ``forall y (p(x) -> q(y))``; grounding ``?y`` over
    # the individual domain entails ``q`` for the only individual (docs/t5_plan.md).
    theory = Theory(
        morphisms=[_m("p", "x")],
        rules=[_rule([_m("p", "x")], _m("q", "?y"))],
    )
    assert prove(theory, _lit("q", "x")).status == "entailed"


def test_unsupported_when_no_individual_can_bind_a_head_only_variable():
    # A head-only variable with no individual to range over keeps the honest refusal.
    theory = Theory(rules=[_rule([_m("p", "?x")], _m("q", "?y"))])
    assert prove(theory, _lit("q", "x")).status == "unsupported"


def test_head_only_grounding_excludes_class_names():
    # T5 soundness: the head-only ``?y`` must not be instantiated at the class name
    # ``prim`` (the object of ``is_a(rex, prim)``), so a goal about ``prim`` is not
    # entailed. Grounding over the full pool would fabricate ``is_a(prim, c)``.
    head_only = _rule([], _m("is_a", "?y", "a"), alternatives=[_m("is_a", "?y", "b")])
    theory = Theory(
        morphisms=[_m("is_a", "rex", "prim")],
        rules=[
            head_only,
            _rule([_m("is_a", "?x", "a")], _m("is_a", "?x", "c")),
            _rule([_m("is_a", "?x", "b")], _m("is_a", "?x", "c")),
        ],
    )
    assert prove(theory, _lit("is_a", "rex", "c")).status == "entailed"
    assert prove(theory, _lit("is_a", "prim", "c")).status == "not_entailed"


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


def test_a_conjunction_can_be_unsatisfiable_without_either_conjunct():
    # ``q → ¬p`` refutes the conjunction ``p ∧ q`` while neither ``¬p`` nor ``¬q``
    # alone is entailed (the shared-witness refutation, docs/t1_plan.md §4.2).
    theory = Theory(rules=[_rule([_m("q")], _m("p", neg=True))])
    clausification = clausify(theory)
    assert prove(theory, _lit("p")).status == "not_entailed"
    assert prove(theory, _lit("q")).status == "not_entailed"
    assert refute_conjunction(clausification, [_lit("p"), _lit("q")]).status == "entailed"


def test_literal_of_matches_the_morphism():
    assert literal_of(_m("is_a", "x", "y")) == ("is_a", "x", "y", False, "neutral")


def test_refute_support_accepts_a_multi_clause_assumption():
    # To refute φ = (A ∨ B) → C assume φ's CNF, {¬A ∨ C} and {¬B ∨ C}. With A, B and
    # ¬C the assumed clauses are jointly unsatisfiable (T4).
    theory = Theory(morphisms=[_m("a", "x"), _m("b", "x"), _m("c", "x", neg=True)])
    clausification = clausify(theory)
    assumed = [
        frozenset({_lit("a", "x", neg=True), _lit("c", "x")}),
        frozenset({_lit("b", "x", neg=True), _lit("c", "x")}),
    ]
    assert refute_support(clausification, assumed).status == "entailed"


def _unit_chain_theory() -> Theory:
    # T6 / FOLIO-0009 shape: a disjunctive head whose body holds, with the other
    # disjuncts negated, so exactly one disjunct is forced.
    return Theory(
        morphisms=[
            _m("is_a", "rex", "w"),
            _m("is_a", "rex", "a", neg=True),
            _m("is_a", "rex", "b", neg=True),
        ],
        rules=[
            _rule(
                [_m("is_a", "?x", "w")],
                _m("is_a", "?x", "a"),
                alternatives=[_m("is_a", "?x", "b"), _m("is_a", "?x", "c")],
            )
        ],
    )


def test_unit_propagation_entails_a_forced_disjunct():
    assert prove(_unit_chain_theory(), _lit("is_a", "rex", "c")).status == "entailed"
    assert prove(_unit_chain_theory(), _lit("is_a", "rex", "c", neg=True)).status == "not_entailed"


def test_unit_propagation_does_not_derive_an_unforced_literal():
    # Soundness control: propagation closes the forced branch, not a missing one.
    assert prove(_unit_chain_theory(), _lit("is_a", "rex", "d")).status == "not_entailed"


def test_unit_propagation_respects_the_budget():
    result = prove(_unit_chain_theory(), _lit("is_a", "rex", "c"), budget=1)
    assert result.status == "budget"
    assert result.proof is None


def test_unit_propagation_records_resolution_nodes():
    result = prove(_unit_chain_theory(), _lit("is_a", "rex", "c"))
    assert result.status == "entailed" and result.proof is not None
    derivation = result.proof.derivation()
    assert derivation[-1] == ()
    derived = [
        result.proof.nodes[key]
        for key in derivation
        if result.proof.nodes[key][0] is not None
    ]
    assert derived
    assert all(pivot is not None for _, _, pivot in derived)


def test_clausify_emits_a_disjunctive_skolem_clause():
    existential = Existential(
        variable="?x",
        atoms=[_m("is_a", "?x", "p")],
        disjunctions=[[_m("is_a", "?x", "q"), _m("is_a", "?x", "r")]],
    )
    result = clausify(Theory(existentials=[existential]))
    keys = {frozenset(clause) for clause in result.clauses}
    assert frozenset({literal_of(_m("is_a", "sk0", "p"))}) in keys
    assert (
        frozenset({literal_of(_m("is_a", "sk0", "q")), literal_of(_m("is_a", "sk0", "r"))})
        in keys
    )
