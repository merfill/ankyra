"""Deterministic classification and application of an LLM proposal.

The model proposes; this module disposes. Nothing enters the theory without a
valid quote (``cited``) or an explicit hypothesis tag (``hypothesis``); a
proposal that is already entailed is a ``derivable`` no-op, and anything that
fails schema, safety or grounding rules is ``rejected`` with a reason code.
"""

from __future__ import annotations

from dataclasses import dataclass

from ankyra.build.normalize import is_var
from ankyra.build.symbolic import normalize_quote, quote_in_source, quote_only_in_conditional
from ankyra.core.models import Hypothesis, Morphism, ProposalCategory, Query, Rule, Theory
from ankyra.engine.builtins import builtin_unsafe
from ankyra.engine.horn import build_context, derive_store, instantiate, unify_pattern
from ankyra.engine.ledger import HypothesisLedger, morphism_key
from ankyra.engine.proposal import ProposalDraft, effective_action, payload_actions


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


def _quote_in_question(quote: str | None, question_text: str | None, source_text: str) -> bool:
    """True when the quote is taken from the interrogative span.

    The question is never asserted as a fact (Phase 0 separates them), so a quote
    drawn from the question cannot license a new axiom — otherwise the LLM could
    prove the goal by citing the goal itself. A question equal to the source means
    the split failed, so nothing is filtered.
    """
    question = (question_text or "").strip()
    source = (source_text or "").strip()
    if not question or question == source:
        return False
    return quote_in_source(quote, question)


def _quote_in_use(theory: Theory, quote: str | None) -> bool:
    """True when this quote already grounds a different theory element.

    A quote is a lexical witness for ONE formalization; reusing it to state a
    different atom or rule silently changes the formalization (drops a restriction
    or flips it), so the new element is an assumption, not ground. The caller has
    already ruled out the same atom via ``_adds_new_facts``, so any overlap with an
    already-grounded atom witness is a different formalization: a fact may not be
    grounded on an atom's quote, nor on a broader span that contains it. Rule
    *sentences* are compared exactly instead — a standalone fact whose phrase also
    occurs inside a conditional sentence is still citable (see the conditional-quote
    guard, which handles that case).
    """
    candidate = normalize_quote(quote)
    if not candidate:
        return False
    for morphism in theory.morphisms:
        used = normalize_quote(morphism.quote)
        if used and (candidate == used or candidate in used or used in candidate):
            return True
    return any(candidate == normalize_quote(rule.quote) for rule in theory.rules)


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


def _asserts_closed_target(morphism: Morphism, query: Query, theory: Theory) -> bool:
    """True when the proposed atom unifies the query target, and the target is closed.

    Assuming the goal itself is circular: a fact hypothesis that *is* the closed
    target derives nothing. Open targets are exempt — there the hypothesis supplies
    a binding (e.g. a class rule), which is the intended abduction.
    """
    target = query.target
    if target is None:
        return False
    if is_var(target.subject) or is_var(target.object):
        return False
    ctx = build_context(theory)
    fact = instantiate(morphism, ctx, {})
    if fact is None:
        return False
    return unify_pattern(target, fact, ctx, {}) is not None


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
    question_text: str = "",
) -> Classification:
    if not (morphism.predicate or "").strip():
        return Classification("rejected", "empty_predicate", theory, query)
    candidate = _with_morphism(theory, morphism)
    if not _adds_new_facts(theory, candidate):
        return Classification("derivable", "already_derivable", theory, query)
    quoted = quote_in_source(morphism.quote, source_text) and not _quote_in_question(
        morphism.quote, question_text, source_text
    )
    reused = quoted and _quote_in_use(theory, morphism.quote)
    conditional = quoted and quote_only_in_conditional(morphism.quote, theory)
    if quoted and not reused and not conditional:
        return Classification("cited", "cited", candidate, query)
    if not allow_hypotheses:
        if reused:
            reason = "quote_reused"
        elif conditional:
            reason = "quote_conditional"
        else:
            reason = "hypotheses_forbidden"
        return Classification("rejected", reason, theory, query)
    if _asserts_closed_target(morphism, query, theory):
        return Classification("rejected", "question_begging", theory, query)
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
    question_text: str = "",
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
            question_text=question_text,
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
    quoted = quote_in_source(rule.quote, source_text) and not _quote_in_question(
        rule.quote, question_text, source_text
    )
    reused = quoted and _quote_in_use(theory, rule.quote)
    conditional = quoted and quote_only_in_conditional(rule.quote, theory)
    if quoted and not reused and not conditional:
        return Classification("cited", "cited", candidate, query)
    if not allow_hypotheses:
        if reused:
            reason = "quote_reused"
        elif conditional:
            reason = "quote_conditional"
        else:
            reason = "hypotheses_forbidden"
        return Classification("rejected", reason, theory, query)
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
    question_text: str = "",
) -> Classification:
    """Classify and, when accepted, apply one proposal to the theory/query."""
    action = effective_action(draft)
    if action is None:
        reason = "ambiguous_payload" if len(payload_actions(draft)) > 1 else "missing_payload"
        return Classification("rejected", reason, theory, query)
    if action == "reformalize_query":
        return _reformalize(draft, theory, query)
    if action == "select_subgoal":
        return Classification("derivable", "subgoal_selected", theory, query)
    if action == "propose_rule":
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
            question_text=question_text,
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
        question_text=question_text,
    )
