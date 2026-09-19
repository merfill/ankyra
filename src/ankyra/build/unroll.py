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
from ankyra.core.models import Morphism, Object, Query, Rule, Theory
from ankyra.core.schemas import ProblemStructure, QuestionStructure, Slot, StructAtom


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


def unroll_problem_structure(
    structure: ProblemStructure,
    *,
    deontic_prefixes: bool = False,
) -> Theory:
    """Deterministically expand a ProblemStructure into a Theory."""
    morphisms: list[Morphism] = []
    for atom in list(structure.facts) + list(structure.variants):
        morphisms.extend(atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes))

    rules: list[Rule] = []
    for struct_rule in structure.rules:
        sorts = {
            f"?{name.lstrip('?')}": sort for name, sort in (struct_rule.forall or {}).items()
        }
        conditions: list[Morphism] = []
        for atom in _normalize_domain(struct_rule.antecedent, sorts):
            conditions.extend(atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes))
        consequents = atom_to_morphisms(struct_rule.consequent, deontic_prefixes=deontic_prefixes)
        if not consequents:
            continue
        consequence = consequents[0]
        if struct_rule.kind == "exception":
            consequence = consequence.model_copy(update={"negated": True})
        rules.append(
            Rule(
                conditions=conditions,
                consequence=consequence,
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
        source_text=structure.source_text,
        domain=list(structure.domain),
    )


def unroll_query_structure(
    structure: QuestionStructure,
    *,
    deontic_prefixes: bool = False,
) -> Query:
    """Facts -> conditions (Gamma), ask -> target (phi); variables carried over."""
    conditions: list[Morphism] = []
    for atom in structure.facts:
        conditions.extend(atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes))
    for struct_rule in structure.rules:
        for atom in struct_rule.antecedent:
            conditions.extend(atom_to_morphisms(atom, deontic_prefixes=deontic_prefixes))

    target: Morphism | None = None
    if structure.ask is not None:
        asks = atom_to_morphisms(structure.ask, deontic_prefixes=deontic_prefixes)
        if asks:
            target = asks[0]

    variables: dict[str, str] = {}
    for key, value in (structure.variables or {}).items():
        name = str(key).lstrip("?")
        if name and value:
            variables[name] = str(value)

    return Query(
        conditions=conditions,
        target=target,
        variables=variables,
        answer_type=derive_answer_type(target, variables),
    )
