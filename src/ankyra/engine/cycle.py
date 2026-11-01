"""Linear driver for the reasoning cycle (the programmatic API).

Drives the same node functions as the LangGraph adapter, so there is one
implementation of every step; only the orchestration differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from ankyra.config.settings import settings
from ankyra.core.models import (
    Answer,
    Explanation,
    Hypothesis,
    Query,
    Revision,
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
from ankyra.engine.state import PendingWave, WaveContext, initial_state, merge_state


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
    revisions: list[Revision] = field(default_factory=list)


@dataclass
class CycleEvent:
    """A deterministic snapshot emitted after one node of the cycle.

    It carries only state the engine already built (theory, query, verdict,
    answer, and the wave record); an observer may render it but never changes the
    run. ``wave`` is the wave the node just processed.
    """

    node: Literal["verified", "proposed", "classified", "explained"]
    wave: int
    status: str
    theory: Theory
    query: Query
    verdict: Verdict | None = None
    answer: Answer | None = None
    draft: ProposalDraft | None = None
    pending: PendingWave | None = None
    record: WaveRecord | None = None
    revision: Revision | None = None


def _unused(*_args, **_kwargs):
    raise AssertionError("Phase 0 is not used by run_cycle")


def _emit(
    on_event: Callable[[CycleEvent], None] | None,
    state: dict,
    node: Literal["verified", "proposed", "classified", "explained"],
    **extra,
) -> None:
    if on_event is None:
        return
    # ``wave`` counts completed waves, so it is bumped only by the following
    # verify; the propose/classify nodes belong to the wave in progress.
    wave = state.get("wave", 0) + (1 if node in {"proposed", "classified"} else 0)
    on_event(
        CycleEvent(
            node=node,
            wave=wave,
            status=state.get("status", ""),
            theory=state["theory"],
            query=state["query"],
            verdict=state.get("verdict"),
            answer=state.get("last_answer"),
            **extra,
        )
    )


def run_cycle(
    propose_fn: Callable[[WaveContext], ProposalDraft],
    theory: Theory,
    query: Query,
    *,
    allow_hypotheses: bool | None = None,
    max_waves: int | None = None,
    on_event: Callable[[CycleEvent], None] | None = None,
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
    _emit(on_event, state, "verified")
    while state["status"] == "running":
        state = merge_state(state, propose_node(state, deps))
        _emit(on_event, state, "proposed", draft=state.get("draft"))
        if state["status"] != "running":
            break
        state = merge_state(state, classify_node(state, deps))
        _emit(on_event, state, "classified", pending=state.get("pending"))
        update = verify_node(state, deps)
        state = merge_state(state, update)
        _emit(
            on_event,
            state,
            "verified",
            record=(update.get("history") or [None])[0],
            revision=(update.get("revisions") or [None])[0],
        )
    state = merge_state(state, explain_node(state, deps))
    _emit(on_event, state, "explained")

    return CycleResult(
        answer=state["answer"],
        explanation=state["explanation"],
        verdict=state["verdict"],
        status=state["status"],
        theory=state["theory"],
        query=state["query"],
        history=list(state.get("history") or []),
        hypotheses=list(state.get("hypotheses") or []),
        revisions=list(state.get("revisions") or []),
    )
