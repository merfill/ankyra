"""Unit tests for the L4 exact-arithmetic numeric engine (``docs/l4_plan.md`` §14)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from ankyra.engine.numeric import (
    NumericEquation,
    NumericError,
    NumericExpr,
    NumericGame,
    NumericQuery,
    NumericQuantity,
    eval_expr,
    solve,
)


def _const(value: int | Fraction) -> NumericExpr:
    return NumericExpr(op="const", value=Fraction(value))


def _q(quantity: str) -> NumericExpr:
    return NumericExpr(op="quantity", quantity=quantity)


def _eq(left: NumericExpr, right: NumericExpr) -> NumericEquation:
    return NumericEquation(lhs=left, rhs=right)


def _game(ids: list[str], equations: list[NumericEquation]) -> NumericGame:
    return NumericGame(
        quantities=[NumericQuantity(id=name) for name in ids], equations=equations
    )


def test_eval_expr_operators() -> None:
    values = {"a": Fraction(6), "b": Fraction(3)}
    assert eval_expr(_const(5), values) == 5
    assert eval_expr(_q("a"), values) == 6
    assert eval_expr(NumericExpr(op="neg", args=[_q("a")]), values) == -6
    assert eval_expr(NumericExpr(op="add", args=[_q("a"), _q("b"), _const(1)]), values) == 10
    assert eval_expr(NumericExpr(op="sub", args=[_q("a"), _q("b")]), values) == 3
    assert eval_expr(NumericExpr(op="mul", args=[_q("a"), _q("b")]), values) == 18
    assert eval_expr(NumericExpr(op="div", args=[_q("a"), _q("b")]), values) == 2


def test_eval_expr_division_by_zero() -> None:
    with pytest.raises(NumericError, match="division by zero"):
        eval_expr(NumericExpr(op="div", args=[_const(1), _const(0)]), {})


def test_eval_expr_max_min() -> None:
    values = {"a": Fraction(6), "b": Fraction(3)}
    assert eval_expr(NumericExpr(op="max", args=[_q("a"), _q("b"), _const(5)]), values) == 6
    assert eval_expr(NumericExpr(op="min", args=[_q("a"), _q("b"), _const(5)]), values) == 3


def test_max_of_known_terms_is_determined() -> None:
    game = _game(
        ["a", "b", "best"],
        [
            _eq(_q("a"), _const(10)),
            _eq(_q("b"), _const(4)),
            _eq(_q("best"), NumericExpr(op="max", args=[_q("a"), _q("b")])),
        ],
    )
    assert solve(game, NumericQuery(target="best")).value == 10


def test_max_of_an_unknown_is_out_of_fragment() -> None:
    game = _game(
        ["x", "y"],
        [_eq(_q("x"), NumericExpr(op="max", args=[_q("y"), _const(3)]))],
    )
    assert solve(game, NumericQuery(target="x")).status == "out_of_fragment"


def test_defined_quantity_dag() -> None:
    game = _game(
        ["eggs", "eaten", "sold", "price", "revenue"],
        [
            _eq(_q("eggs"), _const(16)),
            _eq(_q("eaten"), _const(3)),
            _eq(_q("sold"), NumericExpr(op="sub", args=[_q("eggs"), _q("eaten")])),
            _eq(_q("price"), _const(2)),
            _eq(_q("revenue"), NumericExpr(op="mul", args=[_q("sold"), _q("price")])),
        ],
    )
    decision = solve(game, NumericQuery(target="revenue"))
    assert decision.status == "determined"
    assert decision.value == 26


def test_linear_system_unique_target() -> None:
    game = _game(
        ["x", "y"],
        [
            _eq(NumericExpr(op="add", args=[_q("x"), _q("y")]), _const(20)),
            _eq(_q("x"), NumericExpr(op="add", args=[_q("y"), _const(4)])),
        ],
    )
    decision = solve(game, NumericQuery(target="x"))
    assert decision.status == "determined"
    assert decision.value == 12


def test_free_target_is_underdetermined() -> None:
    game = _game(
        ["x", "y"],
        [_eq(NumericExpr(op="add", args=[_q("x"), _q("y")]), _const(10))],
    )
    assert solve(game, NumericQuery(target="x")).status == "underdetermined"
    assert solve(game, NumericQuery(target="y")).status == "underdetermined"


def test_target_determined_despite_free_sibling() -> None:
    game = _game(
        ["x", "y", "z"],
        [
            _eq(NumericExpr(op="add", args=[_q("x"), _q("y")]), _const(10)),
            _eq(NumericExpr(op="sub", args=[_q("x"), _q("y")]), _const(0)),
        ],
    )
    assert solve(game, NumericQuery(target="x")).value == 5
    assert solve(game, NumericQuery(target="z")).status == "underdetermined"


def test_inconsistent_system() -> None:
    game = _game(["x"], [_eq(_q("x"), _const(1)), _eq(_q("x"), _const(2))])
    assert solve(game, NumericQuery(target="x")).status == "inconsistent"


def test_nonlinear_is_out_of_fragment() -> None:
    game = _game(
        ["x"],
        [_eq(NumericExpr(op="mul", args=[_q("x"), _q("x")]), _const(4))],
    )
    decision = solve(game, NumericQuery(target="x"))
    assert decision.status == "out_of_fragment"


def test_nonconstant_divisor_is_out_of_fragment() -> None:
    game = _game(
        ["x", "y"],
        [_eq(_q("x"), NumericExpr(op="div", args=[_const(1), _q("y")]))],
    )
    assert solve(game, NumericQuery(target="x")).status == "out_of_fragment"


def test_budget_exhaustion_is_insufficient() -> None:
    game = _game(
        ["x", "y", "z"],
        [
            _eq(NumericExpr(op="add", args=[_q("x"), _q("y")]), _const(1)),
            _eq(NumericExpr(op="add", args=[_q("y"), _q("z")]), _const(1)),
            _eq(NumericExpr(op="add", args=[_q("x"), _q("z")]), _const(1)),
        ],
    )
    assert solve(game, NumericQuery(target="x"), budget=1).status == "insufficient"


def test_unknown_quantity_reference_is_a_build_error() -> None:
    game = _game(["x"], [_eq(_q("x"), _q("missing"))])
    with pytest.raises(NumericError, match="unknown quantity"):
        solve(game, NumericQuery(target="x"))


def test_duplicate_quantity_id_is_a_build_error() -> None:
    game = NumericGame(
        quantities=[NumericQuantity(id="x"), NumericQuantity(id="x")],
        equations=[],
    )
    with pytest.raises(NumericError, match="duplicate quantity"):
        solve(game, NumericQuery(target="x"))


def test_unknown_target_is_a_build_error() -> None:
    game = _game(["x"], [])
    with pytest.raises(NumericError, match="target"):
        solve(game, NumericQuery(target="missing"))
