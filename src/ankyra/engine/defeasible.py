"""Defeasible (non-monotonic) effective closure, behind ``ANKYRA_DEFEASIBLE``.

Strict rules keep the monotone Horn closure. A defeasible rule fires only when its
head does not contradict a strict fact (negation as failure: strict overrides any
default) and is not defeated by a strictly more specific conflicting rule.
Specificity compares the class atoms of the two rule applications through the
strict ``is_a`` order. A conflict specificity cannot decide (the Nixon diamond) is
accepted by neither branch, so the goal stays unknown.
"""

from __future__ import annotations

from dataclasses import dataclass

from ankyra.core.models import Fact, FactKey, Morphism, Rule, Theory
from ankyra.engine.horn import (
    AtomStore,
    TheoryContext,
    _match_conditions,
    build_context,
    instantiate,
    saturate,
)

_MAX_ITERATIONS = 64


@dataclass
class Candidate:
    """One grounded application of a defeasible rule."""

    rule_index: int
    head: Fact
    body_facts: list[Fact]


@dataclass
class Defeat:
    """A resolved conflict: ``winner`` is strictly more specific than ``loser``."""

    winner: Candidate
    loser: Candidate
    reason: str


@dataclass
class Undecided:
    """A conflict specificity cannot decide, with the competing candidates."""

    candidates: list[Candidate]
    reason: str


def _clone(store: AtomStore) -> AtomStore:
    copy = AtomStore()
    for fact in store.facts:
        copy.add(fact)
    return copy


def _with(strict: AtomStore, accepted: dict[FactKey, Candidate]) -> AtomStore:
    store = _clone(strict)
    for candidate in accepted.values():
        store.add(candidate.head)
    return store


def _negated_key(key: FactKey) -> FactKey:
    return (key[0], key[1], key[2], not key[3], key[4])


def _is_a_order(store: AtomStore) -> dict[str, set[str]]:
    """Transitive ``is_a`` ancestors over neutral positive edges."""
    edges: dict[str, set[str]] = {}
    for fact in store.facts:
        if fact.predicate == "is_a" and not fact.negated and fact.modality == "neutral":
            edges.setdefault(fact.subject, set()).add(fact.object)
    changed = True
    while changed:
        changed = False
        for child in list(edges):
            for parent in list(edges[child]):
                for ancestor in edges.get(parent, ()):
                    if ancestor not in edges[child]:
                        edges[child].add(ancestor)
                        changed = True
    return edges


def _class_atoms(candidate: Candidate) -> list[tuple[str, str]]:
    return [
        (fact.subject, fact.object)
        for fact in candidate.body_facts
        if fact.predicate == "is_a" and not fact.negated and fact.modality == "neutral"
    ]


def _specificity_witness(
    more: Candidate, less: Candidate, order: dict[str, set[str]]
) -> tuple[str, str] | None:
    """The ``(more_class, less_class)`` pair proving ``more`` is more specific."""
    for more_subject, more_class in _class_atoms(more):
        for less_subject, less_class in _class_atoms(less):
            if more_subject != less_subject:
                continue
            if less_class in order.get(more_class, set()) and more_class not in order.get(
                less_class, set()
            ):
                return more_class, less_class
    return None


def specificity(more: Candidate, less: Candidate, order: dict[str, set[str]]) -> bool:
    """True when ``more`` is strictly more specific than ``less`` via ``is_a``.

    The compared class atoms must share their subject (the same individual); if no
    comparable class pair exists the relation is undecided and this returns False.
    """
    return _specificity_witness(more, less, order) is not None


def _classes(candidates: list[Candidate]) -> list[str]:
    seen: list[str] = []
    for candidate in candidates:
        for _, class_id in _class_atoms(candidate):
            if class_id not in seen:
                seen.append(class_id)
    return seen


def _undecided_reason(group: list[Candidate], opponents: list[Candidate]) -> str:
    left, right = _classes(group), _classes(opponents)
    if left and right:
        return f"no is_a relation decides between {', '.join(left)} and {', '.join(right)}"
    return "specificity cannot decide between the competing defaults"


def _candidates(
    rules: list[tuple[int, Rule]],
    store: AtomStore,
    ctx: TheoryContext,
    *,
    world_assumption: str = "open",
) -> list[Candidate]:
    out: list[Candidate] = []
    for index, rule in rules:
        if not rule.conditions:
            continue
        for subst, used_facts in _match_conditions(
            rule.conditions, store.facts, ctx, {}, world_assumption=world_assumption
        ):
            head = instantiate(rule.consequence, ctx, subst)
            if head is None:
                continue
            head.premises = frozenset(fact.key for fact in used_facts)
            used: set[FactKey] = set()
            for fact in used_facts:
                used.add(fact.key)
                used.update(fact.used)
            head.used = frozenset(used)
            head.rule_index = index
            head.witness = f"rule:{index}:=>{head.label()}"
            out.append(Candidate(rule_index=index, head=head, body_facts=list(used_facts)))
    return out


def _resolve(
    candidates: list[Candidate], strict: AtomStore, order: dict[str, set[str]]
) -> tuple[dict[FactKey, Candidate], dict[FactKey, Undecided], list[Defeat]]:
    """Resolve every conflicting pair; accept a side only when it clearly wins.

    Returns the accepted heads, the pairs specificity cannot decide (with the
    competing candidates of both polarities), and the resolved defeats with the
    ``is_a`` witness that decided them.
    """
    groups: dict[FactKey, list[Candidate]] = {}
    for candidate in candidates:
        groups.setdefault(candidate.head.key, []).append(candidate)

    accepted: dict[FactKey, Candidate] = {}
    unresolved: dict[FactKey, Undecided] = {}
    defeats: list[Defeat] = []
    processed: set[frozenset] = set()
    for key, group in groups.items():
        opposite = _negated_key(key)
        pair = frozenset({key, opposite})
        if pair in processed:
            continue
        processed.add(pair)
        if opposite in strict.by_key or key in strict.by_key:
            continue
        opponents = groups.get(opposite, [])
        survivors = [c for c in group if not any(specificity(o, c, order) for o in opponents)]
        opposite_survivors = [
            c for c in opponents if not any(specificity(o, c, order) for o in group)
        ]
        if survivors and not opposite_survivors:
            winner = survivors[0]
            accepted[key] = winner
            for loser in opponents:
                witness = _specificity_witness(winner, loser, order)
                if witness is not None:
                    defeats.append(
                        Defeat(winner, loser, f"{witness[0]} is-a {witness[1]}")
                    )
        elif opposite_survivors and not survivors:
            winner = opposite_survivors[0]
            accepted[opposite] = winner
            for loser in group:
                witness = _specificity_witness(winner, loser, order)
                if witness is not None:
                    defeats.append(
                        Defeat(winner, loser, f"{witness[0]} is-a {witness[1]}")
                    )
        elif survivors or opposite_survivors:
            reason = _undecided_reason(group, opponents)
            unresolved[key] = Undecided(survivors, reason)
            unresolved[opposite] = Undecided(opposite_survivors, reason)
        else:
            reason = _undecided_reason(group, opponents)
            unresolved[key] = Undecided(list(group), reason)
            unresolved[opposite] = Undecided(list(opponents), reason)
    return accepted, unresolved, defeats


def effective_closure(
    theory: Theory,
    assumptions: list[Morphism] | None = None,
    *,
    ctx: TheoryContext | None = None,
    world_assumption: str = "open",
) -> tuple[AtomStore, dict[FactKey, Undecided], list[Defeat]]:
    """Strict closure plus accepted defaults, to a bounded alternating fixpoint.

    The second value holds the conflicts left undecided (so the caller can report
    ``undecided_conflict`` and show both branches); the third holds the resolved
    defeats and the ``is_a`` witness that decided each one.
    """
    ctx = ctx or build_context(theory)
    strict = saturate(
        theory, assumptions, ctx=ctx, strengths={"strict"}, world_assumption=world_assumption
    )
    defeasible_rules = [
        (index, rule)
        for index, rule in enumerate(theory.rules, 1)
        if rule.strength == "defeasible" and rule.conditions
    ]
    if not defeasible_rules:
        return strict, {}, []

    accepted: dict[FactKey, Candidate] = {}
    unresolved: dict[FactKey, Undecided] = {}
    defeats: list[Defeat] = []
    for _ in range(_MAX_ITERATIONS):
        base = _with(strict, accepted)
        order = _is_a_order(base)
        candidates = _candidates(defeasible_rules, base, ctx, world_assumption=world_assumption)
        updated, unresolved, defeats = _resolve(candidates, strict, order)
        signature = {key: candidate.rule_index for key, candidate in updated.items()}
        if signature == {key: candidate.rule_index for key, candidate in accepted.items()}:
            accepted = updated
            break
        accepted = updated
    return _with(strict, accepted), unresolved, defeats


def effective_store(
    theory: Theory,
    assumptions: list[Morphism] | None = None,
    *,
    ctx: TheoryContext | None = None,
) -> AtomStore:
    """Strict closure plus accepted defaults (the store alone)."""
    store, _, _ = effective_closure(theory, assumptions, ctx=ctx)
    return store
