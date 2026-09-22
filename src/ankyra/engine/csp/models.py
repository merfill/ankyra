"""CSP IR for the L3 finite-domain engine (``docs/l3_plan.md`` §7).

A general structural model: finite domains with a **declared** topology, variables,
and constraint relations. It is deliberately independent from ``Theory``/``Query`` —
L3 is a separate engine (``docs/l3_plan.md`` D-L3-4), so nothing here depends on the
Horn spine or the clausal procedure.

The IR is data only; evaluation lives in ``engine.csp.solver``. A construct the IR
cannot express must stay ``out_of_fragment``, never be lowered onto a weaker shape
(``docs/l3_plan.md`` §3).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# A declared topology makes an ``order``/``adjacent`` relation meaningful; it is part
# of the extracted structure and is never guessed from the wording (D-L3-2).
Topology = Literal["set", "linear", "circular"]
ConstraintKind = Literal[
    "all_different",
    "eq",
    "neq",
    "order",
    "adjacent",
    "not_adjacent",
    "same_group",
    "different_group",
    "count",
    "count_compare",
    "conditional",
    "all",
    "any",
    "not",
]
CountMode = Literal["exactly", "at_least", "at_most"]
Comparison = Literal["gt", "lt", "eq"]
# A complete-and-accurate list enumerates either a variable's possible values or, for a
# value target, the variables assigned to that declared value; the mode unions the
# per-model item sets ("could") or intersects them ("must").
TargetKind = Literal["variable", "value"]
ListMode = Literal["could", "must"]
# The model-theoretic question semantics in the committed fragment (D-L3-3):
# not-violate, must, could, cannot-be-true/must-be-false, complete-and-accurate-list.
QuestionKind = Literal["not_violate", "must", "could", "must_be_false", "complete_list"]


class CspDomain(BaseModel):
    """A finite set of values plus the topology under which they are ordered.

    A domain may be a **product** of atomic factor domains: ``factors`` names them and
    ``value_factors`` decomposes each value into factor values (aligned to ``factors``),
    so a constraint can be evaluated on one factor (D-L3-11).
    """

    id: str
    values: list[str] = Field(default_factory=list)
    topology: Topology = "set"
    factors: list[str] = Field(
        default_factory=list,
        description="Atomic factor-domain ids this domain is the product of; empty = atomic.",
    )
    value_factors: dict[str, list[str]] = Field(
        default_factory=dict,
        description="For a product domain: value -> its factor values, aligned to `factors`.",
    )


class CspVariable(BaseModel):
    """A variable ranging over one declared domain."""

    id: str
    domain: str
    quote: str | None = None


class CspConstraint(BaseModel):
    """A relation over variables/values, each with a quote.

    ``variables``/``values`` are interpreted per ``kind``; ``condition``/``consequence``
    are the two halves of a ``conditional`` (``if condition then consequence``).
    """

    kind: ConstraintKind
    variables: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    immediate: bool = Field(default=False, description="For order/adjacent: 'immediately'.")
    factor: str | None = Field(
        default=None,
        description="Project each variable's value onto this declared factor before evaluating "
        "(e.g. compare 'screen' or 'time' of a packed slot value); D-L3-11.",
    )
    count: int | None = Field(default=None, description="For count: the N.")
    count_mode: CountMode = Field(default="exactly", description="For count: exactly/at_least/at_most.")
    comparison: Comparison | None = Field(
        default=None,
        description="For count_compare: compare count(values[0]) gt/lt/eq count(values[1]).",
    )
    condition: "CspConstraint | None" = Field(default=None, description="Conditional antecedent.")
    consequence: "CspConstraint | None" = Field(default=None, description="Conditional consequent.")
    constraints: list["CspConstraint"] = Field(
        default_factory=list,
        description="Sub-constraints for all (AND) / any (OR) / not (a single element); empty otherwise.",
    )
    quote: str | None = None


class CspGame(BaseModel):
    """Domains, variables, constraints, and the source text (for quote checks)."""

    domains: list[CspDomain] = Field(default_factory=list)
    variables: list[CspVariable] = Field(default_factory=list)
    constraints: list[CspConstraint] = Field(default_factory=list)
    source_text: str = ""


class CspOption(BaseModel):
    """A candidate answer: a conjunction of constraints, or a value list.

    A ``complete_list`` option carries ``values`` (the proposed complete list); every
    other question kind carries ``constraints`` (an assignment is a conjunction of
    ``eq``; a pair/ordering is the relevant relation).
    """

    constraints: list[CspConstraint] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    quote: str | None = None


class CspQuestion(BaseModel):
    """A multiple-choice question: a kind, five options, a target, and assumptions.

    ``assumptions`` is the question's own hypothetical premise (Gamma): extra
    constraints added to the game before the options are checked, which is what an
    "if …" question asserts. It is a question-local restriction, never a game fact.
    """

    kind: QuestionKind
    options: list[CspOption] = Field(default_factory=list)
    target: str | None = Field(default=None, description="Variable or value for complete_list.")
    target_kind: TargetKind = Field(
        default="variable",
        description="For complete_list: whether target names a variable (list its possible "
        "values) or a declared value (list the variables assigned to it).",
    )
    list_mode: ListMode = Field(
        default="could",
        description='For complete_list: "could" (union the per-model item sets) or "must" '
        "(intersection, the items present in every model).",
    )
    assumptions: list[CspConstraint] = Field(
        default_factory=list,
        description="Gamma: extra constraints added to the game before deciding.",
    )
    quote: str | None = None


class CspQuery(BaseModel):
    """A CSP question posed against a game; the question kind is harness-declared."""

    question: CspQuestion


CspConstraint.model_rebuild()
