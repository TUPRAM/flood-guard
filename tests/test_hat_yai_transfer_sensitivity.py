from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/hat_yai_transfer_sensitivity.py"
SPEC = importlib.util.spec_from_file_location("hat_yai_transfer_sensitivity", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
access_effect = MODULE.access_effect
select_candidate_closures = MODULE.select_candidate_closures


def test_overlap_threshold_and_grade_assumption_are_monotone() -> None:
    edges = [
        {"edge_id": "short", "length_m": 100, "bridge": "no", "tunnel": "no"},
        {"edge_id": "long", "length_m": 100, "bridge": "no", "tunnel": "no"},
        {"edge_id": "bridge", "length_m": 100, "bridge": "yes", "tunnel": "no"},
    ]
    overlaps = [
        {"edge_id": "short", "intersection_length_m": 5, "intersection_fraction": 0.05},
        {"edge_id": "long", "intersection_length_m": 60, "intersection_fraction": 0.6},
        {"edge_id": "bridge", "intersection_length_m": 30, "intersection_fraction": 0.3},
    ]

    all_ids, _ = select_candidate_closures(overlaps, edges, 0)
    twenty_ids, review = select_candidate_closures(overlaps, edges, 20)
    fifty_ids, _ = select_candidate_closures(overlaps, edges, 50)
    grade_ids, grade_review = select_candidate_closures(
        overlaps, edges, 20, exclude_mapped_grade_separation=True
    )

    assert all_ids == ["bridge", "long", "short"]
    assert twenty_ids == ["bridge", "long"]
    assert fifty_ids == ["long"]
    assert grade_ids == ["long"]
    assert review["tagged_bridge_or_tunnel_intersections"] == 1
    assert grade_review["excluded_mapped_grade_edges"] == 1


def test_overlap_rejects_unknown_duplicate_or_inconsistent_edges() -> None:
    edges = [{"edge_id": "a", "length_m": 10, "bridge": "no", "tunnel": "no"}]
    good = {"edge_id": "a", "intersection_length_m": 5, "intersection_fraction": 0.5}

    with pytest.raises(ValueError, match="duplicate or unknown"):
        select_candidate_closures([good, good], edges, 0)
    with pytest.raises(ValueError, match="duplicate or unknown"):
        select_candidate_closures([{**good, "edge_id": "other"}], edges, 0)
    with pytest.raises(ValueError, match="invalid centerline"):
        select_candidate_closures([{**good, "intersection_fraction": 0.9}], edges, 0)
    with pytest.raises(ValueError, match="minimum overlap"):
        select_candidate_closures([good], edges, -1)


def test_access_effect_keeps_unknown_and_loss_denominators_separate() -> None:
    result = {"node_results": [
        {"total_population": 10, "snap_status": "connected", "normal_access_minutes": 10,
         "scenario_access_minutes": None, "loses_15_min_access": True,
         "loses_30_min_access": True, "loses_60_min_access": True},
        {"total_population": 20, "snap_status": "connected", "normal_access_minutes": 20,
         "scenario_access_minutes": 40, "loses_15_min_access": False,
         "loses_30_min_access": True, "loses_60_min_access": False},
        {"total_population": 30, "snap_status": "missing_graph_coverage", "normal_access_minutes": None,
         "scenario_access_minutes": None, "loses_15_min_access": False,
         "loses_30_min_access": False, "loses_60_min_access": False},
    ]}

    effect = access_effect(result)

    assert effect["modelled_residents_2020"] == 60
    assert effect["unknown_connector_population"] == 30
    assert effect["new_all_route_loss_population"] == 10
    assert effect["new_threshold_loss_population"] == {"15": 10, "30": 30, "60": 10}
    assert effect["comparable_finite_route_population"] == 20
    assert effect["mean_delay_minutes_among_comparable_finite_routes"] == 20
