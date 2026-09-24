"""Numeric IR for the L4 exact-arithmetic engine (``docs/l4_plan.md`` §7).

A general structural model: quantities, expressions over exact rationals,
equations, and a target. It is deliberately independent from ``Theory``/``Query`` and
from the CSP IR — L4 is a separate engine (``docs/l4_plan.md`` §2), so nothing here
depends on the Horn spine, the clausal procedure, or ``engine.csp``.

The IR is data only; evaluation and elimination live in ``engine.numeric.solver``. A
construct the IR cannot express must stay ``out_of_fragment``, never be lowered onto a
weaker shape (``docs/l4_plan.md`` §3).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, Field

# The committed term language (D-L4-2, extended by D-L4-4). ``sub``/``div`` are binary;
# ``add``/``mul``/``max``/``min`` are n-ary (two or more terms). A construct outside this
# set is not representable and is refused by the builder rather than approximated.
ExprOp = Literal["const", "quantity", "neg", "add", "sub", "mul", "div", "max", "min"]


class NumericExpr(BaseModel):
    """A term: a rational constant, a quantity reference, or an arithmetic operator.

    ``value`` carries the constant for ``op == "const"``; ``quantity`` names the
    referenced quantity for ``op == "quantity"``; ``args`` are the operands of the
    operator nodes. The shape is validated by ``engine.numeric.solver`` (a stray
    ``value``/``quantity``/arity is a build error, not a silent reinterpretation).
    """

    op: ExprOp
    value: Fraction | None = Field(default=None, description="For op == 'const'.")
    quantity: str | None = Field(default=None, description="For op == 'quantity'.")
    args: list["NumericExpr"] = Field(default_factory=list)


class NumericQuantity(BaseModel):
    """A named quantity: a value to be determined, with an optional unit label.

    A quantity is *known* when an equation defines it outright and *unknown*
    otherwise; the solver assigns the known ones and eliminates the rest.
    """

    id: str
    unit: str | None = None
    quote: str | None = None


class NumericEquation(BaseModel):
    """An equation ``lhs = rhs`` grounded by a quote. Only equality is in fragment."""

    lhs: NumericExpr
    rhs: NumericExpr
    quote: str | None = None


class NumericGame(BaseModel):
    """Quantities, equations, and the source text (for quote checks)."""

    quantities: list[NumericQuantity] = Field(default_factory=list)
    equations: list[NumericEquation] = Field(default_factory=list)
    source_text: str = ""


class NumericQuery(BaseModel):
    """The target quantity to determine, and an optional comparison tolerance.

    The solver is exact; ``tolerance`` belongs to the harness's answer comparison, not
    to the engine's arithmetic.
    """

    target: str
    tolerance: Fraction | None = None


NumericExpr.model_rebuild()
