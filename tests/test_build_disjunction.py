"""Tests for lowering L2 structures (disjunctive heads, bodies, facts, goals)."""

from __future__ import annotations

from ankyra.build.query import settle_query
from ankyra.build.unroll import unroll_problem_structure, unroll_query_structure
from ankyra.core.models import Morphism, Query, Theory
from ankyra.core.schemas import ProblemStructure, QuestionStructure
from ankyra.engine.horn import saturate
from ankyra.engine.verify import verify


def _theory(**fields) -> Theory:
    return unroll_problem_structure(ProblemStructure.model_validate(fields))


def test_disjunctive_rule_head_becomes_alternatives():
    theory = _theory(
        source_text="x",
        rules=[
            {
                "antecedent": [{"predicate": "is_a", "subject": "?x", "object": "prim"}],
                "consequents": [
                    {"predicate": "is_a", "subject": "?x", "object": "a"},
                    {"predicate": "is_a", "subject": "?x", "object": "b"},
                ],
                "quote": "q",
            }
        ],
    )
    rule = theory.rules[0]
    assert not rule.is_horn
    assert [literal.object for literal in rule.head] == ["a", "b"]


def test_disjunctive_antecedent_splits_into_one_rule_per_disjunct():
    theory = _theory(
        source_text="x",
        rules=[
            {
                "disjunctive_antecedent": [
                    {"predicate": "is_a", "subject": "?x", "object": "a"},
                    {"predicate": "is_a", "subject": "?x", "object": "b"},
                ],
                "consequent": {"predicate": "is_a", "subject": "?x", "object": "c"},
                "quote": "q",
            }
        ],
    )
    assert len(theory.rules) == 2
    assert all(len(rule.conditions) == 1 for rule in theory.rules)
    assert {rule.conditions[0].object for rule in theory.rules} == {"a", "b"}


def test_disjunctive_ground_fact_is_a_clause_not_facts():
    theory = _theory(
        source_text="Rex is a or b",
        disjunctions=[
            {
                "literals": [
                    {"predicate": "is_a", "subject": "rex", "object": "a"},
                    {"predicate": "is_a", "subject": "rex", "object": "b"},
                ],
                "quote": "Rex is a or b",
            }
        ],
    )
    assert theory.morphisms == []
    assert len(theory.rules) == 1
    assert theory.rules[0].conditions == []
    assert not theory.rules[0].is_horn


def test_variants_do_not_become_concurrent_facts():
    theory = _theory(
        source_text="x",
        variants=[
            {"predicate": "is_a", "subject": "rex", "object": "a"},
            {"predicate": "is_a", "subject": "rex", "object": "b"},
        ],
    )
    assert theory.morphisms == []
    assert len(theory.rules) == 1
    assert not theory.rules[0].is_horn


def test_horn_engine_skips_a_disjunctive_rule():
    theory = _theory(
        source_text="x",
        morphisms=[{"predicate": "is_a", "subject": "rex", "object": "prim"}],
        rules=[
            {
                "antecedent": [{"predicate": "is_a", "subject": "?x", "object": "prim"}],
                "consequents": [
                    {"predicate": "is_a", "subject": "?x", "object": "a"},
                    {"predicate": "is_a", "subject": "?x", "object": "b"},
                ],
                "quote": "q",
            }
        ],
    )
    store = saturate(theory)
    assert store.get(("is_a", "rex", "a", False, "neutral")) is None
    assert store.get(("is_a", "rex", "b", False, "neutral")) is None


def test_verify_reports_out_of_fragment_for_a_disjunctive_fact():
    theory = _theory(
        source_text="Rex is a or b",
        disjunctions=[
            {
                "literals": [
                    {"predicate": "is_a", "subject": "rex", "object": "a"},
                    {"predicate": "is_a", "subject": "rex", "object": "b"},
                ],
                "quote": "Rex is a or b",
            }
        ],
    )
    verdict = verify(theory, Query(target=Morphism(predicate="is_a", subject="rex", object="a")))
    assert verdict.status == "out_of_fragment"
    assert any(gap.startswith("out_of_fragment:") for gap in verdict.gaps)


def test_compound_goal_decomposes_to_goals_and_mode():
    structure = QuestionStructure.model_validate(
        {
            "ask_all": [
                {"predicate": "is_a", "subject": "rex", "object": "a"},
                {"predicate": "is_a", "subject": "rex", "object": "b"},
            ]
        }
    )
    query = unroll_query_structure(structure)
    assert query.goal_mode == "all"
    assert len(query.goals) == 2
    assert query.target is not None and query.target.object == "a"
    # The Horn engine cannot decide a compound goal yet: it is out_of_fragment.
    assert verify(Theory(), query).status == "out_of_fragment"


def test_settle_query_drops_a_goal_echo_for_decomposed_goals():
    structure = QuestionStructure.model_validate(
        {
            "presuppositions": [{"predicate": "is_a", "subject": "rex", "object": "a"}],
            "ask_any": [
                {"predicate": "is_a", "subject": "rex", "object": "a"},
                {"predicate": "is_a", "subject": "rex", "object": "b"},
            ],
        }
    )
    query = settle_query(unroll_query_structure(structure))
    assert query.conditions == []
    assert query.goal_mode == "any"


def test_conjunctive_conclusion_splits_into_one_rule_per_conjunct():
    structure = ProblemStructure.model_validate(
        {
            "source_text": "x",
            "rules": [
                {
                    "antecedent": [{"predicate": "p", "subject": "?x"}],
                    "consequent": {"predicate": "has", "subject": "?x", "object": {"set": ["a", "b"]}},
                    "quote": "q",
                }
            ],
        }
    )
    theory = unroll_problem_structure(structure)
    assert len(theory.rules) == 2
    assert {rule.consequence.object for rule in theory.rules} == {"a", "b"}
    assert all(rule.is_horn for rule in theory.rules)


def test_head_only_universal_disjunction_is_a_conditionless_clause():
    theory = _theory(
        source_text="Every thing is a or b.",
        rules=[
            {
                "consequents": [
                    {"predicate": "is_a", "subject": "?x", "object": "a"},
                    {"predicate": "is_a", "subject": "?x", "object": "b"},
                ],
                "quote": "Every thing is a or b.",
            }
        ],
    )
    assert len(theory.rules) == 1
    rule = theory.rules[0]
    assert rule.conditions == []
    assert not rule.is_horn
    assert {literal.subject for literal in rule.head} == {"?x"}


def test_head_only_disjunction_is_decided_over_individuals():
    from ankyra.config.settings import setting_overrides

    theory = _theory(
        source_text="Every thing is a or b.",
        facts=[{"predicate": "is_a", "subject": "rex", "object": "a", "negated": True}],
        rules=[
            {
                "consequents": [
                    {"predicate": "is_a", "subject": "?x", "object": "a"},
                    {"predicate": "is_a", "subject": "?x", "object": "b"},
                ],
                "quote": "Every thing is a or b.",
            }
        ],
    )
    query = Query(target=Morphism(predicate="is_a", subject="rex", object="b"))
    with setting_overrides(LOGIC="ground"):
        verdict = verify(theory, query)
    assert verdict.status == "supported"


def test_existential_premise_unrolls_and_is_carried_by_enrichment():
    from ankyra.build.enrich import enrich_theory

    structure = ProblemStructure.model_validate(
        {
            "source_text": "There is an animal.",
            "existentials": [
                {
                    "variable": "x",
                    "atoms": [{"predicate": "is_a", "subject": "?x", "object": "animal"}],
                    "quote": "There is an animal.",
                }
            ],
        }
    )
    theory = unroll_problem_structure(structure)
    assert len(theory.existentials) == 1
    assert theory.existentials[0].variable == "?x"
    assert theory.existentials[0].atoms[0].object == "animal"
    assert enrich_theory(theory).existentials == theory.existentials
