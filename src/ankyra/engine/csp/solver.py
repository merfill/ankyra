"""Bounded finite-domain search for the L3 engine (``docs/l3_plan.md`` §8).

The solver answers **model queries**, not entailment of a clause set:

* :func:`satisfiable` — find a model (a witness);
* :func:`countermodel` — find a model where an option's conjunction fails; a ``None``
  result within the budget is the ``must`` proof (no explicit negation needed);
* :func:`enumerate_models` — collect models for a complete-and-accurate list.

The search is a depth-first backtracking over the variables in declaration order,
pruning as soon as an evaluable constraint is falsified, under an explicit node
budget. Exhaustion is the honest ``budget``, never a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from ankyra.engine.csp.models import (
    CspConstraint,
    CspDomain,
    CspGame,
    CspQuestion,
)

DEFAULT_BUDGET = 200_000

SearchStatus = Literal["sat", "unsat", "budget"]
DecisionStatus = Literal["decided", "ambiguous", "unknown", "insufficient", "out_of_fragment"]


@dataclass(frozen=True)
class _Context:
    """Resolved lookups for constraint evaluation (built once per search)."""

    domain_of: dict[str, CspDomain]
    order: dict[str, dict[str, int]]
    size: dict[str, int]


def _context(game: CspGame) -> _Context:
    domains = {d.id: d for d in game.domains}
    domain_of: dict[str, CspDomain] = {}
    for variable in game.variables:
        if variable.domain not in domains:
            raise ValueError(f"variable {variable.id!r} references unknown domain {variable.domain!r}")
        domain_of[variable.id] = domains[variable.domain]
    order = {d.id: {value: i for i, value in enumerate(d.values)} for d in game.domains}
    size = {d.id: len(d.values) for d in game.domains}
    return _Context(domain_of=domain_of, order=order, size=size)


def _holds(constraint: CspConstraint, assign: dict[str, str], ctx: _Context) -> bool | None:
    """Three-valued evaluation: True / False / None (not yet determined)."""
    kind = constraint.kind

    if kind == "conditional":
        condition = _holds(constraint.condition, assign, ctx) if constraint.condition else True
        consequence = _holds(constraint.consequence, assign, ctx) if constraint.consequence else True
        if consequence is True or condition is False:
            return True
        if condition is True:
            return consequence
        return None

    if kind in ("all", "any", "not"):
        parts = [_holds(sub, assign, ctx) for sub in constraint.constraints]
        if kind == "all":
            return _and(parts)
        if kind == "any":
            return _or(parts)
        # not: a single sub-constraint.
        if not parts:
            return None
        value = parts[0]
        return None if value is None else not value

    if kind == "all_different":
        seen: set[str] = set()
        assigned = 0
        for variable in constraint.variables:
            value = assign.get(variable)
            if value is None:
                continue
            assigned += 1
            if value in seen:
                return False
            seen.add(value)
        if assigned == len(constraint.variables):
            return True
        return None

    if any(variable not in assign for variable in constraint.variables):
        return None

    if kind == "eq":
        if len(constraint.variables) == 1:
            return assign[constraint.variables[0]] == constraint.values[0]
        return assign[constraint.variables[0]] == assign[constraint.variables[1]]

    if kind == "neq":
        if len(constraint.variables) == 1:
            return assign[constraint.variables[0]] != constraint.values[0]
        return assign[constraint.variables[0]] != assign[constraint.variables[1]]

    if kind == "order":
        first, second = constraint.variables[0], constraint.variables[1]
        domain = ctx.domain_of[first]
        left = ctx.order[domain.id][assign[first]]
        right = ctx.order[domain.id][assign[second]]
        if domain.topology == "circular":
            if not constraint.immediate:
                raise ValueError("circular order without 'immediate' is undefined")
            return right == (left + 1) % ctx.size[domain.id]
        return right == left + 1 if constraint.immediate else left < right

    if kind in ("adjacent", "not_adjacent"):
        first, second = constraint.variables[0], constraint.variables[1]
        domain = ctx.domain_of[first]
        left = ctx.order[domain.id][assign[first]]
        right = ctx.order[domain.id][assign[second]]
        distance = abs(left - right)
        size = ctx.size[domain.id]
        adjacent = distance == 1 or (domain.topology == "circular" and distance == size - 1)
        return adjacent if kind == "adjacent" else not adjacent

    if kind in ("same_group", "different_group"):
        equal = assign[constraint.variables[0]] == assign[constraint.variables[1]]
        return equal if kind == "same_group" else not equal

    if kind == "count":
        if constraint.count is None or not constraint.values:
            raise ValueError("count constraint needs a count and a group value")
        total = sum(1 for variable in constraint.variables if assign[variable] == constraint.values[0])
        if constraint.count_mode == "exactly":
            return total == constraint.count
        if constraint.count_mode == "at_least":
            return total >= constraint.count
        return total <= constraint.count

    if kind == "count_compare":
        if constraint.comparison is None or len(constraint.values) < 2:
            raise ValueError("count_compare needs a comparison and two group values")
        left = sum(1 for variable in constraint.variables if assign[variable] == constraint.values[0])
        right = sum(1 for variable in constraint.variables if assign[variable] == constraint.values[1])
        if constraint.comparison == "gt":
            return left > right
        if constraint.comparison == "lt":
            return left < right
        return left == right

    raise ValueError(f"unknown constraint kind {kind!r}")


def _and(values: list[bool | None]) -> bool | None:
    """Three-valued conjunction: False dominates; True only if all are True."""
    if any(value is False for value in values):
        return False
    if all(value is True for value in values):
        return True
    return None


def _or(values: list[bool | None]) -> bool | None:
    """Three-valued disjunction: True dominates; False only if all are False."""
    if any(value is True for value in values):
        return True
    if all(value is False for value in values):
        return False
    return None


def _option_holds(option: list[CspConstraint], assign: dict[str, str], ctx: _Context) -> bool:
    """An option is a conjunction of constraints (an empty conjunction is True)."""
    return all(_holds(constraint, assign, ctx) is True for constraint in option)


@dataclass
class SearchResult:
    """The outcome of a model query plus the models found and the nodes visited."""

    status: SearchStatus
    model: dict[str, str] | None = None
    models: list[dict[str, str]] = field(default_factory=list)
    steps: int = 0


def _search(
    game: CspGame,
    extra: list[CspConstraint],
    accept: Callable[[dict[str, str], _Context], bool],
    *,
    budget: int,
    collect: int,
) -> SearchResult:
    ctx = _context(game)
    constraints = [*game.constraints, *extra]
    variables = [variable.id for variable in game.variables]
    values = {variable.id: list(ctx.domain_of[variable.id].values) for variable in game.variables}

    found: list[dict[str, str]] = []
    assign: dict[str, str] = {}
    steps = 0
    exhausted = False

    def recurse(index: int) -> bool:
        nonlocal steps, exhausted
        steps += 1
        if steps > budget:
            exhausted = True
            return False
        if index == len(variables):
            if accept(assign, ctx):
                found.append(dict(assign))
                return len(found) >= collect
            return False
        variable = variables[index]
        for value in values[variable]:
            assign[variable] = value
            consistent = True
            for constraint in constraints:
                if _holds(constraint, assign, ctx) is False:
                    consistent = False
                    break
            if consistent and recurse(index + 1):
                return True
            del assign[variable]
        return False

    recurse(0)
    if exhausted:
        return SearchResult("budget", steps=steps, models=found)
    if found:
        # A single-model query stopped early; the rest were not searched, so report
        # only what was asked for.
        models = found if collect > 1 else found[:1]
        return SearchResult("sat", model=found[0], models=models, steps=steps)
    return SearchResult("unsat", steps=steps, models=[])


def satisfiable(
    game: CspGame,
    extra: list[CspConstraint] | None = None,
    *,
    budget: int = DEFAULT_BUDGET,
) -> SearchResult:
    """Find any model satisfying the game plus ``extra`` (a witness)."""
    return _search(game, list(extra or []), lambda _assign, _ctx: True, budget=budget, collect=1)


def countermodel(
    game: CspGame,
    option: list[CspConstraint],
    *,
    budget: int = DEFAULT_BUDGET,
) -> SearchResult:
    """Find a model where the option's conjunction is false (the ``must`` check)."""
    return _search(
        game,
        [],
        lambda assign, ctx: not _option_holds(option, assign, ctx),
        budget=budget,
        collect=1,
    )


def enumerate_models(
    game: CspGame,
    *,
    limit: int,
    budget: int = DEFAULT_BUDGET,
) -> SearchResult:
    """Collect up to ``limit`` models (for a complete-and-accurate list)."""
    return _search(game, [], lambda _assign, _ctx: True, budget=budget, collect=max(1, limit))


@dataclass
class CspDecision:
    """The per-question decision: which option (if any) the solver verified."""

    status: DecisionStatus
    index: int | None = None
    witness: dict[str, str] | None = None
    verified: list[int] = field(default_factory=list)
    complete_list: list[str] = field(default_factory=list)
    detail: str = ""


def decide_question(
    game: CspGame,
    question: CspQuestion,
    *,
    budget: int = DEFAULT_BUDGET,
) -> CspDecision:
    """Decide a multiple-choice question by the model-theoretic reading (D-L3-3).

    Exactly one verified option is ``decided``; none is ``unknown``; more than one is
    ``ambiguous`` (an encoding signal, never a tie-break). A budget miss is
    ``insufficient`` — no option is guessed.

    An option is always checked against the game augmented with the question's
    ``assumptions`` (Gamma), which is what an "if …" question asserts.
    """
    effective = game
    if question.assumptions:
        effective = game.model_copy(
            update={"constraints": [*game.constraints, *question.assumptions]}
        )
    verified: list[tuple[int, dict[str, str] | None]] = []

    if question.kind == "complete_list":
        if not question.target:
            return CspDecision("unknown", detail="complete_list needs a target variable")
        result = enumerate_models(effective, limit=budget, budget=budget)
        if result.status == "budget":
            return CspDecision("insufficient", detail="enumeration budget exhausted")
        possible = sorted({model.get(question.target, "") for model in result.models})
        for index, option in enumerate(question.options):
            if sorted(option.values) == possible:
                verified.append((index, None))
        return _finalize(verified, complete_list=possible)

    for index, option in enumerate(question.options):
        if question.kind in ("could", "not_violate"):
            result = satisfiable(effective, list(option.constraints), budget=budget)
            if result.status == "budget":
                return CspDecision("insufficient", detail=f"option {index}: budget exhausted")
            if result.status == "sat":
                verified.append((index, result.model))
        elif question.kind == "must":
            result = countermodel(effective, list(option.constraints), budget=budget)
            if result.status == "budget":
                return CspDecision("insufficient", detail=f"option {index}: budget exhausted")
            if result.status == "unsat":
                verified.append((index, None))
        elif question.kind == "must_be_false":
            # The dual of "could": the verified option is the one that has no model.
            result = satisfiable(effective, list(option.constraints), budget=budget)
            if result.status == "budget":
                return CspDecision("insufficient", detail=f"option {index}: budget exhausted")
            if result.status == "unsat":
                verified.append((index, None))
        else:
            return CspDecision("unknown", detail=f"unknown question kind {question.kind!r}")

    return _finalize(verified)


def _finalize(
    verified: list[tuple[int, dict[str, str] | None]],
    *,
    complete_list: list[str] | None = None,
) -> CspDecision:
    if len(verified) == 1:
        index, witness = verified[0]
        return CspDecision(
            "decided",
            index=index,
            witness=witness,
            verified=[index],
            complete_list=complete_list or [],
        )
    if not verified:
        return CspDecision("unknown", detail="no option verified", complete_list=complete_list or [])
    return CspDecision(
        "ambiguous",
        verified=[index for index, _ in verified],
        detail="multiple options verified",
        complete_list=complete_list or [],
    )
