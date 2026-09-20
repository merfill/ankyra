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


def get_setting(key: str, default: Any = None) -> Any:
    """Read a setting, honouring the current context's overrides.

    ``setting_overrides`` installs per-run values (``BUILTINS`` / ``DEFEASIBLE``)
    in a ``ContextVar`` instead of mutating the global singleton, so concurrent
    eval runs on threads cannot observe each other's flags.
    """
    overrides = _overrides.get()
    if key in overrides:
        return overrides[key]
    return settings.get(key, default)


@contextmanager
def setting_overrides(**values: Any) -> Iterator[None]:
    """Apply ``values`` for the duration of the context, isolated per thread/task."""
    token = _overrides.set({**_overrides.get(), **values})
    try:
        yield
    finally:
        _overrides.reset(token)
