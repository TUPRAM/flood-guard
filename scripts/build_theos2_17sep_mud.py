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

Stage ``score`` (section 4.4)
    Checks the three label files against the draw, takes them in beside the key outside Git, and scores the frozen rule
    once on the label at least two of three gave, area-weighted by group, against the bar of 0.60.

    python scripts/build_theos2_17sep_mud.py points --external-root <root>
    python scripts/build_theos2_17sep_mud.py freeze --external-root <root> --labels <labels.json>
    python scripts/build_theos2_17sep_mud.py score --external-root <root> --label-files <a.json> <b.json> <c.json>

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

    area = load_script("build_theos2_study_event_check").mae_sai(external)
    return lattice_pixels(area, area["land_cover"] == BUILT_UP, grid)


def lattice_pixels(area: dict[str, Any], values: np.ndarray, grid: dict[str, Any]) -> np.ndarray:
    """A boolean of the 10 m lattice of the district under each 2 m pixel centre; False outside the lattice."""

    built = values
    west, north, rows, columns = area["grid"]
    xs = grid["west"] + (np.arange(grid["columns"]) + 0.5) * grid["cell_m"]
    ys = grid["north"] - (np.arange(grid["rows"]) + 0.5) * grid["cell_m"]
    column_index = np.floor((xs - west) / 10.0).astype(int)
    row_index = np.floor((north - ys) / 10.0).astype(int)
    inside_columns = (column_index >= 0) & (column_index < columns)
    inside_rows = (row_index >= 0) & (row_index < rows)
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


# ---------------------------------------------------------------------------
# Amendment 1: new masks, mud_s3 and mud_s4, forty points in the opened ground, the second freeze
# ---------------------------------------------------------------------------

AMENDMENT = "docs/proposal_execution/theos2_17sep_recession_and_mud_plan_v1_amendment_1.md"
POINTS_V2_NAME = "development_points_v2.json"
FREEZE_V2_NAME = "freeze_v2.json"
OSM_WATER = "derived_context/mae_sai_2024/mae_sai_osm_multipolygons.gpkg"
OSM_WATER_TAGS = r'"natural"=>"water"|"water"=>|"landuse"=>"(?:aquaculture|reservoir|basin)"'
WATER_SCL = 6


def water_before(external: Path, grid: dict[str, Any], shape: tuple[int, int]) -> tuple[np.ndarray, dict[str, Any]]:
    """Water before the flood under each 2 m pixel: Sentinel-2 of 5 September, OSM water, the permanent water of the lattice."""

    import pyogrio
    import rasterio
    from rasterio.windows import Window

    bands, scl, window = read_s2(external, "before", grid)
    row0, column0, rows, columns = window[:4]
    with rasterio.open(external / S2["before"] / "swir16.tif") as source:
        swir = source.read(1, window=Window(column0 // 2, row0 // 2, columns // 2 + 2, rows // 2 + 2), boundless=True, fill_value=0)
    swir = np.repeat(np.repeat(swir, 2, axis=0), 2, axis=1)[row0 % 2:row0 % 2 + rows, column0 % 2:column0 % 2 + columns].astype("float32") / 10000.0
    with np.errstate(divide="ignore", invalid="ignore"):
        mndwi = np.where(bands["green"] + swir > 0, (bands["green"] - swir) / (bands["green"] + swir), np.nan)
    s2_water = (scl == WATER_SCL) | (np.isin(scl, mud.CLEAR_SCL) & (mndwi > 0))
    frame = pyogrio.read_dataframe(external / OSM_WATER, bbox=grid_bounds_lonlat(grid))
    frame = frame[frame["other_tags"].fillna("").str.contains(OSM_WATER_TAGS, regex=True)].to_crs(delivery_meta.EPSG)
    osm = rasterize_lines_or_shapes(list(frame.geometry), grid, all_touched=False)
    area = load_script("build_theos2_study_event_check").mae_sai(external)
    permanent = lattice_pixels(area, area["permanent_water"], grid)
    from_s2 = to_pixels(s2_water, shape, window)
    detail = {"sentinel2_cells_water_on_5_september": int(s2_water.sum()), "sentinel2_cells_clear_on_5_september": int(np.isin(scl, mud.CLEAR_SCL).sum()),
              "sentinel2_cells_in_window": int(scl.size), "osm_polygons": int(len(frame)),
              "km2": {"sentinel2": round(float(from_s2.sum()) * 4e-6, 3), "osm": round(float(osm.sum()) * 4e-6, 3),
                      "permanent": round(float(permanent.sum()) * 4e-6, 3)}}
    return from_s2 | osm | permanent, detail


def scene_layers_v2(external: Path, delivery: dict[str, Any], reference: dict[str, Any], layers: dict[str, Any]) -> dict[str, Any]:
    """The masks of amendment 1, cached outside Git beside those of plan v1."""

    import rasterio

    work = external / WORK
    cache = work / "scene_2m_v2.npz"
    if cache.exists():
        with np.load(cache) as stored:
            return {name: stored[name] for name in stored.files} | json.loads((work / "scene_2m_v2.json").read_text(encoding="utf-8"))
    grid = delivery["one_pixel_grid"]
    with rasterio.open(external / STUDY_WORK / "reference_20240917_water_2m.tif") as source:
        rule_v2 = source.read(1)
    roofs, _outlines = buildings_mask(external, grid)
    before, detail = water_before(external, grid, rule_v2.shape)
    cloud = layers["covered"] & (rule_v2 == 255)
    observable = layers["covered"] & ~cloud & ~roofs & ~before
    opened = observable & ~layers["observable"]
    np.savez_compressed(cache, observable_v2=observable, opened=opened)
    meta = {"water_before": detail,
            "masks_v2_km2": {"observable": round(float(observable.sum()) * 4e-6, 3), "opened": round(float(opened.sum()) * 4e-6, 3),
                             "cloud": round(float(cloud.sum()) * 4e-6, 3),
                             "water_before_in_covered": round(float((before & layers["covered"]).sum()) * 4e-6, 3),
                             "observable_in_v1_now_water_before": round(float((layers["observable"] & before).sum()) * 4e-6, 3)}}
    write_json(work / "scene_2m_v2.json", meta)
    return {"observable_v2": observable, "opened": opened} | meta


def candidate_v2(bands: dict[str, np.ndarray], layers: dict[str, Any], limits: mud.MudLimits | None = None) -> np.ndarray:
    colour = mud.colour_rule(bands["red"], bands["green"], bands["blue"], bands["nir"], limits or mud.MudLimits())
    return mud.answer(colour, layers["observable_v2"], None, mud.MIN_OBJECT_PX_V2)


def strata_v2(s0: np.ndarray, s3: np.ndarray, layers: dict[str, Any]) -> tuple[np.ndarray, list[str]]:
    """The strata of amendment 1: the groups of mud_s0 outside the opened ground, two strata of mud_s3 inside it."""

    names = [*mud.GROUPS, *mud.OPENED_STRATA]
    raster = mud.groups(s0)
    raster[~layers["covered"]] = 255
    raster[layers["opened"] & (s3 == mud.MUD_YES)] = len(mud.GROUPS)
    raster[layers["opened"] & (s3 != mud.MUD_YES)] = len(mud.GROUPS) + 1
    return raster, names


def stage_points2(arguments: argparse.Namespace) -> None:
    from floodguard import theos2_water_rule_v2 as v2

    external = Path(arguments.external_root)
    work = external / WORK
    record_path = ROOT / OUTPUT_DIR / POINTS_V2_NAME
    if record_path.exists():
        raise BuildError("the points of amendment 1 are drawn once")
    if not (ROOT / OUTPUT_DIR / FREEZE_NAME).exists() or any((ROOT / OUTPUT_DIR).glob("test_*")):
        raise BuildError("amendment 1 comes after the first freeze and before any test point")
    delivery, reference = check_inputs()
    layers = scene_layers(external, delivery, reference)
    layers |= scene_layers_v2(external, delivery, reference, layers)
    bands = scaled_bands(layers)
    s0, s3 = candidate("mud_s0", bands, layers), candidate_v2(bands, layers)
    del bands
    raster, names = strata_v2(s0, s3, layers)
    orders = delivery_meta.ORDERS
    sizes = {(name, order): int(((raster == index) & (layers["order"] == order_index)).sum())
             for index, name in enumerate(names) for order_index, order in enumerate(orders)}
    old = json.loads((work / "development_key_v1.json").read_text(encoding="utf-8"))["points"]
    free = v2.away_from(raster.shape, [(point["row"], point["column"]) for point in old], mud.KEEP_AWAY_PX)
    opened_raster = np.where(raster >= len(mud.GROUPS), raster - len(mud.GROUPS), 255).astype("uint8")
    opened_sizes = {(name, order): sizes[(name, order)] for name in mud.OPENED_STRATA for order in orders}
    counts = mud.allocate(opened_sizes, mud.OPENED_POINTS, orders, mud.OPENED_STRATA, spill_to="opened_not_mud")
    points = mud.draw(opened_raster, layers["order"], orders, counts, mud.NEW_DEVELOPMENT_SEED, free=free, group_names=mud.OPENED_STRATA)
    grid = delivery["one_pixel_grid"]
    for index, point in enumerate(points, start=1):
        point.update({"name": f"e{index:03d}", "x": grid["west"] + (point["column"] + 0.5) * grid["cell_m"],
                      "y": grid["north"] - (point["row"] + 0.5) * grid["cell_m"]})
    key_path = work / "development_key_v2.json"
    write_json(key_path, {"points": points})
    sheets = write_sheets(external, delivery, points, picture_scale(layers), "development2")
    record = {
        "schema": "floodguard.theos2_17sep_mud_points.v2",
        **envelope(),
        "what_this_is": "The masks of amendment 1, the strata of the rescore and the 40 new development points in the ground the new masks open, drawn before any of them was labelled.",
        "amendment": {"path": AMENDMENT, "sha256": sha256_file(ROOT / AMENDMENT)},
        "points_v1": {"path": f"{OUTPUT_DIR}/{POINTS_NAME}", "sha256": sha256_file(ROOT / OUTPUT_DIR / POINTS_NAME)},
        "freeze_v1": {"path": f"{OUTPUT_DIR}/{FREEZE_NAME}", "sha256": sha256_file(ROOT / OUTPUT_DIR / FREEZE_NAME)},
        "water_before": layers["water_before"], "masks_v2_km2": layers["masks_v2_km2"],
        "mud_s3_km2_in_the_scene": round(float((s3 == mud.MUD_YES).sum()) * 4e-6, 3),
        "stratum_pixels": {f"{name}|{order}": size for (name, order), size in sizes.items()},
        "points_per_stratum": {f"{name}|{order}": count for (name, order), count in counts.items() if count},
        "seed": mud.NEW_DEVELOPMENT_SEED,
        "files_outside_git": [{"name": path.relative_to(work).as_posix(), "sha256": sha256_file(path)} for path in (key_path, *sheets)],
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    write_json(record_path, record)
    print(json.dumps({"masks_v2_km2": layers["masks_v2_km2"], "water_before": layers["water_before"]["km2"],
                      "mud_s3_km2": record["mud_s3_km2_in_the_scene"], "points": record["points_per_stratum"], "sheets": len(sheets)}, indent=1))


def stage_freeze2(arguments: argparse.Namespace) -> None:
    external = Path(arguments.external_root)
    work = external / WORK
    points_path, freeze_path = ROOT / OUTPUT_DIR / POINTS_V2_NAME, ROOT / OUTPUT_DIR / FREEZE_V2_NAME
    if freeze_path.exists():
        raise BuildError("the second freeze is made once")
    record = json.loads(points_path.read_text(encoding="utf-8"))
    if record["amendment"]["sha256"] != sha256_file(ROOT / AMENDMENT):
        raise BuildError("the amendment changed after its points were drawn")
    for item in record["files_outside_git"]:
        if sha256_file(work / item["name"]) != item["sha256"]:
            raise BuildError(f"{item['name']} is not the file the points record binds")
    first = json.loads((ROOT / OUTPUT_DIR / FREEZE_NAME).read_text(encoding="utf-8"))
    old_labels_path, new_labels_path = Path(arguments.old_labels), Path(arguments.labels)
    if sha256_file(old_labels_path) != first["labels"]["file_sha256"]:
        raise BuildError("the labels of plan v1 are not the file the first freeze binds")
    old_labels = json.loads(old_labels_path.read_text(encoding="utf-8"))["labels"]
    new_labels = json.loads(new_labels_path.read_text(encoding="utf-8"))["labels"]
    old = json.loads((work / "development_key_v1.json").read_text(encoding="utf-8"))["points"]
    new = json.loads((work / "development_key_v2.json").read_text(encoding="utf-8"))["points"]
    for point in old:
        point["label"] = old_labels[point["name"]]
    for point in new:
        point["label"] = new_labels.get(point["name"])
    if any(point["label"] not in mud.LABELS for point in new):
        raise BuildError("a new point has no label of the plan")
    delivery, reference = check_inputs()
    layers = scene_layers(external, delivery, reference)
    layers |= scene_layers_v2(external, delivery, reference, layers)
    bands = scaled_bands(layers)
    s0, s3 = candidate("mud_s0", bands, layers), candidate_v2(bands, layers)
    raster, names = strata_v2(s0, s3, layers)
    points = old + new
    for point in points:
        point["group"] = names[raster[point["row"], point["column"]]]
    sizes = {tuple(key.split("|")): value for key, value in record["stratum_pixels"].items()}
    at = (np.array([point["row"] for point in points]), np.array([point["column"] for point in points]))

    def said(values: np.ndarray) -> list[bool]:
        return (values[at] == mud.MUD_YES).tolist()

    def score_on(order: str | None, saids: list[bool]) -> dict[str, Any]:
        chosen = [(point, value) for point, value in zip(points, saids) if order is None or point["order"] == order]
        kept = [point for point, _ in chosen]
        return mud.weighted_f1(kept, [value for _, value in chosen], mud.point_weights(sizes, kept))

    answers = {"mud_s0": said(s0), "mud_s3": said(s3)}
    grid_answers = [said(candidate_v2(bands, layers, limits)) for limits in mud.threshold_grid()]
    orders = delivery_meta.ORDERS
    by_order = {name: {order: score_on(order, values) for order in orders} for name, values in answers.items()}
    scores = {name: mud.mean_score([by_order[name][order]["f1"] for order in orders]) for name in answers}

    def best(order: str | None) -> int:
        values = [score_on(order, values)["f1"] for values in grid_answers]
        return int(np.argmax([-1.0 if value is None else value for value in values]))

    crossed = {}
    for fit, held in (orders, orders[::-1]):
        index = best(fit)
        crossed[f"fitted_on_{fit}"] = {"limits": mud.limits_dict(mud.threshold_grid()[index]), "scored_on": held, **score_on(held, grid_answers[index])}
    scores["mud_s4"] = mud.mean_score([item["f1"] for item in crossed.values()])
    chosen = mud.choose(scores, order=("mud_s0", "mud_s3", "mud_s4"))
    limits = mud.threshold_grid()[best(None)] if chosen == "mud_s4" else mud.MudLimits()
    final = s0 if chosen == "mud_s0" else candidate_v2(bands, layers, limits)
    raster_path = work / "mud_frozen_v2_2m.tif"
    write_raster(raster_path, final, delivery["one_pixel_grid"])
    result = {
        "schema": "floodguard.theos2_17sep_mud_freeze.v2",
        **envelope(),
        "what_this_is": "The mud rule of question 4 after amendment 1: mud_s0, mud_s3 and mud_s4 scored on 200 development points the agent labelled; it supersedes freeze_v1.json for the test.",
        "amendment": record["amendment"],
        "points_record": {"path": f"{OUTPUT_DIR}/{POINTS_V2_NAME}", "sha256": sha256_file(points_path)},
        "supersedes": {"path": f"{OUTPUT_DIR}/{FREEZE_NAME}", "sha256": sha256_file(ROOT / OUTPUT_DIR / FREEZE_NAME)},
        "labels": {"by": "the agent that builds the rule (an AI model), from the sheets alone", "old_file_sha256": sha256_file(old_labels_path),
                   "new_file_sha256": sha256_file(new_labels_path),
                   "counts_new": {label: sum(1 for point in new if point["label"] == label) for label in mud.LABELS},
                   "by_point_new": {point["name"]: point["label"] for point in new},
                   "old_points_moved_to_the_opened_ground": [point["name"] for point in old if point["group"] in mud.OPENED_STRATA],
                   "note": "Development data, not a reference. No label of plan v1 was changed."},
        "scores": {"mud_s0": {"mean_f1": scores["mud_s0"], "by_order": by_order["mud_s0"]},
                   "mud_s3": {"mean_f1": scores["mud_s3"], "by_order": by_order["mud_s3"]},
                   "mud_s4": {"mean_f1": scores["mud_s4"], "crossed": crossed}},
        "choice_rule": f"mud_s0 stays unless mud_s3 is better by {mud.CHOICE_MARGIN} or more; the one kept stays unless mud_s4 is better than it by {mud.CHOICE_MARGIN} or more.",
        "chosen": chosen,
        "frozen_rule": {"candidate": chosen, "limits": mud.limits_dict(limits), "scaling_lines": layers["scaling"]["lines"],
                        "masks": "plan v1" if chosen == "mud_s0" else "amendment 1",
                        "min_object_px": mud.MIN_OBJECT_PX if chosen == "mud_s0" else mud.MIN_OBJECT_PX_V2,
                        "code": "floodguard.theos2_mud and scripts/build_theos2_17sep_mud.py (candidate, candidate_v2)"},
        "mud_km2_in_the_scene": round(float((final == mud.MUD_YES).sum()) * 4e-6, 3),
        "raster_outside_git": {"name": raster_path.name, "sha256": sha256_file(raster_path), "values": "1 mud, 0 not mud, 255 unobservable or outside the scene"},
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    write_json(freeze_path, result)
    print(json.dumps({"scores": scores, "chosen": chosen, "limits": mud.limits_dict(limits), "mud_km2": result["mud_km2_in_the_scene"],
                      "by_order": {name: {order: by_order[name][order] for order in orders} for name in by_order}}, indent=1))


# ---------------------------------------------------------------------------
# Section 4.4: the test points and the page the three team members label on
# ---------------------------------------------------------------------------

TEST_NAME = "test_points_v1.json"
TEST_KEY = "test_key_v1.json"
TEST_PAGE = "mud_label_page_v1.html"
TEST_TEMPLATE = "scripts/theos2_mud_label_page.html"
NATIVE_M = 0.5
DETAIL_PX = 128          # 64 m at 0.5 m
SQUARE_AT_PX = 62        # the 4 by 4 pixels of the square start here in the detail picture
CONTEXT_NATIVE_PX = 640  # 320 m at 0.5 m
CONTEXT_PX = 320         # shown at 1 m
STRETCH_PERCENTILES = (0.5, 99.5)
STRETCH_GAMMA = 0.8
JPEG_QUALITY = 90
PRACTICE_SEED = mud.TEST_SEED + 1


def stretch_limits(layers: dict[str, Any]) -> list[tuple[float, float]]:
    """The dark and the bright end of each band over the scene, the same for every picture."""

    sample = layers["covered"][::7, ::7]
    return [tuple(float(value) for value in np.percentile(layers["image"][band][::7, ::7][sample], STRETCH_PERCENTILES)) for band in range(4)]


def page_pictures(external: Path, delivery: dict[str, Any], point: dict[str, Any], limits: list[tuple[float, float]]) -> dict[str, str]:
    """The three pictures of a point, from the first product by name that holds its square, as on the water page."""

    import base64
    import io

    import rasterio
    from PIL import Image
    from rasterio.windows import Window

    def to_bytes(bands: np.ndarray, order: tuple[int, int, int]) -> np.ndarray:
        layers = []
        for band in order:
            low, high = limits[band]
            scaled = np.clip((bands[band].astype("float64") - low) / max(high - low, 1.0), 0.0, 1.0) ** STRETCH_GAMMA
            layers.append(np.round(scaled * 255).astype("uint8"))
        return np.stack(layers, axis=-1)

    def jpeg(picture: np.ndarray) -> str:
        buffer = io.BytesIO()
        Image.fromarray(picture).save(buffer, format="JPEG", quality=JPEG_QUALITY, subsampling=0)
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    grid = delivery["one_pixel_grid"]
    x_left, y_top = grid["west"] + point["column"] * grid["cell_m"], grid["north"] - point["row"] * grid["cell_m"]
    folder = external / delivery["work_folder_outside_git"]
    for product in sorted(delivery["products"], key=lambda item: item["product"]):
        with rasterio.open(folder / product["image"]["path"]) as source:
            column = int(round((x_left - source.transform.c) / NATIVE_M))
            row = int(round((source.transform.f - y_top) / NATIVE_M))
            if not (0 <= row and 0 <= column and row + 4 <= source.height and column + 4 <= source.width):
                continue
            if source.read(window=Window(column, row, 4, 4)).min() == 0:
                continue
            detail = source.read(window=Window(column - SQUARE_AT_PX, row - SQUARE_AT_PX, DETAIL_PX, DETAIL_PX), boundless=True, fill_value=0)
            half = CONTEXT_NATIVE_PX // 2
            context = source.read(window=Window(column + 2 - half, row + 2 - half, CONTEXT_NATIVE_PX, CONTEXT_NATIVE_PX),
                                  boundless=True, fill_value=0).astype("float64")
        factor = CONTEXT_NATIVE_PX // CONTEXT_PX
        context = context.reshape(4, CONTEXT_PX, factor, CONTEXT_PX, factor).mean(axis=(2, 4))
        true_colour, false_colour = (0, 1, 2), (3, 0, 1)
        return {"d": jpeg(to_bytes(detail, true_colour)), "f": jpeg(to_bytes(detail, false_colour)), "c": jpeg(to_bytes(context, true_colour))}
    raise BuildError(f"no product holds the square of {point.get('id', point)}")


def stage_test(arguments: argparse.Namespace) -> None:
    import rasterio

    from floodguard import theos2_water_rule_v2 as v2

    external = Path(arguments.external_root)
    work = external / WORK
    record_path = ROOT / OUTPUT_DIR / TEST_NAME
    freeze_path = ROOT / OUTPUT_DIR / FREEZE_V2_NAME
    if record_path.exists():
        raise BuildError("the test points are drawn once")
    if not freeze_path.exists():
        raise BuildError("the test points are drawn only after the freeze of amendment 1 is committed")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    raster_path = work / freeze["raster_outside_git"]["name"]
    if sha256_file(raster_path) != freeze["raster_outside_git"]["sha256"]:
        raise BuildError("the mud raster is not the one the freeze binds")
    delivery, reference = check_inputs()
    layers = scene_layers(external, delivery, reference)
    with rasterio.open(raster_path) as source:
        frozen = source.read(1)
    group_raster = mud.groups(frozen)
    group_raster[~layers["covered"]] = 255
    sizes = group_sizes(group_raster, layers["order"])
    counts = mud.allocate(sizes, mud.TEST_POINTS, delivery_meta.ORDERS)
    development = [*json.loads((work / "development_key_v1.json").read_text(encoding="utf-8"))["points"],
                   *json.loads((work / "development_key_v2.json").read_text(encoding="utf-8"))["points"]]
    free = v2.away_from(group_raster.shape, [(point["row"], point["column"]) for point in development], mud.KEEP_AWAY_PX)
    points = mud.draw(group_raster, layers["order"], delivery_meta.ORDERS, counts, mud.TEST_SEED, free=free)
    practice_free = free & v2.away_from(group_raster.shape, [(point["row"], point["column"]) for point in points], mud.KEEP_AWAY_PX)
    practice_counts = {(group, delivery_meta.ORDERS[index % 2]): 1 for index, group in enumerate(mud.GROUPS)}
    practice = mud.draw(group_raster, layers["order"], delivery_meta.ORDERS, practice_counts, PRACTICE_SEED, free=practice_free)
    grid = delivery["one_pixel_grid"]
    for index, point in enumerate(points, start=1):
        point.update({"id": f"t{index:03d}", "x": grid["west"] + (point["column"] + 0.5) * grid["cell_m"],
                      "y": grid["north"] - (point["row"] + 0.5) * grid["cell_m"]})
    limits = stretch_limits(layers)
    shown = [{"id": point["id"], **page_pictures(external, delivery, point, limits)} for point in points]
    practice_shown = [page_pictures(external, delivery, point, limits) for point in practice]
    test_work = work / "test"
    test_work.mkdir(parents=True, exist_ok=True)
    key_path = test_work / TEST_KEY
    write_json(key_path, {"schema": "floodguard.theos2_17sep_mud.test_key.v1", "plan": PLAN, "seed": mud.TEST_SEED, "epsg": delivery_meta.EPSG,
                          "what_a_point_is": "One pixel of the 2 m mud raster of freeze_v2; x and y are its centre.",
                          "points": [{key: point[key] for key in ("id", "group", "order", "row", "column", "x", "y")} for point in points],
                          "practice": [{key: point[key] for key in ("group", "order", "row", "column")} for point in practice]})
    sample_id = sha256_file(key_path)
    page = (ROOT / TEST_TEMPLATE).read_text(encoding="utf-8")
    for token, value in (("/*SAMPLE_ID*/", sample_id), ("/*PRACTICE*/[]", json.dumps(practice_shown, separators=(",", ":"))),
                         ("/*POINTS*/[]", json.dumps(shown, separators=(",", ":")))):
        if page.count(token) != 1:
            raise BuildError(f"the page template does not hold {token} exactly once")
        page = page.replace(token, value)
    page_path = test_work / TEST_PAGE
    page_path.write_bytes(page.encode("utf-8"))
    record = {
        "schema": "floodguard.theos2_17sep_mud.test_points.v1",
        **envelope(),
        "what_this_is": "The draw of the 150 test points of question 4 in the groups of the rule frozen by amendment 1, made before anybody labelled. "
                        "It holds no place and no group of a point: the key stays outside Git until the score is computed, because the repository is public and the labellers read it.",
        "freeze": {"path": f"{OUTPUT_DIR}/{FREEZE_V2_NAME}", "sha256": sha256_file(freeze_path)},
        "seed": mud.TEST_SEED, "practice_seed": PRACTICE_SEED,
        "group_pixels": {f"{group}|{order}": size for (group, order), size in sizes.items()},
        "points_per_group": {f"{group}|{order}": count for (group, order), count in counts.items() if count},
        "points": len(points), "practice_points": len(practice),
        "kept_away_from_development_points_m": mud.KEEP_AWAY_PX * 2,
        "labels": list(mud.LABELS),
        "sample_id": sample_id,
        "key_outside_git": {"name": f"test/{TEST_KEY}", "sha256": sample_id},
        "page_outside_git": {"name": f"test/{TEST_PAGE}", "sha256": sha256_file(page_path),
                             "template": {"path": TEST_TEMPLATE, "sha256": sha256_file(ROOT / TEST_TEMPLATE)},
                             "megabytes": round(page_path.stat().st_size / 1e6, 1), "holds_the_answer_of_the_rule": False,
                             "stretch_of_the_pictures": {"percentiles": list(STRETCH_PERCENTILES), "gamma": STRETCH_GAMMA,
                                                         "limits_by_band": [[round(low, 1), round(high, 1)] for low, high in limits]}},
        "labellers": "three team members, each alone",
        "labels_received": 0,
        "licence": "THEOS-2 imagery provided by GISTDA for GeoHackathon 2026. The page holds pixels of the scene and stays outside Git.",
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    write_json(record_path, record)
    print(json.dumps({"points_per_group": record["points_per_group"], "page_megabytes": record["page_outside_git"]["megabytes"],
                      "page": str(page_path)}, indent=1))


# ---------------------------------------------------------------------------
# Section 4.4: the score of the test, once, on the label files of three team members
# ---------------------------------------------------------------------------

SCORE_NAME = "test_score_v1.json"
ORDER_NAMES = {"AWG_20261014_bc7a15": "town box", "AWG_20261014_417d92": "west edge of the Ko Chang box"}
SCORE_LIMITS = [
    "Three team members labelled each point alone from three pictures of the image; nobody went to the ground.",
    "A test point stands for the pixels of the group it was drawn in; the shares are shares of that area, not of the district.",
    "Mud on a road says the water reached it; no mud never says a place stayed dry or a road stayed passable.",
]


def stage_score(arguments: argparse.Namespace) -> None:
    from collections import Counter
    from itertools import combinations

    external = Path(arguments.external_root)
    test_work = external / WORK / "test"
    record_path, score_path = ROOT / OUTPUT_DIR / TEST_NAME, ROOT / OUTPUT_DIR / SCORE_NAME
    if score_path.exists():
        raise BuildError("the test is scored once")
    if not record_path.exists():
        raise BuildError("no test points")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record["plan"]["sha256"] != sha256_file(ROOT / PLAN):
        raise BuildError("the plan changed after the test points were drawn")
    if record["freeze"]["sha256"] != sha256_file(ROOT / OUTPUT_DIR / FREEZE_V2_NAME):
        raise BuildError("the freeze is not the one the test points were drawn from")
    key_path = test_work / TEST_KEY
    if sha256_file(key_path) != record["sample_id"]:
        raise BuildError("the key is not the one the test record binds")
    points = json.loads(key_path.read_text(encoding="utf-8"))["points"]
    ids = [point["id"] for point in points]
    files = [Path(path) for path in arguments.label_files]
    if len(files) != 3:
        raise BuildError("the test is scored on three label files")
    contents = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    by_labeller: dict[str, dict[str, str]] = {}
    for content in contents:
        labels = mud.check_label_file(content, record["sample_id"], ids)
        name = str(content["labeller"]).strip()
        if name.casefold() in {known.casefold() for known in by_labeller}:
            raise BuildError("two label files name the same labeller")
        by_labeller[name] = labels

    # The files are taken in beside the key, outside Git, and bound by SHA-256.
    labels_dir = test_work / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    received = []
    for path, content in zip(files, contents):
        target = labels_dir / path.name
        if target.exists() and sha256_file(target) != sha256_file(path):
            raise BuildError(f"{target.name} is already taken in with other content")
        target.write_bytes(path.read_bytes())
        seconds = mud.seconds_of(content)
        received.append({"labeller": str(content["labeller"]).strip(), "file": f"test/labels/{path.name}", "sha256": sha256_file(target),
                         "saved_at_utc": content.get("saved_at_utc"),
                         "median_seconds_per_point": round(float(np.median(seconds)), 1) if seconds else None})

    names = sorted(by_labeller)
    sizes = {tuple(key.split("|")): value for key, value in record["group_pixels"].items()}
    weights = mud.point_weights(sizes, points)
    majority = {point: mud.majority_label([by_labeller[name][point] for name in names]) for point in ids}

    def shares(labels: dict[str, str | None], subset: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        chosen = points if subset is None else subset
        return {"labels_of_the_plan": mud.area_shares(chosen, labels, weights),
                "bare_counted_as_mud": mud.area_shares(chosen, labels, weights, bare_as_mud=True)}

    result_main = shares(majority)
    bar_share = result_main["labels_of_the_plan"]["share_of_rule_mud_labelled_mud"]
    met = bar_share is not None and bar_share >= mud.TEST_BAR - 1e-12
    by_order = {f"{order} ({ORDER_NAMES.get(order, order)})": shares(majority, [point for point in points if point["order"] == order])
                for order in delivery_meta.ORDERS}
    pairs = {f"{first} + {second}": shares({point: mud.agreed_label([by_labeller[first][point], by_labeller[second][point]]) for point in ids})
             for first, second in combinations(names, 2)}
    triples = [[by_labeller[name][point] for name in names] for point in ids]
    agreement = {"all_three_agree": sum(1 for labels in triples if len(set(labels)) == 1),
                 "two_of_three_agree": sum(1 for labels in triples if len(set(labels)) == 2),
                 "all_three_differ": sum(1 for labels in triples if len(set(labels)) == 3),
                 "pairs_agree": {f"{first} + {second}": sum(1 for point in ids if by_labeller[first][point] == by_labeller[second][point])
                                 for first, second in combinations(names, 2)},
                 "points": len(ids)}
    result = {
        "schema": "floodguard.theos2_17sep_mud.test_score.v1",
        **envelope(),
        "confidence_basis": "Three team members labelled 150 points alone from pictures of one optical image; nobody went to the ground.",
        "what_this_is": "The test of the frozen mud rule (freeze_v2, mud_s4), scored once on the labels of three team members, as plan section 4.4 fixed before any test point was drawn.",
        "test_points": {"path": f"{OUTPUT_DIR}/{TEST_NAME}", "sha256": sha256_file(record_path)},
        "freeze": record["freeze"],
        "sample_id": record["sample_id"],
        "labels_received": received,
        "rule_says_by_group": mud.RULE_SAYS,
        "weights": "pixels of each (group, order) over the test points drawn in it, as in the development score",
        "scored_on": "the label at least two of the three gave; a point where all three differ is left out, as are 'cannot tell' and, "
                     "in 'labels_of_the_plan', 'bare, cannot tell'",
        "bar": {"value": mud.TEST_BAR, "on": "share_of_rule_mud_labelled_mud, labels_of_the_plan", "share": bar_share, "met": met},
        "sentence": mud.bar_sentence(bar_share),
        "result": result_main,
        "interval_95_of_the_bar_share": {**mud.bootstrap_share(points, majority, weights),
                                         "how": "points drawn again with replacement inside each (group, order); beside the score, not used by the bar"},
        "beside_not_binding": {"by_order": by_order, "each_labeller": {name: shares(by_labeller[name]) for name in names}, "each_pair": pairs},
        "agreement": agreement,
        "label_counts": {"two_of_three": {str(label): count for label, count in Counter(majority.values()).items()},
                         **{name: dict(Counter(by_labeller[name].values())) for name in names}},
        "labels_by_point": {point: {**{name: by_labeller[name][point] for name in names}, "two_of_three": majority[point]} for point in ids},
        "next": "Section 4.5, once, with the mud raster as a map." if met else "Section 4.5, once, with the labelled points alone: no mud map is used.",
        "key_stays_outside_git": True,
        "assumptions": ASSUMPTIONS, "limits": LIMITS + SCORE_LIMITS,
    }
    write_json(score_path, result)
    print(json.dumps({"bar": result["bar"], "sentence": result["sentence"], "result": result_main,
                      "interval": result["interval_95_of_the_bar_share"], "agreement": agreement,
                      "by_order": {name: value["labels_of_the_plan"] for name, value in by_order.items()}}, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("stage", choices=("points", "freeze", "points2", "freeze2", "test", "score"))
    parser.add_argument("--external-root", required=True)
    parser.add_argument("--labels")
    parser.add_argument("--old-labels", help="freeze2: the label file of plan v1, as the first freeze binds it")
    parser.add_argument("--label-files", nargs="+", default=[], help="score: the label files of the three team members")
    arguments = parser.parse_args()
    if arguments.stage in ("freeze", "freeze2") and not arguments.labels:
        raise BuildError("a freeze stage needs --labels")
    if arguments.stage == "freeze2" and not arguments.old_labels:
        raise BuildError("the second freeze needs --old-labels")
    {"points": stage_points, "freeze": stage_freeze, "points2": stage_points2, "freeze2": stage_freeze2,
     "test": stage_test, "score": stage_score}[arguments.stage](arguments)


if __name__ == "__main__":
    main()
