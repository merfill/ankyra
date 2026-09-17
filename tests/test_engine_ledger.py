"""Tests for the hypothesis ledger and proof-based attribution."""

from __future__ import annotations

from ankyra.core.models import Morphism, Rule, Theory
from ankyra.engine.horn import saturate
from ankyra.engine.ledger import HypothesisLedger, morphism_key


def test_rule_hypothesis_is_attributed_through_the_rule_index():
    rule = Rule(
        conditions=[Morphism(predicate="p", subject="?x")],
        consequence=Morphism(predicate="r", subject="?x"),
    )
    theory = Theory(morphisms=[Morphism(predicate="p", subject="a")], rules=[rule])
    ledger = HypothesisLedger()
    hypothesis_id = ledger.next_id()
    ledger.add_rule(hypothesis_id, rule, rule_index=1, rationale="", wave=0)

    store = saturate(theory)
    proof = frozenset(fact.key for fact in store.facts)
    assert ledger.used(store, proof) == [hypothesis_id]


def test_fact_hypothesis_is_attributed_through_its_key():
    fact = Morphism(predicate="is_a", subject="car", object="motor_vehicle")
    theory = Theory(morphisms=[fact])
    ledger = HypothesisLedger()
    hypothesis_id = ledger.next_id()
    ledger.add_fact(
        hypothesis_id, fact, key=morphism_key(fact), rationale="", wave=0
    )

    store = saturate(theory)
    proof = frozenset({morphism_key(fact)})
    assert ledger.used(store, proof) == [hypothesis_id]


def test_ids_are_sequential():
    ledger = HypothesisLedger()
    assert ledger.next_id() == "H1"
    ledger.add_fact(
        "H1", Morphism(predicate="p"), key=morphism_key(Morphism(predicate="p")), rationale="", wave=0
    )
    assert ledger.next_id() == "H2"
