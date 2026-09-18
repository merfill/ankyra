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


def test_fresh_quote_rule_is_cited():
    theory = Theory(
        morphisms=[Morphism(predicate="p", subject="a")],
        source_text="p holds for a and all p are r",
    )
    query = Query(target=Morphism(predicate="r", subject="a"))
    rule = Rule(
        conditions=[Morphism(predicate="p", subject="?x")],
        consequence=Morphism(predicate="r", subject="?x"),
        quote="all p are r",
    )
    result = _classify(ProposalDraft(action="propose_rule", rule=rule), theory, query)
    assert result.category == "cited"


def _nice_people_theory() -> Theory:
    return Theory(
        morphisms=[Morphism(predicate="nice", subject="fiona")],
        rules=[
            Rule(
                conditions=[
                    Morphism(predicate="is_a", subject="?x", object="people"),
                    Morphism(predicate="nice", subject="?x"),
                ],
                consequence=Morphism(predicate="young", subject="?x"),
                quote="All nice people are young",
            )
        ],
        source_text="All nice people are young",
    )


def test_same_quote_rule_that_drops_a_condition_is_a_hypothesis():
    theory = _nice_people_theory()
    query = Query(target=Morphism(predicate="young", subject="fiona"))
    rule = Rule(
        conditions=[Morphism(predicate="nice", subject="?x")],
        consequence=Morphism(predicate="young", subject="?x"),
        quote="All nice people are young",
    )
    result = _classify(ProposalDraft(action="propose_rule", rule=rule), theory, query)
    assert result.category == "hypothesis"
    assert result.theory.rules[-1].source == "hypothesis:H1"


def test_dropping_a_condition_is_rejected_when_hypotheses_are_forbidden():
    theory = _nice_people_theory()
    query = Query(target=Morphism(predicate="young", subject="fiona"))
    rule = Rule(
        conditions=[Morphism(predicate="nice", subject="?x")],
        consequence=Morphism(predicate="young", subject="?x"),
        quote="All nice people are young",
    )
    result = _classify(
        ProposalDraft(action="propose_rule", rule=rule),
        theory,
        query,
        allow_hypotheses=False,
    )
    assert result.category == "rejected"
    assert result.reason == "quote_reused"


def test_reusing_a_grounded_rule_quote_is_never_silently_cited():
    theory = Theory(
        morphisms=[Morphism(predicate="young", subject="anne")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="person")],
                consequence=Morphism(predicate="blue", subject="?x", negated=True),
                quote="All young people are not blue",
            )
        ],
        source_text="All young people are not blue",
    )
    query = Query(target=Morphism(predicate="blue", subject="anne", negated=True))
    rule = Rule(
        conditions=[Morphism(predicate="young", subject="?x")],
        consequence=Morphism(predicate="blue", subject="?x", negated=True),
        quote="All young people are not blue",
    )
    result = _classify(ProposalDraft(action="propose_rule", rule=rule), theory, query)
    assert result.category == "hypothesis"


def test_fact_reusing_a_rule_quote_is_not_cited():
    theory = Theory(
        rules=[
            Rule(
                conditions=[Morphism(predicate="human", subject="?x")],
                consequence=Morphism(predicate="mortal", subject="?x"),
                quote="all humans are mortal",
            )
        ],
        source_text="all humans are mortal",
    )
    query = Query(target=Morphism(predicate="mortal", subject="fiona"))
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(predicate="is_a", subject="fiona", object="people", quote="all humans are mortal"),
    )
    result = _classify(draft, theory, query)
    assert result.category == "hypothesis"


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
