"""Tests for deterministic enrichment."""

from __future__ import annotations

from ankyra.build.enrich import enrich_theory, heal_structural, strip_domain_conditions
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


def test_strip_domain_conditions_removes_a_universe_sort_premise():
    rule = Rule(
        conditions=[
            Morphism(predicate="is_a", subject="?x", object="person"),
            Morphism(predicate="young", subject="?x"),
        ],
        consequence=Morphism(predicate="white", subject="?x"),
    )
    stripped = strip_domain_conditions([rule], ["person"])
    assert [cond.predicate for cond in stripped[0].conditions] == ["young"]


def test_strip_domain_conditions_keeps_a_proper_class_premise():
    rule = Rule(
        conditions=[Morphism(predicate="is_a", subject="?x", object="dog")],
        consequence=Morphism(predicate="mammal", subject="?x"),
    )
    stripped = strip_domain_conditions([rule], ["person"])
    assert stripped[0].conditions[0].object == "dog"


def test_enrich_drops_domain_conditions_from_a_theory():
    theory = Theory(
        domain=["person"],
        rules=[
            Rule(
                conditions=[
                    Morphism(predicate="is_a", subject="?x", object="person"),
                    Morphism(predicate="nice", subject="?x"),
                ],
                consequence=Morphism(predicate="young", subject="?x"),
            )
        ],
    )
    enriched = enrich_theory(theory)
    assert [cond.predicate for cond in enriched.rules[0].conditions] == ["nice"]


def test_build_theory_drops_domain_conditions_end_to_end():
    from ankyra.build.pipeline import build_theory
    from ankyra.core.schemas import ProblemStructure

    structure = ProblemStructure.model_validate(
        {
            "source_text": "Fiona is nice. All nice people are young.",
            "domain": ["person"],
            "facts": [{"predicate": "nice", "subject": "fiona"}],
            "rules": [
                {
                    "antecedent": [
                        {"predicate": "is_a", "subject": "?x", "object": "person"},
                        {"predicate": "nice", "subject": "?x"},
                    ],
                    "consequent": {"predicate": "young", "subject": "?x"},
                    "quote": "All nice people are young",
                }
            ],
        }
    )
    theory = build_theory(structure)
    assert [cond.predicate for cond in theory.rules[0].conditions] == ["nice"]
    assert theory.domain == ["person"]
