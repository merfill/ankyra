"""Answer and explanation assembly for an L4 numeric decision (``docs/l4_plan.md`` §12).

The numeric answer is a **number**: its ``value`` is the exact value and its
``strength`` is ``proven`` only when the target is uniquely determined. The
justification is an evaluation step (the target and its exact value), never a
fabricated Horn proof.
"""

from __future__ import annotations

from ankyra.core.models import Answer, Explanation, ExplanationStep
from ankyra.engine.numeric.solver import NumericDecision


def build_numeric_answer(decision: NumericDecision) -> Answer:
    """Map the decision to an ``Answer`` with an explicit number kind and strength."""
    if decision.status == "determined":
        return Answer(value=str(decision.value), kind="number", strength="proven")
    return Answer(value=None, kind="unknown", strength="not_proven")


def build_numeric_explanation(decision: NumericDecision) -> Explanation:
    """A single evaluation step; no step when the target is not determined."""
    if decision.status != "determined":
        return Explanation(goal=None, steps=[], conflict=None)
    return Explanation(
        goal=f"value {decision.value}",
        steps=[
            ExplanationStep(
                index=0,
                kind="numeric",
                statement=f"the target is determined: {decision.value}",
            )
        ],
    )
