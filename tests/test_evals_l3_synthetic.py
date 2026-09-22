"""L3 synthetic collection: determinism and the gate itself."""

from __future__ import annotations

import json

from evals import build_l3_synthetic
from evals.l3_synthetic import SAMPLE, evaluate, load_sample, run_all

_CONSTRAINT_KINDS = {
    "all_different",
    "eq",
    "neq",
    "order",
    "adjacent",
    "not_adjacent",
    "same_group",
    "different_group",
    "count",
    "count_compare",
    "conditional",
    "all",
    "any",
    "not",
}


def test_committed_sample_is_deterministic():
    committed = load_sample(SAMPLE)
    rebuilt = json.loads(json.dumps(build_l3_synthetic.cases(), ensure_ascii=False))
    assert rebuilt == committed


def test_all_cases_pass_the_gate():
    results = run_all(load_sample(SAMPLE))
    failures = [result for result in results if not result["match"]]
    assert not failures, failures


def test_collection_covers_every_constraint_kind_and_question_kind():
    cases = load_sample(SAMPLE)
    used = {kind for case in cases for kind in case["uses"]}
    assert _CONSTRAINT_KINDS <= used
    assert {"not_violate", "must", "could", "must_be_false", "complete_list"} <= {
        case["question_kind"] for case in cases
    }


def test_collection_has_negative_controls():
    results = {result["id"]: result for result in run_all(load_sample(SAMPLE))}
    # Two verified options is an encoding signal, never a pick.
    assert results["ambiguous-17"]["actual"]["status"] == "ambiguous"
    # No option verified is unknown; an unentailed must is not chosen.
    assert results["unknown-18"]["actual"]["status"] == "unknown"
    assert results["must-not-entailed-19"]["actual"]["status"] == "unknown"
    # An exhausted budget is insufficient, never a guessed option.
    assert results["budget-insufficient-20"]["actual"]["status"] == "insufficient"
    # Ignoring the conditional would make a second option possible; the sound engine
    # still decides a unique option.
    assert results["conditional-soundness-could-14"]["actual"]["index"] == 2
    # Two impossible options in a must_be_false question is ambiguous, not a pick.
    assert results["must-be-false-ambiguous-22"]["actual"]["status"] == "ambiguous"
    # The question's assumptions are load-bearing: they pin the answer...
    assert results["assumptions-could-23"]["actual"]["index"] == 1
    # ...and an inconsistent assumption leaves no option verified (never a guess).
    assert results["assumptions-inconsistent-24"]["actual"]["status"] == "unknown"


def test_evaluate_reports_a_mismatch():
    case = {
        "id": "bogus",
        "mechanism": "test",
        "uses": ["eq"],
        "question_kind": "could",
        "game": {
            "domains": [{"id": "s2", "values": ["0", "1"], "topology": "set"}],
            "variables": [{"id": "A", "domain": "s2"}],
            "constraints": [],
            "source_text": "",
        },
        "question": {"kind": "could", "options": [{"constraints": [], "values": []}], "target": None},
        "expected": {"status": "decided", "index": 3},
        "budget": None,
    }
    result = evaluate(case)
    assert not result["match"]
    # The empty option is trivially satisfiable, so the decision is index 0, not 3.
    assert result["actual"] == {"status": "decided", "index": 0}
    assert result["mismatches"] == ["index"]
