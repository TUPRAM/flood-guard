"""Separate automated observation evaluation and one-use holdout tests."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import observation_evaluation as automated_evaluation
from floodguard.observation_evaluation import (
    AUTOMATED_INTERPRETATION,
    ObservationEvaluationError,
    canonical_sha256,
    evaluate_against_automated_reference,
    validate_automated_evaluation_result,
    validate_automated_preregistration,
    verify_automated_preregistration_commit,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMIT = "77833df9d595429c1cf903c9a841e86aa8668b79"
PREREG = REPO_ROOT / "docs/proposal_execution/automated_track/preregistration_v1.json"


@pytest.fixture
def synthetic_commit(monkeypatch):
    """Synthetic tiny-grid plans exercise math without asserting a Git commit."""

    monkeypatch.setattr(automated_evaluation, "verify_automated_preregistration_commit", lambda *_: COMMIT)


def _plan():
    plan = json.loads(PREREG.read_text(encoding="utf-8"))
    plan["partition"] = {"block_size_m": 100, "halo_m": 10, "seed": "seed-1", "development_fraction": 0.5}
    plan["preregistration_sha256"] = canonical_sha256({k: v for k, v in plan.items() if k != "preregistration_sha256"})
    return plan


def _reference(plan):
    receipt = {
        "schema": "floodguard.automated_optical_reference.v1",
        "preregistration_sha256": plan["preregistration_sha256"],
        "preregistration_commit": COMMIT,
        "label_raster_sha256": "b" * 64,
        "human_reviewed": False,
        "official_warning": False,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def _candidates(plan):
    rasters = {}
    sources = {}
    for declared in plan["candidate_products"]:
        identifier = declared["product_id"]
        rasters[identifier] = np.full((60, 60), 255 if "m2" in identifier else 0, dtype=np.uint8)
        native = declared["native_pixel_size_m"]
        sources[identifier] = {
            "source_raster_sha256": declared["raster_sha256"],
            "source_receipt_sha256": declared["source_receipt_sha256"],
            "source_grid": {"crs": "EPSG:32647", "width": 60, "height": 60, "transform": [native, 0, 0, 0, -native, native * 60], "nodata": 255},
            "source_bounds": [0.0, 0.0, float(native * 60), float(native * 60)],
            "source_timestamp": "2024-09-15T23:16:01Z",
        }
    return rasters, sources


def _evaluate(plan, reference, role, *, development=None, ledger=None):
    rasters, sources = _candidates(plan)
    return evaluate_against_automated_reference(
        plan, reference, np.ones((60, 60), dtype=np.uint8), rasters, sources,
        role=role, preregistration_commit_sha=COMMIT, reference_raster_sha256="b" * 64,
        development_result=development, external_ledger_dir=ledger,
    )


def _final_evidence(tmp_path):
    plan = _plan()
    reference = _reference(plan)
    development = _evaluate(plan, reference, "development")
    development_path = tmp_path / "development.json"
    development_path.write_text(json.dumps(development), encoding="utf-8")
    final = _evaluate(plan, reference, "final_holdout", development=development, ledger=tmp_path)
    marker_path, = tmp_path.glob("automated_holdout_consumption-*.json")
    return plan, reference, development_path, final, marker_path


def test_committed_preregistration_self_hash_and_git_content_verify():
    committed = json.loads(PREREG.read_text(encoding="utf-8"))
    validate_automated_preregistration(committed)
    assert verify_automated_preregistration_commit(committed, COMMIT, REPO_ROOT) == COMMIT
    changed = copy.deepcopy(committed)
    changed["acceptance_limits"]["min_iou"] = 0.9
    changed["preregistration_sha256"] = canonical_sha256({k: v for k, v in changed.items() if k != "preregistration_sha256"})
    with pytest.raises(ObservationEvaluationError, match="differs from committed"):
        verify_automated_preregistration_commit(changed, COMMIT, REPO_ROOT)


def test_preregistration_or_reference_hash_mismatch_refuses_before_metrics(synthetic_commit):
    plan = _plan()
    reference = _reference(plan)
    broken = copy.deepcopy(plan)
    broken["acceptance_limits"]["min_iou"] = 0.9
    with pytest.raises(ObservationEvaluationError, match="pre-registration self-hash"):
        _evaluate(broken, reference, "development")
    broken_reference = dict(reference, label_raster_sha256="c" * 64)
    with pytest.raises(ObservationEvaluationError, match="reference receipt self-hash"):
        _evaluate(plan, broken_reference, "development")
    with pytest.raises(ObservationEvaluationError, match="reference raster hash"):
        rasters, sources = _candidates(plan)
        evaluate_against_automated_reference(
            plan, reference, np.ones((60, 60), dtype=np.uint8), rasters, sources,
            role="development", preregistration_commit_sha=COMMIT,
            reference_raster_sha256="c" * 64,
        )


def test_both_predeclared_candidates_required_and_source_hashes_frozen(synthetic_commit):
    plan = _plan()
    reference = _reference(plan)
    rasters, sources = _candidates(plan)
    rasters.pop(next(iter(rasters)))
    with pytest.raises(ObservationEvaluationError, match="both predeclared candidates"):
        evaluate_against_automated_reference(
            plan, reference, np.ones((60, 60), dtype=np.uint8), rasters, sources,
            role="development", preregistration_commit_sha=COMMIT, reference_raster_sha256="b" * 64,
        )
    rasters, sources = _candidates(plan)
    sources[next(iter(sources))]["source_raster_sha256"] = "f" * 64
    with pytest.raises(ObservationEvaluationError, match="source hashes differ"):
        evaluate_against_automated_reference(
            plan, reference, np.ones((60, 60), dtype=np.uint8), rasters, sources,
            role="development", preregistration_commit_sha=COMMIT, reference_raster_sha256="b" * 64,
        )


def test_development_then_one_final_holdout_contains_both_candidates(tmp_path, synthetic_commit):
    plan = _plan()
    reference = _reference(plan)
    development = _evaluate(plan, reference, "development")
    validate_automated_evaluation_result(development, plan, reference)
    assert development["metric_interpretation"] == AUTOMATED_INTERPRETATION
    assert development["human_reviewed"] is False
    assert development["can_feed_decision_layer"] is False
    assert development["accepted_observation"] is False
    assert development["official_warning"] is False
    m2_id, amplitude_id = [candidate["product_id"] for candidate in plan["candidate_products"]]
    assert development["candidate_results"][m2_id]["metrics"]["evaluated_coverage"] == 0
    assert development["candidate_results"][m2_id]["acceptance"]["meets_predeclared_limits"] is False
    amplitude = development["candidate_results"][amplitude_id]
    assert amplitude["possible_recession_candidate_cells"] == amplitude["metrics"]["confusion"]["false_negative"]
    assert amplitude["possible_recession_candidate_cells"] > 0

    with pytest.raises(ObservationEvaluationError, match="prior development result"):
        _evaluate(plan, reference, "final_holdout", ledger=tmp_path)
    final = _evaluate(plan, reference, "final_holdout", development=development, ledger=tmp_path)
    development_path = tmp_path / "development.json"
    development_path.write_text(json.dumps(development), encoding="utf-8")
    markers = list(tmp_path.glob("automated_holdout_consumption-*.json"))
    assert len(markers) == 1
    validate_automated_evaluation_result(
        final, plan, reference, development_result=development_path, holdout_marker=markers[0],
    )
    assert set(final["candidate_results"]) == {m2_id, amplitude_id}
    marker_bytes = markers[0].read_bytes()
    with pytest.raises(ObservationEvaluationError, match="already been consumed"):
        _evaluate(plan, reference, "final_holdout", development=development, ledger=tmp_path)
    assert markers[0].read_bytes() == marker_bytes


def test_tampered_automated_result_refuses_validation(synthetic_commit):
    plan = _plan()
    reference = _reference(plan)
    result = _evaluate(plan, reference, "development")
    result["human_reviewed"] = True
    with pytest.raises(ObservationEvaluationError, match="self-hash"):
        validate_automated_evaluation_result(result, plan, reference)


def test_bad_candidate_metadata_cannot_consume_holdout(tmp_path, synthetic_commit):
    plan = _plan()
    reference = _reference(plan)
    development = _evaluate(plan, reference, "development")
    rasters, sources = _candidates(plan)
    identifier = next(iter(sources))
    del sources[identifier]["source_timestamp"]
    with pytest.raises(ObservationEvaluationError, match="source timestamp"):
        evaluate_against_automated_reference(
            plan, reference, np.ones((60, 60), dtype=np.uint8), rasters, sources,
            role="final_holdout", preregistration_commit_sha=COMMIT,
            reference_raster_sha256="b" * 64, development_result=development,
            external_ledger_dir=tmp_path,
        )
    assert not list(tmp_path.iterdir())


def test_direct_evaluator_refuses_uncommitted_plan_before_metrics_or_marker(tmp_path):
    plan = _plan()
    reference = _reference(plan)
    with pytest.raises(ObservationEvaluationError, match="differs from committed"):
        _evaluate(plan, reference, "final_holdout", ledger=tmp_path)
    assert not list(tmp_path.iterdir())


def test_final_result_requires_actual_marker_and_development_file(tmp_path, synthetic_commit):
    plan, reference, development_path, final, marker_path = _final_evidence(tmp_path)
    with pytest.raises(ObservationEvaluationError, match="requires development result and holdout marker"):
        validate_automated_evaluation_result(final, plan, reference)
    with pytest.raises(ObservationEvaluationError, match="holdout marker is missing"):
        validate_automated_evaluation_result(
            final, plan, reference, development_result=development_path,
            holdout_marker=tmp_path / "missing.json",
        )
    with pytest.raises(ObservationEvaluationError, match="development result file is missing"):
        validate_automated_evaluation_result(
            final, plan, reference, development_result=tmp_path / "missing-development.json",
            holdout_marker=marker_path,
        )


def test_forged_self_consistent_final_consumption_hash_refuses(tmp_path, synthetic_commit):
    plan, reference, development_path, final, marker_path = _final_evidence(tmp_path)
    forged = copy.deepcopy(final)
    forged["automated_holdout_consumption_sha256"] = "f" * 64
    forged["result_sha256"] = canonical_sha256({k: v for k, v in forged.items() if k != "result_sha256"})
    with pytest.raises(ObservationEvaluationError, match="marker hash differs"):
        validate_automated_evaluation_result(
            forged, plan, reference, development_result=development_path, holdout_marker=marker_path,
        )


def test_tampered_marker_or_development_file_refuses_final(tmp_path, synthetic_commit):
    plan, reference, development_path, final, marker_path = _final_evidence(tmp_path)
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["development_result_sha256"] = "e" * 64
    marker_path.write_text(json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(ObservationEvaluationError, match="marker bindings are invalid"):
        validate_automated_evaluation_result(
            final, plan, reference, development_result=development_path, holdout_marker=marker_path,
        )
    development = json.loads(development_path.read_text(encoding="utf-8"))
    development["human_reviewed"] = True
    development_path.write_text(json.dumps(development), encoding="utf-8")
    with pytest.raises(ObservationEvaluationError, match="self-hash"):
        validate_automated_evaluation_result(
            final, plan, reference, development_result=development_path, holdout_marker=marker_path,
        )


def test_candidate_nearest_alignment_keeps_outside_and_nodata_as_abstain(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    spec = importlib.util.spec_from_file_location(
        "automated_evaluation_cli", REPO_ROOT / "scripts/evaluate_against_automated_reference.py",
    )
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    source_path = tmp_path / "candidate.tif"
    source_transform = from_origin(0, 20, 10, 10)
    with rasterio.open(
        source_path, "w", driver="GTiff", width=2, height=2, count=1,
        dtype="uint8", crs="EPSG:32647", transform=source_transform, nodata=255,
    ) as dataset:
        dataset.write(np.array([[0, 1], [255, 0]], dtype=np.uint8), 1)
    source_hash = cli._file_sha256(source_path)
    receipt = {
        "grid": {"crs": "EPSG:32647", "width": 2, "height": 2, "transform": list(tuple(source_transform)[:6])},
        "outputs": {"candidate_mask": {"sha256": source_hash}},
        "post_observed_at_utc": "2024-09-15T23:16:01Z",
    }
    receipt_path = tmp_path / "candidate_receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    declared = {
        "product_id": "test_candidate", "raster_sha256": source_hash,
        "source_receipt_sha256": cli._file_sha256(receipt_path),
        "source_receipt_kind": "candidate_receipt.json", "native_pixel_size_m": 10,
    }
    aligned, metadata = cli._read_aligned_candidate(
        source_path, receipt_path, declared, (4, 4), from_origin(-10, 30, 10, 10), rasterio.CRS.from_epsg(32647),
    )
    expected = np.full((4, 4), 255, dtype=np.uint8)
    expected[1:3, 1:3] = [[0, 1], [255, 0]]
    assert np.array_equal(aligned, expected)
    assert metadata["source_raster_sha256"] == source_hash
