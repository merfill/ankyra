"""Tests for the core domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ankyra.core.models import (
    Answer,
    Fact,
    Hypothesis,
    Morphism,
    Object,
    Proposal,
    Query,
    Rule,
    Theory,
    Verdict,
    WaveRecord,
    normalize_modality,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("permit", "permit"),
        ("Permitted", "permit"),
        ("allowed", "permit"),
        ("may", "permit"),
        ("obligation", "obligation"),
        ("mandatory", "obligation"),
        ("required", "obligation"),
        ("must", "obligation"),
        ("forbidden", "forbidden"),
        ("prohibited", "forbidden"),
        ("banned", "forbidden"),
        ("neutral", "neutral"),
        ("", "neutral"),
        (None, "neutral"),
    ],
)
def test_normalize_modality(raw, expected):
    assert normalize_modality(raw) == expected


def test_morphism_modality_is_a_field_not_a_prefix():
    m = Morphism(predicate="transfer", subject="a", object="b", modality="Permitted")
    assert m.modality == "permit"
    assert m.predicate == "transfer"


def test_negation_is_the_same_predicate_with_a_flag():
    pos = Morphism(predicate="is_a", subject="x", object="car")
    neg = Morphism(predicate="is_a", subject="x", object="car", negated=True)
    assert pos.predicate == neg.predicate
    assert pos.negated is False and neg.negated is True


def test_unary_morphism_canonicalizes_to_the_subject_slot():
    from_object = Morphism(predicate="is_wet", object="ground")
    from_subject = Morphism(predicate="is_wet", subject="ground")
    assert from_object.subject == "ground" and from_object.object is None
    assert from_object == from_subject


def test_unary_canonicalization_is_idempotent_under_model_copy():
    morphism = Morphism(predicate="ground_wet", object="ground")
    assert morphism == morphism.model_copy()
    copied = morphism.model_copy().model_copy(update={"negated": True})
    assert (copied.subject, copied.object) == ("ground", None)


def test_binary_morphism_keeps_both_slots():
    m = Morphism(predicate="is_a", subject="poodle", object="dog")
    assert (m.subject, m.object) == ("poodle", "dog")


def test_rule_requires_a_consequence():
    with pytest.raises(ValidationError):
        Rule(conditions=[Morphism(predicate="a")])


@pytest.mark.parametrize("source", ["quote", "hypothesis:H1", "hypothesis: h2 "])
def test_rule_source_accepts_quote_and_hypothesis(source):
    rule = Rule(
        conditions=[Morphism(predicate="a")],
        consequence=Morphism(predicate="b"),
        source=source,
    )
    assert rule.source == source.strip()


def test_rule_source_hypothesis_id():
    rule = Rule(
        conditions=[Morphism(predicate="a")],
        consequence=Morphism(predicate="b"),
        source="hypothesis:H1",
    )
    assert rule.source_hypothesis_id == "H1"
    quoted = Rule(
        conditions=[Morphism(predicate="a")],
        consequence=Morphism(predicate="b"),
    )
    assert quoted.source == "quote"
    assert quoted.source_hypothesis_id is None


def test_rule_source_rejects_unknown_values():
    with pytest.raises(ValidationError):
        Rule(
            conditions=[Morphism(predicate="a")],
            consequence=Morphism(predicate="b"),
            source="bogus",
        )


def test_fact_coerces_missing_argument_and_builds_key_and_label():
    unary = Fact(predicate="raining")
    assert unary.subject == "" and unary.object == ""
    assert unary.key == ("raining", "", "", False, "neutral")
    assert unary.label() == "raining()"

    binary = Fact(predicate="is_a", subject="x", object="car")
    assert binary.key == ("is_a", "x", "car", False, "neutral")
    assert binary.label() == "is_a(x,car)"

    denied = Fact(predicate="is_a", subject="x", object="car", negated=True)
    assert denied.label() == "NOT is_a(x,car)"


def test_fact_modality_is_part_of_atom_identity():
    owed = Fact(predicate="pay", subject="alice", modality="obligation")
    allowed = Fact(predicate="pay", subject="alice", modality="permit")
    assert owed.key != allowed.key
    assert owed.label() == "obligation:pay(alice)"


def test_fact_carries_provenance():
    fact = Fact(
        predicate="is_wet",
        subject="ground",
        rule_index=1,
        used=frozenset({("raining", "", "", False, "neutral")}),
    )
    assert fact.rule_index == 1
    assert ("raining", "", "", False, "neutral") in fact.used


def test_hypothesis_payload_discriminates_fact_and_rule():
    fact = Hypothesis(id="H1", kind="fact", payload={"predicate": "has_engine", "subject": "x"})
    assert isinstance(fact.payload, Morphism)
    rule = Hypothesis(
        id="H2",
        kind="rule",
        payload={"conditions": [{"predicate": "a"}], "consequence": {"predicate": "b"}},
    )
    assert isinstance(rule.payload, Rule)


def test_theory_query_verdict_answer_construct():
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
    assert theory.rules[0].consequence.predicate == "is_wet"

    query = Query(target=Morphism(predicate="is_wet", object="ground"))
    assert query.answer_type == "yes_no"

    verdict = Verdict(status="supported", matched=["rule:1:=>is_wet(ground)"], shelf="proven")
    assert verdict.status == "supported"

    answer = Answer(value="yes", strength="proven", hypotheses_used=["H1"])
    assert answer.strength == "proven"

    record = WaveRecord(
        wave=0,
        proposal=Proposal(action="propose_rule", narration="...", payload={}),
        category="hypothesis",
        verdict_after=verdict,
    )
    assert record.category == "hypothesis"
