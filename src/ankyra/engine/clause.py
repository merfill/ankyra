"""Ground clause IR and finite-domain clausification for the L2 procedure.

The L2 procedure decides a clause set by bounded resolution (``docs/reasoning_roadmap.md``).
This module lowers a ``Theory`` into **ground clauses over the theory's finite domain**
(``docs/l2_plan.md`` D-L2-4):

* an axiom / assumption becomes a unit clause;
* a rule becomes ``¬c1 ∨ … ∨ h1 ∨ …`` for every grounding of its body variables over
  the object pool (a disjunctive head stays a disjunction of positive literals);
* transitive ``is_a`` and the disjointness ``Constraint``\\ s become ordinary ground
  clauses, so L2 does not call the Horn forward chain and the two engines cannot
  diverge;
* a conjunctive existential premise (``∃x (φ ∧ …)``) is **Skolemized** to a fresh
  constant per existential (added to the pool), at clausification time — not by the
  builder.

Rationale for grounding (not first-order unification): the committed collections
(ProntoQA-OOD, FOLIO's in-fragment slice) are over finite, named domains, and ground
resolution terminates where first-order saturation need not (``not_entailed`` stays
decidable). Function terms and nested existentials remain outside the fragment and are
reported ``unsupported``; a head variable not bound by the body is an unsafe rule.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import product

from ankyra.build.normalize import is_var
from ankyra.core.models import FactKey, Morphism, Theory
from ankyra.engine.builtins import canonical_builtin
from ankyra.engine.horn import build_context

# A literal is a ground atom key: predicate, subject, object, negated, modality.
Literal = FactKey
Clause = frozenset[tuple[str, str, str, bool, str]]
ClauseKey = tuple[tuple[str, str, str, bool, str], ...]

_IS_A = "is_a"
_NEUTRAL = "neutral"


def literal_of(morphism: Morphism) -> Literal:
    return (
        morphism.predicate,
        morphism.subject or "",
        morphism.object or "",
        morphism.negated,
        morphism.modality,
    )


def negate(literal: Literal) -> Literal:
    return (literal[0], literal[1], literal[2], not literal[3], literal[4])


def clause_key(clause: Clause) -> ClauseKey:
    return tuple(sorted(clause))


def is_tautology(clause: Clause) -> bool:
    return any(negate(literal) in clause for literal in clause)


def label_of(literal: Literal) -> str:
    neg = "NOT " if literal[3] else ""
    modality = "" if literal[4] == _NEUTRAL else f"{literal[4]}:"
    args = ",".join(part for part in (literal[1], literal[2]) if part)
    return f"{neg}{modality}{literal[0]}({args})"


@dataclass
class Clausification:
    """Ground clauses plus provenance, Skolem constants and the fragment flags."""

    clauses: list[Clause] = field(default_factory=list)
    origins: dict[ClauseKey, list[str]] = field(default_factory=dict)
    unsupported: list[str] = field(default_factory=list)
    skolems: list[str] = field(default_factory=list)

    def add(self, clause: Clause, origin: str) -> None:
        key = clause_key(clause)
        for existing in self.origins.setdefault(key, []):
            if existing == origin:
                return
        self.origins[key].append(origin)
        self.clauses.append(clause)


def _rule_variables(rule) -> tuple[set[str], set[str]]:
    body = {
        var
        for condition in rule.conditions
        for var in (condition.subject, condition.object)
        if is_var(var)
    }
    head = {var for literal in rule.head for var in (literal.subject, literal.object) if is_var(var)}
    return body, head


def _ground_literal(morphism: Morphism, subst: dict[str, str]) -> Literal | None:
    subject = morphism.subject or ""
    obj = morphism.object or ""
    if is_var(subject):
        subject = subst.get(subject, "")
        if not subject:
            return None
    if is_var(obj):
        obj = subst.get(obj, "")
        if not obj:
            return None
    return (morphism.predicate, subject, obj, morphism.negated, morphism.modality)


def _groundings(
    rule, pool: list[str], individuals: list[str]
) -> list[dict[str, str]] | None:
    """Every grounding of the rule's variables, or ``None`` when unsafe.

    A variable bound by the body ranges over the full ``pool``: a class variable
    (``?c`` in ``is_a(?x, ?c)``) must reach class names. A **head-only** variable
    (T5, ``docs/t5_plan.md``) ranges over the individual domain only: the committed
    encoding lowers a unary ``P(t)`` to ``is_a(t, p)``, so a class name is not an
    element of the intended universe and instantiating the universal there is not a
    consequence of it (and can fabricate a proof). A head-only variable with no
    individual to range over keeps the honest ``unsafe_rule`` refusal.
    """
    body_vars, head_vars = _rule_variables(rule)
    if (head_vars - body_vars) and not individuals:
        return None
    names = sorted(body_vars | head_vars)
    domains = [
        (pool or [""]) if name in body_vars else individuals for name in names
    ]
    return [dict(zip(names, combo)) for combo in product(*domains)]


def _class_names(theory: Theory) -> set[str]:
    """Objects of ``is_a`` atoms and constraint sides — lowered predicates (T5)."""
    atoms: list[Morphism] = list(theory.morphisms)
    for rule in theory.rules:
        atoms.extend(rule.conditions)
        atoms.extend(rule.head)
    for existential in theory.existentials:
        atoms.extend(existential.atoms)
        for disjunction in existential.disjunctions:
            atoms.extend(disjunction)
    names = {
        atom.object
        for atom in atoms
        if atom.predicate == _IS_A and atom.object and not is_var(atom.object)
    }
    for constraint in theory.constraints:
        names.update(side for side in (constraint.left, constraint.right) if side)
    return names


def _individual_pool(theory: Theory, pool: list[str]) -> list[str]:
    """The individual domain of the theory: ``pool`` minus class names (T5).

    ``pool`` is the full grounding pool (objects ∪ Skolems ∪ extra terms);
    excluding the ``is_a`` objects leaves the intended universe of discourse
    (``docs/t5_plan.md`` §4.1). Variables are never domain elements.
    """
    classes = _class_names(theory)
    return sorted(
        term
        for term in pool
        if term and not is_var(term) and term not in classes
    )


def _clause_of_rule(rule, subst: dict[str, str]) -> Clause | None:
    literals: set[Literal] = set()
    for condition in rule.conditions:
        literal = _ground_literal(condition, subst)
        if literal is None:
            return None
        literals.add(negate(literal))
    for head in rule.head:
        literal = _ground_literal(head, subst)
        if literal is None:
            return None
        literals.add(literal)
    clause = frozenset(literals)
    return None if is_tautology(clause) else clause


def _positive_is_a_edges(clauses: list[Clause]) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for clause in clauses:
        for literal in clause:
            if (
                literal[0] == _IS_A
                and not literal[3]
                and literal[4] == _NEUTRAL
                and literal[1]
                and literal[2]
            ):
                edges.add((literal[1], literal[2]))
    return edges


def _transitive_closure(edges: set[tuple[str, str]]) -> set[tuple[str, str]]:
    closure = set(edges)
    changed = True
    while changed:
        changed = False
        for left, mid in list(closure):
            for mid2, right in list(closure):
                if mid == mid2 and (left, right) not in closure:
                    closure.add((left, right))
                    changed = True
    return closure


def _is_a_atom(subject: str, obj: str, *, negated: bool) -> Literal:
    return (_IS_A, subject, obj, negated, _NEUTRAL)


def _add_transitivity(result: Clausification) -> None:
    """Add the ground instances ``¬is_a(a,b) ∨ ¬is_a(b,c) ∨ is_a(a,c)``.

    Instantiating only the transitive closure of the potential ``is_a`` edges keeps the
    clause set small without losing any derivable ``is_a``.
    """
    closure = _transitive_closure(_positive_is_a_edges(result.clauses))
    seen: set[ClauseKey] = set()
    for left, mid in closure:
        for mid2, right in closure:
            if mid != mid2:
                continue
            clause = frozenset(
                {
                    _is_a_atom(left, mid, negated=True),
                    _is_a_atom(mid, right, negated=True),
                    _is_a_atom(left, right, negated=False),
                }
            )
            if is_tautology(clause):
                continue
            key = clause_key(clause)
            if key in seen:
                continue
            seen.add(key)
            result.add(clause, "transitivity")


def _add_constraints(result: Clausification, theory: Theory) -> None:
    """Add ``¬is_a(t,left) ∨ ¬is_a(t,right)`` for every class term ``t``."""
    if not theory.constraints:
        return
    terms: set[str] = set()
    for clause in result.clauses:
        for literal in clause:
            if literal[0] == _IS_A:
                terms.update(part for part in (literal[1], literal[2]) if part)
    for constraint in theory.constraints:
        for term in terms:
            result.add(
                frozenset(
                    {
                        _is_a_atom(term, constraint.left, negated=True),
                        _is_a_atom(term, constraint.right, negated=True),
                    }
                ),
                f"constraint:{constraint.left}|{constraint.right}",
            )


def _ground_existential_atom(atom: Morphism, variable: str, constant: str) -> Morphism:
    subject = constant if atom.subject == variable else atom.subject
    obj = constant if atom.object == variable else atom.object
    return atom.model_copy(update={"subject": subject, "object": obj})


def _existential_morphism_is_ground(morphism: Morphism) -> bool:
    return not (is_var(morphism.subject) or is_var(morphism.object))


def _add_existentials(result: Clausification, theory: Theory) -> None:
    """Skolemize each existential premise with a fresh constant.

    The body is a CNF (``atoms`` are units, ``disjunctions`` the multi-literal
    clauses, T2); each clause becomes a ground clause over the Skolem constant. An
    atom over a different free variable (a nested quantifier) is out of fragment,
    never a non-ground clause.
    """
    for index, existential in enumerate(theory.existentials):
        constant = f"sk{index}"
        grounded_atoms = [
            _ground_existential_atom(atom, existential.variable, constant)
            for atom in existential.atoms
        ]
        grounded_groups = [
            [
                _ground_existential_atom(atom, existential.variable, constant)
                for atom in disjunction
            ]
            for disjunction in existential.disjunctions
        ]
        if not all(
            _existential_morphism_is_ground(atom) for atom in grounded_atoms
        ) or not all(
            _existential_morphism_is_ground(atom)
            for group in grounded_groups
            for atom in group
        ):
            result.unsupported.append(f"existential:{index}")
            continue
        result.skolems.append(constant)
        for grounded in grounded_atoms:
            result.add(frozenset({literal_of(grounded)}), f"skolem:{index}")
        for group in grounded_groups:
            clause = frozenset(literal_of(atom) for atom in group)
            if clause and not is_tautology(clause):
                result.add(clause, f"skolem:{index}")


def clausify(
    theory: Theory,
    *,
    assumptions: list[Morphism] | None = None,
    extra_pool: Iterable[str] = (),
) -> Clausification:
    """Lower a theory (and the query's Gamma assumptions) into ground clauses.

    ``extra_pool`` adds ground terms to the pool the rules are instantiated over. T3
    uses it to ground a universal clause goal at a fresh constant (universal
    generalization, ``docs/t3_plan.md`` §4); instantiating a universal rule at one more
    term is a logical consequence of the theory, so this is sound.
    """
    result = Clausification()
    for morphism in theory.morphisms:
        result.add(frozenset({literal_of(morphism)}), f"axiom:{label_of(literal_of(morphism))}")
    for index, assumption in enumerate(assumptions or ()):
        result.add(frozenset({literal_of(assumption)}), f"presupposition:{index}")

    _add_existentials(result, theory)
    pool = sorted(set(build_context(theory).obj_pool) | set(result.skolems) | set(extra_pool))
    individuals = _individual_pool(theory, pool)

    for index, rule in enumerate(theory.rules, 1):
        if any(canonical_builtin(condition.predicate) for condition in rule.conditions):
            result.unsupported.append(f"builtin:rule:{index}")
            continue
        groundings = _groundings(rule, pool, individuals)
        if groundings is None:
            result.unsupported.append(f"unsafe_rule:{index}")
            continue
        for subst in groundings:
            clause = _clause_of_rule(rule, subst)
            if clause is not None:
                result.add(clause, f"rule:{index}")

    _add_transitivity(result)
    _add_constraints(result, theory)
    return result
