"""Compute the dependent share of each unit of a case frame (plan task E7).

The dependent share is residents aged 0-14 plus residents aged 60 and over,
divided by all residents, in the WorldPop 2024 1 km age counts. It is the input
of the vulnerability component of planning frame v1 (protocol v1a). This script
writes that input for the units of one case frame, with the number of age cells
behind each share, the area with no age count and a low/high range from two
other allocations of the same cells.

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
v1b are in force, and it refuses to overwrite a table. A second run needs
``--replace --reason "<why>"``; its receipt then names the table and the
receipt it supersedes by SHA-256 and says whether the figures are the same.
There is no mode that computes without writing a receipt.

The counts come from the code that produced the national anchors
(``scripts/build_national_vulnerability_anchors.py`` and
``floodguard.evidence_age_surface.summarize_geometry``), read from the same
input bytes, so a unit's share and the anchors are on the same footing. The
receipt records that check.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_national_vulnerability_anchors as anchors_builder  # noqa: E402
import record_planning_protocol_receipt as receipt_tool  # noqa: E402

from floodguard import age_exposure  # noqa: E402

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
COMPARED_KEYS = ("units", "input_hashes", "protocol_sha256", "allocation", "age_groups")
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
    "The counts are computed by the code and from the input bytes that produced the national vulnerability "
    "anchors, so a unit's share can be compared with those anchors.",
    "The low/high range re-allocates the same cells two other ways. The plan gives no formula for it; it is "
    "not a confidence interval.",
]
LIMITATIONS = [
    "A unit of a few dozen 1 km cells has many cells that lie only partly inside it. The range shows how much "
    "that can move the share; it does not cover the error of the modelled counts themselves.",
    "Area with no valid age count carries no count. It is reported as unsupported area, not as zero residents.",
    "The plan's range for age-resolved exposure, [known, known + unsupported], needs resident counts inside a "
    "flood input. No flood input is read here, so that range is not in this file.",
    "A dependent share is not a measure of need in any place, and it is not the vulnerability component.",
]
NOT_COMPUTED = [
    "vulnerability component (0-100)", "FPPS", "A-E class", "would-be class", "ensemble cell",
    "age-resolved exposure inside a flood input", "2024-rescaled demand",
]


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


def anchor_consistency(v1b: dict[str, Any], root: Path, input_hashes: dict[str, Any]) -> dict[str, Any]:
    """Check that this run uses the code and the input bytes of the national-anchor run.

    Raises:
        ValueError: when the anchor receipt is not the one protocol v1b names,
            or the code or the inputs differ from that run.
    """

    declared = v1b["national_vulnerability_anchors"]["output_receipt"]
    path = root / declared["path"]
    if anchors_builder.sha256_file(path) != declared["sha256"]:
        raise ValueError("the national-anchor receipt is not the one protocol v1b names")
    anchor = json.loads(path.read_text(encoding="utf-8"))
    code = {
        "allocation_module": (root / "src" / "floodguard" / "evidence_age_surface.py",
                              anchor["implementation"]["allocation_module_sha256"]),
        "normalisation_module": (root / "src" / "floodguard" / "normalisation.py",
                                 anchor["implementation"]["normalisation_module_sha256"]),
        "anchors_builder": (root / "scripts" / "build_national_vulnerability_anchors.py",
                            anchor["implementation"]["builder_sha256"]),
    }
    same_code = {name: anchors_builder.sha256_file(file) == recorded for name, (file, recorded) in code.items()}
    same_inputs = {
        "age_acquisition_manifest": anchor["input_hashes"]["age_acquisition_manifest_sha256"]
        == input_hashes["age_acquisition_manifest_sha256"],
        "age_rasters": anchor["input_hashes"]["age_rasters_sha256"] == input_hashes["age_rasters_sha256"],
        "tambon_boundaries": anchor["input_hashes"]["tambon_boundaries_sha256"]
        == input_hashes["tambon_boundaries_sha256"],
    }
    if not all(same_code.values()) or not all(same_inputs.values()):
        raise ValueError("the code or the inputs differ from the national-anchor run; the shares would not be "
                         "on the same footing as the anchors")
    return {
        "anchor_receipt_path": declared["path"],
        "anchor_receipt_sha256": declared["sha256"],
        "same_code_bytes_as_the_anchor_run": same_code,
        "same_input_bytes_as_the_anchor_run": same_inputs,
        "all_same": True,
        "national_unit_table_recomputed": False,
        "note": "The counts come from the functions that produced the anchors, with the same SHA-256 as in the "
                "anchor receipt, and from the same input bytes. The national unit table behind the anchors was "
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
        root: The repository root, for the anchor receipt and the code hashes.

    Returns:
        The table, and the receipt without its ``outputs`` and time fields.

    Raises:
        ValueError: when a protocol is not in force, an input is not the one
            protocol v1b names, a unit is missing from the boundary layer, or
            the code or inputs differ from the national-anchor run.
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
    rows = age_exposure.age_exposure_table([(unit, geometries[unit]) for unit in wanted], paths)
    units = [{"unit_id": row["unit_id"], "unit_name": names[row["unit_id"]],
              **{key: value for key, value in row.items() if key != "unit_id"}} for row in rows]

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
                             "and no formula for the effect of the 1 km cell size on a unit's share. The two "
                             "allocation extremes are shown so a reader can see that effect; the owners have "
                             "not decided how, or whether, the range enters the vulnerability component.",
        "age_cells_rule": age_exposure.AGE_CELLS_STATEMENT,
        "unsupported_area_rule": age_exposure.UNSUPPORTED_AREA_STATEMENT,
        "counts_unit": "modelled 2024 residents",
        "share_precision": "Shares and counts are written at full double precision. The protocol rounds the "
                           "national anchors to six decimal places and states no rounding for a unit's share.",
        "unit_count": len(units),
        "units": units,
        "not_computed": NOT_COMPUTED,
        "input_hashes": input_hashes,
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
    }
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
            "base_commit_note": "The commit the working tree was on. The files below are identified by their "
                                "own SHA-256, committed or not.",
            "builder_sha256": anchors_builder.sha256_file(Path(__file__)),
            "age_exposure_module_sha256": anchors_builder.sha256_file(root / "src" / "floodguard" / "age_exposure.py"),
            "allocation_module_sha256": anchors_builder.sha256_file(root / "src" / "floodguard" / "evidence_age_surface.py"),
            "normalisation_module_sha256": anchors_builder.sha256_file(root / "src" / "floodguard" / "normalisation.py"),
            "anchors_builder_sha256": anchors_builder.sha256_file(root / "scripts" / "build_national_vulnerability_anchors.py"),
            "software": software_versions(),
        },
        "not_computed": NOT_COMPUTED,
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
    }
    return table, receipt


def receipt_path_for(output: Path) -> Path:
    """Return the receipt path that goes with a table path."""

    return output.with_name(f"{output.stem}_receipt.json")


def supersedes(output: Path, table: dict[str, Any], reason: str) -> dict[str, Any]:
    """Describe the table and the receipt that a replacement run supersedes."""

    previous = json.loads(output.read_text(encoding="utf-8"))
    previous_receipt = receipt_path_for(output)
    same = {key: previous.get(key) == table.get(key) for key in COMPARED_KEYS}
    return {
        "table_sha256": anchors_builder.sha256_file(output),
        "receipt_sha256": anchors_builder.sha256_file(previous_receipt) if previous_receipt.exists() else None,
        "generated_at_utc": previous.get("generated_at_utc"),
        "reason": reason,
        "same_as_superseded": same,
        "all_same": all(same.values()),
        "note": "The superseded table and receipt stay in the Git history. Figures are compared after "
                "recomputing everything from the same inputs.",
    }


def run(case: str, age_dir: Path, boundaries: Path, output: Path, *, docs: Path = DOCS, root: Path = ROOT,
        replace_reason: str | None = None) -> dict[str, Any]:
    """Compute the table, write it and its receipt, and return a short summary.

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
    parser.add_argument("--output", type=Path, default=None,
                        help="default: outputs/planning_v1/age_exposure_<case>_v1.json")
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
    output = args.output or OUTPUT_DIR / f"age_exposure_{args.case}_v1.json"
    try:
        summary = run(args.case, args.age_dir, boundaries, output,
                      replace_reason=args.reason.strip() if args.replace else None)
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
