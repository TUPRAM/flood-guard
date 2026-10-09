"""Tests of the second class reading: the order of the triggers, and the committed record."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from floodguard import class_v2_reading as v2

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "outputs" / "class_v2_reading" / "se1_mae_sai_v1.json"
BASE = {"met_e": False, "met_a": False, "fpps": 60.0, "confidence_class": "medium",
        "isolated_residents": 0.0, "facility_hit": False, "recurrence_share": 0.0}


def reading(**changes: object) -> dict:
    return v2.evaluate(**{**BASE, **changes})


def test_the_first_trigger_met_in_the_order_gives_the_letter() -> None:
    assert reading()["result"] == v2.NO_V2_TRIGGER
    assert reading(isolated_residents=500.0, facility_hit=True, recurrence_share=0.5)["result"] == "B"
    assert reading(isolated_residents=499.9, facility_hit=True, recurrence_share=0.5)["result"] == "C"
    assert reading(recurrence_share=0.20)["result"] == "D" and reading(recurrence_share=0.1999)["result"] == v2.NO_V2_TRIGGER
    assert reading(met_e=True, isolated_residents=9999.0)["result"] == "E"
    assert reading(met_a=True, isolated_residents=9999.0)["result"] == "A"


def test_c_and_d_need_the_score_and_c_needs_confidence_above_low() -> None:
    assert reading(fpps=34.9, facility_hit=True, recurrence_share=0.9)["triggers"] == {"E": False, "A": False, "B": False, "C": False, "D": False}
    assert reading(confidence_class="low", facility_hit=True)["triggers"]["C"] is False
    assert reading(fpps=None, facility_hit=True, recurrence_share=0.9)["result"] == v2.NO_V2_TRIGGER


def test_a_trigger_nobody_evaluated_leaves_the_result_open_unless_an_earlier_one_is_met() -> None:
    assert reading(isolated_residents=None)["result"] == v2.NOT_EVALUATED
    assert reading(facility_hit=None)["result"] == v2.NOT_EVALUATED
    assert reading(recurrence_share=None)["result"] == v2.NOT_EVALUATED
    assert reading(isolated_residents=600.0, facility_hit=None, recurrence_share=None)["result"] == "B"
    assert reading(met_e=True, isolated_residents=None)["result"] == "E"
    with pytest.raises(v2.ClassV2ReadingError):
        reading(confidence_class="high")
    with pytest.raises(v2.ClassV2ReadingError):
        reading(recurrence_share=1.2)
    with pytest.raises(v2.ClassV2ReadingError):
        reading(isolated_residents=-1.0)


def test_committed_reading_is_bound_to_the_published_file_and_changes_no_binding_class() -> None:
    if not RESULT.exists():
        pytest.skip("the second reading has not been written")
    record = json.loads(RESULT.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False
    assert record["confidence_class"] == "low" and record["source_timestamp"] and record["assumptions"] and record["limits"]
    assert "stays binding" in record["binding"] and b"\r" not in RESULT.read_bytes()
    published = ROOT / record["inputs"]["published_result_file"]["path"]
    assert hashlib.sha256(published.read_bytes()).hexdigest() == record["inputs"]["published_result_file"]["sha256"]
    overlay = {row["unit_id"]: row for row in json.loads(published.read_text(encoding="utf-8"))["rows"]}
    assert set(record["units"]) == set(overlay) and len(record["units"]) == 8
    differs = 0
    for unit_id, row in record["units"].items():
        source = overlay[unit_id]
        assert row["binding_class_v1"] == source["action_class"] and row["fpps_0_100"] == source["fpps_0_100"]
        assert source["class_v2"]["result"] in ("not_evaluated", "E")  # the published file is unchanged
        earlier = {item["trigger"]: item["met"] for item in source["class_v2"]["trigger_evidence"]}
        facilities = row["trigger_C"]["serving_facilities"]
        again = v2.evaluate(
            met_e=earlier["E"], met_a=earlier["A"], fpps=row["fpps_0_100"], confidence_class=source["confidence"]["confidence_class"],
            isolated_residents=row["trigger_B"]["largest_number_of_residents_one_link_isolates"],
            facility_hit=any(item["point_inside_the_flood_extent"] or item["no_vehicle_route_to_a_main_road_entry_in_the_flooded_run"] for item in facilities),
            recurrence_share=row["trigger_D"]["share"])
        assert again["result"] == row["second_reading_v2"] and again["triggers"] == row["triggers"]
        for item in facilities:
            if item["kind"] == v2.SHELTER_KIND:  # pitch level: no row identifier and no count in a public file
                assert "facility_id" not in item and "residents_of_the_unit_it_is_nearest_for" not in item and item["pitch_level"]
            else:
                assert item["residents_of_the_unit_it_is_nearest_for"] >= v2.SERVED_RESIDENTS_MIN
        differs += int(not row["same_as_v1"])
    assert record["counts"]["second_reading_differs_from_v1"] == differs
    assert len(record["top_20_links"]) == 20


def test_a_shelter_row_in_a_public_file_carries_no_identifier_and_no_count() -> None:
    shelter = {"kind": v2.SHELTER_KIND, "facility_id": "DDPM-invented-row-1", "residents_of_the_unit_it_is_nearest_for": 1234.5,
               "point_inside_the_flood_extent": False, "no_vehicle_route_to_a_main_road_entry_in_the_flooded_run": True}
    public = v2.public_facility_row(shelter)
    assert "facility_id" not in public and "residents_of_the_unit_it_is_nearest_for" not in public
    assert public["no_vehicle_route_to_a_main_road_entry_in_the_flooded_run"] is True and public["point_inside_the_flood_extent"] is False
    hospital = {"kind": "hospital", "facility_id": "OSM-way-1", "residents_of_the_unit_it_is_nearest_for": 500.0,
                "point_inside_the_flood_extent": False, "no_vehicle_route_to_a_main_road_entry_in_the_flooded_run": False}
    assert v2.public_facility_row(hospital) == hospital
    text = (ROOT / "docs" / "class_v2_reading.md").read_text(encoding="utf-8")
    assert "9,300" not in text and "DDPM-gd002" not in RESULT.read_text(encoding="utf-8")
