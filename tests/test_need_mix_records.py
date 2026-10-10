"""The committed records of the need mix of case SE1: the cache receipt, the mix, the squares and the picture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from floodguard import equity_by_age as eba
from floodguard import need_mix as nm

ROOT = Path(__file__).resolve().parents[1]
CACHE_RECEIPT = ROOT / "outputs" / "cell_outcomes" / "se1_mae_sai_v1_receipt.json"
MIX = ROOT / "outputs" / "need_mix" / "se1_mae_sai_v1.json"
SQUARES = ROOT / "outputs" / "need_mix" / "se1_mae_sai_squares_500m_v1.json"
MAP_RECORD = ROOT / "outputs" / "need_mix" / "se1_mae_sai_need_map_v1.json"
PUBLISHED = ROOT / "outputs" / "planning_v1" / "overlays" / "planning_assessment_overlay_se1_mae_sai.json"
REGISTRATION = ROOT / "outputs" / "equity_by_age" / "se1_mae_sai_registration_ensemble_v1.json"
NEEDS = (nm.IN_THE_WATER, nm.DRY_CUT_OFF, nm.DRY_LOSES_HOSPITAL)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def mix() -> dict:
    if not MIX.exists():
        pytest.skip("the need mix has not been written")
    return json.loads(MIX.read_text(encoding="utf-8"))


def test_the_cache_receipt_names_its_checks_against_the_runs_of_record() -> None:
    if not CACHE_RECEIPT.exists():
        pytest.skip("the cell outcomes have not been computed")
    receipt = json.loads(CACHE_RECEIPT.read_text(encoding="utf-8"))
    assert receipt["official_warning"] is False and receipt["can_feed_decision_layer"] is False and receipt["confidence_class"] == "low"
    assert receipt["source_timestamp"] and receipt["assumptions"] and receipt["limits"] and len(receipt["runs"]) == 9
    checks = receipt["checks"]
    assert checks["as_provided_runs_against_the_e5_table"] == {**checks["as_provided_runs_against_the_e5_table"], "result": "PASS", "values_compared": 48}
    against = checks["every_run_against_the_registered_ensemble"]
    assert against["result"] == "PASS" and against["values_compared"] == 288
    assert sha(ROOT / against["registered_receipt"]["path"]) == against["registered_receipt"]["sha256"], "the run of record is the one it was checked against"
    assert receipt["cache_outside_git"]["path"].startswith("<external_data_workspace>/") and len(receipt["cache_outside_git"]["sha256"]) == 64
    assert b"\r" not in CACHE_RECEIPT.read_bytes()


def test_the_mix_says_what_it_is_and_is_bound_to_what_it_was_made_from(mix: dict) -> None:
    assert mix["official_warning"] is False and mix["can_feed_decision_layer"] is False and mix["confidence_class"] == "low"
    assert mix["source_timestamp"] and mix["assumptions"] and mix["limits"] and "not a planning class" in mix["not_a_class"]
    assert [item["type"] for item in mix["need_types"]] == list(nm.NEED_TYPES)
    assert mix["made_from"]["published_result_file"]["sha256"] == sha(PUBLISHED), "the published result file is unchanged"
    assert mix["made_from"]["cache_receipt"]["sha256"] == sha(CACHE_RECEIPT)
    assert mix["checks"]["counts_of_the_published_run_against_the_published_file"]["values_compared"] == 32
    assert any("Class E never means safe" in limit for limit in mix["limits"]) and b"\r" not in MIX.read_bytes()


def test_every_resident_is_counted_once_and_the_tambons_add_up_to_the_district(mix: dict) -> None:
    published = {row["unit_id"]: row for row in json.loads(PUBLISHED.read_text(encoding="utf-8"))["rows"]}
    assert set(mix["by_tambon"]) == set(published)
    for vintage in ("worldpop_2020", "rescaled_2024"):
        district = mix["district"][vintage]["in_the_published_run"]
        assert sum(entry["residents"] for entry in district["by_type"].values()) == pytest.approx(district["residents"], abs=0.3)
        for name in nm.NEED_TYPES:
            assert sum(block[vintage]["in_the_published_run"]["by_type"][name]["residents"] for block in mix["by_tambon"].values()) == pytest.approx(
                district["by_type"][name]["residents"], abs=0.5)
    for unit_id, block in mix["by_tambon"].items():
        row = published[unit_id]
        entry = block["worldpop_2020"]["in_the_published_run"]
        assert block["binding_class_v1_of_the_published_file"] == row["action_class"]
        inputs = row["components"]
        assert entry["by_type"][nm.IN_THE_WATER]["residents"] == pytest.approx(inputs["exposure_0_100"]["inputs"]["residents_inside_flood_extent"], abs=0.06)
        assert entry["hidden_by_the_order"]["cut_off_in_the_water_or_dry"] == pytest.approx(
            inputs["road_criticality_0_100"]["inputs"]["residents_losing_all_routes"], abs=0.06)
        spread = block["worldpop_2020"]["over_the_nine_runs"]
        for name in nm.NEED_TYPES:
            assert spread[name]["residents_lowest"] <= entry["by_type"][name]["residents"] <= spread[name]["residents_highest"]


def test_the_three_tambons_of_one_class_have_three_different_leading_needs(mix: dict) -> None:
    """The finding the page leads with, read from the record: one class, three mixes."""

    leading = {}
    for unit_id, block in mix["by_tambon"].items():
        if block["binding_class_v1_of_the_published_file"] == "D":
            by_type = block["worldpop_2020"]["in_the_published_run"]["by_type"]
            leading[block["unit_name_en"]] = max(NEEDS, key=lambda name: by_type[name]["share"])
    assert leading == {"Mae Sai": nm.IN_THE_WATER, "Si Mueang Chum": nm.IN_THE_WATER, "Ban Dai": nm.DRY_LOSES_HOSPITAL}
    ko_chang = next(block for block in mix["by_tambon"].values() if block["unit_name_en"] == "Ko Chang")
    assert ko_chang["worldpop_2020"]["in_the_published_run"]["by_type"][nm.NOT_AFFECTED]["residents"] == 0.0
    in_the_water_in_class_e = sum(block["worldpop_2020"]["in_the_published_run"]["by_type"][nm.IN_THE_WATER]["residents"]
                                  for block in mix["by_tambon"].values() if block["binding_class_v1_of_the_published_file"] == "E")
    assert in_the_water_in_class_e > 1000, "class E never means safe"


def test_the_squares_hold_the_residents_of_the_district_and_the_picture_is_the_one_recorded(mix: dict) -> None:
    squares = json.loads(SQUARES.read_text(encoding="utf-8"))
    assert squares["made_from"]["need_mix"]["sha256"] == sha(MIX) and squares["grid"]["side_m"] == 500.0
    assert squares["official_warning"] is False and squares["source_timestamp"] and squares["limits"]
    listed = squares["squares"]
    assert len(listed) == mix["squares_file"]["squares"]
    district = mix["district"]["worldpop_2020"]["in_the_published_run"]
    assert sum(item["residents"] for item in listed) == pytest.approx(district["residents"], abs=len(listed) * 0.06)
    assert all(item["leading_type"] in nm.NEED_TYPES for item in listed if item["residents"] > 0)
    assert all(item["x_min"] % 500 == 0 and item["y_min"] % 500 == 0 for item in listed)
    if not MAP_RECORD.exists():
        pytest.skip("the picture has not been drawn")
    record = json.loads(MAP_RECORD.read_text(encoding="utf-8"))
    assert sha(ROOT / record["picture"]["path"]) == record["picture"]["sha256"]
    assert record["made_from"]["need_mix"]["sha256"] == sha(MIX) and record["made_from"]["squares"]["sha256"] == sha(SQUARES)
    assert record["official_warning"] is False and record["limits"]
    changing = sum(1 for item in listed if item["residents"] >= 1.0 and not item["leading_type_is_the_same_in_all_nine_runs"])
    assert record["drawn"]["squares_whose_leading_type_changes_over_the_nine_runs"] == changing


def test_the_registration_comparison_over_the_ensemble_applies_the_rule_with_the_smallest_size() -> None:
    if not REGISTRATION.exists():
        pytest.skip("the registration comparison over the ensemble has not been written")
    record = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["confidence_class"] == "low" and record["limits"] and record["assumptions"]
    assert record["ensemble"]["cells"] == 180 and len(record["counts"]) == 18
    assert record["made_from"]["cache_receipt"]["sha256"] == sha(CACHE_RECEIPT)
    assert "Thai nationals" in record["source"]["ages_cover"]
    for comparison in eba.COMPARISONS:
        differences = [count["loses_a_hospital_within_30_minutes"][comparison]["difference_of_rates"] for count in record["counts"]]
        block = record["loses_a_hospital_within_30_minutes"][comparison]
        assert block["rule_with_the_smallest_size"] == eba.gap_statement(
            [value for value in differences for _cell in range(10)], min_abs_difference=eba.MIN_GAP_SHARE)
        assert block["rule_with_the_smallest_size"]["runs"] == 180
    older = record["loses_a_hospital_within_30_minutes"]["60_plus_vs_under_60"]
    assert older["rule_with_the_smallest_size"]["may_state_a_gap"] is True and older["difference_of_rates"]["lowest"] > 0
    assert any("not a statistical interval" in limit for limit in record["limits"]) and b"\r" not in REGISTRATION.read_bytes()
