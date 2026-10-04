"""Confidence rule v1 (protocol v1a confidence_rule_v1): pure functions on invented rows.

Every row here is invented: the unit IDs start with SYN and the dates are in
2030. No test reads a flood layer or a population raster, and none computes an
FPPS or an A-E class. The thresholds are read from the signed protocol file, so
the boundary cases follow the file, not numbers typed here.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from floodguard.confidence import (
    BASIS_VALUES,
    BY_CONSTRUCTION,
    BY_SCENARIO_DECLARATION,
    CONDITION_IDS,
    FAIL,
    PASS,
    SCENARIO_BASE_AGENCY,
    SCENARIO_BASE_OWN_CANDIDATE,
    ConfidenceError,
    ConfidenceInputs,
    ConfidenceRule,
    confidence_rule_from_protocol,
    derive_confidence,
    load_confidence_rule,
    recency_days,
    t2_skill_condition,
)
from floodguard.config import VALID_CONFIDENCE_CLASSES
from floodguard.normalisation import NormalisationError
from floodguard.scoring import SCORE_COMPONENTS

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
V1A = DOCS / "planning_protocol_v1a.json"
V1B = DOCS / "planning_protocol_v1b.json"
RECEIPTS = DOCS / "RECEIPTS.jsonl"
MODULE = ROOT / "src" / "floodguard" / "confidence.py"

REFERENCE = date(2030, 1, 10)
EVALUATED_T2_INPUT = "M1-v2"
AGENCY_INPUT = "invented agency extent"
ALL_COMPUTED = {name: "computed" for name in SCORE_COMPONENTS}


@pytest.fixture(scope="module")
def protocol() -> dict[str, Any]:
    return json.loads(V1A.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rule() -> ConfidenceRule:
    return load_confidence_rule(V1A, RECEIPTS)


def row(**changes: Any) -> ConfidenceInputs:
    """An invented observed row on a dated agency extent (tier T3) that meets every condition."""

    values: dict[str, Any] = {
        "unit_id": "SYN-001",
        "lane": "OBS",
        "tier": "T3",
        "flood_input": AGENCY_INPUT,
        "scenario_base": None,
        "acquisition_date": REFERENCE,
        "case_reference_date": REFERENCE,
        "unit_valid_coverage": 0.95,
        "coverage_by_construction": False,
        "exposure_plus_one_pixel_0_100": 42.0,
        "exposure_minus_one_pixel_0_100": 35.0,
        "t2_abstention_fraction": None,
        "t2_geoid_held_out_test_iou": None,
        "component_status": dict(ALL_COMPUTED),
        "unit_residents": 5000.0,
        "baseline_vehicle_no_route_share": 0.02,
        "hospitals_reachable_at_baseline": 2,
    }
    values.update(changes)
    return ConfidenceInputs(**values)


def own_candidate_row(**changes: Any) -> ConfidenceInputs:
    """An invented observed row on an own candidate (tier T2) that meets the skill condition."""

    values = {
        "tier": "T2",
        "flood_input": EVALUATED_T2_INPUT,
        "t2_abstention_fraction": 0.05,
        "t2_geoid_held_out_test_iou": 0.55,
    }
    values.update(changes)
    return row(**values)


def scenario_row(**changes: Any) -> ConfidenceInputs:
    """An invented season-envelope scenario row (tier T1) on an agency product used as provided."""

    values = {
        "lane": "SCN-ENV",
        "tier": "T1",
        "scenario_base": SCENARIO_BASE_AGENCY,
        "acquisition_date": None,
        "case_reference_date": None,
    }
    values.update(changes)
    return row(**values)


# ---------------------------------------------------------------------------
# The rule is read from the signed file
# ---------------------------------------------------------------------------


def test_rule_thresholds_come_from_the_signed_protocol(rule: ConfidenceRule, protocol: dict[str, Any]) -> None:
    conditions = {entry["id"]: entry.get("threshold", {}) for entry in protocol["confidence_rule_v1"]["medium_requires_all"]}
    assert rule.version == protocol["confidence_rule_v1"]["version"] == "confidence_rule_v1"
    assert rule.recency_window_days == conditions["C2_recency"]["recency_window_days"]
    assert rule.unit_valid_coverage_min == conditions["C3_coverage"]["unit_valid_coverage_min"]
    uncertainty = conditions["C4_input_uncertainty"]
    assert rule.exposure_plus_minus_one_pixel_max_points == uncertainty["exposure_plus_minus_one_pixel_max_points"]
    assert rule.t2_abstention_fraction_max == uncertainty["t2_abstention_fraction_max"]
    assert rule.unit_residents_min == conditions["C6_residents"]["unit_residents_min"]
    assert rule.baseline_vehicle_no_route_share_max == conditions["C7_baseline_no_route"]["baseline_vehicle_no_route_share_max"]
    assert rule.hospitals_reachable_at_baseline_min == conditions["C8_hospital"]["hospitals_reachable_at_baseline_min"]
    skill = protocol["t2_skill_bar"]
    assert rule.skill_geoid_held_out_test_iou_min == skill["conditions"]["geoid_held_out_test_iou_min"]
    assert rule.skill_abstention_fraction_max == skill["conditions"]["mae_sai_abstention_fraction_max"]
    assert rule.skill_unit_coverage_min == skill["conditions"]["mae_sai_unit_coverage_min"]
    assert rule.skill_recency_window_days == skill["conditions"]["recency_window_days"]
    assert list(rule.skill_declared_unable_to_meet) == skill["declared_unable_to_meet"]
    assert list(rule.skill_evaluated_by_the_rule) == skill["evaluated_by_the_rule"]
    guardrail = next(entry for entry in protocol["guardrails"] if entry["id"] == "GR1_minimum_denominators")
    assert rule.gr1_unit_residents_min_for_class == guardrail["parameters"]["unit_residents_min_for_class"]
    assert tuple(conditions) == CONDITION_IDS


def test_reason_codes_are_the_ones_the_protocol_declares(rule: ConfidenceRule, protocol: dict[str, Any]) -> None:
    class_rule = protocol["class_rules"]["v1"]
    low = derive_confidence(row(hospitals_reachable_at_baseline=0), rule)
    under_minimum = derive_confidence(row(unit_residents=10), rule)
    assert low["reason_code"] in class_rule["reason_codes"]
    assert under_minimum["reason_code"] in class_rule["added_reason_code"]
    assert low["reason_code"] != under_minimum["reason_code"]


def test_rule_carries_the_hash_of_the_protocol_in_force(rule: ConfidenceRule) -> None:
    digest = hashlib.sha256(V1A.read_bytes()).hexdigest()
    assert rule.protocol_sha256 == digest
    assert json.loads(V1B.read_text(encoding="utf-8"))["depends_on"]["v1a_sha256"] == digest
    assert derive_confidence(row(), rule)["protocol_v1a_sha256"] == digest


def test_rule_is_refused_when_the_protocol_is_not_in_force(tmp_path: Path) -> None:
    receipts = tmp_path / "RECEIPTS.jsonl"
    receipts.write_text(json.dumps({"output_hashes": {"planning_protocol_v1a_sha256": "0" * 64}}) + "\n", encoding="utf-8")
    with pytest.raises(NormalisationError, match="not in force"):
        load_confidence_rule(V1A, receipts)


def _change(protocol: dict[str, Any], pointer: str, value: Any) -> dict[str, Any]:
    """Return a copy of the protocol with one value replaced (``DELETE`` removes the key)."""

    changed = deepcopy(protocol)
    node: Any = changed
    parts = pointer.split("/")
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last: Any = int(parts[-1]) if isinstance(node, list) else parts[-1]
    if value == "DELETE":
        del node[last]
    else:
        node[last] = value
    return changed


def _reading_index(protocol: dict[str, Any], reading: str) -> int:
    return next(index for index, entry in enumerate(protocol["drafter_readings"]) if entry["id"] == reading)


@pytest.mark.parametrize("pointer, value, message", [
    ("status", "draft_for_signature", "signed protocol"),
    ("confidence_rule_v1/version", "confidence_rule_v2", "implements confidence_rule_v1"),
    ("confidence_rule_v1/medium_requires_all/0/id", "C0_other", "eight conditions"),
    ("confidence_rule_v1/uses_ensemble_output", True, "no ensemble output"),
    ("confidence_rule_v1/rights_are_an_input", True, "no rights input"),
    ("confidence_rule_v1/vocabulary", ["high", "medium", "low", "none"], "vocabulary"),
    ("evidence_tier_model/tiers/2/lane", "SCN", "tiers and lanes"),
    ("evidence_tier_model/lanes/0/lane", "OBSERVED", "tiers and lanes"),
    ("confidence_rule_v1/medium_requires_all/2/threshold", "DELETE", "does not hold"),
    ("confidence_rule_v1/medium_requires_all/2/threshold/unit_valid_coverage_min", "0.8", "not a number"),
    ("confidence_rule_v1/medium_requires_all/2/threshold/unit_valid_coverage_min", True, "not a number"),
    ("confidence_rule_v1/medium_requires_all/2/threshold/unit_valid_coverage_min", -0.1, "not negative"),
    ("t2_skill_bar/conditions/geoid_held_out_test_iou_min", float("nan"), "finite"),
    ("guardrails/0/parameters/unit_residents_min_for_class", 50, "one resident threshold"),
    ("t2_skill_bar", "DELETE", "does not hold"),
    ("class_rules/v1/reason_codes/low_confidence", "DELETE", "reason codes"),
    ("class_rules/v1/added_reason_code/insufficient_denominator", "DELETE", "reason codes"),
    ("confidence_rule_v1/medium_requires_all", None, "does not hold"),
])
def test_rule_is_refused_when_the_protocol_states_another_rule(
    protocol: dict[str, Any], pointer: str, value: Any, message: str
) -> None:
    with pytest.raises(ConfidenceError, match=message):
        confidence_rule_from_protocol(_change(protocol, pointer, value))


@pytest.mark.parametrize("reading", ["DR-A07", "DR-A09"])
def test_rule_is_refused_when_a_reading_it_implements_is_not_confirmed(protocol: dict[str, Any], reading: str) -> None:
    pointer = f"drafter_readings/{_reading_index(protocol, reading)}/status"
    with pytest.raises(ConfidenceError, match=reading):
        confidence_rule_from_protocol(_change(protocol, pointer, "amended"))
    assert confidence_rule_from_protocol(protocol).protocol_sha256 is None


# ---------------------------------------------------------------------------
# Medium requires all eight conditions; low otherwise; high never
# ---------------------------------------------------------------------------


def test_medium_when_all_eight_conditions_hold(rule: ConfidenceRule) -> None:
    result = derive_confidence(row(), rule)
    assert result["confidence_class"] == "medium"
    assert result["confidence_kind"] == "observed"
    assert result["basis"] == {condition: PASS for condition in CONDITION_IDS}
    assert result["failed_conditions"] == []
    assert result["reason_code"] is None
    assert result["confidence_rule_version"] == "confidence_rule_v1"
    assert result["t2_skill_condition"] is None
    assert result["guardrail_gr1"]["applies"] is False
    assert result["measurements"]["exposure_plus_minus_one_pixel_points"] == pytest.approx(7.0)
    assert result["measurements"]["recency_days"] == 0
    assert result["thresholds"]["unit_valid_coverage_min"] == rule.unit_valid_coverage_min
    assert result["assumptions"] and all(isinstance(text, str) for text in result["assumptions"])


@pytest.mark.parametrize("changes, failed", [
    ({"acquisition_date": REFERENCE + timedelta(days=9)}, "C2_recency"),
    ({"acquisition_date": None}, "C2_recency"),
    ({"case_reference_date": None}, "C2_recency"),
    ({"unit_valid_coverage": 0.5}, "C3_coverage"),
    ({"unit_valid_coverage": None}, "C3_coverage"),
    ({"exposure_plus_one_pixel_0_100": 80.0}, "C4_input_uncertainty"),
    ({"exposure_plus_one_pixel_0_100": None}, "C4_input_uncertainty"),
    ({"exposure_minus_one_pixel_0_100": None}, "C4_input_uncertainty"),
    ({"component_status": {**ALL_COMPUTED, "access_gap_0_100": "assumed"}}, "C5_components"),
    ({"component_status": {**ALL_COMPUTED, "vulnerability_context_0_100": "not_computed"}}, "C5_components"),
    ({"baseline_vehicle_no_route_share": 0.4}, "C7_baseline_no_route"),
    ({"baseline_vehicle_no_route_share": None}, "C7_baseline_no_route"),
    ({"hospitals_reachable_at_baseline": 0}, "C8_hospital"),
    ({"hospitals_reachable_at_baseline": None}, "C8_hospital"),
])
def test_one_failed_condition_is_enough_for_low(rule: ConfidenceRule, changes: dict[str, Any], failed: str) -> None:
    result = derive_confidence(row(**changes), rule)
    assert result["confidence_class"] == "low"
    assert result["failed_conditions"] == [failed]
    assert result["basis"][failed] == FAIL
    assert result["reason_code"] == "low_confidence"
    assert [condition for condition in CONDITION_IDS if result["basis"][condition] != PASS] == [failed]


def test_boundaries_are_inclusive_on_the_side_the_protocol_names(rule: ConfidenceRule) -> None:
    step = timedelta(days=int(rule.recency_window_days))
    points = rule.exposure_plus_minus_one_pixel_max_points
    cases = [
        # (changes at the threshold, changes just beyond it, condition)
        ({"acquisition_date": REFERENCE + step}, {"acquisition_date": REFERENCE + step + timedelta(days=1)}, "C2_recency"),
        ({"acquisition_date": REFERENCE - step}, {"acquisition_date": REFERENCE - step - timedelta(days=1)}, "C2_recency"),
        ({"unit_valid_coverage": rule.unit_valid_coverage_min},
         {"unit_valid_coverage": rule.unit_valid_coverage_min - 1e-9}, "C3_coverage"),
        ({"exposure_plus_one_pixel_0_100": 20.0 + points, "exposure_minus_one_pixel_0_100": 20.0},
         {"exposure_plus_one_pixel_0_100": 20.0 + points + 0.01, "exposure_minus_one_pixel_0_100": 20.0},
         "C4_input_uncertainty"),
        # The difference is absolute: a shrunk input that exposes more residents counts the same.
        ({"exposure_plus_one_pixel_0_100": 20.0, "exposure_minus_one_pixel_0_100": 20.0 + points},
         {"exposure_plus_one_pixel_0_100": 20.0, "exposure_minus_one_pixel_0_100": 20.0 + points + 0.01},
         "C4_input_uncertainty"),
        ({"unit_residents": rule.unit_residents_min}, {"unit_residents": rule.unit_residents_min - 0.01}, "C6_residents"),
        ({"baseline_vehicle_no_route_share": rule.baseline_vehicle_no_route_share_max},
         {"baseline_vehicle_no_route_share": rule.baseline_vehicle_no_route_share_max + 1e-9}, "C7_baseline_no_route"),
        ({"hospitals_reachable_at_baseline": int(rule.hospitals_reachable_at_baseline_min)},
         {"hospitals_reachable_at_baseline": int(rule.hospitals_reachable_at_baseline_min) - 1}, "C8_hospital"),
    ]
    for at_threshold, beyond, condition in cases:
        inside = derive_confidence(row(**at_threshold), rule)
        outside = derive_confidence(row(**beyond), rule)
        assert inside["confidence_class"] == "medium", (condition, at_threshold)
        assert inside["basis"][condition] == PASS
        assert outside["confidence_class"] == "low", (condition, beyond)
        assert outside["failed_conditions"] == [condition]


def test_high_is_never_assigned_and_tier_t4_is_locked(rule: ConfidenceRule) -> None:
    assert VALID_CONFIDENCE_CLASSES[0] == "high"
    with pytest.raises(ConfidenceError, match="T4 is locked"):
        derive_confidence(row(tier="T4"), rule)
    for inputs in (row(), own_candidate_row(), scenario_row()):
        assert derive_confidence(inputs, rule)["confidence_class"] == "medium"


def test_recency_is_a_count_of_calendar_days() -> None:
    assert recency_days(date(2030, 1, 13), date(2030, 1, 10)) == 3
    assert recency_days(date(2030, 1, 7), date(2030, 1, 10)) == 3
    assert recency_days(date(2030, 1, 10), date(2030, 1, 10)) == 0
    assert recency_days(None, date(2030, 1, 10)) is None
    assert recency_days(date(2030, 1, 10), None) is None


# ---------------------------------------------------------------------------
# Tier T2: the skill condition
# ---------------------------------------------------------------------------


def test_own_candidate_reaches_medium_only_through_the_skill_condition(rule: ConfidenceRule) -> None:
    result = derive_confidence(own_candidate_row(), rule)
    assert result["confidence_class"] == "medium"
    assert result["basis"]["C1_tier"] == PASS
    skill = result["t2_skill_condition"]
    assert skill["status"] == "evaluated" and skill["passes"] is True and skill["failed_conditions"] == []
    assert set(skill["conditions"]) == {
        "geoid_held_out_test_iou_min", "mae_sai_abstention_fraction_max", "mae_sai_unit_coverage_min",
        "recency_window_days",
    }
    assert "not independent accuracy" in skill["metric_wording"]


def test_inputs_declared_unable_to_meet_the_skill_condition_stay_low(rule: ConfidenceRule) -> None:
    assert rule.skill_declared_unable_to_meet
    for name in rule.skill_declared_unable_to_meet:
        result = derive_confidence(own_candidate_row(flood_input=name, t2_geoid_held_out_test_iou=0.99), rule)
        assert result["confidence_class"] == "low"
        assert result["failed_conditions"] == ["C1_tier"]
        assert result["t2_skill_condition"]["status"] == "declared_unable_to_meet"
        assert result["t2_skill_condition"]["failed_conditions"] == []
        assert result["reason_code"] == "low_confidence"


def test_an_input_the_protocol_does_not_list_as_evaluated_stays_low(rule: ConfidenceRule) -> None:
    result = derive_confidence(own_candidate_row(flood_input="invented own candidate"), rule)
    assert result["confidence_class"] == "low" and result["failed_conditions"] == ["C1_tier"]
    assert result["t2_skill_condition"]["status"] == "not_evaluated_by_the_rule"
    for name in rule.skill_evaluated_by_the_rule:
        assert derive_confidence(own_candidate_row(flood_input=name), rule)["confidence_class"] == "medium"


def test_each_skill_condition_is_needed_and_inclusive_at_its_threshold(rule: ConfidenceRule) -> None:
    window = timedelta(days=int(rule.skill_recency_window_days))
    cases = [
        ({"t2_geoid_held_out_test_iou": rule.skill_geoid_held_out_test_iou_min},
         {"t2_geoid_held_out_test_iou": rule.skill_geoid_held_out_test_iou_min - 1e-9},
         "geoid_held_out_test_iou_min", ["C1_tier"]),
        ({"t2_geoid_held_out_test_iou": rule.skill_geoid_held_out_test_iou_min},
         {"t2_geoid_held_out_test_iou": None}, "geoid_held_out_test_iou_min", ["C1_tier"]),
        ({"t2_abstention_fraction": rule.skill_abstention_fraction_max},
         {"t2_abstention_fraction": rule.skill_abstention_fraction_max + 1e-9},
         "mae_sai_abstention_fraction_max", ["C1_tier", "C4_input_uncertainty"]),
        ({"t2_abstention_fraction": rule.t2_abstention_fraction_max},
         {"t2_abstention_fraction": None}, "mae_sai_abstention_fraction_max", ["C1_tier", "C4_input_uncertainty"]),
        ({"unit_valid_coverage": rule.skill_unit_coverage_min},
         {"unit_valid_coverage": rule.skill_unit_coverage_min - 1e-9},
         "mae_sai_unit_coverage_min", ["C1_tier", "C3_coverage"]),
        ({"acquisition_date": REFERENCE + window},
         {"acquisition_date": REFERENCE + window + timedelta(days=1)},
         "recency_window_days", ["C1_tier", "C2_recency"]),
    ]
    for at_threshold, beyond, skill_condition, failed in cases:
        inside = derive_confidence(own_candidate_row(**at_threshold), rule)
        assert inside["confidence_class"] == "medium", at_threshold
        outside = derive_confidence(own_candidate_row(**beyond), rule)
        assert outside["confidence_class"] == "low"
        assert outside["failed_conditions"] == failed
        assert outside["t2_skill_condition"]["failed_conditions"] == [skill_condition]
        assert outside["t2_skill_condition"]["passes"] is False


def test_skill_condition_is_a_pure_function_of_its_inputs(rule: ConfidenceRule) -> None:
    arguments = {
        "flood_input": EVALUATED_T2_INPUT,
        "geoid_held_out_test_iou": 0.5,
        "abstention_fraction": 0.1,
        "unit_valid_coverage": 0.9,
        "acquisition_date": REFERENCE,
        "case_reference_date": REFERENCE,
    }
    first = t2_skill_condition(rule, **arguments)
    assert first == t2_skill_condition(rule, **arguments) and first["passes"] is True
    assert first["thresholds"]["geoid_held_out_test_iou_min"] == rule.skill_geoid_held_out_test_iou_min
    with pytest.raises(ConfidenceError, match="between 0 and 1"):
        t2_skill_condition(rule, **{**arguments, "geoid_held_out_test_iou": 1.2})


def test_t2_measurements_on_an_agency_row_are_refused(rule: ConfidenceRule) -> None:
    with pytest.raises(ConfidenceError, match="own T2 candidate only"):
        derive_confidence(row(t2_abstention_fraction=0.1), rule)
    with pytest.raises(ConfidenceError, match="own T2 candidate only"):
        derive_confidence(scenario_row(t2_geoid_held_out_test_iou=0.5), rule)


# ---------------------------------------------------------------------------
# Tier T1: scenario rows (drafter reading DR-A07, confirmed at signing)
# ---------------------------------------------------------------------------


def test_reading_dr_a07_is_confirmed_in_the_signed_file(protocol: dict[str, Any]) -> None:
    reading = protocol["drafter_readings"][_reading_index(protocol, "DR-A07")]
    assert reading["status"] == "confirmed" and reading["where"] == "confidence_rule_v1.scenario_rows"
    assert "Confirmed by the owners at signing" in protocol["confidence_rule_v1"]["scenario_rows"]["rule_status"]


@pytest.mark.parametrize("lane", ["SCN-ENV", "SCN"])
def test_scenario_row_on_an_agency_product_derives_its_confidence(rule: ConfidenceRule, lane: str) -> None:
    result = derive_confidence(scenario_row(lane=lane), rule)
    assert result["confidence_class"] == "medium"
    assert result["confidence_kind"] == "scenario"
    assert result["basis"]["C1_tier"] == BY_SCENARIO_DECLARATION
    assert result["basis"]["C2_recency"] == BY_SCENARIO_DECLARATION
    assert [result["basis"][condition] for condition in CONDITION_IDS[2:]] == [PASS] * 6
    assert result["failed_conditions"] == [] and result["reason_code"] is None
    assert any("DR-A07" in text and "never shown or counted as observed" in text for text in result["assumptions"])
    # The recency condition is replaced, so a season-window input with no date does not fail it.
    assert result["measurements"]["recency_days"] is None


@pytest.mark.parametrize("changes, failed", [
    ({"unit_valid_coverage": 0.5}, "C3_coverage"),
    ({"exposure_plus_one_pixel_0_100": 90.0}, "C4_input_uncertainty"),
    ({"component_status": {**ALL_COMPUTED, "road_criticality_0_100": "assumed"}}, "C5_components"),
    ({"baseline_vehicle_no_route_share": 0.5}, "C7_baseline_no_route"),
    ({"hospitals_reachable_at_baseline": 0}, "C8_hospital"),
])
def test_scenario_rows_evaluate_c3_to_c8_as_an_observed_row_does(
    rule: ConfidenceRule, changes: dict[str, Any], failed: str
) -> None:
    result = derive_confidence(scenario_row(**changes), rule)
    assert result["confidence_class"] == "low" and result["confidence_kind"] == "scenario"
    assert result["failed_conditions"] == [failed]
    assert result["basis"]["C1_tier"] == result["basis"]["C2_recency"] == BY_SCENARIO_DECLARATION


def test_scenario_row_on_an_own_candidate_is_judged_on_that_candidate(rule: ConfidenceRule) -> None:
    base = {
        "lane": "SCN",
        "scenario_base": SCENARIO_BASE_OWN_CANDIDATE,
        "t2_abstention_fraction": 0.05,
        "acquisition_date": REFERENCE,
        "case_reference_date": REFERENCE,
    }
    failing = derive_confidence(scenario_row(flood_input="M1-literal", t2_geoid_held_out_test_iou=0.9, **base), rule)
    assert failing["confidence_class"] == "low" and failing["confidence_kind"] == "scenario"
    assert failing["failed_conditions"] == ["C1_tier"]
    assert failing["basis"]["C2_recency"] == BY_SCENARIO_DECLARATION
    assert failing["t2_skill_condition"]["status"] == "declared_unable_to_meet"

    passing = derive_confidence(
        scenario_row(flood_input=EVALUATED_T2_INPUT, t2_geoid_held_out_test_iou=0.6, **base), rule
    )
    assert passing["confidence_class"] == "medium" and passing["basis"]["C1_tier"] == PASS
    assert passing["basis"]["C2_recency"] == BY_SCENARIO_DECLARATION

    # C4 keeps its T2 part for a scenario built on an own candidate.
    abstaining = derive_confidence(
        scenario_row(flood_input=EVALUATED_T2_INPUT, t2_geoid_held_out_test_iou=0.6,
                     **{**base, "t2_abstention_fraction": 0.5}), rule
    )
    assert abstaining["failed_conditions"] == ["C1_tier", "C4_input_uncertainty"]


def test_observed_rows_never_carry_a_scenario_declaration(rule: ConfidenceRule) -> None:
    for inputs in (row(), own_candidate_row(), row(unit_valid_coverage=0.1)):
        result = derive_confidence(inputs, rule)
        assert BY_SCENARIO_DECLARATION not in result["basis"].values()
        assert result["confidence_kind"] == "observed"
        assert not any("DR-A07" in text for text in result["assumptions"])


# ---------------------------------------------------------------------------
# C3 by construction
# ---------------------------------------------------------------------------


def test_coverage_by_construction_is_reported_as_such(rule: ConfidenceRule) -> None:
    for inputs in (
        scenario_row(coverage_by_construction=True, unit_valid_coverage=None),
        row(coverage_by_construction=True, unit_valid_coverage=1.0),
    ):
        result = derive_confidence(inputs, rule)
        assert result["basis"]["C3_coverage"] == BY_CONSTRUCTION
        assert result["confidence_class"] == "medium" and result["failed_conditions"] == []
    with pytest.raises(ConfidenceError, match="below the minimum"):
        derive_confidence(row(coverage_by_construction=True, unit_valid_coverage=0.3), rule)
    with pytest.raises(ConfidenceError, match="not for an own candidate"):
        derive_confidence(own_candidate_row(coverage_by_construction=True), rule)


# ---------------------------------------------------------------------------
# Guardrail GR1 takes precedence over C6 (drafter reading DR-A09)
# ---------------------------------------------------------------------------


def test_a_unit_under_the_resident_minimum_has_no_class_and_low_confidence(rule: ConfidenceRule) -> None:
    for residents in (rule.gr1_unit_residents_min_for_class - 0.01, 12.0, 0.0):
        result = derive_confidence(row(unit_residents=residents), rule)
        assert result["confidence_class"] == "low"
        assert result["failed_conditions"] == ["C6_residents"]
        assert result["reason_code"] == "insufficient_denominator"
        guardrail = result["guardrail_gr1"]
        assert guardrail["id"] == "GR1_minimum_denominators" and guardrail["applies"] is True
        assert guardrail["no_binding_class"] and guardrail["no_would_be_class"] and guardrail["no_v2_class"]
        assert any("insufficient_denominator" in text for text in result["assumptions"])


def test_gr1_reason_code_wins_over_other_failed_conditions(rule: ConfidenceRule) -> None:
    result = derive_confidence(own_candidate_row(flood_input="M1-literal", unit_residents=40, unit_valid_coverage=0.2), rule)
    assert result["failed_conditions"] == ["C1_tier", "C3_coverage", "C6_residents"]
    assert result["reason_code"] == "insufficient_denominator"
    scenario = derive_confidence(scenario_row(unit_residents=40), rule)
    assert scenario["reason_code"] == "insufficient_denominator" and scenario["confidence_kind"] == "scenario"


def test_a_unit_at_the_resident_minimum_is_not_under_gr1(rule: ConfidenceRule) -> None:
    result = derive_confidence(row(unit_residents=rule.gr1_unit_residents_min_for_class), rule)
    guardrail = result["guardrail_gr1"]
    assert guardrail["applies"] is False
    assert not (guardrail["no_binding_class"] or guardrail["no_would_be_class"] or guardrail["no_v2_class"])
    assert result["confidence_class"] == "medium" and result["reason_code"] is None
    low = derive_confidence(row(unit_residents=rule.gr1_unit_residents_min_for_class, hospitals_reachable_at_baseline=0), rule)
    assert low["reason_code"] == "low_confidence" and low["guardrail_gr1"]["applies"] is False


# ---------------------------------------------------------------------------
# Rights and ensemble outputs are not inputs
# ---------------------------------------------------------------------------


def test_rights_and_ensemble_outputs_are_not_inputs(rule: ConfidenceRule) -> None:
    names = [field.name for field in dataclasses.fields(ConfidenceInputs)]
    for word in ("right", "licen", "publication", "eligib", "ensemble", "retention"):
        assert not any(word in name for name in names), word
    for extra in ("rights_level", "publication_eligibility", "class_retention"):
        with pytest.raises(TypeError):
            row(**{extra: "public"})
    result = derive_confidence(row(), rule)
    assert result["rights_are_an_input"] is False and result["uses_ensemble_output"] is False
    assert "publication_eligibility" not in result
    source = MODULE.read_text(encoding="utf-8")
    assert "uncertainty_ensemble" not in source and "rights_level" not in source


def test_derivation_is_pure(rule: ConfidenceRule) -> None:
    status = dict(ALL_COMPUTED)
    inputs = row(component_status=status)
    first = derive_confidence(inputs, rule)
    second = derive_confidence(inputs, rule)
    assert first == second and first is not second
    assert status == ALL_COMPUTED
    first["basis"]["C1_tier"] = "changed"
    assert derive_confidence(inputs, rule)["basis"]["C1_tier"] == PASS
    assert json.dumps(first)  # the record is plain JSON


# ---------------------------------------------------------------------------
# Refused inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("changes, message", [
    ({"lane": "ENG", "tier": "T0"}, "engine rows"),
    ({"tier": "T0"}, "engine rows"),
    ({"lane": "ENG"}, "engine rows"),
    ({"tier": "T9"}, "unknown lane"),
    ({"lane": "OBSERVED"}, "unknown lane"),
    ({"lane": "SCN"}, "tier T1 belongs"),
    ({"tier": "T1"}, "tier T1 belongs"),
    ({"scenario_base": SCENARIO_BASE_AGENCY}, "tier T1 rows only"),
    ({"lane": "SCN", "tier": "T1"}, "names its base flood input"),
    ({"lane": "SCN", "tier": "T1", "scenario_base": "something else"}, "names its base flood input"),
    ({"lane": "SCN-ENV", "tier": "T1", "scenario_base": SCENARIO_BASE_OWN_CANDIDATE}, "used as provided"),
    ({"unit_id": ""}, "must be text"),
    ({"unit_id": 7}, "must be text"),
    ({"flood_input": None}, "must be text"),
    ({"unit_valid_coverage": 1.5}, "between 0 and 1"),
    ({"unit_valid_coverage": -0.1}, "between 0 and 1"),
    ({"unit_valid_coverage": float("nan")}, "between 0 and 1"),
    ({"unit_valid_coverage": True}, "a number or None"),
    ({"unit_valid_coverage": "0.9"}, "a number or None"),
    ({"exposure_plus_one_pixel_0_100": 101.0}, "between 0 and 100"),
    ({"exposure_minus_one_pixel_0_100": -1.0}, "between 0 and 100"),
    ({"baseline_vehicle_no_route_share": 2.0}, "between 0 and 1"),
    ({"hospitals_reachable_at_baseline": 1.5}, "whole number"),
    ({"hospitals_reachable_at_baseline": -1}, "between 0 and inf"),
    ({"unit_residents": None}, "unit_residents is required"),
    ({"unit_residents": float("inf")}, "between 0 and inf"),
    ({"unit_residents": -5}, "between 0 and inf"),
    ({"acquisition_date": datetime(2030, 1, 10, 6, 16)}, "calendar date"),
    ({"case_reference_date": "2030-01-10"}, "calendar date"),
    ({"coverage_by_construction": "yes"}, "True or False"),
    ({"component_status": {"exposure_0_100": "computed"}}, "exactly the five"),
    ({"component_status": [*SCORE_COMPONENTS]}, "exactly the five"),
    ({"component_status": {**ALL_COMPUTED, "exposure_0_100": "guessed"}}, "must be one of"),
])
def test_inputs_outside_the_contract_are_refused(rule: ConfidenceRule, changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfidenceError, match=message):
        derive_confidence(row(**changes), rule)


def test_every_field_has_to_be_given() -> None:
    with pytest.raises(TypeError):
        ConfidenceInputs(unit_id="SYN-001", lane="OBS", tier="T3")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        ConfidenceInputs("SYN-001", "OBS", "T3")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Property tests on invented rows, against an independent statement of the rule
# ---------------------------------------------------------------------------


def _random_row(generator: random.Random, rule: ConfidenceRule) -> ConfidenceInputs:
    """An invented row: each measurement is usually sound and sometimes missing, at a threshold or beyond it."""

    def pick(sound: list[Any], other: list[Any]) -> Any:
        if generator.random() < 0.88:
            return generator.choice(sound)
        return generator.choice(other)

    kind = generator.choice(["T3", "T2", "T1-agency", "T1-own"])
    statuses = {name: pick(["computed"], ["assumed", "not_computed"]) for name in SCORE_COMPONENTS}
    values: dict[str, Any] = {
        "unit_id": f"SYN-{generator.randrange(10_000):04d}",
        "unit_valid_coverage": pick([0.8, 0.81, 1.0, 0.8 + 0.2 * generator.random()], [None, 0.0, 0.5, 0.79]),
        "exposure_plus_one_pixel_0_100": pick([30.0, 40.0, 45.0], [None, 0.0, 45.01, 100.0, 100 * generator.random()]),
        "exposure_minus_one_pixel_0_100": pick([30.0, 35.0], [None, 0.0, 100.0, 100 * generator.random()]),
        "component_status": statuses,
        "unit_residents": pick([100.0, 100.01, 5000.0, 100 + 20_000 * generator.random()], [0.0, 50.0, 99.99]),
        "baseline_vehicle_no_route_share": pick([0.0, 0.1, 0.1 * generator.random()], [None, 0.1000001, 0.5]),
        "hospitals_reachable_at_baseline": pick([1, 2, 7], [None, 0]),
        "acquisition_date": pick(
            [REFERENCE + timedelta(days=offset) for offset in range(-3, 4)],
            [None, REFERENCE + timedelta(days=4), REFERENCE - timedelta(days=4), REFERENCE + timedelta(days=40)],
        ),
        "case_reference_date": pick([REFERENCE], [None]),
    }
    if kind == "T3":
        values.update(tier="T3", lane="OBS", flood_input=AGENCY_INPUT)
    elif kind == "T1-agency":
        values.update(tier="T1", lane=generator.choice(["SCN", "SCN-ENV"]), scenario_base=SCENARIO_BASE_AGENCY)
    else:
        values.update(
            flood_input=pick(
                list(rule.skill_evaluated_by_the_rule),
                [*rule.skill_declared_unable_to_meet, "invented own candidate"],
            ),
            t2_abstention_fraction=pick([0.0, 0.2, 0.2 * generator.random()], [None, 0.2000001, 0.6]),
            t2_geoid_held_out_test_iou=pick([0.4, 0.41, 0.9], [None, 0.0, 0.39]),
        )
        if kind == "T2":
            values.update(tier="T2", lane="OBS")
        else:
            values.update(tier="T1", lane="SCN", scenario_base=SCENARIO_BASE_OWN_CANDIDATE)
    return row(**values)


def _expected(inputs: ConfidenceInputs, rule: ConfidenceRule) -> tuple[str, list[str]]:
    """The rule written a second time, as plain statements of protocol v1a."""

    own = inputs.tier == "T2" or inputs.scenario_base == SCENARIO_BASE_OWN_CANDIDATE
    scenario = inputs.tier == "T1"
    dates_known = inputs.acquisition_date is not None and inputs.case_reference_date is not None
    recent = dates_known and abs((inputs.acquisition_date - inputs.case_reference_date).days) <= 3
    covered = inputs.unit_valid_coverage is not None and inputs.unit_valid_coverage >= 0.8
    abstention_ok = inputs.t2_abstention_fraction is not None and inputs.t2_abstention_fraction <= 0.2
    skill = (
        own
        and inputs.flood_input in ("M1-v2", "A6-prime classifier")
        and inputs.t2_geoid_held_out_test_iou is not None
        and inputs.t2_geoid_held_out_test_iou >= 0.4
        and abstention_ok
        and covered
        and recent
    )
    plus, minus = inputs.exposure_plus_one_pixel_0_100, inputs.exposure_minus_one_pixel_0_100
    held = {
        "C1_tier": inputs.tier == "T3" or (scenario and not own) or skill,
        "C2_recency": scenario or recent,
        "C3_coverage": covered,
        "C4_input_uncertainty": plus is not None and minus is not None and abs(plus - minus) <= 15
        and (abstention_ok or not own),
        "C5_components": all(status == "computed" for status in inputs.component_status.values()),
        "C6_residents": inputs.unit_residents >= 100,
        "C7_baseline_no_route": inputs.baseline_vehicle_no_route_share is not None
        and inputs.baseline_vehicle_no_route_share <= 0.1,
        "C8_hospital": inputs.hospitals_reachable_at_baseline is not None and inputs.hospitals_reachable_at_baseline >= 1,
    }
    failed = [condition for condition in CONDITION_IDS if not held[condition]]
    return ("low" if failed else "medium"), failed


def test_properties_hold_on_many_invented_rows(rule: ConfidenceRule) -> None:
    # The second statement of the rule in _expected types the plan's numbers; check they are the file's.
    assert (rule.recency_window_days, rule.unit_valid_coverage_min, rule.t2_abstention_fraction_max) == (3, 0.8, 0.2)
    assert (rule.exposure_plus_minus_one_pixel_max_points, rule.unit_residents_min) == (15, 100)
    assert (rule.baseline_vehicle_no_route_share_max, rule.hospitals_reachable_at_baseline_min) == (0.1, 1)
    assert (rule.skill_geoid_held_out_test_iou_min, rule.skill_evaluated_by_the_rule) == (0.4, ("M1-v2", "A6-prime classifier"))

    generator = random.Random(20261004)
    seen = {"medium": 0, "low": 0, "scenario": 0, "gr1": 0}
    for _ in range(4000):
        inputs = _random_row(generator, rule)
        result = derive_confidence(inputs, rule)
        expected_class, expected_failed = _expected(inputs, rule)
        assert result["confidence_class"] == expected_class, inputs
        assert result["failed_conditions"] == expected_failed, inputs

        assert result["confidence_class"] in ("medium", "low")  # never high
        assert tuple(result["basis"]) == CONDITION_IDS
        assert set(result["basis"].values()) <= set(BASIS_VALUES)
        assert (result["confidence_class"] == "medium") == (not result["failed_conditions"])
        scenario = inputs.tier == "T1"
        assert (result["confidence_kind"] == "scenario") == scenario
        assert (result["basis"]["C2_recency"] == BY_SCENARIO_DECLARATION) == scenario
        assert (result["basis"]["C1_tier"] == BY_SCENARIO_DECLARATION) == (
            scenario and inputs.scenario_base == SCENARIO_BASE_AGENCY
        )
        assert BY_CONSTRUCTION not in result["basis"].values()
        under_minimum = inputs.unit_residents < 100
        assert result["guardrail_gr1"]["applies"] == under_minimum
        if under_minimum:
            assert result["reason_code"] == "insufficient_denominator"
            assert "C6_residents" in result["failed_conditions"] and result["confidence_class"] == "low"
        elif result["confidence_class"] == "low":
            assert result["reason_code"] == "low_confidence"
        else:
            assert result["reason_code"] is None
        seen[result["confidence_class"]] += 1
        seen["scenario"] += scenario
        seen["gr1"] += under_minimum
    assert all(count > 50 for count in seen.values()), seen


def test_making_one_measurement_worse_never_raises_the_class(rule: ConfidenceRule) -> None:
    generator = random.Random(4009)
    worse = [
        {"unit_valid_coverage": 0.0},
        {"exposure_plus_one_pixel_0_100": 100.0, "exposure_minus_one_pixel_0_100": 0.0},
        {"component_status": {**ALL_COMPUTED, "exposure_0_100": "assumed"}},
        {"unit_residents": 0.0},
        {"baseline_vehicle_no_route_share": 1.0},
        {"hospitals_reachable_at_baseline": 0},
    ]
    for _ in range(600):
        inputs = _random_row(generator, rule)
        before = derive_confidence(inputs, rule)
        change = generator.choice(worse)
        after = derive_confidence(dataclasses.replace(inputs, **change), rule)
        assert after["confidence_class"] == "low"
        assert set(before["failed_conditions"]) <= set(after["failed_conditions"])
