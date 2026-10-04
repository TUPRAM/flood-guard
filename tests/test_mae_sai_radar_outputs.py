"""The committed radar candidate tables of case O1 (plan tasks A2 and A4) and their result document.

These tests read committed files only. They run no method on real data and
compute no FPPS, no A-E class and no ensemble. They check that the tables say
what they are, that each receipt binds its table, that the figures add up,
that the T2 skill bar of protocol v1a was applied as signed, and that the
result document repeats the tables and words its limits as the shared wording
rules ask.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from floodguard import confidence
from floodguard import geoid_m1_review as review
from floodguard.wording_lint import find_violations, json_strings, load_rules

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "planning_v1"
DOCS = ROOT / "docs" / "proposal_execution"
DOCUMENT = DOCS / "automated_track" / "MAE_SAI_RADAR_CANDIDATES_RESULT.md"
RECORD = "radar_o1_mae_sai_v1"
SENSITIVITY = "radar_o1_mae_sai_v1_height_aware_sensitivity"
RUNS = (RECORD, SENSITIVITY)
METHODS = ("un_spider", "m1_literal", "m1_v2")
UNITS = ["TH570901", "TH570902", "TH570903", "TH570904", "TH570905", "TH570906", "TH570908", "TH570909"]
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")

pytestmark = pytest.mark.skipif(
    not (OUTPUTS / f"{RECORD}.json").exists(), reason="the radar candidate run is not on this checkout"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(name: str) -> dict[str, Any]:
    return json.loads((OUTPUTS / name).read_bytes().decode("ascii"))


@pytest.fixture(scope="module")
def tables() -> dict[str, dict[str, Any]]:
    return {run: _load(f"{run}.json") for run in RUNS}


@pytest.fixture(scope="module")
def receipts() -> dict[str, dict[str, Any]]:
    return {run: _load(f"{run}_receipt.json") for run in RUNS}


@pytest.fixture(scope="module")
def document() -> str:
    return DOCUMENT.read_text(encoding="utf-8")


# --- what the files are ---------------------------------------------------


@pytest.mark.parametrize("run", RUNS)
def test_receipt_binds_its_table_and_is_registered(run: str, receipts: dict[str, dict[str, Any]]) -> None:
    receipt = receipts[run]
    bound = receipt["outputs"]["table"]
    assert bound["path"] == f"outputs/planning_v1/{run}.json"
    assert bound["sha256"] == _sha256(OUTPUTS / f"{run}.json")
    for name in (f"{run}.json", f"{run}_receipt.json"):
        entry = json.loads((OUTPUTS / "run_register" / f"a2_a4_{name}").read_text(encoding="ascii"))
        assert entry == {"path": f"outputs/planning_v1/{name}", "sha256": _sha256(OUTPUTS / name)}
    rasters = receipt["outputs"]["rasters"]
    assert len(rasters) == 16 and all(item["kept_outside_git"] and len(item["sha256"]) == 64 for item in rasters)
    assert all(item["path"].startswith("<external_data_workspace>/proposal_execution/planning_v1/o1_mae_sai/")
               for item in rasters)
    assert receipt["timestamps"]["run_started_at_utc"] < receipt["generated_at_utc"]


@pytest.mark.parametrize("run", RUNS)
def test_files_name_no_local_path_and_no_score(
    run: str, tables: dict[str, dict[str, Any]], receipts: dict[str, dict[str, Any]]
) -> None:
    for payload in (tables[run], receipts[run]):
        text = json.dumps(payload)
        assert "C:/" not in text and "C:\\\\" not in text and "/Users/" not in text
        assert payload["official_warning"] is False and payload["confidence_class"] == "low"
        assert {"FPPS", "A-E class", "ensemble cell"} <= set(payload["not_computed"])
        assert "any comparison with UNOSAT/GISTDA product 4009" in payload["not_computed"]
    keys: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            keys.update(value)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(tables[run])
    assert not {key for key in keys if "fpps" in key.lower() or key in {"action_class", "would_be_class"}}
    # Guardrail GR4: product 4009 appears only where the files say that no comparison was made.
    for path, text in json_strings(tables[run]):
        if "4009" in text:
            assert path.startswith("$.not_computed"), path


def test_roles_of_the_two_runs(tables: dict[str, dict[str, Any]], receipts: dict[str, dict[str, Any]]) -> None:
    record, sensitivity = tables[RECORD], tables[SENSITIVITY]
    assert record["run_role"] == receipts[RECORD]["run_role"] == "run_of_record_plan_fallback"
    assert record["geocoding"]["label"] == "approximate geocoding: GCP affine, no DEM terrain correction"
    assert record["geocoding"]["method"] == "gcp_polynomial"
    assert "sigmaNought look-up table" in record["geocoding"]["radiometry"]
    assert record["t2_skill_bar"]["evaluation_of_record"] is True
    assert sensitivity["run_role"] == "sensitivity_run_not_in_the_plan"
    assert "replaces nothing" in sensitivity["run_role_note"]
    assert sensitivity["t2_skill_bar"]["evaluation_of_record"] is False
    named = receipts[SENSITIVITY]["run_of_record"]
    assert named["table_sha256"] == _sha256(OUTPUTS / f"{RECORD}.json")
    assert named["receipt_sha256"] == _sha256(OUTPUTS / f"{RECORD}_receipt.json")
    assert receipts[RECORD]["generated_at_utc"] < receipts[SENSITIVITY]["generated_at_utc"]
    for run in RUNS:
        for method in tables[run]["methods"].values():
            assert method["tier"] == "T2" and method["lane"] == "OBS"
            assert method["display"] == "Own model candidate: verify before action"
            assert method["label"].endswith(f"({tables[run]['geocoding']['label']})")


@pytest.mark.parametrize("run", RUNS)
def test_protocols_and_the_frozen_method_are_the_ones_in_force(
    run: str, tables: dict[str, dict[str, Any]], receipts: dict[str, dict[str, Any]]
) -> None:
    for name in ("v1a", "v1b"):
        digest = _sha256(DOCS / f"planning_protocol_{name}.json")
        assert tables[run]["protocol_sha256"][f"planning_protocol_{name}"] == digest
        assert receipts[run]["inputs"][f"planning_protocol_{name}"]["sha256"] == digest
    binding = review.require_frozen_m1_v2(ROOT)
    recorded = receipts[run]["m1_v2_frozen_binding"]
    assert recorded["frozen_config_sha256"] == binding["frozen_config_sha256"]
    assert recorded["code_sha256"] == binding["code_sha256"]
    assert receipts[run]["parameters"]["m1_v2"] == binding["parameters"] == tables[run]["methods"]["m1_v2"]["configuration"]
    assert receipts[run]["implementation"]["sar_change_v2_sha256"] == binding["code_sha256"]["src/floodguard/sar_change_v2.py"]
    assert receipts[run]["parameters"]["un_spider"]["difference_threshold"] == 1.25
    for role in ("pre_event_safe", "post_event_safe"):
        assert receipts[run]["inputs"][role]["matches_the_acquisition_manifest"] is True
    assert tables[run]["image_pair"]["pre"]["relative_orbit"] == tables[run]["image_pair"]["post"]["relative_orbit"] == 135
    assert tables[run]["source_timestamp"] == "2024-09-15T23:16:01Z"


def test_a_superseding_receipt_names_every_earlier_run(receipts: dict[str, dict[str, Any]]) -> None:
    for run in RUNS:
        chain = receipts[run]["supersedes"]
        times = []
        while chain is not None:
            assert len(chain["table_sha256"]) == 64 and chain["reason"].strip()
            assert chain["same_frame_and_unit_figures"] is True
            assert len(chain["copies_kept_outside_git"]) == 2
            times.append(chain["generated_at_utc"])
            chain = chain.get("runs_before_the_superseded_one")  # The second runs were written before this key.
        assert len(times) == 2 and times == sorted(times, reverse=True)
        assert times[0] < receipts[run]["generated_at_utc"]


# --- the figures add up ---------------------------------------------------


@pytest.mark.parametrize("run", RUNS)
@pytest.mark.parametrize("method", METHODS)
def test_unit_rows_cover_the_frame_and_add_up(run: str, method: str, tables: dict[str, dict[str, Any]]) -> None:
    table = tables[run]
    entry = table["methods"][method]
    rows, frame = entry["units"], entry["frame"]
    assert [row["unit_id"] for row in rows] == UNITS == [unit["unit_id"] for unit in table["units"]]
    assert frame["cells"] == sum(row["cells"] for row in rows) == table["radar_input"]["frame_cells"]
    assert frame["candidate_cells"] == sum(row["candidate_cells"] for row in rows)
    assert frame["candidate_area_km2"] == pytest.approx(frame["candidate_cells"] * 1e-4)
    assert frame["area_km2"] == pytest.approx(sum(unit["polygon_area_km2"] for unit in table["units"]), rel=1e-4)
    for row in rows:
        assert row["answered_cells"] + row["cells_without_an_answer"] == row["cells"]
        assert sum(row["cells_without_an_answer_by_reason"].values()) == row["cells_without_an_answer"]
        assert row["answer_coverage"] == pytest.approx(row["answered_cells"] / row["cells"], abs=1e-6)
        assert row["abstention_fraction"] == pytest.approx(1 - row["answer_coverage"], abs=1e-6)
        assert row["candidate_cells_outside_permanent_water"] <= row["candidate_cells"] <= row["answered_cells"]
        # Plan row A4: coverage of at least 0.80, or a reason-coded low confidence.
        assert bool(row["low_confidence_reason_codes"]) == (row["answer_coverage"] < 0.8)
    for strata in entry["strata"].values():
        assert sum(item["frame_cells"] for item in strata) == frame["cells"]
        assert sum(item["candidate_cells"] for item in strata) == frame["candidate_cells"]


@pytest.mark.parametrize("run", RUNS)
def test_m1_v2_cells_without_an_answer_are_the_declined_tiles(run: str, tables: dict[str, dict[str, Any]]) -> None:
    entry = tables[run]["methods"]["m1_v2"]
    declined = {unit: 0 for unit in UNITS}
    for tile in entry["tiles"]:
        assert tile["declined"] == tile["whole_tile"]["abstained"] == (tile["tile"] in entry["tiles_declined"])
        assert (tile["declined_because"] is None) != tile["declined"]
        threshold = tile["whole_tile"]["sides"]["darkening"]["threshold_db"]
        assert (threshold is None) == tile["declined"] and (threshold is None or threshold > 0)
        if tile["declined"]:
            assert tile["candidate_cells_in_frame"] == 0
            for unit, cells in tile["frame_cells_by_unit"].items():
                declined[unit] += cells
    assert sum(sum(tile["frame_cells_by_unit"].values()) for tile in entry["tiles"]) == entry["frame"]["cells"]
    for row in entry["units"]:
        assert row["cells_without_an_answer"] == declined[row["unit_id"]]
        assert row["input_coverage"] == 1.0
    assert len(entry["tiles"]) == 9 == len(tables[run]["grid"]["tiles_holding_part_of_the_frame"])
    levels = entry["threshold_levels"]["frame_km2"]
    assert levels["strictest"] <= levels["central"] <= levels["loosest"]
    assert levels["central"] == entry["frame"]["candidate_area_km2"]


@pytest.mark.parametrize("run", RUNS)
def test_un_spider_statement_and_steps(run: str, tables: dict[str, dict[str, Any]]) -> None:
    entry = tables[run]["methods"]["un_spider"]
    steps = entry["steps"]
    removed = (steps["cells_removed_as_perennial_water"] + steps["cells_removed_by_connected_pixel_rule"]
               + steps["cells_removed_by_slope_rule"])
    assert steps["cells_above_threshold"] - removed == steps["candidate_cells"] == entry["frame"]["candidate_cells"]
    assert entry["frame"]["abstention_fraction"] == 0.0 and entry["frame"]["input_coverage"] == 1.0
    assert entry["statement"] == (
        f"Reproduces UN-SPIDER practice; {entry['frame']['candidate_area_km2']:.2f} km2 of residual water at "
        "16 Sep 06:16 ICT; the published 93.38% OA does not transfer"
    )
    assert entry["configuration"]["difference_threshold"] == 1.25
    assert entry["frame"]["candidate_cells_outside_permanent_water"] == entry["frame"]["candidate_cells"]


# --- the T2 skill bar -----------------------------------------------------


@pytest.mark.parametrize("run", RUNS)
def test_t2_skill_bar_is_the_signed_rule_applied_to_the_unit_rows(run: str, tables: dict[str, dict[str, Any]]) -> None:
    rule = confidence.load_confidence_rule(DOCS / "planning_protocol_v1a.json", DOCS / "RECEIPTS.jsonl")
    skill = tables[run]["t2_skill_bar"]
    assert skill["thresholds"] == {
        "geoid_held_out_test_iou_min": 0.4, "mae_sai_abstention_fraction_max": 0.2,
        "mae_sai_unit_coverage_min": 0.8, "recency_window_days": 3.0,
    }
    assert skill["recency"]["case_reference_date"] == "2024-09-15" and skill["recency"]["passes"] is True
    geoid = skill["geoid_condition"]
    derived = json.loads((ROOT / "outputs" / "geoid_m1_benchmark_v2_derived_checks.json").read_text(encoding="utf-8"))
    assert geoid["m1_v2_test_iou_strict"] == derived["t2_skill_bar"]["m1_v2_test"]["iou_strict"] == 0.411164
    assert geoid["m1_v2_test_cells_without_an_answer"] == 0.678737
    assert geoid["said_beside_the_result_every_time"] == [
        "The GEOID result (0.411) is not distinguishable from 0.40 on 14 tiles.",
        "67.9% of the GEOID test cells had no answer.",
        "The GEOID figure measures agreement with a same-pass CEMS map, not an independent check.",
    ]
    for name in ("un_spider", "m1_literal"):
        entry = skill["methods"][name]
        assert entry["status_in_protocol_v1a"] == "declared_unable_to_meet"
        assert entry["units_passing_all_four_conditions"] == {"input_coverage": [], "answer_coverage": []}
    entry = skill["methods"]["m1_v2"]
    assert entry["status_in_protocol_v1a"] == "evaluated" and entry["geoid_held_out_test_iou_used"] == 0.411164
    rows = {row["unit_id"]: row for row in tables[run]["methods"]["m1_v2"]["units"]}
    for unit in entry["units"]:
        row = rows[unit["unit_id"]]
        assert unit["abstention_fraction"] == row["abstention_fraction"]
        for reading in ("input_coverage", "answer_coverage"):
            again = confidence.t2_skill_condition(
                rule, flood_input="M1-v2", geoid_held_out_test_iou=0.411164,
                abstention_fraction=row["abstention_fraction"], unit_valid_coverage=row[reading],
                acquisition_date=date(2024, 9, 16), case_reference_date=date(2024, 9, 15),
            )
            assert unit["coverage_reading"][reading]["passes"] == again["passes"]
            assert unit["coverage_reading"][reading]["conditions"] == again["conditions"]
    conditions = entry["mae_sai_conditions"]
    frame = tables[run]["methods"]["m1_v2"]["frame"]
    assert conditions["abstention"]["frame_abstention_fraction"] == frame["abstention_fraction"]
    assert conditions["abstention"]["frame_at_most_max"] == (frame["abstention_fraction"] <= 0.2)


def test_m1_v2_does_not_meet_the_skill_bar_at_mae_sai(tables: dict[str, dict[str, Any]]) -> None:
    """The result of record, stated as the committed table states it."""

    for run in RUNS:
        entry = tables[run]["t2_skill_bar"]["methods"]["m1_v2"]
        conditions = entry["mae_sai_conditions"]
        assert conditions["abstention"]["frame_abstention_fraction"] == 0.772595
        assert conditions["abstention"]["frame_at_most_max"] is False
        assert conditions["abstention"]["units_at_most_max"] == 1
        assert conditions["coverage"]["units_with_answer_coverage_at_least_min"] == 1
        assert conditions["coverage"]["units_with_input_coverage_at_least_min"] == 8
        assert conditions["recency_passes"] is True
        assert entry["units_passing_all_four_conditions"] == {
            "input_coverage": ["TH570908"], "answer_coverage": ["TH570908"],
        }
        assert entry["result"].startswith(
            "M1-v2 does not meet the Mae Sai conditions for the frame, nor in 7 of 8 tambons")
        assert "open point A4-OP3" in entry["result"]
        assert len(tables[run]["methods"]["m1_v2"]["tiles_declined"]) == 6


# --- the displacement -----------------------------------------------------


def test_the_displacement_is_measured_and_restricts_the_use_of_the_run_of_record(
    tables: dict[str, dict[str, Any]],
) -> None:
    record = tables[RECORD]
    check = record["geolocation_check"]
    warp = check["control_point_warp"]["whole_grid"]
    assert (warp["east_m"], warp["north_m"], warp["at_search_edge"]) == (-670.0, 130.0, False)
    readings = check["height_aware_mapping"]["readings"]
    aware = readings["annotation_heights_are_ellipsoidal_and_dem_is_above_the_geoid"]["whole_grid"]
    assert abs(aware["east_m"]) <= 10.0 and abs(aware["north_m"]) <= 10.0
    expected = check["expected_from_geometry"]["readings"][
        "annotation_heights_are_ellipsoidal_and_dem_is_above_the_geoid"]["frame"]["along_range_m"]["median"]
    assert 600.0 < expected < 800.0
    assert check == tables[SENSITIVITY]["geolocation_check"] | {"pre_against_post": check["pre_against_post"]}
    assert "Tambon totals only" in record["o1_flood_input_interface"]["use_restriction"]
    assert "unless the owners decide so" in tables[SENSITIVITY]["o1_flood_input_interface"]["use_restriction"]
    assert {point["id"] for point in record["open_points"]} == {
        "A4-OP1", "A4-OP2", "A4-OP3", "A4-OP4", "A4-OP5", "A4-OP6", "A2-OP1",
    }


# --- the result document --------------------------------------------------


def test_document_repeats_the_tables(document: str, tables: dict[str, dict[str, Any]]) -> None:
    record, sensitivity = tables[RECORD], tables[SENSITIVITY]
    labels = {"un_spider": "UN-SPIDER reproduction", "m1_literal": "M1-literal", "m1_v2": "M1-v2 (frozen)"}
    for name, label in labels.items():
        a, b = record["methods"][name]["frame"], sensitivity["methods"][name]["frame"]
        assert (f"| {label} | {a['candidate_area_km2']:.2f} | {b['candidate_area_km2']:.2f} | "
                f"{100 * a['abstention_fraction']:.1f}% | {100 * b['abstention_fraction']:.1f}% |") in document
    for row in record["methods"]["un_spider"]["units"]:
        assert (f"| {row['unit_id']} {row['unit_name']} | {row['area_km2']:.2f} | 100.0% | 0.0% | "
                f"{row['candidate_area_km2']:.2f} |") in document
    for row in record["methods"]["m1_literal"]["units"]:
        assert (f"| {row['unit_id']} {row['unit_name']} | 100.0% | 0.0% | {row['candidate_area_km2']:.2f} | "
                f"{row['candidate_area_outside_permanent_water_km2']:.2f} |") in document
    for row in record["methods"]["m1_v2"]["units"]:
        code = ", ".join(row["low_confidence_reason_codes"]) or "none"
        assert (f"| {row['unit_id']} {row['unit_name']} | 100.0% | {100 * row['answer_coverage']:.1f}% | "
                f"{100 * row['abstention_fraction']:.1f}% | {row['candidate_area_km2']:.2f} | "
                f"{'yes' if row['answer_coverage_at_least_min'] else 'no'} | {code} |") in document
    for tile in record["methods"]["m1_v2"]["tiles"]:
        side = tile["whole_tile"]["sides"]["darkening"]
        threshold = "none" if side["threshold_db"] is None else f"{side['threshold_db']:.1f}"
        assert f"| {tile['tile']} | {tile['frame_cells_in_tile']:,} |" in document
        assert f"| {side['selected_blocks']} | {threshold} |" in document
    for name, label in (("m1_literal", "M1-literal"), ("m1_v2", "M1-v2 (frozen)")):
        levels = record["methods"][name]["threshold_levels"]["frame_km2"]
        assert (f"| {label} | {levels['strictest']:.2f} | {levels['central']:.2f} | "
                f"{levels['loosest']:.2f} |") in document
    assert record["methods"]["un_spider"]["statement"].replace("; ", ";") in document.replace("\n   ", " ").replace("; ", ";")
    steps = record["methods"]["un_spider"]["steps"]
    for key in ("cells_above_threshold", "cells_removed_as_perennial_water", "cells_removed_by_connected_pixel_rule",
                "cells_removed_by_slope_rule", "candidate_cells"):
        assert f"{steps[key]:,}" in document
    binding = review.require_frozen_m1_v2(ROOT)
    assert binding["frozen_config_sha256"] in document
    assert binding["code_sha256"]["src/floodguard/sar_change_v2.py"] in document
    for run in RUNS:
        stamp = tables[run]["generated_at_utc"]
        assert f"| {stamp[11:19]} |" in document


def test_document_states_the_result_the_limits_and_the_open_points(document: str) -> None:
    flat = " ".join(document.split())
    assert "Verify before action" in flat and "Tier 2 own candidates: verify before action." in flat
    assert "approximate geocoding: GCP affine, no DEM terrain correction" in flat
    assert "M1-v2 does not meet the T2 skill bar at Mae Sai" in flat
    # Decision R15: said beside the result, every time the result is stated.
    assert flat.count("not distinguishable from 0.40 on 14 tiles") == 2
    assert flat.count("67.9% of the GEOID test cells had no answer") == 2
    assert flat.count("agreement with a same-pass CEMS map, not an independent check") == 2
    assert "residual water only" in flat and "twelve days apart" in flat
    assert "No qualified reference exists for Mae Sai" in flat
    assert "No candidate was compared with UNOSAT/GISTDA product 4009 (guardrail GR4)" in flat
    assert flat.count("4009") == 1
    assert "670 m west and 130 m north" in flat and "It replaces nothing" in flat
    for point in ("A4-OP1", "A4-OP2", "A4-OP3", "A4-OP4", "A4-OP5", "A4-OP6", "A2-OP1"):
        assert f"| {point} |" in document
    assert "No flood-inputs module (plan task E1) is on this branch" in flat
    assert "No FPPS, no A-E class and no ensemble was computed" in flat


def test_document_and_tables_pass_the_shared_wording_lint(
    document: str, tables: dict[str, dict[str, Any]], receipts: dict[str, dict[str, Any]]
) -> None:
    assert find_violations(document, RULES, "result document") == []
    readme = (OUTPUTS / "README.md").read_text(encoding="utf-8")
    section = readme.split("### Radar flood candidates of case O1 (plan tasks A2 and A4)", 1)[1]
    assert find_violations(section, RULES, "outputs README") == []
    for run in RUNS:
        for payload in (tables[run], receipts[run]):
            assert [finding for path, text in json_strings(payload)
                    for finding in find_violations(text, RULES, path)] == []
    raw = DOCUMENT.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n") and raw.isascii()
