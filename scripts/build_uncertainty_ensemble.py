"""Build the uncertainty ensemble of one case and report the run (plan task E10).

Plan 8.1 row E10: "uncertainty_ensemble.py + LOCO + headline rule; 540 cells per lane reported". For one case of
protocol v1a this script runs the predeclared grid of protocol v1b (``ensemble_grid``) over the reporting units of
the case, as far as the earlier tasks allow today, and reports every one of the 540 core cells of the lane: the
cells that were run, the cells that were not run with the reason, and any cell that failed.

An ensemble is planning guidance for preparedness and post-event prioritisation. It is not an official warning,
not an observation of a flood and not an operational product, and class E never means safe. A closure is a
modelled assumption, and the product 4009 layers are used as provided; FloodGuard did not validate them. A cell
is the same modelled chain run with another declared choice: the ensemble shows how far a score and a class move
under those choices, and nothing about how close they are to what happened on the ground.

**What it reads, and what it checks before it lays a flood layer over a unit.** Nothing of an earlier task is
rebuilt or rewritten. Every check of the task E8 builder is made first, through its own function
(``build_planning_assessment.prepare``): both protocols in force, every input the file its registered receipt
binds, the rights registry, an access table that says it is usable, one flood input, one routing context and one
closure rule across the stages. Then:

* the registered receipt of the task E8 run of the case, and the file it binds outside Git. That run must have
  been made from the inputs this run reads; its rows are read for one comparison only (the default cell below);
* the flood extents of task E1 at all three levels, in the reporting frame and in the routing context, each as
  the bytes the registered E1 receipt binds.

A check that fails here stops the run before any unit is measured against a flood level; the run then returns 2
and writes nothing.

**What it computes** (full-chain reruns, vehicle mode; plan 5 item 11).

* Access: the task E5 runner, unchanged (``build_access_diff.case_runs``), makes a flooded run for each of the
  three flood levels and each of the three closure levels on the baseline graph of the context of record. The
  three runs at the flood level as provided must reproduce the unit rows of the registered E5 table exactly.
* Components, FPPS and class: ``floodguard.uncertainty_ensemble.run_ensemble``, which assesses every unit of a
  combination as task E8 does and scores every cell with the scoring block of task E8. The default cell must be
  the rows the registered E8 receipt records (their SHA-256).
* Levels that cannot be run today are not approximated: the two facility sets that add shelters need a walking
  context of record (open point E5-OP5) and the pitch level, and the 2024-rescaled demand needs two rules the
  formula leaves out. Their cells are reported as not run, each with the reason.

**Where things go.** The per-unit results (every cell that was run, for every unit) and the access runs of the
minus and plus flood levels go into one file outside Git, under
``<external data root>/proposal_execution/planning_v1/<case>/e10_uncertainty_ensemble/``, beside the licence
notice of the rights record, and are bound by SHA-256 in the receipt. The receipt is
``outputs/planning_v1/e10_uncertainty_ensemble_<case>_<frame>.json``; it holds counts for the whole case and is
registered in ``outputs/planning_v1/run_register/``. Nothing is written under ``apps/web/public/``::

    python scripts/build_uncertainty_ensemble.py --case SE1 --frame mae_sai --external-data <external data root> \
        [--development-read "<what was read before this run>"] [--replace --reason "<why>"] [--verify]

Every run is reported. Once a unit has been measured against a flood level, the run writes and registers a
receipt whatever happens next, a failed check or any other error, and returns 3 when it could not compute the
ensemble: the receipt then gives the stage, a code and the type of the error, and the message is in the file
outside Git. A second run needs ``--replace --reason``; the receipt it replaces is read and checked before the
run starts, its receipt names every earlier run and a copy of the superseded files is kept outside Git. ``--verify`` computes
everything again with the generation time of the receipt, compares the file outside Git byte for byte and the
whole receipt except its run-specific fields, and writes nothing. ``--check-inputs`` makes the input checks and
writes nothing: it lays no flood layer over a unit and computes no component. Measuring the season envelope of
case SE1 against the road graph takes about ten minutes for each flood level.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_e8_builder() -> Any:
    """Load the task E8 builder as a module: its input checks and its unit measurements are used unchanged."""

    name = "build_planning_assessment"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "build_planning_assessment.py")
    if spec is None or spec.loader is None:
        raise ImportError("scripts/build_planning_assessment.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


e8_builder = _load_e8_builder()
e5_builder = e8_builder.e5_builder

from floodguard import access_diff, closure_rules, demand_rescale, flood_inputs, planning_assessment, rights  # noqa: E402
from floodguard import uncertainty_ensemble as ensemble  # noqa: E402
from floodguard.normalisation import PUBLIC_LEVEL  # noqa: E402
from floodguard.planning_overlay import is_public_web_path  # noqa: E402

RECEIPT_SCHEMA = "floodguard.uncertainty_ensemble_run_receipt.v2"
RESULTS_SCHEMA = "floodguard.uncertainty_ensemble_units.v2"
REPLACEABLE_RECEIPT_SCHEMAS: tuple[str, ...] = ("floodguard.uncertainty_ensemble_run_receipt.v1", RECEIPT_SCHEMA)
"""The receipts a second run may replace. Version 2 (after the review of 4 October 2026): a share that is labelled as
taken over the cells run keeps a failed cell in its denominator; the headline record gives the other reading of the
protocol's set and every pair of levels declared cut line 6 could keep; the receipt says which of its counts state
a value of a single unit; the distance of the minus and plus levels is read from the protocol."""
DOCS = e8_builder.DOCS
OUTPUT_DIR = e8_builder.OUTPUT_DIR
REGISTER_DIR = e8_builder.REGISTER_DIR
EXTERNAL_DATA_VARIABLE = e8_builder.EXTERNAL_DATA_VARIABLE
EXTERNAL_LABEL = e8_builder.EXTERNAL_LABEL
PROCESSED_RELATIVE_PATH = e8_builder.PROCESSED_RELATIVE_PATH
BOUNDARY_RELATIVE_PATH = e8_builder.BOUNDARY_RELATIVE_PATH
E1_STAGE_FOLDER = e8_builder.E1_STAGE_FOLDER
STAGE_FOLDER = "e10_uncertainty_ensemble"
LICENCE_NOTICE_NAME = e8_builder.LICENCE_NOTICE_NAME
SUPERSEDED_FOLDER = "superseded_runs"
PUBLIC_SERVICES = e8_builder.PUBLIC_SERVICES
FRAME_SETS = e8_builder.FRAME_SETS
LEVEL = PUBLIC_LEVEL
"""The level this builder runs: the public facility set. A pitch-level run is not built (open point E10-OP3)."""
VINTAGE_RUN = "worldpop_2020"
VINTAGE_RESCALED = demand_rescale.RESCALED_LEVEL
"""The second level of the population axis. It is run only when the folder of the WorldPop 2024 age rasters is given
(``--age-dir``): the demand is then built with the two readings of the formula that decision log R38 records and the
team accepted (R39). Without the folder the level is reported as not run, as before."""
POPULATION_2020 = Path("open_context") / "worldpop_population" / "tha_ppp_2020.tif"
RESIDENT_TOLERANCE = e8_builder.RESIDENT_TOLERANCE
EXIT_WRITTEN, EXIT_REFUSED, EXIT_NOT_COMPUTED = 0, 2, 3
"""0: the ensemble was computed and written. 2: refused before a unit was measured against a flood level; nothing
is written. 3: units were measured and the ensemble was not computed; the receipt is written and registered."""
STAGE_ACCESS, STAGE_AS_PROVIDED, STAGE_MEASUREMENT, STAGE_ENSEMBLE, STAGE_DEFAULT_CELL, STAGE_FIGURES = (
    "access_runs", "as_provided_runs_against_the_e5_table", "unit_measurements", "ensemble_cells", "default_cell_against_the_e8_rows",
    "figures_of_the_receipt")
RUN_SPECIFIC_KEYS: tuple[str, ...] = ("timing_seconds", "implementation", "development_reads")
RECEIPT_KEYS_NOT_RECOMPUTED: tuple[str, ...] = ("generated_at_utc", "run_kind", "outputs", "timestamps", "supersedes", "run_history")

COMPUTES = (
    "For one case and each of its reporting units: the cells of the predeclared grid of protocol v1b that can be run "
    "today, each with the five components of planning frame v1, FPPS, the binding class of class rule v1 with its "
    "reason code and leave-one-component-out; and from them the range of the FPPS, the share of cells in each class, "
    "the cells keeping the class of the default cell, the best and worst rank, the residents losing 30-minute access "
    "over the access runs, the FPPS swing along each axis, and the headline-stability record of guardrail GR8. The "
    "access runs of the minus and plus flood levels are made for it. No equity figure, no overlay and no accepted value."
)
CONFIDENCE_BASIS = (
    "An ensemble of planning classes from modelled access on OpenStreetMap roads, modelled resident and age counts, "
    "and closures assumed from a flood input that FloodGuard did not check against the ground or against an "
    "independent source. Every cell is the same modelled chain with another declared choice; the spread across the "
    "cells says how far the result depends on those choices and nothing about its distance from what happened. This "
    "line is the confidence of the run as evidence; the confidence class of each unit under rule v1 is in the results."
)
ONE_PIXEL_SOURCE = "planning_protocol_v1b.json /ensemble_grid/core_axes/0/one_pixel_m (owner choice 2)"


def assumptions(one_pixel_m: float) -> list[str]:
    """Return the assumptions of a run, with the distance of the minus and plus levels as the protocol states it."""

    return [
        "A closure is a modelled assumption of closure rule v1 (closure_basis), not an observed closure. A flood "
        "intersection does not prove that a road was closed.",
        "A flood input is used as provided. A product 4009 layer is a preliminary agency extent that was not checked in "
        "the field (Field_Validation=0), and FloodGuard did not validate it. The minus and plus levels are the same layer "
        f"shrunk and grown by {one_pixel_m:g} m (one pixel; protocol v1b, owner choice 2); neither is a lower or an upper "
        "bound of the water, and the level as provided is not a central estimate.",
        *ASSUMPTIONS_OF_EVERY_RUN,
    ]


ASSUMPTIONS_OF_EVERY_RUN = [
    "Residents are modelled WorldPop 2020 counts. A cell counts for the unit whose polygon holds its centre, and a "
    "resident is inside a flood extent when the cell centre is.",
    "The strict, central and permissive closure levels are the three levels of closure rule v1. None of them is a "
    "central estimate of what was passable.",
    "Every cell carries the confidence of its unit in its lane, derived as task E8 derives it. Condition C4 always "
    "compares the plus and the minus level of the flood input as provided (open point E10-OP4).",
    "Each cell is one modelled chain with one declared choice changed. The cells are not samples of a distribution: "
    "the share of cells in a class is not a probability, and the range of the FPPS is not a confidence interval.",
    "The weight presets are those of protocol v1a, normalised to sum to 1 by the scorer. The default is the published "
    "default; another preset is a sensitivity view.",
    "Planning guidance only. Not an official warning. Class E never means safe.",
]
LIMITATIONS = [
    "Only a part of the predeclared grid can be run today: the public facility set with WorldPop 2020. The cells of "
    "the two facility sets that add shelters and of the 2024-rescaled demand are reported as not run, with the "
    "reason (open points E10-OP2 and E10-OP3).",
    "The headline rule is evaluated only when every cell the protocol takes retention over has a class. Until then "
    "no class is headlined (open point E10-OP1).",
    "A resident whose cell does not snap to the vehicle graph within 250 m is in no access count.",
    "One flood input drives 4 of 5 components (90% of weight), so the flood-level axis moves four components at once.",
    "The equity figures (EED and EER) that protocol v1b lists among the per-unit outputs are plan task E9.",
]
RESCALED_NOT_COMPUTED = "the cells of the 2024-rescaled demand"
LIMITATIONS_WITH_THE_RESCALED_DEMAND = [
    "Only a part of the predeclared grid can be run today: the public facility set, with both levels of the population "
    "axis. The cells of the two facility sets that add shelters are reported as not run, with the reason (open point "
    "E10-OP3).",
    "The headline rule is evaluated on the cells of the public facility set, the set protocol v1b names for a public "
    "overlay. No published file carries its result until a result file is published again.",
    *LIMITATIONS[2:],
    "The 2024-rescaled demand follows two readings of the formula of the protocol (decision log R38), which the team "
    "accepted (R39). The two population products are two models of where residents are counted; neither was checked "
    "on the ground.",
]
NOT_COMPUTED = [
    "the cells of the two facility sets that add shelters", "the cells of the 2024-rescaled demand",
    "equity difference and ratio by age group (EED, EER)", "the terrain and remoteness proxy (case O1 only)",
    "the outcomes of class rule v2 triggers B, C and D", "an overlay", "a public projection",
    "accepted FPPS and accepted class (tier T4 is locked)", "an ensemble of case O1",
]


def change_notice_step(one_pixel_m: float) -> str:
    """Return the sentence that carries a product 4009 change notice on by the step of this task."""

    return (f"In plan task E10 the same chain was then run with the layer shrunk and grown by {one_pixel_m:g} m and under "
            "the strict, central and permissive levels of closure rule v1, and each result was scored under two pairs of "
            "vulnerability anchors and five weight presets.")


VALUES_SENTENCE = "This file holds values derived from the layer, not the layer."


class BuildError(ValueError):
    """Raised when an input is not the one a signed file or a registered receipt names, or may not be used."""


class StageError(ValueError):
    """Raised when a check stops the run after a unit was measured against a flood level: the stage and a code."""

    def __init__(self, stage: str, code: str, message: str) -> None:
        super().__init__(message)
        self.stage, self.code = stage, code


encode = e8_builder.encode
sha256_bytes = e8_builder.sha256_bytes
sha256_file = e8_builder.sha256_file
path_label = e8_builder.path_label
external_path = e8_builder.external_path
bound_outputs = e8_builder.bound_outputs


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_of(value: Any) -> str:
    """Return the SHA-256 of a JSON value in a canonical form: no generation time, no header text."""

    return sha256_bytes(_canonical(value).encode("utf-8"))


def stage_folder(case_id: str, frame_set: Any, external: Path) -> Path:
    """Return the folder outside Git that holds what this task writes for a case."""

    return external / PROCESSED_RELATIVE_PATH / frame_set.case_folders[case_id] / STAGE_FOLDER


def results_path(case_id: str, frame_set: Any, external: Path) -> Path:
    """Return the one place the per-unit results of a case are written, outside Git."""

    return stage_folder(case_id, frame_set, external) / f"uncertainty_ensemble_{case_id.lower()}_{frame_set.name}.json"


def receipt_path_for(case_id: str, frame_set: Any, output_dir: Path = OUTPUT_DIR) -> Path:
    """Return the one place the receipt of a case and frame is written."""

    return output_dir / f"e10_uncertainty_ensemble_{case_id.lower()}_{frame_set.name}.json"


# ---------------------------------------------------------------------------
# Inputs beyond those of task E8, each checked against the file that names it
# ---------------------------------------------------------------------------


def load_e8_run(case_id: str, frame_set: Any, external: Path, found: SimpleNamespace, *, output_dir: Path, register_dir: Path,
                root: Path) -> dict[str, Any]:
    """Read the registered receipt of the task E8 run of the case and the rows of the file it binds.

    The default cell of the ensemble is the row task E8 reports. The E8 run must be registered, must have been
    made under the protocol files in force and from the inputs this run reads, and must report its rows.

    Raises:
        BuildError: when the receipt is missing or not registered, names other protocol files or other
            inputs, reports no row, or the file it binds is missing or has other bytes.
    """

    name = e8_builder.receipt_path_for(case_id, frame_set, output_dir, LEVEL).name
    receipt, record = e8_builder.load_registered(name, output_dir, register_dir, root, "the receipt of the task E8 run")
    if e8_builder.protocol_hashes_named(receipt) != dict(found.hashes):
        raise BuildError("the task E8 run was made under other protocol files than the ones in force")
    here = {item["input_id"]: item["sha256"] for item in found.inputs}
    if dict(receipt.get("lineage_input_sha256") or {}) != here:
        raise BuildError("the task E8 run was made from other inputs than the ones this run reads; run task E8 again first")
    rows_digest = (receipt.get("result") or {}).get("rows_sha256")
    if not rows_digest:
        raise BuildError("the task E8 run of the case reports no row, so the ensemble has no default cell to stand on")
    rows, read_from = None, None
    for label, digest in bound_outputs(receipt["outputs"]).items():
        path = external_path(label, external) if label.startswith(EXTERNAL_LABEL) else root / label
        if path.name == LICENCE_NOTICE_NAME:
            continue
        if not path.is_file() or sha256_file(path) != digest:
            raise BuildError("the file the task E8 receipt binds is missing or is not the file it names")
        found_rows, _inputs = e8_builder.rows_and_inputs_of_a_written_file(path)
        if found_rows is not None:
            rows, read_from = found_rows, {"path": label, "sha256": digest}
    if rows is None or e8_builder.rows_sha256(rows) != rows_digest:
        raise BuildError("the rows of the task E8 run cannot be read back with the SHA-256 its receipt records")
    return {"receipt": record, "rows_sha256": rows_digest, "rows_file": read_from, "rows": rows,
            "overlay_written": bool(receipt["result"].get("overlay_written")),
            "generated_at_utc": receipt.get("generated_at_utc"),
            "note": "The rows are read for one comparison: the default cell of this run must be these rows. Every cell "
                    "is computed by this run from the inputs."}


def load_closure_extents(case_id: str, frame_set: Any, external: Path, found: SimpleNamespace) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the flood extents of the routing context at the three levels, as the registered E1 receipt binds them.

    Returns:
        ``level -> extent`` (EPSG:32647, clipped to the routing context) and what was read of each.

    Raises:
        BuildError: when an extent is not the file the E1 receipt binds, or does not state the rights level the
            registry gives its layer.
    """

    receipt, _record = e8_builder.load_registered(frame_set.e1_receipt, found.output_dir, found.register_dir, found.root,
                                                  "the E1 receipt")
    bound = bound_outputs(receipt["outputs"])
    folder = external / PROCESSED_RELATIVE_PATH / frame_set.case_folders[case_id] / E1_STAGE_FOLDER
    prefix = f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/{frame_set.case_folders[case_id]}/{E1_STAGE_FOLDER}/"
    try:
        record, extents = flood_inputs.read_written_input(folder)
    except flood_inputs.FloodInputError as error:
        raise BuildError(f"the flood input of case {case_id} cannot be read: {error}") from error
    files = {(row.get("what"), row.get("level"), row.get("frame")): row for row in record["files"]}
    read: dict[str, Any] = {}
    for level in flood_inputs.LEVELS:
        entry = files.get(("flood_extent", level, flood_inputs.ROUTING_CONTEXT))
        if entry is None or bound.get(prefix + entry["file"]) != entry["sha256"]:
            raise BuildError(f"the {level} closure extent of case {case_id} is not the one the registered E1 receipt binds")
        if entry.get("rights_level") != found.flood.grant.rights_level:
            raise BuildError(f"the {level} closure extent of case {case_id} does not state the rights level of its layer")
        read[level] = {"path": prefix + entry["file"], "sha256": entry["sha256"], "rights_level": entry.get("rights_level")}
    if read[flood_inputs.AS_PROVIDED]["sha256"] != found.flood.read["closure_extent_routing_context"]["sha256"]:
        raise BuildError("the closure extent as provided is not the one the task E8 checks read")
    return {level: extents[level][flood_inputs.ROUTING_CONTEXT] for level in flood_inputs.LEVELS}, read


def levels_not_run(grid: ensemble.EnsembleGrid, e5_receipt: Mapping[str, Any], *,
                   rescaled_demand_built: bool = False) -> list[ensemble.LevelNotRun]:
    """Say which levels of the grid cannot be run today, from what the earlier tasks have delivered.

    The shelter sets are read from the registered E5 receipt: whether the shelter service was computed and
    whether its tables are usable. The 2024-rescaled demand has no stage, and its formula leaves two points
    open. Nothing listed here is approximated.
    """

    shelter = e5_receipt.get("shelter_service") or {}
    if shelter.get("usable_by_task_e8") is True:
        basis = ("The registered E5 receipt says the shelter tables are usable, and this builder does not run a "
                 "pitch-level facility set yet: its lineage has to name the walking context and the DDPM shelter list")
    elif shelter.get("computed"):
        basis = ("The registered E5 receipt says the shelter tables rest on a candidate walking context and are not "
                 "usable until the owners accept a walking build of record (open point E5-OP5)")
    else:
        basis = "The registered E5 receipt holds no shelter table (open point E5-OP5)"
    facilities = grid.axis(ensemble.FACILITIES_AXIS).levels
    listed = [ensemble.LevelNotRun(
        ensemble.FACILITIES_AXIS, level, "facility_set_needs_a_walking_context_of_record_and_the_pitch_level",
        "This facility set adds DDPM located shelters, reached by walking within 30 minutes, at the pitch "
        f"level (protocol v1b facility_sets, owner choice 7). {basis}. "
        + ("No access table exists for the subset of the shelters this set keeps. " if level != facilities[-1] else "")
        + "The set is not approximated from the candidate tables.",
        ("E10-OP3", "E5-OP5")) for level in facilities if level != PUBLIC_LEVEL]
    if rescaled_demand_built:  # the demand of the second population level was built for this run (--age-dir)
        return listed
    vintage = [level for level in grid.axis(ensemble.VINTAGE_AXIS).levels if level != VINTAGE_RUN]
    listed += [ensemble.LevelNotRun(
        ensemble.VINTAGE_AXIS, level, "rescale_rule_leaves_two_points_open_and_no_stage_builds_the_demand",
        "The 2024-rescaled demand is not built by any stage. Its formula (protocol v1b, owner choice 12) does not say "
        "which 1 km cell a 100 m count is inside, and the two grids do not nest; nor what a positive 2020 count becomes "
        "in a 1 km cell with no 2024 total (floodguard.age_exposure.rescale_2020_counts_to_2024 decides neither). The "
        "level is not approximated.",
        ("E10-OP2",)) for level in vintage]
    return listed


def _load_script(name: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise BuildError(f"scripts/{name}.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def rescaled_residents(found: SimpleNamespace, external: Path, age_dir: Path) -> tuple[dict[str, float], dict[str, Any]]:
    """Return the 2024-rescaled resident count of every demand cell of the planning context, and the record of the rescale.

    Protocol v1b, owner choice 12, with the two readings of ``floodguard.demand_rescale`` (decision log R38, accepted
    by the team in R39). No flood layer is read: this is part of the input checks.

    Raises:
        BuildError: when the WorldPop 2020 raster is not the file of the lineage, a grid is not a north-up grid in
            EPSG:4326, or a demand cell does not carry the count of the 2020 pixel it is looked up at.
    """

    import math

    import numpy as np
    import rasterio
    from rasterio.windows import Window

    from floodguard import age_exposure

    v1b = json.loads(found.v1b_path.read_text(encoding="utf-8"))
    population_path = external / POPULATION_2020
    stated = {item["input_id"]: item["sha256"] for item in found.inputs}.get("worldpop_2020_100m")
    population_sha = sha256_file(population_path)
    if population_sha != stated:
        raise BuildError("the WorldPop 2020 raster is not the file the lineage of the case names")
    manifest_sha = v1b["national_vulnerability_anchors"]["inputs"]["age_rasters"]["manifest_sha256"]
    manifest, paths, _hashes = _load_script("build_national_vulnerability_anchors").check_age_sources(age_dir, manifest_sha)

    rows = list(found.graph.population)
    lon = np.array([float(row["longitude"]) for row in rows])
    lat = np.array([float(row["latitude"]) for row in rows])
    residents = np.array([float(row["total_population"]) for row in rows])
    rasters = {band: rasterio.open(paths[band]) for band in age_exposure.AGE_BANDS}
    try:
        first = rasters[age_exposure.AGE_BANDS[0]]
        grid = first.transform
        if grid.b != 0 or grid.d != 0 or first.crs.to_epsg() != 4326:
            raise BuildError("the 2024 age grid is not a north-up grid in EPSG:4326")
        geometry = {"west": grid.c, "north": grid.f, "cell_width": grid.a, "cell_height": -grid.e, "rows": first.height, "columns": first.width}
        cells_of_demand = demand_rescale.cell_index(lon, lat, **geometry)
        if (cells_of_demand < 0).any():
            raise BuildError("a demand cell lies outside the 2024 age grid")
        cell_rows, cell_columns = cells_of_demand // first.width, cells_of_demand % first.width
        row0, row1 = max(0, int(cell_rows.min()) - 1), min(first.height, int(cell_rows.max()) + 2)
        column0, column1 = max(0, int(cell_columns.min()) - 1), min(first.width, int(cell_columns.max()) + 2)
        totals_grid, _dependants, valid = age_exposure.read_grid_counts(rasters, Window(column0, row0, column1 - column0, row1 - row0))
    finally:
        for source in rasters.values():
            source.close()
    totals: dict[int, float | None] = {}
    for row in range(row0, row1):
        for column in range(column0, column1):
            total = float(totals_grid[row - row0, column - column0])
            totals[row * geometry["columns"] + column] = total if bool(valid[row - row0, column - column0]) else None

    west, north = geometry["west"] + column0 * geometry["cell_width"], geometry["north"] - row0 * geometry["cell_height"]
    east, south = geometry["west"] + column1 * geometry["cell_width"], geometry["north"] - row1 * geometry["cell_height"]
    with rasterio.open(population_path) as source:
        fine = source.transform
        if fine.b != 0 or fine.d != 0 or source.crs.to_epsg() != 4326:
            raise BuildError("the WorldPop 2020 raster is not a north-up grid in EPSG:4326")
        first_column, last_column = int(math.floor((west - fine.c) / fine.a)), int(math.ceil((east - fine.c) / fine.a))
        first_row, last_row = int(math.floor((fine.f - north) / -fine.e)), int(math.ceil((fine.f - south) / -fine.e))
        counts = source.read(1, window=Window(first_column, first_row, last_column - first_column, last_row - first_row),
                             boundless=True, fill_value=0).astype("float64")
        nodata = source.nodata
    counts[~np.isfinite(counts) | (counts < 0) | ((counts == nodata) if nodata is not None else False)] = 0.0
    fine_west, fine_north = fine.c + first_column * fine.a, fine.f + first_row * fine.e
    grid_x, grid_y = np.meshgrid(fine_west + (np.arange(counts.shape[1]) + 0.5) * fine.a, fine_north + (np.arange(counts.shape[0]) + 0.5) * fine.e)
    ids = demand_rescale.cell_index(grid_x, grid_y, **geometry)
    in_window = np.isin(ids, np.fromiter(totals.keys(), dtype="int64"))
    counts = np.where(in_window, counts, 0.0)  # pixels of 1 km cells that are not read whole are left out
    try:
        rescaled = demand_rescale.rescale_counts(counts, np.where(in_window, ids, -1), totals)
        pixel_column = np.floor((lon - fine_west) / fine.a).astype("int64")
        pixel_row = np.floor((fine_north - lat) / -fine.e).astype("int64")
        values = demand_rescale.demand_values(counts, rescaled["counts"], pixel_row, pixel_column, residents)
    except demand_rescale.DemandRescaleError as error:
        raise BuildError(f"the 2024-rescaled demand cannot be built: {error}") from error
    kept = rescaled["kept_at_2020"][pixel_row, pixel_column]
    record = {
        **rescaled["record"],
        "decision": "The two rules are the readings of decision log R38, accepted by the team (R39, item V-27 of the team page).",
        "scope_of_the_counts_above": "every 2020 100 m count of the 1 km cells that hold a demand cell of the planning context, and one ring of cells around them",
        "demand_cells": int(residents.size), "demand_residents_2020": math.fsum(residents.tolist()),
        "demand_residents_rescaled": math.fsum(values.tolist()),
        "demand_cells_kept_at_2020": int(kept.sum()), "demand_residents_kept_at_2020": math.fsum(residents[kept].tolist()),
        "sources": {"worldpop_2020": {"file": POPULATION_2020.as_posix(), "sha256": population_sha},
                    "worldpop_2024_age_counts": {"product": manifest.get("product"), "year_represented": manifest.get("year_represented"),
                                                 "manifest_sha256": manifest_sha, "rights_level": "public (decision log R21)",
                                                 "total": "the sum of the 20 age bands of a 1 km cell; no total where a band has no valid count"}},
    }
    return {str(row["population_id"]): float(value) for row, value in zip(rows, values)}, record


def vintages_of(found: SimpleNamespace) -> tuple[str, ...]:
    """Return the levels of the population axis a run makes: the 2020 demand, and the rescaled one when it was built."""

    return (VINTAGE_RUN, VINTAGE_RESCALED) if getattr(found, "rescaled", None) is not None else (VINTAGE_RUN,)


def prepare(case_id: str, frame_set: Any, external: Path, boundaries: Path, *, docs: Path = DOCS, root: Path = ROOT,
            output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR,
            registry: rights.RightsRegistry | None = None, age_dir: Path | None = None) -> SimpleNamespace:
    """Make every input check of a run and return what was read. No unit is measured against a flood level.

    The checks of the task E8 builder come first, through its own function; then the registered E8 run, the
    grid of the protocols in force, the closure extents of the three flood levels, and the distance by which task
    E1 shrank and grew the minus and plus levels, which must be the one protocol v1b states.

    Raises:
        BuildError, ValueError: an input check refused the run.
    """

    try:
        found = e8_builder.prepare(case_id, frame_set, external, boundaries, level=LEVEL, docs=docs, root=root,
                                   output_dir=output_dir, register_dir=register_dir, registry=registry)
    except e8_builder.BuildError as error:
        raise BuildError(str(error)) from error
    found.output_dir, found.register_dir, found.root = output_dir, register_dir, root
    grid = ensemble.load_grid(found.v1a_path, found.v1b_path, found.receipts_path)
    try:
        e8_run = load_e8_run(case_id, frame_set, external, found, output_dir=output_dir, register_dir=register_dir, root=root)
        extents, extents_read = load_closure_extents(case_id, frame_set, external, found)
        e5_receipt, _record = e8_builder.load_registered(frame_set.e5_receipt, output_dir, register_dir, root, "the E5 receipt")
    except e8_builder.BuildError as error:
        raise BuildError(str(error)) from error
    target = results_path(case_id, frame_set, external)
    if is_public_web_path(target):
        raise BuildError("this script writes nothing under apps/web/public")
    written_with = (found.record.get("levels") or {}).get("one_pixel_m")
    if not isinstance(written_with, (int, float)) or isinstance(written_with, bool) or float(written_with) != grid.one_pixel_m:
        raise BuildError(f"the input record of the flood input states the one-pixel distance {written_with!r}; protocol v1b "
                         f"states {grid.one_pixel_m:g} m for the minus and the plus level")
    found.grid, found.e8_run, found.closure_extents, found.closure_extents_read = grid, e8_run, extents, extents_read
    found.rescaled = None
    if age_dir is not None:
        if VINTAGE_RESCALED not in grid.axis(ensemble.VINTAGE_AXIS).levels:
            raise BuildError(f"the grid of the protocols has no population level named {VINTAGE_RESCALED}")
        by_cell, rescale_record = rescaled_residents(found, external, age_dir)
        found.rescaled = SimpleNamespace(by_cell=by_cell, record=rescale_record)
    found.not_run = levels_not_run(grid, e5_receipt, rescaled_demand_built=found.rescaled is not None)
    found.results_target = target
    return found


def check_inputs(case_id: str, frame_set: Any, external: Path, boundaries: Path, **arguments: Any) -> dict[str, Any]:
    """Check the inputs of a case and say what a run would do; write nothing and measure no unit against a flood level."""

    found = prepare(case_id, frame_set, external, boundaries, **arguments)
    root = arguments.get("root", ROOT)
    table = ensemble.cell_table(found.grid, run_keys(found.grid, vintages_of(found)), found.not_run)
    return {
        "inputs_checked": True, "case_id": case_id, "lane": found.case.lane, "tier": found.case.tier, "level": LEVEL,
        "units": len(found.unit_ids), "core_cells_per_lane": len(table),
        "cells_that_would_be_run": sum(1 for cell in table if cell["status"] == ensemble.STATUS_RUN),
        "cells_not_run": sum(1 for cell in table if cell["status"] == ensemble.STATUS_NOT_RUN),
        "levels_not_run": [f"{item.axis}={item.level}" for item in found.not_run],
        "access_runs_to_make": len(flood_inputs.LEVELS) * len(closure_rules.LEVELS),
        "e8_rows_sha256": found.e8_run["rows_sha256"], "publication_eligibility": found.eligibility,
        "results_would_go_to": path_label(found.results_target, root, external),
        "computed": "No flood layer was laid over a unit, no access run was made and no component was computed.",
    }


def run_keys(grid: ensemble.EnsembleGrid, vintages: Sequence[str] = (VINTAGE_RUN,)) -> list[ensemble.RoutingKey]:
    """Return the measurement combinations this builder runs: every flood level and passability, public set, each demand run."""

    return [(flood_level, passability, LEVEL, vintage)
            for flood_level in grid.axis(ensemble.FLOOD_AXIS).levels for passability in grid.axis(ensemble.PASSABILITY_AXIS).levels
            for vintage in vintages]


# ---------------------------------------------------------------------------
# One build: everything computed, nothing written
# ---------------------------------------------------------------------------


def access_runs(case_id: str, found: SimpleNamespace, services: Sequence[access_diff.ServiceRule],
                arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Make the flooded runs of every flood level and closure level with the unchanged task E5 runner."""

    graph = found.graph
    cells = [{"population_id": cell["population_id"], "unit_id": cell["unit_id"], "residents": cell["residents"]}
             for cell in found.counted.cells]
    baselines = {access_diff.VEHICLE: e5_builder.baseline_runs(graph, services)}
    alternate = None
    if getattr(found, "rescaled", None) is not None:
        # Travel times do not depend on resident counts: the same runs are counted on the rescaled demand as well.
        alternate = {VINTAGE_RESCALED: [{**cell, "residents": found.rescaled.by_cell[str(cell["population_id"])]} for cell in cells]}
    computed = e5_builder.case_runs(case_id, str(found.record["input_id"]), found.closure_extents, {access_diff.VEHICLE: graph},
                                    baselines, services, arguments, cells, list(found.unit_ids), alternate_cells=alternate)
    return {"runs": computed["runs"], "checks": computed["checks"], "timing_seconds": computed["timing_seconds"]}


def check_as_provided_runs(runs: Sequence[Mapping[str, Any]], table: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the runs of this task at the flood level as provided with the registered task E5 table.

    The unit rows and the closure result of each closure level must be the same, value for value: the access
    runs of the minus and plus levels then come from the chain that produced the table of record.

    Raises:
        StageError: when a run differs from the table.
    """

    compared = []
    for stated in table["runs"]:
        if stated["flood_level"] != flood_inputs.AS_PROVIDED:
            continue
        mine = next((run for run in runs if run["flood_level"] == flood_inputs.AS_PROVIDED
                     and run["closure_level"] == stated["closure_level"]), None)
        same_rows = mine is not None and _canonical(mine[PUBLIC_SERVICES]["units"]) == _canonical(stated["units"])
        same_closure = mine is not None and (mine["closure"][access_diff.VEHICLE]["closure_result_sha256"]
                                             == stated["closure"][access_diff.VEHICLE]["closure_result_sha256"])
        compared.append({"closure_level": stated["closure_level"], "unit_rows_same": bool(same_rows),
                         "closure_result_same": bool(same_closure)})
    if len(compared) != len(closure_rules.LEVELS) or not all(row["unit_rows_same"] and row["closure_result_same"] for row in compared):
        raise StageError(STAGE_AS_PROVIDED, "as_provided_runs_differ_from_the_e5_table",
                         "the access runs of this task at the flood level as provided do not reproduce the registered "
                         f"task E5 table: {compared}")
    return {"result": "PASS", "compared": compared,
            "what": "The three runs of this task at the flood level as provided against the unit rows and the closure "
                    "result of the registered task E5 table: the same, value for value."}


def measurements_of_the_cells(found: SimpleNamespace, runs: Sequence[Mapping[str, Any]]
                              ) -> tuple[dict[Any, Any], dict[Any, Any], dict[str, Any]]:
    """Build the measurements of every unit for every combination that is run, and compare the stages.

    Returns:
        The measurements by combination, the residents newly losing 30-minute access by combination, unit and
        service, and the checks.

    Raises:
        StageError: when an access run counts other residents or another baseline for a unit than the table of
            record, or the default combination is not the measurement task E8 makes.
    """

    rules, flood = found.rules, found.flood
    base, checks = e8_builder.unit_measurements(rules, found.flood_spec.name, found.units, found.names, flood, found.counted)
    frame = flood_inputs.frame_from_units(flood_inputs.REPORTING_FRAME, "the reporting units of the case", list(found.units), {})
    areas = {level: {unit.unit_id: flood_inputs.flooded_land_areas(frame.units[unit.unit_id], flood.extents[level], flood.water)
                     for unit in base} for level in flood_inputs.LEVELS}
    measurements: dict[Any, Any] = {}
    losing: dict[Any, Any] = {}
    differing: list[str] = []
    for run in runs:
        key = (run["flood_level"], run["closure_level"], LEVEL, VINTAGE_RUN)
        rows = {str(row["unit_id"]): row for row in run[PUBLIC_SERVICES]["units"]}
        listed, lost = [], {}
        for unit in base:
            counts = planning_assessment.access_counts_from_e5_row(rows[unit.unit_id], found.services)
            same_baseline = all(
                counts["access_gap_inputs"][service]["baseline_access_residents"] == unit.access_gap_inputs[service]["baseline_access_residents"]
                for service in found.services) and counts["residents_with_baseline_route"] == unit.residents_with_baseline_route
            if abs(counts["residents"] - unit.unit_residents) > RESIDENT_TOLERANCE or not same_baseline or (
                    counts["residents_connected_to_the_graph"] != unit.residents_connected_to_the_graph):
                differing.append(f"{unit.unit_id} at {run['flood_level']}/{run['closure_level']}")
            listed.append(ensemble.cell_measurements(
                unit,
                flooded_non_permanent_water_land_area=areas[run["flood_level"]][unit.unit_id]["flooded_non_permanent_water_land_area"],
                residents_inside_flood_extent=unit.residents_inside_flood_extent[run["flood_level"]],
                access_gap_inputs=counts["access_gap_inputs"],
                residents_losing_all_routes=counts["residents_losing_all_routes"],
                residents_with_baseline_route=counts["residents_with_baseline_route"]))
            lost[unit.unit_id] = {
                service: float(detail["thresholds_minutes"][str(ensemble.THIRTY_MINUTES)]["newly_lost_residents"])
                for service, detail in rows[unit.unit_id]["access"].items()
                if str(ensemble.THIRTY_MINUTES) in detail["thresholds_minutes"]}
        measurements[key], losing[key] = listed, lost
    if differing:
        raise StageError(STAGE_MEASUREMENT, "access_runs_count_another_baseline",
                         "guardrail GR3: an access run of this task counts other residents or another baseline for a unit "
                         f"than the table of record: {differing}")
    default_key = (flood_inputs.AS_PROVIDED, rules.reference_closure_level, LEVEL, VINTAGE_RUN)
    if measurements.get(default_key) != base:
        raise StageError(STAGE_MEASUREMENT, "default_combination_differs_from_the_e8_measurements",
                         "the measurements of the default combination are not the measurements task E8 makes")
    wanted = [(flood_level, closure_level, LEVEL, VINTAGE_RUN)
              for flood_level in flood_inputs.LEVELS for closure_level in closure_rules.LEVELS]
    if sorted(measurements) != sorted(wanted):
        raise StageError(STAGE_MEASUREMENT, "access_runs_are_not_the_nine_combinations",
                         "the access runs do not hold each flood level under each closure level once")
    # Both checks read the measurements that are handed to the ensemble, not the tables they were taken from.
    own_level = all(
        listed[position].flooded_non_permanent_water_land_area == areas[key[0]][unit.unit_id]["flooded_non_permanent_water_land_area"]
        and listed[position].residents_inside_flood_extent[flood_inputs.AS_PROVIDED] == unit.residents_inside_flood_extent[key[0]]
        for key, listed in measurements.items() for position, unit in enumerate(base))
    if not own_level:
        raise StageError(STAGE_MEASUREMENT, "a_combination_does_not_carry_the_flood_measurements_of_its_own_level",
                         "a combination was handed the flooded land or the residents inside the extent of another flood level")

    def not_smaller_at_a_larger_level(value: Any, tolerance: float) -> bool:
        return all(
            first <= second + tolerance <= third + 2 * tolerance
            for closure_level in closure_rules.LEVELS for position in range(len(base))
            for first, second, third in [tuple(value(measurements[(flood_level, closure_level, LEVEL, VINTAGE_RUN)][position])
                                               for flood_level in flood_inputs.LEVELS)])

    ordered = not_smaller_at_a_larger_level(lambda unit: unit.flooded_non_permanent_water_land_area, 1e-6)
    exposed = not_smaller_at_a_larger_level(lambda unit: unit.residents_inside_flood_extent[flood_inputs.AS_PROVIDED], 1e-9)
    return measurements, losing, {
        **checks,
        "combinations_measured": len(measurements),
        "residents_and_baseline_counts_same_in_every_access_run": True,
        "default_combination_is_the_measurement_of_task_e8": True,
        "each_combination_carries_the_flood_measurements_of_its_own_level": True,
        "flooded_land_not_smaller_at_a_larger_flood_level_in_every_unit": bool(ordered),
        "residents_inside_not_fewer_at_a_larger_flood_level_in_every_unit": bool(exposed),
        "flood_level_checks_read": "The measurements handed to the ensemble: for each unit and closure level, the flooded "
                                   "land and the residents inside the extent of the minus, the as-provided and the plus "
                                   "combination.",
    }


def rescaled_measurements(found: SimpleNamespace, runs: Sequence[Mapping[str, Any]], measurements: Mapping[Any, Any]
                          ) -> tuple[dict[Any, Any], dict[Any, Any], dict[str, Any]]:
    """Build the measurements of every unit for the combinations of the rescaled demand, from those of the 2020 demand.

    The flooded land of a unit does not depend on the demand. Its residents, the residents inside each flood level
    and its access counts are those of the rescaled demand; the access counts come from the same access runs,
    counted on the rescaled cells. The age counts of a unit, and so its vulnerability component, are unchanged.

    Raises:
        StageError: when an access run counts other rescaled residents for a unit than the rescaled demand holds.
    """

    from dataclasses import replace

    flood = found.flood
    cells = [{**cell, "residents": found.rescaled.by_cell[str(cell["population_id"])]} for cell in found.counted.cells]
    residents = planning_assessment.residents_by_unit(cells)
    inside = {level: planning_assessment.residents_by_unit(cells, flood.extents[level]) for level in flood_inputs.LEVELS}
    result: dict[Any, Any] = {}
    losing: dict[Any, Any] = {}
    differing: list[str] = []
    for run in runs:
        of_2020 = measurements[(run["flood_level"], run["closure_level"], LEVEL, VINTAGE_RUN)]
        rows = {str(row["unit_id"]): row for row in run[e5_builder.ALTERNATE_DEMAND][VINTAGE_RESCALED]["units"]}
        listed, lost = [], {}
        for unit in of_2020:
            counts = planning_assessment.access_counts_from_e5_row(rows[unit.unit_id], found.services)
            total = residents.get(unit.unit_id, 0.0)
            if abs(counts["residents"] - total) > RESIDENT_TOLERANCE:
                differing.append(f"{unit.unit_id} at {run['flood_level']}/{run['closure_level']}")
            base = replace(
                unit, unit_residents=total,
                residents_inside_flood_extent={level: inside[level].get(unit.unit_id, 0.0) for level in flood_inputs.LEVELS},
                residents_connected_to_the_graph=counts["residents_connected_to_the_graph"],
                connected_residents_without_a_hospital_route=counts["connected_residents_without_a_hospital_route"])
            listed.append(ensemble.cell_measurements(
                base, flooded_non_permanent_water_land_area=unit.flooded_non_permanent_water_land_area,
                residents_inside_flood_extent=inside[run["flood_level"]].get(unit.unit_id, 0.0),
                access_gap_inputs=counts["access_gap_inputs"],
                residents_losing_all_routes=counts["residents_losing_all_routes"],
                residents_with_baseline_route=counts["residents_with_baseline_route"]))
            lost[unit.unit_id] = {
                service: float(detail["thresholds_minutes"][str(ensemble.THIRTY_MINUTES)]["newly_lost_residents"])
                for service, detail in rows[unit.unit_id]["access"].items()
                if str(ensemble.THIRTY_MINUTES) in detail["thresholds_minutes"]}
        key = (run["flood_level"], run["closure_level"], LEVEL, VINTAGE_RESCALED)
        result[key], losing[key] = listed, lost
    if differing:
        raise StageError(STAGE_MEASUREMENT, "access_runs_count_other_rescaled_residents",
                         "an access run counts other rescaled residents for a unit than the rescaled demand holds: "
                         f"{differing}")
    # The receipt names no unit beside a value, so the residents of each unit under the rescaled demand are not put here;
    # they are in the file of per-unit results (the unit_residents of every cell of the rescaled demand).
    return result, losing, {"combinations_measured": len(result),
                            "unit_residents_same_in_the_rescaled_demand_and_the_access_tables": True,
                            "residents_in_the_units": math.fsum(residents.values())}


def whole_frame_access(runs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the closure counts and the whole-frame counts of every access run, as the task E5 receipt gives them."""

    summary = e5_builder.whole_frame_summary(runs)
    for item, run in zip(summary, runs):
        frame = run[PUBLIC_SERVICES]["whole_frame"]["access"]
        item["newly_lost_residents_within_30_minutes"] = {
            service: detail["thresholds_minutes"][str(ensemble.THIRTY_MINUTES)]["newly_lost_residents"]
            for service, detail in frame.items() if str(ensemble.THIRTY_MINUTES) in detail["thresholds_minutes"]}
    return summary


def cells_by_status(table: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Group the identifiers of the 540 core cells by status, and the cells not run by their reasons."""

    not_run: dict[str, list[str]] = {}
    for cell in table:
        if cell["status"] == ensemble.STATUS_NOT_RUN:
            not_run.setdefault("+".join(cell["not_run_because"]), []).append(cell["cell_id"])
    return {
        "cell_id": "The six levels of a cell, in the order of the axes: " + "|".join(ensemble.AXES),
        "run": [cell["cell_id"] for cell in table if cell["status"] == ensemble.STATUS_RUN],
        "not_run": {reason: identifiers for reason, identifiers in sorted(not_run.items())},
    }


def counts_of_single_units(single_units: Mapping[str, Any] | None) -> dict[str, Any]:
    """Say what the whole-case counts of a receipt state about single units (open point E10-OP10).

    ``single_units`` is ``summary.counts_that_state_a_value_of_a_single_unit`` of the ensemble, or ``None`` for
    a run that computed no ensemble. The receipt names no unit beside a value; this block says which of its
    counts state the class of a single unit all the same, so that nobody reads the receipt as holding none.
    """

    if single_units is None:
        return {"states_a_value_of_a_single_unit": False, "cells_in_which_every_unit_has_one_class": 0,
                "classes_one_unit_alone_holds_in_the_default_cell": [], "cells_in_which_such_a_class_has_another_count": 0,
                "cells_whose_class_counts_differ_from_the_default_cell": 0, "units_with_more_than_one_class_over_the_cells_run": 0,
                "what": "The run computed no ensemble, so the receipt holds no count of units by class."}
    return {
        **{key: single_units[key] for key in (
            "states_a_value_of_a_single_unit", "cells_in_which_every_unit_has_one_class",
            "classes_one_unit_alone_holds_in_the_default_cell", "cells_in_which_such_a_class_has_another_count",
            "cells_whose_class_counts_differ_from_the_default_cell", "units_with_more_than_one_class_over_the_cells_run")},
        "what": single_units["what"],
        "where": "result.summary.class_counts_by_cell, read with reference_class_counts, class_counts_over_every_unit_cell, "
                 "units_by_number_of_classes_over_the_cells_run and retention_over_the_cells_run of the same summary.",
        "who_can_read_them": "Whoever knows the class of each unit in the default cell, which is the row of the task E8 run "
                             "of the case. Those rows are in a file outside Git; where committed files let a reader work "
                             "them out (the README of the output folder says so for each case), the counts here follow "
                             "single units through the cells.",
        "cannot_be_rebuilt_from_committed_files": "The class of a unit in a cell of the minus or plus flood level rests on "
                                                  "the access runs of that level, whose unit rows are outside Git (open "
                                                  "point E10-OP8). What these counts state of such a cell cannot be worked "
                                                  "out from the other committed files.",
    }


def licence_of_the_run(found: SimpleNamespace) -> dict[str, Any] | None:
    """Return the licence, the credit and the change notice of a run whose flood input is product 4009.

    The block is the one the task E8 receipts carry, with the change notice carried on by the step of this task.
    """

    if found.licence is None:
        return None
    notice = str(found.licence["change_notice"])
    step = change_notice_step(found.grid.one_pixel_m)
    carried = notice.replace(VALUES_SENTENCE, f"{step} {VALUES_SENTENCE}") if VALUES_SENTENCE in notice else f"{notice} {step}"
    return {
        **found.licence,
        "applies_to": "Every figure of this run that is derived from UNOSAT/GISTDA product 4009: the closure counts, the "
                      "whole-frame resident counts and the counts of units and cells by class in this file, and every "
                      "component value, FPPS, class and access count in the file this run wrote outside Git.",
        "change_notice": carried,
        "where_the_values_are": "The counts for the whole case are in this receipt (access_runs, result). The values of each "
                                "unit are in the file this receipt binds (outputs), which carries the same licence, credit "
                                "and change notice.",
    }


def build(case_id: str, frame_set: Any, external: Path, boundaries: Path, *, generated_at_utc: str, docs: Path = DOCS,
          root: Path = ROOT, output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR,
          registry: rights.RightsRegistry | None = None, git_commit: str | None = None,
          development_reads: Sequence[str] = (), age_dir: Path | None = None) -> SimpleNamespace:
    """Check every input, make the access runs, run the ensemble and assemble the receipt (nothing is written).

    The input checks of :func:`prepare` raise, and the caller then writes nothing. From the first access run on,
    nothing raises to the caller: whatever stops the run, a check of this builder or any other error, is
    reported in the receipt, with the stage, a code and the type of the error, because every run on real units
    is reported.

    Raises:
        BuildError, ValueError: see :func:`prepare`. No unit was measured against a flood level.
    """

    found = prepare(case_id, frame_set, external, boundaries, docs=docs, root=root, output_dir=output_dir,
                    register_dir=register_dir, registry=registry, age_dir=age_dir)
    rules, grid, case, record, flood = found.rules, found.grid, found.case, found.record, found.flood
    timings: dict[str, Any] = dict(found.timings)
    commit = git_commit or e8_builder.head_commit(root)
    v1a = json.loads(found.v1a_path.read_text(encoding="utf-8"))
    v1b = json.loads(found.v1b_path.read_text(encoding="utf-8"))
    table = ensemble.cell_table(grid, run_keys(grid, vintages_of(found)), found.not_run)
    services = access_diff.service_rules(v1a, v1b)
    arguments = access_diff.closure_arguments(v1b)

    stage = STAGE_ACCESS
    refusal: dict[str, Any] | None = None
    refusal_for_the_receipt: dict[str, Any] | None = None
    access: dict[str, Any] | None = None
    as_provided_check: dict[str, Any] | None = None
    measurement_checks: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    default_cell_check: dict[str, Any] | None = None
    figures: dict[str, Any] | None = None
    try:
        clock = time.perf_counter()
        access = access_runs(case_id, found, services, arguments)
        timings["access_runs"] = round(time.perf_counter() - clock, 1)
        timings["access"] = access["timing_seconds"]
        stage = STAGE_AS_PROVIDED
        as_provided_check = check_as_provided_runs(access["runs"], found.access_table)
        stage = STAGE_MEASUREMENT
        clock = time.perf_counter()
        measurements, losing, measurement_checks = measurements_of_the_cells(found, access["runs"])
        if found.rescaled is not None:
            more, more_losing, more_checks = rescaled_measurements(found, access["runs"], measurements)
            measurements, losing = {**measurements, **more}, {**losing, **more_losing}
            measurement_checks = {**measurement_checks, "rescaled_demand": more_checks}
        timings["units_measured_at_three_flood_levels"] = round(time.perf_counter() - clock, 1)
        stage = STAGE_ENSEMBLE
        clock = time.perf_counter()
        result = ensemble.run_ensemble(grid, rules, case, found.flood_spec, measurements, routing_context_id=found.context_id,
                                       level=LEVEL, not_run=found.not_run, people_losing_access=losing)
        timings["cells_scored"] = round(time.perf_counter() - clock, 1)
        stage = STAGE_DEFAULT_CELL
        digest = e8_builder.rows_sha256(result["reference_rows"])
        if digest != found.e8_run["rows_sha256"]:
            raise StageError(STAGE_DEFAULT_CELL, "default_cell_differs_from_the_e8_rows",
                             "the rows of the default cell do not have the SHA-256 the registered task E8 receipt records")
        default_cell_check = {
            "result": "PASS", "rows": len(result["reference_rows"]), "rows_sha256": digest,
            "what": "The rows of the default cell, assembled by this run from the inputs, have the SHA-256 of the rows "
                    "the registered task E8 receipt records: every value of every unit, leave-one-component-out included."}
        stage = STAGE_FIGURES
        figures = {
            "access_summary": whole_frame_access(access["runs"]),
            "edges_ordered": _edges_ordered(access["runs"]),
            "access_unit_rows_sha256": digest_of([{"flood_level": run["flood_level"], "closure_level": run["closure_level"],
                                                    "units": run[PUBLIC_SERVICES]["units"]} for run in access["runs"]]),
            "units_sha256": digest_of(result["units"]),
            "single_units": dict(result["summary"]["counts_that_state_a_value_of_a_single_unit"]),
        }
    except Exception as error:  # noqa: BLE001 - every run on real units is reported, whatever stopped it
        # Not only the refusal of a check (a ValueError): an error of a geometry library, a missing key or a file that
        # cannot be read would otherwise end a run on real units with a traceback and no receipt.
        expected = isinstance(error, ValueError)
        code = error.code if isinstance(error, StageError) else "check_failed" if expected else "unexpected_error"
        stage = error.stage if isinstance(error, StageError) else stage
        result, default_cell_check, access, as_provided_check, measurement_checks, figures = None, None, None, None, None, None
        refusal = {"code": code, "stage": stage, "error": type(error).__name__, "message": str(error)}
        refusal_for_the_receipt = {
            "code": code, "stage": stage, "error": type(error).__name__,
            "message": ("A check stopped the run" if expected else "An error that is not a check of this builder stopped the run")
                       + " after its units had been measured against a flood level. The run is "
                       "reported here because every run on real units is reported. No figure of the run is reported, "
                       "for a unit or for the whole frame: a result that fails a check is not a result. The message of "
                       "the " + ("check" if expected else "error") + ", which may name units, is in the file outside Git "
                       "that this receipt binds."}

    summary = None if result is None else result["summary"]
    below_public = found.eligibility != rights.PUBLIC_LEVEL
    single_units = None if figures is None else figures["single_units"]
    access_summary = None if figures is None else figures["access_summary"]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "plan_task": "E10: uncertainty_ensemble.py + LOCO + headline rule; 540 cells per lane reported",
        "status": "run_receipt",
        "status_note": "Written with protocol v1a and v1b in force (protocol_sha256). The run computed an FPPS and a class "
                       "for real units in every cell of the ensemble that can be run today, which protocol v1b allows "
                       "since it is in force; every run is reported, and so is every cell.",
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "computes": COMPUTES,
        "source_timestamp": str(record["source_timestamp"]),
        "source_timestamps": {
            "flood_input": str(record["source_timestamp"]),
            "osm_retrieved_at_utc": found.context_record.get("osm_retrieved_at_utc"),
            "population_year_represented": 2020,
            "age_counts": found.age_read.get("source_timestamp"),
            "permanent_water": flood.water_properties.get("source_timestamp"),
        },
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "protocol_sha256": found.hashes,
        "licence": licence_of_the_run(found),
        "parameters": {
            "case_id": case_id,
            "frame_set": frame_set.name,
            "lane": case.lane,
            "tier": case.tier,
            "case_reference_date": None if case.case_reference_date is None else case.case_reference_date.isoformat(),
            "unit_ids": sorted(found.unit_ids),
            "level": LEVEL,
            "services": found.services,
            "grid": ensemble.grid_record(grid),
            "levels_run": {axis.name: [level for level in axis.levels
                                       if not any(item.axis == axis.name and item.level == level for item in found.not_run)]
                           for axis in grid.axes},
            "levels_not_run": [item.as_record() for item in found.not_run],
            "one_pixel_m": {"minus": grid.one_pixel_m, "plus": grid.one_pixel_m, "source": ONE_PIXEL_SOURCE,
                            "input_record_of_task_e1": record["levels"]["one_pixel_m"],
                            "note": "The levels are those task E1 wrote; its input record states the same distance."},
            "closure_rule": {"version": closure_rules.CLOSURE_RULE_VERSION, "levels": list(closure_rules.LEVELS),
                             "length_thresholds_m": arguments["length_thresholds_m"], "delay_factor_k": arguments["delay_factor_k"],
                             "strict_delay_rule": arguments["strict_delay_rule"],
                             "culvert_tag_handling": arguments["culvert_tag_handling"]},
            "access_services": [rule.as_record() for rule in services],
            "normalisation_version": found.frame.version,
            "confidence_rule_version": rules.binding.rule.version,
            "class_rule_binding": "class_rule_v1 (floodguard.scoring.assign_action_class, unchanged)",
            "headline_rule": {"class_retention_min": grid.class_retention_min,
                              "evaluated_only_when": "every cell of the set the protocol names has a class (open point E10-OP1)"},
            "tolerances": {"residents_between_two_stages": RESIDENT_TOLERANCE,
                           "note": "A choice of this task, not a rule of the protocols."},
        },
        "inputs": {
            "planning_protocol_v1a": {"path": path_label(found.v1a_path, root, external), "sha256": found.hashes["planning_protocol_v1a"]},
            "planning_protocol_v1b": {"path": path_label(found.v1b_path, root, external), "sha256": found.hashes["planning_protocol_v1b"]},
            "protocol_receipts": {"path": path_label(found.receipts_path, root, external), "sha256": sha256_file(found.receipts_path)},
            "e8_run": {key: value for key, value in found.e8_run.items() if key != "rows"},
            "flood_input": flood.read,
            "closure_extents_routing_context": found.closure_extents_read,
            "access_table_as_provided": found.access_read,
            "age_table": found.age_read,
            "national_anchors": found.anchors,
            "planning_context_vehicle": {key: value for key, value in found.context_record.items() if key != "graph"},
            "tambon_boundaries": {**found.boundary, **found.unit_summary},
            "rights_record": {"input_id": flood.grant.input_id, "layer": flood.grant.layer, "path": flood.grant.record_path,
                              "sha256": flood.grant.record_sha256, "record_status": flood.grant.record_status},
        },
        "rights": {
            "registry": "floodguard.rights.REGISTERED_RECORDS",
            "rule": "Protocol v1a guardrail GR6: the rights level of an output is the minimum across its lineage. The "
                    "lineage is that of the task E8 run of the case, with the minus and plus extents of the same flood "
                    "layer. This task writes the per-unit results outside Git at every level and binds them here by "
                    "SHA-256; whether a copy goes into Git once the lineage is public is for the owners (open points "
                    "E8-OP5 and E10-OP8). Nothing is written under apps/web/public/.",
            "publication_eligibility": found.eligibility,
            "lineage_levels": {item["input_id"]: item["rights_level"] for item in found.inputs},
            "closure_extents": {level: entry["rights_level"] for level, entry in found.closure_extents_read.items()},
            "flood_layer": {"rights_level": flood.grant.rights_level, "basis": flood.grant.rights_level_basis},
            "levels_and_git": rights.LEVELS_AND_GIT,
            "figures_of_local_level_layers_in_this_receipt": {
                "what": "This receipt is committed. It holds the closure counts and whole-frame resident counts of the "
                        "access runs, and counts of units and cells for the whole case. It names no unit beside a value. "
                        "Some of its counts state a value of a single unit all the same "
                        "(counts_that_state_a_value_of_a_single_unit). When the lineage is below the public level those "
                        "counts come from a lineage below the public level; the file that holds the values of each unit "
                        "is outside Git.",
                "figures": ([{"where": "access_runs and result.summary", "publication_eligibility": found.eligibility,
                              "flood_layer_rights_level": flood.grant.rights_level,
                              "figures": "The closure counts and whole-frame resident counts of nine access runs; the number "
                                         "of units by class in each cell, by retention and by headline status."}]
                            if below_public and access_summary is not None else []),
                "counts_that_state_a_value_of_a_single_unit": counts_of_single_units(single_units),
                "what_the_counts_give_away": "In a cell where every unit of the case has one class, the class count states "
                                             "the class of each unit listed in parameters.unit_ids, and so does a count of "
                                             "units that covers every unit. A class that one unit alone holds in the "
                                             "default cell marks that unit, and its count in each cell says whether the "
                                             "unit holds it there. For those counts the receipt in Git says the same as "
                                             "the file outside Git (open points E8-OP7 and E10-OP10).",
                "for_the_owners": "Open points E1-OP1, E8-OP5, E8-OP7 and E10-OP10: whether a level below public allows "
                                  "these counts in Git.",
            },
            "written_under_apps_web_public": False,
        },
        "lane_purity": found.lane_purity,
        "lineage_input_sha256": {item["input_id"]: item["sha256"] for item in found.inputs},
        "graph": found.graph.record,
        "cells": cells_by_status(table),
        "access_runs": None if access is None else {
            "what": "Nine flooded runs on the baseline vehicle graph of the context of record: three flood levels by three "
                    "closure levels, public services. Closure counts and whole-frame counts; inputs of two components, "
                    "not component values. The unit rows of the minus and plus levels are in the file outside Git; those "
                    "of the level as provided are the registered task E5 table.",
            "runs": access_summary,
            "checks": {
                "as_provided_runs_against_the_e5_table": as_provided_check,
                "against_calculate_total_access": access["checks"]["reference"],
                "against_calculate_total_access_all_same": all(row["same"] for row in access["checks"]["reference"]),
                "shorter_routes_in_a_flooded_run": access["checks"]["shorter_routes_in_a_flooded_run"],
                "residents_gaining_access": access["checks"]["residents_gaining_access"],
                "intersected_edges_not_fewer_at_a_larger_flood_level": figures["edges_ordered"],
            },
            "unit_rows_sha256": figures["access_unit_rows_sha256"],
        },
        "measurement_checks": measurement_checks,
        "result": {
            "computed": result is not None,
            "not_computed_because": refusal_for_the_receipt,
            "default_cell_against_the_e8_rows": default_cell_check,
            "summary": summary,
            "units_sha256": None if figures is None else figures["units_sha256"],
            "units_sha256_note": "The SHA-256 of the per-unit results alone, in a canonical form: every value of every unit "
                                 "in every cell, without the generation time and the header text of the file that holds "
                                 "them. Two runs that computed the same results have the same value here.",
        },
        "development_reads": {
            "what": "Reads of the same inputs made while the code was written, before this run. They are listed because "
                    "every run is reported.",
            "reads": list(development_reads),
        },
        "open_points": [dict(point) for point in ensemble.OPEN_POINTS],
        "not_computed": NOT_COMPUTED,
        "assumptions": assumptions(grid.one_pixel_m),
        "limitations": LIMITATIONS,
        "implementation": {
            "base_commit": commit,
            "base_commit_note": "The commit the working tree was on. The files below are the ones this run loaded, "
                                "identified by their own SHA-256, committed or not.",
            "builder_sha256": sha256_file(Path(__file__)),
            "e8_builder_sha256": sha256_file(ROOT / "scripts" / "build_planning_assessment.py"),
            "e5_builder_sha256": sha256_file(ROOT / "scripts" / "build_access_diff.py"),
            **{f"{name}_module_sha256": sha256_file(ROOT / "src" / "floodguard" / f"{name}.py")
               for name in ("uncertainty_ensemble", "planning_assessment", "planning_overlay", "normalisation", "confidence",
                            "scoring", "sensitivity", "flood_inputs", "access_diff", "closure_rules", "rights", "rights_basis")},
            "ensemble_version": ensemble.ENSEMBLE_VERSION,
            "software": e8_builder.software_versions(),
        },
        "timing_seconds": timings,
    }
    if found.rescaled is not None:
        # Everything a run with the rescaled demand adds to the receipt is added here, so that a run without it
        # writes the receipt it wrote before and an earlier receipt still verifies.
        receipt["source_timestamps"]["population_rescaled_to_year"] = 2024
        receipt["parameters"]["rescaled_demand"] = dict(found.rescaled.record)
        receipt["not_computed"] = [item for item in NOT_COMPUTED if item != RESCALED_NOT_COMPUTED]
        receipt["limitations"] = LIMITATIONS_WITH_THE_RESCALED_DEMAND
        receipt["assumptions"] = [
            *receipt["assumptions"], *demand_rescale.RULES,
            "In the cells of the rescaled demand the residents of a cell are its WorldPop 2020 count multiplied by the ratio of "
            "its 1 km cell (WorldPop 2024 total over the 2020 sum). Travel times do not depend on the demand, so the nine "
            "access runs serve both demands. The age counts of a unit, and so its vulnerability component, are the same "
            "for both."]
        receipt["open_points_answered_for_this_run"] = [{
            "id": "E10-OP2", "answer": "The two points the formula leaves open were read as decision log R38 records, and the "
            "team accepted the readings (R39, item V-27 of the team page)."}]
    document = results_document(case_id, frame_set, found, receipt, result, access, refusal, generated_at_utc=generated_at_utc,
                                receipt_label=path_label(receipt_path_for(case_id, frame_set, output_dir), root, None))
    return SimpleNamespace(receipt=receipt, document=document, target=found.results_target,
                           target_label=path_label(found.results_target, root, external), notice=found.notice,
                           computed=result is not None, refusal=refusal, generated_at_utc=generated_at_utc)


def _edges_ordered(runs: Sequence[Mapping[str, Any]]) -> bool:
    """Whether a larger flood level never intersects fewer edges: the minus extent lies inside the plus extent."""

    by_level = {run["flood_level"]: run["closure"][access_diff.VEHICLE]["intersected_edges"] for run in runs}
    counts = [by_level[level] for level in flood_inputs.LEVELS if level in by_level]
    return counts == sorted(counts)


def results_document(case_id: str, frame_set: Any, found: SimpleNamespace, receipt: Mapping[str, Any],
                     result: Mapping[str, Any] | None, access: Mapping[str, Any] | None, refusal: Mapping[str, Any] | None, *,
                     generated_at_utc: str, receipt_label: str) -> dict[str, Any]:
    """Assemble the file of per-unit results: every cell that was run for every unit, and the new access runs."""

    licence = receipt.get("licence")
    if licence is not None:
        licence = {**licence, "where_the_values_are": "In this file: units (every cell of every unit) and access_runs."}
    new_runs = None
    if access is not None:
        new_runs = [{"flood_level": run["flood_level"], "closure_level": run["closure_level"], "closure_basis": run["closure_basis"],
                     "closure": run["closure"], **run[PUBLIC_SERVICES]}
                    for run in access["runs"] if run["flood_level"] != flood_inputs.AS_PROVIDED]
    return {
        "schema_version": RESULTS_SCHEMA,
        "what": ("The uncertainty ensemble of one case: for every reporting unit, every cell of the predeclared grid that "
                 "was run, with its FPPS, class and leave-one-component-out, and the summaries protocol v1b names. It is "
                 "not an overlay and no page reads it." if result is not None else
                 "The ensemble of this run was not computed. This file says why."),
        "case_id": case_id,
        "frame_set": frame_set.name,
        "lane": found.case.lane,
        "tier": found.case.tier,
        "generated_at_utc": generated_at_utc,
        "receipt_file": receipt_label,
        "source_timestamp": receipt["source_timestamp"],
        "source_timestamps": receipt["source_timestamps"],
        "confidence_class": receipt["confidence_class"],
        "confidence_basis": receipt["confidence_basis"],
        "assumptions": list(receipt["assumptions"]),
        "limitations": list(receipt["limitations"]),
        "protocol_sha256": receipt["protocol_sha256"],
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "accepted_fpps": None,
        "accepted_action_class": None,
        "publication_eligibility": receipt["rights"]["publication_eligibility"],
        "licence": licence,
        "lane_disclosure": found.frame.lane_disclosure,
        "class_e_wording": planning_assessment.CLASS_E_WORDING,
        "not_computed_because": refusal,
        "ensemble_version": ensemble.ENSEMBLE_VERSION,
        "level": LEVEL,
        "grid": None if result is None else result["grid"],
        "levels_not_run": receipt["parameters"]["levels_not_run"],
        "cells": None if result is None else result["cells"],
        "summary": None if result is None else result["summary"],
        "units": None if result is None else result["units"],
        "access_runs": {
            "what": "The unit rows of the access runs this task made at the minus and plus flood levels, as the task E5 "
                    "runner writes them: counts of residents, no ratio. The runs at the level as provided are the "
                    "registered task E5 table.",
            "services": receipt["parameters"]["access_services"],
            "runs": new_runs,
        },
        "open_points": [dict(point) for point in ensemble.OPEN_POINTS],
    }


# ---------------------------------------------------------------------------
# Run, verify, command line
# ---------------------------------------------------------------------------


def _outputs(built: SimpleNamespace, root: Path, external: Path) -> tuple[dict[str, Any], dict[Path, bytes]]:
    """Return the outputs block of the receipt and the files to write, by path."""

    data = encode(built.document)
    files: dict[Path, bytes] = {built.target: data}
    summary = built.receipt["result"]["summary"]
    listed: list[dict[str, Any]] = [{
        "path": built.target_label, "sha256": sha256_bytes(data), "bytes": len(data),
        "what": "uncertainty_ensemble_units" if built.computed else "ensemble_not_computed_report", "in_git": False,
        "publication_eligibility": built.receipt["rights"]["publication_eligibility"],
        "units": None if summary is None else summary["units"], "cells_run": None if summary is None else summary["cells_run"]}]
    if built.notice is not None:
        target = built.target.parent / LICENCE_NOTICE_NAME
        files[target] = built.notice
        listed.append({"path": path_label(target, root, external), "sha256": sha256_bytes(built.notice),
                       "bytes": len(built.notice), "what": "licence_notice", "in_git": False})
    return {"ensemble": {"files": listed}}, files


def receipt_to_replace(receipt_path: Path, case_id: str) -> tuple[dict[str, Any], str, dict[str, str]]:
    """Read the receipt a second run replaces and check it, before any unit is measured.

    A receipt that cannot be read, is not a receipt of this task for the case, or does not bind its outputs
    refuses the run here, so that nothing found in the old receipt can stop a run after its units were measured.

    Returns:
        The parsed receipt, its SHA-256 and the outputs it binds (label to SHA-256).

    Raises:
        BuildError: when the receipt cannot be read or is not a receipt of this task for the case.
    """

    try:
        data = receipt_path.read_bytes()
        previous = json.loads(data.decode("ascii"))
    except (OSError, ValueError) as error:
        raise BuildError(f"the receipt to replace cannot be read ({type(error).__name__}); nothing was measured") from error
    if (not isinstance(previous, dict) or previous.get("schema_version") not in REPLACEABLE_RECEIPT_SCHEMAS
            or (previous.get("parameters") or {}).get("case_id") != case_id):
        raise BuildError(f"the receipt to replace is not a receipt of this task for case {case_id}; nothing was measured")
    try:
        bound = dict(bound_outputs(previous["outputs"]))
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise BuildError(f"the receipt to replace does not bind its outputs ({type(error).__name__}); nothing was measured") from error
    history = previous.get("run_history") or []
    if not isinstance(history, list) or not all(isinstance(entry, dict) for entry in history):
        raise BuildError("the receipt to replace does not list its earlier runs as records; nothing was measured")
    return previous, sha256_bytes(data), bound


def cells_digest(units: Any) -> str | None:
    """Return the SHA-256 of every cell of every unit alone: FPPS, class, reason code and leave-one-component-out.

    The summaries of a unit record (headline, shares, ranks) are left out, so two runs that scored every cell
    the same have the same value here even when the record gained or lost a summary field.
    """

    try:
        return digest_of([{"unit_id": unit["unit_id"], "cells": unit["cells"]} for unit in units])
    except (KeyError, TypeError, ValueError):
        return None


def unit_fields_that_differ(old_units: Any, new_units: Any) -> list[str] | None:
    """Return the fields of the per-unit records whose value differs between two runs, in any unit; None if not comparable."""

    try:
        if [unit["unit_id"] for unit in old_units] != [unit["unit_id"] for unit in new_units]:
            return None
        return sorted({key for old, new in zip(old_units, new_units) for key in {*old, *new}
                       if key not in old or key not in new or _canonical(old[key]) != _canonical(new[key])})
    except (KeyError, TypeError, ValueError):
        return None


def superseded_run(previous: Mapping[str, Any], receipt_sha256: str, bound: Mapping[str, str], receipt_path: Path,
                   built: SimpleNamespace, replace_reason: str, archive: Path, *, root: Path, external: Path) -> dict[str, Any]:
    """Describe the run a new run replaces, compare the two and keep a copy of the replaced files outside Git.

    The old receipt was read and checked before the run (:func:`receipt_to_replace`). Nothing here raises: a
    file that cannot be copied or read back is reported as such, because the run it belongs to is reported.
    """

    stamp = str(previous.get("generated_at_utc", "unknown")).replace(":", "").replace("-", "")
    folder = archive / stamp
    kept: list[dict[str, Any]] = []
    old_units: Any = None

    def keep(source: Path, sha256: str, what: str) -> None:
        entry = {"path": path_label(folder / source.name, root, external), "sha256": sha256, "what": what, "copied": True}
        try:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, folder / source.name)
        except OSError as error:
            entry.update({"copied": False, "error": type(error).__name__})
        kept.append(entry)

    keep(receipt_path, receipt_sha256, "receipt")
    for label, digest in bound.items():
        path = external_path(label, external) if label.startswith(EXTERNAL_LABEL) else root / label
        try:
            same = path.is_file() and sha256_file(path) == digest
        except OSError:
            same = False
        if not same:
            kept.append({"path": label, "sha256": digest, "what": "file the receipt bound", "copied": False,
                         "error": "the file is missing or no longer has the bytes the receipt bound"})
            continue
        keep(path, digest, "file the receipt bound")
        if path.name != LICENCE_NOTICE_NAME:
            try:
                old_units = json.loads(path.read_text(encoding="ascii")).get("units")
            except (OSError, ValueError, AttributeError):
                old_units = None
    old, new = previous.get("result") or {}, built.receipt["result"]
    new_units = built.document.get("units")
    units_same = None if not old.get("units_sha256") or not new.get("units_sha256") else old["units_sha256"] == new["units_sha256"]
    old_cells = None if old_units is None else cells_digest(old_units)
    new_cells = None if new_units is None else cells_digest(new_units)
    summary_same = _canonical(old.get("summary")) == _canonical(new.get("summary"))
    old_summary, new_summary = old.get("summary") or {}, new.get("summary") or {}
    old_access = (previous.get("access_runs") or {}).get("unit_rows_sha256")
    new_access = (built.receipt.get("access_runs") or {}).get("unit_rows_sha256")
    return {
        "receipt_sha256": receipt_sha256,
        "generated_at_utc": previous.get("generated_at_utc"),
        "reason": replace_reason,
        "result_same": bool(summary_same and units_same is True),
        "summary_same": summary_same,
        "summary_fields_that_differ": sorted(key for key in {*old_summary, *new_summary}
                                             if key not in old_summary or key not in new_summary
                                             or _canonical(old_summary[key]) != _canonical(new_summary[key])),
        "units_same": units_same,
        "units_sha256_of_the_superseded_run": old.get("units_sha256"),
        "units_sha256_of_this_run": new.get("units_sha256"),
        "unit_cells_same": None if old_cells is None or new_cells is None else old_cells == new_cells,
        "unit_cells_sha256_of_the_superseded_run": old_cells,
        "unit_cells_sha256_of_this_run": new_cells,
        "unit_record_fields_that_differ": None if old_units is None or new_units is None else unit_fields_that_differ(old_units, new_units),
        "access_unit_rows_same": None if old_access is None or new_access is None else old_access == new_access,
        "lineage_inputs_same": dict(previous.get("lineage_input_sha256") or {}) == dict(built.receipt["lineage_input_sha256"]),
        "outputs_of_the_superseded_run": dict(bound),
        "copies_kept_outside_git": kept,
        "note": "result_same is true only when the counts of the whole case are the same (summary_same) and the per-unit "
                "results are the same (units_same: the SHA-256 of the results alone, which covers every value of every "
                "unit in every cell and every summary of a unit). unit_cells_same compares the cells alone, read back "
                "from the file the superseded receipt bound: the FPPS, the class, the reason code and "
                "leave-one-component-out of every unit in every cell that was run, without the summaries of a unit; "
                "unit_record_fields_that_differ and summary_fields_that_differ name the fields whose value changed, was "
                "added or was dropped. The superseded receipt is named by its SHA-256 and copied outside Git with the "
                "files it bound; run_history lists every earlier run.",
    }


def run(case_id: str, frame_set: Any, external: Path, boundaries: Path, *, docs: Path = DOCS, root: Path = ROOT,
        output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR, registry: rights.RightsRegistry | None = None,
        git_commit: str | None = None, replace_reason: str | None = None, development_reads: Sequence[str] = (),
        age_dir: Path | None = None) -> dict[str, Any]:
    """Check the inputs, compute the ensemble, write its file and its receipt and register the receipt.

    Once a unit has been measured against a flood level, the receipt is written and registered whatever the run
    found (:func:`build`). Every run is reported. The receipt a second run replaces is read and checked before
    the run starts, so nothing in it can stop the run later.

    Raises:
        FileExistsError: when the receipt exists and no replacement reason is given.
        FileNotFoundError: when a replacement is asked for and no receipt exists.
        BuildError, ValueError: an input check refused the run, or the receipt to replace cannot be read;
            nothing is written and no unit was measured.
    """

    receipt_path = receipt_path_for(case_id, frame_set, output_dir)
    if replace_reason is None and receipt_path.exists():
        raise FileExistsError("the receipt exists; a second run needs --replace --reason")
    if replace_reason is not None and not receipt_path.exists():
        raise FileNotFoundError("--replace needs an existing receipt")
    replaced = None if replace_reason is None else receipt_to_replace(receipt_path, case_id)
    started = e5_builder.utc_now()
    clock = time.perf_counter()
    built = build(case_id, frame_set, external, boundaries, generated_at_utc=started, docs=docs, root=root, output_dir=output_dir,
                  register_dir=register_dir, registry=registry, git_commit=git_commit, development_reads=development_reads,
                  age_dir=age_dir)
    outputs, files = _outputs(built, root, external)
    supersedes, history = None, None
    if replaced is not None and replace_reason is not None:
        previous, previous_sha256, previous_bound = replaced
        supersedes = superseded_run(previous, previous_sha256, previous_bound, receipt_path, built, replace_reason,
                                    stage_folder(case_id, frame_set, external) / SUPERSEDED_FOLDER, root=root, external=external)
        history = [dict(entry) for entry in previous.get("run_history") or []]
        history.append({"generated_at_utc": supersedes["generated_at_utc"], "receipt_sha256": supersedes["receipt_sha256"],
                        "superseded_because": replace_reason, "result_same_as_the_run_that_replaced_it": supersedes["result_same"],
                        "unit_cells_same_as_the_run_that_replaced_it": supersedes["unit_cells_same"],
                        "units_sha256": supersedes["units_sha256_of_the_superseded_run"],
                        "outputs_sha256": dict(supersedes["outputs_of_the_superseded_run"]),
                        "copies_kept_outside_git": [dict(item) for item in supersedes["copies_kept_outside_git"]]})
    for target, data in files.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    finished = e5_builder.utc_now()
    receipt = {
        "schema_version": built.receipt["schema_version"],
        "generated_at_utc": started,
        "run_kind": "first_run" if supersedes is None else "superseding_run",
        **{key: value for key, value in built.receipt.items() if key != "schema_version"},
        "outputs": outputs,
        "timestamps": {"run_started_at_utc": started, "run_finished_at_utc": finished,
                       "wall_time_minutes": round((time.perf_counter() - clock) / 60, 2),
                       "note": "generated_at_utc is the start of the run; the file of per-unit results carries the same time."},
    }
    if supersedes is not None:
        receipt["supersedes"] = supersedes
        receipt["run_history"] = history
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(encode(receipt))
    receipt_sha256 = sha256_file(receipt_path)
    label = path_label(receipt_path, root, None)
    register_dir.mkdir(parents=True, exist_ok=True)
    (register_dir / receipt_path.name).write_bytes(encode({"path": label, "sha256": receipt_sha256}))
    summary = built.receipt["result"]["summary"]
    return {"receipt": label, "receipt_sha256": receipt_sha256, "computed": built.computed,
            "not_computed_because": None if built.refusal is None else built.refusal["code"],
            "publication_eligibility": receipt["rights"]["publication_eligibility"],
            "cells_run": None if summary is None else summary["cells_run"],
            "cells_not_run": None if summary is None else summary["cells_not_run"],
            "files": [entry["path"] for entry in outputs["ensemble"]["files"]], "generated_at_utc": started,
            "wall_time_minutes": receipt["timestamps"]["wall_time_minutes"]}


def verify(case_id: str, frame_set: Any, external: Path, boundaries: Path, *, docs: Path = DOCS, root: Path = ROOT,
           output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR,
           registry: rights.RightsRegistry | None = None, age_dir: Path | None = None) -> dict[str, Any]:
    """Compute everything again and compare it with the receipt and with the files the receipt binds; write nothing.

    Compared: the file of per-unit results byte for byte, the outputs block of the receipt, and the whole body of
    the receipt except its run-specific fields. The SHA-256 of the builder and of each module is compared with
    the receipt and reported; a difference there alone does not fail the verification.
    """

    receipt = json.loads(receipt_path_for(case_id, frame_set, output_dir).read_text(encoding="ascii"))
    built = build(case_id, frame_set, external, boundaries, generated_at_utc=receipt["generated_at_utc"], docs=docs, root=root,
                  output_dir=output_dir, register_dir=register_dir, registry=registry,
                  git_commit=receipt["implementation"]["base_commit"], age_dir=age_dir)
    block, files = _outputs(built, root, external)
    recomputed = json.loads(json.dumps(built.receipt))
    differing = sorted(key for key in {*recomputed, *receipt}
                       if key not in RECEIPT_KEYS_NOT_RECOMPUTED and key not in RUN_SPECIFIC_KEYS
                       and (key not in receipt or key not in recomputed or _canonical(receipt[key]) != _canonical(recomputed[key])))
    outputs_same = _canonical(receipt["outputs"]) == _canonical(json.loads(json.dumps(block)))
    on_disk = all(path.is_file() and sha256_file(path) == sha256_bytes(data) for path, data in files.items())
    stated, today = receipt["implementation"], recomputed["implementation"]
    code_changed = sorted(key for key in today if key.endswith("_sha256") and stated.get(key) != today[key])
    return {"verified": bool(not differing and outputs_same and on_disk), "computed": built.computed,
            "receipt_body_same": not differing, "receipt_fields_that_differ": differing, "outputs_block_same": outputs_same,
            "files_on_disk_same_as_recomputed": on_disk, "code_changed_since_the_run": code_changed}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the arguments and make one reported run, or verify the last one.

    Returns:
        0 when the ensemble was computed and written (or the inputs were checked, or the run verified); 1 when
        ``--verify`` found a difference; 2 when an input check refused the run before a unit was measured
        against a flood level, and nothing was written; 3 when units were measured and the ensemble was not
        computed: the receipt is then written and registered.
    """

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", required=True, help="the case of protocol v1a: SE1 or O2")
    parser.add_argument("--frame", choices=sorted(FRAME_SETS), required=True)
    parser.add_argument("--external-data", type=Path, default=None,
                        help=f"external data root; default: the environment variable {EXTERNAL_DATA_VARIABLE}")
    parser.add_argument("--boundaries", type=Path, default=None,
                        help="the COD-AB boundary file; default: <external data root>/" + BOUNDARY_RELATIVE_PATH.as_posix())
    parser.add_argument("--age-dir", type=Path, default=None,
                        help="the folder of the WorldPop 2024 age rasters; with it the 2024-rescaled demand is built and the "
                             "cells of the second population level are run (decision log R38 and R39)")
    parser.add_argument("--development-read", action="append", default=[],
                        help="one read of the inputs made before this run, in a sentence; repeat for each")
    parser.add_argument("--replace", action="store_true", help="make a second run; needs --reason, and the new receipt names the old")
    parser.add_argument("--reason", help="why the run is repeated (one sentence)")
    parser.add_argument("--verify", action="store_true",
                        help="compute everything again and compare it with the receipt and its files; write nothing")
    parser.add_argument("--check-inputs", action="store_true",
                        help="check every input against the file that names it; lay no flood layer over a unit, make no "
                             "access run, compute no component and write nothing")
    args = parser.parse_args(argv)
    if args.replace != bool((args.reason or "").strip()):
        parser.error("--replace and --reason go together")
    external = args.external_data or (Path(os.environ[EXTERNAL_DATA_VARIABLE]) if os.environ.get(EXTERNAL_DATA_VARIABLE) else None)
    if external is None:
        parser.error(f"give --external-data or set {EXTERNAL_DATA_VARIABLE}")
    boundaries = args.boundaries or external / BOUNDARY_RELATIVE_PATH
    frame_set = FRAME_SETS[args.frame]
    try:
        if args.check_inputs:
            print(json.dumps(check_inputs(args.case, frame_set, external, boundaries, age_dir=args.age_dir)))
            return EXIT_WRITTEN
        if args.verify:
            summary = verify(args.case, frame_set, external, boundaries, age_dir=args.age_dir)
            print(json.dumps(summary))
            return EXIT_WRITTEN if summary["verified"] else 1
        summary = run(args.case, frame_set, external, boundaries,
                      replace_reason=args.reason.strip() if args.replace else None, development_reads=args.development_read,
                      age_dir=args.age_dir)
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        # Every refusal that reaches this line was raised before a unit was measured: the input checks, and the
        # reading of the receipt to replace. From the first access run on, build() reports whatever stops the run.
        print(f"REFUSED: {error}", file=sys.stderr)
        return EXIT_REFUSED
    print(json.dumps(summary))
    return EXIT_WRITTEN if summary["computed"] else EXIT_NOT_COMPUTED


if __name__ == "__main__":
    raise SystemExit(main())
