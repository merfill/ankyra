"""Tests for the Phase 0 extraction schemas."""

from __future__ import annotations

import json

from ankyra.core.schemas import (
    ProblemStructure,
    QuestionStructure,
    Slot,
    StructAtom,
    StructObject,
    StructRule,
    llm_json_schema,
)


def test_slot_accepts_a_bare_string():
    slot = Slot.model_validate("ground")
    assert slot.id == "ground"
    assert slot.set == [] and slot.variants == [] and slot.exclude == []


def test_slot_keeps_sets_variants_and_exclusions():
    slot = Slot.model_validate({"set": ["a", "b"], "exclude": ["c"], "variants": []})
    assert slot.set == ["a", "b"]
    assert slot.exclude == ["c"]


def test_struct_atom_coerces_bare_slot_and_modality():
    atom = StructAtom.model_validate(
        {"predicate": "transfer", "subject": "a", "object": "b", "modality": "Prohibited"}
    )
    assert atom.subject.id == "a"
    assert atom.object.id == "b"
    assert atom.modality == "forbidden"


def test_struct_rule_wraps_antecedent_and_coerces_kind():
    rule = StructRule.model_validate(
        {
            "antecedent": {"set": [{"predicate": "raining"}]},
            "consequent": {"predicate": "is_wet", "object": "ground"},
            "kind": "Exception",
        }
    )
    assert len(rule.antecedent) == 1
    assert rule.antecedent[0].predicate == "raining"
    assert rule.consequent.predicate == "is_wet"
    assert rule.kind == "exception"


def test_problem_structure_coerces_objects_and_references():
    structure = ProblemStructure.model_validate(
        {
            "objects": ["ground", {"name": "sky", "label": "the sky"}],
            "references": ["see above", {"quote": "as stated"}],
        }
    )
    assert [o.id for o in structure.objects] == ["ground", "sky"]
    assert structure.objects[1].label == "the sky"
    assert structure.references == ["see above", "as stated"]


def test_question_structure_allows_null_ask():
    structure = QuestionStructure.model_validate({"facts": [{"predicate": "rain"}]})
    assert structure.ask is None

    asked = QuestionStructure.model_validate({"ask": {"predicate": "is_wet", "subject": "?x"}})
    assert asked.ask is not None
    assert asked.ask.subject.id == "?x"


def test_problem_structure_source_text_defaults_empty_for_llm_output():
    structure = ProblemStructure.model_validate(
        {"objects": [StructObject(id="ground")], "facts": [{"predicate": "raining"}]}
    )
    assert structure.source_text == ""
    assert structure.question == ""
    assert structure.facts[0].predicate == "raining"


def test_struct_atom_tolerates_missing_arguments():
    atom = StructAtom.model_validate({"predicate": "raining", "subject": None, "object": None})
    assert atom.subject.id is None and atom.object.id is None


def test_llm_json_schema_is_valid_json_with_field_descriptions():
    schema = json.loads(llm_json_schema(StructAtom))
    assert schema["title"] == "StructAtom"
    assert "predicate" in schema["properties"]
    assert "modality" in schema["properties"]


def test_model_dump_is_deterministic():
    structure = ProblemStructure.model_validate(
        {"objects": ["ground"], "facts": [{"predicate": "raining"}]}
    )
    assert structure.model_dump() == structure.model_dump()
