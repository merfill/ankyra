"""Deterministic classification and application of an LLM proposal.

The model proposes; this module disposes. Nothing enters the theory without a
valid quote (``cited``) or an explicit hypothesis tag (``hypothesis``); a
proposal that is already entailed is a ``derivable`` no-op, and anything that
fails schema, safety or grounding rules is ``rejected`` with a reason code.
"""

from __future__ import annotations

from dataclasses import dataclass

from ankyra.build.normalize import is_var
from ankyra.build.symbolic import quote_in_source
from ankyra.core.models import Hypothesis, Morphism, ProposalCategory, Query, Rule, Theory
from ankyra.engine.builtins import builtin_unsafe
from ankyra.engine.horn import build_context, derive_store, instantiate
from ankyra.engine.ledger import HypothesisLedger, morphism_key
from ankyra.engine.proposal import ProposalDraft


@dataclass
class Classification:
    category: ProposalCategory
    reason: str
    theory: Theory
    query: Query
    hypothesis: Hypothesis | None = None


def _closure_keys(theory: Theory) -> set:
    return {fact.key for fact in derive_store(theory).facts}


def _adds_new_facts(theory: Theory, candidate: Theory) -> bool:
    return bool(_closure_keys(candidate) - _closure_keys(theory))


def _unsafe_rule(rule: Rule) -> bool:
    """Range restriction: every variable in the head must occur in the body."""
    body = {v for cond in rule.conditions for v in (cond.subject, cond.object) if is_var(v)}
    head = {v for v in (rule.consequence.subject, rule.consequence.object) if is_var(v)}
    return bool(head - body)


def _empty_predicates(rule: Rule) -> bool:
    if not (rule.consequence.predicate or "").strip():
        return True
    return any(not (cond.predicate or "").strip() for cond in rule.conditions)


def _with_morphism(theory: Theory, morphism: Morphism) -> Theory:
    return theory.model_copy(update={"morphisms": [*theory.morphisms, morphism]})


def _with_rule(theory: Theory, rule: Rule) -> Theory:
    return theory.model_copy(update={"rules": [*theory.rules, rule]})


def _atom_key(morphism: Morphism) -> tuple:
    return (
        morphism.predicate,
        morphism.subject,
        morphism.object,
        morphism.negated,
        morphism.modality,
    )


def _grounded_key(morphism: Morphism, theory: Theory):
    fact = instantiate(morphism, build_context(theory), {})
    return fact.key if fact is not None else morphism_key(morphism)


def _apply_atom(
    morphism: Morphism,
    theory: Theory,
    query: Query,
    ledger: HypothesisLedger,
    *,
    source_text: str,
    allow_hypotheses: bool,
    wave: int,
    narration: str,
) -> Classification:
    if not (morphism.predicate or "").strip():
        return Classification("rejected", "empty_predicate", theory, query)
    candidate = _with_morphism(theory, morphism)
    if not _adds_new_facts(theory, candidate):
        return Classification("derivable", "already_derivable", theory, query)
    if quote_in_source(morphism.quote, source_text):
        return Classification("cited", "cited", candidate, query)
    if not allow_hypotheses:
        return Classification("rejected", "hypotheses_forbidden", theory, query)
    hypothesis_id = ledger.next_id()
    hypothesis = ledger.add_fact(
        hypothesis_id,
        morphism,
        key=_grounded_key(morphism, candidate),
        rationale=narration,
        wave=wave,
    )
    return Classification("hypothesis", f"hypothesis:{hypothesis_id}", candidate, query, hypothesis)


def _apply_rule(
    rule: Rule,
    theory: Theory,
    query: Query,
    ledger: HypothesisLedger,
    *,
    source_text: str,
    allow_hypotheses: bool,
    wave: int,
    narration: str,
) -> Classification:
    if not rule.conditions:
        quoted = rule.consequence.model_copy(update={"quote": rule.consequence.quote or rule.quote})
        return _apply_atom(
            quoted,
            theory,
            query,
            ledger,
            source_text=source_text,
            allow_hypotheses=allow_hypotheses,
            wave=wave,
            narration=narration,
        )
    if _empty_predicates(rule):
        return Classification("rejected", "empty_predicate", theory, query)
    if _unsafe_rule(rule):
        return Classification("rejected", "unsafe_rule", theory, query)
    if builtin_unsafe(rule):
        return Classification("rejected", "unsafe_builtin", theory, query)
    candidate = _with_rule(theory, rule)
    if not _adds_new_facts(theory, candidate):
        return Classification("derivable", "already_derivable", theory, query)
    if quote_in_source(rule.quote, source_text):
        return Classification("cited", "cited", candidate, query)
    if not allow_hypotheses:
        return Classification("rejected", "hypotheses_forbidden", theory, query)
    hypothesis_id = ledger.next_id()
    tagged = rule.model_copy(update={"source": f"hypothesis:{hypothesis_id}"})
    candidate = _with_rule(theory, tagged)
    hypothesis = ledger.add_rule(
        hypothesis_id,
        tagged,
        rule_index=len(candidate.rules),
        rationale=narration,
        wave=wave,
    )
    return Classification("hypothesis", f"hypothesis:{hypothesis_id}", candidate, query, hypothesis)


def _merge_conditions(old: list[Morphism], new: list[Morphism]) -> list[Morphism]:
    merged = list(old)
    seen = {_atom_key(cond) for cond in merged}
    for cond in new:
        key = _atom_key(cond)
        if key not in seen:
            seen.add(key)
            merged.append(cond)
    return merged


def _reformalize(draft: ProposalDraft, theory: Theory, query: Query) -> Classification:
    if draft.query is None:
        return Classification("rejected", "missing_payload", theory, query)
    if query.target is not None and draft.query.target is None:
        return Classification("rejected", "target_weakened", theory, query)
    target = draft.query.target if draft.query.target is not None else query.target
    updated = query.model_copy(
        update={
            "conditions": _merge_conditions(query.conditions, draft.query.conditions),
            "target": target,
            "variables": {**query.variables, **draft.query.variables},
        }
    )
    if updated == query:
        return Classification("derivable", "no_change", theory, query)
    return Classification("derivable", "reformalized", theory, updated)


def classify(
    draft: ProposalDraft,
    theory: Theory,
    query: Query,
    ledger: HypothesisLedger,
    *,
    source_text: str,
    allow_hypotheses: bool,
    wave: int,
) -> Classification:
    """Classify and, when accepted, apply one proposal to the theory/query."""
    if draft.action == "reformalize_query":
        return _reformalize(draft, theory, query)
    if draft.action == "select_subgoal":
        return Classification("derivable", "subgoal_selected", theory, query)
    if draft.action == "propose_rule":
        if draft.rule is None:
            return Classification("rejected", "missing_payload", theory, query)
        return _apply_rule(
            draft.rule,
            theory,
            query,
            ledger,
            source_text=source_text,
            allow_hypotheses=allow_hypotheses,
            wave=wave,
            narration=draft.narration,
        )
    if draft.fact is None:
        return Classification("rejected", "missing_payload", theory, query)
    return _apply_atom(
        draft.fact,
        theory,
        query,
        ledger,
        source_text=source_text,
        allow_hypotheses=allow_hypotheses,
        wave=wave,
        narration=draft.narration,
    )
