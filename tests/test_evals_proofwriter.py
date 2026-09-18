"""Offline tests for the ProofWriter adapter (no LLM, no network)."""

from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import pytest

from ankyra.core.models import Answer, Morphism, Query
from evals import proofwriter as pw


def _result(target_negated: bool, kind: str, status: str = "supported") -> SimpleNamespace:
    target = Morphism(predicate="nice", subject="anne", negated=target_negated)
    return SimpleNamespace(
        query=Query(target=target),
        answer=Answer(kind=kind),
        status=status,
    )


def test_problem_text_phrases_the_statement_as_a_yes_no():
    record = {"theory": "Anne is nice.", "question": "Anne is not nice."}
    assert pw.problem_text(record) == "Anne is nice.\n\nIs it true that Anne is not nice?"


def test_is_negative_detects_explicit_negation():
    assert pw.is_negative("Anne is not nice.")
    assert pw.is_negative("The dog doesn't chase the lion.")
    assert not pw.is_negative("Anne is nice.")


@pytest.mark.parametrize(
    ("label", "flipped", "expected"),
    [
        ("True", False, "yes"),
        ("False", False, "no"),
        ("Unknown", False, "unknown"),
        ("True", True, "no"),
        ("False", True, "yes"),
        ("Unknown", True, "unknown"),
    ],
)
def test_expected_kind_is_polarity_aware(label, flipped, expected):
    assert pw.expected_kind(label, flipped) == expected


def test_score_matches_a_positive_statement():
    score = pw.score_record(
        {"id": "p", "answer": "True", "question": "Anne is nice."}, _result(False, "yes")
    )
    assert score["polarity_known"] is True
    assert score["polarity_flipped"] is False
    assert score["kind_match"] is True


def test_score_matches_a_preserved_negative_statement():
    score = pw.score_record(
        {"id": "p", "answer": "True", "question": "Anne is not nice."}, _result(True, "yes")
    )
    assert score["polarity_flipped"] is False
    assert score["expected_kind"] == "yes"
    assert score["kind_match"] is True


def test_score_accounts_for_a_polarity_flip():
    score = pw.score_record(
        {"id": "p", "answer": "True", "question": "Anne is not nice."}, _result(False, "no")
    )
    assert score["polarity_flipped"] is True
    assert score["expected_kind"] == "no"
    assert score["kind_match"] is True


def test_score_without_a_target_is_not_counted_as_a_match():
    result = SimpleNamespace(query=None, answer=Answer(kind="unknown"), status="unsupported")
    score = pw.score_record({"id": "p", "answer": "Unknown", "question": "Anne is nice."}, result)
    assert score["polarity_known"] is False
    assert score["kind_match"] is False


def test_committed_sample_is_tier_a_stratified():
    rows = pw.load_sample()
    assert len(rows) == 45
    counts = Counter((row["config"], row["answer"]) for row in rows)
    assert set(counts.values()) == {3}
    assert {row["config"] for row in rows} == set(pw._DEPTHS)
    assert {row["answer"] for row in rows} == set(pw._LABELS)
    assert all(row["source"] == "tasksource/proofwriter" for row in rows)
    assert all(row["theory"] and row["question"] for row in rows)
