"""L1 engine: disjointness constraints, negation-as-failure and the world assumption."""

from __future__ import annotations

from ankyra.core.models import Constraint, Morphism, Query, Rule, Theory
from ankyra.engine.answer import build_answer
from ankyra.engine.explain import build_explanation
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.verify import verify


def _isa(subject: str, obj: str, negated: bool = False) -> Morphism:
    return Morphism(predicate="is_a", subject=subject, object=obj, negated=negated)


def _disjoint_theory() -> Theory:
    return Theory(
        objects=[],
        morphisms=[_isa("a", "real_number")],
        constraints=[Constraint(left="real_number", right="imaginary")],
    )


def test_constraint_derives_the_negative_of_the_other_side():
    theory = _disjoint_theory()
    from ankyra.engine.horn import saturate

    store = saturate(theory)
    assert store.get(("is_a", "a", "imaginary", True, "neutral")) is not None


def test_constraint_refutes_a_positive_target():
    theory = _disjoint_theory()
    query = Query(target=_isa("a", "imaginary"), answer_type="yes_no")
    verdict = verify(theory, query)
    assert verdict.status == "refuted"
    answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    assert answer.kind == "no"
    assert answer.strength == "proven"


def test_constraint_negative_reaches_through_a_chain():
    theory = Theory(
        morphisms=[_isa("a", "prime")],
        rules=[Rule(conditions=[_isa("?x", "prime")], consequence=_isa("?x", "real_number"))],
        constraints=[Constraint(left="real_number", right="imaginary")],
    )
    query = Query(target=_isa("a", "imaginary"), answer_type="yes_no")
    assert verify(theory, query).status == "refuted"


def test_both_sides_of_a_constraint_are_a_contradiction():
    theory = Theory(
        morphisms=[_isa("a", "real_number"), _isa("a", "imaginary")],
        constraints=[Constraint(left="real_number", right="imaginary")],
    )
    query = Query(target=_isa("a", "imaginary"), answer_type="yes_no")
    verdict = verify(theory, query)
    assert verdict.status == "contradiction"


def test_constraint_with_one_side_alone_derives_nothing():
    theory = Theory(
        morphisms=[_isa("a", "real_number")],
        constraints=[Constraint(left="real_number", right="imaginary")],
    )
    query = Query(target=_isa("a", "transcendental"), answer_type="yes_no")
    verdict = verify(theory, query)
    assert verdict.status == "unsupported"


def test_constraint_appears_in_the_explanation():
    theory = _disjoint_theory()
    theory = theory.model_copy(update={"constraints": [Constraint(left="real_number", right="imaginary", quote="No real number is imaginary.")]})
    query = Query(target=_isa("a", "imaginary"), answer_type="yes_no")
    verdict = verify(theory, query)
    explanation = build_explanation(theory, query, verdict, HypothesisLedger())
    kinds = {step.kind for step in explanation.steps}
    assert "constraint" in kinds


def _naf_theory() -> Theory:
    # Any person without a license needs training. Alice is a person; nothing
    # derives a license for her.
    return Theory(
        morphisms=[_isa("alice", "person")],
        rules=[
            Rule(
                conditions=[
                    _isa("?x", "person"),
                    Morphism(predicate="has_license", subject="?x", negated=True),
                ],
                consequence=Morphism(predicate="needs_training", subject="?x"),
            )
        ],
    )


def test_naf_derives_under_a_declared_closed_world():
    theory = _naf_theory()
    query = Query(
        target=Morphism(predicate="needs_training", subject="alice"),
        answer_type="yes_no",
        world_assumption="closed",
    )
    verdict = verify(theory, query)
    assert verdict.status == "supported"
    answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    assert answer.kind == "yes"


def test_naf_does_not_fire_in_an_open_world():
    theory = _naf_theory()
    query = Query(
        target=Morphism(predicate="needs_training", subject="alice"),
        answer_type="yes_no",
    )
    assert verify(theory, query).status == "unsupported"


def test_naf_literal_fails_when_the_positive_atom_is_derivable():
    from ankyra.engine.horn import saturate

    theory = Theory(
        morphisms=[_isa("alice", "person")],
        rules=[
            Rule(
                conditions=[_isa("?x", "person")],
                consequence=Morphism(predicate="has_license", subject="?x"),
            ),
            Rule(
                conditions=[
                    _isa("?x", "person"),
                    Morphism(predicate="has_license", subject="?x", negated=True),
                ],
                consequence=Morphism(predicate="needs_training", subject="?x"),
            ),
        ],
    )
    store = saturate(theory, world_assumption="closed")
    assert store.get(("has_license", "alice", "", False, "neutral")) is not None
    assert store.get(("needs_training", "alice", "", False, "neutral")) is None


def test_closed_world_refutes_an_unprovable_ground_target():
    theory = Theory(morphisms=[_isa("alice", "person")])
    query = Query(
        target=Morphism(predicate="has_license", subject="alice"),
        answer_type="yes_no",
        world_assumption="closed",
    )
    verdict = verify(theory, query)
    assert verdict.status == "refuted"
    answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    assert answer.kind == "no"
    explanation = build_explanation(theory, query, verdict, HypothesisLedger())
    assert [step.kind for step in explanation.steps] == ["naf"]


def test_open_world_does_not_refute_an_unprovable_target():
    theory = Theory(morphisms=[_isa("alice", "person")])
    query = Query(
        target=Morphism(predicate="has_license", subject="alice"),
        answer_type="yes_no",
    )
    assert verify(theory, query).status == "unsupported"


def test_closed_world_supports_an_unprovable_negated_target():
    theory = Theory(morphisms=[_isa("alice", "person")])
    query = Query(
        target=Morphism(predicate="has_license", subject="alice", negated=True),
        answer_type="yes_no",
        world_assumption="closed",
    )
    verdict = verify(theory, query)
    assert verdict.status == "supported"
    answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    assert answer.kind == "yes"
    explanation = build_explanation(theory, query, verdict, HypothesisLedger())
    assert [step.kind for step in explanation.steps] == ["naf"]


def test_open_target_is_never_refuted_by_cwa():
    theory = Theory(morphisms=[_isa("alice", "person")])
    query = Query(
        target=Morphism(predicate="has_license", subject="?who"),
        answer_type="open",
        world_assumption="closed",
    )
    assert verify(theory, query).status == "unsupported"


def test_non_stratifiable_program_is_out_of_fragment():
    # p depends negatively on q, q depends positively on p: a negative cycle.
    theory = Theory(
        morphisms=[_isa("alice", "person")],
        rules=[
            Rule(
                conditions=[
                    _isa("?x", "person"),
                    Morphism(predicate="q", subject="?x", negated=True),
                ],
                consequence=Morphism(predicate="p", subject="?x"),
            ),
            Rule(
                conditions=[Morphism(predicate="p", subject="?x")],
                consequence=Morphism(predicate="q", subject="?x"),
            ),
        ],
    )
    query = Query(
        target=Morphism(predicate="p", subject="alice"),
        answer_type="yes_no",
        world_assumption="closed",
    )
    verdict = verify(theory, query)
    assert verdict.status == "out_of_fragment"
    assert "out_of_fragment:stratification" in verdict.gaps


def test_stratification_orders_a_stratified_program():
    from ankyra.engine.horn import stratification

    theory = _naf_theory()
    strata = stratification(theory)
    assert strata is not None
    assert strata["needs_training"] == 1
    assert strata["has_license"] == 0


def test_stratification_ignores_builtins():
    from ankyra.config.settings import settings
    from ankyra.engine.horn import has_naf, stratification

    theory = Theory(
        rules=[
            Rule(
                conditions=[
                    _isa("?x", "person"),
                    Morphism(predicate="gte", subject="?p", object="5"),
                ],
                consequence=Morphism(predicate="q", subject="?x"),
            )
        ]
    )
    previous = settings.get("BUILTINS", False)
    settings.set("BUILTINS", True)
    try:
        strata = stratification(theory)
        assert strata is not None
        assert "gte" not in strata
        assert has_naf(theory) is False
    finally:
        settings.set("BUILTINS", previous)

