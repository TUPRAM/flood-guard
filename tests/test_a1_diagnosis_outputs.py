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
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
FIGURES = ("bvf_unimodal_gaussian", "m2_windows_mae_sai", "m2_windows_geoid", "sentinel1_pass_gap", "pilot_grid_vs_envelope",
           "darkening_auc_vs_envelope", "terrain_auc_vs_envelope")
ENVELOPE_FIGURES = ("pilot_grid_vs_envelope", "darkening_auc_vs_envelope", "terrain_auc_vs_envelope")
CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
HEADER_SECTIONS = ("Reads", "Computes", "Does not show", "Writes", "Run")


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
    assert receipt["script"]["path"] == f"scripts/diagnostics/{name}.py" and re.fullmatch(r"[0-9a-f]{64}", receipt["script"]["sha256"])
    assert re.search(r"[0-9a-f]{64}", json.dumps(receipt["inputs"])), "inputs are named by SHA-256"
    assert "<external_data_workspace>" in json.dumps(receipt["inputs"]) or name in ("bvf_unimodal_gaussian", "sentinel1_pass_gap")
    assert not re.search(r"[A-Za-z]:[\\/]{1,2}Users", json.dumps(receipt) + json.dumps(figures)), "no machine path"
    # Every run is reported: a superseding run names the run it replaced, by SHA-256, with the reason.
    history = receipt["run_history"]["earlier_runs"]
    if receipt["run_kind"] == "superseding_run":
        supersedes = receipt["supersedes"]
        assert supersedes["reason"].strip() and isinstance(supersedes["figures_same"], bool)
        assert history and history[-1]["receipt_sha256"] == supersedes["receipt_sha256"]
        assert history[-1]["figures_sha256"] == supersedes["figures_sha256"]
        assert history[-1]["generated_at_utc"] == supersedes["generated_at_utc"] < receipt["generated_at_utc"]
    else:
        assert receipt["run_kind"] == "first_run" and receipt["supersedes"] is None and history == []
    for point in figures["open_points"]:
        assert point == {"id": point["id"], **diagnosis_run.OPEN_POINTS[point["id"]]}
    assert {"FPPS", "A-E class"} <= set(figures["not_computed"])


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
    assert figures["measured_against"] == "vs a season envelope, not an event map"
    licence = figures["licence"]
    assert licence["name"] == "CC BY-SA 4.0" and licence["credit"] == CREDIT
    assert licence["change_notice"].startswith("Changed by FloodGuard: clipped to AOI-01")
    assert licence["change_notice"].endswith(f"Source: {CREDIT}, CC BY-SA 4.0.")
    assert "Field_Validation=0" in licence["standard_sentence"] and "FloodGuard did not validate it." in licence["standard_sentence"]
    assert "never an event map" in licence["used_as"] and "never a reference" in licence["used_as"]
    record = ROOT / licence["rights_record"]["path"]
    assert licence["rights_record"]["sha256"] == _sha256(record)
    assert f"{CREDIT}, CC BY-SA 4.0" in figures["attributions"]
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
    figures = _figures(name)
    assert figures["measured_against"] is None and figures["licence"] is None
    assert "4009" not in json.dumps(_receipt(name)["inputs"])


# --- What the runs measured, against what the plan states -------------------------------------------------


def test_one_normal_population_stays_below_the_gate_in_theory_and_through_the_kernel() -> None:
    figures = _figures("bvf_unimodal_gaussian")["figures"]
    assert figures["gate"] == 0.72
    assert figures["theory_normal_population_split_at_its_mean"] == round(diagnosis.GAUSSIAN_BVF_THEORY, 6) == 0.63662
    assert figures["theory_same_population_clipped_at_1st_and_99th_percentile"] == round(diagnosis.clipped_gaussian_bvf(), 6)
    assert all(figures["below_the_gate"].values())
    simulated = figures["simulated_windows_of_pure_noise_through_the_m2_kernel"]
    assert sum(row["windows"] for row in simulated) == 600 and all(row["windows_passing_the_gate"] == 0 for row in simulated)
    assert figures["largest_fraction_of_any_simulated_window"] == max(row["between_variance_fraction_max"] for row in simulated) < 0.72
    plan = _figures("bvf_unimodal_gaussian")["plan_figure"]
    assert plan["plan_value"] == 0.637 == plan["measured"] and plan["reproduced"] is True
    # A fresh, smaller simulation gives the same picture (the committed one is seeded; this one is not compared exactly).
    fresh = diagnosis.simulate_unimodal((16384,), repeats=20, seed=99)[0]
    assert fresh["windows_passing_the_gate"] == 0
    assert fresh["between_variance_fraction_mean"] == pytest.approx(simulated[1]["between_variance_fraction_mean"], abs=0.005)
    shares = [row["second_population_share"] for row in figures["two_populations_through_the_m2_kernel"]]
    needed = [row["first_separation_passing_the_gate"] for row in figures["two_populations_through_the_m2_kernel"]]
    assert shares == [0.5, 0.3, 0.2, 0.1] and needed == sorted(needed) and needed[0] > 2.0


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
    assert summary["verified"] is True, summary
    figures = _figures("sentinel1_pass_gap")
    assert figures["figures"]["pass_count"] == 4 and figures["figures"]["no_pass_strictly_inside_the_interval"] is True
    assert figures["figures"]["longest_gap"]["days"] == 9.49 and figures["plan_figure"]["reproduced"] is True
    assert figures["plan_figure"]["measured"]["after_utc"] == "2024-09-06T11:31" and figures["plan_figure"]["measured"]["before_utc"] == "2024-09-15T23:16"
    assert [entry["relative_orbit"] for entry in figures["figures"]["passes"]] == [135, 172, 135, 172]
    # The two replay keyframes are written in the script as the replay's own figures state them, and are labelled as a scenario.
    replay = (ROOT / "docs" / "demo" / "replay_numbers.md").read_text(encoding="utf-8")
    for keyframe in module.REPLAY_KEYFRAMES.values():
        assert f"`{keyframe['key']}`" in replay and keyframe["in_thailand"] in replay
        thailand = diagnosis.parse_utc(keyframe["utc"]) + diagnosis.THAILAND_UTC_OFFSET
        assert f"{thailand.day} Sep {thailand:%H:%M} ICT" == keyframe["in_thailand"]
    context = figures["figures"]["replay_keyframes_for_context"]
    assert "illustrative" in context["what"] and "not observations" in context["what"]
    assert context["onset_keyframe"]["inside_the_gap"] and context["modelled_peak_keyframe"]["inside_the_gap"]


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
    for row in darkening["figures"]["readings"] + terrain["figures"]["readings"]:
        counts = domain["by_permanent_water_reading"][row["permanent_water"]]
        assert row["cells_inside_the_layer"] == counts["envelope_cells"] and row["cells_left_out_for_no_value"] == 0
        assert row["cells_inside_the_layer"] + row["cells_outside_the_layer"] == counts["cells"]
        assert 0.0 < row["auc"] < 1.0


def test_the_darkening_figure_reproduces_the_plan_and_is_given_under_both_geocodings() -> None:
    document = _figures("darkening_auc_vs_envelope")
    readings = document["figures"]["readings"]
    assert len(readings) == 6 and {row["geocoding"] for row in readings} == {"gcp_polynomial", "annotation_grid_with_cell_height"}
    assert {row["permanent_water"] for row in readings} == {"jrc_surface_water", "worldcover_class_80", "nothing_left_out"}
    exploratory = document["figures"]["reading_that_follows_the_exploratory_definition"]
    assert exploratory["geocoding"] == "gcp_polynomial" and exploratory["permanent_water"] == "jrc_surface_water"
    assert round(exploratory["auc"], 3) == 0.421 == document["plan_figure"]["plan_value"] and document["plan_figure"]["reproduced"] is True
    assert document["figures"]["every_reading_is_below_one_half"] is True and max(row["auc"] for row in readings) < 0.5
    for row in readings:
        assert row["auc_of_brightening"] == pytest.approx(1 - row["auc"], abs=1e-6)
        assert row["median_inside_the_layer"] < row["median_outside_the_layer"] < 0  # Brighter after, and more so inside.
    # No reading is named the figure of record, and the open points say why.
    assert "figure_of_record" not in json.dumps(document)
    assert [point["id"] for point in document["open_points"]] == ["A1-OP2", "A1-OP3", "A1-OP4", "A1-OP5", "A1-OP6"]
    receipt = _receipt("darkening_auc_vs_envelope")
    for geocoding, relative in (("gcp_polynomial", "outputs/planning_v1/radar_o1_mae_sai_v1_receipt.json"),
                                ("annotation_grid_with_cell_height", "outputs/planning_v1/radar_o1_mae_sai_v1_height_aware_sensitivity_receipt.json")):
        radar = receipt["inputs"]["radar"][geocoding]
        assert radar["receipt"] == {"path": relative, "sha256": _sha256(ROOT / relative)}
        bound = {entry["path"]: entry["sha256"] for entry in json.loads((ROOT / relative).read_text(encoding="ascii"))["outputs"]["rasters"]}
        for key in ("sigma0_pre_20240903", "sigma0_post_20240915"):
            assert bound[radar[key]["path"]] == radar[key]["sha256"], "the radar raster is the one its registered receipt binds"
    # The candidates of tasks A2 and A4 are not read (guardrail GR4): only the sigma0 rasters are.
    assert not re.search(r"_candidate\.tif|_score\.tif|_reason\.tif", json.dumps(receipt["inputs"]))


def test_the_terrain_figure_is_the_first_computation_and_names_no_figure_of_record() -> None:
    document = _figures("terrain_auc_vs_envelope")
    assert document["plan_figure"]["plan_value"] is None and document["plan_figure"]["reproduced"] is None
    readings = document["figures"]["readings"]
    assert len(readings) == 6 and {row["feature"] for row in readings} == {"low_elevation", "low_slope"}
    for row in readings:
        assert 0.5 < row["auc"] < 0.75
    assert [point["id"] for point in document["open_points"]] == ["A1-OP1", "A1-OP4", "A1-OP6"]
    assert "HAND (height above the nearest drainage)" in document["not_computed"]
    assert "neither is the figure of record" in document["figures"]["not_named_the_terrain_figure_of_the_plan"]
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
                    "## 9. Not reproduced, and not recorded", "## 10. Every run, reported"):
        assert heading in _page(), heading
    for identifier in diagnosis_run.OPEN_POINTS:
        assert f"| {identifier} |" in _page(), identifier
    # Decision R15: the GEOID result is quoted with its three statements.
    for phrase in ("not distinguishable from 0.40 on 14 tiles", "67.9% of the test cells had no answer", "not an independent check"):
        assert phrase in text, phrase


def test_every_figure_is_traced_to_its_script_its_figures_file_and_its_receipt() -> None:
    text = _page()
    table = text.split("## 4. Every number, traced", 1)[1].split("## 5. Input files", 1)[0]
    for name in FIGURES:
        row = next(line for line in table.splitlines() if f"`{name}.py`" in line or (name == "bvf_unimodal_gaussian" and "same | same | same" in line))
        assert row
        assert f"| `{name}.py` | `{name}.json` | `a1_diagnosis_{name}.json` |" in table, name
        assert (SCRIPTS / f"{name}.py").is_file()


def test_every_number_of_the_argument_is_the_number_in_its_figures_file() -> None:
    text = " ".join(_page().split())
    bvf = _figures("bvf_unimodal_gaussian")["figures"]
    simulated = bvf["simulated_windows_of_pure_noise_through_the_m2_kernel"]
    mixtures = {row["second_population_share"]: row for row in bvf["two_populations_through_the_m2_kernel"]}
    mae_sai = _figures("m2_windows_mae_sai")["figures"]["between_variance_fraction"]
    geoid = _figures("m2_windows_geoid")["figures"]["between_variance_fraction"]
    gap = _figures("sentinel1_pass_gap")["figures"]
    keyframes = gap["replay_keyframes_for_context"]
    pilot = _figures("pilot_grid_vs_envelope")["figures"]
    darkening = _figures("darkening_auc_vs_envelope")["figures"]
    terrain = _figures("terrain_auc_vs_envelope")["figures"]
    record = {row["permanent_water"]: row for row in darkening["readings"] if row["geocoding"] == "gcp_polynomial"}
    sensitivity = {row["permanent_water"]: row for row in darkening["readings"] if row["geocoding"] == "annotation_grid_with_cell_height"}
    elevation = {row["permanent_water"]: row for row in terrain["readings"] if row["feature"] == "low_elevation"}
    slope = {row["permanent_water"]: row for row in terrain["readings"] if row["feature"] == "low_slope"}
    everything = darkening["domain"]["by_permanent_water_reading"]["nothing_left_out"]
    expected = [
        f"gives 2/pi = {bvf['theory_normal_population_split_at_its_mean']:.3f}",
        f"(2/pi = {bvf['theory_normal_population_split_at_its_mean']:.6f})",
        f"raises the figure to {bvf['theory_same_population_clipped_at_1st_and_99th_percentile']:.3f}",
        f"theory with clipping ({bvf['theory_same_population_clipped_at_1st_and_99th_percentile']:.6f})",
        f"{sum(row['windows'] for row in simulated)} simulated windows of pure noise scored between "
        f"{min(row['between_variance_fraction_min'] for row in simulated):.3f} and {max(row['between_variance_fraction_max'] for row in simulated):.3f}",
        f"| 50% | {mixtures[0.5]['first_separation_passing_the_gate']} |",
        f"| 30% | {mixtures[0.3]['first_separation_passing_the_gate']} |",
        f"| 20% | {mixtures[0.2]['first_separation_passing_the_gate']} (every simulated window accepted from {mixtures[0.2]['first_separation_every_window_accepted']}) |",
        f"| 10% | {mixtures[0.1]['first_separation_passing_the_gate']} (every simulated window accepted from {mixtures[0.1]['first_separation_every_window_accepted']}) |",
        f"| M2 at Mae Sai, pilot grid | {mae_sai['windows']} | {mae_sai['windows_at_or_above_the_gate']} | {mae_sai['between_variance_fraction_min']:.3f} / "
        f"{mae_sai['between_variance_fraction_median']:.3f} / {mae_sai['between_variance_fraction_max']:.3f} |",
        f"| M2 rule on GEOID-Flood, 29 tiles | {geoid['windows']:,} | {geoid['windows_at_or_above_the_gate']} | {geoid['between_variance_fraction_min']:.3f} / "
        f"{geoid['between_variance_fraction_median']:.3f} / {geoid['between_variance_fraction_max']:.3f} |",
        f"That gap is {gap['longest_gap']['hours']:.1f} hours, or {gap['longest_gap']['days']:.2f} days",
        f"the last pass before the onset keyframe was {keyframes['onset_keyframe']['hours_after_the_pass_of_6_september']:.1f} hours earlier",
        f"the next pass came {keyframes['onset_keyframe']['hours_before_the_pass_of_15_september_utc']:.1f} hours "
        f"({keyframes['onset_keyframe']['days_before_the_pass_of_15_september_utc']:.2f} days) after the onset keyframe and "
        f"{keyframes['modelled_peak_keyframe']['hours_before_the_pass_of_15_september_utc']:.1f} hours "
        f"({keyframes['modelled_peak_keyframe']['days_before_the_pass_of_15_september_utc']:.2f} days) after the keyframe of the modelled peak",
        f"| Season envelope inside AOI-01 | {pilot['envelope_inside_aoi_01_km2']:.3f} |",
        f"| Of that, inside the M2 pilot grid | {pilot['envelope_inside_aoi_01_and_inside_the_pilot_grid_km2']:.3f} |",
        f"| Of that, outside the M2 pilot grid | {pilot['envelope_inside_aoi_01_and_outside_the_pilot_grid_km2']:.3f} |",
        f"leaves out **{pilot['share_of_the_envelope_in_aoi_01_outside_the_pilot_grid'] * 100:.1f}%** of the envelope inside AOI-01 and holds "
        f"{pilot['share_of_aoi_01_inside_the_pilot_grid'] * 100:.1f}% of AOI-01 ({pilot['aoi_01_km2']:.2f} km2)",
        f"{everything['cells']:,} cells, {everything['envelope_cells']:,} of them inside the envelope ({everything['envelope_share_of_the_cells'] * 100:.1f}%)",
        f"gives {record['jrc_surface_water']['auc']:.6f}",
        f"in {record['jrc_surface_water']['auc_of_brightening'] * 100:.1f}% of pairs ({sensitivity['jrc_surface_water']['auc_of_brightening'] * 100:.1f}% in the sensitivity run)",
        f"by {-record['jrc_surface_water']['median_inside_the_layer']:.2f} dB against {-record['jrc_surface_water']['median_outside_the_layer']:.2f} dB outside",
        # The summary and the terrain comparison quote the same readings (JRC water left out).
        f"{elevation['jrc_surface_water']['auc']:.3f} for low ground and {slope['jrc_surface_water']['auc']:.3f} for flat ground, against "
        f"{record['jrc_surface_water']['auc_of_brightening']:.3f} and {sensitivity['jrc_surface_water']['auc_of_brightening']:.3f} for the radar change read as brightening",
        f"Flat ground ({slope['jrc_surface_water']['auc']:.3f}) separates it more than the radar change of this pass does in either direction "
        f"({record['jrc_surface_water']['auc_of_brightening']:.3f} and {sensitivity['jrc_surface_water']['auc_of_brightening']:.3f} when read as brightening); "
        f"low ground ({elevation['jrc_surface_water']['auc']:.3f})",
        f"in {record['jrc_surface_water']['auc'] * 100:.1f}% of pairs ({record['jrc_surface_water']['auc']:.3f}, where 0.5 is no separation)",
        f"the value is {sensitivity['jrc_surface_water']['auc']:.3f}. Cells inside the envelope",
        f"holds {pilot['share_of_aoi_01_inside_the_pilot_grid'] * 100:.1f}% of AOI-01 and leaves out "
        f"{pilot['share_of_the_envelope_in_aoi_01_outside_the_pilot_grid'] * 100:.1f}% of the 2024 season envelope inside AOI-01",
        f"a gap of {gap['longest_gap']['days']:.2f} days. The pass that was used came "
        f"{keyframes['modelled_peak_keyframe']['days_before_the_pass_of_15_september_utc']:.2f} days after the keyframe",
        f"All {mae_sai['windows']} windows at Mae Sai scored between {mae_sai['between_variance_fraction_min']:.3f} and "
        f"{mae_sai['between_variance_fraction_max']:.3f}, and all {geoid['windows']:,} windows of a labelled foreign flood event scored between "
        f"{geoid['between_variance_fraction_min']:.3f} and {geoid['between_variance_fraction_max']:.3f}",
    ]
    labels = {"jrc_surface_water": "JRC surface water", "worldcover_class_80": "WorldCover class 80", "nothing_left_out": "nothing"}
    for water, label in labels.items():
        first = "Run of record (control-point warp)" if water == "jrc_surface_water" else "Run of record"
        value = f"**{record[water]['auc']:.3f}**" if water == "jrc_surface_water" else f"{record[water]['auc']:.3f}"
        expected.append(f"| {first} | {label} | {value} | {record[water]['median_inside_the_layer']:.2f} / {record[water]['median_outside_the_layer']:.2f} |")
        first = "Sensitivity run (DEM height per cell)" if water == "jrc_surface_water" else "Sensitivity run"
        expected.append(f"| {first} | {label} | {sensitivity[water]['auc']:.3f} | {sensitivity[water]['median_inside_the_layer']:.2f} / "
                        f"{sensitivity[water]['median_outside_the_layer']:.2f} |")
        expected.append(f"| Low elevation | {label} | {elevation[water]['auc']:.3f} | {elevation[water]['median_elevation_m_inside_the_layer']:.1f} m / "
                        f"{elevation[water]['median_elevation_m_outside_the_layer']:.1f} m |")
        expected.append(f"| Low slope | {label} | {slope[water]['auc']:.3f} | {slope[water]['median_slope_degrees_inside_the_layer']:.2f} / "
                        f"{slope[water]['median_slope_degrees_outside_the_layer']:.2f} degrees |")
    for phrase in expected:
        assert phrase in text, phrase
    for entry in gap["passes"]:
        moment = diagnosis.parse_utc(entry["start_utc"])
        assert f"| {moment.day} Sep 2024, {moment:%H:%M:%S} |" in text and f"| {entry['relative_orbit']} |" in text


def test_every_hash_on_the_page_is_an_input_of_a_receipt_or_a_protocol_in_force() -> None:
    known: set[str] = set()
    for name in FIGURES:
        receipt = _receipt(name)
        known |= set(re.findall(r"[0-9a-f]{64}", json.dumps(receipt["inputs"])))
        known |= set(receipt["protocol_sha256"].values())
    on_page = set(re.findall(r"[0-9a-f]{64}", _page()))
    assert len(on_page) >= 24 and on_page <= known, sorted(on_page - known)


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
    baseline = json.loads((ROOT / "docs" / "proposal_execution" / "ait_mbrsc_guard_baseline_v1.json").read_text(encoding="ascii"))
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
    for phrase in ("CC BY-SA 4.0", f"Credit: {CREDIT}.", "Changed by FloodGuard:", "FloodGuard did not validate it."):
        assert phrase in section, phrase
    # A superseded run is named in the README by the start of the SHA-256 its receipt records.
    for name in FIGURES:
        for run in _receipt(name)["run_history"]["earlier_runs"]:
            assert f"`{run['receipt_sha256'][:8]}...{run['receipt_sha256'][-4:]}`" in section, name
            assert f"`{run['figures_sha256'][:8]}...{run['figures_sha256'][-4:]}`" in section, name


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


@pytest.mark.parametrize("name", [name for name in FIGURES if name != "sentinel1_pass_gap"])
def test_each_figure_verifies_against_the_external_data_when_it_is_there(name: str) -> None:
    value = os.environ.get(diagnosis_run.EXTERNAL_DATA_VARIABLE, "").strip()
    if not value or not Path(value).is_dir():
        pytest.skip(f"{diagnosis_run.EXTERNAL_DATA_VARIABLE} is not set: the external data workspace is not read by the default suite")
    module = _script(name)
    summary = diagnosis_run.verify(module.SPEC, module.make_compute(ROOT, Path(value)), root=ROOT)
    assert summary["verified"] is True, summary
