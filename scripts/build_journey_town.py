#!/usr/bin/env python
"""Bake the journey town pack: the real map of Mae Sai town around the Public app's example home (branch journey-v2).

The ``/journey/`` story plays on the real map of Mae Sai town with the water of the published replay (revision r5, a
model reconstruction of September 2024 with low confidence). This bake writes what the 3D scene reads, following the
data contract in ``docs/journey-v2-real-map.md``. The people of the story are fictional; the two example homes are
points of the replay's resident grid, not addresses.

Inputs
------
* External files (kept outside Git), under ``--external-root`` or ``FLOODGUARD_EXTERNAL_DATA``:
  - ``proposal_execution/buildings_in_water/mae_sai_outlines.gpkg``: open building outlines (Google Open Buildings v3
    and Microsoft building footprints, combined by VIDA), read by bounding box. Its SHA-256 must equal the one recorded
    in ``outputs/buildings_in_water/outlines_v1.json`` (the provenance record of 11 October 2026).
  - ``derived_context/mae_sai_2024/mae_sai_osm_roads.geojson``: OpenStreetMap road centrelines.
  - ``derived_context/mae_sai_2024/mae_sai_osm_multipolygons.gpkg``: OpenStreetMap site polygons (places of worship,
    offices, schools, markets): building kinds and the compounds of the reported sites.
  - ``open_context/osm_geofabrik/thailand-latest.osm.pbf``: OpenStreetMap land-use, natural and water polygons and the
    waterway lines inside the detail box. The derived multipolygon file keeps no ``landuse`` or ``natural`` tag and no
    waterway line, so the bake reads them from the Geofabrik extract of 9 July 2026 on every run (about 90 seconds;
    nothing is cached).
  - ``open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif``: relief. The backdrop square
    lies inside this tile, so the E100 tile is not read.
* In-repo files: the replay r5 (``apps/web/public/studies/mae-sai-2024-timeline/r5/timeline.json``,
  ``hand-codes.png`` and ``access-nodes.bin``; the hashes of the last two must equal those in ``timeline.json``),
  ``outputs/mae_sai_access_edges.csv`` (the replay's walking network; node ids hold longitude and latitude),
  and ``outputs/buildings_in_water/outlines_v1.json``.
* Constants: the practice homes and scenario hours of the Public app (``PRACTICE_HOMES`` and ``PRACTICE_SCENARIOS`` of
  ``apps/web/src/lib/public-practice-scenarios.ts``) are copied here, so unrelated edits to that file do not touch the
  receipt; ``tests/test_journey_town.py`` parses the TypeScript and fails when the two differ.

Frame
-----
A local plane at the dry example home (20.44042, 99.88718): ``x = (lon - 99.88718) * 111320 * cos(20.44042 deg)``,
``z = (20.44042 - lat) * 110540`` (metres; x east, z south, y up; the constants of ``groundDistanceM``). Detail box
x -1500..900, z -800..1800. Backdrop: a square of 133 cells of 60 m (7.98 km) centred on (x -300, z 500).

The r5 HAND raster is linear in longitude across its columns and linear in Web Mercator y down its rows, over the
manifest's rounded bounds ``[[S, W], [N, E]]``: ``col = floor((lon - W) / (E - W) * 1610)``,
``row = floor((mercY(N) - mercY(lat)) / (mercY(N) - mercY(S)) * 1753)``, ``mercY(lat) = ln(tan(pi/4 + lat/2))``.

Outputs (``apps/web/public/journey/town/``)
-------------------------------------------
* ``mae-sai-town-cells.png``: RGB 8-bit, the r5 cells covering the detail box, cell for cell: R = code (0 channel,
  1-254 effective HAND in 0.05 m steps, 255 never floods), G = depth-factor byte (k = G / 255 * 2.5), B = 255 where the
  r5 low-confidence byte is at least 128 and the cell is not channel, else 0. The manifest gives the crop offset and the
  affine of cell centres in the local frame (straight-line fit; its largest error is recorded and must stay below 1 m).
* ``mae-sai-town-relief.png``: RGB 8-bit on the same cells: R, G = big-endian uint16 of height in decimetres + 2000 for
  cells that never flood (code 255), else 0; B = 0. Height = Copernicus DSM at the cell centre (bilinear) minus a
  drainage datum, clamped to at least 12.8 m so it stays above the highest floodable cell (code 254 = 12.7 m). The datum
  is the median over the floodable cells of the detail box of (DSM - k * code * 0.05), rounded to 0.01 m.
* ``mae-sai-town-cover.png``: greyscale 8-bit, 4 m cells over the detail box: 0 open ground, 1 water, 2 road,
  3 building, 4 green, 5 field. Precedence where classes overlap: water > building > road > field > green > open.
* ``mae-sai-town-backdrop.png``: RGB 8-bit, 60 m cells over the backdrop square: R, G = big-endian uint16 of
  (DSM - datum) in decimetres + 2000 (heights down to -200 m fit); B = 0.
* ``mae-sai-town.json``: manifest (provenance, timestamp, confidence, assumptions, credits, replay hashes, frame,
  places, beats, route) and vectors (buildings, roads, trees) as integer decimetres, delta-encoded.
* ``LICENSE.txt``: credits and licences (ODbL 1.0 for the derivative database).

The bake asserts and stops when the dry home is wet at any beat, the flooded neighbour is dry at hour 84, the usual
walk is closed at hour 48 or open at hour 84, the walk's cut stage differs from the Public app's cut level by more than
0.25 m, or any output coordinate leaves its extent.

Reproducibility
---------------
Every bake writes an input receipt (``docs/journey_town_input_receipt.json``): the path relative to its root
(``external`` or ``repo``, never a machine path), the size and the SHA-256 of every input the bake opened, the library
versions and the SHA-256 of the bake's own sources. ``generated_at`` is never read from the clock: it is declared with
``--generated-at``; without it, a bake carries the recorded value only when it reproduces every recorded output file
byte for byte. ``--verify`` bakes into a temporary folder and byte-compares it with the committed folder (exit 1 on
any difference). Output is deterministic: stable sort orders, fixed rounding, a fixed random seed for the trees,
compact JSON with LF line endings.

This is a scene for preparedness learning. It is not an observation, a real-time product or an official warning.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np
from PIL import Image
import pyogrio
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine
from rasterio.windows import Window
from scipy import ndimage
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from floodguard.bake_receipt import (  # noqa: E402
    DEFAULT_LIBRARIES,
    RECEIPT_SCHEMA,
    InputReceipt,
    compare_directories,
    directory_listing,
    input_differences,
    library_versions,
    source_differences,
    source_hashes,
    version_differences,
)
from floodguard.evacuation_access import closure_stage  # noqa: E402
from floodguard.flood_timeline import CHANNEL_CODE, HAND_STEP_M, IMPASSABLE_DEPTH_M, NEVER_CODE  # noqa: E402
import mae_sai_timeline_evacuation as evac  # noqa: E402

Track = Callable[[Path], Path]

SCHEMA = "floodguard.journey-town.v1"
GENERATED_BY = "scripts/build_journey_town.py"
OUT_REL = Path("apps/web/public/journey/town")
RECEIPT_REL = Path("docs/journey_town_input_receipt.json")
HREF_PREFIX = "/journey/town/"
FILES = {
    "manifest": "mae-sai-town.json",
    "cells": "mae-sai-town-cells.png",
    "relief": "mae-sai-town-relief.png",
    "cover": "mae-sai-town-cover.png",
    "backdrop": "mae-sai-town-backdrop.png",
    "licence": "LICENSE.txt",
}

REPLAY_REL = Path("apps/web/public/studies/mae-sai-2024-timeline/r5")
TIMELINE_REL = REPLAY_REL / "timeline.json"
HAND_REL = REPLAY_REL / "hand-codes.png"
NODES_REL = REPLAY_REL / "access-nodes.bin"
EDGES_REL = Path("outputs/mae_sai_access_edges.csv")
OUTLINES_RECORD_REL = Path("outputs/buildings_in_water/outlines_v1.json")

OUTLINES_EXT = "proposal_execution/buildings_in_water/mae_sai_outlines.gpkg"
ROADS_EXT = "derived_context/mae_sai_2024/mae_sai_osm_roads.geojson"
SITES_EXT = "derived_context/mae_sai_2024/mae_sai_osm_multipolygons.gpkg"
PBF_EXT = "open_context/osm_geofabrik/thailand-latest.osm.pbf"
DEM_EXT = "open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif"

ORIGIN_LAT, ORIGIN_LON = 20.44042, 99.88718
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(ORIGIN_LAT))
M_PER_DEG_LAT = 110540.0
DETAIL = (-1500.0, 900.0, -800.0, 1800.0)
"""Detail box in the local frame: x_min, x_max, z_min, z_max (metres)."""
BACKDROP_CENTRE = (-300.0, 500.0)
BACKDROP_CELL_M = 60.0
BACKDROP_CELLS = 133
COVER_CELL_M = 4.0
HEIGHT_OFFSET_DM = 2000
NEVER_MIN_HEIGHT_M = 12.8
PNG_COLS, PNG_ROWS = 1610, 1753
LOW_CONFIDENCE_MIN_BYTE = 128
REPLAY_EPOCH = datetime(2024, 9, 9, tzinfo=timezone(timedelta(hours=7)))
REPLAY_EPOCH_TEXT = "2024-09-09T00:00:00+07:00"
BEAT_HOURS = (12, 40, 46, 48, 49, 84, 132)
WALK_LIMIT_M = 2000.0
"""The replay's walking threshold (``ACCESS_THRESHOLD_M``): about 30 minutes at 4 km/h."""
APP_NODE_REACH_M = 150.0
"""``PRACTICE_NODE_REACH_M`` of the Public app: a home takes the figures of the nearest resident point within this distance."""
CUT_TOLERANCE_M = 0.25
WET_SHARE_RADIUS_M = 450.0
REPORTED_SET_ID = "reported_2024"
SAI_BRIDGE_LONLAT = (99.8826, 20.4460)
"""Sai River at the Mae Sai border bridges (the replay's main-stem reference): the river label sits on the river nearest it."""

BUILDING_SIMPLIFY_M = 0.35
BUILDING_MIN_AREA_M2 = 8.0
ROAD_SIMPLIFY_M = 0.5
SHOPHOUSE_REACH_M = 12.0
FRONT_TIE = 0.1
BUILDING_KINDS = ("shophouse", "house", "large", "shed", "temple", "government", "school", "market")
FLOORS = {"shophouse": (2, 4), "house": (1, 2), "large": (1, 2), "shed": (1, 1), "temple": (1, 1),
          "government": (2, 3), "school": (2, 3), "market": (1, 1)}
ROAD_CLASSES = ("trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service", "living_street",
                "track", "path", "footway", "pedestrian", "other")
ROAD_WIDTH_DM = {"trunk": 140, "primary": 120, "secondary": 90, "tertiary": 80, "unclassified": 60, "residential": 50,
                 "living_street": 45, "service": 35, "track": 30, "path": 18, "footway": 18, "pedestrian": 18, "other": 35}
HIGHWAY_ALIASES = {"trunk_link": "trunk", "primary_link": "primary", "secondary_link": "secondary",
                   "tertiary_link": "tertiary", "steps": "footway", "cycleway": "path", "bridleway": "path"}
MAIN_ROADS = frozenset({"trunk", "primary", "secondary", "tertiary"})
LANE_WIDTH_DM = 32.5

COVER_CLASSES = ("open_ground", "water", "road", "building", "green", "field")
OPEN, WATER, ROAD, BUILDING, GREEN, FIELD = range(6)
COVER_PRECEDENCE = ("water", "building", "road", "field", "green", "open_ground")
GREEN_LANDUSE = frozenset({"forest", "grass", "meadow", "orchard", "recreation_ground", "village_green", "cemetery",
                           "plant_nursery"})
GREEN_NATURAL = frozenset({"wood", "scrub", "grassland", "heath"})
GREEN_LEISURE = frozenset({"park", "garden", "pitch", "golf_course", "nature_reserve"})
FIELD_LANDUSE = frozenset({"farmland", "paddy"})
WATER_LANDUSE = frozenset({"reservoir", "basin"})
WATERWAY_HALF_WIDTH_M = {"river": 10.0, "canal": 3.0, "stream": 2.0}
MIN_ROAD_HALF_WIDTH_IN_COVER_M = COVER_CELL_M / 2

TEMPLE_AMENITY = frozenset({"place_of_worship"})
TEMPLE_BUILDING = frozenset({"temple", "shrine"})
GOVERNMENT_AMENITY = frozenset({"townhall", "police", "fire_station", "courthouse"})
GOVERNMENT_BUILDING = frozenset({"government", "public", "civic"})
SCHOOL_AMENITY = frozenset({"school", "college", "kindergarten", "university"})
SCHOOL_BUILDING = frozenset({"school", "college", "university", "kindergarten"})
MARKET_AMENITY = frozenset({"marketplace"})

TREE_SEED = 20240909
TREE_MAX = 5000
TREE_KINDS = ("broadleaf", "coconut_palm", "banana", "mango_or_rain_tree")
TREE_CLEARANCE_M = 2.5
RIVER_BANK_M = 25.0
TREE_PASSES = (
    # name, minimum spacing (m), candidate darts per disc of the spacing, at most this many trees,
    # kind weights (broadleaf, coconut palm, banana, mango or rain tree)
    ("river_bank", 9.0, 3.0, 900, (0.0, 1.0, 0.0, 0.0)),
    ("green", 6.0, 3.0, 2000, (0.65, 0.05, 0.12, 0.18)),
    ("field_edge", 8.0, 3.0, 300, (0.45, 0.35, 0.2, 0.0)),
    ("open_ground", 16.0, 2.0, 1800, (0.4, 0.1, 0.3, 0.2)),
)

TAG = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')


# --- Small helpers ---------------------------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 of ``data`` as lowercase hexadecimal."""
    return hashlib.sha256(data).hexdigest()


def to_local(lon: Any, lat: Any) -> tuple[Any, Any]:
    """Longitude and latitude (degrees) to the local frame (x east, z south, metres)."""
    return (np.asarray(lon) - ORIGIN_LON) * M_PER_DEG_LON, (ORIGIN_LAT - np.asarray(lat)) * M_PER_DEG_LAT


def to_lonlat(x: Any, z: Any) -> tuple[Any, Any]:
    """Local frame (metres) to longitude and latitude (degrees)."""
    return ORIGIN_LON + np.asarray(x) / M_PER_DEG_LON, ORIGIN_LAT - np.asarray(z) / M_PER_DEG_LAT


def localise(geometry: Any) -> Any:
    """Shapely geometry (or array of geometries) in longitude/latitude to the local frame."""
    return shapely.transform(geometry, lambda c: np.column_stack(to_local(c[:, 0], c[:, 1])))


def detail_lonlat_bbox(margin_m: float = 60.0) -> tuple[float, float, float, float]:
    """The detail box (plus ``margin_m``) as a longitude/latitude bounding box (west, south, east, north)."""
    x0, x1, z0, z1 = DETAIL
    west, north = to_lonlat(x0 - margin_m, z0 - margin_m)
    east, south = to_lonlat(x1 + margin_m, z1 + margin_m)
    return float(west), float(south), float(east), float(north)


def inside_detail(x: Any, z: Any) -> np.ndarray:
    """True where (x, z) lies inside the detail box (edges included)."""
    x0, x1, z0, z1 = DETAIL
    x, z = np.asarray(x, dtype=float), np.asarray(z, dtype=float)
    return (x >= x0) & (x <= x1) & (z >= z0) & (z <= z1)


def parse_tags(text: str | None) -> dict[str, str]:
    """Parse an OGR ``other_tags`` hstore string into a dict."""
    return {key: value for key, value in TAG.findall(text or "")}


def text_value(value: Any) -> str | None:
    """A field value as a non-empty string, or None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def stable_int(text: str) -> int:
    """A deterministic 32-bit integer from ``text`` (first four bytes of its SHA-256)."""
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")


def dm(values: Any) -> np.ndarray:
    """Metres to integer decimetres (round half to even, as numpy)."""
    return np.rint(np.asarray(values, dtype=float) * 10.0).astype(np.int64)


def delta_encode(points_dm: np.ndarray) -> list[int]:
    """Flatten (n, 2) integer points: first point absolute, then differences."""
    if len(points_dm) == 0:
        return []
    deltas = np.vstack([points_dm[:1], np.diff(points_dm, axis=0)])
    return [int(v) for v in deltas.reshape(-1)]


def round_or_none(value: float | None, digits: int) -> float | None:
    """Round a finite value; None and non-finite values become None."""
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


def read_layer(path: Path, bbox: tuple[float, float, float, float], layer: str | None = None) -> tuple[list[dict[str, Any]], np.ndarray]:
    """Read a vector layer inside ``bbox`` (longitude/latitude): attribute rows and shapely geometries, in file order."""
    meta, _, geometry, fields = pyogrio.raw.read(path, layer=layer, bbox=bbox)
    names = list(meta["fields"])
    geoms = shapely.from_wkb(geometry)
    rows = [{name: fields[j][i] for j, name in enumerate(names)} for i in range(len(geoms))]
    return rows, geoms


# --- The r5 replay -----------------------------------------------------------------------------------------------


def merc_y(lat: Any) -> Any:
    """Web Mercator y of a latitude (radians of the projection, not metres)."""
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


class HandGrid:
    """The georeferencing of the r5 HAND raster: linear in longitude (columns) and in Web Mercator y (rows)."""

    def __init__(self, south: float, west: float, north: float, east: float, width: int, height: int) -> None:
        self.south, self.west, self.north, self.east = float(south), float(west), float(north), float(east)
        self.width, self.height = int(width), int(height)

    def fractional(self, lon: Any, lat: Any) -> tuple[np.ndarray, np.ndarray]:
        """Fractional (column, row) of points; the integer part is the cell."""
        col = (np.asarray(lon, dtype=float) - self.west) / (self.east - self.west) * self.width
        row = (merc_y(self.north) - merc_y(np.asarray(lat, dtype=float))) / (merc_y(self.north) - merc_y(self.south)) * self.height
        return col, row

    def cell(self, lon: Any, lat: Any) -> tuple[np.ndarray, np.ndarray]:
        """Integer (row, column) of the cells holding the points."""
        col, row = self.fractional(lon, lat)
        return np.floor(row).astype(np.int64), np.floor(col).astype(np.int64)

    def centre(self, rows: Any, cols: Any) -> tuple[np.ndarray, np.ndarray]:
        """Longitude and latitude of cell centres."""
        lon = self.west + (np.asarray(cols, dtype=float) + 0.5) / self.width * (self.east - self.west)
        y = merc_y(self.north) - (np.asarray(rows, dtype=float) + 0.5) / self.height * (merc_y(self.north) - merc_y(self.south))
        return lon, np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


def load_replay(track: Track) -> SimpleNamespace:
    """Read the r5 manifest, HAND raster and access nodes, and check the raster and node hashes against the manifest."""
    timeline_bytes = Path(track(ROOT / TIMELINE_REL)).read_bytes()
    timeline = json.loads(timeline_bytes.decode("utf-8"))
    hand_bytes = Path(track(ROOT / HAND_REL)).read_bytes()
    nodes_bytes = Path(track(ROOT / NODES_REL)).read_bytes()
    if sha256_bytes(hand_bytes) != timeline["hand"]["sha256"]:
        raise RuntimeError("hand-codes.png does not match the hash in timeline.json")
    if sha256_bytes(nodes_bytes) != timeline["access"]["nodes"]["sha256"]:
        raise RuntimeError("access-nodes.bin does not match the hash in timeline.json")
    with Image.open(ROOT / HAND_REL) as image:
        rgb = np.asarray(image.convert("RGB"))
    (south, west), (north, east) = timeline["bounds"]
    grid = HandGrid(south, west, north, east, rgb.shape[1], rgb.shape[0])
    if (grid.width, grid.height) != (PNG_COLS, PNG_ROWS) or (timeline["hand"]["width"], timeline["hand"]["height"]) != (PNG_COLS, PNG_ROWS):
        raise RuntimeError("unexpected r5 HAND raster size")
    hand = timeline["hand"]
    if (hand["step_m"], hand["channel_code"], hand["never_code"]) != (HAND_STEP_M, CHANNEL_CODE, NEVER_CODE):
        raise RuntimeError("the r5 HAND coding differs from floodguard.flood_timeline")
    if float(timeline["impassable_depth_m"]) != IMPASSABLE_DEPTH_M:
        raise RuntimeError("the r5 impassable depth differs from floodguard.flood_timeline")
    return SimpleNamespace(
        timeline=timeline, rgb=rgb, grid=grid, nodes=nodes_bytes, scale=float(hand["depth_factor"]["byte_scale"]),
        anchors_t=[float(a["t"]) for a in timeline["stage_anchors"]],
        anchors_stage=[float(a["stage_m"]) for a in timeline["stage_anchors"]],
        hashes={"timeline": sha256_bytes(timeline_bytes), "hand": sha256_bytes(hand_bytes), "nodes": sha256_bytes(nodes_bytes)},
    )


def cell_depth(code: int, stage: float, factor_byte: int, scale: float) -> float | None:
    """Depth (m) of one HAND cell at ``stage`` by the app's ``cellDepth`` rule, or None when it is dry."""
    k = factor_byte / 255 * scale
    if code == CHANNEL_CODE:
        return k * max(0.0, stage)
    if code == NEVER_CODE or not code * HAND_STEP_M < stage:
        return None
    return k * (stage - code * HAND_STEP_M)


def stage_at_hour(replay: SimpleNamespace, hour: float) -> float:
    """The replay's stage at ``hour`` (numpy.interp over the r5 anchors; the same values as ``stageAt``)."""
    return float(np.interp(hour / 24, replay.anchors_t, replay.anchors_stage))


# --- Cells, relief and backdrop -----------------------------------------------------------------------------------


def crop_cells(replay: SimpleNamespace) -> SimpleNamespace:
    """The r5 cells covering the detail box, and the affine of their centres in the local frame."""
    grid: HandGrid = replay.grid
    x0, x1, z0, z1 = DETAIL
    west, north = to_lonlat(x0, z0)
    east, south = to_lonlat(x1, z1)
    row0, col0 = (int(v) for v in grid.cell(west, north))
    row1, col1 = (int(v) for v in grid.cell(east, south))
    rows, cols = row1 - row0 + 1, col1 - col0 + 1
    crop = replay.rgb[row0:row1 + 1, col0:col1 + 1]
    c_idx, r_idx = np.arange(cols), np.arange(rows)
    lon_c, _ = grid.centre(np.zeros(cols), col0 + c_idx)
    _, lat_c = grid.centre(row0 + r_idx, np.zeros(rows))
    x_exact, _ = to_local(lon_c, ORIGIN_LAT)
    _, z_exact = to_local(ORIGIN_LON, lat_c)
    dx, ax = np.polyfit(c_idx, x_exact, 1)
    dz, az = np.polyfit(r_idx, z_exact, 1)
    affine = {"x0": round(float(ax), 4), "dx": round(float(dx), 6), "z0": round(float(az), 4), "dz": round(float(dz), 6)}
    ex = np.abs(affine["x0"] + c_idx * affine["dx"] - x_exact).max()
    ez = np.abs(affine["z0"] + r_idx * affine["dz"] - z_exact).max()
    error = float(math.hypot(ex, ez))
    if error >= 1.0:
        raise RuntimeError(f"the affine of the r5 cells is off by {error:.2f} m (must be below 1 m)")
    code, factor, lowconf = (crop[..., i].astype(np.int64) for i in range(3))
    blue = np.where((lowconf >= LOW_CONFIDENCE_MIN_BYTE) & (code != CHANNEL_CODE), 255, 0)
    png = np.dstack([code, factor, blue]).astype(np.uint8)
    lon_grid, lat_grid = np.meshgrid(lon_c, lat_c)
    xc, zc = np.meshgrid(x_exact, z_exact)
    return SimpleNamespace(row0=row0, col0=col0, rows=rows, cols=cols, code=code, factor=factor, png=png, affine=affine,
                           error=error, lon=lon_grid, lat=lat_grid, x=xc, z=zc)


class Dem:
    """A window of the Copernicus DSM tile, sampled bilinearly at points (pixel-is-area, centres at +0.5)."""

    def __init__(self, path: Path, west: float, south: float, east: float, north: float) -> None:
        with rasterio.open(path) as src:
            t = src.transform
            if src.crs.to_epsg() != 4326 or t.b != 0 or t.d != 0:
                raise RuntimeError("the DEM tile is not a north-up EPSG:4326 grid")
            col0 = int(math.floor((west - t.c) / t.a)) - 2
            row0 = int(math.floor((north - t.f) / t.e)) - 2
            col1 = int(math.ceil((east - t.c) / t.a)) + 2
            row1 = int(math.ceil((south - t.f) / t.e)) + 2
            if col0 < 0 or row0 < 0 or col1 > src.width or row1 > src.height:
                raise RuntimeError("the backdrop square leaves the DEM tile")
            self.data = src.read(1, window=Window(col0, row0, col1 - col0, row1 - row0)).astype(np.float64)
            self.west, self.north, self.dx, self.dy = t.c + col0 * t.a, t.f + row0 * t.e, t.a, t.e
            if src.nodata is not None and np.any(self.data == src.nodata):
                raise RuntimeError("the DEM window holds no-data cells")

    def sample(self, lon: Any, lat: Any) -> np.ndarray:
        """Bilinear DSM height (m) at points."""
        fc = (np.asarray(lon, dtype=float) - self.west) / self.dx - 0.5
        fr = (np.asarray(lat, dtype=float) - self.north) / self.dy - 0.5
        i, j = np.floor(fr).astype(np.int64), np.floor(fc).astype(np.int64)
        di, dj = fr - i, fc - j
        d = self.data
        return (d[i, j] * (1 - di) * (1 - dj) + d[i + 1, j] * di * (1 - dj) + d[i, j + 1] * (1 - di) * dj
                + d[i + 1, j + 1] * di * dj)


def height_png(height_m: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """RGB 8-bit: R, G = big-endian uint16 of height (dm) + 2000 where ``mask``, else 0; B = 0."""
    value = dm(height_m) + HEIGHT_OFFSET_DM
    if np.any(value[mask] < 0) or np.any(value[mask] > 65535):
        raise RuntimeError("a height leaves the uint16 range of the relief encoding")
    value = np.where(mask, value, 0)
    return np.dstack([value >> 8, value & 255, np.zeros_like(value)]).astype(np.uint8)


def backdrop_axes() -> tuple[np.ndarray, np.ndarray]:
    """Cell-centre x and z of the backdrop square."""
    half = (BACKDROP_CELLS - 1) // 2
    offsets = (np.arange(BACKDROP_CELLS) - half) * BACKDROP_CELL_M
    return BACKDROP_CENTRE[0] + offsets, BACKDROP_CENTRE[1] + offsets


def relief_and_backdrop(cells: SimpleNamespace, replay: SimpleNamespace, dem_path: Path) -> SimpleNamespace:
    """The drainage datum, the relief of never-flooding cells and the backdrop heights."""
    bx, bz = backdrop_axes()
    half = BACKDROP_CELL_M / 2
    west, north = to_lonlat(bx[0] - half, bz[0] - half)
    east, south = to_lonlat(bx[-1] + half, bz[-1] + half)
    dem = Dem(dem_path, float(west), float(south), float(east), float(north))
    dsm = dem.sample(cells.lon, cells.lat)
    k = cells.factor / 255 * replay.scale
    floodable = (cells.code >= 1) & (cells.code <= NEVER_CODE - 1) & inside_detail(cells.x, cells.z)
    datum = round(float(np.median(dsm[floodable] - k[floodable] * cells.code[floodable] * HAND_STEP_M)), 2)
    never = cells.code == NEVER_CODE
    height = dsm - datum
    clamped = int(np.count_nonzero(never & (height < NEVER_MIN_HEIGHT_M)))
    relief = height_png(np.maximum(height, NEVER_MIN_HEIGHT_M), never)
    bxx, bzz = np.meshgrid(bx, bz)
    blon, blat = to_lonlat(bxx, bzz)
    back_height = dem.sample(blon, blat) - datum
    backdrop = height_png(back_height, np.ones_like(back_height, dtype=bool))
    return SimpleNamespace(datum=datum, relief=relief, backdrop=backdrop, never=int(never.sum()), clamped=clamped,
                           floodable=int(floodable.sum()), back_min=float(back_height.min()), back_max=float(back_height.max()),
                           never_max=float(height[never].max()) if never.any() else None, axes=(bx, bz))


# --- OpenStreetMap ----------------------------------------------------------------------------------------------------


def road_class(highway: str | None) -> str | None:
    """The scene's road class of an OSM highway value (None for non-roads)."""
    if not highway:
        return None
    value = HIGHWAY_ALIASES.get(highway, highway)
    if value in ROAD_CLASSES:
        return value
    if value in {"road", "corridor", "busway"}:
        return "other"
    return None


def road_width_dm(cls: str, tags: dict[str, str]) -> int:
    """Carriageway width (dm): the ``width`` tag in metres, else ``lanes`` x 3.25 m, else the class default."""
    width = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*m?\s*", tags.get("width", ""))
    if width:
        return int(round(float(width.group(1)) * 10))
    lanes = re.fullmatch(r"\s*(\d+)\s*", tags.get("lanes", ""))
    if lanes and int(lanes.group(1)) > 0:
        return int(round(int(lanes.group(1)) * LANE_WIDTH_DM))
    return ROAD_WIDTH_DM[cls]


def clean_line(coords_m: np.ndarray) -> np.ndarray:
    """Integer-decimetre vertices without consecutive duplicates."""
    pts = dm(coords_m)
    if len(pts) == 0:
        return pts.reshape(0, 2)
    keep = np.ones(len(pts), dtype=bool)
    keep[1:] = np.any(np.diff(pts, axis=0) != 0, axis=1)
    return pts[keep]


def load_roads(path: Path) -> SimpleNamespace:
    """OSM roads clipped to the detail box, simplified, in integer decimetres."""
    rows, geoms = read_layer(path, detail_lonlat_bbox())
    clip = box(DETAIL[0], DETAIL[2], DETAIL[1], DETAIL[3])
    names: dict[tuple[str, str], int] = {}
    pieces = []
    for row, geom in zip(rows, geoms):
        cls = road_class(text_value(row.get("highway")))
        if cls is None or geom is None:
            continue
        tags = parse_tags(text_value(row.get("other_tags")))
        osm_id = int(text_value(row.get("osm_id")) or 0)
        clipped = localise(geom).intersection(clip)
        parts = [g for g in getattr(clipped, "geoms", [clipped]) if isinstance(g, LineString) and not g.is_empty]
        for part_index, part in enumerate(parts):
            pts = clean_line(np.asarray(part.simplify(ROAD_SIMPLIFY_M).coords))
            if len(pts) < 2:
                continue
            name_th, name_en = text_value(row.get("name")) or "", tags.get("name:en", "")
            pieces.append({
                "osm_id": osm_id, "part": part_index, "class": cls, "width_dm": road_width_dm(cls, tags),
                "bridge": tags.get("bridge", "no") not in {"no", ""}, "name": (name_th, name_en), "points": pts,
            })
    pieces.sort(key=lambda p: (p["osm_id"], p["part"]))
    for key in sorted({p["name"] for p in pieces if p["name"] != ("", "")}):
        names[key] = len(names)
    lines = [LineString(p["points"] / 10.0) for p in pieces]
    return SimpleNamespace(pieces=pieces, names=names, lines=lines)


def load_sites(path: Path) -> list[dict[str, Any]]:
    """OSM site polygons (derived multipolygon file) in the local frame, with their kind flags."""
    rows, geoms = read_layer(path, detail_lonlat_bbox(300.0))
    sites = []
    for row, geom in zip(rows, geoms):
        if geom is None or geom.is_empty:
            continue
        amenity, building, office = (text_value(row.get(k)) or "" for k in ("amenity", "building", "office"))
        flags = {
            "temple": amenity in TEMPLE_AMENITY or building in TEMPLE_BUILDING,
            "government": amenity in GOVERNMENT_AMENITY or office == "government" or building in GOVERNMENT_BUILDING,
            "school": amenity in SCHOOL_AMENITY or building in SCHOOL_BUILDING,
            "market": amenity in MARKET_AMENITY,
        }
        way = text_value(row.get("osm_way_id"))
        if not any(flags.values()) and way is None:
            continue
        sites.append({"osm_way_id": int(way) if way else None, "name": text_value(row.get("name")), "flags": flags,
                      "polygon": shapely.make_valid(localise(geom))})
    return sites


def load_land(pbf: Path) -> SimpleNamespace:
    """Water, green and field polygons and waterway lines from the Geofabrik extract, clipped to the detail box."""
    clip = box(DETAIL[0], DETAIL[2], DETAIL[1], DETAIL[3])
    bbox = detail_lonlat_bbox()
    rows, geoms = read_layer(pbf, bbox, layer="multipolygons")
    water, green, field = [], [], []
    for row, geom in zip(rows, geoms):
        if geom is None:
            continue
        tags = parse_tags(text_value(row.get("other_tags")))
        landuse, natural, leisure = (text_value(row.get(k)) or "" for k in ("landuse", "natural", "leisure"))
        target = None
        if natural == "water" or landuse in WATER_LANDUSE or tags.get("waterway") == "riverbank" or "water" in tags:
            target = water
        elif landuse in FIELD_LANDUSE:
            target = field
        elif landuse in GREEN_LANDUSE or natural in GREEN_NATURAL or leisure in GREEN_LEISURE:
            target = green
        if target is None:
            continue
        part = shapely.make_valid(localise(geom)).intersection(clip)
        if not part.is_empty and part.area > 0:
            target.append(part)
    line_rows, line_geoms = read_layer(pbf, bbox, layer="lines")
    waterways, river_lines = [], []
    for row, geom in zip(line_rows, line_geoms):
        kind = text_value(row.get("waterway"))
        if geom is None or kind not in WATERWAY_HALF_WIDTH_M:
            continue
        line = localise(geom)
        band = line.buffer(WATERWAY_HALF_WIDTH_M[kind]).intersection(clip)
        if not band.is_empty:
            waterways.append(band)
        if kind == "river":
            tags = parse_tags(text_value(row.get("other_tags")))
            river_lines.append({"line": line, "name": text_value(row.get("name")), "name_en": tags.get("name:en"),
                                "osm_id": int(text_value(row.get("osm_id")) or 0)})
    return SimpleNamespace(water=water + waterways, green=green, field=field, river_lines=river_lines,
                           water_polygons=len(water), waterway_bands=len(waterways))


# --- Buildings --------------------------------------------------------------------------------------------------------


def polygon_array(buildings: list[dict[str, Any]]) -> np.ndarray:
    """The buildings' polygons as a numpy object array (for vectorised shapely calls)."""
    array = np.empty(len(buildings), dtype=object)
    array[:] = [b["polygon"] for b in buildings]
    return array


def ring_area(points: np.ndarray) -> float:
    """Signed shoelace area of a ring of (n, 2) points (positive counter-clockwise in the x/z plane)."""
    x, z = points[:, 0], points[:, 1]
    return 0.5 * float(np.dot(x, np.roll(z, -1)) - np.dot(z, np.roll(x, -1)))


def load_buildings(path: Path) -> list[dict[str, Any]]:
    """Outlines wholly inside the detail box: simplified, counter-clockwise, in integer decimetres, sorted by z then x."""
    rows, geoms = read_layer(path, detail_lonlat_bbox(0.0))
    out = []
    for row, geom in zip(rows, geoms):
        if geom is None or geom.is_empty:
            continue
        polygons = [g for g in getattr(geom, "geoms", [geom]) if isinstance(g, Polygon)]
        for polygon in polygons:
            raw = Polygon(localise(polygon).exterior)
            bx0, bz0, bx1, bz1 = raw.bounds
            if not (bx0 >= DETAIL[0] and bx1 <= DETAIL[1] and bz0 >= DETAIL[2] and bz1 <= DETAIL[3]):
                continue
            source = text_value(row.get("bf_source")) or "unknown"
            centre = raw.centroid
            ident = f"{source}:{int(round(centre.x * 10))}:{int(round(centre.y * 10))}:{int(round(raw.area * 10))}"
            simple = raw.simplify(BUILDING_SIMPLIFY_M, preserve_topology=True)
            if not isinstance(simple, Polygon) or simple.is_empty:
                continue
            ring = np.asarray(orient(Polygon(simple.exterior), sign=1.0).exterior.coords)[:-1]
            pts = clean_line(ring)
            if len(pts) > 1 and np.all(pts[0] == pts[-1]):
                pts = pts[:-1]
            if len(pts) < 3:
                continue
            area = ring_area(pts / 10.0)
            if area < BUILDING_MIN_AREA_M2:
                continue
            confidence = row.get("confidence")
            conf = -1 if confidence is None or (isinstance(confidence, float) and math.isnan(confidence)) else int(round(float(confidence) * 100))
            out.append({"id": ident, "src": source, "conf": conf, "points": pts, "area": area,
                        "polygon": Polygon(pts / 10.0), "centre_dm": (int(round(centre.x * 10)), int(round(centre.y * 10)))})
    out.sort(key=lambda b: (b["centre_dm"][1], b["centre_dm"][0], b["id"]))
    return out


def classify_buildings(buildings: list[dict[str, Any]], sites: list[dict[str, Any]], roads: SimpleNamespace) -> list[str]:
    """Kind of each building by the deterministic rules of the manifest (``buildings.kind_rules``)."""
    points = shapely.point_on_surface(polygon_array(buildings))

    def inside(flag: str) -> np.ndarray:
        polys = [s["polygon"] for s in sites if s["flags"][flag]]
        hit = np.zeros(len(buildings), dtype=bool)
        if polys:
            pairs = STRtree(polys).query(points, predicate="within")
            hit[np.unique(pairs[0])] = True
        return hit

    temple, government, school, market = (inside(f) for f in ("temple", "government", "school", "market"))
    bands = [line.buffer(SHOPHOUSE_REACH_M + p["width_dm"] / 20.0)
             for line, p in zip(roads.lines, roads.pieces) if p["class"] in MAIN_ROADS]
    near_main = np.zeros(len(buildings), dtype=bool)
    if bands:
        pairs = STRtree(bands).query([b["polygon"] for b in buildings], predicate="intersects")
        near_main[np.unique(pairs[0])] = True
    kinds = []
    for i, b in enumerate(buildings):
        area = b["area"]
        if temple[i]:
            kinds.append("temple")
        elif government[i]:
            kinds.append("government")
        elif school[i]:
            kinds.append("school")
        elif market[i] or area >= 900:
            kinds.append("market")
        elif area < 30:
            kinds.append("shed")
        elif near_main[i]:
            kinds.append("shophouse")
        elif area >= 400:
            kinds.append("large")
        else:
            kinds.append("house")
    return kinds


def front_edges(buildings: list[dict[str, Any]], roads: SimpleNamespace) -> list[int]:
    """For each building, the edge whose outward normal faces the nearest road (the longest of near-ties)."""
    tree = STRtree(roads.lines)
    centres = shapely.centroid(polygon_array(buildings))
    pairs = tree.query_nearest(centres, all_matches=True)
    nearest = np.full(len(buildings), -1, dtype=np.int64)
    for i, j in sorted(zip(pairs[0].tolist(), pairs[1].tolist())):
        if nearest[i] < 0:
            nearest[i] = j
    fronts = []
    for i, b in enumerate(buildings):
        pts = b["points"] / 10.0
        edges = np.roll(pts, -1, axis=0) - pts
        lengths = np.hypot(edges[:, 0], edges[:, 1])
        centre = b["polygon"].centroid
        target = None
        if nearest[i] >= 0:
            line = roads.lines[nearest[i]]
            target = line.interpolate(line.project(centre))
        direction = None if target is None else np.array([target.x - centre.x, target.y - centre.y])
        if direction is None or np.hypot(*direction) < 0.01:
            fronts.append(int(np.argmax(lengths)))
            continue
        direction /= np.hypot(*direction)
        with np.errstate(invalid="ignore", divide="ignore"):
            normals = np.column_stack([edges[:, 1], -edges[:, 0]]) / lengths[:, None]
        score = np.where(lengths > 0, normals @ direction, -2.0)
        ties = np.flatnonzero(score >= score.max() - FRONT_TIE)
        fronts.append(int(ties[np.argmax(lengths[ties])]))
    return fronts


def oriented_box(b: dict[str, Any], front: int) -> tuple[list[int], int]:
    """OBB [cx_dm, cz_dm, w_dm, d_dm, angle_centidegrees] (w along the side nearest the front edge) and rectangularity 0-100."""
    rect = shapely.oriented_envelope(b["polygon"])
    corners = np.asarray(rect.exterior.coords)[:4] if isinstance(rect, Polygon) else np.asarray(b["polygon"].exterior.coords)[:4]
    a, c = corners[1] - corners[0], corners[2] - corners[1]
    pts = b["points"] / 10.0
    edge = pts[(front + 1) % len(pts)] - pts[front]
    unit = edge / max(np.hypot(*edge), 1e-9)
    la, lc = max(np.hypot(*a), 1e-9), max(np.hypot(*c), 1e-9)
    w_vec, d_len = (a, lc) if abs(np.dot(a / la, unit)) >= abs(np.dot(c / lc, unit)) else (c, la)
    angle = math.degrees(math.atan2(w_vec[1], w_vec[0])) % 180.0
    centre = rect.centroid
    w_len = float(np.hypot(*w_vec))
    obb = [int(round(centre.x * 10)), int(round(centre.y * 10)), int(round(w_len * 10)), int(round(d_len * 10)),
           int(round(angle * 100)) % 18000]
    box_area = w_len * d_len
    rectangularity = int(round(min(1.0, b["area"] / box_area) * 100)) if box_area > 0 else 0
    return obb, rectangularity


def nearest_building(buildings: list[dict[str, Any]], x: float, z: float, within: Any = None) -> int | None:
    """Index of the building whose outline holds (x, z), else the nearest one (optionally only those inside ``within``)."""
    point = Point(x, z)
    candidates = range(len(buildings))
    if within is not None:
        inside = [i for i in candidates if within.contains(buildings[i]["polygon"].representative_point())]
        if inside:
            return max(inside, key=lambda i: (buildings[i]["area"], -i))
    best, best_d = None, math.inf
    for i in candidates:
        d = buildings[i]["polygon"].distance(point)
        if d < best_d:
            best, best_d = i, d
    return best


# --- Cover raster and trees ----------------------------------------------------------------------------------------


def cover_raster(land: SimpleNamespace, roads: SimpleNamespace, buildings: list[dict[str, Any]]) -> np.ndarray:
    """4 m class raster over the detail box. Burn order gives the precedence water > building > road > field > green > open."""
    cols = int(round((DETAIL[1] - DETAIL[0]) / COVER_CELL_M))
    rows = int(round((DETAIL[3] - DETAIL[2]) / COVER_CELL_M))
    transform = Affine(COVER_CELL_M, 0.0, DETAIL[0], 0.0, COVER_CELL_M, DETAIL[2])
    road_bands = [line.buffer(max(p["width_dm"] / 20.0, MIN_ROAD_HALF_WIDTH_IN_COVER_M), cap_style="flat")
                  for line, p in zip(roads.lines, roads.pieces)]
    shapes = ([(g, GREEN) for g in land.green] + [(g, FIELD) for g in land.field] + [(g, ROAD) for g in road_bands]
              + [(b["polygon"], BUILDING) for b in buildings] + [(g, WATER) for g in land.water])
    if not shapes:
        return np.zeros((rows, cols), dtype=np.uint8)
    return rasterize(shapes, out_shape=(rows, cols), transform=transform, fill=OPEN, dtype="uint8", all_touched=False)


def plant_trees(cover: np.ndarray, land: SimpleNamespace, roads: SimpleNamespace, buildings: list[dict[str, Any]]) -> SimpleNamespace:
    """Seeded Poisson-disk (dart-throwing) trees on river banks, green, field edges and open ground."""
    rng = np.random.default_rng(TREE_SEED)
    rows, cols = cover.shape
    water_mask = cover == WATER
    distance_to_water = ndimage.distance_transform_edt(~water_mask) * COVER_CELL_M if water_mask.any() else np.full(cover.shape, np.inf)
    field_mask = cover == FIELD
    field_edge = field_mask & ~ndimage.binary_erosion(field_mask, structure=np.ones((3, 3), dtype=bool), border_value=0)
    plantable = (cover == OPEN) | (cover == GREEN) | (cover == FIELD)
    masks = {
        "river_bank": plantable & (distance_to_water <= RIVER_BANK_M),
        "green": cover == GREEN,
        "field_edge": field_edge,
        "open_ground": cover == OPEN,
    }
    road_bands = [line.buffer(max(p["width_dm"] / 20.0, MIN_ROAD_HALF_WIDTH_IN_COVER_M), cap_style="flat")
                  for line, p in zip(roads.lines, roads.pieces)]
    obstacles = STRtree([b["polygon"] for b in buildings] + road_bands)
    cell = 16.0
    by_pass = {name: 0 for name, *_ in TREE_PASSES}
    buckets: dict[tuple[int, int], list[tuple[float, float]]] = {}
    accepted: list[tuple[float, float, int, int]] = []
    for name, spacing, density, cap, weights in TREE_PASSES:
        mask = masks[name]
        cells = np.flatnonzero(mask)
        if cells.size == 0 or len(accepted) >= TREE_MAX:
            continue
        area = cells.size * COVER_CELL_M ** 2
        count = int(math.ceil(area / (math.pi * spacing ** 2) * density))
        pick = cells[rng.integers(0, cells.size, size=count)]
        jitter = rng.random((count, 2))
        xs = DETAIL[0] + ((pick % cols) + jitter[:, 0]) * COVER_CELL_M
        zs = DETAIL[2] + ((pick // cols) + jitter[:, 1]) * COVER_CELL_M
        kinds = rng.choice(len(TREE_KINDS), size=count, p=np.asarray(weights) / sum(weights))
        scales = rng.integers(75, 126, size=count)
        blocked = np.zeros(count, dtype=bool)
        pairs = obstacles.query(shapely.points(xs, zs), predicate="dwithin", distance=TREE_CLEARANCE_M)
        blocked[np.unique(pairs[0])] = True
        for x, z, kind, scale, bad in zip(xs, zs, kinds, scales, blocked):
            if bad or len(accepted) >= TREE_MAX or by_pass[name] >= cap:
                continue
            gx, gz = int(math.floor(x / cell)), int(math.floor(z / cell))
            reach = int(math.ceil(spacing / cell))
            clash = False
            for ix in range(gx - reach, gx + reach + 1):
                for iz in range(gz - reach, gz + reach + 1):
                    for px, pz in buckets.get((ix, iz), ()):
                        if (px - x) ** 2 + (pz - z) ** 2 < spacing ** 2:
                            clash = True
                            break
                    if clash:
                        break
                if clash:
                    break
            if clash:
                continue
            buckets.setdefault((gx, gz), []).append((float(x), float(z)))
            accepted.append((float(x), float(z), int(kind), int(scale)))
            by_pass[name] += 1
    pts = np.array([[a[0], a[1]] for a in accepted]) if accepted else np.zeros((0, 2))
    coords = dm(pts) if len(pts) else np.zeros((0, 2), dtype=np.int64)
    order = np.lexsort((coords[:, 0], coords[:, 1])) if len(coords) else np.zeros(0, dtype=np.int64)
    return SimpleNamespace(coords=coords[order], kind=[accepted[i][2] for i in order], scale=[accepted[i][3] for i in order],
                           masks={k: int(v.sum()) for k, v in masks.items()}, by_pass=by_pass)


# --- Walking network ----------------------------------------------------------------------------------------------------


def load_network(path: Path, replay: SimpleNamespace) -> SimpleNamespace:
    """The replay's walking network with lengths in the local frame and closure stages on the r5 cells."""
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    ids = sorted({r["from_node"] for r in rows} | {r["to_node"] for r in rows})
    index = {node: i for i, node in enumerate(ids)}
    lonlat = np.array([evac.node_lonlat(node) for node in ids])
    x, z = to_local(lonlat[:, 0], lonlat[:, 1])
    u = np.array([index[r["from_node"]] for r in rows], dtype=np.int64)
    v = np.array([index[r["to_node"]] for r in rows], dtype=np.int64)
    length = np.hypot(x[v] - x[u], z[v] - z[u])
    grid: HandGrid = replay.grid
    codes = replay.rgb[..., 0]
    kgrid = replay.rgb[..., 1].astype(np.float64) / 255 * replay.scale
    # sample_road reads cells as floor(x / res) and floor(-y / res): fractional columns and negated fractional rows
    # on a unit grid give the r5 Web Mercator cells exactly.
    unit = SimpleNamespace(bounds=(0.0, -float(grid.height), float(grid.width), 0.0), res=1.0, width=grid.width, height=grid.height)
    close = np.empty(len(rows))
    for i, (a, b) in enumerate(zip(u, v)):
        steps = np.linspace(0.0, 1.0, max(2, int(length[i] // 10) + 2))
        lon = lonlat[a, 0] + steps * (lonlat[b, 0] - lonlat[a, 0])
        lat = lonlat[a, 1] + steps * (lonlat[b, 1] - lonlat[a, 1])
        col, row = grid.fractional(lon, lat)
        h, k = evac.sample_road(codes, kgrid, unit, col, -row)
        close[i] = closure_stage(h, k, IMPASSABLE_DEPTH_M)
    adjacency: list[list[tuple[int, int]]] = [[] for _ in ids]
    for e, (a, b) in enumerate(zip(u.tolist(), v.tolist())):
        adjacency[a].append((b, e))
        adjacency[b].append((a, e))
    return SimpleNamespace(ids=ids, lonlat=lonlat, x=x, z=z, u=u, v=v, length=length, close=close, adjacency=adjacency)


def walk(network: SimpleNamespace, source: int, stage: float, limit: float = WALK_LIMIT_M) -> tuple[dict[int, float], dict[int, tuple[int, int]]]:
    """Dijkstra over edges still open at ``stage`` (closure above the stage), up to ``limit`` metres."""
    dist = {source: 0.0}
    pred: dict[int, tuple[int, int]] = {}
    heap = [(0.0, source)]
    done: set[int] = set()
    while heap:
        d, n = heapq.heappop(heap)
        if n in done:
            continue
        done.add(n)
        for m, e in network.adjacency[n]:
            if not network.close[e] > stage:
                continue
            nd = d + float(network.length[e])
            if nd <= limit + 1e-9 and nd < dist.get(m, math.inf):
                dist[m] = nd
                pred[m] = (n, e)
                heapq.heappush(heap, (nd, m))
    return dist, pred


def nearest_node(network: SimpleNamespace, x: float, z: float) -> tuple[int, float]:
    """Index of the network node nearest (x, z) and its distance (m); ties go to the lower index."""
    d = np.hypot(network.x - x, network.z - z)
    i = int(np.argmin(d))
    return i, float(d[i])


def trace(network: SimpleNamespace, pred: dict[int, tuple[int, int]], source: int, target: int) -> tuple[list[int], list[int]]:
    """Nodes and edges of the path from ``source`` to ``target``."""
    nodes, edges = [target], []
    while nodes[-1] != source:
        n, e = pred[nodes[-1]]
        nodes.append(n)
        edges.append(e)
    return nodes[::-1], edges[::-1]


def best_walk(network: SimpleNamespace, home: int, shelters: list[dict[str, Any]], stage: float) -> dict[str, Any] | None:
    """The shortest walk still open at ``stage`` to any in-set reported shelter within the limit, or None."""
    dist, pred = walk(network, home, stage)
    options = sorted((dist[s["node"]], s["id"]) for s in shelters if s["node"] in dist)
    if not options:
        return None
    length, shelter_id = options[0]
    shelter = next(s for s in shelters if s["id"] == shelter_id)
    nodes, edges = trace(network, pred, home, shelter["node"])
    return {"destination": shelter_id, "length_m": length, "nodes": nodes, "edges": edges, "shelter": shelter}


def path_points(network: SimpleNamespace, path: dict[str, Any]) -> np.ndarray:
    """Points of a walk in metres: the home point, the network nodes, the shelter point."""
    nodes = path["nodes"]
    return np.vstack([[0.0, 0.0], np.column_stack([network.x[nodes], network.z[nodes]]), [path["shelter"]["x"], path["shelter"]["z"]]])


def polyline_length(points: np.ndarray) -> float:
    """Length (m) of a polyline."""
    return float(np.hypot(*np.diff(points, axis=0).T).sum()) if len(points) > 1 else 0.0


# --- Practice scenarios -------------------------------------------------------------------------------------------------


PRACTICE_HOMES = {"dry": (20.44042, 99.88718), "flooded": (20.44126, 99.88662)}
"""``PRACTICE_HOMES`` of ``public-practice-scenarios.ts`` as (latitude, longitude); the dry home is the frame origin."""
PRACTICE_SCENARIOS = (
    {"id": "normal", "home": "dry", "hour": 12},
    {"id": "heads_up", "home": "dry", "hour": 40},
    {"id": "roads_cut", "home": "dry", "hour": 46},
    {"id": "reach_at_risk", "home": "dry", "hour": 48},
    {"id": "cut_off", "home": "dry", "hour": 84},
    {"id": "water_at_home", "home": "flooded", "hour": 84},
    {"id": "going_down", "home": "dry", "hour": 132},
)
"""``PRACTICE_SCENARIOS`` of ``public-practice-scenarios.ts`` in menu order (a test compares the two)."""


def practice_constants() -> SimpleNamespace:
    """The practice homes and scenarios; stops when the dry home is not the frame origin."""
    if PRACTICE_HOMES["dry"] != (ORIGIN_LAT, ORIGIN_LON):
        raise RuntimeError("the dry practice home is not the frame origin")
    return SimpleNamespace(homes=dict(PRACTICE_HOMES), scenarios=[dict(s) for s in PRACTICE_SCENARIOS])


# --- Manifest text ------------------------------------------------------------------------------------------------------

PURPOSE = ("The real map of Mae Sai town for the /journey/ story: open building outlines, OpenStreetMap roads and water, "
           "Copernicus relief and the water of the published September 2024 replay (r5) at the hours of the story. "
           "For preparedness learning; the people of the story are fictional.")

CREDITS = {
    "en": ("Building outlines: Google Open Buildings v3 (CC BY 4.0) and Microsoft building footprints (ODbL), combined by "
           "VIDA (Source Cooperative). Roads, water and land use © OpenStreetMap contributors (ODbL). Terrain: Copernicus "
           "DEM GLO-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the "
           "European Union and ESA. Water: FloodGuard replay r5, a model reconstruction of September 2024, low confidence."),
    "th": ("ขอบเขตอาคาร: Google Open Buildings v3 (CC BY 4.0) และ Microsoft building footprints (ODbL) รวมชุดข้อมูลโดย "
           "VIDA (Source Cooperative) · ถนน แหล่งน้ำ และการใช้ที่ดิน © ผู้ร่วมสร้าง OpenStreetMap (ODbL) · "
           "ภูมิประเทศ: Copernicus DEM GLO-30 © DLR e.V. 2010-2014 และ © Airbus Defence and Space GmbH 2014-2018 "
           "ให้บริการภายใต้โครงการ COPERNICUS โดยสหภาพยุโรปและ ESA · น้ำ: การจำลองย้อนหลังของ FloodGuard รุ่น r5 "
           "ซึ่งสร้างขึ้นใหม่ด้วยแบบจำลองสำหรับเดือนกันยายน 2567 (2024) มีความเชื่อมั่นต่ำ"),
}

CONFIDENCE_EXTRA = ("Building outlines were drawn by a model on satellite images of earlier years, not surveyed; building "
                    "heights, floors, facades and trees are illustrative.")

ASSUMPTIONS = [
    "The water is the published replay r5: a HAND (height above nearest drainage) reconstruction driven by illustrative "
    "stage keyframes. A cell is wet when the stage is above code x 0.05 m; its depth is k x (stage - code x 0.05). It is a "
    "model, not an observation.",
    "Beat stages are numpy.interp of the r5 stage anchors at hour / 24 (the same values as the app's stageAt); hour 0 is "
    "9 Sep 2024 00:00 ICT.",
    "The local frame is equirectangular at the example home with the constants of groundDistanceM (111320 x cos(20.44042 deg) "
    "m per degree of longitude, 110540 m per degree of latitude); x east, z south, y up.",
    "The r5 cells are linear in Web Mercator rows over the manifest's rounded bounds; the affine of the cropped cell centres "
    "is a straight-line fit whose largest error is recorded (cells.max_affine_error_m).",
    "Relief of never-flooding cells is the Copernicus DSM (it includes buildings and trees) minus one drainage datum, the "
    "median of DSM - k x code x 0.05 over the floodable cells of the detail box, clamped to at least 12.8 m so it stays "
    "above the highest floodable cell. Heights are for the scene, not survey levels.",
    "Cover classes come from OpenStreetMap: water (water polygons and river, canal and stream lines at 20, 6 and 4 m), "
    "roads (centrelines at their width, at least one 4 m cell wide), buildings (the simplified outlines), green and field "
    "land use. Precedence: water > building > road > field > green > open ground. Unmapped land reads as open ground.",
    "Outlines are simplified by 0.35 m (topology kept); slivers under 8 m2 and outlines crossing the box edge are dropped. "
    "Kinds follow fixed rules on OpenStreetMap sites, size and distance to main roads; floors come from a hash of the "
    "outline: both are illustrative.",
    "Trees are placed by a seeded Poisson-disk sampler (seed 20240909) on river banks, green land, field edges and open "
    "ground, at least 2.5 m from buildings and roads: an illustration, not a tree inventory.",
    "The usual walk follows the replay's walking network (outputs/mae_sai_access_edges.csv) from the network node nearest "
    "the home to the nearest reported shelter of the reported_2024 set within 2 km. An edge closes at the replay's road "
    "rule (sample_road and closure_stage: 10 m samples on the r5 cells, impassable at 0.3 m, channel and never-flood "
    "samples ignored); shelters are assumed open for the whole replay. The replay's access sets also drop a shelter once "
    "its own site floods; the shelters reachable from the home here never do.",
    "Reported sites come from the replay's compiled list of public reporting (not an official register).",
]

LIMITATIONS = [
    "Not a real-time product or an official warning; for preparedness learning only.",
    "The September 2024 water is a model reconstruction with low confidence: onset and peak extents were not observed.",
    "Building outlines are model-drawn from images of earlier years: buildings may be missing, merged or no longer there.",
    "The outline file covers Thailand only: north of the Sai River (Tachileik, Myanmar) the pack has OpenStreetMap roads but no buildings.",
    "OpenStreetMap land use is sparse in Mae Sai: most fields, orchards and wooded hills are not mapped and read as open ground.",
    "The terrain model is a surface model at 30 m: in town it is biased up by buildings and trees.",
    "The replay's drainage lines (cells of HAND 0, from the 30 m surface model) run about 100 to 150 m south of the mapped "
    "Sai River through town (median 115 m from OpenStreetMap water): the replay's water rises from the model's lines, "
    "while the river at a dry hour is drawn from OpenStreetMap.",
    "Building outlines overlap where the source does (about 2,600 pairs by more than 1 m2), so some drawn buildings meet "
    "or cross.",
    "The walk closures here are read on the 15 m r5 cells; the Public app's cut level comes from the replay's own 10 m grid. "
    "They agree within the tolerance recorded in route.app.",
    "No ponding after the river falls: the replay dries every cell as soon as the assumed river level drops below it.",
    "The homes are model points of the replay's resident grid, not addresses; the people of the story are fictional.",
    "The Thai text of this pack was written and checked by the assistant; it has not been reviewed by a native speaker.",
]


def sources(replay: SimpleNamespace) -> list[dict[str, str]]:
    """The manifest's source list (id, name, licence, attribution, timestamp)."""
    return [
        {"id": "open-buildings", "name": "Google-Microsoft Open Buildings, combined by VIDA (Source Cooperative), Thailand",
         "licence": "Google Open Buildings v3: CC BY 4.0 and ODbL 1.0; Microsoft building footprints: ODbL 1.0",
         "attribution": "Building outlines: Google Open Buildings v3 (CC BY 4.0) and Microsoft building footprints (ODbL), combined by VIDA and hosted by Source Cooperative",
         "timestamp": "country file of 2024-08-26 (Last-Modified 26 Aug 2024 19:32:27 GMT); outlines drawn on images of earlier years"},
        {"id": "osm", "name": "OpenStreetMap roads, sites, land use and waterways (Geofabrik extract and the derived Mae Sai files)",
         "licence": "ODbL 1.0", "attribution": "© OpenStreetMap contributors", "timestamp": "2026-07-09"},
        {"id": "copernicus-dem", "name": "Copernicus DEM GLO-30 (tile N20 E099)",
         "licence": "Copernicus DEM licence (free, attribution)",
         "attribution": "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA",
         "timestamp": "2021 release (DSM from 2011-2015 acquisitions)"},
        {"id": "replay-r5", "name": f"FloodGuard replay {replay.timeline['revision']} ({replay.timeline['study_id']})",
         "licence": "FloodGuard project data; its OpenStreetMap-derived parts ODbL 1.0",
         "attribution": "FloodGuard replay r5, a model reconstruction of September 2024, low confidence",
         "timestamp": replay.timeline["source_timestamp"]},
        {"id": "reported-sites", "name": "Shelters and relief sites reported in use in September 2024 (FloodGuard desk research)",
         "licence": "Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)",
         "attribution": "FloodGuard desk research of public reporting; sources linked per site in the replay",
         "timestamp": f"compiled {replay.timeline['shelters']['reported_compiled']}"},
    ]


LICENCE_NOTES = [
    "The building outlines, roads and cover raster of this pack are a derivative database of OpenStreetMap and of the open "
    "building outlines, published under the Open Database License 1.0 with the credit above.",
    "Google Open Buildings v3 outlines are credited under CC BY 4.0 as the provider states; Microsoft building footprints "
    "are under ODbL 1.0.",
    "Relief from the Copernicus DEM GLO-30 carries the Copernicus credit.",
    "This is an engineering note on the right to use, not a legal clearance.",
]


def licence_text(manifest_credit: dict[str, str]) -> str:
    """The pack's LICENSE.txt."""
    lines = [
        "FloodGuard journey town pack (apps/web/public/journey/town/)",
        "Baked by scripts/build_journey_town.py on branch journey-v2.",
        "",
        "Credits",
        "-------",
        manifest_credit["en"],
        "",
        manifest_credit["th"],
        "",
        "Licences",
        "--------",
        "* Derivative database: the building outlines, roads and land cover in mae-sai-town.json and",
        "  mae-sai-town-cover.png are a derivative database of OpenStreetMap (ODbL 1.0) and of the open building",
        "  outlines of Google Open Buildings v3 (CC BY 4.0 and ODbL 1.0) and Microsoft building footprints (ODbL 1.0),",
        "  combined by VIDA and hosted by Source Cooperative. This pack publishes it under the Open Database License 1.0:",
        "  https://opendatacommons.org/licenses/odbl/1-0/ . Keep the credit; share changes to the database alike.",
        "* OpenStreetMap: © OpenStreetMap contributors, https://www.openstreetmap.org/copyright",
        "* Google Open Buildings v3: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/",
        "* Copernicus DEM GLO-30 (relief and backdrop): © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH",
        "  2014-2018, provided under COPERNICUS by the European Union and ESA; all rights reserved.",
        "* Water, beats and walk: FloodGuard replay r5 (apps/web/public/studies/mae-sai-2024-timeline/r5/), a model",
        "  reconstruction of September 2024 with low confidence; its OpenStreetMap-derived parts are under ODbL 1.0.",
        "",
        "What this is not",
        "----------------",
        "Not an observation, a real-time product or an official warning. Building heights, floors, facades and trees",
        "are illustrative. The people of the story are fictional; the example homes are model points, not addresses.",
        "",
        "This is an engineering note on the right to use, not a legal clearance.",
    ]
    return "\n".join(lines) + "\n"


# --- The bake -----------------------------------------------------------------------------------------------------------


def png_bytes(array: np.ndarray, mode: str) -> bytes:
    """Encode an array as PNG with fixed settings (no metadata)."""
    import io

    buffer = io.BytesIO()
    Image.fromarray(array, mode).save(buffer, format="PNG", compress_level=9)
    return buffer.getvalue()


def file_entry(name: str, data: bytes) -> dict[str, Any]:
    """href, SHA-256 and size of one output file."""
    return {"href": HREF_PREFIX + name, "sha256": sha256_bytes(data), "bytes": len(data)}


def check_extent(label: str, xs: Any, zs: Any, extent: tuple[float, float, float, float] = DETAIL) -> None:
    """Stop when any coordinate (metres) of ``label`` lies outside ``extent``."""
    xs, zs = np.asarray(xs, dtype=float), np.asarray(zs, dtype=float)
    x0, x1, z0, z1 = extent
    if xs.size and (xs.min() < x0 or xs.max() > x1 or zs.min() < z0 or zs.max() > z1):
        raise AssertionError(f"{label}: a coordinate falls outside its extent")


def place_cell(replay: SimpleNamespace, x: float, z: float) -> dict[str, Any]:
    """r5 cell (row, column, code, k) at a local point."""
    lon, lat = to_lonlat(x, z)
    row, col = (int(v) for v in replay.grid.cell(lon, lat))
    code, factor = int(replay.rgb[row, col, 0]), int(replay.rgb[row, col, 1])
    return {"row": row, "col": col, "code": code, "factor_byte": factor, "k": round(factor / 255 * replay.scale, 4)}


def first_sentence(text: str | None) -> str | None:
    """The first sentence of ``text``."""
    if not text:
        return None
    match = re.match(r"(.+?\.)(\s|$)", text.strip())
    return match.group(1) if match else text.strip()


def build_places(replay: SimpleNamespace, practice: SimpleNamespace, sites: list[dict[str, Any]], land: SimpleNamespace) -> tuple[list[dict[str, Any]], list[Any]]:
    """Places (homes, reported sites inside the box, the Sai River label) and the OSM polygon of each (or None)."""
    places: list[dict[str, Any]] = []
    polygons: list[Any] = []
    flooded_lat, flooded_lon = practice.homes["flooded"]
    nx, nz = (float(v) for v in to_local(flooded_lon, flooded_lat))
    places.append({"id": "home", "kind": "example_home", "practice_home": "dry", "x": 0.0, "z": 0.0,
                   "name": {"en": "Example home (stays dry)", "th": "บ้านตัวอย่าง (น้ำไม่ท่วม)"},
                   "cell": place_cell(replay, 0.0, 0.0),
                   "notes": {"en": "The Public app's dry example home: a point of the replay's resident grid, not an address.",
                             "th": "บ้านตัวอย่างที่น้ำไม่ท่วมของแอปสำหรับประชาชน เป็นจุดหนึ่งในตารางผู้อยู่อาศัยของการจำลองย้อนหลัง ไม่ใช่ที่อยู่จริง"}})
    polygons.append(None)
    places.append({"id": "neighbour", "kind": "example_home", "practice_home": "flooded", "x": round(nx, 2), "z": round(nz, 2),
                   "name": {"en": "Example neighbour (floods)", "th": "บ้านใกล้เคียงตัวอย่าง (น้ำท่วมถึง)"},
                   "cell": place_cell(replay, nx, nz),
                   "notes": {"en": "The Public app's flooded example home, about 110 m from the dry one: a model point, not an address.",
                             "th": "บ้านตัวอย่างที่น้ำท่วมถึงของแอปสำหรับประชาชน ห่างจากบ้านที่น้ำไม่ท่วมราว 110 เมตร เป็นจุดของแบบจำลอง ไม่ใช่ที่อยู่จริง"}})
    polygons.append(None)
    by_way = {s["osm_way_id"]: s for s in sites if s["osm_way_id"] is not None}
    for record in sorted(replay.timeline["shelters"]["reported"], key=lambda r: r["id"]):
        if record.get("lat") is None or record.get("lon") is None:
            continue
        x, z = (float(v) for v in to_local(record["lon"], record["lat"]))
        if not bool(inside_detail(x, z)):
            continue
        way_match = re.search(r"OSM way (\d+)", record.get("location_evidence") or "")
        way = int(way_match.group(1)) if way_match else None
        cell = place_cell(replay, x, z)
        place = {"id": record["id"], "kind": "reported_site", "role": record.get("role"), "x": round(x, 2), "z": round(z, 2),
                 "name": {"en": record.get("name_en"), "th": record.get("name_th")}, "cell": cell,
                 "in_access_set": bool(record.get("in_access_set")), "first_use": record.get("first_use"),
                 "location_confidence": record.get("location_confidence"), "osm_way": way,
                 "notes": {"en": record.get("access_set_note"), "th": record.get("access_set_note_th")},
                 "period": {"en": first_sentence(record.get("period_used"))}}
        if record["id"] == "R04":
            peak = max(replay.anchors_stage)
            dry_at_peak = cell_depth(cell["code"], peak, cell["factor_byte"], replay.scale) is None
            place["model_vs_report"] = {
                "reported": "The temple was itself flooded and evacuated around 11-12 Sep 2024; it served as a shelter from 21 Sep 2024.",
                "reported_th": "มีรายงานว่าวัดถูกน้ำท่วมและต้องอพยพราววันที่ 11-12 ก.ย. 2567 (2024) แล้วจึงใช้เป็นที่พักพิงตั้งแต่ 21 ก.ย.",
                "model_cell_code": cell["code"], "model_dry_at_peak": dry_at_peak,
                "reading": "Model and reports disagree here: an example of what still needs checking. Not a shelter in the story.",
                "reading_th": "แบบจำลองกับรายงานไม่ตรงกันที่จุดนี้ จึงเป็นตัวอย่างของสิ่งที่ยังต้องตรวจสอบ และไม่ใช่ที่พักพิงในเรื่อง"}
        places.append(place)
        polygons.append(by_way[way]["polygon"] if way in by_way else None)
    bridge_x, bridge_z = (float(v) for v in to_local(*SAI_BRIDGE_LONLAT))
    clip = box(DETAIL[0], DETAIL[2], DETAIL[1], DETAIL[3])
    best = None
    for river in sorted(land.river_lines, key=lambda r: r["osm_id"]):
        part = river["line"].intersection(clip)
        if part.is_empty:
            continue
        point = part.interpolate(part.project(Point(bridge_x, bridge_z))) if isinstance(part, LineString) else \
            min((g.interpolate(g.project(Point(bridge_x, bridge_z))) for g in part.geoms if isinstance(g, LineString)),
                key=lambda p: p.distance(Point(bridge_x, bridge_z)))
        d = point.distance(Point(bridge_x, bridge_z))
        if best is None or d < best[0]:
            best = (d, point, river)
    if best is None:
        raise RuntimeError("no OSM river line crosses the detail box")
    _, point, river = best
    places.append({"id": "sai_river", "kind": "river_label", "x": round(point.x, 2), "z": round(point.y, 2),
                   "name": {"en": river["name_en"] or "Sai River", "th": river["name"] or "แม่น้ำสาย"},
                   "name_source": "OpenStreetMap" if river["name"] else "FloodGuard label",
                   "cell": place_cell(replay, point.x, point.y),
                   "notes": {"en": "The Sai River, the border with Myanmar; the label sits on the OSM river line nearest the Mae Sai border bridges.",
                             "th": "แม่น้ำสาย เส้นพรมแดนกับเมียนมา ป้ายชื่อวางบนเส้นแม่น้ำของ OSM ที่ใกล้สะพานข้ามพรมแดนแม่สายที่สุด"}})
    polygons.append(None)
    return places, polygons


def app_block(replay: SimpleNamespace) -> dict[str, Any]:
    """The Public app's figures for the dry home: nearest access node, its codes and the reported-set cut level."""
    access = replay.timeline["access"]
    count = int(access["nodes"]["count"])
    layout = {item["name"]: item for item in access["nodes"]["layout"]}
    raw = replay.nodes
    lon = np.frombuffer(raw, "<f4", count, layout["lon"]["offset"]).astype(np.float64)
    lat = np.frombuffer(raw, "<f4", count, layout["lat"]["offset"]).astype(np.float64)
    east = (lon - ORIGIN_LON) * 111320 * math.cos(math.radians(ORIGIN_LAT))
    north = (lat - ORIGIN_LAT) * 110540
    distance = np.hypot(east, north)
    node = int(np.argmin(distance))
    if distance[node] > APP_NODE_REACH_M:
        raise AssertionError("no access node of the replay lies within 150 m of the dry home")
    sets = list(access["sets"])
    set_index = sets.index(REPORTED_SET_ID)
    shape = layout["cut_codes"]["shape"]
    cut = np.frombuffer(raw, "u1", shape[0] * shape[1], layout["cut_codes"]["offset"]).reshape(shape)
    cut_code = int(cut[set_index, node])
    levels = access["levels"]
    level = float(levels[cut_code]) if cut_code < len(levels) else None
    return {"node_index": node, "lon": float(lon[node]), "lat": float(lat[node]), "distance_m": round(float(distance[node]), 2),
            "home_code": int(np.frombuffer(raw, "u1", count, layout["home_code"]["offset"])[node]),
            "home_k_byte": int(np.frombuffer(raw, "u1", count, layout["home_k"]["offset"])[node]),
            "home_k_note": "home_k is the depth factor x 255 (unscaled, clipped to 1..255), not the hand PNG's byte scale of 2.5.",
            "set_id": REPORTED_SET_ID, "set_index": set_index, "cut_code": cut_code, "cut_level_m": level,
            "rule": "nearestAccessNode (within 150 m, groundDistanceM) of apps/web/src/lib/public-practice.ts; cut code indexes access.levels"}


def bake(external: Path, out_dir: Path, generated_at: str) -> tuple[dict[str, Any], InputReceipt, SimpleNamespace]:
    """Run the whole bake into ``out_dir``; return the manifest, the input receipt and a summary for the console."""
    receipt = InputReceipt({"external": external, "repo": ROOT})
    track = receipt.track
    replay = load_replay(track)
    practice = practice_constants()
    outlines_record = json.loads(Path(track(ROOT / OUTLINES_RECORD_REL)).read_text(encoding="utf-8"))
    outlines_path = Path(track(external / OUTLINES_EXT))
    recorded_sha = outlines_record["areas"]["mae_sai"]["file_outside_git"]["sha256"]
    if receipt_sha(receipt, outlines_path) != recorded_sha:
        raise RuntimeError("mae_sai_outlines.gpkg differs from the file recorded in outputs/buildings_in_water/outlines_v1.json")

    cells = crop_cells(replay)
    heights = relief_and_backdrop(cells, replay, Path(track(external / DEM_EXT)))
    roads = load_roads(Path(track(external / ROADS_EXT)))
    sites = load_sites(Path(track(external / SITES_EXT)))
    land = load_land(Path(track(external / PBF_EXT)))
    buildings = load_buildings(outlines_path)
    kinds = classify_buildings(buildings, sites, roads)
    fronts = front_edges(buildings, roads)
    cover = cover_raster(land, roads, buildings)
    trees = plant_trees(cover, land, roads, buildings)
    places, place_polygons = build_places(replay, practice, sites, land)

    # Buildings: arrays, compounds and the named outlines.
    reps = shapely.point_on_surface(polygon_array(buildings))
    compound = np.full(len(buildings), -1, dtype=np.int64)
    for place_index, polygon in enumerate(place_polygons):
        if polygon is None:
            continue
        hit = shapely.contains(polygon, reps)
        compound[(compound < 0) & hit] = place_index
    ring_start, coords, obbs, rects = [0], [], [], []
    for b, front in zip(buildings, fronts):
        coords.extend(delta_encode(b["points"]))
        ring_start.append(ring_start[-1] + len(b["points"]))
        obb, rect = oriented_box(b, front)
        obbs.extend(obb)
        rects.append(rect)
    all_pts = np.vstack([b["points"] for b in buildings]) / 10.0 if buildings else np.zeros((0, 2))
    check_extent("buildings", all_pts[:, 0], all_pts[:, 1])
    place_index = {p["id"]: i for i, p in enumerate(places)}
    home_building = nearest_building(buildings, 0.0, 0.0)
    neighbour = places[place_index["neighbour"]]
    neighbour_building = nearest_building(buildings, neighbour["x"], neighbour["z"])
    named = {}
    for key, pid in (("district_office", "R05"), ("municipality_office", "R01")):
        if pid in place_index:
            p = places[place_index[pid]]
            named[key] = nearest_building(buildings, p["x"], p["z"], place_polygons[place_index[pid]])
        else:
            named[key] = None

    # The walk.
    network = load_network(Path(track(ROOT / EDGES_REL)), replay)
    home_node, home_offset = nearest_node(network, 0.0, 0.0)
    shelters = []
    for record in sorted(replay.timeline["shelters"]["reported"], key=lambda r: r["id"]):
        if record.get("in_access_set") and record.get("lat") is not None:
            x, z = (float(v) for v in to_local(record["lon"], record["lat"]))
            node, offset = nearest_node(network, x, z)
            shelters.append({"id": record["id"], "x": x, "z": z, "node": node, "snap_m": offset})
    usual = best_walk(network, home_node, shelters, 0.0)
    if usual is None:
        raise AssertionError("no reported shelter of the access set lies within 2 km of the home at stage 0")
    usual_points = path_points(network, usual)
    edge_close = [float(network.close[e]) for e in usual["edges"]]
    cut_stage = min(edge_close)
    first = int(np.argmin(edge_close))
    along = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(usual_points, axis=0).T))])
    app = app_block(replay)
    if app["cut_level_m"] is None or abs(cut_stage - app["cut_level_m"]) > CUT_TOLERANCE_M:
        raise AssertionError(f"the walk's cut stage {cut_stage} differs from the app's cut level {app['cut_level_m']} by more than {CUT_TOLERANCE_M} m")
    check_extent("route", usual_points[:, 0], usual_points[:, 1])
    route = {
        "rule": "Shortest walk on the replay's network at stage 0 from the node nearest the home to the nearest reported "
                "shelter of the reported_2024 set within 2 km. An edge is open while the stage is below its closure stage.",
        "network": EDGES_REL.as_posix(),
        "from": {"node": network.ids[home_node], "offset_m": round(home_offset, 2)},
        "destination": usual["destination"],
        "destination_node": network.ids[usual["shelter"]["node"]],
        "destination_snap_m": round(usual["shelter"]["snap_m"], 2),
        "length_m": round(usual["length_m"], 1),
        "drawn_length_m": round(polyline_length(usual_points), 1),
        "points": delta_encode(dm(usual_points)),
        "edges": [[i + 1, i + 2, round_or_none(c, 4)] for i, c in enumerate(edge_close)],
        "cut_stage_m": round(cut_stage, 4),
        "first_cut": {"edge": first, "along_m": [round(float(along[first + 1]), 1), round(float(along[first + 2]), 1)],
                      "x": round(float(usual_points[first + 1, 0]), 1), "z": round(float(usual_points[first + 1, 1]), 1),
                      "closure_stage_m": round(edge_close[first], 4)},
        "closure_rule": "closure_stage(sample_road(...)) of floodguard.evacuation_access and scripts/mae_sai_timeline_evacuation.py "
                        "on samples every 10 m along the edge, read on the r5 cells: the stage at which the depth k x (stage - "
                        "code x 0.05) first reaches 0.3 m at a usable sample (channel and never-flood samples ignored).",
        "app": app,
    }

    # Beats.
    home_cell = places[place_index["home"]]["cell"]
    neighbour_cell = neighbour["cell"]
    near = np.hypot(cells.x, cells.z) <= WET_SHARE_RADIUS_M
    beats = []
    for hour in BEAT_HOURS:
        stage = stage_at_hour(replay, hour)
        home_depth = cell_depth(home_cell["code"], stage, home_cell["factor_byte"], replay.scale)
        neighbour_depth = cell_depth(neighbour_cell["code"], stage, neighbour_cell["factor_byte"], replay.scale)
        k = cells.factor[near] / 255 * replay.scale
        code = cells.code[near]
        depth = np.where(code == CHANNEL_CODE, k * max(0.0, stage),
                         np.where((code != NEVER_CODE) & (code * HAND_STEP_M < stage), k * (stage - code * HAND_STEP_M), 0.0))
        best = best_walk(network, home_node, shelters, stage)
        best_block = None
        if best is not None:
            pts = path_points(network, best)
            check_extent(f"best walk at hour {hour}", pts[:, 0], pts[:, 1])
            best_block = {"destination": best["destination"], "length_m": round(best["length_m"], 1),
                          "points": delta_encode(dm(pts))}
        if home_depth is not None:
            raise AssertionError(f"the dry home is wet at hour {hour}")
        beats.append({
            "hour": hour, "t": hour / 24, "stage_m": stage,
            "time_local": (REPLAY_EPOCH + timedelta(hours=hour)).isoformat(),
            "practice": [{"id": s["id"], "home": s["home"]} for s in practice.scenarios if s["hour"] == hour],
            "home_depth_m": None if home_depth is None else round(home_depth, 4),
            "neighbour_depth_m": None if neighbour_depth is None else round(neighbour_depth, 4),
            "wet_share_450m": round(float(np.count_nonzero(depth > 0)) / int(near.sum()), 4),
            "route_open": bool(cut_stage > stage),
            "best_path": best_block,
        })
    by_hour = {b["hour"]: b for b in beats}
    if by_hour[84]["neighbour_depth_m"] is None:
        raise AssertionError("the flooded neighbour is dry at hour 84")
    if not by_hour[48]["route_open"]:
        raise AssertionError("the usual walk is closed at hour 48")
    if by_hour[84]["route_open"]:
        raise AssertionError("the usual walk is open at hour 84")

    # Trees and places in extent.
    tree_m = trees.coords / 10.0
    check_extent("trees", tree_m[:, 0], tree_m[:, 1])
    check_extent("places", [p["x"] for p in places], [p["z"] for p in places])
    road_pts = np.vstack([p["points"] for p in roads.pieces]) / 10.0
    check_extent("roads", road_pts[:, 0], road_pts[:, 1])

    # Files.
    out_dir.mkdir(parents=True, exist_ok=True)
    blobs = {
        "cells": png_bytes(cells.png, "RGB"),
        "relief": png_bytes(heights.relief, "RGB"),
        "cover": png_bytes(cover, "L"),
        "backdrop": png_bytes(heights.backdrop, "RGB"),
        "licence": licence_text(CREDITS).encode("utf-8"),
    }
    bx, bz = heights.axes
    timeline = replay.timeline
    hand = timeline["hand"]
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_by": GENERATED_BY,
        "generated_at": {"value": generated_at, "basis": "declared",
                         "note": "Declared with --generated-at and recorded in docs/journey_town_input_receipt.json; never read from the clock."},
        "purpose": PURPOSE,
        "data_mode": "historical_reconstruction",
        "real_time": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "confidence": "low",
        "confidence_reason": f"{timeline['confidence_reason']} {CONFIDENCE_EXTRA}",
        "source_timestamp": timeline["source_timestamp"],
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
        "credits": CREDITS,
        "licence": {"database": "ODbL-1.0", "notes": LICENCE_NOTES, **file_entry(FILES["licence"], blobs["licence"])},
        "sources": sources(replay),
        "replay": {
            "study_id": timeline["study_id"], "revision": timeline["revision"], "data_version": timeline["data_version"],
            "generated_at": timeline["generated_at"], "timeline_sha256": replay.hashes["timeline"],
            "hand_sha256": replay.hashes["hand"], "access_nodes_sha256": replay.hashes["nodes"],
            "stage_anchors": timeline["stage_anchors"], "impassable_depth_m": timeline["impassable_depth_m"],
            "hand": {"step_m": hand["step_m"], "byte_scale": hand["depth_factor"]["byte_scale"],
                     "channel_code": hand["channel_code"], "never_code": hand["never_code"],
                     "low_confidence_min_byte": LOW_CONFIDENCE_MIN_BYTE},
            "epoch": REPLAY_EPOCH_TEXT,
        },
        "frame": {
            "origin": {"lat": ORIGIN_LAT, "lon": ORIGIN_LON},
            "m_per_deg_lon": M_PER_DEG_LON, "m_per_deg_lat": M_PER_DEG_LAT,
            "formula": "x = (lon - 99.88718) * 111320 * cos(20.44042 deg); z = (20.44042 - lat) * 110540",
            "axes": "x east, z south, y up; metres (places) or integer decimetres (vectors)",
            "detail": {"x_min": DETAIL[0], "x_max": DETAIL[1], "z_min": DETAIL[2], "z_max": DETAIL[3]},
            "backdrop": {"x_min": float(bx[0] - BACKDROP_CELL_M / 2), "x_max": float(bx[-1] + BACKDROP_CELL_M / 2),
                         "z_min": float(bz[0] - BACKDROP_CELL_M / 2), "z_max": float(bz[-1] + BACKDROP_CELL_M / 2),
                         "centre": list(BACKDROP_CENTRE)},
        },
        "cells": {
            **file_entry(FILES["cells"], blobs["cells"]),
            "source": HAND_REL.as_posix(), "col0": cells.col0, "row0": cells.row0, "cols": cells.cols, "rows": cells.rows,
            **cells.affine, "max_affine_error_m": round(cells.error, 4),
            "affine_rule": "Centre of crop cell (c, r): x = x0 + c * dx, z = z0 + r * dz (r5 column col0 + c, row row0 + r).",
            "georef": {"bounds": timeline["bounds"], "png_size": [PNG_COLS, PNG_ROWS],
                       "rule": "col = floor((lon - W) / (E - W) * 1610); row = floor((mercY(N) - mercY(lat)) / (mercY(N) - mercY(S)) * 1753); mercY(lat) = ln(tan(pi/4 + lat/2))"},
            "channels": {"R": "code: 0 channel, 1-254 effective HAND in 0.05 m steps, 255 never floods",
                         "G": "depth-factor byte: k = G / 255 * 2.5",
                         "B": "255 where the r5 low-confidence byte >= 128 and the cell is not channel, else 0"},
        },
        "relief": {
            **file_entry(FILES["relief"], blobs["relief"]),
            "encoding": "R, G = big-endian uint16 of height_dm + 2000 for cells with code 255, else 0; B = 0 (same cells as the cells PNG)",
            "datum_m": heights.datum,
            "datum_rule": "median over floodable cells (code 1-254, centre inside the detail box) of DSM - k * code * 0.05, rounded to 0.01 m",
            "height_rule": "DSM (bilinear at the cell centre) - datum_m, clamped to >= 12.8 m",
            "clamp_min_m": NEVER_MIN_HEIGHT_M, "never_cells": heights.never, "clamped_cells": heights.clamped,
            "floodable_cells_in_datum": heights.floodable,
        },
        "cover": {
            **file_entry(FILES["cover"], blobs["cover"]),
            "cols": int(cover.shape[1]), "rows": int(cover.shape[0]),
            "x0": DETAIL[0] + COVER_CELL_M / 2, "z0": DETAIL[2] + COVER_CELL_M / 2, "cell_m": COVER_CELL_M,
            "cell_rule": "Centre of cell (c, r): x = x0 + c * cell_m, z = z0 + r * cell_m; a polygon fills the cells whose centre it covers.",
            "classes": [{"value": i, "id": name} for i, name in enumerate(COVER_CLASSES)],
            "precedence": list(COVER_PRECEDENCE),
            "counts": {name: int(np.count_nonzero(cover == i)) for i, name in enumerate(COVER_CLASSES)},
            "rules": {
                "water": "OSM natural=water, water=*, landuse=reservoir|basin, waterway=riverbank polygons; waterway river, canal, stream lines buffered 10, 3, 2 m each side",
                "road": "OSM road centrelines buffered by half their width (at least 2 m, so one cell)",
                "building": "the simplified outlines of this pack",
                "green": "landuse forest|grass|meadow|orchard|recreation_ground|village_green|cemetery|plant_nursery; natural wood|scrub|grassland|heath; leisure park|garden|pitch|golf_course|nature_reserve",
                "field": "landuse farmland|paddy",
            },
        },
        "backdrop": {
            **file_entry(FILES["backdrop"], blobs["backdrop"]),
            "cols": BACKDROP_CELLS, "rows": BACKDROP_CELLS, "x0": float(bx[0]), "z0": float(bz[0]), "cell_m": BACKDROP_CELL_M,
            "cell_rule": "Centre of cell (c, r): x = x0 + c * cell_m, z = z0 + r * cell_m",
            "encoding": "R, G = big-endian uint16 of (DSM - datum_m) in decimetres + 2000; B = 0",
            "height_range_m": [round(heights.back_min, 1), round(heights.back_max, 1)],
        },
        "places": places,
        "beats": beats,
        "route": route,
        "buildings": {
            "count": len(buildings),
            "encoding": "ring_start[i] is the index of building i's first vertex in the vertex list (length count + 1, the last "
                        "value is the vertex total); coords holds 2 integers per vertex in decimetres: the first vertex of each ring "
                        "absolute, the next ones as differences from the previous vertex. Rings are counter-clockwise in the x/z "
                        "plane (positive shoelace area) and do not repeat the first vertex. Edge i runs from vertex i to i + 1.",
            "ring_start": ring_start,
            "coords": coords,
            "kinds": list(BUILDING_KINDS),
            "kind": [BUILDING_KINDS.index(k) for k in kinds],
            "kind_rules": [
                "temple: representative point inside an OSM amenity=place_of_worship or building=temple|shrine polygon",
                "government: inside amenity=townhall|police|fire_station|courthouse, office=government or building=government|public|civic",
                "school: inside amenity=school|college|kindergarten|university or building=school|college|university|kindergarten",
                "market: inside amenity=marketplace, or area >= 900 m2 when none of the above",
                "shed: area < 30 m2",
                "shophouse: within 12 m + half the road width of a trunk, primary, secondary or tertiary centreline (links included)",
                "large: area >= 400 m2",
                "house: everything else",
            ],
            "floors": [FLOORS[k][0] + stable_int(b["id"]) % (FLOORS[k][1] - FLOORS[k][0] + 1) for b, k in zip(buildings, kinds)],
            "floors_rule": "lo + h mod (hi - lo + 1), h = first 4 bytes of SHA-256 of the outline id; ranges: "
                           + ", ".join(f"{k} {lo}-{hi}" for k, (lo, hi) in FLOORS.items()) + ". Illustrative.",
            "front": fronts,
            "front_rule": "edge whose outward normal points most directly at the nearest point of the nearest road; among edges "
                          "within 0.1 of the best cosine, the longest",
            "obb": obbs,
            "obb_encoding": "5 integers per building: cx_dm, cz_dm, w_dm (side most parallel to the front edge), d_dm, angle of the w side "
                            "in centidegrees from +x toward +z, 0-17999",
            "rect": rects,
            "area_m2": [int(round(b["area"])) for b in buildings],
            "compound": [int(c) for c in compound],
            "compound_rule": "index into places of the reported site whose OSM polygon holds the outline's representative point, else -1",
            "conf": [b["conf"] for b in buildings],
            "conf_rule": "outline confidence x 100 (Google); -1 where the source gives none (Microsoft)",
            "sources": ["google", "microsoft"],
            "src": [0 if b["src"] == "google" else 1 for b in buildings],
            "simplify_m": BUILDING_SIMPLIFY_M, "min_area_m2": BUILDING_MIN_AREA_M2,
            "home": home_building, "neighbour": neighbour_building, **named,
        },
        "roads": {
            "count": len(roads.pieces),
            "encoding": "line_start[i] is the index of road line i's first vertex (length count + 1); coords as for buildings "
                        "(first vertex absolute, then differences, decimetres)",
            "classes": list(ROAD_CLASSES),
            "line_start": [0, *np.cumsum([len(p["points"]) for p in roads.pieces]).tolist()],
            "coords": [v for p in roads.pieces for v in delta_encode(p["points"])],
            "class": [ROAD_CLASSES.index(p["class"]) for p in roads.pieces],
            "width_dm": [p["width_dm"] for p in roads.pieces],
            "width_rule": "width tag (m), else lanes x 3.25 m, else the class default: "
                          + ", ".join(f"{k} {v}" for k, v in ROAD_WIDTH_DM.items()) + " (dm)",
            "bridge": [1 if p["bridge"] else 0 for p in roads.pieces],
            "osm_id": [p["osm_id"] for p in roads.pieces],
            "names": [{"th": th or None, "en": en or None} for th, en in roads.names],
            "name": [roads.names.get(p["name"], -1) for p in roads.pieces],
            "simplify_m": ROAD_SIMPLIFY_M,
        },
        "trees": {
            "count": int(len(trees.coords)),
            "encoding": "coords: 2 integers per tree in decimetres, sorted by z then x, the first absolute and the next ones as differences",
            "coords": delta_encode(trees.coords),
            "kinds": list(TREE_KINDS),
            "kind": trees.kind,
            "scale": trees.scale,
            "scale_rule": "percent of the kind's base size, 75-125",
            "seed": TREE_SEED,
            "rule": "Dart-throwing Poisson-disk passes in order (spacing m): "
                    + ", ".join(f"{name} {spacing:g} m, at most {cap}" for name, spacing, _, cap, _ in TREE_PASSES)
                    + f"; never within {TREE_CLEARANCE_M} m of a building or of a road as drawn in the cover raster; river bank = "
                    f"plantable cells within {RIVER_BANK_M:g} m of water (coconut palms); field edge = field cells next to another class; "
                    f"at most {TREE_MAX} in all.",
            "passes": dict(trees.by_pass),
        },
    }
    for key in ("cells", "relief", "cover", "backdrop"):
        (out_dir / FILES[key]).write_bytes(blobs[key])
    (out_dir / FILES["licence"]).write_bytes(blobs["licence"])
    text = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    (out_dir / FILES["manifest"]).write_bytes(text.encode("utf-8"))
    summary = SimpleNamespace(cells=cells, heights=heights, buildings=len(buildings), roads=len(roads.pieces),
                              trees=len(trees.coords), tree_masks=trees.masks, tree_passes=trees.by_pass, route=route, beats=beats, land=land,
                              kinds={k: kinds.count(k) for k in BUILDING_KINDS}, cover=manifest["cover"]["counts"])
    return manifest, receipt, summary


def receipt_sha(receipt: InputReceipt, path: Path) -> str:
    """SHA-256 of a tracked input, through the receipt's hash cache."""
    key = receipt.locate(path)
    for row in receipt.entries():
        if (row["root"], row["path"]) == key:
            return row["sha256"]
    raise RuntimeError("input not tracked")


# --- Receipt, verify and main ---------------------------------------------------------------------------------------

RECEIPT_ASSUMPTIONS = [
    "Input paths are relative to the external data root (FLOODGUARD_EXTERNAL_DATA) or to the repository root; no machine path is recorded.",
    "The same inputs give the same bytes only with the same library versions: another GDAL, GEOS, PROJ or zlib build can change bytes without changing the method.",
    "The OpenStreetMap land use and waterways are read from the Geofabrik PBF itself on every run; no derived cache stands between the receipt and the result.",
    "generated_at is a declared value, not a clock reading; a bake that changes any output file must declare a new one.",
    "Bake sources are hashed with CRLF read as LF, so a Windows checkout gives the same hashes.",
]

BAKE_SOURCES = (
    GENERATED_BY,
    "scripts/mae_sai_timeline_evacuation.py",
    "src/floodguard/bake_receipt.py",
    "src/floodguard/evacuation_access.py",
    "src/floodguard/flood_timeline.py",
)
"""This script and the repository modules it imports (a unit test checks the imports)."""

LIBRARIES = (*DEFAULT_LIBRARIES, "geopandas")


def bake_sources() -> list[dict[str, str]]:
    """Line-ending-neutral SHA-256 of every file in :data:`BAKE_SOURCES`."""
    return source_hashes([ROOT / path for path in BAKE_SOURCES], ROOT)


def receipt_document(manifest: dict[str, Any], receipt: InputReceipt, out_dir: Path) -> dict[str, Any]:
    """The input receipt of a finished bake in ``out_dir``."""
    inputs = receipt.entries()
    outputs = directory_listing(out_dir)
    return {
        "schema": RECEIPT_SCHEMA,
        "pack": SCHEMA, "generated_by": GENERATED_BY,
        "purpose": "Every input file the journey town bake opened, so the pack can be rebuilt and compared byte for byte (--verify).",
        "generated_at": {"value": manifest["generated_at"]["value"], "basis": manifest["generated_at"]["basis"]},
        "source_timestamp": manifest["source_timestamp"],
        "confidence": manifest["confidence"],
        "confidence_reason": "Confidence of the baked scene, copied from mae-sai-town.json. The receipt itself is an exact file record.",
        "assumptions": RECEIPT_ASSUMPTIONS,
        "official_warning": False, "real_time": False, "operational_status": "non_operational", "can_feed_decision_layer": False,
        "roots": {"external": "FLOODGUARD_EXTERNAL_DATA or --external-root (kept outside Git)", "repo": "repository root"},
        "input_count": len(inputs), "input_bytes": sum(row["bytes"] for row in inputs),
        "inputs": inputs,
        "outputs": {"folder": OUT_REL.as_posix(), "file_count": len(outputs), "bytes": sum(row["bytes"] for row in outputs), "files": outputs},
        "code": bake_sources(),
        "libraries": library_versions(LIBRARIES),
        "platform": {"system": platform.system(), "machine": platform.machine()},
    }


def write_receipt(path: Path, document: dict[str, Any]) -> None:
    """Write the receipt as UTF-8 JSON with LF line endings and a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(document, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))


def normalise_time(value: str) -> str:
    """An ISO 8601 time with a UTC offset, normalised to UTC ``YYYY-MM-DDTHH:MM:SSZ``."""
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--generated-at needs a UTC offset (for example 2026-10-14T12:00:00Z)")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def recorded_receipt(path: Path) -> dict[str, Any]:
    """The receipt of an earlier bake, or an empty mapping."""
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def recorded_time(recorded: dict[str, Any]) -> str | None:
    """The declared ``generated_at`` of the recorded receipt, if any."""
    value = recorded.get("generated_at")
    if isinstance(value, dict) and value.get("basis") == "declared" and value.get("value"):
        return normalise_time(value["value"])
    return None


def differences_from(document: dict[str, Any], recorded: dict[str, Any]) -> list[str]:
    """Output files that differ from the recorded bake, plus the input, code and library notes that explain them."""
    recorded_files = {row["name"]: row["sha256"] for row in recorded.get("outputs", {}).get("files", [])}
    fresh_files = {row["name"]: row["sha256"] for row in document["outputs"]["files"]}
    notes = [f"output differs: {name}" for name in sorted(fresh_files.keys() | recorded_files.keys())
             if fresh_files.get(name) != recorded_files.get(name)]
    if notes:
        notes += [f"input note: {n}" for n in input_differences(document["inputs"], recorded.get("inputs", []))]
        notes += [f"code note: {n}" for n in source_differences(document["code"], recorded.get("code", []))]
        notes += [f"library note: {n}" for n in version_differences(document["libraries"], recorded.get("libraries", {}))]
    return notes


def verify(external: Path, committed: Path, receipt_path: Path, generated_at: str | None = None) -> int:
    """Bake into a temporary folder and byte-compare it with ``committed``; return 0 only when every file matches."""
    if not committed.is_dir():
        print(f"verify: the committed folder does not exist: {committed.name}")
        return 1
    recorded = recorded_receipt(receipt_path)
    stamp = normalise_time(generated_at) if generated_at else recorded_time(recorded)
    if stamp is None:
        print("verify: no declared generated_at in the receipt; pass --generated-at")
        return 1
    with tempfile.TemporaryDirectory(prefix="journey-town-verify-") as tmp:
        fresh = Path(tmp) / committed.name
        if fresh.resolve() == committed.resolve():
            raise RuntimeError("--verify must never bake into the committed folder")
        manifest, receipt, _ = bake(external, fresh, stamp)
        comparison = compare_directories(fresh, committed)
        document = receipt_document(manifest, receipt, fresh)
    print(f"verify: generated_at {stamp}")
    print(f"verify: {comparison.summary()} ({committed.name}, {document['outputs']['bytes']:,} bytes in the fresh bake)")
    for label, names in (("different bytes", comparison.different), ("committed but not baked", comparison.missing_from_fresh),
                         ("baked but not committed", comparison.extra_in_fresh)):
        for name in names:
            print(f"verify: {label}: {name}")
    if recorded:
        for note in input_differences(document["inputs"], recorded.get("inputs", [])):
            print(f"verify: input note: {note}")
        for note in source_differences(document["code"], recorded.get("code", [])):
            print(f"verify: code note: {note}")
        for note in version_differences(document["libraries"], recorded.get("libraries", {})):
            print(f"verify: library note: {note}")
    print("verify: PASS" if comparison.matches else "verify: FAIL")
    return 0 if comparison.matches else 1


def report(summary: SimpleNamespace) -> None:
    """Print the bake's key figures."""
    route = summary.route
    print(f"cells {summary.cells.cols}x{summary.cells.rows} at r5 col {summary.cells.col0} row {summary.cells.row0}; "
          f"affine error {summary.cells.error:.3f} m; datum {summary.heights.datum} m; never cells {summary.heights.never}, clamped {summary.heights.clamped}")
    print(f"buildings {summary.buildings} {summary.kinds}; roads {summary.roads}; trees {summary.trees} {summary.tree_passes} (mask cells {summary.tree_masks})")
    print(f"cover {summary.cover}; OSM water polygons {summary.land.water_polygons}, waterway bands {summary.land.waterway_bands}, "
          f"green {len(summary.land.green)}, field {len(summary.land.field)}")
    print(f"route to {route['destination']}: {route['length_m']} m on the network ({route['drawn_length_m']} m drawn); "
          f"cut stage {route['cut_stage_m']} m, first cut {route['first_cut']}; app cut {route['app']['cut_code']} = {route['app']['cut_level_m']} m")
    for beat in summary.beats:
        best = beat["best_path"]
        print(f"h{beat['hour']:>3} stage {beat['stage_m']:.4f} {beat['practice']} home {beat['home_depth_m']} neighbour "
              f"{beat['neighbour_depth_m']} wet {beat['wet_share_450m']} open {beat['route_open']} best "
              f"{None if best is None else (best['destination'], best['length_m'])}")


def main(argv: list[str] | None = None) -> int:
    """Command line: bake (into ``--out``), or ``--verify`` against it."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--external-root", default=os.environ.get("FLOODGUARD_EXTERNAL_DATA"),
                        help="Folder holding the external data (or set FLOODGUARD_EXTERNAL_DATA).")
    parser.add_argument("--out", default=str(ROOT / OUT_REL),
                        help="Folder to bake into; with --verify, the committed folder to compare against (never written).")
    parser.add_argument("--receipt", default=None, help="Input receipt to write (or compare with). Defaults to the committed receipt.")
    parser.add_argument("--generated-at", default=None,
                        help="Bake time to record (ISO 8601 with a UTC offset, e.g. 2026-10-14T12:00:00Z). Without it the recorded "
                             "value is carried, only when the bake reproduces the recorded files. The clock is never read.")
    parser.add_argument("--verify", action="store_true", help="Bake into a temporary folder and byte-compare with --out.")
    args = parser.parse_args(argv)
    if not args.external_root:
        parser.error("--external-root or FLOODGUARD_EXTERNAL_DATA is required")
    external, out_dir = Path(args.external_root), Path(args.out)
    receipt_path = Path(args.receipt) if args.receipt else (
        ROOT / RECEIPT_REL if out_dir.resolve() == (ROOT / OUT_REL).resolve() else out_dir.parent / f"{out_dir.name}_input_receipt.json")
    if args.verify:
        return verify(external, out_dir, receipt_path, args.generated_at)
    recorded = recorded_receipt(receipt_path)
    if args.generated_at:
        stamp = normalise_time(args.generated_at)
        manifest, receipt, summary = bake(external, out_dir, stamp)
    else:
        stamp = recorded_time(recorded)
        if stamp is None:
            print("Declare when these files are generated with --generated-at (ISO 8601 with a UTC offset). Nothing was written.", file=sys.stderr)
            return 2
        with tempfile.TemporaryDirectory(prefix="journey-town-bake-") as tmp:
            staging = Path(tmp) / out_dir.name
            manifest, receipt, summary = bake(external, staging, stamp)
            notes = differences_from(receipt_document(manifest, receipt, staging), recorded)
            if notes:
                print(f"generated_at: the recorded time {stamp} cannot be carried, because this bake does not reproduce the recorded files.", file=sys.stderr)
                for note in notes:
                    print(f"  {note}", file=sys.stderr)
                print("Declare when these files are generated with --generated-at. Nothing was written.", file=sys.stderr)
                return 2
            shutil.copytree(staging, out_dir, dirs_exist_ok=True)
    write_receipt(receipt_path, receipt_document(manifest, receipt, out_dir))
    print(f"generated_at: {stamp}")
    report(summary)
    for row in directory_listing(out_dir):
        print(f"{row['name']}: {row['bytes']:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
