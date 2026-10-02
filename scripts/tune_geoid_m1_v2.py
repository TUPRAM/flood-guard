"""Tune M1-v2 on the 15 GEOID development tiles and freeze the choice.

Opens development tiles only: the loader refuses every held-out test tile.
Runs the search space declared in geoid_m1_benchmark_protocol_v2.json, logs
every run, then writes the frozen configuration and its receipt. Commit the
log, the configuration and the receipt before any held-out scoring.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import geoid_m1_benchmark as bench  # noqa: E402
from floodguard import sar_change_v2 as sar  # noqa: E402

TRACK = ROOT / "docs" / "proposal_execution" / "automated_track"
PROTOCOL = TRACK / "geoid_m1_benchmark_protocol_v2.json"
TUNING_LOG = TRACK / "geoid_m1_v2_tuning_log.jsonl"
FROZEN_CONFIG = TRACK / "geoid_m1_v2_frozen_config.json"
FREEZE_RECEIPT = TRACK / "geoid_m1_v2_freeze_receipt.json"
CODE_FILES = ("src/floodguard/sar_change_v2.py", "src/floodguard/geoid_m1_benchmark.py")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_log(record: dict[str, Any]) -> None:
    line = json.dumps(record, sort_keys=True, ensure_ascii=True, allow_nan=False)
    with TUNING_LOG.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--external-data",
        type=Path,
        default=Path(os.environ["FLOODGUARD_EXTERNAL_DATA"])
        if os.environ.get("FLOODGUARD_EXTERNAL_DATA")
        else None,
        help="External data root (default: FLOODGUARD_EXTERNAL_DATA).",
    )
    parser.add_argument(
        "--protocol-v1a",
        type=Path,
        default=None,
        help="Optional path to planning_protocol_v1a.json, to check its hash and split.",
    )
    parser.add_argument(
        "--note", default="", help="Why this tuning session is run (kept in the log)."
    )
    arguments = parser.parse_args()
    if arguments.external_data is None:
        raise SystemExit("Set FLOODGUARD_EXTERNAL_DATA or pass --external-data")
    if FROZEN_CONFIG.exists() or FREEZE_RECEIPT.exists():
        raise SystemExit("A frozen configuration already exists; tuning is closed")

    protocol_bytes = PROTOCOL.read_bytes()
    protocol = json.loads(protocol_bytes)
    if (
        tuple(protocol["split"]["development_tile_ids"]) != bench.DEVELOPMENT_TILE_IDS
        or tuple(protocol["split"]["test_tile_ids"]) != bench.TEST_TILE_IDS
        or protocol["planning_protocol_v1a_sha256"] != bench.PROTOCOL_V1A_SHA256
    ):
        raise SystemExit("The declared benchmark protocol and the code disagree on the split")
    v1a_checked = False
    if arguments.protocol_v1a is not None:
        v1a_bytes = arguments.protocol_v1a.read_bytes()
        if bench.bytes_sha256(v1a_bytes) != bench.PROTOCOL_V1A_SHA256:
            raise SystemExit("planning_protocol_v1a.json does not have the signed SHA-256")
        bench.verify_split_against_protocol(json.loads(v1a_bytes))
        v1a_checked = True
    grid = bench.expand_search_space(protocol["m1_v2"]["search_space"]["dimensions"])
    if len(grid) != protocol["m1_v2"]["search_space"]["runs"]:
        raise SystemExit("The search space does not have the declared number of runs")

    geoid = arguments.external_data / "geoid_flood"
    store = bench.GeoidTileStore(
        geoid / "sample" / "sample" / "geoid-flood" / bench.AOI,
        geoid / "metadata" / "SHA256SUMS",
        phase=bench.PHASE_TUNING,
    )
    code_sha256 = {name: bench.file_sha256(ROOT / name) for name in CODE_FILES}
    session = now_utc()
    loaded = bench.load_tiles(store, store.tile_ids(), with_reference=True)
    source_timestamp = max(tile.post_acquired_utc for tile in loaded.inputs.values())
    append_log(
        {
            "record": "session_start",
            "session_started_utc": session,
            "note": arguments.note,
            "phase": bench.PHASE_TUNING,
            "tiles_opened": sorted(loaded.filtered),
            "test_tiles_opened": [],
            "declared_benchmark_protocol_sha256": bench.bytes_sha256(protocol_bytes),
            "planning_protocol_v1a_sha256": bench.PROTOCOL_V1A_SHA256,
            "planning_protocol_v1a_file_checked": v1a_checked,
            "code_sha256": code_sha256,
            "input_sha256": loaded.input_sha256,
            "source_timestamp": source_timestamp,
            "runs_declared": len(grid),
        }
    )
    runs: list[dict[str, Any]] = []
    for record in bench.tuning_runs(loaded.filtered, loaded.references, grid):
        record = {
            "run_id": f"{session}-run-{record['run_index']:02d}",
            "logged_utc": now_utc(),
            **record,
        }
        append_log(record)
        runs.append(record)
        print(
            f"{record['run_id']} {record['parameters']} "
            f"IoU strict={record['development_iou_strict']} "
            f"covered={record['development_iou_covered']} "
            f"coverage={record['development_coverage']} "
            f"abstained tiles={record['development_abstained_tiles']} "
            f"otsu={record['otsu_comparator_development_iou_strict']}",
            flush=True,
        )

    chosen = bench.select_run(runs)
    config = sar.M1V2Config(threshold_method="kittler_illingworth", **chosen["parameters"])
    frozen_at = now_utc()
    frozen = {
        "schema": "floodguard.geoid_m1_v2_frozen_config.v1",
        "method": "m1_v2",
        "version": "m1_v2_geoid_slope_free_1",
        "parameters": sar.config_to_json(config),
        "tuned_fields": list(protocol["m1_v2"]["search_space"]["dimensions"]),
        "otsu_comparator": "same parameters with threshold_method otsu; reported, never selected",
        "selected_run_id": chosen["run_id"],
        "selection_rule": protocol["m1_v2"]["selection_rule"]["score"],
        "development": {
            "tiles": len(loaded.filtered),
            "iou_strict": chosen["development_iou_strict"],
            "iou_covered": chosen["development_iou_covered"],
            "precision": chosen["development_precision"],
            "recall_strict": chosen["development_recall_strict"],
            "coverage": chosen["development_coverage"],
            "abstained_tiles": chosen["development_abstained_tiles"],
            "wording": bench.AGREEMENT_WORDING,
        },
        "declared_benchmark_protocol_sha256": bench.bytes_sha256(protocol_bytes),
        "planning_protocol_v1a_sha256": bench.PROTOCOL_V1A_SHA256,
        "slope_mask": "none: no DEM for these tiles is on disk (plan A3)",
        "land_cover_stratification": "none: no land-cover layer for these tiles is on disk",
        "source_timestamp": source_timestamp,
        "frozen_at_utc": frozen_at,
        "confidence": (
            "low: a research benchmark on one foreign event; the development score is "
            + bench.AGREEMENT_WORDING
        ),
        "assumptions": [
            "GEOID S1GRD tiles are linear sigma0 at 10 m with about 4.4 equivalent looks.",
            "Mapped background in the CEMS-derived label is not confirmed dry land.",
            "The development tiles are representative enough of the test tiles to choose on.",
        ],
        "official_warning": False,
        "can_feed_decision_layer": False,
    }
    frozen_bytes = bench.canonical_json_bytes(frozen)
    FROZEN_CONFIG.write_bytes(frozen_bytes)
    append_log(
        {
            "record": "selection",
            "session_started_utc": session,
            "selected_run_id": chosen["run_id"],
            "selected_parameters": chosen["parameters"],
            "runs_completed": len(runs),
            "frozen_config_sha256": bench.bytes_sha256(frozen_bytes),
            "selected_utc": frozen_at,
        }
    )
    receipt = bench.build_freeze_receipt(
        frozen_config_sha256=bench.bytes_sha256(frozen_bytes),
        declared_protocol_sha256=bench.bytes_sha256(protocol_bytes),
        tuning_log_sha256=bench.file_sha256(TUNING_LOG),
        code_sha256=code_sha256,
        selected_run_id=chosen["run_id"],
        frozen_at_utc=frozen_at,
    )
    FREEZE_RECEIPT.write_bytes(bench.canonical_json_bytes(receipt))
    print(f"frozen {chosen['run_id']} {chosen['parameters']}")
    print(f"frozen config SHA-256 {receipt['frozen_config_sha256']}")


if __name__ == "__main__":
    main()
