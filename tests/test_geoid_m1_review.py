"""Tests for the review addendum of the GEOID M1 benchmark."""

from __future__ import annotations

import importlib.util
import json
import os
import random
import shutil
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from floodguard import geoid_m1_benchmark as bench
from floodguard import geoid_m1_review as review
from floodguard import sar_change_v2 as sar

ROOT = Path(__file__).resolve().parents[1]
TRACK = ROOT / "docs" / "proposal_execution" / "automated_track"
RESULT_DOCUMENT = TRACK / "GEOID_M1_BENCHMARK_V2_RESULT.md"
FREEZE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
SPEC = sar.HistogramSpec()


def _load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _counts(**values: int) -> dict[str, int]:
    counts = {key: 0 for key in bench.COUNT_KEYS}
    counts.update(values)
    return counts


def _answered(tp: int, fp: int, fn: int, tn: int) -> dict[str, int]:
    cells = tp + fp + fn + tn
    return _counts(
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        true_negative=tn,
        evaluable_cells=cells,
        covered_cells=cells,
        reference_flood_cells=tp + fn,
    )


def _declined(flood: int, dry: int) -> dict[str, int]:
    return _counts(
        evaluable_cells=flood + dry,
        reference_flood_cells=flood,
        abstained_reference_flood_cells=flood,
        abstained_reference_nonflood_cells=dry,
    )


# --- output context and the recording store -----------------------------------


def test_output_context_carries_the_four_required_fields() -> None:
    context = review.output_context("2024-01-03T05:34:06Z")
    assert context["source_timestamp"] == "2024-01-03T05:34:06Z"
    assert context["confidence"].startswith("low")
    assert bench.AGREEMENT_WORDING in context["confidence"]
    assert context["wording"] == bench.AGREEMENT_WORDING
    assert len(context["assumptions"]) >= 5


def _write_sample(root: Path, tile_ids: tuple[int, ...], size: int = 8) -> Path:
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    rng = np.random.default_rng(7)
    lines = []
    for position, tile_id in enumerate(tile_ids):
        flooded = np.zeros((size, size), dtype=bool)
        if position % 3 == 0:
            flooded[: size // 4, :] = True
        base = np.stack([np.full((size, size), 0.1), np.full((size, size), 0.025)])
        pre = base * rng.gamma(4.4, 1 / 4.4, size=base.shape)
        post = np.where(flooded, base * 0.1, base) * rng.gamma(4.4, 1 / 4.4, size=base.shape)
        label = np.where(flooded, 2, 0).astype("uint8")
        layers = {
            f"s1grd/{bench.AOI}-{tile_id}_s1grd_pre_20230908T170906.tif": pre.astype("float32"),
            f"s1grd/{bench.AOI}-{tile_id}_s1grd_post_20240103T053341.tif": post.astype("float32"),
            f"label/{bench.AOI}-{tile_id}_label.tif": label[None],
            f"validity/{bench.AOI}-{tile_id}_validity.tif": np.ones((1, size, size), "uint8"),
        }
        for relative, data in layers.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=size,
                width=size,
                count=data.shape[0],
                dtype=data.dtype.name,
                crs="EPSG:32632",
                transform=from_origin(471040.0, 5888000.0, 10.0, 10.0),
            ) as dataset:
                dataset.write(data)
            lines.append(f"{bench.file_sha256(path)}  sample/geoid-flood/{bench.AOI}/{relative}")
    sums = root / "SHA256SUMS"
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return sums


def test_recording_store_keeps_what_it_opened_and_what_it_refused(tmp_path: Path) -> None:
    sums = _write_sample(tmp_path, (9, 10, 35))
    store = review.RecordingTileStore(tmp_path, sums, phase=bench.PHASE_TUNING)
    assert store.opened_tile_ids() == () and store.refused_tile_ids() == ()
    store.read_inputs(10)
    store.read_reference(9)
    with pytest.raises(bench.TestTileAccessRefused):
        store.read_inputs(35)
    with pytest.raises(bench.TestTileAccessRefused):
        store.read_reference(50)
    assert store.opened_tile_ids() == (9, 10)
    assert store.opened_test_tile_ids() == ()
    assert store.refused_tile_ids() == (35, 50)
    record = store.access_record()
    assert record["tiles_opened"] == ["EMSR712-3-9", "EMSR712-3-10"]
    assert record["test_tiles_opened"] == []
    assert record["tiles_refused"] == ["EMSR712-3-35", "EMSR712-3-50"]
    assert "around the store" in record["access_record_scope"]
    # A read that the access rule lets start counts as opened even if it then fails.
    with pytest.raises(bench.GeoidBenchmarkError, match="one pre and one post"):
        store.read_inputs(12)
    assert store.opened_tile_ids() == (9, 10, 12)
    scoring = review.RecordingTileStore(
        tmp_path, sums, phase=bench.PHASE_HELD_OUT_SCORING, freeze_commit=FREEZE_COMMIT
    )
    scoring.read_inputs(35)
    assert scoring.opened_test_tile_ids() == (35,)
    assert scoring.access_record()["test_tiles_opened"] == ["EMSR712-3-35"]


# --- robustness of a pooled score ---------------------------------------------


def test_the_strict_reading_rewards_declining_a_tile_with_little_flood() -> None:
    """Requiring both readings does not stop a method from gaining by declining."""

    flooded = _answered(tp=60, fp=20, fn=40, tn=880)
    sparse_answered = _answered(tp=2, fp=120, fn=3, tn=875)
    sparse_declined = _declined(flood=5, dry=995)
    answering = review.pooled_metrics([flooded, sparse_answered])
    declining = review.pooled_metrics([flooded, sparse_declined])
    assert answering["strict"]["iou"] == pytest.approx(62 / 245, abs=1e-6)
    assert declining["strict"]["iou"] == pytest.approx(60 / 125, abs=1e-6)
    assert declining["covered"]["iou"] == pytest.approx(60 / 120, abs=1e-6)
    assert not bench.clears_skill_bar(answering)
    assert bench.clears_skill_bar(declining)
    assert declining["abstained_cell_share"] == 0.5
    # A declined tile scores exactly like an answer of "no flood" everywhere.
    all_no = _answered(tp=0, fp=0, fn=5, tn=995)
    assert (
        review.pooled_metrics([flooded, all_no])["strict"]["iou"] == declining["strict"]["iou"]
    )


def test_leave_one_tile_out_names_the_tiles_that_carry_the_score() -> None:
    counts = {
        "EMSR712-3-35": _declined(flood=10, dry=990),
        "EMSR712-3-42": _answered(tp=600, fp=100, fn=300, tn=0),
        "EMSR712-3-46": _answered(tp=50, fp=60, fn=90, tn=800),
    }
    result = review.leave_one_tile_out(counts, minimum=0.40)
    rows = {row["tile_left_out"]: row for row in result["rows"]}
    assert [row["tile_left_out"] for row in result["rows"]] == list(counts)
    assert rows["EMSR712-3-35"]["tile_was_declined"] is True
    assert rows["EMSR712-3-42"]["iou_strict"] == pytest.approx(50 / 210, abs=1e-6)
    assert rows["EMSR712-3-46"]["iou_strict"] == pytest.approx(600 / 1010, abs=1e-6)
    assert result["tiles_whose_removal_takes_a_reading_below_minimum"] == ["EMSR712-3-42"]
    assert result["holds_for_every_tile_left_out"] is False
    assert result["lowest_iou_strict_tile_left_out"] == "EMSR712-3-42"
    with pytest.raises(review.GeoidReviewError):
        review.leave_one_tile_out({"EMSR712-3-35": counts["EMSR712-3-35"]}, minimum=0.4)


def test_resample_indices_are_reproducible() -> None:
    first = review.resample_indices(14, 50, 20261003)
    assert first.shape == (50, 14)
    assert first.min() >= 0 and first.max() <= 13
    assert (first == review.resample_indices(14, 50, 20261003)).all()
    assert not (first == review.resample_indices(14, 50, 1)).all()
    # The draws come from random.Random(seed).random(), which is stable across versions.
    generator = random.Random(20261003)
    assert first[0].tolist() == [min(int(generator.random() * 14), 13) for _ in range(14)]
    assert first[0].tolist() == [0, 12, 4, 2, 6, 7, 8, 7, 0, 9, 5, 11, 8, 10]
    with pytest.raises(review.GeoidReviewError):
        review.resample_indices(0, 5, 1)


def test_tile_bootstrap_and_the_robust_flag() -> None:
    same = {f"EMSR712-3-{index}": _answered(tp=70, fp=10, fn=20, tn=900) for index in (35, 36, 37)}
    steady = review.skill_bar_robustness(same, minimum=0.40, resamples=200, seed=3)
    assert steady["iou_strict"] == pytest.approx(0.7)
    bootstrap = steady["tile_bootstrap"]
    assert bootstrap["iou_strict"]["lower"] == bootstrap["iou_strict"]["upper"] == 0.7
    assert bootstrap["iou_strict"]["share_of_resamples_at_or_above_minimum"] == 1.0
    assert bootstrap["share_of_resamples_with_both_readings_at_or_above_minimum"] == 1.0
    assert steady["point_estimate_reaches_minimum"] and steady["robust"]
    assert steady["reading"] == "point estimate 0.700; at or above 0.40 on every check"

    uneven = {
        "EMSR712-3-35": _declined(flood=40, dry=960),
        "EMSR712-3-36": _declined(flood=0, dry=1000),
        "EMSR712-3-42": _answered(tp=300, fp=60, fn=140, tn=500),
        "EMSR712-3-46": _answered(tp=30, fp=40, fn=60, tn=870),
    }
    marginal = review.skill_bar_robustness(uneven, minimum=0.40, resamples=2000, seed=3)
    assert marginal["point_estimate_reaches_minimum"] is True
    assert marginal["robust"] is False
    assert marginal["tiles_declined"] == 2
    assert marginal["abstained_cell_share"] == pytest.approx(0.5, abs=1e-6)
    assert "not distinguishable from 0.40 on 4 tiles" in marginal["reading"]
    spread = marginal["tile_bootstrap"]
    assert spread["iou_strict"]["lower"] < 0.40 < spread["iou_strict"]["upper"]
    assert spread["iou_covered"]["undefined_resamples"] > 0
    assert 0 < spread["iou_strict"]["share_of_resamples_at_or_above_minimum"] < 1
    assert spread["strict_range_lies_at_or_above_minimum"] is False
    again = review.skill_bar_robustness(uneven, minimum=0.40, resamples=2000, seed=3)
    assert again == marginal

    failing = {
        "EMSR712-3-35": _answered(tp=10, fp=60, fn=30, tn=900),
        "EMSR712-3-36": _answered(tp=10, fp=60, fn=30, tn=900),
    }
    low = review.skill_bar_robustness(failing, minimum=0.40, resamples=100, seed=3)
    assert low["point_estimate_reaches_minimum"] is False and low["robust"] is False
    assert "below 0.40" in low["reading"]


# --- the threshold step ---------------------------------------------------------


def _histogram(rng: np.random.Generator, modes: list[tuple[float, float, int]]) -> np.ndarray:
    samples = np.concatenate([rng.normal(mean, std, size=count) for mean, std, count in modes])
    return sar.histogram_db(samples, SPEC)


def test_criterion_is_the_one_the_frozen_code_minimises() -> None:
    rng = np.random.default_rng(11)
    for modes in (
        [(-1.0, 1.0, 40000), (7.0, 1.0, 12000)],
        [(-0.5, 2.5, 60000), (5.0, 2.3, 9000)],
        [(0.0, 2.0, 50000)],
    ):
        counts = _histogram(rng, modes)
        thresholds, criterion = review.kittler_illingworth_criterion(counts, SPEC)
        assert thresholds.shape == criterion.shape == (SPEC.bins - 1,)
        lowest = float(thresholds[int(np.argmin(criterion))])
        assert lowest == sar.kittler_illingworth_threshold(counts, SPEC)
    with pytest.raises(review.GeoidReviewError):
        review.kittler_illingworth_criterion(np.zeros(SPEC.bins, dtype="int64"), SPEC)
    with pytest.raises(review.GeoidReviewError):
        review.kittler_illingworth_criterion(np.zeros(3, dtype="int64"), SPEC)


def test_threshold_step_separates_an_interior_minimum_from_an_edge() -> None:
    rng = np.random.default_rng(12)
    config = sar.M1V2Config()
    separated = review.describe_threshold_step(
        _histogram(rng, [(-1.0, 1.0, 40000), (7.0, 1.0, 12000)]), config
    )
    assert separated["ki_threshold_db_before_amendment_1"] == separated[
        "ki_threshold_db_after_amendment_1"
    ]
    assert separated["ki_before_amendment_1_is_edge_of_admissible_range"] is False
    assert (
        separated["ki_threshold_db_after_amendment_1"]
        in separated["local_minima_between_fitted_modes_db"]
    )
    assert separated["pooled_fit_ashman_d"] > 2
    low, high = separated["admissible_range_db"]
    assert low < separated["ki_threshold_db_after_amendment_1"] < high

    assert separated["ki_threshold_db_after_amendment_1"] == sar.threshold_from_histogram(
        _histogram(np.random.default_rng(12), [(-1.0, 1.0, 40000), (7.0, 1.0, 12000)]), config
    )

    # Overlapping classes: the criterion has no minimum between the modes. Before
    # amendment 1 the code returned the edge of the admissible range; now it declines.
    overlapping = _histogram(rng, [(-0.5, 2.6, 60000), (4.0, 2.4, 9000)])
    described = review.describe_threshold_step(overlapping, config)
    assert described["local_minima_between_fitted_modes_db"] == []
    assert described["ki_threshold_db_after_amendment_1"] is None
    assert sar.threshold_from_histogram(overlapping, config) is None
    assert described["ki_before_amendment_1_is_edge_of_admissible_range"] is True
    assert described["ki_threshold_db_before_amendment_1"] in described["admissible_range_db"]


def test_step_4_without_the_zero_clause_flags_more_where_the_threshold_is_positive() -> None:
    rng = np.random.default_rng(13)
    shape = (96, 96)
    base = np.stack([np.full(shape, 0.1), np.full(shape, 0.025)])

    def pair(change_db: np.ndarray) -> sar.FilteredPair:
        factor = 10.0 ** (change_db / 10.0)
        pre = base * rng.gamma(4.4, 1 / 4.4, size=base.shape)
        post = base * factor * rng.gamma(4.4, 1 / 4.4, size=base.shape)
        return sar.filter_pair(
            pre, post, speckle_filter="lee_local_statistics", window_pixels=5
        )

    brighter = pair(np.full(shape, 1.5))
    implemented, detail = sar.m1_literal_from_filtered(brighter)
    without, summary = review.m1_literal_without_zero_clause(brighter)
    assert detail["otsu_threshold_delta_vh_db"] == summary["otsu_threshold_delta_vh_db"] > 0
    assert (without == sar.CANDIDATE_YES).sum() > (implemented == sar.CANDIDATE_YES).sum()
    assert not ((implemented == sar.CANDIDATE_YES) & (without != sar.CANDIDATE_YES)).any()

    change = np.zeros(shape)
    change[:40, :] = -9.0
    flooded = pair(change)
    implemented, detail = sar.m1_literal_from_filtered(flooded)
    without, summary = review.m1_literal_without_zero_clause(flooded)
    assert summary["otsu_threshold_delta_vh_db"] < 0
    assert (implemented == without).all()


# --- the guard for later lanes ----------------------------------------------------


def _copy_frozen_files(target: Path) -> None:
    for relative in (
        review.PROTOCOL_FILE,
        review.TUNING_LOG_FILE,
        review.FROZEN_CONFIG_FILE,
        review.FREEZE_RECEIPT_FILE,
        *review.CODE_FILES,
    ):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)


def test_frozen_method_is_unchanged_in_this_checkout() -> None:
    """The two code modules bound by the freeze receipt must not change."""

    binding = review.require_frozen_m1_v2(ROOT)
    receipt = json.loads((ROOT / review.FREEZE_RECEIPT_FILE).read_bytes())
    assert binding["frozen_config_sha256"] == bench.file_sha256(ROOT / review.FROZEN_CONFIG_FILE)
    assert binding["frozen_config_sha256"] == receipt["frozen_config_sha256"]
    assert binding["planning_protocol_v1a_sha256"] == bench.PROTOCOL_V1A_SHA256
    assert set(binding["code_sha256"]) == set(review.CODE_FILES)
    for name in review.CODE_FILES:
        assert binding["code_sha256"][name] == bench.file_sha256(ROOT / name), name
    summary = json.loads((ROOT / review.SUMMARY_FILE).read_bytes())
    assert summary["provenance"]["code_sha256"] == binding["code_sha256"]
    assert binding["parameters"] == summary["m1_v2_frozen_parameters"]


def test_guard_refuses_changed_code_and_changed_label_fields(tmp_path: Path) -> None:
    _copy_frozen_files(tmp_path)
    assert review.require_frozen_m1_v2(tmp_path)["parameters"]["block_pixels"] == 64
    code = tmp_path / review.CODE_FILES[0]
    code.write_bytes(code.read_bytes() + b"\n# changed\n")
    with pytest.raises(review.GeoidReviewError, match="Code changed after the freeze"):
        review.require_frozen_m1_v2(tmp_path)
    shutil.copyfile(ROOT / review.CODE_FILES[0], code)
    review.require_frozen_m1_v2(tmp_path)
    frozen = tmp_path / review.FROZEN_CONFIG_FILE
    frozen.write_bytes(frozen.read_bytes().replace(b'"block_pixels": 64', b'"block_pixels": 128'))
    with pytest.raises(review.GeoidReviewError, match="frozen_config_sha256"):
        review.require_frozen_m1_v2(tmp_path)
    (tmp_path / review.FREEZE_RECEIPT_FILE).unlink()
    with pytest.raises(review.GeoidReviewError, match="Missing file"):
        review.require_frozen_m1_v2(tmp_path)

    parameters = json.loads((ROOT / review.FROZEN_CONFIG_FILE).read_bytes())["parameters"]
    review.check_label_only_config_fields(parameters)
    for field, other in (
        ("kittler_illingworth_rule", "lowest_admissible_value"),
        ("isolated_speckle_cleaning", "none"),
        ("speckle_filter", "lee_local_statistics"),
        ("equivalent_looks", 1.0),
    ):
        # The frozen code would accept each of these and behave the same on the benchmark path.
        sar.m1_v2_config_from_json({**parameters, field: other})
        with pytest.raises(review.GeoidReviewError, match=field):
            review.check_label_only_config_fields({**parameters, field: other})
    missing = {key: value for key, value in parameters.items() if key != "speckle_filter"}
    with pytest.raises(review.GeoidReviewError, match="lacks"):
        review.check_label_only_config_fields(missing)


# --- committed artefacts of the review ---------------------------------------------

DERIVED = ROOT / review.DERIVED_CHECKS_FILE
REPRODUCTION = ROOT / review.AMENDMENT_CHECK_FILE
ADDENDUM = ROOT / review.ADDENDUM_FILE
SUMMARY = ROOT / review.SUMMARY_FILE
NO_DECISION_FLAGS = (
    "fpps_computed",
    "action_class_computed",
    "mae_sai_run",
    "accepted_observation",
    "official_warning",
    "can_feed_decision_layer",
    "human_reviewed_by_floodguard",
)


def _required_fields(
    record: dict[str, object], source_timestamp: str = "2024-01-03T05:34:06Z"
) -> None:
    assert record["source_timestamp"] == source_timestamp
    assert str(record["confidence"]).startswith("low")
    assert len(record["assumptions"]) >= 5  # type: ignore[arg-type]
    assert record["wording"] == bench.AGREEMENT_WORDING


def test_derived_checks_equal_a_fresh_derivation_from_the_committed_files() -> None:
    script = _load_script("derive_geoid_m1_review_checks")
    fresh = bench.canonical_json_bytes(script.build(ROOT))
    assert DERIVED.read_bytes() == fresh
    derived = json.loads(fresh)
    summary = json.loads(SUMMARY.read_bytes())
    _required_fields(derived)
    for flag in NO_DECISION_FLAGS:
        assert derived[flag] is False
    assert derived["derived_from"]["summary_sha256"] == bench.file_sha256(SUMMARY)
    assert derived["derived_from"]["tuning_log_sha256"] == bench.file_sha256(
        ROOT / review.TUNING_LOG_FILE
    )
    assert derived["derived_from"]["code_sha256"] == {
        name: bench.file_sha256(ROOT / name) for name in review.CODE_FILES
    }

    bar = derived["t2_skill_bar"]
    held_out = bar["m1_v2_test"]
    test = summary["results"][review.FROZEN_METHOD]["test"]["primary"]
    assert held_out["iou_strict"] == test["strict"]["iou"] == 0.411164
    assert held_out["iou_covered"] == test["covered"]["iou"]
    assert held_out["abstained_cell_share"] == test["abstained_cell_share"] == 0.678737
    assert held_out["tiles"] == 14 and held_out["tiles_declined"] == 10
    assert (
        held_out["point_estimate_reaches_minimum"]
        is summary["t2_skill_bar"]["m1_v2_reaches_the_geoid_condition"]
        is True
    )
    assert held_out["robust"] is False
    assert held_out["reading"] == "point estimate 0.411; not distinguishable from 0.40 on 14 tiles"
    assert "not prevent" in bar["what_the_strict_reading_does"]
    assert "Written after the score was seen" in bar["robustness_rule"]
    one_out = held_out["leave_one_tile_out"]
    assert len(one_out["rows"]) == 14
    assert one_out["tiles_whose_removal_takes_a_reading_below_minimum"] == [
        "EMSR712-3-42",
        "EMSR712-3-49",
    ]
    assert one_out["lowest_iou_strict"] == pytest.approx(0.297, abs=5e-4)
    by_tile = {row["tile_left_out"]: row for row in one_out["rows"]}
    assert by_tile["EMSR712-3-49"]["iou_strict"] == pytest.approx(0.380, abs=5e-4)
    spread = held_out["tile_bootstrap"]
    assert spread["resamples"] == 20000 and spread["tiles"] == 14
    assert spread["iou_strict"]["lower"] < 0.15 and spread["iou_strict"]["upper"] > 0.45
    assert 0.4 < spread["iou_strict"]["share_of_resamples_at_or_above_minimum"] < 0.6
    assert spread["strict_range_lies_at_or_above_minimum"] is False

    declined = derived["declined_tiles"]["test"]
    assert len(declined["tiles_declined"]) == 10 and len(declined["tiles_answered"]) == 4
    assert declined["declined_tiles"]["false_alarms_counted_against_the_frozen_m1_v2"] == 0
    others = declined["declined_tiles"]["false_alarms_of_the_methods_that_answered_there"]
    assert others["m1_literal"] > others["m1_v2_otsu_comparator"] > 1_000_000
    like = declined["pooled_scores_on_the_tiles_where_the_frozen_m1_v2_answered"]
    assert like[review.FROZEN_METHOD]["iou_covered"] == test["covered"]["iou"]
    assert like["m1_literal"]["iou_covered"] < like["m1_v2_otsu_comparator"]["iou_covered"]
    assert like["m1_v2_otsu_comparator"]["iou_covered"] < like[review.FROZEN_METHOD]["iou_covered"]

    otsu = derived["otsu_comparator_on_development_tiles"]
    assert len(otsu["rows"]) == 36 and otsu["frozen_run_index"] == 1
    assert otsu["best_otsu_run"]["run_index"] == 29
    assert otsu["best_otsu_run"]["otsu_iou_strict"] == 0.47523
    assert otsu["best_otsu_run"]["otsu_tiles_declined"] == 10
    assert otsu["otsu_runs_above_the_frozen_kittler_illingworth_score"] == [29]
    assert otsu["otsu_at_the_frozen_run"]["otsu_tiles_declined"] == 0

    literal = derived["m1_literal"]
    assert literal["tiles"] == 29 and literal["tiles_with_threshold_above_zero"] == 23
    assert [name.rsplit("-", 1)[1] for name in literal["tiles_with_threshold_at_or_below_zero"]] == [
        "22",
        "31",
        "32",
        "33",
        "42",
        "49",
    ]
    shares = literal["flagged_share_on_tiles_without_reference_flood"]
    assert shares["per_tile_lowest"] == pytest.approx(0.254, abs=5e-4)
    assert shares["per_tile_highest"] == pytest.approx(0.436, abs=5e-4)
    assert derived["dice"][review.FROZEN_METHOD]["test"]["primary"] == {
        "dice_strict": test["strict"]["dice"],
        "dice_covered": test["covered"]["dice"],
    }


def test_amendment_check_reproduction_opened_development_tiles_only() -> None:
    record = json.loads(REPRODUCTION.read_bytes())
    protocol = json.loads((ROOT / review.PROTOCOL_FILE).read_bytes())
    receipt = json.loads((ROOT / review.FREEZE_RECEIPT_FILE).read_bytes())
    _required_fields(record)
    for flag in NO_DECISION_FLAGS:
        assert record[flag] is False
    assert record["selects_a_configuration"] is False
    assert record["phase"] == bench.PHASE_TUNING
    assert record["tiles_opened"] == [bench.tile_name(tile) for tile in bench.DEVELOPMENT_TILE_IDS]
    assert record["test_tiles_opened"] == [] and record["tiles_refused"] == []
    test_names = {bench.tile_name(tile) for tile in bench.TEST_TILE_IDS}
    assert not any(name + "_" in path for name in test_names for path in record["input_sha256"])
    assert len(record["input_sha256"]) == 15 * 4
    assert record["frozen_method_binding"]["code_sha256"] == receipt["code_sha256"]
    assert record["frozen_method_binding"]["frozen_config_sha256"] == receipt["frozen_config_sha256"]
    assert record["declared_benchmark_protocol_sha256"] == bench.file_sha256(
        ROOT / review.PROTOCOL_FILE
    )
    check = record["amendment_check"]
    amendment = protocol["amendments"][0]
    assert check["configuration"] == amendment["what_happened"]["first_session_choice"]["parameters"]
    assert check["every_published_value_recomputed"] is True
    published = amendment["development_only_check"]["tiles"]
    assert [row["tile"] for row in check["comparison_with_amendment_text"]] == [
        bench.tile_name(entry["tile"]) for entry in published
    ]
    for entry in published:
        recomputed = check["per_tile"][bench.tile_name(entry["tile"])]
        assert recomputed["ki_threshold_db_before_amendment_1"] == entry["ki_threshold_db"]
        assert recomputed["pooled_fit"] == entry["pooled_fit"]
        assert recomputed["local_minima_between_fitted_modes_db"] == entry["interior_local_minima_db"]
    edge = check["per_tile"]["EMSR712-3-25"]
    assert edge["ki_before_amendment_1_is_edge_of_admissible_range"] is True
    assert edge["ki_threshold_db_after_amendment_1"] is None
    assert "does not show" in record["limit"]

    readings = record["m1_literal_step_4_readings"]
    summary = json.loads(SUMMARY.read_bytes())
    committed = summary["results"]["m1_literal"]["development"]["primary"]
    assert readings["split"] == "development" and readings["tiles"] == 15
    assert readings["as_implemented"]["equals_the_committed_development_score"] is True
    assert readings["as_implemented"]["iou_strict"] == committed["strict"]["iou"]
    assert readings["as_implemented"]["false_positive"] == committed["false_positive"]
    assert readings["without_zero_clause"]["iou_strict"] < readings["as_implemented"]["iou_strict"]
    assert not any(name in readings["per_tile"] for name in test_names)


@pytest.mark.skipif(
    not os.environ.get("FLOODGUARD_EXTERNAL_DATA"), reason="FLOODGUARD_EXTERNAL_DATA is not set"
)
def test_amendment_check_recomputes_on_a_real_development_tile() -> None:
    pytest.importorskip("rasterio")
    geoid = Path(os.environ["FLOODGUARD_EXTERNAL_DATA"]) / "geoid_flood"
    root = geoid / "sample" / "sample" / "geoid-flood" / bench.AOI
    if not root.is_dir():
        pytest.skip("The GEOID sample is not on this machine")
    script = _load_script("diagnose_geoid_m1_v2_amendment_check")
    record = json.loads(REPRODUCTION.read_bytes())
    store = review.RecordingTileStore(
        root, geoid / "metadata" / "SHA256SUMS", phase=bench.PHASE_TUNING
    )
    loaded = bench.load_tiles(store, (25,), with_reference=False)
    config = sar.M1V2Config(**record["amendment_check"]["configuration"])
    described = script.threshold_step_by_tile(loaded.filtered, config)
    assert described == {"EMSR712-3-25": record["amendment_check"]["per_tile"]["EMSR712-3-25"]}
    assert store.opened_tile_ids() == (25,) and store.opened_test_tile_ids() == ()


def test_addendum_names_the_files_it_corrects_by_hash_and_carries_the_fields() -> None:
    data = ADDENDUM.read_bytes()
    assert b"\r" not in data
    addendum = json.loads(data)
    _required_fields(addendum)
    for flag in NO_DECISION_FLAGS:
        assert addendum["safety"][flag] is False
    bound = addendum["corrects_without_editing"]
    assert set(bound) == {
        review.PROTOCOL_FILE,
        review.TUNING_LOG_FILE,
        review.FROZEN_CONFIG_FILE,
        review.FREEZE_RECEIPT_FILE,
        review.SUMMARY_FILE,
        *review.CODE_FILES,
    }
    for relative, entry in {**bound, **addendum["adds"]}.items():
        assert entry["sha256"] == bench.file_sha256(ROOT / relative), relative
    assert set(addendum["adds"]) == {review.DERIVED_CHECKS_FILE, review.AMENDMENT_CHECK_FILE}
    corrections = addendum["corrections"]
    assert sorted(item["review_finding"] for item in corrections) == list(range(1, 10))
    for item in corrections:
        assert item["where"] and item["what_is_wrong"] and item["correct_statement"]
    sidecar = addendum["fields_for_files_that_lack_them"]
    assert set(sidecar) == {review.TUNING_LOG_FILE, review.FREEZE_RECEIPT_FILE}
    for relative, entry in sidecar.items():
        assert entry["sha256"] == bench.file_sha256(ROOT / relative)
        _required_fields(entry)
    text = json.dumps(addendum)
    assert "not distinguishable from 0.40 on 14 tiles" in text
    assert "require_frozen_m1_v2" in text
    assert "v3" in text and "held-out data" in text
    assert len(addendum["decisions_for_the_owners"]) >= 5
    # The log and the receipt themselves still lack the fields: they are bound by hash.
    receipt = json.loads((ROOT / review.FREEZE_RECEIPT_FILE).read_bytes())
    assert "confidence" not in receipt and "assumptions" not in receipt


def test_result_document_carries_the_review_corrections() -> None:
    text = RESULT_DOCUMENT.read_bytes().decode("utf-8")
    assert "\r" not in text
    flat = " ".join(text.split())
    derived = json.loads(DERIVED.read_bytes())
    summary = json.loads(SUMMARY.read_bytes())
    reproduction = json.loads(REPRODUCTION.read_bytes())
    held_out = derived["t2_skill_bar"]["m1_v2_test"]
    # Finding 1: the verdict is a point estimate with its spread, not a bare yes.
    assert "the GEOID condition of the bar is met" not in flat
    assert held_out["reading"].replace("point estimate", "Reading: point estimate") in flat.replace(
        "**", ""
    )
    spread = held_out["tile_bootstrap"]
    for reading in ("iou_strict", "iou_covered"):
        entry = spread[reading]
        assert (
            f"{entry['lower']:.3f} to {entry['upper']:.3f} | "
            f"{100 * entry['share_of_resamples_at_or_above_minimum']:.1f}% |"
        ) in text
    assert f"In {spread['iou_covered']['undefined_resamples']} draws no answered tile" in flat
    for row in held_out["leave_one_tile_out"]["rows"]:
        line = (
            f"| {row['tile_left_out'].rsplit('-', 1)[1]} | "
            f"{'declined' if row['tile_was_declined'] else 'answered'} | "
            f"{row['iou_strict']:.3f} | {row['iou_covered']:.3f} | "
            f"{100 * row['abstained_cell_share']:.1f}% | "
            f"{'yes' if row['both_readings_reach_minimum'] else 'no'} |"
        )
        assert line in text, line
    assert "`robust: false`" in text
    # Finding 3: the false claim is withdrawn, and the strict IoU travels with the share.
    assert "abstaining cannot buy the bar" in flat  # quoted as the sentence that is wrong
    assert "Requiring both readings does not make the bar proof against declining" in flat
    test = summary["results"][review.FROZEN_METHOD]["test"]["primary"]
    cell = f"{test['strict']['iou']:.3f} ({100 * test['abstained_cell_share']:.1f}% no answer)"
    assert text.count(cell) >= 3
    # Finding 2: the Otsu comparator across the grid.
    otsu = derived["otsu_comparator_on_development_tiles"]
    best = otsu["best_otsu_run"]
    assert f"scored {best['otsu_iou_strict']:.3f} on the development tiles" in flat
    assert f"while declining {best['otsu_tiles_declined']} of 15" in flat
    tuning = text.split("### Two sessions and one amendment")[1].split("What the table shows")[0]
    for row in otsu["rows"]:
        tail = f"| {row['otsu_iou_strict']:.3f} | {row['otsu_tiles_declined']} of 15 |"
        chosen = row["run_index"] == otsu["frozen_run_index"]
        start = f"| **{row['run_index']}** | " if chosen else f"| {row['run_index']} | "
        lines = [line for line in tuning.splitlines() if line.startswith(start)]
        assert len(lines) == 1 and lines[0].endswith(tail), (row["run_index"], lines)
    like = derived["declined_tiles"]["test"][
        "pooled_scores_on_the_tiles_where_the_frozen_m1_v2_answered"
    ]
    assert (
        f"{like['m1_literal']['iou_covered']:.3f} (M1-literal), "
        f"{like['m1_v2_otsu_comparator']['iou_covered']:.3f} (Otsu comparator) and "
        f"{like[review.FROZEN_METHOD]['iou_covered']:.3f} (M1-v2)"
    ) in flat
    # Finding 7: the added clause.
    literal = derived["m1_literal"]
    assert f"above zero on {literal['tiles_with_threshold_above_zero']} of the 29 tiles" in flat
    readings = reproduction["m1_literal_step_4_readings"]
    assert f"scores IoU {readings['without_zero_clause']['iou_strict']:.3f}" in flat
    # Finding 8: Dice in the by-split tables and the per-tile range.
    assert "| Dice, strict | Dice, covered cells |" in text
    assert "25% to 44% per tile" in flat
    assert "27% to 31%" not in flat.split("## Review corrections")[0]
    # Findings 4, 5, 6 and 9.
    assert "## Decisions for the owners" in text
    assert text.index("## Decisions for the owners") < text.index("## Result in brief")
    assert "used up for this configuration" in flat
    assert "written as constants by the scripts" in flat
    assert "Every published value for the six tiles was recomputed exactly" in flat
    assert "require_frozen_m1_v2" in text
    receipt = json.loads((ROOT / review.FREEZE_RECEIPT_FILE).read_bytes())
    for digest in (receipt["frozen_config_sha256"], *receipt["code_sha256"].values()):
        assert digest in text
    assert "optimistic by construction" in flat
    for name in (
        "geoid_m1_benchmark_v2_addendum_1.json",
        "geoid_m1_benchmark_v2_derived_checks.json",
        "geoid_m1_v2_amendment_check_reproduction.json",
    ):
        assert name in text


# --- the tuning script writes what the store recorded ------------------------------


def test_tuning_script_records_opened_tiles_and_the_required_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "external"
    sample = external / "geoid_flood" / "sample" / "sample" / "geoid-flood" / bench.AOI
    sums = _write_sample(sample, bench.ALL_TILE_IDS, size=96)
    metadata = external / "geoid_flood" / "metadata"
    metadata.mkdir(parents=True)
    shutil.move(str(sums), str(metadata / "SHA256SUMS"))
    protocol = json.loads((ROOT / review.PROTOCOL_FILE).read_bytes())
    protocol["m1_v2"]["search_space"]["dimensions"] = {
        "channel": ["vh"],
        "direction": ["darkening"],
        "block_pixels": [32],
        "threshold_scope": ["per_tile", "pooled_run"],
    }
    protocol["m1_v2"]["search_space"]["runs"] = 2
    track = tmp_path / "track"
    track.mkdir()
    (track / "protocol.json").write_bytes(bench.canonical_json_bytes(protocol))

    tune = _load_script("tune_geoid_m1_v2")
    monkeypatch.setattr(tune, "PROTOCOL", track / "protocol.json")
    monkeypatch.setattr(tune, "TUNING_LOG", track / "log.jsonl")
    monkeypatch.setattr(tune, "FROZEN_CONFIG", track / "frozen.json")
    monkeypatch.setattr(tune, "FREEZE_RECEIPT", track / "receipt.json")
    monkeypatch.setattr(sys, "argv", ["tune", "--external-data", str(external), "--note", "test"])
    tune.main()

    records = [
        json.loads(line)
        for line in (track / "log.jsonl").read_bytes().decode("utf-8").splitlines()
    ]
    assert [record["record"] for record in records] == ["session_start", "run", "run", "selection"]
    development = [bench.tile_name(tile) for tile in bench.DEVELOPMENT_TILE_IDS]
    session = records[0]
    assert records[1]["development_iou_strict"] > 0.9
    assert records[1]["development_abstained_tiles"] == 10
    assert session["tiles_opened"] == development
    assert session["test_tiles_opened"] == [] and session["tiles_refused"] == []
    for record in records:
        _required_fields(record, "2024-01-03T05:33:41Z")
    receipt = json.loads((track / "receipt.json").read_bytes())
    _required_fields(receipt, "2024-01-03T05:33:41Z")
    assert receipt["tiles_opened"] == development
    assert receipt["test_tiles_opened"] == []
    assert receipt["test_tiles_opened_before_freeze"] is False
    bench.verify_freeze_receipt(
        receipt,
        frozen_config_bytes=(track / "frozen.json").read_bytes(),
        declared_protocol_bytes=(track / "protocol.json").read_bytes(),
        tuning_log_bytes=(track / "log.jsonl").read_bytes(),
        code_bytes={name: (ROOT / name).read_bytes() for name in review.CODE_FILES},
    )
    # Tuning is closed once a frozen configuration exists.
    with pytest.raises(SystemExit, match="tuning is closed"):
        tune.main()


def test_review_files_carry_no_local_path_and_no_decision_output() -> None:
    for relative in (
        "src/floodguard/geoid_m1_review.py",
        "scripts/derive_geoid_m1_review_checks.py",
        "scripts/diagnose_geoid_m1_v2_amendment_check.py",
        "scripts/tune_geoid_m1_v2.py",
        review.ADDENDUM_FILE,
        review.DERIVED_CHECKS_FILE,
        review.AMENDMENT_CHECK_FILE,
    ):
        data = (ROOT / relative).read_bytes()
        assert b"\r" not in data, relative
        text = data.decode("utf-8")
        assert "C:/" not in text and "C:\\" not in text and "/Users/" not in text, relative
        assert "%20" not in text, relative
        if relative.endswith(".py"):
            assert "floodguard.scoring" not in text and "calculate_fpps" not in text
    assert b"\r" not in Path(__file__).read_bytes()
