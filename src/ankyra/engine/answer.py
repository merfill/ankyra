"""Answer assembly: explicit strength and hypothesis accounting."""

from __future__ import annotations

from ankyra.core.models import Answer, Query, Theory, Verdict
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.verify import winning_proof


def build_answer(
    theory: Theory,
    query: Query,
    verdict: Verdict,
    ledger: HypothesisLedger,
    status: str,
) -> Answer:
    """``proven`` uses no hypotheses; any hypothesis in the proof gives ``proven_under``."""
    if status == "refuted" and query.target is not None and any(
        gap.startswith("target_refuted:") for gap in verdict.gaps
    ):
        # The target is false: answer "no" and attribute the negative proof.
        negated_goal = query.target.model_copy(update={"negated": not query.target.negated})
        proof = winning_proof(theory, query, goal=negated_goal)
        hypotheses_used = ledger.used(proof[0], proof[1]) if proof else []
        return Answer(
            value="no" if query.answer_type == "yes_no" else None,
            strength="proven" if not hypotheses_used else "proven_under",
            hypotheses_used=hypotheses_used,
        )
    if status != "supported":
        return Answer(value=None, strength="not_proven", hypotheses_used=[])
    proof = winning_proof(theory, query)
    hypotheses_used = ledger.used(proof[0], proof[1]) if proof else []
    if query.answer_type == "yes_no":
        value: str | None = "yes"
    elif query.answer_type == "open":
        bound = ", ".join(
            f"{key}={val}" for key, val in verdict.bindings.items() if key.startswith("?")
        )
        value = bound or None
    else:
        value = None
    strength = "proven" if not hypotheses_used else "proven_under"
    return Answer(value=value, strength=strength, hypotheses_used=hypotheses_used)
