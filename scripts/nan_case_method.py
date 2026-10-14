"""The Nan case, method M1-z: tune, freeze, test and maps.

The rules are those of ``docs/proposal_execution/nan_case_protocol_v1.json`` (decision log R51); the pure functions
are in ``src/floodguard/m1z.py``. The stages run in this order, and each refuses to run out of it:

``tune``
    Scores every candidate of the protocol's tuned parameters on the tuning sets that are not dropped in
    ``outputs/nan_case/tuning_references_v1.json``, applies the selection rule, the constraint and the tie rule,
    and writes ``outputs/nan_case/tuning_v1.json`` with the full score table. Reads no Nan file. Refuses while
    the two code files have uncommitted changes, so that the tuning runs at a commit that holds the code.

``freeze``
    Writes ``outputs/nan_case/freeze_v1.json``: the selected parameters, the lower and upper flood levels, the
    SHA-256 of the two code files, the commit at which the tuning ran and the score table. Refuses while the two
    code files have uncommitted changes or differ from the code that tuned.

``test``
    Runs once, after the freeze record is committed in HEAD, unchanged and pushed, and the code matches its
    hashes. Tests 1, 1b, 2 and the dry control of the protocol. It is the only stage that opens the JAXA files
    (and, under the fallback, GFM), the THEOS-2 Nan chips, their rule v2 water and their labels. It refuses to start
    while a fetched pass lacks its dry-season statistics, or while the radar record lists event passes that are not
    on disk (unless ``--missing-passes-reason`` is given). It writes the test 1 reference as provided on the frame
    grid into ``method/case_n2_reference/`` (outside Git), the flood input of case N2.

``maps``
    The frozen method at three flood levels on every fetched Nan event pass, after the test result exists.

Examples (from the repository root)::

    python scripts/nan_case_method.py tune --external-root <external-data-root>
    python scripts/nan_case_method.py freeze
    python scripts/nan_case_method.py test --external-root <external-data-root> --theos2-dir <THEOS-2 folder>
    python scripts/nan_case_method.py maps --external-root <external-data-root>

Every figure is agreement with a reference layer, not accuracy. No map is an official warning; nothing here
computes a planning score or a class. Planning guidance only. Rasters stay in the work folder outside Git.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from floodguard import m1z  # noqa: E402

PROTOCOL = "docs/proposal_execution/nan_case_protocol_v1.json"
AMENDMENT_1 = "docs/proposal_execution/nan_case_protocol_v1_amendment_1.json"
AREAS = "outputs/nan_case/areas_v1.json"
TUNING_REFERENCES = "outputs/nan_case/tuning_references_v1.json"
RADAR_RECORD_OF_THE_FRAME = "outputs/nan_case/radar_passes_nan_frame_v1.json"
TUNING = "outputs/nan_case/tuning_v1.json"
FREEZE = "outputs/nan_case/freeze_v1.json"
TEST_RESULT = "outputs/nan_case/test_result_v1.json"
CODE_FILES: tuple[str, ...] = ("src/floodguard/m1z.py", "scripts/nan_case_method.py")
RULE_V2_FREEZE = "outputs/theos2_water_rule_v2/freeze_v1.json"
LABELS_DIR = "outputs/theos2_water_labels"
LABEL_SAMPLE = "sample_v1.json"
LABEL_KEY = "key_v1.json"

CASE = Path("proposal_execution") / "nan_case_v1"
RADAR_DIR = CASE / "radar"
TERRAIN_DIR = CASE / "terrain"
REFERENCES_DIR = CASE / "references_tuning"
SEALED_DIR = CASE / "jaxa_sealed"
WORK = CASE / "method"
MAPS = WORK / "maps"
CASE_N2_REFERENCE = WORK / "case_n2_reference"
"""The test 1 reference as provided, on the frame grid, for case N2 (test 5); written by the test stage only."""
RULE_V2_WORK = Path("proposal_execution") / "theos2_water_rule_v2"
BOUNDARIES = Path("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
UNITS_LAYER = "tha_admin3"

EPSG = 32647
CELL_M = m1z.CELL_M
FRAME_AREA = "nan_frame"
SET_AREAS: dict[str, str] = {
    "sukhothai_theos2_20250730": "sukhothai_chip",
    "mae_sai_20241022": "mae_sai_20241022",
    "chaiyaphum_20210928": "chaiyaphum_20210928",
}
"""Tuning set of the protocol -> area of outputs/nan_case/areas_v1.json (and folder name of the other lanes)."""
CHIP_TOWN, CHIP_DRY = "nan_chip_003", "nan_chip_001"
THEOS2_NAN_IMAGES = {CHIP_TOWN: "IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif", CHIP_DRY: "IMG_T2V_20250731035100_ORTHO_PMS_32-001.tif"}
RULE_V2_CHIP = {CHIP_TOWN: "chip_003", CHIP_DRY: "chip_001"}
THEOS2_NAN_UTC = "2025-07-31T03:51:00Z"
TEST2_PASS_UTC = "2025-07-31T23:08:00Z"
TEST1_FALLBACK_PASS_UTC = "2025-07-28T11:21:00Z"
PASS_MATCH_MINUTES = 60
JAXA_MAPS = {"20250728": "test_1", "20250719": "test_1b"}
GFM_STAC = "https://stac.eodc.eu/api/v1"
GFM_COLLECTION = "GFM"
GFM_FLOOD_ASSET, GFM_EXCLUSION_ASSET = "ensemble_flood_extent", "exclusion_mask"
GFM_NODATA = 255
GFM_WINDOW_MINUTES = 30
PASS_IF_IOU, PASS_IF_NO_ANSWER = 0.40, 0.20
DRY_CONTROL_MAX_SHARE = 0.05
JAXA_MIN_COVER_SHARE = 0.5

FIREWALL_MARKERS: tuple[str, ...] = (
    "jaxa_sealed", "water_v2_chip_001", "water_v2_chip_003", "chip_001_2m", "chip_003_2m", "held_chip_00",
    "IMG_T2V_20250731035100", "theos2_water_labels", "eodc.eu",
)
"""Paths no stage but ``test`` may open (protocol, tuning, never_read_before_the_freeze)."""

ASSUMPTIONS_METHOD = [
    "M1-z is applied as the protocol writes it, on the 20 m grid of each area: z_vh = (VH after dB - dry mean dB) / dry spread dB.",
    "Permanent water is ESA WorldCover 2021 class 80; it is never flagged and is left out of the compared cells of every measure.",
    "The terrain answer comes first: HAND above the limit or a slope of 5 degrees or more is answered not flooded even where the radar has no value.",
    "A cell without a HAND or slope value that terrain does not answer gets no answer; the protocol does not name this case, it is a data gap.",
    "The no-answer share and the binding IoU are counted on the compared cells only; a cell without an answer counts as not flagged in the binding IoU.",
]
LIMITS = [
    "C-band radar does not see water under trees, between buildings or under rice canopy, nor water that drained before the pass.",
    "The references are other maps (optical water read by a fixed rule, an agency layer, another satellite's map), not ground checks.",
    "Every figure is agreement with a reference layer, not accuracy. Planning guidance only; not an official warning.",
]


class StageError(RuntimeError):
    """A stage refuses to run: the order of the protocol is broken or an input does not fit."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def now_utc() -> str:
    """The time now, UTC, to the second."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    """SHA-256 of a file's bytes."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dumps_record(record: Mapping[str, Any], compact: Sequence[str] = ()) -> str:
    """JSON text with indent 1, LF line ends; the top-level lists named in ``compact`` hold one element per line."""

    body = dict(record)
    parts: dict[str, list[Any]] = {}
    for key in compact:
        if key in body and isinstance(body[key], list):
            parts[key] = body[key]
            body[key] = f"@@{key}@@"
    text = json.dumps(body, indent=1, ensure_ascii=False)
    for key, rows in parts.items():
        inner = ",\n  ".join(json.dumps(row, ensure_ascii=False) for row in rows)
        text = text.replace(json.dumps(f"@@{key}@@"), "[\n  " + inner + "\n ]" if rows else "[]")
    return text + "\n"


def write_record(path: Path, record: Mapping[str, Any], compact: Sequence[str] = ()) -> None:
    """Write a JSON record as UTF-8 with LF line ends, so its SHA-256 is that of the bytes Git holds."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps_record(record, compact).encode("utf-8"))


def read_amendment(root: Path) -> dict[str, Any] | None:
    """Amendment 1 of the protocol, or ``None`` when it is not in the tree."""

    path = root / AMENDMENT_1
    return read_json(path) if path.is_file() else None


def platform_offsets(root: Path) -> dict[str, float]:
    """Amendment 1: the dB added to VV and VH of an event pass, by platform (for example ``sentinel-1c``)."""

    amendment = read_amendment(root)
    if amendment is None or "platform_offset" not in amendment.get("changes", {}):
        return {}
    return {str(key).lower(): float(value) for key, value in amendment["changes"]["platform_offset"]["offset_db"].items()}


def platform_key(platform: str | None) -> str:
    """``Sentinel-1C``, ``S1C`` or ``sentinel-1c`` read as ``sentinel-1c``."""

    text = str(platform or "").strip().lower().replace(" ", "")
    match = re.search(r"(?:sentinel-?|s)1([a-d])", text)
    return f"sentinel-1{match.group(1)}" if match else text


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def envelope(source_timestamp: str, confidence_class: str, assumptions: Sequence[str]) -> dict[str, Any]:
    """The fields every FloodGuard record carries."""

    return {"generated_at_utc": now_utc(), "source_timestamp": source_timestamp, "confidence_class": confidence_class,
            "assumptions": list(assumptions), "official_warning": False, "operational_status": "non_operational",
            "can_feed_decision_layer": False}


class Log:
    """Print a line and append it to a log file in the work folder, if there is one."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, message: str) -> None:
        line = f"{now_utc()} {message}"
        print(line, flush=True)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")


def guard(path: Path | str, stage: str) -> None:
    """Refuse to open a path behind the firewall in any stage but ``test``."""

    if stage == "test":
        return
    text = str(path).replace("\\", "/")
    for marker in FIREWALL_MARKERS:
        if marker in text:
            raise StageError(f"stage {stage} may not open {text}: it lies behind the firewall of the protocol until the test")
    if stage == "tune" and f"/{FRAME_AREA}/" in text + "/":
        raise StageError(f"stage tune may not open a file of the Nan frame: {text}")


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------


def _git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a read-only git command in ``root``."""

    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=False, env=_git_env())


def head_commit(root: Path) -> str | None:
    found = git(root, "rev-parse", "HEAD")
    return found.stdout.decode().strip() if found.returncode == 0 else None


def uncommitted(root: Path, paths: Sequence[str]) -> list[str]:
    """The paths among ``paths`` that differ from HEAD or are not tracked."""

    found = git(root, "status", "--porcelain", "--untracked-files=all", "--", *paths)
    if found.returncode != 0:
        raise StageError(f"git status failed in {root}: {found.stderr.decode().strip()}")
    return [line[3:].strip() for line in found.stdout.decode().splitlines() if line.strip()]


def same_as_head(root: Path, path: str) -> bool:
    """True when ``path`` is in the HEAD commit and the file on disk holds the same bytes."""

    found = git(root, "show", f"HEAD:{path}")
    return found.returncode == 0 and (root / path).is_file() and (root / path).read_bytes() == found.stdout


def pushed_commit(root: Path, path: str) -> str | None:
    """The last commit that touched ``path``, when a remote-tracking branch holds it; else ``None``."""

    found = git(root, "log", "-1", "--format=%H", "--", path)
    commit = found.stdout.decode().strip()
    if found.returncode != 0 or not commit:
        return None
    remote = git(root, "branch", "-r", "--contains", commit)
    return commit if remote.returncode == 0 and remote.stdout.decode().strip() else None


def code_hashes(root: Path) -> dict[str, str]:
    return {name: sha256_file(root / name) for name in CODE_FILES}


# ---------------------------------------------------------------------------
# Grids and rasters
# ---------------------------------------------------------------------------

Grid = tuple[float, float, int, int]


def area_grid(areas: Mapping[str, Any], key: str) -> Grid:
    entry = areas["areas"].get(key)
    if entry is None:
        raise StageError(f"{AREAS} names no area {key}")
    grid = entry["grid"]
    return float(grid["west"]), float(grid["north"]), int(grid["rows"]), int(grid["cols"])


def grid_transform(grid: Grid) -> Any:
    from rasterio.transform import from_origin

    return from_origin(grid[0], grid[1], CELL_M, CELL_M)


def check_grid(source: Any, grid: Grid, path: Path) -> None:
    """Refuse a raster that is not on ``grid`` (EPSG:32647, 20 m, same corner and size)."""

    west, north, rows, columns = grid
    transform = source.transform
    if source.crs is None or source.crs.to_epsg() != EPSG:
        raise StageError(f"{path.name} is not in EPSG:{EPSG}")
    if (abs(transform.a - CELL_M) > 1e-6 or abs(transform.e + CELL_M) > 1e-6 or abs(transform.c - west) > 1e-3
            or abs(transform.f - north) > 1e-3 or source.width != columns or source.height != rows):
        raise StageError(f"{path.name} is not on the grid west {west}, north {north}, {rows} rows, {columns} columns at {CELL_M} m")


def band_index(source: Any, name: str, default: int) -> int:
    """The band whose description is ``name``, starts with it, or holds it as a word (as in "gamma0 VH, linear");
    ``default`` when no band is described so."""

    described = [(index + 1, (text or "").strip().lower()) for index, text in enumerate(source.descriptions)]
    word = re.compile(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])")
    for test in (lambda text: text == name, lambda text: text.startswith(name), lambda text: bool(word.search(text))):
        for index, text in described:
            if text and test(text):
                return index
    return default


def read_bands(path: Path, grid: Grid, stage: str, wanted: Mapping[str, int], *, as_float: bool = True) -> dict[str, np.ndarray]:
    """Read the named bands of a raster on ``grid``; no-data becomes NaN when ``as_float``."""

    import rasterio

    guard(path, stage)
    with rasterio.open(path) as source:
        check_grid(source, grid, path)
        out = {}
        for name, default in wanted.items():
            index = band_index(source, name, default)
            if index > source.count:
                raise StageError(f"{path.name} has no band {name}")
            values = source.read(index)
            if as_float:
                values = values.astype("float32")
                if source.nodata is not None and not (isinstance(source.nodata, float) and math.isnan(source.nodata)):
                    values[values == np.float32(source.nodata)] = np.nan
            out[name] = values
        return out


def read_single(path: Path, grid: Grid, stage: str, *, as_float: bool = True) -> np.ndarray:
    return read_bands(path, grid, stage, {"band_1": 1}, as_float=as_float)["band_1"]


def write_map(path: Path, grid: Grid, bands: Sequence[tuple[str, np.ndarray]]) -> str:
    """Write uint8 bands on ``grid`` as a tiled, DEFLATE-compressed GeoTIFF; returns its SHA-256."""

    import rasterio

    west, north, rows, columns = grid
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=rows, width=columns, count=len(bands), dtype="uint8", nodata=m1z.NO_ANSWER,
                       crs=f"EPSG:{EPSG}", transform=grid_transform(grid), compress="deflate", tiled=True,
                       blockxsize=256, blockysize=256) as target:
        for index, (name, values) in enumerate(bands, start=1):
            target.write(np.asarray(values, dtype="uint8"), index)
            target.set_band_description(index, name)
    return sha256_file(path)


def first_existing(folder: Path, names: Sequence[str]) -> Path | None:
    """The first of ``names`` (file names or glob patterns) that exists in ``folder``."""

    for name in names:
        if any(character in name for character in "*?["):
            found = sorted(folder.glob(name))
            if found:
                return found[0]
        elif (folder / name).is_file():
            return folder / name
    return None


def area_folder(base: Path, names: Sequence[str]) -> Path | None:
    for name in names:
        if (base / name).is_dir():
            return base / name
    return None


# ---------------------------------------------------------------------------
# Passes and inputs (the files of the radar, terrain and reference lanes)
# ---------------------------------------------------------------------------

TIME_KEYS = ("datetime", "pass_utc", "pass_datetime_utc", "start_utc", "acquired_utc", "start_datetime", "time_utc", "sensing_start_utc", "start")
ORBIT_KEYS = ("relative_orbit", "sat:relative_orbit", "orbit")
PLATFORM_KEYS = ("platform", "satellite", "mission")


def parse_time(text: Any) -> datetime | None:
    """A UTC time from an ISO text or a compact stamp such as 20250731T230815; a time without zone is read as UTC."""

    if not isinstance(text, str):
        return None
    value = text.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        pass
    match = re.search(r"(20\d{2})-?(\d{2})-?(\d{2})[T_ ]?(\d{2}):?(\d{2})(?::?(\d{2}))?", value)
    if not match:
        return None
    year, month, day, hour, minute, second = (int(part or 0) for part in match.groups())
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError:
        return None


def find_value(value: Any, keys: Sequence[str]) -> Any:
    """The first value under one of ``keys``, searched breadth-first through dictionaries and lists."""

    queue = [value]
    while queue:
        item = queue.pop(0)
        if isinstance(item, Mapping):
            for key in keys:
                if key in item and item[key] not in (None, ""):
                    return item[key]
            queue.extend(item.values())
        elif isinstance(item, list):
            queue.extend(item)
    return None


@dataclass
class EventPass:
    """One fetched event pass of an area, from the files of the radar lane."""

    path: Path
    time: datetime | None
    orbit: int | None
    platform: str | None
    record: Mapping[str, Any] | None

    @property
    def label(self) -> str:
        if self.time is None:
            return self.path.stem
        parts = [self.time.strftime("%Y%m%dT%H%M")]
        if self.orbit is not None:
            parts.append(f"o{self.orbit}")
        if self.platform:
            short = re.sub(r"(?i)sentinel-?", "S", str(self.platform)).replace(" ", "").upper()
            parts.append(short)
        return "_".join(parts)

    def as_json(self) -> dict[str, Any]:
        return {"file": self.path.name, "time_utc": None if self.time is None else self.time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "relative_orbit": self.orbit, "platform": self.platform, "label": self.label}


def describe_pass(path: Path, stage: str) -> EventPass:
    """Time, orbit and platform of an event raster: from the JSON record beside it, its tags, or its name."""

    import rasterio

    guard(path, stage)
    record = None
    for candidate in (path.with_suffix(".json"), path.with_name(path.stem + "_record.json")):
        if candidate.is_file():
            record = read_json(candidate)
            break
    with rasterio.open(path) as source:
        tags = {key.lower(): value for key, value in source.tags().items()}
    sources: list[Any] = [item for item in (record, tags) if item]
    when = None
    for item in sources:
        when = parse_time(find_value(item, TIME_KEYS))
        if when is not None:
            break
    if when is None:
        when = parse_time(path.stem)
    orbit = None
    for item in sources:
        found = find_value(item, ORBIT_KEYS)
        if found is not None:
            try:
                orbit = int(found)
                break
            except (TypeError, ValueError):
                pass
    if orbit is None:
        match = re.search(r"(?:^|[_-])(?:o|orbit|ro|rel_orbit)(\d{1,3})(?=$|[_.-])", path.stem, re.IGNORECASE)
        orbit = int(match.group(1)) if match else None
    platform = None
    for item in sources:
        found = find_value(item, PLATFORM_KEYS)
        if isinstance(found, str):
            platform = found
            break
    if platform is None:
        match = re.search(r"S1([ABCD])", path.stem, re.IGNORECASE)
        platform = f"sentinel-1{match.group(1).lower()}" if match else None
    return EventPass(path=path, time=when, orbit=orbit, platform=platform, record=record)


def discover_passes(folder: Path, stage: str) -> list[EventPass]:
    """Every ``event_*.tif`` of an area folder of the radar lane, oldest first (passes without a time last)."""

    found = [describe_pass(path, stage) for path in sorted(folder.glob("event_*.tif"))]
    return sorted(found, key=lambda item: (item.time is None, item.time or datetime.max.replace(tzinfo=timezone.utc), item.path.name))


def nearest_pass(passes: Sequence[EventPass], when: datetime, *, within_minutes: float | None = None) -> EventPass | None:
    timed = [item for item in passes if item.time is not None]
    if not timed:
        return None
    best = min(timed, key=lambda item: abs((item.time - when).total_seconds()))
    if within_minutes is not None and abs((best.time - when).total_seconds()) > within_minutes * 60:
        return None
    return best


def dry_file(folder: Path, orbit: int | None) -> Path:
    if orbit is not None and (folder / f"dry_o{orbit}.tif").is_file():
        return folder / f"dry_o{orbit}.tif"
    found = sorted(folder.glob("dry_o*.tif"))
    if orbit is None and len(found) == 1:
        return found[0]
    raise StageError(f"no dry-season statistics for orbit {orbit} in {folder}")


def file_record(path: Path) -> dict[str, Any]:
    return {"name": path.name, "sha256": sha256_file(path)}


def load_terrain(external: Path, names: Sequence[str], grid: Grid, stage: str) -> dict[str, Any]:
    """HAND, slope, WorldCover and the permanent water of an area, from the terrain lane's folder."""

    folder = area_folder(external / TERRAIN_DIR, names)
    if folder is None:
        raise StageError(f"no terrain folder for {names[0]} under {external / TERRAIN_DIR}")
    paths = {
        "hand": first_existing(folder, ["hand_m.tif", "*hand*.tif"]),
        "slope": first_existing(folder, ["slope_deg.tif", "*slope*.tif"]),
        "cover": first_existing(folder, ["worldcover.tif", "*worldcover*.tif", "*land_cover*.tif"]),
        "permanent_water": first_existing(folder, ["permanent_water.tif", "*permanent*.tif"]),
    }
    missing = [name for name in ("hand", "slope", "cover") if paths[name] is None]
    if missing:
        raise StageError(f"terrain of {names[0]}: no {', '.join(missing)} in {folder}")
    cover = read_single(paths["cover"], grid, stage, as_float=False).astype("uint8")
    water = cover == m1z.PERMANENT_WATER_CLASS
    disagreement = None
    if paths["permanent_water"] is not None:
        lane = read_single(paths["permanent_water"], grid, stage, as_float=False)
        disagreement = int(((lane == 1) != water).sum())
    return {
        "hand": read_single(paths["hand"], grid, stage), "slope": read_single(paths["slope"], grid, stage), "cover": cover,
        "permanent_water": water, "folder": folder.name,
        "files": {name: file_record(path) for name, path in paths.items() if path is not None},
        "permanent_water_rule": "ESA WorldCover class 80 (protocol); the terrain lane's permanent_water.tif is compared, not used",
        "cells_where_the_lane_permanent_water_differs_from_class_80": disagreement,
    }


EVENT_BANDS = {"vv": 1, "vh": 2}
DRY_BANDS = {"vh_mean_db": 1, "vh_std_db": 2, "vv_mean_db": 3, "vv_std_db": 4, "n_valid": 5}


def load_pass(event: EventPass, grid: Grid, stage: str, *, orbit: int | None = None,
              offsets: Mapping[str, float] | None = None) -> dict[str, Any]:
    """VV and VH of one pass (linear) and the dry-season statistics of its orbit, from the radar lane's folder.

    ``offsets`` (amendment 1) adds a platform's dB to VV and VH of the event pass; the dry-season statistics are not
    changed. The offset applied is recorded under ``platform_offset_db``.
    """

    folder = event.path.parent
    image = read_bands(event.path, grid, stage, EVENT_BANDS)
    offset = float((offsets or {}).get(platform_key(event.platform), 0.0))
    if offset:
        factor = np.float32(10.0 ** (offset / 10.0))
        image = {name: (values * factor).astype("float32") for name, values in image.items()}
    dry_path = dry_file(folder, orbit if orbit is not None else event.orbit)
    dry = read_bands(dry_path, grid, stage, DRY_BANDS)
    return {"vv": image["vv"], "vh": image["vh"], **{name: dry[name] for name in DRY_BANDS},
            "files": {"event": file_record(event.path), "dry_season": file_record(dry_path)}, "pass": event.as_json(),
            "platform_offset_db": offset}


def m1z_levels(inputs: Mapping[str, Any], terrain: Mapping[str, Any], selected: m1z.M1zParameters) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    vh_db = m1z.to_db(inputs["vh"])
    return m1z.classify_levels(vh_db, inputs["vh_mean_db"], inputs["vh_std_db"], inputs["n_valid"], terrain["hand"], terrain["slope"],
                               terrain["cover"], selected, permanent_water=terrain["permanent_water"])


# ---------------------------------------------------------------------------
# Comparators
# ---------------------------------------------------------------------------


def comparator_maps(root: Path, inputs: Mapping[str, Any], terrain: Mapping[str, Any], grid: Grid) -> dict[str, Any]:
    """The comparators of the protocol on one pass. A comparator that cannot run is recorded with the reason."""

    from floodguard import radar_candidates as rc

    out: dict[str, Any] = {}
    slope, water = terrain["slope"], terrain["permanent_water"]
    vh, vv = inputs["vh"], inputs["vv"]
    jobs: dict[str, Callable[[], np.ndarray]] = {
        "r37_frozen_detector": lambda: m1z.frozen_detector_r37(vh, slope, water),
        "r37_simple_threshold": lambda: m1z.simple_threshold_r37(vh, slope, water),
        "un_spider_dry_mean_before": lambda: m1z.un_spider_dry_mean(vh, inputs["vh_mean_db"], slope, water),
    }

    def before() -> np.ndarray:
        return np.stack([np.power(10.0, inputs["vv_mean_db"] / 10.0), np.power(10.0, inputs["vh_mean_db"] / 10.0)]).astype("float32")

    def literal() -> np.ndarray:
        from floodguard import sar_change_v2 as sar

        config = sar.M1LiteralConfig()
        return m1z.on_lattice(before(), np.stack([vv, vh]), lambda a, b: rc.m1_literal_tile(a, b, config), grid_west=grid[0], grid_north=grid[1])

    def version_two() -> np.ndarray:
        from floodguard import geoid_m1_review as review
        from floodguard import sar_change_v2 as sar

        binding = review.require_frozen_m1_v2(root)
        config = sar.m1_v2_config_from_json(binding["parameters"])
        return m1z.on_lattice(before(), np.stack([vv, vh]), lambda a, b: rc.m1_v2_tile(a, b, config), grid_west=grid[0], grid_north=grid[1])

    jobs["m1_literal_dry_mean_before"] = literal
    jobs["m1_v2_dry_mean_before"] = version_two
    for name, job in jobs.items():
        try:
            out[name] = job()
        except Exception as error:  # noqa: BLE001 - a comparator is optional; its failure is recorded
            out[name] = {"not_run": f"{type(error).__name__}: {error}"}
    return out


COMPARATOR_NOTES = {
    "r37_frozen_detector": ("Decision log R37 frozen detector (simple_threshold_cleaned): VH after, a 3 by 3 mean at 20 m (the 5 by 5 at "
                            "10 m), at or below -18.46 dB; flags on slopes of 5 degrees or more dropped, then groups of fewer than 2 cells "
                            "(800 m2), then growth into touching cells within 1.5 dB."),
    "r37_simple_threshold": "Decision log R37 simple threshold: VH after, a 3 by 3 mean at 20 m, at or below -18.46 dB; no cleaning.",
    "un_spider_dry_mean_before": ("UN-SPIDER recommended practice with the dry-season mean of VH as its image before; groups of fewer than "
                                  "2 cells at 20 m (the 8 cells at 10 m)."),
    "m1_literal_dry_mean_before": "M1-literal (frozen configuration) with the dry-season means of VV and VH as the image before, per 10,240 m lattice tile at 20 m.",
    "m1_v2_dry_mean_before": ("M1-v2 (frozen configuration, checked by geoid_m1_review.require_frozen_m1_v2) with the dry-season means as "
                              "the image before, per lattice tile at 20 m."),
}


def score_comparators(maps: Mapping[str, Any], water: np.ndarray, compared: np.ndarray, window: tuple[slice, slice] | None = None) -> dict[str, Any]:
    """:func:`m1z.evaluate` of every comparator that ran, on the same cells."""

    out = {}
    for name, value in maps.items():
        if isinstance(value, dict):
            out[name] = value
            continue
        code = value if window is None else value[window]
        out[name] = m1z.evaluate(code, water, compared)
    return out


# ---------------------------------------------------------------------------
# Stage 1: tune
# ---------------------------------------------------------------------------


def reference_status(record: Mapping[str, Any], set_id: str, area: str) -> dict[str, Any]:
    """Whether the references lane dropped a tuning set, from ``tuning_references_v1.json`` (its keys are read loosely)."""

    containers = [record.get(key) for key in ("sets", "references", "tuning_sets", "areas")]
    entry = None
    for container in containers:
        if isinstance(container, Mapping):
            entry = container.get(set_id) or container.get(area)
        elif isinstance(container, list):
            entry = next((item for item in container if isinstance(item, Mapping)
                          and {item.get(key) for key in ("id", "set_id", "area", "name")} & {set_id, area}), None)
        if entry is not None:
            break
    if entry is None:
        return {"listed": False, "dropped": True, "reason": f"{TUNING_REFERENCES} does not list the set", "entry": None}
    status = str(entry.get("status", "")).lower()
    reason = entry.get("drop_reason") or entry.get("dropped_reason") or entry.get("reason_dropped")
    dropped = bool(entry.get("dropped")) or status.startswith("dropped") or bool(reason) or entry.get("usable") is False
    return {"listed": True, "dropped": dropped, "reason": reason or (status if dropped else None), "entry": entry}


def recorded_sha256(entry: Any, file_name: str) -> str | None:
    """A SHA-256 the references record gives for ``file_name``, wherever it sits in the entry."""

    queue = [entry]
    while queue:
        item = queue.pop(0)
        if isinstance(item, Mapping):
            keyed = item.get(file_name)
            if isinstance(keyed, Mapping) and isinstance(keyed.get("sha256"), str):
                return keyed["sha256"]
            names = [str(item.get(key, "")) for key in ("name", "file", "path", "raster")]
            if any(name.replace("\\", "/").endswith(file_name) for name in names) and isinstance(item.get("sha256"), str):
                return item["sha256"]
            queue.extend(item.values())
        elif isinstance(item, list):
            queue.extend(item)
    return None


def load_tuning_set(external: Path, set_id: str, area: str, areas: Mapping[str, Any], status: Mapping[str, Any]) -> dict[str, Any]:
    """Radar, terrain and reference of one tuning set on its grid."""

    stage = "tune"
    grid = area_grid(areas, area)
    names = [area, set_id]
    radar = area_folder(external / RADAR_DIR, names)
    if radar is None:
        raise StageError(f"no radar folder for {area}")
    passes = discover_passes(radar, stage)
    if not passes:
        raise StageError(f"no event_*.tif in {radar}")
    event_entry = areas["areas"][area].get("event", {})
    wanted = parse_time(event_entry.get("pass_utc"))
    chosen = nearest_pass(passes, wanted, within_minutes=PASS_MATCH_MINUTES) if wanted is not None else None
    if chosen is None:
        if len(passes) != 1:
            raise StageError(f"{radar}: no event pass within {PASS_MATCH_MINUTES} minutes of {event_entry.get('pass_utc')}")
        chosen = passes[0]
    orbit = areas["areas"][area].get("dry_season", {}).get("relative_orbit") or event_entry.get("relative_orbit") or chosen.orbit
    inputs = load_pass(chosen, grid, stage, orbit=orbit)
    terrain = load_terrain(external, names, grid, stage)
    folder = area_folder(external / REFERENCES_DIR, names)
    reference_path = None if folder is None else first_existing(folder, ["reference_20m.tif", "*reference*20m*.tif"])
    if reference_path is None:
        raise StageError(f"no reference_20m.tif for {area} under {external / REFERENCES_DIR}")
    expected = recorded_sha256(status.get("entry"), reference_path.name)
    actual = sha256_file(reference_path)
    if expected is not None and expected != actual:
        raise StageError(f"{reference_path} is not the reference {TUNING_REFERENCES} records")
    reference = read_single(reference_path, grid, stage, as_float=False)
    return {"grid": grid, "inputs": inputs, "terrain": terrain, "reference": reference, "pass": chosen,
            "reference_file": {"name": reference_path.name, "sha256": actual, "sha256_recorded_by_the_references_lane": expected}}


def score_set(data: Mapping[str, Any], candidates: Sequence[m1z.M1zParameters]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every candidate's figures on one tuning set, and the set's description."""

    inputs, terrain = data["inputs"], data["terrain"]
    water, compared = m1z.reference_cells(data["reference"], exclude=terrain["permanent_water"])
    vh_db = m1z.to_db(inputs["vh"])
    z = m1z.z_score(vh_db, inputs["vh_mean_db"], inputs["vh_std_db"])
    statics: dict[tuple[float, float | None], np.ndarray] = {}
    flags: dict[tuple[float, float], np.ndarray] = {}
    rows = []
    for candidate in candidates:
        key_static = (candidate.hand_max_m, candidate.dry_spread_max_db)
        if key_static not in statics:
            statics[key_static] = m1z.static_reasons(vh_db, inputs["vh_mean_db"], inputs["vh_std_db"], inputs["n_valid"], terrain["hand"],
                                                     terrain["slope"], terrain["cover"], hand_max_m=candidate.hand_max_m,
                                                     dry_spread_max_db=candidate.dry_spread_max_db, permanent_water=terrain["permanent_water"])
        key_flag = (candidate.z_vh_max, candidate.vh_after_max_db)
        if key_flag not in flags:
            flags[key_flag] = m1z.radar_flag(vh_db, z, candidate.z_vh_max, candidate.vh_after_max_db)
        code, _reason = m1z.finish(statics[key_static], flags[key_flag])
        rows.append(m1z.evaluate(code, water, compared))
    described = {
        "compared_cells": int(compared.sum()), "reference_water_cells": int((compared & water).sum()),
        "reference_cells_left_out_as_permanent_water": int((np.isin(data["reference"], (0, 1)) & terrain["permanent_water"]).sum()),
        "grid": dict(zip(("west", "north", "rows", "cols"), data["grid"])), "pass": data["pass"].as_json(),
        "inputs": {**data["inputs"]["files"], **{f"terrain_{name}": entry for name, entry in terrain["files"].items()},
                   "reference": data["reference_file"]},
        "terrain_folder": terrain["folder"],
        "cells_where_the_lane_permanent_water_differs_from_class_80": terrain["cells_where_the_lane_permanent_water_differs_from_class_80"],
    }
    return rows, described


SHORT = {"iou_no_answer_as_not_flagged": "iou", "iou_answered_cells": "iou_answered", "flagged_that_is_reference_water": "on_water",
         "reference_water_flagged_no_answer_as_not_flagged": "water_flagged", "no_answer_share": "no_answer_share", "true_positive": "tp", "false_positive": "fp",
         "false_negative_answered": "fn_answered", "no_answer_reference_water": "no_answer_water", "no_answer_cells": "no_answer",
         "compared_cells": "compared"}


def table_row(parameters: m1z.M1zParameters, per_set: Mapping[str, Mapping[str, Any]], score: float | None, meets: bool) -> dict[str, Any]:
    return {**parameters.as_json(), "score": score, "meets_the_constraint": meets,
            "sets": {set_id: {short: figures[long] for long, short in SHORT.items()} for set_id, figures in per_set.items()}}


def stage_tune(root: Path, arguments: argparse.Namespace, hooks: Mapping[str, Any]) -> dict[str, Any]:
    external = Path(arguments.external_root)
    log = Log(external / WORK / "tune.log")
    if (root / TEST_RESULT).exists():
        raise StageError("the test result exists: the method is never tuned again after the test")
    replace = bool(arguments.replace and arguments.reason)
    if arguments.replace and not arguments.reason:
        raise StageError("--replace needs --reason")
    if (root / FREEZE).exists() and not replace:
        raise StageError(f"{FREEZE} exists: tuning again needs --replace with --reason, and the freeze must then be made again")
    if (root / TUNING).exists() and not replace:
        raise StageError(f"{TUNING} exists; use --replace with --reason")
    dirty = uncommitted(root, CODE_FILES)
    if dirty:
        raise StageError(f"commit the code first: the tuning must run at a commit that holds it (uncommitted: {', '.join(dirty)})")
    for name in (PROTOCOL, AREAS, TUNING_REFERENCES):
        if not (root / name).is_file():
            raise StageError(f"{name} is missing")
    protocol, areas, references = read_json(root / PROTOCOL), read_json(root / AREAS), read_json(root / TUNING_REFERENCES)
    candidates = m1z.candidate_grid(protocol["method"]["tuned_parameters"])
    rule = protocol["tuning"]
    limit = re.search(r"at most ([0-9.]+)", str(rule.get("constraint", "")))
    max_share = float(limit.group(1)) if limit else m1z.MAX_NO_ANSWER_SHARE
    amendment = read_amendment(root)
    floor_margin = None
    if amendment is not None and "tuning_constraint" in amendment.get("changes", {}):
        floor_margin = float(amendment["changes"]["tuning_constraint"]["margin"])
    log(f"tune: {len(candidates)} candidates; constraint "
        + (f"amendment 1: at most {floor_margin} above each set's lowest no-answer share" if floor_margin is not None else f"at most {max_share}"))

    sets: dict[str, Any] = {}
    datas: dict[str, dict[str, Any]] = {}
    per_candidate: list[dict[str, Any]] = [{} for _ in candidates]
    comparators: dict[str, Any] = {}
    for entry in rule["sets"]:
        set_id = entry["id"]
        area = SET_AREAS.get(set_id, set_id)
        status = reference_status(references, set_id, area)
        if status["dropped"] and "drop_rule" not in entry:
            raise StageError(f"{TUNING_REFERENCES} drops or does not list {set_id} ({status['reason']}), but the protocol gives that set no "
                             "drop rule: the owner decides before anything is tuned")
        if status["dropped"]:
            sets[set_id] = {"used": False, "area": area, "dropped": True, "reason": status["reason"], "listed_in_the_references_record": status["listed"]}
            log(f"tune: {set_id} dropped: {status['reason']}")
            continue
        try:
            data = load_tuning_set(external, set_id, area, areas, status)
        except StageError as error:
            if "drop_rule" not in entry:
                raise
            sets[set_id] = {"used": False, "area": area, "dropped": True, "reason": f"dropped by its drop rule: {error}"}
            log(f"tune: {set_id} dropped by its drop rule: {error}")
            continue
        started = time.time()
        rows, described = score_set(data, candidates)
        for index, figures in enumerate(rows):
            per_candidate[index][set_id] = figures
        water, compared = m1z.reference_cells(data["reference"], exclude=data["terrain"]["permanent_water"])
        comparators[set_id] = {"scores": score_comparators(comparator_maps(root, data["inputs"], data["terrain"], data["grid"]), water, compared)}
        sets[set_id] = {"used": True, "area": area, **described}
        datas[set_id] = data
        log(f"tune: {set_id} scored in {time.time() - started:.0f} s ({described['compared_cells']} compared cells)")
    used = [set_id for set_id, entry in sets.items() if entry["used"]]
    if not used:
        raise StageError("no tuning set can be used: nothing is tuned")

    scored = [{"parameters": candidate.as_json(), "sets": per_candidate[index]} for index, candidate in enumerate(candidates)]
    limits_by_set = m1z.no_answer_limits_from_floor(scored, floor_margin) if floor_margin is not None else None
    selection = m1z.select_parameters(scored, max_no_answer_share=max_share, max_no_answer_by_set=limits_by_set)
    if limits_by_set is not None:
        selection["constraint_rule"] = "amendment 1: in every set, a no-answer share at most 0.10 above the lowest share any candidate reaches on that set"

    def limit_of(set_id: str) -> float:
        return limits_by_set[set_id] if limits_by_set is not None else max_share

    table = []
    for index, candidate in enumerate(candidates):
        score = m1z.mean_score(per_candidate[index])
        meets = all(per_candidate[index][set_id]["no_answer_share"] is not None
                    and per_candidate[index][set_id]["no_answer_share"] <= limit_of(set_id) + 1e-12 for set_id in used)
        table.append(table_row(candidate, per_candidate[index], score, meets))

    shares = {set_id: [per_candidate[index][set_id]["no_answer_share"] for index in range(len(candidates))] for set_id in used}
    selection["no_answer_share_range_by_set"] = {set_id: [min(values), max(values)] if all(value is not None for value in values) else None
                                                 for set_id, values in shares.items()}
    selected_detail: dict[str, Any] = {}
    if selection["selected"] is not None:
        chosen = m1z.M1zParameters.from_json(selection["selected"])
        for set_id in used:
            data = datas[set_id]
            water, compared = m1z.reference_cells(data["reference"], exclude=data["terrain"]["permanent_water"])
            levels = m1z_levels(data["inputs"], data["terrain"], chosen)
            code, reason = levels["central"]
            selected_detail[set_id] = {
                "central": m1z.evaluate(code, water, compared),
                "by_worldcover_group": m1z.evaluate_by_cover(code, water, compared, data["terrain"]["cover"]),
                "interval_95": m1z.tile_bootstrap(code, water, compared),
                "lower": m1z.evaluate(levels["lower"][0], water, compared), "upper": m1z.evaluate(levels["upper"][0], water, compared),
                "reasons_on_compared_cells": m1z.reason_counts(reason, compared),
            }
            better = {name: figures["iou_no_answer_as_not_flagged"] for name, figures in comparators[set_id]["scores"].items()
                      if isinstance(figures, dict) and figures.get("iou_no_answer_as_not_flagged") is not None
                      and figures["iou_no_answer_as_not_flagged"] > (selected_detail[set_id]["central"]["iou_no_answer_as_not_flagged"] or 0)}
            comparators[set_id]["better_than_the_selected_m1z_by_iou"] = better

    source = "; ".join(f"{set_id}: pass {entry['pass']['time_utc']}" for set_id, entry in sets.items() if entry["used"])
    record = {
        "schema": "floodguard.nan_case_tuning.v1",
        **envelope(source, "low", [
            *ASSUMPTIONS_METHOD,
            "The tuning reads the three tuning sets of the protocol only; no file of the Nan frame and no sealed reference is opened.",
            "Score: the mean over the sets used of IoU with no-answer cells counted as not flagged; constraint: "
            + (f"a no-answer share at most {floor_margin} above the lowest share any candidate reaches on that set, in every set used "
               "(amendment 1 of the protocol)." if floor_margin is not None else f"a no-answer share of at most {max_share} in every set used."),
            "Ties: every eligible candidate within 0.01 of the best score; the most negative z limit, then the most negative VH limit, then "
            "the smallest HAND limit, then the smallest dry spread limit (no limit counts as the largest).",
        ]),
        "confidence_basis": "Limits chosen on three other events with references that are other maps, not ground checks.",
        "what_this_is": ("The score of every candidate parameter set of M1-z on the tuning sets of the Nan case protocol, and the choice by "
                         "its rule. Agreement with each set's reference, not accuracy."),
        "protocol": {"path": PROTOCOL, "sha256": sha256_file(root / PROTOCOL)},
        "areas_record": {"path": AREAS, "sha256": sha256_file(root / AREAS)},
        "tuning_references_record": {"path": TUNING_REFERENCES, "sha256": sha256_file(root / TUNING_REFERENCES)},
        "code_sha256": code_hashes(root),
        "git_commit_at_tuning": head_commit(root),
        "code_committed_at_tuning": True,
        "how_the_files_were_found": ("The other lanes' files are found by name: radar/<area>/event_*.tif (time, orbit and platform from the "
                                     "JSON beside it, its tags or its name) and dry_o<orbit>.tif; terrain/<area>/hand_m.tif, slope_deg.tif, "
                                     "worldcover.tif, permanent_water.tif (glob fallbacks); references_tuning/<area>/reference_20m.tif."),
        "sets": sets,
        "sets_used": used,
        "candidates": len(candidates),
        "tuned_parameters": protocol["method"]["tuned_parameters"],
        "fixed": {"min_dry_passes": m1z.MIN_DRY_PASSES, "max_slope_deg": m1z.MAX_SLOPE_DEG, "min_group_cells": m1z.MIN_GROUP_CELLS,
                  "connectivity": "8", "permanent_water_class": m1z.PERMANENT_WATER_CLASS,
                  "no_answer_cover_classes_at_low_hand": [m1z.BUILT_UP_CLASS, m1z.TREE_COVER_CLASS], "cell_m": CELL_M},
        "selection": selection,
        "selected_on_each_set": selected_detail,
        "comparators": {"what": COMPARATOR_NOTES, "rule": "a comparator that does better is reported, never renamed as the result", "by_set": comparators},
        "score_table_columns": {"sets": {short: long for long, short in SHORT.items()}},
        "score_table": table,
        "limits": LIMITS,
        "supersedes": superseded(root / TUNING, arguments),
    }
    write_record(root / TUNING, record, compact=("score_table",))
    log(f"tune: selected {selection['selected']} with score {selection.get('selected_score')}; eligible {selection['eligible']} of {len(candidates)}")
    return record


def superseded(path: Path, arguments: argparse.Namespace) -> dict[str, Any] | None:
    """What a ``--replace`` run replaces: the old record's time and SHA-256, and the reason given."""

    if not path.exists():
        return None
    old = read_json(path)
    return {"reason": arguments.reason, "generated_at_utc": old.get("generated_at_utc"), "sha256": sha256_file(path)}


# ---------------------------------------------------------------------------
# Stage 2: freeze
# ---------------------------------------------------------------------------


def stage_freeze(root: Path, arguments: argparse.Namespace, hooks: Mapping[str, Any]) -> dict[str, Any]:
    if (root / TEST_RESULT).exists():
        raise StageError("the test result exists: the method is never frozen again after the test")
    if arguments.replace and not arguments.reason:
        raise StageError("--replace needs --reason")
    if (root / FREEZE).exists() and not arguments.replace:
        raise StageError(f"{FREEZE} exists; use --replace with --reason")
    dirty = uncommitted(root, CODE_FILES)
    if dirty:
        raise StageError(f"the code has uncommitted changes: {', '.join(dirty)}")
    if not (root / TUNING).is_file():
        raise StageError("no tuning record: run the tune stage first")
    tuning = read_json(root / TUNING)
    if tuning.get("code_sha256") != code_hashes(root):
        raise StageError("the code differs from the code that tuned: tune again")
    if tuning.get("protocol", {}).get("sha256") != sha256_file(root / PROTOCOL):
        raise StageError("the protocol changed after the tuning")
    selected = tuning.get("selection", {}).get("selected")
    if selected is None:
        raise StageError(f"the tuning selected nothing ({tuning.get('selection', {}).get('why')}); the protocol gives no rule for this case")
    chosen = m1z.M1zParameters.from_json(selected)
    levels = m1z.flood_levels(chosen)
    record = {
        "schema": "floodguard.nan_case_freeze.v1",
        **envelope(tuning.get("source_timestamp", ""), "low", [
            *ASSUMPTIONS_METHOD,
            "The parameters are those the tuning record selected by the protocol's rule; nothing is chosen here.",
            "Lower flood = the selected z limit minus 0.5; upper flood = plus 0.5; the other parameters as selected.",
        ]),
        "confidence_basis": "Frozen on three other events; the Nan references have not been opened.",
        "what_this_is": ("The frozen M1-z of the Nan case: parameters, flood levels and the SHA-256 of the code that applies them, fixed "
                         "before any reference of the case is read."),
        "held_out_references_read": False,
        "protocol": {"path": PROTOCOL, "sha256": sha256_file(root / PROTOCOL)},
        "tuning_record": {"path": TUNING, "sha256": sha256_file(root / TUNING)},
        "git_commit_at_tuning": tuning.get("git_commit_at_tuning"),
        "git_commit_at_freeze": head_commit(root),
        "code_sha256": code_hashes(root),
        "selected": chosen.as_json(),
        "selection": tuning.get("selection"),
        "flood_levels": {name: level.as_json() for name, level in levels.items()},
        "fixed": tuning.get("fixed"),
        "comparators_fixed": COMPARATOR_NOTES,
        "sets_used": tuning.get("sets_used"),
        "score_table": tuning.get("score_table", []),
        "limits": LIMITS,
        "supersedes": superseded(root / FREEZE, arguments),
    }
    write_record(root / FREEZE, record, compact=("score_table",))
    print(f"freeze: {chosen.as_json()}; commit and push {FREEZE} and {TUNING} before the test", flush=True)
    return record


# ---------------------------------------------------------------------------
# The order checks of the test and maps stages
# ---------------------------------------------------------------------------


def require_frozen(root: Path) -> dict[str, Any]:
    """The freeze record, after checking that it is committed, unchanged, pushed and matches the code and protocol."""

    if not (root / FREEZE).is_file():
        raise StageError("no freeze record: run tune and freeze, then commit and push")
    if not same_as_head(root, FREEZE):
        raise StageError(f"{FREEZE} is not in the HEAD commit or differs from it: commit it unchanged")
    if pushed_commit(root, FREEZE) is None:
        raise StageError(f"the commit of {FREEZE} is on no remote branch: push it before the test")
    freeze = read_json(root / FREEZE)
    if freeze.get("code_sha256") != code_hashes(root):
        raise StageError("the code differs from the code the freeze record binds")
    if freeze.get("protocol", {}).get("sha256") != sha256_file(root / PROTOCOL):
        raise StageError("the protocol differs from the one the freeze record binds")
    if not (root / TUNING).is_file() or freeze.get("tuning_record", {}).get("sha256") != sha256_file(root / TUNING):
        raise StageError("the tuning record differs from the one the freeze record binds")
    return freeze


# ---------------------------------------------------------------------------
# The frame, JAXA and GFM (test stage only)
# ---------------------------------------------------------------------------


def frame_units_mask(path: Path, grid: Grid, district_pcodes: Sequence[str]) -> tuple[np.ndarray, dict[str, Any]]:
    """The cells whose centre lies inside the frame's units (COD-AB tha_admin3 of the three districts)."""

    import pyogrio
    from rasterio.features import rasterize

    units = pyogrio.read_dataframe(path, layer=UNITS_LAYER)
    units = units[units["adm2_pcode"].isin(list(district_pcodes))]
    if units.empty:
        raise StageError(f"{path.name}: no unit of {list(district_pcodes)}")
    units = units.to_crs(EPSG)
    mask = rasterize(((geometry, 1) for geometry in units.geometry if geometry is not None and not geometry.is_empty),
                     out_shape=(grid[2], grid[3]), transform=grid_transform(grid), fill=0, dtype="uint8", all_touched=False) == 1
    return mask, {"file": path.name, "layer": UNITS_LAYER, "units": int(len(units)),
                  "units_by_district": {str(key): int(value) for key, value in units.groupby("adm2_pcode").size().items()},
                  "cells_inside": int(mask.sum())}


OBS_PATTERN = re.compile(r"obs(?:ervation)?[\s_-]*(?:area|extent|frame|range|region|zone|boundary|footprint)|\bobservation\b|footprint|coverage"
                         r"|swath|outline|\baoi\b|scene[\s_-]*(?:frame|area|extent|footprint|outline|boundary)", re.IGNORECASE)
"""Names of an observation area. "Observed flood" is not one."""
OTHER_PATTERN = re.compile(r"perman|reference[\s_-]*water|normal[\s_-]*water|usual[\s_-]*water|pre[-_ ]?(?:flood|event)|river|lake", re.IGNORECASE)
"""Layer names of water that is not flood (set aside)."""
OTHER_VALUE = re.compile(r"\s*(?:(?:permanent|normal|reference|usual|pre[-_ ]?(?:flood|event))[\s_-]*water(?:[\s_-]*bod(?:y|ies))?s?|rivers?|lakes?)\s*",
                         re.IGNORECASE)
"""A whole attribute value that names water that is not flood."""


def observation_text(value: str) -> bool:
    """An attribute value or a name that points to an observation area and not to flood."""

    return bool(OBS_PATTERN.search(value)) and "flood" not in value.lower()
SCENE_PATTERN = re.compile(r"ALOS2\d{6,}-\d{6}")
ZONED_TIME = re.compile(r"(20\d{2}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?\s*(Z|UTC|GMT|JST|[+-]\d{2}:?\d{2})", re.IGNORECASE)


def zoned_times(text: str) -> list[datetime]:
    """Times with an explicit zone in a text (Z, UTC, GMT, JST or an offset), as UTC. A time without a zone is not read."""

    out = []
    for date, clock, zone in ZONED_TIME.findall(text):
        zone = zone.upper()
        offset = {"Z": "+00:00", "UTC": "+00:00", "GMT": "+00:00", "JST": "+09:00"}.get(zone, zone if ":" in zone else f"{zone[:3]}:{zone[3:]}")
        try:
            out.append(datetime.fromisoformat(f"{date}T{clock}{offset}").astimezone(timezone.utc))
        except ValueError:
            continue
    return out


def inspect_jaxa(zip_path: Path) -> dict[str, Any]:
    """The layers of a JAXA zip: flood polygons, observation-area polygons, times with a zone, and scene identifiers.

    A layer whose name points to an observation area (observation, footprint, coverage, scene, swath, outline)
    is an observation area; one that points to permanent or reference water is set aside; every other polygon
    layer holds flood polygons. Inside a flood layer, a feature whose text says observation area is one.
    """

    import geopandas as gpd
    import pandas as pd
    import pyogrio

    record: dict[str, Any] = {"file": zip_path.name, "layers": []}
    flood, observed = [], []
    times: list[datetime] = []
    scenes: set[str] = set()
    with zipfile.ZipFile(zip_path) as archive:
        members = archive.namelist()
        for member in members:
            scenes.update(SCENE_PATTERN.findall(member))
            if member.lower().endswith((".txt", ".xml", ".csv", ".htm", ".html", ".prj", ".md")):
                text = archive.read(member).decode("utf-8", errors="ignore")
                scenes.update(SCENE_PATTERN.findall(text))
                times.extend(zoned_times(text))
    vectors = [member for member in members if member.lower().endswith((".geojson", ".json", ".shp", ".gpkg", ".kml"))]
    for member in vectors:
        source = f"/vsizip/{zip_path.as_posix()}/{member}"
        try:
            frame = pyogrio.read_dataframe(source)
        except Exception as error:  # noqa: BLE001 - recorded
            record["layers"].append({"member": member, "read": False, "error": f"{type(error).__name__}: {error}"})
            continue
        crs_given = frame.crs is not None
        if not crs_given:
            frame = frame.set_crs(4326)
        text_columns = [column for column in frame.columns if column != frame.geometry.name
                        and (pd.api.types.is_object_dtype(frame[column]) or pd.api.types.is_string_dtype(frame[column]))]
        for column in text_columns:
            for value in frame[column].dropna().astype(str).unique()[:200]:
                scenes.update(SCENE_PATTERN.findall(value))
                times.extend(zoned_times(value))
        polygons = frame[frame.geometry.notna() & frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        name = Path(member).stem
        is_obs = np.zeros(len(polygons), dtype=bool)
        is_other = np.zeros(len(polygons), dtype=bool)
        if observation_text(name):
            kind = "observation_area"
            is_obs[:] = True
        elif OTHER_PATTERN.search(name):
            kind = "set_aside"
            is_other[:] = True
        else:
            kind = "flood"
            for column in text_columns:
                values = polygons[column].astype(str).fillna("")
                is_obs |= values.map(observation_text).to_numpy(dtype=bool)
                is_other |= values.map(lambda text: bool(OTHER_VALUE.fullmatch(text))).to_numpy(dtype=bool)
            is_other &= ~is_obs
        observed.append(polygons[is_obs])
        flood.append(polygons[~is_obs & ~is_other])
        record["layers"].append({"member": member, "read": True, "kind": kind, "features": int(len(frame)), "polygons": int(len(polygons)),
                                 "observation_polygons": int(is_obs.sum()), "set_aside_polygons": int(is_other.sum()),
                                 "flood_polygons": int((~is_obs & ~is_other).sum()),
                                 "geometry_types": sorted({str(item) for item in frame.geometry.geom_type.dropna().unique()}),
                                 "crs": str(frame.crs) if crs_given else "none given: read as EPSG:4326",
                                 "fields": [str(column) for column in frame.columns if column != frame.geometry.name]})

    def joined(parts: list[Any]) -> Any:
        parts = [part.to_crs(EPSG) for part in parts if len(part)]
        return None if not parts else gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=f"EPSG:{EPSG}")

    record["scene_identifiers"] = sorted(scenes)
    record["times_with_a_zone_utc"] = sorted({item.strftime("%Y-%m-%dT%H:%M:%SZ") for item in times})
    return {"record": record, "flood": joined(flood), "observed": joined(observed), "times": sorted(set(times))}


def rasterize_polygons(frame: Any, grid: Grid) -> np.ndarray:
    """Polygons on the grid by cell centre."""

    from rasterio.features import rasterize

    if frame is None or not len(frame):
        return np.zeros((grid[2], grid[3]), dtype=bool)
    shapes = ((geometry, 1) for geometry in frame.geometry if geometry is not None and not geometry.is_empty)
    return rasterize(shapes, out_shape=(grid[2], grid[3]), transform=grid_transform(grid), fill=0, dtype="uint8", all_touched=False) == 1


def lonlat_bounds(grid: Grid) -> list[float]:
    from pyproj import Transformer

    west, north, rows, columns = grid
    transformer = Transformer.from_crs(EPSG, 4326, always_xy=True)
    return [round(value, 6) for value in transformer.transform_bounds(west, north - rows * CELL_M, west + columns * CELL_M, north)]


def read_remote_on_grid(href: str, grid: Grid, *, nodata: int = GFM_NODATA, tries: int = 6) -> np.ndarray:
    """A remote raster put on the grid by nearest neighbour, read by window over HTTPS."""

    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    options = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MAX_RETRY": "6", "GDAL_HTTP_RETRY_DELAY": "4"}
    for attempt in range(tries):
        try:
            with rasterio.Env(**options), rasterio.open(href) as source:
                with WarpedVRT(source, crs=f"EPSG:{EPSG}", transform=grid_transform(grid), width=grid[3], height=grid[2],
                               resampling=Resampling.nearest, src_nodata=source.nodata if source.nodata is not None else nodata,
                               nodata=nodata) as warped:
                    return warped.read(1).astype("uint8")
        except Exception:  # noqa: BLE001 - the host times out now and then
            if attempt == tries - 1:
                raise
            time.sleep(min(60, 10 * (attempt + 1)))
    raise StageError("unreachable")


def fetch_gfm(grid: Grid, start: datetime, end: datetime) -> dict[str, Any] | None:
    """GFM ensemble flood extent and exclusion mask of the items between two times, on the grid; ``None`` without items."""

    from floodguard import s1_rtc

    body: dict[str, Any] = {"collections": [GFM_COLLECTION], "bbox": lonlat_bounds(grid),
                            "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}", "limit": 100}
    features: list[dict[str, Any]] = []
    page = s1_rtc.fetch_json(f"{GFM_STAC}/search", body=body)
    for _ in range(20):
        features.extend(page.get("features", []))
        follow = next((link for link in page.get("links", []) if link.get("rel") == "next"), None)
        if follow is None:
            break
        page = s1_rtc.fetch_json(follow["href"], body=follow.get("body")) if follow.get("method", "GET").upper() == "POST" else s1_rtc.fetch_json(follow["href"])
    features = [item for item in features if GFM_FLOOD_ASSET in item.get("assets", {}) and GFM_EXCLUSION_ASSET in item.get("assets", {})]
    if not features:
        return None
    features.sort(key=lambda item: (item["properties"].get("datetime", ""), item["id"]))
    flood = np.full((grid[2], grid[3]), GFM_NODATA, dtype="uint8")
    exclusion = np.full((grid[2], grid[3]), GFM_NODATA, dtype="uint8")
    for item in features:
        block_flood = read_remote_on_grid(item["assets"][GFM_FLOOD_ASSET]["href"], grid)
        block_exclusion = read_remote_on_grid(item["assets"][GFM_EXCLUSION_ASSET]["href"], grid)
        fill = (flood == GFM_NODATA) & (block_flood != GFM_NODATA)
        flood[fill], exclusion[fill] = block_flood[fill], block_exclusion[fill]
    items = [{"id": item["id"], "datetime": item["properties"].get("datetime"), "equi7_tile": item["properties"].get("Equi7Tile"),
              "platform": item["properties"].get("platform")} for item in features]
    return {"flood": flood, "exclusion": exclusion, "items": items}


def gfm_reference(found: Mapping[str, Any], frame_land: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(water, compared, code)`` of a GFM read: compared where GFM holds data outside its exclusion mask on frame land."""

    flood, exclusion = np.asarray(found["flood"]), np.asarray(found["exclusion"])
    holds = (flood != GFM_NODATA) & (exclusion == 0)
    code = np.where(holds, np.where(flood == 1, m1z.FLAGGED, m1z.NOT_FLAGGED), m1z.NO_ANSWER).astype("uint8")
    return holds & (flood == 1), holds & frame_land, code


# ---------------------------------------------------------------------------
# Stage 3: test
# ---------------------------------------------------------------------------


def sealed_files(root: Path, external: Path, protocol: Mapping[str, Any]) -> dict[str, Path]:
    """The JAXA zips, after checking their SHA-256 against the protocol. A changed seal refuses the test."""

    folder = external / SEALED_DIR
    out = {}
    for name, digest in protocol["sealed_references"]["files"].items():
        path = folder / name
        if not path.is_file():
            out[name] = None
            continue
        if sha256_file(path) != digest:
            raise StageError(f"{name} is not the file the protocol sealed")
        out[name] = path
    return out


def label_points(root: Path, chip: str) -> tuple[list[dict[str, Any]], dict[str, str | None], dict[str, Any]]:
    """The labelled points of a THEOS-2 chip and the label at least two of the three labellers gave."""

    from floodguard import theos2_water_labels as wl

    folder = root / LABELS_DIR
    sample = read_json(folder / LABEL_SAMPLE)
    key_path = folder / LABEL_KEY
    if sha256_file(key_path) != sample["sample_id"]:
        raise StageError("the key of the labelled points is not the one the committed draw names")
    key = read_json(key_path)
    ids = [point["id"] for point in key["points"]]
    files = sorted(folder.glob("labels_*.json"))
    if len(files) != 3:
        raise StageError(f"three label files are expected in {LABELS_DIR}, found {len(files)}")
    given = [wl.check_labels(read_json(path), sample_id=sample["sample_id"], point_ids=ids) for path in files]
    majority = wl.majority(given)
    points = [point for point in key["points"] if point["chip"] == chip]
    return points, majority, {"key": file_record(key_path), "label_files": [file_record(path) for path in files],
                              "scoring": "the label at least two of the three gave, where it is water or not water"}


def cells_of_points(points: Sequence[Mapping[str, Any]], grid: Grid) -> list[tuple[int, int] | None]:
    out = []
    for point in points:
        row, column = int(math.floor((grid[1] - float(point["y"])) / CELL_M)), int(math.floor((float(point["x"]) - grid[0]) / CELL_M))
        out.append((row, column) if 0 <= row < grid[2] and 0 <= column < grid[3] else None)
    return out


def theos2_headers(folder: Path | None, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """The bounds of the two THEOS-2 Nan images (headers only) against the chip rectangles of the protocol."""

    import rasterio
    from rasterio.warp import transform_bounds

    out: dict[str, Any] = {}
    for chip, name in THEOS2_NAN_IMAGES.items():
        rectangle = protocol["grid"]["chips"][chip]
        path = None if folder is None else Path(folder) / name
        if path is None or not path.is_file():
            out[chip] = {"file": name, "found": False}
            continue
        with rasterio.open(path) as source:
            bounds = transform_bounds(source.crs, f"EPSG:{EPSG}", *source.bounds) if source.crs and source.crs.to_epsg() != EPSG else tuple(source.bounds)
        edges = dict(zip(("west", "south", "east", "north"), bounds))
        out[chip] = {"file": name, "found": True, "largest_edge_difference_m": round(max(abs(edges[key] - float(rectangle[key])) for key in edges), 3)}
    return out


def chip_reference(external: Path, root: Path, chip: str, grid: Grid, protocol: Mapping[str, Any]) -> tuple[np.ndarray, tuple[slice, slice], dict[str, Any]]:
    """The rule v2 water of a THEOS-2 chip on the frame cells whose centre lies inside the chip, by the 20 m half rule."""

    import rasterio

    try:
        named = read_json(root / RULE_V2_FREEZE)["frozen_rule"]["chips"][RULE_V2_CHIP[chip]]["raster_outside_git"]
    except (OSError, KeyError, TypeError) as error:
        raise StageError(f"{RULE_V2_FREEZE} names no rule v2 raster of {RULE_V2_CHIP[chip]}: {error}") from error
    path = external / RULE_V2_WORK / named["name"]
    if not path.is_file() or sha256_file(path) != named["sha256"]:
        raise StageError(f"{named['name']} is missing or is not the raster the rule v2 freeze names")
    window = m1z.centre_window(grid, protocol["grid"]["chips"][chip])
    with rasterio.open(path) as source:
        if source.crs is None or source.crs.to_epsg() != EPSG:
            raise StageError(f"{path.name} is not in EPSG:{EPSG}")
        fine, transform = source.read(1), source.transform
    rows, columns = window[0].stop - window[0].start, window[1].stop - window[1].start
    water, valid, pixels = m1z.fine_counts_on_grid(fine, fine_west=transform.c, fine_north=transform.f, fine_m=transform.a,
                                                   grid_west=grid[0] + window[1].start * CELL_M, grid_north=grid[1] - window[0].start * CELL_M,
                                                   rows=rows, columns=columns)
    code = m1z.half_rule(water, valid, pixels, basis="all")
    return code, window, {"raster": {"name": path.name, "sha256": named["sha256"]}, "fine_m": float(transform.a), "pixels_per_cell": pixels,
                          "half_rule": "water when at least half of the cell's 2 m pixels are water; not compared when fewer than half hold a value",
                          "cells": int(code.size), "compared_cells": int((code != m1z.NO_ANSWER).sum()), "water_cells": int((code == 1).sum())}


def by_built_up(code: np.ndarray, water: np.ndarray, compared: np.ndarray, cover: np.ndarray) -> dict[str, Any]:
    built = np.asarray(cover) == m1z.BUILT_UP_CLASS
    return {"built_up": m1z.evaluate(code, water, compared & built), "open_land_not_built_up": m1z.evaluate(code, water, compared & ~built)}


def pass_days(event: EventPass, reference_date: str) -> int | None:
    """Days between the pass (as a Thai calendar date) and the case reference date."""

    if event.time is None:
        return None
    local = (event.time + timedelta(hours=7)).date()
    return abs((local - datetime.fromisoformat(reference_date).date()).days)


def check_pass_set(root: Path, folder: Path, passes: Sequence[EventPass], missing_reason: str | None) -> dict[str, Any]:
    """Refuse a test that would open the sealed references with an incomplete set of Nan passes.

    Every fetched pass needs the dry-season statistics of its orbit, or the test would stop half-way, after the
    sealed files are opened. Every event pass that the radar lane's record (``RADAR_RECORD_OF_THE_FRAME``) lists
    must be fetched, because test 1 takes the pass nearest in time to JAXA's acquisition and tests 3b and 4 read
    the passes of late July; ``missing_reason`` (``--missing-passes-reason``) lets the test run without some of
    them, and the record keeps the reason. Without the radar record only the first check applies.
    """

    without_dry = []
    for item in passes:
        try:
            dry_file(folder, item.orbit)
        except StageError:
            without_dry.append(item.label)
    if without_dry:
        raise StageError(f"no dry-season statistics for the fetched pass(es) {', '.join(without_dry)}: compute them before the test")
    record: dict[str, Any] = {"passes_found": len(passes), "every_pass_has_its_dry_season_statistics": True, "radar_record": None,
                              "event_passes_not_on_disk": None, "missing_passes_reason": missing_reason}
    path = root / RADAR_RECORD_OF_THE_FRAME
    if path.is_file():
        listed = [entry for entry in (read_json(path).get("event_passes") or []) if isinstance(entry, Mapping)]
        absent = sorted(str(entry.get("key")) for entry in listed
                        if entry.get("status") != "fetched" or not (folder / f"event_{entry.get('key')}.tif").is_file())
        record.update(radar_record={"path": RADAR_RECORD_OF_THE_FRAME, "sha256": sha256_file(path)}, event_passes_listed=len(listed),
                      event_passes_not_on_disk=absent)
        if absent and not missing_reason:
            raise StageError(f"{RADAR_RECORD_OF_THE_FRAME} lists event passes that are not on disk ({', '.join(absent)}): fetch them and "
                             "the dry-season statistics of their orbits before the test, or run it without them with --missing-passes-reason")
    return record


def write_case_n2_reference(external: Path, grid: Grid, code: np.ndarray, name: str, what: str) -> dict[str, Any]:
    """Write the test 1 reference as provided on the frame grid (1 water, 0 not water, 255 not observed), for case N2.

    The file stays in the work folder outside Git; only its name and SHA-256 enter the test record.
    """

    path = external / CASE_N2_REFERENCE / f"{name}.tif"
    digest = write_map(path, grid, [("reference: 1 water, 0 not water, 255 not observed", code)])
    counts = {str(value): int((np.asarray(code) == value).sum()) for value in (1, 0, m1z.NO_ANSWER)}
    return {"name": path.name, "sha256": digest, "folder": f"<external>/{CASE_N2_REFERENCE.as_posix()}", "what": what,
            "codes": "1 water, 0 not water, 255 not observed (no answer)", "cells_by_code": counts,
            "use": "the flood input of case N2 (test 5): scripts/nan_case_chain.py nan --case N2 --flood-central <this file>",
            "rights": "a raster made from the reference for the chain; it stays outside Git and is never published"}


def stage_test(root: Path, arguments: argparse.Namespace, hooks: Mapping[str, Any]) -> dict[str, Any]:
    freeze = require_frozen(root)
    if arguments.replace and not arguments.reason:
        raise StageError("--replace needs --reason")
    if (root / TEST_RESULT).exists() and not arguments.replace:
        raise StageError(f"{TEST_RESULT} exists: the test runs once (replace only with --replace and --reason)")
    external = Path(arguments.external_root)
    log = Log(external / WORK / "test.log")
    offsets = platform_offsets(root)
    protocol, areas = read_json(root / PROTOCOL), read_json(root / AREAS)
    grid = area_grid(areas, FRAME_AREA)
    selected = m1z.M1zParameters.from_json(freeze["selected"])
    gfm_fetch = hooks.get("gfm_fetch", fetch_gfm)

    # --- preflight: every file is found and checked before any reference is opened ------------------------------
    radar = area_folder(external / RADAR_DIR, [FRAME_AREA])
    if radar is None:
        raise StageError(f"no radar folder {external / RADAR_DIR / FRAME_AREA}")
    passes = discover_passes(radar, "test")
    pass_set = check_pass_set(root, radar, passes, arguments.missing_passes_reason)
    test2_pass = nearest_pass(passes, parse_time(TEST2_PASS_UTC), within_minutes=PASS_MATCH_MINUTES)
    if test2_pass is None:
        raise StageError(f"the pass of {TEST2_PASS_UTC} is not among the fetched Nan passes")
    terrain = load_terrain(external, [FRAME_AREA], grid, "test")
    boundaries = Path(arguments.boundaries) if arguments.boundaries else external / BOUNDARIES
    units, units_record = frame_units_mask(boundaries, grid, protocol["frame"]["district_pcodes"])
    named_count = re.search(r"\((\d+) units", str(protocol["frame"].get("units", "")))
    units_record["units_the_protocol_names"] = int(named_count.group(1)) if named_count else None
    units_record["matches_the_protocol"] = None if named_count is None else units_record["units"] == int(named_count.group(1))
    frame_land = units & ~terrain["permanent_water"]
    sealed = sealed_files(root, external, protocol)
    for name in (LABEL_SAMPLE, LABEL_KEY):
        if not (root / LABELS_DIR / name).is_file():
            raise StageError(f"{LABELS_DIR}/{name} is missing")
    # Test 2's reference and labels are read here, so that nothing can fail half-way once JAXA is opened.
    town_reference, town_window, town_described = chip_reference(external, root, CHIP_TOWN, grid, protocol)
    points, majority, label_files = label_points(root, RULE_V2_CHIP[CHIP_TOWN])
    dry_window = m1z.centre_window(grid, protocol["grid"]["chips"][CHIP_DRY])
    log(f"test: preflight passed; {len(passes)} Nan passes; frame land {int(frame_land.sum())} cells")

    loaded: dict[str, dict[str, Any]] = {}
    maps_written: dict[str, Any] = {}
    freeze_sha256 = sha256_file(root / FREEZE)
    gfm_found: dict[tuple[str, str], Any] = {}

    def gfm_of(when: datetime, *, required: bool) -> dict[str, Any] | None:
        """GFM of the pass at ``when`` (items within 30 minutes), read once. Outside the fallback a failure is recorded."""

        start, end = when - timedelta(minutes=GFM_WINDOW_MINUTES), when + timedelta(minutes=GFM_WINDOW_MINUTES)
        key = (f"{start:%Y-%m-%dT%H:%M:%SZ}", f"{end:%Y-%m-%dT%H:%M:%SZ}")
        if key not in gfm_found:
            try:
                gfm_found[key] = gfm_fetch(grid, start, end)
            except Exception as error:  # noqa: BLE001 - recorded where GFM is a comparator
                if required:
                    raise
                gfm_found[key] = {"error": f"{type(error).__name__}: {error}"}
        return gfm_found[key]

    def gfm_comparator(found: Mapping[str, Any] | None, water: np.ndarray, compared: np.ndarray,
                       window: tuple[slice, slice] | None = None) -> dict[str, Any]:
        if found is None:
            return {"not_run": "GFM holds no item of this pass over the frame"}
        if "error" in found:
            return {"not_run": found["error"]}
        code = gfm_reference(found, frame_land)[2]
        return {"items": found["items"], **m1z.evaluate(code if window is None else code[window], water, compared)}

    def better_than_ours(comparators: Mapping[str, Any], ours: Mapping[str, Any]) -> dict[str, float]:
        mine = ours.get("iou_no_answer_as_not_flagged") or 0
        return {name: entry["iou_no_answer_as_not_flagged"] for name, entry in comparators.items()
                if isinstance(entry, dict) and entry.get("iou_no_answer_as_not_flagged") is not None and entry["iou_no_answer_as_not_flagged"] > mine}

    def pass_data(event: EventPass, *, with_comparators: bool = False) -> dict[str, Any]:
        """The three maps of a pass (written to maps/ once) and, when asked, its comparator maps."""

        entry = loaded.get(event.label)
        if entry is None or (with_comparators and "comparators" not in entry):
            inputs = load_pass(event, grid, "test", offsets=offsets)
            if entry is None:
                levels = m1z_levels(inputs, terrain, selected)
                entry = loaded[event.label] = {"levels": levels}
                maps_written[event.label] = write_pass_map(external, event, grid, levels, inputs, terrain, freeze_sha256, freeze["flood_levels"], units)
            if with_comparators:
                entry["comparators"] = comparator_maps(root, inputs, terrain, grid)
            del inputs
        return entry

    def score_against(event: EventPass, water: np.ndarray, compared: np.ndarray, *, with_comparators: bool = True,
                      without_offset: bool = False) -> dict[str, Any]:
        data = pass_data(event, with_comparators=with_comparators)
        code = data["levels"]["central"][0]
        applied = float(offsets.get(platform_key(event.platform), 0.0))
        figures = {
            "pass": event.as_json(),
            "central": m1z.evaluate(code, water, compared),
            "lower": m1z.evaluate(data["levels"]["lower"][0], water, compared),
            "upper": m1z.evaluate(data["levels"]["upper"][0], water, compared),
            "central_by_worldcover_group": m1z.evaluate_by_cover(code, water, compared, terrain["cover"]),
            "central_interval_95": m1z.tile_bootstrap(code, water, compared),
            "central_reasons_on_compared_cells": m1z.reason_counts(data["levels"]["central"][1], compared),
        }
        figures["platform_offset_db"] = applied
        if without_offset and applied:
            raw = load_pass(event, grid, "test")
            raw_code = m1z_levels(raw, terrain, selected)["central"][0]
            figures["central_without_platform_offset_report_only"] = m1z.evaluate(raw_code, water, compared)
            del raw, raw_code
        if with_comparators:
            figures["comparators"] = score_comparators(data["comparators"], water, compared)
        return figures

    def verdict(figures: Mapping[str, Any]) -> bool:
        central = figures["central"]
        return bool(central["iou_no_answer_as_not_flagged"] is not None and central["iou_no_answer_as_not_flagged"] >= PASS_IF_IOU
                    and central["no_answer_share"] is not None and central["no_answer_share"] <= PASS_IF_NO_ANSWER)

    def jaxa(date: str) -> dict[str, Any]:
        zips = [path for name, path in sealed.items() if date in name and path is not None]
        zips.sort(key=lambda path: (0 if "geojson" in path.name else 1, path.name))
        if not zips:
            return {"usable": False, "why": f"no sealed JAXA file of {date}"}
        found, errors = None, []
        for path in zips:
            try:
                found = inspect_jaxa(path)
                if found["flood"] is not None or found["observed"] is not None:
                    break
            except Exception as error:  # noqa: BLE001 - the next file is tried
                errors.append(f"{path.name}: {type(error).__name__}: {error}")
        if found is None:
            return {"usable": False, "why": "no JAXA file could be read", "errors": errors}
        record: dict[str, Any] = {"contents": found["record"], "errors": errors}
        observed = rasterize_polygons(found["observed"], grid)
        share = float((observed & frame_land).sum()) / float(frame_land.sum()) if frame_land.any() else 0.0
        record["observation_area_geometry_found"] = found["observed"] is not None
        record["scene_footprints_route"] = ("scene identifiers are listed, but the code knows no login-free source of ALOS-2 scene footprints; this route is not used"
                                            if found["record"]["scene_identifiers"] else "no scene identifier is listed")
        record["share_of_frame_land_inside_the_observation_area"] = round(share, 6)
        record["usable"] = bool(found["observed"] is not None and share >= JAXA_MIN_COVER_SHARE)
        record["why"] = ("an observation-area geometry covers at least half of the frame's land outside permanent water" if record["usable"]
                         else "no observation-area geometry in the files" if found["observed"] is None
                         else f"the observation area covers {share:.3f} of the frame's land, less than half")
        record["_water"] = rasterize_polygons(found["flood"], grid)
        record["_observed"] = observed
        record["_compared"] = frame_land & observed
        record["_times"] = found["times"]
        return record

    # --- test 1 ------------------------------------------------------------------------------------------------
    test1: dict[str, Any] = {"reference": None}
    jaxa_main = jaxa("20250728")
    case_reference_date = "2025-07-28"
    flood_input: EventPass | None = None
    reference_n2: dict[str, Any] | None = None
    if jaxa_main.get("usable"):
        times = jaxa_main["_times"]
        if times:
            middle = times[len(times) // 2]
            event = nearest_pass(passes, middle)
            choice = f"the pass nearest to JAXA's acquisition time {middle:%Y-%m-%dT%H:%M:%SZ} (median of the zoned times in the files)"
        else:
            event = nearest_pass(passes, parse_time(TEST1_FALLBACK_PASS_UTC), within_minutes=PASS_MATCH_MINUTES)
            choice = f"JAXA's time cannot be read: the Sentinel-1C pass of {TEST1_FALLBACK_PASS_UTC}"
            if event is None:
                event = nearest_pass(passes, parse_time(TEST1_FALLBACK_PASS_UTC))
                choice += " was not fetched; the nearest fetched pass is used (a deviation, recorded)"
        figures = score_against(event, jaxa_main["_water"], jaxa_main["_compared"], without_offset=True)
        found_gfm = gfm_of(event.time, required=False) if event.time else None
        figures["external_comparator_gfm_same_pass"] = gfm_comparator(found_gfm, jaxa_main["_water"], jaxa_main["_compared"])
        test1 = {"reference": "JAXA ALOS-2 Flood Proxy Map of 2025-07-28", "label": "Agreement with JAXA's ALOS-2 map (another sensor), not accuracy.",
                 "pass_choice": choice, **figures}
        flood_input = event
        observed = jaxa_main["_observed"]
        reference_n2 = write_case_n2_reference(
            external, grid, np.where(observed, np.where(jaxa_main["_water"], m1z.FLAGGED, m1z.NOT_FLAGGED), m1z.NO_ANSWER).astype("uint8"),
            "reference_test_1_jaxa_20250728",
            "JAXA's flood polygons of 2025-07-28 as provided, by cell centre, inside its observation area; 255 outside it")
    else:
        found_gfm = gfm_of(parse_time(TEST2_PASS_UTC), required=True)
        case_reference_date = "2025-07-31"
        if found_gfm is None:
            test1 = {"reference": None, "not_run": "JAXA's map is not usable and GFM holds no item of the 2025-07-31 pass over the frame"}
        else:
            water, compared, gfm_code = gfm_reference(found_gfm, frame_land)
            figures = score_against(test2_pass, water, compared, without_offset=True)
            test1 = {"reference": "GFM ensemble flood extent of the Sentinel-1A pass of 2025-07-31 (fallback)",
                     "label": "Agreement with a same-pass CEMS map, not independent and not accuracy.",
                     "gfm_items": found_gfm["items"], **figures}
            flood_input = test2_pass
            reference_n2 = write_case_n2_reference(
                external, grid, gfm_code, "reference_test_1_gfm_20250731T2308",
                "GFM's ensemble flood extent of the pass of 2025-07-31 23:08 UTC as provided, where GFM holds data outside its exclusion mask; 255 elsewhere")
    jaxa_record = {key: value for key, value in jaxa_main.items() if not key.startswith("_")}
    test1["jaxa_usability"] = jaxa_record
    if test1.get("central"):
        test1["pass_if"] = f"IoU (no answer counted as not flagged) >= {PASS_IF_IOU} and no-answer share <= {PASS_IF_NO_ANSWER}"
        test1["passes"] = verdict(test1)
        test1["comparators_better_by_iou"] = better_than_ours({**test1.get("comparators", {}),
                                                               "gfm": test1.get("external_comparator_gfm_same_pass", {})}, test1["central"])
    else:
        test1["passes"] = False
    log(f"test 1: reference {test1.get('reference')}; passes {test1.get('passes')}")

    # --- test 1b: the JAXA map of 2025-07-19, report only ----------------------------------------------------------
    jaxa_second = jaxa("20250719")
    test1b: dict[str, Any] = {"report_only": True, "jaxa_usability": {key: value for key, value in jaxa_second.items() if not key.startswith("_")}}
    if jaxa_second.get("usable"):
        times = jaxa_second["_times"]
        target = times[len(times) // 2] if times else datetime(2025, 7, 19, 5, 0, tzinfo=timezone.utc)
        event = nearest_pass(passes, target)
        test1b.update(pass_choice=("the pass nearest to JAXA's acquisition time" if times else
                                   "JAXA's time cannot be read: the pass nearest to 2025-07-19 12:00 Thai time"),
                      **score_against(event, jaxa_second["_water"], jaxa_second["_compared"], with_comparators=False))
        test1b["label"] = "Agreement with JAXA's ALOS-2 map of 2025-07-19, not accuracy; report only."

    # --- test 2 and the dry control ----------------------------------------------------------------------------------
    data = pass_data(test2_pass, with_comparators=True)
    window, described = town_window, town_described
    water, compared = m1z.reference_cells(town_reference, exclude=terrain["permanent_water"][window])
    code = data["levels"]["central"][0]
    cells = cells_of_points(points, grid)
    labels = [majority.get(point["id"]) for point in points]
    point_figures = {"central": m1z.point_agreement([code[cell] if cell else m1z.NO_ANSWER for cell in cells], labels)}
    for name, value in data["comparators"].items():
        if not isinstance(value, dict):
            point_figures[name] = m1z.point_agreement([value[cell] if cell else m1z.NO_ANSWER for cell in cells], labels)
    test2 = {
        "status": "seen image, new method: the chip was the held-out test of R37 and was labelled in R47; reported, not binding",
        "label": "Agreement with water read from THEOS-2 by the frozen rule v2, and with the labels of three team members; not accuracy.",
        "pass": test2_pass.as_json(), "hours_after_theos2": round((test2_pass.time - parse_time(THEOS2_NAN_UTC)).total_seconds() / 3600, 2),
        "reference": described,
        "central": m1z.evaluate(code[window], water, compared),
        "lower": m1z.evaluate(data["levels"]["lower"][0][window], water, compared),
        "upper": m1z.evaluate(data["levels"]["upper"][0][window], water, compared),
        "central_by_built_up_and_open_land": by_built_up(code[window], water, compared, terrain["cover"][window]),
        "central_by_worldcover_group": m1z.evaluate_by_cover(code[window], water, compared, terrain["cover"][window]),
        "comparators": score_comparators(data["comparators"], water, compared, window),
        "external_comparator_gfm_same_pass": gfm_comparator(gfm_of(test2_pass.time, required=False), water, compared, window),
        "labelled_points": {**label_files, "points": len(points), "points_outside_the_grid": sum(1 for cell in cells if cell is None),
                            "agreement": point_figures},
    }
    test2["comparators_better_by_iou"] = better_than_ours({**test2["comparators"], "gfm": test2["external_comparator_gfm_same_pass"]}, test2["central"])

    def dry_share(map_code: np.ndarray) -> dict[str, Any]:
        part = map_code[dry_window]
        answered = np.isin(part, (m1z.FLAGGED, m1z.NOT_FLAGGED)) & ~terrain["permanent_water"][dry_window]
        flagged = answered & (part == m1z.FLAGGED)
        return {"cells": int(part.size), "answered_cells": int(answered.sum()), "flagged_cells": int(flagged.sum()),
                "flagged_share_of_answered": round(float(flagged.sum()) / float(answered.sum()), 6) if answered.any() else None}

    dry_control = {"rule": f"our map flags at most {DRY_CONTROL_MAX_SHARE} of the chip's answered cells (permanent water left out)",
                   "pass": test2_pass.as_json(), "central": dry_share(code)}
    dry_control["passes"] = bool(dry_control["central"]["flagged_share_of_answered"] is not None
                                 and dry_control["central"]["flagged_share_of_answered"] <= DRY_CONTROL_MAX_SHARE)
    dry_control["lower"], dry_control["upper"] = dry_share(data["levels"]["lower"][0]), dry_share(data["levels"]["upper"][0])
    dry_control["comparators"] = {name: (value if isinstance(value, dict) else dry_share(value)) for name, value in data["comparators"].items()}
    if flood_input is not None and flood_input.label != test2_pass.label:
        dry_control["report_only_on_the_test_1_pass"] = {"pass": flood_input.as_json(), "central": dry_share(pass_data(flood_input)["levels"]["central"][0])}
    log(f"test 2: IoU {test2['central']['iou_no_answer_as_not_flagged']}; dry control passes {dry_control['passes']}")

    binding = {
        "test_1_passes": bool(test1.get("passes")),
        "dry_control_passes": dry_control["passes"],
        "case_reference_date": case_reference_date,
        "flood_input_of_case_N1": None if flood_input is None else {**flood_input.as_json(), "map": maps_written.get(flood_input.label),
                                                                     "days_from_the_case_reference_date_thai_calendar": pass_days(flood_input, case_reference_date)},
        "per_tambon_conditions": "set by the planning lane from the map of the flood input: no-answer share <= 0.20, answered land >= 0.80, pass within 3 days, C4 to C8",
        "reference_of_case_N2": reference_n2,
    }
    record = {
        "schema": "floodguard.nan_case_test_result.v1",
        **envelope(f"Nan passes {', '.join(item.as_json()['time_utc'] or item.path.name for item in passes)}; JAXA maps of 2025-07-19 and 2025-07-28; "
                   f"THEOS-2 {THEOS2_NAN_UTC}", "low", [
            *ASSUMPTIONS_METHOD,
            "The frozen method runs unchanged; the comparators run with their own frozen rules on the same passes and cells.",
            "Test 1 compares frame land (cells whose centre lies inside the 35 units) outside permanent water; JAXA polygons and the observation area are rasterised by cell centre.",
            "A JAXA time is read only where the files give it with a zone; otherwise the protocol's pass of 2025-07-28 11:21 UTC is used.",
            "Test 2 compares the frame cells whose centre lies inside the chip, outside permanent water, by the 20 m half rule on rule v2 water.",
            "The 95% intervals come from 1000 draws of 2 km tiles (100 by 100 cells from the frame's north-west corner) with the seed recorded.",
        ]),
        "confidence_basis": "One event and one frame; references are other maps and labels from images, not ground checks.",
        "what_this_is": "The one test of the frozen M1-z of the Nan case: tests 1, 1b, 2 and the dry control of the protocol.",
        "freeze_record": {"path": FREEZE, "sha256": sha256_file(root / FREEZE)},
        "protocol": {"path": PROTOCOL, "sha256": sha256_file(root / PROTOCOL)},
        "code_sha256": code_hashes(root),
        "git_commit": head_commit(root),
        "frozen_parameters": freeze["flood_levels"],
        "frame": {**units_record, "frame_land_cells": int(frame_land.sum()), "grid": dict(zip(("west", "north", "rows", "cols"), grid)),
                  "terrain_inputs": terrain["files"],
                  "cells_where_the_lane_permanent_water_differs_from_class_80": terrain["cells_where_the_lane_permanent_water_differs_from_class_80"]},
        "passes_fetched": [item.as_json() for item in passes],
        "pass_set_check": pass_set,
        "theos2_images": theos2_headers(Path(arguments.theos2_dir) if arguments.theos2_dir else None, protocol),
        "amendment_1": {"path": AMENDMENT_1, "sha256": sha256_file(root / AMENDMENT_1) if (root / AMENDMENT_1).is_file() else None,
                        "platform_offset_db_applied_to_event_passes": offsets},
        "test_1": test1,
        "test_1b_report_only": test1b,
        "test_2": test2,
        "dry_control": dry_control,
        "binding": binding,
        "comparators": {"what": COMPARATOR_NOTES, "rule": "a comparator that does better is reported, never renamed as the result"},
        "maps_written_outside_git": maps_written,
        "rights_note": "Only figures are recorded; no JAXA or GFM geometry or raster enters Git. Credit: JAXA ALOS-2 maps 'Provided by JAXA' (Sentinel Asia).",
        "limits": LIMITS,
        "supersedes": superseded(root / TEST_RESULT, arguments),
    }
    write_record(root / TEST_RESULT, record)
    log(f"test: written {TEST_RESULT}")
    return record


# ---------------------------------------------------------------------------
# Stage 4: maps
# ---------------------------------------------------------------------------


def write_pass_map(external: Path, event: EventPass, grid: Grid, levels: Mapping[str, tuple[np.ndarray, np.ndarray]], inputs: Mapping[str, Any],
                   terrain: Mapping[str, Any], freeze_sha256: str, flood_levels: Mapping[str, Any], units: np.ndarray | None) -> dict[str, Any]:
    """Write the lower, central and upper map of a pass with the central reasons, and its record, into maps/."""

    folder = external / MAPS
    name = f"m1z_{event.label}"
    digest = write_map(folder / f"{name}.tif", grid, [("code_lower", levels["lower"][0]), ("code_central", levels["central"][0]),
                                                     ("code_upper", levels["upper"][0]), ("reason_central", levels["central"][1])])
    cell_km2 = CELL_M * CELL_M / 1e6
    land = None if units is None else units & ~terrain["permanent_water"]
    summary = {}
    for level, (code, reason) in levels.items():
        entry = {"flagged_km2_grid": round(int((code == m1z.FLAGGED).sum()) * cell_km2, 4), "reasons_grid": m1z.reason_counts(reason)}
        if land is not None and land.any():
            entry.update(flagged_km2_frame_land=round(int((land & (code == m1z.FLAGGED)).sum()) * cell_km2, 4),
                         no_answer_share_frame_land=round(float((land & (code == m1z.NO_ANSWER)).sum()) / float(land.sum()), 6),
                         answered_share_frame_land=round(float((land & (code != m1z.NO_ANSWER)).sum()) / float(land.sum()), 6))
        summary[level] = entry
    record = {
        "schema": "floodguard.nan_case_m1z_map.v1",
        **envelope(event.as_json()["time_utc"] or event.path.name, "low (set per tambon by the binding rule of the protocol)", [
            *ASSUMPTIONS_METHOD, "Band 1 lower flood, band 2 central, band 3 upper (codes 1 flagged, 0 not flagged, 255 no answer); band 4 the central reason."]),
        "what_this_is": "The frozen M1-z on one Nan event pass at three flood levels. A map of radar evidence for planning, not an official warning.",
        "pass": event.as_json(), "freeze_record": {"path": FREEZE, "sha256": freeze_sha256}, "flood_levels": dict(flood_levels),
        "map": {"name": f"{name}.tif", "sha256": digest, "bands": ["code_lower", "code_central", "code_upper", "reason_central"]},
        "reason_codes": {str(code): label for code, label in m1z.REASON_LABELS.items()},
        "inputs": {**inputs["files"], **{f"terrain_{key}": value for key, value in terrain["files"].items()}},
        "summary": summary, "limits": LIMITS,
    }
    write_record(folder / f"{name}.json", record)
    return {"name": f"{name}.tif", "sha256": digest, "record": f"{name}.json"}


def stage_maps(root: Path, arguments: argparse.Namespace, hooks: Mapping[str, Any]) -> dict[str, Any]:
    if not (root / TEST_RESULT).is_file():
        raise StageError("the maps of every pass are made only after the test result exists")
    freeze = require_frozen(root)
    freeze_sha256 = sha256_file(root / FREEZE)
    external = Path(arguments.external_root)
    log = Log(external / WORK / "maps.log")
    offsets = platform_offsets(root)
    protocol, areas = read_json(root / PROTOCOL), read_json(root / AREAS)
    grid = area_grid(areas, FRAME_AREA)
    selected = m1z.M1zParameters.from_json(freeze["selected"])
    radar = area_folder(external / RADAR_DIR, [FRAME_AREA])
    if radar is None:
        raise StageError(f"no radar folder {external / RADAR_DIR / FRAME_AREA}")
    passes = discover_passes(radar, "maps")
    terrain = load_terrain(external, [FRAME_AREA], grid, "maps")
    boundaries = Path(arguments.boundaries) if arguments.boundaries else external / BOUNDARIES
    units, _record = frame_units_mask(boundaries, grid, protocol["frame"]["district_pcodes"])
    written = {}
    for event in passes:
        started = time.time()
        inputs = load_pass(event, grid, "maps", offsets=offsets)
        written[event.label] = write_pass_map(external, event, grid, m1z_levels(inputs, terrain, selected), inputs, terrain, freeze_sha256,
                                              freeze["flood_levels"], units)
        del inputs
        log(f"maps: {event.label} in {time.time() - started:.0f} s")
    index = {
        "schema": "floodguard.nan_case_m1z_maps_index.v1",
        **envelope("; ".join(item.as_json()["time_utc"] or item.path.name for item in passes), "low (set per tambon by the binding rule of the protocol)",
                   ASSUMPTIONS_METHOD),
        "freeze_record": {"path": FREEZE, "sha256": freeze_sha256}, "test_result": {"path": TEST_RESULT, "sha256": sha256_file(root / TEST_RESULT)},
        "maps": written, "limits": LIMITS,
    }
    write_record(external / MAPS / "maps_index_v1.json", index)
    return index


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

STAGES: dict[str, Callable[[Path, argparse.Namespace, Mapping[str, Any]], dict[str, Any]]] = {
    "tune": stage_tune, "freeze": stage_freeze, "test": stage_test, "maps": stage_maps,
}


def parser() -> argparse.ArgumentParser:
    commands = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    stages = commands.add_subparsers(dest="stage", required=True)
    for name in STAGES:
        stage = stages.add_parser(name)
        if name != "freeze":
            stage.add_argument("--external-root", required=True, help="the external data root (outside Git)")
        if name == "test":
            stage.add_argument("--theos2-dir", required=True, help="the folder that holds the THEOS-2 images (headers are checked)")
            stage.add_argument("--missing-passes-reason", help="run although the radar record lists Nan event passes not on disk; "
                                                               "the reason is recorded")
        if name in ("test", "maps"):
            stage.add_argument("--boundaries", help="the COD-AB file; default <external root>/open_context/hdx_cod_ab/tha_admin_boundaries.gdb.zip")
        if name != "maps":
            stage.add_argument("--replace", action="store_true", help="replace an existing record (needs --reason)")
            stage.add_argument("--reason", help="why the record is replaced")
    return commands


def run(argv: Sequence[str] | None = None, *, root: Path | None = None, hooks: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Run one stage; raises :class:`StageError` when it refuses."""

    arguments = parser().parse_args(argv)
    for name in ("replace", "reason", "boundaries", "theos2_dir", "missing_passes_reason"):
        if not hasattr(arguments, name):
            setattr(arguments, name, None if name != "replace" else False)
    return STAGES[arguments.stage](Path(root or ROOT), arguments, hooks or {})


def main(argv: Sequence[str] | None = None) -> int:
    try:
        run(argv)
    except StageError as error:
        print(f"refused: {error}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
