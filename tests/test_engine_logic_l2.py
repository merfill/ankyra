"""Tests for the L2 integration: verify/answer/explain behind ANKYRA_LOGIC."""

from __future__ import annotations

from ankyra.config.settings import setting_overrides
from ankyra.core.models import Constraint, Existential, Morphism, Object, Query, Rule, Theory
from ankyra.engine.answer import build_answer
from ankyra.engine.explain import build_explanation
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.verify import verify


def _m(predicate, subject=None, obj=None, *, neg=False):
    return Morphism(predicate=predicate, subject=subject, object=obj, negated=neg)


def _rule(conditions, consequence, alternatives=()):
    return Rule(conditions=list(conditions), consequence=consequence, alternatives=list(alternatives))


def _case_split_theory() -> Theory:
    return Theory(
        objects=[],
        rules=[
            _rule([], _m("is_a", "rex", "a"), alternatives=[_m("is_a", "rex", "b")]),
            _rule([_m("is_a", "?x", "a")], _m("is_a", "?x", "c")),
            _rule([_m("is_a", "?x", "b")], _m("is_a", "?x", "c")),
        ],
    )


def test_l2_case_split_is_supported():
    query = Query(target=_m("is_a", "rex", "c"))
    with setting_overrides(LOGIC="ground"):
        verdict = verify(_case_split_theory(), query)
    assert verdict.status == "supported"
    assert verdict.shelf == "proven"


def test_l2_contradiction_when_both_polarities_hold():
    theory = Theory(morphisms=[_m("p"), _m("p", neg=True)])
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, Query(target=_m("p")))
    assert verdict.status == "contradiction"


def test_l2_refutes_via_disjointness_constraint():
    theory = Theory(
        morphisms=[_m("is_a", "x", "real")],
        constraints=[Constraint(left="real", right="imaginary")],
    )
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, Query(target=_m("is_a", "x", "imaginary")))
        answer = build_answer(theory, Query(target=_m("is_a", "x", "imaginary")), verdict, HypothesisLedger(), verdict.status)
    assert verdict.status == "refuted"
    assert answer.kind == "no" and answer.strength == "proven"


def test_l2_compound_goals_all_and_any():
    theory = Theory(morphisms=[_m("a"), _m("b")])
    all_query = Query(target=_m("a"), goals=[_m("a"), _m("b")], goal_mode="all")
    any_query = Query(target=_m("a"), goals=[_m("a"), _m("missing")], goal_mode="any")
    with setting_overrides(LOGIC="ground"):
        assert verify(theory, all_query).status == "supported"
        assert verify(theory, any_query).status == "supported"
    partial = Theory(morphisms=[_m("a")])
    with setting_overrides(LOGIC="ground"):
        assert verify(partial, Query(target=_m("a"), goals=[_m("a"), _m("b")], goal_mode="all")).status == "insufficient"


def test_l2_shared_witness_supported_with_binding():
    theory = Theory(morphisms=[_m("is_a", "rex", "p"), _m("is_a", "rex", "q")])
    query = Query(
        target=_m("is_a", "?x", "p"),
        goals=[_m("is_a", "?x", "p"), _m("is_a", "?x", "q")],
        goal_mode="all",
        answer_type="open",
    )
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
        answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    assert verdict.status == "supported"
    assert verdict.bindings["?x"] == "rex"
    assert answer.kind == "binding"


def test_l2_shared_witness_rejects_independent_witnesses():
    theory = Theory(morphisms=[_m("is_a", "a", "p"), _m("is_a", "b", "q")])
    query = Query(
        target=_m("is_a", "?x", "p"),
        goals=[_m("is_a", "?x", "p"), _m("is_a", "?x", "q")],
        goal_mode="all",
        answer_type="open",
    )
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
    assert verdict.status == "insufficient"


def test_l2_shared_witness_explanation_merges_both_conjunct_proofs():
    theory = Theory(morphisms=[_m("is_a", "rex", "p"), _m("is_a", "rex", "q")])
    query = Query(
        target=_m("is_a", "?x", "p"),
        goals=[_m("is_a", "?x", "p"), _m("is_a", "?x", "q")],
        goal_mode="all",
        answer_type="open",
    )
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
        explanation = build_explanation(theory, query, verdict, HypothesisLedger())
    assert len(explanation.steps) == 6
    assert all(
        premise < step.index
        for step in explanation.steps
        for premise in step.premises
    )
    statements = {step.statement for step in explanation.steps}
    assert {"is_a(rex,p)", "NOT is_a(rex,p)", "is_a(rex,q)", "NOT is_a(rex,q)"} <= statements


def test_l2_shared_witness_refutes_a_universal_negative():
    theory = Theory(
        morphisms=[_m("is_a", "a", "p"), _m("is_a", "b", "p")],
        rules=[_rule([_m("is_a", "?x", "p")], _m("is_a", "?x", "q", neg=True))],
    )
    query = Query(
        target=_m("is_a", "?x", "p"),
        goals=[_m("is_a", "?x", "p"), _m("is_a", "?x", "q")],
        goal_mode="all",
    )
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
        answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    assert verdict.status == "refuted"
    assert answer.kind == "no"


def _forall_ab_query() -> Query:
    return Query(
        target=_m("is_a", "?x", "a", neg=True),
        goals=[_m("is_a", "?x", "a", neg=True), _m("is_a", "?x", "b")],
        goal_mode="forall",
    )


def test_l2_universal_goal_supported_by_a_fresh_constant():
    theory = Theory(
        rules=[
            _rule([_m("is_a", "?x", "a")], _m("is_a", "?x", "b")),
            _rule([_m("is_a", "?x", "b")], _m("is_a", "?x", "c")),
        ]
    )
    query = Query(
        target=_m("is_a", "?x", "a", neg=True),
        goals=[_m("is_a", "?x", "a", neg=True), _m("is_a", "?x", "c")],
        goal_mode="forall",
    )
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
        answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
        explanation = build_explanation(theory, query, verdict, HypothesisLedger())
    assert verdict.status == "supported"
    assert answer.kind == "yes" and answer.strength == "proven"
    assert explanation.steps and explanation.goal.startswith("∀")


def test_l2_universal_goal_is_not_proved_by_a_named_witness():
    # Soundness control: A(rex) and B(rex) do not prove forall x (A(x) -> B(x)),
    # which the named-pool enumeration would wrongly accept.
    theory = Theory(
        objects=[Object(id="rex")],
        morphisms=[_m("is_a", "rex", "a"), _m("is_a", "rex", "b")],
    )
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, _forall_ab_query())
    assert verdict.status == "insufficient"


def test_l2_universal_goal_refuted_by_a_named_witness():
    theory = Theory(
        objects=[Object(id="rex")],
        morphisms=[_m("is_a", "rex", "a"), _m("is_a", "rex", "b", neg=True)],
    )
    query = _forall_ab_query()
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
        answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    assert verdict.status == "refuted"
    assert answer.kind == "no" and answer.strength == "proven"


def test_l2_negated_existential_is_refuted():
    theory = Theory(objects=[Object(id="rex")], morphisms=[_m("is_a", "rex", "p")])
    query = Query(
        target=_m("is_a", "?x", "p", neg=True),
        goals=[_m("is_a", "?x", "p", neg=True)],
        goal_mode="forall",
    )
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
    assert verdict.status == "refuted"


def test_l2_universal_goal_budget_is_insufficient():
    theory = Theory(
        rules=[
            _rule([_m("is_a", "?x", "a")], _m("is_a", "?x", "b")),
            _rule([_m("is_a", "?x", "b")], _m("is_a", "?x", "c")),
        ]
    )
    query = Query(
        target=_m("is_a", "?x", "a", neg=True),
        goals=[_m("is_a", "?x", "a", neg=True), _m("is_a", "?x", "c")],
        goal_mode="forall",
    )
    with setting_overrides(LOGIC="ground", LOGIC_BUDGET=1):
        verdict = verify(theory, query)
    assert verdict.status == "insufficient"
    assert any(gap.startswith("logic_budget:") for gap in verdict.gaps)


def test_l2_universal_goal_is_out_of_fragment_without_logic():
    theory = Theory(rules=[_rule([_m("is_a", "?x", "a")], _m("is_a", "?x", "b"))])
    with setting_overrides(LOGIC="off"):
        verdict = verify(theory, _forall_ab_query())
    assert verdict.status == "out_of_fragment"
    assert "out_of_fragment:compound_goal" in verdict.gaps


def test_l2_budget_is_insufficient_with_a_gap():
    theory = Theory(morphisms=[_m("p")], rules=[_rule([_m("p")], _m("q"))])
    with setting_overrides(LOGIC="ground", LOGIC_BUDGET=1):
        verdict = verify(theory, Query(target=_m("q")))
    assert verdict.status == "insufficient"
    assert any(gap.startswith("logic_budget:") for gap in verdict.gaps)


def test_l2_builtin_is_out_of_fragment():
    theory = Theory(rules=[_rule([_m("gte", "?p", "50")], _m("big", "?p"))])
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, Query(target=_m("big", "x")))
    assert verdict.status == "out_of_fragment"


def test_l2_rejects_mixing_closed_world_naf():
    theory = Theory(
        rules=[_rule([_m("p", "?x"), _m("q", "?x", neg=True)], _m("r", "?x"))],
    )
    query = Query(target=_m("r", "x"), world_assumption="closed")
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
    assert verdict.status == "out_of_fragment"
    assert "out_of_fragment:naf_in_l2" in verdict.gaps


def test_horn_parity_between_off_and_ground():
    theory = Theory(morphisms=[_m("p", "x")], rules=[_rule([_m("p", "?x")], _m("q", "?x"))])
    query = Query(target=_m("q", "x"))
    with setting_overrides(LOGIC="off"):
        horn = verify(theory, query).status
    with setting_overrides(LOGIC="ground"):
        l2 = verify(theory, query).status
    assert horn == l2 == "supported"


def test_l2_explanation_renders_resolution_steps():
    query = Query(target=_m("is_a", "rex", "c"))
    with setting_overrides(LOGIC="ground"):
        verdict = verify(_case_split_theory(), query)
        explanation = build_explanation(_case_split_theory(), query, verdict, HypothesisLedger())
    kinds = {step.kind for step in explanation.steps}
    assert "resolution" in kinds
    assert "rule" in kinds


def test_l2_skolemizes_an_existential_premise():
    theory = Theory(
        existentials=[Existential(variable="?x", atoms=[_m("is_a", "?x", "animal")])],
        rules=[_rule([_m("is_a", "?x", "animal")], _m("has_mind", "?x"))],
    )
    with setting_overrides(LOGIC="ground"):
        assert verify(theory, Query(target=_m("is_a", "sk0", "animal"))).status == "supported"
        assert verify(theory, Query(target=_m("has_mind", "sk0"))).status == "supported"


def test_l2_open_goal_returns_a_witness_binding():
    theory = Theory(morphisms=[_m("is_a", "a", "cat"), _m("is_a", "b", "cat")])
    query = Query(target=_m("is_a", "?x", "cat"), answer_type="open")
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
        answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    assert verdict.status == "supported"
    assert verdict.bindings.get("?x") in {"a", "b"}
    assert answer.kind == "binding" and answer.strength == "proven"


def test_l2_open_goal_without_a_witness_is_unknown():
    theory = Theory(morphisms=[_m("is_a", "a", "cat")])
    query = Query(target=_m("is_a", "?x", "plant"), answer_type="open")
    with setting_overrides(LOGIC="ground"):
        assert verify(theory, query).status == "unsupported"


def test_l2_existential_goal_uses_the_skolem_witness():
    theory = Theory(
        existentials=[Existential(variable="?x", atoms=[_m("is_a", "?x", "animal")])],
        rules=[_rule([_m("is_a", "?x", "animal")], _m("is_a", "?x", "mortal"))],
    )
    query = Query(target=_m("is_a", "?x", "mortal"), answer_type="open")
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
    assert verdict.status == "supported"
    assert verdict.bindings.get("?x") == "sk0"
