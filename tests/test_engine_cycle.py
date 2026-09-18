"""Tests for the guided reasoning cycle (proposal stage scripted, no LLM)."""

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


def test_example_a_is_proven_without_any_wave():
    theory = Theory(
        objects=[Object(id="ground")],
        morphisms=[Morphism(predicate="raining")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
            )
        ],
    )
    query = Query(target=Morphism(predicate="is_wet", object="ground"))
    result = run_cycle(_never, theory, query)
    assert result.status == "supported"
    assert result.answer.strength == "proven"
    assert result.answer.hypotheses_used == []
    assert result.history == []


def test_example_b_is_proven_under_hypotheses():
    theory = Theory(
        objects=[Object(id="x")],
        morphisms=[
            Morphism(predicate="has_engine", subject="x"),
            Morphism(predicate="wheel_count", subject="x", object="4"),
            Morphism(predicate="power", subject="x", object="150"),
            Morphism(predicate="door_count", subject="x", object="4"),
        ],
        source_text="X has an engine, four wheels, 150 horse power and four doors.",
    )
    query = Query(
        target=Morphism(predicate="is_a", subject="x", object="?c"),
        answer_type="open",
    )
    class_rule = Rule(
        conditions=[
            Morphism(predicate="has_engine", subject="?x"),
            Morphism(predicate="wheel_count", subject="?x", object="4"),
            Morphism(predicate="power", subject="?x", object="150"),
            Morphism(predicate="door_count", subject="?x", object="4"),
        ],
        consequence=Morphism(predicate="is_a", subject="?x", object="car"),
    )
    hierarchy = Rule(
        conditions=[Morphism(predicate="is_a", subject="?x", object="car")],
        consequence=Morphism(predicate="is_a", subject="?x", object="motor_vehicle"),
    )
    proposals = iter(
        [
            ProposalDraft(action="propose_rule", rule=class_rule),
            ProposalDraft(action="propose_rule", rule=hierarchy),
        ]
    )
    result = run_cycle(lambda _ctx: next(proposals), theory, query, max_waves=5)
    assert result.status == "supported"
    assert result.answer.strength == "proven_under"
    assert result.answer.hypotheses_used == ["H1"]
    assert result.answer.value == "?c=car"


def test_example_b_chain_uses_every_hypothesis_needed():
    theory = Theory(
        objects=[Object(id="x")],
        morphisms=[
            Morphism(predicate="has_engine", subject="x"),
            Morphism(predicate="wheel_count", subject="x", object="4"),
            Morphism(predicate="power", subject="x", object="150"),
            Morphism(predicate="door_count", subject="x", object="4"),
        ],
        source_text="X has an engine, four wheels, 150 horse power and four doors.",
    )
    query = Query(target=Morphism(predicate="is_a", subject="x", object="motor_vehicle"))
    class_rule = Rule(
        conditions=[
            Morphism(predicate="has_engine", subject="?x"),
            Morphism(predicate="wheel_count", subject="?x", object="4"),
            Morphism(predicate="power", subject="?x", object="150"),
            Morphism(predicate="door_count", subject="?x", object="4"),
        ],
        consequence=Morphism(predicate="is_a", subject="?x", object="car"),
    )
    hierarchy = Rule(
        conditions=[Morphism(predicate="is_a", subject="?x", object="car")],
        consequence=Morphism(predicate="is_a", subject="?x", object="motor_vehicle"),
    )
    proposals = iter(
        [
            ProposalDraft(action="propose_rule", rule=class_rule),
            ProposalDraft(action="propose_rule", rule=hierarchy),
        ]
    )
    result = run_cycle(lambda _ctx: next(proposals), theory, query, max_waves=5)
    assert result.status == "supported"
    assert result.answer.strength == "proven_under"
    assert result.answer.hypotheses_used == ["H1", "H2"]


def test_hypotheses_forbidden_is_an_honest_refusal():
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
    result = run_cycle(
        lambda _ctx: ProposalDraft(action="propose_rule", rule=rule),
        theory,
        query,
        allow_hypotheses=False,
        max_waves=3,
    )
    assert result.status == "unsupported"
    assert result.answer.strength == "not_proven"
    assert result.hypotheses == []


def test_cited_fact_is_proven_without_hypotheses():
    theory = Theory(
        morphisms=[Morphism(predicate="raining")],
        source_text="It is raining and the ground is wet.",
    )
    query = Query(target=Morphism(predicate="is_wet", object="ground"))

    def cite(_ctx):
        return ProposalDraft(
            action="assert_cited_fact",
            fact=Morphism(predicate="is_wet", object="ground", quote="the ground is wet"),
        )

    result = run_cycle(cite, theory, query, max_waves=3)
    assert result.status == "supported"
    assert result.answer.strength == "proven"
    assert result.answer.hypotheses_used == []


def test_identical_proposals_stop_as_no_progress():
    theory = Theory(morphisms=[Morphism(predicate="p", subject="a")])
    query = Query(target=Morphism(predicate="r", subject="b"))
    unsafe = ProposalDraft(
        action="propose_rule",
        rule=Rule(
            conditions=[Morphism(predicate="p", subject="?x")],
            consequence=Morphism(predicate="r", subject="?y"),
        ),
    )
    result = run_cycle(lambda _ctx: unsafe, theory, query, max_waves=5)
    assert result.status == "no_progress"


def test_cycle_answers_no_for_a_refuted_target():
    theory = Theory(morphisms=[Morphism(predicate="fly", subject="tweety", negated=True)])
    query = Query(target=Morphism(predicate="fly", subject="tweety"))
    result = run_cycle(_never, theory, query)
    assert result.status == "refuted"
    assert result.answer.value == "no"
    assert result.answer.strength == "proven"


def test_repeated_inert_proposals_stop_as_no_progress():
    theory = Theory(morphisms=[Morphism(predicate="p", subject="a")])
    query = Query(target=Morphism(predicate="r", subject="b"))
    unsafe = Rule(
        conditions=[Morphism(predicate="p", subject="?x")],
        consequence=Morphism(predicate="r", subject="?y"),
    )
    counter = {"n": 0}

    def propose(_ctx):
        counter["n"] += 1
        return ProposalDraft(action="propose_rule", narration=f"try{counter['n']}", rule=unsafe)

    result = run_cycle(propose, theory, query, max_waves=5)
    assert result.status == "no_progress"


def test_budget_stops_the_cycle():
    theory = Theory(morphisms=[Morphism(predicate="p")])
    query = Query(target=Morphism(predicate="q"))
    result = run_cycle(_never, theory, query, max_waves=0)
    assert result.status == "budget"


def test_an_unused_premise_is_a_terminal_insufficient():
    theory = Theory(
        morphisms=[Morphism(predicate="p", subject="a")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="p", subject="?x")],
                consequence=Morphism(predicate="r", subject="?x"),
            )
        ],
    )
    query = Query(
        conditions=[Morphism(predicate="q", subject="a")],
        target=Morphism(predicate="r", subject="a"),
    )
    result = run_cycle(_never, theory, query, max_waves=5)
    assert result.status == "insufficient"
    assert result.answer.kind == "unknown"
    assert result.history == []


@pytest.mark.live
@live
def test_live_example_b_full_pipeline_smoke():
    from ankyra.build.extract import extract_problem_structure, extract_question_structure
    from ankyra.build.pipeline import build_query, build_theory
    from ankyra.engine.proposal import propose
    from ankyra.llm.client import create_chat_llm

    problem = (
        "A vehicle X has an engine, four wheels, 150 horsepower and four doors. "
        "What type of vehicle is X?"
    )
    extractor = create_chat_llm(role="extract")
    structure = extract_problem_structure(extractor, text=problem)
    theory = build_theory(structure)
    question = extract_question_structure(
        extractor, question=structure.question, theory=theory, source_text=problem
    )
    query = build_query(question)

    proposer = create_chat_llm(role="answer")
    result = run_cycle(
        lambda ctx: propose(proposer, ctx),
        theory,
        query,
        allow_hypotheses=True,
        max_waves=6,
    )
    assert result.status in {"supported", "unsupported", "budget", "no_progress"}
