"""Core domain models: theory, query, verdict, answer, and provenance.

The LLM never authors these directly; Phase 0 emits ``StructAtom``/``StructRule``
(see ``ankyra.core.schemas``) and a deterministic builder assembles the models
below. Modality is a typed field, never encoded in the predicate name.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Modality = Literal["permit", "obligation", "forbidden", "neutral"]
RuleKind = Literal["implication", "exception"]
HypothesisKind = Literal["rule", "fact"]
AnswerType = Literal["yes_no", "open", "instruction"]
Status = Literal["supported", "insufficient", "unsupported", "refuted", "no_progress", "budget"]
AnswerStrength = Literal["proven", "proven_under", "not_proven"]
ProposalAction = Literal["reformalize_query", "propose_rule", "assert_cited_fact", "select_subgoal"]
ProposalCategory = Literal["derivable", "cited", "hypothesis", "rejected"]
Shelf = Literal["proven", "attested", "refused"]

# Provenance key of a ground atom. Subject/object use "" for a missing argument;
# modality is part of atom identity, so obligation/pay never unifies with permit/pay.
FactKey = tuple[str, str, str, bool, str]

# English modality inflections normalise by root prefix; closed set (~5 roots).
_MODALITY_ROOTS: list[tuple[str, str]] = [
    ("perm", "permit"),  # permit, permitted, permission, permissible
    ("allow", "permit"),  # allowed, allowable
    ("obli", "obligation"),  # obligation, obligatory, obligated
    ("requi", "obligation"),  # required
    ("manda", "obligation"),  # mandatory
    ("forbi", "forbidden"),  # forbidden, forbids
    ("prohi", "forbidden"),  # prohibited, prohibitive
    ("bann", "forbidden"),  # banned
    ("neutr", "neutral"),  # neutral
]


def normalize_modality(value: Any) -> str:
    """Map any English inflection/synonym to a canonical modality by root prefix."""
    if not isinstance(value, str) or not value.strip():
        return "neutral"
    v = value.strip().lower()
    for root, canonical in _MODALITY_ROOTS:
        if v.startswith(root):
            return canonical
    if v in {"may", "can"}:
        return "permit"
    if v in {"must", "shall"}:
        return "obligation"
    return v


class Object(BaseModel):
    """Canonical vertex in a theory."""

    id: str = Field(description="Canonical object id.")


class Morphism(BaseModel):
    """An arrow: an asserted fact, a rule slot, or a query triple.

    Negation is the same predicate with ``negated = true``; there is no separate
    negative name. Modality is a typed field, not part of the predicate name.
    """

    predicate: str = Field(description="Relation id (lowercase snake_case).")
    subject: str | None = Field(default=None, description="Object id or ?variable.")
    object: str | None = Field(default=None, description="Object id, ?variable, or null.")
    modality: Modality = Field(default="neutral", description="permit | obligation | forbidden | neutral.")
    quote: str | None = Field(default=None, description="Optional verbatim source span.")
    negated: bool = Field(default=False, description="True if this arrow is denied.")

    @field_validator("modality", mode="before")
    @classmethod
    def _coerce_modality(cls, value: Any) -> Any:
        return normalize_modality(value)


class Rule(BaseModel):
    """A Horn clause: ``conditions`` (AND) => ``consequence``."""

    conditions: list[Morphism] = Field(default_factory=list)
    consequence: Morphism = Field(description="Conclusion; never a plain string.")
    kind: RuleKind = Field(default="implication")
    source: str = Field(
        default="quote",
        description="'quote' when grounded in the text, else 'hypothesis:<id>'.",
    )
    quote: str | None = Field(default=None, description="Verbatim source span supporting the rule.")

    @field_validator("source", mode="before")
    @classmethod
    def _validate_source(cls, value: Any) -> str:
        text = str(value or "").strip()
        if text == "quote":
            return text
        if text.startswith("hypothesis:") and text.split(":", 1)[1].strip():
            return text
        raise ValueError("source must be 'quote' or 'hypothesis:<id>'")

    @property
    def source_hypothesis_id(self) -> str | None:
        if self.source.startswith("hypothesis:"):
            return self.source.split(":", 1)[1]
        return None


class Theory(BaseModel):
    """Objects, asserted axioms (``morphisms``), and Horn ``rules``.

    ``source_text`` is carried for deterministic quote checks (Phase 0); the
    engine ignores it.
    """

    objects: list[Object] = Field(default_factory=list)
    morphisms: list[Morphism] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    source_text: str = Field(default="", description="Original problem text; injected by Phase 0.")


class Query(BaseModel):
    """Conditions (Gamma), target (phi, may contain ``?x``), and answer type."""

    conditions: list[Morphism] = Field(default_factory=list)
    target: Morphism | None = Field(default=None)
    variables: dict[str, str] = Field(default_factory=dict)
    answer_type: AnswerType = Field(default="yes_no")


class Fact(BaseModel):
    """Engine-internal ground atom plus provenance."""

    predicate: str = ""
    subject: str = ""
    object: str = ""
    negated: bool = False
    modality: Modality = "neutral"
    used: frozenset[FactKey] = Field(
        default_factory=frozenset, description="Transitive provenance keys (hypothesis accounting)."
    )
    premises: frozenset[FactKey] = Field(
        default_factory=frozenset, description="Direct premises of this fact's derivation."
    )
    witness: str = ""
    axiom: bool = False
    rule_index: int | None = None

    @field_validator("subject", "object", mode="before")
    @classmethod
    def _coerce_blank(cls, value: Any) -> str:
        return "" if value is None else value

    @field_validator("modality", mode="before")
    @classmethod
    def _coerce_modality(cls, value: Any) -> Any:
        return normalize_modality(value)

    @property
    def key(self) -> FactKey:
        return (self.predicate, self.subject, self.object, self.negated, self.modality)

    def label(self) -> str:
        neg = "NOT " if self.negated else ""
        mod = "" if self.modality == "neutral" else f"{self.modality}:"
        args = [a for a in (self.subject, self.object) if a]
        return f"{neg}{mod}{self.predicate}({','.join(args)})"


class Hypothesis(BaseModel):
    """A tagged assumption from the ledger: a proposed rule or fact."""

    id: str
    kind: HypothesisKind
    payload: Rule | Morphism | None = Field(default=None)
    wave: int = 0
    rationale: str = ""


class Verdict(BaseModel):
    """Result of ``verify``: status, bindings, gaps, witnesses, shelf."""

    status: Status
    bindings: dict[str, str] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list, description="Codes: target_unmatched:, condition_unmatched:, unused_premise:, contradiction:")
    matched: list[str] = Field(default_factory=list)
    shelf: Shelf = Field(default="attested")
    unused_premises: list[int] = Field(default_factory=list, description="Indices of query conditions no winning proof uses.")


class Proposal(BaseModel):
    """One typed LLM proposal plus its narration."""

    action: ProposalAction
    narration: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class WaveRecord(BaseModel):
    """Auditable trace of one reasoning wave."""

    wave: int
    proposal: Proposal | None = Field(default=None)
    category: ProposalCategory
    reason: str = ""
    verdict_after: Verdict


class Answer(BaseModel):
    """Final answer with its explicit strength and hypothesis accounting."""

    value: str | None = Field(default=None)
    strength: AnswerStrength = Field(default="not_proven")
    hypotheses_used: list[str] = Field(default_factory=list)


ExplanationKind = Literal["axiom", "assumption", "rule", "is_a", "hypothesis"]


class ExplanationStep(BaseModel):
    """One derivation step, mapped to a real provenance edge or a hypothesis."""

    index: int
    kind: ExplanationKind
    statement: str
    premises: list[int] = Field(default_factory=list, description="Indices of premise steps.")
    rule_index: int | None = None
    rule: str | None = Field(default=None, description="Rendered rule 'IF ... => ... [kind]' for rule steps.")
    source: str | None = Field(default=None, description="'quote' or 'hypothesis:<id>'.")
    quote: str | None = None
    hypothesis: str | None = None


class Explanation(BaseModel):
    """Mechanical proof trace, ordered from premises to the goal."""

    goal: str | None = None
    binding: dict[str, str] = Field(default_factory=dict)
    hypotheses_used: list[str] = Field(default_factory=list)
    steps: list[ExplanationStep] = Field(default_factory=list)
