"""Fail-closed, report-only model promotion recommendations.

This module deliberately sits after the controlled three-model experiment.  It
does not train a model, alter FPPS, or make an output decision-layer eligible.
It verifies a predeclared signed policy, a separately signed comparison receipt,
and the exact metrics, calibration, error-category, and runtime artifacts before
issuing a signed recommendation for a later human acceptance process.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
from datetime import UTC, datetime
import hashlib
import hmac
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any


POLICY_SCHEMA = "floodguard.model_promotion_policy.v2"
RECOMMENDATION_SCHEMA = "floodguard.model_promotion_recommendation.v3"
CONTROLLED_RESULT_SCHEMA = "floodguard.controlled_experiment_result.v4"
SIGNATURE_ALGORITHM = "HMAC-SHA256"

REQUIRED_MODEL_FAMILIES = (
    "deterministic_sar_baseline",
    "weak_label_logistic",
    "geoai_candidate",
)
REQUIRED_ARTIFACT_ROLES = (
    "metrics",
    "calibration",
    "error_categories",
    "runtime",
)
RESULT_ARTIFACT_ROLES = (
    *REQUIRED_ARTIFACT_ROLES,
    "calibration_curve",
    "summary",
)
REQUIRED_ERROR_CATEGORIES = (
    "permanent_water",
    "wet_soil_agriculture",
    "radar_shadow",
    "layover_double_bounce",
    "steep_terrain",
    "urban_surface",
    "speckle",
    "narrow_channel",
    "flood_boundary_disagreement",
    "temporal_land_cover_change",
    "missing_noisy_input",
    "reference_label_uncertainty",
    "geometry_mismatch",
)
THRESHOLD_FIELDS = (
    "minimum_iou",
    "minimum_f1_dice",
    "minimum_precision",
    "minimum_recall",
    "maximum_absolute_area_error_ratio",
    "maximum_brier_score",
    "maximum_expected_calibration_error",
)
ALLOWED_TIE_BREAKERS = (
    "iou_desc",
    "f1_dice_desc",
    "precision_desc",
    "recall_desc",
    "absolute_area_error_ratio_asc",
    "brier_score_asc",
    "expected_calibration_error_asc",
    "total_seconds_asc",
    "model_id_ascending",
)

METRIC_COLUMNS = {
    "model_family",
    "evaluation_split",
    "holdout_group_count",
    "sample_count",
    "decision_threshold",
    "true_positive",
    "false_positive",
    "false_negative",
    "true_negative",
    "iou",
    "f1_dice",
    "precision",
    "recall",
    "cell_area_m2",
    "predicted_area_m2",
    "reference_area_m2",
    "area_error_m2",
    "absolute_area_error_m2",
    "area_error_ratio",
    "absolute_area_error_ratio",
    "brier_score",
    "expected_calibration_error",
    "can_feed_decision_layer",
}
CALIBRATION_COLUMNS = {
    "model_family",
    "bin_index",
    "bin_lower",
    "bin_upper",
    "sample_count",
    "sample_fraction",
    "mean_probability",
    "observed_flood_rate",
    "absolute_gap",
}
ERROR_COLUMNS = {
    "model_family",
    "category",
    "coverage_status",
    "cell_count",
    "reference_positive_count",
    "reference_negative_count",
    "false_positive_count",
    "false_negative_count",
    "false_positive_rate",
    "false_negative_rate",
    "precision",
    "recall",
}
RUNTIME_COLUMNS = {
    "model_family",
    "model_id",
    "training_seconds",
    "calibration_seconds",
    "inference_seconds",
    "total_seconds",
    "peak_memory_mb",
    "device",
    "hardware_class",
}
RUNTIME_PROFILE_FIELDS = (
    "training_seconds",
    "calibration_seconds",
    "inference_seconds",
    "total_seconds",
    "peak_memory_mb",
    "device",
    "hardware_class",
)
RESULT_RECEIPT_FIELDS = {
    "artifact_schema",
    "experiment_id",
    "study_area",
    "generated_at",
    "expires_at_utc",
    "acquisition_manifest_sha256",
    "acquisition_authority_receipt_sha256",
    "reviewer_qualification_receipt_file_sha256",
    "reviewer_qualification_manifest_sha256",
    "spatial_holdout_manifest_sha256",
    "spatial_holdout_membership_sha256",
    "training_partition_sha256",
    "calibration_partition_sha256",
    "final_holdout_partition_sha256",
    "reference_cell_receipt_file_sha256",
    "reference_cell_manifest_sha256",
    "reference_cell_evidence_sha256",
    "calibration_reference_file_sha256",
    "execution_authorization_receipt_file_sha256",
    "execution_authorization_manifest_sha256",
    "promotion_policy_manifest_sha256",
    "model_evidence_manifest_sha256",
    "model_ids",
    "models",
    "artifacts",
    "comparison_status",
    "processing_allowed",
    "experiment_executed",
    "can_feed_decision_layer",
    "official_warning",
    "operational_status",
    "signing_role",
    "zero_division_convention",
    "assumptions",
    "signing_key_id",
    "signature_algorithm",
    "manifest_sha256",
    "signature",
}
RESULT_MODEL_FIELDS = {
    "model_id",
    "model_family",
    "model_contract_schema",
    "model_artifact_file",
    "model_artifact_sha256",
    "model_contract_file",
    "model_contract_file_sha256",
    "model_contract_sha256",
    "floodguard_commit",
    "prediction_file",
    "prediction_sha256",
    "model_run_manifest_file",
    "model_run_manifest_file_sha256",
    "model_run_manifest_sha256",
    "training_partition_sha256",
    "calibration_partition_sha256",
    "final_holdout_partition_sha256",
    "decision_threshold",
    "threshold_selection_receipt_file",
    "threshold_selection_receipt_file_sha256",
    "threshold_selection_manifest_sha256",
    "threshold_selection_scope",
    "runtime_profile",
    "runtime_evidence_status",
    "completed_at_utc",
    "signing_key_id",
}
ZERO_DIVISION_CONVENTION = (
    "finite: 0/0=0.0; nonzero/0=1.0; otherwise numerator/denominator"
)

SHA256_RE = re.compile(r"[0-9a-f]{64}")
SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
PRIVATE_PATH_RE = re.compile(
    r"(?:^|[\s\"'=])(?:[A-Za-z]:[\\/]|file://|"
    r"\\\\[^\\/\s]+[\\/][^\\/\s]+|"
    r"/(?:home|Users|private|tmp|var|opt|mnt|srv|root|Volumes|data|"
    r"workspace|usr|run)(?:[\\/]|$))",
    re.IGNORECASE,
)


class ModelPromotionError(ValueError):
    """Raised when promotion-review evidence is incomplete or substituted."""


def write_signed_model_promotion_policy(
    output_path: str | Path,
    *,
    policy_id: str,
    experiment_id: str,
    study_area: str,
    issued_at_utc: datetime,
    expires_at_utc: datetime,
    thresholds: Mapping[str, float],
    required_error_categories: Sequence[str],
    minimum_error_category_cell_count: int,
    tie_break_order: Sequence[str],
    expected_artifact_filenames: Mapping[str, str],
    signing_key_id: str,
    signing_key: bytes,
) -> Path:
    """Write an immutable, HMAC-signed policy with no default thresholds."""

    target = Path(output_path)
    _reject_existing_output(target)
    issued = _require_utc(issued_at_utc, "issued_at_utc")
    expires = _require_utc(expires_at_utc, "expires_at_utc")
    if expires <= issued:
        raise ModelPromotionError("Policy expiry must be after policy issuance.")
    normalized_thresholds = _validate_thresholds(thresholds)
    normalized_categories = _validate_required_categories(required_error_categories)
    normalized_tie_break = _validate_tie_break_order(tie_break_order)
    expected = _validate_expected_artifacts(expected_artifact_filenames)
    payload: dict[str, object] = {
        "artifact_schema": POLICY_SCHEMA,
        "policy_id": _safe_id(policy_id, "policy_id"),
        "experiment_id": _safe_id(experiment_id, "experiment_id"),
        "study_area": _safe_text(study_area, "study_area"),
        "issued_at_utc": _format_utc(issued),
        "expires_at_utc": _format_utc(expires),
        "comparison_receipt_schema": CONTROLLED_RESULT_SCHEMA,
        "eligible_model_families": list(REQUIRED_MODEL_FAMILIES),
        "thresholds": normalized_thresholds,
        "required_error_categories": normalized_categories,
        "minimum_error_category_cell_count": _positive_int(
            minimum_error_category_cell_count,
            "minimum_error_category_cell_count",
        ),
        "tie_break_order": normalized_tie_break,
        "expected_artifact_filenames": expected,
        "thresholds_frozen_before_result": True,
        "selection_scope": "report_only_recommendation",
        "requires_separate_decision_layer_acceptance": True,
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "signing_role": "model_promotion_policy_authority",
    }
    sealed = _seal(payload, signing_key_id=signing_key_id, signing_key=signing_key)
    _reject_private_paths(sealed)
    _write_json_exclusive(target, sealed)
    return target


def load_signed_model_promotion_policy(
    policy_path: str | Path,
    *,
    signing_keys: Mapping[str, bytes],
    evaluated_at_utc: datetime,
) -> dict[str, object]:
    """Load and verify a signed policy at a caller-supplied review time."""

    payload, _ = _load_signed_json(
        Path(policy_path), signing_keys=signing_keys, label="promotion policy"
    )
    _validate_policy(payload, evaluated_at_utc=evaluated_at_utc)
    return payload


def build_model_promotion_recommendation(
    *,
    policy_path: str | Path,
    result_receipt_path: str | Path,
    artifact_paths: Mapping[str, str | Path],
    signing_keys: Mapping[str, bytes],
    output_path: str | Path,
    signing_key_id: str,
    signing_key: bytes,
) -> Path:
    """Verify comparison evidence and write a signed report-only recommendation.

    A selected candidate remains ineligible for the FloodGuard decision layer.
    Separate decision-layer acceptance is always required.
    """

    target = Path(output_path)
    _reject_existing_output(target)
    verification_started = _utc_now()
    policy, policy_file_sha = _load_signed_json(
        Path(policy_path), signing_keys=signing_keys, label="promotion policy"
    )
    _validate_policy(policy, evaluated_at_utc=verification_started)
    result, result_file_sha = _load_signed_json(
        Path(result_receipt_path),
        signing_keys=signing_keys,
        label="controlled comparison receipt",
    )
    _validate_result_receipt(
        result,
        policy=policy,
        evaluated_at_utc=verification_started,
    )

    snapshots = _verify_artifact_snapshots(
        artifact_paths,
        result_artifacts=result["artifacts"],
        expected_filenames=policy["expected_artifact_filenames"],
    )
    metrics = _validate_metrics(_parse_csv(snapshots["metrics"], "metrics"))
    calibration = _validate_calibration(
        _parse_csv(snapshots["calibration"], "calibration")
    )
    errors = _validate_error_categories(
        _parse_csv(snapshots["error_categories"], "error categories"),
        required_categories=policy["required_error_categories"],
    )
    runtime = _validate_runtime(_parse_csv(snapshots["runtime"], "runtime"))
    _verify_result_model_identity(result, metrics=metrics)
    _verify_runtime_model_identity(result, runtime=runtime)
    _verify_calibration_consistency(metrics=metrics, calibration=calibration)
    _verify_error_category_consistency(metrics=metrics, errors=errors)

    runtime_by_family = {row["model_family"]: row for row in runtime}
    model_ids = {
        str(row["model_family"]): str(row["model_id"]) for row in result["models"]
    }
    thresholds = policy["thresholds"]
    evaluated_models: list[dict[str, object]] = []
    for row in metrics:
        family = str(row["model_family"])
        reasons = _threshold_failures(row, thresholds)
        reasons.extend(
            _error_coverage_failures(
                family,
                errors,
                minimum_cell_count=int(policy["minimum_error_category_cell_count"]),
            )
        )
        evaluated_models.append(
            {
                "model_id": model_ids[family],
                "model_family": family,
                "metrics": {
                    key: row[key]
                    for key in (
                        "iou",
                        "f1_dice",
                        "precision",
                        "recall",
                        "absolute_area_error_ratio",
                        "brier_score",
                        "expected_calibration_error",
                    )
                },
                "runtime_profile": {
                    key: runtime_by_family[family][key]
                    for key in (
                        "training_seconds",
                        "calibration_seconds",
                        "inference_seconds",
                        "total_seconds",
                        "peak_memory_mb",
                        "device",
                        "hardware_class",
                    )
                },
                "qualified": not reasons,
                "rejection_reasons": reasons,
            }
        )
    qualified = [row for row in evaluated_models if row["qualified"] is True]
    ranked = sorted(
        qualified,
        key=lambda row: _tie_break_key(row, policy["tie_break_order"]),
    )
    if ranked:
        status = "candidate_selected"
        selected: dict[str, object] | None = {
            "model_id": ranked[0]["model_id"],
            "model_family": ranked[0]["model_family"],
            "metrics": ranked[0]["metrics"],
            "runtime_profile": ranked[0]["runtime_profile"],
        }
    else:
        status = "no_candidate_qualified"
        selected = None

    # Re-read the clock after all potentially slow artifact verification.  This
    # is the actual signing time bound into the recommendation, and it closes a
    # race where evidence could expire while checks were running.
    generated_at = _utc_now()
    _validate_policy(policy, evaluated_at_utc=generated_at)
    _validate_result_receipt(
        result,
        policy=policy,
        evaluated_at_utc=generated_at,
    )
    policy_key_id = str(policy["signing_key_id"])
    result_key_id = str(result["signing_key_id"])
    recommendation_key_id = _safe_id(signing_key_id, "signing_key_id")
    if len({policy_key_id, result_key_id, recommendation_key_id}) != 3:
        raise ModelPromotionError(
            "Policy, comparison result, and recommendation signing identities must differ."
        )
    model_executor_key_ids = {
        _safe_id(model["signing_key_id"], "model executor signing_key_id")
        for model in _sequence(result["models"], "result models")
    }
    authority_key_ids = {policy_key_id, result_key_id, recommendation_key_id}
    overlapping_roles = sorted(authority_key_ids.intersection(model_executor_key_ids))
    if overlapping_roles:
        raise ModelPromotionError(
            "Policy, comparison-result, and recommendation authorities must be "
            "independent of model executors: " + ", ".join(overlapping_roles)
        )
    _require_distinct_credentials(
        {
            policy_key_id: signing_keys.get(policy_key_id),
            result_key_id: signing_keys.get(result_key_id),
            recommendation_key_id: signing_key,
        },
        label="promotion authority roles",
    )

    artifact_evidence = {
        role: {
            "file": _basename(result["artifacts"][role]["file"], f"{role} file"),
            "sha256": _sha256(result["artifacts"][role]["sha256"], f"{role} sha256"),
        }
        for role in REQUIRED_ARTIFACT_ROLES
    }
    lineage = {
        "policy_manifest_sha256": policy["manifest_sha256"],
        "policy_file_sha256": policy_file_sha,
        "policy_signing_key_id": policy["signing_key_id"],
        "comparison_manifest_sha256": result["manifest_sha256"],
        "comparison_file_sha256": result_file_sha,
        "comparison_signing_key_id": result["signing_key_id"],
        "artifacts": artifact_evidence,
    }
    recommendation_id = (
        "promotion-review-"
        + _canonical_sha256(
            {
                "experiment_id": result["experiment_id"],
                "generated_at_utc": _format_utc(generated_at),
                "lineage": lineage,
            }
        )[:24]
    )
    payload = {
        "artifact_schema": RECOMMENDATION_SCHEMA,
        "recommendation_id": recommendation_id,
        "experiment_id": result["experiment_id"],
        "study_area": result["study_area"],
        "generated_at_utc": _format_utc(generated_at),
        "policy_id": policy["policy_id"],
        "lineage": lineage,
        "recommendation_status": status,
        "selected_candidate": selected,
        "evaluated_models": sorted(
            evaluated_models, key=lambda row: str(row["model_family"])
        ),
        "tie_break_order": list(policy["tie_break_order"]),
        "selection_scope": "report_only_recommendation",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "requires_separate_decision_layer_acceptance": True,
        "signing_role": "model_promotion_recommendation_authority",
        "assumptions": [
            "Selection applies only to the signed comparison and predeclared policy.",
            "A selected candidate is not an accepted FloodGuard decision-layer input.",
            "Agency acceptance and a separate decision-layer promotion receipt remain required.",
        ],
    }
    sealed = _seal(payload, signing_key_id=signing_key_id, signing_key=signing_key)
    _validate_recommendation(sealed)
    _reject_private_paths(sealed)
    _write_json_exclusive(target, sealed)
    return target


def load_model_promotion_recommendation(
    recommendation_path: str | Path,
    *,
    signing_keys: Mapping[str, bytes],
) -> dict[str, object]:
    """Load and verify an immutable report-only recommendation receipt."""

    payload, _ = _load_signed_json(
        Path(recommendation_path),
        signing_keys=signing_keys,
        label="model promotion recommendation",
    )
    _validate_recommendation(payload)
    lineage = _mapping(payload["lineage"], "recommendation lineage")
    _require_distinct_credentials(
        {
            str(lineage["policy_signing_key_id"]): signing_keys.get(
                str(lineage["policy_signing_key_id"])
            ),
            str(lineage["comparison_signing_key_id"]): signing_keys.get(
                str(lineage["comparison_signing_key_id"])
            ),
            str(payload["signing_key_id"]): signing_keys.get(
                str(payload["signing_key_id"])
            ),
        },
        label="promotion authority roles",
    )
    return payload


def _validate_policy(
    policy: Mapping[str, object], *, evaluated_at_utc: datetime
) -> None:
    required = {
        "artifact_schema",
        "policy_id",
        "experiment_id",
        "study_area",
        "issued_at_utc",
        "expires_at_utc",
        "comparison_receipt_schema",
        "eligible_model_families",
        "thresholds",
        "required_error_categories",
        "minimum_error_category_cell_count",
        "tie_break_order",
        "expected_artifact_filenames",
        "thresholds_frozen_before_result",
        "selection_scope",
        "requires_separate_decision_layer_acceptance",
        "operational_status",
        "official_warning",
        "can_feed_decision_layer",
        "signing_role",
        "signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "signature",
    }
    _exact_keys(policy, required, "promotion policy")
    if policy["artifact_schema"] != POLICY_SCHEMA:
        raise ModelPromotionError("Promotion policy schema is unsupported.")
    _safe_id(policy["policy_id"], "policy_id")
    _safe_id(policy["experiment_id"], "experiment_id")
    _safe_text(policy["study_area"], "study_area")
    issued = _timestamp(policy["issued_at_utc"], "policy issued_at_utc")
    expires = _timestamp(policy["expires_at_utc"], "policy expires_at_utc")
    reviewed = _require_utc(evaluated_at_utc, "evaluated_at_utc")
    if expires <= issued or reviewed < issued or reviewed > expires:
        raise ModelPromotionError("Promotion policy is not valid at review time.")
    if policy["comparison_receipt_schema"] != CONTROLLED_RESULT_SCHEMA:
        raise ModelPromotionError("Promotion policy targets another result schema.")
    if policy["eligible_model_families"] != list(REQUIRED_MODEL_FAMILIES):
        raise ModelPromotionError(
            "Policy must compare exactly the three required models."
        )
    _validate_thresholds(_mapping(policy["thresholds"], "policy thresholds"))
    _validate_required_categories(
        _sequence(policy["required_error_categories"], "required_error_categories")
    )
    _positive_int(
        policy["minimum_error_category_cell_count"],
        "minimum_error_category_cell_count",
    )
    _validate_tie_break_order(_sequence(policy["tie_break_order"], "tie_break_order"))
    _validate_expected_artifacts(
        _mapping(policy["expected_artifact_filenames"], "expected artifacts")
    )
    if (
        policy["thresholds_frozen_before_result"] is not True
        or policy["selection_scope"] != "report_only_recommendation"
        or policy["requires_separate_decision_layer_acceptance"] is not True
        or policy["operational_status"] != "non_operational"
        or policy["official_warning"] is not False
        or policy["can_feed_decision_layer"] is not False
        or policy["signing_role"] != "model_promotion_policy_authority"
    ):
        raise ModelPromotionError("Promotion policy contains unsafe authority fields.")
    _reject_private_paths(policy)


def _validate_result_receipt(
    result: Mapping[str, object],
    *,
    policy: Mapping[str, object],
    evaluated_at_utc: datetime,
) -> None:
    forbidden_claims = {
        "candidate_selected",
        "selected_candidate",
        "promoted_model_id",
        "promotion_status",
        "decision_layer_accepted",
    }
    present = sorted(forbidden_claims & set(result))
    if present:
        raise ModelPromotionError(
            "Comparison receipt must not contain promotion claims: "
            + ", ".join(present)
        )
    _exact_keys(result, RESULT_RECEIPT_FIELDS, "controlled comparison receipt")
    if result["artifact_schema"] != CONTROLLED_RESULT_SCHEMA:
        raise ModelPromotionError(
            "Controlled comparison receipt schema is unsupported."
        )
    if (
        result["experiment_id"] != policy["experiment_id"]
        or result["study_area"] != policy["study_area"]
    ):
        raise ModelPromotionError(
            "Comparison result was substituted across policy identity."
        )
    generated = _timestamp(result["generated_at"], "result generated_at")
    expires = _timestamp(result["expires_at_utc"], "result expires_at_utc")
    reviewed = _require_utc(evaluated_at_utc, "evaluated_at_utc")
    policy_issued = _timestamp(policy["issued_at_utc"], "policy issued_at_utc")
    if generated <= policy_issued:
        raise ModelPromotionError("Comparison result predates the signed policy.")
    if expires <= generated or reviewed < generated or reviewed > expires:
        raise ModelPromotionError(
            "Controlled comparison result is expired or not yet valid."
        )
    if (
        result["comparison_status"] != "completed_report_only"
        or result["processing_allowed"] is not True
        or result["experiment_executed"] is not True
        or result["can_feed_decision_layer"] is not False
        or result["official_warning"] is not False
        or result["operational_status"] != "non_operational"
        or result["signing_role"] != "comparison_result_authority"
    ):
        raise ModelPromotionError(
            "Controlled comparison receipt contains unsafe status fields."
        )
    if result["promotion_policy_manifest_sha256"] != policy["manifest_sha256"]:
        raise ModelPromotionError(
            "Comparison result is not bound to the supplied promotion policy."
        )
    for field in RESULT_RECEIPT_FIELDS:
        if field.endswith("_sha256"):
            _sha256(result[field], field)
    if result["zero_division_convention"] != ZERO_DIVISION_CONVENTION:
        raise ModelPromotionError(
            "Controlled comparison receipt uses another zero-division convention."
        )
    assumptions = _sequence(result["assumptions"], "result assumptions")
    if not assumptions or any(
        not isinstance(value, str) or not value.strip() for value in assumptions
    ):
        raise ModelPromotionError("Controlled comparison assumptions are invalid.")
    artifacts = _mapping(result["artifacts"], "result artifacts")
    _exact_keys(artifacts, set(RESULT_ARTIFACT_ROLES), "result artifacts")
    filenames: list[str] = []
    for role, record_value in artifacts.items():
        _safe_id(role, "artifact role")
        record = _mapping(record_value, f"{role} artifact")
        _exact_keys(record, {"file", "sha256"}, f"{role} artifact")
        filenames.append(_basename(record["file"], f"{role} file"))
        _sha256(record["sha256"], f"{role} sha256")
    if len(filenames) != len(set(filenames)):
        raise ModelPromotionError("Comparison artifact filenames must be unique.")
    _verify_result_models(result, generated_at=generated)
    _reject_private_paths(result)


def _verify_result_models(
    result: Mapping[str, object], *, generated_at: datetime
) -> None:
    models = _sequence(result["models"], "result models")
    if len(models) != len(REQUIRED_MODEL_FAMILIES):
        raise ModelPromotionError(
            "Comparison result must describe exactly three models."
        )
    families: list[str] = []
    ids: list[str] = []
    for value in models:
        row = _mapping(value, "result model")
        _exact_keys(row, RESULT_MODEL_FIELDS, "result model")
        family = _safe_id(row["model_family"], "model_family")
        model_id = _safe_id(row["model_id"], "model_id")
        _safe_id(row["model_contract_schema"], "model_contract_schema")
        _safe_id(row["floodguard_commit"], "floodguard_commit")
        _safe_id(row["signing_key_id"], "model signing_key_id")
        for field in (
            "model_artifact_file",
            "model_contract_file",
            "prediction_file",
            "model_run_manifest_file",
            "threshold_selection_receipt_file",
        ):
            _basename(row[field], field)
        for field in RESULT_MODEL_FIELDS:
            if field.endswith("_sha256"):
                _sha256(row[field], field)
        for field in (
            "training_partition_sha256",
            "calibration_partition_sha256",
            "final_holdout_partition_sha256",
        ):
            if row[field] != result[field]:
                raise ModelPromotionError(
                    "Comparison model partition lineage does not match the result receipt."
                )
        _bounded_float(row["decision_threshold"], "decision_threshold")
        if (
            row["threshold_selection_scope"] != "verified_calibration_projection_only"
            or row["runtime_evidence_status"]
            != "operator_reported_signed_not_process_measured"
        ):
            raise ModelPromotionError(
                "Comparison model contains unsafe threshold or runtime evidence status."
            )
        _validate_runtime_profile_mapping(
            _mapping(row["runtime_profile"], "result model runtime_profile"),
            label="result model runtime_profile",
        )
        completed_at = _timestamp(row["completed_at_utc"], "model completed_at_utc")
        if completed_at > generated_at:
            raise ModelPromotionError(
                "Comparison result predates a signed model completion time."
            )
        families.append(family)
        ids.append(model_id)
    if set(families) != set(REQUIRED_MODEL_FAMILIES) or len(set(families)) != len(
        families
    ):
        raise ModelPromotionError(
            "Comparison model families are incomplete or duplicated."
        )
    if len(set(ids)) != len(ids):
        raise ModelPromotionError("Comparison model IDs must be unique.")
    declared_ids = _sequence(result["model_ids"], "model_ids")
    if sorted(str(value) for value in declared_ids) != sorted(ids):
        raise ModelPromotionError(
            "Comparison model ID list does not match model evidence."
        )


def _verify_result_model_identity(
    result: Mapping[str, object], *, metrics: Sequence[Mapping[str, object]]
) -> None:
    result_by_family = {str(row["model_family"]): row for row in result["models"]}
    metrics_by_family = {str(row["model_family"]): row for row in metrics}
    if set(result_by_family) != set(metrics_by_family):
        raise ModelPromotionError(
            "Metrics model families do not match the signed receipt."
        )
    for family, metric in metrics_by_family.items():
        signed_threshold = float(result_by_family[family]["decision_threshold"])
        if not math.isclose(
            float(metric["decision_threshold"]),
            signed_threshold,
            abs_tol=1e-12,
        ):
            raise ModelPromotionError(
                f"Metrics decision threshold for {family} does not match the signed model run."
            )


def _verify_runtime_model_identity(
    result: Mapping[str, object], *, runtime: Sequence[Mapping[str, object]]
) -> None:
    expected = {
        str(row["model_family"]): str(row["model_id"]) for row in result["models"]
    }
    actual = {str(row["model_family"]): str(row["model_id"]) for row in runtime}
    if actual != expected:
        raise ModelPromotionError(
            "Runtime model identities do not match the signed comparison receipt."
        )
    runtime_by_family = {str(row["model_family"]): row for row in runtime}
    for model in result["models"]:
        family = str(model["model_family"])
        signed = _validate_runtime_profile_mapping(
            _mapping(model["runtime_profile"], "signed runtime profile"),
            label="signed runtime profile",
        )
        artifact = runtime_by_family[family]
        for field in RUNTIME_PROFILE_FIELDS:
            if field in {"device", "hardware_class"}:
                matches = signed[field] == artifact[field]
            else:
                matches = math.isclose(
                    float(signed[field]),
                    float(artifact[field]),
                    abs_tol=1e-9,
                )
            if not matches:
                raise ModelPromotionError(
                    f"Runtime profile for {family} does not match the signed comparison receipt."
                )


def _verify_artifact_snapshots(
    artifact_paths: Mapping[str, str | Path],
    *,
    result_artifacts: object,
    expected_filenames: object,
) -> dict[str, bytes]:
    if set(artifact_paths) != set(REQUIRED_ARTIFACT_ROLES):
        raise ModelPromotionError(
            "Artifact paths must contain exactly metrics, calibration, "
            "error_categories, and runtime."
        )
    receipt_records = _mapping(result_artifacts, "result artifacts")
    expected = _validate_expected_artifacts(
        _mapping(expected_filenames, "expected artifact filenames")
    )
    snapshots: dict[str, bytes] = {}
    for role in REQUIRED_ARTIFACT_ROLES:
        path = Path(artifact_paths[role])
        record = _mapping(receipt_records[role], f"{role} artifact")
        filename = _basename(record["file"], f"{role} file")
        if filename != expected[role] or path.name != filename:
            raise ModelPromotionError(f"{role} artifact filename was substituted.")
        content = _read_stable_bytes(path, f"{role} artifact")
        if hashlib.sha256(content).hexdigest() != _sha256(
            record["sha256"], f"{role} artifact sha256"
        ):
            raise ModelPromotionError(f"{role} artifact checksum mismatch.")
        try:
            artifact_text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ModelPromotionError(f"{role} artifact is not UTF-8 text.") from exc
        _reject_private_paths(artifact_text)
        snapshots[role] = content
    return snapshots


def _parse_csv(content: bytes, label: str) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ModelPromotionError(
            f"{label.capitalize()} artifact is not UTF-8."
        ) from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ModelPromotionError(f"{label.capitalize()} artifact is empty.") from exc
    if (
        not header
        or any(not value.strip() for value in header)
        or len(header) != len(set(header))
    ):
        raise ModelPromotionError(
            f"{label.capitalize()} CSV header is invalid or duplicated."
        )
    rows: list[dict[str, str]] = []
    for line_number, values in enumerate(reader, start=2):
        if len(values) != len(header):
            raise ModelPromotionError(
                f"{label.capitalize()} CSV row {line_number} has the wrong column count."
            )
        if not any(value.strip() for value in values):
            raise ModelPromotionError(f"{label.capitalize()} CSV contains a blank row.")
        rows.append(dict(zip(header, values, strict=True)))
    if not rows:
        raise ModelPromotionError(f"{label.capitalize()} artifact has no data rows.")
    return rows


def _validate_metrics(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    _require_exact_columns(rows, METRIC_COLUMNS, "metrics")
    if len(rows) != len(REQUIRED_MODEL_FAMILIES):
        raise ModelPromotionError(
            "Metrics must contain exactly one row per model family."
        )
    normalized: list[dict[str, object]] = []
    for row in rows:
        family = _safe_id(row["model_family"], "metrics model_family")
        if row["evaluation_split"] != "untouched_final_spatial_holdout":
            raise ModelPromotionError(
                "Metrics do not use the untouched final spatial holdout."
            )
        if not _csv_false(row["can_feed_decision_layer"]):
            raise ModelPromotionError("Metrics must remain decision-layer ineligible.")
        sample_count = _positive_int(
            row["sample_count"], f"metrics {family} sample_count"
        )
        holdout_group_count = _positive_int(
            row["holdout_group_count"],
            f"metrics {family} holdout_group_count",
        )
        decision_threshold = _bounded_float(
            row["decision_threshold"], f"metrics {family} decision_threshold"
        )
        cell_area_m2 = _positive_float(
            row["cell_area_m2"], f"metrics {family} cell_area_m2"
        )
        counts = {
            field: _nonnegative_int(row[field], f"metrics {family} {field}")
            for field in (
                "true_positive",
                "false_positive",
                "false_negative",
                "true_negative",
            )
        }
        if sum(counts.values()) != sample_count:
            raise ModelPromotionError(
                f"Metrics confusion counts for {family} do not match sample_count."
            )
        tp = counts["true_positive"]
        fp = counts["false_positive"]
        fn = counts["false_negative"]
        predicted_area_m2 = float((tp + fp) * cell_area_m2)
        reference_area_m2 = float((tp + fn) * cell_area_m2)
        area_error_m2 = predicted_area_m2 - reference_area_m2
        area_error_ratio = _finite_ratio(area_error_m2, reference_area_m2)
        expected = {
            "iou": _finite_ratio(tp, tp + fp + fn),
            "f1_dice": _finite_ratio(2 * tp, (2 * tp) + fp + fn),
            "precision": _finite_ratio(tp, tp + fp),
            "recall": _finite_ratio(tp, tp + fn),
            "predicted_area_m2": predicted_area_m2,
            "reference_area_m2": reference_area_m2,
            "area_error_m2": area_error_m2,
            "absolute_area_error_m2": abs(area_error_m2),
            "area_error_ratio": area_error_ratio,
            "absolute_area_error_ratio": abs(area_error_ratio),
        }
        values: dict[str, object] = {
            "model_family": family,
            "holdout_group_count": holdout_group_count,
            "sample_count": sample_count,
            "decision_threshold": decision_threshold,
            "cell_area_m2": cell_area_m2,
            **counts,
        }
        for key in (
            "iou",
            "f1_dice",
            "precision",
            "recall",
            "brier_score",
            "expected_calibration_error",
        ):
            values[key] = _bounded_float(row[key], f"metrics {family} {key}")
        for key in (
            "predicted_area_m2",
            "reference_area_m2",
            "absolute_area_error_m2",
            "absolute_area_error_ratio",
        ):
            values[key] = _nonnegative_float(row[key], f"metrics {family} {key}")
        values["area_error_m2"] = _float(
            row["area_error_m2"], f"metrics {family} area_error_m2"
        )
        values["area_error_ratio"] = _float(
            row["area_error_ratio"], f"metrics {family} area_error_ratio"
        )
        for key, expected_value in expected.items():
            if not math.isclose(
                float(values[key]),
                expected_value,
                rel_tol=1e-12,
                abs_tol=1e-6,
            ):
                raise ModelPromotionError(
                    f"Metrics {key} for {family} does not reproduce confusion counts."
                )
        normalized.append(values)
    families = [str(row["model_family"]) for row in normalized]
    if set(families) != set(REQUIRED_MODEL_FAMILIES) or len(set(families)) != len(
        families
    ):
        raise ModelPromotionError(
            "Metrics model families are incomplete or duplicated."
        )
    first = normalized[0]
    for row in normalized[1:]:
        if (
            row["sample_count"] != first["sample_count"]
            or row["holdout_group_count"] != first["holdout_group_count"]
            or not math.isclose(
                float(row["cell_area_m2"]),
                float(first["cell_area_m2"]),
                rel_tol=1e-12,
                abs_tol=1e-9,
            )
        ):
            raise ModelPromotionError(
                "All model metrics must use the same final-holdout sample count, "
                "group count, and cell area."
            )
    return normalized


def _validate_calibration(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    _require_columns(rows, CALIBRATION_COLUMNS, "calibration")
    normalized: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    for row in rows:
        family = _safe_id(row["model_family"], "calibration model_family")
        bin_index = _nonnegative_int(row["bin_index"], "calibration bin_index")
        identity = (family, bin_index)
        if identity in seen:
            raise ModelPromotionError("Calibration bins are duplicated.")
        seen.add(identity)
        lower = _bounded_float(row["bin_lower"], "calibration bin_lower")
        upper = _bounded_float(row["bin_upper"], "calibration bin_upper")
        if upper <= lower:
            raise ModelPromotionError("Calibration bin bounds are invalid.")
        sample_count = _nonnegative_int(row["sample_count"], "calibration sample_count")
        mean_probability = _bounded_float(
            row["mean_probability"], "calibration mean_probability"
        )
        observed_rate = _bounded_float(
            row["observed_flood_rate"], "calibration observed_flood_rate"
        )
        absolute_gap = _bounded_float(row["absolute_gap"], "calibration absolute_gap")
        if not math.isclose(
            absolute_gap,
            abs(mean_probability - observed_rate),
            abs_tol=1e-6,
        ):
            raise ModelPromotionError(
                "Calibration absolute_gap does not reproduce probability and observed rate."
            )
        if sample_count and not (
            lower <= mean_probability <= upper
            if upper == 1.0
            else lower <= mean_probability < upper
        ):
            raise ModelPromotionError(
                "Calibration mean probability falls outside its declared bin."
            )
        normalized.append(
            {
                "model_family": family,
                "bin_index": bin_index,
                "bin_lower": lower,
                "bin_upper": upper,
                "sample_count": sample_count,
                "sample_fraction": _bounded_float(
                    row["sample_fraction"], "calibration sample_fraction"
                ),
                "mean_probability": mean_probability,
                "observed_flood_rate": observed_rate,
                "absolute_gap": absolute_gap,
            }
        )
    common_grid: tuple[tuple[int, float, float], ...] | None = None
    for family in REQUIRED_MODEL_FAMILIES:
        family_rows = sorted(
            (row for row in normalized if row["model_family"] == family),
            key=lambda row: int(row["bin_index"]),
        )
        if len(family_rows) < 2 or [row["bin_index"] for row in family_rows] != list(
            range(len(family_rows))
        ):
            raise ModelPromotionError(f"Calibration bins for {family} are incomplete.")
        if family_rows[0]["bin_lower"] != 0.0 or family_rows[-1]["bin_upper"] != 1.0:
            raise ModelPromotionError(
                f"Calibration bins for {family} do not cover [0,1]."
            )
        for previous, current in zip(family_rows, family_rows[1:]):
            if not math.isclose(
                float(previous["bin_upper"]),
                float(current["bin_lower"]),
                abs_tol=1e-12,
            ):
                raise ModelPromotionError(
                    f"Calibration bins for {family} are not contiguous."
                )
        total_count = sum(int(row["sample_count"]) for row in family_rows)
        if total_count <= 0:
            raise ModelPromotionError(
                f"Calibration rows for {family} contain no samples."
            )
        tolerance = max(1e-5, len(family_rows) * 5e-7)
        if not math.isclose(
            sum(float(row["sample_fraction"]) for row in family_rows),
            1.0,
            abs_tol=tolerance,
        ):
            raise ModelPromotionError(
                f"Calibration sample fractions for {family} do not sum to one."
            )
        for row in family_rows:
            expected_fraction = int(row["sample_count"]) / total_count
            if not math.isclose(
                float(row["sample_fraction"]),
                expected_fraction,
                abs_tol=1e-6,
            ):
                raise ModelPromotionError(
                    f"Calibration sample fraction for {family} does not reproduce counts."
                )
        family_grid = tuple(
            (
                int(row["bin_index"]),
                float(row["bin_lower"]),
                float(row["bin_upper"]),
            )
            for row in family_rows
        )
        if common_grid is None:
            common_grid = family_grid
        elif len(family_grid) != len(common_grid) or any(
            current[0] != expected[0]
            or not math.isclose(current[1], expected[1], abs_tol=1e-12)
            or not math.isclose(current[2], expected[2], abs_tol=1e-12)
            for current, expected in zip(family_grid, common_grid, strict=True)
        ):
            raise ModelPromotionError(
                "All model calibration artifacts must use the same bin grid."
            )
    return normalized


def _verify_calibration_consistency(
    *,
    metrics: Sequence[Mapping[str, object]],
    calibration: Sequence[Mapping[str, object]],
) -> None:
    for metric in metrics:
        family = str(metric["model_family"])
        rows = [row for row in calibration if row["model_family"] == family]
        if sum(int(row["sample_count"]) for row in rows) != int(metric["sample_count"]):
            raise ModelPromotionError(
                f"Calibration sample count for {family} does not match final holdout metrics."
            )
        calculated = sum(
            float(row["sample_fraction"]) * float(row["absolute_gap"]) for row in rows
        )
        if not math.isclose(
            calculated,
            float(metric["expected_calibration_error"]),
            abs_tol=max(1e-5, len(rows) * 1e-6),
        ):
            raise ModelPromotionError(
                f"Calibration artifact does not reproduce {family} ECE."
            )


def _validate_error_categories(
    rows: list[dict[str, str]], *, required_categories: object
) -> list[dict[str, object]]:
    _require_columns(rows, ERROR_COLUMNS, "error categories")
    categories = _validate_required_categories(
        _sequence(required_categories, "required_error_categories")
    )
    required_set = {"all", *categories}
    normalized: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    by_family: dict[str, set[str]] = {
        family: set() for family in REQUIRED_MODEL_FAMILIES
    }
    for row in rows:
        family = _safe_id(row["model_family"], "error model_family")
        category = str(row["category"])
        if family not in by_family or category not in required_set:
            raise ModelPromotionError(
                "Error-category artifact contains an unknown model or category."
            )
        identity = (family, category)
        if identity in seen:
            raise ModelPromotionError("Error-category rows are duplicated.")
        seen.add(identity)
        by_family[family].add(category)
        coverage = str(row["coverage_status"])
        if coverage not in {"measured", "not_measured_insufficient_coverage"}:
            raise ModelPromotionError("Error-category coverage status is invalid.")
        cell_count = _nonnegative_int(row["cell_count"], "error cell_count")
        positive = _nonnegative_int(
            row["reference_positive_count"], "reference_positive_count"
        )
        negative = _nonnegative_int(
            row["reference_negative_count"], "reference_negative_count"
        )
        false_positive = _nonnegative_int(
            row["false_positive_count"], "false_positive_count"
        )
        false_negative = _nonnegative_int(
            row["false_negative_count"], "false_negative_count"
        )
        if (
            positive + negative != cell_count
            or false_positive > negative
            or false_negative > positive
            or (coverage == "measured") is not (cell_count > 0)
        ):
            raise ModelPromotionError(
                "Error-category coverage and confusion counts are inconsistent."
            )
        true_positive = positive - false_negative
        predicted_positive = true_positive + false_positive
        expected_rates = {
            "false_positive_rate": (false_positive / negative if negative else None),
            "false_negative_rate": (false_negative / positive if positive else None),
            "precision": (
                true_positive / predicted_positive if predicted_positive else None
            ),
            "recall": true_positive / positive if positive else None,
        }
        rates: dict[str, float | None] = {}
        for field, expected in expected_rates.items():
            raw = str(row[field]).strip()
            if expected is None:
                if raw:
                    raise ModelPromotionError(
                        f"Error-category {field} must be blank when undefined."
                    )
                rates[field] = None
            else:
                value = _bounded_float(raw, f"error category {field}")
                if not math.isclose(value, expected, abs_tol=1e-6):
                    raise ModelPromotionError(
                        f"Error-category {field} does not reproduce counts."
                    )
                rates[field] = value
        normalized.append(
            {
                "model_family": family,
                "category": category,
                "coverage_status": coverage,
                "cell_count": cell_count,
                "reference_positive_count": positive,
                "reference_negative_count": negative,
                "false_positive_count": false_positive,
                "false_negative_count": false_negative,
                **rates,
            }
        )
    for family, present in by_family.items():
        if present != required_set:
            raise ModelPromotionError(
                f"Required error categories for {family} are incomplete or substituted."
            )
    return normalized


def _error_coverage_failures(
    family: str,
    rows: Sequence[Mapping[str, object]],
    *,
    minimum_cell_count: int,
) -> list[str]:
    failures: list[str] = []
    for row in rows:
        if row["model_family"] != family or row["category"] == "all":
            continue
        if (
            row["coverage_status"] != "measured"
            or int(row["cell_count"]) < minimum_cell_count
        ):
            failures.append(
                f"error_category={row['category']} has insufficient coverage "
                f"({row['cell_count']}<{minimum_cell_count})"
            )
    return failures


def _verify_error_category_consistency(
    *,
    metrics: Sequence[Mapping[str, object]],
    errors: Sequence[Mapping[str, object]],
) -> None:
    metric_by_family = {str(row["model_family"]): row for row in metrics}
    error_by_identity = {
        (str(row["model_family"]), str(row["category"])): row for row in errors
    }
    reference_by_category: dict[str, tuple[object, ...]] = {}
    for family in REQUIRED_MODEL_FAMILIES:
        metric = metric_by_family[family]
        overall = error_by_identity[(family, "all")]
        all_counts = (
            int(overall["cell_count"]),
            int(overall["reference_positive_count"]),
            int(overall["reference_negative_count"]),
        )
        if all_counts[0] != int(metric["sample_count"]):
            raise ModelPromotionError(
                f"Overall error row for {family} does not match metric sample_count."
            )
        derived_confusion = {
            "true_positive": all_counts[1] - int(overall["false_negative_count"]),
            "false_positive": int(overall["false_positive_count"]),
            "false_negative": int(overall["false_negative_count"]),
            "true_negative": all_counts[2] - int(overall["false_positive_count"]),
        }
        if any(int(metric[key]) != value for key, value in derived_confusion.items()):
            raise ModelPromotionError(
                f"Overall error row for {family} does not reproduce metrics confusion counts."
            )
        for category in ("all", *REQUIRED_ERROR_CATEGORIES):
            row = error_by_identity[(family, category)]
            reference = (
                row["coverage_status"],
                int(row["cell_count"]),
                int(row["reference_positive_count"]),
                int(row["reference_negative_count"]),
            )
            prior = reference_by_category.setdefault(category, reference)
            if reference != prior:
                raise ModelPromotionError(
                    f"Reference coverage for error category {category} differs across models."
                )
            if category != "all" and (
                int(row["cell_count"]) > all_counts[0]
                or int(row["reference_positive_count"]) > all_counts[1]
                or int(row["reference_negative_count"]) > all_counts[2]
            ):
                raise ModelPromotionError(
                    f"Error category {category} exceeds overall holdout coverage."
                )


def _validate_runtime_profile_mapping(
    value: Mapping[str, object], *, label: str
) -> dict[str, object]:
    _exact_keys(value, set(RUNTIME_PROFILE_FIELDS), label)
    profile: dict[str, object] = {
        "training_seconds": _nonnegative_float(
            value["training_seconds"], f"{label} training_seconds"
        ),
        "calibration_seconds": _nonnegative_float(
            value["calibration_seconds"], f"{label} calibration_seconds"
        ),
        "inference_seconds": _positive_float(
            value["inference_seconds"], f"{label} inference_seconds"
        ),
        "total_seconds": _positive_float(
            value["total_seconds"], f"{label} total_seconds"
        ),
        "peak_memory_mb": _positive_float(
            value["peak_memory_mb"], f"{label} peak_memory_mb"
        ),
        "device": _safe_text(value["device"], f"{label} device"),
        "hardware_class": _safe_text(
            value["hardware_class"], f"{label} hardware_class"
        ),
    }
    measured = sum(
        float(profile[field])
        for field in (
            "training_seconds",
            "calibration_seconds",
            "inference_seconds",
        )
    )
    if float(profile["total_seconds"]) + 1e-9 < measured:
        raise ModelPromotionError(
            f"{label.capitalize()} total_seconds is shorter than measured phases."
        )
    return profile


def _validate_runtime(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    _require_columns(rows, RUNTIME_COLUMNS, "runtime")
    if len(rows) != len(REQUIRED_MODEL_FAMILIES):
        raise ModelPromotionError(
            "Runtime artifact must contain exactly one row per model."
        )
    normalized: list[dict[str, object]] = []
    for row in rows:
        family = _safe_id(row["model_family"], "runtime model_family")
        model_id = _safe_id(row["model_id"], "runtime model_id")
        profile = _validate_runtime_profile_mapping(
            {field: row[field] for field in RUNTIME_PROFILE_FIELDS},
            label=f"runtime profile for {family}",
        )
        normalized.append(
            {
                "model_family": family,
                "model_id": model_id,
                **profile,
            }
        )
    families = [str(row["model_family"]) for row in normalized]
    if set(families) != set(REQUIRED_MODEL_FAMILIES) or len(set(families)) != len(
        families
    ):
        raise ModelPromotionError(
            "Runtime model families are incomplete or duplicated."
        )
    return normalized


def _threshold_failures(
    metrics: Mapping[str, object], thresholds: Mapping[str, object]
) -> list[str]:
    checks = (
        ("iou", "minimum_iou", ">="),
        ("f1_dice", "minimum_f1_dice", ">="),
        ("precision", "minimum_precision", ">="),
        ("recall", "minimum_recall", ">="),
        ("absolute_area_error_ratio", "maximum_absolute_area_error_ratio", "<="),
        ("brier_score", "maximum_brier_score", "<="),
        ("expected_calibration_error", "maximum_expected_calibration_error", "<="),
    )
    failures: list[str] = []
    for metric_name, threshold_name, operator in checks:
        value = float(metrics[metric_name])
        limit = float(thresholds[threshold_name])
        failed = value < limit if operator == ">=" else value > limit
        if failed:
            failures.append(f"{metric_name}={value:.6f} fails {operator}{limit:.6f}")
    return failures


def _tie_break_key(
    candidate: Mapping[str, object], order: object
) -> tuple[object, ...]:
    metrics = _mapping(candidate["metrics"], "candidate metrics")
    runtime = _mapping(candidate["runtime_profile"], "candidate runtime")
    values: dict[str, object] = {
        "iou_desc": -float(metrics["iou"]),
        "f1_dice_desc": -float(metrics["f1_dice"]),
        "precision_desc": -float(metrics["precision"]),
        "recall_desc": -float(metrics["recall"]),
        "absolute_area_error_ratio_asc": float(metrics["absolute_area_error_ratio"]),
        "brier_score_asc": float(metrics["brier_score"]),
        "expected_calibration_error_asc": float(metrics["expected_calibration_error"]),
        "total_seconds_asc": float(runtime["total_seconds"]),
        "model_id_ascending": str(candidate["model_id"]),
    }
    return tuple(values[str(item)] for item in _sequence(order, "tie_break_order"))


def _validate_recommendation(payload: Mapping[str, object]) -> None:
    required = {
        "artifact_schema",
        "recommendation_id",
        "experiment_id",
        "study_area",
        "generated_at_utc",
        "policy_id",
        "lineage",
        "recommendation_status",
        "selected_candidate",
        "evaluated_models",
        "tie_break_order",
        "selection_scope",
        "operational_status",
        "official_warning",
        "can_feed_decision_layer",
        "requires_separate_decision_layer_acceptance",
        "signing_role",
        "assumptions",
        "signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "signature",
    }
    _exact_keys(payload, required, "model promotion recommendation")
    if payload["artifact_schema"] != RECOMMENDATION_SCHEMA:
        raise ModelPromotionError(
            "Model promotion recommendation schema is unsupported."
        )
    status_value = payload["recommendation_status"]
    if status_value not in {"candidate_selected", "no_candidate_qualified"}:
        raise ModelPromotionError("Model promotion recommendation status is invalid.")
    selected = payload["selected_candidate"]
    if (status_value == "candidate_selected") != isinstance(selected, Mapping):
        raise ModelPromotionError(
            "Selected candidate does not match recommendation status."
        )
    if (
        payload["selection_scope"] != "report_only_recommendation"
        or payload["operational_status"] != "non_operational"
        or payload["official_warning"] is not False
        or payload["can_feed_decision_layer"] is not False
        or payload["requires_separate_decision_layer_acceptance"] is not True
        or payload["signing_role"] != "model_promotion_recommendation_authority"
    ):
        raise ModelPromotionError("Recommendation contains unsafe authority fields.")
    _safe_id(payload["recommendation_id"], "recommendation_id")
    _safe_id(payload["experiment_id"], "experiment_id")
    _safe_text(payload["study_area"], "study_area")
    _safe_id(payload["policy_id"], "policy_id")
    _timestamp(payload["generated_at_utc"], "generated_at_utc")
    tie_break = _validate_tie_break_order(
        _sequence(payload["tie_break_order"], "tie_break_order")
    )
    lineage = _mapping(payload["lineage"], "recommendation lineage")
    _exact_keys(
        lineage,
        {
            "policy_manifest_sha256",
            "policy_file_sha256",
            "policy_signing_key_id",
            "comparison_manifest_sha256",
            "comparison_file_sha256",
            "comparison_signing_key_id",
            "artifacts",
        },
        "recommendation lineage",
    )
    for field in (
        "policy_manifest_sha256",
        "policy_file_sha256",
        "comparison_manifest_sha256",
        "comparison_file_sha256",
    ):
        _sha256(lineage[field], field)
    policy_key_id = _safe_id(lineage["policy_signing_key_id"], "policy_signing_key_id")
    result_key_id = _safe_id(
        lineage["comparison_signing_key_id"], "comparison_signing_key_id"
    )
    recommendation_key_id = _safe_id(
        payload["signing_key_id"], "recommendation signing_key_id"
    )
    if len({policy_key_id, result_key_id, recommendation_key_id}) != 3:
        raise ModelPromotionError(
            "Promotion authority signing identities must be distinct."
        )
    artifacts = _mapping(lineage["artifacts"], "recommendation artifacts")
    _exact_keys(artifacts, set(REQUIRED_ARTIFACT_ROLES), "recommendation artifacts")
    for role, raw in artifacts.items():
        record = _mapping(raw, f"{role} recommendation artifact")
        _exact_keys(record, {"file", "sha256"}, f"{role} recommendation artifact")
        _basename(record["file"], f"{role} artifact file")
        _sha256(record["sha256"], f"{role} artifact sha256")
    evaluated = _validate_recommendation_models(payload["evaluated_models"])
    qualified = [row for row in evaluated if row["qualified"] is True]
    if status_value == "no_candidate_qualified":
        if selected is not None or qualified:
            raise ModelPromotionError(
                "No-candidate status contradicts evaluated model qualifications."
            )
    else:
        selected_mapping = _mapping(selected, "selected candidate")
        _exact_keys(
            selected_mapping,
            {"model_id", "model_family", "metrics", "runtime_profile"},
            "selected candidate",
        )
        ranked = sorted(
            qualified,
            key=lambda row: _tie_break_key(row, tie_break),
        )
        if not ranked:
            raise ModelPromotionError(
                "Candidate-selected status has no qualified evaluated model."
            )
        expected_selected = {
            "model_id": ranked[0]["model_id"],
            "model_family": ranked[0]["model_family"],
            "metrics": ranked[0]["metrics"],
            "runtime_profile": ranked[0]["runtime_profile"],
        }
        if dict(selected_mapping) != expected_selected:
            raise ModelPromotionError(
                "Selected candidate does not reproduce the signed ranking."
            )
    assumptions = _sequence(payload["assumptions"], "recommendation assumptions")
    if not assumptions or any(
        not isinstance(value, str) or not value.strip() for value in assumptions
    ):
        raise ModelPromotionError("Recommendation assumptions are invalid.")
    _reject_private_paths(payload)


def _validate_recommendation_models(value: object) -> list[dict[str, object]]:
    rows = _sequence(value, "evaluated_models")
    if len(rows) != len(REQUIRED_MODEL_FAMILIES):
        raise ModelPromotionError(
            "Recommendation must contain exactly three evaluated models."
        )
    normalized: list[dict[str, object]] = []
    for raw in rows:
        row = _mapping(raw, "evaluated model")
        _exact_keys(
            row,
            {
                "model_id",
                "model_family",
                "metrics",
                "runtime_profile",
                "qualified",
                "rejection_reasons",
            },
            "evaluated model",
        )
        family = _safe_id(row["model_family"], "evaluated model_family")
        model_id = _safe_id(row["model_id"], "evaluated model_id")
        metrics = _mapping(row["metrics"], "evaluated metrics")
        metric_fields = {
            "iou",
            "f1_dice",
            "precision",
            "recall",
            "absolute_area_error_ratio",
            "brier_score",
            "expected_calibration_error",
        }
        _exact_keys(metrics, metric_fields, "evaluated metrics")
        normalized_metrics = {
            key: (
                _nonnegative_float(metrics[key], key)
                if key == "absolute_area_error_ratio"
                else _bounded_float(metrics[key], key)
            )
            for key in metric_fields
        }
        runtime = _mapping(row["runtime_profile"], "evaluated runtime")
        runtime_fields = {
            "training_seconds",
            "calibration_seconds",
            "inference_seconds",
            "total_seconds",
            "peak_memory_mb",
            "device",
            "hardware_class",
        }
        _exact_keys(runtime, runtime_fields, "evaluated runtime")
        normalized_runtime = {
            "training_seconds": _nonnegative_float(
                runtime["training_seconds"], "training_seconds"
            ),
            "calibration_seconds": _nonnegative_float(
                runtime["calibration_seconds"], "calibration_seconds"
            ),
            "inference_seconds": _positive_float(
                runtime["inference_seconds"], "inference_seconds"
            ),
            "total_seconds": _positive_float(runtime["total_seconds"], "total_seconds"),
            "peak_memory_mb": _positive_float(
                runtime["peak_memory_mb"], "peak_memory_mb"
            ),
            "device": str(runtime["device"]).strip(),
            "hardware_class": str(runtime["hardware_class"]).strip(),
        }
        if not normalized_runtime["device"] or not normalized_runtime["hardware_class"]:
            raise ModelPromotionError("Evaluated runtime identity is missing.")
        measured_seconds = sum(
            float(normalized_runtime[field])
            for field in (
                "training_seconds",
                "calibration_seconds",
                "inference_seconds",
            )
        )
        if float(normalized_runtime["total_seconds"]) + 1e-9 < measured_seconds:
            raise ModelPromotionError(
                "Evaluated runtime total_seconds is shorter than measured phases."
            )
        reasons = _sequence(row["rejection_reasons"], "rejection_reasons")
        if any(not isinstance(item, str) or not item.strip() for item in reasons):
            raise ModelPromotionError("Recommendation rejection reasons are invalid.")
        qualified = row["qualified"]
        if not isinstance(qualified, bool) or qualified is bool(reasons):
            raise ModelPromotionError(
                "Model qualification contradicts its rejection reasons."
            )
        normalized.append(
            {
                "model_id": model_id,
                "model_family": family,
                "metrics": normalized_metrics,
                "runtime_profile": normalized_runtime,
                "qualified": qualified,
                "rejection_reasons": list(reasons),
            }
        )
    families = [str(row["model_family"]) for row in normalized]
    identifiers = [str(row["model_id"]) for row in normalized]
    if (
        set(families) != set(REQUIRED_MODEL_FAMILIES)
        or len(set(families)) != len(families)
        or len(set(identifiers)) != len(identifiers)
    ):
        raise ModelPromotionError(
            "Recommendation model identities are incomplete or duplicated."
        )
    return normalized


def _validate_thresholds(thresholds: Mapping[str, object]) -> dict[str, float]:
    _exact_keys(thresholds, set(THRESHOLD_FIELDS), "promotion thresholds")
    normalized: dict[str, float] = {}
    for key in THRESHOLD_FIELDS:
        if key == "maximum_absolute_area_error_ratio":
            normalized[key] = _nonnegative_float(thresholds[key], key)
        else:
            normalized[key] = _bounded_float(thresholds[key], key)
    return normalized


def _validate_required_categories(categories: Sequence[object]) -> list[str]:
    normalized = [str(value) for value in categories]
    if normalized != list(REQUIRED_ERROR_CATEGORIES):
        raise ModelPromotionError(
            "Required error categories must explicitly contain the canonical ordered set."
        )
    return normalized


def _validate_tie_break_order(order: Sequence[object]) -> list[str]:
    normalized = [str(value) for value in order]
    if (
        not normalized
        or len(normalized) != len(set(normalized))
        or any(value not in ALLOWED_TIE_BREAKERS for value in normalized)
        or normalized[-1] != "model_id_ascending"
    ):
        raise ModelPromotionError(
            "Tie-break order must be unique, supported, and end with model_id_ascending."
        )
    return normalized


def _validate_expected_artifacts(value: Mapping[str, object]) -> dict[str, str]:
    _exact_keys(value, set(REQUIRED_ARTIFACT_ROLES), "expected artifacts")
    normalized = {
        role: _basename(value[role], f"expected {role} filename")
        for role in REQUIRED_ARTIFACT_ROLES
    }
    if len(set(normalized.values())) != len(normalized):
        raise ModelPromotionError("Expected artifact filenames must be unique.")
    return normalized


def _seal(
    payload: Mapping[str, object], *, signing_key_id: str, signing_key: bytes
) -> dict[str, object]:
    sealed = dict(payload)
    if {"manifest_sha256", "signature", "signing_key_id", "signature_algorithm"} & set(
        sealed
    ):
        raise ModelPromotionError("Payload already contains signing fields.")
    sealed["signing_key_id"] = _safe_id(signing_key_id, "signing_key_id")
    sealed["signature_algorithm"] = SIGNATURE_ALGORITHM
    sealed["manifest_sha256"] = _canonical_sha256(sealed)
    sealed["signature"] = hmac.new(
        _validated_signing_key(signing_key),
        _canonical_json_bytes(sealed),
        hashlib.sha256,
    ).hexdigest()
    return sealed


def _load_signed_json(
    path: Path, *, signing_keys: Mapping[str, bytes], label: str
) -> tuple[dict[str, object], str]:
    content = _read_stable_bytes(path, label)

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        payload: dict[str, object] = {}
        for key, value in pairs:
            if key in payload:
                raise ModelPromotionError(
                    f"{label.capitalize()} contains duplicate JSON key: {key}."
                )
            payload[key] = value
        return payload

    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=reject_duplicates
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelPromotionError(
            f"{label.capitalize()} is not valid UTF-8 JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise ModelPromotionError(f"{label.capitalize()} must be a JSON object.")
    _verify_seal(payload, signing_keys=signing_keys, label=label)
    _reject_private_paths(payload)
    return payload, hashlib.sha256(content).hexdigest()


def _verify_seal(
    payload: Mapping[str, object], *, signing_keys: Mapping[str, bytes], label: str
) -> None:
    if payload.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        raise ModelPromotionError(
            f"{label.capitalize()} signature algorithm is unsupported."
        )
    key_id = _safe_id(payload.get("signing_key_id"), f"{label} signing_key_id")
    if key_id not in signing_keys:
        raise ModelPromotionError(f"{label.capitalize()} signing key is not trusted.")
    manifest = _sha256(payload.get("manifest_sha256"), f"{label} manifest_sha256")
    signature = _sha256(payload.get("signature"), f"{label} signature")
    unhashed = {
        key: value
        for key, value in payload.items()
        if key not in {"manifest_sha256", "signature"}
    }
    if not hmac.compare_digest(manifest, _canonical_sha256(unhashed)):
        raise ModelPromotionError(f"{label.capitalize()} self-hash is invalid.")
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    expected = hmac.new(
        _validated_signing_key(signing_keys[key_id]),
        _canonical_json_bytes(unsigned),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ModelPromotionError(f"{label.capitalize()} HMAC signature is invalid.")


def _read_stable_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink():
        raise ModelPromotionError(f"{label.capitalize()} must not be a symbolic link.")
    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise ModelPromotionError(f"{label.capitalize()} is not a regular file.")
        with path.open("rb") as handle:
            opened = stat.S_ISREG(Path(path).stat().st_mode)
            content = handle.read()
            descriptor = handle.fileno()
            during = os.fstat(descriptor)
        after = path.stat()
    except OSError as exc:
        raise ModelPromotionError(f"Could not read {label} as a stable file.") from exc
    if (
        not opened
        or before.st_dev != during.st_dev
        or before.st_ino != during.st_ino
        or before.st_size != during.st_size
        or before.st_mtime_ns != during.st_mtime_ns
        or before.st_ctime_ns != during.st_ctime_ns
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
    ):
        raise ModelPromotionError(f"{label.capitalize()} changed while being verified.")
    return content


def _write_json_exclusive(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise ModelPromotionError(
            f"Output already exists and is immutable: {path.name}"
        ) from exc


def _reject_existing_output(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ModelPromotionError(
            f"Output already exists and is immutable: {path.name}"
        )


def _reject_private_paths(value: object) -> None:
    if isinstance(value, str) and PRIVATE_PATH_RE.search(value):
        raise ModelPromotionError("Evidence contains a private absolute path.")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_private_paths(key)
            _reject_private_paths(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_private_paths(item)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelPromotionError(f"{label.capitalize()} must be an object.")
    return value


def _sequence(value: object, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ModelPromotionError(f"{label.capitalize()} must be an array.")
    return value


def _exact_keys(value: Mapping[str, object], keys: set[str], label: str) -> None:
    if set(value) != keys:
        missing = sorted(keys - set(value))
        extra = sorted(set(value) - keys)
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("extra=" + ",".join(extra))
        raise ModelPromotionError(
            f"{label.capitalize()} fields are invalid ({'; '.join(detail)})."
        )


def _require_columns(
    rows: Sequence[Mapping[str, str]], columns: set[str], label: str
) -> None:
    missing = sorted(columns - set(rows[0]))
    if missing:
        raise ModelPromotionError(
            f"{label.capitalize()} artifact is missing columns: {', '.join(missing)}"
        )


def _require_exact_columns(
    rows: Sequence[Mapping[str, str]], columns: set[str], label: str
) -> None:
    actual = set(rows[0])
    missing = sorted(columns - actual)
    extra = sorted(actual - columns)
    if missing or extra:
        detail = []
        if missing:
            detail.append("missing columns: " + ", ".join(missing))
        if extra:
            detail.append("unexpected columns: " + ", ".join(extra))
        raise ModelPromotionError(
            f"{label.capitalize()} artifact schema is invalid ({'; '.join(detail)})."
        )


def _safe_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value):
        raise ModelPromotionError(f"{label.capitalize()} is invalid.")
    return value


def _safe_text(value: object, label: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ModelPromotionError(f"{label.capitalize()} must be non-blank text.")
    if len(value) > 255 or any(ord(character) < 32 for character in value):
        raise ModelPromotionError(f"{label.capitalize()} contains unsafe characters.")
    _reject_private_paths(value)
    return value


def _basename(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ModelPromotionError(f"{label.capitalize()} must be a plain filename.")
    parsed = PurePosixPath(value)
    if parsed.name != value or value in {".", ".."}:
        raise ModelPromotionError(f"{label.capitalize()} must be a plain filename.")
    _reject_private_paths(value)
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ModelPromotionError(
            f"{label.capitalize()} must be a lowercase SHA-256 digest."
        )
    return value


def _float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ModelPromotionError(f"{label.capitalize()} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ModelPromotionError(
            f"{label.capitalize()} must be a finite number."
        ) from exc
    if not math.isfinite(number):
        raise ModelPromotionError(f"{label.capitalize()} must be a finite number.")
    return number


def _bounded_float(value: object, label: str) -> float:
    number = _float(value, label)
    if not 0.0 <= number <= 1.0:
        raise ModelPromotionError(f"{label.capitalize()} must be in [0,1].")
    return number


def _nonnegative_float(value: object, label: str) -> float:
    number = _float(value, label)
    if number < 0.0:
        raise ModelPromotionError(f"{label.capitalize()} must be non-negative.")
    return number


def _positive_float(value: object, label: str) -> float:
    number = _float(value, label)
    if number <= 0.0:
        raise ModelPromotionError(f"{label.capitalize()} must be positive.")
    return number


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ModelPromotionError(
            f"{label.capitalize()} must be a non-negative integer."
        )
    try:
        number = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ModelPromotionError(
            f"{label.capitalize()} must be a non-negative integer."
        ) from exc
    if str(number) != str(value).strip() or number < 0:
        raise ModelPromotionError(
            f"{label.capitalize()} must be a non-negative integer."
        )
    return number


def _positive_int(value: object, label: str) -> int:
    number = _nonnegative_int(value, label)
    if number <= 0:
        raise ModelPromotionError(f"{label} must be positive.")
    return number


def _csv_false(value: object) -> bool:
    return str(value).strip().lower() in {"false", "0"}


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ModelPromotionError(
            f"{label.capitalize()} must be an explicit UTC timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ModelPromotionError(f"{label.capitalize()} is invalid.") from exc
    return _require_utc(parsed, label)


def _require_utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ModelPromotionError(f"{label.capitalize()} must be timezone-aware UTC.")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ModelPromotionError(f"{label.capitalize()} must use UTC.")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    """Return the internally trusted signing clock without losing ordering precision."""

    return datetime.now(UTC)


def _finite_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0 if numerator == 0 else 1.0
    return float(numerator) / float(denominator)


def _validated_signing_key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ModelPromotionError(
            "Signing keys must be external byte strings of at least 32 bytes."
        )
    return value


def _require_distinct_credentials(
    credentials_by_id: Mapping[str, bytes | None], *, label: str
) -> None:
    seen: list[bytes] = []
    for key_id, raw in credentials_by_id.items():
        _safe_id(key_id, f"{label} signing_key_id")
        if raw is None:
            raise ModelPromotionError(f"{label} signing key {key_id!r} is not trusted.")
        credential = _validated_signing_key(raw)
        if any(hmac.compare_digest(credential, prior) for prior in seen):
            raise ModelPromotionError(
                f"{label} must use distinct credentials for every authority role."
            )
        seen.append(credential)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
