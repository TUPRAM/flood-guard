"""THEOS-2 optical cross-check of the radar flood candidates (Sukhothai, 30 July 2025).

Plan: ``docs/proposal_execution/theos2_cross_check_plan_v1.md``. Two stages,
run in this order and committed one after the other:

``reference``  reads the THEOS-2 scene, builds the optical water raster with
               ``floodguard.theos2_cross_check`` and writes the reference
               record. It reads no radar data.
``compare``    refuses to run without that record. It fetches the Sentinel-1
               pair, applies the three radar candidates of plan tasks A2 and
               A4 unchanged, counts their agreement with the optical water and
               checks closure rule v1 against road centrelines on the image.

The THEOS-2 imagery and every raster stay outside Git, under ``--work-dir``.
Nothing here is an official warning, and no FPPS or A-E class is computed.

Examples::

    python scripts/build_theos2_radar_cross_check.py reference \
        --theos2 <downloads>/IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif \
        --work-dir <external-data-root>/theos2_cross_check/sukhothai_20250730_v1
    python scripts/build_theos2_radar_cross_check.py compare \
        --work-dir <external-data-root>/theos2_cross_check/sukhothai_20250730_v1 \
        --osm-pbf <external-data-root>/open_context/osm_geofabrik/thailand-latest.osm.pbf
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any
import urllib.request

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import access_diff, closure_rules, evidence_context  # noqa: E402
from floodguard import geoid_m1_review as review  # noqa: E402
from floodguard import radar_candidates as rc  # noqa: E402
from floodguard import sar_change_v2 as sar  # noqa: E402
from floodguard import theos2_cross_check as cc  # noqa: E402

PLAN = "docs/proposal_execution/theos2_cross_check_plan_v1.md"
OUTPUT_DIR = "outputs/theos2_cross_check"
REFERENCE_NAME = "sukhothai_20250730_reference_v1.json"
RESULT_NAME = "sukhothai_20250730_v1.json"
RECEIPT_NAME = "sukhothai_20250730_v1_receipt.json"
FIGURE_NAME = "sukhothai_20250730_v1_overview.png"

THEOS2_FILE = "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"
THEOS2_ACQUIRED_UTC = "2025-07-30T03:33:31Z"
THEOS2_BANDS = {"red": 1, "green": 2, "blue": 3, "nir": 4}
EPSG = 32647
FINE_M = 2.0
CELL_M = 10.0
READ_FACTOR = 4

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-1-rtc"
S1_PRE = ("S1A_IW_GRDH_1SDV_20250719T230832_20250719T230857_060159_rtc",)
S1_POST = (
    "S1A_IW_GRDH_1SDV_20250731T230828_20250731T230853_060334_rtc",
    "S1A_IW_GRDH_1SDV_20250731T230853_20250731T230918_060334_rtc",
)
WORLDCOVER_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
                  "ESA_WorldCover_10m_2021_v200_N15E099_Map.tif")
DEM_URLS = tuple(
    f"https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{lat}_00_E099_00_DEM/"
    f"Copernicus_DSM_COG_10_N{lat}_00_E099_00_DEM.tif" for lat in (16, 17)
)
PERMANENT_WATER_CLASS = 80
LAND_COVER_GROUPS = {"built_up": (50,), "cropland": (40,), "tree_cover": (10,)}
RASTER_MIN_POLYGON_CELLS = 5

# Set on the THEOS-2 image alone, before any radar data of this tile was read (plan section 4).
# The box marks thin cloud in the north-east corner of the chip that the brightness rule does not catch.
OPTICAL_CONFIG = cc.OpticalWaterConfig(unobservable_boxes=((0, 300, 1230, 1501),))

ASSUMPTIONS = [
    "The THEOS-2 water raster is a rule on four uncalibrated bands at 2 m, checked by eye; it was not validated on the ground.",
    "The radar after-image was acquired 43.6 hours after the THEOS-2 scene; water may have risen or fallen in between.",
    "The radar before-image of 19 July 2025 is assumed free of flood water; that was not verified.",
    "Terrain-corrected gamma0 is used where the Mae Sai runs used sigma0 (plan section 3, declared deviation).",
    "A road closure is modelled from a flood extent with closure rule v1; a flood intersection does not prove a closure.",
]
LIMITS = [
    "One scene of 9 square kilometres from one event: no method is selected, tuned or promoted on it.",
    "Every figure is agreement between two sensors at two times, never accuracy.",
    "It qualifies no candidate for Mae Sai; the T2 skill bar of protocol v1a is unchanged.",
    "Tree crowns and roofs hide a road surface and an OpenStreetMap centreline can lie metres off the road, so 'seen under water' is an under-count.",
    "Large roofs that pass the object rule can still be read as water in built-up cells.",
]


class BuildError(RuntimeError):
    """The stage cannot run on these inputs."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Bytes with LF line ends on every platform: receipts bind these files by SHA-256 (.gitattributes, D-41).
    path.write_bytes((json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


def superseded(path: Path, arguments: argparse.Namespace, same_keys: tuple[str, ...],
               new: dict[str, Any]) -> dict[str, Any] | None:
    """Describe the record a ``--replace`` run supersedes, and say whether its figures are the same."""

    if not path.exists():
        return None
    if not arguments.reason:
        raise BuildError("--replace needs --reason")
    old = json.loads(path.read_text(encoding="utf-8"))
    canonical = hashlib.sha256(json.dumps(old, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {
        "reason": arguments.reason,
        "generated_at_utc": old.get("generated_at_utc"),
        "canonical_json_sha256": canonical,
        "figures_same": {key: old.get(key) == new.get(key) for key in same_keys},
    }


def envelope(source_timestamp: str) -> dict[str, Any]:
    """The fields every FloodGuard output carries."""

    return {
        "generated_at_utc": now_utc(),
        "source_timestamp": source_timestamp,
        "confidence_class": "low",
        "confidence_basis": "One optical scene and one radar pair, 43.6 hours apart; no ground check.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "plan": {"path": PLAN, "sha256": sha256_file(ROOT / PLAN)},
    }


def lattice_grid(bounds: tuple[float, float, float, float]) -> tuple[list[rc.LatticeTile], float, float, int, int]:
    tiles = rc.lattice_tiles(bounds)
    west, east = min(t.west for t in tiles), max(t.east for t in tiles)
    south, north = min(t.south for t in tiles), max(t.north for t in tiles)
    return tiles, west, north, int(round((north - south) / CELL_M)), int(round((east - west) / CELL_M))


# ---------------------------------------------------------------------------
# Stage 1: the optical reference
# ---------------------------------------------------------------------------


def read_theos2_chip(path: Path) -> tuple[np.ndarray, tuple[float, float]]:
    """Read the scene at 2 m by averaging and return its valid rectangle with its upper-left corner."""

    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import Window

    with rasterio.open(path) as source:
        if source.crs is None or source.crs.to_epsg() != EPSG or abs(source.res[0] - 0.5) > 1e-9:
            raise BuildError("the THEOS-2 scene is not the 0.5 m EPSG:32647 ortho the plan names")
        height, width = source.height // READ_FACTOR, source.width // READ_FACTOR
        image = np.zeros((4, height, width), dtype="float32")
        seen = np.zeros((height, width), dtype=bool)
        for first in range(0, height, 512):
            last = min(height, first + 512)
            window = Window(0, first * READ_FACTOR, width * READ_FACTOR, (last - first) * READ_FACTOR)
            block = source.read(window=window, out_shape=(4, last - first, width),
                                resampling=Resampling.average, masked=True)
            image[:, first:last, :] = block.filled(0)
            seen[first:last, :] = ~np.ma.getmaskarray(block).any(axis=0)
        rows, columns = np.where(seen.any(axis=1))[0], np.where(seen.any(axis=0))[0]
        if rows.size == 0:
            raise BuildError("the THEOS-2 scene holds no valid pixel")
        r0, r1, c0, c1 = rows.min(), rows.max() + 1, columns.min(), columns.max() + 1
        if not seen[r0:r1, c0:c1].all():
            raise BuildError("the valid part of the scene is not a filled rectangle")
        west = source.transform.c + c0 * FINE_M
        north = source.transform.f - r0 * FINE_M
    return image[:, r0:r1, c0:c1], (float(west), float(north))


def aggregate_to_grid(water: np.ndarray, west: float, north: float, grid_west: float, grid_north: float,
                      rows: int, columns: int) -> tuple[np.ndarray, np.ndarray]:
    """Average the 2 m water raster onto the 10 m lattice: water share of observable pixels, and observable share."""

    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject

    source_transform = from_origin(west, north, FINE_M, FINE_M)
    target_transform = from_origin(grid_west, grid_north, CELL_M, CELL_M)
    crs = f"EPSG:{EPSG}"

    def average(values: np.ndarray) -> np.ndarray:
        target = np.zeros((rows, columns), dtype="float32")
        reproject(values.astype("float32"), target, src_transform=source_transform, src_crs=crs,
                  dst_transform=target_transform, dst_crs=crs, resampling=Resampling.average,
                  src_nodata=None, dst_nodata=None, init_dest_nodata=True)
        return target

    # Outside the chip the source has no pixel: the footprint share says how much of a cell the chip covers.
    footprint = average(np.ones(water.shape, dtype="float32"))
    observable = average((water != cc.WATER_UNOBSERVABLE).astype("float32"))
    wet = average((water == cc.WATER_YES).astype("float32"))
    with np.errstate(divide="ignore", invalid="ignore"):
        water_share = np.where(observable > 0, wet / observable, np.nan)
        observable_share = np.where(footprint >= 0.999, observable, 0.0)
    return water_share.astype("float32"), observable_share.astype("float32")


def stage_reference(arguments: argparse.Namespace) -> None:
    import rasterio
    from rasterio.transform import from_origin

    work = Path(arguments.work_dir)
    output = ROOT / OUTPUT_DIR / REFERENCE_NAME
    if output.exists() and not arguments.replace:
        raise BuildError(f"{output} exists; a second reference needs --replace and a reason in the plan")
    scene = Path(arguments.theos2)
    if scene.name != THEOS2_FILE:
        raise BuildError(f"the plan names {THEOS2_FILE}")
    scene_sha = sha256_file(scene)
    with (ROOT / "outputs/theos2_selected_file_manifest.csv").open(encoding="utf-8", newline="") as handle:
        recorded = {row["file_name"]: row["sha256"] for row in csv.DictReader(handle)}
    if recorded.get(THEOS2_FILE) != scene_sha:
        raise BuildError("the scene does not have the SHA-256 the selected-file manifest records")

    chip, (west, north) = read_theos2_chip(scene)
    red, green, blue, nir = (chip[THEOS2_BANDS[name] - 1] for name in ("red", "green", "blue", "nir"))
    water, summary = cc.optical_water(red, green, blue, nir, nir > 0, OPTICAL_CONFIG)
    height, width = water.shape
    bounds = (west, north - height * FINE_M, west + width * FINE_M, north)
    _, grid_west, grid_north, rows, columns = lattice_grid(bounds)
    water_share, observable_share = aggregate_to_grid(water, west, north, grid_west, grid_north, rows, columns)
    cells = cc.reference_cells(water_share, observable_share)

    work.mkdir(parents=True, exist_ok=True)
    np.save(work / "theos2_chip_2m.npy", chip)
    profile = {"driver": "GTiff", "crs": f"EPSG:{EPSG}", "compress": "deflate"}
    with rasterio.open(work / "theos2_water_2m.tif", "w", height=height, width=width, count=1, dtype="uint8",
                       nodata=cc.WATER_UNOBSERVABLE, transform=from_origin(west, north, FINE_M, FINE_M), **profile) as target:
        target.write(water, 1)
    with rasterio.open(work / "theos2_reference_10m.tif", "w", height=rows, width=columns, count=2, dtype="float32",
                       nodata=float("nan"), transform=from_origin(grid_west, grid_north, CELL_M, CELL_M), **profile) as target:
        target.write(water_share, 1)
        target.write(observable_share, 2)
        target.set_band_description(1, "water share of observable 2 m pixels")
        target.set_band_description(2, "observable share of 2 m pixels (0 outside the chip)")

    cell_km2 = CELL_M * CELL_M / 1e6
    record = {
        "schema": "floodguard.theos2_cross_check.reference.v1",
        **envelope(THEOS2_ACQUIRED_UTC),
        "stage": "reference: built from the THEOS-2 image alone, before any radar candidate or change image of this tile was computed",
        "radar_reads_before_this_stage": "One coverage check read the VH windows of five Sentinel-1 passes over the chip and its lattice tiles and printed, per pass, the share of valid cells and the median backscatter. No candidate, no change image and no comparison was computed.",
        "theos2_scene": {
            "file_name": THEOS2_FILE, "sha256": scene_sha, "acquired_utc": THEOS2_ACQUIRED_UTC,
            "band_order": THEOS2_BANDS, "native_pixel_m": 0.5, "read_at_m": FINE_M,
            "read_rule": "mean of 4 by 4 native pixels",
            "valid_rectangle_epsg32647": {"west": bounds[0], "south": bounds[1], "east": bounds[2], "north": bounds[3]},
            "valid_area_km2": round(height * width * FINE_M * FINE_M / 1e6, 4),
            "note": "The file is a 15.9 km canvas of no-data around a 3 km chip. The footprint and the area in "
                    "outputs/theos2_local_metadata_manifest.csv describe the canvas, not the imagery.",
            "licence": "THEOS-2 sample imagery provided by GISTDA for GeoHackathon 2026 (docs/theos2_usage_terms_log.md). "
                       "The imagery stays outside Git; derived figures are shared.",
        },
        "optical_water_rule": summary,
        "rule_replaced_once_at_this_stage": {
            "plan_rule": "two-class Otsu on NDWI",
            "applied_rule": "upper threshold of a three-class Otsu split on NDWI",
            "why": "The NDWI histogram has three populations (vegetation; roads, roofs and bare ground; water). The "
                   "two-class threshold splits vegetation from everything else and marks roads, roofs and bare ground "
                   "as water, which is visibly wrong on the image.",
            "two_class_value": summary["ndwi_two_class_otsu"],
            "three_class_values": summary["ndwi_three_class_otsu"],
        },
        "additions_set_by_eye_on_the_image": [
            "Bright objects at least 22 m wide are unobservable, with a 20 m margin: cloud, large bright roofs, bare bright ground.",
            "One rectangle in the north-east corner is unobservable: thin cloud the brightness rule does not catch.",
            "Connected water objects smaller than 250 pixels of 2 m (1,000 square metres) are dropped: mostly roofs.",
        ],
        "grid_10m": {"epsg": EPSG, "west": grid_west, "north": grid_north, "rows": rows, "columns": columns,
                     "cell_m": CELL_M, "lattice": "GEOID tile lattice of 10.24 km, as at Mae Sai"},
        "cells_10m": {
            "rule": "compared at an observable share of 0.9 or more; wet at a water share of 0.5 or more",
            "compared": int(cells["compared"].sum()), "wet": int(cells["wet"].sum()), "dry": int(cells["dry"].sum()),
            "mixed_water_share_between_0.1_and_0.9": int(cells["mixed"].sum()),
            "compared_km2": round(int(cells["compared"].sum()) * cell_km2, 4),
            "wet_km2": round(int(cells["wet"].sum()) * cell_km2, 4),
        },
        "rasters_outside_git": {
            name: {"sha256": sha256_file(work / name)} for name in ("theos2_water_2m.tif", "theos2_reference_10m.tif")
        },
        "assumptions": ASSUMPTIONS[:1],
        "limits": LIMITS[3:],
    }
    previous = superseded(output, arguments, ("optical_water_rule", "cells_10m", "rasters_outside_git"), record)
    if previous is not None:
        record["supersedes"] = previous
    write_json(output, record)
    print(json.dumps({key: record.get(key) for key in ("optical_water_rule", "cells_10m", "supersedes")}, indent=1))


# ---------------------------------------------------------------------------
# Stage 2: the radar candidates and the comparison
# ---------------------------------------------------------------------------


def fetch_json(url: str, tries: int = 6) -> dict[str, Any]:
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as response:
                return json.load(response)
        except Exception:  # noqa: BLE001 - the catalogue times out now and then; retried, then raised
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise BuildError("unreachable")


def fetch_radar(work: Path, grid: tuple[float, float, int, int]) -> dict[str, Any]:
    """Read the lattice window of the Sentinel-1 pair and cache it as two GeoTIFFs (VV, VH; linear gamma0)."""

    import rasterio
    from rasterio.transform import from_origin
    from rasterio.windows import from_bounds

    west, north, rows, columns = grid
    bounds = (west, north - rows * CELL_M, west + columns * CELL_M, north)
    record: dict[str, Any] = {}
    token: str | None = None
    for role, items in (("pre", S1_PRE), ("post", S1_POST)):
        path = work / f"s1_{role}_gamma0.tif"
        meta_path = work / f"s1_{role}_gamma0.json"
        if not (path.exists() and meta_path.exists()):
            token = token or fetch_json(SAS)["token"]
            image = np.full((2, rows, columns), np.nan, dtype="float32")
            sources = []
            for item_id in items:
                item = fetch_json(STAC + item_id)
                entry = {"item": item_id, "datetime": item["properties"]["datetime"],
                         "platform": item["properties"].get("platform"),
                         "relative_orbit": item["properties"].get("sat:relative_orbit"),
                         "orbit_state": item["properties"].get("sat:orbit_state"), "assets": {}}
                for band, name in enumerate(("vv", "vh")):
                    href = item["assets"][name]["href"]
                    entry["assets"][name] = href
                    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="6",
                                      GDAL_HTTP_RETRY_DELAY="4"):
                        with rasterio.open(f"{href}?{token}") as source:
                            if source.crs.to_epsg() != EPSG or source.res != (CELL_M, CELL_M):
                                raise BuildError(f"{item_id} is not on the 10 m EPSG:{EPSG} grid")
                            window = from_bounds(*bounds, transform=source.transform)
                            if any(abs(value - round(value)) > 1e-6 for value in (window.col_off, window.row_off)):
                                raise BuildError(f"{item_id} is not aligned to the lattice")
                            block = source.read(1, window=window, boundless=True, fill_value=np.nan).astype("float32")
                    block[~(np.isfinite(block) & (block > 0))] = np.nan
                    image[band] = np.where(np.isfinite(image[band]), image[band], block)
                sources.append(entry)
            with rasterio.open(path, "w", driver="GTiff", height=rows, width=columns, count=2, dtype="float32",
                               nodata=float("nan"), crs=f"EPSG:{EPSG}", compress="deflate",
                               transform=from_origin(west, north, CELL_M, CELL_M)) as target:
                target.write(image)
                target.set_band_description(1, "gamma0 VV, linear")
                target.set_band_description(2, "gamma0 VH, linear")
            write_json(meta_path, {"fetched_at_utc": now_utc(), "sources": sources,
                                   "mosaic_rule": "first valid value in the listed order"})
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        record[role] = {**meta, "window_file": path.name, "window_sha256": sha256_file(path)}
    return record


def warp_remote(url: str, work: Path, name: str, grid: tuple[float, float, int, int], *, nearest: bool,
                dtype: str, fill: float) -> np.ndarray:
    """Warp a remote open raster onto the lattice grid and cache the result."""

    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject

    west, north, rows, columns = grid
    path = work / name
    if path.exists():
        with rasterio.open(path) as cached:
            return cached.read(1)
    target = np.full((rows, columns), fill, dtype=dtype)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="6", GDAL_HTTP_RETRY_DELAY="4"):
        with rasterio.open(url) as source:
            reproject(rasterio.band(source, 1), target, dst_transform=from_origin(west, north, CELL_M, CELL_M),
                      dst_crs=f"EPSG:{EPSG}", resampling=Resampling.nearest if nearest else Resampling.bilinear,
                      dst_nodata=fill, init_dest_nodata=True)
    with rasterio.open(path, "w", driver="GTiff", height=rows, width=columns, count=1, dtype=dtype, nodata=fill,
                       crs=f"EPSG:{EPSG}", compress="deflate",
                       transform=from_origin(west, north, CELL_M, CELL_M)) as cached:
        cached.write(target, 1)
    return target


def read_roads(pbf: Path, bounds_lonlat: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Road edges inside the bounds: one edge per pair of consecutive vertices of an OpenStreetMap way."""

    import pyogrio

    frame = pyogrio.read_dataframe(pbf, layer="lines", bbox=bounds_lonlat, columns=["osm_id", "highway", "other_tags"])
    edges: list[dict[str, Any]] = []
    for osm_id, highway, tags, geometry in zip(frame["osm_id"], frame["highway"], frame["other_tags"], frame.geometry):
        road_class = evidence_context.ROAD_CLASSES.get(highway) if isinstance(highway, str) else None
        if road_class is None or geometry is None or geometry.geom_type != "LineString":
            continue
        tags = tags if isinstance(tags, str) else ""
        coordinates = list(geometry.coords)
        for index in range(len(coordinates) - 1):
            edges.append({
                "edge_id": f"w{osm_id}_{index:04d}", "from_node": f"w{osm_id}_n{index}", "to_node": f"w{osm_id}_n{index + 1}",
                "road_class": road_class, "highway": highway,
                "bridge": "yes" if '"bridge"=>"yes"' in tags else None,
                "tunnel": "culvert" if '"tunnel"=>"culvert"' in tags else None,
                "start": coordinates[index][:2], "end": coordinates[index + 1][:2],
            })
    return edges


def candidate_extent(candidate: np.ndarray, grid: tuple[float, float, int, int]) -> Any:
    """Polygons of the candidate cells in WGS84; polygons of fewer than five cells are dropped (protocol v1b)."""

    import shapely
    from pyproj import Transformer
    from rasterio import features
    from rasterio.transform import from_origin
    from shapely.geometry import shape
    from shapely.ops import transform, unary_union

    west, north, _, _ = grid
    mask = candidate == cc.CANDIDATE_YES
    shapes = [shape(geometry) for geometry, value in features.shapes(
        mask.astype("uint8"), mask=mask, transform=from_origin(west, north, CELL_M, CELL_M)) if value == 1]
    kept = [polygon for polygon in shapes if polygon.area >= RASTER_MIN_POLYGON_CELLS * CELL_M * CELL_M - 1e-6]
    if not kept:
        return shapely.Polygon()
    union = shapely.make_valid(unary_union(kept))
    return transform(Transformer.from_crs(EPSG, 4326, always_xy=True).transform, union)


def write_figure(path: Path, chip: np.ndarray, water: np.ndarray, layers: dict[str, np.ndarray],
                 chip_origin: tuple[float, float], grid: tuple[float, float, int, int]) -> None:
    """One overview: the image, the optical water, and each candidate over the optical water."""

    from PIL import Image, ImageDraw

    def stretch(band: np.ndarray) -> np.ndarray:
        low, high = np.percentile(band, [1, 99.5])
        return np.clip((band - low) / (high - low), 0, 1) ** 0.8

    step = 3  # 6 m per figure pixel: an overview, not the imagery
    rgb = np.dstack([stretch(chip[THEOS2_BANDS[name] - 1]) for name in ("red", "green", "blue")])[::step, ::step]
    fine = water[::step, ::step]
    size = rgb.shape[0]
    west, north = chip_origin
    grid_west, grid_north, _, _ = grid
    columns = ((west + (np.arange(size) * step + 0.5) * FINE_M - grid_west) / CELL_M).astype(int)
    rows = ((grid_north - (north - (np.arange(size) * step + 0.5) * FINE_M)) / CELL_M).astype(int)

    def panel(base: np.ndarray, title: str) -> Image.Image:
        image = Image.fromarray((np.clip(base, 0, 1) * 255).astype("uint8"))
        ImageDraw.Draw(image).rectangle([0, 0, size, 15], fill=(0, 0, 0))
        ImageDraw.Draw(image).text((4, 2), title, fill=(255, 255, 255))
        return image

    grey = np.repeat(rgb.mean(axis=2, keepdims=True), 3, axis=2) * 0.6 + 0.2
    optical = grey.copy()
    optical[fine == cc.WATER_YES] = (0.15, 0.5, 0.95)
    optical[fine == cc.WATER_UNOBSERVABLE] = (0.75, 0.3, 0.75)
    panels = [panel(rgb, "THEOS-2, 30 Jul 2025 03:33 UTC (overview at 6 m)"),
              panel(optical, "Optical water (blue); unobservable (purple)")]
    for name, candidate in layers.items():
        sampled = candidate[np.ix_(rows, columns)]
        wet = fine == cc.WATER_YES
        yes = sampled == cc.CANDIDATE_YES
        view = grey.copy()
        view[wet & yes] = (0.1, 0.65, 0.3)       # both
        view[wet & ~yes] = (0.15, 0.5, 0.95)     # optical water only
        view[~wet & yes] = (0.95, 0.55, 0.1)     # radar candidate only
        view[sampled == cc.CANDIDATE_NO_ANSWER] = view[sampled == cc.CANDIDATE_NO_ANSWER] * 0.5 + 0.35
        view[fine == cc.WATER_UNOBSERVABLE] = (0.75, 0.3, 0.75)
        panels.append(panel(view, f"{name}: both green, optical only blue, radar only orange"))
    sheet = Image.new("RGB", (size * len(panels) + 6 * (len(panels) - 1), size), (255, 255, 255))
    for index, image in enumerate(panels):
        sheet.paste(image, (index * (size + 6), 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)


def stage_compare(arguments: argparse.Namespace) -> None:
    import rasterio
    from pyproj import Transformer

    work = Path(arguments.work_dir)
    reference_path = ROOT / OUTPUT_DIR / REFERENCE_NAME
    if not reference_path.exists():
        raise BuildError("no reference record: run the reference stage first and commit it")
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    for name, entry in reference["rasters_outside_git"].items():
        if not (work / name).exists() or sha256_file(work / name) != entry["sha256"]:
            raise BuildError(f"{name} is not the raster the reference record binds")
    if reference["plan"]["sha256"] != sha256_file(ROOT / PLAN) and not arguments.plan_amended_before_comparison:
        raise BuildError("the plan changed after the reference record was written")
    result_path = ROOT / OUTPUT_DIR / RESULT_NAME
    if result_path.exists() and not arguments.replace:
        raise BuildError(f"{result_path} exists; the comparison is run once (plan section 6)")

    grid_record = reference["grid_10m"]
    grid = (float(grid_record["west"]), float(grid_record["north"]), int(grid_record["rows"]), int(grid_record["columns"]))
    west, north, rows, columns = grid
    bounds = (west, north - rows * CELL_M, west + columns * CELL_M, north)
    tiles = rc.lattice_tiles(bounds)
    cell_km2 = CELL_M * CELL_M / 1e6

    with rasterio.open(work / "theos2_reference_10m.tif") as source:
        water_share, observable_share = source.read(1), source.read(2)
    with rasterio.open(work / "theos2_water_2m.tif") as source:
        water_fine = source.read(1)
        fine_origin = (source.transform.c, source.transform.f)
    cells = cc.reference_cells(water_share, observable_share)

    radar = fetch_radar(work, grid)
    images = {}
    for role in ("pre", "post"):
        with rasterio.open(work / radar[role]["window_file"]) as source:
            images[role] = source.read().astype("float64")
    worldcover = warp_remote(WORLDCOVER_URL, work, "worldcover_10m.tif", grid, nearest=True, dtype="uint8", fill=0)
    height = None
    for index, url in enumerate(DEM_URLS):
        part = warp_remote(url, work, f"dem_{index}_10m.tif", grid, nearest=False, dtype="float32", fill=-9999.0)
        part = np.where(part == -9999.0, np.nan, part)
        height = part if height is None else np.where(np.isfinite(height), height, part)
    slope = rc.slope_degrees(height, CELL_M, CELL_M)
    permanent_water = worldcover == PERMANENT_WATER_CLASS
    in_frame = np.ones((rows, columns), dtype=bool)

    binding = review.require_frozen_m1_v2(ROOT)
    v2_config = sar.m1_v2_config_from_json(binding["parameters"])
    literal_config = sar.M1LiteralConfig()
    un_spider_config = rc.UnSpiderConfig()

    candidates: dict[str, np.ndarray] = {}
    method_notes: dict[str, Any] = {}
    candidate, _, _, summary = rc.un_spider_candidate(
        images["pre"][1], images["post"][1], in_frame=in_frame, permanent_water=permanent_water, slope=slope,
        cell_m=CELL_M, config=un_spider_config)
    candidates["un_spider"] = candidate
    method_notes["un_spider"] = {"summary": summary, "frame": "the two lattice tiles; no clip to the chip"}
    for name, runner in (
        ("m1_literal", lambda pre, post: rc.m1_literal_tile(pre, post, literal_config)),
        ("m1_v2", lambda pre, post: rc.m1_v2_tile(pre, post, v2_config)),
    ):
        candidate, reason, _, _, summaries = rc.run_on_tiles(
            images["pre"], images["post"], tiles, runner, grid_west=west, grid_north=north, cell_m=CELL_M)
        candidates[name] = candidate
        method_notes[name] = {
            "tiles": {tile: {key: value for key, value in tile_summary.items()
                             if not isinstance(value, (dict, list)) or key in ("sides", "threshold_levels")}
                      for tile, tile_summary in summaries.items()},
            "cells_without_an_answer_by_reason": {
                rc.REASON_LABELS[code]: int(((reason == code) & cells["compared"]).sum())
                for code in (rc.REASON_NO_VALID_RADAR_INPUT, rc.REASON_METHOD_DECLINED)},
        }

    flood_cells = cells["compared"] & ~permanent_water
    wet = cells["wet"] & flood_cells
    unmixed = flood_cells & ~cells["mixed"]
    methods: dict[str, Any] = {}
    for name, candidate in candidates.items():
        methods[name] = {
            "flood_input_name": rc.FLOOD_INPUT_NAMES[name],
            "all_compared_cells": cc.agreement(candidate, wet, flood_cells, cell_area_km2=cell_km2),
            "without_mixed_cells": cc.agreement(candidate, wet & unmixed, unmixed, cell_area_km2=cell_km2),
            "by_land_cover_worldcover_2021": cc.agreement_by_class(
                candidate, wet, flood_cells, worldcover, LAND_COVER_GROUPS, cell_area_km2=cell_km2),
            "notes": method_notes[name],
        }

    # --- roads -------------------------------------------------------------
    to_lonlat = Transformer.from_crs(EPSG, 4326, always_xy=True).transform
    to_utm = Transformer.from_crs(4326, EPSG, always_xy=True).transform
    rectangle = reference["theos2_scene"]["valid_rectangle_epsg32647"]
    corners = [to_lonlat(x, y) for x in (rectangle["west"], rectangle["east"]) for y in (rectangle["south"], rectangle["north"])]
    lonlat_bounds = (min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners))
    pbf = Path(arguments.osm_pbf)
    edges = read_roads(pbf, lonlat_bounds)
    start = np.array([edge["start"] for edge in edges], dtype="float64")
    end = np.array([edge["end"] for edge in edges], dtype="float64")
    start_x, start_y = to_utm(start[:, 0], start[:, 1])
    end_x, end_y = to_utm(end[:, 0], end[:, 1])
    segments = np.stack([np.column_stack([start_x, start_y]), np.column_stack([end_x, end_y])], axis=1)
    measured = cc.centreline_water_lengths(segments, water_fine, west=fine_origin[0], north=fine_origin[1], cell_m=FINE_M)
    usable = [index for index, row in enumerate(measured) if row["length_m"] > 0 and row["observable_share"] >= 0.9]
    road_edges = [edges[index] for index in usable]
    road_rows = [measured[index] for index in usable]
    node_coordinates: dict[str, tuple[float, float]] = {}
    for edge in road_edges:
        node_coordinates[edge["from_node"]] = edge["start"]
        node_coordinates[edge["to_node"]] = edge["end"]
    seen_wet = [cc.seen_under_water(row) for row in road_rows]
    lengths = [row["length_m"] for row in road_rows]
    closure = access_diff.closure_arguments(json.loads(
        (ROOT / "docs/proposal_execution/planning_protocol_v1b.json").read_text(encoding="utf-8")))
    optical_extent = np.where(cells["wet"], cc.CANDIDATE_YES, cc.CANDIDATE_NO).astype("uint8")
    road_results: dict[str, Any] = {}
    for name, layer in {"theos2_optical_wet_cells_10m": optical_extent, **candidates}.items():
        extent = candidate_extent(layer, grid)
        intersections = closure_rules.edge_intersections(road_edges, node_coordinates, extent)
        levels = {}
        for level in closure_rules.LEVELS:
            applied = closure_rules.apply_closure_rule(
                level, road_edges, intersections, flood_input_id=name,
                length_thresholds_m=closure["length_thresholds_m"], strict_delays=closure["strict_delays"])
            closed = set(applied["closed_edge_ids"])
            levels[level] = cc.road_agreement([edge["edge_id"] in closed for edge in road_edges], seen_wet, lengths)
        road_results[name] = {"closure_basis": f"modelled_from_{name}", "by_level": levels}
    by_class: dict[str, dict[str, float]] = {}
    for edge, row, wet_edge in zip(road_edges, road_rows, seen_wet):
        entry = by_class.setdefault(edge["road_class"], {"edges": 0, "km": 0.0, "seen_under_water_edges": 0,
                                                         "centreline_on_water_km": 0.0})
        entry["edges"] += 1
        entry["km"] += row["length_m"] / 1000.0
        entry["seen_under_water_edges"] += int(wet_edge)
        entry["centreline_on_water_km"] += row["on_water_m"] / 1000.0
    by_class = {key: {name: (round(value, 3) if isinstance(value, float) else value) for name, value in entry.items()}
                for key, entry in sorted(by_class.items())}

    figure_path = ROOT / OUTPUT_DIR / FIGURE_NAME
    write_figure(figure_path, np.load(work / "theos2_chip_2m.npy"), water_fine, candidates, fine_origin, grid)
    for name, candidate in candidates.items():
        with rasterio.open(work / f"candidate_{name}.tif", "w", driver="GTiff", height=rows, width=columns, count=1,
                           dtype="uint8", nodata=cc.CANDIDATE_NO_ANSWER, crs=f"EPSG:{EPSG}", compress="deflate",
                           transform=rasterio.transform.from_origin(west, north, CELL_M, CELL_M)) as target:
            target.write(candidate, 1)

    pre_time = radar["pre"]["sources"][0]["datetime"]
    post_time = radar["post"]["sources"][0]["datetime"]
    gap_hours = (datetime.fromisoformat(post_time.replace("Z", "+00:00"))
                 - datetime.fromisoformat(THEOS2_ACQUIRED_UTC.replace("Z", "+00:00"))).total_seconds() / 3600.0
    result = {
        "schema": "floodguard.theos2_cross_check.result.v1",
        **envelope(THEOS2_ACQUIRED_UTC),
        "what_this_is": "Agreement between three radar flood candidates and THEOS-2 optical water on one 9 square "
                        "kilometre chip at Sukhothai. A validation tile, not a study area: no FPPS, no A-E class, "
                        "no exposure and no access figure.",
        "label": "agreement with THEOS-2 optical water acquired 43.6 hours before the radar pass; not accuracy",
        "times": {"theos2_utc": THEOS2_ACQUIRED_UTC, "radar_before_utc": pre_time, "radar_after_utc": post_time,
                  "radar_after_minus_theos2_hours": round(gap_hours, 2)},
        "reference": {"record": f"{OUTPUT_DIR}/{REFERENCE_NAME}", "sha256": sha256_file(reference_path),
                      "cells": reference["cells_10m"]},
        "compared_cells": {
            "rule": "observable THEOS-2 cells outside permanent water (ESA WorldCover 2021 v200, class 80)",
            "cells": int(flood_cells.sum()), "km2": round(int(flood_cells.sum()) * cell_km2, 4),
            "optical_wet_cells": int(wet.sum()), "optical_wet_km2": round(int(wet.sum()) * cell_km2, 4),
            "permanent_water_cells_left_out": int((cells["compared"] & permanent_water).sum()),
            "mixed_cells": int((flood_cells & cells["mixed"]).sum()),
        },
        "radar_input": {
            "product": "Sentinel-1 IW GRD, radiometrically terrain-corrected gamma0, 10 m (Microsoft Planetary Computer)",
            "deviation_from_mae_sai": "gamma0 in place of sigma0 (plan section 3)",
            "valid_share_of_compared_cells": {
                role: round(float((np.isfinite(images[role][1]) & flood_cells).sum()) / float(flood_cells.sum()), 6)
                for role in ("pre", "post")},
            "median_vh_db_on_compared_cells": {
                role: round(float(10 * np.log10(np.nanmedian(images[role][1][flood_cells]))), 3) for role in ("pre", "post")},
        },
        "methods": methods,
        "road_check": {
            "source": "OpenStreetMap ways (Geofabrik Thailand extract); one edge per pair of consecutive vertices",
            "edges_read": len(edges), "edges_compared": len(road_edges),
            "rule_for_compared": "at least 90% of the centreline on observable THEOS-2 pixels",
            "seen_under_water_rule": "20 m of centreline on optical water or more; an edge shorter than 40 m also at "
                                     "half its length or more",
            "seen_under_water_edges": int(sum(seen_wet)),
            "seen_under_water_km": round(sum(l for l, w in zip(lengths, seen_wet) if w) / 1000.0, 3),
            "centreline_on_water_km": round(sum(row["on_water_m"] for row in road_rows) / 1000.0, 3),
            "compared_km": round(sum(lengths) / 1000.0, 3),
            "by_road_class": by_class,
            "raster_polygons": "candidate cells polygonised with 4-neighbour connectivity; polygons under 5 cells dropped",
            "closure_parameters": {"length_thresholds_m": closure["length_thresholds_m"],
                                   "strict_delays": closure["strict_delays"]},
            "modelled_against_seen": road_results,
        },
        "figure": f"{OUTPUT_DIR}/{FIGURE_NAME}",
        "assumptions": ASSUMPTIONS,
        "limits": LIMITS,
    }
    previous = superseded(result_path, arguments, ("compared_cells", "methods", "road_check"), result)
    if previous is not None:
        result["supersedes"] = previous
    write_json(result_path, result)
    receipt = {
        "schema": "floodguard.theos2_cross_check.receipt.v1",
        **envelope(THEOS2_ACQUIRED_UTC),
        "run_kind": "first_and_only_comparison_run" if not arguments.replace else "superseding_run",
        "inputs": {
            "theos2_scene": {"file_name": THEOS2_FILE, "sha256": reference["theos2_scene"]["sha256"]},
            "reference_record": {"path": f"{OUTPUT_DIR}/{REFERENCE_NAME}", "sha256": sha256_file(reference_path)},
            "sentinel1": radar,
            "worldcover": {"url": WORLDCOVER_URL, "window_sha256": sha256_file(work / "worldcover_10m.tif"),
                           "credit": "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) "
                                     "processed by ESA WorldCover consortium (CC BY 4.0)"},
            "copernicus_dem": {"urls": list(DEM_URLS),
                               "window_sha256": [sha256_file(work / f"dem_{index}_10m.tif") for index in range(len(DEM_URLS))]},
            "openstreetmap": {"file_name": pbf.name, "sha256": sha256_file(pbf),
                              "credit": "© OpenStreetMap contributors (ODbL 1.0)"},
            "m1_v2_frozen_config": {"path": review.FROZEN_CONFIG_FILE, "sha256": binding["frozen_config_sha256"]},
            "planning_protocol_v1b": {"sha256": sha256_file(ROOT / "docs/proposal_execution/planning_protocol_v1b.json"),
                                      "used_for": "the closure parameters only"},
        },
        "parameters": {
            "un_spider": asdict(un_spider_config), "m1_literal": sar.config_to_json(literal_config),
            "m1_v2": sar.config_to_json(v2_config), "optical": reference["optical_water_rule"]["configuration"],
        },
        "outputs": {
            f"{OUTPUT_DIR}/{RESULT_NAME}": {"sha256": sha256_file(result_path)},
            f"{OUTPUT_DIR}/{FIGURE_NAME}": {"sha256": sha256_file(figure_path)},
            "rasters_outside_git": {f"candidate_{name}.tif": {"sha256": sha256_file(work / f"candidate_{name}.tif")}
                                    for name in candidates},
        },
        "credits": ["Contains modified Copernicus Sentinel data 2025.",
                    "THEOS-2 imagery © GISTDA, sample provided for GeoHackathon 2026."],
        "libraries": {"python": sys.version.split()[0], "numpy": np.__version__, "rasterio": rasterio.__version__},
    }
    write_json(ROOT / OUTPUT_DIR / RECEIPT_NAME, receipt)
    brief = {name: {reading: {key: block[reading][key] for key in ("cells", "tp", "fp", "fn", "iou", "precision", "recall")}
                    for reading in ("on_answered_cells", "strict_no_answer_counts_as_not_a_candidate")}
             for name, block in ((name, methods[name]["all_compared_cells"]) for name in methods)}
    print(json.dumps({"compared_cells": result["compared_cells"], "methods": brief, "supersedes": previous}, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    stages = parser.add_subparsers(dest="stage", required=True)
    first = stages.add_parser("reference", help="build the optical water reference from THEOS-2 alone")
    first.add_argument("--theos2", required=True)
    first.add_argument("--work-dir", required=True)
    first.add_argument("--replace", action="store_true")
    first.add_argument("--reason", default="")
    second = stages.add_parser("compare", help="apply the radar candidates and count the agreement")
    second.add_argument("--work-dir", required=True)
    second.add_argument("--osm-pbf", required=True)
    second.add_argument("--replace", action="store_true")
    second.add_argument("--reason", default="")
    second.add_argument("--plan-amended-before-comparison", action="store_true",
                        help="the plan was amended after the reference record and before any comparison")
    arguments = parser.parse_args()
    {"reference": stage_reference, "compare": stage_compare}[arguments.stage](arguments)


if __name__ == "__main__":
    try:
        main()
    except BuildError as error:
        raise SystemExit(f"refused: {error}") from error
