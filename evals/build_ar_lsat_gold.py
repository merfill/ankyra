"""Build the hand-encoded AR-LSAT gold set (T0, LLM-free; ``docs/l3_plan.md`` §13.2).

Real games from the official **development** split, encoded by hand into the CSP IR,
with the dataset's answer option as the expected decision. Running the engine on this
set separates the **method** (IR + solver) from extraction: no LLM is involved.

The set intentionally excludes questions whose shape the committed fragment does not
cover (``rule substitution``, "how many", "fully determine", and complete lists over
derived sequences/entities), and one row whose stored answer key is inconsistent with
its own constraints (``201306_2-G_1`` q4 — recorded in ``docs/l3_plan.md``).

Usage::

    uv run python -m evals.build_ar_lsat_gold [--out PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ankyra.build.csp import build_csp_game
from ankyra.engine.csp import CspConstraint, CspDomain, CspGame, CspOption, CspQuestion, CspVariable
from ankyra.engine.csp.schemas import CspGameStructure

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "ar_lsat_gold.jsonl"
SOURCE = "zhongwanjun/AR-LSAT (development)"

C = CspConstraint


def _eq(name: str, value: str) -> dict:
    return C(kind="eq", variables=[name], values=[value])


def _neq(name: str, value: str) -> dict:
    return C(kind="neq", variables=[name], values=[value])


def _order(a: str, b: str, *, immediate: bool = False) -> dict:
    return C(kind="order", variables=[a, b], immediate=immediate)


def _adjacent(a: str, b: str) -> dict:
    return C(kind="adjacent", variables=[a, b])


def _any(*constraints: dict) -> dict:
    return C(kind="any", constraints=list(constraints))


def _all(*constraints: dict) -> dict:
    return C(kind="all", constraints=list(constraints))


def _option(*constraints: dict) -> CspOption:
    return CspOption(constraints=list(constraints))


def _assign(*pairs: str) -> list[dict]:
    return [_eq(pairs[index], pairs[index + 1]) for index in range(0, len(pairs), 2)]


def _game(domain: CspDomain, names: str, constraints: list[dict]) -> CspGame:
    variables = [CspVariable(id=name, domain=domain.id) for name in names.split()]
    raw = CspGame(domains=[domain], variables=variables, constraints=constraints)
    # Validate the hand encoding through the same deterministic builder as extraction:
    # a dangling reference or an out-of-domain value is an error, not a silent no-op.
    return build_csp_game(CspGameStructure.model_validate(raw.model_dump()))


def _record(father: str, question_id: str, kind: str, expected: int, game: CspGame, question: CspQuestion) -> dict:
    return {
        "id": f"ar-gold-{father}-{question_id}",
        "fatherId": father,
        "source": SOURCE,
        "question_kind": kind,
        "expected_index": expected,
        "game": game.model_dump(),
        "question": question.model_dump(),
    }


# --- 201409_3-G_1 — CD track sequence (linear ordering + boolean composition) -----


def _cd_game() -> CspGame:
    domain = CspDomain(id="pos", values=[str(i) for i in range(5)], topology="linear")
    return _game(
        domain,
        "R S T V W",
        [
            C(kind="all_different", variables=["R", "S", "T", "V", "W"]),
            _order("S", "V"),
            _any(
                _all(_order("T", "R"), _order("T", "S")),
                _all(_order("R", "T"), _order("S", "T")),
            ),
            _any(
                _all(_order("W", "R"), _order("W", "T")),
                _all(_order("R", "W"), _order("T", "W")),
            ),
        ],
    )


def _cd_records() -> list[dict]:
    game = _cd_game()
    father = "201409_3-G_1"
    return [
        _record(father, "q1", "not_violate", 1, game, CspQuestion(kind="not_violate", options=[
            _option(*_assign("R", "0", "T", "1", "W", "2", "S", "3", "V", "4")),
            _option(*_assign("S", "0", "R", "1", "T", "2", "V", "3", "W", "4")),
            _option(*_assign("T", "0", "W", "1", "S", "2", "V", "3", "R", "4")),
            _option(*_assign("V", "0", "W", "1", "S", "2", "R", "3", "T", "4")),
            _option(*_assign("W", "0", "S", "1", "V", "2", "T", "3", "R", "4")),
        ])),
        _record(father, "q2", "must", 2, game, CspQuestion(kind="must", assumptions=[_eq("S", "3")], options=[
            _option(_order("R", "W")), _option(_order("S", "T")), _option(_order("T", "R")),
            _option(_order("V", "W")), _option(_order("W", "T")),
        ])),
        _record(father, "q3", "could", 1, game, CspQuestion(kind="could", assumptions=[_eq("R", "0")], options=[
            _option(_eq("T", "1")), _option(_eq("V", "2")), _option(_eq("W", "2")),
            _option(_eq("S", "3")), _option(_eq("T", "4")),
        ])),
        _record(father, "q4", "could", 4, game, CspQuestion(kind="could", assumptions=[_eq("T", "1")], options=[
            _option(_eq("S", "0")), _option(_eq("R", "0")), _option(_eq("V", "2")),
            _option(_eq("W", "3")), _option(_eq("R", "4")),
        ])),
        _record(father, "q5", "could", 1, game, CspQuestion(kind="could", options=[
            _option(*_assign("R", "0", "V", "1")), _option(*_assign("W", "0", "S", "1")),
            _option(*_assign("S", "0", "T", "1")), _option(*_assign("T", "0", "W", "1")),
            _option(*_assign("R", "0", "W", "1")),
        ])),
        _record(father, "q6", "could", 3, game, CspQuestion(kind="could", assumptions=[_eq("V", "1")], options=[
            _option(_eq("W", "0")), _option(_eq("S", "2")), _option(_eq("T", "2")),
            _option(_eq("R", "3")), _option(_eq("R", "4")),
        ])),
        _record(father, "q7", "must_be_false", 0, game, CspQuestion(kind="must_be_false", assumptions=[_eq("W", "0")], options=[
            _option(_eq("T", "2")), _option(_eq("V", "2")), _option(_eq("S", "3")),
            _option(_eq("V", "3")), _option(_eq("T", "4")),
        ])),
    ]


# --- 201409_3-G_3 — building ownership (grouping + count comparison) --------------


def _ownership_game() -> CspGame:
    domain = CspDomain(id="fam", values=["T", "W", "Y"], topology="set")
    names = ["forge", "granary", "inn", "mill", "stable"]
    return _game(
        domain,
        "forge granary inn mill stable",
        [
            C(kind="count", variables=names, values=["T"], count=1, count_mode="at_least"),
            C(kind="count", variables=names, values=["W"], count=1, count_mode="at_least"),
            C(kind="count", variables=names, values=["Y"], count=1, count_mode="at_least"),
            C(kind="count_compare", variables=names, values=["W", "Y"], comparison="gt"),
            C(kind="neq", variables=["inn", "forge"]),
            C(kind="neq", variables=["mill", "forge"]),
            _any(_eq("stable", "T"), _eq("inn", "Y")),
        ],
    )


def _ownership_records() -> list[dict]:
    game = _ownership_game()
    father = "201409_3-G_3"
    return [
        _record(father, "q1", "must_be_false", 3, game, CspQuestion(kind="must_be_false", options=[
            _option(_all(_eq("forge", "T"), _eq("granary", "T"))),
            _option(_all(_eq("granary", "T"), _eq("mill", "T"))),
            _option(_all(_eq("granary", "T"), _eq("stable", "T"))),
            _option(_all(_eq("inn", "T"), _eq("mill", "T"))),
            _option(_all(_eq("inn", "T"), _eq("stable", "T"))),
        ])),
        _record(father, "q2", "must", 3, game, CspQuestion(kind="must", assumptions=[_eq("mill", "Y")], options=[
            _option(_eq("forge", "T")), _option(_eq("inn", "T")), _option(_eq("forge", "W")),
            _option(_eq("granary", "W")), _option(_eq("inn", "W")),
        ])),
    ]


# --- 201112_2-G_1 — recital order (linear ordering + immediate disjunction) -------


def _recital_game() -> CspGame:
    domain = CspDomain(id="pos", values=[str(i) for i in range(5)], topology="linear")
    return _game(
        domain,
        "F G H J K",
        [
            C(kind="all_different", variables=["F", "G", "H", "J", "K"]),
            _order("G", "F"),
            _order("K", "H"),
            _order("K", "J"),
            _any(_order("H", "F", immediate=True), _order("F", "H", immediate=True)),
        ],
    )


def _recital_records() -> list[dict]:
    game = _recital_game()
    father = "201112_2-G_1"
    return [
        _record(father, "q1", "not_violate", 3, game, CspQuestion(kind="not_violate", options=[
            _option(*_assign("G", "0", "F", "1", "H", "2", "K", "3", "J", "4")),
            _option(*_assign("G", "0", "J", "1", "K", "2", "H", "3", "F", "4")),
            _option(*_assign("G", "0", "K", "1", "H", "2", "J", "3", "F", "4")),
            _option(*_assign("K", "0", "G", "1", "J", "2", "F", "3", "H", "4")),
            _option(*_assign("K", "0", "J", "1", "F", "2", "H", "3", "G", "4")),
        ])),
        _record(father, "q2", "could", 0, game, CspQuestion(kind="could", assumptions=[_order("J", "G")], options=[
            _option(_eq("F", "3")), _option(_eq("G", "1")), _option(_eq("H", "2")),
            _option(_eq("J", "2")), _option(_eq("K", "1")),
        ])),
        _record(father, "q3", "must_be_false", 2, game, CspQuestion(kind="must_be_false", options=[
            _option(_order("F", "J", immediate=True)), _option(_order("G", "H", immediate=True)),
            _option(_order("H", "G", immediate=True)), _option(_order("J", "G", immediate=True)),
            _option(_order("K", "H", immediate=True)),
        ])),
    ]


# --- 201306_2-G_1 — manuscript ages (linear ordering + range via any) -------------


def _manuscript_game() -> CspGame:
    domain = CspDomain(id="pos", values=[str(i) for i in range(7)], topology="linear")
    return _game(
        domain,
        "F G H L M P S",
        [
            C(kind="all_different", variables=["F", "G", "H", "L", "M", "P", "S"]),
            _order("F", "H"),
            _order("H", "S"),
            _order("G", "P", immediate=True),
            _neq("H", "4"),
            _any(_eq("L", "4"), _eq("L", "5"), _eq("L", "6")),
            _any(_eq("M", "0"), _eq("M", "1"), _eq("M", "2")),
        ],
    )


def _manuscript_records() -> list[dict]:
    game = _manuscript_game()
    father = "201306_2-G_1"
    # q4 ("which CANNOT be written fourth", key D) is excluded: the engine proves the
    # key's option satisfiable and the alternative (H) unsatisfiable, so the stored
    # answer key is inconsistent with the constraints (recorded in docs/l3_plan.md).
    return [
        _record(father, "q1", "not_violate", 4, game, CspQuestion(kind="not_violate", options=[
            _option(*_assign("F", "0", "M", "1", "G", "2", "H", "3", "P", "4", "L", "5", "S", "6")),
            _option(*_assign("G", "0", "P", "1", "M", "2", "F", "3", "H", "4", "S", "5", "L", "6")),
            _option(*_assign("H", "0", "F", "1", "M", "2", "G", "3", "P", "4", "L", "5", "S", "6")),
            _option(*_assign("L", "0", "F", "1", "M", "2", "G", "3", "P", "4", "H", "5", "S", "6")),
            _option(*_assign("M", "0", "F", "1", "H", "2", "S", "3", "L", "4", "G", "5", "P", "6")),
        ])),
        _record(father, "q2", "must_be_false", 0, game, CspQuestion(kind="must_be_false", options=[
            _option(_eq("S", "2")), _option(_eq("P", "2")), _option(_eq("M", "2")),
            _option(_eq("H", "2")), _option(_eq("G", "2")),
        ])),
        _record(father, "q3", "could", 4, game, CspQuestion(kind="could", assumptions=[_order("M", "H", immediate=True)], options=[
            _option(_eq("F", "1")), _option(_eq("G", "2")), _option(_eq("H", "3")),
            _option(_eq("P", "2")), _option(_eq("S", "3")),
        ])),
    ]


# --- 200310_2-G_1 — hangers (linear ordering + adjacency) -------------------------


def _hangers_game() -> CspGame:
    domain = CspDomain(id="h", values=[str(i) for i in range(6)], topology="linear")
    return _game(
        domain,
        "G L P R S W",
        [
            C(kind="all_different", variables=["G", "L", "P", "R", "S", "W"]),
            _order("G", "P"),
            _any(_eq("R", "0"), _eq("R", "5")),
            _any(_eq("W", "2"), _eq("S", "2")),
            _order("S", "L", immediate=True),
        ],
    )


def _hangers_records() -> list[dict]:
    game = _hangers_game()
    father = "200310_2-G_1"
    odd = lambda name: _any(_eq(name, "0"), _eq(name, "2"), _eq(name, "4"))  # noqa: E731
    even = lambda name: _any(_eq(name, "1"), _eq(name, "3"), _eq(name, "5"))  # noqa: E731

    def mapping(*fabrics: str) -> list[dict]:
        return [_eq(name, str(index)) for index, name in enumerate(fabrics)]

    return [
        _record(father, "q1", "not_violate", 0, game, CspQuestion(kind="not_violate", options=[
            _option(*mapping("W", "G", "S", "L", "P", "R")),
            _option(*mapping("R", "W", "G", "S", "L", "P")),
            _option(*mapping("P", "G", "W", "S", "L", "R")),
            _option(*mapping("L", "S", "W", "G", "P", "R")),
            _option(*mapping("G", "R", "S", "L", "W", "P")),
        ])),
        _record(father, "q2", "could", 1, game, CspQuestion(kind="could", assumptions=[odd("S"), odd("G")], options=[
            _option(_eq("P", "0")), _option(_eq("W", "1")), _option(_eq("P", "3")),
            _option(_eq("L", "4")), _option(_eq("W", "5")),
        ])),
        _record(father, "q3", "could", 4, game, CspQuestion(kind="could", assumptions=[even("S")], options=[
            _option(_order("G", "S", immediate=True)), _option(_order("L", "S", immediate=True)),
            _option(_order("P", "S", immediate=True)), _option(_order("R", "S", immediate=True)),
            _option(_order("W", "S", immediate=True)),
        ])),
        _record(father, "q4", "must", 4, game, CspQuestion(kind="must", assumptions=[_eq("P", "1")], options=[
            _option(_eq("S", "0")), _option(_eq("W", "2")), _option(_eq("L", "3")),
            _option(_eq("L", "4")), _option(_eq("R", "5")),
        ])),
        _record(father, "q5", "must_be_false", 1, game, CspQuestion(kind="must_be_false", options=[
            _option(_any(_order("L", "G", immediate=True), _order("G", "L", immediate=True))),
            _option(_order("R", "P", immediate=True)),
            _option(_order("R", "W", immediate=True)),
            _option(_order("S", "G")),
            _option(_order("R", "W")),
        ])),
        _record(father, "q6", "must_be_false", 3, game, CspQuestion(kind="must_be_false", options=[
            _option(_adjacent("G", "R")), _option(_adjacent("L", "R")), _option(_adjacent("P", "R")),
            _option(_adjacent("S", "R")), _option(_adjacent("W", "R")),
        ])),
    ]


def cases() -> list[dict]:
    return (
        _cd_records()
        + _ownership_records()
        + _recital_records()
        + _manuscript_records()
        + _hangers_records()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the AR-LSAT hand-encoded gold set.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    collected = cases()
    with out.open("w", encoding="utf-8") as handle:
        for record in collected:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    games = {record["fatherId"] for record in collected}
    print(f"wrote {len(collected)} gold questions over {len(games)} games to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
