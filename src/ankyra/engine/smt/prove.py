"""A Z3-backed clause procedure with the contract of ``engine.resolution`` (L2).

The second backend of the L2 decision procedure: it clausifies a theory with
``engine.clause`` exactly as ground resolution does, then decides the resulting
clause set with Z3 instead of saturation. The encoding is purely propositional —
one ``z3.Bool`` per ground atom ``(predicate, subject, object, modality)``, a clause
becoming a disjunction and an empty clause the literal ``False`` — so the two
backends agree on every input the fragment covers and differ only in how the
refutation is reached (and in that Z3 records no proof DAG, hence ``proof is None``).

Z3 is optional (``uv sync --extra smt``): ``z3`` is loaded lazily through
:func:`ankyra.engine.smt.require_z3`, so importing this module never requires it.

``unsat`` of the theory plus the negated goal is ``entailed``; a model is
``not_entailed``; ``unknown`` (Z3 gave up) is the honest ``budget``. The step budget
bounds the work: ``steps`` is the number of added clauses in the encoding, and an
encoding larger than the budget is reported as ``budget`` without calling the solver,
so the budget keeps the same "never a guess" meaning as in resolution.

The result type is the shared :class:`ankyra.engine.resolution.ProverResult`
(``status, proof, steps, budget``). Z3 records no resolution DAG, so this backend
never builds one: ``proof`` is always ``None`` (also for ``entailed``), and the trace
is not mechanically replayable the way a resolution refutation is.
"""

from __future__ import annotations

from ankyra.core.models import Theory
from ankyra.engine.clause import (
    Clause,
    Clausification,
    Literal,
    clausify,
    negate,
)
from ankyra.engine.resolution import DEFAULT_BUDGET, ProverResult
from ankyra.engine.smt import require_z3

# An atom is a literal without its polarity: (predicate, subject, object, modality).
Atom = tuple[str, str, str, str]

__all__ = [
    "DEFAULT_BUDGET",
    "ProverResult",
    "prove",
    "refute",
    "refute_conjunction",
    "refute_support",
]


def _atom(literal: Literal) -> Atom:
    return (literal[0], literal[1], literal[2], literal[4])


def _atom_name(atom: Atom) -> str:
    """A deterministic, collision-free symbol name for a ground atom."""
    return "atom" + repr(atom)


class _Encoding:
    """The propositional encoding of a clause set; one cache per call."""

    def __init__(self, z3) -> None:
        self._z3 = z3
        self._atoms: dict[Atom, object] = {}

    def atom(self, literal: Literal):
        atom = _atom(literal)
        symbol = self._atoms.get(atom)
        if symbol is None:
            symbol = self._z3.Bool(_atom_name(atom))
            self._atoms[atom] = symbol
        return symbol

    def literal(self, literal: Literal):
        symbol = self.atom(literal)
        return self._z3.Not(symbol) if literal[3] else symbol

    def clause(self, clause: Clause):
        disjuncts = [self.literal(literal) for literal in clause]
        return self._z3.Or(*disjuncts) if disjuncts else self._z3.BoolVal(False)


def _decide(
    clausification: Clausification,
    assumed: list[Clause],
    *,
    budget: int,
) -> ProverResult:
    """Encode ``clausification ∪ assumed`` and report whether it is unsatisfiable.

    The encoding is propositional: one ``z3.Bool`` per ground atom, one disjunction per
    clause, ``BoolVal(False)`` for the empty clause. ``steps`` counts the added clauses;
    when that count already exceeds ``budget`` the solver is never called and the result
    is ``budget``. ``proof`` is always ``None`` — Z3 records no proof DAG here.
    """
    assumptions = [frozenset(clause) for clause in assumed]
    steps = len(clausification.clauses) + len(assumptions)
    if steps > budget:
        return ProverResult("budget", None, steps, budget)

    z3 = require_z3()
    encoding = _Encoding(z3)
    solver = z3.Solver()
    for clause in clausification.clauses:
        solver.add(encoding.clause(clause))
    for clause in assumptions:
        solver.add(encoding.clause(clause))

    outcome = solver.check()
    if outcome == z3.unsat:
        return ProverResult("entailed", None, steps, budget)
    if outcome == z3.sat:
        return ProverResult("not_entailed", None, steps, budget)
    return ProverResult("budget", None, steps, budget)


def refute_support(
    clausification: Clausification,
    assumed: list[Clause],
    *,
    budget: int = DEFAULT_BUDGET,
) -> ProverResult:
    """Refute a set of assumed clauses against the clausified theory.

    ``assumed`` is the clausification of the negated goal (a single unit for a
    literal goal; one unit per conjunct for a conjunction); it is added to the
    theory's clauses and the conjunction is checked for unsatisfiability. The result
    carries ``proof is None``: unlike :func:`ankyra.engine.resolution.refute_support`,
    no proof DAG is built.
    """
    return _decide(clausification, assumed, budget=budget)


def refute(
    clausification: Clausification, goal: Literal, *, budget: int = DEFAULT_BUDGET
) -> ProverResult:
    """Refute ``¬goal`` (the single-literal case of :func:`refute_support`)."""
    return refute_support(clausification, [frozenset({negate(goal)})], budget=budget)


def refute_conjunction(
    clausification: Clausification, literals: list[Literal], *, budget: int = DEFAULT_BUDGET
) -> ProverResult:
    """Refute the conjunction of ``literals`` (T1's ``∃``/``∧`` negative check).

    ``T ⊨ ¬(g₁ ∧ … ∧ gₙ)`` iff the units ``g₁ … gₙ`` are jointly unsatisfiable; each
    literal is assumed as its own unit.
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

    ``unsupported`` is decided first, from the clausification alone, before Z3 is even
    loaded: it means the theory uses a construct outside the fragment (a builtin
    comparison, an unsafe rule); ``budget`` means the encoding did not fit the step
    budget or Z3 returned ``unknown``. Neither is a proof, and ``proof`` is always
    ``None`` — this backend builds no history DAG.
    """
    clausification = clausify(theory, assumptions=assumptions)
    if clausification.unsupported:
        return ProverResult("unsupported", None, 0, budget)
    return refute(clausification, goal, budget=budget)
