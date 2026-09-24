"""Answer assembly: explicit strength and hypothesis accounting."""

from __future__ import annotations

from ankyra.core.models import Answer, AnswerKind, FactKey, Query, Theory, Verdict
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.verify import winning_proof

_ANSWER_LABELS = {
    "en": {
        "label": "Answer",
        "yes": "Yes",
        "no": "No",
        "unknown": "Unknown",
        "contradiction": "Inconsistent (both the claim and its negation hold)",
        "binding": "Value: {value}",
        "choice": "Choice: {value}",
        "number": "Number: {value}",
        "instruction": "No question to answer",
        "under": "under hypotheses: {h}",
        "default": "by default",
    },
    "ru": {
        "label": "Ответ",
        "yes": "Да",
        "no": "Нет",
        "unknown": "Не определено",
        "contradiction": "Противоречие (выводимы и утверждение, и его отрицание)",
        "binding": "Значение: {value}",
        "choice": "Вариант: {value}",
        "number": "Число: {value}",
        "instruction": "Вопрос не задан",
        "under": "при гипотезах: {h}",
        "default": "по умолчанию",
    },
}


def _answer_kind(query: Query, status: str, value: str | None) -> AnswerKind:
    """Deterministic answer shape from the verdict status and the answer type."""
    if query.target is None:
        return "instruction"
    if status == "contradiction":
        return "contradiction"
    if status == "refuted":
        return "no" if query.answer_type == "yes_no" else "unknown"
    if status == "supported":
        if query.answer_type == "yes_no":
            return "yes"
        return "binding" if value else "unknown"
    return "unknown"


def render_answer(answer: Answer, language: str | None = None) -> str:
    """Localized one-line direct answer (deterministic; no LLM)."""
    lang = "ru" if str(language or "").lower().startswith("ru") else "en"
    labels = _ANSWER_LABELS[lang]
    kind = answer.kind
    text = labels[kind]
    if kind in ("binding", "choice", "number") and answer.value:
        text = text.format(value=answer.value)
    qualifiers = []
    if answer.strength == "proven_under" and answer.hypotheses_used:
        qualifiers.append(labels["under"].format(h=", ".join(answer.hypotheses_used)))
    if answer.defeasible:
        qualifiers.append(labels["default"])
    if qualifiers:
        text = f"{text} ({'; '.join(qualifiers)})"
    return f"{labels['label']}: {text}"


def refutation_is_hypothetical(
    theory: Theory, query: Query, ledger: HypothesisLedger
) -> bool:
    """True when the target's refutation rests on a hypothesis, not grounded facts.

    A hypothesis is an assumption: assuming ``P`` does not establish that ``¬P`` is
    false. In an open-world setting the absence of a grounded counter-proof is
    ``unknown``, so a hypothetical counter-derivation must not be reported as a
    refutation (and thus as a definite "no"). Strict deduction is unaffected: with
    no hypotheses the ledger attributes nothing and this returns ``False``.
    """
    if query.target is None:
        return False
    negated_goal = query.target.model_copy(update={"negated": not query.target.negated})
    proof = winning_proof(theory, query, goal=negated_goal)
    if proof is None:
        return False
    store, proof_keys = proof
    return bool(ledger.used(store, proof_keys))


def _uses_defeasible(theory: Theory, store, proof_keys: frozenset[FactKey]) -> bool:
    """True when any fact in the proof was derived by a defeasible rule."""
    for key in proof_keys:
        fact = store.by_key.get(key)
        if fact is not None and fact.rule_index is not None:
            rule = theory.rules[fact.rule_index - 1]
            if rule.strength == "defeasible":
                return True
    return False


def build_answer(
    theory: Theory,
    query: Query,
    verdict: Verdict,
    ledger: HypothesisLedger,
    status: str,
) -> Answer:
    """``proven`` uses no hypotheses; any hypothesis in the proof gives ``proven_under``."""
    if status == "refuted" and query.target is not None and any(
        gap.startswith("target_refuted:") for gap in verdict.gaps
    ):
        # The target is false: answer "no" and attribute the negative proof.
        negated_goal = query.target.model_copy(update={"negated": not query.target.negated})
        proof = winning_proof(theory, query, goal=negated_goal)
        hypotheses_used = ledger.used(proof[0], proof[1]) if proof else []
        defeasible = _uses_defeasible(theory, proof[0], proof[1]) if proof else False
        value = "no" if query.answer_type == "yes_no" else None
        return Answer(
            value=value,
            kind=_answer_kind(query, status, value),
            strength="proven" if not hypotheses_used else "proven_under",
            hypotheses_used=hypotheses_used,
            defeasible=defeasible,
        )
    if status != "supported":
        return Answer(
            value=None,
            kind=_answer_kind(query, status, None),
            strength="not_proven",
            hypotheses_used=[],
        )
    proof = winning_proof(theory, query)
    hypotheses_used = ledger.used(proof[0], proof[1]) if proof else []
    defeasible = _uses_defeasible(theory, proof[0], proof[1]) if proof else False
    if query.answer_type == "yes_no":
        value: str | None = "yes"
    elif query.answer_type == "open":
        bound = ", ".join(
            f"{key}={val}" for key, val in verdict.bindings.items() if key.startswith("?")
        )
        value = bound or None
    else:
        value = None
    strength = "proven" if not hypotheses_used else "proven_under"
    return Answer(
        value=value,
        kind=_answer_kind(query, status, value),
        strength=strength,
        hypotheses_used=hypotheses_used,
        defeasible=defeasible,
    )
