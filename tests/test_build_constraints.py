"""L1 builder plumbing: disjointness constraints and the world assumption."""

from __future__ import annotations

from ankyra.build.enrich import enrich_theory
from ankyra.build.pipeline import build_query, build_theory
from ankyra.build.unroll import unroll_problem_structure, unroll_query_structure
from ankyra.core.models import Query
from ankyra.core.schemas import ProblemStructure, QuestionStructure, StructDisjoint
from ankyra.engine.state import initial_state


def test_disjoint_statement_compiles_to_a_constraint():
    structure = ProblemStructure.model_validate(
        {
            "source_text": "No real number is imaginary.",
            "disjoint": [
                {
                    "left": {"predicate": "is_a", "object": "real_number"},
                    "right": {"predicate": "is_a", "object": "imaginary"},
                    "quote": "No real number is imaginary",
                }
            ],
        }
    )
    theory = unroll_problem_structure(structure)
    assert len(theory.constraints) == 1
    constraint = theory.constraints[0]
    assert constraint.kind == "disjoint"
    assert (constraint.left, constraint.right) == ("real_number", "imaginary")


def test_disjoint_side_accepts_a_bare_class_string():
    constraint = StructDisjoint.model_validate({"left": "real_number", "right": "imaginary"})
    assert (constraint.left, constraint.right) == ("real_number", "imaginary")


def test_disjoint_side_accepts_an_atom_dict():
    constraint = StructDisjoint.model_validate(
        {"left": {"predicate": "is_a", "object": "real_number"}, "right": "imaginary"}
    )
    assert constraint.left == "real_number"


def test_enrich_preserves_constraints_without_source():
    structure = ProblemStructure.model_validate(
        {"disjoint": [{"left": "real_number", "right": "imaginary"}]}
    )
    theory = build_theory(structure)
    assert len(theory.constraints) == 1


def test_enrich_dedupes_symmetric_constraints():
    theory = enrich_theory(
        unroll_problem_structure(
            ProblemStructure.model_validate(
                {
                    "disjoint": [
                        {"left": "real_number", "right": "imaginary"},
                        {"left": "imaginary", "right": "real_number"},
                    ]
                }
            )
        )
    )
    assert len(theory.constraints) == 1


def test_query_world_assumption_defaults_open():
    query = unroll_query_structure(
        QuestionStructure.model_validate({"ask": {"predicate": "p", "subject": "a"}})
    )
    assert query.world_assumption == "open"


def test_build_query_honors_a_declared_world_assumption():
    structure = QuestionStructure.model_validate(
        {"ask": {"predicate": "p", "subject": "a"}}
    )
    assert build_query(structure, world_assumption="closed").world_assumption == "closed"


def test_world_assumption_is_not_part_of_the_llm_schema():
    assert "world_assumption" not in QuestionStructure.model_fields
    assert "world_assumption" not in ProblemStructure.model_fields


def test_query_carries_world_assumption_through_the_engine_models():
    query = Query(target=None, world_assumption="closed")
    assert query.world_assumption == "closed"


def test_initial_state_carries_world_assumption():
    state = initial_state(world_assumption="closed")
    assert state["world_assumption"] == "closed"


def test_default_world_assumption_follows_config():
    from ankyra.build.pipeline import default_world_assumption
    from ankyra.config.settings import settings

    previous = settings.get("NEGATION_MODE", "open")
    try:
        settings.set("NEGATION_MODE", "closed")
        assert default_world_assumption() == "closed"
        settings.set("NEGATION_MODE", "open")
        assert default_world_assumption() == "open"
    finally:
        settings.set("NEGATION_MODE", previous)


def test_disjoint_structure_end_to_end_refutes():
    from ankyra.engine.verify import verify

    structure = ProblemStructure.model_validate(
        {
            "source_text": "No real number is imaginary. A is a real number.",
            "facts": [
                {"predicate": "is_a", "subject": "a", "object": "real_number", "quote": "A is a real number"}
            ],
            "disjoint": [
                {
                    "left": "real_number",
                    "right": "imaginary",
                    "quote": "No real number is imaginary",
                }
            ],
        }
    )
    theory = build_theory(structure)
    query = build_query(
        QuestionStructure.model_validate(
            {"ask": {"predicate": "is_a", "subject": "a", "object": "imaginary"}}
        )
    )
    assert verify(theory, query).status == "refuted"
