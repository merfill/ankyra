"""Build the hand-encoded GSM8K gold set (T0, LLM-free; ``docs/l4_plan.md`` §13.2).

Real problems from the committed **dev** slice of the official test split, encoded by
hand into the numeric IR, with the dataset's reference number as the expected value.
Running the engine on this set separates the **method** (IR + solver) from extraction:
no LLM is involved.

Each encoding is validated through the same deterministic builder as extraction
(``ankyra.build.numeric``): a dangling reference, a malformed expression or a
non-verbatim quote is an error, not a silent no-op.

Usage::

    uv run python -m evals.build_gsm8k_gold [--out PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ankyra.build.numeric import build_numeric_game, build_numeric_query
from ankyra.engine.numeric.schemas import NumericGameStructure, NumericQueryStructure

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "gsm8k_gold.jsonl"
SOURCE = "openai/grade-school-math (test)"


def _c(value: int | str) -> dict:
    return {"op": "const", "value": str(value)}


def _q(name: str) -> dict:
    return {"op": "quantity", "quantity": name}


def _add(*args: dict) -> dict:
    return {"op": "add", "args": list(args)}


def _sub(left: dict, right: dict) -> dict:
    return {"op": "sub", "args": [left, right]}


def _mul(*args: dict) -> dict:
    return {"op": "mul", "args": list(args)}


def _div(left: dict, right: dict) -> dict:
    return {"op": "div", "args": [left, right]}


def _eq(lhs: dict, rhs: dict, quote: str) -> dict:
    return {"lhs": lhs, "rhs": rhs, "quote": quote}


def _record(
    sample_index: str,
    question: str,
    reference: str,
    quantities: list[tuple[str, str | None, str]],
    equations: list[dict],
    target: str,
) -> dict:
    game = build_numeric_game(
        NumericGameStructure.model_validate(
            {
                "quantities": [
                    {"id": name, "unit": unit, "quote": quote}
                    for name, unit, quote in quantities
                ],
                "equations": equations,
            }
        ),
        source_text=question,
    )
    query = build_numeric_query(NumericQueryStructure(target=target), game=game)
    return {
        "id": f"gsm8k-gold-{sample_index}",
        "source": SOURCE,
        "sample_id": f"gsm8k-test-{sample_index}",
        "question": question,
        "reference": reference,
        "game": game.model_dump(mode="json"),
        "query": query.model_dump(mode="json"),
    }


# --- 0028 — bike trip between stops (multi-step subtract) ------------------------
BIKE_Q = (
    "Henry made two stops during his 60-mile bike trip. He first stopped after 20 miles. "
    "His second stop was 15 miles before the end of the trip. How many miles did he "
    "travel between his first and second stops?"
)


def _bike() -> dict:
    return _record(
        "0028",
        BIKE_Q,
        "25",
        [
            ("total", "miles", "60-mile bike trip"),
            ("first", "miles", "first stopped after 20 miles"),
            ("before_end", "miles", "15 miles before the end of the trip"),
            ("between", "miles", "travel between his first and second stops"),
        ],
        [
            _eq(_q("total"), _c(60), "60-mile bike trip"),
            _eq(_q("first"), _c(20), "first stopped after 20 miles"),
            _eq(_q("before_end"), _c(15), "15 miles before the end of the trip"),
            _eq(
                _q("between"),
                _sub(_q("total"), _add(_q("first"), _q("before_end"))),
                "travel between his first and second stops",
            ),
        ],
        "between",
    )


# --- 0480 — paint tubes (ratio + ratio + sum) ------------------------------------
PAINT_Q = (
    "Ben has 4 tubes of blue paint and 3 tubes of yellow paint. Jasper has half as many "
    "tubes of blue paint as Ben, and three times as many tubes of yellow paint as Ben. "
    "How many tubes of paint does Jasper have?"
)


def _paint() -> dict:
    return _record(
        "0480",
        PAINT_Q,
        "11",
        [
            ("ben_blue", "tubes", "4 tubes of blue paint"),
            ("ben_yellow", "tubes", "3 tubes of yellow paint"),
            ("jasper_blue", "tubes", "half as many tubes of blue paint as Ben"),
            ("jasper_yellow", "tubes", "three times as many tubes of yellow paint as Ben"),
            ("jasper_total", "tubes", "How many tubes of paint does Jasper have"),
        ],
        [
            _eq(_q("ben_blue"), _c(4), "4 tubes of blue paint"),
            _eq(_q("ben_yellow"), _c(3), "3 tubes of yellow paint"),
            _eq(_q("jasper_blue"), _div(_q("ben_blue"), _c(2)), "half as many tubes of blue paint as Ben"),
            _eq(_q("jasper_yellow"), _mul(_c(3), _q("ben_yellow")), "three times as many tubes of yellow paint as Ben"),
            _eq(_q("jasper_total"), _add(_q("jasper_blue"), _q("jasper_yellow")), "How many tubes of paint does Jasper have"),
        ],
        "jasper_total",
    )


# --- 0673 — Janey/Sally books (linear equation with an unknown) ------------------
BOOKS_Q = (
    "Janey has 3 more than twice the number of books that Sally has. If Janey has 21 "
    "books, how many does Sally have?"
)


def _books() -> dict:
    return _record(
        "0673",
        BOOKS_Q,
        "9",
        [
            ("janey", "books", "Janey has 21 books"),
            ("sally", "books", "number of books that Sally has"),
        ],
        [
            _eq(_q("janey"), _c(21), "Janey has 21 books"),
            _eq(_q("janey"), _add(_c(3), _mul(_c(2), _q("sally"))), "3 more than twice the number of books that Sally has"),
        ],
        "sally",
    )


# --- 0852 — food baskets discount (count + discount) -----------------------------
BASKETS_Q = (
    "A basket of green food costs $25 and a basket of red food costs $18. If you buy 3 "
    "baskets of green food and red food, how much will you have to pay in total if you "
    "get $2 off for each basket of red food?"
)


def _baskets() -> dict:
    return _record(
        "0852",
        BASKETS_Q,
        "123",
        [
            ("green", "dollars", "green food costs $25"),
            ("red", "dollars", "red food costs $18"),
            ("count", "baskets", "buy 3 baskets"),
            ("discount", "dollars", "$2 off for each basket of red food"),
            ("total", "dollars", "how much will you have to pay in total"),
        ],
        [
            _eq(_q("green"), _c(25), "green food costs $25"),
            _eq(_q("red"), _c(18), "red food costs $18"),
            _eq(_q("count"), _c(3), "buy 3 baskets"),
            _eq(_q("discount"), _c(2), "$2 off for each basket of red food"),
            _eq(
                _q("total"),
                _add(_mul(_q("green"), _q("count")), _mul(_sub(_q("red"), _q("discount")), _q("count"))),
                "how much will you have to pay in total",
            ),
        ],
        "total",
    )


# --- 1083 — bananas bunch vs individual (two unit prices) ------------------------
BANANAS_Q = (
    "The bananas at the supermarket cost $0.80 each, or a bunch for $3.00.  Jenny buys "
    "10 bunches that average 4 bananas per bunch. How much money, in dollars, did she "
    "save by buying the bananas in bunches instead of individually?"
)


def _bananas() -> dict:
    return _record(
        "1083",
        BANANAS_Q,
        "2",
        [
            ("each", "dollars", "cost $0.80 each"),
            ("per_bunch", "dollars", "a bunch for $3.00"),
            ("bunches", "bunches", "buys 10 bunches"),
            ("bananas", "bananas", "average 4 bananas per bunch"),
            ("individual_cost", "dollars", "instead of individually"),
            ("bunch_cost", "dollars", "buying the bananas in bunches"),
            ("saved", "dollars", "did she save by buying the bananas in bunches"),
        ],
        [
            _eq(_q("each"), _c("0.80"), "cost $0.80 each"),
            _eq(_q("per_bunch"), _c(3), "a bunch for $3.00"),
            _eq(_q("bunches"), _c(10), "buys 10 bunches"),
            _eq(_q("bananas"), _mul(_q("bunches"), _c(4)), "average 4 bananas per bunch"),
            _eq(_q("bunch_cost"), _mul(_q("per_bunch"), _q("bunches")), "buying the bananas in bunches"),
            _eq(_q("individual_cost"), _mul(_q("bananas"), _q("each")), "instead of individually"),
            _eq(_q("saved"), _sub(_q("individual_cost"), _q("bunch_cost")), "did she save by buying the bananas in bunches"),
        ],
        "saved",
    )


# --- 1114 — Raymond's money (add then subtract) ----------------------------------
MONEY_Q = (
    "Raymond had $21. Then he saved $11 from his allowance and spent $5 on a comic book "
    "and $19 on a puzzle. How much money does Raymond have left?"
)


def _money() -> dict:
    return _record(
        "1114",
        MONEY_Q,
        "8",
        [
            ("start", "dollars", "Raymond had $21"),
            ("saved", "dollars", "$11 from his allowance"),
            ("comic", "dollars", "$5 on a comic book"),
            ("puzzle", "dollars", "$19 on a puzzle"),
            ("left", "dollars", "How much money does Raymond have left"),
        ],
        [
            _eq(_q("start"), _c(21), "Raymond had $21"),
            _eq(_q("saved"), _c(11), "$11 from his allowance"),
            _eq(_q("comic"), _c(5), "$5 on a comic book"),
            _eq(_q("puzzle"), _c(19), "$19 on a puzzle"),
            _eq(
                _q("left"),
                _sub(_add(_q("start"), _q("saved")), _add(_q("comic"), _q("puzzle"))),
                "How much money does Raymond have left",
            ),
        ],
        "left",
    )


# --- 1143 — Tim's lemons (product over a decade) ---------------------------------
LEMONS_Q = (
    "Tim grows 5 trees.  Each year he collects 6 lemons from each tree.  How many lemons "
    "does he get in a decade?"
)


def _lemons() -> dict:
    return _record(
        "1143",
        LEMONS_Q,
        "300",
        [
            ("trees", "trees", "grows 5 trees"),
            ("per_tree", "lemons", "6 lemons from each tree"),
            ("years", "years", "in a decade"),
            ("total", "lemons", "How many lemons does he get in a decade"),
        ],
        [
            _eq(_q("trees"), _c(5), "grows 5 trees"),
            _eq(_q("per_tree"), _c(6), "6 lemons from each tree"),
            _eq(_q("years"), _c(10), "in a decade"),
            _eq(_q("total"), _mul(_q("trees"), _q("per_tree"), _q("years")), "How many lemons does he get in a decade"),
        ],
        "total",
    )


# --- 1208 — magazine profit (fraction multiplier) --------------------------------
MAGAZINE_Q = (
    "Trinity sells magazines at 11/8 of the price she bought the magazines. If she bought "
    "the magazines at $72, what is her profit?"
)


def _magazines() -> dict:
    return _record(
        "1208",
        MAGAZINE_Q,
        "27",
        [
            ("bought", "dollars", "bought the magazines at $72"),
            ("sold", "dollars", "sells magazines at 11/8 of the price she bought"),
            ("profit", "dollars", "what is her profit"),
        ],
        [
            _eq(_q("bought"), _c(72), "bought the magazines at $72"),
            _eq(_q("sold"), _mul(_q("bought"), _div(_c(11), _c(8))), "sells magazines at 11/8 of the price she bought"),
            _eq(_q("profit"), _sub(_q("sold"), _q("bought")), "what is her profit"),
        ],
        "profit",
    )


def cases() -> list[dict]:
    return [
        _bike(),
        _paint(),
        _books(),
        _baskets(),
        _bananas(),
        _money(),
        _lemons(),
        _magazines(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the GSM8K hand-encoded gold set.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    collected = cases()
    with out.open("w", encoding="utf-8") as handle:
        for record in collected:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"wrote {len(collected)} gold problems to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
