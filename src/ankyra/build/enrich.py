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


def heal_structural(rules: list[Rule]) -> list[Rule]:
    """Drop a rule premise that negates its own consequence; keep the rest.

    A conflict with an axiom is NOT healed here: it is a real contradiction and
    must reach the engine, where it is reported instead of silently dropped.
    """
    out: list[Rule] = []
    for rule in rules:
        consequence = rule.consequence
        kept = [cond for cond in rule.conditions if _key(cond) != _negation_key(consequence)]
        if rule.conditions and not kept:
            continue
        if len(kept) != len(rule.conditions):
            rule = rule.model_copy(update={"conditions": kept})
        out.append(rule)
    return out


def enrich_theory(theory: Theory) -> Theory:
    """Normalize polarity, dedupe, and hygienically clean rules — no LLM.

    Rule consequences are not materialized into axioms (that would hide the rule
    from the explanation), and contradictory axioms are not collapsed (that would
    hide a contradiction from the engine).
    """
    ids = sorted(obj.id for obj in theory.objects if obj.id.strip())
    rewritten_morphisms = [_rewrite_morphism(m) for m in theory.morphisms]
    morphisms = _dedupe_morphisms([m for m in rewritten_morphisms if _valid_morphism(m)])
    rewritten_rules = [_rewrite_rule(r) for r in theory.rules]
    rules = _dedupe_rules([r for r in rewritten_rules if _valid_rule(r)])
    rules = heal_structural(rules)

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
