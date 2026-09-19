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


def test_settle_keeps_an_unused_premise_but_drops_the_goal_echo():
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
    settled = settle_query(query)
    assert settled.conditions == [Morphism(predicate="q", subject="a")]
    assert verify(theory, settled).status == "insufficient"


def test_settle_drops_a_condition_complementary_to_the_target():
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
        conditions=[Morphism(predicate="r", subject="a", negated=True)],
        target=Morphism(predicate="r", subject="a"),
    )
    settled = settle_query(query)
    assert settled.conditions == []
    verdict = verify(theory, settled)
    assert verdict.status == "supported"


def test_phase0_open_question_with_variable_labels_binds_the_unknown():
    theory = Theory(
        morphisms=[Morphism(predicate="has_engine", subject="vehicle_x")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="has_engine", subject="?v")],
                consequence=Morphism(predicate="is_a", subject="?v", object="car"),
            )
        ],
    )
    question = QuestionStructure.model_validate(
        {
            "ask": {
                "predicate": "is_a",
                "subject": "vehicle_x",
                "object": "?c",
                "quote": "what type",
            },
            "variables": {"c": "vehicle type"},
        }
    )
    query = build_query(question)
    assert query.variables == {"c": "vehicle type"}
    verdict = verify(theory, query)
    assert verdict.status == "supported"
    assert verdict.bindings.get("?c") == "car"


def test_settle_query_keeps_unary_atoms_in_the_subject_slot():
    query = Query.model_validate(
        {
            "conditions": [{"predicate": "raining", "object": "ground"}],
            "target": {"predicate": "ground_wet", "object": "ground"},
        }
    )
    settled = settle_query(query)
    assert (settled.target.subject, settled.target.object) == ("ground", None)
    assert len(settled.conditions) == 1
    assert (settled.conditions[0].subject, settled.conditions[0].object) == ("ground", None)


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
    query = build_query(question)
    verdict = verify(theory, query)
    assert verdict.status == "supported"
    assert verdict.shelf == "proven"


def test_build_query_strips_domain_conditions():
    question = QuestionStructure.model_validate(
        {
            "source_text": "given that Fiona is a person, is Fiona young?",
            "presuppositions": [
                {"predicate": "is_a", "subject": "fiona", "object": "person"},
                {"predicate": "nice", "subject": "fiona"},
            ],
            "ask": {"predicate": "young", "subject": "fiona"},
        }
    )
    query = build_query(question, domain=["person"])
    assert [cond.predicate for cond in query.conditions] == ["nice"]
