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

from ankyra.build.pipeline import build_theory
from ankyra.build.symbolic import GapClass, classify_gap, quality_key, symbolic_check
from ankyra.build.unroll import unroll_query_structure
from ankyra.config.settings import get_setting, settings
from ankyra.core.models import Theory
from ankyra.core.schemas import ProblemStructure, QuestionStructure
from ankyra.llm.client import extract_max_tokens, with_max_tokens
from ankyra.llm.structured import invoke_as_dict

PROBLEM_SYSTEM = """You analyze a problem that contains conditions (facts, "if ... then ..." rules)
and a question, and return a STRUCTURAL decomposition for a deterministic builder.
You do NOT write the final theory, and you do NOT assert the question as a fact.

Return valid JSON matching the ProblemStructure schema: objects, facts, rules,
disjoint, variants, references, question. A rule may carry "forall" (variable -> sort),
the quantifier's domain, so it is not written as an is_a body condition.

ATOM GRAMMAR — every fact, rule condition, rule consequent and ask is one atom:
  {"predicate": "<snake_case>", "subject": <slot>, "object": <slot>,
   "relation_kind": "ascription|possession|action",
   "modality": "neutral|permit|obligation|forbidden", "negated": false, "quote": "..."}
The relation name ALWAYS goes in "predicate" — never in "id" or "name". A slot is a
bare id string, {"set": [...]} (AND), {"variants": [...]} (OR), or
{"set": [...], "exclude": [...]}. A relation with no stated argument omits that slot.

RESERVED CONVENTIONS:
- Class membership / subclass: predicate "is_a", subject = specific, object = general
  (e.g. {"predicate":"is_a","subject":"poodle","object":"dog"}). Never invent
  "instance", "subclass_of", "type_of", "is".
- A universal statement ("all / every / any X ...") is a rule quantified over an
  individual VARIABLE "?x", never over the class noun. The same holds for a BARE
  PLURAL generic ("Plungers suck.", "Birds fly.", "Vampires suck"): it is the rule
  is_a(?x, <noun>) => <predicate>(?x) over "?x", never a fact whose subject is the
  class constant. When the generic noun is the quantifier's UNIVERSE SORT, record it
  in the rule's "forall": {"x": "person"}. If another antecedent atom already binds
  ?x ("All furry people are smart" -> antecedent furry(?x)), do NOT add
  is_a(?x,person). If the sort is the ONLY thing restricting ?x ("All people need
  sleep"), KEEP is_a(?x,person) as an antecedent atom — never leave the antecedent
  empty and never repeat the conclusion in the antecedent. Use "forall" only for a
  sort that covers ALL named individuals; a PROPER subset ("All young birds ...")
  stays an ordinary is_a(?x,sort) condition.
- Negative statements: a statement that a class does NOT have a property ("Every
  real number is not imaginary") is a rule whose CONSEQUENT atom carries "negated":
  true — the same predicate, not a twin predicate. A negative antecedent ("if X is
  not Y then ...") is an antecedent atom with "negated": true; it holds only under a
  world assumption the caller supplies, never by itself. A negative statement about
  a NAMED individual ("Marvin cannot be from Earth", "the duster doesn't suck") is a
  ground FACT with "negated": true and MUST be kept; a conjunction of ground
  statements is one fact per conjunct.
- A ground implication's antecedent is NOT asserted: "If 1984 is a streaming
  service, then 1984 is a hardcover book" adds only the rule
  is_a(1984, streaming_service) => is_a(1984, hardcover_book); never also assert
  is_a(1984, streaming_service) as a fact.
- Disjointness: a statement that two classes cannot overlap ("No X is a Y",
  "X and Y are disjoint") goes to "disjoint" as {"left": <class>, "right": <class>}.
  Never write it as a rule with negated premises, and never infer disjointness from
  class names: record it only when the text states it.
- Disjunction (L2). A rule whose CONSEQUENT is an alternative goes to "consequents"
  (a LIST of atoms); leave "consequent" at its default. A rule whose ANTECEDENT is a
  disjunction ("Everything that is A or B or C is D") goes to "disjunctive_antecedent"
  (a LIST of atoms) and "antecedent" is ignored; a conjunctive antecedent stays in
  "antecedent". A disjunctive GROUND fact about a named individual ("Rex is a shumpus
  or a jompus or a grimpus") goes to "disjunctions" as {"literals": [atom, atom, …],
  "quote": …}; NEVER split it into separate facts and never use "facts" for it. A
  CONJUNCTION of conclusions ("Each X is A and B") stays one consequent whose extra
  members go in the slot's "set" — the builder emits one rule per conjunct.
- Existential premise (L2). A statement that some unnamed individual has a property
  ("There is an animal", "Some person has a license", "Symptoms include coughing")
  goes to "existentials" as [{"variable": "?x", "atoms": [atom over ?x, …],
  "quote": …}]. Never encode it as a fact whose subject is the class noun.
- "domain" is the legacy global form of the same idea; leave it empty when rules
  carry "forall".
- Denial is the SAME predicate with "negated": true; never a twin predicate.
- "relation_kind" records the atom's logical role, and MUST be used consistently in
  facts AND in rule conditions/conclusions so they unify:
  - "ascription": the subject has a property/class — predicative "is/are" AND
    attributive modifiers alike. Put the PROPERTY/CLASS in "predicate", the subject
    in "subject", omit "object" ("Gary is blue", "blue people", "they are not blue"
    -> {"predicate":"blue","subject":"gary","relation_kind":"ascription"}); the
    builder emits is_a(subject, property). Never leave an in-place property as a
    plain verb predicate.
  - "possession": the subject has an object/part ("X has an engine", "four wheels").
    Keep it a binary predicate with "object"; it is NEVER is_a.
  - "action": any other verb/relation ("the bird sings", "X sees Y").
  ("predication" is a legacy surface hint; relation_kind takes precedence.)
- Modality is the "modality" field, never a prefix in the predicate name.
- Predicate ids: lowercase snake_case, no function words (a, the, and, or, of, by, to,
  for, with, from, in, on, as, when). Object ids: lowercase English head nouns; reuse
  the SAME id for the SAME concept, never mint synonyms.
- A real conditional ("if / when / provided that") is a rule; never assert its
  conclusion as a fact. An exception ("except") is kind "exception". A conditional
  about a SPECIFIC named individual keeps that CONSTANT and is a ground
  implication, never a variable over "?x": "If Harry is young then Harry is rough"
  -> antecedent young(harry), consequent rough(harry). Only a generic statement
  ("all / every / any X", a plural or a bare generic noun) is quantified over "?x".
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
5) "All furry people are smart. Gary is furry."
   facts = [{"predicate":"furry","subject":"gary","relation_kind":"ascription","quote":"Gary is furry"}]
   rules = [{"forall":{"x":"person"},
             "antecedent":[{"predicate":"furry","subject":"?x","relation_kind":"ascription","quote":"furry people"}],
             "consequent":{"predicate":"smart","subject":"?x","relation_kind":"ascription","quote":"are smart"},
             "quote":"All furry people are smart"}]
   (No is_a(?x,person) condition: "person" is in "forall", the quantifier's domain.)
6) "Every real number is not imaginary. No prime is even."
   rules = [{"antecedent":[{"predicate":"is_a","subject":"?x","object":"real_number","quote":"Every real number"}],
             "consequent":{"predicate":"is_a","subject":"?x","object":"imaginary","negated":true,"quote":"is not imaginary"},
             "quote":"Every real number is not imaginary"}]
   disjoint = [{"left":"prime","right":"even","quote":"No prime is even"}]
7) "Rex is a wumpus or a lorpus. Everything that is a wumpus or a lorpus is fierce. There is an animal."
   rules = [{"disjunctive_antecedent":[{"predicate":"is_a","subject":"?x","object":"wumpus","quote":"a wumpus"},
                                        {"predicate":"is_a","subject":"?x","object":"lorpus","quote":"a lorpus"}],
             "consequent":{"predicate":"is_a","subject":"?x","object":"fierce","quote":"is fierce"},
             "quote":"Everything that is a wumpus or a lorpus is fierce"}]
   disjunctions = [{"literals":[{"predicate":"is_a","subject":"rex","object":"wumpus","quote":"a wumpus"},
                                {"predicate":"is_a","subject":"rex","object":"lorpus","quote":"a lorpus"}],
                    "quote":"Rex is a wumpus or a lorpus"}]
   existentials = [{"variable":"?x","atoms":[{"predicate":"is_a","subject":"?x","object":"animal","quote":"There is an animal"}],
                    "quote":"There is an animal"}]
Return ONLY valid JSON, no markdown fences."""

PROBLEM_HUMAN = """Problem:
{text}

Produce the ProblemStructure JSON."""

QUESTION_SYSTEM = """You DECOMPOSE a question into the conditions it asserts as given
(Gamma) and the single conclusion it asks (the target), on top of a theory. A
deterministic expander turns your structure into conditions and a target. Return
valid JSON matching the QuestionStructure schema: presuppositions, rules, ask,
variables.

ATOM GRAMMAR — same shape as the theory: {"predicate": "...", "subject": <slot>,
"object": <slot>, "relation_kind": "ascription|possession|action",
"modality": "neutral|permit|obligation|forbidden", "negated": false,
"quote": "..."}. The relation name ALWAYS goes in "predicate". Class membership uses
predicate "is_a". A relation with no stated argument omits that slot. "relation_kind"
"ascription" means the subject has a property/class (predicative "is/are" or an
attributive modifier): put the PROPERTY in "predicate", the subject in "subject",
omit "object"; the builder makes is_a(subject, property). Use "possession" for "has"
and "action" otherwise.

The theory below (Objects, Predicates, Morphisms, Rules) is the vocabulary for the
PRESUPPOSITIONS and RULES of the question: reuse its predicates and object ids exactly
when the question refers to a theory relation, without renaming. A named individual the theory
does not mention may still appear as a CONSTANT object id — do not drop such a
condition; the engine reports non-theory conditions honestly. The ASK is exempt
entirely: it states the question's own conclusion in the question's own short wording
and may use predicates/ids the theory does not have. Concrete named things stay
CONSTANTS; a variable is used only for a genuine unknown the answer must supply.

How to decompose the question:
1. presuppositions = Gamma: ONLY the relations the QUESTION itself ASSERTS as given.
   This INCLUDES:
   - explicit clauses: "given that X is Y", "assuming ...", "suppose ...",
     "provided that ..." (and their Russian equivalents "при условии что",
     "предположим", "допустим");
   - a declarative clause joined to the interrogative by a comma or semicolon when the
     question builds on it: "Socrates is a philosopher, is Socrates mortal?" has
     presupposition is_a(socrates, philosopher) and ask is_a(socrates, mortal);
     "Rex is a puppy, does Rex bark?" has presupposition is_a(rex, puppy).
   Every such clause MUST be listed; never drop it. Do NOT copy the theory's own facts
   into the question. AND-enumerations go into one atom's {"set": [...]};
   OR-alternatives into {"variants": [...]}.
2. ask = the single conclusion being asked, and almost every question has one.
   - A value/class/actor/quantity/list question (what / which / who / how many / what
     type) is OPEN: put a variable in the unknown slot and record it in "variables"
     (e.g. {"predicate":"is_a","subject":"x","object":"?c"}). Keep the ask even when the
     theory has no such predicate, so the engine can look for the missing rule.
   - A yes/no question: the ask is the checkable conclusion, with constants only, in
     POSITIVE form. Ask "Can Tweety fly?" as fly(tweety); never copy a negation or a
     fact-to-the-contrary from the text ("cannot fly") into the ask.
   - A question asking whether SEVERAL statements ALL hold ("is X both A and B?",
     "Prove: A and B", "are A, B and C true?") goes to "ask_all" (a LIST of positive
     atoms); a question asking whether SOME statement holds ("is X A or B?",
     "Prove: A or B") goes to "ask_any" (a LIST of positive atoms). Both replace
     "ask" and leave it null; use "ask" only for a single conclusion. Every listed
     atom is in POSITIVE form with constants, exactly as for a single ask.
   - ONLY an imperative action request ("what should I do", "how do I proceed") has no
     single conclusion: set ask to null.
   Never turn "what type / which class / who / how many" into a null ask.
3. variables: reserve "?x" ONLY for a genuine unknown the answer must supply.
   Concrete named things are constants, not variables.
4. rules: only a real condition inside the question ("if / when"). Never copy a theory
   rule into the question.
5. Every presupposition, rule and ask carries ONE minimal verbatim quote.

EXAMPLE (shape only):
"Socrates is a philosopher, is Socrates mortal?"
  presuppositions = [{"predicate":"is_a","subject":"socrates","object":"philosopher","quote":"Socrates is a philosopher"}]
  ask = {"predicate":"is_a","subject":"socrates","object":"mortal","quote":"is Socrates mortal"}
  variables = {}
"Prove: Rex is a or b."
  ask = null
  ask_any = [{"predicate":"is_a","subject":"rex","object":"a","quote":"a"},
             {"predicate":"is_a","subject":"rex","object":"b","quote":"b"}]
The declarative clause is a question condition and MUST appear in presuppositions; the
ask keeps only the interrogative part.
Return ONLY valid JSON, no markdown fences."""

BUILTINS_BLOCK = """
NUMERIC THRESHOLDS (comparison predicates are available):
A threshold compares a bound value: bind it first with a relational atom, then compare
it. Operators: eq, neq, lt, lte, gt, gte; the compared value is a number. Example:
"power of at least 50" -> has_power(?x, ?p) AND gte(?p, 50). Never encode a threshold
as a new object id such as "at_least_50"."""


def builtins_block() -> str:
    return BUILTINS_BLOCK if get_setting("BUILTINS", False) else ""


REPAIR_BLOCK = """The previous decomposition below was rejected by a deterministic
checker. Fix ONLY the listed problems and return the FULL corrected structure.
Every atom MUST carry one verbatim quote that really occurs in the source; if an
atom cannot be grounded in the source, delete it. Add nothing unrelated.

Previous decomposition:
{previous}

Problems to fix:
{problems}
"""

QUESTION_REPAIR_BLOCK = """The previous decomposition below was rejected by a
deterministic checker. Fix ONLY the listed problems and return the FULL corrected
structure. Keep presuppositions ("given that ...", "assuming ...", and a declarative
clause joined to the interrogative by a comma) in "presuppositions". Every atom MUST
carry one verbatim quote from the source; if an atom cannot be grounded, delete it. Do
not invent conditions the question does not assert.

Previous decomposition:
{previous}

Problems to fix:
{problems}
"""


def _problems_block(gaps: list[str]) -> str:
    return "\n".join(f"- {gap}" for gap in gaps)


def _sample_count(samples: int | None) -> int:
    value = settings.get("EXTRACT_SAMPLES", 1) if samples is None else samples
    return max(1, int(value))


def _repair_count(repairs: int | None) -> int:
    value = settings.get("EXTRACT_REPAIRS", 0) if repairs is None else repairs
    return max(0, int(value))


def _parallel_enabled() -> bool:
    return bool(settings.get("EXTRACT_PARALLEL", True))


def _rank_key(candidate, score) -> tuple:
    """Score plus a canonical fingerprint, so ties never depend on arrival order.

    ``quality_key`` is a syntax/grounding metric and frequently ties on logically
    different structures; the canonical JSON makes best-of-N reproducible for a
    fixed multiset of samples even when they finish concurrently.
    """
    try:
        fingerprint = candidate.model_dump_json()
    except AttributeError:
        fingerprint = repr(candidate)
    return (*score(candidate), fingerprint)


def _best_of(candidates, errors, score):
    """Pick the min candidate by ``_rank_key``; raise the first error if none."""
    best = None
    best_key = None
    for candidate in candidates:
        if candidate is None:
            continue
        key = _rank_key(candidate, score)
        if best_key is None or key < best_key:
            best, best_key = candidate, key
    if best is None:
        first_error = next((error for error in errors if error is not None), None)
        raise first_error if first_error is not None else RuntimeError("no extraction candidate")
    return best


def _pick_best(make_candidate, score, samples: int):
    """Sample ``samples`` candidates and keep the best by ``score``.

    A failing sample is skipped when another succeeds; if every sample fails, the
    first error (in sample order) propagates, so N=1 keeps the previous behaviour
    exactly. Ties are broken by the candidate's canonical fingerprint, so the
    choice is independent of arrival order. With N>1 the samples are issued
    concurrently (``ANKYRA_EXTRACT_PARALLEL=false`` forces sequential); the chosen
    candidate is the same for a fixed multiset of outputs.
    """
    if samples > 1 and _parallel_enabled():
        return _pick_best_parallel(make_candidate, score, samples)
    candidates: list = [None] * samples
    errors: list[Exception | None] = [None] * samples
    for index in range(samples):
        try:
            candidates[index] = make_candidate()
        except Exception as exc:  # noqa: BLE001 - re-raised below if all fail
            errors[index] = exc
    return _best_of(candidates, errors, score)


def _pick_best_parallel(make_candidate, score, samples: int):
    """Concurrent ``_pick_best``: issue N calls at once, then rank deterministically.

    Each worker runs with a copy of the caller's context so the LLM trace
    (a ``ContextVar``) still records extraction calls made off the main thread.
    """
    from concurrent.futures import ThreadPoolExecutor
    from contextvars import copy_context

    results: list = [None] * samples
    errors: list[Exception | None] = [None] * samples
    with ThreadPoolExecutor(max_workers=samples) as pool:
        futures = [
            (index, pool.submit(copy_context().run, make_candidate))
            for index in range(samples)
        ]
        for index, future in futures:
            try:
                results[index] = future.result()
            except Exception as exc:  # noqa: BLE001 - re-raised below if all fail
                errors[index] = exc
    return _best_of(results, errors, score)


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
        head = " OR ".join(_fmt_morphism(h, with_quote=False) for h in rule.head)
        quote = f' quote="{rule.quote}"' if rule.quote else ""
        rule_lines.append(f"  R{i}: IF {conditions or '?'} => {head}{quote}")
    rules = "\n".join(rule_lines) or "  (none)"
    existential_lines = [
        "  " + " AND ".join(_fmt_morphism(atom, with_quote=False) for atom in existential.atoms)
        + f" [∃{existential.variable}]"
        for existential in theory.existentials
    ]
    existentials = "\n".join(existential_lines) or "  (none)"
    return (
        f"\n\n--- Theory ---\n"
        f"Objects: {', '.join(objects) or '(none)'}\n"
        f"Predicates: {', '.join(predicates) or '(none)'}\n\n"
        f"Morphisms:\n{morphism_lines}\n\n"
        f"Rules:\n{rules}\n"
        f"Existentials:\n{existentials}\n"
        f"--- end theory ---\n"
    )


def _iter_slots(theory: Theory):
    yield from theory.morphisms
    for rule in theory.rules:
        yield from rule.conditions
        yield from rule.head


def _fmt_morphism(morphism, *, with_quote: bool = True) -> str:
    neg = "NOT " if morphism.negated else ""
    modality = "" if morphism.modality == "neutral" else f"{morphism.modality}:"
    quote = f' quote="{morphism.quote}"' if with_quote and morphism.quote else ""
    subject = morphism.subject or ""
    obj = morphism.object or ""
    return f"{neg}{modality}{morphism.predicate}({subject}, {obj}){quote}"


def _extract_problem_once(llm: Any, text: str) -> ProblemStructure:
    messages = [
        SystemMessage(content=PROBLEM_SYSTEM + builtins_block()),
        HumanMessage(content=PROBLEM_HUMAN.format(text=text.strip())),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(llm, messages, schema=ProblemStructure, label="extract_problem")
    data.pop("source_text", None)
    data["source_text"] = text
    return ProblemStructure.model_validate(data)


def _repair_problem_once(
    llm: Any, text: str, structure: ProblemStructure, gaps: list[str]
) -> ProblemStructure:
    messages = [
        SystemMessage(content=PROBLEM_SYSTEM + builtins_block()),
        HumanMessage(
            content=PROBLEM_HUMAN.format(text=text.strip())
            + "\n\n"
            + REPAIR_BLOCK.format(
                previous=structure.model_dump_json(indent=2),
                problems=_problems_block(gaps),
            )
        ),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(text))
    data = invoke_as_dict(llm, messages, schema=ProblemStructure, label="repair_problem")
    data.pop("source_text", None)
    data["source_text"] = text
    return ProblemStructure.model_validate(data)


def _problem_quality(structure: ProblemStructure) -> tuple[int, int, int]:
    return quality_key(build_theory(structure, enforce_grounding=False))


def extract_problem_structure(
    llm: Any,
    *,
    text: str,
    samples: int | None = None,
    repairs: int | None = None,
) -> ProblemStructure:
    """One structural decomposition of the descriptive part, sampled best-of-N.

    With ``ANKYRA_EXTRACT_SAMPLES`` > 1 the model is called N times and the best
    structure is picked by ``symbolic.quality_key`` (fewer grounding gaps, more
    source coverage, more compact) — deterministic for any fixed set of samples.
    ``ANKYRA_EXTRACT_REPAIRS`` adds bounded repair passes driven by repairable gaps.
    """
    best = _pick_best(
        lambda: _extract_problem_once(llm, text),
        _problem_quality,
        _sample_count(samples),
    )
    for _ in range(_repair_count(repairs)):
        report = symbolic_check(build_theory(best, enforce_grounding=False))
        repairable = [gap for gap in report.gaps if classify_gap(gap) is GapClass.REPAIRABLE]
        if not repairable:
            break
        best = _repair_problem_once(llm, text, best, repairable)
    return best


def _extract_question_once(
    llm: Any, question: str, theory: Theory, source_text: str
) -> QuestionStructure:
    messages = [
        SystemMessage(content=QUESTION_SYSTEM),
        HumanMessage(
            content=QUESTION_HUMAN.format(
                question=question.strip(),
                theory=format_theory_for_llm(theory),
            )
        ),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(source_text))
    data = invoke_as_dict(llm, messages, schema=QuestionStructure, label="extract_question")
    data.pop("source_text", None)
    data["source_text"] = source_text
    return QuestionStructure.model_validate(data)


def _repair_question_once(
    llm: Any,
    question: str,
    theory: Theory,
    source_text: str,
    structure: QuestionStructure,
    gaps: list[str],
) -> QuestionStructure:
    messages = [
        SystemMessage(content=QUESTION_SYSTEM),
        HumanMessage(
            content=QUESTION_HUMAN.format(
                question=question.strip(),
                theory=format_theory_for_llm(theory),
            )
            + "\n\n"
            + QUESTION_REPAIR_BLOCK.format(
                previous=structure.model_dump_json(indent=2),
                problems=_problems_block(gaps),
            )
        ),
    ]
    llm = with_max_tokens(llm, extract_max_tokens(source_text))
    data = invoke_as_dict(llm, messages, schema=QuestionStructure, label="repair_question")
    data.pop("source_text", None)
    data["source_text"] = source_text
    return QuestionStructure.model_validate(data)


def _question_theory(structure: QuestionStructure) -> Theory:
    """The question's asserted atoms as a theory, only for deterministic scoring."""
    query = unroll_query_structure(structure)
    goal = [query.target] if query.target is not None else []
    return Theory(morphisms=[*query.conditions, *goal], source_text=structure.source_text)


def _question_quality(structure: QuestionStructure) -> tuple[int, int, int]:
    return quality_key(_question_theory(structure))


def extract_question_structure(
    llm: Any,
    *,
    question: str,
    theory: Theory,
    source_text: str = "",
    samples: int | None = None,
    repairs: int | None = None,
) -> QuestionStructure:
    """Express the question over the theory vocabulary, sampled best-of-N."""
    text = (source_text or question).strip()
    best = _pick_best(
        lambda: _extract_question_once(llm, question, theory, text),
        _question_quality,
        _sample_count(samples),
    )
    for _ in range(_repair_count(repairs)):
        repairable = [
            gap
            for gap in symbolic_check(_question_theory(best)).gaps
            if classify_gap(gap) is GapClass.REPAIRABLE
        ]
        if not repairable:
            break
        best = _repair_question_once(llm, question, theory, text, best, repairable)
    return best
