"""The Nan case: the time series of the protocol (report only).

Protocol ``docs/proposal_execution/nan_case_protocol_v1.json`` (decision log R51, key ``time_series``): "the frozen
central M1-z on every event pass: flooded area and residents inside per tambon and per pass, report-only, set beside
a public gauge record of the Nan River if one is found". This script reads, and computes no flag:

* every frozen map of a Nan pass that the method lane wrote (``scripts/nan_case_method.py``, stages ``test`` and
  ``maps``): ``<external root>/proposal_execution/nan_case_v1/method/maps/m1z_<label>.tif`` with the bands
  ``code_lower``, ``code_central``, ``code_upper`` and ``reason_central`` (codes 1 flagged, 0 not flagged, 255 no
  answer) and the record ``m1z_<label>.json`` beside it. A map counts only when its record names the freeze record
  in force (``outputs/nan_case/freeze_v1.json``, by SHA-256) and its bytes are those its record names;
* the frame lane's unit raster (``frame/n1_units_20m.tif``) and demand cells (``frame/demand_cells_v1.json``,
  WorldPop 2020), each checked against the SHA-256 that ``outputs/nan_case/frame_v1.json`` records;
* the radar lane's record ``outputs/nan_case/radar_passes_nan_frame_v1.json`` for each pass's footprint;
* the gauge series the consequence lane saved (``consequence/gauge/thaiwater_<station>_*.csv``), indexed by
  ``outputs/nan_case/news_records_v1.json`` (``gauge_records``) and checked against the SHA-256 recorded there.

For every pass, per tambon of the frame and for the whole frame, it gives the land the map flags (km2, central
and lower / upper), the share of land flagged, the no-answer share, the modelled residents inside flagged cells
(a resident is inside when the centre of its demand cell lies in a flagged 20 m cell, the grid lookup of the score
chain, ``floodguard.nan_case_chain.grid_values_at``), the pass time in UTC and Thai time, its platform and relative
orbit and the share of the frame it covers. Passes on partial footprints (relative orbits 99, 135 and 172, or a
catalogue footprint under 0.99 of the grid) are labelled with their coverage, and the frame figures are also given
on the land that every pass of one orbit (and every pass) sees with radar, so that a rise or fall is not read as
water when it is coverage. The gauge levels at the pass times are set beside them.

Outputs: ``outputs/nan_case/time_series_v1.json`` (figures only, in Git) and a small chart
``outputs/nan_case/time_series_v1.png`` (PIL). The stage refuses unless the test record
``outputs/nan_case/test_result_v1.json`` exists (the order rule of the protocol), and it never opens the sealed JAXA
folder, a GFM file, the THEOS-2 files of 31 July 2025 or anything derived from them, or the case N2 reference.

Usage (from the repository root)::

    python scripts/nan_case_time_series.py run --external-root <external data root>
    python scripts/nan_case_time_series.py check-inputs --external-root <external data root> [--chart-preview <png>]

``check-inputs`` reads the records, the unit raster, the demand cells and the gauge series, reads the gauge levels
at the times of the event passes the radar record lists, and opens no map: it computes no flood figure and needs no
test record. Every figure is planning guidance: not an official warning, and no reference layer is compared here.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform as python_platform
import re
import subprocess
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from floodguard import m1z  # noqa: E402
from floodguard import nan_case_chain as chain_rules  # noqa: E402
from floodguard.flood_inputs import ANALYSIS_CRS, WGS84_CRS  # noqa: E402


def _load_method() -> Any:
    """The method lane's script as a module (its pass helpers are reused unchanged)."""

    name = "nan_case_method"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "nan_case_method.py")
    if spec is None or spec.loader is None:
        raise ImportError("scripts/nan_case_method.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


method = _load_method()

SCHEMA = "floodguard.nan_case_time_series.v1"
PROTOCOL = "docs/proposal_execution/nan_case_protocol_v1.json"
AMENDMENT_1 = "docs/proposal_execution/nan_case_protocol_v1_amendment_1.json"
FRAME_RECORD = "outputs/nan_case/frame_v1.json"
RADAR_RECORD = "outputs/nan_case/radar_passes_nan_frame_v1.json"
NEWS_RECORD = "outputs/nan_case/news_records_v1.json"
FREEZE = "outputs/nan_case/freeze_v1.json"
TEST_RESULT = "outputs/nan_case/test_result_v1.json"
OUT_JSON = "outputs/nan_case/time_series_v1.json"
OUT_PNG = "outputs/nan_case/time_series_v1.png"
CASE = Path("proposal_execution") / "nan_case_v1"
MAPS_DIR = CASE / "method" / "maps"
FRAME_DIR = CASE / "frame"
GAUGE_DIR = CASE / "consequence" / "gauge"
UNIT_RASTER_NAME = "n1_units_20m.tif"
DEMAND_NAME = "demand_cells_v1.json"
MAPS_INDEX_NAME = "maps_index_v1.json"
GAUGE_SUMMARY_NAME = "gauge_summary_v1.json"
MAP_SCHEMA = "floodguard.nan_case_m1z_map.v1"
EXTERNAL_LABEL = "<external_data_workspace>"

LEVELS: tuple[str, ...] = ("lower", "central", "upper")
CODE_BANDS: dict[str, str] = {level: f"code_{level}" for level in LEVELS}
REASON_BAND = "reason_central"
TERRAIN_REASONS: tuple[int, ...] = (m1z.REASON_TERRAIN_HAND, m1z.REASON_TERRAIN_SLOPE)
CELL_KM2 = m1z.CELL_M * m1z.CELL_M / 1e6
PARTIAL_FOOTPRINT_ORBITS: tuple[int, ...] = (99, 135, 172)
"""The relative orbits whose footprints cover only part of the frame grid (radar record of the frame)."""
FULL_FOOTPRINT_MIN_SHARE = 0.99
PASS_MATCH_MINUTES = 60
THAI = timezone(timedelta(hours=7))
GAUGE_INTERPOLATION_MAX_GAP_MINUTES = 180
GAUGE_NEAREST_MAX_MINUTES = 90
GAUGE_COLUMNS: tuple[str, ...] = ("datetime_thai_time", "level_m_msl", "gauge_height_m", "discharge_m3_s")
GAUGE_FIELDS: tuple[str, ...] = ("level_m_msl", "gauge_height_m", "discharge_m3_s")
CHART_STATIONS: tuple[str, ...] = ("N.1", "N.64", "N.75", "SKU04 (N.13A)")
"""The four public Nan River gauges of the task, drawn in the chart (every station of the index is in the record)."""
BANK_LEVEL = "min_bank"
EXIT_DONE, EXIT_REFUSED = 0, 2

FIREWALL_MARKERS: tuple[str, ...] = (
    "jaxa_sealed", "case_n2_reference", "gfm", "eodc", "theos2_water_labels", "water_v2_chip_00", "chip_001_2m",
    "chip_003_2m", "held_chip_", "img_t2v_20250731035100",
)
"""Parts of a path this stage never opens (the firewall of the Nan case), beside ``nan_case_chain.firewall_refusal``:
the sealed JAXA folder, the case N2 reference (the test 1 reference on the frame grid), GFM, the THEOS-2 scene of
31 July 2025, its labels and everything derived from its two Nan chips."""

ASSUMPTIONS = [
    "Every figure is read from the frozen M1-z maps of the method lane (bands code_lower, code_central and code_upper; "
    "1 flagged, 0 not flagged, 255 no answer; band reason_central), unchanged. No flag is computed here, and no "
    "reference layer is compared.",
    "Land is a 20 m cell whose centre lies in one of the tambons of the frame (the frame lane's unit raster) and that "
    "the map does not mark as permanent water (reason code 20: ESA WorldCover 2021 class 80).",
    "Flooded land is the land the map flags. A no-answer cell counts as not flagged, as in the binding chain; the "
    "no-answer share is that of the central map (the three maps share their no-answer cells, which the record checks).",
    "A modelled resident (WorldPop 2020, the frame lane's demand cells) is inside when the centre of its 100 m demand "
    "cell lies in a flagged 20 m cell: the grid lookup of the score chain. A cell counts for the tambon that holds its "
    "centre.",
    "A pass on a partial footprint sees only part of the frame. Outside its scenes, low land gets no answer and high or "
    "steep land is answered by terrain, so its totals fall for lack of radar, not for lack of water. Compare passes of "
    "one relative orbit, or the figures on the land every pass of a group sees with radar.",
    "Sentinel-1C passes carry the platform offset of protocol amendment 1 as the method lane applied it.",
    "Gauge levels are the thaiwater.net series the consequence lane saved, in Thai time, read at the pass time by linear "
    "interpolation between the nearest readings with a value on each side when they are at most 3 hours apart. A gauge "
    "level is one point on a river, not a flood extent.",
    "Report only: no score, class or test rule of the case reads these figures.",
]
LIMITS = [
    "C-band radar does not see water under trees, between buildings or under crops, nor water that drained before the pass.",
    "The passes are hours or days apart; water that came and went between two passes is not in the series.",
    "Residents are modelled 2020 counts, not event-year counts and not people observed in the water.",
    "Planning guidance only; not an official warning.",
]


class TimeSeriesError(ValueError):
    """Raised when the stage refuses: the order rule, the firewall, or an input that is not the one recorded."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def now_utc() -> str:
    """The time now, UTC, to the second."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    """SHA-256 of bytes."""

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """SHA-256 of a file's bytes."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def code_sha256(path: Path) -> str:
    """SHA-256 of a code file as Git holds it: a checkout's CRLF line ends are read as LF."""

    return sha256_bytes(Path(path).read_bytes().replace(b"\r\n", b"\n"))


def read_json(path: Path) -> Any:
    """A JSON file read as UTF-8."""

    return json.loads(Path(path).read_bytes().decode("utf-8"))


def label_path(path: Path, root: Path, external: Path | None) -> str:
    """Name a file without a machine path: relative to the repository, or to the external data root."""

    resolved = Path(path).resolve()
    for base, prefix in ((root, None), (external, EXTERNAL_LABEL)):
        if base is None:
            continue
        try:
            relative = resolved.relative_to(Path(base).resolve()).as_posix()
        except ValueError:
            continue
        return relative if prefix is None else f"{prefix}/{relative}"
    return Path(path).name


def km2(cells: int | float) -> float:
    """Area of a number of 20 m cells, km2, to 4 decimals (one cell is 0.0004 km2)."""

    return round(float(cells) * CELL_KM2, 4)


def share(part: int | float, whole: int | float) -> float | None:
    """``part / whole`` to 6 decimals; ``None`` when there is no whole."""

    return None if not whole else round(float(part) / float(whole), 6)


def people(value: float) -> float:
    """A modelled resident count to 3 decimals."""

    return round(float(value), 3)


def parse_utc(text: Any) -> datetime | None:
    """A UTC instant from an ISO text (``Z`` or an offset); ``None`` when it cannot be read."""

    parsed = method.parse_time(text)
    return None if parsed is None else parsed.astimezone(timezone.utc)


def utc_text(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def thai_text(instant: datetime) -> str:
    """Thai time (UTC+7) of an instant, ISO with its offset."""

    return instant.astimezone(THAI).strftime("%Y-%m-%dT%H:%M:%S+07:00")


def thai_naive(instant: datetime) -> datetime:
    """The Thai wall-clock time of an instant, without a zone (as the gauge series write it)."""

    return instant.astimezone(THAI).replace(tzinfo=None)


def firewall_refusal(path: Path | str) -> str | None:
    """Say why this stage may not open a path, or ``None`` when it may.

    The score chain's rule (``floodguard.nan_case_chain.firewall_refusal``) and the markers of this stage
    (:data:`FIREWALL_MARKERS`): the sealed JAXA folder, the case N2 reference, GFM and the THEOS-2 files of 31 July
    2025 with everything derived from them.
    """

    why = chain_rules.firewall_refusal(path)
    if why is not None:
        return why
    text = str(path).replace("\\", "/").lower()
    for marker in FIREWALL_MARKERS:
        if marker in text:
            return f"{Path(path).as_posix()} lies behind the firewall of the Nan case ({marker}); the time series never opens it"
    return None


def refuse_firewall(paths: Sequence[Path | str | None]) -> None:
    """Refuse before anything is opened when a path lies behind the firewall.

    Raises:
        TimeSeriesError: for the first such path.
    """

    for path in paths:
        if path is None:
            continue
        why = firewall_refusal(path)
        if why is not None:
            raise TimeSeriesError(why)


def dumps_record(record: Mapping[str, Any], compact: Sequence[str] = ()) -> str:
    """JSON text with indent 1, ASCII, LF line ends; the top-level lists named in ``compact`` hold one row per line."""

    body = dict(record)
    parts: dict[str, list[Any]] = {}
    for key in compact:
        if isinstance(body.get(key), list):
            parts[key] = body[key]
            body[key] = f"@@{key}@@"
    text = json.dumps(body, indent=1, ensure_ascii=True, allow_nan=False)
    for key, rows in parts.items():
        inner = ",\n  ".join(json.dumps(row, ensure_ascii=True, allow_nan=False) for row in rows)
        text = text.replace(json.dumps(f"@@{key}@@"), "[\n  " + inner + "\n ]" if rows else "[]")
    return text + "\n"


def write_text(path: Path, text: str) -> dict[str, Any]:
    """Write UTF-8 text with LF line ends; return its size and SHA-256."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": sha256_bytes(data)}


def head_commit(root: Path) -> str | None:
    """The commit the working tree is on (read-only ``git rev-parse``), or ``None``."""

    try:
        found = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    text = found.stdout.decode().strip()
    return text if found.returncode == 0 and text else None


# ---------------------------------------------------------------------------
# The frame: units, unit raster and demand cells
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    """One tambon of the frame and the value it takes in the unit raster."""

    unit_id: str
    name: str
    district: str
    raster_value: int


def frame_units(frame_record: Mapping[str, Any]) -> list[Unit]:
    """The tambons of the frame record, in the order of their codes.

    Raises:
        TimeSeriesError: for a record without units, a repeated code or raster value, or a raster value outside 1-254.
    """

    rows = frame_record.get("units") or []
    units = sorted((Unit(str(row["adm3_pcode"]), str(row.get("adm3_name") or row["adm3_pcode"]), str(row.get("adm2_pcode") or ""),
                         int(row["raster_value"])) for row in rows), key=lambda unit: unit.unit_id)
    if not units:
        raise TimeSeriesError("the frame record lists no unit")
    if len({unit.unit_id for unit in units}) != len(units) or len({unit.raster_value for unit in units}) != len(units):
        raise TimeSeriesError("each unit of the frame record has its own code and its own raster value")
    if any(not 1 <= unit.raster_value <= 254 for unit in units):
        raise TimeSeriesError("a unit's raster value lies between 1 and 254 (0 is no unit, 255 more than one)")
    return units


def check_grid_of(source: Any, grid: chain_rules.RasterGrid, name: str) -> None:
    """Refuse a raster that is not on the frame grid (EPSG:32647, 20 m, same corner and size)."""

    if source.crs is None or source.crs.to_epsg() != grid.epsg:
        raise TimeSeriesError(f"{name}: a raster of the frame is in EPSG:{grid.epsg}")
    if (source.width, source.height) != (grid.cols, grid.rows) or any(
            abs(a - b) > 1e-6 for a, b in zip(tuple(source.transform)[:6], tuple(grid.transform)[:6])):
        raise TimeSeriesError(f"{name}: the raster is not on the frame grid {grid.as_record()}")


def read_unit_raster(path: Path, grid: chain_rules.RasterGrid, units: Sequence[Unit], expected_sha256: str | None
                     ) -> tuple[np.ndarray, dict[str, Any]]:
    """The frame lane's unit raster, checked against its recorded SHA-256, the grid and the units' raster values."""

    import rasterio

    refuse_firewall([path])
    if not path.is_file():
        raise TimeSeriesError(f"no unit raster {path.name} in the frame folder")
    digest = sha256_file(path)
    if expected_sha256 and digest != expected_sha256:
        raise TimeSeriesError(f"{path.name} is not the unit raster the frame record names (SHA-256 differs)")
    with rasterio.open(path) as source:
        check_grid_of(source, grid, path.name)
        values = source.read(1)
    found = set(np.unique(values).tolist())
    allowed = {0, 255, *(unit.raster_value for unit in units)}
    if not found <= allowed:
        raise TimeSeriesError(f"{path.name} holds values the frame record names no unit for: {sorted(found - allowed)[:5]}")
    return values, {"name": path.name, "sha256": digest, "sha256_recorded_by_the_frame_lane": expected_sha256,
                    "cells_in_the_frame": int(np.isin(values, [unit.raster_value for unit in units]).sum()),
                    "cells_in_more_than_one_unit": int((values == 255).sum())}


@dataclass
class Demand:
    """The demand cells of the frame: EPSG:32647 centre, WorldPop 2020 residents and the tambon of each."""

    x: np.ndarray
    y: np.ndarray
    residents: np.ndarray
    unit_ids: list[str | None]
    members: dict[str, np.ndarray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (len(self.x) == len(self.y) == len(self.residents) == len(self.unit_ids)):
            raise TimeSeriesError("every demand cell has a centre, a count and a unit")
        if len(self.residents) and (not np.all(np.isfinite(self.residents)) or float(self.residents.min()) < 0):
            raise TimeSeriesError("a resident count is a finite number, 0 or more")
        if not self.members:
            grouped: dict[str, list[int]] = {}
            for index, unit_id in enumerate(self.unit_ids):
                if unit_id is not None:
                    grouped.setdefault(unit_id, []).append(index)
            self.members = {unit_id: np.asarray(indices, dtype="int64") for unit_id, indices in grouped.items()}


def demand_from_record(record: Mapping[str, Any], grid: chain_rules.RasterGrid) -> tuple[Demand, dict[str, Any]]:
    """The demand cells of the frame lane's file (``columns`` and ``rows``), projected as the score chain projects them.

    The chain projects each cell's longitude and latitude to EPSG:32647 (pyproj, always_xy) and looks the 20 m cell
    up; the frame lane wrote the same cell as ``grid_row`` and ``grid_col``. Both are read; the cells where they
    differ are counted in the record.

    Raises:
        TimeSeriesError: for a file without the columns the frame lane writes.
    """

    from pyproj import Transformer

    columns = list(record.get("columns") or [])
    needed = ("population_id", "unit_id", "residents_2020", "longitude", "latitude", "grid_row", "grid_col")
    missing = [name for name in needed if name not in columns]
    if missing:
        raise TimeSeriesError(f"the demand cells file has no column {missing}")
    index = {name: columns.index(name) for name in needed}
    rows = record.get("rows") or []
    longitude = np.array([float(row[index["longitude"]]) for row in rows], dtype="float64")
    latitude = np.array([float(row[index["latitude"]]) for row in rows], dtype="float64")
    residents = np.array([float(row[index["residents_2020"]]) for row in rows], dtype="float64")
    unit_ids = [None if row[index["unit_id"]] is None else str(row[index["unit_id"]]) for row in rows]
    to_metres = Transformer.from_crs(WGS84_CRS, ANALYSIS_CRS, always_xy=True)
    x, y = to_metres.transform(longitude, latitude) if len(rows) else (np.array([]), np.array([]))
    x, y = np.asarray(x, dtype="float64"), np.asarray(y, dtype="float64")
    cols = np.floor((x - grid.west) / grid.cell_m).astype("int64")
    lines = np.floor((grid.north - y) / grid.cell_m).astype("int64")
    stated_rows = np.array([-1 if row[index["grid_row"]] is None else int(row[index["grid_row"]]) for row in rows], dtype="int64")
    stated_cols = np.array([-1 if row[index["grid_col"]] is None else int(row[index["grid_col"]]) for row in rows], dtype="int64")
    differ = int(((lines != stated_rows) | (cols != stated_cols)).sum()) if len(rows) else 0
    demand = Demand(x=x, y=y, residents=residents, unit_ids=unit_ids)
    return demand, {"demand_cells": len(rows), "residents_2020": people(math.fsum(residents.tolist())),
                    "cells_in_no_unit": sum(1 for unit_id in unit_ids if unit_id is None),
                    "cells_whose_projected_cell_differs_from_the_frame_lane_grid_cell": differ,
                    "lookup": "longitude and latitude projected to EPSG:32647 (pyproj, always_xy) and looked up on the 20 m grid "
                              "(floodguard.nan_case_chain.grid_values_at), as the score chain does"}


def read_demand(path: Path, grid: chain_rules.RasterGrid, expected_sha256: str | None) -> tuple[Demand, dict[str, Any]]:
    """The frame lane's demand cells file, checked against the SHA-256 the frame record names."""

    refuse_firewall([path])
    if not path.is_file():
        raise TimeSeriesError(f"no demand cells file {path.name} in the frame folder")
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if expected_sha256 and digest != expected_sha256:
        raise TimeSeriesError(f"{path.name} is not the demand cells file the frame record names (SHA-256 differs)")
    demand, summary = demand_from_record(json.loads(data.decode("utf-8")), grid)
    return demand, {"name": path.name, "sha256": digest, "sha256_recorded_by_the_frame_lane": expected_sha256, **summary}


# ---------------------------------------------------------------------------
# The maps and the figures of one pass
# ---------------------------------------------------------------------------


@dataclass
class MapEntry:
    """One frozen map of a Nan pass, with its record."""

    path: Path
    record: Mapping[str, Any]
    record_sha256: str
    map_sha256: str
    time: datetime
    label: str
    platform: str | None
    orbit: int | None
    in_the_maps_index: bool | None


def discover_maps(folder: Path, freeze_sha256: str, root: Path, external: Path | None
                  ) -> tuple[list[MapEntry], list[dict[str, Any]], dict[str, Any] | None]:
    """The frozen maps of the maps folder, oldest pass first, and the files that do not count, each with why.

    A map counts when its record (``m1z_<label>.json`` beside it, schema ``floodguard.nan_case_m1z_map.v1``) names
    the freeze record in force by SHA-256, names the map by its file name and SHA-256, and gives the pass time.
    """

    refuse_firewall([folder])
    used: list[MapEntry] = []
    skipped: list[dict[str, Any]] = []
    index_names: set[str] | None = None
    index_record = None
    index_path = folder / MAPS_INDEX_NAME
    if index_path.is_file():
        index = read_json(index_path)
        index_names = {str(item.get("name")) for item in (index.get("maps") or {}).values() if isinstance(item, Mapping)}
        index_record = {"name": index_path.name, "sha256": sha256_file(index_path), "maps_listed": len(index_names)}
    for path in sorted(folder.glob("m1z_*.tif")) if folder.is_dir() else []:
        refuse_firewall([path])
        record_path = path.with_suffix(".json")
        why = None
        record: Mapping[str, Any] = {}
        if not record_path.is_file():
            why = "no record beside the map"
        else:
            record = read_json(record_path)
            pass_info = record.get("pass") or {}
            if record.get("schema") != MAP_SCHEMA:
                why = f"the record is not {MAP_SCHEMA}"
            elif (record.get("freeze_record") or {}).get("sha256") != freeze_sha256:
                why = "the record names another freeze record than the one in force: not a map of the frozen method"
            elif (record.get("map") or {}).get("name") != path.name:
                why = "the record names another map file"
            elif parse_utc(pass_info.get("time_utc")) is None:
                why = "the record gives no pass time"
        digest = None
        if why is None:
            digest = sha256_file(path)
            if digest != (record.get("map") or {}).get("sha256"):
                why = "the map's bytes are not those its record names"
        if why is not None:
            skipped.append({"map": label_path(path, root, external), "why": why})
            continue
        pass_info = record["pass"]
        orbit = pass_info.get("relative_orbit")
        used.append(MapEntry(path=path, record=record, record_sha256=sha256_file(record_path), map_sha256=str(digest),
                             time=parse_utc(pass_info["time_utc"]),  # type: ignore[arg-type]
                             label=str(pass_info.get("label") or path.stem.removeprefix("m1z_")),
                             platform=pass_info.get("platform"), orbit=None if orbit is None else int(orbit),
                             in_the_maps_index=None if index_names is None else path.name in index_names))
    used.sort(key=lambda entry: (entry.time, entry.label))
    return used, skipped, index_record


def read_map(path: Path, grid: chain_rules.RasterGrid) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """The three code bands and the central reasons of a map, checked against the grid and the codes.

    Raises:
        TimeSeriesError: for another grid, a missing band, a code other than 1, 0 and 255, or an unknown reason.
    """

    import rasterio

    refuse_firewall([path])
    with rasterio.open(path) as source:
        check_grid_of(source, grid, path.name)
        names = [str(text or "") for text in source.descriptions]
        wanted = [*CODE_BANDS.values(), REASON_BAND]
        missing = [name for name in wanted if name not in names]
        if missing:
            raise TimeSeriesError(f"{path.name}: no band named {missing}; the bands are {names}")
        codes = {level: source.read(names.index(band) + 1) for level, band in CODE_BANDS.items()}
        reason = source.read(names.index(REASON_BAND) + 1)
    for level, values in codes.items():
        try:
            chain_rules.check_flood_values(values, grid)
        except chain_rules.NanChainError as error:
            raise TimeSeriesError(f"{path.name}, band {CODE_BANDS[level]}: {error}") from error
    unknown = set(np.unique(reason).tolist()) - set(m1z.REASON_LABELS)
    if unknown:
        raise TimeSeriesError(f"{path.name}: reason codes the method does not name: {sorted(unknown)[:5]}")
    return codes, reason


def pass_figures(codes: Mapping[str, np.ndarray], reason: np.ndarray, unit_raster: np.ndarray, units: Sequence[Unit],
                 demand: Demand, grid: chain_rules.RasterGrid) -> dict[str, Any]:
    """The figures of one pass for the frame and for each tambon.

    Land is a cell of a tambon that the map does not mark as permanent water. Flooded land is the flagged land of
    each level; the no-answer, no-radar-after and terrain-answered shares are those of the central map. A demand cell
    is inside when the 20 m cell under its centre is flagged (``nan_case_chain.grid_values_at``).

    Returns:
        ``frame`` (the whole frame), ``units`` (one dict per tambon, in the order of ``units``), ``masks`` (the
        land, the flagged land of each level and the land without radar after, for the common-area figures) and
        ``checks``.
    """

    values = np.array([unit.raster_value for unit in units], dtype=unit_raster.dtype)
    in_frame = np.isin(unit_raster, values)
    water = reason == m1z.REASON_PERMANENT_WATER
    land = in_frame & ~water
    flagged = {level: land & (codes[level] == m1z.FLAGGED) for level in LEVELS}
    no_answer = land & (codes["central"] == m1z.NO_ANSWER)
    no_radar = land & (reason == m1z.REASON_NO_RADAR_AFTER)
    terrain = land & np.isin(reason, TERRAIN_REASONS)

    def by_unit(mask: np.ndarray) -> np.ndarray:
        return np.bincount(unit_raster[mask].astype("int64"), minlength=256)

    counts = {"land": by_unit(land), "no_answer": by_unit(no_answer), "no_radar": by_unit(no_radar), "terrain": by_unit(terrain),
              **{f"flagged_{level}": by_unit(flagged[level]) for level in LEVELS}}
    looked_up = {level: chain_rules.grid_values_at(codes[level], grid, demand.x, demand.y) for level in LEVELS}
    inside = {level: looked_up[level] == m1z.FLAGGED for level in LEVELS}
    unanswered = looked_up["central"] == m1z.NO_ANSWER

    def residents_where(selection: np.ndarray, members: np.ndarray | None = None) -> float:
        chosen = demand.residents if members is None else demand.residents[members]
        where = selection if members is None else selection[members]
        return math.fsum(chosen[where].tolist())

    def figures(land_cells: int, flagged_cells: Mapping[str, int], no_answer_cells: int, no_radar_cells: int, terrain_cells: int,
                residents: float, inside_residents: Mapping[str, float], unanswered_residents: float) -> dict[str, Any]:
        not_terrain = land_cells - terrain_cells
        return {
            "land_cells": int(land_cells), "land_km2": km2(land_cells),
            "flagged_cells": {level: int(flagged_cells[level]) for level in LEVELS},
            "flooded_land_km2": {level: km2(flagged_cells[level]) for level in LEVELS},
            "flagged_share_of_land": {level: share(flagged_cells[level], land_cells) for level in LEVELS},
            "no_answer_land_km2": km2(no_answer_cells),
            "no_answer_share_of_land": share(no_answer_cells, land_cells),
            "no_radar_after_share_of_land": share(no_radar_cells, land_cells),
            "terrain_answered_share_of_land": share(terrain_cells, land_cells),
            "radar_value_share_of_land_not_answered_by_terrain": None if not_terrain <= 0 else round(1.0 - no_radar_cells / not_terrain, 6),
            "residents_2020": people(residents),
            "residents_in_flagged_cells": {level: people(inside_residents[level]) for level in LEVELS},
            "residents_in_no_answer_cells": people(unanswered_residents),
        }

    rows = []
    for unit in units:
        value = unit.raster_value
        members = demand.members.get(unit.unit_id, np.array([], dtype="int64"))
        rows.append({"unit_id": unit.unit_id, "unit_name": unit.name, **figures(
            int(counts["land"][value]), {level: int(counts[f"flagged_{level}"][value]) for level in LEVELS},
            int(counts["no_answer"][value]), int(counts["no_radar"][value]), int(counts["terrain"][value]),
            math.fsum(demand.residents[members].tolist()),
            {level: residents_where(inside[level], members) for level in LEVELS}, residents_where(unanswered, members))})
    frame = figures(int(land.sum()), {level: int(flagged[level].sum()) for level in LEVELS}, int(no_answer.sum()), int(no_radar.sum()),
                    int(terrain.sum()), math.fsum(demand.residents.tolist()),
                    {level: residents_where(inside[level]) for level in LEVELS}, residents_where(unanswered))
    same_no_answer = all(np.array_equal(codes[level] == m1z.NO_ANSWER, codes["central"] == m1z.NO_ANSWER) for level in LEVELS)
    ordered = bool(np.all(flagged["lower"] <= flagged["central"]) and np.all(flagged["central"] <= flagged["upper"]))
    checks = {"no_answer_cells_same_in_the_three_maps": same_no_answer,
              "lower_flags_within_central_and_central_within_upper": ordered,
              "flagged_cells_outside_the_land_of_the_frame_central": int(((codes["central"] == m1z.FLAGGED) & ~land & in_frame).sum())}
    return {"frame": frame, "units": rows, "checks": checks,
            "masks": {"land": land, "no_radar": no_radar, **{f"flagged_{level}": flagged[level] for level in LEVELS}}}


def against_the_map_record(frame: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    """Set the frame figures beside the summary the method lane wrote in the map's record (its own frame mask)."""

    summary = record.get("summary") or {}
    rows = {}
    same = True
    for level in LEVELS:
        stated = (summary.get(level) or {}).get("flagged_km2_frame_land")
        computed = frame["flooded_land_km2"][level]
        rows[f"flooded_land_km2_{level}"] = {"map_record": stated, "here": computed}
        if stated is not None and abs(float(stated) - computed) > 1e-6:
            same = False
    stated_share = (summary.get("central") or {}).get("no_answer_share_frame_land")
    rows["no_answer_share_of_land"] = {"map_record": stated_share, "here": frame["no_answer_share_of_land"]}
    if stated_share is not None and frame["no_answer_share_of_land"] is not None and abs(float(stated_share) - frame["no_answer_share_of_land"]) > 1e-5:
        same = False
    return {"figures": rows, "same": same if summary else None,
            "note": "The map record counts the cells whose centre lies in the frame's COD-AB units, rasterised by the method "
                    "lane; this stage reads the frame lane's unit raster made by the same rule."}


# ---------------------------------------------------------------------------
# Coverage and the land every pass of a group sees
# ---------------------------------------------------------------------------


def radar_entry_for(pass_info: Mapping[str, Any], radar_record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The radar lane's entry of a pass: by event file name, else by platform, relative orbit and start within 60 min."""

    if not radar_record:
        return None
    passes = [entry for entry in radar_record.get("event_passes") or [] if isinstance(entry, Mapping)]
    name = pass_info.get("file")
    for entry in passes:
        if name and entry.get("file") == name:
            return dict(entry)
    when = parse_utc(pass_info.get("time_utc"))
    key = method.platform_key(pass_info.get("platform"))
    orbit = pass_info.get("relative_orbit")
    found = []
    for entry in passes:
        start = parse_utc(entry.get("start_utc"))
        if (when is None or start is None or orbit is None or entry.get("relative_orbit") is None
                or method.platform_key(entry.get("platform")) != key or int(entry["relative_orbit"]) != int(orbit)):
            continue
        gap = abs((start - when).total_seconds())
        if gap <= PASS_MATCH_MINUTES * 60:
            found.append((gap, entry))
    return dict(min(found, key=lambda item: item[0])[1]) if found else None


def coverage_record(orbit: int | None, entry: Mapping[str, Any] | None, radar_value_share: float | None) -> dict[str, Any]:
    """The share of the frame a pass covers, and its label: full or partial footprint.

    A pass is on a partial footprint when its relative orbit is one of :data:`PARTIAL_FOOTPRINT_ORBITS` or when the
    catalogue footprint of its scenes covers less than :data:`FULL_FOOTPRINT_MIN_SHARE` of the frame grid.
    """

    footprint = None if entry is None or entry.get("footprint_share_of_grid") is None else float(entry["footprint_share_of_grid"])
    valid = None if entry is None else (entry.get("valid_share") or {}).get("vh")
    partial = (orbit is not None and int(orbit) in PARTIAL_FOOTPRINT_ORBITS) or (footprint is not None and footprint < FULL_FOOTPRINT_MIN_SHARE)
    seen = "an unmeasured share" if radar_value_share is None else f"{radar_value_share:.0%}"
    grid_share = "an unrecorded share" if footprint is None else f"{footprint:.0%}"
    if partial:
        text = (f"partial footprint: the pass's scenes cover {grid_share} of the frame grid (catalogue) and the radar has a "
                f"value on {seen} of the frame land that terrain does not answer; its totals are not comparable with passes "
                "of other orbits, only with passes of its own orbit or on the land every pass sees")
    else:
        text = (f"full footprint: the pass's scenes cover {grid_share} of the frame grid (catalogue); the radar has a value on "
                f"{seen} of the frame land that terrain does not answer")
    return {"footprint": "partial" if partial else "full", "label": text,
            "catalogue_footprint_share_of_grid": footprint,
            "valid_vh_share_of_grid": None if valid is None else float(valid),
            "radar_value_share_of_frame_land_not_answered_by_terrain": radar_value_share,
            "relative_orbit_with_a_partial_footprint": orbit is not None and int(orbit) in PARTIAL_FOOTPRINT_ORBITS}


def common_area_figures(groups: Mapping[str, Sequence[str]], masks: Mapping[str, Mapping[str, np.ndarray]]) -> dict[str, Any]:
    """The frame figures of each pass on the land every pass of its group sees with radar.

    For a group of passes, the common land is the land of every pass where no pass of the group lacks a radar value
    after (reason ``no_answer_rtc_no_data_after``). Terrain answers and permanent water do not change from pass to
    pass, so a cell of the common land can be flagged on every pass of the group where water is seen.

    Args:
        groups: Group name -> labels of its passes.
        masks: Pass label -> the packed masks of :func:`pack_masks`.
    """

    result: dict[str, Any] = {}
    for name, labels in groups.items():
        labels = [label for label in labels if label in masks]
        if not labels:
            continue
        land: np.ndarray | None = None
        without: np.ndarray | None = None
        for label in labels:   # one mask unpacked at a time: a frame mask is 18 million cells
            here, lacking = unpack_mask(masks[label], "land"), unpack_mask(masks[label], "no_radar")
            land = here if land is None else land & here
            without = lacking if without is None else without | lacking
        common = land & ~without  # type: ignore[operator]
        common_cells = int(common.sum())
        by_pass = []
        for label in labels:
            flagged = {level: int((common & unpack_mask(masks[label], f"flagged_{level}")).sum()) for level in LEVELS}
            by_pass.append({"pass": label, **{f"flooded_land_km2_{level}": km2(flagged[level]) for level in LEVELS},
                            "flagged_share_of_common_land_central": share(flagged["central"], common_cells)})
        result[name] = {"passes": list(labels), "common_land_cells": common_cells, "common_land_km2": km2(common_cells),
                        "common_land_share_of_frame_land": share(common_cells, int(land.sum())),  # type: ignore[union-attr]
                        "by_pass": by_pass}
    return result


def pack_masks(masks: Mapping[str, np.ndarray]) -> dict[str, Any]:
    """Pack boolean masks into bits, to keep the masks of many passes in memory."""

    shape = next(iter(masks.values())).shape
    return {"shape": shape, **{name: np.packbits(np.asarray(mask, dtype=bool).ravel()) for name, mask in masks.items()}}


def unpack_mask(packed: Mapping[str, Any], name: str) -> np.ndarray:
    """One mask of :func:`pack_masks`, unpacked."""

    shape = tuple(packed["shape"])
    return np.unpackbits(packed[name], count=int(np.prod(shape))).astype(bool).reshape(shape)


# ---------------------------------------------------------------------------
# Gauges
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """One reading of a gauge series: Thai wall-clock time and the three fields (``None`` when empty)."""

    time: datetime
    level_m_msl: float | None
    gauge_height_m: float | None
    discharge_m3_s: float | None


def gauge_index(news_record: Mapping[str, Any] | None, summary_record: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], str]:
    """The gauge stations and their files: from the news record's ``gauge_records`` (in Git), else the gauge summary."""

    stations: list[dict[str, Any]] = []
    if news_record and news_record.get("gauge_records"):
        for entry in news_record["gauge_records"]:
            stored = entry.get("file_outside_git") or {}
            stations.append({
                "station": str(entry.get("station")), "agency": entry.get("agency"), "place": entry.get("place"),
                "river": entry.get("river"), "file": stored.get("name"), "sha256_recorded": stored.get("sha256"),
                "reading_step": entry.get("reading_step"), "retrieved_at_utc": entry.get("retrieved_at_utc"),
                "peak_m_msl": entry.get("peak_m_msl"), "peak_times_thai_time": list(entry.get("peak_times_thai_time") or []),
                "levels_m_msl": {name: value.get("level_m_msl") for name, value in (entry.get("levels") or {}).items()
                                 if isinstance(value, Mapping)},
            })
        return stations, f"{NEWS_RECORD} (gauge_records)"
    if summary_record and summary_record.get("stations"):
        for entry in summary_record["stations"]:
            stored = entry.get("csv_file") or {}
            summary = entry.get("summary") or {}
            stations.append({
                "station": str(entry.get("code")), "agency": entry.get("agency"), "place": entry.get("place"),
                "river": entry.get("river"), "file": stored.get("name"), "sha256_recorded": stored.get("sha256"),
                "reading_step": None, "retrieved_at_utc": entry.get("retrieved_at_utc"),
                "peak_m_msl": summary.get("peak_msl"), "peak_times_thai_time": list(summary.get("peak_times_local") or []),
                "levels_m_msl": {name: value.get("level_msl") for name, value in (summary.get("levels") or {}).items()
                                 if isinstance(value, Mapping)},
            })
        return stations, f"the consequence lane's {GAUGE_SUMMARY_NAME}"
    return [], "no gauge index found"


def _number(text: str | None) -> float | None:
    if text is None or not str(text).strip():
        return None
    value = float(text)
    return value if math.isfinite(value) else None


def read_gauge_csv(path: Path) -> list[Reading]:
    """A gauge series of the consequence lane (``datetime_thai_time,level_m_msl,gauge_height_m,discharge_m3_s``).

    Raises:
        TimeSeriesError: for a file without these columns or a time that cannot be read.
    """

    refuse_firewall([path])
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or any(name not in reader.fieldnames for name in GAUGE_COLUMNS):
            raise TimeSeriesError(f"{path.name}: a gauge series has the columns {GAUGE_COLUMNS}")
        readings = []
        for row in reader:
            try:
                when = datetime.strptime(row["datetime_thai_time"].strip(), "%Y-%m-%d %H:%M")
            except ValueError as error:
                raise TimeSeriesError(f"{path.name}: a time is not YYYY-MM-DD HH:MM: {row['datetime_thai_time']!r}") from error
            readings.append(Reading(when, _number(row["level_m_msl"]), _number(row["gauge_height_m"]), _number(row["discharge_m3_s"])))
    readings.sort(key=lambda reading: reading.time)
    return readings


def value_at(readings: Sequence[Reading], when: datetime, name: str, *,
             max_gap_minutes: float = GAUGE_INTERPOLATION_MAX_GAP_MINUTES) -> dict[str, Any]:
    """The value of one field at a Thai wall-clock time: the reading at that minute, or a linear interpolation.

    The two readings are the nearest with a value at or before and at or after the time; they are used when at most
    ``max_gap_minutes`` apart. Otherwise the value is ``None`` and ``how`` says why.
    """

    valued = [reading for reading in readings if getattr(reading, name) is not None]
    times = [reading.time for reading in valued]
    if not valued:
        return {"value": None, "how": "no reading with a value"}
    after_index = bisect_left(times, when)
    before_index = bisect_right(times, when) - 1
    before = valued[before_index] if before_index >= 0 else None
    after = valued[after_index] if after_index < len(valued) else None
    if before is not None and before.time == when:
        return {"value": round(float(getattr(before, name)), 3), "how": f"the reading of {before.time:%Y-%m-%d %H:%M}"}
    if before is None or after is None:
        return {"value": None, "how": "the time lies outside the series"}
    gap = (after.time - before.time).total_seconds() / 60.0
    if gap > max_gap_minutes:
        return {"value": None, "how": f"no interpolation: the readings with a value around the time are {gap:.0f} minutes apart "
                                      f"(more than {max_gap_minutes:.0f})"}
    weight = (when - before.time).total_seconds() / (after.time - before.time).total_seconds()
    value = float(getattr(before, name)) + weight * (float(getattr(after, name)) - float(getattr(before, name)))
    return {"value": round(value, 3), "how": f"linear between the readings of {before.time:%Y-%m-%d %H:%M} and {after.time:%Y-%m-%d %H:%M}"}


def nearest_reading(readings: Sequence[Reading], when: datetime, *, max_minutes: float = GAUGE_NEAREST_MAX_MINUTES) -> dict[str, Any] | None:
    """The reading with a level nearest to a Thai wall-clock time, within ``max_minutes``; ``None`` when there is none."""

    valued = [reading for reading in readings if reading.level_m_msl is not None]
    if not valued:
        return None
    best = min(valued, key=lambda reading: (abs((reading.time - when).total_seconds()), reading.time))
    minutes = (best.time - when).total_seconds() / 60.0
    if abs(minutes) > max_minutes:
        return None
    return {"time_thai": best.time.strftime("%Y-%m-%d %H:%M"), "minutes_from_the_time": round(minutes, 1),
            "level_m_msl": round(float(best.level_m_msl), 3)}  # type: ignore[arg-type]


def gauges_at(stations: Sequence[Mapping[str, Any]], folder: Path, times: Sequence[tuple[str, datetime]]
              ) -> tuple[list[dict[str, Any]], dict[str, list[Reading]]]:
    """Read each station's series and its levels at the given times (``label``, UTC instant).

    Returns the station records and the readings of each station that was read (for the chart).
    """

    out: list[dict[str, Any]] = []
    series: dict[str, list[Reading]] = {}
    for station in stations:
        entry = {key: station[key] for key in ("station", "agency", "place", "river", "reading_step", "retrieved_at_utc",
                                               "peak_m_msl", "peak_times_thai_time", "levels_m_msl")}
        name = station.get("file")
        path = None if not name else folder / str(name)
        if path is None or not path.is_file():
            out.append({**entry, "file": {"name": name, "read": False, "why": "the series file is not in the gauge folder"}, "at_passes": []})
            continue
        refuse_firewall([path])
        digest = sha256_file(path)
        if station.get("sha256_recorded") and digest != station["sha256_recorded"]:
            out.append({**entry, "file": {"name": name, "sha256": digest, "read": False,
                                          "why": "the file's SHA-256 is not the one the index records"}, "at_passes": []})
            continue
        readings = read_gauge_csv(path)
        series[str(station["station"])] = readings
        rows = []
        for label, instant in times:
            local = thai_naive(instant)
            values = {name_: value_at(readings, local, name_) for name_ in GAUGE_FIELDS}
            level = values["level_m_msl"]["value"]
            rows.append({
                "pass": label, "time_thai": local.strftime("%Y-%m-%d %H:%M"), "level_m_msl": level,
                "how": values["level_m_msl"]["how"],
                "gauge_height_m": values["gauge_height_m"]["value"], "discharge_m3_s": values["discharge_m3_s"]["value"],
                "nearest_reading_with_a_level": nearest_reading(readings, local),
                "level_minus_m": {name_: None if level is None or value is None else round(level - float(value), 3)
                                  for name_, value in entry["levels_m_msl"].items()},
            })
        out.append({**entry, "file": {"name": name, "sha256": digest, "read": True, "readings": len(readings),
                                      "readings_with_a_level": sum(1 for reading in readings if reading.level_m_msl is not None)},
                    "at_passes": rows})
    return out, series


# ---------------------------------------------------------------------------
# The chart (PIL)
# ---------------------------------------------------------------------------

SURFACE = (252, 252, 251)
INK = (11, 11, 11)
INK_2 = (82, 81, 78)
INK_3 = (150, 149, 144)
GRID_INK = (228, 227, 223)
ORBIT_STYLES: dict[int, tuple[str, str]] = {62: ("#2a78d6", "circle"), 99: ("#eb6834", "square"), 135: ("#1baf7a", "triangle"),
                                            172: ("#eda100", "diamond")}
"""Relative orbit -> categorical slot 1 to 4 of the reference palette (fixed, in orbit order) and a marker shape."""
STATION_COLOURS: tuple[str, ...] = ("#e87ba4", "#008300", "#4a3aa7", "#e34948")
"""Slots 5 to 8 of the reference palette, in the order of :data:`CHART_STATIONS` (the orbits hold slots 1 to 4)."""
OTHER_STYLE = ("#52514e", "cross")
SCALE = 2


def _rgb(text: str) -> tuple[int, int, int]:
    text = text.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _font(size: int) -> Any:
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size * SCALE)
    except TypeError:  # an old Pillow without scalable default fonts
        return ImageFont.load_default()


def nice_ticks(low: float, high: float, target: int = 5) -> list[float]:
    """Round tick values covering ``low`` to ``high`` (steps of 1, 2, 2.5 or 5 times a power of ten)."""

    if not high > low:
        high = low + 1.0
    span = high - low
    magnitude = 10 ** math.floor(math.log10(span / target))
    step = magnitude
    for multiple in (1, 2, 2.5, 5, 10):
        step = multiple * magnitude
        if span / step <= target:
            break
    start = math.floor(low / step + 1e-9) * step
    ticks = []
    value = start
    while value < high - 1e-9 * step:
        ticks.append(round(value, 10))
        value += step
    ticks.append(round(value, 10))
    return ticks


def _marker(draw: Any, shape: str, x: float, y: float, radius: float, colour: tuple[int, int, int], hollow: bool) -> None:
    width = 2 * SCALE
    fill = SURFACE if hollow else colour
    if shape == "circle":
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=fill, outline=colour, width=width)
    elif shape == "square":
        r = radius * 0.9
        draw.rectangle([x - r, y - r, x + r, y + r], fill=fill, outline=colour, width=width)
    elif shape == "triangle":
        points = [(x, y - radius * 1.1), (x + radius, y + radius * 0.8), (x - radius, y + radius * 0.8)]
        draw.polygon(points, fill=fill, outline=colour, width=width)
    elif shape == "diamond":
        points = [(x, y - radius * 1.15), (x + radius, y), (x, y + radius * 1.15), (x - radius, y)]
        draw.polygon(points, fill=fill, outline=colour, width=width)
    else:
        draw.line([(x - radius, y - radius), (x + radius, y + radius)], fill=colour, width=width)
        draw.line([(x - radius, y + radius), (x + radius, y - radius)], fill=colour, width=width)


def draw_chart(path: Path, passes: Sequence[Mapping[str, Any]], gauges: Mapping[str, Sequence[tuple[datetime, float]]],
               window: tuple[datetime, datetime], *, title: str, notes: Sequence[str], bank_name: str = BANK_LEVEL) -> dict[str, Any]:
    """Draw the chart: the land each pass's map flags (top) and the gauge levels (bottom), on one time axis.

    Args:
        path: The PNG to write.
        passes: One dict per pass: ``time`` (Thai wall clock), ``orbit``, ``partial``, ``footprint`` (share of the
            grid or ``None``), ``lower``, ``central``, ``upper`` (km2, or ``None`` when there is no map) and ``mark``
            (a short text under the marker, or ``None``).
        gauges: Station -> (Thai wall-clock time, level minus the bank level in m), in time order.
        window: First and last Thai wall-clock time of the axis.
        title: The title line.
        notes: The note lines under the chart.

    Returns:
        The file's size and SHA-256.
    """

    from PIL import Image, ImageDraw

    width, height = 1400 * SCALE, 900 * SCALE
    image = Image.new("RGB", (width, height), SURFACE)
    draw = ImageDraw.Draw(image)
    f_title, f_text, f_small = _font(19), _font(14), _font(12)
    left, right = 100 * SCALE, 1190 * SCALE
    top_a, bottom_a = 120 * SCALE, 450 * SCALE
    top_b, bottom_b = 540 * SCALE, 780 * SCALE
    start, end = window
    total = max((end - start).total_seconds(), 1.0)

    def x_of(when: datetime) -> float:
        return left + (when - start).total_seconds() / total * (right - left)

    draw.text((left, 24 * SCALE), title, font=f_title, fill=INK)
    # The time axis: a tick a day, a label every second day, and a line at each pass.
    day = datetime(start.year, start.month, start.day)
    count = 0
    while day <= end:
        if day >= start:
            x = x_of(day)
            for top, bottom in ((top_a, bottom_a), (top_b, bottom_b)):
                draw.line([(x, bottom), (x, bottom + 5 * SCALE)], fill=INK_3, width=SCALE)
            if count % 2 == 0:
                text = day.strftime("%d %b").lstrip("0")
                draw.text((x - draw.textlength(text, font=f_small) / 2, bottom_b + 10 * SCALE), text, font=f_small, fill=INK_2)
            count += 1
        day += timedelta(days=1)
    draw.text((left, bottom_b + 32 * SCALE), "Date (Thai time, 2025)", font=f_small, fill=INK_2)
    for item in passes:
        x = x_of(item["time"])
        for y in range(top_a, bottom_b, 10 * SCALE):
            draw.line([(x, y), (x, min(y + 4 * SCALE, bottom_b))], fill=GRID_INK, width=SCALE)

    # Panel A: flooded land of the frame per pass.
    values = [value for item in passes for value in (item.get("lower"), item.get("central"), item.get("upper")) if value is not None]
    ticks = nice_ticks(0.0, max(values) if values and max(values) > 0 else 1.0)
    low, high = ticks[0], ticks[-1]

    def y_a(value: float) -> float:
        return bottom_a - (value - low) / (high - low) * (bottom_a - top_a)

    for tick in ticks:
        y = y_a(tick)
        draw.line([(left, y), (right, y)], fill=GRID_INK, width=SCALE)
        text = f"{tick:g}"
        draw.text((left - 10 * SCALE - draw.textlength(text, font=f_small), y - 8 * SCALE), text, font=f_small, fill=INK_2)
    draw.line([(left, bottom_a), (right, bottom_a)], fill=INK_3, width=SCALE)
    draw.text((left, top_a - 34 * SCALE), "Land the frozen M1-z map flags in the 35 tambons (km2): marker central map, bar lower to upper",
              font=f_text, fill=INK)
    if not values:
        draw.text((left + 20 * SCALE, (top_a + bottom_a) / 2), "No map of a pass is drawn here.", font=f_text, fill=INK_2)
    for item in passes:
        if item.get("central") is None:
            continue
        colour_text, shape = ORBIT_STYLES.get(int(item["orbit"]) if item.get("orbit") is not None else -1, OTHER_STYLE)
        colour = _rgb(colour_text)
        x = x_of(item["time"])
        if item.get("lower") is not None and item.get("upper") is not None:
            draw.line([(x, y_a(item["lower"])), (x, y_a(item["upper"]))], fill=colour, width=2 * SCALE)
            for value in (item["lower"], item["upper"]):
                draw.line([(x - 5 * SCALE, y_a(value)), (x + 5 * SCALE, y_a(value))], fill=colour, width=2 * SCALE)
        y = y_a(item["central"])
        _marker(draw, shape, x, y, 6 * SCALE, colour, bool(item.get("partial")))
    # Under the axis: the footprint share of each partial pass, then the mark of a pass (the case N1 input).
    for item in passes:
        x = x_of(item["time"])
        if item.get("partial") and item.get("footprint") is not None:
            text = f"{item['footprint']:.0%}"
            draw.text((x - draw.textlength(text, font=f_small) / 2, bottom_a + 8 * SCALE), text, font=f_small, fill=INK_2)
        if item.get("mark") and item.get("central") is not None:
            draw.text((x - draw.textlength(item["mark"], font=f_small) / 2, bottom_a + 26 * SCALE), item["mark"], font=f_small, fill=INK_2)
    # Legend of panel A, at the right.
    legend_x, legend_y = right + 20 * SCALE, top_a
    draw.text((legend_x, legend_y), "Relative orbit", font=f_text, fill=INK)
    shown = sorted({int(item["orbit"]) for item in passes if item.get("orbit") is not None})
    for row, orbit in enumerate(shown):
        colour_text, shape = ORBIT_STYLES.get(orbit, OTHER_STYLE)
        y = legend_y + (28 + 24 * row) * SCALE
        _marker(draw, shape, legend_x + 8 * SCALE, y + 8 * SCALE, 6 * SCALE, _rgb(colour_text), False)
        draw.text((legend_x + 22 * SCALE, y), f"{orbit}", font=f_small, fill=INK)
    y = legend_y + (36 + 24 * len(shown)) * SCALE
    _marker(draw, "circle", legend_x + 8 * SCALE, y + 8 * SCALE, 6 * SCALE, INK_2, True)
    draw.text((legend_x + 22 * SCALE, y), "hollow: partial", font=f_small, fill=INK)
    draw.text((legend_x + 22 * SCALE, y + 18 * SCALE), "footprint; % under", font=f_small, fill=INK)
    draw.text((legend_x + 22 * SCALE, y + 36 * SCALE), "the axis: share of", font=f_small, fill=INK)
    draw.text((legend_x + 22 * SCALE, y + 54 * SCALE), "the grid it covers", font=f_small, fill=INK)

    # Panel B: gauge levels against the bank level.
    draw.text((left, top_b - 34 * SCALE), f"Nan River gauges, thaiwater.net: level minus the station's {bank_name} field (m)",
              font=f_text, fill=INK)
    drawn = {name: points for name, points in gauges.items() if points}
    if drawn:
        levels = [value for points in drawn.values() for _when, value in points]
        ticks_b = nice_ticks(min(min(levels), 0.0), max(max(levels), 0.0))
        low_b, high_b = ticks_b[0], ticks_b[-1]

        def y_b(value: float) -> float:
            return bottom_b - (value - low_b) / (high_b - low_b) * (bottom_b - top_b)

        for tick in ticks_b:
            y = y_b(tick)
            draw.line([(left, y), (right, y)], fill=GRID_INK, width=SCALE)
            text = f"{tick:g}"
            draw.text((left - 10 * SCALE - draw.textlength(text, font=f_small), y - 8 * SCALE), text, font=f_small, fill=INK_2)
        y0 = y_b(0.0)
        for x in range(left, right, 12 * SCALE):
            draw.line([(x, y0), (min(x + 6 * SCALE, right), y0)], fill=INK_2, width=SCALE)
        draw.text((left + 6 * SCALE, y0 - 20 * SCALE), f"{bank_name} field", font=f_small, fill=INK_2)
        ends: list[tuple[float, str, tuple[int, int, int]]] = []
        for index, name in enumerate(CHART_STATIONS):
            points = drawn.get(name)
            if not points:
                continue
            colour = _rgb(STATION_COLOURS[index % len(STATION_COLOURS)])
            pieces: list[list[tuple[float, float]]] = []
            previous: datetime | None = None
            for when, value in points:
                if when < start or when > end:
                    continue
                if previous is None or (when - previous).total_seconds() > GAUGE_INTERPOLATION_MAX_GAP_MINUTES * 60:
                    pieces.append([])   # a gap of more than 3 hours without a level breaks the line
                pieces[-1].append((x_of(when), y_b(value)))
                previous = when
            for piece in pieces:
                if len(piece) >= 2:
                    draw.line(piece, fill=colour, width=2 * SCALE, joint="curve")
                elif piece:
                    draw.ellipse([piece[0][0] - 2 * SCALE, piece[0][1] - 2 * SCALE, piece[0][0] + 2 * SCALE, piece[0][1] + 2 * SCALE], fill=colour)
            if pieces:
                ends.append((pieces[-1][-1][1], name, colour))
        # Direct labels at the right end of each line, nudged apart, and a legend row.
        placed: list[float] = []
        for end_y, name, colour in sorted(ends):
            y = end_y
            while any(abs(y - other) < 18 * SCALE for other in placed):
                y += 18 * SCALE
            placed.append(y)
            draw.line([(right + 4 * SCALE, end_y), (right + 10 * SCALE, y)], fill=INK_3, width=SCALE)   # a connector, not data
            draw.line([(right + 10 * SCALE, y), (right + 20 * SCALE, y)], fill=colour, width=2 * SCALE)
            draw.text((right + 24 * SCALE, y - 8 * SCALE), name, font=f_small, fill=INK)
        draw.line([(left, bottom_b), (right, bottom_b)], fill=INK_3, width=SCALE)
    else:
        draw.text((left + 20 * SCALE, (top_b + bottom_b) / 2), "No gauge series was found.", font=f_text, fill=INK_2)
    for row, text in enumerate(notes):
        draw.text((left, bottom_b + (54 + 18 * row) * SCALE), text, font=f_small, fill=INK_2)
    final = image.resize((width // SCALE, height // SCALE), Image.Resampling.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    final.save(path, format="PNG", optimize=True)
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": sha256_bytes(data), "width": final.width, "height": final.height}


def chart_gauge_points(series: Mapping[str, Sequence[Reading]], stations: Sequence[Mapping[str, Any]]) -> dict[str, list[tuple[datetime, float]]]:
    """Station -> (time, level minus its bank level) for the chart stations whose index gives a bank level."""

    banks = {str(station["station"]): (station.get("levels_m_msl") or {}).get(BANK_LEVEL) for station in stations}
    points: dict[str, list[tuple[datetime, float]]] = {}
    for name in CHART_STATIONS:
        bank = banks.get(name)
        if name not in series or bank is None:
            continue
        points[name] = [(reading.time, float(reading.level_m_msl) - float(bank)) for reading in series[name] if reading.level_m_msl is not None]
    return points


# ---------------------------------------------------------------------------
# The stage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Paths:
    """Where the stage reads and writes; :func:`default_paths` gives the paths of the case."""

    root: Path
    external: Path | None
    maps_dir: Path
    frame_dir: Path
    gauge_dir: Path
    out_json: Path
    out_png: Path


def default_paths(external: Path, *, root: Path = ROOT, maps_dir: Path | None = None, frame_dir: Path | None = None,
                  gauge_dir: Path | None = None, out_json: Path | None = None, out_png: Path | None = None) -> Paths:
    return Paths(root=root, external=external, maps_dir=maps_dir or external / MAPS_DIR, frame_dir=frame_dir or external / FRAME_DIR,
                 gauge_dir=gauge_dir or external / GAUGE_DIR, out_json=out_json or root / OUT_JSON, out_png=out_png or root / OUT_PNG)


def _optional_json(path: Path) -> Any:
    refuse_firewall([path])
    return read_json(path) if path.is_file() else None


def _record_ref(path: Path, root: Path) -> dict[str, Any] | None:
    return {"path": label_path(path, root, None), "sha256": sha256_file(path)} if path.is_file() else None


def read_frame_inputs(paths: Paths) -> dict[str, Any]:
    """The protocol, the frame record, the unit raster and the demand cells, each checked (no map is opened)."""

    protocol = read_json(paths.root / PROTOCOL)
    if protocol.get("schema") != chain_rules.NAN_PROTOCOL_SCHEMA:
        raise TimeSeriesError(f"{PROTOCOL} is not {chain_rules.NAN_PROTOCOL_SCHEMA}")
    grid = chain_rules.grid_from_record(protocol["grid"]["frame"])
    frame = read_json(paths.root / FRAME_RECORD)
    stated = (frame.get("unit_raster") or {}).get("grid")
    if stated is not None and chain_rules.grid_from_record(stated) != grid:
        raise TimeSeriesError("the grid of the frame record's unit raster is not the protocol's frame grid")
    units = frame_units(frame)
    files = frame.get("files_outside_git") or {}
    unit_raster, unit_record = read_unit_raster(paths.frame_dir / UNIT_RASTER_NAME, grid, units,
                                                (frame.get("unit_raster") or {}).get("sha256") or (files.get("unit_raster") or {}).get("sha256"))
    demand, demand_record = read_demand(paths.frame_dir / DEMAND_NAME, grid, (files.get("demand_cells") or {}).get("sha256"))
    unknown = sorted({unit_id for unit_id in demand.unit_ids if unit_id is not None} - {unit.unit_id for unit in units})
    if unknown:
        raise TimeSeriesError(f"demand cells name units the frame record does not list: {unknown[:5]}")
    window = [parse_utc(text) for text in (protocol.get("event") or {}).get("window_utc") or []]
    return {"protocol": protocol, "grid": grid, "frame": frame, "units": units, "unit_raster": unit_raster,
            "unit_record": unit_record, "demand": demand, "demand_record": demand_record,
            "window": (window[0], window[1]) if len(window) == 2 and all(window) else None}


def chart_window(window: tuple[datetime, datetime] | None, times: Sequence[datetime]) -> tuple[datetime, datetime]:
    """The chart's time axis in Thai wall-clock time: the protocol's event window, widened to every pass."""

    instants = list(times)
    if window is not None:
        instants.extend(window)
    if not instants:
        raise TimeSeriesError("the chart needs a time")
    first, last = thai_naive(min(instants)), thai_naive(max(instants))
    return datetime(first.year, first.month, first.day), datetime(last.year, last.month, last.day) + timedelta(days=1)


def build(paths: Paths, *, generated_at: str | None = None, git_commit: str | None = None) -> dict[str, Any]:
    """Run the stage: read the frozen maps of every pass, write the record and the chart, and return the record.

    Raises:
        TimeSeriesError: when the order rule, the firewall or an input check refuses (nothing is written).
    """

    refuse_firewall([paths.maps_dir, paths.frame_dir, paths.gauge_dir, paths.out_json, paths.out_png])
    test_path, freeze_path = paths.root / TEST_RESULT, paths.root / FREEZE
    if not test_path.is_file():
        raise TimeSeriesError(f"the order rule of the Nan protocol: the time series runs after the test, and {TEST_RESULT} does not exist")
    if not freeze_path.is_file():
        raise TimeSeriesError(f"no freeze record {FREEZE}: there is no frozen method whose maps could be read")
    started = generated_at or now_utc()
    freeze_sha256 = sha256_file(freeze_path)
    freeze = read_json(freeze_path)
    test_record = read_json(test_path)
    flood_input = (test_record.get("binding") or {}).get("flood_input_of_case_N1") or {}
    n1_label = flood_input.get("label") if isinstance(flood_input, Mapping) else None
    entries, skipped, index_record = discover_maps(paths.maps_dir, freeze_sha256, paths.root, paths.external)
    if not entries:
        raise TimeSeriesError(f"no frozen map of a Nan pass in {label_path(paths.maps_dir, paths.root, paths.external)}: "
                              "run the maps stage of scripts/nan_case_method.py first")
    inputs = read_frame_inputs(paths)
    grid, units, demand, unit_raster = inputs["grid"], inputs["units"], inputs["demand"], inputs["unit_raster"]
    radar = _optional_json(paths.root / RADAR_RECORD)
    news = _optional_json(paths.root / NEWS_RECORD)
    offsets = method.platform_offsets(paths.root)

    passes: list[dict[str, Any]] = []
    tambon_rows: list[dict[str, Any]] = []
    masks: dict[str, Any] = {}
    for entry in entries:
        try:
            codes, reason = read_map(entry.path, grid)
        except TimeSeriesError as error:
            skipped.append({"map": label_path(entry.path, paths.root, paths.external), "why": str(error)})
            continue
        figures = pass_figures(codes, reason, unit_raster, units, demand, grid)
        del codes, reason
        masks[entry.label] = pack_masks(figures.pop("masks"))
        pass_info = entry.record.get("pass") or {}
        radar_entry = radar_entry_for(pass_info, radar)
        coverage = coverage_record(entry.orbit, radar_entry, figures["frame"]["radar_value_share_of_land_not_answered_by_terrain"])
        passes.append({
            "pass": entry.label, "time_utc": utc_text(entry.time), "time_thai": thai_text(entry.time),
            "platform": entry.platform, "relative_orbit": entry.orbit,
            "orbit_state": None if radar_entry is None else radar_entry.get("orbit_state"),
            "radar_record_key": None if radar_entry is None else radar_entry.get("key"),
            "platform_offset_db_applied_by_the_method": float(offsets.get(method.platform_key(entry.platform), 0.0)),
            "is_the_flood_input_of_case_N1": n1_label is not None and entry.label == n1_label,
            "coverage": coverage,
            "map": {"name": entry.path.name, "sha256": entry.map_sha256, "record": entry.path.with_suffix(".json").name,
                    "record_sha256": entry.record_sha256, "in_the_maps_index": entry.in_the_maps_index},
            "frame": figures["frame"],
            "frame_figures_beside_the_map_record": against_the_map_record(figures["frame"], entry.record),
            "checks": figures["checks"],
        })
        for row in figures["units"]:
            tambon_rows.append(flat_tambon_row(entry.label, row))
    if not passes:
        raise TimeSeriesError("no frozen map of a Nan pass could be read")
    orbit_groups: dict[str, list[str]] = {}
    for item in passes:
        orbit_groups.setdefault(f"relative orbit {item['relative_orbit']}", []).append(item["pass"])
    for item in passes:
        item["passes_of_the_same_orbit"] = orbit_groups[f"relative orbit {item['relative_orbit']}"]
    common = common_area_figures({"every pass": [item["pass"] for item in passes], **orbit_groups}, masks)
    del masks

    stations, index_source = gauge_index(news, _optional_json(paths.gauge_dir / GAUGE_SUMMARY_NAME))
    times = [(item["pass"], parse_utc(item["time_utc"])) for item in passes]
    gauge_rows, series = gauges_at(stations, paths.gauge_dir, times)  # type: ignore[arg-type]
    by_pass = {item["pass"]: {} for item in passes}
    for station in gauge_rows:
        for row in station["at_passes"]:
            by_pass[row["pass"]][station["station"]] = row["level_m_msl"]
    for item in passes:
        item["gauge_levels_m_msl_at_the_pass"] = by_pass[item["pass"]]

    window = chart_window(inputs["window"], [parse_utc(item["time_utc"]) for item in passes])  # type: ignore[misc]
    chart_passes = [{"time": thai_naive(parse_utc(item["time_utc"])), "orbit": item["relative_orbit"],  # type: ignore[arg-type]
                     "partial": item["coverage"]["footprint"] == "partial",
                     "footprint": item["coverage"]["catalogue_footprint_share_of_grid"],
                     **{level: item["frame"]["flooded_land_km2"][level] for level in LEVELS},
                     "mark": "N1 input" if item["is_the_flood_input_of_case_N1"] else None} for item in passes]
    chart = draw_chart(paths.out_png, chart_passes, chart_gauge_points(series, stations), window,
                       title="Nan case N1: frozen M1-z flooded land per Sentinel-1 pass, and Nan River gauges (report only)",
                       notes=["Hollow marker: a pass on a partial radar footprint; its total is low for lack of radar, not of water. "
                              "Compare passes of one orbit.",
                              "Radar: contains modified Copernicus Sentinel data (2025), processed by FloodGuard. Gauges: thaiwater.net "
                              "(Hydro-Informatics Institute).",
                              "Modelled figures for planning; not an official warning. No reference layer is compared here."])

    pass_times = ", ".join(item["time_utc"] for item in passes)
    retrieved = sorted({str(station.get("retrieved_at_utc")) for station in gauge_rows if station.get("retrieved_at_utc")})
    previous = None
    if paths.out_json.is_file():
        try:
            old = read_json(paths.out_json)
            previous = {"sha256": sha256_file(paths.out_json), "generated_at_utc": old.get("generated_at_utc")}
        except (ValueError, UnicodeDecodeError):
            previous = {"sha256": sha256_file(paths.out_json), "generated_at_utc": None}
    record = {
        "schema": SCHEMA,
        "case_id": "N1",
        "generated_at_utc": started,
        "source_timestamp": (f"Sentinel-1 passes {pass_times} (UTC)"
                             + (f"; thaiwater.net gauge series retrieved {', '.join(retrieved)} (readings in Thai time)" if retrieved else "")),
        "confidence_class": "low",
        "confidence_basis": "Flags of the frozen radar method on the passes of one event, with no reference compared here; "
                            "modelled WorldPop 2020 residents; gauge levels read from a public service without a check on the ground.",
        "assumptions": ASSUMPTIONS,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "report_only": True,
        "what_this_is": "The time series of protocol nan_case_protocol_v1 (key time_series): the land the frozen M1-z maps flag and the "
                        "modelled residents inside, per tambon and per Sentinel-1 pass, set beside the Nan River gauge levels at the "
                        "pass times. Figures only; no map is in this file.",
        "protocol": {"path": PROTOCOL, "sha256": sha256_file(paths.root / PROTOCOL),
                     "amendment_1": _record_ref(paths.root / AMENDMENT_1, paths.root)},
        "order": {"test_result": _record_ref(test_path, paths.root), "freeze_record": {"path": FREEZE, "sha256": freeze_sha256},
                  "rule": "The stage runs after the test record exists; a map counts only when its record names this freeze record."},
        "flood_levels_of_the_freeze": freeze.get("flood_levels"),
        "inputs": {
            "frame_record": _record_ref(paths.root / FRAME_RECORD, paths.root),
            "radar_record": _record_ref(paths.root / RADAR_RECORD, paths.root),
            "news_record": _record_ref(paths.root / NEWS_RECORD, paths.root),
            "unit_raster": {"path": label_path(paths.frame_dir / UNIT_RASTER_NAME, paths.root, paths.external), **inputs["unit_record"]},
            "demand_cells": {"path": label_path(paths.frame_dir / DEMAND_NAME, paths.root, paths.external), **inputs["demand_record"]},
            "maps_folder": label_path(paths.maps_dir, paths.root, paths.external),
            "maps_index": index_record,
            "maps_index_note": None if index_record is not None else (
                "No maps index: the maps stage of the method lane has not run, so only the maps the test stage wrote are read."),
            "maps_not_used": skipped,
            "radar_record_passes_without_a_frozen_map": passes_without_a_map(radar, passes),
        },
        "parameters": {
            "grid": grid.as_record(), "cell_km2": CELL_KM2, "levels": list(LEVELS),
            "partial_footprint_orbits": list(PARTIAL_FOOTPRINT_ORBITS), "full_footprint_min_share_of_grid": FULL_FOOTPRINT_MIN_SHARE,
            "gauge_interpolation_max_gap_minutes": GAUGE_INTERPOLATION_MAX_GAP_MINUTES,
            "gauge_nearest_reading_max_minutes": GAUGE_NEAREST_MAX_MINUTES, "thai_time": "UTC+7",
        },
        "passes": passes,
        "common_radar_land": {
            "rule": "For each group of passes (every pass, and the passes of each relative orbit): the frame land where no pass of "
                    "the group lacks a radar value after (reason no_answer_rtc_no_data_after), and the land each pass flags inside it. "
                    "These figures can be compared from pass to pass within the group.",
            "groups": common,
        },
        "gauges": {
            "status": "read" if series else "no gauge series found",
            "index": index_source,
            "folder": label_path(paths.gauge_dir, paths.root, paths.external),
            "source": "thaiwater.net public service of the Hydro-Informatics Institute (HII), read without a login by the consequence lane",
            "stations": gauge_rows,
        },
        "tambon_rows_note": "One row per pass and tambon: land and flooded land (km2), shares of the land, and modelled WorldPop 2020 "
                            "residents in flagged and in no-answer cells. _lower, _central and _upper are the three frozen maps.",
        "tambon_rows": tambon_rows,
        "chart": {"path": label_path(paths.out_png, paths.root, paths.external), **chart,
                  "what": "Top: the land each pass's map flags in the frame (central marker, lower to upper bar), by relative orbit, "
                          "hollow for a partial footprint. Bottom: the gauge levels minus each station's min_bank field."},
        "limits": LIMITS,
        "credits": ["Radar: contains modified Copernicus Sentinel data (2025), processed by FloodGuard (frozen M1-z).",
                    "Residents: WorldPop (www.worldpop.org), University of Southampton, Thailand 100 m 2020, CC BY 4.0. Modelled, not observed.",
                    "Tambons: OCHA / HDX Thailand COD-AB (tha_admin3), valid on 2022-01-22.",
                    "Gauge levels: thaiwater.net, Hydro-Informatics Institute (RID, EGAT and HII stations)."],
        "implementation": implementation(paths.root, git_commit),
        "supersedes": previous,
    }
    record["written"] = write_text(paths.out_json, dumps_record(record, compact=("tambon_rows",)))
    return record


def passes_without_a_map(radar_record: Mapping[str, Any] | None, passes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The event passes of the radar record that no frozen map read here belongs to, with their status and footprint."""

    matched = {item.get("radar_record_key") for item in passes}
    return [{"key": entry.get("key"), "start_utc": entry.get("start_utc"), "relative_orbit": entry.get("relative_orbit"),
             "status_in_the_radar_record": entry.get("status"), "footprint_share_of_grid": entry.get("footprint_share_of_grid")}
            for entry in (radar_record or {}).get("event_passes") or [] if isinstance(entry, Mapping) and entry.get("key") not in matched]


def flat_tambon_row(label: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """One row of ``tambon_rows``: the figures of one tambon on one pass, flat."""

    return {
        "pass": label, "unit_id": row["unit_id"], "unit_name": row["unit_name"], "land_km2": row["land_km2"],
        **{f"flooded_land_km2_{level}": row["flooded_land_km2"][level] for level in LEVELS},
        **{f"flagged_share_of_land_{level}": row["flagged_share_of_land"][level] for level in LEVELS},
        "no_answer_share_of_land": row["no_answer_share_of_land"],
        "no_radar_after_share_of_land": row["no_radar_after_share_of_land"],
        "terrain_answered_share_of_land": row["terrain_answered_share_of_land"],
        "radar_value_share_of_land_not_answered_by_terrain": row["radar_value_share_of_land_not_answered_by_terrain"],
        "residents_2020": row["residents_2020"],
        **{f"residents_in_flagged_cells_{level}": row["residents_in_flagged_cells"][level] for level in LEVELS},
        "residents_in_no_answer_cells": row["residents_in_no_answer_cells"],
    }


def implementation(root: Path, git_commit: str | None) -> dict[str, Any]:
    """The code a run used (SHA-256 as Git holds it) and the library versions."""

    import PIL
    import pyproj
    import rasterio

    return {
        "base_commit": git_commit if git_commit is not None else head_commit(root),
        "script_sha256": code_sha256(Path(__file__)),
        "nan_case_chain_module_sha256": code_sha256(ROOT / "src" / "floodguard" / "nan_case_chain.py"),
        "m1z_module_sha256": code_sha256(ROOT / "src" / "floodguard" / "m1z.py"),
        "method_script_sha256": code_sha256(ROOT / "scripts" / "nan_case_method.py"),
        "line_ends": "LF: the bytes Git holds; a checkout's CRLF line ends are read as LF",
        "software": {"python": python_platform.python_version(), "numpy": np.__version__, "rasterio": rasterio.__version__,
                     "pyproj": pyproj.__version__, "pillow": PIL.__version__},
    }


def check_inputs(paths: Paths, *, chart_preview: Path | None = None) -> dict[str, Any]:
    """Read and check every input that needs no map, and read the gauges at the times of the radar record's passes.

    No map is opened and no flood figure is computed, so the order rule does not stop it; nothing is written in Git.
    """

    refuse_firewall([paths.frame_dir, paths.gauge_dir, chart_preview])
    if chart_preview is not None and Path(chart_preview).resolve().is_relative_to(paths.root.resolve()):
        raise TimeSeriesError("the chart preview of check-inputs is written outside the repository")
    inputs = read_frame_inputs(paths)
    radar = _optional_json(paths.root / RADAR_RECORD)
    news = _optional_json(paths.root / NEWS_RECORD)
    listed = [entry for entry in (radar or {}).get("event_passes") or [] if parse_utc(entry.get("start_utc")) is not None]
    times = [(str(entry.get("key")), parse_utc(entry["start_utc"])) for entry in listed]
    stations, index_source = gauge_index(news, _optional_json(paths.gauge_dir / GAUGE_SUMMARY_NAME))
    gauge_rows, series = gauges_at(stations, paths.gauge_dir, times)  # type: ignore[arg-type]
    result: dict[str, Any] = {
        "inputs_checked": True,
        "computed": "No map was opened and no flood figure was computed.",
        "grid": inputs["grid"].as_record(), "units": len(inputs["units"]), "unit_raster": inputs["unit_record"],
        "demand_cells": inputs["demand_record"],
        "radar_record_event_passes": [{"key": entry.get("key"), "time_thai": thai_text(parse_utc(entry["start_utc"])),  # type: ignore[arg-type]
                                       "relative_orbit": entry.get("relative_orbit"), "status": entry.get("status"),
                                       "coverage": coverage_record(entry.get("relative_orbit"), entry, None)["footprint"],
                                       "footprint_share_of_grid": entry.get("footprint_share_of_grid")} for entry in listed],
        "gauges": {"index": index_source, "stations_read": sorted(series),
                   "levels_at_the_listed_pass_times_m_msl": {station["station"]: {row["pass"]: row["level_m_msl"] for row in station["at_passes"]}
                                                             for station in gauge_rows}},
    }
    if chart_preview is not None:
        window = chart_window(inputs["window"], [instant for _key, instant in times])  # type: ignore[misc]
        chart_passes = [{"time": thai_naive(instant), "orbit": entry.get("relative_orbit"),  # type: ignore[arg-type]
                         "partial": coverage_record(entry.get("relative_orbit"), entry, None)["footprint"] == "partial",
                         "footprint": entry.get("footprint_share_of_grid"), "lower": None, "central": None, "upper": None, "mark": None}
                        for entry, (_key, instant) in zip(listed, times)]
        result["chart_preview"] = draw_chart(Path(chart_preview), chart_passes, chart_gauge_points(series, stations), window,
                                             title="Nan case N1: input check (no map read)", notes=["Preview of the gauge panel; no flood figure."])
    return result


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    commands = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    modes = commands.add_subparsers(dest="mode", required=True)
    for name in ("run", "check-inputs"):
        mode = modes.add_parser(name)
        mode.add_argument("--external-root", type=Path, required=True, help="the external data root (outside Git)")
        mode.add_argument("--repo-root", type=Path, default=ROOT, help="the repository whose records are read (default: this one)")
        mode.add_argument("--maps-dir", type=Path, help="default <external root>/proposal_execution/nan_case_v1/method/maps")
        mode.add_argument("--frame-dir", type=Path, help="default <external root>/proposal_execution/nan_case_v1/frame")
        mode.add_argument("--gauge-dir", type=Path, help="default <external root>/proposal_execution/nan_case_v1/consequence/gauge")
        if name == "run":
            mode.add_argument("--out-json", type=Path, help=f"default {OUT_JSON}")
            mode.add_argument("--out-png", type=Path, help=f"default {OUT_PNG}")
        else:
            mode.add_argument("--chart-preview", type=Path, help="draw the gauge panel to this PNG (outside the repository)")
    return commands


def main(argv: Sequence[str] | None = None) -> int:
    """Run one mode; 0 when it finished, 2 when it refused (nothing written)."""

    args = parser().parse_args(argv)
    paths = default_paths(args.external_root, root=args.repo_root, maps_dir=args.maps_dir, frame_dir=args.frame_dir, gauge_dir=args.gauge_dir,
                          out_json=getattr(args, "out_json", None), out_png=getattr(args, "out_png", None))
    try:
        if args.mode == "run":
            record = build(paths)
            print(json.dumps({"written": label_path(paths.out_json, paths.root, paths.external), **record["written"],
                              "chart": record["chart"]["path"], "chart_sha256": record["chart"]["sha256"],
                              "passes": [item["pass"] for item in record["passes"]],
                              "maps_not_used": record["inputs"]["maps_not_used"]}, indent=2))
        else:
            print(json.dumps(check_inputs(paths, chart_preview=args.chart_preview), indent=2))
    except TimeSeriesError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return EXIT_REFUSED
    return EXIT_DONE


if __name__ == "__main__":
    raise SystemExit(main())
