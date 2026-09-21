"""Routing synthetic collection: determinism, the gate, coverage, flag hygiene."""

from __future__ import annotations

import json

from ankyra.config.settings import get_setting
from evals import build_routing_synthetic
from evals.routing_synthetic import SAMPLE, load_sample, run_all

_FEATURES = {"horn", "negation", "disjunction", "existential", "builtin", "compound_goal"}
_REFUSALS = {
    "out_of_fragment:non_horn",
    "out_of_fragment:compound_goal",
    "out_of_fragment:existential",
    "out_of_fragment:naf_in_l2",
    "out_of_fragment:defeasible_with_clausal_fragment",
}


def test_committed_sample_is_deterministic():
    committed = load_sample(SAMPLE)
    rebuilt = json.loads(json.dumps(build_routing_synthetic.cases(), ensure_ascii=False))
    assert rebuilt == committed


def test_all_cases_pass_the_gate():
    failures = [result for result in run_all(load_sample(SAMPLE)) if not result["match"]]
    assert not failures, failures


def test_collection_covers_every_fragment_feature():
    covered = {feature for case in load_sample(SAMPLE) for feature in case["expected"]["fragment"]}
    assert _FEATURES <= covered


def test_collection_covers_every_refusal_code():
    refusals = {
        case["expected"]["refusal"]
        for case in load_sample(SAMPLE)
        if case["expected"]["refusal"] is not None
    }
    assert _REFUSALS <= refusals


def test_negative_controls():
    results = {result["id"]: result for result in run_all(load_sample(SAMPLE))}
    # A disjunctive head with L2 off is refused by name, never consumed or guessed.
    assert results["refuse-non-horn-06"]["actual"]["status"] == "out_of_fragment"
    assert results["refuse-non-horn-06"]["actual"]["refusal"] == "out_of_fragment:non_horn"
    # A1: the L2 flag selects clausal even for a Horn structure; the fragment stays horn.
    assert results["control-horn-logic-on-11"]["actual"]["procedure"] == "clausal"
    assert results["control-horn-logic-on-11"]["actual"]["fragment"] == ["horn"]


def test_runner_restores_the_flags():
    previous = {key: get_setting(key) for key in ("LOGIC", "DEFEASIBLE", "BUILTINS")}
    run_all(load_sample(SAMPLE))
    assert {key: get_setting(key) for key in previous} == previous
