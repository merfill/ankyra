"""Build the committed L4 synthetic collection (deterministic, LLM-free; ``docs/l4_plan.md`` §13.1).

The L4 engine is gated by a structural collection: each case is a fully structured
numeric game/query with an independently written expected decision, graded by
``evals.l4_synthetic``. No LLM, no natural language, zero provider variance.

Coverage: every expression op (``const``, ``quantity``, ``neg``, ``add``, ``sub``,
``mul``, ``div``), both formalization classes (defined-quantity DAG and linear
system), every outcome (``determined``, ``underdetermined``, ``inconsistent``,
``out_of_fragment``, ``insufficient``) and the mandatory negative controls (a free
target is never answered; an inconsistent system is never answered; a non-linear
equation is refused; a malformed structure is a build error, not a value).

Usage:
    uv run python -m evals.build_l4_synthetic [--out PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "l4_synthetic.jsonl"


def _const(value: int | str) -> dict:
    return {"op": "const", "value": str(value)}


def _q(name: str) -> dict:
    return {"op": "quantity", "quantity": name}


def _op(op: str, *args: dict) -> dict:
    return {"op": op, "args": list(args)}


def _neg(arg: dict) -> dict:
    return _op("neg", arg)


def _eq(lhs: dict, rhs: dict, quote: str = "synthetic") -> dict:
    return {"lhs": lhs, "rhs": rhs, "quote": quote}


def _game(
    names: list[str] | list[tuple[str, str | None]],
    equations: list[dict],
    source: str = "",
) -> dict:
    quantities = []
    for name in names:
        if isinstance(name, tuple):
            quantities.append({"id": name[0], "unit": name[1]})
        else:
            quantities.append({"id": name, "unit": None})
    return {"quantities": quantities, "equations": equations, "source_text": source}


def _case(
    id: str,
    mechanism: str,
    uses: list[str],
    game: dict,
    target: str,
    expected: dict,
    budget: int | None = None,
) -> dict:
    case = {
        "id": id,
        "mechanism": mechanism,
        "uses": sorted(set(uses)),
        "game": game,
        "query": {"target": target},
        "expected": expected,
    }
    if budget is not None:
        case["budget"] = budget
    return case


# --- expression ops -------------------------------------------------------------


def _expression_cases() -> list[dict]:
    return [
        _case(
            "expr-const",
            "expr-const",
            ["const"],
            _game(["x"], [_eq(_q("x"), _const(7))]),
            "x",
            {"status": "determined", "value": "7"},
        ),
        _case(
            "expr-neg",
            "expr-neg",
            ["const", "neg"],
            _game(["x"], [_eq(_q("x"), _neg(_const(3)))]),
            "x",
            {"status": "determined", "value": "-3"},
        ),
        _case(
            "expr-add",
            "expr-add",
            ["const", "add"],
            _game(["x"], [_eq(_q("x"), _op("add", _const(2), _const(3), _const(4)))]),
            "x",
            {"status": "determined", "value": "9"},
        ),
        _case(
            "expr-sub",
            "expr-sub",
            ["const", "sub"],
            _game(["x"], [_eq(_q("x"), _op("sub", _const(10), _const(4)))]),
            "x",
            {"status": "determined", "value": "6"},
        ),
        _case(
            "expr-mul",
            "expr-mul",
            ["const", "mul"],
            _game(["x"], [_eq(_q("x"), _op("mul", _const(2), _const(3), _const(4)))]),
            "x",
            {"status": "determined", "value": "24"},
        ),
        _case(
            "expr-div",
            "expr-div",
            ["const", "div"],
            _game(["x"], [_eq(_q("x"), _op("div", _const(3), _const(4)))]),
            "x",
            {"status": "determined", "value": "3/4"},
        ),
        _case(
            "expr-negative-result",
            "expr-sub",
            ["const", "sub"],
            _game(["x"], [_eq(_q("x"), _op("sub", _const(3), _const(10)))]),
            "x",
            {"status": "determined", "value": "-7"},
        ),
        _case(
            "expr-nested",
            "expr-nested",
            ["const", "add", "sub", "mul"],
            _game(
                ["x"],
                [_eq(_q("x"), _op("mul", _op("add", _const(2), _const(3)), _op("sub", _const(10), _const(4))))],
            ),
            "x",
            {"status": "determined", "value": "30"},
        ),
        _case(
            "expr-div-nested",
            "expr-nested",
            ["const", "add", "div"],
            _game(["x"], [_eq(_q("x"), _op("div", _op("add", _const(1), _const(1)), _const(2)))]),
            "x",
            {"status": "determined", "value": "1"},
        ),
        _case(
            "expr-max",
            "expr-max",
            ["const", "max"],
            _game(["x"], [_eq(_q("x"), _op("max", _const(3), _const(7), _const(5)))]),
            "x",
            {"status": "determined", "value": "7"},
        ),
        _case(
            "expr-min",
            "expr-min",
            ["const", "min"],
            _game(["x"], [_eq(_q("x"), _op("min", _const(3), _const(7), _const(5)))]),
            "x",
            {"status": "determined", "value": "3"},
        ),
    ]


# --- defined-quantity DAG -------------------------------------------------------


def _dag_cases() -> list[dict]:
    return [
        _case(
            "dag-chain",
            "dag",
            ["const", "quantity", "sub", "add", "mul"],
            _game(
                ["eggs", "eaten", "baked", "sold", "price", "revenue"],
                [
                    _eq(_q("eggs"), _const(16)),
                    _eq(_q("eaten"), _const(3)),
                    _eq(_q("baked"), _const(4)),
                    _eq(_q("sold"), _op("sub", _q("eggs"), _op("add", _q("eaten"), _q("baked")))),
                    _eq(_q("price"), _const(2)),
                    _eq(_q("revenue"), _op("mul", _q("sold"), _q("price"))),
                ],
            ),
            "revenue",
            {"status": "determined", "value": "18"},
        ),
        _case(
            "dag-ratio",
            "dag",
            ["const", "quantity", "div"],
            _game(
                ["tom", "sam"],
                [
                    _eq(_q("tom"), _const(10)),
                    _eq(_q("sam"), _op("div", _q("tom"), _const(2))),
                ],
            ),
            "sam",
            {"status": "determined", "value": "5"},
        ),
        _case(
            "dag-percent",
            "dag",
            ["const", "quantity", "mul", "div", "sub"],
            _game(
                ["list", "discount", "sale"],
                [
                    _eq(_q("list"), _const(80)),
                    _eq(_q("discount"), _op("mul", _q("list"), _op("div", _const(25), _const(100)))),
                    _eq(_q("sale"), _op("sub", _q("list"), _q("discount"))),
                ],
            ),
            "sale",
            {"status": "determined", "value": "60"},
        ),
        _case(
            "dag-unit",
            "dag",
            ["const", "quantity", "mul"],
            _game(
                [("cups", "cups"), ("ounces_per_cup", "ounces/cup"), ("ounces", "ounces")],
                [
                    _eq(_q("cups"), _const(3)),
                    _eq(_q("ounces_per_cup"), _const(8)),
                    _eq(_q("ounces"), _op("mul", _q("cups"), _q("ounces_per_cup"))),
                ],
            ),
            "ounces",
            {"status": "determined", "value": "24"},
        ),
        _case(
            "dag-consistent-redefinition",
            "dag",
            ["const", "quantity", "add"],
            _game(
                ["x"],
                [_eq(_q("x"), _op("add", _const(2), _const(3))), _eq(_q("x"), _const(5))],
            ),
            "x",
            {"status": "determined", "value": "5"},
        ),
        _case(
            "dag-target-with-residual",
            "dag",
            ["const", "quantity", "add"],
            _game(
                ["a", "b", "x", "y", "z"],
                [
                    _eq(_q("a"), _const(1)),
                    _eq(_q("b"), _const(2)),
                    _eq(_q("x"), _op("add", _q("a"), _q("b"))),
                    _eq(_op("add", _q("y"), _q("z")), _const(10)),
                ],
            ),
            "x",
            {"status": "determined", "value": "3"},
        ),
        _case(
            "dag-max-choice",
            "dag",
            ["const", "quantity", "mul", "div", "max"],
            _game(
                ["jewelry", "gadgets", "profit_jewelry", "profit_gadgets", "best"],
                [
                    _eq(_q("jewelry"), _const(5000)),
                    _eq(_q("gadgets"), _const(8000)),
                    _eq(_q("profit_jewelry"), _op("mul", _q("jewelry"), _op("div", _const("5/2"), _const(100)))),
                    _eq(_q("profit_gadgets"), _op("mul", _q("gadgets"), _op("div", _const("6/5"), _const(100)))),
                    _eq(_q("best"), _op("max", _q("profit_jewelry"), _q("profit_gadgets"))),
                ],
            ),
            "best",
            {"status": "determined", "value": "125"},
        ),
    ]


# --- linear systems -------------------------------------------------------------


def _linear_cases() -> list[dict]:
    return [
        _case(
            "linear-classic",
            "linear",
            ["const", "quantity", "add"],
            _game(
                ["x", "y"],
                [
                    _eq(_op("add", _q("x"), _q("y")), _const(20)),
                    _eq(_q("x"), _op("add", _q("y"), _const(4))),
                ],
            ),
            "x",
            {"status": "determined", "value": "12"},
        ),
        _case(
            "linear-sum-diff-x",
            "linear",
            ["const", "quantity", "add", "sub"],
            _game(
                ["x", "y"],
                [
                    _eq(_op("add", _q("x"), _q("y")), _const(10)),
                    _eq(_op("sub", _q("x"), _q("y")), _const(4)),
                ],
            ),
            "x",
            {"status": "determined", "value": "7"},
        ),
        _case(
            "linear-sum-diff-y",
            "linear",
            ["const", "quantity", "add", "sub"],
            _game(
                ["x", "y"],
                [
                    _eq(_op("add", _q("x"), _q("y")), _const(10)),
                    _eq(_op("sub", _q("x"), _q("y")), _const(4)),
                ],
            ),
            "y",
            {"status": "determined", "value": "3"},
        ),
        _case(
            "linear-three-variables",
            "linear",
            ["const", "quantity", "add", "sub"],
            _game(
                ["x", "y", "z"],
                [
                    _eq(_op("add", _q("x"), _q("y"), _q("z")), _const(6)),
                    _eq(_op("sub", _q("x"), _q("y")), _const(0)),
                    _eq(_op("sub", _q("y"), _q("z")), _const(0)),
                ],
            ),
            "z",
            {"status": "determined", "value": "2"},
        ),
        _case(
            "linear-target-free-sibling",
            "linear",
            ["const", "quantity", "add", "sub"],
            _game(
                ["x", "y", "z"],
                [
                    _eq(_op("add", _q("x"), _q("y")), _const(10)),
                    _eq(_op("sub", _q("x"), _q("y")), _const(0)),
                ],
            ),
            "x",
            {"status": "determined", "value": "5"},
        ),
        _case(
            "linear-underdetermined",
            "underdetermined",
            ["const", "quantity", "add"],
            _game(
                ["x", "y"],
                [_eq(_op("add", _q("x"), _q("y")), _const(10))],
            ),
            "x",
            {"status": "underdetermined"},
        ),
        _case(
            "linear-underdetermined-free-sibling",
            "underdetermined",
            ["const", "quantity", "add", "sub"],
            _game(
                ["x", "y", "z"],
                [
                    _eq(_op("add", _q("x"), _q("y")), _const(10)),
                    _eq(_op("sub", _q("x"), _q("y")), _const(0)),
                ],
            ),
            "z",
            {"status": "underdetermined"},
        ),
        _case(
            "linear-fraction",
            "linear",
            ["const", "quantity", "mul"],
            _game(["x"], [_eq(_op("mul", _const(2), _q("x")), _const(3))]),
            "x",
            {"status": "determined", "value": "3/2"},
        ),
        _case(
            "linear-nontrivial-fraction",
            "linear",
            ["const", "quantity", "add", "sub", "mul"],
            _game(
                ["x", "y"],
                [
                    _eq(_op("add", _op("mul", _const(3), _q("x")), _op("mul", _const(2), _q("y"))), _const(12)),
                    _eq(_op("sub", _q("x"), _q("y")), _const(0)),
                ],
            ),
            "x",
            {"status": "determined", "value": "12/5"},
        ),
        _case(
            "linear-inconsistent",
            "inconsistent",
            ["const", "quantity", "add"],
            _game(
                ["x", "y"],
                [
                    _eq(_op("add", _q("x"), _q("y")), _const(1)),
                    _eq(_op("add", _q("x"), _q("y")), _const(2)),
                ],
            ),
            "x",
            {"status": "inconsistent"},
        ),
    ]


# --- out of fragment / budget / malformed ---------------------------------------


def _boundary_cases() -> list[dict]:
    return [
        _case(
            "oof-nonlinear-square",
            "out-of-fragment",
            ["const", "quantity", "mul"],
            _game(["x"], [_eq(_op("mul", _q("x"), _q("x")), _const(4))]),
            "x",
            {"status": "out_of_fragment"},
        ),
        _case(
            "oof-two-unknowns-product",
            "out-of-fragment",
            ["const", "quantity", "mul"],
            _game(["x", "y"], [_eq(_op("mul", _q("x"), _q("y")), _const(4))]),
            "x",
            {"status": "out_of_fragment"},
        ),
        _case(
            "oof-nonconstant-divisor",
            "out-of-fragment",
            ["const", "quantity", "div"],
            _game(["x", "y"], [_eq(_q("x"), _op("div", _const(1), _q("y")))]),
            "x",
            {"status": "out_of_fragment"},
        ),
        _case(
            "oof-max-unknown",
            "out-of-fragment",
            ["const", "quantity", "max"],
            _game(["x", "y"], [_eq(_q("x"), _op("max", _q("y"), _const(3)))]),
            "x",
            {"status": "out_of_fragment"},
        ),
        _case(
            "budget-insufficient",
            "budget",
            ["const", "quantity", "add"],
            _game(
                ["x", "y", "z"],
                [
                    _eq(_op("add", _q("x"), _q("y")), _const(1)),
                    _eq(_op("add", _q("y"), _q("z")), _const(1)),
                    _eq(_op("add", _q("x"), _q("z")), _const(1)),
                ],
            ),
            "x",
            {"status": "insufficient"},
            budget=1,
        ),
        _case(
            "err-division-by-zero",
            "build-error",
            ["const", "quantity", "div"],
            _game(["x"], [_eq(_q("x"), _op("div", _const(1), _const(0)))]),
            "x",
            {"raises": "division by zero"},
        ),
        _case(
            "err-unknown-quantity",
            "build-error",
            ["quantity"],
            _game(["x"], [_eq(_q("x"), _q("missing"))]),
            "x",
            {"raises": "unknown quantity"},
        ),
        _case(
            "err-duplicate-quantity",
            "build-error",
            ["quantity"],
            _game(["x", "x"], []),
            "x",
            {"raises": "duplicate quantity"},
        ),
        _case(
            "err-unknown-target",
            "build-error",
            ["quantity"],
            _game(["x"], []),
            "missing",
            {"raises": "target"},
        ),
    ]


def cases() -> list[dict]:
    """The full deterministic collection (grouped by mechanism)."""
    return [*_expression_cases(), *_dag_cases(), *_linear_cases(), *_boundary_cases()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the committed L4 synthetic collection.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    rows = cases()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} cases to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
