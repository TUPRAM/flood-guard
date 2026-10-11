"""The THEOS-2 water rule against labels by two people: the draw of the points, and the figures.

Plan: docs/proposal_execution/theos2_water_label_check_plan_v1.md.

Stage ``sample``
    Runs the water rule again on the three THEOS-2 chips, checks it against the committed records, puts every
    pixel in one of six groups and draws 300 points. Writes the key and the page a labeller opens outside Git,
    and a record with their SHA-256 in Git. The page holds pixels of the THEOS-2 samples and never enters Git;
    the key enters Git with the figures.

Stage ``score``
    Reads the key and the two label files, computes the figures of the plan once, and writes the result, the key
    and the label files to Git.

    python scripts/build_theos2_water_labels.py sample --theos2-dir <downloads> --external-root <external-data-root>
    python scripts/build_theos2_water_labels.py score --external-root <external-data-root> \
        --labels <first label file> <second label file>

Nothing here is a ground check: the labels come from the same image the rule reads.
"""

from __future__ import annotations

import argparse
import base64
import csv
import importlib.util
import io
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import theos2_cross_check as cc  # noqa: E402
from floodguard import theos2_water_labels as wl  # noqa: E402

PLAN = "docs/proposal_execution/theos2_water_label_check_plan_v1.md"
OUTPUT_DIR = "outputs/theos2_water_labels"
SAMPLE_NAME = "sample_v1.json"
RESULT_NAME = "result_v1.json"
KEY_NAME = "key_v1.json"
PAGE_NAME = "label_page_v1.html"
PAGE_TEMPLATE = "scripts/theos2_water_label_page.html"
WORK = "proposal_execution/theos2_water_labels_v1"
SOURCE_TIMESTAMP = "THEOS-2 2025-07-30T03:33Z (sukhothai) and 2025-07-31T03:51Z (chip_003, chip_001)"

NATIVE_M = 0.5
DETAIL_PX = 128          # 64 m at 0.5 m
SQUARE_AT_PX = 62        # the 4 by 4 pixels of the square start here in the detail picture
CONTEXT_NATIVE_PX = 640  # 320 m at 0.5 m
CONTEXT_PX = 320         # shown at 1 m
STRETCH_PERCENTILES = (0.5, 99.5)
STRETCH_GAMMA = 0.8
JPEG_QUALITY = 90

LIMITS = [
    "The labels come from the same image the rule reads, in true and false colour: the figures say whether the rule "
    "reads the image as a person does, not what was on the ground.",
    "The labellers are team members, not trained image interpreters.",
    "Three chips of two days in one season and one region; none of them covers Mae Sai.",
    "A square of 2 m at the edge of water is often mixed; 'more than half' is a judgement.",
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

# Each chip: its scene, the setting of the rule, and where the committed record of the rule's run is.
CHIPS: dict[str, dict[str, Any]] = {
    "sukhothai": {
        "file_name": t2.THEOS2_FILE, "config": t2.OPTICAL_CONFIG,
        "record": ("outputs/theos2_cross_check/sukhothai_20250730_reference_v1.json", ("optical_water_rule",)),
    },
    "chip_003": {
        "file_name": "IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif", "config": cc.OpticalWaterConfig(),
        "record": ("outputs/radar_detection_improvement/held_out_reference_v1.json", ("chips", "chip_003", "optical_water_rule")),
    },
    "chip_001": {
        "file_name": "IMG_T2V_20250731035100_ORTHO_PMS_32-001.tif", "config": cc.OpticalWaterConfig(),
        "record": ("outputs/radar_detection_improvement/held_out_reference_v1.json", ("chips", "chip_001", "optical_water_rule")),
    },
}


def envelope() -> dict[str, Any]:
    """The fields every FloodGuard output carries."""

    return {
        "generated_at_utc": t2.now_utc(),
        "source_timestamp": SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "Labels by two team members on the image the rule reads; no ground check.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "plan": {"path": PLAN, "sha256": t2.sha256_file(ROOT / PLAN)},
    }


def committed_rule_summary(chip: str) -> dict[str, Any]:
    path, keys = CHIPS[chip]["record"]
    value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    for key in keys:
        value = value[key]
    return value


# ---------------------------------------------------------------------------
# Stage 1: the draw, the key and the page
# ---------------------------------------------------------------------------


def run_rule(scene: Path, chip: str) -> dict[str, Any]:
    """Run the water rule on a scene as it was run for the record, and check it against that record."""

    image, (west, north) = t2.read_theos2_chip(scene)
    red, green, blue, nir = (image[t2.THEOS2_BANDS[name] - 1] for name in ("red", "green", "blue", "nir"))
    config = CHIPS[chip]["config"]
    water, summary = cc.optical_water(red, green, blue, nir, nir > 0, config)
    recorded = committed_rule_summary(chip)
    for field in ("water_pixels", "pixels_dropped_by_object_rule", "observable_pixels", "ndwi_threshold_applied"):
        if summary[field] != recorded[field]:
            raise BuildError(f"{chip}: the rule gives {field} = {summary[field]}, the committed record holds {recorded[field]}")
    # The threshold the rule applied, without the rounding of the record.
    index = cc.ndwi(green, nir)
    observable = water != cc.WATER_UNOBSERVABLE
    threshold = cc.multi_otsu_thresholds(index[observable], low=config.histogram_low, high=config.histogram_high,
                                         bins=config.histogram_bins)[1] if config.ndwi_threshold is None else config.ndwi_threshold
    with np.errstate(invalid="ignore"):
        above = observable & (index >= threshold)
    if int(above.sum() - (water == cc.WATER_YES).sum()) != recorded["pixels_dropped_by_object_rule"]:
        raise BuildError(f"{chip}: the pixels above the threshold are not those of the committed record")
    return {"image": image, "west": west, "north": north, "water": water, "above": above, "summary": summary}


def stretch_limits(image: np.ndarray) -> list[tuple[float, float]]:
    """The dark and the bright end of each band of a chip, the same for every picture of that chip."""

    return [tuple(float(value) for value in np.percentile(band, STRETCH_PERCENTILES)) for band in image]


def to_bytes(bands: np.ndarray, limits: list[tuple[float, float]], order: tuple[int, int, int]) -> np.ndarray:
    """Three bands of a window as an 8-bit picture, with the fixed stretch of the chip."""

    layers = []
    for band in order:
        low, high = limits[band]
        scaled = np.clip((bands[band].astype("float64") - low) / max(high - low, 1.0), 0.0, 1.0) ** STRETCH_GAMMA
        layers.append(np.round(scaled * 255).astype("uint8"))
    return np.stack(layers, axis=-1)


def jpeg(picture: np.ndarray) -> str:
    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(picture).save(buffer, format="JPEG", quality=JPEG_QUALITY, subsampling=0)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def pictures(source: Any, native_row: int, native_column: int, limits: list[tuple[float, float]]) -> dict[str, str]:
    """The three pictures of a point whose square starts at a native pixel of the scene."""

    from rasterio.windows import Window

    true_colour = (t2.THEOS2_BANDS["red"] - 1, t2.THEOS2_BANDS["green"] - 1, t2.THEOS2_BANDS["blue"] - 1)
    false_colour = (t2.THEOS2_BANDS["nir"] - 1, t2.THEOS2_BANDS["red"] - 1, t2.THEOS2_BANDS["green"] - 1)
    detail = source.read(window=Window(native_column - SQUARE_AT_PX, native_row - SQUARE_AT_PX, DETAIL_PX, DETAIL_PX),
                         boundless=True, masked=True).filled(0)
    middle = 2  # the centre of the square of 4 pixels
    half = CONTEXT_NATIVE_PX // 2
    context = source.read(window=Window(native_column + middle - half, native_row + middle - half, CONTEXT_NATIVE_PX, CONTEXT_NATIVE_PX),
                          boundless=True, masked=True).filled(0).astype("float64")
    # Averaged here and not by the reader, so that the dark outside the scene is the same in every picture.
    factor = CONTEXT_NATIVE_PX // CONTEXT_PX
    context = context.reshape(4, CONTEXT_PX, factor, CONTEXT_PX, factor).mean(axis=(2, 4))
    return {"d": jpeg(to_bytes(detail, limits, true_colour)), "f": jpeg(to_bytes(detail, limits, false_colour)),
            "c": jpeg(to_bytes(context, limits, true_colour))}


def stage_sample(arguments: argparse.Namespace) -> None:
    import rasterio

    work = Path(arguments.external_root) / WORK
    record_path = ROOT / OUTPUT_DIR / SAMPLE_NAME
    if (ROOT / OUTPUT_DIR / RESULT_NAME).exists():
        raise BuildError("the figures have been computed; the points are not drawn again after that")
    if record_path.exists() and not arguments.replace:
        raise BuildError(f"{record_path} exists; a second draw needs --replace with --reason")
    with (ROOT / "outputs/theos2_selected_file_manifest.csv").open(encoding="utf-8", newline="") as handle:
        manifest = {row["file_name"]: row["sha256"] for row in csv.DictReader(handle)}

    drawn: list[dict[str, Any]] = []
    practice: list[dict[str, Any]] = []
    shown: dict[tuple[str, int, int], dict[str, str]] = {}
    chips: dict[str, Any] = {}
    for number, chip in enumerate(wl.CHIPS):
        scene = Path(arguments.theos2_dir) / CHIPS[chip]["file_name"]
        scene_sha = t2.sha256_file(scene)
        if manifest.get(scene.name) != scene_sha:
            raise BuildError(f"{scene.name} does not have the SHA-256 the selected-file manifest records")
        run = run_rule(scene, chip)
        groups = wl.groups_of(run["water"], run["above"])
        sizes = wl.group_sizes(groups)
        points = wl.points_per_group(sizes, wl.PLANNED_POINTS[chip])
        mine = wl.draw(groups, points, seed=wl.SEED, chip_number=number)
        extra = wl.draw_practice(groups, [(p["row"], p["column"]) for p in mine], seed=wl.SEED) if chip == wl.PRACTICE_CHIP else []
        limits = stretch_limits(run["image"])
        with rasterio.open(scene) as source:
            column0 = int(round((run["west"] - source.transform.c) / NATIVE_M))
            row0 = int(round((source.transform.f - run["north"]) / NATIVE_M))
            for point in mine + extra:
                point["chip"] = chip
                point["x"] = run["west"] + (point["column"] + 0.5) * t2.FINE_M
                point["y"] = run["north"] - (point["row"] + 0.5) * t2.FINE_M
                shown[(chip, point["row"], point["column"])] = pictures(
                    source, row0 + point["row"] * t2.READ_FACTOR, column0 + point["column"] * t2.READ_FACTOR, limits)
        drawn.extend(mine)
        practice.extend(extra)
        chips[chip] = {
            "file_name": scene.name, "sha256": scene_sha,
            "rule_run_checked_against": CHIPS[chip]["record"][0],
            "ndwi_threshold_applied": run["summary"]["ndwi_threshold_applied"],
            "pixels_2m": int(groups.size),
            "pixels_by_group": sizes,
            "points_by_group": points,
            "points": sum(points.values()),
            "stretch_of_the_pictures": {"percentiles": list(STRETCH_PERCENTILES), "gamma": STRETCH_GAMMA,
                                        "limits_by_band": [[round(low, 1), round(high, 1)] for low, high in limits]},
        }
        print(chip, sizes, points, flush=True)

    ordered = wl.in_one_order(drawn, seed=wl.SEED)
    key = {
        "schema": "floodguard.theos2_water_labels.key.v1",
        "plan": PLAN, "seed": wl.SEED, "epsg": t2.EPSG, "pixel_m": t2.FINE_M,
        "what_a_point_is": "One pixel of the 2 m raster of the water rule; x and y are its centre.",
        "points": [{key: point[key] for key in ("id", "chip", "group", "row", "column", "x", "y")} for point in ordered],
        "practice": [{key: point[key] for key in ("chip", "group", "row", "column", "x", "y")} for point in practice],
    }
    work.mkdir(parents=True, exist_ok=True)
    t2.write_json(work / KEY_NAME, key)
    sample_id = t2.sha256_file(work / KEY_NAME)

    def for_page(points: list[dict[str, Any]], named: bool) -> str:
        rows = [{**({"id": point["id"]} if named else {}), **shown[(point["chip"], point["row"], point["column"])]} for point in points]
        return json.dumps(rows, separators=(",", ":"))

    page = (ROOT / PAGE_TEMPLATE).read_text(encoding="utf-8")
    for token, value in (("/*SAMPLE_ID*/", sample_id), ("/*PRACTICE*/[]", for_page(practice, False)),
                         ("/*POINTS*/[]", for_page(ordered, True))):
        if page.count(token) != 1:
            raise BuildError(f"the page template does not hold {token} exactly once")
        page = page.replace(token, value)
    (work / PAGE_NAME).write_bytes(page.encode("utf-8"))

    record = {
        "schema": "floodguard.theos2_water_labels.sample.v1",
        **envelope(),
        "what_this_is": "The draw of the points on which two people label water or not water, made before anybody labelled. "
                        "It holds no place of a point and no group of a point: the key stays outside Git until the figures "
                        "are computed, because the repository is public and the labellers read it.",
        "seed": wl.SEED,
        "edge_distance_px": wl.EDGE_PX,
        "groups": list(wl.GROUPS),
        "chips": chips,
        "points": len(ordered),
        "practice_points": len(practice),
        "labels": list(wl.LABELS),
        "sample_id": sample_id,
        "key_outside_git": {"name": KEY_NAME, "sha256": sample_id},
        "page_outside_git": {"name": PAGE_NAME, "sha256": t2.sha256_file(work / PAGE_NAME),
                             "template": {"path": PAGE_TEMPLATE, "sha256": t2.sha256_file(ROOT / PAGE_TEMPLATE)},
                             "megabytes": round((work / PAGE_NAME).stat().st_size / 1e6, 1),
                             "holds_the_answer_of_the_rule": False},
        "labels_received": 0,
        "licence": "THEOS-2 sample imagery provided by GISTDA for GeoHackathon 2026 (docs/theos2_usage_terms_log.md). "
                   "The page holds pixels of the samples and stays outside Git.",
        "limits": LIMITS,
    }
    previous = t2.superseded(record_path, arguments, ("chips", "sample_id"), record)
    if previous is not None:
        record["supersedes"] = previous
    t2.write_json(record_path, record)
    print(json.dumps({"points": len(ordered), "practice": len(practice), "sample_id": sample_id,
                      "page_megabytes": record["page_outside_git"]["megabytes"]}, indent=1))


# ---------------------------------------------------------------------------
# Stage 2: the figures
# ---------------------------------------------------------------------------


def percent(value: float | None) -> str:
    return "no figure" if value is None else f"{round(value * 100)}%"


def with_interval(figure: dict[str, Any]) -> str:
    if figure["estimate"] is None:
        return "no figure"
    if figure["standard_error"] == 0:
        # Every scored point of every group says the same: the sample gives no spread to make an interval from.
        return f"{percent(figure['estimate'])} (no interval: the scored points of each group all say the same)"
    low, high = figure["interval_95"]
    return f"{percent(figure['estimate'])} ({percent(low)} to {percent(high)})"


def sentences(names: list[str], together: dict[str, Any], set_aside: dict[str, Any], readers: dict[str, Any]) -> list[str]:
    """The sentences of plan section 7, written from the figures whatever they are."""

    agreed = together["both_agree"]
    alone = set_aside["both_agree"]
    return [
        f"{names[0]} and {names[1]} each labelled {readers['points']} points on three THEOS-2 chips. On the two chips "
        f"that served as a reference they gave the same label of water or not water on {agreed['points_scored']} of "
        f"{agreed['points']} points. On those, {with_interval(agreed['a_share_of_rule_water_labelled_water'])} of the area "
        f"the rule calls water is water to both, and the rule finds "
        f"{with_interval(agreed['b_share_of_labelled_water_the_rule_finds'])} of the water both see.",
        f"The two gave the same label on {percent(readers['share_same_label'])} of all points "
        f"(Cohen's kappa {readers['cohens_kappa']}).",
        f"On the chip that was set aside because it holds no flood, "
        f"{with_interval(alone['a_share_of_rule_water_labelled_water'])} of the area the rule calls water is water to both "
        f"({alone['points_scored']} of {alone['points']} points scored).",
        "Every figure is agreement between a rule and two readers of the same image; nobody went to the ground, and no "
        "radar figure is changed with them.",
    ]


def stage_score(arguments: argparse.Namespace) -> None:
    work = Path(arguments.external_root) / WORK
    out = ROOT / OUTPUT_DIR
    sample_path, result_path = out / SAMPLE_NAME, out / RESULT_NAME
    if not sample_path.exists():
        raise BuildError("no draw of points: run the sample stage first")
    if result_path.exists() and not arguments.replace:
        raise BuildError(f"{result_path} exists; the figures are computed again only with --replace and --reason")
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    key_path = work / KEY_NAME
    if t2.sha256_file(key_path) != sample["key_outside_git"]["sha256"]:
        raise BuildError("the key is not the one the committed draw names")
    key = json.loads(key_path.read_text(encoding="utf-8"))
    points = key["points"]
    ids = [point["id"] for point in points]
    sizes = {(chip, group): int(sample["chips"][chip]["pixels_by_group"][group]) for chip in wl.CHIPS for group in wl.GROUPS}

    files = [Path(path) for path in arguments.labels]
    if len(files) != 2:
        raise BuildError("the plan has two labellers: give two label files")
    raw = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    given = [wl.check_labels(data, sample_id=sample["sample_id"], point_ids=ids) for data in raw]
    names = [str(data["labeller"]).strip() for data in raw]
    if names[0].lower() == names[1].lower():
        raise BuildError("the two label files name the same labeller")

    scorings = {"both_agree": wl.agreed(given[0], given[1]), **{f"{name}_alone": wl.alone(labels) for name, labels in zip(names, given)}}
    sets = {**{chip: (chip,) for chip in wl.CHIPS}, "reference_chips_together": wl.REFERENCE_CHIPS}
    figures = {
        name: {scoring: wl.figures(points, labels, sizes, chips) for scoring, labels in scorings.items()}
        for name, chips in sets.items()
    }
    readers = wl.between_labellers(given[0], given[1])
    readers["order"] = {"first": names[0], "second": names[1]}
    readers["by_chip"] = {}
    for chip in wl.CHIPS:
        mine = [point["id"] for point in points if point["chip"] == chip]
        part = wl.between_labellers({i: given[0][i] for i in mine}, {i: given[1][i] for i in mine})
        readers["by_chip"][chip] = {field: part[field] for field in ("points", "share_same_label", "cohens_kappa")}
    seconds = {
        name: round(statistics.median(float(entry["seconds"]) for entry in data["labels"].values() if isinstance(entry, dict)), 1)
        for name, data in zip(names, raw)
    }

    together = figures["reference_chips_together"]["both_agree"]
    low = [letter for letter, field in (("a", "a_share_of_rule_water_labelled_water"), ("b", "b_share_of_labelled_water_the_rule_finds"))
           if together[field]["estimate"] is not None and together[field]["estimate"] < 0.80]
    copies = {}
    for name, path in zip(names, files):
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        target = out / f"labels_{slug}.json"
        target.write_bytes(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8"))
        copies[name] = {"path": f"{OUTPUT_DIR}/{target.name}", "sha256": t2.sha256_file(target)}
    (out / KEY_NAME).write_bytes(key_path.read_bytes())

    result = {
        "schema": "floodguard.theos2_water_labels.result.v1",
        **envelope(),
        "what_this_is": "How often the THEOS-2 water rule says what two team members say who look at the same image at full "
                        "detail, on 300 points drawn at random in six groups. Agreement between a rule and two readers; no "
                        "ground check.",
        "sample": {"path": f"{OUTPUT_DIR}/{SAMPLE_NAME}", "sha256": t2.sha256_file(sample_path)},
        "key": {"path": f"{OUTPUT_DIR}/{KEY_NAME}", "sha256": t2.sha256_file(out / KEY_NAME)},
        "label_files": copies,
        "scoring_label": "The label both gave, where both gave water or both gave not water. Other points are left out of "
                         "figures a to d and counted; the figures for each labeller alone are given beside.",
        "estimator": "Stratified random sample with the six groups of each chip as strata (Stehman 2014); 95 percent "
                     "intervals by the normal approximation; counts of one group with a Wilson interval. Points left out "
                     "are taken to be missing at random inside their group.",
        "between_the_two_labellers": readers,
        "median_seconds_per_point": seconds,
        "label_counts_by_group": {name: wl.label_counts(points, labels, wl.CHIPS) for name, labels in zip(names, given)},
        "figures": figures,
        "plan_section_7": {
            "sentences": sentences(names, figures["reference_chips_together"], figures["chip_001"], readers),
            "figures_below_0.80_on_the_reference_chips_together": low,
            "consequence": "The documents and the pitch do not call the THEOS-2 water a reference without the figure in the "
                           "same sentence." if low else "None: both figures are at or above 0.80.",
        },
        "limits": LIMITS,
    }
    previous = t2.superseded(result_path, arguments, ("figures", "between_the_two_labellers"), result)
    if previous is not None:
        result["supersedes"] = previous
    t2.write_json(result_path, result)
    print("\n".join(result["plan_section_7"]["sentences"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    stages = parser.add_subparsers(dest="stage", required=True)
    first = stages.add_parser("sample")
    first.add_argument("--theos2-dir", required=True, help="the folder that holds the three THEOS-2 files")
    second = stages.add_parser("score")
    second.add_argument("--labels", nargs=2, required=True, help="the two label files the page wrote")
    for stage in (first, second):
        stage.add_argument("--external-root", required=True)
        stage.add_argument("--replace", action="store_true")
        stage.add_argument("--reason", default="")
    arguments = parser.parse_args()
    {"sample": stage_sample, "score": stage_score}[arguments.stage](arguments)


if __name__ == "__main__":
    main()
