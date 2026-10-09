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

from floodguard import s1_rtc  # noqa: E402

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
    for key, area in areas.items():
        started = time.time()
        _path, record[key] = dry_baseline(external, key, area)
        print(f"{area['name']}: dry-season baseline of {len(area['dry'])} passes, {time.time() - started:.0f} s", flush=True)
    started = time.time()
    record["mae_sai_september_pass"] = s1_rtc.fetch_pass(work, areas["mae_sai"]["grid"], MAE_SAI_SEPTEMBER, "s1_mae_sai_20240915",
                                                         epsg=EPSG, cell_m=CELL_M)
    print(f"Mae Sai, pass of 15 September 2024: {time.time() - started:.0f} s", flush=True)
    t2.write_json(work / "baselines_record.json", {"fetched_at_utc": t2.now_utc(), "areas": record})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    stages = parser.add_subparsers(dest="stage", required=True)
    for name in ("baselines", "develop", "reference", "test"):
        stage = stages.add_parser(name)
        stage.add_argument("--external-root", required=True)
        stage.add_argument("--replace", action="store_true")
        stage.add_argument("--reason", default="")
    arguments = parser.parse_args()
    handlers = {"baselines": stage_baselines}
    if arguments.stage not in handlers:
        raise BuildError(f"stage {arguments.stage} is not written yet")
    handlers[arguments.stage](arguments)


if __name__ == "__main__":
    main()
