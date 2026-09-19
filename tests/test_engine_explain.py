"""Tests for the mechanical explanation built from proof provenance."""

from __future__ import annotations

import os

import pytest

from ankyra.core.models import Morphism, Object, Query, Rule, Theory
from ankyra.engine.cycle import run_cycle
from ankyra.engine.proposal import ProposalDraft

live = pytest.mark.skipif(
    not os.getenv("ANKYRA_LIVE"),
    reason="set ANKYRA_LIVE=1 to call the LLM",
)


def _never(_ctx):
    raise AssertionError("no proposal expected")


def _assert_topological(explanation):
    for step in explanation.steps:
        assert all(0 <= p < step.index for p in step.premises)


def test_explanation_of_example_a_names_the_rule_and_quote():
    theory = Theory(
        objects=[Object(id="ground")],
        morphisms=[Morphism(predicate="raining", quote="raining")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
                quote="if it is raining, the ground is wet",
            )
        ],
    )
    query = Query(target=Morphism(predicate="is_wet", object="ground"))
    result = run_cycle(_never, theory, query)
    explanation = result.explanation

    assert explanation.goal == "is_wet(ground)"
    _assert_topological(explanation)

    kinds = {step.kind for step in explanation.steps}
    assert kinds == {"axiom", "rule"}

    axiom = next(s for s in explanation.steps if s.kind == "axiom")
    assert axiom.statement == "raining()"
    assert axiom.quote == "raining"

    rule = next(s for s in explanation.steps if s.kind == "rule")
    assert rule.source == "quote"
    assert rule.quote == "if it is raining, the ground is wet"
    assert rule.premises == [axiom.index]


def test_explanation_of_a_hypothesis_rule_carries_its_id():
    theory = Theory(
        objects=[Object(id="x")],
        morphisms=[Morphism(predicate="has_engine", subject="x")],
        source_text="X has an engine.",
    )
    query = Query(target=Morphism(predicate="is_a", subject="x", object="car"))
    rule = Rule(
        conditions=[Morphism(predicate="has_engine", subject="?x")],
        consequence=Morphism(predicate="is_a", subject="?x", object="car"),
    )
    proposals = iter([ProposalDraft(action="propose_rule", rule=rule)])
    result = run_cycle(lambda _ctx: next(proposals), theory, query, max_waves=3)

    explanation = result.explanation
    assert explanation.hypotheses_used == ["H1"]
    hypothesis_step = next(s for s in explanation.steps if s.hypothesis == "H1")
    assert hypothesis_step.kind == "rule"
    assert hypothesis_step.source == "hypothesis:H1"
    _assert_topological(explanation)


def test_a_question_condition_used_in_the_proof_is_source_presupposition():
    theory = Theory(
        rules=[
            Rule(
                conditions=[
                    Morphism(predicate="is_a", subject="?x", object="philosopher")
                ],
                consequence=Morphism(predicate="is_a", subject="?x", object="mortal"),
            )
        ]
    )
    query = Query(
        conditions=[Morphism(predicate="is_a", subject="socrates", object="philosopher")],
        target=Morphism(predicate="is_a", subject="socrates", object="mortal"),
    )
    result = run_cycle(_never, theory, query)

    assert result.verdict.status == "supported"
    presupposition = next(
        step
        for step in result.explanation.steps
        if step.statement == "is_a(socrates,philosopher)"
    )
    assert presupposition.kind == "assumption"
    assert presupposition.source == "presupposition"
    _assert_topological(result.explanation)


def test_explanation_of_is_a_chain_uses_the_two_edges():
    theory = Theory(
        morphisms=[
            Morphism(predicate="is_a", subject="a", object="b"),
            Morphism(predicate="is_a", subject="b", object="c"),
        ],
    )
    query = Query(target=Morphism(predicate="is_a", subject="a", object="c"))
    result = run_cycle(_never, theory, query)

    explanation = result.explanation
    chain = next(s for s in explanation.steps if s.kind == "is_a")
    assert chain.statement == "is_a(a,c)"
    assert len(chain.premises) == 2
    assert all(explanation.steps[p].kind == "axiom" for p in chain.premises)
    _assert_topological(explanation)


def test_unproven_goal_has_an_empty_explanation():
    theory = Theory(morphisms=[Morphism(predicate="p")])
    query = Query(target=Morphism(predicate="q"))
    result = run_cycle(_never, theory, query, max_waves=0)
    assert result.explanation.steps == []
    assert result.explanation.goal is None


def test_refuted_target_explains_the_negative_branch():
    theory = Theory(morphisms=[Morphism(predicate="fly", subject="tweety", negated=True)])
    query = Query(target=Morphism(predicate="fly", subject="tweety"))
    result = run_cycle(_never, theory, query)

    assert result.verdict.status == "refuted"
    explanation = result.explanation
    assert explanation.goal == "NOT fly(tweety)"
    assert [step.statement for step in explanation.steps] == ["NOT fly(tweety)"]
    assert result.answer.value == "no"
    _assert_topological(explanation)


def test_contradiction_exposes_both_branches():
    theory = Theory(
        morphisms=[
            Morphism(predicate="raining"),
            Morphism(predicate="raining", negated=True),
        ],
    )
    query = Query(target=Morphism(predicate="raining"))
    result = run_cycle(_never, theory, query)

    assert result.verdict.status == "contradiction"
    conflict = result.explanation.conflict
    assert conflict is not None
    assert conflict.kind == "strict"
    assert conflict.defeated == "none"
    assert [step.statement for step in conflict.supporting] == ["raining()"]
    assert [step.statement for step in conflict.attacking] == ["NOT raining()"]
    assert result.answer.strength == "not_proven"
    _assert_topological(result.explanation)
    for step in conflict.supporting + conflict.attacking:
        assert all(0 <= p < step.index for p in step.premises)


@pytest.mark.live
@live
def test_live_narration_paraphrases_the_trace():
    from ankyra.engine.narrate import narrate_explanation
    from ankyra.llm.client import create_chat_llm

    theory = Theory(
        objects=[Object(id="ground")],
        morphisms=[Morphism(predicate="raining", quote="raining")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
            )
        ],
    )
    query = Query(target=Morphism(predicate="is_wet", object="ground"))
    result = run_cycle(_never, theory, query)
    narration = narrate_explanation(create_chat_llm(role="answer"), result.explanation)
    assert isinstance(narration, str) and narration.strip()
