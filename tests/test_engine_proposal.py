"""Tests for the proposal hint assembly."""

from __future__ import annotations

from ankyra.core.models import Morphism, Proposal, Query, Theory, Verdict, WaveRecord
from ankyra.engine.proposal import build_hint
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
