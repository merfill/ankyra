"""AR-LSAT L3 harness: gold determinism/gate, sample integrity, metadata helpers."""

from __future__ import annotations

import json

from evals import build_ar_lsat_gold, build_ar_lsat_sample as B
from evals.ar_lsat import load_sample, run_gold, sample_path

GOLD = B.DATA / "ar_lsat_gold.jsonl"


def test_committed_gold_is_deterministic():
    committed = load_sample(GOLD)
    rebuilt = json.loads(json.dumps(build_ar_lsat_gold.cases(), ensure_ascii=False))
    assert rebuilt == committed


def test_gold_gate_is_green_without_grounded_mismatch():
    results = run_gold(GOLD)
    assert results, "gold set is empty"
    shapes = {result["shape"] for result in results}
    assert shapes == {"correct"}, [r for r in results if r["shape"] != "correct"]
    assert len(results) == 21  # 5 games, committed


def test_dev_eval_samples_are_game_disjoint_and_balanced():
    dev = load_sample(sample_path("dev"))
    evaluation = load_sample(sample_path("eval"))
    assert dev and evaluation
    # fatherId-disjoint: no game family leaks between the debugging and gate pools.
    assert {row["fatherId"] for row in dev}.isdisjoint({row["fatherId"] for row in evaluation})
    for rows in (dev, evaluation):
        assert all(row["in_fragment"] for row in rows)
        answers = [row["answer_letter"] for row in rows]
        assert max(answers.count(letter) for letter in "ABCDE") - min(
            answers.count(letter) for letter in "ABCDE"
        ) <= 2
        assert {row["question_kind"] for row in rows} <= B.IN_FRAGMENT


def test_metadata_normalization():
    assert B.normalize_kind("must be false (cannot be true)") == "must_be_false"
    assert B.normalize_kind("“if” / could be true") == "could"
    assert B.normalize_kind("acceptability") == "not_violate"
    assert B.normalize_kind("complete and accurate list") == "complete_list"
    assert B.normalize_kind("rule substitution") == "out"
    assert B.normalize_kind("how many") == "out"
    assert B.normalize_kind("") == "other"
    assert B.has_assumption("“if” clause / must be true")
    assert B.has_assumption("pifq / could be true")
    assert not B.has_assumption("must be true")


def test_select_questions_balances_kinds_and_answers():
    rows = []
    for index, kind in enumerate(["could", "must", "must_be_false", "not_violate"]):
        for offset, letter in enumerate("ABC"):
            rows.append(
                {
                    "id": f"r{index}{offset}",
                    "question_kind": kind,
                    "answer_letter": letter,
                    "in_fragment": True,
                }
            )
    selected = B._select_questions(rows, target=4)
    assert len(selected) == 4
    # Greedy balance: all four kinds appear before any kind repeats.
    assert len({row["question_kind"] for row in selected}) == 4
