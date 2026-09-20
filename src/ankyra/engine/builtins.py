"""Range-restricted builtin comparisons (decision D1, v0.1, behind a flag).

A builtin atom is never matched against facts; it is *evaluated* as a filter over
the current substitution. The closed operator set is ``eq`` / ``neq`` / ``lt`` /
``lte`` / ``gt`` / ``gte`` over numeric literals (``eq`` / ``neq`` also compare
strings). Safety: every variable in a builtin condition must be bound by an
earlier positive relational atom of the same rule body.
"""

from __future__ import annotations

from ankyra.build.normalize import is_var
from ankyra.config.settings import get_setting
from ankyra.core.models import Morphism, Rule

Subst = dict[str, str]

_ALIASES = {"=": "eq", "==": "eq", "!=": "neq", "<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}
_CANONICAL = frozenset({"eq", "neq", "lt", "lte", "gt", "gte"})


def builtins_enabled() -> bool:
    return bool(get_setting("BUILTINS", False))


def canonical_builtin(name: str) -> str | None:
    if not name:
        return None
    normalized = _ALIASES.get(name.strip(), name.strip().casefold())
    return normalized if normalized in _CANONICAL else None


def is_builtin(name: str) -> bool:
    return builtins_enabled() and canonical_builtin(name) is not None


def _resolve(term: str | None, subst: Subst) -> str | None:
    if term is None:
        return None
    if is_var(term):
        return subst.get(term) or subst.get(term[1:])
    return term


def _number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate(atom: Morphism, subst: Subst) -> Subst | None:
    """Return the substitution if the builtin holds, else ``None``.

    An unbound variable or a non-numeric operand fails the filter; this never
    raises, so a malformed comparison can only fail to match.
    """
    op = canonical_builtin(atom.predicate)
    if op is None:
        return None
    left = _resolve(atom.subject, subst)
    right = _resolve(atom.object, subst)
    if left is None or right is None:
        return None

    if op in {"eq", "neq"}:
        left_number, right_number = _number(left), _number(right)
        if left_number is not None and right_number is not None:
            equal = left_number == right_number
        else:
            equal = left == right
        return subst if (equal if op == "eq" else not equal) else None

    left_number, right_number = _number(left), _number(right)
    if left_number is None or right_number is None:
        return None
    holds = {
        "lt": left_number < right_number,
        "lte": left_number <= right_number,
        "gt": left_number > right_number,
        "gte": left_number >= right_number,
    }[op]
    return subst if holds else None


def builtin_unsafe(rule: Rule) -> bool:
    """True when a builtin uses a variable not bound by an earlier relational atom."""
    bound: set[str] = set()
    for condition in rule.conditions:
        if is_builtin(condition.predicate):
            used = {v for v in (condition.subject, condition.object) if is_var(v)}
            if not used <= bound:
                return True
        else:
            bound |= {v for v in (condition.subject, condition.object) if is_var(v)}
    return False
