"""The committed records of buildings in the water against residents in the water."""

from __future__ import annotations

import json
import re
from pathlib import Path

from floodguard import buildings_in_water as bw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/buildings_in_water"
OUTLINES = json.loads((OUT / "outlines_v1.json").read_text(encoding="utf-8"))
CHIPS = json.loads((OUT / "theos2_chips_v1.json").read_text(encoding="utf-8"))
DISTRICT = json.loads((OUT / "se1_mae_sai_v1.json").read_text(encoding="utf-8"))
NEED_MIX = json.loads((ROOT / "outputs/need_mix/se1_mae_sai_v1.json").read_text(encoding="utf-8"))
SHA = re.compile(r"^[0-9a-f]{64}$")


def test_every_record_carries_the_fields_of_every_output() -> None:
    for record in (OUTLINES, CHIPS, DISTRICT):
        assert record["source_timestamp"] and record["generated_at_utc"].endswith("Z")
        assert record["confidence_class"] == "low" and record["confidence_basis"]
        assert record["operational_status"] == "non_operational"
        assert record["official_warning"] is False and record["can_feed_decision_layer"] is False
        assert record["plan"]["path"] == "docs/proposal_execution/buildings_in_water_plan_v1.md"
        assert (ROOT / record["plan"]["path"]).exists() and SHA.match(record["plan"]["sha256"])
        assert record["limits"]
    assert DISTRICT["label"] == "scenario, not an observation"


def test_the_outlines_stay_outside_git_and_are_named_with_their_source() -> None:
    source = OUTLINES["source"]
    assert source["url"].startswith("https://data.source.coop/") and "ODbL" in source["licence"] and "CC BY 4.0" in source["licence"]
    assert OUTLINES["rule_for_using_an_outline"] == {"min_area_m2": bw.MIN_AREA_M2, "min_confidence_where_given": bw.MIN_CONFIDENCE}
    assert set(OUTLINES["areas"]) == {"sukhothai", "chip_003", "mae_sai"}
    for area in OUTLINES["areas"].values():
        assert area["outlines_read"] >= area["used_by_the_rule_of_the_plan"] > 0
        assert sum(area["by_source"].values()) == area["outlines_read"]
        assert SHA.match(area["file_outside_git"]["sha256"])
    assert not list(OUT.glob("*.gpkg")) and not list(OUT.glob("*.fgb")) and not list(OUT.glob("*.geojson"))
    register = (ROOT / "docs/proposal_execution/SOURCES_AND_RIGHTS.md").read_text(encoding="utf-8")
    assert "Note of 11 October 2026: open building outlines" in register and source["credit"] in " ".join(register.split())
    for record in (CHIPS, DISTRICT):
        assert source["credit"] in record["credits"]
        assert SHA.match(record["outlines"]["sha256"])


def test_the_chips_give_both_water_rules_and_three_readings() -> None:
    assert set(CHIPS["chips"]) == {"sukhothai", "chip_003"}
    assert "neither is called right" in CHIPS["what_this_is"]
    for chip in CHIPS["chips"].values():
        assert chip["buildings_counted"] <= chip["outlines_used"]
        assert set(chip["by_water_rule"]) == {"rule_v1", "rule_v2"}
        for rule in chip["by_water_rule"].values():
            assert rule["buildings_assessed"] + rule["buildings_not_assessed"] == chip["buildings_counted"]
            wet = rule["buildings_in_the_water"]
            quarter, half, three = (wet[f"at_{share}_of_the_ring"]["buildings"] for share in ("0.25", "0.5", "0.75"))
            assert quarter >= half >= three and half <= rule["buildings_assessed"]
            readings = rule["residents_in_the_water"]
            assert {"centre_rule", "area", "buildings"} <= set(readings)
            assert readings["residents_compared"] <= readings["residents"]
            for name in ("centre_rule", "area", "buildings"):
                assert 0.0 <= readings[name]["share"] <= 1.0
            assert rule["on_the_centre_rule"] == bw.verdict(readings["buildings_minus_centre_rule_points"])


def test_the_district_is_checked_against_the_published_need_mix() -> None:
    assert DISTRICT["published_level"] == "as_provided" and set(DISTRICT["by_flood_level"]) == set(DISTRICT["flood_levels"])
    rows = DISTRICT["by_flood_level"]["as_provided"]
    tambons = {key: row for key, row in rows.items() if key != "district"}
    assert set(tambons) == set(NEED_MIX["by_tambon"])
    assert sum(row["buildings"] for row in tambons.values()) == rows["district"]["buildings"] == DISTRICT["buildings"]["in_a_demand_cell"]
    assert DISTRICT["buildings"]["in_a_demand_cell"] + DISTRICT["buildings"]["not_within_reach_of_a_cell"] == DISTRICT["buildings"]["outlines_used"]
    # The centre rule on all cells is the published count of residents in the water, to the rounding of a tambon.
    published = NEED_MIX["district"]
    text = json.dumps(published)
    centre = rows["district"]["residents_in_the_water_by_the_centre_rule_all_cells"]
    assert any(str(centre + step) in text for step in (-1, 0, 1)), centre
    for key, row in rows.items():
        readings = row["on_the_cells_that_hold_a_building"]
        assert "area" not in readings
        assert row["buildings_in_the_layer"] <= row["buildings"]
        assert row["on_the_centre_rule"] == bw.verdict(readings["buildings_minus_centre_rule_points"])
    # A wider layer never holds fewer buildings.
    levels = [DISTRICT["by_flood_level"][level]["district"]["buildings_in_the_layer"] for level in ("minus", "as_provided", "plus")]
    assert levels == sorted(levels)
    named = DISTRICT["tambons_where_the_two_readings_differ_by_more_than_5_points"]
    apart = [row for row in tambons.values()
             if abs(row["on_the_cells_that_hold_a_building"]["buildings_minus_centre_rule_points"] or 0.0) > bw.DIFFERENCE_POINTS]
    assert len(named) == len(apart)
