"""Structured LLM JSON: tool_calling first, json_object + manual parse on failure.

Fallback chain: function_calling → plain JSON → JsonOutputParser.
Every call is recorded into the active ``ankyra.llm.trace`` (if any).
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel

from ankyra.config.settings import settings
from ankyra.llm import trace as llm_trace
from ankyra.llm.client import with_max_tokens

logger = logging.getLogger(__name__)

_COMPLETION_TOKENS_RE = re.compile(r"completion_tokens\s*=\s*(\d+)", re.I)
# Length-limit retries: a truncation is usually a verbose provider replica, so a
# fresh call often lands on a compact one. Keep the budget low; chunks are small.
_MAX_LENGTH_BUMPS = 2


def invoke_as_dict(
    llm: Any,
    messages: list[Any],
    *,
    schema: type[BaseModel] | None = None,
    label: str | None = None,
    _token_bumps: int = 0,
) -> dict[str, Any]:
    """Return a JSON object from the model.

    1. ``with_structured_output(..., method="function_calling")`` when schema is set.
    2. On a tool-calling error, retry ``response_format=json_object``.
    3. If json_object is unsupported, plain ``invoke``.
    On a completion length cap, raise the cap once and retry the same call.
    Do not fall through to plain invoke: truncated JSON will not parse.
    """
    started = time.perf_counter()
    try:
        data, raw = _invoke_as_dict_once(llm, messages, schema=schema)
    except Exception as exc:
        _record(label, messages, schema, None, None, str(exc), started)
        if not _is_length_limit(exc) or _token_bumps >= _MAX_LENGTH_BUMPS:
            raise
        nxt = _higher_max_tokens(llm, exc)
        if nxt is None:
            raise
        bumped = with_max_tokens(llm, nxt)
        if bumped is llm:
            raise
        logger.warning("length cap; retry max_tokens=%s", nxt)
        return invoke_as_dict(
            bumped, messages, schema=schema, label=label, _token_bumps=_token_bumps + 1
        )
    _record(label, messages, schema, raw, data, None, started)
    return data


def _record(
    label: str | None,
    messages: list[Any],
    schema: type[BaseModel] | None,
    raw: str | None,
    parsed: dict[str, Any] | None,
    error: str | None,
    started: float,
) -> None:
    trace = llm_trace.current_trace()
    if trace is None:
        return
    trace.record(
        llm_trace.LLMCall(
            label=label or "llm",
            messages=llm_trace.serialize_messages(messages),
            schema=getattr(schema, "__name__", None) if schema is not None else None,
            raw=raw,
            parsed=parsed,
            error=error,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
    )


def _invoke_as_dict_once(
    llm: Any,
    messages: list[Any],
    *,
    schema: type[BaseModel] | None,
) -> tuple[dict[str, Any], str | None]:
    if schema is not None and hasattr(llm, "with_structured_output"):
        try:
            structured = llm.with_structured_output(
                schema, method="function_calling", include_raw=True
            )
            result = structured.invoke(messages)
            if isinstance(result, dict) and "parsed" in result:
                # langchain include_raw wrapper: reuse the raw text when the
                # model answered in content instead of a tool call (no 2nd call).
                raw = result.get("raw")
                raw_text = str(getattr(raw, "content", None) or "")
                parsed = result.get("parsed")
                if parsed is not None and isinstance(parsed, BaseModel):
                    dumped = parsed.model_dump()
                    if dumped:
                        return dumped, raw_text
                elif isinstance(parsed, dict) and parsed:
                    return parsed, raw_text
                perr = result.get("parsing_error")
                if perr is not None and _is_length_limit(perr):
                    raise ValueError(str(perr))
                if raw_text.strip():
                    data = _parse_json_content(raw_text)
                    if isinstance(data, dict) and data:
                        return data, raw_text
                raise ValueError("structured output returned None")
            if result is not None:
                if isinstance(result, BaseModel):
                    dumped = result.model_dump()
                    if dumped:
                        return dumped, None
                elif isinstance(result, dict) and result:
                    return result, None
                raise ValueError("empty structured output")
            raise ValueError("structured output returned None")
        except Exception as exc:
            if _is_length_limit(exc):
                raise
            logger.warning("tool_calling failed (%s); retry json_object", exc)

    raw_body = _invoke_json_body(llm, messages, schema=schema)
    data = _parse_json_content(raw_body)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object, got {type(data).__name__}")
    return data, raw_body


def _is_length_limit(exc: BaseException) -> bool:
    text = str(exc).casefold()
    return "length limit" in text or "max_tokens" in text


def _completion_tokens_from_exc(exc: BaseException) -> int | None:
    match = _COMPLETION_TOKENS_RE.search(str(exc))
    return int(match.group(1)) if match else None


def _higher_max_tokens(llm: Any, exc: BaseException) -> int | None:
    current = getattr(llm, "max_tokens", None)
    try:
        current_n = int(current) if current is not None else int(settings.get("MAX_TOKENS", 4096))
    except (TypeError, ValueError):
        current_n = int(settings.get("MAX_TOKENS", 4096))
    used = _completion_tokens_from_exc(exc) or current_n
    ceiling = int(settings.get("MAX_TOKENS_EXTRACT", 32768))
    nxt = min(max(used * 2, current_n * 2), max(current_n, ceiling))
    if nxt <= current_n:
        return None
    return nxt


def _json_schema_text(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)


def _invoke_json_body(
    llm: Any, messages: list[Any], *, schema: type[BaseModel] | None = None
) -> str:
    if schema is not None:
        # Tool-calling failed: make the contract explicit in the prompt so the
        # plain JSON path sees the exact schema instead of guessing field names.
        messages = [
            *messages,
            HumanMessage(
                content=(
                    "Return ONLY a JSON object matching this schema, no markdown "
                    "fences and no extra keys:\n" + _json_schema_text(schema)
                )
            ),
        ]
    bound = llm
    try:
        if hasattr(llm, "bind"):
            bound = llm.bind(response_format={"type": "json_object"})
    except Exception as exc:
        logger.warning("json_object bind failed (%s); plain invoke", exc)
        bound = llm
    try:
        response = bound.invoke(messages)
    except Exception as exc:
        if _is_length_limit(exc):
            raise
        logger.warning("json_object invoke failed (%s); plain invoke", exc)
        response = llm.invoke(messages)
    raw = str(getattr(response, "content", None) or response)
    if not str(raw).strip():
        raise ValueError(
            "LLM returned empty JSON body (often max_tokens / reasoning limit). "
            "Raise ANKYRA_MAX_TOKENS or disable thinking in ANKYRA_EXTRA_BODY."
        )
    return raw


def _parse_json_content(raw: str) -> Any:
    try:
        return JsonOutputParser().parse(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise
