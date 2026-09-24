"""The L4 exact-arithmetic numeric engine (separate from Horn/L2/CSP; ``docs/l4_plan.md``)."""

from ankyra.engine.numeric.answer import build_numeric_answer, build_numeric_explanation
from ankyra.engine.numeric.decide import decide
from ankyra.engine.numeric.models import (
    ExprOp,
    NumericEquation,
    NumericExpr,
    NumericGame,
    NumericQuery,
    NumericQuantity,
)
from ankyra.engine.numeric.solver import (
    DEFAULT_BUDGET,
    NumericDecision,
    NumericError,
    as_linear,
    eval_expr,
    solve,
    validate_expression,
)

__all__ = [
    "DEFAULT_BUDGET",
    "ExprOp",
    "NumericDecision",
    "NumericEquation",
    "NumericError",
    "NumericExpr",
    "NumericGame",
    "NumericQuery",
    "NumericQuantity",
    "as_linear",
    "build_numeric_answer",
    "build_numeric_explanation",
    "decide",
    "eval_expr",
    "solve",
    "validate_expression",
]
