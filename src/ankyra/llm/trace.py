"""Opt-in in-memory trace of LLM calls, used by the offline eval harness.

Off by default: ``invoke_as_dict``/``narrate`` record only while a ``tracing()``
context is active, so production runs pay nothing.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class LLMCall:
    label: str
    messages: list[dict[str, str]]
    schema: str | None = None
    raw: str | None = None
    parsed: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class LLMTrace:
    calls: list[LLMCall] = field(default_factory=list)

    def record(self, call: LLMCall) -> None:
        self.calls.append(call)


_current: ContextVar[LLMTrace | None] = ContextVar("ankyra_llm_trace", default=None)


def current_trace() -> LLMTrace | None:
    return _current.get()


@contextmanager
def tracing() -> Iterator[LLMTrace]:
    trace = LLMTrace()
    token = _current.set(trace)
    try:
        yield trace
    finally:
        _current.reset(token)


def serialize_messages(messages: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for message in messages:
        role = getattr(message, "type", None) or getattr(message, "role", "?")
        content = getattr(message, "content", None)
        out.append({"role": str(role), "content": str(content)})
    return out


def record_direct(
    label: str,
    messages: list[Any],
    content: str | None,
    *,
    duration_ms: float = 0.0,
    error: str | None = None,
) -> None:
    """Record a non-structured call (e.g. narration)."""
    trace = current_trace()
    if trace is None:
        return
    trace.record(
        LLMCall(
            label=label,
            messages=serialize_messages(messages),
            raw=content,
            error=error,
            duration_ms=round(duration_ms, 1),
        )
    )
