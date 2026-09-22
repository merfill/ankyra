"""Phase 0 extraction schemas — the only structures the LLM authors.

The model performs a *structural* decomposition only (slots, sets, variants,
modalities, quotes). A deterministic builder (Phase 0.3) turns these into the
finished triples/rules of ``ankyra.core.models``; the model never writes
combinatorial triples itself.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ankyra.core.models import Modality, RuleKind, normalize_modality


def _slot_item(value: Any) -> Any:
    """Coerce a set/variant element: a bare id stays, a dict collapses to its id."""
    if isinstance(value, dict):
        for key in ("id", "name"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return value


class Slot(BaseModel):
    """A role filler: one id, an AND-set, OR-variants, plus optional exclusions."""

    id: str | None = Field(default=None, description="Single object id.")
    set: list[str] = Field(default_factory=list, description="AND-multiplicity: all listed ids.")
    variants: list[str] = Field(default_factory=list, description="OR-alternatives: exactly one applies.")
    exclude: list[str] = Field(default_factory=list, description="Ids subtracted from this slot.")

    @field_validator("id", "set", "variants", "exclude", mode="before")
    @classmethod
    def _coerce_slot_values(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [_slot_item(v) for v in value]
        if isinstance(value, dict):
            item = value.get("id") or value.get("name")
            if isinstance(item, str):
                return item
            return value
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="before")
    @classmethod
    def _bare_string_to_id(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip():
            return {"id": value.strip()}
        return value


RelationKind = Literal["ascription", "possession", "action"]


class StructAtom(BaseModel):
    """One structured relation/obligation, with set/variant slots instead of triples."""

    predicate: str = Field(
        default="",
        description="Relation name (lowercase snake_case). MUST be filled here, never in "
        "'id'/'name'. Class membership uses the reserved predicate 'is_a'.",
    )
    subject: Slot = Field(default_factory=Slot)
    object: Slot = Field(default_factory=Slot)
    relation_kind: RelationKind = Field(
        default="action",
        description='Logical role of the atom: "ascription" when the subject has a '
        'property/class ("Gary is blue", "blue people", "they are not blue"; the '
        'builder emits is_a(subject, property)); "possession" when the subject has an '
        'object/part ("X has an engine") and must stay a binary predicate, never '
        'is_a; "action" for any other verb/relation.',
    )
    predication: Literal["copula", "verb"] = Field(
        default="verb",
        description="Legacy surface hint; relation_kind takes precedence. A copula "
        "without an explicit relation_kind is inferred as ascription.",
    )
    modality: Modality = Field(default="neutral", description="permit | obligation | forbidden | neutral.")
    negated: bool = Field(default=False, description="True if the connection is explicitly denied.")
    quote: str = Field(default="", description="Minimal verbatim span from the source.")

    @field_validator("subject", "object", mode="before")
    @classmethod
    def _coerce_missing_slot(cls, value: Any) -> Any:
        return {} if value is None else value

    @field_validator("relation_kind", mode="before")
    @classmethod
    def _coerce_relation_kind(cls, value: Any) -> Any:
        text = str(value or "").strip().lower()
        aliases = {"attribute": "ascription", "predicate": "ascription", "state": "ascription",
                   "has": "possession", "part": "possession", "verb": "action"}
        text = aliases.get(text, text)
        return text if text in {"ascription", "possession", "action"} else "action"

    @field_validator("predication", mode="before")
    @classmethod
    def _coerce_predication(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        return text if text in {"copula", "verb"} else "verb"

    @field_validator("modality", mode="before")
    @classmethod
    def _coerce_modality(cls, value: Any) -> Any:
        return normalize_modality(value)

    @model_validator(mode="after")
    def _infer_ascription(self) -> "StructAtom":
        """A legacy copula without an explicit relation_kind is an ascription."""
        if self.relation_kind == "action" and self.predication == "copula":
            self.relation_kind = "ascription"
        return self


class StructRule(BaseModel):
    """A real conditional: IF antecedent (AND) => consequent.

    A **disjunctive head** is expressed with ``consequents`` (an OR of atoms); when
    it is non-empty it replaces ``consequent``. A **disjunctive body** is expressed
    with ``disjunctive_antecedent`` (an OR of atoms); when it is non-empty the body
    is that disjunction and the builder splits it into one rule per atom (L2).
    """

    antecedent: list[StructAtom] = Field(default_factory=list)
    consequent: StructAtom = Field(default_factory=StructAtom)
    consequents: list[StructAtom] = Field(
        default_factory=list,
        description="Disjunctive head (OR of atoms); when non-empty it replaces "
        "'consequent'. Use the single 'consequent' for a Horn head.",
    )
    disjunctive_antecedent: list[StructAtom] = Field(
        default_factory=list,
        description="Disjunctive body (OR of atoms); when non-empty the body is that "
        "disjunction and 'antecedent' is ignored. The builder emits one rule per atom.",
    )
    kind: RuleKind = Field(default="implication", description="exception negates the consequent.")
    forall: dict[str, str] = Field(
        default_factory=dict,
        description='Sorted quantifier domain: variable name (no "?") -> universe sort. '
        'For "All X people ..." write {"forall": {"x": "person"}} and do NOT add '
        "is_a(?x,person) when another antecedent atom binds x; when the sort is the "
        "only binder (\"All people need sleep\") keep is_a(?x,person) as an antecedent "
        "atom. The builder treats the sort as the quantifier's domain, not a premise, "
        "and synthesizes the binder if it is missing. A sort restricting a PROPER "
        "subset stays an ordinary is_a condition.",
    )
    quote: str = Field(default="", description="Minimal verbatim span supporting the rule.")

    @field_validator("forall", mode="before")
    @classmethod
    def _coerce_forall(cls, value: Any) -> Any:
        """Accept {"x": "person"}, [{"var": "x", "sort": "person"}], or None."""
        if not value:
            return {}
        out: dict[str, str] = {}
        items = value.items() if isinstance(value, dict) else []
        for key, item in items:
            name = str(key).lstrip("?")
            if name and item is not None and str(item).strip():
                out[name] = str(item).strip()
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("var") or item.get("variable") or "").lstrip("?")
                sort = item.get("sort") or item.get("domain") or item.get("type")
                if name and sort is not None and str(sort).strip():
                    out[name] = str(sort).strip()
        return out

    @field_validator("antecedent", "consequents", "disjunctive_antecedent", mode="before")
    @classmethod
    def _wrap_antecedent(cls, value: Any) -> Any:
        if isinstance(value, dict):
            items = value.get("set")
            if isinstance(items, list):
                return items
            return [value]
        if isinstance(value, list):
            return value
        return []

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"implication", "exception"}:
                return text
            return "implication"
        return "implication"


class StructObject(BaseModel):
    """An object mention in the source."""

    id: str = Field(default="", description="Canonical object id.")
    label: str = Field(default="", description="Surface noun phrase (optional).")


class StructDisjoint(BaseModel):
    """A disjointness statement: no individual is both classes (L1).

    Structurally extracted ("No X is a Y", "X and Y are disjoint"). The builder
    turns it into a strict ``Constraint`` in the theory. It is never expanded into
    Horn rules (that would be a non-stratified negative cycle).
    """

    left: str = Field(default="", description="One disjoint class id.")
    right: str = Field(default="", description="The other disjoint class id.")
    quote: str = Field(default="", description="Minimal verbatim span supporting the constraint.")

    @field_validator("left", "right", mode="before")
    @classmethod
    def _coerce_class(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for key in ("object", "predicate", "id", "name"):
                item = value.get(key)
                if isinstance(item, str) and item.strip():
                    return item.strip()
            return ""
        if isinstance(value, str):
            return value.strip()
        return value


class StructDisjunction(BaseModel):
    """A disjunctive ground fact: ``A ∨ B ∨ …`` (L2).

    Structurally extracted ("Rex is a shumpus or a jompus or a grimpus"). The builder
    turns it into a conditionless clause with a disjunctive head, never into a set of
    concurrent facts (which would be an unsound OR-as-AND).
    """

    literals: list[StructAtom] = Field(default_factory=list, description="The disjunct atoms (at least two).")
    quote: str = Field(default="", description="Minimal verbatim span supporting the fact.")

    @field_validator("literals", mode="before")
    @classmethod
    def _wrap_literals(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return [value]
        return value


class StructExistential(BaseModel):
    """A conjunctive existential premise: ``∃variable (atom ∧ …)`` (L2).

    Structurally extracted ("There is an animal", "Some person has a license"). The
    builder records it on the theory; the prover Skolemizes it (docs/l2_plan.md §7.4),
    so it is never turned into a fact about a class constant.
    """

    variable: str = Field(default="?x", description="The existentially quantified variable.")
    atoms: list[StructAtom] = Field(default_factory=list, description="The conjoined atoms over it.")
    quote: str = Field(default="", description="Minimal verbatim span supporting the premise.")

    @field_validator("variable", mode="before")
    @classmethod
    def _normalize_variable(cls, value: Any) -> str:
        text = str(value or "?x").strip() or "?x"
        return text if text.startswith("?") else f"?{text}"

    @field_validator("atoms", mode="before")
    @classmethod
    def _wrap_atoms(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return [value]
        return value


class ProblemStructure(BaseModel):
    """Structural decomposition of the descriptive part of a problem."""

    source_text: str = Field(default="", description="Omit in LLM JSON (injected by caller).")
    question: str = Field(
        default="",
        description="Plain string: the verbatim interrogative part of the problem "
        "(never an object); it is never asserted as a fact.",
    )
    objects: list[StructObject] = Field(default_factory=list)
    facts: list[StructAtom] = Field(default_factory=list, description="Asserted relations (AND-sets stay one fact).")
    rules: list[StructRule] = Field(default_factory=list, description="Only real conditionals.")
    disjoint: list[StructDisjoint] = Field(
        default_factory=list,
        description="Disjointness statements: no individual is both classes (L1). "
        "A strict constraint, never a Horn rule. Leave empty when the text does not "
        "state disjointness — never infer it from class names.",
    )
    variants: list[StructAtom] = Field(default_factory=list, description="Disjunctive options; never expanded into concurrent facts.")
    disjunctions: list[StructDisjunction] = Field(
        default_factory=list,
        description="Disjunctive ground facts (L2): A or B or C. A non-Horn clause, "
        "never a set of concurrent facts. Leave empty unless the text asserts a "
        "disjunction of facts.",
    )
    existentials: list[StructExistential] = Field(
        default_factory=list,
        description="Conjunctive existential premises (L2): there is an X such that "
        "…. Recorded structurally; the prover Skolemizes them. Leave empty unless the "
        "text asserts existence over an unnamed individual.",
    )
    references: list[str] = Field(default_factory=list, description="Cross-references; not theory facts.")
    domain: list[str] = Field(
        default_factory=list,
        description="Universe sorts: the sort(s) every named individual belongs to, "
        "when the text uses them only as the generic subject of quantified rules "
        "rather than as a proper subset (e.g. a problem entirely about people). A "
        "rule condition that restricts the quantified variable to a domain sort is "
        "the quantifier's domain, not a premise; the builder drops it. List a sort "
        "here only if it covers ALL named individuals.",
    )

    @field_validator("objects", mode="before")
    @classmethod
    def _coerce_objects(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        out: list[StructObject] = []
        for item in value:
            if isinstance(item, dict):
                oid = item.get("id") or item.get("name")
                if oid:
                    out.append(StructObject(id=str(oid), label=item.get("label") or ""))
            elif isinstance(item, str) and item.strip():
                out.append(StructObject(id=item.strip()))
        return out

    @field_validator("references", mode="before")
    @classmethod
    def _coerce_references(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    out.append(text)
            elif isinstance(item, dict):
                text = str(item.get("quote") or item.get("id") or "").strip()
                if text:
                    out.append(text)
        return out

    @field_validator("domain", mode="before")
    @classmethod
    def _coerce_domain(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                text = str(item.get("id") or item.get("name") or "").strip()
                if text:
                    out.append(text)
        return out


class QuestionStructure(BaseModel):
    """Structural decomposition of the interrogative part, over the theory vocabulary.

    ``ask`` is the question's own conclusion: a variable for an open unknown, a
    constant otherwise, or ``null`` for an instruction (no target).
    """

    source_text: str = Field(default="", description="Omit in LLM JSON (injected by caller).")
    presuppositions: list[StructAtom] = Field(
        default_factory=list,
        description="Gamma: the relations the QUESTION itself asserts as given (never "
        "theory facts). Includes explicit clauses ('given that ...', 'assuming ...', "
        "'suppose ...', 'provided that ...') AND a declarative clause joined to the "
        "interrogative by a comma or semicolon whose content the question builds on "
        "('Socrates is a philosopher, is Socrates mortal?').",
    )
    rules: list[StructRule] = Field(default_factory=list, description="Only real conditionals inside the question.")
    ask: StructAtom | None = Field(default=None, description="Single target, or null.")
    ask_all: list[StructAtom] = Field(
        default_factory=list,
        description="Conjunctive goal (L2): every listed atom must hold ('is X both A "
        "and B?'). When non-empty it replaces 'ask'; the builder decomposes it into "
        "one goal per atom.",
    )
    ask_any: list[StructAtom] = Field(
        default_factory=list,
        description="Disjunctive goal (L2): some listed atom must hold ('is X A, B, or "
        "C?'). When non-empty it replaces 'ask'; the builder decomposes it into one "
        "goal per atom.",
    )
    ask_universal: list[StructAtom] = Field(
        default_factory=list,
        description="Universal clause goal (L2/T3): ∀x(l₁ ∨ … ∨ lₙ). The listed atoms "
        "are the disjuncts of ONE clause over the SAME variable; a disjunct may be "
        "negated (an implication A(x)→B(x) is ¬A(x) ∨ B(x); a negative universal "
        "'no X is Y' is ¬X(x) ∨ ¬Y(x); ¬∃x φ is ∀x ¬φ). When non-empty it replaces "
        "'ask'/'ask_all'/'ask_any'. Use 'ask_all' only for a shared-witness "
        "existential conjunction ∃x(g₁ ∧ … ∧ gₙ).",
    )
    ask_clauses: list[list[StructAtom]] = Field(
        default_factory=list,
        description="General GROUND goal formula in CNF (L2/T4): a LIST of clauses, "
        "each clause a LIST of literal atoms (a disjunction); the formula is the AND of "
        "the clauses. Use it for a compound/conditional conclusion about named things "
        "that is not a single literal and not a flat ∧/∨ (e.g. '(A∧B)→(C∧D)', "
        "'¬(A∧B)'), never for a universally quantified conclusion (that is "
        "'ask_universal'). When non-empty it replaces the other ask forms.",
    )
    variables: dict[str, str] = Field(default_factory=dict, description="Theory slot name (no '?') -> literal.")

    @field_validator("ask_universal", mode="before")
    @classmethod
    def _wrap_ask_universal(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return [value]
        return value

    @field_validator("ask_clauses", mode="before")
    @classmethod
    def _wrap_ask_clauses(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return [[value]]
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            return [value]
        return value


def llm_json_schema(model: type[BaseModel]) -> str:
    """JSON Schema for an LLM prompt (includes field descriptions)."""
    return json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2)
