"""Tests for deterministic enrichment."""

from __future__ import annotations

from ankyra.build.enrich import (
    enrich_theory,
    heal_contradictory_axioms,
    heal_structural,
    materialize_rule_morphisms,
)
from ankyra.core.models import Morphism, Rule, Theory


def test_materialize_adds_the_consequence_when_conditions_are_facts():
    morphisms = [Morphism(predicate="raining")]
    rules = [
        Rule(
            conditions=[Morphism(predicate="raining")],
            consequence=Morphism(predicate="is_wet", object="ground"),
        )
    ]
    predicates = {m.predicate for m in materialize_rule_morphisms(morphisms, rules)}
    assert "is_wet" in predicates


def test_heal_structural_drops_a_rule_blocked_by_an_axiom():
    morphisms = [Morphism(predicate="fly", subject="x")]
    rules = [
        Rule(
            conditions=[Morphism(predicate="bird", subject="x")],
            consequence=Morphism(predicate="fly", subject="x", negated=True),
        )
    ]
    assert heal_structural(morphisms, rules) == []


def test_heal_contradictory_axioms_keeps_the_positive_reading():
    out = heal_contradictory_axioms(
        [Morphism(predicate="p", subject="x", negated=True), Morphism(predicate="p", subject="x")]
    )
    assert len(out) == 1
    assert out[0].negated is False


def test_enrich_dedupes_identical_morphisms_and_keeps_the_quote():
    theory = Theory(
        source_text="x is a car",
        morphisms=[
            Morphism(predicate="is_a", subject="x", object="car"),
            Morphism(predicate="is_a", subject="x", object="car", quote="x is a car"),
        ],
    )
    enriched = enrich_theory(theory)
    assert len(enriched.morphisms) == 1
    assert enriched.morphisms[0].quote == "x is a car"


def test_enrich_drops_malformed_atoms_and_rules():
    theory = Theory(
        source_text="x",
        morphisms=[Morphism(predicate=""), Morphism(predicate="raining")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="")],
                consequence=Morphism(predicate="wet"),
            )
        ],
    )
    enriched = enrich_theory(theory)
    assert [m.predicate for m in enriched.morphisms] == ["raining"]
    assert enriched.rules == []
