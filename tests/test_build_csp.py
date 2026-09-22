"""The deterministic CSP builder: schema -> strict IR (``docs/l3_plan.md`` §15)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ankyra.build.csp import CspBuildError, build_csp_game, build_csp_question
from ankyra.engine.csp import decide_question
from ankyra.engine.csp.schemas import (
    CspConstraintSpec,
    CspDomainSpec,
    CspGameStructure,
    CspOptionSpec,
    CspQuestionStructure,
    CspVariableSpec,
)


def _seat_game(*, topology: str = "linear") -> CspGameStructure:
    return CspGameStructure(
        domains=[CspDomainSpec(id="seat", values=["0", "1", "2"], topology=topology)],
        variables=[CspVariableSpec(id="A", domain="seat"), CspVariableSpec(id="B", domain="seat")],
        constraints=[
            CspConstraintSpec(kind="all_different", variables=["A", "B"]),
            CspConstraintSpec(kind="eq", variables=["A"], values=["0"]),
        ],
    )


def test_build_game_normalizes_aliases_and_topology():
    structure = CspGameStructure(
        domains=[CspDomainSpec(id="seat", values=["0", "1", "2"], topology="around")],
        variables=[CspVariableSpec(id="A", domain="seat"), CspVariableSpec(id="B", domain="seat")],
        constraints=[
            CspConstraintSpec(kind="distinct", variables=["?A", "B"]),
            CspConstraintSpec(kind="next_to", variables=["A", "B"]),
        ],
    )
    game = build_csp_game(structure, source_text="source")
    assert game.domains[0].topology == "circular"
    assert game.constraints[0].kind == "all_different"
    assert game.constraints[0].variables == ["A", "B"]  # leading '?' stripped
    assert game.constraints[1].kind == "adjacent"
    assert game.source_text == "source"


def test_build_game_keeps_quotes_and_count():
    structure = CspGameStructure(
        domains=[CspDomainSpec(id="g", values=["X", "Y"], topology="set")],
        variables=[CspVariableSpec(id="A", domain="g"), CspVariableSpec(id="B", domain="g")],
        constraints=[
            CspConstraintSpec(
                kind="count",
                variables=["A", "B"],
                values=["X"],
                count=1,
                count_mode="at_least",
                quote="at least one",
            )
        ],
    )
    game = build_csp_game(structure)
    assert game.constraints[0].count_mode == "at_least"
    assert game.constraints[0].quote == "at least one"


def test_dangling_variable_raises():
    structure = CspGameStructure(
        domains=[CspDomainSpec(id="seat", values=["0", "1"])],
        variables=[CspVariableSpec(id="A", domain="seat")],
        constraints=[CspConstraintSpec(kind="eq", variables=["Z"], values=["0"])],
    )
    with pytest.raises(CspBuildError):
        build_csp_game(structure)


def test_unknown_domain_raises():
    structure = CspGameStructure(
        variables=[CspVariableSpec(id="A", domain="missing")],
    )
    with pytest.raises(CspBuildError):
        build_csp_game(structure)


def test_value_outside_domain_raises():
    structure = CspGameStructure(
        domains=[CspDomainSpec(id="seat", values=["0", "1"])],
        variables=[CspVariableSpec(id="A", domain="seat")],
        constraints=[CspConstraintSpec(kind="eq", variables=["A"], values=["9"])],
    )
    with pytest.raises(CspBuildError):
        build_csp_game(structure)


def test_conditional_halves_are_validated_recursively():
    structure = CspGameStructure(
        domains=[CspDomainSpec(id="g", values=["X", "Y"], topology="set")],
        variables=[CspVariableSpec(id="A", domain="g")],
        constraints=[
            CspConstraintSpec(
                kind="conditional",
                condition=CspConstraintSpec(kind="eq", variables=["A"], values=["X"]),
                consequence=CspConstraintSpec(kind="eq", variables=["Z"], values=["X"]),
            )
        ],
    )
    with pytest.raises(CspBuildError):
        build_csp_game(structure)


def test_unknown_topology_and_kind_are_refused():
    with pytest.raises(ValidationError):
        CspDomainSpec(id="d", values=["0"], topology="hexagonal")
    with pytest.raises(ValidationError):
        CspConstraintSpec(kind="frobnicate", variables=["A"])


def test_build_question_arrangement_options():
    game = build_csp_game(_seat_game())
    structure = CspQuestionStructure(
        kind="not_violate",
        options=[
            CspOptionSpec(
                constraints=[
                    CspConstraintSpec(kind="eq", variables=["A"], values=["0"]),
                    CspConstraintSpec(kind="eq", variables=["B"], values=["1"]),
                ]
            ),
            CspOptionSpec(
                constraints=[
                    CspConstraintSpec(kind="eq", variables=["A"], values=["1"]),
                    CspConstraintSpec(kind="eq", variables=["B"], values=["0"]),
                ]
            ),
        ],
    )
    question = build_csp_question(structure, game=game)
    assert question.kind == "not_violate"
    decision = decide_question(game, question)
    assert decision.status == "decided"
    assert decision.index == 0  # only A=0 and B=1 satisfies A=0 and all_different


def test_build_question_complete_list_target():
    game = build_csp_game(
        CspGameStructure(
            domains=[CspDomainSpec(id="seat", values=["0", "1"])],
            variables=[CspVariableSpec(id="A", domain="seat")],
            constraints=[CspConstraintSpec(kind="eq", variables=["A"], values=["0"])],
        )
    )
    structure = CspQuestionStructure(
        kind="complete_list",
        target="A",
        options=[CspOptionSpec(values=["0"]), CspOptionSpec(values=["1"])],
    )
    question = build_csp_question(structure, game=game)
    assert question.target == "A"
    assert decide_question(game, question).index == 0


def test_complete_list_without_target_raises():
    structure = CspQuestionStructure(kind="complete_list", options=[CspOptionSpec(values=["0"])])
    with pytest.raises(CspBuildError):
        build_csp_question(structure)


def test_question_option_dangling_variable_raises():
    game = build_csp_game(_seat_game())
    structure = CspQuestionStructure(
        kind="could",
        options=[CspOptionSpec(constraints=[CspConstraintSpec(kind="eq", variables=["Z"], values=["0"])])],
    )
    with pytest.raises(CspBuildError):
        build_csp_question(structure, game=game)


def test_boolean_and_count_aliases():
    assert CspConstraintSpec(kind="or", constraints=[CspConstraintSpec(kind="eq", variables=["A"], values=["0"])]).kind == "any"
    assert CspConstraintSpec(kind="and").kind == "all"
    assert CspConstraintSpec(kind="negation").kind == "not"
    counted = CspConstraintSpec(
        kind="count-compare", variables=["A", "B"], values=["X", "Y"], comparison="more_than"
    )
    assert counted.kind == "count_compare"
    assert counted.comparison == "gt"
    with pytest.raises(ValidationError):
        CspConstraintSpec(kind="count_compare", comparison="sideways")


def test_nested_sub_constraints_are_validated():
    structure = CspGameStructure(
        domains=[CspDomainSpec(id="seat", values=["0", "1"], topology="linear")],
        variables=[CspVariableSpec(id="A", domain="seat")],
        constraints=[
            CspConstraintSpec(
                kind="any",
                constraints=[CspConstraintSpec(kind="eq", variables=["Z"], values=["0"])],
            )
        ],
    )
    with pytest.raises(CspBuildError):
        build_csp_game(structure)


def test_question_assumptions_are_built_and_validated():
    game = build_csp_game(_seat_game())
    structure = CspQuestionStructure(
        kind="could",
        options=[CspOptionSpec(constraints=[CspConstraintSpec(kind="eq", variables=["B"], values=["1"])])],
        assumptions=[CspConstraintSpec(kind="eq", variables=["A"], values=["0"])],
    )
    question = build_csp_question(structure, game=game)
    assert [statement.kind for statement in question.assumptions] == ["eq"]

    dangling = CspQuestionStructure(
        kind="could",
        options=[CspOptionSpec(constraints=[CspConstraintSpec(kind="eq", variables=["A"], values=["0"])])],
        assumptions=[CspConstraintSpec(kind="eq", variables=["Z"], values=["0"])],
    )
    with pytest.raises(CspBuildError):
        build_csp_question(dangling, game=game)

    bad_value = CspQuestionStructure(
        kind="could",
        options=[CspOptionSpec(constraints=[CspConstraintSpec(kind="eq", variables=["A"], values=["0"])])],
        assumptions=[CspConstraintSpec(kind="eq", variables=["A"], values=["9"])],
    )
    with pytest.raises(CspBuildError):
        build_csp_question(bad_value, game=game)
