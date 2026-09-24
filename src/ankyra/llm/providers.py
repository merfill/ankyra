"""Provider-agnostic chat-model factory.

Every provider is built behind the common LangChain ``BaseChatModel`` interface, so
the rest of Ankyra never depends on a concrete provider class. Only OpenAI-compatible
endpoints are registered for now (OpenAI, RouterAI, DeepSeek, OpenRouter, vLLM,
Ollama's OpenAI API, ...); a genuinely different SDK is added by registering a builder
here, without touching the engine or the extractors.
"""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

ChatConfig = dict[str, Any]
ProviderBuilder = Callable[[ChatConfig], BaseChatModel]


def _build_openai_compatible(config: ChatConfig) -> BaseChatModel:
    """Any provider exposing an OpenAI-compatible chat-completions API."""
    return ChatOpenAI(**config)


PROVIDERS: dict[str, ProviderBuilder] = {
    "openai": _build_openai_compatible,
}


def available_providers() -> list[str]:
    return sorted(PROVIDERS)


def build_chat_model(provider: str | None, config: ChatConfig) -> BaseChatModel:
    """Build a chat model for ``provider`` from an already-resolved ``config``.

    An unknown provider is a configuration error, never a silent fallback.
    """
    key = str(provider or "openai").strip().casefold()
    builder = PROVIDERS.get(key)
    if builder is None:
        raise ValueError(
            f"Unknown LLM provider {provider!r}; available: {', '.join(available_providers())}"
        )
    return builder(config)
