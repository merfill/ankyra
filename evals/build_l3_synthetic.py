"""Build the committed L3 synthetic collection (deterministic, LLM-free).

The L3 engine is gated by a structural collection: each case is a fully structured
CSP game/question with an independently written expected decision, graded by
``evals.l3_synthetic``. No LLM, no natural language, zero provider variance.

Coverage (``docs/l3_plan.md`` §13.1): every constraint kind (``all_different``, ``eq``,
``neq``, ``order``, ``adjacent``, ``not_adjacent``, ``same_group``, ``different_group``,
``count``, ``conditional``) and every question semantics (``not_violate``, ``must``,
``could``, ``complete_list``), plus mandatory negative controls: no option verified is
``unknown``; two verified options is ``ambiguous``; an exhausted budget is
``insufficient`` (never a picked option); a ``must`` with a counter-model is not
chosen; a conditional must prune a model (dropping it would make a second option
possible).

Usage:
    uv run python -m evals.build_l3_synthetic [--out PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "l3_synthetic.jsonl"


def _dom(id: str, values: list[str], topology: str = "set") -> dict:
    return {"id": id, "values": list(values), "topology": topology}


def _var(id: str, domain: str) -> dict:
    return {"id": id, "domain": domain, "quote": None}


def _c(
    kind: str,
    variables: list[str] | None = None,
    values: list[str] | None = None,
    *,
    immediate: bool = False,
    count: int | None = None,
    count_mode: str = "exactly",
    comparison: str | None = None,
    condition: dict | None = None,
    consequence: dict | None = None,
    constraints: list[dict] | None = None,
) -> dict:
    return {
        "kind": kind,
        "variables": list(variables or []),
        "values": list(values or []),
        "immediate": immediate,
        "count": count,
        "count_mode": count_mode,
        "comparison": comparison,
        "condition": condition,
        "consequence": consequence,
        "constraints": list(constraints or []),
        "quote": None,
    }


def _eq(name: str, value: str) -> dict:
    return _c("eq", [name], [value])


def _neq(name: str, value: str) -> dict:
    return _c("neq", [name], [value])


def _opt(constraints: list[dict] | None = None, values: list[str] | None = None) -> dict:
    return {"constraints": list(constraints or []), "values": list(values or []), "quote": None}


def _arr(*pairs: str) -> list[dict]:
    return [_eq(pairs[index], pairs[index + 1]) for index in range(0, len(pairs), 2)]


def _game(domains: list[dict], variables: list[dict], constraints: list[dict]) -> dict:
    return {"domains": domains, "variables": variables, "constraints": constraints, "source_text": ""}


def _question(kind: str, options: list[dict], target: str | None = None) -> dict:
    return {"kind": kind, "options": options, "target": target, "quote": None}


def _case(
    id: str,
    mechanism: str,
    uses: list[str],
    game: dict,
    question: dict,
    expected: dict,
    *,
    budget: int | None = None,
) -> dict:
    return {
        "id": id,
        "mechanism": mechanism,
        "uses": list(uses),
        "question_kind": question["kind"],
        "game": game,
        "question": question,
        "expected": expected,
        "budget": budget,
    }


# --- ordering & all-different -----------------------------------------------------


def _order_cases() -> list[dict]:
    linear = [_dom("s4", ["0", "1", "2", "3"], "linear")]
    vars4 = [_var(name, "s4") for name in "ABCD"]
    game = _game(
        linear,
        vars4,
        [
            _c("all_different", ["A", "B", "C", "D"]),
            _c("order", ["A", "B"]),
            _c("order", ["B", "C"]),
        ],
    )
    # A < B < C; B is 1 or 2 (never 3), so "B is not 3" holds in every model.
    q_must = _question(
        "must",
        [
            _opt([_eq("B", "3")]),
            _opt([_eq("B", "1")]),
            _opt([_eq("C", "2")]),
            _opt([_eq("A", "0")]),
            _opt([_neq("B", "3")]),
        ],
    )
    immediate = _game(
        [_dom("si", ["0", "1", "2", "3"], "linear")],
        [_var(name, "si") for name in "ABC"],
        [
            _c("all_different", ["A", "B", "C"]),
            _c("order", ["A", "B"], immediate=True),
        ],
    )
    # A immediately before B; A is 0, 1 or 2 (never 3).
    q_immediate = _question(
        "must",
        [
            _opt([_eq("A", "3")]),
            _opt([_eq("A", "2")]),
            _opt([_eq("B", "0")]),
            _opt([_neq("A", "3")]),
            _opt([_eq("C", "3")]),
        ],
    )
    return [
        _case("linear-order-must-01", "order", ["order", "all_different"], game, q_must, {"status": "decided", "index": 4}),
        _case(
            "immediate-order-must-02",
            "order",
            ["order", "all_different"],
            immediate,
            q_immediate,
            {"status": "decided", "index": 3},
        ),
    ]


def _all_different_cases() -> list[dict]:
    game = _game(
        [_dom("s3", ["0", "1", "2"], "linear")],
        [_var(name, "s3") for name in "ABC"],
        [_c("all_different", ["A", "B", "C"])],
    )
    q = _question(
        "not_violate",
        [
            _opt(_arr("A", "0", "B", "0", "C", "1")),  # duplicate
            _opt(_arr("A", "0", "B", "1", "C", "1")),  # duplicate
            _opt(_arr("A", "0", "B", "1", "C", "2")),  # a permutation
            _opt(_arr("A", "2", "B", "2", "C", "0")),  # duplicate
            _opt(_arr("A", "1", "B", "1", "C", "2")),  # duplicate
        ],
    )
    return [_case("all-different-not-violate-03", "all_different", ["all_different"], game, q, {"status": "decided", "index": 2})]


# --- eq / neq ---------------------------------------------------------------------


def _neq_cases() -> list[dict]:
    game = _game(
        [_dom("s2", ["0", "1"], "set")],
        [_var("A", "s2"), _var("B", "s2")],
        [_neq("A", "0"), _eq("B", "1")],
    )
    # A = 1 and B = 1 is the only model; exactly one option is consistent.
    q = _question(
        "could",
        [
            _opt([*_arr("A", "0", "B", "1")]),
            _opt([*_arr("A", "1", "B", "0")]),
            _opt([*_arr("A", "1", "B", "1")]),
            _opt([*_arr("A", "0", "B", "0")]),
            _opt([_eq("A", "2")]),
        ],
    )
    return [_case("neq-value-could-04", "neq", ["neq", "eq"], game, q, {"status": "decided", "index": 2})]


# --- adjacency --------------------------------------------------------------------


def _adjacency_cases() -> list[dict]:
    linear = _game(
        [_dom("s3", ["0", "1", "2"], "linear")],
        [_var("A", "s3"), _var("B", "s3")],
        [_c("adjacent", ["A", "B"]), _eq("A", "0")],
    )
    q_linear = _question(
        "not_violate",
        [
            _opt(_arr("A", "0", "B", "1")),  # valid
            _opt(_arr("A", "0", "B", "2")),  # not adjacent
            _opt(_arr("A", "1", "B", "0")),  # A != 0
            _opt(_arr("A", "0", "B", "0")),  # not adjacent
            _opt(_arr("A", "2", "B", "1")),  # A != 0
        ],
    )
    # Circular wrap: on a three-seat circle 0 and 2 are adjacent; on a line they are
    # not, so dropping the declared topology turns the only model into no model.
    circular = _game(
        [_dom("s3c", ["0", "1", "2"], "circular")],
        [_var("A", "s3c"), _var("B", "s3c")],
        [_eq("A", "0"), _eq("B", "2"), _c("adjacent", ["A", "B"])],
    )
    q_circular = _question(
        "not_violate",
        [
            _opt(_arr("A", "0", "B", "2")),  # valid only with the circular topology
            _opt(_arr("A", "0", "B", "1")),  # B != 2
            _opt(_arr("A", "0", "B", "0")),  # B != 2
            _opt(_arr("A", "1", "B", "2")),  # A != 0
            _opt(_arr("A", "2", "B", "0")),  # A != 0
        ],
    )
    not_adjacent = _game(
        [_dom("s4c", ["0", "1", "2", "3"], "circular")],
        [_var("A", "s4c"), _var("B", "s4c")],
        [_eq("A", "0"), _c("not_adjacent", ["A", "B"]), _c("neq", ["A", "B"])],
    )
    # Neighbours of 0 are 1 and 3, so "not adjacent" allows 0 or 2; A != B forces 2.
    q_not_adjacent = _question(
        "must",
        [
            _opt([_eq("B", "1")]),
            _opt([_eq("B", "3")]),
            _opt([_eq("B", "2")]),
            _opt([_eq("B", "0")]),
            _opt([_neq("B", "2")]),
        ],
    )
    return [
        _case("adjacent-linear-not-violate-05", "adjacent", ["adjacent", "eq"], linear, q_linear, {"status": "decided", "index": 0}),
        _case(
            "adjacent-circular-wrap-06",
            "adjacent",
            ["adjacent", "eq"],
            circular,
            q_circular,
            {"status": "decided", "index": 0},
        ),
        _case(
            "not-adjacent-must-07",
            "not_adjacent",
            ["not_adjacent", "neq", "eq"],
            not_adjacent,
            q_not_adjacent,
            {"status": "decided", "index": 2},
        ),
    ]


# --- grouping ---------------------------------------------------------------------


def _group_cases() -> list[dict]:
    same = _game(
        [_dom("g", ["X", "Y"], "set")],
        [_var("A", "g"), _var("B", "g")],
        [_c("same_group", ["A", "B"]), _eq("A", "X")],
    )
    q_same = _question(
        "must",
        [
            _opt([_eq("B", "X")]),  # true in every model
            _opt([_eq("B", "Y")]),
            _opt([_eq("A", "Y")]),
            _opt([_c("neq", ["A", "B"])]),
            _opt([_neq("B", "X")]),
        ],
    )
    different = _game(
        [_dom("g", ["X", "Y"], "set")],
        [_var("A", "g"), _var("B", "g")],
        [_c("different_group", ["A", "B"]), _eq("A", "X")],
    )
    q_different = _question(
        "must",
        [
            _opt([_eq("B", "Y")]),  # true in every model
            _opt([_eq("B", "X")]),
            _opt([_eq("A", "Y")]),
            _opt([_c("same_group", ["A", "B"])]),
            _opt([_neq("A", "X")]),
        ],
    )
    return [
        _case("same-group-must-08", "same_group", ["same_group", "eq"], same, q_same, {"status": "decided", "index": 0}),
        _case(
            "different-group-must-09",
            "different_group",
            ["different_group", "eq"],
            different,
            q_different,
            {"status": "decided", "index": 0},
        ),
    ]


# --- count ------------------------------------------------------------------------


def _count_cases() -> list[dict]:
    exactly = _game(
        [_dom("g", ["X", "Y"], "set")],
        [_var(name, "g") for name in "ABC"],
        [
            _c("count", ["A", "B", "C"], ["X"], count=2, count_mode="exactly"),
            _eq("A", "X"),
            _eq("B", "Y"),
        ],
    )
    q_exactly = _question(
        "not_violate",
        [
            _opt(_arr("A", "X", "B", "Y", "C", "X")),  # valid, exactly two in X
            _opt(_arr("A", "X", "B", "X", "C", "Y")),  # B != Y
            _opt(_arr("A", "X", "B", "Y", "C", "Y")),  # only one in X
            _opt(_arr("A", "Y", "B", "X", "C", "X")),  # A != X
            _opt(_arr("A", "X", "B", "X", "C", "X")),  # three in X
        ],
    )
    at_most = _game(
        [_dom("g", ["X", "Y"], "set")],
        [_var(name, "g") for name in "ABC"],
        [
            _c("count", ["A", "B", "C"], ["X"], count=1, count_mode="at_most"),
            _eq("A", "X"),
        ],
    )
    q_at_most = _question(
        "not_violate",
        [
            _opt(_arr("A", "X", "B", "Y", "C", "Y")),  # valid, at most one in X
            _opt(_arr("A", "X", "B", "X", "C", "Y")),  # two in X
            _opt(_arr("A", "X", "B", "Y", "C", "X")),  # two in X
            _opt(_arr("A", "Y", "B", "Y", "C", "Y")),  # A != X
            _opt(_arr("A", "X", "B", "X", "C", "X")),  # three in X
        ],
    )
    impossible = _game(
        [_dom("g", ["X", "Y"], "set")],
        [_var("A", "g"), _var("B", "g")],
        [_c("count", ["A", "B"], ["X"], count=3, count_mode="at_least")],
    )
    q_impossible = _question(
        "could",
        [_opt([_eq("A", "X")]), _opt([_eq("A", "Y")])],
    )
    return [
        _case("count-exactly-not-violate-10", "count", ["count", "eq"], exactly, q_exactly, {"status": "decided", "index": 0}),
        _case("count-at-most-not-violate-11", "count", ["count", "eq"], at_most, q_at_most, {"status": "decided", "index": 0}),
        _case(
            "count-at-least-impossible-12",
            "count",
            ["count"],
            impossible,
            q_impossible,
            {"status": "unknown"},
        ),
    ]


# --- conditional ------------------------------------------------------------------


def _conditional_cases() -> list[dict]:
    pruning = _game(
        [_dom("g", ["X", "Y"], "set")],
        [_var(name, "g") for name in "ABC"],
        [
            _c("conditional", condition=_eq("A", "X"), consequence=_eq("B", "X")),
            _eq("B", "Y"),
        ],
    )
    # A = X would force B = X, contradicting B = Y, so A = Y in every model.
    q_pruning = _question(
        "must",
        [
            _opt([_eq("A", "Y")]),  # true in every model
            _opt([_eq("A", "X")]),
            _opt([_eq("B", "X")]),
            _opt([_eq("C", "X")]),
            _opt([_eq("C", "Y")]),
        ],
    )
    soundness = _game(
        [_dom("g", ["X", "Y"], "set")],
        [_var(name, "g") for name in "ABCD"],
        [
            _eq("A", "Y"),
            _eq("B", "X"),
            _eq("D", "Y"),
            _c("conditional", condition=_eq("C", "X"), consequence=_eq("D", "X")),
        ],
    )
    # C = X is possible only if the conditional is ignored; it prunes that model, so
    # only "C is Y" is consistent (a wrong engine would report an ambiguity).
    q_soundness = _question(
        "could",
        [
            _opt([_eq("C", "X")]),
            _opt([_eq("D", "X")]),
            _opt([_eq("C", "Y")]),
            _opt([_eq("A", "X")]),
            _opt([_eq("B", "Y")]),
        ],
    )
    return [
        _case("conditional-must-13", "conditional", ["conditional", "eq"], pruning, q_pruning, {"status": "decided", "index": 0}),
        _case(
            "conditional-soundness-could-14",
            "conditional",
            ["conditional", "eq"],
            soundness,
            q_soundness,
            {"status": "decided", "index": 2},
        ),
    ]


# --- boolean constraint composition (all / any / not) -----------------------------


def _boolean_cases() -> list[dict]:
    # "A is either before both B and C or after both" = A is not between B and C.
    nested = _game(
        [_dom("s3", ["0", "1", "2"], "linear")],
        [_var(name, "s3") for name in "ABC"],
        [
            _c("all_different", ["A", "B", "C"]),
            _c(
                "any",
                constraints=[
                    _c("all", constraints=[_c("order", ["A", "B"]), _c("order", ["A", "C"])]),
                    _c("all", constraints=[_c("order", ["B", "A"]), _c("order", ["C", "A"])]),
                ],
            ),
        ],
    )
    # A is 0 or 2 in every model, so "A is not 1" holds in every model.
    q_nested = _question(
        "must",
        [
            _opt([_eq("A", "1")]),
            _opt([_eq("A", "0")]),
            _opt([_eq("A", "2")]),
            _opt([_c("neq", ["A"], ["1"])]),
            _opt([_eq("B", "0")]),
        ],
    )
    negated = _game(
        [_dom("s3", ["0", "1", "2"], "linear")],
        [_var("A", "s3"), _var("B", "s3")],
        [
            _c("all_different", ["A", "B"]),
            _c("not", constraints=[_eq("A", "0")]),
        ],
    )
    q_negated = _question(
        "must",
        [
            _opt([_eq("A", "0")]),
            _opt([_c("neq", ["A"], ["0"])]),
            _opt([_eq("A", "1")]),
            _opt([_eq("A", "2")]),
            _opt([_c("neq", ["A"], ["1"])]),
        ],
    )
    return [
        _case(
            "boolean-any-all-25",
            "any",
            ["any", "all", "order", "all_different"],
            nested,
            q_nested,
            {"status": "decided", "index": 3},
        ),
        _case("boolean-not-26", "not", ["not", "eq", "all_different"], negated, q_negated, {"status": "decided", "index": 1}),
    ]


# --- count comparison across groups ----------------------------------------------


def _count_compare_cases() -> list[dict]:
    # X is assigned more often than Y; A and B are Y, so C, D and E are all X.
    game = _game(
        [_dom("g", ["X", "Y"], "set")],
        [_var(name, "g") for name in "ABCDE"],
        [
            _eq("A", "Y"),
            _eq("B", "Y"),
            _c("count_compare", ["A", "B", "C", "D", "E"], ["X", "Y"], comparison="gt"),
        ],
    )
    q = _question(
        "must",
        [
            _opt([_eq("C", "X")]),  # true in every model
            _opt([_eq("C", "Y")]),
            _opt([_eq("A", "X")]),
            _opt([_eq("B", "X")]),
            _opt([_eq("D", "Y")]),
        ],
    )
    return [
        _case(
            "count-compare-must-27",
            "count_compare",
            ["count_compare", "eq"],
            game,
            q,
            {"status": "decided", "index": 0},
        )
    ]


# --- complete list ----------------------------------------------------------------


def _complete_list_cases() -> list[dict]:
    game = _game(
        [_dom("s3", ["0", "1", "2"], "linear")],
        [_var(name, "s3") for name in "ABC"],
        [
            _c("all_different", ["A", "B", "C"]),
            _c("order", ["A", "B"]),
            _c("adjacent", ["A", "C"]),
        ],
    )
    q = _question(
        "complete_list",
        [
            _opt(values=["0", "1"]),  # complete and accurate
            _opt(values=["0"]),
            _opt(values=["1"]),
            _opt(values=["0", "1", "2"]),
            _opt(values=["2"]),
        ],
        target="A",
    )
    single = _game(
        [_dom("s3", ["0", "1", "2"], "linear")],
        [_var("A", "s3")],
        [_eq("A", "1")],
    )
    q_single = _question(
        "complete_list",
        [
            _opt(values=["1"]),
            _opt(values=["0"]),
            _opt(values=["2"]),
            _opt(values=["0", "1"]),
            _opt(values=[]),
        ],
        target="A",
    )
    return [
        _case("complete-list-15", "complete_list", ["all_different", "order", "adjacent"], game, q, {"status": "decided", "index": 0}),
        _case("complete-list-single-16", "complete_list", ["eq"], single, q_single, {"status": "decided", "index": 0}),
    ]


# --- must_be_false (cannot be true) ----------------------------------------------


def _must_be_false_cases() -> list[dict]:
    game = _game(
        [_dom("s3", ["0", "1", "2"], "linear")],
        [_var(name, "s3") for name in "ABC"],
        [
            _c("all_different", ["A", "B", "C"]),
            _c("order", ["A", "B"]),
        ],
    )
    # A < B over three seats; B is 1 or 2 in every model, so "B is 0" is the unique
    # option that cannot be true.
    q = _question(
        "must_be_false",
        [
            _opt([_eq("A", "0")]),  # possible
            _opt([_eq("A", "1")]),  # possible
            _opt([_eq("B", "0")]),  # impossible -> the answer
            _opt([_eq("B", "2")]),  # possible
            _opt([_eq("C", "0")]),  # possible
        ],
    )
    ambiguous = _game([_dom("s2", ["0", "1"], "set")], [_var("A", "s2")], [])
    q_ambiguous = _question("must_be_false", [_opt([_eq("A", "2")]), _opt([_eq("A", "3")])])
    return [
        _case("must-be-false-21", "must_be_false", ["all_different", "order"], game, q, {"status": "decided", "index": 2}),
        _case("must-be-false-ambiguous-22", "control", [], ambiguous, q_ambiguous, {"status": "ambiguous"}),
    ]


# --- question assumptions (Gamma, "if …") ----------------------------------------


def _assumption_cases() -> list[dict]:
    game = _game(
        [_dom("s3", ["0", "1", "2"], "linear")],
        [_var(name, "s3") for name in "ABC"],
        [
            _c("all_different", ["A", "B", "C"]),
            _c("order", ["A", "B"]),
        ],
    )
    # Under the assumption A=0 and B=2 the only model is C=1, so "C is 1" is the only
    # consistent option; without the assumption C=2 and C=0 would also be possible.
    q = _question(
        "could",
        [
            _opt([_eq("C", "2")]),
            _opt([_eq("C", "1")]),  # the only consistent option under the assumption
            _opt([_eq("A", "1")]),
            _opt([_eq("B", "1")]),
            _opt([_eq("C", "0")]),
        ],
    )
    q["assumptions"] = [_eq("A", "0"), _eq("B", "2")]
    # An inconsistent assumption makes the game unsatisfiable: no option is verified.
    inconsistent = _question("could", [_opt([_eq("C", "0")]), _opt([_eq("C", "2")])])
    inconsistent["assumptions"] = [_eq("A", "1"), _eq("B", "0")]
    return [
        _case("assumptions-could-23", "assumptions", ["eq", "all_different", "order"], game, q, {"status": "decided", "index": 1}),
        _case(
            "assumptions-inconsistent-24",
            "control",
            ["eq", "order"],
            game,
            inconsistent,
            {"status": "unknown"},
        ),
    ]


# --- negative controls ------------------------------------------------------------


def _control_cases() -> list[dict]:
    ambiguous = _game(
        [_dom("s2", ["0", "1"], "set")],
        [_var("A", "s2")],
        [],
    )
    q_ambiguous = _question("could", [_opt([_eq("A", "0")]), _opt([_eq("A", "1")])])
    unknown = _question("could", [_opt([_eq("A", "2")])])
    not_entailed = _game(
        [_dom("s3", ["0", "1", "2"], "linear")],
        [_var("A", "s3"), _var("B", "s3")],
        [_eq("A", "0")],
    )
    # B is unconstrained, so "B is 1" has a counter-model (B = 0): not a must.
    q_not_entailed = _question("must", [_opt([_eq("B", "1")])])
    budget_game = _game(
        [_dom("s4", ["0", "1", "2", "3"], "linear")],
        [_var(name, "s4") for name in "ABCD"],
        [_c("all_different", ["A", "B", "C", "D"])],
    )
    q_budget = _question("could", [_opt([_eq("A", "0")])])
    return [
        _case("ambiguous-17", "control", [], ambiguous, q_ambiguous, {"status": "ambiguous"}),
        _case("unknown-18", "control", [], ambiguous, unknown, {"status": "unknown"}),
        _case("must-not-entailed-19", "control", ["eq"], not_entailed, q_not_entailed, {"status": "unknown"}),
        _case("budget-insufficient-20", "control", ["all_different"], budget_game, q_budget, {"status": "insufficient"}, budget=1),
    ]


def cases() -> list[dict]:
    """The full deterministic collection, grouped by mechanism."""
    return (
        _order_cases()
        + _all_different_cases()
        + _neq_cases()
        + _adjacency_cases()
        + _group_cases()
        + _count_cases()
        + _conditional_cases()
        + _boolean_cases()
        + _count_compare_cases()
        + _must_be_false_cases()
        + _assumption_cases()
        + _complete_list_cases()
        + _control_cases()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the L3 synthetic collection.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    collected = cases()
    with out.open("w", encoding="utf-8") as handle:
        for case in collected:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    print(f"wrote {len(collected)} cases to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
