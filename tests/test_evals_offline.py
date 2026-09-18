"""Offline tests for the eval harness: flag handling and trace rendering."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ankyra.build.pipeline import build_theory
from ankyra.config.settings import settings
from ankyra.core.models import (
    Conflict,
    Explanation,
    ExplanationStep,
    Morphism,
    Query,
    Rule,
    Theory,
)
from ankyra.core.schemas import ProblemStructure
from evals import narrate as narrate_mod
from evals import run as run_mod
from evals.evaluators import VocabularyEvaluator


class _FakeResult:
    """Minimal shape ``run_one`` reads from a ``run_problem`` result."""

    def __init__(self) -> None:
        self.status = "unsupported"
        self.structure = None
        self.theory = None
        self.query = None
        self.verdict = None
        self.answer = None
        self.explanation = None
        self.history: list = []
        self.hypotheses: list = []


def _reset_flags(previous: dict) -> None:
    for name, value in previous.items():
        settings.set(name, value)


def test_run_one_applies_and_restores_per_problem_flags(monkeypatch):
    previous = {
        "BUILTINS": settings.get("BUILTINS", False),
        "DEFEASIBLE": settings.get("DEFEASIBLE", False),
    }
    settings.set("BUILTINS", False)
    settings.set("DEFEASIBLE", False)
    seen = {}

    def fake_run_problem(text, *, allow_hypotheses, max_waves):
        seen["builtins"] = settings.get("BUILTINS")
        seen["defeasible"] = settings.get("DEFEASIBLE")
        return _FakeResult()

    monkeypatch.setattr(run_mod, "run_problem", fake_run_problem)
    try:
        trace, _ = run_mod.run_one(
            {"id": "p1", "text": "x", "builtins": True, "defeasible": True}
        )
        assert seen == {"builtins": True, "defeasible": True}
        assert settings.get("BUILTINS") is False
        assert settings.get("DEFEASIBLE") is False
        assert trace["id"] == "p1"
    finally:
        _reset_flags(previous)


def test_run_one_restores_flags_when_the_run_raises(monkeypatch):
    previous = {
        "BUILTINS": settings.get("BUILTINS", False),
        "DEFEASIBLE": settings.get("DEFEASIBLE", False),
    }
    settings.set("BUILTINS", False)
    settings.set("DEFEASIBLE", False)

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(run_mod, "run_problem", boom)
    try:
        with pytest.raises(RuntimeError):
            run_mod.run_one({"id": "p1", "text": "x", "builtins": True, "defeasible": True})
        assert settings.get("BUILTINS") is False
        assert settings.get("DEFEASIBLE") is False
    finally:
        _reset_flags(previous)


def _vocabulary_result(condition: Morphism) -> SimpleNamespace:
    structure = ProblemStructure.model_validate(
        {
            "source_text": "It is raining. If it is raining, the ground is wet.",
            "objects": ["ground"],
            "facts": [{"predicate": "raining", "quote": "it is raining"}],
            "rules": [
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
        }
    )
    theory = build_theory(structure)
    query = Query(
        conditions=[condition], target=Morphism(predicate="is_wet", subject="ground")
    )
    return SimpleNamespace(query=query, theory=theory, structure=structure)


def test_vocabulary_evaluator_reports_reuse():
    result = _vocabulary_result(Morphism(predicate="raining", subject="ground"))
    score = VocabularyEvaluator().evaluate({}, result, {})
    assert score.passed is True
    assert score.metrics["condition_predicate_reuse"] == 1.0
    assert score.metrics["new_condition_predicates"] == []


def test_vocabulary_evaluator_flags_a_new_condition_predicate():
    result = _vocabulary_result(Morphism(predicate="snowing", subject="ground"))
    score = VocabularyEvaluator().evaluate({}, result, {})
    assert score.metrics["condition_predicate_reuse"] == 0.0
    assert score.metrics["new_condition_predicates"] == ["snowing"]
    assert "snowing" in score.notes[0]


def test_vocabulary_evaluator_reports_a_non_theory_constant_without_failing():
    result = _vocabulary_result(Morphism(predicate="raining", subject="moon"))
    score = VocabularyEvaluator().evaluate({}, result, {})
    assert score.passed is True
    assert score.metrics["condition_predicate_reuse"] == 1.0
    assert score.metrics["non_theory_condition_ids"] == ["moon"]


def test_vocabulary_evaluator_handles_a_missing_query():
    result = SimpleNamespace(query=None, theory=None, structure=None)
    score = VocabularyEvaluator().evaluate({}, result, {})
    assert score.passed is True
    assert score.metrics["condition_predicate_reuse"] == 1.0


def test_summary_reports_vocabulary_reuse():
    trace = {
        "status": "supported",
        "answer": {"strength": "proven"},
        "scores": [
            {"name": "invariants", "passed": True, "metrics": {}, "notes": []},
            {
                "name": "vocabulary",
                "passed": True,
                "metrics": {"condition_predicate_reuse": 0.5},
                "notes": [],
            },
        ],
        "llm_calls": [],
    }
    assert "vocab_reuse=0.50" in run_mod._summary([trace])


def test_with_rule_text_fills_missing_rule_text():
    theory = Theory(
        rules=[
            Rule(
                conditions=[Morphism(predicate="p")],
                consequence=Morphism(predicate="q"),
            )
        ]
    )
    explanation = Explanation(
        goal="q()",
        steps=[ExplanationStep(index=0, kind="rule", statement="q()", rule_index=1)],
    )
    filled = narrate_mod._with_rule_text(explanation, theory)
    assert filled.steps[0].rule == "IF p() => q() [implication, defeasible]"
    assert narrate_mod._with_rule_text(explanation, None) is explanation


def test_with_rule_text_ignores_an_out_of_range_rule_index():
    theory = Theory(
        rules=[Rule(conditions=[Morphism(predicate="p")], consequence=Morphism(predicate="q"))]
    )
    explanation = Explanation(
        steps=[ExplanationStep(index=0, kind="rule", statement="q()", rule_index=5)]
    )
    assert narrate_mod._with_rule_text(explanation, theory).steps[0].rule is None


def test_steps_renders_derivation_or_a_placeholder():
    assert narrate_mod._steps(Explanation()) == "  (no derivation)"
    explanation = Explanation(
        goal="q()",
        steps=[
            ExplanationStep(index=0, kind="axiom", statement="p()", source="quote", quote="p"),
            ExplanationStep(
                index=1,
                kind="rule",
                statement="q()",
                premises=[0],
                rule_index=1,
                rule="IF p() => q() [implication, defeasible]",
            ),
        ],
    )
    text = narrate_mod._steps(explanation)
    assert "1. [rule] q()" in text
    assert "<- [0]" in text
    assert "rule 1: IF p() => q()" in text


def test_conflict_block_marks_empty_branches():
    assert narrate_mod._conflict_block(Explanation()) == ""
    conflict = Conflict(
        kind="defeasible",
        status="undecided",
        supporting=[ExplanationStep(index=0, kind="rule", statement="p()")],
        attacking=[],
        defeated="none",
        reason="no is_a relation decides",
    )
    block = narrate_mod._conflict_block(Explanation(goal="p()", conflict=conflict))
    assert "Conflict (defeasible, undecided, defeated=none)" in block
    assert "no is_a relation decides" in block
    assert "supporting:" in block and "attacking:" in block
    assert "(none)" in block


def test_verdict_block_reports_gaps_bindings_and_waves():
    trace = {
        "verdict": {
            "gaps": ["target_unmatched:q"],
            "bindings": {"?z": "b", "ignored": "x"},
            "unused_premises": [1],
        },
        "frontier": ["p()"],
        "waves": [{"wave": 1, "category": "added", "reason": ""}],
    }
    block = narrate_mod._verdict_block(trace)
    assert "Gaps: target_unmatched:q" in block
    assert "Bindings: {'?z': 'b'}" in block
    assert "Unused premises: [1]" in block
    assert "Frontier: p()" in block
    assert "Waves: w1:added" in block
    assert narrate_mod._verdict_block({}) == ""


def test_narrate_main_renders_an_old_trace_without_kind(tmp_path, capsys, monkeypatch):
    trace = {
        "status": "supported",
        "answer": {"value": "yes", "strength": "proven", "hypotheses_used": []},
        "explanation": {
            "goal": "q()",
            "steps": [
                {"index": 0, "kind": "axiom", "statement": "p()", "source": "quote", "quote": "p"},
                {"index": 1, "kind": "rule", "statement": "q()", "premises": [0]},
            ],
        },
        "verdict": {"gaps": []},
    }
    (tmp_path / "p1.json").write_text(json.dumps(trace), encoding="utf-8")
    problem = {"id": "p1", "level": 1, "text": "p, therefore q?"}
    monkeypatch.setattr(narrate_mod, "load_problems", lambda: [problem])
    monkeypatch.setattr(narrate_mod, "create_chat_llm", lambda role: object())
    monkeypatch.setattr(narrate_mod, "narrate_explanation", lambda *args, **kwargs: "narrative")

    rc = narrate_mod.main(["--out", str(tmp_path), "--ids", "p1"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "kind: unknown" in out
    assert "narrative" in out
    assert "Ответ" in out
