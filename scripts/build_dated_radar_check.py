"""Radar flood candidates against the dated agency layer of 22 October 2024 at Mae Sai (work package 3).

Two stages, in the order of the plan (``docs/proposal_execution/dated_radar_check_plan_v1.md``):

``reference``
    The 10 m lattice over Mae Sai district, the cells of the frame and the cells the dated layer marks as water,
    from the layer and open context alone. No radar is read. Its record is committed before the next stage.

``compare``
    Fetches the Sentinel-1 pass of 21 October 2024 and the two images before, applies the three radar methods of
    the Mae Sai runs unchanged, and counts their agreement with the dated layer. It runs once.

The dated layer is held at the ``local`` level (decision log R33): its rasters and the figure stay in the work
folder outside Git, and the records in Git hold whole-district counts and shares only. Every figure is agreement
with an agency layer that was not checked in the field; none is accuracy. No FPPS and no A-E class is computed,
and nothing here is an official warning.

Example::

    python scripts/build_dated_radar_check.py reference --external-root <external-data-root>
    python scripts/build_dated_radar_check.py compare --external-root <external-data-root>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import dated_radar_check as drc  # noqa: E402
from floodguard import geoid_m1_review as review  # noqa: E402
from floodguard import radar_candidates as rc  # noqa: E402
from floodguard import sar_change_v2 as sar  # noqa: E402

PLAN = "docs/proposal_execution/dated_radar_check_plan_v1.md"
OUTPUT_DIR = "outputs/dated_radar_check"
REFERENCE_NAME = "mae_sai_20241022_reference_v1.json"
RESULT_NAME = "mae_sai_20241022_v1.json"
RECEIPT_NAME = "mae_sai_20241022_v1_receipt.json"
WORK = Path("proposal_execution") / "dated_radar_check_v1"
PRODUCT_ZIP = Path("unosat") / "unosat_4009_chiang_rai_2024" / "FL20240912THA_GDB.zip"
PRODUCT_GDB = "FL20240912THA.gdb"
DATED_LAYER = "CHIANGRAI_20241022_FloodExtent"
SEASON_LAYER = "CHIANGRAI_20240801_20241012_AccumulatedFlood"
BOUNDARIES = Path("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
DISTRICT = "TH5709"
SOURCE_TIMESTAMP = "2024-10-22 (agency layer); Sentinel-1 2024-10-21T23:16:14Z"

EPSG = 32647
CELL_M = 10.0
S1_POST = "S1A_IW_GRDH_1SDV_20241021T231602_20241021T231627_056207_06E178_rtc"
S1_BEFORE = {
    "primary": "S1A_IW_GRDH_1SDV_20240822T231600_20240822T231625_055332_06BF48_rtc",
    "second": "S1A_IW_GRDH_1SDV_20240412T231601_20240412T231626_053407_067A69_rtc",
}
WORLDCOVER_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
                  "ESA_WorldCover_10m_2021_v200_N18E099_Map.tif")
DEM_URLS = tuple(
    f"https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{lat}_00_E{lon:03d}_00_DEM/"
    f"Copernicus_DSM_COG_10_N{lat}_00_E{lon:03d}_00_DEM.tif" for lat in (20, 19) for lon in (99, 100)
)
PERMANENT_WATER_CLASS = 80
LAND_COVER_GROUPS = {"built_up": (50,), "cropland": (40,), "tree_cover": (10,)}

ASSUMPTIONS = [
    "The reference is the layer UNOSAT and GISTDA dated 22 October 2024, as provided: a cell is agency water when its centre lies inside it.",
    "Where the agency mapped no water the cell counts as dry; the layer has no 'not observed' class.",
    "The three radar methods run with the parameters of the Mae Sai runs; nothing is tuned for this date.",
    "The image before of the primary reading is the pass of 22 August 2024; the second reading uses 12 April 2024.",
]
LIMITS = [
    "One district, one date, a few square kilometres of residual water late in the season. It says nothing of the September flood.",
    "The agency layer was not checked in the field and may have been made from the same Sentinel-1 pass.",
    "Every figure is agreement with the agency layer, not accuracy.",
    "No planning score, no class and no exposure or access figure is computed.",
]


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


t2 = load_script("build_theos2_radar_cross_check")
BuildError = t2.BuildError


def envelope() -> dict[str, Any]:
    """The fields every FloodGuard output carries."""

    return {
        "generated_at_utc": t2.now_utc(),
        "source_timestamp": SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "One agency layer that was not checked in the field and one radar pass; no ground check.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "plan": {"path": PLAN, "sha256": t2.sha256_file(ROOT / PLAN)},
    }


def write_raster(path: Path, bands: list[np.ndarray], grid: tuple[float, float, int, int], dtype: str, nodata: float) -> None:
    import rasterio
    from rasterio.transform import from_origin

    west, north, rows, columns = grid
    with rasterio.open(path, "w", driver="GTiff", height=rows, width=columns, count=len(bands), dtype=dtype, nodata=nodata,
                       crs=f"EPSG:{EPSG}", compress="deflate", transform=from_origin(west, north, CELL_M, CELL_M)) as target:
        for index, band in enumerate(bands, start=1):
            target.write(band.astype(dtype), index)


def context_rasters(work: Path, grid: tuple[float, float, int, int]) -> tuple[np.ndarray, np.ndarray]:
    """WorldCover and the slope of the Copernicus DEM on the lattice grid (cached in the work folder)."""

    worldcover = t2.warp_remote(WORLDCOVER_URL, work, "worldcover_10m.tif", grid, nearest=True, dtype="uint8", fill=0)
    height = None
    for index, url in enumerate(DEM_URLS):
        part = t2.warp_remote(url, work, f"dem_{index}_10m.tif", grid, nearest=False, dtype="float32", fill=-9999.0)
        part = np.where(part == -9999.0, np.nan, part)
        height = part if height is None else np.where(np.isfinite(height), height, part)
    return worldcover, rc.slope_degrees(height, CELL_M, CELL_M)


def stage_reference(arguments: argparse.Namespace) -> None:
    import geopandas as gpd
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    import shapely

    external = Path(arguments.external_root)
    work = external / WORK
    work.mkdir(parents=True, exist_ok=True)
    record_path = ROOT / OUTPUT_DIR / REFERENCE_NAME
    if record_path.exists() and not arguments.replace:
        raise BuildError(f"{record_path} exists; use --replace with --reason")
    if (ROOT / OUTPUT_DIR / RESULT_NAME).exists():
        raise BuildError("the comparison has been run; the reference is not rebuilt after it")

    boundaries = gpd.read_file(f"/vsizip/{(external / BOUNDARIES).as_posix()}", layer="tha_admin3",
                               where=f"adm2_pcode = '{DISTRICT}'").to_crs(EPSG)
    if boundaries.empty:
        raise BuildError(f"no tambon of district {DISTRICT} in the boundary file")
    district = shapely.union_all(list(boundaries.geometry))
    tiles, west, north, rows, columns = t2.lattice_grid(district.bounds)
    grid = (west, north, rows, columns)
    transform = from_origin(west, north, CELL_M, CELL_M)

    product = f"/vsizip/{(external / PRODUCT_ZIP).as_posix()}/{PRODUCT_GDB}"
    window = shapely.box(west, north - rows * CELL_M, west + columns * CELL_M, north)
    layers = {}
    for name in (DATED_LAYER, SEASON_LAYER):
        frame = gpd.read_file(product, layer=name).to_crs(EPSG)
        geometry = shapely.intersection(shapely.union_all(list(frame.geometry.make_valid())), window)
        layers[name] = rasterize([(geometry, 1)], out_shape=(rows, columns), transform=transform, fill=0,
                                 dtype="uint8") if not geometry.is_empty else np.zeros((rows, columns), dtype="uint8")
    in_district = rasterize([(district, 1)], out_shape=(rows, columns), transform=transform, fill=0, dtype="uint8").astype(bool)
    worldcover, _slope = context_rasters(work, grid)
    permanent_water = worldcover == PERMANENT_WATER_CLASS
    reference = layers[DATED_LAYER].astype(bool)
    frame_cells = in_district & ~permanent_water
    interior = drc.interior_cells(reference, in_district)

    write_raster(work / "dated_reference_10m.tif",
                 [reference, in_district, permanent_water, interior, layers[SEASON_LAYER].astype(bool)], grid, "uint8", 255)
    record = {
        "schema": "floodguard.dated_radar_check_reference.v1",
        **envelope(),
        "what_this_is": "The frame and the reference cells of the radar check against the dated agency layer, before any radar is read.",
        "rights_note": "The dated layer is held at the local level (decision log R33). This record holds whole-district "
                       "counts only; the rasters stay outside Git.",
        "district": {"adm2_pcode": DISTRICT, "name": "Mae Sai", "tambons": int(len(boundaries))},
        "grid_10m": {"epsg": EPSG, "cell_m": CELL_M, "west": west, "north": north, "rows": rows, "columns": columns,
                     "lattice_tiles": [tile.name for tile in tiles]},
        "reference_layer": {"product": "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009", "layer": DATED_LAYER,
                            "archive_sha256": t2.sha256_file(external / PRODUCT_ZIP),
                            "rule": "cell centre inside the layer; geometry repaired with make_valid"},
        "season_layer_for_context": SEASON_LAYER,
        "counts": drc.frame_counts(in_district, permanent_water, reference, layers[SEASON_LAYER].astype(bool),
                                   cell_area_km2=CELL_M * CELL_M / 1e6),
        "cells_not_at_the_edge_of_the_layer": int((interior & frame_cells).sum()),
        "rasters_outside_git": {"dated_reference_10m.tif": {
            "sha256": t2.sha256_file(work / "dated_reference_10m.tif"),
            "bands": ["agency water", "in the district", "permanent water", "not at the edge of the layer", "season layer"]}},
        "radar_read": False,
        "assumptions": ASSUMPTIONS,
        "limits": LIMITS,
    }
    record["supersedes"] = t2.superseded(record_path, arguments, ("counts", "grid_10m"), record)
    t2.write_json(record_path, record)
    print(json.dumps(record["counts"], indent=1))


def fetch_scene(work: Path, grid: tuple[float, float, int, int], item_id: str, name: str) -> dict[str, Any]:
    """Read the lattice window of one terrain-corrected Sentinel-1 scene and cache it (VV, VH; linear gamma0)."""

    import rasterio
    from rasterio.windows import from_bounds

    west, north, rows, columns = grid
    bounds = (west, north - rows * CELL_M, west + columns * CELL_M, north)
    path, meta_path = work / f"s1_{name}_gamma0.tif", work / f"s1_{name}_gamma0.json"
    if not (path.exists() and meta_path.exists()):
        token = t2.fetch_json(t2.SAS)["token"]
        item = t2.fetch_json(t2.STAC + item_id)
        image = np.full((2, rows, columns), np.nan, dtype="float32")
        for band, asset in enumerate(("vv", "vh")):
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="6", GDAL_HTTP_RETRY_DELAY="4"):
                with rasterio.open(f"{item['assets'][asset]['href']}?{token}") as source:
                    if source.crs.to_epsg() != EPSG or source.res != (CELL_M, CELL_M):
                        raise BuildError(f"{item_id} is not on the 10 m EPSG:{EPSG} grid")
                    window = from_bounds(*bounds, transform=source.transform)
                    if any(abs(value - round(value)) > 1e-6 for value in (window.col_off, window.row_off)):
                        raise BuildError(f"{item_id} is not aligned to the lattice")
                    block = source.read(1, window=window, boundless=True, fill_value=np.nan).astype("float32")
            block[~(np.isfinite(block) & (block > 0))] = np.nan
            image[band] = block
        write_raster(path, [image[0], image[1]], grid, "float32", float("nan"))
        t2.write_json(meta_path, {"fetched_at_utc": t2.now_utc(), "item": item_id,
                                  "datetime": item["properties"]["datetime"],
                                  "platform": item["properties"].get("platform"),
                                  "relative_orbit": item["properties"].get("sat:relative_orbit"),
                                  "orbit_state": item["properties"].get("sat:orbit_state")})
    return {**json.loads(meta_path.read_text(encoding="utf-8")), "window_file": path.name, "window_sha256": t2.sha256_file(path)}


def run_methods(pre: np.ndarray, post: np.ndarray, tiles: list[Any], grid: tuple[float, float, int, int],
                permanent_water: np.ndarray, slope: np.ndarray, configs: dict[str, Any]) -> dict[str, np.ndarray]:
    """The three radar candidates of one image pair, as the Mae Sai runs made them."""

    west, north, rows, columns = grid
    candidates: dict[str, np.ndarray] = {}
    candidates["un_spider"], _, _, _ = rc.un_spider_candidate(
        pre[1], post[1], in_frame=np.ones((rows, columns), dtype=bool), permanent_water=permanent_water, slope=slope,
        cell_m=CELL_M, config=configs["un_spider"])
    for name, runner in (
        ("m1_literal", lambda before, after: rc.m1_literal_tile(before, after, configs["m1_literal"])),
        ("m1_v2", lambda before, after: rc.m1_v2_tile(before, after, configs["m1_v2"])),
    ):
        candidates[name], _, _, _, _ = rc.run_on_tiles(pre, post, tiles, runner, grid_west=west, grid_north=north, cell_m=CELL_M)
    return candidates


def write_figure(path: Path, reference: np.ndarray, in_district: np.ndarray, candidates: dict[str, np.ndarray]) -> None:
    """One panel per method of the primary reading: both green, agency only blue, radar only orange. Kept outside Git."""

    from PIL import Image

    panels = []
    for candidate in candidates.values():
        flagged = candidate == 1
        picture = np.full((*reference.shape, 3), 235, dtype="uint8")
        picture[~in_district] = (200, 200, 200)
        picture[in_district & reference & flagged] = (34, 160, 60)
        picture[in_district & reference & ~flagged] = (40, 130, 235)
        picture[in_district & ~reference & flagged] = (255, 150, 20)
        panels.append(picture[::2, ::2])
    gap = np.full((panels[0].shape[0], 6, 3), 255, dtype="uint8")
    Image.fromarray(np.concatenate([part for panel in panels for part in (panel, gap)][:-1], axis=1)).save(path, optimize=True)


def stage_compare(arguments: argparse.Namespace) -> None:
    import rasterio

    external = Path(arguments.external_root)
    work = external / WORK
    reference_path = ROOT / OUTPUT_DIR / REFERENCE_NAME
    if not reference_path.exists():
        raise BuildError("no reference record: run the reference stage first and commit it")
    record = json.loads(reference_path.read_text(encoding="utf-8"))
    if record["plan"]["sha256"] != t2.sha256_file(ROOT / PLAN):
        raise BuildError("the plan changed after the reference record was written")
    raster = work / "dated_reference_10m.tif"
    if t2.sha256_file(raster) != record["rasters_outside_git"]["dated_reference_10m.tif"]["sha256"]:
        raise BuildError("dated_reference_10m.tif is not the raster the reference record binds")
    result_path = ROOT / OUTPUT_DIR / RESULT_NAME
    if result_path.exists() and not arguments.replace:
        raise BuildError(f"{result_path} exists; the comparison is run once (plan section 7)")

    grid_record = record["grid_10m"]
    grid = (float(grid_record["west"]), float(grid_record["north"]), int(grid_record["rows"]), int(grid_record["columns"]))
    west, north, rows, columns = grid
    tiles = rc.lattice_tiles((west, north - rows * CELL_M, west + columns * CELL_M, north))
    cell_km2 = CELL_M * CELL_M / 1e6
    with rasterio.open(raster) as source:
        reference, in_district, permanent_water, interior, _season = (source.read(band).astype(bool) for band in range(1, 6))
    worldcover, slope = context_rasters(work, grid)

    scenes = {"post": fetch_scene(work, grid, S1_POST, "post")}
    for reading, item_id in S1_BEFORE.items():
        scenes[f"before_{reading}"] = fetch_scene(work, grid, item_id, f"before_{reading}")
    images = {}
    for name, scene in scenes.items():
        with rasterio.open(work / scene["window_file"]) as source:
            images[name] = source.read().astype("float64")

    binding = review.require_frozen_m1_v2(ROOT)
    configs = {"un_spider": rc.UnSpiderConfig(), "m1_literal": sar.M1LiteralConfig(),
               "m1_v2": sar.m1_v2_config_from_json(binding["parameters"])}
    valid_post = np.isfinite(images["post"]).all(axis=0)
    compared = in_district & ~permanent_water & valid_post
    readings: dict[str, dict[str, Any]] = {}
    pictures: dict[str, np.ndarray] = {}
    for reading in S1_BEFORE:
        candidates = run_methods(images[f"before_{reading}"], images["post"], tiles, grid, permanent_water, slope, configs)
        readings[reading] = {
            name: {"flood_input_name": rc.FLOOD_INPUT_NAMES[name],
                   **drc.method_agreement(candidate, reference, compared, interior, worldcover, LAND_COVER_GROUPS,
                                          cell_area_km2=cell_km2)}
            for name, candidate in candidates.items()}
        if reading == "primary":
            pictures = candidates
    figure = work / "mae_sai_20241022_v1_overview.png"
    write_figure(figure, reference, in_district, pictures)

    result = {
        "schema": "floodguard.dated_radar_check.v1",
        **envelope(),
        "what_this_is": "Agreement of the three radar flood candidates with the layer UNOSAT and GISTDA dated 22 October "
                        "2024, in Mae Sai district. Whole-district counts and shares.",
        "label": "Agreement with an agency layer that was not checked in the field; not accuracy.",
        "rights_note": "The dated layer is held at the local level (decision log R33): the rasters and the figure "
                       "stay outside Git, and no table by tambon is written.",
        "reference_record": {"path": f"{OUTPUT_DIR}/{REFERENCE_NAME}", "sha256": t2.sha256_file(reference_path)},
        "times": {"agency_layer_date": "2024-10-22", "radar_after_utc": scenes["post"]["datetime"],
                  "radar_after_local_time": "22 October 2024, 06:16 (UTC+7)",
                  "radar_before_primary_utc": scenes["before_primary"]["datetime"],
                  "radar_before_second_utc": scenes["before_second"]["datetime"]},
        "compared_cells": {"cells": int(compared.sum()), "km2": round(int(compared.sum()) * cell_km2, 4),
                           "frame_cells_without_radar_after": int((in_district & ~permanent_water & ~valid_post).sum()),
                           "reference_wet_cells": int((reference & compared).sum()),
                           "reference_wet_km2": round(int((reference & compared).sum()) * cell_km2, 4)},
        "frame_counts": record["counts"],
        "readings": readings,
        "fixed_sentences_of_the_plan": drc.fixed_sentences(readings),
        "methods": {"un_spider": "UN-SPIDER recommended practice, quotient 1.25, as in the Mae Sai runs",
                    "m1_literal": "M1 as written, on each lattice tile",
                    "m1_v2": {"frozen_binding": {key: binding[key] for key in binding if key != "parameters"}}},
        "figure_outside_git": figure.name,
        "assumptions": ASSUMPTIONS,
        "limits": LIMITS,
    }
    result["supersedes"] = t2.superseded(result_path, arguments, ("readings", "compared_cells"), result)
    t2.write_json(result_path, result)
    receipt = {
        "schema": "floodguard.dated_radar_check_receipt.v1",
        **envelope(),
        "inputs": {"reference_record": result["reference_record"],
                   "reference_archive_sha256": record["reference_layer"]["archive_sha256"],
                   "sentinel1": scenes,
                   "worldcover": WORLDCOVER_URL, "dem": list(DEM_URLS)},
        "outputs": {f"{OUTPUT_DIR}/{RESULT_NAME}": {"sha256": t2.sha256_file(result_path)},
                    "outside_git": {figure.name: {"sha256": t2.sha256_file(figure)}}},
        "code": {name: t2.sha256_file(ROOT / name) for name in (
            "scripts/build_dated_radar_check.py", "src/floodguard/dated_radar_check.py",
            "src/floodguard/radar_candidates.py", "src/floodguard/sar_change_v2.py")},
    }
    t2.write_json(ROOT / OUTPUT_DIR / RECEIPT_NAME, receipt)
    for reading, methods in readings.items():
        for name, agreement in methods.items():
            strict = agreement["all_compared_cells"]["strict_no_answer_counts_as_not_a_candidate"]
            print(reading, name, "flagged km2", strict["candidate_km2"], "precision", strict["precision"],
                  "recall", strict["recall"], "iou", strict["iou"], "answered", agreement["all_compared_cells"]["answered_share"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    stages = parser.add_subparsers(dest="stage", required=True)
    for name, text in (("reference", "build the frame and the reference cells; no radar is read"),
                       ("compare", "fetch the radar, apply the three methods and count the agreement")):
        stage = stages.add_parser(name, help=text)
        stage.add_argument("--external-root", required=True)
        stage.add_argument("--replace", action="store_true")
        stage.add_argument("--reason", default="")
    arguments = parser.parse_args()
    {"reference": stage_reference, "compare": stage_compare}[arguments.stage](arguments)


if __name__ == "__main__":
    main()
