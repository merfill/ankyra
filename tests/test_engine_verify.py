"""Tests for symbolic verification, including the Example A acceptance test."""

from __future__ import annotations

from ankyra.core.models import Morphism, Object, Query, Rule, Theory
from ankyra.engine.verify import verify


def test_example_a_deduction_is_proven_without_hypotheses():
    theory = Theory(
        objects=[Object(id="ground")],
        morphisms=[Morphism(predicate="raining")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
            )
        ],
    )
    query = Query(target=Morphism(predicate="is_wet", object="ground"))
    verdict = verify(theory, query)
    assert verdict.status == "supported"
    assert verdict.shelf == "proven"
    assert verdict.gaps == []
    assert verdict.matched


def test_missing_target_is_unsupported_in_example_b_fragment():
    theory = Theory(
        morphisms=[
            Morphism(predicate="has_engine", subject="x"),
            Morphism(predicate="wheel_count", subject="x", object="4"),
            Morphism(predicate="power", subject="x", object="150"),
            Morphism(predicate="door_count", subject="x", object="4"),
        ],
    )
    query = Query(target=Morphism(predicate="is_a", subject="?x", object="?c"), answer_type="open")
    verdict = verify(theory, query)
    assert verdict.status == "unsupported"
    assert verdict.shelf == "refused"
    assert "target_unmatched:is_a" in verdict.gaps


def test_unused_premise_makes_the_verdict_insufficient():
    theory = Theory(
        morphisms=[Morphism(predicate="p", subject="a")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="p", subject="?x")],
                consequence=Morphism(predicate="r", subject="?x"),
            )
        ],
    )
    query = Query(
        conditions=[Morphism(predicate="q", subject="a")],
        target=Morphism(predicate="r", subject="a"),
    )
    verdict = verify(theory, query)
    assert verdict.status == "insufficient"
    assert verdict.shelf == "attested"
    assert "unused_premise:q" in verdict.gaps


def test_declared_query_variables_do_not_prebind_the_open_target():
    theory = Theory(
        morphisms=[Morphism(predicate="has_engine", subject="vehicle_x")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="has_engine", subject="?v")],
                consequence=Morphism(predicate="is_a", subject="?v", object="car"),
            )
        ],
    )
    query = Query(
        target=Morphism(predicate="is_a", subject="vehicle_x", object="?c"),
        variables={"c": "vehicle type", "?c": "vehicle_type"},
        answer_type="open",
    )
    verdict = verify(theory, query)
    assert verdict.status == "supported"
    assert verdict.bindings.get("?c") == "car"
    assert "vehicle_type" not in verdict.bindings.values()


def test_a_premise_used_only_as_an_assumption_stays_supported():
    theory = Theory(
        rules=[
            Rule(
                conditions=[Morphism(predicate="p", subject="?x")],
                consequence=Morphism(predicate="r", subject="?x"),
            )
        ]
    )
    query = Query(
        conditions=[Morphism(predicate="p", subject="a")],
        target=Morphism(predicate="r", subject="a"),
    )
    assert verify(theory, query).status == "supported"


def test_a_premise_redundant_with_a_theory_fact_stays_supported():
    theory = Theory(
        objects=[Object(id="ground")],
        morphisms=[Morphism(predicate="raining")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
            )
        ],
    )
    query = Query(
        conditions=[Morphism(predicate="raining")],
        target=Morphism(predicate="is_wet", object="ground"),
    )
    assert verify(theory, query).status == "supported"


def test_target_contradiction_is_reported():
    theory = Theory(
        morphisms=[
            Morphism(predicate="raining"),
            Morphism(predicate="raining", negated=True),
        ],
    )
    query = Query(target=Morphism(predicate="raining"))
    verdict = verify(theory, query)
    assert verdict.status == "contradiction"
    assert verdict.shelf == "refused"
    assert any(gap.startswith("contradiction:") for gap in verdict.gaps)


def test_unrelated_inconsistency_does_not_sink_a_supported_target():
    theory = Theory(
        morphisms=[
            Morphism(predicate="raining", subject="a"),
            Morphism(predicate="raining", subject="a", negated=True),
            Morphism(predicate="snowing", subject="b"),
        ],
    )
    query = Query(
        conditions=[Morphism(predicate="snowing", subject="b")],
        target=Morphism(predicate="snowing", subject="b"),
    )
    verdict = verify(theory, query)
    assert verdict.status == "supported"
    assert any(gap.startswith("inconsistent_theory:") for gap in verdict.gaps)


def test_negated_target_is_refuted():
    theory = Theory(morphisms=[Morphism(predicate="fly", subject="tweety", negated=True)])
    query = Query(target=Morphism(predicate="fly", subject="tweety"))
    verdict = verify(theory, query)
    assert verdict.status == "refuted"
    assert "target_refuted:fly" in verdict.gaps


def test_open_subsumption_query_binds_the_variable():
    theory = Theory(
        morphisms=[
            Morphism(predicate="is_a", subject="sedan", object="car"),
            Morphism(predicate="is_a", subject="car", object="motor_vehicle"),
        ],
    )
    query = Query(target=Morphism(predicate="is_a", subject="sedan", object="?c"), answer_type="open")
    verdict = verify(theory, query)
    assert verdict.status == "supported"
    assert verdict.bindings.get("?c") == "car"
