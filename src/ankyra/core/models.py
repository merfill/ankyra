"""Core domain models: theory, query, verdict, answer, and provenance.

The LLM never authors these directly; Phase 0 emits ``StructAtom``/``StructRule``
(see ``ankyra.core.schemas``) and a deterministic builder assembles the models
below. Modality is a typed field, never encoded in the predicate name.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Modality = Literal["permit", "obligation", "forbidden", "neutral"]
RuleKind = Literal["implication", "exception"]
RuleStrength = Literal["strict", "defeasible"]
# Per-query world assumption (L1). ``closed`` enables negation-as-failure for the
# query; ``open`` (default) is the usual open-world reading. It is a semantic choice
# carried by the query, never guessed from wording (docs/l1_plan.md D-L1-4).
WorldAssumption = Literal["open", "closed"]
# How a decomposed question goal is read (L2, D-L2-7): ``single`` is the ordinary
# one-target query; ``all`` requires every goal (a conjunctive question); ``any``
# requires some goal (a disjunctive question); ``forall`` is a universally quantified
# clause goal "∀x (l₁ ∨ … ∨ lₙ)" (T3), whose goals are the clause literals. The goals
# are the decomposed conjuncts/disjuncts/literals; ``Query.target`` still names the
# first one for echo/answer use.
GoalMode = Literal["single", "all", "any", "forall"]
ConstraintKind = Literal["disjoint"]
HypothesisKind = Literal["rule", "fact"]
AnswerType = Literal["yes_no", "open", "instruction"]
AnswerKind = Literal["yes", "no", "unknown", "contradiction", "binding", "instruction"]
Status = Literal[
    "supported",
    "insufficient",
    "unsupported",
    "refuted",
    "contradiction",
    "no_progress",
    "budget",
    "out_of_fragment",
]
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

    @model_validator(mode="after")
    def _canonicalize_unary_slot(self) -> "Morphism":
        """A single-argument atom always uses ``subject``; slots are positional.

        ``subject``/``object`` carry no meaning for a unary relation, so the
        builder and the question must agree on one slot. Both sides normalize here,
        which is what lets ``wet(ground)`` from a rule match ``wet(ground)`` from a
        question regardless of which slot the extractor chose.
        """
        if self.object and not self.subject:
            self.subject = self.object
            self.object = None
        return self


class Rule(BaseModel):
    """A clause: ``conditions`` (AND) => ``head`` (disjunction of consequences).

    The head is ``consequence`` plus any ``alternatives``. A Horn rule has none. A
    disjunctive head (``A ∨ B ← G``) lists the other disjuncts there, and a
    disjunctive ground fact (``A ∨ B``) is a conditionless rule with alternatives
    (L2, ``docs/l2_plan.md`` D-L2-3). The Horn engine fires only Horn rules; the L2
    procedure handles the disjunctive ones.
    """

    conditions: list[Morphism] = Field(default_factory=list)
    consequence: Morphism = Field(description="First head literal; never a plain string.")
    alternatives: list[Morphism] = Field(
        default_factory=list,
        description="Other disjuncts of the head; empty for a Horn rule (L2).",
    )
    kind: RuleKind = Field(default="implication")
    forall: dict[str, str] = Field(
        default_factory=dict,
        description="Audit only: the quantifier's sorted domain (var -> sort), carried from "
        "Phase 0. The engine ignores it; the sort was already used to drop the domain premise.",
    )
    source: str = Field(
        default="quote",
        description="'quote' when grounded in the text, else 'hypothesis:<id>'.",
    )
    quote: str | None = Field(default=None, description="Verbatim source span supporting the rule.")

    @property
    def strength(self) -> RuleStrength:
        """Every rule is a default; only asserted facts/axioms are strict.

        The LLM never authors strength, and no predicate heuristic is guessed:
        class-taxonomy rules are defaults too, so an `is_a` conflict is resolved by
        specificity like any other (and reported undecided when it cannot be).
        """
        return "defeasible"

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

    @property
    def head(self) -> list[Morphism]:
        """Every head literal: the consequence plus the disjunctive alternatives."""
        return [self.consequence, *self.alternatives]

    @property
    def is_horn(self) -> bool:
        """True when the head has a single literal (a Horn clause)."""
        return not self.alternatives


class Existential(BaseModel):
    """A conjunctive existential premise: ``∃variable (atom ∧ …)`` (L2).

    Phase 0 records the quantifier structure; the prover Skolemizes it (a fresh
    constant per existential) during clausification. It is deliberately not expanded
    by the builder: Skolemization is a decision-procedure step, not extraction
    (docs/folio.md §4, docs/l2_plan.md §7.4).
    """

    variable: str = Field(default="?x", description="The existentially quantified variable.")
    atoms: list[Morphism] = Field(default_factory=list, description="The conjoined atoms over it.")
    quote: str | None = Field(default=None, description="Optional verbatim source span.")


class Constraint(BaseModel):
    """A negative constraint between two classes: no individual is both.

    ``disjoint`` is the only kind today: ``¬∃x(is_a(x, left) ∧ is_a(x, right))``.
    The sides are class ids (the ``object`` of an ``is_a`` atom). It is a strict
    axiom, not a Horn rule, so the engine derives a negative conclusion from one
    side (``is_a(a, left)`` yields ``¬is_a(a, right)``). It is deliberately not
    encoded as negation-as-failure: two sibling classes would form a negative cycle
    and break stratification (docs/l1_plan.md D-L1-2).
    """

    kind: ConstraintKind = Field(default="disjoint")
    left: str = Field(description="One disjoint class id.")
    right: str = Field(description="The other disjoint class id.")
    quote: str | None = Field(default=None, description="Optional verbatim source span.")


class Theory(BaseModel):
    """Objects, asserted axioms (``morphisms``), and Horn ``rules``.

    ``source_text`` is carried for deterministic quote checks (Phase 0); the
    engine ignores it. ``domain`` names the universe sorts of the problem: a
    condition that restricts a rule to a domain sort is the quantifier's domain,
    not a premise, so the builder drops it (see ``build.enrich``).
    """

    objects: list[Object] = Field(default_factory=list)
    morphisms: list[Morphism] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    constraints: list[Constraint] = Field(
        default_factory=list,
        description="Negative constraints (L1): disjoint class atoms, strict axioms.",
    )
    existentials: list[Existential] = Field(
        default_factory=list,
        description="Conjunctive existential premises (L2): Skolemized by the prover.",
    )
    source_text: str = Field(default="", description="Original problem text; injected by Phase 0.")
    domain: list[str] = Field(
        default_factory=list, description="Universe sorts declared by Phase 0; membership is vacuous."
    )


class Query(BaseModel):
    """Conditions (Gamma), target (phi, may contain ``?x``), and answer type."""

    conditions: list[Morphism] = Field(default_factory=list)
    target: Morphism | None = Field(default=None)
    goals: list[Morphism] = Field(
        default_factory=list,
        description="Decomposed goals when the question target is a conjunction or "
        "disjunction (L2, D-L2-7); empty for the single-target case.",
    )
    goal_mode: GoalMode = Field(
        default="single",
        description="single | all (conjunctive) | any (disjunctive) | forall (a "
        "universal clause over ``goals``).",
    )
    variables: dict[str, str] = Field(default_factory=dict)
    answer_type: AnswerType = Field(default="yes_no")
    world_assumption: WorldAssumption = Field(
        default="open",
        description="Closed-world enables negation-as-failure for this query (L1).",
    )


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
    kind: AnswerKind = Field(
        default="unknown",
        description="Machine-readable answer shape: yes/no/unknown/contradiction/binding/instruction.",
    )
    strength: AnswerStrength = Field(default="not_proven")
    hypotheses_used: list[str] = Field(default_factory=list)
    defeasible: bool = Field(
        default=False, description="True when the proof applies a defeasible rule."
    )


RevisionTrigger = Literal["new_cited_fact", "new_hypothesis", "answer_change"]


class Revision(BaseModel):
    """A wave at which the answer changed, with the proposal that caused it.

    Monotonicity constrains the theory, not the answer: the base only grows, but
    the answer can move from unknown to bound and its hypothesis accounting can
    change. A revision is the auditable record of such a change, kept in wave
    order alongside the ``WaveRecord`` history.
    """

    wave: int
    trigger: RevisionTrigger
    previous: Answer | None = Field(default=None, description="Answer before the wave, if any.")
    current: Answer = Field(description="Answer after the wave.")
    source_ids: list[str] = Field(
        default_factory=list,
        description="Hypothesis ids accepted in the triggering wave.",
    )


ExplanationKind = Literal[
    "axiom", "assumption", "rule", "is_a", "hypothesis", "constraint", "naf",
    "case", "resolution", "skolem",
]


class ExplanationStep(BaseModel):
    """One derivation step, mapped to a real provenance edge or a hypothesis."""

    index: int
    kind: ExplanationKind
    statement: str
    premises: list[int] = Field(default_factory=list, description="Indices of premise steps.")
    rule_index: int | None = None
    rule: str | None = Field(default=None, description="Rendered rule 'IF ... => ... [kind]' for rule steps.")
    source: str | None = Field(
        default=None,
        description="Origin: 'quote' (cited from the text), 'hypothesis:<id>', or "
        "'presupposition' (a question condition, Gamma).",
    )
    quote: str | None = None
    hypothesis: str | None = None


ConflictKind = Literal["strict", "defeasible"]
ConflictStatus = Literal["resolved", "undecided"]
ConflictDefeated = Literal["supporting", "attacking", "none"]


class Conflict(BaseModel):
    """Two competing derivations of the same goal: the supporting branch vs its attack.

    ``strict`` is an inconsistent theory (both polarities hold). ``defeasible`` is a
    default conflict; ``defeated`` names the branch that loses, or ``none`` when
    specificity does not decide (the Nixon diamond).
    """

    kind: ConflictKind = "strict"
    status: ConflictStatus = "undecided"
    supporting: list[ExplanationStep] = Field(default_factory=list)
    attacking: list[ExplanationStep] = Field(default_factory=list)
    defeated: ConflictDefeated = "none"
    reason: str = Field(default="", description="Why the engine chose a side, or why it could not.")
    note: str = ""
    source_ids: list[str] = Field(
        default_factory=list,
        description="Hypothesis ids feeding the competing branches (specificity provenance).",
    )


class Explanation(BaseModel):
    """Mechanical proof trace, ordered from premises to the goal."""

    goal: str | None = None
    binding: dict[str, str] = Field(default_factory=dict)
    hypotheses_used: list[str] = Field(default_factory=list)
    steps: list[ExplanationStep] = Field(default_factory=list)
    conflict: Conflict | None = Field(default=None, description="Both branches when the goal is contradicted.")
    revisions: list[Revision] = Field(
        default_factory=list, description="Answer changes across waves, in wave order."
    )
