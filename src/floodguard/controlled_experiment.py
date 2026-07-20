"""Fail-closed authority and evaluation for the three-model flood experiment.

This module never downloads imagery, trains GeoAI, or imports the isolated
GeoAI runtime.  It verifies immutable evidence produced by the existing SAR,
weak-label, and ``services/geoai-runner`` lanes, then evaluates all three on
the same untouched spatial holdout.  Missing or substituted evidence blocks
execution rather than degrading to a weak-label or random-pixel experiment.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import base64
import hashlib
import hmac
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Any

import pandas as pd

from floodguard.label_factory.calibration import load_reviewer_calibration_receipt
from floodguard.label_factory.calibration_release import (
    CALIBRATION_QUERIES_NAME,
    FRESH_RETEST_QUERIES_NAME,
    CalibrationReleaseError,
    validate_calibration_release_package,
)


ACQUISITION_SCHEMA = "floodguard.controlled_experiment_acquisition.v1"
ACQUISITION_AUTHORITY_SCHEMA = "floodguard.acquisition_authority_receipt.v2"
EXTERNAL_AUTHORITY_DECISION_SCHEMA = "floodguard.external_authority_decision.v1"
HOLDOUT_SCHEMA = "floodguard.spatial_holdout.v6"
GRID_CONTRACT_SCHEMA = "floodguard.equal_area_grid.v1"
REFERENCE_CELL_RECEIPT_SCHEMA = "floodguard.controlled_reference_cells_receipt.v2"
REVIEWER_QUALIFICATION_SCHEMA = (
    "floodguard.controlled_reviewer_qualification_receipt.v3"
)
THRESHOLD_SELECTION_SCHEMA = "floodguard.controlled_threshold_selection_receipt.v1"
EXECUTION_AUTHORIZATION_SCHEMA = (
    "floodguard.controlled_experiment_execution_authorization.v1"
)
MODEL_RUN_SCHEMA = "floodguard.controlled_model_run_receipt.v3"
GATE_RECEIPT_SCHEMA = "floodguard.controlled_experiment_gate_receipt.v4"
RESULT_RECEIPT_SCHEMA = "floodguard.controlled_experiment_result.v4"
SIGNATURE_ALGORITHM = "HMAC-SHA256"
ZERO_DIVISION_CONVENTION = (
    "finite: 0/0=0.0; nonzero/0=1.0; otherwise numerator/denominator"
)

REQUIRED_INPUT_ROLES = ("pre_event_sar", "post_event_sar", "reference_mask")
REQUIRED_MODEL_FAMILIES = (
    "deterministic_sar_baseline",
    "weak_label_logistic",
    "geoai_candidate",
)
ERROR_STRATA = (
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
RUNTIME_PROFILE_FIELDS = (
    "training_seconds",
    "calibration_seconds",
    "inference_seconds",
    "total_seconds",
    "peak_memory_mb",
    "device",
    "hardware_class",
)
SIGNING_ROLES = {
    "acquisition": "internal_acquisition_receipt_integrity",
    "reviewer": "reviewer_calibration_authority",
    "adjudicator": "reference_adjudication_authority",
    "holdout": "spatial_partition_custodian",
    "reference": "reference_derivation_authority",
    "execution": "experiment_execution_authority",
    "model": "model_lane_executor",
    "result": "comparison_result_authority",
}

EXTERNAL_PERMISSION_FIELDS = (
    "local_analysis",
    "model_input_or_feature_use",
    "ml_label_use",
    "validation_metrics",
    "derived_reporting",
    "screenshots_and_demo_display",
    "source_redistribution",
    "derived_geometry_redistribution",
    "reference_only_storage_if_not_redistributable",
)
EXTERNAL_SIGNER_ATTESTATIONS = (
    "authorized_to_make_the_recorded_decisions",
    "all_permissions_are_product_specific",
    "unanswered_or_ambiguous_fields_remain_denied",
    "scientific_qualification_is_separate_from_licensing",
    "no_official_warning_or_operational_endorsement_is_granted",
)
MODEL_CONTRACT_SCHEMAS = {
    "deterministic_sar_baseline": "floodguard.deterministic_sar_baseline_run.v1",
    "weak_label_logistic": "floodguard.weak_label_logistic_run.v1",
    "geoai_candidate": "floodguard.geoai_candidate_run.v1",
}

ACQUISITION_COLUMNS = (
    "schema_version",
    "experiment_id",
    "study_area",
    "role",
    "source_name",
    "source_url",
    "product_id",
    "acquisition_start_utc",
    "acquisition_end_utc",
    "local_path_hint",
    "sha256",
    "sha256_status",
    "license_status",
    "local_analysis_allowed",
    "derived_metrics_allowed",
    "ml_label_use_allowed",
    "redistribution_status",
    "reference_mask_status",
    "temporal_alignment_status",
    "processing_allowed",
    "source_timestamp",
    "assumptions",
)

MODEL_EVIDENCE_COLUMNS = (
    "model_id",
    "model_family",
    "prediction_file",
    "prediction_sha256",
    "model_artifact_file",
    "model_artifact_sha256",
    "model_contract_file",
    "model_contract_file_sha256",
    "model_contract_sha256",
    "model_run_manifest_file",
    "model_run_manifest_sha256",
    "acquisition_manifest_sha256",
    "reference_mask_sha256",
    "spatial_holdout_manifest_sha256",
    "reviewer_qualification_file_sha256",
    "execution_authorization_manifest_sha256",
    "threshold_selection_manifest_sha256",
    "completed_at_utc",
    "execution_status",
    "spatial_holdout_untouched",
    "can_feed_decision_layer",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

CELL_GRID_COLUMNS = (
    "cell_id",
    "x",
    "y",
    "row_index",
    "column_index",
    "cell_area_m2",
    "grid_contract_sha256",
)

HOLDOUT_MEMBERSHIP_COLUMNS = (
    *CELL_GRID_COLUMNS,
    "spatial_group_id",
    "split",
)

PREDICTION_COLUMNS = (
    "cell_id",
    "spatial_group_id",
    "split",
    "probability_0_1",
)

REFERENCE_CELL_COLUMNS = (
    "cell_id",
    "reference_flood_extent",
    *ERROR_STRATA,
)

SHA256_RE = re.compile(r"[0-9a-f]{64}")
EPSG_RE = re.compile(r"EPSG:\d+", re.IGNORECASE)
PRODUCT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{2,255}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
PRIVATE_PATH_RE = re.compile(
    r"(?:^|[\s\"'=])(?:[A-Za-z]:[\\/]|file://|"
    r"\\\\[^\\/\s]+[\\/][^\\/\s]+|"
    r"/(?:home|Users|private|tmp|var|opt|mnt|srv|root|Volumes|data|"
    r"workspace|usr|run)(?:[\\/]|$))",
    re.IGNORECASE,
)
EXPECTED_GEOAI_VERSION = "0.41.1"
EXPECTED_GEOAI_COMMIT = "6833c8b71fb18f5b8ea17d5d9f8e0745157643c2"
REQUIRED_SAR_CHANNELS = (
    "pre_event_vv",
    "post_event_vv",
    "pre_event_vh",
    "post_event_vh",
    "vv_change",
    "vh_change",
)


class ControlledExperimentError(ValueError):
    """Raised when experiment evidence is malformed, incomplete, or unsafe."""


_VERIFIED_ACQUISITION_MARKER = object()


@dataclass(frozen=True, slots=True)
class AcquisitionGateAssessment:
    """Deterministic result of validating the acquisition manifest and bytes."""

    experiment_id: str
    study_area: str
    manifest_sha256: str
    manifest_file_sha256: str | None
    sha256_by_role: tuple[tuple[str, str], ...]
    authority_receipt_sha256: str | None
    authority_signing_key_id: str | None
    authority_issued_at_utc: datetime | None
    authority_expires_at_utc: datetime | None
    ready: bool
    blockers: tuple[str, ...]
    external_authority_signing_key_id: str | None
    external_authority_decision_sha256: str | None
    _verification_marker: object

    def __post_init__(self) -> None:
        if self._verification_marker is not _VERIFIED_ACQUISITION_MARKER:
            raise ControlledExperimentError(
                "Acquisition assessment must be created by the verified manifest path."
            )

    @property
    def reference_mask_sha256(self) -> str:
        return dict(self.sha256_by_role)["reference_mask"]

    def to_dict(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "study_area": self.study_area,
            "manifest_sha256": self.manifest_sha256,
            "manifest_file_sha256": self.manifest_file_sha256,
            "sha256_by_role": dict(self.sha256_by_role),
            "authority_receipt_sha256": self.authority_receipt_sha256,
            "authority_signing_key_id": self.authority_signing_key_id,
            "authority_issued_at_utc": (
                _format_utc(self.authority_issued_at_utc)
                if self.authority_issued_at_utc is not None
                else None
            ),
            "authority_expires_at_utc": (
                _format_utc(self.authority_expires_at_utc)
                if self.authority_expires_at_utc is not None
                else None
            ),
            "external_authority_signing_key_id": (
                self.external_authority_signing_key_id
            ),
            "external_authority_decision_sha256": (
                self.external_authority_decision_sha256
            ),
            "ready": self.ready,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True, slots=True)
class FrozenCellMembership:
    """One cell cryptographically bound to the frozen grid and spatial split."""

    cell_id: str
    x: float
    y: float
    row_index: int
    column_index: int
    cell_area_m2: float
    grid_contract_sha256: str
    spatial_group_id: str
    split: str

    def to_dict(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "x": self.x,
            "y": self.y,
            "row_index": self.row_index,
            "column_index": self.column_index,
            "cell_area_m2": self.cell_area_m2,
            "grid_contract_sha256": self.grid_contract_sha256,
            "spatial_group_id": self.spatial_group_id,
            "split": self.split,
        }


@dataclass(frozen=True, slots=True)
class VerifiedGridContract:
    """Exact-byte grid contract used to derive centers and physical cell area."""

    file_name: str
    file_sha256: str
    target_crs: str
    transform: tuple[float, float, float, float, float, float]
    width: int
    height: int
    cell_ids_sha256: str

    @property
    def cell_count(self) -> int:
        return self.width * self.height

    @property
    def cell_area_m2(self) -> float:
        a, b, _c, d, e, _f = self.transform
        return abs(a * e - b * d)


_VERIFIED_HOLDOUT_MARKER = object()


@dataclass(frozen=True, slots=True)
class VerifiedSpatialHoldout:
    """A signed holdout receipt plus its re-derived authoritative membership."""

    receipt: dict[str, object]
    memberships: tuple[FrozenCellMembership, ...]
    _verified_receipt_sha256: str
    _verification_marker: object

    def __post_init__(self) -> None:
        if self._verification_marker is not _VERIFIED_HOLDOUT_MARKER:
            raise ControlledExperimentError(
                "Spatial holdout must be created by the signed verifier."
            )
        if _canonical_sha256(self.receipt) != self._verified_receipt_sha256:
            raise ControlledExperimentError(
                "Spatial holdout receipt differs from the verified snapshot."
            )

    @property
    def manifest_sha256(self) -> str:
        return str(self.receipt["manifest_sha256"])

    @property
    def membership_sha256(self) -> str:
        return str(self.receipt["membership_sha256"])

    @property
    def training_partition_sha256(self) -> str:
        return self._partition_sha256("train")

    @property
    def calibration_partition_sha256(self) -> str:
        return self._partition_sha256("calibration")

    @property
    def final_holdout_partition_sha256(self) -> str:
        return self._partition_sha256("final_holdout")

    def _partition_sha256(self, split: str) -> str:
        rows = [
            membership.to_dict()
            for membership in self.memberships
            if membership.split == split
        ]
        if not rows:
            raise ControlledExperimentError(
                f"Verified spatial holdout has no {split} cells."
            )
        digest = _canonical_sha256(rows)
        declared = self.receipt.get("partition_sha256_by_split")
        if not isinstance(declared, Mapping) or declared.get(split) != digest:
            raise ControlledExperimentError(
                f"Verified spatial holdout {split} membership was substituted."
            )
        return digest


_VERIFIED_REVIEWER_QUALIFICATION_MARKER = object()


@dataclass(frozen=True, slots=True)
class VerifiedReviewerQualification:
    """A dual-signed calibration/adjudication decision bound to this event."""

    experiment_id: str
    study_area: str
    acquisition_manifest_sha256: str
    reference_mask_sha256: str
    calibration_release_receipt_sha256: str
    calibration_release_file_sha256: str
    calibration_receipt_sha256: str
    calibration_file_sha256: str
    approved_query_manifest_file_sha256: str
    reviewer_query_manifest_sha256: str
    grid_contract_sha256_by_query: tuple[tuple[str, str], ...]
    source_registry_sha256_by_query: tuple[tuple[str, str], ...]
    source_timestamp_by_query: tuple[tuple[str, str], ...]
    calibration_query_ids: tuple[str, ...]
    fresh_retest_query_ids: tuple[str, ...]
    reviewer_ids: tuple[str, ...]
    adjudicator_id: str
    disagreement_evidence_sha256: str
    disagreement_resolution_manifest_sha256: str
    error_strata_file_sha256: str
    formal_review_not_before_utc: datetime
    qualified_at_utc: datetime
    expires_at_utc: datetime
    manifest_sha256: str
    receipt_file_sha256: str
    reviewer_signing_key_id: str
    adjudicator_signing_key_id: str
    _verification_marker: object

    def __post_init__(self) -> None:
        if self._verification_marker is not _VERIFIED_REVIEWER_QUALIFICATION_MARKER:
            raise ControlledExperimentError(
                "Reviewer qualification must be created by the dual-signature verifier."
            )


_VERIFIED_CALIBRATION_REFERENCE_MARKER = object()


@dataclass(frozen=True, slots=True)
class VerifiedCalibrationReference:
    """A calibration-only projection verified without opening final-holdout truth."""

    experiment_id: str
    study_area: str
    reference_receipt_file_sha256: str
    reference_manifest_sha256: str
    reference_cell_evidence_sha256: str
    reference_mask_sha256: str
    reviewer_qualification_manifest_sha256: str
    spatial_holdout_manifest_sha256: str
    calibration_partition_sha256: str
    calibration_file_sha256: str
    reference_signing_key_id: str
    derived_at_utc: datetime
    cells: tuple[tuple[str, int], ...]
    _verification_marker: object

    def __post_init__(self) -> None:
        if self._verification_marker is not _VERIFIED_CALIBRATION_REFERENCE_MARKER:
            raise ControlledExperimentError(
                "Calibration reference must be created by the signed verifier."
            )

    @property
    def frame(self) -> pd.DataFrame:
        """Return a fresh calibration projection so callers cannot mutate truth."""

        return pd.DataFrame(
            self.cells,
            columns=("cell_id", "reference_flood_extent"),
        )


_VERIFIED_EXECUTION_AUTHORIZATION_MARKER = object()


@dataclass(frozen=True, slots=True)
class VerifiedExecutionAuthorization:
    """A signed pre-execution gate that contains no model performance evidence."""

    experiment_id: str
    study_area: str
    acquisition_manifest_sha256: str
    reviewer_qualification_manifest_sha256: str
    spatial_holdout_manifest_sha256: str
    reference_cell_manifest_sha256: str
    promotion_policy_manifest_sha256: str
    authorized_at_utc: datetime
    expires_at_utc: datetime
    manifest_sha256: str
    receipt_file_sha256: str
    signing_key_id: str
    _verification_marker: object

    def __post_init__(self) -> None:
        if self._verification_marker is not _VERIFIED_EXECUTION_AUTHORIZATION_MARKER:
            raise ControlledExperimentError(
                "Execution authorization must be created by the signed verifier."
            )


@dataclass(frozen=True, slots=True)
class ReferenceCell:
    """One immutable qualified-reference label and its documented strata."""

    cell_id: str
    reference_flood_extent: int
    error_strata: tuple[tuple[str, bool], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "reference_flood_extent": self.reference_flood_extent,
            **dict(self.error_strata),
        }


_VERIFIED_REFERENCE_MARKER = object()


@dataclass(frozen=True, slots=True)
class VerifiedReferenceCellEvidence:
    """Reference cells admitted only after signed receipt and byte verification."""

    experiment_id: str
    study_area: str
    reference_mask_sha256: str
    spatial_holdout_manifest_sha256: str
    spatial_holdout_membership_sha256: str
    grid_contract_sha256: str
    reviewer_qualification_manifest_sha256: str
    manifest_sha256: str
    receipt_file_sha256: str
    evidence_file_sha256: str
    calibration_reference_file_sha256: str
    error_strata_file_sha256: str
    derived_at_utc: datetime
    signing_key_id: str
    cells: tuple[ReferenceCell, ...]
    _verification_marker: object

    def __post_init__(self) -> None:
        if self._verification_marker is not _VERIFIED_REFERENCE_MARKER:
            raise ControlledExperimentError(
                "Reference-cell evidence must be created by the signed verifier."
            )


def assess_acquisition_manifest(
    source: pd.DataFrame | str | Path,
    *,
    artifact_paths: Mapping[str, str | Path] | None = None,
    authority_receipt_path: str | Path | None = None,
    signing_keys: Mapping[str, bytes] | None = None,
    external_authority_public_keys: Mapping[str, bytes] | None = None,
    verified_at_utc: datetime | None = None,
) -> AcquisitionGateAssessment:
    """Validate product identity, permission fields, timing, and local bytes.

    ``artifact_paths`` is deliberately separate from the publishable manifest:
    it maps the three roles to private external-workspace files at execution
    time.  Those absolute paths are never serialized into the receipt.
    """

    frame, file_sha = _coerce_csv(source, "acquisition manifest")
    _require_columns(frame, ACQUISITION_COLUMNS, "acquisition manifest")
    if len(frame) != len(REQUIRED_INPUT_ROLES):
        raise ControlledExperimentError(
            "Acquisition manifest must contain exactly pre, post, and reference rows."
        )
    frame = frame.fillna("").copy()
    roles = tuple(str(value).strip() for value in frame["role"])
    if set(roles) != set(REQUIRED_INPUT_ROLES) or len(set(roles)) != len(roles):
        raise ControlledExperimentError(
            "Acquisition roles must be unique and exactly pre_event_sar, "
            "post_event_sar, and reference_mask."
        )
    product_ids = tuple(
        _product_id(value, f"{role} product_id")
        for role, value in zip(roles, frame["product_id"], strict=True)
    )
    if len(set(product_ids)) != len(product_ids):
        raise ControlledExperimentError("Acquisition product IDs must be unique.")
    experiment_ids = {_text(value, "experiment_id") for value in frame["experiment_id"]}
    study_areas = {_text(value, "study_area") for value in frame["study_area"]}
    if len(experiment_ids) != 1 or len(study_areas) != 1:
        raise ControlledExperimentError(
            "All acquisition rows must share one experiment_id and study_area."
        )

    normalized_rows: list[dict[str, object]] = []
    blockers: list[str] = []
    sha_by_role: dict[str, str] = {}
    times: dict[str, tuple[datetime, datetime]] = {}
    paths = dict(artifact_paths or {})
    unexpected_paths = sorted(set(paths) - set(REQUIRED_INPUT_ROLES))
    if unexpected_paths:
        raise ControlledExperimentError(
            "Unknown acquisition artifact role(s): " + ", ".join(unexpected_paths)
        )

    for raw in frame.to_dict("records"):
        role = _text(raw["role"], "role")
        schema = _text(raw["schema_version"], "schema_version")
        if schema != ACQUISITION_SCHEMA:
            raise ControlledExperimentError(
                f"{role}: schema_version must be {ACQUISITION_SCHEMA}."
            )
        source_url = _text(raw["source_url"], "source_url")
        if not source_url.startswith("https://"):
            raise ControlledExperimentError(f"{role}: source_url must use HTTPS.")
        source_name = _text(raw["source_name"], f"{role} source_name")
        product_id = _product_id(raw["product_id"], f"{role} product_id")
        assumptions = _text(raw["assumptions"], f"{role} assumptions")
        _redacted_path_hint(raw["local_path_hint"], role)
        start = _timestamp(raw["acquisition_start_utc"], f"{role} acquisition start")
        end = _timestamp(raw["acquisition_end_utc"], f"{role} acquisition end")
        if end < start:
            raise ControlledExperimentError(
                f"{role}: acquisition_end_utc precedes acquisition_start_utc."
            )
        source_timestamp = _timestamp(
            raw["source_timestamp"], f"{role} source_timestamp"
        )
        if not start <= source_timestamp <= end:
            raise ControlledExperimentError(
                f"{role}: source_timestamp is outside the acquisition interval."
            )
        times[role] = (start, end)
        digest = _optional_sha256(raw["sha256"], f"{role} sha256")
        sha_by_role[role] = digest
        row_blockers: list[str] = []
        if str(raw["sha256_status"]).strip() != "verified" or not digest:
            row_blockers.append("checksum status is not verified")
        private_path = paths.get(role)
        if private_path is None:
            row_blockers.append("local artifact was not supplied for byte verification")
        else:
            artifact = Path(private_path)
            if not artifact.is_file():
                row_blockers.append("local artifact is missing")
            elif not digest or _file_sha256(artifact) != digest:
                row_blockers.append(
                    "local artifact SHA-256 does not match the manifest"
                )

        local_allowed = _strict_bool(
            raw["local_analysis_allowed"], f"{role} local_analysis_allowed"
        )
        derived_allowed = _strict_bool(
            raw["derived_metrics_allowed"], f"{role} derived_metrics_allowed"
        )
        ml_allowed = _strict_bool(
            raw["ml_label_use_allowed"], f"{role} ml_label_use_allowed"
        )
        processing_allowed = _strict_bool(
            raw["processing_allowed"], f"{role} processing_allowed"
        )
        if str(raw["license_status"]).strip() != "confirmed_for_experiment":
            row_blockers.append("license is not confirmed for this experiment")
        if not local_allowed:
            row_blockers.append("local analysis permission is not confirmed")
        if not derived_allowed:
            row_blockers.append("derived metrics permission is not confirmed")
        if not ml_allowed:
            row_blockers.append("ML-label/model use permission is not confirmed")
        if str(raw["redistribution_status"]).strip() not in {
            "reference_only",
            "redistributable",
        }:
            row_blockers.append("redistribution/reference-only status is unresolved")
        if str(raw["temporal_alignment_status"]).strip() != "confirmed":
            row_blockers.append("temporal alignment is not confirmed")
        if (
            role == "reference_mask"
            and str(raw["reference_mask_status"]).strip()
            != "qualified_expert_or_adjudicated"
        ):
            row_blockers.append(
                "reference mask is not qualified expert/adjudicated truth"
            )
        if (
            role != "reference_mask"
            and str(raw["reference_mask_status"]).strip() != "not_applicable"
        ):
            raise ControlledExperimentError(
                f"{role}: reference_mask_status must be not_applicable."
            )
        if processing_allowed and row_blockers:
            raise ControlledExperimentError(
                f"{role}: processing_allowed=true attempts to override: "
                + "; ".join(row_blockers)
            )
        if not processing_allowed:
            row_blockers.append("processing_allowed is false")
        blockers.extend(f"{role}: {reason}" for reason in row_blockers)

        normalized = {
            column: str(raw[column]).strip() for column in ACQUISITION_COLUMNS
        }
        normalized.update(
            {
                "source_name": source_name,
                "source_url": source_url,
                "product_id": product_id,
                "acquisition_start_utc": _format_utc(start),
                "acquisition_end_utc": _format_utc(end),
                "source_timestamp": _format_utc(source_timestamp),
                "assumptions": assumptions,
                "local_analysis_allowed": local_allowed,
                "derived_metrics_allowed": derived_allowed,
                "ml_label_use_allowed": ml_allowed,
                "processing_allowed": processing_allowed,
            }
        )
        normalized_rows.append(normalized)

    if times["pre_event_sar"][1] >= times["post_event_sar"][0]:
        blockers.append(
            "pre_event_sar: acquisition is not strictly before post_event_sar"
        )
    reference_start, reference_end = times["reference_mask"]
    post_start = times["post_event_sar"][0]
    if not reference_start <= post_start <= reference_end:
        blockers.append(
            "reference_mask: observation interval does not include the post-event acquisition"
        )

    normalized_rows.sort(key=lambda row: str(row["role"]))
    manifest_sha = _canonical_sha256(
        {"schema_version": ACQUISITION_SCHEMA, "rows": normalized_rows}
    )
    authority_receipt_sha256: str | None = None
    authority_payload: dict[str, object] | None = None
    if authority_receipt_path is None:
        blockers.append(
            "acquisition_authority: externally signed product-specific authority "
            "decision and internal integrity receipt are missing"
        )
    else:
        authority_path = Path(authority_receipt_path)
        try:
            authority_payload, authority_receipt_sha256 = (
                _verify_acquisition_authority_receipt(
                    authority_path,
                    manifest_sha256=manifest_sha,
                    experiment_id=next(iter(experiment_ids)),
                    study_area=next(iter(study_areas)),
                    normalized_rows=normalized_rows,
                    signing_keys=signing_keys or {},
                    external_authority_public_keys=(
                        external_authority_public_keys or {}
                    ),
                    verified_at_utc=verified_at_utc or datetime.now(UTC),
                )
            )
        except (ControlledExperimentError, OSError) as exc:
            blockers.append(f"acquisition_authority: receipt is invalid: {exc}")

    return AcquisitionGateAssessment(
        experiment_id=next(iter(experiment_ids)),
        study_area=next(iter(study_areas)),
        manifest_sha256=manifest_sha,
        manifest_file_sha256=file_sha,
        sha256_by_role=tuple(sorted(sha_by_role.items())),
        authority_receipt_sha256=authority_receipt_sha256,
        authority_signing_key_id=(
            str(authority_payload["signing_key_id"])
            if authority_payload is not None
            else None
        ),
        authority_issued_at_utc=(
            _timestamp(authority_payload["issued_at_utc"], "authority issued_at_utc")
            if authority_payload is not None
            else None
        ),
        authority_expires_at_utc=(
            _timestamp(authority_payload["expires_at_utc"], "authority expires_at_utc")
            if authority_payload is not None
            else None
        ),
        external_authority_signing_key_id=(
            str(authority_payload["external_authority_signing_key_id"])
            if authority_payload is not None
            else None
        ),
        external_authority_decision_sha256=(
            str(authority_payload["external_authority_decision_sha256"])
            if authority_payload is not None
            else None
        ),
        ready=not blockers,
        blockers=tuple(sorted(set(blockers))),
        _verification_marker=_VERIFIED_ACQUISITION_MARKER,
    )


def write_acquisition_authority_receipt(
    acquisition: AcquisitionGateAssessment,
    acquisition_source: pd.DataFrame | str | Path,
    *,
    external_authority_decision_path: str | Path,
    external_authority_signature_path: str | Path,
    external_authority_public_keys: Mapping[str, bytes],
    catalog_evidence_paths_by_role: Mapping[str, str | Path],
    license_evidence_paths_by_role: Mapping[str, str | Path],
    verified_at_utc: datetime,
    receipt_signing_key_id: str,
    receipt_signing_key: bytes,
    output_path: str | Path,
) -> dict[str, object]:
    """Bind an externally signed authority decision into an internal receipt.

    The HMAC on the resulting receipt is only an internal integrity envelope. It
    cannot create licensing authority: readiness also requires a detached
    Ed25519 signature from a separately trusted external public key.
    """

    _verify_acquisition_assessment(acquisition)
    allowed_blocker = (
        "acquisition_authority: externally signed product-specific authority "
        "decision and internal integrity receipt are missing"
    )
    remaining = [item for item in acquisition.blockers if item != allowed_blocker]
    if remaining:
        raise ControlledExperimentError(
            "Acquisition authority cannot be issued while base gates are blocked: "
            + "; ".join(remaining)
        )
    catalog_paths = _exact_role_paths(
        catalog_evidence_paths_by_role, "catalog evidence"
    )
    license_paths = _exact_role_paths(
        license_evidence_paths_by_role, "license evidence"
    )
    frame, _file_sha = _coerce_csv(acquisition_source, "acquisition manifest")
    _require_columns(frame, ACQUISITION_COLUMNS, "acquisition manifest")
    expected_rows = _external_product_expectations(frame.fillna(""))
    verified = _verify_external_authority_decision_files(
        Path(external_authority_decision_path),
        Path(external_authority_signature_path),
        manifest_sha256=acquisition.manifest_sha256,
        experiment_id=acquisition.experiment_id,
        study_area=acquisition.study_area,
        expected_rows=expected_rows,
        external_authority_public_keys=external_authority_public_keys,
        verified_at_utc=verified_at_utc,
        catalog_evidence_sha256_by_role={
            role: _file_sha256(path) for role, path in catalog_paths.items()
        },
        license_evidence_sha256_by_role={
            role: _file_sha256(path) for role, path in license_paths.items()
        },
    )
    decision = verified["decision"]
    signer = decision["authorized_signer"]
    authority_id = f"{signer['organization']}::{signer['name']}"
    payload: dict[str, object] = {
        "artifact_schema": ACQUISITION_AUTHORITY_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "authority_id": authority_id,
        "external_authority_decision_id": decision["decision_id"],
        "signing_role": SIGNING_ROLES["acquisition"],
        "internal_trust_notice": (
            "HMAC-SHA256 authenticates repository receipt integrity only; external "
            "authority derives exclusively from the verified detached Ed25519 decision."
        ),
        "issued_at_utc": signer["decision_issued_at_utc"],
        "expires_at_utc": signer["decision_expires_at_utc"],
        "external_authority_decision_file": Path(external_authority_decision_path).name,
        "external_authority_decision_file_sha256": verified["decision_file_sha256"],
        "external_authority_decision_sha256": verified["decision_sha256"],
        "external_authority_signature_file": Path(
            external_authority_signature_path
        ).name,
        "external_authority_signature_file_sha256": verified["signature_file_sha256"],
        "external_authority_signature_base64": verified["signature_base64"],
        "external_authority_signing_key_id": signer["signing_key_id"],
        "external_authority_public_key_sha256": signer["public_key_sha256"],
        "external_authority_decision": decision,
        "authorizations": decision["products"],
        "official_warning": False,
        "can_feed_decision_layer": False,
    }
    sealed = _seal_signed_payload(
        payload,
        signing_key_id=receipt_signing_key_id,
        signing_key=receipt_signing_key,
        self_hash_field="manifest_sha256",
    )
    _write_immutable_json(sealed, Path(output_path), "Acquisition authority receipt")
    return sealed


def _verify_acquisition_authority_receipt(
    path: Path,
    *,
    manifest_sha256: str,
    experiment_id: str,
    study_area: str,
    normalized_rows: Sequence[Mapping[str, object]],
    signing_keys: Mapping[str, bytes],
    external_authority_public_keys: Mapping[str, bytes],
    verified_at_utc: datetime,
) -> tuple[dict[str, object], str]:
    receipt_bytes = _read_stable_bytes(path, "acquisition authority receipt")
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    payload = _json_object_bytes(receipt_bytes, "acquisition authority receipt")
    required = {
        "artifact_schema",
        "experiment_id",
        "study_area",
        "acquisition_manifest_sha256",
        "authority_id",
        "external_authority_decision_id",
        "signing_role",
        "internal_trust_notice",
        "issued_at_utc",
        "expires_at_utc",
        "external_authority_decision_file",
        "external_authority_decision_file_sha256",
        "external_authority_decision_sha256",
        "external_authority_signature_file",
        "external_authority_signature_file_sha256",
        "external_authority_signature_base64",
        "external_authority_signing_key_id",
        "external_authority_public_key_sha256",
        "external_authority_decision",
        "authorizations",
        "official_warning",
        "can_feed_decision_layer",
        "signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "signature",
    }
    _exact_keys(payload, required, "acquisition authority receipt")
    if payload["artifact_schema"] != ACQUISITION_AUTHORITY_SCHEMA:
        raise ControlledExperimentError("Acquisition authority schema is unsupported.")
    if payload["signing_role"] != SIGNING_ROLES["acquisition"]:
        raise ControlledExperimentError(
            "Acquisition authority signing role is invalid."
        )
    _verify_signed_payload(payload, signing_keys, "acquisition authority receipt")
    _verify_self_hash(payload, "manifest_sha256", "acquisition authority receipt")
    if payload["experiment_id"] != experiment_id or payload["study_area"] != study_area:
        raise ControlledExperimentError("Acquisition authority scope was substituted.")
    if payload["acquisition_manifest_sha256"] != manifest_sha256:
        raise ControlledExperimentError(
            "Acquisition authority manifest was substituted."
        )
    if "integrity only" not in _text(
        payload["internal_trust_notice"], "internal_trust_notice"
    ):
        raise ControlledExperimentError(
            "Acquisition receipt does not distinguish internal integrity from authority."
        )
    if (
        payload["official_warning"] is not False
        or payload["can_feed_decision_layer"] is not False
    ):
        raise ControlledExperimentError(
            "Acquisition authority has unsafe status fields."
        )
    decision = payload["external_authority_decision"]
    if not isinstance(decision, Mapping):
        raise ControlledExperimentError(
            "Acquisition receipt external authority decision is malformed."
        )
    signature = _decode_ed25519_material(
        payload["external_authority_signature_base64"],
        expected_length=64,
        label="external authority signature",
    )
    expected_rows = _external_product_expectations(pd.DataFrame(normalized_rows))
    decision_metadata = _validate_external_authority_decision_payload(
        dict(decision),
        manifest_sha256=manifest_sha256,
        experiment_id=experiment_id,
        study_area=study_area,
        expected_rows=expected_rows,
        external_authority_public_keys=external_authority_public_keys,
        signature=signature,
        verified_at_utc=verified_at_utc,
    )
    if payload["authorizations"] != decision["products"]:
        raise ControlledExperimentError(
            "Acquisition receipt authorizations differ from the external decision."
        )
    expected_external = {
        "external_authority_decision_sha256": decision_metadata["decision_sha256"],
        "external_authority_signing_key_id": decision_metadata["signing_key_id"],
        "external_authority_public_key_sha256": decision_metadata["public_key_sha256"],
        "issued_at_utc": decision_metadata["issued_at_utc"],
        "expires_at_utc": decision_metadata["expires_at_utc"],
        "authority_id": decision_metadata["authority_id"],
        "external_authority_decision_id": decision["decision_id"],
    }
    for field, expected_value in expected_external.items():
        if payload[field] != expected_value:
            raise ControlledExperimentError(
                f"Acquisition receipt {field} differs from external authority."
            )
    _basename(payload["external_authority_decision_file"], "decision file")
    _sha256(
        payload["external_authority_decision_file_sha256"],
        "external authority decision file SHA-256",
    )
    _basename(payload["external_authority_signature_file"], "signature file")
    _sha256(
        payload["external_authority_signature_file_sha256"],
        "external authority signature file SHA-256",
    )
    return payload, receipt_sha256


def _verify_acquisition_assessment(acquisition: AcquisitionGateAssessment) -> None:
    if (
        not isinstance(acquisition, AcquisitionGateAssessment)
        or acquisition._verification_marker is not _VERIFIED_ACQUISITION_MARKER
    ):
        raise ControlledExperimentError(
            "Acquisition evidence must come from assess_acquisition_manifest."
        )


def _exact_role_paths(values: Mapping[str, str | Path], label: str) -> dict[str, Path]:
    if set(values) != set(REQUIRED_INPUT_ROLES):
        raise ControlledExperimentError(
            f"{label.capitalize()} mapping must cover exactly the three acquisition roles."
        )
    paths = {role: Path(values[role]) for role in REQUIRED_INPUT_ROLES}
    for role, path in paths.items():
        if not path.is_file():
            raise ControlledExperimentError(f"{role}: {label} file is missing.")
    return paths


def _external_product_expectations(
    frame: pd.DataFrame,
) -> dict[str, dict[str, object]]:
    expectations: dict[str, dict[str, object]] = {}
    for raw in frame.to_dict("records"):
        role = _text(raw["role"], "role")
        if role in expectations:
            raise ControlledExperimentError(
                "Acquisition manifest contains duplicate product roles."
            )
        expectations[role] = {
            "role": role,
            "source_name": _text(raw["source_name"], f"{role} source_name"),
            "source_url": _https_url(raw["source_url"], f"{role} source_url"),
            "product_id": _product_id(raw["product_id"], f"{role} product_id"),
            "acquisition_start_utc": _format_utc(
                _timestamp(raw["acquisition_start_utc"], f"{role} acquisition start")
            ),
            "acquisition_end_utc": _format_utc(
                _timestamp(raw["acquisition_end_utc"], f"{role} acquisition end")
            ),
            "source_timestamp": _format_utc(
                _timestamp(raw["source_timestamp"], f"{role} source timestamp")
            ),
            "artifact_sha256": _sha256(raw["sha256"], f"{role} artifact SHA-256"),
            "license_status": _text(raw["license_status"], f"{role} license_status"),
            "redistribution_status": _text(
                raw["redistribution_status"], f"{role} redistribution_status"
            ),
            "reference_mask_status": _text(
                raw["reference_mask_status"], f"{role} reference_mask_status"
            ),
            "temporal_alignment_status": _text(
                raw["temporal_alignment_status"],
                f"{role} temporal_alignment_status",
            ),
            "assumptions": _text(raw["assumptions"], f"{role} assumptions"),
            "local_analysis_allowed": _strict_bool(
                raw["local_analysis_allowed"], f"{role} local_analysis_allowed"
            ),
            "derived_metrics_allowed": _strict_bool(
                raw["derived_metrics_allowed"], f"{role} derived_metrics_allowed"
            ),
            "ml_label_use_allowed": _strict_bool(
                raw["ml_label_use_allowed"], f"{role} ml_label_use_allowed"
            ),
        }
    if set(expectations) != set(REQUIRED_INPUT_ROLES):
        raise ControlledExperimentError(
            "External authority decision requires exactly the three acquisition roles."
        )
    return expectations


def _verify_external_authority_decision_files(
    decision_path: Path,
    signature_path: Path,
    *,
    manifest_sha256: str,
    experiment_id: str,
    study_area: str,
    expected_rows: Mapping[str, Mapping[str, object]],
    external_authority_public_keys: Mapping[str, bytes],
    verified_at_utc: datetime,
    catalog_evidence_sha256_by_role: Mapping[str, str],
    license_evidence_sha256_by_role: Mapping[str, str],
) -> dict[str, object]:
    decision_bytes = _read_stable_bytes(decision_path, "external authority decision")
    signature_bytes = _read_stable_bytes(
        signature_path, "external authority detached signature"
    )
    decision = _json_object_bytes(decision_bytes, "external authority decision")
    signature = _decode_ed25519_material(
        signature_bytes.decode("ascii"),
        expected_length=64,
        label="external authority detached signature",
    )
    metadata = _validate_external_authority_decision_payload(
        decision,
        manifest_sha256=manifest_sha256,
        experiment_id=experiment_id,
        study_area=study_area,
        expected_rows=expected_rows,
        external_authority_public_keys=external_authority_public_keys,
        signature=signature,
        verified_at_utc=verified_at_utc,
        catalog_evidence_sha256_by_role=catalog_evidence_sha256_by_role,
        license_evidence_sha256_by_role=license_evidence_sha256_by_role,
    )
    return {
        **metadata,
        "decision": decision,
        "decision_file_sha256": hashlib.sha256(decision_bytes).hexdigest(),
        "signature_file_sha256": hashlib.sha256(signature_bytes).hexdigest(),
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }


def _validate_external_authority_decision_payload(
    decision: Mapping[str, object],
    *,
    manifest_sha256: str,
    experiment_id: str,
    study_area: str,
    expected_rows: Mapping[str, Mapping[str, object]],
    external_authority_public_keys: Mapping[str, bytes],
    signature: bytes,
    verified_at_utc: datetime,
    catalog_evidence_sha256_by_role: Mapping[str, str] | None = None,
    license_evidence_sha256_by_role: Mapping[str, str] | None = None,
) -> dict[str, object]:
    _exact_keys(
        decision,
        {
            "schema_version",
            "decision_id",
            "request_id",
            "experiment_id",
            "study_area",
            "acquisition_manifest_sha256",
            "decision_status",
            "products",
            "required_attribution_and_conditions",
            "authorized_signer",
            "signer_attestations",
            "official_warning",
        },
        "external authority decision",
    )
    if decision["schema_version"] != EXTERNAL_AUTHORITY_DECISION_SCHEMA:
        raise ControlledExperimentError(
            "External authority decision schema is unsupported."
        )
    _product_id(decision["decision_id"], "external decision_id")
    _product_id(decision["request_id"], "external request_id")
    if (
        decision["experiment_id"] != experiment_id
        or decision["study_area"] != study_area
        or decision["acquisition_manifest_sha256"] != manifest_sha256
    ):
        raise ControlledExperimentError(
            "External authority decision scope or manifest was substituted."
        )
    if decision["decision_status"] != "approved_for_controlled_experiment":
        raise ControlledExperimentError(
            "External authority decision is not affirmative."
        )
    if decision["official_warning"] is not False:
        raise ControlledExperimentError(
            "External authority decision cannot claim an official warning."
        )
    conditions = decision["required_attribution_and_conditions"]
    if not isinstance(conditions, Mapping):
        raise ControlledExperimentError(
            "External attribution and conditions must be an object."
        )
    _exact_keys(
        conditions,
        {
            "unmodified_source_notice",
            "modified_or_derived_notice",
            "citation",
            "disclaimer",
            "additional_conditions",
        },
        "external attribution and conditions",
    )
    for field, value in conditions.items():
        _substantive_text(value, f"external attribution {field}")
    attestations = decision["signer_attestations"]
    if not isinstance(attestations, Mapping):
        raise ControlledExperimentError(
            "External signer attestations must be an object."
        )
    _exact_keys(
        attestations,
        set(EXTERNAL_SIGNER_ATTESTATIONS),
        "external signer attestations",
    )
    if any(attestations[field] is not True for field in EXTERNAL_SIGNER_ATTESTATIONS):
        raise ControlledExperimentError(
            "Every external signer attestation must be explicit true."
        )
    signer = decision["authorized_signer"]
    if not isinstance(signer, Mapping):
        raise ControlledExperimentError("External authorized signer must be an object.")
    _exact_keys(
        signer,
        {
            "name",
            "organization",
            "title_or_role",
            "authority_basis",
            "identity_evidence_type",
            "identity_evidence_sha256",
            "decision_issued_at_utc",
            "decision_expires_at_utc",
            "signing_key_id",
            "signature_algorithm",
            "public_key_sha256",
        },
        "external authorized signer",
    )
    for field in (
        "name",
        "organization",
        "title_or_role",
        "authority_basis",
        "identity_evidence_type",
    ):
        _substantive_text(signer[field], f"external signer {field}")
    _sha256(
        signer["identity_evidence_sha256"],
        "external signer identity_evidence_sha256",
    )
    key_id = _product_id(signer["signing_key_id"], "external signing_key_id")
    if signer["signature_algorithm"] != "Ed25519":
        raise ControlledExperimentError(
            "External authority signature algorithm must be Ed25519."
        )
    public_key_value = external_authority_public_keys.get(key_id)
    if public_key_value is None:
        raise ControlledExperimentError(
            "External authority public key is not trusted at runtime."
        )
    public_key = _validated_ed25519_public_key(public_key_value)
    public_key_sha = hashlib.sha256(public_key).hexdigest()
    if signer["public_key_sha256"] != public_key_sha:
        raise ControlledExperimentError(
            "External authority public-key fingerprint was substituted."
        )
    issued = _timestamp(signer["decision_issued_at_utc"], "external decision issue")
    expires = _timestamp(signer["decision_expires_at_utc"], "external decision expiry")
    verified = _timestamp(_format_utc(verified_at_utc), "verified_at_utc")
    latest_source = max(
        _timestamp(row["acquisition_end_utc"], "product acquisition end")
        for row in expected_rows.values()
    )
    if expires <= issued or issued < latest_source or not issued <= verified <= expires:
        raise ControlledExperimentError(
            "External authority decision is expired, premature, or not yet valid."
        )
    products = decision["products"]
    if not isinstance(products, list) or len(products) != len(REQUIRED_INPUT_ROLES):
        raise ControlledExperimentError(
            "External authority decision must contain exactly three products."
        )
    seen: set[str] = set()
    for product in products:
        if not isinstance(product, Mapping):
            raise ControlledExperimentError("External authority product is malformed.")
        _validate_external_authority_product(
            product,
            expected_rows=expected_rows,
            seen=seen,
            catalog_evidence_sha256_by_role=catalog_evidence_sha256_by_role,
            license_evidence_sha256_by_role=license_evidence_sha256_by_role,
        )
    if seen != set(REQUIRED_INPUT_ROLES):
        raise ControlledExperimentError(
            "External authority decision product roles are incomplete."
        )
    decision_sha = _canonical_sha256(decision)
    if not _ed25519_verify(public_key, signature, _canonical_json_bytes(decision)):
        raise ControlledExperimentError(
            "External authority detached Ed25519 signature is invalid."
        )
    return {
        "decision_sha256": decision_sha,
        "signing_key_id": key_id,
        "public_key_sha256": public_key_sha,
        "issued_at_utc": _format_utc(issued),
        "expires_at_utc": _format_utc(expires),
        "authority_id": f"{signer['organization']}::{signer['name']}",
    }


def _validate_external_authority_product(
    product: Mapping[str, object],
    *,
    expected_rows: Mapping[str, Mapping[str, object]],
    seen: set[str],
    catalog_evidence_sha256_by_role: Mapping[str, str] | None,
    license_evidence_sha256_by_role: Mapping[str, str] | None,
) -> None:
    _exact_keys(
        product,
        {
            "role",
            "source_name",
            "source_url",
            "product_id",
            "acquisition_start_utc",
            "acquisition_end_utc",
            "source_timestamp",
            "artifact_sha256",
            "catalog_evidence_sha256",
            "license_evidence_sha256",
            "terms_url",
            "license_status",
            "redistribution_status",
            "reference_mask_status",
            "temporal_alignment_status",
            "assumptions",
            "authority_decision",
            "permissions",
            "reference_qualification",
        },
        "external authority product",
    )
    role = _text(product["role"], "external product role")
    expected = expected_rows.get(role)
    if expected is None or role in seen:
        raise ControlledExperimentError(
            "External authority product roles are duplicated or unknown."
        )
    seen.add(role)
    for field in (
        "source_name",
        "source_url",
        "product_id",
        "acquisition_start_utc",
        "acquisition_end_utc",
        "source_timestamp",
        "artifact_sha256",
        "license_status",
        "redistribution_status",
        "reference_mask_status",
        "temporal_alignment_status",
        "assumptions",
    ):
        if product[field] != expected[field]:
            raise ControlledExperimentError(
                f"{role}: external authority {field} was substituted."
            )
    _https_url(product["terms_url"], f"{role} terms_url")
    catalog_sha = _sha256(
        product["catalog_evidence_sha256"], f"{role} catalog evidence SHA-256"
    )
    license_sha = _sha256(
        product["license_evidence_sha256"], f"{role} license evidence SHA-256"
    )
    if (
        catalog_evidence_sha256_by_role is not None
        and catalog_sha != catalog_evidence_sha256_by_role.get(role)
    ):
        raise ControlledExperimentError(
            f"{role}: catalog evidence bytes do not match the external decision."
        )
    if (
        license_evidence_sha256_by_role is not None
        and license_sha != license_evidence_sha256_by_role.get(role)
    ):
        raise ControlledExperimentError(
            f"{role}: license evidence bytes do not match the external decision."
        )
    if product["authority_decision"] != "approved_for_controlled_experiment":
        raise ControlledExperimentError(
            f"{role}: authority decision is not affirmative."
        )
    permissions = product["permissions"]
    if not isinstance(permissions, Mapping):
        raise ControlledExperimentError(f"{role}: permissions must be an object.")
    _exact_keys(
        permissions,
        set(EXTERNAL_PERMISSION_FIELDS),
        f"{role} external permissions",
    )
    always_required = set(EXTERNAL_PERMISSION_FIELDS) - {"source_redistribution"}
    if any(permissions[field] is not True for field in always_required):
        raise ControlledExperimentError(
            f"{role}: every required external permission must be explicit true."
        )
    redistribution = expected["redistribution_status"]
    expected_source_redistribution = redistribution == "redistributable"
    if permissions["source_redistribution"] is not expected_source_redistribution:
        raise ControlledExperimentError(
            f"{role}: source redistribution permission conflicts with its status."
        )
    if (
        expected["local_analysis_allowed"] is not True
        or expected["derived_metrics_allowed"] is not True
        or expected["ml_label_use_allowed"] is not True
    ):
        raise ControlledExperimentError(
            f"{role}: manifest permissions are not affirmative."
        )
    qualification = product["reference_qualification"]
    if role != "reference_mask":
        if qualification is not None:
            raise ControlledExperimentError(
                f"{role}: reference qualification must be null."
            )
        return
    if not isinstance(qualification, Mapping):
        raise ControlledExperimentError(
            "reference_mask: qualification evidence must be an object."
        )
    _exact_keys(
        qualification,
        {
            "status",
            "qualification_method",
            "known_uncertainty_and_error_categories",
            "independent_of_model_inputs",
        },
        "reference-mask qualification",
    )
    if (
        qualification["status"] != "qualified_expert_or_adjudicated"
        or qualification["independent_of_model_inputs"] is not True
    ):
        raise ControlledExperimentError(
            "Reference mask is not independently qualified."
        )
    _substantive_text(
        qualification["qualification_method"], "reference qualification method"
    )
    _substantive_text(
        qualification["known_uncertainty_and_error_categories"],
        "reference qualification uncertainty",
    )


def _require_ready_acquisition_for_holdout(
    acquisition: AcquisitionGateAssessment,
    *,
    frozen_at_utc: datetime,
) -> None:
    """Require a ready, signed acquisition that was valid when frozen."""

    _verify_acquisition_assessment(acquisition)
    if not acquisition.ready:
        raise ControlledExperimentError(
            "Spatial holdout requires a ready signed acquisition authority."
        )
    if (
        acquisition.authority_receipt_sha256 is None
        or acquisition.authority_signing_key_id is None
        or acquisition.authority_issued_at_utc is None
        or acquisition.authority_expires_at_utc is None
        or acquisition.external_authority_decision_sha256 is None
        or acquisition.external_authority_signing_key_id is None
    ):
        raise ControlledExperimentError(
            "Spatial holdout requires complete signed acquisition authority lineage."
        )
    _sha256(acquisition.manifest_sha256, "acquisition manifest SHA-256")
    _sha256(
        acquisition.authority_receipt_sha256,
        "acquisition authority receipt SHA-256",
    )
    _text(
        acquisition.authority_signing_key_id,
        "acquisition authority signing key ID",
    )
    _sha256(
        acquisition.external_authority_decision_sha256,
        "external authority decision SHA-256",
    )
    _text(
        acquisition.external_authority_signing_key_id,
        "external authority signing key ID",
    )
    if not (
        acquisition.authority_issued_at_utc
        <= frozen_at_utc
        <= acquisition.authority_expires_at_utc
    ):
        raise ControlledExperimentError(
            "Spatial holdout freeze time is outside acquisition authority validity."
        )


def _verify_holdout_acquisition_lineage(
    payload: Mapping[str, object],
    acquisition: AcquisitionGateAssessment,
) -> None:
    expected = {
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": (acquisition.authority_receipt_sha256),
        "acquisition_authority_signing_key_id": (acquisition.authority_signing_key_id),
        "external_authority_decision_sha256": (
            acquisition.external_authority_decision_sha256
        ),
        "external_authority_signing_key_id": (
            acquisition.external_authority_signing_key_id
        ),
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise ControlledExperimentError(
                f"Spatial holdout {field} was substituted across acquisitions."
            )
    if payload.get("signing_key_id") == acquisition.authority_signing_key_id:
        raise ControlledExperimentError(
            "Spatial holdout authority must be distinct from acquisition authority."
        )


def freeze_spatial_holdout(
    geometry_path: str | Path,
    *,
    acquisition: AcquisitionGateAssessment,
    grid_contract_path: str | Path,
    cell_grid_path: str | Path,
    membership_output_path: str | Path,
    target_crs: str,
    grid_contract_sha256: str,
    frozen_at_utc: datetime,
    assumptions: str,
    signing_key_id: str,
    signing_key: bytes,
    output_path: str | Path,
) -> VerifiedSpatialHoldout:
    """Freeze geometry-derived membership against one authorized acquisition."""

    geometry = Path(geometry_path)
    frozen_at = _timestamp(_format_utc(frozen_at_utc), "frozen_at_utc")
    _require_ready_acquisition_for_holdout(acquisition, frozen_at_utc=frozen_at)
    if _text(signing_key_id, "signing_key_id") == (
        acquisition.authority_signing_key_id
    ):
        raise ControlledExperimentError(
            "Spatial holdout authority signing key must differ from acquisition authority."
        )
    if not EPSG_RE.fullmatch(_text(target_crs, "target_crs")):
        raise ControlledExperimentError("target_crs must be an EPSG identifier.")
    _validate_equal_area_crs(target_crs)
    groups, group_geometries, geometry_sha256 = _load_spatial_groups(
        geometry,
        expected_crs=target_crs,
    )
    train_ids = sorted(
        group["spatial_group_id"] for group in groups if group["split"] == "train"
    )
    calibration_ids = sorted(
        group["spatial_group_id"] for group in groups if group["split"] == "calibration"
    )
    final_holdout_ids = sorted(
        group["spatial_group_id"]
        for group in groups
        if group["split"] == "final_holdout"
    )
    if not train_ids or not calibration_ids or not final_holdout_ids:
        raise ControlledExperimentError(
            "Spatial holdout requires non-empty train, calibration, and "
            "final_holdout polygons."
        )
    grid_contract = _load_grid_contract(
        Path(grid_contract_path),
        expected_sha256=_sha256(grid_contract_sha256, "grid_contract_sha256"),
        expected_crs=target_crs,
    )
    grid_sha = grid_contract.file_sha256
    cell_grid = _read_cell_grid(Path(cell_grid_path), grid_contract=grid_contract)
    memberships = _derive_memberships(cell_grid, group_geometries)
    membership_splits = {item.split for item in memberships}
    if not {"train", "calibration", "final_holdout"}.issubset(membership_splits):
        raise ControlledExperimentError(
            "Frozen cell membership requires non-empty train, calibration, and "
            "final_holdout cells."
        )
    membership_path = Path(membership_output_path)
    target = Path(output_path)
    if membership_path.suffix.lower() != ".csv":
        raise ControlledExperimentError("Holdout membership must be CSV.")
    if target.suffix.lower() != ".json":
        raise ControlledExperimentError("Spatial holdout receipt must be JSON.")
    if membership_path.exists() or target.exists():
        raise ControlledExperimentError(
            "Spatial holdout outputs are immutable and already exist."
        )
    membership_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [membership.to_dict() for membership in memberships],
        columns=HOLDOUT_MEMBERSHIP_COLUMNS,
    ).to_csv(membership_path, index=False, lineterminator="\n")
    partition_sha256_by_split = {
        split: _canonical_sha256(
            [item.to_dict() for item in memberships if item.split == split]
        )
        for split in ("train", "calibration", "final_holdout")
    }
    payload: dict[str, object] = {
        "artifact_schema": HOLDOUT_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": (acquisition.authority_receipt_sha256),
        "acquisition_authority_signing_key_id": (acquisition.authority_signing_key_id),
        "external_authority_decision_sha256": (
            acquisition.external_authority_decision_sha256
        ),
        "external_authority_signing_key_id": (
            acquisition.external_authority_signing_key_id
        ),
        "target_crs": target_crs.upper(),
        "geometry_file": geometry.name,
        "geometry_sha256": geometry_sha256,
        "membership_file": membership_path.name,
        "membership_sha256": _file_sha256(membership_path),
        "cell_count": len(memberships),
        "cell_area_m2": grid_contract.cell_area_m2,
        "grid_contract_file": grid_contract.file_name,
        "grid_contract_sha256": grid_sha,
        "frozen_at_utc": _format_utc(frozen_at),
        "signing_role": SIGNING_ROLES["holdout"],
        "created_before_model_fitting": True,
        "groups": groups,
        "training_ids": train_ids,
        "calibration_ids": calibration_ids,
        "final_holdout_ids": final_holdout_ids,
        "partition_sha256_by_split": partition_sha256_by_split,
        "assumptions": _text(assumptions, "assumptions"),
        "official_warning": False,
        "can_feed_decision_layer": False,
    }
    sealed = _seal_signed_payload(
        payload,
        signing_key_id=signing_key_id,
        signing_key=signing_key,
        self_hash_field="manifest_sha256",
    )
    _write_immutable_json(sealed, target, "Spatial holdout receipt")
    return load_spatial_holdout(
        target,
        geometry,
        Path(grid_contract_path),
        membership_path,
        acquisition=acquisition,
        signing_keys={signing_key_id: signing_key},
    )


def load_spatial_holdout(
    receipt_path: str | Path,
    geometry_path: str | Path,
    grid_contract_path: str | Path,
    membership_path: str | Path,
    *,
    acquisition: AcquisitionGateAssessment,
    signing_keys: Mapping[str, bytes],
) -> VerifiedSpatialHoldout:
    """Re-hash and re-derive a signed holdout; reject every substitution."""

    receipt_file = Path(receipt_path)
    payload = _json_object(receipt_file, "spatial holdout receipt")
    required = {
        "artifact_schema",
        "experiment_id",
        "study_area",
        "acquisition_manifest_sha256",
        "acquisition_authority_receipt_sha256",
        "acquisition_authority_signing_key_id",
        "external_authority_decision_sha256",
        "external_authority_signing_key_id",
        "target_crs",
        "geometry_file",
        "geometry_sha256",
        "membership_file",
        "membership_sha256",
        "cell_count",
        "cell_area_m2",
        "grid_contract_file",
        "grid_contract_sha256",
        "frozen_at_utc",
        "signing_role",
        "created_before_model_fitting",
        "groups",
        "training_ids",
        "calibration_ids",
        "final_holdout_ids",
        "partition_sha256_by_split",
        "assumptions",
        "official_warning",
        "can_feed_decision_layer",
        "signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "signature",
    }
    _exact_keys(payload, required, "spatial holdout receipt")
    if payload["artifact_schema"] != HOLDOUT_SCHEMA:
        raise ControlledExperimentError(
            "Spatial holdout receipt schema is unsupported."
        )
    _verify_signed_payload(payload, signing_keys, "spatial holdout receipt")
    _verify_self_hash(payload, "manifest_sha256", "spatial holdout receipt")
    _verify_holdout_acquisition_lineage(payload, acquisition)
    if payload["created_before_model_fitting"] is not True:
        raise ControlledExperimentError("Holdout must be frozen before model fitting.")
    if (
        payload["official_warning"] is not False
        or payload["can_feed_decision_layer"] is not False
    ):
        raise ControlledExperimentError(
            "Spatial holdout receipt has unsafe status fields."
        )
    geometry = Path(geometry_path)
    if geometry.name != payload["geometry_file"]:
        raise ControlledExperimentError(
            "Holdout geometry filename does not match receipt."
        )
    _validate_equal_area_crs(str(payload["target_crs"]))
    groups, group_geometries, geometry_sha256 = _load_spatial_groups(
        geometry,
        expected_crs=str(payload["target_crs"]),
    )
    if geometry_sha256 != _sha256(payload["geometry_sha256"], "geometry_sha256"):
        raise ControlledExperimentError(
            "Holdout geometry SHA-256 does not match receipt."
        )
    if groups != payload["groups"]:
        raise ControlledExperimentError(
            "Holdout polygon IDs, splits, or bounds changed."
        )
    train_ids = sorted(
        group["spatial_group_id"] for group in groups if group["split"] == "train"
    )
    calibration_ids = sorted(
        group["spatial_group_id"] for group in groups if group["split"] == "calibration"
    )
    final_holdout_ids = sorted(
        group["spatial_group_id"]
        for group in groups
        if group["split"] == "final_holdout"
    )
    if (
        payload["training_ids"] != train_ids
        or payload["calibration_ids"] != calibration_ids
        or payload["final_holdout_ids"] != final_holdout_ids
    ):
        raise ControlledExperimentError(
            "Holdout ID lists do not match geometry splits."
        )
    if payload["signing_role"] != SIGNING_ROLES["holdout"]:
        raise ControlledExperimentError("Spatial holdout signing role is invalid.")
    frozen_at = _timestamp(payload["frozen_at_utc"], "frozen_at_utc")
    _require_ready_acquisition_for_holdout(acquisition, frozen_at_utc=frozen_at)
    grid_sha = _sha256(payload["grid_contract_sha256"], "grid_contract_sha256")
    grid_contract_path = Path(grid_contract_path)
    if grid_contract_path.name != _basename(
        payload["grid_contract_file"], "grid_contract_file"
    ):
        raise ControlledExperimentError(
            "Grid contract filename does not match receipt."
        )
    grid_contract = _load_grid_contract(
        grid_contract_path,
        expected_sha256=grid_sha,
        expected_crs=str(payload["target_crs"]),
    )
    membership = Path(membership_path)
    if membership.name != payload["membership_file"]:
        raise ControlledExperimentError(
            "Holdout membership filename does not match receipt."
        )
    memberships, membership_sha256 = _read_frozen_membership(
        membership,
        grid_contract=grid_contract,
    )
    if membership_sha256 != _sha256(payload["membership_sha256"], "membership_sha256"):
        raise ControlledExperimentError(
            "Holdout membership SHA-256 does not match receipt."
        )
    if len(memberships) != _positive_int(payload["cell_count"], "cell_count"):
        raise ControlledExperimentError("Holdout membership cell count changed.")
    receipt_area = _positive_float(payload["cell_area_m2"], "cell_area_m2")
    if not math.isclose(
        grid_contract.cell_area_m2,
        receipt_area,
        rel_tol=0,
        abs_tol=1e-9,
    ):
        raise ControlledExperimentError("Holdout cell area does not match receipt.")
    derived = _derive_memberships(
        pd.DataFrame(
            [
                {
                    column: membership_item.to_dict()[column]
                    for column in CELL_GRID_COLUMNS
                }
                for membership_item in memberships
            ],
            columns=CELL_GRID_COLUMNS,
        ),
        group_geometries,
    )
    if derived != memberships:
        raise ControlledExperimentError(
            "Frozen cell membership no longer matches coordinates and holdout polygons."
        )
    derived_train_ids = sorted(
        {item.spatial_group_id for item in memberships if item.split == "train"}
    )
    derived_calibration_ids = sorted(
        {item.spatial_group_id for item in memberships if item.split == "calibration"}
    )
    derived_final_holdout_ids = sorted(
        {item.spatial_group_id for item in memberships if item.split == "final_holdout"}
    )
    if (
        derived_train_ids != payload["training_ids"]
        or derived_calibration_ids != payload["calibration_ids"]
        or derived_final_holdout_ids != payload["final_holdout_ids"]
    ):
        raise ControlledExperimentError(
            "Frozen membership group IDs do not match receipt."
        )
    expected_partitions = {
        split: _canonical_sha256(
            [item.to_dict() for item in memberships if item.split == split]
        )
        for split in ("train", "calibration", "final_holdout")
    }
    if payload["partition_sha256_by_split"] != expected_partitions:
        raise ControlledExperimentError(
            "Frozen partition membership hashes do not match the receipt."
        )
    return VerifiedSpatialHoldout(
        dict(payload),
        memberships,
        _verified_receipt_sha256=_canonical_sha256(payload),
        _verification_marker=_VERIFIED_HOLDOUT_MARKER,
    )


def _validate_reviewer_calibration_release_lineage(
    *,
    release_package_path: Path,
    release: Mapping[str, object],
    reviewer: Any,
    calibration_attempt: str,
) -> dict[str, object]:
    """Bind one reviewer-calibration receipt to the exact frozen release rows.

    Query identifiers alone are not sufficient lineage: the same identifiers
    can be attached to substituted geometry, grids, source registries, or
    timestamps.  Formal qualification therefore requires the reviewer receipt
    to have been built from the exact immutable attempt CSV in the validated
    calibration release, then rechecks every per-query lineage value.
    """

    attempt_files = {
        "initial": CALIBRATION_QUERIES_NAME,
        "fresh_retest": FRESH_RETEST_QUERIES_NAME,
    }
    membership_file = attempt_files.get(calibration_attempt)
    if membership_file is None:
        raise ControlledExperimentError(
            "calibration_attempt must be initial or fresh_retest."
        )
    membership_path = release_package_path / membership_file
    membership, membership_file_sha = _read_csv_snapshot(
        membership_path,
        "approved calibration query manifest",
    )
    _require_columns(
        membership,
        (
            "query_region_id",
            "grid_contract_sha256",
            "source_registry_sha256",
            "source_timestamp",
        ),
        "approved calibration query manifest",
    )
    membership = membership.fillna("")
    if membership["query_region_id"].astype(str).duplicated().any():
        raise ControlledExperimentError(
            "Approved calibration query manifest contains duplicate query IDs."
        )

    inventory = release.get("artifacts")
    if not isinstance(inventory, Sequence) or isinstance(
        inventory, (str, bytes, bytearray)
    ):
        raise ControlledExperimentError(
            "Calibration release artifact inventory is missing."
        )
    inventory_records = [
        item
        for item in inventory
        if isinstance(item, Mapping) and item.get("package_path") == membership_file
    ]
    if len(inventory_records) != 1:
        raise ControlledExperimentError(
            "Calibration release does not bind the selected query manifest exactly once."
        )
    inventory_sha = _sha256(
        inventory_records[0].get("sha256"),
        "approved calibration query manifest inventory SHA-256",
    )
    if inventory_sha != membership_file_sha:
        raise ControlledExperimentError(
            "Approved calibration query manifest changed after release validation."
        )

    selection = release.get("selection_contract")
    if not isinstance(selection, Mapping):
        raise ControlledExperimentError(
            "Calibration release selection contract is missing."
        )
    attempt_key = {
        "initial": "calibration_query_ids",
        "fresh_retest": "fresh_retest_query_ids",
    }[calibration_attempt]
    expected_query_ids = tuple(
        sorted(
            _text(value, "calibration query id")
            for value in selection.get(attempt_key, [])
        )
    )
    observed_query_ids = tuple(
        sorted(
            _text(value, "approved calibration query id")
            for value in membership["query_region_id"].astype(str)
        )
    )
    if observed_query_ids != expected_query_ids:
        raise ControlledExperimentError(
            "Approved calibration query manifest membership differs from the release."
        )
    if tuple(sorted(reviewer.query_region_ids)) != expected_query_ids:
        raise ControlledExperimentError(
            "Reviewer calibration queries do not match the approved release attempt."
        )
    if reviewer.query_manifest_sha256 != membership_file_sha:
        raise ControlledExperimentError(
            "Reviewer calibration query manifest is not the exact frozen release artifact."
        )

    rows_by_query = {
        _text(raw["query_region_id"], "approved calibration query id"): raw
        for raw in membership.to_dict("records")
    }
    expected_grid = tuple(
        sorted(
            (
                query_id,
                _sha256(raw["grid_contract_sha256"], f"{query_id} grid contract"),
            )
            for query_id, raw in rows_by_query.items()
        )
    )
    expected_source = tuple(
        sorted(
            (
                query_id,
                _sha256(raw["source_registry_sha256"], f"{query_id} source registry"),
            )
            for query_id, raw in rows_by_query.items()
        )
    )
    expected_timestamps = tuple(
        sorted(
            (
                query_id,
                _format_utc(
                    _timestamp(raw["source_timestamp"], f"{query_id} source timestamp")
                ),
            )
            for query_id, raw in rows_by_query.items()
        )
    )
    if tuple(sorted(reviewer.grid_contract_sha256_by_query)) != expected_grid:
        raise ControlledExperimentError(
            "Reviewer calibration grid lineage differs from the approved release."
        )
    if tuple(sorted(reviewer.source_registry_sha256_by_query)) != expected_source:
        raise ControlledExperimentError(
            "Reviewer calibration source-registry lineage differs from the approved release."
        )
    if tuple(sorted(reviewer.source_timestamp_by_query)) != expected_timestamps:
        raise ControlledExperimentError(
            "Reviewer calibration source timestamps differ from the approved release."
        )
    return {
        "approved_query_manifest_file": membership_file,
        "approved_query_manifest_file_sha256": membership_file_sha,
        "reviewer_query_manifest_sha256": reviewer.query_manifest_sha256,
        "grid_contract_sha256_by_query": dict(expected_grid),
        "source_registry_sha256_by_query": dict(expected_source),
        "source_timestamp_by_query": dict(expected_timestamps),
    }


def _reviewer_cell_decision_lineage(
    paths_by_reviewer: Mapping[str, str | Path],
    *,
    reviewer: Any,
    expected_query_ids: Sequence[str],
) -> dict[str, object]:
    """Reopen exact reviewer cells and bind every disagreement to their bytes."""

    expected_reviewers = tuple(sorted(reviewer.reviewer_ids))
    supplied_reviewers = tuple(sorted(paths_by_reviewer))
    if supplied_reviewers != expected_reviewers:
        raise ControlledExperimentError(
            "Reviewer-cell paths must exactly cover the calibrated reviewers."
        )
    receipt_hashes = dict(reviewer.reviewer_cell_sha256_by_reviewer)
    if set(receipt_hashes) != set(expected_reviewers):
        raise ControlledExperimentError(
            "Reviewer calibration receipt has incomplete reviewer-cell hashes."
        )
    expected_queries = tuple(
        sorted(_text(value, "query_region_id") for value in expected_query_ids)
    )
    if len(set(expected_queries)) != len(expected_queries):
        raise ControlledExperimentError("Reviewer decision query IDs are duplicated.")

    files: dict[str, str] = {}
    file_hashes: dict[str, str] = {}
    canonical_rows: dict[str, dict[str, list[dict[str, object]]]] = {
        query_id: {} for query_id in expected_queries
    }
    decision_hashes: dict[str, dict[str, str]] = {
        query_id: {} for query_id in expected_queries
    }
    cell_ids_by_query: dict[str, set[str]] = {}
    for reviewer_id in expected_reviewers:
        path = Path(paths_by_reviewer[reviewer_id])
        frame, file_sha = _read_csv_snapshot(path, f"{reviewer_id} reviewer cells")
        if file_sha != receipt_hashes[reviewer_id]:
            raise ControlledExperimentError(
                f"Reviewer-cell checksum differs from calibration receipt for {reviewer_id}."
            )
        _require_columns(
            frame,
            ("reviewer_id", "query_region_id", "cell_id", "label_code"),
            f"{reviewer_id} reviewer cells",
        )
        frame = frame.fillna("")
        if set(frame["reviewer_id"].astype(str)) != {reviewer_id}:
            raise ControlledExperimentError(
                f"Reviewer-cell evidence contains another identity for {reviewer_id}."
            )
        observed_queries = {
            _text(value, f"{reviewer_id} query_region_id")
            for value in frame["query_region_id"].astype(str)
        }
        if observed_queries != set(expected_queries):
            raise ControlledExperimentError(
                f"Reviewer-cell evidence does not exactly cover the approved attempt for {reviewer_id}."
            )
        if frame[["query_region_id", "cell_id"]].astype(str).duplicated().any():
            raise ControlledExperimentError(
                f"Reviewer-cell evidence contains duplicate cells for {reviewer_id}."
            )
        files[reviewer_id] = path.name
        file_hashes[reviewer_id] = file_sha
        for query_id in expected_queries:
            query = frame.loc[
                frame["query_region_id"].astype(str).eq(query_id),
                ["cell_id", "label_code"],
            ].copy()
            if query.empty:
                raise ControlledExperimentError(
                    f"Reviewer-cell evidence has no rows for {reviewer_id}/{query_id}."
                )
            normalized_rows: list[dict[str, object]] = []
            for raw in query.to_dict("records"):
                cell_id = _text(raw["cell_id"], f"{reviewer_id} cell_id")
                label_code = _nonnegative_int(
                    raw["label_code"], f"{reviewer_id}/{cell_id} label_code"
                )
                if label_code not in {0, 1, 2, 3, 4, 255}:
                    raise ControlledExperimentError(
                        f"Reviewer-cell label is outside flood_label_v1 for {reviewer_id}/{cell_id}."
                    )
                normalized_rows.append({"cell_id": cell_id, "label_code": label_code})
            normalized_rows.sort(key=lambda row: str(row["cell_id"]))
            observed_cells = {str(row["cell_id"]) for row in normalized_rows}
            if query_id in cell_ids_by_query:
                if observed_cells != cell_ids_by_query[query_id]:
                    raise ControlledExperimentError(
                        f"Reviewer-cell coverage differs between reviewers for {query_id}."
                    )
            else:
                cell_ids_by_query[query_id] = observed_cells
            canonical_rows[query_id][reviewer_id] = normalized_rows
            decision_hashes[query_id][reviewer_id] = _canonical_sha256(normalized_rows)

    disagreement_query_ids = tuple(
        query_id
        for query_id in expected_queries
        if len(
            {
                _canonical_sha256(canonical_rows[query_id][reviewer_id])
                for reviewer_id in expected_reviewers
            }
        )
        > 1
    )
    return {
        "reviewer_cell_files_by_reviewer": files,
        "reviewer_cell_sha256_by_reviewer": file_hashes,
        "reviewer_decision_sha256_by_query": decision_hashes,
        "disagreement_query_ids": disagreement_query_ids,
    }


def write_signed_reviewer_qualification_receipt(
    *,
    acquisition: AcquisitionGateAssessment,
    calibration_release_package_path: str | Path,
    reviewer_calibration_receipt_path: str | Path,
    reviewer_cell_paths_by_reviewer: Mapping[str, str | Path],
    calibration_attempt: str,
    adjudication_evidence_path: str | Path,
    error_strata_path: str | Path,
    qualified_at_utc: datetime,
    expires_at_utc: datetime,
    reviewer_signing_key_id: str,
    reviewer_signing_key: bytes,
    adjudicator_signing_key_id: str,
    adjudicator_signing_key: bytes,
    output_path: str | Path,
) -> dict[str, object]:
    """Dual-sign one event-bound calibration and adjudication qualification."""

    _verify_acquisition_assessment(acquisition)
    if (
        not acquisition.ready
        or acquisition.authority_receipt_sha256 is None
        or acquisition.authority_issued_at_utc is None
        or acquisition.authority_signing_key_id is None
    ):
        raise ControlledExperimentError(
            "Ready acquisition authority is required for reviewer qualification."
        )
    try:
        release = validate_calibration_release_package(calibration_release_package_path)
    except (CalibrationReleaseError, OSError) as exc:
        raise ControlledExperimentError(
            "Calibration release package is invalid."
        ) from exc
    release_package = Path(calibration_release_package_path)
    release_path = release_package / "calibration_release_receipt.json"
    release_file_sha = _file_sha256(release_path)
    reviewer, reviewer_file_sha = _load_reviewer_calibration_snapshot(
        Path(reviewer_calibration_receipt_path)
    )
    attempt = _text(calibration_attempt, "calibration_attempt")
    attempt_key = {
        "initial": "calibration_query_ids",
        "fresh_retest": "fresh_retest_query_ids",
    }.get(attempt)
    if attempt_key is None:
        raise ControlledExperimentError(
            "calibration_attempt must be initial or fresh_retest."
        )
    selection = release.get("selection_contract")
    if not isinstance(selection, Mapping):
        raise ControlledExperimentError(
            "Calibration release selection contract is missing."
        )
    calibration_query_ids = tuple(
        _text(value, "calibration query id")
        for value in selection.get("calibration_query_ids", [])
    )
    fresh_retest_query_ids = tuple(
        _text(value, "fresh retest query id")
        for value in selection.get("fresh_retest_query_ids", [])
    )
    expected_attempt_ids = (
        calibration_query_ids if attempt == "initial" else fresh_retest_query_ids
    )
    release_lineage = _validate_reviewer_calibration_release_lineage(
        release_package_path=release_package,
        release=release,
        reviewer=reviewer,
        calibration_attempt=attempt,
    )
    reviewer_decisions = _reviewer_cell_decision_lineage(
        reviewer_cell_paths_by_reviewer,
        reviewer=reviewer,
        expected_query_ids=expected_attempt_ids,
    )
    adjudication_path = Path(adjudication_evidence_path)
    adjudication_bytes = _read_stable_bytes(adjudication_path, "adjudication evidence")
    adjudication_file_sha = hashlib.sha256(adjudication_bytes).hexdigest()
    adjudication = _json_object_bytes(adjudication_bytes, "adjudication evidence")
    _validate_adjudication_evidence(
        adjudication,
        acquisition=acquisition,
        reviewer_ids=reviewer.reviewer_ids,
        calibration_release_id=str(release["release_id"]),
        reviewer_not_before=reviewer.formal_review_not_before_utc,
        reviewer_completed_at=reviewer.calibration_completed_at_utc,
        expected_query_ids=expected_attempt_ids,
        expected_reviewer_cell_sha256_by_reviewer=reviewer_decisions[
            "reviewer_cell_sha256_by_reviewer"
        ],
        expected_reviewer_decision_sha256_by_query=reviewer_decisions[
            "reviewer_decision_sha256_by_query"
        ],
        expected_disagreement_query_ids=reviewer_decisions["disagreement_query_ids"],
    )
    error_path = Path(error_strata_path)
    error_frame, error_file_sha = _read_csv_snapshot(error_path, "error strata")
    _validated_error_strata(error_frame)
    qualified = _timestamp(_format_utc(qualified_at_utc), "qualified_at_utc")
    expires = _timestamp(_format_utc(expires_at_utc), "expires_at_utc")
    adjudication_completed = _timestamp(
        adjudication["completed_at_utc"], "adjudication completed_at_utc"
    )
    if (
        qualified < acquisition.authority_issued_at_utc
        or qualified < adjudication_completed
        or expires <= qualified
    ):
        raise ControlledExperimentError(
            "Reviewer qualification chronology or expiry is invalid."
        )
    if (
        reviewer_signing_key_id == acquisition.authority_signing_key_id
        or adjudicator_signing_key_id == acquisition.authority_signing_key_id
    ):
        raise ControlledExperimentError(
            "Licensing, reviewer, and adjudicator signing identities must differ."
        )
    payload: dict[str, object] = {
        "artifact_schema": REVIEWER_QUALIFICATION_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": (acquisition.authority_receipt_sha256),
        "acquisition_authority_signing_key_id": (acquisition.authority_signing_key_id),
        "reference_mask_sha256": acquisition.reference_mask_sha256,
        "event_id": _text(release["event_id"], "calibration release event_id"),
        "calibration_release_id": _text(
            release["release_id"], "calibration release_id"
        ),
        "calibration_release_receipt_sha256": _sha256(
            release["receipt_sha256"], "calibration release receipt_sha256"
        ),
        "calibration_release_file": release_path.name,
        "calibration_release_file_sha256": release_file_sha,
        "reference_authority_approval_manifest_sha256": _sha256(
            release["authority_approval"]["manifest_sha256"],
            "reference authority approval manifest_sha256",
        ),
        "calibration_attempt": attempt,
        "calibration_query_ids": list(calibration_query_ids),
        "fresh_retest_query_ids": list(fresh_retest_query_ids),
        **release_lineage,
        "reviewer_calibration_file": Path(reviewer_calibration_receipt_path).name,
        "reviewer_calibration_file_sha256": reviewer_file_sha,
        "reviewer_calibration_receipt_sha256": reviewer.receipt_sha256,
        "reviewer_ids": list(reviewer.reviewer_ids),
        "reviewer_cell_files_by_reviewer": reviewer_decisions[
            "reviewer_cell_files_by_reviewer"
        ],
        "reviewer_cell_sha256_by_reviewer": reviewer_decisions[
            "reviewer_cell_sha256_by_reviewer"
        ],
        "reviewer_decision_manifest_sha256": _canonical_sha256(
            reviewer_decisions["reviewer_decision_sha256_by_query"]
        ),
        "protocol_version": reviewer.protocol_version,
        "taxonomy_version": reviewer.taxonomy_version,
        "formal_review_not_before_utc": _format_utc(
            reviewer.formal_review_not_before_utc
        ),
        "adjudicator_id": adjudication["adjudicator_id"],
        "adjudication_evidence_file": adjudication_path.name,
        "adjudication_evidence_sha256": adjudication_file_sha,
        "adjudication_resolution_manifest_sha256": _canonical_sha256(
            adjudication["disagreement_resolutions"]
        ),
        "disagreement_count": adjudication["disagreement_count"],
        "resolved_disagreement_count": adjudication["resolved_disagreement_count"],
        "unresolved_disagreement_count": 0,
        "error_strata_file": error_path.name,
        "error_strata_file_sha256": error_file_sha,
        "qualified_at_utc": _format_utc(qualified),
        "expires_at_utc": _format_utc(expires),
        "signing_roles": [SIGNING_ROLES["reviewer"], SIGNING_ROLES["adjudicator"]],
        "qualification_status": "qualified_for_controlled_reference_derivation",
        "processing_allowed": True,
        "can_feed_decision_layer": False,
        "official_warning": False,
    }
    sealed = _seal_dual_signed_payload(
        payload,
        reviewer_signing_key_id=reviewer_signing_key_id,
        reviewer_signing_key=reviewer_signing_key,
        adjudicator_signing_key_id=adjudicator_signing_key_id,
        adjudicator_signing_key=adjudicator_signing_key,
    )
    _write_immutable_json(sealed, Path(output_path), "Reviewer qualification receipt")
    return sealed


def load_signed_reviewer_qualification_receipt(
    receipt_path: str | Path,
    *,
    acquisition: AcquisitionGateAssessment,
    signing_keys: Mapping[str, bytes],
    verified_at_utc: datetime | None = None,
) -> VerifiedReviewerQualification:
    """Verify a dual-signed reviewer qualification and its event lineage."""

    _verify_acquisition_assessment(acquisition)
    path = Path(receipt_path)
    content = _read_stable_bytes(path, "reviewer qualification receipt")
    file_sha = hashlib.sha256(content).hexdigest()
    payload = _json_object_bytes(content, "reviewer qualification receipt")
    required = {
        "artifact_schema",
        "experiment_id",
        "study_area",
        "acquisition_manifest_sha256",
        "acquisition_authority_receipt_sha256",
        "acquisition_authority_signing_key_id",
        "reference_mask_sha256",
        "event_id",
        "calibration_release_id",
        "calibration_release_receipt_sha256",
        "calibration_release_file",
        "calibration_release_file_sha256",
        "reference_authority_approval_manifest_sha256",
        "calibration_attempt",
        "calibration_query_ids",
        "fresh_retest_query_ids",
        "approved_query_manifest_file",
        "approved_query_manifest_file_sha256",
        "reviewer_query_manifest_sha256",
        "grid_contract_sha256_by_query",
        "source_registry_sha256_by_query",
        "source_timestamp_by_query",
        "reviewer_calibration_file",
        "reviewer_calibration_file_sha256",
        "reviewer_calibration_receipt_sha256",
        "reviewer_ids",
        "reviewer_cell_files_by_reviewer",
        "reviewer_cell_sha256_by_reviewer",
        "reviewer_decision_manifest_sha256",
        "protocol_version",
        "taxonomy_version",
        "formal_review_not_before_utc",
        "adjudicator_id",
        "adjudication_evidence_file",
        "adjudication_evidence_sha256",
        "adjudication_resolution_manifest_sha256",
        "disagreement_count",
        "resolved_disagreement_count",
        "unresolved_disagreement_count",
        "error_strata_file",
        "error_strata_file_sha256",
        "qualified_at_utc",
        "expires_at_utc",
        "signing_roles",
        "qualification_status",
        "processing_allowed",
        "can_feed_decision_layer",
        "official_warning",
        "reviewer_signing_key_id",
        "adjudicator_signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "reviewer_signature",
        "adjudicator_signature",
    }
    _exact_keys(payload, required, "reviewer qualification receipt")
    if payload["artifact_schema"] != REVIEWER_QUALIFICATION_SCHEMA:
        raise ControlledExperimentError(
            "Reviewer qualification receipt schema is unsupported."
        )
    _verify_dual_signed_payload(payload, signing_keys, "reviewer qualification")
    _verify_dual_self_hash(payload, "reviewer qualification")
    if (
        not acquisition.ready
        or acquisition.authority_receipt_sha256 is None
        or acquisition.authority_signing_key_id is None
    ):
        raise ControlledExperimentError(
            "Reviewer qualification requires ready acquisition authority."
        )
    expected = {
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": (acquisition.authority_receipt_sha256),
        "acquisition_authority_signing_key_id": (acquisition.authority_signing_key_id),
        "reference_mask_sha256": acquisition.reference_mask_sha256,
    }
    for field, value in expected.items():
        if payload[field] != value:
            raise ControlledExperimentError(
                f"Reviewer qualification {field} was substituted."
            )
    if payload["signing_roles"] != [
        SIGNING_ROLES["reviewer"],
        SIGNING_ROLES["adjudicator"],
    ]:
        raise ControlledExperimentError(
            "Reviewer qualification signing roles are invalid."
        )
    reviewer_ids = tuple(
        _text(value, "reviewer_id") for value in payload["reviewer_ids"]
    )
    if len(reviewer_ids) < 2 or len(set(reviewer_ids)) != len(reviewer_ids):
        raise ControlledExperimentError(
            "Reviewer qualification requires distinct reviewers."
        )
    reviewer_cell_files = payload["reviewer_cell_files_by_reviewer"]
    reviewer_cell_hashes = payload["reviewer_cell_sha256_by_reviewer"]
    if (
        not isinstance(reviewer_cell_files, Mapping)
        or not isinstance(reviewer_cell_hashes, Mapping)
        or set(reviewer_cell_files) != set(reviewer_ids)
        or set(reviewer_cell_hashes) != set(reviewer_ids)
    ):
        raise ControlledExperimentError(
            "Reviewer qualification reviewer-cell lineage is incomplete."
        )
    for reviewer_id in reviewer_ids:
        _basename(
            reviewer_cell_files[reviewer_id],
            f"{reviewer_id} reviewer-cell file",
        )
        _sha256(
            reviewer_cell_hashes[reviewer_id],
            f"{reviewer_id} reviewer-cell SHA-256",
        )
    _sha256(
        payload["reviewer_decision_manifest_sha256"],
        "reviewer_decision_manifest_sha256",
    )
    adjudicator_id = _text(payload["adjudicator_id"], "adjudicator_id")
    if adjudicator_id in reviewer_ids:
        raise ControlledExperimentError(
            "Reviewer qualification adjudicator must be independent."
        )
    calibration_ids = tuple(
        _text(value, "calibration_query_id")
        for value in payload["calibration_query_ids"]
    )
    retest_ids = tuple(
        _text(value, "fresh_retest_query_id")
        for value in payload["fresh_retest_query_ids"]
    )
    if (
        len(calibration_ids) != 12
        or len(retest_ids) != 12
        or set(calibration_ids).intersection(retest_ids)
    ):
        raise ControlledExperimentError(
            "Reviewer qualification must bind disjoint 12/12 calibration membership."
        )
    attempt = payload["calibration_attempt"]
    if attempt not in {"initial", "fresh_retest"}:
        raise ControlledExperimentError(
            "Reviewer qualification calibration attempt is invalid."
        )
    attempt_ids = calibration_ids if attempt == "initial" else retest_ids
    expected_manifest_file = (
        CALIBRATION_QUERIES_NAME if attempt == "initial" else FRESH_RETEST_QUERIES_NAME
    )
    if payload["approved_query_manifest_file"] != expected_manifest_file:
        raise ControlledExperimentError(
            "Reviewer qualification approved query-manifest file is invalid."
        )
    approved_manifest_sha = _sha256(
        payload["approved_query_manifest_file_sha256"],
        "approved_query_manifest_file_sha256",
    )
    reviewer_manifest_sha = _sha256(
        payload["reviewer_query_manifest_sha256"],
        "reviewer_query_manifest_sha256",
    )
    if reviewer_manifest_sha != approved_manifest_sha:
        raise ControlledExperimentError(
            "Reviewer qualification is not bound to the exact frozen query manifest."
        )

    lineage_by_field: dict[str, tuple[tuple[str, str], ...]] = {}
    expected_lineage_ids = set(attempt_ids)
    if len(expected_lineage_ids) != len(attempt_ids):
        raise ControlledExperimentError(
            "Reviewer qualification attempt membership contains duplicate query IDs."
        )
    for field in (
        "grid_contract_sha256_by_query",
        "source_registry_sha256_by_query",
        "source_timestamp_by_query",
    ):
        raw_mapping = payload[field]
        if not isinstance(raw_mapping, Mapping):
            raise ControlledExperimentError(
                f"Reviewer qualification {field} must be an object."
            )
        normalized: list[tuple[str, str]] = []
        for raw_query_id, raw_value in raw_mapping.items():
            query_id = _text(raw_query_id, f"{field} query ID")
            if field == "source_timestamp_by_query":
                value = _format_utc(
                    _timestamp(raw_value, f"{query_id} source timestamp")
                )
            else:
                value = _sha256(raw_value, f"{query_id} {field}")
            normalized.append((query_id, value))
        normalized_tuple = tuple(sorted(normalized))
        if {query_id for query_id, _value in normalized_tuple} != expected_lineage_ids:
            raise ControlledExperimentError(
                f"Reviewer qualification {field} does not exactly cover the approved attempt."
            )
        lineage_by_field[field] = normalized_tuple
    if (
        _nonnegative_int(payload["disagreement_count"], "disagreement_count")
        != _nonnegative_int(
            payload["resolved_disagreement_count"],
            "resolved_disagreement_count",
        )
        or _nonnegative_int(
            payload["unresolved_disagreement_count"],
            "unresolved_disagreement_count",
        )
        != 0
    ):
        raise ControlledExperimentError(
            "Reviewer qualification has unresolved disagreements."
        )
    if (
        payload["qualification_status"]
        != "qualified_for_controlled_reference_derivation"
        or payload["processing_allowed"] is not True
        or payload["can_feed_decision_layer"] is not False
        or payload["official_warning"] is not False
    ):
        raise ControlledExperimentError(
            "Reviewer qualification has unsafe status fields."
        )
    formal_not_before = _timestamp(
        payload["formal_review_not_before_utc"],
        "reviewer formal_review_not_before_utc",
    )
    qualified = _timestamp(payload["qualified_at_utc"], "qualified_at_utc")
    expires = _timestamp(payload["expires_at_utc"], "expires_at_utc")
    verified = _timestamp(
        _format_utc(verified_at_utc or datetime.now(UTC)), "verified_at_utc"
    )
    if (
        qualified < formal_not_before
        or expires <= qualified
        or not qualified <= verified <= expires
    ):
        raise ControlledExperimentError(
            "Reviewer qualification is not currently valid."
        )
    reviewer_key_id = _text(
        payload["reviewer_signing_key_id"], "reviewer_signing_key_id"
    )
    adjudicator_key_id = _text(
        payload["adjudicator_signing_key_id"], "adjudicator_signing_key_id"
    )
    if acquisition.authority_signing_key_id in {
        reviewer_key_id,
        adjudicator_key_id,
    }:
        raise ControlledExperimentError(
            "Licensing, reviewer, and adjudicator signing identities must differ."
        )
    _require_distinct_trusted_credentials(
        signing_keys,
        [
            acquisition.authority_signing_key_id,
            reviewer_key_id,
            adjudicator_key_id,
        ],
        label="acquisition and reviewer qualification roles",
    )
    for field in (
        "calibration_release_receipt_sha256",
        "calibration_release_file_sha256",
        "reference_authority_approval_manifest_sha256",
        "approved_query_manifest_file_sha256",
        "reviewer_query_manifest_sha256",
        "reviewer_calibration_file_sha256",
        "reviewer_calibration_receipt_sha256",
        "adjudication_evidence_sha256",
        "adjudication_resolution_manifest_sha256",
        "error_strata_file_sha256",
    ):
        _sha256(payload[field], field)
    for field in (
        "calibration_release_file",
        "approved_query_manifest_file",
        "reviewer_calibration_file",
        "adjudication_evidence_file",
        "error_strata_file",
    ):
        _basename(payload[field], field)
    _reject_private_paths(payload)
    return VerifiedReviewerQualification(
        experiment_id=acquisition.experiment_id,
        study_area=acquisition.study_area,
        acquisition_manifest_sha256=acquisition.manifest_sha256,
        reference_mask_sha256=acquisition.reference_mask_sha256,
        calibration_release_receipt_sha256=str(
            payload["calibration_release_receipt_sha256"]
        ),
        calibration_release_file_sha256=str(payload["calibration_release_file_sha256"]),
        calibration_receipt_sha256=str(payload["reviewer_calibration_receipt_sha256"]),
        calibration_file_sha256=str(payload["reviewer_calibration_file_sha256"]),
        approved_query_manifest_file_sha256=approved_manifest_sha,
        reviewer_query_manifest_sha256=reviewer_manifest_sha,
        grid_contract_sha256_by_query=lineage_by_field["grid_contract_sha256_by_query"],
        source_registry_sha256_by_query=lineage_by_field[
            "source_registry_sha256_by_query"
        ],
        source_timestamp_by_query=lineage_by_field["source_timestamp_by_query"],
        calibration_query_ids=calibration_ids,
        fresh_retest_query_ids=retest_ids,
        reviewer_ids=reviewer_ids,
        adjudicator_id=adjudicator_id,
        disagreement_evidence_sha256=str(payload["adjudication_evidence_sha256"]),
        disagreement_resolution_manifest_sha256=str(
            payload["adjudication_resolution_manifest_sha256"]
        ),
        error_strata_file_sha256=str(payload["error_strata_file_sha256"]),
        formal_review_not_before_utc=formal_not_before,
        qualified_at_utc=qualified,
        expires_at_utc=expires,
        manifest_sha256=str(payload["manifest_sha256"]),
        receipt_file_sha256=file_sha,
        reviewer_signing_key_id=reviewer_key_id,
        adjudicator_signing_key_id=adjudicator_key_id,
        _verification_marker=_VERIFIED_REVIEWER_QUALIFICATION_MARKER,
    )


def _validate_adjudication_evidence(
    payload: Mapping[str, object],
    *,
    acquisition: AcquisitionGateAssessment,
    reviewer_ids: Sequence[str],
    calibration_release_id: str,
    reviewer_not_before: datetime,
    reviewer_completed_at: datetime,
    expected_query_ids: Sequence[str],
    expected_reviewer_cell_sha256_by_reviewer: Mapping[str, str],
    expected_reviewer_decision_sha256_by_query: Mapping[str, Mapping[str, str]],
    expected_disagreement_query_ids: Sequence[str],
) -> None:
    required = {
        "artifact_schema",
        "experiment_id",
        "study_area",
        "calibration_release_id",
        "reference_mask_sha256",
        "reviewer_ids",
        "reviewer_cell_sha256_by_reviewer",
        "adjudicator_id",
        "formal_review_started_at_utc",
        "completed_at_utc",
        "disagreement_count",
        "resolved_disagreement_count",
        "unresolved_disagreement_count",
        "disagreement_resolutions",
        "resolution_method",
        "assumptions",
    }
    _exact_keys(payload, required, "adjudication evidence")
    if payload["artifact_schema"] != "floodguard.controlled_adjudication_evidence.v3":
        raise ControlledExperimentError("Adjudication evidence schema is unsupported.")
    if (
        payload["experiment_id"] != acquisition.experiment_id
        or payload["study_area"] != acquisition.study_area
        or payload["calibration_release_id"] != calibration_release_id
        or payload["reference_mask_sha256"] != acquisition.reference_mask_sha256
    ):
        raise ControlledExperimentError("Adjudication evidence scope was substituted.")
    supplied_reviewers = tuple(
        _text(value, "adjudication reviewer_id") for value in payload["reviewer_ids"]
    )
    if set(supplied_reviewers) != set(reviewer_ids) or len(supplied_reviewers) != len(
        reviewer_ids
    ):
        raise ControlledExperimentError(
            "Adjudication evidence reviewer identities do not match calibration."
        )
    supplied_cell_hashes = payload["reviewer_cell_sha256_by_reviewer"]
    if not isinstance(supplied_cell_hashes, Mapping) or set(
        supplied_cell_hashes
    ) != set(supplied_reviewers):
        raise ControlledExperimentError(
            "Adjudication evidence reviewer-cell hashes are incomplete."
        )
    if set(expected_reviewer_cell_sha256_by_reviewer) != set(supplied_reviewers):
        raise ControlledExperimentError("Expected reviewer-cell hashes are incomplete.")
    normalized_cell_hashes = {
        reviewer_id: _sha256(
            supplied_cell_hashes[reviewer_id],
            f"{reviewer_id} reviewer-cell SHA-256",
        )
        for reviewer_id in supplied_reviewers
    }
    expected_cell_hashes = {
        reviewer_id: _sha256(
            expected_reviewer_cell_sha256_by_reviewer[reviewer_id],
            f"expected {reviewer_id} reviewer-cell SHA-256",
        )
        for reviewer_id in supplied_reviewers
    }
    if normalized_cell_hashes != expected_cell_hashes:
        raise ControlledExperimentError(
            "Adjudication evidence reviewer-cell hashes were substituted."
        )
    adjudicator = _text(payload["adjudicator_id"], "adjudicator_id")
    if adjudicator in supplied_reviewers:
        raise ControlledExperimentError("Adjudicator must be independent of reviewers.")
    started = _timestamp(
        payload["formal_review_started_at_utc"], "formal_review_started_at_utc"
    )
    completed = _timestamp(payload["completed_at_utc"], "completed_at_utc")
    if (
        started < reviewer_not_before
        or started < reviewer_completed_at
        or completed < started
    ):
        raise ControlledExperimentError("Adjudication chronology is invalid.")
    disagreements = _nonnegative_int(
        payload["disagreement_count"], "disagreement_count"
    )
    resolved = _nonnegative_int(
        payload["resolved_disagreement_count"], "resolved_disagreement_count"
    )
    unresolved = _nonnegative_int(
        payload["unresolved_disagreement_count"], "unresolved_disagreement_count"
    )
    if disagreements != resolved or unresolved != 0:
        raise ControlledExperimentError(
            "Adjudication evidence has unresolved disagreements."
        )
    expected_ids = set(expected_query_ids)
    expected_disagreement_ids = set(expected_disagreement_query_ids)
    if not expected_disagreement_ids.issubset(expected_ids):
        raise ControlledExperimentError(
            "Expected adjudication disagreements are outside the approved query set."
        )
    if disagreements != len(expected_disagreement_ids):
        raise ControlledExperimentError(
            "Adjudication disagreement_count does not match exact reviewer-cell evidence."
        )
    if set(expected_reviewer_decision_sha256_by_query) != expected_ids:
        raise ControlledExperimentError(
            "Reviewer decision hashes do not exactly cover the approved query set."
        )
    for query_id, reviewer_hashes in expected_reviewer_decision_sha256_by_query.items():
        if set(reviewer_hashes) != set(supplied_reviewers):
            raise ControlledExperimentError(
                f"Reviewer decision hashes are incomplete for {query_id}."
            )
    resolution_rows = payload["disagreement_resolutions"]
    if not isinstance(resolution_rows, Sequence) or isinstance(
        resolution_rows, (str, bytes, bytearray)
    ):
        raise ControlledExperimentError(
            "Adjudication disagreement_resolutions must be an array."
        )
    if len(resolution_rows) != disagreements:
        raise ControlledExperimentError(
            "Adjudication resolution records do not match disagreement_count."
        )
    disagreement_ids: set[str] = set()
    resolved_query_ids: set[str] = set()
    for index, row in enumerate(resolution_rows):
        if not isinstance(row, Mapping):
            raise ControlledExperimentError(
                "Each adjudication resolution must be an object."
            )
        _exact_keys(
            row,
            {
                "disagreement_id",
                "query_region_id",
                "reviewer_decision_sha256_by_reviewer",
                "adjudication_outcome",
                "resolution_reason",
            },
            f"adjudication resolution {index}",
        )
        disagreement_id = _text(row["disagreement_id"], "disagreement_id")
        if disagreement_id in disagreement_ids:
            raise ControlledExperimentError(
                "Adjudication disagreement IDs must be unique."
            )
        disagreement_ids.add(disagreement_id)
        query_region_id = _text(row["query_region_id"], "query_region_id")
        if query_region_id not in expected_disagreement_ids:
            raise ControlledExperimentError(
                "Adjudication resolution references a query without an exact reviewer-cell disagreement."
            )
        if query_region_id in resolved_query_ids:
            raise ControlledExperimentError(
                "Adjudication resolutions must cover each disagreeing query exactly once."
            )
        resolved_query_ids.add(query_region_id)
        reviewer_decisions = row["reviewer_decision_sha256_by_reviewer"]
        if not isinstance(reviewer_decisions, Mapping) or set(
            reviewer_decisions
        ) != set(supplied_reviewers):
            raise ControlledExperimentError(
                "Adjudication reviewer-decision hashes are incomplete or substituted."
            )
        expected_decisions = expected_reviewer_decision_sha256_by_query[query_region_id]
        normalized_decisions = {
            reviewer_id: _sha256(
                reviewer_decisions[reviewer_id],
                f"{query_region_id}/{reviewer_id} reviewer decision SHA-256",
            )
            for reviewer_id in supplied_reviewers
        }
        if normalized_decisions != dict(expected_decisions):
            raise ControlledExperimentError(
                "Adjudication reviewer-decision hashes differ from exact reviewer cells."
            )
        outcome = _text(row["adjudication_outcome"], "adjudication_outcome")
        if outcome not in {
            "accept_a",
            "accept_b",
            "redraw",
            "uncertain",
            "unobservable",
            "reject",
        }:
            raise ControlledExperimentError(
                "Adjudication outcome is outside the approved taxonomy."
            )
        _text(row["resolution_reason"], "resolution_reason")
    if resolved_query_ids != expected_disagreement_ids:
        raise ControlledExperimentError(
            "Adjudication resolutions do not exactly cover reviewer-cell disagreements."
        )
    _text(payload["resolution_method"], "resolution_method")
    _text(payload["assumptions"], "adjudication assumptions")
    _reject_private_paths(payload)


def _validated_error_strata(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ("cell_id", *ERROR_STRATA)
    _require_exact_columns(frame, columns, "error strata")
    if frame.empty:
        raise ControlledExperimentError("Error-strata evidence must not be empty.")
    normalized = frame.copy()
    normalized["cell_id"] = normalized["cell_id"].map(
        lambda value: _text(value, "error strata cell_id")
    )
    if normalized["cell_id"].duplicated().any():
        raise ControlledExperimentError("Error-strata cell IDs must be unique.")
    for column in ERROR_STRATA:
        normalized[column] = normalized[column].map(
            lambda value, name=column: _strict_bool(value, name)
        )
    return normalized.sort_values("cell_id").reset_index(drop=True)


def write_signed_reference_cell_receipt(
    reference_mask_path: str | Path,
    *,
    acquisition: AcquisitionGateAssessment,
    reviewer_qualification: VerifiedReviewerQualification,
    holdout: VerifiedSpatialHoldout,
    error_strata_path: str | Path,
    reference_cell_output_path: str | Path,
    calibration_reference_output_path: str | Path,
    derived_at_utc: datetime,
    derivation_method: str,
    assumptions: str,
    signing_key_id: str,
    signing_key: bytes,
    output_path: str | Path,
) -> dict[str, object]:
    """Derive cells from the exact qualified mask, then sign all lineage."""

    _verify_acquisition_assessment(acquisition)
    if not acquisition.ready or acquisition.authority_receipt_sha256 is None:
        raise ControlledExperimentError(
            "Signed, ready acquisition authority is required for reference cells."
        )
    _verify_holdout_instance(holdout)
    _verify_holdout_acquisition_lineage(holdout.receipt, acquisition)
    if (
        holdout.receipt["experiment_id"] != acquisition.experiment_id
        or holdout.receipt["study_area"] != acquisition.study_area
    ):
        raise ControlledExperimentError(
            "Reference-cell acquisition and spatial holdout scope do not match."
        )
    if (
        reviewer_qualification._verification_marker
        is not _VERIFIED_REVIEWER_QUALIFICATION_MARKER
        or reviewer_qualification.experiment_id != acquisition.experiment_id
        or reviewer_qualification.study_area != acquisition.study_area
        or reviewer_qualification.acquisition_manifest_sha256
        != acquisition.manifest_sha256
        or reviewer_qualification.reference_mask_sha256
        != acquisition.reference_mask_sha256
    ):
        raise ControlledExperimentError(
            "Verified reviewer qualification does not match reference derivation."
        )
    forbidden_key_ids = {
        acquisition.authority_signing_key_id,
        reviewer_qualification.reviewer_signing_key_id,
        reviewer_qualification.adjudicator_signing_key_id,
        str(holdout.receipt["signing_key_id"]),
    }
    if signing_key_id in forbidden_key_ids:
        raise ControlledExperimentError(
            "Reference derivation must use a distinct signing identity."
        )
    derived = _timestamp(_format_utc(derived_at_utc), "derived_at_utc")
    frozen = _timestamp(holdout.receipt["frozen_at_utc"], "holdout frozen_at_utc")
    if derived < frozen or derived < reviewer_qualification.qualified_at_utc:
        raise ControlledExperimentError(
            "Reference-cell evidence cannot predate holdout or reviewer qualification."
        )
    mask_path = Path(reference_mask_path)
    strata_path = Path(error_strata_path)
    strata_frame, strata_sha = _read_csv_snapshot(strata_path, "error strata")
    strata = _validated_error_strata(strata_frame)
    if strata_sha != reviewer_qualification.error_strata_file_sha256:
        raise ControlledExperimentError(
            "Error-strata evidence differs from reviewer qualification."
        )
    frame, raster_contract, mask_sha = _derive_reference_cells_from_mask(
        mask_path,
        holdout=holdout,
        error_strata=strata,
        expected_sha256=acquisition.reference_mask_sha256,
    )
    cells = _validated_reference_cells(frame, holdout)
    evidence_path = Path(reference_cell_output_path)
    calibration_path = Path(calibration_reference_output_path)
    target = Path(output_path)
    if (
        evidence_path.suffix.lower() != ".csv"
        or calibration_path.suffix.lower() != ".csv"
    ):
        raise ControlledExperimentError("Reference-cell outputs must be CSV files.")
    if target.suffix.lower() != ".json":
        raise ControlledExperimentError("Reference-cell receipt must be JSON.")
    if evidence_path.exists() or calibration_path.exists() or target.exists():
        raise ControlledExperimentError(
            "Reference-cell outputs are immutable and already exist."
        )
    evidence_bytes = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    evidence_sha = hashlib.sha256(evidence_bytes).hexdigest()
    calibration_ids = {
        item.cell_id for item in holdout.memberships if item.split == "calibration"
    }
    calibration_frame = frame.loc[
        frame["cell_id"].isin(calibration_ids),
        ["cell_id", "reference_flood_extent"],
    ].sort_values("cell_id")
    if set(calibration_frame["cell_id"]) != calibration_ids:
        raise ControlledExperimentError(
            "Calibration reference projection does not cover the calibration split."
        )
    calibration_bytes = calibration_frame.to_csv(
        index=False, lineterminator="\n"
    ).encode("utf-8")
    calibration_sha = hashlib.sha256(calibration_bytes).hexdigest()
    payload: dict[str, object] = {
        "artifact_schema": REFERENCE_CELL_RECEIPT_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "reference_mask_sha256": mask_sha,
        "reference_mask_file": mask_path.name,
        "reference_mask_raster_contract": raster_contract,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": acquisition.authority_receipt_sha256,
        "reference_mask_status": "qualified_expert_or_adjudicated",
        "reviewer_qualification_receipt_file_sha256": (
            reviewer_qualification.receipt_file_sha256
        ),
        "reviewer_qualification_manifest_sha256": (
            reviewer_qualification.manifest_sha256
        ),
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "grid_contract_sha256": holdout.receipt["grid_contract_sha256"],
        "reference_cell_file": evidence_path.name,
        "reference_cell_sha256": evidence_sha,
        "reference_cell_ids_sha256": _canonical_sha256(
            [cell.cell_id for cell in cells]
        ),
        "cell_count": len(cells),
        "calibration_reference_file": calibration_path.name,
        "calibration_reference_sha256": calibration_sha,
        "calibration_reference_ids_sha256": _canonical_sha256(sorted(calibration_ids)),
        "calibration_reference_count": len(calibration_ids),
        "error_strata_file": strata_path.name,
        "error_strata_file_sha256": strata_sha,
        "derived_at_utc": _format_utc(derived),
        "derivation_method": _text(derivation_method, "derivation_method"),
        "assumptions": _text(assumptions, "assumptions"),
        "signing_role": SIGNING_ROLES["reference"],
        "processing_allowed": True,
        "can_feed_decision_layer": False,
        "official_warning": False,
    }
    sealed = _seal_signed_payload(
        payload,
        signing_key_id=signing_key_id,
        signing_key=signing_key,
        self_hash_field="manifest_sha256",
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    calibration_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open("xb") as handle:
        handle.write(evidence_bytes)
    with calibration_path.open("xb") as handle:
        handle.write(calibration_bytes)
    _write_immutable_json(sealed, target, "Reference-cell receipt")
    return sealed


def load_signed_reference_cell_evidence(
    receipt_path: str | Path,
    reference_cell_path: str | Path,
    *,
    acquisition: AcquisitionGateAssessment,
    reviewer_qualification: VerifiedReviewerQualification,
    holdout: VerifiedSpatialHoldout,
    calibration_reference_path: str | Path,
    error_strata_path: str | Path,
    signing_keys: Mapping[str, bytes],
) -> VerifiedReferenceCellEvidence:
    """Verify signed mask-derived reference cells and calibration projection."""

    _verify_acquisition_assessment(acquisition)
    _verify_holdout_instance(holdout)
    _verify_holdout_acquisition_lineage(holdout.receipt, acquisition)
    receipt_file = Path(receipt_path)
    receipt_bytes = _read_stable_bytes(receipt_file, "reference-cell receipt")
    receipt_file_sha = hashlib.sha256(receipt_bytes).hexdigest()
    payload = _json_object_bytes(receipt_bytes, "reference-cell receipt")
    required = {
        "artifact_schema",
        "experiment_id",
        "study_area",
        "reference_mask_sha256",
        "reference_mask_file",
        "reference_mask_raster_contract",
        "acquisition_manifest_sha256",
        "acquisition_authority_receipt_sha256",
        "reference_mask_status",
        "reviewer_qualification_receipt_file_sha256",
        "reviewer_qualification_manifest_sha256",
        "spatial_holdout_manifest_sha256",
        "spatial_holdout_membership_sha256",
        "grid_contract_sha256",
        "reference_cell_file",
        "reference_cell_sha256",
        "reference_cell_ids_sha256",
        "cell_count",
        "calibration_reference_file",
        "calibration_reference_sha256",
        "calibration_reference_ids_sha256",
        "calibration_reference_count",
        "error_strata_file",
        "error_strata_file_sha256",
        "derived_at_utc",
        "derivation_method",
        "assumptions",
        "signing_role",
        "processing_allowed",
        "can_feed_decision_layer",
        "official_warning",
        "signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "signature",
    }
    _exact_keys(payload, required, "reference-cell receipt")
    if payload["artifact_schema"] != REFERENCE_CELL_RECEIPT_SCHEMA:
        raise ControlledExperimentError("Reference-cell receipt schema is unsupported.")
    _verify_signed_payload(payload, signing_keys, "reference-cell receipt")
    _verify_self_hash(payload, "manifest_sha256", "reference-cell receipt")
    if not acquisition.ready or acquisition.authority_receipt_sha256 is None:
        raise ControlledExperimentError(
            "Reference-cell verification requires ready acquisition authority."
        )
    if (
        reviewer_qualification._verification_marker
        is not _VERIFIED_REVIEWER_QUALIFICATION_MARKER
    ):
        raise ControlledExperimentError("Reviewer qualification is not verified.")
    expected_lineage = {
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "reference_mask_sha256": acquisition.reference_mask_sha256,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": acquisition.authority_receipt_sha256,
        "reference_mask_status": "qualified_expert_or_adjudicated",
        "reviewer_qualification_receipt_file_sha256": (
            reviewer_qualification.receipt_file_sha256
        ),
        "reviewer_qualification_manifest_sha256": reviewer_qualification.manifest_sha256,
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "grid_contract_sha256": holdout.receipt["grid_contract_sha256"],
    }
    for field, expected in expected_lineage.items():
        if payload[field] != expected:
            raise ControlledExperimentError(
                f"Reference-cell receipt {field} was substituted."
            )
    if (
        payload["signing_role"] != SIGNING_ROLES["reference"]
        or payload["signing_key_id"]
        in {
            acquisition.authority_signing_key_id,
            reviewer_qualification.reviewer_signing_key_id,
            reviewer_qualification.adjudicator_signing_key_id,
            holdout.receipt["signing_key_id"],
        }
        or payload["processing_allowed"] is not True
        or payload["can_feed_decision_layer"] is not False
        or payload["official_warning"] is not False
    ):
        raise ControlledExperimentError(
            "Reference-cell receipt has unsafe status fields."
        )
    _require_distinct_trusted_credentials(
        signing_keys,
        [
            str(acquisition.authority_signing_key_id),
            reviewer_qualification.reviewer_signing_key_id,
            reviewer_qualification.adjudicator_signing_key_id,
            str(holdout.receipt["signing_key_id"]),
            str(payload["signing_key_id"]),
        ],
        label="reference-cell authority roles",
    )
    _basename(payload["reference_mask_file"], "reference_mask_file")
    _validate_reference_raster_contract(payload["reference_mask_raster_contract"])
    _text(payload["derivation_method"], "reference-cell derivation_method")
    _text(payload["assumptions"], "reference-cell assumptions")
    evidence_path = Path(reference_cell_path)
    if evidence_path.name != _basename(
        payload["reference_cell_file"], "reference_cell_file"
    ):
        raise ControlledExperimentError("Reference-cell filename was substituted.")
    frame, evidence_sha = _read_csv_snapshot(evidence_path, "reference-cell evidence")
    if evidence_sha != _sha256(
        payload["reference_cell_sha256"], "reference_cell_sha256"
    ):
        raise ControlledExperimentError(
            "Reference-cell evidence checksum was substituted."
        )
    cells = _validated_reference_cells(frame, holdout)
    if len(cells) != _positive_int(payload["cell_count"], "reference cell_count"):
        raise ControlledExperimentError(
            "Reference-cell count does not match its receipt."
        )
    if _canonical_sha256([cell.cell_id for cell in cells]) != _sha256(
        payload["reference_cell_ids_sha256"], "reference_cell_ids_sha256"
    ):
        raise ControlledExperimentError(
            "Reference-cell IDs do not match their receipt."
        )
    calibration_path = Path(calibration_reference_path)
    if calibration_path.name != _basename(
        payload["calibration_reference_file"], "calibration_reference_file"
    ):
        raise ControlledExperimentError(
            "Calibration reference filename was substituted."
        )
    calibration_frame, calibration_sha = _read_csv_snapshot(
        calibration_path, "calibration reference"
    )
    if calibration_sha != _sha256(
        payload["calibration_reference_sha256"], "calibration_reference_sha256"
    ):
        raise ControlledExperimentError(
            "Calibration reference checksum was substituted."
        )
    _validate_calibration_reference_projection(
        calibration_frame, holdout=holdout, reference_cells=cells, receipt=payload
    )
    strata_path = Path(error_strata_path)
    if strata_path.name != _basename(payload["error_strata_file"], "error_strata_file"):
        raise ControlledExperimentError("Error-strata filename was substituted.")
    strata_frame, strata_sha = _read_csv_snapshot(strata_path, "error strata")
    if (
        strata_sha
        != _sha256(payload["error_strata_file_sha256"], "error_strata_file_sha256")
        or strata_sha != reviewer_qualification.error_strata_file_sha256
    ):
        raise ControlledExperimentError("Error-strata evidence was substituted.")
    _validated_error_strata(strata_frame)
    derived_at = _timestamp(payload["derived_at_utc"], "reference-cell derived_at_utc")
    if derived_at < reviewer_qualification.qualified_at_utc:
        raise ControlledExperimentError(
            "Reference cells predate reviewer qualification."
        )
    _reject_private_paths(payload)
    return VerifiedReferenceCellEvidence(
        experiment_id=acquisition.experiment_id,
        study_area=acquisition.study_area,
        reference_mask_sha256=acquisition.reference_mask_sha256,
        spatial_holdout_manifest_sha256=holdout.manifest_sha256,
        spatial_holdout_membership_sha256=holdout.membership_sha256,
        grid_contract_sha256=str(holdout.receipt["grid_contract_sha256"]),
        reviewer_qualification_manifest_sha256=(reviewer_qualification.manifest_sha256),
        manifest_sha256=str(payload["manifest_sha256"]),
        receipt_file_sha256=receipt_file_sha,
        evidence_file_sha256=evidence_sha,
        calibration_reference_file_sha256=calibration_sha,
        error_strata_file_sha256=strata_sha,
        derived_at_utc=derived_at,
        signing_key_id=str(payload["signing_key_id"]),
        cells=cells,
        _verification_marker=_VERIFIED_REFERENCE_MARKER,
    )


def _derive_reference_cells_from_mask(
    reference_mask_path: Path,
    *,
    holdout: VerifiedSpatialHoldout,
    error_strata: pd.DataFrame,
    expected_sha256: str,
) -> tuple[pd.DataFrame, dict[str, object], str]:
    """Sample a binary authoritative raster at frozen cell centres without reprojection."""

    try:
        import numpy as np
        from rasterio.io import MemoryFile
    except ImportError as exc:
        raise ControlledExperimentError(
            "Reference-mask derivation requires Rasterio and NumPy."
        ) from exc
    content = _read_stable_bytes(reference_mask_path, "qualified reference mask")
    mask_sha = hashlib.sha256(content).hexdigest()
    if mask_sha != _sha256(expected_sha256, "reference mask sha256"):
        raise ControlledExperimentError(
            "Reference-mask bytes do not match acquisition authority."
        )
    expected_crs = str(holdout.receipt["target_crs"]).upper()
    try:
        with MemoryFile(content) as memory_file, memory_file.open() as dataset:
            if dataset.count != 1 or dataset.crs is None:
                raise ControlledExperimentError(
                    "Reference mask must be a single-band georeferenced raster."
                )
            observed_crs = dataset.crs.to_string().upper()
            if observed_crs != expected_crs:
                raise ControlledExperimentError(
                    "Reference-mask CRS must exactly match the frozen analysis CRS."
                )
            if dataset.width <= 0 or dataset.height <= 0 or dataset.nodata is None:
                raise ControlledExperimentError(
                    "Reference mask requires positive dimensions and explicit nodata."
                )
            nodata = float(dataset.nodata)
            if not math.isfinite(nodata) or nodata in {0.0, 1.0}:
                raise ControlledExperimentError(
                    "Reference-mask nodata must be finite and distinct from classes 0/1."
                )
            band = dataset.read(1)
            valid = band[band != dataset.nodata]
            if valid.size == 0 or not np.isin(valid, [0, 1]).all():
                raise ControlledExperimentError(
                    "Reference-mask valid pixels must use only binary classes 0 and 1."
                )
            values: dict[str, int] = {}
            for membership in holdout.memberships:
                row, column = dataset.index(membership.x, membership.y)
                if (
                    row < 0
                    or column < 0
                    or row >= dataset.height
                    or column >= dataset.width
                ):
                    raise ControlledExperimentError(
                        f"Reference mask does not cover cell {membership.cell_id}."
                    )
                value = band[row, column]
                if value == dataset.nodata:
                    raise ControlledExperimentError(
                        f"Reference mask is nodata at cell {membership.cell_id}."
                    )
                if int(value) not in {0, 1} or float(value) != float(int(value)):
                    raise ControlledExperimentError(
                        f"Reference mask class is invalid at cell {membership.cell_id}."
                    )
                values[membership.cell_id] = int(value)
            raster_contract: dict[str, object] = {
                "crs": observed_crs,
                "transform": [float(value) for value in dataset.transform[:6]],
                "width": int(dataset.width),
                "height": int(dataset.height),
                "nodata": nodata,
                "dtype": str(dataset.dtypes[0]),
                "class_mapping": {"non_flood": 0, "flood": 1},
                "sampling_rule": "frozen_analysis_cell_center_nearest_source_pixel",
                "reprojection_performed": False,
            }
    except ControlledExperimentError:
        raise
    except Exception as exc:
        raise ControlledExperimentError(
            "Qualified reference mask could not be read safely."
        ) from exc
    expected_ids = {item.cell_id for item in holdout.memberships}
    if set(error_strata["cell_id"]) != expected_ids:
        raise ControlledExperimentError(
            "Error-strata evidence must exactly cover frozen holdout membership."
        )
    strata_by_cell = error_strata.set_index("cell_id")
    rows = []
    for cell_id in sorted(expected_ids):
        rows.append(
            {
                "cell_id": cell_id,
                "reference_flood_extent": values[cell_id],
                **{
                    category: bool(strata_by_cell.at[cell_id, category])
                    for category in ERROR_STRATA
                },
            }
        )
    frame = pd.DataFrame(rows, columns=REFERENCE_CELL_COLUMNS)
    _validate_reference_raster_contract(raster_contract)
    return frame, raster_contract, mask_sha


def load_signed_calibration_reference_evidence(
    receipt_path: str | Path,
    calibration_reference_path: str | Path,
    *,
    acquisition: AcquisitionGateAssessment,
    reviewer_qualification: VerifiedReviewerQualification,
    holdout: VerifiedSpatialHoldout,
    signing_keys: Mapping[str, bytes],
) -> VerifiedCalibrationReference:
    """Verify only the signed calibration projection; final truth stays unopened."""

    _verify_acquisition_assessment(acquisition)
    _verify_holdout_instance(holdout)
    _verify_holdout_acquisition_lineage(holdout.receipt, acquisition)
    receipt_file = Path(receipt_path)
    content = _read_stable_bytes(receipt_file, "reference-cell receipt")
    receipt_file_sha = hashlib.sha256(content).hexdigest()
    payload = _json_object_bytes(content, "reference-cell receipt")
    required = {
        "artifact_schema",
        "experiment_id",
        "study_area",
        "reference_mask_sha256",
        "reference_mask_file",
        "reference_mask_raster_contract",
        "acquisition_manifest_sha256",
        "acquisition_authority_receipt_sha256",
        "reference_mask_status",
        "reviewer_qualification_receipt_file_sha256",
        "reviewer_qualification_manifest_sha256",
        "spatial_holdout_manifest_sha256",
        "spatial_holdout_membership_sha256",
        "grid_contract_sha256",
        "reference_cell_file",
        "reference_cell_sha256",
        "reference_cell_ids_sha256",
        "cell_count",
        "calibration_reference_file",
        "calibration_reference_sha256",
        "calibration_reference_ids_sha256",
        "calibration_reference_count",
        "error_strata_file",
        "error_strata_file_sha256",
        "derived_at_utc",
        "derivation_method",
        "assumptions",
        "signing_role",
        "processing_allowed",
        "can_feed_decision_layer",
        "official_warning",
        "signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "signature",
    }
    _exact_keys(payload, required, "reference-cell receipt")
    if payload["artifact_schema"] != REFERENCE_CELL_RECEIPT_SCHEMA:
        raise ControlledExperimentError("Reference-cell receipt schema is unsupported.")
    _verify_signed_payload(payload, signing_keys, "reference-cell receipt")
    _verify_self_hash(payload, "manifest_sha256", "reference-cell receipt")
    expected = {
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "reference_mask_sha256": acquisition.reference_mask_sha256,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": acquisition.authority_receipt_sha256,
        "reviewer_qualification_receipt_file_sha256": (
            reviewer_qualification.receipt_file_sha256
        ),
        "reviewer_qualification_manifest_sha256": reviewer_qualification.manifest_sha256,
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "grid_contract_sha256": holdout.receipt["grid_contract_sha256"],
    }
    for field, value in expected.items():
        if payload[field] != value:
            raise ControlledExperimentError(
                f"Calibration reference {field} was substituted."
            )
    if (
        payload["signing_role"] != SIGNING_ROLES["reference"]
        or payload["processing_allowed"] is not True
        or payload["can_feed_decision_layer"] is not False
        or payload["official_warning"] is not False
    ):
        raise ControlledExperimentError(
            "Calibration reference has unsafe status fields."
        )
    calibration_path = Path(calibration_reference_path)
    if calibration_path.name != _basename(
        payload["calibration_reference_file"], "calibration_reference_file"
    ):
        raise ControlledExperimentError(
            "Calibration reference filename was substituted."
        )
    frame, file_sha = _read_csv_snapshot(calibration_path, "calibration reference")
    if file_sha != _sha256(
        payload["calibration_reference_sha256"], "calibration_reference_sha256"
    ):
        raise ControlledExperimentError(
            "Calibration reference checksum was substituted."
        )
    _require_exact_columns(
        frame, ("cell_id", "reference_flood_extent"), "calibration reference"
    )
    normalized = frame.copy()
    normalized["cell_id"] = normalized["cell_id"].map(
        lambda value: _text(value, "calibration reference cell_id")
    )
    if normalized["cell_id"].duplicated().any():
        raise ControlledExperimentError("Calibration reference IDs must be unique.")
    normalized["reference_flood_extent"] = _binary_series(
        normalized["reference_flood_extent"], "calibration reference"
    )
    normalized = normalized.sort_values("cell_id").reset_index(drop=True)
    expected_ids = sorted(
        item.cell_id for item in holdout.memberships if item.split == "calibration"
    )
    if normalized["cell_id"].tolist() != expected_ids:
        raise ControlledExperimentError(
            "Calibration reference does not exactly cover the calibration partition."
        )
    if len(expected_ids) != _positive_int(
        payload["calibration_reference_count"], "calibration reference count"
    ) or _canonical_sha256(expected_ids) != _sha256(
        payload["calibration_reference_ids_sha256"],
        "calibration_reference_ids_sha256",
    ):
        raise ControlledExperimentError(
            "Calibration reference membership differs from the receipt."
        )
    derived = _timestamp(payload["derived_at_utc"], "reference derived_at_utc")
    if derived < reviewer_qualification.qualified_at_utc:
        raise ControlledExperimentError(
            "Calibration reference predates reviewer qualification."
        )
    _validate_reference_raster_contract(payload["reference_mask_raster_contract"])
    _reject_private_paths(payload)
    return VerifiedCalibrationReference(
        experiment_id=acquisition.experiment_id,
        study_area=acquisition.study_area,
        reference_receipt_file_sha256=receipt_file_sha,
        reference_manifest_sha256=str(payload["manifest_sha256"]),
        reference_cell_evidence_sha256=str(payload["reference_cell_sha256"]),
        reference_mask_sha256=acquisition.reference_mask_sha256,
        reviewer_qualification_manifest_sha256=(reviewer_qualification.manifest_sha256),
        spatial_holdout_manifest_sha256=holdout.manifest_sha256,
        calibration_partition_sha256=holdout.calibration_partition_sha256,
        calibration_file_sha256=file_sha,
        reference_signing_key_id=str(payload["signing_key_id"]),
        derived_at_utc=derived,
        cells=tuple(
            (str(row["cell_id"]), int(row["reference_flood_extent"]))
            for row in normalized.to_dict("records")
        ),
        _verification_marker=_VERIFIED_CALIBRATION_REFERENCE_MARKER,
    )


def write_signed_execution_authorization_receipt(
    *,
    acquisition: AcquisitionGateAssessment,
    reviewer_qualification: VerifiedReviewerQualification,
    holdout: VerifiedSpatialHoldout,
    reference_cells: VerifiedReferenceCellEvidence,
    promotion_policy_path: str | Path,
    signing_keys: Mapping[str, bytes],
    expires_at_utc: datetime,
    signing_key_id: str,
    signing_key: bytes,
    output_path: str | Path,
) -> dict[str, object]:
    """Sign the complete pre-execution gate without model-output evidence."""

    _verify_acquisition_assessment(acquisition)
    try:
        from floodguard.model_promotion import (
            ModelPromotionError,
            load_signed_model_promotion_policy,
        )
    except ImportError as exc:
        raise ControlledExperimentError(
            "Model promotion policy verifier is unavailable."
        ) from exc
    authorized = datetime.now(UTC)
    try:
        policy, policy_file_sha = _load_promotion_policy_snapshot(
            Path(promotion_policy_path),
            signing_keys=signing_keys,
            evaluated_at_utc=authorized,
            loader=load_signed_model_promotion_policy,
        )
    except (ModelPromotionError, OSError) as exc:
        raise ControlledExperimentError(
            "Predeclared promotion policy is invalid."
        ) from exc
    _verify_execution_prerequisites(
        acquisition=acquisition,
        reviewer_qualification=reviewer_qualification,
        holdout=holdout,
        reference_cells=reference_cells,
    )
    if (
        policy["experiment_id"] != acquisition.experiment_id
        or policy["study_area"] != acquisition.study_area
    ):
        raise ControlledExperimentError(
            "Promotion policy scope differs from experiment prerequisites."
        )
    expires = _timestamp(_format_utc(expires_at_utc), "execution expires_at_utc")
    if expires <= authorized:
        raise ControlledExperimentError(
            "Execution authorization expiry must be in the future."
        )
    upstream_key_ids = {
        acquisition.authority_signing_key_id,
        reviewer_qualification.reviewer_signing_key_id,
        reviewer_qualification.adjudicator_signing_key_id,
        str(holdout.receipt["signing_key_id"]),
        reference_cells.signing_key_id,
        str(policy["signing_key_id"]),
    }
    if signing_key_id in upstream_key_ids:
        raise ControlledExperimentError(
            "Execution authorization must use a distinct signing identity."
        )
    latest_prerequisite = max(
        value
        for value in (
            acquisition.authority_issued_at_utc,
            reviewer_qualification.qualified_at_utc,
            _timestamp(holdout.receipt["frozen_at_utc"], "holdout frozen_at_utc"),
            reference_cells.derived_at_utc,
            _timestamp(policy["issued_at_utc"], "policy issued_at_utc"),
        )
        if value is not None
    )
    if authorized < latest_prerequisite:
        raise ControlledExperimentError(
            "Execution authorization predates a verified prerequisite."
        )
    payload: dict[str, object] = {
        "artifact_schema": EXECUTION_AUTHORIZATION_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": acquisition.authority_receipt_sha256,
        "reviewer_qualification_manifest_sha256": (
            reviewer_qualification.manifest_sha256
        ),
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "reference_cell_receipt_file_sha256": reference_cells.receipt_file_sha256,
        "reference_cell_manifest_sha256": reference_cells.manifest_sha256,
        "reference_cell_evidence_sha256": reference_cells.evidence_file_sha256,
        "promotion_policy_file": Path(promotion_policy_path).name,
        "promotion_policy_file_sha256": policy_file_sha,
        "promotion_policy_manifest_sha256": policy["manifest_sha256"],
        "prerequisite_latest_at_utc": _format_utc(latest_prerequisite),
        "authorized_at_utc": _format_utc(authorized),
        "expires_at_utc": _format_utc(expires),
        "signing_role": SIGNING_ROLES["execution"],
        "authorization_status": "authorized_for_bounded_model_lane_execution",
        "processing_allowed": True,
        "experiment_executed": False,
        "can_feed_decision_layer": False,
        "official_warning": False,
        "operational_status": "non_operational",
    }
    sealed = _seal_signed_payload(
        payload,
        signing_key_id=signing_key_id,
        signing_key=signing_key,
        self_hash_field="manifest_sha256",
    )
    _write_immutable_json(sealed, Path(output_path), "Execution authorization receipt")
    return sealed


def load_signed_execution_authorization_receipt(
    receipt_path: str | Path,
    *,
    acquisition: AcquisitionGateAssessment,
    reviewer_qualification: VerifiedReviewerQualification,
    holdout: VerifiedSpatialHoldout,
    reference_cells: VerifiedReferenceCellEvidence | None = None,
    calibration_reference: VerifiedCalibrationReference | None = None,
    promotion_policy_path: str | Path,
    signing_keys: Mapping[str, bytes],
    verified_at_utc: datetime | None = None,
) -> VerifiedExecutionAuthorization:
    """Verify the signed pre-execution gate and every bound prerequisite hash.

    Threshold-selection callers must supply ``calibration_reference`` only.  That
    path verifies the signed parent reference receipt without opening the full
    reference-cell CSV, preserving the final-holdout isolation boundary.  Final
    evaluation callers supply ``reference_cells`` instead.
    """

    _verify_acquisition_assessment(acquisition)
    try:
        from floodguard.model_promotion import (
            ModelPromotionError,
            load_signed_model_promotion_policy,
        )
    except ImportError as exc:
        raise ControlledExperimentError(
            "Model promotion policy verifier is unavailable."
        ) from exc
    verified = verified_at_utc or datetime.now(UTC)
    if (reference_cells is None) == (calibration_reference is None):
        raise ControlledExperimentError(
            "Execution authorization verification requires exactly one of "
            "reference_cells or calibration_reference."
        )
    if reference_cells is not None:
        _verify_execution_prerequisites(
            acquisition=acquisition,
            reviewer_qualification=reviewer_qualification,
            holdout=holdout,
            reference_cells=reference_cells,
        )
        reference_receipt_file_sha256 = reference_cells.receipt_file_sha256
        reference_manifest_sha256 = reference_cells.manifest_sha256
        reference_cell_evidence_sha256 = reference_cells.evidence_file_sha256
        reference_signing_key_id = reference_cells.signing_key_id
        reference_derived_at_utc = reference_cells.derived_at_utc
    else:
        assert calibration_reference is not None
        _verify_calibration_execution_prerequisites(
            acquisition=acquisition,
            reviewer_qualification=reviewer_qualification,
            holdout=holdout,
            calibration_reference=calibration_reference,
        )
        reference_receipt_file_sha256 = (
            calibration_reference.reference_receipt_file_sha256
        )
        reference_manifest_sha256 = calibration_reference.reference_manifest_sha256
        reference_cell_evidence_sha256 = (
            calibration_reference.reference_cell_evidence_sha256
        )
        reference_signing_key_id = calibration_reference.reference_signing_key_id
        reference_derived_at_utc = calibration_reference.derived_at_utc
    try:
        policy, policy_file_sha = _load_promotion_policy_snapshot(
            Path(promotion_policy_path),
            signing_keys=signing_keys,
            evaluated_at_utc=verified,
            loader=load_signed_model_promotion_policy,
        )
    except (ModelPromotionError, OSError) as exc:
        raise ControlledExperimentError(
            "Predeclared promotion policy is invalid."
        ) from exc
    path = Path(receipt_path)
    content = _read_stable_bytes(path, "execution authorization receipt")
    file_sha = hashlib.sha256(content).hexdigest()
    payload = _json_object_bytes(content, "execution authorization receipt")
    required = {
        "artifact_schema",
        "experiment_id",
        "study_area",
        "acquisition_manifest_sha256",
        "acquisition_authority_receipt_sha256",
        "reviewer_qualification_manifest_sha256",
        "spatial_holdout_manifest_sha256",
        "spatial_holdout_membership_sha256",
        "reference_cell_receipt_file_sha256",
        "reference_cell_manifest_sha256",
        "reference_cell_evidence_sha256",
        "promotion_policy_file",
        "promotion_policy_file_sha256",
        "promotion_policy_manifest_sha256",
        "prerequisite_latest_at_utc",
        "authorized_at_utc",
        "expires_at_utc",
        "signing_role",
        "authorization_status",
        "processing_allowed",
        "experiment_executed",
        "can_feed_decision_layer",
        "official_warning",
        "operational_status",
        "signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "signature",
    }
    _exact_keys(payload, required, "execution authorization receipt")
    if payload["artifact_schema"] != EXECUTION_AUTHORIZATION_SCHEMA:
        raise ControlledExperimentError(
            "Execution authorization receipt schema is unsupported."
        )
    _verify_signed_payload(payload, signing_keys, "execution authorization receipt")
    _verify_self_hash(payload, "manifest_sha256", "execution authorization receipt")
    policy_path = Path(promotion_policy_path)
    expected = {
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": acquisition.authority_receipt_sha256,
        "reviewer_qualification_manifest_sha256": reviewer_qualification.manifest_sha256,
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "reference_cell_receipt_file_sha256": reference_receipt_file_sha256,
        "reference_cell_manifest_sha256": reference_manifest_sha256,
        "reference_cell_evidence_sha256": reference_cell_evidence_sha256,
        "promotion_policy_file": policy_path.name,
        "promotion_policy_file_sha256": policy_file_sha,
        "promotion_policy_manifest_sha256": policy["manifest_sha256"],
    }
    for field, value in expected.items():
        if payload[field] != value:
            raise ControlledExperimentError(
                f"Execution authorization {field} was substituted."
            )
    authorized = _timestamp(payload["authorized_at_utc"], "authorized_at_utc")
    expires = _timestamp(payload["expires_at_utc"], "expires_at_utc")
    checked = _timestamp(_format_utc(verified), "verified_at_utc")
    latest = _timestamp(
        payload["prerequisite_latest_at_utc"], "prerequisite_latest_at_utc"
    )
    expected_latest = max(
        value
        for value in (
            acquisition.authority_issued_at_utc,
            reviewer_qualification.qualified_at_utc,
            _timestamp(holdout.receipt["frozen_at_utc"], "holdout frozen_at_utc"),
            reference_derived_at_utc,
            _timestamp(policy["issued_at_utc"], "policy issued_at_utc"),
        )
        if value is not None
    )
    if latest != expected_latest:
        raise ControlledExperimentError(
            "Execution authorization prerequisite chronology was substituted."
        )
    if (
        expires <= authorized
        or authorized < latest
        or not authorized <= checked <= expires
    ):
        raise ControlledExperimentError(
            "Execution authorization is not currently valid."
        )
    if (
        payload["signing_role"] != SIGNING_ROLES["execution"]
        or payload["authorization_status"]
        != "authorized_for_bounded_model_lane_execution"
        or payload["processing_allowed"] is not True
        or payload["experiment_executed"] is not False
        or payload["can_feed_decision_layer"] is not False
        or payload["official_warning"] is not False
        or payload["operational_status"] != "non_operational"
    ):
        raise ControlledExperimentError(
            "Execution authorization has unsafe status fields."
        )
    signing_key_id = _text(payload["signing_key_id"], "execution signing_key_id")
    upstream_ids = {
        acquisition.authority_signing_key_id,
        reviewer_qualification.reviewer_signing_key_id,
        reviewer_qualification.adjudicator_signing_key_id,
        holdout.receipt["signing_key_id"],
        reference_signing_key_id,
        policy["signing_key_id"],
    }
    if signing_key_id in upstream_ids:
        raise ControlledExperimentError(
            "Execution authorization signing identity is not role-separated."
        )
    _require_distinct_trusted_credentials(
        signing_keys,
        [
            signing_key_id,
            *(str(value) for value in upstream_ids if value is not None),
        ],
        label="execution-authorization authority roles",
    )
    _reject_private_paths(payload)
    return VerifiedExecutionAuthorization(
        experiment_id=acquisition.experiment_id,
        study_area=acquisition.study_area,
        acquisition_manifest_sha256=acquisition.manifest_sha256,
        reviewer_qualification_manifest_sha256=(reviewer_qualification.manifest_sha256),
        spatial_holdout_manifest_sha256=holdout.manifest_sha256,
        reference_cell_manifest_sha256=reference_manifest_sha256,
        promotion_policy_manifest_sha256=str(policy["manifest_sha256"]),
        authorized_at_utc=authorized,
        expires_at_utc=expires,
        manifest_sha256=str(payload["manifest_sha256"]),
        receipt_file_sha256=file_sha,
        signing_key_id=signing_key_id,
        _verification_marker=_VERIFIED_EXECUTION_AUTHORIZATION_MARKER,
    )


def _verify_execution_prerequisites(
    *,
    acquisition: AcquisitionGateAssessment,
    reviewer_qualification: VerifiedReviewerQualification,
    holdout: VerifiedSpatialHoldout,
    reference_cells: VerifiedReferenceCellEvidence,
) -> None:
    _verify_acquisition_assessment(acquisition)
    _verify_holdout_instance(holdout)
    _verify_holdout_acquisition_lineage(holdout.receipt, acquisition)
    if (
        not acquisition.ready
        or acquisition.authority_receipt_sha256 is None
        or reviewer_qualification._verification_marker
        is not _VERIFIED_REVIEWER_QUALIFICATION_MARKER
        or reference_cells._verification_marker is not _VERIFIED_REFERENCE_MARKER
        or reviewer_qualification.experiment_id != acquisition.experiment_id
        or reviewer_qualification.study_area != acquisition.study_area
        or reviewer_qualification.acquisition_manifest_sha256
        != acquisition.manifest_sha256
        or holdout.receipt["experiment_id"] != acquisition.experiment_id
        or holdout.receipt["study_area"] != acquisition.study_area
        or reference_cells.experiment_id != acquisition.experiment_id
        or reference_cells.study_area != acquisition.study_area
        or reference_cells.spatial_holdout_manifest_sha256 != holdout.manifest_sha256
        or reference_cells.reviewer_qualification_manifest_sha256
        != reviewer_qualification.manifest_sha256
    ):
        raise ControlledExperimentError(
            "Pre-execution prerequisites do not share one verified lineage."
        )


def _verify_calibration_execution_prerequisites(
    *,
    acquisition: AcquisitionGateAssessment,
    reviewer_qualification: VerifiedReviewerQualification,
    holdout: VerifiedSpatialHoldout,
    calibration_reference: VerifiedCalibrationReference,
) -> None:
    """Verify execution lineage without opening final-holdout reference cells."""

    _verify_holdout_instance(holdout)
    _verify_holdout_acquisition_lineage(holdout.receipt, acquisition)
    if (
        not acquisition.ready
        or acquisition.authority_receipt_sha256 is None
        or reviewer_qualification._verification_marker
        is not _VERIFIED_REVIEWER_QUALIFICATION_MARKER
        or calibration_reference._verification_marker
        is not _VERIFIED_CALIBRATION_REFERENCE_MARKER
        or reviewer_qualification.experiment_id != acquisition.experiment_id
        or reviewer_qualification.study_area != acquisition.study_area
        or reviewer_qualification.acquisition_manifest_sha256
        != acquisition.manifest_sha256
        or holdout.receipt["experiment_id"] != acquisition.experiment_id
        or holdout.receipt["study_area"] != acquisition.study_area
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
    ):
        raise ControlledExperimentError(
            "Calibration-safe execution prerequisites do not share one verified lineage."
        )


def _load_promotion_policy_snapshot(
    path: Path,
    *,
    signing_keys: Mapping[str, bytes],
    evaluated_at_utc: datetime,
    loader: Any,
) -> tuple[dict[str, object], str]:
    content = _read_stable_bytes(path, "promotion policy")
    digest = hashlib.sha256(content).hexdigest()
    try:
        with tempfile.TemporaryDirectory(prefix="floodguard-policy-") as directory:
            snapshot = Path(directory) / "promotion-policy.json"
            snapshot.write_bytes(content)
            payload = loader(
                snapshot,
                signing_keys=signing_keys,
                evaluated_at_utc=evaluated_at_utc,
            )
    except OSError as exc:
        raise ControlledExperimentError(
            "Promotion policy snapshot could not be verified."
        ) from exc
    return dict(payload), digest


def _validate_reference_raster_contract(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ControlledExperimentError("Reference raster contract must be an object.")
    required = {
        "crs",
        "transform",
        "width",
        "height",
        "nodata",
        "dtype",
        "class_mapping",
        "sampling_rule",
        "reprojection_performed",
    }
    _exact_keys(value, required, "reference raster contract")
    if not EPSG_RE.fullmatch(_text(value["crs"], "reference raster crs")):
        raise ControlledExperimentError("Reference raster CRS must be EPSG-based.")
    transform = value["transform"]
    if (
        not isinstance(transform, list)
        or len(transform) != 6
        or any(not math.isfinite(float(item)) for item in transform)
    ):
        raise ControlledExperimentError("Reference raster transform is invalid.")
    _positive_int(value["width"], "reference raster width")
    _positive_int(value["height"], "reference raster height")
    nodata = _finite_float(value["nodata"], "reference raster nodata")
    if nodata in {0.0, 1.0}:
        raise ControlledExperimentError(
            "Reference raster nodata conflicts with classes."
        )
    _text(value["dtype"], "reference raster dtype")
    if value["class_mapping"] != {"non_flood": 0, "flood": 1}:
        raise ControlledExperimentError("Reference raster class mapping is invalid.")
    if (
        value["sampling_rule"] != "frozen_analysis_cell_center_nearest_source_pixel"
        or value["reprojection_performed"] is not False
    ):
        raise ControlledExperimentError(
            "Reference raster sampling contract is invalid."
        )


def _validate_calibration_reference_projection(
    frame: pd.DataFrame,
    *,
    holdout: VerifiedSpatialHoldout,
    reference_cells: Sequence[ReferenceCell],
    receipt: Mapping[str, object],
) -> None:
    _require_exact_columns(
        frame, ("cell_id", "reference_flood_extent"), "calibration reference"
    )
    normalized = frame.copy()
    normalized["cell_id"] = normalized["cell_id"].map(
        lambda value: _text(value, "calibration reference cell_id")
    )
    if normalized["cell_id"].duplicated().any():
        raise ControlledExperimentError("Calibration reference IDs must be unique.")
    normalized["reference_flood_extent"] = _binary_series(
        normalized["reference_flood_extent"], "calibration reference"
    )
    expected_ids = sorted(
        item.cell_id for item in holdout.memberships if item.split == "calibration"
    )
    normalized = normalized.sort_values("cell_id").reset_index(drop=True)
    if normalized["cell_id"].tolist() != expected_ids:
        raise ControlledExperimentError(
            "Calibration reference does not exactly cover the calibration partition."
        )
    reference_by_cell = {
        item.cell_id: item.reference_flood_extent for item in reference_cells
    }
    if normalized["reference_flood_extent"].tolist() != [
        reference_by_cell[cell_id] for cell_id in expected_ids
    ]:
        raise ControlledExperimentError(
            "Calibration reference labels differ from signed reference cells."
        )
    if len(expected_ids) != _positive_int(
        receipt["calibration_reference_count"], "calibration reference count"
    ) or _canonical_sha256(expected_ids) != _sha256(
        receipt["calibration_reference_ids_sha256"],
        "calibration_reference_ids_sha256",
    ):
        raise ControlledExperimentError(
            "Calibration reference membership differs from the receipt."
        )


def _validated_reference_cells(
    frame: pd.DataFrame,
    holdout: VerifiedSpatialHoldout,
) -> tuple[ReferenceCell, ...]:
    _require_exact_columns(frame, REFERENCE_CELL_COLUMNS, "reference-cell evidence")
    if frame.empty:
        raise ControlledExperimentError("Reference-cell evidence must not be empty.")
    normalized = frame.copy()
    normalized["cell_id"] = normalized["cell_id"].map(
        lambda value: _text(value, "reference cell_id")
    )
    if normalized["cell_id"].duplicated().any():
        raise ControlledExperimentError("Reference-cell IDs must be unique.")
    normalized = normalized.sort_values("cell_id").reset_index(drop=True)
    expected_ids = tuple(sorted(item.cell_id for item in holdout.memberships))
    if tuple(normalized["cell_id"]) != expected_ids:
        raise ControlledExperimentError(
            "Reference cells do not exactly cover signed holdout membership."
        )
    normalized["reference_flood_extent"] = _binary_series(
        normalized["reference_flood_extent"], "reference_flood_extent"
    )
    for column in ERROR_STRATA:
        normalized[column] = normalized[column].map(
            lambda value, name=column: _strict_bool(value, name)
        )
    return tuple(
        ReferenceCell(
            cell_id=str(raw["cell_id"]),
            reference_flood_extent=int(raw["reference_flood_extent"]),
            error_strata=tuple((name, bool(raw[name])) for name in ERROR_STRATA),
        )
        for raw in normalized.to_dict("records")
    )


def build_gate_receipt(
    acquisition: AcquisitionGateAssessment,
    *,
    generated_at_utc: datetime,
    reviewer_qualification_receipt_path: str | Path | None = None,
    holdout_receipt_path: str | Path | None = None,
    holdout_geometry_path: str | Path | None = None,
    holdout_grid_contract_path: str | Path | None = None,
    holdout_membership_path: str | Path | None = None,
    reference_cell_receipt_path: str | Path | None = None,
    reference_cell_evidence_path: str | Path | None = None,
    calibration_reference_path: str | Path | None = None,
    error_strata_path: str | Path | None = None,
    promotion_policy_path: str | Path | None = None,
    signing_keys: Mapping[str, bytes] | None = None,
    model_evidence_manifest_path: str | Path | None = None,
) -> dict[str, object]:
    """Build an auditable pre-execution readiness decision.

    Model outputs are deliberately not prerequisites for this receipt.  A ready
    receipt says only that the bounded model lanes may start; completed lane
    evidence is verified later by :func:`run_controlled_three_model_experiment`.
    """

    _verify_acquisition_assessment(acquisition)
    blockers = list(acquisition.blockers)
    reviewer_summary: dict[str, object] = {"status": "missing"}
    verified_reviewer: VerifiedReviewerQualification | None = None
    if reviewer_qualification_receipt_path is None:
        blockers.append("reviewer_calibration: dual-signed qualification is missing")
    else:
        try:
            reviewer = load_signed_reviewer_qualification_receipt(
                reviewer_qualification_receipt_path,
                acquisition=acquisition,
                signing_keys=signing_keys or {},
                verified_at_utc=generated_at_utc,
            )
        except (ControlledExperimentError, OSError) as exc:
            blockers.append(f"reviewer_calibration: receipt is invalid: {exc}")
        else:
            verified_reviewer = reviewer
            reviewer_summary = {
                "status": "verified",
                "file_sha256": reviewer.receipt_file_sha256,
                "manifest_sha256": reviewer.manifest_sha256,
                "reviewer_count": len(reviewer.reviewer_ids),
                "adjudicator_id": reviewer.adjudicator_id,
                "formal_review_not_before_utc": _format_utc(
                    reviewer.formal_review_not_before_utc
                ),
                "qualified_at_utc": _format_utc(reviewer.qualified_at_utc),
            }

    holdout_summary: dict[str, object] = {"status": "missing"}
    verified_holdout: VerifiedSpatialHoldout | None = None
    if (
        holdout_receipt_path is None
        or holdout_geometry_path is None
        or holdout_grid_contract_path is None
        or holdout_membership_path is None
    ):
        blockers.append(
            "spatial_holdout: signed polygon and frozen cell-membership receipt is missing"
        )
    else:
        try:
            holdout = load_spatial_holdout(
                holdout_receipt_path,
                holdout_geometry_path,
                holdout_grid_contract_path,
                holdout_membership_path,
                acquisition=acquisition,
                signing_keys=signing_keys or {},
            )
        except (ControlledExperimentError, OSError) as exc:
            blockers.append(f"spatial_holdout: receipt is invalid: {exc}")
        else:
            verified_holdout = holdout
            holdout_summary = {
                "status": "verified",
                "manifest_sha256": holdout.manifest_sha256,
                "geometry_sha256": holdout.receipt["geometry_sha256"],
                "membership_sha256": holdout.membership_sha256,
                "grid_contract_sha256": holdout.receipt["grid_contract_sha256"],
                "calibration_ids": holdout.receipt["calibration_ids"],
                "final_holdout_ids": holdout.receipt["final_holdout_ids"],
                "frozen_at_utc": holdout.receipt["frozen_at_utc"],
                "signing_key_id": holdout.receipt["signing_key_id"],
            }

    reference_summary: dict[str, object] = {"status": "missing"}
    if (
        reference_cell_receipt_path is None
        or reference_cell_evidence_path is None
        or calibration_reference_path is None
        or error_strata_path is None
    ):
        blockers.append(
            "reference_cells: signed mask-derived cells, calibration projection, "
            "or error-strata evidence is missing"
        )
    elif verified_holdout is None or verified_reviewer is None:
        blockers.append(
            "reference_cells: reviewer qualification or spatial holdout is not verified"
        )
    else:
        try:
            reference = load_signed_reference_cell_evidence(
                reference_cell_receipt_path,
                reference_cell_evidence_path,
                acquisition=acquisition,
                reviewer_qualification=verified_reviewer,
                holdout=verified_holdout,
                calibration_reference_path=calibration_reference_path,
                error_strata_path=error_strata_path,
                signing_keys=signing_keys or {},
            )
        except (ControlledExperimentError, OSError) as exc:
            blockers.append(f"reference_cells: receipt is invalid: {exc}")
        else:
            reference_summary = {
                "status": "verified",
                "receipt_file_sha256": reference.receipt_file_sha256,
                "manifest_sha256": reference.manifest_sha256,
                "evidence_file_sha256": reference.evidence_file_sha256,
                "cell_count": len(reference.cells),
                "signing_key_id": reference.signing_key_id,
            }

    policy_summary: dict[str, object] = {"status": "missing"}
    if promotion_policy_path is None:
        blockers.append("promotion_policy: signed predeclared policy is missing")
    else:
        try:
            from floodguard.model_promotion import (
                ModelPromotionError,
                load_signed_model_promotion_policy,
            )

            policy, policy_file_sha = _load_promotion_policy_snapshot(
                Path(promotion_policy_path),
                signing_keys=signing_keys or {},
                evaluated_at_utc=generated_at_utc,
                loader=load_signed_model_promotion_policy,
            )
            if (
                policy["experiment_id"] != acquisition.experiment_id
                or policy["study_area"] != acquisition.study_area
            ):
                raise ControlledExperimentError(
                    "Promotion policy scope differs from the acquisition."
                )
        except (ControlledExperimentError, ModelPromotionError, OSError) as exc:
            blockers.append(f"promotion_policy: receipt is invalid: {exc}")
        else:
            policy_summary = {
                "status": "verified",
                "file_sha256": policy_file_sha,
                "manifest_sha256": policy["manifest_sha256"],
                "policy_id": policy["policy_id"],
                "issued_at_utc": policy["issued_at_utc"],
                "expires_at_utc": policy["expires_at_utc"],
                "signing_key_id": policy["signing_key_id"],
            }

    model_summary: dict[str, object] = {"status": "not_expected_before_execution"}
    if model_evidence_manifest_path is not None:
        model_path = Path(model_evidence_manifest_path)
        if not model_path.is_file():
            model_summary = {"status": "declared_but_missing"}
        else:
            model_summary = {
                "status": "present_post_execution_unverified",
                "file_sha256": _file_sha256(model_path),
            }

    unique_blockers = sorted(set(blockers))
    ready = not unique_blockers
    payload: dict[str, object] = {
        "artifact_schema": GATE_RECEIPT_SCHEMA,
        "gate_kind": "pre_execution_readiness",
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "generated_at": _format_utc(generated_at_utc),
        "acquisition": acquisition.to_dict(),
        "reviewer_calibration": reviewer_summary,
        "spatial_holdout": holdout_summary,
        "reference_cells": reference_summary,
        "promotion_policy": policy_summary,
        "model_evidence": model_summary,
        "gate_status": "ready" if ready else "blocked",
        "processing_allowed": ready,
        "experiment_executed": False,
        "can_feed_decision_layer": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "reason_blocked": "; ".join(unique_blockers),
        "blockers": unique_blockers,
        "assumptions": [
            "A ready gate is pre-execution authorization evidence only; it does not prove a model ran.",
            "Completed model evidence is intentionally absent from readiness criteria.",
            "The three-model comparison remains non-operational and report-only.",
        ],
    }
    payload["receipt_sha256"] = _canonical_sha256(payload)
    _reject_private_paths(payload)
    return payload


def write_gate_report(
    receipt: Mapping[str, object],
    acquisition_source: pd.DataFrame | str | Path,
    *,
    json_output_path: str | Path,
    markdown_output_path: str | Path,
) -> dict[str, Path]:
    """Exclusively write a path-redacted gate receipt and human report."""

    _verify_gate_receipt(receipt)
    frame, _file_sha = _coerce_csv(acquisition_source, "acquisition manifest")
    _require_columns(frame, ACQUISITION_COLUMNS, "acquisition manifest")
    json_path = Path(json_output_path)
    markdown_path = Path(markdown_output_path)
    if json_path.suffix.lower() != ".json" or markdown_path.suffix.lower() != ".md":
        raise ControlledExperimentError("Gate outputs must be JSON and Markdown.")
    if json_path.exists() or markdown_path.exists():
        raise ControlledExperimentError(
            "Gate report outputs are immutable and already exist."
        )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    markdown_path.write_text(
        build_gate_report_markdown(receipt, frame),
        encoding="utf-8",
    )
    return {"receipt": json_path, "report": markdown_path}


def build_gate_report_markdown(
    receipt: Mapping[str, object],
    acquisition: pd.DataFrame,
) -> str:
    """Render a concise, durable explanation of passed and blocked evidence."""

    _verify_gate_receipt(receipt)
    lines = [
        "# Controlled three-model experiment gate status",
        "",
        f"Gate status: **{str(receipt['gate_status']).upper()}**",
        "",
        "FloodGuard did not run a real three-model experiment unless every gate below "
        "was cryptographically bound and verified. This report is non-operational, is "
        "not field validation, and is not an official warning.",
        "Catalog/licence approval requires an externally verifiable Ed25519 authority "
        "decision. Holdout, reference, model, and evaluation evidence require "
        "role-separated HMAC-signed internal integrity receipts; editable CSV claims "
        "are not authority.",
        "",
        "## Acquisition evidence",
        "",
        "| Role | Product ID | Checksum status | Processing allowed |",
        "| --- | --- | --- | --- |",
    ]
    for row in acquisition.sort_values("role").fillna("").to_dict("records"):
        lines.append(
            f"| {row['role']} | `{row['product_id']}` | {row['sha256_status']} | "
            f"{str(row['processing_allowed']).lower()} |"
        )
    lines.extend(["", "## Gate evidence", ""])
    for key, label in (
        ("acquisition", "Acquisition and byte integrity"),
        ("reviewer_calibration", "Reviewer calibration"),
        ("spatial_holdout", "Immutable spatial holdout"),
        ("reference_cells", "Signed qualified reference cells"),
        ("promotion_policy", "Predeclared promotion policy"),
        ("model_evidence", "Post-execution model evidence (informational)"),
    ):
        value = receipt.get(key, {"status": "missing"})
        if key == "acquisition":
            status = "ready" if value["ready"] else "blocked"
        else:
            status = value["status"]
        lines.append(f"- {label}: `{status}`")
    lines.extend(["", "## Exact blockers", ""])
    blockers = list(receipt["blockers"])
    lines.extend(f"- {blocker}" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Official-source acquisition path",
            "",
            "- Sentinel-1 products are catalogued and downloaded through the official "
            "[Copernicus Data Space OData API](https://documentation.dataspace.copernicus.eu/APIs/OData.html).",
            "- [Copernicus Data Space terms](https://dataspace.copernicus.eu/terms-and-conditions) "
            "state that Sentinel data are free, full, and open, subject to the Sentinel "
            "legal notice and attribution requirements.",
            "- [UNOSAT product 3991](https://unosat.org/products/3991) is useful event "
            "context for Mae Sai but its published PDF is preliminary analysis, not a "
            "qualified pixel-level reference mask.",
            "- The inspected Sentinel Asia / MBRSC geometry remains a reference candidate "
            "because product-specific validation, derived-metric, screenshot, redistribution, "
            "and ML-label permissions are unresolved.",
            "",
            "## Integrity finding",
            "",
            "The controlled manifest uses the independently re-hashed original SAFE pair. "
            "It does not reuse the older COG acquisition receipt: the current external COG "
            "archive bytes do not match the hashes recorded in "
            "`outputs/cdse_mae_sai_acquisition_manifest.csv`. Those COG files require "
            "controlled re-registration before any future use.",
            "",
            "Spatial evaluation membership is re-derived from descriptor-bound bytes, "
            "immutable train/calibration/final-holdout polygons, and a signed grid contract on a projected "
            "metre-based equal-area CRS. Physical cell area comes only from the grid "
            "affine determinant; the complete cell-ID, row/column, and affine-center "
            "membership must match exactly. Any relabelled, missing, out-of-polygon, "
            "boundary-ambiguous, grid-mismatched, or checksum-substituted cell fails "
            "closed. Each signed model-run receipt must bind a strict lane-specific "
            "model contract and a threshold fixed from the signed calibration partition "
            "before final-holdout evaluation.",
            "",
            f"Zero-division convention: `{ZERO_DIVISION_CONVENTION}`. Physical area error "
            "is reported in square metres as well as a finite ratio.",
            "",
            "## Decision",
            "",
            "No real training or three-model result was produced. Existing weak-reference "
            "metrics remain candidate screening evidence and are not substituted for this "
            "controlled experiment.",
            "",
            f"Receipt SHA-256: `{receipt['receipt_sha256']}`",
            "",
        ]
    )
    return "\n".join(lines)


def compare_three_model_predictions(
    predictions_by_family: Mapping[str, pd.DataFrame],
    holdout: VerifiedSpatialHoldout,
    *,
    reference_cells: VerifiedReferenceCellEvidence,
    thresholds: Mapping[str, float],
    calibration_bins: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Evaluate three models against externally signed reference-cell evidence."""

    _verify_holdout_instance(holdout)
    if set(predictions_by_family) != set(REQUIRED_MODEL_FAMILIES):
        raise ControlledExperimentError(
            "Predictions must contain exactly deterministic baseline, weak-label, and GeoAI families."
        )
    if (
        not isinstance(reference_cells, VerifiedReferenceCellEvidence)
        or reference_cells._verification_marker is not _VERIFIED_REFERENCE_MARKER
    ):
        raise ControlledExperimentError(
            "Comparison requires verified signed reference-cell evidence."
        )
    if (
        reference_cells.spatial_holdout_manifest_sha256 != holdout.manifest_sha256
        or reference_cells.spatial_holdout_membership_sha256
        != holdout.membership_sha256
        or reference_cells.grid_contract_sha256
        != holdout.receipt["grid_contract_sha256"]
    ):
        raise ControlledExperimentError(
            "Reference-cell evidence does not match signed holdout lineage."
        )
    if type(calibration_bins) is not int or calibration_bins <= 1:
        raise ControlledExperimentError(
            "calibration_bins must be an integer greater than one."
        )
    threshold_map = dict(thresholds)
    if set(threshold_map) != set(REQUIRED_MODEL_FAMILIES):
        raise ControlledExperimentError(
            "Signed thresholds must cover exactly all three model families."
        )
    for family, value in threshold_map.items():
        if family not in REQUIRED_MODEL_FAMILIES or not _bounded_probability(value):
            raise ControlledExperimentError(f"Invalid threshold for {family}.")

    membership_by_cell = {
        membership.cell_id: membership for membership in holdout.memberships
    }
    if len(membership_by_cell) != len(holdout.memberships):
        raise ControlledExperimentError("Frozen holdout contains duplicate cell IDs.")
    authoritative_cells = tuple(sorted(membership_by_cell))
    normalized: dict[str, pd.DataFrame] = {}
    for family in REQUIRED_MODEL_FAMILIES:
        frame = predictions_by_family[family].copy()
        _require_exact_columns(frame, PREDICTION_COLUMNS, f"{family} predictions")
        if frame.empty or frame["cell_id"].astype(str).duplicated().any():
            raise ControlledExperimentError(
                f"{family}: prediction cell IDs must be non-empty and unique."
            )
        frame["cell_id"] = frame["cell_id"].map(lambda value: _text(value, "cell_id"))
        frame = frame.sort_values("cell_id").reset_index(drop=True)
        cell_ids = tuple(frame["cell_id"])
        if cell_ids != authoritative_cells:
            raise ControlledExperimentError(
                f"{family}: prediction cells do not exactly match frozen membership."
            )
        for index, row in frame.iterrows():
            membership = membership_by_cell[str(row["cell_id"])]
            if (
                _text(row["spatial_group_id"], "spatial_group_id")
                != membership.spatial_group_id
                or _text(row["split"], "split") != membership.split
            ):
                raise ControlledExperimentError(
                    f"{family}: row {index} was relabelled outside frozen membership."
                )
        frame["probability_0_1"] = pd.to_numeric(
            frame["probability_0_1"], errors="coerce"
        )
        if (
            frame["probability_0_1"].isna().any()
            or not frame["probability_0_1"].map(math.isfinite).all()
            or not frame["probability_0_1"].between(0, 1).all()
        ):
            raise ControlledExperimentError(
                f"{family}: probabilities must be finite values in [0,1]."
            )
        normalized[family] = frame

    first = normalized[REQUIRED_MODEL_FAMILIES[0]]
    authoritative_splits = pd.Series(
        [membership_by_cell[cell_id].split for cell_id in authoritative_cells]
    )
    if not {"train", "calibration", "final_holdout"}.issubset(
        set(authoritative_splits)
    ):
        raise ControlledExperimentError(
            "Predictions require train, calibration, and final_holdout coverage."
        )
    final_holdout_mask = authoritative_splits.eq("final_holdout")
    expected_final_holdout_ids = {
        str(value) for value in holdout.receipt["final_holdout_ids"]
    }
    if (
        set(first.loc[final_holdout_mask, "spatial_group_id"].astype(str))
        != expected_final_holdout_ids
    ):
        raise ControlledExperimentError(
            "Prediction final-holdout IDs do not exactly match the receipt."
        )
    reference_by_cell = {cell.cell_id: cell for cell in reference_cells.cells}
    if tuple(sorted(reference_by_cell)) != authoritative_cells:
        raise ControlledExperimentError(
            "Verified reference cells do not exactly match frozen membership."
        )
    reference_frame = pd.DataFrame(
        [reference_by_cell[cell_id].to_dict() for cell_id in authoritative_cells]
    )
    truth = reference_frame.loc[
        final_holdout_mask, "reference_flood_extent"
    ].reset_index(drop=True)
    if truth.empty:
        raise ControlledExperimentError(
            "Untouched final spatial holdout contains no cells."
        )
    cell_area_m2 = _positive_float(
        holdout.receipt["cell_area_m2"], "holdout cell_area_m2"
    )

    metric_rows: list[dict[str, object]] = []
    calibration_rows: list[dict[str, object]] = []
    error_rows: list[dict[str, object]] = []
    for family in REQUIRED_MODEL_FAMILIES:
        frame = normalized[family]
        probability = frame.loc[final_holdout_mask, "probability_0_1"].reset_index(
            drop=True
        )
        threshold = float(threshold_map[family])
        prediction = probability.ge(threshold).astype(int)
        metrics = _probability_metrics(
            probability,
            truth,
            threshold=threshold,
            calibration_bins=calibration_bins,
            cell_area_m2=cell_area_m2,
        )
        metric_rows.append(
            {
                "model_family": family,
                "evaluation_split": "untouched_final_spatial_holdout",
                "holdout_group_count": len(expected_final_holdout_ids),
                "sample_count": len(truth),
                "decision_threshold": threshold,
                **metrics,
                "can_feed_decision_layer": False,
            }
        )
        calibration_rows.extend(
            _calibration_rows(family, probability, truth, calibration_bins)
        )
        category_frame = reference_frame.loc[
            final_holdout_mask, list(ERROR_STRATA)
        ].reset_index(drop=True)
        error_rows.append(
            _error_category_row(
                family=family,
                category="all",
                members=pd.Series(True, index=truth.index),
                prediction=prediction,
                truth=truth,
            )
        )
        for category in ERROR_STRATA:
            members = category_frame[category]
            error_rows.append(
                _error_category_row(
                    family=family,
                    category=category,
                    members=members,
                    prediction=prediction,
                    truth=truth,
                )
            )
    return (
        pd.DataFrame(metric_rows),
        pd.DataFrame(calibration_rows),
        pd.DataFrame(error_rows),
    )


def _load_model_lane_contract(
    path: Path,
    *,
    family: str,
    model_id: str,
    model_artifact_sha256: str,
) -> tuple[dict[str, object], str, str]:
    content = _read_stable_bytes(path, f"{family} lane contract")
    file_sha256 = hashlib.sha256(content).hexdigest()
    payload = _json_object_bytes(content, f"{family} lane contract")
    _exact_keys(
        payload,
        {
            "artifact_schema",
            "model_family",
            "model_id",
            "model_artifact_sha256",
            "floodguard_commit",
            "prediction_semantics",
            "execution_authorization_manifest_sha256",
            "configuration_frozen_at_utc",
            "lane",
        },
        f"{family} lane contract",
    )
    if payload["artifact_schema"] != MODEL_CONTRACT_SCHEMAS[family]:
        raise ControlledExperimentError(f"{family}: lane contract schema is invalid.")
    if payload["model_family"] != family or payload["model_id"] != model_id:
        raise ControlledExperimentError(
            f"{family}: lane contract identity was substituted."
        )
    if payload["model_artifact_sha256"] != model_artifact_sha256:
        raise ControlledExperimentError(
            f"{family}: lane contract model artifact changed."
        )
    commit = _text(payload["floodguard_commit"], f"{family} floodguard_commit")
    if not COMMIT_RE.fullmatch(commit):
        raise ControlledExperimentError(
            f"{family}: FloodGuard commit must be a 40-character lowercase commit."
        )
    if payload["prediction_semantics"] != "binary_flood_probability_class_1":
        raise ControlledExperimentError(f"{family}: prediction semantics are invalid.")
    _sha256(
        payload["execution_authorization_manifest_sha256"],
        f"{family} execution authorization manifest",
    )
    _timestamp(
        payload["configuration_frozen_at_utc"],
        f"{family} configuration_frozen_at_utc",
    )
    lane = payload["lane"]
    if not isinstance(lane, Mapping):
        raise ControlledExperimentError(f"{family}: lane contract must be an object.")
    if family == "deterministic_sar_baseline":
        _exact_keys(
            lane,
            {"algorithm", "feature_names", "configuration_sha256", "split_policy"},
            "deterministic SAR lane",
        )
        if lane["algorithm"] != "deterministic_sar_change_baseline":
            raise ControlledExperimentError(
                "Deterministic SAR algorithm was substituted."
            )
        _validate_feature_names(lane["feature_names"], REQUIRED_SAR_CHANNELS, family)
        if lane["split_policy"] != "immutable_spatial_holdout":
            raise ControlledExperimentError(
                "Deterministic SAR split policy is invalid."
            )
        _sha256(lane["configuration_sha256"], "deterministic SAR configuration")
    elif family == "weak_label_logistic":
        _exact_keys(
            lane,
            {
                "algorithm",
                "feature_names",
                "preprocessing",
                "configuration_sha256",
                "split_policy",
            },
            "weak-label logistic lane",
        )
        if lane["algorithm"] != "logistic_regression":
            raise ControlledExperimentError(
                "Weak-label model must be logistic regression."
            )
        _validate_feature_names(lane["feature_names"], None, family)
        if lane["preprocessing"] != "training_fold_only_standardization":
            raise ControlledExperimentError("Weak-label preprocessing was substituted.")
        if lane["split_policy"] != "grouped_spatial":
            raise ControlledExperimentError("Weak-label split policy is invalid.")
        _sha256(lane["configuration_sha256"], "weak-label configuration")
    else:
        _exact_keys(
            lane,
            {
                "geoai_version",
                "geoai_commit",
                "architecture",
                "encoder",
                "encoder_weights",
                "channel_names",
                "preprocessing",
                "isolated_environment_manifest_sha256",
                "run_contract_sha256",
            },
            "GeoAI lane",
        )
        if lane["geoai_version"] != EXPECTED_GEOAI_VERSION:
            raise ControlledExperimentError("GeoAI version must be pinned to 0.41.1.")
        if lane["geoai_commit"] != EXPECTED_GEOAI_COMMIT:
            raise ControlledExperimentError(
                "GeoAI reviewed source commit was substituted."
            )
        if lane["architecture"] not in {"unet", "fpn"}:
            raise ControlledExperimentError("GeoAI architecture must be U-Net or FPN.")
        _text(lane["encoder"], "GeoAI encoder")
        if lane["encoder_weights"] is not None:
            raise ControlledExperimentError(
                "SAR GeoAI candidates must start with encoder_weights=None."
            )
        channel_names = _validate_feature_names(
            lane["channel_names"], None, "geoai_candidate"
        )
        if (
            not 6 <= len(channel_names) <= 8
            or tuple(channel_names[:6]) != REQUIRED_SAR_CHANNELS
        ):
            raise ControlledExperimentError(
                "GeoAI channels must contain the ordered six-band SAR stack plus optional terrain/water bands."
            )
        if len(channel_names) >= 7 and channel_names[6] not in {"slope", "hand"}:
            raise ControlledExperimentError(
                "GeoAI seventh channel must be slope or HAND."
            )
        if len(channel_names) == 8 and channel_names[7] != "permanent_water":
            raise ControlledExperimentError(
                "GeoAI eighth channel must be permanent water."
            )
        preprocessing = lane["preprocessing"]
        if not isinstance(preprocessing, Mapping):
            raise ControlledExperimentError("GeoAI preprocessing contract is required.")
        _exact_keys(
            preprocessing,
            {"method", "value_domain", "sidecar_sha256"},
            "GeoAI preprocessing",
        )
        if (
            preprocessing["method"] != "fixed_clip_scale_to_uint8"
            or preprocessing["value_domain"] != "uint8_0_255"
        ):
            raise ControlledExperimentError(
                "GeoAI preprocessing must explicitly encode physical bands to uint8."
            )
        _sha256(preprocessing["sidecar_sha256"], "GeoAI preprocessing sidecar")
        _sha256(
            lane["isolated_environment_manifest_sha256"],
            "GeoAI isolated environment manifest",
        )
        _sha256(lane["run_contract_sha256"], "GeoAI run contract")
    _reject_private_paths(payload)
    return payload, file_sha256, _canonical_sha256(payload)


def _validate_feature_names(
    value: object,
    expected: Sequence[str] | None,
    label: str,
) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ControlledExperimentError(f"{label}: feature names are required.")
    names = [_text(item, f"{label} feature name") for item in value]
    if len(set(names)) != len(names):
        raise ControlledExperimentError(f"{label}: feature names must be unique.")
    if expected is not None and tuple(names) != tuple(expected):
        raise ControlledExperimentError(f"{label}: feature order was substituted.")
    return names


def _validated_runtime_profile(value: Mapping[str, object]) -> dict[str, object]:
    """Validate a small, portable runtime/resource record for one model lane."""

    _exact_keys(value, set(RUNTIME_PROFILE_FIELDS), "runtime profile")
    numbers: dict[str, float] = {}
    for field in RUNTIME_PROFILE_FIELDS[:5]:
        raw = value[field]
        if isinstance(raw, bool):
            raise ControlledExperimentError(
                f"runtime profile {field} must be a finite number."
            )
        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise ControlledExperimentError(
                f"runtime profile {field} must be a finite number."
            ) from exc
        if not math.isfinite(number) or number < 0:
            raise ControlledExperimentError(
                f"runtime profile {field} must be non-negative and finite."
            )
        numbers[field] = number
    if (
        numbers["inference_seconds"] <= 0
        or numbers["total_seconds"] <= 0
        or numbers["peak_memory_mb"] <= 0
    ):
        raise ControlledExperimentError(
            "Runtime inference, total time, and peak memory must be positive."
        )
    measured = (
        numbers["training_seconds"]
        + numbers["calibration_seconds"]
        + numbers["inference_seconds"]
    )
    if numbers["total_seconds"] + 1e-9 < measured:
        raise ControlledExperimentError(
            "Runtime total_seconds cannot be shorter than measured phases."
        )
    profile: dict[str, object] = {
        **numbers,
        "device": _text(value["device"], "runtime profile device"),
        "hardware_class": _text(
            value["hardware_class"], "runtime profile hardware_class"
        ),
    }
    _reject_private_paths(profile)
    return profile


def _error_category_row(
    *,
    family: str,
    category: str,
    members: pd.Series,
    prediction: pd.Series,
    truth: pd.Series,
) -> dict[str, object]:
    """Report category coverage separately from observed classification errors."""

    selected = members.astype(bool)
    count = int(selected.sum())
    reference_positive = int((truth.eq(1) & selected).sum())
    reference_negative = int((truth.eq(0) & selected).sum())
    predicted_positive = int((prediction.eq(1) & selected).sum())
    false_positive = int((prediction.eq(1) & truth.eq(0) & selected).sum())
    false_negative = int((prediction.eq(0) & truth.eq(1) & selected).sum())
    true_positive = int((prediction.eq(1) & truth.eq(1) & selected).sum())
    measured = count > 0
    return {
        "model_family": family,
        "category": category,
        "coverage_status": (
            "measured" if measured else "not_measured_insufficient_coverage"
        ),
        "cell_count": count,
        "reference_positive_count": reference_positive,
        "reference_negative_count": reference_negative,
        "false_positive_count": false_positive,
        "false_negative_count": false_negative,
        "false_positive_rate": (
            _ratio(false_positive, reference_negative) if reference_negative else None
        ),
        "false_negative_rate": (
            _ratio(false_negative, reference_positive) if reference_positive else None
        ),
        "precision": (
            _ratio(true_positive, predicted_positive) if predicted_positive else None
        ),
        "recall": (
            _ratio(true_positive, reference_positive) if reference_positive else None
        ),
    }


def write_signed_model_run_manifest(
    *,
    model_id: str,
    model_family: str,
    model_artifact_path: str | Path,
    model_contract_path: str | Path,
    prediction_path: str | Path,
    acquisition: AcquisitionGateAssessment,
    reviewer_qualification: VerifiedReviewerQualification,
    holdout: VerifiedSpatialHoldout,
    reference_cells: VerifiedReferenceCellEvidence,
    calibration_reference: VerifiedCalibrationReference,
    execution_authorization: VerifiedExecutionAuthorization,
    threshold_selection_receipt_path: str | Path,
    calibration_prediction_path: str | Path,
    runtime_profile: Mapping[str, object],
    inference_started_at_utc: datetime,
    completed_at_utc: datetime,
    assumptions: str,
    signing_keys: Mapping[str, bytes],
    signing_key_id: str,
    signing_key: bytes,
    output_path: str | Path,
) -> dict[str, object]:
    """Bind final inference only after a reproducible calibration threshold."""

    _verify_acquisition_assessment(acquisition)
    from floodguard.controlled_threshold import (
        load_signed_threshold_selection_receipt,
    )

    family = _text(model_family, "model_family")
    contract_schema = MODEL_CONTRACT_SCHEMAS.get(family)
    if contract_schema is None:
        raise ControlledExperimentError("Unsupported controlled model family.")
    if not acquisition.ready or acquisition.authority_receipt_sha256 is None:
        raise ControlledExperimentError(
            "A signed, ready acquisition authority is required for a model run."
        )
    _verify_execution_prerequisites(
        acquisition=acquisition,
        reviewer_qualification=reviewer_qualification,
        holdout=holdout,
        reference_cells=reference_cells,
    )
    if (
        calibration_reference._verification_marker
        is not _VERIFIED_CALIBRATION_REFERENCE_MARKER
        or calibration_reference.reference_manifest_sha256
        != reference_cells.manifest_sha256
        or execution_authorization._verification_marker
        is not _VERIFIED_EXECUTION_AUTHORIZATION_MARKER
        or execution_authorization.reference_cell_manifest_sha256
        != reference_cells.manifest_sha256
    ):
        raise ControlledExperimentError(
            "Calibration, reference, or execution authorization lineage differs."
        )
    completed = _timestamp(_format_utc(completed_at_utc), "completed_at_utc")
    inference_started = _timestamp(
        _format_utc(inference_started_at_utc), "inference_started_at_utc"
    )
    artifact = Path(model_artifact_path)
    if not artifact.is_file():
        raise ControlledExperimentError("Model artifact is missing.")
    artifact_sha256 = _file_sha256(artifact)
    model_contract = Path(model_contract_path)
    contract_payload, contract_file_sha256, contract_sha256 = _load_model_lane_contract(
        model_contract,
        family=family,
        model_id=_text(model_id, "model_id"),
        model_artifact_sha256=artifact_sha256,
    )
    threshold, threshold_file_sha = load_signed_threshold_selection_receipt(
        threshold_selection_receipt_path,
        model_id=_text(model_id, "model_id"),
        model_family=family,
        model_artifact_path=artifact,
        model_contract_path=model_contract,
        calibration_prediction_path=calibration_prediction_path,
        acquisition=acquisition,
        reviewer_qualification=reviewer_qualification,
        holdout=holdout,
        calibration_reference=calibration_reference,
        execution_authorization=execution_authorization,
        signing_keys=signing_keys,
    )
    selected = _timestamp(threshold["selected_at_utc"], "threshold selected_at_utc")
    if not (
        selected < inference_started <= completed
        and completed <= execution_authorization.expires_at_utc
    ):
        raise ControlledExperimentError(
            "Final inference must follow threshold selection and finish before authorization expiry."
        )
    if threshold["signing_key_id"] != signing_key_id:
        raise ControlledExperimentError(
            "Threshold and model-run receipts must use the same model-executor identity."
        )
    prediction = Path(prediction_path)
    prediction_frame, prediction_sha = _read_csv_snapshot(
        prediction, f"{family} prediction"
    )
    _require_exact_columns(prediction_frame, PREDICTION_COLUMNS, f"{family} prediction")
    if prediction_frame.empty:
        raise ControlledExperimentError(f"{family}: prediction CSV must not be empty.")
    payload: dict[str, object] = {
        "artifact_schema": MODEL_RUN_SCHEMA,
        "model_contract_schema": contract_schema,
        "model_id": _text(model_id, "model_id"),
        "model_family": family,
        "model_artifact_file": artifact.name,
        "model_artifact_sha256": artifact_sha256,
        "model_contract_file": model_contract.name,
        "model_contract_file_sha256": contract_file_sha256,
        "model_contract_sha256": contract_sha256,
        "floodguard_commit": contract_payload["floodguard_commit"],
        "prediction_file": prediction.name,
        "prediction_sha256": prediction_sha,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": (acquisition.authority_receipt_sha256),
        "reference_mask_sha256": acquisition.reference_mask_sha256,
        "reviewer_qualification_receipt_file_sha256": (
            reviewer_qualification.receipt_file_sha256
        ),
        "reviewer_qualification_manifest_sha256": (
            reviewer_qualification.manifest_sha256
        ),
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "training_partition_sha256": holdout.training_partition_sha256,
        "calibration_partition_sha256": holdout.calibration_partition_sha256,
        "final_holdout_partition_sha256": (holdout.final_holdout_partition_sha256),
        "reference_cell_receipt_file_sha256": reference_cells.receipt_file_sha256,
        "reference_cell_manifest_sha256": reference_cells.manifest_sha256,
        "reference_cell_evidence_sha256": reference_cells.evidence_file_sha256,
        "execution_authorization_receipt_file_sha256": (
            execution_authorization.receipt_file_sha256
        ),
        "execution_authorization_manifest_sha256": (
            execution_authorization.manifest_sha256
        ),
        "threshold_selection_receipt_file": Path(threshold_selection_receipt_path).name,
        "threshold_selection_receipt_file_sha256": threshold_file_sha,
        "threshold_selection_manifest_sha256": threshold["manifest_sha256"],
        "calibration_prediction_file_sha256": threshold[
            "calibration_prediction_sha256"
        ],
        "decision_threshold": float(threshold["selected_threshold"]),
        "runtime_profile": _validated_runtime_profile(runtime_profile),
        "runtime_evidence_status": "operator_reported_signed_not_process_measured",
        "execution_started_at_utc": threshold["execution_started_at_utc"],
        "training_started_at_utc": threshold["training_started_at_utc"],
        "training_completed_at_utc": threshold["training_completed_at_utc"],
        "threshold_selected_at_utc": _format_utc(selected),
        "threshold_selection_scope": "verified_calibration_projection_only",
        "final_holdout_evaluated_during_threshold_selection": False,
        "inference_started_at_utc": _format_utc(inference_started),
        "completed_at_utc": _format_utc(completed),
        "execution_status": "completed",
        "spatial_holdout_untouched": True,
        "can_feed_decision_layer": False,
        "official_warning": False,
        "signing_role": SIGNING_ROLES["model"],
        "assumptions": _text(assumptions, "assumptions"),
    }
    sealed = _seal_signed_payload(
        payload,
        signing_key_id=signing_key_id,
        signing_key=signing_key,
        self_hash_field="manifest_sha256",
    )
    _write_immutable_json(sealed, Path(output_path), "Model run manifest")
    return sealed


def run_controlled_three_model_experiment(
    *,
    acquisition_manifest_path: str | Path,
    acquisition_artifact_paths: Mapping[str, str | Path],
    acquisition_authority_receipt_path: str | Path,
    reviewer_qualification_receipt_path: str | Path,
    holdout_receipt_path: str | Path,
    holdout_geometry_path: str | Path,
    holdout_grid_contract_path: str | Path,
    holdout_membership_path: str | Path,
    reference_cell_receipt_path: str | Path,
    reference_cell_evidence_path: str | Path,
    calibration_reference_path: str | Path,
    error_strata_path: str | Path,
    promotion_policy_path: str | Path,
    execution_authorization_receipt_path: str | Path,
    model_evidence_manifest_path: str | Path,
    prediction_paths: Mapping[str, str | Path],
    calibration_prediction_paths: Mapping[str, str | Path],
    threshold_selection_receipt_paths: Mapping[str, str | Path],
    model_artifact_paths: Mapping[str, str | Path],
    model_contract_paths: Mapping[str, str | Path],
    model_run_manifest_paths: Mapping[str, str | Path],
    signing_keys: Mapping[str, bytes],
    external_authority_public_keys: Mapping[str, bytes],
    result_signing_key_id: str,
    output_directory: str | Path,
    result_expires_at_utc: datetime,
) -> dict[str, Path]:
    """Re-verify every receipt, compare three models, and write small results."""

    evaluation_started = datetime.now(UTC)
    acquisition = assess_acquisition_manifest(
        acquisition_manifest_path,
        artifact_paths=acquisition_artifact_paths,
        authority_receipt_path=acquisition_authority_receipt_path,
        signing_keys=signing_keys,
        external_authority_public_keys=external_authority_public_keys,
        verified_at_utc=evaluation_started,
    )
    if not acquisition.ready:
        raise ControlledExperimentError(
            "Controlled experiment is blocked by acquisition gates: "
            + "; ".join(acquisition.blockers)
        )
    reviewer = load_signed_reviewer_qualification_receipt(
        reviewer_qualification_receipt_path,
        acquisition=acquisition,
        signing_keys=signing_keys,
        verified_at_utc=evaluation_started,
    )
    holdout = load_spatial_holdout(
        holdout_receipt_path,
        holdout_geometry_path,
        holdout_grid_contract_path,
        holdout_membership_path,
        acquisition=acquisition,
        signing_keys=signing_keys,
    )
    if holdout.receipt["experiment_id"] != acquisition.experiment_id:
        raise ControlledExperimentError("Holdout belongs to a different experiment.")
    if holdout.receipt["study_area"] != acquisition.study_area:
        raise ControlledExperimentError("Holdout belongs to a different study area.")
    reference_cells = load_signed_reference_cell_evidence(
        reference_cell_receipt_path,
        reference_cell_evidence_path,
        acquisition=acquisition,
        reviewer_qualification=reviewer,
        holdout=holdout,
        calibration_reference_path=calibration_reference_path,
        error_strata_path=error_strata_path,
        signing_keys=signing_keys,
    )
    calibration_reference = load_signed_calibration_reference_evidence(
        reference_cell_receipt_path,
        calibration_reference_path,
        acquisition=acquisition,
        reviewer_qualification=reviewer,
        holdout=holdout,
        signing_keys=signing_keys,
    )
    execution_authorization = load_signed_execution_authorization_receipt(
        execution_authorization_receipt_path,
        acquisition=acquisition,
        reviewer_qualification=reviewer,
        holdout=holdout,
        reference_cells=reference_cells,
        promotion_policy_path=promotion_policy_path,
        signing_keys=signing_keys,
        verified_at_utc=evaluation_started,
    )
    (
        model_manifest,
        model_evidence_manifest_sha256,
        predictions,
        thresholds,
        verified_models,
    ) = _load_model_evidence(
        model_evidence_manifest_path,
        prediction_paths=prediction_paths,
        calibration_prediction_paths=calibration_prediction_paths,
        threshold_selection_receipt_paths=threshold_selection_receipt_paths,
        model_artifact_paths=model_artifact_paths,
        model_contract_paths=model_contract_paths,
        model_run_manifest_paths=model_run_manifest_paths,
        acquisition=acquisition,
        reviewer_qualification=reviewer,
        holdout=holdout,
        reference_cells=reference_cells,
        calibration_reference=calibration_reference,
        execution_authorization=execution_authorization,
        signing_keys=signing_keys,
        evaluation_started_at_utc=evaluation_started,
    )
    metrics, calibration, errors = compare_three_model_predictions(
        predictions,
        holdout,
        reference_cells=reference_cells,
        thresholds=thresholds,
    )
    generated_at = datetime.now(UTC)
    result_expires_at = _timestamp(
        _format_utc(result_expires_at_utc), "result_expires_at_utc"
    )
    if result_expires_at <= generated_at:
        raise ControlledExperimentError(
            "Experiment result expiry must be after result generation."
        )
    result_key_id = _text(result_signing_key_id, "result_signing_key_id")
    result_signing_key = signing_keys.get(result_key_id)
    if not isinstance(result_signing_key, bytes) or not result_signing_key:
        raise ControlledExperimentError(
            "The result signing key is not trusted at runtime."
        )
    upstream_key_ids = {
        acquisition.authority_signing_key_id,
        reviewer.reviewer_signing_key_id,
        reviewer.adjudicator_signing_key_id,
        str(holdout.receipt["signing_key_id"]),
        reference_cells.signing_key_id,
        execution_authorization.signing_key_id,
        *(str(row["signing_key_id"]) for row in verified_models),
    }
    if result_key_id in upstream_key_ids:
        raise ControlledExperimentError(
            "Comparison result must use a distinct signing identity."
        )
    _require_distinct_trusted_credentials(
        signing_keys,
        [result_key_id, *(value for value in upstream_key_ids if value is not None)],
        label="controlled experiment signing roles",
    )
    runtime = _runtime_profile_frame(verified_models)
    output_dir = Path(output_directory)
    if output_dir.exists():
        raise ControlledExperimentError(
            "Controlled experiment output directory is immutable and already exists."
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-",
            dir=output_dir.parent,
        )
    )
    filenames = {
        "metrics": "three_model_metrics.csv",
        "calibration": "three_model_calibration.csv",
        "calibration_curve": "three_model_calibration.svg",
        "error_categories": "three_model_error_categories.csv",
        "runtime": "three_model_runtime.csv",
        "summary": "three_model_summary.md",
        "receipt": "three_model_result_receipt.json",
    }
    paths = {key: staging_dir / filename for key, filename in filenames.items()}
    try:
        metrics.to_csv(paths["metrics"], index=False, lineterminator="\n")
        calibration.to_csv(paths["calibration"], index=False, lineterminator="\n")
        paths["calibration_curve"].write_text(
            _calibration_curve_svg(calibration), encoding="utf-8"
        )
        errors.to_csv(paths["error_categories"], index=False, lineterminator="\n")
        runtime.to_csv(paths["runtime"], index=False, lineterminator="\n")
        paths["summary"].write_text(_result_summary(metrics, runtime), encoding="utf-8")
        receipt: dict[str, object] = {
            "artifact_schema": RESULT_RECEIPT_SCHEMA,
            "experiment_id": acquisition.experiment_id,
            "study_area": acquisition.study_area,
            "generated_at": _format_utc(generated_at),
            "expires_at_utc": _format_utc(result_expires_at),
            "acquisition_manifest_sha256": acquisition.manifest_sha256,
            "acquisition_authority_receipt_sha256": (
                acquisition.authority_receipt_sha256
            ),
            "reviewer_qualification_receipt_file_sha256": reviewer.receipt_file_sha256,
            "reviewer_qualification_manifest_sha256": reviewer.manifest_sha256,
            "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
            "spatial_holdout_membership_sha256": holdout.membership_sha256,
            "training_partition_sha256": holdout.training_partition_sha256,
            "calibration_partition_sha256": holdout.calibration_partition_sha256,
            "final_holdout_partition_sha256": holdout.final_holdout_partition_sha256,
            "reference_cell_receipt_file_sha256": reference_cells.receipt_file_sha256,
            "reference_cell_manifest_sha256": reference_cells.manifest_sha256,
            "reference_cell_evidence_sha256": reference_cells.evidence_file_sha256,
            "calibration_reference_file_sha256": (
                calibration_reference.calibration_file_sha256
            ),
            "execution_authorization_receipt_file_sha256": (
                execution_authorization.receipt_file_sha256
            ),
            "execution_authorization_manifest_sha256": (
                execution_authorization.manifest_sha256
            ),
            "promotion_policy_manifest_sha256": (
                execution_authorization.promotion_policy_manifest_sha256
            ),
            "model_evidence_manifest_sha256": model_evidence_manifest_sha256,
            "model_ids": sorted(model_manifest["model_id"].astype(str).tolist()),
            "models": verified_models,
            "artifacts": {
                key: {"file": path.name, "sha256": _file_sha256(path)}
                for key, path in paths.items()
                if key != "receipt"
            },
            "comparison_status": "completed_report_only",
            "processing_allowed": True,
            "experiment_executed": True,
            "can_feed_decision_layer": False,
            "official_warning": False,
            "operational_status": "non_operational",
            "signing_role": SIGNING_ROLES["result"],
            "zero_division_convention": ZERO_DIVISION_CONVENTION,
            "assumptions": [
                "All metrics use signed, geometry-derived untouched final-holdout membership.",
                "Area errors are thresholded physical square metres on a validated equal-area grid.",
                "Comparison completion does not promote any flood layer into FPPS.",
            ],
        }
        _reject_private_paths(receipt)
        sealed = _seal_signed_payload(
            receipt,
            signing_key_id=result_key_id,
            signing_key=result_signing_key,
            self_hash_field="manifest_sha256",
        )
        _write_immutable_json(sealed, paths["receipt"], "Experiment result receipt")

        staged_receipt = _json_object_bytes(
            _read_stable_bytes(paths["receipt"], "experiment result receipt"),
            "experiment result receipt",
        )
        _verify_signed_payload(
            staged_receipt,
            signing_keys,
            "experiment result receipt",
        )
        _verify_self_hash(
            staged_receipt,
            "manifest_sha256",
            "experiment result receipt",
        )
        if staged_receipt != sealed:
            raise ControlledExperimentError(
                "Experiment result receipt changed during staged publication."
            )
        for role, record in receipt["artifacts"].items():
            if _file_sha256(paths[role]) != record["sha256"]:
                raise ControlledExperimentError(
                    f"Staged {role} artifact changed before publication."
                )

        staging_dir.rename(output_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    return {key: output_dir / filename for key, filename in filenames.items()}


def _load_model_evidence(
    source: str | Path,
    *,
    prediction_paths: Mapping[str, str | Path],
    calibration_prediction_paths: Mapping[str, str | Path],
    threshold_selection_receipt_paths: Mapping[str, str | Path],
    model_artifact_paths: Mapping[str, str | Path],
    model_contract_paths: Mapping[str, str | Path],
    model_run_manifest_paths: Mapping[str, str | Path],
    acquisition: AcquisitionGateAssessment,
    reviewer_qualification: VerifiedReviewerQualification,
    holdout: VerifiedSpatialHoldout,
    reference_cells: VerifiedReferenceCellEvidence,
    calibration_reference: VerifiedCalibrationReference,
    execution_authorization: VerifiedExecutionAuthorization,
    signing_keys: Mapping[str, bytes],
    evaluation_started_at_utc: datetime,
) -> tuple[
    pd.DataFrame,
    str,
    dict[str, pd.DataFrame],
    dict[str, float],
    list[dict[str, object]],
]:
    manifest, manifest_sha256 = _read_csv_snapshot(
        Path(source), "model evidence manifest"
    )
    _require_exact_columns(
        manifest,
        MODEL_EVIDENCE_COLUMNS,
        "model evidence manifest",
    )
    if len(manifest) != len(REQUIRED_MODEL_FAMILIES):
        raise ControlledExperimentError("Model evidence requires exactly three rows.")
    manifest = manifest.fillna("").copy()
    families = tuple(str(value).strip() for value in manifest["model_family"])
    if set(families) != set(REQUIRED_MODEL_FAMILIES) or len(set(families)) != len(
        families
    ):
        raise ControlledExperimentError("Model families are incomplete or duplicated.")
    if manifest["model_id"].astype(str).duplicated().any():
        raise ControlledExperimentError("Model IDs must be unique.")
    for label, paths in (
        ("Prediction", prediction_paths),
        ("Calibration prediction", calibration_prediction_paths),
        ("Threshold-selection receipt", threshold_selection_receipt_paths),
        ("Model artifact", model_artifact_paths),
        ("Model contract", model_contract_paths),
        ("Model run manifest", model_run_manifest_paths),
    ):
        if set(paths) != set(REQUIRED_MODEL_FAMILIES):
            raise ControlledExperimentError(
                f"{label} path mapping must cover all model families."
            )
    holdout_time = _timestamp(holdout.receipt["frozen_at_utc"], "holdout frozen_at_utc")
    evaluation_started = _timestamp(
        _format_utc(evaluation_started_at_utc), "evaluation_started_at_utc"
    )
    predictions: dict[str, pd.DataFrame] = {}
    thresholds: dict[str, float] = {}
    verified_models: list[dict[str, object]] = []
    for raw in manifest.to_dict("records"):
        family = _text(raw["model_family"], "model_family")
        model_id = _text(raw["model_id"], "model_id")
        prediction_path = Path(prediction_paths[family])
        calibration_prediction_path = Path(calibration_prediction_paths[family])
        threshold_receipt_path = Path(threshold_selection_receipt_paths[family])
        artifact_path = Path(model_artifact_paths[family])
        contract_path = Path(model_contract_paths[family])
        run_path = Path(model_run_manifest_paths[family])
        if prediction_path.name != _basename(raw["prediction_file"], "prediction_file"):
            raise ControlledExperimentError(f"{family}: prediction filename mismatch.")
        prediction_frame, prediction_sha = _read_csv_snapshot(
            prediction_path, f"{family} prediction"
        )
        if prediction_sha != _sha256(
            raw["prediction_sha256"], f"{family} prediction_sha256"
        ):
            raise ControlledExperimentError(f"{family}: prediction checksum mismatch.")
        if artifact_path.name != _basename(
            raw["model_artifact_file"], "model_artifact_file"
        ):
            raise ControlledExperimentError(
                f"{family}: model artifact filename mismatch."
            )
        artifact_sha = _file_sha256(artifact_path)
        if artifact_sha != _sha256(
            raw["model_artifact_sha256"], f"{family} model_artifact_sha256"
        ):
            raise ControlledExperimentError(
                f"{family}: model artifact checksum mismatch."
            )
        if contract_path.name != _basename(
            raw["model_contract_file"], "model_contract_file"
        ):
            raise ControlledExperimentError(
                f"{family}: model contract filename mismatch."
            )
        contract_payload, contract_file_sha, contract_sha = _load_model_lane_contract(
            contract_path,
            family=family,
            model_id=model_id,
            model_artifact_sha256=artifact_sha,
        )
        if contract_file_sha != _sha256(
            raw["model_contract_file_sha256"],
            f"{family} model_contract_file_sha256",
        ) or contract_sha != _sha256(
            raw["model_contract_sha256"], f"{family} model_contract_sha256"
        ):
            raise ControlledExperimentError(
                f"{family}: model contract was substituted."
            )
        if run_path.name != _basename(
            raw["model_run_manifest_file"], "model_run_manifest_file"
        ):
            raise ControlledExperimentError(
                f"{family}: run manifest filename mismatch."
            )
        run_bytes = _read_stable_bytes(run_path, f"{family} model run manifest")
        run_file_sha = hashlib.sha256(run_bytes).hexdigest()
        if run_file_sha != _sha256(
            raw["model_run_manifest_sha256"],
            f"{family} model_run_manifest_sha256",
        ):
            raise ControlledExperimentError(
                f"{family}: run manifest checksum mismatch."
            )
        if raw["acquisition_manifest_sha256"] != acquisition.manifest_sha256:
            raise ControlledExperimentError(
                f"{family}: acquisition receipt substitution."
            )
        if raw["reference_mask_sha256"] != acquisition.reference_mask_sha256:
            raise ControlledExperimentError(f"{family}: reference-mask substitution.")
        if raw["spatial_holdout_manifest_sha256"] != holdout.manifest_sha256:
            raise ControlledExperimentError(f"{family}: spatial-holdout substitution.")
        if (
            raw["reviewer_qualification_file_sha256"]
            != reviewer_qualification.receipt_file_sha256
        ):
            raise ControlledExperimentError(
                f"{family}: reviewer-qualification substitution."
            )
        if (
            raw["execution_authorization_manifest_sha256"]
            != execution_authorization.manifest_sha256
        ):
            raise ControlledExperimentError(
                f"{family}: execution-authorization substitution."
            )
        completed = _timestamp(raw["completed_at_utc"], f"{family} completed_at_utc")
        if (
            completed < holdout_time
            or completed < reviewer_qualification.qualified_at_utc
            or completed < execution_authorization.authorized_at_utc
        ):
            raise ControlledExperimentError(
                f"{family}: model evidence predates a frozen execution prerequisite."
            )
        if str(raw["execution_status"]).strip() != "completed":
            raise ControlledExperimentError(f"{family}: execution is not completed.")
        if not _strict_bool(
            raw["spatial_holdout_untouched"], "spatial_holdout_untouched"
        ):
            raise ControlledExperimentError(f"{family}: holdout was not untouched.")
        if _strict_bool(raw["can_feed_decision_layer"], "can_feed_decision_layer"):
            raise ControlledExperimentError(
                f"{family}: comparison evidence cannot claim decision-layer promotion."
            )
        _timestamp(raw["source_timestamp"], f"{family} source_timestamp")
        _text(raw["confidence_class"], f"{family} confidence_class")
        _text(raw["assumptions"], f"{family} assumptions")
        run = _verify_model_run_manifest(
            _json_object_bytes(run_bytes, f"{family} model run manifest"),
            family=family,
            model_id=model_id,
            artifact_path=artifact_path,
            artifact_sha256=artifact_sha,
            model_contract_path=contract_path,
            model_contract_payload=contract_payload,
            model_contract_file_sha256=contract_file_sha,
            model_contract_sha256=contract_sha,
            prediction_path=prediction_path,
            prediction_sha256=prediction_sha,
            acquisition=acquisition,
            reviewer_qualification=reviewer_qualification,
            holdout=holdout,
            reference_cells=reference_cells,
            calibration_reference=calibration_reference,
            execution_authorization=execution_authorization,
            threshold_selection_receipt_path=threshold_receipt_path,
            calibration_prediction_path=calibration_prediction_path,
            signing_keys=signing_keys,
            evaluation_started_at_utc=evaluation_started,
        )
        if (
            raw["threshold_selection_manifest_sha256"]
            != run["threshold_selection_manifest_sha256"]
        ):
            raise ControlledExperimentError(
                f"{family}: threshold-selection substitution."
            )
        if run["completed_at_utc"] != _format_utc(completed):
            raise ControlledExperimentError(
                f"{family}: evidence completion time differs from signed run manifest."
            )
        threshold = float(run["decision_threshold"])
        thresholds[family] = threshold
        predictions[family] = prediction_frame
        verified_models.append(
            {
                "model_id": model_id,
                "model_family": family,
                "model_contract_schema": run["model_contract_schema"],
                "model_artifact_file": artifact_path.name,
                "model_artifact_sha256": artifact_sha,
                "model_contract_file": contract_path.name,
                "model_contract_file_sha256": contract_file_sha,
                "model_contract_sha256": contract_sha,
                "floodguard_commit": contract_payload["floodguard_commit"],
                "prediction_file": prediction_path.name,
                "prediction_sha256": prediction_sha,
                "model_run_manifest_file": run_path.name,
                "model_run_manifest_file_sha256": run_file_sha,
                "model_run_manifest_sha256": run["manifest_sha256"],
                "training_partition_sha256": run["training_partition_sha256"],
                "calibration_partition_sha256": run["calibration_partition_sha256"],
                "final_holdout_partition_sha256": run["final_holdout_partition_sha256"],
                "decision_threshold": threshold,
                "threshold_selection_receipt_file": run[
                    "threshold_selection_receipt_file"
                ],
                "threshold_selection_receipt_file_sha256": run[
                    "threshold_selection_receipt_file_sha256"
                ],
                "threshold_selection_manifest_sha256": run[
                    "threshold_selection_manifest_sha256"
                ],
                "threshold_selection_scope": run["threshold_selection_scope"],
                "runtime_profile": run["runtime_profile"],
                "runtime_evidence_status": run["runtime_evidence_status"],
                "completed_at_utc": run["completed_at_utc"],
                "signing_key_id": run["signing_key_id"],
            }
        )
    if len({str(row["floodguard_commit"]) for row in verified_models}) != 1:
        raise ControlledExperimentError(
            "All three model lane contracts must bind the same FloodGuard commit."
        )
    verified_models.sort(key=lambda row: str(row["model_family"]))
    return manifest, manifest_sha256, predictions, thresholds, verified_models


def _verify_model_run_manifest(
    payload: Mapping[str, object],
    *,
    family: str,
    model_id: str,
    artifact_path: Path,
    artifact_sha256: str,
    model_contract_path: Path,
    model_contract_payload: Mapping[str, object],
    model_contract_file_sha256: str,
    model_contract_sha256: str,
    prediction_path: Path,
    prediction_sha256: str,
    acquisition: AcquisitionGateAssessment,
    reviewer_qualification: VerifiedReviewerQualification,
    holdout: VerifiedSpatialHoldout,
    reference_cells: VerifiedReferenceCellEvidence,
    calibration_reference: VerifiedCalibrationReference,
    execution_authorization: VerifiedExecutionAuthorization,
    threshold_selection_receipt_path: str | Path,
    calibration_prediction_path: str | Path,
    signing_keys: Mapping[str, bytes],
    evaluation_started_at_utc: datetime,
) -> dict[str, object]:
    required = {
        "artifact_schema",
        "model_contract_schema",
        "model_id",
        "model_family",
        "model_artifact_file",
        "model_artifact_sha256",
        "model_contract_file",
        "model_contract_file_sha256",
        "model_contract_sha256",
        "floodguard_commit",
        "prediction_file",
        "prediction_sha256",
        "acquisition_manifest_sha256",
        "acquisition_authority_receipt_sha256",
        "reference_mask_sha256",
        "reviewer_qualification_receipt_file_sha256",
        "reviewer_qualification_manifest_sha256",
        "spatial_holdout_manifest_sha256",
        "spatial_holdout_membership_sha256",
        "reference_cell_receipt_file_sha256",
        "reference_cell_manifest_sha256",
        "reference_cell_evidence_sha256",
        "training_partition_sha256",
        "calibration_partition_sha256",
        "final_holdout_partition_sha256",
        "execution_authorization_receipt_file_sha256",
        "execution_authorization_manifest_sha256",
        "threshold_selection_receipt_file",
        "threshold_selection_receipt_file_sha256",
        "threshold_selection_manifest_sha256",
        "calibration_prediction_file_sha256",
        "decision_threshold",
        "runtime_profile",
        "runtime_evidence_status",
        "execution_started_at_utc",
        "training_started_at_utc",
        "training_completed_at_utc",
        "threshold_selected_at_utc",
        "threshold_selection_scope",
        "final_holdout_evaluated_during_threshold_selection",
        "inference_started_at_utc",
        "completed_at_utc",
        "execution_status",
        "spatial_holdout_untouched",
        "can_feed_decision_layer",
        "official_warning",
        "signing_role",
        "assumptions",
        "signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "signature",
    }
    _exact_keys(payload, required, f"{family} model run manifest")
    if payload["artifact_schema"] != MODEL_RUN_SCHEMA:
        raise ControlledExperimentError(
            f"{family}: run manifest schema is unsupported."
        )
    _verify_signed_payload(payload, signing_keys, f"{family} model run manifest")
    _verify_self_hash(payload, "manifest_sha256", f"{family} model run manifest")
    if payload["signing_role"] != SIGNING_ROLES["model"]:
        raise ControlledExperimentError(f"{family}: model-run signing role is invalid.")
    expected_contract = MODEL_CONTRACT_SCHEMAS[family]
    if payload["model_contract_schema"] != expected_contract:
        raise ControlledExperimentError(f"{family}: model contract schema mismatch.")
    if payload["model_family"] != family or payload["model_id"] != model_id:
        raise ControlledExperimentError(f"{family}: model identity was substituted.")
    if (
        payload["model_artifact_file"] != artifact_path.name
        or payload["model_artifact_sha256"] != artifact_sha256
    ):
        raise ControlledExperimentError(
            f"{family}: signed model artifact was substituted."
        )
    if (
        payload["model_contract_file"] != model_contract_path.name
        or payload["model_contract_file_sha256"] != model_contract_file_sha256
        or payload["model_contract_sha256"] != model_contract_sha256
    ):
        raise ControlledExperimentError(
            f"{family}: signed lane contract was substituted."
        )
    if payload["floodguard_commit"] != model_contract_payload["floodguard_commit"]:
        raise ControlledExperimentError(
            f"{family}: lane contract commit was substituted."
        )
    if (
        payload["prediction_file"] != prediction_path.name
        or payload["prediction_sha256"] != prediction_sha256
    ):
        raise ControlledExperimentError(f"{family}: signed prediction was substituted.")
    expected_lineage = {
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": (acquisition.authority_receipt_sha256),
        "reference_mask_sha256": acquisition.reference_mask_sha256,
        "reviewer_qualification_receipt_file_sha256": (
            reviewer_qualification.receipt_file_sha256
        ),
        "reviewer_qualification_manifest_sha256": (
            reviewer_qualification.manifest_sha256
        ),
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "reference_cell_receipt_file_sha256": reference_cells.receipt_file_sha256,
        "reference_cell_manifest_sha256": reference_cells.manifest_sha256,
        "reference_cell_evidence_sha256": reference_cells.evidence_file_sha256,
        "training_partition_sha256": holdout.training_partition_sha256,
        "calibration_partition_sha256": holdout.calibration_partition_sha256,
        "final_holdout_partition_sha256": (holdout.final_holdout_partition_sha256),
        "execution_authorization_receipt_file_sha256": (
            execution_authorization.receipt_file_sha256
        ),
        "execution_authorization_manifest_sha256": (
            execution_authorization.manifest_sha256
        ),
    }
    for field, expected in expected_lineage.items():
        if payload[field] != expected:
            raise ControlledExperimentError(
                f"{family}: signed {field} was substituted."
            )
    from floodguard.controlled_threshold import (
        load_signed_threshold_selection_receipt,
    )

    threshold, threshold_file_sha = load_signed_threshold_selection_receipt(
        threshold_selection_receipt_path,
        model_id=model_id,
        model_family=family,
        model_artifact_path=artifact_path,
        model_contract_path=model_contract_path,
        calibration_prediction_path=calibration_prediction_path,
        acquisition=acquisition,
        reviewer_qualification=reviewer_qualification,
        holdout=holdout,
        calibration_reference=calibration_reference,
        execution_authorization=execution_authorization,
        signing_keys=signing_keys,
    )
    threshold_path = Path(threshold_selection_receipt_path)
    threshold_expected = {
        "threshold_selection_receipt_file": threshold_path.name,
        "threshold_selection_receipt_file_sha256": threshold_file_sha,
        "threshold_selection_manifest_sha256": threshold["manifest_sha256"],
        "calibration_prediction_file_sha256": threshold[
            "calibration_prediction_sha256"
        ],
    }
    for field, expected in threshold_expected.items():
        if payload[field] != expected:
            raise ControlledExperimentError(
                f"{family}: signed {field} was substituted."
            )
    if not _bounded_probability(payload["decision_threshold"]):
        raise ControlledExperimentError(f"{family}: signed threshold is invalid.")
    decision_threshold = float(payload["decision_threshold"])
    if not math.isclose(
        decision_threshold,
        float(threshold["selected_threshold"]),
        abs_tol=1e-12,
    ):
        raise ControlledExperimentError(
            f"{family}: signed decision threshold differs from calibration receipt."
        )
    runtime_profile = payload["runtime_profile"]
    if not isinstance(runtime_profile, Mapping):
        raise ControlledExperimentError(f"{family}: signed runtime profile is invalid.")
    _validated_runtime_profile(runtime_profile)
    execution_started = _timestamp(
        payload["execution_started_at_utc"], f"{family} execution_started_at_utc"
    )
    training_started = _timestamp(
        payload["training_started_at_utc"], f"{family} training_started_at_utc"
    )
    training_completed = _timestamp(
        payload["training_completed_at_utc"], f"{family} training_completed_at_utc"
    )
    selected = _timestamp(
        payload["threshold_selected_at_utc"],
        f"{family} threshold_selected_at_utc",
    )
    inference_started = _timestamp(
        payload["inference_started_at_utc"], f"{family} inference_started_at_utc"
    )
    completed = _timestamp(payload["completed_at_utc"], f"{family} completed_at_utc")
    if (
        payload["execution_started_at_utc"] != threshold["execution_started_at_utc"]
        or payload["training_started_at_utc"] != threshold["training_started_at_utc"]
        or payload["training_completed_at_utc"]
        != threshold["training_completed_at_utc"]
        or payload["threshold_selected_at_utc"] != threshold["selected_at_utc"]
    ):
        raise ControlledExperimentError(
            f"{family}: signed execution chronology differs from threshold receipt."
        )
    if not (
        execution_authorization.authorized_at_utc
        <= execution_started
        <= training_started
        <= training_completed
        <= selected
        < inference_started
        <= completed
        <= execution_authorization.expires_at_utc
    ):
        raise ControlledExperimentError(
            f"{family}: signed model execution chronology is invalid."
        )
    if completed > evaluation_started_at_utc:
        raise ControlledExperimentError(
            f"{family}: signed model run completes after evaluation started."
        )
    if payload["threshold_selection_scope"] != "verified_calibration_projection_only":
        raise ControlledExperimentError(
            f"{family}: threshold selection was not calibration-only."
        )
    if payload["final_holdout_evaluated_during_threshold_selection"] is not False:
        raise ControlledExperimentError(
            f"{family}: final holdout influenced threshold selection."
        )
    if (
        payload["runtime_evidence_status"]
        != "operator_reported_signed_not_process_measured"
        or payload["signing_key_id"] != threshold["signing_key_id"]
        or payload["execution_status"] != "completed"
        or payload["spatial_holdout_untouched"] is not True
        or payload["can_feed_decision_layer"] is not False
        or payload["official_warning"] is not False
    ):
        raise ControlledExperimentError(
            f"{family}: signed run has unsafe status fields."
        )
    upstream_key_ids = [
        value
        for value in (
            acquisition.authority_signing_key_id,
            reviewer_qualification.reviewer_signing_key_id,
            reviewer_qualification.adjudicator_signing_key_id,
            str(holdout.receipt["signing_key_id"]),
            reference_cells.signing_key_id,
            execution_authorization.signing_key_id,
        )
        if value is not None
    ]
    if payload["signing_key_id"] in upstream_key_ids:
        raise ControlledExperimentError(
            f"{family}: model executor signing identity is not role-separated."
        )
    _require_distinct_trusted_credentials(
        signing_keys,
        [str(payload["signing_key_id"]), *upstream_key_ids],
        label=f"{family} controlled model run",
    )
    _text(payload["assumptions"], f"{family} assumptions")
    _reject_private_paths(payload)
    return payload


def _probability_metrics(
    probability: pd.Series,
    truth: pd.Series,
    *,
    threshold: float,
    calibration_bins: int,
    cell_area_m2: float,
) -> dict[str, float | int]:
    prediction = probability.ge(threshold).astype(int)
    tp = int((prediction.eq(1) & truth.eq(1)).sum())
    fp = int((prediction.eq(1) & truth.eq(0)).sum())
    fn = int((prediction.eq(0) & truth.eq(1)).sum())
    tn = int((prediction.eq(0) & truth.eq(0)).sum())
    predicted_area_m2 = float((tp + fp) * cell_area_m2)
    reference_area_m2 = float((tp + fn) * cell_area_m2)
    area_error_m2 = predicted_area_m2 - reference_area_m2
    signed_area_error = _ratio(area_error_m2, reference_area_m2)
    calibration = _calibration_rows("_metric", probability, truth, calibration_bins)
    ece = sum(
        float(row["sample_fraction"]) * float(row["absolute_gap"])
        for row in calibration
    )
    brier = float(((probability.astype(float) - truth.astype(float)) ** 2).mean())
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "iou": _ratio(tp, tp + fp + fn),
        "f1_dice": _ratio(2 * tp, 2 * tp + fp + fn),
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "cell_area_m2": cell_area_m2,
        "predicted_area_m2": predicted_area_m2,
        "reference_area_m2": reference_area_m2,
        "area_error_m2": area_error_m2,
        "absolute_area_error_m2": abs(area_error_m2),
        "area_error_ratio": signed_area_error,
        "absolute_area_error_ratio": round(abs(signed_area_error), 6),
        "brier_score": round(brier, 6),
        "expected_calibration_error": round(ece, 6),
    }


def _calibration_rows(
    family: str,
    probability: pd.Series,
    truth: pd.Series,
    bins: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    total = len(probability)
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        members = probability.ge(lower) & (
            probability.le(upper) if index == bins - 1 else probability.lt(upper)
        )
        count = int(members.sum())
        if count:
            mean_probability = float(probability[members].mean())
            observed_rate = float(truth[members].mean())
            absolute_gap = abs(mean_probability - observed_rate)
        else:
            mean_probability = observed_rate = absolute_gap = 0.0
        rows.append(
            {
                "model_family": family,
                "bin_index": index,
                "bin_lower": lower,
                "bin_upper": upper,
                "sample_count": count,
                "sample_fraction": round(count / total, 6),
                "mean_probability": round(mean_probability, 6),
                "observed_flood_rate": round(observed_rate, 6),
                "absolute_gap": round(absolute_gap, 6),
            }
        )
    return rows


def _runtime_profile_frame(
    verified_models: Sequence[Mapping[str, object]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for model in verified_models:
        family = _text(model.get("model_family"), "runtime model_family")
        model_id = _text(model.get("model_id"), "runtime model_id")
        raw_profile = model.get("runtime_profile")
        if not isinstance(raw_profile, Mapping):
            raise ControlledExperimentError(
                f"{family}: verified runtime profile is missing."
            )
        profile = _validated_runtime_profile(raw_profile)
        rows.append({"model_family": family, "model_id": model_id, **profile})
    frame = pd.DataFrame(
        rows,
        columns=("model_family", "model_id", *RUNTIME_PROFILE_FIELDS),
    ).sort_values("model_family", ignore_index=True)
    if set(frame["model_family"]) != set(REQUIRED_MODEL_FAMILIES):
        raise ControlledExperimentError(
            "Runtime profiles must cover exactly all three model families."
        )
    return frame


def _calibration_curve_svg(calibration: pd.DataFrame) -> str:
    """Render an offline, accessible reliability curve from verified bins."""

    required = {
        "model_family",
        "bin_index",
        "sample_count",
        "mean_probability",
        "observed_flood_rate",
    }
    if not required.issubset(calibration.columns):
        raise ControlledExperimentError(
            "Calibration rows cannot render the required reliability curve."
        )
    width, height = 840, 540
    left, top, plot_width, plot_height = 90, 55, 650, 390

    def point(x_value: float, y_value: float) -> tuple[float, float]:
        return (
            left + max(0.0, min(1.0, x_value)) * plot_width,
            top + (1.0 - max(0.0, min(1.0, y_value))) * plot_height,
        )

    styles = {
        "deterministic_sar_baseline": ("#075985", ""),
        "weak_label_logistic": ("#0f766e", "8 4"),
        "geoai_candidate": ("#c2410c", "3 4"),
    }
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
            'aria-labelledby="title description">'
        ),
        '<title id="title">Three-model probability calibration curves</title>',
        (
            '<desc id="description">Observed final-holdout flood rate versus mean '
            "predicted class-1 probability. The diagonal line is ideal calibration.</desc>"
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        (
            f'<rect x="{left}" y="{top}" width="{plot_width}" '
            f'height="{plot_height}" fill="#f8fafc" stroke="#64748b"/>'
        ),
    ]
    for index in range(6):
        value = index / 5
        x, y = point(value, value)
        lines.extend(
            [
                (
                    f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" '
                    f'y2="{top + plot_height}" stroke="#e2e8f0"/>'
                ),
                (
                    f'<line x1="{left}" y1="{y:.1f}" '
                    f'x2="{left + plot_width}" y2="{y:.1f}" '
                    'stroke="#e2e8f0"/>'
                ),
                (
                    f'<text x="{x:.1f}" y="{top + plot_height + 26}" '
                    'text-anchor="middle" font-size="13" fill="#334155">'
                    f"{value:.1f}</text>"
                ),
                (
                    f'<text x="{left - 18}" y="{y + 4:.1f}" '
                    'text-anchor="end" font-size="13" fill="#334155">'
                    f"{value:.1f}</text>"
                ),
            ]
        )
    ideal_start = point(0, 0)
    ideal_end = point(1, 1)
    lines.append(
        f'<line x1="{ideal_start[0]:.1f}" y1="{ideal_start[1]:.1f}" '
        f'x2="{ideal_end[0]:.1f}" y2="{ideal_end[1]:.1f}" '
        'stroke="#475569" stroke-width="2" stroke-dasharray="6 5"/>'
    )
    for family in REQUIRED_MODEL_FAMILIES:
        family_rows = calibration.loc[
            calibration["model_family"].eq(family)
            & pd.to_numeric(calibration["sample_count"], errors="coerce").gt(0)
        ].sort_values("bin_index")
        coordinates = [
            point(float(row["mean_probability"]), float(row["observed_flood_rate"]))
            for row in family_rows.to_dict("records")
        ]
        if not coordinates:
            raise ControlledExperimentError(
                f"{family}: calibration curve has no populated bins."
            )
        color, dash = styles[family]
        dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in coordinates)
        lines.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" '
            f'stroke-width="3"{dash_attribute}/>'
        )
        lines.extend(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#ffffff" '
            f'stroke="{color}" stroke-width="2"/>'
            for x, y in coordinates
        )
    lines.extend(
        [
            (
                f'<text x="{left + plot_width / 2:.1f}" y="{height - 30}" '
                'text-anchor="middle" font-size="15" fill="#0f172a">'
                "Mean predicted flood probability</text>"
            ),
            (
                f'<text x="24" y="{top + plot_height / 2:.1f}" '
                'text-anchor="middle" font-size="15" fill="#0f172a" '
                f'transform="rotate(-90 24 {top + plot_height / 2:.1f})">'
                "Observed flood rate</text>"
            ),
        ]
    )
    legend_y = 72
    for family in REQUIRED_MODEL_FAMILIES:
        color, dash = styles[family]
        dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
        lines.append(
            f'<line x1="760" y1="{legend_y}" x2="790" y2="{legend_y}" '
            f'stroke="{color}" stroke-width="3"{dash_attribute}/>'
        )
        lines.append(
            f'<text x="755" y="{legend_y + 5}" text-anchor="end" '
            f'font-size="12" fill="#0f172a">{family}</text>'
        )
        legend_y += 30
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _result_summary(metrics: pd.DataFrame, runtime: pd.DataFrame) -> str:
    lines = [
        "# Controlled three-model experiment",
        "",
        "Status: completed report-only comparison on one untouched final spatial holdout.",
        "",
        "This output is non-operational, not an official warning, and cannot feed "
        "the FloodGuard decision layer without a separate promotion review.",
        "",
        "| Model | IoU | Dice/F1 | Precision | Recall | Area error m2 | Area error ratio | Brier | ECE |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in metrics.to_dict("records"):
        lines.append(
            f"| {row['model_family']} | {row['iou']:.6f} | {row['f1_dice']:.6f} | "
            f"{row['precision']:.6f} | {row['recall']:.6f} | "
            f"{row['area_error_m2']:.6f} | {row['area_error_ratio']:.6f} | "
            f"{row['brier_score']:.6f} | "
            f"{row['expected_calibration_error']:.6f} |"
        )
    lines.extend(
        [
            "",
            "Error-category counts and reliability bins are provided in separate CSV files. "
            "Error strata may overlap (for example, an urban cell may also be permanent "
            "water), so category counts must not be summed as mutually exclusive totals.",
            "",
            f"Zero-division convention: {ZERO_DIVISION_CONVENTION}.",
            "Area error is thresholded physical area on the signed equal-area cell grid.",
            "",
            "## Runtime and resources",
            "",
            "| Model | Training s | Calibration s | Inference s | Total s | Peak MB | Device | Hardware class |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in runtime.to_dict("records"):
        lines.append(
            f"| {row['model_family']} | {row['training_seconds']:.6f} | "
            f"{row['calibration_seconds']:.6f} | {row['inference_seconds']:.6f} | "
            f"{row['total_seconds']:.6f} | {row['peak_memory_mb']:.6f} | "
            f"{row['device']} | {row['hardware_class']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _load_spatial_groups(
    path: Path,
    *,
    expected_crs: str,
) -> tuple[list[dict[str, object]], list[tuple[str, str, Any]], str]:
    content = _read_stable_bytes(path, "spatial holdout GeoJSON")
    payload = _json_object_bytes(content, "spatial holdout GeoJSON")
    if payload.get("type") != "FeatureCollection" or not isinstance(
        payload.get("features"), list
    ):
        raise ControlledExperimentError(
            "Holdout geometry must be a GeoJSON FeatureCollection."
        )
    declared_crs = payload.get("floodguard_crs")
    if not isinstance(declared_crs, str) or not EPSG_RE.fullmatch(declared_crs):
        raise ControlledExperimentError(
            "Holdout GeoJSON requires an explicit top-level floodguard_crs EPSG identifier."
        )
    if declared_crs.upper() != expected_crs.upper():
        raise ControlledExperimentError(
            "Holdout GeoJSON CRS does not match the experiment target CRS."
        )
    try:
        from shapely.geometry import shape
    except ImportError as exc:
        raise ControlledExperimentError(
            "Spatial holdout validation requires the FloodGuard geo extra (Shapely)."
        ) from exc
    records: list[tuple[dict[str, object], Any]] = []
    seen: set[str] = set()
    for feature in payload["features"]:
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise ControlledExperimentError(
                "Holdout GeoJSON contains a malformed feature."
            )
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            raise ControlledExperimentError("Holdout feature properties are required.")
        group_id = _text(properties.get("spatial_group_id"), "spatial_group_id")
        split = _text(properties.get("split"), "split")
        if split not in {"train", "calibration", "final_holdout"}:
            raise ControlledExperimentError(
                "Holdout feature split must be train, calibration, or final_holdout."
            )
        if group_id in seen:
            raise ControlledExperimentError("Spatial group IDs must be unique.")
        seen.add(group_id)
        try:
            geometry = shape(feature.get("geometry"))
        except (TypeError, ValueError) as exc:
            raise ControlledExperimentError(
                "Holdout feature geometry is invalid."
            ) from exc
        if (
            geometry.is_empty
            or not geometry.is_valid
            or geometry.geom_type not in {"Polygon", "MultiPolygon"}
            or geometry.area <= 0
        ):
            raise ControlledExperimentError(
                "Holdout features must be valid non-empty Polygon/MultiPolygon geometries."
            )
        bounds = [round(float(value), 9) for value in geometry.bounds]
        record = {
            "spatial_group_id": group_id,
            "split": split,
            "bounds": bounds,
            "geometry_sha256": _canonical_sha256(feature["geometry"]),
        }
        records.append((record, geometry))
    if len(records) < 2:
        raise ControlledExperimentError("Holdout GeoJSON requires at least two groups.")
    for index, (_first_record, first) in enumerate(records):
        for _second_record, second in records[index + 1 :]:
            if first.intersection(second).area > 0:
                raise ControlledExperimentError("Spatial partition interiors overlap.")
    records.sort(key=lambda item: str(item[0]["spatial_group_id"]))
    public_records = [record for record, _geometry in records]
    geometries = [
        (str(record["spatial_group_id"]), str(record["split"]), geometry)
        for record, geometry in records
    ]
    return public_records, geometries, hashlib.sha256(content).hexdigest()


def _validate_equal_area_crs(value: str) -> None:
    try:
        from pyproj import CRS
    except ImportError as exc:
        raise ControlledExperimentError(
            "Equal-area holdout validation requires the FloodGuard geo extra (pyproj)."
        ) from exc
    try:
        crs = CRS.from_user_input(value)
    except Exception as exc:  # pragma: no cover - pyproj exception types vary
        raise ControlledExperimentError("target_crs is not a valid CRS.") from exc
    operation = crs.coordinate_operation
    method = "" if operation is None else str(operation.method_name).lower()
    metre_axes = bool(crs.axis_info) and all(
        math.isclose(float(axis.unit_conversion_factor or 0.0), 1.0, abs_tol=1e-12)
        for axis in crs.axis_info
    )
    if not crs.is_projected or not metre_axes or "equal area" not in method:
        raise ControlledExperimentError(
            "target_crs must be a projected metre-based equal-area CRS."
        )


def _load_grid_contract(
    path: Path,
    *,
    expected_sha256: str,
    expected_crs: str,
) -> VerifiedGridContract:
    content = _read_stable_bytes(path, "equal-area grid contract")
    file_sha256 = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(file_sha256, expected_sha256):
        raise ControlledExperimentError("Grid contract SHA-256 was substituted.")
    payload = _json_object_bytes(content, "equal-area grid contract")
    _exact_keys(
        payload,
        {
            "artifact_schema",
            "grid_id",
            "target_crs",
            "transform",
            "width",
            "height",
            "cell_ids_sha256",
            "source_grid_sha256",
            "created_at_utc",
            "official_warning",
        },
        "equal-area grid contract",
    )
    if payload["artifact_schema"] != GRID_CONTRACT_SCHEMA:
        raise ControlledExperimentError(
            "Equal-area grid contract schema is unsupported."
        )
    _text(payload["grid_id"], "grid contract grid_id")
    target_crs = _text(payload["target_crs"], "grid contract target_crs").upper()
    if target_crs != expected_crs.upper():
        raise ControlledExperimentError("Grid contract CRS does not match holdout CRS.")
    _validate_equal_area_crs(target_crs)
    transform_value = payload["transform"]
    if not isinstance(transform_value, list) or len(transform_value) != 6:
        raise ControlledExperimentError(
            "Grid contract transform must contain six values."
        )
    transform: list[float] = []
    for value in transform_value:
        if isinstance(value, bool):
            raise ControlledExperimentError("Grid contract transform must be finite.")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ControlledExperimentError(
                "Grid contract transform must be finite."
            ) from exc
        if not math.isfinite(number):
            raise ControlledExperimentError("Grid contract transform must be finite.")
        transform.append(number)
    width = _positive_int(payload["width"], "grid contract width")
    height = _positive_int(payload["height"], "grid contract height")
    contract = VerifiedGridContract(
        file_name=path.name,
        file_sha256=file_sha256,
        target_crs=target_crs,
        transform=tuple(transform),  # type: ignore[arg-type]
        width=width,
        height=height,
        cell_ids_sha256=_sha256(
            payload["cell_ids_sha256"], "grid contract cell_ids_sha256"
        ),
    )
    if not math.isfinite(contract.cell_area_m2) or contract.cell_area_m2 <= 0:
        raise ControlledExperimentError(
            "Grid affine determinant must define a positive physical cell area."
        )
    _sha256(payload["source_grid_sha256"], "grid contract source_grid_sha256")
    _timestamp(payload["created_at_utc"], "grid contract created_at_utc")
    if payload["official_warning"] is not False:
        raise ControlledExperimentError(
            "Grid contract cannot claim an official warning."
        )
    _reject_private_paths(payload)
    return contract


def _read_cell_grid(path: Path, *, grid_contract: VerifiedGridContract) -> pd.DataFrame:
    frame, _file_sha = _coerce_csv(path, "cell grid")
    _require_exact_columns(frame, CELL_GRID_COLUMNS, "cell grid")
    if frame.empty:
        raise ControlledExperimentError("Cell grid must not be empty.")
    return _validate_cell_grid_frame(
        frame, grid_contract=grid_contract, label="Cell grid"
    )


def _read_frozen_membership(
    path: Path,
    *,
    grid_contract: VerifiedGridContract,
) -> tuple[tuple[FrozenCellMembership, ...], str]:
    frame, file_sha = _read_csv_snapshot(path, "frozen holdout membership")
    _require_exact_columns(
        frame,
        HOLDOUT_MEMBERSHIP_COLUMNS,
        "frozen holdout membership",
    )
    grid = _validate_cell_grid_frame(
        frame,
        grid_contract=grid_contract,
        label="Frozen membership",
    )
    memberships: list[FrozenCellMembership] = []
    for raw in grid.to_dict("records"):
        group_id = _text(raw["spatial_group_id"], "spatial_group_id")
        split = _text(raw["split"], "split")
        if split not in {"train", "calibration", "final_holdout"}:
            raise ControlledExperimentError("Frozen membership split is invalid.")
        memberships.append(
            FrozenCellMembership(
                cell_id=str(raw["cell_id"]),
                x=float(raw["x"]),
                y=float(raw["y"]),
                row_index=int(raw["row_index"]),
                column_index=int(raw["column_index"]),
                cell_area_m2=float(raw["cell_area_m2"]),
                grid_contract_sha256=str(raw["grid_contract_sha256"]),
                spatial_group_id=group_id,
                split=split,
            )
        )
    return tuple(memberships), file_sha


def _validate_cell_grid_frame(
    frame: pd.DataFrame,
    *,
    grid_contract: VerifiedGridContract,
    label: str,
) -> pd.DataFrame:
    base = frame.loc[:, CELL_GRID_COLUMNS].copy()
    if base.empty:
        raise ControlledExperimentError(f"{label} must not be empty.")
    base["cell_id"] = base["cell_id"].map(lambda value: _text(value, "cell_id"))
    if base["cell_id"].duplicated().any():
        raise ControlledExperimentError(f"{label} cell IDs must be unique.")
    for column in ("x", "y", "cell_area_m2"):
        base[column] = pd.to_numeric(base[column], errors="coerce")
        if base[column].isna().any() or not base[column].map(math.isfinite).all():
            raise ControlledExperimentError(f"{label} {column} must be finite.")
    if (
        not base["cell_area_m2"]
        .map(
            lambda value: math.isclose(
                float(value), grid_contract.cell_area_m2, rel_tol=0, abs_tol=1e-9
            )
        )
        .all()
    ):
        raise ControlledExperimentError(
            f"{label} cell area does not match the grid affine determinant."
        )
    for column in ("row_index", "column_index"):
        numeric = pd.to_numeric(base[column], errors="coerce")
        if numeric.isna().any() or not numeric.eq(numeric.astype(int)).all():
            raise ControlledExperimentError(f"{label} {column} must be integer.")
        base[column] = numeric.astype(int)
    if base.duplicated(["row_index", "column_index"]).any():
        raise ControlledExperimentError(f"{label} row/column positions must be unique.")
    expected_positions = {
        (row, column)
        for row in range(grid_contract.height)
        for column in range(grid_contract.width)
    }
    observed_positions = set(zip(base["row_index"], base["column_index"], strict=True))
    if (
        observed_positions != expected_positions
        or len(base) != grid_contract.cell_count
    ):
        raise ControlledExperimentError(
            f"{label} does not exactly cover the signed grid dimensions."
        )
    hashes = {
        _sha256(value, f"{label} grid_contract_sha256")
        for value in base["grid_contract_sha256"]
    }
    if hashes != {grid_contract.file_sha256}:
        raise ControlledExperimentError(
            f"{label} grid contract SHA-256 was substituted."
        )
    if (
        _canonical_sha256(sorted(base["cell_id"].tolist()))
        != grid_contract.cell_ids_sha256
    ):
        raise ControlledExperimentError(
            f"{label} cell IDs do not match the grid contract."
        )
    a, b, c, d, e, f = grid_contract.transform
    for raw in base.to_dict("records"):
        row = int(raw["row_index"])
        column = int(raw["column_index"])
        expected_x = a * (column + 0.5) + b * (row + 0.5) + c
        expected_y = d * (column + 0.5) + e * (row + 0.5) + f
        if not math.isclose(
            float(raw["x"]), expected_x, rel_tol=0, abs_tol=1e-7
        ) or not math.isclose(float(raw["y"]), expected_y, rel_tol=0, abs_tol=1e-7):
            raise ControlledExperimentError(
                f"{label} coordinates do not match affine-derived cell centers."
            )
    if "spatial_group_id" in frame.columns and "split" in frame.columns:
        base["spatial_group_id"] = frame["spatial_group_id"].astype(str)
        base["split"] = frame["split"].astype(str)
    return base.sort_values("cell_id").reset_index(drop=True)


def _derive_memberships(
    cell_grid: pd.DataFrame,
    group_geometries: Sequence[tuple[str, str, Any]],
) -> tuple[FrozenCellMembership, ...]:
    try:
        from shapely.geometry import Point
    except ImportError as exc:
        raise ControlledExperimentError(
            "Spatial membership derivation requires the FloodGuard geo extra (Shapely)."
        ) from exc
    memberships: list[FrozenCellMembership] = []
    for raw in cell_grid.sort_values("cell_id").to_dict("records"):
        point = Point(float(raw["x"]), float(raw["y"]))
        matches = [
            (group_id, split)
            for group_id, split, geometry in group_geometries
            if geometry.covers(point)
        ]
        if len(matches) != 1:
            reason = (
                "outside all polygons" if not matches else "on an ambiguous boundary"
            )
            raise ControlledExperimentError(
                f"Cell {_text(raw['cell_id'], 'cell_id')} is {reason}."
            )
        group_id, split = matches[0]
        memberships.append(
            FrozenCellMembership(
                cell_id=_text(raw["cell_id"], "cell_id"),
                x=float(raw["x"]),
                y=float(raw["y"]),
                row_index=int(raw["row_index"]),
                column_index=int(raw["column_index"]),
                cell_area_m2=float(raw["cell_area_m2"]),
                grid_contract_sha256=_sha256(
                    raw["grid_contract_sha256"], "grid_contract_sha256"
                ),
                spatial_group_id=group_id,
                split=split,
            )
        )
    return tuple(memberships)


def _verify_holdout_payload(payload: Mapping[str, object]) -> None:
    if payload.get("artifact_schema") != HOLDOUT_SCHEMA:
        raise ControlledExperimentError("Spatial holdout payload has the wrong schema.")
    _verify_self_hash(payload, "manifest_sha256", "spatial holdout payload")


def _verify_holdout_instance(holdout: VerifiedSpatialHoldout) -> None:
    if (
        not isinstance(holdout, VerifiedSpatialHoldout)
        or holdout._verification_marker is not _VERIFIED_HOLDOUT_MARKER
    ):
        raise ControlledExperimentError(
            "Comparison requires a holdout created by the signed verifier."
        )
    if _canonical_sha256(holdout.receipt) != holdout._verified_receipt_sha256:
        raise ControlledExperimentError(
            "Verified spatial holdout receipt was mutated in memory."
        )
    _verify_holdout_payload(holdout.receipt)
    if len(holdout.memberships) != _positive_int(
        holdout.receipt.get("cell_count"), "holdout cell_count"
    ):
        raise ControlledExperimentError(
            "Verified spatial holdout membership count was substituted."
        )
    for split in ("train", "calibration", "final_holdout"):
        holdout._partition_sha256(split)


def _verify_gate_receipt(receipt: Mapping[str, object]) -> None:
    schema = receipt.get("artifact_schema")
    current_schema = schema == GATE_RECEIPT_SCHEMA
    if not current_schema:
        legacy_blocked = (
            schema
            in {
                "floodguard.controlled_experiment_gate_receipt.v2",
                "floodguard.controlled_experiment_gate_receipt.v3",
            }
            and receipt.get("gate_status") == "blocked"
            and receipt.get("experiment_executed") is False
            and receipt.get("processing_allowed") is False
            and receipt.get("can_feed_decision_layer") is False
        )
        if not legacy_blocked:
            raise ControlledExperimentError("Gate receipt schema is unsupported.")
    else:
        required = {
            "artifact_schema",
            "gate_kind",
            "experiment_id",
            "study_area",
            "generated_at",
            "acquisition",
            "reviewer_calibration",
            "spatial_holdout",
            "reference_cells",
            "promotion_policy",
            "model_evidence",
            "gate_status",
            "processing_allowed",
            "experiment_executed",
            "can_feed_decision_layer",
            "official_warning",
            "operational_status",
            "reason_blocked",
            "blockers",
            "assumptions",
            "receipt_sha256",
        }
        _exact_keys(receipt, required, "gate receipt")
        if receipt.get("gate_kind") != "pre_execution_readiness":
            raise ControlledExperimentError("Gate receipt kind is invalid.")
        gate_status = receipt.get("gate_status")
        blockers = receipt.get("blockers")
        if gate_status not in {"ready", "blocked"}:
            raise ControlledExperimentError("Gate receipt status is invalid.")
        if not isinstance(blockers, list) or any(
            not isinstance(item, str) or not item.strip() for item in blockers
        ):
            raise ControlledExperimentError("Gate receipt blockers are invalid.")
        if blockers != sorted(set(blockers)):
            raise ControlledExperimentError(
                "Gate receipt blockers must be sorted and unique."
            )
        is_ready = gate_status == "ready"
        if (
            receipt.get("processing_allowed") is not is_ready
            or receipt.get("experiment_executed") is not False
            or receipt.get("can_feed_decision_layer") is not False
            or receipt.get("official_warning") is not False
            or receipt.get("operational_status") != "non_operational"
            or bool(blockers) is is_ready
            or receipt.get("reason_blocked") != "; ".join(blockers)
        ):
            raise ControlledExperimentError(
                "Gate receipt contains unsafe or contradictory status fields."
            )
        acquisition = receipt.get("acquisition")
        reviewer = receipt.get("reviewer_calibration")
        holdout = receipt.get("spatial_holdout")
        reference = receipt.get("reference_cells")
        policy = receipt.get("promotion_policy")
        models = receipt.get("model_evidence")
        if not all(
            isinstance(value, Mapping)
            for value in (acquisition, reviewer, holdout, reference, policy, models)
        ):
            raise ControlledExperimentError(
                "Gate receipt evidence summaries are invalid."
            )
        if is_ready and (
            acquisition.get("ready") is not True
            or reviewer.get("status") != "verified"
            or holdout.get("status") != "verified"
            or reference.get("status") != "verified"
            or policy.get("status") != "verified"
        ):
            raise ControlledExperimentError(
                "Ready gate receipt is missing verified prerequisite evidence."
            )
        if models.get("status") not in {
            "not_expected_before_execution",
            "present_post_execution_unverified",
            "declared_but_missing",
        }:
            raise ControlledExperimentError(
                "Gate receipt model-evidence status is invalid."
            )
        _timestamp(receipt.get("generated_at"), "gate receipt generated_at")
        _text(receipt.get("experiment_id"), "gate receipt experiment_id")
        _text(receipt.get("study_area"), "gate receipt study_area")
    expected = receipt.get("receipt_sha256")
    if not isinstance(expected, str) or expected != _canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    ):
        raise ControlledExperimentError("Gate receipt self-hash is invalid.")
    _reject_private_paths(receipt)


def _coerce_csv(
    source: pd.DataFrame | str | Path,
    label: str,
) -> tuple[pd.DataFrame, str | None]:
    if isinstance(source, pd.DataFrame):
        return source.copy(), None
    return _read_csv_snapshot(Path(source), label)


def _json_object(path: Path, label: str) -> dict[str, Any]:
    return _json_object_bytes(_read_stable_bytes(path, label), label)


def _json_object_bytes(content: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ControlledExperimentError(
                    f"{label} contains duplicate JSON key: {key}."
                )
            value[key] = item
        return value

    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ControlledExperimentError(f"Could not read {label}.") from exc
    if not isinstance(value, dict):
        raise ControlledExperimentError(f"{label} must be a JSON object.")
    return value


def _read_csv_snapshot(path: Path, label: str) -> tuple[pd.DataFrame, str]:
    content = _read_stable_bytes(path, label)
    digest = hashlib.sha256(content).hexdigest()
    try:
        frame = pd.read_csv(io.BytesIO(content))
    except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ControlledExperimentError(f"Could not read {label}.") from exc
    return frame, digest


def _load_reviewer_calibration_snapshot(path: Path) -> tuple[Any, str]:
    """Parse the calibration receipt from the exact descriptor-bound bytes hashed."""

    content = _read_stable_bytes(path, "reviewer calibration receipt")
    digest = hashlib.sha256(content).hexdigest()
    try:
        with tempfile.TemporaryDirectory(prefix="floodguard-reviewer-") as directory:
            snapshot = Path(directory) / "reviewer-calibration-receipt.json"
            snapshot.write_bytes(content)
            reviewer = load_reviewer_calibration_receipt(snapshot)
    except OSError as exc:
        raise ControlledExperimentError(
            "Could not verify reviewer calibration snapshot."
        ) from exc
    return reviewer, digest


def _read_stable_bytes(path: Path, label: str) -> bytes:
    with _open_stable_binary(path, label) as stream:
        try:
            before = os.fstat(stream.fileno())
            content = stream.read()
            after = os.fstat(stream.fileno())
        except OSError as exc:
            raise ControlledExperimentError(f"Could not read {label}.") from exc
    _assert_unchanged_snapshot(path, before, after, label)
    return content


@contextmanager
def _open_stable_binary(path: Path, label: str) -> Iterator[Any]:
    try:
        path_stat = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ControlledExperimentError(f"Could not inspect {label}.") from exc
    if not stat.S_ISREG(path_stat.st_mode):
        raise ControlledExperimentError(
            f"{label.capitalize()} must be a regular non-symlink file."
        )
    flags = os.O_RDONLY
    for flag_name in ("O_BINARY", "O_NOINHERIT", "O_NOFOLLOW"):
        flags |= int(getattr(os, flag_name, 0))
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ControlledExperimentError(f"Could not open {label} safely.") from exc
    try:
        descriptor_stat = os.fstat(descriptor)
        inode_changed = (
            path_stat.st_ino != 0
            and descriptor_stat.st_ino != 0
            and path_stat.st_ino != descriptor_stat.st_ino
        )
        if (
            not stat.S_ISREG(descriptor_stat.st_mode)
            or path_stat.st_dev != descriptor_stat.st_dev
            or inode_changed
        ):
            raise ControlledExperimentError(
                f"{label.capitalize()} changed before its snapshot was opened."
            )
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            yield stream
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ControlledExperimentError(
            f"{label} is missing columns: {', '.join(missing)}"
        )


def _require_exact_columns(
    frame: pd.DataFrame,
    columns: Sequence[str],
    label: str,
) -> None:
    expected = set(columns)
    missing = sorted(expected - set(frame.columns))
    extra = sorted(set(frame.columns) - expected)
    if missing or extra:
        raise ControlledExperimentError(
            f"{label} columns do not match contract; missing={missing}, extra={extra}."
        )


def _exact_keys(value: Mapping[str, object], keys: set[str], label: str) -> None:
    missing = sorted(keys - set(value))
    extra = sorted(set(value) - keys)
    if missing or extra:
        raise ControlledExperimentError(
            f"{label} keys do not match schema; missing={missing}, extra={extra}."
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ControlledExperimentError(f"{label} must not be blank.")
    return value.strip()


def _substantive_text(value: object, label: str) -> str:
    text = _text(value, label)
    normalized = text.lower()
    if (
        "<" in text
        or ">" in text
        or normalized
        in {"unanswered", "unknown", "none", "n/a", "not provided", "pending"}
    ):
        raise ControlledExperimentError(
            f"{label} must contain completed attributable evidence."
        )
    return text


def _https_url(value: object, label: str) -> str:
    text = _substantive_text(value, label)
    if not text.startswith("https://"):
        raise ControlledExperimentError(f"{label} must use HTTPS.")
    return text


def _product_id(value: object, label: str) -> str:
    product_id = _text(value, label)
    if not PRODUCT_ID_RE.fullmatch(product_id):
        raise ControlledExperimentError(
            f"{label} must be a stable product identifier without paths or whitespace."
        )
    return product_id


def _timestamp(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlledExperimentError(f"{label} must be ISO-8601.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ControlledExperimentError(f"{label} must include a timezone.")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ControlledExperimentError("Timestamp must be timezone-aware.")
    # Preserve supplied sub-second precision. Acquisition instants are part of
    # the authority-signed identity, so rounding here would make two distinct
    # source timestamps within the same second hash to the same authorization.
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _strict_bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ControlledExperimentError(f"{label} must be explicit true or false.")


def _binary_series(values: pd.Series, label: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any() or not set(numeric.astype(int)).issubset({0, 1}):
        raise ControlledExperimentError(f"{label} must contain only 0 and 1.")
    if not numeric.eq(numeric.astype(int)).all():
        raise ControlledExperimentError(f"{label} must contain integer 0 and 1.")
    return numeric.astype(int)


def _redacted_path_hint(value: object, role: str) -> str:
    text = _text(value, f"{role} local_path_hint")
    if PRIVATE_PATH_RE.search(text) or not text.startswith(
        "<external_data_workspace>/"
    ):
        raise ControlledExperimentError(
            f"{role}: local_path_hint must be redacted under <external_data_workspace>."
        )
    relative = text.removeprefix("<external_data_workspace>/")
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise ControlledExperimentError(f"{role}: local_path_hint is unsafe.")
    return text


def _basename(value: object, label: str) -> str:
    text = _text(value, label)
    if Path(text).name != text or text in {".", ".."}:
        raise ControlledExperimentError(f"{label} must be a basename.")
    return text


def _optional_sha256(value: object, label: str) -> str:
    text = str(value).strip().lower()
    if not text:
        return ""
    return _sha256(text, label)


def _sha256(value: object, label: str) -> str:
    text = str(value).strip().lower()
    if not SHA256_RE.fullmatch(text):
        raise ControlledExperimentError(f"{label} must be a lowercase SHA-256.")
    return text


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    label = f"required artifact {path.name}"
    with _open_stable_binary(path, label) as handle:
        try:
            before = os.fstat(handle.fileno())
            for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
                digest.update(chunk)
            after = os.fstat(handle.fileno())
        except OSError as exc:
            raise ControlledExperimentError(
                f"Could not hash required artifact {path.name}."
            ) from exc
    _assert_unchanged_snapshot(path, before, after, label)
    return digest.hexdigest()


def _assert_unchanged_snapshot(
    path: Path,
    before: os.stat_result,
    after: os.stat_result,
    label: str,
) -> None:
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise ControlledExperimentError(
            f"{label.capitalize()} changed while its bytes were read."
        )
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ControlledExperimentError(
            f"{label.capitalize()} changed after its bytes were read."
        ) from exc
    inode_changed = (
        after.st_ino != 0 and current.st_ino != 0 and after.st_ino != current.st_ino
    )
    if (
        not stat.S_ISREG(current.st_mode)
        or after.st_dev != current.st_dev
        or inode_changed
        or after.st_size != current.st_size
        or after.st_mtime_ns != current.st_mtime_ns
        or after.st_ctime_ns != current.st_ctime_ns
    ):
        raise ControlledExperimentError(
            f"{label.capitalize()} path no longer identifies the captured bytes."
        )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _seal_signed_payload(
    payload: Mapping[str, object],
    *,
    signing_key_id: str,
    signing_key: bytes,
    self_hash_field: str,
) -> dict[str, object]:
    key_id = _text(signing_key_id, "signing_key_id")
    key = _validated_signing_key(signing_key)
    sealed = dict(payload)
    if self_hash_field in sealed or "signature" in sealed:
        raise ControlledExperimentError("Signed payload already contains seal fields.")
    sealed["signing_key_id"] = key_id
    sealed["signature_algorithm"] = SIGNATURE_ALGORITHM
    sealed[self_hash_field] = _canonical_sha256(sealed)
    sealed["signature"] = hmac.new(
        key,
        _canonical_json_bytes(sealed),
        hashlib.sha256,
    ).hexdigest()
    return sealed


def _require_distinct_trusted_credentials(
    signing_keys: Mapping[str, bytes],
    signing_key_ids: Sequence[str],
    *,
    label: str,
) -> None:
    """Reject role-separated IDs that resolve to the same HMAC credential."""

    normalized = [_text(value, f"{label} signing_key_id") for value in signing_key_ids]
    if len(normalized) != len(set(normalized)):
        raise ControlledExperimentError(f"{label} signing identities must be distinct.")
    credentials: list[bytes] = []
    for key_id in normalized:
        value = signing_keys.get(key_id)
        if value is None:
            raise ControlledExperimentError(
                f"{label} signing key {key_id!r} is not trusted at runtime."
            )
        credential = _validated_signing_key(value)
        if any(hmac.compare_digest(credential, prior) for prior in credentials):
            raise ControlledExperimentError(
                f"{label} must use distinct credentials for every authority role."
            )
        credentials.append(credential)


def _seal_dual_signed_payload(
    payload: Mapping[str, object],
    *,
    reviewer_signing_key_id: str,
    reviewer_signing_key: bytes,
    adjudicator_signing_key_id: str,
    adjudicator_signing_key: bytes,
) -> dict[str, object]:
    reviewer_key_id = _text(reviewer_signing_key_id, "reviewer_signing_key_id")
    adjudicator_key_id = _text(adjudicator_signing_key_id, "adjudicator_signing_key_id")
    reviewer_key = _validated_signing_key(reviewer_signing_key)
    adjudicator_key = _validated_signing_key(adjudicator_signing_key)
    if reviewer_key_id == adjudicator_key_id or hmac.compare_digest(
        reviewer_key, adjudicator_key
    ):
        raise ControlledExperimentError(
            "Reviewer authority and adjudicator must use distinct credentials."
        )
    sealed = dict(payload)
    forbidden = {
        "reviewer_signing_key_id",
        "adjudicator_signing_key_id",
        "signature_algorithm",
        "manifest_sha256",
        "reviewer_signature",
        "adjudicator_signature",
    }
    if forbidden.intersection(sealed):
        raise ControlledExperimentError(
            "Dual-signed payload already contains seal fields."
        )
    sealed.update(
        {
            "reviewer_signing_key_id": reviewer_key_id,
            "adjudicator_signing_key_id": adjudicator_key_id,
            "signature_algorithm": SIGNATURE_ALGORITHM,
        }
    )
    sealed["manifest_sha256"] = _canonical_sha256(sealed)
    signed_bytes = _canonical_json_bytes(sealed)
    sealed["reviewer_signature"] = hmac.new(
        reviewer_key, signed_bytes, hashlib.sha256
    ).hexdigest()
    sealed["adjudicator_signature"] = hmac.new(
        adjudicator_key, signed_bytes, hashlib.sha256
    ).hexdigest()
    return sealed


def _verify_dual_signed_payload(
    payload: Mapping[str, object],
    signing_keys: Mapping[str, bytes],
    label: str,
) -> None:
    if payload.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        raise ControlledExperimentError(f"{label} signature algorithm is unsupported.")
    reviewer_id = _text(
        payload.get("reviewer_signing_key_id"), f"{label} reviewer_signing_key_id"
    )
    adjudicator_id = _text(
        payload.get("adjudicator_signing_key_id"),
        f"{label} adjudicator_signing_key_id",
    )
    if reviewer_id == adjudicator_id:
        raise ControlledExperimentError(
            f"{label} reviewer and adjudicator signing keys must differ."
        )
    reviewer_key_value = signing_keys.get(reviewer_id)
    adjudicator_key_value = signing_keys.get(adjudicator_id)
    if reviewer_key_value is None or adjudicator_key_value is None:
        raise ControlledExperimentError(
            f"{label} dual signing keys are not trusted at runtime."
        )
    reviewer_key = _validated_signing_key(reviewer_key_value)
    adjudicator_key = _validated_signing_key(adjudicator_key_value)
    if hmac.compare_digest(reviewer_key, adjudicator_key):
        raise ControlledExperimentError(
            f"{label} reviewer and adjudicator credentials must differ."
        )
    unsigned = {
        key: value
        for key, value in payload.items()
        if key not in {"reviewer_signature", "adjudicator_signature"}
    }
    signed_bytes = _canonical_json_bytes(unsigned)
    for signature_field, key in (
        ("reviewer_signature", reviewer_key),
        ("adjudicator_signature", adjudicator_key),
    ):
        signature = _sha256(payload.get(signature_field), signature_field)
        expected = hmac.new(key, signed_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ControlledExperimentError(
                f"{label} {signature_field} HMAC is invalid."
            )


def _verify_signed_payload(
    payload: Mapping[str, object],
    signing_keys: Mapping[str, bytes],
    label: str,
) -> None:
    if payload.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        raise ControlledExperimentError(f"{label} signature algorithm is unsupported.")
    key_id = _text(payload.get("signing_key_id"), f"{label} signing_key_id")
    key_value = signing_keys.get(key_id)
    if key_value is None:
        raise ControlledExperimentError(
            f"{label} signing key is not trusted at runtime."
        )
    key = _validated_signing_key(key_value)
    signature = _sha256(payload.get("signature"), f"{label} signature")
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    expected = hmac.new(
        key,
        _canonical_json_bytes(unsigned),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ControlledExperimentError(f"{label} HMAC signature is invalid.")


def _verify_self_hash(
    payload: Mapping[str, object],
    field: str,
    label: str,
) -> None:
    expected = _sha256(payload.get(field), f"{label} {field}")
    unsealed = {
        key: value for key, value in payload.items() if key not in {field, "signature"}
    }
    if expected != _canonical_sha256(unsealed):
        raise ControlledExperimentError(f"{label} self-hash is invalid.")


def _verify_dual_self_hash(payload: Mapping[str, object], label: str) -> None:
    expected = _sha256(payload.get("manifest_sha256"), f"{label} manifest_sha256")
    unsealed = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "manifest_sha256",
            "reviewer_signature",
            "adjudicator_signature",
        }
    }
    if expected != _canonical_sha256(unsealed):
        raise ControlledExperimentError(f"{label} self-hash is invalid.")


def _validated_signing_key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ControlledExperimentError(
            "Signing keys must be external byte strings of at least 32 bytes."
        )
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


_ED25519_FIELD = 2**255 - 19
_ED25519_ORDER = 2**252 + 27742317777372353535851937790883648493
_ED25519_D = (-121665 * pow(121666, _ED25519_FIELD - 2, _ED25519_FIELD)) % (
    _ED25519_FIELD
)
_ED25519_I = pow(2, (_ED25519_FIELD - 1) // 4, _ED25519_FIELD)


def _ed25519_xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(
        (_ED25519_D * y * y + 1) % _ED25519_FIELD,
        _ED25519_FIELD - 2,
        _ED25519_FIELD,
    )
    x = pow(xx % _ED25519_FIELD, (_ED25519_FIELD + 3) // 8, _ED25519_FIELD)
    if (x * x - xx) % _ED25519_FIELD != 0:
        x = (x * _ED25519_I) % _ED25519_FIELD
    if x % 2:
        x = _ED25519_FIELD - x
    return x


_ED25519_BY = (4 * pow(5, _ED25519_FIELD - 2, _ED25519_FIELD)) % _ED25519_FIELD
_ED25519_B = (_ed25519_xrecover(_ED25519_BY), _ED25519_BY)
_ED25519_IDENTITY = (0, 1)


def _ed25519_add(first: tuple[int, int], second: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = first
    x2, y2 = second
    factor = (_ED25519_D * x1 * x2 * y1 * y2) % _ED25519_FIELD
    x3 = (x1 * y2 + x2 * y1) * pow(
        (1 + factor) % _ED25519_FIELD,
        _ED25519_FIELD - 2,
        _ED25519_FIELD,
    )
    y3 = (y1 * y2 + x1 * x2) * pow(
        (1 - factor) % _ED25519_FIELD,
        _ED25519_FIELD - 2,
        _ED25519_FIELD,
    )
    return x3 % _ED25519_FIELD, y3 % _ED25519_FIELD


def _ed25519_scalarmult(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    result = _ED25519_IDENTITY
    addend = point
    value = scalar
    while value:
        if value & 1:
            result = _ed25519_add(result, addend)
        addend = _ed25519_add(addend, addend)
        value >>= 1
    return result


def _ed25519_decode_point(value: bytes) -> tuple[int, int] | None:
    if len(value) != 32:
        return None
    encoded = int.from_bytes(value, "little")
    sign = encoded >> 255
    y = encoded & ((1 << 255) - 1)
    if y >= _ED25519_FIELD:
        return None
    x = _ed25519_xrecover(y)
    if x & 1 != sign:
        x = _ED25519_FIELD - x
    if (-x * x + y * y - 1 - _ED25519_D * x * x * y * y) % _ED25519_FIELD != 0:
        return None
    point = (x, y)
    if _ed25519_scalarmult(point, 8) == _ED25519_IDENTITY:
        return None
    return point


def _ed25519_verify(public_key: bytes, signature: bytes, message: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False
    public_point = _ed25519_decode_point(public_key)
    r_point = _ed25519_decode_point(signature[:32])
    scalar = int.from_bytes(signature[32:], "little")
    if public_point is None or r_point is None or scalar >= _ED25519_ORDER:
        return False
    challenge = (
        int.from_bytes(
            hashlib.sha512(signature[:32] + public_key + message).digest(), "little"
        )
        % _ED25519_ORDER
    )
    return _ed25519_scalarmult(_ED25519_B, scalar) == _ed25519_add(
        r_point, _ed25519_scalarmult(public_point, challenge)
    )


def _validated_ed25519_public_key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise ControlledExperimentError(
            "Trusted external Ed25519 public keys must contain exactly 32 bytes."
        )
    if _ed25519_decode_point(value) is None:
        raise ControlledExperimentError(
            "Trusted external Ed25519 public key is invalid."
        )
    return value


def _decode_ed25519_material(
    value: object, *, expected_length: int, label: str
) -> bytes:
    text = _text(value, label)
    try:
        if re.fullmatch(r"[0-9a-fA-F]+", text) and len(text) == expected_length * 2:
            decoded = bytes.fromhex(text)
        else:
            decoded = base64.b64decode(text, validate=True)
    except (ValueError, UnicodeError) as exc:
        raise ControlledExperimentError(
            f"{label} must be hexadecimal or base64."
        ) from exc
    if len(decoded) != expected_length:
        raise ControlledExperimentError(
            f"{label} must contain exactly {expected_length} bytes."
        )
    return decoded


def load_ed25519_public_key(path: str | Path) -> bytes:
    """Read one trusted raw, hexadecimal, or base64 Ed25519 public key file."""

    content = _read_stable_bytes(Path(path), "external authority public key")
    if len(content) == 32:
        return _validated_ed25519_public_key(content)
    try:
        decoded = _decode_ed25519_material(
            content.decode("ascii"),
            expected_length=32,
            label="external authority public key",
        )
    except UnicodeError as exc:
        raise ControlledExperimentError(
            "External authority public key encoding is invalid."
        ) from exc
    return _validated_ed25519_public_key(decoded)


def _write_immutable_json(
    payload: Mapping[str, object],
    path: Path,
    label: str,
) -> None:
    if path.suffix.lower() != ".json":
        raise ControlledExperimentError(f"{label} must use a JSON filename.")
    if path.exists():
        raise ControlledExperimentError(f"{label} is immutable and already exists.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _bounded_probability(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and 0 <= number <= 1


def _positive_float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ControlledExperimentError(f"{label} must be a positive number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ControlledExperimentError(f"{label} must be a positive number.") from exc
    if not math.isfinite(number) or number <= 0:
        raise ControlledExperimentError(f"{label} must be a positive number.")
    return number


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ControlledExperimentError(f"{label} must be a positive integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ControlledExperimentError(f"{label} must be a positive integer.") from exc
    if number <= 0 or float(value) != number:
        raise ControlledExperimentError(f"{label} must be a positive integer.")
    return number


def _finite_float(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ControlledExperimentError(f"{label} must be finite.") from exc
    if not math.isfinite(number):
        raise ControlledExperimentError(f"{label} must be finite.")
    return number


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ControlledExperimentError(f"{label} must be a non-negative integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ControlledExperimentError(
            f"{label} must be a non-negative integer."
        ) from exc
    try:
        exactly_integral = float(value) == float(number)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ControlledExperimentError(
            f"{label} must be a non-negative integer."
        ) from exc
    if number < 0 or not exactly_integral:
        raise ControlledExperimentError(f"{label} must be a non-negative integer.")
    return number


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0 if numerator == 0 else 1.0
    return round(float(numerator) / float(denominator), 6)


def _reject_private_paths(value: object) -> None:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if PRIVATE_PATH_RE.search(serialized):
        raise ControlledExperimentError(
            "Public receipt contains a private absolute path."
        )
