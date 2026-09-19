"""Tests for LLM client plumbing (extra body / seed); no network."""

from __future__ import annotations

from ankyra.config.settings import settings
from ankyra.llm.client import _extra_body, _temperature


def _restore(name: str, value) -> None:
    settings.set(name, value)


def test_per_role_zero_temperature_is_honoured():
    previous = {name: settings.get(name) for name in ("EXTRACT_TEMPERATURE", "TEMPERATURE")}
    settings.set("TEMPERATURE", 0.1)
    settings.set("EXTRACT_TEMPERATURE", 0)
    try:
        assert _temperature(role="extract") == 0.0
    finally:
        for name, value in previous.items():
            _restore(name, value)


def test_temperature_falls_back_to_the_global_default():
    previous = {name: settings.get(name) for name in ("EXTRACT_TEMPERATURE", "TEMPERATURE")}
    settings.set("EXTRACT_TEMPERATURE", None)
    settings.set("TEMPERATURE", 0.3)
    try:
        assert _temperature(role="extract") == 0.3
    finally:
        for name, value in previous.items():
            _restore(name, value)


def test_seed_is_merged_into_extra_body():
    previous = {name: settings.get(name) for name in ("EXTRA_BODY", "SEED")}
    settings.set("EXTRA_BODY", {"thinking": False})
    settings.set("SEED", 7)
    try:
        assert _extra_body() == {"thinking": False, "seed": 7}
    finally:
        for name, value in previous.items():
            _restore(name, value)


def test_seed_alone_creates_an_extra_body():
    previous = {name: settings.get(name) for name in ("EXTRA_BODY", "SEED")}
    settings.set("EXTRA_BODY", None)
    settings.set("SEED", "11")
    try:
        assert _extra_body() == {"seed": 11}
    finally:
        for name, value in previous.items():
            _restore(name, value)


def test_extra_body_can_be_a_json_string():
    previous = {name: settings.get(name) for name in ("EXTRA_BODY", "SEED")}
    settings.set("EXTRA_BODY", '{"thinking": true}')
    settings.set("SEED", None)
    try:
        assert _extra_body() == {"thinking": True}
    finally:
        for name, value in previous.items():
            _restore(name, value)
