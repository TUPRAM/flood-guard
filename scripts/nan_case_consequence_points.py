"""Place the reported road cuts and the two hospitals of the Nan case on OpenStreetMap, and record the public news.

Case N1, tests 3b and 4 (``docs/proposal_execution/nan_case_protocol_v1.json``; in words
``docs/proposal_execution/nan_case_plan_v1.md``). The protocol lists four points of the Ministry of Transport summary
of 31 July 2025 inside the frame. Each is placed on the OpenStreetMap way with that route reference, by milestone
nodes (``highway=milestone`` with a ``distance`` tag) where they exist, interpolating; otherwise as the part of the
route inside the named tambon (COD-AB ``tha_admin3``). A route that is not found is recorded as not found; no
position is guessed. Nan Hospital and Wiang Sa Hospital are located from OpenStreetMap with the routing-point rule of
the SE2 frame (protocol v1b).

Stages (``--stage``):

``extract``
    Read the OSM extract with pyogrio inside the frame's bounding box widened by 0.25 degrees (lines with a highway
    tag, every tagged node, areas with an amenity or healthcare tag) into ``osm_extract_v1.gpkg`` in the work folder.
``place``
    Place the cuts and the hospitals and write ``outputs/nan_case/consequence_points_v1.json``.
``gauge``
    Download the hourly Nan River levels of 15 July to 15 August 2025 that thaiwater.net serves without a login, save
    them under ``gauge/`` in the work folder with their source, and summarise the peaks.
``news``
    Write ``outputs/nan_case/news_records_v1.json``: the dated news and list records found by web research, each with
    its source, publisher, date, a one-sentence paraphrase and what it says about time and place, and the gauge peaks.

The lane never reads radar, a flood map or any reference layer, and computes no flag of the frame. Every path it opens
is checked against the firewall of the case first (:func:`refuse_firewalled`). Positions are OpenStreetMap data
(ODbL 1.0, OpenStreetMap contributors). Planning guidance only; nothing here is an official warning.

Example::

    python scripts/nan_case_consequence_points.py --external-root <external-data-root> --stage all
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path, PurePath
import re
import sys
import time
from typing import Any
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROTOCOL = "docs/proposal_execution/nan_case_protocol_v1.json"
PLAN = "docs/proposal_execution/nan_case_plan_v1.md"
AREAS = "outputs/nan_case/areas_v1.json"
FREEZE = "outputs/nan_case/freeze_v1.json"
POINTS_RECORD = "outputs/nan_case/consequence_points_v1.json"
NEWS_RECORD = "outputs/nan_case/news_records_v1.json"
SCRIPT = "scripts/nan_case_consequence_points.py"
SOURCE_MANIFEST = "outputs/open_context_data_file_manifest.csv"
WORK = PurePath("proposal_execution") / "nan_case_v1" / "consequence"
PBF = PurePath("open_context") / "osm_geofabrik" / "thailand-latest.osm.pbf"
BOUNDARIES = PurePath("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
EXTRACT_NAME = "osm_extract_v1.gpkg"
EXTRACT_RECEIPT = "osm_extract_v1_receipt.json"
GAUGE_DIR = "gauge"
GAUGE_SUMMARY = "gauge_summary_v1.json"
LOG_NAME = "build_log.txt"

EPSG = 32647
PROVINCE = "TH55"
FRAME_DISTRICTS: tuple[str, ...] = ("TH5501", "TH5514", "TH5507")
FRAME_UNITS = 35
EXTRACT_MARGIN_DEG = 0.25
ROUTING_BUFFER_M = 3000.0
BUFFER_QUAD_SEGS = 16
MILESTONE_MAX_OFFSET_M = 30.0
"""A milestone node counts as on the route when it lies within this distance of the merged route line."""
END_MATCH_M = 100.0
"""A single km-0 milestone fixes the direction of the route when it lies within this distance of one end."""
WAY_CARRIES_M = 1.0
TEST_3B_BUFFER_M = 300

FIREWALL_PARTS: tuple[str, ...] = (
    "jaxa_sealed", "img_t2v_20250731035100", "water_v2_chip_001", "water_v2_chip_003", "chip_001_2m", "chip_003_2m",
    "held_chip_00", "gfm",
)
"""Pieces of a path that name a file of the Nan frame this lane may never open (the firewall of the case)."""

MINISTRY_LIST = {
    "url": "https://www.thebangkokinsight.com/news/politics-general/general/1528937/",
    "publisher": "The Bangkok Insight",
    "author": "Wanpen Puttanont",
    "published_local": "2025-07-31T15:44+07:00",
    "what": "Ministry of Transport summary of road network points affected by floods, cumulative 1 to 31 July 2025: "
            "189 points affected, 18 of them impassable; the Nan entries are listed under the Department of Highways "
            "(8 impassable points in 3 provinces) and the Department of Rural Roads (10 impassable in 2 provinces).",
    "original_release": "not found: the Ministry's news pages are served by a script and its content service refused "
                        "automated requests; web searches found press copies only.",
}


@dataclass(frozen=True)
class Route:
    """A route of a ministry entry: its number and the forms its reference takes in OSM.

    ``prefix`` is the Thai provincial prefix of a rural road (``นน`` for Nan) or ``None`` for a national highway.
    A bare number is accepted for a rural road only on ways that touch the province (:func:`ref_matches`).
    """

    number: str
    prefix: str | None
    authority: str


@dataclass(frozen=True)
class Cut:
    """One reported cut: the entry of the list, its route, its km range and the tambon the list names."""

    id: str
    entry_th: str
    route: Route
    km_from: float
    km_to: float
    tambon_pcode: str
    tambon_as_written_th: str
    in_protocol_list: bool
    note: str = ""


DOH = "Department of Highways (กรมทางหลวง)"
DRR = "Department of Rural Roads (กรมทางหลวงชนบท)"
CUTS: tuple[Cut, ...] = (
    Cut("cut_1243_km59_100", "ทล.1243 กม.59+100 ต.น้ำม่วน อ.เวียงสา", Route("1243", None, DOH), 59.1, 59.1, "TH550707",
        "น้ำม่วน", True,
        "The list writes the tambon as น้ำม่วน (the protocol's 'Nam Muan'). Wiang Sa has no tambon of that name in "
        "COD-AB; it is read as Nam Muap (น้ำมวบ, TH550707), the Wiang Sa tambon on route 1243 with the nearest name."),
    Cut("cut_nan4020_km31_690", "นน.4020 กม. ที่ 31+690 – 32+200 ระยะทาง 0.510 กม. ต.ไหล่น่าน อ.เวียงสา",
        Route("4020", "นน", DRR), 31.69, 32.2, "TH550703", "ไหล่น่าน", True),
    Cut("cut_nan4020_km10_500", "นน.4020 กม. ที่ 10+500 – 10+900 ระยะทาง 0.400 กม. ต.นาปัง อ.ภูเพียง",
        Route("4020", "นน", DRR), 10.5, 10.9, "TH551402", "นาปัง", True),
    Cut("cut_nan021_km0_000", "นน.021 กม. ที่ 0+000 – 0+300 ระยะทาง 0.300 กม. ต.ฝายแก้ว อ.ภูเพียง",
        Route("021", "นน", DRR), 0.0, 0.3, "TH551407", "ฝายแก้ว", True,
        "The Department of Rural Roads list of 26 July 2025 names this road the approach road of the bridge "
        "'หัวเวียงเหนือ – น้ำต้วนพัฒนา' (Phu Phiang)."),
)
SUPPLEMENTARY_CUTS: tuple[Cut, ...] = (
    Cut("cut_nan3019_km7_000", "นน.3019 กม. ที่ 7+000 – 8+000 ระยะทาง 1.000 กม. ต.เมืองจัง",
        Route("3019", "นน", DRR), 7.0, 8.0, "TH551405", "เมืองจัง", False,
        "A fifth Nan entry of the same list lies inside the frame: Mueang Chang (เมืองจัง) is a tambon of Phu Phiang, "
        "though the list gives no district for it. It is not among the four points of the protocol; it is placed here "
        "by the same rule for information and takes no part in test 3b unless the protocol is amended before any "
        "flag of the frame is computed."),
)

HOSPITALS: tuple[dict[str, Any], ...] = (
    {"id": "nan_hospital", "name_th": "โรงพยาบาลน่าน", "names": ("โรงพยาบาลน่าน",), "english": ("nan hospital",)},
    {"id": "wiang_sa_hospital", "name_th": "โรงพยาบาลเวียงสา", "names": ("โรงพยาบาลเวียงสา", "โรงพยาบาลอำเภอเวียงสา"),
     "english": ("wiang sa hospital", "wiangsa hospital", "wieng sa hospital")},
)
HOSPITAL_TAGS: tuple[str, ...] = ("name", "name:th", "name:en", "amenity", "healthcare", "emergency", "operator",
                                  "operator:short", "wikidata", "addr:housenumber", "addr:street", "addr:city",
                                  "addr:postcode", "beds", "building")

# --- the gauge records ----------------------------------------------------------------------------------------------
THAIWATER_GRAPH = ("https://api-v3.thaiwater.net/api/v1/thaiwater30/public/waterlevel_graph?station_type=tele_waterlevel"
                   "&station_id={station_id}&start_date={start}&end_date={end}")
THAIWATER_LOAD = "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/waterlevel_load"
GAUGE_PERIOD = ("2025-07-15", "2025-08-15")
GAUGE_STATIONS: tuple[dict[str, Any], ...] = (
    {"station_id": 3246, "code": "N.64", "agency": "RID", "place": "Ban Pha Khwang, Mueang Nan (upstream of the town)",
     "river": "Nan"},
    {"station_id": 3219, "code": "N.1", "agency": "RID", "place": "in front of the Forest Office, Mueang Nan town",
     "river": "Nan"},
    {"station_id": 523, "code": "NAN003", "agency": "HII", "place": "Mueang Nan", "river": "Nan"},
    {"station_id": 1113292, "code": "SKU04 (N.13A)", "agency": "EGAT", "place": "Wiang Sa", "river": "Nan"},
    {"station_id": 512, "code": "NAN009", "agency": "HII", "place": "Wiang Sa", "river": "Nan"},
    {"station_id": 3221, "code": "N.75", "agency": "RID", "place": "Tha Li bridge, Wiang Sa", "river": "Wa (Nam Wa)"},
)
GAUGE_NEWS_CHECKS: tuple[tuple[str, str, float, str], ...] = (
    ("N.1", "2025-07-23 06:00", 5.82, "thansettakij_20250723_levels"),
    ("N.64", "2025-07-23 06:00", 7.99, "thansettakij_20250723_levels"),
    ("N.75", "2025-07-23 06:00", 7.69, "thansettakij_20250723_levels"),
    ("N.1", "2025-07-24 05:00", 9.27, "thairath_20250724_update"),
    ("N.64", "2025-07-24 05:00", 14.65, "thairath_20250724_update"),
)
"""Gauge heights (m above the gauge zero) that news reports gave at a stated Thai time, checked against the series."""
GAUGE_NEWS_BELOW_LEVEL: tuple[tuple[str, str, float, str], ...] = (
    ("SKU04 (N.13A)", "2025-07-23 06:00", 1.50, "thansettakij_20250723_levels"),
)
"""News gave N.13A at 5.00 m against a bank of 6.50 m (1.50 m below); the EGAT series is checked against its
``critical_level_msl`` field, the only field of that station the news reading fits."""

ASSUMPTIONS = [
    "OpenStreetMap is the Geofabrik extract recorded in outputs/open_context_data_file_manifest.csv (retrieved "
    "2026-07-10), a year after the event; a road, milestone or hospital mapped differently in July 2025 is not seen.",
    "A milestone's distance tag is the official km of the route at that node; between two milestones the official km "
    "is spread evenly along the merged OSM line, and beyond the last one the line is read at one OSM metre per "
    "official metre.",
    "A milestone counts as on the route when it lies within 30 m of the merged route line; it is moved onto the line.",
    "Tambon names of the list are matched to COD-AB tha_admin3 polygons (boundaries valid 2022-01-22); the COD-AB "
    "polygons and the OSM roads were not drawn together and can disagree by a few hundred metres.",
    "A route of the list is found only by its reference on OSM ways (or a name that carries the route number); a "
    "road not tagged that way is recorded as not found and given no position.",
    "Hospitals are OSM map records; their operation, entrances and the parts that flooded are not checked here.",
]
LIMITS = [
    "Positions are OpenStreetMap data, not surveyed; the km of a cut comes from the list, its place on the map from "
    "the milestones or the tambon.",
    "The list is a month's cumulative summary: it says where roads were affected during 1 to 31 July 2025, not when "
    "each cut began or ended.",
    "Nothing here is a flag or a flood map; the points are placed before any flag of the frame is computed.",
    "Planning guidance only; not an official warning.",
]


class BuildError(RuntimeError):
    """The run cannot start, or it would break the order or the firewall of the case."""


class PlacementError(ValueError):
    """The milestones of a route cannot be read as one consistent chainage."""


# ---------------------------------------------------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------------------------------------------------

def refuse_firewalled(path: Path | PurePath | str) -> Path:
    """Return ``path`` as a :class:`Path`, or raise :class:`BuildError` when it names a file behind the firewall."""

    text = PurePath(path).as_posix().lower()
    for part in FIREWALL_PARTS:
        if part in text:
            raise BuildError(f"refused to open {PurePath(path).name!r}: it lies behind the firewall of the case ({part})")
    return Path(path)


_HSTORE = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')
_UNESCAPE = re.compile(r"\\(.)")


def parse_other_tags(text: str | None) -> dict[str, str]:
    """The ``other_tags`` field of GDAL's OSM driver (``"key"=>"value",...``) as a dict; escaped quotes are kept."""

    if not isinstance(text, str) or not text:
        return {}
    return {_UNESCAPE.sub(r"\1", key): _UNESCAPE.sub(r"\1", value) for key, value in _HSTORE.findall(text)}


_THAI_PREFIX = re.compile(r"^([฀-๿]{1,4})\s*\.?\s*([0-9][0-9\-]*)$")


def normalise_ref(value: str | None) -> list[str]:
    """The references of a ``ref`` tag in one spelling: split on ';', spaces dropped, ``นน 4020`` -> ``นน.4020``."""

    if not value:
        return []
    out = []
    for part in str(value).split(";"):
        text = part.strip()
        if not text:
            continue
        match = _THAI_PREFIX.match(text)
        if match:
            out.append(f"{match.group(1)}.{match.group(2)}")
        else:
            out.append(re.sub(r"\s+", "", text))
    return out


def ref_matches(value: str | None, route: Route, *, touches_province: bool) -> str | None:
    """How a ``ref`` tag matches ``route``: ``"national"``, ``"prefixed"``, ``"bare"`` or ``None``.

    A national highway matches its number or ``ทล.<number>``. A rural road matches ``<prefix>.<number>``; its bare
    number matches only on a way that touches the province, and a number with another province's prefix
    (``พร.4020``) never matches.
    """

    for ref in normalise_ref(value):
        if route.prefix is None:
            if ref in (route.number, f"ทล.{route.number}"):
                return "national"
            continue
        if ref == f"{route.prefix}.{route.number}":
            return "prefixed"
        if ref == route.number and touches_province:
            return "bare"
    return None


def parse_km(distance: str | None) -> float | None:
    """The km of a milestone's ``distance`` tag (``"13"``, ``"13.5"``, ``"13 km"``, ``"13+500"``), or ``None``."""

    if distance is None:
        return None
    text = str(distance).strip().lower().replace(",", ".")
    match = re.fullmatch(r"(\d+)\+(\d{1,3})", text)
    if match:
        return int(match.group(1)) + int(match.group(2)) / 1000.0
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:km)?", text)
    return float(match.group(1)) if match else None


def merged_chains(lines: Sequence[Any]) -> list[Any]:
    """The ways of a route merged into continuous lines, longest first."""

    from shapely.geometry import LineString, MultiLineString
    from shapely.ops import linemerge, unary_union

    pieces = [line for line in lines if line is not None and not line.is_empty]
    if not pieces:
        return []
    union = unary_union(pieces)
    if isinstance(union, LineString):
        return [union]
    merged = linemerge(union) if isinstance(union, MultiLineString) else union
    chains = [merged] if isinstance(merged, LineString) else list(merged.geoms)
    return sorted(chains, key=lambda chain: -chain.length)


@dataclass(frozen=True)
class Station:
    """A milestone on a route line: its OSM id, km, distance along the line and offset from it (metres)."""

    osm_id: str
    km: float
    s_m: float
    offset_m: float


def stations_on_line(line: Any, milestones: Sequence[tuple[str, float, Any]],
                     max_offset_m: float = MILESTONE_MAX_OFFSET_M) -> tuple[list[Station], list[dict[str, Any]]]:
    """Milestones ``(osm_id, km, point)`` projected onto ``line``: those within ``max_offset_m``, and the rest."""

    used, rejected = [], []
    for osm_id, km, point in milestones:
        offset = line.distance(point)
        if offset <= max_offset_m:
            used.append(Station(str(osm_id), float(km), line.project(point), offset))
        else:
            rejected.append({"osm_id": str(osm_id), "km": km, "offset_m": round(offset, 1),
                             "reason": f"more than {max_offset_m:g} m from the route line"})
    used.sort(key=lambda station: station.km)
    return used, rejected


def reverse_line(line: Any) -> Any:
    """``line`` with its vertices in the opposite order."""

    from shapely.geometry import LineString

    return LineString(list(line.coords)[::-1])


def orient_by_stations(line: Any, stations: Sequence[Station]) -> tuple[Any, list[Station], bool]:
    """Orient ``line`` so that distance along it grows with km; return the line, the re-projected stations, flipped.

    With one station the direction is fixed only by a km-0 milestone within :data:`END_MATCH_M` of an end; otherwise
    the line is returned unchanged and the caller must not extrapolate from it.
    """

    if len(stations) >= 2:
        first, last = stations[0], stations[-1]
        flip = last.s_m < first.s_m
    elif len(stations) == 1 and stations[0].km == 0.0:
        flip = line.length - stations[0].s_m <= END_MATCH_M < stations[0].s_m
    else:
        flip = False
    if not flip:
        return line, list(stations), False
    length = line.length
    flipped = [Station(st.osm_id, st.km, length - st.s_m, st.offset_m) for st in stations]
    return reverse_line(line), sorted(flipped, key=lambda station: station.km), True


def check_monotonic(stations: Sequence[Station]) -> None:
    """Raise :class:`PlacementError` unless distance along the line grows strictly with km."""

    for before, after in zip(stations, stations[1:]):
        if after.km == before.km:
            raise PlacementError(f"two milestones give km {after.km:g} ({before.osm_id}, {after.osm_id})")
        if after.s_m <= before.s_m:
            raise PlacementError(f"milestone km {after.km:g} ({after.osm_id}) does not lie beyond km {before.km:g} "
                                 f"({before.osm_id}) along the route")


def km_to_s(km: float, stations: Sequence[Station]) -> tuple[float, str]:
    """Distance along the oriented line (metres) of an official ``km``, and how it was obtained.

    Between two stations: linear interpolation (``interpolated``). Before the first or after the last station: one
    OSM metre per official metre from the nearest station (``extrapolated_before_first`` /
    ``extrapolated_after_last``). One station: the same unit scale (``unit_scale_from_single``).
    """

    if not stations:
        raise PlacementError("no milestone on the route")
    check_monotonic(stations)
    if len(stations) == 1:
        return stations[0].s_m + (km - stations[0].km) * 1000.0, "unit_scale_from_single"
    if km < stations[0].km:
        return stations[0].s_m - (stations[0].km - km) * 1000.0, "extrapolated_before_first"
    if km > stations[-1].km:
        return stations[-1].s_m + (km - stations[-1].km) * 1000.0, "extrapolated_after_last"
    for before, after in zip(stations, stations[1:]):
        if before.km <= km <= after.km:
            share = (km - before.km) / (after.km - before.km)
            return before.s_m + share * (after.s_m - before.s_m), "interpolated"
    raise PlacementError(f"km {km:g} not bracketed")  # pragma: no cover - the loop covers every km in range


def km_to_s_unit_from_nearest(km: float, stations: Sequence[Station]) -> tuple[float, Station]:
    """Distance along the line of ``km`` read at unit scale from the nearest milestone (a check, not the rule)."""

    nearest = min(stations, key=lambda station: (abs(station.km - km), station.km))
    return nearest.s_m + (km - nearest.km) * 1000.0, nearest


def segment_ratios(stations: Sequence[Station]) -> list[dict[str, Any]]:
    """Metres of OSM line per official metre between consecutive milestones."""

    return [{"from_km": before.km, "to_km": after.km, "line_m": round(after.s_m - before.s_m, 1),
             "osm_m_per_official_m": round((after.s_m - before.s_m) / ((after.km - before.km) * 1000.0), 4)}
            for before, after in zip(stations, stations[1:])]


def cut_part(line: Any, s_from: float, s_to: float) -> tuple[Any, dict[str, Any]]:
    """The part of ``line`` between two distances (a point when they are equal), clipped to the line."""

    from shapely.ops import substring

    length = line.length
    low, high = sorted((s_from, s_to))
    clipped = {"beyond_start_m": round(max(0.0, -low), 1), "beyond_end_m": round(max(0.0, high - length), 1)}
    low, high = min(max(low, 0.0), length), min(max(high, 0.0), length)
    if high - low < 1e-6:
        return line.interpolate(low), clipped
    return substring(line, low, high), clipped


def part_inside(lines: Sequence[Any], polygon: Any) -> Any:
    """The parts of ``lines`` inside ``polygon`` (line geometry only), merged; empty when the route misses it."""

    from shapely.geometry import GeometryCollection, LineString, MultiLineString
    from shapely.ops import linemerge, unary_union

    pieces = []
    for line in lines:
        inter = line.intersection(polygon)
        for geom in getattr(inter, "geoms", [inter]):
            if isinstance(geom, LineString) and geom.length > 0:
                pieces.append(geom)
            elif isinstance(geom, MultiLineString):
                pieces.extend(g for g in geom.geoms if g.length > 0)
    if not pieces:
        return GeometryCollection()
    union = unary_union(pieces)
    return linemerge(union) if isinstance(union, MultiLineString) else union


def lengths_by_unit(geometry: Any, units: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Length (metres) of a line geometry inside each unit it crosses; a point gives the unit that covers it."""

    out = []
    for unit in units:
        polygon = unit["geometry_m"]
        if geometry.geom_type == "Point":
            if polygon.covers(geometry):
                out.append({"adm3_pcode": unit["adm3_pcode"], "adm3_name": unit["adm3_name"], "length_m": 0.0})
            continue
        length = geometry.intersection(polygon).length
        if length > 0.5:
            out.append({"adm3_pcode": unit["adm3_pcode"], "adm3_name": unit["adm3_name"], "length_m": round(length, 1)})
    return sorted(out, key=lambda row: -row["length_m"])


def routing_point(geometry: Any, entrances: Sequence[tuple[str, str, Any]]) -> tuple[Any, str, list[str]]:
    """The routing point of an OSM facility by the SE2 rule (``floodguard.evidence_context._osm_facilities``).

    A node is its point. An area is its representative point, or its one tagged entrance node (``entrance`` not
    ``no``) on the boundary when it has exactly one. Coordinates are WGS84, as that builder reads them.
    """

    if geometry.geom_type == "Point":
        return geometry, "osm_facility_node", []
    on_boundary = sorted(osm_id for osm_id, tag, point in entrances
                         if tag not in (None, "", "no") and geometry.boundary.distance(point) <= 1e-8)
    if len(on_boundary) == 1:
        point = next(point for osm_id, tag, point in entrances if osm_id == on_boundary[0])
        return point, "osm_tagged_site_boundary_entrance_not_independently_verified", on_boundary
    return geometry.representative_point(), "derived_site_interior_representative_not_entrance", on_boundary


MAX_GAP_IN_RUN = timedelta(hours=6)
"""Readings without a value do not end a run above a level, unless the gap between two values is longer than this."""


def runs_above(values: Sequence[tuple[str, float]], level: float) -> list[list[str]]:
    """The runs ``[first, last]`` of readings above ``level``; a reading at or below it, or a long gap, ends a run."""

    runs: list[list[str]] = []
    open_run = False
    previous: datetime | None = None
    for stamp, value in values:
        moment = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
        if previous is not None and moment - previous > MAX_GAP_IN_RUN:
            open_run = False
        if value > level:
            if open_run:
                runs[-1][1] = stamp
            else:
                runs.append([stamp, stamp])
                open_run = True
        else:
            open_run = False
        previous = moment
    return runs


def gauge_summary(series: Sequence[tuple[str, float | None]], levels: Mapping[str, float],
                  gauge_zero_msl: float | None) -> dict[str, Any]:
    """Peak of a series ``(datetime_local, metres MSL or None)`` and when it stood above each named level.

    The peak is the highest value; the times at that value are given (the first and last and their number when there
    are more than six). For each level of ``levels`` (metres MSL): the readings above it, the first and last of them
    and the runs, where a reading with no value does not end a run.
    """

    values = sorted(((stamp, value) for stamp, value in series if value is not None and math.isfinite(value)),
                    key=lambda row: row[0])
    out: dict[str, Any] = {"readings_in_series": len(series), "readings_with_value": len(values)}
    if not values:
        return {**out, "peak_msl": None}
    peak = max(value for _, value in values)
    at_peak = [stamp for stamp, value in values if abs(value - peak) < 0.005]
    out.update({"peak_msl": round(peak, 2),
                "peak_times_local": at_peak if len(at_peak) <= 6 else [at_peak[0], at_peak[-1]],
                "readings_at_peak": len(at_peak),
                "peak_gauge_m": None if gauge_zero_msl is None else round(peak - gauge_zero_msl, 2)})
    above_levels = {}
    for name, level in levels.items():
        above = [stamp for stamp, value in values if value > level]
        above_levels[name] = {"level_msl": round(level, 2), "readings_above": len(above),
                              "first_above_local": above[0] if above else None,
                              "last_above_local": above[-1] if above else None,
                              "runs_above_local": runs_above(values, level),
                              "peak_minus_level_m": round(peak - level, 2)}
    out["levels"] = above_levels
    return out


def round_coords(geojson: Any, digits: int) -> Any:
    """A GeoJSON geometry mapping with every coordinate rounded."""

    def walk(value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            if value and all(isinstance(item, (int, float)) for item in value):
                return [round(float(item), digits) for item in value]
            return [walk(item) for item in value]
        return value

    return {**geojson, "coordinates": walk(geojson["coordinates"])}


def geometry_pair(geometry_m: Any, to_wgs84: Any) -> dict[str, Any]:
    """A geometry in EPSG:32647 (0.1 m) and in WGS84 (7 decimals), as GeoJSON mappings."""

    from shapely.geometry import mapping
    from shapely.ops import transform

    return {"epsg32647": round_coords(mapping(geometry_m), 1),
            "wgs84": round_coords(mapping(transform(to_wgs84, geometry_m)), 7)}


# ---------------------------------------------------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------------------------------------------------

def now_utc() -> str:
    """The time now, UTC, to the second."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    """The SHA-256 of a file's bytes."""

    digest = hashlib.sha256()
    with refuse_firewalled(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write JSON as UTF-8 with LF line ends, so the SHA-256 holds for the bytes Git stores."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(refuse_firewalled(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, indent=1, ensure_ascii=False) + "\n")


def read_json(path: Path) -> Any:
    """Read a JSON file after the firewall check."""

    return json.loads(refuse_firewalled(path).read_text(encoding="utf-8"))


def git_file(relative: str) -> dict[str, str]:
    """A file of the repository by path and SHA-256."""

    return {"path": relative, "sha256": sha256_file(ROOT / relative)}


class Log:
    """Lines of progress, printed and appended to the log of the work folder (LF line ends)."""

    def __init__(self, path: Path) -> None:
        self.path = refuse_firewalled(path)
        path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, text: str) -> None:
        line = f"{now_utc()} {text}"
        print(line, flush=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")


def envelope(source_timestamp: str, confidence_basis: str) -> dict[str, Any]:
    """The fields every record of the case carries."""

    return {
        "generated_at_utc": now_utc(),
        "source_timestamp": source_timestamp,
        "confidence_class": "low",
        "confidence_basis": confidence_basis,
        "assumptions": ASSUMPTIONS,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
    }


def recorded_sources() -> dict[str, dict[str, str]]:
    """The rows of the committed open-context source manifest, by source group."""

    with (ROOT / SOURCE_MANIFEST).open(encoding="utf-8-sig", newline="") as stream:
        return {row["source_group"]: row for row in csv.DictReader(stream)}


def frame_bbox_wgs84(grid: Mapping[str, Any], cell_m: float = 20.0) -> tuple[float, float, float, float]:
    """The WGS84 bounding box of a grid of ``outputs/nan_case/areas_v1.json`` (its four corners and edge midpoints)."""

    from pyproj import Transformer

    west, north = float(grid["west"]), float(grid["north"])
    east, south = west + grid["cols"] * cell_m, north - grid["rows"] * cell_m
    back = Transformer.from_crs(EPSG, 4326, always_xy=True)
    xs, ys = [], []
    for x in (west, (west + east) / 2, east):
        for y in (south, (south + north) / 2, north):
            lon, lat = back.transform(x, y)
            xs.append(lon)
            ys.append(lat)
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------------------------------------------------
# Stage: extract
# ---------------------------------------------------------------------------------------------------------------------

EXTRACT_LAYERS: tuple[tuple[str, str | None], ...] = (
    ("lines", "highway IS NOT NULL"),
    ("points", None),
    ("multipolygons", "amenity IS NOT NULL OR other_tags LIKE '%healthcare%'"),
)


def stage_extract(external: Path, log: Log) -> dict[str, Any]:
    """Read the OSM layers of the widened frame box with pyogrio into the work folder's GeoPackage."""

    import pyogrio

    pbf = refuse_firewalled(external / PBF)
    recorded = recorded_sources()["osm_geofabrik"]
    pbf_sha = sha256_file(pbf)
    if pbf_sha != recorded["sha256"]:
        raise BuildError(f"the OSM extract differs from {SOURCE_MANIFEST}")
    grid = read_json(ROOT / AREAS)["areas"]["nan_frame"]["grid"]
    west, south, east, north = frame_bbox_wgs84(grid)
    m = EXTRACT_MARGIN_DEG
    bbox = (round(west - m, 4), round(south - m, 4), round(east + m, 4), round(north + m, 4))
    work = external / WORK
    target = refuse_firewalled(work / EXTRACT_NAME)
    if target.exists():
        target.unlink()
    counts = {}
    for layer, where in EXTRACT_LAYERS:
        started = time.time()
        frame = pyogrio.read_dataframe(pbf, layer=layer, bbox=bbox, where=where)
        frame.to_file(target, layer=layer, driver="GPKG")
        counts[layer] = len(frame)
        log(f"extract: {layer}: {len(frame)} features in {time.time() - started:.0f} s")
    receipt = {
        "schema": "floodguard.nan_case_osm_extract.v1",
        "generated_at_utc": now_utc(),
        "pbf": {"path": f"<external>/{PBF.as_posix()}", "sha256": pbf_sha,
                "retrieved_at_utc": recorded["retrieved_at_utc"]},
        "frame_bbox_wgs84": [round(value, 6) for value in (west, south, east, north)],
        "extract_bbox_wgs84": list(bbox),
        "margin_deg": m,
        "layers": {layer: {"where": where, "features": counts[layer]} for layer, where in EXTRACT_LAYERS},
        "reader": {"pyogrio": pyogrio.__version__, "gdal": pyogrio.__gdal_version_string__},
        "gpkg_sha256": sha256_file(target),
    }
    write_json(work / EXTRACT_RECEIPT, receipt)
    return receipt


# ---------------------------------------------------------------------------------------------------------------------
# Stage: place
# ---------------------------------------------------------------------------------------------------------------------

def load_units(external: Path) -> tuple[list[dict[str, Any]], str]:
    """The COD-AB tha_admin3 units of Nan province in EPSG:32647, and the SHA-256 of the boundary file."""

    import pyogrio
    from pyproj import Transformer
    from shapely.ops import transform

    boundaries = refuse_firewalled(external / BOUNDARIES)
    sha = sha256_file(boundaries)
    if sha != recorded_sources()["hdx_cod_ab"]["sha256"]:
        raise BuildError(f"the boundary file differs from {SOURCE_MANIFEST}")
    frame = pyogrio.read_dataframe(boundaries, layer="tha_admin3",
                                   columns=["adm3_pcode", "adm3_name", "adm3_name1", "adm2_pcode", "adm2_name", "adm1_pcode", "valid_on"],
                                   where=f"adm1_pcode = '{PROVINCE}'")
    if len(frame) == 0:
        raise BuildError(f"COD-AB tha_admin3 has no unit of {PROVINCE}")
    forward = Transformer.from_crs(4326, EPSG, always_xy=True).transform
    units = [{"adm3_pcode": str(row["adm3_pcode"]), "adm3_name": str(row["adm3_name"]),
              "adm3_name_th": str(row["adm3_name1"]), "adm2_pcode": str(row["adm2_pcode"]),
              "adm2_name": str(row["adm2_name"]), "valid_on": str(row["valid_on"])[:10],
              "geometry_m": transform(forward, row["geometry"])} for _, row in frame.iterrows()]
    return sorted(units, key=lambda unit: unit["adm3_pcode"]), sha


def load_extract(external: Path) -> dict[str, Any]:
    """The cached OSM layers, after checking the receipt against the GeoPackage and the recorded PBF."""

    import pyogrio

    work = external / WORK
    receipt = read_json(work / EXTRACT_RECEIPT)
    target = refuse_firewalled(work / EXTRACT_NAME)
    if sha256_file(target) != receipt["gpkg_sha256"]:
        raise BuildError(f"{EXTRACT_NAME} is not the extract its receipt records; run --stage extract")
    if receipt["pbf"]["sha256"] != recorded_sources()["osm_geofabrik"]["sha256"]:
        raise BuildError("the extract was read from another OSM file than the recorded one")
    layers = {layer: pyogrio.read_dataframe(target, layer=layer) for layer, _ in EXTRACT_LAYERS}
    return {"receipt": receipt, **layers}


def _route_ways(lines: Any, route: Route, province_m: Any, forward: Any) -> list[dict[str, Any]]:
    from shapely.ops import transform

    ways = []
    for _, row in lines.iterrows():
        tags = parse_other_tags(row["other_tags"])
        candidates = [tags.get("ref"), tags.get("official_ref")]
        if not any(route.number in ref for c in candidates for ref in normalise_ref(c)):
            continue
        geometry_m = transform(forward, row["geometry"])
        touches = geometry_m.intersects(province_m)
        how = next((m for m in (ref_matches(c, route, touches_province=touches) for c in candidates) if m), None)
        if how is None:
            continue
        ways.append({"osm_id": str(row["osm_id"]), "how": how, "ref": tags.get("ref"), "highway": row["highway"],
                     "name": row["name"] if isinstance(row["name"], str) else None, "bridge": tags.get("bridge"),
                     "geometry_m": geometry_m})
    return ways


def _named_route_ways(lines: Any, route: Route) -> list[str]:
    """OSM ways whose name names the route (``นน.021``, ``ทางหลวงชนบท ... 021``): ids only, for the record."""

    pattern = re.compile(rf"(?<![0-9]){re.escape(route.number)}(?![0-9])")
    found = []
    for _, row in lines.iterrows():
        tags = parse_other_tags(row["other_tags"])
        for key in ("name", "name:th", "name:en", "alt_name", "old_name"):
            value = row["name"] if key == "name" else tags.get(key)
            if isinstance(value, str) and pattern.search(value) and (route.prefix is None or route.prefix in value
                                                                      or "Nan" in value or "ทางหลวง" in value):
                found.append(str(row["osm_id"]))
                break
    return found


def refs_inside(lines: Any, polygon_m: Any, forward: Any) -> dict[str, int]:
    """The ``ref`` values of the highway ways that enter ``polygon_m``, with how many ways carry each."""

    from shapely.ops import transform

    counts: dict[str, int] = {}
    for _, row in lines.iterrows():
        ref = parse_other_tags(row["other_tags"]).get("ref")
        if ref and transform(forward, row["geometry"]).intersects(polygon_m):
            counts[ref] = counts.get(ref, 0) + 1
    return dict(sorted(counts.items()))


def _milestones(points: Any, route: Route, forward: Any) -> list[tuple[str, float, Any]]:
    from shapely.ops import transform

    out = []
    for _, row in points.iterrows():
        if row["highway"] != "milestone":
            continue
        tags = parse_other_tags(row["other_tags"])
        if ref_matches(row["ref"] if isinstance(row["ref"], str) else tags.get("ref"), route, touches_province=True) is None:
            continue
        km = parse_km(tags.get("distance"))
        if km is None:
            continue
        out.append((str(row["osm_id"]), km, transform(forward, row["geometry"])))
    return out


def _fmt_km(km: float) -> str:
    whole = int(math.floor(km + 1e-9))
    return f"{whole}+{round((km - whole) * 1000):03d}"


def place_cut(cut: Cut, lines: Any, points: Any, units: Sequence[Mapping[str, Any]], province_m: Any,
              forward: Any, backward: Any) -> dict[str, Any]:
    """Place one cut by the protocol rule and return its entry for the record."""

    from shapely.geometry import Point
    from shapely.ops import unary_union

    unit_by_code = {unit["adm3_pcode"]: unit for unit in units}
    named = unit_by_code[cut.tambon_pcode]
    entry: dict[str, Any] = {
        "id": cut.id,
        "in_protocol_list": cut.in_protocol_list,
        "entry_as_listed_th": cut.entry_th,
        "authority": cut.route.authority,
        "route": f"{cut.route.prefix}.{cut.route.number}" if cut.route.prefix else cut.route.number,
        "km_from": cut.km_from,
        "km_to": cut.km_to,
        "km_as_listed": _fmt_km(cut.km_from) if cut.km_from == cut.km_to else f"{_fmt_km(cut.km_from)} to {_fmt_km(cut.km_to)}",
        "tambon_as_listed_th": cut.tambon_as_written_th,
        "tambon_cod_ab": {"adm3_pcode": named["adm3_pcode"], "adm3_name": named["adm3_name"],
                          "adm3_name_th": named["adm3_name_th"], "adm2_name": named["adm2_name"]},
        "note": cut.note or None,
        "ref_forms_tried": ([cut.route.number, f"ทล.{cut.route.number}"] if cut.route.prefix is None else
                            [f"{cut.route.prefix}.{cut.route.number}", f"{cut.route.prefix}. {cut.route.number}",
                             f"{cut.route.prefix} {cut.route.number}", f"{cut.route.number} (only on ways that touch Nan province)"]),
        "test_3b_buffer_m": TEST_3B_BUFFER_M,
    }
    ways = _route_ways(lines, cut.route, province_m, forward)
    if not ways:
        entry.update({
            "status": "route_not_found",
            "method": None,
            "placed": None,
            "way_ids": [],
            "ways_whose_name_carries_the_number": _named_route_ways(lines, cut.route),
            "refs_on_ways_in_named_tambon": refs_inside(lines, named["geometry_m"], forward),
            "certainty": f"Not placed: no OSM way in the extract carries the reference {entry['route']} in any of the "
                         f"forms tried, and no way's name carries the route number with the province prefix, so the "
                         f"cut has no position.",
            "placement_confidence": None,
        })
        return entry
    chains = merged_chains([way["geometry_m"] for way in ways])
    milestones = _milestones(points, cut.route, forward)
    main = chains[0]
    stations, rejected = stations_on_line(main, milestones)
    main, stations, flipped = orient_by_stations(main, stations)
    entry["route_ways"] = sorted(way["osm_id"] for way in ways)
    entry["route_ways_bare_number"] = sorted(way["osm_id"] for way in ways if way["how"] == "bare")
    entry["route_line"] = {"chains": len(chains), "main_chain_length_m": round(main.length, 1),
                           "other_chain_lengths_m": [round(chain.length, 1) for chain in chains[1:]],
                           "start_tambon": _unit_at(Point(main.coords[0]), units) or "outside Nan province",
                           "end_tambon": _unit_at(Point(main.coords[-1]), units) or "outside Nan province",
                           "oriented_by_milestones": bool(stations), "reversed": flipped}
    entry["milestones_used"] = [{"osm_id": st.osm_id, "km": st.km, "s_m": round(st.s_m, 1),
                                 "offset_m": round(st.offset_m, 1), "tambon": _unit_at(main.interpolate(st.s_m), units)}
                                for st in stations]
    entry["milestones_rejected"] = rejected
    usable = len(stations) >= 2 or (len(stations) == 1 and stations[0].km == 0.0 and stations[0].s_m <= END_MATCH_M)
    if usable:
        s_from, how_from = km_to_s(cut.km_from, stations)
        s_to, how_to = km_to_s(cut.km_to, stations)
        geometry, clipped = cut_part(main, s_from, s_to)
        method = "milestones"
        entry["chainage"] = {"s_from_m": round(s_from, 1), "s_to_m": round(s_to, 1), "how_from": how_from,
                             "how_to": how_to, "clipped": clipped, "ratios": segment_ratios(stations)}
        alt_from, near_from = km_to_s_unit_from_nearest(cut.km_from, stations)
        alt_to, near_to = km_to_s_unit_from_nearest(cut.km_to, stations)
        alt_geometry, _ = cut_part(main, alt_from, alt_to)
        nearest_text = (f"km {near_from.km:g}" if near_from.km == near_to.km
                        else f"km {near_from.km:g} and km {near_to.km:g}")
        entry["check_unit_scale_from_nearest_milestone"] = {
            "what": "Report only: the same km read at one OSM metre per official metre from the nearest milestone "
                    f"({nearest_text}).",
            "s_from_m": round(alt_from, 1), "s_to_m": round(alt_to, 1),
            "shift_from_placed_m": round(((alt_from - s_from) + (alt_to - s_to)) / 2.0, 1),
            "tambons": lengths_by_unit(alt_geometry, units),
            "geometry": geometry_pair(alt_geometry, backward),
        }
        tambon_part = part_inside([main], named["geometry_m"])
        if not tambon_part.is_empty:
            low = min(main.project(Point(c)) for g in getattr(tambon_part, "geoms", [tambon_part]) for c in g.coords)
            high = max(main.project(Point(c)) for g in getattr(tambon_part, "geoms", [tambon_part]) for c in g.coords)
            low_near = min(stations, key=lambda st: abs(st.s_m - low))
            high_near = min(stations, key=lambda st: abs(st.s_m - high))
            entry["check_named_tambon_along_the_line"] = {
                "what": "Report only: where the route line runs through the tambon the list names, as km by the rule "
                        "and as km read at unit scale from the nearest milestone.",
                "s_from_m": round(low, 1), "s_to_m": round(high, 1), "length_m": round(tambon_part.length, 1),
                "km_by_the_rule_from": round(_s_to_km(low, stations), 3),
                "km_by_the_rule_to": round(_s_to_km(high, stations), 3),
                "km_by_unit_scale_from_nearest_from": round(low_near.km + (low - low_near.s_m) / 1000.0, 3),
                "km_by_unit_scale_from_nearest_to": round(high_near.km + (high - high_near.s_m) / 1000.0, 3),
            }
    else:
        geometry = part_inside([chain for chain in chains], named["geometry_m"])
        method = "tambon_part"
        if geometry.is_empty:
            entry.update({"status": "route_misses_named_tambon", "method": method, "placed": None,
                          "way_ids": [], "placement_confidence": None,
                          "certainty": "Not placed: the route has no mapped milestone and its OSM ways do not enter "
                                       "the tambon the list names."})
            return entry
    carried = sorted({way["osm_id"] for way in ways
                      if way["geometry_m"].buffer(WAY_CARRIES_M).intersection(geometry).length > WAY_CARRIES_M
                      or (geometry.geom_type == "Point" and way["geometry_m"].distance(geometry) <= WAY_CARRIES_M)})
    parallel = sorted({way["osm_id"] for way in ways if way["osm_id"] not in carried
                       and way["geometry_m"].distance(geometry) <= 30.0})
    tambons = lengths_by_unit(geometry, units)
    inside = named["geometry_m"].buffer(0.5).covers(geometry)
    entry.update({
        "status": "placed",
        "method": method,
        "way_ids": carried,
        "parallel_route_way_ids_within_30_m": parallel,
        "placed": {**geometry_pair(geometry, backward), "geometry_type": geometry.geom_type,
                   "length_m": round(geometry.length, 1)},
        "tambons_of_placed_part": tambons,
        "inside_named_tambon": inside,
        "distance_to_named_tambon_m": round(geometry.distance(named["geometry_m"]), 1),
        "share_inside_named_tambon": (None if geometry.geom_type == "Point" or geometry.length == 0 else
                                      round(geometry.intersection(named["geometry_m"]).length / geometry.length, 3)),
    })
    return entry


def _s_to_km(s_m: float, stations: Sequence[Station]) -> float:
    """The official km at a distance along the line, by the same rule as :func:`km_to_s` (inverse)."""

    if len(stations) == 1:
        return stations[0].km + (s_m - stations[0].s_m) / 1000.0
    if s_m < stations[0].s_m:
        return stations[0].km - (stations[0].s_m - s_m) / 1000.0
    if s_m > stations[-1].s_m:
        return stations[-1].km + (s_m - stations[-1].s_m) / 1000.0
    for before, after in zip(stations, stations[1:]):
        if before.s_m <= s_m <= after.s_m:
            return before.km + (s_m - before.s_m) / (after.s_m - before.s_m) * (after.km - before.km)
    raise PlacementError("distance not bracketed")  # pragma: no cover


def _unit_at(point: Any, units: Sequence[Mapping[str, Any]]) -> str | None:
    for unit in units:
        if unit["geometry_m"].covers(point):
            return f"{unit['adm3_pcode']} {unit['adm3_name']}"
    return None


CHAINAGE_PROBES_1243: tuple[tuple[float, str | None, str], ...] = (
    (34.036, "TH550402", "list of 31 July 2025: km 34+036 (start of a range) in Chiang Khong, Na Noi"),
    (59.1, "TH550707", "list of 31 July 2025: km 59+100 in Nam Muap (written น้ำม่วน), Wiang Sa"),
    (58.875, None, "list of 1 August 2025: km 58+875 to 58+900 in Wiang Sa, a washed-out bridge approach"),
)


def along_line_gap(line: Any, s_m: float, polygon: Any) -> float | None:
    """Distance along ``line`` from ``s_m`` to the stretch of the line inside ``polygon`` (0 inside, None if missed)."""

    from shapely.geometry import Point

    part = line.intersection(polygon)
    if part.is_empty or part.length == 0:
        return None
    ends = [line.project(Point(c)) for g in getattr(part, "geoms", [part]) if g.length > 0 for c in g.coords]
    low, high = min(ends), max(ends)
    return 0.0 if low <= s_m <= high else min(abs(s_m - low), abs(s_m - high))


def chainage_check_1243(lines: Any, units: Sequence[Mapping[str, Any]], forward: Any, backward: Any) -> dict[str, Any]:
    """Report only: route 1243 read as km from either end of its merged OSM line, against the lists' tambon names.

    With no milestone mapped, the end the km run from is judged by which reading puts the listed km into the listed
    tambons; the bridges of the route are given with their km from the southern end.
    """

    from shapely.geometry import Point
    from shapely.ops import transform

    route = Route("1243", None, DOH)
    ways = []
    for _, row in lines.iterrows():
        tags = parse_other_tags(row["other_tags"])
        if ref_matches(tags.get("ref"), route, touches_province=True):
            ways.append({"osm_id": str(row["osm_id"]), "bridge": tags.get("bridge"),
                         "geometry_m": transform(forward, row["geometry"])})
    chains = merged_chains([way["geometry_m"] for way in ways])
    line = chains[0]
    if line.coords[0][1] > line.coords[-1][1]:
        line = reverse_line(line)  # distance along the line now runs from the southern end
    length = line.length
    polygons = {unit["adm3_pcode"]: unit["geometry_m"] for unit in units}
    readings: dict[str, Any] = {}
    gaps: dict[str, float] = {}
    for origin in ("southern_end", "northern_end"):
        rows = []
        total = 0.0
        for km, pcode, what in CHAINAGE_PROBES_1243:
            s = km * 1000.0 if origin == "southern_end" else length - km * 1000.0
            row: dict[str, Any] = {"km": km, "what": what,
                                   "tambon_at_reading": _unit_at(line.interpolate(s), units) or "outside Nan province"}
            if pcode is not None:
                gap = along_line_gap(line, s, polygons[pcode])
                row["along_line_to_listed_tambon_m"] = None if gap is None else round(gap, 1)
                total += math.inf if gap is None else gap
            rows.append(row)
        readings[origin] = rows
        gaps[origin] = total
    bridges = []
    for way in ways:
        if way.get("bridge") in (None, "no"):
            continue
        ends = [line.project(Point(c)) for c in way["geometry_m"].coords]
        bridges.append({"osm_id": way["osm_id"], "length_m": round(way["geometry_m"].length, 1),
                        "km_from_southern_end": [round(min(ends) / 1000, 3), round(max(ends) / 1000, 3)],
                        "tambon": _unit_at(way["geometry_m"].interpolate(0.5, normalized=True), units)
                        or "outside Nan province"})
    bridges.sort(key=lambda row: row["km_from_southern_end"][0])
    nearest = min(bridges, key=lambda row: abs(row["km_from_southern_end"][0] - 58.875)) if bridges else None
    point = line.interpolate(59100.0)
    consistent = min(gaps, key=lambda key: gaps[key])
    return {
        "what": "Report only, not the placement: route 1243 has no milestone in OSM, so the protocol places its cut "
                "as the part of the route inside the named tambon. This check reads the OSM line length as km from "
                "either end and asks which reading puts the listed km into the listed tambons.",
        "route_ways": sorted(way["osm_id"] for way in ways),
        "merged_length_m": round(length, 1),
        "chains": len(chains),
        "southern_end_tambon": _unit_at(Point(line.coords[0]), units) or "outside Nan province",
        "northern_end_tambon": _unit_at(Point(line.coords[-1]), units) or "outside Nan province",
        "readings": readings,
        "sum_of_gaps_to_listed_tambons_m": {key: (None if math.isinf(value) else round(value, 1))
                                            for key, value in gaps.items()},
        "reading_consistent_with_the_lists": consistent,
        "bridges_on_route": bridges,
        "bridge_nearest_km_58_875_from_southern_end": nearest,
        "km_59_100_from_southern_end": {**geometry_pair(point, backward),
                                        "tambon": _unit_at(point, units) or "outside Nan province"},
        "caution": "OSM length and official km can differ by a few per cent (on Nan 4020 the first 13 km are 2.2 km "
                   "short in OSM), so a reading from an end is good to a few km at best.",
    }


def _hospital_objects(layers: Mapping[str, Any], forward: Any) -> list[dict[str, Any]]:
    from shapely.ops import transform

    objects = []
    for layer in ("points", "multipolygons"):
        for _, row in layers[layer].iterrows():
            tags = parse_other_tags(row["other_tags"])
            for key in ("name", "amenity", "building"):
                if key in row.index and isinstance(row[key], str):
                    tags.setdefault(key, row[key])
            if layer == "multipolygons":
                kind, osm_id = ("way", row["osm_way_id"]) if isinstance(row["osm_way_id"], str) and row["osm_way_id"] else ("relation", row["osm_id"])
            else:
                kind, osm_id = "node", row["osm_id"]
            objects.append({"kind": kind, "osm_id": str(osm_id), "tags": tags, "geometry": row["geometry"],
                            "geometry_m": transform(forward, row["geometry"])})
    return objects


def _entrances(points: Any) -> list[tuple[str, str, Any]]:
    out = []
    for _, row in points.iterrows():
        tags = parse_other_tags(row["other_tags"])
        if tags.get("entrance") not in (None, "no"):
            out.append((str(row["osm_id"]), tags["entrance"], row["geometry"]))
    return out


def locate_hospitals(layers: Mapping[str, Any], units: Sequence[Mapping[str, Any]], routing_m: Any, forward: Any,
                     backward: Any) -> list[dict[str, Any]]:
    """Nan Hospital and Wiang Sa Hospital from OSM: the hospital-tagged object with the Thai name, and the others."""

    from shapely.geometry import mapping
    from shapely.ops import transform

    objects = _hospital_objects(layers, forward)
    entrances = _entrances(layers["points"])
    out = []
    for spec in HOSPITALS:
        def named(obj: Mapping[str, Any]) -> bool:
            tags = obj["tags"]
            thai = {tags.get("name"), tags.get("name:th")}
            english = " ".join(str(tags.get(k, "")) for k in ("name", "name:en")).lower()
            return bool(thai & set(spec["names"])) or any(word in english for word in spec["english"])

        def hospital(obj: Mapping[str, Any]) -> bool:
            return "hospital" in {obj["tags"].get("amenity"), obj["tags"].get("healthcare")}

        candidates = [obj for obj in objects if named(obj)]
        chosen = [obj for obj in candidates if hospital(obj) and ({obj["tags"].get("name"), obj["tags"].get("name:th")}
                                                                  & set(spec["names"]))]
        entry: dict[str, Any] = {"id": spec["id"], "name_th": spec["name_th"]}
        if len(chosen) != 1:
            entry.update({"status": "not_located" if not chosen else "ambiguous",
                          "candidates": [f"{obj['kind']}/{obj['osm_id']}" for obj in chosen]})
            out.append(entry)
            continue
        obj = chosen[0]
        point, role, on_boundary = routing_point(obj["geometry"], entrances)
        point_m = transform(forward, point)
        polygon = obj["geometry"] if obj["geometry"].geom_type != "Point" else None
        entry.update({
            "status": "located",
            "osm": {"type": obj["kind"], "id": obj["osm_id"], "url": f"https://www.openstreetmap.org/{obj['kind']}/{obj['osm_id']}"},
            "tags": {key: obj["tags"][key] for key in HOSPITAL_TAGS if key in obj["tags"]},
            "routing_point": {"rule": "SE2 rule of protocol v1b: a node is its point; an area is its representative "
                                      "point, or its one tagged entrance node on the boundary.",
                              "role": role, "entrances_on_boundary": on_boundary,
                              **geometry_pair(point_m, backward)},
            "polygon": None if polygon is None else {
                "wgs84": round_coords(mapping(polygon), 7),
                "area_m2": round(obj["geometry_m"].area, 1)},
            "tambon_of_routing_point": _unit_at(point_m, units),
            "inside_se2_routing_geometry": bool(routing_m.covers(point_m)),
            "in_se2_hospital_list": bool(routing_m.covers(point_m)) and hospital(obj),
            "other_osm_objects_with_the_name": [
                {"osm": f"{other['kind']}/{other['osm_id']}",
                 "tags": {key: other["tags"][key] for key in HOSPITAL_TAGS if key in other["tags"]},
                 "distance_m": round(other["geometry_m"].distance(obj["geometry_m"]), 1),
                 "area_m2": round(other["geometry_m"].area, 1)}
                for other in candidates if other is not obj],
        })
        out.append(entry)
    return out


HOSPITAL_NOTES = {
    "nan_hospital": "Identified as OSM way 315323384: tagged amenity=hospital, name:th โรงพยาบาลน่าน, the address 1 "
                    "Worawichai, emergency=yes, operator Ministry of Public Health and Wikidata Q18118091, whose "
                    "coordinates (about 18.795 N, 100.789 E) fall on the site. Two other OSM objects carry the name: a "
                    "small building in the town centre tagged as a clinic, and a building inside the army hospital "
                    "(Fort Suriyaphong) whose English name tag reads 'Nan Hospital'; neither is taken. The site is "
                    "about 7.6 ha, so a 200 m test from the routing point and from the site edge give different areas; "
                    "both are given here and the test stage must say which it uses.",
    "wiang_sa_hospital": "Identified as OSM way 315331634: tagged amenity=hospital, name โรงพยาบาลอำเภอเวียงสา, "
                         "name:en Wiangsa Hospital, emergency=yes, beside highway 101 (Yantarakitkoson Road).",
}


def stage_place(external: Path, arguments: argparse.Namespace, log: Log) -> dict[str, Any]:
    """Place the cuts and the hospitals and write the record of positions."""

    from pyproj import Transformer
    from shapely.ops import unary_union

    if (ROOT / FREEZE).exists() and not arguments.replace:
        raise BuildError("the method of the case is frozen; the positions are not re-placed after the freeze")
    record_path = ROOT / POINTS_RECORD
    if record_path.exists() and not arguments.replace:
        raise BuildError(f"{POINTS_RECORD} exists; use --replace with --reason")
    if arguments.replace and not arguments.reason:
        raise BuildError("--replace needs --reason")
    forward = Transformer.from_crs(4326, EPSG, always_xy=True).transform
    backward = Transformer.from_crs(EPSG, 4326, always_xy=True).transform
    layers = load_extract(external)
    units, boundary_sha = load_units(external)
    frame_units = [unit for unit in units if unit["adm2_pcode"] in FRAME_DISTRICTS]
    if len(frame_units) != FRAME_UNITS:
        raise BuildError(f"the frame has {len(frame_units)} units in COD-AB, not {FRAME_UNITS}")
    province_m = unary_union([unit["geometry_m"] for unit in units])
    routing_m = unary_union([unit["geometry_m"] for unit in frame_units]).buffer(ROUTING_BUFFER_M, quad_segs=BUFFER_QUAD_SEGS)

    cuts = []
    for cut in CUTS + SUPPLEMENTARY_CUTS:
        entry = place_cut(cut, layers["lines"], layers["points"], units, province_m, forward, backward)
        entry["certainty"] = entry.get("certainty") or certainty_sentence(entry)
        entry["placement_confidence"] = entry.get("placement_confidence", placement_confidence(entry))
        if cut.id == "cut_1243_km59_100":
            entry["check_chainage_from_either_end"] = chainage_check_1243(layers["lines"], units, forward, backward)
        if cut.id == "cut_nan021_km0_000":
            entry["lead_for_a_person_to_check"] = NAN021_LEAD
        cuts.append(entry)
        log(f"place: {cut.id}: {entry['status']} ({entry.get('method')}), ways {entry.get('way_ids')}")
    hospitals = locate_hospitals(layers, units, routing_m, forward, backward)
    for hospital in hospitals:
        hospital["identification"] = HOSPITAL_NOTES.get(hospital["id"])
        log(f"place: {hospital['id']}: {hospital['status']} {hospital.get('osm', {}).get('id')}")

    receipt = layers["receipt"]
    protocol_cuts = [entry for entry in cuts if entry["in_protocol_list"]]
    record = {
        "schema": "floodguard.nan_case_consequence_points.v1",
        "case_id": "N1",
        **envelope("Ministry of Transport list of 2025-07-31 (cumulative 1 to 31 July 2025, as published by The "
                   f"Bangkok Insight); OpenStreetMap extract retrieved {receipt['pbf']['retrieved_at_utc']}; COD-AB "
                   f"boundaries valid on {units[0]['valid_on']}",
                   "Positions from OpenStreetMap ways, milestones and COD-AB tambons, none checked on the ground; one "
                   "of the four routes is not in OSM and one is placed only to a 29 km stretch."),
        "what_this_is": "The positions of the reported road cuts and of the two hospitals of the Nan case, placed "
                        "before any flag of the frame is computed (test 3b and test 4 of the protocol). Positions "
                        "only: nothing here is set against radar, a flood map or a reference layer.",
        "attribution": "Road, milestone and hospital positions © OpenStreetMap contributors, available under the Open "
                       "Database Licence 1.0 (ODbL); tambon boundaries: HDX Thailand COD-AB (OCHA, RTSD).",
        "protocol": git_file(PROTOCOL),
        "plan": git_file(PLAN),
        "areas": git_file(AREAS),
        "inputs": {
            "osm_extract": {"path": f"<external>/{PBF.as_posix()}", "sha256": receipt["pbf"]["sha256"],
                            "retrieved_at_utc": receipt["pbf"]["retrieved_at_utc"], "licence": "ODbL-1.0",
                            "read_with": receipt["reader"], "extract_bbox_wgs84": receipt["extract_bbox_wgs84"],
                            "frame_bbox_wgs84": receipt["frame_bbox_wgs84"],
                            "work_folder_extract": {"name": EXTRACT_NAME, "sha256": receipt["gpkg_sha256"],
                                                    "layers": receipt["layers"]}},
            "boundaries": {"path": f"<external>/{BOUNDARIES.as_posix()}", "sha256": boundary_sha,
                           "layer": "tha_admin3", "valid_on": units[0]["valid_on"]},
            "ministry_list": MINISTRY_LIST,
        },
        "rules": {
            "placement": "Protocol test 3b: each point placed on the OpenStreetMap way with that route reference, by "
                         "milestone nodes where they exist, otherwise as the part of the route inside the named tambon.",
            "milestones": f"highway=milestone nodes whose ref names the route and whose distance tag gives a km, within "
                          f"{MILESTONE_MAX_OFFSET_M:g} m of the merged route line, moved onto it. Two or more: the "
                          "official km is interpolated linearly between the bracketing milestones and read at one OSM "
                          "metre per official metre beyond the first or last. One milestone at km 0 within "
                          f"{END_MATCH_M:g} m of a route end: one OSM metre per official metre from it.",
            "route_line": "The OSM ways that carry the route reference, merged; the longest merged line is the route "
                          "line. A rural road's bare number counts only on ways that touch Nan province.",
            "not_found": "A route with no OSM way carrying its reference is recorded as not found and gets no position.",
            "test_3b_buffer_m": TEST_3B_BUFFER_M,
            "hospital_routing_point": "SE2 rule of protocol v1b (floodguard.evidence_context._osm_facilities).",
            "se2_routing_geometry": f"the union of the {FRAME_UNITS} frame units buffered by {ROUTING_BUFFER_M:g} m in "
                                    f"EPSG:{EPSG} ({BUFFER_QUAD_SEGS} segments per quarter circle)",
        },
        "reported_cuts": [entry for entry in cuts if entry["in_protocol_list"]],
        "supplementary_cuts": [entry for entry in cuts if not entry["in_protocol_list"]],
        "hospitals": hospitals,
        "summary": {
            "protocol_points": len(protocol_cuts),
            "placed": [entry["id"] for entry in protocol_cuts if entry["status"] == "placed"],
            "not_placed": [entry["id"] for entry in protocol_cuts if entry["status"] != "placed"],
            "by_method": {method: [entry["id"] for entry in protocol_cuts if entry.get("method") == method]
                          for method in ("milestones", "tambon_part")},
            "note": "Test 3b counts the share of the four listed points found; a point with no position cannot be "
                    "found, and the test stage must say how it is counted.",
            "notes_for_the_test_stage": [
                "Highway 1243 km 59+100 is placed by the protocol's tambon rule as the whole stretch of the route in "
                "Nam Muap (about 29.5 km), so its 300 m buffer takes in every edge of that stretch. Report only: "
                "reading the OSM line from its southern end puts km 59+100 in Nam Muap and the only bridge of the "
                "route inside Nam Muap (way 314512631) at km 58.49 to 58.52, 0.36 km from the washed-out bridge approach "
                "of the 1 August list (km 58+875 to 58+900).",
                "Nan 4020 km 10+500 to 10+900 is placed by milestones in Kong Khwai (Mueang Nan), about 0.5 km beyond "
                "the road's stretch in Na Pang, which the list names; within 300 m of the placed part lies part of "
                "the unit-scale reading, not the Na Pang stretch.",
                "Nan 021 has no position. The Department of Rural Roads list of 26 July 2025 gives it, both "
                "stretches of Nan 4020 and Nan 3019 as impassable that day.",
            ],
        },
        "order_rule": "Written before any flag of the Nan frame is computed and before the freeze; the stage refuses to "
                      "re-place after the freeze. The coordinator commits this file before the test stage runs.",
        "firewall": "This lane opened no radar, flood map or reference layer: not the sealed JAXA folder, not any GFM "
                    "file, not the THEOS-2 files of 31 July 2025 nor anything derived from them. Every path was "
                    "checked against that list before it was opened.",
        "code": git_file(SCRIPT),
        "limits": LIMITS,
        "supersedes": None,
    }
    if record_path.exists():
        old = json.loads(record_path.read_text(encoding="utf-8"))
        record["supersedes"] = {
            "reason": arguments.reason,
            "generated_at_utc": old.get("generated_at_utc"),
            "canonical_json_sha256": hashlib.sha256(json.dumps(old, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
            "positions_same": {entry["id"]: (next((o.get("placed") for o in old.get("reported_cuts", []) + old.get("supplementary_cuts", [])
                                                   if o["id"] == entry["id"]), None) == entry.get("placed"))
                               for entry in cuts},
        }
    write_json(record_path, record)
    log(f"place: wrote {POINTS_RECORD} sha256 {sha256_file(record_path)}")
    return record


NAN021_LEAD = (
    "Not a placement. The Department of Rural Roads list of 26 July 2025 (and its list of 20 August 2026, another "
    "flood) names Nan 021 the approach road of the bridge 'หัวเวียงเหนือ – น้ำต้วนพัฒนา' in Phu Phiang. In the OSM "
    "extract a node named วัดหัวเวียงเหนือ (node 6937697412) and a village node บ้านน้ำต้วน (node 2686080665) lie in "
    "Fai Kaeo about 650 m apart, and one unnamed, untagged bridge way (way 356007707, 143 m) crosses the Nan River "
    "between them. A person who checks the bridge on the ground or on imagery may tag it; until then the point has "
    "no position and takes part in test 3b only as not found."
)


def certainty_sentence(entry: Mapping[str, Any]) -> str:
    """One sentence on how certain a placement is, from the figures of its entry."""

    if entry["status"] != "placed":
        return entry.get("certainty") or "Not placed."
    tambon = entry["tambon_cod_ab"]["adm3_name"]
    if entry["method"] == "tambon_part":
        return (f"Route {entry['route']} has no mapped milestone, so by the protocol rule the cut is the "
                f"{entry['placed']['length_m'] / 1000:.1f} km of the route inside {tambon}; where along that stretch "
                f"the cut lies is not known from OSM (see the report-only chainage check).")
    chain = entry["chainage"]
    hows = {chain["how_from"], chain["how_to"]}
    inside = entry["inside_named_tambon"]
    share = entry.get("share_inside_named_tambon")
    shift = entry["check_unit_scale_from_nearest_milestone"]["shift_from_placed_m"]
    used = entry["milestones_used"]
    if hows == {"interpolated"}:
        before = max((m for m in used if m["km"] <= entry["km_from"]), key=lambda m: m["km"])
        after = min((m for m in used if m["km"] >= entry["km_to"]), key=lambda m: m["km"])
        ratio = (after["s_m"] - before["s_m"]) / ((after["km"] - before["km"]) * 1000.0)
        basis = (f"interpolated between the milestones of km {before['km']:g} and km {after['km']:g}, which lie "
                 f"{(after['s_m'] - before['s_m']) / 1000:.2f} km apart along the OSM line "
                 f"({ratio:.2f} OSM metre per official metre)")
    elif "extrapolated_after_last" in hows:
        last = used[-1]
        basis = (f"read {entry['km_from'] - last['km']:.2f} to {entry['km_to'] - last['km']:.2f} km beyond the last "
                 f"mapped milestone (km {last['km']:g}) at one OSM metre per official metre")
        if len(used) >= 2:
            before = used[-2]
            ratio = (last["s_m"] - before["s_m"]) / ((last["km"] - before["km"]) * 1000.0)
            basis += (f", where the last milestone spacing (km {before['km']:g} to {last['km']:g}) matches the OSM "
                      f"line to {abs(ratio - 1.0) * 100:.1f}%")
    elif "extrapolated_before_first" in hows:
        basis = f"read before the first mapped milestone (km {used[0]['km']:g}) at one OSM metre per official metre"
    else:
        basis = f"read from the single milestone of km {used[0]['km']:g} at one OSM metre per official metre"
    if inside:
        where = f"the placed part lies inside {tambon}, as the list says"
    else:
        others = ", ".join(row["adm3_name"] for row in entry["tambons_of_placed_part"]) or "no tambon"
        where = (f"the placed part lies in {others}, {entry['distance_to_named_tambon_m']:.0f} m from {tambon}, which "
                 f"the list names (share inside {tambon}: {share if share is not None else 0:g}), so its place along "
                 f"the road is uncertain by some hundreds of metres")
    if abs(shift) < 1.0:
        return f"Placed by milestones, {basis}; {where}."
    return (f"Placed by milestones, {basis}; {where}; reading from the nearest milestone at unit scale instead shifts "
            f"it by {abs(shift):.0f} m.")


def placement_confidence(entry: Mapping[str, Any]) -> str | None:
    """``medium`` for a milestone placement inside the named tambon, ``low`` for every other placement."""

    if entry["status"] != "placed":
        return None
    if entry["method"] == "milestones" and entry["inside_named_tambon"]:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------------------------------------------------
# Stage: gauge
# ---------------------------------------------------------------------------------------------------------------------

def fetch(url: str, attempts: int = 4) -> bytes:
    """GET ``url`` without credentials, retrying with a growing pause when the host times out."""

    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "floodguard-nan-case/1 (research; no login)"})
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except Exception as error:  # noqa: BLE001 - every failure of a public host is retried, then raised
            last = error
            time.sleep(10 * (attempt + 1))
    raise BuildError(f"could not fetch {url}: {last}")


def parse_graph(payload: Mapping[str, Any]) -> tuple[list[tuple[str, float | None, float | None]], dict[str, Any]]:
    """The hourly rows ``(datetime_local, metres MSL, discharge)`` and the station fields of a thaiwater graph."""

    data = payload["data"]
    rows = [(row["datetime"], None if row.get("value") is None else float(row["value"]),
             None if row.get("discharge") is None else float(row["discharge"])) for row in data["graph_data"]]
    meta = {key: data.get(key) for key in ("min_bank", "ground_level", "warning_level", "critical_level", "qmax")}
    return rows, meta


def stage_gauge(external: Path, log: Log) -> dict[str, Any]:
    """Download the hourly levels of the gauges, save them with their source, and summarise the peaks."""

    folder = external / WORK / GAUGE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    retrieved = now_utc()
    load_bytes = fetch(THAIWATER_LOAD)
    load_path = refuse_firewalled(folder / "thaiwater_waterlevel_load_snapshot.json")
    load_path.write_bytes(load_bytes)
    load = json.loads(load_bytes.decode("utf-8"))
    station_meta = {}
    for row in load["waterlevel_data"]["data"]:
        station = row.get("station") or {}
        station_meta[station.get("id")] = {key: station.get(key) for key in (
            "tele_station_oldcode", "tele_station_name", "tele_station_lat", "tele_station_long", "min_bank",
            "ground_level", "offset", "critical_level_msl")}
    stations = []
    for spec in GAUGE_STATIONS:
        url = THAIWATER_GRAPH.format(station_id=spec["station_id"], start=GAUGE_PERIOD[0], end=GAUGE_PERIOD[1])
        raw = fetch(url)
        raw_path = refuse_firewalled(folder / f"thaiwater_{spec['station_id']}_{GAUGE_PERIOD[0]}_{GAUGE_PERIOD[1]}.json")
        raw_path.write_bytes(raw)
        rows, meta = parse_graph(json.loads(raw.decode("utf-8")))
        current = station_meta.get(spec["station_id"], {})
        offset = current.get("offset")
        gauge_zero = float(offset) if spec["agency"] == "RID" and offset is not None else None
        levels = {}
        if meta.get("min_bank") is not None:
            levels["min_bank"] = float(meta["min_bank"])
        if current.get("critical_level_msl") is not None:
            levels["critical_level_msl"] = float(current["critical_level_msl"])
        csv_path = refuse_firewalled(folder / f"thaiwater_{spec['station_id']}_{GAUGE_PERIOD[0]}_{GAUGE_PERIOD[1]}.csv")
        with open(csv_path, "w", encoding="utf-8", newline="\n") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["datetime_thai_time", "level_m_msl", "gauge_height_m", "discharge_m3_s"])
            for stamp, value, discharge in rows:
                writer.writerow([stamp, "" if value is None else f"{value:.3f}",
                                 "" if value is None or gauge_zero is None else f"{value - gauge_zero:.3f}",
                                 "" if discharge is None else f"{discharge:.1f}"])
        summary = gauge_summary([(stamp, value) for stamp, value, _ in rows], levels, gauge_zero)
        checks = []
        for code, stamp, expected, source in GAUGE_NEWS_CHECKS:
            if code != spec["code"] or gauge_zero is None:
                continue
            value = next((v for s, v, _ in rows if s == stamp), None)
            checks.append({"news_record": source, "datetime_thai_time": stamp, "gauge_m_in_news": expected,
                           "gauge_m_in_series": None if value is None else round(value - gauge_zero, 2),
                           "same_to_1_cm": None if value is None else abs(value - gauge_zero - expected) <= 0.011})
        for code, stamp, below, source in GAUGE_NEWS_BELOW_LEVEL:
            if code != spec["code"] or "critical_level_msl" not in levels:
                continue
            value = next((v for s, v, _ in rows if s == stamp), None)
            checks.append({"news_record": source, "datetime_thai_time": stamp,
                           "metres_below_bank_in_news": below,
                           "metres_below_critical_level_msl_in_series": None if value is None else
                           round(levels["critical_level_msl"] - value, 2)})
        stations.append({
            **spec,
            "source_url": url,
            "retrieved_at_utc": retrieved,
            "raw_file": {"name": raw_path.name, "sha256": sha256_file(raw_path)},
            "csv_file": {"name": csv_path.name, "sha256": sha256_file(csv_path)},
            "station_fields_in_series": meta,
            "station_fields_now": current,
            "gauge_zero_msl": gauge_zero,
            "summary": summary,
            "checks_against_news": checks,
        })
        log(f"gauge: {spec['code']}: peak {summary.get('peak_msl')} m MSL at {summary.get('peak_times_local')}")
    record = {
        "schema": "floodguard.nan_case_gauge_summary.v1",
        "generated_at_utc": retrieved,
        "source": "thaiwater.net public service of the Hydro-Informatics Institute (HII), no login; levels of RID, "
                  "HII and EGAT stations as that service serves them",
        "period_thai_time": list(GAUGE_PERIOD),
        "load_snapshot": {"name": load_path.name, "sha256": sha256_file(load_path), "url": THAIWATER_LOAD,
                          "note": "station fields (bank, gauge zero) as published on the retrieval date, not "
                                  "necessarily those of 2025"},
        "stations": stations,
    }
    write_json(folder / GAUGE_SUMMARY, record)
    return record


# ---------------------------------------------------------------------------------------------------------------------
# Stage: news
# ---------------------------------------------------------------------------------------------------------------------

NEWS: tuple[dict[str, Any], ...] = (
    {"id": "bangkokinsight_20250731_mot_list", "topic": "road_cuts",
     "source_url": "https://www.thebangkokinsight.com/news/politics-general/general/1528937/",
     "publisher": "The Bangkok Insight", "published_local": "2025-07-31T15:44+07:00", "language": "th",
     "paraphrase": "The Ministry of Transport summarised road points hit by floods from 1 to 31 July 2025 (189 points, "
                   "18 impassable) and listed for Nan highway 1243 at km 59+100 in Wiang Sa and rural roads Nan 4020 "
                   "(two stretches), Nan 021 and Nan 3019 among others.",
     "time_said": "cumulative 1 to 31 July 2025, as of 31 July 2025; no time of day and no start or end of any cut",
     "place_said": "route, km and tambon (district for most entries); the four protocol entries match the protocol's "
                   "text, the tambon of highway 1243 written น้ำม่วน; a fifth entry inside the frame (Nan 3019 km "
                   "7+000 to 8+000, Mueang Chang) has no district",
     "use": "the list of test 3b"},
    {"id": "thansettakij_20250726_drr_list", "topic": "road_cuts",
     "source_url": "https://www.thansettakij.com/general-news/634140",
     "publisher": "Thansettakij (ฐานเศรษฐกิจ)", "published_local": "2025-07-26T15:06+07:00", "language": "th",
     "paraphrase": "The Department of Rural Roads listed 21 impassable rural roads in the north, nine of them in Nan, "
                   "including Nan 4020 at km 10+500 to 10+900 and km 31+690 to 32+200, Nan 3019 at km 7+000 to "
                   "8+000, the approach road of the Hua Wiang Nuea – Nam Tuan Phatthana bridge (Nan 021, km 0+000 to "
                   "0+300) and the Nakhon Nan Phatthana bridge road (Nan 012) beside Nan Hospital.",
     "time_said": "situation at 09:00 on 26 July 2025",
     "place_said": "route name, km range and district; Nan 4020 is the road from highway 1168 to Ban Huai Son in Phu "
                   "Phiang and Wiang Sa",
     "use": "dates three of the four protocol points (and Nan 3019) as impassable on 26 July 2025, inside the window of "
            "test 3b; names the road of Nan 021"},
    {"id": "thansettakij_20250801_doh_drr_list", "topic": "road_cuts",
     "source_url": "https://www.thansettakij.com/general-news/634749",
     "publisher": "Thansettakij (ฐานเศรษฐกิจ)", "published_local": "2025-08-01T13:56+07:00", "language": "th",
     "paraphrase": "On 1 August 2025 highway 1243 (section Huai Phai – Hat Rai) was impassable at km 58+875 to 58+900 "
                   "in Wiang Sa where a bridge approach had washed out, with a local detour, and over a long stretch "
                   "from km 34+036 in Na Noi because of landslides; no rural road of Nan was listed.",
     "time_said": "status of 1 August 2025",
     "place_said": "route, section name, km and district",
     "use": "places the 1243 cut of the 31 July list at a bridge approach about km 58.9 (report only; the protocol "
            "placement is by tambon)"},
    {"id": "thansettakij_20260820_drr_list_other_event", "topic": "road_cuts",
     "source_url": "https://www.thansettakij.com/general-news/666967",
     "publisher": "Thansettakij (ฐานเศรษฐกิจ)", "published_local": "2026-08-20T13:44+07:00", "language": "th",
     "paraphrase": "During a later flood (August 2026) the Department of Rural Roads closed seven Nan roads, among them "
                   "the Hua Wiang Nuea – Nam Tuan Phatthana bridge road (Nan 021, km 0+000 to 0+600) in Phu Phiang "
                   "with water 130 cm deep at the bridge approach.",
     "time_said": "20 August 2026: a different event, not the 2025 case",
     "place_said": "route name, km range and district",
     "use": "identification of the Nan 021 road only; no fact of 2025"},
    {"id": "khaosod_lineToday_20250724_hospital", "topic": "hospital",
     "source_url": "https://today.line.me/th/v3/article/nXOBrGM",
     "publisher": "Khaosod via LINE TODAY", "published_local": "2025-07-24T08:13+07:00", "language": "th",
     "paraphrase": "Water from the Nan River had entered Nan Hospital, reaching its emergency department; critically ill "
                   "patients, including those on ventilators, were moved to nearby hospitals, the emergency service "
                   "moved to the Air Force Wing 466 base in Nan, and barriers were raised around the ICU and "
                   "operating rooms.",
     "time_said": "by the morning of 24 July 2025 (LINE TODAY stamps 01:13 UTC, updated 05:13 UTC); no hour of entry given",
     "place_said": "Nan Hospital, its emergency department; the town's economic quarter flooded",
     "use": "test 4: the hospital was flooded by the early hours of 24 July 2025"},
    {"id": "thairath_20250724_update", "topic": "hospital_and_river",
     "source_url": "https://www.thairath.co.th/news/local/north/2872477",
     "publisher": "Thairath", "published_local": "2025-07-24T18:26+07:00", "language": "th",
     "paraphrase": "Staff reached Nan Hospital in small boats against a strong current while patients without severe "
                   "conditions were moved to Wing 466, and at 05:00 the river stood at 9.27 m at the Nan town station "
                   "(bank 7 m) and 14.65 m at the Pha Khwang bridge station, above the 2024 peaks.",
     "time_said": "the night of 23 July and 24 July 2025; river levels at 05:00 on 24 July",
     "place_said": "Nan Hospital; Nan town and Phu Phiang, where the river left its banks from about 09:00",
     "use": "test 4 and the gauge check (N.1 at 05:00 on 24 July)"},
    {"id": "thairath_20250724_town", "topic": "river_and_town",
     "source_url": "https://www.thairath.co.th/news/local/northeast/2872276",
     "publisher": "Thairath", "published_local": "2025-07-24T09:14+07:00", "language": "th",
     "paraphrase": "Flooding in Nan municipality grew from 18:30 on 23 July, and the provincial water centre expected "
                   "the Nan River at the Phatthana Phak Nuea bridge to peak at about 9.51 m between 04:00 and 06:00 "
                   "on 24 July.",
     "time_said": "from 18:30 on 23 July 2025; expected peak 04:00 to 06:00 on 24 July",
     "place_said": "Nan municipality; the Phatthana Phak Nuea bridge (the N.1 station's bridge)",
     "use": "time of town flooding beside the gauge record"},
    {"id": "thansettakij_20250723_levels", "topic": "river",
     "source_url": "https://www.thansettakij.com/general-news/633657",
     "publisher": "Thansettakij (ฐานเศรษฐกิจ)", "published_local": "2025-07-23T07:21+07:00", "language": "th",
     "paraphrase": "The Upper Northern Region Irrigation Hydrology Center gave Nan River levels at 06:00 on 23 July: "
                   "N.64 7.99 m (bank 9.50 m), N.1 5.82 m (7.00 m), N.13A 5.00 m (6.50 m) and N.75 7.69 m (10.00 m).",
     "time_said": "06:00 on 23 July 2025",
     "place_said": "stations N.64 Ban Pha Khwang, N.1 Nan town, N.13A Ban Phai Ngam (Wiang Sa), N.75 Tha Li bridge",
     "use": "gauge check"},
    {"id": "thansettakij_20250725_hospital", "topic": "hospital",
     "source_url": "https://www.thansettakij.com/general-news/634023",
     "publisher": "Thansettakij (ฐานเศรษฐกิจ)", "published_local": "2025-07-25T11:45+07:00", "language": "th",
     "paraphrase": "At 09:30 on 25 July Nan Hospital had been under water for 35 hours; the water had fallen by about "
                   "90 cm, but the hospital could not yet run normal services and could not yet assess the damage.",
     "time_said": "09:30 on 25 July 2025, which puts the water's entry at about 22:30 on 23 July (inferred, not "
                  "stated)",
     "place_said": "Nan Hospital (inside the hospital; no building named)",
     "use": "test 4: duration and fall of the water"},
    {"id": "thansettakij_20250725_moph", "topic": "hospital",
     "source_url": "https://www.thansettakij.com/health-wellness/wellbeing/634064",
     "publisher": "Thansettakij (ฐานเศรษฐกิจ)", "published_local": "2025-07-25T17:15+07:00", "language": "th",
     "paraphrase": "The Ministry of Public Health counted 19 health facilities hit by Storm Wipha and 9 closed; Nan "
                   "Hospital was among the hardest hit and closed, while Wiang Sa Hospital was listed as affected "
                   "but not closed.",
     "time_said": "25 July 2025",
     "place_said": "Nan Hospital, Wiang Sa Hospital and other Nan facilities by name",
     "use": "test 4; Wiang Sa Hospital affected"},
    {"id": "matichon_20250726_hospital", "topic": "hospital",
     "source_url": "https://www.matichon.co.th/social/news_5293520",
     "publisher": "Matichon", "published_local": "2025-07-26T09:41+07:00", "language": "th",
     "paraphrase": "The governor reported that at 08:00 on 26 July water no longer covered the Nakhon Nan Phatthana "
                   "bridge beside Nan Hospital, and that the hospital's accident and emergency building had stood in "
                   "more than 1 m of water for over 40 hours; staff could enter it that morning to clean, but normal "
                   "services could not resume yet.",
     "time_said": "morning of 26 July 2025; the water stood in the building for more than 40 hours before",
     "place_said": "Nan Hospital, its accident and emergency building; the Nakhon Nan Phatthana bridge beside it; Phu "
                   "Phiang side still partly under water",
     "use": "test 4: depth (over 1 m in the emergency building) and the water leaving by the morning of 26 July"},
    {"id": "matichon_20250727_hospital_reopens", "topic": "hospital",
     "source_url": "https://www.matichon.co.th/region/news_5295722",
     "publisher": "Matichon", "published_local": "2025-07-27T22:20+07:00", "language": "th",
     "paraphrase": "Nan Hospital, whose services had been cut back since 24 July, announced at 20:00 on 27 July that "
                   "its accident and emergency service would reopen in its accident building from 28 July, with other "
                   "services to follow; the governor said the Nan River was back within its banks except at N.13A.",
     "time_said": "services reduced from 24 July 2025; emergency service from 28 July 2025",
     "place_said": "Nan Hospital, accident building; the Nan River at the Phatthana Phak Nuea bridge; station N.13A "
                   "(Wiang Sa) still above its bank on 27 July",
     "use": "test 4: end of the closure; Wiang Sa still high on 27 July"},
)

SEARCHES_WITHOUT_RESULT: tuple[dict[str, str], ...] = (
    {"what": "the original Ministry of Transport release of 31 July 2025",
     "where_looked": "web search; www.mot.go.th (news pages built by a script); its content service rapi.mot.go.th "
                     "refused automated requests (HTTP 418 from a web firewall)",
     "outcome": "not found; the press copy of The Bangkok Insight is the source, and the Department of Rural Roads "
                "list of 26 July 2025 carries the same three rural-road entries"},
    {"what": "a public record of the hour Nan Hospital's water entered and left, and its peak depth",
     "where_looked": "news search in Thai and English",
     "outcome": "no stated hour of entry; 35 hours under water at 09:30 on 25 July (entry about 22:30 on 23 July by "
                "inference); more than 1 m for over 40 hours in the emergency building; water off the bridge beside "
                "the hospital by 08:00 on 26 July; emergency service from 28 July"},
    {"what": "the RID Upper Northern hydrology centre's own station pages (hydro-1.net)",
     "where_looked": "https and http from this machine",
     "outcome": "not reachable from this machine (https refused; http answered by a national web filter page); the "
                "same RID stations were read through thaiwater.net"},
)


GAUGE_LEVEL_NOTES: dict[str, str] = {
    "N.64": "min_bank is the bank level the news gives (9.50 m above the gauge zero).",
    "N.1": "min_bank is the bank level the news gives (7.00 m above the gauge zero); two news readings match the "
           "series to the centimetre at the stated Thai hours.",
    "N.75": "min_bank is the bank level the news gives (10.00 m above the gauge zero).",
    "SKU04 (N.13A)": "The station's min_bank field (about 190.3 m) is never reached, although the governor said N.13A "
                     "was still above its bank on 27 July; its critical_level_msl field (183.9 m) fits the news "
                     "reading of 23 July (1.50 m below the bank in the news, 1.60 m below that field in the series) "
                     "and is read as the bank. The two fields are given as published.",
    "NAN003": "HII station; min_bank as published, not checked against a news reading.",
    "NAN009": "HII station; min_bank as published, not checked against a news reading.",
}


def stage_news(external: Path, log: Log) -> dict[str, Any]:
    """Write the news record with the gauge peaks of the work folder's gauge summary."""

    summary_path = external / WORK / GAUGE_DIR / GAUGE_SUMMARY
    gauge = read_json(summary_path) if refuse_firewalled(summary_path).exists() else None
    gauge_records = []
    if gauge is not None:
        for station in gauge["stations"]:
            s = station["summary"]
            gauge_records.append({
                "station": station["code"], "agency": station["agency"], "place": station["place"],
                "river": station["river"], "source_url": station["source_url"],
                "publisher": "thaiwater.net (Hydro-Informatics Institute)",
                "retrieved_at_utc": station["retrieved_at_utc"],
                "period_thai_time": gauge["period_thai_time"],
                "file_outside_git": {"folder": f"<external>/{(WORK / GAUGE_DIR).as_posix()}", **station["csv_file"]},
                "reading_step": "hourly" if station["agency"] in ("RID", "EGAT") else "10 minutes",
                "peak_m_msl": s.get("peak_msl"), "peak_gauge_height_m": s.get("peak_gauge_m"),
                "peak_times_thai_time": s.get("peak_times_local"), "readings_at_peak": s.get("readings_at_peak"),
                "gauge_zero_m_msl": station["gauge_zero_msl"],
                "levels": {name: {"level_m_msl": level["level_msl"], "readings_above": level["readings_above"],
                                  "first_above_thai_time": level["first_above_local"],
                                  "last_above_thai_time": level["last_above_local"],
                                  "runs_above_thai_time": level["runs_above_local"],
                                  "peak_minus_level_m": level["peak_minus_level_m"]}
                           for name, level in s.get("levels", {}).items()},
                "level_note": GAUGE_LEVEL_NOTES.get(station["code"]),
                "checks_against_news": station["checks_against_news"],
            })
    record = {
        "schema": "floodguard.nan_case_news_records.v1",
        "case_id": "N1",
        **envelope("news and lists of 23 July to 1 August 2025 (one of 20 August 2026, marked); thaiwater.net hourly "
                   "levels of 15 July to 15 August 2025",
                   "Press reports and copies of agency lists, paraphrased; a public gauge service read without a "
                   "login; nothing checked on the ground."),
        "what_this_is": "Dated public records set beside the Nan case: the reported road cuts, the flooding of Nan "
                        "Hospital and the Nan River levels. Facts with a citation, paraphrased; quotations are a few "
                        "words at most. They are context for tests 3b and 4, not a reference layer.",
        "times": "Thai time (UTC+7) unless marked. published_local is the publication time in each page's metadata "
                 "(datePublished), put in Thai time. thaiwater.net series are in Thai time: five news readings of "
                 "23 and 24 July agree with the series to the centimetre at the stated Thai hours.",
        "records": list(NEWS),
        "gauge_records": gauge_records,
        "gauge_note": None if gauge is not None else "the gauge stage has not run",
        "searches_without_result": list(SEARCHES_WITHOUT_RESULT),
        "rights": "News texts belong to their publishers and are not copied; the gauge series stay outside Git and "
                  "only their peaks are given, with the source address.",
        "code": git_file(SCRIPT),
        "limits": LIMITS,
    }
    write_json(ROOT / NEWS_RECORD, record)
    log(f"news: wrote {NEWS_RECORD} sha256 {sha256_file(ROOT / NEWS_RECORD)}")
    return record


# ---------------------------------------------------------------------------------------------------------------------

def run(arguments: argparse.Namespace) -> None:
    """Run the stages asked for."""

    external = Path(arguments.external_root)
    if not external.is_dir():
        raise BuildError(f"the external data root {external} is not a folder")
    log = Log(external / WORK / LOG_NAME)
    stages = ("extract", "place", "gauge", "news") if arguments.stage == "all" else (arguments.stage,)
    log(f"start: {SCRIPT} stages {', '.join(stages)}")
    for stage in stages:
        if stage == "extract":
            stage_extract(external, log)
        elif stage == "place":
            stage_place(external, arguments, log)
        elif stage == "gauge":
            stage_gauge(external, log)
        elif stage == "news":
            stage_news(external, log)
    log("done")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-root", required=True, help="the external data root (outside Git)")
    parser.add_argument("--stage", choices=("extract", "place", "gauge", "news", "all"), default="all")
    parser.add_argument("--replace", action="store_true", help="write over an existing record of positions")
    parser.add_argument("--reason", default="", help="why an existing record of positions is replaced")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
