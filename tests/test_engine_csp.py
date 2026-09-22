"""Unit tests for the L3 finite-domain CSP engine (``docs/l3_plan.md`` §15)."""

from __future__ import annotations

import pytest

from ankyra.engine.csp import (
    CspConstraint,
    CspDomain,
    CspGame,
    CspOption,
    CspQuestion,
    CspVariable,
    countermodel,
    decide_question,
    enumerate_models,
    satisfiable,
)

C = CspConstraint


def _game(domain: CspDomain, names: str, constraints: list[CspConstraint]) -> CspGame:
    return CspGame(
        domains=[domain],
        variables=[CspVariable(id=name, domain=domain.id) for name in names.split()],
        constraints=constraints,
    )


def _eq(name: str, value: str) -> CspConstraint:
    return C(kind="eq", variables=[name], values=[value])


def _seat(n: int, topology: str = "linear") -> CspDomain:
    return CspDomain(id=f"seat{n}", values=[str(i) for i in range(n)], topology=topology)


def test_order_and_all_different() -> None:
    game = _game(
        _seat(3),
        "A B C",
        [
            C(kind="all_different", variables=["A", "B", "C"]),
            C(kind="order", variables=["A", "B"]),
        ],
    )
    result = enumerate_models(game, limit=100)
    assert result.status == "sat"
    assert result.models
    assert all(int(model["A"]) < int(model["B"]) for model in result.models)
    # A<B over 3 seats leaves the third seat for C: three models.
    assert len(result.models) == 3


def test_immediate_order_and_unsat() -> None:
    game = _game(
        _seat(3),
        "A B",
        [
            C(kind="order", variables=["A", "B"], immediate=True),
            _eq("A", "2"),
        ],
    )
    assert satisfiable(game).status == "unsat"
    game_ok = _game(_seat(3), "A B", [C(kind="order", variables=["A", "B"], immediate=True), _eq("A", "0")])
    assert satisfiable(game_ok).model == {"A": "0", "B": "1"}


def test_circular_adjacency_wraps() -> None:
    circular = _game(
        _seat(3, "circular"),
        "A B",
        [_eq("A", "0"), _eq("B", "2"), C(kind="adjacent", variables=["A", "B"])],
    )
    assert satisfiable(circular).status == "sat"
    linear = _game(
        _seat(3, "linear"),
        "A B",
        [_eq("A", "0"), _eq("B", "2"), C(kind="adjacent", variables=["A", "B"])],
    )
    assert satisfiable(linear).status == "unsat"


def test_not_adjacent() -> None:
    game = _game(
        _seat(4, "circular"),
        "A B",
        [_eq("A", "0"), _eq("B", "2"), C(kind="not_adjacent", variables=["A", "B"])],
    )
    assert satisfiable(game).status == "sat"
    violating = _game(
        _seat(4, "circular"),
        "A B",
        [_eq("A", "0"), _eq("B", "1"), C(kind="not_adjacent", variables=["A", "B"])],
    )
    assert satisfiable(violating).status == "unsat"


def test_neq_two_variables_and_value() -> None:
    game = _game(_seat(2), "A B", [C(kind="neq", variables=["A", "B"]), _eq("A", "0")])
    assert satisfiable(game).model == {"A": "0", "B": "1"}
    with_value = _game(_seat(2), "A", [C(kind="neq", variables=["A"], values=["0"])])
    assert satisfiable(with_value).model == {"A": "1"}


def test_group_relations() -> None:
    domain = CspDomain(id="g", values=["X", "Y"], topology="set")
    same = _game(domain, "A B", [C(kind="same_group", variables=["A", "B"])])
    assert satisfiable(same).status == "sat"
    different = _game(domain, "A B", [_eq("A", "X"), C(kind="different_group", variables=["A", "B"])])
    assert satisfiable(different).model == {"A": "X", "B": "Y"}


def test_count_modes() -> None:
    domain = CspDomain(id="g", values=["X", "Y"], topology="set")
    base = [C(kind="count", variables=["A", "B", "C"], values=["X"], count=2, count_mode="exactly")]
    assert satisfiable(_game(domain, "A B C", base)).status == "sat"
    at_least = _game(
        domain,
        "A B C",
        [C(kind="count", variables=["A", "B", "C"], values=["X"], count=2, count_mode="at_least")],
    )
    assert satisfiable(at_least).status == "sat"
    at_most_always_true = _game(
        domain,
        "A B C",
        [C(kind="count", variables=["A", "B", "C"], values=["X"], count=3, count_mode="at_most")],
    )
    assert satisfiable(at_most_always_true).status == "sat"
    exactly_one = _game(
        domain,
        "A B",
        [C(kind="count", variables=["A", "B"], values=["X"], count=1, count_mode="exactly")],
    )
    assert satisfiable(exactly_one).status == "sat"
    # X for at_least 3 of only 2 candidates is impossible.
    unreachable = _game(
        domain,
        "A B",
        [C(kind="count", variables=["A", "B"], values=["X"], count=3, count_mode="at_least")],
    )
    assert satisfiable(unreachable).status == "unsat"


def test_count_group_is_a_set_of_values() -> None:
    # A count group is the SET of declared values (membership), so a group that spans the
    # whole domain counts every variable, and a subset counts the variables in it.
    countries = CspDomain(id="c", values=["V", "Y", "Z"], topology="set")
    # Both A and B always take a country, so "exactly one is on V, Y or Z" is impossible.
    everything = C(
        kind="count", variables=["A", "B"], values=["V", "Y", "Z"], count=1, count_mode="exactly"
    )
    assert satisfiable(_game(countries, "A B", []), [everything]).status == "unsat"

    region = CspDomain(id="region", values=["east", "west"], topology="set")
    exactly_one_east = C(
        kind="count", variables=["A", "B"], values=["east"], count=1, count_mode="exactly"
    )
    either_region = C(
        kind="count", variables=["A", "B"], values=["east", "west"], count=2, count_mode="exactly"
    )
    assert satisfiable(_game(region, "A B", [exactly_one_east])).status == "sat"
    assert satisfiable(_game(region, "A B", [either_region])).status == "sat"


def test_conditional_prunes() -> None:
    domain = CspDomain(id="g", values=["X", "Y"], topology="set")
    game = _game(
        domain,
        "C D",
        [_eq("D", "Y"), C(kind="conditional", condition=_eq("C", "X"), consequence=_eq("D", "X"))],
    )
    # C = X would force D = X, contradicting D = Y, so the only model is C = Y.
    assert satisfiable(game).model == {"C": "Y", "D": "Y"}
    witness = satisfiable(_game(domain, "C D", [_eq("C", "X")]))
    assert witness.status == "sat"


def test_countermodel_and_must() -> None:
    game = _game(
        _seat(4),
        "A B C D",
        [
            C(kind="all_different", variables=["A", "B", "C", "D"]),
            C(kind="order", variables=["A", "B"]),
            C(kind="order", variables=["B", "C"]),
        ],
    )
    # "B is not 4" holds in every model: no countermodel.
    assert countermodel(game, [C(kind="neq", variables=["B"], values=["4"])]).status == "unsat"
    # "B is 2" has a countermodel (B can be 3).
    assert countermodel(game, [_eq("B", "2")]).status == "sat"


def test_decide_must() -> None:
    game = _game(
        _seat(3),
        "A B",
        [_eq("A", "0"), C(kind="order", variables=["A", "B"])],
    )
    question = CspQuestion(
        kind="must",
        options=[
            CspOption(constraints=[_eq("B", "2")]),
            CspOption(constraints=[_eq("A", "0")]),
        ],
    )
    decision = decide_question(game, question)
    # "A is 0" is true in every model; "B is 2" is not.
    assert decision.status == "decided"
    assert decision.index == 1


def test_decide_could_is_ambiguous_when_two_options_possible() -> None:
    game = _game(_seat(2), "A", [])
    question = CspQuestion(
        kind="could",
        options=[
            CspOption(constraints=[_eq("A", "0")]),
            CspOption(constraints=[_eq("A", "1")]),
        ],
    )
    decision = decide_question(game, question)
    assert decision.status == "ambiguous"
    assert decision.verified == [0, 1]


def test_decide_complete_list() -> None:
    game = _game(
        _seat(3),
        "A B C",
        [
            C(kind="all_different", variables=["A", "B", "C"]),
            C(kind="order", variables=["A", "B"]),
            C(kind="adjacent", variables=["A", "C"]),
        ],
    )
    question = CspQuestion(
        kind="complete_list",
        target="A",
        options=[
            CspOption(values=["0", "1"]),
            CspOption(values=["0"]),
        ],
    )
    decision = decide_question(game, question)
    assert decision.status == "decided"
    assert decision.index == 0
    assert decision.complete_list == ["0", "1"]


def test_complete_list_over_a_value_unions_the_variables() -> None:
    # "the books that could be on the bottom shelf": across models each book can be the
    # one on the bottom, so a "could" list unions the per-model sets.
    shelf = CspDomain(id="shelf", values=["top", "bottom"], topology="set")
    game = _game(shelf, "A B", [C(kind="all_different", variables=["A", "B"])])
    could = CspQuestion(
        kind="complete_list",
        target="bottom",
        target_kind="value",
        list_mode="could",
        options=[
            CspOption(values=["A", "B"]),
            CspOption(values=["A"]),
            CspOption(values=["B"]),
            CspOption(values=[]),
        ],
    )
    decision = decide_question(game, could)
    assert decision.index == 0
    assert decision.complete_list == ["A", "B"]

    must = could.model_copy(
        update={
            "list_mode": "must",
            "options": [
                CspOption(values=[]),
                CspOption(values=["A"]),
                CspOption(values=["B"]),
                CspOption(values=["A", "B"]),
            ],
        }
    )
    # No book is on the bottom in every model, so the "must" list is empty.
    must_decision = decide_question(game, must)
    assert must_decision.index == 0
    assert must_decision.complete_list == []


def test_complete_list_over_a_variable_can_intersect_models() -> None:
    # A is always 0, so a "must" list over the variable A is ["0"] even though the list
    # mode is normally a union.
    game = _game(_seat(2), "A B", [_eq("A", "0")])
    question = CspQuestion(
        kind="complete_list",
        target="A",
        target_kind="variable",
        list_mode="must",
        options=[CspOption(values=["0"]), CspOption(values=["1"]), CspOption(values=[])],
    )
    decision = decide_question(game, question)
    assert decision.index == 0
    assert decision.complete_list == ["0"]


def test_incomplete_enumeration_is_insufficient_not_a_partial_list() -> None:
    # A list read from a truncated enumeration could silently omit an item; it must be
    # the honest insufficient, never a partial complete_list.
    game = _game(_seat(2), "A B", [C(kind="all_different", variables=["A", "B"])])
    question = CspQuestion(
        kind="complete_list",
        target="A",
        options=[CspOption(values=["0", "1"])],
    )
    decision = decide_question(game, question, budget=1)
    assert decision.status == "insufficient"
    assert decision.index is None


def _slots_game() -> CspGame:
    """A packed slot domain: a slot is a (screen, time) pair (D-L3-11)."""
    slots = ["s1_7", "s1_8", "s1_9", "s2_7", "s2_8", "s2_9"]
    return CspGame(
        domains=[
            CspDomain(id="screen", values=["s1", "s2"], topology="set"),
            CspDomain(id="time", values=["7", "8", "9"], topology="linear"),
            CspDomain(
                id="slot",
                values=slots,
                topology="set",
                factors=["screen", "time"],
                value_factors={slot: slot.split("_") for slot in slots},
            ),
        ],
        variables=[CspVariable(id="A", domain="slot"), CspVariable(id="B", domain="slot")],
        constraints=[C(kind="all_different", variables=["A", "B"])],
    )


def test_factor_projection_is_load_bearing() -> None:
    game = _slots_game()
    forward = C(kind="order", variables=["A", "B"], factor="time")
    backward = C(kind="order", variables=["B", "A"], factor="time")
    assert satisfiable(game, [forward]).status == "sat"
    # Time order is irreflexive, and the projection is what makes "before" compare the
    # time component rather than the packed value.
    assert satisfiable(game, [forward, backward]).status == "unsat"
    # "Same screen" is not equal packed values: two different slots on s1 satisfy it.
    same = C(kind="same_group", variables=["A", "B"], factor="screen")
    different = C(kind="different_group", variables=["A", "B"], factor="screen")
    assert satisfiable(game, [same]).status == "sat"
    assert satisfiable(game, [same, different]).status == "unsat"


def test_factor_projection_compares_factor_values() -> None:
    game = _slots_game()
    on_s1 = C(kind="eq", variables=["A"], values=["s1"], factor="screen")
    at_7 = C(kind="eq", variables=["A"], values=["7"], factor="time")
    counted = C(
        kind="count",
        variables=["A", "B"],
        values=["s1"],
        count=2,
        count_mode="exactly",
        factor="screen",
    )
    assert satisfiable(game, [on_s1, at_7]).status == "sat"
    assert countermodel(game, [on_s1, counted]).status == "sat"  # B need not be on s1
    assert satisfiable(game, [on_s1, C(kind="eq", variables=["B"], values=["s1"], factor="screen"), counted]).status == "sat"


def test_boolean_any_and_all_compose_relations() -> None:
    # "A is either before both B and C or after both" = A is not between B and C.
    game = _game(
        _seat(3),
        "A B C",
        [
            C(kind="all_different", variables=["A", "B", "C"]),
            C(
                kind="any",
                constraints=[
                    C(kind="all", constraints=[C(kind="order", variables=["A", "B"]), C(kind="order", variables=["A", "C"])]),
                    C(kind="all", constraints=[C(kind="order", variables=["B", "A"]), C(kind="order", variables=["C", "A"])]),
                ],
            ),
        ],
    )
    assert countermodel(game, [C(kind="neq", variables=["A"], values=["1"])]).status == "unsat"
    assert satisfiable(game, [C(kind="eq", variables=["A"], values=["1"])]).status == "unsat"


def test_boolean_not_negates_a_sub_constraint() -> None:
    game = _game(
        _seat(3),
        "A B",
        [C(kind="all_different", variables=["A", "B"]), C(kind="not", constraints=[C(kind="eq", variables=["A"], values=["0"])])],
    )
    assert satisfiable(game, [C(kind="eq", variables=["A"], values=["0"])]).status == "unsat"
    assert satisfiable(game).model is not None


def test_count_compare_across_groups() -> None:
    domain = CspDomain(id="g", values=["X", "Y"], topology="set")
    game = _game(
        domain,
        "A B C D E",
        [
            C(kind="eq", variables=["A"], values=["Y"]),
            C(kind="eq", variables=["B"], values=["Y"]),
            C(
                kind="count_compare",
                variables=["A", "B", "C", "D", "E"],
                values=["X", "Y"],
                comparison="gt",
            ),
        ],
    )
    # Y count is 2 (A, B), so X count must be 3: C, D and E are all X.
    assert countermodel(game, [C(kind="eq", variables=["C"], values=["X"])]).status == "unsat"
    assert satisfiable(game, [C(kind="eq", variables=["C"], values=["Y"])]).status == "unsat"


def test_decide_must_be_false() -> None:
    game = _game(
        _seat(3),
        "A B C",
        [
            C(kind="all_different", variables=["A", "B", "C"]),
            C(kind="order", variables=["A", "B"]),
        ],
    )
    question = CspQuestion(
        kind="must_be_false",
        options=[
            CspOption(constraints=[_eq("A", "0")]),  # possible
            CspOption(constraints=[_eq("A", "1")]),  # possible
            CspOption(constraints=[_eq("B", "0")]),  # impossible -> the answer
        ],
    )
    decision = decide_question(game, question)
    assert decision.status == "decided"
    assert decision.index == 2


def test_decide_must_be_false_ambiguous() -> None:
    game = _game(_seat(2), "A", [])
    question = CspQuestion(
        kind="must_be_false",
        options=[CspOption(constraints=[_eq("A", "2")]), CspOption(constraints=[_eq("A", "3")])],
    )
    assert decide_question(game, question).status == "ambiguous"


def test_question_assumptions_pin_the_answer() -> None:
    game = _game(
        _seat(3),
        "A B C",
        [
            C(kind="all_different", variables=["A", "B", "C"]),
            C(kind="order", variables=["A", "B"]),
        ],
    )
    question = CspQuestion(
        kind="could",
        options=[
            CspOption(constraints=[_eq("C", "2")]),
            CspOption(constraints=[_eq("C", "1")]),  # only under A=0, B=2
            CspOption(constraints=[_eq("C", "0")]),
        ],
        assumptions=[_eq("A", "0"), _eq("B", "2")],
    )
    assert decide_question(game, question).index == 1
    # Without the assumptions two options are consistent, so the decision is ambiguous.
    bare = CspQuestion(kind="could", options=question.options)
    assert decide_question(game, bare).status == "ambiguous"


def test_inconsistent_assumptions_verify_nothing() -> None:
    game = _game(
        _seat(3),
        "A B C",
        [
            C(kind="all_different", variables=["A", "B", "C"]),
            C(kind="order", variables=["A", "B"]),
        ],
    )
    question = CspQuestion(
        kind="could",
        options=[CspOption(constraints=[_eq("C", "0")])],
        assumptions=[_eq("A", "1"), _eq("B", "0")],
    )
    assert decide_question(game, question).status == "unknown"


def test_budget_exhaustion_is_insufficient_not_a_guess() -> None:
    game = _game(_seat(4), "A B C D", [C(kind="all_different", variables=["A", "B", "C", "D"])])
    question = CspQuestion(kind="could", options=[CspOption(constraints=[_eq("A", "0")])])
    decision = decide_question(game, question, budget=1)
    assert decision.status == "insufficient"
    assert decision.index is None


def test_no_option_verified_is_unknown() -> None:
    game = _game(_seat(2), "A", [])
    question = CspQuestion(kind="could", options=[CspOption(constraints=[_eq("A", "9")])])
    assert decide_question(game, question).status == "unknown"


def test_variable_with_unknown_domain_raises() -> None:
    game = CspGame(
        domains=[_seat(2)],
        variables=[CspVariable(id="A", domain="missing")],
        constraints=[],
    )
    with pytest.raises(ValueError):
        satisfiable(game)
