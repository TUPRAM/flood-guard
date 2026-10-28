"""Report-only reason counts of the Nan case, counted after the test (figures only).

What M1-z did, by its frozen reason band (``reason_central``), with three sets of cells:

- JAXA's water of 2025-07-28 on the compared cells of test 1 of record (Sentinel-1C pass of 2025-07-28), with the
  HAND of those cells;
- the answered cells of the dry chip ``nan_chip_001`` on the Sentinel-1A pass of 2025-07-31 (the dry control of the
  first run) and on the Sentinel-1C pass of 2025-07-28;
- the THEOS-2 rule v2 water of the Wiang Sa chip ``nan_chip_003`` on the compared cells of test 2 (pass of
  2025-07-31).

The script imports the frozen ``scripts/nan_case_method.py`` and ``src/floodguard/m1z.py`` unchanged and only reads
the work folder. Each set is checked against the totals of its test record before anything is written. The record
holds counts and shares only: no raster, map or per-tambon figure. It binds nothing and changes no test.

Run from the repository root with PYTHONPATH=src:
    python scripts/nan_case_post_test_reasons.py --external-root <root> [--write]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from floodguard import m1z

ROOT = Path(__file__).resolve().parents[1]
TEST_1 = "outputs/nan_case/test_1_jaxa_v1.json"
FIRST_RUN = "outputs/nan_case/test_result_v1.json"
TARGET = "outputs/nan_case/post_test_reasons_v1.json"
TEST_1_MAP = "m1z_20250728T1120_o99_S1C.tif"
FIRST_RUN_MAP = "m1z_20250731T2308_o62_S1A.tif"
JAXA_RASTER = "reference_test_1_jaxa_20250728.tif"
HAND_LIMIT_M = 5.0


def sha256_file(path: Path) -> str:
    """The SHA-256 of a file's bytes."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def reason_counts(reason: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    """Counts and shares of M1-z's reason codes on the cells of ``mask``.

    Labels come from ``m1z.REASON_LABELS``; shares are of the cells of ``mask`` and are rounded to six places.
    """

    values = np.asarray(reason)[np.asarray(mask, dtype=bool)]
    total = int(values.size)
    codes, counts = np.unique(values, return_counts=True)
    by_reason = {m1z.REASON_LABELS.get(int(code), f"code_{int(code)}"): int(count) for code, count in zip(codes, counts)}
    shares = {name: (round(count / total, 6) if total else None) for name, count in by_reason.items()}
    return {"cells": total, "counts": by_reason, "shares": shares}


def radar_and_terrain(counts: Mapping[str, int]) -> dict[str, int]:
    """Cells answered by terrain, cells the radar decided, and cells without an answer, from ``reason_counts``."""

    terrain = sum(counts.get(name, 0) for name in ("not_flagged_terrain_hand_above_the_limit",
                                                    "not_flagged_terrain_slope_5_degrees_or_more"))
    radar = sum(counts.get(name, 0) for name in ("flagged", "not_flagged_radar_dry",
                                                  "not_flagged_group_of_fewer_than_2_cells_dropped"))
    no_answer = sum(value for name, value in counts.items() if name.startswith("no_answer"))
    return {"answered_by_terrain": terrain, "decided_by_the_radar": radar, "no_answer": no_answer}


def load_method(root: Path) -> Any:
    """The frozen method module, imported unchanged."""

    spec = importlib.util.spec_from_file_location("nan_case_method", root / "scripts" / "nan_case_method.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["nan_case_method"] = module
    spec.loader.exec_module(module)
    return module


def read_map(path: Path, method: Any) -> tuple[np.ndarray, np.ndarray]:
    """The central code and central reason bands of a maps-stage map."""

    import rasterio

    with rasterio.open(path) as source:
        code = source.read(method.band_index(source, "code_central", 2))
        reason = source.read(method.band_index(source, "reason_central", 4))
    return code, reason


def require(condition: bool, text: str) -> None:
    if not condition:
        raise SystemExit(f"check failed: {text}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    external = args.external_root
    method = load_method(ROOT)
    import rasterio

    test_1 = json.loads((ROOT / TEST_1).read_text(encoding="utf-8"))
    first = json.loads((ROOT / FIRST_RUN).read_text(encoding="utf-8"))
    protocol = method.read_json(ROOT / method.PROTOCOL)
    areas = method.read_json(ROOT / method.AREAS)
    grid = method.area_grid(areas, method.FRAME_AREA)
    terrain = method.load_terrain(external, [method.FRAME_AREA], grid, "test")
    units, _ = method.frame_units_mask(external / method.BOUNDARIES, grid, protocol["frame"]["district_pcodes"])
    permanent = terrain["permanent_water"]
    frame_land = units & ~permanent
    del units

    maps = external / method.MAPS
    test_map, first_map = maps / TEST_1_MAP, maps / FIRST_RUN_MAP
    require(sha256_file(test_map) == test_1["binding"]["flood_input_of_case_N1"]["map"]["sha256"], "test 1 map bytes")
    jaxa_path = external / method.CASE_N2_REFERENCE / JAXA_RASTER
    require(sha256_file(jaxa_path) == test_1["binding"]["reference_of_case_N2"]["sha256"], "JAXA raster bytes")

    # --- test 1: JAXA water on the compared cells ---------------------------------------------------------------
    with rasterio.open(jaxa_path) as source:
        jaxa = source.read(1)
    compared = frame_land & (jaxa != 255)
    water = compared & (jaxa == 1)
    del jaxa
    central = test_1["test_1"]["central"]
    require(int(compared.sum()) == central["compared_cells"], "test 1 compared cells")
    require(int(water.sum()) == central["reference_water_cells"], "test 1 JAXA water cells")
    code, reason = read_map(test_map, method)
    require(int((water & (code == m1z.FLAGGED)).sum()) == central["true_positive"], "test 1 flagged JAXA water")
    on_jaxa = reason_counts(reason, water)
    hand = terrain["hand"][water]
    hand = hand[np.isfinite(hand)]
    test_1_block = {
        "pass": test_1["test_1"]["pass"]["label"],
        "map": {"name": TEST_1_MAP, "sha256": sha256_file(test_map)},
        "which_cells": "JAXA FLDEXT water of 2025-07-28 on the compared cells of test 1 of record",
        "reasons_on_jaxa_water": on_jaxa,
        "reasons_on_jaxa_water_by_kind": radar_and_terrain(on_jaxa["counts"]),
        "hand_on_jaxa_water": {"cells_with_a_value": int(hand.size),
                               "share_above_the_limit": round(float((hand > HAND_LIMIT_M).mean()), 6) if hand.size else None,
                               "median_m": round(float(np.median(hand)), 2) if hand.size else None,
                               "limit_m": HAND_LIMIT_M},
    }
    dry_window = m1z.centre_window(grid, protocol["grid"]["chips"][method.CHIP_DRY])
    dry_answered = np.isin(code[dry_window], (m1z.FLAGGED, m1z.NOT_FLAGGED)) & ~permanent[dry_window]
    dry_on_test_1_pass = reason_counts(reason[dry_window], dry_answered)
    require(dry_on_test_1_pass["cells"] == test_1["dry_chip_report_only_on_the_test_1_pass"]["central"]["answered_cells"],
            "dry chip answered cells, 28 July")
    del code, reason, water, compared, hand

    # --- first run: dry chip and test 2 on the 31 July pass -----------------------------------------------------
    require(sha256_file(first_map) == "c22c11c2d40118f470e2cc8176221d2cb2db78131b8dd427b31317fdcb849adb", "31 July map bytes")
    code, reason = read_map(first_map, method)
    dry_answered = np.isin(code[dry_window], (m1z.FLAGGED, m1z.NOT_FLAGGED)) & ~permanent[dry_window]
    dry_on_first_pass = reason_counts(reason[dry_window], dry_answered)
    require(dry_on_first_pass["cells"] == first["dry_control"]["central"]["answered_cells"], "dry chip answered cells, 31 July")
    require(dry_on_first_pass["counts"].get("flagged", 0) == first["dry_control"]["central"]["flagged_cells"], "dry chip flags")
    town, window, _ = method.chip_reference(external, ROOT, method.CHIP_TOWN, grid, protocol)
    town_water, town_compared = m1z.reference_cells(town, exclude=permanent[window])
    require(int(town_water.sum()) == first["test_2"]["central"]["reference_water_cells"], "test 2 water cells")
    on_town_water = reason_counts(reason[window], town_water)
    require(on_town_water["counts"].get("flagged", 0) == first["test_2"]["central"]["true_positive"], "test 2 flagged water")
    del code, reason, terrain

    record = {
        "schema": "floodguard.nan_case_post_test_reasons.v1",
        "case_id": "nan_case_v1",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_timestamp": "Nan passes 2025-07-28T11:20:49Z (Sentinel-1C) and 2025-07-31T23:08:03Z (Sentinel-1A); JAXA ALOS-2 map "
                            "of 2025-07-28 (its files give no time with a zone); THEOS-2 2025-07-31",
        "confidence_class": "low",
        "confidence_basis": "Counts of the frozen map's own reason codes on one event; the references are other maps, not ground checks.",
        "report_only": True,
        "binds_nothing": True,
        "counted_after_the_test": True,
        "official_warning": False,
        "operational_status": "non_operational",
        "what_this_is": "Why M1-z flags or does not flag the cells of three reference sets, by its frozen reason band, counted after "
                        "test 1 of record and the first run. Figures only.",
        "assumptions": [
            "The reason band is reason_central of the maps-stage map; terrain reasons are the same at the three levels.",
            "Compared cells, the dry chip's answered cells and test 2's water are formed by the frozen code exactly as in the test "
            "records, and each count is checked against its record before this file is written.",
            "HAND is the terrain lane's HAND of the frame (from Copernicus DEM GLO-30, a surface model); cells without a value are left out.",
        ],
        "read_from": {
            "test_1_of_record": {"path": TEST_1, "sha256": sha256_file(ROOT / TEST_1)},
            "first_run": {"path": FIRST_RUN, "sha256": sha256_file(ROOT / FIRST_RUN)},
            "frozen_code": {"src/floodguard/m1z.py": sha256_file(ROOT / "src" / "floodguard" / "m1z.py"),
                            "scripts/nan_case_method.py": sha256_file(ROOT / "scripts" / "nan_case_method.py")},
            "this_script": {"path": "scripts/nan_case_post_test_reasons.py", "sha256": sha256_file(Path(__file__))},
        },
        "test_1_jaxa_water": test_1_block,
        "dry_chip": {
            "chip": method.CHIP_DRY,
            "which_cells": "answered cells of the chip, permanent water left out (the dry control's cells)",
            "first_run_pass_20250731T2308_o62_S1A": {**reason_counts_with_kind(dry_on_first_pass),
                                                    "map": {"name": FIRST_RUN_MAP, "sha256": sha256_file(first_map)}},
            "test_1_pass_20250728T1120_o99_S1C": reason_counts_with_kind(dry_on_test_1_pass),
            "note": "The radar decides only the cells terrain does not answer; the flagged share of the cells the radar decided is given beside the dry control's share of all answered cells.",
        },
        "test_2_theos2_water": {
            "chip": method.CHIP_TOWN,
            "which_cells": "THEOS-2 rule v2 water on the compared cells of test 2 (permanent water left out)",
            "pass": first["test_2"]["pass"]["label"],
            **reason_counts_with_kind(on_town_water),
        },
        "rights_note": "Counts and shares only; no JAXA- or GFM-derived raster, map or per-tambon table. JAXA map: Provided by JAXA (Sentinel Asia).",
        "words": "Agreement with other maps and reason codes of our own map, counted after the test; report only.",
    }
    text = json.dumps(record, ensure_ascii=False, indent=1) + "\n"
    if args.write:
        (ROOT / TARGET).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {TARGET}")
    else:
        print(text)
    return 0


def reason_counts_with_kind(block: Mapping[str, Any]) -> dict[str, Any]:
    """``reason_counts`` output with the terrain, radar and no-answer totals and the radar's flagged share beside it."""

    kind = radar_and_terrain(block["counts"])
    flagged = block["counts"].get("flagged", 0)
    radar = kind["decided_by_the_radar"]
    return {**block, "by_kind": kind,
            "flagged_share_of_cells_the_radar_decided": round(flagged / radar, 6) if radar else None,
            "terrain_share": round(kind["answered_by_terrain"] / block["cells"], 6) if block["cells"] else None}


if __name__ == "__main__":
    raise SystemExit(main())
