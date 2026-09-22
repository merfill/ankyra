"""Gold-FOL diagnostic for FOLIO: feed the annotated FOL directly to the engine.

Separates two failure sources on FOLIO (``docs/folio.md`` §6): **fragment** (the gold
formalization itself is not decidable by the engine's logic) versus **extraction**
(text-to-theory errors). No LLM: the FOL annotation is parsed deterministically into
the L1/L2 models, so the number isolates the method from extraction errors
(``docs/folio_ceilings.md`` §4).

The parser covers the reachable L2 shape — universal/implication formulas, ``∧``/``∨``,
negation (pushed to literals by NNF), conjunctive existential premises (``∃x (φ ∧ …)``),
ground or open goals, flat compound goals and a conjunctive existential conclusion with a
shared witness (``∃x (A(x) ∧ B(x))``, decided jointly, ``docs/t1_plan.md``). A formula
outside the committed fragment raises :class:`FolParseError` (an honest
``out_of_fragment``), never a guessed encoding: universal/conditional goals, nested
quantifiers and function terms stay outside L2.
"""

from __future__ import annotations

import re

from ankyra.core.models import Existential, Morphism, Object, Query, Rule, Theory

_LABEL_TO_KIND = {"True": "yes", "False": "no", "Uncertain": "unknown"}
_VARIABLES = frozenset({"x", "y", "z"})

# A token is a connective, a parenthesis/comma, or an identifier (unicode letters,
# digits, underscore, and the annotation's typographic apostrophe in ``Companies’Stocks``).
_TOKEN = re.compile(r"\s*(∀|∃|¬|∧|∨|→|\(|\)|,|[^\W\d][\w’']*)", re.UNICODE)


class FolParseError(Exception):
    """The gold formula is outside the supported L2 shape (``out_of_fragment``)."""


def expected_kind(label: str, flipped: bool) -> str:
    kind = _LABEL_TO_KIND[label]
    if not flipped:
        return kind
    return {"yes": "no", "no": "yes", "unknown": "unknown"}[kind]


def statement_negative(record: dict) -> bool:
    """Polarity of the conclusion as annotated (leading ``¬`` or a negative NL cue)."""
    return record["conclusion_fol"].strip().startswith("¬")


# --- tokenizer and recursive-descent parser ---------------------------------------


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        match = _TOKEN.match(text, position)
        if match is None:
            raise FolParseError(f"unexpected character {text[position]!r}")
        tokens.append(match.group(1))
        position = match.end()
    return tokens


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._index = 0

    def _peek(self) -> str | None:
        return self._tokens[self._index] if self._index < len(self._tokens) else None

    def _take(self) -> str:
        token = self._peek()
        if token is None:
            raise FolParseError("unexpected end of formula")
        self._index += 1
        return token

    def _expect(self, token: str) -> None:
        if self._peek() != token:
            raise FolParseError(f"expected {token!r}, got {self._peek()!r}")
        self._index += 1

    def parse(self):
        formula = self._formula()
        if self._peek() is not None:
            raise FolParseError(f"trailing tokens: {self._tokens[self._index:]}")
        return formula

    def _formula(self):
        left = self._or()
        if self._peek() == "→":
            self._take()
            return ("implies", left, self._formula())
        return left

    def _or(self):
        parts = [self._and()]
        while self._peek() == "∨":
            self._take()
            parts.append(self._and())
        return _mk_or(parts)

    def _and(self):
        parts = [self._unary()]
        while self._peek() == "∧":
            self._take()
            parts.append(self._unary())
        return _mk_and(parts)

    def _unary(self):
        token = self._peek()
        if token == "¬":
            self._take()
            return ("not", self._unary())
        if token in ("∀", "∃"):
            self._take()
            variable = self._take()
            if variable in ("∀", "∃", "(", ")", ",", "¬", "∧", "∨", "→"):
                raise FolParseError(f"expected a variable after {token!r}")
            return ("forall" if token == "∀" else "exists", variable, self._formula())
        if token == "(":
            self._take()
            inner = self._formula()
            self._expect(")")
            return inner
        return self._atom()

    def _atom(self):
        name = self._take()
        if name in ("∀", "∃", "¬", "∧", "∨", "→", "(", ")", ","):
            raise FolParseError(f"expected a predicate, got {name!r}")
        self._expect("(")
        args: list[str] = []
        if self._peek() != ")":
            args.append(self._take())
            while self._peek() == ",":
                self._take()
                args.append(self._take())
        self._expect(")")
        return ("atom", name, args)


def _mk_and(parts: list):
    flat: list = []
    for part in parts:
        if part[0] == "and":
            flat.extend(part[1])
        else:
            flat.append(part)
    if not flat:
        raise FolParseError("empty conjunction")
    return flat[0] if len(flat) == 1 else ("and", flat)


def _mk_or(parts: list):
    flat: list = []
    for part in parts:
        if part[0] == "or":
            flat.extend(part[1])
        else:
            flat.append(part)
    if not flat:
        raise FolParseError("empty disjunction")
    return flat[0] if len(flat) == 1 else ("or", flat)


def _parse(text: str):
    return _Parser(_tokenize(text)).parse()


# --- negation normal form and CNF --------------------------------------------------


def _is_literal(formula) -> bool:
    if formula[0] == "atom":
        return True
    return formula[0] == "not" and formula[1][0] == "atom"


def _nnf(formula, negate: bool = False):
    tag = formula[0]
    if tag == "atom":
        return ("not", formula) if negate else formula
    if tag == "not":
        return _nnf(formula[1], not negate)
    if tag == "and":
        parts = [_nnf(part, negate) for part in formula[1]]
        return _mk_or(parts) if negate else _mk_and(parts)
    if tag == "or":
        parts = [_nnf(part, negate) for part in formula[1]]
        return _mk_and(parts) if negate else _mk_or(parts)
    if tag == "implies":
        if negate:
            return _mk_and([_nnf(formula[1], False), _nnf(formula[2], True)])
        return _mk_or([_nnf(formula[1], True), _nnf(formula[2], False)])
    if tag in ("forall", "exists"):
        flipped = "exists" if (tag == "forall") == negate else "forall"
        return (flipped, formula[1], _nnf(formula[2], negate))
    raise FolParseError(f"unsupported formula {tag!r}")


def _cnf(formula) -> list[list]:
    if _is_literal(formula):
        return [[formula]]
    if formula[0] == "and":
        clauses: list[list] = []
        for part in formula[1]:
            clauses.extend(_cnf(part))
        return clauses
    if formula[0] == "or":
        clauses = [[]]
        for part in formula[1]:
            sub = _cnf(part)
            clauses = [left + right for left in clauses for right in sub]
        return clauses
    raise FolParseError(f"unsupported quantifier/nesting in {formula[0]!r}")


# --- formula -> engine models ------------------------------------------------------


def _term(value: str) -> str:
    return f"?{value}" if value in _VARIABLES else value


def _morphism(literal) -> Morphism:
    negated = literal[0] == "not"
    atom = literal[1] if negated else literal
    _, name, args = atom
    predicate = name.casefold()
    if len(args) == 1:
        return Morphism(predicate="is_a", subject=_term(args[0]), object=predicate, negated=negated)
    if len(args) == 2:
        return Morphism(predicate=predicate, subject=_term(args[0]), object=_term(args[1]), negated=negated)
    raise FolParseError(f"unsupported arity {len(args)} for {name}")


def _negate_literal(literal):
    if literal[0] == "not":
        return literal[1]
    return ("not", literal)


def _body_literals(formula) -> list | None:
    if _is_literal(formula):
        return [formula]
    if formula[0] == "and" and all(_is_literal(part) for part in formula[1]):
        return list(formula[1])
    return None


def _head_literals(formula) -> list | None:
    if _is_literal(formula):
        return [formula]
    if formula[0] == "or" and all(_is_literal(part) for part in formula[1]):
        return list(formula[1])
    return None


def _clause_rule(clause: list) -> Rule:
    """A clause (disjunction of literals) as ``conditions → head (∨ alternatives)``."""
    positive = [literal for literal in clause if literal[0] == "atom"]
    negative = [literal for literal in clause if literal[0] == "not"]
    if positive:
        consequence = _morphism(positive[0])
        alternatives = [_morphism(literal) for literal in positive[1:]]
        conditions = [_morphism(_negate_literal(literal)) for literal in negative]
    else:
        consequence = _morphism(negative[0])
        alternatives = []
        conditions = [_morphism(_negate_literal(literal)) for literal in negative[1:]]
    return Rule(conditions=conditions, consequence=consequence, alternatives=alternatives)


def _has_variable(morphism: Morphism) -> bool:
    return bool(morphism.subject and morphism.subject.startswith("?")) or bool(
        morphism.object and morphism.object.startswith("?")
    )


def _premise(formula) -> tuple[list[Morphism], list[Rule], list[Existential]]:
    stripped = formula
    while stripped[0] == "forall":
        stripped = stripped[2]
    if stripped[0] == "exists":
        if stripped is not formula:
            raise FolParseError("nested quantifier in a premise")
        return _existential_premise(stripped)
    if stripped[0] == "implies":
        body = _body_literals(stripped[1])
        head = _head_literals(stripped[2])
        if body is not None and head is not None:
            consequence = _morphism(head[0])
            alternatives = [_morphism(literal) for literal in head[1:]]
            return [], [Rule(
                conditions=[_morphism(literal) for literal in body],
                consequence=consequence,
                alternatives=alternatives,
            )], []
    facts: list[Morphism] = []
    rules: list[Rule] = []
    for clause in _cnf(_nnf(stripped)):
        if len(clause) == 1:
            fact = _morphism(clause[0])
            if _has_variable(fact):
                raise FolParseError("universally quantified fact is out of fragment")
            facts.append(fact)
        else:
            rules.append(_clause_rule(clause))
    return facts, rules, []


def _existential_premise(formula) -> tuple[list, list, list[Existential]]:
    variable = f"?{formula[1]}"
    body = _nnf(formula[2])
    if _is_literal(body):
        literals = [body]
    elif body[0] == "and" and all(_is_literal(part) for part in body[1]):
        literals = list(body[1])
    else:
        raise FolParseError("existential premise is not a conjunction of literals")
    atoms = [_morphism(literal) for literal in literals]
    return [], [], [Existential(variable=variable, atoms=atoms)]


def _conclusion(formula):
    """Return ``(target, goals, goal_mode)`` for the annotated conclusion."""
    if formula[0] == "forall":
        raise FolParseError("universal conclusion has no goal form (L2 target form pending)")
    if formula[0] == "exists":
        body = _nnf(formula[2])
        if _is_literal(body):
            literal = body
            target = _morphism(literal)
            return target, [], "single"
        if body[0] == "and" and all(_is_literal(part) for part in body[1]):
            goals = [_morphism(literal) for literal in body[1]]
            return goals[0], goals, "all"
        if body[0] == "or" and all(_is_literal(part) for part in body[1]):
            goals = [_morphism(literal) for literal in body[1]]
            return goals[0], goals, "any"
        raise FolParseError("existential conclusion is not a flat literal combination")
    normal = _nnf(formula)
    if _is_literal(normal):
        target = _morphism(normal)
        return target, [], "single"
    if normal[0] == "and" and all(_is_literal(part) for part in normal[1]):
        goals = [_morphism(literal) for literal in normal[1]]
        return goals[0], goals, "all"
    if normal[0] == "or" and all(_is_literal(part) for part in normal[1]):
        goals = [_morphism(literal) for literal in normal[1]]
        return goals[0], goals, "any"
    raise FolParseError("compound conclusion is not a flat conjunction/disjunction")


def _object_names(theory: Theory, target: Morphism | None, goals: list[Morphism]) -> list[str]:
    names: list[str] = []
    atoms: list[Morphism] = [*theory.morphisms]
    for rule in theory.rules:
        atoms.extend(rule.conditions)
        atoms.extend(rule.head)
    for existential in theory.existentials:
        atoms.extend(existential.atoms)
    if target is not None:
        atoms.append(target)
    atoms.extend(goals)
    for atom in atoms:
        if atom.predicate == "is_a":
            terms = (atom.subject,)
        else:
            terms = (atom.subject, atom.object)
        names.extend(term for term in terms if term and not term.startswith("?"))
    return list(dict.fromkeys(names))


def to_theory_query(record: dict, *, world_assumption: str = "open") -> tuple[Theory, Query]:
    """Parse a FOLIO record's gold FOL into ``(Theory, Query)``.

    Raises :class:`FolParseError` when a premise or conclusion is outside the supported
    L2 shape; the caller reports ``out_of_fragment`` rather than guessing.
    """
    facts: list[Morphism] = []
    rules: list[Rule] = []
    existentials: list[Existential] = []
    for formula in record["premises_fol"]:
        premise_facts, premise_rules, premise_existentials = _premise(_parse(formula))
        facts.extend(premise_facts)
        rules.extend(premise_rules)
        existentials.extend(premise_existentials)

    target, goals, goal_mode = _conclusion(_parse(record["conclusion_fol"]))
    theory = Theory(
        objects=[Object(id=name) for name in _object_names(
            Theory(morphisms=facts, rules=rules, existentials=existentials), target, goals
        )],
        morphisms=facts,
        rules=rules,
        existentials=existentials,
    )
    query = Query(
        target=target,
        goals=goals,
        goal_mode=goal_mode,
        answer_type="yes_no",
        world_assumption=world_assumption,
    )
    return theory, query
