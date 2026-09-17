"""LangChain LLM factories."""

from __future__ import annotations

import json
from typing import Any

from langchain_openai import ChatOpenAI

from ankyra.config.settings import settings


def _extra_body() -> dict[str, Any] | None:
    raw = settings.get("EXTRA_BODY")
    if not raw:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


def _temperature(*, role: str) -> float:
    """Extract/critic stay low; other roles follow TEMPERATURE (default 0.1)."""
    if role in {"extract", "critic"}:
        raw = settings.get(f"{role.upper()}_TEMPERATURE") or settings.get("TEMPERATURE", 0.1)
    else:
        raw = settings.get("TEMPERATURE", 0.1)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.1


def extract_max_tokens(text: str) -> int:
    """Completion cap for ontology extract: scale with source length, never below MAX_TOKENS."""
    base = int(settings.get("MAX_TOKENS", 4096))
    ceiling = int(settings.get("MAX_TOKENS_EXTRACT", 32768))
    # Russian source is ~2–3 chars/token; quoted JSON is often as large as the source.
    need = max(base, len(text.strip()) // 2)
    return min(need, max(base, ceiling))


def with_max_tokens(llm: Any, n: int) -> Any:
    """Return a copy of ``llm`` with a higher completion cap. No-op if it cannot copy."""
    current = getattr(llm, "max_tokens", None)
    try:
        if current is not None and int(current) >= n:
            return llm
    except (TypeError, ValueError):
        pass
    copier = getattr(llm, "model_copy", None)
    if callable(copier):
        try:
            return copier(update={"max_tokens": n})
        except Exception:
            return llm
    return llm


def with_temperature(llm: Any, temperature: float) -> Any:
    """Return a copy of ``llm`` with a lower sampling temperature. No-op if it cannot copy."""
    update: dict[str, Any] = {"temperature": temperature}
    extra = getattr(llm, "extra_body", None)
    if isinstance(extra, dict):
        eb = dict(extra)
        eb["temperature"] = temperature
        update["extra_body"] = eb
    copier = getattr(llm, "model_copy", None)
    if callable(copier):
        try:
            return copier(update=update)
        except Exception:
            return llm
    binder = getattr(llm, "bind", None)
    if callable(binder):
        try:
            return binder(temperature=temperature)
        except Exception:
            return llm
    return llm


def create_chat_llm(*, role: str = "default") -> ChatOpenAI:
    """role: default | extract | critic | answer — picks MODEL or {ROLE}_MODEL."""
    model_key = "MODEL" if role == "default" else f"{role.upper()}_MODEL"
    model = settings.get(model_key) or settings.get("MODEL")
    temperature = _temperature(role=role)
    kwargs: dict[str, Any] = {
        "base_url": settings.get("API_URL"),
        "api_key": settings.get("API_KEY"),
        "model": model,
        "temperature": temperature,
        "max_tokens": int(settings.get("MAX_TOKENS", 4096)),
    }
    extra = _extra_body()
    if extra:
        extra = dict(extra)
        extra.setdefault("temperature", temperature)
        kwargs["extra_body"] = extra
    reasoning_effort = settings.get("REASONING_EFFORT")
    if reasoning_effort:
        kwargs["reasoning_effort"] = str(reasoning_effort)
    return ChatOpenAI(**kwargs)
