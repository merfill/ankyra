"""Bounded ground resolution refutation with proof recording (L2).

The L2 decision procedure (``docs/reasoning_roadmap.md``): to prove a ground literal
``g`` from ``Theory ∪ Gamma``, clausify the theory (``engine.clause``), add the negated
goal as a unit clause, and saturate by binary resolution under an explicit step budget.
An empty clause is the refutation (``entailed``); a completed saturation without one
means the goal is not entailed (``not_entailed``); an exhausted budget is the honest
``budget`` (never a guess). Every derived clause records its parents and pivot, so the
refutation is a mechanically checkable proof DAG.

Set-of-support keeps the search goal-directed: only clauses descended from the negated
goal drive new resolutions. The fragment is ground/finite-domain (``docs/l2_plan.md``
D-L2-4); quantifiers are handled by clausification (Skolemization + grounding) and by
witness enumeration in ``verify``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ankyra.core.models import Theory
from ankyra.engine.clause import (
    Clause,
    ClauseKey,
    Clausification,
    Literal,
    clausify,
    clause_key,
    is_tautology,
    negate,
)

DEFAULT_BUDGET = 10000

# A resolution node: the two parent clauses and the literal resolved on. An input
# clause has ``None`` parents.
Node = tuple[ClauseKey | None, ClauseKey | None, Literal | None]


@dataclass
class Proof:
    """A refutation: the empty clause and the resolution DAG that produced it."""

    assumed: list[Clause]
    steps: int
    nodes: dict[ClauseKey, Node] = field(default_factory=dict)
    origins: dict[ClauseKey, list[str]] = field(default_factory=dict)

    @property
    def empty(self) -> ClauseKey:
        return ()

    def derivation(self) -> list[ClauseKey]:
        """Clause keys in post-order from the empty clause (premises first)."""
        order: list[ClauseKey] = []
        seen: set[ClauseKey] = set()

        def visit(key: ClauseKey) -> None:
            if key in seen or key not in self.nodes:
                return
            seen.add(key)
            first, second, _ = self.nodes[key]
            if first is not None:
                visit(first)
            if second is not None:
                visit(second)
            order.append(key)

        visit(())
        return order


@dataclass
class MergedProof:
    """Several independent refutations presented as one trace (T1).

    A conjunctive goal with a shared witness is proved by one refutation per
    conjunct over the same witness (``docs/t1_plan.md`` §4.2); :func:`engine.explain._l2_steps`
    flattens the parts into a single ordered step list.
    """

    parts: list[Proof] = field(default_factory=list)

    @property
    def steps(self) -> int:
        return sum(part.steps for part in self.parts)


@dataclass
class ProverResult:
    """``entailed`` | ``not_entailed`` | ``budget`` | ``unsupported``."""

    status: str
    proof: Proof | None
    steps: int
    budget: int


def _pivots(left: Clause, right: Clause):
    for literal in left:
        if negate(literal) in right:
            yield literal


def _resolve(left: Clause, right: Clause, pivot: Literal) -> Clause | None:
    """Resolve on ``pivot``; ``None`` when the resolvent is a tautology."""
    rest = (left - {pivot}) | (right - {negate(pivot)})
    if any(negate(literal) in rest for literal in rest):
        return None
    return frozenset(rest)


def _subsumes(general: Clause, specific: Clause) -> bool:
    """Ground subsumption: ``general`` is a subset of ``specific`` (stronger clause)."""
    return general <= specific


def refute_support(
    clausification: Clausification,
    assumed: list[Clause],
    *,
    budget: int = DEFAULT_BUDGET,
) -> ProverResult:
    """Refute a set of assumed clauses by bounded set-of-support resolution.

    ``assumed`` is the clausification of the negated goal (a single unit for a
    literal goal; one unit per conjunct for a conjunction, T1); every assumed clause
    seeds the set of support. Only support clauses drive new resolutions, so the
    search stays goal-directed; the base theory must be satisfiable for set-of-support
    completeness. Only an actually derived empty clause is ``entailed``, so an
    incomplete search is the honest ``not_entailed``/``budget``, never a false proof.
    """
    clauses: dict[ClauseKey, Clause] = {}
    nodes: dict[ClauseKey, Node] = {}
    origins: dict[ClauseKey, list[str]] = {}

    for clause in clausification.clauses:
        key = clause_key(clause)
        clauses.setdefault(key, clause)
        nodes.setdefault(key, (None, None, None))
        origins.setdefault(key, [])
    for key, sources in clausification.origins.items():
        if key in clauses:
            origins[key] = list(sources)

    assumed_units = [frozenset(clause) for clause in assumed]
    support: list[ClauseKey] = []
    in_support: set[ClauseKey] = set()
    for clause in assumed_units:
        key = clause_key(clause)
        clauses.setdefault(key, clause)
        nodes.setdefault(key, (None, None, None))
        origins.setdefault(key, ["goal"])
        if key not in in_support:
            in_support.add(key)
            support.append(key)
    steps = 0
    while steps < budget:
        candidates: list[ClauseKey] = []
        for support_key in list(support):
            left = clauses.get(support_key)
            if left is None:
                continue
            for key in list(clauses):
                if key == support_key:
                    continue
                right = clauses[key]
                for pivot in _pivots(left, right):
                    resolvent = _resolve(left, right, pivot)
                    if resolvent is None:
                        continue
                    steps += 1
                    if steps > budget:
                        return ProverResult("budget", None, steps - 1, budget)
                    if not resolvent:
                        nodes[()] = (support_key, key, pivot)
                        origins[()] = []
                        proof = Proof(assumed=assumed_units, steps=steps, nodes=nodes, origins=origins)
                        return ProverResult("entailed", proof, steps, budget)
                    resolvent_key = clause_key(resolvent)
                    if resolvent_key in clauses:
                        continue
                    if any(_subsumes(existing, resolvent) for existing in clauses.values()):
                        continue
                    clauses[resolvent_key] = resolvent
                    nodes[resolvent_key] = (support_key, key, pivot)
                    origins[resolvent_key] = []
                    candidates.append(resolvent_key)
        if not candidates:
            return ProverResult("not_entailed", None, steps, budget)
        for candidate in candidates:
            if candidate not in in_support:
                in_support.add(candidate)
                support.append(candidate)
    return ProverResult("budget", None, steps, budget)


def refute(
    clausification: Clausification, goal: Literal, *, budget: int = DEFAULT_BUDGET
) -> ProverResult:
    """Refute ``¬goal`` (the single-literal case of :func:`refute_support`)."""
    return refute_support(
        clausification, [frozenset({negate(goal)})], budget=budget
    )


def refute_conjunction(
    clausification: Clausification, literals: list[Literal], *, budget: int = DEFAULT_BUDGET
) -> ProverResult:
    """Refute the conjunction of ``literals`` (T1's ``∃``/``∧`` negative check).

    ``T ⊨ ¬(g₁ ∧ … ∧ gₙ)`` iff the units ``g₁ … gₙ`` are jointly unsatisfiable; each
    literal is assumed as its own unit and an empty clause refutes the conjunction.
    """
    return refute_support(
        clausification, [frozenset({literal}) for literal in literals], budget=budget
    )


def prove(
    theory: Theory,
    goal: Literal,
    *,
    assumptions: list | None = None,
    budget: int = DEFAULT_BUDGET,
) -> ProverResult:
    """Clausify the theory (plus Gamma assumptions) and prove a ground ``goal``.

    ``unsupported`` means the theory uses a construct outside the fragment (a builtin
    comparison, an unsafe rule); ``budget`` means the step budget was exhausted.
    Neither is a proof.
    """
    clausification = clausify(theory, assumptions=assumptions)
    if clausification.unsupported:
        return ProverResult("unsupported", None, 0, budget)
    return refute(clausification, goal, budget=budget)
