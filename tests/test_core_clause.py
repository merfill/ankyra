"""Tests for the L2 clause IR: disjunctive rule heads and decomposed goals."""

from __future__ import annotations

from ankyra.core.models import Morphism, Query, Rule


def test_horn_rule_head_is_one_literal():
    rule = Rule(conditions=[Morphism(predicate="a")], consequence=Morphism(predicate="b"))
    assert rule.is_horn
    assert [literal.predicate for literal in rule.head] == ["b"]


def test_disjunctive_head_lists_alternatives():
    rule = Rule(
        conditions=[Morphism(predicate="a")],
        consequence=Morphism(predicate="b"),
        alternatives=[Morphism(predicate="c")],
    )
    assert not rule.is_horn
    assert [literal.predicate for literal in rule.head] == ["b", "c"]


def test_a_conditionless_disjunctive_rule_is_a_fact_and_not_horn():
    fact = Rule(consequence=Morphism(predicate="a"), alternatives=[Morphism(predicate="b")])
    assert fact.conditions == []
    assert not fact.is_horn


def test_query_goal_fields_default_to_single():
    query = Query(target=Morphism(predicate="a"))
    assert query.goal_mode == "single"
    assert query.goals == []


def test_query_carries_decomposed_goals_and_mode():
    query = Query(
        target=Morphism(predicate="a"),
        goals=[Morphism(predicate="a"), Morphism(predicate="b")],
        goal_mode="all",
    )
    assert query.goal_mode == "all"
    assert len(query.goals) == 2
