"""OpenAI-compatible shim for running Logic-LM / LINC on the Ankyra provider.

Both frameworks were written against the legacy ``openai<1`` SDK and OpenAI's
endpoint. This module points that SDK at the same OpenAI-compatible provider the
Ankyra engine uses (``ANKYRA_API_URL`` / ``ANKYRA_API_KEY`` / ``ANKYRA_MODEL``
from ``.env``) and forces every outgoing request to the Ankyra model, whatever
model alias the framework passed for its own routing.

A transparent on-disk cache (temperature-0 requests only) avoids paying twice
while the plumbing is being tested. Disable with ``COMPARISON_NO_CACHE=1``.

Usage inside a framework process::

    from comparison.patch import install
    alias = install()          # returns the model alias to hand the framework
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = Path(os.environ.get("COMPARISON_CACHE", ROOT / "comparison" / ".cache"))


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip("'\"")
    for key in ("ANKYRA_API_URL", "ANKYRA_API_KEY", "ANKYRA_MODEL", "ANKYRA_EXTRA_BODY"):
        if os.environ.get(key):
            env[key] = os.environ[key].strip()
    return env


def _extra_body(env: dict[str, str]) -> dict:
    """Provider body options (DeepSeek thinking off), mirroring the Ankyra engine."""
    raw = os.environ.get("COMPARISON_EXTRA_BODY") or env.get("ANKYRA_EXTRA_BODY") or ""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _cache_key(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cached(cache_file: Path, payload: dict, produce):
    enabled = os.environ.get("COMPARISON_NO_CACHE") != "1"
    if not enabled:
        return produce()
    key = _cache_key(payload)
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if key in data:
            return data[key]
    result = produce()
    data = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    data[key] = result
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return result


def install(force_model: str | None = None) -> str:
    """Patch the legacy ``openai`` SDK. Returns the authoritative model id."""
    import openai  # noqa: PLC0415  (must be imported inside the framework venv)

    if not hasattr(openai, "ChatCompletion"):
        raise RuntimeError(
            "This shim targets the legacy openai<1 SDK; found "
            f"openai {getattr(openai, '__version__', '?')}"
        )

    env = _load_env()
    api_url = env["ANKYRA_API_URL"].rstrip("/")
    api_key = env["ANKYRA_API_KEY"]
    model = force_model or env["ANKYRA_MODEL"]

    openai.api_base = api_url
    openai.api_key = api_key
    extra_body = _extra_body(env)

    from openai.openai_object import OpenAIObject  # noqa: PLC0415

    def _wrap(endpoint: str, create, cache_file: Path):
        def wrapper(*args, **kwargs):
            kwargs["model"] = model
            kwargs.pop("engine", None)
            kwargs["api_key"] = api_key
            kwargs["api_base"] = api_url
            for key, value in extra_body.items():
                kwargs.setdefault(key, value)
            payload = {"endpoint": endpoint, **kwargs}
            if kwargs.get("temperature") not in (0, 0.0):
                return create(*args, **kwargs)

            result = _cached(cache_file, payload, lambda: create(*args, **kwargs))
            if isinstance(result, dict):
                return OpenAIObject.construct_from(result, api_key)
            return result

        return wrapper

    openai.ChatCompletion.create = _wrap(
        "chat", openai.ChatCompletion.create, _CACHE_DIR / "chat.json"
    )
    openai.Completion.create = _wrap(
        "completion", openai.Completion.create, _CACHE_DIR / "completion.json"
    )
    return model
