"""Tests for deterministic Phase 0 completeness checks."""

from __future__ import annotations

from ankyra.build.symbolic import (
    GapClass,
    check_naming,
    check_quote_witnesses,
    check_structural,
    classify_gap,
    enforce_grounded,
    quality_key,
    quote_in_source,
    quote_only_in_conditional,
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


def test_classify_gap_separates_repair_from_legitimate():
    assert classify_gap("missing_quote:morphism:snow(,)") is GapClass.REPAIRABLE
    assert classify_gap("structural:empty_theory") is GapClass.REPAIRABLE
    assert classify_gap("naming:object:Ground:rewrite_to_lowerCamelCase") is GapClass.DETERMINISTIC
    assert (
        classify_gap("structural:rule:1:consequence_negates_premise:fly(x,)")
        is GapClass.LEGITIMATE
    )
    assert (
        classify_gap("structural:axiom_blocks_exception:fly(x,)") is GapClass.LEGITIMATE
    )
    assert classify_gap("something:unknown") is GapClass.LEGITIMATE


def test_enforce_grounded_drops_atoms_without_a_real_quote():
    theory = Theory(
        source_text="It is raining.",
        morphisms=[
            Morphism(predicate="raining", quote="raining"),
            Morphism(predicate="sunny", quote="sunny"),
            Morphism(predicate="cloudy"),
        ],
    )
    kept = enforce_grounded(theory)
    assert [m.predicate for m in kept.morphisms] == ["raining"]


def test_enforce_grounded_drops_ungrounded_rules():
    theory = Theory(
        source_text="It is raining.",
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining", quote="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
                quote="if it rains the ground is wet",
            )
        ],
    )
    assert enforce_grounded(theory).rules == []


def test_enforce_grounded_is_a_noop_without_source_text():
    theory = Theory(morphisms=[Morphism(predicate="raining")])
    assert enforce_grounded(theory) is theory


def test_quality_key_prefers_grounded_over_ungrounded():
    source = "It is raining. The ground is wet."
    grounded = Theory(
        source_text=source,
        morphisms=[
            Morphism(predicate="raining", quote="raining"),
            Morphism(predicate="is_wet", subject="ground", quote="the ground is wet"),
        ],
    )
    ungrounded = Theory(
        source_text=source,
        morphisms=[
            Morphism(predicate="raining", quote="raining"),
            Morphism(predicate="is_wet", subject="ground", quote="not in the source"),
        ],
    )
    assert quality_key(grounded) < quality_key(ungrounded)


def test_quality_key_rewards_source_coverage_then_compactness():
    source = "It is raining. The ground is wet."
    wide = Theory(
        source_text=source,
        morphisms=[
            Morphism(predicate="raining", quote="raining"),
            Morphism(predicate="is_wet", subject="ground", quote="the ground is wet"),
        ],
    )
    narrow = Theory(
        source_text=source,
        morphisms=[Morphism(predicate="raining", quote="raining")],
    )
    assert quality_key(wide) < quality_key(narrow)


def test_quality_key_does_not_penalize_a_legitimate_exception_rule():
    source = "Birds fly. Penguins do not fly."
    theory = Theory(
        source_text=source,
        rules=[
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="penguin", quote="penguins")],
                consequence=Morphism(predicate="fly", subject="?x", negated=True, quote="do not fly"),
                quote="Penguins do not fly",
            )
        ],
    )
    hard = quality_key(theory)[0]
    assert hard == 0


def _conditional_theory() -> Theory:
    return Theory(
        source_text=(
            "If 1984 is a streaming service, then 1984 is a hardcover book. "
            "It is raining. If it is raining, the ground is wet."
        ),
        rules=[
            Rule(
                conditions=[Morphism(predicate="is_a", subject="1984", object="streaming_service")],
                consequence=Morphism(predicate="is_a", subject="1984", object="hardcover_book"),
                quote="If 1984 is a streaming service, then 1984 is a hardcover book",
            ),
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", subject="ground"),
                quote="If it is raining, the ground is wet",
            ),
        ],
    )


def test_conditional_quote_guard_survives_a_trailing_period():
    theory = _conditional_theory()
    assert quote_only_in_conditional(
        "If 1984 is a streaming service, then 1984 is a hardcover book.", theory
    )


def test_conditional_quote_guard_allows_a_standalone_occurrence():
    theory = _conditional_theory()
    # "it is raining" is a substring of the conditional but also occurs standalone.
    assert not quote_only_in_conditional("It is raining.", theory)
