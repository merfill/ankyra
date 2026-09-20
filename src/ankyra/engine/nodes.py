"""Pipeline nodes: one step each, plus pure routers.

Nodes are plain functions over ``ReasoningState`` that take injected ``GraphDeps``
(so the pipeline is testable without an LLM). ``ankyra.graph.build`` binds them
into a ``StateGraph``; ``run_cycle`` drives the same functions linearly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ankyra.build.pipeline import build_query, build_theory
from ankyra.core.models import (
    Answer,
    Explanation,
    Query,
    Revision,
    RevisionTrigger,
    Theory,
    WaveRecord,
)
from ankyra.core.schemas import ProblemStructure, QuestionStructure
from ankyra.engine.answer import build_answer, refutation_is_hypothetical
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
    theory = state.get("theory")
    return {
        "query": build_query(
            state["question"],
            domain=theory.domain if theory else None,
            world_assumption=state.get("world_assumption", "open"),
        )
    }


_REVISION_TRIGGERS: dict[str, RevisionTrigger] = {
    "cited": "new_cited_fact",
    "hypothesis": "new_hypothesis",
}


def _revision(
    previous: Answer | None, current: Answer, pending: PendingWave | None
) -> Revision | None:
    """An answer change caused by the wave that just completed, if any.

    ``None`` when there is no prior answer or it is unchanged; the trigger names
    the accepted proposal that caused the change. Wave 0 has no prior answer, so
    the first answer (even when terminal) is not itself a revision.
    """
    if previous is None or previous == current:
        return None
    trigger: RevisionTrigger = _REVISION_TRIGGERS.get(
        pending.category if pending is not None else "", "answer_change"
    )
    source_ids = [pending.hypothesis.id] if pending is not None and pending.hypothesis else []
    return Revision(
        wave=pending.wave if pending is not None else 0,
        trigger=trigger,
        previous=previous,
        current=current,
        source_ids=source_ids,
    )


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

    if verdict.status in {"supported", "refuted", "contradiction", "insufficient", "out_of_fragment"}:
        status = verdict.status
    elif any(gap.startswith("undecided_conflict:") for gap in verdict.gaps):
        # A conflict specificity cannot decide is a definitive answer (unknown),
        # not a reason to keep proposing: stop with the honest verdict.
        status = "unsupported"
    elif state.get("halt"):
        status = "unsupported"
    elif stuck >= 2:
        status = "no_progress"
    elif wave >= state.get("max_waves", 0):
        status = "budget"
    else:
        status = "running"

    if status == "refuted" and query.target is not None and refutation_is_hypothetical(
        theory, query, state["ledger"]
    ):
        # A hypothesis cannot refute a target: assuming the counter-fact only makes
        # the answer hold under that assumption, so report the honest unknown.
        verdict = verdict.model_copy(
            update={
                "status": "unsupported",
                "shelf": "attested",
                "gaps": [
                    *(g for g in verdict.gaps if not g.startswith("target_refuted:")),
                    f"hypothetical_refutation:{query.target.predicate}",
                ],
            }
        )
        status = "unsupported"
        update["verdict"] = verdict
    update["status"] = status

    current_answer = build_answer(theory, query, verdict, state["ledger"], status)
    update["last_answer"] = current_answer
    revision = _revision(state.get("last_answer"), current_answer, pending)
    if revision is not None:
        update["revisions"] = [revision]
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
        history=list(state.get("history") or []),
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
    structure = state.get("structure")
    result = classify(
        draft,
        state["theory"],
        state["query"],
        ledger,
        source_text=state["theory"].source_text,
        allow_hypotheses=state["allow_hypotheses"],
        wave=state["wave"],
        question_text=structure.question if structure is not None else "",
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
    explanation = build_explanation(theory, query, verdict, ledger)
    revisions = list(state.get("revisions") or [])
    if revisions:
        explanation = explanation.model_copy(update={"revisions": revisions})
    return {
        "answer": build_answer(theory, query, verdict, ledger, state["status"]),
        "explanation": explanation,
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
