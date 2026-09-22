"""Phase 0 extraction schemas for the L3 CSP engine (``docs/l3_plan.md`` §10–§11).

These are the structures the LLM authors; a deterministic builder
(``ankyra.build.csp``) validates and assembles them into the strict IR of
``ankyra.engine.csp.models``. The schemas are deliberately lenient about spelling
(normalizing closed enum fields and ids the LLM already extracted is allowed) and
strict about structure: a construct outside the IR is not coerced into an
approximation (``docs/task.md`` §3.8, ``docs/l3_plan.md`` §3).

The engine is self-contained, so the schemas live here rather than in
``core.schemas`` (which owns the Horn/L2 structures); this keeps the separate L3
engine in one package.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from ankyra.engine.csp.models import (
    Comparison,
    ConstraintKind,
    CountMode,
    QuestionKind,
    Topology,
)

_TOPOLOGY_ALIASES: dict[str, str] = {
    "linear": "linear", "line": "linear", "row": "linear", "ordered": "linear",
    "order": "linear", "sequence": "linear", "list": "linear", "rank": "linear",
    "circular": "circular", "circle": "circular", "round": "circular",
    "cyclic": "circular", "ring": "circular", "around": "circular",
    "set": "set", "none": "set", "unordered": "set", "group": "set", "groups": "set",
}

_KIND_ALIASES: dict[str, str] = {
    "all_different": "all_different", "all-different": "all_different",
    "distinct": "all_different", "permutation": "all_different",
    "eq": "eq", "equals": "eq", "equal": "eq", "is": "eq",
    "neq": "neq", "not_equal": "neq", "unequal": "neq", "not_equals": "neq",
    "order": "order", "before": "order", "precedes": "order", "earlier": "order",
    "adjacent": "adjacent", "next_to": "adjacent", "next": "adjacent",
    "neighbours": "adjacent", "neighbors": "adjacent", "adjacent_to": "adjacent",
    "not_adjacent": "not_adjacent", "not_next_to": "not_adjacent",
    "same_group": "same_group", "same": "same_group", "together": "same_group",
    "different_group": "different_group", "different": "different_group",
    "apart": "different_group", "separate": "different_group",
    "count": "count", "cardinality": "count", "number": "count",
    "count_compare": "count_compare", "count-compare": "count_compare",
    "compare": "count_compare",
    "conditional": "conditional", "if_then": "conditional", "implies": "conditional",
    "all": "all", "and": "all", "conjunction": "all",
    "any": "any", "or": "any", "disjunction": "any",
    "not": "not", "negation": "not", "negate": "not",
}

_COMPARISON_ALIASES: dict[str, str] = {
    "gt": "gt", "greater": "gt", "more": "gt", "more_than": "gt",
    "greater_than": "gt", ">": "gt",
    "lt": "lt", "less": "lt", "fewer": "lt", "less_than": "lt",
    "fewer_than": "lt", "<": "lt",
    "eq": "eq", "equal": "eq", "same": "eq", "=": "eq",
}

_COUNT_MODE_ALIASES: dict[str, str] = {
    "exactly": "exactly", "exact": "exactly", "equal": "exactly", "=": "exactly",
    "at_least": "at_least", "atleast": "at_least", "at least": "at_least",
    "minimum": "at_least", "min": "at_least", ">=": "at_least",
    "at_most": "at_most", "atmost": "at_most", "at most": "at_most",
    "maximum": "at_most", "max": "at_most", "<=": "at_most",
}

_QUESTION_KIND_ALIASES: dict[str, str] = {
    "not_violate": "not_violate", "not-violate": "not_violate",
    "violates": "not_violate", "valid": "not_violate", "arrangement": "not_violate",
    "must": "must", "must_be_true": "must", "entailed": "must",
    "could": "could", "could_be_true": "could", "possible": "could",
    "must_be_false": "must_be_false", "must-be-false": "must_be_false",
    "cannot_be_true": "must_be_false", "cannot-be-true": "must_be_false",
    "impossible": "must_be_false", "false": "must_be_false",
    "complete_list": "complete_list", "complete-list": "complete_list",
    "list": "complete_list", "enumerate": "complete_list",
}


def _scalar(value: Any) -> Any:
    """A bare id or a ``{"id"/"name"/"value": ...}`` object collapses to its string."""
    if isinstance(value, dict):
        for key in ("id", "name", "value", "var", "variable"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return value
    if isinstance(value, str):
        return value.strip()
    return value


def _identifier(value: Any) -> Any:
    """Normalize an id: a scalar, with a leading '?' and surrounding space stripped."""
    item = _scalar(value)
    if isinstance(item, str):
        return item.lstrip("?").strip()
    return item


def _string_list(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_scalar(item) for item in value]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return value


def _identifier_list(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_identifier(item) for item in value]
    if isinstance(value, str):
        return [_identifier(value)]
    return value


class CspDomainSpec(BaseModel):
    """A candidate domain: a finite set of values and a declared topology."""

    id: str = Field(default="", description="Domain id (lowercase snake_case).")
    values: list[str] = Field(default_factory=list, description="The finite set of values.")
    topology: Topology = Field(
        default="set",
        description='Declared topology: "set" (unordered groups), "linear" (a row/ranking) '
        'or "circular" (around a table). It is what makes order/adjacent meaningful; '
        "declare it from the text, never guess it from variable names.",
    )

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, value: Any) -> Any:
        return _identifier(value)

    @field_validator("values", mode="before")
    @classmethod
    def _coerce_values(cls, value: Any) -> Any:
        return _string_list(value)

    @field_validator("topology", mode="before")
    @classmethod
    def _coerce_topology(cls, value: Any) -> Any:
        text = str(value or "").strip().lower()
        if not text:
            return "set"
        if text not in _TOPOLOGY_ALIASES:
            raise ValueError(f"unknown topology {value!r} (expected set/linear/circular)")
        return _TOPOLOGY_ALIASES[text]


class CspVariableSpec(BaseModel):
    """A variable ranging over one declared domain."""

    id: str = Field(default="", description="Variable id (an entity or a position).")
    domain: str = Field(default="", description="The id of the domain it ranges over.")

    @field_validator("id", "domain", mode="before")
    @classmethod
    def _coerce_id(cls, value: Any) -> Any:
        return _identifier(value)


class CspConstraintSpec(BaseModel):
    """One constraint relation, with a verbatim quote."""

    kind: ConstraintKind = Field(description="Constraint kind.")
    variables: list[str] = Field(default_factory=list, description="The variable ids in scope.")
    values: list[str] = Field(default_factory=list, description="Value(s) for eq/neq/count.")
    immediate: bool = Field(default=False, description='True for "immediately".')
    count: int | None = Field(default=None, description="The N for a count constraint.")
    count_mode: CountMode = Field(default="exactly", description="exactly | at_least | at_most.")
    comparison: "Comparison | None" = Field(
        default=None, description="For count_compare: gt | lt | eq (count(values[0]) vs count(values[1]))."
    )
    condition: "CspConstraintSpec | None" = Field(default=None, description="Conditional antecedent.")
    consequence: "CspConstraintSpec | None" = Field(default=None, description="Conditional consequent.")
    constraints: list["CspConstraintSpec"] = Field(
        default_factory=list,
        description='Sub-constraints: all (AND), any (OR, "either … or …"), not (a single element). '
        "Use them to compose relations that are not a flat conjunction.",
    )
    quote: str = Field(default="", description="Minimal verbatim span supporting the constraint.")

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, value: Any) -> Any:
        text = str(value or "").strip().lower().replace(" ", "_")
        return _KIND_ALIASES.get(text, text)

    @field_validator("variables", mode="before")
    @classmethod
    def _coerce_variables(cls, value: Any) -> Any:
        return _identifier_list(value)

    @field_validator("values", mode="before")
    @classmethod
    def _coerce_values(cls, value: Any) -> Any:
        return _string_list(value)

    @field_validator("immediate", mode="before")
    @classmethod
    def _coerce_immediate(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "immediately", "immediate", "1"}
        return value

    @field_validator("count", mode="before")
    @classmethod
    def _coerce_count(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
            return int(value.strip())
        return value

    @field_validator("count_mode", mode="before")
    @classmethod
    def _coerce_count_mode(cls, value: Any) -> Any:
        text = str(value or "").strip().lower()
        if not text:
            return "exactly"
        if text not in _COUNT_MODE_ALIASES:
            raise ValueError(f"unknown count_mode {value!r} (expected exactly/at_least/at_most)")
        return _COUNT_MODE_ALIASES[text]

    @field_validator("comparison", mode="before")
    @classmethod
    def _coerce_comparison(cls, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip().lower().replace(" ", "_")
        if not text:
            return None
        if text not in _COMPARISON_ALIASES:
            raise ValueError(f"unknown comparison {value!r} (expected gt/lt/eq)")
        return _COMPARISON_ALIASES[text]

    @field_validator("constraints", mode="before")
    @classmethod
    def _wrap_constraints(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return [value]
        return value

    @field_validator("quote", mode="before")
    @classmethod
    def _coerce_quote(cls, value: Any) -> Any:
        return "" if value is None else str(value)


CspConstraintSpec.model_rebuild()


class CspGameStructure(BaseModel):
    """The LLM-authored encoding of a game: domains, variables, constraints."""

    source_text: str = Field(default="", description="Omit in LLM JSON (injected by caller).")
    domains: list[CspDomainSpec] = Field(default_factory=list)
    variables: list[CspVariableSpec] = Field(default_factory=list)
    constraints: list[CspConstraintSpec] = Field(default_factory=list)


class CspOptionSpec(BaseModel):
    """A candidate answer: a conjunction of constraints, or a value list."""

    constraints: list[CspConstraintSpec] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list, description="For complete_list options.")
    quote: str = Field(default="", description="Minimal verbatim span supporting the option.")

    @field_validator("values", mode="before")
    @classmethod
    def _coerce_values(cls, value: Any) -> Any:
        return _string_list(value)


class CspQuestionStructure(BaseModel):
    """The LLM-authored question: a kind, five options, and a complete-list target."""

    source_text: str = Field(default="", description="Omit in LLM JSON (injected by caller).")
    kind: QuestionKind = Field(
        description='Question semantics: "not_violate" (which arrangement is valid), '
        '"must" (true in every model), "could" (true in some model), '
        '"must_be_false" (true in no model; "cannot be true"), '
        '"complete_list" (a complete and accurate list of values).',
    )
    options: list[CspOptionSpec] = Field(default_factory=list, description="The candidate answers.")
    target: str | None = Field(
        default=None,
        description="For complete_list: the id of the variable whose possible values are listed.",
    )
    assumptions: list[CspConstraintSpec] = Field(
        default_factory=list,
        description='Gamma: extra constraints the question asserts ("if …" questions). '
        "They are added to the game before the options are checked; leave empty when "
        "the question carries no hypothesis.",
    )

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, value: Any) -> Any:
        text = str(value or "").strip().lower().replace(" ", "_")
        return _QUESTION_KIND_ALIASES.get(text, text)

    @field_validator("target", mode="before")
    @classmethod
    def _coerce_target(cls, value: Any) -> Any:
        if value is None:
            return None
        item = _identifier(value)
        return item or None
