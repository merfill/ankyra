"""Deterministic numeric builder: LLM structure -> strict L4 IR (``docs/l4_plan.md`` §10).

The builder acts only on structured output: it assembles the validated extraction
schemas into the engine IR and checks structural integrity (every referenced quantity
is declared, every expression is well-formed, and — when the source text is available
— every quantity/equation carries a verbatim quote). A structure the IR cannot
represent is an honest ``NumericBuildError``, never an approximation
(``docs/l4_plan.md`` §3).
"""

from __future__ import annotations

from ankyra.engine.numeric.models import (
    NumericExpr,
    NumericGame,
    NumericQuery,
)
from ankyra.engine.numeric.schemas import NumericGameStructure, NumericQueryStructure
from ankyra.engine.numeric.solver import NumericError, validate_expression


class NumericBuildError(ValueError):
    """The structure violates the IR's integrity (dangling reference, bad expression)."""


def _check_expression(expr: NumericExpr, declared: set[str]) -> None:
    try:
        validate_expression(expr, declared)
    except NumericError as exc:
        raise NumericBuildError(str(exc)) from exc


def _check_quotes(game: NumericGame) -> None:
    """Every quantity and equation must cite a verbatim span, when a source is known.

    A quote check is a structural witness check on the raw text
    (``docs/task.md`` §3.8), not an interpretation of it.
    """
    source = game.source_text
    if not source:
        return
    for quantity in game.quantities:
        if not quantity.quote or quantity.quote not in source:
            raise NumericBuildError(
                f"quantity {quantity.id!r}: missing or non-verbatim quote"
            )
    for equation in game.equations:
        if not equation.quote or equation.quote not in source:
            raise NumericBuildError("an equation has a missing or non-verbatim quote")


def build_numeric_game(structure: NumericGameStructure, *, source_text: str = "") -> NumericGame:
    """Validate a game structure into the strict IR."""
    data = {**structure.model_dump(), "source_text": source_text or structure.source_text}
    game = NumericGame.model_validate(data)

    for quantity in game.quantities:
        if not quantity.id:
            raise NumericBuildError("a quantity has no id")
    ids = [quantity.id for quantity in game.quantities]
    if len(ids) != len(set(ids)):
        raise NumericBuildError("duplicate quantity id")
    declared = set(ids)
    for equation in game.equations:
        _check_expression(equation.lhs, declared)
        _check_expression(equation.rhs, declared)
    _check_quotes(game)
    return game


def build_numeric_query(structure: NumericQueryStructure, *, game: NumericGame) -> NumericQuery:
    """Validate a question structure into the strict IR against its game."""
    query = NumericQuery.model_validate(
        {"target": structure.target, "tolerance": structure.tolerance}
    )
    if not query.target:
        raise NumericBuildError("a numeric query needs a target")
    declared = {quantity.id for quantity in game.quantities}
    if query.target not in declared:
        raise NumericBuildError(f"target {query.target!r} is not a declared quantity")
    return query
