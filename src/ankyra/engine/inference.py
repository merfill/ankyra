"""Pluggable inference semantics seam (``docs/logic_layer.md``).

Policy and mechanics stay where they are; only the **semantics** — entailment, the
shape of a verdict, and the closure a proposal is classified against — is pluggable.
Two implementations exist today:

* :class:`HornInference` — monotonic Horn/L1 forward chaining (the default);
* :class:`ClausalInference` — the L2 ground-clause resolution procedure.

The module is deliberately thin: the concrete procedures live in ``engine.horn`` /
``engine.resolution`` and the verdict assembly in ``engine.verify``, so extracting the
seam does not duplicate logic. ``select_inference`` is called by ``verify`` (the policy
of *which* semantics runs stays there); ``classify`` uses the Horn closure.
"""

from __future__ import annotations

from typing import Protocol

from ankyra.core.models import FactKey, Query, Theory, Verdict


class Inference(Protocol):
    """The varying part of a logic: entailment and a query verdict."""

    name: str
    supports_proposals: bool

    def entails(self, theory: Theory, literal: FactKey) -> bool: ...

    def closure_keys(self, theory: Theory) -> set[FactKey]: ...

    def decide(self, theory: Theory, query: Query) -> Verdict: ...


class HornInference:
    """Monotonic Horn/L1 semantics: the forward-chaining closure."""

    name = "horn"
    supports_proposals = True

    def entails(self, theory: Theory, literal: FactKey) -> bool:
        from ankyra.engine.horn import derive_store

        return derive_store(theory).get(literal) is not None

    def closure_keys(self, theory: Theory) -> set[FactKey]:
        from ankyra.engine.horn import derive_store

        return {fact.key for fact in derive_store(theory).facts}

    def decide(self, theory: Theory, query: Query) -> Verdict:
        from ankyra.engine.horn import build_context
        from ankyra.engine.verify import _verify_horn

        return _verify_horn(theory, query, build_context(theory))


class ClausalInference:
    """L2 semantics: ground-clause resolution (quantifiers by clausification)."""

    name = "clausal"
    supports_proposals = False

    def entails(self, theory: Theory, literal: FactKey) -> bool:
        from ankyra.engine.resolution import prove

        return prove(theory, literal, budget=_logic_budget()).status == "entailed"

    def closure_keys(self, theory: Theory) -> set[FactKey]:
        # L2 is not propositionalized into a fact set; proposals are unsupported
        # (D-L2-6), so classification must not use it.
        raise NotImplementedError("L2 has no fact closure; proposals are unsupported")

    def decide(self, theory: Theory, query: Query) -> Verdict:
        from ankyra.engine.horn import build_context
        from ankyra.engine.verify import _verify_l2

        return _verify_l2(theory, query, build_context(theory))


def _logic_budget() -> int:
    from ankyra.config.settings import get_setting
    from ankyra.engine.resolution import DEFAULT_BUDGET

    value = get_setting("LOGIC_BUDGET", DEFAULT_BUDGET)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_BUDGET


def select_inference(*, logic_enabled: bool, has_goals: bool) -> Inference:
    """Choose the semantics: L2 when enabled and a target exists, else Horn.

    This is policy (config + query shape), so it stays at the call site rather than in
    the semantics objects themselves.
    """
    if logic_enabled and has_goals:
        return ClausalInference()
    return HornInference()
