"""Deterministic CSP builder: LLM structure -> strict L3 IR (``docs/l3_plan.md`` §10).

The builder acts only on structured output: it assembles the validated extraction
schemas into the engine IR and checks structural integrity (every variable has a
known domain, every constraint references known variables, and a value belongs to
the domain it is compared against). A structure the IR cannot represent is an
honest ``CspBuildError``, never an approximation (``docs/l3_plan.md`` §3).
"""

from __future__ import annotations

from ankyra.engine.csp.models import (
    CspConstraint,
    CspGame,
    CspQuestion,
)
from ankyra.engine.csp.schemas import (
    CspGameStructure,
    CspQuestionStructure,
)


class CspBuildError(ValueError):
    """The structure violates the IR's integrity (dangling reference, bad value)."""


class CspFragmentError(CspBuildError):
    """A construct outside the committed L3 fragment — an honest ``out_of_fragment``.

    Raised when the structure is well-formed but asks for something the fragment does
    not express (e.g. a complete list over a derived sequence/entity, not a variable).
    """


def _iter_constraints(constraint: CspConstraint):
    """Yield a constraint and, recursively, its conditional halves and sub-groups."""
    yield constraint
    if constraint.condition is not None:
        yield from _iter_constraints(constraint.condition)
    if constraint.consequence is not None:
        yield from _iter_constraints(constraint.consequence)
    for sub in constraint.constraints:
        yield from _iter_constraints(sub)


def _check_shape(constraints: list[CspConstraint], context: str) -> None:
    """Reject composite constraints with missing parts.

    ``all``/``any`` over an empty list evaluate vacuously (``True``/``False``) and a
    ``conditional`` without both halves (or a ``not`` without exactly one operand)
    would silently change the semantics; a malformed composite is a build error, not a
    guess (``docs/l3_plan.md`` §3).
    """
    for constraint in constraints:
        for statement in _iter_constraints(constraint):
            _check_composite(statement, context)


def _check_composite(statement: CspConstraint, context: str) -> None:
    kind = statement.kind
    if kind in ("all", "any"):
        if not statement.constraints:
            raise CspBuildError(
                f"{context}: {kind!r} has no sub-constraints; supply its parts"
            )
    elif kind == "not":
        if len(statement.constraints) != 1:
            raise CspBuildError(f"{context}: 'not' needs exactly one sub-constraint")
    elif kind == "conditional":
        if statement.condition is None or statement.consequence is None:
            raise CspBuildError(
                f"{context}: 'conditional' needs both a condition and a consequence"
            )


def _check_counted(constraints: list[CspConstraint], context: str) -> None:
    """Reject a malformed counted group.

    A ``count`` counts the variables whose value belongs to its group — the **set** of
    declared ``values`` — so it needs a count and at least one value (a single value is
    the special case). ``count_compare`` compares two groups and needs exactly two
    distinct values. Rejecting a malformed group is a build error, never a guess
    (``docs/l3_plan.md`` §3).
    """
    for constraint in constraints:
        for statement in _iter_constraints(constraint):
            if statement.kind == "count":
                if statement.count is None or not statement.values:
                    raise CspBuildError(
                        f"{context}: 'count' needs a count and at least one group value"
                    )
            elif statement.kind == "count_compare":
                if statement.comparison is None or len(statement.values) != 2:
                    raise CspBuildError(
                        f"{context}: 'count_compare' needs a comparison and exactly two group values"
                    )
                if statement.values[0] == statement.values[1]:
                    raise CspBuildError(
                        f"{context}: 'count_compare' needs two distinct group values"
                    )


def _known_variables(game: CspGame) -> set[str]:
    return {variable.id for variable in game.variables}


def _domain_values(game: CspGame) -> set[str]:
    return {value for domain in game.domains for value in domain.values}


def _check_references(constraints: list[CspConstraint], known: set[str], context: str) -> None:
    for constraint in constraints:
        for statement in _iter_constraints(constraint):
            for variable in statement.variables:
                if variable not in known:
                    raise CspBuildError(
                        f"{context}: {statement.kind!r} references unknown variable {variable!r}"
                    )


def _check_values(game: CspGame, constraints: list[CspConstraint]) -> None:
    """A compared/counted value must belong to the domain (or factor) it is compared in."""
    domain_of = {variable.id: variable.domain for variable in game.variables}
    values = {domain.id: set(domain.values) for domain in game.domains}
    for constraint in constraints:
        for statement in _iter_constraints(constraint):
            if not statement.values or not statement.variables:
                continue
            if statement.factor:
                allowed = values.get(statement.factor, set())
                where = f"factor {statement.factor!r}"
            else:
                allowed = values.get(domain_of.get(statement.variables[0], ""), set())
                where = f"the domain of {statement.variables[0]!r}"
            for value in statement.values:
                if value not in allowed:
                    raise CspBuildError(
                        f"{statement.kind!r}: value {value!r} is not in {where}"
                    )


_LEAF_KINDS = {
    "all_different", "eq", "neq", "order", "adjacent", "not_adjacent",
    "same_group", "different_group", "count", "count_compare",
}


def _check_domains(game: CspGame) -> None:
    """A product domain's factors must be declared atomic domains, fully decomposed."""
    domains = {domain.id: domain for domain in game.domains}
    for domain in game.domains:
        for factor in domain.factors:
            if factor not in domains:
                raise CspBuildError(
                    f"domain {domain.id!r} references unknown factor domain {factor!r}"
                )
            if domains[factor].factors:
                raise CspBuildError(f"factor domain {factor!r} must be atomic")
        if not domain.factors:
            if domain.value_factors:
                raise CspBuildError(
                    f"atomic domain {domain.id!r} must not declare value_factors"
                )
            continue
        for value in domain.values:
            parts = domain.value_factors.get(value)
            if parts is None or len(parts) != len(domain.factors):
                raise CspBuildError(
                    f"domain {domain.id!r}: value {value!r} has no factor decomposition"
                )
            for factor, part in zip(domain.factors, parts):
                if part not in domains[factor].values:
                    raise CspBuildError(
                        f"domain {domain.id!r}: value {value!r} factor {factor!r}={part!r} "
                        "is not in that factor domain"
                    )


def _check_factors(game: CspGame, constraints: list[CspConstraint], context: str) -> None:
    """``factor`` must name a declared factor of every referenced variable's domain."""
    domains = {domain.id: domain for domain in game.domains}
    domain_of = {variable.id: domains.get(variable.domain) for variable in game.variables}
    for constraint in constraints:
        for statement in _iter_constraints(constraint):
            if statement.factor is None:
                continue
            if statement.kind not in _LEAF_KINDS or statement.kind == "all_different":
                raise CspBuildError(
                    f"{context}: 'factor' is not meaningful on {statement.kind!r}"
                )
            if statement.factor not in domains:
                raise CspBuildError(
                    f"{context}: unknown factor domain {statement.factor!r}"
                )
            for variable in statement.variables:
                domain = domain_of.get(variable)
                if domain is None or statement.factor not in domain.factors:
                    raise CspBuildError(
                        f"{context}: variable {variable!r} does not range over a domain "
                        f"with factor {statement.factor!r}"
                    )


def build_csp_game(structure: CspGameStructure, *, source_text: str = "") -> CspGame:
    """Validate a game structure into the strict IR."""
    game = CspGame.model_validate(
        {**structure.model_dump(), "source_text": source_text or structure.source_text}
    )
    domain_ids = {domain.id for domain in game.domains}
    for variable in game.variables:
        if variable.domain not in domain_ids:
            raise CspBuildError(
                f"variable {variable.id!r} references unknown domain {variable.domain!r}"
            )
    _check_domains(game)
    known = _known_variables(game)
    _check_shape(game.constraints, "game")
    _check_counted(game.constraints, "game")
    _check_references(game.constraints, known, "game")
    _check_factors(game, game.constraints, "game")
    _check_values(game, game.constraints)
    return game


def build_csp_question(structure: CspQuestionStructure, *, game: CspGame | None = None) -> CspQuestion:
    """Validate a question structure into the strict IR (optionally against its game)."""
    data = {key: value for key, value in structure.model_dump().items() if key != "source_text"}
    question = CspQuestion.model_validate(data)
    if question.kind == "complete_list" and not question.target:
        raise CspFragmentError("a complete_list question needs a target")
    if game is not None:
        known = _known_variables(game)
        if question.kind == "complete_list" and question.target:
            if question.target_kind == "variable" and question.target not in known:
                # The list is over a derived sequence/entity, not a variable: the
                # fragment does not express it (docs/ar_lsat.md §8.1).
                raise CspFragmentError(
                    f"complete_list target {question.target!r} is not a known variable"
                )
            if question.target_kind == "value" and question.target not in _domain_values(game):
                raise CspFragmentError(
                    f"complete_list target {question.target!r} is not a known domain value"
                )
        _check_shape(question.assumptions, "assumption")
        _check_counted(question.assumptions, "assumption")
        _check_references(question.assumptions, known, "assumption")
        _check_factors(game, question.assumptions, "assumption")
        _check_values(game, question.assumptions)
        for option in question.options:
            _check_shape(option.constraints, "option")
            _check_counted(option.constraints, "option")
            _check_references(option.constraints, known, "option")
            _check_factors(game, option.constraints, "option")
    return question
