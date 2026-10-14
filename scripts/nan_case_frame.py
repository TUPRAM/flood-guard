"""Build the frame and planning context of the Nan case N1 (decision log R51; nan_case_protocol_v1.json).

The case protocol fixes the frame: the 35 COD-AB ``tha_admin3`` units of Mueang Nan, Phu Phiang and Wiang Sa;
routing through their union buffered by 3 km (the SE2 frame rule of protocol v1b); every OSM hospital whose
routing point lies inside; and the rest of the planning chain as protocols v1a and v1b state it. This script
builds that frame with the code that built the Mae Sai and Mueang Chiang Rai frames, unchanged:

* ``frame``: the units and the routing geometry (``floodguard.planning_frames``), the hospitals inside
  (``floodguard.evidence_context`` extraction, as ``scripts/build_planning_frames.py`` reads it), a check of the
  20 m grid against the protocol, and a raster of the units on that grid;
* ``context``: the vehicle planning context by the rules of plan task E4 (``build_planning_context.build``,
  unchanged: road graph, grade joins at 0 m, vehicle class speeds, OSM hospitals, main-road entries and the
  WorldPop 2020 demand cells), without DDPM shelters, which are not part of the N1 score;
* ``age``: the WorldPop 2024 1 km age counts of each unit, by the functions of plan task E7;
* ``demand``: the demand cells, each counted for the unit that holds its centre, with their 2024-rescaled
  count (``build_ensemble_rescaled_demand.rescaled_residents``, unchanged) and their cell of the 20 m grid;
* ``baseline``: baseline access (no flood) per tambon: residents with a vehicle route to a hospital within 30
  minutes and to a main-road entry within 15 minutes, and the baseline no-route share;
* ``record``: ``outputs/nan_case/frame_v1.json``, which binds every file above by SHA-256.

It reads no flood layer, computes no flood flag over the frame, and computes no closure, access loss,
component, FPPS, A-E class or ensemble. It opens nothing under the sealed reference folder of the case.
Planning guidance only: not an official warning and not real-time.

Example::

    python scripts/nan_case_frame.py --external-root <external data root> \\
        --age-dir <folder of the 20 WorldPop 2024 age rasters> \\
        [--dga-facilities <thailand_health_facilities_th.geojson>] [--stage all] [--replace --reason "<why>"]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from floodguard import nan_frame  # noqa: E402
from floodguard import planning_frames as frames  # noqa: E402

DOCS = ROOT / "docs" / "proposal_execution"
PROTOCOL_PATH = DOCS / "nan_case_protocol_v1.json"
PROTOCOL_V1A = DOCS / "planning_protocol_v1a.json"
PROTOCOL_V1B = DOCS / "planning_protocol_v1b.json"
AREAS_PATH = ROOT / "outputs" / "nan_case" / "areas_v1.json"
RECORD_PATH = ROOT / "outputs" / "nan_case" / "frame_v1.json"
SOURCE_MANIFEST = ROOT / "outputs" / "open_context_data_file_manifest.csv"
EXTERNAL_LABEL = "<external_data_workspace>"
BOUNDARY_RELATIVE = Path("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
OSM_RELATIVE = Path("open_context") / "osm_geofabrik" / "thailand-latest.osm.pbf"
WORLDPOP_RELATIVE = Path("open_context") / "worldpop_population" / "tha_ppp_2020.tif"
WORK_RELATIVE = Path("proposal_execution") / "nan_case_v1" / "frame"
SEALED_FOLDER = "jaxa_sealed"
SCHEMA = "floodguard.nan_case_frame.v1"
STAGES = ("frame", "context", "age", "demand", "baseline", "record")
CHECK_STAGE = "verify"
COUNTRY_PAD_DEG = 0.1
BOUNDARY_WINDOW_MARGIN_DEG = 0.45  # the reporting-geometry read window of build_planning_context.load_case
HOSPITAL_GAP_MINUTES = 30
MAIN_ROAD_GAP_MINUTES = 15
RESIDENT_TOLERANCE = 1e-6

FILES = {
    "units": "n1_units.geojson",
    "routing": "n1_routing_geometry.geojson",
    "frame_stage": "frame_stage_v1.json",
    "osm_extract": "osm_frame_extract",
    "unit_raster": "n1_units_20m.tif",
    "context_dir": "e4_vehicle_candidate",
    "age": "age_exposure_n1_v1.json",
    "demand": "demand_cells_v1.json",
    "rescaled": "rescaled_demand_2024_v1.json",
    "baseline": "baseline_access_v1.json",
}
CONTEXT_FILES = {"context": "context_inputs.json", "facility_table": "planning_facilities.json",
                 "join_log": "grade_join_log.json", "receipt": "receipt.json"}

CONFIDENCE_BASIS = (
    "Administrative boundaries valid on 2022-01-22, OpenStreetMap roads and hospitals retrieved on 2026-07-10 and "
    "WorldPop modelled residents, none checked on the ground. Travel times are modelled class speeds on an undirected "
    "graph. The rules are those of the case protocol and of protocols v1a and v1b; the build has not been reviewed."
)
COMMON_ASSUMPTIONS = [
    "The 35 units are the 2022 COD-AB tha_admin3 polygons of districts TH5501, TH5514 and TH5507, copied unchanged.",
    "The routing geometry is the area the N1 context may route through; it is not a flood extent. Roads and "
    "hospitals outside it are not seen, even where a route would leave and re-enter it.",
    "OpenStreetMap was retrieved on 2026-07-10, about a year after the event of July and August 2025; roads and "
    "hospitals mapped or changed in between are taken as they stood in July 2026.",
    "WorldPop 2020 counts are modelled residents of 2020, not event-year counts and not observed evacuation demand.",
    "Nothing here is an observation of a flood. No flood layer is read and no flood flag is computed.",
]
CREDITS = [
    "Roads and hospitals (c) OpenStreetMap contributors, ODbL 1.0, via Geofabrik.",
    "Residents: WorldPop (www.worldpop.org), University of Southampton, Thailand 100 m 2020, CC BY 4.0. Modelled, "
    "not observed.",
    "Age counts: WorldPop Global2 R2025A v1, 2024, 1 km constrained age counts, CC BY 4.0. Modelled, not observed.",
    "Boundaries: OCHA / HDX Thailand COD-AB (tha_admin3, tha_admin0), valid on 2022-01-22.",
]


class FrameBuildError(RuntimeError):
    """Raised when an input is not the file the records name, or a stage would break a rule of the case."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def utc_now() -> str:
    """Return the current UTC time to the second, as the records write it."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file as lowercase hex."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def label(path: Path, external: Path) -> str:
    """Name a path without a machine prefix: relative to the repository or under the external data placeholder."""

    resolved = Path(path).resolve()
    for base, prefix in ((ROOT.resolve(), None), (external.resolve(), EXTERNAL_LABEL)):
        try:
            relative = resolved.relative_to(base).as_posix()
        except ValueError:
            continue
        return relative if prefix is None else f"{prefix}/{relative}"
    return Path(path).name


def refuse_sealed(path: Path) -> None:
    """Refuse any path inside the sealed reference folder of the case: this lane never opens it."""

    if SEALED_FOLDER in {part.lower() for part in Path(path).resolve().parts}:
        raise FrameBuildError("the sealed reference folder of the case is never opened by this script")


def load_script(name: str) -> Any:
    """Load a script of ``scripts/`` as a module once, registered by name (its dataclasses look the name up)."""

    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise FrameBuildError(f"scripts/{name}.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> Any:
    """Read a UTF-8 JSON file."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_bytes(path: Path, data: bytes) -> str:
    """Write bytes (LF already) and return their SHA-256."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def record_head(schema: str, generated_at_utc: str, source_timestamp: str, assumptions: Sequence[str],
                **extra: Any) -> dict[str, Any]:
    """The fields every record of the case carries, first in the file."""

    return {
        "schema": schema,
        "case_id": nan_frame.CASE_ID,
        "generated_at_utc": generated_at_utc,
        "source_timestamp": source_timestamp,
        **extra,
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "official_warning": False,
        "operational_status": "non_operational",
        "assumptions": list(assumptions),
    }


def recorded_sources() -> dict[str, dict[str, str]]:
    """The committed source manifest: SHA-256 and retrieval time of the national open-context files."""

    import csv

    with SOURCE_MANIFEST.open(encoding="utf-8-sig", newline="") as stream:
        return {row["source_group"]: row for row in csv.DictReader(stream)}


def check_source(path: Path, group: str) -> dict[str, str]:
    """Check one open-context file against the committed source manifest and return its record."""

    refuse_sealed(path)
    row = recorded_sources()[group]
    digest = sha256_file(path)
    if digest != row["sha256"]:
        raise FrameBuildError(f"{path.name} differs from outputs/open_context_data_file_manifest.csv")
    return {"file": path.name, "sha256": digest, "retrieved_at_utc": row["retrieved_at_utc"],
            "source_name": row["source_name"], "licence_status": row["license_status"]}


def protocols() -> dict[str, Any]:
    """Read the case protocol, the area grids and protocols v1a and v1b, with their SHA-256."""

    case = read_json(PROTOCOL_PATH)
    stated = nan_frame.check_protocol_frame(case)
    areas = read_json(AREAS_PATH)
    grid = areas["areas"]["nan_frame"]["grid"]
    if {key: int(grid[key]) for key in ("west", "north", "rows", "cols")} != {
            key: stated["grid"][key] for key in ("west", "north", "rows", "cols")}:
        raise FrameBuildError("outputs/nan_case/areas_v1.json and the case protocol state different frame grids")
    return {
        "case": case, "stated": stated, "v1a": read_json(PROTOCOL_V1A), "v1b": read_json(PROTOCOL_V1B),
        "hashes": {
            "nan_case_protocol_v1": sha256_file(PROTOCOL_PATH),
            "nan_case_areas_v1": sha256_file(AREAS_PATH),
            "planning_protocol_v1a": sha256_file(PROTOCOL_V1A),
            "planning_protocol_v1b": sha256_file(PROTOCOL_V1B),
        },
    }


def transformers() -> tuple[Any, Any, Any]:
    """Return WGS84 -> EPSG:32647 and back as geometry functions, and the point transformer."""

    from pyproj import Transformer
    from shapely.ops import transform

    forward = Transformer.from_crs(4326, nan_frame.GRID_EPSG, always_xy=True)
    backward = Transformer.from_crs(nan_frame.GRID_EPSG, 4326, always_xy=True)
    return (lambda geometry: transform(forward.transform, geometry),
            lambda geometry: transform(backward.transform, geometry), forward)


def library_versions() -> dict[str, str]:
    """The versions of the libraries that decide the numbers."""

    import numpy
    import pyproj
    import rasterio
    import shapely

    return {"python": platform.python_version(), "numpy": numpy.__version__, "shapely": shapely.__version__,
            "geos": ".".join(str(part) for part in shapely.geos_version), "pyproj": pyproj.__version__,
            "proj": pyproj.proj_version_str, "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__}


def implementation() -> dict[str, Any]:
    """The code of this run, by SHA-256."""

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    files = {
        "script_sha256": ROOT / "scripts" / "nan_case_frame.py",
        "nan_frame_module_sha256": ROOT / "src" / "floodguard" / "nan_frame.py",
        "planning_frames_module_sha256": ROOT / "src" / "floodguard" / "planning_frames.py",
        "planning_context_module_sha256": ROOT / "src" / "floodguard" / "planning_context.py",
        "evidence_context_module_sha256": ROOT / "src" / "floodguard" / "evidence_context.py",
        "grade_join_module_sha256": ROOT / "src" / "floodguard" / "grade_join.py",
        "access_diff_module_sha256": ROOT / "src" / "floodguard" / "access_diff.py",
        "age_exposure_module_sha256": ROOT / "src" / "floodguard" / "age_exposure.py",
        "demand_rescale_module_sha256": ROOT / "src" / "floodguard" / "demand_rescale.py",
        "build_planning_context_sha256": ROOT / "scripts" / "build_planning_context.py",
        "build_planning_frames_sha256": ROOT / "scripts" / "build_planning_frames.py",
        "build_access_diff_sha256": ROOT / "scripts" / "build_access_diff.py",
        "build_age_exposure_sha256": ROOT / "scripts" / "build_age_exposure.py",
        "build_ensemble_rescaled_demand_sha256": ROOT / "scripts" / "build_ensemble_rescaled_demand.py",
    }
    return {"base_commit": commit.stdout.strip() or None,
            "base_commit_note": "The commit the working tree was on; the files below are identified by their own "
                                "SHA-256, committed or not.",
            **{key: sha256_file(path) for key, path in files.items()}, "libraries": library_versions()}


# ---------------------------------------------------------------------------
# Stage 1: the frame
# ---------------------------------------------------------------------------


def _boundary_row(record: Any) -> dict[str, Any]:
    builder = load_script("build_planning_frames")
    return builder._row(record)  # the row shape of floodguard.planning_frames, with the Thai-name check


def read_frame_rows(boundaries: Path) -> tuple[list[dict[str, Any]], Any]:
    """Read the tha_admin3 rows of the three districts and the country polygon near them."""

    import pyogrio
    from shapely.geometry import box
    from shapely.ops import unary_union

    codes = ", ".join(f"'{code}'" for code, _name, _count in nan_frame.DISTRICTS)
    columns = ["adm3_pcode", "adm3_name", "adm3_name1", "lang1", "adm2_pcode", "adm2_name", "adm1_pcode", "valid_on"]
    table = pyogrio.read_dataframe(boundaries, layer="tha_admin3", columns=columns, where=f"adm2_pcode IN ({codes})")
    if table.crs is None or table.crs.to_epsg() != 4326:
        raise FrameBuildError("the boundary layer must be EPSG:4326")
    rows = [_boundary_row(record) for _, record in table.iterrows()]
    country = pyogrio.read_dataframe(boundaries, layer="tha_admin0", columns=["adm0_pcode"])
    if len(country) != 1:
        raise FrameBuildError("tha_admin0 must hold one feature")
    west, south, east, north = unary_union([row["geometry"] for row in rows]).bounds
    pad = COUNTRY_PAD_DEG
    near = country.geometry.iloc[0].intersection(box(west - pad, south - pad, east + pad, north + pad))
    return rows, near


def geojson_bytes(name: str, head: Mapping[str, Any], features: Sequence[Mapping[str, Any]]) -> bytes:
    """A FeatureCollection with the record fields in its header, one feature per line (planning_frames encoder)."""

    header = {"type": "FeatureCollection", "name": name,
              "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}, **head}
    return frames.encode_feature_collection(header, features)


def unit_raster(path: Path, units: Sequence[Mapping[str, Any]], table: Sequence[Mapping[str, Any]], grid: Mapping[str, int],
                to_metres: Any, generated_at_utc: str) -> dict[str, Any]:
    """Write the unit raster on the 20 m frame grid: each cell takes the unit that holds its centre.

    0 is a cell whose centre lies in no unit, 255 one whose centre lies in more than one; otherwise the
    ``raster_value`` of the unit. Tiled, DEFLATE-compressed GeoTIFF in EPSG:32647.
    """

    import numpy as np
    import rasterio
    from rasterio.enums import MergeAlg
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    shape = (grid["rows"], grid["cols"])
    transform = from_origin(grid["west"], grid["north"], nan_frame.GRID_CELL_M, nan_frame.GRID_CELL_M)
    values = {row["adm3_pcode"]: row["raster_value"] for row in table}
    metric = [(to_metres(row["geometry"]), values[row["adm3_pcode"]]) for row in units]
    count = rasterize([(geometry, 1) for geometry, _value in metric], out_shape=shape, transform=transform, fill=0,
                      all_touched=False, merge_alg=MergeAlg.add, dtype="uint8")
    value = rasterize(metric, out_shape=shape, transform=transform, fill=0, all_touched=False, dtype="uint8")
    out = np.where(count == 0, nan_frame.UNIT_RASTER_NONE, np.where(count > 1, nan_frame.UNIT_RASTER_SEVERAL, value))
    out = out.astype("uint8")
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {"driver": "GTiff", "height": shape[0], "width": shape[1], "count": 1, "dtype": "uint8",
               "crs": f"EPSG:{nan_frame.GRID_EPSG}", "transform": transform, "tiled": True, "blockxsize": 256,
               "blockysize": 256, "compress": "DEFLATE"}
    with rasterio.open(path, "w", **profile) as target:
        target.write(out, 1)
        target.update_tags(
            case_id=nan_frame.CASE_ID, generated_at_utc=generated_at_utc,
            what="Unit of each 20 m cell of the N1 frame grid: the tha_admin3 unit that holds the cell centre.",
            values="1-35: raster_value of the unit in outputs/nan_case/frame_v1.json; 0: centre in no unit; 255: centre "
                   "in more than one unit.",
            official_warning="false", operational_status="non_operational", confidence_class="low",
            source_timestamp="COD-AB tha_admin3 valid on 2022-01-22")
    counts = {int(key): int(number) for key, number in zip(*np.unique(out, return_counts=True))}
    return {"cells_by_value": {str(key): counts[key] for key in sorted(counts)},
            "cells_with_a_unit": int(sum(number for key, number in counts.items()
                                         if key not in (nan_frame.UNIT_RASTER_NONE, nan_frame.UNIT_RASTER_SEVERAL))),
            "cells_in_several_units": counts.get(nan_frame.UNIT_RASTER_SEVERAL, 0)}


def stage_frame(external: Path, work: Path) -> dict[str, Any]:
    """Build the units, the routing geometry, the hospitals inside, the grid check and the unit raster."""

    from shapely.geometry import Point, shape

    from floodguard.evidence_context import _extract_osm, _osm_facilities, _tags

    started = time.perf_counter()
    generated_at_utc = utc_now()
    found = protocols()
    boundaries, pbf = external / BOUNDARY_RELATIVE, external / OSM_RELATIVE
    sources = {"boundaries": check_source(boundaries, "hdx_cod_ab"), "osm": check_source(pbf, "osm_geofabrik")}
    v1b = found["v1b"]
    if sources["boundaries"]["sha256"] not in v1b["corridor_polygon"]["construction"]["boundary_source"]:
        raise FrameBuildError("the boundary file is not the one protocol v1b names")
    to_metres, to_wgs84, _forward = transformers()
    rows, country = read_frame_rows(boundaries)
    units = nan_frame.frame_units(rows)
    valid_on = sorted({row["valid_on"] for row in units})
    if len(valid_on) != 1:
        raise FrameBuildError("the units carry different valid_on dates")
    table = nan_frame.unit_table(units, to_metres)

    metric_units = [to_metres(row["geometry"]) for row in units]
    routing = frames.routing_geometry(metric_units, to_wgs84, country)
    routing_json = frames.geojson_geometry(routing)
    routing_sha256 = frames.geometry_sha256(routing_json)
    from shapely.ops import unary_union

    buffered_metric = unary_union(metric_units).buffer(frames.ROUTING_BUFFER_M, quad_segs=frames.BUFFER_QUAD_SEGS)
    routing_metric = to_metres(shape(routing_json))
    grid_check = {
        "rule": "The bounds of the units' union buffered by 3 km in EPSG:32647 (before the clip to Thailand), snapped "
                "outward to 20 m, against the frame grid of the case protocol (grid.frame) and of "
                "outputs/nan_case/areas_v1.json.",
        **nan_frame.compare_grid(nan_frame.snapped_grid(buffered_metric.bounds), found["stated"]["grid"]),
        "after_the_clip_to_thailand": nan_frame.compare_grid(nan_frame.snapped_grid(routing_metric.bounds),
                                                             found["stated"]["grid"]),
    }
    if not grid_check["same"]:
        raise FrameBuildError(f"the frame grid computed from the units differs from the protocol: {grid_check}")
    clip_km2 = round((buffered_metric.area - routing_metric.area) / 1e6, 6)

    head = record_head("floodguard.nan_case_units.v1", generated_at_utc, valid_on[0], COMMON_ASSUMPTIONS[:1],
                       source_timestamp_note="COD-AB valid_on date of the tambon boundaries.")
    unit_features = []
    for row, summary in zip(units, table):
        properties = {"frame_id": nan_frame.CASE_KEY, "case": nan_frame.CASE_ID,
                      **{field: row[field] for field in frames.UNIT_FIELDS}, "area_km2": summary["area_km2"],
                      "raster_value": summary["raster_value"], "boundary_source": "HDX Thailand COD-AB, layer tha_admin3",
                      "boundary_sha256": sources["boundaries"]["sha256"]}
        unit_features.append({"type": "Feature", "properties": properties,
                              "geometry": frames.geojson_geometry(row["geometry"])})
    units_bytes = geojson_bytes("n1_units", head, unit_features)
    routing_head = record_head("floodguard.nan_case_routing_geometry.v1", generated_at_utc, valid_on[0],
                               COMMON_ASSUMPTIONS[1:2],
                               source_timestamp_note="COD-AB valid_on date of the tambon boundaries.")
    routing_feature = {"type": "Feature", "properties": {
        "id": "n1_routing_geometry", "case": nan_frame.CASE_ID, "buffer_m": frames.ROUTING_BUFFER_M,
        "buffer_epsg": frames.METRIC_EPSG, "buffer_quad_segs": frames.BUFFER_QUAD_SEGS,
        "area_km2": round(routing_metric.area / 1e6, 6), "geometry_sha256": routing_sha256,
        "boundary_sha256": sources["boundaries"]["sha256"]}, "geometry": routing_json}
    routing_bytes = geojson_bytes("n1_routing_geometry", routing_head, [routing_feature])
    units_sha = write_bytes(work / FILES["units"], units_bytes)
    routing_file_sha = write_bytes(work / FILES["routing"], routing_bytes)

    # The hospitals a context build on this geometry sees: the bounding box of the geometry read back from its file.
    routing_from_file = shape(json.loads(routing_bytes.decode("ascii"))["features"][0]["geometry"])
    if frames.geometry_sha256(frames.geojson_geometry(routing_from_file)) != routing_sha256:
        raise FrameBuildError("the routing geometry does not read back with the same SHA-256")
    extract_dir = work / FILES["osm_extract"]
    extract_dir.mkdir(parents=True, exist_ok=True)
    _roads, features = _extract_osm(pbf, routing_from_file.bounds, extract_dir, sources["osm"]["sha256"],
                                    hashlib.sha256(routing_from_file.wkb).hexdigest())
    road_features = len(_roads["features"])
    del _roads
    english = {}
    for feature in features["features"]:
        tags = _tags(feature.get("properties", {}))
        if "hospital" in {tags.get("amenity"), tags.get("healthcare")} and tags.get("name:en"):
            english[frames.osm_identifier(tags, feature["geometry"]["type"])] = tags["name:en"]
    facilities = _osm_facilities(features, role_map={"hospital": "hospital"})
    hospitals = frames.hospitals_inside(facilities, routing_from_file, english)
    for row in hospitals:
        holders = nan_frame.containing_units(Point(row["longitude"], row["latitude"]), units)
        row["unit_holding_the_routing_point"] = holders[0] if len(holders) == 1 else None
        row["units_covering_the_routing_point"] = holders
    counts = frames.hospital_counts(hospitals)
    extract_receipt = read_json(extract_dir / "osm_extraction_receipt.json")

    raster = unit_raster(work / FILES["unit_raster"], units, table, found["stated"]["grid"], to_metres, generated_at_utc)
    raster["sha256"] = sha256_file(work / FILES["unit_raster"])

    record = {
        **record_head("floodguard.nan_case_frame_stage.v1", generated_at_utc, sources["osm"]["retrieved_at_utc"],
                      COMMON_ASSUMPTIONS,
                      source_timestamps={"boundaries_valid_on": valid_on[0],
                                         "osm_extract_retrieved_at_utc": sources["osm"]["retrieved_at_utc"]}),
        "protocol_sha256": found["hashes"],
        "inputs": sources,
        "units": table,
        "unit_counts_by_district": {code: sum(row["adm2_pcode"] == code for row in table)
                                    for code, _name, _count in nan_frame.DISTRICTS},
        "frame_area_km2": round(math.fsum(row["area_km2"] for row in table), 6),
        "units_file": {"path": label(work / FILES["units"], external), "sha256": units_sha},
        "routing_geometry": {
            "rule": "The union of the 35 units, buffered by 3,000 m in EPSG:32647 (16 segments per quarter circle), "
                    "projected to WGS84 and intersected with the COD-AB tha_admin0 polygon of Thailand "
                    "(floodguard.planning_frames.routing_geometry, the SE2 frame rule of protocol v1b).",
            "path": label(work / FILES["routing"], external), "file_sha256": routing_file_sha,
            "geometry_sha256": routing_sha256, "geometry_type": routing.geom_type,
            "area_km2": round(routing_metric.area / 1e6, 6),
            "area_removed_by_the_clip_to_thailand_km2": clip_km2,
            "bounds_wgs84": [round(value, 6) for value in routing_from_file.bounds],
        },
        "grid_check": grid_check,
        "hospitals": {
            "rule": "Every OSM object tagged amenity=hospital or healthcare=hospital whose routing point the routing "
                    "geometry covers. Object, identity and routing point as in "
                    "floodguard.evidence_context.build_context_inputs: a node is its point; a way or relation is its "
                    "representative point, or its one tagged entrance node when it has exactly one. The OSM extract is "
                    "the bounding box of the routing geometry (scripts/build_planning_frames.py).",
            "hospitals": hospitals,
            "counts": counts,
            "counts_note": "osm_objects counts OSM objects; distinct_named_hospitals is the unit of owner choice 22 "
                           "(decision log R12). Every object is a destination, named or not.",
            "osm_extract": {"path": label(extract_dir, external), "road_features_in_the_box": road_features,
                            **{key: value for key, value in extract_receipt.items() if key != "ogr_runtime"},
                            "ogr_runtime": extract_receipt.get("ogr_runtime")},
        },
        "unit_raster": {"path": label(work / FILES["unit_raster"], external), "grid": found["stated"]["grid"],
                        "rule": "Each 20 m cell takes the unit whose polygon holds its centre (GDAL rasterize, "
                                "all_touched false). 0: no unit; 255: more than one unit.", **raster},
        "timing_seconds": round(time.perf_counter() - started, 1),
    }
    write_bytes(work / FILES["frame_stage"], nan_frame.encode_record(record))
    return {"units": len(table), "hospitals": counts, "routing_geometry_sha256": routing_sha256,
            "grid_same": grid_check["same"], "clip_km2": clip_km2}


def load_frame_stage(work: Path, external: Path) -> dict[str, Any]:
    """Read the frame stage record and check the units and routing files it binds."""

    record = read_json(work / FILES["frame_stage"])
    for key, path in (("units_file", work / FILES["units"]), ("routing_geometry", work / FILES["routing"])):
        stated = record[key].get("sha256") or record[key].get("file_sha256")
        if sha256_file(path) != stated:
            raise FrameBuildError(f"{path.name} differs from the frame stage record")
    return record


def frame_units_from_file(work: Path) -> list[dict[str, Any]]:
    """The 35 units as rows with shapely geometries, read from the units file."""

    from shapely.geometry import shape

    document = read_json(work / FILES["units"])
    return [{**feature["properties"], "geometry": shape(feature["geometry"])} for feature in document["features"]]


def routing_from_file(work: Path, record: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    """The routing geometry and its GeoJSON, checked against the frame stage record."""

    from shapely.geometry import shape

    features = read_json(work / FILES["routing"])["features"]
    if len(features) != 1:
        raise FrameBuildError("the routing geometry file must hold one feature")
    geometry = features[0]["geometry"]
    if frames.geometry_sha256(geometry) != record["routing_geometry"]["geometry_sha256"]:
        raise FrameBuildError("the routing geometry differs from the geometry the frame stage recorded")
    return shape(geometry), geometry


# ---------------------------------------------------------------------------
# Stage 2: the planning context (plan task E4 rules)
# ---------------------------------------------------------------------------


def stage_context(external: Path, work: Path, dga: Path | None) -> dict[str, Any]:
    """Build the vehicle context with ``build_planning_context.build``, unchanged, and write its files."""

    import pyogrio
    from shapely.geometry import box
    from shapely.ops import unary_union

    bpc = load_script("build_planning_context")
    found = protocols()
    v1b = found["v1b"]
    frame = load_frame_stage(work, external)
    boundaries = external / BOUNDARY_RELATIVE
    check_source(boundaries, "hdx_cod_ab")
    units = frame_units_from_file(work)
    routing, routing_json = routing_from_file(work, frame)
    demand = unary_union([row["geometry"] for row in units])
    west, south, east, north = routing.bounds
    margin = BOUNDARY_WINDOW_MARGIN_DEG
    window = box(west - margin, south - margin, east + margin, north + margin)
    admin3 = pyogrio.read_dataframe(boundaries, layer="tha_admin3", columns=["adm3_pcode"], bbox=window.bounds)
    intersecting = admin3[admin3.geometry.intersects(routing)]
    reporting = unary_union(list(intersecting.geometry))
    hospital_ids = [row["facility_id"] for row in frame["hospitals"]["hospitals"]]
    description = {
        "case_id": nan_frame.CASE_SLUG,
        "title": "Nan N1: the 35 tambons of Mueang Nan, Phu Phiang and Wiang Sa, routed through their 3 km routing "
                 "geometry",
        "rules": {
            "aoi_geometry": "The union of the 35 units of the N1 frame (nan_case_protocol_v1.json, frame.units).",
            "routing_geometry": "The N1 routing geometry: the union of the units buffered by 3 km and clipped to "
                                "Thailand (the SE2 frame rule of protocol v1b), checked against its SHA-256 in the "
                                "frame stage record.",
            "reporting_geometry": "The union of the COD-AB tha_admin3 polygons that intersect the routing geometry.",
        },
        "routing_source": {"path": label(work / FILES["routing"], external),
                           "sha256": frame["routing_geometry"]["file_sha256"],
                           "geometry_sha256": frame["routing_geometry"]["geometry_sha256"],
                           "checked_against_protocol_v1b": False,
                           "checked_against": "the frame stage record of case N1 (frame_stage_v1.json), bound in "
                                              "outputs/nan_case/frame_v1.json"},
        "named_ways": [],
        "expected_hospital_ids": hospital_ids,
        "reporting_units_intersecting": int(len(intersecting)),
        "main_road_entry_definition": v1b["facility_sets"]["services"]["main_road_entry"]["definition"],
    }
    hashes = {"boundaries_sha256": frame["inputs"]["boundaries"]["sha256"],
              "routing_file_sha256": frame["routing_geometry"]["file_sha256"],
              "units_file_sha256": frame["units_file"]["sha256"]}
    case = bpc.Case(nan_frame.CASE_KEY, demand, routing, routing_json, reporting, description, hashes)
    dga_points: list[tuple[float, float]] = []
    dga_sha = None
    if dga is not None:
        refuse_sealed(dga)
        dga_points = [(float(row["geometry"]["coordinates"][0]), float(row["geometry"]["coordinates"][1]))
                      for row in read_json(dga)["features"]]
        dga_sha = sha256_file(dga)
    sources = bpc.Sources([], dga_points, [], {"ddpm_file_sha256": None, "dga_file_sha256": dga_sha,
                                               "reviewed_junctions_sha256": None})
    folder = work / FILES["context_dir"]
    paths = {"processed": folder, **{key: folder / name for key, name in CONTEXT_FILES.items()}}
    started_utc = utc_now()
    clock = time.perf_counter()
    scratch = Path(tempfile.mkdtemp(prefix="e4-n1-", dir=work))
    try:
        outputs = bpc.build(case, sources, v1b=v1b, context_root=external, scratch=scratch,
                            travel_mode="legacy_vehicle", record=False, paths=paths)
        peak = bpc.peak_memory_gib()
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(outputs["context_file"], paths["context"])
        paths["facility_table"].write_bytes(outputs["facility_table"])
        paths["join_log"].write_bytes(outputs["join_log"])
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    body = outputs["receipt_body"]
    run = {
        "generated_at_utc": body["generated_at_utc"],
        "run_started_at_utc": started_utc,
        "run_finished_at_utc": utc_now(),
        "wall_time_minutes": round((time.perf_counter() - clock) / 60, 2),
        "timing_seconds": outputs["timings"],
        "peak_working_set_gib": peak,
        "compute_window": {
            "declared": False,
            "note": "No compute window was declared: other lanes of the overnight run of 14-15 October 2026 ran on "
                    "the machine at the same time, so the terms of plan 5 item 1 (no other project job running) "
                    "could not be met. The build is a candidate in the words of plan task E4.",
        },
        "called_as": "build_planning_context.build (unchanged) from scripts/nan_case_frame.py, with a Case for N1 and "
                     "Sources holding no DDPM row and no reviewed junction",
        "machine": {"logical_processors": os.cpu_count(), "system": platform.system(), "release": platform.release(),
                    "python": platform.python_version()},
        "implementation": {**bpc._implementation(), "nan_case_frame_sha256": sha256_file(Path(__file__)),
                           "nan_frame_module_sha256": sha256_file(ROOT / "src" / "floodguard" / "nan_frame.py")},
        "protocol_sha256": found["hashes"],
        "processed_folder": label(folder, external),
        "note": bpc.RUN_NOTE,
    }
    from floodguard import planning_context

    paths["receipt"].write_bytes(planning_context.encode_json({**body, "run": run}))
    return {"canonical_sha256": outputs["context_canonical_sha256"], "edges": body["context"]["edges"],
            "hospitals": body["facilities"]["counts"]["osm_hospitals"],
            "main_road_entries": body["facilities"]["main_road_entries"],
            "baseline_no_route": body["baseline_no_route"]["with_grade_joins"],
            "frame_hospital_check_same": (body["frame_hospital_check"] or {}).get("same"),
            "wall_time_minutes": run["wall_time_minutes"]}


def load_context(work: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the retained context and its receipt; refuse a context whose canonical SHA-256 is not the receipt's."""

    from floodguard.evidence_context import _context_content_hash

    folder = work / FILES["context_dir"]
    receipt = json.loads((folder / CONTEXT_FILES["receipt"]).read_text(encoding="ascii"))
    context = json.loads((folder / CONTEXT_FILES["context"]).read_bytes().decode("utf-8"))
    expected = receipt["context"]["canonical_sha256"]
    if context.get("canonical_sha256") != expected or _context_content_hash(context) != expected:
        raise FrameBuildError("the retained context does not have the canonical SHA-256 its receipt names")
    return context, receipt


# ---------------------------------------------------------------------------
# Stage 3: the age counts (plan task E7 functions)
# ---------------------------------------------------------------------------


def stage_age(external: Path, work: Path, age_dir: Path) -> dict[str, Any]:
    """Compute the E7 unit rows of the 35 units with the functions and checks of ``build_age_exposure``."""

    from floodguard import age_exposure

    refuse_sealed(age_dir)
    started = time.perf_counter()
    generated_at_utc = utc_now()
    builder = load_script("build_age_exposure")
    anchors = builder.anchors_builder
    found = protocols()
    frame = load_frame_stage(work, external)
    binding_protocols, binding = builder.protocol_binding(DOCS)
    v1b = binding_protocols["v1b"]
    declared = v1b["national_vulnerability_anchors"]["inputs"]
    boundaries = external / BOUNDARY_RELATIVE
    manifest, paths, raster_hashes = anchors.check_age_sources(age_dir, declared["age_rasters"]["manifest_sha256"])
    boundaries_sha256 = anchors.sha256_file(boundaries)
    if boundaries_sha256 != declared["tambon_boundaries"]["sha256"]:
        raise FrameBuildError("the boundary file is not the one protocol v1b names")
    input_hashes = {"age_acquisition_manifest_sha256": declared["age_rasters"]["manifest_sha256"],
                    "age_rasters_sha256": dict(sorted(raster_hashes.items())),
                    "tambon_boundaries_sha256": boundaries_sha256}
    consistency = builder.anchor_consistency(v1b, ROOT, input_hashes)
    all_units, boundary_summary = anchors.read_units(boundaries)
    geometries = dict(all_units)
    wanted = [row["adm3_pcode"] for row in frame["units"]]
    missing = [unit for unit in wanted if unit not in geometries]
    if missing:
        raise FrameBuildError(f"units missing from the boundary layer: {missing}")
    names = builder.unit_names(boundaries, wanted)
    computed = age_exposure.age_exposure_frame([(unit, geometries[unit]) for unit in wanted], paths,
                                               layer_units=[geometry for _unit, geometry in all_units])
    units = [{"unit_id": row["unit_id"], "unit_name": names[row["unit_id"]],
              **{key: value for key, value in row.items() if key != "unit_id"}} for row in computed["units"]]
    anchors_block = v1b["national_vulnerability_anchors"]
    table = {
        **record_head("floodguard.age_exposure.v1", generated_at_utc, manifest["publication_date"],
                      builder.ASSUMPTIONS,
                      source_timestamps={"age_counts_year_represented": manifest["year_represented"],
                                         "age_counts_publication_date": manifest["publication_date"],
                                         "tambon_boundaries_valid_on": boundary_summary["valid_on"]}),
        "schema_version": builder.TABLE_SCHEMA_VERSION,
        "age_exposure_version": age_exposure.AGE_EXPOSURE_VERSION,
        "plan_task": "E7 functions applied to the frame of case N1 (age_exposure.age_exposure_frame, the readers and "
                     "checks of scripts/build_age_exposure.py and scripts/build_national_vulnerability_anchors.py)",
        "case_frame": nan_frame.CASE_SLUG,
        "case_frame_label": "Nan case N1: the 35 tha_admin3 units of TH5501, TH5514 and TH5507 "
                            "(nan_case_protocol_v1.json, frame.units)",
        "status": "unit_inputs",
        "status_note": "Inputs to the vulnerability component of case N1. The component, the FPPS and the A-E class "
                       "belong to the chain stage and are not here. Written outside Git by the frame lane; "
                       "outputs/nan_case/frame_v1.json binds it by SHA-256.",
        "computes": builder.COMPUTES,
        "protocol_sha256": {**binding["protocol_sha256"], **{key: value for key, value in found["hashes"].items()
                                                           if key.startswith("nan_case")}},
        "definition": "Dependent share: residents aged 0-14 plus residents aged 60 and over, over all residents "
                      "(protocol v1a scoring_frame.components.vulnerability_context_0_100), from the WorldPop 2024 "
                      "1 km age counts.",
        "age_groups": anchors_block["method"]["age_groups"],
        "allocation": age_exposure.ALLOCATION_STATEMENT,
        "allocation_in_protocol_v1b": anchors_block["method"]["allocation"],
        "caveat": anchors_block["caveat"],
        "range_rule": age_exposure.RANGE_STATEMENT,
        "age_cells_rule": age_exposure.AGE_CELLS_STATEMENT,
        "unsupported_area_rule": age_exposure.UNSUPPORTED_AREA_STATEMENT,
        "border_cells_rule": age_exposure.BORDER_CELLS_STATEMENT,
        "counts_unit": "modelled 2024 residents",
        "share_precision": "Shares and counts are written as unrounded 64-bit floats (E7-OP3).",
        "unit_count": len(units),
        "units": units,
        "border_cells": {"what": "The cells that lie partly outside every unit of the boundary layer, counted once "
                                 "over the units of the frame.", **computed["border_cells"]},
        "age_grid_reading": {"what": age_exposure.GRID_READING_STATEMENT, **computed["age_grid_reading"]},
        "open_points": builder.OPEN_POINTS,
        "not_computed": builder.NOT_COMPUTED[:-1],
        "input_hashes": input_hashes,
        "consistency_with_national_anchors": consistency,
        "inputs": {"age_acquisition_manifest": {"file": "acquisition_manifest.json",
                                                "sha256": input_hashes["age_acquisition_manifest_sha256"]},
                   "tambon_boundaries": {"file": boundaries.name, "layer": anchors.BOUNDARY_LAYER,
                                         "sha256": boundaries_sha256, "units_in_layer": boundary_summary["units"],
                                         "repaired_geometries": boundary_summary["repaired_geometries"]}},
        "limitations": [item for item in builder.LIMITATIONS if "national border" not in item]
        + ["Cells that lie partly outside every unit of the boundary layer may hold residents who reside outside "
           "the layer, and their age composition is that of the whole cell (cells_partly_outside_every_unit)."],
        "credits": CREDITS[2:4],
        "implementation": {"builder_functions_from": "scripts/build_age_exposure.py (unchanged)",
                           "build_age_exposure_sha256": sha256_file(ROOT / "scripts" / "build_age_exposure.py"),
                           "age_exposure_module_sha256": sha256_file(Path(str(age_exposure.__file__))),
                           "nan_case_frame_sha256": sha256_file(Path(__file__)),
                           "software": builder.software_versions()},
        "timing_seconds": round(time.perf_counter() - started, 1),
    }
    digest = write_bytes(work / FILES["age"], nan_frame.encode_record(table))
    with_share = sum(row.get("dependent_share") is not None for row in units)
    return {"units": len(units), "units_with_a_share": with_share, "sha256": digest,
            "anchor_consistency_all_same": consistency["all_same"]}


# ---------------------------------------------------------------------------
# Stage 4: the demand cells
# ---------------------------------------------------------------------------


def boundless_check(worldpop: Path, units: Sequence[Mapping[str, Any]], population: Sequence[Mapping[str, Any]]
                    ) -> dict[str, Any]:
    """Read the WorldPop 2020 window of the frame with ``boundless=True`` and count the positive cells whose centre
    the units' union covers, against the demand cells of the context."""

    import numpy as np
    import rasterio
    import shapely
    from rasterio.windows import Window
    from shapely.ops import unary_union

    union = unary_union([row["geometry"] for row in units])
    west, south, east, north = union.bounds
    with rasterio.open(worldpop) as source:
        fine = source.transform
        if fine.b != 0 or fine.d != 0 or source.crs.to_epsg() != 4326:
            raise FrameBuildError("the WorldPop 2020 raster is not a north-up grid in EPSG:4326")
        first_column = int(math.floor((west - fine.c) / fine.a)) - 1
        last_column = int(math.ceil((east - fine.c) / fine.a)) + 1
        first_row = int(math.floor((fine.f - north) / -fine.e)) - 1
        last_row = int(math.ceil((fine.f - south) / -fine.e)) + 1
        window = Window(first_column, first_row, last_column - first_column, last_row - first_row)
        counts = source.read(1, window=window, boundless=True, fill_value=0).astype("float64")
        nodata = source.nodata
        inside_raster = (first_row >= 0 and first_column >= 0 and last_row <= source.height and last_column <= source.width)
    invalid = ~np.isfinite(counts) | (counts < 0)
    if nodata is not None:
        invalid |= counts == nodata
    counts[invalid] = 0.0
    x = fine.c + (first_column + np.arange(counts.shape[1]) + 0.5) * fine.a
    y = fine.f + (first_row + np.arange(counts.shape[0]) + 0.5) * fine.e
    grid_x, grid_y = np.meshgrid(x, y)
    positive = counts > 0
    shapely.prepare(union)
    covered = np.zeros(counts.shape, dtype=bool)
    covered[positive] = shapely.covers(union, shapely.points(grid_x[positive], grid_y[positive]))
    cells = int(covered.sum())
    residents = math.fsum(counts[covered].tolist())
    context_residents = math.fsum(float(row["total_population"]) for row in population)
    return {
        "rule": "An independent read of tha_ppp_2020.tif over the bounds of the 35 units (one pixel more on each side), "
                "boundless=True with fill 0; a cell is counted when its count is positive and its centre is covered by "
                "the union of the units (shapely covers). The context's demand cells come from the E4 builder's own "
                "read (rasterio mask, cell centre inside, values above 0).",
        "window_inside_the_raster": inside_raster,
        "independent_read": {"cells": cells, "residents_2020": residents},
        "context_demand": {"cells": len(population), "residents_2020": context_residents},
        "cell_difference": len(population) - cells,
        "resident_difference": context_residents - residents,
    }


def stage_demand(external: Path, work: Path, age_dir: Path | None) -> dict[str, Any]:
    """Write every demand cell with its unit (cell-centre rule), its 20 m grid cell and its 2024-rescaled count."""

    from floodguard import access_diff

    started = time.perf_counter()
    generated_at_utc = utc_now()
    found = protocols()
    frame = load_frame_stage(work, external)
    units = frame_units_from_file(work)
    context, receipt = load_context(work)
    population = list(context["population"])
    assignment = access_diff.assign_cells(population, [(row["adm3_pcode"], row["geometry"]) for row in units])
    worldpop = external / WORLDPOP_RELATIVE
    worldpop_source = check_source(worldpop, "worldpop_population")
    if worldpop_source["sha256"] != context["input_hashes"]["worldpop"]:
        raise FrameBuildError("the WorldPop raster is not the one the context was built from")
    rescaled = kept = None
    rescale_record: dict[str, Any] | None = None
    rescale_status = "not_built"
    if age_dir is not None:
        refuse_sealed(age_dir)
        rescaler = load_script("build_ensemble_rescaled_demand")
        found_like = SimpleNamespace(graph=SimpleNamespace(population=population))
        registered_like = {"lineage_input_sha256": {"worldpop_2020_100m": worldpop_source["sha256"]}}
        rescaled, rescale_record = rescaler.rescaled_residents(found_like, external, age_dir, found["v1b"],
                                                               registered_like)
        kept = _kept_at_2020(population, external, age_dir, found["v1b"])
        if sum(kept.values()) != rescale_record["demand_cells_kept_at_2020"]:
            raise FrameBuildError("the cells kept at their 2020 count differ from the count the rescale builder records")
        rescale_status = "built"
    _to_metres, _to_wgs84, forward = transformers()
    rows = nan_frame.demand_rows(population, assignment, forward.transform, found["stated"]["grid"], rescaled, kept)
    unit_ids = [row["adm3_pcode"] for row in frame["units"]]
    summary = nan_frame.demand_summary(rows, unit_ids)
    check = boundless_check(worldpop, units, population)
    assignment_counts = {key: sum(1 for value in assignment.values() if value["unit_assignment"] == key)
                         for key in (access_diff.CELL_IN_ONE_UNIT, access_diff.CELL_IN_NO_UNIT,
                                     access_diff.CELL_IN_SEVERAL_UNITS)}
    record = {
        **record_head("floodguard.nan_case_demand_cells.v1", generated_at_utc,
                      "WorldPop 2020 (year represented); WorldPop Global2 R2025A 2024 1 km totals for the rescaled count",
                      [*COMMON_ASSUMPTIONS[3:4],
                       "A demand cell counts for the tha_admin3 unit whose polygon holds its centre "
                       "(floodguard.access_diff.assign_cells, the rule of tasks E5 and E8); a centre in no unit or in "
                       "more than one counts for no unit.",
                       *(demand_rescale_rules() if rescaled is not None else []),
                       "x_32647 and y_32647 are the cell centre in EPSG:32647; grid_row and grid_col are the 20 m cell "
                       "of the N1 frame grid that holds that centre."],
                      source_timestamps={"population_year_represented": 2020,
                                         "population_rescaled_to_year": 2024 if rescaled is not None else None}),
        "protocol_sha256": found["hashes"],
        "context": {"path": receipt["context"]["path"], "canonical_sha256": receipt["context"]["canonical_sha256"]},
        "frame_grid": found["stated"]["grid"],
        "worldpop_2020": worldpop_source,
        "assignment_counts": assignment_counts,
        "summary": summary,
        "boundless_check": check,
        "rescaled_2024": {"status": rescale_status, "record": rescale_record,
                          "how": "build_ensemble_rescaled_demand.rescaled_residents, unchanged, called with the N1 "
                                 "demand cells and the SHA-256 of tha_ppp_2020.tif from the committed source manifest "
                                 "(the one check it makes of the registered run)."},
        "columns": list(nan_frame.DEMAND_COLUMNS),
        "rows": rows,
        "credits": CREDITS,
        "timing_seconds": round(time.perf_counter() - started, 1),
    }
    digest = write_bytes(work / FILES["demand"], nan_frame.encode_record(record, indent=None))
    rescaled_sha = None
    if rescaled is not None:
        by_cell = {str(row[0]): float(row[4]) for row in rows}
        mapping = {
            **record_head("floodguard.nan_case_rescaled_demand.v1", generated_at_utc,
                          "WorldPop 2020 counts rescaled to the WorldPop Global2 R2025A 2024 1 km totals",
                          demand_rescale_rules()),
            "what": "The 2024-rescaled resident count of every demand cell of the N1 context, by population_id: the "
                    "second level of the population axis of the ensemble (protocol v1b ensemble_grid, owner choice 12).",
            "context": {"path": receipt["context"]["path"], "canonical_sha256": receipt["context"]["canonical_sha256"]},
            "demand_cells_file_sha256": digest,
            "record": rescale_record,
            "credits": CREDITS[1:3],
            "by_cell": by_cell,
        }
        rescaled_sha = write_bytes(work / FILES["rescaled"], nan_frame.encode_record(mapping, indent=None))
    return {"cells": summary["demand_cells"], "residents_2020": summary["residents_2020"], "rescaled_sha256": rescaled_sha,
            "residents_rescaled_2024": summary["residents_rescaled_2024"], "sha256": digest,
            "boundless_cell_difference": check["cell_difference"], "assignment": assignment_counts}


def demand_rescale_rules() -> list[str]:
    """The two rules of the rescale, as ``floodguard.demand_rescale`` states them."""

    from floodguard import demand_rescale

    return [f"Rescale to the 2024 totals: {rule}" for rule in demand_rescale.RULES]


def _kept_at_2020(population: Sequence[Mapping[str, Any]], external: Path, age_dir: Path,
                  v1b: Mapping[str, Any]) -> dict[str, bool]:
    """Mark the demand cells whose 1 km cell has no valid 2024 total (rule 2 keeps their 2020 count).

    The rescale builder returns the counts, not this mask; it is read again here from the same rasters with the
    same functions so that each cell carries it.
    """

    import numpy as np
    import rasterio
    from rasterio.windows import Window

    from floodguard import age_exposure, demand_rescale

    anchors = load_script("build_national_vulnerability_anchors")
    _manifest, paths, _hashes = anchors.check_age_sources(
        age_dir, v1b["national_vulnerability_anchors"]["inputs"]["age_rasters"]["manifest_sha256"])
    lon = np.array([float(row["longitude"]) for row in population])
    lat = np.array([float(row["latitude"]) for row in population])
    rasters = {band: rasterio.open(paths[band]) for band in age_exposure.AGE_BANDS}
    try:
        first = rasters[age_exposure.AGE_BANDS[0]]
        grid = first.transform
        geometry = {"west": grid.c, "north": grid.f, "cell_width": grid.a, "cell_height": -grid.e,
                    "rows": first.height, "columns": first.width}
        ids = demand_rescale.cell_index(lon, lat, **geometry)
        cell_rows, cell_columns = ids // first.width, ids % first.width
        row0, row1 = int(cell_rows.min()), int(cell_rows.max()) + 1
        column0, column1 = int(cell_columns.min()), int(cell_columns.max()) + 1
        _totals, _dependants, valid = age_exposure.read_grid_counts(
            rasters, Window(column0, row0, column1 - column0, row1 - row0))
    finally:
        for source in rasters.values():
            source.close()
    has_total = valid[cell_rows - row0, cell_columns - column0]
    return {str(row["population_id"]): not bool(flag) for row, flag in zip(population, has_total)}


# ---------------------------------------------------------------------------
# Stage 5: baseline access (no flood)
# ---------------------------------------------------------------------------


def read_demand(work: Path) -> dict[str, Any]:
    """Read the demand cells file into a list of dicts."""

    document = read_json(work / FILES["demand"])
    columns = document["columns"]
    return {"document": document, "cells": [dict(zip(columns, row)) for row in document["rows"]]}


def baseline_tables(found: Mapping[str, Any], frame: Mapping[str, Any], context: Mapping[str, Any],
                    receipt: Mapping[str, Any], work: Path) -> tuple[dict[str, Any], dict[str, Any], Any, list[Any]]:
    """Compute the baseline tables of both demands, the hospitals each unit reaches, and the check against the
    context's receipt, with the E5 runner's graph and trees (``build_access_diff.mode_graph`` and ``baseline_runs``)."""

    from floodguard import access_diff, planning_assessment

    e5 = load_script("build_access_diff")
    graph = e5.mode_graph(access_diff.VEHICLE, context)
    services = [rule for rule in access_diff.service_rules(found["v1a"], found["v1b"])
                if rule.publication_level == access_diff.PUBLIC_LEVEL and rule.mode == access_diff.VEHICLE]
    if sorted(rule.service for rule in services) != sorted(access_diff.ROUTE_SERVICES):
        raise FrameBuildError("the public vehicle services are not the hospital and the main-road entry")
    gaps = {rule.service: rule.access_gap_threshold_minutes for rule in services}
    if (gaps[access_diff.HOSPITAL], gaps[access_diff.MAIN_ROAD_ENTRY]) != (HOSPITAL_GAP_MINUTES, MAIN_ROAD_GAP_MINUTES):
        raise FrameBuildError("the protocols state other access-gap thresholds than 30 and 15 minutes")
    baseline = e5.baseline_runs(graph, services)
    demand = read_demand(work)
    if demand["document"]["context"]["canonical_sha256"] != receipt["context"]["canonical_sha256"]:
        raise FrameBuildError("the demand cells were made from another context")
    cells = demand["cells"]
    unit_ids = [row["adm3_pcode"] for row in frame["units"]]
    tables = {}
    for vintage, column in (("worldpop_2020", "residents_2020"), ("rescaled_2024", "residents_rescaled_2024")):
        if any(cell[column] is None for cell in cells):
            tables[vintage] = None
            continue
        rows = [{"population_id": cell["population_id"], "unit_id": cell["unit_id"], "residents": float(cell[column])}
                for cell in cells]
        table = access_diff.unit_rows(rows, unit_ids, services, baseline, baseline)
        tables[vintage] = nan_frame.baseline_table(table, hospital_gap_minutes=HOSPITAL_GAP_MINUTES,
                                                   main_road_gap_minutes=MAIN_ROAD_GAP_MINUTES,
                                                   no_route_share=planning_assessment.baseline_no_route_share)
    reach_cells = [{"unit_id": cell["unit_id"], "residents": float(cell["residents_2020"]), "node_id": cell["node_id"],
                    "snap_distance_m": cell["snap_distance_m"]} for cell in cells]
    reachable = planning_assessment.hospitals_reachable_at_baseline(reach_cells, graph.edges,
                                                                    graph.destinations[access_diff.HOSPITAL])
    for row in tables["worldpop_2020"]["units"]:
        row["hospitals_reachable_at_baseline"] = int(reachable.get(row["unit_id"], 0))
    whole = tables["worldpop_2020"]["whole_frame"]
    e4 = receipt["baseline_no_route"]["with_grade_joins"]
    e4_check = {
        "rule": "The whole-frame baseline of this stage against the baseline no-route figures of the context's own "
                "receipt (calculate_total_access with the grade joins), as task E5 checks its baseline run.",
        "connected_residents": {"this_stage": whole["residents_connected_to_the_graph"],
                                "context_receipt": e4["graph_connected_residents"]},
        "connected_residents_without_a_hospital_route": {
            "this_stage": whole["connected_residents_without_a_hospital_route"],
            "context_receipt": e4["connected_residents_without_a_route"]},
    }
    e4_check["same"] = all(abs(value["this_stage"] - value["context_receipt"]) <= 1e-6 * max(1.0, value["context_receipt"])
                           for key, value in e4_check.items() if isinstance(value, dict))
    return tables, e4_check, graph, services


def stage_baseline(external: Path, work: Path) -> dict[str, Any]:
    """Count baseline access per tambon with the E5 runner's graph and trees, for both demands."""

    started = time.perf_counter()
    generated_at_utc = utc_now()
    found = protocols()
    frame = load_frame_stage(work, external)
    context, receipt = load_context(work)
    tables, e4_check, graph, services = baseline_tables(found, frame, context, receipt, work)
    whole = tables["worldpop_2020"]["whole_frame"]
    record = {
        **record_head("floodguard.nan_case_baseline_access.v1", generated_at_utc,
                      receipt["source_timestamp"],
                      ["Baseline means no flood: the context's road graph with its grade joins (decision D13), "
                       "every edge open at its class speed.",
                       "Travel time is that of calculate_total_access: the fastest modelled route on the undirected "
                       "graph from the road node a WorldPop 2020 cell snaps to (within 250 m) to the nearest "
                       "destination, plus the connectors of the cell and the destination at 5 km/h "
                       "(build_access_diff.baseline_runs, unchanged).",
                       "A resident has access within a threshold when the modelled time is at most the threshold.",
                       "The baseline vehicle no-route share of a unit is its connected residents with no modelled route "
                       "to any hospital over its connected residents; 1 when nobody is connected "
                       "(floodguard.planning_assessment.baseline_no_route_share, condition C7).",
                       *COMMON_ASSUMPTIONS[2:4]],
                      source_timestamps=dict(receipt["source_timestamps"])),
        "protocol_sha256": found["hashes"],
        "context": {"path": receipt["context"]["path"], "canonical_sha256": receipt["context"]["canonical_sha256"]},
        "demand_file_sha256": sha256_file(work / FILES["demand"]),
        "services": [rule.as_record() for rule in services],
        "graph": graph.record,
        "check_against_the_context_receipt": e4_check,
        "baseline_by_demand": tables,
        "not_computed": ["any flooded run", "closure", "access loss", "access-gap component", "road-criticality "
                         "component", "any other component", "FPPS", "A-E class", "ensemble cell"],
        "credits": CREDITS[:2],
        "timing_seconds": round(time.perf_counter() - started, 1),
    }
    digest = write_bytes(work / FILES["baseline"], nan_frame.encode_record(record))
    return {"sha256": digest, "e4_check_same": e4_check["same"],
            "whole_frame": {key: whole[key] for key in ("residents", "residents_connected_to_the_graph",
                                                        "hospital_within_30_minutes_residents",
                                                        "main_road_within_15_minutes_residents",
                                                        "baseline_vehicle_no_route_share")}}


# ---------------------------------------------------------------------------
# Stage 6: the record in Git
# ---------------------------------------------------------------------------


DEVIATIONS = [
    {"id": "N1F-D1", "rule": "Plan task E4: the facilities supplied to build_context_inputs are the DDPM located "
                             "shelters (plan 3.1 P2).",
     "what_was_done": "No DDPM shelter was supplied, and none of the facility table's shelter rows exists. Shelters are "
                      "not part of the N1 score (the case protocol's ensemble keeps the public facility set only). "
                      "The road graph, the demand cells, the OSM hospitals and the main-road entries do not depend on "
                      "the supplied facilities; the context's canonical SHA-256 does."},
    {"id": "N1F-D2", "rule": "Plan task E4 at Mae Sai supplied the 20 reviewed junctions of AOI-01 "
                             "(osm_junction_review.json).",
     "what_was_done": "No reviewed junction was supplied: none exists for the Nan frame, and the 20 of AOI-01 lie "
                      "about 250 km away. The grade joins of decision D13 at 0 m are applied as at Mae Sai."},
    {"id": "N1F-D3", "rule": "Plan 5 item 1: a build of record runs serially in a declared compute window.",
     "what_was_done": "The context is a candidate build in the words of task E4: no compute window was declared, "
                      "because other lanes of the overnight run used the machine at the same time. Its receipt says so "
                      "(run_kind candidate). Nothing of the computation depends on it."},
    {"id": "N1F-D4", "rule": "Case SE2 committed its frame and routing GeoJSON under resources/planning_frames/ and "
                             "protocol v1b records their SHA-256 (corridor_polygon.se2_frame).",
     "what_was_done": "The N1 units and routing geometry stay in the work folder outside Git; this record names them by "
                      "SHA-256 (files_outside_git) and the context build checked the routing geometry against the frame "
                      "stage record, not against a signed protocol (routing_source.checked_against_protocol_v1b false)."},
    {"id": "N1F-D5", "rule": "Task E7 writes its age table to outputs/planning_v1/ with a registered receipt "
                             "(scripts/build_age_exposure.py, which knows the Mae Sai frame only).",
     "what_was_done": "The E7 rows of the 35 units were computed with the same functions and checks (the readers and "
                      "source checks of the national anchors, the anchor-consistency check, age_exposure_frame) and "
                      "written to the work folder in the E7 table format, without a separate receipt; the table carries "
                      "its input hashes, the consistency check and the code hashes itself."},
    {"id": "N1F-D6", "rule": "The 2024-rescaled demand is built by scripts/build_ensemble_rescaled_demand.py for a "
                             "registered E10 run.",
     "what_was_done": "Its function rescaled_residents was called unchanged with the N1 demand cells; in the place of the "
                      "registered run's receipt it was given the SHA-256 of tha_ppp_2020.tif from the committed source "
                      "manifest, which is the one value it reads from that receipt. Mae Sai's behaviour is unchanged "
                      "(no file of that builder was edited)."},
    {"id": "N1F-D7", "rule": "Task E5 tables hold counts of residents and no ratio of them (open point E5-OP8).",
     "what_was_done": "baseline_access.units gives, beside the counts, the baseline vehicle no-route share of each "
                      "tambon (condition C7 of confidence rule v1), because the lane was asked for it. It is a baseline "
                      "figure with no flood; it is not the access-gap or the road-criticality component."},
]
OPEN_POINTS = [
    {"id": "N1F-OP1", "point": "Hospital objects that are small facilities.",
     "what_this_file_does": "The SE2 rule takes every OSM object tagged amenity=hospital or healthcare=hospital, as for "
                            "Mueang Chiang Rai (where health-promoting hospitals and clinics tagged as hospitals were "
                            "kept). The list is in hospitals.hospitals; no object was removed."},
    {"id": "N1F-OP3", "point": "Which OSM object is Nan Hospital (test 4 of the case protocol).",
     "what_this_file_does": "The tags are listed as found. OSM way 315323384 is named 'Nan central hospital'. OSM ways "
                            "1464956018 and 315330559 carry one Thai name, that of the hospital of the Suriyaphong army "
                            "camp, and way 1464956018 also carries name:en 'Nan Hospital'. Both are kept as destinations "
                            "under the SE2 rule; the stage that runs test 4 says which object it takes."},
    {"id": "N1F-OP4", "point": "Plan row E4 asks for at least 4 hospitals in a context.",
     "what_this_file_does": "The SE2 rule gives 5 OSM hospital objects and 3 distinct named hospitals (owner choice 22), "
                            "so the E4 criterion hospitals_in_context_min is not met (context.plan_row_e4_acceptance). "
                            "The case protocol names the rule, not a minimum; nothing was added."},
    {"id": "N1F-OP5", "point": "Residents whose demand cell does not snap to the vehicle graph within 250 m.",
     "what_this_file_does": "About a quarter of the modelled 2020 residents of the frame (context.baseline_no_route_whole_"
                            "frame.residents_not_connected_to_the_graph) lie in such cells, mostly in rural tambons with few "
                            "mapped roads; they are in no numerator and no denominator of the access figures (E5-OP3). "
                            "The share per tambon is in baseline_access.units."},
    {"id": "N1F-OP6", "point": "Demand cells whose 1 km cell has no 2024 total.",
     "what_this_file_does": "They keep their 2020 count under the second rule of floodguard.demand_rescale "
                            "(demand.rescaled_2024.demand_cells_kept_at_2020). The 2024 product is constrained to mapped "
                            "settlement, so the two demands differ most where the 2020 product spreads residents over "
                            "unsettled land."},
    {"id": "N1F-OP2", "point": "Demand cells whose centre lies in no unit or in more than one.",
     "what_this_file_does": "They stay in the whole-frame figures and in no unit row, as in tasks E5 and E8 "
                            "(demand.assignment_counts)."},
]


def stage_record(external: Path, work: Path, replace_reason: str | None) -> dict[str, Any]:
    """Write outputs/nan_case/frame_v1.json from the stage files, binding each by SHA-256."""

    from floodguard import planning_context

    generated_at_utc = utc_now()
    found = protocols()
    frame = load_frame_stage(work, external)
    context, receipt = load_context(work)
    folder = work / FILES["context_dir"]
    for key in ("facility_table", "join_log"):
        stated = receipt["facilities"]["facility_table"]["sha256"] if key == "facility_table" else receipt["grade_joins"]["log_sha256"]
        if sha256_file(folder / CONTEXT_FILES[key]) != stated:
            raise FrameBuildError(f"the {key} differs from the SHA-256 its receipt names")
    age = read_json(work / FILES["age"])
    demand = read_json(work / FILES["demand"])
    baseline = read_json(work / FILES["baseline"])
    for document, name in ((demand, "demand"), (baseline, "baseline")):
        if document["context"]["canonical_sha256"] != receipt["context"]["canonical_sha256"]:
            raise FrameBuildError(f"the {name} file was made from another context")
    if baseline["demand_file_sha256"] != sha256_file(work / FILES["demand"]):
        raise FrameBuildError("the baseline file was made from other demand cells")
    if sha256_file(work / FILES["unit_raster"]) != frame["unit_raster"]["sha256"]:
        raise FrameBuildError("the unit raster differs from the frame stage record")

    entries = planning_context.main_road_entries(context)
    roads = nan_frame.main_road_summary(entries, context["edges"])
    if (roads["entries"], roads["node_ids_sha256"]) != (receipt["facilities"]["main_road_entries"],
                                                        receipt["facilities"]["main_road_entry_node_ids_sha256"]):
        raise FrameBuildError("the main-road entries of the context differ from those its receipt records")
    in_context = {row["facility_id"]: row for row in planning_context.hospital_destinations(context)}
    table_rows = {row["facility_id"]: row for row in json.loads(
        (folder / CONTEXT_FILES["facility_table"]).read_bytes().decode("ascii"))["services"]["hospital"]["rows"]}
    hospitals = []
    for row in frame["hospitals"]["hospitals"]:
        context_row = in_context.get(row["facility_id"], {})
        table_row = table_rows.get(row["facility_id"], {})
        hospitals.append({
            "facility_id": row["facility_id"],
            "osm_url": "https://www.openstreetmap.org/" + "/".join(row["facility_id"].split("-")[1:3]),
            "name": row["name"], **({"name_en": row["name_en"]} if "name_en" in row else {}),
            "routing_point_lon_lat": [row["longitude"], row["latitude"]],
            "source_geometry_type": row["source_geometry_type"], "geometry_role": row["geometry_role"],
            "unit_holding_the_routing_point": row["unit_holding_the_routing_point"],
            "destination_in_the_context": row["facility_id"] in in_context,
            "node_id": context_row.get("node_id"), "snap_distance_m": context_row.get("snap_distance_m"),
            "dga_records_within_150_m": table_row.get("dga_records_within_150_m"),
        })
    units_by_code = {row["adm3_pcode"]: row for row in frame["units"]}
    age_by_unit = {row["unit_id"]: row for row in age["units"]}
    baseline_2020 = baseline["baseline_by_demand"]["worldpop_2020"]
    baseline_2024 = baseline["baseline_by_demand"]["rescaled_2024"]
    by_2024 = {row["unit_id"]: row for row in baseline_2024["units"]} if baseline_2024 else {}
    baseline_rows = []
    for row in baseline_2020["units"]:
        entry = {"unit_id": row["unit_id"], "unit_name": units_by_code[row["unit_id"]]["adm3_name"]}
        for key in ("residents", "demand_cells", "residents_connected_to_the_graph",
                    "residents_not_connected_to_the_graph", "hospital_within_30_minutes_residents",
                    "main_road_within_15_minutes_residents", "connected_residents_without_a_hospital_route",
                    "baseline_vehicle_no_route_share", "residents_with_a_route_to_a_hospital_or_main_road",
                    "connected_residents_without_any_route", "hospitals_reachable_at_baseline"):
            value = row[key]
            entry[key] = round(value, 6) if isinstance(value, float) else value
        if row["unit_id"] in by_2024:
            other = by_2024[row["unit_id"]]
            entry["rescaled_2024"] = {key: round(other[key], 6) for key in (
                "residents", "residents_connected_to_the_graph", "hospital_within_30_minutes_residents",
                "main_road_within_15_minutes_residents", "connected_residents_without_a_hospital_route",
                "baseline_vehicle_no_route_share")}
        baseline_rows.append(entry)
    whole_2020 = baseline_2020["whole_frame"]

    def rounded(mapping: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
        return {key: round(mapping[key], 6) if isinstance(mapping[key], float) else mapping[key] for key in keys}

    whole_keys = ("residents", "demand_cells", "residents_connected_to_the_graph", "residents_not_connected_to_the_graph",
                  "hospital_within_30_minutes_residents", "main_road_within_15_minutes_residents",
                  "connected_residents_without_a_hospital_route", "baseline_vehicle_no_route_share",
                  "residents_with_a_route_to_a_hospital_or_main_road", "connected_residents_without_any_route")
    rescale = demand["rescaled_2024"]
    rescale_record = rescale["record"] or {}
    files = {
        "frame_stage_record": work / FILES["frame_stage"], "units": work / FILES["units"],
        "routing_geometry": work / FILES["routing"], "unit_raster": work / FILES["unit_raster"],
        "context": folder / CONTEXT_FILES["context"], "context_receipt": folder / CONTEXT_FILES["receipt"],
        "facility_table": folder / CONTEXT_FILES["facility_table"], "grade_join_log": folder / CONTEXT_FILES["join_log"],
        "age_counts": work / FILES["age"], "demand_cells": work / FILES["demand"],
        "baseline_access": work / FILES["baseline"],
    }
    if (work / FILES["rescaled"]).is_file():
        files["rescaled_demand_2024"] = work / FILES["rescaled"]
    supersedes = None
    if RECORD_PATH.exists():
        if not replace_reason:
            raise FrameBuildError("outputs/nan_case/frame_v1.json exists; pass --replace with --reason to replace it")
        earlier = read_json(RECORD_PATH)
        supersedes = {"sha256": sha256_file(RECORD_PATH), "generated_at_utc": earlier.get("generated_at_utc"),
                      "reason": replace_reason}
    edge_counts = receipt["edge_counts"]
    record = {
        **record_head(SCHEMA, generated_at_utc, frame["source_timestamp"], [
            *COMMON_ASSUMPTIONS,
            "Road times are fixed class speeds on an undirected graph; one-way rules, turn restrictions and road "
            "condition are not represented. A grade join shows that two ways end at one OSM coordinate (0 m), not "
            "that the transition can be driven.",
            "A main-road entry is a node of a trunk or primary edge of the context, links included (owner choice 8); "
            "grade-join connectors are not main roads.",
            "A demand cell counts for the unit that holds its centre; WorldPop 2020 counts are modelled residents.",
            "The 2024-rescaled demand is another model of where residents are counted, not four years of growth.",
        ], source_timestamps={**frame["source_timestamps"], "population_year_represented": 2020,
                              "age_counts_year_represented": age["source_timestamps"]["age_counts_year_represented"],
                              "age_counts_publication_date": age["source_timestamps"]["age_counts_publication_date"]},
            status="frame_and_context_inputs_of_case_n1",
            status_note="The frame of case N1 and the inputs the chain stage scores it with. It holds baseline (no "
                        "flood) counts per tambon and no flood figure, closure, access loss, component value, FPPS, "
                        "A-E class or ensemble. Planning guidance only: not an official warning and not real-time."),
        "protocol_sha256": found["hashes"],
        "protocol": {"path": PROTOCOL_PATH.relative_to(ROOT).as_posix(), "decision_log": "R51",
                     "frame_rules": found["stated"]["frame"]},
        "counts": {
            "units": len(frame["units"]), "units_by_district": frame["unit_counts_by_district"],
            "osm_hospital_objects": frame["hospitals"]["counts"]["osm_objects"],
            "distinct_named_hospitals": frame["hospitals"]["counts"]["distinct_named_hospitals"],
            "main_road_entries": roads["entries"], "context_edges": receipt["context"]["edges"],
            "grade_joins": receipt["grade_joins"]["join_count"],
            "demand_cells": demand["summary"]["demand_cells"],
            "residents_2020": round(demand["summary"]["residents_2020"], 3),
        },
        "units": [{**row, "dependent_share_2024": age_by_unit[row["adm3_pcode"]].get("dependent_share")}
                  for row in frame["units"]],
        "frame_area_km2": frame["frame_area_km2"],
        "routing_geometry": frame["routing_geometry"],
        "grid_check": frame["grid_check"],
        "hospitals": {"rule": frame["hospitals"]["rule"], "counts": frame["hospitals"]["counts"],
                      "counts_note": frame["hospitals"]["counts_note"], "hospitals": hospitals,
                      "context_check": {
                          "rule": "The hospital destinations of the context (eligible, routing point inside the routing "
                                  "context) against the frame list above.",
                          **{key: receipt["frame_hospital_check"][key] for key in ("missing", "extra", "same")}}},
        "main_road_destinations": {
            "definition": found["v1b"]["facility_sets"]["services"]["main_road_entry"]["definition"],
            "implemented_by": "floodguard.planning_context.main_road_entries: every node of a trunk or primary edge "
                              "of the context, links included; grade-join connectors are not main roads.",
            **{key: roads[key] for key in ("entries", "node_ids_sha256", "entries_by_road_class", "ways_by_road_class")},
            "osm_way_ids": [row["osm_way_id"] for row in roads["osm_ways"]],
            "rows_in": label(files["facility_table"], external) + " (services.main_road_entry.rows)",
        },
        "context": {
            "rules": "Plan task E4 (build_planning_context.build, unchanged): floodguard.evidence_context."
                     "build_context_inputs with the units' union as demand area, the N1 routing geometry, the union of "
                     "the tha_admin3 polygons that meet it as reporting geometry, travel mode legacy_vehicle; the grade "
                     "joins of floodguard.grade_join at 0 m.",
            "run_kind": receipt["run_kind"], "status": receipt["status"],
            "osm_extract": {"file": "thailand-latest.osm.pbf", "sha256": receipt["input_hashes"]["osm_pbf_sha256"],
                            "same_extract_as_the_mae_sai_e4_build_of_record": True,
                            "retrieved_at_utc": receipt["source_timestamps"]["osm_retrieved_at_utc"]},
            "canonical_sha256": receipt["context"]["canonical_sha256"],
            "edges": receipt["context"]["edges"], "road_nodes": receipt["context"]["road_nodes"],
            "connected_components": receipt["context"]["connected_components"],
            "segments_omitted_at_routing_boundary_or_degenerate":
                receipt["context"]["segments_omitted_at_routing_boundary_or_degenerate"],
            "edge_counts_by_road_class": edge_counts["by_road_class"],
            "bridge_yes_edges": edge_counts["bridge_yes_edges"], "tunnel_culvert_edges": edge_counts["tunnel_culvert_edges"],
            "edge_attributes_for_closure_rule_v1": "edge_id, from_node, to_node (node_coordinates in WGS84), length_m, "
                                                   "road_class, normal_minutes, osm_way_id, bridge, layer, tunnel; "
                                                   "culvert=* is not carried (owner choice 23).",
            "grade_joins": {key: receipt["grade_joins"][key] for key in ("join_count", "joins_sha256",
                                                                       "coincidence_tolerance_m", "log_sha256")},
            "population_cells": receipt["context"]["population_cells"],
            "population_snap_coverage_fraction": receipt["context"]["population_snap_coverage_fraction"],
            "baseline_no_route_whole_frame": receipt["baseline_no_route"]["with_grade_joins"],
            "plan_row_e4_acceptance": receipt["acceptance"]["criteria_met"],
        },
        "demand": {
            "rule": "WorldPop 2020 100 m cells with a positive count whose centre lies in the units' union (the E4 "
                    "builder's read); each counts for the unit that holds its centre (access_diff.assign_cells).",
            "assignment_counts": demand["assignment_counts"],
            "residents_2020": round(demand["summary"]["residents_2020"], 3),
            "cells_in_no_unit_or_several": demand["summary"]["cells_in_no_unit_or_several"],
            "boundless_check": demand["boundless_check"],
            "rescaled_2024": {
                "status": rescale["status"], "how": rescale["how"],
                "residents_rescaled_2024": round(demand["summary"]["residents_rescaled_2024"], 3)
                if demand["summary"]["residents_rescaled_2024"] is not None else None,
                **{key: rescale_record.get(key) for key in (
                    "ratio_lowest_median_highest", "demand_cells_kept_at_2020", "demand_residents_kept_at_2020",
                    "kept_at_2020_because_the_1km_cell_has_no_2024_total",
                    "residents_2024_in_1km_cells_with_no_2020_count")},
                "population_axis_of_the_ensemble": "kept: the rescaled demand was built for the frame"
                if rescale["status"] == "built" else "dropped: the rescaled demand was not built",
                "by_cell_file": label(work / FILES["rescaled"], external) if rescale["status"] == "built" else None,
            },
        },
        "age_counts": {
            "rule": "The E7 rows (age_exposure.age_exposure_frame) of the 35 units from the WorldPop 2024 1 km age "
                    "counts, allocated by projected-area fraction (reading DR-B04), with the national-anchor "
                    "consistency check of scripts/build_age_exposure.py.",
            "units_with_a_share": sum(row.get("dependent_share") is not None for row in age["units"]),
            "anchor_consistency_all_same": age["consistency_with_national_anchors"]["all_same"],
            "border_cells": {key: age["border_cells"].get(key) for key in (
                "distinct_cells", "residents_in_those_cells", "residents_of_those_cells_in_no_unit")},
        },
        "baseline_access": {
            "what": "Baseline (no flood) vehicle access per tambon on the context's graph with its grade joins, for "
                    "the chain stage to check its own baseline. Hospital within 30 minutes and main-road entry within "
                    "15 minutes are the access-gap thresholds of protocols v1a and v1b.",
            "check_against_the_context_receipt": baseline["check_against_the_context_receipt"],
            "whole_frame_worldpop_2020": rounded(whole_2020, whole_keys),
            "whole_frame_rescaled_2024": rounded(baseline_2024["whole_frame"], whole_keys) if baseline_2024 else None,
            "cells_in_no_unit": baseline_2020["cells_in_no_unit"],
            "units": baseline_rows,
        },
        "unit_raster": {key: frame["unit_raster"][key] for key in ("path", "grid", "rule", "cells_with_a_unit",
                                                                 "cells_in_several_units", "sha256")},
        "files_outside_git": {name: {"path": label(path, external), "sha256": sha256_file(path),
                                     "bytes": path.stat().st_size} for name, path in files.items()},
        "inputs_for_the_chain_stage": {
            "context": "files_outside_git.context (a vehicle context in the format of scripts/build_planning_context.py; "
                       "its canonical SHA-256 is context.canonical_sha256)",
            "routing_geometry": "files_outside_git.routing_geometry (one GeoJSON feature, EPSG:4326)",
            "age_table": "files_outside_git.age_counts (the format of the task E7 table)",
            "rescaled_population": "files_outside_git.rescaled_demand_2024 (population_id to residents under by_cell)",
            "unit_raster": "files_outside_git.unit_raster (the 20 m frame grid; values are units[].raster_value)",
            "demand_cells": "files_outside_git.demand_cells (columns and rows; unit, EPSG:32647 centre and 20 m grid cell "
                            "of every demand cell)",
            "baseline": "baseline_access here, and files_outside_git.baseline_access for every threshold",
        },
        "deviations": DEVIATIONS,
        "open_points": OPEN_POINTS,
        "not_computed": ["flood flag of the Nan frame", "flood extent", "closure", "access loss", "any component value",
                         "FPPS", "A-E class", "would-be class", "ensemble cell", "anything of case N2"],
        "rights": "Open context only: OpenStreetMap (ODbL 1.0), WorldPop (CC BY 4.0) and HDX COD-AB. No JAXA, GFM or "
                  "THEOS-2 file was opened by this lane.",
        "credits": CREDITS,
        "implementation": implementation(),
    }
    if supersedes:
        record["supersedes"] = supersedes
    digest = write_bytes(RECORD_PATH, nan_frame.encode_record(record))
    return {"path": RECORD_PATH.relative_to(ROOT).as_posix(), "sha256": digest}


def external_path(text: str, external: Path) -> Path:
    """Turn a path written under the external data placeholder into a path on this machine."""

    if not text.startswith(EXTERNAL_LABEL + "/"):
        raise FrameBuildError(f"{text} is not a path under the external data root")
    return external / text[len(EXTERNAL_LABEL) + 1:]


def stage_verify(external: Path, work: Path) -> dict[str, Any]:
    """Check outputs/nan_case/frame_v1.json against the files it binds, and compute again what is cheap to compute.

    Every file outside Git must have the SHA-256 the record names; the context its canonical SHA-256; the routing
    geometry, built again from the boundary file, its geometry SHA-256; the main-road entries their count and
    node-ID hash; and the baseline tables, computed again from the context and the demand cells, must equal the
    baseline file. Nothing is written.
    """

    from floodguard import planning_context

    record = read_json(RECORD_PATH)
    problems: list[str] = []
    checked: list[str] = []
    for name, entry in record["files_outside_git"].items():
        path = external_path(entry["path"], external)
        refuse_sealed(path)
        if not path.is_file():
            problems.append(f"{name}: the file is missing")
        elif sha256_file(path) != entry["sha256"]:
            problems.append(f"{name}: the file differs from the SHA-256 the record names")
        checked.append(f"file:{name}")
    context, receipt = load_context(work)
    if receipt["context"]["canonical_sha256"] != record["context"]["canonical_sha256"]:
        problems.append("context: the canonical SHA-256 differs from the record")
    checked.append("context_canonical_sha256_recomputed")

    to_metres, to_wgs84, _forward = transformers()
    rows, country = read_frame_rows(external / BOUNDARY_RELATIVE)
    units = nan_frame.frame_units(rows)
    routing = frames.routing_geometry([to_metres(row["geometry"]) for row in units], to_wgs84, country)
    if frames.geometry_sha256(frames.geojson_geometry(routing)) != record["routing_geometry"]["geometry_sha256"]:
        problems.append("routing geometry: a rebuild from the boundary file gives another geometry SHA-256")
    if [row["adm3_pcode"] for row in units] != [row["adm3_pcode"] for row in record["units"]]:
        problems.append("units: a rebuild from the boundary file gives other units")
    checked.append("routing_geometry_and_units_rebuilt")

    roads = nan_frame.main_road_summary(planning_context.main_road_entries(context), context["edges"])
    stated = record["main_road_destinations"]
    if (roads["entries"], roads["node_ids_sha256"]) != (stated["entries"], stated["node_ids_sha256"]):
        problems.append("main-road entries: the context gives another list")
    checked.append("main_road_entries_recomputed")

    found = protocols()
    frame = load_frame_stage(work, external)
    tables, _e4_check, _graph, _services = baseline_tables(found, frame, context, receipt, work)
    written = read_json(work / FILES["baseline"])["baseline_by_demand"]
    if json.loads(json.dumps(tables)) != written:
        problems.append("baseline: a recomputation from the context and the demand cells differs from the baseline file")
    checked.append("baseline_tables_recomputed")
    return {"verified": not problems, "checked": checked, "problems": problems}


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--external-root", type=Path, required=True, help="the external data root (outside Git)")
    parser.add_argument("--work-dir", type=Path, help="default: <external root>/proposal_execution/nan_case_v1/frame")
    parser.add_argument("--age-dir", type=Path, help="the folder of the 20 WorldPop 2024 1 km age rasters")
    parser.add_argument("--dga-facilities", type=Path, help="optional: the DGA health-facility GeoJSON")
    parser.add_argument("--stage", choices=(*STAGES, "all", CHECK_STAGE), default="all",
                        help="one stage, all six in order, or verify (check frame_v1.json against its files; writes nothing)")
    parser.add_argument("--replace", action="store_true", help="replace outputs/nan_case/frame_v1.json")
    parser.add_argument("--reason", default="", help="why frame_v1.json is replaced")
    args = parser.parse_args(argv)
    if args.work_dir is None:
        args.work_dir = args.external_root / WORK_RELATIVE
    for name in ("work_dir", "external_root"):
        resolved = getattr(args, name).resolve()
        if resolved == ROOT.resolve() or ROOT.resolve() in resolved.parents:
            parser.error(f"--{name.replace('_', '-')} must be outside the repository")
    if args.replace and not args.reason.strip():
        parser.error("--replace needs --reason")
    if args.stage in ("age", "all") and args.age_dir is None:
        parser.error("the age stage needs --age-dir")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Run one stage, or all of them in order, and print a JSON summary of each."""

    args = parse_args(argv)
    refuse_sealed(args.work_dir)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    if args.stage == CHECK_STAGE:
        result = stage_verify(args.external_root, args.work_dir)
        print(json.dumps({"stage": CHECK_STAGE, **result}))
        return 0 if result["verified"] else 1
    stages = STAGES if args.stage == "all" else (args.stage,)
    for stage in stages:
        clock = time.perf_counter()
        if stage == "frame":
            result = stage_frame(args.external_root, args.work_dir)
        elif stage == "context":
            result = stage_context(args.external_root, args.work_dir, args.dga_facilities)
        elif stage == "age":
            result = stage_age(args.external_root, args.work_dir, args.age_dir)
        elif stage == "demand":
            result = stage_demand(args.external_root, args.work_dir, args.age_dir)
        elif stage == "baseline":
            result = stage_baseline(args.external_root, args.work_dir)
        else:
            result = stage_record(args.external_root, args.work_dir, args.reason.strip() if args.replace else None)
        print(json.dumps({"stage": stage, "seconds": round(time.perf_counter() - clock, 1), **result}, default=str),
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
