"""The committed runs of the abstention diagnosis (plan task A1) and the page that explains them.

Plan row 8.1 A1 accepts the task when "every number [is] traced; guard test green". These tests read the
committed figures files, receipts, scripts and the write-up. They open no file of the external data
workspace, except the last test, which runs only when ``FLOODGUARD_EXTERNAL_DATA`` is set.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
from typing import Any

import pytest

from floodguard import abstention_diagnosis as diagnosis
from floodguard import diagnosis_run
from floodguard.wording_lint import find_violations, json_strings, load_rules, python_strings

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "diagnostics"
PAGE = ROOT / "docs" / "proposal_execution" / "automated_track" / "WHY_THRESHOLD_ONLY_FAILED.md"
README = ROOT / "outputs" / "planning_v1" / "README.md"
RADAR_TABLE = ROOT / "outputs" / "planning_v1" / "radar_o1_mae_sai_v1.json"
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
FIGURES = ("bvf_unimodal_gaussian", "m2_windows_mae_sai", "m2_windows_geoid", "sentinel1_pass_gap", "pilot_grid_vs_envelope",
           "darkening_auc_vs_envelope", "terrain_auc_vs_envelope")
ENVELOPE_FIGURES = ("pilot_grid_vs_envelope", "darkening_auc_vs_envelope", "terrain_auc_vs_envelope")
NO_EXTERNAL_DATA = ("bvf_unimodal_gaussian", "sentinel1_pass_gap")
CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
HEADER_SECTIONS = ("Reads", "Computes", "Does not show", "Writes", "Run")
WINDOWS = (1, 3, 5, 9, 15, 25)
ALL, FLAT = "all_cells", "slope_under_5_degrees"
RECORD, SENSITIVITY = "gcp_polynomial", "annotation_grid_with_cell_height"
JRC, WORLDCOVER, NOTHING = "jrc_surface_water", "worldcover_class_80", "nothing_left_out"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _script(name: str) -> Any:
    """Load a diagnosis script as a module, without running it."""

    spec = importlib.util.spec_from_file_location(f"diagnostics_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _figures(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "outputs" / "a1_diagnosis" / f"{name}.json").read_text(encoding="ascii"))


def _receipt(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "outputs" / "planning_v1" / f"a1_diagnosis_{name}.json").read_text(encoding="ascii"))


# --- The scripts -----------------------------------------------------------------------------------------


def test_there_is_one_script_for_each_figure_and_nothing_else() -> None:
    assert sorted(path.stem for path in SCRIPTS.glob("*.py")) == sorted(FIGURES)
    assert sorted(path.name for path in SCRIPTS.iterdir() if path.suffix != ".py" and path.name != "__pycache__") == ["README.md"]
    assert sorted(path.stem for path in (ROOT / "outputs" / "a1_diagnosis").glob("*.json")) == sorted(FIGURES)
    assert sorted(path.stem for path in (ROOT / "outputs" / "planning_v1").glob("a1_diagnosis_*.json")) == sorted(
        f"a1_diagnosis_{name}" for name in FIGURES)


@pytest.mark.parametrize("name", FIGURES)
def test_each_script_has_a_readme_header_that_says_what_it_reads_computes_and_does_not_show(name: str) -> None:
    source = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
    header = ast.get_docstring(ast.parse(source))
    assert header is not None and "README\n======" in header
    positions = [header.index(f"\n{section}\n") for section in HEADER_SECTIONS]
    assert positions == sorted(positions), "the header sections are in the order Reads, Computes, Does not show, Writes, Run"
    module = _script(name)
    spec = module.SPEC
    assert spec.figure_id == name and spec.script == f"scripts/diagnostics/{name}.py"
    assert len(spec.does_not_show) >= 3 and spec.plan_statement.strip() and spec.computes.strip()
    assert f"outputs/a1_diagnosis/{name}.json" in header and f"outputs/planning_v1/a1_diagnosis_{name}.json" in header
    # No machine path: the external data root is an argument or the environment variable.
    assert not re.search(r"[A-Za-z]:[\\/]|/Users/|/home/", source)
    assert (spec.label == diagnosis_run.ENVELOPE_LABEL) == (name in ENVELOPE_FIGURES)
    if name in ENVELOPE_FIGURES:
        flat = " ".join(header.split())
        assert "vs a season envelope, not an event map" in flat and "CC BY-SA 4.0" in flat and CREDIT in flat


def test_the_scripts_folder_readme_lists_every_script() -> None:
    text = (SCRIPTS / "README.md").read_text(encoding="utf-8")
    for name in FIGURES:
        assert f"`{name}.py`" in text
    assert "--no-extra diagnostics" in text and "FLOODGUARD_EXTERNAL_DATA" in text
    flat = " ".join(text.split())
    assert "Without the root the run is refused" in flat and "the code on disk is not the code the receipt names" in flat


# --- The figures files and the receipts ------------------------------------------------------------------


@pytest.mark.parametrize("name", FIGURES)
def test_each_figure_is_bound_by_its_receipt_and_the_receipt_by_the_register(name: str) -> None:
    figures_path = ROOT / "outputs" / "a1_diagnosis" / f"{name}.json"
    receipt_path = ROOT / "outputs" / "planning_v1" / f"a1_diagnosis_{name}.json"
    figures, receipt = _figures(name), _receipt(name)
    for path in (figures_path, receipt_path):
        raw = path.read_bytes()
        assert raw.endswith(b"\n") and b"\r" not in raw
    assert receipt["outputs"]["figures"] == {"path": f"outputs/a1_diagnosis/{name}.json", "sha256": _sha256(figures_path),
                                             "bytes": figures_path.stat().st_size}
    register = json.loads((ROOT / "outputs" / "planning_v1" / "run_register" / f"a1_diagnosis_{name}.json").read_text(encoding="ascii"))
    assert register == {"path": f"outputs/planning_v1/a1_diagnosis_{name}.json", "sha256": _sha256(receipt_path)}
    protocols = {f"planning_protocol_{version}": _sha256(ROOT / "docs" / "proposal_execution" / f"planning_protocol_{version}.json")
                 for version in ("v1a", "v1b")}
    for document in (figures, receipt):
        assert document["figure_id"] == name and document["generated_at_utc"] == receipt["generated_at_utc"]
        assert document["source_timestamp"].strip() and document["confidence_class"] == "low" and document["confidence_basis"].strip()
        assert document["assumptions"] and all(line.strip() for line in document["assumptions"])
        assert document["official_warning"] is False and document["operational_status"] == "non_operational"
        assert document["protocol_sha256"] == protocols
    assert figures["schema_version"] == diagnosis_run.FIGURES_SCHEMA and figures["status"] == "diagnosis_figures"
    assert figures["receipt_file"] == f"outputs/planning_v1/a1_diagnosis_{name}.json"
    assert figures["script"] == f"scripts/diagnostics/{name}.py" and figures["does_not_show"] and figures["limits"]
    assert receipt["schema_version"] == diagnosis_run.RECEIPT_SCHEMA and receipt["status"] == "run_receipt"
    assert receipt["protocol_state"] == {"v1a": "in_force", "v1b": "in_force"}
    assert receipt["timestamps"]["run_started_at_utc"] <= receipt["timestamps"]["run_finished_at_utc"] == receipt["generated_at_utc"]
    assert re.search(r"[0-9a-f]{64}", json.dumps(receipt["inputs"])), "inputs are named by SHA-256"
    assert ("<external_data_workspace>" in json.dumps(receipt["inputs"])) == (name not in NO_EXTERNAL_DATA)
    assert not re.search(r"[A-Za-z]:[\\/]{1,2}Users", json.dumps(receipt) + json.dumps(figures)), "no machine path"
    # A receipt can be read alone: it carries the label, the licence block and the credits of its figures file.
    assert receipt["measured_against"] == figures["measured_against"] and receipt["licence"] == figures["licence"]
    assert receipt["attributions"] == figures["attributions"]
    # Every run is reported: a superseding run names the run it replaced, by SHA-256, with the reason and its times.
    history = receipt["run_history"]["earlier_runs"]
    assert receipt["run_kind"] == "superseding_run", "every figure was run again after the review"
    supersedes = receipt["supersedes"]
    assert supersedes["reason"].startswith("Review of 4 October 2026 (UTC):") and isinstance(supersedes["figures_same"], bool)
    assert history and history[-1]["receipt_sha256"] == supersedes["receipt_sha256"]
    assert history[-1]["figures_sha256"] == supersedes["figures_sha256"]
    assert history[-1]["generated_at_utc"] == supersedes["generated_at_utc"] < receipt["generated_at_utc"]
    assert history[-1]["run_started_at_utc"] <= history[-1]["run_finished_at_utc"] == history[-1]["generated_at_utc"]
    assert [run["generated_at_utc"] for run in history] == sorted(run["generated_at_utc"] for run in history)
    assert len(supersedes["copies_kept"]) == 2 and all(label.startswith("<external_data_workspace>/") for label in supersedes["copies_kept"])
    for point in figures["open_points"]:
        assert point == {"id": point["id"], **diagnosis_run.OPEN_POINTS[point["id"]]}
    assert receipt["open_points"] == figures["open_points"]
    assert {"FPPS", "A-E class"} <= set(figures["not_computed"])


@pytest.mark.parametrize("name", FIGURES)
def test_the_code_on_disk_is_the_code_each_receipt_names(name: str) -> None:
    """A receipt traces its figure only while the script and the shared modules are the ones it names by SHA-256.

    A change to one of them after a run fails here, also where the external data workspace is absent: the
    figure then needs a superseding run.
    """

    receipt = _receipt(name)
    script = f"scripts/diagnostics/{name}.py"
    assert receipt["script"] == {"path": script, "sha256": _sha256(ROOT / script)}, "the script changed after the run"
    named = receipt["implementation"]["files_sha256"]
    assert set(named) == {script, *diagnosis_run.MODULES}
    for path, sha256 in named.items():
        assert sha256 == _sha256(ROOT / path), f"{path} changed after the run of {name}"
    assert diagnosis_run.code_checks(_script(name).SPEC, receipt, ROOT) == {
        "script_is_the_one_the_receipt_names": True, "code_files_are_the_ones_the_receipt_names": True}
    # The library versions the run had loaded are recorded, so that another environment can be told from another input.
    software = receipt["implementation"]["software"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", software["python"]) and re.fullmatch(r"\d+\.\d+\.\d+", software["numpy"])
    if name in ("darkening_auc_vs_envelope", "terrain_auc_vs_envelope"):
        assert {"rasterio", "gdal", "pyproj", "proj", "shapely", "geos", "pyogrio"} <= set(software)
    assert re.fullmatch(r"[0-9a-f]{40}", receipt["implementation"]["base_commit"])


def _keys(value: Any) -> set[str]:
    """Every key of a JSON document, at any depth, in lower case."""

    if isinstance(value, dict):
        return {str(key).lower() for key in value} | {key for child in value.values() for key in _keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _keys(child)}
    return set()


def test_no_figures_file_or_receipt_holds_a_score_a_class_or_a_value_for_a_tambon() -> None:
    for name in FIGURES:
        for document in (_figures(name), _receipt(name)):
            text = json.dumps(document)
            keys = _keys(document)
            assert not [key for key in keys if any(word in key for word in ("fpps", "action_class", "binding_class", "flood_likelihood",
                                                                             "candidate", "subdistrict_id", "unit_id"))], name
            # A tambon is named only as a unit of the Thai side of AOI-01, never beside a value.
            domain = json.dumps(document.get("figures", {}).get("domain", {}).get("thai_side_of_aoi_01", {}).get("units_meeting_the_frame", []))
            assert len(re.findall(r"TH\d{6}", text)) == len(re.findall(r"TH\d{6}", domain)), name


@pytest.mark.parametrize("name", ENVELOPE_FIGURES)
def test_a_figure_against_product_4009_carries_its_licence_credit_change_notice_and_label(name: str) -> None:
    figures, receipt = _figures(name), _receipt(name)
    record = None
    # The figures file and the receipt each carry the label and the licence block, so that either can be shared alone.
    for document in (figures, receipt):
        assert document["measured_against"] == "vs a season envelope, not an event map"
        licence = document["licence"]
        assert licence["name"] == "CC BY-SA 4.0" and licence["credit"] == CREDIT
        assert licence["change_notice"].startswith("Changed by FloodGuard: clipped to AOI-01")
        assert licence["change_notice"].endswith(f"Source: {CREDIT}, CC BY-SA 4.0.")
        assert "Field_Validation=0" in licence["standard_sentence"] and "FloodGuard did not validate it." in licence["standard_sentence"]
        assert "never an event map" in licence["used_as"] and "never a reference" in licence["used_as"]
        record = ROOT / licence["rights_record"]["path"]
        assert licence["rights_record"]["sha256"] == _sha256(record)
        assert f"{CREDIT}, CC BY-SA 4.0" in document["attributions"]
    assert record is not None
    # The layer read is the layer the confirmed record names, at the public level; the local-level layer is not read.
    grant = receipt["rights"]["grant"]
    assert grant["rights_level"] == "public" and grant["record_status"] == "confirmed"
    assert grant["layer"] == receipt["inputs"]["product_4009_archive"]["layer"] == "CHIANGRAI_20240801_20241012_AccumulatedFlood"
    assert receipt["inputs"]["product_4009_archive"]["sha256"] == json.loads(record.read_text(encoding="utf-8"))["archive"]["sha256"]
    assert receipt["parameters"]["footprint_layer_read"] is False
    assert "AnalysisExtent" not in json.dumps(receipt) and "20241022" not in json.dumps(receipt["inputs"])
    assert any("comparison with a season envelope, not a validation" in line for line in figures["assumptions"])
    assert any(point["id"] == "A1-OP6" for point in figures["open_points"])


@pytest.mark.parametrize("name", [name for name in FIGURES if name not in ENVELOPE_FIGURES])
def test_a_figure_that_reads_no_flood_layer_carries_no_envelope_label(name: str) -> None:
    figures, receipt = _figures(name), _receipt(name)
    assert figures["measured_against"] is None and figures["licence"] is None
    assert receipt["measured_against"] is None and receipt["licence"] is None
    assert "4009" not in json.dumps(receipt["inputs"])


# --- What the runs measured, against what the plan states -------------------------------------------------


def test_one_normal_population_stays_below_the_gate_in_theory_and_through_the_kernel() -> None:
    document = _figures("bvf_unimodal_gaussian")
    figures = document["figures"]
    assert figures["gate"] == 0.72
    assert figures["theory_normal_population_split_at_its_mean"] == round(diagnosis.GAUSSIAN_BVF_THEORY, 6) == 0.63662
    assert figures["theory_same_population_clipped_at_1st_and_99th_percentile"] == round(diagnosis.clipped_gaussian_bvf(), 6)
    assert all(figures["below_the_gate"].values())
    simulated = figures["simulated_windows_of_pure_noise_through_the_m2_kernel"]
    assert sum(row["windows"] for row in simulated) == 600 and all(row["windows_passing_the_gate"] == 0 for row in simulated)
    assert figures["largest_fraction_of_any_simulated_window"] == max(row["between_variance_fraction_max"] for row in simulated) < 0.72
    plan = document["plan_figure"]
    assert plan["plan_value"] == 0.637 == plan["measured"] and plan["reproduced"] is True
    # A fresh, smaller simulation gives the same picture (the committed one is seeded; this one is not compared exactly).
    fresh = diagnosis.simulate_unimodal((16384,), repeats=20, seed=99)[0]
    assert fresh["windows_passing_the_gate"] == 0
    assert fresh["between_variance_fraction_mean"] == pytest.approx(simulated[1]["between_variance_fraction_mean"], abs=0.005)
    shares = [row["second_population_share"] for row in figures["two_populations_through_the_m2_kernel"]]
    needed = [row["first_separation_passing_the_gate"] for row in figures["two_populations_through_the_m2_kernel"]]
    assert shares == [0.5, 0.3, 0.2, 0.1] and needed == sorted(needed) and needed[0] > 2.0


def test_the_gate_is_not_said_to_decline_every_single_population() -> None:
    """The result holds for a normal population. One flat-topped population passes, and the figure says so."""

    document = _figures("bvf_unimodal_gaussian")
    flat_topped = document["figures"]["one_flat_topped_population"]
    assert flat_topped["theory_uniform_population_split_at_its_mean"] == diagnosis.UNIFORM_BVF_THEORY == 0.75 > document["figures"]["gate"]
    assert flat_topped["above_the_gate_in_theory"] is True
    rows = flat_topped["simulated_windows_through_the_m2_kernel"]
    assert flat_topped["simulated_windows"] == sum(row["windows"] for row in rows) == 600
    assert flat_topped["simulated_windows_the_kernel_accepted"] == sum(row["windows_the_kernel_accepts"] for row in rows) == 600
    assert all(row["between_variance_fraction_min"] >= 0.72 and row["reason_counts"] == {"accepted": row["windows"]} for row in rows)
    assert any("one flat-topped population passes it" in line for line in document["does_not_show"])
    assert any("holds for a normal population" in line for line in document["limits"])
    header = " ".join((ast.get_docstring(ast.parse((SCRIPTS / "bvf_unimodal_gaussian.py").read_text(encoding="utf-8"))) or "").split())
    assert "whatever it is" not in header and "is not passed by one normal (bell-shaped) population" in header


def test_the_one_population_figure_is_recomputed_without_external_data() -> None:
    module = _script("bvf_unimodal_gaussian")
    summary = diagnosis_run.verify(module.SPEC, module.make_compute(ROOT, None), root=ROOT)
    assert summary["verified"] is True, summary


def test_the_window_figures_reproduce_the_committed_summaries() -> None:
    mae_sai = _figures("m2_windows_mae_sai")
    assert mae_sai["figures"]["windows"] == mae_sai["figures"]["windows_declined"] == 81
    assert mae_sai["figures"]["windows_the_kernel_accepted"] == 0 and mae_sai["figures"]["same_as_the_committed_summary"] is True
    assert mae_sai["figures"]["windows_whose_only_failed_test_was_the_gate"] == 81
    summary = json.loads((ROOT / "outputs" / "sar_m2_abstention_diagnostic_v1.json").read_text(encoding="utf-8"))
    fractions = mae_sai["figures"]["between_variance_fraction"]
    assert fractions["between_variance_fraction_min"] == summary["window_summary"]["between_variance_fraction_min"]
    assert fractions["between_variance_fraction_max"] == summary["window_summary"]["between_variance_fraction_max"]
    assert fractions["between_variance_fraction_max"] < fractions["gate"] == 0.72
    assert _receipt("m2_windows_mae_sai")["inputs"]["m2_run_receipt"]["sha256"] == summary["source_receipt_sha256"]
    assert mae_sai["plan_figure"]["reproduced"] is True

    geoid = _figures("m2_windows_geoid")
    assert (geoid["figures"]["windows_the_kernel_accepted"], geoid["figures"]["windows"], geoid["figures"]["tiles"]) == (0, 1421, 29)
    assert all(geoid["figures"]["same_as_the_committed_summary"].values()) and geoid["plan_figure"]["reproduced"] is True
    detector = json.loads((ROOT / "outputs" / "geoid_s1grd_sigma0_benchmark_summary_v1.json").read_text(encoding="utf-8"))["detector"]
    assert geoid["figures"]["between_variance_fraction"]["between_variance_fraction_max"] == detector["between_variance_fraction_max"] < 0.72
    assets = _receipt("m2_windows_geoid")["inputs"]["geoid_flood_sample_assets"]
    assert assets["files_checked_against_the_published_sums"] == 116 and "not opened" in assets["inventory_note"]


def test_the_pass_gap_is_recomputed_from_the_committed_snapshot() -> None:
    module = _script("sentinel1_pass_gap")
    summary = diagnosis_run.verify(module.SPEC, module.make_compute(ROOT, None), root=ROOT)
    assert summary["verified"] is True, (
        "the pass-gap figure is not the one its receipt binds; if docs/demo/replay_numbers.md was written again, the figure needs "
        f"a superseding run: {summary}")
    figures = _figures("sentinel1_pass_gap")
    assert figures["figures"]["pass_count"] == 4 and figures["figures"]["no_pass_strictly_inside_the_interval"] is True
    assert figures["figures"]["longest_gap"]["days"] == 9.49 and figures["plan_figure"]["reproduced"] is True
    assert figures["plan_figure"]["measured"]["after_utc"] == "2024-09-06T11:31" and figures["plan_figure"]["measured"]["before_utc"] == "2024-09-15T23:16"
    assert [entry["relative_orbit"] for entry in figures["figures"]["passes"]] == [135, 172, 135, 172]
    assert figures["figures"]["platforms_in_the_snapshot"] == ["S1A"], "the snapshot holds Sentinel-1 only"


def test_the_replay_keyframes_are_read_from_a_file_the_receipt_binds() -> None:
    """The hours to the two keyframes come from docs/demo/replay_numbers.md, which is an input with its SHA-256."""

    module = _script("sentinel1_pass_gap")
    assert not hasattr(module, "REPLAY_KEYFRAMES"), "no keyframe time is typed into the script"
    assert not re.search(r"2024-09-1[02]T", (SCRIPTS / "sentinel1_pass_gap.py").read_text(encoding="utf-8"))
    replay_path = ROOT / "docs" / "demo" / "replay_numbers.md"
    replay = replay_path.read_text(encoding="utf-8")
    receipt = _receipt("sentinel1_pass_gap")
    assert receipt["inputs"]["replay_numbers"]["path"] == "docs/demo/replay_numbers.md"
    assert receipt["inputs"]["replay_numbers"]["sha256"] == _sha256(replay_path)
    assert receipt["inputs"]["replay_numbers"]["rows_read"] == sorted(module.REPLAY_KEYFRAME_KEYS.values()) == ["stage.onset_knot", "stage.peak"]
    context = _figures("sentinel1_pass_gap")["figures"]["replay_keyframes_for_context"]
    assert "illustrative" in context["what"] and "not observations" in context["what"] and context["read_at_run_time"] is True
    for name, key in module.REPLAY_KEYFRAME_KEYS.items():
        stated = diagnosis.replay_keyframe(replay, key)
        assert {field: context[name][field] for field in stated} == stated
        assert context[name]["inside_the_gap"] is True
        thailand = diagnosis.parse_utc(stated["utc"]) + diagnosis.THAILAND_UTC_OFFSET
        assert f"{thailand.day} Sep {thailand:%H:%M} ICT" == stated["in_thailand"]


def test_the_other_radar_acquisitions_in_the_gap_are_the_ones_committed_files_name() -> None:
    """The pass list is Sentinel-1 only; the limit that names other radar satellites is bound to its two sources."""

    document = _figures("sentinel1_pass_gap")
    note = document["figures"]["other_radar_acquisitions_dated_inside_the_gap"]
    assert note in document["limits"] and "None of their data is cleared for this lane and none was read." in note
    assert any("RADARSAT-2 and ALOS-2" in line for line in document["does_not_show"])
    row = next(line for line in (ROOT / "docs" / "demo" / "replay_numbers.md").read_text(encoding="utf-8").splitlines()
               if line.startswith("| `cal.gistda` |"))
    assert "RADARSAT-2" in row and "10 Sep 18:15" in row and "RADARSAT-2 analysis by GISTDA of 10 September 2024" in note
    v1a = json.loads((ROOT / "docs" / "proposal_execution" / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
    case = next(case for case in v1a["case_portfolio"]["cases"] if case["id"] == "O4")
    inputs = " | ".join(case["flood_inputs"])
    assert "ALOS-2 15 Sep 2024" in inputs and "ALOS-2 14 Sep 2024" in inputs and "permission" in case["condition"]
    assert "ALOS-2 acquisitions of 14 and 15 September 2024 (planning protocol v1a, case O4" in note
    gap = document["figures"]["interval"]
    assert gap["after_utc"] < "2024-09-10" and "2024-09-15T23" < gap["before_utc"], "10 and 14 September lie inside the gap; 15 September is a date only"
    assert "dated inside the gap" in note and "no time of day" in note


def test_the_envelope_figures_agree_with_each_other_and_with_task_e1() -> None:
    pilot = _figures("pilot_grid_vs_envelope")["figures"]
    assert pilot["envelope_inside_aoi_01_km2"] == 15.337, "the E1 acceptance figure: 15.34 km2 in AOI-01"
    e1 = json.loads((ROOT / "outputs" / "planning_v1" / "e1_flood_inputs_mae_sai.json").read_text(encoding="ascii"))
    assert round(e1["acceptance"]["layers"]["SE1"]["clip_km2_epsg32647"], 3) == pilot["envelope_inside_aoi_01_km2"]
    inside, outside = pilot["envelope_inside_aoi_01_and_inside_the_pilot_grid_km2"], pilot["envelope_inside_aoi_01_and_outside_the_pilot_grid_km2"]
    assert inside + outside == pytest.approx(pilot["envelope_inside_aoi_01_km2"], abs=0.002)
    assert pilot["share_of_the_envelope_in_aoi_01_outside_the_pilot_grid"] == pytest.approx(outside / (inside + outside), abs=1e-3)
    assert round(pilot["share_of_the_envelope_in_aoi_01_outside_the_pilot_grid"] * 100) == 80
    assert _figures("pilot_grid_vs_envelope")["plan_figure"]["reproduced"] is True

    darkening, terrain = _figures("darkening_auc_vs_envelope"), _figures("terrain_auc_vs_envelope")
    assert darkening["figures"]["domain"] == terrain["figures"]["domain"], "both figures are measured on the same cells"
    domain = darkening["figures"]["domain"]
    assert domain["envelope_km2_by_cell_count"] == pytest.approx(pilot["envelope_inside_aoi_01_km2"], abs=0.05)
    assert domain["envelope_cells_outside_the_thai_side"] == 0 and domain["thai_side_of_aoi_01"]["all_units_are_in_the_reporting_frame_of_protocol_v1a"]
    assert domain["slope_in_the_domain"]["cells_with_no_slope_value"] == 0 and domain["slope_in_the_domain"]["limit_degrees"] == 5.0
    assert set(domain["sets_of_cells"]) == {ALL, FLAT}
    for row in darkening["figures"]["readings"] + darkening["figures"]["readings_by_smoothing_window"] + terrain["figures"]["readings"]:
        counts = domain["by_permanent_water_reading"][row["permanent_water"]]
        counts = counts if row["cells"] == ALL else counts[FLAT]
        assert row["cells_inside_the_layer"] == counts["envelope_cells"] and row["cells_left_out_for_no_value"] == 0
        assert row["cells_inside_the_layer"] + row["cells_outside_the_layer"] == counts["cells"]
        assert 0.0 < row["auc"] < 1.0
    for water in (JRC, WORLDCOVER, NOTHING):
        counts = domain["by_permanent_water_reading"][water]
        assert counts[FLAT]["cells"] < counts["cells"] and counts[FLAT]["envelope_cells"] < counts["envelope_cells"]


def _darkening_rows() -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[tuple[str, str, int], dict[str, Any]]]:
    figures = _figures("darkening_auc_vs_envelope")["figures"]
    readings = {(row["geocoding"], row["cells"], row["permanent_water"]): row for row in figures["readings"]}
    by_window = {(row["geocoding"], row["cells"], row["window_cells"]): row for row in figures["readings_by_smoothing_window"]}
    return readings, by_window


def test_the_darkening_figure_reproduces_the_plan_and_is_given_under_both_geocodings() -> None:
    document = _figures("darkening_auc_vs_envelope")
    readings = document["figures"]["readings"]
    assert len(readings) == 12 and {row["geocoding"] for row in readings} == {RECORD, SENSITIVITY}
    assert {row["permanent_water"] for row in readings} == {JRC, WORLDCOVER, NOTHING} and {row["cells"] for row in readings} == {ALL, FLAT}
    assert {row["window_cells"] for row in readings} == {5}
    exploratory = document["figures"]["reading_that_follows_the_exploratory_definition"]
    assert exploratory == {"geocoding": RECORD, "permanent_water": JRC, "cells": ALL, "window_cells": 5, "auc": 0.421149}
    assert round(exploratory["auc"], 3) == 0.421 == document["plan_figure"]["plan_value"] and document["plan_figure"]["reproduced"] is True
    # The values of the runs before the review are in this run, unchanged.
    by_key, _by_window = _darkening_rows()
    assert by_key[(RECORD, ALL, JRC)]["auc"] == 0.421149 and by_key[(SENSITIVITY, ALL, JRC)]["auc"] == 0.377043
    for row in readings:
        assert row["auc_of_brightening"] == pytest.approx(1 - row["auc"], abs=1e-6)
        assert row["median_inside_the_layer"] < row["median_outside_the_layer"] < 0  # Brighter after, and more so inside.
    # No reading is named the figure of record, and the open points say why.
    assert "figure_of_record" not in json.dumps(document)
    assert [point["id"] for point in document["open_points"]] == ["A1-OP2", "A1-OP3", "A1-OP4", "A1-OP5", "A1-OP6", "A1-OP10"]
    receipt = _receipt("darkening_auc_vs_envelope")
    for geocoding, relative in ((RECORD, "outputs/planning_v1/radar_o1_mae_sai_v1_receipt.json"),
                                (SENSITIVITY, "outputs/planning_v1/radar_o1_mae_sai_v1_height_aware_sensitivity_receipt.json")):
        radar = receipt["inputs"]["radar"][geocoding]
        assert radar["receipt"] == {"path": relative, "sha256": _sha256(ROOT / relative)}
        bound = {entry["path"]: entry["sha256"] for entry in json.loads((ROOT / relative).read_text(encoding="ascii"))["outputs"]["rasters"]}
        for key in ("sigma0_pre_20240903", "sigma0_post_20240915"):
            assert bound[radar[key]["path"]] == radar[key]["sha256"], "the radar raster is the one its registered receipt binds"
    # The candidates of tasks A2 and A4 are not read (guardrail GR4): only the sigma0 rasters are.
    assert not re.search(r"_candidate\.tif|_score\.tif|_reason\.tif", json.dumps(receipt["inputs"]))
    # The time of the peak is not stated as a fact: the replay's keyframe is named as what it is.
    text = " ".join(document["assumptions"] + document["limits"])
    assert "after the flood peak" not in text and "several days after the keyframe" in text and "illustrative" in text
    assert "no gauge record gives the time of the peak" in text


def test_the_darkening_figure_is_given_for_six_windows_and_no_window_is_the_window_of_record() -> None:
    document = _figures("darkening_auc_vs_envelope")
    figures = document["figures"]
    readings, by_window = _darkening_rows()
    assert figures["windows_cells"] == list(WINDOWS)
    assert set(by_window) == {(geocoding, cells, window) for geocoding in (RECORD, SENSITIVITY) for cells in (ALL, FLAT) for window in WINDOWS}
    assert {row["permanent_water"] for row in figures["readings_by_smoothing_window"]} == {JRC}
    for geocoding in (RECORD, SENSITIVITY):
        for cells in (ALL, FLAT):
            values = [by_window[(geocoding, cells, window)]["auc"] for window in WINDOWS]
            assert values == sorted(values, reverse=True) and len(set(values)) == len(values), "the value falls at every step as the window grows"
            assert figures["the_value_falls_at_every_step_as_the_window_grows"][geocoding][cells] is True
            # The rows of the 5 by 5 window repeat the readings with JRC water left out.
            assert by_window[(geocoding, cells, 5)] == readings[(geocoding, cells, JRC)]
    everything = [row["auc"] for row in figures["readings"] + figures["readings_by_smoothing_window"]]
    assert figures["smallest_and_largest_auc_over_the_readings"] == [min(everything), max(everything)] == [0.254389, 0.477731]
    assert figures["every_reading_is_below_one_half"] is True
    # 0.421 is the value of one window: with no smoothing it is nearer one half, and with a wide window further from it.
    assert by_window[(RECORD, ALL, 1)]["auc"] > 0.46 and by_window[(RECORD, ALL, 25)]["auc"] < 0.30
    receipt = _receipt("darkening_auc_vs_envelope")
    assert receipt["parameters"]["boxcar_windows_cells"] == list(WINDOWS) and receipt["parameters"]["boxcar_cells"] == 5
    assert receipt["parameters"]["sets_of_cells"] == [ALL, FLAT] and receipt["parameters"]["flat_slope_limit_degrees"] == 5.0
    assert any("No window is the window of record" in line for line in document["limits"])
    assert "no window is named the window of record" in diagnosis_run.OPEN_POINTS["A1-OP2"]["what_was_done"]


def test_the_terrain_figure_says_what_was_seen_before_and_names_no_figure_of_record() -> None:
    document = _figures("terrain_auc_vs_envelope")
    assert document["plan_figure"]["plan_value"] is None and document["plan_figure"]["reproduced"] is None
    # The exploratory script had computed the same two features against the same layer: this is the first computation
    # from cleared files and the first recorded value, and the file does not call it the first computation.
    note = document["plan_figure"]["note"]
    assert "first computation from cleared files and the first recorded value" in note
    assert "not the first time the figure was seen" in note and "were taken from that script" in note
    assert "this is the first computation of the figure" not in json.dumps(document)
    point = next(point for point in document["open_points"] if point["id"] == "A1-OP1")
    assert "printed both values on the line that gave 0.421" in point["what_was_done"]
    readings = document["figures"]["readings"]
    assert len(readings) == 12 and {row["feature"] for row in readings} == {"low_elevation", "low_slope"}
    assert {row["cells"] for row in readings} == {ALL, FLAT} and {row["permanent_water"] for row in readings} == {JRC, WORLDCOVER, NOTHING}
    by_key = {(row["feature"], row["cells"], row["permanent_water"]): row for row in readings}
    # The values of the runs before the review are in this run, unchanged.
    assert by_key[("low_elevation", ALL, JRC)]["auc"] == 0.616479 and by_key[("low_slope", ALL, JRC)]["auc"] == 0.67974
    for water in (JRC, WORLDCOVER, NOTHING):
        assert 0.6 < by_key[("low_elevation", ALL, water)]["auc"] < by_key[("low_slope", ALL, water)]["auc"] < 0.7
        # On the cells under 5 degrees the hills are left out: low elevation falls below one half and low slope nears it.
        assert by_key[("low_elevation", FLAT, water)]["auc"] < 0.5 < by_key[("low_slope", FLAT, water)]["auc"] < 0.56
        row = by_key[("low_elevation", FLAT, water)]
        assert row["median_elevation_m_inside_the_layer"] > row["median_elevation_m_outside_the_layer"]
    slope = document["figures"]["domain"]["slope_in_the_domain"]
    assert slope["share_of_envelope_cells_under_the_limit"] > 0.97 and slope["share_of_other_cells_under_the_limit"] < 0.69
    assert [point["id"] for point in document["open_points"]] == ["A1-OP1", "A1-OP4", "A1-OP6", "A1-OP10"]
    assert "HAND (height above the nearest drainage)" in document["not_computed"]
    assert "none is the figure of record" in document["figures"]["not_named_the_terrain_figure_of_the_plan"]
    assert any("low elevation can separate plain from hill as much as wet from dry" in line for line in document["limits"])
    receipt = _receipt("terrain_auc_vs_envelope")
    assert "radar" not in receipt["inputs"] and "sigma0" not in json.dumps(receipt["inputs"]), "no radar image is read"


# --- The page ----------------------------------------------------------------------------------------------


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_the_page_states_what_it_is_and_carries_the_licence_and_the_label() -> None:
    text = " ".join(_page().split())
    assert text.startswith("# Why threshold-only change detection failed at the 16 Sep pass")
    for phrase in ("not a flood map, not an observation of a flood and not an official warning", "Source timestamp:", "Confidence: low.",
                   "Assumptions:", "vs a season envelope, not an event map", "CC BY-SA 4.0", f"Credit: {CREDIT}.", "Changed by FloodGuard:",
                   "FloodGuard did not validate it.", "contain modified Copernicus Sentinel data 2024",
                   "No FPPS, no A-E class and no flood candidate was computed"):
        assert phrase in text, phrase
    for heading in ("## 1. What the pass of 16 September could and could not see",
                    "## 2. Why a single threshold on backscatter change abstains or fails here",
                    "## 4. Every number, traced", "## 5. Input files", "## 6. Limits",
                    "## 7. What this means for the radar methods of tasks A2 to A4", "## 8. Open points for the owners",
                    "## 9. Not reproduced, not recorded, and seen before", "## 10. Every run, reported"):
        assert heading in _page(), heading
    for identifier in diagnosis_run.OPEN_POINTS:
        assert f"| {identifier} |" in _page(), identifier
    # Decision R15: the GEOID result is quoted with its three statements.
    for phrase in ("not distinguishable from 0.40 on 14 tiles", "67.9% of the test cells had no answer", "not an independent check"):
        assert phrase in text, phrase


def test_the_page_says_what_the_review_found() -> None:
    """Each statement the review asked for is on the page, and each statement it refuted is gone."""

    text = " ".join(_page().split())
    for phrase in (
        # The pass list is Sentinel-1 only, and other radar satellites looked in the gap.
        "**No Sentinel-1 pass falls in the days when, by the replay's keyframes, the water rose and peaked.**",
        "**The snapshot holds Sentinel-1 only.** Other radar satellites did look in the gap.",
        "- **Sentinel-1 only.** Other radar satellites looked in the gap (section 1).",
        # The terrain figure was seen before.
        "first computation from cleared files and the first recorded value. It is not the first time the figure was seen",
        "ranked seven features against the same layer and printed the values on one line",
        "The two features were taken from that script",
        # Terrain on all cells is hill against plain; no ranking of terrain against radar.
        "On all of AOI-01, terrain mostly tells the plain from the hills.",
        "so low elevation can separate plain from hill as much as wet from dry",
        "so this page ranks neither above the other",
        # The window is a free choice.
        '"0.421" is therefore the value of one window, not a property of the pass',
        "The exploratory run used 5 by 5 cells",
        # One normal population; a flat-topped one passes.
        "**That holds for a normal population only.**",
        "A window that passes it is not shown to hold two populations.",
        # M1-v2 was not examined.
        "The diagnosis is consistent with those declines and did not examine them",
        "A histogram without two clear humps gives two outcomes",
        # The peak is a keyframe of the replay.
        "the second several days after the keyframe the replay sets for the modelled peak.** That keyframe is illustrative",
        # The guard's limits.
        "**What the guard does not see.** It is a net, not a proof.",
        "The repository installs no Git hook",
    ):
        assert phrase in text, phrase
    for refuted in ("No radar pass falls", "points slightly away", "at least as well", "in either direction", "computed here for the first time",
                    "The same histogram gives two outcomes", "The diagnosis gives the reason", "several days after the peak",
                    "bell-shaped population does not pass the gate, whatever"):
        assert refuted not in text, refuted
    # Slope separates hill from plain: the limit is on the page, not only in the figures file.
    assert text.count("plain from hill") >= 1 and text.count("hill from plain") >= 2


def test_every_figure_is_traced_to_its_script_its_figures_file_and_its_receipt() -> None:
    text = _page()
    table = text.split("## 4. Every number, traced", 1)[1].split("## 5. Input files", 1)[0]
    for name in FIGURES:
        row = next(line for line in table.splitlines() if f"`{name}.py`" in line or (name == "bvf_unimodal_gaussian" and "same | same | same" in line))
        assert row
        assert f"| `{name}.py` | `{name}.json` | `a1_diagnosis_{name}.json` |" in table, name
        assert (SCRIPTS / f"{name}.py").is_file()
    assert '"terrain AUC vs 4009 (to compute)": first computation from cleared files, first recorded value' in table


def test_every_number_of_the_argument_is_the_number_in_its_figures_file() -> None:
    text = " ".join(_page().split())
    bvf = _figures("bvf_unimodal_gaussian")["figures"]
    simulated = bvf["simulated_windows_of_pure_noise_through_the_m2_kernel"]
    flat_topped = bvf["one_flat_topped_population"]
    uniform = flat_topped["simulated_windows_through_the_m2_kernel"]
    mixtures = {row["second_population_share"]: row for row in bvf["two_populations_through_the_m2_kernel"]}
    mae_sai = _figures("m2_windows_mae_sai")["figures"]["between_variance_fraction"]
    geoid = _figures("m2_windows_geoid")["figures"]["between_variance_fraction"]
    gap = _figures("sentinel1_pass_gap")["figures"]
    keyframes = gap["replay_keyframes_for_context"]
    pilot = _figures("pilot_grid_vs_envelope")["figures"]
    darkening = _figures("darkening_auc_vs_envelope")["figures"]
    terrain = _figures("terrain_auc_vs_envelope")["figures"]
    readings, by_window = _darkening_rows()
    ground = {(row["feature"], row["cells"], row["permanent_water"]): row for row in terrain["readings"]}
    domain = darkening["domain"]
    everything = domain["by_permanent_water_reading"][NOTHING]
    slope = domain["slope_in_the_domain"]
    record, sensitivity = readings[(RECORD, ALL, JRC)], readings[(SENSITIVITY, ALL, JRC)]
    record_flat, sensitivity_flat = readings[(RECORD, FLAT, JRC)], readings[(SENSITIVITY, FLAT, JRC)]
    low, flat = ground[("low_elevation", ALL, JRC)], ground[("low_slope", ALL, JRC)]
    low_on_flat, flat_on_flat = ground[("low_elevation", FLAT, JRC)], ground[("low_slope", FLAT, JRC)]
    smallest, largest = darkening["smallest_and_largest_auc_over_the_readings"]
    expected = [
        # Section 2: one population against the gate.
        f"gives 2/pi = {bvf['theory_normal_population_split_at_its_mean']:.3f}",
        f"(2/pi = {bvf['theory_normal_population_split_at_its_mean']:.6f})",
        f"raises the figure to {bvf['theory_same_population_clipped_at_1st_and_99th_percentile']:.3f}",
        f"theory with clipping ({bvf['theory_same_population_clipped_at_1st_and_99th_percentile']:.6f})",
        f"{sum(row['windows'] for row in simulated)} simulated windows of pure noise scored between "
        f"{min(row['between_variance_fraction_min'] for row in simulated):.3f} and {max(row['between_variance_fraction_max'] for row in simulated):.3f}",
        f"gives 3/4 = {flat_topped['theory_uniform_population_split_at_its_mean']:.3f} in theory, above the gate",
        f"{flat_topped['simulated_windows_the_kernel_accepted']} of {flat_topped['simulated_windows']} simulated windows of one flat-topped "
        f"population were accepted, with fractions between {min(row['between_variance_fraction_min'] for row in uniform):.3f} and "
        f"{max(row['between_variance_fraction_max'] for row in uniform):.3f}",
        f"| 50% | {mixtures[0.5]['first_separation_passing_the_gate']} |",
        f"| 30% | {mixtures[0.3]['first_separation_passing_the_gate']} |",
        f"| 20% | {mixtures[0.2]['first_separation_passing_the_gate']} (every simulated window accepted from {mixtures[0.2]['first_separation_every_window_accepted']}) |",
        f"| 10% | {mixtures[0.1]['first_separation_passing_the_gate']} (every simulated window accepted from {mixtures[0.1]['first_separation_every_window_accepted']}) |",
        f"| M2 at Mae Sai, pilot grid | {mae_sai['windows']} | {mae_sai['windows_at_or_above_the_gate']} | {mae_sai['between_variance_fraction_min']:.3f} / "
        f"{mae_sai['between_variance_fraction_median']:.3f} / {mae_sai['between_variance_fraction_max']:.3f} |",
        f"| M2 rule on GEOID-Flood, 29 tiles | {geoid['windows']:,} | {geoid['windows_at_or_above_the_gate']} | {geoid['between_variance_fraction_min']:.3f} / "
        f"{geoid['between_variance_fraction_median']:.3f} / {geoid['between_variance_fraction_max']:.3f} |",
        # Section 1: the passes and the keyframes.
        f"That gap is {gap['longest_gap']['hours']:.1f} hours, or {gap['longest_gap']['days']:.2f} days",
        f"the onset at {keyframes['onset_keyframe']['in_thailand']} and the modelled peak at {keyframes['modelled_peak_keyframe']['in_thailand']}",
        f"the last pass before the onset keyframe was {keyframes['onset_keyframe']['hours_after_the_pass_of_6_september']:.1f} hours earlier",
        f"the next pass came {keyframes['onset_keyframe']['hours_before_the_pass_of_15_september_utc']:.1f} hours "
        f"({keyframes['onset_keyframe']['days_before_the_pass_of_15_september_utc']:.2f} days) after the onset keyframe and "
        f"{keyframes['modelled_peak_keyframe']['hours_before_the_pass_of_15_september_utc']:.1f} hours "
        f"({keyframes['modelled_peak_keyframe']['days_before_the_pass_of_15_september_utc']:.2f} days) after the keyframe of the modelled peak",
        # Section 3.1: the pilot grid.
        f"| Season envelope inside AOI-01 | {pilot['envelope_inside_aoi_01_km2']:.3f} |",
        f"| Of that, inside the M2 pilot grid | {pilot['envelope_inside_aoi_01_and_inside_the_pilot_grid_km2']:.3f} |",
        f"| Of that, outside the M2 pilot grid | {pilot['envelope_inside_aoi_01_and_outside_the_pilot_grid_km2']:.3f} |",
        f"leaves out **{pilot['share_of_the_envelope_in_aoi_01_outside_the_pilot_grid'] * 100:.1f}%** of the envelope inside AOI-01 and holds "
        f"{pilot['share_of_aoi_01_inside_the_pilot_grid'] * 100:.1f}% of AOI-01 ({pilot['aoi_01_km2']:.2f} km2)",
        # Section 3.2: the cells, the readings and the windows.
        f"{everything['cells']:,} cells, {everything['envelope_cells']:,} of them inside the envelope ({everything['envelope_share_of_the_cells'] * 100:.1f}%)",
        f"{everything[FLAT]['cells']:,} cells, {everything[FLAT]['envelope_cells']:,} of them inside the envelope "
        f"({everything[FLAT]['envelope_share_of_the_cells'] * 100:.1f}%)",
        f"gives {record['auc']:.6f}",
        f"in {record['auc_of_brightening'] * 100:.1f}% of pairs ({sensitivity['auc_of_brightening'] * 100:.1f}% in the sensitivity run)",
        f"by {-record['median_inside_the_layer']:.2f} dB against {-record['median_outside_the_layer']:.2f} dB outside",
        f"With no smoothing the value is near one half ({by_window[(RECORD, ALL, 1)]['auc']:.3f})",
        f"read as brightening, gives {by_window[(RECORD, ALL, 25)]['auc_of_brightening']:.3f} and "
        f"{by_window[(SENSITIVITY, ALL, 25)]['auc_of_brightening']:.3f} on all cells",
        # Section 3.3: terrain on all cells and on the cells under 5 degrees.
        f"{slope['share_of_envelope_cells_under_the_limit'] * 100:.1f}% of the envelope cells have a slope under 5 degrees, against "
        f"{slope['share_of_other_cells_under_the_limit'] * 100:.1f}% of the other cells",
        f"Low elevation gives {low_on_flat['auc']:.3f}, below one half: there the envelope cells are slightly higher "
        f"({low_on_flat['median_elevation_m_inside_the_layer']:.1f} m against {low_on_flat['median_elevation_m_outside_the_layer']:.1f} m). "
        f"Low slope gives {flat_on_flat['auc']:.3f}.",
        f"read as brightening with the 5 by 5 window, gives {record_flat['auc_of_brightening']:.3f} and {sensitivity_flat['auc_of_brightening']:.3f}; "
        f"low slope gives {flat_on_flat['auc']:.3f} and low elevation {low_on_flat['auc']:.3f}",
        # In brief.
        f"a gap of {gap['longest_gap']['days']:.2f} days. The pass that was used came "
        f"{keyframes['modelled_peak_keyframe']['days_before_the_pass_of_15_september_utc']:.2f} days after the keyframe",
        f"One normal population gives {bvf['theory_normal_population_split_at_its_mean']:.3f} in theory and "
        f"{bvf['theory_same_population_clipped_at_1st_and_99th_percentile']:.3f} through the M2 kernel",
        f"All {mae_sai['windows']} windows at Mae Sai scored between {mae_sai['between_variance_fraction_min']:.3f} and "
        f"{mae_sai['between_variance_fraction_max']:.3f}, and all {geoid['windows']:,} windows of a labelled foreign flood event scored between "
        f"{geoid['between_variance_fraction_min']:.3f} and {geoid['between_variance_fraction_max']:.3f}",
        f"holds {pilot['share_of_aoi_01_inside_the_pilot_grid'] * 100:.1f}% of AOI-01 and leaves out "
        f"{pilot['share_of_the_envelope_in_aoi_01_outside_the_pilot_grid'] * 100:.1f}% of the 2024 season envelope inside AOI-01",
        f"in {record['auc'] * 100:.1f}% of pairs ({record['auc']:.3f}, where 0.5 is no separation)",
        f"It is {by_window[(RECORD, ALL, 1)]['auc']:.3f} with no smoothing and {by_window[(RECORD, ALL, 25)]['auc']:.3f} with a 25-cell window, "
        f"{record_flat['auc']:.3f} on flat ground only, and {sensitivity['auc']:.3f} with the radar layers placed more exactly",
        f"Every reading is below one half: {smallest:.3f} to {largest:.3f}.",
        f"Low ground gives {low['auc']:.3f} and flat ground {flat['auc']:.3f}, because "
        f"{slope['share_of_envelope_cells_under_the_limit'] * 100:.1f}% of the envelope cells have a slope under 5 degrees against "
        f"{slope['share_of_other_cells_under_the_limit'] * 100:.1f}% of the other cells",
        f"On the cells under 5 degrees, low ground gives {low_on_flat['auc']:.3f} and flat ground {flat_on_flat['auc']:.3f}. On the same cells "
        f"the radar change, read as brightening, gives {record_flat['auc_of_brightening']:.3f} and {sensitivity_flat['auc_of_brightening']:.3f}.",
        # Sections 6 and 7 quote the same readings.
        f"The darkening value runs from {smallest:.3f} to {largest:.3f} over the windows, cells and geocodings tried",
        f"moves from {record['auc']:.3f} to {sensitivity['auc']:.3f} at the 5 by 5 window",
        f"inside the cells under 5 degrees slope gives {flat_on_flat['auc']:.3f}",
    ]
    # The window counts of section 2 are the marks the two window figures hold.
    assert mae_sai["windows_at_or_above_0.65"] == 1 and mae_sai["windows_at_or_above_0.70"] == 0
    assert geoid["windows_at_or_above_0.70"] == 3 and geoid["windows_at_or_above_0.71"] == 1
    expected += ["One window reached 0.65.", "three windows reached 0.70 and one reached 0.71"]
    # The two tables of section 3.2 and the table of section 3.3, cell by cell.
    labels = {RECORD: ("Run of record (control-point warp)", "Run of record"), SENSITIVITY: ("Sensitivity run (DEM height per cell)", "Sensitivity run")}
    cells_label = {ALL: "all", FLAT: "slope under 5 degrees"}
    for geocoding, (first, second) in labels.items():
        for cells in (ALL, FLAT):
            values = [f"{readings[(geocoding, cells, water)]['auc']:.3f}" for water in (JRC, WORLDCOVER, NOTHING)]
            if geocoding == RECORD and cells == ALL:
                values[0] = f"**{values[0]}**"
            row = readings[(geocoding, cells, JRC)]
            expected.append(f"| {first if cells == ALL else second} | {cells_label[cells]} | {' | '.join(values)} | "
                            f"{row['median_inside_the_layer']:.2f} / {row['median_outside_the_layer']:.2f} |")
    window_label = {1: "1 (no smoothing)", 5: "5 (the exploratory run)"}
    for window in WINDOWS:
        values = [f"{by_window[(geocoding, cells, window)]['auc']:.3f}" for geocoding in (RECORD, SENSITIVITY) for cells in (ALL, FLAT)]
        expected.append(f"| {window_label.get(window, str(window))} | {' | '.join(values)} |")
    for feature, label, unit in (("low_elevation", "Low elevation", "m"), ("low_slope", "Low slope", "degrees")):
        for cells in (ALL, FLAT):
            values = [f"{ground[(feature, cells, water)]['auc']:.3f}" for water in (JRC, WORLDCOVER, NOTHING)]
            row = ground[(feature, cells, JRC)]
            if feature == "low_elevation":
                medians = f"{row['median_elevation_m_inside_the_layer']:.1f} m / {row['median_elevation_m_outside_the_layer']:.1f} m"
            else:
                medians = f"{row['median_slope_degrees_inside_the_layer']:.2f} / {row['median_slope_degrees_outside_the_layer']:.2f} degrees"
            expected.append(f"| {label} | {cells_label[cells]} | {' | '.join(values)} | {medians} |")
            assert unit in medians
    for phrase in expected:
        assert phrase in text, phrase
    # The pass table: each pass with its time in UTC, its time in Thailand and its track.
    for entry in gap["passes"]:
        moment = diagnosis.parse_utc(entry["start_utc"])
        local = moment + diagnosis.THAILAND_UTC_OFFSET
        assert entry["start_in_thailand"] == f"{local:%Y-%m-%d %H:%M} ICT"
        assert f"| {moment.day} Sep 2024, {moment:%H:%M:%S} | {local.day} Sep, {local:%H:%M} ICT | {entry['relative_orbit']} |" in text


def test_the_numbers_quoted_from_tasks_a2_and_a4_are_those_of_the_radar_table() -> None:
    """Sections 2 and 7 quote the A2/A4 result. If that run is superseded (A4-OP1 is open), these fail and the page is read again."""

    text = " ".join(_page().split())
    table = json.loads(RADAR_TABLE.read_text(encoding="ascii"))
    methods = table["methods"]
    tiles = len(table["grid"]["tiles_holding_part_of_the_frame"])
    words = {6: "six", 9: "nine"}
    literal = methods["m1_literal"]
    thresholds = [tile["whole_tile"]["otsu_threshold_delta_vh_db"] for tile in literal["tiles"]]
    assert len(thresholds) == tiles == 9
    share = literal["frame"]["candidate_cells"] / literal["frame"]["cells"]
    assert (f"M1-literal put its threshold between {min(thresholds):.1f} and {max(thresholds):+.1f} dB in the {words[tiles]} tiles and flagged "
            f"{literal['frame']['candidate_area_km2']:.2f} km2, {share * 100:.1f}% of the frame") in text
    v2 = methods["m1_v2"]
    declined = [tile for tile in v2["tiles"] if tile["declined"]]
    assert sorted(tile["tile"] for tile in declined) == sorted(v2["tiles_declined"]) and len(declined) == 6
    assert (f"declined {words[len(declined)]} of the {words[tiles]} tiles of the Mae Sai frame, "
            f"{v2['frame']['abstention_fraction'] * 100:.1f}% of its cells") in text
    assert f"M1-v2 on {words[len(declined)]} of {words[tiles]} tiles" in text
    # The two kinds of decline of M1-v2, which this diagnosis did not examine.
    no_block = [tile for tile in declined if tile["declined_because"] == "no bimodal block in the tile"]
    kept = [tile["whole_tile"]["sides"]["darkening"]["selected_blocks"] for tile in declined if tile not in no_block]
    assert len(no_block) == 1 and all("bimodal blocks were found" in tile["declined_because"] for tile in declined if tile not in no_block)
    assert f"One tile had no bimodal block. Five tiles kept bimodal blocks ({', '.join(str(count) for count in kept[:-1])} and {kept[-1]}) and found no accepted threshold" in text
    assert f"{methods['un_spider']['frame']['candidate_area_km2']:.2f} km2 of candidate area" in text
    displaced = table["geolocation_check"]["control_point_warp"]["whole_grid"]
    assert round((displaced["east_m"] ** 2 + displaced["north_m"] ** 2) ** 0.5, -1) == 680.0 and "lie about 680 m from where they belong" in text
    assert round(table["geolocation_check"]["pre_against_post"]["east_m_subcell"]) == 9 and "the two dates lie about 9 m apart" in text
    assert "This page measured nothing about M1-v2." in text and "no script here measured anything about M1-v2" in text


def test_every_hash_on_the_page_is_an_input_of_a_receipt_or_a_protocol_in_force() -> None:
    known: set[str] = set()
    for name in FIGURES:
        receipt = _receipt(name)
        known |= set(re.findall(r"[0-9a-f]{64}", json.dumps(receipt["inputs"])))
        known |= set(receipt["protocol_sha256"].values())
    on_page = set(re.findall(r"[0-9a-f]{64}", _page()))
    assert len(on_page) >= 25 and on_page <= known, sorted(on_page - known)
    assert _receipt("sentinel1_pass_gap")["inputs"]["replay_numbers"]["sha256"] in on_page


# --- Every run, reported ---------------------------------------------------------------------------------


def _clock(stamp: str) -> str:
    return stamp[11:]


def _run_rows(text: str) -> list[str]:
    return [line for line in text.splitlines() if re.match(r"\| (?:about )?\d{2}:\d{2}", line)]


@pytest.mark.parametrize("source", ["page", "readme"])
def test_the_run_times_in_the_run_tables_are_the_times_the_receipts_record(source: str) -> None:
    """Every run of every figure has a row whose start and finish are the times its receipt records.

    The receipt in force gives the times of its own run and, in ``run_history``, of each run it carries. A
    first run that was superseded before the times were carried has its finish in the history and its start
    only in the copy kept outside Git; the tables mark such a start with an asterisk.
    """

    text = _page().split("## 10. Every run, reported", 1)[1].split("## 11.", 1)[0] if source == "page" else \
        README.read_text(encoding="utf-8").split("### Plan task A1: the abstention diagnosis", 1)[1]
    rows = _run_rows(text)
    runs = 0
    for name in FIGURES:
        receipt = _receipt(name)
        times = receipt["timestamps"]
        assert any(row.startswith(f"| {_clock(times['run_started_at_utc'])} | {_clock(times['run_finished_at_utc'])} |") for row in rows), (name, times)
        runs += 1
        for run in receipt["run_history"]["earlier_runs"]:
            finish = _clock(run["generated_at_utc"])
            if run.get("run_started_at_utc") is not None:
                assert any(row.startswith(f"| {_clock(run['run_started_at_utc'])} | {finish} |") for row in rows), (name, run)
            else:
                assert any(re.match(rf"\| \d{{2}}:\d{{2}}:\d{{2}}Z \* \| {finish} \|", row) for row in rows), (name, run)
            runs += 1
    # Seven figures: four were run three or four times, three were run twice.
    timed = [row for row in rows if re.match(r"\| \d{2}:\d{2}:\d{2}Z", row)]
    assert runs == len(timed) == 20, "one row for each run that wrote a receipt, and no other row with exact times"
    assert len([row for row in timed if " * |" in row[:16]]) == 4
    # The runs that wrote nothing are listed too: the reads, the verifications and the runs of the review.
    untimed = " ".join(row for row in rows if row.startswith("| about "))
    for phrase in ("Reads while the scripts were written", "`--verify`", "review", "Reads after the review"):
        assert phrase in untimed, phrase
    assert "about 21:05" in untimed and "about 21:38" in untimed, "the runs of the review are reported"


# --- Wording ---------------------------------------------------------------------------------------------


def _texts() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = [("page", _page()), ("scripts README", (SCRIPTS / "README.md").read_text(encoding="utf-8")),
                                    ("figures README", (ROOT / "outputs" / "a1_diagnosis" / "README.md").read_text(encoding="utf-8")),
                                    ("planning README, A1 section", README.read_text(encoding="utf-8").split("### Plan task A1: the abstention diagnosis", 1)[1])]
    for name in FIGURES:
        items += [(f"{name} figures {path}", text) for path, text in json_strings(_figures(name))]
        items += [(f"{name} receipt {path}", text) for path, text in json_strings(_receipt(name))]
        source = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
        items += [(f"{name}.py", text) for text in python_strings(source)]
        items.append((f"{name}.py header", ast.get_docstring(ast.parse(source)) or ""))
    for module in ("abstention_diagnosis.py", "diagnosis_run.py", "diagnosis_layers.py", "ait_mbrsc_guard.py"):
        items += [(module, text) for text in python_strings((ROOT / "src" / "floodguard" / module).read_text(encoding="utf-8"))]
    items += [("guard command", text) for text in python_strings((ROOT / "scripts" / "check_ait_mbrsc_guard.py").read_text(encoding="utf-8"))]
    baseline = json.loads((ROOT / "docs" / "proposal_execution" / "ait_mbrsc_guard_baseline_v2.json").read_text(encoding="ascii"))
    items += [(f"guard baseline {path}", text) for path, text in json_strings({key: value for key, value in baseline.items() if key != "files"})]
    return items


def test_the_shared_wording_lint_passes_on_the_page_the_figures_and_the_scripts() -> None:
    items = _texts()
    assert len(items) > 400
    findings = [finding.describe() for source, text in items for finding in find_violations(text, RULES, source)]
    assert findings == []
    # The lint does see a claim: a figure against the season envelope is never called a validation or a score of correctness.
    for claim in ("The darkening was validated against product 4009.", "Accuracy against the season envelope: 42%",
                  "Recall of the season envelope: 0.42", "The season envelope corroborates the radar."):
        assert find_violations(claim, RULES), claim


def test_the_readme_section_is_the_last_one_and_lists_every_receipt() -> None:
    text = README.read_text(encoding="utf-8")
    assert text.count("### Plan task A1: the abstention diagnosis") == 1
    section = text.split("### Plan task A1: the abstention diagnosis", 1)[1]
    assert "\n## " not in section and "\n### " not in section, "the A1 section is the last section of the file"
    for name in FIGURES:
        assert f"`a1_diagnosis_{name}.json`" in section and f"`scripts/diagnostics/{name}.py`" in section
    for identifier in diagnosis_run.OPEN_POINTS:
        assert f"**{identifier}," in section, identifier
    for phrase in ("CC BY-SA 4.0", f"Credit: {CREDIT}.", "Changed by FloodGuard:", "FloodGuard did not validate it.",
                   "first computation from cleared files, first recorded value", "**The runs of the review**",
                   "`docs/proposal_execution/ait_mbrsc_guard_baseline_v2.json`"):
        assert phrase in section, phrase
    # A superseded run is named in the README by the start of the SHA-256 its receipt records.
    for name in FIGURES:
        for run in _receipt(name)["run_history"]["earlier_runs"]:
            assert f"`{run['receipt_sha256'][:8]}...{run['receipt_sha256'][-4:]}`" in section, name
            assert f"`{run['figures_sha256'][:8]}...{run['figures_sha256'][-4:]}`" in section, name
    # The values the README quotes for the windows are the values of the figures file.
    _readings, by_window = _darkening_rows()
    for geocoding, cells, label in ((RECORD, ALL, "Run of record, all cells"), (RECORD, FLAT, "Cells under 5 degrees"),
                                    (SENSITIVITY, ALL, "Sensitivity run, all cells"), (SENSITIVITY, FLAT, "Cells under 5 degrees")):
        values = ", ".join(f"{by_window[(geocoding, cells, window)]['auc']:.3f}" for window in WINDOWS)
        assert f"{label}: {values}." in section, (label, values)


# --- The extra and the CI sync ---------------------------------------------------------------------------


def test_the_diagnostics_extra_exists_and_is_left_out_of_the_default_ci_sync() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = pyproject.split("\ndiagnostics = [", 1)[1].split("]", 1)[0]
    requirements = sorted(re.findall(r'"([A-Za-z0-9_-]+)[^"]*"', block))
    assert requirements == ["geopandas", "pyproj", "rasterio", "shapely"]
    # The extra adds no package: each one is already required by another extra.
    others = pyproject.split("[project.optional-dependencies]", 1)[1].split("\n# Diagnosis scripts", 1)[0].lower()
    assert all(f'"{name}' in others for name in requirements)
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "uv sync --locked --all-extras --no-extra diagnostics" in workflow
    assert "uv sync --locked --all-extras\n" not in workflow
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert 'provides-extras = ["dev", "ml", "geo", "theos2", "evidence", "diagnostics"]' in lock
    assert lock.count("marker = \"extra == 'diagnostics'\"") == 4


# --- With the external data workspace --------------------------------------------------------------------


@pytest.mark.parametrize("name", [name for name in FIGURES if name not in NO_EXTERNAL_DATA])
def test_each_figure_verifies_against_the_external_data_when_it_is_there(name: str) -> None:
    value = os.environ.get(diagnosis_run.EXTERNAL_DATA_VARIABLE, "").strip()
    if not value or not Path(value).is_dir():
        pytest.skip(f"{diagnosis_run.EXTERNAL_DATA_VARIABLE} is not set: the external data workspace is not read by the default suite")
    module = _script(name)
    summary = diagnosis_run.verify(module.SPEC, module.make_compute(ROOT, Path(value)), root=ROOT)
    assert summary["verified"] is True, summary
