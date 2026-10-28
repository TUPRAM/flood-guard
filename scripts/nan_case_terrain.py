"""Terrain layers of the Nan case on the exact 20 m grid of every area (case N1, lane TERRAIN).

Rules: ``docs/proposal_execution/nan_case_protocol_v1.json`` (``method.hand``, ``method.slope`` and the
permanent-water rule of ``method.steps``). Grids: ``outputs/nan_case/areas_v1.json`` (EPSG:32647, 20 m, a grid is
west, north, rows, columns as in ``floodguard.s1_rtc.Grid``). For each area the script writes, outside Git, under
``<external-root>/proposal_execution/nan_case_v1/terrain/<area>/``:

``dem_m.tif``                  Copernicus DEM GLO-30, bilinear to the 20 m grid (float32, NaN no-data).
``slope_deg.tif``              slope in degrees of that 20 m DEM (float32, NaN no-data).
``hand_m.tif``                 height above the nearest drainage by the method of work package 4, computed on a
                               buffered 30 m window and interpolated bilinearly to the 20 m grid (float32).
``hand_1km2_context_m.tif``    the same with the 1 km2 stream threshold of work package 4; context only, not the
                               HAND of the protocol.
``hand_straight_line_rule.tif`` 1 where ``hand_m.tif`` came from the straight-line rule of work package 4 (no
                               resolved D8 path to a stream inside the window), 0 where it came from the flow path.
``worldcover.tif``             ESA WorldCover 2021 v200 class codes, the most common 10 m class of each 20 m cell
                               (uint8, 0 no-data).
``permanent_water.tif``        1 where that class is 80, else 0 (uint8).
``jrc_occurrence.tif``         JRC Global Surface Water occurrence 1984-2021 in percent (uint8, 255 no-data);
                               context only, not used by the method.
``terrain_record.json``        sources, tiles and their SHA-256, the HAND method and threshold, the grid, the
                               file hashes, and checks of HAND against windows buffered by 10 and 30 km
                               (the window of record is buffered by 20 km).

Tiles that are not under ``open_context/`` are fetched once from the public buckets (Copernicus DEM on AWS,
ESA WorldCover on AWS, JRC on Google Cloud Storage) into ``terrain/_sources/<kind>/`` and hashed.

These are terrain inputs of the method lane. Nothing here reads a radar image, a flood reference or a flag, and
nothing here is an official warning. Planning guidance only.

Example::

    python scripts/nan_case_terrain.py --external-root <external-data-root>
    python scripts/nan_case_terrain.py --external-root <external-data-root> --areas sukhothai_chip --replace
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any
import urllib.error
import urllib.request

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import radar_candidates as rc  # noqa: E402
from floodguard.s1_rtc import Grid  # noqa: E402

PROTOCOL = "docs/proposal_execution/nan_case_protocol_v1.json"
AREAS = "outputs/nan_case/areas_v1.json"
SCRIPT = "scripts/nan_case_terrain.py"
WP4_SCRIPT = "scripts/build_flood_susceptibility_model.py"
WORK = Path("proposal_execution") / "nan_case_v1" / "terrain"
SEALED_FOLDER = "jaxa_sealed"
SCHEMA = "floodguard.nan_case_terrain.v1"

EPSG = 32647
CELL_M = 20.0
FINE_M = 10.0
FINE_FACTOR = int(CELL_M // FINE_M)
HYDRO_CELL_M = 30.0  # work package 4 (CELL_M of scripts/build_flood_susceptibility_model.py)
MAIN_STREAM_KM2 = 25.0  # work package 4, the stream of its HAND feature hand_main_stream_m
SMALL_STREAM_KM2 = 1.0  # work package 4, hand_small_stream_m (context only here)
BUFFER_M = 20_000.0
MIN_BUFFER_M = 5_000.0
CHECK_BUFFERS_M = (10_000.0, 30_000.0)
BUFFER_CHOICE = (
    "20 km, chosen on terrain alone (no flood layer, radar image or reference was read) from windows buffered by 5, "
    "10, 20 and 30 km: the flat resolution of pysheds leaves interior pits whose position depends on the window, and "
    "with a 10 km buffer one such pit sent 31% of the Chaiyaphum chip's cells to the straight-line rule; with 20 km "
    "that share is at most 2.6% in every area. The windows of 10 and 30 km are kept as checks (hand.edge_checks).")
LONLAT_MARGIN_DEG = 0.01
DEM_NODATA = -9999.0
PERMANENT_WATER = 80
WORLDCOVER_NODATA = 0
JRC_NODATA = 255
TUNING_FIRST = ("sukhothai_chip", "mae_sai_20241022", "chaiyaphum_20210928")

OPEN_CONTEXT = {
    "copernicus_dem_glo30": Path("open_context") / "copernicus_dem_glo30",
    "esa_worldcover": Path("open_context") / "esa_worldcover",
    "jrc_global_surface_water": Path("open_context") / "jrc_global_surface_water",
}
DEM_URL = "https://copernicus-dem-30m.s3.amazonaws.com/{stem}/{stem}.tif"
WORLDCOVER_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/{name}"
JRC_URL = "https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/{name}"
USER_AGENT = "floodguard-nan-case-terrain/1"

SOURCE_TIMESTAMP = ("Copernicus DEM GLO-30: TanDEM-X acquisitions of 2011 to 2015; ESA WorldCover 2021 v200: "
                    "2021-01-01 to 2021-12-31; JRC Global Surface Water v1.4 occurrence: March 1984 to December 2021")
CREDITS = [
    "Copernicus DEM GLO-30, produced using Copernicus WorldDEM-30 (c) DLR e.V. 2010-2014 and (c) Airbus Defence and "
    "Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA; all rights reserved.",
    "ESA WorldCover 2021 v200 (c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021), "
    "CC BY 4.0.",
    "JRC Global Surface Water v1.4, Pekel et al. (2016), Nature 540, 418-422, (c) European Commission, Joint "
    "Research Centre.",
]
ASSUMPTIONS = [
    "Every layer is on the area's exact grid: EPSG:32647, 20 m cells, north-up, west and north edges and the "
    "numbers of rows and columns as in outputs/nan_case/areas_v1.json.",
    "Copernicus DEM GLO-30 is a surface model: its heights include buildings and tree canopy, so slope and HAND "
    "under trees and in towns are those of the top surface, not of the ground.",
    "Heights are kept as delivered (EGM2008 geoid); no datum change is applied.",
    "Reprojection uses GDAL's warper with its default approximation of the projection, within 0.125 of a source "
    "pixel (about 4 m for GLO-30), as in work package 4; on steep slopes this moves a bilinear height by up to about "
    "3 m against an exact transformation (median about 0.3 m over the Nan frame), and much less on flat ground.",
    "The DEM tiles are mosaicked on their own pixel lattice (the box widened to whole pixels, so no value is moved) "
    "and then interpolated bilinearly, so tile edges leave no seam.",
    "Slope is computed from the four neighbours of each 20 m cell on the bilinear 20 m DEM, read with a margin of "
    "one cell so the grid's border cells have a slope too.",
    "HAND follows work package 4: the DEM is put on a 30 m EPSG:32647 grid by bilinear interpolation, pits and "
    "depressions are filled and flats resolved with pysheds, D8 flow directions and upstream cells are computed, a "
    "stream is a cell with at least 25 km2 upstream or WorldCover 2021 class 80 on the 30 m grid (nearest), and "
    "HAND is the height above the stream cell each cell drains to.",
    "The hydrology window is the area buffered by 20 km and snapped outward to 30 m; upstream area is counted "
    "inside the window only, which is why permanent water counts as a stream.",
    "A cell without a resolved flow path to a stream gets its height above the nearest stream cell in a straight "
    "line, and HAND below zero is set to zero (both rules of work package 4).",
    "The flat resolution of pysheds leaves some interior pits; a cell whose D8 path ends in a pit with less than "
    "25 km2 upstream takes the straight-line rule. hand_straight_line_rule.tif marks those cells.",
    "HAND is interpolated bilinearly from 30 m to the 20 m grid, so a 20 m cell beside a stream can hold a small "
    "positive value.",
    "WorldCover on the 20 m grid is the most common class of the four 10 m cells of the cell; each 10 m cell takes "
    "the class at its centre (nearest); 10 m cells without a class are not counted; ties go to the smallest class "
    "code, the convention of scipy.stats.mode.",
    "JRC occurrence is context only and is not read by the method of the protocol; it is put on the grid by "
    "nearest cell.",
    "Nothing here reads a radar image, a flood reference or a flag; these layers are inputs of the method lane.",
]


class TerrainError(RuntimeError):
    """The terrain layers of an area cannot be built from these inputs."""


class SourceAbsent(TerrainError):
    """The provider holds no file of that name (HTTP 404)."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def now_utc() -> str:
    """The current UTC time as an ISO 8601 string with a Z."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    """SHA-256 of a file's bytes."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_git_text(path: Path) -> str:
    """SHA-256 of a text file as Git holds it (LF line ends, ``.gitattributes`` eol=lf)."""

    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write JSON with LF line ends, so a recorded SHA-256 matches the bytes Git holds."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, indent=1, ensure_ascii=False) + "\n")


def refuse_sealed(path: Path) -> Path:
    """Raise when a path lies inside the sealed folder of the case; the terrain lane never opens it."""

    if SEALED_FOLDER in Path(path).parts:
        raise TerrainError(f"refused: {path} lies inside the sealed folder of the case")
    return Path(path)


def log(message: str) -> None:
    print(f"{now_utc()} {message}", flush=True)


# ---------------------------------------------------------------------------
# Grids and tiles
# ---------------------------------------------------------------------------


def area_grid(entry: Mapping[str, Any]) -> Grid:
    """The (west, north, rows, columns) grid of an entry of ``areas_v1.json``."""

    grid = entry["grid"]
    rows, columns = int(grid["rows"]), int(grid["cols"])
    if rows <= 0 or columns <= 0:
        raise TerrainError("a grid needs positive numbers of rows and columns")
    return (float(grid["west"]), float(grid["north"]), rows, columns)


def grid_bounds(grid: Grid, cell_m: float) -> tuple[float, float, float, float]:
    """West, south, east and north edges of a grid."""

    west, north, rows, columns = grid
    return (west, north - rows * cell_m, west + columns * cell_m, north)


def grid_transform(grid: Grid, cell_m: float) -> Any:
    """The affine transform of a north-up grid."""

    from rasterio.transform import from_origin

    return from_origin(grid[0], grid[1], cell_m, cell_m)


def expand_grid(grid: Grid, cell_m: float, cells: int) -> Grid:
    """The same lattice with ``cells`` more cells on every side."""

    west, north, rows, columns = grid
    return (west - cells * cell_m, north + cells * cell_m, rows + 2 * cells, columns + 2 * cells)


def fine_grid(grid: Grid, factor: int = FINE_FACTOR) -> Grid:
    """The grid of cells ``factor`` times smaller with the same edges (the 10 m cells of a 20 m grid)."""

    west, north, rows, columns = grid
    return (west, north, rows * factor, columns * factor)


def hydrology_grid(grid: Grid, cell_m: float, buffer_m: float, hydro_cell_m: float = HYDRO_CELL_M) -> Grid:
    """The flow-routing window: the area buffered by ``buffer_m`` and snapped outward to whole ``hydro_cell_m``.

    The edges are whole multiples of ``hydro_cell_m``, as the window of work package 4 was.
    """

    if buffer_m < 0 or hydro_cell_m <= 0:
        raise TerrainError("the buffer must not be negative and the hydrology cell must be positive")
    west, south, east, north = grid_bounds(grid, cell_m)
    west = math.floor((west - buffer_m) / hydro_cell_m) * hydro_cell_m
    south = math.floor((south - buffer_m) / hydro_cell_m) * hydro_cell_m
    east = math.ceil((east + buffer_m) / hydro_cell_m) * hydro_cell_m
    north = math.ceil((north + buffer_m) / hydro_cell_m) * hydro_cell_m
    return (float(west), float(north), int(round((north - south) / hydro_cell_m)), int(round((east - west) / hydro_cell_m)))


def lonlat_bounds(bounds: Sequence[float], epsg: int = EPSG, margin_deg: float = 0.0) -> tuple[float, float, float, float]:
    """The lon/lat box around projected bounds, widened by ``margin_deg`` on every side."""

    from rasterio.warp import transform_bounds

    west, south, east, north = transform_bounds(f"EPSG:{epsg}", "EPSG:4326", *bounds, densify_pts=21)
    return (west - margin_deg, south - margin_deg, east + margin_deg, north + margin_deg)


def _hemisphere(value: int, positive: str, negative: str, width: int) -> str:
    return f"{positive if value >= 0 else negative}{abs(value):0{width}d}"


def dem_tiles(lonlat: Sequence[float]) -> list[tuple[str, str]]:
    """File names and public addresses of the 1-degree Copernicus DEM GLO-30 tiles that touch a lon/lat box."""

    west, south, east, north = lonlat
    tiles = []
    for lat in range(math.floor(south), math.floor(north) + 1):
        for lon in range(math.floor(west), math.floor(east) + 1):
            stem = (f"Copernicus_DSM_COG_10_{_hemisphere(lat, 'N', 'S', 2)}_00_"
                    f"{_hemisphere(lon, 'E', 'W', 3)}_00_DEM")
            tiles.append((f"{stem}.tif", DEM_URL.format(stem=stem)))
    return tiles


def worldcover_tiles(lonlat: Sequence[float]) -> list[tuple[str, str]]:
    """File names and public addresses of the 3-degree ESA WorldCover 2021 v200 tiles that touch a lon/lat box."""

    west, south, east, north = lonlat
    tiles = []
    for lat in range(3 * math.floor(south / 3), 3 * math.floor(north / 3) + 1, 3):
        for lon in range(3 * math.floor(west / 3), 3 * math.floor(east / 3) + 1, 3):
            name = f"ESA_WorldCover_10m_2021_v200_{_hemisphere(lat, 'N', 'S', 2)}{_hemisphere(lon, 'E', 'W', 3)}_Map.tif"
            tiles.append((name, WORLDCOVER_URL.format(name=name)))
    return tiles


def jrc_tiles(lonlat: Sequence[float]) -> list[tuple[str, str]]:
    """File names and public addresses of the 10-degree JRC occurrence tiles (named by west and north edge)."""

    west, south, east, north = lonlat
    tiles = []
    for top in range(10 * math.floor(north / 10) + 10, 10 * math.floor(south / 10), -10):
        for lon in range(10 * math.floor(west / 10), 10 * math.floor(east / 10) + 1, 10):
            name = f"occurrence_{abs(lon)}{'E' if lon >= 0 else 'W'}_{abs(top)}{'N' if top >= 0 else 'S'}v1_4_2021.tif"
            tiles.append((name, JRC_URL.format(name=name)))
    return tiles


# ---------------------------------------------------------------------------
# Sources: on disk under open_context, or fetched once into the work folder
# ---------------------------------------------------------------------------


def download(url: str, target: Path, *, tries: int = 6, timeout: float = 180.0) -> dict[str, Any]:
    """Fetch a public file to ``target`` (through a ``.part`` file); retried, and checked against its length."""

    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response, part.open("wb") as handle:
                expected = int(response.headers.get("Content-Length") or -1)
                headers = {"last_modified": response.headers.get("Last-Modified"), "etag": response.headers.get("ETag"),
                           "content_length": expected}
                shutil.copyfileobj(response, handle, 8 * 1024 * 1024)
            if expected >= 0 and part.stat().st_size != expected:
                raise TerrainError(f"{url}: {part.stat().st_size} bytes received, {expected} announced")
            os.replace(part, target)
            return {"url": url, "fetched_at_utc": now_utc(), **headers}
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise SourceAbsent(f"{url} does not exist") from error
            if attempt == tries - 1:
                raise
        except Exception:  # noqa: BLE001 - the hosts time out now and then: retried, then raised
            if attempt == tries - 1:
                raise
        time.sleep(min(60, 10 * (attempt + 1)))
    raise TerrainError("unreachable")


_HASHES: dict[str, str] = {}


def resolve_source(external: Path, kind: str, name: str, url: str, *, allow_download: bool) -> dict[str, Any] | None:
    """Find a tile under ``open_context/<kind>/``, else in ``terrain/_sources/<kind>/``, else fetch it there.

    Returns its record (file, place, SHA-256, bytes, address) or None when it is not on disk and may not be fetched.
    Raises SourceAbsent when the provider holds no such file.
    """

    local = external / OPEN_CONTEXT[kind] / name
    cached = external / WORK / "_sources" / kind / name
    sidecar = cached.with_name(name + ".download.json")
    if local.exists():
        path, origin, fetched = local, "on disk under open_context", None
    elif cached.exists():
        path, origin = cached, "fetched earlier by this script from the public address"
        fetched = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else None
    elif allow_download:
        log(f"fetching {url}")
        fetched = download(url, cached)
        path, origin = cached, "fetched by this script from the public address"
        fetched["sha256"] = sha256_file(cached)
        write_json(sidecar, fetched)
    else:
        return None
    refuse_sealed(path)
    key = str(path.resolve())
    if key not in _HASHES:
        _HASHES[key] = sha256_file(path)
    record: dict[str, Any] = {"file": name, "path_under_external_root": path.relative_to(external).as_posix(),
                              "origin": origin, "sha256": _HASHES[key], "bytes": path.stat().st_size,
                              "public_address": url}
    if fetched:
        record["fetch"] = {key_: fetched[key_] for key_ in ("fetched_at_utc", "last_modified", "etag") if key_ in fetched}
    return record


def resolve_tiles(external: Path, kind: str, tiles: Iterable[tuple[str, str]], *,
                  allow_download: bool) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Records of the tiles found or fetched, and the tiles that could not be had (with the reason)."""

    found: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for name, url in tiles:
        try:
            record = resolve_source(external, kind, name, url, allow_download=allow_download)
        except SourceAbsent:
            missing.append({"file": name, "url": url, "reason": "the provider holds no such tile"})
            continue
        if record is None:
            missing.append({"file": name, "url": url, "reason": "not on disk, and fetching was not allowed"})
        else:
            found.append(record)
    return found, missing


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------


def snap_to_lattice(bounds: Sequence[float], transform: Any) -> tuple[float, float, float, float]:
    """Bounds widened outward to the pixel edges of a north-up raster's lattice."""

    step_x, step_y = transform.a, -transform.e
    if step_x <= 0 or step_y <= 0 or transform.b or transform.d:
        raise TerrainError("the DEM tiles must be north-up")
    x0, y0 = transform.c, transform.f
    west, south, east, north = bounds
    tolerance = 1e-6
    return (x0 + math.floor((west - x0) / step_x + tolerance) * step_x,
            y0 - math.ceil((y0 - south) / step_y - tolerance) * step_y,
            x0 + math.ceil((east - x0) / step_x - tolerance) * step_x,
            y0 - math.floor((y0 - north) / step_y + tolerance) * step_y)


def mosaic_dem(paths: Sequence[Path], lonlat: Sequence[float]) -> tuple[np.ndarray, Any, Any]:
    """The DEM tiles merged over a lon/lat box (float32, ``DEM_NODATA`` where no tile holds a value).

    The box is first widened to the pixel edges of the tiles, so the mosaic holds the tile values on their own
    lattice: rasterio's merge re-grids by nearest cell, with a shift of up to half a pixel, when the bounds fall
    between pixel edges.

    Raises:
        TerrainError: when the tiles do not share one lattice.
    """

    import rasterio
    from rasterio.merge import merge

    sources = [rasterio.open(refuse_sealed(path)) for path in paths]
    try:
        reference = sources[0].transform
        for source in sources[1:]:
            other = source.transform
            if (abs(other.a - reference.a) > 1e-12 or abs(other.e - reference.e) > 1e-12
                    or abs(((other.c - reference.c) / reference.a) % 1.0 - 0.5) < 0.5 - 1e-6
                    or abs(((other.f - reference.f) / reference.e) % 1.0 - 0.5) < 0.5 - 1e-6):
                raise TerrainError("the DEM tiles do not share one pixel lattice")
        mosaic, transform = merge(sources, bounds=snap_to_lattice(lonlat, reference), nodata=DEM_NODATA)
        crs = sources[0].crs
    finally:
        for source in sources:
            source.close()
    return mosaic[0].astype("float32"), transform, crs


def warp_array(values: np.ndarray, src_transform: Any, src_crs: Any, src_nodata: float, grid: Grid, cell_m: float, *,
               resampling: str, dtype: str, fill: float) -> np.ndarray:
    """An in-memory raster resampled onto ``grid`` (EPSG:32647); cells without a source value get ``fill``."""

    from rasterio.warp import Resampling, reproject

    west, north, rows, columns = grid
    target = np.full((rows, columns), fill, dtype=dtype)
    reproject(values, target, src_transform=src_transform, src_crs=src_crs, src_nodata=src_nodata,
              dst_transform=grid_transform(grid, cell_m), dst_crs=f"EPSG:{EPSG}", dst_nodata=fill,
              resampling=getattr(Resampling, resampling), init_dest_nodata=True)
    return target


def warp_files(paths: Sequence[Path], grid: Grid, cell_m: float, *, resampling: str, dtype: str, fill: int) -> np.ndarray:
    """Band 1 of several tiles resampled onto ``grid``; a later tile fills only the cells earlier ones left at ``fill``."""

    import rasterio
    from rasterio.warp import Resampling, reproject

    west, north, rows, columns = grid
    result = np.full((rows, columns), fill, dtype=dtype)
    for path in paths:
        part = np.full((rows, columns), fill, dtype=dtype)
        with rasterio.open(refuse_sealed(path)) as source:
            reproject(rasterio.band(source, 1), part, dst_transform=grid_transform(grid, cell_m), dst_crs=f"EPSG:{EPSG}",
                      dst_nodata=fill, resampling=getattr(Resampling, resampling), init_dest_nodata=True)
        result = np.where(result == fill, part, result)
    return result


def most_common_class(fine: np.ndarray, factor: int = FINE_FACTOR, nodata: int = WORLDCOVER_NODATA) -> np.ndarray:
    """The most common class of each block of ``factor`` by ``factor`` fine cells.

    Fine cells holding ``nodata`` are not counted; a block of only ``nodata`` cells is ``nodata``. Ties go to the
    smallest class code (the convention of ``scipy.stats.mode``).

    Raises:
        TerrainError: when the fine grid is not a whole number of blocks.
    """

    classes = np.asarray(fine)
    if classes.ndim != 2 or factor < 1 or classes.shape[0] % factor or classes.shape[1] % factor:
        raise TerrainError("the fine grid must be two-dimensional and a whole number of blocks each way")
    rows, columns = classes.shape[0] // factor, classes.shape[1] // factor
    blocks = classes.reshape(rows, factor, columns, factor)
    best = np.full((rows, columns), nodata, dtype=classes.dtype)
    best_count = np.zeros((rows, columns), dtype="uint16")
    for code in np.unique(classes):  # ascending, and only a strictly larger count replaces: ties keep the smaller code
        if code == nodata:
            continue
        count = (blocks == code).sum(axis=(1, 3), dtype="uint16")
        better = count > best_count
        best[better] = code
        best_count[better] = count[better]
    return best


def slope_on_grid(dem_with_margin: np.ndarray, cell_m: float) -> np.ndarray:
    """Slope in degrees of the inner cells of a DEM read with a margin of one cell (``radar_candidates.slope_degrees``)."""

    heights = np.asarray(dem_with_margin, dtype="float64")
    if heights.ndim != 2 or min(heights.shape) < 3:
        raise TerrainError("the DEM with its margin must have at least three rows and columns")
    return rc.slope_degrees(heights, cell_m, cell_m)[1:-1, 1:-1].astype("float32")


# ---------------------------------------------------------------------------
# HAND, as work package 4 computed it
# ---------------------------------------------------------------------------


def hand_wp4(dem_path: Path, water: np.ndarray, cell_m: float,
             thresholds_km2: Mapping[str, float]) -> tuple[dict[str, np.ndarray], dict[str, Any], dict[str, np.ndarray]]:
    """Height above the nearest drainage by the flow routing of work package 4.

    The statements are those of ``stage_features`` in ``scripts/build_flood_susceptibility_model.py`` (from
    ``ShedGrid.from_raster`` to ``np.clip(hand, 0, None)``), with the window, the cell size and the thresholds
    passed in: pits, depressions and flats of the DEM are resolved with pysheds, D8 flow directions and upstream
    cells are computed, a stream is a cell with at least the threshold of upstream area or a ``water`` cell,
    ``compute_hand`` gives the height above the stream cell each cell drains to, a cell without a resolved flow
    path gets its height above the nearest stream cell in a straight line, and values below zero become zero.

    Args:
        dem_path: a GeoTIFF of the DEM on a projected grid of ``cell_m`` with ``DEM_NODATA`` as no-data.
        water: cells that count as stream whatever their upstream area (permanent water), on the same grid.
        cell_m: the cell size of the DEM in metres.
        thresholds_km2: name to the upstream area in km2 that makes a stream.

    Returns:
        HAND in metres per name (float32, NaN where the DEM holds no value), the counts work package 4 recorded,
        and per name the cells whose HAND came from the straight-line rule (bool).
    """

    from pysheds.grid import Grid as ShedGrid
    from scipy import ndimage

    shed = ShedGrid.from_raster(str(dem_path))
    raw = shed.read_raster(str(dem_path))
    no_terrain = ~np.isfinite(np.asarray(raw, dtype="float64")) | (np.asarray(raw) == DEM_NODATA)
    if np.asarray(water).shape != np.asarray(raw).shape:
        raise TerrainError("the water mask is not on the grid of the DEM")
    conditioned = shed.resolve_flats(shed.fill_depressions(shed.fill_pits(raw)))
    direction = shed.flowdir(conditioned)
    accumulation = shed.accumulation(direction)
    surface = np.asarray(conditioned, dtype="float32")
    layers: dict[str, np.ndarray] = {}
    counts: dict[str, Any] = {}
    straight_line: dict[str, np.ndarray] = {}
    for name, threshold in thresholds_km2.items():
        stream_raster = accumulation * (cell_m ** 2) / 1e6 >= threshold  # keeps the pysheds raster type
        stream_raster[water] = True
        streams = np.asarray(stream_raster, dtype=bool)
        if not streams.any():
            raise TerrainError(f"no stream cell for the {threshold} km2 threshold in the window")
        counts[f"{name}_stream_cells"] = int(streams.sum())
        hand = np.asarray(shed.compute_hand(direction, conditioned, stream_raster), dtype="float32")
        distance, indices = ndimage.distance_transform_edt(~streams, return_indices=True)
        missing = ~np.isfinite(hand)
        # A flat without a resolved flow path gets its height above the nearest stream cell in a straight line.
        hand[missing] = surface[missing] - surface[indices[0], indices[1]][missing]
        counts[f"{name}_cells_without_a_flow_path"] = int(missing.sum())
        layers[name] = np.where(no_terrain, np.nan, np.clip(hand, 0, None)).astype("float32")
        straight_line[name] = missing & ~no_terrain
    counts["cells_without_terrain"] = int(no_terrain.sum())
    counts["window_cells"] = int(no_terrain.size)
    return layers, counts, straight_line


# ---------------------------------------------------------------------------
# Writing and checking
# ---------------------------------------------------------------------------


def write_raster(path: Path, array: np.ndarray, grid: Grid, cell_m: float, *, nodata: float | None,
                 description: str = "") -> None:
    """One band on ``grid`` as a tiled, DEFLATE-compressed GeoTIFF."""

    import rasterio

    west, north, rows, columns = grid
    values = np.asarray(array)
    if values.shape != (rows, columns):
        raise TerrainError(f"{path.name}: the array is {values.shape}, the grid {rows} by {columns}")
    refuse_sealed(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile: dict[str, Any] = {"driver": "GTiff", "height": rows, "width": columns, "count": 1, "dtype": values.dtype.name,
                               "crs": f"EPSG:{EPSG}", "transform": grid_transform(grid, cell_m), "compress": "deflate",
                               "tiled": True, "blockxsize": 256, "blockysize": 256}
    if values.dtype.kind == "f":
        profile["predictor"] = 3
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as target:
        target.write(values, 1)
        if description:
            target.set_band_description(1, description)


def check_alignment(path: Path, grid: Grid, cell_m: float) -> None:
    """Raise unless the raster is exactly on ``grid``: EPSG:32647, the cell size, the west and north edges, the shape."""

    import rasterio

    west, north, rows, columns = grid
    with rasterio.open(path) as source:
        transform = source.transform
        if source.crs is None or source.crs.to_epsg() != EPSG:
            raise TerrainError(f"{path.name} is not on EPSG:{EPSG}")
        if (source.height, source.width) != (rows, columns):
            raise TerrainError(f"{path.name} is {source.height} by {source.width}, the grid {rows} by {columns}")
        expected = (cell_m, 0.0, west, 0.0, -cell_m, north)
        if any(abs(a - b) > 1e-6 for a, b in zip((transform.a, transform.b, transform.c, transform.d, transform.e,
                                                  transform.f), expected)):
            raise TerrainError(f"{path.name} is not aligned to the grid: {tuple(transform)[:6]}")


def describe(values: np.ndarray) -> dict[str, Any]:
    """Count, no-data count and quantiles of a float layer."""

    array = np.asarray(values, dtype="float64")
    finite = array[np.isfinite(array)]
    result: dict[str, Any] = {"cells": int(array.size), "no_data_cells": int(array.size - finite.size)}
    if finite.size:
        quantiles = np.quantile(finite, [0.05, 0.25, 0.5, 0.75, 0.95])
        result.update({"min": round(float(finite.min()), 3), "p05": round(float(quantiles[0]), 3),
                       "p25": round(float(quantiles[1]), 3), "p50": round(float(quantiles[2]), 3),
                       "p75": round(float(quantiles[3]), 3), "p95": round(float(quantiles[4]), 3),
                       "max": round(float(finite.max()), 3), "mean": round(float(finite.mean()), 3)})
    return result


def class_counts(values: np.ndarray) -> dict[str, int]:
    """Cells per class code."""

    codes, counts = np.unique(np.asarray(values), return_counts=True)
    return {str(int(code)): int(count) for code, count in zip(codes, counts)}


def edge_check(main: np.ndarray, other: np.ndarray, buffer_m: float, other_buffer_m: float,
               cuts_m: Sequence[float]) -> dict[str, Any]:
    """How far HAND on the 20 m grid moves when the hydrology window is buffered less.

    For each cut the share of cells the two windows put on different sides of it is given: a terrain statistic,
    not a flag.
    """

    both = np.isfinite(main) & np.isfinite(other)
    difference = np.abs(main[both].astype("float64") - other[both].astype("float64"))
    cells = int(both.sum())
    share = (lambda mask: round(float(mask.sum()) / cells, 6)) if cells else (lambda mask: None)
    return {
        "what": f"HAND (25 km2) on the 20 m grid with the window buffered by {int(buffer_m)} m against {int(other_buffer_m)} m",
        "cells_compared": cells,
        "share_differing_by_more_than_0_5_m": share(difference > 0.5),
        "share_differing_by_more_than_1_m": share(difference > 1.0),
        "share_differing_by_more_than_2_m": share(difference > 2.0),
        "median_abs_difference_m": round(float(np.median(difference)), 4) if cells else None,
        "max_abs_difference_m": round(float(difference.max()), 3) if cells else None,
        "share_on_different_sides_of": {f"{cut:g}": share((main[both] > cut) != (other[both] > cut)) for cut in cuts_m},
    }


# ---------------------------------------------------------------------------
# One area
# ---------------------------------------------------------------------------


def hydrology_hand(folder: Path, mosaic: tuple[np.ndarray, Any, Any], cover_paths: Sequence[Path], grid: Grid,
                   buffer_m: float, thresholds_km2: Mapping[str, float]) -> tuple[dict[str, np.ndarray], dict[str, Any], Grid]:
    """HAND on the buffered 30 m window of an area, and the record of that window.

    The layers are HAND per threshold name and, under ``<name>_straight_line``, the cells (uint8, 1 or 0) whose
    HAND came from the straight-line rule.
    """

    window = hydrology_grid(grid, CELL_M, buffer_m)
    values, transform, crs = mosaic
    elevation = warp_array(values, transform, crs, DEM_NODATA, window, HYDRO_CELL_M, resampling="bilinear",
                           dtype="float32", fill=np.nan)
    dem_path = folder / f"dem_30m_buffer_{int(buffer_m)}m.tif"
    # The window may reach past the tiles; those cells are no-data, as in work package 4.
    write_raster(dem_path, np.where(np.isfinite(elevation), elevation, DEM_NODATA).astype("float32"), window,
                 HYDRO_CELL_M, nodata=DEM_NODATA, description="Copernicus DEM GLO-30, bilinear to 30 m (m)")
    cover = warp_files(cover_paths, window, HYDRO_CELL_M, resampling="nearest", dtype="uint8", fill=WORLDCOVER_NODATA)
    water = cover == PERMANENT_WATER
    clock = time.perf_counter()
    layers, counts, straight_line = hand_wp4(dem_path, water, HYDRO_CELL_M, thresholds_km2)
    for key, mask in straight_line.items():
        layers[f"{key}_straight_line"] = mask.astype("uint8")
    record = {"west": window[0], "north": window[1], "rows": window[2], "cols": window[3], "cell_m": HYDRO_CELL_M,
              "epsg": EPSG, "buffer_m": buffer_m, "dem_file": dem_path.name, "dem_sha256": sha256_file(dem_path),
              "permanent_water_cells_30m": int(water.sum()), **counts,
              "flow_routing_seconds": round(time.perf_counter() - clock, 1)}
    return layers, record, window


def build_area(external: Path, name: str, entry: Mapping[str, Any], *, provenance: Mapping[str, Any],
               buffer_m: float = BUFFER_M, check_buffers_m: Sequence[float] = CHECK_BUFFERS_M,
               hand_cuts_m: Sequence[float] = (5, 10, 15, 20), allow_download: bool = True,
               main_threshold_km2: float = MAIN_STREAM_KM2, small_threshold_km2: float = SMALL_STREAM_KM2) -> dict[str, Any]:
    """Write the terrain layers of one area on its exact 20 m grid and return its record.

    Args:
        external: the external data root.
        name: the area's key in ``areas_v1.json``.
        entry: the area's entry in ``areas_v1.json``.
        provenance: hashes of the protocol, the areas file and the code, copied into the record.
        buffer_m: the buffer of the hydrology window around the area.
        check_buffers_m: other buffers whose HAND is set against the HAND of record (edge checks); empty skips them.
        hand_cuts_m: HAND values at which the edge checks count changes of side (the protocol's hand_max_m).
        allow_download: whether tiles missing on disk may be fetched from the public addresses.
        main_threshold_km2: the stream threshold of ``hand_m.tif`` (25 km2, work package 4).
        small_threshold_km2: the stream threshold of ``hand_1km2_context_m.tif`` (1 km2, work package 4).
    """

    clock = time.perf_counter()
    grid = area_grid(entry)
    folder = refuse_sealed(external / WORK / name)
    hydro_folder = folder / "hydrology"
    hydro_folder.mkdir(parents=True, exist_ok=True)
    for stale in hydro_folder.glob("*_30m_buffer_*m.tif"):  # windows of an earlier build of this area
        stale.unlink()
    largest = max([buffer_m, *check_buffers_m])
    window = hydrology_grid(grid, CELL_M, largest)
    window_lonlat = lonlat_bounds(grid_bounds(window, HYDRO_CELL_M), margin_deg=LONLAT_MARGIN_DEG)

    dem_found, dem_missing = resolve_tiles(external, "copernicus_dem_glo30", dem_tiles(window_lonlat), allow_download=allow_download)
    if not dem_found:
        raise TerrainError(f"{name}: no Copernicus DEM tile covers the area")
    cover_found, cover_missing = resolve_tiles(external, "esa_worldcover", worldcover_tiles(window_lonlat),
                                               allow_download=allow_download)
    if not cover_found:
        raise TerrainError(f"{name}: no WorldCover tile covers the area")
    area_lonlat = lonlat_bounds(grid_bounds(grid, CELL_M), margin_deg=LONLAT_MARGIN_DEG)
    jrc_found, jrc_missing = resolve_tiles(external, "jrc_global_surface_water", jrc_tiles(area_lonlat),
                                           allow_download=allow_download)
    for kind, missing in (("Copernicus DEM", dem_missing), ("WorldCover", cover_missing)):
        if any(item["reason"] != "the provider holds no such tile" for item in missing):
            raise TerrainError(f"{name}: a {kind} tile of the area is not on disk and may not be fetched")
    dem_paths = [external / record["path_under_external_root"] for record in dem_found]
    cover_paths = [external / record["path_under_external_root"] for record in cover_found]
    log(f"{name}: grid {grid}, {len(dem_found)} DEM tiles, {len(cover_found)} WorldCover tiles, {len(jrc_found)} JRC tiles")

    mosaic = mosaic_dem(dem_paths, window_lonlat)
    files: dict[str, dict[str, Any]] = {}

    # DEM and slope on the 20 m grid (bilinear from the mosaic, one cell of margin for the slope).
    margin = expand_grid(grid, CELL_M, 1)
    dem_margin = warp_array(*mosaic[:3], DEM_NODATA, margin, CELL_M, resampling="bilinear", dtype="float32", fill=np.nan)
    dem = dem_margin[1:-1, 1:-1]
    slope = slope_on_grid(dem_margin, CELL_M)
    write_raster(folder / "dem_m.tif", dem, grid, CELL_M, nodata=np.nan, description="Copernicus DEM GLO-30, bilinear (m)")
    write_raster(folder / "slope_deg.tif", slope, grid, CELL_M, nodata=np.nan, description="slope (degrees)")
    files["dem_m.tif"] = {"dtype": "float32", "nodata": "NaN", "units": "m (EGM2008)", "resampling": "bilinear from the "
                          "mosaic of the GLO-30 tiles", "statistics": describe(dem)}
    files["slope_deg.tif"] = {"dtype": "float32", "nodata": "NaN", "units": "degrees",
                              "method": "radar_candidates.slope_degrees (four neighbours, central differences) on "
                                        "dem_m.tif read with a margin of one cell",
                              "statistics": describe(slope),
                              "share_of_cells_at_5_degrees_or_more": round(float((slope >= 5).sum()) / slope.size, 6)}
    log(f"{name}: DEM and slope written")

    # HAND on the buffered 30 m window, then bilinear to the 20 m grid.
    layers, hydro_record, window_main = hydrology_hand(hydro_folder, mosaic, cover_paths, grid, buffer_m,
                                                       {"main": main_threshold_km2, "small": small_threshold_km2})
    log(f"{name}: flow routing on {window_main[2]} by {window_main[3]} cells took {hydro_record['flow_routing_seconds']} s")
    hand_30m = hydro_folder / f"hand_30m_buffer_{int(buffer_m)}m.tif"
    write_raster(hand_30m, layers["main"], window_main, HYDRO_CELL_M, nodata=np.nan,
                 description=f"HAND, streams of {main_threshold_km2} km2 or permanent water (m)")
    hydro_record["hand_file"] = hand_30m.name
    hydro_record["hand_sha256"] = sha256_file(hand_30m)
    window_transform = grid_transform(window_main, HYDRO_CELL_M)
    hand = warp_array(layers["main"], window_transform, f"EPSG:{EPSG}", np.nan, grid, CELL_M, resampling="bilinear",
                      dtype="float32", fill=np.nan)
    hand_small = warp_array(layers["small"], window_transform, f"EPSG:{EPSG}", np.nan, grid, CELL_M,
                            resampling="bilinear", dtype="float32", fill=np.nan)
    write_raster(folder / "hand_m.tif", hand, grid, CELL_M, nodata=np.nan, description="HAND, work package 4 method (m)")
    write_raster(folder / "hand_1km2_context_m.tif", hand_small, grid, CELL_M, nodata=np.nan,
                 description="HAND with 1 km2 streams, context only (m)")
    files["hand_m.tif"] = {"dtype": "float32", "nodata": "NaN", "units": "m",
                           "what": f"HAND with streams of at least {main_threshold_km2} km2 upstream or permanent water; "
                                   "the HAND of the protocol (method.hand)",
                           "resampling": "bilinear from the 30 m hydrology window", "statistics": describe(hand)}
    files["hand_1km2_context_m.tif"] = {"dtype": "float32", "nodata": "NaN", "units": "m",
                                        "what": f"HAND with streams of at least {small_threshold_km2} km2 upstream or "
                                                "permanent water (work package 4's hand_small_stream_m); context only, "
                                                "not the HAND of the protocol",
                                        "resampling": "bilinear from the 30 m hydrology window",
                                        "statistics": describe(hand_small)}
    # Which 20 m cells took their HAND from the straight-line rule (the 30 m cell nearest the cell centre).
    straight = {key: warp_array(layers[f"{key}_straight_line"], window_transform, f"EPSG:{EPSG}", 255, grid, CELL_M,
                                resampling="nearest", dtype="uint8", fill=255) for key in ("main", "small")}
    write_raster(folder / "hand_straight_line_rule.tif", straight["main"], grid, CELL_M, nodata=255,
                 description="1 where hand_m.tif came from the straight-line rule, 0 from the D8 flow path")
    files["hand_straight_line_rule.tif"] = {
        "dtype": "uint8", "nodata": 255,
        "values": {"1": "HAND of hand_m.tif from the straight-line rule (no resolved D8 path to a stream in the window)",
                   "0": "HAND from the D8 flow path"},
        "resampling": "nearest from the 30 m hydrology window",
        "share_of_cells": round(float((straight["main"] == 1).sum()) / straight["main"].size, 6)}
    files["hand_1km2_context_m.tif"]["share_of_cells_from_the_straight_line_rule"] = round(
        float((straight["small"] == 1).sum()) / straight["small"].size, 6)
    del layers, straight
    log(f"{name}: HAND written")

    edges: list[dict[str, Any]] = []
    for other_buffer_m in check_buffers_m:
        other_layers, other_record, other_window = hydrology_hand(hydro_folder, mosaic, cover_paths, grid, other_buffer_m,
                                                                  {"main": main_threshold_km2})
        other_transform = grid_transform(other_window, HYDRO_CELL_M)
        other = warp_array(other_layers["main"], other_transform, f"EPSG:{EPSG}", np.nan, grid, CELL_M,
                           resampling="bilinear", dtype="float32", fill=np.nan)
        other_straight = warp_array(other_layers["main_straight_line"], other_transform, f"EPSG:{EPSG}", 255, grid,
                                    CELL_M, resampling="nearest", dtype="uint8", fill=255)
        edges.append({**edge_check(hand, other, buffer_m, other_buffer_m, hand_cuts_m),
                      "other_window": {**{key: other_record[key] for key in ("west", "north", "rows", "cols", "buffer_m",
                                                                             "dem_file", "dem_sha256", "main_stream_cells",
                                                                             "main_cells_without_a_flow_path",
                                                                             "flow_routing_seconds")},
                                       "share_of_area_cells_from_the_straight_line_rule":
                                           round(float((other_straight == 1).sum()) / other_straight.size, 6)}})
        del other_layers, other, other_straight
        log(f"{name}: edge check against {int(other_buffer_m)} m done")
    del mosaic

    # WorldCover: nearest to the 10 m cells of the grid, then the most common class of each 20 m cell.
    fine = warp_files(cover_paths, fine_grid(grid), FINE_M, resampling="nearest", dtype="uint8", fill=WORLDCOVER_NODATA)
    cover = most_common_class(fine, FINE_FACTOR, WORLDCOVER_NODATA)
    fine_counts = class_counts(fine)
    del fine
    water = (cover == PERMANENT_WATER).astype("uint8")
    write_raster(folder / "worldcover.tif", cover, grid, CELL_M, nodata=WORLDCOVER_NODATA,
                 description="ESA WorldCover 2021 v200 class, most common 10 m class")
    write_raster(folder / "permanent_water.tif", water, grid, CELL_M, nodata=None,
                 description="1 where WorldCover 2021 class is 80, else 0")
    files["worldcover.tif"] = {"dtype": "uint8", "nodata": WORLDCOVER_NODATA, "units": "ESA WorldCover 2021 v200 class code",
                               "resampling": "nearest to the 10 m cells of the grid, then the most common class of the "
                                             "four 10 m cells (ties to the smallest code; no-data not counted)",
                               "cells_by_class": class_counts(cover), "ten_metre_cells_by_class": fine_counts}
    files["permanent_water.tif"] = {"dtype": "uint8", "nodata": None, "values": {"1": "WorldCover class 80", "0": "otherwise"},
                                    "cells": int(water.sum())}

    jrc: dict[str, Any]
    if jrc_found and not jrc_missing:
        occurrence = warp_files([external / record["path_under_external_root"] for record in jrc_found], grid, CELL_M,
                                resampling="nearest", dtype="uint8", fill=JRC_NODATA)
        write_raster(folder / "jrc_occurrence.tif", occurrence, grid, CELL_M, nodata=JRC_NODATA,
                     description="JRC GSW v1.4 occurrence 1984-2021 (percent)")
        valid = occurrence != JRC_NODATA
        files["jrc_occurrence.tif"] = {"dtype": "uint8", "nodata": JRC_NODATA, "units": "percent of valid observations "
                                       "with water, 1984-2021", "resampling": "nearest", "context_only": True,
                                       "valid_cells": int(valid.sum()),
                                       "cells_at_25_percent_or_more": int((valid & (occurrence >= 25)).sum())}
        jrc = {"tiles": jrc_found}
    else:
        jrc = {"tiles": jrc_found, "missing": jrc_missing,
               "skipped": "jrc_occurrence.tif was not written: not every JRC tile of the area could be had"}

    for file_name in files:
        check_alignment(folder / file_name, grid, CELL_M)
        files[file_name]["sha256"] = sha256_file(folder / file_name)

    west, south, east, north = grid_bounds(grid, CELL_M)
    record = {
        "schema": SCHEMA,
        "generated_at_utc": now_utc(),
        "source_timestamp": SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "Open global terrain and land-cover layers, not checked on the ground in this case; the DEM "
                            "is a surface model.",
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "lane": "terrain",
        "area": name,
        "role": entry.get("role"),
        **provenance,
        "grid": {"epsg": EPSG, "cell_m": CELL_M, "west": grid[0], "north": grid[1], "rows": grid[2], "cols": grid[3],
                 "east": east, "south": south, "rule": "north-up; (west, north, rows, cols) as in floodguard.s1_rtc.Grid",
                 "alignment_check": "every file below was reopened and found on this grid exactly"},
        "folder_under_external_root": folder.relative_to(external).as_posix(),
        "files": files,
        "sources": {
            "copernicus_dem_glo30": {"tiles": dem_found, "missing": dem_missing, "box_lonlat": [round(v, 6) for v in window_lonlat],
                                     "box_rule": "the hydrology window in lon/lat plus 0.01 degree, widened to whole pixels of the tiles before the merge",
                                     "kind": "digital surface model, 1 arc-second, heights on the EGM2008 geoid"},
            "esa_worldcover_2021_v200": {"tiles": cover_found, "missing": cover_missing},
            "jrc_global_surface_water_v1_4_occurrence": jrc,
        },
        "hand": {
            "method": "work package 4 (scripts/build_flood_susceptibility_model.py, stage_features, the feature "
                      "hand_main_stream_m of its baseline model), statements copied into hand_wp4 with the window passed in",
            "steps": [
                "mosaic the Copernicus DEM GLO-30 tiles over the window and resample bilinearly to a 30 m EPSG:32647 grid "
                "whose edges are whole multiples of 30 m (no-data -9999)",
                "pysheds 0.5: fill_pits, then fill_depressions, then resolve_flats",
                "flowdir (D8, pysheds defaults), then accumulation (cells upstream, the cell itself included)",
                f"stream = upstream area (cells x 900 m2) of at least {main_threshold_km2} km2, or WorldCover 2021 class 80 "
                "resampled to the 30 m grid by nearest cell (permanent water counts as a stream)",
                "compute_hand(direction, conditioned DEM, stream mask as a pysheds Raster): the height of each cell above "
                "the stream cell its D8 path reaches",
                "a cell whose HAND is not finite (no resolved flow path, or the window's border) gets its conditioned "
                "height minus that of the nearest stream cell by Euclidean distance (scipy distance_transform_edt)",
                "clip at zero; NaN where the DEM holds no value",
                "resample bilinearly from the 30 m window to the area's 20 m grid",
            ],
            "stream_threshold_km2": main_threshold_km2,
            "permanent_water_counts_as_stream": True,
            "routing": "D8",
            "dem_of_the_heights": "the conditioned DEM (after fill_pits, fill_depressions and resolve_flats), as in work package 4",
            "native_resolution": "30 m on EPSG:32647, the cell of work package 4 (GLO-30 is 1 arc-second, about 31 m by "
                                 "29 m at 18 degrees north)",
            "resampling_to_20m": "bilinear",
            "hydrology_window": hydro_record,
            "context_layer": f"hand_1km2_context_m.tif: the same flow routing with {small_threshold_km2} km2 streams",
            "buffer_choice": BUFFER_CHOICE,
            "differences_from_work_package_4": [
                "the window, its buffer and the stream thresholds are passed in instead of fixed to Mae Sai",
                "the merge box of the DEM tiles is widened to whole pixels of the tiles; work package 4 passed a box "
                "between pixel edges, which rasterio's merge re-grids by nearest cell with a shift of up to half a "
                "pixel (about 15 m)",
                "a window without any stream cell is refused instead of passed to the distance transform",
            ],
            "edge_checks": edges,
        },
        "libraries": libraries(),
        "credits": CREDITS,
        "assumptions": ASSUMPTIONS,
        "seconds": round(time.perf_counter() - clock, 1),
    }
    write_json(folder / "terrain_record.json", record)
    log(f"{name}: done in {record['seconds']} s")
    return record


def libraries() -> dict[str, str]:
    """Versions of the libraries that shape the layers."""

    import importlib.metadata

    import rasterio
    import scipy

    versions = {"python": sys.version.split()[0], "numpy": np.__version__, "scipy": scipy.__version__,
                "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__}
    try:
        versions["pysheds"] = importlib.metadata.version("pysheds")
    except importlib.metadata.PackageNotFoundError:
        versions["pysheds"] = "unknown"
    return versions


def provenance_of(root: Path) -> dict[str, Any]:
    """SHA-256 (as Git holds them) of the protocol, the areas file, this script and the work-package-4 script."""

    return {
        "protocol": {"path": PROTOCOL, "sha256": sha256_git_text(root / PROTOCOL)},
        "areas_file": {"path": AREAS, "sha256": sha256_git_text(root / AREAS)},
        "code": {"path": SCRIPT, "sha256": sha256_git_text(root / SCRIPT)},
        "hand_code_of_work_package_4": {"path": WP4_SCRIPT, "sha256": sha256_git_text(root / WP4_SCRIPT)},
    }


def ordered_areas(areas: Mapping[str, Any], chosen: Sequence[str] | None) -> list[str]:
    """The areas to build: the tuning areas first, then the rest (the Nan frame) in file order."""

    names = [name for name in TUNING_FIRST if name in areas] + [name for name in areas if name not in TUNING_FIRST]
    if chosen:
        unknown = sorted(set(chosen) - set(areas))
        if unknown:
            raise TerrainError(f"unknown areas: {', '.join(unknown)}")
        names = [name for name in names if name in chosen]
    return names


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-root", required=True)
    parser.add_argument("--areas", nargs="*", help="area keys of areas_v1.json (default: all, tuning areas first)")
    parser.add_argument("--buffer-m", type=float, default=BUFFER_M)
    parser.add_argument("--check-buffers-m", type=float, nargs="*", default=list(CHECK_BUFFERS_M),
                        help="other buffers whose HAND is set against the HAND of record; none skips the checks")
    parser.add_argument("--no-download", action="store_true", help="use tiles on disk only")
    parser.add_argument("--replace", action="store_true", help="rebuild an area whose record exists")
    arguments = parser.parse_args(argv)
    if arguments.buffer_m < MIN_BUFFER_M:
        raise TerrainError(f"the hydrology window must be buffered by at least {int(MIN_BUFFER_M)} m")
    external = Path(arguments.external_root)
    if not external.is_dir():
        raise TerrainError(f"{external} is not a folder")
    protocol = json.loads((ROOT / PROTOCOL).read_text(encoding="utf-8"))
    cuts = [float(value) for value in protocol["method"]["tuned_parameters"]["hand_max_m"]]
    areas = json.loads((ROOT / AREAS).read_text(encoding="utf-8"))["areas"]
    provenance = provenance_of(ROOT)
    index_path = external / WORK / "terrain_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"areas": {}}
    for name in ordered_areas(areas, arguments.areas):
        record_path = external / WORK / name / "terrain_record.json"
        if record_path.exists() and not arguments.replace:
            log(f"{name}: record exists, skipped (use --replace to rebuild)")
        else:
            build_area(external, name, areas[name], provenance=provenance, buffer_m=arguments.buffer_m,
                       check_buffers_m=arguments.check_buffers_m, hand_cuts_m=cuts,
                       allow_download=not arguments.no_download)
        index["areas"][name] = {"record": record_path.relative_to(external).as_posix(), "sha256": sha256_file(record_path)}
    index.update({
        "schema": "floodguard.nan_case_terrain_index.v1", "generated_at_utc": now_utc(),
        "source_timestamp": SOURCE_TIMESTAMP, "confidence_class": "low", "official_warning": False,
        "operational_status": "non_operational", **provenance,
        "assumptions": ["Each area's record holds its own sources, method and hashes; this index only lists them."],
    })
    write_json(index_path, index)


if __name__ == "__main__":
    try:
        main()
    except TerrainError as error:
        raise SystemExit(f"refused: {error}") from error
