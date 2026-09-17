"""Deterministic enrichment after structural unroll (no LLM)."""

from __future__ import annotations

from ankyra.build.normalize import predicate_polarity
from ankyra.core.models import Morphism, Object, Rule, Theory


def _key(morphism: Morphism) -> tuple:
    return (morphism.predicate, morphism.subject, morphism.object, morphism.negated, morphism.modality)


def _negation_key(morphism: Morphism) -> tuple:
    return (morphism.predicate, morphism.subject, morphism.object, not morphism.negated, morphism.modality)


def _rewrite_morphism(morphism: Morphism) -> Morphism:
    predicate, negated = predicate_polarity(morphism.predicate, morphism.negated)
    if predicate == morphism.predicate and negated == morphism.negated:
        return morphism
    return morphism.model_copy(update={"predicate": predicate, "negated": negated})


def _valid_morphism(morphism: Morphism) -> bool:
    """An atom without a predicate is malformed (bad extraction) and is dropped."""
    return bool((morphism.predicate or "").strip())


def _valid_rule(rule: Rule) -> bool:
    """A rule is dropped when any of its atoms is malformed."""
    if not (rule.consequence.predicate or "").strip():
        return False
    return all((condition.predicate or "").strip() for condition in rule.conditions)


def _dedupe_morphisms(morphisms: list[Morphism]) -> list[Morphism]:
    seen: dict[tuple, int] = {}
    out: list[Morphism] = []
    for morphism in morphisms:
        key = _key(morphism)
        if key in seen:
            index = seen[key]
            if not (out[index].quote or "").strip() and (morphism.quote or "").strip():
                out[index] = morphism
            continue
        seen[key] = len(out)
        out.append(morphism)
    return out


def _rewrite_rule(rule: Rule) -> Rule:
    return rule.model_copy(
        update={
            "conditions": _dedupe_morphisms([_rewrite_morphism(c) for c in rule.conditions]),
            "consequence": _rewrite_morphism(rule.consequence),
        }
    )


def _dedupe_rules(rules: list[Rule]) -> list[Rule]:
    seen: set[str] = set()
    out: list[Rule] = []
    for rule in rules:
        signature = repr(rule.model_dump())
        if signature in seen:
            continue
        seen.add(signature)
        out.append(rule)
    return out


def _iter_rule_morphisms(rules: list[Rule]) -> list[Morphism]:
    out: list[Morphism] = []
    for rule in rules:
        out.extend(rule.conditions)
        out.append(rule.consequence)
    return out


def materialize_rule_morphisms(morphisms: list[Morphism], rules: list[Rule]) -> list[Morphism]:
    """Forward-chain: when every condition is already a fact, add the consequence.

    Only derived axioms are materialized — not every rule atom, which would make
    verify treat rule-only slots as unconditionally true.
    """
    facts = list(morphisms)
    keys = {_key(m) for m in facts}
    changed = True
    guard = 0
    while changed and guard < 32:
        changed = False
        guard += 1
        for rule in rules:
            if not rule.conditions:
                continue
            if any(_key(cond) not in keys for cond in rule.conditions):
                continue
            cons_key = _key(rule.consequence)
            if cons_key in keys:
                continue
            added = rule.consequence
            if not (added.quote or "").strip() and (rule.quote or "").strip():
                added = added.model_copy(update={"quote": rule.quote})
            facts.append(added)
            keys.add(cons_key)
            changed = True
    return facts


def heal_structural(morphisms: list[Morphism], rules: list[Rule]) -> list[Rule]:
    """Drop rules that can only fire into a contradiction with existing facts.

    - a rule concluding the opposite of an existing axiom is dropped;
    - a rule whose premise negates its own consequence has that premise removed,
      and is dropped if nothing remains.
    """
    axiom_keys = {_key(m) for m in morphisms}
    out: list[Rule] = []
    for rule in rules:
        consequence = rule.consequence
        if _negation_key(consequence) in axiom_keys:
            continue
        kept = [cond for cond in rule.conditions if _key(cond) != _negation_key(consequence)]
        if rule.conditions and not kept:
            continue
        if len(kept) != len(rule.conditions):
            rule = rule.model_copy(update={"conditions": kept})
        out.append(rule)
    return out


def heal_contradictory_axioms(morphisms: list[Morphism]) -> list[Morphism]:
    """If both ``P`` and ``¬P`` are asserted, keep the positive reading."""
    by_key: dict[tuple, Morphism] = {}
    for morphism in morphisms:
        by_key.setdefault(_key(morphism), morphism)
    out: list[Morphism] = []
    seen: set[tuple] = set()
    for morphism in by_key.values():
        key = _key(morphism)
        if key in seen:
            continue
        opposite = _negation_key(morphism)
        if opposite in by_key:
            positive = morphism if not morphism.negated else by_key[opposite]
            positive_key = _key(positive)
            if positive_key not in seen:
                seen.add(positive_key)
                out.append(positive)
            continue
        seen.add(key)
        out.append(morphism)
    return out


def enrich_theory(theory: Theory) -> Theory:
    """Normalize polarity, dedupe, materialize, and heal — no LLM."""
    ids = sorted(obj.id for obj in theory.objects if obj.id.strip())
    rewritten_morphisms = [_rewrite_morphism(m) for m in theory.morphisms]
    morphisms = _dedupe_morphisms([m for m in rewritten_morphisms if _valid_morphism(m)])
    rewritten_rules = [_rewrite_rule(r) for r in theory.rules]
    rules = _dedupe_rules([r for r in rewritten_rules if _valid_rule(r)])

    rules = heal_structural(morphisms, rules)
    morphisms = _dedupe_morphisms(materialize_rule_morphisms(morphisms, rules))
    rules = heal_structural(morphisms, rules)
    morphisms = heal_contradictory_axioms(morphisms)
    morphisms = _dedupe_morphisms(morphisms)

    for morphism in [*morphisms, *_iter_rule_morphisms(rules)]:
        if morphism.subject and morphism.subject not in ids:
            ids.append(morphism.subject)
        if morphism.object and morphism.object not in ids:
            ids.append(morphism.object)

    return theory.model_copy(
        update={
            "objects": [Object(id=oid) for oid in ids],
            "morphisms": morphisms,
            "rules": rules,
        }
    )
