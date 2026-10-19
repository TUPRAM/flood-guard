"""Mud on the THEOS-2 scene of 17 September 2024, question 4 of the plan: development points, then the freeze.

Plan: ``docs/proposal_execution/theos2_17sep_recession_and_mud_plan_v1.md``, sections 4.2 and 4.3.

Stage ``points``
    Lays the four products on one 2 m grid, fits the four Theil-Sen lines that put the counts on the scale of the
    Sentinel-2 reflectance of 15 September 2024, reads ``mud_s0``, cuts its five groups, draws the 160 development
    points (seed 20261019) and writes sheets of three pictures per point, with a number and no group. The key and the
    sheets stay outside Git; the record in Git holds the lines, the group sizes and their SHA-256.
Stage ``freeze``
    Reads the labels the agent gave on the sheets, scores the three candidates on them (``mud_s2`` fitted on one
    order and scored on the other), applies the choice of the plan, writes the 2 m mud raster of the chosen rule
    outside Git and the freeze record in Git, with the labels.

    python scripts/build_theos2_17sep_mud.py points --external-root <root>
    python scripts/build_theos2_17sep_mud.py freeze --external-root <root> --labels <labels.json>

The development labels are the reading of an AI model, not of a person, and are never a reference. Report-only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import theos2_event_delivery as delivery_meta  # noqa: E402
from floodguard import theos2_mud as mud  # noqa: E402
from floodguard import theos2_study_event as study  # noqa: E402

PLAN = "docs/proposal_execution/theos2_17sep_recession_and_mud_plan_v1.md"
DELIVERY = "outputs/theos2_delivery/delivery_20240917_v1.json"
REFERENCE = "outputs/theos2_study_event_check/reference_20240917_v1.json"
OUTPUT_DIR = "outputs/theos2_17sep_mud"
POINTS_NAME = "development_points_v1.json"
FREEZE_NAME = "freeze_v1.json"
WORK = Path("proposal_execution") / "theos2_17sep_mud_v1"
STUDY_WORK = Path("proposal_execution") / "theos2_study_event_check_v1"
S2 = {"after": "earth_search/mae_sai_2024/S2B_47QNC_20240915_0_L2A", "before": "earth_search/mae_sai_2024/S2B_47QNC_20240905_0_L2A"}
S2_BANDS = {"red": "red.tif", "green": "green.tif", "blue": "blue.tif", "nir": "nir.tif"}
BUILDINGS = "proposal_execution/buildings_in_water/mae_sai_outlines.gpkg"
ROADS = "derived_context/mae_sai_2024/mae_sai_osm_roads.geojson"
NOT_ROADS = ("path", "footway", "steps")
BUILT_UP = 50  # WorldCover class
S2_CELL_M = 10.0
SHEET_POINTS = 6
SOURCE_TIMESTAMP = "THEOS-2 2024-09-17T03:54:20Z; Sentinel-2 L2A 2024-09-15T03:58:15Z and 2024-09-05T03:58:19Z"


class BuildError(RuntimeError):
    """A stage cannot run, or it would run out of the order the plan fixed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # LF bytes on every platform: records bind these files by SHA-256.
    path.write_bytes((json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


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


def envelope() -> dict[str, Any]:
    return {"generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source_timestamp": SOURCE_TIMESTAMP,
            "confidence_class": "low",
            "confidence_basis": "One optical image read by a colour rule; development labels by an AI model; nobody went to the ground.",
            "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
            "plan": {"path": PLAN, "sha256": sha256_file(ROOT / PLAN)}}


ASSUMPTIONS = [
    "Mud is a 2 m square more than half covered by a fresh deposit of the flood, read from one image; it is not a ground survey.",
    "The counts of the image are put on the scale of Sentinel-2 surface reflectance by one Theil-Sen line per band, fitted on the scene of two days earlier.",
    "Roofs are the Google Open Buildings v3 and Microsoft outlines widened by 1 m; a roof missing from them can read as mud.",
]
LIMITS = [
    "One image, about five days after the peak: mud cleared before it is not seen, and no mud never means a place stayed dry.",
    "Report-only. No published class changes and nothing enters a planning score.",
]


# ---------------------------------------------------------------------------
# The scene on one 2 m grid, with what each pixel may be
# ---------------------------------------------------------------------------


def read_product_2m(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """One product at 2 m, the mean of 4 by 4 pixels of 0.5 m read in strips, with its valid pixels."""

    import rasterio
    from rasterio.windows import Window

    with rasterio.open(path) as source:
        rows, columns = source.height // study.BLOCK, source.width // study.BLOCK
        image = np.zeros((4, rows, columns), dtype="float32")
        valid = np.zeros((rows, columns), dtype=bool)
        for first in range(0, rows, 256):
            last = min(rows, first + 256)
            block = source.read(window=Window(0, first * study.BLOCK, columns * study.BLOCK, (last - first) * study.BLOCK))
            image[:, first:last], valid[first:last] = study.block_mean(block)
    return image, valid


def scene_2m(external: Path, delivery: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The four bands on the grid of the delivery record, the first product by name kept where they overlap; the covered
    pixels; and the order index (``delivery_meta.ORDERS``) of each covered pixel."""

    grid = delivery["one_pixel_grid"]
    folder = external / delivery["work_folder_outside_git"]
    image = np.zeros((4, grid["rows"], grid["columns"]), dtype="float32")
    covered = np.zeros((grid["rows"], grid["columns"]), dtype=bool)
    order = np.full((grid["rows"], grid["columns"]), 255, dtype="uint8")
    for product in sorted(delivery["products"], key=lambda item: item["product"]):
        part, valid = read_product_2m(folder / product["image"]["path"])
        row = int(round((grid["north"] - product["header"]["transform"][5]) / grid["cell_m"]))
        column = int(round((product["header"]["transform"][2] - grid["west"]) / grid["cell_m"]))
        window = (slice(row, row + valid.shape[0]), slice(column, column + valid.shape[1]))
        new = valid & ~covered[window]
        for band in range(4):
            image[band][window][new] = part[band][new]
        order[window][new] = delivery_meta.ORDERS.index(product["order"])
        covered[window] |= new
        del part, valid
    return image, covered, order


def rasterize_lines_or_shapes(geometries: list[Any], grid: dict[str, Any], *, all_touched: bool) -> np.ndarray:
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    if not geometries:
        return np.zeros((grid["rows"], grid["columns"]), dtype=bool)
    return rasterize(((geometry, 1) for geometry in geometries), out_shape=(grid["rows"], grid["columns"]),
                     transform=from_origin(grid["west"], grid["north"], grid["cell_m"], grid["cell_m"]),
                     fill=0, all_touched=all_touched, dtype="uint8").astype(bool)


def grid_bounds_lonlat(grid: dict[str, Any]) -> tuple[float, float, float, float]:
    from pyproj import Transformer

    west, north = grid["west"], grid["north"]
    east, south = west + grid["columns"] * grid["cell_m"], north - grid["rows"] * grid["cell_m"]
    to_lonlat = Transformer.from_crs(delivery_meta.EPSG, 4326, always_xy=True).transform
    corners = [to_lonlat(x, y) for x in (west, east) for y in (south, north)]
    return (min(c[0] for c in corners) - 0.001, min(c[1] for c in corners) - 0.001, max(c[0] for c in corners) + 0.001, max(c[1] for c in corners) + 0.001)


def buildings_mask(external: Path, grid: dict[str, Any]) -> tuple[np.ndarray, int]:
    import pyogrio

    frame = pyogrio.read_dataframe(external / BUILDINGS, bbox=grid_bounds_lonlat(grid)).to_crs(delivery_meta.EPSG)
    return rasterize_lines_or_shapes(list(frame.geometry.buffer(1.0)), grid, all_touched=True), int(len(frame))


def roads_mask(external: Path, grid: dict[str, Any]) -> tuple[np.ndarray, int]:
    import pyogrio

    frame = pyogrio.read_dataframe(external / ROADS, bbox=grid_bounds_lonlat(grid))
    frame = frame[~frame["highway"].isin(NOT_ROADS)].to_crs(delivery_meta.EPSG)
    return rasterize_lines_or_shapes(list(frame.geometry.buffer(10.0)), grid, all_touched=False), int(len(frame))


def s2_window(grid: dict[str, Any], source_transform: Any) -> tuple[int, int, int, int, int, int]:
    """The Sentinel-2 cells over the grid, starting one cell before it, and the pixel offsets that put 2 m pixels in them.

    Returns (s2_row0, s2_column0, rows, columns, pad_rows, pad_columns): 2 m pixel (r, c) lies in window cell
    ((r + pad_rows) // 5, (c + pad_columns) // 5).
    """

    per = int(S2_CELL_M / grid["cell_m"])
    column0 = int(np.floor((grid["west"] - source_transform.c) / S2_CELL_M))
    row0 = int(np.floor((source_transform.f - grid["north"]) / S2_CELL_M))
    pad_columns = int(round((grid["west"] - (source_transform.c + column0 * S2_CELL_M)) / grid["cell_m"]))
    pad_rows = int(round(((source_transform.f - row0 * S2_CELL_M) - grid["north"]) / grid["cell_m"]))
    if not (0 <= pad_columns < per and 0 <= pad_rows < per):
        raise BuildError("the 2 m grid does not nest in the Sentinel-2 cells")
    rows = -(-(grid["rows"] + pad_rows) // per)
    columns = -(-(grid["columns"] + pad_columns) // per)
    return row0, column0, rows, columns, pad_rows, pad_columns


def read_s2(external: Path, key: str, grid: dict[str, Any]) -> tuple[dict[str, np.ndarray], np.ndarray, tuple[int, ...]]:
    """Reflectance (counts / 10,000) of the four bands and the scene class, on the Sentinel-2 cells over the grid."""

    import rasterio
    from rasterio.windows import Window

    folder = external / S2[key]
    with rasterio.open(folder / "red.tif") as source:
        window = s2_window(grid, source.transform)
    row0, column0, rows, columns = window[:4]
    bands = {}
    for name, file in S2_BANDS.items():
        with rasterio.open(folder / file) as source:
            bands[name] = source.read(1, window=Window(column0, row0, columns, rows), boundless=True, fill_value=0).astype("float32") / 10000.0
    with rasterio.open(folder / "scl.tif") as source:
        scl = source.read(1, window=Window(column0 // 2, row0 // 2, columns // 2 + 2, rows // 2 + 2), boundless=True, fill_value=0)
    scl = np.repeat(np.repeat(scl, 2, axis=0), 2, axis=1)[row0 % 2:row0 % 2 + rows, column0 % 2:column0 % 2 + columns]
    return bands, scl, window


def cells_of(values: np.ndarray, window: tuple[int, ...]) -> np.ndarray:
    """The mean of a 2 m raster in each Sentinel-2 cell of the window (pixels outside the grid count as 0)."""

    _row0, _column0, rows, columns, pad_rows, pad_columns = window
    per = 5
    padded = np.zeros((rows * per, columns * per), dtype="float32")
    padded[pad_rows:pad_rows + values.shape[0], pad_columns:pad_columns + values.shape[1]] = values
    return padded.reshape(rows, per, columns, per).mean(axis=(1, 3))


def to_pixels(cells: np.ndarray, shape: tuple[int, int], window: tuple[int, ...]) -> np.ndarray:
    """A value per Sentinel-2 cell spread to the 2 m pixels inside it."""

    pad_rows, pad_columns = window[4], window[5]
    rows = (np.arange(shape[0]) + pad_rows) // 5
    columns = (np.arange(shape[1]) + pad_columns) // 5
    return cells[np.ix_(rows, columns)]


def built_up_pixels(external: Path, grid: dict[str, Any]) -> np.ndarray:
    """WorldCover built-up under each 2 m pixel centre, from the 10 m lattice of the district."""

    event = load_script("build_theos2_study_event_check")
    area = event.mae_sai(external)
    west, north, rows, columns = area["grid"]
    xs = grid["west"] + (np.arange(grid["columns"]) + 0.5) * grid["cell_m"]
    ys = grid["north"] - (np.arange(grid["rows"]) + 0.5) * grid["cell_m"]
    column_index = np.floor((xs - west) / 10.0).astype(int)
    row_index = np.floor((north - ys) / 10.0).astype(int)
    inside_columns = (column_index >= 0) & (column_index < columns)
    inside_rows = (row_index >= 0) & (row_index < rows)
    built = area["land_cover"] == BUILT_UP
    result = np.zeros((grid["rows"], grid["columns"]), dtype=bool)
    result[np.ix_(inside_rows, inside_columns)] = built[np.ix_(row_index[inside_rows], column_index[inside_columns])]
    return result


# ---------------------------------------------------------------------------
# Stage points
# ---------------------------------------------------------------------------


def check_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    delivery = json.loads((ROOT / DELIVERY).read_text(encoding="utf-8"))
    reference = json.loads((ROOT / REFERENCE).read_text(encoding="utf-8"))
    if reference["delivery"]["sha256"] != sha256_file(ROOT / DELIVERY):
        raise BuildError("the delivery record changed after the reference was built")
    if not reference.get("looked_at"):
        raise BuildError("the reference of the scene has no look written; the mud track comes after it")
    return delivery, reference


def scene_layers(external: Path, delivery: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    """Everything the candidates read, cached outside Git so that the freeze reads exactly what the points read."""

    import rasterio

    work = external / WORK
    cache = work / "scene_2m.npz"
    if cache.exists():
        with np.load(cache) as stored:
            return {name: stored[name] for name in stored.files} | json.loads((work / "scene_2m.json").read_text(encoding="utf-8"))
    grid = delivery["one_pixel_grid"]
    water_path = external / STUDY_WORK / "reference_20240917_water_2m.tif"
    bound = {item["name"]: item["sha256"] for item in reference["rasters_outside_git"]}
    if sha256_file(water_path) != bound[water_path.name]:
        raise BuildError("the rule v2 raster is not the one the reference record binds")
    with rasterio.open(water_path) as source:
        water = source.read(1)
    image, covered, order = scene_2m(external, delivery)
    roofs, outlines = buildings_mask(external, grid)
    roads, road_lines = roads_mask(external, grid)
    built = built_up_pixels(external, grid)
    observable = covered & (water == 0) & ~roofs

    after, scl_after, window = read_s2(external, "after", grid)
    before, scl_before, _ = read_s2(external, "before", grid)
    green_before = (np.isin(scl_before, mud.CLEAR_SCL)) & (mud.ndvi(before["red"], before["nir"]) >= mud.GREEN_BEFORE_NDVI)
    before_ok = to_pixels(green_before, observable.shape, window) | roads | built

    # The scaling cells: every 2 m pixel observable, clear on 15 September, a reflectance in every band.
    share = cells_of(observable.astype("float32"), window)
    means = [cells_of(np.where(observable, image[band], 0.0), window) for band in range(4)]
    usable = (share >= 0.999) & np.isin(scl_after, mud.CLEAR_SCL) & np.all([after[name] > 0 for name in S2_BANDS], axis=0)
    rows, columns = np.nonzero(usable)
    rng = np.random.default_rng(mud.SCALING_SEED)
    pick = rng.choice(rows.size, size=min(mud.SCALING_CELLS, rows.size), replace=False)
    lines = {}
    for band, name in enumerate(("red", "green", "blue", "nir")):
        counts = means[band][rows[pick], columns[pick]] / share[rows[pick], columns[pick]]
        lines[name] = mud.theil_sen(counts, after[name][rows[pick], columns[pick]])
    scaling = {"lines": lines, "cells_usable": int(rows.size), "cells_drawn": int(pick.size), "seed": mud.SCALING_SEED,
               "sentinel2_bands": {"red": "B04", "green": "B03", "blue": "B02", "nir": "B08"}}
    work.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, image=image, covered=covered, order=order, observable=observable, before_ok=before_ok)
    meta = {"scaling": scaling, "outlines_read": outlines, "road_lines_read": road_lines,
            "masks_km2": {"covered": round(float(covered.sum()) * 4e-6, 3), "observable": round(float(observable.sum()) * 4e-6, 3),
                          "roofs_in_covered": round(float((roofs & covered).sum()) * 4e-6, 3),
                          "condition_before_met_in_observable": round(float((before_ok & observable).sum()) * 4e-6, 3)}}
    write_json(work / "scene_2m.json", meta)
    return {"image": image, "covered": covered, "order": order, "observable": observable, "before_ok": before_ok} | meta


def scaled_bands(layers: dict[str, Any]) -> dict[str, np.ndarray]:
    return {name: mud.scale(layers["image"][band], layers["scaling"]["lines"][name]) for band, name in enumerate(("red", "green", "blue", "nir"))}


def candidate(name: str, bands: dict[str, np.ndarray], layers: dict[str, Any], limits: mud.MudLimits | None = None) -> np.ndarray:
    colour = mud.colour_rule(bands["red"], bands["green"], bands["blue"], bands["nir"], limits or mud.MudLimits())
    return mud.answer(colour, layers["observable"], None if name == "mud_s0" else layers["before_ok"])


def group_sizes(group_raster: np.ndarray, order_raster: np.ndarray) -> dict[tuple[str, str], int]:
    sizes = {}
    for group_index, group in enumerate(mud.GROUPS):
        for order_index, order in enumerate(delivery_meta.ORDERS):
            sizes[(group, order)] = int(((group_raster == group_index) & (order_raster == order_index)).sum())
    return sizes


def picture_scale(layers: dict[str, Any]) -> dict[str, float]:
    sample = layers["covered"][::7, ::7]
    return {"red": float(np.percentile(layers["image"][0][::7, ::7][sample], 99)), "nir": float(np.percentile(layers["image"][3][::7, ::7][sample], 99))}


def point_pictures(external: Path, delivery: dict[str, Any], x: float, y: float, scale: dict[str, float]) -> list[np.ndarray]:
    """Three pictures of a point: 64 m at 0.5 m in true colour and in false colour, 320 m at 1 m; the 2 m square outlined."""

    import rasterio
    from rasterio.windows import from_bounds

    folder = external / delivery["work_folder_outside_git"]
    for product in sorted(delivery["products"], key=lambda item: item["product"]):
        with rasterio.open(folder / product["image"]["path"]) as source:
            left, bottom, right, top = source.bounds
            if not (left <= x <= right and bottom <= y <= top):
                continue
            near = source.read(window=from_bounds(x - 32, y - 32, x + 32, y + 32, source.transform), boundless=True, fill_value=0).astype("float32")
            if near[0, 62:66, 62:66].min() == 0:
                continue
            wide = source.read(window=from_bounds(x - 160, y - 160, x + 160, y + 160, source.transform), boundless=True, fill_value=0).astype("float32")
        wide = wide.reshape(4, 320, 2, 320, 2).mean(axis=(2, 4))

        def colour(a: np.ndarray, false: bool) -> np.ndarray:
            stack = (np.stack([a[3] / scale["nir"], a[0] / scale["red"], a[1] / scale["red"]], -1) if false
                     else np.stack([a[0], a[1], a[2]], -1) / scale["red"])
            return np.clip(stack * 255, 0, 255).astype("uint8")

        true, false, context = colour(near, False), colour(near, True), colour(wide, False)
        for picture in (true, false):
            picture[61, 61:67] = picture[66, 61:67] = (255, 230, 0)
            picture[61:67, 61] = picture[61:67, 66] = (255, 230, 0)
        context[128, 128:192] = context[191, 128:192] = (255, 230, 0)
        context[128:192, 128] = context[128:192, 191] = (255, 230, 0)
        return [np.kron(true, np.ones((2, 2, 1), dtype="uint8")), np.kron(false, np.ones((2, 2, 1), dtype="uint8")), context]
    raise BuildError(f"no product shows the point at {x}, {y}")


def write_sheets(external: Path, delivery: dict[str, Any], points: list[dict[str, Any]], scale: dict[str, float], prefix: str) -> list[Path]:
    from PIL import Image, ImageDraw

    work = external / WORK / "sheets"
    work.mkdir(parents=True, exist_ok=True)
    cell_w, cell_h, gap = 256 + 256 + 320 + 12, 320 + 22, 16
    paths = []
    for sheet_index in range(0, len(points), SHEET_POINTS):
        sheet = Image.new("RGB", (2 * cell_w + gap, 3 * cell_h), (20, 20, 20))
        draw = ImageDraw.Draw(sheet)
        for slot, point in enumerate(points[sheet_index:sheet_index + SHEET_POINTS]):
            left, top = (slot % 2) * (cell_w + gap), (slot // 2) * cell_h
            draw.text((left + 4, top + 4), point["name"], fill=(255, 255, 255))
            pictures = point_pictures(external, delivery, point["x"], point["y"], scale)
            offset = left
            for picture in pictures:
                sheet.paste(Image.fromarray(picture), (offset, top + 22))
                offset += picture.shape[1] + 6
        path = work / f"{prefix}_{sheet_index // SHEET_POINTS + 1:02d}.png"
        sheet.save(path, optimize=True)
        paths.append(path)
    return paths


def stage_points(arguments: argparse.Namespace) -> None:
    external = Path(arguments.external_root)
    work = external / WORK
    record_path = ROOT / OUTPUT_DIR / POINTS_NAME
    if record_path.exists():
        raise BuildError("the development points are drawn once")
    delivery, reference = check_inputs()
    layers = scene_layers(external, delivery, reference)
    bands = scaled_bands(layers)
    s0 = candidate("mud_s0", bands, layers)
    del bands
    group_raster = mud.groups(s0)
    group_raster[~layers["covered"]] = 255
    sizes = group_sizes(group_raster, layers["order"])
    counts = mud.allocate(sizes, mud.DEVELOPMENT_POINTS, delivery_meta.ORDERS)
    points = mud.draw(group_raster, layers["order"], delivery_meta.ORDERS, counts, mud.DEVELOPMENT_SEED)
    grid = delivery["one_pixel_grid"]
    for index, point in enumerate(points, start=1):
        point.update({"name": f"d{index:03d}", "x": grid["west"] + (point["column"] + 0.5) * grid["cell_m"],
                      "y": grid["north"] - (point["row"] + 0.5) * grid["cell_m"]})
    key_path = work / "development_key_v1.json"
    write_json(key_path, {"points": points})
    sheets = write_sheets(external, delivery, points, picture_scale(layers), "development")
    s0_path = work / "mud_s0_2m.tif"
    write_raster(s0_path, s0, grid)
    record = {
        "schema": "floodguard.theos2_17sep_mud_points.v1",
        **envelope(),
        "what_this_is": "The scaling of the THEOS-2 counts, the groups of mud_s0 and the 160 development points of question 4, drawn before any label.",
        "reference": {"path": REFERENCE, "sha256": sha256_file(ROOT / REFERENCE)},
        "delivery": {"path": DELIVERY, "sha256": sha256_file(ROOT / DELIVERY)},
        "scaling": layers["scaling"],
        "inputs": {"buildings": BUILDINGS, "outlines_read": layers["outlines_read"], "roads": ROADS, "road_lines_read": layers["road_lines_read"],
                   "roads_left_out": list(NOT_ROADS), "built_up": "WorldCover 2021 class 50 on the 10 m lattice of the district",
                   "roof_rasterization": "outlines widened by 1 m, every pixel they touch",
                   "condition_before": "the Sentinel-2 cell under the pixel centre is clear and has NDVI 0.45 or more on 5 September 2024, or the pixel centre lies within 10 m of a mapped road, or in WorldCover built-up"},
        "masks_km2": layers["masks_km2"],
        "mud_s0_km2_in_the_scene": round(float((s0 == mud.MUD_YES).sum()) * 4e-6, 3),
        "group_pixels": {f"{group}|{order}": size for (group, order), size in sizes.items()},
        "points_per_group": {f"{group}|{order}": count for (group, order), count in counts.items() if count},
        "seed": mud.DEVELOPMENT_SEED,
        "files_outside_git": [{"name": path.relative_to(work).as_posix(), "sha256": sha256_file(path)} for path in (key_path, s0_path, *sheets)],
        "labels": "The agent labels the points from the sheets alone: a number and three pictures, never the group. Labels: " + ", ".join(mud.LABELS) + ".",
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    write_json(record_path, record)
    print(json.dumps({"scaling": layers["scaling"]["lines"], "mud_s0_km2": record["mud_s0_km2_in_the_scene"], "sheets": len(sheets)}, indent=1))


def write_raster(path: Path, values: np.ndarray, grid: dict[str, Any]) -> None:
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1], count=1, dtype="uint8", nodata=255,
                       crs=f"EPSG:{delivery_meta.EPSG}", transform=from_origin(grid["west"], grid["north"], grid["cell_m"], grid["cell_m"]),
                       compress="deflate") as target:
        target.write(values, 1)


# ---------------------------------------------------------------------------
# Stage freeze
# ---------------------------------------------------------------------------


def stage_freeze(arguments: argparse.Namespace) -> None:
    external = Path(arguments.external_root)
    work = external / WORK
    points_path, freeze_path = ROOT / OUTPUT_DIR / POINTS_NAME, ROOT / OUTPUT_DIR / FREEZE_NAME
    if freeze_path.exists():
        raise BuildError("the mud rule is frozen once")
    if not points_path.exists():
        raise BuildError("no development points")
    record = json.loads(points_path.read_text(encoding="utf-8"))
    if record["plan"]["sha256"] != sha256_file(ROOT / PLAN):
        raise BuildError("the plan changed after the points were drawn")
    for item in record["files_outside_git"]:
        if sha256_file(work / item["name"]) != item["sha256"]:
            raise BuildError(f"{item['name']} is not the file the points record binds")
    delivery, reference = check_inputs()
    labels_path = Path(arguments.labels)
    labels = json.loads(labels_path.read_text(encoding="utf-8"))["labels"]
    points = json.loads((work / "development_key_v1.json").read_text(encoding="utf-8"))["points"]
    missing = [point["name"] for point in points if labels.get(point["name"]) not in mud.LABELS]
    if missing:
        raise BuildError(f"points without a label of the plan: {missing[:5]}")
    for point in points:
        point["label"] = labels[point["name"]]
    sizes = {tuple(key.split("|")): value for key, value in record["group_pixels"].items()}

    layers = scene_layers(external, delivery, reference)
    if layers["scaling"] != record["scaling"]:
        raise BuildError("the cached scene is not the one the points were drawn on")
    bands = scaled_bands(layers)
    at = (np.array([point["row"] for point in points]), np.array([point["column"] for point in points]))

    def said(raster: np.ndarray) -> list[bool]:
        return (raster[at] == mud.MUD_YES).tolist()

    def score_on(order: str | None, saids: list[bool]) -> dict[str, Any]:
        chosen = [(point, value) for point, value in zip(points, saids) if order is None or point["order"] == order]
        kept = [point for point, _ in chosen]
        return mud.weighted_f1(kept, [value for _, value in chosen], mud.point_weights(sizes, kept))

    answers = {"mud_s0": said(candidate("mud_s0", bands, layers)), "mud_s1": said(candidate("mud_s1", bands, layers))}
    grid_answers = [said(candidate("mud_s2", bands, layers, limits)) for limits in mud.threshold_grid()]
    by_order = {name: {order: score_on(order, values) for order in delivery_meta.ORDERS} for name, values in answers.items()}
    scores = {name: mud.mean_score([by_order[name][order]["f1"] for order in delivery_meta.ORDERS]) for name in answers}

    def best(order: str | None) -> int:
        values = [score_on(order, values)["f1"] for values in grid_answers]
        return int(np.argmax([-1.0 if value is None else value for value in values]))

    crossed = {}
    for fit, held in (delivery_meta.ORDERS, delivery_meta.ORDERS[::-1]):
        index = best(fit)
        crossed[f"fitted_on_{fit}"] = {"limits": mud.limits_dict(mud.threshold_grid()[index]), "scored_on": held,
                                       **score_on(held, grid_answers[index])}
    scores["mud_s2"] = mud.mean_score([item["f1"] for item in crossed.values()])
    chosen = mud.choose(scores)
    limits = mud.threshold_grid()[best(None)] if chosen == "mud_s2" else mud.MudLimits()
    final = candidate(chosen, bands, layers, limits)
    grid = delivery["one_pixel_grid"]
    raster = work / "mud_frozen_2m.tif"
    write_raster(raster, final, grid)
    result = {
        "schema": "floodguard.theos2_17sep_mud_freeze.v1",
        **envelope(),
        "what_this_is": "The mud rule of question 4, chosen on 160 development points the agent labelled and frozen before any test point is drawn.",
        "points_record": {"path": f"{OUTPUT_DIR}/{POINTS_NAME}", "sha256": sha256_file(points_path)},
        "labels": {"by": "the agent that builds the rule (an AI model), from the sheets alone", "file_sha256": sha256_file(labels_path),
                   "counts": {label: sum(1 for point in points if point["label"] == label) for label in mud.LABELS},
                   "by_point": {point["name"]: point["label"] for point in points},
                   "note": "Development data, not a reference."},
        "scores": {"mud_s0": {"mean_f1": scores["mud_s0"], "by_order": by_order["mud_s0"]},
                   "mud_s1": {"mean_f1": scores["mud_s1"], "by_order": by_order["mud_s1"]},
                   "mud_s2": {"mean_f1": scores["mud_s2"], "crossed": crossed}},
        "choice_rule": f"mud_s0 stays unless mud_s1 is better by {mud.CHOICE_MARGIN} or more; the one kept stays unless mud_s2 is better than it by {mud.CHOICE_MARGIN} or more.",
        "chosen": chosen,
        "frozen_rule": {"candidate": chosen, "limits": mud.limits_dict(limits), "scaling_lines": record["scaling"]["lines"],
                        "condition_before": chosen != "mud_s0", "min_object_px": mud.MIN_OBJECT_PX,
                        "code": "floodguard.theos2_mud (colour_rule, answer) and scripts/build_theos2_17sep_mud.py (candidate)"},
        "mud_km2_in_the_scene": round(float((final == mud.MUD_YES).sum()) * 4e-6, 3),
        "raster_outside_git": {"name": raster.name, "sha256": sha256_file(raster), "values": "1 mud, 0 not mud, 255 unobservable or outside the scene"},
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    write_json(freeze_path, result)
    print(json.dumps({"scores": {name: value for name, value in scores.items()}, "chosen": chosen, "limits": mud.limits_dict(limits),
                      "mud_km2": result["mud_km2_in_the_scene"]}, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("stage", choices=("points", "freeze"))
    parser.add_argument("--external-root", required=True)
    parser.add_argument("--labels")
    arguments = parser.parse_args()
    if arguments.stage == "freeze" and not arguments.labels:
        raise BuildError("the freeze stage needs --labels")
    {"points": stage_points, "freeze": stage_freeze}[arguments.stage](arguments)


if __name__ == "__main__":
    main()
