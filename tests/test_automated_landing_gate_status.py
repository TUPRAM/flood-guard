"""The automated landing indicators keep receipt integrity and limit outcomes distinct."""

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import numpy as np

from floodguard.landing_gate_status import (
    AUTOMATED_CRITERIA,
    build_automated_landing_gate_status,
)
from floodguard.observation_evaluation import (
    AUTOMATED_INTERPRETATION,
    AUTOMATED_RESULT_SCHEMA,
    canonical_sha256,
    compare_to_limits,
    compute_observation_metrics,
)

ROOT = Path(__file__).resolve().parents[1]
PREREGISTRATION = ROOT / "docs/proposal_execution/automated_track/preregistration_v1.json"
PREREGISTRATION_COMMIT = "77833df9d595429c1cf903c9a841e86aa8668b79"


def _write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _context(tmp_path, monkeypatch, *, water_dice=0.7, cohen_kappa=0.6):
    plan = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    raster_path = tmp_path / "label.tif"
    raster_path.write_bytes(b"synthetic label fixture")
    reference = {
        "schema": "floodguard.automated_optical_reference.v1",
        "preregistration_sha256": plan["preregistration_sha256"],
        "preregistration_commit": PREREGISTRATION_COMMIT,
        "label_raster_sha256": hashlib.sha256(raster_path.read_bytes()).hexdigest(),
        "ab_agreement": {"water_dice": water_dice, "cohen_kappa": cohen_kappa},
        "human_reviewed": False,
        "official_warning": False,
    }
    reference["receipt_sha256"] = canonical_sha256(reference)
    module = ModuleType("floodguard.automated_reference")
    def validate_reference(receipt, *, manifest, raster_path):
        if hashlib.sha256(raster_path.read_bytes()).hexdigest() != reference["label_raster_sha256"]:
            raise ValueError("optical label raster hash mismatch")
        return reference
    module.validate_automated_reference_receipt = validate_reference
    monkeypatch.setitem(sys.modules, module.__name__, module)

    labels = np.array([[1, 0], [0, 1]], dtype=np.uint8)
    candidates = {
        "mae_sai_m2_gamma0_10m_otsu_candidate": np.full((2, 2), 255, dtype=np.uint8),
        "mae_sai_20m_amplitude_comparator": np.array([[1, 0], [1, 0]], dtype=np.uint8),
    }
    candidate_results = {}
    for product in plan["candidate_products"]:
        product_id = product["product_id"]
        metrics = compute_observation_metrics(
            labels, candidates[product_id], np.ones((2, 2), dtype=bool),
            pixel_size_m=10, boundary_tolerance_m=20,
        )
        candidate_results[product_id] = {
            "processing_variant": product["processing_variant"],
            "source_raster_sha256": product["raster_sha256"],
            "source_receipt_sha256": product["source_receipt_sha256"],
            "aligned_cells_sha256": "d" * 64,
            "source_timestamp": "2024-09-15T23:16:01Z",
            "metrics": metrics,
            "acceptance": compare_to_limits(metrics, plan["acceptance_limits"]),
            "possible_recession_candidate_cells": metrics["confusion"]["false_negative"],
        }
    result = {
        "schema": AUTOMATED_RESULT_SCHEMA,
        "preregistration_sha256": plan["preregistration_sha256"],
        "preregistration_commit_sha": PREREGISTRATION_COMMIT,
        "automated_reference_receipt_sha256": reference["receipt_sha256"],
        "reference_raster_sha256": reference["label_raster_sha256"],
        "plan_id": plan["plan_id"],
        "event_id": plan["event_id"],
        "study_area_id": plan["study_area_id"],
        "role": "final_holdout",
        "final_holdout_partition_sha256": "a" * 64,
        "automated_holdout_consumption_sha256": None,
        "development_result_sha256": None,
        "candidate_results": candidate_results,
        "metric_interpretation": AUTOMATED_INTERPRETATION,
        "source_timestamp": "2024-09-15T23:16:01Z",
        "processed_utc": "2026-09-24T10:00:02Z",
        "confidence": "Automated optical agreement for one historical event only.",
        "assumptions": ["Synthetic fixture for builder validation."],
        "evidence_tier": "preregistered_automated_evaluation",
        "reference_kind": "automated_optical_reference",
        "human_reviewed": False,
        "accepted_observation": False,
        "can_feed_decision_layer": False,
        "official_warning": False,
        "operational_status": "non_operational",
    }
    development = deepcopy(result)
    development["role"] = "development"
    development["processed_utc"] = "2026-09-24T10:00:00Z"
    development["result_sha256"] = canonical_sha256(development)
    result["development_result_sha256"] = development["result_sha256"]
    marker = {
        "schema": "floodguard.automated_holdout_consumption.v1",
        "status": "local_exclusive_consumption",
        "final_holdout_partition_sha256": result["final_holdout_partition_sha256"],
        "preregistration_sha256": plan["preregistration_sha256"],
        "preregistration_commit_sha": PREREGISTRATION_COMMIT,
        "automated_reference_receipt_sha256": reference["receipt_sha256"],
        "development_result_sha256": development["result_sha256"],
        "consumed_at_utc": "2026-09-24T10:00:01Z",
    }
    result["automated_holdout_consumption_sha256"] = canonical_sha256(marker)
    result["result_sha256"] = canonical_sha256(result)
    manifest = tmp_path / "assets.csv"
    manifest.write_text("fixture", encoding="utf-8")
    reference_path = _write_json(tmp_path / "reference.json", reference)
    result_path = _write_json(tmp_path / "result.json", result)
    development_path = _write_json(tmp_path / "development.json", development)
    marker_path = tmp_path / f"automated_holdout_consumption-{result['final_holdout_partition_sha256']}.json"
    marker_path.write_bytes((json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    return {"plan": plan, "reference": reference, "result": result, "manifest": manifest, "raster_path": raster_path,
            "reference_path": reference_path, "result_path": result_path,
            "development_path": development_path, "marker_path": marker_path}


def _build(context):
    return build_automated_landing_gate_status(
        preregistration=PREREGISTRATION,
        input_manifest=context["manifest"],
        reference_receipt=context["reference_path"],
        reference_raster=context["raster_path"],
        final_holdout_result=context["result_path"],
        development_result=context["development_path"],
        holdout_marker=context["marker_path"],
        generated_at_utc="2026-09-24T10:00:00Z",
    )


def test_missing_automated_receipts_keep_all_three_indicators_closed():
    status = build_automated_landing_gate_status(generated_at_utc="2026-09-24T10:00:00Z")
    assert status["track"] == "automated"
    assert list(status["criteria"]) == list(AUTOMATED_CRITERIA)
    assert all(not criterion["met"] for criterion in status["criteria"].values())
    assert status["candidate_agreement"] == {}
    assert status["human_reviewed"] is False
    assert status["can_feed_decision_layer"] is False


def test_verified_holdout_shows_both_candidate_states_even_when_limits_fail(tmp_path, monkeypatch):
    context = _context(tmp_path, monkeypatch, water_dice=0.4, cohen_kappa=0.2)
    status = _build(context)
    assert status["criteria"]["automated_optical_reference"]["met"] is True
    assert status["criteria"]["automated_cross_review"]["met"] is False
    assert status["criteria"]["preregistered_holdout_evaluation"]["met"] is True, status["criteria"]["preregistered_holdout_evaluation"]["reason"]
    scores = status["candidate_agreement"]
    assert scores["mae_sai_m2_gamma0_10m_otsu_candidate"]["iou"] is None
    assert scores["mae_sai_m2_gamma0_10m_otsu_candidate"]["evaluated_coverage"] == 0
    assert scores["mae_sai_20m_amplitude_comparator"]["iou"] is not None
    assert scores["mae_sai_m2_gamma0_10m_otsu_candidate"]["meets_predeclared_limits"] is False


def test_reference_pre_registration_hash_mismatch_closes_every_automated_indicator(tmp_path, monkeypatch):
    context = _context(tmp_path, monkeypatch)
    context["reference"]["preregistration_sha256"] = "0" * 64
    status = _build(context)
    assert all(not criterion["met"] for criterion in status["criteria"].values())


def test_missing_or_changed_label_raster_closes_optical_indicator(tmp_path, monkeypatch):
    context = _context(tmp_path, monkeypatch)
    missing = build_automated_landing_gate_status(
        preregistration=PREREGISTRATION,
        input_manifest=context["manifest"],
        reference_receipt=context["reference_path"],
    )
    assert missing["criteria"]["automated_optical_reference"]["met"] is False
    context["raster_path"].write_bytes(b"tampered label fixture")
    changed = _build(context)
    assert all(not criterion["met"] for criterion in changed["criteria"].values())


def test_tampered_final_result_turns_holdout_indicator_off_and_hides_scores(tmp_path, monkeypatch):
    context = _context(tmp_path, monkeypatch)
    initial = _build(context)["criteria"]["preregistered_holdout_evaluation"]
    assert initial["met"] is True, initial["reason"]
    result = context["result"]
    result["candidate_results"]["mae_sai_20m_amplitude_comparator"]["metrics"]["iou"] = 0.99
    _write_json(context["result_path"], result)
    status = _build(context)
    assert status["criteria"]["preregistered_holdout_evaluation"]["met"] is False
    assert status["candidate_agreement"] == {}


def test_missing_or_changed_holdout_marker_keeps_final_indicator_off(tmp_path, monkeypatch):
    context = _context(tmp_path, monkeypatch)
    missing = build_automated_landing_gate_status(
        preregistration=PREREGISTRATION,
        input_manifest=context["manifest"],
        reference_receipt=context["reference_path"],
        reference_raster=context["raster_path"],
        final_holdout_result=context["result_path"],
        development_result=context["development_path"],
    )
    assert missing["criteria"]["preregistered_holdout_evaluation"]["met"] is False
    assert missing["candidate_agreement"] == {}

    context["marker_path"].write_bytes(context["marker_path"].read_bytes() + b" ")
    changed = _build(context)
    assert changed["criteria"]["automated_optical_reference"]["met"] is True
    assert changed["criteria"]["preregistered_holdout_evaluation"]["met"] is False
    assert changed["candidate_agreement"] == {}


def test_automated_cli_emits_explicit_track_and_ids_without_receipts(tmp_path):
    output = tmp_path / "status.json"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_landing_gate_status.py"), "--track", "automated",
         "--output", str(output), "--generated-at", "2026-09-24T10:00:00Z"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    status = json.loads(output.read_text(encoding="utf-8"))
    assert status["track"] == "automated"
    assert list(status["criteria"]) == list(AUTOMATED_CRITERIA)


def test_automated_cli_requires_label_raster_with_reference_receipt(tmp_path):
    command = [sys.executable, str(ROOT / "scripts/build_landing_gate_status.py"), "--track", "automated",
               "--automated-reference-receipt", str(tmp_path / "reference.json"),
               "--output", str(tmp_path / "status.json")]
    result = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "--automated-reference-raster is required" in result.stderr
