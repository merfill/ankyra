"""Defeasible synthetic collection: determinism, the gate, and flag hygiene."""

from __future__ import annotations

import json

from ankyra.config.settings import settings
from evals import build_defeasible_synthetic
from evals.defeasible_synthetic import SAMPLE, load_sample, run_all


def test_committed_sample_is_deterministic():
    committed = load_sample(SAMPLE)
    rebuilt = json.loads(json.dumps(build_defeasible_synthetic.cases(), ensure_ascii=False))
    assert rebuilt == committed


def test_all_cases_pass_the_gate():
    failures = [result for result in run_all(load_sample(SAMPLE)) if not result["match"]]
    assert not failures, failures


def test_collection_covers_specificity_conflict_and_control():
    mechanisms = {case["mechanism"] for case in load_sample(SAMPLE)}
    assert {"specificity", "undecided", "strict", "no_conflict", "control"} <= mechanisms


def test_layer_off_control_is_a_strict_contradiction():
    results = {result["id"]: result for result in run_all(load_sample(SAMPLE))}
    assert results["layer-off-control-08"]["actual"]["status"] == "contradiction"
    assert results["penguin-refute-01"]["actual"]["defeasible"] is True


def test_runner_restores_the_defeasible_flag():
    previous = bool(settings.get("DEFEASIBLE", False))
    run_all(load_sample(SAMPLE))
    assert bool(settings.get("DEFEASIBLE", False)) == previous
