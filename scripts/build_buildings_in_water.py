"""Buildings in the water against residents in the water: the outlines, two THEOS-2 chips, and case SE1.

Plan: docs/proposal_execution/buildings_in_water_plan_v1.md.

Stage ``fetch``
    Reads the building outlines inside the bounding boxes of the two flood chips and of Mae Sai district from the
    combined Google and Microsoft file for Thailand (range requests; the country file is not downloaded), and keeps
    them outside Git with their SHA-256.

Stage ``chips``
    On each flood chip and for each water rule: the buildings that stand in water by the ground around them, and
    three readings of residents in the water on the population grid.

Stage ``district``
    For case SE1: buildings inside the flood layer of the scenario against residents in the water by the centre
    rule, for the district and each tambon.

    python scripts/build_buildings_in_water.py fetch --external-root <external-data-root>
    python scripts/build_buildings_in_water.py chips --external-root <external-data-root>
    python scripts/build_buildings_in_water.py district --external-root <external-data-root> --age-dir <age rasters>

Outlines are drawn by a model on satellite images; nothing here counts people or observes a flooded house.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import buildings_in_water as bw  # noqa: E402

PLAN = "docs/proposal_execution/buildings_in_water_plan_v1.md"
OUTPUT_DIR = "outputs/buildings_in_water"
OUTLINES_NAME = "outlines_v1.json"
CHIPS_NAME = "theos2_chips_v1.json"
DISTRICT_NAME = "se1_mae_sai_v1.json"
WORK = "proposal_execution/buildings_in_water"
RULE_WORK = "proposal_execution/theos2_water_rule_v2"
RULE_FREEZE = "outputs/theos2_water_rule_v2/freeze_v1.json"
WORLDPOP = "open_context/worldpop_population/tha_ppp_2020.tif"
DISTRICT_BOUNDARY = "derived_context/mae_sai_2024/mae_sai_adm3.geojson"
CELL_CACHE = "proposal_execution/planning_v1/se1_mae_sai/cell_outcomes/cell_outcomes_se1_mae_sai_v1.npz"
CELL_RECEIPT = "outputs/cell_outcomes/se1_mae_sai_v1_receipt.json"
NEED_MIX = "outputs/need_mix/se1_mae_sai_v1.json"

SOURCE_URL = "https://data.source.coop/vida/google-microsoft-open-buildings/flatgeobuf/by_country/country_iso=THA/THA.fgb"
SOURCE_NAME = "Google-Microsoft Open Buildings, combined by VIDA (Source Cooperative), Thailand"
SOURCE_LICENCE = "Google Open Buildings v3: CC BY 4.0 and ODbL v1.0. Microsoft building footprints: ODbL v1.0."
CREDIT = ("Building outlines: Google Open Buildings v3 (CC BY 4.0) and Microsoft building footprints (ODbL), combined by VIDA "
          "and hosted by Source Cooperative.")
FLOOD_CHIPS = ("sukhothai", "chip_003")
EPSG = 32647
PIXEL_M = 2.0
CELL_INSIDE_M = 50.0

LIMITS = [
    "The outlines are drawn by a model on satellite images of earlier years: not a survey, and not a register of dwellings. "
    "Sheds, shops and temples count like houses.",
    "Spreading the residents of a cell evenly over its buildings is a model, as the population grid is. The comparison sets "
    "one model against another; neither is a count of people.",
    "No published figure changes: the planning score keeps the centre rule.",
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
    # Bytes with LF line ends on every platform (.gitattributes, D-41).
    path.write_bytes((json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


def envelope(source_timestamp: str, basis: str) -> dict[str, Any]:
    """The fields every FloodGuard output carries."""

    return {
        "generated_at_utc": now_utc(),
        "source_timestamp": source_timestamp,
        "confidence_class": "low",
        "confidence_basis": basis,
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "plan": {"path": PLAN, "sha256": sha256_file(ROOT / PLAN)},
    }


def guard(path: Path, arguments: argparse.Namespace) -> None:
    if path.exists() and not (arguments.replace and arguments.reason):
        raise BuildError(f"{path} exists; a second run needs --replace and --reason")


def superseded(path: Path, arguments: argparse.Namespace) -> dict[str, Any] | None:
    if not path.exists():
        return None
    old = json.loads(path.read_text(encoding="utf-8"))
    canonical = hashlib.sha256(json.dumps(old, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"reason": arguments.reason, "generated_at_utc": old.get("generated_at_utc"), "canonical_json_sha256": canonical}


def load_script(name: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"scripts/{name}.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def chip_cache(external: Path, chip: str) -> Any:
    return np.load(external / RULE_WORK / f"{chip}_2m.npz")


def chip_bounds(cache: Any) -> tuple[float, float, float, float]:
    """West, south, east and north of a chip in EPSG:32647."""

    rows, columns = cache["water_v1"].shape
    west, north = float(cache["west"]), float(cache["north"])
    return west, north - rows * PIXEL_M, west + columns * PIXEL_M, north


# ---------------------------------------------------------------------------
# Stage 1: the outlines
# ---------------------------------------------------------------------------


TILE_DEGREES = 0.08
READ_TRIES = 5


def read_box(box: tuple[float, float, float, float]) -> Any:
    """The outlines that meet a bounding box. A large box is read in tiles, each tried again when the read breaks."""

    import time

    import pandas as pd
    import pyogrio

    west, south, east, north = box
    columns = max(1, int(np.ceil((east - west) / TILE_DEGREES)))
    rows = max(1, int(np.ceil((north - south) / TILE_DEGREES)))
    parts = []
    for row in range(rows):
        for column in range(columns):
            tile = (west + column * (east - west) / columns, south + row * (north - south) / rows,
                    west + (column + 1) * (east - west) / columns, south + (row + 1) * (north - south) / rows)
            for attempt in range(READ_TRIES):
                try:
                    parts.append(pyogrio.read_dataframe("/vsicurl/" + SOURCE_URL, bbox=tile))
                    break
                except Exception as error:  # a broken range read: wait and read the tile again
                    if attempt == READ_TRIES - 1:
                        raise BuildError(f"the outlines of tile {tile} could not be read: {error}") from error
                    time.sleep(5 * (attempt + 1))
            print(f"  tile {row * columns + column + 1} of {rows * columns}: {len(parts[-1])} outlines", flush=True)
    frame = pd.concat(parts, ignore_index=True)
    # An outline on a tile edge is read twice.
    return frame.loc[~frame.geometry.to_wkb().duplicated()].reset_index(drop=True)


def stage_fetch(arguments: argparse.Namespace) -> None:
    import geopandas as gpd
    from pyproj import Transformer

    external = Path(arguments.external_root)
    work = external / WORK
    record_path = ROOT / OUTPUT_DIR / OUTLINES_NAME
    guard(record_path, arguments)
    work.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".fgb")
    os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
    os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "3")
    with urllib.request.urlopen(urllib.request.Request(SOURCE_URL, method="HEAD", headers={"User-Agent": "curl/8.0"}), timeout=60) as response:
        head = {name: response.headers.get(name) for name in ("Content-Length", "Last-Modified", "ETag")}

    to_lonlat = Transformer.from_crs(EPSG, 4326, always_xy=True)
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for chip in FLOOD_CHIPS:
        west, south, east, north = chip_bounds(chip_cache(external, chip))
        lon0, lat0 = to_lonlat.transform(west, south)
        lon1, lat1 = to_lonlat.transform(east, north)
        boxes[chip] = (min(lon0, lon1), min(lat0, lat1), max(lon0, lon1), max(lat0, lat1))
    district = gpd.read_file(external / DISTRICT_BOUNDARY)
    boxes["mae_sai"] = tuple(float(value) for value in district.to_crs(4326).total_bounds)

    areas: dict[str, Any] = {}
    for area, box in boxes.items():
        frame = read_box(box)
        frame = frame[["bf_source", "confidence", "area_in_meters", "geometry"]].reset_index(drop=True)
        keep = bw.used(frame["area_in_meters"].to_numpy(), frame["confidence"].to_numpy())
        target = work / f"{area}_outlines.gpkg"
        if target.exists():
            target.unlink()
        frame.to_file(target, driver="GPKG", layer="outlines")
        areas[area] = {
            "bounding_box_lonlat": [round(value, 5) for value in box],
            "outlines_read": int(len(frame)),
            "by_source": {str(key): int(value) for key, value in frame["bf_source"].value_counts().items()},
            "used_by_the_rule_of_the_plan": int(keep.sum()),
            "file_outside_git": {"name": target.name, "sha256": sha256_file(target)},
        }
        print(area, areas[area]["outlines_read"], areas[area]["used_by_the_rule_of_the_plan"], flush=True)
    record = {
        "schema": "floodguard.buildings_in_water.outlines.v1",
        **envelope(f"source file of {head['Last-Modified']}", "Outlines drawn by a model on satellite images of earlier years; not a survey."),
        "what_this_is": "The building outlines read for the two flood chips and for Mae Sai district. Only the outlines inside "
                        "the bounding boxes were read; they stay outside Git.",
        "source": {"name": SOURCE_NAME, "url": SOURCE_URL, "licence": SOURCE_LICENCE, "credit": CREDIT,
                   "bytes_of_the_country_file": int(head["Content-Length"]), "last_modified": head["Last-Modified"],
                   "etag": head["ETag"], "read_with": "range requests on the FlatGeobuf file, by bounding box"},
        "rule_for_using_an_outline": {"min_area_m2": bw.MIN_AREA_M2, "min_confidence_where_given": bw.MIN_CONFIDENCE},
        "areas": areas,
        "limits": LIMITS[:1],
    }
    previous = superseded(record_path, arguments)
    if previous is not None:
        record["supersedes"] = previous
    write_json(record_path, record)


def read_outlines(external: Path, area: str) -> Any:
    """The outlines of an area that the plan uses, in EPSG:32647, checked against the committed record."""

    import geopandas as gpd

    record = json.loads((ROOT / OUTPUT_DIR / OUTLINES_NAME).read_text(encoding="utf-8"))["areas"][area]
    path = external / WORK / record["file_outside_git"]["name"]
    if sha256_file(path) != record["file_outside_git"]["sha256"]:
        raise BuildError(f"{path.name} is not the file the committed record names")
    frame = gpd.read_file(path, layer="outlines")
    frame = frame[bw.used(frame["area_in_meters"].to_numpy(), frame["confidence"].to_numpy())]
    if len(frame) != record["used_by_the_rule_of_the_plan"]:
        raise BuildError("the outlines used are not as many as the committed record says")
    return frame.to_crs(EPSG).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Stage 2: the two flood chips
# ---------------------------------------------------------------------------


def stage_chips(arguments: argparse.Namespace) -> None:
    import rasterio
    from pyproj import Transformer
    from rasterio import features
    from rasterio.transform import from_origin

    external = Path(arguments.external_root)
    record_path = ROOT / OUTPUT_DIR / CHIPS_NAME
    guard(record_path, arguments)
    freeze = json.loads((ROOT / RULE_FREEZE).read_text(encoding="utf-8"))
    to_lonlat = Transformer.from_crs(EPSG, 4326, always_xy=True)
    chips: dict[str, Any] = {}
    for chip in FLOOD_CHIPS:
        cache = chip_cache(external, chip)
        named = freeze["frozen_rule"]["chips"][chip]["raster_outside_git"]
        if sha256_file(external / RULE_WORK / named["name"]) != named["sha256"]:
            raise BuildError(f"{named['name']} is not the raster the freeze names")
        with rasterio.open(external / RULE_WORK / named["name"]) as source:
            waters = {"rule_v1": cache["water_v1"], "rule_v2": source.read(1)}
        rows, columns = waters["rule_v1"].shape
        west, south, east, north = chip_bounds(cache)
        transform = from_origin(west, north, PIXEL_M, PIXEL_M)

        outlines = read_outlines(external, chip)
        centre = outlines.geometry.centroid
        margin = bw.EDGE_MARGIN_M
        counted = ((centre.x >= west + margin) & (centre.x <= east - margin) & (centre.y >= south + margin)
                   & (centre.y <= north - margin)).to_numpy()
        # Every outline is drawn, also the ones not counted: a neighbour at the edge still takes ground from a ring.
        labels = features.rasterize(((geometry, number + 1) for number, geometry in enumerate(outlines.geometry)),
                                    out_shape=(rows, columns), transform=transform, fill=0, all_touched=True, dtype="int32")
        ring = bw.rings(labels)

        # --- the population grid ----------------------------------------------------------------------------------
        with rasterio.open(external / WORLDPOP) as source:
            lon0, lat0 = to_lonlat.transform(west, south)
            lon1, lat1 = to_lonlat.transform(east, north)
            window = source.window(min(lon0, lon1), min(lat0, lat1), max(lon0, lon1), max(lat0, lat1)).round_offsets().round_lengths()
            people = source.read(1, window=window, masked=True).filled(0.0).astype("float64")
            grid = source.window_transform(window)
        people[people < 0] = 0.0
        cell_rows, cell_columns = people.shape
        to_utm = Transformer.from_crs(4326, EPSG, always_xy=True)
        cell_lon = grid.c + (np.arange(cell_columns) + 0.5) * grid.a
        cell_lat = grid.f + (np.arange(cell_rows) + 0.5) * grid.e
        lon_grid, lat_grid = np.meshgrid(cell_lon, cell_lat)
        cell_x, cell_y = to_utm.transform(lon_grid.ravel(), lat_grid.ravel())
        inside = ((cell_x >= west + CELL_INSIDE_M) & (cell_x <= east - CELL_INSIDE_M) & (cell_y >= south + CELL_INSIDE_M)
                  & (cell_y <= north - CELL_INSIDE_M))
        residents = np.where(inside, people.ravel(), 0.0)

        def cell_of(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            """The index of the population cell a point lies in, or -1 outside the window."""

            lon, lat = to_lonlat.transform(x, y)
            column = np.floor((np.asarray(lon) - grid.c) / grid.a).astype("int64")
            row = np.floor((np.asarray(lat) - grid.f) / grid.e).astype("int64")
            ok = (row >= 0) & (row < cell_rows) & (column >= 0) & (column < cell_columns)
            return np.where(ok, row * cell_columns + column, -1)

        pixel_x = west + (np.arange(columns) + 0.5) * PIXEL_M
        pixel_y = north - (np.arange(rows) + 0.5) * PIXEL_M
        xs, ys = np.meshgrid(pixel_x, pixel_y)
        pixel_cell = cell_of(xs.ravel(), ys.ravel())
        centre_row = np.clip(((north - cell_y) / PIXEL_M).astype("int64"), 0, rows - 1)
        centre_column = np.clip(((cell_x - west) / PIXEL_M).astype("int64"), 0, columns - 1)
        building_cell = cell_of(centre.x.to_numpy(), centre.y.to_numpy())
        cells = cell_rows * cell_columns

        by_rule: dict[str, Any] = {}
        for rule, water in waters.items():
            counts = bw.ring_counts(ring, water, len(outlines))
            is_assessed = bw.assessed(counts) & counted
            wet = {share: bw.in_water(counts, share) & counted for share in (bw.IN_WATER_SHARE, *bw.OTHER_SHARES)}
            ok = pixel_cell >= 0
            answered = np.bincount(pixel_cell[ok], weights=(water.ravel()[ok] != bw.WATER_UNOBSERVABLE), minlength=cells)
            water_px = np.bincount(pixel_cell[ok], weights=(water.ravel()[ok] == bw.WATER_YES), minlength=cells)
            with np.errstate(divide="ignore", invalid="ignore"):
                area_share = np.where(answered > 0, water_px / answered, np.nan)
            at_centre = water[centre_row, centre_column].astype("float64")
            centre_in_water = np.where(at_centre == bw.WATER_UNOBSERVABLE, np.nan, (at_centre == bw.WATER_YES).astype("float64"))
            in_cell = building_cell >= 0
            held = np.bincount(building_cell[in_cell & is_assessed], minlength=cells)
            held_wet = np.bincount(building_cell[in_cell & wet[bw.IN_WATER_SHARE]], minlength=cells)
            readings = bw.residents_in_water(residents, centre_in_water, area_share, held, held_wet)
            number = int(is_assessed.sum())
            by_rule[rule] = {
                "water_share_of_the_chip": round(float((water == bw.WATER_YES).mean()), 4),
                "buildings_assessed": number,
                "buildings_not_assessed": int(counted.sum()) - number,
                "buildings_in_the_water": {
                    f"at_{share:g}_of_the_ring": {"buildings": int(flags.sum()), "share": None if number == 0 else round(float(flags.sum()) / number, 4)}
                    for share, flags in wet.items()},
                "residents_in_the_water": readings,
                "on_the_centre_rule": bw.verdict(readings["buildings_minus_centre_rule_points"]),
            }
            print(chip, rule, number, by_rule[rule]["buildings_in_the_water"], readings["centre_rule"], readings["area"],
                  readings["buildings"], flush=True)
        chips[chip] = {
            "outlines_used": int(len(outlines)),
            "buildings_counted": int(counted.sum()),
            "population_cells_inside_the_chip": int(inside.sum()),
            "by_water_rule": by_rule,
        }
    record = {
        "schema": "floodguard.buildings_in_water.theos2_chips.v1",
        **envelope("THEOS-2 2025-07-30T03:33Z (sukhothai) and 2025-07-31T03:51Z (chip_003); WorldPop 2020; outlines of 2024",
                   "A water rule on one optical image, outlines drawn by a model, and a modelled population grid; no ground check."),
        "what_this_is": "On two THEOS-2 chips: the buildings that stand in water by the ground around them, and three readings "
                        "of residents in the water on the population grid. Neither water rule has been scored on the test "
                        "points yet; both are given and neither is called right.",
        "outlines": {"path": f"{OUTPUT_DIR}/{OUTLINES_NAME}", "sha256": sha256_file(ROOT / OUTPUT_DIR / OUTLINES_NAME)},
        "water_rules": {"rule_v1": "as run for the earlier checks", "rule_v2": {"freeze": RULE_FREEZE, "sha256": sha256_file(ROOT / RULE_FREEZE)}},
        "a_building_in_the_water": {
            "ring": f"pixels of 2 m more than {bw.RING_INNER_PX * PIXEL_M:g} m and at most {bw.RING_OUTER_PX * PIXEL_M:g} m from the "
                    "outline, nearer to this building than to any other",
            "assessed": f"a ring of at least {bw.MIN_RING_PX} pixels, at least {bw.MIN_ANSWERED_SHARE:g} of them with an answer",
            "in_the_water": f"at least {bw.IN_WATER_SHARE:g} of the answered pixels of the ring are water",
            "counted": f"centre at least {bw.EDGE_MARGIN_M:g} m inside the chip",
        },
        "population": {"grid": "WorldPop Thailand 100 m 2020 (tha_ppp_2020.tif), the grid of the planning score",
                       "cells_used": f"centre at least {CELL_INSIDE_M:g} m inside the chip, so that the whole cell is on the image "
                                     "(a detail fixed when the stage was written; the plan says 'in the chip')"},
        "chips": chips,
        "credits": [CREDIT, "Residents: WorldPop (CC BY 4.0).", "THEOS-2 sample imagery provided by GISTDA for GeoHackathon 2026."],
        "limits": LIMITS + [
            "On the image, 'in the water' is the water rule's reading of the ground 2 to 8 m from the wall. Water under trees "
            "is missed, so buildings in the water are under-counted where houses stand under trees.",
            "Two chips of two days in one region; neither is Mae Sai.",
        ],
    }
    previous = superseded(record_path, arguments)
    if previous is not None:
        record["supersedes"] = previous
    write_json(record_path, record)


# ---------------------------------------------------------------------------
# Stage 3: case SE1
# ---------------------------------------------------------------------------


def stage_district(arguments: argparse.Namespace) -> None:
    import shapely
    from scipy.spatial import cKDTree

    external = Path(arguments.external_root)
    record_path = ROOT / OUTPUT_DIR / DISTRICT_NAME
    guard(record_path, arguments)
    cache_path = external / CELL_CACHE
    receipt = json.loads((ROOT / CELL_RECEIPT).read_text(encoding="utf-8"))
    cache = np.load(cache_path, allow_pickle=True)
    need_mix = json.loads((ROOT / NEED_MIX).read_text(encoding="utf-8"))
    names = {unit: row["unit_name_en"] for unit, row in need_mix["by_tambon"].items()}

    runner = load_script("build_uncertainty_ensemble")
    cells_builder = load_script("build_cell_outcomes")
    frame_set = runner.FRAME_SETS[cells_builder.FRAME]
    found = runner.prepare(cells_builder.CASE, frame_set, external, external / runner.BOUNDARY_RELATIVE_PATH,
                           age_dir=Path(arguments.age_dir))
    levels = list(found.flood.extents)

    outlines = read_outlines(external, "mae_sai")
    centre = outlines.geometry.centroid
    points = shapely.points(centre.x.to_numpy(), centre.y.to_numpy())
    x, y = cache["x"], cache["y"]
    unit = np.array([str(value) for value in cache["unit_id"]])
    residents = cache["residents_worldpop_2020"].astype("float64")
    distance, nearest = cKDTree(np.column_stack([x, y])).query(np.column_stack([centre.x.to_numpy(), centre.y.to_numpy()]))
    in_a_cell = distance <= bw.CELL_REACH_M
    cells = len(x)
    held = np.bincount(nearest[in_a_cell], minlength=cells)

    def figures(level: str) -> dict[str, Any]:
        extent = found.flood.extents[level]
        shapely.prepare(extent)
        in_layer = np.asarray(shapely.covers(extent, points), dtype=bool)
        cell_centre = np.asarray(shapely.covers(extent, shapely.points(x, y)), dtype=bool)
        if not np.array_equal(cell_centre, cache[f"inside_{level}"]):
            raise BuildError(f"the flood layer at level {level} is not the one the cell cache was made with")
        held_wet = np.bincount(nearest[in_a_cell & in_layer], minlength=cells)
        rows = {}
        for key, mask in [("district", np.ones(cells, dtype=bool))] + [(code, unit == code) for code in sorted(names)]:
            readings = bw.residents_in_water(np.where(mask, residents, 0.0), cell_centre.astype("float64"), None, held, held_wet)
            mine = in_a_cell & mask[nearest]
            buildings = int(mine.sum())
            rows[key] = {
                **({"unit_name_en": names[key]} if key in names else {}),
                "buildings": buildings,
                "buildings_in_the_layer": int((mine & in_layer).sum()),
                "share_of_buildings_in_the_layer": None if buildings == 0 else round(float((mine & in_layer).sum()) / buildings, 4),
                "residents_in_the_water_by_the_centre_rule_all_cells": round(float(residents[mask & cell_centre].sum())),
                "share_of_residents_in_the_water_by_the_centre_rule_all_cells": round(
                    float(residents[mask & cell_centre].sum()) / float(residents[mask].sum()), 4),
                "on_the_cells_that_hold_a_building": readings,
                "on_the_centre_rule": bw.verdict(readings["buildings_minus_centre_rule_points"]),
                "on_the_cells_without_a_building": {
                    "cells": int((mask & (held == 0)).sum()),
                    "residents": round(float(residents[mask & (held == 0)].sum())),
                    "share_of_the_residents": round(float(residents[mask & (held == 0)].sum()) / float(residents[mask].sum()), 4),
                    "in_the_water_by_the_centre_rule": round(float(residents[mask & (held == 0) & cell_centre].sum())),
                    "share_in_the_water_by_the_centre_rule": None if not (mask & (held == 0)).any() else round(
                        float(residents[mask & (held == 0) & cell_centre].sum()) / float(residents[mask & (held == 0)].sum()), 4),
                },
            }
        return rows

    by_level = {level: figures(level) for level in levels}
    main = by_level["as_provided"]
    apart = [f"{row['unit_name_en']} ({row['on_the_cells_that_hold_a_building']['buildings_minus_centre_rule_points']:+g} points)"
             for key, row in main.items() if key != "district"
             and row["on_the_cells_that_hold_a_building"]["buildings_minus_centre_rule_points"] is not None
             and abs(row["on_the_cells_that_hold_a_building"]["buildings_minus_centre_rule_points"]) > bw.DIFFERENCE_POINTS]
    spread = {key: round(float(residents[unit == key].sum()) * (row["share_of_buildings_in_the_layer"] or 0.0))
              for key, row in main.items() if key != "district"}
    spread["district"] = sum(spread.values())
    spread["district_share"] = round(spread["district"] / float(residents.sum()), 4)
    record = {
        "schema": "floodguard.buildings_in_water.se1_mae_sai.v1",
        **envelope(need_mix["source_timestamp"] + "; building outlines of 2024",
                   "A scenario layer, outlines drawn by a model and a modelled population grid; nothing was checked on the ground."),
        "label": "scenario, not an observation",
        "what_this_is": "For case SE1: where the buildings of Mae Sai district stand against the flood layer of the scenario, "
                        "and residents in the water by the centre rule of the planning score against the same residents "
                        "spread over the buildings of their cell. It shows where buildings are, not that they were flooded.",
        "outlines": {"path": f"{OUTPUT_DIR}/{OUTLINES_NAME}", "sha256": sha256_file(ROOT / OUTPUT_DIR / OUTLINES_NAME)},
        "cells": {"receipt": CELL_RECEIPT, "sha256": sha256_file(ROOT / CELL_RECEIPT),
                  "cells": cells, "residents": round(float(residents.sum()))},
        "need_mix": {"path": NEED_MIX, "sha256": sha256_file(ROOT / NEED_MIX)},
        "a_building_in_the_layer": "the centre of its outline lies inside the flood layer",
        "a_building_and_its_cell": f"the demand cell whose centre is nearest, within {bw.CELL_REACH_M:g} m",
        "buildings": {"outlines_used": int(len(outlines)), "in_a_demand_cell": int(in_a_cell.sum()),
                      "not_within_reach_of_a_cell": int((~in_a_cell).sum())},
        "flood_levels": levels,
        "published_level": "as_provided",
        "by_flood_level": by_level,
        "tambons_where_the_two_readings_differ_by_more_than_5_points": apart,
        "computed_after_the_result_was_seen": {
            "not_in_the_plan": "The planned comparison leaves out the cells that hold no building. They hold a large share of "
                               "the modelled residents, so one more figure is given: the residents of each tambon spread over "
                               "all the buildings of that tambon. It is an illustration of how much the count depends on where "
                               "the grid puts people, not a second exposure count.",
            "residents_in_the_layer_if_spread_over_the_buildings_of_their_tambon": spread,
        },
        "credits": [CREDIT] + list(need_mix.get("credits", [])),
        "limits": LIMITS + [
            "There is no image in this comparison: a building inside the layer of the scenario is not a building that was flooded.",
            "A building belongs to the nearest cell centre, which is not always the cell it stands in at a cell edge.",
        ],
    }
    previous = superseded(record_path, arguments)
    if previous is not None:
        record["supersedes"] = previous
    write_json(record_path, record)
    district = main["district"]
    print(json.dumps({"buildings": district["buildings"], "share_in_layer": district["share_of_buildings_in_the_layer"],
                      "centre_rule_all_cells": district["share_of_residents_in_the_water_by_the_centre_rule_all_cells"],
                      "compared": district["on_the_cells_that_hold_a_building"], "apart": apart}, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    stages = parser.add_subparsers(dest="stage", required=True)
    for name in ("fetch", "chips", "district"):
        stage = stages.add_parser(name)
        stage.add_argument("--external-root", required=True)
        stage.add_argument("--replace", action="store_true")
        stage.add_argument("--reason", default="")
        if name == "district":
            stage.add_argument("--age-dir", required=True)
    arguments = parser.parse_args()
    {"fetch": stage_fetch, "chips": stage_chips, "district": stage_district}[arguments.stage](arguments)


if __name__ == "__main__":
    main()
