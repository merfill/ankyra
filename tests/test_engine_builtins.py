"""Tests for the range-restricted builtin comparisons (flag-gated)."""

from __future__ import annotations

import pytest

from ankyra.core.models import Morphism, Query, Rule, Theory
from ankyra.engine import builtins as builtins_module
from ankyra.engine.builtins import (
    builtin_unsafe,
    canonical_builtin,
    evaluate,
    is_builtin,
)
from ankyra.engine.classify import classify
from ankyra.engine.horn import saturate
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.proposal import ProposalDraft


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(builtins_module, "builtins_enabled", lambda: True)


def _threshold_theory():
    return Theory(
        morphisms=[
            Morphism(predicate="has_engine", subject="x"),
            Morphism(predicate="power", subject="x", object="150"),
        ],
        rules=[
            Rule(
                conditions=[
                    Morphism(predicate="has_engine", subject="?x"),
                    Morphism(predicate="power", subject="?x", object="?p"),
                    Morphism(predicate="gte", subject="?p", object="50"),
                ],
                consequence=Morphism(predicate="is_a", subject="?x", object="car"),
            )
        ],
    )


def test_canonical_builtin_aliases():
    assert canonical_builtin("=") == "eq"
    assert canonical_builtin("!=") == "neq"
    assert canonical_builtin(">=") == "gte"
    assert canonical_builtin("GT") == "gt"
    assert canonical_builtin("foo") is None


def test_is_builtin_respects_the_flag(enabled):
    assert is_builtin("gt")


def test_is_builtin_disabled_by_default():
    assert not is_builtin("gt")


def test_evaluate_operators(enabled):
    subst = {"?p": "150"}
    assert evaluate(Morphism(predicate="gt", subject="?p", object="50"), subst) is not None
    assert evaluate(Morphism(predicate="gte", subject="?p", object="150"), subst) is not None
    assert evaluate(Morphism(predicate="lt", subject="?p", object="50"), subst) is None
    assert evaluate(Morphism(predicate="lte", subject="?p", object="150"), subst) is not None
    assert evaluate(Morphism(predicate="eq", subject="?p", object="150"), subst) is not None
    assert evaluate(Morphism(predicate="neq", subject="?p", object="150"), subst) is None
    assert evaluate(Morphism(predicate=">", subject="?p", object="50"), subst) is not None


def test_non_numeric_and_unbound_operands_fail_silently(enabled):
    assert evaluate(Morphism(predicate="gt", subject="?p", object="50"), {}) is None
    assert evaluate(Morphism(predicate="gt", subject="heavy", object="50"), {}) is None
    assert evaluate(Morphism(predicate="eq", subject="car", object="car"), {}) is not None
    assert evaluate(Morphism(predicate="eq", subject="car", object="boat"), {}) is None


def test_rule_with_a_builtin_threshold_fires(enabled):
    store = saturate(_threshold_theory())
    assert store.get(("is_a", "x", "car", False, "neutral")) is not None


def test_disabled_builtins_do_not_fire():
    store = saturate(_threshold_theory())
    assert store.get(("is_a", "x", "car", False, "neutral")) is None


def test_builtin_unsafe_detects_an_unbound_operand(enabled):
    rule = Rule(
        conditions=[
            Morphism(predicate="gte", subject="?p", object="50"),
            Morphism(predicate="power", subject="?x", object="?p"),
        ],
        consequence=Morphism(predicate="is_a", subject="?x", object="car"),
    )
    assert builtin_unsafe(rule) is True


def test_unsafe_builtin_proposal_is_rejected(enabled):
    rule = Rule(
        conditions=[
            Morphism(predicate="gte", subject="?p", object="50"),
            Morphism(predicate="power", subject="?x", object="?p"),
        ],
        consequence=Morphism(predicate="is_a", subject="?x", object="car"),
    )
    theory = Theory(morphisms=[Morphism(predicate="power", subject="x", object="150")])
    query = Query(target=Morphism(predicate="is_a", subject="x", object="car"))
    result = classify(
        ProposalDraft(action="propose_rule", rule=rule),
        theory,
        query,
        HypothesisLedger(),
        source_text=theory.source_text,
        allow_hypotheses=True,
        wave=0,
    )
    assert result.category == "rejected"
    assert result.reason == "unsafe_builtin"
