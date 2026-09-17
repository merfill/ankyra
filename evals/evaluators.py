"""Evaluators: hard engine invariants and soft expectation checks.

Invariants must always hold and are asserted by tests. Expectations compare
against the problem's ideal outcome and are reported as metrics, because they
depend on LLM extraction quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

_TERMINAL_STATUSES = {
    "supported",
    "insufficient",
    "unsupported",
    "refuted",
    "no_progress",
    "budget",
    "proposal_error",
    "extraction_error",
}


@dataclass
class EvalScore:
    name: str
    passed: bool
    notes: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class Evaluator(Protocol):
    name: str

    def evaluate(self, problem: dict, result: Any, trace: dict) -> EvalScore: ...


def invariant_violations(problem: dict, result: Any) -> list[str]:
    """Violations of properties that must hold for every run."""
    violations: list[str] = []
    answer, verdict, explanation = result.answer, result.verdict, result.explanation
    if answer is None or verdict is None:
        if result.status in {"extraction_error", "proposal_error"}:
            return []
        return ["pipeline produced no answer or verdict"]

    if result.status not in _TERMINAL_STATUSES:
        violations.append(f"unknown terminal status {result.status!r}")
    if answer.strength not in {"proven", "proven_under", "not_proven"}:
        violations.append(f"unknown answer strength {answer.strength!r}")
    if answer.strength == "proven" and answer.hypotheses_used:
        violations.append("proven answer depends on hypotheses")
    if answer.strength == "proven_under" and not answer.hypotheses_used:
        violations.append("proven_under answer lists no hypotheses")
    if not problem.get("allow_hypotheses", True) and answer.strength == "proven_under":
        violations.append("proven_under while hypotheses are disallowed")

    if verdict.status == "supported":
        if explanation is None or not explanation.steps:
            violations.append("supported verdict without explanation steps")
        elif explanation.goal is None:
            violations.append("supported verdict without a goal label")

    if explanation is not None:
        for step in explanation.steps:
            for premise in step.premises:
                if not 0 <= premise < step.index:
                    violations.append(
                        f"non-topological premise {premise} at step {step.index}"
                    )
    return violations


class InvariantEvaluator:
    name = "invariants"

    def evaluate(self, problem: dict, result: Any, trace: dict) -> EvalScore:
        violations = invariant_violations(problem, result)
        return EvalScore(name=self.name, passed=not violations, notes=violations)


class ExpectationEvaluator:
    name = "expectations"

    def evaluate(self, problem: dict, result: Any, trace: dict) -> EvalScore:
        expect = problem.get("expect") or {}
        answer = result.answer
        if not expect or answer is None:
            return EvalScore(name=self.name, passed=True)
        notes: list[str] = []
        if "status" in expect and result.status != expect["status"]:
            notes.append(f"status: want {expect['status']!r}, got {result.status!r}")
        if "strength" in expect and answer.strength != expect["strength"]:
            notes.append(f"strength: want {expect['strength']!r}, got {answer.strength!r}")
        if "answer" in expect and (answer.value or "").strip().lower() != str(
            expect["answer"]
        ).strip().lower():
            notes.append(f"answer: want {expect['answer']!r}, got {answer.value!r}")
        return EvalScore(name=self.name, passed=not notes, notes=notes)
