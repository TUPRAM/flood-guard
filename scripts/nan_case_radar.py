"""Radar passes of the Nan case: catalogue listing, event passes and dry-season statistics on the 20 m grids.

The rules are those of ``docs/proposal_execution/nan_case_protocol_v1.json`` (sections ``grid`` and ``radar``);
the grids are those of ``outputs/nan_case/areas_v1.json``. Nothing here detects water or computes a flood flag:
the outputs are terrain-corrected backscatter values (gamma0) and their dry-season statistics.

Subcommands:

``list --area <id>``
    Searches the ``sentinel-1-rtc`` catalogue for the area, groups scenes into passes and writes
    ``outputs/nan_case/radar_passes_<area>_v1.json`` (metadata only, no tokens).

``fetch --area <id> --pass <key>``
    One event pass on the area's 20 m grid: the mean of linear gamma0 over the valid 10 m cells of each 20 m cell,
    no data where fewer than 3 are valid. Writes ``radar/<area>/event_<key>.tif`` (band 1 VV, band 2 VH) and a
    record beside it.

``drystats --area <id> --orbit <n>``
    The selected dry-season passes of one relative orbit, fetched one at a time by the same rule, streamed into
    per-cell count, sum and sum of squares of VH and VV dB per platform; writes ``radar/<area>/dry_o<n>.tif``
    (vh_mean_db, vh_std_db, vv_mean_db, vv_std_db, n_valid) with the protocol's sensor-agreement check.

``status --area <id>``
    Refreshes the status fields of the committed record from the work folder, without the network.

The work folder is ``<external data root>/proposal_execution/nan_case_v1/radar/``. Planning guidance only: no
output here is an official warning, and none is real-time.

Example::

    python scripts/nan_case_radar.py list --area sukhothai_chip --external-root <external-data-root>
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import s1_rtc  # noqa: E402

PROTOCOL = "docs/proposal_execution/nan_case_protocol_v1.json"
AREAS = "outputs/nan_case/areas_v1.json"
OUTPUT_DIR = "outputs/nan_case"
WORK = Path("proposal_execution") / "nan_case_v1" / "radar"
SEALED_NAMES = ("jaxa_sealed",)

EPSG = 32647
CELL_M = 20.0
FINE_M = 10.0
MIN_VALID_FINE = 3
PASS_GAP_S = 300.0
TUNING_MATCH_S = 600.0
DRY_CAP = 10
MIN_DRY_PASSES_FOR_THE_METHOD = 6
SENSOR_FLAG_DB = 0.5
THAI = timezone(timedelta(hours=7))
BAND_ROWS_FINE = 512
MIN_BLOCK_COLUMNS_FINE = 512
MIN_GROUP_ROWS_FINE = 1024
READ_TRIES = 6
DEFAULT_THREADS = 12

CELL_RULE = ("per polarisation, the mean of linear gamma0 over the valid 10 m cells (finite and above zero) of each "
             "20 m cell; a 20 m cell with fewer than 3 valid 10 m cells is no data (NaN)")
MOSAIC_RULE = ("at 10 m, before the 20 m mean: " + s1_rtc.MOSAIC_RULE
               + "; scenes listed by start time; checked per band of rows and column block")
DRY_RULE = ("a dry pass counts for a cell when both VV and VH hold a value there at 20 m; per cell, the mean and the "
            "population standard deviation of 10 log10(gamma0) over those passes, and their number")
SENSOR_RULE = ("for an orbit whose selected dry passes come from two platforms: the median, over cells with at least "
               "one valid pass of each platform, of (mean VH dB of the Sentinel-1A passes minus mean VH dB of the "
               "other platform's passes); flagged when its absolute value is above 0.5 dB; no correction is applied")
GROUPING_RULE = ("scenes of one platform and one relative orbit whose start times follow each other within 300 s form "
                 "one pass; a pass starts at its first scene's start")

GDAL_OPTIONS = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MAX_RETRY": "6", "GDAL_HTTP_RETRY_DELAY": "4",
                "GDAL_HTTP_TIMEOUT": "120", "GDAL_HTTP_CONNECTTIMEOUT": "30", "GDAL_INGESTED_BYTES_AT_OPEN": "32768"}
PROCESS_GDAL_OPTIONS = {"GDAL_CACHEMAX": "256", "CPL_VSIL_CURL_CACHE_SIZE": str(64 * 1024 * 1024)}

ASSUMPTIONS_COMMON = [
    "Values are terrain-corrected gamma0 (VV, VH) of the sentinel-1-rtc collection of Microsoft Planetary Computer, read anonymously with a short-lived token that is never recorded.",
    "Nothing here detects water or computes a flood flag; the files are inputs of the M1-z method of the protocol.",
    "A 20 m cell is the mean of the valid 10 m cells it holds, per polarisation, and no data with fewer than 3 of them (protocol, section grid).",
    "Scenes whose file is on the 10 m EPSG:32647 lattice of the grid are read as they are; a scene on another projection or lattice is first taken onto the 10 m lattice by nearest neighbour, and its record says so.",
    "Planning guidance only: not an official warning and not real-time.",
]


class RadarCaseError(RuntimeError):
    """A rule of the case cannot be applied as written."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def now_utc() -> str:
    """The current UTC time as ``YYYY-mm-ddTHH:MM:SSZ``."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text: str) -> datetime:
    """A catalogue time (``...Z``, ``...+00:00`` or with a space) as an aware UTC datetime."""

    value = datetime.fromisoformat(str(text).strip().replace(" ", "T").replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utc_text(value: datetime) -> str:
    """An aware datetime as ``YYYY-mm-ddTHH:MM:SSZ`` (seconds kept, fractions dropped)."""

    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def thai_text(value: datetime) -> str:
    """An aware datetime in Thai time (UTC+7) as ``YYYY-mm-ddTHH:MM:SS+07:00``."""

    return value.astimezone(THAI).strftime("%Y-%m-%dT%H:%M:%S+07:00")


def platform_name(raw: str | None) -> str:
    """``sentinel-1a`` or ``SENTINEL-1A`` as ``Sentinel-1A``."""

    text = str(raw or "").strip().lower()
    if not text.startswith("sentinel-1") or len(text) != len("sentinel-1a"):
        raise RadarCaseError(f"unknown platform {raw!r}")
    return "Sentinel-1" + text[-1].upper()


def platform_code(name: str) -> str:
    """``Sentinel-1A`` as ``s1a``."""

    return "s1" + platform_name(name)[-1].lower()


def pass_key(platform: str, relative_orbit: int, start: datetime) -> str:
    """The key of a pass: start minute in UTC, platform and relative orbit, e.g. ``20250728T1120Z_s1c_o99``."""

    return f"{start.astimezone(timezone.utc):%Y%m%dT%H%M}Z_{platform_code(platform)}_o{int(relative_orbit)}"


def write_json(path: Path, value: Any) -> None:
    """Write JSON with LF line ends and UTF-8, so a recorded SHA-256 matches the bytes Git holds."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, indent=1, ensure_ascii=False) + "\n")


def guard_path(path: Path) -> Path:
    """Refuse any path inside a sealed folder of the case (the firewall of the protocol)."""

    if any(part.lower() in SEALED_NAMES for part in Path(path).parts):
        raise RadarCaseError(f"{path} lies inside a sealed folder of the case")
    return Path(path)


def envelope(source_timestamp: str, confidence_class: str, assumptions: Sequence[str]) -> dict[str, Any]:
    """The fields every record of the case carries."""

    return {"generated_at_utc": now_utc(), "source_timestamp": source_timestamp, "confidence_class": confidence_class,
            "assumptions": list(assumptions), "official_warning": False, "operational_status": "non_operational"}


# ---------------------------------------------------------------------------
# Pure rules: passes, selection, the 20 m cell, the dry-season statistics
# ---------------------------------------------------------------------------


def scene_entry(feature: dict[str, Any]) -> dict[str, Any]:
    """The metadata of one catalogue scene that the case keeps (no asset address, no token)."""

    properties = feature["properties"]
    start = parse_utc(properties.get("start_datetime") or properties["datetime"])
    end = parse_utc(properties.get("end_datetime") or properties["datetime"])
    return {"item": feature["id"], "platform": platform_name(properties.get("platform")),
            "relative_orbit": int(properties["sat:relative_orbit"]), "orbit_state": properties.get("sat:orbit_state"),
            "start_utc": utc_text(start), "end_utc": utc_text(end), "datetime_utc": utc_text(parse_utc(properties["datetime"])),
            "proj_epsg": properties.get("proj:epsg"), "geometry": feature.get("geometry")}


def group_passes(scenes: Sequence[dict[str, Any]], *, gap_s: float = PASS_GAP_S) -> list[dict[str, Any]]:
    """Group scenes into passes: same platform and relative orbit, starts within ``gap_s`` of the previous scene.

    Each scene needs ``item``, ``platform``, ``relative_orbit`` and ``start_utc`` (``end_utc`` and ``orbit_state``
    are kept when present). Passes come back oldest first, each with its scenes in start order and its key.
    """

    ordered = sorted(scenes, key=lambda scene: (platform_name(scene["platform"]), int(scene["relative_orbit"]),
                                                 parse_utc(scene["start_utc"]), scene["item"]))
    groups: list[list[dict[str, Any]]] = []
    for scene in ordered:
        last = groups[-1][-1] if groups else None
        if (last is not None and platform_name(last["platform"]) == platform_name(scene["platform"])
                and int(last["relative_orbit"]) == int(scene["relative_orbit"])
                and (parse_utc(scene["start_utc"]) - parse_utc(last["start_utc"])).total_seconds() <= gap_s):
            if scene["item"] != last["item"]:
                groups[-1].append(scene)
            continue
        groups.append([scene])
    passes = []
    for members in groups:
        first = members[0]
        start = parse_utc(first["start_utc"])
        end = max(parse_utc(member.get("end_utc") or member["start_utc"]) for member in members)
        platform = platform_name(first["platform"])
        passes.append({"key": pass_key(platform, int(first["relative_orbit"]), start), "platform": platform,
                       "relative_orbit": int(first["relative_orbit"]), "orbit_state": first.get("orbit_state"),
                       "start_utc": utc_text(start), "end_utc": utc_text(end), "start_thai": thai_text(start),
                       "scenes": [{key: member[key] for key in ("item", "start_utc", "end_utc") if key in member}
                                  for member in members]})
    return sorted(passes, key=lambda entry: (entry["start_utc"], entry["key"]))


def passes_starting_between(passes: Sequence[dict[str, Any]], start: datetime, end: datetime) -> list[dict[str, Any]]:
    """The passes whose start lies in ``[start, end]``."""

    return [entry for entry in passes if start <= parse_utc(entry["start_utc"]) <= end]


def select_latest(passes: Sequence[dict[str, Any]], *, cap: int = DRY_CAP, relative_orbit: int | None = None) -> list[dict[str, Any]]:
    """The latest passes first, at most ``cap``; only those of ``relative_orbit`` when it is given."""

    if cap < 0:
        raise RadarCaseError("the cap cannot be negative")
    usable = [entry for entry in passes if relative_orbit is None or int(entry["relative_orbit"]) == int(relative_orbit)]
    return sorted(usable, key=lambda entry: parse_utc(entry["start_utc"]), reverse=True)[:cap]


def match_named_pass(passes: Sequence[dict[str, Any]], *, platform: str, relative_orbit: int, when: datetime,
                     tolerance_s: float = TUNING_MATCH_S) -> list[dict[str, Any]]:
    """The passes of one platform and orbit that start within ``tolerance_s`` of a named time."""

    return [entry for entry in passes if entry["platform"] == platform_name(platform)
            and int(entry["relative_orbit"]) == int(relative_orbit)
            and abs((parse_utc(entry["start_utc"]) - when).total_seconds()) <= tolerance_s]


def block_mean_2x2(fine: np.ndarray, *, min_valid: int = MIN_VALID_FINE) -> np.ndarray:
    """The 20 m cells of a 10 m array: the mean of its valid values in each 2 by 2 block.

    A value is valid when it is finite and above zero. A block with fewer than ``min_valid`` valid values is NaN.
    The array must have an even number of rows and columns. Returns float32.
    """

    values = np.asarray(fine)
    if values.ndim != 2 or values.shape[0] % 2 or values.shape[1] % 2:
        raise RadarCaseError("the 10 m array must be two-dimensional with an even number of rows and columns")
    rows, columns = values.shape[0] // 2, values.shape[1] // 2
    with np.errstate(invalid="ignore"):
        valid = np.isfinite(values) & (values > 0)
    total = np.where(valid, values, 0.0).astype("float64").reshape(rows, 2, columns, 2).sum(axis=(1, 3))
    count = valid.reshape(rows, 2, columns, 2).sum(axis=(1, 3))
    out = np.full((rows, columns), np.nan, dtype="float32")
    keep = count >= min_valid
    out[keep] = (total[keep] / count[keep]).astype("float32")
    return out


def to_db(linear: np.ndarray) -> np.ndarray:
    """10 log10 of linear gamma0 where it is finite and above zero, NaN elsewhere (float64)."""

    values = np.asarray(linear, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(np.isfinite(values) & (values > 0), 10.0 * np.log10(np.where(values > 0, values, 1.0)), np.nan)


class DryAccumulator:
    """Per-cell count, sum and sum of squares of VH dB and VV dB, kept separately for each platform.

    The arrays live in memory, or in ``folder`` as memory-mapped ``.npy`` files so a long run can be resumed and
    the whole frame never has to sit in memory. A pass counts for a cell when both polarisations hold a value.
    """

    FIELDS = ("n", "sum_vh", "sumsq_vh", "sum_vv", "sumsq_vv")

    def __init__(self, shape: tuple[int, int], platforms: Sequence[str], *, folder: Path | None = None,
                 resume: bool = False) -> None:
        self.shape = (int(shape[0]), int(shape[1]))
        self.platforms = sorted({platform_name(name) for name in platforms})
        if not self.platforms:
            raise RadarCaseError("an accumulator needs at least one platform")
        self.folder = Path(folder) if folder is not None else None
        self.arrays: dict[str, dict[str, np.ndarray]] = {}
        for platform in self.platforms:
            self.arrays[platform] = {}
            for field in self.FIELDS:
                dtype = "uint16" if field == "n" else "float64"
                if self.folder is None:
                    self.arrays[platform][field] = np.zeros(self.shape, dtype=dtype)
                    continue
                self.folder.mkdir(parents=True, exist_ok=True)
                path = self.folder / f"{platform_code(platform)}_{field}.npy"
                if resume:
                    array = np.load(path, mmap_mode="r+")
                    if array.shape != self.shape or array.dtype != np.dtype(dtype):
                        raise RadarCaseError(f"{path.name} does not fit the grid")
                else:
                    array = np.lib.format.open_memmap(path, mode="w+", dtype=dtype, shape=self.shape)
                    array[:] = 0
                self.arrays[platform][field] = array

    def add(self, platform: str, vh_linear: np.ndarray, vv_linear: np.ndarray, *, row0: int = 0) -> int:
        """Add one pass (or a strip of rows of it starting at ``row0``); returns the number of cells it counted in."""

        vh, vv = to_db(vh_linear), to_db(vv_linear)
        if vh.shape != vv.shape or vh.ndim != 2 or vh.shape[1] != self.shape[1] or row0 < 0 or row0 + vh.shape[0] > self.shape[0]:
            raise RadarCaseError("the strip does not fit the accumulator")
        both = np.isfinite(vh) & np.isfinite(vv)
        rows = slice(row0, row0 + vh.shape[0])
        target = self.arrays[platform_name(platform)]
        target["n"][rows] += both.astype("uint16")
        vh, vv = np.where(both, vh, 0.0), np.where(both, vv, 0.0)
        target["sum_vh"][rows] += vh
        target["sumsq_vh"][rows] += vh * vh
        target["sum_vv"][rows] += vv
        target["sumsq_vv"][rows] += vv * vv
        return int(both.sum())

    def flush(self) -> None:
        """Write memory-mapped arrays to disk."""

        for fields in self.arrays.values():
            for array in fields.values():
                if isinstance(array, np.memmap):
                    array.flush()

    def close(self) -> None:
        """Release memory-mapped arrays (they can then be deleted)."""

        self.flush()
        for fields in self.arrays.values():
            for array in fields.values():
                mapping = getattr(array, "_mmap", None)
                if mapping is not None:
                    mapping.close()
        self.arrays = {}

    def statistics(self, row0: int = 0, row1: int | None = None, *, platforms: Sequence[str] | None = None) -> dict[str, np.ndarray]:
        """Mean and population standard deviation (dB) of VH and VV and the count, over the given platforms.

        Cells without a valid pass are NaN in every band but ``n_valid`` (which is 0 there).
        """

        rows = slice(row0, self.shape[0] if row1 is None else row1)
        chosen = self.platforms if platforms is None else [platform_name(name) for name in platforms]
        totals = {field: sum(self.arrays[platform][field][rows].astype("float64") for platform in chosen)
                  for field in self.FIELDS}
        count = totals["n"]
        seen = count > 0
        out: dict[str, np.ndarray] = {"n_valid": count}
        with np.errstate(invalid="ignore", divide="ignore"):
            for band in ("vh", "vv"):
                mean = np.where(seen, totals[f"sum_{band}"] / np.where(seen, count, 1.0), np.nan)
                variance = np.where(seen, totals[f"sumsq_{band}"] / np.where(seen, count, 1.0) - mean * mean, np.nan)
                out[f"{band}_mean_db"] = mean
                out[f"{band}_std_db"] = np.sqrt(np.clip(variance, 0.0, None))
        return out


def sensor_difference(first_mean_db: np.ndarray, second_mean_db: np.ndarray, *,
                      flag_db: float = SENSOR_FLAG_DB) -> dict[str, Any]:
    """The median over cells valid in both of (first minus second), its quartiles and the flag of the protocol."""

    difference = np.asarray(first_mean_db, dtype="float64") - np.asarray(second_mean_db, dtype="float64")
    return difference_summary(difference[np.isfinite(difference)], flag_db=flag_db)


def difference_summary(values: np.ndarray, *, flag_db: float = SENSOR_FLAG_DB) -> dict[str, Any]:
    """Median and quartiles of per-cell differences (dB) and whether the absolute median is above ``flag_db``."""

    values = np.asarray(values, dtype="float64").ravel()
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"cells_valid_in_both": 0, "median_db": None, "p25_db": None, "p75_db": None, "flagged": None,
                "flag_abs_median_above_db": flag_db}
    median = float(np.median(values))
    return {"cells_valid_in_both": int(values.size), "median_db": round(median, 4),
            "p25_db": round(float(np.percentile(values, 25)), 4), "p75_db": round(float(np.percentile(values, 75)), 4),
            "flag_abs_median_above_db": flag_db, "flagged": bool(abs(median) > flag_db)}


def column_blocks(columns: int, parts: int) -> list[tuple[int, int]]:
    """Split ``columns`` (even) into at most ``parts`` contiguous blocks with even edges."""

    if columns <= 0 or columns % 2:
        raise RadarCaseError("the number of 10 m columns must be positive and even")
    parts = max(1, min(int(parts), columns // 2))
    pairs = columns // 2
    edges = [2 * round(pairs * index / parts) for index in range(parts + 1)]
    return [(edges[index], edges[index + 1]) for index in range(parts) if edges[index + 1] > edges[index]]


def read_tasks(rows: int, columns: int, threads: int) -> list[tuple[int, int, int, int]]:
    """Tasks of a 10 m grid as (row0, row1, col0, col1): column blocks of at least 512 columns, rows split if threads remain."""

    if rows <= 0 or rows % 2:
        raise RadarCaseError("the number of 10 m rows must be positive and even")
    blocks = column_blocks(columns, max(1, min(threads, columns // MIN_BLOCK_COLUMNS_FINE)))
    groups = column_blocks(rows, max(1, min(max(1, threads // len(blocks)), rows // MIN_GROUP_ROWS_FINE)))
    return [(r0, r1, c0, c1) for r0, r1 in groups for c0, c1 in blocks]


# ---------------------------------------------------------------------------
# Areas, grids and the catalogue
# ---------------------------------------------------------------------------


def load_areas() -> dict[str, dict[str, Any]]:
    """The areas of ``outputs/nan_case/areas_v1.json``."""

    return json.loads((ROOT / AREAS).read_text(encoding="utf-8"))["areas"]


def area_grid(area: dict[str, Any]) -> s1_rtc.Grid:
    """The 20 m grid of an area as (west, north, rows, cols)."""

    grid = area["grid"]
    return (float(grid["west"]), float(grid["north"]), int(grid["rows"]), int(grid["cols"]))


def fine_grid(grid: s1_rtc.Grid) -> s1_rtc.Grid:
    """The 10 m lattice of a 20 m grid: same corner, twice the rows and columns."""

    west, north, rows, columns = grid
    return (west, north, 2 * rows, 2 * columns)


def grid_polygon_lonlat(grid: s1_rtc.Grid, *, cell_m: float = CELL_M, points_per_side: int = 10) -> dict[str, Any]:
    """The outline of a grid in lon/lat as a GeoJSON polygon, densified along each side."""

    from pyproj import Transformer

    west, north, rows, columns = grid
    east, south = west + columns * cell_m, north - rows * cell_m
    to_lonlat = Transformer.from_crs(EPSG, 4326, always_xy=True).transform
    corners = [(west, north), (east, north), (east, south), (west, south), (west, north)]
    ring = []
    for (x0, y0), (x1, y1) in zip(corners[:-1], corners[1:]):
        for step in range(points_per_side):
            x, y = to_lonlat(x0 + (x1 - x0) * step / points_per_side, y0 + (y1 - y0) * step / points_per_side)
            ring.append([round(x, 6), round(y, 6)])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def footprint_share(geometries: Sequence[dict[str, Any]], grid: s1_rtc.Grid) -> float | None:
    """The share of the grid's area inside the union of scene footprints (lon/lat GeoJSON)."""

    from pyproj import Transformer
    from shapely import make_valid
    from shapely.geometry import box, shape
    from shapely.ops import transform, unary_union

    to_utm = Transformer.from_crs(4326, EPSG, always_xy=True).transform
    # Some catalogue footprints self-intersect, before or after projection: each is repaired on both sides.
    shapes = [make_valid(transform(to_utm, make_valid(shape(geometry)))) for geometry in geometries if geometry]
    if not shapes:
        return None
    west, north, rows, columns = grid
    frame = box(west, north - rows * CELL_M, west + columns * CELL_M, north)
    footprint = make_valid(unary_union([part.intersection(frame) for part in shapes]))
    return round(float(footprint.area / frame.area), 4)


def search_scenes(geometry: dict[str, Any], start: str, end: str, *, relative_orbit: int | None = None) -> list[dict[str, Any]]:
    """Every scene of the collection that intersects ``geometry`` with a catalogue time in [start, end], all pages."""

    body: dict[str, Any] = {"collections": [s1_rtc.COLLECTION], "intersects": geometry, "datetime": f"{start}/{end}",
                            "limit": 200}
    if relative_orbit is not None:
        body["query"] = {"sat:relative_orbit": {"eq": int(relative_orbit)}}
    features: list[dict[str, Any]] = []
    url, payload = s1_rtc.STAC_SEARCH, body
    for _page in range(50):
        page = s1_rtc.fetch_json(url, body=payload)
        features.extend(page.get("features", []))
        following = [link for link in page.get("links", []) if link.get("rel") == "next"]
        if not following:
            break
        link = following[0]
        url = link["href"]
        payload = {**payload, **link["body"]} if link.get("body") else None
    seen: dict[str, dict[str, Any]] = {}
    for feature in features:
        seen.setdefault(feature["id"], feature)
    return [scene_entry(feature) for feature in seen.values()]


class CatalogueResolver:
    """Resolves scene ids to signed asset addresses; the item is asked once, the token renewed after 25 minutes."""

    TOKEN_AGE_S = 25 * 60

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: str | None = None
        self._token_time = 0.0
        self._items: dict[str, dict[str, Any]] = {}

    def refresh(self) -> None:
        """Forget the token, so the next call asks for a new one."""

        with self._lock:
            self._token = None

    def __call__(self, item_id: str) -> dict[str, Any]:
        with self._lock:
            if self._token is None or time.time() - self._token_time > self.TOKEN_AGE_S:
                self._token = s1_rtc.fetch_json(s1_rtc.SAS_TOKEN)["token"]
                self._token_time = time.time()
            token = self._token
            if item_id not in self._items:
                self._items[item_id] = s1_rtc.fetch_json(s1_rtc.STAC_ITEMS + item_id)
            item = self._items[item_id]
        properties = item["properties"]
        return {"datetime": properties["datetime"], "platform": properties.get("platform"),
                "relative_orbit": properties.get("sat:relative_orbit"), "orbit_state": properties.get("sat:orbit_state"),
                "assets": {band: f"{item['assets'][band]['href']}?{token}" for band in s1_rtc.BANDS}}


# ---------------------------------------------------------------------------
# Reading one pass onto a 20 m grid
# ---------------------------------------------------------------------------


def scene_layout(href: str, grid10: s1_rtc.Grid) -> dict[str, Any]:
    """How a scene file sits on the 10 m lattice: read as it is (``aligned``) or taken by nearest neighbour."""

    import rasterio

    west, north, rows, columns = grid10
    with rasterio.Env(**GDAL_OPTIONS):
        with rasterio.open(href) as source:
            epsg = source.crs.to_epsg() if source.crs is not None else None
            transform = source.transform
            if epsg == EPSG and transform.b == 0 and transform.d == 0 and abs(transform.a - FINE_M) < 1e-9 \
                    and abs(transform.e + FINE_M) < 1e-9:
                column = (west - transform.c) / FINE_M
                row = (transform.f - north) / FINE_M
                if abs(column - round(column)) < 1e-6 and abs(row - round(row)) < 1e-6:
                    return {"method": "aligned", "crs": f"EPSG:{epsg}", "row_off": int(round(row)),
                            "col_off": int(round(column)), "height": source.height, "width": source.width}
            return {"method": "nearest_neighbour_onto_the_10m_lattice", "crs": f"EPSG:{epsg}" if epsg else str(source.crs),
                    "row_off": 0, "col_off": 0, "height": rows, "width": columns}


def layout_window(layout: dict[str, Any], r0: int, r1: int, c0: int, c1: int) -> tuple[int, int, int, int] | None:
    """The part of grid rows [r0, r1) and columns [c0, c1) that the scene's file covers, or None."""

    top, bottom = max(r0, -layout["row_off"]), min(r1, layout["height"] - layout["row_off"])
    left, right = max(c0, -layout["col_off"]), min(c1, layout["width"] - layout["col_off"])
    if bottom <= top or right <= left:
        return None
    return top, bottom, left, right


class _SceneHandle:
    """One open scene band for one reading thread (a plain dataset, or a nearest-neighbour warped view)."""

    def __init__(self, href: str, layout: dict[str, Any], grid10: s1_rtc.Grid) -> None:
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.transform import from_origin
        from rasterio.vrt import WarpedVRT

        self.layout = layout
        self.source = rasterio.open(href)
        self.view: Any = None
        if layout["method"] != "aligned":
            west, north, rows, columns = grid10
            nodata = self.source.nodata if self.source.nodata is not None else float("nan")
            self.view = WarpedVRT(self.source, crs=f"EPSG:{EPSG}", transform=from_origin(west, north, FINE_M, FINE_M),
                                  width=columns, height=rows, resampling=Resampling.nearest,
                                  src_nodata=self.source.nodata, nodata=nodata)

    def read(self, top: int, bottom: int, left: int, right: int) -> np.ndarray:
        from rasterio.windows import Window

        if self.view is not None:
            block = self.view.read(1, window=Window(left, top, right - left, bottom - top))
        else:
            block = self.source.read(1, window=Window(left + self.layout["col_off"], top + self.layout["row_off"],
                                                      right - left, bottom - top))
        block = block.astype("float32")
        with np.errstate(invalid="ignore"):
            block[~(np.isfinite(block) & (block > 0))] = np.nan
        return block

    def close(self) -> None:
        if self.view is not None:
            self.view.close()
        self.source.close()


def _read_task(task: tuple[int, int, int, int], items: Sequence[str], layouts: Sequence[dict[str, Any]],
               grid10: s1_rtc.Grid, out20: np.ndarray, resolve: s1_rtc.Resolver, reads: list[list[int]],
               progress: Callable[[int, int], None]) -> None:
    """Read one block of the 10 m grid in bands of rows, mosaic its scenes, and write its 20 m cells."""

    import rasterio

    r0, r1, c0, c1 = task
    handles: dict[tuple[int, str], _SceneHandle] = {}

    def handle(index: int, band: str) -> _SceneHandle:
        if (index, band) not in handles:
            handles[(index, band)] = _SceneHandle(resolve(items[index])["assets"][band], layouts[index], grid10)
        return handles[(index, band)]

    def read(index: int, band: str, window: tuple[int, int, int, int]) -> np.ndarray:
        for attempt in range(READ_TRIES):
            try:
                return handle(index, band).read(*window)
            except Exception:  # noqa: BLE001 - the host drops connections now and then: reopen with a new token
                stale = handles.pop((index, band), None)
                if stale is not None:
                    try:
                        stale.close()
                    except Exception:  # noqa: BLE001
                        pass
                if attempt == READ_TRIES - 1:
                    raise
                refresh = getattr(resolve, "refresh", None)
                if refresh is not None:
                    refresh()
                time.sleep(min(60, 5 * (attempt + 1)))
        raise RadarCaseError("unreachable")

    try:
        with rasterio.Env(**GDAL_OPTIONS):
            for top in range(r0, r1, BAND_ROWS_FINE):
                bottom = min(r1, top + BAND_ROWS_FINE)
                fine = np.full((len(s1_rtc.BANDS), bottom - top, c1 - c0), np.nan, dtype="float32")
                for index, layout in enumerate(layouts):
                    if np.isfinite(fine).all():
                        break
                    window = layout_window(layout, top, bottom, c0, c1)
                    if window is None:
                        continue
                    wt, wb, wl, wr = window
                    for band_index, band in enumerate(s1_rtc.BANDS):
                        held = fine[band_index, wt - top:wb - top, wl - c0:wr - c0]
                        if np.isfinite(held).all():
                            continue
                        block = read(index, band, window)
                        progress(index, band_index)
                        fine[band_index, wt - top:wb - top, wl - c0:wr - c0] = np.where(np.isfinite(held), held, block)
                for band_index in range(len(s1_rtc.BANDS)):
                    out20[band_index, top // 2:bottom // 2, c0 // 2:c1 // 2] = block_mean_2x2(fine[band_index])
                progress(-1, -1)
    finally:
        for opened in handles.values():
            try:
                opened.close()
            except Exception:  # noqa: BLE001
                pass


def read_pass_20m(grid: s1_rtc.Grid, items: Sequence[str], *, resolve: s1_rtc.Resolver,
                  threads: int = DEFAULT_THREADS, log: Callable[[str], None] | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    """One pass on a 20 m grid: VV and VH (linear, float32, NaN no data) by the cell and mosaic rules of the case.

    Returns the ``(2, rows, cols)`` array and the reading details: the layout of each scene and how many blocks
    of it were read.
    """

    if not items:
        raise RadarCaseError("a pass needs at least one scene")
    grid10 = fine_grid(grid)
    _west, _north, rows10, columns10 = grid10
    layouts = []
    for item_id in items:
        for attempt in range(READ_TRIES):
            try:
                assets = resolve(item_id)["assets"]
                both = [scene_layout(assets[band], grid10) for band in s1_rtc.BANDS]
                if any(layout != both[0] for layout in both[1:]):
                    raise RadarCaseError(f"the VV and VH files of {item_id} are not on one lattice")
                layouts.append(both[0])
                break
            except RadarCaseError:
                raise
            except Exception:  # noqa: BLE001 - retried with a new token, then raised
                if attempt == READ_TRIES - 1:
                    raise
                refresh = getattr(resolve, "refresh", None)
                if refresh is not None:
                    refresh()
                time.sleep(min(60, 5 * (attempt + 1)))
    tasks = read_tasks(rows10, columns10, threads)
    out20 = np.full((len(s1_rtc.BANDS), rows10 // 2, columns10 // 2), np.nan, dtype="float32")
    reads = [[0] * len(s1_rtc.BANDS) for _ in items]
    total = sum(-(-(r1 - r0) // BAND_ROWS_FINE) for r0, r1, _c0, _c1 in tasks)
    done = {"bands": 0, "reported": 0}
    lock = threading.Lock()

    def progress(index: int, band_index: int) -> None:
        with lock:
            if index >= 0:
                reads[index][band_index] += 1
                return
            done["bands"] += 1
            tenth = 10 * done["bands"] // total
            if log is not None and tenth > done["reported"]:
                done["reported"] = tenth
                log(f"  {10 * tenth}% of the bands read")

    with ThreadPoolExecutor(max(1, len(tasks))) as pool:
        futures = [pool.submit(_read_task, task, items, layouts, grid10, out20, resolve, reads, progress) for task in tasks]
        for future in futures:
            future.result()
    details = {"scenes": [{"item": item_id, "read_method": layout["method"], "file_crs": layout["crs"],
                           "blocks_read": {band: reads[index][band_index] for band_index, band in enumerate(s1_rtc.BANDS)}}
                          for index, (item_id, layout) in enumerate(zip(items, layouts))],
               "reading_tasks": len(tasks)}
    return out20, details


def write_raster(path: Path, bands: Sequence[np.ndarray], grid: s1_rtc.Grid, descriptions: Sequence[str]) -> None:
    """Write float32 bands on a 20 m grid: tiled, DEFLATE-compressed GeoTIFF, NaN no data, band descriptions."""

    import rasterio
    from rasterio.transform import from_origin

    west, north, rows, columns = grid
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=rows, width=columns, count=len(bands), dtype="float32",
                       nodata=float("nan"), crs=f"EPSG:{EPSG}", transform=from_origin(west, north, CELL_M, CELL_M),
                       tiled=True, blockxsize=256, blockysize=256, compress="deflate", predictor=3,
                       BIGTIFF="IF_SAFER") as target:
        for index, (band, description) in enumerate(zip(bands, descriptions), start=1):
            target.write(np.asarray(band, dtype="float32"), index)
            target.set_band_description(index, description)


def valid_shares(image: np.ndarray) -> dict[str, float]:
    """Share of grid cells with a value: VV, VH and both."""

    finite = np.isfinite(image)
    return {"vv": round(float(finite[0].mean()), 6), "vh": round(float(finite[1].mean()), 6),
            "both": round(float(finite.all(axis=0).mean()), 6)}


def fetch_pass_file(folder: Path, area_id: str, grid: s1_rtc.Grid, entry: dict[str, Any], name: str, *,
                    resolve: s1_rtc.Resolver, threads: int = DEFAULT_THREADS, role: str = "event",
                    replace: bool = False, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Fetch one pass to ``<folder>/<name>.tif`` with its record ``<name>.json``; an existing pair is reused."""

    folder = guard_path(folder)
    path, record_path = folder / f"{name}.tif", folder / f"{name}.json"
    if path.exists() and record_path.exists() and not replace:
        return json.loads(record_path.read_text(encoding="utf-8"))
    started = time.perf_counter()
    items = [scene["item"] for scene in entry["scenes"]]
    image, details = read_pass_20m(grid, items, resolve=resolve, threads=threads, log=log)
    write_raster(path, list(image), grid, ["gamma0 VV, linear", "gamma0 VH, linear"])
    seconds = round(time.perf_counter() - started, 1)
    west, north, rows, columns = grid
    record = {
        "schema": "floodguard.nan_case_radar_pass.v1",
        **envelope(f"Sentinel-1 pass starting {entry['start_utc']} ({entry['start_thai']} Thai time)",
                   "not applicable (backscatter values; nothing is detected here)", ASSUMPTIONS_COMMON),
        "protocol": PROTOCOL, "area": area_id, "role": role, "pass": entry["key"], "platform": entry["platform"],
        "relative_orbit": entry["relative_orbit"], "orbit_state": entry.get("orbit_state"),
        "start_utc": entry["start_utc"], "end_utc": entry["end_utc"], "start_thai": entry["start_thai"],
        "scenes": [{**scene, **detail} for scene, detail in zip(entry["scenes"], details["scenes"])],
        "grid": {"epsg": EPSG, "cell_m": CELL_M, "west": west, "north": north, "rows": rows, "cols": columns},
        "bands": ["gamma0 VV, linear", "gamma0 VH, linear"], "nodata": "NaN",
        "cell_rule": CELL_RULE, "mosaic_rule": MOSAIC_RULE, "valid_share": valid_shares(image),
        "file": path.name, "sha256": s1_rtc.sha256_file(path), "seconds": seconds, "threads": threads,
        "reading_tasks": details["reading_tasks"],
    }
    write_json(record_path, record)
    return record


# ---------------------------------------------------------------------------
# The committed record and its statuses
# ---------------------------------------------------------------------------


def record_path(area_id: str) -> Path:
    """``outputs/nan_case/radar_passes_<area>_v1.json``."""

    return ROOT / OUTPUT_DIR / f"radar_passes_{area_id}_v1.json"


def work_folder(external_root: str | Path, area_id: str) -> Path:
    """``<external>/proposal_execution/nan_case_v1/radar/<area>/``."""

    return guard_path(Path(external_root) / WORK / area_id)


def dry_window(area: dict[str, Any]) -> tuple[datetime, datetime]:
    """The dry-season window of an area in UTC: from the start date's 00:00:00 to the end date's 23:59:59."""

    season = area["dry_season"]
    return (parse_utc(season["start"] + "T00:00:00Z"), parse_utc(season["end"] + "T23:59:59Z"))


def pass_status(folder: Path, name: str) -> dict[str, Any]:
    """The status of an event pass in the work folder."""

    record_file, failed_file = folder / f"{name}.json", folder / f"{name}.failed.json"
    if record_file.exists() and (folder / f"{name}.tif").exists():
        record = json.loads(record_file.read_text(encoding="utf-8"))
        return {"status": "fetched", "file": record["file"], "sha256": record["sha256"], "valid_share": record["valid_share"],
                "seconds": record["seconds"], "fetched_at_utc": record["generated_at_utc"]}
    if failed_file.exists():
        failure = json.loads(failed_file.read_text(encoding="utf-8"))
        return {"status": "failed", "reason": failure.get("reason"), "failed_at_utc": failure.get("generated_at_utc")}
    return {"status": "not fetched yet"}


def dry_status(folder: Path, orbit: int) -> dict[str, Any]:
    """The status of the dry-season statistics of one orbit in the work folder."""

    name = f"dry_o{orbit}"
    record_file, state_file = folder / f"{name}.json", folder / f"{name}_partial" / "state.json"
    if record_file.exists() and (folder / f"{name}.tif").exists():
        record = json.loads(record_file.read_text(encoding="utf-8"))
        return {"status": "computed", "file": record["file"], "sha256": record["sha256"],
                "passes_used": [entry["key"] for entry in record["passes_used"]],
                "share_of_cells_with_at_least_6_valid_passes": record["share_of_cells_with_at_least_6_valid_passes"],
                "sensor_agreement": record["sensor_agreement"], "seconds": record["seconds"],
                "computed_at_utc": record["generated_at_utc"]}
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        return {"status": f"in progress ({len(state.get('added', []))} of {len(state.get('selected', []))} passes added)"}
    if (folder / f"{name}.failed.json").exists():
        failure = json.loads((folder / f"{name}.failed.json").read_text(encoding="utf-8"))
        return {"status": "failed", "reason": failure.get("reason"), "failed_at_utc": failure.get("generated_at_utc")}
    return {"status": "not computed yet"}


@contextmanager
def file_lock(path: Path, *, wait_s: float = 300.0) -> Iterator[None]:
    """A lock file created exclusively; a lock older than ten minutes is taken as stale."""

    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + wait_s
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > 600:
                    path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.time() > deadline:
                raise RadarCaseError(f"{path} is held by another process")
            time.sleep(0.5)
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


STATUS_KEYS = ("status", "file", "sha256", "valid_share", "seconds", "fetched_at_utc", "reason", "failed_at_utc")


def refresh_record(area_id: str, external_root: str | Path) -> dict[str, Any]:
    """Re-read the statuses of the committed record from the work folder and write it again."""

    folder = work_folder(external_root, area_id)
    path = record_path(area_id)
    with file_lock(folder / ".record.lock"):
        record = json.loads(path.read_text(encoding="utf-8"))
        for entry in record["event_passes"]:
            for key in STATUS_KEYS:
                entry.pop(key, None)
            entry.update(pass_status(folder, f"event_{entry['key']}"))
        for orbit, block in record["dry_season"]["by_orbit"].items():
            block["statistics"] = dry_status(folder, int(orbit))
        counts: dict[str, int] = {}
        for entry in record["event_passes"]:
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        record["status_summary"] = {"event_passes": counts,
                                    "dry_orbits": {orbit: block["statistics"]["status"] for orbit, block in record["dry_season"]["by_orbit"].items()},
                                    "refreshed_at_utc": now_utc()}
        write_json(path, record)
    return record


def load_record(area_id: str) -> dict[str, Any]:
    """The committed pass record of an area; ``list`` must have run."""

    path = record_path(area_id)
    if not path.exists():
        raise RadarCaseError(f"{path.relative_to(ROOT)} does not exist: run the list subcommand first")
    return json.loads(path.read_text(encoding="utf-8"))


def find_pass(record: dict[str, Any], key: str) -> dict[str, Any]:
    """An event pass of the record by key, by a unique prefix, or ``event`` when the record holds one only."""

    passes = record["event_passes"]
    if key == "event" and len(passes) == 1:
        return passes[0]
    exact = [entry for entry in passes if entry["key"] == key]
    if exact:
        return exact[0]
    prefixed = [entry for entry in passes if entry["key"].startswith(key)]
    if len(prefixed) == 1:
        return prefixed[0]
    raise RadarCaseError(f"no single event pass matches {key!r}; known: {[entry['key'] for entry in passes]}")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def logger(prefix: str) -> Callable[[str], None]:
    """A printer that stamps each line with the UTC time."""

    def log(message: str) -> None:
        print(f"{now_utc()} {prefix} {message}", flush=True)

    return log


def strip_geometry(entry: dict[str, Any]) -> dict[str, Any]:
    """A pass without the footprints used only to compute its share of the grid."""

    return {key: value for key, value in entry.items() if key != "geometries"}


def with_footprints(passes: list[dict[str, Any]], scenes: Sequence[dict[str, Any]], grid: s1_rtc.Grid) -> list[dict[str, Any]]:
    """Add the share of the grid inside each pass's scene footprints."""

    by_item = {scene["item"]: scene for scene in scenes}
    for entry in passes:
        geometries = [by_item[scene["item"]]["geometry"] for scene in entry["scenes"] if by_item[scene["item"]].get("geometry")]
        entry["footprint_share_of_grid"] = footprint_share(geometries, grid)
        for scene in entry["scenes"]:
            scene["file_epsg_in_catalogue"] = by_item[scene["item"]].get("proj_epsg")
    return passes


def command_list(arguments: argparse.Namespace) -> None:
    """Search the catalogue for an area and write its pass record."""

    log = logger(f"[list {arguments.area}]")
    areas = load_areas()
    if arguments.area not in areas:
        raise RadarCaseError(f"unknown area {arguments.area!r}; known: {sorted(areas)}")
    area = areas[arguments.area]
    grid = area_grid(area)
    polygon = grid_polygon_lonlat(grid)
    searched_at = now_utc()
    pad = timedelta(hours=1)
    problems: list[str] = []
    if "window_utc" in area["event"]:
        start, end = (parse_utc(text) for text in area["event"]["window_utc"])
        scenes = search_scenes(polygon, utc_text(start - pad), utc_text(end + pad))
        event_passes = passes_starting_between(group_passes(scenes), start, end)
        event_rule = "every pass of the collection that intersects the grid and starts inside the event window"
        event_source = f"event window {utc_text(start)} to {utc_text(end)}"
    else:
        named = area["event"]
        when = parse_utc(named["pass_utc"] + ":00Z" if len(named["pass_utc"]) == 16 else named["pass_utc"])
        scenes = search_scenes(polygon, utc_text(when - timedelta(days=1)), utc_text(when + timedelta(days=1)),
                               relative_orbit=int(named["relative_orbit"]))
        event_passes = match_named_pass(group_passes(scenes), platform=named["platform"],
                                        relative_orbit=int(named["relative_orbit"]), when=when)
        event_rule = (f"the one pass named in {AREAS}: {named['platform']}, relative orbit {named['relative_orbit']}, "
                      f"starting within {int(TUNING_MATCH_S)} s of {named['pass_utc']} UTC")
        event_source = f"named event pass {named['pass_utc']} UTC"
        if len(event_passes) != 1:
            problems.append(f"{len(event_passes)} passes match the named event pass")
    with_footprints(event_passes, scenes, grid)
    log(f"{len(event_passes)} event passes")
    window = dry_window(area)
    by_orbit: dict[str, Any] = {}
    for orbit in sorted({entry["relative_orbit"] for entry in event_passes}):
        dry_scenes = search_scenes(polygon, utc_text(window[0] - pad), utc_text(window[1] + pad), relative_orbit=orbit)
        found = passes_starting_between(group_passes(dry_scenes), *window)
        with_footprints(found, dry_scenes, grid)
        selected = select_latest(found, cap=DRY_CAP, relative_orbit=orbit)
        platforms = sorted({entry["platform"] for entry in selected})
        by_orbit[str(orbit)] = {
            "passes_found": [strip_geometry(entry) for entry in found],
            "selected_latest_first": [entry["key"] for entry in selected],
            "selected_platforms": {name: sum(1 for entry in selected if entry["platform"] == name) for name in platforms},
            "sensor_agreement_check_applies": len(platforms) >= 2,
            "fewer_than_the_cap": len(selected) < DRY_CAP,
        }
        if len(selected) < MIN_DRY_PASSES_FOR_THE_METHOD:
            problems.append(f"orbit {orbit}: only {len(selected)} dry passes, fewer than the {MIN_DRY_PASSES_FOR_THE_METHOD} the method needs per cell")
        log(f"orbit {orbit}: {len(found)} dry passes found, {len(selected)} selected")
    west, north, rows, columns = grid
    assumptions = [
        "Scenes are those of the sentinel-1-rtc catalogue whose footprint intersects the grid's outline (lon/lat, 10 points per side); catalogue holes are not filled from elsewhere.",
        GROUPING_RULE[0].upper() + GROUPING_RULE[1:] + ".",
        "A pass belongs to a window when its start (UTC) lies inside it; the dry season runs from the start date 00:00:00 UTC to the end date 23:59:59 UTC.",
        "Dry-season passes: the latest of the window first, at most 10, of the relative orbit of each event pass, from every platform the catalogue holds.",
        "footprint_share_of_grid is the share of the grid inside the union of the pass's scene footprints as the catalogue gives them; it is not the share of valid values.",
        "Metadata only: no asset address and no token is recorded.",
    ]
    record = {
        "schema": "floodguard.nan_case_radar_passes.v1",
        **envelope(f"catalogue searched {searched_at}; {event_source}; dry season {area['dry_season']['start']} to {area['dry_season']['end']}",
                   "not applicable (catalogue metadata)", assumptions),
        "protocol": PROTOCOL, "areas_file": AREAS, "area": arguments.area, "role": area.get("role"),
        "grid": {"epsg": EPSG, "cell_m": CELL_M, "west": west, "north": north, "rows": rows, "cols": columns},
        "catalogue": {"collection": s1_rtc.COLLECTION, "search": s1_rtc.STAC_SEARCH, "searched_at_utc": searched_at,
                      "intersects": "the grid outline in lon/lat (EPSG:4326), 10 points per side",
                      "grouping_rule": GROUPING_RULE},
        "event": {"rule": event_rule, **({"window_utc": area["event"]["window_utc"]} if "window_utc" in area["event"]
                                         else {"named_pass": area["event"]})},
        "event_passes": [strip_geometry(entry) for entry in event_passes],
        "dry_season": {"window_utc": [utc_text(window[0]), utc_text(window[1])], "cap": DRY_CAP,
                       "rule": "per relative orbit of the event passes: the latest passes of the window first, at most 10",
                       "min_valid_passes_per_cell_of_the_method": MIN_DRY_PASSES_FOR_THE_METHOD, "by_orbit": by_orbit},
        "work_folder": f"<external data root>/{WORK.as_posix()}/{arguments.area}/",
        "file_naming": {"event_pass": "event_<key>.tif and event_<key>.json", "dry_statistics": "dry_o<orbit>.tif and dry_o<orbit>.json"},
        "problems": problems,
    }
    path = record_path(arguments.area)
    folder = work_folder(arguments.external_root, arguments.area)
    folder.mkdir(parents=True, exist_ok=True)
    with file_lock(folder / ".record.lock"):
        write_json(path, record)
    refresh_record(arguments.area, arguments.external_root)
    log(f"wrote {path.relative_to(ROOT).as_posix()}")


def record_failure(folder: Path, name: str, reason: str, source_timestamp: str) -> None:
    """Write ``<name>.failed.json`` so the record can say why a step did not complete."""

    write_json(folder / f"{name}.failed.json", {"schema": "floodguard.nan_case_radar_failure.v1",
                                                **envelope(source_timestamp, "not applicable (failed step)", ASSUMPTIONS_COMMON),
                                                "step": name, "reason": reason})


def command_fetch(arguments: argparse.Namespace) -> None:
    """Fetch one event pass of an area onto its 20 m grid."""

    record = load_record(arguments.area)
    entry = find_pass(record, arguments.pass_key)
    log = logger(f"[fetch {arguments.area} {entry['key']}]")
    folder = work_folder(arguments.external_root, arguments.area)
    name = f"event_{entry['key']}"
    grid = area_grid(load_areas()[arguments.area])
    log(f"{len(entry['scenes'])} scenes, start {entry['start_utc']} ({entry['start_thai']})")
    try:
        result = fetch_pass_file(folder, arguments.area, grid, entry, name, resolve=CatalogueResolver(),
                                 threads=arguments.threads, replace=arguments.replace, log=log)
    except Exception as error:  # noqa: BLE001 - recorded, then raised
        record_failure(folder, name, f"{type(error).__name__}: {error}", entry["start_utc"])
        refresh_record(arguments.area, arguments.external_root)
        raise
    (folder / f"{name}.failed.json").unlink(missing_ok=True)
    refresh_record(arguments.area, arguments.external_root)
    log(f"done in {result['seconds']} s; valid share {result['valid_share']}")


def command_drystats(arguments: argparse.Namespace) -> None:
    """Stream the selected dry-season passes of one orbit into per-cell statistics and write them."""

    import rasterio
    from rasterio.transform import from_origin
    from rasterio.windows import Window

    orbit = int(arguments.orbit)
    log = logger(f"[drystats {arguments.area} o{orbit}]")
    record = load_record(arguments.area)
    block = record["dry_season"]["by_orbit"].get(str(orbit))
    if block is None:
        raise RadarCaseError(f"orbit {orbit} is not an orbit of the event passes of {arguments.area}")
    found = {entry["key"]: entry for entry in block["passes_found"]}
    selected = [found[key] for key in block["selected_latest_first"]]
    if not selected:
        raise RadarCaseError(f"no dry-season pass of orbit {orbit} for {arguments.area}")
    grid = area_grid(load_areas()[arguments.area])
    _west, _north, rows, columns = grid
    folder = work_folder(arguments.external_root, arguments.area)
    name = f"dry_o{orbit}"
    out_path, out_record = folder / f"{name}.tif", folder / f"{name}.json"
    if out_path.exists() and out_record.exists() and not arguments.replace:
        log("already computed")
        refresh_record(arguments.area, arguments.external_root)
        return
    partial = folder / f"{name}_partial"
    state_path = partial / "state.json"
    platforms = sorted({entry["platform"] for entry in selected})
    keys = [entry["key"] for entry in selected]
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() and not arguments.replace else None
    if state is not None and (state.get("selected") != keys or state.get("in_progress")):
        log("the partial state does not fit (another selection, or a pass was being added when it stopped): starting again")
        state = None
    accumulator = DryAccumulator((rows, columns), platforms, folder=partial, resume=state is not None)
    if state is None:
        state = {"selected": keys, "added": [], "in_progress": None}
        write_json(state_path, state)
    started = time.perf_counter()
    resolve = CatalogueResolver()
    try:
        for position, entry in enumerate(selected, start=1):
            if any(added["key"] == entry["key"] for added in state["added"]):
                continue
            log(f"pass {position} of {len(selected)}: {entry['key']} ({len(entry['scenes'])} scenes)")
            temporary = f"tmp_{name}_{entry['key']}"
            pass_record = fetch_pass_file(folder, arguments.area, grid, entry, temporary, resolve=resolve,
                                          threads=arguments.threads, role=f"dry season, orbit {orbit}", log=log)
            state["in_progress"] = entry["key"]
            write_json(state_path, state)
            counted = 0
            levels: dict[str, list[np.ndarray]] = {"vh": [], "vv": []}
            with rasterio.open(folder / f"{temporary}.tif") as source:
                for top in range(0, rows, 512):
                    height = min(512, rows - top)
                    window = Window(0, top, columns, height)
                    vv, vh = source.read(1, window=window), source.read(2, window=window)
                    counted += accumulator.add(entry["platform"], vh, vv, row0=top)
                    both = np.isfinite(vh) & np.isfinite(vv) & (vh > 0) & (vv > 0)
                    levels["vh"].append(to_db(vh[both]).astype("float32"))
                    levels["vv"].append(to_db(vv[both]).astype("float32"))
            accumulator.flush()
            medians = {band: (round(float(np.median(np.concatenate(values))), 4) if sum(part.size for part in values) else None)
                       for band, values in levels.items()}
            del levels
            state["added"].append({"key": entry["key"], "platform": entry["platform"], "start_utc": entry["start_utc"],
                                   "start_thai": entry["start_thai"], "scenes": pass_record["scenes"],
                                   "temporary_file": pass_record["file"], "temporary_file_sha256": pass_record["sha256"],
                                   "valid_share": pass_record["valid_share"], "seconds": pass_record["seconds"],
                                   "cells_counted": counted, "median_vh_db_over_its_cells": medians["vh"],
                                   "median_vv_db_over_its_cells": medians["vv"]})
            state["in_progress"] = None
            write_json(state_path, state)
            (folder / f"{temporary}.tif").unlink()
            (folder / f"{temporary}.json").unlink()
            log(f"  added in {pass_record['seconds']} s; {counted} cells counted")
            refresh_record(arguments.area, arguments.external_root)
    except Exception as error:  # noqa: BLE001 - recorded, then raised
        accumulator.close()
        record_failure(folder, name, f"{type(error).__name__}: {error}", f"dry season of orbit {orbit}")
        refresh_record(arguments.area, arguments.external_root)
        raise
    log("writing the statistics")
    bands = ("vh_mean_db", "vh_std_db", "vv_mean_db", "vv_std_db", "n_valid")
    histogram = np.zeros(len(selected) + 1, dtype="int64")
    differences: dict[str, list[np.ndarray]] = {"vh": [], "vv": []}
    west, north, _rows, _columns = grid
    with rasterio.open(out_path, "w", driver="GTiff", height=rows, width=columns, count=len(bands), dtype="float32",
                       nodata=float("nan"), crs=f"EPSG:{EPSG}", transform=from_origin(west, north, CELL_M, CELL_M),
                       tiled=True, blockxsize=256, blockysize=256, compress="deflate", predictor=3,
                       BIGTIFF="IF_SAFER") as target:
        for top in range(0, rows, 512):
            bottom = min(rows, top + 512)
            stats = accumulator.statistics(top, bottom)
            count = stats["n_valid"]
            histogram += np.bincount(count.astype("int64").ravel(), minlength=len(selected) + 1)[:len(selected) + 1]
            for index, band in enumerate(bands, start=1):
                values = stats[band].astype("float32")
                if band == "n_valid":
                    values = np.where(count > 0, values, np.nan).astype("float32")
                target.write(values, index, window=Window(0, top, columns, bottom - top))
            if len(platforms) >= 2:
                first = accumulator.statistics(top, bottom, platforms=[platforms[0]])
                second = accumulator.statistics(top, bottom, platforms=[platforms[1]])
                for band in ("vh", "vv"):
                    difference = first[f"{band}_mean_db"] - second[f"{band}_mean_db"]
                    differences[band].append(difference[np.isfinite(difference)].astype("float32"))
        for index, band in enumerate(bands, start=1):
            target.set_band_description(index, band)
    if len(platforms) >= 2:
        vh = difference_summary(np.concatenate(differences["vh"]) if differences["vh"] else np.array([]))
        vv = difference_summary(np.concatenate(differences["vv"]) if differences["vv"] else np.array([]))
        sensor = {"applies": True, "platforms": platforms[:2],
                  "difference": f"mean VH dB of the {platforms[0]} passes minus mean VH dB of the {platforms[1]} passes",
                  "passes_per_platform": {name_: sum(1 for entry in selected if entry["platform"] == name_) for name_ in platforms},
                  **vh, "vv_for_information": {key: vv[key] for key in ("median_db", "p25_db", "p75_db")},
                  "correction_applied": False, "rule": SENSOR_RULE}
    else:
        sensor = {"applies": False, "platforms": platforms,
                  "reason": f"every selected dry pass of orbit {orbit} is from {platforms[0]}", "rule": SENSOR_RULE}
    accumulator.close()
    cells = rows * columns
    at_least = int(histogram[MIN_DRY_PASSES_FOR_THE_METHOD:].sum())
    result = {
        "schema": "floodguard.nan_case_radar_dry_statistics.v1",
        **envelope(f"dry season {record['dry_season']['window_utc'][0]} to {record['dry_season']['window_utc'][1]}, "
                   f"passes {selected[-1]['start_utc']} to {selected[0]['start_utc']}",
                   "not applicable (backscatter statistics; nothing is detected here)",
                   ASSUMPTIONS_COMMON + [DRY_RULE[0].upper() + DRY_RULE[1:] + ".",
                                         "Sums are kept in float64 per platform; the totals add the platforms.",
                                         "The minimum of 6 valid passes is applied by the method, not here: n_valid lets it be applied."]),
        "protocol": PROTOCOL, "area": arguments.area, "relative_orbit": orbit,
        "window_utc": record["dry_season"]["window_utc"], "selection_rule": record["dry_season"]["rule"],
        "passes_used": state["added"], "platforms": platforms,
        "bands": list(bands), "nodata": "NaN (every band, where n_valid is 0)", "cell_rule": CELL_RULE, "dry_rule": DRY_RULE,
        "n_valid_histogram": {str(index): int(value) for index, value in enumerate(histogram)},
        "share_of_cells_with_at_least_6_valid_passes": round(at_least / cells, 6),
        "share_of_cells_with_no_valid_pass": round(int(histogram[0]) / cells, 6),
        "sensor_agreement": sensor,
        "per_pass_medians_for_information": {
            "what": ("the median VH dB and VV dB of each pass over the cells where it counted, in time order: shows "
                     "whether passes of one platform stand apart from the seasonal course of the other; no rule uses it"),
            "passes": sorted(({"key": added["key"], "platform": added["platform"], "start_utc": added["start_utc"],
                               "median_vh_db": added.get("median_vh_db_over_its_cells"),
                               "median_vv_db": added.get("median_vv_db_over_its_cells")} for added in state["added"]),
                             key=lambda item: item["start_utc"])},
        "file": out_path.name, "sha256": s1_rtc.sha256_file(out_path),
        "seconds": round(time.perf_counter() - started, 1),
        "seconds_of_the_passes": round(sum(float(entry.get("seconds", 0)) for entry in state["added"]), 1),
    }
    write_json(out_record, result)
    for path in sorted(partial.glob("*")) + sorted(folder.glob(f"tmp_{name}_*")):
        path.unlink()  # the accumulators, and any temporary pass left by a run that stopped after adding it
    partial.rmdir()
    (folder / f"{name}.failed.json").unlink(missing_ok=True)
    refresh_record(arguments.area, arguments.external_root)
    log(f"done; cells with at least 6 valid passes: {result['share_of_cells_with_at_least_6_valid_passes']}; sensor: "
        f"{sensor.get('median_db')} dB (flagged {sensor.get('flagged')})")


def command_status(arguments: argparse.Namespace) -> None:
    """Refresh the statuses of an area's record from the work folder."""

    record = refresh_record(arguments.area, arguments.external_root)
    print(json.dumps(record["status_summary"], indent=1))


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line and run one subcommand."""

    for key, value in PROCESS_GDAL_OPTIONS.items():
        os.environ.setdefault(key, value)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "fetch", "drystats", "status"):
        command = commands.add_parser(name)
        command.add_argument("--area", required=True)
        command.add_argument("--external-root", required=True)
        if name in ("fetch", "drystats"):
            command.add_argument("--threads", type=int, default=DEFAULT_THREADS)
            command.add_argument("--replace", action="store_true")
        if name == "fetch":
            command.add_argument("--pass", dest="pass_key", required=True)
        if name == "drystats":
            command.add_argument("--orbit", required=True, type=int)
    arguments = parser.parse_args(argv)
    {"list": command_list, "fetch": command_fetch, "drystats": command_drystats, "status": command_status}[arguments.command](arguments)


if __name__ == "__main__":
    main()
