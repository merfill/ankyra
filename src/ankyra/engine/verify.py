"""Symbolic verification: does ``Theory ∪ Gamma`` entail the target ``phi``?"""

from __future__ import annotations

from ankyra.build.normalize import is_var
from ankyra.core.models import Fact, FactKey, Morphism, Query, Theory, Verdict
from ankyra.engine.horn import (
    AtomStore,
    GoalHit,
    assumption_explained,
    build_context,
    complementary,
    derive_closure,
    derive_store,
    has_naf,
    match_goal,
    stratification,
    unify_pattern,
)


def _ground(target: Morphism) -> bool:
    return not (is_var(target.subject) or is_var(target.object))


def _winning_hit(query: Query, store: AtomStore, ctx, goal=None) -> GoalHit | None:
    """The goal hit (default: the target) whose proof uses every query condition."""
    goal = goal if goal is not None else query.target
    if goal is None:
        return None
    for hit in match_goal(goal, store, ctx):
        if all(
            assumption_explained(cond, store, ctx, used=hit.fact.used)
            for cond in query.conditions
        ):
            return hit
    return None


def winning_store_hit(
    theory: Theory, query: Query, *, goal=None
) -> tuple[AtomStore, GoalHit] | None:
    """Store and winning goal hit (default: the target), else ``None``."""
    ctx = build_context(theory)
    store = derive_store(
        theory, query.conditions, ctx=ctx, world_assumption=query.world_assumption
    )
    hit = _winning_hit(query, store, ctx, goal=goal)
    if hit is None:
        return None
    return store, hit


def winning_proof(
    theory: Theory, query: Query, *, goal=None
) -> tuple[AtomStore, frozenset[FactKey]] | None:
    """Store and transitive proof keys for the goal, else ``None``."""
    result = winning_store_hit(theory, query, goal=goal)
    if result is None:
        return None
    store, hit = result
    return store, frozenset(hit.fact.used) | {hit.fact.key}


def _conflicting_pairs(store: AtomStore) -> list[tuple]:
    """Every ``P`` / ``¬P`` pair in the store, deduplicated by key set."""
    seen: set[frozenset] = set()
    pairs: list[tuple] = []
    for fact in store.facts:
        opp = complementary(store, fact)
        if opp is None:
            continue
        signature = frozenset({fact.key, opp.key})
        if signature in seen:
            continue
        seen.add(signature)
        pairs.append((fact, opp))
    return pairs


def _key_matches(goal, key: FactKey, ctx) -> bool:
    fact = Fact(
        predicate=key[0], subject=key[1], object=key[2], negated=key[3], modality=key[4]
    )
    return unify_pattern(goal, fact, ctx, {}) is not None


def _target_keys(query: Query, store: AtomStore, ctx) -> set[FactKey]:
    """Keys of any target/negated-target match plus its transitive proof."""
    if query.target is None:
        return set()
    negated_goal = query.target.model_copy(update={"negated": not query.target.negated})
    keys: set[FactKey] = set()
    for goal in (query.target, negated_goal):
        for hit in match_goal(goal, store, ctx):
            keys.add(hit.fact.key)
            keys.update(hit.fact.used)
    return keys


def verify(theory: Theory, query: Query) -> Verdict:
    """Verify the query sequent. Unused premises block support; contradictions are explicit.

    Status: ``contradiction`` when the target's own proof contains ``P ∧ ¬P``;
    ``supported`` when the target matches and every condition is used;
    ``insufficient`` when the target matches but a premise is unused; ``refuted``
    when only its negation is entailed; ``unsupported`` when nothing matches. An
    inconsistency unrelated to the target is reported as an ``inconsistent_theory:``
    gap and does not change the answer.
    """
    ctx = build_context(theory)
    if query.world_assumption == "closed" and has_naf(theory) and stratification(theory) is None:
        return Verdict(
            status="out_of_fragment",
            bindings=dict(ctx.bindings),
            gaps=["out_of_fragment:stratification"],
            shelf="refused",
        )
    axiom_store = derive_store(theory, [], ctx=ctx)
    store, unresolved, _ = derive_closure(
        theory,
        query.conditions,
        ctx=ctx,
        world_assumption=query.world_assumption,
    )
    bindings = dict(ctx.bindings)

    conflicts = _conflicting_pairs(store)
    target_keys = _target_keys(query, store, ctx)
    target_conflicts = [
        (fact, opp)
        for fact, opp in conflicts
        if fact.key in target_keys or opp.key in target_keys
    ]
    if target_conflicts:
        fact, opp = target_conflicts[0]
        return Verdict(
            status="contradiction",
            bindings=bindings,
            gaps=[f"contradiction:{fact.label()}"],
            matched=[fact.witness or fact.label(), opp.witness or opp.label()],
            shelf="refused",
        )
    inconsistent_gaps = [f"inconsistent_theory:{fact.label()}" for fact, _ in conflicts]

    if query.target is not None:
        hit = _winning_hit(query, store, ctx)
        if hit is not None:
            bindings.update(hit.subst)
            return Verdict(
                status="supported",
                bindings=bindings,
                gaps=list(inconsistent_gaps),
                matched=[hit.fact.witness or hit.fact.label()],
                shelf="proven",
            )
        hits = match_goal(query.target, store, ctx)
        if hits:
            leftover_idx = [
                i
                for i, cond in enumerate(query.conditions)
                if not assumption_explained(cond, store, ctx, used=hits[0].fact.used)
            ]
            bindings.update(hits[0].subst)
            return Verdict(
                status="insufficient",
                bindings=bindings,
                gaps=inconsistent_gaps
                + [f"unused_premise:{query.conditions[i].predicate}" for i in leftover_idx],
                matched=[hits[0].fact.witness or hits[0].fact.label()],
                shelf="attested",
                unused_premises=leftover_idx,
            )
        negated_goal = query.target.model_copy(update={"negated": not query.target.negated})
        negative_hit = _winning_hit(query, store, ctx, goal=negated_goal)
        if negative_hit is not None:
            bindings.update(negative_hit.subst)
            return Verdict(
                status="refuted",
                bindings=bindings,
                gaps=inconsistent_gaps + [f"target_refuted:{query.target.predicate}"],
                matched=[negative_hit.fact.witness or negative_hit.fact.label()],
                shelf="refused",
            )
        if query.world_assumption == "closed" and _ground(query.target):
            # Declared closed world: the positive atom is unprovable, so it is false.
            # A positive target is refuted; a negated target ("not P") is supported.
            positive = query.target.model_copy(update={"negated": False})
            witness = f"naf:{positive.predicate}({positive.subject},{positive.object})"
            if query.target.negated:
                return Verdict(
                    status="supported",
                    bindings=bindings,
                    gaps=inconsistent_gaps,
                    matched=[witness],
                    shelf="proven",
                )
            return Verdict(
                status="refuted",
                bindings=bindings,
                gaps=inconsistent_gaps + [f"target_refuted:{query.target.predicate}"],
                matched=[witness],
                shelf="refused",
            )
        gaps = inconsistent_gaps + [f"target_unmatched:{query.target.predicate}"]
        if any(
            _key_matches(query.target, key, ctx) or _key_matches(negated_goal, key, ctx)
            for key in unresolved
        ):
            gaps.append(f"undecided_conflict:{query.target.predicate}")
    else:
        gaps = list(inconsistent_gaps)

    matched: list[str] = []
    cond_results: list[bool] = []
    for cond in query.conditions:
        hits = match_goal(cond, axiom_store, ctx)
        ok = bool(hits)
        cond_results.append(ok)
        if ok:
            matched.append(hits[0].fact.witness or hits[0].fact.label())
        else:
            gaps.append(f"condition_unmatched:{cond.predicate}")

    all_conds = bool(cond_results) and all(cond_results)
    any_cond = any(cond_results) if cond_results else False

    if query.target is None:
        if all_conds:
            status, shelf = "supported", "proven"
        elif any_cond:
            status, shelf = "insufficient", "attested"
        else:
            status, shelf = "unsupported", "refused"
    elif any_cond:
        status, shelf = "insufficient", "attested"
    else:
        status, shelf = "unsupported", "refused"

    return Verdict(status=status, bindings=bindings, gaps=gaps, matched=matched, shelf=shelf)
