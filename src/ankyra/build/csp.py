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


def _known_variables(game: CspGame) -> set[str]:
    return {variable.id for variable in game.variables}


def _check_references(constraints: list[CspConstraint], known: set[str], context: str) -> None:
    for constraint in constraints:
        for statement in _iter_constraints(constraint):
            for variable in statement.variables:
                if variable not in known:
                    raise CspBuildError(
                        f"{context}: {statement.kind!r} references unknown variable {variable!r}"
                    )


def _check_values(game: CspGame, constraints: list[CspConstraint]) -> None:
    """A compared/counted value must belong to the domain of its first variable."""
    domain_of = {variable.id: variable.domain for variable in game.variables}
    values = {domain.id: set(domain.values) for domain in game.domains}
    for constraint in constraints:
        for statement in _iter_constraints(constraint):
            if not statement.values or not statement.variables:
                continue
            allowed = values.get(domain_of.get(statement.variables[0], ""), set())
            for value in statement.values:
                if value not in allowed:
                    raise CspBuildError(
                        f"{statement.kind!r}: value {value!r} is not in the domain of "
                        f"{statement.variables[0]!r}"
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
    known = _known_variables(game)
    _check_shape(game.constraints, "game")
    _check_references(game.constraints, known, "game")
    _check_values(game, game.constraints)
    return game


def build_csp_question(structure: CspQuestionStructure, *, game: CspGame | None = None) -> CspQuestion:
    """Validate a question structure into the strict IR (optionally against its game)."""
    data = {key: value for key, value in structure.model_dump().items() if key != "source_text"}
    question = CspQuestion.model_validate(data)
    if question.kind == "complete_list" and not question.target:
        raise CspFragmentError("a complete_list question needs a target variable")
    if game is not None:
        known = _known_variables(game)
        if question.target and question.target not in known:
            # The list is over a derived sequence/entity, not a variable: the fragment
            # does not express it (docs/l3_plan.md §13.2).
            raise CspFragmentError(
                f"complete_list target {question.target!r} is not a known variable"
            )
        _check_shape(question.assumptions, "assumption")
        _check_references(question.assumptions, known, "assumption")
        _check_values(game, question.assumptions)
        for option in question.options:
            _check_shape(option.constraints, "option")
            _check_references(option.constraints, known, "option")
    return question
