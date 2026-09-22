"""Public L3 entry point: capability routing + the solver decision (``docs/l3_plan.md`` §9).

``decide`` is the single call a product runtime or harness uses: it checks the
``ANKYRA_CSP`` capability through :func:`ankyra.engine.inference.analyze_csp_routing`
and either decides with the finite-domain solver or returns an honest
``out_of_fragment`` refusal. The solver itself never reads a flag.
"""

from __future__ import annotations

from ankyra.engine.csp.models import CspGame, CspQuestion
from ankyra.engine.csp.solver import DEFAULT_BUDGET, CspDecision, decide_question


def _budget() -> int:
    from ankyra.config.settings import get_setting

    value = get_setting("CSP_BUDGET", DEFAULT_BUDGET)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_BUDGET


def decide(
    game: CspGame,
    question: CspQuestion,
    *,
    budget: int | None = None,
) -> CspDecision:
    """Decide a CSP question if the ``csp`` capability is enabled, else refuse by name."""
    from ankyra.engine.inference import analyze_csp_routing

    routing = analyze_csp_routing(question)
    if not routing.compatible:
        return CspDecision("out_of_fragment", detail=routing.refusal or "out_of_fragment:csp_off")
    return decide_question(game, question, budget=_budget() if budget is None else budget)
