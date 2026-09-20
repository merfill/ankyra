"""FOLIO negation-subset adapter and builder (offline; no LLM)."""

from __future__ import annotations

from types import SimpleNamespace

from ankyra.core.models import Answer, Morphism, Query
from ankyra.engine.answer import build_answer
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.verify import verify
from evals import build_folio_sample as builder
from evals import folio


def _result(target, kind, *, strength="proven", status="supported"):
    return SimpleNamespace(
        query=Query(target=target, answer_type="yes_no"),
        answer=Answer(value=None, kind=kind, strength=strength),
        status=status,
    )


def _row(premises_fol, conclusion_fol, label="True"):
    return {
        "premises-FOL": premises_fol,
        "conclusion-FOL": conclusion_fol,
        "label": label,
    }


def test_constructs_flags_a_disjunction_as_beyond_l1():
    row = _row(["∀x (A(x) → B(x))"], "C(a) ∨ D(a)")
    assert "disjunction" in builder.constructs(row)
    assert not builder.in_l1_negation(row)


def test_multivariable_quantification_is_beyond_l1():
    row = _row(["∀x ∀y (R(x, y) → S(x, y))"], "¬T(a)")
    assert "multivar" in builder.constructs(row)
    assert not builder.in_l1_negation(row)


def test_plain_negation_implication_is_in_l1():
    row = _row(["∀x (A(x) → ¬B(x))", "A(a)"], "¬B(a)")
    assert builder.in_l1_negation(row)


def test_quantified_conclusion_is_beyond_l1():
    row = _row(["∀x (A(x) → ¬B(x))", "A(a)"], "∀x (A(x) → ¬C(x))")
    assert not builder.in_l1_negation(row)


def test_in_l2_accepts_disjunction_and_existential():
    assert builder.in_l2(_row(["∀x (A(x) → B(x))"], "C(a) ∨ D(a)"))
    assert builder.in_l2(_row(["∃x (A(x) ∧ B(x))"], "C(a)"))


def test_in_l2_rejects_beyond_l2_constructs():
    assert not builder.in_l2(_row(["∀x (A(x) → B(x))"], "C(a) ⊕ D(a)"))
    assert not builder.in_l2(_row(["∀x ∀y (R(x, y) → S(x, y))"], "C(a) ∨ D(a)"))
    assert not builder.in_l2(_row(["∀x (A(x) → ¬B(x))"], "¬B(a)"))


def test_committed_l2_sample_stays_in_the_l2_fragment():
    records = folio.load_sample(folio.sample_path("l2"))
    assert len(records) == 45
    for record in records:
        raw = {
            "premises-FOL": record["premises_fol"],
            "conclusion-FOL": record["conclusion_fol"],
            "label": record["label"],
        }
        assert builder.in_l2(raw), record["id"]
        assert record["label"] in {"True", "False", "Uncertain"}


def test_sample_paths_are_distinct():
    assert folio.sample_path("negation").name == "folio_negation_tier_a.jsonl"
    assert folio.sample_path("l2").name == "folio_l2_tier_a.jsonl"


def test_l2_problem_selects_the_ground_logic():
    record = folio.load_sample(folio.sample_path("l2"))[0]
    problem = folio._to_problem(record, allow_hypotheses=False, logic="ground")
    assert problem["logic"] == "ground"
    assert problem["world_assumption"] == "open"


def test_committed_sample_stays_in_the_l1_negation_fragment():
    records = folio.load_sample()
    assert records
    for record in records:
        raw = {
            "premises-FOL": record["premises_fol"],
            "conclusion-FOL": record["conclusion_fol"],
            "label": record["label"],
        }
        assert builder.in_l1_negation(raw), record["id"]
        assert record["label"] in {"True", "False", "Uncertain"}


def test_expected_kind_is_polarity_aware():
    assert folio.expected_kind("True", flipped=False) == "yes"
    assert folio.expected_kind("False", flipped=False) == "no"
    assert folio.expected_kind("Uncertain", flipped=False) == "unknown"
    assert folio.expected_kind("True", flipped=True) == "no"


def test_score_record_matches_an_entailed_positive_conclusion():
    record = {"id": "x", "label": "True", "statement_negative": False}
    result = _result(Morphism(predicate="is_a", subject="a", object="b"), "yes")
    score = folio.score_record(record, result)
    assert score["kind_match"]
    assert score["polarity_flipped"] is False


def test_score_record_uncertain_stays_unknown():
    record = {"id": "y", "label": "Uncertain", "statement_negative": False}
    result = _result(Morphism(predicate="is_a", subject="a", object="b"), "unknown", strength="not_proven", status="unsupported")
    score = folio.score_record(record, result)
    assert score["kind_match"]


def test_score_open_existential_binding_counts_as_yes():
    record = {"id": "o", "label": "True", "statement_negative": False}
    query = Query(target=Morphism(predicate="is_a", subject="?x", object="animal"), answer_type="open")
    result = SimpleNamespace(
        query=query,
        answer=Answer(value="?x=sk0", kind="binding", strength="proven"),
        status="supported",
    )
    score = folio.score_record(record, result)
    assert score["compound"] and score["kind_match"] and score["actual_kind"] == "yes"


def test_score_compound_uncertain_conclusion_uses_the_label():
    record = {"id": "m", "label": "Uncertain", "statement_negative": True}
    negated = Morphism(predicate="is_a", subject="pet", object="cat", negated=True)
    query = Query(target=negated, goals=[negated], goal_mode="all", answer_type="yes_no")
    result = SimpleNamespace(
        query=query,
        answer=Answer(value="yes", kind="yes", strength="proven"),
        status="supported",
    )
    score = folio.score_record(record, result)
    assert score["compound"] and not score["kind_match"]
    assert score["expected_kind"] == "unknown"


def test_problem_text_and_open_world():
    record = folio.load_sample()[0]
    text = folio.problem_text(record)
    assert "Is it true that" in text
    problem = folio._to_problem(record, allow_hypotheses=False)
    assert problem["world_assumption"] == "open"


def test_gold_fol_parser_builds_a_theory():
    from evals.folio_fol import to_theory_query

    record = {r["id"]: r for r in folio.load_sample()}["folio-validation-0027"]
    theory, query = to_theory_query(record)
    assert theory.morphisms and theory.rules
    assert query.target is not None
    assert query.target.predicate == "is_a"
    assert query.target.subject == "marvin"


def test_gold_fed_open_world_is_a_fragment_boundary():
    from evals.folio_fol import expected_kind, to_theory_query

    records = folio.load_sample()
    hits = 0
    for record in records:
        theory, query = to_theory_query(record, world_assumption="open")
        verdict = verify(theory, query)
        answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
        if answer.kind == expected_kind(record["label"], False):
            hits += 1
    # Even with perfect formalization the open-world engine decides 7/13; the rest
    # need L2 (reductio/contrapositive) or a different world assumption.
    assert hits == 7
