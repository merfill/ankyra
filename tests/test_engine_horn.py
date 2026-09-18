"""Tests for the deterministic Horn engine."""

from __future__ import annotations

from ankyra.core.models import Morphism, Rule, Theory
from ankyra.engine.horn import build_context, complementary, match_goal, saturate


def test_unary_fact_derives_another_fact_with_provenance():
    theory = Theory(
        morphisms=[Morphism(predicate="raining")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
            )
        ],
    )
    store = saturate(theory)
    derived = store.get(("is_wet", "ground", "", False, "neutral"))
    assert derived is not None
    assert derived.rule_index == 1
    assert ("raining", "", "", False, "neutral") in derived.used
    assert derived.witness == "rule:1:=>is_wet(ground)"


def test_is_a_is_transitively_closed():
    theory = Theory(
        morphisms=[
            Morphism(predicate="is_a", subject="a", object="b"),
            Morphism(predicate="is_a", subject="b", object="c"),
        ],
    )
    store = saturate(theory)
    assert store.get(("is_a", "a", "c", False, "neutral")) is not None

    ctx = build_context(theory)
    hits = match_goal(Morphism(predicate="is_a", subject="a", object="?z"), store, ctx)
    objects = {hit.subst.get("?z") for hit in hits}
    assert {"b", "c"} <= objects


def test_modality_blocks_unification():
    neutral_rule = Rule(
        conditions=[Morphism(predicate="pay", subject="alice")],
        consequence=Morphism(predicate="done", subject="alice"),
    )
    theory = Theory(
        morphisms=[Morphism(predicate="pay", subject="alice", modality="obligation")],
        rules=[neutral_rule],
    )
    assert saturate(theory).get(("done", "alice", "", False, "neutral")) is None

    matching_rule = Rule(
        conditions=[Morphism(predicate="pay", subject="alice", modality="obligation")],
        consequence=Morphism(predicate="done", subject="alice"),
    )
    matching = Theory(
        morphisms=[Morphism(predicate="pay", subject="alice", modality="obligation")],
        rules=[matching_rule],
    )
    assert saturate(matching).get(("done", "alice", "", False, "neutral")) is not None


def test_complementary_finds_the_opposite_atom():
    theory = Theory(
        morphisms=[
            Morphism(predicate="raining"),
            Morphism(predicate="raining", negated=True),
        ],
    )
    store = saturate(theory)
    positive = store.get(("raining", "", "", False, "neutral"))
    assert positive is not None
    opposite = complementary(store, positive)
    assert opposite is not None and opposite.negated is True


def test_predicate_is_kept_as_authored_without_semantic_folding():
    theory = Theory(morphisms=[Morphism(predicate="isNot", subject="x", object="car")])
    store = saturate(theory)
    assert store.get(("isnot", "x", "car", False, "neutral")) is not None
