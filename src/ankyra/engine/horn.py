"""Deterministic Horn engine: unification, forward chaining, subsumption.

The engine is the spine of Ankyra: it derives and verifies but never adds
knowledge. Every derived atom carries provenance (``used`` / ``witness`` /
``rule_index``) so the explanation can later be built mechanically.
"""

from __future__ import annotations

from dataclasses import dataclass

from ankyra.build.normalize import is_var, predicate_polarity
from ankyra.core.models import Fact, FactKey, Morphism, Theory
from ankyra.engine.builtins import evaluate, is_builtin

Subst = dict[str, str]


def _bare(value: str) -> str:
    return value[1:] if value.startswith("?") else value


@dataclass
class TheoryContext:
    """Resolved vocabulary of a theory plus the query bindings."""

    theory: Theory
    obj_pool: set[str]
    pred_pool: set[str]
    bindings: Subst


@dataclass
class GoalHit:
    """A fact that matches a goal, with the substitution that matched it."""

    fact: Fact
    subst: Subst


def _all_slots(theory: Theory):
    """Axioms and every rule slot — the theory's full relational vocabulary."""
    yield from theory.morphisms
    for rule in theory.rules:
        yield from rule.conditions
        yield from rule.head


def _object_pool(theory: Theory) -> set[str]:
    pool = {o.id for o in theory.objects if o.id}
    for m in _all_slots(theory):
        if m.subject:
            pool.add(m.subject)
        if m.object:
            pool.add(m.object)
    for constraint in theory.constraints:
        for class_id in (constraint.left, constraint.right):
            if class_id:
                pool.add(class_id)
    return {p for p in pool if p}


def _predicate_pool(theory: Theory) -> set[str]:
    return {m.predicate for m in _all_slots(theory) if m.predicate}


def build_context(theory: Theory, *, bindings: Subst | None = None) -> TheoryContext:
    raw = dict(bindings or {})
    env: Subst = {}
    for key, val in raw.items():
        env[key] = val
        env[_bare(key)] = val
        if not key.startswith("?"):
            env[f"?{key}"] = val
    return TheoryContext(
        theory=theory,
        obj_pool=_object_pool(theory),
        pred_pool=_predicate_pool(theory),
        bindings=env,
    )


def _pool_lookup(value: str, pool: set[str]) -> str | None:
    needle = value.casefold()
    for item in pool:
        if item.casefold() == needle:
            return item.casefold()
    return None


def resolve_term(
    value: str | None,
    ctx: TheoryContext,
    *,
    field: str,
    subst: Subst | None = None,
) -> str:
    if not value:
        return ""
    env = subst or {}
    cur = value
    seen: set[str] = set()
    while cur not in seen:
        seen.add(cur)
        nxt = (
            env.get(cur)
            or env.get(_bare(cur))
            or ctx.bindings.get(cur)
            or ctx.bindings.get(_bare(cur))
        )
        if not nxt or nxt == cur:
            break
        cur = nxt
    if is_var(cur):
        hit = _pool_lookup(_bare(cur), ctx.obj_pool if field != "predicate" else ctx.pred_pool)
        if hit:
            return hit
        return cur
    if field == "predicate":
        pred, _ = predicate_polarity(cur, False)
        return _pool_lookup(pred, ctx.pred_pool) or pred.casefold()
    return _pool_lookup(cur, ctx.obj_pool) or cur.casefold()


def unify_terms(left: str, right: str, subst: Subst) -> Subst | None:
    """Unify two already-resolved terms. Empty left is a pattern wildcard."""
    env = dict(subst)
    a = env.get(left, left)
    b = env.get(right, right)
    if not a:
        return env
    if a == b:
        return env
    if is_var(a):
        env[a] = b
        env[_bare(a)] = b
        return env
    if is_var(b):
        env[b] = a
        env[_bare(b)] = a
        return env
    return None


def unify_pattern(pattern: Morphism, fact: Fact, ctx: TheoryContext, subst: Subst) -> Subst | None:
    """Match a morphism pattern against a ground fact.

    Polarity, modality and negation must agree; modality is part of atom identity
    so a neutral pattern never matches an obligation fact.

    The builtin extension point: builtins are evaluated as filters in
    ``_match_conditions``, never matched against facts, so they match nothing here.
    """
    if is_builtin(pattern.predicate):
        return None
    _, pat_neg = predicate_polarity(pattern.predicate, pattern.negated)
    if pat_neg != fact.negated:
        return None
    if pattern.modality != fact.modality:
        return None
    env = dict(subst)
    pred = resolve_term(pattern.predicate, ctx, field="predicate", subst=env)
    merged = unify_terms(pred, fact.predicate, env)
    if merged is None:
        return None
    env = merged
    subj = resolve_term(pattern.subject, ctx, field="object", subst=env)
    merged = unify_terms(subj, fact.subject, env)
    if merged is None:
        return None
    env = merged
    obj = resolve_term(pattern.object, ctx, field="object", subst=env)
    return unify_terms(obj, fact.object, env)


def instantiate(pattern: Morphism, ctx: TheoryContext, subst: Subst) -> Fact | None:
    """Ground a pattern under a substitution; ``None`` if a term is still free."""
    pred = resolve_term(pattern.predicate, ctx, field="predicate", subst=subst)
    subj = resolve_term(pattern.subject, ctx, field="object", subst=subst)
    obj = resolve_term(pattern.object, ctx, field="object", subst=subst)
    if not pred or is_var(pred) or is_var(subj) or is_var(obj):
        return None
    _, negated = predicate_polarity(pattern.predicate, pattern.negated)
    return Fact(
        predicate=pred,
        subject=subj,
        object=obj,
        negated=negated,
        modality=pattern.modality,
    )


class AtomStore:
    """Deduplicated ground atoms keyed by ``FactKey``."""

    def __init__(self) -> None:
        self.by_key: dict[FactKey, Fact] = {}
        self.facts: list[Fact] = []

    def add(self, fact: Fact) -> bool:
        old = self.by_key.get(fact.key)
        if old is None:
            self.by_key[fact.key] = fact
            self.facts.append(fact)
            return True
        if fact.axiom and not old.axiom:
            self._replace(old, fact)
            return True
        if (not old.axiom) and len(fact.used) < len(old.used):
            self._replace(old, fact)
            return True
        return False

    def _replace(self, old: Fact, new: Fact) -> None:
        self.by_key[new.key] = new
        self.facts[self.facts.index(old)] = new

    def get(self, key: FactKey) -> Fact | None:
        return self.by_key.get(key)


def _seed_fact(morphism: Morphism, ctx: TheoryContext, *, axiom: bool) -> Fact | None:
    fact = instantiate(morphism, ctx, {})
    if fact is None:
        return None
    fact.axiom = axiom
    fact.witness = fact.label()
    if not axiom:
        fact.used = frozenset({fact.key})
    return fact


def _negative_holds(
    positive: Morphism, facts: list[Fact], ctx: TheoryContext, env: Subst
) -> bool | None:
    """NAF check: does ``¬positive`` hold by failure of ``positive``?

    ``None`` means the literal is unsafe (a variable is unbound at this point), so
    the rule cannot fire. Otherwise the literal holds iff no fact derives the
    positive atom under ``env`` (closed world only).
    """
    pred = resolve_term(positive.predicate, ctx, field="predicate", subst=env)
    subj = resolve_term(positive.subject, ctx, field="object", subst=env)
    obj = resolve_term(positive.object, ctx, field="object", subst=env)
    if is_var(pred) or is_var(subj) or is_var(obj):
        return None
    for fact in facts:
        if unify_pattern(positive, fact, ctx, env) is not None:
            return False
    return True


def _match_conditions(
    conditions: list[Morphism],
    facts: list[Fact],
    ctx: TheoryContext,
    subst: Subst,
    *,
    world_assumption: str = "open",
) -> list[tuple[Subst, list[Fact]]]:
    if not conditions:
        return [(dict(subst), [])]

    def rec(index: int, env: Subst, used_facts: list[Fact]) -> list[tuple[Subst, list[Fact]]]:
        if index >= len(conditions):
            return [(dict(env), list(used_facts))]
        condition = conditions[index]
        if is_builtin(condition.predicate):
            merged = evaluate(condition, env)
            if merged is None:
                return []
            return rec(index + 1, merged, used_facts)
        if condition.negated and world_assumption == "closed":
            # Negation-as-failure: `not P` holds iff P is not derivable.
            positive = condition.model_copy(update={"negated": False})
            holds = _negative_holds(positive, facts, ctx, env)
            if not holds:
                return []  # failure, or unsafe literal
            return rec(index + 1, env, used_facts)
        out: list[tuple[Subst, list[Fact]]] = []
        for fact in facts:
            merged = unify_pattern(condition, fact, ctx, env)
            if merged is None:
                continue
            out.extend(rec(index + 1, merged, used_facts + [fact]))
        return out

    return rec(0, subst, [])


def has_naf(theory: Theory) -> bool:
    """True when a rule body contains a negation-as-failure literal."""
    return any(
        condition.negated and not is_builtin(condition.predicate)
        for rule in theory.rules
        for condition in rule.conditions
    )


def has_non_horn(theory: Theory) -> bool:
    """True when the theory contains a non-Horn clause (a disjunctive head/fact).

    Such a clause is out of the Horn fragment: the forward chain must not fire it
    (``_fire_rules`` skips non-Horn rules), and ``verify`` reports the theory
    ``out_of_fragment`` unless the L2 procedure is enabled (``docs/l2_plan.md``).
    """
    return any(not rule.is_horn for rule in theory.rules)


def stratification(theory: Theory) -> dict[str, int] | None:
    """Stratify predicate symbols for NAF, or ``None`` when not stratifiable.

    A positive body dependency requires ``head >= body``; a negative body literal
    requires ``head >= body + 1``. A convergent assignment exists iff no cycle
    contains a negative edge; otherwise the program is outside L1 and the caller
    reports ``out_of_fragment`` (docs/l1_plan.md D-L1-2).
    """
    predicates: set[str] = set()
    edges: list[tuple[str, str, bool]] = []
    for rule in theory.rules:
        head = rule.consequence.predicate
        if not head:
            continue
        predicates.add(head)
        for condition in rule.conditions:
            if not condition.predicate or is_builtin(condition.predicate):
                continue
            predicates.add(condition.predicate)
            edges.append((condition.predicate, head, bool(condition.negated)))
    strata = {name: 0 for name in predicates}
    for _ in range(len(predicates) + 1):
        changed = False
        for body, head, negative in edges:
            required = strata[body] + (1 if negative else 0)
            if strata[head] < required:
                strata[head] = required
                changed = True
        if not changed:
            return strata
    return None


def saturate(
    theory: Theory,
    assumptions: list[Morphism] | None = None,
    *,
    ctx: TheoryContext | None = None,
    max_iterations: int = 64,
    strengths: set[str] | None = None,
    world_assumption: str = "open",
) -> AtomStore:
    """Forward-chain until a fixed point. Axioms, then assumptions, then rules.

    ``strengths`` restricts firing to rules of those strengths (``rule_index`` still
    indexes the full ``theory.rules`` list, so provenance stays valid).

    Under a closed world with NAF, rules are evaluated stratum by stratum so a
    negative literal only sees fully-computed lower strata (stratified negation).
    """
    ctx = ctx or build_context(theory)
    store = AtomStore()
    for morphism in theory.morphisms:
        fact = _seed_fact(morphism, ctx, axiom=True)
        if fact is not None:
            store.add(fact)
    for morphism in assumptions or ():
        fact = _seed_fact(morphism, ctx, axiom=False)
        if fact is None:
            continue
        if fact.key in store.by_key and store.by_key[fact.key].axiom:
            continue
        store.add(fact)

    naf = world_assumption == "closed" and has_naf(theory)
    if naf:
        strata = stratification(theory) or {}
        for stratum in sorted(set(strata.values())) or [0]:
            _fire_rules(
                store,
                theory,
                ctx,
                max_iterations,
                strengths,
                world_assumption,
                strata,
                stratum,
            )
    else:
        _fire_rules(
            store, theory, ctx, max_iterations, strengths, world_assumption, None, None
        )
    return store


def _fire_rules(
    store: AtomStore,
    theory: Theory,
    ctx: TheoryContext,
    max_iterations: int,
    strengths: set[str] | None,
    world_assumption: str,
    strata: dict[str, int] | None,
    allowed_stratum: int | None,
) -> None:
    for _ in range(max_iterations):
        progressed = False
        snapshot = list(store.facts)
        for i, rule in enumerate(theory.rules, 1):
            if not rule.conditions:
                continue
            if not rule.is_horn:
                # A disjunctive head is not Horn: deriving its first disjunct would be
                # unsound. The L2 procedure handles it (docs/l2_plan.md D-L2-3).
                continue
            if strengths is not None and rule.strength not in strengths:
                continue
            if allowed_stratum is not None and (strata or {}).get(
                rule.consequence.predicate, 0
            ) != allowed_stratum:
                continue
            for subst, used_facts in _match_conditions(
                rule.conditions, snapshot, ctx, {}, world_assumption=world_assumption
            ):
                derived = instantiate(rule.consequence, ctx, subst)
                if derived is None:
                    continue
                # Direct premises for the explanation; `used` is the transitive
                # closure for hypothesis accounting.
                derived.premises = frozenset(used_fact.key for used_fact in used_facts)
                used: set[FactKey] = set()
                for used_fact in used_facts:
                    used.add(used_fact.key)
                    used.update(used_fact.used)
                derived.used = frozenset(used)
                derived.rule_index = i
                derived.witness = f"rule:{i}:=>{derived.label()}"
                if store.add(derived):
                    progressed = True
        if _close_is_a(store):
            progressed = True
        if _apply_constraints(store, theory):
            progressed = True
        if not progressed:
            break


def _apply_constraints(store: AtomStore, theory: Theory) -> bool:
    """Strict disjointness: ``is_a(a, C)`` and ``disjoint(C, D)`` yield ``¬is_a(a, D)``.

    A disjointness axiom is classical (``¬∃x(C(x) ∧ D(x))``), so one side holding
    entails the negation of the other. Monotone and terminating; if the other side
    also becomes derivable later, the caller reports a real contradiction.
    """
    if not theory.constraints:
        return False
    progressed = False
    for constraint in theory.constraints:
        left, right = constraint.left.casefold(), constraint.right.casefold()
        for fact in list(store.facts):
            if (
                fact.predicate != "is_a"
                or fact.negated
                or fact.modality != "neutral"
                or not fact.subject
                or not fact.object
            ):
                continue
            obj = fact.object.casefold()
            if obj == left:
                other = constraint.right
            elif obj == right:
                other = constraint.left
            else:
                continue
            derived = Fact(
                predicate="is_a",
                subject=fact.subject,
                object=other,
                negated=True,
                modality="neutral",
                used=frozenset(fact.used) | {fact.key},
                premises=frozenset({fact.key}),
                witness=f"disjoint:{constraint.left}|{constraint.right}",
            )
            if store.add(derived):
                progressed = True
    return progressed


def _close_is_a(store: AtomStore) -> bool:
    """Transitive closure of neutral, positive ``is_a`` facts (subsumption chain).

    ``is_a(a, b)`` and ``is_a(b, c)`` yield ``is_a(a, c)`` so direct subsumption
    questions match. Bounded: fixpoint over the finite fact set, no reflexivity.
    """
    progressed = False
    edges: dict[tuple[str, str], Fact] = {}
    for fact in store.facts:
        if fact.predicate == "is_a" and not fact.negated and fact.modality == "neutral":
            if fact.subject and fact.object:
                edges[(fact.subject, fact.object)] = fact
    changed = True
    while changed:
        changed = False
        keys = list(edges)
        for x, y in keys:
            fxy = edges[(x, y)]
            for y2, z in keys:
                if y != y2 or x == z:
                    continue
                if (x, z) in edges:
                    continue
                fyz = edges[(y2, z)]
                used = set(fxy.used) | {fxy.key} | set(fyz.used) | {fyz.key}
                derived = Fact(
                    predicate="is_a",
                    subject=x,
                    object=z,
                    negated=False,
                    modality="neutral",
                    used=frozenset(used),
                    premises=frozenset({fxy.key, fyz.key}),
                    witness=f"is_a:({x}->{y}->{z})",
                )
                if store.add(derived):
                    edges[(x, z)] = derived
                    changed = True
                    progressed = True
    return progressed


def derive_closure(
    theory: Theory,
    assumptions: list[Morphism] | None = None,
    *,
    ctx: TheoryContext | None = None,
    world_assumption: str = "open",
) -> tuple[AtomStore, dict, list]:
    """Strict closure, or the defeasible effective closure when enabled.

    Returns the store and, when defeasible, the undecided conflict candidates and
    the resolved defeats. The single entry point shared by ``verify``,
    ``winning_store_hit`` and ``frontier`` so the engine and the explanation never
    disagree on the store.
    """
    from ankyra.config.settings import get_setting

    if bool(get_setting("DEFEASIBLE", False)):
        from ankyra.engine.defeasible import effective_closure

        return effective_closure(
            theory, assumptions, ctx=ctx, world_assumption=world_assumption
        )
    return (
        saturate(theory, assumptions, ctx=ctx, world_assumption=world_assumption),
        {},
        [],
    )


def derive_store(
    theory: Theory,
    assumptions: list[Morphism] | None = None,
    *,
    ctx: TheoryContext | None = None,
    world_assumption: str = "open",
) -> AtomStore:
    """The store alone (see ``derive_closure``)."""
    store, _, _ = derive_closure(
        theory, assumptions, ctx=ctx, world_assumption=world_assumption
    )
    return store


def frontier(theory: Theory) -> list[str]:
    """Labels of the derived (non-axiom) facts of a theory's closure."""
    return [fact.label() for fact in derive_store(theory).facts if not fact.axiom]


def _slot_label(morphism: Morphism, grounded: Fact | None) -> str:
    if grounded is not None:
        return grounded.label()
    neg = "NOT " if morphism.negated else ""
    mod = "" if morphism.modality == "neutral" else f"{morphism.modality}:"
    args = [a for a in (morphism.subject, morphism.object) if a]
    return f"{neg}{mod}{morphism.predicate}({','.join(args)})"


def near_miss(theory: Theory, target: Morphism | None, *, limit: int = 8) -> list[str]:
    """Partially-matched rules relevant to the goal, with their unmet body literals.

    Deterministic abduction hint: for every rule whose head can match the goal or
    the goal's complement, ground the head and report the rules whose body is only
    partly satisfied in the current closure together with the grounded literals the
    closure lacks. The engine names *what* is missing; a proposal only supplies it.
    """
    if target is None:
        return []
    ctx = build_context(theory)
    goal = instantiate(target, ctx, {})
    if goal is None:
        return []
    variants = [
        goal,
        Fact(
            predicate=goal.predicate,
            subject=goal.subject,
            object=goal.object,
            negated=not goal.negated,
            modality=goal.modality,
        ),
    ]
    store = derive_store(theory)
    hints: list[str] = []
    seen: set[str] = set()
    for index, rule in enumerate(theory.rules, 1):
        if not rule.conditions:
            continue
        for variant in variants:
            subst = unify_pattern(rule.consequence, variant, ctx, {})
            if subst is None:
                continue
            head = instantiate(rule.consequence, ctx, subst)
            if head is None:
                continue
            unmet: list[str] = []
            matched = 0
            for condition in rule.conditions:
                grounded = instantiate(condition, ctx, subst)
                if grounded is not None and store.get(grounded.key) is not None:
                    matched += 1
                else:
                    unmet.append(_slot_label(condition, grounded))
            if unmet and matched:
                hint = f"R{index} {head.label()}: unmet {', '.join(unmet)}"
                if hint not in seen:
                    seen.add(hint)
                    hints.append(hint)
                break
    return hints[:limit]


def match_goal(goal: Morphism, store: AtomStore, ctx: TheoryContext) -> list[GoalHit]:
    """All facts matching ``goal``, best (axiom, shortest provenance) first."""
    hits: list[GoalHit] = []
    for fact in store.facts:
        subst = unify_pattern(goal, fact, ctx, {})
        if subst is not None:
            hits.append(GoalHit(fact=fact, subst=subst))
    hits.sort(key=lambda h: (not h.fact.axiom, len(h.fact.used), h.fact.rule_index or 0))
    return hits


def complementary(store: AtomStore, fact: Fact) -> Fact | None:
    """The fact ``P`` opposite to ``¬P`` (same triple and modality)."""
    key = (fact.predicate, fact.subject, fact.object, not fact.negated, fact.modality)
    return store.get(key)


def assumption_explained(
    assumption: Morphism,
    store: AtomStore,
    ctx: TheoryContext,
    *,
    used: frozenset[FactKey],
) -> bool:
    """True if the assumption is an axiom, was used, or is a lemma of that proof."""
    grounded = instantiate(assumption, ctx, {})
    if grounded is not None and grounded.key in used:
        return True
    for fact in store.facts:
        if not fact.used.issubset(used):
            continue
        if unify_pattern(assumption, fact, ctx, {}) is not None:
            return True
    return False
