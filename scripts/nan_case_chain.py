"""Run the score chain of the Nan case: a flood raster and a frame's planning context to a planning result file.

Protocol ``docs/proposal_execution/nan_case_protocol_v1.json`` (decision log R51) feeds a flood map through the
planning chain of protocols v1a and v1b, unchanged except where the Nan protocol says otherwise, to a score and a
class per tambon. This script is that chain as one command. It reads:

* a flood raster on the frame's 20 m grid (EPSG:32647): 1 flagged, 0 not flagged (by radar or by terrain), 255 no
  answer; the central map, and for the ensemble the lower and the upper map (``z_vh_max`` minus and plus 0.5);
* the frame's planning context of the vehicle mode (the format of ``scripts/build_planning_context.py``), the
  tambon boundaries (COD-AB ``tha_admin3``), the ESA WorldCover tile for permanent water, the age counts of each
  tambon (a table, or the WorldPop 2024 age rasters), and optionally the 2024-rescaled demand;
* the case-level outcome of test 1 and the dry control, which the binding rule of the Nan protocol reads.

It runs, with the code of the earlier tasks: closure rule v1 at its three levels (``build_access_diff.case_runs``,
unchanged), the access difference of the two public services, the five components of planning frame v1, the
confidence record (rule v1 with the Nan binding rule in the place of C1's T2 skill condition for case N1;
``floodguard.nan_case_chain``), FPPS and the classes (``floodguard.planning_assessment``), and the ensemble of the
Nan protocol (``floodguard.uncertainty_ensemble``). It writes a result file in the schema of the published case
SE1 file (overlay schema 1.1), a run record beside it, and the access runs and the ensemble cells in the work
folder outside Git.

Every figure is agreement with a reference layer, not accuracy. A result is planning guidance for preparedness
and prioritisation after an event: not real-time, not an official warning and not an operational product, and
class E never means safe. ``accepted_fpps`` and ``accepted_action_class`` stay null and no result can feed the
decision layer.

Two modes::

    # The proof on case SE1's own inputs: reproduce the published SE1 rows and the registered ensemble.
    python scripts/nan_case_chain.py se1-replay --external-root <external data root> [--age-dir <WorldPop 2024 age folder>]

    # A Nan case, after the test (the freeze record and the test record must exist). The outcome, the pass and
    # its map are read from the test record; every value can also be given on its own (see --help):
    python scripts/nan_case_chain.py nan --case N1 --external-root <external data root> \
        --test-result outputs/nan_case/test_result_v1.json \
        --context <frame folder>/e4_vehicle_candidate/context_inputs.json \
        --routing-geometry <frame folder>/n1_routing_geometry.geojson \
        --age-table <frame folder>/age_exposure_n1_v1.json \
        --rescaled-population <frame folder>/rescaled_demand_2024_v1.json

    # The same inputs checked without a flood map (opens no map, measures nothing):
    python scripts/nan_case_chain.py nan --case N1 --external-root <external data root> --check-inputs \
        --context ... --routing-geometry ... --age-table ... --rescaled-population ...

A flood map is either one GeoTIFF per level (``--flood-central``, ``--flood-lower``, ``--flood-upper``) or one map of
the method lane with the bands ``code_lower``, ``code_central`` and ``code_upper`` (``--flood-map``). The chain never
opens the sealed JAXA folder or the THEOS-2 files of 31 July 2025, and it refuses a Nan case unless the freeze
record and the test record exist (the order rule of the Nan protocol).
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import re
import sys
import time
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_script(name: str) -> Any:
    """Load a script of the repository as a module, once (the earlier builders are used unchanged)."""

    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"scripts/{name}.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


e10 = _load_script("build_uncertainty_ensemble")
e8 = e10.e8_builder
e5 = e8.e5_builder

import numpy as np  # noqa: E402
import shapely  # noqa: E402

from floodguard import access_diff, closure_rules, flood_inputs, planning_assessment, rights  # noqa: E402
from floodguard import nan_case_chain as nan  # noqa: E402
from floodguard import uncertainty_ensemble as ensemble  # noqa: E402
from floodguard.evidence_context import _context_content_hash  # noqa: E402
from floodguard.planning_overlay import (  # noqa: E402
    FIXTURE_KIND,
    PORTFOLIO_KIND,
    SCHEMA_RELATIVE_PATH,
    load_overlay_schema,
    overlay_text,
)

DOCS = ROOT / "docs" / "proposal_execution"
NAN_PROTOCOL = DOCS / "nan_case_protocol_v1.json"
AREAS_RECORD = ROOT / "outputs" / "nan_case" / "areas_v1.json"
FREEZE_RECORD = ROOT / "outputs" / "nan_case" / "freeze_v1.json"
TEST_RECORD = ROOT / "outputs" / "nan_case" / "test_result_v1.json"
PUBLISHED_SE1 = ROOT / "apps" / "web" / "public" / "planning-overlays" / "mae-sai-2024" / "se1.json"
RESULT_DIR_IN_GIT = ROOT / "outputs" / "nan_case"
WORK_RELATIVE = Path("proposal_execution") / "nan_case_v1" / "score_chain"
BOUNDARY_RELATIVE = Path("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
LAND_COVER_RELATIVE = Path("open_context") / "esa_worldcover" / "ESA_WorldCover_10m_2021_v200_N18E099_Map.tif"
POPULATION_2020_RELATIVE = Path("open_context") / "worldpop_population" / "tha_ppp_2020.tif"
RECORD_SCHEMA = "floodguard.nan_case_chain_record.v1"
ACCESS_SCHEMA = "floodguard.nan_case_chain_access_runs.v1"
ENSEMBLE_SCHEMA = "floodguard.nan_case_chain_ensemble.v1"
PROOF_SCHEMA = "floodguard.nan_case_chain_se1_replay.v1"
PUBLIC_SERVICES = e5.PUBLIC_SERVICES
ALTERNATE_DEMAND = e5.ALTERNATE_DEMAND
VINTAGE_2020 = e10.VINTAGE_RUN
VINTAGE_RESCALED = e10.VINTAGE_RESCALED
RESIDENT_TOLERANCE = e8.RESIDENT_TOLERANCE
EXIT_DONE, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
WATER_CLASS = 80
WATER_SOURCE = "ESA WorldCover 2021 v200"
ROUTING_BUFFER_M = 3000.0
THIRTY = str(ensemble.THIRTY_MINUTES)


class ChainError(ValueError):
    """Raised when an input of the chain is refused; nothing of a unit has been measured against the flood input."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return flood_inputs.sha256_file(path)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_of(value: Any) -> str:
    """SHA-256 of a JSON value in canonical form (the digest the ensemble receipts record)."""

    return sha256_bytes(canonical(value).encode("utf-8"))


def write_bytes(path: Path, data: bytes) -> dict[str, Any]:
    """Write a file (LF line ends, as given) and return its size and SHA-256."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"bytes": len(data), "sha256": sha256_bytes(data)}


def label(path: Path, external: Path | None) -> str:
    """Name a file without a machine path: relative to the repository, or to the external data root."""

    return e5.path_label(path, ROOT, external)


def refuse_sealed(paths: Sequence[Path | None]) -> None:
    """Refuse any input the firewall of the Nan case forbids, before anything is opened.

    Raises:
        ChainError: for a path in the sealed JAXA folder or a THEOS-2 file of 31 July 2025.
    """

    for path in paths:
        if path is None:
            continue
        why = nan.firewall_refusal(path)
        if why is not None:
            raise ChainError(why)


def code_sha256(path: Path) -> str:
    """SHA-256 of a code file as Git holds it: a checkout's CRLF line ends are read as LF."""

    return sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def code_hashes() -> dict[str, str]:
    """SHA-256 of the code a run loaded (as Git holds it): this script, the earlier builders and the modules."""

    found = {"chain_script_sha256": code_sha256(Path(__file__)),
             "e5_builder_sha256": code_sha256(ROOT / "scripts" / "build_access_diff.py"),
             "e8_builder_sha256": code_sha256(ROOT / "scripts" / "build_planning_assessment.py"),
             "e10_builder_sha256": code_sha256(ROOT / "scripts" / "build_uncertainty_ensemble.py")}
    for name in ("nan_case_chain", "planning_assessment", "uncertainty_ensemble", "planning_overlay", "normalisation",
                 "confidence", "scoring", "flood_inputs", "access_diff", "closure_rules"):
        found[f"{name}_module_sha256"] = code_sha256(ROOT / "src" / "floodguard" / f"{name}.py")
    found["line_ends"] = "LF: the bytes Git holds; a checkout's CRLF line ends are read as LF"
    return found


def software_versions() -> dict[str, str]:
    import pyproj
    import rasterio

    return {**e5.software_versions(), "rasterio": rasterio.__version__, "pyproj": pyproj.__version__,
            "python_build": platform.python_version()}


# ---------------------------------------------------------------------------
# The chain itself: the same steps for every case
# ---------------------------------------------------------------------------


@dataclass
class ChainInputs:
    """Everything the chain needs for one case, with every flood extent already in EPSG:32647.

    ``component`` holds, for each level of the flood axis the chain runs (keys of the v1b grid: ``minus``,
    ``as_provided``, ``plus``), the extent the components read, clipped to the reporting frame; ``closure`` the
    extent closure rule v1 measures roads against, clipped to the routing frame; ``c4`` the extents of confidence
    condition C4 (the flood input as provided grown and shrunk by one pixel).
    """

    case_id: str
    rules: planning_assessment.AssessmentRules
    grid: ensemble.EnsembleGrid
    case: planning_assessment.CaseSpec
    flood_spec: planning_assessment.FloodInputSpec
    access_flood_input_id: str
    units: list[tuple[str, Any]]
    names: dict[str, tuple[str, str]]
    graph: Any
    service_rules: tuple[access_diff.ServiceRule, ...]
    services: list[str]
    arguments: dict[str, Any]
    age_table: Mapping[str, Any]
    water: Any
    component: dict[str, Any]
    closure: dict[str, Any]
    c4: dict[str, Any]
    coverage: dict[str, float | None]
    by_construction: dict[str, bool]
    abstention: dict[str, float | None]
    test_iou: float | None
    routing_context_id: str
    derive: Any
    not_run: list[ensemble.LevelNotRun]
    rescaled: dict[str, float] | None
    overlay_assumptions: list[str]
    source_name: str
    generated_at: str
    git_commit: str
    timings: dict[str, float] = field(default_factory=dict)


def _clock(timings: dict[str, float], name: str, start: float) -> float:
    timings[name] = round(time.perf_counter() - start, 1)
    return time.perf_counter()


def measure(ci: ChainInputs) -> SimpleNamespace:
    """Make the access runs and measure every unit for every combination of the ensemble that is run.

    The access runs are those of the task E5 runner (``build_access_diff.case_runs``) on the baseline vehicle graph:
    each flood level under each closure level. The measurements of a unit are those task E8 and task E10 make
    (``build_planning_assessment.unit_counts_of_the_stages``, ``uncertainty_ensemble.cell_measurements``).

    Raises:
        ChainError: when an access run counts other residents for a unit than the planning context holds.
    """

    clock = time.perf_counter()
    unit_ids = [unit_id for unit_id, _geometry in ci.units]
    population = ci.graph.population
    cells = access_diff.demand_cells(population, access_diff.assign_cells(population, ci.units))
    baselines = {access_diff.VEHICLE: e5.baseline_runs(ci.graph, ci.service_rules)}
    alternate = None
    if ci.rescaled is not None:
        missing = [cell["population_id"] for cell in cells if str(cell["population_id"]) not in ci.rescaled]
        if missing:
            raise ChainError(f"the 2024-rescaled demand has no count for {len(missing)} demand cells of the context")
        alternate = {VINTAGE_RESCALED: [{**cell, "residents": float(ci.rescaled[str(cell["population_id"])])} for cell in cells]}
    closure_levels = {level: ci.closure[level] for level in flood_inputs.LEVELS if level in ci.closure}
    access = e5.case_runs(ci.case_id, ci.access_flood_input_id, closure_levels, {access_diff.VEHICLE: ci.graph}, baselines,
                          ci.service_rules, ci.arguments, cells, unit_ids, alternate_cells=alternate)
    clock = _clock(ci.timings, "access_runs", clock)
    by_key = {(run["flood_level"], run["closure_level"]): run for run in access["runs"]}
    default = by_key[(flood_inputs.AS_PROVIDED, ci.rules.reference_closure_level)]
    counted = e8.unit_counts_of_the_stages(ci.units, ci.graph, {"units": default[PUBLIC_SERVICES]["units"]}, ci.age_table,
                                           ci.services)
    frame = flood_inputs.frame_from_units(flood_inputs.REPORTING_FRAME, "the reporting units of the case", list(ci.units), {})
    inside_c4 = {level: planning_assessment.residents_by_unit(counted.cells, ci.c4[level])
                 for level in (flood_inputs.MINUS, flood_inputs.PLUS)}
    inside_level = {level: planning_assessment.residents_by_unit(counted.cells, extent) for level, extent in ci.component.items()}
    areas = {level: {unit_id: flood_inputs.flooded_land_areas(frame.units[unit_id], extent, ci.water) for unit_id in unit_ids}
             for level, extent in ci.component.items()}
    base: list[planning_assessment.UnitMeasurements] = []
    for unit_id in unit_ids:
        counts, ages = counted.access[unit_id], counted.ages[unit_id]
        name_en, name_th = ci.names[unit_id]
        here = areas[flood_inputs.AS_PROVIDED][unit_id]
        base.append(planning_assessment.UnitMeasurements(
            unit_id=unit_id, unit_name_en=name_en, unit_name_th=name_th,
            flooded_non_permanent_water_land_area=here["flooded_non_permanent_water_land_area"],
            non_permanent_water_land_area=here["non_permanent_water_land_area"],
            unit_residents=counted.residents.get(unit_id, 0.0),
            residents_inside_flood_extent={
                flood_inputs.MINUS: inside_c4[flood_inputs.MINUS].get(unit_id, 0.0),
                flood_inputs.AS_PROVIDED: inside_level[flood_inputs.AS_PROVIDED].get(unit_id, 0.0),
                flood_inputs.PLUS: inside_c4[flood_inputs.PLUS].get(unit_id, 0.0)},
            access_gap_inputs=counts["access_gap_inputs"],
            residents_losing_all_routes=counts["residents_losing_all_routes"],
            residents_with_baseline_route=counts["residents_with_baseline_route"],
            children_0_14=ages["children_0_14"], older_60_plus=ages["older_60_plus"], age_residents=ages["age_residents"],
            unit_valid_coverage=ci.coverage[unit_id], coverage_by_construction=ci.by_construction[unit_id],
            residents_connected_to_the_graph=counts["residents_connected_to_the_graph"],
            connected_residents_without_a_hospital_route=counts["connected_residents_without_a_hospital_route"],
            hospitals_reachable_at_baseline=counted.hospitals_reachable.get(unit_id, 0),
            t2_abstention_fraction=ci.abstention.get(unit_id), t2_geoid_held_out_test_iou=ci.test_iou,
        ))
    measurements: dict[Any, Any] = {}
    losing: dict[Any, Any] = {}
    differing: list[str] = []
    for run in access["runs"]:
        level = run["flood_level"]
        rows = {str(row["unit_id"]): row for row in run[PUBLIC_SERVICES]["units"]}
        listed, lost = [], {}
        for unit in base:
            counts = planning_assessment.access_counts_from_e5_row(rows[unit.unit_id], ci.services)
            if abs(counts["residents"] - unit.unit_residents) > RESIDENT_TOLERANCE or (
                    counts["residents_connected_to_the_graph"] != unit.residents_connected_to_the_graph):
                differing.append(f"{unit.unit_id} at {level}/{run['closure_level']}")
            listed.append(ensemble.cell_measurements(
                unit, flooded_non_permanent_water_land_area=areas[level][unit.unit_id]["flooded_non_permanent_water_land_area"],
                residents_inside_flood_extent=inside_level[level].get(unit.unit_id, 0.0),
                access_gap_inputs=counts["access_gap_inputs"], residents_losing_all_routes=counts["residents_losing_all_routes"],
                residents_with_baseline_route=counts["residents_with_baseline_route"]))
            lost[unit.unit_id] = {service: float(detail["thresholds_minutes"][THIRTY]["newly_lost_residents"])
                                  for service, detail in rows[unit.unit_id]["access"].items() if THIRTY in detail["thresholds_minutes"]}
        key = (level, run["closure_level"], ensemble.PUBLIC_LEVEL, VINTAGE_2020)
        measurements[key], losing[key] = listed, lost
    if ci.rescaled is not None:
        rescaled_cells = [{**cell, "residents": float(ci.rescaled[str(cell["population_id"])])} for cell in counted.cells]
        residents = planning_assessment.residents_by_unit(rescaled_cells)
        r_c4 = {level: planning_assessment.residents_by_unit(rescaled_cells, ci.c4[level]) for level in (flood_inputs.MINUS, flood_inputs.PLUS)}
        r_level = {level: planning_assessment.residents_by_unit(rescaled_cells, extent) for level, extent in ci.component.items()}
        for run in access["runs"]:
            level = run["flood_level"]
            of_2020 = measurements[(level, run["closure_level"], ensemble.PUBLIC_LEVEL, VINTAGE_2020)]
            rows = {str(row["unit_id"]): row for row in run[ALTERNATE_DEMAND][VINTAGE_RESCALED]["units"]}
            listed, lost = [], {}
            for unit in of_2020:
                counts = planning_assessment.access_counts_from_e5_row(rows[unit.unit_id], ci.services)
                total = residents.get(unit.unit_id, 0.0)
                if abs(counts["residents"] - total) > RESIDENT_TOLERANCE:
                    differing.append(f"{unit.unit_id} at {level}/{run['closure_level']} (rescaled)")
                rescaled_unit = replace(
                    unit, unit_residents=total,
                    residents_inside_flood_extent={flood_inputs.MINUS: r_c4[flood_inputs.MINUS].get(unit.unit_id, 0.0),
                                                   flood_inputs.AS_PROVIDED: r_level[flood_inputs.AS_PROVIDED].get(unit.unit_id, 0.0),
                                                   flood_inputs.PLUS: r_c4[flood_inputs.PLUS].get(unit.unit_id, 0.0)},
                    residents_connected_to_the_graph=counts["residents_connected_to_the_graph"],
                    connected_residents_without_a_hospital_route=counts["connected_residents_without_a_hospital_route"])
                listed.append(ensemble.cell_measurements(
                    rescaled_unit, flooded_non_permanent_water_land_area=unit.flooded_non_permanent_water_land_area,
                    residents_inside_flood_extent=r_level[level].get(unit.unit_id, 0.0),
                    access_gap_inputs=counts["access_gap_inputs"], residents_losing_all_routes=counts["residents_losing_all_routes"],
                    residents_with_baseline_route=counts["residents_with_baseline_route"]))
                lost[unit.unit_id] = {service: float(detail["thresholds_minutes"][THIRTY]["newly_lost_residents"])
                                      for service, detail in rows[unit.unit_id]["access"].items() if THIRTY in detail["thresholds_minutes"]}
            key = (level, run["closure_level"], ensemble.PUBLIC_LEVEL, VINTAGE_RESCALED)
            measurements[key], losing[key] = listed, lost
    if differing:
        raise ChainError(f"guardrail GR3: an access run counts other residents for a unit than the planning context: {differing[:5]}")
    _clock(ci.timings, "units_measured", clock)
    return SimpleNamespace(cells=cells, access=access, counted=counted, base=base, measurements=measurements, losing=losing,
                           areas=areas, inside_level=inside_level, default_run=default, frame=frame)


def assess(ci: ChainInputs, measured: SimpleNamespace, inputs: Sequence[Mapping[str, Any]]) -> SimpleNamespace:
    """Assemble the rows of the default cell, check them, and run the ensemble over every combination measured."""

    clock = time.perf_counter()
    unit_ids = [unit_id for unit_id, _geometry in ci.units]
    closure = planning_assessment.ClosureSpec(closure_rules.CLOSURE_RULE_VERSION, ci.rules.reference_closure_level)
    overlay = planning_assessment.assemble_overlay(
        ci.rules, ci.case, ci.flood_spec, closure, measured.base, list(inputs), routing_context_id=ci.routing_context_id,
        generated_at=ci.generated_at, git_commit=ci.git_commit, source_name=ci.source_name,
        assumptions=ci.overlay_assumptions, derive=ci.derive)
    guardrails = planning_assessment.guardrail_report(overlay, ci.rules, reporting_units=unit_ids, lane=ci.case.lane)
    counted_by_the_runs = math.fsum(float(row["residents"]) for row in measured.default_run[PUBLIC_SERVICES]["units"]
                                    if str(row["unit_id"]) in set(unit_ids))
    whole_case = planning_assessment.whole_case_checks(overlay["rows"], overlay["scoring_frame"],
                                                       residents_counted_by_the_access_table=counted_by_the_runs,
                                                       resident_tolerance=RESIDENT_TOLERANCE)
    clock = _clock(ci.timings, "rows_assembled_and_checked", clock)
    result = ensemble.run_ensemble(ci.grid, ci.rules, ci.case, ci.flood_spec, measured.measurements,
                                   routing_context_id=ci.routing_context_id, level=ensemble.PUBLIC_LEVEL, not_run=ci.not_run,
                                   people_losing_access=measured.losing, derive=ci.derive)
    _clock(ci.timings, "ensemble", clock)

    def comparable(rows: Sequence[Mapping[str, Any]]) -> str:
        return e8.rows_sha256([{key: value for key, value in row.items() if key not in ("assumptions", "headline_stability")}
                               for row in rows])

    return SimpleNamespace(
        overlay=overlay, guardrails=guardrails, whole_case=whole_case, ensemble=result,
        default_cell_is_the_row=e8.rows_sha256(result["reference_rows"]) == e8.rows_sha256(overlay["rows"]),
        default_cell_is_the_row_but_text=comparable(result["reference_rows"]) == comparable(overlay["rows"]))


def access_runs_document(ci: ChainInputs, measured: SimpleNamespace, *, external: Path | None, extra: Mapping[str, Any] | None = None
                         ) -> dict[str, Any]:
    """The unit rows and closure counts of every access run of the chain, for the work folder (counts, no ratio)."""

    return {
        "schema_version": ACCESS_SCHEMA,
        "case_id": ci.case_id,
        "generated_at_utc": ci.generated_at,
        "source_timestamp": ci.flood_spec.source_instant,
        "confidence_class": "low",
        "confidence_basis": "Modelled access on OpenStreetMap roads under closures assumed from the flood input; no "
                            "closure, route or count was checked on the ground.",
        "assumptions": list(e5.ASSUMPTIONS[:1]) + [
            "Counts of residents only; no ratio of two counts is written. These are inputs of the access-gap and "
            "road-criticality components, not the components."],
        "official_warning": False,
        "operational_status": "non_operational",
        "closure_basis_input": ci.access_flood_input_id,
        "runs": [{"flood_level": run["flood_level"], "closure_level": run["closure_level"], "closure_basis": run["closure_basis"],
                  "closure": run["closure"], PUBLIC_SERVICES: run[PUBLIC_SERVICES],
                  **({ALTERNATE_DEMAND: run[ALTERNATE_DEMAND]} if ALTERNATE_DEMAND in run else {})}
                 for run in measured.access["runs"]],
        "checks": measured.access["checks"],
        **(dict(extra) if extra else {}),
    }


# ---------------------------------------------------------------------------
# Mode 1: the proof on case SE1's own inputs
# ---------------------------------------------------------------------------


def se1_replay(external: Path, *, age_dir: Path | None, work_dir: Path) -> dict[str, Any]:
    """Run the chain on the inputs of case SE1 and compare what it gives with the published and registered results.

    The inputs are read and checked by the registered builders' own input checks (``build_uncertainty_ensemble.prepare``,
    which makes every check of the task E8 builder first). The chain then makes its own access runs, rows and
    ensemble. Compared: the rows with the published file ``apps/web/public/planning-overlays/mae-sai-2024/se1.json``
    and with the SHA-256 of the rows the registered task E8 receipt records; the whole file, byte for byte, with the
    header of the published file; the access runs at the flood level as provided with the registered task E5 table;
    and the ensemble with the registered task E10 receipt (the SHA-256 of the per-unit results, the summary and the
    access unit rows).
    """

    started = e5.utc_now()
    frame_set = e8.FRAME_SETS["mae_sai"]
    boundaries = external / BOUNDARY_RELATIVE
    found = e10.prepare("SE1", frame_set, external, boundaries, age_dir=age_dir)
    published_bytes = PUBLISHED_SE1.read_bytes()
    published = json.loads(published_bytes.decode("ascii"))
    record = found.record
    assumptions = [
        *e8.ASSUMPTIONS,
        f"The flood input is written as '{found.flood_spec.input_id}' in this file; task E1 names it '{record['input_id']}'. "
        "The closure basis of a row names the same input.",
        "The rights level of this file is the minimum across its lineage (guardrail GR6). An input with no rights "
        "record states the level its row gives, with the basis in the run receipt (open point E8-OP5).",
    ]
    for key in ("standard_sentence", "label"):
        if isinstance(record.get(key), str) and record[key].strip():
            assumptions.append(f"The flood input: {record[key]}")
    unit_ids = list(found.unit_ids)
    ci = ChainInputs(
        case_id="SE1", rules=found.rules, grid=found.grid, case=found.case, flood_spec=found.flood_spec,
        access_flood_input_id=str(record["input_id"]), units=list(found.units), names=dict(found.names), graph=found.graph,
        service_rules=access_diff.service_rules(json.loads(found.v1a_path.read_text(encoding="utf-8")),
                                                json.loads(found.v1b_path.read_text(encoding="utf-8"))),
        services=list(found.services),
        arguments=access_diff.closure_arguments(json.loads(found.v1b_path.read_text(encoding="utf-8"))),
        age_table=found.age_table, water=found.flood.water, component=dict(found.flood.extents),
        closure=dict(found.closure_extents),
        c4={level: found.flood.extents[level] for level in (flood_inputs.MINUS, flood_inputs.PLUS)},
        coverage={unit_id: None for unit_id in unit_ids},
        by_construction={unit_id: planning_assessment.coverage_by_construction_applies(
            found.rules.binding.rule, unit_id=unit_id, flood_input=found.flood_spec.name) for unit_id in unit_ids},
        abstention={}, test_iou=None, routing_context_id=found.context_id, derive=None, not_run=list(found.not_run),
        rescaled=None if found.rescaled is None else dict(found.rescaled.by_cell),
        overlay_assumptions=assumptions,
        source_name=f"FloodGuard planning assessment overlay: case SE1, {frame_set.title}",
        generated_at=str(published["generated_at"]), git_commit=str(published["git_commit"]))
    if any(ci.coverage[unit_id] is None and not ci.by_construction[unit_id] for unit_id in unit_ids):
        raise ChainError("case SE1 has coverage by construction in every unit (protocol v1a); a unit lacks it")
    measured = measure(ci)
    assessed = assess(ci, measured, found.inputs)
    rows = assessed.overlay["rows"]
    schema = load_overlay_schema(ROOT / SCHEMA_RELATIVE_PATH)
    text = overlay_text(assessed.overlay, schema, binding=found.rules.binding)
    e10_receipt = json.loads((e8.OUTPUT_DIR / "e10_uncertainty_ensemble_se1_mae_sai.json").read_text(encoding="ascii"))
    e8_rows_sha256 = found.e8_run["rows_sha256"]
    try:
        access_check = e10.check_as_provided_runs(measured.access["runs"], found.access_table)
    except e10.StageError as error:
        access_check = {"result": "FAIL", "message": str(error)}
    units_digest = digest_of(assessed.ensemble["units"])
    access_rows_digest = digest_of([{"flood_level": run["flood_level"], "closure_level": run["closure_level"],
                                     "units": run[PUBLIC_SERVICES]["units"]} for run in measured.access["runs"]])
    registered = e10_receipt["result"]
    summary_same = canonical(assessed.ensemble["summary"]) == canonical(registered["summary"])
    differing_summary = sorted(key for key in {*assessed.ensemble["summary"], *registered["summary"]}
                               if canonical(assessed.ensemble["summary"].get(key)) != canonical(registered["summary"].get(key)))
    published_rows = published["rows"]
    row_fields = sorted({key for row in rows for key in row})
    differing_rows = [row["unit_id"] for row, other in zip(rows, published_rows) if canonical(row) != canonical(other)]
    comparison = {
        "rows": {
            "published_file": {"path": label(PUBLISHED_SE1, external), "sha256": sha256_bytes(published_bytes),
                               "bytes": len(published_bytes)},
            "rows": len(rows),
            "rows_same_as_the_published_file": canonical(rows) == canonical(published_rows),
            "rows_that_differ": differing_rows,
            "rows_sha256_of_the_chain": e8.rows_sha256(rows),
            "rows_sha256_the_registered_e8_receipt_records": e8_rows_sha256,
            "rows_sha256_same": e8.rows_sha256(rows) == e8_rows_sha256,
            "fields_compared": row_fields,
            "whole_file_with_the_published_header": {
                "sha256": sha256_bytes(text.encode("ascii")), "bytes": len(text.encode("ascii")),
                "same_bytes_as_the_published_file": text.encode("ascii") == published_bytes},
            "per_row": [{"unit_id": row["unit_id"], "fpps_0_100": row["fpps_0_100"], "action_class": row["action_class"],
                         "action_reason_code": row["action_reason_code"], "confidence_class": row["confidence"]["confidence_class"],
                         "same_as_published": canonical(row) == canonical(other)}
                        for row, other in zip(rows, published_rows)],
        },
        "access_runs": {
            "as_provided_runs_against_the_registered_e5_table": access_check,
            "unit_rows_sha256_of_the_chain": access_rows_digest,
            "unit_rows_sha256_the_registered_e10_receipt_records": (e10_receipt.get("access_runs") or {}).get("unit_rows_sha256"),
            "same": access_rows_digest == (e10_receipt.get("access_runs") or {}).get("unit_rows_sha256"),
            "runs": len(measured.access["runs"]),
        },
        "ensemble": {
            "cells_run": assessed.ensemble["summary"]["cells_run"],
            "units_sha256_of_the_chain": units_digest,
            "units_sha256_the_registered_e10_receipt_records": registered.get("units_sha256"),
            "units_same": units_digest == registered.get("units_sha256"),
            "summary_same_as_the_registered_e10_receipt": summary_same,
            "summary_fields_that_differ": differing_summary,
            "default_cell_is_the_row": assessed.default_cell_is_the_row,
            "headline_status_counts": assessed.ensemble["summary"]["headline_status_counts"],
            "class_counts_over_every_unit_cell": assessed.ensemble["summary"]["class_counts_over_every_unit_cell"],
            "rescaled_demand_built": ci.rescaled is not None,
        },
        "guardrails": assessed.guardrails,
        "whole_case_checks": assessed.whole_case,
    }
    proof = {
        "schema_version": PROOF_SCHEMA,
        "what": "The score chain of the Nan case run on case SE1's own inputs, to show that it reproduces the published "
                "SE1 rows and the registered SE1 ensemble. Every input was read through the input checks of the "
                "registered builders. Nothing was written in Git.",
        "generated_at_utc": started,
        "source_timestamp": str(record["source_timestamp"]),
        "confidence_class": "low",
        "confidence_basis": "A reproduction check of code, not a statement about any place: it compares two runs of the "
                            "same modelled chain on the same inputs.",
        "assumptions": [
            "Case SE1 is the 2024 season envelope scenario: every area ever mapped as water in the season is treated as "
            "flooded at once. A reproduction of its rows says nothing new about Mae Sai.",
            "The chain made its own access runs, rows and ensemble; the earlier receipts were read for the comparison only.",
        ],
        "official_warning": False,
        "operational_status": "non_operational",
        "protocol_sha256": found.hashes,
        "inputs": {"e8_receipt_rows_sha256": e8_rows_sha256, "e10_receipt": {
            "path": "outputs/planning_v1/e10_uncertainty_ensemble_se1_mae_sai.json",
            "sha256": sha256_file(e8.OUTPUT_DIR / "e10_uncertainty_ensemble_se1_mae_sai.json")},
            "age_dir_given": age_dir is not None},
        "comparison": comparison,
        "all_same": bool(comparison["rows"]["rows_same_as_the_published_file"] and comparison["rows"]["rows_sha256_same"]
                         and access_check.get("result") == "PASS" and comparison["access_runs"]["same"]
                         and comparison["ensemble"]["units_same"] and summary_same and assessed.default_cell_is_the_row),
        "implementation": {**code_hashes(), "software": software_versions()},
        "timing_seconds": dict(ci.timings),
    }
    target = work_dir / "se1_replay" / "se1_replay_proof.json"
    written = write_bytes(target, e8.encode(proof))
    overlay_copy = work_dir / "se1_replay" / "se1_replay_result_file.json"
    write_bytes(overlay_copy, text.encode("ascii"))
    return {"proof": label(target, external), **written, "all_same": proof["all_same"],
            "rows_same": comparison["rows"]["rows_same_as_the_published_file"],
            "file_bytes_same": comparison["rows"]["whole_file_with_the_published_header"]["same_bytes_as_the_published_file"],
            "ensemble_units_same": comparison["ensemble"]["units_same"], "summary_same": summary_same,
            "access_same": comparison["access_runs"]["same"], "timing_seconds": ci.timings}


# ---------------------------------------------------------------------------
# Mode 2: a Nan case
# ---------------------------------------------------------------------------


CASE_TITLES: Mapping[str, tuple[str, str]] = {
    "N1": ("Case N1: own radar flood map (M1-z), Nan, Mueang Nan, Phu Phiang and Wiang Sa (35 tambons)",
           "กรณี N1: แผนที่น้ำท่วมจากเรดาร์ของ FloodGuard (M1-z) จังหวัดน่าน อำเภอเมืองน่าน ภูเพียง และเวียงสา (35 ตำบล)"),
    "N2": ("Case N2: the test 1 reference map as provided, Nan, Mueang Nan, Phu Phiang and Wiang Sa (35 tambons)",
           "กรณี N2: แผนที่อ้างอิงของการทดสอบที่ 1 ตามที่ได้รับ จังหวัดน่าน อำเภอเมืองน่าน ภูเพียง และเวียงสา (35 ตำบล)"),
}
"""The titles of the two Nan cases. The Thai titles were written by the AI agent and are not native-reviewed."""
CASE_TIERS: Mapping[str, str] = {"N1": "T2", "N2": "T3"}


@dataclass
class NanArguments:
    """What a Nan run is given on the command line (or by a test)."""

    case_id: str
    external: Path
    context: Path
    flood: dict[str, Path]
    flood_input_id: str
    flood_name: str
    acquisition_date: date
    source_instant: str
    outcome: nan.CaseOutcome
    boundaries: Path
    land_cover: Path
    routing_geometry: Path | None = None
    age_table: Path | None = None
    age_dir: Path | None = None
    rescaled_population: Path | None = None
    build_rescaled_demand: bool = False
    out_dir: Path | None = None
    work_dir: Path | None = None
    sensitivity: bool = True
    fixture: bool = False
    unit_ids: tuple[str, ...] = ()
    unit_layer: str | None = "tha_admin3"
    unit_id_field: str = "adm3_pcode"
    unit_name_en_field: str = "adm3_name"
    unit_name_th_field: str = "adm3_name1"
    unit_district_field: str = "adm2_pcode"
    grid: nan.RasterGrid | None = None
    git_commit: str | None = None
    generated_at: str | None = None
    docs: Path = DOCS
    test_result: Mapping[str, Any] | None = None


def read_flood_raster(path: Path, grid: nan.RasterGrid, level: str = "central") -> tuple[np.ndarray, dict[str, Any]]:
    """Read one flood map and check it against the frame's grid and the three codes.

    A one-band raster is the map itself. A raster of several bands is a map of the method lane
    (``scripts/nan_case_method.py maps``: bands ``code_lower``, ``code_central``, ``code_upper`` and the central
    reasons); the band named ``code_<level>`` is read.

    Raises:
        ChainError: for another coordinate system, another grid, no band of the level, or another code.
    """

    import rasterio

    with rasterio.open(path) as source:
        if source.crs is None or source.crs.to_epsg() != grid.epsg:
            raise ChainError(f"{path.name}: a flood map of the case is in EPSG:{grid.epsg}")
        expected = grid.transform
        if (source.width, source.height) != (grid.cols, grid.rows) or any(
                abs(a - b) > 1e-6 for a, b in zip(tuple(source.transform)[:6], tuple(expected)[:6])):
            raise ChainError(f"{path.name}: the raster is not on the frame's grid {grid.as_record()}")
        band = 1
        if source.count > 1:
            names = list(source.descriptions)
            wanted = f"code_{level}"
            if wanted not in names:
                raise ChainError(f"{path.name}: a map of several bands holds a band named {wanted}; it holds {names}")
            band = names.index(wanted) + 1
        values = source.read(band)
        nodata = source.nodata
    try:
        counts = nan.check_flood_values(values, grid)
    except nan.NanChainError as error:
        raise ChainError(f"{path.name}: {error}") from error
    return values, {"file": path.name, "band": band, "sha256": sha256_file(path), "bytes": path.stat().st_size,
                    "nodata_tag": nodata, "cell_counts": counts}


def outcome_from_test_result(path: Path, external: Path) -> tuple[nan.CaseOutcome, dict[str, Any]]:
    """Read the case-level outcome and the flood input of case N1 from the test record of the method lane.

    ``outputs/nan_case/test_result_v1.json`` (``scripts/nan_case_method.py test``): ``binding.test_1_passes``,
    ``binding.dry_control_passes``, ``binding.case_reference_date``, ``test_1.central.iou_no_answer_as_not_flagged``,
    ``test_1.reference`` and ``binding.flood_input_of_case_N1`` (the pass and its map in the maps folder).

    Raises:
        ChainError: when the record does not hold these fields, or the map it names is missing or has other bytes.
    """

    record = json.loads(path.read_text(encoding="utf-8"))
    try:
        binding = record["binding"]
        test_1 = record["test_1"]
        central = test_1.get("central") or {}
        reference_date = date.fromisoformat(str(binding["case_reference_date"]))
        flood_input = binding["flood_input_of_case_N1"]
        outcome = nan.CaseOutcome(test_1_passed=bool(binding["test_1_passes"]), dry_control_passed=bool(binding["dry_control_passes"]),
                                  test_1_iou=central.get("iou_no_answer_as_not_flagged"),
                                  reference=str(test_1.get("reference") or "the test 1 reference"),
                                  case_reference_date=reference_date, fallback=reference_date == date(2025, 7, 31))
    except (KeyError, TypeError, ValueError) as error:
        raise ChainError(f"the test record does not hold the binding outcome of the case: {error!r}") from error
    found: dict[str, Any] = {"test_result": {"path": label(path, external), "sha256": sha256_file(path)}, "flood_input": flood_input}
    if isinstance(flood_input, Mapping) and isinstance(flood_input.get("map"), Mapping):
        map_path = external / "proposal_execution" / "nan_case_v1" / "method" / "maps" / str(flood_input["map"]["name"])
        if not map_path.is_file() or sha256_file(map_path) != flood_input["map"].get("sha256"):
            raise ChainError(f"the map of the flood input, {map_path.name}, is missing or is not the file the test record names")
        found["map_path"] = map_path
    return outcome, found


def read_units(arguments: NanArguments, districts: Sequence[str]) -> tuple[list[tuple[str, Any]], dict[str, tuple[str, str]], dict[str, Any]]:
    """Read the tambons of the frame and their names (COD-AB ``tha_admin3``, or the fields a fixture names)."""

    import pyogrio

    columns = [arguments.unit_id_field, arguments.unit_name_en_field, arguments.unit_name_th_field]
    if not arguments.fixture:
        columns += [arguments.unit_district_field, "lang1"]
    table = pyogrio.read_dataframe(arguments.boundaries, layer=arguments.unit_layer, columns=columns)
    if table.crs is None or table.crs.to_epsg() != 4326:
        raise ChainError("the boundary layer must be EPSG:4326")
    if arguments.fixture:
        table = table[table[arguments.unit_id_field].astype(str).isin(set(arguments.unit_ids))] if arguments.unit_ids else table
    else:
        table = table[table[arguments.unit_district_field].astype(str).isin(set(districts))]
        if set(table["lang1"].astype(str)) != {"th"}:
            raise ChainError(f"the boundary layer does not say that {arguments.unit_name_th_field} is the Thai name")
    found = sorted((str(code), geometry) for code, geometry in zip(table[arguments.unit_id_field], table.geometry))
    identifiers = [code for code, _geometry in found]
    if not found or len(set(identifiers)) != len(identifiers):
        raise ChainError("the boundary layer does not hold the units of the frame, each once")
    names = {str(row[arguments.unit_id_field]): (str(row[arguments.unit_name_en_field]), str(row[arguments.unit_name_th_field]))
             for _index, row in table.iterrows()}
    by_district = {}
    if not arguments.fixture:
        by_district = {district: int((table[arguments.unit_district_field].astype(str) == district).sum()) for district in districts}
    return found, names, {"units": len(found), "by_district": by_district, "layer": arguments.unit_layer,
                          "unit_id_field": arguments.unit_id_field}


def routing_frame(units: Sequence[tuple[str, Any]], arguments: NanArguments) -> tuple[flood_inputs.Frame, dict[str, Any]]:
    """The routing frame: the given routing geometry, or the units' union buffered by 3 km (the SE2 frame rule)."""

    import pyogrio

    if arguments.routing_geometry is not None:
        table = pyogrio.read_dataframe(arguments.routing_geometry)
        if table.crs is None or table.crs.to_epsg() != 4326:
            raise ChainError("the routing geometry must be EPSG:4326")
        geometry = shapely.union_all(np.array(list(table.geometry), dtype=object))
        frame = flood_inputs.frame_from_wgs84(flood_inputs.ROUTING_CONTEXT, "the routing geometry of the frame", geometry, {})
        return frame, {"source": "given", "path": label(arguments.routing_geometry, arguments.external),
                       "sha256": sha256_file(arguments.routing_geometry), "area_km2": round(frame.area_m2 / 1e6, 3)}
    reporting = flood_inputs.frame_from_units(flood_inputs.REPORTING_FRAME, "the units of the frame", list(units), {})
    buffered = flood_inputs.as_multipolygon(reporting.geometry.buffer(ROUTING_BUFFER_M, quad_segs=flood_inputs.BUFFER_QUAD_SEGS))
    rule = "the union of the units buffered by 3,000 m in EPSG:32647 (16 segments per quarter circle)"
    if not arguments.fixture:
        try:
            country = pyogrio.read_dataframe(arguments.boundaries, layer="tha_admin0")
            land = flood_inputs.as_multipolygon(flood_inputs.project(
                flood_inputs.as_multipolygon(shapely.make_valid(shapely.union_all(np.array(list(country.geometry), dtype=object)))),
                flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS))
            buffered = flood_inputs.as_multipolygon(shapely.intersection(buffered, land))
            rule += ", intersected with the COD-AB tha_admin0 polygon of Thailand"
        except Exception as error:  # noqa: BLE001 - the layer is optional; the record says which rule was applied
            rule += f" (tha_admin0 could not be read: {type(error).__name__}; not intersected)"
    frame = flood_inputs.Frame(flood_inputs.ROUTING_CONTEXT, "the routing geometry of the frame", buffered, {})
    return frame, {"source": "computed", "rule": rule, "area_km2": round(frame.area_m2 / 1e6, 3)}


def load_context(path: Path, external: Path) -> tuple[Any, dict[str, Any]]:
    """Read the frame's planning context and build its baseline vehicle graph; its canonical SHA-256 must hold."""

    context = json.loads(path.read_bytes().decode("utf-8"))
    canonical_sha256 = _context_content_hash(context)
    if context.get("canonical_sha256") != canonical_sha256:
        raise ChainError("the planning context does not have the canonical SHA-256 it states")
    try:
        graph = e5.mode_graph(access_diff.VEHICLE, context)
    except e5.BuildError as error:
        raise ChainError(str(error)) from error
    metadata = context.get("source_metadata") or {}
    record = {"path": label(path, external), "file_sha256": sha256_file(path), "canonical_sha256": canonical_sha256,
              "generated_at": context.get("generated_at"), "graph": graph.record,
              "osm_retrieved_at_utc": (metadata.get("osm") or {}).get("retrieved_at_utc") if isinstance(metadata, Mapping) else None,
              "input_hashes": dict(context.get("input_hashes") or {})}
    return graph, record


def load_age_table(arguments: NanArguments, units: Sequence[tuple[str, Any]], work_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """The age counts of each unit: a table given (the format of task E7), or computed from the age rasters."""

    if arguments.age_table is not None:
        data = arguments.age_table.read_bytes()
        table = json.loads(data.decode("utf-8"))
        return table, {"source": "given", "path": label(arguments.age_table, arguments.external), "sha256": sha256_bytes(data),
                       "source_timestamp": table.get("source_timestamp")}
    if arguments.age_dir is None:
        raise ChainError("the vulnerability component needs the age counts of each unit: give --age-table or --age-dir")
    from floodguard import age_exposure

    v1b = json.loads((arguments.docs / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    manifest_sha = v1b["national_vulnerability_anchors"]["inputs"]["age_rasters"]["manifest_sha256"]
    manifest, paths, _hashes = e10._load_script("build_national_vulnerability_anchors").check_age_sources(arguments.age_dir, manifest_sha)
    rows = age_exposure.age_exposure_table(list(units), paths)
    table = {"schema_version": "floodguard.age_exposure.v1", "what": "Age counts of each unit, computed by the score chain "
             "with floodguard.age_exposure (the code of task E7 and of the national anchors).",
             "source_timestamp": str(manifest.get("year_represented", "2024")), "units": rows,
             "official_warning": False, "operational_status": "non_operational", "confidence_class": "low",
             "assumptions": [age_exposure.ALLOCATION_STATEMENT]}
    data = e8.encode(table)
    target = work_dir / f"age_table_{arguments.case_id.lower()}.json"
    written = write_bytes(target, data)
    return table, {"source": "computed", "path": label(target, arguments.external), **written,
                   "age_manifest_sha256": manifest_sha, "source_timestamp": table["source_timestamp"]}


def load_rescaled(arguments: NanArguments, graph: Any, v1b_path: Path) -> tuple[dict[str, float] | None, dict[str, Any]]:
    """The 2024-rescaled demand: given by the frame lane, built with the rescale builder of task E10, or dropped."""

    if arguments.rescaled_population is not None:
        data = arguments.rescaled_population.read_bytes()
        loaded = json.loads(data.decode("utf-8"))
        by_cell = loaded.get("by_cell", loaded) if isinstance(loaded, Mapping) else None
        if not isinstance(by_cell, Mapping):
            raise ChainError("the rescaled demand is a mapping of population_id to residents (or holds one under by_cell)")
        return {str(key): float(value) for key, value in by_cell.items()}, {
            "source": "given", "path": label(arguments.rescaled_population, arguments.external), "sha256": sha256_bytes(data)}
    if arguments.build_rescaled_demand:
        if arguments.age_dir is None:
            raise ChainError("--build-rescaled-demand needs --age-dir")
        population = arguments.external / POPULATION_2020_RELATIVE
        found = SimpleNamespace(v1b_path=v1b_path, graph=graph,
                                inputs=[{"input_id": "worldpop_2020_100m", "sha256": sha256_file(population)}])
        by_cell, record = e10.rescaled_residents(found, arguments.external, arguments.age_dir)
        return by_cell, {"source": "built with build_uncertainty_ensemble.rescaled_residents (decision log R38, R39)", **record}
    return None, {"source": "not given", "consequence": "the population axis is dropped: the Nan ensemble has 90 cells "
                                                        "(nan_case_protocol_v1, ensemble.population)"}


def lineage_inputs(arguments: NanArguments, *, tier: str, fallback: bool, flood_record: Mapping[str, Any], context_record: Mapping[str, Any],
                   boundary_sha256: str, water_record: Mapping[str, Any], age_record: Mapping[str, Any],
                   anchors_sha256: str, anchors_timestamp: str, access_sha256: str, population_sha256: str | None
                   ) -> list[dict[str, Any]]:
    """The lineage input records of the result file (overlay schema ``input``), each with its SHA-256 and rights level.

    Case N1's flood input is the project's own map from Copernicus Sentinel-1 data: open data, public level (the
    Nan protocol allows its figures and per-tambon tables in Git). No Sentinel-1 rights record is registered
    (open point E1-OP2), and the record says so. Case N2's flood input is the test 1 reference map as provided:
    local level (its per-tambon results stay in the work folder).
    """

    own = tier == "T2"
    flood_change = (
        "Derived by FloodGuard: Sentinel-1 RTC gamma0 (Microsoft Planetary Computer) flagged by the frozen M1-z method of "
        "the Nan case on the frame's 20 m grid; in the score chain the flagged cells were polygonised, closure rule v1 "
        "was applied to the roads, and the flooded share of each tambon's land outside permanent water, the share of its "
        "residents inside the flagged cells and its access counts were turned into the components of planning frame v1. "
        "This file holds values derived from the map, not the map." if own else
        "Rasterised by cell centre onto the frame's 20 m grid by the test stage of the Nan case (cells outside the "
        "observed area: no answer); in the score chain the flagged cells were polygonised and put through the same "
        "chain. This file holds values derived from the map, not the map.")
    licence = ("Copernicus Sentinel data, free, full and open access (Copernicus data policy)" if own else
               "Used under the terms of its provider for scientific and disaster-management use; not redistributed")
    attribution = ("Contains modified Copernicus Sentinel data (2025), processed by FloodGuard" if own else
                   "Copernicus Emergency Management Service, Global Flood Monitoring (GFM); used as provided" if fallback else
                   "Provided by JAXA; used as provided")
    level = rights.PUBLIC_LEVEL if own else rights.LOCAL_LEVEL

    def item(input_id: str, role: str, name: str, sha256: str, rights_level: str, licence_text: str, credit: str,
             source_timestamp: str, *, acquisition_date: str | None = None, change_notice: str | None = None) -> dict[str, Any]:
        return {"input_id": input_id, "role": role, "name": name, "source_product": None, "acquisition_date": acquisition_date,
                "sha256": sha256, "rights_level": rights_level, "licence": licence_text, "attribution": credit,
                "change_notice": change_notice, "source_timestamp": source_timestamp}

    return [
        item(arguments.flood_input_id, "flood_input", arguments.flood_name, str(flood_record["sha256"]), level, licence,
             attribution, arguments.source_instant, acquisition_date=arguments.acquisition_date.isoformat(),
             change_notice=flood_change),
        item("nan_planning_context_vehicle", "routing_context",
             "Planning context of the Nan frame, vehicle mode: OpenStreetMap roads and hospitals, WorldPop 2020 demand cells",
             str(context_record["canonical_sha256"]), rights.PUBLIC_LEVEL, "ODbL 1.0 (roads and hospitals); CC BY 4.0 (demand cells)",
             "(c) OpenStreetMap contributors; WorldPop (www.worldpop.org), University of Southampton",
             f"OpenStreetMap retrieved {context_record.get('osm_retrieved_at_utc')}; population year 2020"),
        item("worldpop_2020_100m", "population", "WorldPop Thailand 100 m population 2020 (tha_ppp_2020.tif)",
             str(population_sha256 or context_record["canonical_sha256"]), rights.PUBLIC_LEVEL, "CC BY 4.0",
             "WorldPop (www.worldpop.org), University of Southampton", "2020"),
        item("unit_boundaries", "boundaries", "HDX Thailand COD-AB subdistrict boundaries (tha_admin3)", boundary_sha256,
             rights.PUBLIC_LEVEL, "CC BY-IGO", "OCHA / HDX Thailand COD-AB", "see the boundary file"),
        item("nan_permanent_water", "permanent_water",
             "Permanent water of the reporting frame: ESA WorldCover 2021 v200, class 80", str(water_record["sha256"]),
             rights.PUBLIC_LEVEL, "CC BY 4.0",
             "ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium",
             "2021", change_notice="The footprint of every class-80 cell, projected to EPSG:32647 and clipped to the reporting frame."),
        item("nan_age_counts", "age_structure", "Age counts per unit: WorldPop Global2 R2025A v1, 2024, 1 km constrained age counts",
             str(age_record["sha256"]), rights.PUBLIC_LEVEL, "CC BY 4.0", "WorldPop (www.worldpop.org), University of Southampton",
             str(age_record.get("source_timestamp") or "2024")),
        item("nan_access_runs", "other", "Access runs of the score chain: resident counts per unit under closure rule v1",
             access_sha256, level, licence, attribution, arguments.source_instant,
             change_notice="Counts of residents per unit with and without the closures the flood input gives; no ratio."),
        item("national_vulnerability_anchors", "other", "National vulnerability anchors of protocol v1b (constants for all of Thailand)",
             anchors_sha256, rights.PUBLIC_LEVEL, "CC BY 4.0 (derived constants)",
             "WorldPop (www.worldpop.org), University of Southampton; HDX Thailand COD-AB", anchors_timestamp),
    ]


def nan_assumptions(tier: str, *, one_pixel_m: float, minimum_px: int, cells: int) -> list[str]:
    """The assumptions of a Nan result file, beyond those the assembly adds."""

    own = tier == "T2"
    return [
        "A closure is a modelled assumption of closure rule v1 (closure_basis), not an observed closure. A flood "
        "intersection does not prove that a road was closed.",
        ("The flood input is the project's own radar flood map (M1-z, frozen before the test; tier T2), a candidate map "
         "used as computed. Every figure of the case is agreement with a reference layer, not accuracy." if own else
         "The flood input is the test 1 reference map as provided (tier T3), rasterised by cell centre onto the frame's "
         "grid; FloodGuard did not check it on the ground."),
        "In the binding chain a no-answer cell (code 255) counts as not flagged, as test 1 counts it. The run record "
        "gives, per tambon, the no-answer share of the land outside permanent water, the residents in no-answer cells "
        "and the vehicle edges crossing them, and a sensitivity run of this cell with no-answer counted as flagged.",
        "Residents are modelled WorldPop 2020 counts. A cell counts for the unit whose polygon holds its centre, and a "
        "resident is inside the flood extent when the cell centre lies in a flagged cell (the extent covers the point).",
        "Flood likelihood is measured on the unit's land outside permanent water (the footprints of the ESA WorldCover "
        "2021 class-80 cells), by polygon overlay in EPSG:32647, with the footprints of the flagged 20 m cells.",
        f"Confidence condition C4 compares the exposure with the flood input grown and shrunk by {one_pixel_m:g} m (one "
        "pixel, owner choice 2 of protocol v1b). The lower and upper maps are the flood axis of the ensemble, not C4.",
        f"Closure rule v1 measures roads against the flagged cells; for a tier T2 raster, polygons under {minimum_px} "
        f"cells (8-connected; open point E1-OP6) are dropped first (protocol v1b raster_minimum_polygon_px).",
        ("Confidence is rule v1 with the binding rule of the Nan protocol in the place of the T2 skill condition behind "
         "C1 (the case-level test outcome, the tambon's no-answer share, the share of its land with an answer, and the "
         "days from the pass to the case reference date); C2 to C8 are rule v1 as written." if own else
         "Confidence is rule v1 as written for an agency extent used as provided; C3 is the share of the tambon's land "
         "inside the observed area of the map."),
        "The access gap and the road criticality are computed from the resident counts of the access runs of the score "
        "chain at the closure level of the row (hospital by vehicle within 30 minutes, main road within 15 minutes). No "
        "stored ratio is read.",
        "Vulnerability is computed from the modelled 2024 age counts of each unit on the national anchors of protocol v1b.",
        f"The headline slot of each row carries guardrail GR8 over the {cells} cells of the Nan ensemble that were run.",
        "Planning guidance only. Not an official warning. Class E never means safe.",
    ]


def nan_run(arguments: NanArguments) -> dict[str, Any]:
    """Check the inputs of a Nan case, run the chain, and write the result file, the run record and the work files.

    Raises:
        ChainError: when an input is refused (before any unit is measured against the flood input).
    """

    started = arguments.generated_at or e5.utc_now()
    timings: dict[str, float] = {}
    clock = time.perf_counter()
    case_id = arguments.case_id
    if case_id not in CASE_TIERS:
        raise ChainError(f"the Nan cases are {sorted(CASE_TIERS)}")
    tier = CASE_TIERS[case_id]
    refuse_sealed([arguments.context, *arguments.flood.values(), arguments.boundaries, arguments.land_cover,
                   arguments.routing_geometry, arguments.age_table, arguments.age_dir, arguments.rescaled_population])
    if not arguments.fixture and not FREEZE_RECORD.is_file():
        raise ChainError("the order rule of the Nan protocol: the freeze record outputs/nan_case/freeze_v1.json does not "
                         "exist, so no Nan case is run")
    if not arguments.fixture and not TEST_RECORD.is_file():
        raise ChainError("the order rule of the Nan protocol: the chain runs on Nan after the test, and the test record "
                         "outputs/nan_case/test_result_v1.json does not exist")
    if "central" not in arguments.flood:
        raise ChainError("a run needs the central flood map")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,63}", arguments.flood_input_id):
        raise ChainError("the flood input identifier is one of the overlay schema: [a-z0-9][a-z0-9_.-]{1,63}")
    outcome = nan.check_outcome(arguments.outcome)
    if tier != "T2" and arguments.out_dir is not None and arguments.out_dir.resolve().is_relative_to(ROOT.resolve()):
        raise ChainError("a result below the public level stays outside Git (guardrail GR6; nan_case_protocol_v1 rights_in_git)")
    docs = arguments.docs
    v1a_path, v1b_path, receipts_path = docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl"
    rules = planning_assessment.load_assessment_rules(v1a_path, v1b_path, receipts_path)
    grid_rules = ensemble.load_grid(v1a_path, v1b_path, receipts_path)
    nan.check_rule_thresholds(rules.binding.rule)
    v1a = json.loads(v1a_path.read_text(encoding="utf-8"))
    v1b = json.loads(v1b_path.read_text(encoding="utf-8"))
    protocol = json.loads(NAN_PROTOCOL.read_text(encoding="utf-8"))
    if protocol.get("schema") != nan.NAN_PROTOCOL_SCHEMA:
        raise ChainError("the Nan protocol file is not floodguard.nan_case_protocol.v1")
    grid = arguments.grid or nan.grid_from_record(protocol["grid"]["frame"])
    if not arguments.fixture:
        areas = json.loads(AREAS_RECORD.read_text(encoding="utf-8"))
        if nan.grid_from_record(areas["areas"]["nan_frame"]["grid"]) != grid:
            raise ChainError("the grid of the Nan protocol and the grid of outputs/nan_case/areas_v1.json differ")
    minimum_px = int(v1b["closure_rule_v1"]["parameters"]["raster_minimum_polygon_px"])
    one_pixel_m = float(grid_rules.one_pixel_m)
    if abs(one_pixel_m - grid.cell_m) > 1e-9:
        raise ChainError(f"one pixel of protocol v1b is {one_pixel_m:g} m and the frame's cells are {grid.cell_m:g} m")
    service_rules = access_diff.service_rules(v1a, v1b)
    public = [rule for rule in service_rules if rule.publication_level == access_diff.PUBLIC_LEVEL]
    services = [rule.service for rule in public]
    closure_arguments = access_diff.closure_arguments(v1b)
    external = arguments.external
    work_dir = arguments.work_dir or external / WORK_RELATIVE
    work_dir.mkdir(parents=True, exist_ok=True)

    units, names, unit_summary = read_units(arguments, protocol["frame"]["district_pcodes"])
    if not arguments.fixture:
        stated = re.search(r"\((\d+) units", str(protocol["frame"]["units"]))
        if stated is None or int(stated.group(1)) != len(units):
            raise ChainError(f"the Nan protocol names {stated.group(1) if stated else '?'} units; the boundary layer holds {len(units)}")
    unit_ids = [unit_id for unit_id, _geometry in units]
    reporting = flood_inputs.frame_from_units(flood_inputs.REPORTING_FRAME, "the reporting units of the case", list(units), {})
    routing, routing_record = routing_frame(units, arguments)
    if not shapely.box(*grid.bounds).buffer(0.01, join_style="mitre").covers(reporting.geometry):
        raise ChainError("the frame's grid does not cover every unit of the case")
    graph, context_record = load_context(arguments.context, external)
    water = flood_inputs.permanent_water(arguments.land_cover, reporting, water_class=WATER_CLASS, source_name=WATER_SOURCE)
    water_record = {**dict(water.record)}
    clock = _clock(timings, "inputs_read", clock)

    rasters: dict[str, Any] = {}
    raster_records: dict[str, Any] = {}
    for name, path in arguments.flood.items():
        if name not in nan.FLOOD_AXIS_KEYS:
            raise ChainError(f"the flood maps are {sorted(nan.FLOOD_AXIS_KEYS)}")
        rasters[name], raster_records[name] = read_flood_raster(path, grid, name)
    transform = grid.transform
    component: dict[str, Any] = {}
    closure: dict[str, Any] = {}
    closure_records: dict[str, Any] = {}
    unclipped_central = None
    for name in ("lower", "central", "upper"):
        if name not in rasters:
            continue
        key = nan.FLOOD_AXIS_KEYS[name]
        mask = nan.treatment_mask(rasters[name], nan.BINDING_TREATMENT)
        extent = nan.cell_footprints(mask, transform)
        if name == "central":
            unclipped_central = extent
        component[key] = flood_inputs.clip_to_frame(extent, reporting)
        kept, counts = nan.closure_extent(mask, transform, tier=tier, minimum_px=minimum_px)
        closure[key] = flood_inputs.clip_to_frame(kept, routing)
        closure_records[name] = {**counts, "reporting_frame": flood_inputs.geometry_summary(component[key]),
                                 "routing_frame": flood_inputs.geometry_summary(closure[key])}
    levels = flood_inputs.one_pixel_levels(unclipped_central, one_pixel_m)
    c4 = {level: flood_inputs.clip_to_frame(levels[level], reporting) for level in (flood_inputs.MINUS, flood_inputs.PLUS)}
    clock = _clock(timings, "flood_extents", clock)

    # The no-answer cells of the central map: report-only figures, and the two measurements the confidence rule reads.
    central = rasters["central"]
    no_answer_mask = central == nan.NO_ANSWER
    pieces = nan.tiled_footprints(no_answer_mask, transform)
    identifiers, lines = nan.edge_lines_in_metres(graph.edges, graph.node_coordinates)
    crossing = nan.edges_crossing_by_unit(identifiers, lines, pieces, reporting.units)
    population_rows = {row["population_id"]: row for row in graph.population}
    cells = access_diff.demand_cells(graph.population, access_diff.assign_cells(graph.population, units))
    from pyproj import Transformer

    to_metres = Transformer.from_crs(flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS, always_xy=True)
    xs, ys = to_metres.transform([float(population_rows[cell["population_id"]]["longitude"]) for cell in cells],
                                 [float(population_rows[cell["population_id"]]["latitude"]) for cell in cells])
    values_at_cells = nan.grid_values_at(central, grid, xs, ys)
    no_answer = nan.no_answer_by_unit(units=reporting.units, water=water.geometry, no_answer_pieces=pieces, cells=cells,
                                      cell_values=values_at_cells, edges_crossing=crossing)
    flagged_lists: dict[str, list[float]] = {unit_id: [] for unit_id in unit_ids}
    for cell, value in zip(cells, values_at_cells.tolist()):
        if value == nan.FLAGGED and cell["unit_id"] in flagged_lists:
            flagged_lists[cell["unit_id"]].append(float(cell["residents"]))
    flagged_by_lookup = {unit_id: math.fsum(values) for unit_id, values in flagged_lists.items()}
    clock = _clock(timings, "no_answer_figures", clock)

    age_table, age_record = load_age_table(arguments, units, work_dir)
    rescaled, rescaled_record = load_rescaled(arguments, graph, v1b_path)
    anchors_path = ROOT / "outputs" / "planning_v1" / "national_vulnerability_anchors_v1.json"
    anchors_sha256 = sha256_file(anchors_path)
    if anchors_sha256 != rules.binding.frame.vulnerability_anchor_receipt_sha256:
        raise ChainError("the national-anchor receipt is not the file protocol v1b names")
    anchors_timestamp = str(json.loads(anchors_path.read_text(encoding="ascii")).get("source_timestamp"))
    population_path = external / POPULATION_2020_RELATIVE
    population_sha256 = sha256_file(population_path) if population_path.is_file() else None

    kind = FIXTURE_KIND if arguments.fixture else PORTFOLIO_KIND
    title_en, title_th = CASE_TITLES[case_id]
    if arguments.fixture:
        title_en, title_th = f"{title_en} (fixture, not a place)", f"{title_th} (ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)"
    case = planning_assessment.CaseSpec(
        case_id=case_id, kind=kind, title_en=title_en, title_th=title_th,
        frame="Nan: Mueang Nan, Phu Phiang and Wiang Sa" + (" (fixture, not a place)" if arguments.fixture else ""),
        case_reference_date=outcome.case_reference_date, lane="OBS", tier=tier,
        fixture_notice="Fixture, not a place: every unit, input, count and date of this file is invented." if arguments.fixture else None)
    flood_spec = planning_assessment.FloodInputSpec(input_id=arguments.flood_input_id, name=arguments.flood_name,
                                                    acquisition_date=arguments.acquisition_date,
                                                    source_instant=arguments.source_instant)
    not_run = [ensemble.LevelNotRun(ensemble.FACILITIES_AXIS, level, "facility_set_not_in_the_nan_ensemble",
                                    "The ensemble of the Nan protocol has the public facility set only (hospitals by "
                                    "vehicle, main road): no shelter set is part of the case.", ("nan_case_protocol_v1",))
               for level in grid_rules.axis(ensemble.FACILITIES_AXIS).levels if level != ensemble.PUBLIC_LEVEL]
    if rescaled is None:
        not_run.append(ensemble.LevelNotRun(ensemble.VINTAGE_AXIS, VINTAGE_RESCALED, "population_axis_dropped_by_the_nan_protocol",
                                            "The 2024-rescaled demand was not built for the frame, so the population axis is "
                                            "dropped and the Nan ensemble has 90 cells (nan_case_protocol_v1, ensemble).",
                                            ("nan_case_protocol_v1",)))
    for name in ("lower", "upper"):
        if name not in rasters:
            not_run.append(ensemble.LevelNotRun(ensemble.FLOOD_AXIS, nan.FLOOD_AXIS_KEYS[name], f"{name}_flood_map_not_given",
                                                f"The {name} flood map of the Nan ensemble was not given to this run.", ()))
    derive = nan.nan_derivation(outcome)
    coverage = {unit_id: no_answer[unit_id]["answered_share_of_land"] for unit_id in unit_ids}
    abstention = {unit_id: no_answer[unit_id]["no_answer_share_of_land"] if tier == "T2" else None for unit_id in unit_ids}
    scope_cells = 180 if rescaled is not None else 90
    run_cells = scope_cells * len(rasters) // 3
    ci = ChainInputs(
        case_id=case_id, rules=rules, grid=grid_rules, case=case, flood_spec=flood_spec,
        access_flood_input_id=arguments.flood_input_id, units=list(units), names=names, graph=graph,
        service_rules=service_rules, services=services, arguments=closure_arguments, age_table=age_table,
        water=water.geometry, component=component, closure=closure, c4=c4, coverage=coverage,
        by_construction={unit_id: False for unit_id in unit_ids}, abstention=abstention,
        test_iou=outcome.test_1_iou if tier == "T2" else None, routing_context_id="nan_planning_context_vehicle",
        derive=derive, not_run=not_run, rescaled=rescaled,
        overlay_assumptions=nan_assumptions(tier, one_pixel_m=one_pixel_m, minimum_px=minimum_px, cells=run_cells),
        source_name=f"FloodGuard planning result: case {case_id}, Nan frame", generated_at=started,
        git_commit=arguments.git_commit or e8.head_commit(ROOT), timings=timings)

    measured = measure(ci)
    clock = time.perf_counter()
    sensitivity = None
    if arguments.sensitivity:
        sensitivity = sensitivity_run(ci, measured, central, grid, reporting, routing, tier=tier, minimum_px=minimum_px,
                                      one_pixel_m=one_pixel_m)
        clock = _clock(timings, "sensitivity_run", clock)
    access_document = access_runs_document(ci, measured, external=external, extra={
        "sensitivity_run": None if sensitivity is None else sensitivity["access"]})
    access_bytes = e8.encode(access_document)
    access_target = work_dir / f"access_runs_{case_id.lower()}.json"
    access_written = write_bytes(access_target, access_bytes)
    boundary_sha256 = sha256_file(arguments.boundaries)
    inputs = lineage_inputs(arguments, tier=tier, fallback=outcome.fallback, flood_record=raster_records["central"], context_record=context_record,
                            boundary_sha256=boundary_sha256, water_record=water_record, age_record=age_record,
                            anchors_sha256=anchors_sha256, anchors_timestamp=anchors_timestamp,
                            access_sha256=access_written["sha256"], population_sha256=population_sha256)
    assessed = assess(ci, measured, inputs)
    clock = time.perf_counter()

    # The headline of each row: guardrail GR8 over the cells of the Nan ensemble that were run.
    result = assessed.ensemble
    run_ids = [cell["cell_id"] for cell in result["cells"] if cell["status"] == ensemble.STATUS_RUN]
    over = (f"the {len(run_ids)} cells of the Nan ensemble that were run (nan_case_protocol_v1, ensemble: 180 cells, or 90 "
            "when the population axis is dropped)")
    headlines = {unit["unit_id"]: nan.headline_over_the_cells_run(grid_rules, unit, scope=run_ids, over=over) for unit in result["units"]}
    would_be = {unit["unit_id"]: nan.would_be_retention(unit, scope=run_ids) for unit in result["units"]}
    overlay = assessed.overlay
    default_sentence = next((text for text in overlay["assumptions"] if text.startswith("Every row is the default cell of protocol v1b")), None)
    if default_sentence is not None:
        overlay["assumptions"] = [text if text != default_sentence else (
            "Every row is the default cell of protocol v1b: the central flood map, the central closure level, the public "
            "services, WorldPop 2020, the P10 / P90 anchors and the default weights. The ensemble of the Nan protocol has "
            "run; the headline slot of each row carries guardrail GR8 over its cells.") for text in overlay["assumptions"]]
    sensitivity_by_unit = {} if sensitivity is None else {row["unit_id"]: row for row in sensitivity["table"]}
    for row in overlay["rows"]:
        unit_id = row["unit_id"]
        row["headline_stability"] = nan.headline_slot(headlines[unit_id])
        figures = no_answer[unit_id]
        share = figures["no_answer_share_of_land"]
        sentence = (f"No answer (code 255) on {('%.4f' % share) if share is not None else 'an unmeasured share'} of the unit's "
                    f"land outside permanent water; {figures['residents_in_no_answer_cells']:.1f} modelled residents in "
                    f"no-answer cells; {figures['vehicle_edges_crossing_no_answer_cells']} vehicle edges cross no-answer cells. "
                    "The binding row counts a no-answer cell as not flagged.")
        if unit_id in sensitivity_by_unit:
            twin = sensitivity_by_unit[unit_id]["no_answer_counted_as_flagged"]
            fpps = "no FPPS" if twin["fpps_0_100"] is None else f"FPPS {twin['fpps_0_100']:.2f}"
            sentence += (f" With no-answer counted as flagged (sensitivity, not binding): {fpps}, class {twin['action_class']}"
                         + (f", would-be class {twin['would_be_class']}" if twin["would_be_class"] else "") + ".")
        row["assumptions"] = [*row["assumptions"], sentence]
    schema = load_overlay_schema(ROOT / SCHEMA_RELATIVE_PATH)
    verified = nan.nan_overlay_problems(overlay, schema, rules.binding, derive)
    if not verified["verified"]:
        raise ChainError(f"the result file is refused: {verified['refused'][:3]}")
    text = json.dumps(overlay, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    eligibility = overlay["publication_eligibility"]
    out_dir = arguments.out_dir or (RESULT_DIR_IN_GIT if eligibility == rights.PUBLIC_LEVEL else work_dir)
    if eligibility != rights.PUBLIC_LEVEL and out_dir.resolve().is_relative_to(ROOT.resolve()):
        raise ChainError("a result below the public level stays outside Git (guardrail GR6; nan_case_protocol_v1 rights_in_git)")
    suffix = "_fixture" if arguments.fixture else ""
    result_path = out_dir / f"planning_result_{case_id.lower()}_nan_v1{suffix}.json"
    result_written = write_bytes(result_path, text.encode("ascii"))
    ensemble_document = {
        "schema_version": ENSEMBLE_SCHEMA, "case_id": case_id, "generated_at_utc": started,
        "source_timestamp": arguments.source_instant, "confidence_class": "low",
        "assumptions": ["A cell is the same modelled chain run with one declared choice changed. The share of cells in a "
                        "class is not a probability.",
                        "Flood axis: minus is the lower map, as_provided the central map and plus the upper map "
                        "(nan_case_protocol_v1, tuning.flood_axis_of_the_ensemble)."],
        "official_warning": False, "operational_status": "non_operational",
        "flood_axis_keys": dict(nan.FLOOD_AXIS_KEYS), "headline_over": over, "ensemble": result,
        "headlines": headlines, "would_be_retention": would_be}
    ensemble_target = work_dir / f"ensemble_{case_id.lower()}.json"
    ensemble_written = write_bytes(ensemble_target, e8.encode(ensemble_document))
    _clock(timings, "headline_verify_and_write", clock)
    rows = overlay["rows"]
    record = {
        "schema_version": RECORD_SCHEMA,
        "what": f"The run record of the score chain for case {case_id}: what was read, what was checked, the per-tambon "
                "no-answer figures, the sensitivity run and the ensemble, beside the result file.",
        "generated_at_utc": started,
        "source_timestamp": arguments.source_instant,
        "confidence_class": "low",
        "confidence_basis": "Planning classes from modelled access on OpenStreetMap roads, modelled resident and age counts, "
                            "and closures assumed from a flood map. The confidence class of each row is in the result file; "
                            "this line is the confidence of the run as evidence.",
        "assumptions": overlay["assumptions"],
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "accepted_fpps": None,
        "accepted_action_class": None,
        "chain_version": nan.CHAIN_VERSION,
        "protocol_sha256": {"v1a": rules.binding.frame.protocol_sha256["v1a"], "v1b": rules.binding.frame.protocol_sha256["v1b"],
                            "nan_case_v1": sha256_file(NAN_PROTOCOL)},
        "case": {"case_id": case_id, "tier": tier, "lane": "OBS", "kind": kind,
                 "case_reference_date": outcome.case_reference_date.isoformat()},
        "case_outcome": {**outcome.as_record(), "read_from": arguments.test_result or "the command line"},
        "publication_eligibility": eligibility,
        "parameters": {"grid": grid.as_record(), "one_pixel_m": one_pixel_m, "raster_minimum_polygon_px": minimum_px,
                       "closure_polygon_connectivity": nan.CLOSURE_POLYGON_CONNECTIVITY,
                       "closure_level_of_the_row": rules.reference_closure_level, "services": services,
                       "binding_treatment": nan.BINDING_TREATMENT,
                       "flood_axis_keys": dict(nan.FLOOD_AXIS_KEYS), "ensemble_cells_run": len(run_ids),
                       "tile_cells_of_the_report_only_figures": nan.TILE_CELLS},
        "inputs": {"flood_maps": raster_records, "context": {key: value for key, value in context_record.items() if key != "graph"},
                   "graph": context_record["graph"], "units": unit_summary, "routing_frame": routing_record,
                   "boundaries": {"path": label(arguments.boundaries, external), "sha256": boundary_sha256},
                   "permanent_water": water_record, "age_counts": age_record, "rescaled_demand": rescaled_record,
                   "national_anchors": {"path": label(anchors_path, external), "sha256": anchors_sha256},
                   "lineage_of_the_result_file": {item["input_id"]: item["sha256"] for item in inputs}},
        "flood_extents": closure_records,
        "no_answer_by_tambon": [{"unit_id": unit_id, **no_answer[unit_id],
                                 "residents_in_flagged_cells_by_grid_lookup": flagged_by_lookup[unit_id]} for unit_id in unit_ids],
        "sensitivity_no_answer_counted_as_flagged": None if sensitivity is None else {
            "what": "The central cell (central map, central closure level, public services, WorldPop 2020, P10 / P90, default "
                    "weights) with every no-answer cell counted as flagged. Report-only; never binding.",
            "closure_measurement": sensitivity["measurement"],
            "table": sensitivity["table"],
            "tambons_whose_class_differs": sum(1 for item in sensitivity["table"] if not item["class_same"]),
        },
        "rows": [{"unit_id": row["unit_id"], "fpps_0_100": row["fpps_0_100"], "action_class": row["action_class"],
                  "action_reason_code": row["action_reason_code"], "would_be_class": row["would_be_class"],
                  "confidence_class": row["confidence"]["confidence_class"],
                  "failed_conditions": row["confidence"]["failed_conditions"],
                  "headline_status": row["headline_stability"]["status"],
                  "class_retention": row["headline_stability"]["class_retention"]} for row in rows],
        "ensemble": {"summary": result["summary"], "headline_over": over,
                     "headlines": {unit_id: {key: value for key, value in record_.items() if key in (
                         "status", "class_retention", "reference_class", "cells_run", "cells_keeping_the_reference_class")}
                                   for unit_id, record_ in headlines.items()},
                     "would_be_retention": would_be, "levels_not_run": [item.as_record() for item in not_run]},
        "checks": {"guardrails": assessed.guardrails, "whole_case": assessed.whole_case, "result_file": verified,
                   "default_cell_of_the_ensemble_is_the_row": assessed.default_cell_is_the_row_but_text,
                   "residents_in_flagged_cells_polygon_and_grid_lookup_differ_by": max(
                       (abs(flagged_by_lookup[unit_id] - measured.inside_level[flood_inputs.AS_PROVIDED].get(unit_id, 0.0))
                        for unit_id in unit_ids), default=0.0)},
        "outputs": [
            {"what": "result_file", "path": label(result_path, external), **result_written, "in_git": result_path.resolve().is_relative_to(ROOT.resolve())},
            {"what": "access_runs", "path": label(access_target, external), **access_written, "in_git": False},
            {"what": "ensemble_cells", "path": label(ensemble_target, external), **ensemble_written, "in_git": False},
        ],
        "implementation": {"base_commit": ci.git_commit, **code_hashes(), "software": software_versions()},
        "timing_seconds": timings,
    }
    record_path = out_dir / f"planning_result_{case_id.lower()}_nan_v1{suffix}_record.json"
    record_written = write_bytes(record_path, e8.encode(record))
    return {"result_file": label(result_path, external), "result_sha256": result_written["sha256"],
            "record": label(record_path, external), "record_sha256": record_written["sha256"],
            "publication_eligibility": eligibility, "rows": len(rows),
            "classes": {row["unit_id"]: row["action_class"] for row in rows}, "ensemble_cells_run": len(run_ids),
            "verified": verified["verified"], "timing_seconds": timings}


def nan_check_inputs(arguments: NanArguments) -> dict[str, Any]:
    """Make the input checks of a Nan run that need no flood map, and write nothing in Git.

    The frame's units, routing geometry, planning context, permanent water, age counts and 2024-rescaled demand
    are read and checked as a run reads them. No flood map is opened, no test outcome is read, no unit is measured
    against a flood input and no component is computed, so the order rule of the Nan protocol does not stop it.
    The figures are counts for the whole frame.
    """

    refuse_sealed([arguments.context, arguments.boundaries, arguments.land_cover, arguments.routing_geometry,
                   arguments.age_table, arguments.age_dir, arguments.rescaled_population])
    started = time.perf_counter()
    docs = arguments.docs
    v1b_path = docs / "planning_protocol_v1b.json"
    rules = planning_assessment.load_assessment_rules(docs / "planning_protocol_v1a.json", v1b_path, docs / "RECEIPTS.jsonl")
    protocol = json.loads(NAN_PROTOCOL.read_text(encoding="utf-8"))
    grid = arguments.grid or nan.grid_from_record(protocol["grid"]["frame"])
    work_dir = arguments.work_dir or arguments.external / WORK_RELATIVE
    work_dir.mkdir(parents=True, exist_ok=True)
    units, _names, unit_summary = read_units(arguments, protocol["frame"]["district_pcodes"])
    reporting = flood_inputs.frame_from_units(flood_inputs.REPORTING_FRAME, "the reporting units of the case", list(units), {})
    routing, routing_record = routing_frame(units, arguments)
    graph, context_record = load_context(arguments.context, arguments.external)
    water = flood_inputs.permanent_water(arguments.land_cover, reporting, water_class=WATER_CLASS, source_name=WATER_SOURCE)
    age_table, age_record = load_age_table(arguments, units, work_dir)
    rescaled, rescaled_record = load_rescaled(arguments, graph, v1b_path)
    population = sorted(graph.population, key=lambda item: item["population_id"])
    cells = access_diff.demand_cells(population, access_diff.assign_cells(population, units))
    unit_ids = {unit_id for unit_id, _geometry in units}
    age_units = {str(row["unit_id"]) for row in age_table.get("units", [])}
    reachable = planning_assessment.hospitals_reachable_at_baseline(
        [{**cell, "node_id": row.get("node_id"), "snap_distance_m": row.get("snap_distance_m")}
         for cell, row in zip(cells, population)], graph.edges, graph.destinations[access_diff.HOSPITAL])
    box = shapely.box(*grid.bounds).buffer(0.01, join_style="mitre")
    return {
        "inputs_checked": True, "case_id": arguments.case_id,
        "computed": "No flood map was opened, no unit was measured against a flood input and no component was computed.",
        "units": unit_summary, "routing_frame": routing_record,
        "grid": grid.as_record(),
        "grid_covers_every_unit": bool(box.covers(reporting.geometry)),
        "grid_covers_the_routing_frame": bool(box.covers(routing.geometry)),
        "context": {key: value for key, value in context_record.items() if key != "input_hashes"},
        "demand_cells": len(cells), "demand_cells_in_one_unit": sum(1 for cell in cells if cell["unit_id"] is not None),
        "residents_in_the_units": math.fsum(cell["residents"] for cell in cells if cell["unit_id"] is not None),
        "units_with_no_reachable_hospital_at_baseline": sum(1 for unit_id in unit_ids if reachable.get(unit_id, 0) < 1),
        "permanent_water_km2_in_the_reporting_frame": water.record["permanent_water_km2"],
        "age_table": {**age_record, "holds_every_unit": unit_ids <= age_units, "units": len(age_units)},
        "rescaled_demand": {**{key: value for key, value in rescaled_record.items() if key in ("source", "path", "sha256", "consequence")},
                            "covers_every_demand_cell": None if rescaled is None else all(
                                str(cell["population_id"]) in rescaled for cell in cells)},
        "protocol_sha256": dict(rules.binding.frame.protocol_sha256),
        "timing_seconds": round(time.perf_counter() - started, 1),
    }


def sensitivity_run(ci: ChainInputs, measured: SimpleNamespace, central: np.ndarray, grid: nan.RasterGrid,
                    reporting: flood_inputs.Frame, routing: flood_inputs.Frame, *, tier: str, minimum_px: int,
                    one_pixel_m: float) -> dict[str, Any]:
    """The central cell with every no-answer cell counted as flagged: rows beside the binding rows (report-only).

    The extents are those of the binding chain, made from the union of the flagged and the no-answer cells. The
    length of each edge inside the closure extent is summed over the tile pieces of that extent
    (``nan_case_chain.edge_lengths_inside_pieces``), the same measurement as closure rule v1 made piece by piece,
    because the extent can cover a large part of the frame. Closure rule v1 is then applied at the central level.
    """

    transform = grid.transform
    mask = nan.treatment_mask(central, nan.SENSITIVITY_TREATMENT)
    extent = nan.cell_footprints(mask, transform)
    component = flood_inputs.clip_to_frame(extent, reporting)
    levels = flood_inputs.one_pixel_levels(extent, one_pixel_m)
    c4 = {level: flood_inputs.clip_to_frame(levels[level], reporting) for level in (flood_inputs.MINUS, flood_inputs.PLUS)}
    if tier == "T2":
        from scipy import ndimage

        labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
        sizes = np.bincount(labels.ravel(), minlength=count + 1)
        keep = sizes >= minimum_px
        keep[0] = False
        closure_mask = keep[labels]
    else:
        closure_mask = mask
    pieces = [piece for piece in nan.tiled_footprints(closure_mask, transform)]
    shapely.prepare(routing.geometry)
    pieces = [piece if routing.geometry.contains(piece) else shapely.intersection(piece, routing.geometry) for piece in pieces]
    pieces = [piece for piece in pieces if not piece.is_empty and piece.area > 0]
    identifiers, lines = nan.edge_lines_in_metres(ci.graph.edges, ci.graph.node_coordinates)
    intersections = nan.edge_lengths_inside_pieces(identifiers, lines, pieces)
    level = ci.rules.reference_closure_level
    changed, result = access_diff.flooded_edges(level, ci.graph.edges, intersections, flood_input_id=ci.access_flood_input_id,
                                                arguments=ci.arguments)
    public = [rule for rule in ci.service_rules if rule.publication_level == access_diff.PUBLIC_LEVEL]
    baselines = e5.baseline_runs(ci.graph, ci.service_rules)
    flooded = {rule.service: access_diff.cell_minutes(ci.graph.population, changed, ci.graph.destinations[rule.service],
                                                      baseline_nodes=ci.graph.nodes) for rule in public}
    unit_ids = [unit_id for unit_id, _geometry in ci.units]
    table = access_diff.unit_rows(measured.cells, unit_ids, public, baselines, flooded)
    rows_by_unit = {str(row["unit_id"]): row for row in table["units"]}
    inside = planning_assessment.residents_by_unit(measured.counted.cells, component)
    inside_c4 = {key: planning_assessment.residents_by_unit(measured.counted.cells, c4[key]) for key in c4}
    header = None
    rows = []
    closure = planning_assessment.ClosureSpec(closure_rules.CLOSURE_RULE_VERSION, level)
    from floodguard.normalisation import frame_record

    header = frame_record(ci.rules.binding.frame)
    for unit in measured.base:
        counts = planning_assessment.access_counts_from_e5_row(rows_by_unit[unit.unit_id], ci.services)
        areas = flood_inputs.flooded_land_areas(measured.frame.units[unit.unit_id], component, ci.water)
        twin = replace(unit, flooded_non_permanent_water_land_area=areas["flooded_non_permanent_water_land_area"],
                       residents_inside_flood_extent={flood_inputs.MINUS: inside_c4[flood_inputs.MINUS].get(unit.unit_id, 0.0),
                                                      flood_inputs.AS_PROVIDED: inside.get(unit.unit_id, 0.0),
                                                      flood_inputs.PLUS: inside_c4[flood_inputs.PLUS].get(unit.unit_id, 0.0)},
                       access_gap_inputs=counts["access_gap_inputs"],
                       residents_losing_all_routes=counts["residents_losing_all_routes"],
                       residents_with_baseline_route=counts["residents_with_baseline_route"])
        rows.append(planning_assessment.assess_unit(ci.rules, ci.case, ci.flood_spec, closure, twin,
                                                    routing_context_id=ci.routing_context_id, frame_header=header,
                                                    derive=ci.derive))
    binding_rows = [planning_assessment.assess_unit(ci.rules, ci.case, ci.flood_spec, closure, unit,
                                                    routing_context_id=ci.routing_context_id, frame_header=header,
                                                    derive=ci.derive) for unit in measured.base]
    return {
        "table": nan.sensitivity_table(binding_rows, rows),
        "measurement": "The length of each edge inside the extent, summed over its tile pieces "
                       f"({nan.TILE_CELLS} x {nan.TILE_CELLS} cells), from the straight node-to-node segment in EPSG:32647; "
                       f"closure rule v1 at the {level} level.",
        "access": {"closure_level": level, "closure": access_diff.closure_summary(result, ci.graph.edges),
                   PUBLIC_SERVICES: table},
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _yes_no(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in ("yes", "true", "pass", "passed"):
        return True
    if lowered in ("no", "false", "fail", "failed"):
        return False
    if lowered in ("unknown", "not_read", "none"):
        return None
    raise argparse.ArgumentTypeError("yes, no or unknown")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the command line and run one mode.

    Returns:
        0 when the run finished (for the replay: and every comparison was the same); 1 when the replay found a
        difference; 2 when an input was refused and nothing was measured.
    """

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    replay = sub.add_parser("se1-replay", help="the proof on case SE1's own inputs")
    replay.add_argument("--external-root", type=Path, required=True)
    replay.add_argument("--age-dir", type=Path, help="the WorldPop 2024 age folder, for the 2024-rescaled demand of the ensemble")
    replay.add_argument("--work-dir", type=Path)
    run = sub.add_parser("nan", help="a Nan case, after the test")
    run.add_argument("--case", choices=sorted(CASE_TIERS), required=True)
    run.add_argument("--external-root", type=Path, required=True)
    run.add_argument("--context", type=Path, required=True, help="the frame's planning context (context_inputs.json, vehicle)")
    run.add_argument("--flood-central", type=Path)
    run.add_argument("--flood-lower", type=Path)
    run.add_argument("--flood-map", type=Path, help="a map of the method lane with the bands code_lower, code_central and "
                     "code_upper (in the place of --flood-central, --flood-lower and --flood-upper)")
    run.add_argument("--test-result", type=Path, help="the test record of the method lane "
                     "(outputs/nan_case/test_result_v1.json): the outcome, the pass and its map")
    run.add_argument("--flood-upper", type=Path)
    run.add_argument("--flood-input-id", help="an identifier of the overlay schema ([a-z0-9][a-z0-9_.-]{1,63})")
    run.add_argument("--flood-name")
    run.add_argument("--acquisition-date", type=date.fromisoformat)
    run.add_argument("--source-instant", help="the pass time, e.g. 2025-07-28T11:21:00Z")
    run.add_argument("--test-1-passed", type=_yes_no)
    run.add_argument("--test-1-iou", type=float)
    run.add_argument("--dry-control-passed", type=_yes_no)
    run.add_argument("--test-1-reference", help="the reference of test 1, in words")
    run.add_argument("--fallback", action="store_true", help="test 1 used its fallback (GFM, same pass); reference date 2025-07-31")
    run.add_argument("--boundaries", type=Path)
    run.add_argument("--land-cover", type=Path)
    run.add_argument("--routing-geometry", type=Path)
    run.add_argument("--age-table", type=Path)
    run.add_argument("--age-dir", type=Path)
    run.add_argument("--rescaled-population", type=Path)
    run.add_argument("--build-rescaled-demand", action="store_true")
    run.add_argument("--out-dir", type=Path)
    run.add_argument("--work-dir", type=Path)
    run.add_argument("--no-sensitivity", action="store_true")
    run.add_argument("--check-inputs", action="store_true",
                     help="check the inputs of the frame that need no flood map; open no flood map and measure nothing")
    args = parser.parse_args(argv)
    try:
        if args.mode == "se1-replay":
            work = args.work_dir or args.external_root / WORK_RELATIVE
            summary = se1_replay(args.external_root, age_dir=args.age_dir, work_dir=work)
            print(json.dumps(summary, indent=2))
            return EXIT_DONE if summary["all_same"] else EXIT_FAILED
        from_record: dict[str, Any] = {}
        if args.test_result is not None and not args.check_inputs:
            outcome_read, from_record = outcome_from_test_result(args.test_result, args.external_root)
            passed = from_record.get("flood_input") or {}
            args.test_1_passed = outcome_read.test_1_passed if args.test_1_passed is None else args.test_1_passed
            args.dry_control_passed = outcome_read.dry_control_passed if args.dry_control_passed is None else args.dry_control_passed
            args.test_1_iou = outcome_read.test_1_iou if args.test_1_iou is None else args.test_1_iou
            args.test_1_reference = args.test_1_reference or outcome_read.reference
            args.fallback = args.fallback or outcome_read.fallback
            if args.flood_map is None and from_record.get("map_path") is not None:
                args.flood_map = from_record["map_path"]
            time_utc = passed.get("time_utc")
            if time_utc and args.source_instant is None:
                args.source_instant = str(time_utc)
            if time_utc and args.acquisition_date is None:
                from datetime import datetime, timedelta

                instant = datetime.strptime(str(time_utc), "%Y-%m-%dT%H:%M:%SZ")
                args.acquisition_date = (instant + timedelta(hours=7)).date()   # the Thai calendar date of the pass
            if passed.get("label") and args.flood_input_id is None:
                args.flood_input_id = "nan_m1z." + re.sub(r"[^a-z0-9_.-]", "_", str(passed["label"]).lower())
            if args.flood_name is None and time_utc:
                args.flood_name = (f"FloodGuard M1-z radar flood map (frozen), {passed.get('platform') or 'Sentinel-1'} pass of "
                                   f"{time_utc}, relative orbit {passed.get('relative_orbit')}")
        if args.flood_map is not None:
            args.flood_central = args.flood_central or args.flood_map
            args.flood_lower = args.flood_lower or args.flood_map
            args.flood_upper = args.flood_upper or args.flood_map
        if not args.check_inputs:
            needed = {"--flood-central": args.flood_central, "--flood-input-id": args.flood_input_id,
                      "--flood-name": args.flood_name, "--acquisition-date": args.acquisition_date,
                      "--source-instant": args.source_instant, "--test-1-reference": args.test_1_reference,
                      "--test-1-passed": "" if args.test_1_passed is not None else None,
                      "--dry-control-passed": "" if args.dry_control_passed is not None else None}
            missing = [name for name, value in needed.items() if value is None]
            if missing:
                parser.error(f"a Nan run needs {', '.join(missing)} (or --check-inputs)")
        flood = {"central": args.flood_central} if args.flood_central is not None else {}
        if args.flood_lower is not None:
            flood["lower"] = args.flood_lower
        if args.flood_upper is not None:
            flood["upper"] = args.flood_upper
        outcome = nan.CaseOutcome(test_1_passed=args.test_1_passed, dry_control_passed=args.dry_control_passed,
                                  test_1_iou=args.test_1_iou, reference=args.test_1_reference or "not read (input checks only)",
                                  case_reference_date=date(2025, 7, 31) if args.fallback else date(2025, 7, 28),
                                  fallback=args.fallback)
        arguments = NanArguments(
            case_id=args.case, external=args.external_root, context=args.context, flood=flood,
            flood_input_id=args.flood_input_id or "", flood_name=args.flood_name or "",
            acquisition_date=args.acquisition_date or date(2025, 7, 28), source_instant=args.source_instant or "",
            outcome=outcome,
            boundaries=args.boundaries or args.external_root / BOUNDARY_RELATIVE,
            land_cover=args.land_cover or args.external_root / LAND_COVER_RELATIVE, routing_geometry=args.routing_geometry,
            age_table=args.age_table, age_dir=args.age_dir, rescaled_population=args.rescaled_population,
            build_rescaled_demand=args.build_rescaled_demand, out_dir=args.out_dir, work_dir=args.work_dir,
            sensitivity=not args.no_sensitivity,
            test_result={key: value for key, value in from_record.items() if key != "map_path"} or None)
        print(json.dumps(nan_check_inputs(arguments) if args.check_inputs else nan_run(arguments), indent=2))
        return EXIT_DONE
    except (ChainError, nan.NanChainError, e8.BuildError, e10.BuildError, e5.BuildError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
