"""Tests for the GEOID M1 benchmark: split, loader, scoring, strata and freeze."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from floodguard import geoid_m1_benchmark as bench
from floodguard import sar_change_v2 as sar

ROOT = Path(__file__).resolve().parents[1]
TRACK = ROOT / "docs" / "proposal_execution" / "automated_track"
PROTOCOL = TRACK / "geoid_m1_benchmark_protocol_v2.json"
FREEZE_COMMIT = "0123456789abcdef0123456789abcdef01234567"


# --- split ------------------------------------------------------------------


def test_split_matches_the_v1a_rule() -> None:
    assert len(bench.DEVELOPMENT_TILE_IDS) == 15
    assert len(bench.TEST_TILE_IDS) == 14
    assert not set(bench.DEVELOPMENT_TILE_IDS) & set(bench.TEST_TILE_IDS)
    ordered = tuple(sorted(bench.ALL_TILE_IDS))
    assert ordered[:15] == bench.DEVELOPMENT_TILE_IDS
    assert ordered[15:] == bench.TEST_TILE_IDS
    assert bench.split_of(9) == "development" and bench.split_of(33) == "development"
    assert bench.split_of(35) == "test" and bench.split_of(50) == "test"
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.split_of(11)


def test_split_is_checked_against_a_protocol_file() -> None:
    protocol = {
        "geoid_split": {
            "development_tile_ids": list(bench.DEVELOPMENT_TILE_IDS),
            "test_tile_ids": list(bench.TEST_TILE_IDS),
        }
    }
    bench.verify_split_against_protocol(protocol)
    protocol["geoid_split"]["test_tile_ids"] = list(bench.TEST_TILE_IDS[:-1])
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.verify_split_against_protocol(protocol)
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.verify_split_against_protocol({})


@pytest.mark.parametrize("tile_id", bench.TEST_TILE_IDS)
def test_tuning_refuses_every_test_tile(tile_id: int) -> None:
    with pytest.raises(bench.TestTileAccessRefused, match="held-out"):
        bench.require_access(tile_id, bench.PHASE_TUNING)


def test_access_rules_by_phase() -> None:
    for tile_id in bench.DEVELOPMENT_TILE_IDS:
        bench.require_access(tile_id, bench.PHASE_TUNING)
    assert bench.allowed_tile_ids(bench.PHASE_TUNING) == bench.DEVELOPMENT_TILE_IDS
    assert bench.allowed_tile_ids(bench.PHASE_HELD_OUT_SCORING) == bench.ALL_TILE_IDS
    for missing in (None, "", "not-a-commit", "abc123"):
        with pytest.raises(bench.TestTileAccessRefused, match="frozen"):
            bench.require_access(35, bench.PHASE_HELD_OUT_SCORING, missing)
    bench.require_access(35, bench.PHASE_HELD_OUT_SCORING, FREEZE_COMMIT)
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.require_access(9, "exploration")
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.allowed_tile_ids("exploration")


def test_tuning_store_refuses_a_test_tile_before_touching_the_disk(tmp_path: Path) -> None:
    store = bench.GeoidTileStore(
        tmp_path / "absent", tmp_path / "absent" / "SHA256SUMS", phase=bench.PHASE_TUNING
    )
    assert store.tile_ids() == bench.DEVELOPMENT_TILE_IDS
    with pytest.raises(bench.TestTileAccessRefused):
        store.read_inputs(35)
    with pytest.raises(bench.TestTileAccessRefused):
        store.read_reference(50)
    scoring = bench.GeoidTileStore(
        tmp_path / "absent", tmp_path / "absent" / "SHA256SUMS", phase=bench.PHASE_HELD_OUT_SCORING
    )
    with pytest.raises(bench.TestTileAccessRefused):
        scoring.read_reference(35)


def _write_fake_sample(root: Path, tile_ids: tuple[int, ...]) -> Path:
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    lines = []
    for tile_id in tile_ids:
        layers = {
            f"s1grd/{bench.AOI}-{tile_id}_s1grd_pre_20230908T170906.tif": np.full(
                (2, 8, 8), 0.1, dtype="float32"
            ),
            f"s1grd/{bench.AOI}-{tile_id}_s1grd_post_20240103T053341.tif": np.full(
                (2, 8, 8), 0.05, dtype="float32"
            ),
            f"label/{bench.AOI}-{tile_id}_label.tif": np.full((1, 8, 8), 2, dtype="uint8"),
            f"validity/{bench.AOI}-{tile_id}_validity.tif": np.ones((1, 8, 8), dtype="uint8"),
        }
        for relative, data in layers.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=8,
                width=8,
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


def test_store_reads_a_development_tile_and_checks_published_hashes(tmp_path: Path) -> None:
    sums = _write_fake_sample(tmp_path, (9, 35))
    store = bench.GeoidTileStore(tmp_path, sums, phase=bench.PHASE_TUNING)
    inputs = store.read_inputs(9)
    assert inputs.pre.shape == (2, 8, 8) and inputs.post.dtype == np.float32
    assert inputs.pre_acquired_utc == "2023-09-08T17:09:06Z"
    assert inputs.post_acquired_utc == "2024-01-03T05:33:41Z"
    assert len(inputs.source_sha256) == 2
    reference = store.read_reference(9)
    assert (reference.label == 2).all() and (reference.validity == 1).all()
    with pytest.raises(bench.TestTileAccessRefused):
        store.read_inputs(35)
    scoring = bench.GeoidTileStore(
        tmp_path, sums, phase=bench.PHASE_HELD_OUT_SCORING, freeze_commit=FREEZE_COMMIT
    )
    assert scoring.read_inputs(35).tile_id == 35
    tampered = [
        line.split("  ", 1)[0][::-1] + "  " + line.split("  ", 1)[1]
        for line in sums.read_text(encoding="utf-8").splitlines()
    ]
    sums.write_text("\n".join(tampered) + "\n", encoding="utf-8", newline="\n")
    changed = bench.GeoidTileStore(tmp_path, sums, phase=bench.PHASE_TUNING)
    with pytest.raises(bench.GeoidBenchmarkError, match="mismatch"):
        changed.read_inputs(9)
    with pytest.raises(bench.GeoidBenchmarkError, match="one pre and one post"):
        store.read_inputs(10)


@pytest.mark.skipif(
    not os.environ.get("FLOODGUARD_EXTERNAL_DATA"), reason="FLOODGUARD_EXTERNAL_DATA is not set"
)
def test_real_development_tile_loads_and_test_tile_is_refused() -> None:
    pytest.importorskip("rasterio")
    geoid = Path(os.environ["FLOODGUARD_EXTERNAL_DATA"]) / "geoid_flood"
    root = geoid / "sample" / "sample" / "geoid-flood" / bench.AOI
    if not root.is_dir():
        pytest.skip("The GEOID sample is not on this machine")
    store = bench.GeoidTileStore(
        root, geoid / "metadata" / "SHA256SUMS", phase=bench.PHASE_TUNING
    )
    inputs = store.read_inputs(9)
    assert inputs.pre.shape == (2, 1024, 1024)
    assert inputs.post_acquired_utc.startswith("2024-01-03T05:3")
    with pytest.raises(bench.TestTileAccessRefused):
        store.read_inputs(35)


# --- tuning and evaluation on a synthetic sample --------------------------------


def _write_synthetic_sample(root: Path) -> Path:
    """All 29 tiles at 128 by 128: every third tile has a flooded strip."""

    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    rng = np.random.default_rng(20)
    lines = []
    for position, tile_id in enumerate(bench.ALL_TILE_IDS):
        flooded = np.zeros((128, 128), dtype=bool)
        if position % 3 == 0:
            flooded[:48, :] = True
        base = np.stack([np.full((128, 128), 0.1), np.full((128, 128), 0.025)])
        pre = base * rng.gamma(4.4, 1 / 4.4, size=base.shape)
        post = np.where(flooded, base * 0.1, base) * rng.gamma(4.4, 1 / 4.4, size=base.shape)
        label = np.where(flooded, 2, 0).astype("uint8")
        label[120:, :] = 255
        label[100:110, 100:110] = 1
        validity = (label != 255).astype("uint8")
        layers = {
            f"s1grd/{bench.AOI}-{tile_id}_s1grd_pre_20230908T170906.tif": pre.astype("float32"),
            f"s1grd/{bench.AOI}-{tile_id}_s1grd_post_20240103T053341.tif": post.astype("float32"),
            f"label/{bench.AOI}-{tile_id}_label.tif": label[None],
            f"validity/{bench.AOI}-{tile_id}_validity.tif": validity[None],
        }
        for relative, data in layers.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=128,
                width=128,
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


def test_tuning_and_held_out_scoring_on_a_synthetic_sample(tmp_path: Path) -> None:
    sums = _write_synthetic_sample(tmp_path)
    tuning = bench.GeoidTileStore(tmp_path, sums, phase=bench.PHASE_TUNING)
    with pytest.raises(bench.TestTileAccessRefused):
        bench.load_tiles(tuning, bench.ALL_TILE_IDS, with_reference=True)
    loaded = bench.load_tiles(tuning, tuning.tile_ids(), with_reference=True)
    assert sorted(loaded.filtered) == sorted(bench.tile_name(i) for i in bench.DEVELOPMENT_TILE_IDS)
    assert len(loaded.input_sha256) == 15 * 4
    grid = bench.expand_search_space(
        {"channel": ["vh"], "block_pixels": [64], "threshold_scope": ["per_tile", "pooled_run"]}
    )
    runs = list(bench.tuning_runs(loaded.filtered, loaded.references, grid))
    assert [run["run_index"] for run in runs] == [1, 2]
    per_tile, pooled_run = runs
    assert per_tile["development_abstained_tiles"] == 10
    assert pooled_run["development_abstained_tiles"] == 0
    assert per_tile["development_iou_strict"] > 0.9
    assert per_tile["development_coverage"] == pytest.approx(1 / 3, abs=0.01)
    assert pooled_run["development_coverage"] == 1.0
    assert per_tile["otsu_comparator_development_iou_strict"] > 0.9
    assert set(per_tile["kittler_illingworth"]["per_tile"]) == set(loaded.filtered)
    chosen = bench.select_run(runs)
    config = sar.M1V2Config(**chosen["parameters"])

    scoring = bench.GeoidTileStore(
        tmp_path, sums, phase=bench.PHASE_HELD_OUT_SCORING, freeze_commit=FREEZE_COMMIT
    )
    rows = []
    hashes: dict[str, str] = {}
    for split in bench.SPLITS:
        split_rows, split_hashes = bench.evaluate_split(
            scoring, split, literal_config=sar.M1LiteralConfig(), config=config
        )
        rows.extend(split_rows)
        hashes.update(split_hashes)
    assert len(rows) == 29 and len(hashes) == 29 * 4
    results = bench.aggregate_results(rows)
    assert set(results) == set(bench.METHODS)
    development = results["m1_v2_kittler_illingworth"]["development"]["primary"]
    assert development["strict"]["iou"] == chosen["development_iou_strict"]
    test = results["m1_v2_kittler_illingworth"]["test"]
    assert test["tiles"] == 14 and test["primary"]["strict"]["iou"] > 0.9
    assert bench.clears_skill_bar(test["primary"])
    literal = results["m1_literal"]["test"]
    assert literal["abstained_tiles"] == 0 and literal["primary"]["coverage"] == 1.0
    assert literal["primary"]["strict"]["iou"] < test["primary"]["strict"]["iou"]
    strata = test["strata"]
    assert set(strata["by_tile_flooded_share"]) == {
        bench.FLOODED_SHARE_STRATA[0],
        bench.FLOODED_SHARE_STRATA[4],
    }
    assert sum(item["tiles"] for item in strata["by_tile_flooded_share"].values()) == 14
    assert list(strata["by_post_acquisition_slice"]) == ["2024-01-03T05:33:41Z"]
    edge, interior = (strata["by_cell_stratum"][name] for name in bench.BOUNDARY_STRATA)
    assert edge["evaluable_cells"] + interior["evaluable_cells"] == test["primary"]["evaluable_cells"]
    secondary = test["secondary"]
    assert secondary["evaluable_cells"] < test["primary"]["evaluable_cells"]
    for row in rows:
        for method in bench.METHODS:
            assert len(row["methods"][method]["candidate_sha256"]) == 64
            assert "configuration" not in row["methods"][method]["prediction"]
    json.dumps(results, allow_nan=False)
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.evaluate_split(scoring, "holdout", literal_config=sar.M1LiteralConfig(), config=config)


# --- scoring ----------------------------------------------------------------


def test_counts_and_both_readings_of_the_score() -> None:
    candidate = np.array([[1, 1, 0, 0, 255, 255, 1, 0]], dtype="uint8")
    label = np.array([[2, 0, 2, 0, 2, 0, 1, 255]], dtype="uint8")
    validity = np.array([[1, 1, 1, 1, 1, 1, 1, 1]], dtype="uint8")
    counts = bench.confusion_counts(candidate, label, validity, include_permanent_water=True)
    assert counts == {
        "true_positive": 1,
        "false_positive": 2,
        "false_negative": 1,
        "true_negative": 1,
        "evaluable_cells": 7,
        "covered_cells": 5,
        "reference_flood_cells": 3,
        "abstained_reference_flood_cells": 1,
        "abstained_reference_nonflood_cells": 1,
    }
    metrics = bench.metrics_from_counts(counts)
    assert metrics["covered"]["iou"] == pytest.approx(1 / 4)
    assert metrics["strict"]["iou"] == pytest.approx(1 / 5)
    assert metrics["covered"]["recall"] == pytest.approx(1 / 2)
    assert metrics["strict"]["recall"] == pytest.approx(1 / 3, abs=1e-6)
    assert metrics["covered"]["precision"] == metrics["strict"]["precision"]
    assert metrics["coverage"] == pytest.approx(5 / 7, abs=1e-6)
    assert metrics["abstained_cell_share"] == pytest.approx(2 / 7, abs=1e-6)
    assert metrics["predicted_to_reference_area_ratio"] == pytest.approx(1.0)
    secondary = bench.confusion_counts(candidate, label, validity, include_permanent_water=False)
    assert secondary["false_positive"] == 1 and secondary["evaluable_cells"] == 6
    scores = bench.score_candidate(candidate, label, validity)
    assert scores["primary"]["strict"]["iou"] == pytest.approx(0.2)
    assert scores["secondary"]["covered"]["iou"] == pytest.approx(1 / 3, abs=1e-6)


def test_validity_zero_and_strata_restrict_the_count() -> None:
    candidate = np.array([[1, 1, 0, 1]], dtype="uint8")
    label = np.array([[2, 2, 2, 0]], dtype="uint8")
    validity = np.array([[1, 0, 1, 1]], dtype="uint8")
    counts = bench.confusion_counts(candidate, label, validity, include_permanent_water=True)
    assert counts["evaluable_cells"] == 3 and counts["true_positive"] == 1
    within = np.array([[True, True, False, False]])
    part = bench.confusion_counts(
        candidate, label, validity, include_permanent_water=True, within=within
    )
    assert part["evaluable_cells"] == 1 and part["false_negative"] == 0


def test_undefined_ratios_are_none_and_counts_pool_before_ratios() -> None:
    empty = {key: 0 for key in bench.COUNT_KEYS}
    metrics = bench.metrics_from_counts(empty)
    assert metrics["covered"]["iou"] is None and metrics["strict"]["iou"] is None
    assert metrics["coverage"] is None and metrics["reference_flood_share"] is None
    first = {**empty, "true_positive": 1, "false_negative": 1, "evaluable_cells": 2, "covered_cells": 2, "reference_flood_cells": 2}
    second = {**empty, "true_positive": 8, "false_positive": 2, "evaluable_cells": 10, "covered_cells": 10, "reference_flood_cells": 8}
    pooled = bench.metrics_from_counts(bench.sum_counts([first, second]))
    assert pooled["covered"]["iou"] == pytest.approx(9 / 12)


def test_unknown_codes_and_shapes_are_rejected() -> None:
    good = np.zeros((2, 2), dtype="uint8")
    ones = np.ones((2, 2), dtype="uint8")
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.confusion_counts(np.full((2, 2), 7, "uint8"), good, ones, include_permanent_water=True)
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.confusion_counts(good, np.full((2, 2), 9, "uint8"), ones, include_permanent_water=True)
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.confusion_counts(good, good, np.full((2, 2), 3, "uint8"), include_permanent_water=True)
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.confusion_counts(np.zeros((2, 3), "uint8"), good, ones, include_permanent_water=True)
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.confusion_counts(
            good, good, ones, include_permanent_water=True, within=np.ones((3, 3), bool)
        )


def test_skill_bar_needs_both_readings() -> None:
    def metrics(covered: float | None, strict: float | None) -> dict[str, dict[str, float | None]]:
        return {"covered": {"iou": covered}, "strict": {"iou": strict}}

    assert bench.T2_SKILL_BAR_TEST_IOU_MIN == 0.40
    assert bench.clears_skill_bar(metrics(0.40, 0.40))
    assert not bench.clears_skill_bar(metrics(0.55, 0.39))
    assert not bench.clears_skill_bar(metrics(0.39, 0.39))
    assert not bench.clears_skill_bar(metrics(None, None))


# --- strata -------------------------------------------------------------------


def test_flooded_share_strata() -> None:
    names = bench.FLOODED_SHARE_STRATA
    assert bench.flooded_share_stratum(None) == names[0]
    assert bench.flooded_share_stratum(0.0) == names[0]
    assert bench.flooded_share_stratum(0.01) == names[1]
    assert bench.flooded_share_stratum(0.011) == names[2]
    assert bench.flooded_share_stratum(0.05) == names[2]
    assert bench.flooded_share_stratum(0.2) == names[3]
    assert bench.flooded_share_stratum(0.21) == names[4]


def test_boundary_band_follows_the_flood_edge() -> None:
    label = np.zeros((12, 12), dtype="uint8")
    label[:, :6] = 2
    validity = np.ones(label.shape, dtype="uint8")
    band = bench.boundary_band(label, validity)
    assert band[:, 4:8].all()
    assert not band[:, :4].any() and not band[:, 8:].any()
    assert not bench.boundary_band(np.zeros((6, 6), "uint8"), np.ones((6, 6), "uint8")).any()


def test_pre_event_classes_and_cell_strata_partition_the_tile() -> None:
    pre_vh = np.array([[-30.0, -22.0, -20.0, -18.0], [-15.0, -14.0, -5.0, np.nan]])
    classes = bench.pre_event_vh_classes(pre_vh)
    assert classes.tolist() == [[0, 1, 1, 2], [2, 3, 3, -1]]
    label = np.array([[2, 2, 0, 0], [2, 2, 0, 0]], dtype="uint8")
    validity = np.ones(label.shape, dtype="uint8")
    strata = bench.cell_strata(label, validity, pre_vh)
    assert set(strata) == set(bench.BOUNDARY_STRATA) | set(bench.PRE_EVENT_VH_STRATA)
    assert (strata[bench.BOUNDARY_STRATA[0]] ^ strata[bench.BOUNDARY_STRATA[1]]).all()
    assert sum(strata[name].sum() for name in bench.PRE_EVENT_VH_STRATA) == 7
    candidate = np.array([[1, 1, 0, 0], [1, 0, 0, 1]], dtype="uint8")
    counts = bench.stratum_counts(candidate, label, validity, strata)
    total = bench.sum_counts(counts[name] for name in bench.BOUNDARY_STRATA)
    assert total == bench.confusion_counts(candidate, label, validity, include_permanent_water=True)


# --- search space, selection and freeze ---------------------------------------


def test_declared_protocol_matches_the_code() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert tuple(protocol["split"]["development_tile_ids"]) == bench.DEVELOPMENT_TILE_IDS
    assert tuple(protocol["split"]["test_tile_ids"]) == bench.TEST_TILE_IDS
    assert protocol["planning_protocol_v1a_sha256"] == bench.PROTOCOL_V1A_SHA256
    assert protocol["required_statements"][0] == bench.REQUIRED_STATEMENT
    assert protocol["evaluation"]["wording"] == bench.AGREEMENT_WORDING
    assert "preregistered" not in protocol["wording"].replace("Not preregistered", "")
    grid = bench.expand_search_space(protocol["m1_v2"]["search_space"]["dimensions"])
    assert len(grid) == protocol["m1_v2"]["search_space"]["runs"] == 36
    assert grid[0] == {
        "channel": "vh",
        "direction": "darkening",
        "block_pixels": 64,
        "threshold_scope": "per_tile",
    }
    assert grid[1]["threshold_scope"] == "pooled_run"
    assert len({json.dumps(item, sort_keys=True) for item in grid}) == 36
    fixed = protocol["m1_v2"]["fixed_parameters"]
    for parameters in grid:
        config = sar.M1V2Config(**parameters)
        assert config.ashman_d_min == fixed["ashman_d_min"] == 2.0
        assert config.min_component_weight == fixed["min_component_weight"]
        assert config.equivalent_looks == fixed["equivalent_looks"]
        assert config.threshold_method == "kittler_illingworth"
    literal = sar.M1LiteralConfig()
    assert literal.speckle_window_pixels == 5 and literal.equivalent_looks == 4.4
    assert protocol["safety"]["can_feed_decision_layer"] is False


def test_expand_search_space_rejects_an_empty_dimension() -> None:
    assert bench.expand_search_space({}) == [{}]
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.expand_search_space({"channel": []})


def test_select_run_follows_the_declared_rule() -> None:
    def run(index: int, iou: float | None, coverage: float | None) -> dict[str, object]:
        return {"run_index": index, "development_iou_strict": iou, "development_coverage": coverage}

    runs = [run(1, 0.30, 1.0), run(2, 0.35, 0.5), run(3, 0.35, 0.9), run(4, 0.35, 0.9), run(5, None, 1.0)]
    assert bench.select_run(runs)["run_index"] == 3
    assert bench.select_run([run(1, None, None), run(2, 0.0, 0.0)])["run_index"] == 2
    assert bench.select_run([run(1, None, None), run(2, None, None)])["run_index"] == 1
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.select_run([])


def test_freeze_receipt_binds_config_protocol_log_and_code() -> None:
    config = bench.canonical_json_bytes({"parameters": {"channel": "vv"}})
    protocol = b"protocol"
    log = b"log\n"
    code = {"src/a.py": b"a", "src/b.py": b"b"}
    receipt = bench.build_freeze_receipt(
        frozen_config_sha256=bench.bytes_sha256(config),
        declared_protocol_sha256=bench.bytes_sha256(protocol),
        tuning_log_sha256=bench.bytes_sha256(log),
        code_sha256={name: bench.bytes_sha256(data) for name, data in code.items()},
        selected_run_id="run-01",
        frozen_at_utc="2026-10-02T00:00:00Z",
    )
    assert receipt["planning_protocol_v1a_sha256"] == bench.PROTOCOL_V1A_SHA256
    assert receipt["test_tiles_opened_before_freeze"] is False
    arguments = dict(
        frozen_config_bytes=config,
        declared_protocol_bytes=protocol,
        tuning_log_bytes=log,
        code_bytes=code,
    )
    bench.verify_freeze_receipt(receipt, **arguments)
    for field, changed in (
        ("frozen_config_bytes", config + b" "),
        ("declared_protocol_bytes", b"other"),
        ("tuning_log_bytes", log + b"x\n"),
        ("code_bytes", {**code, "src/a.py": b"changed"}),
        ("code_bytes", {"src/a.py": b"a"}),
    ):
        with pytest.raises(bench.GeoidBenchmarkError):
            bench.verify_freeze_receipt(receipt, **{**arguments, field: changed})
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.verify_freeze_receipt({**receipt, "planning_protocol_v1a_sha256": "0" * 64}, **arguments)
    with pytest.raises(bench.GeoidBenchmarkError):
        bench.verify_freeze_receipt({**receipt, "schema": "other"}, **arguments)


def test_hash_helpers_are_stable() -> None:
    assert bench.canonical_json_bytes({"b": 1, "a": 2}) == b'{\n  "a": 2,\n  "b": 1\n}\n'
    first = bench.array_sha256(np.zeros((2, 3), dtype="uint8"))
    assert first == bench.array_sha256(np.zeros((2, 3), dtype="uint8"))
    assert first != bench.array_sha256(np.zeros((3, 2), dtype="uint8"))
    assert first != bench.array_sha256(np.zeros((2, 3), dtype="int8"))


def test_scripts_and_modules_carry_no_local_path_and_no_decision_output() -> None:
    for relative in (
        "scripts/tune_geoid_m1_v2.py",
        "scripts/score_geoid_m1_benchmark.py",
        "src/floodguard/sar_change_v2.py",
        "src/floodguard/geoid_m1_benchmark.py",
    ):
        data = (ROOT / relative).read_bytes()
        assert b"\r" not in data
        text = data.decode("utf-8")
        assert "C:/" not in text and "C:\\" not in text and "/Users/" not in text
        assert "floodguard.scoring" not in text and "calculate_fpps" not in text
