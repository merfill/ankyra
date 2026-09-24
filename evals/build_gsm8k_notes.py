"""Committed notes on GSM8K rows whose reference answer is unsound or ambiguous.

GSM8K references are not always correct or unambiguous. Since L4 arithmetic is exact,
a ``grounded_mismatch`` (the engine determined a value that differs from the reference)
is a *modelling* signal, never an arithmetic error; but before treating one as a real
miss it must be checked against the reference. Two committed rows are annotated here,
reproducibly:

* ``gsm8k-test-0823`` — **dataset_error**: the reference chain of thought sums Julie's
  first-game score (10) where Sasha's (14) belongs, so its ``14`` is wrong; the faithful
  model gives ``18``.
* ``gsm8k-test-0649`` — **ambiguity**: "received 70 times as many … new likes" can be read
  as *became* 70× the initial (``160000``) or as *received* 70× the initial as new likes
  (the reference's reading, ``162000``); both are arithmetically valid.

Each note carries the hand-encoded model the engine used and, for an ambiguity, the
alternative reading; the models are validated through the deterministic builder and
solved, so the disagreement is asserted reproducibly (``tests/test_evals_gsm8k.py``) —
mirroring the AR-LSAT exclusion record (``docs/l3_extension_plan.md`` H2). This is an
audit artifact, never per-id tuning of the engine.

Usage::

    uv run python -m evals.build_gsm8k_notes [--out PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ankyra.build.numeric import build_numeric_game, build_numeric_query
from ankyra.engine.numeric.schemas import NumericGameStructure, NumericQueryStructure
from ankyra.engine.numeric.solver import solve

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "gsm8k_notes.jsonl"
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


def _eq(lhs: dict, rhs: dict, quote: str) -> dict:
    return {"lhs": lhs, "rhs": rhs, "quote": quote}


def _model(
    quantities: list[tuple[str, str]],
    equations: list[dict],
    source: str,
    target: str,
) -> tuple[dict, dict, str]:
    game = build_numeric_game(
        NumericGameStructure.model_validate(
            {
                "quantities": [{"id": name, "quote": quote} for name, quote in quantities],
                "equations": equations,
            }
        ),
        source_text=source,
    )
    query = build_numeric_query(NumericQueryStructure(target=target), game=game)
    value = str(solve(game, query).value)
    return game.model_dump(mode="json"), query, value


# --- 0823 — Sasha/Julie basketball (dataset error) -------------------------------
SASHA_Q = (
    "Sasha and Julie are best friends playing on opposing basketball teams. The teams "
    "have two practice games scheduled. In the first game, Sasha had the home court "
    "advantage and scored 14 points. Julie scored 4 fewer points than Sasha in the same "
    "game. Sasha always struggles during away games and their second match was at Julie's "
    "home court. Sasha scored 6 fewer points in the second game than Julie's score in the "
    "first game. How many total points did Sasha score during both games?"
)


def _sasha() -> dict:
    game, query, value = _model(
        [
            ("sasha_first", "scored 14 points"),
            ("julie_first", "Julie scored 4 fewer points than Sasha"),
            ("sasha_second", "Sasha scored 6 fewer points in the second game than Julie's score in the first game"),
            ("sasha_total", "How many total points did Sasha score during both games"),
        ],
        [
            _eq(_q("sasha_first"), _c(14), "scored 14 points"),
            _eq(_q("julie_first"), _sub(_q("sasha_first"), _c(4)), "Julie scored 4 fewer points than Sasha"),
            _eq(
                _q("sasha_second"),
                _sub(_q("julie_first"), _c(6)),
                "Sasha scored 6 fewer points in the second game than Julie's score in the first game",
            ),
            _eq(
                _q("sasha_total"),
                _add(_q("sasha_first"), _q("sasha_second")),
                "How many total points did Sasha score during both games",
            ),
        ],
        SASHA_Q,
        "sasha_total",
    )
    return {
        "id": "gsm8k-test-0823",
        "sample_id": "gsm8k-test-0823",
        "source": SOURCE,
        "kind": "dataset_error",
        "reference": "14",
        "engine_value": value,
        "reason": (
            "the reference chain of thought sums Julie's first-game score (10) where "
            "Sasha's (14) belongs ('Sasha scored 10+4=14'); the faithful model gives 18"
        ),
        "question": SASHA_Q,
        "model": {"game": game, "query": query.model_dump(mode="json")},
        "alternative": None,
    }


# --- 0649 — Fishio likes (ambiguity) ---------------------------------------------
FISHIO_Q = (
    "Fishio posted her selfie on Instagram. She received 2000 likes on the photo after 1 "
    "week. Three weeks later, the number of likes was 70 times as many as the initial "
    "number of likes. If she received 20000 more new likes recently, how many Instagram "
    "likes are there?"
)


def _fishio() -> dict:
    quantities = [
        ("initial_likes", "received 2000 likes"),
        ("later_likes", "70 times as many as the initial number of likes"),
        ("recent_likes", "received 20000 more new likes"),
        ("total_likes", "how many Instagram likes are there"),
    ]
    # Reading A (the engine's): the count *became* 70x the initial, then + recent.
    game_a, query_a, value_a = _model(
        quantities,
        [
            _eq(_q("initial_likes"), _c(2000), "received 2000 likes"),
            _eq(_q("later_likes"), _mul(_c(70), _q("initial_likes")), "70 times as many as the initial number of likes"),
            _eq(_q("recent_likes"), _c(20000), "received 20000 more new likes"),
            _eq(_q("total_likes"), _add(_q("later_likes"), _q("recent_likes")), "how many Instagram likes are there"),
        ],
        FISHIO_Q,
        "total_likes",
    )
    # Reading B (the reference's): 70x the initial arrived as *new* likes, added on top.
    game_b, query_b, value_b = _model(
        [
            ("initial_likes", "received 2000 likes"),
            ("new_likes", "70 times as many as the initial number of likes"),
            ("likes_after", "the number of likes was 70 times as many as the initial number of likes"),
            ("recent_likes", "received 20000 more new likes"),
            ("total_likes", "how many Instagram likes are there"),
        ],
        [
            _eq(_q("initial_likes"), _c(2000), "received 2000 likes"),
            _eq(_q("new_likes"), _mul(_c(70), _q("initial_likes")), "70 times as many as the initial number of likes"),
            _eq(_q("likes_after"), _add(_q("initial_likes"), _q("new_likes")), "the number of likes was 70 times as many as the initial number of likes"),
            _eq(_q("recent_likes"), _c(20000), "received 20000 more new likes"),
            _eq(_q("total_likes"), _add(_q("likes_after"), _q("recent_likes")), "how many Instagram likes are there"),
        ],
        FISHIO_Q,
        "total_likes",
    )
    return {
        "id": "gsm8k-test-0649",
        "sample_id": "gsm8k-test-0649",
        "source": SOURCE,
        "kind": "ambiguity",
        "reference": "162000",
        "engine_value": value_a,
        "reason": (
            "'received 70 times as many ... new likes' reads as 'became 70x the initial' "
            f"({value_a}) or as 'received 70x the initial as new likes' (the reference's "
            f"reading, {value_b}); both are arithmetically valid"
        ),
        "question": FISHIO_Q,
        "model": {"game": game_a, "query": query_a.model_dump(mode="json")},
        "alternative": {
            "value": value_b,
            "game": game_b,
            "query": query_b.model_dump(mode="json"),
        },
    }


def notes() -> list[dict]:
    return [_sasha(), _fishio()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the GSM8K dataset-notes artifact.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    collected = notes()
    with out.open("w", encoding="utf-8") as handle:
        for record in collected:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"wrote {len(collected)} notes to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
