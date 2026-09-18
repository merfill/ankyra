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
    "contradiction",
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

    branches = [] if explanation is None else [explanation.steps]
    if explanation is not None and explanation.conflict is not None:
        branches += [explanation.conflict.supporting, explanation.conflict.attacking]
    for steps in branches:
        for step in steps:
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
        if "kind" in expect and answer.kind != expect["kind"]:
            notes.append(f"kind: want {expect['kind']!r}, got {answer.kind!r}")
        if "strength" in expect and answer.strength != expect["strength"]:
            notes.append(f"strength: want {expect['strength']!r}, got {answer.strength!r}")
        if "answer" in expect and (answer.value or "").strip().lower() != str(
            expect["answer"]
        ).strip().lower():
            notes.append(f"answer: want {expect['answer']!r}, got {answer.value!r}")
        return EvalScore(name=self.name, passed=not notes, notes=notes)


def _vocabulary(theory: Any) -> tuple[set[str], set[str]]:
    """Theory predicate names and non-variable object ids."""
    predicates: set[str] = set()
    objects: set[str] = set()

    def visit(morphism: Any) -> None:
        if morphism.predicate:
            predicates.add(morphism.predicate)
        for term in (morphism.subject, morphism.object):
            if term and not term.startswith("?"):
                objects.add(term)

    for morphism in theory.morphisms:
        visit(morphism)
    for rule in theory.rules:
        for condition in rule.conditions:
            visit(condition)
        visit(rule.consequence)
    for obj in theory.objects:
        if obj.id:
            objects.add(obj.id)
    return predicates, objects


class VocabularyEvaluator:
    """Descriptive metric: how much the question conditions reuse the theory vocabulary.

    This never fails a run. ASK/target is exempt (it may use its own wording), and a
    non-theory object id is allowed by design (a named constant the theory omits), so
    both are reported as counts rather than violations.
    """

    name = "vocabulary"

    def evaluate(self, problem: dict, result: Any, trace: dict) -> EvalScore:
        query = getattr(result, "query", None)
        theory = getattr(result, "theory", None)
        structure = getattr(result, "structure", None)
        if query is None or theory is None:
            return EvalScore(
                name=self.name,
                passed=True,
                metrics={
                    "condition_predicates": 0,
                    "condition_predicate_reuse": 1.0,
                    "new_condition_predicates": [],
                    "non_theory_condition_ids": [],
                },
            )
        if structure is not None:
            try:
                from ankyra.build.pipeline import build_theory

                theory = build_theory(structure)
            except Exception:
                pass
        predicates, objects = _vocabulary(theory)

        conditions = list(query.conditions or [])
        condition_predicates = [c.predicate for c in conditions if c.predicate]
        matched = [p for p in condition_predicates if p in predicates]
        new_predicates = sorted({p for p in condition_predicates if p not in predicates})
        constants = sorted(
            {
                term
                for condition in conditions
                for term in (condition.subject, condition.object)
                if term and not term.startswith("?")
            }
        )
        new_constants = sorted({term for term in constants if term not in objects})
        reuse = len(matched) / len(condition_predicates) if condition_predicates else 1.0

        notes: list[str] = []
        if new_predicates:
            notes.append(f"new condition predicates: {', '.join(new_predicates)}")
        if new_constants:
            notes.append(f"non-theory condition ids: {', '.join(new_constants)}")
        return EvalScore(
            name=self.name,
            passed=True,
            notes=notes,
            metrics={
                "condition_predicates": len(condition_predicates),
                "condition_predicate_reuse": round(reuse, 3),
                "new_condition_predicates": new_predicates,
                "non_theory_condition_ids": new_constants,
            },
        )
