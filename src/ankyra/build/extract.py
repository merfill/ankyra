"""Phase 0 LLM extraction: problem structure, then question structure.

Two calls, in order. The problem call reads the whole text and also records the
verbatim interrogative part (``question``). The question call then expresses the
question over the *canonical* theory vocabulary produced deterministically from
the first call — the ordering is what keeps the question's predicates aligned
with the theory, so it cannot be merged into a single call.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ankyra.config.settings import settings
from ankyra.core.models import Theory
from ankyra.core.schemas import ProblemStructure, QuestionStructure
from ankyra.llm.client import extract_max_tokens, with_max_tokens
from ankyra.llm.structured import invoke_as_dict

PROBLEM_SYSTEM = """You analyze a problem that contains conditions (facts, "if ... then ..." rules)
and a question, and return a STRUCTURAL decomposition for a deterministic builder.
You do NOT write the final theory, and you do NOT assert the question as a fact.

Return valid JSON matching the ProblemStructure schema: objects, facts, rules,
variants, references, question.

ATOM GRAMMAR — every fact, rule condition, rule consequent and ask is one atom:
  {"predicate": "<snake_case>", "subject": <slot>, "object": <slot>,
   "modality": "neutral|permit|obligation|forbidden", "negated": false, "quote": "..."}
The relation name ALWAYS goes in "predicate" — never in "id" or "name". A slot is a
bare id string, {"set": [...]} (AND), {"variants": [...]} (OR), or
{"set": [...], "exclude": [...]}. A relation with no stated argument omits that slot.

RESERVED CONVENTIONS:
- Class membership / subclass: predicate "is_a", subject = specific, object = general
  (e.g. {"predicate":"is_a","subject":"poodle","object":"dog"}). Never invent
  "instance", "subclass_of", "type_of", "is".
- A universal statement ("all / every / any X ...") is a rule quantified over an
  individual VARIABLE "?x", never over the class noun: "All people need sleep" →
  is_a(?x, person) => need(?x, sleep). The class noun appears only as the object of is_a.
- Denial is the SAME predicate with "negated": true; never a twin predicate.
- Modality is the "modality" field, never a prefix in the predicate name.
- Predicate ids: lowercase snake_case, no function words (a, the, and, or, of, by, to,
  for, with, from, in, on, as, when). Object ids: lowercase English head nouns; reuse
  the SAME id for the SAME concept, never mint synonyms.
- A real conditional ("if / when / provided that") is a rule; never assert its
  conclusion as a fact. An exception ("except") is kind "exception".
- "question" is a PLAIN STRING with the verbatim interrogative part — never an object.
- Extract facts/rules ONLY from the descriptive part (everything before the question).
  The question and any condition stated inside it ("given that ...", "assuming ...",
  "suppose ...") belong to the question and MUST NOT appear in facts or rules.
- Cross-references ("as defined above", "in accordance with ...") go to "references".
- Every fact, rule and ask carries ONE minimal verbatim quote. Invent nothing.

EXAMPLES (shape only; do not reuse the content):
1) "It snows. If it snows, the road is slippery."
   facts = [{"predicate":"snow","quote":"It snows."}]
   rules = [{"antecedent":[{"predicate":"snow","quote":"if it snows"}],
             "consequent":{"predicate":"slippery","object":"road","quote":"the road is slippery"},
             "quote":"if it snows, the road is slippery"}]
2) "A poodle is a dog. A dog is an animal."
   facts = [{"predicate":"is_a","subject":"poodle","object":"dog","quote":"a poodle is a dog"},
            {"predicate":"is_a","subject":"dog","object":"animal","quote":"a dog is an animal"}]
3) "Employees must submit a report and may leave early."
   facts = [{"predicate":"submit","subject":"employee","object":"report","modality":"obligation","quote":"employees must submit a report"},
            {"predicate":"leave_early","subject":"employee","modality":"permit","quote":"may leave early"}]
4) "All dogs are mammals. Rex is a dog."
   facts = [{"predicate":"is_a","subject":"rex","object":"dog","quote":"Rex is a dog"}]
   rules = [{"antecedent":[{"predicate":"is_a","subject":"?x","object":"dog","quote":"all dogs"}],
             "consequent":{"predicate":"is_a","subject":"?x","object":"mammal","quote":"are mammals"},
             "quote":"All dogs are mammals"}]
Return ONLY valid JSON, no markdown fences."""

PROBLEM_HUMAN = """Problem:
{text}

Produce the ProblemStructure JSON."""

QUESTION_SYSTEM = """You turn a question into a STRUCTURAL decomposition on top of a theory.
A deterministic expander turns your structure into conditions and a target. Return
valid JSON matching the QuestionStructure schema: facts, rules, ask, variables.

ATOM GRAMMAR — same shape as the theory: {"predicate": "...", "subject": <slot>,
"object": <slot>, "modality": "neutral|permit|obligation|forbidden", "negated": false,
"quote": "..."}. The relation name ALWAYS goes in "predicate". Class membership uses
predicate "is_a". A relation with no stated argument omits that slot.

The theory below (Objects, Predicates, Morphisms, Rules) is the vocabulary for the
FACTS and RULES of the question: reuse its predicates and object ids exactly when the
question refers to a theory relation, without renaming. A named individual the theory
does not mention may still appear as a CONSTANT object id — do not drop such a
condition; the engine reports non-theory conditions honestly. The ASK is exempt
entirely: it states the question's own conclusion in the question's own short wording
and may use predicates/ids the theory does not have. Concrete named things stay
CONSTANTS; a variable is used only for a genuine unknown the answer must supply.

How to structure the question:
1. facts = ONLY the relations the question itself ASSERTS as given. This INCLUDES
   presuppositions: clauses like "given that X is Y", "assuming ...", "suppose ..." are
   conditions of the question and MUST be kept as facts, never dropped. Do NOT copy the
   theory's own facts into the question. AND-enumerations go into one fact's
   {"set": [...]}; OR-alternatives into {"variants": [...]}.
2. ask = the single conclusion being asked, and almost every question has one.
   - A value/class/actor/quantity/list question (what / which / who / how many / what
     type) is OPEN: put a variable in the unknown slot and record it in "variables"
     (e.g. {"predicate":"is_a","subject":"x","object":"?c"}). Keep the ask even when the
     theory has no such predicate, so the engine can look for the missing rule.
   - A yes/no question: the ask is the checkable conclusion, with constants only, in
     POSITIVE form. Ask "Can Tweety fly?" as fly(tweety); never copy a negation or a
     fact-to-the-contrary from the text ("cannot fly") into the ask.
   - ONLY an imperative action request ("what should I do", "how do I proceed") has no
     single conclusion: set ask to null.
   Never turn "what type / which class / who / how many" into a null ask.
3. variables: reserve "?x" ONLY for a genuine unknown the answer must supply.
   Concrete named things are constants, not variables.
4. rules: only a real condition inside the question ("if / when"). Never copy a theory
   rule into the question.
5. Every fact, rule and ask carries ONE minimal verbatim quote.

EXAMPLE (shape only):
"Given that Socrates is a philosopher, is Socrates mortal?"
  facts = [{"predicate":"is_a","subject":"socrates","object":"philosopher","quote":"Socrates is a philosopher"}]
  ask = {"predicate":"is_a","subject":"socrates","object":"mortal","quote":"is Socrates mortal"}
  variables = {}
The "given that" clause is a question condition and MUST appear in facts.
Return ONLY valid JSON, no markdown fences."""

BUILTINS_BLOCK = """
NUMERIC THRESHOLDS (comparison predicates are available):
A threshold compares a bound value: bind it first with a relational atom, then compare
it. Operators: eq, neq, lt, lte, gt, gte; the compared value is a number. Example:
"power of at least 50" -> has_power(?x, ?p) AND gte(?p, 50). Never encode a threshold
as a new object id such as "at_least_50"."""


def builtins_block() -> str:
    return BUILTINS_BLOCK if settings.get("BUILTINS", False) else ""


QUESTION_HUMAN = """Question:
{question}
{theory}

Produce the QuestionStructure JSON for this question against the theory above."""


def format_theory_for_llm(theory: Theory) -> str:
    """Full theory context: objects, predicates, morphisms, rules."""
    predicates = sorted(
        {
            m.predicate
            for m in _iter_slots(theory)
            if m.predicate
        }
    )
    objects = sorted(obj.id for obj in theory.objects if obj.id)
    morphism_lines = "\n".join(f"  {_fmt_morphism(m)}" for m in theory.morphisms) or "  (none)"
    rule_lines = []
    for i, rule in enumerate(theory.rules, 1):
        conditions = " AND ".join(_fmt_morphism(c, with_quote=False) for c in rule.conditions)
        consequence = _fmt_morphism(rule.consequence, with_quote=False)
        quote = f' quote="{rule.quote}"' if rule.quote else ""
        rule_lines.append(f"  R{i}: IF {conditions or '?'} => {consequence}{quote}")
    rules = "\n".join(rule_lines) or "  (none)"
    return (
        f"\n\n--- Theory ---\n"
        f"Objects: {', '.join(objects) or '(none)'}\n"
        f"Predicates: {', '.join(predicates) or '(none)'}\n\n"
        f"Morphisms:\n{morphism_lines}\n\n"
        f"Rules:\n{rules}\n"
        f"--- end theory ---\n"
    )


def _iter_slots(theory: Theory):
    yield from theory.morphisms
    for rule in theory.rules:
        yield from rule.conditions
        yield rule.consequence


def _fmt_morphism(morphism, *, with_quote: bool = True) -> str:
    neg = "NOT " if morphism.negated else ""
    modality = "" if morphism.modality == "neutral" else f"{morphism.modality}:"
    quote = f' quote="{morphism.quote}"' if with_quote and morphism.quote else ""
    subject = morphism.subject or ""
    obj = morphism.object or ""
    return f"{neg}{modality}{morphism.predicate}({subject}, {obj}){quote}"


def extract_problem_structure(llm: Any, *, text: str) -> ProblemStructure:
    """One call: split the text and decompose the descriptive part."""
    messages = [
        SystemMessage(content=PROBLEM_SYSTEM + builtins_block()),
        HumanMessage(content=PROBLEM_HUMAN.format(text=text.strip())),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(llm, messages, schema=ProblemStructure, label="extract_problem")
    data.pop("source_text", None)
    data["source_text"] = text
    return ProblemStructure.model_validate(data)


def extract_question_structure(
    llm: Any,
    *,
    question: str,
    theory: Theory,
    source_text: str = "",
) -> QuestionStructure:
    """One call: express the question over the theory's canonical vocabulary."""
    text = (source_text or question).strip()
    messages = [
        SystemMessage(content=QUESTION_SYSTEM),
        HumanMessage(
            content=QUESTION_HUMAN.format(
                question=question.strip(),
                theory=format_theory_for_llm(theory),
            )
        ),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(llm, messages, schema=QuestionStructure, label="extract_question")
    data.pop("source_text", None)
    data["source_text"] = text
    return QuestionStructure.model_validate(data)
