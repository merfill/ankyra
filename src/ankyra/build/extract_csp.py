"""Phase 0 CSP extraction for L3 (``docs/l3_plan.md`` §11).

Two calls, in order: the game (domains, variables, constraints) and then the
question expressed against the encoded game. The model proposes the finite-domain
encoding structurally — it declares domains, topologies and constraint relations
with verbatim quotes — and the deterministic builder (``ankyra.build.csp``)
validates it. No cue phrases, no word lists, no fixed positional ontology
(``docs/task.md`` §3.8): the semantics of "next to" or "around a table" is what the
prompt asks the model to express as a topology and a relation.
"""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from ankyra.build.extract import language_spec_block
from ankyra.engine.csp.models import CspConstraint, CspGame
from ankyra.engine.csp.schemas import CspGameStructure, CspQuestionStructure
from ankyra.llm.client import extract_max_tokens, with_max_tokens
from ankyra.llm.structured import invoke_as_dict

CSP_GAME_SYSTEM = """You encode an analytical-reasoning game into a finite-domain constraint
model for a deterministic solver. You do NOT solve it and you do NOT write prose.

Return valid JSON matching the CspGameStructure schema: domains, variables, constraints.

DOMAINS — each finite set of values, with its declared TOPOLOGY:
  {"id": "...", "values": ["...", ...], "topology": "set|linear|circular"}
- "set": unordered values (groups, categories).
- "linear": an ordered row / ranking / sequence of positions.
- "circular": positions around a table or in a cycle.
Declare the topology from the text ("in a row" -> linear, "around a table" -> circular);
never guess it from names. Values are the positions/slots (e.g. "1".."6") or the groups.

PACKED DOMAINS — only when one slot combines two attributes (e.g. a theater slot is a
screen AND a time). Declare the factor domains too, then the packed domain:
  {"id": "slot", "values": ["screen1_7pm", ...], "topology": "set",
   "factors": ["screen", "time"],
   "value_factors": {"screen1_7pm": ["screen1", "7pm"], ...}}
Decompose EVERY packed value into its factor values, in the order of "factors". Keep a
plain flat domain when no position combines attributes.

VARIABLES — each entity or slot that takes a value:
  {"id": "...", "domain": "<a domain id>"}
Encode one consistent direction: either one variable per entity ranging over the
position domain (so an arrangement is an assignment of each entity to a position), or
one variable per position ranging over the entity domain. Pick one and keep it.

CONSTRAINTS — use exactly these kinds, each with ONE verbatim quote from the text:
  {"kind": "all_different", "variables": [...], "quote": "..."}
  {"kind": "eq"|"neq", "variables": [v], "values": [value]}   # v equals / differs from a value
  {"kind": "eq"|"neq", "variables": [a, b]}                    # a equals / differs from b
  {"kind": "order", "variables": [a, b], "immediate": true|false}  # a before b ("immediately")
  {"kind": "adjacent"|"not_adjacent", "variables": [a, b]}      # next to / not next to
  {"kind": "same_group"|"different_group", "variables": [a, b]}
  {"kind": "count", "variables": [...], "values": [group...], "count": N, "count_mode": "exactly|at_least|at_most"}
    # "values" is the group as a SET: count the variables whose value is in it (one value
    # is the common case; "Venezuela, Yemen or Zambia" is a set of three).
  {"kind": "conditional", "condition": <constraint>, "consequence": <constraint>}  # if ... then ...
- A relation about ONE component of a packed value carries "factor": "<factor id>":
  "the sci-fi film is not on screen 3" -> {"kind":"neq","variables":["scifi"],
  "values":["screen3"],"factor":"screen"}; "the western is before the horror" ->
  {"kind":"order","variables":["western","horror"],"factor":"time"}. Omit "factor" for
  relations over the whole value.

RULES:
- There must be an all_different constraint whenever the entities and the positions form
  a bijection (each item fills one slot and each slot holds one item).
- Encode positional/relational meaning with the kinds above. Do NOT invent predicate
  names such as "next_to" or "across_from"; express them as adjacent/order/neq.
- State only what the text states. Never add a constraint to make the puzzle solvable.
- Every constraint carries a minimal verbatim quote from the game context.
"""

CSP_GAME_HUMAN = """Game context:
{text}

Produce the CspGameStructure JSON encoding of this game."""

CSP_QUESTION_SYSTEM = """You express one multiple-choice question against an already-encoded
finite-domain game. You do NOT solve it; you encode the question and its options.

Return valid JSON matching the CspQuestionStructure schema: kind, options, target.

KIND — read the question's own wording (never a tag):
- "not_violate": "which arrangement does NOT violate the conditions" — every option is
  a COMPLETE arrangement.
- "must": "which one MUST be true" (true in every model of the constraints).
- "could": "which one COULD be true" (true in some model).
- "must_be_false": "which one CANNOT be true" / "must be false".
- "complete_list": "which is the complete and accurate list of ...". Set "target" to the
  thing that is listed and "target_kind" to how it is read:
  - "variable": the list is the possible values of one game variable (e.g. "the positions
    X could occupy"); the options' "values" are those values.
  - "value": the list is the game entities/variables assigned to one DECLARED value (e.g.
    "the books on the bottom shelf", "the bands that could perform in slot one", "the
    students who must be assigned"); set "target" to that declared value and put the
    candidate entity lists in the options' "values".
  Set "list_mode" to "could" (an item is listed if some arrangement includes it) or
  "must" (only items present in every arrangement); default "could".
If the question begins with "If ...", put that hypothetical premise in "assumptions"
(it is added to the game before the options are checked). Use the SAME domain values
as the game (e.g. the position labels the game declared).

The question text below includes its five answer options (A–E). Encode EXACTLY those
five options, in the given order (option A is index 0); never invent, merge or reorder
them. Encode each option's FULL logical claim; never reduce an option to a single
entity or a single field.

CRITICAL — a complete arrangement/sequence option lists an order for ALL entities
(e.g. "Salammbo, Reciprocity, Trapezoid, Vancouver, Wisteria" or "1: wool; 2: gauze;
..."). Encode it with ONE `eq` for EVERY variable of the game (all of them, using the
game's own domain values) — a single `eq` is wrong. If two options would encode
identically, you have mis-read one of them: re-read the option text.

OPTION SHAPES:
- full arrangement/sequence -> one `eq` per game variable (see example).
- "X is the Nth" -> {kind "eq", variables [X], values [value]}.
- "X is earlier than Y" -> {kind "order", variables [X, Y]}.
- "X is immediately before/after Y" -> {kind "order", variables [X, Y], immediate true}.
- "X is next to Y" -> {kind "adjacent", variables [X, Y]}.
- "X is not next to Y" -> {kind "not_adjacent", variables [X, Y]}.
- "X and Y are in the same room/group" -> {kind "same_group", variables [X, Y]}.
- "X and Y are in different rooms/groups" -> {kind "different_group", variables [X, Y]}.
- a conjunction in one option ("X and Y are both ...") -> {kind "all", constraints [...]}.
- "either ... or ..." inside one option -> {kind "any", constraints [...]}.
- "complete_list": each option carries "values" (a list), not constraints.
Encode every option faithfully; do not decide which one is correct.

EXAMPLES.
- Option "Wisteria is earlier than Reciprocity." ->
  {"constraints": [{"kind": "order", "variables": ["Wisteria", "Reciprocity"]}]}
- Option "Salammbo, Reciprocity, Trapezoid, Vancouver, Wisteria" (a complete order,
  game variables R, S, T, V, W with positions "1".."5") ->
  {"constraints": [{"kind":"eq","variables":["Salammbo"],"values":["1"]},
                   {"kind":"eq","variables":["Reciprocity"],"values":["2"]},
                   {"kind":"eq","variables":["Trapezoid"],"values":["3"]},
                   {"kind":"eq","variables":["Vancouver"],"values":["4"]},
                   {"kind":"eq","variables":["Wisteria"],"values":["5"]}]}
"""

CSP_QUESTION_HUMAN = """Question:
{question}
{game}

Produce the CspQuestionStructure JSON for this question against the game above."""

CSP_QUESTION_REPAIR = """The previous encoding below was rejected by a deterministic check:
{problems}

Re-read the question and EACH of its five options, then return a corrected
CspQuestionStructure. Keep the five options in order. A complete arrangement option
must encode one eq for EVERY game variable. Fix the problem above; do not change the
game.
"""


def _format_constraint(constraint: CspConstraint) -> str:
    parts = [constraint.kind]
    if constraint.variables:
        parts.append(f"vars={constraint.variables}")
    if constraint.values:
        parts.append(f"values={constraint.values}")
    if constraint.immediate:
        parts.append("immediate")
    if constraint.count is not None:
        parts.append(f"count={constraint.count_mode}:{constraint.count}")
    if constraint.condition is not None or constraint.consequence is not None:
        condition = _format_constraint(constraint.condition) if constraint.condition else "?"
        consequence = _format_constraint(constraint.consequence) if constraint.consequence else "?"
        parts.append(f"if({condition})->then({consequence})")
    return " ".join(parts)


def format_game_for_llm(game: CspGame) -> str:
    """Deterministic game context for the question call."""
    domain_lines = [
        f"  {domain.id} [{domain.topology}]: {', '.join(domain.values)}"
        for domain in game.domains
    ]
    variable_lines = [f"  {variable.id}: {variable.domain}" for variable in game.variables]
    constraint_lines = [f"  {_format_constraint(c)}" for c in game.constraints]
    return (
        "\n\n--- Game ---\n"
        f"Domains:\n" + ("\n".join(domain_lines) or "  (none)") + "\n"
        f"Variables:\n" + ("\n".join(variable_lines) or "  (none)") + "\n"
        f"Constraints:\n" + ("\n".join(constraint_lines) or "  (none)") + "\n"
        "--- end game ---\n"
    )


def extract_csp_game(llm: Any, *, text: str) -> CspGameStructure:
    """One structural CSP encoding of a game context (no best-of-N)."""
    messages = [
        SystemMessage(content=CSP_GAME_SYSTEM + language_spec_block()),
        HumanMessage(content=CSP_GAME_HUMAN.format(text=text.strip())),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(llm, messages, schema=CspGameStructure, label="extract_csp_game")
    data.pop("source_text", None)
    data["source_text"] = text
    return CspGameStructure.model_validate(data)


def _extract_csp_question_once(
    llm: Any, question: str, game: CspGame, text: str
) -> CspQuestionStructure:
    messages = [
        SystemMessage(content=CSP_QUESTION_SYSTEM + language_spec_block()),
        HumanMessage(
            content=CSP_QUESTION_HUMAN.format(
                question=question.strip(),
                game=format_game_for_llm(game),
            )
        ),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(
        llm, messages, schema=CspQuestionStructure, label="extract_csp_question"
    )
    data.pop("source_text", None)
    data["source_text"] = text
    return CspQuestionStructure.model_validate(data)


def _repair_csp_question_once(
    llm: Any,
    question: str,
    game: CspGame,
    text: str,
    structure: CspQuestionStructure,
    problem: str,
) -> CspQuestionStructure:
    messages = [
        SystemMessage(content=CSP_QUESTION_SYSTEM),
        HumanMessage(
            content=CSP_QUESTION_HUMAN.format(
                question=question.strip(),
                game=format_game_for_llm(game),
            )
            + "\n\n"
            + CSP_QUESTION_REPAIR.format(
                previous=structure.model_dump_json(indent=2), problems=problem
            )
        ),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(
        llm, messages, schema=CspQuestionStructure, label="repair_csp_question"
    )
    data.pop("source_text", None)
    data["source_text"] = text
    return CspQuestionStructure.model_validate(data)


def extract_csp_question(
    llm: Any,
    *,
    question: str,
    game: CspGame,
    source_text: str = "",
    validate: Callable[[CspQuestionStructure], str | None] | None = None,
    repairs: int = 0,
) -> CspQuestionStructure:
    """One structural encoding of a multiple-choice question against its game.

    ``validate`` is a deterministic game-aware check that returns a problem hint when
    an encoding is unusable (e.g. it makes several options satisfiable); ``repairs``
    bounds how many times the model may re-encode it. The hint never reveals the
    correct option — it only describes the structural defect.
    """
    text = (source_text or question).strip()
    structure = _extract_csp_question_once(llm, question, game, text)
    for _ in range(max(0, repairs)):
        if validate is None:
            break
        problem = validate(structure)
        if problem is None:
            break
        structure = _repair_csp_question_once(llm, question, game, text, structure, problem)
    return structure
