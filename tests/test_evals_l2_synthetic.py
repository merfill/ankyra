"""L2 synthetic collection: determinism and the gate itself."""

from __future__ import annotations

import json

from evals import build_l2_synthetic
from evals.l2_synthetic import SAMPLE, evaluate, load_sample, run_all


def test_committed_sample_is_deterministic():
    committed = load_sample(SAMPLE)
    rebuilt = json.loads(json.dumps(build_l2_synthetic.cases(), ensure_ascii=False))
    assert rebuilt == committed


def test_all_cases_pass_the_gate():
    results = run_all(load_sample(SAMPLE))
    failures = [result for result in results if not result["match"]]
    assert not failures, failures


def test_collection_covers_every_new_mechanism():
    mechanisms = {case["mechanism"] for case in load_sample(SAMPLE)}
    assert {
        "disjunctive_head",
        "disjunctive_body",
        "de_morgan",
        "reductio",
        "conjunctive_goal",
        "disjunctive_goal",
        "disjunctive_fact",
        "existential",
        "open_goal",
        "budget",
        "out_of_fragment",
        "control",
    } <= mechanisms


def test_collection_has_negative_controls():
    results = {result["id"]: result for result in run_all(load_sample(SAMPLE))}
    # A disjunctive clause must not entail a disjunct; the Horn flag must not consume it.
    assert results["head-no-disjunct-02"]["actual"]["status"] == "unsupported"
    assert results["control-flag-off-01"]["actual"]["status"] == "out_of_fragment"
    # An exhausted budget must not yield a proof.
    assert results["budget-01"]["actual"]["strength"] == "not_proven"


def test_evaluate_reports_a_mismatch():
    case = {
        "id": "bogus",
        "mechanism": "test",
        "theory": {"objects": [], "morphisms": [{"predicate": "p"}], "rules": [], "constraints": []},
        "query": {"target": {"predicate": "p"}, "answer_type": "yes_no"},
        "expected": {"status": "unsupported", "kind": "unknown", "strength": "not_proven"},
        "logic": "ground",
    }
    result = evaluate(case)
    assert not result["match"]
    assert result["mismatches"] == ["status", "kind", "strength"]
