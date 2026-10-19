"""The radar readings of the study event against a dated THEOS-2 image of it, in three stages.

Plan: ``docs/proposal_execution/theos2_study_event_check_plan_v1.md``. The order is the point of it:

``radar``
    Run now, before GISTDA delivers any image of September 2024. Six readings of the Sentinel-1 pass of
    15 September 2024 over Mae Sai district are written on the 10 m lattice, outside Git, and a freeze record with
    their SHA-256 is committed. Nothing of them can be changed after an image is seen without the record showing it.
``reference``
    Run when a scene arrives. By amendment 1 the water of the image is read by rule v2, with rule v1 beside it, with
    no setting made by eye; each delivered product is read at 2 m and laid on one grid (the delivery record), then on
    the lattice, and looked at beside the image. No radar reading is opened.
``compare``
    Run once per scene, after the reference record is committed: the frozen readings against the water of the
    image, the sentences the plan fixed, and what the image shows of the roads of the Ko Chang road sheet.

Report-only. An agreement with one optical image is not a check on the ground. The THEOS-2 imagery stays outside
Git. Nothing here is an official warning or an input of the planning score.

Examples::

    python scripts/build_theos2_study_event_check.py radar --external-root <external data root>
    python scripts/build_theos2_study_event_check.py reference --external-root <root> --scene-key 20240917 \\
        --looked-at "<what the look showed>"
    python scripts/build_theos2_study_event_check.py compare --external-root <root> --scene-key 20240917
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import theos2_study_event as study  # noqa: E402

PLAN = "docs/proposal_execution/theos2_study_event_check_plan_v1.md"
OUTPUT_DIR = "outputs/theos2_study_event_check"
FREEZE_NAME = "radar_freeze_v1.json"
WORK = Path("proposal_execution") / "theos2_study_event_check_v1"
READINGS_RASTER = "radar_readings_mae_sai_20240915.tif"
AMENDMENT = "docs/proposal_execution/theos2_study_event_check_plan_v1_amendment_1.md"
DELIVERY = "outputs/theos2_delivery/delivery_20240917_v1.json"
RULES = ("rule_v2", "rule_v1")
STRIP_ROWS_2M = 256
PASS_AFTER_UTC = "2024-09-15T23:16:14Z"
MAX_DAYS_BEFORE = 36
ROAD_SHEET = "outputs/ko_chang_road_check/ko_chang_roads_se1_v1.json"
SOURCE_TIMESTAMP = "Sentinel-1 2024-09-15T23:16:14Z; image before: the last pass of the same orbit the source holds; dry-season passes of 24 February, 7 March and 12 April 2024"
ASSUMPTIONS = [
    "The radar readings are those of one Sentinel-1 pass, four to five days after the peak of the flood at Mae Sai.",
    "The water of a THEOS-2 image is read by rule v2 (amendment 1), with rule v1 beside it, with no setting made by eye; it is not a check on the ground.",
    "Cells of permanent water and cells outside the district are left out of every count.",
]
LIMITS = [
    "One optical image, hours after the radar pass: water that came or went in between counts against the radar.",
    "Radar cannot see water under roofs and trees; the counts by stratum say how much of the compared ground that is.",
    "Report-only. No published class changes and nothing enters a planning score.",
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


improve = load_script("build_radar_detection_improvement")
dated, t2, rc, rd, rfc, s1_rtc, cc = improve.dated, improve.t2, improve.rc, improve.rd, improve.rfc, improve.s1_rtc, improve.cc
EPSG, CELL_M = improve.EPSG, improve.CELL_M
CELL_KM2 = CELL_M * CELL_M / 1e6


class BuildError(RuntimeError):
    """A stage cannot run, or it would run out of the order the plan fixed."""


def envelope() -> dict[str, Any]:
    return {"generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source_timestamp": SOURCE_TIMESTAMP,
            "confidence_class": "low",
            "confidence_basis": "Sentinel-1 backscatter read by fixed rules and one frozen detector; no reading was checked on the ground.",
            "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
            "plan": {"path": PLAN, "sha256": t2.sha256_file(ROOT / PLAN)}}


def mae_sai(external: Path) -> dict[str, Any]:
    """The lattice of Mae Sai district with its slope, land cover, district mask and permanent water, as the earlier stages cached them."""

    import rasterio

    area = improve.area_grids(external)["mae_sai"]
    folder = area["folder"]
    with rasterio.open(folder / "worldcover_10m.tif") as source:
        land_cover = source.read(1)
    slope = improve.read_slope(folder, [f"dem_{index}_10m.tif" for index in range(len(dated.DEM_URLS))])
    with rasterio.open(folder / "dated_reference_10m.tif") as source:
        in_district, permanent_water = source.read(2).astype(bool), source.read(3).astype(bool)
    return {"grid": area["grid"], "land_cover": land_cover, "slope": slope, "in_district": in_district, "permanent_water": permanent_water}


def pass_before(grid: tuple[float, float, int, int]) -> list[dict[str, Any]]:
    """The last pass of the same orbit before the pass of 15 September 2024 that the radar source holds (plan section 3)."""

    from pyproj import Transformer

    west, north, rows, columns = grid
    to_lonlat = Transformer.from_crs(EPSG, 4326, always_xy=True).transform
    corners = [to_lonlat(x, y) for x in (west, west + columns * CELL_M) for y in (north, north - rows * CELL_M)]
    bbox = [min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners)]
    after = datetime.strptime(PASS_AFTER_UTC, "%Y-%m-%dT%H:%M:%SZ")
    orbit = next((entry["relative_orbit"] for entry in s1_rtc.search_passes(
        bbox, (after - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), (after + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))), None)
    if orbit is None:
        raise BuildError("the catalogue does not list the pass of 15 September 2024 over the district")
    found = s1_rtc.search_passes(bbox, (after - timedelta(days=MAX_DAYS_BEFORE)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 (after - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), relative_orbit=orbit)
    if not found:
        raise BuildError(f"the source holds no pass of the same orbit in the {MAX_DAYS_BEFORE} days before 15 September 2024")
    last = max(found, key=lambda entry: entry["datetime"])
    return [entry for entry in found if abs((datetime.strptime(entry["datetime"][:19], "%Y-%m-%dT%H:%M:%S")
                                              - datetime.strptime(last["datetime"][:19], "%Y-%m-%dT%H:%M:%S")).total_seconds()) < 300]


def stage_radar(arguments: argparse.Namespace) -> None:
    import joblib
    import rasterio
    from rasterio.transform import from_origin

    from floodguard import geoid_m1_review as review
    from floodguard import sar_change_v2 as sar

    external = Path(arguments.external_root)
    record_path = ROOT / OUTPUT_DIR / FREEZE_NAME
    if record_path.exists():
        raise BuildError("the radar readings are frozen; they are not written a second time")
    if any((ROOT / OUTPUT_DIR).glob("reference_*.json")):
        raise BuildError("a reference record exists; the radar readings are frozen before any image is read")
    work, source_work = external / WORK, external / improve.WORK
    work.mkdir(parents=True, exist_ok=True)
    freeze = json.loads((ROOT / improve.OUTPUT_DIR / "freeze_v1.json").read_text(encoding="utf-8"))
    if t2.sha256_file(source_work / "frozen_detector.joblib") != freeze["frozen_detector"]["file_outside_git"]["sha256"]:
        raise BuildError("frozen_detector.joblib is not the detector the freeze record of decision log R37 binds")
    bundle = joblib.load(source_work / "frozen_detector.joblib")
    area = mae_sai(external)
    grid, slope, land_cover, permanent_water = area["grid"], area["slope"], area["land_cover"], area["permanent_water"]
    west, north, rows, columns = grid
    after_path, dry_path = source_work / "s1_mae_sai_20240915.tif", source_work / "dry_mae_sai.tif"

    features = improve.strip_baseline_features(after_path, dry_path, slope, land_cover)
    usable = rfc.usable_cells(features, rd.FEATURES_BASELINE) & ~permanent_water
    readings: dict[str, np.ndarray] = {}
    flag, _cut = improve.apply_detector(bundle, features, usable, slope)
    readings["frozen_detector"] = np.where(usable, flag.astype("uint8"), 255).astype("uint8")
    flag, _cut = improve.apply_detector({"base": improve.STEP_THRESHOLD, "cleaned": False, "threshold_db": bundle["threshold_db"]},
                                        features, usable, slope)
    readings["simple_threshold"] = np.where(usable, flag.astype("uint8"), 255).astype("uint8")
    del features
    with rasterio.open(after_path) as source:
        after = source.read().astype("float64")
    with rasterio.open(dry_path) as source:
        dry_vh = np.power(10.0, source.read(2).astype("float64") / 10.0)
    candidate, _, _, _ = rc.un_spider_candidate(dry_vh, after[1], in_frame=np.ones(after[1].shape, dtype=bool),
                                                permanent_water=permanent_water, slope=slope, cell_m=CELL_M)
    readings["un_spider_dry_baseline"] = candidate.astype("uint8")

    passes = pass_before(grid)
    before_record = s1_rtc.fetch_pass(work, grid, [item["item"] for item in passes], "s1_mae_sai_last_pass_before", epsg=EPSG, cell_m=CELL_M)
    with rasterio.open(work / before_record["window_file"]) as source:
        before = source.read().astype("float64")
    binding = review.require_frozen_m1_v2(ROOT)
    configs = {"un_spider": rc.UnSpiderConfig(), "m1_literal": sar.M1LiteralConfig(), "m1_v2": sar.m1_v2_config_from_json(binding["parameters"])}
    tiles = rc.lattice_tiles((west, north - rows * CELL_M, west + columns * CELL_M, north))
    candidates = dated.run_methods(before, after, tiles, grid, permanent_water, slope, configs)
    for name in ("un_spider", "m1_literal", "m1_v2"):
        readings[f"{name}_last_pass_before"] = candidates[name].astype("uint8")

    raster = work / READINGS_RASTER
    with rasterio.open(raster, "w", driver="GTiff", height=rows, width=columns, count=len(study.READINGS), dtype="uint8", nodata=255,
                       crs=f"EPSG:{EPSG}", transform=from_origin(west, north, CELL_M, CELL_M), compress="deflate") as target:
        for band, name in enumerate(study.READINGS, start=1):
            target.write(readings[name], band)
            target.set_band_description(band, name)
    inside = area["in_district"] & ~permanent_water
    record = {
        "schema": "floodguard.theos2_study_event_radar_freeze.v1",
        **envelope(),
        "what_this_is": "The radar readings of the Sentinel-1 pass of 15 September 2024 over Mae Sai district, frozen before any THEOS-2 image of September 2024 was received.",
        "no_image_of_the_event_was_read": True,
        "readings": {name: {
            "band": band,
            "flagged_km2_in_the_district": round(int(((readings[name] == 1) & inside).sum()) * CELL_KM2, 3),
            "cells_without_an_answer_in_the_district": int(((readings[name] == 255) & inside).sum()),
        } for band, name in enumerate(study.READINGS, start=1)},
        "what_each_reading_is": {
            "frozen_detector": "the detector frozen in decision log R37: VH after at or below the frozen threshold, cleaned (slope, group size, growth)",
            "simple_threshold": "VH after at or below the frozen threshold, not cleaned",
            "un_spider_dry_baseline": "the UN-SPIDER quotient rule with the median of three dry-season passes as its image before",
            "un_spider_last_pass_before": "the UN-SPIDER quotient rule with the last pass of the same orbit before the event as its image before",
            "m1_literal_last_pass_before": "rule M1-literal with the same image before",
            "m1_v2_last_pass_before": "the frozen rule M1-v2 with the same image before",
        },
        "sentinel1": {"after": PASS_AFTER_UTC, "last_pass_before": [{"item": item["item"], "datetime": item["datetime"]} for item in passes],
                      "relative_orbit": passes[0]["relative_orbit"]},
        "frozen_detector": {"freeze_record": f"{improve.OUTPUT_DIR}/freeze_v1.json",
                            "sha256": t2.sha256_file(ROOT / improve.OUTPUT_DIR / "freeze_v1.json")},
        "grid_10m": {"epsg": EPSG, "west": west, "north": north, "rows": rows, "columns": columns, "cell_m": CELL_M},
        "district_km2_outside_permanent_water": round(int(inside.sum()) * CELL_KM2, 3),
        "raster_outside_git": {"name": READINGS_RASTER, "sha256": t2.sha256_file(raster), "values": "1 flagged, 0 not flagged, 255 no answer"},
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    t2.write_json(record_path, record)
    print(json.dumps(record["readings"], indent=1))


def read_product_2m(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """One delivered product at 2 m, the mean of 4 by 4 pixels of 0.5 m, read in strips; with its valid pixels."""

    import rasterio
    from rasterio.windows import Window

    with rasterio.open(path) as source:
        if source.crs is None or source.crs.to_epsg() != EPSG or abs(source.res[0] - 0.5) > 1e-9 or source.count != 4:
            raise BuildError("the THEOS-2 product is not the four-band 0.5 m EPSG:32647 ortho the plan names")
        rows, columns = source.height // study.BLOCK, source.width // study.BLOCK
        image = np.zeros((4, rows, columns), dtype="float32")
        valid = np.zeros((rows, columns), dtype=bool)
        for first in range(0, rows, STRIP_ROWS_2M):
            last = min(rows, first + STRIP_ROWS_2M)
            block = source.read(window=Window(0, first * study.BLOCK, columns * study.BLOCK, (last - first) * study.BLOCK))
            image[:, first:last], valid[first:last] = study.block_mean(block)
    return image, valid


def stage_reference(arguments: argparse.Namespace) -> None:
    """Amendment 1: rule v2 is the reference, rule v1 is read beside it; each product is read, then laid on one 2 m grid."""

    import rasterio
    from rasterio.transform import from_origin

    from floodguard import theos2_water_rule_v2 as v2

    external = Path(arguments.external_root)
    work = external / WORK
    freeze_path = ROOT / OUTPUT_DIR / FREEZE_NAME
    record_path = ROOT / OUTPUT_DIR / f"reference_{arguments.scene_key}_v1.json"
    if not freeze_path.exists():
        raise BuildError("no radar freeze record: the radar readings are frozen and committed before an image is read")
    if record_path.exists() or (ROOT / OUTPUT_DIR / f"comparison_{arguments.scene_key}_v1.json").exists():
        raise BuildError("this scene has a reference record; a reference is built once and not after its comparison")
    draft_path = work / f"reference_{arguments.scene_key}_draft.json"
    if arguments.looked_at.strip():
        finish_reference(arguments, work, draft_path, record_path)
        return
    if draft_path.exists():
        raise BuildError(f"{draft_path.name} exists: look at its pictures and run again with --looked-at; the rasters are not computed twice")
    delivery_path = ROOT / arguments.delivery
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    folder = external / delivery["work_folder_outside_git"]
    grid = delivery["one_pixel_grid"]
    products = sorted(delivery["products"], key=lambda product: product["product"])
    for product in products:
        if t2.sha256_file(folder / product["image"]["path"]) != product["image"]["sha256"]:
            raise BuildError(f"{product['image']['path']} is not the file the delivery record binds")
    acquired = products[0]["metadata"]["acquired_utc"]

    mosaics = {name: np.full((grid["rows"], grid["columns"]), cc.WATER_UNOBSERVABLE, dtype="uint8") for name in RULES}
    covered = {name: np.zeros((grid["rows"], grid["columns"]), dtype=bool) for name in RULES}
    step = max(1, -(-max(grid["rows"], grid["columns"]) // 3000))
    look = np.zeros((-(-grid["rows"] // step), -(-grid["columns"] // step), 3), dtype="float32")
    look_seen = np.zeros(look.shape[:2], dtype=bool)
    per_product = []
    for product in products:
        image, valid = read_product_2m(folder / product["image"]["path"])
        red, green, blue, nir = (image[t2.THEOS2_BANDS[band] - 1] for band in ("red", "green", "blue", "nir"))
        answers = {"rule_v2": v2.water_v2(red, green, blue, nir, valid), "rule_v1": cc.optical_water(red, green, blue, nir, valid, cc.OpticalWaterConfig())}
        row = int(round((grid["north"] - product["header"]["transform"][5]) / grid["cell_m"]))
        column = int(round((product["header"]["transform"][2] - grid["west"]) / grid["cell_m"]))
        summary = {"product": product["product"], "order": product["order"], "valid_pixels_2m": int(valid.sum()),
                   "red_percentile_99": float(np.percentile(red[valid], 99)) if valid.any() else None}
        for name, (water, rule_summary) in answers.items():
            summary[name] = {**rule_summary, "pixels_that_disagree_with_an_earlier_product": study.place_first_valid(
                mosaics[name], covered[name], water, valid, row, column)}
        # The picture to look at: every step-th pixel of the true colour, the first product kept where they overlap.
        r0, c0 = -(-row // step) * step - row, -(-column // step) * step - column
        sub_valid = valid[r0::step, c0::step]
        lr, lc = (row + r0) // step, (column + c0) // step
        target = look[lr:lr + sub_valid.shape[0], lc:lc + sub_valid.shape[1]]
        fresh = sub_valid & ~look_seen[lr:lr + sub_valid.shape[0], lc:lc + sub_valid.shape[1]]
        target[fresh] = np.stack([red[r0::step, c0::step], green[r0::step, c0::step], blue[r0::step, c0::step]], axis=-1)[fresh]
        look_seen[lr:lr + sub_valid.shape[0], lc:lc + sub_valid.shape[1]] |= fresh
        per_product.append(summary)
        del image, red, green, blue, nir, answers

    area = mae_sai(external)
    grid_west, grid_north, rows, columns = area["grid"]
    inside = area["in_district"] & ~area["permanent_water"]
    profile = {"driver": "GTiff", "crs": f"EPSG:{EPSG}", "compress": "deflate"}
    raster = work / f"reference_{arguments.scene_key}_10m.tif"
    cells_by_rule: dict[str, Any] = {}
    with rasterio.open(raster, "w", height=rows, width=columns, count=2 * len(RULES), dtype="float32", nodata=float("nan"),
                       transform=from_origin(grid_west, grid_north, CELL_M, CELL_M), **profile) as target:
        for index, name in enumerate(RULES):
            water_share, observable_share = t2.aggregate_to_grid(mosaics[name], grid["west"], grid["north"], grid_west, grid_north, rows, columns)
            target.write(water_share, 2 * index + 1)
            target.write(observable_share, 2 * index + 2)
            target.set_band_description(2 * index + 1, f"{name} water share")
            target.set_band_description(2 * index + 2, f"{name} observable share")
            cells = cc.reference_cells(water_share, observable_share)
            cells_by_rule[name] = {"compared": int((cells["compared"] & inside).sum()), "wet": int((cells["wet"] & inside).sum()),
                                   "compared_km2": round(int((cells["compared"] & inside).sum()) * CELL_KM2, 3),
                                   "wet_km2": round(int((cells["wet"] & inside).sum()) * CELL_KM2, 3)}
    fine = {name: work / f"reference_{arguments.scene_key}_water_2m{'' if name == 'rule_v2' else '_' + name}.tif" for name in RULES}
    for name, path in fine.items():
        with rasterio.open(path, "w", height=grid["rows"], width=grid["columns"], count=1, dtype="uint8", nodata=255,
                           transform=from_origin(grid["west"], grid["north"], t2.FINE_M, t2.FINE_M), **profile) as target:
            target.write(mosaics[name], 1)
    from PIL import Image

    scale = max(max(item["red_percentile_99"] or 1.0 for item in per_product), 1.0)
    picture = np.clip(look / scale * 255, 0, 255).astype("uint8")
    for name in RULES:
        marked = picture.copy()
        sub = mosaics[name][::step, ::step][:picture.shape[0], :picture.shape[1]]
        marked[sub == cc.WATER_YES] = (40, 130, 235)
        marked[(sub == cc.WATER_UNOBSERVABLE) & look_seen] = (200, 80, 200)
        Image.fromarray(np.concatenate([picture, marked], axis=1)).save(work / f"reference_{arguments.scene_key}_look_{name}.png", optimize=True)
    record = {
        "schema": "floodguard.theos2_study_event_reference.v2",
        **envelope(),
        "source_timestamp": f"THEOS-2 {acquired}",
        "what_this_is": "The water of the THEOS-2 image of the study event, read from the image alone on the lattice of the district by rule v2 (amendment 1) with rule v1 beside it. No radar reading was opened.",
        "radar_read": False,
        "radar_freeze": {"path": f"{OUTPUT_DIR}/{FREEZE_NAME}", "sha256": t2.sha256_file(freeze_path)},
        "amendment": {"path": AMENDMENT, "sha256": t2.sha256_file(ROOT / AMENDMENT)},
        "delivery": {"path": arguments.delivery, "sha256": t2.sha256_file(delivery_path)},
        "scene": {"key": arguments.scene_key, "acquired_utc": acquired,
                  "products": [{"product": product["product"], "image_sha256": product["image"]["sha256"]} for product in products]},
        "reference_rule": "rule_v2",
        "rules": {"rule_v2": "Near infrared at or below red (red-NIR index at or below -0.01), cloud set aside (floodguard.theos2_water_rule_v2, frozen on 11 October 2026).",
                  "rule_v1": "NDWI above the upper threshold of a three-class Otsu split computed on each delivered product; bright objects unobservable; water objects under 1,000 square metres dropped."},
        "products_read": per_product,
        "grid_2m": grid,
        "cells_10m_in_the_district": cells_by_rule,
        "looked_at": None,
        "set_aside_from_the_comparison": None,
        "rule_v1_left_out": None,
        "rasters_outside_git": [{"name": path.name, "sha256": t2.sha256_file(path)} for path in (raster, *fine.values())],
        "pictures_looked_at_outside_git": [f"reference_{arguments.scene_key}_look_{name}.png" for name in RULES],
        "licence": "THEOS-2 imagery provided by GISTDA for GeoHackathon 2026. The imagery stays outside Git; derived figures are shared.",
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    t2.write_json(draft_path, record)
    print(json.dumps(record["cells_10m_in_the_district"]), flush=True)
    print(f"Look at {', '.join(record['pictures_looked_at_outside_git'])} beside the image, then run again with --looked-at.", flush=True)


def finish_reference(arguments: argparse.Namespace, work: Path, draft_path: Path, record_path: Path) -> None:
    """The second run of the reference stage: the look written into the draft, which becomes the record. Nothing is recomputed."""

    if not draft_path.exists():
        raise BuildError("no draft: run the reference stage without --looked-at first, then look at its pictures")
    record = json.loads(draft_path.read_text(encoding="utf-8"))
    for item in record["rasters_outside_git"]:
        if t2.sha256_file(work / item["name"]) != item["sha256"]:
            raise BuildError(f"{item['name']} changed after the draft was written")
    if record["amendment"]["sha256"] != t2.sha256_file(ROOT / AMENDMENT) or record["delivery"]["sha256"] != t2.sha256_file(ROOT / record["delivery"]["path"]):
        raise BuildError("the amendment or the delivery record changed after the draft was written")
    record.update({"looked_at": arguments.looked_at, "set_aside_from_the_comparison": arguments.set_aside or None,
                   "rule_v1_left_out": arguments.rule_v1_left_out or None,
                   "look_written_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    t2.write_json(record_path, record)
    print(json.dumps(record["cells_10m_in_the_district"]), flush=True)


def road_pieces(external: Path, water_path: Path) -> dict[str, Any]:
    """What the 2 m water raster of an image shows of every piece of the roads the Ko Chang road sheet names."""

    import rasterio
    from pyproj import Transformer

    sheet = json.loads((ROOT / ROAD_SHEET).read_text(encoding="utf-8"))
    ways = [str(step["osm_way_id"]) for step in sheet["what_if_roads_stay_passable_one_after_another"]["steps"]]
    bad = load_script("build_access_diff")
    v1b = json.loads((bad.DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    context, _record = bad.load_vehicle_context(v1b, external, bad.OUTPUT_DIR, ROOT)
    to_metres = Transformer.from_crs(4326, EPSG, always_xy=True).transform
    with rasterio.open(water_path) as source:
        water = source.read(1)
        west, north = source.transform.c, source.transform.f
    roads: dict[str, Any] = {}
    for order, way in enumerate(ways, start=1):
        edges = [edge for edge in context["edges"] if str(edge.get("osm_way_id")) == way]
        if not edges:
            continue
        segments = np.array([[to_metres(*context["node_coordinates"][edge["from_node"]]), to_metres(*context["node_coordinates"][edge["to_node"]])]
                             for edge in edges], dtype="float64")
        lengths = cc.centreline_water_lengths(segments, water, west=west, north=north, cell_m=t2.FINE_M)
        pieces = [{"length_m": row["length_m"], "observable_m": row["observable_m"], "water_m": row["on_water_m"],
                   "seen_under_water": bool(row["observable_m"] > 0 and cc.seen_under_water(row))} for row in lengths]
        roads[way] = {"order_in_the_road_sheet": order, "look_at": f"https://www.openstreetmap.org/way/{way}", **study.road_reading(pieces)}
    return roads


def stage_compare(arguments: argparse.Namespace) -> None:
    import rasterio

    external = Path(arguments.external_root)
    work = external / WORK
    freeze_path = ROOT / OUTPUT_DIR / FREEZE_NAME
    reference_path = ROOT / OUTPUT_DIR / f"reference_{arguments.scene_key}_v1.json"
    result_path = ROOT / OUTPUT_DIR / f"comparison_{arguments.scene_key}_v1.json"
    if not (freeze_path.exists() and reference_path.exists()):
        raise BuildError("the radar freeze record and the reference record of the scene must exist and be committed first")
    if result_path.exists():
        raise BuildError("the comparison of this scene has been run; it is run once")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    if reference["radar_freeze"]["sha256"] != t2.sha256_file(freeze_path) or freeze["plan"]["sha256"] != t2.sha256_file(ROOT / PLAN):
        raise BuildError("the plan or the radar freeze record changed after it was committed")
    if reference["amendment"]["sha256"] != t2.sha256_file(ROOT / AMENDMENT):
        raise BuildError("amendment 1 changed after the reference was built")
    if reference.get("set_aside_from_the_comparison"):
        raise BuildError(f"this scene was set aside before any comparison: {reference['set_aside_from_the_comparison']}")
    readings_path = work / READINGS_RASTER
    if t2.sha256_file(readings_path) != freeze["raster_outside_git"]["sha256"]:
        raise BuildError("the radar readings are not the raster the freeze record binds")
    bound = {item["name"]: item["sha256"] for item in reference["rasters_outside_git"]}
    for name, digest in bound.items():
        if t2.sha256_file(work / name) != digest:
            raise BuildError(f"{name} is not the raster the reference record binds")
    area = mae_sai(external)
    with rasterio.open(readings_path) as source:
        readings = {name: source.read(band) for band, name in enumerate(study.READINGS, start=1)}
    inside = area["in_district"] & ~area["permanent_water"]
    seen = rd.observable(area["land_cover"])
    flags = {name: values == 1 for name, values in readings.items()}
    by_rule: dict[str, Any] = {}
    with rasterio.open(work / f"reference_{arguments.scene_key}_10m.tif") as source:
        for index, name in enumerate(RULES):
            if name == "rule_v1" and reference.get("rule_v1_left_out"):
                by_rule[name] = {"left_out": reference["rule_v1_left_out"]}
                continue
            cells = cc.reference_cells(source.read(2 * index + 1), source.read(2 * index + 2))
            rule_compared, rule_wet = cells["compared"] & inside, cells["wet"] & inside
            by_rule[name] = {"compared": rule_compared, "wet": rule_wet,
                             "scores": study.score_readings(flags, rule_wet, rule_compared, cell_km2=CELL_KM2,
                                                            strata={"open_ground": seen, "built_up_or_trees": ~seen})}
    compared, wet, scores = by_rule["rule_v2"]["compared"], by_rule["rule_v2"]["wet"], by_rule["rule_v2"]["scores"]
    acquired = datetime.strptime(reference["scene"]["acquired_utc"], "%Y-%m-%dT%H:%M:%SZ")
    hours = (acquired - datetime.strptime(PASS_AFTER_UTC, "%Y-%m-%dT%H:%M:%SZ")).total_seconds() / 3600
    result = {
        "schema": "floodguard.theos2_study_event_comparison.v1",
        **envelope(),
        "source_timestamp": f"{SOURCE_TIMESTAMP}; THEOS-2 {reference['scene']['acquired_utc']}",
        "what_this_is": "The frozen radar readings of 15 September 2024 against the water of one THEOS-2 image of the study event. Run once.",
        "scene": reference["scene"], "hours_from_the_radar_pass_to_the_image": round(hours, 1),
        "radar_freeze": {"path": f"{OUTPUT_DIR}/{FREEZE_NAME}", "sha256": t2.sha256_file(freeze_path)},
        "reference": {"path": f"{OUTPUT_DIR}/{reference_path.name}", "sha256": t2.sha256_file(reference_path)},
        "compared_km2": round(int(compared.sum()) * CELL_KM2, 3), "reference_water_km2": round(int(wet.sum()) * CELL_KM2, 3),
        "share_of_the_compared_ground_that_is_built_up_or_trees": round(float((compared & ~seen).sum() / max(int(compared.sum()), 1)), 4),
        "reference_rule": "rule_v2",
        "readings": scores,
        "statement": study.statement(scores, hours_after_the_pass=hours),
        "beside_it_rule_v1": by_rule["rule_v1"] if "left_out" in by_rule["rule_v1"] else {
            "compared_km2": round(int(by_rule["rule_v1"]["compared"].sum()) * CELL_KM2, 3),
            "reference_water_km2": round(int(by_rule["rule_v1"]["wet"].sum()) * CELL_KM2, 3),
            "readings": by_rule["rule_v1"]["scores"],
            "note": "Given beside rule v2 as amendment 1 says; nothing is named on these figures."},
        "roads_of_the_ko_chang_road_sheet": road_pieces(external, work / f"reference_{arguments.scene_key}_water_2m.tif"),
        "licence": reference["licence"], "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    t2.write_json(result_path, result)
    print(json.dumps(result["statement"], indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("stage", choices=("radar", "reference", "compare"))
    parser.add_argument("--external-root", required=True)
    parser.add_argument("--delivery", default=DELIVERY, help="the delivery record of the scene, relative to the repository")
    parser.add_argument("--scene-key")
    parser.add_argument("--looked-at", default="")
    parser.add_argument("--set-aside", default="", help="the reason rule v2 fails on the scene; the comparison is then refused")
    parser.add_argument("--rule-v1-left-out", default="", help="the reason rule v1 alone fails; its figures are left out")
    arguments = parser.parse_args()
    if arguments.stage != "radar" and not arguments.scene_key:
        raise BuildError("--scene-key is needed: one key per scene, for example 20240917")
    {"radar": stage_radar, "reference": stage_reference, "compare": stage_compare}[arguments.stage](arguments)


if __name__ == "__main__":
    main()
