"""Tests for query assembly, settling, and the Phase 0 end-to-end path."""

from __future__ import annotations

from ankyra.build.pipeline import build_query, build_theory
from ankyra.build.query import derive_answer_type, settle_query
from ankyra.core.models import Morphism, Query, Rule, Theory
from ankyra.core.schemas import ProblemStructure, QuestionStructure
from ankyra.engine.verify import verify


def test_derive_answer_type():
    assert derive_answer_type(None, {}) == "instruction"
    assert derive_answer_type(Morphism(predicate="is_a", subject="x", object="?c"), {}) == "open"
    assert derive_answer_type(Morphism(predicate="is_a", subject="x", object="car"), {}) == "yes_no"
    assert derive_answer_type(Morphism(predicate="is_a", subject="x", object="car"), {"c": "?c"}) == "open"


def test_settle_drops_the_goal_echo_and_unused_premises():
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
        conditions=[
            Morphism(predicate="r", subject="a"),
            Morphism(predicate="q", subject="a"),
        ],
        target=Morphism(predicate="r", subject="a"),
    )
    settled = settle_query(theory, query)
    assert settled.conditions == []


def test_phase0_rain_end_to_end_is_proven():
    structure = ProblemStructure.model_validate(
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
    theory = build_theory(structure)
    question = QuestionStructure.model_validate(
        {
            "source_text": "is the ground wet?",
            "ask": {"predicate": "is_wet", "object": "ground", "quote": "ground wet"},
        }
    )
    query = build_query(theory, question)
    verdict = verify(theory, query)
    assert verdict.status == "supported"
    assert verdict.shelf == "proven"
