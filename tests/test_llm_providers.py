"""Tests for the provider-agnostic LLM factory; no network."""

from __future__ import annotations

import pytest

from ankyra.config.settings import settings
from ankyra.llm import client, providers


class _FakeChat:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_available_providers_includes_openai():
    assert "openai" in providers.available_providers()


def test_build_chat_model_dispatches_to_openai(monkeypatch):
    monkeypatch.setattr(providers, "ChatOpenAI", _FakeChat)
    model = providers.build_chat_model("openai", {"model": "m", "temperature": 0.2})
    assert isinstance(model, _FakeChat)
    assert model.kwargs == {"model": "m", "temperature": 0.2}


def test_build_chat_model_defaults_to_openai(monkeypatch):
    monkeypatch.setattr(providers, "ChatOpenAI", _FakeChat)
    assert isinstance(providers.build_chat_model(None, {"model": "m"}), _FakeChat)


def test_unknown_provider_is_refused():
    with pytest.raises(ValueError, match="available"):
        providers.build_chat_model("bogus", {})


def test_create_chat_llm_uses_the_configured_provider(monkeypatch):
    captured: dict = {}

    def fake_build(provider, config):
        captured["provider"] = provider
        captured["config"] = config
        return "MODEL"

    monkeypatch.setattr(client, "build_chat_model", fake_build)
    names = ("LLM_PROVIDER", "MODEL", "API_URL", "API_KEY", "TEMPERATURE")
    previous = {name: settings.get(name) for name in names}
    settings.set("LLM_PROVIDER", "openai")
    settings.set("MODEL", "test-model")
    settings.set("API_URL", "http://example.invalid/v1")
    settings.set("API_KEY", "test-key")
    settings.set("TEMPERATURE", 0.1)
    try:
        result = client.create_chat_llm(role="extract")
    finally:
        for name, value in previous.items():
            settings.set(name, value)
    assert result == "MODEL"
    assert captured["provider"] == "openai"
    assert captured["config"]["model"] == "test-model"
    assert captured["config"]["base_url"] == "http://example.invalid/v1"
