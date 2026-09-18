"""Deterministic completeness checks for the Phase 0 builder (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ankyra.build.normalize import FORBIDDEN_PRED_TOKENS
from ankyra.core.models import Theory

_NORM = re.compile(r"\s+")
_CAMEL_OBJ = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_SNAKE_PRED = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


def _norm(text: str | None) -> str:
    cleaned = str(text or "").replace("-", " ")
    return _NORM.sub(" ", cleaned.strip().casefold())


def normalize_quote(quote: str | None) -> str:
    """Normalized comparison form of a quote (case/space/hyphen insensitive)."""
    return _norm(quote)


def quote_in_source(quote: str | None, source: str | None) -> bool:
    """True when the quote is a real (normalized) substring of the source."""
    normalized = normalize_quote(quote)
    if not normalized:
        return False
    return normalized in _norm(source)


def _morphism_key(morphism) -> tuple:
    return (morphism.predicate, morphism.subject, morphism.object, morphism.negated, morphism.modality)


def check_quote_witnesses(theory: Theory) -> list[str]:
    gaps: list[str] = []
    for m in theory.morphisms:
        if not quote_in_source(m.quote, theory.source_text):
            gaps.append(f"missing_quote:morphism:{m.predicate}({m.subject},{m.object})")
    for i, rule in enumerate(theory.rules, 1):
        if not quote_in_source(rule.quote, theory.source_text):
            gaps.append(f"missing_quote:rule:{i}")
    return gaps


def check_structural(theory: Theory) -> list[str]:
    """Flag rules that can only fire into a contradiction with existing facts."""
    gaps: list[str] = []
    if not theory.morphisms and not theory.rules:
        gaps.append("structural:empty_theory")
    for m in theory.morphisms:
        if not (m.predicate or "").strip():
            gaps.append("structural:morphism:missing_predicate")
    axiom_keys = {_morphism_key(m) for m in theory.morphisms}
    for i, rule in enumerate(theory.rules, 1):
        consequence = rule.consequence
        cons_key = _morphism_key(consequence)
        for cond in rule.conditions:
            cond_key = _morphism_key(cond)
            if (
                cond_key[:3] == cons_key[:3]
                and cond_key[3] != cons_key[3]
                and cond_key[4] == cons_key[4]
            ):
                gaps.append(
                    f"structural:rule:{i}:consequence_negates_premise:{consequence.predicate}"
                    f"({consequence.subject},{consequence.object})"
                )
                break
        opposite = (
            consequence.predicate,
            consequence.subject,
            consequence.object,
            not consequence.negated,
            consequence.modality,
        )
        if opposite in axiom_keys:
            gaps.append(
                f"structural:axiom_blocks_exception:{consequence.predicate}"
                f"({consequence.subject},{consequence.object})"
            )
    return gaps


def check_naming(theory: Theory) -> list[str]:
    """Deterministic id-recipe errors."""
    gaps: list[str] = []
    for obj in theory.objects:
        name = (obj.id or "").strip()
        if not name:
            continue
        if not _CAMEL_OBJ.match(name):
            gaps.append(f"naming:object:{name}:rewrite_to_lowerCamelCase")
    predicates = {m.predicate for m in _all_slots(theory) if m.predicate}
    for pred in sorted(predicates):
        if not _SNAKE_PRED.match(pred):
            gaps.append(f"naming:predicate:{pred}:rewrite_to_lowercase_snake_case")
        if pred == "is_a":
            continue
        hits = [token for token in pred.split("_") if token in FORBIDDEN_PRED_TOKENS]
        if hits:
            gaps.append(f"naming:predicate:{pred}:drop_forbidden_tokens:{','.join(hits)}")
    return gaps


def _all_slots(theory: Theory):
    yield from theory.morphisms
    for rule in theory.rules:
        yield from rule.conditions
        yield rule.consequence


@dataclass
class SymbolicReport:
    gaps: list[str] = field(default_factory=list)
    ok: bool = True

    def __post_init__(self) -> None:
        self.ok = not self.gaps


def symbolic_check(theory: Theory) -> SymbolicReport:
    """Merge quote, structural and naming checks into one deterministic report."""
    gaps: list[str] = []
    seen: set[str] = set()
    for gap in (
        check_quote_witnesses(theory)
        + check_structural(theory)
        + check_naming(theory)
    ):
        if gap not in seen:
            seen.add(gap)
            gaps.append(gap)
    return SymbolicReport(gaps=gaps)
