"""Offline tests for the ProofWriter tier builder and committed samples."""

from __future__ import annotations

import pytest

from evals import build_proofwriter_sample as bw
from evals import proofwriter as pw

TIER_SIZES = {"a": 45, "b": 75, "c": 150, "d": 300}
CORE_PREFIXES = set(bw.CORE_PREFIXES)


def _rows():
    """Synthetic validation rows with enough candidates for every tier."""
    rows: list[dict] = []
    for depth in bw.CORE_DEPTHS:
        for prefix in bw.CORE_PREFIXES:
            for label in bw.LABELS:
                for k in range(8):
                    rows.append({
                        "id": f"{prefix}-OWA-D{depth}-{k}",
                        "config": f"depth-{depth}",
                        "answer": label,
                        "QDep": 0 if depth == 0 else 1,
                        "maxD": depth,
                        "NFact": 1,
                        "NRule": 1,
                        "theory": "t",
                        "question": "q",
                    })
    for k in range(100):
        for label in bw.LABELS:
            rows.append({
                "id": f"AttNonegNatLang-OWA-{k}",
                "config": "NatLang",
                "answer": label,
                "QDep": 1,
                "maxD": 3,
                "NFact": 1,
                "NRule": 1,
                "theory": "t",
                "question": "q",
            })
    for prefix in bw.CORE_PREFIXES:
        for k in range(60):
            for label in bw.LABELS:
                rows.append({
                    "id": f"{prefix}-OWA-D3-{k}",
                    "config": "depth-3ext",
                    "answer": label,
                    "QDep": 1,
                    "maxD": 3,
                    "NFact": 1,
                    "NRule": 1,
                    "theory": "t",
                    "question": "q",
                })
    return rows


def test_select_is_deterministic_per_tier():
    rows = _rows()
    for tier, size in TIER_SIZES.items():
        first = bw.select(rows, tier)
        second = bw.select(rows, tier)
        assert [r["id"] for r in first] == [r["id"] for r in second]
        assert len(first) == size


def test_select_no_id_is_reused_within_a_tier():
    rows = _rows()
    for tier in TIER_SIZES:
        ids = [r["id"] for r in bw.select(rows, tier)]
        assert len(ids) == len(set(ids))


def test_smaller_tiers_are_prefixes_of_larger_ones():
    rows = _rows()
    ids = {tier: {r["id"] for r in bw.select(rows, tier)} for tier in TIER_SIZES}
    assert ids["a"] <= ids["b"]
    assert ids["b"] <= ids["c"]
    assert ids["c"] <= ids["d"]


@pytest.mark.parametrize("tier,size", sorted(TIER_SIZES.items()))
def test_committed_tier_is_stratified(tier, size):
    rows = pw.load_sample(pw.sample_path(tier))
    assert len(rows) == size
    counts = {}
    for row in rows:
        counts[row["answer"]] = counts.get(row["answer"], 0) + 1
    assert set(counts) == set(bw.LABELS)
    assert set(counts.values()) == {size // 3}
    assert len({row["id"] for row in rows}) == size


def test_committed_tiers_add_the_right_areas():
    by_tier = {t: pw.load_sample(pw.sample_path(t)) for t in TIER_SIZES}

    def configs(rows):
        return {row["config"] for row in rows}

    def natlang(rows):
        return sum(1 for row in rows if row["prefix"] == bw.NATLANG_PREFIX)

    assert configs(by_tier["a"]) == set(pw._DEPTHS)
    assert natlang(by_tier["a"]) == 0

    assert natlang(by_tier["b"]) == 30
    assert configs(by_tier["b"]) == set(pw._DEPTHS) | {"NatLang"}

    assert natlang(by_tier["c"]) == 75
    assert sum(1 for row in by_tier["c"] if row["prefix"] in CORE_PREFIXES) == 75

    assert configs(by_tier["d"]) == set(pw._DEPTHS) | {"NatLang", "depth-3ext"}
    assert sum(1 for row in by_tier["d"] if row["config"] == "depth-3ext") == 150
