"""Public L4 entry point: capability routing + the exact solver decision (``docs/l4_plan.md`` §9).

``decide`` is the single call a product runtime or harness uses: it checks the
``ANKYRA_ARITH`` capability through :func:`ankyra.engine.inference.analyze_numeric_routing`
and either decides with the exact solver or returns an honest ``out_of_fragment``
refusal. The solver itself never reads a flag.
"""

from __future__ import annotations

from ankyra.engine.numeric.models import NumericGame, NumericQuery
from ankyra.engine.numeric.solver import DEFAULT_BUDGET, NumericDecision, NumericError, solve


def _budget() -> int:
    from ankyra.config.settings import get_setting

    value = get_setting("ARITH_BUDGET", DEFAULT_BUDGET)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_BUDGET


def decide(
    game: NumericGame,
    query: NumericQuery,
    *,
    budget: int | None = None,
) -> NumericDecision:
    """Decide a numeric query if the ``numeric`` capability is enabled, else refuse by name."""
    from ankyra.engine.inference import analyze_numeric_routing

    routing = analyze_numeric_routing(query)
    if not routing.compatible:
        return NumericDecision("out_of_fragment", detail=routing.refusal or "out_of_fragment:numeric_off")
    try:
        return solve(game, query, budget=_budget() if budget is None else budget)
    except NumericError as exc:
        return NumericDecision("out_of_fragment", detail=f"numeric_error:{exc}")
