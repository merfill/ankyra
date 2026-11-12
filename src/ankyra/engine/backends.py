"""Selection of the L2 clause-decision backend.

The L2 procedure has two interchangeable implementations with the same contract
(``refute`` / ``refute_support`` / ``refute_conjunction`` returning a
:class:`ankyra.engine.resolution.ProverResult`): the in-repo bounded resolution
engine and the optional Z3/SMT engine. The run picks one with the ``L2_BACKEND``
setting (env ``ANKYRA_L2_BACKEND``), read through
:func:`ankyra.config.settings.get_setting`, so ``setting_overrides`` isolates the
choice per eval run. The accepted spellings are ``resolution`` and ``smt``
(:data:`L2_BACKENDS`); the value is stripped and lower-cased. Without the setting
the default is ``resolution``.

``resolution`` is imported statically. ``smt`` is imported lazily inside the
selection functions, because it lives behind the optional ``smt`` extra
(``uv sync --extra smt``): a base install never needs Z3, and importing this
module does not import the SMT package or ``z3``.

An unknown value is an explicit refusal (``out_of_fragment:l2_backend_unknown``),
never a silent fallback to ``resolution``. A selected ``smt`` backend whose Z3
dependency is missing is refused with ``out_of_fragment:l2_backend_unavailable``
instead of surfacing the :class:`ImportError`. Both refusals are carried on the
:attr:`BackendResult.refusal` field, the same gap-code form that
:class:`ankyra.engine.inference.RoutingDecision` uses, so a caller can pass it
straight into ``Verdict(status="out_of_fragment", gaps=[...], shelf="refused")``.

The SMT backend records no resolution DAG, so for it ``ProverResult.proof`` is
always ``None``. Consequently ``_unused_l2`` in ``engine.verify`` (which returns
early when ``proof is None``) cannot find unused premises under ``smt``, and a
goal whose proof does not rest on all of the query conditions can be reported as
``supported`` instead of ``insufficient``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ankyra.config.settings import get_setting
from ankyra.engine import resolution
from ankyra.engine.clause import Clausification, Literal
from ankyra.engine.resolution import DEFAULT_BUDGET, ProverResult

# The accepted values of the L2_BACKEND setting.
L2_BACKENDS = frozenset({"resolution", "smt"})
BACKENDS = L2_BACKENDS

DEFAULT_L2_BACKEND = "resolution"

L2_BACKEND_UNKNOWN = "out_of_fragment:l2_backend_unknown"
L2_BACKEND_UNAVAILABLE = "out_of_fragment:l2_backend_unavailable"

__all__ = [
    "BACKENDS",
    "BackendDecision",
    "BackendResult",
    "DEFAULT_L2_BACKEND",
    "L2_BACKENDS",
    "L2_BACKEND_UNAVAILABLE",
    "L2_BACKEND_UNKNOWN",
    "refute",
    "refute_conjunction",
    "refute_support",
    "select_backend",
]


@dataclass(frozen=True)
class BackendDecision:
    """The selected L2 backend, or why no backend can be used.

    ``refusal`` is the ``out_of_fragment`` gap code when the requested backend is
    unknown or unavailable, and ``None`` when the choice is usable. The shape
    mirrors :class:`ankyra.engine.inference.RoutingDecision`, so a refusal is
    never mistaken for a (silent) downgrade.
    """

    backend: str
    refusal: str | None
    reasons: tuple[str, ...]

    @property
    def name(self) -> str:
        return self.backend

    @property
    def procedure(self) -> str:
        return self.backend

    @property
    def compatible(self) -> bool:
        return self.refusal is None


@dataclass
class BackendResult(ProverResult):
    """A :class:`ProverResult` that may also carry a backend refusal code.

    It is a ``ProverResult`` (same fields and meaning), with one extra optional
    field: ``refusal`` holds the ``out_of_fragment`` gap when the backend could
    not run at all. A refused call is ``status="unsupported"`` with ``proof=None``
    and ``steps=0`` — no procedure was consulted.
    """

    refusal: str | None = None


def _requested_backend() -> str:
    """Read and normalise the ``L2_BACKEND`` setting."""
    value: Any = get_setting("L2_BACKEND", DEFAULT_L2_BACKEND)
    return str(value).strip().lower()


def _z3_available() -> bool:
    """Whether the optional SMT backend can import its solver."""
    try:
        from ankyra.engine import smt

        smt.require_z3()
    except ImportError:
        return False
    return True


def select_backend() -> BackendDecision:
    """Resolve ``L2_BACKEND`` to a backend decision, without deciding anything.

    An unknown value is refused with ``out_of_fragment:l2_backend_unknown``; a
    valid ``smt`` choice whose solver is not installed is refused with
    ``out_of_fragment:l2_backend_unavailable``. The SMT package is imported only
    here (and only for the ``smt`` choice), never at module import time.
    """
    backend = _requested_backend()
    if backend not in L2_BACKENDS:
        return BackendDecision(backend, L2_BACKEND_UNKNOWN, (backend, L2_BACKEND_UNKNOWN))
    if backend == "smt" and not _z3_available():
        return BackendDecision(backend, L2_BACKEND_UNAVAILABLE, (backend, L2_BACKEND_UNAVAILABLE))
    return BackendDecision(backend, None, (backend,))


def _refusal(decision: BackendDecision, budget: int) -> BackendResult:
    assert decision.refusal is not None
    return BackendResult(
        status="unsupported", proof=None, steps=0, budget=budget, refusal=decision.refusal
    )


def _prover(decision: BackendDecision):
    """Return the module implementing the selected backend's contract."""
    if decision.backend == "resolution":
        return resolution

    from ankyra.engine import smt

    return smt.prove


def refute(
    clausification: Clausification, goal: Literal, *, budget: int = DEFAULT_BUDGET
) -> ProverResult:
    """Refute ``¬goal`` with the selected L2 backend."""
    decision = select_backend()
    if decision.refusal is not None:
        return _refusal(decision, budget)
    return _prover(decision).refute(clausification, goal, budget=budget)


def refute_support(
    clausification: Clausification,
    assumed: list,
    *,
    budget: int = DEFAULT_BUDGET,
) -> ProverResult:
    """Refute a set of assumed clauses with the selected L2 backend."""
    decision = select_backend()
    if decision.refusal is not None:
        return _refusal(decision, budget)
    return _prover(decision).refute_support(clausification, assumed, budget=budget)


def refute_conjunction(
    clausification: Clausification, literals: list[Literal], *, budget: int = DEFAULT_BUDGET
) -> ProverResult:
    """Refute the conjunction of ``literals`` with the selected L2 backend."""
    decision = select_backend()
    if decision.refusal is not None:
        return _refusal(decision, budget)
    return _prover(decision).refute_conjunction(clausification, literals, budget=budget)
