from __future__ import annotations

import csv
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

import floodguard.model_promotion as model_promotion
from floodguard.model_promotion import (
    ModelPromotionError,
    REQUIRED_ERROR_CATEGORIES,
    REQUIRED_MODEL_FAMILIES,
    build_model_promotion_recommendation,
    load_model_promotion_recommendation,
    load_signed_model_promotion_policy,
    write_signed_model_promotion_policy,
)


KEY = b"promotion-policy-test-key-material-000000000000"
OTHER_KEY = b"different-promotion-test-key-00000000000000"
KEY_ID = "test-policy-key"
RESULT_KEY = b"promotion-result-test-key-material-000000000000"
RESULT_KEY_ID = "test-result-key"
RECOMMENDATION_KEY = b"promotion-recommendation-key-material-000000000"
RECOMMENDATION_KEY_ID = "test-recommendation-key"
TRUSTED_KEYS = {
    KEY_ID: KEY,
    RESULT_KEY_ID: RESULT_KEY,
    RECOMMENDATION_KEY_ID: RECOMMENDATION_KEY,
}
ISSUED = datetime(2026, 1, 1, tzinfo=UTC)
GENERATED = datetime(2026, 1, 2, tzinfo=UTC)
REVIEWED = datetime(2026, 1, 3, tzinfo=UTC)
EXPIRES = datetime(2026, 1, 10, tzinfo=UTC)

FILENAMES = {
    "metrics": "three_model_metrics.csv",
    "calibration": "three_model_calibration.csv",
    "error_categories": "three_model_error_categories.csv",
    "runtime": "three_model_runtime.csv",
}
TIE_BREAK = [
    "iou_desc",
    "f1_dice_desc",
    "precision_desc",
    "recall_desc",
    "absolute_area_error_ratio_asc",
    "brier_score_asc",
    "expected_calibration_error_asc",
    "total_seconds_asc",
    "model_id_ascending",
]
THRESHOLDS = {
    "minimum_iou": 0.60,
    "minimum_f1_dice": 0.65,
    "minimum_precision": 0.60,
    "minimum_recall": 0.60,
    "maximum_absolute_area_error_ratio": 0.30,
    "maximum_brier_score": 0.20,
    "maximum_expected_calibration_error": 0.15,
}
MODEL_IDS = {
    "deterministic_sar_baseline": "sar-baseline-v1",
    "weak_label_logistic": "logistic-v1",
    "geoai_candidate": "geoai-fpn-v1",
}


@pytest.fixture(autouse=True)
def _fixed_recommendation_signing_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep fixtures deterministic while production uses its internal UTC clock."""

    monkeypatch.setattr(model_promotion, "_utc_now", lambda: REVIEWED)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _seal(
    payload: dict[str, object],
    *,
    key: bytes = RESULT_KEY,
    key_id: str = RESULT_KEY_ID,
) -> dict[str, object]:
    sealed = dict(payload)
    sealed["signing_key_id"] = key_id
    sealed["signature_algorithm"] = "HMAC-SHA256"
    sealed["manifest_sha256"] = hashlib.sha256(_canonical_bytes(sealed)).hexdigest()
    sealed["signature"] = hmac.new(
        key, _canonical_bytes(sealed), hashlib.sha256
    ).hexdigest()
    return sealed


def _reseal(
    payload: dict[str, object], *, key: bytes, key_id: str
) -> dict[str, object]:
    unsigned = {
        field: value
        for field, value in payload.items()
        if field
        not in {
            "signing_key_id",
            "signature_algorithm",
            "manifest_sha256",
            "signature",
        }
    }
    return _seal(unsigned, key=key, key_id=key_id)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _metrics_rows(*, tied: bool = False) -> list[dict[str, object]]:
    counts = {
        "deterministic_sar_baseline": (60, 20, 20, 0),
        "weak_label_logistic": (70, 15, 10, 5),
        "geoai_candidate": (75, 5, 5, 15),
    }
    if tied:
        counts = {family: (70, 10, 10, 10) for family in REQUIRED_MODEL_FAMILIES}
    scores = {
        "deterministic_sar_baseline": (0.14, 0.10),
        "weak_label_logistic": (0.11, 0.08),
        "geoai_candidate": (0.08, 0.05),
    }
    if tied:
        scores = {family: (0.11, 0.08) for family in REQUIRED_MODEL_FAMILIES}
    rows = []
    for family in REQUIRED_MODEL_FAMILIES:
        tp, fp, fn, tn = counts[family]
        brier, ece = scores[family]
        cell_area_m2 = 25.0
        predicted_area_m2 = (tp + fp) * cell_area_m2
        reference_area_m2 = (tp + fn) * cell_area_m2
        area_error_m2 = predicted_area_m2 - reference_area_m2
        area_error_ratio = area_error_m2 / reference_area_m2
        rows.append(
            {
                "model_family": family,
                "evaluation_split": "untouched_final_spatial_holdout",
                "holdout_group_count": 2,
                "sample_count": tp + fp + fn + tn,
                "decision_threshold": 0.5,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "true_negative": tn,
                "iou": tp / (tp + fp + fn),
                "f1_dice": (2 * tp) / (2 * tp + fp + fn),
                "precision": tp / (tp + fp),
                "recall": tp / (tp + fn),
                "cell_area_m2": cell_area_m2,
                "predicted_area_m2": predicted_area_m2,
                "reference_area_m2": reference_area_m2,
                "area_error_m2": area_error_m2,
                "absolute_area_error_m2": abs(area_error_m2),
                "area_error_ratio": area_error_ratio,
                "absolute_area_error_ratio": abs(area_error_ratio),
                "brier_score": brier,
                "expected_calibration_error": ece,
                "can_feed_decision_layer": False,
            }
        )
    return rows


def _calibration_rows(*, tied: bool = False) -> list[dict[str, object]]:
    ece = {
        "deterministic_sar_baseline": 0.10,
        "weak_label_logistic": 0.08,
        "geoai_candidate": 0.05,
    }
    if tied:
        ece = {family: 0.08 for family in REQUIRED_MODEL_FAMILIES}
    rows: list[dict[str, object]] = []
    for family in REQUIRED_MODEL_FAMILIES:
        gap = ece[family]
        rows.extend(
            [
                {
                    "model_family": family,
                    "bin_index": 0,
                    "bin_lower": 0.0,
                    "bin_upper": 0.5,
                    "sample_count": 50,
                    "sample_fraction": 0.5,
                    "mean_probability": 0.1 + gap,
                    "observed_flood_rate": 0.1,
                    "absolute_gap": gap,
                },
                {
                    "model_family": family,
                    "bin_index": 1,
                    "bin_lower": 0.5,
                    "bin_upper": 1.0,
                    "sample_count": 50,
                    "sample_fraction": 0.5,
                    "mean_probability": 0.9 - gap,
                    "observed_flood_rate": 0.9,
                    "absolute_gap": gap,
                },
            ]
        )
    return rows


def _error_rows(*, tied: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    all_counts = {
        "deterministic_sar_baseline": (60, 20, 20, 0),
        "weak_label_logistic": (70, 15, 10, 5),
        "geoai_candidate": (75, 5, 5, 15),
    }
    if tied:
        all_counts = {family: (70, 10, 10, 10) for family in REQUIRED_MODEL_FAMILIES}
    for family in REQUIRED_MODEL_FAMILIES:
        tp, fp, fn, tn = all_counts[family]
        for category in ("all", *REQUIRED_ERROR_CATEGORIES):
            if category == "all":
                cell_count = tp + fp + fn + tn
                positive = tp + fn
                negative = fp + tn
                category_fp = fp
                category_fn = fn
                category_tp = tp
            else:
                cell_count = 2
                positive = 1
                negative = 1
                category_fp = 0
                category_fn = 0
                category_tp = 1
            predicted_positive = category_tp + category_fp
            rows.append(
                {
                    "model_family": family,
                    "category": category,
                    "coverage_status": "measured",
                    "cell_count": cell_count,
                    "reference_positive_count": positive,
                    "reference_negative_count": negative,
                    "false_positive_count": category_fp,
                    "false_negative_count": category_fn,
                    "false_positive_rate": (category_fp / negative if negative else ""),
                    "false_negative_rate": category_fn / positive if positive else "",
                    "precision": category_tp / predicted_positive
                    if predicted_positive
                    else "",
                    "recall": category_tp / positive if positive else "",
                }
            )
    return rows


def _runtime_rows(
    *,
    tied: bool = False,
    model_ids: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    ids = model_ids or MODEL_IDS
    seconds = {
        "deterministic_sar_baseline": 2.0,
        "weak_label_logistic": 4.0,
        "geoai_candidate": 8.0,
    }
    if tied:
        seconds = {family: 4.0 for family in REQUIRED_MODEL_FAMILIES}
    return [
        {
            "model_family": family,
            "model_id": ids[family],
            "training_seconds": 0.0,
            "calibration_seconds": 0.0,
            "inference_seconds": seconds[family],
            "total_seconds": seconds[family],
            "peak_memory_mb": 128.0,
            "device": "cpu-test-fixture",
            "hardware_class": "synthetic-test-host",
        }
        for family in REQUIRED_MODEL_FAMILIES
    ]


def _write_artifacts(
    tmp_path: Path,
    *,
    tied: bool = False,
    model_ids: dict[str, str] | None = None,
) -> dict[str, Path]:
    paths = {role: tmp_path / filename for role, filename in FILENAMES.items()}
    _write_csv(paths["metrics"], _metrics_rows(tied=tied))
    _write_csv(paths["calibration"], _calibration_rows(tied=tied))
    _write_csv(paths["error_categories"], _error_rows(tied=tied))
    _write_csv(paths["runtime"], _runtime_rows(tied=tied, model_ids=model_ids))
    return paths


def _write_policy(
    tmp_path: Path,
    *,
    thresholds: dict[str, float] | None = None,
    expires: datetime = EXPIRES,
    minimum_error_category_cell_count: int = 1,
    tied: bool = False,
) -> Path:
    del tied
    path = tmp_path / "promotion-policy.json"
    write_signed_model_promotion_policy(
        path,
        policy_id="mae-sai-promotion-policy-v1",
        experiment_id="mae-sai-controlled-v1",
        study_area="mae_sai_candidate_v1",
        issued_at_utc=ISSUED,
        expires_at_utc=expires,
        thresholds=thresholds or THRESHOLDS,
        required_error_categories=REQUIRED_ERROR_CATEGORIES,
        minimum_error_category_cell_count=minimum_error_category_cell_count,
        tie_break_order=TIE_BREAK,
        expected_artifact_filenames=FILENAMES,
        signing_key_id=KEY_ID,
        signing_key=KEY,
    )
    return path


def _result_payload(
    paths: dict[str, Path],
    *,
    policy: Path,
    signed_runtime_rows: list[dict[str, object]] | None = None,
    expires: datetime = EXPIRES,
    model_ids: dict[str, str] | None = None,
) -> dict[str, object]:
    ids = model_ids or MODEL_IDS
    policy_payload = json.loads(policy.read_text(encoding="utf-8"))
    if signed_runtime_rows is None:
        with paths["runtime"].open(encoding="utf-8", newline="") as handle:
            runtime_rows: list[dict[str, object]] = list(csv.DictReader(handle))
    else:
        runtime_rows = signed_runtime_rows
    runtime_by_family = {}
    for row in runtime_rows:
        family = str(row["model_family"])
        runtime_by_family[family] = {
            key: (
                float(row[key])
                if key
                in {
                    "training_seconds",
                    "calibration_seconds",
                    "inference_seconds",
                    "total_seconds",
                    "peak_memory_mb",
                }
                else row[key]
            )
            for key in (
                "training_seconds",
                "calibration_seconds",
                "inference_seconds",
                "total_seconds",
                "peak_memory_mb",
                "device",
                "hardware_class",
            )
        }
    partition_hashes = {
        "training_partition_sha256": _digest("training-partition"),
        "calibration_partition_sha256": _digest("calibration-partition"),
        "final_holdout_partition_sha256": _digest("final-holdout-partition"),
    }
    auxiliary_paths = {
        "calibration_curve": paths["calibration"].with_name(
            "three_model_calibration.svg"
        ),
        "summary": paths["metrics"].with_name("three_model_summary.md"),
    }
    for role, path in auxiliary_paths.items():
        if not path.exists():
            path.write_text(f"synthetic {role} fixture\n", encoding="utf-8")
    result_artifacts = {**paths, **auxiliary_paths}
    return {
        "artifact_schema": "floodguard.controlled_experiment_result.v4",
        "experiment_id": "mae-sai-controlled-v1",
        "study_area": "mae_sai_candidate_v1",
        "generated_at": GENERATED.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires_at_utc": expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "acquisition_manifest_sha256": _digest("acquisition-manifest"),
        "acquisition_authority_receipt_sha256": _digest(
            "acquisition-authority-receipt"
        ),
        "reviewer_qualification_receipt_file_sha256": _digest(
            "reviewer-qualification-file"
        ),
        "reviewer_qualification_manifest_sha256": _digest(
            "reviewer-qualification-manifest"
        ),
        "spatial_holdout_manifest_sha256": _digest("spatial-holdout-manifest"),
        "spatial_holdout_membership_sha256": _digest("spatial-holdout-membership"),
        **partition_hashes,
        "reference_cell_receipt_file_sha256": _digest("reference-cell-file"),
        "reference_cell_manifest_sha256": _digest("reference-cell-manifest"),
        "reference_cell_evidence_sha256": _digest("reference-cell-evidence"),
        "calibration_reference_file_sha256": _digest("calibration-reference"),
        "execution_authorization_receipt_file_sha256": _digest(
            "execution-authorization-file"
        ),
        "execution_authorization_manifest_sha256": _digest(
            "execution-authorization-manifest"
        ),
        "promotion_policy_manifest_sha256": policy_payload["manifest_sha256"],
        "model_evidence_manifest_sha256": _digest("model-evidence-manifest"),
        "model_ids": sorted(ids.values()),
        "models": [
            {
                "model_family": family,
                "model_id": ids[family],
                "model_contract_schema": f"floodguard.{family}.contract.v1",
                "model_artifact_file": f"{ids[family]}.bin",
                "model_artifact_sha256": _digest(f"{family}-model-artifact"),
                "model_contract_file": f"{ids[family]}-contract.json",
                "model_contract_file_sha256": _digest(f"{family}-contract-file"),
                "model_contract_sha256": _digest(f"{family}-contract-manifest"),
                "floodguard_commit": "a" * 40,
                "prediction_file": f"{ids[family]}-predictions.csv",
                "prediction_sha256": _digest(f"{family}-predictions"),
                "model_run_manifest_file": f"{ids[family]}-run.json",
                "model_run_manifest_file_sha256": _digest(f"{family}-run-file"),
                "model_run_manifest_sha256": _digest(f"{family}-run-manifest"),
                **partition_hashes,
                "decision_threshold": 0.5,
                "threshold_selection_receipt_file": (f"{ids[family]}-threshold.json"),
                "threshold_selection_receipt_file_sha256": _digest(
                    f"{family}-threshold-file"
                ),
                "threshold_selection_manifest_sha256": _digest(
                    f"{family}-threshold-manifest"
                ),
                "threshold_selection_scope": ("verified_calibration_projection_only"),
                "completed_at_utc": GENERATED.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                ),
                "runtime_profile": runtime_by_family[family],
                "runtime_evidence_status": (
                    "operator_reported_signed_not_process_measured"
                ),
                "signing_key_id": f"model-run-{family}",
            }
            for family in REQUIRED_MODEL_FAMILIES
        ],
        "artifacts": {
            role: {
                "file": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for role, path in result_artifacts.items()
        },
        "comparison_status": "completed_report_only",
        "processing_allowed": True,
        "experiment_executed": True,
        "can_feed_decision_layer": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "signing_role": "comparison_result_authority",
        "zero_division_convention": (
            "finite: 0/0=0.0; nonzero/0=1.0; otherwise numerator/denominator"
        ),
        "assumptions": ["Synthetic test evidence only."],
    }


def _write_result(
    tmp_path: Path,
    paths: dict[str, Path],
    *,
    mutate: Any | None = None,
    policy: Path | None = None,
    signed_runtime_rows: list[dict[str, object]] | None = None,
    expires: datetime = EXPIRES,
    model_ids: dict[str, str] | None = None,
    key: bytes = RESULT_KEY,
) -> Path:
    policy_path = policy or tmp_path / "promotion-policy.json"
    payload = _result_payload(
        paths,
        policy=policy_path,
        signed_runtime_rows=signed_runtime_rows,
        expires=expires,
        model_ids=model_ids,
    )
    if mutate is not None:
        mutate(payload)
    path = tmp_path / "comparison-result.json"
    _write_json(path, _seal(payload, key=key, key_id=RESULT_KEY_ID))
    return path


def _build(
    tmp_path: Path,
    *,
    policy: Path | None = None,
    result: Path | None = None,
    artifacts: dict[str, Path] | None = None,
    output: Path | None = None,
) -> Path:
    artifact_paths = artifacts or _write_artifacts(tmp_path)
    policy_path = policy or _write_policy(tmp_path)
    result_path = result or _write_result(tmp_path, artifact_paths, policy=policy_path)
    target = output or tmp_path / "promotion-recommendation.json"
    return build_model_promotion_recommendation(
        policy_path=policy_path,
        result_receipt_path=result_path,
        artifact_paths=artifact_paths,
        signing_keys=TRUSTED_KEYS,
        output_path=target,
        signing_key_id=RECOMMENDATION_KEY_ID,
        signing_key=RECOMMENDATION_KEY,
    )


def test_signed_recommendation_selects_qualified_candidate_but_stays_report_only(
    tmp_path: Path,
) -> None:
    target = _build(tmp_path)
    receipt = load_model_promotion_recommendation(target, signing_keys=TRUSTED_KEYS)

    assert receipt["recommendation_status"] == "candidate_selected"
    assert receipt["selected_candidate"]["model_family"] == "geoai_candidate"
    assert receipt["operational_status"] == "non_operational"
    assert receipt["official_warning"] is False
    assert receipt["can_feed_decision_layer"] is False
    assert receipt["requires_separate_decision_layer_acceptance"] is True
    assert set(receipt["lineage"]["artifacts"]) == set(FILENAMES)
    assert receipt["artifact_schema"] == "floodguard.model_promotion_recommendation.v3"
    assert receipt["generated_at_utc"] == "2026-01-03T00:00:00Z"
    assert "evaluated_at_utc" not in receipt


def test_no_candidate_qualified_is_a_signed_valid_outcome(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    thresholds = dict(THRESHOLDS)
    thresholds["minimum_iou"] = 0.99
    policy = _write_policy(tmp_path, thresholds=thresholds)
    result = _write_result(tmp_path, artifacts)

    receipt = load_model_promotion_recommendation(
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts),
        signing_keys=TRUSTED_KEYS,
    )
    assert receipt["recommendation_status"] == "no_candidate_qualified"
    assert receipt["selected_candidate"] is None
    assert all(not row["qualified"] for row in receipt["evaluated_models"])


def test_tie_break_ends_in_model_id_and_is_deterministic(tmp_path: Path) -> None:
    ids = {
        "deterministic_sar_baseline": "z-model",
        "weak_label_logistic": "a-model",
        "geoai_candidate": "m-model",
    }
    artifacts = _write_artifacts(tmp_path, tied=True, model_ids=ids)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts, model_ids=ids)

    receipt = load_model_promotion_recommendation(
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts),
        signing_keys=TRUSTED_KEYS,
    )
    assert receipt["selected_candidate"]["model_id"] == "a-model"


def test_policy_requires_all_explicit_thresholds_categories_and_tie_break(
    tmp_path: Path,
) -> None:
    arguments = dict(
        policy_id="policy-v1",
        experiment_id="experiment-v1",
        study_area="mae_sai_candidate_v1",
        issued_at_utc=ISSUED,
        expires_at_utc=EXPIRES,
        thresholds=THRESHOLDS,
        required_error_categories=REQUIRED_ERROR_CATEGORIES,
        minimum_error_category_cell_count=1,
        tie_break_order=TIE_BREAK,
        expected_artifact_filenames=FILENAMES,
        signing_key_id=KEY_ID,
        signing_key=KEY,
    )
    missing = dict(THRESHOLDS)
    missing.pop("minimum_precision")
    with pytest.raises(ModelPromotionError, match="missing=minimum_precision"):
        write_signed_model_promotion_policy(
            tmp_path / "missing.json", **arguments | {"thresholds": missing}
        )
    with pytest.raises(ModelPromotionError, match="canonical ordered set"):
        write_signed_model_promotion_policy(
            tmp_path / "categories.json",
            **arguments | {"required_error_categories": REQUIRED_ERROR_CATEGORIES[:-1]},
        )
    with pytest.raises(ModelPromotionError, match="end with model_id_ascending"):
        write_signed_model_promotion_policy(
            tmp_path / "tie.json", **arguments | {"tie_break_order": TIE_BREAK[:-1]}
        )


def test_policy_rejects_existing_output_and_private_filename(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path)
    with pytest.raises(ModelPromotionError, match="already exists"):
        _write_policy(tmp_path)
    policy.unlink()
    bad_files = dict(FILENAMES)
    bad_files["runtime"] = "C:\\private\\runtime.csv"
    with pytest.raises(ModelPromotionError, match="plain filename"):
        write_signed_model_promotion_policy(
            policy,
            policy_id="policy-v1",
            experiment_id="experiment-v1",
            study_area="mae_sai_candidate_v1",
            issued_at_utc=ISSUED,
            expires_at_utc=EXPIRES,
            thresholds=THRESHOLDS,
            required_error_categories=REQUIRED_ERROR_CATEGORIES,
            minimum_error_category_cell_count=1,
            tie_break_order=TIE_BREAK,
            expected_artifact_filenames=bad_files,
            signing_key_id=KEY_ID,
            signing_key=KEY,
        )


def test_policy_signature_tamper_untrusted_key_and_expiry_fail_closed(
    tmp_path: Path,
) -> None:
    policy = _write_policy(tmp_path)
    assert (
        load_signed_model_promotion_policy(
            policy, signing_keys={KEY_ID: KEY}, evaluated_at_utc=REVIEWED
        )["policy_id"]
        == "mae-sai-promotion-policy-v1"
    )
    with pytest.raises(ModelPromotionError, match="not trusted"):
        load_signed_model_promotion_policy(
            policy, signing_keys={"other": OTHER_KEY}, evaluated_at_utc=REVIEWED
        )
    payload = json.loads(policy.read_text(encoding="utf-8"))
    payload["thresholds"]["minimum_iou"] = 0.01
    _write_json(policy, payload)
    with pytest.raises(ModelPromotionError, match="self-hash"):
        load_signed_model_promotion_policy(
            policy, signing_keys={KEY_ID: KEY}, evaluated_at_utc=REVIEWED
        )

    expired = tmp_path / "expired-policy.json"
    write_signed_model_promotion_policy(
        expired,
        policy_id="expired-policy",
        experiment_id="mae-sai-controlled-v1",
        study_area="mae_sai_candidate_v1",
        issued_at_utc=ISSUED,
        expires_at_utc=datetime(2026, 1, 2, tzinfo=UTC),
        thresholds=THRESHOLDS,
        required_error_categories=REQUIRED_ERROR_CATEGORIES,
        minimum_error_category_cell_count=1,
        tie_break_order=TIE_BREAK,
        expected_artifact_filenames=FILENAMES,
        signing_key_id=KEY_ID,
        signing_key=KEY,
    )
    with pytest.raises(ModelPromotionError, match="not valid"):
        load_signed_model_promotion_policy(
            expired, signing_keys={KEY_ID: KEY}, evaluated_at_utc=REVIEWED
        )


def test_unsigned_policy_and_result_are_rejected(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path)
    unsigned_policy = json.loads(policy.read_text(encoding="utf-8"))
    unsigned_policy.pop("signature")
    _write_json(policy, unsigned_policy)
    with pytest.raises(ModelPromotionError, match="signature"):
        load_signed_model_promotion_policy(
            policy, signing_keys={KEY_ID: KEY}, evaluated_at_utc=REVIEWED
        )

    policy.unlink()
    policy = _write_policy(tmp_path)
    artifacts = _write_artifacts(tmp_path)
    result = _write_result(tmp_path, artifacts)
    unsigned_result = json.loads(result.read_text(encoding="utf-8"))
    unsigned_result.pop("signature")
    _write_json(result, unsigned_result)
    with pytest.raises(ModelPromotionError, match="signature"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_result_signature_substitution_wrong_key_and_expiry_fail_closed(
    tmp_path: Path,
) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)
    payload = json.loads(result.read_text(encoding="utf-8"))
    payload["study_area"] = "another_area"
    _write_json(result, payload)
    with pytest.raises(ModelPromotionError, match="self-hash"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)

    result.unlink()
    result = _write_result(tmp_path, artifacts, key=OTHER_KEY)
    with pytest.raises(ModelPromotionError, match="HMAC signature"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)

    result.unlink()
    result = _write_result(
        tmp_path,
        artifacts,
        expires=datetime(2026, 1, 2, 12, tzinfo=UTC),
    )
    with pytest.raises(ModelPromotionError, match="expired"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_signed_json_rejects_duplicate_keys_before_signature_evaluation(
    tmp_path: Path,
) -> None:
    policy = _write_policy(tmp_path)
    raw = policy.read_text(encoding="utf-8")
    duplicate = raw.replace(
        '"official_warning": false,',
        '"official_warning": true,\n  "official_warning": false,',
        1,
    )
    assert duplicate != raw
    policy.write_text(duplicate, encoding="utf-8")

    with pytest.raises(
        ModelPromotionError, match="duplicate JSON key: official_warning"
    ):
        load_signed_model_promotion_policy(
            policy,
            signing_keys={KEY_ID: KEY},
            evaluated_at_utc=REVIEWED,
        )


def test_promotion_authorities_cannot_reuse_a_model_executor_identity(
    tmp_path: Path,
) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path)

    def reuse_result_authority(payload: dict[str, object]) -> None:
        models = payload["models"]
        assert isinstance(models, list)
        models[0]["signing_key_id"] = RESULT_KEY_ID

    result = _write_result(
        tmp_path,
        artifacts,
        policy=policy,
        mutate=reuse_result_authority,
    )

    with pytest.raises(ModelPromotionError, match="independent of model executors"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_recommendation_rechecks_expiry_at_actual_signing_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)
    clock = iter(
        (
            REVIEWED,
            datetime(2026, 1, 11, tzinfo=UTC),
        )
    )
    monkeypatch.setattr(model_promotion, "_utc_now", lambda: next(clock))

    with pytest.raises(ModelPromotionError, match="not valid"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_promotion_cli_rejects_operator_supplied_backdated_review_time() -> None:
    arguments = [
        "recommend",
        "--policy",
        "policy.json",
        "--result-receipt",
        "result.json",
        "--metrics",
        "metrics.csv",
        "--calibration",
        "calibration.csv",
        "--error-categories",
        "errors.csv",
        "--runtime",
        "runtime.csv",
        "--evaluated-at-utc",
        "2026-01-02T00:00:00Z",
        "--trusted-key",
        "result-key=RESULT_KEY_ENV",
        "--signing-key-id",
        "promotion-key",
        "--signing-key-env",
        "PROMOTION_KEY_ENV",
        "--output",
        "recommendation.json",
    ]

    completed = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "build_controlled_model_promotion_decision.py"
            ),
            *arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "unrecognized arguments: --evaluated-at-utc" in completed.stderr


def test_promotion_policy_cli_redacts_absolute_output_path(tmp_path: Path) -> None:
    output = tmp_path / "policy.json"
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "build_controlled_model_promotion_decision.py"
    )
    arguments = [
        "policy",
        "--output",
        str(output),
        "--policy-id",
        "policy-1",
        "--experiment-id",
        "experiment-1",
        "--study-area",
        "Mae Sai",
        "--issued-at-utc",
        "2026-01-01T00:00:00Z",
        "--expires-at-utc",
        "2030-01-01T00:00:00Z",
        "--minimum-iou",
        "0.6",
        "--minimum-f1-dice",
        "0.65",
        "--minimum-precision",
        "0.6",
        "--minimum-recall",
        "0.6",
        "--maximum-absolute-area-error-ratio",
        "0.3",
        "--maximum-brier-score",
        "0.2",
        "--maximum-expected-calibration-error",
        "0.15",
        "--minimum-error-category-cell-count",
        "1",
        "--metrics-file",
        FILENAMES["metrics"],
        "--calibration-file",
        FILENAMES["calibration"],
        "--error-categories-file",
        FILENAMES["error_categories"],
        "--runtime-file",
        FILENAMES["runtime"],
        "--signing-key-id",
        KEY_ID,
        "--signing-key-env",
        "FLOODGUARD_TEST_PROMOTION_KEY",
    ]
    for category in REQUIRED_ERROR_CATEGORIES:
        arguments.extend(("--required-error-category", category))
    for criterion in TIE_BREAK:
        arguments.extend(("--tie-break", criterion))

    completed = subprocess.run(
        [sys.executable, str(script), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "FLOODGUARD_TEST_PROMOTION_KEY": KEY.decode("utf-8"),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == output.name
    assert str(tmp_path) not in completed.stdout
    assert output.exists()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.__setitem__("official_warning", True), "unsafe status"),
        (
            lambda value: value.__setitem__("can_feed_decision_layer", True),
            "unsafe status",
        ),
        (
            lambda value: value.__setitem__("candidate_selected", True),
            "promotion claims",
        ),
        (
            lambda value: value.__setitem__("notes", "C:\\Users\\reviewer\\secret.csv"),
            "private absolute path",
        ),
        (
            lambda value: value.__setitem__("notes", "/home/reviewer/secret.csv"),
            "private absolute path",
        ),
        (
            lambda value: value.__setitem__("notes", "stored in /tmp/secret.csv"),
            "private absolute path",
        ),
        (
            lambda value: value.__setitem__(
                "notes", "stored in /workspace/floodguard/private-host"
            ),
            "private absolute path",
        ),
        (
            lambda value: value.__setitem__("notes", "/usr/src/floodguard"),
            "private absolute path",
        ),
        (
            lambda value: value.__setitem__("notes", "/run/user/1000/floodguard"),
            "private absolute path",
        ),
    ],
)
def test_result_rejects_unsafe_authority_and_private_paths(
    tmp_path: Path, mutate: Any, message: str
) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts, mutate=mutate)
    with pytest.raises(ModelPromotionError, match=message):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_promotion_path_filter_allows_public_urls_and_api_routes() -> None:
    model_promotion._reject_private_paths(
        {
            "source_url": "https://example.test/public/artifact",
            "api_route": "/api/v1/status",
        }
    )


def test_artifact_checksum_and_filename_substitution_fail_closed(
    tmp_path: Path,
) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)
    artifacts["metrics"].write_text("substituted\n", encoding="utf-8")
    with pytest.raises(ModelPromotionError, match="checksum mismatch"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)

    artifacts = _write_artifacts(tmp_path)
    renamed = tmp_path / "renamed-runtime.csv"
    artifacts["runtime"].rename(renamed)
    artifacts["runtime"] = renamed
    with pytest.raises(ModelPromotionError, match="filename was substituted"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_missing_runtime_and_error_category_are_rejected(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)
    missing_runtime = dict(artifacts)
    missing_runtime.pop("runtime")
    with pytest.raises(ModelPromotionError, match="exactly metrics"):
        _build(tmp_path, policy=policy, result=result, artifacts=missing_runtime)

    error_rows = _error_rows()
    error_rows.pop()
    _write_csv(artifacts["error_categories"], error_rows)
    result.unlink()
    result = _write_result(tmp_path, artifacts)
    with pytest.raises(ModelPromotionError, match="incomplete or substituted"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_calibration_must_reproduce_reported_ece(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    rows = _calibration_rows()
    rows[0]["absolute_gap"] = 0.01
    _write_csv(artifacts["calibration"], rows)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)
    with pytest.raises(ModelPromotionError, match="does not reproduce"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_runtime_missing_column_and_incomplete_model_are_rejected(
    tmp_path: Path,
) -> None:
    artifacts = _write_artifacts(tmp_path)
    rows = _runtime_rows()
    for row in rows:
        row.pop("peak_memory_mb")
    _write_csv(artifacts["runtime"], rows)
    policy = _write_policy(tmp_path)
    result = _write_result(
        tmp_path,
        artifacts,
        signed_runtime_rows=_runtime_rows(),
    )
    with pytest.raises(ModelPromotionError, match="missing columns: peak_memory_mb"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_missing_required_metric_is_rejected(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    rows = _metrics_rows()
    for row in rows:
        row.pop("precision")
    _write_csv(artifacts["metrics"], rows)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)
    with pytest.raises(ModelPromotionError, match="missing columns: precision"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_existing_recommendation_output_is_never_overwritten(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)
    output = tmp_path / "promotion-recommendation.json"
    output.write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(ModelPromotionError, match="already exists"):
        _build(
            tmp_path,
            policy=policy,
            result=result,
            artifacts=artifacts,
            output=output,
        )


def test_recommendation_signature_tamper_is_rejected(tmp_path: Path) -> None:
    target = _build(tmp_path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["can_feed_decision_layer"] = True
    _write_json(target, payload)
    with pytest.raises(ModelPromotionError, match="self-hash"):
        load_model_promotion_recommendation(target, signing_keys=TRUSTED_KEYS)


def test_metrics_must_reproduce_signed_confusion_counts(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    rows = _metrics_rows()
    rows[0]["precision"] = 0.99
    _write_csv(artifacts["metrics"], rows)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)

    with pytest.raises(ModelPromotionError, match="precision.*confusion counts"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("decision_threshold", 0.99, "decision threshold.*signed model run"),
        ("predicted_area_m2", 9999.0, "predicted_area_m2.*confusion counts"),
        ("area_error_m2", -500.0, "area_error_m2.*confusion counts"),
    ],
)
def test_metrics_bind_signed_threshold_and_physical_area_fields(
    tmp_path: Path,
    field: str,
    value: float,
    message: str,
) -> None:
    artifacts = _write_artifacts(tmp_path)
    rows = _metrics_rows()
    rows[0][field] = value
    _write_csv(artifacts["metrics"], rows)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)

    with pytest.raises(ModelPromotionError, match=message):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_metrics_require_identical_holdout_contract_and_exact_schema(
    tmp_path: Path,
) -> None:
    for field, value in (
        ("sample_count", 101),
        ("holdout_group_count", 3),
        ("cell_area_m2", 30.0),
    ):
        case = tmp_path / field
        case.mkdir()
        artifacts = _write_artifacts(case)
        rows = _metrics_rows()
        rows[0][field] = value
        if field == "sample_count":
            rows[0]["true_negative"] = int(rows[0]["true_negative"]) + 1
        elif field == "cell_area_m2":
            tp = int(rows[0]["true_positive"])
            fp = int(rows[0]["false_positive"])
            fn = int(rows[0]["false_negative"])
            rows[0]["predicted_area_m2"] = (tp + fp) * value
            rows[0]["reference_area_m2"] = (tp + fn) * value
            rows[0]["area_error_m2"] = (fp - fn) * value
            rows[0]["absolute_area_error_m2"] = abs((fp - fn) * value)
        _write_csv(artifacts["metrics"], rows)
        policy = _write_policy(case)
        result = _write_result(case, artifacts)
        with pytest.raises(ModelPromotionError, match="same final-holdout"):
            _build(case, policy=policy, result=result, artifacts=artifacts)

    case = tmp_path / "unexpected"
    case.mkdir()
    artifacts = _write_artifacts(case)
    rows = _metrics_rows()
    for row in rows:
        row["unversioned_claim"] = "unsafe"
    _write_csv(artifacts["metrics"], rows)
    policy = _write_policy(case)
    result = _write_result(case, artifacts)
    with pytest.raises(ModelPromotionError, match="unexpected columns"):
        _build(case, policy=policy, result=result, artifacts=artifacts)


def test_calibration_fraction_must_reproduce_bin_counts(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    rows = _calibration_rows()
    rows[0]["sample_count"] = 60
    rows[1]["sample_count"] = 40
    _write_csv(artifacts["calibration"], rows)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)

    with pytest.raises(ModelPromotionError, match="sample fraction.*counts"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_all_models_must_use_the_same_calibration_bin_grid(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    rows = _calibration_rows()
    for row in rows:
        if row["model_family"] == "geoai_candidate":
            if row["bin_index"] == 0:
                row["bin_upper"] = 0.4
            else:
                row["bin_lower"] = 0.4
    _write_csv(artifacts["calibration"], rows)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)

    with pytest.raises(ModelPromotionError, match="same bin grid"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_error_category_cannot_exceed_overall_holdout(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    rows = _error_rows()
    category = rows[1]
    category.update(
        {
            "cell_count": 101,
            "reference_positive_count": 81,
            "reference_negative_count": 20,
            "false_positive_count": 0,
            "false_negative_count": 0,
            "false_positive_rate": 0.0,
            "false_negative_rate": 0.0,
            "precision": 1.0,
            "recall": 1.0,
        }
    )
    _write_csv(artifacts["error_categories"], rows)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)

    with pytest.raises(ModelPromotionError, match="exceeds overall holdout coverage"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_overall_error_row_must_reproduce_metrics(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    rows = _error_rows()
    overall = rows[0]
    overall["false_positive_count"] = 19
    overall["false_positive_rate"] = 19 / 20
    overall["precision"] = 60 / (60 + 19)
    _write_csv(artifacts["error_categories"], rows)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)

    with pytest.raises(ModelPromotionError, match="does not reproduce metrics"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_error_reference_coverage_must_match_across_models(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    rows = _error_rows()
    logistic_category = next(
        row
        for row in rows
        if row["model_family"] == "weak_label_logistic"
        and row["category"] == "permanent_water"
    )
    logistic_category.update(
        {
            "cell_count": 3,
            "reference_positive_count": 2,
            "reference_negative_count": 1,
            "false_positive_count": 0,
            "false_negative_count": 0,
            "false_positive_rate": 0.0,
            "false_negative_rate": 0.0,
            "precision": 1.0,
            "recall": 1.0,
        }
    )
    _write_csv(artifacts["error_categories"], rows)
    policy = _write_policy(tmp_path)
    result = _write_result(tmp_path, artifacts)

    with pytest.raises(ModelPromotionError, match="differs across models"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_policy_minimum_error_coverage_can_fail_all_candidates(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path, minimum_error_category_cell_count=3)
    result = _write_result(tmp_path, artifacts)

    receipt = load_model_promotion_recommendation(
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts),
        signing_keys=TRUSTED_KEYS,
    )

    assert receipt["recommendation_status"] == "no_candidate_qualified"
    assert all(
        any("insufficient coverage" in reason for reason in row["rejection_reasons"])
        for row in receipt["evaluated_models"]
    )


def test_runtime_csv_must_match_signed_model_runtime_profile(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path)

    def substitute_runtime(payload: dict[str, object]) -> None:
        payload["models"][0]["runtime_profile"]["device"] = "substituted-device"

    result = _write_result(tmp_path, artifacts, mutate=substitute_runtime)
    with pytest.raises(ModelPromotionError, match="does not match the signed"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_result_policy_lineage_and_exact_v4_schema_fail_closed(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path)
    result = _write_result(
        tmp_path,
        artifacts,
        mutate=lambda payload: payload.__setitem__(
            "promotion_policy_manifest_sha256", "0" * 64
        ),
    )
    with pytest.raises(ModelPromotionError, match="not bound to the supplied"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)

    result.unlink()
    result = _write_result(
        tmp_path,
        artifacts,
        mutate=lambda payload: payload.__setitem__("unreviewed_metadata", "safe"),
    )
    with pytest.raises(ModelPromotionError, match="fields are invalid.*extra="):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_result_model_exact_schema_rejects_signed_extra_field(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    policy = _write_policy(tmp_path)

    def add_model_field(payload: dict[str, object]) -> None:
        payload["models"][0]["unreviewed_metadata"] = "safe"

    result = _write_result(tmp_path, artifacts, mutate=add_model_field)
    with pytest.raises(ModelPromotionError, match="Result model fields are invalid"):
        _build(tmp_path, policy=policy, result=result, artifacts=artifacts)


def test_signed_recommendation_loader_rechecks_runtime_phase_total(
    tmp_path: Path,
) -> None:
    target = _build(tmp_path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["evaluated_models"][0]["runtime_profile"]["total_seconds"] = 0.5
    _write_json(
        target,
        _reseal(
            payload,
            key=RECOMMENDATION_KEY,
            key_id=RECOMMENDATION_KEY_ID,
        ),
    )

    with pytest.raises(ModelPromotionError, match="shorter than measured phases"):
        load_model_promotion_recommendation(target, signing_keys=TRUSTED_KEYS)


def test_recommendation_signing_timestamp_preserves_subsecond_precision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    precise = REVIEWED.replace(microsecond=123456)
    monkeypatch.setattr(model_promotion, "_utc_now", lambda: precise)

    receipt = load_model_promotion_recommendation(
        _build(tmp_path), signing_keys=TRUSTED_KEYS
    )

    assert receipt["generated_at_utc"] == "2026-01-03T00:00:00.123456Z"
