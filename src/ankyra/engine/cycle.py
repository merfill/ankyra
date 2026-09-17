"""Linear driver for the reasoning cycle (the programmatic API).

Drives the same node functions as the LangGraph adapter, so there is one
implementation of every step; only the orchestration differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ankyra.config.settings import settings
from ankyra.core.models import (
    Answer,
    Explanation,
    Hypothesis,
    Query,
    Theory,
    Verdict,
    WaveRecord,
)
from ankyra.engine.nodes import (
    GraphDeps,
    classify_node,
    explain_node,
    propose_node,
    verify_node,
)
from ankyra.engine.proposal import ProposalDraft
from ankyra.engine.state import WaveContext, initial_state, merge_state


@dataclass
class CycleResult:
    answer: Answer
    explanation: Explanation
    verdict: Verdict
    status: str
    theory: Theory
    query: Query
    history: list[WaveRecord] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)


def _unused(*_args, **_kwargs):
    raise AssertionError("Phase 0 is not used by run_cycle")


def run_cycle(
    propose_fn: Callable[[WaveContext], ProposalDraft],
    theory: Theory,
    query: Query,
    *,
    allow_hypotheses: bool | None = None,
    max_waves: int | None = None,
) -> CycleResult:
    """Run the bounded cycle over a preset theory/query and return the answer."""
    if allow_hypotheses is None:
        allow_hypotheses = bool(settings.get("ALLOW_HYPOTHESES", True))
    if max_waves is None:
        max_waves = int(settings.get("MAX_WAVES", 8))

    deps = GraphDeps(extract_problem=_unused, extract_question=_unused, propose=propose_fn)
    state = initial_state(
        problem_text=theory.source_text,
        theory=theory,
        query=query,
        allow_hypotheses=allow_hypotheses,
        max_waves=max_waves,
    )
    state = merge_state(state, verify_node(state, deps))
    while state["status"] == "running":
        state = merge_state(state, propose_node(state, deps))
        if state["status"] != "running":
            break
        state = merge_state(state, classify_node(state, deps))
        state = merge_state(state, verify_node(state, deps))
    state = merge_state(state, explain_node(state, deps))

    return CycleResult(
        answer=state["answer"],
        explanation=state["explanation"],
        verdict=state["verdict"],
        status=state["status"],
        theory=state["theory"],
        query=state["query"],
        history=list(state.get("history") or []),
        hypotheses=list(state.get("hypotheses") or []),
    )
