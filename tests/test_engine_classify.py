"""Tests for deterministic proposal classification."""

from __future__ import annotations

from ankyra.core.models import Morphism, Query, Rule, Theory
from ankyra.engine.classify import classify
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.proposal import ProposalDraft


def _classify(draft, theory, query, *, allow_hypotheses=True, wave=0):
    return classify(
        draft,
        theory,
        query,
        HypothesisLedger(),
        source_text=theory.source_text,
        allow_hypotheses=allow_hypotheses,
        wave=wave,
    )


def test_already_entailed_is_derivable_and_changes_nothing():
    theory = Theory(morphisms=[Morphism(predicate="raining")])
    query = Query(target=Morphism(predicate="raining"))
    draft = ProposalDraft(action="assert_cited_fact", fact=Morphism(predicate="raining"))
    result = _classify(draft, theory, query)
    assert result.category == "derivable"
    assert result.theory == theory


def test_valid_quote_is_cited():
    theory = Theory(
        morphisms=[Morphism(predicate="raining")],
        source_text="It is raining and the ground is wet.",
    )
    query = Query(target=Morphism(predicate="is_wet", object="ground"))
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(predicate="is_wet", object="ground", quote="the ground is wet"),
    )
    result = _classify(draft, theory, query)
    assert result.category == "cited"
    assert Morphism(predicate="is_wet", object="ground", quote="the ground is wet") in result.theory.morphisms


def test_missing_quote_becomes_a_tagged_hypothesis():
    theory = Theory(
        morphisms=[Morphism(predicate="p", subject="a")],
        source_text="p holds for a.",
    )
    query = Query(target=Morphism(predicate="r", subject="a"))
    rule = Rule(
        conditions=[Morphism(predicate="p", subject="?x")],
        consequence=Morphism(predicate="r", subject="?x"),
    )
    result = _classify(ProposalDraft(action="propose_rule", rule=rule), theory, query)
    assert result.category == "hypothesis"
    assert result.hypothesis is not None and result.hypothesis.id == "H1"
    assert result.theory.rules[-1].source == "hypothesis:H1"


def test_hypotheses_forbidden_rejects_without_changing_theory():
    theory = Theory(
        morphisms=[Morphism(predicate="p", subject="a")],
        source_text="p holds for a.",
    )
    query = Query(target=Morphism(predicate="r", subject="a"))
    rule = Rule(
        conditions=[Morphism(predicate="p", subject="?x")],
        consequence=Morphism(predicate="r", subject="?x"),
    )
    result = _classify(
        ProposalDraft(action="propose_rule", rule=rule),
        theory,
        query,
        allow_hypotheses=False,
    )
    assert result.category == "rejected"
    assert result.reason == "hypotheses_forbidden"
    assert result.theory == theory


def test_unsafe_rule_is_rejected():
    theory = Theory(morphisms=[Morphism(predicate="p", subject="a")])
    query = Query(target=Morphism(predicate="r", subject="b"))
    rule = Rule(
        conditions=[Morphism(predicate="p", subject="?x")],
        consequence=Morphism(predicate="r", subject="?y"),
    )
    result = _classify(ProposalDraft(action="propose_rule", rule=rule), theory, query)
    assert result.category == "rejected"
    assert result.reason == "unsafe_rule"


def test_reformalize_rejects_target_weakening():
    theory = Theory()
    query = Query(target=Morphism(predicate="p"))
    draft = ProposalDraft(action="reformalize_query", query=Query(target=None))
    result = _classify(draft, theory, query)
    assert result.category == "rejected"
    assert result.reason == "target_weakened"
