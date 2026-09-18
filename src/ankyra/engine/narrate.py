"""Optional LLM narration of a finished explanation (paraphrase only)."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ankyra.config.settings import settings
from ankyra.core.models import Answer, Explanation
from ankyra.engine.answer import render_answer
from ankyra.llm import trace as llm_trace

NARRATE_SYSTEM = """You rewrite a finished formal derivation as short natural-language prose.
You may ONLY paraphrase the steps you are given. Do not add, drop or change any
fact, rule, binding, quote or hypothesis, and do not draw new conclusions. Translate
predicate and object ids into natural language. Keep hypothesis tags visible.
If a conflict is present, do not pick a side yourself: the trace already says which
branch (if any) the engine selected and why. When the conflict is undecided, state
plainly that it could not be resolved. If a direct answer is given, start your prose
with it and never contradict it. Return plain text, no markdown, no JSON."""


def _render(explanation: Explanation, answer: Answer | None = None, language: str | None = None) -> str:
    lines = []
    if answer is not None:
        lines.append(render_answer(answer, language))
    lines.append(f"Goal: {explanation.goal or '(none)'}")
    if explanation.hypotheses_used:
        lines.append(f"Depends on hypotheses: {', '.join(explanation.hypotheses_used)}")
    for step in explanation.steps:
        detail = f"{step.index}. [{step.kind}] {step.statement}"
        if step.premises:
            detail += f"  <- steps {step.premises}"
        if step.source:
            detail += f"  [{step.source}]"
        if step.quote:
            detail += f'  quote="{step.quote}"'
        lines.append(detail)
        if step.rule:
            lines.append(f"      rule {step.rule_index}: {step.rule}")
    if explanation.conflict is not None:
        conflict = explanation.conflict
        detail = f"Conflict: {conflict.kind}, {conflict.status}, defeated={conflict.defeated}."
        if conflict.reason:
            detail += f" Reason: {conflict.reason}."
        if conflict.note:
            detail += f" {conflict.note}"
        lines.append(detail)
        for label, branch in (("supporting", conflict.supporting), ("attacking", conflict.attacking)):
            lines.append(f"  {label}:")
            for step in branch:
                lines.append(f"    {step.index}. [{step.kind}] {step.statement}")
    return "\n".join(lines)


def narrate_explanation(
    llm: Any,
    explanation: Explanation,
    *,
    answer: Answer | None = None,
    language: str | None = None,
) -> str:
    """Return a prose paraphrase of a finished derivation; introduces no facts."""
    lang = language or str(settings.get("LANG", "en"))
    messages = [
        SystemMessage(content=NARRATE_SYSTEM + f"\nWrite the narration in this language: {lang}."),
        HumanMessage(
            content="Derivation steps:\n"
            + _render(explanation, answer, lang)
            + "\n\nRewrite as prose."
        ),
    ]
    started = time.perf_counter()
    try:
        response = llm.invoke(messages)
    except Exception as exc:
        llm_trace.record_direct(
            "narrate",
            messages,
            None,
            duration_ms=(time.perf_counter() - started) * 1000,
            error=str(exc),
        )
        raise
    content = str(getattr(response, "content", None) or response)
    llm_trace.record_direct(
        "narrate", messages, content, duration_ms=(time.perf_counter() - started) * 1000
    )
    return content
