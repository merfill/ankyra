"""Tests for deterministic enrichment."""

from __future__ import annotations

from ankyra.build.enrich import enrich_theory, heal_structural
from ankyra.core.models import Morphism, Rule, Theory


def test_enrich_does_not_materialize_rule_consequences():
    theory = Theory(
        morphisms=[Morphism(predicate="raining")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
            )
        ],
    )
    enriched = enrich_theory(theory)
    assert {m.predicate for m in enriched.morphisms} == {"raining"}
    assert len(enriched.rules) == 1


def test_enrich_keeps_a_real_contradiction():
    theory = Theory(
        morphisms=[
            Morphism(predicate="p", subject="x"),
            Morphism(predicate="p", subject="x", negated=True),
        ],
    )
    enriched = enrich_theory(theory)
    assert len(enriched.morphisms) == 2


def test_heal_structural_keeps_a_rule_blocked_by_an_axiom():
    rules = [
        Rule(
            conditions=[Morphism(predicate="bird", subject="x")],
            consequence=Morphism(predicate="fly", subject="x", negated=True),
        )
    ]
    assert heal_structural(rules) == rules


def test_heal_structural_drops_a_premise_that_negates_its_consequence():
    rule = Rule(
        conditions=[Morphism(predicate="p", subject="x", negated=True)],
        consequence=Morphism(predicate="p", subject="x"),
    )
    assert heal_structural([rule]) == []


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
