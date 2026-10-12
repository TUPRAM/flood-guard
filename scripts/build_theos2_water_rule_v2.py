"""A sturdier THEOS-2 water rule: the development points, the candidates, and the freeze.

Plan: docs/proposal_execution/theos2_water_rule_v2_plan_v1.md.

Stage ``points``
    Draws the 240 development points (another seed than the test points, none within 20 m of one), caches the
    2 m image and rule v1 of each chip outside Git, and writes sheets of pictures the agent labels from. A sheet
    shows a number and three pictures of a point, and no group.

Stage ``freeze``
    Reads the labels the agent gave, scores every candidate on the development points with one chip left out in
    turn, applies the choice of the plan, writes the water raster of the chosen rule for each chip outside Git and
    the freeze record in Git.

    python scripts/build_theos2_water_rule_v2.py points --theos2-dir <downloads> --external-root <external-data-root>
    python scripts/build_theos2_water_rule_v2.py freeze --external-root <external-data-root> --labels <labels file>

The development labels are the reading of an AI model, not of a person, and are never a reference.
"""

from __future__ import annotations

import argparse
import base64
import csv
import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import theos2_water_labels as wl  # noqa: E402
from floodguard import theos2_water_rule_v2 as v2  # noqa: E402

PLAN = "docs/proposal_execution/theos2_water_rule_v2_plan_v1.md"
OUTPUT_DIR = "outputs/theos2_water_rule_v2"
POINTS_NAME = "development_points_v1.json"
FREEZE_NAME = "freeze_v1.json"
WORK = "proposal_execution/theos2_water_rule_v2"
TEST_WORK = "proposal_execution/theos2_water_labels_v1"
TEST_SAMPLE = "outputs/theos2_water_labels/sample_v1.json"
SHEET_POINTS = 12


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


labels_build = load_script("build_theos2_water_labels")
t2 = labels_build.t2
BuildError = t2.BuildError


def envelope() -> dict[str, Any]:
    """The fields every FloodGuard output carries."""

    return {
        "generated_at_utc": t2.now_utc(),
        "source_timestamp": labels_build.SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "A rule developed on three THEOS-2 chips with labels by an AI model; no ground check.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "plan": {"path": PLAN, "sha256": t2.sha256_file(ROOT / PLAN)},
    }


def test_pixels(external: Path) -> dict[str, list[tuple[int, int]]]:
    """The pixels of the test and practice points of each chip, from the key that stays outside Git."""

    sample = json.loads((ROOT / TEST_SAMPLE).read_text(encoding="utf-8"))
    key_path = external / TEST_WORK / labels_build.KEY_NAME
    if t2.sha256_file(key_path) != sample["key_outside_git"]["sha256"]:
        raise BuildError("the key of the test points is not the one the committed draw names")
    key = json.loads(key_path.read_text(encoding="utf-8"))
    pixels: dict[str, list[tuple[int, int]]] = {chip: [] for chip in wl.CHIPS}
    for point in key["points"] + key["practice"]:
        pixels[point["chip"]].append((int(point["row"]), int(point["column"])))
    return pixels


# ---------------------------------------------------------------------------
# Stage 1: the development points and the sheets
# ---------------------------------------------------------------------------


def sheet(tiles: list[tuple[str, dict[str, str]]], path: Path) -> None:
    """One sheet: for each point its number and three pictures, two points to a row. No group is shown."""

    from PIL import Image, ImageDraw

    detail, context, gap, label_height = 256, 160, 6, 14
    width_of_point = 2 * detail + context + 3 * gap
    rows = (len(tiles) + 1) // 2
    canvas = Image.new("RGB", (2 * width_of_point + gap, rows * (detail + label_height + gap) + gap), (24, 24, 24))
    pen = ImageDraw.Draw(canvas)
    scale = detail / labels_build.DETAIL_PX
    for place, (name, shown) in enumerate(tiles):
        left = gap + (place % 2) * width_of_point
        top = gap + (place // 2) * (detail + label_height + gap)
        pen.text((left, top), name, fill=(255, 255, 255))
        for offset, picture in ((0, "d"), (detail + gap, "f")):
            tile = Image.open(io.BytesIO(base64.b64decode(shown[picture]))).resize((detail, detail), Image.NEAREST)
            canvas.paste(tile, (left + offset, top + label_height))
            start = labels_build.SQUARE_AT_PX * scale
            x0, y0 = left + offset + start, top + label_height + start
            pen.rectangle([x0 - 2, y0 - 2, x0 + 4 * scale + 1, y0 + 4 * scale + 1], outline=(255, 230, 0), width=1)
        tile = Image.open(io.BytesIO(base64.b64decode(shown["c"]))).resize((context, context), Image.BILINEAR)
        canvas.paste(tile, (left + 2 * (detail + gap), top + label_height))
        x0, y0 = left + 2 * (detail + gap) + 0.4 * context, top + label_height + 0.4 * context
        pen.rectangle([x0, y0, x0 + 0.2 * context, y0 + 0.2 * context], outline=(255, 230, 0), width=1)
    canvas.save(path, optimize=True)


def stage_points(arguments: argparse.Namespace) -> None:
    import rasterio

    external = Path(arguments.external_root)
    work = external / WORK
    record_path = ROOT / OUTPUT_DIR / POINTS_NAME
    if (ROOT / OUTPUT_DIR / FREEZE_NAME).exists():
        raise BuildError("a rule is frozen; the development points are not drawn again after that")
    if record_path.exists() and not arguments.replace:
        raise BuildError(f"{record_path} exists; a second draw needs --replace with --reason")
    with (ROOT / "outputs/theos2_selected_file_manifest.csv").open(encoding="utf-8", newline="") as handle:
        manifest = {row["file_name"]: row["sha256"] for row in csv.DictReader(handle)}
    taken = test_pixels(external)
    work.mkdir(parents=True, exist_ok=True)

    drawn: list[dict[str, Any]] = []
    shown: dict[tuple[str, int, int], dict[str, str]] = {}
    chips: dict[str, Any] = {}
    for number, chip in enumerate(wl.CHIPS):
        scene = Path(arguments.theos2_dir) / labels_build.CHIPS[chip]["file_name"]
        if manifest.get(scene.name) != t2.sha256_file(scene):
            raise BuildError(f"{scene.name} does not have the SHA-256 the selected-file manifest records")
        run = labels_build.run_rule(scene, chip)
        groups = wl.groups_of(run["water"], run["above"])
        sizes = wl.group_sizes(groups)
        free = v2.away_from(groups.shape, taken[chip], v2.KEEP_AWAY_PX)
        open_groups = np.where(free, groups, v2.NOT_DRAWN)
        open_sizes = {name: int((open_groups == index).sum()) for index, name in enumerate(wl.GROUPS)}
        points = wl.points_per_group(open_sizes, v2.DEVELOPMENT_POINTS[chip])
        mine = wl.draw(open_groups, points, seed=v2.DEVELOPMENT_SEED, chip_number=number)
        limits = labels_build.stretch_limits(run["image"])
        with rasterio.open(scene) as source:
            column0 = int(round((run["west"] - source.transform.c) / labels_build.NATIVE_M))
            row0 = int(round((source.transform.f - run["north"]) / labels_build.NATIVE_M))
            for point in mine:
                point["chip"] = chip
                shown[(chip, point["row"], point["column"])] = labels_build.pictures(
                    source, row0 + point["row"] * t2.READ_FACTOR, column0 + point["column"] * t2.READ_FACTOR, limits)
        np.savez_compressed(work / f"{chip}_2m.npz", image=run["image"], water_v1=run["water"], groups=groups,
                            west=run["west"], north=run["north"])
        drawn.extend(mine)
        chips[chip] = {"pixels_by_group": sizes, "pixels_kept_away_from_test_points": int((~free).sum()),
                       "points_by_group": points, "points": sum(points.values())}
        print(chip, points, flush=True)

    ordered = [{**point, "id": "d" + point["id"][1:]} for point in wl.in_one_order(drawn, seed=v2.DEVELOPMENT_SEED)]
    for first in range(0, len(ordered), SHEET_POINTS):
        part = ordered[first:first + SHEET_POINTS]
        sheet([(point["id"], shown[(point["chip"], point["row"], point["column"])]) for point in part],
              work / f"sheet_{first // SHEET_POINTS + 1:02d}.png")
    record = {
        "schema": "floodguard.theos2_water_rule_v2.development_points.v1",
        **envelope(),
        "what_this_is": "The development points of a second THEOS-2 water rule. They are labelled by the agent that builds "
                        "the rule (an AI model), from sheets that show a number and three pictures. Development data, not a "
                        "reference.",
        "seed": v2.DEVELOPMENT_SEED,
        "kept_away_from_test_points_m": v2.KEEP_AWAY_PX * t2.FINE_M,
        "test_sample": {"path": TEST_SAMPLE, "sha256": t2.sha256_file(ROOT / TEST_SAMPLE)},
        "chips": chips,
        "points": [{key: point[key] for key in ("id", "chip", "group", "row", "column")} for point in ordered],
        "labels": None,
    }
    previous = t2.superseded(record_path, arguments, ("chips", "points"), record)
    if previous is not None:
        record["supersedes"] = previous
    t2.write_json(record_path, record)
    print(json.dumps({"points": len(ordered), "sheets": (len(ordered) + SHEET_POINTS - 1) // SHEET_POINTS}))


# ---------------------------------------------------------------------------
# Stage 2: the candidates, the choice and the freeze
# ---------------------------------------------------------------------------

LABELS_NAME = "development_labels_v1.json"
OVERVIEW_NAME = "rule_v1_and_v2_overview.jpg"
THRESHOLD_GRID = tuple(round(-0.10 + 0.01 * step, 2) for step in range(13))  # -0.10 ... 0.02
CLOUD_WIDTHS_PX = (11, 20, 40)
CLOUD_INDEX_LIMITS = (-0.04, -0.06, -0.08)


def chip_features(image: np.ndarray, water_v1: np.ndarray) -> dict[str, np.ndarray]:
    from floodguard import theos2_cross_check as cc

    red, green, blue, nir = image.astype("float64")
    brightness = (red + green + blue) / 3.0
    return {
        "red": red, "green": green, "blue": blue, "nir": nir, "v1": water_v1,
        "index": v2.red_nir_index(red, nir), "water_index": cc.ndwi(green, nir), "brightness": brightness,
        "red_blue": (red - blue) / (red + blue), "green_blue": (green - blue) / (green + blue),
        "relative_brightness": brightness / float(np.median(brightness)),
    }


def bright(features: dict[str, np.ndarray], width_px: int) -> np.ndarray:
    from floodguard import theos2_cross_check as cc

    config = v2.WaterRuleV2()
    return cc.bright_object_mask(features["brightness"], features["nir"], brightness_min=config.bright_brightness_min,
                                 nir_min=config.bright_nir_min, min_width_px=width_px, margin_px=config.cloud_margin_px)


def without_small_objects(mask: np.ndarray, min_px: int) -> np.ndarray:
    from scipy import ndimage

    labelled, _ = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    keep = np.bincount(labelled.ravel()) >= min_px
    keep[0] = False
    return keep[labelled]


def stage_freeze(arguments: argparse.Namespace) -> None:
    import warnings

    import rasterio
    from rasterio.transform import from_origin
    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier

    external = Path(arguments.external_root)
    work = external / WORK
    out = ROOT / OUTPUT_DIR
    freeze_path = out / FREEZE_NAME
    if (ROOT / "outputs/theos2_water_labels/result_v1.json").exists():
        raise BuildError("the figures of the label check exist: no rule is frozen after the test labels were scored")
    if freeze_path.exists() and not arguments.replace:
        raise BuildError(f"{freeze_path} exists; a second freeze needs --replace with --reason")
    record = json.loads((out / POINTS_NAME).read_text(encoding="utf-8"))
    points = record["points"]
    given = json.loads(Path(arguments.labels).read_text(encoding="utf-8"))
    labels = wl.check_labels({"sample_id": "development", "labeller": given["labeller"], "labels": given["labels"]},
                             sample_id="development", point_ids=[point["id"] for point in points])
    scoring = wl.alone(labels)
    sizes = {(chip, group): int(record["chips"][chip]["pixels_by_group"][group]) for chip in wl.CHIPS for group in wl.GROUPS}
    caches = {chip: np.load(work / f"{chip}_2m.npz") for chip in wl.CHIPS}
    features = {chip: chip_features(caches[chip]["image"], caches[chip]["water_v1"]) for chip in wl.CHIPS}
    words = {v2.WATER_YES: wl.WATER, v2.WATER_NO: wl.NOT_WATER, v2.WATER_UNOBSERVABLE: wl.UNOBSERVABLE}

    def scores(rasters: dict[str, np.ndarray]) -> dict[str, Any]:
        """The share answered and alike of a candidate on each chip, and their mean."""

        answers = {point["id"]: words[int(rasters[point["chip"]][point["row"], point["column"]])] for point in points}
        by_chip = {chip: wl.figures_of_a_map(points, scoring, answers, sizes, (chip,))["share_answered_and_alike"]["estimate"]
                   for chip in wl.CHIPS}
        return {"by_chip": by_chip, "mean": round(float(np.mean(list(by_chip.values()))), 4),
                "water_share_of_the_chip": {chip: round(float((rasters[chip] == v2.WATER_YES).mean()), 4) for chip in wl.CHIPS},
                "unobservable_share_of_the_chip": {chip: round(float((rasters[chip] == v2.WATER_UNOBSERVABLE).mean()), 4)
                                                  for chip in wl.CHIPS}}

    def from_rule(rule: Any) -> dict[str, np.ndarray]:
        return {chip: np.where(rule(features[chip]), v2.WATER_YES, v2.WATER_NO).astype("uint8") for chip in wl.CHIPS}

    scored = [point for point in points if scoring[point["id"]] is not None]

    def table(names: tuple[str, ...], chips: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rows, target, weight = [], [], []
        for point in scored:
            if point["chip"] not in chips:
                continue
            rows.append([features[point["chip"]][name][point["row"], point["column"]] for name in names])
            target.append(int(scoring[point["id"]] == wl.WATER))
            in_group = sum(1 for other in scored if other["chip"] == point["chip"] and other["group"] == point["group"])
            weight.append(sizes[(point["chip"], point["group"])] / in_group)
        return np.array(rows), np.array(target), np.array(weight)

    def fitted_without_each_chip(names: tuple[str, ...], factory: Any, area_weighted: bool) -> dict[str, np.ndarray]:
        rasters = {}
        for chip in wl.CHIPS:
            rows, target, weight = table(names, [other for other in wl.CHIPS if other != chip])
            model = factory().fit(rows, target, sample_weight=weight / weight.mean() if area_weighted else None)
            stacked = np.stack([features[chip][name].ravel() for name in names], axis=1)
            rasters[chip] = model.predict(stacked).reshape(features[chip]["red"].shape).astype("uint8")
        return rasters

    candidates: list[dict[str, Any]] = []

    def add(name: str, fitted: int, rasters: dict[str, np.ndarray], note: str = "") -> dict[str, Any]:
        entry = {"name": name, "fitted_parameters": fitted, **scores(rasters), **({"note": note} if note else {})}
        candidates.append(entry)
        print(f"{name:62s} {entry['mean']:.3f} {entry['by_chip']}", flush=True)
        return entry

    add("rule_v1", 0, {chip: features[chip]["v1"] for chip in wl.CHIPS}, "The rule of the earlier checks, as it was run.")
    add("nir_at_or_below_red", 0, from_rule(lambda f: f["index"] <= 0.0))
    grid = {limit: scores(from_rule(lambda f, limit=limit: f["index"] <= limit)) for limit in THRESHOLD_GRID}
    chosen_without, rasters = {}, {}
    for chip in wl.CHIPS:
        others = [other for other in wl.CHIPS if other != chip]
        best = max(THRESHOLD_GRID, key=lambda limit: (round(float(np.mean([grid[limit]["by_chip"][o] for o in others])), 6), limit))
        chosen_without[chip] = best
        rasters[chip] = np.where(features[chip]["index"] <= best, v2.WATER_YES, v2.WATER_NO).astype("uint8")
    threshold = add("index_at_or_below_a_fitted_limit", 1, rasters,
                    f"The limit is fitted without the chip that is scored; limits chosen: {chosen_without}.")
    threshold["limits_on_all_three_chips"] = {str(limit): grid[limit]["mean"] for limit in THRESHOLD_GRID}
    for limit in (-0.045, -0.10, -0.145):
        add(f"water_index_at_or_above_{limit}", 1, from_rule(lambda f, limit=limit: f["water_index"] >= limit),
            "The water index of rule v1 with one limit for every image; the limit is not fitted without the chip.")
    for min_px in (25, 250):
        add(f"index_at_or_below_-0.02_objects_of_{min_px}_px_or_more", 2,
            from_rule(lambda f, min_px=min_px: without_small_objects(f["index"] <= -0.02, min_px)),
            "Tried to see whether a size rule helps; the limit and the size are not fitted without the chip.")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for area_weighted in (False, True):
            tag = "area_weighted" if area_weighted else "unweighted"
            for names in (("index", "water_index", "red_blue"), ("index", "water_index", "red_blue", "green_blue"),
                          ("index", "red_blue"), ("index", "water_index", "red_blue", "relative_brightness")):
                add(f"logistic_{'_'.join(names)}_{tag}", len(names) + 1,
                    fitted_without_each_chip(names, lambda: LogisticRegression(C=10.0, max_iter=2000), area_weighted))
            add(f"tree_depth_2_index_water_index_red_blue_{tag}", 3, fitted_without_each_chip(
                ("index", "water_index", "red_blue"), lambda: DecisionTreeClassifier(max_depth=2, random_state=0), area_weighted))
            add(f"tree_depth_3_with_relative_brightness_{tag}", 7, fitted_without_each_chip(
                ("index", "water_index", "red_blue", "relative_brightness"),
                lambda: DecisionTreeClassifier(max_depth=3, min_samples_leaf=5, random_state=0), area_weighted))
    for limit in (0.08, 0.12, 0.15):
        add(f"nir_at_or_below_red_and_brown_or_dark_{limit}", 2, from_rule(
            lambda f, limit=limit: (f["index"] <= 0.0) & ((f["red_blue"] >= limit) | (f["relative_brightness"] < 0.9))),
            "A hand rule with a colour condition against grey roofs; its two limits are not fitted without the chip.")

    # --- the choice of the plan (section 4) ---------------------------------------------------------------------------
    best = max(candidates, key=lambda entry: entry["mean"])
    near = [entry for entry in candidates if best["mean"] - entry["mean"] <= 0.01]
    choice = min(near, key=lambda entry: (entry["fitted_parameters"], -entry["mean"]))
    rule_v1 = candidates[0]
    if choice["mean"] - rule_v1["mean"] <= 0.01:
        raise BuildError("no candidate is more than 0.01 above rule v1: rule v1 stays, and this stage has nothing to freeze")
    if choice["name"] != "index_at_or_below_a_fitted_limit":
        raise BuildError(f"the plan chooses {choice['name']}, which this stage does not know how to freeze")
    limit_all = max(THRESHOLD_GRID, key=lambda limit: (grid[limit]["mean"], limit))
    config = v2.WaterRuleV2()
    if limit_all != config.index_water_max:
        raise BuildError(f"the limit fitted on all three chips is {limit_all}; the rule in the code holds {config.index_water_max}")

    # --- cloud: outside the score, because a point under cloud has no scoring label ----------------------------------------
    kinds = given.get("cannot_tell_because", {})
    cloud_points = [point for point in points if kinds.get(point["id"]) == "cloud"]

    def cloud_variant(name: str, build: Any) -> dict[str, Any]:
        made = {chip: build(features[chip]) for chip in wl.CHIPS}
        answers = [words[int(made[point["chip"]][point["row"], point["column"]])] for point in cloud_points]
        return {"name": name, **scores(made), "cloud_points": len(cloud_points),
                "cloud_points_set_aside": answers.count(wl.UNOBSERVABLE), "cloud_points_called_water": answers.count(wl.WATER)}

    def with_cloud(f: dict[str, np.ndarray], mask: np.ndarray, how: str, index_limit: float = 0.0) -> np.ndarray:
        water = f["index"] <= limit_all
        answer = np.where(water, v2.WATER_YES, v2.WATER_NO).astype("uint8")
        if how == "water_first":
            answer[mask & ~water] = v2.WATER_UNOBSERVABLE
        elif how == "cloud_first":
            answer[mask] = v2.WATER_UNOBSERVABLE
        else:
            answer[mask & (f["index"] > index_limit)] = v2.WATER_UNOBSERVABLE
        return answer

    cloud_variants = [cloud_variant("no_cloud_rule", lambda f: with_cloud(f, np.zeros(f["red"].shape, dtype=bool), "water_first"))]
    for width in CLOUD_WIDTHS_PX:
        masks = {id(features[chip]["red"]): bright(features[chip], width) for chip in wl.CHIPS}
        cloud_variants.append(cloud_variant(f"bright_{width}_px_wide_water_first", lambda f: with_cloud(f, masks[id(f["red"])], "water_first")))
        cloud_variants.append(cloud_variant(f"bright_{width}_px_wide_cloud_first", lambda f: with_cloud(f, masks[id(f["red"])], "cloud_first")))
        for index_limit in CLOUD_INDEX_LIMITS:
            cloud_variants.append(cloud_variant(
                f"bright_{width}_px_wide_and_index_above_{index_limit}",
                lambda f, index_limit=index_limit: with_cloud(f, masks[id(f["red"])], "by_index", index_limit)))
    for entry in cloud_variants:
        print(f"{entry['name']:62s} {entry['mean']:.3f} set aside {entry['cloud_points_set_aside']} of {entry['cloud_points']}", flush=True)

    # --- the frozen rule on each chip -----------------------------------------------------------------------------------
    frozen: dict[str, Any] = {}
    frozen_rasters: dict[str, np.ndarray] = {}
    for chip in wl.CHIPS:
        image = caches[chip]["image"]
        red, green, blue, nir = (image[t2.THEOS2_BANDS[name] - 1] for name in ("red", "green", "blue", "nir"))
        water, summary = v2.water_v2(red, green, blue, nir, nir > 0, config)
        frozen_rasters[chip] = water
        name = f"water_v2_{chip}_2m.tif"
        with rasterio.open(work / name, "w", driver="GTiff", height=water.shape[0], width=water.shape[1], count=1, dtype="uint8",
                           nodata=v2.WATER_UNOBSERVABLE, crs=f"EPSG:{t2.EPSG}", compress="deflate",
                           transform=from_origin(float(caches[chip]["west"]), float(caches[chip]["north"]), t2.FINE_M, t2.FINE_M)) as target:
            target.write(water, 1)
        v1 = caches[chip]["water_v1"]
        frozen[chip] = {
            "rule_v2": summary,
            "water_share_of_the_chip": {"rule_v1": round(float((v1 == v2.WATER_YES).mean()), 4),
                                        "rule_v2": round(float((water == v2.WATER_YES).mean()), 4)},
            "unobservable_share_of_the_chip": {"rule_v1": round(float((v1 == v2.WATER_UNOBSERVABLE).mean()), 4),
                                               "rule_v2": round(float((water == v2.WATER_UNOBSERVABLE).mean()), 4)},
            "raster_outside_git": {"name": name, "sha256": t2.sha256_file(work / name)},
        }
    frozen_scores = scores(frozen_rasters)
    write_overview(out / OVERVIEW_NAME, caches, frozen_rasters)
    answers = [words[int(frozen_rasters[point["chip"]][point["row"], point["column"]])] for point in cloud_points]

    label_record = {
        "schema": "floodguard.theos2_water_rule_v2.development_labels.v1",
        "what_this_is": "The labels the agent (an AI model) gave the 240 development points, from sheets that show a number and "
                        "three pictures of a point and no group. Development data, not a reference.",
        "labeller": given["labeller"], "labelled_on": given["labelled_on"],
        "counts": {label: sum(1 for value in labels.values() if value == label) for label in wl.LABELS},
        "labels": labels,
        "cannot_tell_because": kinds,
    }
    t2.write_json(out / LABELS_NAME, label_record)
    result = {
        "schema": "floodguard.theos2_water_rule_v2.freeze.v1",
        **envelope(),
        "what_this_is": "The second THEOS-2 water rule, chosen on 240 development points labelled by the agent and frozen "
                        "before any label of a team member was read. It is scored on the 300 test points in the run that "
                        "computes the figures of the label check.",
        "test_labels_read_before_this_freeze": False,
        "development_points": {"path": f"{OUTPUT_DIR}/{POINTS_NAME}", "sha256": t2.sha256_file(out / POINTS_NAME)},
        "development_labels": {"path": f"{OUTPUT_DIR}/{LABELS_NAME}", "sha256": t2.sha256_file(out / LABELS_NAME),
                               "counts": label_record["counts"]},
        "choice_figure": "Share answered and alike: of the area where the development label is water or not water, the share "
                         "where the candidate gives an answer and the answer is the label; each group weighted by its pixels. "
                         "A candidate with fitted parameters is scored on a chip by a version fitted without that chip.",
        "candidates": candidates,
        "choice": {
            "best_mean": best["name"], "chosen": choice["name"], "fitted_parameters": choice["fitted_parameters"],
            "rule_of_the_plan": "Highest mean over the three chips; a candidate within 0.01 of the best with fewer fitted "
                                "parameters is preferred; nothing is frozen unless it is more than 0.01 above rule v1.",
            "mean_of_rule_v1": rule_v1["mean"], "mean_of_the_chosen_with_one_chip_left_out": choice["mean"],
            "limit_fitted_on_all_three_chips": limit_all,
        },
        "cloud": {
            "why_outside_the_score": "A point under cloud has no scoring label, so the choice figure cannot see whether cloud "
                                     "is set aside. The variant frozen is the one that sets aside the most points the agent "
                                     "marked as cloud without lowering the choice figure. This is an addition to the plan, "
                                     "made on five points, and is said so.",
            "variants": cloud_variants,
            "frozen": f"bright_{config.cloud_min_width_px}_px_wide_and_index_above_{config.index_cloud_min}",
            "cloud_points_set_aside_by_the_frozen_rule": answers.count(wl.UNOBSERVABLE),
            "cloud_points_called_water_by_the_frozen_rule": answers.count(wl.WATER),
        },
        "overview": {"path": f"{OUTPUT_DIR}/{OVERVIEW_NAME}", "sha256": t2.sha256_file(out / OVERVIEW_NAME),
                     "note": "The three chips at 6 m a pixel with the water of each rule. A picture to look at, not a measurement."},
        "frozen_rule": {
            "code": "floodguard.theos2_water_rule_v2.water_v2",
            "configuration": summary["configuration"],
            "in_words": "A pixel of 2 m is water when (NIR - red) / (NIR + red) is at or below -0.01. Inside a bright object "
                        "at least 80 m wide, a pixel with that index above -0.04 is unobservable (cloud). No limit is found "
                        "on the image, no object is dropped for its size, and nothing is set by eye.",
            "share_answered_and_alike_on_the_development_points": frozen_scores,
            "chips": frozen,
        },
        "limits": [
            "The development labels are the reading of an AI model on the same four bands the rule reads.",
            "The limit of -0.01 was the best on every pair of chips, but there are only three chips, two of them from one pass.",
            "Roofs, roads and concrete have an index just below zero and are called water in places; thin cloud that is not "
            "bright is not set aside.",
            "The two brightness limits are raw sensor values taken over from rule v1; a scene with other light may need others.",
            "On the chip without a flood the rule finds no water at all, also not the river in one corner of it: seen on the "
            "overview picture, not measured.",
            "None of the three chips shows Mae Sai, a mountain valley, or terrain shadow.",
        ],
    }
    previous = t2.superseded(freeze_path, arguments, ("candidates", "frozen_rule"), result)
    if previous is not None:
        result["supersedes"] = previous
    t2.write_json(freeze_path, result)
    print(json.dumps({"chosen": choice["name"], "limit": limit_all, "v1": rule_v1["mean"], "chosen_mean": choice["mean"],
                      "frozen_on_development": frozen_scores["by_chip"]}, indent=1))


def write_overview(path: Path, caches: dict[str, Any], rasters: dict[str, np.ndarray]) -> None:
    """One row for each chip: the image, the water of rule v1 and the water of rule v2, at 6 m a pixel."""

    from PIL import Image, ImageDraw

    step, gap, head = 3, 8, 22
    blue, set_aside = np.array([42, 120, 214]), np.array([170, 170, 170])
    titles = ("THEOS-2 image", "Rule v1: water (blue), set aside (grey)", "Rule v2: water (blue), set aside (grey)")
    rows = []
    for chip in wl.CHIPS:
        image = caches[chip]["image"]
        limits = labels_build.stretch_limits(image)
        look = labels_build.to_bytes(image, limits, (t2.THEOS2_BANDS["red"] - 1, t2.THEOS2_BANDS["green"] - 1,
                                                     t2.THEOS2_BANDS["blue"] - 1))[::step, ::step]
        panels = [look]
        for water in (caches[chip]["water_v1"], rasters[chip]):
            small = water[::step, ::step]
            marked = (look * 0.35).astype("uint8")
            marked[small == v2.WATER_YES] = blue
            marked[small == v2.WATER_UNOBSERVABLE] = set_aside
            panels.append(marked)
        rows.append((chip, panels))
    side = rows[0][1][0].shape[0]
    width = 3 * rows[0][1][0].shape[1] + 4 * gap
    canvas = Image.new("RGB", (width, len(rows) * (side + head + gap) + gap), (255, 255, 255))
    pen = ImageDraw.Draw(canvas)
    for place, (chip, panels) in enumerate(rows):
        top = gap + place * (side + head + gap)
        for column, panel in enumerate(panels):
            left = gap + column * (panel.shape[1] + gap)
            pen.text((left, top + 4), f"{chip}: {titles[column]}", fill=(20, 20, 20))
            canvas.paste(Image.fromarray(panel), (left, top + head))
    canvas.save(path, format="JPEG", quality=88)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    stages = parser.add_subparsers(dest="stage", required=True)
    first = stages.add_parser("points")
    first.add_argument("--theos2-dir", required=True, help="the folder that holds the three THEOS-2 files")
    second = stages.add_parser("freeze")
    second.add_argument("--labels", required=True, help="the labels the agent gave the development points")
    for stage in (first, second):
        stage.add_argument("--external-root", required=True)
        stage.add_argument("--replace", action="store_true")
        stage.add_argument("--reason", default="")
    arguments = parser.parse_args()
    {"points": stage_points, "freeze": stage_freeze}[arguments.stage](arguments)


if __name__ == "__main__":
    main()
