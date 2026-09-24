"""GSM8K L4 harness: gold determinism/gate, sample carving, scoring."""

from __future__ import annotations

import json

from evals import build_gsm8k_gold, build_gsm8k_notes, build_gsm8k_sample as B
from evals.gsm8k import gold_path, load_sample, notes_path, run_gold, sample_path

GOLD = gold_path()
NOTES = notes_path()


def test_committed_gold_is_deterministic():
    committed = load_sample(GOLD)
    rebuilt = json.loads(json.dumps(build_gsm8k_gold.cases(), ensure_ascii=False))
    assert rebuilt == committed


def test_gold_gate_is_green_without_grounded_mismatch():
    results = run_gold(GOLD)
    assert len(results) == 8
    shapes = {result["shape"] for result in results}
    assert shapes == {"correct"}, [r for r in results if r["shape"] != "correct"]


def test_gold_rows_match_the_committed_dev_sample():
    dev = {row["id"]: row for row in load_sample(sample_path("dev"))}
    for record in load_sample(GOLD):
        assert record["sample_id"] in dev
        assert record["question"] == dev[record["sample_id"]]["question"]
        assert record["reference"] == dev[record["sample_id"]]["reference"]


def test_reference_extraction():
    assert B.reference("some work\n#### 18") == "18"
    assert B.reference("work\n#### 18,000") == "18000"


def test_carve_is_deterministic_and_disjoint():
    rows = [
        {"id": f"r{i}", "index": i, "question": "q", "answer": "a", "reference": str(i)}
        for i in range(B.DEV_SIZE + B.EVAL_SIZE + 5)
    ]
    first = B.carve(rows)
    second = B.carve(list(rows))
    assert first == second
    assert len(first["dev"]) == B.DEV_SIZE
    assert len(first["eval"]) == B.EVAL_SIZE
    assert {row["index"] for row in first["dev"]}.isdisjoint(
        {row["index"] for row in first["eval"]}
    )


def test_shape_classification():
    from evals.gsm8k import _shape

    assert _shape("determined", 25, "25") == "correct"
    assert _shape("determined", 24, "25") == "grounded_mismatch"
    assert _shape("underdetermined", None, "25") == "underdetermined"
    assert _shape("out_of_fragment", None, "25") == "out_of_fragment"


def _solve_model(model: dict) -> str:
    from ankyra.engine.numeric import NumericGame, NumericQuery, solve

    game = NumericGame.model_validate(model["game"])
    query = NumericQuery.model_validate(model["query"])
    return str(solve(game, query).value)


def test_committed_notes_are_deterministic():
    committed = load_sample(NOTES)
    rebuilt = json.loads(json.dumps(build_gsm8k_notes.notes(), ensure_ascii=False))
    assert rebuilt == committed


def test_notes_reproduce_the_reference_disagreement():
    notes = {note["id"]: note for note in load_sample(NOTES)}
    assert notes, "the dataset discrepancies must stay recorded"
    for note in notes.values():
        assert note["kind"] in {"dataset_error", "ambiguity"}
        assert note["reason"]
        assert _solve_model(note["model"]) == note["engine_value"]
        # The note exists precisely because the engine's value differs from the reference.
        assert note["engine_value"] != note["reference"]
        if note["kind"] == "ambiguity":
            alternative = note["alternative"]
            assert _solve_model(alternative) == alternative["value"] == note["reference"]


def test_notes_rows_match_the_committed_eval_sample():
    evaluation = {row["id"]: row for row in load_sample(sample_path("eval"))}
    for note in load_sample(NOTES):
        assert note["sample_id"] in evaluation
        assert note["question"] == evaluation[note["sample_id"]]["question"]
        assert note["reference"] == evaluation[note["sample_id"]]["reference"]
