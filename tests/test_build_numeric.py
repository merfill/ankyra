"""Unit tests for the L4 numeric builder path (``docs/l4_plan.md`` §10, §14)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from ankyra.build.numeric import (
    NumericBuildError,
    build_numeric_game,
    build_numeric_query,
)
from ankyra.engine.numeric.schemas import (
    NumericExprSpec,
    NumericGameStructure,
    NumericQueryStructure,
)
from ankyra.engine.numeric.solver import solve

PERCENT = {
    "quantities": [
        {"id": "list", "quote": "costs $80"},
        {"id": "discount", "quote": "25% off"},
        {"id": "sale", "quote": "sale for 25% off"},
    ],
    "equations": [
        {"lhs": {"op": "quantity", "quantity": "list"}, "rhs": {"op": "const", "value": "80"}, "quote": "costs $80"},
        {
            "lhs": {"op": "quantity", "quantity": "discount"},
            "rhs": {"op": "mul", "args": [{"op": "quantity", "quantity": "list"}, {"op": "div", "args": [{"op": "const", "value": "25"}, {"op": "const", "value": "100"}]}]},
            "quote": "25% off",
        },
        {
            "lhs": {"op": "quantity", "quantity": "sale"},
            "rhs": {"op": "sub", "args": [{"op": "quantity", "quantity": "list"}, {"op": "quantity", "quantity": "discount"}]},
            "quote": "sale for 25% off",
        },
    ],
}
PERCENT_SOURCE = "A shirt costs $80. It is on sale for 25% off."


def test_build_game_and_solve_end_to_end():
    structure = NumericGameStructure.model_validate(PERCENT)
    game = build_numeric_game(structure, source_text=PERCENT_SOURCE)
    query = build_numeric_query(NumericQueryStructure(target="sale"), game=game)
    decision = solve(game, query)
    assert decision.status == "determined"
    assert decision.value == 60


def test_op_aliases_and_identifier_normalization():
    structure = NumericGameStructure.model_validate(
        {
            "quantities": [{"id": "?x"}],
            "equations": [
                {
                    "lhs": {"op": "quantity", "quantity": "?x"},
                    "rhs": {
                        "op": "sum",
                        "args": [
                            {"op": "const", "value": "2"},
                            {"op": "product", "args": [{"op": "const", "value": "3"}, {"op": "const", "value": "4"}]},
                        ],
                    },
                }
            ],
        }
    )
    game = build_numeric_game(structure)
    assert game.quantities[0].id == "x"
    decision = solve(game, build_numeric_query(NumericQueryStructure(target="x"), game=game))
    assert decision.value == 14


def test_fraction_literals():
    assert NumericExprSpec.model_validate({"op": "const", "value": "0.5"}).value == Fraction(1, 2)
    assert NumericExprSpec.model_validate({"op": "const", "value": "25%"}).value == Fraction(1, 4)
    assert NumericExprSpec.model_validate({"op": "const", "value": "3/4"}).value == Fraction(3, 4)
    assert NumericExprSpec.model_validate({"op": "const", "value": "$1,000"}).value == Fraction(1000)


def test_duplicate_quantity_is_a_build_error():
    structure = NumericGameStructure.model_validate({"quantities": [{"id": "x"}, {"id": "x"}]})
    with pytest.raises(NumericBuildError, match="duplicate quantity"):
        build_numeric_game(structure)


def test_unknown_quantity_reference_is_a_build_error():
    structure = NumericGameStructure.model_validate(
        {
            "quantities": [{"id": "x"}],
            "equations": [{"lhs": {"op": "quantity", "quantity": "x"}, "rhs": {"op": "quantity", "quantity": "missing"}}],
        }
    )
    with pytest.raises(NumericBuildError, match="unknown quantity"):
        build_numeric_game(structure)


def test_const_without_value_is_a_build_error():
    structure = NumericGameStructure.model_validate(
        {
            "quantities": [{"id": "x"}],
            "equations": [{"lhs": {"op": "quantity", "quantity": "x"}, "rhs": {"op": "const"}}],
        }
    )
    with pytest.raises(NumericBuildError, match="const"):
        build_numeric_game(structure)


def test_wrong_arity_is_a_build_error():
    structure = NumericGameStructure.model_validate(
        {
            "quantities": [{"id": "x"}],
            "equations": [
                {"lhs": {"op": "quantity", "quantity": "x"}, "rhs": {"op": "sub", "args": [{"op": "const", "value": "1"}]}}
            ],
        }
    )
    with pytest.raises(NumericBuildError, match="sub"):
        build_numeric_game(structure)


def test_empty_quantity_id_is_a_build_error():
    structure = NumericGameStructure.model_validate(
        {"quantities": [{"id": ""}], "equations": []}
    )
    with pytest.raises(NumericBuildError, match="no id"):
        build_numeric_game(structure)


def test_unknown_target_is_a_build_error():
    structure = NumericGameStructure.model_validate({"quantities": [{"id": "x"}]})
    game = build_numeric_game(structure)
    with pytest.raises(NumericBuildError, match="target"):
        build_numeric_query(NumericQueryStructure(target="y"), game=game)


def test_missing_or_non_verbatim_quote_is_a_build_error():
    structure = NumericGameStructure.model_validate(
        {
            "quantities": [{"id": "x", "quote": "not in the source"}],
            "equations": [],
        }
    )
    with pytest.raises(NumericBuildError, match="quote"):
        build_numeric_game(structure, source_text="x is stated here")


def test_quotes_are_not_required_without_a_source():
    structure = NumericGameStructure.model_validate({"quantities": [{"id": "x"}], "equations": []})
    game = build_numeric_game(structure)
    assert game.quantities[0].id == "x"


def test_query_tolerance_parsing():
    structure = NumericGameStructure.model_validate({"quantities": [{"id": "x"}]})
    game = build_numeric_game(structure)
    query = build_numeric_query(
        NumericQueryStructure(target="x", tolerance="0.01"), game=game
    )
    assert query.tolerance == Fraction(1, 100)
