"""Score M1-literal and the frozen M1-v2 on the GEOID tiles, once.

Runs only after the frozen configuration, its receipt, the tuning log, the
declared benchmark protocol and the two code modules are committed and
unchanged. M1-literal is run once on all 29 tiles and reported by split.
M1-v2 is run with the frozen configuration on the development tiles (to
confirm the tuning log) and on the 14 held-out test tiles. The script refuses
to run again once its summary exists.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import geoid_m1_benchmark as bench  # noqa: E402
from floodguard import sar_change_v2 as sar  # noqa: E402

TRACK = "docs/proposal_execution/automated_track"
PROTOCOL = f"{TRACK}/geoid_m1_benchmark_protocol_v2.json"
TUNING_LOG = f"{TRACK}/geoid_m1_v2_tuning_log.jsonl"
FROZEN_CONFIG = f"{TRACK}/geoid_m1_v2_frozen_config.json"
FREEZE_RECEIPT = f"{TRACK}/geoid_m1_v2_freeze_receipt.json"
CODE_FILES = ("src/floodguard/sar_change_v2.py", "src/floodguard/geoid_m1_benchmark.py")
SUMMARY = "outputs/geoid_m1_benchmark_v2_summary.json"


def git(*arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments], cwd=ROOT, check=True, capture_output=True
    ).stdout


def committed_bytes(relative: str) -> bytes:
    """Bytes of a file, after checking they equal the version committed at HEAD."""

    working = (ROOT / relative).read_bytes()
    try:
        committed = git("show", f"HEAD:{relative}")
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Not committed at HEAD: {relative}") from error
    if working != committed:
        raise SystemExit(f"Working file differs from the committed version: {relative}")
    return working


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
    arguments = parser.parse_args()
    if arguments.external_data is None:
        raise SystemExit("Set FLOODGUARD_EXTERNAL_DATA or pass --external-data")
    summary_path = ROOT / SUMMARY
    if summary_path.exists():
        raise SystemExit("The held-out score already exists; it is computed once")

    protocol_bytes = committed_bytes(PROTOCOL)
    frozen_bytes = committed_bytes(FROZEN_CONFIG)
    receipt_bytes = committed_bytes(FREEZE_RECEIPT)
    log_bytes = committed_bytes(TUNING_LOG)
    code_bytes = {name: committed_bytes(name) for name in CODE_FILES}
    try:
        bench.verify_freeze_receipt(
            json.loads(receipt_bytes),
            frozen_config_bytes=frozen_bytes,
            declared_protocol_bytes=protocol_bytes,
            tuning_log_bytes=log_bytes,
            code_bytes=code_bytes,
        )
    except bench.GeoidBenchmarkError as error:
        raise SystemExit(str(error)) from error
    freeze_commit = git("log", "-1", "--format=%H", "--", FREEZE_RECEIPT).decode().strip()
    head_commit = git("rev-parse", "HEAD").decode().strip()
    frozen = json.loads(frozen_bytes)
    config = sar.m1_v2_config_from_json(frozen["parameters"])
    literal_config = sar.M1LiteralConfig()

    geoid = arguments.external_data / "geoid_flood"
    sums_path = geoid / "metadata" / "SHA256SUMS"
    store = bench.GeoidTileStore(
        geoid / "sample" / "sample" / "geoid-flood" / bench.AOI,
        sums_path,
        phase=bench.PHASE_HELD_OUT_SCORING,
        freeze_commit=freeze_commit,
    )
    rows = []
    input_hashes: dict[str, str] = {}
    for split in bench.SPLITS:
        split_rows, hashes = bench.evaluate_split(
            store, split, literal_config=literal_config, config=config
        )
        rows.extend(split_rows)
        input_hashes.update(hashes)
        print(f"scored the {split} split ({len(split_rows)} tiles)", flush=True)
    results = bench.aggregate_results(rows)

    # The frozen configuration must repeat its logged development score.
    repeated = results["m1_v2_kittler_illingworth"]["development"]["primary"]
    if (
        repeated["strict"]["iou"] != frozen["development"]["iou_strict"]
        or repeated["covered"]["iou"] != frozen["development"]["iou_covered"]
    ):
        raise SystemExit("The frozen configuration does not reproduce its development score")

    test_metrics = results["m1_v2_kittler_illingworth"]["test"]["primary"]
    summary = {
        "schema": "floodguard.geoid_m1_benchmark_summary.v2",
        "evidence_tier": "research_benchmark_diagnostic",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_timestamp": max(row["post_acquired_utc"] for row in rows),
        "confidence": (
            "low: a research benchmark on one foreign event with a spatial split by tile; "
            "every score is " + bench.AGREEMENT_WORDING
        ),
        "assumptions": [
            "GEOID S1GRD tiles are linear sigma0 at 10 m with about 4.4 equivalent looks.",
            "The CEMS-derived label was drawn from the same Sentinel-1 pass as the "
            "post-event input.",
            "Mapped background is not confirmed dry land.",
            "Permanent water in the label is modelled; it is a non-flood class in the "
            "primary comparison and left out of the secondary one.",
            "No DEM, slope, HAND or land-cover layer for these tiles is on disk, so neither "
            "method uses one.",
            "Pre-event and post-event passes are almost four months apart and come from "
            "different orbit directions.",
        ],
        "wording": bench.AGREEMENT_WORDING,
        "required_statement": bench.REQUIRED_STATEMENT,
        "disclosures": json.loads(protocol_bytes)["required_statements"][1:],
        "dataset": {
            "repository": bench.DATASET_REPOSITORY,
            "revision": bench.DATASET_REVISION,
            "aoi_id": bench.AOI,
            "development_tile_ids": list(bench.DEVELOPMENT_TILE_IDS),
            "test_tile_ids": list(bench.TEST_TILE_IDS),
            "published_sha256sums_sha256": bench.file_sha256(sums_path),
            "input_sha256": dict(sorted(input_hashes.items())),
        },
        "provenance": {
            "planning_protocol_v1a_sha256": bench.PROTOCOL_V1A_SHA256,
            "declared_benchmark_protocol_sha256": bench.bytes_sha256(protocol_bytes),
            "frozen_config_sha256": bench.bytes_sha256(frozen_bytes),
            "freeze_receipt_sha256": bench.bytes_sha256(receipt_bytes),
            "tuning_log_sha256": bench.bytes_sha256(log_bytes),
            "code_sha256": {name: bench.bytes_sha256(data) for name, data in code_bytes.items()},
            "freeze_commit": freeze_commit,
            "scored_at_commit": head_commit,
        },
        "m1_literal_configuration": sar.config_to_json(literal_config),
        "m1_v2_frozen_parameters": frozen["parameters"],
        "results": results,
        "per_tile": rows,
        "t2_skill_bar": {
            "source": "planning protocol v1a, t2_skill_bar",
            "geoid_held_out_test_iou_min": bench.T2_SKILL_BAR_TEST_IOU_MIN,
            "m1_v2_test_iou_covered": test_metrics["covered"]["iou"],
            "m1_v2_test_iou_strict": test_metrics["strict"]["iou"],
            "m1_v2_reaches_the_geoid_condition": bench.clears_skill_bar(test_metrics),
            "reading": "Both readings (covered and strict) must reach the minimum.",
            "not_assessed_here": [
                "Mae Sai abstention at most 0.20",
                "Mae Sai unit coverage at least 0.80",
                "3-day recency window",
            ],
            "m1_literal": "declared unable to meet the bar by protocol v1a, whatever it scores",
            "meaning": "One of four conditions, on one foreign event. Not a validation.",
        },
        "fpps_computed": False,
        "action_class_computed": False,
        "mae_sai_run": False,
        "human_reviewed_by_floodguard": False,
        "accepted_observation": False,
        "official_warning": False,
        "can_feed_decision_layer": False,
    }
    summary_path.write_bytes(bench.canonical_json_bytes(summary))
    print(f"wrote {SUMMARY}")
    for method in bench.METHODS:
        for split in bench.SPLITS:
            primary = results[method][split]["primary"]
            print(
                f"{method} {split}: IoU strict={primary['strict']['iou']} "
                f"covered={primary['covered']['iou']} "
                f"precision={primary['covered']['precision']} "
                f"recall strict={primary['strict']['recall']} coverage={primary['coverage']} "
                f"abstained tiles={results[method][split]['abstained_tiles']}"
            )


if __name__ == "__main__":
    main()
