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
import hashlib
import hmac
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Any

import pandas as pd

from floodguard.label_factory.calibration import (
    ReviewerCalibrationError,
    load_reviewer_calibration_receipt,
)


ACQUISITION_SCHEMA = "floodguard.controlled_experiment_acquisition.v1"
ACQUISITION_AUTHORITY_SCHEMA = "floodguard.acquisition_authority_receipt.v1"
HOLDOUT_SCHEMA = "floodguard.spatial_holdout.v3"
GRID_CONTRACT_SCHEMA = "floodguard.equal_area_grid.v1"
REFERENCE_CELL_RECEIPT_SCHEMA = "floodguard.controlled_reference_cells_receipt.v1"
MODEL_RUN_SCHEMA = "floodguard.controlled_model_run_receipt.v1"
GATE_RECEIPT_SCHEMA = "floodguard.controlled_experiment_gate_receipt.v2"
RESULT_RECEIPT_SCHEMA = "floodguard.controlled_experiment_result.v2"
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
    "radar_shadow",
    "steep_terrain",
    "urban_surface",
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
    "reviewer_calibration_file_sha256",
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
PRIVATE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/home/|/Users/)")
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


@dataclass(frozen=True, slots=True)
class AcquisitionGateAssessment:
    """Deterministic result of validating the acquisition manifest and bytes."""

    experiment_id: str
    study_area: str
    manifest_sha256: str
    manifest_file_sha256: str | None
    sha256_by_role: tuple[tuple[str, str], ...]
    authority_receipt_sha256: str | None
    ready: bool
    blockers: tuple[str, ...]

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


@dataclass(frozen=True, slots=True)
class VerifiedSpatialHoldout:
    """A signed holdout receipt plus its re-derived authoritative membership."""

    receipt: dict[str, object]
    memberships: tuple[FrozenCellMembership, ...]

    @property
    def manifest_sha256(self) -> str:
        return str(self.receipt["manifest_sha256"])

    @property
    def membership_sha256(self) -> str:
        return str(self.receipt["membership_sha256"])

    @property
    def training_partition_sha256(self) -> str:
        rows = [
            membership.to_dict()
            for membership in self.memberships
            if membership.split == "train"
        ]
        return _canonical_sha256(rows)


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
    manifest_sha256: str
    receipt_file_sha256: str
    evidence_file_sha256: str
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
    if authority_receipt_path is None:
        blockers.append(
            "acquisition_authority: signed catalog/license allowlist receipt is missing"
        )
    else:
        authority_path = Path(authority_receipt_path)
        try:
            _authority_payload, authority_receipt_sha256 = (
                _verify_acquisition_authority_receipt(
                    authority_path,
                    manifest_sha256=manifest_sha,
                    experiment_id=next(iter(experiment_ids)),
                    study_area=next(iter(study_areas)),
                    normalized_rows=normalized_rows,
                    signing_keys=signing_keys or {},
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
        ready=not blockers,
        blockers=tuple(sorted(set(blockers))),
    )


def write_acquisition_authority_receipt(
    acquisition: AcquisitionGateAssessment,
    acquisition_source: pd.DataFrame | str | Path,
    *,
    authority_id: str,
    allowlist_id: str,
    catalog_receipt_sha256_by_role: Mapping[str, str],
    license_receipt_sha256_by_role: Mapping[str, str],
    issued_at_utc: datetime,
    expires_at_utc: datetime,
    signing_key_id: str,
    signing_key: bytes,
    output_path: str | Path,
) -> dict[str, object]:
    """Issue an immutable authority receipt after independent catalog/licence review.

    This helper never invents authority: the caller supplies external catalog and
    licence receipt digests plus an HMAC key held outside the repository.  The
    signed allowlist binds those digests to the exact manifest rows and bytes.
    """

    allowed_blocker = (
        "acquisition_authority: signed catalog/license allowlist receipt is missing"
    )
    remaining = [item for item in acquisition.blockers if item != allowed_blocker]
    if remaining:
        raise ControlledExperimentError(
            "Acquisition authority cannot be issued while base gates are blocked: "
            + "; ".join(remaining)
        )
    if set(catalog_receipt_sha256_by_role) != set(REQUIRED_INPUT_ROLES):
        raise ControlledExperimentError(
            "Catalog receipt mapping must cover exactly the three acquisition roles."
        )
    if set(license_receipt_sha256_by_role) != set(REQUIRED_INPUT_ROLES):
        raise ControlledExperimentError(
            "License receipt mapping must cover exactly the three acquisition roles."
        )
    issued = _timestamp(_format_utc(issued_at_utc), "issued_at_utc")
    expires = _timestamp(_format_utc(expires_at_utc), "expires_at_utc")
    if expires <= issued:
        raise ControlledExperimentError(
            "Authority receipt expiry must follow issue time."
        )
    frame, _file_sha = _coerce_csv(acquisition_source, "acquisition manifest")
    _require_columns(frame, ACQUISITION_COLUMNS, "acquisition manifest")
    frame = frame.fillna("")
    authorizations: list[dict[str, object]] = []
    for raw in frame.sort_values("role").to_dict("records"):
        role = _text(raw["role"], "role")
        authorizations.append(
            {
                "role": role,
                "source_name": _text(raw["source_name"], f"{role} source_name"),
                "product_id": _product_id(raw["product_id"], f"{role} product_id"),
                "source_url": _text(raw["source_url"], f"{role} source_url"),
                "acquisition_start_utc": _format_utc(
                    _timestamp(
                        raw["acquisition_start_utc"], f"{role} acquisition start"
                    )
                ),
                "acquisition_end_utc": _format_utc(
                    _timestamp(raw["acquisition_end_utc"], f"{role} acquisition end")
                ),
                "source_timestamp": _format_utc(
                    _timestamp(raw["source_timestamp"], f"{role} source_timestamp")
                ),
                "assumptions": _text(raw["assumptions"], f"{role} assumptions"),
                "artifact_sha256": _sha256(raw["sha256"], f"{role} sha256"),
                "catalog_receipt_sha256": _sha256(
                    catalog_receipt_sha256_by_role[role],
                    f"{role} catalog_receipt_sha256",
                ),
                "license_receipt_sha256": _sha256(
                    license_receipt_sha256_by_role[role],
                    f"{role} license_receipt_sha256",
                ),
                "license_status": _text(
                    raw["license_status"], f"{role} license_status"
                ),
                "local_analysis_allowed": _strict_bool(
                    raw["local_analysis_allowed"], f"{role} local_analysis_allowed"
                ),
                "derived_metrics_allowed": _strict_bool(
                    raw["derived_metrics_allowed"], f"{role} derived_metrics_allowed"
                ),
                "ml_label_use_allowed": _strict_bool(
                    raw["ml_label_use_allowed"], f"{role} ml_label_use_allowed"
                ),
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
                "approved_for_controlled_experiment": True,
            }
        )
    payload: dict[str, object] = {
        "artifact_schema": ACQUISITION_AUTHORITY_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "authority_id": _text(authority_id, "authority_id"),
        "allowlist_id": _text(allowlist_id, "allowlist_id"),
        "issued_at_utc": _format_utc(issued),
        "expires_at_utc": _format_utc(expires),
        "authorizations": authorizations,
        "official_warning": False,
        "can_feed_decision_layer": False,
    }
    sealed = _seal_signed_payload(
        payload,
        signing_key_id=signing_key_id,
        signing_key=signing_key,
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
        "allowlist_id",
        "issued_at_utc",
        "expires_at_utc",
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
    _verify_signed_payload(payload, signing_keys, "acquisition authority receipt")
    _verify_self_hash(payload, "manifest_sha256", "acquisition authority receipt")
    if payload["experiment_id"] != experiment_id or payload["study_area"] != study_area:
        raise ControlledExperimentError("Acquisition authority scope was substituted.")
    if payload["acquisition_manifest_sha256"] != manifest_sha256:
        raise ControlledExperimentError(
            "Acquisition authority manifest was substituted."
        )
    issued = _timestamp(payload["issued_at_utc"], "authority issued_at_utc")
    expires = _timestamp(payload["expires_at_utc"], "authority expires_at_utc")
    verified = _timestamp(_format_utc(verified_at_utc), "verified_at_utc")
    if expires <= issued or not issued <= verified <= expires:
        raise ControlledExperimentError(
            "Acquisition authority receipt is not currently valid."
        )
    if (
        payload["official_warning"] is not False
        or payload["can_feed_decision_layer"] is not False
    ):
        raise ControlledExperimentError(
            "Acquisition authority has unsafe status fields."
        )
    rows_by_role = {str(row["role"]): row for row in normalized_rows}
    authorizations = payload["authorizations"]
    if not isinstance(authorizations, list) or len(authorizations) != len(
        REQUIRED_INPUT_ROLES
    ):
        raise ControlledExperimentError(
            "Acquisition authority must contain three authorizations."
        )
    seen: set[str] = set()
    for authorization in authorizations:
        if not isinstance(authorization, Mapping):
            raise ControlledExperimentError(
                "Acquisition authorization must be an object."
            )
        _exact_keys(
            authorization,
            {
                "role",
                "source_name",
                "product_id",
                "source_url",
                "acquisition_start_utc",
                "acquisition_end_utc",
                "source_timestamp",
                "assumptions",
                "artifact_sha256",
                "catalog_receipt_sha256",
                "license_receipt_sha256",
                "license_status",
                "local_analysis_allowed",
                "derived_metrics_allowed",
                "ml_label_use_allowed",
                "redistribution_status",
                "reference_mask_status",
                "temporal_alignment_status",
                "approved_for_controlled_experiment",
            },
            "acquisition authorization",
        )
        role = _text(authorization["role"], "authorization role")
        row = rows_by_role.get(role)
        if row is None or role in seen:
            raise ControlledExperimentError(
                "Acquisition authority role set is invalid."
            )
        seen.add(role)
        expected = {
            "source_name": str(row["source_name"]),
            "product_id": str(row["product_id"]),
            "source_url": str(row["source_url"]),
            "acquisition_start_utc": str(row["acquisition_start_utc"]),
            "acquisition_end_utc": str(row["acquisition_end_utc"]),
            "source_timestamp": str(row["source_timestamp"]),
            "assumptions": str(row["assumptions"]),
            "artifact_sha256": str(row["sha256"]),
            "license_status": str(row["license_status"]),
            "local_analysis_allowed": bool(row["local_analysis_allowed"]),
            "derived_metrics_allowed": bool(row["derived_metrics_allowed"]),
            "ml_label_use_allowed": bool(row["ml_label_use_allowed"]),
            "redistribution_status": str(row["redistribution_status"]),
            "reference_mask_status": str(row["reference_mask_status"]),
            "temporal_alignment_status": str(row["temporal_alignment_status"]),
        }
        for field, expected_value in expected.items():
            if authorization[field] != expected_value:
                raise ControlledExperimentError(
                    f"{role}: acquisition authority {field} was substituted."
                )
        _sha256(authorization["catalog_receipt_sha256"], f"{role} catalog receipt")
        _sha256(authorization["license_receipt_sha256"], f"{role} license receipt")
        if authorization["approved_for_controlled_experiment"] is not True:
            raise ControlledExperimentError(
                f"{role}: product is not authority-approved."
            )
    if seen != set(REQUIRED_INPUT_ROLES):
        raise ControlledExperimentError("Acquisition authority role set is incomplete.")
    return payload, receipt_sha256


def freeze_spatial_holdout(
    geometry_path: str | Path,
    *,
    grid_contract_path: str | Path,
    cell_grid_path: str | Path,
    membership_output_path: str | Path,
    experiment_id: str,
    study_area: str,
    target_crs: str,
    grid_contract_sha256: str,
    source_registry_sha256: str,
    frozen_at_utc: datetime,
    assumptions: str,
    signing_key_id: str,
    signing_key: bytes,
    output_path: str | Path,
) -> VerifiedSpatialHoldout:
    """Freeze geometry-derived cell membership and sign it with external authority."""

    geometry = Path(geometry_path)
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
    holdout_ids = sorted(
        group["spatial_group_id"] for group in groups if group["split"] == "holdout"
    )
    if not train_ids or not holdout_ids:
        raise ControlledExperimentError(
            "Spatial holdout requires at least one train and one holdout polygon."
        )
    grid_contract = _load_grid_contract(
        Path(grid_contract_path),
        expected_sha256=_sha256(grid_contract_sha256, "grid_contract_sha256"),
        expected_crs=target_crs,
    )
    grid_sha = grid_contract.file_sha256
    cell_grid = _read_cell_grid(Path(cell_grid_path), grid_contract=grid_contract)
    memberships = _derive_memberships(cell_grid, group_geometries)
    if not any(item.split == "train" for item in memberships) or not any(
        item.split == "holdout" for item in memberships
    ):
        raise ControlledExperimentError(
            "Frozen cell membership requires at least one train and one holdout cell."
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
    payload: dict[str, object] = {
        "artifact_schema": HOLDOUT_SCHEMA,
        "experiment_id": _text(experiment_id, "experiment_id"),
        "study_area": _text(study_area, "study_area"),
        "target_crs": target_crs.upper(),
        "geometry_file": geometry.name,
        "geometry_sha256": geometry_sha256,
        "membership_file": membership_path.name,
        "membership_sha256": _file_sha256(membership_path),
        "cell_count": len(memberships),
        "cell_area_m2": grid_contract.cell_area_m2,
        "grid_contract_file": grid_contract.file_name,
        "grid_contract_sha256": grid_sha,
        "source_registry_sha256": _sha256(
            source_registry_sha256, "source_registry_sha256"
        ),
        "frozen_at_utc": _format_utc(frozen_at_utc),
        "created_before_model_fitting": True,
        "groups": groups,
        "training_ids": train_ids,
        "holdout_ids": holdout_ids,
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
        signing_keys={signing_key_id: signing_key},
    )


def load_spatial_holdout(
    receipt_path: str | Path,
    geometry_path: str | Path,
    grid_contract_path: str | Path,
    membership_path: str | Path,
    *,
    signing_keys: Mapping[str, bytes],
) -> VerifiedSpatialHoldout:
    """Re-hash and re-derive a signed holdout; reject every substitution."""

    receipt_file = Path(receipt_path)
    payload = _json_object(receipt_file, "spatial holdout receipt")
    required = {
        "artifact_schema",
        "experiment_id",
        "study_area",
        "target_crs",
        "geometry_file",
        "geometry_sha256",
        "membership_file",
        "membership_sha256",
        "cell_count",
        "cell_area_m2",
        "grid_contract_file",
        "grid_contract_sha256",
        "source_registry_sha256",
        "frozen_at_utc",
        "created_before_model_fitting",
        "groups",
        "training_ids",
        "holdout_ids",
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
    holdout_ids = sorted(
        group["spatial_group_id"] for group in groups if group["split"] == "holdout"
    )
    if payload["training_ids"] != train_ids or payload["holdout_ids"] != holdout_ids:
        raise ControlledExperimentError(
            "Holdout ID lists do not match geometry splits."
        )
    _timestamp(payload["frozen_at_utc"], "frozen_at_utc")
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
    _sha256(payload["source_registry_sha256"], "source_registry_sha256")
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
    derived_holdout_ids = sorted(
        {item.spatial_group_id for item in memberships if item.split == "holdout"}
    )
    if (
        derived_train_ids != payload["training_ids"]
        or derived_holdout_ids != payload["holdout_ids"]
    ):
        raise ControlledExperimentError(
            "Frozen membership group IDs do not match receipt."
        )
    return VerifiedSpatialHoldout(dict(payload), memberships)


def write_signed_reference_cell_receipt(
    reference_cell_path: str | Path,
    *,
    acquisition: AcquisitionGateAssessment,
    holdout: VerifiedSpatialHoldout,
    derived_at_utc: datetime,
    derivation_method: str,
    assumptions: str,
    signing_key_id: str,
    signing_key: bytes,
    output_path: str | Path,
) -> dict[str, object]:
    """Sign the exact qualified-mask-derived reference cells used for evaluation."""

    if not acquisition.ready or acquisition.authority_receipt_sha256 is None:
        raise ControlledExperimentError(
            "Signed, ready acquisition authority is required for reference cells."
        )
    if (
        holdout.receipt["experiment_id"] != acquisition.experiment_id
        or holdout.receipt["study_area"] != acquisition.study_area
    ):
        raise ControlledExperimentError(
            "Reference-cell acquisition and spatial holdout scope do not match."
        )
    derived = _timestamp(_format_utc(derived_at_utc), "derived_at_utc")
    frozen = _timestamp(holdout.receipt["frozen_at_utc"], "holdout frozen_at_utc")
    if derived < frozen:
        raise ControlledExperimentError(
            "Reference-cell evidence cannot predate the frozen spatial holdout."
        )
    evidence_path = Path(reference_cell_path)
    frame, evidence_sha = _read_csv_snapshot(evidence_path, "reference-cell evidence")
    cells = _validated_reference_cells(frame, holdout)
    cell_ids = [cell.cell_id for cell in cells]
    payload: dict[str, object] = {
        "artifact_schema": REFERENCE_CELL_RECEIPT_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "reference_mask_sha256": acquisition.reference_mask_sha256,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": (acquisition.authority_receipt_sha256),
        "reference_mask_status": "qualified_expert_or_adjudicated",
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "grid_contract_sha256": holdout.receipt["grid_contract_sha256"],
        "reference_cell_file": evidence_path.name,
        "reference_cell_sha256": evidence_sha,
        "reference_cell_ids_sha256": _canonical_sha256(cell_ids),
        "cell_count": len(cells),
        "derived_at_utc": _format_utc(derived),
        "derivation_method": _text(derivation_method, "derivation_method"),
        "assumptions": _text(assumptions, "assumptions"),
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
    _write_immutable_json(sealed, Path(output_path), "Reference-cell receipt")
    return sealed


def load_signed_reference_cell_evidence(
    receipt_path: str | Path,
    reference_cell_path: str | Path,
    *,
    acquisition: AcquisitionGateAssessment,
    holdout: VerifiedSpatialHoldout,
    signing_keys: Mapping[str, bytes],
) -> VerifiedReferenceCellEvidence:
    """Verify one signed reference artifact and parse only its hashed byte snapshot."""

    receipt_file = Path(receipt_path)
    receipt_bytes = _read_stable_bytes(receipt_file, "reference-cell receipt")
    receipt_file_sha = hashlib.sha256(receipt_bytes).hexdigest()
    payload = _json_object_bytes(receipt_bytes, "reference-cell receipt")
    required = {
        "artifact_schema",
        "experiment_id",
        "study_area",
        "reference_mask_sha256",
        "acquisition_manifest_sha256",
        "acquisition_authority_receipt_sha256",
        "reference_mask_status",
        "spatial_holdout_manifest_sha256",
        "spatial_holdout_membership_sha256",
        "grid_contract_sha256",
        "reference_cell_file",
        "reference_cell_sha256",
        "reference_cell_ids_sha256",
        "cell_count",
        "derived_at_utc",
        "derivation_method",
        "assumptions",
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
    expected_lineage = {
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "reference_mask_sha256": acquisition.reference_mask_sha256,
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "acquisition_authority_receipt_sha256": acquisition.authority_receipt_sha256,
        "reference_mask_status": "qualified_expert_or_adjudicated",
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
        payload["processing_allowed"] is not True
        or payload["can_feed_decision_layer"] is not False
        or payload["official_warning"] is not False
    ):
        raise ControlledExperimentError(
            "Reference-cell receipt has unsafe status fields."
        )
    _timestamp(payload["derived_at_utc"], "reference-cell derived_at_utc")
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
    return VerifiedReferenceCellEvidence(
        experiment_id=acquisition.experiment_id,
        study_area=acquisition.study_area,
        reference_mask_sha256=acquisition.reference_mask_sha256,
        spatial_holdout_manifest_sha256=holdout.manifest_sha256,
        spatial_holdout_membership_sha256=holdout.membership_sha256,
        grid_contract_sha256=str(holdout.receipt["grid_contract_sha256"]),
        manifest_sha256=str(payload["manifest_sha256"]),
        receipt_file_sha256=receipt_file_sha,
        evidence_file_sha256=evidence_sha,
        signing_key_id=str(payload["signing_key_id"]),
        cells=cells,
        _verification_marker=_VERIFIED_REFERENCE_MARKER,
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
    reviewer_calibration_receipt_path: str | Path | None = None,
    holdout_receipt_path: str | Path | None = None,
    holdout_geometry_path: str | Path | None = None,
    holdout_grid_contract_path: str | Path | None = None,
    holdout_membership_path: str | Path | None = None,
    reference_cell_receipt_path: str | Path | None = None,
    reference_cell_evidence_path: str | Path | None = None,
    signing_keys: Mapping[str, bytes] | None = None,
    model_evidence_manifest_path: str | Path | None = None,
) -> dict[str, object]:
    """Build an auditable ready/blocked decision without weakening any gate."""

    blockers = list(acquisition.blockers)
    reviewer_summary: dict[str, object] = {"status": "missing"}
    if reviewer_calibration_receipt_path is None:
        blockers.append("reviewer_calibration: passing receipt is missing")
    else:
        reviewer_path = Path(reviewer_calibration_receipt_path)
        try:
            reviewer, reviewer_file_sha256 = _load_reviewer_calibration_snapshot(
                reviewer_path
            )
        except (ControlledExperimentError, ReviewerCalibrationError, OSError) as exc:
            blockers.append(f"reviewer_calibration: receipt is invalid: {exc}")
        else:
            reviewer_summary = {
                "status": "verified",
                "file_sha256": reviewer_file_sha256,
                "receipt_sha256": reviewer.receipt_sha256,
                "reviewer_count": len(reviewer.reviewer_ids),
                "formal_review_not_before_utc": _format_utc(
                    reviewer.formal_review_not_before_utc
                ),
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
                "holdout_ids": holdout.receipt["holdout_ids"],
                "frozen_at_utc": holdout.receipt["frozen_at_utc"],
                "signing_key_id": holdout.receipt["signing_key_id"],
            }

    reference_summary: dict[str, object] = {"status": "missing"}
    if reference_cell_receipt_path is None or reference_cell_evidence_path is None:
        blockers.append(
            "reference_cells: externally signed qualified-mask cell evidence is missing"
        )
    elif verified_holdout is None:
        blockers.append("reference_cells: spatial holdout is not verified")
    else:
        try:
            reference = load_signed_reference_cell_evidence(
                reference_cell_receipt_path,
                reference_cell_evidence_path,
                acquisition=acquisition,
                holdout=verified_holdout,
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

    model_summary: dict[str, object] = {"status": "missing"}
    if model_evidence_manifest_path is None:
        blockers.append(
            "model_evidence: no completed baseline, weak-label, and GeoAI evidence manifest exists"
        )
    else:
        model_path = Path(model_evidence_manifest_path)
        if not model_path.is_file():
            blockers.append("model_evidence: manifest file is missing")
        else:
            model_summary = {
                "status": "present_unverified_until_execution",
                "file_sha256": _file_sha256(model_path),
            }

    unique_blockers = sorted(set(blockers))
    ready = not unique_blockers
    payload: dict[str, object] = {
        "artifact_schema": GATE_RECEIPT_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "generated_at": _format_utc(generated_at_utc),
        "acquisition": acquisition.to_dict(),
        "reviewer_calibration": reviewer_summary,
        "spatial_holdout": holdout_summary,
        "reference_cells": reference_summary,
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
            "A gate receipt is evidence of readiness only; it does not run a model.",
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
        "Catalog/licence approval, holdout membership, model artifacts, run manifests, "
        "and pre-holdout thresholds require externally keyed signatures; editable CSV "
        "claims are not authority.",
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
        ("model_evidence", "Three-model evidence"),
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
            "immutable holdout polygons, and a signed grid contract on a projected "
            "metre-based equal-area CRS. Physical cell area comes only from the grid "
            "affine determinant; the complete cell-ID, row/column, and affine-center "
            "membership must match exactly. Any relabelled, missing, out-of-polygon, "
            "boundary-ambiguous, grid-mismatched, or checksum-substituted cell fails "
            "closed. Each signed model-run receipt must bind a strict lane-specific "
            "model contract and a threshold fixed before holdout evaluation.",
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

    _verify_holdout_payload(holdout.receipt)
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
    if not {"train", "holdout"}.issubset(set(authoritative_splits)):
        raise ControlledExperimentError(
            "Predictions require both train and holdout coverage."
        )
    holdout_mask = authoritative_splits.eq("holdout")
    expected_holdout_ids = set(str(value) for value in holdout.receipt["holdout_ids"])
    if (
        set(first.loc[holdout_mask, "spatial_group_id"].astype(str))
        != expected_holdout_ids
    ):
        raise ControlledExperimentError(
            "Prediction holdout IDs do not exactly match the receipt."
        )
    reference_by_cell = {cell.cell_id: cell for cell in reference_cells.cells}
    if tuple(sorted(reference_by_cell)) != authoritative_cells:
        raise ControlledExperimentError(
            "Verified reference cells do not exactly match frozen membership."
        )
    reference_frame = pd.DataFrame(
        [reference_by_cell[cell_id].to_dict() for cell_id in authoritative_cells]
    )
    truth = reference_frame.loc[holdout_mask, "reference_flood_extent"].reset_index(
        drop=True
    )
    if truth.empty:
        raise ControlledExperimentError("Untouched spatial holdout contains no cells.")
    cell_area_m2 = _positive_float(
        holdout.receipt["cell_area_m2"], "holdout cell_area_m2"
    )

    metric_rows: list[dict[str, object]] = []
    calibration_rows: list[dict[str, object]] = []
    error_rows: list[dict[str, object]] = []
    for family in REQUIRED_MODEL_FAMILIES:
        frame = normalized[family]
        probability = frame.loc[holdout_mask, "probability_0_1"].reset_index(drop=True)
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
                "evaluation_split": "untouched_spatial_holdout",
                "holdout_group_count": len(expected_holdout_ids),
                "sample_count": len(truth),
                "decision_threshold": threshold,
                **metrics,
                "can_feed_decision_layer": False,
            }
        )
        calibration_rows.extend(
            _calibration_rows(family, probability, truth, calibration_bins)
        )
        false_positive = prediction.eq(1) & truth.eq(0)
        false_negative = prediction.eq(0) & truth.eq(1)
        category_frame = reference_frame.loc[
            holdout_mask, list(ERROR_STRATA)
        ].reset_index(drop=True)
        error_rows.extend(
            [
                {
                    "model_family": family,
                    "error_type": "false_positive",
                    "category": "all",
                    "cell_count": int(false_positive.sum()),
                },
                {
                    "model_family": family,
                    "error_type": "false_negative",
                    "category": "all",
                    "cell_count": int(false_negative.sum()),
                },
            ]
        )
        for category in ERROR_STRATA:
            members = category_frame[category]
            error_rows.append(
                {
                    "model_family": family,
                    "error_type": "false_positive",
                    "category": category,
                    "cell_count": int((false_positive & members).sum()),
                }
            )
            error_rows.append(
                {
                    "model_family": family,
                    "error_type": "false_negative",
                    "category": category,
                    "cell_count": int((false_negative & members).sum()),
                }
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


def write_signed_model_run_manifest(
    *,
    model_id: str,
    model_family: str,
    model_artifact_path: str | Path,
    model_contract_path: str | Path,
    prediction_path: str | Path,
    acquisition: AcquisitionGateAssessment,
    reviewer_calibration_file_sha256: str,
    holdout: VerifiedSpatialHoldout,
    reference_cells: VerifiedReferenceCellEvidence,
    decision_threshold: float,
    threshold_selection_data_sha256: str,
    threshold_selected_at_utc: datetime,
    completed_at_utc: datetime,
    assumptions: str,
    signing_key_id: str,
    signing_key: bytes,
    output_path: str | Path,
) -> dict[str, object]:
    """Write a signed pre-holdout threshold and model-artifact lineage receipt."""

    family = _text(model_family, "model_family")
    contract_schema = MODEL_CONTRACT_SCHEMAS.get(family)
    if contract_schema is None:
        raise ControlledExperimentError("Unsupported controlled model family.")
    if not acquisition.ready or acquisition.authority_receipt_sha256 is None:
        raise ControlledExperimentError(
            "A signed, ready acquisition authority is required for a model run."
        )
    if (
        reference_cells._verification_marker is not _VERIFIED_REFERENCE_MARKER
        or reference_cells.experiment_id != acquisition.experiment_id
        or reference_cells.study_area != acquisition.study_area
        or reference_cells.reference_mask_sha256 != acquisition.reference_mask_sha256
        or reference_cells.spatial_holdout_manifest_sha256 != holdout.manifest_sha256
        or reference_cells.spatial_holdout_membership_sha256
        != holdout.membership_sha256
    ):
        raise ControlledExperimentError(
            "Verified reference-cell evidence does not match the model-run lineage."
        )
    if not _bounded_probability(decision_threshold):
        raise ControlledExperimentError("decision_threshold must be in [0,1].")
    selected = _timestamp(
        _format_utc(threshold_selected_at_utc), "threshold_selected_at_utc"
    )
    completed = _timestamp(_format_utc(completed_at_utc), "completed_at_utc")
    frozen = _timestamp(holdout.receipt["frozen_at_utc"], "holdout frozen_at_utc")
    if selected < frozen or completed <= selected:
        raise ControlledExperimentError(
            "Threshold selection must follow holdout freeze and precede model completion."
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
        "reviewer_calibration_file_sha256": _sha256(
            reviewer_calibration_file_sha256,
            "reviewer_calibration_file_sha256",
        ),
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "reference_cell_receipt_file_sha256": reference_cells.receipt_file_sha256,
        "reference_cell_manifest_sha256": reference_cells.manifest_sha256,
        "reference_cell_evidence_sha256": reference_cells.evidence_file_sha256,
        "training_partition_sha256": holdout.training_partition_sha256,
        "threshold_selection_data_sha256": _sha256(
            threshold_selection_data_sha256,
            "threshold_selection_data_sha256",
        ),
        "decision_threshold": float(decision_threshold),
        "threshold_selected_at_utc": _format_utc(selected),
        "threshold_selection_scope": "training_only_pre_holdout",
        "holdout_evaluated_during_threshold_selection": False,
        "completed_at_utc": _format_utc(completed),
        "execution_status": "completed",
        "spatial_holdout_untouched": True,
        "can_feed_decision_layer": False,
        "official_warning": False,
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
    reviewer_calibration_receipt_path: str | Path,
    holdout_receipt_path: str | Path,
    holdout_geometry_path: str | Path,
    holdout_grid_contract_path: str | Path,
    holdout_membership_path: str | Path,
    reference_cell_receipt_path: str | Path,
    reference_cell_evidence_path: str | Path,
    model_evidence_manifest_path: str | Path,
    prediction_paths: Mapping[str, str | Path],
    model_artifact_paths: Mapping[str, str | Path],
    model_contract_paths: Mapping[str, str | Path],
    model_run_manifest_paths: Mapping[str, str | Path],
    signing_keys: Mapping[str, bytes],
    output_directory: str | Path,
    generated_at_utc: datetime,
) -> dict[str, Path]:
    """Re-verify every receipt, compare three models, and write small results."""

    acquisition = assess_acquisition_manifest(
        acquisition_manifest_path,
        artifact_paths=acquisition_artifact_paths,
        authority_receipt_path=acquisition_authority_receipt_path,
        signing_keys=signing_keys,
        verified_at_utc=generated_at_utc,
    )
    if not acquisition.ready:
        raise ControlledExperimentError(
            "Controlled experiment is blocked by acquisition gates: "
            + "; ".join(acquisition.blockers)
        )
    reviewer_path = Path(reviewer_calibration_receipt_path)
    try:
        reviewer, reviewer_file_sha = _load_reviewer_calibration_snapshot(reviewer_path)
    except (ControlledExperimentError, ReviewerCalibrationError) as exc:
        raise ControlledExperimentError(
            f"Controlled experiment is blocked by reviewer calibration: {exc}"
        ) from exc
    holdout = load_spatial_holdout(
        holdout_receipt_path,
        holdout_geometry_path,
        holdout_grid_contract_path,
        holdout_membership_path,
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
        holdout=holdout,
        signing_keys=signing_keys,
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
        model_artifact_paths=model_artifact_paths,
        model_contract_paths=model_contract_paths,
        model_run_manifest_paths=model_run_manifest_paths,
        acquisition=acquisition,
        reviewer_file_sha256=reviewer_file_sha,
        reviewer_not_before=reviewer.formal_review_not_before_utc,
        holdout=holdout,
        reference_cells=reference_cells,
        signing_keys=signing_keys,
        evaluation_started_at_utc=generated_at_utc,
    )
    metrics, calibration, errors = compare_three_model_predictions(
        predictions,
        holdout,
        reference_cells=reference_cells,
        thresholds=thresholds,
    )
    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "metrics": output_dir / "three_model_metrics.csv",
        "calibration": output_dir / "three_model_calibration.csv",
        "error_categories": output_dir / "three_model_error_categories.csv",
        "summary": output_dir / "three_model_summary.md",
        "receipt": output_dir / "three_model_result_receipt.json",
    }
    existing = [str(path) for path in paths.values() if path.exists()]
    if existing:
        raise ControlledExperimentError(
            "Controlled experiment outputs are immutable and already exist: "
            + ", ".join(existing)
        )
    metrics.to_csv(paths["metrics"], index=False, lineterminator="\n")
    calibration.to_csv(paths["calibration"], index=False, lineterminator="\n")
    errors.to_csv(paths["error_categories"], index=False, lineterminator="\n")
    paths["summary"].write_text(_result_summary(metrics), encoding="utf-8")
    receipt: dict[str, object] = {
        "artifact_schema": RESULT_RECEIPT_SCHEMA,
        "experiment_id": acquisition.experiment_id,
        "study_area": acquisition.study_area,
        "generated_at": _format_utc(generated_at_utc),
        "acquisition_manifest_sha256": acquisition.manifest_sha256,
        "reviewer_calibration_file_sha256": reviewer_file_sha,
        "reviewer_calibration_receipt_sha256": reviewer.receipt_sha256,
        "acquisition_authority_receipt_sha256": (acquisition.authority_receipt_sha256),
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "reference_cell_receipt_file_sha256": reference_cells.receipt_file_sha256,
        "reference_cell_manifest_sha256": reference_cells.manifest_sha256,
        "reference_cell_evidence_sha256": reference_cells.evidence_file_sha256,
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
        "zero_division_convention": ZERO_DIVISION_CONVENTION,
        "assumptions": [
            "All metrics use signed, geometry-derived untouched holdout membership.",
            "Area errors are thresholded physical square metres on a validated equal-area grid.",
            "Comparison completion does not promote any flood layer into FPPS.",
        ],
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    _reject_private_paths(receipt)
    with paths["receipt"].open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return paths


def _load_model_evidence(
    source: str | Path,
    *,
    prediction_paths: Mapping[str, str | Path],
    model_artifact_paths: Mapping[str, str | Path],
    model_contract_paths: Mapping[str, str | Path],
    model_run_manifest_paths: Mapping[str, str | Path],
    acquisition: AcquisitionGateAssessment,
    reviewer_file_sha256: str,
    reviewer_not_before: datetime,
    holdout: VerifiedSpatialHoldout,
    reference_cells: VerifiedReferenceCellEvidence,
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
    reviewer_not_before = reviewer_not_before.astimezone(UTC)
    predictions: dict[str, pd.DataFrame] = {}
    thresholds: dict[str, float] = {}
    verified_models: list[dict[str, object]] = []
    for raw in manifest.to_dict("records"):
        family = _text(raw["model_family"], "model_family")
        model_id = _text(raw["model_id"], "model_id")
        prediction_path = Path(prediction_paths[family])
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
        if raw["reviewer_calibration_file_sha256"] != reviewer_file_sha256:
            raise ControlledExperimentError(f"{family}: reviewer-receipt substitution.")
        completed = _timestamp(raw["completed_at_utc"], f"{family} completed_at_utc")
        if completed < holdout_time or completed < reviewer_not_before:
            raise ControlledExperimentError(
                f"{family}: model evidence predates the frozen holdout or calibration authority."
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
            reviewer_file_sha256=reviewer_file_sha256,
            holdout=holdout,
            reference_cells=reference_cells,
            signing_keys=signing_keys,
            reviewer_not_before=reviewer_not_before,
            evaluation_started_at_utc=evaluation_started,
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
                "decision_threshold": threshold,
                "threshold_selection_scope": run["threshold_selection_scope"],
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
    reviewer_file_sha256: str,
    holdout: VerifiedSpatialHoldout,
    reference_cells: VerifiedReferenceCellEvidence,
    signing_keys: Mapping[str, bytes],
    reviewer_not_before: datetime,
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
        "reviewer_calibration_file_sha256",
        "spatial_holdout_manifest_sha256",
        "spatial_holdout_membership_sha256",
        "reference_cell_receipt_file_sha256",
        "reference_cell_manifest_sha256",
        "reference_cell_evidence_sha256",
        "training_partition_sha256",
        "threshold_selection_data_sha256",
        "decision_threshold",
        "threshold_selected_at_utc",
        "threshold_selection_scope",
        "holdout_evaluated_during_threshold_selection",
        "completed_at_utc",
        "execution_status",
        "spatial_holdout_untouched",
        "can_feed_decision_layer",
        "official_warning",
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
        "reviewer_calibration_file_sha256": reviewer_file_sha256,
        "spatial_holdout_manifest_sha256": holdout.manifest_sha256,
        "spatial_holdout_membership_sha256": holdout.membership_sha256,
        "reference_cell_receipt_file_sha256": reference_cells.receipt_file_sha256,
        "reference_cell_manifest_sha256": reference_cells.manifest_sha256,
        "reference_cell_evidence_sha256": reference_cells.evidence_file_sha256,
        "training_partition_sha256": holdout.training_partition_sha256,
    }
    for field, expected in expected_lineage.items():
        if payload[field] != expected:
            raise ControlledExperimentError(
                f"{family}: signed {field} was substituted."
            )
    _sha256(
        payload["threshold_selection_data_sha256"],
        f"{family} threshold_selection_data_sha256",
    )
    if not _bounded_probability(payload["decision_threshold"]):
        raise ControlledExperimentError(f"{family}: signed threshold is invalid.")
    selected = _timestamp(
        payload["threshold_selected_at_utc"],
        f"{family} threshold_selected_at_utc",
    )
    completed = _timestamp(payload["completed_at_utc"], f"{family} completed_at_utc")
    frozen = _timestamp(holdout.receipt["frozen_at_utc"], "holdout frozen_at_utc")
    if selected < frozen or selected < reviewer_not_before or completed <= selected:
        raise ControlledExperimentError(
            f"{family}: threshold was not fixed after authority and before completion."
        )
    if completed > evaluation_started_at_utc:
        raise ControlledExperimentError(
            f"{family}: signed model run completes after evaluation started."
        )
    if payload["threshold_selection_scope"] != "training_only_pre_holdout":
        raise ControlledExperimentError(
            f"{family}: threshold selection was not training-only."
        )
    if payload["holdout_evaluated_during_threshold_selection"] is not False:
        raise ControlledExperimentError(
            f"{family}: holdout influenced threshold selection."
        )
    if (
        payload["execution_status"] != "completed"
        or payload["spatial_holdout_untouched"] is not True
        or payload["can_feed_decision_layer"] is not False
        or payload["official_warning"] is not False
    ):
        raise ControlledExperimentError(
            f"{family}: signed run has unsafe status fields."
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


def _result_summary(metrics: pd.DataFrame) -> str:
    lines = [
        "# Controlled three-model experiment",
        "",
        "Status: completed report-only comparison on one untouched spatial holdout.",
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
        ]
    )
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
        if split not in {"train", "holdout"}:
            raise ControlledExperimentError(
                "Holdout feature split must be train or holdout."
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
        if split not in {"train", "holdout"}:
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


def _verify_gate_receipt(receipt: Mapping[str, object]) -> None:
    if receipt.get("artifact_schema") != GATE_RECEIPT_SCHEMA:
        raise ControlledExperimentError("Gate receipt schema is unsupported.")
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
    try:
        value = json.loads(content.decode("utf-8"))
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
