import json

import numpy as np

import floodguard.landing_gate_status as gate_status
from floodguard.label_factory.multi_event_preflight import QualifiedReleaseFiles
from floodguard.observation_evaluation import (
    PARTITION_FINAL_HOLDOUT,
    assign_partition,
    evaluate_observation,
    partition_sha256,
)
from test_observation_evaluation import ELIGIBLE_GATE, _plan

FILES = QualifiedReleaseFiles(*(["unused"] * 6), review_pair_json=(), qualified_reference_json="unused",
                              reference_raster="unused", analysis_grid="unused")


def test_without_receipts_every_indicator_is_closed():
    status = gate_status.build_landing_gate_status(generated_at_utc="2026-09-24T00:00:00Z")
    assert status["official_warning"] is False
    assert list(status["criteria"]) == list(gate_status.CRITERIA)
    assert all(c["met"] is False and c["receipt_sha256"] is None for c in status["criteria"].values())


def test_unreadable_reference_keeps_gate_closed(tmp_path):
    bad = tmp_path / "release.json"
    bad.write_text("{}", encoding="utf-8")
    status = gate_status.build_landing_gate_status(qualified_reference_release=bad)
    assert status["criteria"]["qualified_reference_mask"]["met"] is False


def test_fixture_only_label_release_keeps_blind_review_closed(monkeypatch):
    monkeypatch.setattr(gate_status, "revalidate_qualified_release_files",
                        lambda files: {"eligible_for_real_experiment": False, "status": "validated_synthetic_fixture_only"})
    status = gate_status.build_landing_gate_status(qualified_release_files=FILES)
    assert status["criteria"]["blind_review_and_adjudication"]["met"] is False
    assert "fixture" in status["criteria"]["blind_review_and_adjudication"]["reason"]


def _holdout_result(tmp_path):
    plan = _plan()
    ref = np.ones((60, 60), dtype=int)
    partition = assign_partition((60, 60), pixel_size_m=10, block_size_m=100, halo_m=10, seed="seed-1", development_fraction=0.5)
    opening = {"status": "signed_opening_verified_preflight_only", "receipt_sha256": "c" * 64,
               "signed_payload": {"final_holdout_partition_sha256": partition_sha256(partition, PARTITION_FINAL_HOLDOUT),
                                  "qualified_release_set_sha256": "b" * 64}}
    result = evaluate_observation(plan, ELIGIBLE_GATE, ref, ref, role="final_holdout", holdout_opening=opening, source_timestamp="t")
    plan_path, result_path = tmp_path / "plan.json", tmp_path / "result.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    result_path.write_text(json.dumps(result), encoding="utf-8")
    return plan_path, result_path, result


def test_holdout_turns_on_only_with_eligible_labels_and_untampered_result(tmp_path, monkeypatch):
    plan_path, result_path, result = _holdout_result(tmp_path)
    monkeypatch.setattr(gate_status, "revalidate_qualified_release_files", lambda files: dict(ELIGIBLE_GATE))
    status = gate_status.build_landing_gate_status(qualified_release_files=FILES, evaluation_plan=plan_path, final_holdout_result=result_path)
    assert status["criteria"]["blind_review_and_adjudication"]["met"] is True
    assert status["criteria"]["frozen_holdout_and_calibration"]["met"] is True
    assert status["criteria"]["frozen_holdout_and_calibration"]["receipt_sha256"] == result["result_sha256"]

    tampered = dict(result)
    tampered["metrics"] = dict(result["metrics"], iou=0.99)
    result_path.write_text(json.dumps(tampered), encoding="utf-8")
    status = gate_status.build_landing_gate_status(qualified_release_files=FILES, evaluation_plan=plan_path, final_holdout_result=result_path)
    assert status["criteria"]["frozen_holdout_and_calibration"]["met"] is False


def test_holdout_cannot_count_without_the_blind_review_gate(tmp_path):
    plan_path, result_path, _ = _holdout_result(tmp_path)
    status = gate_status.build_landing_gate_status(evaluation_plan=plan_path, final_holdout_result=result_path)
    assert status["criteria"]["frozen_holdout_and_calibration"]["met"] is False
