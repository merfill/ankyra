"""Exact numeric solver for the L4 engine (``docs/l4_plan.md`` §8).

The engine answers a **value query**, not an entailment: given a game (quantities +
equations) and a target quantity, it decides whether the target is uniquely
determined and returns its exact rational value. Two formalization classes are in the
committed fragment (D-L4-2):

1. a **defined-quantity DAG** — each unknown is defined by one equation over already
   known quantities; and
2. a **linear system** over the remaining unknowns, solved by exact Gaussian
   elimination.

Everything else is ``out_of_fragment``. Arithmetic is exact (``fractions.Fraction``),
so an arithmetic error is impossible by construction; incompleteness is the honest
``underdetermined`` / ``inconsistent`` / ``insufficient``, never a guessed number.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from ankyra.engine.numeric.models import NumericEquation, NumericExpr, NumericGame, NumericQuery

DEFAULT_BUDGET = 200_000

DecisionStatus = Literal[
    "determined", "underdetermined", "inconsistent", "insufficient", "out_of_fragment"
]


class NumericError(ValueError):
    """A malformed numeric structure (a builder/programming error, not an answer)."""


class _Unknown(Exception):
    """Internal: an expression references a quantity that is not yet known."""


class _Nonlinear(Exception):
    """Internal: an expression is not linear in the remaining unknowns."""


@dataclass(frozen=True)
class NumericDecision:
    """The verdict for one target: its status and, when determined, its exact value."""

    status: DecisionStatus
    value: Fraction | None = None
    detail: str | None = None


# --- expression evaluation ------------------------------------------------------


def _arity(expr: NumericExpr, n: int) -> None:
    if len(expr.args) != n:
        raise NumericError(f"{expr.op!r} takes {n} operand(s), got {len(expr.args)}")


def eval_expr(expr: NumericExpr, values: dict[str, Fraction]) -> Fraction:
    """Evaluate an expression to an exact value; unknown quantities raise ``_Unknown``."""
    if expr.op == "const":
        if expr.value is None:
            raise NumericError("const node without a value")
        return expr.value
    if expr.op == "quantity":
        if not expr.quantity:
            raise NumericError("quantity node without an id")
        if expr.quantity not in values:
            raise _Unknown(expr.quantity)
        return values[expr.quantity]
    if expr.op == "neg":
        _arity(expr, 1)
        return -eval_expr(expr.args[0], values)
    if expr.op == "add":
        if not expr.args:
            raise NumericError("add needs at least one operand")
        return sum((eval_expr(arg, values) for arg in expr.args), Fraction(0))
    if expr.op == "sub":
        _arity(expr, 2)
        return eval_expr(expr.args[0], values) - eval_expr(expr.args[1], values)
    if expr.op == "mul":
        if not expr.args:
            raise NumericError("mul needs at least one operand")
        result = Fraction(1)
        for arg in expr.args:
            result *= eval_expr(arg, values)
        return result
    if expr.op == "div":
        _arity(expr, 2)
        denominator = eval_expr(expr.args[1], values)
        if denominator == 0:
            raise NumericError("division by zero")
        return eval_expr(expr.args[0], values) / denominator
    if expr.op in ("max", "min"):
        if not expr.args:
            raise NumericError(f"{expr.op!r} needs at least one operand")
        operands = [eval_expr(arg, values) for arg in expr.args]
        return max(operands) if expr.op == "max" else min(operands)
    raise NumericError(f"unknown op {expr.op!r}")


def _try_eval(expr: NumericExpr, values: dict[str, Fraction]) -> Fraction | None:
    try:
        return eval_expr(expr, values)
    except _Unknown:
        return None


def as_linear(expr: NumericExpr, values: dict[str, Fraction]) -> tuple[dict[str, Fraction], Fraction]:
    """Express an expression as ``Σ coeff·unknown + constant`` over the unknowns.

    Raises ``_Nonlinear`` when a product/quotient involves two unknown-bearing
    sub-terms (or a non-constant divisor), which is the ``out_of_fragment`` boundary.
    """
    if expr.op == "const":
        if expr.value is None:
            raise NumericError("const node without a value")
        return {}, expr.value
    if expr.op == "quantity":
        if not expr.quantity:
            raise NumericError("quantity node without an id")
        if expr.quantity in values:
            return {}, values[expr.quantity]
        return {expr.quantity: Fraction(1)}, Fraction(0)
    if expr.op == "neg":
        _arity(expr, 1)
        coeffs, const = as_linear(expr.args[0], values)
        return {key: -value for key, value in coeffs.items()}, -const
    if expr.op == "add":
        if not expr.args:
            raise NumericError("add needs at least one operand")
        coeffs: dict[str, Fraction] = {}
        const = Fraction(0)
        for arg in expr.args:
            sub_coeffs, sub_const = as_linear(arg, values)
            coeffs = _merge(coeffs, sub_coeffs, 1)
            const += sub_const
        return _drop_zero(coeffs), const
    if expr.op == "sub":
        _arity(expr, 2)
        left_coeffs, left_const = as_linear(expr.args[0], values)
        right_coeffs, right_const = as_linear(expr.args[1], values)
        return _drop_zero(_merge(left_coeffs, right_coeffs, -1)), left_const - right_const
    if expr.op == "mul":
        if not expr.args:
            raise NumericError("mul needs at least one operand")
        constant = Fraction(1)
        nonconstant: tuple[dict[str, Fraction], Fraction] | None = None
        for arg in expr.args:
            sub_coeffs, sub_const = as_linear(arg, values)
            if not sub_coeffs:
                constant *= sub_const
            elif nonconstant is None:
                nonconstant = (sub_coeffs, sub_const)
            else:
                raise _Nonlinear()
        if nonconstant is None:
            return {}, constant
        coeffs, const = nonconstant
        return (
            {key: value * constant for key, value in coeffs.items()},
            const * constant,
        )
    if expr.op == "div":
        _arity(expr, 2)
        num_coeffs, num_const = as_linear(expr.args[0], values)
        den_coeffs, den_const = as_linear(expr.args[1], values)
        if den_coeffs:
            raise _Nonlinear()
        if den_const == 0:
            raise NumericError("division by zero")
        scale = Fraction(1) / den_const
        return (
            {key: value * scale for key, value in num_coeffs.items()},
            num_const * scale,
        )
    if expr.op in ("max", "min"):
        if not expr.args:
            raise NumericError(f"{expr.op!r} needs at least one operand")
        constants = []
        for arg in expr.args:
            sub_coeffs, sub_const = as_linear(arg, values)
            if sub_coeffs:
                # A max/min of a not-yet-known term is piecewise: out of fragment.
                raise _Nonlinear()
            constants.append(sub_const)
        return {}, (max(constants) if expr.op == "max" else min(constants))
    raise NumericError(f"unknown op {expr.op!r}")


def _merge(
    left: dict[str, Fraction], right: dict[str, Fraction], factor: Fraction
) -> dict[str, Fraction]:
    merged = dict(left)
    for key, value in right.items():
        merged[key] = merged.get(key, Fraction(0)) + factor * value
    return merged


def _drop_zero(coeffs: dict[str, Fraction]) -> dict[str, Fraction]:
    return {key: value for key, value in coeffs.items() if value != 0}


# --- validation -----------------------------------------------------------------


def validate_expression(expr: NumericExpr, declared: set[str]) -> None:
    if expr.op == "const":
        if expr.value is None:
            raise NumericError("const node without a value")
        if expr.args:
            raise NumericError("const node must not have operands")
    elif expr.op == "quantity":
        if not expr.quantity:
            raise NumericError("quantity node without an id")
        if expr.quantity not in declared:
            raise NumericError(f"unknown quantity {expr.quantity!r}")
        if expr.args:
            raise NumericError("quantity node must not have operands")
    elif expr.op in ("neg",):
        _arity(expr, 1)
    elif expr.op in ("sub", "div"):
        _arity(expr, 2)
    elif expr.op in ("add", "mul", "max", "min"):
        if not expr.args:
            raise NumericError(f"{expr.op!r} needs at least one operand")
    else:
        raise NumericError(f"unknown op {expr.op!r}")
    for arg in expr.args:
        validate_expression(arg, declared)


def _validate(game: NumericGame, query: NumericQuery) -> None:
    ids = [quantity.id for quantity in game.quantities]
    if len(ids) != len(set(ids)):
        raise NumericError("duplicate quantity id")
    declared = set(ids)
    for equation in game.equations:
        validate_expression(equation.lhs, declared)
        validate_expression(equation.rhs, declared)
    if query.target not in declared:
        raise NumericError(f"target {query.target!r} is not a declared quantity")


# --- substitution fixpoint (the DAG class) --------------------------------------


def _as_quantity(expr: NumericExpr) -> str | None:
    return expr.quantity if expr.op == "quantity" else None


def _reduce(equation: NumericEquation, values: dict[str, Fraction]) -> str:
    left_id = _as_quantity(equation.lhs)
    right_id = _as_quantity(equation.rhs)
    if left_id is not None and left_id not in values:
        right_value = _try_eval(equation.rhs, values)
        if right_value is not None:
            values[left_id] = right_value
            return "assigned"
    if right_id is not None and right_id not in values:
        left_value = _try_eval(equation.lhs, values)
        if left_value is not None:
            values[right_id] = left_value
            return "assigned"
    left_value = _try_eval(equation.lhs, values)
    right_value = _try_eval(equation.rhs, values)
    if left_value is not None and right_value is not None:
        return "consistent" if left_value == right_value else "inconsistent"
    return "pending"


def _fixpoint(equations: list[NumericEquation], values: dict[str, Fraction]) -> tuple[str, list[NumericEquation]]:
    pending = list(equations)
    progress = True
    while progress:
        progress = False
        remaining: list[NumericEquation] = []
        for equation in pending:
            outcome = _reduce(equation, values)
            if outcome == "inconsistent":
                return "inconsistent", []
            if outcome in ("assigned", "consistent"):
                progress = True
            else:
                remaining.append(equation)
        pending = remaining
    return "ok", pending


# --- linear elimination (the linear-system class) -------------------------------

_RrefOutcome = tuple[str, list[list[Fraction]] | None, list[tuple[int, int]], dict[str, int]]


def _rref(
    rows: list[tuple[dict[str, Fraction], Fraction]],
    columns: list[str],
    budget: int,
) -> _RrefOutcome:
    """Reduced row echelon form of the augmented system; budget exhaustion is honest."""
    index = {name: i for i, name in enumerate(columns)}
    width = len(columns)
    matrix = [[Fraction(0)] * (width + 1) for _ in rows]
    for row, (coeffs, const) in enumerate(rows):
        for name, value in coeffs.items():
            if name in index:
                matrix[row][index[name]] = value
        matrix[row][width] = -const

    pivots: list[tuple[int, int]] = []
    pivot_row = 0
    steps = 0
    for column in range(width):
        selected = next((r for r in range(pivot_row, len(matrix)) if matrix[r][column] != 0), None)
        if selected is None:
            continue
        matrix[pivot_row], matrix[selected] = matrix[selected], matrix[pivot_row]
        inverse = matrix[pivot_row][column]
        matrix[pivot_row] = [value / inverse for value in matrix[pivot_row]]
        steps += width + 1
        if steps > budget:
            return "budget", None, [], index
        for r in range(len(matrix)):
            if r != pivot_row and matrix[r][column] != 0:
                factor = matrix[r][column]
                matrix[r] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(matrix[r], matrix[pivot_row])
                ]
                steps += width + 1
                if steps > budget:
                    return "budget", None, [], index
        pivots.append((pivot_row, column))
        pivot_row += 1
        if pivot_row == len(matrix):
            break

    for r in range(len(matrix)):
        if all(matrix[r][c] == 0 for c in range(width)) and matrix[r][width] != 0:
            return "inconsistent", matrix, pivots, index
    return "ok", matrix, pivots, index


def _decide_linear(
    rows: list[tuple[dict[str, Fraction], Fraction]],
    unknowns: list[str],
    target: str,
    budget: int,
) -> NumericDecision:
    status, matrix, pivots, index = _rref(rows, unknowns, budget)
    if status == "budget":
        return NumericDecision("insufficient", detail="elimination budget exhausted")
    if status == "inconsistent":
        return NumericDecision("inconsistent")
    assert matrix is not None
    if target not in index:
        return NumericDecision("underdetermined")
    target_column = index[target]
    target_row = next((r for r, column in pivots if column == target_column), None)
    if target_row is None:
        return NumericDecision("underdetermined")
    pivot_columns = {column for _, column in pivots}
    free_columns = [c for c in range(len(unknowns)) if c not in pivot_columns]
    if any(matrix[target_row][c] != 0 for c in free_columns):
        return NumericDecision("underdetermined")
    return NumericDecision("determined", value=matrix[target_row][len(unknowns)])


# --- public entry ---------------------------------------------------------------


def solve(
    game: NumericGame,
    query: NumericQuery,
    *,
    budget: int | None = None,
) -> NumericDecision:
    """Decide whether ``query.target`` is determined in ``game`` and return its value."""
    bound = DEFAULT_BUDGET if budget is None else max(1, int(budget))
    _validate(game, query)

    values: dict[str, Fraction] = {}
    outcome, pending = _fixpoint(list(game.equations), values)
    if outcome == "inconsistent":
        return NumericDecision("inconsistent")

    if query.target in values:
        return NumericDecision("determined", value=values[query.target])

    unknowns = [quantity.id for quantity in game.quantities if quantity.id not in values]
    rows: list[tuple[dict[str, Fraction], Fraction]] = []
    for equation in pending:
        try:
            left_coeffs, left_const = as_linear(equation.lhs, values)
            right_coeffs, right_const = as_linear(equation.rhs, values)
        except _Nonlinear:
            return NumericDecision(
                "out_of_fragment", detail="expression is not linear in the unknowns"
            )
        coeffs = _drop_zero(_merge(left_coeffs, right_coeffs, -1))
        rows.append((coeffs, left_const - right_const))

    return _decide_linear(rows, unknowns, query.target, bound)
