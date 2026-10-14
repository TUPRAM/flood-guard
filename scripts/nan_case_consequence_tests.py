"""The Nan case, tests 3a, 3b and 4: roads and the provincial hospital set beside the frozen maps of the Nan passes.

The rules are those of ``docs/proposal_execution/nan_case_protocol_v1.json`` (decision log R51) as amendment 1
(``docs/proposal_execution/nan_case_protocol_v1_amendment_1.json``, R52) changes them.

Test 3a, the pass of 2025-07-31 23:08 UTC
    Inside the ``nan_chip_003`` rectangle of the protocol: the vehicle edges that closure rule v1 closes at the central
    level on our map; the share of them seen under THEOS-2 rule v2 water (20 m of centreline on water or more, the
    rule of R26 at Sukhothai, ``docs/theos2_radar_cross_check.md``); and the share of the edges seen under water that
    our map closes. The same with the case N2 reference raster as the extent, report only, when it is given.
Test 3b, the five listed points of amendment 1
    A point is found when at least one vehicle edge within 300 m of it is closed at the central level on at least one
    pass that starts between 2025-07-20 00:00 and 2025-07-31 23:59 Thai time. For every pass the record says which
    edges it closes near the point, or that its footprint does not cover the point, or that it has no map. Nan 021 has
    no position and counts as not found. Measure: the share of the five found, with the number placed beside it.
Test 4, Nan Hospital (OSM way 315323384)
    On the passes that start on 22 July and on 26 July 2025 (Thai time): the flagged and the no-answer cells whose
    centre lies inside the site polygon or within 200 m of it, and the closed edges within 200 m, set beside the news
    records of ``outputs/nan_case/news_records_v1.json`` by their record ids. A check only, with no pass mark.

Closure rule v1 at the central level is applied as the score chain applies it (``scripts/nan_case_chain.py``): the
flagged cells of the central band (a no-answer cell counts as not flagged), ``floodguard.nan_case_chain.closure_extent``
(polygons under 5 cells dropped, 8-connected, for the project's own map), clipped to the routing geometry of the frame,
projected to longitude and latitude, ``floodguard.closure_rules.edge_intersections`` and
``floodguard.access_diff.flooded_edges`` with ``access_diff.closure_arguments`` of protocol v1b, all unchanged.

The stage runs after the test of the case (``outputs/nan_case/test_result_v1.json`` must exist) and after the maps
stage of ``scripts/nan_case_method.py``; it runs once (a second run needs ``--replace`` and ``--reason``). It writes
``outputs/nan_case/consequence_tests_v1.json``: figures, edge identifiers and OpenStreetMap positions (ODbL), no
raster. It never opens the sealed JAXA folder, the THEOS-2 images of 31 July 2025, anything of chip_001 or the
labels; the rule v2 water of chip_003 and the case N2 reference are opened only once the test result exists.

Example (from the repository root)::

    python scripts/nan_case_consequence_tests.py --external-root <external data root>

Every figure is agreement with a reference layer or a dated record. Planning guidance only; not real-time and not an
official warning.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import shapely  # noqa: E402
from shapely.geometry import shape  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402

from floodguard import access_diff, closure_rules, flood_inputs, m1z  # noqa: E402
from floodguard import nan_case_chain as nan  # noqa: E402
from floodguard import theos2_cross_check as cc  # noqa: E402
from floodguard.confidence import OWN_CANDIDATE_TIER  # noqa: E402
from floodguard.grade_join import JOIN_EDGE_KIND  # noqa: E402

PROTOCOL = "docs/proposal_execution/nan_case_protocol_v1.json"
AMENDMENT_1 = "docs/proposal_execution/nan_case_protocol_v1_amendment_1.json"
PROTOCOL_V1B = "docs/proposal_execution/planning_protocol_v1b.json"
CONSEQUENCE_POINTS = "outputs/nan_case/consequence_points_v1.json"
NEWS_RECORDS = "outputs/nan_case/news_records_v1.json"
RADAR_RECORD = "outputs/nan_case/radar_passes_nan_frame_v1.json"
FRAME_RECORD = "outputs/nan_case/frame_v1.json"
FREEZE = "outputs/nan_case/freeze_v1.json"
TEST_RESULT = "outputs/nan_case/test_result_v1.json"
RULE_V2_FREEZE = "outputs/theos2_water_rule_v2/freeze_v1.json"
OUTPUT = "outputs/nan_case/consequence_tests_v1.json"
SCHEMA = "floodguard.nan_case_consequence_tests.v1"

CASE = Path("proposal_execution") / "nan_case_v1"
MAPS = CASE / "method" / "maps"
MAPS_INDEX = "maps_index_v1.json"
CASE_N2_REFERENCE = CASE / "method" / "case_n2_reference"
CONTEXT = CASE / "frame" / "e4_vehicle_candidate" / "context_inputs.json"
ROUTING_GEOMETRY = CASE / "frame" / "n1_routing_geometry.geojson"
RULE_V2_WORK = Path("proposal_execution") / "theos2_water_rule_v2"
RULE_V2_CHIP = "chip_003"
CHIP_TOWN = "nan_chip_003"

THAI = timezone(timedelta(hours=7))
TEST_3A_PASS_UTC = "2025-07-31T23:08:00Z"
WINDOW_3B_THAI = ("2025-07-20T00:00:00+07:00", "2025-07-31T23:59:59+07:00")
"""Test 3b: a pass counts when its first scene starts inside this window (Thai time, both ends included)."""
TEST_4_THAI_DATES = ("2025-07-22", "2025-07-26")
"""Test 4: the passes of 22 July and of 26 July 2025, Thai calendar (the second is 2025-07-25 23:06 UTC)."""
PASS_MATCH_MINUTES = 60
BUFFER_3B_M = 300.0
HOSPITAL_DISTANCE_M = 200.0
COMPARED_OBSERVABLE_SHARE_MIN = 0.9
"""R26: an edge is compared when at least 90% of its centreline lies on observable THEOS-2 pixels."""
CENTRAL = "central"
CASE_N2_TIER = "T3"
"""The tier of case N2 in the score chain (``scripts/nan_case_chain.py`` CASE_TIERS): no polygon is dropped."""
HOSPITAL_ID = "nan_hospital"

POINTS_3B: tuple[dict[str, str | None], ...] = (
    {"id": "cut_1243_km59_100", "section": "reported_cuts", "position": "km_59_100_from_southern_end", "words": "highway 1243"},
    {"id": "cut_nan4020_km31_690", "section": "reported_cuts", "position": "placed", "words": "Nan 4020 km 31+690"},
    {"id": "cut_nan4020_km10_500", "section": "reported_cuts", "position": "placed", "words": "Nan 4020 km 10+500"},
    {"id": "cut_nan021_km0_000", "section": "reported_cuts", "position": None, "words": "Nan 021"},
    {"id": "cut_nan3019_km7_000", "section": "supplementary_cuts", "position": "placed", "words": "Nan 3019"},
)
"""The five points of amendment 1 (changes.test_3b_points.points, in its order) and where the consequence record
holds each position: highway 1243 at 59.1 km from the southern end of its merged route line (the record's
check_chainage_from_either_end); the others as placed; Nan 021 without a position (counted as not found)."""

RADAR_AFTER_REASONS: frozenset[int] = frozenset({
    m1z.REASON_FLAGGED, m1z.REASON_RADAR_DRY, m1z.REASON_SMALL_GROUP, m1z.REASON_FEW_DRY_PASSES, m1z.REASON_DRY_SPREAD,
    m1z.REASON_BUILT_UP_LOW, m1z.REASON_TREE_COVER_LOW, m1z.REASON_NO_TERRAIN})
"""Reasons the method gives only to a cell with radar data after (it tests 'no RTC data after' before them)."""
NO_RADAR_AFTER_REASONS: frozenset[int] = frozenset({m1z.REASON_NO_RADAR_AFTER})
TERRAIN_FIRST_REASONS: frozenset[int] = frozenset({m1z.REASON_PERMANENT_WATER, m1z.REASON_TERRAIN_SLOPE, m1z.REASON_TERRAIN_HAND})
"""Reasons given before the radar is looked at: such a cell says nothing about the footprint of the pass."""

NEVER_OPENED: tuple[str, ...] = (
    r"IMG_T2V_20250731035100", r"water_v2_chip_001", r"chip_001_2m", r"held_chip_", r"theos2_water_labels", r"eodc\.eu",
)
"""Names this stage never opens: the THEOS-2 images of 31 July 2025, anything of the dry chip, the held chips, the labels
and the GFM service. The sealed JAXA folder is refused by name of folder."""
AFTER_THE_TEST_ONLY: tuple[str, ...] = (r"water_v2_chip_003", r"chip_003_2m", r"case_n2_reference")
"""Names this stage opens only once the test result exists: the rule v2 water of chip_003 and the case N2 reference."""

ASSUMPTIONS = [
    "Closure rule v1 at the central level is applied as the score chain applies it: the flagged cells of the central "
    "band (a no-answer cell counts as not flagged), polygons under 5 cells (8-connected) dropped for the project's own "
    "map (tier T2), the extent clipped to the routing geometry of the frame, and the straight node-to-node segment of "
    "each vehicle edge measured against it (floodguard.closure_rules and floodguard.access_diff.flooded_edges, "
    "unchanged). A closure is a modelled assumption, not an observed closure.",
    "Only the vehicle edges the tests read are measured: those within 300 m of a placed test 3b point, within 200 m of "
    "the hospital site, or crossing the chip_003 rectangle. The rule measures each edge on its own, so each gets the "
    "state the score chain gives it. The zero-length grade-join connectors are left out; they cannot close.",
    "Test 3a follows R26 (docs/theos2_radar_cross_check.md, floodguard.theos2_cross_check, unchanged): an edge is "
    "compared when at least 90% of its centreline lies on observable rule v2 pixels inside the chip_003 rectangle "
    "(a pixel whose centre lies outside the rectangle counts as unobservable), and is seen under water at 20 m of "
    "centreline on water or more, or, for an edge shorter than 40 m, at half its length or more.",
    "Rule v2 water is read as the test stage reads it: 1 water, 255 no value, any other value not water.",
    "Test 3b: an edge is within reach of a point when its straight segment lies within 300 m of the point's placed "
    "geometry (a point for highway 1243, a line for the other placed points).",
    "The footprint of a pass at a point is read from the reason band of its central map over the cells whose centre "
    "lies within the buffer: 'no RTC data after' marks a cell outside the footprint, a reason the radar gives marks "
    "a cell inside it, and a cell answered first by terrain or permanent water says nothing.",
    "Thai time is UTC+7. A pass belongs to the window of test 3b, or to a Thai date of test 4, by the start of its "
    "first scene (start_utc of the radar record).",
    "Test 4: a cell counts when its centre lies inside the site polygon of OSM way 315323384 or within 200 m of it; an "
    "edge counts when its segment lies within 200 m of the polygon.",
    "Road and hospital positions are OpenStreetMap data of the extract retrieved on 2026-07-10, a year after the event.",
]
LIMITS = [
    "C-band radar does not see water under trees or between buildings, nor water that drained before the pass; a road "
    "can also be cut by a landslide or a washed-out bridge with no water standing at the pass.",
    "The Ministry list is a month's summary with no start or end of any cut, so only the share of the listed points "
    "found is given, never a share of our closures that are reported cuts.",
    "THEOS-2 rule v2 water is a rule on an optical image, not a ground survey, and the radar pass came 19 hours later.",
    "The news records are paraphrased press reports, not surveys; they are set beside the maps, not scored.",
    "Every figure is agreement with a reference layer or a dated record. Planning guidance only; not an official warning.",
]


class StageError(RuntimeError):
    """The stage refuses to run: the order of the protocol is broken or an input does not fit."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def now_utc() -> str:
    """The time now, UTC, to the second."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path | str) -> str:
    """SHA-256 of a file's bytes."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def code_sha256(path: Path) -> str:
    """SHA-256 of a code file as Git holds it: a checkout's CRLF line ends are read as LF."""

    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_json(path: Path | str) -> Any:
    """Read a UTF-8 JSON file."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def dumps_record(record: Mapping[str, Any]) -> str:
    """JSON text with indent 1 and a final newline."""

    return json.dumps(record, indent=1, ensure_ascii=False, allow_nan=False) + "\n"


def write_record(path: Path, record: Mapping[str, Any]) -> None:
    """Write a record as UTF-8 with LF line ends, so its SHA-256 is that of the bytes Git holds."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(dumps_record(record))


def parse_utc(text: Any) -> datetime | None:
    """A UTC time from an ISO text; a time without a zone is read as UTC."""

    if not isinstance(text, str) or not text.strip():
        return None
    try:
        parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def as_utc_text(when: datetime) -> str:
    """A time as ``YYYY-MM-DDTHH:MM:SSZ``."""

    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def as_thai_text(when: datetime) -> str:
    """A time in Thai time (UTC+7), ISO with its offset."""

    return when.astimezone(THAI).isoformat(timespec="seconds")


def rounded(value: float | None, digits: int = 3) -> float | None:
    """A float rounded for the record; ``None`` stays ``None``."""

    return None if value is None else round(float(value), digits)


def platform_key(platform: str | None) -> str:
    """``Sentinel-1C``, ``S1C`` or ``sentinel-1c`` read as ``sentinel-1c``."""

    text = str(platform or "").strip().lower().replace(" ", "")
    match = re.search(r"(?:sentinel-?|s)1([a-d])", text)
    return f"sentinel-1{match.group(1)}" if match else text


def git_head(root: Path) -> str | None:
    """The commit of HEAD in ``root`` (read only), or ``None`` outside a repository."""

    found = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, check=False)
    return found.stdout.decode().strip() if found.returncode == 0 else None


def same_as_head(root: Path, path: str) -> bool | None:
    """Whether ``path`` is in HEAD with the bytes on disk (read only); ``None`` when Git cannot say."""

    found = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=root, capture_output=True, check=False)
    if found.returncode != 0:
        return None if git_head(root) is None else False
    return (root / path).read_bytes() == found.stdout


def firewall(path: Path | str, root: Path) -> None:
    """Refuse a path this stage may not open (the firewall of the Nan case).

    Raises:
        StageError: for the sealed JAXA folder, a THEOS-2 image of 31 July 2025, anything of chip_001, the held chips,
            the labels or the GFM service, and, before the test result exists, the rule v2 water of chip_003 and the
            case N2 reference.
    """

    text = Path(path).as_posix()
    if "jaxa_sealed" in [part.lower() for part in Path(path).parts]:
        raise StageError(f"{text} lies in the sealed folder of the JAXA files; this stage never opens it")
    for pattern in NEVER_OPENED:
        if re.search(pattern, text, flags=re.IGNORECASE):
            raise StageError(f"{text} lies behind the firewall of the Nan case; this stage never opens it")
    if not (root / TEST_RESULT).is_file():
        for pattern in AFTER_THE_TEST_ONLY:
            if re.search(pattern, text, flags=re.IGNORECASE):
                raise StageError(f"{text} may be opened only after the test of the case: {TEST_RESULT} does not exist")


# ---------------------------------------------------------------------------
# Passes and maps
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pass:
    """One event pass of the frame, as the radar record lists it."""

    key: str
    platform: str | None
    orbit: int | None
    start: datetime
    status: str | None
    footprint_share_of_grid: float | None

    def as_json(self) -> dict[str, Any]:
        """The pass as plain JSON values."""

        return {"key": self.key, "platform": self.platform, "relative_orbit": self.orbit, "start_utc": as_utc_text(self.start),
                "start_thai": as_thai_text(self.start), "radar_record_status": self.status,
                "footprint_share_of_grid_in_the_catalogue": self.footprint_share_of_grid}


def passes_of_record(record: Mapping[str, Any]) -> list[Pass]:
    """The event passes of the radar record of the frame, oldest first.

    Raises:
        StageError: for a pass without a readable start time.
    """

    found = []
    for entry in record.get("event_passes") or []:
        start = parse_utc(entry.get("start_utc"))
        if start is None:
            raise StageError(f"{RADAR_RECORD}: pass {entry.get('key')} has no readable start_utc")
        orbit = entry.get("relative_orbit")
        share = entry.get("footprint_share_of_grid")
        found.append(Pass(str(entry.get("key")), entry.get("platform"), None if orbit is None else int(orbit), start,
                          entry.get("status"), None if share is None else float(share)))
    return sorted(found, key=lambda item: (item.start, item.key))


def in_window_3b(when: datetime) -> bool:
    """Whether a pass start lies inside the window of test 3b (Thai time, both ends included)."""

    first, last = (datetime.fromisoformat(text) for text in WINDOW_3B_THAI)
    return first <= when <= last


def thai_date(when: datetime) -> str:
    """The Thai calendar date of a time."""

    return when.astimezone(THAI).date().isoformat()


def nearest_pass(passes: Sequence[Pass], when: datetime, *, within_minutes: float = PASS_MATCH_MINUTES) -> Pass | None:
    """The pass that starts nearest to ``when``, if it starts within ``within_minutes`` of it."""

    if not passes:
        return None
    best = min(passes, key=lambda item: abs((item.start - when).total_seconds()))
    return best if abs((best.start - when).total_seconds()) <= within_minutes * 60 else None


@dataclass(frozen=True)
class PassMap:
    """One map of the method lane (``m1z_<label>.tif``) and the record beside it."""

    label: str
    path: Path
    time: datetime | None
    orbit: int | None
    platform: str | None
    record: Mapping[str, Any] | None

    def as_json(self, sha256: str | None = None) -> dict[str, Any]:
        """The map as plain JSON values."""

        return {"name": self.path.name, "label": self.label, "sha256": sha256,
                "time_utc": None if self.time is None else as_utc_text(self.time), "relative_orbit": self.orbit,
                "platform": self.platform}


MAP_LABEL = re.compile(r"^m1z_(?P<time>\d{8}T\d{4})(?:_o(?P<orbit>\d{1,3}))?(?:_(?P<platform>S1[A-D]))?$", re.IGNORECASE)


def discover_maps(folder: Path) -> list[PassMap]:
    """Every ``m1z_*.tif`` of the maps folder with the pass its record (or its name) gives."""

    found = []
    for path in sorted(Path(folder).glob("m1z_*.tif")):
        record_path = path.with_suffix(".json")
        record = read_json(record_path) if record_path.is_file() else None
        about = (record or {}).get("pass") or {}
        named = MAP_LABEL.match(path.stem)
        when = parse_utc(about.get("time_utc"))
        if when is None and named:
            when = datetime.strptime(named.group("time"), "%Y%m%dT%H%M").replace(tzinfo=timezone.utc)
        orbit = about.get("relative_orbit")
        if orbit is None and named and named.group("orbit"):
            orbit = int(named.group("orbit"))
        platform = about.get("platform") or (named.group("platform") if named and named.group("platform") else None)
        found.append(PassMap(str(about.get("label") or path.stem[len("m1z_"):]), path, when, None if orbit is None else int(orbit),
                             platform, record))
    return found


def match_map(item: Pass, maps: Sequence[PassMap]) -> PassMap | None:
    """The map of a pass: the same orbit and platform where both are known, and a time within 60 minutes."""

    candidates = [
        found for found in maps if found.time is not None
        and abs((found.time - item.start).total_seconds()) <= PASS_MATCH_MINUTES * 60
        and (found.orbit is None or item.orbit is None or found.orbit == item.orbit)
        and (not found.platform or not item.platform or platform_key(found.platform) == platform_key(item.platform))
    ]
    return min(candidates, key=lambda found: abs((found.time - item.start).total_seconds())) if candidates else None


def check_map(found: PassMap, index: Mapping[str, Any], freeze_sha256: str) -> str:
    """Check that a map is a frozen map of the maps stage; return its SHA-256.

    Raises:
        StageError: when the map has no record, its record names another freeze record or other bytes, or the maps
            index does not list it with the same bytes.
    """

    if found.record is None:
        raise StageError(f"{found.path.name} has no record beside it: it is not a map of the maps stage")
    digest = sha256_file(found.path)
    if (found.record.get("freeze_record") or {}).get("sha256") != freeze_sha256:
        raise StageError(f"{found.path.name} was not made under the freeze record in force ({FREEZE})")
    if (found.record.get("map") or {}).get("sha256") != digest:
        raise StageError(f"{found.path.name} does not hold the bytes its record names")
    listed = (index.get("maps") or {}).get(found.label)
    if not isinstance(listed, Mapping) or listed.get("sha256") != digest:
        raise StageError(f"{found.path.name} is not in the maps index with these bytes: run the maps stage of scripts/nan_case_method.py")
    return digest


def read_code_raster(path: Path, grid: nan.RasterGrid, bands: Sequence[str]) -> dict[str, np.ndarray]:
    """Read named bands of a raster on the frame's grid (EPSG:32647, 20 m, same corner and size).

    A raster of one band gives that band for the first name. Every band named ``code_*``, and a one-band raster, must
    hold the three codes of the case.

    Raises:
        StageError: for another coordinate system or grid, a missing band, or another code.
    """

    import rasterio

    with rasterio.open(path) as source:
        if source.crs is None or source.crs.to_epsg() != grid.epsg:
            raise StageError(f"{path.name}: a raster of the case is in EPSG:{grid.epsg}")
        if (source.width, source.height) != (grid.cols, grid.rows) or any(
                abs(a - b) > 1e-6 for a, b in zip(tuple(source.transform)[:6], tuple(grid.transform)[:6])):
            raise StageError(f"{path.name}: the raster is not on the frame's grid {grid.as_record()}")
        names = list(source.descriptions)
        single = source.count == 1
        out: dict[str, np.ndarray] = {}
        for position, name in enumerate(bands):
            if single and position == 0:
                index = 1
            elif name in names:
                index = names.index(name) + 1
            else:
                raise StageError(f"{path.name}: no band named {name}; it holds {names}")
            out[name] = source.read(index)
    for name, values in out.items():
        if name.startswith("code_") or single:
            try:
                nan.check_flood_values(values, grid)
            except nan.NanChainError as error:
                raise StageError(f"{path.name}: {error}") from error
    return out


# ---------------------------------------------------------------------------
# Roads and closure rule v1 at the central level
# ---------------------------------------------------------------------------


@dataclass
class Roads:
    """The vehicle edges the tests read, and what closure rule v1 needs to judge them as the score chain does."""

    edges: list[dict[str, Any]]
    node_coordinates: Mapping[str, Sequence[float]]
    lines: dict[str, Any]
    """edge_id -> the straight node-to-node segment in EPSG:32647 (the segment closure rule v1 measures)."""
    routing: flood_inputs.Frame
    arguments: Mapping[str, Any]
    minimum_px: int
    grid: nan.RasterGrid

    def edge(self, edge_id: str) -> Mapping[str, Any]:
        """One edge by its identifier."""

        return self._by_id[edge_id]

    def __post_init__(self) -> None:
        self._by_id = {str(edge["edge_id"]): edge for edge in self.edges}


def select_edges(edges: Sequence[Mapping[str, Any]], node_coordinates: Mapping[str, Sequence[float]],
                 reach: Sequence[tuple[BaseGeometry, float]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The road edges whose segment lies within the distance of one of the geometries (0: crosses it).

    Grade-join connectors (zero length) are left out. Returns the edges and their segments in EPSG:32647, by edge id.
    """

    road = [dict(edge) for edge in edges if edge.get("edge_kind") != JOIN_EDGE_KIND]
    identifiers, lines = nan.edge_lines_in_metres(road, node_coordinates)
    if not identifiers:
        return [], {}
    tree = shapely.STRtree(lines)
    wanted: set[int] = set()
    for geometry, distance in reach:
        if geometry is None or geometry.is_empty:
            continue
        hits = (tree.query(geometry, predicate="dwithin", distance=float(distance)) if distance > 0
                else tree.query(geometry, predicate="intersects"))
        wanted.update(int(index) for index in np.atleast_1d(hits))
    by_id = {str(edge["edge_id"]): edge for edge in road}
    chosen = sorted(wanted)
    return [by_id[identifiers[index]] for index in chosen], {identifiers[index]: lines[index] for index in chosen}


def central_closure(code: np.ndarray, roads: Roads, *, tier: str, flood_input_id: str) -> dict[str, Any]:
    """Closure rule v1 at the central level on one flood raster, as the score chain applies it.

    The steps are those of ``scripts/nan_case_chain.py`` (``nan_run``) and ``scripts/build_access_diff.py``
    (``case_runs``): the binding treatment of the raster, the closure extent of its tier, the clip to the routing
    geometry, the projection to longitude and latitude, ``closure_rules.edge_intersections`` and
    ``access_diff.flooded_edges``, all unchanged.

    Returns:
        ``closed`` and ``delayed`` (sets of edge ids), ``inside`` (edge id -> the intersection row), the closure basis,
        the rule version and the counts of the closure extent.

    Raises:
        StageError: when the extent is not valid in longitude and latitude, or closure rule v1 refuses its inputs.
    """

    mask = nan.treatment_mask(code, nan.BINDING_TREATMENT)
    kept, counts = nan.closure_extent(mask, roads.grid.transform, tier=tier, minimum_px=roads.minimum_px)
    extent_metres = flood_inputs.clip_to_frame(kept, roads.routing)
    extent = flood_inputs.project(extent_metres, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)
    if not extent.is_valid:
        raise StageError(f"the closure extent of {flood_input_id} is not a valid geometry in longitude and latitude")
    intersections = closure_rules.edge_intersections(roads.edges, roads.node_coordinates, extent)
    try:
        _changed, result = access_diff.flooded_edges(CENTRAL, roads.edges, intersections, flood_input_id=flood_input_id,
                                                     arguments=roads.arguments)
    except access_diff.AccessDiffError as error:
        raise StageError(str(error)) from error
    return {
        "closure_rule_version": result["closure_rule_version"], "level": result["level"], "closure_basis": result["closure_basis"],
        "closed": set(result["closed_edge_ids"]), "delayed": {row["edge_id"] for row in result["delayed_edges"]},
        "inside": {row["edge_id"]: row for row in intersections},
        "extent": {**{key: value for key, value in counts.items()}, "routing_frame": flood_inputs.geometry_summary(extent_metres)},
    }


def closure_summary(closure: Mapping[str, Any]) -> dict[str, Any]:
    """The closure of one raster in plain JSON values (without the per-edge rows)."""

    return {"closure_rule_version": closure["closure_rule_version"], "level": closure["level"],
            "closure_basis": closure["closure_basis"], "closure_extent": closure["extent"],
            "edges_of_the_tests_intersected": len(closure["inside"]), "edges_of_the_tests_closed": len(closure["closed"]),
            "edges_of_the_tests_delayed": len(closure["delayed"])}


def edge_rows(closure: Mapping[str, Any], roads: Roads, geometry: BaseGeometry, distance_m: float, *,
              states: Sequence[str] = ("closed",)) -> list[dict[str, Any]]:
    """The edges in ``states`` whose segment lies within ``distance_m`` of ``geometry``, nearest first."""

    rows = []
    for edge_id, line in roads.lines.items():
        state = "closed" if edge_id in closure["closed"] else "delayed" if edge_id in closure["delayed"] else "open"
        if state not in states:
            continue
        distance = float(shapely.distance(line, geometry))
        if distance > distance_m:
            continue
        edge = roads.edge(edge_id)
        inside = closure["inside"].get(edge_id) or {}
        rows.append({"edge_id": edge_id, "state": state, "osm_way_id": edge.get("osm_way_id"), "road_class": edge.get("road_class"),
                     "bridge": edge.get("bridge"), "segment_length_m": rounded(line.length, 1),
                     "length_inside_the_closure_extent_m": rounded(inside.get("intersection_length_m", 0.0), 1),
                     "share_inside_the_closure_extent": rounded(inside.get("intersection_fraction", 0.0), 4),
                     "distance_m": rounded(distance, 1)})
    return sorted(rows, key=lambda row: (row["distance_m"], row["edge_id"]))


# ---------------------------------------------------------------------------
# Cells near a geometry, and what a pass says there
# ---------------------------------------------------------------------------


def cells_near(geometry: BaseGeometry, grid: nan.RasterGrid, distance_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Rows and columns of the cells whose centre lies within ``distance_m`` of ``geometry`` (inside a polygon is 0 m)."""

    minx, miny, maxx, maxy = geometry.bounds
    first_col = max(0, int(math.floor((minx - distance_m - grid.west) / grid.cell_m)))
    last_col = min(grid.cols - 1, int(math.floor((maxx + distance_m - grid.west) / grid.cell_m)))
    first_row = max(0, int(math.floor((grid.north - maxy - distance_m) / grid.cell_m)))
    last_row = min(grid.rows - 1, int(math.floor((grid.north - miny + distance_m) / grid.cell_m)))
    if last_col < first_col or last_row < first_row:
        return np.array([], dtype="int64"), np.array([], dtype="int64")
    rows, cols = np.mgrid[first_row:last_row + 1, first_col:last_col + 1]
    rows, cols = rows.ravel(), cols.ravel()
    centres = shapely.points(grid.west + (cols + 0.5) * grid.cell_m, grid.north - (rows + 0.5) * grid.cell_m)
    keep = shapely.distance(centres, geometry) <= distance_m
    return rows[keep], cols[keep]


def code_counts(values: np.ndarray) -> dict[str, int]:
    """Cells by map code: flagged (1), not flagged (0) and no answer (255)."""

    array = np.asarray(values)
    return {"cells": int(array.size), "flagged": int((array == nan.FLAGGED).sum()),
            "not_flagged": int((array == nan.NOT_FLAGGED).sum()), "no_answer": int((array == nan.NO_ANSWER).sum())}


def footprint_cover(reasons: np.ndarray) -> dict[str, Any]:
    """Whether a pass's footprint covers a set of cells, read from the reason band of its central map.

    ``covered``: every cell that terrain does not answer first has radar data after; ``not_covered``: none has;
    ``partly_covered``: some have; ``not_known_from_the_map``: there is no cell, or terrain or permanent water answers
    every cell first.
    """

    values = np.asarray(reasons).astype("int64")
    with_radar = int(np.isin(values, sorted(RADAR_AFTER_REASONS)).sum())
    without = int(np.isin(values, sorted(NO_RADAR_AFTER_REASONS)).sum())
    terrain = int(np.isin(values, sorted(TERRAIN_FIRST_REASONS)).sum())
    if with_radar and not without:
        status, words = "covered", "the pass's footprint covers the cells of the buffer"
    elif without and not with_radar:
        status, words = "not_covered", "the pass's footprint does not cover the point: no cell of the buffer has radar data after"
    elif with_radar and without:
        status, words = "partly_covered", "the pass's footprint covers part of the buffer only"
    else:
        status, words = "not_known_from_the_map", "the map cannot say: no cell, or terrain or permanent water answers every cell first"
    return {"status": status, "words": words, "cells": int(values.size), "cells_with_radar_data_after": with_radar,
            "cells_without_radar_data_after": without, "cells_answered_first_by_terrain_or_permanent_water": terrain}


def reason_counts(reasons: np.ndarray) -> dict[str, int]:
    """Cells per reason label of the method (only labels that occur)."""

    return m1z.reason_counts(np.asarray(reasons, dtype="uint8"))


def measure_pass(code: np.ndarray, reason: np.ndarray, roads: Roads, *, flood_input_id: str,
                 points: Mapping[str, BaseGeometry] | None = None, hospital: BaseGeometry | None = None) -> dict[str, Any]:
    """Everything the three tests read of one pass: the central closure, and what the map says near each point and
    near the hospital site."""

    closure = central_closure(code, roads, tier=OWN_CANDIDATE_TIER, flood_input_id=flood_input_id)
    near: dict[str, Any] = {}
    for point_id, geometry in (points or {}).items():
        rows, cols = cells_near(geometry, roads.grid, BUFFER_3B_M)
        near[point_id] = {"cells_within_the_buffer": code_counts(code[rows, cols]), "footprint": footprint_cover(reason[rows, cols]),
                          "closed_edges_within_the_buffer": edge_rows(closure, roads, geometry, BUFFER_3B_M),
                          "delayed_edges_within_the_buffer": len(edge_rows(closure, roads, geometry, BUFFER_3B_M, states=("delayed",)))}
    site = None
    if hospital is not None:
        rows, cols = cells_near(hospital, roads.grid, 0.0)
        zone_rows, zone_cols = cells_near(hospital, roads.grid, HOSPITAL_DISTANCE_M)
        site = {
            "cells_inside_the_site": {**code_counts(code[rows, cols]), "reasons": reason_counts(reason[rows, cols])},
            "cells_inside_or_within_200_m": {**code_counts(code[zone_rows, zone_cols]), "reasons": reason_counts(reason[zone_rows, zone_cols])},
            "footprint": footprint_cover(reason[zone_rows, zone_cols]),
            "closed_edges_within_200_m": edge_rows(closure, roads, hospital, HOSPITAL_DISTANCE_M),
            "delayed_edges_within_200_m": len(edge_rows(closure, roads, hospital, HOSPITAL_DISTANCE_M, states=("delayed",))),
        }
    return {"closure": closure, "points": near, "hospital": site}


# ---------------------------------------------------------------------------
# The records the tests read
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PointSpec:
    """One listed point of test 3b: what the list says, and the geometry the test uses (``None`` when not placed)."""

    point_id: str
    geometry: BaseGeometry | None
    listed: Mapping[str, Any]
    placement: Mapping[str, Any]


def check_amendment(amendment: Mapping[str, Any]) -> dict[str, Any]:
    """Check that amendment 1 states the five points, the buffer and the hospital object this code applies.

    Raises:
        StageError: when it states other points, another buffer or another hospital object.
    """

    try:
        change = amendment["changes"]["test_3b_points"]
        listed = list(change["points"])
        buffer_m = float(change["buffer_m"])
        hospital_object = str(amendment["changes"]["test_4_hospital"]["object"])
    except (KeyError, TypeError, ValueError) as error:
        raise StageError(f"{AMENDMENT_1} does not hold the test 3b points and the test 4 object: {error!r}") from error
    if len(listed) != len(POINTS_3B) or any(str(spec["words"]) not in str(text) for spec, text in zip(POINTS_3B, listed)):
        raise StageError(f"{AMENDMENT_1} lists other test 3b points than the five this code applies")
    if buffer_m != BUFFER_3B_M:
        raise StageError(f"{AMENDMENT_1} states a buffer of {buffer_m} m; this code applies {BUFFER_3B_M} m")
    way = re.search(r"way (\d+)", hospital_object)
    if way is None:
        raise StageError(f"{AMENDMENT_1} names no OpenStreetMap way for test 4")
    return {"points": listed, "buffer_m": buffer_m, "hospital_osm_way": way.group(1), "measure": change.get("measure"),
            "found_if": change.get("found_if")}


def _entry(record: Mapping[str, Any], section: str, point_id: str) -> Mapping[str, Any]:
    for entry in record.get(section) or []:
        if entry.get("id") == point_id:
            return entry
    raise StageError(f"{CONSEQUENCE_POINTS} holds no {point_id} under {section}")


def point_specs(record: Mapping[str, Any]) -> list[PointSpec]:
    """The five points of test 3b with the geometry amendment 1 gives each (EPSG:32647).

    Raises:
        StageError: when a placed point has no geometry in the record.
    """

    specs = []
    for spec in POINTS_3B:
        entry = _entry(record, str(spec["section"]), str(spec["id"]))
        listed = {key: entry.get(key) for key in ("entry_as_listed_th", "authority", "route", "km_as_listed", "in_protocol_list")}
        listed["tambon"] = (entry.get("tambon_cod_ab") or {}).get("adm3_name")
        geometry: BaseGeometry | None = None
        if spec["position"] == "km_59_100_from_southern_end":
            check = entry.get("check_chainage_from_either_end") or {}
            found = (check.get("km_59_100_from_southern_end") or {}).get("epsg32647")
            if not found:
                raise StageError(f"{spec['id']}: the record holds no point at km 59.1 from the southern end of the route line")
            geometry = shape(found)
            placed = (entry.get("placed") or {}).get("epsg32647")
            placement = {"used": "the point at 59.1 km from the southern end of the merged OSM route line "
                                 "(check_chainage_from_either_end.km_59_100_from_southern_end), amendment 1",
                         "reading_consistent_with_the_lists_in_the_record": check.get("reading_consistent_with_the_lists"),
                         "distance_to_the_recorded_tambon_part_m": None if not placed else rounded(geometry.distance(shape(placed)), 1),
                         "placement_confidence_in_the_record": entry.get("placement_confidence")}
        elif spec["position"] == "placed":
            found = (entry.get("placed") or {}).get("epsg32647")
            if entry.get("status") != "placed" or not found:
                raise StageError(f"{spec['id']}: amendment 1 places it as recorded, and the record gives it no position")
            geometry = shape(found)
            placement = {"used": "the placed part as recorded (placed.epsg32647)", "method_in_the_record": entry.get("method"),
                         "placement_confidence_in_the_record": entry.get("placement_confidence"),
                         "share_inside_the_listed_tambon": entry.get("share_inside_named_tambon")}
        else:
            placement = {"used": None, "status_in_the_record": entry.get("status"),
                         "why": "amendment 1: not in OpenStreetMap; it has no position and counts as not found"}
        if geometry is not None:
            placement = {**placement, "geometry_type": geometry.geom_type, "length_m": rounded(geometry.length, 1)}
        specs.append(PointSpec(str(spec["id"]), geometry, listed, placement))
    return specs


@dataclass(frozen=True)
class HospitalSpec:
    """The site of Nan Hospital (EPSG:32647) and its identification."""

    polygon: BaseGeometry
    about: Mapping[str, Any]


def hospital_spec(record: Mapping[str, Any], osm_way: str) -> HospitalSpec:
    """The site polygon of the hospital amendment 1 names, from the consequence record.

    Raises:
        StageError: when the record holds no such hospital or no polygon for it.
    """

    for entry in record.get("hospitals") or []:
        if entry.get("id") == HOSPITAL_ID:
            break
    else:
        raise StageError(f"{CONSEQUENCE_POINTS} holds no hospital {HOSPITAL_ID}")
    if str((entry.get("osm") or {}).get("id")) != osm_way:
        raise StageError(f"{HOSPITAL_ID} is OSM way {(entry.get('osm') or {}).get('id')}; amendment 1 names way {osm_way}")
    polygon = ((entry.get("polygon") or {}).get("wgs84"))
    if not polygon:
        raise StageError(f"{HOSPITAL_ID} has no site polygon in the record")
    site = flood_inputs.as_multipolygon(flood_inputs.project(shape(polygon), flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS))
    about = {"id": HOSPITAL_ID, "osm": entry.get("osm"), "name_th": entry.get("name_th"),
             "operator": (entry.get("tags") or {}).get("operator"), "area_m2_in_the_record": (entry.get("polygon") or {}).get("area_m2"),
             "area_m2_measured": rounded(site.area, 1)}
    return HospitalSpec(site, about)


def hospital_news(news: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The news records whose topic is the hospital."""

    return [record for record in news.get("records") or [] if "hospital" in str(record.get("topic", ""))]


def news_beside(records: Sequence[Mapping[str, Any]], start: datetime) -> list[dict[str, Any]]:
    """The hospital news records cited beside a pass, with the hours from the pass to each publication."""

    out = []
    for record in records:
        published = parse_utc(record.get("published_local"))
        out.append({"id": record.get("id"), "published_local": record.get("published_local"), "time_said": record.get("time_said"),
                    "hours_from_the_pass_to_publication": None if published is None else rounded((published - start).total_seconds() / 3600, 1)})
    return out


def gauges_at(news: Mapping[str, Any], start: datetime) -> list[dict[str, Any]]:
    """For each gauge of the news record, whether the river stood above each published level at the pass."""

    out = []
    when = start.astimezone(THAI).replace(tzinfo=None)
    for gauge in news.get("gauge_records") or []:
        levels = {}
        for name, level in (gauge.get("levels") or {}).items():
            runs = [(datetime.strptime(first, "%Y-%m-%d %H:%M"), datetime.strptime(last, "%Y-%m-%d %H:%M"))
                    for first, last in level.get("runs_above_thai_time") or []]
            levels[name] = {"level_m_msl": level.get("level_m_msl"), "above_at_the_pass": any(first <= when <= last for first, last in runs)}
        out.append({"station": gauge.get("station"), "place": gauge.get("place"), "river": gauge.get("river"), "levels": levels,
                    "peak_times_thai_time": gauge.get("peak_times_thai_time")})
    return out


# ---------------------------------------------------------------------------
# The three tests
# ---------------------------------------------------------------------------


def rule_v2_water(fine: np.ndarray, transform: Any, rectangle: Mapping[str, float]) -> np.ndarray:
    """Rule v2 water as the R26 road check reads it, inside the rectangle only.

    1 water, 255 no value and any other value not water (as the test stage reads rule v2), in the codes of
    ``floodguard.theos2_cross_check``; a pixel whose centre lies outside the rectangle is unobservable.

    Raises:
        StageError: for a raster that is not north-up with square pixels.
    """

    if abs(transform.b) > 1e-9 or abs(transform.d) > 1e-9 or transform.a <= 0 or abs(transform.a + transform.e) > 1e-9:
        raise StageError("the rule v2 water raster is not north-up with square pixels")
    data = np.asarray(fine)
    water = np.where(data == 1, cc.WATER_YES, cc.WATER_NO).astype("uint8")
    water[data == 255] = cc.WATER_UNOBSERVABLE
    x = transform.c + (np.arange(data.shape[1]) + 0.5) * transform.a
    y = transform.f + (np.arange(data.shape[0]) + 0.5) * transform.e
    inside = (((x >= float(rectangle["west"])) & (x <= float(rectangle["east"])))[None, :]
              & ((y >= float(rectangle["south"])) & (y <= float(rectangle["north"])))[:, None])
    water[~inside] = cc.WATER_UNOBSERVABLE
    return water


def roads_under_theos2_water(roads: Roads, rectangle: Mapping[str, float], water: np.ndarray, transform: Any,
            closures: Mapping[str, Mapping[str, Any]], *, with_edges: Sequence[str] = ("our_map",)) -> dict[str, Any]:
    """Test 3a: the closed edges inside the chip against the edges seen under rule v2 water (the R26 rule).

    ``closures`` maps a name (``our_map``, ``case_n2_reference``) to :func:`central_closure` of that extent. The edges
    of the names in ``with_edges`` are listed one by one; for the others only counts and shares are given.
    """

    chip = shapely.box(float(rectangle["west"]), float(rectangle["south"]), float(rectangle["east"]), float(rectangle["north"]))
    inside = sorted(edge_id for edge_id, line in roads.lines.items() if line.intersects(chip))
    if inside:
        segments = np.array([np.asarray(roads.lines[edge_id].coords)[[0, -1]] for edge_id in inside], dtype="float64")
        measured = cc.centreline_water_lengths(segments, water, west=float(transform.c), north=float(transform.f), cell_m=float(transform.a))
    else:
        measured = []
    compared = [index for index, row in enumerate(measured) if row["length_m"] > 0 and row["observable_share"] >= COMPARED_OBSERVABLE_SHARE_MIN]
    seen = [cc.seen_under_water(measured[index]) for index in compared]
    lengths = [measured[index]["length_m"] for index in compared]
    result: dict[str, Any] = {
        "edges_crossing_the_rectangle": len(inside),
        "edges_compared": len(compared),
        "rule_for_compared": "at least 90% of the centreline on observable rule v2 pixels inside the rectangle (R26)",
        "seen_under_water_rule": "20 m of centreline on rule v2 water or more; an edge shorter than 40 m also at half its length or more (R26)",
        "edges_seen_under_water": int(sum(seen)),
        "km_compared": rounded(sum(lengths) / 1000.0),
        "km_seen_under_water": rounded(sum(length for length, wet in zip(lengths, seen) if wet) / 1000.0),
        "by_extent": {},
    }
    for name, closure in closures.items():
        closed_inside = [edge_id for edge_id in inside if edge_id in closure["closed"]]
        flags = [inside[index] in closure["closed"] for index in compared]
        agreement = cc.road_agreement(flags, seen, lengths)
        entry: dict[str, Any] = {
            **closure_summary(closure),
            "closed_edges_crossing_the_rectangle": len(closed_inside),
            "closed_edges_compared": int(sum(flags)),
            "closed_edges_not_compared": len(closed_inside) - int(sum(flags)),
            "share_of_closed_edges_seen_under_water": agreement["share_of_rule_closed_that_is_seen_under_water"],
            "share_of_edges_seen_under_water_that_it_closes": agreement["share_of_seen_under_water_that_the_rule_closes"],
            "counts": agreement,
        }
        if name in with_edges:
            rows = []
            for index, wet, closed in zip(compared, seen, flags):
                if not (wet or closed):
                    continue
                edge_id = inside[index]
                edge = roads.edge(edge_id)
                row = measured[index]
                rows.append({"edge_id": edge_id, "osm_way_id": edge.get("osm_way_id"), "road_class": edge.get("road_class"),
                             "bridge": edge.get("bridge"), "length_m": rounded(row["length_m"], 1), "on_water_m": rounded(row["on_water_m"], 1),
                             "observable_share": rounded(row["observable_share"], 4), "closed": bool(closed), "seen_under_water": bool(wet)})
            entry["edges_closed_or_seen_under_water"] = rows
        result["by_extent"][name] = entry
    return result


def reported_cuts_found(points: Sequence[PointSpec], window: Sequence[Pass], maps: Mapping[str, PassMap | None],
            digests: Mapping[str, str], measured: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Test 3b: for each listed point and each pass of the window, the closed edges within 300 m, the footprint, or
    the absence of a map; a point is found when one pass of the window closes an edge within 300 m of it."""

    rows = []
    for point in points:
        passes = []
        found_on = []
        for item in window:
            found = maps.get(item.key)
            entry: dict[str, Any] = {"pass": item.key, "start_thai": as_thai_text(item.start)}
            if point.geometry is None:
                entry["state"] = "the point has no position"
            elif found is None:
                entry.update(map=None, state="no map of this pass",
                             why=f"the radar record gives the pass the status {item.status!r}; the footprint at the point is not known")
            else:
                near = measured[item.key]["points"][point.point_id]
                closed = near["closed_edges_within_the_buffer"]
                entry.update(map=found.as_json(digests.get(item.key)), footprint=near["footprint"],
                             cells_within_the_buffer=near["cells_within_the_buffer"], closed_edges_within_the_buffer=closed,
                             delayed_edges_within_the_buffer=near["delayed_edges_within_the_buffer"],
                             state="closes an edge within 300 m" if closed else
                             "the pass's footprint does not cover the point" if near["footprint"]["status"] == "not_covered" else
                             "closes no edge within 300 m")
                if closed:
                    found_on.append(item.key)
            passes.append(entry)
        rows.append({"id": point.point_id, "listed": dict(point.listed), "placement": dict(point.placement),
                     "placed": point.geometry is not None, "found": bool(found_on), "found_on_passes": found_on, "passes": passes})
    placed = sum(1 for row in rows if row["placed"])
    found_count = sum(1 for row in rows if row["found"])
    return {
        "found_if": "at least one vehicle edge within 300 m of the point is closed at the central level on at least one "
                    "pass that starts between 2025-07-20 00:00 and 2025-07-31 23:59 Thai time (amendment 1)",
        "buffer_m": BUFFER_3B_M,
        "window_thai_time": list(WINDOW_3B_THAI),
        "passes_in_the_window": [{**item.as_json(), "map": None if maps.get(item.key) is None else maps[item.key].as_json(digests.get(item.key))}
                                 for item in window],
        "points": rows,
        "measure": {"listed_points": len(rows), "placed": placed, "found": found_count,
                    "share_of_the_five_listed_points_found": rounded(found_count / len(rows), 4) if rows else None,
                    "found_ids": [row["id"] for row in rows if row["found"]],
                    "words": "the share of the five listed points found, with the number that could be placed beside it; "
                             "a point without a position counts as not found. No share of our closures that are listed "
                             "cuts is given: the list is a month's summary."},
    }


def hospital_check(hospital: HospitalSpec, by_date: Mapping[str, Sequence[Pass]], maps: Mapping[str, PassMap | None],
           digests: Mapping[str, str], measured: Mapping[str, Mapping[str, Any]], news: Mapping[str, Any]) -> dict[str, Any]:
    """Test 4: what the passes of 22 and 26 July (Thai time) show at the hospital site, beside the news records."""

    records = hospital_news(news)
    entries = []
    for day, passes in by_date.items():
        if not passes:
            entries.append({"thai_date": day, "pass": None, "state": "no pass of the radar record starts on this Thai date"})
        for item in passes:
            found = maps.get(item.key)
            entry: dict[str, Any] = {"thai_date": day, "pass": item.as_json(), "news_records_beside": news_beside(records, item.start),
                                     "gauges_at_the_pass": gauges_at(news, item.start)}
            if found is None:
                entry.update(map=None, state="no map of this pass", why=f"the radar record gives the pass the status {item.status!r}")
            else:
                entry.update(map=found.as_json(digests.get(item.key)), **measured[item.key]["hospital"])
            entries.append(entry)
    return {
        "check_only": True, "pass_mark": None,
        "object": dict(hospital.about),
        "rule": "flagged and no-answer cells whose centre lies inside the site polygon or within 200 m of it, and the "
                "vehicle edges within 200 m closed at the central level, on the passes of 22 and 26 July 2025 (Thai time)",
        "distance_m": HOSPITAL_DISTANCE_M,
        "passes": entries,
        "news_records_cited": [record.get("id") for record in records],
        "words": "a check only, with no pass mark: the maps are set beside the news records by their ids, not scored against them",
    }


# ---------------------------------------------------------------------------
# The stage
# ---------------------------------------------------------------------------


def _load_script(name: str, module_name: str) -> Any:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"scripts/{name}.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_vehicle_graph(context_path: Path, external: Path) -> tuple[list[dict[str, Any]], Mapping[str, Sequence[float]], dict[str, Any]]:
    """The baseline vehicle graph of the frame, read as the score chain reads it (``nan_case_chain.load_context``)."""

    chain = _load_script("nan_case_chain", "nan_case_chain_script")
    try:
        graph, record = chain.load_context(context_path, external)
    except chain.ChainError as error:
        raise StageError(str(error)) from error
    return list(graph.edges), graph.node_coordinates, record


def routing_frame(path: Path) -> flood_inputs.Frame:
    """The routing geometry of the frame (GeoJSON, longitude and latitude) as the score chain builds it."""

    data = read_json(path)
    features = data.get("features") if data.get("type") == "FeatureCollection" else [data]
    geometries = [shape(feature["geometry"] if "geometry" in feature else feature) for feature in features]
    geometry = shapely.union_all(np.array(geometries, dtype=object))
    return flood_inputs.frame_from_wgs84(flood_inputs.ROUTING_CONTEXT, "the routing geometry of the frame", geometry, {})


def file_entry(path: Path, label: str, sha256: str | None = None) -> dict[str, Any]:
    """A file of the record: its label (never a machine path) and its SHA-256."""

    return {"path": label, "sha256": sha256 or sha256_file(path)}


def code_hashes() -> dict[str, str]:
    """SHA-256 of this script and of the code it reuses, as Git holds them (LF)."""

    found = {"script_sha256": code_sha256(Path(__file__))}
    for name in ("closure_rules", "access_diff", "nan_case_chain", "flood_inputs", "theos2_cross_check", "m1z", "grade_join"):
        found[f"{name}_module_sha256"] = code_sha256(ROOT / "src" / "floodguard" / f"{name}.py")
    for name in ("nan_case_chain", "build_access_diff"):
        found[f"{name}_script_sha256"] = code_sha256(ROOT / "scripts" / f"{name}.py")
    found["line_ends"] = "LF: the bytes Git holds; a checkout's CRLF line ends are read as LF"
    return found


def superseded(path: Path, reason: str | None) -> dict[str, Any] | None:
    """What a ``--replace`` run replaces: the old record's time and SHA-256, and the reason given."""

    if not path.exists():
        return None
    old = read_json(path)
    return {"reason": reason, "generated_at_utc": old.get("generated_at_utc"), "sha256": sha256_file(path)}


def stage(root: Path, arguments: argparse.Namespace, hooks: Mapping[str, Any]) -> dict[str, Any]:
    """Run tests 3a, 3b and 4 once, after the test of the case, and write the record.

    Raises:
        StageError: when the test result or the freeze record is missing, the record exists (without ``--replace`` and
            ``--reason``), or an input is missing, behind the firewall, or not the file the records name.
    """

    if not (root / TEST_RESULT).is_file():
        raise StageError(f"the order rule of the Nan protocol: tests 3a, 3b and 4 run after the test, and {TEST_RESULT} does not exist")
    if not (root / FREEZE).is_file():
        raise StageError(f"no freeze record {FREEZE}: the maps of the case are made only under a freeze")
    output = root / OUTPUT
    if arguments.replace and not arguments.reason:
        raise StageError("--replace needs --reason")
    if output.exists() and not arguments.replace:
        raise StageError(f"{OUTPUT} exists: the stage runs once (replace only with --replace and --reason)")
    if not (root / AMENDMENT_1).is_file():
        raise StageError(f"{AMENDMENT_1} is missing: tests 3b and 4 are applied as amendment 1 changes them")
    external = Path(arguments.external_root)
    started = now_utc()

    protocol, amendment = read_json(root / PROTOCOL), read_json(root / AMENDMENT_1)
    points_record, news = read_json(root / CONSEQUENCE_POINTS), read_json(root / NEWS_RECORDS)
    radar, frame_record = read_json(root / RADAR_RECORD), read_json(root / FRAME_RECORD)
    v1b, test_result = read_json(root / PROTOCOL_V1B), read_json(root / TEST_RESULT)
    freeze_sha256, test_sha256 = sha256_file(root / FREEZE), sha256_file(root / TEST_RESULT)
    stated = check_amendment(amendment)
    grid = nan.grid_from_record(protocol["grid"]["frame"])
    rectangle = protocol["grid"]["chips"][CHIP_TOWN]
    points = point_specs(points_record)
    hospital = hospital_spec(points_record, stated["hospital_osm_way"])

    # --- the passes and their frozen maps -----------------------------------------------------------------------
    passes = passes_of_record(radar)
    maps_dir = Path(arguments.maps_dir) if arguments.maps_dir else external / MAPS
    index_path = maps_dir / MAPS_INDEX
    if not index_path.is_file():
        raise StageError(f"no maps index in {maps_dir}: run the maps stage of scripts/nan_case_method.py first")
    index = read_json(index_path)
    if (index.get("freeze_record") or {}).get("sha256") != freeze_sha256:
        raise StageError("the maps index was not written under the freeze record in force")
    found_maps = discover_maps(maps_dir)
    window = [item for item in passes if in_window_3b(item.start)]
    pass_3a = nearest_pass(passes, parse_utc(TEST_3A_PASS_UTC))
    if pass_3a is None:
        raise StageError(f"the radar record lists no pass within {PASS_MATCH_MINUTES} minutes of {TEST_3A_PASS_UTC} (test 3a)")
    by_date = {day: [item for item in passes if thai_date(item.start) == day] for day in TEST_4_THAI_DATES}
    needed: dict[str, Pass] = {item.key: item for item in [*window, pass_3a, *(item for day in by_date.values() for item in day)]}
    assigned: dict[str, PassMap | None] = {}
    digests: dict[str, str] = {}
    for key, item in needed.items():
        found = match_map(item, found_maps)
        if found is None and item.status == "fetched":
            raise StageError(f"pass {key} was fetched and has no map: run the maps stage of scripts/nan_case_method.py")
        if found is not None:
            digests[key] = check_map(found, index, freeze_sha256)
        assigned[key] = found
    if assigned[pass_3a.key] is None:
        raise StageError(f"the pass of test 3a ({pass_3a.key}) has no map")

    # --- the frame's roads and routing geometry --------------------------------------------------------------------
    context_path = Path(arguments.context) if arguments.context else external / CONTEXT
    routing_path = Path(arguments.routing_geometry) if arguments.routing_geometry else external / ROUTING_GEOMETRY
    stated_files = frame_record.get("files_outside_git") or {}
    checked: dict[str, str] = {}
    for name, path in (("context", context_path), ("routing_geometry", routing_path)):
        firewall(path, root)
        if not path.is_file():
            raise StageError(f"the {name.replace('_', ' ')} of the frame is missing: {path.name}")
        checked[name] = sha256_file(path)
        if (stated_files.get(name) or {}).get("sha256") != checked[name]:
            raise StageError(f"{path.name} is not the {name.replace('_', ' ')} {FRAME_RECORD} names")

    # --- test 3a's references (opened only now, after the test) ------------------------------------------------------
    try:
        named = read_json(root / RULE_V2_FREEZE)["frozen_rule"]["chips"][RULE_V2_CHIP]["raster_outside_git"]
    except (OSError, KeyError, TypeError) as error:
        raise StageError(f"{RULE_V2_FREEZE} names no rule v2 raster of {RULE_V2_CHIP}: {error}") from error
    water_path = external / RULE_V2_WORK / str(named["name"])
    firewall(water_path, root)
    if not water_path.is_file() or sha256_file(water_path) != named["sha256"]:
        raise StageError(f"{named['name']} is missing or is not the raster the rule v2 freeze names")
    n2_named = ((test_result.get("binding") or {}).get("reference_of_case_N2")) or None
    n2_path: Path | None = None
    if arguments.case_n2_reference:
        n2_path = Path(arguments.case_n2_reference)
    elif isinstance(n2_named, Mapping) and n2_named.get("name"):
        candidate = external / CASE_N2_REFERENCE / str(n2_named["name"])
        n2_path = candidate if candidate.is_file() else None
    n2_sha256 = None
    if n2_path is not None:
        firewall(n2_path, root)
        if not n2_path.is_file():
            raise StageError(f"the case N2 reference {n2_path.name} is missing")
        n2_sha256 = sha256_file(n2_path)
        if isinstance(n2_named, Mapping) and n2_named.get("sha256") and n2_named["sha256"] != n2_sha256:
            raise StageError(f"{n2_path.name} is not the case N2 reference the test record names")

    # --- the roads the tests read ------------------------------------------------------------------------------------
    load_graph: Callable[[Path, Path], Any] = hooks.get("load_graph", load_vehicle_graph)
    edges, node_coordinates, graph_record = load_graph(context_path, external)
    chip = shapely.box(float(rectangle["west"]), float(rectangle["south"]), float(rectangle["east"]), float(rectangle["north"]))
    reach = [*((point.geometry, BUFFER_3B_M) for point in points if point.geometry is not None),
             (hospital.polygon, HOSPITAL_DISTANCE_M), (chip, 0.0)]
    selected, lines = select_edges(edges, node_coordinates, reach)
    try:
        closure_arguments = access_diff.closure_arguments(v1b)
    except access_diff.AccessDiffError as error:
        raise StageError(str(error)) from error
    minimum_px = int(v1b["closure_rule_v1"]["parameters"]["raster_minimum_polygon_px"])
    roads = Roads(selected, node_coordinates, lines, routing_frame(routing_path), closure_arguments, minimum_px, grid)

    # --- every pass once ---------------------------------------------------------------------------------------------
    test4_keys = {item.key for day in by_date.values() for item in day}
    window_keys = {item.key for item in window}
    placed = {point.point_id: point.geometry for point in points if point.geometry is not None}
    measured: dict[str, dict[str, Any]] = {}
    for key, item in needed.items():
        found = assigned[key]
        if found is None:
            continue
        bands = read_code_raster(found.path, grid, ("code_central", "reason_central"))
        measured[key] = measure_pass(bands["code_central"], bands["reason_central"], roads,
                                     flood_input_id=f"nan_m1z_{found.label.lower()}_central",
                                     points=placed if key in window_keys else None,
                                     hospital=hospital.polygon if key in test4_keys else None)
        del bands

    # --- test 3a ------------------------------------------------------------------------------------------------------
    import rasterio

    with rasterio.open(water_path) as source:
        if source.crs is None or source.crs.to_epsg() != grid.epsg:
            raise StageError(f"{water_path.name} is not in EPSG:{grid.epsg}")
        water = rule_v2_water(source.read(1), source.transform, rectangle)
        water_transform = source.transform
    closures = {"our_map": measured[pass_3a.key]["closure"]}
    n2_record: dict[str, Any] = {"given": False, "why": "no case N2 reference raster was given or found"}
    if n2_path is not None:
        n2_code = read_code_raster(n2_path, grid, ("reference",))["reference"]
        closures["case_n2_reference"] = central_closure(n2_code, roads, tier=CASE_N2_TIER, flood_input_id="nan_case_n2_reference")
        del n2_code
        n2_record = {"given": True, "file": {"name": n2_path.name, "sha256": n2_sha256}, "tier": CASE_N2_TIER, "report_only": True,
                     "what": (n2_named or {}).get("what") if isinstance(n2_named, Mapping) else None}
    t3a = roads_under_theos2_water(roads, rectangle, water, water_transform, closures)
    t3a = {"pass": {**pass_3a.as_json(), "map": assigned[pass_3a.key].as_json(digests[pass_3a.key])},
           "rectangle_epsg32647": {key: float(rectangle[key]) for key in ("west", "south", "east", "north")},
           "rule_v2_water": {"name": water_path.name, "sha256": named["sha256"], "pixel_m": float(water_transform.a)},
           "case_n2_reference": n2_record, **t3a,
           "words": "agreement of the modelled closures with roads seen under THEOS-2 rule v2 water 19 hours before the "
                    "pass; the case N2 extent is report only"}

    # --- tests 3b and 4 -------------------------------------------------------------------------------------------------
    t3b = reported_cuts_found(points, window, assigned, digests, measured)
    t4 = hospital_check(hospital, by_date, assigned, digests, measured, news)

    used = sorted(measured)
    attribution = ["Road and hospital positions (c) OpenStreetMap contributors, Open Database Licence 1.0 (ODbL).",
                   "Contains modified Copernicus Sentinel data (2025), processed by FloodGuard.",
                   "THEOS-2 figures from imagery (c) GISTDA, sample provided for GeoHackathon 2026; the imagery stays outside Git."]
    if n2_path is not None:
        attribution.append("Case N2 extent: Provided by JAXA; used as provided." if "jaxa" in n2_path.name.lower() else
                           "Case N2 extent: Copernicus Emergency Management Service, Global Flood Monitoring (GFM); used as provided.")
    record = {
        "schema": SCHEMA,
        "case_id": "N1",
        "generated_at_utc": now_utc(),
        "source_timestamp": (f"Nan passes {', '.join(as_utc_text(needed[key].start) for key in used)}; THEOS-2 2025-07-31T03:51:00Z "
                             f"(test 3a); Ministry of Transport list of 2025-07-31; OpenStreetMap retrieved "
                             f"{((points_record.get('inputs') or {}).get('osm_extract') or {}).get('retrieved_at_utc')}"),
        "confidence_class": "low",
        "confidence_basis": "One event; closures are modelled from our own radar map by closure rule v1; the references are "
                            "an optical rule, a month's list of cuts placed on OpenStreetMap and press reports, none checked "
                            "on the ground.",
        "assumptions": ASSUMPTIONS,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "what_this_is": "Tests 3a, 3b and 4 of the Nan case (protocol v1 as amendment 1 changes them): the roads closure "
                        "rule v1 closes on the frozen maps of the Nan passes, set beside roads seen under THEOS-2 water, "
                        "the listed road cuts and the flooding of Nan Hospital. Figures only; not an official warning.",
        "order": {
            "started_utc": started,
            "freeze_record": {"path": FREEZE, "sha256": freeze_sha256},
            "test_result": {"path": TEST_RESULT, "sha256": test_sha256, "in_head_unchanged": same_as_head(root, TEST_RESULT)},
            "maps_index": {"path": f"<external>/{MAPS.as_posix()}/{MAPS_INDEX}", "sha256": sha256_file(index_path),
                           "freeze_record_matches": True,
                           "test_result_matches": (index.get("test_result") or {}).get("sha256") == test_sha256},
            "git_commit": git_head(root),
        },
        "inputs": {
            "protocol": file_entry(root / PROTOCOL, PROTOCOL),
            "amendment_1": file_entry(root / AMENDMENT_1, AMENDMENT_1),
            "planning_protocol_v1b": file_entry(root / PROTOCOL_V1B, PROTOCOL_V1B),
            "consequence_points": file_entry(root / CONSEQUENCE_POINTS, CONSEQUENCE_POINTS),
            "news_records": file_entry(root / NEWS_RECORDS, NEWS_RECORDS),
            "radar_record": file_entry(root / RADAR_RECORD, RADAR_RECORD),
            "frame_record": file_entry(root / FRAME_RECORD, FRAME_RECORD),
            "rule_v2_freeze": file_entry(root / RULE_V2_FREEZE, RULE_V2_FREEZE),
            "context": {"path": f"<external>/{CONTEXT.as_posix()}" if not arguments.context else context_path.name,
                        "sha256": checked["context"], "canonical_sha256": graph_record.get("canonical_sha256")},
            "routing_geometry": {"path": f"<external>/{ROUTING_GEOMETRY.as_posix()}" if not arguments.routing_geometry else routing_path.name,
                                 "sha256": checked["routing_geometry"]},
            "maps": {key: assigned[key].as_json(digests[key]) for key in used},
            "rule_v2_water_chip_003": {"path": f"<external>/{RULE_V2_WORK.as_posix()}/{water_path.name}", "sha256": named["sha256"]},
            "case_n2_reference": None if n2_path is None else {"name": n2_path.name, "sha256": n2_sha256},
        },
        "rules": {
            "closure": {"rule": closure_rules.CLOSURE_RULE_VERSION, "level": CENTRAL, "treatment": nan.BINDING_TREATMENT,
                        "raster_minimum_polygon_px": minimum_px, "polygon_connectivity": nan.CLOSURE_POLYGON_CONNECTIVITY,
                        "length_thresholds_m": dict(closure_arguments["length_thresholds_m"]),
                        "applied_by": "floodguard.nan_case_chain.closure_extent, floodguard.flood_inputs.clip_to_frame, "
                                      "floodguard.closure_rules.edge_intersections, floodguard.access_diff.flooded_edges"},
            "edges_measured": {"edges_of_the_graph": len(edges), "road_edges_the_tests_read": len(selected),
                               "graph": {key: value for key, value in (graph_record.get("graph") or {}).items() if not isinstance(value, (dict, list))}},
            "amendment_1": stated,
        },
        "test_3a": t3a,
        "test_3b": t3b,
        "test_4": t4,
        "closures_by_pass": {key: closure_summary(measured[key]["closure"]) for key in used},
        "attribution": attribution,
        "rights_note": "Figures, edge identifiers and OpenStreetMap positions only; no raster and no map geometry. Of the "
                       "case N2 extent only counts and shares are given, as the protocol keeps any reproduction of a JAXA "
                       "or GFM map out of Git.",
        "code_sha256": code_hashes(),
        "limits": LIMITS,
        "supersedes": superseded(output, arguments.reason) if arguments.replace else None,
    }
    write_record(output, record)
    return record


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    """The command line of the stage."""

    commands = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands.add_argument("--external-root", required=True, help="the external data root (outside Git)")
    commands.add_argument("--maps-dir", help="the maps folder; default <external root>/proposal_execution/nan_case_v1/method/maps")
    commands.add_argument("--context", help="the frame's vehicle context; default <external root>/.../frame/e4_vehicle_candidate/context_inputs.json")
    commands.add_argument("--routing-geometry", help="the frame's routing geometry; default <external root>/.../frame/n1_routing_geometry.geojson")
    commands.add_argument("--case-n2-reference", help="the case N2 reference raster for test 3a (report only); default the one the test record names, if found")
    commands.add_argument("--replace", action="store_true", help="replace an existing record (needs --reason)")
    commands.add_argument("--reason", help="why the record is replaced")
    return commands


def run(argv: Sequence[str] | None = None, *, root: Path | None = None, hooks: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Run the stage; raises :class:`StageError` when it refuses."""

    return stage(Path(root or ROOT), parser().parse_args(argv), hooks or {})


def main(argv: Sequence[str] | None = None) -> int:
    """Run the stage from the command line; 2 when it refuses."""

    try:
        run(argv)
    except StageError as error:
        print(f"refused: {error}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
