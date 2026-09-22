"""Finite equality fragment (Tier-2 item 3a; ``docs/equality_plan.md``)."""

from __future__ import annotations

from ankyra.config.settings import setting_overrides
from ankyra.core.models import Morphism, Query, Rule, Theory
from ankyra.engine.answer import build_answer
from ankyra.engine.clause import clausify, equality_partition, has_equality
from ankyra.engine.inference import analyze_routing
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.verify import verify


def _m(predicate, subject=None, obj=None, *, neg=False):
    return Morphism(predicate=predicate, subject=subject, object=obj, negated=neg)


def _is_a(subject, obj, *, neg=False):
    return _m("is_a", subject, obj, neg=neg)


def _eq(left, right, *, neg=False):
    return _m("eq", left, right, neg=neg)


def _rule(conditions, consequence, alternatives=()):
    return Rule(conditions=list(conditions), consequence=consequence, alternatives=list(alternatives))


def _verify(theory, query, logic="ground"):
    with setting_overrides(LOGIC=logic):
        verdict = verify(theory, query)
        answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    return verdict, answer


def test_equality_partition_merges_asserted_names():
    theory = Theory(morphisms=[_is_a("rex", "cat"), _eq("rex", "tom")])
    assert equality_partition(theory) == {"rex": "tom", "tom": "tom"}


def test_clausify_canonicalizes_and_adds_axioms():
    theory = Theory(
        morphisms=[_is_a("rex", "cat"), _is_a("kim", "cat"), _eq("rex", "tom")],
        rules=[_rule([_is_a("?x", "cat")], _is_a("?x", "animal"))],
    )
    result = clausify(theory)
    assert result.canon == {"rex": "tom", "tom": "tom"}
    labels = {label for origins in result.origins.values() for label in origins}
    assert "equality:reflexive" in labels
    assert "equality:unique_names" in labels
    # No clause still mentions the non-representative ``rex``.
    assert all("rex" not in literal[1:] for clause in result.clauses for literal in clause)


def test_has_equality_detects_every_position():
    assert has_equality(Theory(morphisms=[_eq("rex", "tom")]))
    assert has_equality(Theory(rules=[_rule([_eq("?x", "c")], _is_a("?x", "k"))]))
    assert has_equality(Theory(), Query(target=_eq("rex", "tom")))
    assert not has_equality(Theory(morphisms=[_is_a("rex", "cat")]))


def test_substitution_through_asserted_equality():
    theory = Theory(
        morphisms=[_is_a("rex", "cat"), _eq("rex", "tom")],
        rules=[_rule([_is_a("?x", "cat")], _is_a("?x", "animal"))],
    )
    verdict, answer = _verify(theory, Query(target=_is_a("tom", "animal")))
    assert verdict.status == "supported" and answer.kind == "yes"


def test_reflexivity():
    theory = Theory(morphisms=[_is_a("rex", "cat")])
    verdict, answer = _verify(theory, Query(target=_eq("rex", "rex")))
    assert verdict.status == "supported" and answer.kind == "yes"


def test_unique_names_distinct_and_equal():
    theory = Theory(morphisms=[_is_a("rex", "cat"), _is_a("tom", "cat")])
    verdict, answer = _verify(theory, Query(target=_eq("rex", "tom", neg=True)))
    assert verdict.status == "supported" and answer.kind == "yes"
    verdict, answer = _verify(theory, Query(target=_eq("rex", "tom")))
    assert verdict.status == "refuted" and answer.kind == "no"


def test_equality_is_symmetric():
    theory = Theory(morphisms=[_is_a("rex", "cat"), _eq("rex", "tom")])
    verdict, _ = _verify(theory, Query(target=_eq("tom", "rex")))
    assert verdict.status == "supported"


def test_body_disequality_fires_only_for_the_other_individual():
    theory = Theory(
        morphisms=[_is_a("rex", "cat"), _is_a("tom", "cat")],
        rules=[_rule([_is_a("?x", "cat"), _eq("?x", "rex", neg=True)], _is_a("?x", "special"))],
    )
    verdict, answer = _verify(theory, Query(target=_is_a("tom", "special")))
    assert verdict.status == "supported" and answer.kind == "yes"
    verdict, answer = _verify(theory, Query(target=_is_a("rex", "special")))
    assert verdict.status == "unsupported" and answer.strength == "not_proven"


def test_equality_with_logic_off_is_refused():
    theory = Theory(morphisms=[_is_a("rex", "cat"), _eq("rex", "tom")])
    query = Query(target=_is_a("tom", "animal"))
    decision = analyze_routing(theory, query)
    assert decision.refusal == "out_of_fragment:equality"
    verdict, _ = _verify(theory, query, logic="off")
    assert verdict.status == "out_of_fragment"
