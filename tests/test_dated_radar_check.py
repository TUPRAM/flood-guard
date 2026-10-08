"""Tests of the radar check against the dated agency layer: the counting on invented cells, and the committed records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import dated_radar_check as drc

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "dated_radar_check"
REFERENCE = OUTPUTS / "mae_sai_20241022_reference_v1.json"
RESULT = OUTPUTS / "mae_sai_20241022_v1.json"
RECEIPT = OUTPUTS / "mae_sai_20241022_v1_receipt.json"
PLAN = "docs/proposal_execution/dated_radar_check_plan_v1.md"
GROUPS = {"built_up": (50,), "cropland": (40,)}


def invented() -> dict[str, np.ndarray]:
    """A 6 by 8 district with a 3 by 4 block of agency water and one cell of permanent water."""

    reference = np.zeros((6, 8), dtype=bool)
    reference[1:4, 2:6] = True
    district = np.ones((6, 8), dtype=bool)
    district[:, 7] = False
    water = np.zeros((6, 8), dtype=bool)
    water[1, 2] = True
    season = np.zeros((6, 8), dtype=bool)
    season[1:4, 2:5] = True
    return {"reference": reference, "district": district, "water": water, "season": season}


def test_interior_cells_are_those_whose_neighbours_agree_and_are_known() -> None:
    cells = invented()
    interior = drc.interior_cells(cells["reference"], cells["district"])
    # Inside the 3 by 4 block only the middle row away from the block's rim is uniform.
    assert interior[2, 3] and interior[2, 4]
    assert not interior[1, 3] and not interior[2, 2] and not interior[2, 5]
    # The rim of the raster, cells beside the layer and cells beside the district edge are not interior.
    assert not interior[0, 0] and not interior[5, 3] and not interior[4, 1] and not interior[2, 6]
    assert int(interior.sum()) == 2
    wide = np.zeros((5, 5), dtype=bool)
    assert drc.interior_cells(wide, np.ones((5, 5), dtype=bool)).sum() == 9  # dry cells far from any layer are interior
    assert not drc.interior_cells(np.zeros((2, 2), dtype=bool), np.ones((2, 2), dtype=bool)).any()
    with pytest.raises(drc.DatedRadarCheckError):
        drc.interior_cells(np.zeros((3, 3), dtype=bool), np.ones((3, 4), dtype=bool))


def test_frame_counts_leave_permanent_water_out_and_count_the_season_overlap() -> None:
    cells = invented()
    counts = drc.frame_counts(cells["district"], cells["water"], cells["reference"], cells["season"], cell_area_km2=0.0001)
    assert counts["district_cells"] == 42 and counts["frame_cells"] == 41
    assert counts["reference_cells_in_the_district"] == 12 and counts["reference_cells_in_the_frame"] == 11
    assert counts["reference_cells_on_permanent_water_left_out"] == 1
    assert counts["reference_cells_inside_the_season_layer"] == 9
    assert counts["reference_share_inside_the_season_layer"] == 0.75
    assert counts["reference_km2_in_the_frame"] == pytest.approx(0.0011)
    with pytest.raises(drc.DatedRadarCheckError):
        drc.frame_counts(cells["district"], cells["water"], cells["reference"], cells["season"], cell_area_km2=0)


def test_method_agreement_counts_no_answer_as_not_flagged_and_names_the_reference() -> None:
    cells = invented()
    compared = cells["district"] & ~cells["water"]
    candidate = np.zeros((6, 8), dtype="uint8")
    candidate[1:4, 2:4] = 1  # flags half of the block
    candidate[5, 0] = 1  # and one dry cell
    candidate[3, 5] = 255  # no answer on one agency-water cell
    land_cover = np.full((6, 8), 40, dtype="uint8")
    land_cover[:, :2] = 50
    interior = drc.interior_cells(cells["reference"], cells["district"])
    agreement = drc.method_agreement(candidate, cells["reference"], compared, interior, land_cover, GROUPS, cell_area_km2=0.0001)
    strict = agreement["all_compared_cells"]["strict_no_answer_counts_as_not_a_candidate"]
    assert (strict["tp"], strict["fp"], strict["fn"]) == (5, 1, 6)
    assert agreement["all_compared_cells"]["on_answered_cells"]["fn"] == 5
    assert "reference_wet_km2" in strict and "optical_wet_km2" not in json.dumps(agreement)
    assert drc.share_flagged(agreement) == pytest.approx(5 / 11, abs=1e-6)
    assert agreement["by_land_cover_worldcover_2021"]["built_up"]["strict_no_answer_counts_as_not_a_candidate"]["fp"] == 1
    assert set(agreement["by_land_cover_worldcover_2021"]) == {"built_up", "cropland", "other"}


def reading(recall: float | None) -> dict[str, object]:
    return {"all_compared_cells": {"strict_no_answer_counts_as_not_a_candidate": {"recall": recall}}}


def test_fixed_sentences_apply_the_two_rules_of_the_plan_as_written() -> None:
    sentences = drc.fixed_sentences({
        "primary": {"a": reading(0.04), "b": reading(0.30), "c": reading(0.20), "d": reading(None)},
        "second": {"a": reading(0.09), "b": reading(0.10), "c": reading(0.25), "d": reading(0.5)},
    })["by_method"]
    assert sentences["a"]["does_not_see_the_water_of_that_date"] and sentences["a"]["the_image_before_decides_the_result"]
    assert not sentences["b"]["does_not_see_the_water_of_that_date"] and sentences["b"]["the_image_before_decides_the_result"]
    assert not sentences["c"]["does_not_see_the_water_of_that_date"] and not sentences["c"]["the_image_before_decides_the_result"]
    assert not sentences["d"]["does_not_see_the_water_of_that_date"] and not sentences["d"]["the_image_before_decides_the_result"]
    with pytest.raises(drc.DatedRadarCheckError):
        drc.fixed_sentences({"primary": {"a": reading(0.1)}})
    with pytest.raises(drc.DatedRadarCheckError):
        drc.fixed_sentences({"primary": {"a": reading(0.1)}, "second": {"b": reading(0.1)}})


@pytest.mark.parametrize("path", [REFERENCE, RESULT, RECEIPT])
def test_committed_records_carry_the_required_fields(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path.name} has not been written")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    assert record["can_feed_decision_layer"] is False and record["confidence_class"] == "low"
    assert record["generated_at_utc"].endswith("Z") and record["source_timestamp"]
    assert record["plan"]["path"] == PLAN
    assert b"\r" not in path.read_bytes()
    if path != RECEIPT:
        assert record["assumptions"] and record["limits"] and "local level" in record["rights_note"]


def test_the_reference_was_built_before_any_radar_and_holds_district_counts_only() -> None:
    if not REFERENCE.exists():
        pytest.skip("the reference stage has not been run")
    record = json.loads(REFERENCE.read_text(encoding="utf-8"))
    assert record["radar_read"] is False and record["district"]["adm2_pcode"] == "TH5709"
    counts = record["counts"]
    assert counts["frame_cells"] == counts["district_cells"] - counts["permanent_water_cells_left_out"]
    assert counts["reference_cells_in_the_frame"] <= counts["reference_cells_in_the_district"]
    text = REFERENCE.read_text(encoding="utf-8")
    assert "adm3" not in text and "TH5701" not in text and "TH5705" not in text


def test_the_result_is_bound_to_the_reference_and_computes_no_score() -> None:
    if not RESULT.exists():
        pytest.skip("the compare stage has not been run")
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert result["reference_record"]["sha256"] == hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    assert result["plan"]["sha256"] == reference["plan"]["sha256"] == hashlib.sha256((ROOT / PLAN).read_bytes()).hexdigest()
    assert reference["generated_at_utc"] < result["generated_at_utc"]
    assert receipt["outputs"]["outputs/dated_radar_check/mae_sai_20241022_v1.json"]["sha256"] == hashlib.sha256(RESULT.read_bytes()).hexdigest()
    assert set(result["readings"]) == {"primary", "second"} and "not accuracy" in result["label"]
    for methods in result["readings"].values():
        assert set(methods) == {"un_spider", "m1_literal", "m1_v2"}
        for agreement in methods.values():
            strict = agreement["all_compared_cells"]["strict_no_answer_counts_as_not_a_candidate"]
            assert strict["tp"] + strict["fn"] == result["compared_cells"]["reference_wet_cells"]
            assert strict["cells"] == result["compared_cells"]["cells"]
    assert drc.fixed_sentences(result["readings"]) == result["fixed_sentences_of_the_plan"]

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for item in value.values() for key in keys(item)}
        if isinstance(value, list):
            return {key for item in value for key in keys(item)}
        return set()

    assert not {key for key in keys(result) if "fpps" in key.lower() or "action_class" in key.lower() or "adm3" in key.lower()}
