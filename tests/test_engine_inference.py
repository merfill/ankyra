"""Tests for the pluggable Inference seam (docs/logic_layer.md)."""

from __future__ import annotations

import pytest

from ankyra.core.models import Morphism, Rule, Theory
from ankyra.engine.inference import (
    ClausalInference,
    HornInference,
    select_inference,
)

_Q = ("q", "", "", False, "neutral")
_R = ("r", "", "", False, "neutral")


def _theory() -> Theory:
    return Theory(
        morphisms=[Morphism(predicate="p")],
        rules=[Rule(conditions=[Morphism(predicate="p")], consequence=Morphism(predicate="q"))],
    )


def test_select_inference_switches_on_the_logic_flag():
    assert isinstance(select_inference(logic_enabled=False, has_goals=True), HornInference)
    assert isinstance(select_inference(logic_enabled=True, has_goals=False), HornInference)
    assert isinstance(select_inference(logic_enabled=True, has_goals=True), ClausalInference)


def test_horn_inference_entails_and_exposes_the_closure():
    inference = HornInference()
    assert inference.entails(_theory(), _Q)
    assert _Q in inference.closure_keys(_theory())
    assert not inference.entails(_theory(), _R)


def test_clausal_inference_entails():
    inference = ClausalInference()
    assert inference.entails(_theory(), _Q)
    assert not inference.entails(_theory(), _R)


def test_clausal_inference_has_no_fact_closure():
    with pytest.raises(NotImplementedError):
        ClausalInference().closure_keys(_theory())
