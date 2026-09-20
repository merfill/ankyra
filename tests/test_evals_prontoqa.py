"""ProntoQA adapter and sample builder (offline; no LLM)."""

from __future__ import annotations

from types import SimpleNamespace

from ankyra.core.models import Answer, Morphism, Query
from evals import build_prontoqa_sample as builder
from evals import prontoqa


def _result(target, kind, *, strength="proven", status="supported"):
    return SimpleNamespace(
        query=Query(target=target, answer_type="yes_no"),
        answer=Answer(value=None, kind=kind, strength=strength),
        status=status,
    )


def test_committed_sample_has_both_shapes_and_polarities():
    records = prontoqa.load_sample()
    assert len(records) == 48
    shapes = {r["proof_shape"] for r in records}
    assert shapes == {"positive", "negation"}
    assert {r["statement_negative"] for r in records} == {True, False}
    assert all(r["context"] and r["question"] for r in records)


def test_tier_b_sample_is_balanced():
    from collections import Counter

    records = prontoqa.load_sample(prontoqa.sample_path("b"))
    assert len(records) == 160
    counts = Counter((r["proof_shape"], r["statement_negative"]) for r in records)
    assert counts[("positive", False)] == 40
    assert counts[("positive", True)] == 40
    assert counts[("negation", False)] == 40
    assert counts[("negation", True)] == 40


def test_problem_text_keeps_context_and_question():
    record = prontoqa.load_sample()[0]
    text = prontoqa.problem_text(record)
    assert record["context"].strip() in text
    assert record["question"].strip() in text


def test_expected_kind_flips_for_a_negative_statement():
    assert prontoqa.expected_kind("A", flipped=False) == "yes"
    assert prontoqa.expected_kind("B", flipped=False) == "no"
    assert prontoqa.expected_kind("A", flipped=True) == "no"
    assert prontoqa.expected_kind("B", flipped=True) == "yes"


def test_score_positive_statement_refuted():
    record = {"id": "x", "proof_shape": "negation", "statement_negative": False, "answer": "B"}
    result = _result(Morphism(predicate="is_a", subject="sally", object="bony"), "no", status="refuted")
    score = prontoqa.score_record(record, result)
    assert score["kind_match"] and score["polarity_flipped"] is False


def test_score_negative_statement_confirmed():
    record = {"id": "y", "proof_shape": "negation", "statement_negative": True, "answer": "A"}
    result = _result(Morphism(predicate="is_a", subject="sally", object="bony"), "no", status="refuted")
    score = prontoqa.score_record(record, result)
    assert score["kind_match"] and score["polarity_flipped"] is True


def test_score_without_an_extracted_target_is_not_scored():
    record = {"id": "z", "proof_shape": "positive", "statement_negative": False, "answer": "A"}
    result = _result(None, "unknown", strength="not_proven", status="unsupported")
    score = prontoqa.score_record(record, result)
    assert score["polarity_known"] is False
    assert not score["kind_match"]


def test_to_problem_declares_an_open_world():
    record = prontoqa.load_sample()[0]
    problem = prontoqa._to_problem(record, allow_hypotheses=False)
    assert problem["world_assumption"] == "open"
    assert problem["builtins"] is False and problem["defeasible"] is False


def _row(record_id, context, cot, answer="A", question="Is the following statement true or false? A is B."):
    return {
        "id": record_id,
        "context": context,
        "question": question,
        "answer": answer,
        "chain_of_thought": cot,
    }


def test_builder_selects_deterministically_and_balances_polarity():
    rows = []
    for index in range(6):
        rows.append(
            _row(
                f"example{index}",
                f"Every c{index} is a d. Every d is an e. A is a c{index}.",
                "Step 1: A is a c.\nStep 2: A is a d.",
                answer="A",
                question=f"Is the following statement true or false? A is not d.",
            )
        )
    for index in range(6):
        rows.append(
            _row(
                f"example1{index}",
                f"Every p{index} is a q. Every q is not r. A is a p{index}.",
                "Step 1: A is a p.\nStep 2: A is not r.",
                answer="B",
                question=f"Is the following statement true or false? A is r.",
            )
        )
    first = builder.select(rows, "a")
    second = builder.select(list(reversed(rows)), "a")
    assert [r["id"] for r in first] == [r["id"] for r in second]
    assert {r["proof_shape"] for r in first} == {"positive", "negation"}
