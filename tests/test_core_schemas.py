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


def test_struct_rule_coerces_forall_from_dict_and_list():
    from_dict = StructRule.model_validate({"forall": {"?x": "person"}})
    assert from_dict.forall == {"x": "person"}
    from_list = StructRule.model_validate(
        {"forall": [{"variable": "?x", "sort": "person"}]}
    )
    assert from_list.forall == {"x": "person"}
    assert StructRule().forall == {}


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


def test_problem_structure_coerces_domain():
    structure = ProblemStructure.model_validate(
        {"domain": ["person", {"id": "thing"}, "", None]}
    )
    assert structure.domain == ["person", "thing"]


def test_question_structure_allows_null_ask():
    structure = QuestionStructure.model_validate(
        {"presuppositions": [{"predicate": "rain"}]}
    )
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


def test_struct_atom_predication_defaults_to_verb_and_coerces():
    default = StructAtom.model_validate({"predicate": "has_engine", "subject": "x"})
    assert default.predication == "verb"
    copula = StructAtom.model_validate(
        {"predicate": "cold", "subject": "gary", "predication": "Copula"}
    )
    assert copula.predication == "copula"
    junk = StructAtom.model_validate(
        {"predicate": "cold", "subject": "gary", "predication": "is"}
    )
    assert junk.predication == "verb"


def test_struct_atom_relation_kind_inferred_and_coerced():
    assert StructAtom.model_validate({"predicate": "p"}).relation_kind == "action"
    legacy_copula = StructAtom.model_validate(
        {"predicate": "cold", "subject": "gary", "predication": "copula"}
    )
    assert legacy_copula.relation_kind == "ascription"
    explicit = StructAtom.model_validate(
        {"predicate": "has_engine", "subject": "x", "relation_kind": "Has"}
    )
    assert explicit.relation_kind == "possession"
    # possession wins over a stray legacy copula hint
    possession = StructAtom.model_validate(
        {"predicate": "has_engine", "subject": "x", "predication": "copula", "relation_kind": "possession"}
    )
    assert possession.relation_kind == "possession"


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
