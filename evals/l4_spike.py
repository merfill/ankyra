"""L4 Phase-0 feasibility spike (LLM-free; ``docs/l4_plan.md`` §6).

Hand-encode five problems (one per axis: multi-step DAG, ratio/division, percent,
linear system with introduced unknowns, unit multiplier) into the numeric IR and
solve them with the in-repo exact solver, plus three negative controls (a free target
must stay ``underdetermined``, an inconsistent system ``inconsistent``, and a
non-linear equation ``out_of_fragment``). This is the decision gate: does a general
IR cover the axes soundly, or does a construct resist it?

Run::

    uv run python -m evals.l4_spike

No LLM calls. Exits non-zero on any decision mismatch.
"""

from __future__ import annotations

from fractions import Fraction

from ankyra.engine.numeric import (
    NumericEquation,
    NumericExpr,
    NumericGame,
    NumericQuery,
    NumericQuantity,
    solve,
)


def _const(value: int | Fraction) -> NumericExpr:
    return NumericExpr(op="const", value=Fraction(value))


def _q(quantity: str) -> NumericExpr:
    return NumericExpr(op="quantity", quantity=quantity)


def _add(*args: NumericExpr) -> NumericExpr:
    return NumericExpr(op="add", args=list(args))


def _sub(left: NumericExpr, right: NumericExpr) -> NumericExpr:
    return NumericExpr(op="sub", args=[left, right])


def _mul(*args: NumericExpr) -> NumericExpr:
    return NumericExpr(op="mul", args=list(args))


def _div(left: NumericExpr, right: NumericExpr) -> NumericExpr:
    return NumericExpr(op="div", args=[left, right])


def _eq(left: NumericExpr, right: NumericExpr, quote: str | None = None) -> NumericEquation:
    return NumericEquation(lhs=left, rhs=right, quote=quote)


def _game(
    names: list[tuple[str, str | None]], equations: list[NumericEquation], source: str = ""
) -> NumericGame:
    return NumericGame(
        quantities=[NumericQuantity(id=name, unit=unit) for name, unit in names],
        equations=equations,
        source_text=source,
    )


# --- Case 1 — multi-step DAG ----------------------------------------------------
# 16 eggs/day; 3 eaten, 4 baked; the rest sold at $2 each. Revenue?
DUCKS = _game(
    [
        ("eggs", "eggs"),
        ("eaten", "eggs"),
        ("baked", "eggs"),
        ("sold", "eggs"),
        ("price", "dollars"),
        ("revenue", "dollars"),
    ],
    [
        _eq(_q("eggs"), _const(16), "lay 16 eggs per day"),
        _eq(_q("eaten"), _const(3), "eats 3 for breakfast"),
        _eq(_q("baked"), _const(4), "uses 4 to bake muffins"),
        _eq(_q("sold"), _sub(_q("eggs"), _add(_q("eaten"), _q("baked"))), "sells the remainder"),
        _eq(_q("price"), _const(2), "for $2 per egg"),
        _eq(_q("revenue"), _mul(_q("sold"), _q("price")), "how much does she make"),
    ],
    source="Janet's ducks lay 16 eggs per day; she eats 3 and bakes with 4, selling the rest at $2 each.",
)
CASE1 = ("multi-step-dag", DUCKS, NumericQuery(target="revenue"), Fraction(18))

# --- Case 2 — ratio/division ----------------------------------------------------
# Tom has 10 apples; Sam has half as many.
RATIO = _game(
    [("tom", "apples"), ("sam", "apples")],
    [
        _eq(_q("tom"), _const(10), "Tom has 10 apples"),
        _eq(_q("sam"), _div(_q("tom"), _const(2)), "half as many apples as Tom"),
    ],
    source="Tom has 10 apples. Sam has half as many apples as Tom.",
)
CASE2 = ("ratio-division", RATIO, NumericQuery(target="sam"), Fraction(5))

# --- Case 3 — percent -----------------------------------------------------------
# $80 shirt, 25% off.
PERCENT = _game(
    [("list", "dollars"), ("discount", "dollars"), ("sale", "dollars")],
    [
        _eq(_q("list"), _const(80), "costs $80"),
        _eq(_q("discount"), _mul(_q("list"), _div(_const(25), _const(100))), "25% off"),
        _eq(_q("sale"), _sub(_q("list"), _q("discount")), "what is the sale price"),
    ],
    source="A shirt costs $80. It is on sale for 25% off. What is the sale price?",
)
CASE3 = ("percent", PERCENT, NumericQuery(target="sale"), Fraction(60))

# --- Case 4 — linear system with introduced unknowns ----------------------------
# The sum of two numbers is 20; one is 4 more than the other. The larger number?
LINEAR = _game(
    [("big", None), ("small", None)],
    [
        _eq(_add(_q("big"), _q("small")), _const(20), "the sum of two numbers is 20"),
        _eq(_q("big"), _add(_q("small"), _const(4)), "one is 4 more than the other"),
    ],
    source="The sum of two numbers is 20. One number is 4 more than the other.",
)
CASE4 = ("linear-system", LINEAR, NumericQuery(target="big"), Fraction(12))

# --- Case 5 — unit multiplier ---------------------------------------------------
# 3 cups of flour; 1 cup is 8 ounces.
UNITS = _game(
    [("cups", "cups"), ("ounces_per_cup", "ounces/cup"), ("ounces", "ounces")],
    [
        _eq(_q("cups"), _const(3), "3 cups of flour"),
        _eq(_q("ounces_per_cup"), _const(8), "1 cup is 8 ounces"),
        _eq(_q("ounces"), _mul(_q("cups"), _q("ounces_per_cup")), "how many ounces"),
    ],
    source="A recipe needs 3 cups of flour. 1 cup is 8 ounces. How many ounces of flour?",
)
CASE5 = ("unit-multiplier", UNITS, NumericQuery(target="ounces"), Fraction(24))

# --- Controls -------------------------------------------------------------------
# A free target (one equation, two unknowns) must not be answered.
FREE = _game(
    [("x", None), ("y", None)],
    [_eq(_add(_q("x"), _q("y")), _const(10), "the sum is 10")],
    source="Two numbers add to 10.",
)
CONTROL_FREE = ("control-underdetermined", FREE, NumericQuery(target="x"), "underdetermined")

# A contradictory pair must be reported as inconsistent.
CONFLICT = _game(
    [("x", None)],
    [_eq(_q("x"), _const(1), "x is 1"), _eq(_q("x"), _const(2), "x is 2")],
    source="x is 1 and x is 2.",
)
CONTROL_CONFLICT = ("control-inconsistent", CONFLICT, NumericQuery(target="x"), "inconsistent")

# A product of two unknowns is outside the committed linear fragment.
NONLINEAR = _game(
    [("x", None)],
    [_eq(_mul(_q("x"), _q("x")), _const(4), "x squared is 4")],
    source="x squared is 4.",
)
CONTROL_NONLINEAR = ("control-nonlinear", NONLINEAR, NumericQuery(target="x"), "out_of_fragment")

CASES = [
    CASE1,
    CASE2,
    CASE3,
    CASE4,
    CASE5,
    CONTROL_FREE,
    CONTROL_CONFLICT,
    CONTROL_NONLINEAR,
]


def run() -> int:
    failures = 0
    print(f"L4 Phase-0 spike — {len(CASES)} hand-encoded cases (LLM-free)\n")
    for name, game, query, expected in CASES:
        decision = solve(game, query)
        if expected == "underdetermined":
            ok = decision.status == "underdetermined"
        elif expected == "inconsistent":
            ok = decision.status == "inconsistent"
        elif expected == "out_of_fragment":
            ok = decision.status == "out_of_fragment"
        else:
            ok = decision.status == "determined" and decision.value == expected
        mark = "ok " if ok else "FAIL"
        shown = decision.value if decision.value is not None else decision.status
        detail = f" ({decision.detail})" if decision.detail else ""
        print(f"  [{mark}] {name:26s} status={decision.status:15s} value={shown}{detail}")
        if not ok:
            failures += 1
    print()
    if failures:
        print(f"spike gate RED: {failures}/{len(CASES)} mismatches")
        return 1
    print(f"spike gate GREEN: {len(CASES)}/{len(CASES)}")
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
