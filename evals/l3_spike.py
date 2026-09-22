"""L3 Phase-0 feasibility spike (LLM-free; ``docs/l3_plan.md`` §6).

Hand-encode five games (one per game/question type) into the CSP IR and solve them
with the in-repo finite-domain solver. This is the decision gate: does a general IR
cover the game axes soundly, or does a construct resist it?

Run::

    uv run python -m evals.l3_spike

No LLM calls. Exits non-zero on any decision mismatch.
"""

from __future__ import annotations

import argparse

from ankyra.engine.csp import (
    CspConstraint,
    CspDomain,
    CspGame,
    CspOption,
    CspQuestion,
    CspVariable,
    decide_question,
)

C = CspConstraint


def _game(domain: CspDomain, names: str, constraints: list[CspConstraint]) -> CspGame:
    variables = [CspVariable(id=name, domain=domain.id) for name in names.split()]
    return CspGame(domains=[domain], variables=variables, constraints=constraints)


def _eq(name: str, value: str) -> CspConstraint:
    return C(kind="eq", variables=[name], values=[value])


def _single(name: str, value: str) -> CspOption:
    return CspOption(constraints=[_eq(name, value)])


def _assign(*pairs: str) -> list[CspConstraint]:
    return [_eq(pairs[i], pairs[i + 1]) for i in range(0, len(pairs), 2)]


# --- Game 1 — linear ordering, "must" -------------------------------------------
# A < B < C over four seats; which claim holds in every model?
_seat4 = CspDomain(id="seat4", values=["1", "2", "3", "4"], topology="linear")
GAME1 = _game(
    _seat4,
    "A B C D",
    [
        C(kind="all_different", variables=["A", "B", "C", "D"]),
        C(kind="order", variables=["A", "B"]),
        C(kind="order", variables=["B", "C"]),
    ],
)
Q1 = CspQuestion(
    kind="must",
    options=[
        _single("B", "4"),  # false
        _single("B", "2"),  # not in every model
        _single("C", "3"),  # not in every model
        _single("A", "1"),  # not in every model
        CspOption(constraints=[C(kind="neq", variables=["B"], values=["4"])]),  # true
    ],
)
GOLD1 = 4

# --- Game 2 — circular ordering, "not_violate" ----------------------------------
# A-B-C-D consecutive around a five-seat circle; E not adjacent to B.
_seat5 = CspDomain(id="seat5", values=["0", "1", "2", "3", "4"], topology="circular")
GAME2 = _game(
    _seat5,
    "A B C D E",
    [
        C(kind="all_different", variables=["A", "B", "C", "D", "E"]),
        C(kind="adjacent", variables=["A", "B"]),
        C(kind="adjacent", variables=["B", "C"]),
        C(kind="adjacent", variables=["C", "D"]),
        C(kind="not_adjacent", variables=["E", "B"]),
    ],
)
Q2 = CspQuestion(
    kind="not_violate",
    options=[
        CspOption(constraints=_assign("A", "0", "B", "1", "C", "2", "D", "3", "E", "4")),  # valid
        CspOption(constraints=_assign("A", "0", "B", "1", "C", "3", "D", "4", "E", "2")),  # B-C not adjacent
        CspOption(constraints=_assign("A", "1", "B", "0", "C", "2", "D", "3", "E", "4")),  # B-C not adjacent
        CspOption(constraints=_assign("A", "0", "B", "1", "C", "2", "D", "4", "E", "3")),  # C-D not adjacent
        CspOption(constraints=_assign("A", "2", "B", "1", "C", "0", "D", "3", "E", "4")),  # C-D not adjacent
    ],
)
GOLD2 = 0

# --- Game 3 — grouping, "must" --------------------------------------------------
# Exactly two in group X; C in X; D in Y; A and B in different groups.
# The models force C and E into X, D into Y; A and B split. C is X in every model.
_group = CspDomain(id="group", values=["X", "Y"], topology="set")
GAME3 = _game(
    _group,
    "A B C D E",
    [
        C(kind="different_group", variables=["A", "B"]),
        _eq("C", "X"),
        _eq("D", "Y"),
        C(kind="count", variables=["A", "B", "C", "D", "E"], values=["X"], count=2, count_mode="exactly"),
    ],
)
Q3 = CspQuestion(
    kind="must",
    options=[
        _single("C", "X"),  # true in every model
        _single("A", "X"),  # only one model
        _single("B", "X"),  # only the other model
        _single("A", "Y"),  # only the other model
        _single("D", "X"),  # never
    ],
)
GOLD3 = 0

# --- Game 4 — assignment, "complete_list" ---------------------------------------
# A < B, A adjacent C over three seats; which is the complete list of seats for A?
_seat3 = CspDomain(id="seat3", values=["1", "2", "3"], topology="linear")
GAME4 = _game(
    _seat3,
    "A B C",
    [
        C(kind="all_different", variables=["A", "B", "C"]),
        C(kind="order", variables=["A", "B"]),
        C(kind="adjacent", variables=["A", "C"]),
    ],
)
Q4 = CspQuestion(
    kind="complete_list",
    target="A",
    options=[
        CspOption(values=["1", "2"]),  # complete and accurate
        CspOption(values=["1"]),
        CspOption(values=["2"]),
        CspOption(values=["1", "2", "3"]),
        CspOption(values=["3"]),
    ],
)
GOLD4 = 0

# --- Game 5 — conditional, "could" ----------------------------------------------
# Fixed A=Y, B=X, D=Y; if C is X then D is X (so C is not X). Which could be true?
GAME5 = _game(
    _group,
    "A B C D",
    [
        _eq("A", "Y"),
        _eq("B", "X"),
        _eq("D", "Y"),
        C(kind="conditional", condition=_eq("C", "X"), consequence=_eq("D", "X")),
    ],
)
Q5 = CspQuestion(
    kind="could",
    options=[
        _single("C", "X"),  # pruned by the conditional
        _single("D", "X"),  # contradicts D=Y
        _single("C", "Y"),  # the only consistent option
        _single("A", "X"),  # contradicts A=Y
        _single("B", "Y"),  # contradicts B=X
    ],
)
GOLD5 = 2

CASES = [
    ("linear-order-must", GAME1, Q1, GOLD1),
    ("circular-order-not-violate", GAME2, Q2, GOLD2),
    ("grouping-must", GAME3, Q3, GOLD3),
    ("assignment-complete-list", GAME4, Q4, GOLD4),
    ("conditional-could", GAME5, Q5, GOLD5),
]


def run(budget: int | None = None) -> int:
    failures = 0
    print(f"L3 Phase-0 spike — {len(CASES)} hand-encoded games (LLM-free)\n")
    for name, game, question, gold in CASES:
        kwargs = {} if budget is None else {"budget": budget}
        decision = decide_question(game, question, **kwargs)
        ok = decision.status == "decided" and decision.index == gold
        mark = "ok " if ok else "FAIL"
        witness = f" witness={decision.witness}" if decision.witness else ""
        extra = f" verified={decision.verified}" if decision.status == "ambiguous" else ""
        detail = f" ({decision.detail})" if decision.detail else ""
        print(
            f"  [{mark}] {name:28s} status={decision.status:11s} "
            f"picked={decision.index} gold={gold}{witness}{extra}{detail}"
        )
        if not ok:
            failures += 1
    print()
    if failures:
        print(f"spike gate RED: {failures}/{len(CASES)} mismatches")
        return 1
    print(f"spike gate GREEN: {len(CASES)}/{len(CASES)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="L3 Phase-0 feasibility spike (LLM-free).")
    parser.add_argument("--budget", type=int, default=None)
    args = parser.parse_args(argv)
    return run(budget=args.budget)


if __name__ == "__main__":
    raise SystemExit(main())
