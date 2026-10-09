"""A supervised radar flood classifier, trained on a dated agency layer and tested on a THEOS-2 tile (work package 7).

Three stages, in the order of the plan (``docs/proposal_execution/radar_flood_classifier_plan_v1.md``):

``features``
    Radar features and labels of the eight training districts, and the training sample. Mae Sai's labels and the
    Sukhothai tile are not touched.

``fit``
    Tunes the four models on spatial blocks inside the training districts, calibrates them, fixes the cut and
    writes the freeze record. The freeze record is committed before the next stage.

``test``
    Runs once: test A on Mae Sai district against the same agency layer, test B on the THEOS-2 tile at Sukhothai
    against the water read from the image, with the three fixed radar rules on the same cells.

The dated layer is held at the ``local`` level (decision log R33): rasters, feature tables and fitted models stay
in the work folder outside Git; the records in Git hold counts by district and for whole frames. Every figure is
agreement with a reference layer, not accuracy. No FPPS and no A-E class is computed, and nothing here is an
official warning.

Example::

    python scripts/build_radar_flood_classifier.py features --external-root <external-data-root>
    python scripts/build_radar_flood_classifier.py fit --external-root <external-data-root>
    python scripts/build_radar_flood_classifier.py test --external-root <external-data-root>
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
from floodguard import radar_flood_classifier as rfc  # noqa: E402
from floodguard import s1_rtc  # noqa: E402
from floodguard import theos2_cross_check as cc  # noqa: E402

PLAN = "docs/proposal_execution/radar_flood_classifier_plan_v1.md"
OUTPUT_DIR = "outputs/radar_flood_classifier"
FREEZE_NAME = "chiang_rai_20241022_freeze_v1.json"
RESULT_NAME = "chiang_rai_20241022_v1.json"
RECEIPT_NAME = "chiang_rai_20241022_v1_receipt.json"
WORK = Path("proposal_execution") / "radar_flood_classifier_v1"
DATED_WORK = Path("proposal_execution") / "dated_radar_check_v1"
SUKHOTHAI_WORK = Path("theos2_cross_check") / "sukhothai_20250730_v1"
SOURCE_TIMESTAMP = "2024-10-22 (training labels); THEOS-2 2025-07-30T03:33Z (independent test)"

TRAINING_DISTRICTS = {
    "TH5708": "Chiang Saen", "TH5707": "Mae Chan", "TH5714": "Khun Tan", "TH5712": "Phaya Mengrai",
    "TH5703": "Chiang Khong", "TH5718": "Doi Luang", "TH5717": "Wiang Chiang Rung", "TH5702": "Wiang Chai",
}
S1_BEFORE = ("S1A_IW_GRDH_1SDV_20240822T231600_20240822T231625_055332_06BF48_rtc",
             "S1A_IW_GRDH_1SDV_20240822T231625_20240822T231650_055332_06BF48_rtc")
S1_AFTER = ("S1A_IW_GRDH_1SDV_20241021T231602_20241021T231627_056207_06E178_rtc",
            "S1A_IW_GRDH_1SDV_20241021T231627_20241021T231652_056207_06E178_rtc")
STRIP_ROWS = 1024
HALO = rfc.WINDOW // 2
RULES = ("un_spider", "m1_literal", "m1_v2")

ASSUMPTIONS = [
    "Training labels are the layer UNOSAT and GISTDA dated 22 October 2024, as provided: a cell is water when its centre lies inside it.",
    "Where the agency mapped no water the cell counts as dry; the layer has no 'not observed' class.",
    "Every feature comes from the Sentinel-1 pair, or is slope or land cover. No feature says where water usually stands.",
    "Weights put the true share of water of the training districts back for calibration and for the out-of-fold figures.",
]
LIMITS = [
    "One date of training labels, late in the season: shallow residual water on fields, not the September flood.",
    "The agency layer was not checked in the field and may come from the same Sentinel-1 pass as the features.",
    "At Sukhothai the radar came 44 hours after the THEOS-2 image; no classifier can flag water the radar did not record.",
    "Every figure is agreement with a reference layer, not accuracy. The model feeds no component, no score and no class.",
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


dated = load_script("build_dated_radar_check")
t2 = dated.t2
BuildError = t2.BuildError
EPSG, CELL_M = dated.EPSG, dated.CELL_M


def envelope() -> dict[str, Any]:
    return {
        "generated_at_utc": t2.now_utc(),
        "source_timestamp": SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "A classifier fitted to one agency layer that was not checked in the field; one independent tile.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "plan": {"path": PLAN, "sha256": t2.sha256_file(ROOT / PLAN)},
    }


def fetch_mosaic(work: Path, grid: tuple[float, float, int, int], items: tuple[str, ...], name: str) -> dict[str, Any]:
    """The lattice window of one Sentinel-1 pass from its frames, first valid value first (VV, VH; linear gamma0).

    A later frame is read only when the frames before it left cells without a value.
    """

    west, north, rows, columns = grid
    bounds = (west, north - rows * CELL_M, west + columns * CELL_M, north)
    path, meta_path = work / f"{name}.tif", work / f"{name}.json"
    if not (path.exists() and meta_path.exists()):
        token = t2.fetch_json(t2.SAS)["token"]
        image = np.full((2, rows, columns), np.nan, dtype="float32")
        sources = []
        for item_id in items:
            if sources and np.isfinite(image).all():
                break
            item = t2.fetch_json(t2.STAC + item_id)
            sources.append({"item": item_id, "datetime": item["properties"]["datetime"]})
            for band, asset in enumerate(("vv", "vh")):
                block = s1_rtc.read_window_parallel(f"{item['assets'][asset]['href']}?{token}", grid, epsg=EPSG, cell_m=CELL_M)
                block[~(np.isfinite(block) & (block > 0))] = np.nan
                image[band] = np.where(np.isfinite(image[band]), image[band], block)
        dated.write_raster(path, [image[0], image[1]], grid, "float32", float("nan"))
        t2.write_json(meta_path, {"fetched_at_utc": t2.now_utc(), "sources": sources,
                                  "mosaic_rule": "first valid value in the listed order"})
    return {**json.loads(meta_path.read_text(encoding="utf-8")), "window_file": path.name, "window_sha256": t2.sha256_file(path)}


def strip_features(before_path: Path, after_path: Path, slope: np.ndarray, land_cover: np.ndarray) -> dict[str, np.ndarray]:
    """The features of a whole grid, computed in strips of rows with a halo so that memory stays small."""

    import rasterio
    from rasterio.windows import Window

    rows, columns = slope.shape
    features = {name: np.full((rows, columns), np.nan, dtype="float32") for name in rfc.FEATURES_ALL}
    with rasterio.open(before_path) as before, rasterio.open(after_path) as after:
        for start in range(0, rows, STRIP_ROWS):
            stop = min(rows, start + STRIP_ROWS)
            top, bottom = max(0, start - HALO), min(rows, stop + HALO)
            window = Window(0, top, columns, bottom - top)
            part = rfc.pair_features(before.read(window=window), after.read(window=window), slope[top:bottom], land_cover[top:bottom])
            for name, values in part.items():
                features[name][start:stop] = values[start - top:start - top + (stop - start)]
    return features


def district_geometry(external: Path, code: str) -> Any:
    import geopandas as gpd
    import shapely

    tambons = gpd.read_file(f"/vsizip/{(external / dated.BOUNDARIES).as_posix()}", layer="tha_admin3",
                            where=f"adm2_pcode = '{code}'").to_crs(EPSG)
    if tambons.empty:
        raise BuildError(f"no tambon of district {code} in the boundary file")
    return shapely.union_all(list(tambons.geometry))


def stage_features(arguments: argparse.Namespace) -> None:
    import geopandas as gpd
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    import shapely

    external = Path(arguments.external_root)
    work = external / WORK
    work.mkdir(parents=True, exist_ok=True)
    if (ROOT / OUTPUT_DIR / FREEZE_NAME).exists() and not arguments.replace:
        raise BuildError("the models are frozen; the features are not rebuilt without --replace and --reason")
    product = f"/vsizip/{(external / dated.PRODUCT_ZIP).as_posix()}/{dated.PRODUCT_GDB}"
    layer = shapely.union_all(list(gpd.read_file(product, layer=dated.DATED_LAYER).to_crs(EPSG).geometry.make_valid()))

    districts = []
    for code, name in TRAINING_DISTRICTS.items():
        started = time.time()
        geometry = district_geometry(external, code)
        _tiles, west, north, rows, columns = t2.lattice_grid(geometry.bounds)
        grid = (west, north, rows, columns)
        transform = from_origin(west, north, CELL_M, CELL_M)
        before = fetch_mosaic(work, grid, S1_BEFORE, f"s1_{code}_before")
        after = fetch_mosaic(work, grid, S1_AFTER, f"s1_{code}_after")
        land_cover = t2.warp_remote(dated.WORLDCOVER_URL, work, f"worldcover_{code}.tif", grid, nearest=True, dtype="uint8", fill=0)
        height = None
        for index, url in enumerate(dated.DEM_URLS):
            part = t2.warp_remote(url, work, f"dem_{code}_{index}.tif", grid, nearest=False, dtype="float32", fill=-9999.0)
            part = np.where(part == -9999.0, np.nan, part)
            height = part if height is None else np.where(np.isfinite(height), height, part)
        slope = rc.slope_degrees(height, CELL_M, CELL_M)
        features = strip_features(work / before["window_file"], work / after["window_file"], slope, land_cover)
        in_district = rasterize([(geometry, 1)], out_shape=(rows, columns), transform=transform, fill=0, dtype="uint8").astype(bool)
        clipped = shapely.intersection(layer, shapely.box(west, north - rows * CELL_M, west + columns * CELL_M, north))
        label = (rasterize([(clipped, 1)], out_shape=(rows, columns), transform=transform, fill=0, dtype="uint8").astype(bool)
                 if not clipped.is_empty else np.zeros((rows, columns), dtype=bool))
        frame = in_district & (land_cover != dated.PERMANENT_WATER_CLASS)
        usable = frame & rfc.usable_cells(features)
        row_index, column_index = np.nonzero(usable)
        np.save(work / f"cells_{code}_features.npy", np.column_stack([features[name][usable] for name in rfc.FEATURES_ALL]))
        np.save(work / f"cells_{code}_label.npy", label[usable])
        np.save(work / f"cells_{code}_xy.npy", np.column_stack([west + (column_index + 0.5) * CELL_M,
                                                               north - (row_index + 0.5) * CELL_M]).astype("float32"))
        districts.append({"adm2_pcode": code, "name": name, "frame_cells": int(frame.sum()), "usable_cells": int(usable.sum()),
                          "frame_cells_without_every_feature": int((frame & ~usable).sum()),
                          "water_cells": int(label[usable].sum()),
                          "water_share": round(float(label[usable].mean()), 6),
                          "sentinel1": {"before": before, "after": after}})
        print(f"{name}: {int(usable.sum())} cells, {int(label[usable].sum())} water, {time.time() - started:.0f} s", flush=True)

    labels = np.concatenate([np.load(work / f"cells_{code}_label.npy") for code in TRAINING_DISTRICTS])
    index, weight = rfc.draw_sample(labels)
    offsets = np.cumsum([0] + [entry["usable_cells"] for entry in districts])
    rows_x, rows_xy, rows_district = [], [], []
    for position, code in enumerate(TRAINING_DISTRICTS):
        chosen = index[(index >= offsets[position]) & (index < offsets[position + 1])] - offsets[position]
        rows_x.append(np.load(work / f"cells_{code}_features.npy", mmap_mode="r")[chosen])
        rows_xy.append(np.load(work / f"cells_{code}_xy.npy", mmap_mode="r")[chosen])
        rows_district.append(np.full(chosen.size, position, dtype="int16"))
        districts[position]["sample_cells"] = int(chosen.size)
        districts[position]["sample_water_cells"] = int(labels[offsets[position]:offsets[position + 1]][chosen].sum())
    np.savez_compressed(work / "training_sample.npz", features=np.concatenate(rows_x), label=labels[index], weight=weight,
                        xy=np.concatenate(rows_xy), district=np.concatenate(rows_district))
    t2.write_json(work / "features_record.json", {
        **envelope(), "districts": districts, "features": list(rfc.FEATURES_ALL),
        "cells": int(labels.size), "water_cells": int(labels.sum()), "water_share": round(float(labels.mean()), 6),
        "sample": {"cells": int(index.size), "water_cells": int(labels[index].sum()), "seed": rfc.SEED,
                   "sha256": t2.sha256_file(work / "training_sample.npz")},
        "test_labels_read": False,
    })
    print(json.dumps({"cells": int(labels.size), "water_cells": int(labels.sum()), "sample": int(index.size)}))


def weighted_scores(probability: np.ndarray, label: np.ndarray, weight: np.ndarray | None) -> dict[str, Any]:
    wet = np.asarray(label, dtype=bool)
    scale = np.ones(wet.size) if weight is None else weight
    brier = float(np.average((probability - wet) ** 2, weights=scale))
    return {**rfc.ranking(probability, wet, weight), "brier": round(brier, 6)}


def stage_fit(arguments: argparse.Namespace) -> None:
    import joblib

    external = Path(arguments.external_root)
    work = external / WORK
    freeze_path = ROOT / OUTPUT_DIR / FREEZE_NAME
    if freeze_path.exists() and not arguments.replace:
        raise BuildError(f"{freeze_path} exists; use --replace with --reason")
    if (ROOT / OUTPUT_DIR / RESULT_NAME).exists():
        raise BuildError("the test has been run; the models are not fitted again after it")
    record = json.loads((work / "features_record.json").read_text(encoding="utf-8"))
    if record["plan"]["sha256"] != t2.sha256_file(ROOT / PLAN):
        raise BuildError("the plan changed after the features were built")
    if t2.sha256_file(work / "training_sample.npz") != record["sample"]["sha256"]:
        raise BuildError("training_sample.npz is not the sample the features record binds")
    sample = np.load(work / "training_sample.npz")
    features, label, weight, xy = sample["features"].astype("float64"), sample["label"].astype(bool), sample["weight"], sample["xy"]
    folds = ml.block_folds(xy[:, 0].astype("float64"), xy[:, 1].astype("float64"))
    columns = {name: position for position, name in enumerate(rfc.FEATURES_ALL)}

    models: dict[str, Any] = {}
    for name, spec in rfc.MODELS.items():
        started = time.time()
        chosen = features[:, [columns[feature] for feature in spec["features"]]]
        trials, best = [], None
        for settings in spec["grid"]:
            raw = ml.out_of_fold(spec["kind"], settings, chosen, label, folds, seed=rfc.SEED)
            figures = weighted_scores(raw, label, weight)
            trials.append({"settings": settings, **figures})
            if best is None or figures["average_precision"] > best[0]:
                best = (figures["average_precision"], settings, raw)
        _score, settings, raw = best
        calibration = rfc.weighted_isotonic(raw, label, weight)
        calibrated = calibration.predict(raw)
        cut = rfc.best_cut(calibrated, label, weight)
        fitted = ml.make_model(spec["kind"], settings, seed=rfc.SEED).fit(chosen, label.astype("int64"))
        joblib.dump({"model": fitted, "calibration": calibration, "features": spec["features"], "cut": cut["cut"]},
                    work / f"model_{name}.joblib")
        models[name] = {
            "kind": spec["kind"], "features": list(spec["features"]), "settings": settings, "trials": trials,
            "out_of_fold_weighted": {**weighted_scores(calibrated, label, weight),
                                     "at_the_frozen_cut": rfc.flag_counts(calibrated >= cut["cut"], label, weight)},
            "frozen_cut": cut["cut"], "cut_trials": cut["trials"],
            "model_file_outside_git": {"name": f"model_{name}.joblib", "sha256": t2.sha256_file(work / f"model_{name}.joblib")},
        }
        print(f"{name}: settings {settings}, AP {models[name]['out_of_fold_weighted']['average_precision']}, cut {cut['cut']}, "
              f"IoU {cut['iou_out_of_fold']}, {time.time() - started:.0f} s", flush=True)

    freeze = {
        "schema": "floodguard.radar_flood_classifier_freeze.v1",
        **envelope(),
        "what_this_is": "The four models of the plan, tuned, fitted, calibrated and frozen on the eight training districts. "
                        "No test label has been read.",
        "rights_note": "The training labels come from a layer held at the local level (decision log R33). The sample, "
                       "the models and every raster stay outside Git; this record holds counts by district.",
        "training": {"districts": [{key: entry[key] for key in ("adm2_pcode", "name", "usable_cells", "water_cells", "water_share",
                                                                "sample_cells", "sample_water_cells")} for entry in record["districts"]],
                     "cells": record["cells"], "water_cells": record["water_cells"], "water_share": record["water_share"],
                     "sample": record["sample"],
                     "sentinel1": {"before": list(S1_BEFORE), "after": list(S1_AFTER)}},
        "tuning": {"folds": ml.FOLDS, "block_m": ml.BLOCK_M, "picked_by": "weighted average precision, out of fold",
                   "seed": rfc.SEED},
        "models": models,
        "primary_model": rfc.PRIMARY,
        "test_labels_read": False,
        "assumptions": ASSUMPTIONS,
        "limits": LIMITS,
    }
    freeze["supersedes"] = t2.superseded(freeze_path, arguments, ("models",), freeze)
    t2.write_json(freeze_path, freeze)


def predict_cells(work: Path, features: np.ndarray) -> dict[str, dict[str, Any]]:
    """Calibrated values and flags of the four frozen models for a table of cells (columns as FEATURES_ALL)."""

    import joblib

    columns = {name: position for position, name in enumerate(rfc.FEATURES_ALL)}
    result = {}
    for name in rfc.MODELS:
        bundle = joblib.load(work / f"model_{name}.joblib")
        chosen = features[:, [columns[feature] for feature in bundle["features"]]].astype("float64")
        probability = np.empty(chosen.shape[0], dtype="float64")
        for start in range(0, chosen.shape[0], 500_000):
            raw = bundle["model"].predict_proba(chosen[start:start + 500_000])[:, 1]
            probability[start:start + 500_000] = bundle["calibration"].predict(raw)
        result[name] = {"probability": probability, "flag": probability >= bundle["cut"], "bundle": bundle}
    return result


def permutation_drop(bundle: dict[str, Any], features: np.ndarray, label: np.ndarray, *, repeats: int = 3) -> dict[str, float]:
    """How much average precision falls when one feature is shuffled; mean of ``repeats`` shuffles."""

    from sklearn.metrics import average_precision_score

    columns = {name: position for position, name in enumerate(rfc.FEATURES_ALL)}
    chosen = features[:, [columns[feature] for feature in bundle["features"]]].astype("float64")
    base = average_precision_score(label, bundle["model"].predict_proba(chosen)[:, 1])
    rng = np.random.default_rng(rfc.SEED)
    drops = {}
    for position, feature in enumerate(bundle["features"]):
        falls = []
        for _ in range(repeats):
            shuffled = chosen.copy()
            shuffled[:, position] = rng.permutation(shuffled[:, position])
            falls.append(base - average_precision_score(label, bundle["model"].predict_proba(shuffled)[:, 1]))
        drops[feature] = round(float(np.mean(falls)), 6)
    return dict(sorted(drops.items(), key=lambda item: -item[1]))


def test_frame(work: Path, features: dict[str, np.ndarray], compared: np.ndarray, wet: np.ndarray,
               rules: dict[str, np.ndarray], land_cover: np.ndarray, *, calibration_figures: bool,
               importance: bool) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """The figures of one test frame for the four models and the three fixed rules, on the same cells."""

    table = np.column_stack([features[name][compared] for name in rfc.FEATURES_ALL])
    label = wet[compared]
    predicted = predict_cells(work, table)
    models: dict[str, Any] = {}
    for name, values in predicted.items():
        entry = {**rfc.ranking(values["probability"], label), "frozen_cut": values["bundle"]["cut"],
                 "at_the_frozen_cut": rfc.flag_counts(values["flag"], label)}
        if calibration_figures:
            entry["brier"] = round(float(np.mean((values["probability"] - label) ** 2)), 6)
            entry["expected_calibration_error"] = round(float(ml.expected_calibration_error(values["probability"], label)), 6)
        entry["by_land_cover_worldcover_2021"] = {}
        classes = land_cover[compared]
        taken = np.zeros(label.size, dtype=bool)
        for group, members in {**dated.LAND_COVER_GROUPS, "other": ()}.items():
            inside = ~taken if group == "other" else np.isin(classes, list(members))
            taken |= inside
            entry["by_land_cover_worldcover_2021"][group] = {"cells": int(inside.sum()), **rfc.flag_counts(values["flag"][inside], label[inside])}
        models[name] = entry
    primary = predicted[rfc.PRIMARY]
    models[rfc.PRIMARY]["values_between_0.3_and_0.7_withheld"] = rfc.withheld(primary["probability"], label)
    if importance:
        models[rfc.PRIMARY]["average_precision_lost_when_a_feature_is_shuffled"] = permutation_drop(primary["bundle"], table, label)
    fixed = {name: {"at_its_own_rule": rfc.flag_counts(candidate[compared] == 1, label),
                    "cells_without_an_answer": int((candidate[compared] == 255).sum())} for name, candidate in rules.items()}
    frame = {"compared_cells": int(compared.sum()), "reference_water_cells": int(label.sum()),
             "reference_water_share": round(float(label.mean()), 6), "models": models, "fixed_rules": fixed}
    return frame, {name: values["probability"] for name, values in predicted.items()}


def stage_test(arguments: argparse.Namespace) -> None:
    import rasterio

    external = Path(arguments.external_root)
    work = external / WORK
    freeze_path = ROOT / OUTPUT_DIR / FREEZE_NAME
    result_path = ROOT / OUTPUT_DIR / RESULT_NAME
    if not freeze_path.exists():
        raise BuildError("no freeze record: run the fit stage first and commit it")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze["plan"]["sha256"] != t2.sha256_file(ROOT / PLAN):
        raise BuildError("the plan changed after the models were frozen")
    for name, entry in freeze["models"].items():
        if t2.sha256_file(work / entry["model_file_outside_git"]["name"]) != entry["model_file_outside_git"]["sha256"]:
            raise BuildError(f"the model file of {name} is not the one the freeze record binds")
    if result_path.exists() and not arguments.replace:
        raise BuildError(f"{result_path} exists; the test is run once (plan section 6)")

    # --- test A: Mae Sai district against the same agency layer ---------------------------------------------
    mae_sai = external / DATED_WORK
    reference_record = json.loads((ROOT / dated.OUTPUT_DIR / dated.REFERENCE_NAME).read_text(encoding="utf-8"))
    if t2.sha256_file(mae_sai / "dated_reference_10m.tif") != reference_record["rasters_outside_git"]["dated_reference_10m.tif"]["sha256"]:
        raise BuildError("the Mae Sai reference raster is not the one work package 3 recorded")
    grid_record = reference_record["grid_10m"]
    grid = (float(grid_record["west"]), float(grid_record["north"]), int(grid_record["rows"]), int(grid_record["columns"]))
    west, north, rows, columns = grid
    with rasterio.open(mae_sai / "dated_reference_10m.tif") as source:
        reference, in_district, permanent_water = (source.read(band).astype(bool) for band in (1, 2, 3))
    land_cover, slope = dated.context_rasters(mae_sai, grid)
    features = strip_features(mae_sai / "s1_before_primary_gamma0.tif", mae_sai / "s1_post_gamma0.tif", slope, land_cover)
    compared = in_district & ~permanent_water & rfc.usable_cells(features)
    images = {}
    for role in ("before_primary", "post"):
        with rasterio.open(mae_sai / f"s1_{role}_gamma0.tif") as source:
            images[role] = source.read().astype("float64")
    from floodguard import geoid_m1_review as review
    from floodguard import sar_change_v2 as sar

    binding = review.require_frozen_m1_v2(ROOT)
    configs = {"un_spider": rc.UnSpiderConfig(), "m1_literal": sar.M1LiteralConfig(),
               "m1_v2": sar.m1_v2_config_from_json(binding["parameters"])}
    tiles = rc.lattice_tiles((west, north - rows * CELL_M, west + columns * CELL_M, north))
    rules = dated.run_methods(images["before_primary"], images["post"], tiles, grid, permanent_water, slope, configs)
    test_a, values_a = test_frame(work, features, compared, reference, rules, land_cover, calibration_figures=True, importance=False)
    probability = np.full((rows, columns), np.nan, dtype="float32")
    probability[compared] = values_a[rfc.PRIMARY]
    dated.write_raster(work / "mae_sai_primary_model_value.tif", [probability], grid, "float32", float("nan"))
    del images, features

    # --- test B: the THEOS-2 tile at Sukhothai against the water read from the image -----------------------
    tile = external / SUKHOTHAI_WORK
    theos2_record = json.loads((ROOT / t2.OUTPUT_DIR / t2.REFERENCE_NAME).read_text(encoding="utf-8"))
    for name, entry in theos2_record["rasters_outside_git"].items():
        if t2.sha256_file(tile / name) != entry["sha256"]:
            raise BuildError(f"{name} is not the raster the THEOS-2 reference record binds")
    with rasterio.open(tile / "theos2_reference_10m.tif") as source:
        cells = cc.reference_cells(source.read(1), source.read(2))
    with rasterio.open(tile / "worldcover_10m.tif") as source:
        land_cover_b = source.read(1)
    height = None
    for index in range(len(t2.DEM_URLS)):
        with rasterio.open(tile / f"dem_{index}_10m.tif") as source:
            part = source.read(1)
        part = np.where(part == -9999.0, np.nan, part)
        height = part if height is None else np.where(np.isfinite(height), height, part)
    slope_b = rc.slope_degrees(height, CELL_M, CELL_M)
    features_b = strip_features(tile / "s1_pre_gamma0.tif", tile / "s1_post_gamma0.tif", slope_b, land_cover_b)
    compared_b = cells["compared"] & (land_cover_b != t2.PERMANENT_WATER_CLASS) & rfc.usable_cells(features_b)
    rules_b = {}
    for name in RULES:
        with rasterio.open(tile / f"candidate_{name}.tif") as source:
            rules_b[name] = source.read(1)
    test_b, _values_b = test_frame(work, features_b, compared_b, cells["wet"], rules_b, land_cover_b,
                                   calibration_figures=False, importance=True)
    test_b["cells_compared_in_the_cross_check_and_left_out_here"] = int(
        (cells["compared"] & (land_cover_b != t2.PERMANENT_WATER_CLASS) & ~compared_b).sum())

    said = rfc.statement({name: entry["at_the_frozen_cut"]["iou"] for name, entry in test_b["models"].items()},
                         {name: entry["at_its_own_rule"]["iou"] for name, entry in test_b["fixed_rules"].items()})
    result = {
        "schema": "floodguard.radar_flood_classifier.v1",
        **envelope(),
        "what_this_is": "A supervised radar flood classifier trained on the agency layer of 22 October 2024 in eight "
                        "districts, tested once on Mae Sai district (the same layer) and on the THEOS-2 tile at Sukhothai.",
        "label": "Agreement with a reference layer; not accuracy.",
        "rights_note": "The dated layer is held at the local level (decision log R33): rasters, feature tables and "
                       "models stay outside Git; this record holds figures for whole frames.",
        "freeze_record": {"path": f"{OUTPUT_DIR}/{FREEZE_NAME}", "sha256": t2.sha256_file(freeze_path)},
        "primary_model": rfc.PRIMARY,
        "test_a_mae_sai_agency_layer": {
            "reference": "UNOSAT and GISTDA layer dated 22 October 2024; may come from the same radar pass",
            "radar_pair": {"before": dated.S1_BEFORE["primary"], "after": dated.S1_POST}, **test_a},
        "test_b_sukhothai_theos2": {
            "reference": "water read from the THEOS-2 image of 30 July 2025 03:33 UTC (committed reference of the cross-check)",
            "radar_pair": {"before": list(t2.S1_PRE), "after": list(t2.S1_POST)}, **test_b},
        "what_the_plan_fixed": said,
        "assumptions": ASSUMPTIONS,
        "limits": LIMITS,
    }
    result["supersedes"] = t2.superseded(result_path, arguments, ("test_a_mae_sai_agency_layer", "test_b_sukhothai_theos2"), result)
    t2.write_json(result_path, result)
    t2.write_json(ROOT / OUTPUT_DIR / RECEIPT_NAME, {
        "schema": "floodguard.radar_flood_classifier_receipt.v1",
        **envelope(),
        "inputs": {"freeze_record": result["freeze_record"],
                   "mae_sai_reference_record": {"path": f"{dated.OUTPUT_DIR}/{dated.REFERENCE_NAME}",
                                                "sha256": t2.sha256_file(ROOT / dated.OUTPUT_DIR / dated.REFERENCE_NAME)},
                   "theos2_reference_record": {"path": f"{t2.OUTPUT_DIR}/{t2.REFERENCE_NAME}",
                                               "sha256": t2.sha256_file(ROOT / t2.OUTPUT_DIR / t2.REFERENCE_NAME)}},
        "outputs": {f"{OUTPUT_DIR}/{RESULT_NAME}": {"sha256": t2.sha256_file(result_path)},
                    "outside_git": {"mae_sai_primary_model_value.tif": {"sha256": t2.sha256_file(work / "mae_sai_primary_model_value.tif")}}},
        "code": {name: t2.sha256_file(ROOT / name) for name in (
            "scripts/build_radar_flood_classifier.py", "src/floodguard/radar_flood_classifier.py",
            "src/floodguard/flood_susceptibility_ml.py")},
    })
    for label_text, frame in (("A", test_a), ("B", test_b)):
        for name, entry in frame["models"].items():
            print(label_text, name, entry["roc_auc"], entry["average_precision"], entry["at_the_frozen_cut"])
        for name, entry in frame["fixed_rules"].items():
            print(label_text, name, entry["at_its_own_rule"])
    print(said["what_is_said"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    stages = parser.add_subparsers(dest="stage", required=True)
    for name, text in (("features", "features, labels and the sample of the training districts"),
                       ("fit", "tune, fit, calibrate and freeze the four models"),
                       ("test", "run the two tests once")):
        stage = stages.add_parser(name, help=text)
        stage.add_argument("--external-root", required=True)
        stage.add_argument("--replace", action="store_true")
        stage.add_argument("--reason", default="")
    arguments = parser.parse_args()
    {"features": stage_features, "fit": stage_fit, "test": stage_test}[arguments.stage](arguments)


if __name__ == "__main__":
    main()
