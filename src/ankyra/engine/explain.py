"""Mechanical explanation: walk the provenance of the winning proof.

The trace is built only from real derivation edges (``premises`` / ``rule_index``)
and identified hypotheses; the LLM never authors it. Steps are ordered from
premises to the goal by a post-order DFS, so every premise index is smaller than
the step that uses it.
"""

from __future__ import annotations

from ankyra.core.models import (
    Explanation,
    ExplanationKind,
    ExplanationStep,
    Fact,
    FactKey,
    Query,
    Theory,
    Verdict,
)
from ankyra.engine.ledger import HypothesisLedger, morphism_key
from ankyra.engine.verify import winning_store_hit


def render_atom(morphism) -> str:
    """Readable atom, including modality and negation: ``obligation:pay(alice)``."""
    neg = "NOT " if morphism.negated else ""
    modality = "" if morphism.modality == "neutral" else f"{morphism.modality}:"
    args = ",".join(arg for arg in (morphism.subject, morphism.object) if arg)
    return f"{neg}{modality}{morphism.predicate}({args})"


def render_rule(rule) -> str:
    """Readable Horn rule: ``IF is_a(?x,dog) => is_a(?x,mammal) [implication]``."""
    conditions = " AND ".join(render_atom(condition) for condition in rule.conditions) or "TRUE"
    return f"IF {conditions} => {render_atom(rule.consequence)} [{rule.kind}]"


def _classify_fact(
    fact: Fact,
    theory: Theory,
    ledger: HypothesisLedger,
    axiom_quotes: dict[FactKey, str | None],
) -> tuple[ExplanationKind, str | None, str | None, str | None, int | None]:
    if fact.key in ledger.fact_keys:
        return "hypothesis", None, None, ledger.fact_keys[fact.key], fact.rule_index
    quote = axiom_quotes.get(fact.key)
    if fact.axiom:
        return "axiom", "quote" if quote else None, quote, None, None
    if fact.rule_index is not None:
        rule = theory.rules[fact.rule_index - 1]
        return "rule", rule.source, rule.quote, rule.source_hypothesis_id, fact.rule_index
    if fact.witness.startswith("is_a:"):
        return "is_a", None, None, None, None
    return "assumption", None, None, None, None


def build_explanation(
    theory: Theory,
    query: Query,
    verdict: Verdict,
    ledger: HypothesisLedger,
) -> Explanation:
    """The ordered derivation of the goal, or an empty trace if it is not proven."""
    result = winning_store_hit(theory, query)
    if result is None:
        return Explanation()
    store, hit = result
    axiom_quotes = {morphism_key(m): m.quote for m in theory.morphisms}
    steps: list[ExplanationStep] = []
    index_of: dict[FactKey, int] = {}

    def visit(key: FactKey) -> int | None:
        if key in index_of:
            return index_of[key]
        fact = store.by_key.get(key)
        if fact is None:
            return None
        premise_ids = []
        for premise in sorted(fact.premises):
            premise_id = visit(premise)
            if premise_id is not None:
                premise_ids.append(premise_id)
        kind, source, quote, hypothesis, rule_index = _classify_fact(
            fact, theory, ledger, axiom_quotes
        )
        rule_text = (
            render_rule(theory.rules[rule_index - 1])
            if kind == "rule" and rule_index is not None
            else None
        )
        index = len(steps)
        steps.append(
            ExplanationStep(
                index=index,
                kind=kind,
                statement=fact.label(),
                premises=premise_ids,
                rule_index=rule_index,
                rule=rule_text,
                source=source,
                quote=quote,
                hypothesis=hypothesis,
            )
        )
        index_of[key] = index
        return index

    visit(hit.fact.key)
    proof_keys = frozenset(hit.fact.used) | {hit.fact.key}
    return Explanation(
        goal=hit.fact.label(),
        binding=dict(verdict.bindings),
        hypotheses_used=ledger.used(store, proof_keys),
        steps=steps,
    )
