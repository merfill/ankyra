"""Gold-FOL diagnostic for FOLIO: feed the annotated FOL directly to the engine.

Separates two failure sources on FOLIO (``docs/folio.md`` §6): **fragment** (the gold
formalization itself is not decidable by the engine's logic) versus **extraction**
(text-to-theory errors). No LLM: the FOL annotation is parsed deterministically.

Only the committed negation-subset shape is supported: unary/binary predicates,
``∀x``/``∀x ∀y`` implications, negation, conjunction, and ground literals. Variables
are the annotation's ``x``/``y``/``z``; everything else is a constant.
"""

from __future__ import annotations

import re

from ankyra.core.models import Morphism, Object, Query, Rule, Theory

_LABEL_TO_KIND = {"True": "yes", "False": "no", "Uncertain": "unknown"}
_VARIABLES = frozenset({"x", "y", "z"})


def expected_kind(label: str, flipped: bool) -> str:
    kind = _LABEL_TO_KIND[label]
    if not flipped:
        return kind
    return {"yes": "no", "no": "yes", "unknown": "unknown"}[kind]


def _split_top(text: str, sep: str) -> list[str]:
    out: list[str] = []
    depth = 0
    current = ""
    index = 0
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if depth == 0 and text[index : index + len(sep)] == sep:
            out.append(current)
            current = ""
            index += len(sep)
            continue
        current += char
        index += 1
    out.append(current)
    return [piece.strip() for piece in out]


def _strip_quantifiers(text: str) -> str:
    text = text.strip()
    while text.startswith("∀"):
        match = re.match(r"∀\s*([A-Za-z][A-Za-z0-9_]*)\s*", text)
        if match is None:
            break
        text = text[match.end() :]
    if text.startswith("(") and text.endswith(")"):
        depth = 0
        outer = True
        for position, char in enumerate(text):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and position != len(text) - 1:
                    outer = False
                    break
        if outer:
            text = text[1:-1].strip()
    return text


def _parse_literal(text: str):
    text = text.strip()
    negated = False
    if text.startswith("¬"):
        negated = True
        text = text[1:].strip()
    match = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\s*\((.*)\)$", text)
    if match is None:
        return None
    args = [arg.strip() for arg in _split_top(match.group(2), ",") if arg.strip()]
    return (negated, match.group(1), args)


def _fact_or_rule(text: str):
    """Return ``("rule", conditions, consequence)`` or ``("fact", literals, None)``."""
    parts = _split_top(text, "→")
    if len(parts) == 2:
        conditions = [lit for lit in (_parse_literal(p) for p in _split_top(parts[0], "∧")) if lit]
        return ("rule", conditions, _parse_literal(parts[1]))
    conjunction = [_parse_literal(p) for p in _split_top(text, "∧")]
    if len(conjunction) > 1 and all(conjunction):
        return ("fact", conjunction, None)
    literal = _parse_literal(text)
    return ("fact", [literal] if literal is not None else [], None)


def _term(value: str) -> str:
    return f"?{value}" if value in _VARIABLES else value


def _to_atom(literal):
    """A parsed literal -> ``(predicate, subject, object, negated)``.

    A unary predicate is a class/property and maps to ``is_a`` (the builder's
    convention); a binary predicate stays relational.
    """
    negated, predicate, args = literal
    name = predicate.casefold()
    if len(args) == 1:
        return ("is_a", _term(args[0]), name, negated)
    if len(args) == 2:
        return (name, _term(args[0]), _term(args[1]), negated)
    return None


def _morphism(atom) -> Morphism:
    predicate, subject, obj, negated = atom
    return Morphism(predicate=predicate, subject=subject, object=obj, negated=negated)


def to_theory_query(record: dict, *, world_assumption: str = "open") -> tuple[Theory, Query]:
    """Parse a FOLIO record's gold FOL into ``(Theory, Query)``."""
    facts = []
    rules = []
    for formula in record["premises_fol"]:
        body = _strip_quantifiers(formula)
        kind, payload, consequence = _fact_or_rule(body)
        if kind == "fact":
            facts.extend(atom for atom in (_to_atom(lit) for lit in payload) if atom)
        else:
            conditions = [atom for atom in (_to_atom(lit) for lit in payload) if atom]
            head = _to_atom(consequence) if consequence else None
            if head and conditions:
                rules.append((conditions, head))

    body = _strip_quantifiers(record["conclusion_fol"])
    kind, payload, _ = _fact_or_rule(body)
    target = _to_atom(payload[0]) if payload else None

    names: list[str] = []
    for atom in facts:
        names.extend(term for term in atom[1:3] if term and not term.startswith("?"))
    for conditions, head in rules:
        for atom in [*conditions, head]:
            names.extend(term for term in atom[1:3] if term and not term.startswith("?"))
    if target:
        names.extend(term for term in target[1:3] if term and not term.startswith("?"))
    objects = [Object(id=name) for name in dict.fromkeys(names)]

    theory = Theory(
        objects=objects,
        morphisms=[_morphism(atom) for atom in facts],
        rules=[Rule(conditions=[_morphism(atom) for atom in conditions], consequence=_morphism(head)) for conditions, head in rules],
    )
    query = Query(
        target=_morphism(target) if target else None,
        answer_type="yes_no",
        world_assumption=world_assumption,
    )
    return theory, query


def statement_negative(record: dict) -> bool:
    """Polarity of the conclusion as annotated (leading ``¬`` or a negative NL cue)."""
    return record["conclusion_fol"].strip().startswith("¬")
