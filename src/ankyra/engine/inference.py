"""Pluggable inference semantics seam (``docs/logic_layer.md``).

Policy and mechanics stay where they are; only the **semantics** — entailment, the
shape of a verdict, and the closure a proposal is classified against — is pluggable.
Two implementations exist today:

* :class:`HornInference` — monotonic Horn/L1 forward chaining (the default);
* :class:`ClausalInference` — the L2 ground-clause resolution procedure.

The module is deliberately thin: the concrete procedures live in ``engine.horn`` /
``engine.resolution`` and the verdict assembly in ``engine.verify``, so extracting the
seam does not duplicate logic. ``select_inference`` is called by ``verify`` (the policy
of *which* semantics runs stays there); ``classify`` uses the Horn closure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ankyra.config.settings import get_setting
from ankyra.core.models import FactKey, Query, Theory, Verdict


# Expressiveness the built structure needs, before any procedure runs. The fragment
# is *derived* from ``Theory``/``Query``; the semantics is *declared* by the query
# and the run config (docs/fragment_routing.md).
FragmentFeature = Literal[
    "horn",
    "negation",
    "disjunction",
    "existential",
    "builtin",
    "compound_goal",
    "shared_witness",
    "universal_goal",
    "head_only_rule",
]

# The features whose presence makes the clausal (L2) procedure the required one.
_CLAUSAL_FRAGMENT = frozenset({"disjunction", "existential", "compound_goal"})


@dataclass(frozen=True)
class RoutingDecision:
    """Static selection of a decision procedure over the built structure.

    ``fragment`` is derived, ``world_assumption`` and ``defeasible`` are declared,
    and ``capabilities`` is the per-run policy (which procedures this run may use).
    A non-``None`` ``refusal`` means the structure asks for a fragment outside the
    capabilities, or for a combination the chosen procedure cannot honor; the code
    is the ``out_of_fragment`` gap, never a silent downgrade.
    """

    fragment: frozenset[str]
    procedure: str
    capabilities: frozenset[str]
    world_assumption: str
    defeasible: bool
    refusal: str | None
    reasons: tuple[str, ...]

    @property
    def compatible(self) -> bool:
        return self.refusal is None


def _has_goals(query: Query) -> bool:
    if query.goal_mode != "single" and query.goals:
        return True
    return query.target is not None


def _has_negation(theory: Theory) -> bool:
    if theory.constraints:
        return True
    if any(m.negated for m in theory.morphisms):
        return True
    for rule in theory.rules:
        if rule.consequence.negated or any(a.negated for a in rule.alternatives):
            return True
        if any(condition.negated for condition in rule.conditions):
            return True
    return False


def _has_shared_witness(query: Query) -> bool:
    """True when conjunctive goals share a variable (an existential witness, T1)."""
    from ankyra.build.normalize import is_var

    if query.goal_mode != "all":
        return False
    return any(is_var(goal.subject) or is_var(goal.object) for goal in query.goals)


def _has_universal_goal(query: Query) -> bool:
    """True when the question is a universally quantified clause goal (T3)."""
    return query.goal_mode == "forall"


def _has_head_only_rule(theory: Theory) -> bool:
    """True when a rule grounds a head variable not bound by its body (T5)."""
    from ankyra.build.normalize import is_var

    for rule in theory.rules:
        body = {
            variable
            for condition in rule.conditions
            for variable in (condition.subject, condition.object)
            if is_var(variable)
        }
        if any(
            is_var(variable) and variable not in body
            for literal in rule.head
            for variable in (literal.subject, literal.object)
        ):
            return True
    return False


def _has_builtin(theory: Theory) -> bool:
    from ankyra.engine.builtins import is_builtin

    for m in theory.morphisms:
        if is_builtin(m.predicate):
            return True
    for rule in theory.rules:
        if is_builtin(rule.consequence.predicate):
            return True
        if any(is_builtin(a.predicate) for a in rule.alternatives):
            return True
        if any(is_builtin(condition.predicate) for condition in rule.conditions):
            return True
    return False


def _fragment(theory: Theory, query: Query) -> frozenset[str]:
    from ankyra.engine.horn import has_non_horn

    features = {"horn"}
    if has_non_horn(theory):
        features.add("disjunction")
    if theory.existentials:
        features.add("existential")
    if _has_negation(theory):
        features.add("negation")
    if _has_builtin(theory):
        features.add("builtin")
    if query.goal_mode != "single":
        features.add("compound_goal")
    if _has_shared_witness(query):
        features.add("shared_witness")
    if _has_universal_goal(query):
        features.add("universal_goal")
    if _has_head_only_rule(theory):
        features.add("head_only_rule")
    return frozenset(features)


def capabilities() -> frozenset[str]:
    """The procedures this run may use, from the config flags (per-run policy)."""
    caps = {"horn"}
    if str(get_setting("LOGIC", "off") or "off").strip().lower() != "off":
        caps.add("clausal")
    if bool(get_setting("BUILTINS", False)):
        caps.add("builtin")
    if bool(get_setting("DEFEASIBLE", False)):
        caps.add("defeasible")
    return frozenset(caps)


def analyze_routing(theory: Theory, query: Query) -> RoutingDecision:
    """Derive the fragment, read the semantics, validate, and pick a procedure.

    A1 (D-FR-2): the procedure mirrors ``select_inference`` (clausal when the L2 flag
    is on and there is a goal), and the existing refusals keep their gap codes. The
    decision is the single place those refusals are expressed; ``verify`` consults it
    before dispatching. Nothing escalates on a verdict's gaps.
    """
    from ankyra.engine.horn import has_naf, has_non_horn, stratification

    caps = capabilities()
    logic = "clausal" in caps
    defeasible = bool(get_setting("DEFEASIBLE", False))
    fragment = _fragment(theory, query)
    has_goals = _has_goals(query)
    procedure = "clausal" if (logic and has_goals) else "horn"
    world = query.world_assumption

    refusal: str | None = None
    if logic and has_naf(theory) and world == "closed":
        # L2 does not implement negation-as-failure: declared CWA is out of fragment.
        refusal = "out_of_fragment:naf_in_l2"
    elif procedure == "horn":
        if has_non_horn(theory):
            refusal = "out_of_fragment:non_horn"
        elif query.goal_mode != "single":
            refusal = "out_of_fragment:compound_goal"
        elif world == "closed" and has_naf(theory) and stratification(theory) is None:
            refusal = "out_of_fragment:stratification"
        elif theory.existentials:
            refusal = "out_of_fragment:existential"
    elif defeasible and (_CLAUSAL_FRAGMENT & fragment):
        # The defeasible layer ranges over the Horn closure and would be silently
        # dropped under the clausal procedure (D-FR-4).
        refusal = "out_of_fragment:defeasible_with_clausal_fragment"

    drivers = tuple(sorted(feature for feature in fragment if feature != "horn"))
    reasons = (*drivers, refusal) if refusal else (drivers or ("horn",))
    return RoutingDecision(
        fragment=fragment,
        procedure=procedure,
        capabilities=caps,
        world_assumption=world,
        defeasible=defeasible,
        refusal=refusal,
        reasons=reasons,
    )


class Inference(Protocol):
    """The varying part of a logic: entailment and a query verdict."""

    name: str
    supports_proposals: bool

    def entails(self, theory: Theory, literal: FactKey) -> bool: ...

    def closure_keys(self, theory: Theory) -> set[FactKey]: ...

    def decide(self, theory: Theory, query: Query) -> Verdict: ...


class HornInference:
    """Monotonic Horn/L1 semantics: the forward-chaining closure."""

    name = "horn"
    supports_proposals = True

    def entails(self, theory: Theory, literal: FactKey) -> bool:
        from ankyra.engine.horn import derive_store

        return derive_store(theory).get(literal) is not None

    def closure_keys(self, theory: Theory) -> set[FactKey]:
        from ankyra.engine.horn import derive_store

        return {fact.key for fact in derive_store(theory).facts}

    def decide(self, theory: Theory, query: Query) -> Verdict:
        from ankyra.engine.horn import build_context
        from ankyra.engine.verify import _verify_horn

        return _verify_horn(theory, query, build_context(theory))


class ClausalInference:
    """L2 semantics: ground-clause resolution (quantifiers by clausification)."""

    name = "clausal"
    supports_proposals = False

    def entails(self, theory: Theory, literal: FactKey) -> bool:
        from ankyra.engine.resolution import prove

        return prove(theory, literal, budget=_logic_budget()).status == "entailed"

    def closure_keys(self, theory: Theory) -> set[FactKey]:
        # L2 is not propositionalized into a fact set; proposals are unsupported
        # (D-L2-6), so classification must not use it.
        raise NotImplementedError("L2 has no fact closure; proposals are unsupported")

    def decide(self, theory: Theory, query: Query) -> Verdict:
        from ankyra.engine.horn import build_context
        from ankyra.engine.verify import _verify_l2

        return _verify_l2(theory, query, build_context(theory))


def _logic_budget() -> int:
    from ankyra.config.settings import get_setting
    from ankyra.engine.resolution import DEFAULT_BUDGET

    value = get_setting("LOGIC_BUDGET", DEFAULT_BUDGET)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_BUDGET


def select_inference(*, logic_enabled: bool, has_goals: bool) -> Inference:
    """Choose the semantics: L2 when enabled and a target exists, else Horn.

    This is policy (config + query shape), so it stays at the call site rather than in
    the semantics objects themselves.
    """
    if logic_enabled and has_goals:
        return ClausalInference()
    return HornInference()
