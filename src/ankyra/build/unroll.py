"""Deterministic expander: structure -> Theory / Query.

Turns the LLM's structural decomposition (sets / variants / exclusions / rules /
modalities) into concrete morphisms and Horn rules, so the model never authors
combinatorial triples. No LLM calls here.

Modality is carried as a typed field. Deontic prefixes (``must_`` / ``must_not_``
/ ``may_``) are a policy: they are applied only when ``deontic_prefixes`` is on.

An OR-slot expands to one morphism per alternative (path A): the reasoner has no
disjunction, so each alternative stays individually matchable.
"""

from __future__ import annotations

from ankyra.build.normalize import canonicalize_predicate, is_var
from ankyra.build.query import derive_answer_type
from ankyra.core.models import (
    Constraint,
    Existential,
    GoalMode,
    Morphism,
    Object,
    Query,
    Rule,
    Theory,
    WorldAssumption,
)
from ankyra.core.schemas import ProblemStructure, QuestionStructure, Slot, StructAtom, StructRule


def modality_prefix(modality: str) -> str:
    """Deontic prefix that lowers a modality into a predicate name."""
    if modality == "obligation":
        return "must_"
    if modality == "forbidden":
        return "must_not_"
    if modality == "permit":
        return "may_"
    return ""


def _predicate(atom: StructAtom, *, deontic_prefixes: bool) -> str:
    prefix = modality_prefix(atom.modality) if deontic_prefixes else ""
    return canonicalize_predicate(f"{prefix}{atom.predicate}" if prefix else atom.predicate)


def _slot_ids(slot: Slot) -> list[str | None]:
    """Expand a slot to concrete terminal ids; empty means a missing argument.

    OR-variants become separate ids, each its own morphism, so any single
    alternative stays individually matchable; ``exclude`` subtracts from the set.
    """
    if slot.variants:
        base = list(slot.variants)
    elif slot.set:
        base = list(slot.set)
    elif slot.id:
        base = [slot.id]
    else:
        base = []
    excluded = set(slot.exclude)
    base = [oid for oid in base if oid not in excluded]
    return base or [None]


def atom_to_morphisms(atom: StructAtom, *, deontic_prefixes: bool = False) -> list[Morphism]:
    """A structural atom -> one morphism per (subject, object) terminal pair.

    An ascription ("Gary is cold", "cold people") is class/property membership, so it
    becomes ``is_a(subject, property)`` regardless of the surface construction; every
    other atom (possession, action) keeps its predicate form.
    """
    predicate = _predicate(atom, deontic_prefixes=deontic_prefixes)
    return [
        _atom_morphism(predicate, subj, obj, atom)
        for subj in _slot_ids(atom.subject)
        for obj in _slot_ids(atom.object)
    ]


def _atom_morphism(
    predicate: str, subject: str | None, obj: str | None, atom: StructAtom
) -> Morphism:
    if atom.relation_kind == "ascription" and subject and obj is None and predicate != "is_a":
        return Morphism(
            predicate="is_a",
            subject=subject,
            object=predicate,
            modality=atom.modality,
            quote=atom.quote or None,
            negated=atom.negated,
        )
    return Morphism(
        predicate=predicate,
        subject=subject,
        object=obj,
        modality=atom.modality,
        quote=atom.quote or None,
        negated=atom.negated,
    )


def _ordered_objects(structure: ProblemStructure) -> list[Object]:
    seen: set[str] = set()
    ordered: list[str] = []

    def use(oid: str | None) -> None:
        if oid and oid not in seen:
            seen.add(oid)
            ordered.append(oid)

    for obj in structure.objects:
        use(obj.id)
    atoms = list(structure.facts) + list(structure.variants)
    for rule in structure.rules:
        atoms.extend(rule.antecedent)
        atoms.append(rule.consequent)
        atoms.extend(rule.consequents)
        atoms.extend(rule.disjunctive_antecedent)
    for item in structure.disjunctions:
        atoms.extend(item.literals)
    for item in structure.existentials:
        atoms.extend(item.atoms)
    for atom in atoms:
        for morphism in atom_to_morphisms(atom):
            use(morphism.subject)
            use(morphism.object)
    return [Object(id=oid) for oid in ordered]


def _domain_var(atom: StructAtom, sorts: dict[str, str]) -> str | None:
    """The variable of a quantifier declaration ``is_a(?x, sort)`` whose sort matches."""
    if atom.predicate != "is_a" or atom.negated or atom.modality != "neutral":
        return None
    var = atom.subject.id
    sort = atom.object.id
    if not var or not sort or var not in sorts:
        return None
    return var if sorts[var].casefold() == sort.casefold() else None


def _atom_vars(atom: StructAtom) -> set[str]:
    return {term for term in (atom.subject.id, atom.object.id) if term and is_var(term)}


def _normalize_domain(
    antecedent: list[StructAtom], sorts: dict[str, str]
) -> list[StructAtom]:
    """Reconcile the rule body with its ``forall`` quantifier domain.

    The domain premise ``is_a(?x, sort)`` is not knowledge: when another positive
    premise already binds ``?x`` it is dropped. When it is the only binder (e.g.
    "All people need sleep"), it is kept — or synthesized from ``forall`` when the
    extractor omitted it — because a free variable would make the rule unsafe.
    """
    if not sorts:
        return antecedent
    bound: set[str] = set()
    domain_atoms: dict[str, StructAtom] = {}
    others: list[StructAtom] = []
    for atom in antecedent:
        var = _domain_var(atom, sorts)
        if var is not None:
            domain_atoms.setdefault(var, atom)
        else:
            others.append(atom)
            bound |= _atom_vars(atom)
    kept = list(others)
    for var, sort in sorts.items():
        if var in bound:
            continue
        atom = domain_atoms.get(var)
        if atom is None:
            atom = StructAtom.model_validate(
                {"predicate": "is_a", "subject": var, "object": sort}
            )
        kept.append(atom)
    return kept


def _uses_variants(atom: StructAtom) -> bool:
    """True when the atom's slots express an OR (alternatives), not an AND-set."""
    return bool(atom.subject.variants or atom.object.variants)


def _head_groups(struct_rule: StructRule, *, deontic_prefixes: bool) -> list[tuple[Morphism, list[Morphism]]]:
    """One ``(consequence, alternatives)`` head per rule the conclusion yields.

    * ``consequents`` (an explicit list) is a **disjunctive** head: one clause with the
      alternatives.
    * a single ``consequent`` whose slots use ``variants`` is likewise disjunctive.
    * a single ``consequent`` whose set expands to several morphisms is a **conjunction**
      of conclusions: one Horn rule per conjunct (this closes the old drop-the-rest bug).
    """
    if struct_rule.consequents:
        morphisms = [
            morphism
            for atom in struct_rule.consequents
            for morphism in atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes)
        ]
        groups = [(morphisms[0], morphisms[1:])] if morphisms else []
    else:
        morphisms = atom_to_morphisms(struct_rule.consequent, deontic_prefixes=deontic_prefixes)
        if not morphisms:
            groups = []
        elif _uses_variants(struct_rule.consequent):
            groups = [(morphisms[0], morphisms[1:])]
        else:
            groups = [(morphism, []) for morphism in morphisms]
    if struct_rule.kind == "exception":
        groups = [
            (head.model_copy(update={"negated": True}), [a.model_copy(update={"negated": True}) for a in alternatives])
            for head, alternatives in groups
        ]
    return groups


def _body_variants(
    struct_rule: StructRule, sorts: dict[str, str], *, deontic_prefixes: bool
) -> list[list[Morphism]]:
    """One condition list per body alternative.

    A disjunctive body (``A ∨ B => C``) is a logical OR over bodies, which is a Horn
    split: the builder emits one rule per disjunct. A conjunctive body stays a single
    condition list, with the quantifier's domain premise normalized away.
    """
    if struct_rule.disjunctive_antecedent:
        return [
            list(atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes))
            for atom in struct_rule.disjunctive_antecedent
        ]
    normalized = _normalize_domain(struct_rule.antecedent, sorts)
    return [
        [
            morphism
            for atom in normalized
            for morphism in atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes)
        ]
    ]


def _unroll_disjunctions(
    structure: ProblemStructure, *, deontic_prefixes: bool
) -> list[Rule]:
    """Compile disjunctive ground facts into conditionless clauses with a head OR.

    A disjunctive fact is non-Horn; lowering it into concurrent facts would be an
    unsound OR-as-AND. A one-literal "disjunction" is malformed and dropped.
    """
    rules: list[Rule] = []
    for item in structure.disjunctions:
        literals = [
            morphism
            for atom in item.literals
            for morphism in atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes)
        ]
        if len(literals) < 2:
            continue
        rules.append(
            Rule(
                conditions=[],
                consequence=literals[0],
                alternatives=literals[1:],
                source="quote",
                quote=item.quote or None,
            )
        )
    return rules


def _unroll_existentials(
    structure: ProblemStructure, *, deontic_prefixes: bool
) -> list[Existential]:
    """Compile existential premises into ``Theory.existentials`` (Skolemized later)."""
    out: list[Existential] = []
    for item in structure.existentials:
        atoms = [
            morphism
            for atom in item.atoms
            for morphism in atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes)
        ]
        if not atoms or not all((atom.predicate or "").strip() for atom in atoms):
            continue
        out.append(
            Existential(variable=item.variable or "?x", atoms=atoms, quote=item.quote or None)
        )
    return out


def unroll_problem_structure(
    structure: ProblemStructure,
    *,
    deontic_prefixes: bool = False,
) -> Theory:
    """Deterministically expand a ProblemStructure into a Theory."""
    morphisms: list[Morphism] = []
    for atom in structure.facts:
        morphisms.extend(atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes))

    # ``variants`` is a disjunction of options, never concurrent facts: a lone option
    # is a plain fact, several become a disjunctive ground-fact clause (OR-as-AND closed).
    variant_literals = [
        morphism
        for atom in structure.variants
        for morphism in atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes)
    ]
    if len(variant_literals) == 1:
        morphisms.extend(variant_literals)

    rules: list[Rule] = _unroll_disjunctions(structure, deontic_prefixes=deontic_prefixes)
    if len(variant_literals) >= 2:
        rules.append(
            Rule(
                conditions=[],
                consequence=variant_literals[0],
                alternatives=variant_literals[1:],
                source="quote",
                quote=variant_literals[0].quote,
            )
        )

    for struct_rule in structure.rules:
        sorts = {
            f"?{name.lstrip('?')}": sort for name, sort in (struct_rule.forall or {}).items()
        }
        head_groups = _head_groups(struct_rule, deontic_prefixes=deontic_prefixes)
        if not head_groups:
            continue
        for conditions in _body_variants(struct_rule, sorts, deontic_prefixes=deontic_prefixes):
            for consequence, alternatives in head_groups:
                if not (consequence.predicate or "").strip():
                    continue
                rules.append(
                    Rule(
                        conditions=conditions,
                        consequence=consequence,
                        alternatives=alternatives,
                        kind=struct_rule.kind,
                        forall=sorts,
                        source="quote",
                        quote=struct_rule.quote or None,
                    )
                )

    return Theory(
        objects=_ordered_objects(structure),
        morphisms=morphisms,
        rules=rules,
        constraints=_unroll_constraints(structure),
        existentials=_unroll_existentials(structure, deontic_prefixes=deontic_prefixes),
        source_text=structure.source_text,
        domain=list(structure.domain),
    )


def _unroll_constraints(structure: ProblemStructure) -> list[Constraint]:
    """Compile disjointness statements into strict ``Constraint`` axioms.

    The two sides are class ids; a statement with a missing side is dropped, like
    any malformed atom elsewhere in the builder.
    """
    constraints: list[Constraint] = []
    for item in structure.disjoint:
        left, right = canonicalize_predicate(item.left), canonicalize_predicate(item.right)
        if not left or not right:
            continue
        constraints.append(Constraint(left=left, right=right, quote=item.quote or None))
    return constraints


def unroll_query_structure(
    structure: QuestionStructure,
    *,
    deontic_prefixes: bool = False,
    world_assumption: WorldAssumption = "open",
) -> Query:
    """Facts -> conditions (Gamma), ask -> target (phi); variables carried over.

    ``world_assumption`` is supplied by the caller (config/harness), never read
    from the question structure.
    """
    conditions: list[Morphism] = []
    for atom in structure.presuppositions:
        conditions.extend(atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes))
    for struct_rule in structure.rules:
        for atom in struct_rule.antecedent:
            conditions.extend(atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes))

    target: Morphism | None = None
    if structure.ask is not None:
        asks = atom_to_morphisms(structure.ask, deontic_prefixes=deontic_prefixes)
        if asks:
            target = asks[0]

    goals: list[Morphism] = []
    goal_clauses: list[list[Morphism]] = []
    goal_mode: GoalMode = "single"
    if structure.ask_universal:
        literals = [
            morphism
            for atom in structure.ask_universal
            for morphism in atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes)
        ]
        if any(
            is_var(term)
            for morphism in literals
            for term in (morphism.subject, morphism.object)
            if term
        ):
            goals = literals
            goal_mode = "forall"
        else:
            # A universal clause over no variable is the ground clause itself (T4).
            goal_clauses = [literals] if literals else []
            goal_mode = "cnf" if goal_clauses else "single"
    elif structure.ask_clauses:
        goal_clauses = [
            [
                morphism
                for atom in clause
                for morphism in atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes)
            ]
            for clause in structure.ask_clauses
        ]
        goal_clauses = [clause for clause in goal_clauses if clause]
        goal_mode = "cnf" if goal_clauses else "single"
    elif structure.ask_all:
        goals = [
            morphism
            for atom in structure.ask_all
            for morphism in atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes)
        ]
        goal_mode = "all"
    elif structure.ask_any:
        goals = [
            morphism
            for atom in structure.ask_any
            for morphism in atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes)
        ]
        goal_mode = "any"
    if goals:
        target = goals[0]
    elif goal_clauses:
        target = goal_clauses[0][0]

    variables: dict[str, str] = {}
    for key, value in (structure.variables or {}).items():
        name = str(key).lstrip("?")
        if name and value:
            variables[name] = str(value)

    return Query(
        conditions=conditions,
        target=target,
        goals=goals,
        goal_clauses=goal_clauses,
        goal_mode=goal_mode,
        variables=variables,
        answer_type=derive_answer_type(target, variables),
        world_assumption=world_assumption,
    )
