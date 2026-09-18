"""Tests for the proposal hint assembly."""

from __future__ import annotations

from ankyra.core.models import Morphism, Proposal, Query, Rule, Theory, Verdict, WaveRecord
from ankyra.engine.proposal import (
    ProposalDraft,
    build_hint,
    effective_action,
    to_proposal,
)
from ankyra.engine.state import WaveContext


def _context(history: list[WaveRecord]) -> WaveContext:
    return WaveContext(
        theory=Theory(source_text="source"),
        query=Query(target=Morphism(predicate="p")),
        verdict=Verdict(status="unsupported"),
        wave=2,
        source_text="source",
        history=history,
    )


def test_hint_reports_the_last_rejected_proposal():
    record = WaveRecord(
        wave=1,
        proposal=Proposal(action="propose_rule"),
        category="rejected",
        reason="missing_payload",
        verdict_after=Verdict(status="unsupported"),
    )
    hint = build_hint(_context([record]))
    assert "Previous waves:" in hint
    assert "w1 rejected propose_rule(missing_payload)" in hint


def test_hint_without_history_has_no_previous_waves_section():
    assert "Previous waves:" not in build_hint(_context([]))


def _near_miss_context() -> WaveContext:
    theory = Theory(
        morphisms=[Morphism(predicate="nice", subject="fiona")],
        rules=[
            Rule(
                conditions=[
                    Morphism(predicate="is_a", subject="?x", object="person"),
                    Morphism(predicate="nice", subject="?x"),
                ],
                consequence=Morphism(predicate="young", subject="?x"),
            )
        ],
        source_text="All nice people are young",
    )
    return WaveContext(
        theory=theory,
        query=Query(target=Morphism(predicate="young", subject="fiona")),
        verdict=Verdict(status="unsupported"),
        wave=0,
        source_text="All nice people are young",
        history=[],
    )


def test_hint_lists_near_miss_unmet_body_literals():
    hint = build_hint(_near_miss_context())
    assert "Near-miss rules" in hint
    assert "unmet is_a(fiona,person)" in hint


def test_effective_action_follows_the_payload_when_the_label_is_wrong():
    draft = ProposalDraft(action="propose_rule", fact=Morphism(predicate="p", subject="a"))
    assert effective_action(draft) == "assert_cited_fact"


def test_effective_action_is_none_for_an_empty_draft():
    assert effective_action(ProposalDraft(action="propose_rule")) is None


def test_to_proposal_records_the_effective_action():
    draft = ProposalDraft(action="propose_rule", fact=Morphism(predicate="p", subject="a"))
    assert to_proposal(draft).action == "assert_cited_fact"
