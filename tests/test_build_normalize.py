"""Tests for deterministic term normalization."""

from __future__ import annotations

import pytest

from ankyra.build.normalize import canonicalize_predicate, predicate_polarity


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("is_wet", "is_wet"),
        ("the_raining", "raining"),
        ("is_a", "is_a"),
        ("is", "is"),
        ("has", "has"),
        ("", ""),
        ("Is-Wet", "is_wet"),
        ("the_of", ""),
    ],
)
def test_canonicalize_predicate(raw, expected):
    assert canonicalize_predicate(raw) == expected


def test_canonicalize_is_idempotent():
    once = canonicalize_predicate("the_raining_of")
    assert canonicalize_predicate(once) == once


def test_predicate_polarity_does_not_guess_semantics():
    assert predicate_polarity("isNot") == ("isnot", False)
    assert predicate_polarity("is_not") == ("is_not", False)


def test_predicate_polarity_keeps_the_negation_flag():
    assert predicate_polarity("is_a", True) == ("is_a", True)
    assert predicate_polarity("is_a") == ("is_a", False)


def test_deontic_prefix_is_not_folded_in_v0():
    assert predicate_polarity("must_not_claim", True) == ("must_not_claim", True)
