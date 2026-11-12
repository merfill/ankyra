"""Dynaconf settings for Ankyra."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

from dynaconf import Dynaconf

PROJECT_ROOT = Path(__file__).resolve().parents[3]

settings = Dynaconf(
    envvar_prefix="ANKYRA",
    load_dotenv=True,
    dotenv_path=PROJECT_ROOT / ".env",
    root_path=PROJECT_ROOT,
)

_overrides: ContextVar[dict[str, Any]] = ContextVar("ankyra_setting_overrides", default={})

# Dynaconf only parses a lower-case subset of env strings ("true"/"false"/"0"/"1"),
# so ANKYRA_CSP=off arrives as the string "off" and bool() at the call sites reads
# it as enabled. Flag spellings are normalised here, in one place.
_BOOL_SPELLINGS = {
    "true": True,
    "yes": True,
    "on": True,
    "false": False,
    "no": False,
    "off": False,
}


def _as_flag(value: Any) -> Any:
    """Normalise an env-provided flag value to a real bool when it spells one."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _BOOL_SPELLINGS:
            return _BOOL_SPELLINGS[text]
    return value


def get_setting(key: str, default: Any = None) -> Any:
    """Read a setting, honouring the current context's overrides.

    ``setting_overrides`` installs per-run values (``BUILTINS`` / ``DEFEASIBLE``)
    in a ``ContextVar`` instead of mutating the global singleton, so concurrent
    eval runs on threads cannot observe each other's flags.
    """
    overrides = _overrides.get()
    if key in overrides:
        value = overrides[key]
    else:
        value = settings.get(key, default)
    return _as_flag(value) if isinstance(default, bool) else value


@contextmanager
def setting_overrides(**values: Any) -> Iterator[None]:
    """Apply ``values`` for the duration of the context, isolated per thread/task."""
    token = _overrides.set({**_overrides.get(), **values})
    try:
        yield
    finally:
        _overrides.reset(token)
