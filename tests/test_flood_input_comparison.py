"""Tests of the figures that set one flood input beside another, on invented counts and on the committed result."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from floodguard import flood_input_comparison as fic

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "flood_input_comparison"
RESULT = OUTPUTS / "mae_sai_v1.json"
RECEIPT = OUTPUTS / "mae_sai_v1_receipt.json"


def test_set_overlap_counts_both_sides() -> None:
    assert fic.set_overlap(["a", "b", "c"], ["b", "c", "d", "e"]) == {
        "first": 3, "second": 4, "both": 2, "first_only": 1, "second_only": 2, "share_of_union_in_both": 0.4}
    assert fic.set_overlap([], [])["share_of_union_in_both"] is None


def test_spearman_agrees_with_known_cases() -> None:
    same = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0}
    assert fic.spearman(same, {key: value * 10 for key, value in same.items()}) == 1.0
    assert fic.spearman(same, {"a": 4.0, "b": 3.0, "c": 2.0, "d": 1.0}) == -1.0
    # Equal values share the mean of their ranks.
    assert fic.spearman({"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 3}) == pytest.approx(0.866025, abs=1e-6)
    # A value that does not vary has no rank correlation.
    assert fic.spearman({"a": 0, "b": 0, "c": 0}, {"a": 1, "b": 2, "c": 3}) is None
    with pytest.raises(fic.ComparisonError):
        fic.spearman({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 2, "x": 3})
    with pytest.raises(fic.ComparisonError):
        fic.spearman({"a": 1, "b": 2}, {"a": 1, "b": 2})


def test_ratio_and_largest() -> None:
    assert fic.ratio(1, 4) == 0.25 and fic.ratio(1, 0) is None
    assert fic.largest({"a": 2.0, "b": 5.0, "c": 5.0}) == {"unit_id": "b", "value": 5.0, "tied_with": ["c"]}
    assert fic.largest({"a": 0.0, "b": 0.0}) == {"unit_id": None, "value": 0.0, "tied_with": []}
    with pytest.raises(fic.ComparisonError):
        fic.largest({})


def test_compare_inputs_reports_totals_ranks_and_the_top_unit() -> None:
    first = {
        "u1": {"flooded_land_km2": 1.0, "residents_inside_extent": 10.0, "residents_losing_every_route": 0.0},
        "u2": {"flooded_land_km2": 2.0, "residents_inside_extent": 30.0, "residents_losing_every_route": 5.0},
        "u3": {"flooded_land_km2": 3.0, "residents_inside_extent": 20.0, "residents_losing_every_route": 1.0},
    }
    second = {
        "u1": {"flooded_land_km2": 10.0, "residents_inside_extent": 100.0, "residents_losing_every_route": 50.0},
        "u2": {"flooded_land_km2": 20.0, "residents_inside_extent": 300.0, "residents_losing_every_route": 10.0},
        "u3": {"flooded_land_km2": 30.0, "residents_inside_extent": 200.0, "residents_losing_every_route": 20.0},
    }
    result = fic.compare_inputs(first, second, closed_first=["e1", "e2"], closed_second=["e2", "e3", "e4"])
    assert result["closed_road_edges"]["both"] == 1 and result["closed_road_edges"]["share_of_union_in_both"] == 0.25
    assert result["flooded_land_km2"] == {"first_total": 6.0, "second_total": 60.0, "first_over_second": 0.1,
                                          "rank_correlation_of_units": 1.0}
    assert result["residents_losing_every_route"]["rank_correlation_of_units"] == -1.0
    top = result["unit_with_most_residents_losing_every_route"]
    assert (top["first"]["unit_id"], top["second"]["unit_id"], top["same"]) == ("u2", "u1", False)


def test_the_committed_result_carries_the_required_fields_and_no_score() -> None:
    if not RESULT.exists():
        pytest.skip("the comparison has not been run")
    record = json.loads(RESULT.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    assert record["can_feed_decision_layer"] is False and record["confidence_class"] == "low"
    assert record["generated_at_utc"].endswith("Z") and record["source_timestamp"]
    assert record["assumptions"] and record["limits"]
    assert record["plan"]["path"] == "docs/proposal_execution/flood_input_comparison_plan_v1.md"
    # The whole-corridor run reproduced the committed SE1 table, or nothing would have been written.
    assert record["reproduction_of_the_se1_table"]["same"] is True
    assert set(record["inputs"]) == {"season_layer_whole_corridor", "season_layer_in_frame", "un_spider", "m1_literal", "m1_v2"}
    assert len(record["unit_ids"]) == 8
    for block in record["inputs"].values():
        assert set(block["units"]) == set(record["unit_ids"])
        assert set(block["by_closure_level"]) == {"strict", "central", "permissive"}

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for item in value.values() for key in keys(item)}
        if isinstance(value, list):
            return {key for item in value for key in keys(item)}
        return set()

    assert not {key for key in keys(record) if "fpps" in key.lower() or "action_class" in key.lower() or "component" in key.lower()}
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    recorded = receipt["outputs"]["outputs/flood_input_comparison/mae_sai_v1.json"]["sha256"]
    assert hashlib.sha256(RESULT.read_bytes()).hexdigest() == recorded
    for path in (RESULT, RECEIPT):
        assert b"\r" not in path.read_bytes()
