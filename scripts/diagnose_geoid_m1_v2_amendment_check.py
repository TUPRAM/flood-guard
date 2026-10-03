"""Reproduce the development-only check behind amendment 1, and one more reading.

Amendment 1 of the declared benchmark protocol quotes a check of the
Kittler-Illingworth threshold on six development tiles. The code that made
that check was not committed and its output is not in the tuning log. This
script computes the same quantities again, from the 15 development tiles
only, through a tile store in the tuning phase that refuses every held-out
test tile and records what it opened. It then compares each value with the
text of the amendment.

It also scores, on the development tiles only, the proposal's step 4 read
without the "below zero" clause that M1-literal adds.

The script selects nothing, tunes nothing and changes no committed score. It
is run after the held-out scoring, so it shows that the published check can
be recomputed from development tiles and committed code. It cannot show what
was looked at when the amendment was designed.
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
from floodguard import geoid_m1_review as review  # noqa: E402
from floodguard import sar_change_v2 as sar  # noqa: E402

COMPARED_FIELDS = (
    ("selected_blocks", "selected_blocks"),
    ("pooled_fit", "pooled_fit"),
    ("pooled_fit_ashman_d", "pooled_fit_ashman_d"),
    ("ki_threshold_db", "ki_threshold_db_before_amendment_1"),
    ("otsu_threshold_db", "otsu_threshold_db"),
    ("admissible_range_db", "admissible_range_db"),
    ("interior_local_minima_db", "local_minima_between_fitted_modes_db"),
    ("j_at_ki", "j_at_ki_before_amendment_1"),
)


def threshold_step_by_tile(
    filtered: dict[str, sar.FilteredPair], config: sar.M1V2Config
) -> dict[str, dict[str, Any]]:
    """Describe the threshold step of every tile that has a selected block."""

    described: dict[str, dict[str, Any]] = {}
    for name in sorted(filtered, key=lambda item: int(item.rsplit("-", 1)[1])):
        pooled, receipts = sar.select_blocks_for_side(filtered[name], config, "darkening")
        selected = sum(bool(receipt["selected"]) for receipt in receipts)
        if selected == 0:
            described[name] = {"selected_blocks": 0}
            continue
        described[name] = {
            "selected_blocks": selected,
            **review.describe_threshold_step(pooled, config),
        }
    return described


def compare_with_amendment(
    described: dict[str, dict[str, Any]], published: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Compare the recomputed values with the tiles quoted in amendment 1."""

    rows = []
    for entry in published:
        name = bench.tile_name(int(entry["tile"]))
        recomputed = described.get(name, {})
        differences = {
            old: {"amendment_text": entry.get(old), "recomputed": recomputed.get(new)}
            for old, new in COMPARED_FIELDS
            if entry.get(old) != recomputed.get(new)
        }
        rows.append({"tile": name, "matches": not differences, "differences": differences})
    return rows


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
    try:
        binding = review.require_frozen_m1_v2(ROOT)
    except review.GeoidReviewError as error:
        raise SystemExit(str(error)) from error

    protocol_bytes = (ROOT / review.PROTOCOL_FILE).read_bytes()
    amendment = json.loads(protocol_bytes)["amendments"][0]
    published = amendment["development_only_check"]["tiles"]
    first_choice = amendment["what_happened"]["first_session_choice"]["parameters"]
    config = sar.M1V2Config(threshold_method="kittler_illingworth", **first_choice)

    geoid = arguments.external_data / "geoid_flood"
    store = review.RecordingTileStore(
        geoid / "sample" / "sample" / "geoid-flood" / bench.AOI,
        geoid / "metadata" / "SHA256SUMS",
        phase=bench.PHASE_TUNING,
    )
    loaded = bench.load_tiles(store, store.tile_ids(), with_reference=True)
    source_timestamp = max(tile.post_acquired_utc for tile in loaded.inputs.values())

    described = threshold_step_by_tile(loaded.filtered, config)
    comparison = compare_with_amendment(described, published)
    with_threshold = sorted(
        (
            name
            for name, entry in described.items()
            if entry.get("ki_threshold_db_before_amendment_1") is not None
            and entry["ki_threshold_db_before_amendment_1"] > 0
        ),
        key=lambda item: int(item.rsplit("-", 1)[1]),
    )

    # The proposal's step 4 with and without the added "below zero" clause.
    literal_config = sar.M1LiteralConfig()
    counts: dict[str, list[dict[str, int]]] = {"as_implemented": [], "without_zero_clause": []}
    per_tile: dict[str, dict[str, Any]] = {}
    for name in sorted(loaded.inputs, key=lambda item: int(item.rsplit("-", 1)[1])):
        tile = loaded.inputs[name]
        reference = loaded.references[name]
        pair = sar.filter_pair(
            tile.pre,
            tile.post,
            speckle_filter=literal_config.speckle_filter,
            equivalent_looks=literal_config.equivalent_looks,
            window_pixels=literal_config.speckle_window_pixels,
        )
        implemented, detail = sar.m1_literal_from_filtered(pair, literal_config)
        without, _ = review.m1_literal_without_zero_clause(pair, literal_config)
        first = bench.confusion_counts(
            implemented, reference.label, reference.validity, include_permanent_water=True
        )
        second = bench.confusion_counts(
            without, reference.label, reference.validity, include_permanent_water=True
        )
        counts["as_implemented"].append(first)
        counts["without_zero_clause"].append(second)
        per_tile[name] = {
            "otsu_threshold_delta_vh_db": detail["otsu_threshold_delta_vh_db"],
            "iou_as_implemented": bench.metrics_from_counts(first)["strict"]["iou"],
            "iou_without_zero_clause": bench.metrics_from_counts(second)["strict"]["iou"],
        }

    def pooled(rows: list[dict[str, int]]) -> dict[str, Any]:
        metrics = review.pooled_metrics(rows)
        return {
            "iou_strict": metrics["strict"]["iou"],
            "dice_strict": metrics["strict"]["dice"],
            "precision": metrics["covered"]["precision"],
            "recall_strict": metrics["strict"]["recall"],
            "coverage": metrics["coverage"],
            "predicted_to_reference_area_ratio": metrics["predicted_to_reference_area_ratio"],
            "false_positive": metrics["false_positive"],
            "true_positive": metrics["true_positive"],
        }

    summary_path = ROOT / review.SUMMARY_FILE
    committed = json.loads(summary_path.read_bytes())["results"]["m1_literal"]["development"][
        "primary"
    ]
    implemented_pooled = pooled(counts["as_implemented"])
    record = {
        "schema": "floodguard.geoid_m1_v2_amendment_check_reproduction.v1",
        "evidence_tier": "research_benchmark_diagnostic",
        "what_this_is": (
            "A recomputation, after the held-out scoring, of the development-only check "
            "quoted in amendment 1 of the declared benchmark protocol, and of the proposal's "
            "step 4 without the added 'below zero' clause. Development tiles only. Nothing "
            "is selected or tuned and no committed score changes."
        ),
        "limit": (
            "The original check was not committed or logged. This file shows that its "
            "published values can be recomputed from the 15 development tiles and committed "
            "code. It does not show what was looked at when the amendment was designed."
        ),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **review.output_context(source_timestamp),
        "phase": bench.PHASE_TUNING,
        **store.access_record(),
        "frozen_method_binding": {
            "frozen_config_sha256": binding["frozen_config_sha256"],
            "code_sha256": binding["code_sha256"],
            "planning_protocol_v1a_sha256": binding["planning_protocol_v1a_sha256"],
        },
        "declared_benchmark_protocol_sha256": bench.bytes_sha256(protocol_bytes),
        "review_module_sha256": bench.file_sha256(
            ROOT / "src" / "floodguard" / "geoid_m1_review.py"
        ),
        "input_sha256": loaded.input_sha256,
        "amendment_check": {
            "configuration": first_choice,
            "threshold_rule_described": (
                "ki_threshold_db_before_amendment_1 is the lowest admissible value of the "
                "criterion, as the code of the first session returned it. "
                "ki_threshold_db_after_amendment_1 is the interior minimum between the "
                "fitted modes, or null."
            ),
            "tiles_with_a_positive_threshold_before_amendment_1": with_threshold,
            "per_tile": described,
            "comparison_with_amendment_text": comparison,
            "every_published_value_recomputed": all(row["matches"] for row in comparison),
        },
        "m1_literal_step_4_readings": {
            "split": "development",
            "tiles": len(per_tile),
            "as_implemented": {
                "rule": "delta-VH below the Otsu threshold and below zero",
                **implemented_pooled,
                "equals_the_committed_development_score": implemented_pooled["iou_strict"]
                == committed["strict"]["iou"],
            },
            "without_zero_clause": {
                "rule": "delta-VH below the Otsu threshold",
                **pooled(counts["without_zero_clause"]),
            },
            "per_tile": per_tile,
            "meaning": (
                "Not scored on the test tiles: the held-out scoring is computed once. The "
                "reading without the clause is not a candidate for any use."
            ),
        },
        "selects_a_configuration": False,
        "fpps_computed": False,
        "action_class_computed": False,
        "mae_sai_run": False,
        "human_reviewed_by_floodguard": False,
        "accepted_observation": False,
        "official_warning": False,
        "can_feed_decision_layer": False,
    }
    target = ROOT / review.AMENDMENT_CHECK_FILE
    target.write_bytes(bench.canonical_json_bytes(record))
    print(f"wrote {review.AMENDMENT_CHECK_FILE}")
    print(f"tiles opened: {len(store.opened_tile_ids())}; test tiles opened: "
          f"{len(store.opened_test_tile_ids())}")
    for row in comparison:
        print(f"{row['tile']}: {'matches' if row['matches'] else row['differences']}")
    for name, values in record["m1_literal_step_4_readings"].items():
        if isinstance(values, dict) and "iou_strict" in values:
            print(f"M1-literal step 4, {name}: IoU strict={values['iou_strict']} "
                  f"area ratio={values['predicted_to_reference_area_ratio']}")


if __name__ == "__main__":
    main()
