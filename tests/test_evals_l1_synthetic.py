"""L1 synthetic collection: determinism and the gate itself."""

from __future__ import annotations

import json

from evals import build_l1_synthetic
from evals.l1_synthetic import SAMPLE, evaluate, load_sample, run_all


def test_committed_sample_is_deterministic():
    committed = load_sample(SAMPLE)
    rebuilt = json.loads(json.dumps(build_l1_synthetic.cases(), ensure_ascii=False))
    assert rebuilt == committed


def test_all_cases_pass_the_gate():
    results = run_all(load_sample(SAMPLE))
    failures = [result for result in results if not result["match"]]
    assert not failures, failures


def test_collection_covers_every_new_mechanism():
    mechanisms = {case["mechanism"] for case in load_sample(SAMPLE)}
    assert {
        "disjointness",
        "negative_consequent",
        "naf",
        "cwa",
        "stratification",
    } <= mechanisms


def test_collection_has_negative_controls():
    ids = {case["id"] for case in load_sample(SAMPLE)}
    assert any("control" in case_id for case_id in ids)
    results = {result["id"]: result for result in run_all(load_sample(SAMPLE))}
    # The open-world controls must not be decided by the new semantics.
    assert results["naf-open-control-02"]["actual"]["status"] == "unsupported"
    assert results["cwa-open-control-06"]["actual"]["status"] == "unsupported"
    assert results["cwa-open-target-07"]["actual"]["status"] == "unsupported"
    assert results["non-stratifiable-open-13"]["actual"]["status"] == "unsupported"


def test_evaluate_reports_a_mismatch():
    case = {
        "id": "bogus",
        "mechanism": "test",
        "theory": {"objects": [], "morphisms": [{"predicate": "p"}], "rules": [], "constraints": []},
        "query": {"target": {"predicate": "p"}, "answer_type": "yes_no"},
        "expected": {"status": "unsupported", "kind": "unknown", "strength": "not_proven"},
    }
    result = evaluate(case)
    assert not result["match"]
    assert result["mismatches"] == ["status", "kind", "strength"]
