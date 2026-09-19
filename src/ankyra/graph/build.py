"""LangGraph orchestration: Phase 0 -> verify -> bounded cycle -> explain.

Edges: START -> extract_problem -> build_theory -> extract_question -> build_query
-> verify -> (propose -> classify -> verify)* -> explain -> END. Routing functions
are pure; every status is committed by a node.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

from ankyra.build.extract import extract_problem_structure, extract_question_structure
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
from ankyra.core.schemas import ProblemStructure
from ankyra.engine.nodes import (
    GraphDeps,
    build_query_node,
    build_theory_node,
    classify_node,
    explain_node,
    extract_problem_node,
    extract_question_node,
    propose_node,
    route_after_propose,
    route_after_stage,
    route_after_verify,
    verify_node,
)
from ankyra.engine.proposal import propose as propose_default
from ankyra.engine.state import ReasoningState, initial_state
from ankyra.llm.client import create_chat_llm


def build_graph(deps: GraphDeps):
    """Compile the pipeline graph with injected stages."""
    builder = StateGraph(ReasoningState)
    builder.add_node("extract_problem", lambda state: extract_problem_node(state, deps))
    builder.add_node("build_theory", lambda state: build_theory_node(state, deps))
    builder.add_node("extract_question", lambda state: extract_question_node(state, deps))
    builder.add_node("build_query", lambda state: build_query_node(state, deps))
    builder.add_node("verify", lambda state: verify_node(state, deps))
    builder.add_node("propose", lambda state: propose_node(state, deps))
    builder.add_node("classify", lambda state: classify_node(state, deps))
    builder.add_node("explain", lambda state: explain_node(state, deps))

    builder.add_edge(START, "extract_problem")
    builder.add_conditional_edges(
        "extract_problem",
        route_after_stage("build_theory"),
        {"explain": "explain", "build_theory": "build_theory"},
    )
    builder.add_edge("build_theory", "extract_question")
    builder.add_conditional_edges(
        "extract_question",
        route_after_stage("build_query"),
        {"explain": "explain", "build_query": "build_query"},
    )
    builder.add_edge("build_query", "verify")
    builder.add_conditional_edges(
        "verify", route_after_verify, {"propose": "propose", "explain": "explain"}
    )
    builder.add_conditional_edges(
        "propose", route_after_propose, {"classify": "classify", "explain": "explain"}
    )
    builder.add_edge("classify", "verify")
    builder.add_edge("explain", END)
    return builder.compile()


@dataclass
class ProblemResult:
    structure: ProblemStructure | None
    theory: Theory | None
    query: Query | None
    verdict: Verdict | None
    answer: Answer | None
    explanation: Explanation | None
    status: str
    history: list[WaveRecord]
    hypotheses: list[Hypothesis]
    revisions: list[Revision]


def run_problem(
    problem_text: str,
    *,
    llm: Any = None,
    llm_propose: Any = None,
    propose_fn: Any = None,
    allow_hypotheses: bool | None = None,
    max_waves: int | None = None,
) -> ProblemResult:
    """Run the full pipeline end to end on a natural-language problem."""
    if allow_hypotheses is None:
        allow_hypotheses = bool(settings.get("ALLOW_HYPOTHESES", True))
    if max_waves is None:
        max_waves = int(settings.get("MAX_WAVES", 8))

    extractor = llm or create_chat_llm(role="extract")
    proposer = llm_propose or llm or create_chat_llm(role="answer")
    deps = GraphDeps(
        extract_problem=lambda text: extract_problem_structure(extractor, text=text),
        extract_question=lambda question, theory, source: extract_question_structure(
            extractor, question=question, theory=theory, source_text=source
        ),
        propose=propose_fn or (lambda ctx: propose_default(proposer, ctx)),
    )

    final = build_graph(deps).invoke(
        initial_state(
            problem_text=problem_text,
            allow_hypotheses=allow_hypotheses,
            max_waves=max_waves,
        )
    )
    return ProblemResult(
        structure=final.get("structure"),
        theory=final.get("theory"),
        query=final.get("query"),
        verdict=final.get("verdict"),
        answer=final.get("answer"),
        explanation=final.get("explanation"),
        status=final.get("status", ""),
        history=list(final.get("history") or []),
        hypotheses=list(final.get("hypotheses") or []),
        revisions=list(final.get("revisions") or []),
    )
