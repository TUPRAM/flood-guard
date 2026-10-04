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

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
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
    assert {point["id"] for point in receipt["open_points"]} == {f"E10-OP{number}" for number in range(1, 10)}

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
    assert receipt["supersedes"]["outputs_of_the_superseded_run"] == {first["files"][0]: hashlib.sha256(old_results).hexdigest()}
    history = receipt["run_history"]
    assert len(history) == 1 and history[0]["receipt_sha256"] == first["receipt_sha256"]
    assert history[0]["result_same_as_the_run_that_replaced_it"] is True
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
