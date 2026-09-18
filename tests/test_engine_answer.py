"""Tests for the deterministic answer kind and its localized rendering."""

from __future__ import annotations

import pytest

from ankyra.core.models import Answer, Morphism, Object, Query, Rule, Theory, Verdict
from ankyra.engine.answer import build_answer, render_answer
from ankyra.engine.cycle import run_cycle
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.proposal import ProposalDraft
from ankyra.engine.verify import verify


def _answer(theory: Theory, query: Query) -> Answer:
    verdict = verify(theory, query)
    return build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)


def test_supported_yes_no_is_yes():
    theory = Theory(morphisms=[Morphism(predicate="raining")])
    query = Query(target=Morphism(predicate="raining"))
    answer = _answer(theory, query)
    assert answer.kind == "yes"
    assert render_answer(answer, "en") == "Answer: Yes"
    assert render_answer(answer, "ru") == "Ответ: Да"


def test_refuted_yes_no_is_no():
    theory = Theory(morphisms=[Morphism(predicate="raining", negated=True)])
    query = Query(target=Morphism(predicate="raining"))
    answer = _answer(theory, query)
    assert answer.kind == "no"
    assert render_answer(answer, "ru") == "Ответ: Нет"


def test_unmatched_target_is_unknown():
    theory = Theory(morphisms=[Morphism(predicate="p")])
    query = Query(target=Morphism(predicate="q"))
    answer = _answer(theory, query)
    assert answer.kind == "unknown"
    assert render_answer(answer, "en") == "Answer: Unknown"


def test_contradiction_kind_and_text():
    theory = Theory(
        morphisms=[Morphism(predicate="p"), Morphism(predicate="p", negated=True)]
    )
    query = Query(target=Morphism(predicate="p"))
    answer = _answer(theory, query)
    assert answer.kind == "contradiction"
    assert "Противоречие" in render_answer(answer, "ru")


def test_open_query_is_a_binding():
    theory = Theory(
        morphisms=[Morphism(predicate="is_a", subject="a", object="b")]
    )
    query = Query(
        target=Morphism(predicate="is_a", subject="a", object="?z"), answer_type="open"
    )
    answer = _answer(theory, query)
    assert answer.kind == "binding"
    assert answer.value == "?z=b"
    assert render_answer(answer, "ru") == "Ответ: Значение: ?z=b"


def test_no_target_is_an_instruction():
    theory = Theory(morphisms=[Morphism(predicate="p")])
    query = Query(conditions=[Morphism(predicate="p")], target=None)
    answer = _answer(theory, query)
    assert answer.kind == "instruction"


def test_render_answer_marks_hypotheses_and_defaults():
    answer = Answer(
        value="yes",
        kind="yes",
        strength="proven_under",
        hypotheses_used=["H1"],
        defeasible=True,
    )
    text = render_answer(answer, "ru")
    assert "при гипотезах: H1" in text
    assert "по умолчанию" in text


@pytest.mark.parametrize("status", ["insufficient", "no_progress", "budget"])
def test_unfinished_statuses_are_unknown(status):
    theory = Theory(morphisms=[Morphism(predicate="p")])
    query = Query(target=Morphism(predicate="p"))
    verdict = Verdict(status=status)
    answer = build_answer(theory, query, verdict, HypothesisLedger(), status)
    assert answer.kind == "unknown"
    assert answer.strength == "not_proven"
    assert render_answer(answer, "en") == "Answer: Unknown"


def test_render_answer_normalizes_language_names():
    answer = Answer(value="yes", kind="yes", strength="proven")
    assert render_answer(answer, "rus").startswith("Ответ")
    assert render_answer(answer, "ru-RU").startswith("Ответ")
    assert render_answer(answer, "en-US").startswith("Answer")


def test_render_answer_omits_the_hypotheses_qualifier_when_none_were_used():
    answer = Answer(value="yes", kind="yes", strength="proven_under", hypotheses_used=[])
    assert render_answer(answer, "en") == "Answer: Yes"


def test_hypothesis_rule_marks_the_answer_defeasible_and_proven_under():
    theory = Theory(
        objects=[Object(id="x")],
        morphisms=[Morphism(predicate="has_engine", subject="x")],
        source_text="X has an engine.",
    )
    query = Query(target=Morphism(predicate="drives", subject="x"))
    rule = Rule(
        conditions=[Morphism(predicate="has_engine", subject="?x")],
        consequence=Morphism(predicate="drives", subject="?x"),
    )
    proposals = iter([ProposalDraft(action="propose_rule", rule=rule)])
    result = run_cycle(lambda _ctx: next(proposals), theory, query, max_waves=3)

    assert result.answer.kind == "yes"
    assert result.answer.strength == "proven_under"
    assert result.answer.hypotheses_used == ["H1"]
    assert result.answer.defeasible is True
