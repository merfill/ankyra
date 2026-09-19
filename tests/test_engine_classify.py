"""Tests for deterministic proposal classification."""

from __future__ import annotations

from ankyra.core.models import Morphism, Query, Rule, Theory
from ankyra.engine.classify import classify
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.proposal import ProposalDraft


def _classify(draft, theory, query, *, allow_hypotheses=True, wave=0, question_text=""):
    return classify(
        draft,
        theory,
        query,
        HypothesisLedger(),
        source_text=theory.source_text,
        allow_hypotheses=allow_hypotheses,
        wave=wave,
        question_text=question_text,
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


def test_a_quote_from_the_question_is_not_cited():
    theory = Theory(
        morphisms=[Morphism(predicate="raining")],
        source_text="It is raining. Is the ground wet?",
    )
    query = Query(target=Morphism(predicate="is_wet", object="ground"))
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(predicate="is_wet", object="ground", quote="the ground wet"),
    )
    assert _classify(draft, theory, query).category == "cited"
    guarded = _classify(draft, theory, query, question_text="Is the ground wet?")
    assert guarded.category == "rejected"
    assert guarded.reason == "question_begging"
    refused = _classify(
        draft, theory, query, allow_hypotheses=False, question_text="Is the ground wet?"
    )
    assert refused.category == "rejected"
    assert refused.reason == "hypotheses_forbidden"


def test_a_fact_hypothesis_asserting_the_closed_target_is_rejected():
    theory = Theory(
        morphisms=[Morphism(predicate="is_a", subject="earin", object="smart")],
        source_text="Earin is smart.",
    )
    query = Query(target=Morphism(predicate="is_a", subject="earin", object="big", negated=True))
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(predicate="is_a", subject="earin", object="big", negated=True),
    )
    result = _classify(draft, theory, query)
    assert result.category == "rejected"
    assert result.reason == "question_begging"
    assert result.theory == theory


def test_an_open_target_may_be_bound_by_a_fact_hypothesis():
    theory = Theory(morphisms=[Morphism(predicate="has_engine", subject="x")])
    query = Query(target=Morphism(predicate="is_a", subject="x", object="?c"), answer_type="open")
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(predicate="is_a", subject="x", object="car"),
    )
    result = _classify(draft, theory, query)
    assert result.category == "hypothesis"


def test_a_cited_fact_may_state_the_target():
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


def test_a_fact_grounded_only_on_a_conditional_is_not_cited():
    theory = Theory(
        morphisms=[Morphism(predicate="is_a", subject="harry", object="blue")],
        rules=[
            Rule(
                conditions=[
                    Morphism(predicate="is_a", subject="harry", object="red", quote="Harry is red")
                ],
                consequence=Morphism(
                    predicate="is_a", subject="harry", object="furry", quote="Harry is furry"
                ),
                quote="If Harry is red then Harry is furry",
            )
        ],
        source_text="Harry is blue. If Harry is red then Harry is furry.",
    )
    query = Query(target=Morphism(predicate="is_a", subject="harry", object="green"))
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(
            predicate="is_a", subject="harry", object="red", quote="Harry is red"
        ),
    )
    result = _classify(draft, theory, query, allow_hypotheses=False)
    assert result.category == "rejected"
    assert result.reason == "quote_conditional"


def test_a_standalone_fact_quote_is_still_cited():
    theory = Theory(
        morphisms=[Morphism(predicate="sunny")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining", quote="it rains")],
                consequence=Morphism(
                    predicate="is_wet", object="ground", quote="the ground is wet"
                ),
                quote="If it rains, the ground is wet",
            )
        ],
        source_text="It is sunny. The ground is wet. If it rains, the ground is wet.",
    )
    query = Query(target=Morphism(predicate="slippery", object="road"))
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(predicate="is_wet", object="ground", quote="The ground is wet"),
    )
    result = _classify(draft, theory, query)
    assert result.category == "cited"


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


def _morphism_quote_theory() -> Theory:
    return Theory(
        morphisms=[Morphism(predicate="nice", subject="fiona", quote="Fiona is nice")],
        source_text="Fiona is nice.",
    )


def test_fact_reusing_a_morphism_quote_is_not_cited():
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(predicate="is_a", subject="fiona", object="person", quote="Fiona is nice"),
    )
    result = _classify(draft, _morphism_quote_theory(), Query(target=Morphism(predicate="young", subject="fiona")))
    assert result.category == "hypothesis"
    assert result.hypothesis is not None


def test_fact_reusing_a_morphism_quote_is_rejected_when_hypotheses_are_forbidden():
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(predicate="is_a", subject="fiona", object="person", quote="Fiona is nice"),
    )
    result = _classify(
        draft,
        _morphism_quote_theory(),
        Query(target=Morphism(predicate="young", subject="fiona")),
        allow_hypotheses=False,
    )
    assert result.category == "rejected"
    assert result.reason == "quote_reused"


def _alan_theory() -> Theory:
    return Theory(
        morphisms=[Morphism(predicate="is_a", subject="alan", object="big", quote="Alan is very big")],
        source_text="Alan is very big for being so young.",
    )


def test_a_broader_span_reusing_an_existing_quote_is_not_cited():
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(
            predicate="is_a", subject="alan", object="red", negated=True,
            quote="Alan is very big for being so young",
        ),
    )
    result = _classify(draft, _alan_theory(), Query(target=Morphism(predicate="is_a", subject="alan", object="blue")))
    assert result.category == "hypothesis"


def test_a_broader_span_reusing_an_existing_quote_is_rejected_when_hypotheses_are_forbidden():
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(
            predicate="is_a", subject="alan", object="red", negated=True,
            quote="Alan is very big for being so young",
        ),
    )
    result = _classify(
        draft,
        _alan_theory(),
        Query(target=Morphism(predicate="is_a", subject="alan", object="blue")),
        allow_hypotheses=False,
    )
    assert result.category == "rejected"
    assert result.reason == "quote_reused"


def test_a_narrower_span_inside_an_existing_quote_is_not_cited():
    theory = Theory(
        morphisms=[Morphism(predicate="is_a", subject="anne", object="nice", quote="Anne is nice and round")],
        source_text="Anne is nice and round.",
    )
    draft = ProposalDraft(
        action="assert_cited_fact",
        fact=Morphism(predicate="is_a", subject="anne", object="round", quote="Anne is nice"),
    )
    result = _classify(draft, theory, Query(target=Morphism(predicate="is_a", subject="anne", object="young")))
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


def test_a_mislabeled_fact_action_is_decided_by_its_payload():
    theory = Theory(
        morphisms=[Morphism(predicate="nice", subject="fiona")],
        source_text="Fiona is nice.",
    )
    query = Query(target=Morphism(predicate="old", subject="fiona"))
    draft = ProposalDraft(
        action="propose_rule", fact=Morphism(predicate="young", subject="fiona")
    )
    result = _classify(draft, theory, query)
    assert result.category == "hypothesis"
    assert result.theory.morphisms[-1].predicate == "young"


def test_a_mislabeled_rule_action_is_decided_by_its_payload():
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
    result = _classify(ProposalDraft(action="assert_cited_fact", rule=rule), theory, query)
    assert result.category == "cited"


def test_conflicting_payloads_are_rejected_as_ambiguous():
    theory = Theory()
    query = Query(target=Morphism(predicate="p"))
    draft = ProposalDraft(
        action="assert_cited_fact",
        rule=Rule(
            conditions=[Morphism(predicate="p", subject="?x")],
            consequence=Morphism(predicate="r", subject="?x"),
        ),
        query=Query(target=Morphism(predicate="p")),
    )
    result = _classify(draft, theory, query)
    assert result.category == "rejected"
    assert result.reason == "ambiguous_payload"


def test_an_empty_proposal_is_missing_payload():
    draft = ProposalDraft(action="propose_rule")
    result = _classify(draft, Theory(), Query(target=Morphism(predicate="p")))
    assert result.category == "rejected"
    assert result.reason == "missing_payload"
