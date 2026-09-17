"""Pipeline nodes: one step each, plus pure routers.

Nodes are plain functions over ``ReasoningState`` that take injected ``GraphDeps``
(so the pipeline is testable without an LLM). ``ankyra.graph.build`` binds them
into a ``StateGraph``; ``run_cycle`` drives the same functions linearly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ankyra.build.pipeline import build_query, build_theory
from ankyra.core.models import Answer, Explanation, Query, Theory, WaveRecord
from ankyra.core.schemas import ProblemStructure, QuestionStructure
from ankyra.engine.answer import build_answer
from ankyra.engine.classify import classify
from ankyra.engine.explain import build_explanation
from ankyra.engine.horn import frontier
from ankyra.engine.proposal import ProposalDraft, signature, to_proposal
from ankyra.engine.state import PendingWave, ReasoningState, WaveContext
from ankyra.engine.verify import verify


@dataclass
class GraphDeps:
    """Injected stages: real LLM calls in production, stubs in tests."""

    extract_problem: Callable[[str], ProblemStructure]
    extract_question: Callable[[str, Theory, str], QuestionStructure]
    propose: Callable[[WaveContext], ProposalDraft]


def extract_problem_node(state: ReasoningState, deps: GraphDeps) -> dict:
    try:
        return {"structure": deps.extract_problem(state["problem_text"])}
    except Exception as exc:
        return {"status": "extraction_error", "error": str(exc), "structure": None}


def build_theory_node(state: ReasoningState, deps: GraphDeps) -> dict:
    return {"theory": build_theory(state["structure"])}


def extract_question_node(state: ReasoningState, deps: GraphDeps) -> dict:
    structure = state.get("structure")
    question_text = structure.question if structure is not None else ""
    try:
        return {
            "question": deps.extract_question(
                question_text, state["theory"], state["problem_text"]
            )
        }
    except Exception as exc:
        return {"status": "extraction_error", "error": str(exc), "question": None}


def build_query_node(state: ReasoningState, deps: GraphDeps) -> dict:
    return {"query": build_query(state["theory"], state["question"])}


def verify_node(state: ReasoningState, deps: GraphDeps) -> dict:
    """Verify, append the previous wave's record, and commit the routing status."""
    theory = state["theory"]
    query = state["query"]
    verdict = verify(theory, query)
    labels = frontier(theory)
    wave = state.get("wave", 0)
    update: dict = {"verdict": verdict, "frontier": labels, "closed_facts": labels}

    pending = state.get("pending")
    stuck = state.get("stuck", 0)
    if pending is not None:
        update["history"] = [
            WaveRecord(
                wave=pending.wave,
                proposal=pending.proposal,
                category=pending.category,
                reason=pending.reason,
                verdict_after=verdict,
            )
        ]
        if pending.hypothesis is not None:
            update["hypotheses"] = [pending.hypothesis]
        stuck = 0 if pending.progress else stuck + 1
        update["stuck"] = stuck
        wave = pending.wave + 1
        update["pending"] = None
    update["wave"] = wave

    if verdict.status in {"supported", "refuted"}:
        status = verdict.status
    elif state.get("halt"):
        status = "unsupported"
    elif stuck >= 2:
        status = "no_progress"
    elif wave >= state.get("max_waves", 0):
        status = "budget"
    else:
        status = "running"
    update["status"] = status
    return update


def propose_node(state: ReasoningState, deps: GraphDeps) -> dict:
    context = WaveContext(
        theory=state["theory"],
        query=state["query"],
        verdict=state["verdict"],
        wave=state["wave"],
        frontier=state.get("frontier", []),
        source_text=state["theory"].source_text,
        allow_hypotheses=state["allow_hypotheses"],
        hypotheses=list(state.get("hypotheses") or []),
    )
    try:
        draft = deps.propose(context)
    except Exception:
        return {"status": "proposal_error", "draft": None}
    draft_signature = signature(draft)
    if draft_signature == state.get("last_signature"):
        return {"status": "no_progress", "draft": None}
    return {"draft": draft, "last_signature": draft_signature, "status": "running"}


def classify_node(state: ReasoningState, deps: GraphDeps) -> dict:
    draft = state["draft"]
    ledger = state["ledger"]
    result = classify(
        draft,
        state["theory"],
        state["query"],
        ledger,
        source_text=state["theory"].source_text,
        allow_hypotheses=state["allow_hypotheses"],
        wave=state["wave"],
    )
    pending = PendingWave(
        proposal=to_proposal(draft),
        category=result.category,
        reason=result.reason,
        wave=state["wave"],
        hypothesis=result.hypothesis,
        progress=result.theory != state["theory"] or result.query != state["query"],
    )
    return {
        "theory": result.theory,
        "query": result.query,
        "ledger": ledger,
        "pending": pending,
        "draft": None,
        "halt": result.reason == "hypotheses_forbidden",
    }


def explain_node(state: ReasoningState, deps: GraphDeps) -> dict:
    theory, query = state.get("theory"), state.get("query")
    verdict, ledger = state.get("verdict"), state["ledger"]
    if theory is None or query is None or verdict is None:
        return {
            "answer": Answer(value=None, strength="not_proven"),
            "explanation": Explanation(),
        }
    return {
        "answer": build_answer(theory, query, verdict, ledger, state["status"]),
        "explanation": build_explanation(theory, query, verdict, ledger),
    }


def route_after_verify(state: ReasoningState) -> str:
    return "propose" if state.get("status") == "running" else "explain"


def route_after_propose(state: ReasoningState) -> str:
    return "classify" if state.get("status") == "running" else "explain"


def route_after_stage(next_node: str):
    """Route to ``explain`` on an extraction failure, else to the next stage."""

    def route(state: ReasoningState) -> str:
        return "explain" if state.get("status") == "extraction_error" else next_node

    return route
