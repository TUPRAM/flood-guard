"""A trained flood-susceptibility model for the Mae Sai area (work package 4).

Plan: ``docs/proposal_execution/flood_susceptibility_model_plan_v1.md``. Three stages, run in this order, the
second and the third each after the one before is committed:

``features``  builds the terrain and land-cover features of the four districts. It reads no flood layer.
              It needs pysheds for the flow routing.
``fit``       reads the season layer inside Mae Sai only, chooses the settings by grouped cross-validation,
              calibrates, fits the final models and writes the freeze record.
``test``      refuses to run without the freeze record. It reads the season layer of the three test districts
              once and writes the figures the plan fixes.

The label is an agency season layer, not ground truth: every figure is agreement with it. The model feeds no
score, and nothing here is an official warning. Rasters, cell tables and fitted models stay outside Git.

Example::

    python scripts/build_flood_susceptibility_model.py features --external-root <external-data-root>
    python scripts/build_flood_susceptibility_model.py fit --external-root <external-data-root>
    python scripts/build_flood_susceptibility_model.py test --external-root <external-data-root>
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import flood_inputs, rights  # noqa: E402
from floodguard import flood_susceptibility_ml as ml  # noqa: E402

PLAN = "docs/proposal_execution/flood_susceptibility_model_plan_v1.md"
OUTPUT_DIR = "outputs/flood_susceptibility"
FREEZE_NAME = "mae_sai_model_v1_freeze.json"
RESULT_NAME = "mae_sai_model_v1.json"
RECEIPT_NAME = "mae_sai_model_v1_receipt.json"
FIGURE_NAME = "mae_sai_model_v1_map.png"
WORK = Path("proposal_execution") / "flood_susceptibility_v1"
DEM_TILES = ("Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif", "Copernicus_DSM_COG_10_N20_00_E100_00_DEM.tif")
DEM_FOLDER = Path("open_context") / "copernicus_dem_glo30"
WORLDCOVER = Path("open_context") / "esa_worldcover" / "ESA_WorldCover_10m_2021_v200_N18E099_Map.tif"
BOUNDARIES = Path("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
SEASON_LAYER = "CHIANGRAI_20240801_20241012_AccumulatedFlood"
EPSG = 32647
CELL_M = 30.0
WINDOW_LONLAT = (99.40, 20.00, 100.40, 20.85)
TRAIN_DISTRICT = "TH5709"
TEST_DISTRICTS = ("TH5707", "TH5708", "TH5715")
DISTRICT_NAMES = {"TH5709": "Mae Sai", "TH5707": "Mae Chan", "TH5708": "Chiang Saen", "TH5715": "Mae Fa Luang"}
DISTRICT_CODES = {code: index + 1 for index, code in enumerate((TRAIN_DISTRICT, *TEST_DISTRICTS))}
MAIN_STREAM_KM2, SMALL_STREAM_KM2 = 25.0, 1.0
PERMANENT_WATER = 80
LAND_COVER = {"tree_cover": 10, "shrubland": 20, "grassland": 30, "cropland": 40, "built_up": 50, "bare": 60, "wetland": 90}
TERRAIN_FEATURES = ("elevation_m", "slope_degrees", "hand_main_stream_m", "hand_small_stream_m", "distance_main_stream_m",
                    "distance_small_stream_m", "log10_upstream_area_km2", "distance_permanent_water_m")
LAND_COVER_FEATURES = tuple(f"land_cover_{name}" for name in (*LAND_COVER, "other"))
FEATURES = (*TERRAIN_FEATURES, *LAND_COVER_FEATURES)
BASELINE_FEATURE = "hand_main_stream_m"
SOURCE_TIMESTAMP = "2024-08-01/2024-10-12 (season layer of product 4009)"

ASSUMPTIONS = [
    "The label is the accumulated layer of UNOSAT/GISTDA product 4009, as provided: an unvalidated preliminary agency "
    "extent made mostly from radar, which sees open water on fields better than water under trees or between buildings.",
    "A cell counts for a district when its centre is inside it; a cell is labelled flooded when its centre is inside the layer.",
    "Upstream area is cut at the edge of the hydrology window, so permanent water counts as a stream.",
    "Land cover is resampled from 10 m to 30 m by nearest cell.",
]
LIMITS = [
    "Susceptibility for one season, not a flood map of any day and not a forecast.",
    "Every figure is agreement with the season layer on districts the model never saw, never accuracy against the ground.",
    "It feeds no component, no planning score and no action class. A use in a planning score would need a new protocol version.",
    "One season of one province: the model is not shown to hold elsewhere or in another year.",
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
    # LF bytes on every platform: receipts bind these files by SHA-256 (.gitattributes, D-41).
    path.write_bytes((json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


def envelope() -> dict[str, Any]:
    return {
        "generated_at_utc": now_utc(), "source_timestamp": SOURCE_TIMESTAMP, "confidence_class": "low",
        "confidence_basis": "A model of an unvalidated agency season layer; nothing was checked on the ground.",
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "plan": {"path": PLAN, "sha256": sha256_file(ROOT / PLAN)},
    }


def grid_of_window() -> tuple[Any, int, int]:
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds

    west, south, east, north = transform_bounds("EPSG:4326", f"EPSG:{EPSG}", *WINDOW_LONLAT, densify_pts=21)
    west, north = np.floor(west / CELL_M) * CELL_M, np.ceil(north / CELL_M) * CELL_M
    columns = int(np.ceil((east - west) / CELL_M))
    rows = int(np.ceil((north - south) / CELL_M))
    return from_origin(west, north, CELL_M, CELL_M), rows, columns


def read_districts(boundaries: Path) -> Any:
    """The four districts and the eight Mae Sai tambons, in EPSG:32647."""

    import geopandas as gpd
    import zipfile

    with zipfile.ZipFile(boundaries) as archive:
        geodatabase = sorted({name.split("/")[0] for name in archive.namelist() if name.split("/")[0].endswith(".gdb")})[0]
    codes = ", ".join(f"'{code}'" for code in DISTRICT_CODES)
    tambons = gpd.read_file(f"/vsizip/{boundaries.as_posix()}/{geodatabase}", layer="tha_admin3",
                            where=f"adm2_pcode IN ({codes})").to_crs(EPSG)
    if set(tambons["adm2_pcode"]) != set(DISTRICT_CODES):
        raise BuildError("the boundary file does not hold the four districts")
    return tambons


# ---------------------------------------------------------------------------
# Stage 1: features (no flood layer is read)
# ---------------------------------------------------------------------------


def stage_features(arguments: argparse.Namespace) -> None:
    import rasterio
    from rasterio import features as rasterio_features
    from rasterio.merge import merge
    from rasterio.warp import Resampling, reproject
    from scipy import ndimage
    from pysheds.grid import Grid as ShedGrid

    external = Path(arguments.external_root)
    work = external / WORK
    work.mkdir(parents=True, exist_ok=True)
    transform, rows, columns = grid_of_window()
    crs = f"EPSG:{EPSG}"
    clock = time.perf_counter()

    sources = [rasterio.open(external / DEM_FOLDER / name) for name in DEM_TILES]
    try:
        mosaic, mosaic_transform = merge(sources, bounds=WINDOW_LONLAT, nodata=-9999.0)
        source_crs = sources[0].crs
    finally:
        for source in sources:
            source.close()
    elevation = np.full((rows, columns), np.nan, dtype="float32")
    reproject(mosaic[0].astype("float32"), elevation, src_transform=mosaic_transform, src_crs=source_crs, src_nodata=-9999.0,
              dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    no_terrain = ~np.isfinite(elevation)
    land_cover = np.zeros((rows, columns), dtype="uint8")
    with rasterio.open(external / WORLDCOVER) as source:
        reproject(rasterio.band(source, 1), land_cover, dst_transform=transform, dst_crs=crs, dst_nodata=0,
                  resampling=Resampling.nearest)
    water = land_cover == PERMANENT_WATER

    dem_path = work / "dem_30m.tif"
    profile = {"driver": "GTiff", "height": rows, "width": columns, "crs": crs, "transform": transform, "compress": "deflate"}
    with rasterio.open(dem_path, "w", count=1, dtype="float32", nodata=-9999.0, **profile) as target:
        # The window reaches a little past the terrain tiles on disk; those cells are no-data, as in the replay build.
        target.write(np.where(no_terrain, -9999.0, elevation).astype("float32"), 1)
    shed = ShedGrid.from_raster(str(dem_path))
    raw = shed.read_raster(str(dem_path))
    conditioned = shed.resolve_flats(shed.fill_depressions(shed.fill_pits(raw)))
    direction = shed.flowdir(conditioned)
    accumulation = shed.accumulation(direction)
    area_km2 = np.asarray(accumulation, dtype="float64") * (CELL_M ** 2) / 1e6
    surface = np.asarray(conditioned, dtype="float32")
    print(f"flow routing: {time.perf_counter() - clock:.0f} s", flush=True)

    layers: dict[str, np.ndarray] = {"elevation_m": elevation}
    gradient_north, gradient_east = np.gradient(elevation.astype("float64"), CELL_M)
    layers["slope_degrees"] = np.degrees(np.arctan(np.hypot(gradient_east, gradient_north))).astype("float32")
    stream_cells: dict[str, int] = {}
    for name, threshold in (("main", MAIN_STREAM_KM2), ("small", SMALL_STREAM_KM2)):
        stream_raster = accumulation * (CELL_M ** 2) / 1e6 >= threshold  # keeps the pysheds raster type
        stream_raster[water] = True
        streams = np.asarray(stream_raster, dtype=bool)
        stream_cells[name] = int(streams.sum())
        hand = np.asarray(shed.compute_hand(direction, conditioned, stream_raster), dtype="float32")
        distance, indices = ndimage.distance_transform_edt(~streams, return_indices=True)
        missing = ~np.isfinite(hand)
        # A flat without a resolved flow path gets its height above the nearest stream cell in a straight line.
        hand[missing] = surface[missing] - surface[indices[0], indices[1]][missing]
        layers[f"hand_{name}_stream_m"] = np.clip(hand, 0, None)
        layers[f"distance_{name}_stream_m"] = (distance * CELL_M).astype("float32")
        stream_cells[f"{name}_cells_without_a_flow_path"] = int(missing.sum())
    layers["log10_upstream_area_km2"] = np.log10(np.maximum(area_km2, CELL_M ** 2 / 1e6)).astype("float32")
    layers["distance_permanent_water_m"] = (ndimage.distance_transform_edt(~water) * CELL_M).astype("float32") if water.any() \
        else np.full((rows, columns), 1e6, dtype="float32")
    known = np.zeros((rows, columns), dtype=bool)
    for name, code in LAND_COVER.items():
        layers[f"land_cover_{name}"] = (land_cover == code).astype("float32")
        known |= land_cover == code
    layers["land_cover_other"] = (~known & ~water).astype("float32")

    tambons = read_districts(external / BOUNDARIES)
    district = rasterio_features.rasterize(
        ((geometry, DISTRICT_CODES[code]) for geometry, code in zip(tambons.geometry, tambons["adm2_pcode"])),
        out_shape=(rows, columns), transform=transform, fill=0, dtype="uint8")
    if (no_terrain & (district > 0)).any():
        raise BuildError("the terrain model does not cover every cell of the four districts")
    for name in layers:
        layers[name] = np.where(no_terrain, np.nan, layers[name]).astype("float32")
    mae_sai = tambons[tambons["adm2_pcode"] == TRAIN_DISTRICT].sort_values("adm3_pcode").reset_index(drop=True)
    tambon_index = rasterio_features.rasterize(
        ((geometry, index + 1) for index, geometry in enumerate(mae_sai.geometry)),
        out_shape=(rows, columns), transform=transform, fill=0, dtype="uint8")

    with rasterio.open(work / "features_30m.tif", "w", count=len(FEATURES), dtype="float32", nodata=np.nan, **profile) as target:
        for band, name in enumerate(FEATURES, start=1):
            target.write(layers[name].astype("float32"), band)
            target.set_band_description(band, name)
    for name, array in (("districts_30m.tif", district), ("mae_sai_tambons_30m.tif", tambon_index),
                        ("land_cover_30m.tif", land_cover)):
        with rasterio.open(work / name, "w", count=1, dtype="uint8", nodata=0, **profile) as target:
            target.write(array, 1)
    record = {
        "schema": "floodguard.flood_susceptibility.features.v1", "generated_at_utc": now_utc(),
        "stage": "features: no flood layer was read",
        "grid": {"epsg": EPSG, "cell_m": CELL_M, "rows": rows, "columns": columns, "west": transform.c, "north": transform.f,
                 "window_lonlat": list(WINDOW_LONLAT)},
        "features": list(FEATURES),
        "stream_rule": {"main_km2": MAIN_STREAM_KM2, "small_km2": SMALL_STREAM_KM2, "permanent_water_counts_as_stream": True, **stream_cells},
        "district_codes": DISTRICT_CODES,
        "mae_sai_tambons": [str(code) for code in mae_sai["adm3_pcode"]],
        "cells_by_district": {code: int((district == index).sum()) for code, index in DISTRICT_CODES.items()},
        "window_cells_without_terrain": int(no_terrain.sum()),
        "permanent_water_cells_by_district": {code: int(((district == index) & water).sum()) for code, index in DISTRICT_CODES.items()},
        "inputs": {
            "dem_tiles": {name: sha256_file(external / DEM_FOLDER / name) for name in DEM_TILES},
            "worldcover": {"file": WORLDCOVER.name, "sha256": sha256_file(external / WORLDCOVER)},
            "boundaries": {"file": BOUNDARIES.name, "sha256": sha256_file(external / BOUNDARIES)},
        },
        "files": {name: sha256_file(work / name) for name in ("features_30m.tif", "districts_30m.tif",
                                                               "mae_sai_tambons_30m.tif", "land_cover_30m.tif")},
        "libraries": {"python": sys.version.split()[0], "numpy": np.__version__, "rasterio": rasterio.__version__},
    }
    write_json(work / "features_record.json", record)
    print(json.dumps({key: record[key] for key in ("grid", "stream_rule", "cells_by_district")}, indent=1))


# ---------------------------------------------------------------------------
# Shared reading
# ---------------------------------------------------------------------------


def load_features(work: Path) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray, np.ndarray, Any]:
    import rasterio

    record = json.loads((work / "features_record.json").read_text(encoding="utf-8"))
    for name, digest in record["files"].items():
        if sha256_file(work / name) != digest:
            raise BuildError(f"{name} is not the raster the features record binds")
    if record["features"] != list(FEATURES):
        raise BuildError("the features on disk are not the features of this code")
    with rasterio.open(work / "features_30m.tif") as source:
        stack = source.read()
        transform = source.transform
    with rasterio.open(work / "districts_30m.tif") as source:
        district = source.read(1)
    with rasterio.open(work / "mae_sai_tambons_30m.tif") as source:
        tambon = source.read(1)
    with rasterio.open(work / "land_cover_30m.tif") as source:
        land_cover = source.read(1)
    return record, stack, district, tambon, land_cover, transform


def season_layer_cells(external: Path, district_codes: tuple[str, ...], shape: tuple[int, int], transform: Any) -> tuple[np.ndarray, dict[str, Any]]:
    """Rasterise the season layer inside the named districts only (cell centre rule); nothing outside them is touched."""

    import shapely
    from rasterio import features as rasterio_features

    registry = rights.RightsRegistry(ROOT)
    grant = registry.require_use(rights.PRODUCT_4009, layer=SEASON_LAYER)
    archive = registry.verify_source(grant, external)
    geometry, _attributes = flood_inputs.read_product_layer(archive, SEASON_LAYER)
    extent = shapely.make_valid(flood_inputs.project(geometry, flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS))
    tambons = read_districts(external / BOUNDARIES)
    chosen = shapely.union_all(list(tambons[tambons["adm2_pcode"].isin(district_codes)].geometry))
    inside = shapely.intersection(extent, chosen)
    label = rasterio_features.rasterize([(inside, 1)], out_shape=shape, transform=transform, fill=0, dtype="uint8") \
        if not inside.is_empty else np.zeros(shape, dtype="uint8")
    return label.astype(bool), {"layer": SEASON_LAYER, "archive_sha256": sha256_file(archive), "rights": grant.as_record(),
                                "districts_read": list(district_codes)}


def cell_table(stack: np.ndarray, district: np.ndarray, land_cover: np.ndarray, codes: tuple[str, ...], transform: Any) -> dict[str, np.ndarray]:
    """The cells of the named districts outside permanent water: features, district index and cell-centre coordinates."""

    wanted = np.isin(district, [DISTRICT_CODES[code] for code in codes]) & (land_cover != PERMANENT_WATER)
    wanted &= np.isfinite(stack).all(axis=0)
    rows, columns = np.nonzero(wanted)
    return {
        "rows": rows, "columns": columns, "features": stack[:, rows, columns].T.astype("float64"),
        "district": district[rows, columns],
        "x": transform.c + (columns + 0.5) * transform.a, "y": transform.f + (rows + 0.5) * transform.e,
    }


# ---------------------------------------------------------------------------
# Stage 2: fit on Mae Sai and freeze
# ---------------------------------------------------------------------------


def stage_fit(arguments: argparse.Namespace) -> None:
    import joblib
    import sklearn

    external = Path(arguments.external_root)
    work = external / WORK
    freeze_path = ROOT / OUTPUT_DIR / FREEZE_NAME
    if freeze_path.exists() and not (arguments.replace and arguments.reason):
        raise BuildError("the freeze record exists; a second fit needs --replace and --reason")
    features_record, stack, district, tambon, land_cover, transform = load_features(work)
    label_raster, label_record = season_layer_cells(external, (TRAIN_DISTRICT,), district.shape, transform)
    cells = cell_table(stack, district, land_cover, (TRAIN_DISTRICT,), transform)
    label = label_raster[cells["rows"], cells["columns"]]
    folds = ml.block_folds(cells["x"], cells["y"])
    prevalence = float(label.mean())
    index = {name: position for position, name in enumerate(FEATURES)}
    columns_of = {
        ml.BASELINE: [index[BASELINE_FEATURE]],
        ml.RANDOM_FOREST: list(range(len(FEATURES))),
        ml.GRADIENT_BOOSTING: list(range(len(FEATURES))),
    }
    terrain_only = [index[name] for name in TERRAIN_FEATURES]
    models: dict[str, Any] = {}
    record_models: dict[str, Any] = {}
    out_of_fold: dict[str, np.ndarray] = {}
    for kind, grid in ((ml.BASELINE, ()), (ml.RANDOM_FOREST, ml.RANDOM_FOREST_GRID), (ml.GRADIENT_BOOSTING, ml.GRADIENT_BOOSTING_GRID)):
        clock = time.perf_counter()
        values = cells["features"][:, columns_of[kind]]
        selection, raw = ml.select_settings(kind, grid, values, label, folds)
        calibrator = ml.fit_isotonic(raw, label)
        final = ml.make_model(kind, selection.settings)
        final.fit(values, label.astype("int64"))
        calibrated = calibrator.predict(raw)
        out_of_fold[kind] = calibrated
        models[kind] = {"model": final, "calibrator": calibrator, "columns": columns_of[kind]}
        record_models[kind] = {
            "settings": selection.settings, "trials": list(selection.trials),
            "features": [FEATURES[position] for position in columns_of[kind]],
            "out_of_fold_on_mae_sai": ml.scores(calibrated, label, training_prevalence=prevalence),
        }
        print(f"{kind}: {time.perf_counter() - clock:.0f} s, settings {selection.settings}", flush=True)
    # The sensitivity run of the plan: the tree model with the better cross-validation figure, without land cover.
    best_tree = max((ml.RANDOM_FOREST, ml.GRADIENT_BOOSTING),
                    key=lambda kind: max(trial["mean_average_precision"] for trial in record_models[kind]["trials"]))
    values = cells["features"][:, terrain_only]
    raw = ml.out_of_fold(best_tree, record_models[best_tree]["settings"], values, label, folds)
    calibrator = ml.fit_isotonic(raw, label)
    final = ml.make_model(best_tree, record_models[best_tree]["settings"])
    final.fit(values, label.astype("int64"))
    name = "sensitivity_without_land_cover"
    models[name] = {"model": final, "calibrator": calibrator, "columns": terrain_only, "kind": best_tree}
    record_models[name] = {
        "kind": best_tree, "settings": record_models[best_tree]["settings"], "features": list(TERRAIN_FEATURES),
        "out_of_fold_on_mae_sai": ml.scores(calibrator.predict(raw), label, training_prevalence=prevalence),
    }

    model_path = work / "models_v1.joblib"
    joblib.dump(models, model_path, compress=3)
    np.save(work / "mae_sai_out_of_fold.npy", np.column_stack([out_of_fold[kind] for kind in (ml.BASELINE, ml.RANDOM_FOREST, ml.GRADIENT_BOOSTING)]))

    tambon_of_cell = tambon[cells["rows"], cells["columns"]]
    tambon_rows = []
    for position, code in enumerate(features_record["mae_sai_tambons"], start=1):
        inside = tambon_of_cell == position
        tambon_rows.append({
            "unit_id": code, "cells": int(inside.sum()),
            "flooded_share_in_the_season_layer": round(float(label[inside].mean()), 6),
            "mean_out_of_fold_value": {kind: round(float(out_of_fold[kind][inside].mean()), 6) for kind in out_of_fold},
        })
    freeze = {
        "schema": "floodguard.flood_susceptibility.freeze.v1", **envelope(),
        "stage": "fit: the season layer was read inside Mae Sai only; no cell of a test district has a label yet",
        "training_district": TRAIN_DISTRICT, "test_districts": list(TEST_DISTRICTS),
        "cells": {"mae_sai": int(label.size), "flooded": int(label.sum()), "flooded_share": round(prevalence, 6)},
        "folds": {"block_m": ml.BLOCK_M, "folds": ml.FOLDS, "seed": ml.SEED,
                  "cells_by_fold": [int((folds == fold).sum()) for fold in range(ml.FOLDS)]},
        "features": list(FEATURES), "baseline_feature": BASELINE_FEATURE,
        "models": record_models,
        "tree_model_of_the_sensitivity_run": best_tree,
        "mae_sai_tambons": tambon_rows,
        "label": label_record,
        "features_record_sha256": sha256_file(work / "features_record.json"),
        "files_outside_git": {"models_v1.joblib": sha256_file(model_path)},
        "libraries": {"python": sys.version.split()[0], "numpy": np.__version__, "scikit_learn": sklearn.__version__},
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    if freeze_path.exists():
        freeze["supersedes"] = {"reason": arguments.reason, "sha256": sha256_file(freeze_path)}
    write_json(freeze_path, freeze)
    print(json.dumps({kind: {key: record_models[kind]["out_of_fold_on_mae_sai"][key] for key in ("roc_auc", "average_precision", "brier")}
                      for kind in record_models}, indent=1))


# ---------------------------------------------------------------------------
# Stage 3: the test districts, once
# ---------------------------------------------------------------------------


def write_map(path: Path, value: np.ndarray, label: np.ndarray, district: np.ndarray) -> None:
    """One picture: the model value and the season layer over the four districts, at 120 m per pixel."""

    from PIL import Image, ImageDraw

    rows = np.nonzero((district > 0).any(axis=1))[0]
    columns = np.nonzero((district > 0).any(axis=0))[0]
    window = np.s_[rows.min():rows.max() + 1:4, columns.min():columns.max() + 1:4]
    inside = district[window] > 0
    shown = np.nan_to_num(value[window], nan=0.0)
    ramp = np.dstack([0.96 - 0.86 * shown, 0.97 - 0.62 * shown, 0.99 - 0.35 * shown])
    ramp[~inside] = 1.0
    flag = np.where(label[window][..., None], np.array([0.10, 0.35, 0.64]), np.array([0.93, 0.94, 0.95]))
    flag[~inside] = 1.0
    edges = np.zeros(inside.shape, dtype=bool)
    code = district[window]
    edges[:-1, :] |= code[:-1, :] != code[1:, :]
    edges[:, :-1] |= code[:, :-1] != code[:, 1:]
    panels = []
    for array, title in ((ramp, "Model value (darker = more likely inside the 2024 season layer)"),
                         (flag, "2024 season layer of UNOSAT and GISTDA")):
        array = array.copy()
        array[edges] = (0.25, 0.25, 0.25)
        image = Image.fromarray((np.clip(array, 0, 1) * 255).astype("uint8"))
        ImageDraw.Draw(image).rectangle([0, 0, image.width, 14], fill=(0, 0, 0))
        ImageDraw.Draw(image).text((4, 2), title, fill=(255, 255, 255))
        panels.append(image)
    sheet = Image.new("RGB", (panels[0].width, panels[0].height * 2 + 6), (255, 255, 255))
    sheet.paste(panels[0], (0, 0))
    sheet.paste(panels[1], (0, panels[0].height + 6))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)


def stage_test(arguments: argparse.Namespace) -> None:
    import joblib
    from sklearn.inspection import permutation_importance

    external = Path(arguments.external_root)
    work = external / WORK
    freeze_path = ROOT / OUTPUT_DIR / FREEZE_NAME
    result_path = ROOT / OUTPUT_DIR / RESULT_NAME
    if not freeze_path.exists():
        raise BuildError("no freeze record: run the fit stage first and commit it")
    if result_path.exists():
        raise BuildError("the result exists: the test districts are read once (plan section 2)")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze["plan"]["sha256"] != sha256_file(ROOT / PLAN):
        raise BuildError("the plan changed after the model was frozen")
    model_path = work / "models_v1.joblib"
    if sha256_file(model_path) != freeze["files_outside_git"]["models_v1.joblib"]:
        raise BuildError("the fitted models are not the ones the freeze record binds")
    _features_record, stack, district, _tambon, land_cover, transform = load_features(work)
    models = joblib.load(model_path)
    label_raster, label_record = season_layer_cells(external, TEST_DISTRICTS, district.shape, transform)
    cells = cell_table(stack, district, land_cover, TEST_DISTRICTS, transform)
    label = label_raster[cells["rows"], cells["columns"]]
    prevalence = float(freeze["cells"]["flooded_share"])

    predicted: dict[str, np.ndarray] = {}
    for name, entry in models.items():
        raw = entry["model"].predict_proba(cells["features"][:, entry["columns"]])[:, 1]
        predicted[name] = entry["calibrator"].predict(raw)
    by_model: dict[str, Any] = {}
    for name, values in predicted.items():
        districts = {}
        for code in TEST_DISTRICTS:
            inside = cells["district"] == DISTRICT_CODES[code]
            districts[code] = {"name": DISTRICT_NAMES[code], **ml.scores(values[inside], label[inside], training_prevalence=prevalence)}
        by_model[name] = {"three_districts_together": ml.scores(values, label, training_prevalence=prevalence), "by_district": districts}
    decision = ml.cite_decision({kind: by_model[kind]["three_districts_together"] for kind in (ml.BASELINE, ml.RANDOM_FOREST, ml.GRADIENT_BOOSTING)})

    explained = decision["model_to_cite"] if decision["model_to_cite"] != ml.BASELINE else freeze["tree_model_of_the_sensitivity_run"]
    entry = models[explained]
    sample = np.random.default_rng(ml.SEED).choice(label.size, size=min(200_000, label.size), replace=False)
    importance = permutation_importance(entry["model"], cells["features"][sample][:, entry["columns"]], label[sample].astype("int64"),
                                        scoring="roc_auc", n_repeats=5, random_state=ml.SEED, n_jobs=1)
    names = [FEATURES[position] for position in entry["columns"]]
    contributions = sorted(({"feature": name, "drop_in_roc_auc": round(float(mean), 6), "spread": round(float(spread), 6)}
                            for name, mean, spread in zip(names, importance.importances_mean, importance.importances_std)),
                           key=lambda row: -row["drop_in_roc_auc"])

    # The map: the cited model over all four districts (Mae Sai shown with the final model, in sample).
    shown = decision["model_to_cite"]
    entry = models[shown]
    everything = cell_table(stack, district, land_cover, (TRAIN_DISTRICT, *TEST_DISTRICTS), transform)
    value = np.full(district.shape, np.nan, dtype="float32")
    value[everything["rows"], everything["columns"]] = entry["calibrator"].predict(
        entry["model"].predict_proba(everything["features"][:, entry["columns"]])[:, 1])
    train_label, _record = season_layer_cells(external, (TRAIN_DISTRICT,), district.shape, transform)
    figure_path = ROOT / OUTPUT_DIR / FIGURE_NAME
    write_map(figure_path, value, label_raster | train_label, district)

    result = {
        "schema": "floodguard.flood_susceptibility.result.v1", **envelope(),
        "what_this_is": "A model of how likely a 30 m cell is to lie inside the area mapped as water in the 2024 season, "
                        "fitted on Mae Sai district and tested once on the three districts that border it.",
        "label": "agreement with the 2024 season layer on districts the model never saw; not accuracy against the ground",
        "freeze_record": {"path": f"{OUTPUT_DIR}/{FREEZE_NAME}", "sha256": sha256_file(freeze_path)},
        "training_district": {"code": TRAIN_DISTRICT, "name": DISTRICT_NAMES[TRAIN_DISTRICT], **freeze["cells"]},
        "test_districts": {code: DISTRICT_NAMES[code] for code in TEST_DISTRICTS},
        "test_cells": {"cells": int(label.size), "flooded": int(label.sum()), "flooded_share": round(float(label.mean()), 6)},
        "models": {name: {"settings": freeze["models"][name].get("settings"), "features": freeze["models"][name]["features"],
                          "out_of_fold_on_mae_sai": {key: freeze["models"][name]["out_of_fold_on_mae_sai"][key]
                                                     for key in ("roc_auc", "average_precision", "brier", "expected_calibration_error")},
                          "test": by_model[name]} for name in by_model},
        "which_model_is_cited": decision,
        "feature_contributions": {"model": explained, "method": "permutation importance on 200,000 test cells, 5 repeats, drop in ROC AUC",
                                  "in_place_of": "SHAP, which the proposal names and which is not installed", "features": contributions},
        "mae_sai_tambons": freeze["mae_sai_tambons"],
        "figure": f"{OUTPUT_DIR}/{FIGURE_NAME}",
        "credits": [
            "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed by FloodGuard: repaired, "
            "projected, cut to four districts and put on a 30 m grid; figures derived from it are shared under CC BY-SA 4.0.",
            "Copernicus DEM GLO-30. ESA WorldCover 2021 v200 (CC BY 4.0). Boundaries: HDX Thailand COD-AB.",
        ],
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    write_json(result_path, result)
    receipt = {
        "schema": "floodguard.flood_susceptibility.receipt.v1", **envelope(),
        "run_kind": "first_and_only_test_run",
        "inputs": {"freeze_record": result["freeze_record"], "label": label_record,
                   "features_record_sha256": freeze["features_record_sha256"],
                   "models": freeze["files_outside_git"]},
        "outputs": {f"{OUTPUT_DIR}/{RESULT_NAME}": {"sha256": sha256_file(result_path)},
                    f"{OUTPUT_DIR}/{FIGURE_NAME}": {"sha256": sha256_file(figure_path)}},
    }
    write_json(ROOT / OUTPUT_DIR / RECEIPT_NAME, receipt)
    brief = {name: {key: by_model[name]["three_districts_together"][key] for key in ("roc_auc", "average_precision", "brier", "brier_skill", "expected_calibration_error")}
             for name in by_model}
    print(json.dumps({"test": brief, "cited": decision["model_to_cite"], "top_features": contributions[:5]}, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    stages = parser.add_subparsers(dest="stage", required=True)
    for name in ("features", "fit", "test"):
        stage = stages.add_parser(name)
        stage.add_argument("--external-root", required=True)
        if name == "fit":
            stage.add_argument("--replace", action="store_true")
            stage.add_argument("--reason", default="")
    arguments = parser.parse_args()
    {"features": stage_features, "fit": stage_fit, "test": stage_test}[arguments.stage](arguments)


if __name__ == "__main__":
    try:
        main()
    except BuildError as error:
        raise SystemExit(f"refused: {error}") from error
