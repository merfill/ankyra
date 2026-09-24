"""LangChain LLM factories."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel

from ankyra.config.settings import settings
from ankyra.llm.providers import build_chat_model


def _extra_body() -> dict[str, Any] | None:
    """Provider body from ``ANKYRA_EXTRA_BODY`` plus an optional ``ANKYRA_SEED``.

    The seed is a reproducibility hint only; a provider that does not support it
    may ignore (or reject) the field, so it stays opt-in.
    """
    raw = settings.get("EXTRA_BODY")
    if not raw:
        body: dict[str, Any] = {}
    elif isinstance(raw, str):
        body = json.loads(raw)
    else:
        body = dict(raw)
    seed = settings.get("SEED")
    if seed is not None and str(seed).strip():
        body.setdefault("seed", int(seed))
    return body or None


def _temperature(*, role: str) -> float:
    """Extract/critic stay low; other roles follow TEMPERATURE (default 0.1).

    An explicit per-role ``0`` must win over the global default, so the unset case
    is checked with ``is None`` rather than a falsy ``or``.
    """
    if role in {"extract", "critic"}:
        raw = settings.get(f"{role.upper()}_TEMPERATURE")
        if raw is None:
            raw = settings.get("TEMPERATURE", 0.1)
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


def create_chat_llm(*, role: str = "default") -> BaseChatModel:
    """Build the chat model for ``role`` (default | extract | critic | answer).

    The provider is selected by ``ANKYRA_LLM_PROVIDER`` (default ``openai``, i.e. any
    OpenAI-compatible endpoint); the concrete class is chosen by
    ``ankyra.llm.providers`` so nothing above this factory depends on it.
    """
    model_key = "MODEL" if role == "default" else f"{role.upper()}_MODEL"
    model = settings.get(model_key) or settings.get("MODEL")
    temperature = _temperature(role=role)
    config: dict[str, Any] = {
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
        config["extra_body"] = extra
    reasoning_effort = settings.get("REASONING_EFFORT")
    if reasoning_effort:
        config["reasoning_effort"] = str(reasoning_effort)
    return build_chat_model(settings.get("LLM_PROVIDER", "openai"), config)
