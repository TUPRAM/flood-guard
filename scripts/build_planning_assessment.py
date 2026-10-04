"""Build the planning assessment overlay of one case and report the run (plan task E8).

Plan 8.1 row E8: "planning_assessment.py + writer + verifier; O1/O2/SE1 overlays; verifier passes". For one case of
protocol v1a and its reporting units this script reads what the earlier tasks wrote, measures what is still missing
for each unit, and hands the measurements to ``floodguard.planning_assessment``, which assembles the overlay rows:
the five components of frame v1, the confidence record of rule v1, FPPS, the binding v1 class, the would-be class,
class rule v2 as a secondary axis, leave-one-component-out and the headline slot (not evaluated: the ensemble is
task E10). The overlay is written and verified with ``floodguard.planning_overlay`` and its validator bound to the
two protocol files.

An overlay is planning guidance for preparedness and post-event prioritisation. It is not an official warning,
not an observation of a flood and not an operational product, and class E never means safe. A closure is a
modelled assumption (``closure_basis``), and the product 4009 layers are used as provided; FloodGuard did not
validate them.

**What it reads, and what it checks before it computes anything.** Nothing is rebuilt, and a check that fails
stops the run before any value of a unit is computed.

* Protocol v1a and v1b, which must both be in force (``RECEIPTS.jsonl``; guardrail GR5).
* The flood input task E1 wrote for the case, read back through ``floodguard.flood_inputs.read_written_input``:
  the input record and each extent must be the files the **registered** E1 receipt binds by SHA-256, and so must
  the permanent-water layer of the frame. The three extents in the reporting frame give the flood likelihood, the
  exposure and the two exposures of confidence condition C4.
* The task E5 access table of the case, bound by the registered E5 receipt. It must say ``usable_by_task_e8:
  true``. At the public level the two public services are read; the shelter service is pitch level only.
* The task E7 age table, bound by its registered receipt, and the national-anchor receipt protocol v1b names.
* The planning context of record of task E4, checked against protocol v1b and the E4 receipt as task E5 checks
  it. Its demand cells give the residents of each unit and the exposure; its baseline graph gives the hospitals
  a unit can reach (condition C8).
* The rights registry (``floodguard.rights``): the flood layer must still have the confirmed record its input
  names. The rights level of the overlay is the minimum across its lineage (guardrail GR6).
* Guardrail GR3: the E5 table must have been computed from the same flood input, the same extent bytes and the
  same routing context that this run reads, under closure rule v1.

**Where things go.** A public overlay goes into ``outputs/planning_v1/overlays/``; an overlay below the public
level stays outside Git under ``<external data root>/proposal_execution/planning_v1/<case>/e8_planning_assessment/``
and is bound by SHA-256 in the receipt. The receipt is ``outputs/planning_v1/e8_planning_assessment_<case>_<frame>.json``
and is registered in ``outputs/planning_v1/run_register/``. Nothing is written under ``apps/web/public/``::

    python scripts/build_planning_assessment.py --case SE1 --frame mae_sai --external-data <external data root> \
        [--development-read "<what was read before this run>"] [--replace --reason "<why>"] [--verify]

Every run is reported. A run that computed the rows and could not write the overlay (the v2 result of a row
depends on a trigger nobody evaluated, open point E8-OP1) still writes its receipt, which says so and names the
units; it returns 3. A second run needs ``--replace --reason`` and its receipt names every earlier run.
``--verify`` computes the overlay again with the generation time of the receipt, compares it byte for byte with
the file the receipt binds, runs the verifier on that file and writes nothing. ``--check-inputs`` checks every
input against the file that names it and compares the stages; it computes no value of a unit and writes nothing.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_e5_builder() -> Any:
    """Load the task E5 builder as a module: its context checks and its graph are used unchanged."""

    name = "build_access_diff"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "build_access_diff.py")
    if spec is None or spec.loader is None:
        raise ImportError("scripts/build_access_diff.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


e5_builder = _load_e5_builder()

from floodguard import access_diff, closure_rules, flood_inputs, planning_assessment, rights  # noqa: E402
from floodguard.confidence import SCENARIO_BASE_AGENCY, coverage_by_construction_applies  # noqa: E402
from floodguard.evidence_context import _context_content_hash  # noqa: E402
from floodguard.normalisation import PITCH_LEVEL, PUBLIC_LEVEL  # noqa: E402
from floodguard.planning_overlay import (  # noqa: E402
    FIXTURE_KIND,
    PORTFOLIO_KIND,
    PRODUCT_4009_SOURCE,
    SCHEMA_RELATIVE_PATH,
    PlanningOverlayError,
    is_public_web_path,
    load_overlay_schema,
    overlay_text,
    summarise_overlay,
)

RECEIPT_SCHEMA = "floodguard.planning_assessment_run_receipt.v1"
REPORT_SCHEMA = "floodguard.planning_assessment_not_written.v1"
DOCS = ROOT / "docs" / "proposal_execution"
OUTPUT_DIR = ROOT / "outputs" / "planning_v1"
REGISTER_DIR = OUTPUT_DIR / "run_register"
EXTERNAL_DATA_VARIABLE = "FLOODGUARD_EXTERNAL_DATA"
EXTERNAL_LABEL = "<external_data_workspace>"
PROCESSED_RELATIVE_PATH = Path("proposal_execution") / "planning_v1"
BOUNDARY_RELATIVE_PATH = Path("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
E1_STAGE_FOLDER = "e1_flood_input"
STAGE_FOLDER = "e8_planning_assessment"
OVERLAY_FOLDER_IN_GIT = "overlays"
LICENCE_NOTICE_NAME = "LICENSE_NOTICE.txt"
NOT_WRITTEN_REPORT_NAME = "overlay_not_written.json"
PUBLIC_SERVICES, PITCH_SERVICES = "public_services", "pitch_services"
SERVICE_SETS: Mapping[str, str] = {PUBLIC_LEVEL: PUBLIC_SERVICES, PITCH_LEVEL: PITCH_SERVICES}
FLOOD_LEVEL = flood_inputs.AS_PROVIDED
CONTEXT_BY_PROTOCOL, CONTEXT_BY_REGISTER = "protocol_v1b", "run_register"
RESIDENT_TOLERANCE = 1e-6
"""Two sums of the same resident counts by two stages may differ by rounding; no more than this."""
EXIT_WRITTEN, EXIT_REFUSED, EXIT_NOT_WRITTEN = 0, 2, 3

COMPUTES = (
    "For one case and each of its reporting units: the five components of planning frame v1, the confidence record of "
    "rule v1, FPPS, the binding class of class rule v1 with its reason code, the would-be class of a low-confidence "
    "row, class rule v2 as a secondary axis, and leave-one-component-out. One row per unit: the default cell of "
    "protocol v1b (flood input as provided, the closure level its reference cell names, the frame's own anchors and "
    "weights). No ensemble cell, no headline, no equity figure and no accepted value."
)
CONFIDENCE_BASIS = (
    "Planning classes from modelled access on OpenStreetMap roads, modelled resident and age counts, and closures "
    "assumed from a flood input that FloodGuard did not check against the ground or against an independent source. "
    "The confidence class of each row under confidence rule v1 is in the overlay; this line is the confidence of "
    "the run as evidence."
)
ASSUMPTIONS = [
    "A closure is a modelled assumption of closure rule v1 (closure_basis), not an observed closure. A flood "
    "intersection does not prove that a road was closed.",
    "A flood input is used as provided. A product 4009 layer is a preliminary agency extent that was not checked in "
    "the field (Field_Validation=0), and FloodGuard did not validate it.",
    "Residents are modelled WorldPop 2020 counts. A cell counts for the unit whose polygon holds its centre, and a "
    "resident is inside the flood extent when the cell centre is (the extent covers the point).",
    "Flood likelihood is measured on the unit's land outside permanent water (the permanent-water layer of task E1), "
    "by polygon overlay in EPSG:32647, with the flood extent as provided, clipped to the reporting frame.",
    "The access gap and the road criticality are computed from the resident counts of the task E5 table at the "
    "closure level of the row. No stored ratio is read.",
    "Vulnerability is computed from the modelled 2024 age counts of the task E7 table, allocated to the unit by "
    "area. The age counts and the resident counts of the exposure are of two vintages.",
    "Confidence condition C4 compares the exposure at the plus and the minus level of the flood input (one pixel, "
    "20 m). C7 is the unit's residents connected to the vehicle graph with no modelled route to a hospital, over "
    "its connected residents. C8 counts the hospital destinations a connected resident of the unit can reach on "
    "the baseline vehicle graph (open point E8-OP3).",
    "Every row is the default cell of protocol v1b. The ensemble has not run, so no class is headlined.",
    "Planning guidance only. Not an official warning. Class E never means safe.",
]
LIMITATIONS = [
    "One row per unit. The minus and plus flood levels, the strict and permissive closure levels, the facility sets, "
    "the population vintage, the P5 / P95 anchors and the weight presets are axes of the ensemble (plan task E10).",
    "Triggers B, C and D of class rule v2 are not evaluated by any stage yet. A row whose v2 result depends on one "
    "of them cannot be written, and then the overlay is not written (open point E8-OP1).",
    "A resident whose cell does not snap to the vehicle graph within 250 m is in no access count.",
    "The equity figures, the shelter supply and the travel-time summaries of plan 7.1 are plan task E9 and are not "
    "in schema 1.0 of the overlay.",
]
NOT_COMPUTED = [
    "ensemble cell", "class retention and headline eligibility", "the outcomes of class rule v2 triggers B, C and D",
    "equity difference and ratio by age group", "2SFCA shelter supply", "accepted FPPS and accepted class (tier T4 is locked)",
    "the strict and permissive closure levels", "the minus and plus flood levels as rows",
]


class BuildError(ValueError):
    """Raised when an input is not the one a signed file or a registered receipt names, or may not be used."""


@dataclass(frozen=True)
class LineageText:
    """What the overlay says of one lineage input that has no rights record: its name, licence, credit and level."""

    name: str
    licence: str
    attribution: str
    rights_level: str
    rights_level_basis: str


@dataclass(frozen=True)
class FrameSet:
    """One frame and the files the earlier tasks wrote for it.

    ``context_binding`` says what names the planning context of record: protocol v1b
    (``corridor_polygon.e4_build_of_record``) for the Mae Sai frame, or a receipt in the run register for a
    frame that protocol v1b does not hold. ``not_run`` lists the cases of the frame that cannot be run, each
    with the reason.
    """

    name: str
    title: str
    kind: str
    case_folders: Mapping[str, str]
    frame_folder: str
    e1_receipt: str
    e5_receipt: str
    e7_receipt: str
    context_binding: str
    lineage: Mapping[str, LineageText]
    case_titles: Mapping[str, tuple[str, str, str]]
    rights_input: Mapping[str, str]
    reporting_frame: str | None = None
    unit_ids: tuple[str, ...] = ()
    context_receipt: str | None = None
    boundary_layer: str | None = "tha_admin3"
    unit_id_field: str = "adm3_pcode"
    unit_name_en_field: str = "adm3_name"
    unit_name_th_field: str = "adm3_name1"
    unit_name_th_language_field: str | None = "lang1"
    fixture_cases: Mapping[str, planning_assessment.CaseSpec] = field(default_factory=dict)
    not_run: Mapping[str, str] = field(default_factory=dict)


_E5_READING = (
    "No rights record exists for this input. Task E5 keeps its public-services table at the public level with this "
    "input in its lineage, and this task reads it the same way (open point E8-OP5)."
)
MAE_SAI_LINEAGE: Mapping[str, LineageText] = {
    "routing_context": LineageText(
        "Planning context of record (plan task E4), vehicle mode: OpenStreetMap roads and hospitals, WorldPop 2020 demand cells",
        "ODbL 1.0 (roads and hospitals); CC BY 4.0 (demand cells)",
        "(c) OpenStreetMap contributors; WorldPop (www.worldpop.org), University of Southampton",
        rights.PUBLIC_LEVEL,
        _E5_READING + " The context file also holds DDPM shelter rows (pitch level); the public services read none of them.",
    ),
    "population": LineageText(
        "WorldPop Thailand 100 m population 2020 (tha_ppp_2020.tif)", "CC BY 4.0",
        "WorldPop (www.worldpop.org), University of Southampton", rights.PUBLIC_LEVEL, _E5_READING,
    ),
    "boundaries": LineageText(
        "HDX Thailand COD-AB subdistrict boundaries (tha_admin3), valid on 2022-01-22", "CC BY-IGO",
        "OCHA / HDX Thailand COD-AB", rights.PUBLIC_LEVEL, _E5_READING,
    ),
    "permanent_water": LineageText(
        "Permanent water of the reporting frame (plan task E1): ESA WorldCover 2021 v200, class 80", "CC BY 4.0",
        "ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium",
        rights.PUBLIC_LEVEL,
        "No rights record exists for this input. The layer is an open-licence land-cover class; task E1 wrote it with "
        "its licence, credit and change notice (open point E8-OP5).",
    ),
    "age_structure": LineageText(
        "Age counts per unit (plan task E7): WorldPop Global2 R2025A v1, 2024, 1 km constrained age counts",
        "CC BY 4.0 (public catalogue); public derivatives need a purpose-specific review that is not recorded",
        "WorldPop (www.worldpop.org), University of Southampton",
        rights.LOCAL_LEVEL,
        "Protocol v1b, national_vulnerability_anchors.inputs.age_rasters.rights: 'Public catalog says CC BY 4.0. Public "
        "derivatives require purpose-specific review.' No such review is recorded in the repository, so the input is "
        "held at the local level and every overlay that carries a vulnerability record is local until the owners "
        "record the review (open point E8-OP5).",
    ),
    "national_anchors": LineageText(
        "National vulnerability anchors of protocol v1b (constants for all of Thailand)", "CC BY 4.0 (derived constants)",
        "WorldPop (www.worldpop.org), University of Southampton; HDX Thailand COD-AB", rights.PUBLIC_LEVEL,
        "The five anchors are constants of the signed protocol v1b, which is in the repository, and are in the frame "
        "header of every overlay.",
    ),
}

FRAME_SETS: dict[str, FrameSet] = {
    "mae_sai": FrameSet(
        name="mae_sai",
        title="Mae Sai",
        kind=PORTFOLIO_KIND,
        case_folders={"SE1": "se1_mae_sai", "O2": "o2_mae_sai"},
        frame_folder="mae_sai_frame",
        e1_receipt="e1_flood_inputs_mae_sai.json",
        e5_receipt="e5_access_diff_mae_sai.json",
        e7_receipt="age_exposure_mae_sai_v1_receipt.json",
        context_binding=CONTEXT_BY_PROTOCOL,
        lineage=MAE_SAI_LINEAGE,
        case_titles={
            "SE1": ("Case SE1: 2024 season envelope scenario, Mae Sai (8 tambons)",
                    "กรณี SE1: สถานการณ์จำลองขอบเขตน้ำท่วมสะสมตลอดฤดูกาล พ.ศ. 2567 อำเภอแม่สาย (8 ตำบล)",
                    "Mae Sai, 8 tambons"),
            "O2": ("Case O2: late-season residual water, 22 October 2024, Mae Sai (8 tambons)",
                   "กรณี O2: น้ำค้างปลายฤดู 22 ตุลาคม พ.ศ. 2567 อำเภอแม่สาย (8 ตำบล)",
                   "Mae Sai, 8 tambons"),
        },
        rights_input={"SE1": rights.PRODUCT_4009, "O2": rights.PRODUCT_4009},
        reporting_frame="mae_sai",
        not_run={
            "O1": "case O1 has no flood input of task E1 and no access table of task E5: no radar candidate was delivered "
                  "to those tasks, and the rights registry holds no record of Sentinel-1 data (open point E1-OP2)",
        },
    ),
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def encode(payload: Mapping[str, Any]) -> bytes:
    """Serialise a receipt or a report: two-space indent, ASCII, LF, one final newline."""

    return (json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return flood_inputs.sha256_file(path)


def path_label(path: Path, root: Path, external: Path | None) -> str:
    """Name a file without a machine path: relative to the repository, or to the external data root."""

    return e5_builder.path_label(path, root, external)


def external_path(label: str, external: Path) -> Path:
    """Turn a path a receipt writes under the external data placeholder into a path on this machine."""

    if not label.startswith(EXTERNAL_LABEL + "/"):
        raise BuildError(f"{label} is not a path under the external data root")
    return external / label[len(EXTERNAL_LABEL) + 1:]


def bound_outputs(value: Any) -> dict[str, str]:
    """Return every path a receipt binds in its ``outputs``, with its SHA-256, however the receipt nests them."""

    found: dict[str, str] = {}
    if isinstance(value, Mapping):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            found[value["path"]] = value["sha256"]
        for child in value.values():
            found.update(bound_outputs(child))
    elif isinstance(value, list):
        for child in value:
            found.update(bound_outputs(child))
    return found


def overlay_input_id(source_id: str) -> str:
    """Turn the identifier a stage gives an input into one the overlay schema takes (lower case, no colon).

    Raises:
        BuildError: when the result is not an identifier of the overlay schema.
    """

    import re

    candidate = source_id.lower().replace(":", ".")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,63}", candidate):
        raise BuildError(f"{source_id!r} cannot be written as an input identifier of the overlay")
    return candidate


def load_registered(name: str, output_dir: Path, register_dir: Path, root: Path, what: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a file of the planning output folder and check that it is the one the run register holds.

    Raises:
        BuildError: when the file or its entry is missing, or the entry names another path or other bytes.
    """

    path, entry_path = output_dir / name, None
    label = path_label(path, root, None)
    for candidate in sorted(register_dir.glob("*.json")) if register_dir.is_dir() else []:
        entry = json.loads(candidate.read_text(encoding="ascii"))
        if entry.get("path") == label:
            entry_path, registered_sha256 = candidate, entry.get("sha256")
            break
    if not path.is_file() or entry_path is None:
        raise BuildError(f"{what} is missing, or it is not registered in the run register: {label}")
    digest = sha256_file(path)
    if digest != registered_sha256:
        raise BuildError(f"{what} is not the file the run register holds: {label}")
    return json.loads(path.read_text(encoding="ascii")), {
        "path": label, "sha256": digest, "registered_in": path_label(entry_path, root, None)}


def protocol_hashes_named(document: Mapping[str, Any]) -> dict[str, Any]:
    """The protocol SHA-256 values a receipt, a table or a record names."""

    return dict(document.get("protocol_sha256") or {})


# ---------------------------------------------------------------------------
# Inputs, each checked against the file that names it
# ---------------------------------------------------------------------------


@dataclass
class FloodData:
    """The flood input of the case as task E1 wrote it, and what was read of it."""

    record: dict[str, Any]
    extents: dict[str, Any]
    extent_properties: dict[str, Any]
    water: Any
    water_properties: dict[str, Any]
    footprint: Any
    grant: rights.RightsGrant
    read: dict[str, Any]
    lineage_levels: list[str]


def _decoded(path: Path, expected_sha256: str | None, what: str) -> tuple[Any, dict[str, Any], str]:
    """Read one written layer and check it against the SHA-256 a receipt binds."""

    if not path.is_file():
        raise BuildError(f"{what} is missing")
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if expected_sha256 is None or digest != expected_sha256:
        raise BuildError(f"{what} is not the file the registered E1 receipt binds")
    geometry, properties = flood_inputs.decode_layer(data)
    return geometry, properties, digest


def load_flood_input(case_id: str, frame_set: FrameSet, external: Path, registry: rights.RightsRegistry,
                     hashes: Mapping[str, str], *, output_dir: Path, register_dir: Path, root: Path,
                     rule: Any, unit_ids: Sequence[str]) -> FloodData:
    """Read the flood input task E1 wrote for the case, as the bytes its registered receipt binds, and ask the registry.

    The input record is read first, for the name of the layer; the rights registry is asked before any extent
    is read. The product footprint is read only where confidence condition C3 has to be measured: where
    protocol v1a grants the coverage by construction, the footprint stays out of the lineage.

    Raises:
        BuildError: when a file is not the one the E1 receipt binds, the input was written for another case or
            under other protocol files, or its rights record is no longer the confirmed record it names.
        floodguard.rights.RightsRefusedError: when the registry refuses the use.
    """

    receipt, receipt_record = load_registered(frame_set.e1_receipt, output_dir, register_dir, root, "the E1 receipt")
    bound = bound_outputs(receipt["outputs"])
    folder = external / PROCESSED_RELATIVE_PATH / frame_set.case_folders[case_id] / E1_STAGE_FOLDER
    prefix = f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/{frame_set.case_folders[case_id]}/{E1_STAGE_FOLDER}/"
    record_path = folder / flood_inputs.INPUT_RECORD_NAME
    if not record_path.is_file():
        raise BuildError(f"case {case_id} has no flood input of task E1 under the external data root")
    record_sha256 = sha256_file(record_path)
    if bound.get(prefix + flood_inputs.INPUT_RECORD_NAME) != record_sha256:
        raise BuildError(f"the input record of case {case_id} is not the one the registered E1 receipt binds")
    record = json.loads(record_path.read_text(encoding="ascii"))
    if record.get("case_id") != case_id or protocol_hashes_named(record) != dict(hashes):
        raise BuildError(f"the flood input of case {case_id} was written for another case or under other protocol files")
    grant = registry.require_use(frame_set.rights_input[case_id], layer=record["source"].get("layer"))
    stated = record["rights"]
    if (grant.record_sha256, grant.rights_level) != (stated["record_sha256"], stated["rights_level"]):
        raise BuildError(f"the rights record of case {case_id} is not the confirmed record its flood input names")
    try:
        record, extents = flood_inputs.read_written_input(folder)
    except flood_inputs.FloodInputError as error:
        raise BuildError(f"the flood input of case {case_id} cannot be read: {error}") from error
    needs_footprint = not all(
        coverage_by_construction_applies(rule, unit_id=unit_id, flood_input=str(record["input_name"])) for unit_id in unit_ids)
    files = {(row.get("what"), row.get("level"), row.get("frame")): row for row in record["files"]}
    read: dict[str, Any] = {}
    properties: dict[str, Any] = {}
    levels: list[str] = []
    for level in flood_inputs.LEVELS:
        entry = files.get(("flood_extent", level, flood_inputs.REPORTING_FRAME))
        if entry is None or bound.get(prefix + entry["file"]) != entry["sha256"]:
            raise BuildError(f"the {level} extent of case {case_id} is not the one the registered E1 receipt binds")
        _geometry, properties[level], _digest = _decoded(folder / entry["file"], entry["sha256"], f"the {level} extent")
        read[level] = {"path": prefix + entry["file"], "sha256": entry["sha256"], "rights_level": entry.get("rights_level")}
        levels.append(str(entry.get("rights_level")))
    closure_entry = files.get(("flood_extent", FLOOD_LEVEL, flood_inputs.ROUTING_CONTEXT))
    if closure_entry is None or bound.get(prefix + closure_entry["file"]) != closure_entry["sha256"]:
        raise BuildError(f"the closure extent of case {case_id} is not the one the registered E1 receipt binds")
    if any(level != grant.rights_level for level in levels):
        raise BuildError(f"an extent of case {case_id} does not state the rights level the registry gives its layer")

    frame_prefix = f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/{frame_set.frame_folder}/{E1_STAGE_FOLDER}/"
    water_label = next((label for label in bound if label.startswith(frame_prefix) and "permanent_water" in label
                        and flood_inputs.REPORTING_FRAME in label), None)
    if water_label is None:
        raise BuildError("the registered E1 receipt binds no permanent-water layer of the reporting frame")
    water, water_properties, water_sha256 = _decoded(external_path(water_label, external), bound[water_label],
                                                     "the permanent-water layer")
    footprint = None
    footprint_read = None
    if needs_footprint:
        entry = files.get(("product_footprint", None, flood_inputs.REPORTING_FRAME))
        if entry is None or bound.get(prefix + entry["file"]) != entry["sha256"]:
            raise BuildError(f"the product footprint of case {case_id} is not a file the registered E1 receipt binds")
        footprint, _properties, _digest = _decoded(folder / entry["file"], entry["sha256"], "the product footprint")
        footprint_read = {"path": prefix + entry["file"], "sha256": entry["sha256"], "rights_level": entry.get("rights_level")}
        levels.append(str(entry.get("rights_level")))
    return FloodData(
        record=record, extents={level: extents[level][flood_inputs.REPORTING_FRAME] for level in flood_inputs.LEVELS},
        extent_properties=properties, water=water, water_properties=water_properties, footprint=footprint, grant=grant,
        read={
            "e1_receipt": receipt_record,
            "input_id": record["input_id"],
            "input_record": {"path": prefix + flood_inputs.INPUT_RECORD_NAME, "sha256": record_sha256},
            "extents_reporting_frame": read,
            "closure_extent_routing_context": {"path": prefix + closure_entry["file"], "sha256": closure_entry["sha256"]},
            "permanent_water": {"path": water_label, "sha256": water_sha256},
            "product_footprint": footprint_read,
            "rights_level": grant.rights_level,
            "boundaries_sha256": (receipt.get("inputs") or {}).get("tambon_boundaries", {}).get("sha256"),
        },
        lineage_levels=levels,
    )


def load_access_table(case_id: str, frame_set: FrameSet, level: str, closure_level: str, external: Path,
                      hashes: Mapping[str, str], *, output_dir: Path, register_dir: Path, root: Path
                      ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Read the task E5 table of the case for the services of ``level`` and take the run of the closure level.

    Returns:
        The table, the run (flood level as provided, the closure level) and what was read.

    Raises:
        BuildError: when the table is not the one the registered E5 receipt binds, says it is not usable by
            task E8, was made for another case or under other protocol files, or has no such run.
    """

    receipt, receipt_record = load_registered(frame_set.e5_receipt, output_dir, register_dir, root, "the E5 receipt")
    service_set = SERVICE_SETS[level]
    entries = [entry for entry in (receipt["outputs"].get(case_id) or {}).get("files", [])
               if entry.get("what") == "unit_table" and entry.get("service_set") == service_set]
    if len(entries) != 1:
        raise BuildError(f"the registered E5 receipt binds no {service_set} table of case {case_id}")
    entry = entries[0]
    if entry["path"].startswith(EXTERNAL_LABEL):
        path = external_path(entry["path"], external)
        if not path.is_file() or sha256_file(path) != entry["sha256"]:
            raise BuildError(f"the {service_set} table of case {case_id} is missing or is not the file the E5 receipt binds")
        table = json.loads(path.read_text(encoding="ascii"))
    else:
        table, registered = load_registered(Path(entry["path"]).name, output_dir, register_dir, root,
                                            f"the {service_set} table of case {case_id}")
        if registered["sha256"] != entry["sha256"] or registered["path"] != entry["path"]:
            raise BuildError(f"the {service_set} table of case {case_id} is not the file the E5 receipt binds")
    if table.get("schema_version") != access_diff.UNIT_TABLE_SCHEMA or table.get("case_id") != case_id or table.get("service_set") != service_set:
        raise BuildError(f"the access table is not a {access_diff.UNIT_TABLE_SCHEMA} table of case {case_id} for {service_set}")
    if table.get("usable_by_task_e8") is not True:
        raise BuildError(
            f"the {service_set} table of case {case_id} says it is not usable by task E8: "
            f"{table.get('usable_by_task_e8_basis') or table.get('status_note') or 'no basis stated'}"
        )
    if protocol_hashes_named(table) != dict(hashes):
        raise BuildError("the access table was made under other protocol files than the ones in force")
    runs = [run for run in table["runs"] if run["flood_level"] == FLOOD_LEVEL and run["closure_level"] == closure_level]
    if len(runs) != 1:
        raise BuildError(f"the access table has no single run at flood level {FLOOD_LEVEL} and closure level {closure_level}")
    return table, runs[0], {
        "e5_receipt": receipt_record,
        "table": {"path": entry["path"], "sha256": entry["sha256"], "service_set": service_set,
                  "publication_level": table.get("publication_level"), "generated_at_utc": table.get("generated_at_utc")},
    }


def load_age_table(frame_set: FrameSet, hashes: Mapping[str, str], *, output_dir: Path, register_dir: Path, root: Path
                   ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the task E7 age table, which the registered E7 receipt must bind and the run register must hold.

    Raises:
        BuildError: when the table is not the registered one, or was made under other protocol files.
    """

    receipt, receipt_record = load_registered(frame_set.e7_receipt, output_dir, register_dir, root, "the E7 receipt")
    bound = bound_outputs(receipt["outputs"])
    labels = [label for label in bound if not label.startswith(EXTERNAL_LABEL)]
    if len(labels) != 1:
        raise BuildError("the registered E7 receipt does not bind one age table in the planning output folder")
    table, registered = load_registered(Path(labels[0]).name, output_dir, register_dir, root, "the E7 age table")
    if registered["sha256"] != bound[labels[0]] or registered["path"] != labels[0]:
        raise BuildError("the E7 age table is not the file the registered E7 receipt binds")
    if protocol_hashes_named(table) != dict(hashes):
        raise BuildError("the age table was made under other protocol files than the ones in force")
    return table, {"e7_receipt": receipt_record, "table": registered,
                   "source_timestamp": table.get("source_timestamp"), "generated_at_utc": table.get("generated_at_utc")}


def load_context(frame_set: FrameSet, v1b: Mapping[str, Any], external: Path, *, output_dir: Path, register_dir: Path,
                 root: Path) -> tuple[Any, dict[str, Any]]:
    """Read the planning context of record and build its baseline vehicle graph, as task E5 does.

    For the Mae Sai frame the context is the one protocol v1b names (``corridor_polygon.e4_build_of_record``);
    the checks are those of task E5 (``build_access_diff.load_vehicle_context``). For a frame protocol v1b does
    not hold, the context's receipt must be in the run register.

    Raises:
        BuildError: when the context or its receipt is not the one that names it.
    """

    try:
        if frame_set.context_binding == CONTEXT_BY_PROTOCOL:
            context, record = e5_builder.load_vehicle_context(v1b, external, output_dir, root)
        else:
            receipt, receipt_record = load_registered(str(frame_set.context_receipt), output_dir, register_dir, root,
                                                      "the receipt of the planning context")
            path = external_path(str(receipt["context"]["path"]), external)
            if not path.is_file():
                raise BuildError("the planning context is missing; it is not rebuilt here")
            context = json.loads(path.read_bytes().decode("utf-8"))
            expected = receipt["context"]["canonical_sha256"]
            if context.get("canonical_sha256") != expected or _context_content_hash(context) != expected:
                raise BuildError("the planning context does not have the canonical SHA-256 its registered receipt names")
            record = {"status": "of_record", "run_kind": receipt.get("run_kind"), "path": str(receipt["context"]["path"]),
                      "file_sha256": sha256_file(path), "canonical_sha256": expected, "canonical_sha256_recomputed": True,
                      "receipt": receipt_record, "named_in": "the run register",
                      "input_hashes": dict(receipt.get("input_hashes") or {}),
                      "osm_retrieved_at_utc": (receipt.get("source_timestamps") or {}).get("osm_retrieved_at_utc")}
        graph = e5_builder.mode_graph(access_diff.VEHICLE, context)
    except e5_builder.BuildError as error:
        raise BuildError(str(error)) from error
    record = {**record, "graph": graph.record}
    return graph, record


def read_units(boundaries: Path, unit_ids: Sequence[str], frame_set: FrameSet) -> tuple[list[tuple[str, Any]], dict[str, tuple[str, str]], dict[str, Any]]:
    """Read the unit polygons and names of the frame from the boundary file, in longitude and latitude.

    Raises:
        BuildError: when the layer is not in EPSG:4326 or a unit is missing or repeated.
    """

    import pyogrio

    columns = [frame_set.unit_id_field, frame_set.unit_name_en_field, frame_set.unit_name_th_field]
    if frame_set.unit_name_th_language_field:
        columns.append(frame_set.unit_name_th_language_field)
    table = pyogrio.read_dataframe(boundaries, layer=frame_set.boundary_layer, columns=columns)
    if table.crs is None or table.crs.to_epsg() != 4326:
        raise BuildError("the boundary layer must be EPSG:4326")
    missing = [column for column in columns if column not in table.columns]
    if missing:
        raise BuildError(f"the boundary layer has no field {missing}")
    table = table[table[frame_set.unit_id_field].astype(str).isin(set(unit_ids))]
    if frame_set.unit_name_th_language_field and set(table[frame_set.unit_name_th_language_field].astype(str)) != {"th"}:
        raise BuildError(f"the boundary layer does not say that {frame_set.unit_name_th_field} is the Thai name")
    found = sorted((str(code), geometry) for code, geometry in zip(table[frame_set.unit_id_field], table.geometry))
    if [code for code, _geometry in found] != sorted(unit_ids):
        raise BuildError("the boundary layer does not hold each unit of the frame exactly once")
    names = {str(row[frame_set.unit_id_field]): (str(row[frame_set.unit_name_en_field]), str(row[frame_set.unit_name_th_field]))
             for _index, row in table.iterrows()}
    return found, names, {"layer": frame_set.boundary_layer, "unit_id_field": frame_set.unit_id_field, "units": len(found)}


# ---------------------------------------------------------------------------
# The measurements of each unit
# ---------------------------------------------------------------------------


def unit_measurements(
    rules: planning_assessment.AssessmentRules,
    case: planning_assessment.CaseSpec,
    flood_name: str,
    units: Sequence[tuple[str, Any]],
    names: Mapping[str, tuple[str, str]],
    flood: FloodData,
    graph: Any,
    run: Mapping[str, Any],
    age_table: Mapping[str, Any],
    services: Sequence[str],
) -> tuple[list[planning_assessment.UnitMeasurements], dict[str, Any]]:
    """Measure every unit of the frame: areas, residents, exposure, the counts of the tables, coverage, C7 and C8.

    Returns:
        The measurements of each unit and the checks that tie the stages together (the residents of each unit
        in the context and in the access table, and the hospital routes).

    Raises:
        floodguard.planning_assessment.LanePurityError: when the access table counts other residents for a
            unit than the planning context holds, or its hospital routes contradict the graph.
        BuildError: when a table has no row for a unit.
    """

    from pyproj import Transformer

    frame = flood_inputs.frame_from_units(flood_inputs.REPORTING_FRAME, "the reporting units of the case", list(units), {})
    population = graph.population
    assignment = access_diff.assign_cells(population, list(units))
    by_id = {row["population_id"]: row for row in population}
    transformer = Transformer.from_crs(flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS, always_xy=True)
    cells = []
    for cell in access_diff.demand_cells(population, assignment):
        row = by_id[cell["population_id"]]
        x, y = transformer.transform(float(row["longitude"]), float(row["latitude"]))
        cells.append({**cell, "x": x, "y": y, "node_id": row.get("node_id"), "snap_distance_m": row.get("snap_distance_m")})
    residents = planning_assessment.residents_by_unit(cells)
    inside = {level: planning_assessment.residents_by_unit(cells, flood.extents[level]) for level in flood_inputs.LEVELS}
    reachable = planning_assessment.hospitals_reachable_at_baseline(cells, graph.edges, graph.destinations[access_diff.HOSPITAL])
    access_rows = {str(row["unit_id"]): row for row in run["units"]}
    age_rows = {str(row["unit_id"]): row for row in age_table["units"]}
    measured: list[planning_assessment.UnitMeasurements] = []
    differing: list[str] = []
    for unit_id, _geometry in units:
        if unit_id not in access_rows or unit_id not in age_rows:
            raise BuildError(f"a table of an earlier task has no row for unit {unit_id}")
        counts = planning_assessment.access_counts_from_e5_row(access_rows[unit_id], services)
        unit_residents = residents.get(unit_id, 0.0)
        hospitals = reachable.get(unit_id, 0)
        if abs(counts["residents"] - unit_residents) > RESIDENT_TOLERANCE or (
                (hospitals >= 1) != (counts["residents_with_a_baseline_hospital_route"] > 0)):
            differing.append(unit_id)
        ages = planning_assessment.age_counts_from_e7_row(age_rows[unit_id])
        by_construction = coverage_by_construction_applies(rules.binding.rule, unit_id=unit_id, flood_input=flood_name)
        coverage = None
        if not by_construction and flood.footprint is not None:
            coverage = planning_assessment.unit_coverage(frame.units[unit_id], flood.footprint)
        areas = flood_inputs.flooded_land_areas(frame.units[unit_id], flood.extents[FLOOD_LEVEL], flood.water)
        name_en, name_th = names[unit_id]
        measured.append(planning_assessment.UnitMeasurements(
            unit_id=unit_id, unit_name_en=name_en, unit_name_th=name_th,
            flooded_non_permanent_water_land_area=areas["flooded_non_permanent_water_land_area"],
            non_permanent_water_land_area=areas["non_permanent_water_land_area"],
            unit_residents=unit_residents,
            residents_inside_flood_extent={level: inside[level].get(unit_id, 0.0) for level in flood_inputs.LEVELS},
            access_gap_inputs=counts["access_gap_inputs"],
            residents_losing_all_routes=counts["residents_losing_all_routes"],
            residents_with_baseline_route=counts["residents_with_baseline_route"],
            children_0_14=ages["children_0_14"], older_60_plus=ages["older_60_plus"], age_residents=ages["age_residents"],
            unit_valid_coverage=coverage, coverage_by_construction=by_construction,
            residents_connected_to_the_graph=counts["residents_connected_to_the_graph"],
            connected_residents_without_a_hospital_route=counts["connected_residents_without_a_hospital_route"],
            hospitals_reachable_at_baseline=hospitals,
        ))
    if differing:
        raise planning_assessment.LanePurityError(
            "guardrail GR3: the access table and the planning context do not agree on the residents of a unit or on "
            f"its hospital routes, so they are not one routing context: {differing}"
        )
    cells_in_units = sum(1 for cell in cells if cell["unit_id"] is not None)
    return measured, {
        "demand_cells": len(cells), "cells_in_one_unit": cells_in_units,
        "residents_in_the_units": math.fsum(residents.values()),
        "unit_residents_same_in_the_context_and_the_access_table": True,
        "hospital_routes_same_in_the_graph_and_the_access_table": True,
        "coverage": "by_construction" if all(unit.coverage_by_construction for unit in measured) else "measured",
    }


def lineage_inputs(frame_set: FrameSet, flood: FloodData, flood_spec: planning_assessment.FloodInputSpec, context_record: Mapping[str, Any],
                   access_read: Mapping[str, Any], access_table: Mapping[str, Any], age_read: Mapping[str, Any],
                   boundary: Mapping[str, Any], anchors: Mapping[str, Any], level: str) -> tuple[list[dict[str, Any]], str]:
    """Build the lineage input records of the overlay; return them with the identifier of the routing context.

    Each input states its SHA-256, its rights level, its licence and its credit. The flood input and the access
    table take theirs from the rights grant of the flood layer; an input with no rights record takes them from
    the frame set (:class:`LineageText`).
    """

    grant = flood.grant
    product = PRODUCT_4009_SOURCE if grant.source == rights.SOURCE_PRODUCT_4009 else None
    licence = str(grant.licence.get("name", ""))
    extent = flood.read["extents_reporting_frame"][FLOOD_LEVEL]
    properties = flood.extent_properties[FLOOD_LEVEL]
    text = frame_set.lineage

    def record(input_id: str, role: str, name: str, sha256: str, rights_level: str, licence_text: str, attribution: str,
               source_timestamp: str, *, source_product: str | None = None, acquisition_date: str | None = None,
               change_notice: str | None = None) -> dict[str, Any]:
        return {"input_id": input_id, "role": role, "name": name, "source_product": source_product,
                "acquisition_date": acquisition_date, "sha256": sha256, "rights_level": rights_level,
                "licence": licence_text, "attribution": attribution, "change_notice": change_notice,
                "source_timestamp": source_timestamp}

    def plain(key: str, input_id: str, role: str, sha256: str, source_timestamp: str, change_notice: str | None = None) -> dict[str, Any]:
        item = text[key]
        return record(input_id, role, item.name, sha256, item.rights_level, item.licence, item.attribution, source_timestamp,
                      change_notice=change_notice)

    acquired = None if flood_spec.acquisition_date is None else flood_spec.acquisition_date.isoformat()
    table_level = str(access_table.get("publication_level"))
    hashes = context_record.get("input_hashes") or {}
    context_id = "e4_planning_context_vehicle"
    inputs = [
        record(flood_spec.input_id, "flood_input", flood_spec.name, extent["sha256"], grant.rights_level, licence,
               grant.attribution, str(flood.record["source_timestamp"]), source_product=product, acquisition_date=acquired,
               change_notice=str(properties["change_notice"])),
        plain("routing_context", context_id, "routing_context", str(context_record["canonical_sha256"]),
              f"OpenStreetMap retrieved {context_record.get('osm_retrieved_at_utc')}; population year 2020"),
        plain("population", "worldpop_2020_100m", "population",
              str(hashes.get("worldpop_2020_sha256") or context_record["canonical_sha256"]), "2020"),
        plain("boundaries", "unit_boundaries", "boundaries", str(boundary["sha256"]), str(boundary.get("valid_on") or "see the boundary file")),
        plain("permanent_water", "e1_permanent_water", "permanent_water", str(flood.read["permanent_water"]["sha256"]),
              str(flood.water_properties.get("source_timestamp")), flood.water_properties.get("change_notice")),
        plain("age_structure", "e7_age_exposure_table", "age_structure", str(age_read["table"]["sha256"]),
              str(age_read.get("source_timestamp"))),
        record("e5_access_table", "other",
               f"Access difference table of plan task E5, {access_read['table']['service_set'].replace('_', ' ')}: resident "
               "counts per unit under closure rule v1",
               str(access_read["table"]["sha256"]), table_level, licence, grant.attribution,
               str(access_table.get("source_timestamp")), source_product=product,
               change_notice=str((access_table.get("licence") or {}).get("change_notice") or properties["change_notice"])),
        plain("national_anchors", "national_vulnerability_anchors", "other", str(anchors["sha256"]), str(anchors["source_timestamp"])),
    ]
    if level == PITCH_LEVEL and table_level != PITCH_LEVEL:
        raise BuildError("a pitch-level overlay reads the pitch-services table, which is at the pitch level")
    return inputs, context_id


# ---------------------------------------------------------------------------
# One build: everything computed, nothing written
# ---------------------------------------------------------------------------


@dataclass
class Built:
    """What one build computed: the overlay text (or why it cannot be written) and the body of the receipt."""

    overlay_text: str | None
    refusal: dict[str, Any] | None
    receipt: dict[str, Any]
    target: Path
    target_label: str
    in_git: bool
    notice: bytes | None
    reporting_units: list[str]
    lane: str
    input_sha256: dict[str, str]


def case_spec(rules: planning_assessment.AssessmentRules, case_id: str, frame_set: FrameSet) -> planning_assessment.CaseSpec:
    """Return the case: a case of protocol v1a for a portfolio frame, an invented one for a fixture frame."""

    if frame_set.kind == FIXTURE_KIND:
        if case_id not in frame_set.fixture_cases:
            raise BuildError(f"{case_id!r} is not a case of the fixture frame {frame_set.name}")
        return frame_set.fixture_cases[case_id]
    title_en, title_th, frame_text = frame_set.case_titles[case_id]
    return planning_assessment.case_spec_from_protocol(rules, case_id, title_en=title_en, title_th=title_th, frame=frame_text,
                                                       scenario_base=SCENARIO_BASE_AGENCY)


def overlay_target(case_id: str, frame_set: FrameSet, eligibility: str, external: Path, output_dir: Path) -> tuple[Path, bool]:
    """Return where the overlay of a case goes: into Git when it is public, under the external data root otherwise."""

    name = f"planning_assessment_overlay_{case_id.lower()}_{frame_set.name}.json"
    if eligibility == rights.PUBLIC_LEVEL:
        return output_dir / OVERLAY_FOLDER_IN_GIT / name, True
    return external / PROCESSED_RELATIVE_PATH / frame_set.case_folders[case_id] / STAGE_FOLDER / name, False


def receipt_path_for(case_id: str, frame_set: FrameSet, output_dir: Path = OUTPUT_DIR) -> Path:
    """Return the one place the receipt of a case and frame is written."""

    return output_dir / f"e8_planning_assessment_{case_id.lower()}_{frame_set.name}.json"


def software_versions() -> dict[str, str]:
    import numpy
    import pandas
    import shapely

    return {"python": platform.python_version(), "numpy": numpy.__version__, "pandas": pandas.__version__,
            "shapely": shapely.__version__}


def head_commit(root: Path) -> str:
    """Return the commit the working tree is on, as the overlay header names it."""

    found = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    commit = found.stdout.strip()
    if found.returncode != 0 or len(commit) < 7:
        raise BuildError("the overlay header names the commit of the code, and the folder is not a Git checkout")
    return commit


def prepare(case_id: str, frame_set: FrameSet, external: Path, boundaries: Path, *, level: str = PUBLIC_LEVEL,
            docs: Path = DOCS, root: Path = ROOT, output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR,
            registry: rights.RightsRegistry | None = None) -> SimpleNamespace:
    """Check every input of one case against the file that names it, and compare the stages (guardrail GR3).

    No value of a unit is computed here: the tables and layers are read, their SHA-256 values are compared, the
    rights registry is asked, and the lineage and the rights level of the overlay are worked out.

    Raises:
        BuildError: when an input is not the one a signed file or a registered receipt names, says it is not
            usable, or the case cannot be run.
        ValueError: when a protocol is not in force, the rights registry refuses the flood layer, or the stages
            do not share one flood input, one routing context and one closure rule.
    """

    timings: dict[str, float] = {}
    clock = time.perf_counter()
    if case_id in frame_set.not_run:
        raise BuildError(f"case {case_id} cannot be run: {frame_set.not_run[case_id]}")
    if case_id not in frame_set.case_folders:
        raise BuildError(f"{case_id!r} is not a case of frame {frame_set.name}")
    if level not in SERVICE_SETS:
        raise BuildError(f"the level of an overlay is one of {sorted(SERVICE_SETS)}")
    v1a_path, v1b_path, receipts_path = docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl"
    rules = planning_assessment.load_assessment_rules(v1a_path, v1b_path, receipts_path)
    frame = rules.binding.frame
    in_force = dict(frame.protocol_sha256)
    hashes = {f"planning_protocol_{name}": in_force[name] for name in ("v1a", "v1b")}
    v1b = json.loads(v1b_path.read_text(encoding="utf-8"))
    registry = registry or rights.RightsRegistry(root)
    case = case_spec(rules, case_id, frame_set)
    unit_ids = list(rules.reporting_frames[frame_set.reporting_frame]) if frame_set.reporting_frame else list(frame_set.unit_ids)
    closure = planning_assessment.ClosureSpec(closure_rules.CLOSURE_RULE_VERSION, rules.reference_closure_level)
    services = [service.service for service in frame.access_services if level == PITCH_LEVEL or service.level == PUBLIC_LEVEL]

    access_table, run, access_read = load_access_table(case_id, frame_set, level, closure.level, external, hashes,
                                                       output_dir=output_dir, register_dir=register_dir, root=root)
    age_table, age_read = load_age_table(frame_set, hashes, output_dir=output_dir, register_dir=register_dir, root=root)
    anchors_path = output_dir / "national_vulnerability_anchors_v1.json"
    if not anchors_path.is_file() or sha256_file(anchors_path) != frame.vulnerability_anchor_receipt_sha256:
        raise BuildError("the national-anchor receipt is not the file protocol v1b names")
    anchors = {"path": path_label(anchors_path, root, None), "sha256": frame.vulnerability_anchor_receipt_sha256,
               "source_timestamp": str(json.loads(anchors_path.read_text(encoding="ascii")).get("source_timestamp")),
               "named_in": "planning_protocol_v1b.json /national_vulnerability_anchors/output_receipt"}
    flood = load_flood_input(case_id, frame_set, external, registry, hashes, output_dir=output_dir, register_dir=register_dir,
                             root=root, rule=rules.binding.rule, unit_ids=unit_ids)
    record = flood.record
    if record["lane"] != case.lane or record["tier"] != case.tier or record.get("case_reference_date") != (
            None if case.case_reference_date is None else case.case_reference_date.isoformat()):
        raise BuildError(f"the flood input of case {case_id} states another lane, tier or reference date than the case")
    boundary = {"path": path_label(boundaries, root, external), "sha256": sha256_file(boundaries)}
    if boundary["sha256"] != flood.read["boundaries_sha256"]:
        raise BuildError("the boundary file is not the one the registered E1 receipt names")
    graph, context_record = load_context(frame_set, v1b, external, output_dir=output_dir, register_dir=register_dir, root=root)
    timings["inputs_checked"] = round(time.perf_counter() - clock, 1)

    # Guardrail GR3: one flood input, one routing context, one closure rule. Compared before any unit is measured.
    stated_flood = access_table["flood_input"]
    stated_extent = (stated_flood.get("files") or {}).get(FLOOD_LEVEL) or {}
    lane_purity = planning_assessment.lane_purity_record({
        "flood_input_id": (record["input_id"], stated_flood.get("input_id")),
        "flood_input_name": (record["input_name"], stated_flood.get("input_name")),
        "closure_extent_sha256": (flood.read["closure_extent_routing_context"]["sha256"], stated_extent.get("sha256")),
        "routing_context_canonical_sha256": (context_record["canonical_sha256"],
                                             ((access_table.get("contexts") or {}).get(access_diff.VEHICLE) or {}).get("canonical_sha256")),
        "closure_basis": (f"modelled_from_{record['input_id']}", run.get("closure_basis")),
        "closure_rule_version": (closure.version, (access_table.get("closure_rule") or {}).get("version")),
        "case_lane": (case.lane, access_table.get("lane")),
    })

    clock = time.perf_counter()
    units, names, unit_summary = read_units(boundaries, unit_ids, frame_set)
    acquisition = None if record.get("acquisition_date") is None else date.fromisoformat(record["acquisition_date"])
    window = record.get("season_window")
    last_date = record.get("acquisition_date") or (window[1] if window else None)
    if last_date is None:
        raise BuildError("the flood input states neither an acquisition date nor a season window")
    flood_spec = planning_assessment.FloodInputSpec(
        input_id=overlay_input_id(str(record["input_id"])), name=str(record["input_name"]), acquisition_date=acquisition,
        source_instant=f"{date.fromisoformat(last_date).isoformat()}T00:00:00Z")
    inputs, context_id = lineage_inputs(frame_set, flood, flood_spec, context_record, access_read, access_table, age_read,
                                        {**boundary, "valid_on": ", ".join((access_table.get("source_timestamps") or {}).get("tambon_boundaries_valid_on") or [])},
                                        anchors, level)
    if flood.read["product_footprint"] is not None:
        footprint = flood.read["product_footprint"]
        inputs.append({"input_id": "e1_product_footprint", "role": "other",
                       "name": "Product footprint of the flood input (plan task E1), read for the coverage of condition C3",
                       "source_product": inputs[0]["source_product"], "acquisition_date": None, "sha256": footprint["sha256"],
                       "rights_level": str(footprint["rights_level"]), "licence": inputs[0]["licence"],
                       "attribution": inputs[0]["attribution"], "change_notice": inputs[0]["change_notice"],
                       "source_timestamp": inputs[0]["source_timestamp"]})
    eligibility = rights.minimum_level(item["rights_level"] for item in inputs)
    target, in_git = overlay_target(case_id, frame_set, eligibility, external, output_dir)
    if is_public_web_path(target):
        raise BuildError("this script writes nothing under apps/web/public")
    timings["units_read_and_lineage"] = round(time.perf_counter() - clock, 1)
    return SimpleNamespace(
        rules=rules, frame=frame, hashes=hashes, case=case, unit_ids=unit_ids, closure=closure, services=services,
        access_table=access_table, run=run, access_read=access_read, age_table=age_table, age_read=age_read, anchors=anchors,
        flood=flood, record=record, boundary=boundary, unit_summary=unit_summary, units=units, names=names, graph=graph,
        context_record=context_record, lane_purity=lane_purity, flood_spec=flood_spec, inputs=inputs, context_id=context_id,
        eligibility=eligibility, target=target, in_git=in_git, registry=registry, v1a_path=v1a_path, v1b_path=v1b_path,
        receipts_path=receipts_path, timings=timings)


def check_inputs(case_id: str, frame_set: FrameSet, external: Path, boundaries: Path, **arguments: Any) -> dict[str, Any]:
    """Check the inputs of a case and say what a run would read; compute no value of a unit and write nothing."""

    found = prepare(case_id, frame_set, external, boundaries, **arguments)
    root = arguments.get("root", ROOT)
    return {
        "inputs_checked": True, "case_id": case_id, "lane": found.case.lane, "tier": found.case.tier,
        "units": len(found.unit_ids), "services": found.services, "closure_level": found.closure.level,
        "lane_purity": found.lane_purity["result"], "publication_eligibility": found.eligibility,
        "overlay_would_go_to": path_label(found.target, root, external), "overlay_in_git": found.in_git,
        "lineage": {item["input_id"]: {"sha256": item["sha256"], "rights_level": item["rights_level"]} for item in found.inputs},
        "computed": "nothing: no unit was measured",
    }


def build(case_id: str, frame_set: FrameSet, external: Path, boundaries: Path, *, generated_at_utc: str, level: str = PUBLIC_LEVEL,
          docs: Path = DOCS, root: Path = ROOT, output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR,
          registry: rights.RightsRegistry | None = None, git_commit: str | None = None,
          development_reads: Sequence[str] = ()) -> Built:
    """Check every input, measure every unit and assemble the overlay of one case (nothing is written).

    Raises:
        BuildError, ValueError: see :func:`prepare`; also when a guardrail does not hold for the measured units.
    """

    found = prepare(case_id, frame_set, external, boundaries, level=level, docs=docs, root=root, output_dir=output_dir,
                    register_dir=register_dir, registry=registry)
    rules, frame, hashes, case, unit_ids = found.rules, found.frame, found.hashes, found.case, found.unit_ids
    closure, services, access_table, access_read = found.closure, found.services, found.access_table, found.access_read
    age_read, anchors, flood, record, boundary = found.age_read, found.anchors, found.flood, found.record, found.boundary
    unit_summary, graph, context_record, lane_purity = found.unit_summary, found.graph, found.context_record, found.lane_purity
    flood_spec, inputs, context_id, eligibility = found.flood_spec, found.inputs, found.context_id, found.eligibility
    target, in_git, registry, timings = found.target, found.in_git, found.registry, found.timings
    v1a_path, v1b_path, receipts_path = found.v1a_path, found.v1b_path, found.receipts_path
    clock = time.perf_counter()
    measured, measurement_checks = unit_measurements(rules, case, flood_spec.name, found.units, found.names, flood, graph,
                                                     found.run, found.age_table, services)
    commit = git_commit or head_commit(root)
    overlay_assumptions = [
        *ASSUMPTIONS,
        f"The flood input is written as '{flood_spec.input_id}' in this file; task E1 names it '{record['input_id']}'. "
        "The closure basis of a row names the same input.",
        "The rights level of this file is the minimum across its lineage (guardrail GR6). An input with no rights "
        "record states the level its row gives, with the basis in the run receipt (open point E8-OP5).",
    ]
    for key in ("standard_sentence", "label"):
        if isinstance(record.get(key), str) and record[key].strip():
            overlay_assumptions.append(f"The flood input: {record[key]}")
    overlay_string: str | None = None
    refusal: dict[str, Any] | None = None
    refusal_for_the_receipt: dict[str, Any] | None = None
    guardrails: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    schema = load_overlay_schema(root / SCHEMA_RELATIVE_PATH if (root / SCHEMA_RELATIVE_PATH).is_file() else ROOT / SCHEMA_RELATIVE_PATH)
    try:
        overlay = planning_assessment.assemble_overlay(
            rules, case, flood_spec, closure, measured, inputs, routing_context_id=context_id, generated_at=generated_at_utc,
            git_commit=commit, source_name=f"FloodGuard planning assessment overlay: case {case_id}, {frame_set.title}",
            assumptions=overlay_assumptions)
        guardrails = planning_assessment.guardrail_report(overlay, rules, reporting_units=unit_ids, lane=case.lane)
        overlay_string = overlay_text(overlay, schema, binding=rules.binding)
        summary = summarise_overlay(overlay)
    except planning_assessment.V2NotEvaluableError as error:
        refusal = {"code": "v2_result_not_evaluable", "message": str(error), "open_point": "E8-OP1",
                   "rows": [dict(row) for row in error.rows]}
        refusal_for_the_receipt = {
            "code": refusal["code"], "open_point": "E8-OP1", "rows": len(error.rows),
            "triggers_not_evaluated": sorted({name for row in error.rows for name in row["triggers_not_evaluated"]}),
            "message": "The v2 result of one or more rows depends on a trigger that was not evaluated, and the protocols "
                       "state no result for that case. The units are named in the report outside Git.",
        }
    except PlanningOverlayError as error:
        refusal = {"code": "overlay_refused_by_the_validator", "message": str(error),
                   "problems": [{"code": item.code, "path": item.path, "message": item.message} for item in error.problems]}
        refusal_for_the_receipt = {
            "code": refusal["code"], "problems": len(error.problems), "problem_codes": list(error.codes),
            "message": "floodguard.planning_overlay refused the assembled overlay. The problems are listed in the report "
                       "outside Git.",
        }
    timings["units_measured_and_assessed"] = round(time.perf_counter() - clock, 1)

    target_label = path_label(target, root, external)
    below_public = eligibility != rights.PUBLIC_LEVEL
    notice = None
    if flood.grant.source == rights.SOURCE_PRODUCT_4009 and not in_git:
        record_4009, _sha256 = registry.read_record(frame_set.rights_input[case_id])
        notice = (root / record_4009["licence_notice_file"]).read_bytes()
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "plan_task": "E8: planning_assessment.py + writer + verifier; O1/O2/SE1 overlays; verifier passes",
        "status": "run_receipt",
        "status_note": "Written with protocol v1a and v1b in force (protocol_sha256). The run computed an FPPS and a class "
                       "for real units, which protocol v1b allows since it is in force; every run is reported.",
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "computes": COMPUTES,
        "source_timestamp": str(record["source_timestamp"]),
        "source_timestamps": {
            "flood_input": str(record["source_timestamp"]),
            "overlay_source_instant": flood_spec.source_instant,
            "osm_retrieved_at_utc": context_record.get("osm_retrieved_at_utc"),
            "population_year_represented": 2020,
            "age_counts": age_read.get("source_timestamp"),
            "permanent_water": flood.water_properties.get("source_timestamp"),
        },
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "protocol_sha256": hashes,
        "parameters": {
            "case_id": case_id,
            "frame_set": frame_set.name,
            "lane": case.lane,
            "tier": case.tier,
            "case_reference_date": None if case.case_reference_date is None else case.case_reference_date.isoformat(),
            "unit_ids": sorted(unit_ids),
            "level": level,
            "services": services,
            "flood_level": FLOOD_LEVEL,
            "closure_rule": {"version": closure.version, "level": closure.level,
                             "source": "planning_protocol_v1b.json /ensemble_grid/headline_rule/reference_cell (open point E8-OP2)"},
            "normalisation_version": frame.version,
            "weights": dict(frame.weights),
            "flood_anchor": frame.flood_anchor,
            "vulnerability_anchors": {name: frame.vulnerability_anchors[name] for name in frame.vulnerability_bounds},
            "confidence_rule_version": rules.binding.rule.version,
            "class_rule_binding": "class_rule_v1 (floodguard.scoring.assign_action_class, unchanged)",
            "class_rule_secondary": rules.binding.class_rule_v2["version"],
            "v2_trigger_inputs": {"B": "not evaluated", "C": "not evaluated", "D": "not evaluated",
                                  "note": "No stage computes them yet (open point E8-OP1)."},
            "headline": "not evaluated: the ensemble is plan task E10",
            "overlay_input_id_of_the_flood_input": flood_spec.input_id,
        },
        "inputs": {
            "planning_protocol_v1a": {"path": path_label(v1a_path, root, external), "sha256": hashes["planning_protocol_v1a"]},
            "planning_protocol_v1b": {"path": path_label(v1b_path, root, external), "sha256": hashes["planning_protocol_v1b"]},
            "protocol_receipts": {"path": path_label(receipts_path, root, external), "sha256": sha256_file(receipts_path)},
            "flood_input": flood.read,
            "access_table": access_read,
            "age_table": age_read,
            "national_anchors": anchors,
            "planning_context_vehicle": {key: value for key, value in context_record.items() if key != "graph"},
            "tambon_boundaries": {**boundary, **unit_summary},
            "rights_record": {"input_id": flood.grant.input_id, "layer": flood.grant.layer, "path": flood.grant.record_path,
                              "sha256": flood.grant.record_sha256, "record_status": flood.grant.record_status},
        },
        "rights": {
            "registry": "floodguard.rights.REGISTERED_RECORDS",
            "rule": "Protocol v1a guardrail GR6: the rights level of an overlay is the minimum across its lineage. The "
                    "registry is asked for the flood layer before any file of it is read. An overlay goes into Git only "
                    "when that minimum is public; any other overlay stays outside Git and is bound here by SHA-256. "
                    "Nothing is written under apps/web/public/.",
            "publication_eligibility": eligibility,
            "lineage_levels": {item["input_id"]: item["rights_level"] for item in inputs},
            "levels_of_inputs_without_a_rights_record": {
                key: {"rights_level": item.rights_level, "basis": item.rights_level_basis} for key, item in frame_set.lineage.items()},
            "flood_layer": {"rights_level": flood.grant.rights_level, "basis": flood.grant.rights_level_basis},
            "levels_and_git": rights.LEVELS_AND_GIT,
            "figures_of_local_level_layers_in_this_receipt": {
                "what": "This receipt is committed. It holds counts of rows for the whole case (result.summary), no value "
                        "of a single unit and no unit of a row that could not be written. When the overlay is below the "
                        "public level those counts come from a lineage below the public level; the overlay itself is "
                        "outside Git.",
                "figures": ([{"where": "result.summary", "publication_eligibility": eligibility,
                              "figures": "The number of rows by class, reason code, confidence class and failed "
                                         "condition, per lane column."}] if below_public else []),
                "for_the_owners": "Open point E1-OP1: whether a level below public allows these counts in Git.",
            },
            "written_under_apps_web_public": False,
        },
        "lane_purity": lane_purity,
        "measurement_checks": measurement_checks,
        "graph": graph.record,
        "guardrails": guardrails,
        "result": {
            "overlay_written": overlay_string is not None,
            "summary": summary,
            "not_written_because": refusal_for_the_receipt,
        },
        "development_reads": {
            "what": "Reads of the same inputs made while the code was written, before this run. They are listed because "
                    "every run is reported.",
            "reads": list(development_reads),
        },
        "open_points": [dict(point) for point in planning_assessment.OPEN_POINTS],
        "not_computed": NOT_COMPUTED,
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
        "implementation": {
            "base_commit": commit,
            "base_commit_note": "The commit the working tree was on. The files below are the ones this run loaded, "
                                "identified by their own SHA-256, committed or not.",
            "builder_sha256": sha256_file(Path(__file__)),
            **{f"{name}_module_sha256": sha256_file(ROOT / "src" / "floodguard" / f"{name}.py")
               for name in ("planning_assessment", "planning_overlay", "normalisation", "confidence", "scoring",
                            "flood_inputs", "access_diff", "rights", "rights_basis")},
            "assessment_version": planning_assessment.ASSESSMENT_VERSION,
            "software": software_versions(),
        },
        "timing_seconds": timings,
    }
    return Built(overlay_text=overlay_string, refusal=refusal, receipt=receipt, target=target, target_label=target_label,
                 in_git=in_git, notice=notice, reporting_units=unit_ids, lane=case.lane,
                 input_sha256={item["input_id"]: item["sha256"] for item in inputs})


# ---------------------------------------------------------------------------
# Run, verify, command line
# ---------------------------------------------------------------------------


def _outputs(built: Built, root: Path, external: Path) -> tuple[dict[str, Any], dict[Path, bytes]]:
    """Return the outputs block of the receipt and the files to write, by path."""

    files: dict[Path, bytes] = {}
    listed: list[dict[str, Any]] = []
    if built.overlay_text is not None:
        data = built.overlay_text.encode("ascii")
        files[built.target] = data
        listed.append({"path": built.target_label, "sha256": sha256_bytes(data), "bytes": len(data),
                       "what": "planning_assessment_overlay", "in_git": built.in_git,
                       "publication_eligibility": built.receipt["rights"]["publication_eligibility"],
                       "rows": built.receipt["result"]["summary"]["row_count"]})
    else:
        report = {
            "schema_version": REPORT_SCHEMA,
            "what": "The overlay of this run was not written. This file says why, and for which units.",
            "case_id": built.receipt["parameters"]["case_id"],
            "protocol_sha256": built.receipt["protocol_sha256"],
            "official_warning": False,
            "operational_status": "non_operational",
            "not_written_because": built.refusal,
        }
        data = encode(report)
        target = built.target.parent / NOT_WRITTEN_REPORT_NAME if not built.in_git else (
            external / PROCESSED_RELATIVE_PATH / STAGE_FOLDER / f"{built.target.stem}__{NOT_WRITTEN_REPORT_NAME}")
        files[target] = data
        listed.append({"path": path_label(target, root, external), "sha256": sha256_bytes(data), "bytes": len(data),
                       "what": "overlay_not_written_report", "in_git": False})
    if built.notice is not None and built.overlay_text is not None:
        target = built.target.parent / LICENCE_NOTICE_NAME
        files[target] = built.notice
        listed.append({"path": path_label(target, root, external), "sha256": sha256_bytes(built.notice),
                       "bytes": len(built.notice), "what": "licence_notice", "in_git": False})
    return {"overlay": {"files": listed}}, files


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def run(case_id: str, frame_set: FrameSet, external: Path, boundaries: Path, *, level: str = PUBLIC_LEVEL, docs: Path = DOCS,
        root: Path = ROOT, output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR,
        registry: rights.RightsRegistry | None = None, git_commit: str | None = None, replace_reason: str | None = None,
        development_reads: Sequence[str] = ()) -> dict[str, Any]:
    """Check the inputs, compute the overlay, write it, write the receipt and register it; return a short summary.

    A run that computed the rows and cannot write the overlay still writes and registers its receipt, with a
    report of why outside Git: every run is reported.

    Raises:
        FileExistsError: when the receipt exists and no replacement reason is given.
        FileNotFoundError: when a replacement is asked for and no receipt exists.
        BuildError, ValueError: see :func:`build`. Nothing is written then.
    """

    receipt_path = receipt_path_for(case_id, frame_set, output_dir)
    if replace_reason is None and receipt_path.exists():
        raise FileExistsError("the receipt exists; a second run needs --replace --reason")
    if replace_reason is not None and not receipt_path.exists():
        raise FileNotFoundError("--replace needs an existing receipt")
    started = e5_builder.utc_now()
    clock = time.perf_counter()
    built = build(case_id, frame_set, external, boundaries, generated_at_utc=started, level=level, docs=docs, root=root,
                  output_dir=output_dir, register_dir=register_dir, registry=registry, git_commit=git_commit,
                  development_reads=development_reads)
    outputs, files = _outputs(built, root, external)
    supersedes, history = None, None
    if replace_reason is not None:
        previous = json.loads(receipt_path.read_text(encoding="ascii"))
        supersedes = {
            "receipt_sha256": sha256_file(receipt_path),
            "generated_at_utc": previous.get("generated_at_utc"),
            "reason": replace_reason,
            "result_same": _canonical(previous.get("result")) == _canonical(built.receipt["result"]),
            "outputs_of_the_superseded_run": bound_outputs(previous["outputs"]),
            "note": "The superseded receipt is named here by its SHA-256, and run_history lists every earlier run. "
                    "result_same compares the result blocks of the two receipts (whether the overlay was written, and "
                    "its summary); an overlay carries its generation time, so its bytes differ between runs.",
        }
        history = [dict(entry) for entry in previous.get("run_history") or []]
        history.append({"generated_at_utc": supersedes["generated_at_utc"], "receipt_sha256": supersedes["receipt_sha256"],
                        "superseded_because": replace_reason, "result_same_as_the_run_that_replaced_it": supersedes["result_same"],
                        "outputs_sha256": dict(supersedes["outputs_of_the_superseded_run"])})
        for stale in supersedes["outputs_of_the_superseded_run"]:
            stale_path = external_path(stale, external) if stale.startswith(EXTERNAL_LABEL) else root / stale
            if stale_path not in files and stale_path.is_file() and stale_path.name != LICENCE_NOTICE_NAME:
                stale_path.unlink()
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
                       "note": "generated_at_utc is the start of the run; the overlay carries the same time."},
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
    return {"receipt": label, "receipt_sha256": receipt_sha256, "overlay_written": built.overlay_text is not None,
            "overlay": built.target_label if built.overlay_text is not None else None,
            "overlay_in_git": built.in_git if built.overlay_text is not None else None,
            "publication_eligibility": receipt["rights"]["publication_eligibility"],
            "not_written_because": None if built.refusal is None else built.refusal["code"],
            "generated_at_utc": started}


def verify(case_id: str, frame_set: FrameSet, external: Path, boundaries: Path, *, level: str = PUBLIC_LEVEL, docs: Path = DOCS,
           root: Path = ROOT, output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR,
           registry: rights.RightsRegistry | None = None) -> dict[str, Any]:
    """Compute the overlay again, compare it with the file the receipt binds and run the verifier on it; write nothing."""

    receipt = json.loads(receipt_path_for(case_id, frame_set, output_dir).read_text(encoding="ascii"))
    built = build(case_id, frame_set, external, boundaries, generated_at_utc=receipt["generated_at_utc"], level=level, docs=docs,
                  root=root, output_dir=output_dir, register_dir=register_dir, registry=registry,
                  git_commit=receipt["implementation"]["base_commit"])
    bound = bound_outputs(receipt["outputs"])
    written = receipt["result"]["overlay_written"]
    same_result = _canonical(receipt["result"]) == _canonical(built.receipt["result"])
    if not written:
        return {"verified": same_result and built.overlay_text is None, "overlay_written": False,
                "receipt_result_same": same_result, "not_written_because": receipt["result"]["not_written_because"]["code"]}
    data = (built.overlay_text or "").encode("ascii")
    digest = sha256_bytes(data)
    on_disk = built.target.is_file() and sha256_file(built.target) == digest
    rules = planning_assessment.load_assessment_rules(docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json",
                                                      docs / "RECEIPTS.jsonl")
    schema = load_overlay_schema(root / SCHEMA_RELATIVE_PATH if (root / SCHEMA_RELATIVE_PATH).is_file() else ROOT / SCHEMA_RELATIVE_PATH)
    checked = planning_assessment.verify_assessment(built.target, schema, rules, reporting_units=built.reporting_units,
                                                    lane=built.lane, expected_input_sha256=built.input_sha256) if on_disk else None
    return {"verified": bool(bound.get(built.target_label) == digest and on_disk and same_result and checked and checked["verified"]),
            "overlay_written": True, "overlay_bytes_same_as_recomputed": bound.get(built.target_label) == digest,
            "overlay_on_disk_same": on_disk, "receipt_result_same": same_result,
            "verifier": None if checked is None else {"verified": checked["verified"], "problems": checked["problems"]}}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the arguments and make one reported run, or verify the last one."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", required=True, help="the case of protocol v1a: SE1, O2 or O1")
    parser.add_argument("--frame", choices=sorted(FRAME_SETS), required=True)
    parser.add_argument("--level", choices=sorted(SERVICE_SETS), default=PUBLIC_LEVEL,
                        help="public: the two public services of the access gap; pitch: adds the shelter service")
    parser.add_argument("--external-data", type=Path, default=None,
                        help=f"external data root; default: the environment variable {EXTERNAL_DATA_VARIABLE}")
    parser.add_argument("--boundaries", type=Path, default=None,
                        help="the COD-AB boundary file; default: <external data root>/" + BOUNDARY_RELATIVE_PATH.as_posix())
    parser.add_argument("--development-read", action="append", default=[],
                        help="one read of the inputs made before this run, in a sentence; repeat for each")
    parser.add_argument("--replace", action="store_true", help="make a second run; needs --reason, and the new receipt names the old")
    parser.add_argument("--reason", help="why the run is repeated (one sentence)")
    parser.add_argument("--verify", action="store_true", help="compute the overlay again, compare and verify it; write nothing")
    parser.add_argument("--check-inputs", action="store_true",
                        help="check every input against the file that names it; compute no value of a unit and write nothing")
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
            print(json.dumps(check_inputs(args.case, frame_set, external, boundaries, level=args.level)))
            return EXIT_WRITTEN
        if args.verify:
            summary = verify(args.case, frame_set, external, boundaries, level=args.level)
            print(json.dumps(summary))
            return EXIT_WRITTEN if summary["verified"] else 1
        summary = run(args.case, frame_set, external, boundaries, level=args.level,
                      replace_reason=args.reason.strip() if args.replace else None, development_reads=args.development_read)
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return EXIT_REFUSED
    print(json.dumps(summary))
    return EXIT_WRITTEN if summary["overlay_written"] else EXIT_NOT_WRITTEN


if __name__ == "__main__":
    raise SystemExit(main())
