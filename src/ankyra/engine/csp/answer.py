"""Answer and explanation assembly for an L3 CSP decision (``docs/l3_plan.md`` §12).

The CSP answer is a multiple-choice **choice**: its ``value`` is the verified option
index and its ``strength`` is ``proven`` only when the solver decided completely. The
justification is a model-based step (a witness model, an enumerated list, or the
absence of a counter-model), never a fabricated Horn proof.
"""

from __future__ import annotations

from ankyra.core.models import Answer, Explanation, ExplanationStep
from ankyra.engine.csp.solver import CspDecision


def build_csp_answer(decision: CspDecision) -> Answer:
    """Map the decision to an ``Answer`` with an explicit choice kind and strength."""
    if decision.status == "decided":
        return Answer(value=str(decision.index), kind="choice", strength="proven")
    return Answer(value=None, kind="unknown", strength="not_proven")


def build_csp_explanation(decision: CspDecision) -> Explanation:
    """A single model-based step; no step when nothing was decided."""
    if decision.status != "decided":
        return Explanation(goal=None, steps=[], conflict=None)
    if decision.witness:
        statement = "witness model: " + ", ".join(
            f"{name}={value}" for name, value in sorted(decision.witness.items())
        )
    elif decision.complete_list:
        statement = "complete and accurate list: " + ", ".join(decision.complete_list)
    else:
        statement = "no counter-model within budget; option verified"
    index = decision.index if decision.index is not None else 0
    return Explanation(
        goal=f"option {index}",
        steps=[ExplanationStep(index=0, kind="model", statement=statement)],
    )
