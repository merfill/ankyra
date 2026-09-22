"""L3 routing capability, answer and explanation (``docs/l3_plan.md`` §9/§12)."""

from __future__ import annotations

from ankyra.config.settings import setting_overrides
from ankyra.engine.answer import render_answer
from ankyra.engine.csp import (
    CspConstraint,
    CspDomain,
    CspGame,
    CspOption,
    CspQuestion,
    CspVariable,
    build_csp_answer,
    build_csp_explanation,
    decide,
    decide_question,
)
from ankyra.engine.inference import analyze_csp_routing, capabilities

C = CspConstraint


def _game() -> CspGame:
    return CspGame(
        domains=[CspDomain(id="s2", values=["0", "1"], topology="set")],
        variables=[CspVariable(id="A", domain="s2")],
        constraints=[C(kind="neq", variables=["A"], values=["0"])],
    )


def _question() -> CspQuestion:
    return CspQuestion(
        kind="could",
        options=[CspOption(constraints=[C(kind="eq", variables=["A"], values=["0"])]),
                 CspOption(constraints=[C(kind="eq", variables=["A"], values=["1"])])],
    )


def test_csp_capability_is_off_by_default():
    assert "csp" not in capabilities()
    routing = analyze_csp_routing(_question())
    assert not routing.compatible
    assert routing.refusal == "out_of_fragment:csp_off"
    assert routing.procedure != "csp"


def test_csp_capability_routes_to_the_engine():
    with setting_overrides(CSP=True):
        assert "csp" in capabilities()
        routing = analyze_csp_routing(_question())
        assert routing.compatible
        assert routing.procedure == "csp"
        # A=0 is impossible (A != 0), so the verified option is index 1.
        assert decide(_game(), _question()).index == 1


def test_decide_refuses_without_the_capability():
    decision = decide(_game(), _question())
    assert decision.status == "out_of_fragment"
    assert decision.detail == "out_of_fragment:csp_off"
    assert decision.index is None


def test_build_csp_answer_and_explanation():
    decided = decide_question(_game(), _question())
    answer = build_csp_answer(decided)
    assert answer.kind == "choice"
    assert answer.value == "1"
    assert answer.strength == "proven"
    explanation = build_csp_explanation(decided)
    assert [step.kind for step in explanation.steps] == ["model"]
    assert explanation.goal == "option 1"

    unknown = build_csp_answer(decide(_game(), _question()))  # refused
    assert unknown.kind == "unknown"
    assert unknown.strength == "not_proven"
    assert build_csp_explanation(decide(_game(), _question())).steps == []


def test_render_choice_answer():
    answer = build_csp_answer(decide_question(_game(), _question()))
    assert "1" in render_answer(answer, language="en")
    assert "Вариант" in render_answer(answer, language="ru")


def test_complete_list_explanation_reports_the_list():
    game = CspGame(
        domains=[CspDomain(id="s2", values=["0", "1"], topology="set")],
        variables=[CspVariable(id="A", domain="s2")],
        constraints=[],
    )
    question = CspQuestion(kind="complete_list", target="A", options=[CspOption(values=["0", "1"])])
    explanation = build_csp_explanation(decide_question(game, question))
    assert "0, 1" in explanation.steps[0].statement
