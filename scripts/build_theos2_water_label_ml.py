"""Learn a water rule from the labels of the label check, one chip left out at a time, and score it beside rule v2.

Plan: ``docs/proposal_execution/theos2_water_label_ml_plan_v1.md``. One run; a second needs ``--replace --reason``.
Report only, confidence low: a water map of an image is not an observation of a flood and not an official warning.

    python scripts/build_theos2_water_label_ml.py --theos2-dir <folder of the THEOS-2 files> --external-root <external data root>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import theos2_cross_check as cc  # noqa: E402
from floodguard import theos2_water_label_ml as ml  # noqa: E402
from floodguard import theos2_water_labels as wl  # noqa: E402

PLAN = "docs/proposal_execution/theos2_water_label_ml_plan_v1.md"
OUTPUT = "outputs/theos2_water_label_ml/result_v1.json"
LABEL_DIR = "outputs/theos2_water_labels"
LABELLERS = ("callixta", "putu", "rachmania")
SETS = {**{chip: (chip,) for chip in wl.CHIPS}, "reference_chips_together": wl.REFERENCE_CHIPS, "three_chips_together": wl.CHIPS}
DECISION_SET = "three_chips_together"

LIMITS = [
    "All three team members gave the same label on 57% of the points: a model learns the majority's reading, with its mistakes.",
    "Three chips make three folds; a chip is one image of one place on one day.",
    "The points were drawn in groups cut from rule v1. Area weights correct the estimate; they do not put points where rule v1 never looked.",
    "No ground check exists for any of the three chips, and none of them covers Mae Sai.",
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


labels_script = load_script("build_theos2_water_labels")
t2 = labels_script.t2
BuildError = t2.BuildError


def short(figure: dict[str, Any]) -> dict[str, Any]:
    """The figures of a map that the account quotes."""

    return {
        "points_scored": figure["points_scored"],
        "share_answered_and_alike": figure["share_answered_and_alike"],
        "share_of_map_water_labelled_water": figure["a_share_of_map_water_labelled_water"],
        "share_of_labelled_water_the_map_finds": figure["b_share_of_labelled_water_the_map_finds"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--theos2-dir", required=True, help="the folder that holds the three THEOS-2 files")
    parser.add_argument("--external-root", required=True)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--reason", default="")
    arguments = parser.parse_args()
    out = ROOT / OUTPUT
    if out.exists() and not arguments.replace:
        raise BuildError(f"{OUTPUT} exists; the figures are computed again only with --replace and --reason")
    if arguments.replace and not arguments.reason.strip():
        raise BuildError("--replace needs --reason")

    sample = json.loads((ROOT / LABEL_DIR / "sample_v1.json").read_text(encoding="utf-8"))
    key = json.loads((ROOT / LABEL_DIR / "key_v1.json").read_text(encoding="utf-8"))
    points = key["points"]
    ids = [point["id"] for point in points]
    sizes = {(chip, group): int(sample["chips"][chip]["pixels_by_group"][group]) for chip in wl.CHIPS for group in wl.GROUPS}
    label_files = {name: ROOT / LABEL_DIR / f"labels_{name}.json" for name in LABELLERS}
    given = {name: wl.check_labels(json.loads(path.read_text(encoding="utf-8")), sample_id=sample["sample_id"], point_ids=ids)
             for name, path in label_files.items()}
    scoring = wl.majority(list(given.values()))

    # --- features of the points, chip by chip; the groups of the key are checked against rule v1 on the same grid -------------
    matrix = np.zeros((len(points), len(ml.FEATURES)))
    scenes = {}
    for chip in wl.CHIPS:
        scene = Path(arguments.theos2_dir) / labels_script.CHIPS[chip]["file_name"]
        run = labels_script.run_rule(scene, chip)
        image = run["image"]
        mine = [index for index, point in enumerate(points) if point["chip"] == chip]
        rows = [points[index]["row"] for index in mine]
        columns = [points[index]["column"] for index in mine]
        for index in mine:
            point = points[index]
            answer = int(run["water"][point["row"], point["column"]])
            expected = (cc.WATER_YES if point["group"] in wl.WATER_GROUPS else cc.WATER_UNOBSERVABLE if point["group"] == "unobservable" else cc.WATER_NO)
            if answer != expected:
                raise BuildError(f"{point['id']}: the pixel is not in the group the key gives; the grid is not the one of the draw")
        bands = {name: image[t2.THEOS2_BANDS[name] - 1] for name in ("blue", "green", "red", "nir")}
        matrix[mine] = ml.features(bands, rows, columns)
        scenes[chip] = {"file_name": scene.name, "sha256": t2.sha256_file(scene), "points": len(mine)}

    # --- rule v1 and the frozen rule v2 at the points, as the label check read them -------------------------------------------
    import rasterio

    freeze_path = ROOT / labels_script.SECOND_RULE_FREEZE
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    words = {0: wl.NOT_WATER, 1: wl.WATER, 255: wl.UNOBSERVABLE}
    answers_v2: dict[str, str] = {}
    for chip in wl.CHIPS:
        named = freeze["frozen_rule"]["chips"][chip]["raster_outside_git"]
        raster_path = Path(arguments.external_root) / labels_script.SECOND_RULE_WORK / named["name"]
        if t2.sha256_file(raster_path) != named["sha256"]:
            raise BuildError(f"{named['name']} is not the raster the freeze names")
        with rasterio.open(raster_path) as source:
            water = source.read(1)
        for point in points:
            if point["chip"] == chip:
                answers_v2[point["id"]] = words[int(water[point["row"], point["column"]])]
    answers_v1 = wl.answers_of_rule_v1(points)

    # --- the fits: each point counts for the area it stands for (main run), and every point the same (beside it) -------------
    runs = {
        "area_weighted": ml.leave_one_chip_out(points, matrix, scoring, ml.area_weights(points, sizes)),
        "every_point_the_same": ml.leave_one_chip_out(points, matrix, scoring, None),
    }

    def scored(answers: dict[str, str]) -> dict[str, Any]:
        return {
            name: {**short(wl.figures_of_a_map(points, scoring, answers, sizes, chips)),
                   "minus_rule_v2": wl.difference_of_two_maps(points, scoring, answers_v2, answers, sizes, chips)}
            for name, chips in SETS.items()
        }

    rules = {
        "rule_v1": {name: short(wl.figures_of_a_map(points, scoring, answers_v1, sizes, chips)) for name, chips in SETS.items()},
        "rule_v2": {name: short(wl.figures_of_a_map(points, scoring, answers_v2, sizes, chips)) for name, chips in SETS.items()},
    }
    models = {run: {name: scored(result["answers"][name]) for name in ml.MODELS} for run, result in runs.items()}
    verdicts = {name: ml.shown_better(models["area_weighted"][name][DECISION_SET]["minus_rule_v2"]) for name in ml.MODELS}

    # --- each team member against the label the other two agree on: what these labels can show at most ------------------------
    people = {}
    for name in LABELLERS:
        others = wl.agreed(*[given[other] for other in LABELLERS if other != name])
        mine = {point: (label if label in (wl.WATER, wl.NOT_WATER) else wl.UNOBSERVABLE) for point, label in given[name].items()}
        people[name] = {set_name: short(wl.figures_of_a_map(points, others, mine, sizes, chips)) for set_name, chips in SETS.items()}

    previous = None
    if out.exists():
        previous = {"sha256": t2.sha256_file(out), "reason": arguments.reason.strip()}
    result = {
        "schema": "floodguard.theos2_water_label_ml.result.v1",
        "generated_at_utc": t2.now_utc(),
        "source_timestamp": labels_script.SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "Labels by three team members on the image the models read; three chips; no ground check.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "plan": {"path": PLAN, "sha256": t2.sha256_file(ROOT / PLAN)},
        "what_this_is": "Four classifiers fitted on the team's labels of two chips and scored on the third, each chip left out "
                        "once, beside the two hand-written rules on the same 300 points. Agreement with the readers of an image; "
                        "no ground check.",
        "inputs": {
            "sample": {"path": f"{LABEL_DIR}/sample_v1.json", "sha256": t2.sha256_file(ROOT / LABEL_DIR / "sample_v1.json")},
            "key": {"path": f"{LABEL_DIR}/key_v1.json", "sha256": t2.sha256_file(ROOT / LABEL_DIR / "key_v1.json")},
            "labels": {name: {"path": f"{LABEL_DIR}/{path.name}", "sha256": t2.sha256_file(path)} for name, path in label_files.items()},
            "rule_v2_freeze": {"path": labels_script.SECOND_RULE_FREEZE, "sha256": t2.sha256_file(freeze_path)},
            "scenes_outside_git": scenes,
        },
        "scoring_label": "The label at least two of the three gave, where it is water or not water.",
        "points": {"all": len(points), "with_a_scoring_label": sum(1 for value in scoring.values() if value is not None),
                   "labelled_water": sum(1 for value in scoring.values() if value == wl.WATER)},
        "features": list(ml.FEATURES),
        "models": {"one_index": "logistic regression on red_nir_index alone", "logistic": "logistic regression on the twelve features, standardised, C = 1",
                   "forest": "random forest, 500 trees, at least 5 points in a leaf", "boosting": "gradient-boosted trees (histogram), depth 3, 200 rounds, learning rate 0.1",
                   "seed": ml.SEED},
        "folds": runs["area_weighted"]["folds"],
        "rules_on_the_same_points": rules,
        "models_scored": models,
        "decision": {
            "rule": f"A model is called better than rule v2 only if, in the area-weighted run and over the three chips together, its "
                    f"difference with rule v2 is above zero by more than {ml.SHARED_LEVEL_Z} standard errors (95% shared over {ml.COMPARISONS} comparisons).",
            "set": DECISION_SET,
            "shown_better_than_rule_v2": verdicts,
            "rule_that_reads_mae_sai": "rule v2, unchanged",
        },
        "each_team_member_against_the_other_two": people,
        "limits": LIMITS,
        **({"supersedes": previous} if previous else {}),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {OUTPUT}")
    for run, by_model in models.items():
        for name, sets in by_model.items():
            entry = sets[DECISION_SET]
            difference = entry["minus_rule_v2"]
            print(f"{run:22s} {name:10s} alike {entry['share_answered_and_alike']['estimate']:.3f}  minus v2 {difference['estimate']:+.3f} (se {difference['standard_error']:.3f})")
    for name, sets in rules.items():
        print(f"{'':22s} {name:10s} alike {sets[DECISION_SET]['share_answered_and_alike']['estimate']:.3f}")
    print("shown better than rule v2:", verdicts)


if __name__ == "__main__":
    main()
