"""Calibration-only threshold selection for the controlled flood experiment.

This module deliberately accepts only the signed calibration projection.  It
does not accept or open the final-holdout reference-cell artifact.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
import math
from pathlib import Path

import pandas as pd

from floodguard import controlled_experiment as ce


def write_signed_threshold_selection_receipt(
    *,
    model_id: str,
    model_family: str,
    model_artifact_path: str | Path,
    model_contract_path: str | Path,
    calibration_prediction_path: str | Path,
    acquisition: ce.AcquisitionGateAssessment,
    reviewer_qualification: ce.VerifiedReviewerQualification,
    holdout: ce.VerifiedSpatialHoldout,
    calibration_reference: ce.VerifiedCalibrationReference,
    execution_authorization: ce.VerifiedExecutionAuthorization,
    execution_started_at_utc: datetime,
    training_started_at_utc: datetime,
    training_completed_at_utc: datetime,
    signing_key_id: str,
    signing_key: bytes,
    output_path: str | Path,
) -> dict[str, object]:
    """Compute and sign a deterministic threshold from calibration cells only."""

    family = ce._text(model_family, "model_family")
    if family not in ce.REQUIRED_MODEL_FAMILIES:
        raise ce.ControlledExperimentError("Unsupported controlled model family.")
    _verify_prerequisites(
        acquisition=acquisition,
        reviewer_qualification=reviewer_qualification,
        holdout=holdout,
        calibration_reference=calibration_reference,
        execution_authorization=execution_authorization,
    )
    if signing_key_id == execution_authorization.signing_key_id:
        raise ce.ControlledExperimentError(
            "Model executor and execution authority signing identities must differ."
        )
    artifact = Path(model_artifact_path)
    if not artifact.is_file():
        raise ce.ControlledExperimentError("Model artifact is missing.")
    artifact_sha = ce._file_sha256(artifact)
    contract_path = Path(model_contract_path)
    contract, contract_file_sha, contract_sha = ce._load_model_lane_contract(
        contract_path,
        family=family,
        model_id=ce._text(model_id, "model_id"),
        model_artifact_sha256=artifact_sha,
    )
    if (
        contract.get("execution_authorization_manifest_sha256")
        != execution_authorization.manifest_sha256
    ):
        raise ce.ControlledExperimentError(
            "Model lane contract is not bound to execution authorization."
        )
    execution_started = _utc(execution_started_at_utc, "execution_started_at_utc")
    training_started = _utc(training_started_at_utc, "training_started_at_utc")
    training_completed = _utc(training_completed_at_utc, "training_completed_at_utc")
    selected_at = datetime.now(UTC)
    configuration_frozen = ce._timestamp(
        contract["configuration_frozen_at_utc"], "configuration_frozen_at_utc"
    )
    if not (
        execution_authorization.authorized_at_utc
        <= configuration_frozen
        <= execution_started
        <= training_started
        <= training_completed
        <= selected_at
        <= execution_authorization.expires_at_utc
    ):
        raise ce.ControlledExperimentError(
            "Threshold-selection execution chronology is invalid."
        )
    prediction_path = Path(calibration_prediction_path)
    prediction_frame, prediction_sha = ce._read_csv_snapshot(
        prediction_path, f"{family} calibration prediction"
    )
    normalized = _validated_calibration_prediction(
        prediction_frame,
        family=family,
        holdout=holdout,
        calibration_reference=calibration_reference,
    )
    selected_threshold, selected_metrics, candidate_count = _select_threshold(
        normalized["probability_0_1"],
        calibration_reference.frame["reference_flood_extent"],
    )
    payload: dict[str, object] = {
        "artifact_schema": ce.THRESHOLD_SELECTION_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "model_id": ce._text(model_id, "model_id"),
        "model_family": family,
        "model_artifact_file": artifact.name,
        "model_artifact_sha256": artifact_sha,
        "model_contract_file": contract_path.name,
        "model_contract_file_sha256": contract_file_sha,
        "model_contract_sha256": contract_sha,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "reviewer_qualification_manifest_sha256": (
            reviewer_qualification.manifest_sha256
        ),
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "calibration_partition_sha256": holdout.calibration_partition_sha256,
        "calibration_reference_file_sha256": (
            calibration_reference.calibration_file_sha256
        ),
        "calibration_reference_parent_manifest_sha256": (
            calibration_reference.reference_manifest_sha256
        ),
        "execution_authorization_file_sha256": (
            execution_authorization.receipt_file_sha256
        ),
        "execution_authorization_manifest_sha256": (
            execution_authorization.manifest_sha256
        ),
        "calibration_prediction_file": prediction_path.name,
        "calibration_prediction_sha256": prediction_sha,
        "selection_method": "fixed_grid_max_f1_then_recall_precision_lower_threshold_v1",
        "candidate_threshold_count": candidate_count,
        "selected_threshold": selected_threshold,
        "selected_calibration_metrics": selected_metrics,
        "execution_started_at_utc": ce._format_utc(execution_started),
        "training_started_at_utc": ce._format_utc(training_started),
        "training_completed_at_utc": ce._format_utc(training_completed),
        "selected_at_utc": ce._format_utc(selected_at),
        "threshold_selection_scope": "calibration_projection_only",
        "final_holdout_reference_opened": False,
        "signing_role": ce.SIGNING_ROLES["model"],
        "can_feed_decision_layer": False,
        "official_warning": False,
    }
    sealed = ce._seal_signed_payload(
        payload,
        signing_key_id=signing_key_id,
        signing_key=signing_key,
        self_hash_field="manifest_sha256",
    )
    ce._write_immutable_json(sealed, Path(output_path), "Threshold-selection receipt")
    return sealed


def load_signed_threshold_selection_receipt(
    receipt_path: str | Path,
    *,
    model_id: str,
    model_family: str,
    model_artifact_path: str | Path,
    model_contract_path: str | Path,
    calibration_prediction_path: str | Path,
    acquisition: ce.AcquisitionGateAssessment,
    reviewer_qualification: ce.VerifiedReviewerQualification,
    holdout: ce.VerifiedSpatialHoldout,
    calibration_reference: ce.VerifiedCalibrationReference,
    execution_authorization: ce.VerifiedExecutionAuthorization,
    signing_keys: Mapping[str, bytes],
) -> tuple[dict[str, object], str]:
    """Recompute threshold selection from exact signed calibration-only bytes."""

    family = ce._text(model_family, "model_family")
    _verify_prerequisites(
        acquisition=acquisition,
        reviewer_qualification=reviewer_qualification,
        holdout=holdout,
        calibration_reference=calibration_reference,
        execution_authorization=execution_authorization,
    )
    path = Path(receipt_path)
    content = ce._read_stable_bytes(path, "threshold-selection receipt")
    file_sha = hashlib.sha256(content).hexdigest()
    payload = ce._json_object_bytes(content, "threshold-selection receipt")
    required = {
        "artifact_schema",
        "experiment_id",
        "study_area",
        "model_id",
        "model_family",
        "model_artifact_file",
        "model_artifact_sha256",
        "model_contract_file",
        "model_contract_file_sha256",
        "model_contract_sha256",
        "acquisition_manifest_sha256",
        "reviewer_qualification_manifest_sha256",
        "spatial_holdout_manifest_sha256",
        "calibration_partition_sha256",
        "calibration_reference_file_sha256",
        "calibration_reference_parent_manifest_sha256",
        "execution_authorization_file_sha256",
        "execution_authorization_manifest_sha256",
        "calibration_prediction_file",
        "calibration_prediction_sha256",
        "selection_method",
        "candidate_threshold_count",
        "selected_threshold",
        "selected_calibration_metrics",
        "execution_started_at_utc",
        "training_started_at_utc",
        "training_completed_at_utc",
        "selected_at_utc",
        "threshold_selection_scope",
        "final_holdout_reference_opened",
        "signing_role",
        "can_feed_decision_layer",
        "official_warning",
        "signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "signature",
    }
    ce._exact_keys(payload, required, "threshold-selection receipt")
    if payload["artifact_schema"] != ce.THRESHOLD_SELECTION_SCHEMA:
        raise ce.ControlledExperimentError(
            "Threshold-selection receipt schema is unsupported."
        )
    ce._verify_signed_payload(payload, signing_keys, "threshold-selection receipt")
    ce._verify_self_hash(payload, "manifest_sha256", "threshold-selection receipt")
    artifact = Path(model_artifact_path)
    artifact_sha = ce._file_sha256(artifact)
    contract_path = Path(model_contract_path)
    contract, contract_file_sha, contract_sha = ce._load_model_lane_contract(
        contract_path,
        family=family,
        model_id=ce._text(model_id, "model_id"),
        model_artifact_sha256=artifact_sha,
    )
    prediction_path = Path(calibration_prediction_path)
    expected = {
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "model_id": model_id,
        "model_family": family,
        "model_artifact_file": artifact.name,
        "model_artifact_sha256": artifact_sha,
        "model_contract_file": contract_path.name,
        "model_contract_file_sha256": contract_file_sha,
        "model_contract_sha256": contract_sha,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "reviewer_qualification_manifest_sha256": reviewer_qualification.manifest_sha256,
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "calibration_partition_sha256": holdout.calibration_partition_sha256,
        "calibration_reference_file_sha256": calibration_reference.calibration_file_sha256,
        "calibration_reference_parent_manifest_sha256": (
            calibration_reference.reference_manifest_sha256
        ),
        "execution_authorization_file_sha256": (
            execution_authorization.receipt_file_sha256
        ),
        "execution_authorization_manifest_sha256": (
            execution_authorization.manifest_sha256
        ),
        "calibration_prediction_file": prediction_path.name,
    }
    for field, value in expected.items():
        if payload[field] != value:
            raise ce.ControlledExperimentError(
                f"Threshold-selection {field} was substituted."
            )
    if (
        contract["execution_authorization_manifest_sha256"]
        != execution_authorization.manifest_sha256
    ):
        raise ce.ControlledExperimentError(
            "Model lane contract is not bound to execution authorization."
        )
    prediction_frame, prediction_sha = ce._read_csv_snapshot(
        prediction_path, f"{family} calibration prediction"
    )
    if prediction_sha != ce._sha256(
        payload["calibration_prediction_sha256"], "calibration_prediction_sha256"
    ):
        raise ce.ControlledExperimentError(
            "Threshold-selection calibration prediction was substituted."
        )
    normalized = _validated_calibration_prediction(
        prediction_frame,
        family=family,
        holdout=holdout,
        calibration_reference=calibration_reference,
    )
    threshold, metrics, candidate_count = _select_threshold(
        normalized["probability_0_1"],
        calibration_reference.frame["reference_flood_extent"],
    )
    if (
        payload["selection_method"]
        != "fixed_grid_max_f1_then_recall_precision_lower_threshold_v1"
        or payload["candidate_threshold_count"] != candidate_count
        or not math.isclose(
            float(payload["selected_threshold"]), threshold, abs_tol=1e-12
        )
        or payload["selected_calibration_metrics"] != metrics
        or payload["threshold_selection_scope"] != "calibration_projection_only"
        or payload["final_holdout_reference_opened"] is not False
        or payload["signing_role"] != ce.SIGNING_ROLES["model"]
        or payload["signing_key_id"] == execution_authorization.signing_key_id
        or payload["can_feed_decision_layer"] is not False
        or payload["official_warning"] is not False
    ):
        raise ce.ControlledExperimentError(
            "Threshold-selection receipt is unsafe or not reproducible."
        )
    ce._require_distinct_trusted_credentials(
        signing_keys,
        [
            str(payload["signing_key_id"]),
            str(acquisition.authority_signing_key_id),
            reviewer_qualification.reviewer_signing_key_id,
            reviewer_qualification.adjudicator_signing_key_id,
            str(holdout.receipt["signing_key_id"]),
            calibration_reference.reference_signing_key_id,
            execution_authorization.signing_key_id,
        ],
        label="threshold-selection authority roles",
    )
    execution_started = ce._timestamp(
        payload["execution_started_at_utc"], "execution_started_at_utc"
    )
    training_started = ce._timestamp(
        payload["training_started_at_utc"], "training_started_at_utc"
    )
    training_completed = ce._timestamp(
        payload["training_completed_at_utc"], "training_completed_at_utc"
    )
    selected = ce._timestamp(payload["selected_at_utc"], "selected_at_utc")
    configuration_frozen = ce._timestamp(
        contract["configuration_frozen_at_utc"], "configuration_frozen_at_utc"
    )
    if not (
        execution_authorization.authorized_at_utc
        <= configuration_frozen
        <= execution_started
        <= training_started
        <= training_completed
        <= selected
        <= execution_authorization.expires_at_utc
    ):
        raise ce.ControlledExperimentError(
            "Threshold-selection execution chronology is invalid."
        )
    ce._reject_private_paths(payload)
    return dict(payload), file_sha


def _verify_prerequisites(
    *,
    acquisition: ce.AcquisitionGateAssessment,
    reviewer_qualification: ce.VerifiedReviewerQualification,
    holdout: ce.VerifiedSpatialHoldout,
    calibration_reference: ce.VerifiedCalibrationReference,
    execution_authorization: ce.VerifiedExecutionAuthorization,
) -> None:
    ce._verify_acquisition_assessment(acquisition)
    ce._verify_holdout_instance(holdout)
    ce._verify_holdout_acquisition_lineage(holdout.receipt, acquisition)
    if (
        reviewer_qualification._verification_marker
        is not ce._VERIFIED_REVIEWER_QUALIFICATION_MARKER
        or calibration_reference._verification_marker
        is not ce._VERIFIED_CALIBRATION_REFERENCE_MARKER
        or execution_authorization._verification_marker
        is not ce._VERIFIED_EXECUTION_AUTHORIZATION_MARKER
        or calibration_reference.experiment_id != acquisition.experiment_id
        or calibration_reference.study_area != acquisition.study_area
        or calibration_reference.reference_mask_sha256
        != acquisition.reference_mask_sha256
        or calibration_reference.reviewer_qualification_manifest_sha256
        != reviewer_qualification.manifest_sha256
        or calibration_reference.spatial_holdout_manifest_sha256
        != holdout.manifest_sha256
        or calibration_reference.calibration_partition_sha256
        != holdout.calibration_partition_sha256
        or execution_authorization.experiment_id != acquisition.experiment_id
        or execution_authorization.study_area != acquisition.study_area
        or execution_authorization.acquisition_manifest_sha256
        != acquisition.manifest_sha256
        or execution_authorization.reviewer_qualification_manifest_sha256
        != reviewer_qualification.manifest_sha256
        or execution_authorization.spatial_holdout_manifest_sha256
        != holdout.manifest_sha256
        or execution_authorization.reference_cell_manifest_sha256
        != calibration_reference.reference_manifest_sha256
    ):
        raise ce.ControlledExperimentError(
            "Threshold-selection prerequisites do not share one verified lineage."
        )


def _validated_calibration_prediction(
    frame: pd.DataFrame,
    *,
    family: str,
    holdout: ce.VerifiedSpatialHoldout,
    calibration_reference: ce.VerifiedCalibrationReference,
) -> pd.DataFrame:
    ce._require_exact_columns(
        frame, ce.PREDICTION_COLUMNS, f"{family} calibration prediction"
    )
    if frame.empty:
        raise ce.ControlledExperimentError(
            f"{family}: calibration prediction must not be empty."
        )
    normalized = frame.copy()
    for column in ("cell_id", "spatial_group_id", "split"):
        normalized[column] = normalized[column].map(
            lambda value, name=column: ce._text(value, f"calibration {name}")
        )
    if normalized["cell_id"].duplicated().any():
        raise ce.ControlledExperimentError(
            f"{family}: calibration prediction cell IDs must be unique."
        )

    def probability(value: object) -> float:
        if not ce._bounded_probability(value):
            raise ce.ControlledExperimentError(
                f"{family} calibration probability must be in [0,1]."
            )
        return float(value)

    normalized["probability_0_1"] = normalized["probability_0_1"].map(probability)
    normalized = normalized.sort_values("cell_id").reset_index(drop=True)
    expected = sorted(
        (item for item in holdout.memberships if item.split == "calibration"),
        key=lambda item: item.cell_id,
    )
    if normalized["cell_id"].tolist() != [item.cell_id for item in expected]:
        raise ce.ControlledExperimentError(
            f"{family}: calibration prediction does not exactly cover calibration cells."
        )
    if normalized["spatial_group_id"].tolist() != [
        item.spatial_group_id for item in expected
    ] or normalized["split"].tolist() != ["calibration"] * len(expected):
        raise ce.ControlledExperimentError(
            f"{family}: calibration prediction partition labels were substituted."
        )
    if (
        normalized["cell_id"].tolist()
        != calibration_reference.frame["cell_id"].tolist()
    ):
        raise ce.ControlledExperimentError(
            f"{family}: calibration prediction and reference membership differ."
        )
    return normalized


def _select_threshold(
    probability: pd.Series,
    truth: pd.Series,
) -> tuple[float, dict[str, float | int], int]:
    candidates = [index / 1000 for index in range(1001)]
    probabilities = [float(value) for value in probability]
    labels = [int(value) for value in truth]
    rows: list[tuple[float, dict[str, float | int]]] = []
    for threshold in candidates:
        predicted = [int(value >= threshold) for value in probabilities]
        true_positive = sum(
            prediction == 1 and label == 1
            for prediction, label in zip(predicted, labels, strict=True)
        )
        false_positive = sum(
            prediction == 1 and label == 0
            for prediction, label in zip(predicted, labels, strict=True)
        )
        false_negative = sum(
            prediction == 0 and label == 1
            for prediction, label in zip(predicted, labels, strict=True)
        )
        true_negative = sum(
            prediction == 0 and label == 0
            for prediction, label in zip(predicted, labels, strict=True)
        )
        metrics = {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "true_negative": true_negative,
            "f1_dice": ce._ratio(
                2 * true_positive,
                2 * true_positive + false_positive + false_negative,
            ),
            "precision": ce._ratio(
                true_positive,
                true_positive + false_positive,
            ),
            "recall": ce._ratio(
                true_positive,
                true_positive + false_negative,
            ),
        }
        rows.append((threshold, metrics))
    threshold, metrics = max(
        rows,
        key=lambda item: (
            float(item[1]["f1_dice"]),
            float(item[1]["recall"]),
            float(item[1]["precision"]),
            -item[0],
        ),
    )
    selected = {
        key: metrics[key]
        for key in (
            "true_positive",
            "false_positive",
            "false_negative",
            "true_negative",
            "f1_dice",
            "precision",
            "recall",
        )
    }
    return threshold, selected, len(candidates)


def _utc(value: datetime, label: str) -> datetime:
    return ce._timestamp(ce._format_utc(value), label)
