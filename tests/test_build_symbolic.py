"""Tests for deterministic Phase 0 completeness checks."""

from __future__ import annotations

from ankyra.build.symbolic import (
    check_naming,
    check_quote_witnesses,
    check_structural,
    quote_in_source,
    symbolic_check,
)
from ankyra.core.models import Morphism, Object, Rule, Theory


def test_quote_in_source_requires_a_real_substring():
    assert quote_in_source("raining", "It is raining today.")
    assert quote_in_source("  is  rainING ", "It is raining today.")
    assert not quote_in_source("rain heavily", "It is raining today.")
    assert not quote_in_source("", "It is raining today.")
    assert not quote_in_source(None, "anything")


def test_quote_normalization_treats_hyphens_and_whitespace():
    assert quote_in_source("is-wet", "the ground is   wet")


def test_check_quote_witnesses_flags_missing_quotes():
    theory = Theory(
        source_text="It is raining.",
        morphisms=[
            Morphism(predicate="raining", quote="raining"),
            Morphism(predicate="sunny", quote="sunny"),
        ],
    )
    gaps = check_quote_witnesses(theory)
    assert any(gap.startswith("missing_quote:morphism:sunny") for gap in gaps)


def test_check_structural_flags_empty_theory():
    assert "structural:empty_theory" in check_structural(Theory())


def test_check_structural_flags_rule_blocked_by_axiom():
    theory = Theory(
        morphisms=[Morphism(predicate="fly", subject="x")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="bird", subject="x")],
                consequence=Morphism(predicate="fly", subject="x", negated=True),
            )
        ],
    )
    gaps = check_structural(theory)
    assert any("axiom_blocks_exception" in gap for gap in gaps)


def test_check_naming_flags_bad_ids():
    theory = Theory(
        objects=[Object(id="Ground")],
        morphisms=[Morphism(predicate="Is_Wet", quote="x")],
    )
    gaps = check_naming(theory)
    assert any(gap.startswith("naming:object:Ground") for gap in gaps)
    assert any(gap.startswith("naming:predicate:Is_Wet") for gap in gaps)


def test_symbolic_check_ok_for_a_clean_theory():
    theory = Theory(
        source_text="It is raining.",
        morphisms=[Morphism(predicate="raining", quote="raining")],
    )
    assert symbolic_check(theory).ok
