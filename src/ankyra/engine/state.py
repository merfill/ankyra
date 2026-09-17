"""State for the reasoning pipeline: wave context, pending record, graph state.

``ReasoningState`` is the single state schema shared by the LangGraph adapter and
by the linear ``run_cycle`` driver; ``history`` and ``hypotheses`` are append-only
via an ``operator.add`` reducer.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from ankyra.core.models import (
    Answer,
    Explanation,
    Hypothesis,
    Proposal,
    ProposalCategory,
    Query,
    Theory,
    Verdict,
    WaveRecord,
)
from ankyra.core.schemas import ProblemStructure, QuestionStructure
from ankyra.engine.ledger import HypothesisLedger


@dataclass
class WaveContext:
    """Everything the proposal stage needs to see for one wave."""

    theory: Theory
    query: Query
    verdict: Verdict
    wave: int
    frontier: list[str] = field(default_factory=list)
    source_text: str = ""
    allow_hypotheses: bool = True
    hypotheses: list[Hypothesis] = field(default_factory=list)


@dataclass
class PendingWave:
    """A classified wave whose ``verdict_after`` is filled in by the next verify."""

    proposal: Proposal
    category: ProposalCategory
    reason: str
    wave: int
    hypothesis: Hypothesis | None = None
    progress: bool = True


class ReasoningState(TypedDict, total=False):
    problem_text: str
    structure: ProblemStructure | None
    theory: Theory | None
    question: QuestionStructure | None
    query: Query | None
    verdict: Verdict | None
    wave: int
    max_waves: int
    allow_hypotheses: bool
    ledger: HypothesisLedger
    draft: Any
    pending: PendingWave | None
    last_signature: str | None
    frontier: list[str]
    closed_facts: list[str]
    stuck: int
    status: str
    error: str | None
    answer: Answer | None
    explanation: Explanation | None
    halt: bool
    history: Annotated[list[WaveRecord], operator.add]
    hypotheses: Annotated[list[Hypothesis], operator.add]


def initial_state(
    *,
    problem_text: str = "",
    theory: Theory | None = None,
    query: Query | None = None,
    allow_hypotheses: bool = True,
    max_waves: int = 8,
) -> ReasoningState:
    return {
        "problem_text": problem_text,
        "structure": None,
        "theory": theory,
        "question": None,
        "query": query,
        "verdict": None,
        "wave": 0,
        "max_waves": max_waves,
        "allow_hypotheses": allow_hypotheses,
        "ledger": HypothesisLedger(),
        "draft": None,
        "pending": None,
        "last_signature": None,
        "frontier": [],
        "closed_facts": [],
        "stuck": 0,
        "status": "running",
        "error": None,
        "answer": None,
        "explanation": None,
        "halt": False,
        "history": [],
        "hypotheses": [],
    }


def merge_state(state: ReasoningState, update: dict) -> ReasoningState:
    """Apply a node update with the same reducer semantics as the LangGraph state."""
    merged: ReasoningState = dict(state)  # type: ignore[assignment]
    for key, value in update.items():
        if key in {"history", "hypotheses"}:
            merged[key] = [*(state.get(key) or []), *value]  # type: ignore[literal-required]
        else:
            merged[key] = value  # type: ignore[literal-required]
    return merged
