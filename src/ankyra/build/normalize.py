"""Deterministic term normalization shared by the builder and the engine."""

from __future__ import annotations

import re

_SNAKE_PRED = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")

def is_var(value: str | None) -> bool:
    """True for a logic variable term such as ``?x``."""
    return bool(value) and value.startswith("?")


FORBIDDEN_PRED_TOKENS = frozenset(
    {
        "a",
        "the",
        "and",
        "or",
        "of",
        "by",
        "to",
        "for",
        "with",
        "from",
        "in",
        "on",
        "as",
        "when",
    }
)


def canonicalize_predicate(name: str) -> str:
    """Purely syntactic predicate id: casefold, hyphen to underscore, drop function
    words. The reserved id ``is_a`` is preserved. Semantics (which predicate to
    use for subsumption, how to spell a denial) belong to the extraction prompt,
    not to this function; an id left empty means the atom is malformed.
    """
    raw = (name or "").strip()
    if not raw:
        return raw
    lowered = raw.replace("-", "_").casefold()
    if lowered == "is_a":
        return "is_a"
    kept = [
        token for token in lowered.split("_") if token and token not in FORBIDDEN_PRED_TOKENS
    ]
    return "_".join(kept)


def predicate_polarity(name: str, negated: bool = False) -> tuple[str, bool]:
    """Canonical predicate id plus the polarity flag carried on the morphism."""
    return canonicalize_predicate(name), bool(negated)
