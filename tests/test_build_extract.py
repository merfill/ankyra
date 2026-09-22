"""Tests for the Phase 0 LLM extraction (live tests are opt-in)."""

from __future__ import annotations

import os

import pytest

from ankyra.build import extract as extract_mod
from ankyra.build.extract import (
    extract_problem_structure,
    extract_question_structure,
    format_theory_for_llm,
    language_spec_block,
)
from ankyra.config.settings import setting_overrides
from ankyra.core.models import Morphism, Object, Rule, Theory
from ankyra.core.schemas import ProblemStructure, QuestionStructure

live = pytest.mark.skipif(
    not os.getenv("ANKYRA_LIVE"),
    reason="set ANKYRA_LIVE=1 to call the LLM",
)


def test_format_theory_for_llm_lists_vocabulary_and_rules():
    theory = Theory(
        objects=[Object(id="ground")],
        morphisms=[Morphism(predicate="raining", quote="raining")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
            )
        ],
    )
    text = format_theory_for_llm(theory)
    assert "raining" in text
    assert "is_wet" in text
    assert "R1: IF raining" in text


@pytest.mark.live
@live
def test_live_problem_and_question_extraction():
    from ankyra.build.pipeline import build_query, build_theory
    from ankyra.engine.verify import verify
    from ankyra.llm.client import create_chat_llm

    problem = "It is raining. If it is raining, the ground is wet. Is the ground wet?"
    llm = create_chat_llm(role="extract")
    structure = extract_problem_structure(llm, text=problem)
    assert structure.question.strip()

    theory = build_theory(structure)
    question = extract_question_structure(
        llm, question=structure.question, theory=theory, source_text=problem
    )
    query = build_query(question)
    verdict = verify(theory, query)
    assert verdict.status in {"supported", "insufficient", "unsupported", "refuted"}


def _problem_structure(text: str, **extra) -> ProblemStructure:
    return ProblemStructure.model_validate({"source_text": text, **extra})


def test_problem_extraction_picks_the_better_sample(monkeypatch):
    text = "It is raining. If it is raining, the ground is wet."
    partial = _problem_structure(
        text, facts=[{"predicate": "raining", "quote": "it is raining"}]
    )
    full = _problem_structure(
        text,
        facts=[{"predicate": "raining", "quote": "it is raining"}],
        rules=[
            {
                "antecedent": [{"predicate": "raining", "quote": "if it is raining"}],
                "consequent": {
                    "predicate": "is_wet",
                    "object": "ground",
                    "quote": "the ground is wet",
                },
                "quote": "if it is raining, the ground is wet",
            }
        ],
    )
    samples = iter([partial, full])
    monkeypatch.setattr(extract_mod, "_extract_problem_once", lambda _llm, _text: next(samples))
    chosen = extract_problem_structure(object(), text=text, samples=2, repairs=0)
    assert chosen is full


def test_problem_extraction_tolerates_a_failed_sample(monkeypatch):
    text = "It is raining."
    good = _problem_structure(text, facts=[{"predicate": "raining", "quote": "it is raining"}])
    calls = {"n": 0}

    def flaky(_llm, _text):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return good

    monkeypatch.setattr(extract_mod, "_extract_problem_once", flaky)
    assert extract_problem_structure(object(), text=text, samples=2, repairs=0) is good


def test_problem_extraction_raises_when_every_sample_fails(monkeypatch):
    def boom(_llm, _text):
        raise RuntimeError("nope")

    monkeypatch.setattr(extract_mod, "_extract_problem_once", boom)
    with pytest.raises(RuntimeError):
        extract_problem_structure(object(), text="x", samples=2, repairs=0)


def test_problem_extraction_repairs_repairable_gaps(monkeypatch):
    text = "It is raining."
    bad = _problem_structure(
        text, facts=[{"predicate": "raining", "quote": "it snowed"}]
    )
    good = _problem_structure(
        text, facts=[{"predicate": "raining", "quote": "it is raining"}]
    )
    monkeypatch.setattr(extract_mod, "_extract_problem_once", lambda _llm, _text: bad)
    seen: dict = {}

    def fake_repair(_llm, _text, structure, gaps):
        seen["gaps"] = gaps
        return good

    monkeypatch.setattr(extract_mod, "_repair_problem_once", fake_repair)
    chosen = extract_problem_structure(object(), text=text, samples=1, repairs=1)
    assert chosen is good
    assert any(gap.startswith("missing_quote") for gap in seen["gaps"])


def test_problem_extraction_skips_repair_without_repairable_gaps(monkeypatch):
    text = "It is raining."
    good = _problem_structure(text, facts=[{"predicate": "raining", "quote": "it is raining"}])
    monkeypatch.setattr(extract_mod, "_extract_problem_once", lambda _llm, _text: good)

    def boom(*_args, **_kwargs):
        raise AssertionError("repair must not run when there is nothing to repair")

    monkeypatch.setattr(extract_mod, "_repair_problem_once", boom)
    assert extract_problem_structure(object(), text=text, samples=1, repairs=1) is good


def test_question_extraction_picks_the_more_grounded_sample(monkeypatch):
    question = "Is the ground wet?"
    bad = QuestionStructure.model_validate(
        {
            "source_text": question,
            "ask": {"predicate": "is_wet", "object": "ground", "quote": "not in the question"},
        }
    )
    good = QuestionStructure.model_validate(
        {
            "source_text": question,
            "ask": {"predicate": "is_wet", "object": "ground", "quote": "ground wet"},
        }
    )
    samples = iter([bad, good])
    monkeypatch.setattr(extract_mod, "_extract_question_once", lambda *args: next(samples))
    chosen = extract_question_structure(
        object(), question=question, theory=Theory(), source_text=question, samples=2, repairs=0
    )
    assert chosen is good


def _factory(sequence):
    iterator = iter(sequence)
    return lambda: next(iterator)


def test_best_of_breaks_ties_independently_of_order(monkeypatch):
    a = _problem_structure("x", facts=[{"predicate": "p", "subject": "a", "quote": "x"}])
    b = _problem_structure("x", facts=[{"predicate": "p", "subject": "b", "quote": "x"}])
    score = lambda _candidate: (0, 0, 0)  # noqa: E731 - deliberate tie

    monkeypatch.setattr(extract_mod, "_parallel_enabled", lambda: False)
    sequential = {
        extract_mod._pick_best(_factory([a, b]), score, 2).model_dump_json(),
        extract_mod._pick_best(_factory([b, a]), score, 2).model_dump_json(),
    }
    monkeypatch.setattr(extract_mod, "_parallel_enabled", lambda: True)
    parallel = {
        extract_mod._pick_best(_factory([a, b]), score, 2).model_dump_json(),
        extract_mod._pick_best(_factory([b, a]), score, 2).model_dump_json(),
    }
    assert len(sequential) == 1
    assert sequential == parallel


def test_parallel_samples_keep_the_llm_trace(monkeypatch):
    from ankyra.llm import trace as llm_trace

    def make_candidate():
        current = llm_trace.current_trace()
        if current is not None:
            current.record(llm_trace.LLMCall(label="probe", messages=[]))
        return _problem_structure("x")

    monkeypatch.setattr(extract_mod, "_parallel_enabled", lambda: True)
    with llm_trace.tracing() as active:
        extract_mod._pick_best(make_candidate, lambda _candidate: (0, 0, 0), 3)
    assert len(active.calls) == 3


def test_problem_prompt_teaches_the_l2_forms():
    for token in ('"consequents"', '"disjunctive_antecedent"', '"disjunctions"', '"existentials"'):
        assert token in extract_mod.PROBLEM_SYSTEM
    # The conjunctive-conclusion guidance must point at the slot set.
    assert "set" in extract_mod.PROBLEM_SYSTEM
    assert "one rule per conjunct" in extract_mod.PROBLEM_SYSTEM


def test_problem_prompt_teaches_the_generic_disjunction_head():
    assert "GENERIC disjunction" in extract_mod.PROBLEM_SYSTEM
    assert "DISJUNCTIVE HEAD" in extract_mod.PROBLEM_SYSTEM


def test_problem_prompt_requires_retaining_every_ground_premise():
    assert "Retain EVERY atomic premise" in extract_mod.PROBLEM_SYSTEM


def test_question_prompt_teaches_compound_goals():
    assert '"ask_all"' in extract_mod.QUESTION_SYSTEM
    assert '"ask_any"' in extract_mod.QUESTION_SYSTEM


def test_question_prompt_teaches_the_universal_goal_form():
    assert '"ask_universal"' in extract_mod.QUESTION_SYSTEM


def test_question_prompt_teaches_the_ground_cnf_goal_form():
    assert '"ask_clauses"' in extract_mod.QUESTION_SYSTEM


def test_question_prompt_teaches_shared_witness_and_named_constants():
    assert "SHARED witness" in extract_mod.QUESTION_SYSTEM
    assert "CONJUNCTION (AND)" in extract_mod.QUESTION_SYSTEM


def test_language_spec_block_is_empty_by_default():
    assert language_spec_block() == ""
    with setting_overrides(LANGUAGE_SPEC=""):
        assert language_spec_block() == ""


def test_language_spec_block_reads_inline_text_and_files(tmp_path):
    with setting_overrides(LANGUAGE_SPEC="read positions left to right"):
        inline = language_spec_block()
    assert "ADDITIONAL LANGUAGE SPECIFICATION" in inline
    assert "read positions left to right" in inline

    guide = tmp_path / "guide.md"
    guide.write_text("a per-object list is ordered", encoding="utf-8")
    with setting_overrides(LANGUAGE_SPEC=str(guide)):
        from_file = language_spec_block()
    assert "a per-object list is ordered" in from_file
    assert "guide.md" in from_file
