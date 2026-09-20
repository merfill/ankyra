"""Deterministic completeness checks for the Phase 0 builder (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ankyra.build.normalize import FORBIDDEN_PRED_TOKENS, is_var
from ankyra.core.models import Theory

_NORM = re.compile(r"\s+")
_CAMEL_OBJ = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_SNAKE_PRED = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
_NUMERIC_TERM = re.compile(r"^[+-]?\d+(\.\d+)?$")


class GapClass(str, Enum):
    """What a deterministic gap licenses — repair, ignore, or deterministic handling."""

    REPAIRABLE = "repairable"
    LEGITIMATE = "legitimate"
    DETERMINISTIC = "deterministic"


_LEGITIMATE_MARKERS = ("consequence_negates_premise", "axiom_blocks_exception")


def classify_gap(gap: str) -> GapClass:
    """Classify a ``symbolic_check`` gap by the action it licenses.

    A gap that is a correct extraction (an exception rule negating its premise, a
    rule that truly contradicts an axiom) is *legitimate* and must never trigger a
    repair. Quote and structure failures are *repairable*; naming failures are
    cosmetic and handled without the LLM. Unknown gaps default to legitimate so the
    safe action is always "leave it alone".
    """
    if any(marker in gap for marker in _LEGITIMATE_MARKERS):
        return GapClass.LEGITIMATE
    if gap.startswith("missing_quote:"):
        return GapClass.REPAIRABLE
    if gap.startswith("conditional_quote:"):
        return GapClass.REPAIRABLE
    if gap in {"structural:empty_theory", "structural:morphism:missing_predicate"}:
        return GapClass.REPAIRABLE
    if gap.startswith("naming:"):
        return GapClass.DETERMINISTIC
    return GapClass.LEGITIMATE


def _norm(text: str | None) -> str:
    cleaned = str(text or "").replace("-", " ")
    return _NORM.sub(" ", cleaned.strip().casefold())


def normalize_quote(quote: str | None) -> str:
    """Normalized comparison form of a quote (case/space/hyphen insensitive)."""
    return _norm(quote)


_EDGE_PUNCTUATION = ".,;:!?\"'()[]{} "


def _core(quote: str | None) -> str:
    """The quote without surrounding sentence punctuation.

    A rule's stored quote and the quote an LLM proposes for a fact frequently differ
    only by a trailing period (``"... book"`` vs ``"... book."``). Comparing cores
    keeps the conditional-quote guard from being defeated by punctuation.
    """
    return normalize_quote(quote).strip(_EDGE_PUNCTUATION)


def quote_in_source(quote: str | None, source: str | None) -> bool:
    """True when the quote is a real (normalized) substring of the source."""
    normalized = normalize_quote(quote)
    if not normalized:
        return False
    return normalized in _norm(source)


def _morphism_key(morphism) -> tuple:
    return (morphism.predicate, morphism.subject, morphism.object, morphism.negated, morphism.modality)


def _quote_occurrences(needle: str, haystack: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = haystack.find(needle)
    while start != -1:
        spans.append((start, start + len(needle)))
        start = haystack.find(needle, start + 1)
    return spans


def _conditional_spans(theory: Theory) -> list[tuple[int, int]]:
    """Source spans of each rule's conditional sentence (punctuation-insensitive)."""
    source = normalize_quote(theory.source_text)
    spans: list[tuple[int, int]] = []
    for rule in theory.rules:
        normalized = _core(rule.quote)
        if normalized:
            spans.extend(_quote_occurrences(normalized, source))
    return spans


def quote_only_in_conditional(quote: str | None, theory: Theory) -> bool:
    """True when every occurrence of ``quote`` lies inside a rule's span.

    A conditional premise ("If Harry is red then ...") cannot assert the same
    phrase as a fact; asserting it is a fabricated axiom. If the phrase also occurs
    standalone in the source, at least one occurrence is outside the rule spans and
    the quote stays usable. Punctuation at the span edges is ignored, so a rule
    quote without a trailing period still covers the sentence that has one.
    """
    normalized = _core(quote)
    if not normalized:
        return False
    source = normalize_quote(theory.source_text)
    if not source:
        return False
    spans = _conditional_spans(theory)
    occurrences = _quote_occurrences(normalized, source)
    if not occurrences:
        return False
    return all(
        any(a <= start and start + len(normalized) <= b for a, b in spans)
        for start, _ in occurrences
    )


def check_quote_witnesses(theory: Theory) -> list[str]:
    gaps: list[str] = []
    for m in theory.morphisms:
        if not quote_in_source(m.quote, theory.source_text):
            gaps.append(f"missing_quote:morphism:{m.predicate}({m.subject},{m.object})")
        elif quote_only_in_conditional(m.quote, theory):
            gaps.append(f"conditional_quote:morphism:{m.predicate}({m.subject},{m.object})")
    for i, rule in enumerate(theory.rules, 1):
        if not quote_in_source(rule.quote, theory.source_text):
            gaps.append(f"missing_quote:rule:{i}")
    for i, constraint in enumerate(theory.constraints, 1):
        if not quote_in_source(constraint.quote, theory.source_text):
            gaps.append(f"missing_quote:constraint:{i}")
    for i, existential in enumerate(theory.existentials, 1):
        if not quote_in_source(existential.quote, theory.source_text):
            gaps.append(f"missing_quote:existential:{i}")
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
        if is_var(name) or _NUMERIC_TERM.match(name):
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
        yield from rule.head
    for existential in theory.existentials:
        yield from existential.atoms


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


def enforce_grounded(theory: Theory) -> Theory:
    """Drop axioms/rules whose quote is not a real substring of the source.

    Enforces the core invariant ("nothing enters the theory without a valid
    quote") on the extraction path. It is a no-op when the theory carries no
    ``source_text``: synthetic theories provably built in code have no source to
    anchor to, and only the LLM extraction path must be grounded.
    """
    source = theory.source_text or ""
    if not source.strip():
        return theory
    morphisms = [m for m in theory.morphisms if quote_in_source(m.quote, source)]
    rules = [r for r in theory.rules if quote_in_source(r.quote, source)]
    constraints = [c for c in theory.constraints if quote_in_source(c.quote, source)]
    existentials = [e for e in theory.existentials if quote_in_source(e.quote, source)]
    if (
        len(morphisms) == len(theory.morphisms)
        and len(rules) == len(theory.rules)
        and len(constraints) == len(theory.constraints)
        and len(existentials) == len(theory.existentials)
    ):
        return theory
    return theory.model_copy(
        update={
            "morphisms": morphisms,
            "rules": rules,
            "constraints": constraints,
            "existentials": existentials,
        }
    )


def source_coverage(quotes, source: str | None) -> int:
    """Source characters covered by at least one valid quote (union of spans)."""
    haystack = normalize_quote(source)
    if not haystack:
        return 0
    covered = bytearray(len(haystack))
    for quote in quotes:
        needle = normalize_quote(quote)
        if not needle:
            continue
        start = haystack.find(needle)
        while start != -1:
            covered[start : start + len(needle)] = b"\x01" * len(needle)
            start = haystack.find(needle, start + 1)
    return sum(covered)


def quality_key(theory: Theory) -> tuple[int, int, int]:
    """Deterministic lexicographic rank of an extraction candidate (lower wins).

    1. fewer repairable gaps (spec violations); 2. more source characters covered
    by valid quotes; 3. more compact. Legitimate gaps — an exception rule or a
    real contradiction — are never penalized. An empty theory is a coverage
    failure, not a grounding defect, so ``empty_theory`` is not counted here.
    """
    hard = sum(
        1
        for gap in symbolic_check(theory).gaps
        if classify_gap(gap) is GapClass.REPAIRABLE
        and not gap.startswith("structural:empty_theory")
    )
    quotes = [m.quote for m in theory.morphisms if quote_in_source(m.quote, theory.source_text)]
    quotes += [r.quote for r in theory.rules if quote_in_source(r.quote, theory.source_text)]
    covered = source_coverage(quotes, theory.source_text)
    size = len(theory.morphisms) + len(theory.rules)
    return (hard, -covered, size)
