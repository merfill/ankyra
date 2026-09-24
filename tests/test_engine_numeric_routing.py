"""L4 routing capability, answer and explanation (``docs/l4_plan.md`` §9/§12)."""

from __future__ import annotations

from ankyra.config.settings import setting_overrides
from ankyra.engine.answer import render_answer
from ankyra.engine.inference import analyze_numeric_routing, capabilities
from ankyra.engine.numeric import (
    NumericEquation,
    NumericExpr,
    NumericGame,
    NumericQuery,
    NumericQuantity,
    build_numeric_answer,
    build_numeric_explanation,
    decide,
    solve,
)


def _const(value: int) -> NumericExpr:
    return NumericExpr(op="const", value=value)


def _game() -> NumericGame:
    return NumericGame(
        quantities=[NumericQuantity(id="eggs"), NumericQuantity(id="sold")],
        equations=[
            NumericEquation(lhs=NumericExpr(op="quantity", quantity="eggs"), rhs=_const(16)),
            NumericEquation(
                lhs=NumericExpr(op="quantity", quantity="sold"),
                rhs=NumericExpr(
                    op="sub",
                    args=[NumericExpr(op="quantity", quantity="eggs"), _const(3)],
                ),
            ),
        ],
    )


def _query() -> NumericQuery:
    return NumericQuery(target="sold")


def test_numeric_capability_is_off_by_default():
    assert "numeric" not in capabilities()
    routing = analyze_numeric_routing(_query())
    assert not routing.compatible
    assert routing.refusal == "out_of_fragment:numeric_off"
    assert routing.procedure != "numeric"


def test_numeric_capability_routes_to_the_engine():
    with setting_overrides(ARITH=True):
        assert "numeric" in capabilities()
        routing = analyze_numeric_routing(_query())
        assert routing.compatible
        assert routing.procedure == "numeric"
        assert decide(_game(), _query()).value == 13


def test_decide_refuses_without_the_capability():
    decision = decide(_game(), _query())
    assert decision.status == "out_of_fragment"
    assert decision.detail == "out_of_fragment:numeric_off"
    assert decision.value is None


def test_decide_reports_a_build_error_as_out_of_fragment():
    game = NumericGame(
        quantities=[NumericQuantity(id="x")],
        equations=[NumericEquation(lhs=NumericExpr(op="quantity", quantity="x"), rhs=NumericExpr(op="quantity", quantity="missing"))],
    )
    with setting_overrides(ARITH=True):
        decision = decide(game, NumericQuery(target="x"))
    assert decision.status == "out_of_fragment"
    assert "numeric_error" in (decision.detail or "")


def test_build_numeric_answer_and_explanation():
    with setting_overrides(ARITH=True):
        decided = decide(_game(), _query())
    answer = build_numeric_answer(decided)
    assert answer.kind == "number"
    assert answer.value == "13"
    assert answer.strength == "proven"
    explanation = build_numeric_explanation(decided)
    assert [step.kind for step in explanation.steps] == ["numeric"]
    assert explanation.goal == "value 13"

    unknown = build_numeric_answer(decide(_game(), _query()))  # refused
    assert unknown.kind == "unknown"
    assert unknown.strength == "not_proven"
    assert build_numeric_explanation(decide(_game(), _query())).steps == []


def test_render_number_answer():
    with setting_overrides(ARITH=True):
        answer = build_numeric_answer(decide(_game(), _query()))
    assert "13" in render_answer(answer, language="en")
    assert "Число" in render_answer(answer, language="ru")


def test_underdetermined_solves_but_does_not_answer():
    game = NumericGame(
        quantities=[NumericQuantity(id="x"), NumericQuantity(id="y")],
        equations=[
            NumericEquation(
                lhs=NumericExpr(op="add", args=[NumericExpr(op="quantity", quantity="x"), NumericExpr(op="quantity", quantity="y")]),
                rhs=_const(10),
            )
        ],
    )
    decision = solve(game, NumericQuery(target="x"))
    assert decision.status == "underdetermined"
    assert build_numeric_answer(decision).kind == "unknown"
