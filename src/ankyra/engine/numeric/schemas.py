"""Phase 0 extraction schemas for the L4 numeric engine (``docs/l4_plan.md`` §10–§11).

These are the structures the LLM authors; a deterministic builder
(``ankyra.build.numeric``) validates and assembles them into the strict IR of
``ankyra.engine.numeric.models``. The schemas are deliberately lenient about spelling
(normalizing closed enum fields and ids the LLM already extracted is allowed) and
strict about structure: a construct outside the IR is not coerced into an
approximation (``docs/task.md`` §3.8, ``docs/l4_plan.md`` §3).

The engine is self-contained, so the schemas live here rather than in
``core.schemas``; this keeps the separate L4 engine in one package.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ankyra.engine.numeric.models import ExprOp

# Closed-set aliases for the term constructor (the model already chose the operator;
# normalizing its spelling is acting on structured output, not on the source).
_OP_ALIASES: dict[str, str] = {
    "const": "const", "constant": "const", "number": "const", "literal": "const",
    "quantity": "quantity", "var": "quantity", "variable": "quantity", "q": "quantity",
    "neg": "neg", "negative": "neg", "unary_minus": "neg",
    "add": "add", "sum": "add", "plus": "add", "+": "add",
    "sub": "sub", "subtract": "sub", "subtraction": "sub", "difference": "sub", "-": "sub",
    "mul": "mul", "multiply": "mul", "product": "mul", "times": "mul", "times_": "mul", "*": "mul",
    "div": "div", "divide": "div", "division": "div", "quotient": "div", "ratio": "div", "/": "div",
    "max": "max", "maximum": "max", "larger": "max", "largest": "max", "greatest": "max",
    "min": "min", "minimum": "min", "smaller": "min", "smallest": "min", "least": "min",
}


def _identifier(value: Any) -> Any:
    """A quantity id: a scalar with a leading ``?`` and surrounding space stripped."""
    if isinstance(value, dict):
        for key in ("id", "name", "value", "var", "variable", "quantity"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip().lstrip("?").strip()
        return value
    if isinstance(value, str):
        return value.strip().lstrip("?").strip()
    return value


def _parse_fraction(value: Any) -> Any:
    """An exact rational from an int, a decimal string, a ``n/d`` string or a percent."""
    if value is None:
        return None
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(str(value))
    text = str(value).strip()
    if not text:
        return None
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    text = text.replace(",", "").replace("$", "").replace(" ", "")
    try:
        fraction = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"cannot read number {value!r}") from exc
    return fraction / 100 if percent else fraction


class NumericExprSpec(BaseModel):
    """One term: a constant, a quantity reference, or an arithmetic operator."""

    op: ExprOp = Field(description="const | quantity | neg | add | sub | mul | div.")
    value: Fraction | None = Field(
        default=None, description='For op "const": the exact number (e.g. "3", "3/4", "0.25").'
    )
    quantity: str | None = Field(default=None, description='For op "quantity": the quantity id.')
    args: list["NumericExprSpec"] = Field(
        default_factory=list, description="Operands for neg/add/sub/mul/div."
    )

    @field_validator("op", mode="before")
    @classmethod
    def _coerce_op(cls, value: Any) -> Any:
        text = str(value or "").strip().lower().replace(" ", "_")
        return _OP_ALIASES.get(text, text)

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, value: Any) -> Any:
        return _parse_fraction(value)

    @field_validator("quantity", mode="before")
    @classmethod
    def _coerce_quantity(cls, value: Any) -> Any:
        if value is None:
            return None
        item = _identifier(value)
        return item or None

    @field_validator("args", mode="before")
    @classmethod
    def _coerce_args(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        return value


NumericExprSpec.model_rebuild()


class NumericQuantitySpec(BaseModel):
    """A named quantity with an optional unit and a verbatim quote."""

    id: str = Field(default="", description="Quantity id (lowercase snake_case).")
    unit: str | None = Field(default=None, description="Optional unit label, e.g. dollars or eggs.")
    quote: str = Field(default="", description="Minimal verbatim span introducing the quantity.")

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, value: Any) -> Any:
        return _identifier(value)

    @field_validator("unit", mode="before")
    @classmethod
    def _coerce_unit(cls, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("quote", mode="before")
    @classmethod
    def _coerce_quote(cls, value: Any) -> Any:
        return "" if value is None else str(value)


class NumericEquationSpec(BaseModel):
    """One equation ``lhs = rhs`` grounded by a verbatim quote."""

    lhs: NumericExprSpec = Field(description="Left-hand side expression.")
    rhs: NumericExprSpec = Field(description="Right-hand side expression.")
    quote: str = Field(default="", description="Minimal verbatim span stating the relation.")

    @field_validator("quote", mode="before")
    @classmethod
    def _coerce_quote(cls, value: Any) -> Any:
        return "" if value is None else str(value)


class NumericGameStructure(BaseModel):
    """The LLM-authored encoding of a problem: quantities and equations."""

    source_text: str = Field(default="", description="Omit in LLM JSON (injected by caller).")
    quantities: list[NumericQuantitySpec] = Field(default_factory=list)
    equations: list[NumericEquationSpec] = Field(default_factory=list)


class NumericQueryStructure(BaseModel):
    """The LLM-authored question: the quantity the question asks for."""

    source_text: str = Field(default="", description="Omit in LLM JSON (injected by caller).")
    target: str = Field(description="The id of the game quantity to determine.")
    tolerance: Fraction | None = Field(
        default=None, description="Optional comparison tolerance; the solver itself is exact."
    )

    @field_validator("target", mode="before")
    @classmethod
    def _coerce_target(cls, value: Any) -> Any:
        return _identifier(value)

    @field_validator("tolerance", mode="before")
    @classmethod
    def _coerce_tolerance(cls, value: Any) -> Any:
        return _parse_fraction(value)
