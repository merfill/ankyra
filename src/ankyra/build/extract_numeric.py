"""Phase 0 numeric extraction for L4 (``docs/l4_plan.md`` §11).

Two calls, in order: the model (quantities and equations) and then the question
expressed against the encoded model. The model proposes the numeric formalization
structurally — it names quantities, writes exact equations and cites verbatim spans —
and the deterministic builder (``ankyra.build.numeric``) validates it. No cue phrases,
no word lists (``docs/task.md`` §3.8): the semantics of a ratio, a percentage or a
unit multiplier is what the prompt asks the model to express as an exact equation.
"""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from ankyra.build.extract import language_spec_block
from ankyra.engine.numeric.models import NumericExpr, NumericGame
from ankyra.engine.numeric.schemas import NumericGameStructure, NumericQueryStructure
from ankyra.llm.client import extract_max_tokens, with_max_tokens
from ankyra.llm.structured import invoke_as_dict

NUMERIC_GAME_SYSTEM = """You translate a quantitative word problem into an exact numeric model
for a deterministic solver. You do NOT solve it and you do NOT write prose.

Return valid JSON matching the NumericGameStructure schema: quantities and equations.

QUANTITIES — one for every amount named or asked about:
  {"id": "snake_case_id", "unit": "optional unit", "quote": "verbatim span"}
Introduce a distinct quantity for each amount, including the quantity the question asks for.

EQUATIONS — each relation the text states, as lhs = rhs:
  {"lhs": <expr>, "rhs": <expr>, "quote": "verbatim span"}
An expression is exactly one of:
  {"op": "const", "value": "3"}            an exact number: "16", "-3", "3/4", "0.25"
  {"op": "quantity", "quantity": "<id>"}   a reference to a quantity above
  {"op": "neg", "args": [<expr>]}
  {"op": "add", "args": [<expr>, ...]}     a sum
  {"op": "sub", "args": [<expr>, <expr>]}  a difference
  {"op": "mul", "args": [<expr>, ...]}     a product
  {"op": "div", "args": [<expr>, <expr>]}  a quotient

RULES:
- Encode each stated relation as an equation; do NOT compute the result yourself.
- Percentages, ratios and fractions are exact: "25% off" -> discount = price * (25 / 100);
  "half as many" -> a = b / 2; "per" -> a rate multiplied by a count.
- Define every derived quantity with an equation; an amount stated directly is a "const".
- Introduce an unknown quantity for an amount the text does not fix, and relate it with
  equations (e.g. "one number is 4 more than the other" -> big = small + 4).
- State only what the text states. Never add an equation to make the numbers work.
- Every quantity and equation carries a minimal verbatim quote from the problem.
- Use only the operators above. A product or quotient of two unknowns is out of fragment;
  keep the relations linear, as the text supports.
"""

NUMERIC_GAME_HUMAN = """Problem:
{text}

Produce the NumericGameStructure JSON encoding of this problem."""

NUMERIC_QUERY_SYSTEM = """You express one question against an already-encoded numeric model.
You do NOT solve it.

Return valid JSON matching the NumericQueryStructure schema: target.
- "target" is the id of the game quantity the question asks for. Choose one of the game's
  quantities; never invent a new quantity or id.
- Set "tolerance" only if the question itself states an allowed error; otherwise omit it.
"""

NUMERIC_QUERY_HUMAN = """Question:
{question}
{game}

Produce the NumericQueryStructure JSON for this question against the model above."""

NUMERIC_GAME_REPAIR = """The previous encoding below was rejected by a deterministic check:
{problems}

Re-read the problem and return a corrected NumericGameStructure with the same schema.
Check the structure: every referenced quantity is declared; a "const" node carries a
value; "sub" and "div" take exactly two operands ("add"/"mul" take two or more); every
quantity and equation carries an exact verbatim quote from the problem. If the problem
states a value for a quantity that has no defining equation, add its equation.
"""

NUMERIC_QUERY_REPAIR = """The previous question encoding below was rejected by a deterministic check:
{problems}

Re-read the question and return a corrected NumericQueryStructure. "target" must be the
id of one of the model's quantities, never a new id.
"""


def _format_expr(expr: NumericExpr) -> str:
    if expr.op == "const":
        return str(expr.value)
    if expr.op == "quantity":
        return expr.quantity or "?"
    if expr.op == "neg":
        return f"(-{_format_expr(expr.args[0])})"
    if expr.op == "add":
        return "(" + " + ".join(_format_expr(arg) for arg in expr.args) + ")"
    if expr.op == "sub":
        return f"({_format_expr(expr.args[0])} - {_format_expr(expr.args[1])})"
    if expr.op == "mul":
        return "(" + " * ".join(_format_expr(arg) for arg in expr.args) + ")"
    if expr.op == "div":
        return f"({_format_expr(expr.args[0])} / {_format_expr(expr.args[1])})"
    return "?"


def format_game_for_llm(game: NumericGame) -> str:
    """Deterministic model context for the question call."""
    quantity_lines = [
        f"  {quantity.id}" + (f" [{quantity.unit}]" if quantity.unit else "")
        for quantity in game.quantities
    ]
    equation_lines = [
        f"  {_format_expr(equation.lhs)} = {_format_expr(equation.rhs)}"
        for equation in game.equations
    ]
    return (
        "\n\n--- Model ---\n"
        "Quantities:\n" + ("\n".join(quantity_lines) or "  (none)") + "\n"
        "Equations:\n" + ("\n".join(equation_lines) or "  (none)") + "\n"
        "--- end model ---\n"
    )


def _extract_numeric_game_once(llm: Any, text: str) -> NumericGameStructure:
    messages = [
        SystemMessage(content=NUMERIC_GAME_SYSTEM + language_spec_block()),
        HumanMessage(content=NUMERIC_GAME_HUMAN.format(text=text.strip())),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(llm, messages, schema=NumericGameStructure, label="extract_numeric_game")
    data.pop("source_text", None)
    data["source_text"] = text
    return NumericGameStructure.model_validate(data)


def _repair_numeric_game_once(
    llm: Any, text: str, structure: NumericGameStructure, problem: str
) -> NumericGameStructure:
    messages = [
        SystemMessage(content=NUMERIC_GAME_SYSTEM + language_spec_block()),
        HumanMessage(
            content=NUMERIC_GAME_HUMAN.format(text=text.strip())
            + "\n\n"
            + NUMERIC_GAME_REPAIR.format(
                previous=structure.model_dump_json(indent=2), problems=problem
            )
        ),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(llm, messages, schema=NumericGameStructure, label="repair_numeric_game")
    data.pop("source_text", None)
    data["source_text"] = text
    return NumericGameStructure.model_validate(data)


def extract_numeric_game(
    llm: Any,
    *,
    text: str,
    validate: Callable[[NumericGameStructure], str | None] | None = None,
    repairs: int = 0,
) -> NumericGameStructure:
    """One structural numeric encoding of a problem (no best-of-N).

    ``validate`` is a deterministic check that returns a problem hint when an encoding
    is unusable (e.g. it does not build); ``repairs`` bounds how many times the model
    may re-encode it with that hint.
    """
    structure = _extract_numeric_game_once(llm, text)
    for _ in range(max(0, repairs)):
        if validate is None:
            break
        problem = validate(structure)
        if problem is None:
            break
        structure = _repair_numeric_game_once(llm, text, structure, problem)
    return structure


def _extract_numeric_query_once(
    llm: Any, question: str, game: NumericGame, text: str
) -> NumericQueryStructure:
    messages = [
        SystemMessage(content=NUMERIC_QUERY_SYSTEM + language_spec_block()),
        HumanMessage(
            content=NUMERIC_QUERY_HUMAN.format(
                question=question.strip(),
                game=format_game_for_llm(game),
            )
        ),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(
        llm, messages, schema=NumericQueryStructure, label="extract_numeric_query"
    )
    data.pop("source_text", None)
    data["source_text"] = text
    return NumericQueryStructure.model_validate(data)


def _repair_numeric_query_once(
    llm: Any, question: str, game: NumericGame, text: str, structure: NumericQueryStructure, problem: str
) -> NumericQueryStructure:
    messages = [
        SystemMessage(content=NUMERIC_QUERY_SYSTEM + language_spec_block()),
        HumanMessage(
            content=NUMERIC_QUERY_HUMAN.format(
                question=question.strip(),
                game=format_game_for_llm(game),
            )
            + "\n\n"
            + NUMERIC_QUERY_REPAIR.format(
                previous=structure.model_dump_json(indent=2), problems=problem
            )
        ),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(
        llm, messages, schema=NumericQueryStructure, label="repair_numeric_query"
    )
    data.pop("source_text", None)
    data["source_text"] = text
    return NumericQueryStructure.model_validate(data)


def extract_numeric_query(
    llm: Any,
    *,
    question: str,
    game: NumericGame,
    source_text: str = "",
    validate: Callable[[NumericQueryStructure], str | None] | None = None,
    repairs: int = 0,
) -> NumericQueryStructure:
    """One structural encoding of a question against its numeric model.

    ``validate`` and ``repairs`` mirror :func:`extract_numeric_game`.
    """
    text = (source_text or question).strip()
    structure = _extract_numeric_query_once(llm, question, game, text)
    for _ in range(max(0, repairs)):
        if validate is None:
            break
        problem = validate(structure)
        if problem is None:
            break
        structure = _repair_numeric_query_once(llm, question, game, text, structure, problem)
    return structure
