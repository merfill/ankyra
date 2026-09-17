"""Deterministic query assembly: answer type, goal-echo removal, premise slimming."""

from __future__ import annotations

from ankyra.build.normalize import is_var, predicate_polarity
from ankyra.core.models import AnswerType, Morphism, Query, Theory
from ankyra.engine.verify import verify


def derive_answer_type(target: Morphism | None, variables: dict[str, str]) -> AnswerType:
    """``instruction`` when there is no target, ``open`` when it has an unknown."""
    if target is None:
        return "instruction"
    if is_var(target.subject) or is_var(target.object) or variables:
        return "open"
    return "yes_no"


def _normalize_polarity(morphism: Morphism) -> Morphism:
    predicate, negated = predicate_polarity(morphism.predicate, morphism.negated)
    if predicate == morphism.predicate and negated == morphism.negated:
        return morphism
    return morphism.model_copy(update={"predicate": predicate, "negated": negated})


def _same_atom(left: Morphism, right: Morphism) -> bool:
    return (
        left.predicate == right.predicate
        and left.subject == right.subject
        and left.object == right.object
        and left.negated == right.negated
        and left.modality == right.modality
    )


def _drop_goal_echo(query: Query) -> Query:
    """A question never asserts its own target as a premise."""
    if query.target is None:
        return query
    kept = [cond for cond in query.conditions if not _same_atom(cond, query.target)]
    if len(kept) == len(query.conditions):
        return query
    return query.model_copy(update={"conditions": kept})


def settle_query(theory: Theory, query: Query) -> Query:
    """Normalize polarity, drop the goal echo, and slim unused premises.

    Premises no winning proof uses are removed one round at a time, re-verifying
    after every round until the verdict is stable.
    """
    settled = query.model_copy(
        update={
            "conditions": [_normalize_polarity(c) for c in query.conditions],
            "target": _normalize_polarity(query.target) if query.target else None,
        }
    )
    settled = _drop_goal_echo(settled)
    for _ in range(len(settled.conditions)):
        verdict = verify(theory, settled)
        unused = set(verdict.unused_premises)
        if not unused:
            break
        kept = [cond for i, cond in enumerate(settled.conditions) if i not in unused]
        if len(kept) == len(settled.conditions):
            break
        settled = settled.model_copy(update={"conditions": kept})
    return settled
