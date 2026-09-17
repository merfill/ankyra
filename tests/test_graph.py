"""Tests for the LangGraph orchestration (stages injected, no LLM)."""

from __future__ import annotations

import os

import pytest

from ankyra.core.models import Morphism, Rule
from ankyra.core.schemas import ProblemStructure, QuestionStructure
from ankyra.engine.nodes import GraphDeps
from ankyra.engine.proposal import ProposalDraft
from ankyra.engine.state import initial_state
from ankyra.graph.build import build_graph

live = pytest.mark.skipif(
    not os.getenv("ANKYRA_LIVE"),
    reason="set ANKYRA_LIVE=1 to call the LLM",
)


def _rain_structure():
    return ProblemStructure.model_validate(
        {
            "source_text": "It is raining. If it is raining, the ground is wet.",
            "objects": ["ground"],
            "facts": [{"predicate": "raining", "quote": "it is raining"}],
            "rules": [
                {
                    "antecedent": [{"predicate": "raining", "quote": "if it is raining"}],
                    "consequent": {
                        "predicate": "is_wet",
                        "object": "ground",
                        "quote": "the ground is wet",
                    },
                    "quote": "if it is raining, the ground is wet",
                }
            ],
        }
    )


def _rain_question():
    return QuestionStructure.model_validate(
        {"ask": {"predicate": "is_wet", "object": "ground", "quote": "ground wet"}}
    )


def _vehicle_structure():
    return ProblemStructure.model_validate(
        {
            "source_text": "X has an engine, four wheels, 150 horsepower and four doors.",
            "objects": ["x"],
            "facts": [
                {"predicate": "has_engine", "subject": "x"},
                {"predicate": "wheel_count", "subject": "x", "object": "4"},
                {"predicate": "power", "subject": "x", "object": "150"},
                {"predicate": "door_count", "subject": "x", "object": "4"},
            ],
        }
    )


def _vehicle_question():
    return QuestionStructure.model_validate(
        {
            "ask": {"predicate": "is_a", "subject": "x", "object": "?c"},
            "variables": {"?c": "?c"},
        }
    )


def _deps(structure, question, propose):
    return GraphDeps(
        extract_problem=lambda _text: structure,
        extract_question=lambda _q, _theory, _source: question,
        propose=propose,
    )


def _no_proposal(_ctx):
    raise AssertionError("no proposal expected")


def test_graph_example_a_is_proven():
    deps = _deps(_rain_structure(), _rain_question(), _no_proposal)
    final = build_graph(deps).invoke(initial_state(problem_text="rain", max_waves=5))
    assert final["status"] == "supported"
    assert final["answer"].strength == "proven"
    assert final["history"] == []


def test_graph_example_b_is_proven_under_a_hypothesis():
    class_rule = Rule(
        conditions=[
            Morphism(predicate="has_engine", subject="?x"),
            Morphism(predicate="wheel_count", subject="?x", object="4"),
            Morphism(predicate="power", subject="?x", object="150"),
            Morphism(predicate="door_count", subject="?x", object="4"),
        ],
        consequence=Morphism(predicate="is_a", subject="?x", object="car"),
    )
    proposals = iter([ProposalDraft(action="propose_rule", rule=class_rule)])
    deps = _deps(_vehicle_structure(), _vehicle_question(), lambda _ctx: next(proposals))
    final = build_graph(deps).invoke(initial_state(problem_text="vehicle", max_waves=5))
    assert final["status"] == "supported"
    assert final["answer"].strength == "proven_under"
    assert final["answer"].hypotheses_used == ["H1"]
    assert len(final["history"]) == 1
    assert final["history"][0].category == "hypothesis"


def test_graph_hypotheses_forbidden_refuses_honestly():
    class_rule = Rule(
        conditions=[Morphism(predicate="has_engine", subject="?x")],
        consequence=Morphism(predicate="is_a", subject="?x", object="car"),
    )
    proposals = iter([ProposalDraft(action="propose_rule", rule=class_rule)])
    deps = _deps(_vehicle_structure(), _vehicle_question(), lambda _ctx: next(proposals))
    final = build_graph(deps).invoke(
        initial_state(problem_text="vehicle", allow_hypotheses=False, max_waves=5)
    )
    assert final["status"] == "unsupported"
    assert final["answer"].strength == "not_proven"
    assert final["history"][0].category == "rejected"
    assert final["history"][0].reason == "hypotheses_forbidden"


@pytest.mark.live
@live
def test_live_graph_full_problem():
    from ankyra.graph.build import run_problem

    result = run_problem(
        "It is raining. If it is raining, the ground is wet. Is the ground wet?",
        max_waves=4,
    )
    assert result.status in {"supported", "unsupported", "budget", "no_progress"}
    assert result.answer is not None
