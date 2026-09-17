"""Tests for the deterministic structure expander."""

from __future__ import annotations

from ankyra.build.unroll import (
    atom_to_morphisms,
    unroll_problem_structure,
    unroll_query_structure,
)
from ankyra.core.schemas import ProblemStructure, QuestionStructure, StructAtom


def test_unary_atom_maps_to_a_nullary_morphism():
    morphisms = atom_to_morphisms(StructAtom.model_validate({"predicate": "raining"}))
    assert len(morphisms) == 1
    assert morphisms[0].subject is None and morphisms[0].object is None


def test_and_set_expands_to_one_morphism_per_member():
    atom = StructAtom.model_validate(
        {"predicate": "inspect", "subject": "police", "object": {"set": ["bag", "car"]}}
    )
    morphisms = atom_to_morphisms(atom)
    assert {m.object for m in morphisms} == {"bag", "car"}
    assert all(m.subject == "police" for m in morphisms)


def test_variants_stay_individual_and_exclude_subtracts():
    variants = StructAtom.model_validate(
        {"predicate": "pay", "subject": {"variants": ["cash", "card"]}}
    )
    assert {m.subject for m in atom_to_morphisms(variants)} == {"cash", "card"}

    excluded = StructAtom.model_validate(
        {"predicate": "visit", "subject": {"set": ["a", "b", "c"], "exclude": ["b"]}}
    )
    assert {m.subject for m in atom_to_morphisms(excluded)} == {"a", "c"}


def test_modality_is_a_field_and_prefix_is_opt_in():
    atom = StructAtom.model_validate(
        {"predicate": "pay", "subject": "alice", "modality": "obligation"}
    )
    default = atom_to_morphisms(atom)[0]
    assert default.predicate == "pay"
    assert default.modality == "obligation"

    lowered = atom_to_morphisms(atom, deontic_prefixes=True)[0]
    assert lowered.predicate == "must_pay"
    assert lowered.modality == "obligation"


def test_exception_flips_the_consequence_polarity():
    structure = ProblemStructure.model_validate(
        {
            "source_text": "All birds fly except penguins.",
            "objects": ["bird", "penguin"],
            "facts": [{"predicate": "is_a", "subject": "penguin", "object": "bird"}],
            "rules": [
                {
                    "antecedent": [{"predicate": "is_a", "subject": "?x", "object": "penguin"}],
                    "consequent": {"predicate": "fly", "subject": "?x"},
                    "kind": "exception",
                    "quote": "except penguins",
                }
            ],
        }
    )
    rule = unroll_problem_structure(structure).rules[0]
    assert rule.kind == "exception"
    assert rule.consequence.negated is True


def test_problem_structure_source_text_is_carried():
    structure = ProblemStructure.model_validate(
        {"source_text": "It is raining.", "facts": [{"predicate": "raining"}]}
    )
    assert unroll_problem_structure(structure).source_text == "It is raining."


def test_query_unroll_maps_facts_target_and_variables():
    structure = QuestionStructure.model_validate(
        {
            "facts": [{"predicate": "has_engine", "subject": "x"}],
            "ask": {"predicate": "is_a", "subject": "x", "object": "?c"},
            "variables": {"?c": "?c"},
        }
    )
    query = unroll_query_structure(structure)
    assert [c.predicate for c in query.conditions] == ["has_engine"]
    assert query.target is not None and query.target.predicate == "is_a"
    assert query.answer_type == "open"
    assert query.variables == {"c": "?c"}


def test_query_without_ask_is_an_instruction():
    query = unroll_query_structure(
        QuestionStructure.model_validate({"facts": [{"predicate": "a"}]})
    )
    assert query.target is None
    assert query.answer_type == "instruction"
