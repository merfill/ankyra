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


def test_complete_list_value_target_must_be_a_declared_value():
    game = build_csp_game(_seat_game())  # domain "seat" over ["0", "1", "2"]
    question = build_csp_question(
        CspQuestionStructure(
            kind="complete_list",
            target="0",
            target_kind="value",
            options=[CspOptionSpec(values=["A"])],
        ),
        game=game,
    )
    assert question.target_kind == "value"
    # A value that no domain declares is out of fragment, not a silent no-op.
    with pytest.raises(CspBuildError):
        build_csp_question(
            CspQuestionStructure(
                kind="complete_list",
                target="nowhere",
                target_kind="value",
                options=[CspOptionSpec(values=["A"])],
            ),
            game=game,
        )


def test_complete_list_target_kind_aliases_and_mislabel():
    # "values" normalizes to the value kind and "all" to the must list mode.
    spec = CspQuestionStructure(
        kind="complete_list",
        target="bottom",
        target_kind="values",
        list_mode="all",
        options=[],
    )
    assert spec.target_kind == "value"
    assert spec.list_mode == "must"
    with pytest.raises(ValidationError):
        CspQuestionStructure(kind="complete_list", target="x", target_kind="sideways", options=[])


def _packed_game() -> CspGameStructure:
    return CspGameStructure(
        domains=[
            CspDomainSpec(id="screen", values=["s1", "s2"], topology="set"),
            CspDomainSpec(id="time", values=["7", "8"], topology="linear"),
            CspDomainSpec(
                id="slot",
                values=["s1_7", "s1_8", "s2_7", "s2_8"],
                topology="set",
                factors=["screen", "time"],
                value_factors={
                    "s1_7": ["s1", "7"], "s1_8": ["s1", "8"],
                    "s2_7": ["s2", "7"], "s2_8": ["s2", "8"],
                },
            ),
        ],
        variables=[CspVariableSpec(id="A", domain="slot"), CspVariableSpec(id="B", domain="slot")],
    )


def test_product_domain_and_factor_projection_build():
    structure = _packed_game()
    structure.constraints.append(
        CspConstraintSpec(kind="same_group", variables=["A", "B"], factor="screen")
    )
    game = build_csp_game(structure)
    assert game.domains[2].factors == ["screen", "time"]
    assert game.constraints[0].factor == "screen"


def test_malformed_product_domains_are_refused():
    # Missing factor decomposition.
    bad = _packed_game()
    bad.domains[2].value_factors.pop("s2_8")
    with pytest.raises(CspBuildError):
        build_csp_game(bad)
    # A factor value outside its factor domain.
    bad = _packed_game()
    bad.domains[2].value_factors["s1_7"] = ["s9", "7"]
    with pytest.raises(CspBuildError):
        build_csp_game(bad)
    # Unknown factor domain.
    bad = _packed_game()
    bad.domains[2].factors = ["screen", "day"]
    with pytest.raises(CspBuildError):
        build_csp_game(bad)
    # An atomic domain must not declare value_factors.
    bad = _packed_game()
    bad.domains[0].value_factors = {"s1": ["s1"]}
    with pytest.raises(CspBuildError):
        build_csp_game(bad)


def test_factor_constraints_are_validated():
    # A factor on a variable whose domain has it is fine.
    structure = _packed_game()
    structure.constraints.append(
        CspConstraintSpec(kind="eq", variables=["A"], values=["7"], factor="time")
    )
    build_csp_game(structure)
    # A variable whose domain lacks the factor is refused.
    bad = _packed_game()
    bad.variables.append(CspVariableSpec(id="C", domain="screen"))
    bad.constraints.append(
        CspConstraintSpec(kind="eq", variables=["C"], values=["7"], factor="time")
    )
    with pytest.raises(CspBuildError):
        build_csp_game(bad)
    # A factor on all_different is meaningless.
    bad = _packed_game()
    bad.constraints.append(
        CspConstraintSpec(kind="all_different", variables=["A", "B"], factor="time")
    )
    with pytest.raises(CspBuildError):
        build_csp_game(bad)
    # A value outside the factor domain is refused.
    bad = _packed_game()
    bad.constraints.append(
        CspConstraintSpec(kind="eq", variables=["A"], values=["9"], factor="time")
    )
    with pytest.raises(CspBuildError):
        build_csp_game(bad)


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


def test_empty_composite_constraints_are_refused():
    # An empty all/any evaluates vacuously (True/False) and silently changes the
    # semantics; it is a build error, not a guess.
    for kind in ("all", "any"):
        structure = CspGameStructure(
            domains=[CspDomainSpec(id="seat", values=["0", "1"], topology="linear")],
            variables=[CspVariableSpec(id="A", domain="seat")],
            constraints=[CspConstraintSpec(kind=kind, constraints=[])],
        )
        with pytest.raises(CspBuildError):
            build_csp_game(structure)


def test_not_needs_exactly_one_sub_constraint():
    def game(constraints):
        return CspGameStructure(
            domains=[CspDomainSpec(id="seat", values=["0", "1"], topology="linear")],
            variables=[CspVariableSpec(id="A", domain="seat")],
            constraints=constraints,
        )

    with pytest.raises(CspBuildError):
        build_csp_game(game([CspConstraintSpec(kind="not", constraints=[])]))
    good = CspConstraintSpec(
        kind="not",
        constraints=[CspConstraintSpec(kind="eq", variables=["A"], values=["0"])],
    )
    build_csp_game(game([good]))


def test_count_needs_a_count_and_a_group():
    # A count group is the SET of declared values; a missing count or an empty group is
    # a build error, while several values are a meaningful union (not a silent drop).
    def game(constraint):
        return CspGameStructure(
            domains=[CspDomainSpec(id="g", values=["X", "Y"], topology="set")],
            variables=[CspVariableSpec(id="A", domain="g"), CspVariableSpec(id="B", domain="g")],
            constraints=[constraint],
        )

    with pytest.raises(CspBuildError):
        build_csp_game(game(CspConstraintSpec(kind="count", variables=["A", "B"], values=["X"], count=None)))
    with pytest.raises(CspBuildError):
        build_csp_game(game(CspConstraintSpec(kind="count", variables=["A", "B"], values=[], count=1)))
    build_csp_game(game(CspConstraintSpec(kind="count", variables=["A", "B"], values=["X"], count=1)))
    build_csp_game(game(CspConstraintSpec(kind="count", variables=["A", "B"], values=["X", "Y"], count=1)))


def test_count_compare_needs_two_distinct_group_values():
    def game(constraint):
        return CspGameStructure(
            domains=[CspDomainSpec(id="g", values=["X", "Y"], topology="set")],
            variables=[CspVariableSpec(id="A", domain="g"), CspVariableSpec(id="B", domain="g")],
            constraints=[constraint],
        )

    with pytest.raises(CspBuildError):
        build_csp_game(game(CspConstraintSpec(kind="count_compare", variables=["A", "B"], values=["X"], comparison="gt")))
    with pytest.raises(CspBuildError):
        build_csp_game(game(CspConstraintSpec(kind="count_compare", variables=["A", "B"], values=["X", "X"], comparison="gt")))
    build_csp_game(game(CspConstraintSpec(kind="count_compare", variables=["A", "B"], values=["X", "Y"], comparison="gt")))


def test_counted_group_in_an_option_is_checked():
    game = build_csp_game(_seat_game())
    bad = CspQuestionStructure(
        kind="could",
        options=[
            CspOptionSpec(
                constraints=[CspConstraintSpec(kind="count", variables=["A", "B"], values=[], count=1)]
            )
        ],
    )
    with pytest.raises(CspBuildError):
        build_csp_question(bad, game=game)
    good = CspQuestionStructure(
        kind="could",
        options=[
            CspOptionSpec(
                constraints=[CspConstraintSpec(kind="count", variables=["A", "B"], values=["0", "1"], count=1)]
            )
        ],
    )
    build_csp_question(good, game=game)


def test_conditional_needs_both_halves():
    def game(constraints):
        return CspGameStructure(
            domains=[CspDomainSpec(id="seat", values=["0", "1"], topology="linear")],
            variables=[CspVariableSpec(id="A", domain="seat")],
            constraints=constraints,
        )

    eq = CspConstraintSpec(kind="eq", variables=["A"], values=["0"])
    with pytest.raises(CspBuildError):
        build_csp_game(game([CspConstraintSpec(kind="conditional", condition=eq)]))
    with pytest.raises(CspBuildError):
        build_csp_game(game([CspConstraintSpec(kind="conditional", consequence=eq)]))
    build_csp_game(game([CspConstraintSpec(kind="conditional", condition=eq, consequence=eq)]))


def test_empty_option_sub_constraints_are_refused():
    game = build_csp_game(_seat_game())
    structure = CspQuestionStructure(
        kind="could",
        options=[CspOptionSpec(constraints=[CspConstraintSpec(kind="any", constraints=[])])],
    )
    with pytest.raises(CspBuildError):
        build_csp_question(structure, game=game)


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
