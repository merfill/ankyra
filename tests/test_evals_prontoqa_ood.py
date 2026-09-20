"""ProntoQA-OOD adapter and sample builder (offline; no LLM)."""

from __future__ import annotations

from types import SimpleNamespace

from ankyra.core.models import Answer, Morphism, Query
from evals import build_prontoqa_ood_sample as builder
from evals import prontoqa_ood


def _result(target, kind, *, strength="proven", status="supported"):
    query = Query(target=target, answer_type="yes_no") if target is not None else Query(target=None)
    return SimpleNamespace(
        query=query,
        answer=Answer(value=None, kind=kind, strength=strength),
        status=status,
    )


def test_committed_sample_is_stratified():
    records = prontoqa_ood.load_sample()
    assert len(records) == 44
    rule_types = {r["rule_type"] for r in records}
    assert {"OrIntro", "OrElim", "ProofByContra", "Composed"} <= rule_types
    classes = {r["class"] for r in records}
    assert {"horn", "l2_decomp", "l2_reductio", "l2_reductio+decomp"} <= classes
    assert {r["statement_negative"] for r in records} == {True, False}


def test_problem_text_keeps_theory_and_query():
    record = prontoqa_ood.load_sample()[0]
    text = prontoqa_ood.problem_text(record)
    assert record["question"].strip() in text
    assert record["query"].strip() in text


def test_score_positive_statement():
    record = {"id": "x", "rule_type": "OrIntro", "class": "l2_decomp", "statement_negative": False, "answer": "A"}
    score = prontoqa_ood.score_record(record, _result(Morphism(predicate="is_a", subject="fae", object="sterpus"), "yes"))
    assert score["kind_match"] and score["polarity_flipped"] is False


def test_score_negative_statement_confirmed_by_refutation():
    record = {"id": "y", "rule_type": "ProofByContra", "class": "l2_reductio", "statement_negative": True, "answer": "A"}
    score = prontoqa_ood.score_record(record, _result(Morphism(predicate="is_a", subject="wren", object="yumpus"), "no", status="refuted"))
    assert score["kind_match"] and score["polarity_flipped"] is True


def test_score_without_a_target_is_not_scored():
    record = {"id": "z", "rule_type": "Composed", "class": "l2_reductio", "statement_negative": False, "answer": "A"}
    score = prontoqa_ood.score_record(record, _result(None, "unknown", strength="not_proven", status="unsupported"))
    assert score["polarity_known"] is False
    assert not score["kind_match"]


def test_score_compound_goal_expects_yes_regardless_of_a_negated_conjunct():
    record = {"id": "c", "rule_type": "Composed", "class": "l2_decomp", "statement_negative": True, "answer": "A"}
    query = Query(
        target=Morphism(predicate="is_a", subject="wren", object="yumpus"),
        goals=[
            Morphism(predicate="is_a", subject="wren", object="yumpus"),
            Morphism(predicate="is_a", subject="wren", object="shumpus", negated=True),
        ],
        goal_mode="all",
        answer_type="yes_no",
    )
    result = SimpleNamespace(
        query=query,
        answer=Answer(value="yes", kind="yes", strength="proven"),
        status="supported",
    )
    score = prontoqa_ood.score_record(record, result)
    assert score["compound"] and score["kind_match"] and score["expected_kind"] == "yes"


def test_out_of_fragment_is_counted():
    record = {"id": "w", "rule_type": "Composed", "class": "l2_reductio", "statement_negative": False, "answer": "A"}
    score = prontoqa_ood.score_record(record, _result(None, "unknown", strength="not_proven", status="out_of_fragment"))
    assert score["out_of_fragment"]


def test_to_problem_selects_the_ground_logic():
    record = prontoqa_ood.load_sample()[0]
    problem = prontoqa_ood._to_problem(record, allow_hypotheses=False)
    assert problem["logic"] == "ground"
    assert problem["world_assumption"] == "open"
    assert problem["builtins"] is False and problem["defeasible"] is False


def _rows():
    rows = []
    for rule in ("OrIntro", "OrElim", "ProofByContra"):
        for kind in ("horn", "l2_decomp", "l2_reductio"):
            for index in range(20):
                rows.append({"id": f"{rule}-{kind}-{index}", "rule_type": rule, "class": kind})
    return rows


def test_select_is_deterministic_and_smaller_tiers_are_prefixes():
    rows = _rows()
    first = builder.select(rows, "a")
    second = builder.select(list(reversed(rows)), "a")
    assert [r["id"] for r in first] == [r["id"] for r in second]
    assert {r["id"] for r in builder.select(rows, "a")} <= {r["id"] for r in builder.select(rows, "b")}
