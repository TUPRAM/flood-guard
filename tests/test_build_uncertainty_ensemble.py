"""The uncertainty-ensemble builder (plan task E10), run end to end on an invented frame.

Everything the builder reads here is invented and written into a temporary folder: the invented frame of
``tests/test_build_planning_assessment.py`` (two units in the open sea, a road graph of eight nodes, five demand
cells, a flood polygon at three levels, a water polygon, an age table, and the receipts that bind them), with the
task E8 run of that frame made first, because the ensemble stands on it. No layer or table of a real case is read
and no component of a real unit is computed. What is real is what every run reads unchanged: the two signed
protocol files and the national-anchor receipt protocol v1b names. One test asks for case O1 of the Mae Sai frame
and is refused before any input of a unit is read; the refusal is worded from two committed receipts.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from floodguard import rights
from floodguard.normalisation import NormalisationError

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The invented frame and the task E8 runner of the planning-assessment tests; the ensemble builder uses that runner.
fx = sys.modules.get("test_build_planning_assessment") or _load(
    "test_build_planning_assessment", ROOT / "tests" / "test_build_planning_assessment.py")
sys.modules["build_planning_assessment"] = fx.runner
runner = _load("build_uncertainty_ensemble", ROOT / "scripts" / "build_uncertainty_ensemble.py")

CASE = fx.CASE
LABEL, PROCESSED = fx.LABEL, fx.PROCESSED
STAGE = f"{PROCESSED}/fx_case/{runner.STAGE_FOLDER}"
RECEIPT_NAME = "e10_uncertainty_ensemble_fx-e8_fx_frame.json"
RESULTS_NAME = "uncertainty_ensemble_fx-e8_fx_frame.json"


def world_with_an_e8_run(tmp_path: Path, residents: dict[str, float] | None = None) -> dict[str, Any]:
    world = fx.build_world(tmp_path, residents)
    fx.run(world)
    return world


def arguments_of(world: dict[str, Any], **changes: Any) -> dict[str, Any]:
    arguments = dict(root=world["root"], output_dir=world["output_dir"], register_dir=world["register_dir"],
                     registry=world["registry"])
    arguments.update(changes)
    return arguments


def run(world: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return runner.run(CASE, world["frame_set"], world["external"], world["boundaries"],
                      **arguments_of(world, git_commit="0123abc", **changes))


# The invented flood is the box (100, 100) to (300, 500) m; unit 1 is the land south of y = 300 m, 2,000 m by 800 m, less
# 2,500 m2 of permanent water that lies inside the flood. The flooded land of unit 1 outside that water, by hand:
LAND_OF_UNIT_1_M2 = 2_000 * 800 - 2_500
FLOODED_LAND_OF_UNIT_1_M2 = {
    # Shrunk by 20 m: 160 m by 180 m, and 30 m by 30 m of the water is still inside.
    "minus": 160 * 180 - 30 * 30,
    "as_provided": 200 * 200 - 2_500,
    # Grown by 20 m with round corners: 240 m by 220 m less the two corners south of the flood, each a 20 m square
    # without its quarter disc. (The layer draws a quarter circle with 16 segments, about 1 m2 less than a disc.)
    "plus": 240 * 220 - 2 * (20 * 20 - math.pi * 20 * 20 / 4) - 2_500,
}


def flood_likelihood_by_hand(flood_level: str) -> float:
    """100 x min(1, flooded share of the land outside permanent water / 0.20), for unit 1 of the invented frame."""

    return 100 * min(1.0, FLOODED_LAND_OF_UNIT_1_M2[flood_level] / LAND_OF_UNIT_1_M2 / 0.20)


def nothing_was_written(world: dict[str, Any]) -> bool:
    return (not (world["output_dir"] / RECEIPT_NAME).exists() and not (world["register_dir"] / RECEIPT_NAME).exists()
            and not (world["external"] / STAGE).exists())


def test_the_builder_uses_the_task_e8_and_task_e5_builders_unchanged() -> None:
    assert runner.e8_builder is fx.runner and runner.e5_builder is fx.runner.e5_builder
    assert runner.FRAME_SETS is fx.runner.FRAME_SETS and set(runner.FRAME_SETS["mae_sai"].case_folders) == {"SE1", "O2"}
    assert runner.LEVEL == "public" and runner.STAGE_FOLDER == "e10_uncertainty_ensemble"


def test_a_run_on_an_invented_frame_reports_every_cell_and_headlines_nothing(tmp_path: Path) -> None:
    world = world_with_an_e8_run(tmp_path)
    e8_receipt = json.loads((world["output_dir"] / "e8_planning_assessment_fx-e8_fx_frame.json").read_text(encoding="ascii"))
    summary = run(world, development_reads=["An invented read made before the run."])
    assert summary["computed"] is True and summary["not_computed_because"] is None
    assert (summary["cells_run"], summary["cells_not_run"]) == (90, 450)
    results_path = world["external"] / STAGE / RESULTS_NAME
    assert summary["files"] == [f"{LABEL}/{STAGE}/{RESULTS_NAME}"] and summary["publication_eligibility"] == "local"
    raw = results_path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert not list(tmp_path.rglob("apps")), "nothing is written under apps/web"

    # The receipt: registered with one small file, it binds the file outside Git and every input by SHA-256.
    receipt_path = world["output_dir"] / RECEIPT_NAME
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    entry = json.loads((world["register_dir"] / RECEIPT_NAME).read_text(encoding="ascii"))
    assert entry == {"path": f"outputs/planning_v1/{RECEIPT_NAME}", "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
    assert receipt["protocol_sha256"] == fx.HASHES and receipt["run_kind"] == "first_run" and receipt["status"] == "run_receipt"
    assert receipt["schema_version"] == runner.RECEIPT_SCHEMA == "floodguard.uncertainty_ensemble_run_receipt.v2"
    assert receipt["confidence_class"] == "low" and receipt["official_warning"] is False and receipt["assumptions"]
    assert receipt["operational_status"] == "non_operational" and receipt["source_timestamp"] == "2030-01-11"
    assert receipt["generated_at_utc"] == summary["generated_at_utc"]
    assert runner.bound_outputs(receipt["outputs"]) == {summary["files"][0]: hashlib.sha256(raw).hexdigest()}
    assert receipt["rights"]["publication_eligibility"] == "local" and receipt["rights"]["written_under_apps_web_public"] is False
    assert receipt["development_reads"]["reads"] == ["An invented read made before the run."]
    inputs = receipt["inputs"]
    assert inputs["e8_run"]["rows_sha256"] == e8_receipt["result"]["rows_sha256"] and "rows" not in inputs["e8_run"]
    assert inputs["e8_run"]["receipt"]["sha256"] == hashlib.sha256(
        (world["output_dir"] / "e8_planning_assessment_fx-e8_fx_frame.json").read_bytes()).hexdigest()
    assert set(inputs["closure_extents_routing_context"]) == {"minus", "as_provided", "plus"}
    assert receipt["lineage_input_sha256"] == e8_receipt["lineage_input_sha256"], "the lineage is that of the task E8 run"

    # Every one of the 540 core cells is reported: 90 run, 450 not run, each with its reason.
    cells = receipt["cells"]
    assert len(cells["run"]) == 90 and sum(len(items) for items in cells["not_run"].values()) == 450
    assert len({*cells["run"], *(item for items in cells["not_run"].values() for item in items)}) == 540
    not_run = receipt["parameters"]["levels_not_run"]
    assert [(item["axis"], item["level"]) for item in not_run] == [
        ("facilities", "corroborated"), ("facilities", "all_listed"), ("population_vintage", "rescaled_2024")]
    assert all("not approximated" in item["reason"] for item in not_run)
    assert "E5-OP5" in not_run[0]["open_points"] and not_run[2]["open_points"] == ["E10-OP2"]
    assert receipt["parameters"]["levels_run"] == {
        "flood_input_single_state": ["minus", "as_provided", "plus"], "passability": ["strict", "central", "permissive"],
        "facilities": ["public"], "population_vintage": ["worldpop_2020"], "vulnerability_anchors": ["P10_P90", "P5_P95"],
        "weights": ["default", "access_heavy", "exposure_heavy", "road_heavy", "vulnerability_heavy"]}
    assert receipt["parameters"]["grid"]["core_cells_per_lane"] == 540
    # The distance of the minus and plus levels is the one of the grid, and the input record of task E1 states the same.
    assert receipt["parameters"]["one_pixel_m"] == {
        "minus": 20.0, "plus": 20.0, "source": runner.ONE_PIXEL_SOURCE, "input_record_of_task_e1": 20.0,
        "note": receipt["parameters"]["one_pixel_m"]["note"]}
    assert receipt["parameters"]["grid"]["one_pixel_m"] == 20.0
    assert any("shrunk and grown by 20 m (one pixel" in line for line in receipt["assumptions"])

    # The access runs: nine, by the unchanged task E5 runner; those at the level as provided reproduce the E5 table.
    access = receipt["access_runs"]
    assert [(item["flood_level"], item["closure_level"]) for item in access["runs"]] == [
        (flood_level, level) for flood_level in ("minus", "as_provided", "plus") for level in ("strict", "central", "permissive")]
    assert access["checks"]["as_provided_runs_against_the_e5_table"]["result"] == "PASS"
    assert all(row["unit_rows_same"] and row["closure_result_same"]
               for row in access["checks"]["as_provided_runs_against_the_e5_table"]["compared"])
    assert access["checks"]["against_calculate_total_access_all_same"] is True and access["checks"]["residents_gaining_access"] == 0.0
    assert access["checks"]["intersected_edges_not_fewer_at_a_larger_flood_level"] is True
    # The invented flood shrunk by 20 m leaves 80 of the 200 m of each edge at r1 inside: the strict level then closes
    # only the edge that lies wholly inside, where the central level still closes all four (80 m is over 30 m).
    closed = {(item["flood_level"], item["closure_level"]): item["closure"]["vehicle"]["closed_edges"] for item in access["runs"]}
    assert closed[("minus", "strict")] == 1 < closed[("as_provided", "strict")] and closed[("minus", "central")] == 4
    checks = receipt["measurement_checks"]
    assert checks["combinations_measured"] == 9 and checks["default_combination_is_the_measurement_of_task_e8"] is True
    assert checks["residents_and_baseline_counts_same_in_every_access_run"] is True
    assert checks["flooded_land_not_smaller_at_a_larger_flood_level_in_every_unit"] is True
    assert checks["residents_inside_not_fewer_at_a_larger_flood_level_in_every_unit"] is True
    assert checks["each_combination_carries_the_flood_measurements_of_its_own_level"] is True
    assert "measurements handed to the ensemble" in checks["flood_level_checks_read"]

    # The default cell is the rows the registered task E8 receipt records.
    result = receipt["result"]
    assert result["computed"] is True and result["not_computed_because"] is None
    assert result["default_cell_against_the_e8_rows"] == {
        "result": "PASS", "rows": 2, "rows_sha256": e8_receipt["result"]["rows_sha256"],
        "what": result["default_cell_against_the_e8_rows"]["what"]}
    counts = result["summary"]
    assert counts["units"] == 2 and counts["unit_cells_with_a_result"] == 180 and counts["unit_cells_failed"] == 0
    assert counts["reference_class_counts"] == {"A": 0, "B": 1, "C": 0, "D": 0, "E": 0, "no_class": 1}
    assert counts["headline_status_counts"] == {"not_evaluated": 2, "headline_eligible": 0, "unstable_verify": 0}
    assert counts["retention_over_the_cells_run"]["units_keeping_the_class_in_at_least_the_minimum_share"] == 1
    assert counts["retention_over_the_cells_run"]["units_without_a_class_to_keep"] == 1
    assert "FX-E8-U1" not in json.dumps({key: receipt[key] for key in ("result", "access_runs", "measurement_checks", "cells")}), (
        "the receipt holds counts for the case, not a unit's values")
    assert receipt["licence"] is None, "the invented flood input is not product 4009"
    assert {point["id"] for point in receipt["open_points"]} == {f"E10-OP{number}" for number in range(1, 13)}
    # The receipt names no unit beside a value and says which of its counts state a value of a single unit all the same
    # (open point E10-OP10): class B is held by one unit in the default cell, and no unit has it in ten cells.
    declared = receipt["rights"]["figures_of_local_level_layers_in_this_receipt"]
    assert "names no unit beside a value" in declared["what"] and "puts no unit beside a value" not in json.dumps(receipt)
    single = declared["counts_that_state_a_value_of_a_single_unit"]
    assert single["states_a_value_of_a_single_unit"] is True and single["classes_one_unit_alone_holds_in_the_default_cell"] == ["B"]
    assert single["cells_in_which_such_a_class_has_another_count"] == 10 == single["cells_whose_class_counts_differ_from_the_default_cell"]
    assert single["cells_in_which_every_unit_has_one_class"] == 0 and single["units_with_more_than_one_class_over_the_cells_run"] == 1
    assert "E10-OP8" in single["cannot_be_rebuilt_from_committed_files"] and "E10-OP10" in declared["for_the_owners"]
    assert counts["counts_that_state_a_value_of_a_single_unit"]["classes_one_unit_alone_holds_in_the_default_cell"] == ["B"]

    # The file outside Git: every cell of every unit, the summaries, and the access runs of the minus and plus levels.
    document = json.loads(raw.decode("ascii"))
    assert document["schema_version"] == runner.RESULTS_SCHEMA and document["generated_at_utc"] == summary["generated_at_utc"]
    assert document["official_warning"] is False and document["protocol_sha256"] == fx.HASHES and document["assumptions"]
    assert document["accepted_fpps"] is None and document["accepted_action_class"] is None
    assert document["class_e_wording"].endswith("Class E never means safe.")
    assert runner.digest_of(document["units"]) == result["units_sha256"]
    first, second = document["units"]
    # Unit 1 is class B in the default cell (task E8). With the flood shrunk by 20 m and the strict level, the roads
    # around r1 stay open, nobody is cut off, and the unit is class E: 10 of the 90 cells that were run.
    assert first["reference_cell"]["action_class"] == "B" and first["reference_cell"]["fpps_0_100"] == 46.56
    assert first["class_counts"] == {"A": 0, "B": 80, "C": 0, "D": 0, "E": 10, "no_class": 0}
    assert {cell["cell_id"].split("|")[0] + "|" + cell["cell_id"].split("|")[1] for cell in first["cells"]
            if cell["action_class"] == "E"} == {"minus|strict"}
    headline = first["headline_stability"]
    assert headline["status"] == "not_evaluated" and headline["class_retention"] is None
    assert headline["retention_over_the_cells_run"] == pytest.approx(80 / 90)
    assert headline["bounds_over_the_protocol_set"] == {"lower": 80 / 180, "upper": 170 / 180, "cells_without_a_class": 90}
    assert headline["after_declared_cut_line_6"]["retention"] == pytest.approx(40 / 45)
    assert first["people_losing_30_minute_access"]["hospital"]["min"] == 0.0
    assert first["people_losing_30_minute_access"]["hospital"]["max"] == 5000.0
    assert first["fpps_swing"]["by_axis"]["facilities"]["measured"] is False
    # The flood likelihood of each combination is that of its own flood level, by hand; the exposure is the same at the
    # three levels here, because the one cell of unit 1 inside the flood is inside all three.
    by_level = {level: flood_likelihood_by_hand(level) for level in ("minus", "as_provided", "plus")}
    assert by_level["minus"] == pytest.approx(8.7324, abs=1e-4) and by_level["as_provided"] == pytest.approx(11.7371, abs=1e-4)
    assert by_level["plus"] == pytest.approx(15.690, abs=1e-3)
    assert len(first["routing_combinations"]) == 9
    for item in first["routing_combinations"]:
        components = item["components"]
        assert components["flood_likelihood_0_100"] == pytest.approx(by_level[item["flood_input_single_state"]], abs=0.002), item
        assert components["exposure_0_100"] == pytest.approx(100 * 400 / 5500), item
    # Unit 2 has 50 residents: guardrail GR1, no class in any cell, so no class to retain.
    assert second["class_counts"]["no_class"] == 90 and second["headline_stability"]["reference_class"] is None
    assert [(item["flood_level"], item["closure_level"]) for item in document["access_runs"]["runs"]] == [
        (flood_level, level) for flood_level in ("minus", "plus") for level in ("strict", "central", "permissive")]
    assert len(document["access_runs"]["runs"][0]["units"]) == 2 and len(document["cells"]) == 540

    # --verify computes everything again to the same bytes and writes nothing.
    before = sorted((str(path), path.stat().st_mtime_ns) for path in tmp_path.rglob("*") if path.is_file())
    verified = runner.verify(CASE, world["frame_set"], world["external"], world["boundaries"], **arguments_of(world))
    assert verified == {"verified": True, "computed": True, "receipt_body_same": True, "receipt_fields_that_differ": [],
                        "outputs_block_same": True, "files_on_disk_same_as_recomputed": True, "code_changed_since_the_run": []}
    checked = runner.check_inputs(CASE, world["frame_set"], world["external"], world["boundaries"], **arguments_of(world))
    assert checked["inputs_checked"] is True and checked["cells_that_would_be_run"] == 90 and checked["access_runs_to_make"] == 9
    assert sorted((str(path), path.stat().st_mtime_ns) for path in tmp_path.rglob("*") if path.is_file()) == before
    # A changed result file is seen.
    results_path.write_bytes(raw.replace(b'"fpps_0_100": 46.56', b'"fpps_0_100": 46.57', 1))
    assert runner.verify(CASE, world["frame_set"], world["external"], world["boundaries"], **arguments_of(world))["verified"] is False


def test_a_second_run_needs_a_reason_and_names_the_run_it_replaces(tmp_path: Path) -> None:
    world = world_with_an_e8_run(tmp_path)
    first = run(world)
    with pytest.raises(FileExistsError, match="--replace --reason"):
        run(world)
    old_results = (world["external"] / STAGE / RESULTS_NAME).read_bytes()
    second = run(world, replace_reason="An invented reason for a second run.")
    receipt = json.loads((world["output_dir"] / RECEIPT_NAME).read_text(encoding="ascii"))
    assert receipt["run_kind"] == "superseding_run" and receipt["supersedes"]["receipt_sha256"] == first["receipt_sha256"]
    assert receipt["supersedes"]["reason"] == "An invented reason for a second run."
    assert receipt["supersedes"]["result_same"] is True and receipt["supersedes"]["units_same"] is True
    assert receipt["supersedes"]["access_unit_rows_same"] is True and receipt["supersedes"]["lineage_inputs_same"] is True
    # The cells alone are compared too, read back from the file the first receipt bound, and the fields that differ are named.
    assert receipt["supersedes"]["unit_cells_same"] is True and receipt["supersedes"]["summary_fields_that_differ"] == []
    assert receipt["supersedes"]["unit_record_fields_that_differ"] == []
    assert len(receipt["supersedes"]["unit_cells_sha256_of_this_run"]) == 64
    assert all(item["copied"] is True for item in receipt["supersedes"]["copies_kept_outside_git"])
    assert receipt["supersedes"]["outputs_of_the_superseded_run"] == {first["files"][0]: hashlib.sha256(old_results).hexdigest()}
    history = receipt["run_history"]
    assert len(history) == 1 and history[0]["receipt_sha256"] == first["receipt_sha256"]
    assert history[0]["result_same_as_the_run_that_replaced_it"] is True
    assert history[0]["unit_cells_same_as_the_run_that_replaced_it"] is True
    # The superseded receipt and the file it bound are kept outside Git.
    kept = {Path(item["path"]).name: item["sha256"] for item in receipt["supersedes"]["copies_kept_outside_git"]}
    assert kept == {RECEIPT_NAME: first["receipt_sha256"], RESULTS_NAME: hashlib.sha256(old_results).hexdigest()}
    archive = next((world["external"] / STAGE / runner.SUPERSEDED_FOLDER).iterdir())
    assert hashlib.sha256((archive / RESULTS_NAME).read_bytes()).hexdigest() == kept[RESULTS_NAME]
    entry = json.loads((world["register_dir"] / RECEIPT_NAME).read_text(encoding="ascii"))
    assert entry["sha256"] == second["receipt_sha256"] != first["receipt_sha256"]
    with pytest.raises(FileNotFoundError, match="existing receipt"):
        fresh = world_with_an_e8_run(tmp_path / "other")
        run(fresh, replace_reason="Nothing to replace.")


def test_the_flood_likelihood_the_exposure_and_the_30_minute_losses_are_those_of_the_cell(tmp_path: Path,
                                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """A second invented frame in which the three flood levels hold other residents and 15 and 30 minutes differ.

    Two invented cells that touch no road are placed at the edge of the invented flood: one 10 m inside its west
    edge (inside the extent as provided and grown, outside the extent shrunk by 20 m), one 10 m outside its east
    edge (inside the grown extent only). And the street to the 4,600 residents at q takes 20 minutes, so they reach
    the hospital and the main road within 30 minutes and not within 15.
    """

    monkeypatch.setattr(fx, "CELL_SITES", {**fx.CELL_SITES, "c5": (None, (110.0, 200.0)), "c6": (None, (310.0, 200.0))})
    monkeypatch.setattr(fx, "STREETS", [street if street[0] != "r-q" else (*street[:4], 0.6) for street in fx.STREETS])
    world = world_with_an_e8_run(tmp_path, {**fx.RESIDENTS, "c5": 500.0, "c6": 200.0})
    summary = run(world)
    assert summary["computed"] is True
    receipt = json.loads((world["output_dir"] / RECEIPT_NAME).read_text(encoding="ascii"))
    document = json.loads((world["external"] / STAGE / RESULTS_NAME).read_text(encoding="ascii"))
    first = document["units"][0]
    # Residents of unit 1: c1 400, c4 4,600, c5 500, c6 200. Inside the extent: c1 at every level, c5 from the level as
    # provided on, c6 at the plus level only.
    residents = 400 + 4600 + 500 + 200
    exposure = {"minus": 100 * 400 / residents, "as_provided": 100 * 900 / residents, "plus": 100 * 1100 / residents}
    seen: dict[str, set[tuple[float, float]]] = {level: set() for level in exposure}
    assert len(first["routing_combinations"]) == 9
    for item in first["routing_combinations"]:
        level, components = item["flood_input_single_state"], item["components"]
        assert components["flood_likelihood_0_100"] == pytest.approx(flood_likelihood_by_hand(level), abs=0.002), item
        assert components["exposure_0_100"] == pytest.approx(exposure[level]), item
        seen[level].add((components["flood_likelihood_0_100"], components["exposure_0_100"]))
    assert all(len(values) == 1 for values in seen.values()), "one flood likelihood and one exposure for each flood level"
    (minus,), (provided,), (plus,) = (tuple(seen[level]) for level in ("minus", "as_provided", "plus"))
    assert minus[0] < provided[0] < plus[0] and minus[1] < provided[1] < plus[1], "minus < as provided < plus, in both components"
    checks = receipt["measurement_checks"]
    assert checks["flooded_land_not_smaller_at_a_larger_flood_level_in_every_unit"] is True
    assert checks["residents_inside_not_fewer_at_a_larger_flood_level_in_every_unit"] is True
    # The residents losing access within 30 minutes are counted at 30 minutes. In unit 1, under the flood as provided,
    # all 5,000 connected residents lose the hospital and the main road; within 15 minutes only the 400 at r1 had either.
    losing = first["people_losing_30_minute_access"]
    assert losing["hospital"]["max"] == 5000.0 and losing["main_road_entry"]["max"] == 5000.0
    assert losing["hospital"]["threshold_minutes"] == 30 and losing["hospital"]["count"] == 9
    e5_rows = {row["closure_level"]: row for row in world["access_table"]["runs"]}
    lost = e5_rows["central"]["units"][0]["access"]["main_road_entry"]["thresholds_minutes"]
    assert (lost["15"]["newly_lost_residents"], lost["30"]["newly_lost_residents"]) == (400.0, 5000.0), "the fixture tells them apart"
    # The whole frame adds the 50 residents of unit 2, who lose both services too.
    whole = {(item["flood_level"], item["closure_level"]): item for item in receipt["access_runs"]["runs"]}
    assert whole[("as_provided", "central")]["newly_lost_residents_within_30_minutes"] == {"hospital": 5050.0, "main_road_entry": 5050.0}
    assert whole[("as_provided", "central")]["access_gap_inputs"]["main_road_entry"]["newly_lost_residents"] == 450.0, (
        "the access-gap threshold of the main-road entry is 15 minutes")


@pytest.mark.parametrize("error", [RuntimeError("an invented error of a geometry library"), KeyError("an invented key"),
                                   OSError("an invented file that cannot be read")])
def test_an_error_that_is_not_a_check_still_ends_in_a_registered_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                         error: Exception) -> None:
    """Once the units are measured, any error is reported: not only the refusal of a check (a ValueError)."""

    assert not isinstance(error, ValueError)
    world = world_with_an_e8_run(tmp_path)
    real = runner.flood_inputs.flooded_land_areas
    calls = {"count": 0}

    def fails_on_another_level(*arguments: Any, **keywords: Any) -> Any:
        # The first two calls measure the two units as task E8 does; the next lays another flood level over a unit.
        calls["count"] += 1
        if calls["count"] > 2:
            raise error
        return real(*arguments, **keywords)

    monkeypatch.setattr(runner.flood_inputs, "flooded_land_areas", fails_on_another_level)
    summary = run(world)
    assert summary["computed"] is False and summary["not_computed_because"] == "unexpected_error"
    receipt_path = world["output_dir"] / RECEIPT_NAME
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    entry = json.loads((world["register_dir"] / RECEIPT_NAME).read_text(encoding="ascii"))
    assert entry["sha256"] == hashlib.sha256(receipt_path.read_bytes()).hexdigest(), "the run is registered"
    reported = receipt["result"]["not_computed_because"]
    assert (reported["code"], reported["stage"], reported["error"]) == ("unexpected_error", "unit_measurements", type(error).__name__)
    assert reported["message"].startswith("An error that is not a check of this builder stopped the run")
    assert "invented" not in json.dumps(receipt["result"]), "the message of the error, which may name units, is outside Git"
    assert receipt["result"]["summary"] is None and receipt["access_runs"] is None and receipt["measurement_checks"] is None
    declared = receipt["rights"]["figures_of_local_level_layers_in_this_receipt"]
    assert declared["figures"] == [] and declared["counts_that_state_a_value_of_a_single_unit"]["states_a_value_of_a_single_unit"] is False
    document = json.loads((world["external"] / STAGE / RESULTS_NAME).read_text(encoding="ascii"))
    assert document["units"] is None and "invented" in document["not_computed_because"]["message"]


def test_the_receipt_to_replace_is_read_before_any_unit_is_measured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A receipt that cannot be read refuses a second run before it starts, not after its units were measured."""

    world = world_with_an_e8_run(tmp_path)
    run(world)
    receipt_path = world["output_dir"] / RECEIPT_NAME
    good = receipt_path.read_bytes()
    register_entry = (world["register_dir"] / RECEIPT_NAME).read_bytes()
    results = (world["external"] / STAGE / RESULTS_NAME).read_bytes()

    def must_not_run(*_arguments: Any, **_keywords: Any) -> Any:
        raise AssertionError("no unit may be measured when the receipt to replace cannot be read")

    monkeypatch.setattr(runner, "build", must_not_run)
    parsed = json.loads(good)
    broken = [
        (good[:200], "cannot be read"),                                                       # not JSON
        (good.replace(b'"run_receipt"', b'"run_receipt\xc3\xa9"', 1), "cannot be read"),      # not ASCII
        (runner.encode({**parsed, "schema_version": "floodguard.another_receipt.v1"}), "not a receipt of this task"),
        (runner.encode({**parsed, "parameters": {**parsed["parameters"], "case_id": "FX-OTHER"}}), "not a receipt of this task"),
        (runner.encode({key: value for key, value in parsed.items() if key != "outputs"}), "does not bind its outputs"),
        (runner.encode({**parsed, "run_history": "none"}), "does not list its earlier runs"),
        (runner.encode([parsed]), "not a receipt of this task"),
    ]
    for data, words in broken:
        receipt_path.write_bytes(data)
        with pytest.raises(runner.BuildError, match=words):
            run(world, replace_reason="An invented reason for a second run.")
        assert receipt_path.read_bytes() == data, "nothing is written"
        assert (world["register_dir"] / RECEIPT_NAME).read_bytes() == register_entry
        assert (world["external"] / STAGE / RESULTS_NAME).read_bytes() == results
        assert not (world["external"] / STAGE / runner.SUPERSEDED_FOLDER).exists()
    # The receipt as the first run wrote it is read and checked, and the second run goes ahead.
    receipt_path.write_bytes(good)
    monkeypatch.undo()
    again = run(world, replace_reason="An invented reason for a second run.")
    assert again["computed"] is True
    # A receipt of schema version 1, as the first runs of this task wrote it, can be replaced too.
    previous, sha256, bound = runner.receipt_to_replace(receipt_path, CASE)
    assert sha256 == again["receipt_sha256"] and list(bound) == again["files"]
    receipt_path.write_bytes(runner.encode({**previous, "schema_version": "floodguard.uncertainty_ensemble_run_receipt.v1"}))
    assert runner.receipt_to_replace(receipt_path, CASE)[0]["schema_version"].endswith(".v1")


def test_the_distance_of_the_minus_and_plus_levels_is_the_one_the_protocol_states(tmp_path: Path,
                                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """The receipt, the assumptions and the change notice take the distance from the grid; task E1 must have used it."""

    grid = runner.ensemble.load_grid(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json", DOCS / "RECEIPTS.jsonl")
    assert grid.one_pixel_m == 20.0
    assert "shrunk and grown by 20 m (one pixel" in runner.assumptions(grid.one_pixel_m)[1]
    assert "shrunk and grown by 10 m (one pixel" in runner.assumptions(10.0)[1] and "20 m" not in " ".join(runner.assumptions(10.0))
    assert "shrunk and grown by 10 m and under" in runner.change_notice_step(10.0) and "20" not in runner.change_notice_step(10.0)
    assert len(runner.assumptions(20.0)) == 8 and runner.assumptions(20.0)[-1].endswith("Class E never means safe.")
    # The change notice of a product 4009 run is carried on with the distance of the grid.
    notice = "Changed by an invented step. " + runner.VALUES_SENTENCE
    found = SimpleNamespace(licence={"name": "an invented licence", "change_notice": notice}, grid=replace(grid, one_pixel_m=10.0))
    carried = runner.licence_of_the_run(found)["change_notice"]
    assert "shrunk and grown by 10 m" in carried and carried.endswith(runner.VALUES_SENTENCE) and "20 m" not in carried
    # A protocol that states another distance than the one task E1 wrote its levels with refuses the run.
    world = world_with_an_e8_run(tmp_path)
    monkeypatch.setattr(runner.ensemble, "load_grid", lambda *_arguments: replace(grid, one_pixel_m=10.0))
    with pytest.raises(runner.BuildError, match="one-pixel distance 20.0; protocol v1b states 10 m"):
        run(world)
    assert nothing_was_written(world)
    monkeypatch.undo()
    # An input record that states no distance is refused too.
    record_path = world["flood_folder"] / runner.flood_inputs.INPUT_RECORD_NAME
    monkeypatch.setattr(runner.e8_builder, "prepare", _without_the_distance(runner.e8_builder.prepare))
    with pytest.raises(runner.BuildError, match="one-pixel distance None"):
        run(world)
    assert nothing_was_written(world) and record_path.is_file()


def _without_the_distance(prepare: Any) -> Any:
    """Wrap the input checks of task E8 so that the input record they return states no one-pixel distance."""

    def wrapped(*arguments: Any, **keywords: Any) -> Any:
        found = prepare(*arguments, **keywords)
        found.record = {key: value for key, value in found.record.items() if key != "levels"}
        return found

    return wrapped


def test_the_builder_refuses_before_any_unit_is_measured_and_then_writes_nothing(tmp_path: Path) -> None:
    """The refusals of the task E8 builder, and those this task adds; each leaves no receipt, no entry and no file."""

    # No task E8 run of the case: the ensemble has no default cell to stand on.
    world = fx.build_world(tmp_path / "no_e8")
    with pytest.raises(runner.BuildError, match="receipt of the task E8 run is missing"):
        run(world)
    assert nothing_was_written(world)

    # A task E8 receipt that is not the registered one.
    world = world_with_an_e8_run(tmp_path / "e8_edited")
    path = world["output_dir"] / "e8_planning_assessment_fx-e8_fx_frame.json"
    path.write_bytes(path.read_bytes().replace(b'"status": "run_receipt"', b'"status": "run_receipt" ', 1))
    with pytest.raises(runner.BuildError, match="not the file the run register holds"):
        run(world)
    assert nothing_was_written(world)

    # The overlay the task E8 receipt binds was changed.
    world = world_with_an_e8_run(tmp_path / "overlay_edited")
    overlay = world["external"] / PROCESSED / "fx_case" / fx.runner.STAGE_FOLDER / "planning_assessment_overlay_fx-e8_fx_frame.json"
    overlay.write_bytes(overlay.read_bytes() + b"\n")
    with pytest.raises(runner.BuildError, match="file the task E8 receipt binds is missing or is not the file it names"):
        run(world)
    assert nothing_was_written(world)

    # A task E8 run made from other inputs: the age table was replaced and registered after it.
    world = world_with_an_e8_run(tmp_path / "other_inputs")
    table_path = world["output_dir"] / "fx_age_table.json"
    table = json.loads(table_path.read_text(encoding="ascii"))
    table["units"][0]["children_0_14"] += 1.0
    sha256 = fx._write(table_path, fx._json(table))
    fx._write(world["output_dir"] / "fx_e7_receipt.json", fx._json({
        "generated_at_utc": "2030-01-03T00:00:00Z", "protocol_sha256": fx.HASHES,
        "outputs": [{"path": "outputs/planning_v1/fx_age_table.json", "sha256": sha256}]}))
    fx.register(world, "fx_age_table.json")
    fx.register(world, "fx_e7_receipt.json")
    with pytest.raises(runner.BuildError, match="made from other inputs"):
        run(world)
    assert nothing_was_written(world)

    # A flood extent of the minus level that is not the file the E1 receipt binds.
    world = world_with_an_e8_run(tmp_path / "extent_edited")
    extent = world["flood_folder"] / "flood_extent__minus__routing_context.geojson"
    extent.write_bytes(extent.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="cannot be read|not the one the registered E1 receipt binds"):
        run(world)
    assert nothing_was_written(world)

    # The access table says it is not usable (a candidate walking context, for example).
    world = world_with_an_e8_run(tmp_path / "unusable")
    fx.write_access_table(world, {**world["access_table"], "usable_by_task_e8": False, "usable_by_task_e8_basis": "An invented basis."})
    with pytest.raises(ValueError, match="not usable by task E8"):
        run(world)
    assert nothing_was_written(world)

    # The rights registry holds no confirmed record of the flood layer.
    world = world_with_an_e8_run(tmp_path / "rights")
    with pytest.raises(ValueError):
        run(world, registry=rights.RightsRegistry(world["root"], records=()))
    assert nothing_was_written(world)

    # A case the earlier tasks have not delivered, and a case that is not of the frame.
    world = world_with_an_e8_run(tmp_path / "cases")
    for case_id, words in (("FX-O1", "cannot be run"), ("FX-NONE", "not a case of frame")):
        with pytest.raises(runner.BuildError, match=words):
            runner.run(case_id, world["frame_set"], world["external"], world["boundaries"], **arguments_of(world, git_commit="0123abc"))
    assert nothing_was_written(world)


def test_the_builder_refuses_to_run_unless_both_protocols_are_in_force(tmp_path: Path) -> None:
    """Guardrail GR5: no ensemble cell is computed for a unit unless both files are signed and recorded."""

    world = world_with_an_e8_run(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in ("planning_protocol_v1a.json", "planning_protocol_v1b.json", "RECEIPTS.jsonl"):
        shutil.copy(DOCS / name, docs / name)
    edited = (docs / "planning_protocol_v1b.json").read_bytes().replace(b'"status": "signed"', b'"status": "signed" ', 1)
    (docs / "planning_protocol_v1b.json").write_bytes(edited)
    with pytest.raises(NormalisationError, match="not in force"):
        run(world, docs=docs)
    assert nothing_was_written(world)


def test_a_run_that_measures_its_units_and_then_fails_a_check_is_still_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The access table of record differs from the runs of this task: no figure is reported, and the run is."""

    world = fx.build_world(tmp_path)
    table = json.loads(json.dumps(world["access_table"]))
    # One count that neither the task E8 checks nor its components read: the residents who lose the hospital within 60 minutes.
    table["runs"][0]["units"][0]["access"]["hospital"]["thresholds_minutes"]["60"]["newly_lost_residents"] += 1.0
    fx.write_access_table(world, table)
    fx.run(world)
    summary = run(world)
    assert summary["computed"] is False and summary["not_computed_because"] == "as_provided_runs_differ_from_the_e5_table"
    receipt = json.loads((world["output_dir"] / RECEIPT_NAME).read_text(encoding="ascii"))
    assert (world["register_dir"] / RECEIPT_NAME).is_file(), "every run on units is reported, also one that fails a check"
    result = receipt["result"]
    assert result["computed"] is False and result["summary"] is None and result["units_sha256"] is None
    assert result["not_computed_because"]["stage"] == "as_provided_runs_against_the_e5_table"
    assert receipt["access_runs"] is None and receipt["measurement_checks"] is None, "no figure of a run that failed a check"
    document = json.loads((world["external"] / STAGE / RESULTS_NAME).read_text(encoding="ascii"))
    assert document["units"] is None and document["access_runs"]["runs"] is None
    assert "do not reproduce the registered task E5 table" in document["not_computed_because"]["message"]
    assert len(receipt["cells"]["run"]) == 90, "the cells the run set out to compute are still listed"
    verified = runner.verify(CASE, world["frame_set"], world["external"], world["boundaries"], **arguments_of(world))
    assert verified["verified"] is True and verified["computed"] is False

    # Another stage: the ensemble itself refuses. The receipt names the stage; a second run needs a reason.
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise runner.ensemble.EnsembleError("an invented refusal of the ensemble")

    other = world_with_an_e8_run(tmp_path / "other")
    monkeypatch.setattr(runner.ensemble, "run_ensemble", refuse)
    summary = run(other)
    assert summary["computed"] is False and summary["not_computed_because"] == "check_failed"
    receipt = json.loads((other["output_dir"] / RECEIPT_NAME).read_text(encoding="ascii"))
    assert receipt["result"]["not_computed_because"]["stage"] == "ensemble_cells"
    assert receipt["result"]["not_computed_because"]["error"] == "EnsembleError"
    monkeypatch.undo()
    again = run(other, replace_reason="The invented refusal was removed.")
    assert again["computed"] is True
    receipt = json.loads((other["output_dir"] / RECEIPT_NAME).read_text(encoding="ascii"))
    assert receipt["supersedes"]["result_same"] is False and receipt["supersedes"]["units_same"] is None


def test_the_default_cell_must_be_the_rows_of_the_registered_e8_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = world_with_an_e8_run(tmp_path)
    real = runner.e8_builder.rows_sha256
    calls = {"count": 0}

    def other_digest(rows: Any) -> str:
        # The first call reads the rows back from the E8 overlay (an input check); the second is the comparison.
        calls["count"] += 1
        return real(rows) if calls["count"] == 1 else "0" * 64

    monkeypatch.setattr(runner.e8_builder, "rows_sha256", other_digest)
    summary = run(world)
    assert summary["computed"] is False and summary["not_computed_because"] == "default_cell_differs_from_the_e8_rows"
    receipt = json.loads((world["output_dir"] / RECEIPT_NAME).read_text(encoding="ascii"))
    assert receipt["result"]["not_computed_because"]["stage"] == "default_cell_against_the_e8_rows"
    assert receipt["result"]["summary"] is None and receipt["access_runs"] is None


def test_the_levels_that_cannot_be_run_are_worded_from_what_task_e5_delivered() -> None:
    grid = runner.ensemble.load_grid(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json", DOCS / "RECEIPTS.jsonl")
    candidate = runner.levels_not_run(grid, {"shelter_service": {"computed": True, "usable_by_task_e8": False}})
    assert [(item.axis, item.level) for item in candidate] == [
        ("facilities", "corroborated"), ("facilities", "all_listed"), ("population_vintage", "rescaled_2024")]
    assert "candidate walking context" in candidate[0].reason and "E5-OP5" in candidate[0].reason
    assert "subset of the shelters" in candidate[0].reason and "subset of the shelters" not in candidate[1].reason
    assert "holds no shelter table" in runner.levels_not_run(grid, {})[0].reason
    usable = runner.levels_not_run(grid, {"shelter_service": {"computed": True, "usable_by_task_e8": True}})
    assert "does not run a pitch-level facility set yet" in usable[0].reason, "a usable table alone does not run the level"
    assert "do not nest" in candidate[2].reason and "no 2024 total" in candidate[2].reason
    assert all("not approximated" in item.reason for item in candidate)
    assert len(runner.run_keys(grid)) == 9 and {key[2:] for key in runner.run_keys(grid)} == {("public", "worldpop_2020")}


def test_the_command_line_refuses_case_o1_and_wants_replace_and_reason_together(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    # Case O1 of the Mae Sai frame: refused from what the registered E1 and E5 receipts bind; no input of a unit is read.
    assert runner.main(["--case", "O1", "--frame", "mae_sai", "--external-data", str(tmp_path)]) == runner.EXIT_REFUSED
    refusal = capsys.readouterr().err
    assert refusal.startswith("REFUSED: case O1 cannot be run") and "E1-OP2" in refusal
    assert runner.main(["--case", "O1", "--frame", "mae_sai", "--external-data", str(tmp_path), "--check-inputs"]) == runner.EXIT_REFUSED
    assert not any(tmp_path.iterdir())
    for arguments in (["--replace"], ["--reason", "why"], ["--replace", "--reason", "  "]):
        with pytest.raises(SystemExit):
            runner.main(["--case", "SE1", "--frame", "mae_sai", "--external-data", str(tmp_path), *arguments])
    monkeypatch.delenv(runner.EXTERNAL_DATA_VARIABLE, raising=False)
    with pytest.raises(SystemExit):
        runner.main(["--case", "SE1", "--frame", "mae_sai"])
    with pytest.raises(SystemExit):
        runner.main(["--case", "SE1", "--frame", "another_frame", "--external-data", str(tmp_path)])
