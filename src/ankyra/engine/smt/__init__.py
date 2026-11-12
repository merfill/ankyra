"""The SMT engine (Z3-backed) — optional, lazily imported.

This package is the single import boundary for Z3. Nothing here is imported at
``ankyra.engine`` import time: call :func:`require_z3` (directly or via a later
solver module) to load ``z3`` on demand. Z3 lives in the optional ``smt`` extra
(``uv sync --extra smt``), so the base install and the offline test suite keep
working without it.
"""


def __getattr__(name: str):
    """Expose the solver modules as attributes without importing them eagerly."""
    if name in _LAZY_MODULES:
        from importlib import import_module

        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_LAZY_MODULES = frozenset({"prove"})


def require_z3():
    """Import and return the ``z3`` module, or fail with an install hint."""
    try:
        import z3
    except ImportError as exc:
        raise ImportError(
            "The Z3 solver is not installed. Z3 is an optional dependency; "
            "install it with: uv sync --extra smt"
        ) from exc
    return z3


__all__ = ["require_z3"]
