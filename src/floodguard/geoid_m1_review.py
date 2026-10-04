"""Review addendum for the GEOID M1 benchmark (plan task A3).

Written after the held-out scoring, in answer to a review of 3 October 2026.
Nothing here changes the frozen configuration, the two method modules bound
by the freeze receipt, or any committed score. The module adds:

* checks of the held-out score that need no tile access: they read the
  per-tile counts of the committed summary (leave one tile out, a tile
  bootstrap, what the declined tiles hold, the Otsu comparator across the
  declared grid, the sign of the M1-literal threshold);
* a tile store that records which tiles it opened;
* a description of the threshold step on one histogram, to reproduce the
  development-only check behind amendment 1;
* the proposal's step 4 read without the added "below zero" clause, for the
  development tiles only;
* a guard that a later lane calls before it uses the frozen M1-v2.

Every score is agreement with a same-pass CEMS map, not independent
accuracy. Nothing in this module computes a priority score or an action
class, and nothing here selects or changes a configuration.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from floodguard import geoid_m1_benchmark as bench
from floodguard import sar_change_v2 as sar

REVIEW_DATE: str = "2026-10-03"
FROZEN_METHOD: str = "m1_v2_kittler_illingworth"

BOOTSTRAP_RESAMPLES: int = 20000
BOOTSTRAP_SEED: int = 20261003
BOOTSTRAP_LEVEL: float = 0.95

TRACK: str = "docs/proposal_execution/automated_track"
PROTOCOL_FILE: str = f"{TRACK}/geoid_m1_benchmark_protocol_v2.json"
TUNING_LOG_FILE: str = f"{TRACK}/geoid_m1_v2_tuning_log.jsonl"
FROZEN_CONFIG_FILE: str = f"{TRACK}/geoid_m1_v2_frozen_config.json"
FREEZE_RECEIPT_FILE: str = f"{TRACK}/geoid_m1_v2_freeze_receipt.json"
ADDENDUM_FILE: str = f"{TRACK}/geoid_m1_benchmark_v2_addendum_1.json"
SUMMARY_FILE: str = "outputs/geoid_m1_benchmark_v2_summary.json"
DERIVED_CHECKS_FILE: str = "outputs/geoid_m1_benchmark_v2_derived_checks.json"
AMENDMENT_CHECK_FILE: str = "outputs/geoid_m1_v2_amendment_check_reproduction.json"
CODE_FILES: tuple[str, ...] = (
    "src/floodguard/sar_change_v2.py",
    "src/floodguard/geoid_m1_benchmark.py",
)

# Fields of the frozen configuration that the frozen code never reads
# (labels), or does not read on the benchmark path (the tile loader names the
# filter and the looks itself). The values are what the frozen code does.
LABEL_ONLY_CONFIG_FIELDS: dict[str, Any] = {
    "kittler_illingworth_rule": "interior_minimum_between_fitted_modes",
    "isolated_speckle_cleaning": "majority_3x3_at_least_5_of_9",
    "speckle_filter": "refined_lee_7x7",
    "equivalent_looks": sar.SENTINEL1_IW_GRDH_LOOKS,
}

BENCHMARK_ASSUMPTIONS: tuple[str, ...] = (
    "GEOID S1GRD tiles are linear sigma0 at 10 m with about 4.4 equivalent looks.",
    "The CEMS-derived label was drawn from the same Sentinel-1 pass as the post-event input.",
    "Mapped background is not confirmed dry land.",
    "Permanent water in the label is modelled; it is a non-flood class in the primary "
    "comparison and left out of the secondary one.",
    "No DEM, slope, HAND or land-cover layer for these tiles is on disk, so neither method "
    "uses one.",
    "Pre-event and post-event passes are almost four months apart and come from different "
    "orbit directions.",
)

ROBUSTNESS_ASSUMPTIONS: tuple[str, ...] = (
    "The tile is the resampling unit. Tiles of one activation share an event, a pass and a "
    "mapping team, and neighbouring tiles are not independent, so the bootstrap range is "
    "more likely too narrow than too wide.",
    "Fourteen tiles are few for a percentile bootstrap; the range is a description of how "
    "much the score depends on single tiles, not a confidence interval with a guaranteed "
    "coverage.",
    "The checks were added after the held-out score had been seen. They change no score "
    "and are not part of the declared protocol.",
)


class GeoidReviewError(ValueError):
    """The committed artefacts cannot support a review check."""


# ---------------------------------------------------------------------------
# Output context
# ---------------------------------------------------------------------------


def output_context(source_timestamp: str) -> dict[str, Any]:
    """Source timestamp, confidence, assumptions and wording of a benchmark output.

    Every record a benchmark script writes carries these four fields, so a
    figure quoted alone still says what it is.
    """

    return {
        "source_timestamp": source_timestamp,
        "confidence": (
            "low: a research benchmark on one foreign event with a spatial split by tile; "
            "every score is " + bench.AGREEMENT_WORDING
        ),
        "assumptions": list(BENCHMARK_ASSUMPTIONS),
        "wording": bench.AGREEMENT_WORDING,
    }


# ---------------------------------------------------------------------------
# A tile store that records what it opened
# ---------------------------------------------------------------------------


class RecordingTileStore(bench.GeoidTileStore):
    """A tile store that keeps the numbers of the tiles it opened.

    A tile counts as opened as soon as the access rule lets a read start,
    whether or not the read then succeeds. A refused request is kept too. The
    record covers reads made through this store only: a raster read that goes
    around the store is not seen by it.
    """

    def __init__(self, *arguments: Any, **keywords: Any) -> None:
        super().__init__(*arguments, **keywords)
        self._opened: set[int] = set()
        self._refused: set[int] = set()

    def _admit(self, tile_id: int) -> None:
        try:
            bench.require_access(tile_id, self._phase, self._freeze_commit)
        except bench.TestTileAccessRefused:
            self._refused.add(int(tile_id))
            raise
        self._opened.add(int(tile_id))

    def read_inputs(self, tile_id: int) -> bench.TileInputs:
        """Read a permitted tile's radar inputs and record the tile number."""

        self._admit(tile_id)
        return super().read_inputs(tile_id)

    def read_reference(self, tile_id: int) -> bench.TileReference:
        """Read a permitted tile's label and validity and record the tile number."""

        self._admit(tile_id)
        return super().read_reference(tile_id)

    def opened_tile_ids(self) -> tuple[int, ...]:
        """Tile numbers this store let a read start on, in ascending order."""

        return tuple(sorted(self._opened))

    def opened_test_tile_ids(self) -> tuple[int, ...]:
        """The held-out test tiles among the opened tiles."""

        return tuple(tile for tile in self.opened_tile_ids() if tile in bench.TEST_TILE_IDS)

    def refused_tile_ids(self) -> tuple[int, ...]:
        """Tile numbers this store refused, in ascending order."""

        return tuple(sorted(self._refused))

    def access_record(self) -> dict[str, Any]:
        """The opened and refused tiles as published tile names."""

        return {
            "tiles_opened": [bench.tile_name(tile) for tile in self.opened_tile_ids()],
            "test_tiles_opened": [bench.tile_name(tile) for tile in self.opened_test_tile_ids()],
            "tiles_refused": [bench.tile_name(tile) for tile in self.refused_tile_ids()],
            "access_record_scope": (
                "Tiles read through the tile store of this run. A raster read that goes "
                "around the store is not recorded."
            ),
        }


# ---------------------------------------------------------------------------
# Robustness of a pooled score, from per-tile counts
# ---------------------------------------------------------------------------


def _tile_number(name: str) -> int:
    return int(name.rsplit("-", 1)[1])


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def tile_counts(
    summary: Mapping[str, Any], method: str, split: str, comparison: str = "primary"
) -> dict[str, dict[str, int]]:
    """Per-tile confusion counts of one method and split, as committed in the summary."""

    rows = [row for row in summary["per_tile"] if row["split"] == split]
    if not rows:
        raise GeoidReviewError(f"The summary has no tile of the {split} split")
    return {
        row["tile"]: {key: int(row["methods"][method][comparison][key]) for key in bench.COUNT_KEYS}
        for row in sorted(rows, key=lambda item: _tile_number(item["tile"]))
    }


def pooled_metrics(counts: Sequence[Mapping[str, int]]) -> dict[str, Any]:
    """Pool counts over tiles, then compute the scores (never the reverse)."""

    return bench.metrics_from_counts(bench.sum_counts(counts))


def leave_one_tile_out(
    counts_by_tile: Mapping[str, Mapping[str, int]], *, minimum: float
) -> dict[str, Any]:
    """Pooled score with each tile left out in turn.

    Shows how much of a pooled score rests on a single tile. ``minimum`` is
    the bar both readings are compared with.
    """

    if len(counts_by_tile) < 2:
        raise GeoidReviewError("Leaving one tile out needs at least two tiles")
    rows: list[dict[str, Any]] = []
    for name in sorted(counts_by_tile, key=_tile_number):
        rest = [counts for other, counts in counts_by_tile.items() if other != name]
        metrics = pooled_metrics(rest)
        rows.append(
            {
                "tile_left_out": name,
                "tile_was_declined": int(counts_by_tile[name]["covered_cells"]) == 0,
                "iou_strict": metrics["strict"]["iou"],
                "iou_covered": metrics["covered"]["iou"],
                "abstained_cell_share": metrics["abstained_cell_share"],
                "both_readings_reach_minimum": bench.clears_skill_bar(metrics),
            }
        )
    defined = [row for row in rows if row["iou_strict"] is not None]
    lowest = min(defined, key=lambda row: row["iou_strict"]) if defined else None
    highest = max(defined, key=lambda row: row["iou_strict"]) if defined else None
    return {
        "rows": rows,
        "lowest_iou_strict": None if lowest is None else lowest["iou_strict"],
        "lowest_iou_strict_tile_left_out": None if lowest is None else lowest["tile_left_out"],
        "highest_iou_strict": None if highest is None else highest["iou_strict"],
        "tiles_whose_removal_takes_a_reading_below_minimum": [
            row["tile_left_out"] for row in rows if not row["both_readings_reach_minimum"]
        ],
        "holds_for_every_tile_left_out": all(row["both_readings_reach_minimum"] for row in rows),
    }


def resample_indices(tiles: int, resamples: int, seed: int) -> np.ndarray:
    """Tile indices of every bootstrap resample, shape ``(resamples, tiles)``.

    Drawn with the standard library generator: ``random.Random.random`` is
    documented to return the same sequence for the same seed on every Python
    version, which NumPy's ``Generator`` does not promise.
    """

    if tiles < 1 or resamples < 1:
        raise GeoidReviewError("tiles and resamples must be positive")
    generator = random.Random(seed)
    draws = [min(int(generator.random() * tiles), tiles - 1) for _ in range(resamples * tiles)]
    return np.asarray(draws, dtype="int64").reshape(resamples, tiles)


def tile_bootstrap(
    counts_by_tile: Mapping[str, Mapping[str, int]],
    *,
    minimum: float,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    level: float = BOOTSTRAP_LEVEL,
) -> dict[str, Any]:
    """Percentile range of the pooled IoU when tiles are resampled with replacement.

    Each resample draws as many tiles as the split holds, pools their counts
    and computes both readings. A resample without any covered flood or
    candidate cell has no covered IoU; it is counted as "undefined" and as not
    reaching ``minimum``.
    """

    if not 0 < level < 1:
        raise GeoidReviewError("level must lie between 0 and 1")
    names = sorted(counts_by_tile, key=_tile_number)
    keys = ("true_positive", "false_positive", "false_negative", "abstained_reference_flood_cells")
    table = np.asarray(
        [[int(counts_by_tile[name][key]) for key in keys] for name in names], dtype="int64"
    )
    sums = table[resample_indices(len(names), resamples, seed)].sum(axis=1)
    agreed, false_alarm, missed, missed_declined = (sums[:, column] for column in range(4))
    covered_denominator = agreed + false_alarm + missed
    strict_denominator = covered_denominator + missed_declined
    with np.errstate(divide="ignore", invalid="ignore"):
        covered = np.where(covered_denominator > 0, agreed / covered_denominator, np.nan)
        strict = np.where(strict_denominator > 0, agreed / strict_denominator, np.nan)
    tail = 100.0 * (1.0 - level) / 2.0

    def describe(values: np.ndarray) -> dict[str, Any]:
        defined = values[np.isfinite(values)]
        if defined.size == 0:
            raise GeoidReviewError("No resample has a defined score")
        lower, median, upper = np.percentile(defined, [tail, 50.0, 100.0 - tail])
        return {
            "lower": _rounded(lower),
            "median": _rounded(median),
            "upper": _rounded(upper),
            "undefined_resamples": int(values.size - defined.size),
            "share_of_resamples_at_or_above_minimum": _rounded(
                float((defined >= minimum).sum()) / values.size
            ),
        }

    with np.errstate(invalid="ignore"):
        both = (
            np.isfinite(strict)
            & np.isfinite(covered)
            & (strict >= minimum)
            & (covered >= minimum)
        )
    strict_range = describe(strict)
    return {
        "unit": "tile, resampled with replacement",
        "tiles": len(names),
        "resamples": resamples,
        "seed": seed,
        "level": level,
        "generator": "random.Random(seed).random(), index = floor(value * tiles)",
        "iou_strict": strict_range,
        "iou_covered": describe(covered),
        "share_of_resamples_with_both_readings_at_or_above_minimum": _rounded(
            float(both.sum()) / resamples
        ),
        "strict_range_lies_at_or_above_minimum": bool(strict_range["lower"] >= minimum),
    }


def skill_bar_robustness(
    counts_by_tile: Mapping[str, Mapping[str, int]],
    *,
    minimum: float = bench.T2_SKILL_BAR_TEST_IOU_MIN,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Read a pooled held-out IoU against a minimum, with its dependence on single tiles.

    ``point_estimate_reaches_minimum`` is the declared reading: both the
    covered and the strict pooled IoU are at least ``minimum``. ``robust`` is
    true only when that also holds with any one tile left out and the lower
    end of the tile-bootstrap range of the strict IoU is at least ``minimum``.

    The strict reading counts a declined tile exactly like a "no flood"
    answer: mapped flood in it is missed, and nothing in it can be a false
    alarm. Declining a tile with little flood therefore raises the strict
    IoU, so the abstained share is returned beside it and belongs in the same
    sentence.
    """

    point = pooled_metrics(list(counts_by_tile.values()))
    reaches = bench.clears_skill_bar(point)
    one_out = leave_one_tile_out(counts_by_tile, minimum=minimum)
    bootstrap = tile_bootstrap(counts_by_tile, minimum=minimum, resamples=resamples, seed=seed)
    robust = bool(
        reaches
        and one_out["holds_for_every_tile_left_out"]
        and bootstrap["strict_range_lies_at_or_above_minimum"]
    )
    strict = point["strict"]["iou"]
    tiles = len(counts_by_tile)
    if strict is None:
        reading = f"no defined point estimate on {tiles} tiles"
    elif not reaches:
        reading = f"point estimate {strict:.3f}; below {minimum:.2f} on at least one reading"
    elif robust:
        reading = f"point estimate {strict:.3f}; at or above {minimum:.2f} on every check"
    else:
        reading = (
            f"point estimate {strict:.3f}; not distinguishable from {minimum:.2f} "
            f"on {tiles} tiles"
        )
    declined = sum(1 for counts in counts_by_tile.values() if int(counts["covered_cells"]) == 0)
    return {
        "minimum": minimum,
        "tiles": tiles,
        "iou_strict": strict,
        "iou_covered": point["covered"]["iou"],
        "abstained_cell_share": point["abstained_cell_share"],
        "tiles_declined": declined,
        "margin_of_the_strict_reading": None if strict is None else _rounded(strict - minimum),
        "point_estimate_reaches_minimum": reaches,
        "leave_one_tile_out": one_out,
        "tile_bootstrap": bootstrap,
        "robust": robust,
        "reading": reading,
    }


# ---------------------------------------------------------------------------
# What the declined tiles hold, and a like-for-like threshold comparison
# ---------------------------------------------------------------------------


def declined_tile_accounting(summary: Mapping[str, Any], split: str) -> dict[str, Any]:
    """Describe the tiles the frozen M1-v2 declined on one split.

    Reads committed counts only. It reports what the declined tiles hold, the
    false alarms the two methods that did answer there produced on them, and
    every method's pooled score on the tiles where the frozen M1-v2 answered.
    No method is combined with another.
    """

    rows = sorted(
        (row for row in summary["per_tile"] if row["split"] == split),
        key=lambda row: _tile_number(row["tile"]),
    )
    if not rows:
        raise GeoidReviewError(f"The summary has no tile of the {split} split")
    declined = [row for row in rows if row["methods"][FROZEN_METHOD]["prediction"]["abstained"]]
    answered = [
        row for row in rows if not row["methods"][FROZEN_METHOD]["prediction"]["abstained"]
    ]

    def total(subset: Sequence[Mapping[str, Any]], method: str, key: str) -> int:
        return sum(int(row["methods"][method]["primary"][key]) for row in subset)

    evaluable = total(rows, FROZEN_METHOD, "evaluable_cells")
    flood = total(rows, FROZEN_METHOD, "reference_flood_cells")
    declined_evaluable = total(declined, FROZEN_METHOD, "evaluable_cells")
    declined_flood = total(declined, FROZEN_METHOD, "reference_flood_cells")
    like_for_like: dict[str, Any] = {}
    for method in bench.METHODS:
        metrics = (
            pooled_metrics([row["methods"][method]["primary"] for row in answered])
            if answered
            else None
        )
        like_for_like[method] = (
            None
            if metrics is None
            else {
                "iou_strict": metrics["strict"]["iou"],
                "iou_covered": metrics["covered"]["iou"],
                "precision": metrics["covered"]["precision"],
                "recall_strict": metrics["strict"]["recall"],
            }
        )
    return {
        "split": split,
        "tiles": len(rows),
        "tiles_answered": [row["tile"] for row in answered],
        "tiles_declined": [row["tile"] for row in declined],
        "declined_tiles": {
            "evaluable_cells": declined_evaluable,
            "share_of_evaluable_cells": _rounded(declined_evaluable / evaluable)
            if evaluable
            else None,
            "reference_flood_cells": declined_flood,
            "share_of_reference_flood": _rounded(declined_flood / flood) if flood else None,
            "false_alarms_counted_against_the_frozen_m1_v2": total(
                declined, FROZEN_METHOD, "false_positive"
            ),
            "false_alarms_of_the_methods_that_answered_there": {
                method: total(declined, method, "false_positive")
                for method in bench.METHODS
                if method != FROZEN_METHOD
            },
        },
        "pooled_scores_on_the_tiles_where_the_frozen_m1_v2_answered": like_for_like,
        "meaning": (
            "On a declined tile the strict reading counts mapped flood as missed and counts "
            "no false alarm, exactly as for an answer of 'no flood' everywhere. The scores on "
            "the answered tiles compare the threshold rules where both gave an answer."
        ),
    }


def otsu_comparator_across_the_grid(log_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The Otsu comparator on the development tiles, for every run of the last session.

    The comparator was logged for all declared runs and never selected one.
    This lists its score and how many tiles it declined in each run, beside
    the Kittler-Illingworth score the selection rule read.
    """

    sessions = [record for record in log_records if record["record"] == "session_start"]
    if not sessions:
        raise GeoidReviewError("The tuning log has no session")
    session = sessions[-1]["session_started_utc"]
    runs = [
        record
        for record in log_records
        if record["record"] == "run" and str(record["run_id"]).startswith(session)
    ]
    if not runs:
        raise GeoidReviewError("The last tuning session has no run")
    chosen = bench.select_run(runs)
    rows = []
    for run in runs:
        otsu = run["otsu_comparator"]
        rows.append(
            {
                "run_index": run["run_index"],
                "parameters": run["parameters"],
                "kittler_illingworth_iou_strict": run["development_iou_strict"],
                "kittler_illingworth_tiles_declined": run["development_abstained_tiles"],
                "otsu_iou_strict": otsu["pooled"]["primary"]["strict"]["iou"],
                "otsu_coverage": otsu["pooled"]["primary"]["coverage"],
                "otsu_tiles_declined": otsu["abstained_tiles"],
            }
        )
    defined = [row for row in rows if row["otsu_iou_strict"] is not None]
    best = max(defined, key=lambda row: (row["otsu_iou_strict"], -row["run_index"]))
    frozen_iou = chosen["development_iou_strict"]
    at_frozen = next(row for row in rows if row["run_index"] == chosen["run_index"])
    return {
        "session": session,
        "tiles": len(chosen["kittler_illingworth"]["per_tile"]),
        "frozen_run_index": chosen["run_index"],
        "frozen_kittler_illingworth_iou_strict": frozen_iou,
        "otsu_at_the_frozen_run": at_frozen,
        "best_otsu_run": best,
        "otsu_runs_above_the_frozen_kittler_illingworth_score": [
            row["run_index"] for row in defined if row["otsu_iou_strict"] > frozen_iou
        ],
        "rows": rows,
        "meaning": (
            "The comparator in the result tables is Otsu at the configuration selected for "
            "Kittler-Illingworth. It is not the best Otsu configuration of the declared grid. "
            "No Otsu variant other than that one was scored on the test tiles."
        ),
    }


def m1_literal_threshold_facts(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Where the M1-literal Otsu threshold sits, and what the method flags without flood.

    M1-literal flags a cell when delta-VH is below the Otsu threshold and
    below zero. Where the threshold is above zero the first condition adds
    nothing, and the rule is "delta-VH below zero".
    """

    rows = sorted(summary["per_tile"], key=lambda row: _tile_number(row["tile"]))
    thresholds = {
        row["tile"]: row["methods"]["m1_literal"]["prediction"]["otsu_threshold_delta_vh_db"]
        for row in rows
    }
    above = [name for name, value in thresholds.items() if value is not None and value > 0]
    not_above = [name for name, value in thresholds.items() if value is not None and value <= 0]
    without_flood: list[dict[str, Any]] = []
    pooled: dict[str, dict[str, int]] = {}
    for row in rows:
        primary = row["methods"]["m1_literal"]["primary"]
        if int(primary["reference_flood_cells"]) != 0:
            continue
        without_flood.append(
            {
                "tile": row["tile"],
                "split": row["split"],
                "flagged_share_of_evaluable_cells": _rounded(
                    primary["predicted_flood_cells"] / primary["evaluable_cells"]
                ),
            }
        )
        entry = pooled.setdefault(row["split"], {"flagged": 0, "evaluable": 0})
        entry["flagged"] += int(primary["predicted_flood_cells"])
        entry["evaluable"] += int(primary["evaluable_cells"])
    shares = [item["flagged_share_of_evaluable_cells"] for item in without_flood]
    return {
        "tiles": len(rows),
        "tiles_with_threshold_above_zero": len(above),
        "tiles_with_threshold_at_or_below_zero": not_above,
        "rule_as_implemented": "delta-VH below the Otsu threshold and below zero",
        "proposal_text": (
            "Estimate the Otsu threshold on valid delta-VH pixels; strong negative change "
            "becomes candidate temporary water."
        ),
        "reading": (
            "The 'below zero' clause is the agent's addition. Where the threshold is above "
            "zero the Otsu threshold plays no part and the rule is 'delta-VH below zero'."
        ),
        "tiles_without_reference_flood": without_flood,
        "flagged_share_on_tiles_without_reference_flood": {
            "per_tile_lowest": min(shares) if shares else None,
            "per_tile_highest": max(shares) if shares else None,
            "pooled_by_split": {
                split: _rounded(entry["flagged"] / entry["evaluable"])
                for split, entry in sorted(pooled.items())
            },
        },
    }


def derived_checks(
    summary: Mapping[str, Any],
    log_records: Sequence[Mapping[str, Any]],
    *,
    summary_sha256: str,
    tuning_log_sha256: str,
) -> dict[str, Any]:
    """Everything the review asked for that follows from committed files alone.

    A pure function of the committed summary and tuning log: no tile is
    opened, no clock is read, and the same inputs give the same output.
    """

    test_counts = tile_counts(summary, FROZEN_METHOD, "test")
    robustness = skill_bar_robustness(test_counts)
    bar = summary["t2_skill_bar"]
    if bar["m1_v2_reaches_the_geoid_condition"] is not robustness["point_estimate_reaches_minimum"]:
        raise GeoidReviewError("The summary and its per-tile counts disagree on the skill bar")
    if robustness["iou_strict"] != bar["m1_v2_test_iou_strict"]:
        raise GeoidReviewError("The per-tile counts do not add up to the committed test IoU")
    results = summary["results"]
    dice = {
        method: {
            split: {
                comparison: {
                    "dice_strict": results[method][split][comparison]["strict"]["dice"],
                    "dice_covered": results[method][split][comparison]["covered"]["dice"],
                }
                for comparison in ("primary", "secondary")
            }
            for split in bench.SPLITS
        }
        for method in bench.METHODS
    }
    return {
        "schema": "floodguard.geoid_m1_benchmark_derived_checks.v1",
        "evidence_tier": "research_benchmark_diagnostic",
        "what_this_is": (
            "Checks added after the held-out scoring, in answer to a review. Computed from "
            "the committed summary and tuning log only. No tile was opened, no score "
            "changed, and nothing was selected or tuned."
        ),
        "review_date": REVIEW_DATE,
        **output_context(summary["source_timestamp"]),
        "robustness_assumptions": list(ROBUSTNESS_ASSUMPTIONS),
        "derived_from": {
            "summary": SUMMARY_FILE,
            "summary_sha256": summary_sha256,
            "summary_generated_at_utc": summary["generated_at_utc"],
            "tuning_log": TUNING_LOG_FILE,
            "tuning_log_sha256": tuning_log_sha256,
            "frozen_config_sha256": summary["provenance"]["frozen_config_sha256"],
            "code_sha256": summary["provenance"]["code_sha256"],
            "planning_protocol_v1a_sha256": summary["provenance"]["planning_protocol_v1a_sha256"],
        },
        "t2_skill_bar": {
            "source": bar["source"],
            "geoid_held_out_test_iou_min": bar["geoid_held_out_test_iou_min"],
            "declared_reading": bar["reading"],
            "what_the_strict_reading_does": (
                "It counts a declined tile like an answer of 'no flood' everywhere: mapped "
                "flood in it is missed, and nothing in it can be a false alarm. Declining a "
                "tile with little flood raises the strict IoU. Requiring both readings does "
                "not prevent that."
            ),
            "m1_v2_test": robustness,
            "robustness_rule": (
                "robust is true only when both readings reach the minimum on the pooled "
                "counts, with any one tile left out, and the lower end of the tile-bootstrap "
                "range of the strict IoU is at least the minimum. Written after the score "
                "was seen; it is a description, not a declared pass rule."
            ),
            "for_later_lanes": (
                "Read 'reading', 'robust' and 'abstained_cell_share' here. Do not take the "
                "boolean m1_v2_reaches_the_geoid_condition of the summary alone."
            ),
            "not_assessed_here": bar["not_assessed_here"],
            "mae_sai_abstention_fraction_max_in_v1a": 0.2,
        },
        "declined_tiles": {
            split: declined_tile_accounting(summary, split) for split in bench.SPLITS
        },
        "otsu_comparator_on_development_tiles": otsu_comparator_across_the_grid(log_records),
        "m1_literal": m1_literal_threshold_facts(summary),
        "dice": dice,
        "fpps_computed": False,
        "action_class_computed": False,
        "mae_sai_run": False,
        "human_reviewed_by_floodguard": False,
        "accepted_observation": False,
        "official_warning": False,
        "can_feed_decision_layer": False,
    }


# ---------------------------------------------------------------------------
# The threshold step on one histogram (reproduction of the amendment check)
# ---------------------------------------------------------------------------


def kittler_illingworth_criterion(
    counts: np.ndarray,
    spec: sar.HistogramSpec = sar.HistogramSpec(),
    *,
    min_class_fraction: float = 0.01,
) -> tuple[np.ndarray, np.ndarray]:
    """Thresholds in dB and the Kittler-Illingworth criterion at each of them.

    The same expression as :func:`floodguard.sar_change_v2.kittler_illingworth_threshold`
    evaluates. A split where a class holds less than ``min_class_fraction``
    of the samples is not admissible and has an infinite criterion.
    """

    counts = np.asarray(counts)
    if counts.shape != (spec.bins,):
        raise GeoidReviewError("counts must match the histogram specification")
    if int(counts.sum()) == 0:
        raise GeoidReviewError("The histogram is empty")
    low_weight, high_weight, _, _, low_variance, high_variance = sar._class_moments(counts, spec)
    floor = spec.bin_width_db**2 / 12.0
    usable = (low_weight >= min_class_fraction) & (high_weight >= min_class_fraction)
    with np.errstate(divide="ignore", invalid="ignore"):
        criterion = (
            1.0
            + low_weight * np.log(np.maximum(low_variance, 0.0) + floor)
            + high_weight * np.log(np.maximum(high_variance, 0.0) + floor)
            - 2.0 * (low_weight * np.log(low_weight) + high_weight * np.log(high_weight))
        )
    criterion = np.where(usable & np.isfinite(criterion), criterion, np.inf)
    thresholds = np.round(
        spec.lower_db + (np.arange(spec.bins - 1) + 1) * spec.bin_width_db, 6
    )
    return thresholds, criterion


def describe_threshold_step(counts: np.ndarray, config: sar.M1V2Config) -> dict[str, Any]:
    """Describe what the threshold step sees on one pooled histogram.

    Returns the two-component fit, the Kittler-Illingworth threshold as the
    code returned it before amendment 1 (the lowest admissible value, which
    may be the edge of the admissible range), the threshold after amendment 1
    (an interior minimum between the fitted modes, or ``None``), the Otsu
    threshold, the admissible range and the local minima of the criterion.
    No label is used.
    """

    spec = config.histogram
    fraction = config.min_threshold_class_fraction
    thresholds, criterion = kittler_illingworth_criterion(
        counts, spec, min_class_fraction=fraction
    )
    finite = np.isfinite(criterion)
    fit = sar.fit_two_gaussians(counts, spec)
    local = np.zeros(criterion.shape, dtype=bool)
    local[1:-1] = (
        finite[:-2]
        & finite[2:]
        & (criterion[1:-1] < criterion[:-2])
        & (criterion[1:-1] <= criterion[2:])
    )
    before = sar.kittler_illingworth_threshold(counts, spec, min_class_fraction=fraction)
    after = (
        None
        if fit is None
        else sar.kittler_illingworth_threshold(
            counts,
            spec,
            min_class_fraction=fraction,
            interior_between_db=(fit.mean_low, fit.mean_high),
        )
    )
    between = (
        np.zeros(criterion.shape, dtype=bool)
        if fit is None
        else local & (thresholds > fit.mean_low) & (thresholds < fit.mean_high)
    )

    def at(threshold: float | None) -> float | None:
        if threshold is None:
            return None
        index = int(np.argmin(np.abs(thresholds - threshold)))
        return round(float(criterion[index]), 4) if finite[index] else None

    return {
        "pooled_cells": int(np.asarray(counts).sum()),
        "pooled_fit": None
        if fit is None
        else {
            "weight_low": round(fit.weight_low, 3),
            "mean_low": round(fit.mean_low, 3),
            "std_low": round(fit.std_low, 3),
            "weight_high": round(fit.weight_high, 3),
            "mean_high": round(fit.mean_high, 3),
            "std_high": round(fit.std_high, 3),
        },
        "pooled_fit_ashman_d": None if fit is None else round(fit.ashman_d, 3),
        "ki_threshold_db_before_amendment_1": before,
        "ki_threshold_db_after_amendment_1": after,
        "otsu_threshold_db": sar.otsu_threshold(counts, spec),
        "admissible_range_db": [float(thresholds[finite][0]), float(thresholds[finite][-1])]
        if finite.any()
        else None,
        "local_minima_db": [float(value) for value in thresholds[local]],
        "j_at_local_minima": [round(float(value), 4) for value in criterion[local]],
        "local_minima_between_fitted_modes_db": [float(value) for value in thresholds[between]],
        "j_at_ki_before_amendment_1": at(before),
        "ki_before_amendment_1_is_edge_of_admissible_range": bool(
            before is not None
            and finite.any()
            and before in (float(thresholds[finite][0]), float(thresholds[finite][-1]))
        ),
    }


# ---------------------------------------------------------------------------
# The proposal's step 4 without the added "below zero" clause
# ---------------------------------------------------------------------------


def m1_literal_without_zero_clause(
    filtered: sar.FilteredPair, config: sar.M1LiteralConfig = sar.M1LiteralConfig()
) -> tuple[np.ndarray, dict[str, Any]]:
    """Flag every valid cell whose delta-VH is below the Otsu threshold.

    This is the proposal's step 4 without the clause "and below zero" that
    M1-literal adds. Where the Otsu threshold is above zero it also flags
    cells that became brighter. It is reported beside M1-literal on the
    development tiles only and is not a candidate for any use.
    """

    valid = filtered.valid
    delta_vh = filtered.post_db[1] - filtered.pre_db[1]
    candidate = np.full(valid.shape, sar.CANDIDATE_ABSTAIN, dtype="uint8")
    counts = sar.histogram_db(delta_vh[valid], config.histogram)
    threshold = sar.otsu_threshold(counts, config.histogram) if counts.sum() else None
    summary: dict[str, Any] = {
        "method": "m1_literal_without_zero_clause",
        "otsu_threshold_delta_vh_db": threshold,
        "abstained": threshold is None,
    }
    if threshold is None:
        summary["candidate_cells"] = 0
        return candidate, summary
    with np.errstate(invalid="ignore"):
        raw = valid & (delta_vh < threshold)
    cleaned = sar.majority_filter(raw, valid)
    candidate[valid] = sar.CANDIDATE_NO
    candidate[cleaned] = sar.CANDIDATE_YES
    summary["candidate_cells"] = int(cleaned.sum())
    return candidate, summary


# ---------------------------------------------------------------------------
# Guard for later lanes
# ---------------------------------------------------------------------------


def check_label_only_config_fields(parameters: Mapping[str, Any]) -> None:
    """Raise unless the label-only fields name what the frozen code does.

    The frozen code never reads ``kittler_illingworth_rule`` or
    ``isolated_speckle_cleaning``, and the benchmark tile loader names the
    speckle filter and the looks itself. A configuration with another value
    in one of these fields would load, behave the same on the benchmark path
    and carry a different SHA-256. This check refuses it.
    """

    for field, expected in LABEL_ONLY_CONFIG_FIELDS.items():
        if field not in parameters:
            raise GeoidReviewError(f"The configuration lacks the field {field}")
        if parameters[field] != expected:
            raise GeoidReviewError(
                f"{field} is {parameters[field]!r}; the frozen code implements {expected!r}"
            )


def require_frozen_m1_v2(root: Path) -> dict[str, Any]:
    """Check that a checkout holds the frozen M1-v2 unchanged, and return its binding.

    The frozen configuration alone does not pin the method: some of its
    fields are labels the code does not act on. The behaviour is pinned by
    the configuration SHA-256 together with the SHA-256 of the two code
    modules in the freeze receipt. This function raises unless the
    configuration, the declared protocol, the tuning log and both code
    modules under ``root`` match the receipt, and unless the label-only
    fields name what the frozen code does. A lane that applies M1-v2 calls it
    first and records the returned hashes with its outputs.
    """

    root = Path(root)

    def read(relative: str) -> bytes:
        path = root / relative
        if not path.is_file():
            raise GeoidReviewError(f"Missing file: {relative}")
        return path.read_bytes()

    receipt = json.loads(read(FREEZE_RECEIPT_FILE))
    frozen_bytes = read(FROZEN_CONFIG_FILE)
    try:
        bench.verify_freeze_receipt(
            receipt,
            frozen_config_bytes=frozen_bytes,
            declared_protocol_bytes=read(PROTOCOL_FILE),
            tuning_log_bytes=read(TUNING_LOG_FILE),
            code_bytes={name: read(name) for name in CODE_FILES},
        )
    except bench.GeoidBenchmarkError as error:
        raise GeoidReviewError(str(error)) from error
    parameters = json.loads(frozen_bytes)["parameters"]
    check_label_only_config_fields(parameters)
    return {
        "frozen_config_sha256": receipt["frozen_config_sha256"],
        "code_sha256": dict(receipt["code_sha256"]),
        "planning_protocol_v1a_sha256": receipt["planning_protocol_v1a_sha256"],
        "freeze_receipt_sha256": bench.bytes_sha256(read(FREEZE_RECEIPT_FILE)),
        "parameters": parameters,
    }
