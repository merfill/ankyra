"""Symbolic verification: does ``Theory ∪ Gamma`` entail the target ``phi``?"""

from __future__ import annotations

from itertools import product

from ankyra.build.normalize import is_var
from ankyra.config.settings import get_setting
from ankyra.core.models import Fact, FactKey, Morphism, Query, Theory, Verdict
from ankyra.engine.clause import clausify, literal_of, negate
from ankyra.engine.horn import (
    AtomStore,
    GoalHit,
    assumption_explained,
    build_context,
    complementary,
    derive_closure,
    derive_store,
    has_naf,
    has_non_horn,
    match_goal,
    stratification,
    unify_pattern,
)
from ankyra.engine.inference import select_inference
from ankyra.engine.resolution import DEFAULT_BUDGET, refute


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


def _verify_horn(theory: Theory, query: Query, ctx) -> Verdict:
    """The Horn/L1 path: forward-chaining closure and single-atom targets.

    Status: ``contradiction`` when the target's own proof contains ``P ∧ ¬P``;
    ``supported`` when the target matches and every condition is used;
    ``insufficient`` when the target matches but a premise is unused; ``refuted``
    when only its negation is entailed; ``unsupported`` when nothing matches. An
    inconsistency unrelated to the target is reported as an ``inconsistent_theory:``
    gap and does not change the answer.
    """
    if has_non_horn(theory):
        # A disjunctive head/fact is out of the Horn fragment. Until the L2 procedure
        # is wired behind ANKYRA_LOGIC, report it honestly instead of guessing
        # (docs/l2_plan.md D-L2-3).
        return Verdict(
            status="out_of_fragment",
            bindings=dict(ctx.bindings),
            gaps=["out_of_fragment:non_horn"],
            shelf="refused",
        )
    if query.goal_mode != "single":
        # A conjunctive/disjunctive goal is decomposed by the L2 path (D-L2-7); the
        # Horn engine decides a single target only.
        return Verdict(
            status="out_of_fragment",
            bindings=dict(ctx.bindings),
            gaps=["out_of_fragment:compound_goal"],
            shelf="refused",
        )
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


def _logic_mode() -> str:
    return str(get_setting("LOGIC", "off") or "off").strip().lower()


def logic_enabled() -> bool:
    """True when the L2 procedure is selected (``ANKYRA_LOGIC`` is not ``off``)."""
    return _logic_mode() != "off"


def _logic_budget() -> int:
    value = get_setting("LOGIC_BUDGET", DEFAULT_BUDGET)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_BUDGET


def _ground_morphism(morphism: Morphism) -> bool:
    return not (is_var(morphism.subject) or is_var(morphism.object))


def _goals_of(query: Query) -> list[Morphism]:
    if query.goal_mode != "single" and query.goals:
        return list(query.goals)
    if query.target is not None:
        return [query.target]
    return []


def _l2_outcome(clausification, goal: Morphism) -> tuple[str, object, object]:
    """The L2 outcome of one ground goal and its proof results.

    ``supported`` (goal entailed), ``refuted`` (its negation entailed),
    ``contradiction`` (both), ``budget`` (exhausted), else ``unknown``. A proved goal
    is never downgraded by a timeout on its complement: the complement is only
    consulted for a refutation when the goal itself is not entailed, or — bounded —
    for a contradiction report when it is.
    """
    budget = _logic_budget()
    target = refute(clausification, literal_of(goal), budget=budget)
    if target.status == "entailed":
        complement = refute(
            clausification, negate(literal_of(goal)), budget=min(budget, _CONTRADICTION_BUDGET)
        )
        if complement.status == "entailed":
            return "contradiction", target, complement
        return "supported", target, complement
    if target.status == "budget":
        return "budget", target, None
    complement = refute(clausification, negate(literal_of(goal)), budget=budget)
    if complement.status == "entailed":
        return "refuted", target, complement
    if complement.status == "budget":
        return "budget", target, complement
    return "unknown", target, complement


def _witness_pool(theory: Theory, clausification) -> list[str]:
    """Ground terms the L2 procedure can use as witnesses (objects + Skolem constants)."""
    return sorted(set(build_context(theory).obj_pool) | set(clausification.skolems))


def _goal_outcome(clausification, goal: Morphism, pool: list[str]):
    """Outcome of a ground goal, or of an open goal by witness enumeration.

    An open target (``?x``) is an existential question over the finite pool: it is
    ``supported`` with the first witness, ``refuted`` when every candidate is refuted,
    ``budget`` on exhaustion, else ``unknown``. Returns
    ``(outcome, target_result, complement_result, binding)``.
    """
    if _ground_morphism(goal):
        outcome, target, complement = _l2_outcome(clausification, goal)
        return outcome, target, complement, {}
    variables = [term for term in (goal.subject, goal.object) if is_var(term)]
    tried = 0
    any_budget = False
    all_refuted = True
    for combo in product(pool, repeat=len(variables)):
        subst = dict(zip(variables, combo))
        grounded = goal.model_copy(
            update={
                "subject": subst.get(goal.subject, goal.subject),
                "object": subst.get(goal.object, goal.object),
            }
        )
        outcome, target, complement = _l2_outcome(clausification, grounded)
        tried += 1
        if outcome == "supported":
            binding = {var: value for var, value in subst.items()}
            return "supported", target, complement, binding
        if outcome == "budget":
            any_budget = True
        if outcome != "refuted":
            all_refuted = False
    if any_budget:
        return "budget", None, None, {}
    if tried and all_refuted:
        return "refuted", None, None, {}
    return "unknown", None, None, {}


def _l2_status(mode: str, kinds: list[str]) -> str:
    if "contradiction" in kinds:
        return "contradiction"
    if mode == "all":
        if kinds and all(kind == "supported" for kind in kinds):
            return "supported"
        if any(kind == "refuted" for kind in kinds):
            return "refuted"
        return "insufficient"
    if mode == "any":
        if any(kind == "supported" for kind in kinds):
            return "supported"
        if kinds and all(kind == "refuted" for kind in kinds):
            return "refuted"
        return "insufficient"
    kind = kinds[0] if kinds else "unknown"
    return {
        "supported": "supported",
        "refuted": "refuted",
        "budget": "insufficient",
        "unknown": "unsupported",
    }.get(kind, "unsupported")


def _unused_l2(theory: Theory, query: Query, proof) -> list[int]:
    """Indices of query conditions no winning proof uses (and that are not entailed)."""
    if not query.conditions or proof is None:
        return []
    used = {
        origin for key in proof.derivation() for origin in proof.origins.get(key, [])
    }
    unused: list[int] = []
    for index, condition in enumerate(query.conditions):
        if f"presupposition:{index}" in used:
            continue
        result = refute(clausify(theory), literal_of(condition), budget=_logic_budget())
        if result.status == "entailed":
            continue
        unused.append(index)
    return unused


_SHELVES = {
    "supported": "proven",
    "refuted": "refused",
    "contradiction": "refused",
    "insufficient": "attested",
    "unsupported": "refused",
    "out_of_fragment": "refused",
}

# A proved goal is enough for ``supported``; the complement is consulted only to
# *upgrade* the report to ``contradiction``, so it runs under a smaller cap.
_CONTRADICTION_BUDGET = 2000


def _verify_l2(theory: Theory, query: Query, ctx) -> Verdict:
    bindings = dict(ctx.bindings)
    clausification, outcomes = l2_outcomes(theory, query)
    if clausification.unsupported:
        return Verdict(
            status="out_of_fragment",
            bindings=bindings,
            gaps=[f"out_of_fragment:{item}" for item in clausification.unsupported],
            shelf="refused",
        )
    mode = query.goal_mode if query.goal_mode in {"all", "any"} else "single"
    status = _l2_status(mode, [outcome for _, outcome, _, _, _ in outcomes])
    gaps: list[str] = []
    if any(outcome == "budget" for _, outcome, _, _, _ in outcomes):
        gaps.append("logic_budget:exhausted")
    if status == "unsupported":
        predicate = query.target.predicate if query.target else "?"
        gaps.append(f"target_unmatched:{predicate}")
    if status == "refuted" and query.target is not None:
        gaps.append(f"target_refuted:{query.target.predicate}")
    for _, outcome, _, _, binding in outcomes:
        if outcome == "supported" and binding:
            bindings.update(binding)
            break
    if status == "supported" and mode == "single":
        target_result = outcomes[0][2]
        unused = _unused_l2(theory, query, target_result.proof if target_result else None)
        if unused:
            return Verdict(
                status="insufficient",
                bindings=bindings,
                gaps=[f"unused_premise:{query.conditions[i].predicate}" for i in unused],
                shelf="attested",
                unused_premises=unused,
            )
    return Verdict(status=status, bindings=bindings, gaps=gaps, shelf=_SHELVES[status])


def l2_outcomes(theory: Theory, query: Query):
    """Clausify and decide every goal, for the verdict and the explanation.

    Returns ``(clausification, [(goal, outcome, target_result, complement_result, binding)])``.
    """
    clausification = clausify(theory, assumptions=query.conditions)
    if clausification.unsupported:
        return clausification, []
    pool = _witness_pool(theory, clausification)
    return clausification, [
        (goal, *_goal_outcome(clausification, goal, pool)) for goal in _goals_of(query)
    ]


def verify(theory: Theory, query: Query) -> Verdict:
    """Verify the query sequent, dispatching through the ``Inference`` protocol.

    Policy (which semantics runs) lives here: with ``ANKYRA_LOGIC`` off the Horn/L1
    semantics decides; with it on, the L2 clausal semantics decides ground goals,
    decomposed conjunction/disjunction goals and open goals by witness enumeration.
    The Horn/L1 machinery (declared CWA, negation-as-failure) is deliberately not
    mixed into L2, so a closed-world NAF query under L2 is ``out_of_fragment``.
    """
    if logic_enabled() and has_naf(theory) and query.world_assumption == "closed":
        return Verdict(
            status="out_of_fragment",
            bindings=dict(build_context(theory).bindings),
            gaps=["out_of_fragment:naf_in_l2"],
            shelf="refused",
        )
    inference = select_inference(
        logic_enabled=logic_enabled(), has_goals=bool(_goals_of(query))
    )
    return inference.decide(theory, query)
