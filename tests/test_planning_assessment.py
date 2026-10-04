"""Planning assessment (plan task E8): the rows of a case, from invented measurements only.

Every unit, count, date and input in this file is invented. Nothing here reads a flood layer, a table of a real
case or a real unit, and no component of a real unit is computed. What is real is what every assessment carries
unchanged from the two signed protocol files: the weights, the anchors, the thresholds and the class rules.
The expected values are worked out by hand from the numbers the protocols state.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import pytest
from shapely.geometry import MultiPolygon, box

from floodguard import planning_assessment as pa
from floodguard.normalisation import NormalisationError
from floodguard.planning_overlay import (
    SCHEMA_RELATIVE_PATH,
    load_overlay_schema,
    overlay_problems,
)
from floodguard.scoring import SCORE_COMPONENTS
from floodguard.wording_lint import lint_texts, load_rules, python_strings

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
V1A, V1B, RECEIPTS = DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json", DOCS / "RECEIPTS.jsonl"

# The signed numbers the hand calculations use (protocol v1a scoring_frame; protocol v1b national anchors).
FLOOD_ANCHOR = 0.20
P10, P75, P90 = 0.351416, 0.454083, 0.477677
WEIGHTS = (0.30, 0.25, 0.20, 0.15, 0.10)

FLOOD_NAME = "Fixture agency extent (invented, not a product)"
FLOOD_ID = "fx_agency.invented_layer"
ROUTING_ID = "fx_routing_context"
REFERENCE = date(2030, 1, 10)


@pytest.fixture(scope="module")
def rules() -> pa.AssessmentRules:
    return pa.load_assessment_rules(V1A, V1B, RECEIPTS)


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return load_overlay_schema(ROOT / SCHEMA_RELATIVE_PATH)


def case(lane: str = "OBS", tier: str = "T3", **changes: Any) -> pa.CaseSpec:
    scenario = lane != "OBS"
    base = pa.CaseSpec(
        case_id="FX-E8", kind="fixture", title_en="Invented case (fixture, not a place)",
        title_th="กรณีทดสอบ (ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)", frame="Invented units (fixture, not a place)",
        case_reference_date=REFERENCE, lane=lane, tier=tier,
        scenario_id="FX-S1" if scenario else None,
        scenario_declaration="Invented what-if: an invented layer is treated as flooded at once." if scenario else None,
        scenario_base="agency_product_as_provided" if scenario else None,
        fixture_notice="Fixture, not a place: every unit, input and date is invented.")
    return replace(base, **changes)


def flood(acquired: date | None = date(2030, 1, 11)) -> pa.FloodInputSpec:
    return pa.FloodInputSpec(FLOOD_ID, FLOOD_NAME, acquired, "2030-01-11T00:00:00Z")


def closure(rules: pa.AssessmentRules) -> pa.ClosureSpec:
    return pa.ClosureSpec("closure_rule_v1", rules.reference_closure_level)


def unit(number: int = 1, **changes: Any) -> pa.UnitMeasurements:
    """An invented unit. Its default numbers give five components that can be worked out by hand."""

    base: dict[str, Any] = dict(
        unit_id=f"FX-U{number:02d}", unit_name_en=f"Invented unit {number:02d} (fixture, not a place)",
        unit_name_th=f"หน่วยทดสอบ {number:02d} (ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)",
        flooded_non_permanent_water_land_area=3.0, non_permanent_water_land_area=40.0,
        unit_residents=1200.0, residents_inside_flood_extent={"minus": 450.0, "as_provided": 480.0, "plus": 510.0},
        access_gap_inputs={
            "hospital": {"mode": "vehicle", "threshold_minutes": 30, "baseline_access_residents": 1100.0, "newly_lost_residents": 300.0},
            "main_road_entry": {"mode": "vehicle", "threshold_minutes": 15, "baseline_access_residents": 1150.0, "newly_lost_residents": 350.0},
        },
        residents_losing_all_routes=200.0, residents_with_baseline_route=1150.0,
        children_0_14=200.0, older_60_plus=330.0, age_residents=1200.0,
        unit_valid_coverage=0.95, coverage_by_construction=False,
        residents_connected_to_the_graph=1150.0, connected_residents_without_a_hospital_route=46.0,
        hospitals_reachable_at_baseline=2,
        v2=pa.V2TriggerInputs(link_isolation=False, serving_facility=False, recurrence_flag=False),
    )
    base.update(changes)
    return pa.UnitMeasurements(**base)


def lineage(rights_level: str = "public") -> list[dict[str, Any]]:
    def item(input_id: str, role: str, name: str, acquired: str | None = None, level: str = "public") -> dict[str, Any]:
        return {"input_id": input_id, "role": role, "name": name, "source_product": None, "acquisition_date": acquired,
                "sha256": hashlib.sha256(input_id.encode("ascii")).hexdigest(), "rights_level": level,
                "licence": "none: invented fixture input", "attribution": "FloodGuard fixture (invented, not a source)",
                "change_notice": None, "source_timestamp": "invented"}

    return [item(FLOOD_ID, "flood_input", FLOOD_NAME, "2030-01-11", rights_level),
            item(ROUTING_ID, "routing_context", "Fixture routing context (invented road graph)")]


def row_of(rules: pa.AssessmentRules, measurements: pa.UnitMeasurements, spec: pa.CaseSpec | None = None,
           flood_spec: pa.FloodInputSpec | None = None) -> dict[str, Any]:
    return pa.assess_unit(rules, spec or case(), flood_spec or flood(), closure(rules), measurements, routing_context_id=ROUTING_ID)


def overlay_of(rules: pa.AssessmentRules, units: list[pa.UnitMeasurements], **arguments: Any) -> dict[str, Any]:
    return pa.assemble_overlay(rules, arguments.pop("case", case()), flood(), closure(rules), units, arguments.pop("inputs", lineage()),
                               routing_context_id=ROUTING_ID, generated_at="2026-10-05T00:00:00Z", git_commit="0123abc",
                               source_name="Invented overlay (fixture, not a place)", **arguments)


# ---------------------------------------------------------------------------
# The rules are those of the protocol files in force
# ---------------------------------------------------------------------------


def test_the_rules_come_from_the_two_protocol_files_in_force(rules: pa.AssessmentRules) -> None:
    v1a = json.loads(V1A.read_text(encoding="utf-8"))
    v1b = json.loads(V1B.read_text(encoding="utf-8"))
    assert "central passability" in v1b["ensemble_grid"]["headline_rule"]["reference_cell"]
    assert rules.reference_closure_level == "central"
    assert rules.v2_dependent_share_percentile == v1a["class_rules"]["v2"]["parameters"]["national_dependent_share_percentile"] == "P75"
    assert rules.v2_dependent_share_min == v1b["national_vulnerability_anchors"]["values"]["P75"] == P75
    assert rules.v2_isolated_residents_min == 500
    assert rules.headline_class_retention_min == 0.6
    assert rules.reporting_frames["mae_sai"] == tuple(v1a["case_portfolio"]["mae_sai_reporting_frame"]["units"])
    assert rules.binding.frame.flood_anchor == FLOOD_ANCHOR
    assert tuple(rules.binding.frame.weights[name] for name in SCORE_COMPONENTS) == WEIGHTS


def test_nothing_is_read_from_a_protocol_that_is_not_in_force(tmp_path: Path) -> None:
    """Guardrail GR5: no rule object exists unless both files are signed and recorded in RECEIPTS.jsonl."""

    for name in ("planning_protocol_v1a.json", "planning_protocol_v1b.json", "RECEIPTS.jsonl"):
        shutil.copy(DOCS / name, tmp_path / name)
    edited = (tmp_path / "planning_protocol_v1b.json").read_bytes().replace(b'"status": "signed"', b'"status": "signed" ', 1)
    (tmp_path / "planning_protocol_v1b.json").write_bytes(edited)
    with pytest.raises(NormalisationError, match="not in force"):
        pa.load_assessment_rules(tmp_path / "planning_protocol_v1a.json", tmp_path / "planning_protocol_v1b.json", tmp_path / "RECEIPTS.jsonl")
    receipts = [line for line in (DOCS / "RECEIPTS.jsonl").read_text(encoding="utf-8").splitlines()
                if "planning_protocol_v1b_sha256" not in line]
    shutil.copy(DOCS / "planning_protocol_v1b.json", tmp_path / "planning_protocol_v1b.json")
    (tmp_path / "RECEIPTS.jsonl").write_text("\n".join(receipts) + "\n", encoding="utf-8")
    with pytest.raises(NormalisationError, match="not in force"):
        pa.load_assessment_rules(tmp_path / "planning_protocol_v1a.json", tmp_path / "planning_protocol_v1b.json", tmp_path / "RECEIPTS.jsonl")


# ---------------------------------------------------------------------------
# The five components, each against a hand calculation
# ---------------------------------------------------------------------------


def test_each_component_is_the_frame_v1_value_of_invented_counts(rules: pa.AssessmentRules) -> None:
    row = row_of(rules, unit())
    components = row["components"]
    # Flood likelihood: 100 x min(1, flooded share of non-permanent-water land / 0.20); 3 of 40 is 0.075.
    assert components["flood_likelihood_0_100"]["value_0_100"] == pytest.approx(100 * (3 / 40) / FLOOD_ANCHOR) == pytest.approx(37.5)
    assert components["flood_likelihood_0_100"]["anchor"] == FLOOD_ANCHOR
    # Exposure, share only: 480 of 1,200 residents.
    assert components["exposure_0_100"]["value_0_100"] == pytest.approx(40.0)
    assert components["exposure_0_100"]["kind"] == "share_only"
    # Access gap: residents newly losing access over residents with baseline access, over the two public services.
    assert components["access_gap_0_100"]["value_0_100"] == pytest.approx(100 * (300 + 350) / (1100 + 1150))
    assert components["access_gap_0_100"]["publication_level"] == "public"
    # Road criticality: 200 of the 1,150 residents with a baseline route lose all routes.
    assert components["road_criticality_0_100"]["value_0_100"] == pytest.approx(100 * 200 / 1150)
    # Vulnerability: the dependent share (200 + 330) / 1,200 between the national P10 and P90.
    share = (200 + 330) / 1200
    assert components["vulnerability_context_0_100"]["value_0_100"] == pytest.approx(100 * (share - P10) / (P90 - P10))
    values = [components[name]["value_0_100"] for name in SCORE_COMPONENTS]
    by_hand = [37.5, 40.0, 100 * 650 / 2250, 100 * 200 / 1150, 100 * (share - P10) / (P90 - P10)]
    assert values == pytest.approx(by_hand)
    assert row["fpps_0_100"] == pytest.approx(round(sum(weight * value for weight, value in zip(WEIGHTS, by_hand)), 2)) == 36.78
    # Medium confidence, FPPS at least 35, no A, B or C threshold reached: class D.
    assert row["confidence"]["confidence_class"] == "medium" and row["confidence"]["failed_conditions"] == []
    assert (row["action_class"], row["action_reason_code"], row["would_be_class"]) == ("D", "resilience", None)
    assert row["normalisation_version"] == "planning_frame_v1"


def test_the_flood_likelihood_saturates_at_the_anchor_and_exposure_does_not_scale_with_the_batch(rules: pa.AssessmentRules) -> None:
    saturated = row_of(rules, unit(flooded_non_permanent_water_land_area=10.0))["components"]["flood_likelihood_0_100"]
    assert saturated["value_0_100"] == 100.0 and saturated["flooded_share"] == 0.25
    alone = row_of(rules, unit())["components"]
    beside_a_larger_unit = overlay_of(rules, [unit(1), unit(2, residents_inside_flood_extent={"minus": 1150.0, "as_provided": 1200.0, "plus": 1200.0})])
    assert beside_a_larger_unit["rows"][0]["components"] == alone, "a component depends on its own unit only (guardrail GR2)"


def test_the_pitch_level_adds_the_shelter_service_and_says_so(rules: pa.AssessmentRules) -> None:
    services = dict(unit().access_gap_inputs)
    services["ddpm_located_shelter"] = {"mode": "walking", "threshold_minutes": 30, "baseline_access_residents": 700.0, "newly_lost_residents": 150.0}
    record = row_of(rules, unit(access_gap_inputs=services))["components"]["access_gap_0_100"]
    assert record["publication_level"] == "pitch"
    assert record["value_0_100"] == pytest.approx(100 * (300 + 350 + 150) / (1100 + 1150 + 700))
    with pytest.raises(pa.PlanningAssessmentError, match="pitch level"):
        overlay_of(rules, [unit(access_gap_inputs=services)])


def test_the_access_counts_come_from_the_table_row_and_a_stored_ratio_is_refused() -> None:
    row = {
        "unit_id": "FX-U01", "residents": 1200.0, "demand_cells": 12,
        "access": {"hospital": {"mode": "vehicle", "residents_connected_to_the_graph": 1150.0, "residents_with_a_baseline_route": 1104.0,
                                "thresholds_minutes": {"30": {"baseline_access_residents": 1100.0, "newly_lost_residents": 300.0}}}},
        "access_gap_inputs": {
            "hospital": {"mode": "vehicle", "threshold_minutes": 30, "baseline_access_residents": 1100.0, "newly_lost_residents": 300.0},
            "main_road_entry": {"mode": "vehicle", "threshold_minutes": 15, "baseline_access_residents": 1150.0, "newly_lost_residents": 350.0}},
        "road_criticality_inputs": {"residents_losing_all_routes": 200.0, "residents_with_baseline_route": 1150.0},
    }
    counts = pa.access_counts_from_e5_row(row, ["hospital", "main_road_entry"])
    assert counts["access_gap_inputs"] == row["access_gap_inputs"] and counts["residents"] == 1200.0
    assert (counts["residents_losing_all_routes"], counts["residents_with_baseline_route"]) == (200.0, 1150.0)
    assert counts["connected_residents_without_a_hospital_route"] == 46.0
    # The first task E5 table held the route ratio, which is the road-criticality component divided by 100.
    for stored in ({"share_losing_all_routes": 0.17}, {"routes": {"newly_lost_share": 0.3}}, {"road_criticality_0_100": 17.4},
                   {"loss_ratio": 0.2}):
        with pytest.raises(pa.PlanningAssessmentError, match="never from a stored ratio"):
            pa.access_counts_from_e5_row({**row, **stored}, ["hospital", "main_road_entry"])
    with pytest.raises(pa.PlanningAssessmentError, match="no counts for the service"):
        pa.access_counts_from_e5_row(row, ["hospital", "main_road_entry", "ddpm_located_shelter"])
    with pytest.raises(pa.PlanningAssessmentError, match="never from a stored ratio"):
        services = {"hospital": {**row["access_gap_inputs"]["hospital"], "newly_lost_over_baseline": 0.27},
                    "main_road_entry": row["access_gap_inputs"]["main_road_entry"]}
        row_units = unit(access_gap_inputs=services)
        pa.component_records(pa.load_assessment_rules(V1A, V1B, RECEIPTS).binding.frame, row_units)


def test_the_age_counts_come_from_the_table_row_and_not_from_its_stated_share() -> None:
    row = {"unit_id": "FX-U01", "residents": 1200.0, "children_0_14": 200.0, "older_60_plus": 330.0,
           "dependent_share": 0.99, "dependent_share_unavailable_reason": None}
    assert pa.age_counts_from_e7_row(row) == {"children_0_14": 200.0, "older_60_plus": 330.0, "age_residents": 1200.0}
    empty = pa.age_counts_from_e7_row({**row, "residents": None, "dependent_share_unavailable_reason": "no_valid_age_cell"})
    assert empty == {"children_0_14": None, "older_60_plus": None, "age_residents": None}


# ---------------------------------------------------------------------------
# Class rule v1 is binding: each boundary
# ---------------------------------------------------------------------------


# Values in the order of SCORE_COMPONENTS: flood likelihood, exposure, access gap, road criticality, vulnerability.
BOUNDARIES = [
    ((100, 70, 70, 0, 0), "A", "life_safety_exposure"),           # exposure >= 70 and access gap >= 70
    ((100, 69.99, 70, 0, 0), "C", "essential_service_access"),     # just under the A exposure: C (65 / 50)
    ((100, 70, 69.99, 0, 0), "C", "essential_service_access"),     # just under the A access gap
    ((100, 0, 55, 75, 0), "B", "critical_route_access"),           # road criticality >= 75 and access gap >= 55
    ((100, 0, 55, 74.99, 0), "D", "resilience"),
    ((100, 0, 54.99, 75, 0), "D", "resilience"),
    ((100, 65, 50, 0, 0), "C", "essential_service_access"),        # exposure >= 65 and access gap >= 50
    ((100, 64.99, 50, 0, 0), "D", "resilience"),
    ((100, 65, 49.99, 0, 0), "D", "resilience"),
    ((100, 20, 0, 0, 0), "D", "resilience"),                       # FPPS exactly 35.00
    ((100, 19.96, 0, 0, 0), "E", "low_priority_score"),            # FPPS 34.99
    ((100, 100, 100, 100, 100), "A", "life_safety_exposure"),      # FPPS 100: A is the first rule that matches
    ((0, 0, 0, 0, 0), "E", "low_priority_score"),                  # FPPS 0
]


@pytest.mark.parametrize(("numbers", "action_class", "reason_code"), BOUNDARIES)
def test_class_rule_v1_at_each_boundary(rules: pa.AssessmentRules, numbers: tuple[float, ...], action_class: str, reason_code: str) -> None:
    header = pa.frame_record(rules.binding.frame)
    values = dict(zip(SCORE_COMPONENTS, (float(number) for number in numbers)))
    block = pa.scoring_block(values, "medium", False, header)
    assert (block["action_class"], block["action_reason_code"]) == (action_class, reason_code)
    assert block["fpps_0_100"] == pytest.approx(round(sum(weight * value for weight, value in zip(WEIGHTS, numbers)), 2))
    assert block["would_be_class"] is None, "a would-be class exists for a low-confidence row only"
    low = pa.scoring_block(values, "low", False, header)
    assert (low["action_class"], low["action_reason_code"]) == ("E", "low_confidence")
    assert low["would_be_class"] == action_class, "the scorer rerun with confidence medium; never binding"
    assert low["fpps_0_100"] == block["fpps_0_100"]


def test_leave_one_component_out_renormalises_the_other_four_weights(rules: pa.AssessmentRules) -> None:
    header = pa.frame_record(rules.binding.frame)
    numbers = (20.0, 80.0, 60.0, 0.0, 0.0)
    block = pa.scoring_block(dict(zip(SCORE_COMPONENTS, numbers)), "medium", False, header)
    for position, dropped in enumerate(SCORE_COMPONENTS):
        kept = [(weight, value) for index, (weight, value) in enumerate(zip(WEIGHTS, numbers)) if index != position]
        expected = sum(weight * value for weight, value in kept) / sum(weight for weight, _value in kept)
        assert block["leave_one_component_out"][dropped]["fpps_0_100"] == pytest.approx(round(expected, 2))
    # With all five the FPPS is 6 + 20 + 12 = 38: class C. Without the exposure it is 18 / 0.75 = 24, under 35: class E.
    assert block["fpps_0_100"] == 38.0 and block["leave_one_component_out"]["exposure_0_100"]["fpps_0_100"] == 24.0
    assert block["action_class"] == "C" and block["leave_one_component_out"]["exposure_0_100"]["action_class"] == "E"


# ---------------------------------------------------------------------------
# Confidence rule v1, guardrail GR1, the would-be class
# ---------------------------------------------------------------------------


def test_low_confidence_forces_class_e_with_its_reason_code(rules: pa.AssessmentRules) -> None:
    high_values = dict(
        flooded_non_permanent_water_land_area=12.0, residents_inside_flood_extent={"minus": 950.0, "as_provided": 960.0, "plus": 970.0},
        access_gap_inputs={
            "hospital": {"mode": "vehicle", "threshold_minutes": 30, "baseline_access_residents": 1100.0, "newly_lost_residents": 900.0},
            "main_road_entry": {"mode": "vehicle", "threshold_minutes": 15, "baseline_access_residents": 1150.0, "newly_lost_residents": 900.0}},
    )
    medium = row_of(rules, unit(**high_values))
    assert (medium["action_class"], medium["would_be_class"]) == ("A", None)
    row = row_of(rules, unit(hospitals_reachable_at_baseline=0, **high_values))
    assert row["confidence"]["confidence_class"] == "low" and row["confidence"]["failed_conditions"] == ["C8_hospital"]
    assert (row["action_class"], row["action_reason_code"]) == ("E", "low_confidence")
    assert row["fpps_0_100"] == medium["fpps_0_100"]
    assert row["would_be_class"] == "A", "what the class would be with confidence medium; never binding"
    assert row["class_v2"]["result"] == "E" and row["class_v2"]["binding"] is False
    # Each of the other conditions a unit can fail on its own measurements.
    failing = {
        "C3_coverage": unit(unit_valid_coverage=0.79),
        "C4_input_uncertainty": unit(residents_inside_flood_extent={"minus": 300.0, "as_provided": 480.0, "plus": 481.0}),
        "C7_baseline_no_route": unit(connected_residents_without_a_hospital_route=116.0),
    }
    for condition, measurements in failing.items():
        found = row_of(rules, measurements)
        assert found["confidence"]["failed_conditions"] == [condition], condition
        assert (found["action_class"], found["action_reason_code"], found["would_be_class"]) == ("E", "low_confidence", "D")
    # C7 is the E0 definition on one unit: 116 of 1,150 connected residents is above 10 percent, 115 is not.
    assert row_of(rules, unit(connected_residents_without_a_hospital_route=115.0))["confidence"]["confidence_class"] == "medium"
    assert pa.baseline_no_route_share(0.0, 0.0) == 1.0, "nobody connected: the share is 1, as the E0 spike defines it"
    with pytest.raises(pa.PlanningAssessmentError, match="more residents are without a route"):
        pa.baseline_no_route_share(10.0, 11.0)


def test_guardrail_gr1_a_unit_under_100_residents_gets_no_class(rules: pa.AssessmentRules) -> None:
    small = unit(unit_residents=99.0, residents_inside_flood_extent={"minus": 40.0, "as_provided": 44.0, "plus": 48.0})
    row = row_of(rules, small)
    assert row["confidence"]["guardrail_gr1"] == {
        "id": "GR1_minimum_denominators", "applies": True, "unit_residents_min_for_class": 100.0,
        "no_binding_class": True, "no_would_be_class": True, "no_v2_class": True}
    assert row["confidence"]["confidence_class"] == "low" and "C6_residents" in row["confidence"]["failed_conditions"]
    assert (row["action_class"], row["action_reason_code"], row["would_be_class"]) == (None, "insufficient_denominator", None)
    assert row["class_v2"]["result"] is None and row["class_v2"]["trigger_evidence"] == []
    assert row["fpps_0_100"] is not None, "the FPPS is still stated; only the class is withheld"
    assert all(entry["action_class"] is None for entry in row["leave_one_component_out"].values())
    at_the_minimum = row_of(rules, unit(unit_residents=100.0, residents_inside_flood_extent={"minus": 40.0, "as_provided": 44.0, "plus": 48.0}))
    assert at_the_minimum["confidence"]["guardrail_gr1"]["applies"] is False and at_the_minimum["action_class"] is not None


def test_a_component_the_protocol_states_no_value_for_is_left_out_and_the_row_is_low(rules: pa.AssessmentRules) -> None:
    no_land = row_of(rules, unit(flooded_non_permanent_water_land_area=0.0, non_permanent_water_land_area=0.0))
    assert no_land["components"]["flood_likelihood_0_100"] is None
    assert no_land["confidence"]["failed_conditions"] == ["C5_components"]
    assert no_land["confidence"]["measurements"]["component_status"]["flood_likelihood_0_100"] == "not_computed"
    assert (no_land["fpps_0_100"], no_land["action_class"], no_land["action_reason_code"]) == (None, "E", "low_confidence")
    assert no_land["would_be_class"] is None and no_land["leave_one_component_out"] is None
    assert any("flood_likelihood_0_100 is not computed" in line for line in no_land["assumptions"])
    no_age = row_of(rules, unit(children_0_14=None, older_60_plus=None, age_residents=None))
    assert no_age["components"]["vulnerability_context_0_100"] is None and no_age["class_v2"]["result"] == "E"
    nobody_with_access = dict(unit().access_gap_inputs)
    nobody_with_access = {name: {**counts, "baseline_access_residents": 0.0, "newly_lost_residents": 0.0}
                          for name, counts in nobody_with_access.items()}
    assert row_of(rules, unit(access_gap_inputs=nobody_with_access))["components"]["access_gap_0_100"] is None


def test_coverage_by_construction_is_refused_outside_the_case_the_protocol_grants(rules: pa.AssessmentRules) -> None:
    with pytest.raises(pa.PlanningAssessmentError, match="by construction"):
        row_of(rules, unit(coverage_by_construction=True, unit_valid_coverage=None))


def test_an_obs_row_that_is_not_event_aligned_is_class_e(rules: pa.AssessmentRules) -> None:
    """Guardrail GR7. Ten days from the reference date is outside the window of three."""

    row = row_of(rules, unit(), flood_spec=flood(date(2030, 1, 20)))
    assert row["temporal_relation"] == "dated_other" and row["confidence"]["failed_conditions"] == ["C2_recency"]
    assert (row["action_class"], row["action_reason_code"], row["would_be_class"]) == ("E", "low_confidence", "D")
    assert row_of(rules, unit(), flood_spec=flood(date(2030, 1, 13)))["temporal_relation"] == "event_aligned"


def test_a_scenario_row_carries_scenario_confidence_and_its_declaration(rules: pa.AssessmentRules) -> None:
    spec = case("SCN", "T1")
    row = row_of(rules, unit(), spec=spec)
    assert row["confidence"]["confidence_kind"] == "scenario"
    assert row["confidence"]["basis"]["C1_tier"] == row["confidence"]["basis"]["C2_recency"] == "by_scenario_declaration"
    assert row["scenario"] == {"id": "FX-S1", "declaration": spec.scenario_declaration}
    with pytest.raises(pa.PlanningAssessmentError, match="scenario declaration"):
        row_of(rules, unit(), spec=replace(spec, scenario_declaration=None))
    with pytest.raises(pa.PlanningAssessmentError, match="scenario declaration"):
        row_of(rules, unit(), spec=case(scenario_id="FX-S1", scenario_declaration="a declaration on an observed row"))


def test_a_protocol_case_takes_its_lane_tier_date_and_declaration_from_protocol_v1a(rules: pa.AssessmentRules) -> None:
    v1a = json.loads(V1A.read_text(encoding="utf-8"))
    lanes = {row["lane"]: row for row in v1a["evidence_tier_model"]["lanes"]}
    se1 = pa.case_spec_from_protocol(rules, "SE1", title_en="t", title_th="t", frame="f", scenario_base="agency_product_as_provided")
    assert (se1.lane, se1.tier, se1.case_reference_date, se1.kind) == ("SCN-ENV", "T1", None, "portfolio_case")
    assert se1.scenario_id == "SCN-ENV" and se1.scenario_declaration.startswith(lanes["SCN-ENV"]["definition"])
    assert lanes["SCN-ENV"]["display_text"] in se1.scenario_declaration
    o2 = pa.case_spec_from_protocol(rules, "O2", title_en="t", title_th="t", frame="f", scenario_base="agency_product_as_provided")
    assert (o2.lane, o2.tier, o2.case_reference_date) == ("OBS", "T3", date(2024, 10, 22))
    assert o2.scenario_id is None and o2.scenario_declaration is None and o2.scenario_base is None
    with pytest.raises(pa.PlanningAssessmentError, match="not a case"):
        pa.case_spec_from_protocol(rules, "AOI-05", title_en="t", title_th="t", frame="f")


# ---------------------------------------------------------------------------
# Class rule v2: a labelled secondary axis
# ---------------------------------------------------------------------------


def v2_of(rules: pa.AssessmentRules, **arguments: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(unit_id="FX-U01", fpps=60.0, exposure=50.0, confidence_class="medium", gr1_applies=False,
                                action_class="D", dependent_share=0.40, triggers=pa.V2TriggerInputs(
                                    link_isolation=False, serving_facility=False, recurrence_flag=False))
    base.update(arguments)
    return pa.class_v2(rules, **base)


def test_v2_is_the_first_trigger_met_in_the_order_e_a_b_c_d(rules: pa.AssessmentRules) -> None:
    every = pa.V2TriggerInputs(link_isolation=True, serving_facility=True, recurrence_flag=True)
    result = v2_of(rules)
    assert (result["class_rule_version"], result["label"], result["binding"]) == ("class_rule_v2", "secondary", False)
    assert [item["trigger"] for item in result["trigger_evidence"]] == ["E", "A", "B", "C", "D"]
    assert result["result"] == "no_v2_trigger" and not any(item["met"] for item in result["trigger_evidence"])
    # E: low confidence, exposure under 10, or FPPS under 35.
    assert v2_of(rules, confidence_class="low", action_class="E", triggers=every)["result"] == "E"
    assert v2_of(rules, exposure=9.99, triggers=every)["result"] == "E"
    assert v2_of(rules, exposure=10.0)["result"] == "no_v2_trigger"
    assert v2_of(rules, fpps=34.99, triggers=every)["result"] == "E"
    assert v2_of(rules, fpps=None, exposure=None, confidence_class="low", action_class="E")["result"] == "E"
    # A: the v1 class is A and the dependent share is at or above the national P75.
    assert v2_of(rules, action_class="A", dependent_share=P75, triggers=every)["result"] == "A"
    assert v2_of(rules, action_class="A", dependent_share=P75 - 1e-6, triggers=every)["result"] == "B"
    assert v2_of(rules, action_class="B", dependent_share=0.9)["result"] == "no_v2_trigger"
    # B, C and D in that order, each from its own input.
    assert v2_of(rules, triggers=pa.V2TriggerInputs(link_isolation=True, serving_facility=True, recurrence_flag=True))["result"] == "B"
    assert v2_of(rules, triggers=pa.V2TriggerInputs(link_isolation=False, serving_facility=True, recurrence_flag=True))["result"] == "C"
    assert v2_of(rules, triggers=pa.V2TriggerInputs(link_isolation=False, serving_facility=False, recurrence_flag=True))["result"] == "D"
    assert v2_of(rules, gr1_applies=True, triggers=every) == {
        "class_rule_version": "class_rule_v2", "label": "secondary", "binding": False, "result": None, "trigger_evidence": []}


def test_v2_states_no_result_that_depends_on_a_trigger_nobody_evaluated(rules: pa.AssessmentRules) -> None:
    unknown = pa.V2TriggerInputs()
    # Trigger E stands first: the result is E whatever the others are, and they are written as not evaluated.
    low = v2_of(rules, confidence_class="low", action_class="E", triggers=unknown)
    assert low["result"] == "E"
    not_evaluated = {item["trigger"]: item for item in low["trigger_evidence"] if item["evidence"].startswith("Not evaluated")}
    assert set(not_evaluated) == {"B", "D"}, "C needs medium confidence, so it is not met on a low row; B and D were not evaluated"
    assert not_evaluated["B"]["met"] is False and "trigger E stands before it" in not_evaluated["B"]["evidence"]
    assert {item["trigger"]: item["met"] for item in low["trigger_evidence"]} == {"E": True, "A": False, "B": False, "C": False, "D": False}
    by_exposure = v2_of(rules, exposure=5.0, triggers=unknown)
    assert by_exposure["result"] == "E"
    assert {item["trigger"] for item in by_exposure["trigger_evidence"] if item["evidence"].startswith("Not evaluated")} == {"B", "C", "D"}
    assert v2_of(rules, action_class="A", dependent_share=0.5, triggers=unknown)["result"] == "A"
    # A medium row with an FPPS of 35 or more, an exposure of 10 or more and no trigger A: B decides, and nobody evaluated it.
    with pytest.raises(pa.V2NotEvaluableError) as refused:
        v2_of(rules, triggers=unknown)
    assert refused.value.rows == ({"unit_id": "FX-U01", "triggers_not_evaluated": ["B", "C", "D"]},)
    with pytest.raises(pa.V2NotEvaluableError) as refused:
        v2_of(rules, triggers=pa.V2TriggerInputs(link_isolation=False, serving_facility=False))
    assert refused.value.rows[0]["triggers_not_evaluated"] == ["D"]
    assert v2_of(rules, triggers=pa.V2TriggerInputs(link_isolation=True))["result"] == "B"
    # An overlay with such a row is not written, and the error names every unit concerned.
    with pytest.raises(pa.V2NotEvaluableError) as refused:
        overlay_of(rules, [unit(1), unit(2, v2=unknown), unit(3, v2=unknown)])
    assert [row["unit_id"] for row in refused.value.rows] == ["FX-U02", "FX-U03"]


# ---------------------------------------------------------------------------
# Measurements from geometry, cells and a graph (all invented)
# ---------------------------------------------------------------------------


def test_residents_are_counted_by_cell_centre_and_coverage_by_area() -> None:
    extent = MultiPolygon([box(0, 0, 100, 100)])
    cells = [
        {"unit_id": "FX-U01", "residents": 10.0, "x": 50.0, "y": 50.0},
        {"unit_id": "FX-U01", "residents": 20.0, "x": 100.0, "y": 100.0},   # on the corner of the extent: covered
        {"unit_id": "FX-U01", "residents": 40.0, "x": 100.1, "y": 50.0},
        {"unit_id": "FX-U02", "residents": 80.0, "x": 500.0, "y": 500.0},
        {"unit_id": None, "residents": 160.0, "x": 50.0, "y": 50.0},        # a cell that counts for no unit
    ]
    assert pa.residents_by_unit(cells) == {"FX-U01": 70.0, "FX-U02": 80.0}
    assert pa.residents_by_unit(cells, extent) == {"FX-U01": 30.0, "FX-U02": 0.0}
    assert pa.residents_by_unit(cells, MultiPolygon()) == {"FX-U01": 0.0, "FX-U02": 0.0}
    assert pa.unit_coverage(box(0, 0, 200, 100), extent) == pytest.approx(0.5)
    assert pa.unit_coverage(box(0, 0, 50, 50), extent) == 1.0 and pa.unit_coverage(box(0, 0, 50, 50), MultiPolygon()) == 0.0


def test_the_hospitals_a_unit_can_reach_are_counted_on_the_baseline_graph() -> None:
    edges = [{"from_node": "a", "to_node": "b"}, {"from_node": "b", "to_node": "c"}, {"from_node": "x", "to_node": "y"}]
    hospitals = [
        {"facility_id": "H1", "node_id": "a", "snap_distance_m": 0.0},
        {"facility_id": "H2", "node_id": "y", "snap_distance_m": 20.0},
        {"facility_id": "H3", "node_id": "c", "snap_distance_m": 100.1},   # snapped beyond the facility limit of 100 m
        {"facility_id": "H4", "node_id": "nowhere", "snap_distance_m": 0.0},
    ]
    cells = [
        {"unit_id": "FX-U01", "residents": 5.0, "node_id": "c", "snap_distance_m": 10.0},
        {"unit_id": "FX-U02", "residents": 5.0, "node_id": "c", "snap_distance_m": 10.0},
        {"unit_id": "FX-U02", "residents": 5.0, "node_id": "x", "snap_distance_m": 250.0},
        {"unit_id": "FX-U03", "residents": 5.0, "node_id": "x", "snap_distance_m": 250.1},   # beyond the limit of 250 m
        {"unit_id": "FX-U04", "residents": 0.0, "node_id": "a", "snap_distance_m": 0.0},     # nobody lives there
        {"unit_id": "FX-U05", "residents": 5.0, "node_id": None, "snap_distance_m": None},
        {"unit_id": None, "residents": 5.0, "node_id": "a", "snap_distance_m": 0.0},
    ]
    assert pa.hospitals_reachable_at_baseline(cells, edges, hospitals) == {
        "FX-U01": 1, "FX-U02": 2, "FX-U03": 0, "FX-U04": 0, "FX-U05": 0}


# ---------------------------------------------------------------------------
# The overlay, the guardrails and the verifier
# ---------------------------------------------------------------------------


def test_an_assembled_overlay_is_accepted_by_the_validator_bound_to_the_protocols(rules: pa.AssessmentRules, schema: dict[str, Any]) -> None:
    units = [
        unit(1),
        unit(2, unit_residents=99.0, residents_inside_flood_extent={"minus": 40.0, "as_provided": 44.0, "plus": 48.0}),
        unit(3, hospitals_reachable_at_baseline=0, v2=pa.V2TriggerInputs()),
        unit(4, flooded_non_permanent_water_land_area=0.0, non_permanent_water_land_area=0.0, v2=pa.V2TriggerInputs()),
        unit(5, v2=pa.V2TriggerInputs(link_isolation=True)),
    ]
    overlay = overlay_of(rules, units)
    assert overlay_problems(overlay, schema, binding=rules.binding) == []
    assert overlay["dataset_mode"] == "fixture_demo" and overlay["publication_eligibility"] == "public"
    assert overlay["official_warning"] is False and overlay["accepted_fpps"] is None
    assert [row["action_class"] for row in overlay["rows"]] == ["D", None, "E", "E", "D"]
    assert [row["class_v2"]["result"] for row in overlay["rows"]] == ["no_v2_trigger", None, "E", "E", "B"]
    assert all(row["headline_stability"] == {"guardrail": "GR8_headline_stability", "status": "not_evaluated",
                                             "class_retention": None, "class_retention_min": 0.6} for row in overlay["rows"])
    lineages = {json.dumps(row["lineage"], sort_keys=True) for row in overlay["rows"]}
    assert lineages == {json.dumps({"flood_input_id": FLOOD_ID, "routing_context_id": ROUTING_ID, "closure_rule": {
        "version": "closure_rule_v1", "level": "central", "closure_basis": f"modelled_from_{FLOOD_ID}"}}, sort_keys=True)}
    assert rules.binding.frame.lane_disclosure in overlay["assumptions"]
    assert any("Class E never means safe" in line for line in overlay["assumptions"])
    report = pa.guardrail_report(overlay, rules, reporting_units=[item.unit_id for item in units], lane="OBS")
    assert all(entry["result"] == "PASS" for entry in report.values())
    assert report["GR1_minimum_denominators"]["units_without_a_class"] == 1
    assert report["GR2_no_max_normalisation"]["rows_checked"] == 4
    assert report["GR2_no_max_normalisation"]["rows_with_a_component_not_computed"] == 1
    # The rights level is the minimum across the lineage (guardrail GR6).
    assert overlay_of(rules, units, inputs=lineage("local"))["publication_eligibility"] == "local"


def test_the_guardrails_refuse_a_missing_unit_a_second_lineage_and_a_changed_record(rules: pa.AssessmentRules) -> None:
    overlay = overlay_of(rules, [unit(1), unit(2)])
    with pytest.raises(pa.PlanningAssessmentError, match="exactly one row"):
        pa.guardrail_report(overlay, rules, reporting_units=["FX-U01", "FX-U02", "FX-U03"], lane="OBS")
    with pytest.raises(pa.PlanningAssessmentError, match="exactly one row"):
        pa.guardrail_report(overlay, rules, reporting_units=["FX-U01"], lane="OBS")
    other = json.loads(json.dumps(overlay))
    other["rows"][1]["lineage"]["closure_rule"]["level"] = "strict"
    with pytest.raises(pa.LanePurityError, match="GR3"):
        pa.guardrail_report(other, rules, reporting_units=["FX-U01", "FX-U02"], lane="OBS")
    scaled = json.loads(json.dumps(overlay))
    top = max(row["components"]["exposure_0_100"]["value_0_100"] for row in scaled["rows"])
    scaled["rows"][0]["components"]["exposure_0_100"]["value_0_100"] *= 100 / top
    scaled["rows"][1]["components"]["exposure_0_100"]["value_0_100"] *= 100 / top
    with pytest.raises(pa.PlanningAssessmentError, match="GR2"):
        pa.guardrail_report(scaled, rules, reporting_units=["FX-U01", "FX-U02"], lane="OBS")
    with pytest.raises(pa.PlanningAssessmentError, match="each once"):
        overlay_of(rules, [unit(1), unit(1)])
    with pytest.raises(pa.PlanningAssessmentError, match="flood input of the rows"):
        overlay_of(rules, [unit(1)], inputs=lineage()[1:])


def test_lane_purity_compares_what_two_stages_say_of_one_input(rules: pa.AssessmentRules) -> None:
    same = pa.lane_purity_record({"flood_input_id": ("fx:layer", "fx:layer"), "closure_extent_sha256": ("a" * 64, "a" * 64)})
    assert same["result"] == "PASS" and same["compared"]["closure_extent_sha256"] == {"value": "a" * 64, "same": True}
    with pytest.raises(pa.LanePurityError, match="closure_extent_sha256"):
        pa.lane_purity_record({"flood_input_id": ("fx:layer", "fx:layer"), "closure_extent_sha256": ("a" * 64, "b" * 64)})
    with pytest.raises(pa.LanePurityError, match="routing_context"):
        pa.lane_purity_record({"routing_context_canonical_sha256": (None, None)})
    with pytest.raises(pa.LanePurityError, match="nothing was compared"):
        pa.lane_purity_record({})


def test_a_written_overlay_is_verified_and_a_changed_one_is_not(rules: pa.AssessmentRules, schema: dict[str, Any], tmp_path: Path) -> None:
    units = [unit(1), unit(2, hospitals_reachable_at_baseline=0)]
    overlay = overlay_of(rules, units)
    target = tmp_path / "overlay.json"
    written = pa.write_assessment(overlay, target, schema, rules)
    assert written["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest() and b"\r" not in target.read_bytes()
    hashes = {item["input_id"]: item["sha256"] for item in overlay["inputs"]}
    checked = pa.verify_assessment(target, schema, rules, reporting_units=["FX-U01", "FX-U02"], lane="OBS", expected_input_sha256=hashes)
    assert checked["verified"] is True and checked["problems"] == []
    assert checked["summary"]["binding_class_by_lane_column"]["OBS"]["D"] == 1
    assert checked["summary"]["reason_code_by_lane_column"]["OBS"]["low_confidence"] == 1
    # Another lineage hash, a missing unit, and a class the rule does not give are each found.
    wrong = pa.verify_assessment(target, schema, rules, reporting_units=["FX-U01", "FX-U02"], lane="OBS",
                                 expected_input_sha256={**hashes, FLOOD_ID: "f" * 64})
    assert wrong["verified"] is False and wrong["problems"][0]["code"] == "lineage_hash"
    missing = pa.verify_assessment(target, schema, rules, reporting_units=["FX-U01", "FX-U02", "FX-U03"], lane="OBS")
    assert missing["verified"] is False and missing["problems"][0]["code"] == "guardrail"
    changed = json.loads(target.read_text(encoding="ascii"))
    changed["rows"][1]["action_class"] = "D"
    target.write_text(json.dumps(changed), encoding="ascii")
    refused = pa.verify_assessment(target, schema, rules, reporting_units=["FX-U01", "FX-U02"], lane="OBS")
    assert refused["verified"] is False
    assert {"class_above_e_without_medium_confidence", "low_confidence_forces_e"} <= {item["code"] for item in refused["problems"]}
    # A refused overlay is never written.
    from floodguard.planning_overlay import PlanningOverlayError

    with pytest.raises(PlanningOverlayError):
        pa.write_assessment(changed, tmp_path / "refused.json", schema, rules)
    assert not (tmp_path / "refused.json").exists()


def test_the_open_points_are_listed_and_the_module_wording_passes_the_shared_lint() -> None:
    assert [point["id"] for point in pa.OPEN_POINTS] == ["E8-OP1", "E8-OP2", "E8-OP3", "E8-OP4", "E8-OP5"]
    assert all(point["for_the_owners"].strip() and point["signed_files_say"].strip() for point in pa.OPEN_POINTS)
    lint = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    sources = ["src/floodguard/planning_assessment.py", "scripts/build_planning_assessment.py"]
    items = [(name, "\n".join(python_strings((ROOT / name).read_text(encoding="utf-8")))) for name in sources]
    items.append(("docs/planning_assessment.md", (ROOT / "docs" / "planning_assessment.md").read_text(encoding="utf-8")))
    assert lint_texts(items, lint) == []
