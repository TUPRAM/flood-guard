"""Compute the dependent share of each unit of a case frame (plan task E7).

The dependent share is residents aged 0-14 plus residents aged 60 and over,
divided by all residents, in the WorldPop 2024 1 km age counts. It is the input
of the vulnerability component of planning frame v1 (protocol v1a). This script
writes that input for the units of one case frame, with the number of age cells
behind each share, the area with no age count, the share under two other
allocations of the same cells, the cells that lie partly outside every unit of
the boundary layer, and a reading of the age grid itself.

It computes no vulnerability component, no FPPS, no A-E class and no ensemble,
and nothing it writes is an official warning or an observation of a flood.

Run it from the repository root. Both inputs are read-only and live outside
Git, so their locations are arguments::

    python scripts/build_age_exposure.py --case mae_sai \
        --age-dir <folder with acquisition_manifest.json and the 20 age rasters> \
        --external-data <external data root>

``--external-data`` defaults to the environment variable
``FLOODGUARD_EXTERNAL_DATA``; ``--boundaries`` names the boundary file directly.

Every run is reported. The script writes the unit table and, beside it, a
receipt with the SHA-256 of every input and output, the parameters, the two
protocol hashes and the run times. It refuses to run unless protocol v1a and
v1b are in force, and it refuses to overwrite a table. The table of a case
frame has one place, ``outputs/planning_v1/age_exposure_<case>_v1.json``, and
the command line cannot write it anywhere else. A second run needs
``--replace --reason "<why>"``; its receipt then names the table and the
receipt it supersedes by SHA-256 and says whether the figures are the same.
There is no mode that computes without writing a receipt.

The counts come from the code that produced the national anchors
(``scripts/build_national_vulnerability_anchors.py`` and
``floodguard.evidence_age_surface.summarize_geometry``), read from the same
input bytes, so a unit's share and the anchors are on the same footing. The
run is refused unless the functions and constants the share depends on have
the source they had in the anchor run (``ANCHOR_RUN_CODE``) and the input bytes
are the same. Other changes to those three files are recorded in the receipt
and do not refuse the run.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_national_vulnerability_anchors as anchors_builder  # noqa: E402
import record_planning_protocol_receipt as receipt_tool  # noqa: E402

from floodguard import age_exposure, evidence_age_surface, normalisation  # noqa: E402

TABLE_SCHEMA_VERSION = "floodguard.age_exposure.v1"
RECEIPT_SCHEMA_VERSION = "floodguard.age_exposure_run_receipt.v1"
DOCS = ROOT / "docs" / "proposal_execution"
OUTPUT_DIR = ROOT / "outputs" / "planning_v1"
BOUNDARY_RELATIVE_PATH = Path("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
EXTERNAL_DATA_VARIABLE = "FLOODGUARD_EXTERNAL_DATA"
UNIT_NAME_FIELD = "adm3_name"

# Case frames whose unit list a signed protocol file fixes.
CASE_FRAMES: dict[str, dict[str, str]] = {
    "mae_sai": {
        "protocol": "v1a",
        "pointer": "/case_portfolio/mae_sai_reporting_frame/units",
        "label": "Mae Sai reporting frame: the eight full tambons of protocol v1a "
                 "(case_portfolio.mae_sai_reporting_frame)",
    },
}
COMPARED_KEYS = ("input_hashes", "protocol_sha256", "allocation", "age_groups")
# The figures of record of a unit row, and the figures of its three allocations. A replacement run compares
# these with the table it supersedes, whatever other fields a row has gained or lost.
RECORD_FIGURE_KEYS = (
    "unit_id", "status", "residents", "children_0_14", "older_60_plus", "other_15_59", "dependent_share",
    "dependent_share_unavailable_reason", "age_cells", "area", "band_mask_mismatch",
)
ALLOCATION_FIGURE_KEYS = (
    "low", "high", age_exposure.PROJECTED_AREA_FRACTION, age_exposure.CELLS_WHOLLY_INSIDE,
    age_exposure.CELLS_ANY_TOUCHING,
)
COMPUTES = (
    "The dependent share of each unit and the age counts behind it: an input to the vulnerability component. "
    "No vulnerability component value, no FPPS, no A-E class and no ensemble."
)
CONFIDENCE_BASIS = (
    "Modelled 1 km age counts, not observed counts, allocated to units by area. No independent check of a "
    "unit's share exists."
)
ASSUMPTIONS = [
    "WorldPop Global2 R2025A 2024 age counts are modelled estimates at about 1 km, not observed counts.",
    "A cell's counts are spread evenly over the cell, so a unit takes the share of each cell that its area "
    "covers. Within a cell the age composition is taken as uniform.",
    "Units are the 2022 COD-AB tha_admin3 polygons. Boundaries (2022), age counts (2024) and the cases' 2020 "
    "demand and 2026 roads have different vintages.",
    "The counts are computed by the functions and from the input bytes that produced the national "
    "vulnerability anchors, so a unit's share can be compared with those anchors.",
    "Low and high are the smallest and the largest share under three allocations of the same cells. The plan "
    "gives no formula for them; they are not a bound on the allocation error and not a confidence interval.",
    "A cell that lies partly outside every unit of the boundary layer is allocated by area like any other "
    "cell (reading DR-B04 as written). Nothing is adjusted for such cells.",
]
LIMITATIONS = [
    "A unit of a few dozen 1 km cells has many cells that lie only partly inside it. Low and high are the "
    "share under three allocations of those cells. They are not a bound on the allocation error: another "
    "allocation can give a share outside them. They do not cover the error of the modelled counts either.",
    "A narrow range does not show a precise share. Where the cells around a unit carry the same age "
    "composition, every allocation gives the same share (age_grid_reading).",
    "Cells that lie partly outside every unit of the boundary layer (for this frame, cells that straddle the "
    "national border) may hold residents who live outside the layer, and their age composition is that of the "
    "whole cell. Reading DR-B04 does not say how they are treated. cells_partly_outside_every_unit shows, for "
    "each unit, how many there are, how many of the unit's residents come from them and at what share, and how "
    "many of their residents go to no unit.",
    "Area with no valid age count carries no count. It is reported as unsupported area, not as zero residents.",
    "The plan's range for age-resolved exposure, [known, known + unsupported], needs resident counts inside a "
    "flood input. No flood input is read here, so that range is not in this file.",
    "A dependent share is not a measure of need in any place, and it is not the vulnerability component.",
]
OPEN_POINTS = [
    {
        "id": "E7-OP1",
        "point": "Cells that lie partly outside every unit of the boundary layer.",
        "protocol_says": "Reading DR-B04 (v1b national_vulnerability_anchors.method.allocation): a cell's counts "
                         "go to a tambon by the projected-area fraction of the cell inside the tambon. Nothing "
                         "on a cell that no set of units covers in full.",
        "what_this_file_does": "Follows DR-B04 as written, as the national anchors did. Each unit row reports "
                               "the cells concerned under cells_partly_outside_every_unit, and border_cells "
                               "counts them once for the frame. No rule is changed.",
        "for_the_owners": "Whether such cells keep the area allocation, give their whole count to the part "
                          "inside the layer, or are left out. The choice moves the share of a border unit.",
    },
    {
        "id": "E7-OP2",
        "point": "A range for a unit's dependent share.",
        "protocol_says": "Nothing. Plan 1.3 (MVP-02) and plan 5 item 5 give a range for residents inside a "
                         "flood input, [known, known + unsupported], and none for a unit's share.",
        "what_this_file_does": "Shows the share under two other allocations of the same cells beside the value "
                               "of record. They are not a bound on the allocation error.",
        "for_the_owners": "Whether a range enters the vulnerability component, and which one.",
    },
    {
        "id": "E7-OP3",
        "point": "Rounding of a unit's dependent share.",
        "protocol_says": "The national anchors are rounded to six decimal places. Nothing on a unit's share.",
        "what_this_file_does": "Writes shares and counts at full double precision.",
        "for_the_owners": "Whether the share is rounded before it enters the vulnerability component.",
    },
]
NOT_COMPUTED = [
    "vulnerability component (0-100)", "FPPS", "A-E class", "would-be class", "ensemble cell",
    "age-resolved exposure inside a flood input", "2024-rescaled demand",
]

# The code the share depends on, as it was in the national-anchor run. The anchor receipt records the SHA-256 of
# three whole files (implementation.*_sha256). Protocol v1b says the rest of planning frame v1 is built in
# normalisation.py, so those files grow, and a whole-file comparison would refuse every later run. The pins below
# were taken on 4 October 2026 from files whose bytes had the SHA-256 the anchor receipt records
# (file_sha256_in_the_anchor_run): the SHA-256 of the source lines of each function the share depends on
# (function_source_sha256), and the value of each constant those functions read. A run is refused when any of
# them differs. tests/test_age_exposure.py checks the pins against the checked-out code and, where Git still
# holds the bytes of the anchor run, against those bytes.
ANCHOR_RUN_CODE: dict[str, dict[str, Any]] = {
    "allocation_module": {
        "module": "floodguard.evidence_age_surface",
        "path": "src/floodguard/evidence_age_surface.py",
        "anchor_receipt_key": "allocation_module_sha256",
        "file_sha256_in_the_anchor_run": "d7572d205aad805869f1363bc4e67a66fe6ee7a198525b67be41a59266a5832b",
        "functions": {
            "_coverage": "55523ec8ee8f24363b4db5cf6985fd7243e81d9e41380a547546f03c91fe9bcc",
            "summarize_geometry": "e97109ac8a5bbcdf3bdf10ac366fc6c4edbf4a7c8112dcfd9653ccfe401284ec",
        },
        "constants": {
            "AGE_BANDS": ["00", "01", "05", "10", "15", "20", "25", "30", "35", "40",
                          "45", "50", "55", "60", "65", "70", "75", "80", "85", "90"],
            "CHILD_BANDS": ["00", "01", "05", "10"],
            "OLDER_BANDS": ["60", "65", "70", "75", "80", "85", "90"],
        },
    },
    "normalisation_module": {
        "module": "floodguard.normalisation",
        "path": "src/floodguard/normalisation.py",
        "anchor_receipt_key": "normalisation_module_sha256",
        "file_sha256_in_the_anchor_run": "18add3a251a136dbf34ffb2dfc467e177904797f80178c9b363366a264d0b07e",
        "functions": {
            "dependent_share": "415b8492cd43046849951c1e10fd41db53f0d6a096a0df192026b5c6ccd0ff15",
        },
        "constants": {},
    },
    "anchors_builder": {
        "module": "build_national_vulnerability_anchors",
        "path": "scripts/build_national_vulnerability_anchors.py",
        "anchor_receipt_key": "builder_sha256",
        "file_sha256_in_the_anchor_run": "38129401bb81dce40945573a7071cfe16c9b2f1adca9a150ee9c7f94b16a7d3c",
        "functions": {
            "check_age_sources": "2d769e534acfbaee708691f18331db2bf7fab07d5252de2543484891736b7262",
            "read_units": "cfa84cabfca9a46f20dce0e85675b5a8a2c8b451fec7a3a72876a8f96085be7b",
            "sha256_file": "652665f0f043986854628abba3353c72d5381c7224dd03043da3faac54a3cfdd",
        },
        "constants": {"BOUNDARY_LAYER": "tha_admin3", "UNIT_ID_FIELD": "adm3_pcode"},
    },
}
_LOADED_MODULES = {
    "allocation_module": evidence_age_surface,
    "normalisation_module": normalisation,
    "anchors_builder": anchors_builder,
}


def utc_now() -> str:
    """Return the current UTC time to the second, as the receipts write it."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def relative_label(path: Path, root: Path) -> str:
    """Return a path relative to the repository, or the bare file name for a file outside it."""

    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def protocol_binding(docs: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Read protocol v1a and v1b and require both to be in force.

    Returns:
        The two parsed protocols, and the binding to record: their SHA-256,
        their state and the SHA-256 of ``RECEIPTS.jsonl``.

    Raises:
        ValueError: when either file is not in force.
    """

    receipts_path = docs / "RECEIPTS.jsonl"
    receipts = receipt_tool.parse_receipts(receipts_path.read_text(encoding="utf-8"))
    protocols: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for name in receipt_tool.PROTOCOL_NAMES:
        data = (docs / f"planning_protocol_{name}.json").read_bytes()
        state = receipt_tool.force_state(name, data, receipts)
        if state != "in_force":
            raise ValueError(f"planning protocol {name} is not in force ({state}); nothing is computed")
        protocols[name] = json.loads(data.decode("utf-8"))
        hashes[f"planning_protocol_{name}"] = receipt_tool.sha256_hex(data)
    if protocols["v1b"]["depends_on"]["v1a_sha256"] != hashes["planning_protocol_v1a"]:
        raise ValueError("protocol v1b does not depend on this v1a")
    return protocols, {
        "protocol_sha256": hashes,
        "protocol_state": {name: "in_force" for name in receipt_tool.PROTOCOL_NAMES},
        "receipts_file_sha256": anchors_builder.sha256_file(receipts_path),
    }


def case_units(case: str, protocols: dict[str, dict[str, Any]]) -> list[str]:
    """Return the unit identifiers a signed protocol file fixes for a case frame."""

    frame = CASE_FRAMES[case]
    units = receipt_tool.resolve_pointer(protocols[frame["protocol"]], frame["pointer"])
    if not isinstance(units, list) or not units or len(set(units)) != len(units):
        raise ValueError("the case frame has no usable unit list")
    return sorted(str(unit) for unit in units)


def unit_names(boundaries: Path, unit_ids: Sequence[str]) -> dict[str, str | None]:
    """Read the English unit names from the boundary layer, where the layer carries them."""

    import pyogrio

    layer = anchors_builder.BOUNDARY_LAYER
    fields = set(pyogrio.read_info(boundaries, layer=layer)["fields"].tolist())
    if UNIT_NAME_FIELD not in fields:
        return {unit: None for unit in unit_ids}
    frame = pyogrio.read_dataframe(
        boundaries, layer=layer, columns=[anchors_builder.UNIT_ID_FIELD, UNIT_NAME_FIELD], read_geometry=False)
    names = dict(zip(frame[anchors_builder.UNIT_ID_FIELD].astype(str), frame[UNIT_NAME_FIELD]))
    return {unit: (str(names[unit]) if isinstance(names.get(unit), str) else None) for unit in unit_ids}


def function_source_sha256(source: str, name: str) -> str:
    """Return the SHA-256 of the source lines of one top-level function of a module.

    The lines run from the first decorator (or the ``def`` line) to the last
    line of the body, joined with LF, so the value does not depend on the line
    endings of the checkout. A change to a comment or to the docstring inside
    the function changes it; a change elsewhere in the file does not.

    Raises:
        ValueError: when the module has no top-level function of that name.
    """

    lines = source.splitlines()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            first = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
            text = "\n".join(lines[first - 1:node.end_lineno]) + "\n"
            return hashlib.sha256(text.encode("utf-8")).hexdigest()
    raise ValueError(f"no top-level function {name}")


def module_constant(source: str, name: str) -> Any:
    """Return the literal a module assigns to a top-level name, with tuples as lists.

    Raises:
        ValueError: when the module does not assign a literal to that name exactly once.
    """

    found = []
    for node in ast.parse(source).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(target, ast.Name) and target.id == name for target in targets) and node.value is not None:
            found.append(node.value)
    if len(found) != 1:
        raise ValueError(f"{name} is not assigned exactly once")
    try:
        value = ast.literal_eval(found[0])
    except ValueError as error:
        raise ValueError(f"{name} is not a literal") from error
    return json.loads(json.dumps(value))


def pinned_code_state(source: str, pins: Mapping[str, Any]) -> dict[str, Any]:
    """Compare a module's source with the pinned functions and constants of one ``ANCHOR_RUN_CODE`` entry.

    Returns:
        ``function_source_sha256`` (the hashes found; ``None`` for a missing
        function), ``functions_same``, ``constants_found`` and
        ``constants_same``.
    """

    functions: dict[str, str | None] = {}
    constants: dict[str, Any] = {}
    for name in pins["functions"]:
        try:
            functions[name] = function_source_sha256(source, name)
        except ValueError:
            functions[name] = None
    for name in pins["constants"]:
        try:
            constants[name] = module_constant(source, name)
        except ValueError:
            constants[name] = None
    return {
        "function_source_sha256": functions,
        "functions_same": {name: functions[name] == pinned for name, pinned in pins["functions"].items()},
        "constants_found": constants,
        "constants_same": {name: constants[name] == pinned for name, pinned in pins["constants"].items()},
    }


def loaded_code_files() -> dict[str, Path]:
    """Return the files of the three modules this process loaded, keyed as in ``ANCHOR_RUN_CODE``."""

    return {name: Path(str(module.__file__)).resolve() for name, module in _LOADED_MODULES.items()}


def anchor_consistency(v1b: dict[str, Any], root: Path, input_hashes: dict[str, Any], *,
                       code_files: Mapping[str, Path] | None = None) -> dict[str, Any]:
    """Check that the share is computed as in the national-anchor run, from the same input bytes.

    The anchor receipt records the SHA-256 of three whole files. This check
    binds what the share depends on: the source of the functions and the
    values of the constants pinned in ``ANCHOR_RUN_CODE``. A whole file that
    has changed elsewhere is recorded and does not refuse the run.

    Args:
        v1b: Protocol v1b, which names the anchor receipt by SHA-256.
        root: The repository root that holds the anchor receipt.
        input_hashes: The SHA-256 of the inputs of this run.
        code_files: The files to check, keyed as in ``ANCHOR_RUN_CODE``;
            default: the files of the modules this process loaded.

    Raises:
        ValueError: when the anchor receipt is not the one protocol v1b names,
            the pins were not taken from the code that receipt records, a
            pinned function or constant differs, or the inputs differ.
    """

    declared = v1b["national_vulnerability_anchors"]["output_receipt"]
    path = root / declared["path"]
    if anchors_builder.sha256_file(path) != declared["sha256"]:
        raise ValueError("the national-anchor receipt is not the one protocol v1b names")
    anchor = json.loads(path.read_text(encoding="utf-8"))
    files = dict(code_files) if code_files is not None else loaded_code_files()
    code: dict[str, Any] = {}
    for name, pins in ANCHOR_RUN_CODE.items():
        recorded = anchor["implementation"][pins["anchor_receipt_key"]]
        if recorded != pins["file_sha256_in_the_anchor_run"]:
            raise ValueError(f"the pinned code of {name} was not taken from the national-anchor run that protocol "
                             "v1b names")
        file_sha256 = anchors_builder.sha256_file(files[name])
        code[name] = {
            "module": pins["module"],
            "file_sha256": file_sha256,
            "file_sha256_in_the_anchor_run": recorded,
            "whole_file_same": file_sha256 == recorded,
            **pinned_code_state(files[name].read_text(encoding="utf-8"), pins),
        }
    same_inputs = {
        "age_acquisition_manifest": anchor["input_hashes"]["age_acquisition_manifest_sha256"]
        == input_hashes["age_acquisition_manifest_sha256"],
        "age_rasters": anchor["input_hashes"]["age_rasters_sha256"] == input_hashes["age_rasters_sha256"],
        "tambon_boundaries": anchor["input_hashes"]["tambon_boundaries_sha256"]
        == input_hashes["tambon_boundaries_sha256"],
    }
    changed = sorted(
        f"{name}.{item}" for name, state in code.items()
        for item, same in {**state["functions_same"], **state["constants_same"]}.items() if not same)
    if changed:
        raise ValueError("code the share depends on differs from the national-anchor run "
                         f"({', '.join(changed)}); the shares would not be on the same footing as the anchors")
    if not all(same_inputs.values()):
        raise ValueError("the inputs differ from the national-anchor run; the shares would not be on the same "
                         "footing as the anchors")
    whole_files_same = all(state["whole_file_same"] for state in code.values())
    return {
        "anchor_receipt_path": declared["path"],
        "anchor_receipt_sha256": declared["sha256"],
        "rule": "Refused unless every pinned function has the source, and every pinned constant the value, it "
                "had in the national-anchor run, and the input bytes are the same. A whole file that differs "
                "elsewhere is recorded here and does not refuse the run.",
        "code": code,
        "pinned_functions_and_constants_same": True,
        "whole_files_same": whole_files_same,
        "same_input_bytes_as_the_anchor_run": same_inputs,
        "all_same": True,
        "national_unit_table_recomputed": False,
        "note": "The counts come from the functions that produced the anchors and from the same input bytes. "
                + ("The three files have the SHA-256 the anchor receipt records. " if whole_files_same else
                   "At least one of the three files has changed outside the pinned functions and constants "
                   "since the anchor run (whole_file_same). ")
                + "The check compares source text and constant values; it does not cover the libraries, whose "
                  "versions are under implementation.software. The national unit table behind the anchors was "
                  "not computed again, so its SHA-256 was not rechecked here.",
    }


def software_versions() -> dict[str, str]:
    """Return the versions of the libraries that decide the numbers."""

    import numpy
    import pyogrio
    import pyproj
    import rasterio
    import shapely

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "rasterio": rasterio.__version__,
        "gdal": rasterio.__gdal_version__,
        "shapely": shapely.__version__,
        "geos": shapely.geos_version_string,
        "pyproj": pyproj.__version__,
        "proj": pyproj.proj_version_str,
        "pyogrio": pyogrio.__version__,
    }


def build(case: str, age_dir: Path, boundaries: Path, *, docs: Path = DOCS, root: Path = ROOT,
          ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute the unit table and the body of its receipt (nothing is written).

    Args:
        case: A key of ``CASE_FRAMES``.
        age_dir: The folder with ``acquisition_manifest.json`` and the 20 age rasters.
        boundaries: The COD-AB boundary file with layer ``tha_admin3``.
        docs: The folder with the two protocol files and ``RECEIPTS.jsonl``.
        root: The repository root, for the anchor receipt, the relative paths
            and the commit. The code hashes are those of the modules this
            process loaded.

    Returns:
        The table, and the receipt without its ``outputs`` and time fields.

    Raises:
        ValueError: when a protocol is not in force, an input is not the one
            protocol v1b names, a unit is missing from the boundary layer, or
            the pinned code or the inputs differ from the national-anchor run.
    """

    protocols, binding = protocol_binding(docs)
    v1b = protocols["v1b"]
    anchors = v1b["national_vulnerability_anchors"]
    declared = anchors["inputs"]
    wanted = case_units(case, protocols)

    manifest_path = age_dir / "acquisition_manifest.json"
    manifest, paths, raster_hashes = anchors_builder.check_age_sources(age_dir, declared["age_rasters"]["manifest_sha256"])
    boundaries_sha256 = anchors_builder.sha256_file(boundaries)
    if boundaries_sha256 != declared["tambon_boundaries"]["sha256"]:
        raise ValueError("the boundary file is not the one protocol v1b names")
    input_hashes = {
        "age_acquisition_manifest_sha256": declared["age_rasters"]["manifest_sha256"],
        "age_rasters_sha256": dict(sorted(raster_hashes.items())),
        "tambon_boundaries_sha256": boundaries_sha256,
    }
    consistency = anchor_consistency(v1b, root, input_hashes)

    all_units, boundary_summary = anchors_builder.read_units(boundaries)
    geometries = dict(all_units)
    missing = [unit for unit in wanted if unit not in geometries]
    if missing:
        raise ValueError(f"units missing from the boundary layer: {', '.join(missing)}")
    names = unit_names(boundaries, wanted)
    frame = age_exposure.age_exposure_frame(
        [(unit, geometries[unit]) for unit in wanted], paths,
        layer_units=[geometry for _unit, geometry in all_units])
    units = [{"unit_id": row["unit_id"], "unit_name": names[row["unit_id"]],
              **{key: value for key, value in row.items() if key != "unit_id"}} for row in frame["units"]]

    source_timestamps = {
        "age_counts_year_represented": manifest["year_represented"],
        "age_counts_publication_date": manifest["publication_date"],
        "tambon_boundaries_valid_on": boundary_summary["valid_on"],
    }
    common = {
        "official_warning": False,
        "operational_status": "non_operational",
        "computes": COMPUTES,
        "source_timestamp": manifest["publication_date"],
        "source_timestamps": source_timestamps,
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "protocol_sha256": binding["protocol_sha256"],
    }
    table = {
        "schema_version": TABLE_SCHEMA_VERSION,
        "age_exposure_version": age_exposure.AGE_EXPOSURE_VERSION,
        "plan_task": "E7: age_exposure.py + vulnerability (dependent share per unit)",
        "case_frame": case,
        "case_frame_label": CASE_FRAMES[case]["label"],
        "status": "unit_inputs",
        "status_note": "Written with protocol v1a and v1b in force (protocol_sha256). These are inputs to the "
                       "vulnerability component. The component, the FPPS and the A-E class belong to plan "
                       "task E8 and are not here.",
        **common,
        "definition": "Dependent share: residents aged 0-14 plus residents aged 60 and over, divided by all "
                      "residents (protocol v1a scoring_frame.components.vulnerability_context_0_100), from the "
                      "WorldPop 2024 1 km age counts.",
        "age_groups": anchors["method"]["age_groups"],
        "allocation": age_exposure.ALLOCATION_STATEMENT,
        "allocation_in_protocol_v1b": anchors["method"]["allocation"],
        "caveat": anchors["caveat"],
        "range_rule": age_exposure.RANGE_STATEMENT,
        "range_rule_status": "Not in the plan and not in the protocol. Plan 1.3 (MVP-02) and plan 5 item 5 "
                             "give a range for residents inside a flood input, [known, known + unsupported], "
                             "and no formula for the effect of the 1 km cell size on a unit's share. Two other "
                             "allocations of the same cells are shown beside the value of record; the owners "
                             "have not decided how, or whether, a range enters the vulnerability component "
                             "(open_points, E7-OP2).",
        "age_cells_rule": age_exposure.AGE_CELLS_STATEMENT,
        "unsupported_area_rule": age_exposure.UNSUPPORTED_AREA_STATEMENT,
        "border_cells_rule": age_exposure.BORDER_CELLS_STATEMENT,
        "border_cells_rule_status": "A description, not a rule of the protocol. The boundary layer is "
                                    f"{anchors_builder.BOUNDARY_LAYER} ({len(all_units)} units). A cell counts as "
                                    "inside the layer when its units cover at least "
                                    f"{age_exposure.IN_LAYER_MIN_FRACTION!r} of its projected area. Reading DR-B04 "
                                    "is silent on such cells (open_points, E7-OP1).",
        "counts_unit": "modelled 2024 residents",
        "share_precision": "Shares and counts are written at full double precision. The protocol rounds the "
                           "national anchors to six decimal places and states no rounding for a unit's share "
                           "(open_points, E7-OP3).",
        "unit_count": len(units),
        "units": units,
        "border_cells": {
            "what": "The cells that lie partly outside every unit of the boundary layer, counted once over the "
                    "units of the frame. A cell can overlap two units, so the per-unit figures do not add up "
                    "to these.",
            **frame["border_cells"],
        },
        "age_grid_reading": {
            "what": age_exposure.GRID_READING_STATEMENT,
            "frame_window_rule": "The smallest window of the age grid, in rows and columns, that holds every "
                                 "cell overlapping a unit of the frame.",
            **frame["age_grid_reading"],
        },
        "open_points": OPEN_POINTS,
        "not_computed": NOT_COMPUTED,
        "input_hashes": input_hashes,
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
    }
    code_files = loaded_code_files()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "plan_task": table["plan_task"],
        "run": f"Dependent share per unit, case frame {case} ({len(units)} units)",
        "status": "run_receipt",
        "status_note": "Receipt of one run on real units, made with protocol v1a and v1b in force. Every run "
                       "is reported: a second run writes a new receipt that names this one.",
        **common,
        "protocol_state": binding["protocol_state"],
        "parameters": {
            "case_frame": case,
            "unit_list_source": f"planning_protocol_{CASE_FRAMES[case]['protocol']}.json{CASE_FRAMES[case]['pointer']}",
            "unit_ids": wanted,
            "boundary_layer": anchors_builder.BOUNDARY_LAYER,
            "unit_id_field": anchors_builder.UNIT_ID_FIELD,
            "age_bands": list(age_exposure.AGE_BANDS),
            "age_groups": anchors["method"]["age_groups"],
            "allocation_of_record": age_exposure.PROJECTED_AREA_FRACTION,
            "range_allocations": [age_exposure.CELLS_WHOLLY_INSIDE, age_exposure.CELLS_ANY_TOUCHING],
            "wholly_inside_min_fraction": age_exposure.WHOLLY_INSIDE_MIN_FRACTION,
            "in_layer_min_fraction": age_exposure.IN_LAYER_MIN_FRACTION,
            "boundary_layer_units_for_border_cells": len(all_units),
            "grid_reading_share_group_decimals": age_exposure.SHARE_GROUP_DECIMALS,
            "grid_reading_share_group_min_cells": age_exposure.SHARE_GROUP_MIN_CELLS,
            "grid_reading_share_cluster_gap": age_exposure.SHARE_CLUSTER_GAP,
            "grid_reading_frame_window": {
                key: frame["age_grid_reading"]["frame_window"][key]
                for key in ("row_off", "col_off", "height", "width")
            },
            "projection_for_areas": "EPSG:32647",
        },
        "inputs": {
            "age_acquisition_manifest": {
                "file": manifest_path.name, "sha256": input_hashes["age_acquisition_manifest_sha256"],
                "bytes": manifest_path.stat().st_size,
            },
            "age_rasters": {
                paths[band].name: {"sha256": raster_hashes[paths[band].name], "bytes": paths[band].stat().st_size}
                for band in age_exposure.AGE_BANDS
            },
            "tambon_boundaries": {
                "file": boundaries.name, "layer": anchors_builder.BOUNDARY_LAYER, "sha256": boundaries_sha256,
                "bytes": boundaries.stat().st_size, "units_in_layer": boundary_summary["units"],
                "repaired_geometries": boundary_summary["repaired_geometries"],
            },
            "planning_protocol_v1a": {
                "path": relative_label(docs / "planning_protocol_v1a.json", root),
                "sha256": binding["protocol_sha256"]["planning_protocol_v1a"],
            },
            "planning_protocol_v1b": {
                "path": relative_label(docs / "planning_protocol_v1b.json", root),
                "sha256": binding["protocol_sha256"]["planning_protocol_v1b"],
            },
            "protocol_receipts": {
                "path": relative_label(docs / "RECEIPTS.jsonl", root), "sha256": binding["receipts_file_sha256"],
            },
            "national_anchor_receipt": {
                "path": consistency["anchor_receipt_path"], "sha256": consistency["anchor_receipt_sha256"],
            },
        },
        "consistency_with_national_anchors": consistency,
        "implementation": {
            "base_commit": commit.stdout.strip() or None,
            "base_commit_note": "The commit the working tree was on. The files below are the ones this run "
                                "loaded, identified by their own SHA-256, committed or not.",
            "builder_sha256": anchors_builder.sha256_file(Path(__file__)),
            "age_exposure_module_sha256": anchors_builder.sha256_file(Path(str(age_exposure.__file__))),
            "allocation_module_sha256": anchors_builder.sha256_file(code_files["allocation_module"]),
            "normalisation_module_sha256": anchors_builder.sha256_file(code_files["normalisation_module"]),
            "anchors_builder_sha256": anchors_builder.sha256_file(code_files["anchors_builder"]),
            "software": software_versions(),
        },
        "open_points": OPEN_POINTS,
        "not_computed": NOT_COMPUTED,
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
    }
    return table, receipt


def default_output(case: str) -> Path:
    """Return the one place the table of a case frame is written by the command line."""

    return OUTPUT_DIR / f"age_exposure_{case}_v1.json"


def receipt_path_for(output: Path) -> Path:
    """Return the receipt path that goes with a table path."""

    return output.with_name(f"{output.stem}_receipt.json")


def supersedes(output: Path, table: dict[str, Any], reason: str) -> dict[str, Any]:
    """Describe the table and the receipt that a replacement run supersedes."""

    previous = json.loads(output.read_text(encoding="utf-8"))
    previous_receipt = receipt_path_for(output)
    before = previous.get("units") if isinstance(previous.get("units"), list) else []
    after = table["units"]

    def figures(rows: list[dict[str, Any]], keys: Sequence[str], inside: str | None = None) -> list[Any]:
        picked = []
        for row in rows:
            source = (row.get(inside) or {}) if inside else row
            picked.append([row.get("unit_id"), *(source.get(key) for key in keys)])
        return picked

    same = {
        "figures_of_record": figures(before, RECORD_FIGURE_KEYS) == figures(after, RECORD_FIGURE_KEYS),
        "allocation_figures": figures(before, ALLOCATION_FIGURE_KEYS, "allocation_range")
        == figures(after, ALLOCATION_FIGURE_KEYS, "allocation_range"),
        **{key: previous.get(key) == table.get(key) for key in COMPARED_KEYS},
    }
    keys_before = sorted({key for row in before for key in row})
    keys_after = sorted({key for row in after for key in row})
    range_before = sorted({key for row in before for key in (row.get("allocation_range") or {})})
    range_after = sorted({key for row in after for key in (row.get("allocation_range") or {})})
    return {
        "table_sha256": anchors_builder.sha256_file(output),
        "receipt_sha256": anchors_builder.sha256_file(previous_receipt) if previous_receipt.exists() else None,
        "generated_at_utc": previous.get("generated_at_utc"),
        "reason": reason,
        "same_as_superseded": same,
        "all_same": all(same.values()),
        "compared": {
            "figures_of_record": list(RECORD_FIGURE_KEYS),
            "allocation_figures": [f"allocation_range.{key}" for key in ALLOCATION_FIGURE_KEYS],
        },
        "unit_rows_identical": before == after,
        "unit_row_keys_added": [key for key in keys_after if key not in keys_before],
        "unit_row_keys_removed": [key for key in keys_before if key not in keys_after],
        "allocation_range_keys_added": [key for key in range_after if key not in range_before],
        "allocation_range_keys_removed": [key for key in range_before if key not in range_after],
        "table_keys_added": sorted(key for key in table if key not in previous),
        "table_keys_removed": sorted(key for key in previous if key not in table and key not in
                                     ("generated_at_utc", "receipt_file")),
        "note": "The superseded table and receipt stay in the Git history. Figures are compared after "
                "recomputing everything from the same inputs: the figures of record and the three allocations "
                "of every unit, field by field. A row can gain or lose other fields and still have the same "
                "figures (unit_rows_identical, unit_row_keys_added, unit_row_keys_removed).",
    }


def run(case: str, age_dir: Path, boundaries: Path, output: Path, *, docs: Path = DOCS, root: Path = ROOT,
        replace_reason: str | None = None) -> dict[str, Any]:
    """Compute the table, write it and its receipt, and return a short summary.

    The command line always writes to ``default_output(case)``. ``output`` is
    an argument so that the tests can run the builder in a scratch folder.

    Raises:
        FileExistsError: when the table exists and no replacement reason is given.
        FileNotFoundError: when a replacement is asked for and no table exists.
        ValueError: see :func:`build`.
    """

    receipt_path = receipt_path_for(output)
    if replace_reason is None and (output.exists() or receipt_path.exists()):
        raise FileExistsError("the table or its receipt exists; a second run needs --replace --reason")
    if replace_reason is not None and not output.exists():
        raise FileNotFoundError("--replace needs an existing table")
    started = utc_now()
    table, receipt = build(case, age_dir, boundaries, docs=docs, root=root)
    replaced = supersedes(output, table, replace_reason) if replace_reason is not None else None
    finished = utc_now()
    table = {"schema_version": table["schema_version"], "generated_at_utc": finished,
             "receipt_file": relative_label(receipt_path, root),
             **{key: value for key, value in table.items() if key != "schema_version"}}
    output.parent.mkdir(parents=True, exist_ok=True)
    table_bytes = anchors_builder.encode(table)
    output.write_bytes(table_bytes)
    receipt = {
        "schema_version": receipt["schema_version"],
        "generated_at_utc": finished,
        **{key: value for key, value in receipt.items() if key != "schema_version"},
        "timestamps": {"run_started_at_utc": started, "run_finished_at_utc": finished},
        "outputs": [{
            "path": relative_label(output, root),
            "sha256": receipt_tool.sha256_hex(table_bytes),
            "bytes": len(table_bytes),
            "unit_count": table["unit_count"],
        }],
    }
    if replaced is not None:
        receipt["supersedes"] = replaced
    receipt_path.write_bytes(anchors_builder.encode(receipt))
    return {
        "table": relative_label(output, root),
        "table_sha256": receipt["outputs"][0]["sha256"],
        "receipt": relative_label(receipt_path, root),
        "receipt_sha256": anchors_builder.sha256_file(receipt_path),
        "unit_count": table["unit_count"],
        "generated_at_utc": finished,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the arguments and make one reported run."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=sorted(CASE_FRAMES), required=True)
    parser.add_argument("--age-dir", type=Path, required=True,
                        help="folder with acquisition_manifest.json and the 20 WorldPop 2024 1 km age rasters")
    parser.add_argument("--external-data", type=Path, default=None,
                        help=f"external data root; default: the environment variable {EXTERNAL_DATA_VARIABLE}")
    parser.add_argument("--boundaries", type=Path, default=None,
                        help="the COD-AB boundary file; default: <external data root>/" + BOUNDARY_RELATIVE_PATH.as_posix())
    parser.add_argument("--replace", action="store_true",
                        help="make a second run over an existing table; needs --reason, and the new receipt names the old")
    parser.add_argument("--reason", help="why the table is replaced (one sentence)")
    args = parser.parse_args(argv)
    if args.replace != bool((args.reason or "").strip()):
        parser.error("--replace and --reason go together")
    boundaries = args.boundaries
    if boundaries is None:
        external = args.external_data or (Path(os.environ[EXTERNAL_DATA_VARIABLE]) if os.environ.get(EXTERNAL_DATA_VARIABLE) else None)
        if external is None:
            parser.error(f"give --boundaries, --external-data or set {EXTERNAL_DATA_VARIABLE}")
        boundaries = external / BOUNDARY_RELATIVE_PATH
    # One table per case frame, in one place: a second run is always a --replace of that table.
    try:
        summary = run(args.case, args.age_dir, boundaries, default_output(args.case),
                      replace_reason=args.reason.strip() if args.replace else None)
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
