"""Tests for the L2 backend selection as seen from ``verify`` (``ANKYRA_L2_BACKEND``)."""

from __future__ import annotations

import importlib.util

import pytest

from ankyra.config.settings import setting_overrides
from ankyra.core.models import Morphism, Query, Theory
from ankyra.engine.verify import verify

_HAS_Z3 = importlib.util.find_spec("z3") is not None


def _m(predicate, subject=None, obj=None, *, neg=False):
    return Morphism(predicate=predicate, subject=subject, object=obj, negated=neg)


def _theory() -> Theory:
    return Theory(morphisms=[_m("is_a", "rex", "a")])


def _query() -> Query:
    return Query(target=_m("is_a", "rex", "a"))


def test_default_backend_is_resolution():
    with setting_overrides(LOGIC="ground"):
        verdict = verify(_theory(), _query())
    assert verdict.status == "supported"
    assert verdict.shelf == "proven"


def test_explicit_resolution_backend_decides():
    with setting_overrides(LOGIC="ground", L2_BACKEND="resolution"):
        verdict = verify(_theory(), _query())
    assert verdict.status == "supported"


def test_unknown_backend_is_refused_not_decided():
    with setting_overrides(LOGIC="ground", L2_BACKEND="nonsense"):
        verdict = verify(_theory(), _query())
    assert verdict.status == "out_of_fragment"
    assert verdict.shelf == "refused"
    assert verdict.gaps == ["out_of_fragment:l2_backend_unknown"]


@pytest.mark.skipif(_HAS_Z3, reason="the smt extra is installed, so the backend is available")
def test_smt_backend_without_z3_is_refused_not_raised():
    with setting_overrides(LOGIC="ground", L2_BACKEND="smt"):
        verdict = verify(_theory(), _query())
    assert verdict.status == "out_of_fragment"
    assert verdict.shelf == "refused"
    assert verdict.gaps == ["out_of_fragment:l2_backend_unavailable"]
