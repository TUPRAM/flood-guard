"""Fail-closed reviewer-calibration evidence for the flood-label factory.

Calibration is deliberately separate from production review.  The functions in
this module bind each named reviewer to locked, blinded annotations and their
canonical cell rasters on a pre-assigned ``reviewer_calibration`` query set.
Scores are measured against a separately frozen expert/adjudicated reference.
Neither the reference, reviewer cells, nor the calibration receipt is eligible
for query-model training, the FloodGuard decision layer, FPPS, or warnings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from floodguard.label_factory.agreement import AgreementError, compute_agreement
from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    annotation_content_sha256,
)
from floodguard.label_factory.contracts import DatasetRole, FloodLabel


CALIBRATION_RECEIPT_SCHEMA = "floodguard.reviewer_calibration_receipt.v1"
CALIBRATION_REFERENCE_SCHEMA = "floodguard.calibration_reference_cells.v1"
CALIBRATION_FAILURE_DIAGNOSTIC_SCHEMA = (
    "floodguard.reviewer_calibration_failure_diagnostic.v1"
)
ANNOTATION_CELL_RASTER_SCHEMA = "floodguard.annotation_cell_raster.v1"
DEFAULT_TAXONOMY_VERSION = "flood_label_v1"
MINIMUM_CALIBRATION_QUERY_COUNT = 8
DEFAULT_CALIBRATION_THRESHOLDS: Mapping[str, float] = {
    "temporary_flood_dice": 0.75,
    "cohen_kappa": 0.75,
    "mean_boundary_f1": 0.70,
    "critical_stratum_dice": 0.65,
}

QUERY_REQUIRED_COLUMNS = (
    "query_region_id",
    "event_id",
    "tile_id",
    "query_size_pixels",
    "resolution_m",
    "crs",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "dataset_role",
    "eligible_for_human_annotation",
    "eligible_for_active_selection",
    "eligible_for_query_model_training",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
    "source_timestamp",
    "assumptions",
)

REVIEWER_CELL_REQUIRED_COLUMNS = (
    "annotation_id",
    "event_id",
    "tile_id",
    "query_region_id",
    "reviewer_id",
    "cell_id",
    "row_index",
    "column_index",
    "label_code",
    "label_class",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "eligible_for_agreement",
    "eligible_for_query_model_training",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
    "source_timestamp",
    "assumptions",
)

REFERENCE_CELL_COLUMNS = (
    "reference_id",
    "event_id",
    "tile_id",
    "query_region_id",
    "cell_id",
    "row_index",
    "column_index",
    "label_code",
    "label_class",
    "crs",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "eligible_for_reviewer_calibration",
    "eligible_for_query_model_training",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
    "source_timestamp",
    "assumptions",
)

REFERENCE_INPUT_REQUIRED_COLUMNS = (
    "event_id",
    "tile_id",
    "query_region_id",
    "cell_id",
    "row_index",
    "column_index",
    "label_code",
)

STRATA_REQUIRED_COLUMNS = ("query_region_id", "stratum")


class ReviewerCalibrationError(ValueError):
    """Raised when calibration evidence is incomplete, inconsistent, or failing."""


@dataclass(frozen=True, slots=True)
class CalibrationReferenceManifest:
    """Self-hashed manifest for immutable calibration-reference cells."""

    reference_id: str
    authority_type: str
    authority_id: str
    protocol_version: str
    taxonomy_version: str
    created_at_utc: datetime
    query_manifest_sha256: str
    reference_cells_sha256: str
    reference_cells_file: str
    query_region_ids: tuple[str, ...]
    cell_count: int
    grid_contract_sha256_by_query: tuple[tuple[str, str], ...]
    source_registry_sha256_by_query: tuple[tuple[str, str], ...]
    source_timestamp_by_query: tuple[tuple[str, str], ...]
    assumptions: str
    manifest_sha256: str

    def to_dict(self, *, include_self_hash: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "artifact_schema": CALIBRATION_REFERENCE_SCHEMA,
            "reference_id": self.reference_id,
            "authority_type": self.authority_type,
            "authority_id": self.authority_id,
            "protocol_version": self.protocol_version,
            "taxonomy_version": self.taxonomy_version,
            "created_at_utc": _iso_utc(self.created_at_utc),
            "query_manifest_sha256": self.query_manifest_sha256,
            "reference_cells_sha256": self.reference_cells_sha256,
            "reference_cells_file": self.reference_cells_file,
            "query_region_ids": list(self.query_region_ids),
            "query_count": len(self.query_region_ids),
            "cell_count": self.cell_count,
            "grid_contract_sha256_by_query": dict(
                self.grid_contract_sha256_by_query
            ),
            "source_registry_sha256_by_query": dict(
                self.source_registry_sha256_by_query
            ),
            "source_timestamp_by_query": dict(self.source_timestamp_by_query),
            "assumptions": self.assumptions,
            "eligible_for_reviewer_calibration": True,
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        if include_self_hash:
            payload["manifest_sha256"] = self.manifest_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReviewerCalibrationReceipt:
    """Self-hashed proof that named reviewers passed a fixed calibration set."""

    reviewer_ids: tuple[str, ...]
    protocol_version: str
    taxonomy_version: str
    calibration_completed_at_utc: datetime
    formal_review_not_before_utc: datetime
    query_manifest_sha256: str
    query_region_ids: tuple[str, ...]
    annotation_sha256_by_id: tuple[tuple[str, str], ...]
    annotation_ids_by_reviewer: tuple[tuple[str, tuple[str, ...]], ...]
    reviewer_cell_sha256_by_reviewer: tuple[tuple[str, str], ...]
    reviewer_cell_manifest_sha256_by_reviewer: tuple[tuple[str, str], ...]
    calibration_reference_manifest_sha256: str
    calibration_reference_cells_sha256: str
    grid_contract_sha256_by_query: tuple[tuple[str, str], ...]
    source_registry_sha256_by_query: tuple[tuple[str, str], ...]
    source_timestamp_by_query: tuple[tuple[str, str], ...]
    metrics_by_reviewer: tuple[tuple[str, Mapping[str, Any]], ...]
    thresholds: tuple[tuple[str, float], ...]
    query_strata_sha256: str
    assumptions: str
    receipt_sha256: str

    def to_dict(self, *, include_self_hash: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "artifact_schema": CALIBRATION_RECEIPT_SCHEMA,
            "reviewer_ids": list(self.reviewer_ids),
            "protocol_version": self.protocol_version,
            "taxonomy_version": self.taxonomy_version,
            "calibration_completed_at_utc": _iso_utc(
                self.calibration_completed_at_utc
            ),
            "formal_review_not_before_utc": _iso_utc(
                self.formal_review_not_before_utc
            ),
            "query_manifest_sha256": self.query_manifest_sha256,
            "query_region_ids": list(self.query_region_ids),
            "query_count": len(self.query_region_ids),
            "annotation_sha256_by_id": dict(self.annotation_sha256_by_id),
            "annotation_ids_by_reviewer": {
                reviewer_id: list(annotation_ids)
                for reviewer_id, annotation_ids in self.annotation_ids_by_reviewer
            },
            "reviewer_cell_sha256_by_reviewer": dict(
                self.reviewer_cell_sha256_by_reviewer
            ),
            "reviewer_cell_manifest_sha256_by_reviewer": dict(
                self.reviewer_cell_manifest_sha256_by_reviewer
            ),
            "calibration_reference_manifest_sha256": (
                self.calibration_reference_manifest_sha256
            ),
            "calibration_reference_cells_sha256": (
                self.calibration_reference_cells_sha256
            ),
            "grid_contract_sha256_by_query": dict(
                self.grid_contract_sha256_by_query
            ),
            "source_registry_sha256_by_query": dict(
                self.source_registry_sha256_by_query
            ),
            "source_timestamp_by_query": dict(self.source_timestamp_by_query),
            "metrics_by_reviewer": {
                reviewer_id: dict(metrics)
                for reviewer_id, metrics in self.metrics_by_reviewer
            },
            "thresholds": dict(self.thresholds),
            "query_strata_sha256": self.query_strata_sha256,
            "calibration_passed": True,
            "assumptions": self.assumptions,
            "dataset_role": DatasetRole.REVIEWER_CALIBRATION.value,
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        if include_self_hash:
            payload["receipt_sha256"] = self.receipt_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReviewerCalibrationFailureDiagnostic:
    """Confidential evidence that one or more reviewers did not pass.

    This artifact is intentionally not a receipt and cannot authorize formal
    review.  It exists only to support targeted human remediation while
    preserving the exact evidence and scores that produced the failure.
    """

    reviewer_ids: tuple[str, ...]
    failed_reviewer_ids: tuple[str, ...]
    protocol_version: str
    taxonomy_version: str
    calibration_completed_at_utc: datetime
    diagnostic_created_at_utc: datetime
    query_manifest_sha256: str
    query_region_ids: tuple[str, ...]
    annotation_sha256_by_id: tuple[tuple[str, str], ...]
    annotation_ids_by_reviewer: tuple[tuple[str, tuple[str, ...]], ...]
    reviewer_cell_sha256_by_reviewer: tuple[tuple[str, str], ...]
    reviewer_cell_manifest_sha256_by_reviewer: tuple[tuple[str, str], ...]
    calibration_reference_manifest_sha256: str
    calibration_reference_cells_sha256: str
    grid_contract_sha256_by_query: tuple[tuple[str, str], ...]
    source_registry_sha256_by_query: tuple[tuple[str, str], ...]
    source_timestamp_by_query: tuple[tuple[str, str], ...]
    metrics_by_reviewer: tuple[tuple[str, Mapping[str, Any]], ...]
    thresholds: tuple[tuple[str, float], ...]
    failure_reasons_by_reviewer: tuple[tuple[str, tuple[str, ...]], ...]
    query_strata_sha256: str
    assumptions: str
    diagnostic_sha256: str

    def to_dict(self, *, include_self_hash: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "artifact_schema": CALIBRATION_FAILURE_DIAGNOSTIC_SCHEMA,
            "reviewer_ids": list(self.reviewer_ids),
            "failed_reviewer_ids": list(self.failed_reviewer_ids),
            "protocol_version": self.protocol_version,
            "taxonomy_version": self.taxonomy_version,
            "calibration_completed_at_utc": _iso_utc(
                self.calibration_completed_at_utc
            ),
            "diagnostic_created_at_utc": _iso_utc(self.diagnostic_created_at_utc),
            "query_manifest_sha256": self.query_manifest_sha256,
            "query_region_ids": list(self.query_region_ids),
            "query_count": len(self.query_region_ids),
            "annotation_sha256_by_id": dict(self.annotation_sha256_by_id),
            "annotation_ids_by_reviewer": {
                reviewer_id: list(annotation_ids)
                for reviewer_id, annotation_ids in self.annotation_ids_by_reviewer
            },
            "reviewer_cell_sha256_by_reviewer": dict(
                self.reviewer_cell_sha256_by_reviewer
            ),
            "reviewer_cell_manifest_sha256_by_reviewer": dict(
                self.reviewer_cell_manifest_sha256_by_reviewer
            ),
            "calibration_reference_manifest_sha256": (
                self.calibration_reference_manifest_sha256
            ),
            "calibration_reference_cells_sha256": (
                self.calibration_reference_cells_sha256
            ),
            "grid_contract_sha256_by_query": dict(
                self.grid_contract_sha256_by_query
            ),
            "source_registry_sha256_by_query": dict(
                self.source_registry_sha256_by_query
            ),
            "source_timestamp_by_query": dict(self.source_timestamp_by_query),
            "metrics_by_reviewer": {
                reviewer_id: dict(metrics)
                for reviewer_id, metrics in self.metrics_by_reviewer
            },
            "thresholds": dict(self.thresholds),
            "failure_reasons_by_reviewer": {
                reviewer_id: list(reasons)
                for reviewer_id, reasons in self.failure_reasons_by_reviewer
            },
            "query_strata_sha256": self.query_strata_sha256,
            "calibration_passed": False,
            "formal_review_authorized": False,
            "confidential": True,
            "assumptions": self.assumptions,
            "dataset_role": DatasetRole.REVIEWER_CALIBRATION.value,
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        if include_self_hash:
            payload["diagnostic_sha256"] = self.diagnostic_sha256
        return payload


@dataclass(frozen=True, slots=True)
class CalibrationReferenceOutputs:
    """Paths written for an immutable reference cell artifact and manifest."""

    cells: Path
    manifest: Path


def write_calibration_reference_artifacts(
    reference_cells: pd.DataFrame | str | Path,
    query_manifest: pd.DataFrame | str | Path,
    *,
    reference_id: str,
    authority_type: str,
    authority_id: str,
    protocol_version: str,
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
    created_at_utc: datetime,
    assumptions: str,
    cells_output_path: str | Path,
    manifest_output_path: str | Path,
) -> CalibrationReferenceOutputs:
    """Validate and exclusively write a fixed expert/adjudicated reference."""

    query_frame = _coerce_frame(query_manifest, "calibration query manifest")
    query_rows = _validate_calibration_query_manifest(query_frame)
    raw_cells = _coerce_frame(reference_cells, "calibration reference cells")
    normalized = _normalize_reference_cells(
        raw_cells,
        query_rows=query_rows,
        reference_id=_required_text(reference_id, "reference_id"),
    )
    authority_kind = _required_text(authority_type, "authority_type")
    if authority_kind not in {"expert_consensus", "adjudicated"}:
        raise ReviewerCalibrationError(
            "authority_type must be expert_consensus or adjudicated."
        )
    authority = _required_text(authority_id, "authority_id")
    protocol = _required_text(protocol_version, "protocol_version")
    taxonomy = _required_text(taxonomy_version, "taxonomy_version")
    if taxonomy != DEFAULT_TAXONOMY_VERSION:
        raise ReviewerCalibrationError(
            f"taxonomy_version must be {DEFAULT_TAXONOMY_VERSION!r}."
        )
    created = _as_utc(created_at_utc, "created_at_utc")
    note = _required_text(assumptions, "assumptions")
    cells_path = Path(cells_output_path)
    manifest_path = Path(manifest_output_path)
    if cells_path.suffix.lower() != ".csv" or manifest_path.suffix.lower() != ".json":
        raise ReviewerCalibrationError(
            "Reference cells must be CSV and the reference manifest must be JSON."
        )
    if cells_path.exists() or manifest_path.exists():
        raise ReviewerCalibrationError(
            "Calibration reference outputs are immutable and must not be overwritten."
        )
    if cells_path.resolve() == manifest_path.resolve():
        raise ReviewerCalibrationError("Reference cell and manifest paths must differ.")
    cells_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    cells_created = False
    manifest_created = False
    try:
        with cells_path.open("x", encoding="utf-8", newline="") as handle:
            cells_created = True
            normalized.to_csv(handle, index=False, lineterminator="\n")
        values = {
            "reference_id": _required_text(reference_id, "reference_id"),
            "authority_type": authority_kind,
            "authority_id": authority,
            "protocol_version": protocol,
            "taxonomy_version": taxonomy,
            "created_at_utc": created,
            "query_manifest_sha256": _artifact_sha256(query_manifest, query_frame),
            "reference_cells_sha256": _file_sha256(cells_path),
            "reference_cells_file": cells_path.name,
            "query_region_ids": tuple(sorted(query_rows)),
            "cell_count": len(normalized),
            "grid_contract_sha256_by_query": tuple(
                sorted(
                    (query_id, str(row["grid_contract_sha256"]).lower())
                    for query_id, row in query_rows.items()
                )
            ),
            "source_registry_sha256_by_query": tuple(
                sorted(
                    (query_id, str(row["source_registry_sha256"]).lower())
                    for query_id, row in query_rows.items()
                )
            ),
            "source_timestamp_by_query": tuple(
                sorted(
                    (query_id, _normalized_timestamp_text(row["source_timestamp"]))
                    for query_id, row in query_rows.items()
                )
            ),
            "assumptions": note,
        }
        provisional = CalibrationReferenceManifest(**values, manifest_sha256="")
        manifest = CalibrationReferenceManifest(
            **values,
            manifest_sha256=_canonical_json_sha256(
                provisional.to_dict(include_self_hash=False)
            ),
        )
        _verify_reference_manifest(manifest)
        with manifest_path.open("x", encoding="utf-8") as handle:
            manifest_created = True
            json.dump(manifest.to_dict(), handle, sort_keys=True, indent=2)
            handle.write("\n")
    except Exception:
        # Keep exclusive-write semantics atomic from the caller's perspective.
        if manifest_created:
            manifest_path.unlink(missing_ok=True)
        if cells_created:
            cells_path.unlink(missing_ok=True)
        raise
    return CalibrationReferenceOutputs(cells=cells_path, manifest=manifest_path)


def load_calibration_reference_manifest(
    path: str | Path,
) -> CalibrationReferenceManifest:
    """Load and verify one self-hashed calibration-reference manifest."""

    source = Path(path)
    payload = _load_json_object(source, "calibration reference manifest")
    expected = {
        "artifact_schema",
        "reference_id",
        "authority_type",
        "authority_id",
        "protocol_version",
        "taxonomy_version",
        "created_at_utc",
        "query_manifest_sha256",
        "reference_cells_sha256",
        "reference_cells_file",
        "query_region_ids",
        "query_count",
        "cell_count",
        "grid_contract_sha256_by_query",
        "source_registry_sha256_by_query",
        "source_timestamp_by_query",
        "assumptions",
        "eligible_for_reviewer_calibration",
        "eligible_for_query_model_training",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "manifest_sha256",
    }
    _require_exact_keys(payload, expected, "calibration reference manifest")
    try:
        manifest = CalibrationReferenceManifest(
            reference_id=_required_text(payload["reference_id"], "reference_id"),
            authority_type=_required_text(payload["authority_type"], "authority_type"),
            authority_id=_required_text(payload["authority_id"], "authority_id"),
            protocol_version=_required_text(
                payload["protocol_version"], "protocol_version"
            ),
            taxonomy_version=_required_text(
                payload["taxonomy_version"], "taxonomy_version"
            ),
            created_at_utc=_parse_timestamp(payload["created_at_utc"], "created_at_utc"),
            query_manifest_sha256=_require_sha256(
                payload["query_manifest_sha256"], "query_manifest_sha256"
            ),
            reference_cells_sha256=_require_sha256(
                payload["reference_cells_sha256"], "reference_cells_sha256"
            ),
            reference_cells_file=_safe_file_name(
                payload["reference_cells_file"], "reference_cells_file"
            ),
            query_region_ids=_string_tuple(payload["query_region_ids"], "query_region_ids"),
            cell_count=_positive_integer(payload["cell_count"], "cell_count"),
            grid_contract_sha256_by_query=_sha_mapping_tuple(
                payload["grid_contract_sha256_by_query"],
                "grid_contract_sha256_by_query",
            ),
            source_registry_sha256_by_query=_sha_mapping_tuple(
                payload["source_registry_sha256_by_query"],
                "source_registry_sha256_by_query",
            ),
            source_timestamp_by_query=_timestamp_mapping_tuple(
                payload["source_timestamp_by_query"], "source_timestamp_by_query"
            ),
            assumptions=_required_text(payload["assumptions"], "assumptions"),
            manifest_sha256=_require_sha256(
                payload["manifest_sha256"], "manifest_sha256"
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ReviewerCalibrationError):
            raise
        raise ReviewerCalibrationError(
            f"Invalid calibration reference manifest: {exc}"
        ) from exc
    if int(payload["query_count"]) != len(manifest.query_region_ids):
        raise ReviewerCalibrationError(
            "Calibration reference query_count does not match query_region_ids."
        )
    _require_reference_safety(payload)
    _verify_reference_manifest(manifest)
    return manifest


def _evaluate_reviewer_calibration_evidence(
    annotation_records: Sequence[AnnotationRecord],
    query_manifest: pd.DataFrame | str | Path,
    *,
    reviewer_cell_paths: Mapping[str, str | Path],
    reviewer_cell_manifest_paths: Mapping[str, str | Path],
    reference_cell_path: str | Path,
    reference_manifest_path: str | Path,
    query_strata: pd.DataFrame | str | Path,
    protocol_version: str,
    taxonomy_version: str,
    assumptions: str,
    thresholds: Mapping[str, float],
    boundary_tolerance_m: float,
) -> dict[str, Any]:
    """Validate and score calibration evidence without deciding pass/fail."""

    protocol = _required_text(protocol_version, "protocol_version")
    taxonomy = _required_text(taxonomy_version, "taxonomy_version")
    if taxonomy != DEFAULT_TAXONOMY_VERSION:
        raise ReviewerCalibrationError(
            f"taxonomy_version must be {DEFAULT_TAXONOMY_VERSION!r}."
        )
    note = _required_text(assumptions, "assumptions")
    threshold_values = _validate_thresholds(thresholds)
    if not math.isfinite(boundary_tolerance_m) or boundary_tolerance_m < 0:
        raise ReviewerCalibrationError(
            "boundary_tolerance_m must be finite and non-negative."
        )
    reviewer_ids = tuple(
        sorted(_required_text(key, "reviewer_id") for key in reviewer_cell_paths)
    )
    manifest_reviewer_ids = tuple(
        sorted(
            _required_text(key, "reviewer_id")
            for key in reviewer_cell_manifest_paths
        )
    )
    if reviewer_ids != manifest_reviewer_ids or len(reviewer_ids) < 2:
        raise ReviewerCalibrationError(
            "Reviewer cell and manifest mappings must name the same two or more reviewers."
        )

    query_frame = _coerce_frame(query_manifest, "calibration query manifest")
    query_rows = _validate_calibration_query_manifest(query_frame)
    query_ids = tuple(sorted(query_rows))
    query_sha = _artifact_sha256(query_manifest, query_frame)
    strata_frame = _coerce_frame(query_strata, "calibration query strata")
    strata_by_name = _validate_query_strata(strata_frame, query_ids)
    strata_sha = _artifact_sha256(query_strata, strata_frame)

    reference_manifest = load_calibration_reference_manifest(reference_manifest_path)
    reference_path = Path(reference_cell_path)
    _verify_reference_artifacts(
        reference_path,
        reference_manifest_path=Path(reference_manifest_path),
        manifest=reference_manifest,
        query_manifest_sha256=query_sha,
        query_rows=query_rows,
        protocol_version=protocol,
        taxonomy_version=taxonomy,
    )
    reference_cells = pd.read_csv(reference_path).fillna("")
    reference_cells = _validate_reference_cells(
        reference_cells, manifest=reference_manifest, query_rows=query_rows
    )

    latest = _latest_calibration_annotations(
        annotation_records,
        reviewer_ids=reviewer_ids,
        query_rows=query_rows,
        protocol_version=protocol,
    )
    annotation_hashes = {
        record.annotation_id: annotation_content_sha256(record)
        for record in latest.values()
    }
    cell_hashes: dict[str, str] = {}
    manifest_hashes: dict[str, str] = {}
    ids_by_reviewer: dict[str, tuple[str, ...]] = {}
    metrics_by_reviewer: dict[str, Mapping[str, Any]] = {}
    latest_lock = max(
        record.locked_at_utc
        for record in latest.values()
        if record.locked_at_utc is not None
    )
    calibration_completed = max(latest_lock, reference_manifest.created_at_utc)

    for reviewer_id in reviewer_ids:
        cell_path = Path(reviewer_cell_paths[reviewer_id])
        manifest_path = Path(reviewer_cell_manifest_paths[reviewer_id])
        reviewer_records = tuple(
            latest[(reviewer_id, query_id)] for query_id in query_ids
        )
        cells = _validate_reviewer_artifact(
            reviewer_id=reviewer_id,
            cell_path=cell_path,
            manifest_path=manifest_path,
            records=reviewer_records,
            query_rows=query_rows,
        )
        cell_hashes[reviewer_id] = _file_sha256(cell_path)
        manifest_hashes[reviewer_id] = _file_sha256(manifest_path)
        ids_by_reviewer[reviewer_id] = tuple(
            sorted(record.annotation_id for record in reviewer_records)
        )
        metrics_by_reviewer[reviewer_id] = _score_reviewer(
            reviewer_id,
            cells,
            reference_cells,
            query_rows=query_rows,
            strata_by_name=strata_by_name,
            boundary_tolerance_m=boundary_tolerance_m,
        )

    return {
        "reviewer_ids": reviewer_ids,
        "protocol_version": protocol,
        "taxonomy_version": taxonomy,
        "calibration_completed_at_utc": calibration_completed,
        "query_manifest_sha256": query_sha,
        "query_region_ids": query_ids,
        "annotation_sha256_by_id": tuple(sorted(annotation_hashes.items())),
        "annotation_ids_by_reviewer": tuple(sorted(ids_by_reviewer.items())),
        "reviewer_cell_sha256_by_reviewer": tuple(sorted(cell_hashes.items())),
        "reviewer_cell_manifest_sha256_by_reviewer": tuple(
            sorted(manifest_hashes.items())
        ),
        "calibration_reference_manifest_sha256": _file_sha256(
            Path(reference_manifest_path)
        ),
        "calibration_reference_cells_sha256": _file_sha256(reference_path),
        "grid_contract_sha256_by_query": (
            reference_manifest.grid_contract_sha256_by_query
        ),
        "source_registry_sha256_by_query": (
            reference_manifest.source_registry_sha256_by_query
        ),
        "source_timestamp_by_query": reference_manifest.source_timestamp_by_query,
        "metrics_by_reviewer": tuple(sorted(metrics_by_reviewer.items())),
        "thresholds": tuple(sorted(threshold_values.items())),
        "query_strata_sha256": strata_sha,
        "assumptions": note,
    }


def build_reviewer_calibration_receipt(
    annotation_records: Sequence[AnnotationRecord],
    query_manifest: pd.DataFrame | str | Path,
    *,
    reviewer_cell_paths: Mapping[str, str | Path],
    reviewer_cell_manifest_paths: Mapping[str, str | Path],
    reference_cell_path: str | Path,
    reference_manifest_path: str | Path,
    query_strata: pd.DataFrame | str | Path,
    protocol_version: str,
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
    formal_review_not_before_utc: datetime,
    assumptions: str,
    thresholds: Mapping[str, float] = DEFAULT_CALIBRATION_THRESHOLDS,
    boundary_tolerance_m: float = 20.0,
) -> ReviewerCalibrationReceipt:
    """Validate fixed calibration evidence, score every reviewer, and gate it."""
    evaluation = _evaluate_reviewer_calibration_evidence(
        annotation_records,
        query_manifest,
        reviewer_cell_paths=reviewer_cell_paths,
        reviewer_cell_manifest_paths=reviewer_cell_manifest_paths,
        reference_cell_path=reference_cell_path,
        reference_manifest_path=reference_manifest_path,
        query_strata=query_strata,
        protocol_version=protocol_version,
        taxonomy_version=taxonomy_version,
        assumptions=assumptions,
        thresholds=thresholds,
        boundary_tolerance_m=boundary_tolerance_m,
    )
    reviewer_ids = evaluation["reviewer_ids"]
    query_ids = evaluation["query_region_ids"]
    threshold_values = dict(evaluation["thresholds"])
    metrics_by_reviewer = dict(evaluation["metrics_by_reviewer"])
    for reviewer_id in reviewer_ids:
        _require_passing_metrics(
            reviewer_id,
            metrics_by_reviewer[reviewer_id],
            threshold_values,
            expected_query_ids=set(query_ids),
        )
    formal_not_before = _as_utc(
        formal_review_not_before_utc, "formal_review_not_before_utc"
    )
    if formal_not_before < evaluation["calibration_completed_at_utc"]:
        raise ReviewerCalibrationError(
            "formal_review_not_before_utc must not precede calibration completion."
        )
    values = dict(evaluation)
    values.pop("reference_manifest", None)
    values.pop("query_rows", None)
    values["formal_review_not_before_utc"] = formal_not_before
    values = {
        "reviewer_ids": values["reviewer_ids"],
        "protocol_version": values["protocol_version"],
        "taxonomy_version": values["taxonomy_version"],
        "calibration_completed_at_utc": values["calibration_completed_at_utc"],
        "formal_review_not_before_utc": formal_not_before,
        "query_manifest_sha256": values["query_manifest_sha256"],
        "query_region_ids": values["query_region_ids"],
        "annotation_sha256_by_id": values["annotation_sha256_by_id"],
        "annotation_ids_by_reviewer": values["annotation_ids_by_reviewer"],
        "reviewer_cell_sha256_by_reviewer": values[
            "reviewer_cell_sha256_by_reviewer"
        ],
        "reviewer_cell_manifest_sha256_by_reviewer": values[
            "reviewer_cell_manifest_sha256_by_reviewer"
        ],
        "calibration_reference_manifest_sha256": values[
            "calibration_reference_manifest_sha256"
        ],
        "calibration_reference_cells_sha256": values[
            "calibration_reference_cells_sha256"
        ],
        "grid_contract_sha256_by_query": values[
            "grid_contract_sha256_by_query"
        ],
        "source_registry_sha256_by_query": values[
            "source_registry_sha256_by_query"
        ],
        "source_timestamp_by_query": values["source_timestamp_by_query"],
        "metrics_by_reviewer": values["metrics_by_reviewer"],
        "thresholds": values["thresholds"],
        "query_strata_sha256": values["query_strata_sha256"],
        "assumptions": values["assumptions"],
    }
    provisional = ReviewerCalibrationReceipt(**values, receipt_sha256="")
    receipt = ReviewerCalibrationReceipt(
        **values,
        receipt_sha256=_canonical_json_sha256(
            provisional.to_dict(include_self_hash=False)
        ),
    )
    verify_reviewer_calibration_receipt(receipt)
    return receipt


def write_reviewer_calibration_receipt(
    receipt: ReviewerCalibrationReceipt, path: str | Path
) -> Path:
    """Exclusively write a fully verified calibration receipt."""

    verify_reviewer_calibration_receipt(receipt)
    target = Path(path)
    if target.suffix.lower() != ".json":
        raise ReviewerCalibrationError("Calibration receipt output must be JSON.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(receipt.to_dict(), handle, sort_keys=True, indent=2)
        handle.write("\n")
    return target


def build_reviewer_calibration_failure_diagnostic(
    annotation_records: Sequence[AnnotationRecord],
    query_manifest: pd.DataFrame | str | Path,
    *,
    reviewer_cell_paths: Mapping[str, str | Path],
    reviewer_cell_manifest_paths: Mapping[str, str | Path],
    reference_cell_path: str | Path,
    reference_manifest_path: str | Path,
    query_strata: pd.DataFrame | str | Path,
    protocol_version: str,
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
    diagnostic_created_at_utc: datetime,
    assumptions: str,
    thresholds: Mapping[str, float] = DEFAULT_CALIBRATION_THRESHOLDS,
    boundary_tolerance_m: float = 20.0,
) -> ReviewerCalibrationFailureDiagnostic:
    """Build a confidential failure artifact without authorizing formal review.

    The artifact can be built only from otherwise valid calibration evidence
    where at least one reviewer misses a configured threshold.  It is rejected
    when everyone passes so it cannot be used as a substitute pass receipt.
    """

    evaluation = _evaluate_reviewer_calibration_evidence(
        annotation_records,
        query_manifest,
        reviewer_cell_paths=reviewer_cell_paths,
        reviewer_cell_manifest_paths=reviewer_cell_manifest_paths,
        reference_cell_path=reference_cell_path,
        reference_manifest_path=reference_manifest_path,
        query_strata=query_strata,
        protocol_version=protocol_version,
        taxonomy_version=taxonomy_version,
        assumptions=assumptions,
        thresholds=thresholds,
        boundary_tolerance_m=boundary_tolerance_m,
    )
    reviewer_ids = tuple(evaluation["reviewer_ids"])
    query_ids = tuple(evaluation["query_region_ids"])
    threshold_values = dict(evaluation["thresholds"])
    metrics = dict(evaluation["metrics_by_reviewer"])
    failures = {
        reviewer_id: _calibration_metric_failures(
            reviewer_id,
            metrics[reviewer_id],
            threshold_values,
            expected_query_ids=set(query_ids),
        )
        for reviewer_id in reviewer_ids
    }
    failed_ids = tuple(
        reviewer_id for reviewer_id in reviewer_ids if failures[reviewer_id]
    )
    if not failed_ids:
        raise ReviewerCalibrationError(
            "All reviewers passed; a failure diagnostic must not be created."
        )
    created = _as_utc(diagnostic_created_at_utc, "diagnostic_created_at_utc")
    if created < evaluation["calibration_completed_at_utc"]:
        raise ReviewerCalibrationError(
            "diagnostic_created_at_utc must not precede calibration completion."
        )
    values = {
        "reviewer_ids": reviewer_ids,
        "failed_reviewer_ids": failed_ids,
        "protocol_version": evaluation["protocol_version"],
        "taxonomy_version": evaluation["taxonomy_version"],
        "calibration_completed_at_utc": evaluation[
            "calibration_completed_at_utc"
        ],
        "diagnostic_created_at_utc": created,
        "query_manifest_sha256": evaluation["query_manifest_sha256"],
        "query_region_ids": query_ids,
        "annotation_sha256_by_id": evaluation["annotation_sha256_by_id"],
        "annotation_ids_by_reviewer": evaluation["annotation_ids_by_reviewer"],
        "reviewer_cell_sha256_by_reviewer": evaluation[
            "reviewer_cell_sha256_by_reviewer"
        ],
        "reviewer_cell_manifest_sha256_by_reviewer": evaluation[
            "reviewer_cell_manifest_sha256_by_reviewer"
        ],
        "calibration_reference_manifest_sha256": evaluation[
            "calibration_reference_manifest_sha256"
        ],
        "calibration_reference_cells_sha256": evaluation[
            "calibration_reference_cells_sha256"
        ],
        "grid_contract_sha256_by_query": evaluation[
            "grid_contract_sha256_by_query"
        ],
        "source_registry_sha256_by_query": evaluation[
            "source_registry_sha256_by_query"
        ],
        "source_timestamp_by_query": evaluation["source_timestamp_by_query"],
        "metrics_by_reviewer": evaluation["metrics_by_reviewer"],
        "thresholds": evaluation["thresholds"],
        "failure_reasons_by_reviewer": tuple(sorted(failures.items())),
        "query_strata_sha256": evaluation["query_strata_sha256"],
        "assumptions": evaluation["assumptions"],
    }
    provisional = ReviewerCalibrationFailureDiagnostic(
        **values, diagnostic_sha256=""
    )
    diagnostic = ReviewerCalibrationFailureDiagnostic(
        **values,
        diagnostic_sha256=_canonical_json_sha256(
            provisional.to_dict(include_self_hash=False)
        ),
    )
    verify_reviewer_calibration_failure_diagnostic(diagnostic)
    return diagnostic


def verify_reviewer_calibration_failure_diagnostic(
    diagnostic: ReviewerCalibrationFailureDiagnostic,
) -> None:
    """Reject tampering, fake failure claims, and unsafe eligibility fields."""

    reviewer_ids = tuple(diagnostic.reviewer_ids)
    if (
        len(reviewer_ids) < 2
        or reviewer_ids != tuple(sorted(set(reviewer_ids)))
    ):
        raise ReviewerCalibrationError(
            "Failure diagnostic requires two or more unique sorted reviewers."
        )
    failed_ids = tuple(diagnostic.failed_reviewer_ids)
    if (
        not failed_ids
        or failed_ids != tuple(sorted(set(failed_ids)))
        or not set(failed_ids).issubset(reviewer_ids)
    ):
        raise ReviewerCalibrationError(
            "Failure diagnostic failed_reviewer_ids are invalid."
        )
    _required_text(diagnostic.protocol_version, "protocol_version")
    if diagnostic.taxonomy_version != DEFAULT_TAXONOMY_VERSION:
        raise ReviewerCalibrationError("Failure diagnostic taxonomy is unsupported.")
    completed = _as_utc(
        diagnostic.calibration_completed_at_utc,
        "calibration_completed_at_utc",
    )
    created = _as_utc(
        diagnostic.diagnostic_created_at_utc,
        "diagnostic_created_at_utc",
    )
    if created < completed:
        raise ReviewerCalibrationError(
            "Failure diagnostic predates calibration completion."
        )
    query_ids = tuple(diagnostic.query_region_ids)
    if (
        len(query_ids) < MINIMUM_CALIBRATION_QUERY_COUNT
        or query_ids != tuple(sorted(set(query_ids)))
    ):
        raise ReviewerCalibrationError(
            "Failure diagnostic query coverage is invalid."
        )
    for field in (
        "query_manifest_sha256",
        "calibration_reference_manifest_sha256",
        "calibration_reference_cells_sha256",
        "query_strata_sha256",
        "diagnostic_sha256",
    ):
        _require_sha256(getattr(diagnostic, field), field)
    _required_text(diagnostic.assumptions, "assumptions")
    annotation_ids = dict(diagnostic.annotation_ids_by_reviewer)
    annotation_hashes = dict(diagnostic.annotation_sha256_by_id)
    cell_hashes = dict(diagnostic.reviewer_cell_sha256_by_reviewer)
    cell_manifest_hashes = dict(
        diagnostic.reviewer_cell_manifest_sha256_by_reviewer
    )
    metrics = dict(diagnostic.metrics_by_reviewer)
    failures = dict(diagnostic.failure_reasons_by_reviewer)
    for name, mapping in (
        ("annotation_ids_by_reviewer", annotation_ids),
        ("reviewer_cell_sha256_by_reviewer", cell_hashes),
        ("reviewer_cell_manifest_sha256_by_reviewer", cell_manifest_hashes),
        ("metrics_by_reviewer", metrics),
        ("failure_reasons_by_reviewer", failures),
    ):
        if set(mapping) != set(reviewer_ids):
            raise ReviewerCalibrationError(
                f"Failure diagnostic {name} reviewer coverage is not exact."
            )
    expected_annotation_ids: set[str] = set()
    for _reviewer_id, ids in annotation_ids.items():
        if (
            len(ids) != len(query_ids)
            or len(ids) != len(set(ids))
            or expected_annotation_ids.intersection(ids)
        ):
            raise ReviewerCalibrationError(
                "Failure diagnostic annotation coverage is not exact."
            )
        expected_annotation_ids.update(ids)
    if set(annotation_hashes) != expected_annotation_ids:
        raise ReviewerCalibrationError(
            "Failure diagnostic annotation hashes do not match annotation ids."
        )
    for digest in annotation_hashes.values():
        _require_sha256(digest, "annotation_sha256_by_id")
    for mapping, field in (
        (cell_hashes, "reviewer_cell_sha256_by_reviewer"),
        (cell_manifest_hashes, "reviewer_cell_manifest_sha256_by_reviewer"),
        (dict(diagnostic.grid_contract_sha256_by_query), "grid hashes"),
        (dict(diagnostic.source_registry_sha256_by_query), "source hashes"),
    ):
        for digest in mapping.values():
            _require_sha256(digest, field)
    expected_queries = set(query_ids)
    for name, mapping in (
        (
            "grid_contract_sha256_by_query",
            dict(diagnostic.grid_contract_sha256_by_query),
        ),
        (
            "source_registry_sha256_by_query",
            dict(diagnostic.source_registry_sha256_by_query),
        ),
        ("source_timestamp_by_query", dict(diagnostic.source_timestamp_by_query)),
    ):
        if set(mapping) != expected_queries:
            raise ReviewerCalibrationError(
                f"Failure diagnostic {name} query coverage is not exact."
            )
    for timestamp in dict(diagnostic.source_timestamp_by_query).values():
        _parse_timestamp(timestamp, "source_timestamp_by_query")
    threshold_values = _validate_thresholds(dict(diagnostic.thresholds))
    recomputed: dict[str, tuple[str, ...]] = {}
    for reviewer_id in reviewer_ids:
        recomputed[reviewer_id] = _calibration_metric_failures(
            reviewer_id,
            metrics[reviewer_id],
            threshold_values,
            expected_query_ids=set(query_ids),
        )
    if recomputed != failures:
        raise ReviewerCalibrationError(
            "Failure diagnostic reasons do not match the measured metrics."
        )
    if tuple(reviewer for reviewer in reviewer_ids if recomputed[reviewer]) != failed_ids:
        raise ReviewerCalibrationError(
            "Failure diagnostic reviewer status does not match measured metrics."
        )
    payload = diagnostic.to_dict()
    expected_safety = {
        "calibration_passed": False,
        "formal_review_authorized": False,
        "confidential": True,
        "dataset_role": DatasetRole.REVIEWER_CALIBRATION.value,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for field, expected in expected_safety.items():
        if payload.get(field) != expected:
            raise ReviewerCalibrationError(
                f"Failure diagnostic has unsafe {field}."
            )
    expected_self_hash = _canonical_json_sha256(
        diagnostic.to_dict(include_self_hash=False)
    )
    if diagnostic.diagnostic_sha256 != expected_self_hash:
        raise ReviewerCalibrationError(
            "Failure diagnostic self-hash does not match."
        )


def write_reviewer_calibration_failure_diagnostic(
    diagnostic: ReviewerCalibrationFailureDiagnostic,
    path: str | Path,
) -> Path:
    """Exclusively write a verified confidential non-pass diagnostic."""

    verify_reviewer_calibration_failure_diagnostic(diagnostic)
    target = Path(path)
    if target.suffix.lower() != ".json":
        raise ReviewerCalibrationError(
            "Calibration failure diagnostic output must be JSON."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(diagnostic.to_dict(), handle, sort_keys=True, indent=2)
        handle.write("\n")
    return target


def load_reviewer_calibration_receipt(
    path: str | Path,
) -> ReviewerCalibrationReceipt:
    """Load and cryptographically verify a calibration receipt."""

    payload = _load_json_object(Path(path), "reviewer calibration receipt")
    expected = {
        "artifact_schema",
        "reviewer_ids",
        "protocol_version",
        "taxonomy_version",
        "calibration_completed_at_utc",
        "formal_review_not_before_utc",
        "query_manifest_sha256",
        "query_region_ids",
        "query_count",
        "annotation_sha256_by_id",
        "annotation_ids_by_reviewer",
        "reviewer_cell_sha256_by_reviewer",
        "reviewer_cell_manifest_sha256_by_reviewer",
        "calibration_reference_manifest_sha256",
        "calibration_reference_cells_sha256",
        "grid_contract_sha256_by_query",
        "source_registry_sha256_by_query",
        "source_timestamp_by_query",
        "metrics_by_reviewer",
        "thresholds",
        "query_strata_sha256",
        "calibration_passed",
        "assumptions",
        "dataset_role",
        "eligible_for_query_model_training",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "receipt_sha256",
    }
    _require_exact_keys(payload, expected, "reviewer calibration receipt")
    _require_receipt_safety(payload)
    try:
        annotation_ids = _mapping(payload["annotation_ids_by_reviewer"], "annotation_ids_by_reviewer")
        metrics = _mapping(payload["metrics_by_reviewer"], "metrics_by_reviewer")
        receipt = ReviewerCalibrationReceipt(
            reviewer_ids=_string_tuple(payload["reviewer_ids"], "reviewer_ids"),
            protocol_version=_required_text(payload["protocol_version"], "protocol_version"),
            taxonomy_version=_required_text(payload["taxonomy_version"], "taxonomy_version"),
            calibration_completed_at_utc=_parse_timestamp(
                payload["calibration_completed_at_utc"], "calibration_completed_at_utc"
            ),
            formal_review_not_before_utc=_parse_timestamp(
                payload["formal_review_not_before_utc"], "formal_review_not_before_utc"
            ),
            query_manifest_sha256=_require_sha256(payload["query_manifest_sha256"], "query_manifest_sha256"),
            query_region_ids=_string_tuple(payload["query_region_ids"], "query_region_ids"),
            annotation_sha256_by_id=_sha_mapping_tuple(payload["annotation_sha256_by_id"], "annotation_sha256_by_id"),
            annotation_ids_by_reviewer=tuple(
                sorted(
                    (
                        _required_text(reviewer_id, "reviewer_id"),
                        _string_tuple(ids, f"annotation_ids_by_reviewer[{reviewer_id}]"),
                    )
                    for reviewer_id, ids in annotation_ids.items()
                )
            ),
            reviewer_cell_sha256_by_reviewer=_sha_mapping_tuple(
                payload["reviewer_cell_sha256_by_reviewer"],
                "reviewer_cell_sha256_by_reviewer",
            ),
            reviewer_cell_manifest_sha256_by_reviewer=_sha_mapping_tuple(
                payload["reviewer_cell_manifest_sha256_by_reviewer"],
                "reviewer_cell_manifest_sha256_by_reviewer",
            ),
            calibration_reference_manifest_sha256=_require_sha256(
                payload["calibration_reference_manifest_sha256"],
                "calibration_reference_manifest_sha256",
            ),
            calibration_reference_cells_sha256=_require_sha256(
                payload["calibration_reference_cells_sha256"],
                "calibration_reference_cells_sha256",
            ),
            grid_contract_sha256_by_query=_sha_mapping_tuple(
                payload["grid_contract_sha256_by_query"],
                "grid_contract_sha256_by_query",
            ),
            source_registry_sha256_by_query=_sha_mapping_tuple(
                payload["source_registry_sha256_by_query"],
                "source_registry_sha256_by_query",
            ),
            source_timestamp_by_query=_timestamp_mapping_tuple(
                payload["source_timestamp_by_query"], "source_timestamp_by_query"
            ),
            metrics_by_reviewer=tuple(
                sorted(
                    (
                        _required_text(reviewer_id, "reviewer_id"),
                        _mapping(value, f"metrics_by_reviewer[{reviewer_id}]"),
                    )
                    for reviewer_id, value in metrics.items()
                )
            ),
            thresholds=tuple(
                sorted(_validate_thresholds(_mapping(payload["thresholds"], "thresholds")).items())
            ),
            query_strata_sha256=_require_sha256(payload["query_strata_sha256"], "query_strata_sha256"),
            assumptions=_required_text(payload["assumptions"], "assumptions"),
            receipt_sha256=_require_sha256(payload["receipt_sha256"], "receipt_sha256"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ReviewerCalibrationError):
            raise
        raise ReviewerCalibrationError(f"Invalid reviewer calibration receipt: {exc}") from exc
    if int(payload["query_count"]) != len(receipt.query_region_ids):
        raise ReviewerCalibrationError(
            "Calibration receipt query_count does not match query_region_ids."
        )
    verify_reviewer_calibration_receipt(receipt)
    return receipt


def verify_reviewer_calibration_receipt(
    receipt: ReviewerCalibrationReceipt,
) -> None:
    """Fail closed on receipt schema, safety, thresholds, lineage, or self-hash."""

    if not isinstance(receipt, ReviewerCalibrationReceipt):
        raise ReviewerCalibrationError(
            "receipt must be a ReviewerCalibrationReceipt."
        )
    _required_text(receipt.protocol_version, "protocol_version")
    _required_text(receipt.taxonomy_version, "taxonomy_version")
    _required_text(receipt.assumptions, "assumptions")
    _as_utc(receipt.calibration_completed_at_utc, "calibration_completed_at_utc")
    _as_utc(receipt.formal_review_not_before_utc, "formal_review_not_before_utc")
    for field_name in (
        "query_manifest_sha256",
        "calibration_reference_manifest_sha256",
        "calibration_reference_cells_sha256",
        "query_strata_sha256",
        "receipt_sha256",
    ):
        _require_sha256(getattr(receipt, field_name), field_name)
    if len(receipt.reviewer_ids) < 2 or len(set(receipt.reviewer_ids)) != len(
        receipt.reviewer_ids
    ):
        raise ReviewerCalibrationError(
            "Calibration receipt requires two or more unique reviewers."
        )
    if len(receipt.query_region_ids) < MINIMUM_CALIBRATION_QUERY_COUNT:
        raise ReviewerCalibrationError(
            f"Calibration receipt requires at least {MINIMUM_CALIBRATION_QUERY_COUNT} unique queries."
        )
    if len(set(receipt.query_region_ids)) != len(receipt.query_region_ids):
        raise ReviewerCalibrationError("Calibration query ids must be unique.")
    for query_id in receipt.query_region_ids:
        _required_text(query_id, "query_region_id")
    if receipt.taxonomy_version != DEFAULT_TAXONOMY_VERSION:
        raise ReviewerCalibrationError("Calibration taxonomy version is unsupported.")
    if receipt.formal_review_not_before_utc < receipt.calibration_completed_at_utc:
        raise ReviewerCalibrationError(
            "Formal review cannot begin before calibration completion."
        )
    reviewers = set(receipt.reviewer_ids)
    for name, pairs in (
        ("annotation_ids_by_reviewer", receipt.annotation_ids_by_reviewer),
        ("reviewer_cell_sha256_by_reviewer", receipt.reviewer_cell_sha256_by_reviewer),
        (
            "reviewer_cell_manifest_sha256_by_reviewer",
            receipt.reviewer_cell_manifest_sha256_by_reviewer,
        ),
        ("metrics_by_reviewer", receipt.metrics_by_reviewer),
    ):
        if (
            len(pairs) != len(reviewers)
            or {reviewer_id for reviewer_id, _value in pairs} != reviewers
        ):
            raise ReviewerCalibrationError(f"{name} does not exactly cover reviewers.")
    for reviewer_id in receipt.reviewer_ids:
        _required_text(reviewer_id, "reviewer_id")
    for _annotation_id, digest in receipt.annotation_sha256_by_id:
        _require_sha256(digest, "annotation_sha256_by_id")
    for name, pairs in (
        ("reviewer_cell_sha256_by_reviewer", receipt.reviewer_cell_sha256_by_reviewer),
        (
            "reviewer_cell_manifest_sha256_by_reviewer",
            receipt.reviewer_cell_manifest_sha256_by_reviewer,
        ),
    ):
        for _reviewer_id, digest in pairs:
            _require_sha256(digest, name)
    query_ids = set(receipt.query_region_ids)
    for name, pairs in (
        ("grid_contract_sha256_by_query", receipt.grid_contract_sha256_by_query),
        ("source_registry_sha256_by_query", receipt.source_registry_sha256_by_query),
        ("source_timestamp_by_query", receipt.source_timestamp_by_query),
    ):
        if (
            len(pairs) != len(query_ids)
            or {query_id for query_id, _value in pairs} != query_ids
        ):
            raise ReviewerCalibrationError(f"{name} does not exactly cover queries.")
    for _query_id, digest in receipt.grid_contract_sha256_by_query:
        _require_sha256(digest, "grid_contract_sha256_by_query")
    for _query_id, digest in receipt.source_registry_sha256_by_query:
        _require_sha256(digest, "source_registry_sha256_by_query")
    for _query_id, timestamp in receipt.source_timestamp_by_query:
        _parse_timestamp(timestamp, "source_timestamp_by_query")
    expected_annotation_count = len(reviewers) * len(query_ids)
    if len(receipt.annotation_sha256_by_id) != expected_annotation_count:
        raise ReviewerCalibrationError(
            "Calibration annotation hashes do not exactly cover reviewer/query assignments."
        )
    all_annotation_ids: list[str] = []
    for _reviewer_id, annotation_ids in receipt.annotation_ids_by_reviewer:
        if len(annotation_ids) != len(query_ids):
            raise ReviewerCalibrationError(
                "Each calibration reviewer must have one annotation per query."
            )
        all_annotation_ids.extend(annotation_ids)
        for annotation_id in annotation_ids:
            _required_text(annotation_id, "annotation_id")
    if set(all_annotation_ids) != {
        annotation_id for annotation_id, _sha in receipt.annotation_sha256_by_id
    } or len(all_annotation_ids) != len(set(all_annotation_ids)):
        raise ReviewerCalibrationError(
            "Calibration annotation id lists and content hashes disagree."
        )
    thresholds = dict(receipt.thresholds)
    _validate_thresholds(thresholds)
    for reviewer_id, metrics in receipt.metrics_by_reviewer:
        _require_passing_metrics(
            reviewer_id,
            metrics,
            thresholds,
            expected_query_ids=set(receipt.query_region_ids),
        )
    expected_hash = _canonical_json_sha256(
        receipt.to_dict(include_self_hash=False)
    )
    if receipt.receipt_sha256 != expected_hash:
        raise ReviewerCalibrationError(
            "Reviewer calibration receipt self-hash does not match its content."
        )


def require_formal_review_calibration(
    receipt: ReviewerCalibrationReceipt,
    *,
    annotation_records: Sequence[AnnotationRecord],
    reviewer_ids: Sequence[str],
    semantics: Mapping[str, Any],
) -> None:
    """Bind production reviewers, protocol, taxonomy, and timing to calibration."""

    verify_reviewer_calibration_receipt(receipt)
    expected_reviewers = {
        _required_text(reviewer_id, "reviewer_id") for reviewer_id in reviewer_ids
    }
    if expected_reviewers != set(receipt.reviewer_ids):
        raise ReviewerCalibrationError(
            "Formal reviewer identities do not exactly match the calibration receipt."
        )
    if not isinstance(semantics, Mapping) or semantics.get("taxonomy") != receipt.taxonomy_version:
        raise ReviewerCalibrationError(
            "Formal labelset taxonomy does not match the calibration receipt."
        )
    if not annotation_records:
        raise ReviewerCalibrationError("Formal review annotations must not be empty.")
    for record in annotation_records:
        if record.reviewer_id not in expected_reviewers:
            continue
        if record.protocol_version != receipt.protocol_version:
            raise ReviewerCalibrationError(
                f"Formal annotation {record.annotation_id} uses a different protocol."
            )
        if record.review_started_at < receipt.formal_review_not_before_utc:
            raise ReviewerCalibrationError(
                f"Formal annotation {record.annotation_id} began before calibration completed."
            )


def _validate_calibration_query_manifest(
    frame: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    _require_columns(frame, QUERY_REQUIRED_COLUMNS, "calibration query manifest")
    if len(frame) < MINIMUM_CALIBRATION_QUERY_COUNT:
        raise ReviewerCalibrationError(
            f"Calibration requires at least {MINIMUM_CALIBRATION_QUERY_COUNT} queries."
        )
    if frame["query_region_id"].astype(str).duplicated().any():
        raise ReviewerCalibrationError("Calibration query ids must be unique.")
    rows: dict[str, dict[str, Any]] = {}
    for raw in frame.fillna("").to_dict("records"):
        query_id = _required_text(raw["query_region_id"], "query_region_id")
        if str(raw["dataset_role"]).strip() != DatasetRole.REVIEWER_CALIBRATION.value:
            raise ReviewerCalibrationError(
                f"Calibration query {query_id} has the wrong dataset_role."
            )
        _positive_integer(raw["query_size_pixels"], "query_size_pixels")
        resolution = float(raw["resolution_m"])
        if not math.isfinite(resolution) or resolution <= 0:
            raise ReviewerCalibrationError("resolution_m must be finite and positive.")
        _require_sha256(raw["grid_contract_sha256"], "grid_contract_sha256")
        _require_sha256(raw["source_registry_sha256"], "source_registry_sha256")
        _parse_timestamp(raw["source_timestamp"], "source_timestamp")
        _required_text(raw["assumptions"], "assumptions")
        expected_flags = {
            "eligible_for_human_annotation": True,
            "eligible_for_active_selection": False,
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        for field, expected in expected_flags.items():
            if _strict_bool(raw[field], field) is not expected:
                raise ReviewerCalibrationError(
                    f"Calibration query {query_id} has unsafe {field}."
                )
        if "eligible_for_training_after_human_review" in raw and str(
            raw["eligible_for_training_after_human_review"]
        ).strip().lower() not in {"", "no"}:
            raise ReviewerCalibrationError(
                f"Calibration query {query_id} cannot become training data."
            )
        rows[query_id] = raw
    return rows


def _normalize_reference_cells(
    frame: pd.DataFrame,
    *,
    query_rows: Mapping[str, Mapping[str, Any]],
    reference_id: str,
) -> pd.DataFrame:
    _require_columns(frame, REFERENCE_INPUT_REQUIRED_COLUMNS, "reference cells")
    raw = frame.copy().fillna("")
    rows: list[dict[str, Any]] = []
    for source in raw.to_dict("records"):
        query_id = _required_text(source["query_region_id"], "query_region_id")
        query = query_rows.get(query_id)
        if query is None:
            raise ReviewerCalibrationError(
                f"Reference cells contain unknown query {query_id}."
            )
        label = _coerce_label(source["label_code"])
        rows.append(
            {
                "reference_id": reference_id,
                "event_id": _required_text(source["event_id"], "event_id"),
                "tile_id": _required_text(source["tile_id"], "tile_id"),
                "query_region_id": query_id,
                "cell_id": _required_text(source["cell_id"], "cell_id"),
                "row_index": _nonnegative_integer(source["row_index"], "row_index"),
                "column_index": _nonnegative_integer(
                    source["column_index"], "column_index"
                ),
                "label_code": int(label),
                "label_class": label.name.lower(),
                "crs": str(query["crs"]),
                "grid_id": str(query["grid_id"]),
                "grid_contract_sha256": str(query["grid_contract_sha256"]).lower(),
                "source_registry_sha256": str(query["source_registry_sha256"]).lower(),
                "eligible_for_reviewer_calibration": True,
                "eligible_for_query_model_training": False,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "source_timestamp": _normalized_timestamp_text(
                    query["source_timestamp"]
                ),
                "assumptions": str(query["assumptions"]).strip(),
            }
        )
    normalized = pd.DataFrame(rows, columns=REFERENCE_CELL_COLUMNS).sort_values(
        ["query_region_id", "row_index", "column_index"], kind="stable"
    ).reset_index(drop=True)
    _validate_cell_grid(normalized, query_rows=query_rows, label="reference cells")
    _require_not_255_only(normalized, label="reference cells")
    return normalized


def _validate_reference_cells(
    frame: pd.DataFrame,
    *,
    manifest: CalibrationReferenceManifest,
    query_rows: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    _require_columns(frame, REFERENCE_CELL_COLUMNS, "calibration reference cells")
    if len(frame) != manifest.cell_count:
        raise ReviewerCalibrationError(
            "Reference cell count does not match its manifest."
        )
    if set(frame["reference_id"].astype(str)) != {manifest.reference_id}:
        raise ReviewerCalibrationError("Reference id does not match its manifest.")
    _validate_cell_grid(frame, query_rows=query_rows, label="reference cells")
    _validate_cell_lineage_and_safety(frame, query_rows=query_rows, reference=True)
    _require_not_255_only(frame, label="reference cells")
    return frame.copy().fillna("")


def _verify_reference_artifacts(
    reference_path: Path,
    *,
    reference_manifest_path: Path,
    manifest: CalibrationReferenceManifest,
    query_manifest_sha256: str,
    query_rows: Mapping[str, Mapping[str, Any]],
    protocol_version: str,
    taxonomy_version: str,
) -> None:
    if not reference_path.is_file() or not reference_manifest_path.is_file():
        raise ReviewerCalibrationError("Calibration reference artifacts are missing.")
    if reference_path.name != manifest.reference_cells_file:
        raise ReviewerCalibrationError(
            "Reference cell filename does not match its immutable manifest."
        )
    if _file_sha256(reference_path) != manifest.reference_cells_sha256:
        raise ReviewerCalibrationError("Calibration reference cells failed checksum.")
    if manifest.query_manifest_sha256 != query_manifest_sha256:
        raise ReviewerCalibrationError(
            "Calibration reference is bound to a different query manifest."
        )
    if manifest.protocol_version != protocol_version or manifest.taxonomy_version != taxonomy_version:
        raise ReviewerCalibrationError(
            "Calibration reference protocol or taxonomy does not match the run."
        )
    query_ids = set(query_rows)
    if set(manifest.query_region_ids) != query_ids:
        raise ReviewerCalibrationError(
            "Calibration reference query coverage does not match the query manifest."
        )
    expected_grid = {
        query_id: str(row["grid_contract_sha256"]).lower()
        for query_id, row in query_rows.items()
    }
    expected_source = {
        query_id: str(row["source_registry_sha256"]).lower()
        for query_id, row in query_rows.items()
    }
    expected_time = {
        query_id: _normalized_timestamp_text(row["source_timestamp"])
        for query_id, row in query_rows.items()
    }
    if dict(manifest.grid_contract_sha256_by_query) != expected_grid:
        raise ReviewerCalibrationError("Reference grid hashes do not match queries.")
    if dict(manifest.source_registry_sha256_by_query) != expected_source:
        raise ReviewerCalibrationError("Reference source hashes do not match queries.")
    if dict(manifest.source_timestamp_by_query) != expected_time:
        raise ReviewerCalibrationError("Reference source timestamps do not match queries.")


def _latest_calibration_annotations(
    records: Sequence[AnnotationRecord],
    *,
    reviewer_ids: Sequence[str],
    query_rows: Mapping[str, Mapping[str, Any]],
    protocol_version: str,
) -> dict[tuple[str, str], AnnotationRecord]:
    reviewer_set = set(reviewer_ids)
    query_set = set(query_rows)
    latest: dict[tuple[str, str], AnnotationRecord] = {}
    for record in records:
        if record.reviewer_id not in reviewer_set or record.query_region_id not in query_set:
            continue
        key = (record.reviewer_id, record.query_region_id)
        previous = latest.get(key)
        if previous is None or record.reviewer_revision > previous.reviewer_revision:
            latest[key] = record
    expected = {(reviewer_id, query_id) for reviewer_id in reviewer_ids for query_id in query_rows}
    missing = sorted(expected - set(latest))
    if missing:
        raise ReviewerCalibrationError(
            f"Calibration annotations do not cover every reviewer/query assignment: {missing[:5]!r}."
        )
    annotation_ids: set[str] = set()
    for key in sorted(expected):
        record = latest[key]
        query = query_rows[record.query_region_id]
        if record.annotation_id in annotation_ids:
            raise ReviewerCalibrationError("Calibration annotation ids must be unique.")
        annotation_ids.add(record.annotation_id)
        if not record.is_locked or not record.review_complete:
            raise ReviewerCalibrationError(
                f"Calibration annotation {record.annotation_id} is not locked and complete."
            )
        if record.model_predictions_visible or record.other_reviewer_annotations_visible:
            raise ReviewerCalibrationError(
                f"Calibration annotation {record.annotation_id} was not independently blinded."
            )
        if record.protocol_version != protocol_version:
            raise ReviewerCalibrationError(
                f"Calibration annotation {record.annotation_id} uses a different protocol."
            )
        if record.event_id != str(query["event_id"]) or record.tile_id != str(query["tile_id"]):
            raise ReviewerCalibrationError(
                f"Calibration annotation {record.annotation_id} has wrong event/tile lineage."
            )
        provenance = {
            "bundle_manifest_sha256": record.bundle_manifest_sha256,
            "context_manifest_sha256": record.context_manifest_sha256,
            "grid_contract_sha256": record.grid_contract_sha256,
            "source_registry_sha256": record.source_registry_sha256,
        }
        for field, value in provenance.items():
            _require_sha256(value, f"{record.annotation_id} {field}")
        if record.grid_contract_sha256 != str(query["grid_contract_sha256"]).lower():
            raise ReviewerCalibrationError(
                f"Calibration annotation {record.annotation_id} has wrong grid hash."
            )
        if record.source_registry_sha256 != str(query["source_registry_sha256"]).lower():
            raise ReviewerCalibrationError(
                f"Calibration annotation {record.annotation_id} has wrong source hash."
            )
        if record.source_timestamp is None or _iso_utc(record.source_timestamp) != _normalized_timestamp_text(query["source_timestamp"]):
            raise ReviewerCalibrationError(
                f"Calibration annotation {record.annotation_id} has wrong source timestamp."
            )
        _required_text(record.assumptions, f"{record.annotation_id} assumptions")
    return latest


def _validate_reviewer_artifact(
    *,
    reviewer_id: str,
    cell_path: Path,
    manifest_path: Path,
    records: Sequence[AnnotationRecord],
    query_rows: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    if not cell_path.is_file() or not manifest_path.is_file():
        raise ReviewerCalibrationError(
            f"Calibration cell artifacts are missing for reviewer {reviewer_id}."
        )
    manifest = _load_json_object(manifest_path, "reviewer cell manifest")
    if manifest.get("artifact_schema") != ANNOTATION_CELL_RASTER_SCHEMA:
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} cell manifest uses the wrong schema."
        )
    if manifest.get("cell_labels_file") != cell_path.name:
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} cell filename does not match its manifest."
        )
    observed_cell_hash = _file_sha256(cell_path)
    if manifest.get("cell_labels_sha256") != observed_cell_hash:
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} cells failed checksum validation."
        )
    expected_ids = {record.annotation_id for record in records}
    if set(_string_tuple(manifest.get("annotation_ids"), "annotation_ids")) != expected_ids:
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} manifest annotation coverage is not exact."
        )
    annotation_hashes = _sha_mapping(
        manifest.get("source_annotation_content_sha256"),
        "source_annotation_content_sha256",
    )
    expected_hashes = {
        record.annotation_id: annotation_content_sha256(record) for record in records
    }
    if annotation_hashes != expected_hashes:
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} manifest annotation hashes do not match."
        )
    expected_grid = {
        query_id: str(row["grid_contract_sha256"]).lower()
        for query_id, row in query_rows.items()
    }
    expected_source = {
        query_id: str(row["source_registry_sha256"]).lower()
        for query_id, row in query_rows.items()
    }
    if _sha_mapping(manifest.get("grid_contract_sha256_by_query"), "grid hashes") != expected_grid:
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} manifest grid hashes do not match."
        )
    if _sha_mapping(manifest.get("source_registry_sha256_by_query"), "source hashes") != expected_source:
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} manifest source hashes do not match."
        )
    if int(manifest.get("cell_count", -1)) <= 0:
        raise ReviewerCalibrationError("Reviewer cell manifest has invalid cell_count.")
    expected_safety = {
        "eligible_for_agreement": True,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for field, expected in expected_safety.items():
        if manifest.get(field) is not expected:
            raise ReviewerCalibrationError(
                f"Reviewer {reviewer_id} manifest has unsafe {field}."
            )
    cells = pd.read_csv(cell_path).fillna("")
    _require_columns(cells, REVIEWER_CELL_REQUIRED_COLUMNS, "reviewer cells")
    if len(cells) != int(manifest["cell_count"]):
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} cell_count does not match its manifest."
        )
    if set(cells["reviewer_id"].astype(str)) != {reviewer_id}:
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} cell artifact contains another identity."
        )
    if set(cells["annotation_id"].astype(str)) != expected_ids:
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} cells do not exactly cover annotation ids."
        )
    annotation_by_query = {record.query_region_id: record.annotation_id for record in records}
    for query_id, rows in cells.groupby(cells["query_region_id"].astype(str)):
        if query_id not in annotation_by_query or set(rows["annotation_id"].astype(str)) != {annotation_by_query[query_id]}:
            raise ReviewerCalibrationError(
                f"Reviewer {reviewer_id} cell/annotation query lineage is invalid."
            )
    _validate_cell_grid(cells, query_rows=query_rows, label=f"reviewer {reviewer_id} cells")
    _validate_cell_lineage_and_safety(cells, query_rows=query_rows, reference=False)
    _require_not_255_only(cells, label=f"reviewer {reviewer_id} cells")
    return cells


def _score_reviewer(
    reviewer_id: str,
    cells: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    query_rows: Mapping[str, Mapping[str, Any]],
    strata_by_name: Mapping[str, tuple[str, ...]],
    boundary_tolerance_m: float,
) -> Mapping[str, Any]:
    aggregate_reviewer: list[int] = []
    aggregate_reference: list[int] = []
    values_by_query: dict[str, tuple[list[int], list[int]]] = {}
    per_query: list[dict[str, Any]] = []
    boundary_values: list[float] = []
    for query_id in sorted(query_rows):
        reviewer_query = cells[cells["query_region_id"].astype(str).eq(query_id)].copy()
        reference_query = reference[
            reference["query_region_id"].astype(str).eq(query_id)
        ].copy()
        reviewer_by_cell = reviewer_query.set_index("cell_id")
        reference_by_cell = reference_query.set_index("cell_id")
        if set(reviewer_by_cell.index) != set(reference_by_cell.index):
            raise ReviewerCalibrationError(
                f"Reviewer {reviewer_id} and reference cell coverage differ for {query_id}."
            )
        size = _positive_integer(
            query_rows[query_id]["query_size_pixels"], "query_size_pixels"
        )
        reviewer_grid: list[list[int]] = []
        reference_grid: list[list[int]] = []
        flat_reviewer: list[int] = []
        flat_reference: list[int] = []
        for row_index in range(size):
            reviewer_row: list[int] = []
            reference_row: list[int] = []
            for column_index in range(size):
                cell_id = f"{query_id}_R{row_index:04d}_C{column_index:04d}"
                reviewer_value = int(_coerce_label(reviewer_by_cell.at[cell_id, "label_code"]))
                reference_value = int(_coerce_label(reference_by_cell.at[cell_id, "label_code"]))
                reviewer_row.append(reviewer_value)
                reference_row.append(reference_value)
                flat_reviewer.append(reviewer_value)
                flat_reference.append(reference_value)
            reviewer_grid.append(reviewer_row)
            reference_grid.append(reference_row)
        try:
            report = compute_agreement(
                reviewer_grid,
                reference_grid,
                pixel_size_m=float(query_rows[query_id]["resolution_m"]),
                boundary_tolerance_m=boundary_tolerance_m,
            )
        except AgreementError as exc:
            raise ReviewerCalibrationError(
                f"Could not score reviewer {reviewer_id} on {query_id}: {exc}"
            ) from exc
        if report.boundary is None:
            raise ReviewerCalibrationError(
                f"Boundary F1 is missing for reviewer {reviewer_id}/{query_id}."
            )
        boundary_values.append(float(report.boundary.f1))
        values_by_query[query_id] = (flat_reviewer, flat_reference)
        aggregate_reviewer.extend(flat_reviewer)
        aggregate_reference.extend(flat_reference)
        flood = report.class_metrics(LabelClass.TEMPORARY_FLOOD)
        per_query.append(
            {
                "query_region_id": query_id,
                "comparable_cell_count": report.valid_pair_count,
                "temporary_flood_dice": flood.dice_f1,
                "temporary_flood_iou": flood.iou,
                "cohen_kappa": report.cohen_kappa,
                "boundary_f1": report.boundary.f1,
            }
        )
    try:
        aggregate = compute_agreement(aggregate_reviewer, aggregate_reference)
    except AgreementError as exc:
        raise ReviewerCalibrationError(
            f"Could not compute aggregate calibration for {reviewer_id}: {exc}"
        ) from exc
    flood = aggregate.class_metrics(LabelClass.TEMPORARY_FLOOD)
    if flood.dice_f1 is None or flood.iou is None:
        raise ReviewerCalibrationError(
            f"Calibration has no measurable temporary-flood support for {reviewer_id}."
        )
    critical: dict[str, float] = {}
    for stratum, stratum_queries in sorted(strata_by_name.items()):
        reviewer_values: list[int] = []
        reference_values: list[int] = []
        for query_id in stratum_queries:
            review_values, truth_values = values_by_query[query_id]
            reviewer_values.extend(review_values)
            reference_values.extend(truth_values)
        report = compute_agreement(reviewer_values, reference_values)
        dice = report.class_metrics(LabelClass.TEMPORARY_FLOOD).dice_f1
        if dice is None:
            raise ReviewerCalibrationError(
                f"Critical stratum {stratum!r} has no measurable flood support."
            )
        critical[stratum] = float(dice)
    return {
        "temporary_flood_dice": float(flood.dice_f1),
        "temporary_flood_iou": float(flood.iou),
        "cohen_kappa": float(aggregate.cohen_kappa),
        "mean_boundary_f1": sum(boundary_values) / len(boundary_values),
        "critical_strata_dice": critical,
        "query_count": len(query_rows),
        "comparable_cell_count": aggregate.valid_pair_count,
        "ignored_cell_count": aggregate.ignored_pair_count,
        "per_query": per_query,
    }


def _calibration_metric_failures(
    reviewer_id: str,
    metrics: Mapping[str, Any],
    thresholds: Mapping[str, float],
    *,
    expected_query_ids: set[str] | None = None,
) -> tuple[str, ...]:
    try:
        dice = float(metrics["temporary_flood_dice"])
        iou = float(metrics["temporary_flood_iou"])
        kappa = float(metrics["cohen_kappa"])
        boundary = float(metrics["mean_boundary_f1"])
        critical = _mapping(
            metrics["critical_strata_dice"], "critical_strata_dice"
        )
        query_count = int(metrics["query_count"])
        comparable = int(metrics["comparable_cell_count"])
        per_query = metrics["per_query"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ReviewerCalibrationError(
            f"Calibration metrics are malformed for reviewer {reviewer_id}."
        ) from exc
    if query_count < MINIMUM_CALIBRATION_QUERY_COUNT or comparable <= 0:
        raise ReviewerCalibrationError(
            f"Calibration metrics lack required coverage for reviewer {reviewer_id}."
        )
    if not isinstance(per_query, Sequence) or isinstance(per_query, (str, bytes)) or len(per_query) != query_count:
        raise ReviewerCalibrationError(
            f"Per-query calibration metrics are incomplete for reviewer {reviewer_id}."
        )
    if expected_query_ids is not None:
        try:
            observed_query_ids = [
                _required_text(row["query_region_id"], "query_region_id")
                for row in per_query
                if isinstance(row, Mapping)
            ]
        except (KeyError, TypeError) as exc:
            raise ReviewerCalibrationError(
                f"Per-query calibration lineage is malformed for reviewer {reviewer_id}."
            ) from exc
        if (
            len(observed_query_ids) != len(per_query)
            or len(observed_query_ids) != len(set(observed_query_ids))
            or set(observed_query_ids) != expected_query_ids
            or query_count != len(expected_query_ids)
        ):
            raise ReviewerCalibrationError(
                f"Per-query calibration metrics do not exactly cover receipt queries for {reviewer_id}."
            )
    values = (dice, iou, kappa, boundary, *(float(value) for value in critical.values()))
    if not all(math.isfinite(value) for value in values):
        raise ReviewerCalibrationError("Calibration metrics must be finite.")
    failures: list[str] = []
    if dice < thresholds["temporary_flood_dice"]:
        failures.append("temporary_flood_dice")
    if kappa < thresholds["cohen_kappa"]:
        failures.append("cohen_kappa")
    if boundary < thresholds["mean_boundary_f1"]:
        failures.append("mean_boundary_f1")
    if not critical:
        failures.append("critical_strata_missing")
    failures.extend(
        f"critical_stratum:{name}"
        for name, value in critical.items()
        if float(value) < thresholds["critical_stratum_dice"]
    )
    return tuple(failures)


def _require_passing_metrics(
    reviewer_id: str,
    metrics: Mapping[str, Any],
    thresholds: Mapping[str, float],
    *,
    expected_query_ids: set[str] | None = None,
) -> None:
    failures = _calibration_metric_failures(
        reviewer_id,
        metrics,
        thresholds,
        expected_query_ids=expected_query_ids,
    )
    if failures:
        raise ReviewerCalibrationError(
            f"Reviewer {reviewer_id} failed calibration thresholds: {', '.join(failures)}."
        )


def _validate_query_strata(
    frame: pd.DataFrame, query_ids: Sequence[str]
) -> dict[str, tuple[str, ...]]:
    _require_columns(frame, STRATA_REQUIRED_COLUMNS, "calibration query strata")
    if frame.empty:
        raise ReviewerCalibrationError("Calibration query strata must not be empty.")
    expected = set(query_ids)
    observed = set(frame["query_region_id"].astype(str))
    if observed != expected:
        raise ReviewerCalibrationError(
            "Calibration query strata must exactly cover calibration queries."
        )
    result: dict[str, tuple[str, ...]] = {}
    for stratum, rows in frame.groupby("stratum"):
        name = _required_text(stratum, "stratum")
        result[name] = tuple(sorted(set(rows["query_region_id"].astype(str))))
    return result


def _validate_cell_grid(
    frame: pd.DataFrame,
    *,
    query_rows: Mapping[str, Mapping[str, Any]],
    label: str,
) -> None:
    if frame.empty:
        raise ReviewerCalibrationError(f"{label} must not be empty.")
    if frame.duplicated(subset=["query_region_id", "cell_id"]).any():
        raise ReviewerCalibrationError(f"{label} contain duplicate query/cell ids.")
    if frame.duplicated(subset=["query_region_id", "row_index", "column_index"]).any():
        raise ReviewerCalibrationError(f"{label} contain duplicate grid positions.")
    if set(frame["query_region_id"].astype(str)) != set(query_rows):
        raise ReviewerCalibrationError(f"{label} do not exactly cover calibration queries.")
    for query_id, query in query_rows.items():
        rows = frame[frame["query_region_id"].astype(str).eq(query_id)]
        size = _positive_integer(query["query_size_pixels"], "query_size_pixels")
        if len(rows) != size * size:
            raise ReviewerCalibrationError(
                f"{label} do not contain the complete canonical grid for {query_id}."
            )
        expected = {
            (row_index, column_index, f"{query_id}_R{row_index:04d}_C{column_index:04d}")
            for row_index in range(size)
            for column_index in range(size)
        }
        observed = {
            (
                _nonnegative_integer(row["row_index"], "row_index"),
                _nonnegative_integer(row["column_index"], "column_index"),
                str(row["cell_id"]),
            )
            for row in rows.to_dict("records")
        }
        if observed != expected:
            raise ReviewerCalibrationError(
                f"{label} do not match canonical cell ids/positions for {query_id}."
            )
        for value in rows["label_code"]:
            _coerce_label(value)
        if "label_class" in rows.columns:
            for row in rows.to_dict("records"):
                label_value = _coerce_label(row["label_code"])
                if str(row["label_class"]).strip().lower() != label_value.name.lower():
                    raise ReviewerCalibrationError(
                        f"{label} label_class does not match label_code for {query_id}."
                    )


def _validate_cell_lineage_and_safety(
    frame: pd.DataFrame,
    *,
    query_rows: Mapping[str, Mapping[str, Any]],
    reference: bool,
) -> None:
    expected_flags = {
        (
            "eligible_for_reviewer_calibration"
            if reference
            else "eligible_for_agreement"
        ): True,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for row in frame.to_dict("records"):
        query_id = str(row["query_region_id"])
        query = query_rows[query_id]
        exact = {
            "event_id": str(query["event_id"]),
            "tile_id": str(query["tile_id"]),
            "grid_id": str(query["grid_id"]),
            "grid_contract_sha256": str(query["grid_contract_sha256"]).lower(),
            "source_registry_sha256": str(query["source_registry_sha256"]).lower(),
            "source_timestamp": _normalized_timestamp_text(query["source_timestamp"]),
        }
        if reference:
            exact["crs"] = str(query["crs"])
        for field, expected in exact.items():
            observed = str(row[field]).strip()
            if field.endswith("sha256"):
                observed = observed.lower()
            elif field == "source_timestamp":
                observed = _normalized_timestamp_text(observed)
            if observed != expected:
                raise ReviewerCalibrationError(
                    f"Cell lineage {field} does not match query {query_id}."
                )
        _required_text(row["assumptions"], "cell assumptions")
        for field, expected in expected_flags.items():
            if _strict_bool(row[field], field) is not expected:
                raise ReviewerCalibrationError(
                    f"Calibration cells have unsafe {field}."
                )


def _require_not_255_only(frame: pd.DataFrame, *, label: str) -> None:
    for query_id, rows in frame.groupby(frame["query_region_id"].astype(str)):
        values = {_coerce_label(value) for value in rows["label_code"]}
        if values == {FloodLabel.UNREVIEWED}:
            raise ReviewerCalibrationError(
                f"{label} query {query_id} is 255-only and cannot prove calibration."
            )


def _verify_reference_manifest(manifest: CalibrationReferenceManifest) -> None:
    _required_text(manifest.reference_id, "reference_id")
    _required_text(manifest.authority_id, "authority_id")
    _required_text(manifest.protocol_version, "protocol_version")
    _required_text(manifest.taxonomy_version, "taxonomy_version")
    _required_text(manifest.assumptions, "assumptions")
    _safe_file_name(manifest.reference_cells_file, "reference_cells_file")
    _as_utc(manifest.created_at_utc, "created_at_utc")
    for field_name in (
        "query_manifest_sha256",
        "reference_cells_sha256",
        "manifest_sha256",
    ):
        _require_sha256(getattr(manifest, field_name), field_name)
    if manifest.cell_count <= 0:
        raise ReviewerCalibrationError("Calibration reference cell_count must be positive.")
    if len(manifest.query_region_ids) < MINIMUM_CALIBRATION_QUERY_COUNT:
        raise ReviewerCalibrationError(
            "Calibration reference does not have the minimum query count."
        )
    if manifest.authority_type not in {"expert_consensus", "adjudicated"}:
        raise ReviewerCalibrationError("Calibration reference authority_type is invalid.")
    if manifest.taxonomy_version != DEFAULT_TAXONOMY_VERSION:
        raise ReviewerCalibrationError("Calibration reference taxonomy is unsupported.")
    expected_queries = set(manifest.query_region_ids)
    for name, mapping in (
        ("grid_contract_sha256_by_query", manifest.grid_contract_sha256_by_query),
        ("source_registry_sha256_by_query", manifest.source_registry_sha256_by_query),
        ("source_timestamp_by_query", manifest.source_timestamp_by_query),
    ):
        if (
            len(mapping) != len(expected_queries)
            or {query_id for query_id, _value in mapping} != expected_queries
        ):
            raise ReviewerCalibrationError(f"Reference {name} coverage is not exact.")
    for query_id in manifest.query_region_ids:
        _required_text(query_id, "query_region_id")
    for _query_id, digest in manifest.grid_contract_sha256_by_query:
        _require_sha256(digest, "grid_contract_sha256_by_query")
    for _query_id, digest in manifest.source_registry_sha256_by_query:
        _require_sha256(digest, "source_registry_sha256_by_query")
    for _query_id, timestamp in manifest.source_timestamp_by_query:
        _parse_timestamp(timestamp, "source_timestamp_by_query")
    expected_hash = _canonical_json_sha256(
        manifest.to_dict(include_self_hash=False)
    )
    if manifest.manifest_sha256 != expected_hash:
        raise ReviewerCalibrationError(
            "Calibration reference manifest self-hash does not match."
        )


def _require_reference_safety(payload: Mapping[str, Any]) -> None:
    expected = {
        "eligible_for_reviewer_calibration": True,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for field, value in expected.items():
        if payload.get(field) is not value:
            raise ReviewerCalibrationError(
                f"Calibration reference manifest has unsafe {field}."
            )


def _require_receipt_safety(payload: Mapping[str, Any]) -> None:
    expected = {
        "calibration_passed": True,
        "dataset_role": DatasetRole.REVIEWER_CALIBRATION.value,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ReviewerCalibrationError(
                f"Reviewer calibration receipt has unsafe {field}."
            )


def _validate_thresholds(values: Mapping[str, float]) -> dict[str, float]:
    if set(values) != set(DEFAULT_CALIBRATION_THRESHOLDS):
        raise ReviewerCalibrationError(
            "Calibration thresholds must exactly name Dice, kappa, boundary, and critical-stratum gates."
        )
    result: dict[str, float] = {}
    for name, protocol_minimum in DEFAULT_CALIBRATION_THRESHOLDS.items():
        try:
            value = float(values[name])
        except (TypeError, ValueError) as exc:
            raise ReviewerCalibrationError(
                f"Calibration threshold {name} must be numeric."
            ) from exc
        if not math.isfinite(value) or value < protocol_minimum or value > 1.0:
            raise ReviewerCalibrationError(
                f"Calibration threshold {name} must be between {protocol_minimum} and 1.0."
            )
        result[name] = value
    return result


def _artifact_sha256(source: pd.DataFrame | str | Path, frame: pd.DataFrame) -> str:
    if isinstance(source, (str, Path)):
        return _file_sha256(Path(source))
    ordered = frame.copy().fillna("")
    ordered = ordered.reindex(sorted(ordered.columns), axis=1)
    return hashlib.sha256(
        ordered.to_csv(index=False, lineterminator="\n").encode("utf-8")
    ).hexdigest()


def _coerce_frame(source: pd.DataFrame | str | Path, label: str) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    path = Path(source)
    try:
        return pd.read_csv(path).fillna("")
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ReviewerCalibrationError(f"Could not load {label}: {path}") from exc


def _require_columns(frame: pd.DataFrame, required: Sequence[str], label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ReviewerCalibrationError(f"{label} missing columns: {missing}.")


def _load_json_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewerCalibrationError(f"Could not load {label}: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ReviewerCalibrationError(f"{label} must be a JSON object.")
    return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewerCalibrationError(f"{field_name} must not be blank.")
    return value.strip()


def _require_sha256(value: Any, field_name: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ReviewerCalibrationError(f"{field_name} must be a complete SHA-256.")
    return normalized


def _strict_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ReviewerCalibrationError(f"{field_name} must be explicit true or false.")


def _positive_integer(value: Any, field_name: str) -> int:
    result = _nonnegative_integer(value, field_name)
    if result <= 0:
        raise ReviewerCalibrationError(f"{field_name} must be positive.")
    return result


def _nonnegative_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ReviewerCalibrationError(f"{field_name} must be an integer.")
    try:
        numeric = float(value)
        result = int(numeric)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReviewerCalibrationError(f"{field_name} must be an integer.") from exc
    if not math.isfinite(numeric) or numeric != result or result < 0:
        raise ReviewerCalibrationError(f"{field_name} must be a non-negative integer.")
    return result


def _coerce_label(value: Any) -> FloodLabel:
    try:
        numeric = _nonnegative_integer(value, "label_code")
        return FloodLabel(numeric)
    except (ValueError, ReviewerCalibrationError) as exc:
        raise ReviewerCalibrationError(
            f"label_code {value!r} is outside the canonical flood taxonomy."
        ) from exc


def _as_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ReviewerCalibrationError(f"{field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ReviewerCalibrationError(f"{field_name} must be a UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewerCalibrationError(f"{field_name} must be an ISO timestamp.") from exc
    return _as_utc(parsed, field_name)


def _iso_utc(value: datetime) -> str:
    return _as_utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _normalized_timestamp_text(value: Any) -> str:
    if isinstance(value, datetime):
        return _iso_utc(value)
    return _iso_utc(_parse_timestamp(value, "source_timestamp"))


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ReviewerCalibrationError(f"{label} must be a JSON array.")
    result = tuple(_required_text(item, label) for item in value)
    if not result or len(result) != len(set(result)):
        raise ReviewerCalibrationError(f"{label} must be non-empty and unique.")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewerCalibrationError(f"{label} must be a JSON object.")
    return value


def _sha_mapping(value: Any, label: str) -> dict[str, str]:
    mapping = _mapping(value, label)
    return {
        _required_text(str(key), label): _require_sha256(item, label)
        for key, item in mapping.items()
    }


def _sha_mapping_tuple(value: Any, label: str) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(_sha_mapping(value, label).items()))


def _timestamp_mapping_tuple(value: Any, label: str) -> tuple[tuple[str, str], ...]:
    mapping = _mapping(value, label)
    return tuple(
        sorted(
            (
                _required_text(str(key), label),
                _normalized_timestamp_text(item),
            )
            for key, item in mapping.items()
        )
    )


def _safe_file_name(value: Any, field_name: str) -> str:
    name = _required_text(value, field_name)
    if Path(name).name != name or name in {".", ".."}:
        raise ReviewerCalibrationError(f"{field_name} must be a basename only.")
    return name


def _require_exact_keys(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    missing = sorted(expected - set(payload))
    extra = sorted(set(payload) - expected)
    if missing or extra:
        raise ReviewerCalibrationError(
            f"{label} keys do not match schema; missing={missing}, extra={extra}."
        )
