"""LLM proposal stage: hint assembly, schema, and one call per wave.

The model proposes; the classifier disposes. The proposal is the only place the
LLM may name new predicates or rules, and it never decides their status.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ankyra.build.extract import builtins_block, format_theory_for_llm
from ankyra.core.models import Morphism, Proposal, ProposalAction, Query, Rule
from ankyra.engine.state import WaveContext
from ankyra.llm.client import extract_max_tokens, with_max_tokens
from ankyra.llm.structured import invoke_as_dict


class ProposalDraft(BaseModel):
    """One typed proposal plus its narration (the LLM's only output per wave)."""

    action: ProposalAction = Field(
        description="reformalize_query | propose_rule | assert_cited_fact | select_subgoal"
    )
    narration: str = Field(default="", description="Short natural-language reasoning.")
    rule: Rule | None = Field(default=None, description="Payload for propose_rule.")
    fact: Morphism | None = Field(default=None, description="Payload for assert_cited_fact.")
    query: Query | None = Field(default=None, description="Payload for reformalize_query.")
    subgoal: str = Field(default="", description="Payload for select_subgoal.")


PROPOSE_SYSTEM = """You are the proposal stage of a symbolic reasoning engine. The engine,
not you, owns truth: you propose exactly ONE action per wave and a deterministic
classifier decides whether it enters the theory. Never claim a result is proven.

Grounding rules:
- A fact or rule whose "quote" is a verbatim span of the source text is CITED and
  enters the theory as an axiom.
- A fact or rule without a valid quote is only a HYPOTHESIS: it is recorded with a
  tag and the final answer becomes "proven under" those tags. If hypotheses are
  disallowed, such a proposal is rejected.
- Do not repropose anything already derivable (it is a no-op).
- Use predicates and object ids from the theory vocabulary. A relation with no
  explicit argument omits that field. Reuse the theory's exact spellings.

Actions, with the field to fill:
- propose_rule: a Horn rule in "rule": {conditions: [atom...], consequence: atom,
  kind: implication|exception, quote: "..."}. Use it for deduction/class rules.
  A rule with no conditions is an unconditional fact.
- assert_cited_fact: one fact in "fact": {predicate, subject, object, modality,
  negated, quote}, with a valid quote when it is grounded in the text.
- reformalize_query: a replacement query in "query": {conditions: [atom...],
  target: atom, variables: {}, answer_type}. The target may not be dropped.
- select_subgoal: a short "subgoal" string.

An atom is {predicate, subject, object, modality, negated, quote}; modality is
permit | obligation | forbidden | neutral. Return ONLY valid JSON matching the
ProposalDraft schema, no markdown fences."""

PROPOSE_HUMAN = """{hint}

Propose exactly ONE action as ProposalDraft JSON."""


def _fmt(morphism: Morphism | None) -> str:
    if morphism is None:
        return "(none)"
    neg = "NOT " if morphism.negated else ""
    modality = "" if morphism.modality == "neutral" else f"{morphism.modality}:"
    args = ",".join(arg for arg in (morphism.subject, morphism.object) if arg)
    return f"{neg}{modality}{morphism.predicate}({args})"


def build_hint(ctx: WaveContext) -> str:
    """Problem + theory + verdict + frontier, the full context for one proposal."""
    conditions = ", ".join(_fmt(c) for c in ctx.query.conditions) or "(none)"
    target = _fmt(ctx.query.target)
    gaps = ", ".join(ctx.verdict.gaps) or "(none)"
    frontier = ", ".join(ctx.frontier[:40]) or "(none)"
    hypotheses = ", ".join(hypothesis.id for hypothesis in ctx.hypotheses) or "(none)"
    return (
        f"Wave: {ctx.wave}\n"
        f"Hypotheses allowed: {ctx.allow_hypotheses}\n"
        f"Existing hypotheses: {hypotheses}\n\n"
        f"Source text:\n{ctx.source_text.strip()}\n"
        f"{format_theory_for_llm(ctx.theory)}\n"
        f"Question conditions: {conditions}\n"
        f"Target: {target}\n"
        f"Verdict: {ctx.verdict.status}\n"
        f"Gaps: {gaps}\n"
        f"Derived frontier: {frontier}\n"
    )


def propose(llm: Any, ctx: WaveContext) -> ProposalDraft:
    """One structured-output call: the model's single proposed action."""
    messages = [
        SystemMessage(content=PROPOSE_SYSTEM + builtins_block()),
        HumanMessage(content=PROPOSE_HUMAN.format(hint=build_hint(ctx))),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(ctx.source_text))
    data = invoke_as_dict(
        llm, messages, schema=ProposalDraft, label=f"propose_wave{ctx.wave}"
    )
    return ProposalDraft.model_validate(data)


def signature(draft: ProposalDraft) -> str:
    """Stable identity of a proposal, used to detect a no-progress repeat."""
    return repr(draft.model_dump())


def to_proposal(draft: ProposalDraft) -> Proposal:
    """Typed draft -> the auditable proposal recorded in a ``WaveRecord``."""
    payload: dict = {}
    if draft.rule is not None:
        payload["rule"] = draft.rule.model_dump()
    if draft.fact is not None:
        payload["fact"] = draft.fact.model_dump()
    if draft.query is not None:
        payload["query"] = draft.query.model_dump()
    if draft.subgoal:
        payload["subgoal"] = draft.subgoal
    return Proposal(action=draft.action, narration=draft.narration, payload=payload)
