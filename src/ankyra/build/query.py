"""Deterministic query assembly: answer type, goal-echo removal, premise slimming."""

from __future__ import annotations

from ankyra.build.normalize import is_var, predicate_polarity
from ankyra.core.models import AnswerType, Morphism, Query


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


def _complement_atom(left: Morphism, right: Morphism) -> bool:
    """Same triple and modality, opposite polarity."""
    return (
        left.predicate == right.predicate
        and left.subject == right.subject
        and left.object == right.object
        and left.negated != right.negated
        and left.modality == right.modality
    )


def _drop_goal_echo(query: Query) -> Query:
    """A question never asserts its own target as a premise, nor its complement.

    A target and its negation cannot both be premises: extracting "is phi?" as a
    positive target with a ``¬phi`` condition is the question restated with the
    polarity on the wrong side, and would make the query self-contradictory. The
    condition is the echo, so it is dropped; genuine presuppositions name other
    atoms and are kept.
    """
    if query.target is None:
        return query
    kept = [
        cond
        for cond in query.conditions
        if not _same_atom(cond, query.target) and not _complement_atom(cond, query.target)
    ]
    if len(kept) == len(query.conditions):
        return query
    return query.model_copy(update={"conditions": kept})


def settle_query(query: Query) -> Query:
    """Normalize polarity and drop the goal echo.

    Unused question premises are kept: ``verify`` reports them as ``insufficient``
    instead of the builder silently deleting a premise the question asserted.
    """
    settled = query.model_copy(
        update={
            "conditions": [_normalize_polarity(c) for c in query.conditions],
            "target": _normalize_polarity(query.target) if query.target else None,
        }
    )
    return _drop_goal_echo(settled)


def strip_domain_conditions(query: Query, domain: list[str] | None) -> Query:
    """Drop a question premise that only restricts the variable to a universe sort."""
    names = {d.casefold() for d in (domain or []) if d}
    if not names:
        return query
    kept = [
        cond
        for cond in query.conditions
        if not (
            cond.predicate == "is_a"
            and not cond.negated
            and cond.modality == "neutral"
            and cond.object
            and cond.object.casefold() in names
        )
    ]
    if len(kept) == len(query.conditions):
        return query
    return query.model_copy(update={"conditions": kept})
