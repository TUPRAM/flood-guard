"""Improving the radar flood detection: baselines, development, freeze, and one test on held-out THEOS-2 chips.

The plan is ``docs/proposal_execution/radar_detection_improvement_plan_v1.md``. Stages, in its order:

``baselines``
    Fetches the dry-season passes of every development area and of Mae Sai's September pass, and caches them.

``develop``
    Builds the features, tries the changes of the plan on the development data with areas held out in turn,
    applies the plan's rule for keeping a change, and freezes one detector. The freeze record is committed.

``reference``
    Builds the water reference of the two held-out THEOS-2 chips from the images alone. Its record is committed.

``test``
    Runs the frozen detector, the simple threshold and the three fixed rules on the held-out chips, once.

The agency layer used in development is held at the ``local`` level (decision log R33): rasters, feature tables
and models stay in the work folder outside Git. Every figure is agreement with a reference layer, not accuracy.
No FPPS and no A-E class is computed, and nothing here is an official warning.

Example::

    python scripts/build_radar_detection_improvement.py baselines --external-root <external-data-root>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import flood_susceptibility_ml as ml  # noqa: E402
from floodguard import radar_candidates as rc  # noqa: E402
from floodguard import radar_detection as rd  # noqa: E402
from floodguard import radar_flood_classifier as rfc  # noqa: E402
from floodguard import s1_rtc  # noqa: E402
from floodguard import theos2_cross_check as cc  # noqa: E402

PLAN = "docs/proposal_execution/radar_detection_improvement_plan_v1.md"
OUTPUT_DIR = "outputs/radar_detection_improvement"
WORK = Path("proposal_execution") / "radar_detection_improvement_v1"
SOURCE_TIMESTAMP = "2024-10-22 (agency layer); THEOS-2 2025-07-30T03:33Z (development); THEOS-2 2025-07-31T03:51Z (held out)"

# The dry season before each event, same orbit as the event pass: three passes, named before any was read.
DRY_CHIANG_RAI = {
    "20240224": ("S1A_IW_GRDH_1SDV_20240224T231601_20240224T231626_052707_066098_rtc",
                 "S1A_IW_GRDH_1SDV_20240224T231626_20240224T231651_052707_066098_rtc"),
    "20240307": ("S1A_IW_GRDH_1SDV_20240307T231601_20240307T231626_052882_06668F_rtc",
                 "S1A_IW_GRDH_1SDV_20240307T231626_20240307T231651_052882_06668F_rtc"),
    "20240412": ("S1A_IW_GRDH_1SDV_20240412T231601_20240412T231626_053407_067A69_rtc",
                 "S1A_IW_GRDH_1SDV_20240412T231626_20240412T231651_053407_067A69_rtc"),
}
DRY_SUKHOTHAI = {
    "20250225": ("S1A_IW_GRDH_1SDV_20250225T230834_20250225T230859_058059_072B31_rtc",),
    "20250309": ("S1A_IW_GRDH_1SDV_20250309T230835_20250309T230900_058234_073251_rtc",),
    "20250414": ("S1A_IW_GRDH_1SDV_20250414T230835_20250414T230900_058759_074778_rtc",),
}
MAE_SAI_SEPTEMBER = ("S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_055682_06CCBA_rtc",)


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


classifier = load_script("build_radar_flood_classifier")
dated = classifier.dated
t2 = classifier.t2
BuildError = t2.BuildError
EPSG, CELL_M = dated.EPSG, dated.CELL_M


def area_grids(external: Path) -> dict[str, dict[str, Any]]:
    """Every development area with its lattice grid and the folder that holds its cached rasters."""

    areas: dict[str, dict[str, Any]] = {}
    for code, name in classifier.TRAINING_DISTRICTS.items():
        geometry = classifier.district_geometry(external, code)
        _tiles, west, north, rows, columns = t2.lattice_grid(geometry.bounds)
        areas[code] = {"name": name, "grid": (west, north, rows, columns), "folder": external / classifier.WORK,
                       "dry": DRY_CHIANG_RAI, "kind": "training_district"}
    record = json.loads((ROOT / dated.OUTPUT_DIR / dated.REFERENCE_NAME).read_text(encoding="utf-8"))["grid_10m"]
    areas["mae_sai"] = {"name": "Mae Sai", "grid": (float(record["west"]), float(record["north"]), int(record["rows"]), int(record["columns"])),
                        "folder": external / classifier.DATED_WORK, "dry": DRY_CHIANG_RAI, "kind": "held_out_district"}
    record = json.loads((ROOT / t2.OUTPUT_DIR / t2.REFERENCE_NAME).read_text(encoding="utf-8"))["grid_10m"]
    areas["sukhothai"] = {"name": "Sukhothai tile", "grid": (float(record["west"]), float(record["north"]), int(record["rows"]), int(record["columns"])),
                          "folder": external / classifier.SUKHOTHAI_WORK, "dry": DRY_SUKHOTHAI, "kind": "theos2_tile"}
    return areas


def dry_baseline(external: Path, key: str, area: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Fetch the dry-season passes of an area and cache their median and spread (dB; VV, VH) as one raster."""

    work = external / WORK
    work.mkdir(parents=True, exist_ok=True)
    grid = area["grid"]
    passes = {date: s1_rtc.fetch_pass(work, grid, items, f"s1_{key}_dry_{date}", epsg=EPSG, cell_m=CELL_M)
              for date, items in area["dry"].items()}
    path = work / f"dry_{key}.tif"
    if not path.exists():
        median, spread = s1_rtc.median_of_passes([work / entry["window_file"] for entry in passes.values()])
        s1_rtc.write_window(path, [median[0], median[1], spread[0], spread[1]], grid, epsg=EPSG, cell_m=CELL_M)
    return path, {"passes": passes, "file": path.name, "sha256": s1_rtc.sha256_file(path),
                  "bands": ["median VV dB", "median VH dB", "spread VV dB", "spread VH dB"]}


def stage_baselines(arguments: argparse.Namespace) -> None:
    external = Path(arguments.external_root)
    work = external / WORK
    work.mkdir(parents=True, exist_ok=True)
    areas = area_grids(external)
    record: dict[str, Any] = {}
    only = [key for key in (arguments.only or "").split(",") if key]
    for key, area in areas.items():
        if only and key not in only:
            continue
        started = time.time()
        _path, record[key] = dry_baseline(external, key, area)
        print(f"{area['name']}: dry-season baseline of {len(area['dry'])} passes, {time.time() - started:.0f} s", flush=True)
    if only and "mae_sai" not in only:
        return  # a helper run for some areas: the record is written by the run that covers them all
    started = time.time()
    record["mae_sai_september_pass"] = s1_rtc.fetch_pass(work, areas["mae_sai"]["grid"], MAE_SAI_SEPTEMBER, "s1_mae_sai_20240915",
                                                         epsg=EPSG, cell_m=CELL_M)
    print(f"Mae Sai, pass of 15 September 2024: {time.time() - started:.0f} s", flush=True)
    if not only:
        t2.write_json(work / "baselines_record.json", {"fetched_at_utc": t2.now_utc(), "areas": record})


# ---------------------------------------------------------------------------
# Stage 2: development on the areas that have been seen
# ---------------------------------------------------------------------------

STEP_THRESHOLD = "simple_threshold"
STEP_SCENE_THRESHOLD = "threshold_with_a_cut_per_scene"
STEP_TREES_AFTER = "trees_without_the_image_before_with_a_cut_per_scene"
STEP_TREES_BASELINE = "trees_against_the_dry_baseline_with_a_cut_per_scene"
STEP_TWO_SOURCES = "trees_against_the_dry_baseline_two_label_sources"
TREE_SETTINGS = {"learning_rate": 0.1, "max_leaf_nodes": 15}
GROW_LOGIT = 1.0
STRIP_ROWS, HALO = 1024, 2

ASSUMPTIONS = [
    "Development labels are the layer UNOSAT and GISTDA dated 22 October 2024 (as provided) and the water read from the THEOS-2 image of Sukhothai.",
    "The dry-season baseline is the median of three passes of the same orbit, in dB, named before any was read.",
    "A scene sets its own cut from its tiles that hold two clear groups of values; a scene with no such tile takes the frozen cut.",
    "Every feature comes from Sentinel-1, or is slope or land cover. No feature says where water usually stands.",
]
LIMITS = [
    "Development data are one province in October 2024 and one tile in July 2025; both have been looked at before.",
    "The agency layer was not checked in the field and may come from the same radar pass; the THEOS-2 image is 44 hours older than the radar.",
    "C-band radar does not see water under rice, trees or between buildings, nor water that drained before the pass.",
    "Every figure is agreement with a reference layer, not accuracy. No detector enters a planning score.",
]


def envelope() -> dict[str, Any]:
    return {
        "generated_at_utc": t2.now_utc(),
        "source_timestamp": SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "Detectors developed on an agency layer that was not checked in the field and on one optical tile; no ground check.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "plan": {"path": PLAN, "sha256": t2.sha256_file(ROOT / PLAN)},
    }


def strip_baseline_features(after_path: Path, dry_path: Path, slope: np.ndarray, land_cover: np.ndarray) -> dict[str, np.ndarray]:
    """The baseline features of a whole grid, computed in strips of rows with a halo."""

    import rasterio
    from rasterio.windows import Window

    rows, columns = slope.shape
    features = {name: np.full((rows, columns), np.nan, dtype="float32") for name in rd.FEATURES_BASELINE}
    with rasterio.open(after_path) as after, rasterio.open(dry_path) as dry:
        for start in range(0, rows, STRIP_ROWS):
            stop = min(rows, start + STRIP_ROWS)
            top, bottom = max(0, start - HALO), min(rows, stop + HALO)
            window = Window(0, top, columns, bottom - top)
            baseline = dry.read(window=window).astype("float64")
            part = rd.baseline_features(after.read(window=window), baseline[:2], baseline[2:], slope[top:bottom], land_cover[top:bottom])
            for name, values in part.items():
                features[name][start:stop] = values[start - top:start - top + (stop - start)]
    return features


def read_slope(folder: Path, names: list[str]) -> np.ndarray:
    import rasterio

    height = None
    for name in names:
        with rasterio.open(folder / name) as source:
            part = source.read(1)
        part = np.where(part == -9999.0, np.nan, part)
        height = part if height is None else np.where(np.isfinite(height), height, part)
    return rc.slope_degrees(height, CELL_M, CELL_M)


def area_rasters(external: Path, key: str, area: dict[str, Any]) -> dict[str, Any]:
    """Features, slope and land cover of one area on its lattice grid."""

    import rasterio

    work = external / WORK
    folder = area["folder"]
    if area["kind"] == "training_district":
        after, cover_name = folder / f"s1_{key}_after.tif", f"worldcover_{key}.tif"
        dems = [f"dem_{key}_{index}.tif" for index in range(len(dated.DEM_URLS))]
    elif key == "mae_sai":
        after, cover_name = folder / "s1_post_gamma0.tif", "worldcover_10m.tif"
        dems = [f"dem_{index}_10m.tif" for index in range(len(dated.DEM_URLS))]
    else:
        after, cover_name = folder / "s1_post_gamma0.tif", "worldcover_10m.tif"
        dems = [f"dem_{index}_10m.tif" for index in range(len(t2.DEM_URLS))]
    with rasterio.open(folder / cover_name) as source:
        land_cover = source.read(1)
    slope = read_slope(folder, dems)
    features = strip_baseline_features(after, work / f"dry_{key}.tif", slope, land_cover)
    return {"features": features, "slope": slope, "land_cover": land_cover, "after": after, "dry": work / f"dry_{key}.tif"}


def table(features: dict[str, np.ndarray], names: tuple[str, ...], where: np.ndarray) -> np.ndarray:
    return np.column_stack([features[name][where] for name in names]).astype("float64")


def predict_raster(model: Any, features: dict[str, np.ndarray], names: tuple[str, ...], where: np.ndarray) -> np.ndarray:
    """The model's value for the cells of ``where``; NaN elsewhere."""

    out = np.full(where.shape, np.nan, dtype="float32")
    rows = np.flatnonzero(where.ravel())
    flat = out.ravel()
    for start in range(0, rows.size, 500_000):
        chunk = rows[start:start + 500_000]
        block = np.column_stack([features[name].ravel()[chunk] for name in names]).astype("float64")
        flat[chunk] = model.predict_proba(block)[:, 1]
    return out


def logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(probability.astype("float64"), 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped))


def detect_with_model(raw: np.ndarray, usable: np.ndarray, calibration: Any, fallback_cut: float) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Flags of a model on a scene: the scene's own cut on the model's values, or the frozen cut when it has none."""

    score = np.where(usable, logit(np.nan_to_num(raw, nan=0.5)), np.nan)
    cut = rd.scene_cut(score, usable, fallback=float("nan"))
    if cut["tiles_with_two_groups"]:
        flag = usable & (score >= cut["cut"])
        nearly = usable & (score >= cut["cut"] - GROW_LOGIT)
    else:
        calibrated = np.zeros(raw.shape, dtype="float64")
        calibrated[usable] = calibration.predict(raw[usable].astype("float64"))
        flag = usable & (calibrated >= fallback_cut)
        nearly = usable & (calibrated >= fallback_cut / 2)
        cut = {**cut, "cut": fallback_cut, "cut_is_on": "the calibrated value"}
    return flag, nearly, cut


def detect_with_threshold(vh_after: np.ndarray, usable: np.ndarray, fallback_db: float) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Flags of a threshold on VH after: the scene's own cut, or the frozen one."""

    cut = rd.scene_cut(vh_after, usable, fallback=fallback_db)
    return usable & (vh_after <= cut["cut"]), usable & (vh_after <= cut["cut"] + rd.GROW_DB), cut


def counts(flag: np.ndarray, compared: np.ndarray, wet: np.ndarray) -> dict[str, Any]:
    return rfc.flag_counts(flag[compared], wet[compared])


def fit_trees(features: np.ndarray, label: np.ndarray) -> Any:
    return ml.make_model(ml.GRADIENT_BOOSTING, TREE_SETTINGS, seed=rfc.SEED).fit(features, label.astype("int64"))


def stage_develop(arguments: argparse.Namespace) -> None:
    import joblib
    import rasterio

    external = Path(arguments.external_root)
    work = external / WORK
    freeze_path = ROOT / OUTPUT_DIR / "freeze_v1.json"
    if freeze_path.exists() and not arguments.replace:
        raise BuildError(f"{freeze_path} exists; use --replace with --reason")
    if (ROOT / OUTPUT_DIR / "held_out_reference_v1.json").exists():
        raise BuildError("the held-out chips have been read; the detector is not developed again after that")
    areas = area_grids(external)
    classifier_work = external / classifier.WORK

    # --- the training table: the sample of work package 7 with the new features -------------------------------
    sample = np.load(classifier_work / "training_sample.npz")
    xy, district_index, label, weight = sample["xy"].astype("float64"), sample["district"], sample["label"].astype(bool), sample["weight"]
    train = np.full((label.size, len(rd.FEATURES_BASELINE)), np.nan)
    for position, code in enumerate(classifier.TRAINING_DISTRICTS):
        started = time.time()
        rasters = area_rasters(external, code, areas[code])
        west, north, _rows, _columns = areas[code]["grid"]
        chosen = district_index == position
        column = np.floor((xy[chosen, 0] - west) / CELL_M).astype("int64")
        row = np.floor((north - xy[chosen, 1]) / CELL_M).astype("int64")
        train[chosen] = np.column_stack([rasters["features"][name][row, column] for name in rd.FEATURES_BASELINE])
        del rasters
        print(f"{classifier.TRAINING_DISTRICTS[code]}: features of {int(chosen.sum())} sample cells, {time.time() - started:.0f} s", flush=True)
    complete = np.isfinite(train).all(axis=1)
    train, label, weight, xy = train[complete], label[complete], weight[complete], xy[complete]
    folds = ml.block_folds(xy[:, 0], xy[:, 1])

    # --- the two held-out areas -----------------------------------------------------------------------------------
    held: dict[str, dict[str, Any]] = {}
    rasters = area_rasters(external, "mae_sai", areas["mae_sai"])
    with rasterio.open(areas["mae_sai"]["folder"] / "dated_reference_10m.tif") as source:
        reference, in_district, permanent_water = (source.read(band).astype(bool) for band in (1, 2, 3))
    usable = rfc.usable_cells(rasters["features"], rd.FEATURES_BASELINE) & ~permanent_water
    held["mae_sai"] = {**rasters, "usable": usable, "compared": usable & in_district, "wet": reference, "permanent_water": permanent_water}
    rasters = area_rasters(external, "sukhothai", areas["sukhothai"])
    with rasterio.open(areas["sukhothai"]["folder"] / "theos2_reference_10m.tif") as source:
        cells = cc.reference_cells(source.read(1), source.read(2))
    permanent_water = rasters["land_cover"] == t2.PERMANENT_WATER_CLASS
    usable = rfc.usable_cells(rasters["features"], rd.FEATURES_BASELINE) & ~permanent_water
    held["sukhothai"] = {**rasters, "usable": usable, "compared": usable & cells["compared"], "wet": cells["wet"], "permanent_water": permanent_water}

    # --- the models -----------------------------------------------------------------------------------------------
    threshold_bundle = joblib.load(classifier_work / f"model_{rfc.BASELINE}.joblib")
    after_bundle = joblib.load(classifier_work / f"model_{rfc.AFTER_ONLY}.joblib")
    grid_db = np.linspace(-35, -5, 3001).reshape(-1, 1)
    flagged = threshold_bundle["calibration"].predict(threshold_bundle["model"].predict_proba(grid_db)[:, 1]) >= threshold_bundle["cut"]
    threshold_db = float(grid_db[flagged].max())

    raw_oof = ml.out_of_fold(ml.GRADIENT_BOOSTING, TREE_SETTINGS, train, label, folds, seed=rfc.SEED)
    calibration = rfc.weighted_isotonic(raw_oof, label, weight)
    frozen_cut = rfc.best_cut(calibration.predict(raw_oof), label, weight)
    baseline_model = fit_trees(train, label)

    # Two label sources: the Sukhothai cells join the training. For Mae Sai the model sees all of them; for Sukhothai
    # itself the tile is cut in a western and an eastern half and each half is read by a model that did not see it.
    tile = held["sukhothai"]
    tile_rows = table(tile["features"], rd.FEATURES_BASELINE, tile["compared"])
    tile_label = tile["wet"][tile["compared"]]
    columns_of_cells = np.nonzero(tile["compared"])[1]
    west_half = columns_of_cells < np.median(columns_of_cells)
    raw_two = np.full(label.shape, np.nan)
    for fold in np.unique(folds):
        inside = folds == fold
        model = fit_trees(np.vstack([train[~inside], tile_rows]), np.concatenate([label[~inside], tile_label]))
        raw_two[inside] = model.predict_proba(train[inside])[:, 1]
    calibration_two = rfc.weighted_isotonic(raw_two, label, weight)
    frozen_cut_two = rfc.best_cut(calibration_two.predict(raw_two), label, weight)
    two_model = fit_trees(np.vstack([train, tile_rows]), np.concatenate([label, tile_label]))
    half_models = {"west": fit_trees(np.vstack([train, tile_rows[~west_half]]), np.concatenate([label, tile_label[~west_half]])),
                   "east": fit_trees(np.vstack([train, tile_rows[west_half]]), np.concatenate([label, tile_label[west_half]]))}

    # --- every step on the two held-out areas -----------------------------------------------------------------------
    figures: dict[str, dict[str, Any]] = {}
    flags: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] = {}

    def record(step: str, area_key: str, flag: np.ndarray, nearly: np.ndarray, cut: dict[str, Any] | None) -> None:
        area = held[area_key]
        figures.setdefault(step, {})[area_key] = {**counts(flag, area["compared"], area["wet"]), "cut": cut}
        flags.setdefault(step, {})[area_key] = (flag, nearly)

    for area_key, area in held.items():
        features, usable = area["features"], area["usable"]
        vh = features["vh_after_db"].astype("float64")
        record(STEP_THRESHOLD, area_key, usable & (vh <= threshold_db), usable & (vh <= threshold_db + rd.GROW_DB),
               {"cut": threshold_db, "source": "frozen in work package 7"})
        record(STEP_SCENE_THRESHOLD, area_key, *detect_with_threshold(vh, usable, threshold_db))
        raw = predict_raster(after_bundle["model"], features, rfc.FEATURES_AFTER_ONLY, usable)
        record(STEP_TREES_AFTER, area_key, *detect_with_model(raw, usable, after_bundle["calibration"], after_bundle["cut"]))
        raw = predict_raster(baseline_model, features, rd.FEATURES_BASELINE, usable)
        record(STEP_TREES_BASELINE, area_key, *detect_with_model(raw, usable, calibration, frozen_cut["cut"]))
        if area_key == "mae_sai":
            raw = predict_raster(two_model, features, rd.FEATURES_BASELINE, usable)
            record(STEP_TWO_SOURCES, area_key, *detect_with_model(raw, usable, calibration_two, frozen_cut_two["cut"]))
        else:
            # Each half is read by the model that did not see it; the scene's cut is taken on the two together.
            middle = float(np.median(columns_of_cells))
            column_index = np.broadcast_to(np.arange(usable.shape[1]), usable.shape)
            raw = np.where(column_index < middle,
                           predict_raster(half_models["west"], features, rd.FEATURES_BASELINE, usable),
                           predict_raster(half_models["east"], features, rd.FEATURES_BASELINE, usable))
            record(STEP_TWO_SOURCES, area_key, *detect_with_model(raw, usable, calibration_two, frozen_cut_two["cut"]))

    order = [STEP_THRESHOLD, STEP_SCENE_THRESHOLD, STEP_TREES_AFTER, STEP_TREES_BASELINE, STEP_TWO_SOURCES]
    steps = [{"name": name, "iou": {area_key: figures[name][area_key]["iou"] for area_key in held}} for name in order]
    first = rd.keep_changes(steps)
    cleaned = f"{first['kept']}_cleaned"
    for area_key, area in held.items():
        flag, nearly = flags[first["kept"]][area_key]
        record(cleaned, area_key, rd.clean(flag, area["slope"], grow_from=nearly), nearly, figures[first["kept"]][area_key]["cut"])
    steps.append({"name": cleaned, "iou": {area_key: figures[cleaned][area_key]["iou"] for area_key in held}})
    ladder = rd.keep_changes(steps)
    kept = ladder["kept"]

    # --- A: the fixed UN-SPIDER rule with the dry-season baseline as its image before -----------------------------
    rule_with_baseline = {}
    for area_key, area in held.items():
        with rasterio.open(area["after"]) as source:
            after_vh = source.read(2).astype("float64")
        with rasterio.open(area["dry"]) as source:
            dry_vh = np.power(10.0, source.read(2).astype("float64") / 10.0)
        candidate, _, _, _ = rc.un_spider_candidate(dry_vh, after_vh, in_frame=np.ones(after_vh.shape, dtype=bool),
                                                    permanent_water=area["permanent_water"], slope=area["slope"], cell_m=CELL_M)
        rule_with_baseline[area_key] = counts(candidate == 1, area["compared"], area["wet"])

    # --- F: where the radar cannot be asked ----------------------------------------------------------------------
    not_asked = {}
    for area_key, area in held.items():
        seen = rd.observable(area["land_cover"])
        flag, _nearly = flags[kept][area_key]
        compared = area["compared"]
        not_asked[area_key] = {
            "compared_cells": int(compared.sum()), "cells_not_observable": int((compared & ~seen).sum()),
            "reference_water_cells_not_observable": int((compared & ~seen & area["wet"]).sum()),
            "kept_detector_on_observable_cells_only": counts(flag, compared & seen, area["wet"]),
        }

    base = kept.removesuffix("_cleaned")
    bundle: dict[str, Any] = {"step": kept, "base": base, "cleaned": kept.endswith("_cleaned"), "threshold_db": threshold_db}
    if base == STEP_TREES_AFTER:
        bundle.update(model=after_bundle["model"], calibration=after_bundle["calibration"], cut=after_bundle["cut"], features=rfc.FEATURES_AFTER_ONLY)
    elif base == STEP_TREES_BASELINE:
        bundle.update(model=baseline_model, calibration=calibration, cut=frozen_cut["cut"], features=rd.FEATURES_BASELINE)
    elif base == STEP_TWO_SOURCES:
        bundle.update(model=two_model, calibration=calibration_two, cut=frozen_cut_two["cut"], features=rd.FEATURES_BASELINE)
    joblib.dump(bundle, work / "frozen_detector.joblib")

    freeze = {
        "schema": "floodguard.radar_detection_freeze.v1",
        **envelope(),
        "what_this_is": "The changes of the plan tried on the development data with areas held out, the rule for keeping a change applied, and the one detector frozen for the test.",
        "rights_note": "The agency layer is held at the local level (decision log R33): rasters, tables and models stay outside Git; this record holds whole-frame figures.",
        "held_out_chips_read": False,
        "development": {
            "training_cells": int(label.size), "training_water_cells": int(label.sum()),
            "sample_cells_left_out_for_a_missing_feature": int((~complete).sum()),
            "held_out_areas": {area_key: {"compared_cells": int(area["compared"].sum()), "reference_water_cells": int((area["compared"] & area["wet"]).sum())}
                               for area_key, area in held.items()},
            "dry_season_passes": {"chiang_rai": sorted(DRY_CHIANG_RAI), "sukhothai": sorted(DRY_SUKHOTHAI)},
            "trees": {"kind": "HistGradientBoostingClassifier", "settings": TREE_SETTINGS, "features": list(rd.FEATURES_BASELINE),
                      "out_of_fold_weighted": {"average_precision": rfc.ranking(calibration.predict(raw_oof), label, weight)["average_precision"],
                                               "frozen_cut": frozen_cut["cut"], "iou_at_the_frozen_cut": frozen_cut["iou_out_of_fold"]}},
            "two_label_sources": {"sukhothai_cells_added": int(tile_label.size), "frozen_cut": frozen_cut_two["cut"],
                                  "how_sukhothai_is_scored": "the tile is cut into a western and an eastern half; each half is read by a model that saw the other half only"},
        },
        "steps": figures,
        "ladder": ladder,
        "change_A_fixed_rule_with_the_dry_baseline": {"rule": "UN-SPIDER practice, image before = the dry-season median", **rule_with_baseline},
        "change_F_not_observable": {"classes": list(rd.NOT_OBSERVABLE_CLASSES), **not_asked},
        "frozen_detector": {"step": kept, "base": base, "cleaned": bundle["cleaned"], "simple_threshold_db": round(threshold_db, 2),
                            "file_outside_git": {"name": "frozen_detector.joblib", "sha256": t2.sha256_file(work / "frozen_detector.joblib")}},
        "not_done": ["Change E without the height above the nearest stream: no drainage model exists for the tiles; slopes, group size and growth only.",
                     "Change F marks tree cover and built-up ground and counts them; the terrain model of work package 4 covers Mae Sai only and is not joined here.",
                     "The trees were fitted with one setting, the one work package 7 picked for the primary model; no new tuning."],
        "assumptions": ASSUMPTIONS,
        "limits": LIMITS,
    }
    freeze["supersedes"] = t2.superseded(freeze_path, arguments, ("ladder", "steps"), freeze)
    t2.write_json(freeze_path, freeze)
    for name in [*order, cleaned]:
        print(name, {area_key: (figures[name][area_key]["flagged_that_is_reference_water"], figures[name][area_key]["reference_water_flagged"],
                                figures[name][area_key]["iou"]) for area_key in held}, flush=True)
    print("fixed rule with the dry baseline", {key: value["iou"] for key, value in rule_with_baseline.items()})
    print("kept:", kept)


# ---------------------------------------------------------------------------
# Stages 3 and 4: the held-out THEOS-2 chips
# ---------------------------------------------------------------------------

HELD_OUT = {"chip_001": "IMG_T2V_20250731035100_ORTHO_PMS_32-001.tif", "chip_003": "IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif"}
HELD_OUT_ACQUIRED_UTC = "2025-07-31T03:51:00Z"
DRY_DATES_2025 = ("2025-02-25", "2025-03-09", "2025-04-14")
RULES = ("un_spider", "m1_literal", "m1_v2")
SET_ASIDE = {
    "chip_001": "The image shows hill country with ploughed fields, forest and one river in a corner; it holds no flood. Its NDWI "
                "histogram has no water group, and the split of the rule marks bare soil as water. Seen on the image alone, before "
                "any radar of the chip was read. The chip is not used as a reference; it is used to count what each detector flags "
                "on ground with no flood.",
}
"""Chips whose water reference was looked at on the image alone and found unusable."""


def apply_detector(bundle: dict[str, Any], features: dict[str, np.ndarray], usable: np.ndarray, slope: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """The flags of a frozen detector on one scene."""

    vh = features["vh_after_db"].astype("float64")
    base = bundle["base"]
    if base == STEP_THRESHOLD:
        flag, nearly = usable & (vh <= bundle["threshold_db"]), usable & (vh <= bundle["threshold_db"] + rd.GROW_DB)
        cut: dict[str, Any] = {"cut": bundle["threshold_db"], "source": "frozen in work package 7"}
    elif base == STEP_SCENE_THRESHOLD:
        flag, nearly, cut = detect_with_threshold(vh, usable, bundle["threshold_db"])
    else:
        raw = predict_raster(bundle["model"], features, tuple(bundle["features"]), usable)
        flag, nearly, cut = detect_with_model(raw, usable, bundle["calibration"], bundle["cut"])
    if bundle["cleaned"]:
        flag = rd.clean(flag, slope, grow_from=nearly)
    return flag, cut


def stage_reference(arguments: argparse.Namespace) -> None:
    import csv

    import rasterio
    from rasterio.transform import from_origin

    external = Path(arguments.external_root)
    work = external / WORK
    record_path = ROOT / OUTPUT_DIR / "held_out_reference_v1.json"
    if not (ROOT / OUTPUT_DIR / "freeze_v1.json").exists():
        raise BuildError("no freeze record: the held-out chips are read only after one detector is frozen and committed")
    if record_path.exists() and not arguments.replace:
        raise BuildError(f"{record_path} exists; use --replace with --reason")
    if (ROOT / OUTPUT_DIR / "held_out_test_v1.json").exists():
        raise BuildError("the test has been run; the reference is not rebuilt after it")
    with (ROOT / "outputs/theos2_selected_file_manifest.csv").open(encoding="utf-8", newline="") as handle:
        recorded = {row["file_name"]: row["sha256"] for row in csv.DictReader(handle)}
    chips = {}
    for key, name in HELD_OUT.items():
        scene = Path(arguments.theos2_dir) / name
        scene_sha = t2.sha256_file(scene)
        if recorded.get(name) != scene_sha:
            raise BuildError(f"{name} does not have the SHA-256 the selected-file manifest records")
        chip, (west, north) = t2.read_theos2_chip(scene)
        red, green, blue, nir = (chip[t2.THEOS2_BANDS[band] - 1] for band in ("red", "green", "blue", "nir"))
        water, summary = cc.optical_water(red, green, blue, nir, nir > 0, cc.OpticalWaterConfig())
        height, width = water.shape
        bounds = (west, north - height * t2.FINE_M, west + width * t2.FINE_M, north)
        _tiles, grid_west, grid_north, rows, columns = t2.lattice_grid(bounds)
        water_share, observable_share = t2.aggregate_to_grid(water, west, north, grid_west, grid_north, rows, columns)
        cells = cc.reference_cells(water_share, observable_share)
        profile = {"driver": "GTiff", "crs": f"EPSG:{EPSG}", "compress": "deflate"}
        with rasterio.open(work / f"held_{key}_reference_10m.tif", "w", height=rows, width=columns, count=2, dtype="float32",
                           nodata=float("nan"), transform=from_origin(grid_west, grid_north, CELL_M, CELL_M), **profile) as target:
            target.write(water_share, 1)
            target.write(observable_share, 2)
        from PIL import Image

        look = np.clip(np.stack([red, green, blue], axis=-1) / max(float(np.percentile(red, 99)), 1.0) * 255, 0, 255).astype("uint8")
        marked = look.copy()
        marked[water == cc.WATER_YES] = (40, 130, 235)
        marked[water == cc.WATER_UNOBSERVABLE] = (200, 80, 200)
        Image.fromarray(np.concatenate([look[::2, ::2], marked[::2, ::2]], axis=1)).save(work / f"held_{key}_reference_look.png", optimize=True)
        cell_km2 = CELL_M * CELL_M / 1e6
        chips[key] = {
            "file_name": name, "sha256": scene_sha, "acquired_utc": HELD_OUT_ACQUIRED_UTC,
            "valid_rectangle_epsg32647": {"west": bounds[0], "south": bounds[1], "east": bounds[2], "north": bounds[3]},
            "optical_water_rule": summary,
            "grid_10m": {"epsg": EPSG, "west": grid_west, "north": grid_north, "rows": rows, "columns": columns, "cell_m": CELL_M},
            "cells_10m": {"compared": int(cells["compared"].sum()), "wet": int(cells["wet"].sum()), "dry": int(cells["dry"].sum()),
                          "compared_km2": round(int(cells["compared"].sum()) * cell_km2, 4), "wet_km2": round(int(cells["wet"].sum()) * cell_km2, 4)},
            "raster_outside_git": {"name": f"held_{key}_reference_10m.tif", "sha256": t2.sha256_file(work / f"held_{key}_reference_10m.tif")},
            "set_aside_from_the_test": SET_ASIDE.get(key),
        }
        print(key, chips[key]["cells_10m"], summary.get("ndwi_three_class_otsu"), flush=True)
    record = {
        "schema": "floodguard.radar_detection_held_out_reference.v1",
        **envelope(),
        "what_this_is": "The water reference of the two held-out THEOS-2 chips, read from the images alone with the rule of the Sukhothai cross-check and no setting made by eye. No radar of these chips has been read.",
        "freeze_record": {"path": f"{OUTPUT_DIR}/freeze_v1.json", "sha256": t2.sha256_file(ROOT / OUTPUT_DIR / "freeze_v1.json")},
        "rule": "NDWI above the upper threshold of a three-class Otsu split, computed on each chip; bright objects unobservable; water objects under 1,000 square metres dropped. The one rectangle set by eye at Sukhothai is not carried over.",
        "radar_read": False,
        "looked_at": "Each reference was looked at beside its image before any radar was read. One chip is set aside for the reason given with it.",
        "chips": chips,
        "licence": "THEOS-2 sample imagery provided by GISTDA for GeoHackathon 2026. The imagery stays outside Git; derived figures are shared.",
        "assumptions": ASSUMPTIONS[:1] + ["The water rule of the Sukhothai cross-check is applied to each held-out chip without any setting made by eye."],
        "limits": LIMITS[1:],
    }
    record["supersedes"] = t2.superseded(record_path, arguments, ("chips",), record)
    t2.write_json(record_path, record)


def passes_for_chip(grid: tuple[float, float, int, int]) -> dict[str, Any]:
    """The Sentinel-1 passes of a held-out chip, chosen by a rule fixed before any was read.

    After: the first pass after the THEOS-2 image. Before (for the fixed rules): the pass of the same orbit 12 days
    earlier. Dry season: the passes of the same orbit nearest to the three dates used at Sukhothai.
    """

    from datetime import datetime, timedelta

    from pyproj import Transformer

    west, north, rows, columns = grid
    to_lonlat = Transformer.from_crs(EPSG, 4326, always_xy=True).transform
    corners = [to_lonlat(x, y) for x in (west, west + columns * CELL_M) for y in (north, north - rows * CELL_M)]
    bbox = [min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners)]

    def when(text: str) -> datetime:
        return datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")

    def group(found: list[dict[str, Any]], around: datetime, orbit: int | None) -> list[dict[str, Any]]:
        usable = [entry for entry in found if orbit is None or entry["relative_orbit"] == orbit]
        if not usable:
            raise BuildError(f"no Sentinel-1 pass near {around.isoformat()} covers the chip")
        nearest = min(usable, key=lambda entry: abs((when(entry["datetime"]) - around).total_seconds()))
        return [entry for entry in usable if entry["relative_orbit"] == nearest["relative_orbit"]
                and abs((when(entry["datetime"]) - when(nearest["datetime"])).total_seconds()) < 300]

    image_time = when(HELD_OUT_ACQUIRED_UTC)
    after_found = [entry for entry in s1_rtc.search_passes(bbox, HELD_OUT_ACQUIRED_UTC, (image_time + timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%SZ"))
                   if when(entry["datetime"]) > image_time]
    if not after_found:
        raise BuildError("no Sentinel-1 pass in the six days after the image covers the chip")
    first = min(after_found, key=lambda entry: entry["datetime"])
    orbit = first["relative_orbit"]
    after = group(after_found, when(first["datetime"]), orbit)
    target = when(first["datetime"]) - timedelta(days=12)
    before = group(s1_rtc.search_passes(bbox, (target - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        (target + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"), relative_orbit=orbit), target, orbit)
    season = s1_rtc.search_passes(bbox, "2025-02-01T00:00:00Z", "2025-05-10T00:00:00Z", relative_orbit=orbit)
    dry = {date: group(season, datetime.strptime(date, "%Y-%m-%d") + timedelta(hours=23), orbit) for date in DRY_DATES_2025}
    return {"relative_orbit": orbit, "after": after, "before": before, "dry": dry,
            "hours_after_the_image": round((when(first["datetime"]) - image_time).total_seconds() / 3600, 1), "bbox": bbox}


def context_urls(bbox: list[float]) -> tuple[list[str], list[str]]:
    """The WorldCover and Copernicus DEM tiles that cover a lon/lat box."""

    import math

    covers = {(3 * math.floor(lat / 3), 3 * math.floor(lon / 3)) for lat in (bbox[1], bbox[3]) for lon in (bbox[0], bbox[2])}
    dems = {(math.floor(lat), math.floor(lon)) for lat in (bbox[1], bbox[3]) for lon in (bbox[0], bbox[2])}
    return ([f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N{lat:02d}E{lon:03d}_Map.tif"
             for lat, lon in sorted(covers)],
            [f"https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM/"
             f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif" for lat, lon in sorted(dems)])


def stage_test(arguments: argparse.Namespace) -> None:
    import joblib
    import rasterio

    from floodguard import geoid_m1_review as review
    from floodguard import sar_change_v2 as sar

    external = Path(arguments.external_root)
    work = external / WORK
    freeze_path, reference_path = ROOT / OUTPUT_DIR / "freeze_v1.json", ROOT / OUTPUT_DIR / "held_out_reference_v1.json"
    result_path = ROOT / OUTPUT_DIR / "held_out_test_v1.json"
    if not (freeze_path.exists() and reference_path.exists()):
        raise BuildError("the freeze record and the reference record must exist and be committed first")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    if reference["freeze_record"]["sha256"] != t2.sha256_file(freeze_path) or freeze["plan"]["sha256"] != t2.sha256_file(ROOT / PLAN):
        raise BuildError("the plan or the freeze record changed after the reference was built")
    if t2.sha256_file(work / "frozen_detector.joblib") != freeze["frozen_detector"]["file_outside_git"]["sha256"]:
        raise BuildError("frozen_detector.joblib is not the detector the freeze record binds")
    if result_path.exists() and not arguments.replace:
        raise BuildError(f"{result_path} exists; the test is run once (plan section 4)")
    bundle = joblib.load(work / "frozen_detector.joblib")
    threshold = {"base": STEP_THRESHOLD, "cleaned": False, "threshold_db": bundle["threshold_db"]}
    binding = review.require_frozen_m1_v2(ROOT)
    configs = {"un_spider": rc.UnSpiderConfig(), "m1_literal": sar.M1LiteralConfig(), "m1_v2": sar.m1_v2_config_from_json(binding["parameters"])}

    chips: dict[str, Any] = {}
    pooled: dict[str, list[np.ndarray]] = {name: [] for name in ("wet", "frozen", "threshold", *RULES)}
    for key, entry in reference["chips"].items():
        raster = work / entry["raster_outside_git"]["name"]
        if t2.sha256_file(raster) != entry["raster_outside_git"]["sha256"]:
            raise BuildError(f"{raster.name} is not the raster the reference record binds")
        grid_record = entry["grid_10m"]
        grid = (float(grid_record["west"]), float(grid_record["north"]), int(grid_record["rows"]), int(grid_record["columns"]))
        west, north, rows, columns = grid
        with rasterio.open(raster) as source:
            cells = cc.reference_cells(source.read(1), source.read(2))
        passes = passes_for_chip(grid)
        after = s1_rtc.fetch_pass(work, grid, [item["item"] for item in passes["after"]], f"s1_{key}_after", epsg=EPSG, cell_m=CELL_M)
        before = s1_rtc.fetch_pass(work, grid, [item["item"] for item in passes["before"]], f"s1_{key}_before", epsg=EPSG, cell_m=CELL_M)
        dry_records = {date: s1_rtc.fetch_pass(work, grid, [item["item"] for item in items], f"s1_{key}_dry_{date.replace('-', '')}", epsg=EPSG, cell_m=CELL_M)
                       for date, items in passes["dry"].items()}
        dry_path = work / f"dry_{key}.tif"
        if not dry_path.exists():
            median, spread = s1_rtc.median_of_passes([work / record["window_file"] for record in dry_records.values()])
            s1_rtc.write_window(dry_path, [median[0], median[1], spread[0], spread[1]], grid, epsg=EPSG, cell_m=CELL_M)
        cover_urls, dem_urls = context_urls(passes["bbox"])
        land_cover = np.zeros((rows, columns), dtype="uint8")
        for index, url in enumerate(cover_urls):
            part = t2.warp_remote(url, work, f"worldcover_{key}_{index}.tif", grid, nearest=True, dtype="uint8", fill=0)
            land_cover = np.where(land_cover == 0, part, land_cover)
        height = None
        for index, url in enumerate(dem_urls):
            part = t2.warp_remote(url, work, f"dem_{key}_{index}.tif", grid, nearest=False, dtype="float32", fill=-9999.0)
            part = np.where(part == -9999.0, np.nan, part)
            height = part if height is None else np.where(np.isfinite(height), height, part)
        slope = rc.slope_degrees(height, CELL_M, CELL_M)
        features = strip_baseline_features(work / after["window_file"], dry_path, slope, land_cover)
        permanent_water = land_cover == t2.PERMANENT_WATER_CLASS
        usable = rfc.usable_cells(features, rd.FEATURES_BASELINE) & ~permanent_water
        compared = usable & cells["compared"]
        frozen_flag, frozen_cut = apply_detector(bundle, features, usable, slope)
        threshold_flag, _cut = apply_detector(threshold, features, usable, slope)
        images = {}
        for role, record in (("before", before), ("after", after)):
            with rasterio.open(work / record["window_file"]) as source:
                images[role] = source.read().astype("float64")
        tiles = rc.lattice_tiles((west, north - rows * CELL_M, west + columns * CELL_M, north))
        candidates = dated.run_methods(images["before"], images["after"], tiles, grid, permanent_water, slope, configs)
        seen = rd.observable(land_cover)
        if entry.get("set_aside_from_the_test"):
            # Not a flood scene: no reference. What each detector flags on the cells the image shows is reported, nothing is scored.
            shown = usable & (cells["compared"] | cells["mixed"])
            cell_km2 = CELL_M * CELL_M / 1e6
            chips[key] = {
                "set_aside_from_the_test": entry["set_aside_from_the_test"],
                "sentinel1": {"relative_orbit": passes["relative_orbit"], "hours_after_the_image": passes["hours_after_the_image"]},
                "cells_the_image_shows": int(shown.sum()), "km2": round(int(shown.sum()) * cell_km2, 4),
                "flagged_km2": {"frozen_detector": round(int((frozen_flag & shown).sum()) * cell_km2, 4),
                                "simple_threshold": round(int((threshold_flag & shown).sum()) * cell_km2, 4),
                                **{name: round(int(((candidates[name] == 1) & shown).sum()) * cell_km2, 4) for name in RULES}},
            }
            print(key, "set aside:", chips[key]["flagged_km2"], flush=True)
            continue
        chips[key] = {
            "sentinel1": {"relative_orbit": passes["relative_orbit"], "hours_after_the_image": passes["hours_after_the_image"],
                          "after": after, "before_for_the_fixed_rules": before, "dry_season": dry_records},
            "compared_cells": int(compared.sum()), "reference_water_cells": int((compared & cells["wet"]).sum()),
            "cells_of_the_reference_left_out_for_a_missing_feature": int((cells["compared"] & ~permanent_water & ~usable).sum()),
            "frozen_detector": {**counts(frozen_flag, compared, cells["wet"]), "cut": frozen_cut},
            "simple_threshold": counts(threshold_flag, compared, cells["wet"]),
            "fixed_rules": {name: counts(candidates[name] == 1, compared, cells["wet"]) for name in RULES},
            "not_observable": {"cells": int((compared & ~seen).sum()), "reference_water_cells": int((compared & ~seen & cells["wet"]).sum()),
                               "frozen_detector_on_observable_cells_only": counts(frozen_flag, compared & seen, cells["wet"])},
        }
        pooled["wet"].append(cells["wet"][compared])
        pooled["frozen"].append(frozen_flag[compared])
        pooled["threshold"].append(threshold_flag[compared])
        for name in RULES:
            pooled[name].append((candidates[name] == 1)[compared])
        print(key, chips[key]["compared_cells"], chips[key]["frozen_detector"]["iou"], chips[key]["simple_threshold"]["iou"],
              {name: chips[key]["fixed_rules"][name]["iou"] for name in RULES}, flush=True)

    wet = np.concatenate(pooled["wet"])
    together = {"compared_cells": int(wet.size), "reference_water_cells": int(wet.sum()),
                "frozen_detector": rfc.flag_counts(np.concatenate(pooled["frozen"]), wet),
                "simple_threshold": rfc.flag_counts(np.concatenate(pooled["threshold"]), wet),
                "fixed_rules": {name: rfc.flag_counts(np.concatenate(pooled[name]), wet) for name in RULES}}
    said = rd.statement_for_the_test(together["frozen_detector"], together["simple_threshold"], together["fixed_rules"],
                                     frozen_is_the_threshold=bundle["base"] == STEP_THRESHOLD and not bundle["cleaned"])
    result = {
        "schema": "floodguard.radar_detection_held_out_test.v1",
        **envelope(),
        "what_this_is": "The one test of the frozen detector on the two held-out THEOS-2 chips, with the simple threshold and the three fixed rules on the same cells.",
        "label": "Agreement with water read from a THEOS-2 image; not accuracy.",
        "freeze_record": {"path": f"{OUTPUT_DIR}/freeze_v1.json", "sha256": t2.sha256_file(freeze_path)},
        "reference_record": {"path": f"{OUTPUT_DIR}/held_out_reference_v1.json", "sha256": t2.sha256_file(reference_path)},
        "frozen_detector": freeze["frozen_detector"],
        "pass_rule": "After: the first Sentinel-1 pass after the image. Before, for the fixed rules: the pass of the same orbit 12 days earlier. Dry season: the passes of the same orbit nearest to 25 February, 9 March and 14 April 2025.",
        "chips": chips,
        "held_out_chips_together": together,
        "what_the_plan_fixed": said,
        "assumptions": ASSUMPTIONS,
        "limits": [*LIMITS[1:], "One chip of about 7 square km is scored: a flooded town, where radar sees least. The other chip holds no flood and is not scored."],
    }
    result["supersedes"] = t2.superseded(result_path, arguments, ("held_out_chips_together",), result)
    t2.write_json(result_path, result)
    print(json.dumps({key: (value["iou"] if "iou" in value else {name: entry["iou"] for name, entry in value.items()})
                      for key, value in together.items() if isinstance(value, dict)}))
    print(said["what_is_said"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    stages = parser.add_subparsers(dest="stage", required=True)
    for name in ("baselines", "develop", "reference", "test"):
        stage = stages.add_parser(name)
        stage.add_argument("--external-root", required=True)
        stage.add_argument("--replace", action="store_true")
        stage.add_argument("--reason", default="")
        if name == "baselines":
            stage.add_argument("--only", default="", help="comma-separated area keys, to fetch some areas in a second process")
        if name == "reference":
            stage.add_argument("--theos2-dir", required=True, help="the folder that holds the two held-out THEOS-2 files")
    arguments = parser.parse_args()
    {"baselines": stage_baselines, "develop": stage_develop, "reference": stage_reference, "test": stage_test}[arguments.stage](arguments)


if __name__ == "__main__":
    main()
