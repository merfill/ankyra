"""End-to-end (offline) tests for builtin thresholds through the Phase 0 builder.

The builtin evaluator is deterministic, so thresholds are verified without an LLM:
structure -> Theory/Query -> verify -> Answer. Live tests only guard the extraction
side (whether the model emits ``gte``/``gt`` instead of an ``at_least_50`` object).
"""

from __future__ import annotations

import pytest

from ankyra.build.pipeline import build_query, build_theory
from ankyra.build.symbolic import symbolic_check
from ankyra.core.schemas import ProblemStructure, QuestionStructure
from ankyra.engine import builtins as builtins_module
from ankyra.engine.answer import build_answer
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.verify import verify


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(builtins_module, "builtins_enabled", lambda: True)


def _question(subject: str, obj: str) -> QuestionStructure:
    return QuestionStructure.model_validate(
        {"ask": {"predicate": "is_a", "subject": subject, "object": obj}}
    )


def _run(structure: ProblemStructure, question: QuestionStructure):
    theory = build_theory(structure)
    query = build_query(question)
    verdict = verify(theory, query)
    answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    return theory, query, verdict, answer


def _gte_problem(value: str) -> ProblemStructure:
    return ProblemStructure.model_validate(
        {
            "source_text": (
                f"Machine m has a power of {value} kilowatts and four wheels. "
                "Any machine with power of at least 50 kilowatts and at least four "
                "wheels is a car."
            ),
            "facts": [
                {"predicate": "power", "subject": "m", "object": value,
                 "quote": f"power of {value} kilowatts"},
                {"predicate": "wheel_count", "subject": "m", "object": "4",
                 "quote": "four wheels"},
            ],
            "rules": [
                {
                    "antecedent": [
                        {"predicate": "power", "subject": "?x", "object": "?p",
                         "quote": "power of at least 50 kilowatts"},
                        {"predicate": "gte", "subject": "?p", "object": "50",
                         "quote": "at least 50 kilowatts"},
                        {"predicate": "wheel_count", "subject": "?x", "object": "?w",
                         "quote": "at least four wheels"},
                        {"predicate": "gte", "subject": "?w", "object": "4",
                         "quote": "at least four wheels"},
                    ],
                    "consequent": {"predicate": "is_a", "subject": "?x", "object": "car",
                                   "quote": "is a car"},
                    "quote": "Any machine with power of at least 50 kilowatts and at "
                    "least four wheels is a car",
                }
            ],
        }
    )


def test_gte_threshold_is_proven_through_the_full_builder(enabled):
    theory, _query, verdict, answer = _run(_gte_problem("150"), _question("m", "car"))
    assert verdict.status == "supported"
    assert answer.kind == "yes"
    assert answer.strength == "proven"


def test_numeric_operands_are_not_reported_as_naming_gaps(enabled):
    theory, _query, _verdict, _answer = _run(_gte_problem("150"), _question("m", "car"))
    assert symbolic_check(theory).ok


def test_value_below_the_threshold_stays_unsupported(enabled):
    _theory, _query, verdict, answer = _run(_gte_problem("30"), _question("m", "car"))
    assert verdict.status == "unsupported"
    assert answer.kind == "unknown"
    assert answer.strength == "not_proven"


def test_gt_threshold(enabled):
    structure = ProblemStructure.model_validate(
        {
            "source_text": "Machine m has a power of 150 kilowatts. Any machine with "
            "power more than 100 kilowatts is powerful.",
            "facts": [
                {"predicate": "power", "subject": "m", "object": "150",
                 "quote": "power of 150 kilowatts"},
            ],
            "rules": [
                {
                    "antecedent": [
                        {"predicate": "power", "subject": "?x", "object": "?p",
                         "quote": "power more than 100 kilowatts"},
                        {"predicate": "gt", "subject": "?p", "object": "100",
                         "quote": "more than 100 kilowatts"},
                    ],
                    "consequent": {"predicate": "is_a", "subject": "?x", "object": "powerful",
                                   "quote": "is powerful"},
                    "quote": "Any machine with power more than 100 kilowatts is powerful",
                }
            ],
        }
    )
    _theory, _query, verdict, answer = _run(structure, _question("m", "powerful"))
    assert verdict.status == "supported"
    assert answer.strength == "proven"


def test_lte_threshold(enabled):
    structure = ProblemStructure.model_validate(
        {
            "source_text": "Machine m has a power of 30 kilowatts. Any machine with "
            "power at most 50 kilowatts is efficient.",
            "facts": [
                {"predicate": "power", "subject": "m", "object": "30",
                 "quote": "power of 30 kilowatts"},
            ],
            "rules": [
                {
                    "antecedent": [
                        {"predicate": "power", "subject": "?x", "object": "?p",
                         "quote": "power at most 50 kilowatts"},
                        {"predicate": "lte", "subject": "?p", "object": "50",
                         "quote": "at most 50 kilowatts"},
                    ],
                    "consequent": {"predicate": "is_a", "subject": "?x", "object": "efficient",
                                   "quote": "is efficient"},
                    "quote": "Any machine with power at most 50 kilowatts is efficient",
                }
            ],
        }
    )
    _theory, _query, verdict, answer = _run(structure, _question("m", "efficient"))
    assert verdict.status == "supported"
    assert answer.strength == "proven"


def test_string_neq_threshold(enabled):
    structure = ProblemStructure.model_validate(
        {
            "source_text": "Machine m is a sedan. Any machine that is not a boat is a "
            "vehicle.",
            "facts": [
                {"predicate": "is_a", "subject": "m", "object": "sedan",
                 "quote": "Machine m is a sedan"},
            ],
            "rules": [
                {
                    "antecedent": [
                        {"predicate": "is_a", "subject": "?x", "object": "?c",
                         "quote": "Any machine"},
                        {"predicate": "neq", "subject": "?c", "object": "boat",
                         "quote": "not a boat"},
                    ],
                    "consequent": {"predicate": "is_a", "subject": "?x", "object": "vehicle",
                                   "quote": "is a vehicle"},
                    "quote": "Any machine that is not a boat is a vehicle",
                }
            ],
        }
    )
    _theory, _query, verdict, answer = _run(structure, _question("m", "vehicle"))
    assert verdict.status == "supported"
    assert answer.strength == "proven"


def test_builtins_disabled_leave_the_threshold_unfired():
    theory, _query, verdict, answer = _run(_gte_problem("150"), _question("m", "car"))
    assert theory is not None
    assert verdict.status == "unsupported"
    assert answer.strength == "not_proven"
