"""Tests for the defeasible (non-monotonic) layer, flag-gated."""

from __future__ import annotations

import pytest

from ankyra.config.settings import settings
from ankyra.core.models import Morphism, Query, Rule, Theory
from ankyra.engine.answer import build_answer
from ankyra.engine.cycle import run_cycle
from ankyra.engine.defeasible import effective_store
from ankyra.engine.explain import build_explanation
from ankyra.engine.horn import derive_store, saturate
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.verify import verify


def _never(_ctx):
    raise AssertionError("no proposal expected for a terminal conflict")


@pytest.fixture
def defeasible_on():
    previous = settings.get("DEFEASIBLE", False)
    settings.set("DEFEASIBLE", True)
    yield
    settings.set("DEFEASIBLE", previous)


def _rule(condition_class: str, *, negated: bool = False) -> Rule:
    return Rule(
        conditions=[Morphism(predicate="is_a", subject="?x", object=condition_class)],
        consequence=Morphism(predicate="fly", subject="?x", negated=negated),
    )


def _penguin_theory(*, penguins_fly: bool) -> Theory:
    """Tweety is a penguin and a penguin is a bird; both defaults conflict."""
    return Theory(
        morphisms=[
            Morphism(predicate="is_a", subject="tweety", object="penguin"),
            Morphism(predicate="is_a", subject="penguin", object="bird"),
        ],
        rules=[
            _rule("bird", negated=penguins_fly),
            _rule("penguin", negated=not penguins_fly),
        ],
    )


def _diamond_theory() -> Theory:
    """Nixon: two defaults about the same predicate, no `is_a` between the classes."""
    return Theory(
        morphisms=[
            Morphism(predicate="is_a", subject="nixon", object="quaker"),
            Morphism(predicate="is_a", subject="nixon", object="republican"),
        ],
        rules=[
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="quaker")],
                consequence=Morphism(predicate="pacifist", subject="?x"),
            ),
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="republican")],
                consequence=Morphism(predicate="pacifist", subject="?x", negated=True),
            ),
        ],
    )


def _fly(tweety_negated: bool):
    return ("fly", "tweety", "", tweety_negated, "neutral")


def test_the_more_specific_default_wins_and_refutes_the_target(defeasible_on):
    theory = _penguin_theory(penguins_fly=False)
    store = effective_store(theory)
    assert store.get(_fly(True)) is not None
    assert store.get(_fly(False)) is None

    verdict = verify(theory, Query(target=Morphism(predicate="fly", subject="tweety")))
    assert verdict.status == "refuted"
    assert "target_refuted:fly" in verdict.gaps


def test_specificity_works_in_the_other_direction(defeasible_on):
    theory = _penguin_theory(penguins_fly=True)
    verdict = verify(theory, Query(target=Morphism(predicate="fly", subject="tweety")))
    assert verdict.status == "supported"


def test_undecided_conflict_stays_unknown(defeasible_on):
    theory = _diamond_theory()
    store = effective_store(theory)
    assert store.get(("pacifist", "nixon", "", False, "neutral")) is None
    assert store.get(("pacifist", "nixon", "", True, "neutral")) is None

    verdict = verify(theory, Query(target=Morphism(predicate="pacifist", subject="nixon")))
    assert verdict.status == "unsupported"


def test_specificity_resolution_marks_the_answer_defeasible(defeasible_on):
    theory = _penguin_theory(penguins_fly=False)
    query = Query(target=Morphism(predicate="fly", subject="tweety"))
    verdict = verify(theory, query)
    answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    assert answer.value == "no"
    assert answer.defeasible is True

    explanation = build_explanation(theory, query, verdict, HypothesisLedger())
    conflict = explanation.conflict
    assert conflict is not None
    assert conflict.kind == "defeasible"
    assert conflict.status == "resolved"
    assert conflict.defeated == "attacking"
    assert conflict.reason == "penguin is-a bird"


def test_undecided_conflict_is_reported_with_both_branches(defeasible_on):
    theory = _diamond_theory()
    query = Query(target=Morphism(predicate="pacifist", subject="nixon"))
    verdict = verify(theory, query)
    assert verdict.status == "unsupported"
    assert "undecided_conflict:pacifist" in verdict.gaps

    explanation = build_explanation(theory, query, verdict, HypothesisLedger())
    conflict = explanation.conflict
    assert conflict is not None
    assert conflict.kind == "defeasible"
    assert conflict.status == "undecided"
    assert "no is_a relation" in conflict.reason
    assert [step.statement for step in conflict.supporting] == ["pacifist(nixon)"]
    assert [step.statement for step in conflict.attacking] == ["NOT pacifist(nixon)"]


def test_undecided_conflict_is_terminal(defeasible_on):
    theory = _diamond_theory()
    query = Query(target=Morphism(predicate="pacifist", subject="nixon"))
    result = run_cycle(_never, theory, query)

    assert result.status == "unsupported"
    assert result.explanation.conflict is not None
    assert result.answer.strength == "not_proven"


def _two_individuals_resolved() -> Theory:
    """Robin's penguin default resolves; Tweety's eagle default is conflict-free."""
    return Theory(
        morphisms=[
            Morphism(predicate="is_a", subject="robin", object="penguin"),
            Morphism(predicate="is_a", subject="penguin", object="bird"),
            Morphism(predicate="is_a", subject="tweety", object="eagle"),
        ],
        rules=[
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="eagle")],
                consequence=Morphism(predicate="fly", subject="?x"),
            ),
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="bird")],
                consequence=Morphism(predicate="fly", subject="?x", negated=True),
            ),
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="penguin")],
                consequence=Morphism(predicate="fly", subject="?x"),
            ),
        ],
    )


def test_resolved_conflict_is_attached_to_the_matching_individual(defeasible_on):
    theory = _two_individuals_resolved()

    robin = Query(target=Morphism(predicate="fly", subject="robin"))
    robin_verdict = verify(theory, robin)
    assert robin_verdict.status == "supported"
    robin_conflict = build_explanation(
        theory, robin, robin_verdict, HypothesisLedger()
    ).conflict
    assert robin_conflict is not None
    assert [step.statement for step in robin_conflict.supporting] == ["fly(robin)"]
    assert [step.statement for step in robin_conflict.attacking] == ["NOT fly(robin)"]


def test_resolved_conflict_is_not_attached_to_another_individual(defeasible_on):
    theory = _two_individuals_resolved()

    tweety = Query(target=Morphism(predicate="fly", subject="tweety"))
    verdict = verify(theory, tweety)
    assert verdict.status == "supported"
    explanation = build_explanation(theory, tweety, verdict, HypothesisLedger())
    assert explanation.conflict is None


def _two_individuals_undecided() -> Theory:
    """The pacifist diamond holds for both Nixon and Reagan."""
    return Theory(
        morphisms=[
            Morphism(predicate="is_a", subject="nixon", object="quaker"),
            Morphism(predicate="is_a", subject="nixon", object="republican"),
            Morphism(predicate="is_a", subject="reagan", object="quaker"),
            Morphism(predicate="is_a", subject="reagan", object="republican"),
        ],
        rules=[
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="quaker")],
                consequence=Morphism(predicate="pacifist", subject="?x"),
            ),
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="republican")],
                consequence=Morphism(predicate="pacifist", subject="?x", negated=True),
            ),
        ],
    )


def test_undecided_conflict_keeps_only_the_query_individual(defeasible_on):
    theory = _two_individuals_undecided()
    query = Query(target=Morphism(predicate="pacifist", subject="nixon"))
    verdict = verify(theory, query)
    assert verdict.status == "unsupported"

    conflict = build_explanation(theory, query, verdict, HypothesisLedger()).conflict
    assert conflict is not None
    assert [step.statement for step in conflict.supporting] == ["pacifist(nixon)"]
    assert [step.statement for step in conflict.attacking] == ["NOT pacifist(nixon)"]


def test_strict_negation_blocks_a_default():
    theory = Theory(
        morphisms=[
            Morphism(predicate="is_a", subject="tweety", object="bird"),
            Morphism(predicate="fly", subject="tweety", negated=True),
        ],
        rules=[_rule("bird")],
    )
    store = effective_store(theory)
    assert store.get(_fly(False)) is None


def test_flag_off_keeps_the_strict_closure():
    theory = _penguin_theory(penguins_fly=False)
    settings.set("DEFEASIBLE", False)
    store = derive_store(theory)
    assert store.get(_fly(False)) is not None
    assert store.get(_fly(True)) is not None


def _two_step_default_chain() -> Theory:
    """Default rules that only reach ``c`` by iterating the effective closure."""
    return Theory(
        morphisms=[Morphism(predicate="is_a", subject="s", object="a")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="a")],
                consequence=Morphism(predicate="is_a", subject="?x", object="b"),
            ),
            Rule(
                conditions=[Morphism(predicate="is_a", subject="?x", object="b")],
                consequence=Morphism(predicate="is_a", subject="?x", object="c"),
            ),
        ],
    )


def test_flag_off_saturates_every_rule_like_the_strict_closure():
    previous = settings.get("DEFEASIBLE", False)
    settings.set("DEFEASIBLE", False)
    try:
        theory = _two_step_default_chain()
        store = derive_store(theory)
        keys = {fact.key for fact in store.facts}
        assert ("is_a", "s", "b", False, "neutral") in keys
        assert ("is_a", "s", "c", False, "neutral") in keys
        assert keys == {fact.key for fact in saturate(theory).facts}
    finally:
        settings.set("DEFEASIBLE", previous)


def test_effective_closure_iterates_defaults_to_a_fixpoint(monkeypatch):
    from ankyra.engine import defeasible

    theory = _two_step_default_chain()
    full = effective_store(theory)
    assert full.get(("is_a", "s", "c", False, "neutral")) is not None

    monkeypatch.setattr(defeasible, "_MAX_ITERATIONS", 1)
    limited = effective_store(theory)
    assert limited.get(("is_a", "s", "c", False, "neutral")) is None


def test_flag_off_does_not_attach_a_defeasible_conflict():
    previous = settings.get("DEFEASIBLE", False)
    settings.set("DEFEASIBLE", False)
    try:
        theory = _two_individuals_resolved()
        query = Query(target=Morphism(predicate="fly", subject="tweety"))
        verdict = verify(theory, query)
        assert verdict.status == "supported"
        explanation = build_explanation(theory, query, verdict, HypothesisLedger())
        assert explanation.conflict is None
    finally:
        settings.set("DEFEASIBLE", previous)
