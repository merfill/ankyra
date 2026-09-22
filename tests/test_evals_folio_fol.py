"""Gold-FOL parser and L2 gold-fed diagnostic (offline; no LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.analyze_folio import SAMPLES, analyze, load_sample
from evals.folio_fol import FolParseError, to_theory_query


def _record(premises: list[str], conclusion: str, label: str = "True") -> dict:
    return {
        "id": "test",
        "premises_fol": premises,
        "conclusion_fol": conclusion,
        "label": label,
    }


def _committed(subset: str, suffix: str) -> dict:
    return next(r for r in load_sample(SAMPLES[subset]) if r["id"].endswith(suffix))


def test_universal_implication_becomes_a_horn_rule():
    theory, query = to_theory_query(_record(["∀x (A(x) → B(x))"], "B(a)"))
    rule = theory.rules[0]
    assert (rule.conditions[0].predicate, rule.conditions[0].subject, rule.conditions[0].object) == (
        "is_a",
        "?x",
        "a",
    )
    assert (rule.consequence.predicate, rule.consequence.object) == ("is_a", "b")
    assert not rule.alternatives and rule.is_horn
    assert (query.target.subject, query.target.object) == ("a", "b")
    assert query.goal_mode == "single" and not query.goals


def test_disjunctive_head_becomes_alternatives():
    theory, _ = to_theory_query(_record(["∀x (A(x) → B(x) ∨ C(x))"], "B(a)"))
    rule = theory.rules[0]
    assert rule.consequence.object == "b"
    assert [alt.object for alt in rule.alternatives] == ["c"]
    assert not rule.is_horn


def test_disjunctive_body_becomes_two_rules():
    theory, _ = to_theory_query(_record(["A(a) ∨ B(a) → C(a)"], "C(a)"))
    heads = {rule.consequence.object for rule in theory.rules}
    bodies = {rule.conditions[0].object for rule in theory.rules}
    assert heads == {"c"} and bodies == {"a", "b"}


def test_ground_disjunctive_fact_is_a_conditionless_rule():
    theory, _ = to_theory_query(_record(["Season(spring) ∨ Season(summer)"], "Season(spring)"))
    rule = theory.rules[0]
    assert not rule.conditions
    assert rule.consequence.subject == "spring"
    assert [alt.subject for alt in rule.alternatives] == ["summer"]
    assert not theory.morphisms


def test_negated_conjunction_is_de_morganed_to_a_rule():
    theory, _ = to_theory_query(_record(["¬(A(a) ∧ B(a))"], "A(a)"))
    rule = theory.rules[0]
    assert rule.consequence.negated and not rule.conditions[0].negated
    assert len(theory.rules) == 1


def test_conjunctive_conclusion_is_a_flat_all_goal():
    _, query = to_theory_query(_record(["A(a)"], "B(a) ∧ C(a)"))
    assert query.goal_mode == "all"
    assert [goal.object for goal in query.goals] == ["b", "c"]
    assert query.target is query.goals[0]


def test_disjunctive_conclusion_is_a_flat_any_goal():
    _, query = to_theory_query(_record(["A(a)"], "B(a) ∨ C(a)"))
    assert query.goal_mode == "any"
    assert [goal.object for goal in query.goals] == ["b", "c"]


def test_existential_premise_becomes_an_existential():
    theory, _ = to_theory_query(_record(["∃x (P(x) ∧ Q(x))"], "P(a)"))
    assert len(theory.existentials) == 1
    existential = theory.existentials[0]
    assert existential.variable == "?x"
    assert [atom.object for atom in existential.atoms] == ["p", "q"]


def test_existential_single_atom_conclusion_is_an_open_target():
    _, query = to_theory_query(_record(["∀x (A(x) → B(x))"], "∃x (A(x))"))
    assert query.goal_mode == "single"
    assert query.target.subject == "?x" and query.target.object == "a"


def test_existential_conjunction_conclusion_is_out_of_fragment():
    with pytest.raises(FolParseError):
        to_theory_query(_record(["A(a)"], "∃x (P(x) ∧ Q(x))"))


def test_universal_conclusion_is_out_of_fragment():
    with pytest.raises(FolParseError):
        to_theory_query(_record(["A(a)"], "∀x (P(x) → Q(x))"))


def test_universal_fact_is_out_of_fragment():
    with pytest.raises(FolParseError):
        to_theory_query(_record(["∀x (A(x))"], "A(a)"))


def test_conditional_compound_conclusion_is_out_of_fragment():
    with pytest.raises(FolParseError):
        to_theory_query(_record(["A(a)"], "B(a) ∧ C(a) → D(a) ∧ E(a)"))


def test_malformed_formula_raises():
    with pytest.raises(FolParseError):
        to_theory_query(_record(["(A(a) ∧ B(a)) ∨ ¬C(a))"], "A(a)"))


def test_unicode_predicate_names_parse():
    _, query = to_theory_query(_record(["Companies’Stocks(kO)"], "Companies’Stocks(kO)"))
    assert query.target.predicate == "is_a"
    assert query.target.subject == "kO"
    assert query.target.object == "companies’stocks"


def test_binary_predicate_and_negation_are_preserved():
    theory, query = to_theory_query(_record(["∀x (C(x) → ¬D(x))"], "¬D(a)"))
    assert query.target.predicate == "is_a" and query.target.negated
    assert theory.rules[0].consequence.negated


def test_gold_l2_ground_refutation(tmp_path: Path):
    result = analyze(_committed("l2", "0064"), tmp_path, logic="ground")
    assert result["gold_open"] == ("no", "refuted")
    assert result["gold_open_ok"] and not result["fragment"]


def test_gold_l2_ground_support(tmp_path: Path):
    result = analyze(_committed("l2", "0024"), tmp_path, logic="ground")
    assert result["gold_open"] == ("yes", "supported")
    assert result["gold_open_ok"]


def test_gold_l2_universal_conclusion_is_fragment(tmp_path: Path):
    result = analyze(_committed("l2", "0045"), tmp_path, logic="ground")
    assert result["fragment"]
    assert result["gold_open"][1].startswith("out_of_fragment")


def test_gold_l1_negation_unchanged(tmp_path: Path):
    result = analyze(_committed("negation", "0074"), tmp_path, logic="off")
    assert result["gold_open"] == ("yes", "supported")
    assert result["gold_open_ok"] and not result["fragment"]
