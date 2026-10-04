"""Build the flood inputs of the Mae Sai cases and report the run (plan task E1).

For each case this script loads the flood input the signed protocols name, through
``floodguard.flood_inputs``, and writes its layers:

* ``SE1``: the UNOSAT/GISTDA product 4009 accumulated layer, the 2024 season envelope (lane SCN-ENV);
* ``O2``: the product 4009 layer of 22 October 2024, its own dated case (lane OBS, tier T3).

Each input is repaired (with a count), given its minus and plus levels (20 m, protocol v1b owner choice 2) and
clipped to the reporting frame (the eight Mae Sai tambons of protocol v1a) and to the routing context (the
corridor of record of protocol v1b). The permanent water of the reporting frame is read from ESA WorldCover
2021 v200, class 80, as the scoring frame of protocol v1a states. The plan's acceptance check is made in the
same run: the accumulated layer clipped to AOI-01.

It computes no FPPS, no component value, no A-E class, no ensemble and no value for a single tambon, and
nothing it writes is an observation of a road closure or an official warning. The product 4009 layers are
used as provided; FloodGuard did not validate them.

**Rights.** The rights registry (``floodguard.rights``) must allow each layer before the archive is opened,
and the archive must have the size and SHA-256 the confirmed rights record names. Every layer derived from
product 4009 carries CC BY-SA 4.0, the credit and its own change notice, and sits in a folder with the
record's licence notice. Each written file carries the rights level of the layer it comes from: the footprint
layers come from the analysis extent, which the registry holds at ``local``, whatever the level of the flood
layer of the case; an input record holds figures of both layers and is at the minimum of the two (protocol
v1a, guardrail GR6). The receipt lists which of its own figures come from a local-level layer.

**Where things go.** Inputs are read-only files outside Git; their locations are arguments, and the external
data root defaults to the environment variable ``FLOODGUARD_EXTERNAL_DATA``. The layers are written outside
Git, under ``<external data root>/proposal_execution/planning_v1/``. The run receipt is written to
``outputs/planning_v1/e1_flood_inputs_<frame>.json`` and registered in
``outputs/planning_v1/run_register/``::

    python scripts/build_flood_inputs.py --frame mae_sai --external-data <external data root> \
        [--development-read "<what was read before this run>"] [--replace --reason "<why>"] [--verify]

Every run is reported. The script refuses to run unless protocol v1a and v1b are in force, and it refuses to
write over a receipt: a second run needs ``--replace --reason``, and its receipt names the receipt it
supersedes. ``--verify`` computes every layer again, compares its SHA-256 with the receipt and writes
nothing.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import flood_inputs, rights, rights_basis  # noqa: E402

RECEIPT_SCHEMA_VERSION = "floodguard.flood_inputs_run_receipt.v1"
DOCS = ROOT / "docs" / "proposal_execution"
OUTPUT_DIR = ROOT / "outputs" / "planning_v1"
REGISTER_DIR = OUTPUT_DIR / "run_register"
EXTERNAL_DATA_VARIABLE = "FLOODGUARD_EXTERNAL_DATA"
EXTERNAL_LABEL = "<external_data_workspace>"
BOUNDARY_RELATIVE_PATH = Path("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
WORLDCOVER_RELATIVE_PATH = Path("open_context") / "esa_worldcover" / "ESA_WorldCover_10m_2021_v200_N18E099_Map.tif"
PROCESSED_RELATIVE_PATH = Path("proposal_execution") / "planning_v1"
BOUNDARY_LAYER = "tha_admin3"
UNIT_ID_FIELD = "adm3_pcode"
STAGE_FOLDER = "e1_flood_input"
LICENCE_NOTICE_NAME = "LICENSE_NOTICE.txt"
INPUT_RECORD_NAME = flood_inputs.INPUT_RECORD_NAME
AOI_01_PATH = Path("resources") / "aoi" / "aoi-01_mae_sai_core.geojson"
ACCEPTANCE_KM2 = 15.34

FRAME_SETS: dict[str, dict[str, Any]] = {
    "mae_sai": {
        "title": "Mae Sai",
        "cases": ("SE1", "O2"),
        "case_folders": {"SE1": "se1_mae_sai", "O2": "o2_mae_sai"},
        "frame_folder": "mae_sai_frame",
        "reporting_label": "the eight Mae Sai subdistricts of protocol v1a (HDX Thailand COD-AB, layer tha_admin3)",
        "routing_label": "the Mae Sai routing corridor of protocol v1b (outputs/planning_v1/corridor_of_record.geojson)",
    },
}
LOADERS = {"SE1": flood_inputs.load_se1, "O2": flood_inputs.load_o2}

COMPUTES = (
    "The flood-input layers of cases SE1 and O2 over the Mae Sai frame: each extent as provided and at the minus and "
    "plus one-pixel levels, clipped to the reporting frame and to the routing context, the product footprint, and the "
    "permanent water of the reporting frame. Areas are for a whole frame. No FPPS, no component value, no A-E class, no "
    "ensemble and no value for a single tambon."
)
CONFIDENCE_BASIS = (
    "The flood layers are unvalidated preliminary agency extents (UNOSAT product 4009 with GISTDA; Field_Validation=0), "
    "used as provided; FloodGuard did not validate them. Nothing here was checked against an independent source."
)
ASSUMPTIONS = [
    "The product 4009 layers are used as provided: preliminary agency extents that were not checked in the field "
    "(Field_Validation=0). FloodGuard did not validate them.",
    "The accumulated layer is a season envelope with no date per patch (lane SCN-ENV). It is a scenario in which every "
    "area mapped as water in the season is treated as flooded at once; it is not an observation of any day and not the "
    "water of September 2024.",
    "The layer of 22 October 2024 is its own dated case, late-season residual water. It does not describe the "
    "September event.",
    "The minus and plus levels are 20 m buffers of the repaired layer, in EPSG:32647 (protocol v1b, owner choice 2). "
    "They are perturbations of one product state and no level is a central estimate.",
    "Every vertex is projected to EPSG:32647 as it is and areas are measured there, so an area is about 0.06 percent "
    "below its geodesic value near 99.9 E. Coordinates are snapped to a 1 mm grid.",
    "Permanent water is every ESA WorldCover 2021 v200 cell of class 80, taken by its footprint. It does not cut the "
    "extents; it is left out of the flood-likelihood areas only, as the scoring frame of protocol v1a states.",
    "The reporting frame is the union of the eight tambon polygons of the 2022 COD-AB layer. The flood layers are "
    "from 2024 and the land-cover map from 2021.",
]
LIMITATIONS = [
    "A flood extent is not a closure. Whether an edge is closed is a modelled assumption of the closure rule, which "
    "this run does not apply.",
    "The minus level removes every part of the extent narrower than 40 m, and the plus level joins parts less than "
    "40 m apart. The three levels of a layer made of narrow patches therefore differ widely; see the areas by level.",
    "The season envelope holds water of August and of early October as well. Its area is not the area flooded on any "
    "day.",
    "The third-party satellite imagery UNOSAT and GISTDA used to make the product is not relicensed by these files, "
    "and UNOSAT and GISTDA do not endorse FloodGuard or its use of the product.",
    "The layers are written outside Git. The receipt binds them by SHA-256; --verify computes them again from the "
    "inputs.",
]
NOT_COMPUTED = [
    "flood-likelihood component", "exposure component", "any other component", "FPPS", "A-E class", "would-be class",
    "ensemble cell", "closed or delayed edges", "access loss", "any value for a single tambon",
    "own radar candidates of case O1 (none has been delivered)",
]


def utc_now() -> str:
    """Return the current UTC time to the second, as the receipts write it."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def encode(payload: Mapping[str, Any]) -> bytes:
    """Serialise a receipt or a record: two-space indent, ASCII, LF, one final newline."""

    return (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def path_label(path: Path, root: Path, external: Path | None) -> str:
    """Name a file without a machine path: relative to the repository, or to the external data root."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        pass
    if external is not None:
        try:
            return f"{EXTERNAL_LABEL}/{resolved.relative_to(external.resolve()).as_posix()}"
        except ValueError:
            pass
    return path.name


def file_record(path: Path, root: Path, external: Path | None) -> dict[str, Any]:
    """Return the label, the SHA-256 and the size of an input file."""

    return {"path": path_label(path, root, external), "sha256": flood_inputs.sha256_file(path), "bytes": path.stat().st_size}


def read_units(boundaries: Path, unit_ids: Sequence[str]) -> tuple[list[tuple[str, Any]], dict[str, Any]]:
    """Read the unit polygons of a case frame from the COD-AB boundary layer.

    Raises:
        ValueError: when the layer is not in EPSG:4326 or a unit is missing or repeated.
    """

    import pyogrio

    quoted = ", ".join(f"'{unit}'" for unit in unit_ids)
    table = pyogrio.read_dataframe(boundaries, layer=BOUNDARY_LAYER, columns=[UNIT_ID_FIELD, "valid_on"],
                                   where=f"{UNIT_ID_FIELD} IN ({quoted})")
    if table.crs is None or table.crs.to_epsg() != 4326:
        raise ValueError("the boundary layer must be EPSG:4326")
    found = sorted((str(code), geometry) for code, geometry in zip(table[UNIT_ID_FIELD], table.geometry))
    if [code for code, _geometry in found] != sorted(unit_ids):
        raise ValueError("the boundary layer does not hold each unit of the frame exactly once")
    return found, {"layer": BOUNDARY_LAYER, "unit_id_field": UNIT_ID_FIELD, "units": len(found),
                   "valid_on": sorted({str(value)[:10] for value in table["valid_on"]})}


def read_polygon_file(path: Path) -> Any:
    """Read the union of the polygons of a GeoJSON file given in longitude and latitude."""

    import shapely
    from shapely.geometry import shape

    collection = json.loads(path.read_text(encoding="utf-8"))
    return shapely.union_all([shape(feature["geometry"]) for feature in collection["features"]])


def context_roads_area(boundaries: Path, routing: flood_inputs.Frame) -> tuple[Any, dict[str, Any]]:
    """Return the part of the routing context that can hold road segments of the context, and what it is.

    Protocol v1b, ``corridor_polygon.context_call``: the reporting geometry of the context call is the union
    of the COD-AB tha_admin3 polygons that intersect the corridor polygon, and the context build limits road
    segments to it. The part of the corridor outside every such polygon lies across the national border and
    holds no road of the context.
    """

    import pyogrio

    bounds = flood_inputs.project(routing.geometry, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS).bounds
    table = pyogrio.read_dataframe(boundaries, layer=BOUNDARY_LAYER, columns=[UNIT_ID_FIELD], bbox=bounds)
    units = flood_inputs.project(shapely.make_valid(table.geometry.values), flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS)
    meeting = shapely.intersects(units, routing.geometry)
    inside = flood_inputs.as_multipolygon(shapely.intersection(routing.geometry, shapely.union_all(units[meeting])))
    return inside, {
        "rule": "Protocol v1b, corridor_polygon.context_call.reporting_geometry: the union of the COD-AB tha_admin3 "
                "polygons that intersect the corridor polygon. The context build limits road segments to it.",
        "tha_admin3_units_meeting_the_routing_context": int(meeting.sum()),
        "area_km2": round(float(inside.area) / 1e6, 6),
        "share_of_routing_context": round(float(inside.area) / routing.area_m2, 6),
    }


def case_frames(frame_set: str, rules: flood_inputs.FloodInputRules, boundaries: Path, *, root: Path,
                external: Path | None) -> tuple[list[flood_inputs.Frame], dict[str, Any]]:
    """Build the reporting frame and the routing context of a frame set, and the records of their inputs.

    Raises:
        ValueError: when the boundary file or the corridor file is not the one protocol v1b names.
    """

    labels = FRAME_SETS[frame_set]
    boundary = file_record(boundaries, root, external)
    if boundary["sha256"] != rules.boundary_file_sha256:
        raise ValueError("the boundary file is not the one protocol v1b names")
    units, summary = read_units(boundaries, rules.reporting_units)
    corridor_path = root / rules.routing_geometry_file["path"]
    corridor = file_record(corridor_path, root, external)
    if corridor["sha256"] != rules.routing_geometry_file["sha256"]:
        raise ValueError("the corridor file is not the one protocol v1b names")
    reporting = flood_inputs.frame_from_units(
        flood_inputs.REPORTING_FRAME, labels["reporting_label"], units,
        {**boundary, **summary, "unit_ids": list(rules.reporting_units),
         "unit_list": "planning_protocol_v1a.json /case_portfolio/mae_sai_reporting_frame/units"})
    routing = flood_inputs.frame_from_wgs84(
        flood_inputs.ROUTING_CONTEXT, labels["routing_label"], read_polygon_file(corridor_path),
        {**corridor, "named_in": "planning_protocol_v1b.json /corridor_polygon/geometry_file"})
    return [reporting, routing], {"tambon_boundaries": {**boundary, **summary}, "routing_geometry": corridor}


def acceptance_check(rules: flood_inputs.FloodInputRules, registry: rights.RightsRegistry, external: Path, *, root: Path) -> dict[str, Any]:
    """Make the acceptance check of plan row E1: the product 4009 clip inside AOI-01 against 15.34 km2.

    Both product 4009 layers are clipped to AOI-01 as provided. The area is given in EPSG:32647, where every
    area of this run is measured, and on the WGS 84 ellipsoid.
    """

    from pyproj import Geod

    aoi_path = root / AOI_01_PATH
    frame = flood_inputs.frame_from_wgs84(
        "aoi_01", "AOI-01 (resources/aoi/aoi-01_mae_sai_core.geojson)", read_polygon_file(aoi_path), file_record(aoi_path, root, external))
    geod = Geod(ellps="WGS84")
    layers: dict[str, Any] = {}
    for case_id, loader in LOADERS.items():
        loaded = loader([frame], rules=rules, registry=registry, external_root=external, footprint_layer=None)
        geodesic = abs(geod.geometry_area_perimeter(loaded.extent_wgs84(flood_inputs.AS_PROVIDED, frame.name))[0])
        summary = loaded.record["levels"]["by_level"][flood_inputs.AS_PROVIDED][frame.name]
        layers[case_id] = {
            "layer": loaded.record["source"]["layer"],
            "clip_km2_epsg32647": summary["area_km2"],
            "clip_km2_geodesic_wgs84": round(geodesic / 1e6, 6),
            "repair": {**{key: loaded.record["repair"][key] for key in
                          ("method", "source_parts", "source_parts_invalid", "parts_read", "parts_repaired", "parts_repaired_after_projection")},
                       "in_aoi_01": loaded.record["repair"]["by_frame"][frame.name]},
        }
    measured = layers["SE1"]["clip_km2_epsg32647"]
    return {
        "plan_row": "E1: clip reproduces 15.34 km2 for 4009 in AOI-01; repair count; +/-1 px layers",
        "aoi_01": {**dict(frame.source), "area_km2_epsg32647": round(frame.area_m2 / 1e6, 6)},
        "expected_km2": ACCEPTANCE_KM2,
        "layers": layers,
        "reproduced": round(measured, 2) == ACCEPTANCE_KM2,
        "reproduced_by": "the accumulated layer, as provided, clipped to AOI-01, area in EPSG:32647 rounded to two decimals",
        "note": "The plan row does not say which product 4009 layer or which area measure gives the figure. reproduced "
                "compares the area of the accumulated layer in EPSG:32647, rounded to two decimals. Its area on the "
                "WGS 84 ellipsoid and the layer of 22 October 2024 are shown beside it.",
    }


def software_versions() -> dict[str, str]:
    """Return the versions of the libraries that decide the geometry."""

    import numpy
    import pyogrio
    import pyproj
    import rasterio
    import shapely

    return {"python": platform.python_version(), "numpy": numpy.__version__, "shapely": shapely.__version__,
            "geos": shapely.geos_version_string, "pyproj": pyproj.__version__, "proj": pyproj.proj_version_str,
            "pyogrio": pyogrio.__version__, "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__}


def water_properties(water: flood_inputs.PermanentWater, frame: flood_inputs.Frame, rules: flood_inputs.FloodInputRules) -> dict[str, Any]:
    """Return the properties of the permanent-water layer: an ESA WorldCover derivative, not a product 4009 one."""

    record = water.record
    return {
        "layer_schema": flood_inputs.LAYER_SCHEMA,
        "what": "permanent_water",
        "frame": frame.name,
        "frame_label": frame.label,
        "source": record["source"],
        "class": record["class"],
        "source_file": {"file": record["file"], "sha256": record["sha256"]},
        "source_timestamp": f"{str(record['time_start'])[:10]}/{str(record['time_end'])[:10]}",
        "confidence_class": "low",
        "confidence_basis": "A class of a global land-cover map of 2021, taken as it is. FloodGuard did not check it "
                            "against the ground or against the water of 2024.",
        "assumptions": [
            "Permanent water is every cell of class 80 (permanent water bodies), by its footprint.",
            "The map describes 2021. A channel that moved, or a pond made since, is not in it.",
            "A cell with no land-cover value is not counted as water.",
        ],
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "licence": record["licence"],
        "credit": record["attribution"],
        "change_notice": f"Changed by FloodGuard: cells of class {record['class']} polygonised by their footprints; "
                         f"reprojected from {record['raster_crs']} to {flood_inputs.ANALYSIS_CRS}; clipped to {frame.label}; "
                         f"coordinates snapped to a {flood_inputs.COORDINATE_GRID_M:g} m grid. Source: {record['attribution']}.",
        "rule": flood_inputs.PERMANENT_WATER_RULE,
        "protocol_sha256": flood_inputs.protocol_hashes(rules),
    }


def build(frame_set: str, external: Path, boundaries: Path, worldcover: Path, *, generated_at_utc: str, docs: Path = DOCS,
          root: Path = ROOT, development_reads: Sequence[str] = ()) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Compute every layer of a frame set and the body of the run receipt (nothing is written).

    Args:
        frame_set: A key of ``FRAME_SETS``.
        external: The external data root (the product archive is found under it, as the rights record says).
        boundaries: The COD-AB boundary file.
        worldcover: The ESA WorldCover 2021 v200 tile that covers the frame.
        generated_at_utc: The generation time the input records carry.
        docs: The folder with the two protocol files and ``RECEIPTS.jsonl``.
        root: The repository root (rights records, corridor, AOI-01).
        development_reads: What was read from the inputs before this run, in the operator's words.

    Returns:
        The files to write, keyed by their path under the processed-data folder, and the receipt without its
        time fields.

    Raises:
        ValueError: when a protocol is not in force, an input is not the one a signed file names, or the
            rights registry refuses a layer.
    """

    timings: dict[str, float] = {}
    clock = time.perf_counter()
    rules = flood_inputs.load_rules(docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl")
    hashes = flood_inputs.protocol_hashes(rules)
    registry = rights.RightsRegistry(root)
    settings = FRAME_SETS[frame_set]
    frames, frame_inputs = case_frames(frame_set, rules, boundaries, root=root, external=external)
    reporting, routing = frames
    road_area, road_area_record = context_roads_area(boundaries, routing)

    if "2021_v200" not in worldcover.name:
        raise ValueError(f"protocol v1a names {rules.permanent_water_source}; {worldcover.name} is not named as that product")
    water = flood_inputs.permanent_water(worldcover, reporting, water_class=rules.permanent_water_class,
                                         source_name=rules.permanent_water_source)
    if water.record["product_version"] != "V2.0.0" or not str(water.record["time_start"]).startswith("2021"):
        raise ValueError(f"protocol v1a names {rules.permanent_water_source}; the raster says otherwise")
    timings["frames_and_permanent_water"] = round(time.perf_counter() - clock, 1)

    files: dict[str, bytes] = {}
    outputs: dict[str, Any] = {}
    water_name = f"{settings['frame_folder']}/{STAGE_FOLDER}/permanent_water__{reporting.name}.geojson"
    files[water_name] = flood_inputs.encode_layer(water.geometry, water_properties(water, reporting, rules), "permanent_water")
    outputs["frame"] = {"folder": f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/{settings['frame_folder']}/{STAGE_FOLDER}",
                        "files": [_output(water_name, files[water_name], what="permanent_water", frame=reporting.name)]}

    record_4009, record_sha256 = registry.read_record(rights.PRODUCT_4009)
    notice_path = root / record_4009["licence_notice_file"]
    notice = notice_path.read_bytes()
    input_records: dict[str, Any] = {}
    grants: dict[str, Any] = {}
    footprint_grants: dict[str, Any] = {}
    output_levels: dict[str, Any] = {}
    footprint_checks: dict[str, Any] = {}
    for case_id in settings["cases"]:
        clock = time.perf_counter()
        loaded = LOADERS[case_id](frames, rules=rules, registry=registry, external_root=external, water=water)
        folder = f"{settings['case_folders'][case_id]}/{STAGE_FOLDER}"
        lineage = loaded.record["lineage_rights"]
        written: list[dict[str, Any]] = []
        for level in flood_inputs.LEVELS:
            for frame in frames:
                name = f"{folder}/flood_extent__{level}__{frame.name}.geojson"
                properties = flood_inputs.layer_properties(
                    loaded, level=level, frame=frame, what=flood_inputs.FLOOD_EXTENT,
                    change=flood_inputs.level_sentence(level, rules.one_pixel_m))
                files[name] = flood_inputs.encode_layer(loaded.extent(level, frame.name), properties, f"flood_extent__{level}__{frame.name}")
                written.append(_output(name, files[name], what=flood_inputs.FLOOD_EXTENT, level=level, frame=frame.name,
                                       rights_level=properties["rights_level"]))
        for frame in frames:
            name = f"{folder}/product_footprint__{frame.name}.geojson"
            properties = flood_inputs.layer_properties(loaded, level=None, frame=frame, what=flood_inputs.PRODUCT_FOOTPRINT,
                                                       change="analysis extent otherwise as provided")
            files[name] = flood_inputs.encode_layer(loaded.footprints[frame.name], properties, f"product_footprint__{frame.name}")
            written.append(_output(name, files[name], what=flood_inputs.PRODUCT_FOOTPRINT, frame=frame.name,
                                   rights_level=properties["rights_level"]))
        files[f"{folder}/{LICENCE_NOTICE_NAME}"] = notice
        written.append(_output(f"{folder}/{LICENCE_NOTICE_NAME}", notice, what="licence_notice"))
        record = {
            "generated_at_utc": generated_at_utc,
            **dict(loaded.record),
            "licence_notice_file": LICENCE_NOTICE_NAME,
            "files": [{"file": entry["path"].rsplit("/", 1)[1], **{key: value for key, value in entry.items() if key != "path"}}
                      for entry in written],
        }
        files[f"{folder}/{INPUT_RECORD_NAME}"] = encode(record)
        written.append(_output(f"{folder}/{INPUT_RECORD_NAME}", files[f"{folder}/{INPUT_RECORD_NAME}"], what="input_record",
                               rights_level=lineage["input_record"]))
        input_records[case_id] = dict(loaded.record)
        grants[case_id] = loaded.record["rights"]
        footprint_grants[case_id] = loaded.record["footprint"]["rights"]
        output_levels[case_id] = {key: lineage[key] for key in (flood_inputs.FLOOD_EXTENT, flood_inputs.PRODUCT_FOOTPRINT, "input_record")}
        uncovered = shapely.difference(road_area, loaded.footprints[routing.name])
        footprint_checks[case_id] = {
            "footprint_layer": flood_inputs.ANALYSIS_EXTENT_LAYER_4009,
            "footprint_layer_rights_level": footprint_grants[case_id]["rights_level"],
            "share_of_reporting_frame": loaded.record["footprint"]["by_frame"][reporting.name]["share_of_frame"],
            "share_of_routing_context": loaded.record["footprint"]["by_frame"][routing.name]["share_of_frame"],
            "routing_context_that_can_hold_roads_outside_the_footprint_km2": round(float(uncovered.area) / 1e6, 6),
        }
        outputs[case_id] = {"folder": f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/{folder}", "files": written}
        timings[f"case_{case_id}"] = round(time.perf_counter() - clock, 1)

    clock = time.perf_counter()
    acceptance = acceptance_check(rules, registry, external, root=root)
    timings["acceptance_check"] = round(time.perf_counter() - clock, 1)

    archive_path = external / record_4009["archive"]["relative_path"]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "plan_task": "E1: flood_inputs.py + rights.py + tests",
        "run": f"Flood inputs of cases {' and '.join(settings['cases'])} over the {settings['title']} frame",
        "status": "run_receipt",
        "status_note": "Receipt of one run on real frames, made with protocol v1a and v1b in force. Every run is reported: "
                       "a second run writes a new receipt that names this one. The layers are outside Git and are bound "
                       "here by SHA-256. The receipt holds whole-frame figures of layers the rights registry holds at "
                       "the local level; rights.figures_of_local_level_layers_in_this_receipt lists them.",
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "computes": COMPUTES,
        "source_timestamp": record_4009["source_timestamp"],
        "source_timestamps": {
            "product_4009": record_4009["source_timestamp"],
            **{case_id: input_records[case_id]["source_timestamp"] for case_id in settings["cases"]},
            "permanent_water": f"{str(water.record['time_start'])[:10]}/{str(water.record['time_end'])[:10]}",
            "tambon_boundaries_valid_on": frame_inputs["tambon_boundaries"]["valid_on"],
        },
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "protocol_sha256": hashes,
        "protocol_state": {name: "in_force" for name in ("v1a", "v1b")},
        "licence": {
            "applies_to": "Every figure and file of this run that is derived from UNOSAT/GISTDA product 4009: the areas, "
                          "the part counts and the layers of cases SE1 and O2.",
            **{key: record_4009["licence"][key] for key in ("name", "full_name", "spdx_id", "url", "legal_code_url")},
            "credit": record_4009["required_attribution_text"],
            "share_alike": record_4009["share_alike"],
            "standard_sentence": rules.standard_4009_sentence,
            "change_notice": "Changed by FloodGuard: each product 4009 layer was repaired (make_valid), projected from "
                             "EPSG:4326 to EPSG:32647, clipped to the frames named here and, for the minus and plus "
                             "levels, shrunk or grown by 20 m; the areas in this file were then measured. Each layer "
                             "file states its own change notice. Source: "
                             f"{record_4009['required_attribution_text']}, {record_4009['licence']['name']}.",
            "other_inputs": other_inputs(water),
            "not_legal_advice": True,
        },
        "parameters": {
            "frame_set": frame_set,
            "cases": list(settings["cases"]),
            "unit_ids": list(rules.reporting_units),
            "analysis_crs": flood_inputs.ANALYSIS_CRS,
            "coordinate_grid_m": flood_inputs.COORDINATE_GRID_M,
            "one_pixel_m": rules.one_pixel_m,
            "one_pixel_source": "planning_protocol_v1b.json /ensemble_grid/core_axes (flood_input_single_state) /one_pixel_m",
            "buffer": {"join_style": "round", "segments_per_quarter_circle": flood_inputs.BUFFER_QUAD_SEGS},
            "levels": list(flood_inputs.LEVELS),
            "level_rule": flood_inputs.LEVEL_RULE,
            "repair_method": flood_inputs.REPAIR_METHOD,
            "recency_window_days": rules.recency_window_days,
            "permanent_water": {"source": rules.permanent_water_source, "class": rules.permanent_water_class,
                                "rule": flood_inputs.PERMANENT_WATER_RULE},
            "layers_read": {
                "SE1": rules.accumulated_layer["layer"], "O2": rules.layer_22_oct["layer"],
                "footprint": flood_inputs.ANALYSIS_EXTENT_LAYER_4009,
                "footprint_named_by": "floodguard.flood_inputs.ANALYSIS_EXTENT_LAYER_4009, a constant of the code. The "
                                      "protocols and the rights record name no footprint layer (open point E1-OP10).",
            },
        },
        "inputs": {
            "product_4009_archive": {**file_record(archive_path, root, external), "geodatabase": flood_inputs.GEODATABASE_4009,
                                     "is_the_archive_the_rights_record_names": True},
            "rights_record_4009": {"path": rights_basis.RIGHTS_BASIS_4009_PATH.as_posix(), "sha256": record_sha256,
                                   "record_status": record_4009["record_status"]},
            "licence_notice_4009": file_record(notice_path, root, external),
            **frame_inputs,
            "permanent_water_raster": {**file_record(worldcover, root, external), "source": rules.permanent_water_source},
            "aoi_01": acceptance["aoi_01"],
            "planning_protocol_v1a": {"path": path_label(docs / "planning_protocol_v1a.json", root, external),
                                      "sha256": hashes["planning_protocol_v1a"]},
            "planning_protocol_v1b": {"path": path_label(docs / "planning_protocol_v1b.json", root, external),
                                      "sha256": hashes["planning_protocol_v1b"]},
            "protocol_receipts": file_record(docs / "RECEIPTS.jsonl", root, external),
        },
        "rights": {
            "registry": "floodguard.rights.REGISTERED_RECORDS",
            "registered_inputs": list(registry.input_ids()),
            "rule": "A layer is read only when the registry finds a confirmed rights record for its input, and the "
                    "archive has the size and SHA-256 that record names. Each layer that is read has its own grant, and "
                    "each written file carries the level of the layer it comes from; a file that holds figures of two "
                    "layers is at the minimum of the two (protocol v1a, guardrail GR6). A write under apps/web/public/ "
                    "needs rights level public; this run writes nothing there.",
            "grants": grants,
            "footprint_layer_grants": footprint_grants,
            "output_rights_level": output_levels,
            "output_rights_level_note": "By case and kind of file. A flood extent comes from the flood layer only, a "
                                        "footprint layer from the analysis extent only, and the input record holds "
                                        "figures of both. Every written file states its own level (outputs).",
            "levels_and_git": rights.LEVELS_AND_GIT,
            "figures_of_local_level_layers_in_this_receipt": local_level_figures(settings["cases"], grants, footprint_grants),
            "written_under_apps_web_public": False,
        },
        "frames": {frame.name: {"label": frame.label, "area_km2": round(frame.area_m2 / 1e6, 6), "units": sorted(frame.units)}
                   for frame in frames},
        "frame_note": "The reporting frame is the union of the eight tambon polygons. The demand area of the context "
                      "build is that union clipped to AOI-02 (protocol v1b, owner choice 21), which is 214.5 square "
                      "metres smaller. The routing context is the corridor polygon; the context build keeps the road "
                      "segments inside it.",
        "footprint_check": {
            "what": "Where the product says nothing, the water is unknown, not absent. The analysis extent of the "
                    "product is its footprint; the two shares say how much of each frame it covers. The corridor "
                    "polygon reaches across the national border, where the context holds no road, so the last figure "
                    "gives how much of the part that can hold roads the footprint leaves out.",
            "routing_context_that_can_hold_roads": road_area_record,
            "by_case": footprint_checks,
        },
        "permanent_water": dict(water.record),
        "flood_inputs": input_records,
        "acceptance": acceptance,
        "outputs": outputs,
        "development_reads": {
            "what": "Reads of the same inputs made while the code was written, before this run. They wrote no file "
                    "and computed no value for a single tambon. They are listed because every run is reported.",
            "reads": list(development_reads),
        },
        "open_points": [dict(point) for point in flood_inputs.OPEN_POINTS],
        "not_computed": NOT_COMPUTED,
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
        "implementation": {
            "base_commit": commit.stdout.strip() or None,
            "base_commit_note": "The commit the working tree was on. The files below are the ones this run loaded, "
                                "identified by their own SHA-256, committed or not.",
            "builder_sha256": flood_inputs.sha256_file(Path(__file__)),
            "flood_inputs_module_sha256": flood_inputs.sha256_file(Path(str(flood_inputs.__file__))),
            "rights_module_sha256": flood_inputs.sha256_file(Path(str(rights.__file__))),
            "rights_basis_module_sha256": flood_inputs.sha256_file(Path(str(rights_basis.__file__))),
            "flood_inputs_version": flood_inputs.FLOOD_INPUTS_VERSION,
            "software": software_versions(),
        },
        "timing_seconds": timings,
    }
    return files, receipt


def local_level_figures(cases: Sequence[str], grants: Mapping[str, Mapping[str, Any]],
                        footprint_grants: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Say which figures of the receipt come from a layer the registry holds below the public level.

    The layers themselves stay outside Git. The receipt is committed and holds whole-frame figures of every
    layer the run read, so it lists the ones whose layer is not public: the signed files do not say whether
    such a figure may be committed (``floodguard.rights.LEVELS_AND_GIT``; open point E1-OP1).
    """

    listed: list[dict[str, str]] = []
    for case_id in cases:
        flood, footprint = grants[case_id], footprint_grants[case_id]
        if flood["rights_level"] != rights.PUBLIC_LEVEL:
            listed.append({
                "case_id": case_id, "layer": str(flood["layer"]), "rights_level": str(flood["rights_level"]),
                "figures": "The areas by level and frame, the areas on and off permanent water, the part and repair "
                           "counts and the AOI-01 clip of the layer.",
                "where": f"flood_inputs.{case_id} (levels, repair) and acceptance.layers.{case_id}",
            })
        if footprint["rights_level"] != rights.PUBLIC_LEVEL:
            listed.append({
                "case_id": case_id, "layer": str(footprint["layer"]), "rights_level": str(footprint["rights_level"]),
                "figures": "The area of the footprint inside each frame, its share of each frame, and the part of the "
                           "routing context that can hold roads and lies outside it.",
                "where": f"flood_inputs.{case_id}.footprint and footprint_check.by_case.{case_id}",
            })
    return {
        "what": "This receipt is committed. It holds whole-frame figures, and no layer, of every layer the run read. "
                "The figures listed here come from a layer the rights registry holds below the public level.",
        "figures": listed,
        "for_the_owners": "Open point E1-OP1: whether a local level allows these figures in Git. They have been in the "
                          "receipt since the first commit of this task.",
    }


def other_inputs(water: flood_inputs.PermanentWater) -> list[dict[str, str]]:
    """List the inputs besides product 4009 whose figures the receipt holds, each with its licence and credit."""

    from floodguard import season_envelope

    listed = [
        {"id": "esa-worldcover", "name": f"{water.record['source']} ({water.record['file']})",
         "licence": str(water.record["licence"]), "attribution": str(water.record["attribution"]),
         "used_for": "The permanent water of the reporting frame, and the area of each level on and off it."},
        {"id": "cod-ab", "name": "HDX Thailand COD-AB subdistrict boundaries (tha_admin3)", "licence": "CC BY-IGO",
         "attribution": "OCHA / HDX Thailand COD-AB", "used_for": "The reporting frame: the eight tambon polygons."},
        {"id": "osm", "name": "OpenStreetMap roads, through the corridor polygon of record",
         "licence": "ODbL 1.0", "attribution": "(c) OpenStreetMap contributors",
         "used_for": "The routing context: the corridor polygon was built along OpenStreetMap routes."},
    ]
    problems = season_envelope.other_input_problems(listed)
    if problems:
        raise ValueError(f"an input besides the product lacks its licence or credit: {problems}")
    return listed


def _output(name: str, data: bytes, **what: Any) -> dict[str, Any]:
    """Describe one written file: its label under the external data root, its SHA-256, its size and what it is."""

    entry = flood_inputs.file_entry(name, data, **what)
    return {"path": f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/{entry.pop('file')}", **entry}


def output_hashes(outputs: Mapping[str, Any]) -> dict[str, str]:
    """Return the SHA-256 of every file a receipt binds, keyed by its path label."""

    return {entry["path"]: entry["sha256"] for group in outputs.values() for entry in group["files"]}


def earlier_runs(previous: Mapping[str, Any], supersedes: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return every earlier run of a receipt, oldest first: the runs the replaced receipt listed, and that receipt.

    A receipt written before ``run_history`` existed names only the run it superseded; that run is taken from
    its ``supersedes`` block.
    """

    history = [dict(entry) for entry in previous.get("run_history") or []]
    older = previous.get("supersedes")
    if not history and isinstance(older, Mapping):
        history.append({
            "generated_at_utc": older.get("generated_at_utc"),
            "receipt_sha256": older.get("receipt_sha256"),
            "superseded_because": older.get("reason"),
            "layers_same_as_the_run_that_replaced_it": older.get("layers_same"),
        })
    history.append({
        "generated_at_utc": supersedes["generated_at_utc"],
        "receipt_sha256": supersedes["receipt_sha256"],
        "superseded_because": supersedes["reason"],
        "layers_same_as_the_run_that_replaced_it": supersedes["layers_same"],
        "geometry_same_as_the_run_that_replaced_it": supersedes.get("geometry_same"),
    })
    return history


def geometry_differs(old: bytes, new: bytes) -> bool:
    """Say whether two written layers hold another geometry; their properties are not compared."""

    try:
        return json.loads(old)["features"][0]["geometry"] != json.loads(new)["features"][0]["geometry"]
    except (ValueError, KeyError, IndexError, TypeError):
        return True


def receipt_path_for(frame_set: str, output_dir: Path = OUTPUT_DIR) -> Path:
    """Return the one place the receipt of a frame set is written."""

    return output_dir / f"e1_flood_inputs_{frame_set}.json"


def run(frame_set: str, external: Path, boundaries: Path, worldcover: Path, *, processed_root: Path, receipt_path: Path,
        register_dir: Path | None = REGISTER_DIR, docs: Path = DOCS, root: Path = ROOT, replace_reason: str | None = None,
        development_reads: Sequence[str] = ()) -> dict[str, Any]:
    """Compute the layers, write them, write the receipt and register it; return a short summary.

    Raises:
        FileExistsError: when the receipt exists and no replacement reason is given.
        FileNotFoundError: when a replacement is asked for and no receipt exists.
        ValueError: see :func:`build`.
    """

    if replace_reason is None and receipt_path.exists():
        raise FileExistsError("the receipt exists; a second run needs --replace --reason")
    if replace_reason is not None and not receipt_path.exists():
        raise FileNotFoundError("--replace needs an existing receipt")
    started = utc_now()
    files, receipt = build(frame_set, external, boundaries, worldcover, generated_at_utc=started, docs=docs, root=root,
                           development_reads=development_reads)
    supersedes, history = None, None
    if replace_reason is not None:
        previous = json.loads(receipt_path.read_text(encoding="ascii"))
        before, after = output_hashes(previous["outputs"]), output_hashes(receipt["outputs"])
        differing = sorted(path for path in set(before) | set(after)
                           if before.get(path) != after.get(path) and not path.endswith(INPUT_RECORD_NAME))
        # A layer whose bytes differ is read back from the disk, as the bytes the old receipt binds, and its
        # geometry is compared with the new one. A layer that cannot be read back that way counts as differing.
        prefix = f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/"
        geometry_differing = []
        for path in differing:
            name = path[len(prefix):]
            target = processed_root / name
            if name not in files or not target.is_file() or flood_inputs.sha256_file(target) != before.get(path):
                geometry_differing.append(path)
            elif geometry_differs(target.read_bytes(), files[name]):
                geometry_differing.append(path)
        supersedes = {
            "receipt_sha256": flood_inputs.sha256_file(receipt_path),
            "generated_at_utc": previous.get("generated_at_utc"),
            "reason": replace_reason,
            "layers_same": not differing,
            "layers_that_differ": differing,
            "geometry_same": not geometry_differing,
            "layers_that_differ_in_geometry": geometry_differing,
            "note": "The superseded receipt is named here by its SHA-256, and run_history lists every earlier run. A "
                    "receipt that was replaced before it was committed is not in the Git history: only its SHA-256 "
                    "remains. The layers are compared by SHA-256; an input record carries its generation time and is "
                    "left out of the comparison. A layer whose bytes differ was read back from the disk as the bytes "
                    "the superseded receipt binds, and its geometry was compared with the new one: geometry_same says "
                    "whether only properties changed. A layer that could not be read back as those bytes is listed as "
                    "differing in geometry.",
        }
        history = earlier_runs(previous, supersedes)
    for name, data in files.items():
        target = processed_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    finished = utc_now()
    receipt = {
        "schema_version": receipt["schema_version"],
        "generated_at_utc": started,
        "run_kind": "first_run" if supersedes is None else "superseding_run",
        **{key: value for key, value in receipt.items() if key != "schema_version"},
        "timestamps": {"run_started_at_utc": started, "run_finished_at_utc": finished,
                       "note": "generated_at_utc is the start of the run; the input records carry the same time."},
    }
    if supersedes is not None:
        receipt["supersedes"] = supersedes
        receipt["run_history"] = history
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(encode(receipt))
    receipt_sha256 = flood_inputs.sha256_file(receipt_path)
    label = path_label(receipt_path, root, None)
    if register_dir is not None:
        register_dir.mkdir(parents=True, exist_ok=True)
        (register_dir / receipt_path.name).write_bytes(encode({"path": label, "sha256": receipt_sha256}))
    return {"receipt": label, "receipt_sha256": receipt_sha256, "files_written": len(files),
            "bytes_written": sum(len(data) for data in files.values()), "generated_at_utc": started,
            "acceptance_reproduced": receipt["acceptance"]["reproduced"]}


def verify(frame_set: str, external: Path, boundaries: Path, worldcover: Path, *, processed_root: Path, receipt_path: Path,
           docs: Path = DOCS, root: Path = ROOT) -> dict[str, Any]:
    """Compute every layer again and compare it with the receipt and with the files on disk; write nothing."""

    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    files, _body = build(frame_set, external, boundaries, worldcover, generated_at_utc=receipt["generated_at_utc"],
                         docs=docs, root=root)
    bound = output_hashes(receipt["outputs"])
    prefix = f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/"
    differing, missing = [], []
    for name, data in files.items():
        digest = hashlib.sha256(data).hexdigest()
        if bound.get(prefix + name) != digest:
            differing.append(name)
        target = processed_root / name
        if not target.is_file():
            missing.append(name)
        elif flood_inputs.sha256_file(target) != digest:
            differing.append(f"{name} (on disk)")
    unbound = sorted(set(bound) - {prefix + name for name in files})
    return {"verified": not differing and not missing and not unbound, "files_compared": len(files),
            "differing": sorted(set(differing)), "missing_on_disk": missing, "bound_but_not_recomputed": unbound}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the arguments and make one reported run, or verify the last one."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frame", choices=sorted(FRAME_SETS), required=True)
    parser.add_argument("--external-data", type=Path, default=None,
                        help=f"external data root; default: the environment variable {EXTERNAL_DATA_VARIABLE}")
    parser.add_argument("--boundaries", type=Path, default=None,
                        help="the COD-AB boundary file; default: <external data root>/" + BOUNDARY_RELATIVE_PATH.as_posix())
    parser.add_argument("--worldcover", type=Path, default=None,
                        help="the ESA WorldCover 2021 v200 tile; default: <external data root>/" + WORLDCOVER_RELATIVE_PATH.as_posix())
    parser.add_argument("--development-read", action="append", default=[],
                        help="one read of the inputs made before this run, in a sentence; repeat for each")
    parser.add_argument("--replace", action="store_true", help="make a second run; needs --reason, and the new receipt names the old")
    parser.add_argument("--reason", help="why the run is repeated (one sentence)")
    parser.add_argument("--verify", action="store_true", help="compute the layers again and compare them with the receipt; write nothing")
    args = parser.parse_args(argv)
    if args.replace != bool((args.reason or "").strip()):
        parser.error("--replace and --reason go together")
    external = args.external_data or (Path(os.environ[EXTERNAL_DATA_VARIABLE]) if os.environ.get(EXTERNAL_DATA_VARIABLE) else None)
    if external is None:
        parser.error(f"give --external-data or set {EXTERNAL_DATA_VARIABLE}")
    boundaries = args.boundaries or external / BOUNDARY_RELATIVE_PATH
    worldcover = args.worldcover or external / WORLDCOVER_RELATIVE_PATH
    common = {"processed_root": external / PROCESSED_RELATIVE_PATH, "receipt_path": receipt_path_for(args.frame)}
    try:
        if args.verify:
            summary = verify(args.frame, external, boundaries, worldcover, **common)
            print(json.dumps(summary))
            return 0 if summary["verified"] else 1
        summary = run(args.frame, external, boundaries, worldcover, **common,
                      replace_reason=args.reason.strip() if args.replace else None, development_reads=args.development_read)
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
