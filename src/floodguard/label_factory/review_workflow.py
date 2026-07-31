"""Fail-closed orchestration for review import, agreement, and label release.

This module bridges reviewer-facing CSV artifacts and the dependency-light
annotation, agreement, QA, adjudication, and semantic-version contracts.  It
does not rasterize human geometry and never treats a region-level class as a
pixel agreement measurement.  Agreement metrics require an explicit canonical
cell-label table produced by a separately audited rasterization step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from floodguard.label_factory.adjudication import (
    AdjudicationError,
    AdjudicationOutcome,
    AdjudicationQueueItem,
    AdjudicationRecord,
    ReviewerPair,
    adjudication_reasons,
    load_adjudication_log,
    pair_locked_annotations,
    unresolved_queue_items,
    validate_queue_item_sources,
)
from floodguard.label_factory.agreement import AgreementReport, compute_agreement
from floodguard.label_factory.annotation_rasterization import (
    AnnotationRasterizationDependencyError,
    AnnotationRasterizationError,
    GEOMETRY_PART_COLUMNS,
    canonical_geometry_parts_payload,
    validate_annotation_geometry_against_query,
)
from floodguard.label_factory.annotations import (
    AnnotationRecord,
    AnnotationValidationError,
    ReviewStage,
    append_annotation_record,
    annotation_content_sha256,
    coerce_label_class,
    load_annotation_log,
)
from floodguard.label_factory.calibration import (
    ReviewerCalibrationError,
    ReviewerCalibrationReceipt,
    require_formal_review_calibration,
    verify_reviewer_calibration_receipt,
)
from floodguard.label_factory.qa import (
    QAFinding,
    QAReport,
    QASeverity,
    run_label_factory_qa,
)
from floodguard.label_factory.processing_alignment import (
    ProcessingAlignmentError,
    validate_processing_alignment_receipt,
)
from floodguard.label_factory.release_qa import (
    ReleaseQAError,
    verify_release_qa_artifacts,
)
from floodguard.label_factory.review_derivatives import (
    DERIVATIVE_CONTEXT_LAYER_ROLES,
    ReviewDerivativeLineageError,
    validate_review_derivative_lineage_receipt,
)
from floodguard.label_factory.review_bundle import (
    REVIEW_PURPOSE_ALLOWED_ROLES,
    ReviewBundleError,
    ReviewPurpose,
    build_blinded_context_manifest,
    validate_processing_receipt_for_review_bundle,
    validate_review_queries_against_canonical_grid,
    validate_static_review_context_against_governance,
)
from floodguard.label_factory.contracts import DatasetRole
from floodguard.label_factory.rights_clearance import (
    RightsClearanceError,
    validate_rights_clearance_package,
)
from floodguard.label_factory.versioning import (
    ChangeKind,
    LabelsetManifest,
    LabelsetVersionError,
    build_labelset_manifest,
    file_sha256,
    freeze_labelset_manifest,
    load_labelset_manifest,
    verify_labelset_content,
    verify_manifest_lineage,
)


class ReviewWorkflowError(ValueError):
    """Raised when review evidence is absent, ambiguous, or unsafe to release."""


REQUIRED_RELEASE_QA_CHECK_IDS: frozenset[str] = frozenset(
    {
        "source_product_id",
        "source_acquisition_time",
        "rights_processing",
        "rights_label_derivation",
        "pre_post_pair_present",
        "pre_before_post",
        "dataset_role_known",
        "entity_single_dataset_role",
        "overlap_group_single_dataset_role",
        "untouched_test_isolation",
        "binary_training_label_known",
        "binary_training_label_eligible",
        "binary_training_target_mapping",
    }
)

REQUIRED_ANNOTATION_QA_CHECK_IDS: frozenset[str] = frozenset(
    {
        "annotation_reviewer_id",
        "annotation_reviewed_extent",
        "annotation_model_blinding",
        "annotation_reviewer_blinding",
        "annotation_review_complete",
        "annotation_locked",
    }
)

LABEL_RASTER_LINEAGE_SCHEMA = "floodguard.reviewed_label_cells.v1"
AGREEMENT_EVIDENCE_SCHEMA = "floodguard.reviewer_agreement.v1"
QA_EVIDENCE_SCHEMA = "floodguard.label_factory_qa_receipt.v1"
CONSENSUS_BUILDER_RECEIPT_SCHEMA = "floodguard.consensus_builder_receipt.v1"
LABELSET_VALIDATION_RECEIPT_SCHEMA = "floodguard.labelset_validation_receipt.v1"
ALLOWED_LABEL_CODES = {0, 1, 2, 3, 4, 255}


REVIEW_TEMPLATE_COLUMNS: tuple[str, ...] = (
    "annotation_id",
    "event_id",
    "tile_id",
    "query_region_id",
    "reviewer_id",
    "review_revision",
    "primary_class",
    "class_code",
    "confidence",
    "ambiguity_reason_codes",
    "evidence_layers_used",
    "review_complete",
    "reviewed_extent_status",
    "geometry_wkt",
    "review_started_at_utc",
    "review_finished_at_utc",
    "protocol_version",
    "tool_version",
    "model_predictions_visible",
    "supersedes_annotation_id",
    "source_timestamp",
    "assumptions",
)

# The current blank review template does not contain enough evidence to create
# a locked canonical AnnotationRecord.  Completed submissions must add these
# explicit columns; the importer intentionally does not invent them.
SUPPLEMENTAL_LOCK_COLUMNS: tuple[str, ...] = (
    "review_stage",
    "other_reviewer_annotations_visible",
    "created_at_utc",
    "locked_at_utc",
    "reviewed_extent",
)

CELL_LABEL_COLUMNS: tuple[str, ...] = (
    "annotation_id",
    "query_region_id",
    "cell_id",
    "label_code",
)


@dataclass(frozen=True, slots=True)
class AnnotationImportReceipt:
    """Auditable receipt for a batch appended to the canonical annotation log."""

    source_path: Path
    annotation_log_path: Path
    imported_annotation_ids: tuple[str, ...]
    record_hashes: tuple[str, ...]
    review_regions_sha256: str | None = None
    geometry_parts_sha256: str | None = None
    bundle_manifest_sha256: str | None = None
    context_manifest_sha256: str | None = None

    @property
    def imported_count(self) -> int:
        return len(self.imported_annotation_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "annotation_log_path": str(self.annotation_log_path),
            "imported_count": self.imported_count,
            "imported_annotation_ids": list(self.imported_annotation_ids),
            "record_hashes": list(self.record_hashes),
            "review_regions_sha256": self.review_regions_sha256,
            "geometry_parts_sha256": self.geometry_parts_sha256,
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "context_manifest_sha256": self.context_manifest_sha256,
        }


@dataclass(frozen=True, slots=True)
class PairedAgreementResult:
    """Cell-level per-query and aggregate agreement with explicit provenance."""

    reviewer_a_id: str
    reviewer_b_id: str
    per_query: tuple[dict[str, Any], ...]
    aggregate: AgreementReport
    total_cell_count: int
    query_count: int
    boundary_metric_query_count: int
    region_primary_class_exact_agreement: float
    critical_strata: tuple[tuple[str, float], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize without implying that region classes are pixel evidence."""

        return {
            "reviewer_a_id": self.reviewer_a_id,
            "reviewer_b_id": self.reviewer_b_id,
            "measurement_unit": "canonical_cell_labels",
            "total_cell_count": self.total_cell_count,
            "query_count": self.query_count,
            "boundary_metric_query_count": self.boundary_metric_query_count,
            "region_primary_class_exact_agreement": (
                self.region_primary_class_exact_agreement
            ),
            "region_primary_class_note": (
                "Descriptive query-level category check only; it is not a pixel, "
                "area, IoU, Dice, or boundary measurement."
            ),
            "critical_strata": dict(self.critical_strata),
            "aggregate": self.aggregate.to_dict(),
            "per_query": list(self.per_query),
        }


@dataclass(frozen=True, slots=True)
class LabelsetValidationReceipt:
    """Result of rechecking a frozen manifest and its external content."""

    labelset_id: str
    labelset_manifest_sha256: str
    validated_at_utc: datetime
    qa_report_sha256: str
    qa_evidence_manifest_sha256: str
    reviewer_calibration_receipt_sha256: str
    agreement_evidence_sha256: str
    raster_lineage_sha256: str
    raster_sha256_by_name: tuple[tuple[str, str], ...]
    grid_contract_sha256: str
    query_region_ids: tuple[str, ...]
    qa_ready: bool
    open_adjudication_count: int
    receipt_sha256: str

    @property
    def manifest_sha256(self) -> str:
        """Backward-compatible alias for callers displaying the manifest hash."""

        return self.labelset_manifest_sha256

    def to_dict(self, *, include_self_hash: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "artifact_schema": LABELSET_VALIDATION_RECEIPT_SCHEMA,
            "labelset_id": self.labelset_id,
            "labelset_manifest_sha256": self.labelset_manifest_sha256,
            "validated_at_utc": self.validated_at_utc.isoformat().replace(
                "+00:00", "Z"
            ),
            "qa_report_sha256": self.qa_report_sha256,
            "qa_evidence_manifest_sha256": self.qa_evidence_manifest_sha256,
            "reviewer_calibration_receipt_sha256": (
                self.reviewer_calibration_receipt_sha256
            ),
            "agreement_evidence_sha256": self.agreement_evidence_sha256,
            "raster_lineage_sha256": self.raster_lineage_sha256,
            "raster_sha256_by_name": dict(self.raster_sha256_by_name),
            "grid_contract_sha256": self.grid_contract_sha256,
            "query_region_ids": list(self.query_region_ids),
            "qa_ready": self.qa_ready,
            "open_adjudication_count": self.open_adjudication_count,
            "eligible_for_query_model_training": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        if include_self_hash:
            payload["receipt_sha256"] = self.receipt_sha256
        return payload


def parse_completed_review_csv(
    source: str | Path | pd.DataFrame,
    *,
    expected_review_regions: str | Path | pd.DataFrame | None = None,
    geometry_parts: str | Path | pd.DataFrame | None = None,
    bundle_manifest: str | Path | pd.DataFrame | None = None,
    context_layers: str | Path | pd.DataFrame | None = None,
    governance_package: str | Path | None = None,
    grid_validation_receipt: str | Path | None = None,
    canonical_tile_manifest: str | Path | None = None,
    canonical_query_manifest: str | Path | None = None,
    supported_query_derivation: str | Path | None = None,
    allow_ungoverned_fixture: bool = False,
) -> tuple[AnnotationRecord, ...]:
    """Convert completed reviewer rows to canonical records without inference.

    ``review_revision`` is mapped to ``reviewer_revision``.  Reviewer identity,
    both reviewer timestamps, class name/code, lock timestamps, review stage,
    and reviewed extent must all be supplied explicitly.
    """

    frame = _coerce_frame(source)
    _require_columns(
        frame,
        REVIEW_TEMPLATE_COLUMNS + SUPPLEMENTAL_LOCK_COLUMNS,
        "completed review CSV",
    )
    if frame.empty:
        raise ReviewWorkflowError("Completed review CSV contains no rows.")
    expected = (
        _load_expected_regions(expected_review_regions)
        if expected_review_regions is not None
        else None
    )
    parts_frame = _coerce_frame(geometry_parts) if geometry_parts is not None else None
    if expected is not None and parts_frame is None:
        raise ReviewWorkflowError(
            "Formal review import requires a geometry-parts artifact bound to every annotation."
        )
    formal_binding = None
    if expected is not None:
        formal_binding = _validate_formal_bundle_binding(
            review_regions=expected_review_regions,
            bundle_manifest=bundle_manifest,
            context_layers=context_layers,
            governance_package=governance_package,
            grid_validation_receipt=grid_validation_receipt,
            canonical_tile_manifest=canonical_tile_manifest,
            canonical_query_manifest=canonical_query_manifest,
            supported_query_derivation=supported_query_derivation,
            allow_ungoverned_fixture=allow_ungoverned_fixture,
        )
    if parts_frame is not None:
        _require_columns(parts_frame, GEOMETRY_PART_COLUMNS, "geometry-parts CSV")
        if parts_frame.empty:
            raise ReviewWorkflowError("Geometry-parts CSV contains no rows.")
    if expected is not None:
        observed_query_keys = [
            (
                _required_text(row["event_id"], "event_id"),
                _required_text(row["tile_id"], "tile_id"),
                _required_text(row["query_region_id"], "query_region_id"),
            )
            for row in frame.to_dict(orient="records")
        ]
        if len(observed_query_keys) != len(set(observed_query_keys)):
            raise ReviewWorkflowError(
                "Formal completed review CSV must contain exactly one row per review query."
            )
        missing = sorted(set(expected) - set(observed_query_keys))
        extra = sorted(set(observed_query_keys) - set(expected))
        if missing or extra:
            raise ReviewWorkflowError(
                "Formal completed review query set does not exactly match review_regions; "
                f"missing={missing}, extra={extra}."
            )
    records: list[AnnotationRecord] = []
    seen_annotation_ids: set[str] = set()
    for row_number, row in enumerate(frame.to_dict(orient="records"), 2):
        try:
            annotation_id = _required_text(row["annotation_id"], "annotation_id")
            if annotation_id in seen_annotation_ids:
                raise ReviewWorkflowError(
                    f"Duplicate annotation_id in completed CSV: {annotation_id}"
                )
            seen_annotation_ids.add(annotation_id)
            primary_class = coerce_label_class(
                _required_text(row["primary_class"], "primary_class")
            )
            class_code = coerce_label_class(
                _required_text(row["class_code"], "class_code")
            )
            if primary_class is not class_code:
                raise ReviewWorkflowError(
                    f"primary_class and class_code disagree for {annotation_id}."
                )
            review_revision = _strict_positive_integer(
                row["review_revision"], "review_revision"
            )
            review_complete = _strict_bool(row["review_complete"], "review_complete")
            if not review_complete:
                raise ReviewWorkflowError(
                    f"Annotation {annotation_id} is not marked review_complete=true."
                )
            model_visible = _strict_bool(
                row["model_predictions_visible"], "model_predictions_visible"
            )
            other_visible = _strict_bool(
                row["other_reviewer_annotations_visible"],
                "other_reviewer_annotations_visible",
            )
            if model_visible or other_visible:
                raise ReviewWorkflowError(
                    f"Annotation {annotation_id} is not independently blinded."
                )
            reviewed_status = _required_text(
                row["reviewed_extent_status"], "reviewed_extent_status"
            ).lower()
            if reviewed_status in {"not_reviewed", "unreviewed", "incomplete"}:
                raise ReviewWorkflowError(
                    f"Annotation {annotation_id} has incomplete reviewed_extent_status."
                )
            reviewed_extent = _required_text(row["reviewed_extent"], "reviewed_extent")
            event_id = _required_text(row["event_id"], "event_id")
            tile_id = _required_text(row["tile_id"], "tile_id")
            query_id = _required_text(row["query_region_id"], "query_region_id")
            expected_query: Mapping[str, Any] | None = None
            if expected is not None:
                expected_key = (event_id, tile_id, query_id)
                if expected_key not in expected:
                    raise ReviewWorkflowError(
                        f"Annotation {annotation_id} does not match the blinded review manifest."
                    )
                expected_query = expected[expected_key]
            supersedes = str(row.get("supersedes_annotation_id", "")).strip()
            if review_revision == 1 and supersedes:
                raise ReviewWorkflowError(
                    f"First revision {annotation_id} must not supersede another annotation."
                )
            if review_revision > 1 and not supersedes:
                raise ReviewWorkflowError(
                    f"Revision {review_revision} for {annotation_id} requires "
                    "supersedes_annotation_id."
                )
            source_timestamp = _parse_timestamp(
                row["source_timestamp"], "source_timestamp"
            )
            assumptions = _required_text(row["assumptions"], "assumptions")
            evidence_layers = _split_list(row["evidence_layers_used"])
            completed_review_stage = _required_text(
                row["review_stage"], "review_stage"
            ).lower()
            if formal_binding is not None:
                completed_review_purpose = _required_text(
                    row.get("review_purpose"), "review_purpose"
                ).lower()
                if (
                    completed_review_stage != formal_binding["review_stage"]
                    or completed_review_purpose
                    != formal_binding["review_purpose"]
                ):
                    raise ReviewWorkflowError(
                        f"Annotation {annotation_id} stage or purpose does not match "
                        "its exact blinded bundle."
                    )
            if formal_binding is not None:
                _validate_used_context_layers(
                    evidence_layers,
                    event_id=event_id,
                    context_frame=formal_binding["context_frame"],
                )
            review_started_at = _parse_timestamp(
                row["review_started_at_utc"], "review_started_at_utc"
            )
            review_evidence_not_before = (
                formal_binding.get("formal_review_evidence_not_before_utc")
                if formal_binding is not None
                else None
            )
            if (
                review_evidence_not_before is not None
                and review_started_at < review_evidence_not_before
            ):
                raise ReviewWorkflowError(
                    f"Annotation {annotation_id} started before its governed "
                    "review evidence existed."
                )
            legacy_geometry = _optional_text(row["geometry_wkt"])
            locked_geometry = legacy_geometry
            if parts_frame is not None:
                annotation_parts = parts_frame.loc[
                    parts_frame["annotation_id"].astype(str).eq(annotation_id)
                ].copy()
                if annotation_parts.empty:
                    raise ReviewWorkflowError(
                        f"Geometry-parts CSV has no rows for annotation {annotation_id}."
                    )
                _validate_legacy_geometry_echo(
                    annotation_id,
                    legacy_geometry,
                    annotation_parts,
                )
                locked_geometry = canonical_geometry_parts_payload(annotation_parts)
            record = AnnotationRecord(
                annotation_id=annotation_id,
                event_id=event_id,
                tile_id=tile_id,
                query_region_id=query_id,
                reviewer_id=_required_text(row["reviewer_id"], "reviewer_id"),
                reviewer_revision=review_revision,
                primary_class=primary_class,
                confidence=_required_text(row["confidence"], "confidence").lower(),
                ambiguity_reason_codes=_split_list(row["ambiguity_reason_codes"]),
                evidence_layers_used=evidence_layers,
                review_complete=True,
                reviewed_extent=reviewed_extent,
                geometry=locked_geometry,
                review_started_at=review_started_at,
                review_finished_at=_parse_timestamp(
                    row["review_finished_at_utc"], "review_finished_at_utc"
                ),
                protocol_version=_required_text(
                    row["protocol_version"], "protocol_version"
                ),
                tool_version=_required_text(row["tool_version"], "tool_version"),
                model_predictions_visible=False,
                other_reviewer_annotations_visible=False,
                created_at_utc=_parse_timestamp(row["created_at_utc"], "created_at_utc"),
                locked_at_utc=_parse_timestamp(row["locked_at_utc"], "locked_at_utc"),
                review_stage=ReviewStage(completed_review_stage),
                supersedes_annotation_id=supersedes or None,
                source_timestamp=source_timestamp,
                assumptions=assumptions,
                bundle_manifest_sha256=(
                    formal_binding["bundle_manifest_sha256"]
                    if formal_binding is not None
                    else None
                ),
                context_manifest_sha256=(
                    formal_binding["context_manifest_sha256"]
                    if formal_binding is not None
                    else None
                ),
                grid_contract_sha256=(
                    _required_sha256_text(
                        expected_query.get("grid_contract_sha256"),
                        "grid_contract_sha256",
                    )
                    if expected_query is not None
                    else None
                ),
                source_registry_sha256=(
                    _required_sha256_text(
                        expected_query.get("source_registry_sha256"),
                        "source_registry_sha256",
                    )
                    if expected_query is not None
                    else None
                ),
            )
            validate_annotation_geometry_against_query(record, expected_query)
        except (
            AnnotationValidationError,
            AnnotationRasterizationError,
            AnnotationRasterizationDependencyError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            if isinstance(exc, ReviewWorkflowError):
                raise
            raise ReviewWorkflowError(
                f"Invalid completed review row {row_number}: {exc}"
            ) from exc
        records.append(record)
    if parts_frame is not None:
        expected_annotation_ids = {record.annotation_id for record in records}
        supplied_part_ids = {
            str(value).strip() for value in parts_frame["annotation_id"]
        }
        if supplied_part_ids != expected_annotation_ids:
            raise ReviewWorkflowError(
                "Geometry-parts annotation ids do not exactly match completed reviews; "
                f"missing={sorted(expected_annotation_ids - supplied_part_ids)}, "
                f"extra={sorted(supplied_part_ids - expected_annotation_ids)}."
            )
    return tuple(records)


def import_reviewer_annotations(
    source: str | Path | pd.DataFrame,
    annotation_log_path: str | Path,
    *,
    expected_review_regions: str | Path | pd.DataFrame | None = None,
    geometry_parts: str | Path | pd.DataFrame | None = None,
    bundle_manifest: str | Path | pd.DataFrame | None = None,
    context_layers: str | Path | pd.DataFrame | None = None,
    governance_package: str | Path | None = None,
    grid_validation_receipt: str | Path | None = None,
    canonical_tile_manifest: str | Path | None = None,
    canonical_query_manifest: str | Path | None = None,
    supported_query_derivation: str | Path | None = None,
    allow_ungoverned_fixture: bool = False,
) -> AnnotationImportReceipt:
    """Validate a complete batch, then append every record to the hash chain."""

    frame = _coerce_frame(source)
    records = parse_completed_review_csv(
        frame,
        expected_review_regions=expected_review_regions,
        geometry_parts=geometry_parts,
        bundle_manifest=bundle_manifest,
        context_layers=context_layers,
        governance_package=governance_package,
        grid_validation_receipt=grid_validation_receipt,
        canonical_tile_manifest=canonical_tile_manifest,
        canonical_query_manifest=canonical_query_manifest,
        supported_query_derivation=supported_query_derivation,
        allow_ungoverned_fixture=allow_ungoverned_fixture,
    )
    target = Path(annotation_log_path)
    existing = load_annotation_log(target)
    supersedes_by_id = {
        _required_text(row["annotation_id"], "annotation_id"): str(
            row.get("supersedes_annotation_id", "")
        ).strip()
        for row in frame.to_dict(orient="records")
    }
    _validate_batch_append(existing, records, supersedes_by_id=supersedes_by_id)
    hashes: list[str] = []
    for record in records:
        hashes.append(append_annotation_record(target, record))
    source_path = Path(source) if not isinstance(source, pd.DataFrame) else Path("<dataframe>")
    return AnnotationImportReceipt(
        source_path=source_path,
        annotation_log_path=target,
        imported_annotation_ids=tuple(record.annotation_id for record in records),
        record_hashes=tuple(hashes),
        review_regions_sha256=_optional_source_sha256(expected_review_regions),
        geometry_parts_sha256=_optional_source_sha256(geometry_parts),
        bundle_manifest_sha256=_optional_source_sha256(bundle_manifest),
        context_manifest_sha256=_optional_source_sha256(context_layers),
    )


def compute_cell_level_agreement(
    pairs: Sequence[ReviewerPair],
    cell_labels: str | Path | pd.DataFrame,
    *,
    pixel_size_m: float | None = None,
    boundary_tolerance_m: float = 20.0,
    query_strata: str | Path | pd.DataFrame | None = None,
) -> PairedAgreementResult:
    """Compute real cell-level agreement; never substitute primary classes.

    The table must contain one row per ``annotation_id``/``cell_id`` with an
    explicit canonical ``label_code``.  Optional integer ``row_index`` and
    ``column_index`` columns enable per-query boundary F1 when they form a
    complete rectangle.  Aggregate boundary F1 is intentionally omitted because
    concatenating unrelated query cores would create artificial boundaries.
    """

    if not pairs:
        raise ReviewWorkflowError("At least one complete reviewer pair is required.")
    frame = _coerce_frame(cell_labels)
    _require_columns(frame, CELL_LABEL_COLUMNS, "canonical cell-label CSV")
    if frame.empty:
        raise ReviewWorkflowError("Canonical cell-label CSV contains no cells.")
    if frame.duplicated(subset=["annotation_id", "cell_id"]).any():
        raise ReviewWorkflowError(
            "Canonical cell-label CSV has duplicate annotation_id/cell_id rows."
        )
    use_grid = {"row_index", "column_index"}.issubset(frame.columns)
    per_query: list[dict[str, Any]] = []
    aggregate_a: list[int] = []
    aggregate_b: list[int] = []
    boundary_count = 0
    region_matches = 0
    values_by_query: dict[str, tuple[list[int], list[int]]] = {}
    expected_annotation_ids: set[str] = set()
    for pair in pairs:
        a = _cells_for_annotation(frame, pair.reviewer_a, use_grid=use_grid)
        b = _cells_for_annotation(frame, pair.reviewer_b, use_grid=use_grid)
        expected_annotation_ids.update(
            {pair.reviewer_a.annotation_id, pair.reviewer_b.annotation_id}
        )
        a_ids = set(a["cell_id"])
        b_ids = set(b["cell_id"])
        if a_ids != b_ids:
            only_a = len(a_ids - b_ids)
            only_b = len(b_ids - a_ids)
            raise ReviewWorkflowError(
                f"Cell coverage differs for {pair.query_region_id}: "
                f"{only_a} A-only and {only_b} B-only cells."
            )
        ordered_ids = sorted(a_ids)
        a_by_id = a.set_index("cell_id")
        b_by_id = b.set_index("cell_id")
        a_values = [int(coerce_label_class(a_by_id.at[cell_id, "label_code"])) for cell_id in ordered_ids]
        b_values = [int(coerce_label_class(b_by_id.at[cell_id, "label_code"])) for cell_id in ordered_ids]
        agreement_input_a: Sequence[Any] = a_values
        agreement_input_b: Sequence[Any] = b_values
        query_pixel_size: float | None = None
        if use_grid:
            agreement_input_a, agreement_input_b = _rectangular_grids(
                a_by_id,
                b_by_id,
                ordered_ids,
            )
            query_pixel_size = _positive_pixel_size(pixel_size_m)
        report = compute_agreement(
            agreement_input_a,
            agreement_input_b,
            pixel_size_m=query_pixel_size,
            boundary_tolerance_m=boundary_tolerance_m,
        )
        if report.boundary is not None:
            boundary_count += 1
        region_class_match = pair.reviewer_a.primary_class is pair.reviewer_b.primary_class
        region_matches += int(region_class_match)
        aggregate_a.extend(a_values)
        aggregate_b.extend(b_values)
        values_by_query[pair.query_region_id] = (a_values, b_values)
        per_query.append(
            {
                "event_id": pair.event_id,
                "tile_id": pair.tile_id,
                "query_region_id": pair.query_region_id,
                "reviewer_a_annotation_id": pair.reviewer_a.annotation_id,
                "reviewer_b_annotation_id": pair.reviewer_b.annotation_id,
                "cell_count": len(ordered_ids),
                "region_primary_class_match": region_class_match,
                "measurement_unit": "canonical_cell_labels",
                "agreement": report.to_dict(),
            }
        )
    unexpected = sorted(set(frame["annotation_id"].astype(str)) - expected_annotation_ids)
    if unexpected:
        raise ReviewWorkflowError(
            "Cell-label CSV contains annotations outside the requested A/B pairs: "
            + ", ".join(unexpected)
        )
    aggregate = compute_agreement(aggregate_a, aggregate_b, pixel_size_m=None)
    critical_strata = _critical_stratum_agreement(values_by_query, query_strata)
    return PairedAgreementResult(
        reviewer_a_id=pairs[0].reviewer_a.reviewer_id,
        reviewer_b_id=pairs[0].reviewer_b.reviewer_id,
        per_query=tuple(per_query),
        aggregate=aggregate,
        total_cell_count=len(aggregate_a),
        query_count=len(pairs),
        boundary_metric_query_count=boundary_count,
        region_primary_class_exact_agreement=region_matches / len(pairs),
        critical_strata=tuple(sorted(critical_strata.items())),
    )


def _critical_stratum_agreement(
    values_by_query: Mapping[str, tuple[list[int], list[int]]],
    query_strata: str | Path | pd.DataFrame | None,
) -> dict[str, float]:
    if query_strata is None:
        return {}
    frame = _coerce_frame(query_strata)
    _require_columns(frame, ("query_region_id", "stratum"), "query strata")
    if frame.empty:
        raise ReviewWorkflowError("query strata must not be empty.")
    unknown = sorted(set(frame["query_region_id"].astype(str)) - set(values_by_query))
    missing = sorted(set(values_by_query) - set(frame["query_region_id"].astype(str)))
    if unknown or missing:
        raise ReviewWorkflowError(
            f"query strata do not exactly cover agreement queries; missing={missing}, unknown={unknown}."
        )
    result: dict[str, float] = {}
    for stratum, rows in frame.groupby("stratum"):
        name = _required_text(stratum, "stratum")
        reviewer_a: list[int] = []
        reviewer_b: list[int] = []
        for query_id in sorted(set(rows["query_region_id"].astype(str))):
            values_a, values_b = values_by_query[query_id]
            reviewer_a.extend(values_a)
            reviewer_b.extend(values_b)
        report = compute_agreement(reviewer_a, reviewer_b)
        dice = report.class_metrics(1).dice_f1
        if dice is None:
            raise ReviewWorkflowError(
                f"Critical stratum {name!r} has no temporary-flood support; Dice is undefined."
            )
        result[name] = float(dice)
    return result


def write_agreement_outputs(
    result: PairedAgreementResult,
    *,
    json_path: str | Path,
    per_query_csv_path: str | Path,
    pairs: Sequence[ReviewerPair] | None = None,
    cell_labels: str | Path | pd.DataFrame | None = None,
    query_strata: str | Path | pd.DataFrame | None = None,
) -> tuple[Path, Path]:
    """Write release-bound agreement artifacts exactly once.

    Formal output requires the exact reviewer pairs and cell-label artifact so
    the JSON can satisfy the release gate.  Omitting either is rejected rather
    than emitting a metrics-only JSON that could be mistaken for release
    evidence.
    """

    if pairs is None or cell_labels is None:
        raise ReviewWorkflowError(
            "Agreement output requires exact reviewer pairs and cell-label evidence."
        )
    evidence = build_bound_agreement_evidence(
        result,
        pairs=pairs,
        cell_labels=cell_labels,
        query_strata=query_strata,
    )

    json_target = Path(json_path)
    csv_target = Path(per_query_csv_path)
    _require_distinct_new_paths(json_target, csv_target)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    csv_target.parent.mkdir(parents=True, exist_ok=True)
    with json_target.open("x", encoding="utf-8") as handle:
        json.dump(evidence, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    flat_rows: list[dict[str, Any]] = []
    for row in evidence["per_query"]:
        report = row["agreement"]
        flood = report["per_class"]["1"]
        boundary = report["boundary"] or {}
        flat_rows.append(
            {
                **{key: value for key, value in row.items() if key != "agreement"},
                "exact_agreement": report["exact_agreement"],
                "cohen_kappa": report["cohen_kappa"],
                "temporary_flood_iou": flood["iou"],
                "temporary_flood_dice_f1": flood["dice_f1"],
                "boundary_f1": boundary.get("f1"),
                "boundary_tolerance_m": boundary.get("tolerance_m"),
            }
        )
    with csv_target.open("x", encoding="utf-8", newline="") as handle:
        pd.DataFrame(flat_rows).to_csv(handle, index=False)
    return json_target, csv_target


def build_bound_agreement_evidence(
    result: PairedAgreementResult,
    *,
    pairs: Sequence[ReviewerPair],
    cell_labels: str | Path | pd.DataFrame,
    query_strata: str | Path | pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Bind computed metrics to the exact reviews, grid, and cell artifact."""

    if not pairs:
        raise ReviewWorkflowError("Agreement evidence requires reviewer pairs.")
    frame = _coerce_frame(cell_labels)
    _require_columns(
        frame,
        (*CELL_LABEL_COLUMNS, "grid_contract_sha256"),
        "canonical cell-label CSV",
    )
    grid_hashes = {
        _required_sha256_text(value, "grid_contract_sha256")
        for value in frame["grid_contract_sha256"]
    }
    if len(grid_hashes) != 1:
        raise ReviewWorkflowError(
            "One agreement artifact must use exactly one grid_contract_sha256."
        )
    grid_hash = next(iter(grid_hashes))
    cell_artifact_sha256 = _optional_source_sha256(cell_labels)
    if cell_artifact_sha256 is None:
        cell_artifact_sha256 = _canonical_json_sha256(
            frame.sort_values(
                ["annotation_id", "query_region_id", "cell_id"], kind="stable"
            ).to_dict("records")
        )
    annotations = [
        record
        for pair in pairs
        for record in (pair.reviewer_a, pair.reviewer_b)
    ]
    if result.reviewer_a_id != pairs[0].reviewer_a.reviewer_id or (
        result.reviewer_b_id != pairs[0].reviewer_b.reviewer_id
    ):
        raise ReviewWorkflowError(
            "Agreement result reviewer identities do not match the supplied pairs."
        )
    annotation_hashes = {
        record.annotation_id: annotation_content_sha256(record)
        for record in annotations
    }
    cell_hashes = {
        record.annotation_id: cell_artifact_sha256 for record in annotations
    }
    import_provenance: dict[str, dict[str, str]] = {}
    for record in annotations:
        provenance = {
            field_name: getattr(record, field_name)
            for field_name in (
                "bundle_manifest_sha256",
                "context_manifest_sha256",
                "grid_contract_sha256",
                "source_registry_sha256",
            )
        }
        if any(not _is_sha256(value) for value in provenance.values()):
            raise ReviewWorkflowError(
                f"Annotation {record.annotation_id} lacks formal import provenance."
            )
        if provenance["grid_contract_sha256"] != grid_hash:
            raise ReviewWorkflowError(
                f"Annotation {record.annotation_id} and agreement cells use different grids."
            )
        import_provenance[record.annotation_id] = {
            key: str(value) for key, value in provenance.items()
        }
    payload = result.to_dict()
    payload["artifact_schema"] = AGREEMENT_EVIDENCE_SCHEMA
    payload["grid_contract_sha256"] = grid_hash
    payload["query_region_ids"] = sorted(pair.query_region_id for pair in pairs)
    payload["annotation_sha256_by_id"] = annotation_hashes
    payload["reviewer_cell_artifact_sha256_by_annotation_id"] = cell_hashes
    payload["review_import_provenance_by_annotation_id"] = import_provenance
    if query_strata is not None:
        strata_hash = _optional_source_sha256(query_strata)
        if strata_hash is None:
            strata_hash = _canonical_json_sha256(
                _coerce_frame(query_strata)
                .sort_values(["query_region_id", "stratum"], kind="stable")
                .to_dict("records")
            )
        payload["query_strata_sha256"] = strata_hash
    pair_by_query = {pair.query_region_id: pair for pair in pairs}
    enriched_rows: list[dict[str, Any]] = []
    for source_row in payload["per_query"]:
        row = dict(source_row)
        pair = pair_by_query[str(row["query_region_id"])]
        row.update(
            {
                "reviewer_a_annotation_sha256": annotation_hashes[
                    pair.reviewer_a.annotation_id
                ],
                "reviewer_b_annotation_sha256": annotation_hashes[
                    pair.reviewer_b.annotation_id
                ],
                "reviewer_a_cell_artifact_sha256": cell_hashes[
                    pair.reviewer_a.annotation_id
                ],
                "reviewer_b_cell_artifact_sha256": cell_hashes[
                    pair.reviewer_b.annotation_id
                ],
            }
        )
        enriched_rows.append(row)
    payload["per_query"] = enriched_rows
    return payload


def write_adjudication_queue_csv(
    queue_items: Sequence[AdjudicationQueueItem],
    path: str | Path,
) -> Path:
    """Write an explicit queue (including an empty, header-only queue) once."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "queue_id",
        "event_id",
        "tile_id",
        "query_region_id",
        "reviewer_a_annotation_id",
        "reviewer_b_annotation_id",
        "reviewer_a_sha256",
        "reviewer_b_sha256",
        "reason_codes",
        "created_at_utc",
        "status",
    ]
    with target.open("x", encoding="utf-8", newline="") as handle:
        pd.DataFrame([item.to_dict() for item in queue_items], columns=columns).to_csv(
            handle,
            index=False,
        )
    return target


def load_adjudication_queue_csv(path: str | Path) -> tuple[AdjudicationQueueItem, ...]:
    """Load and validate a queue CSV written by this workflow."""

    source = Path(path)
    if not source.exists():
        raise ReviewWorkflowError(f"Adjudication queue does not exist: {source}")
    try:
        frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ReviewWorkflowError(f"Could not read adjudication queue: {source}") from exc
    expected_columns = (
        "queue_id",
        "event_id",
        "tile_id",
        "query_region_id",
        "reviewer_a_annotation_id",
        "reviewer_b_annotation_id",
        "reviewer_a_sha256",
        "reviewer_b_sha256",
        "reason_codes",
        "created_at_utc",
        "status",
    )
    _require_columns(frame, expected_columns, "adjudication queue")
    try:
        items = tuple(
            AdjudicationQueueItem.from_dict(row)
            for row in frame.to_dict(orient="records")
        )
    except AdjudicationError as exc:
        raise ReviewWorkflowError(f"Invalid adjudication queue: {exc}") from exc
    ids = [item.queue_id for item in items]
    if len(ids) != len(set(ids)):
        raise ReviewWorkflowError("Adjudication queue contains duplicate queue_id values.")
    return items


def load_qa_report_csv(path: str | Path) -> QAReport:
    """Load structured QA evidence and preserve blocking severities."""

    frame = _coerce_frame(path)
    required = (
        "check_id",
        "entity_id",
        "passed",
        "severity",
        "message",
        "observed",
        "expected",
    )
    _require_columns(frame, required, "QA report")
    if frame.empty:
        raise ReviewWorkflowError("QA report contains no findings.")
    findings: list[QAFinding] = []
    for row_number, row in enumerate(frame.to_dict(orient="records"), 2):
        try:
            findings.append(
                QAFinding(
                    check_id=_required_text(row["check_id"], "check_id"),
                    entity_id=_required_text(row["entity_id"], "entity_id"),
                    passed=_strict_bool(row["passed"], "passed"),
                    severity=QASeverity(
                        _required_text(row["severity"], "severity").lower()
                    ),
                    message=_required_text(row["message"], "message"),
                    observed=str(row["observed"]),
                    expected=str(row["expected"]),
                )
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ReviewWorkflowError):
                raise
            raise ReviewWorkflowError(f"Invalid QA report row {row_number}: {exc}") from exc
    return QAReport(findings=tuple(findings))


def freeze_reviewed_labelset(
    *,
    annotation_records: Sequence[AnnotationRecord],
    reviewer_a_id: str,
    reviewer_b_id: str,
    queue_items: Sequence[AdjudicationQueueItem],
    adjudications: Sequence[AdjudicationRecord],
    qa_report: QAReport,
    qa_evidence_manifest: Mapping[str, Any],
    qa_report_path: str | Path,
    qa_raw_input_paths: Mapping[str, str | Path],
    reviewer_calibration_receipt: ReviewerCalibrationReceipt,
    agreement_evidence: Mapping[str, Any],
    raster_lineage: Mapping[str, Any],
    labelset_name: str,
    version: str,
    change_kind: ChangeKind | str,
    label_content: Any,
    metadata: Mapping[str, Any],
    semantics: Mapping[str, Any],
    source_annotation_ids: Sequence[str],
    raster_paths: Mapping[str, str | Path],
    expected_raster_sha256: Mapping[str, str],
    consensus_source_artifact_paths: Mapping[str, str | Path],
    output_path: str | Path,
    created_at_utc: datetime,
    parent: LabelsetManifest | None = None,
) -> LabelsetManifest:
    """Freeze a versioned labelset only after all human and QA gates pass."""

    try:
        verify_reviewer_calibration_receipt(reviewer_calibration_receipt)
    except ReviewerCalibrationError as exc:
        raise ReviewWorkflowError(
            f"Reviewer calibration evidence failed: {exc}"
        ) from exc
    formal_annotation_records = tuple(
        record
        for record in annotation_records
        if record.query_region_id
        not in set(reviewer_calibration_receipt.query_region_ids)
    )
    pairs = pair_locked_annotations(
        formal_annotation_records,
        reviewer_a_id=reviewer_a_id,
        reviewer_b_id=reviewer_b_id,
    )
    try:
        require_formal_review_calibration(
            reviewer_calibration_receipt,
            annotation_records=[
                record
                for pair in pairs
                for record in (pair.reviewer_a, pair.reviewer_b)
            ],
            reviewer_ids=(reviewer_a_id, reviewer_b_id),
            semantics=semantics,
        )
    except ReviewerCalibrationError as exc:
        raise ReviewWorkflowError(
            f"Formal review is not covered by reviewer calibration: {exc}"
        ) from exc
    _validate_queue_completeness(pairs, queue_items)
    resolutions_by_query = _validate_adjudication_closure(
        pairs, queue_items, adjudications
    )
    _require_passing_qa(
        qa_report,
        required_check_ids=REQUIRED_RELEASE_QA_CHECK_IDS,
    )
    annotation_qa = run_label_factory_qa(
        annotations=[
            record
            for pair in pairs
            for record in (pair.reviewer_a, pair.reviewer_b)
        ],
        require_complete_annotations=True,
    )
    _require_passing_qa(
        annotation_qa,
        required_check_ids=REQUIRED_ANNOTATION_QA_CHECK_IDS,
    )
    latest_ids = {
        record.annotation_id
        for pair in pairs
        for record in (pair.reviewer_a, pair.reviewer_b)
    }
    supplied_ids = {_required_text(value, "source_annotation_id") for value in source_annotation_ids}
    if supplied_ids != latest_ids:
        missing = sorted(latest_ids - supplied_ids)
        unknown = sorted(supplied_ids - latest_ids)
        raise ReviewWorkflowError(
            "source_annotation_ids must exactly name the latest A/B records; "
            f"missing={missing}, unknown_or_obsolete={unknown}."
        )
    _require_nonempty_content(label_content, "label_content")
    _require_nonempty_content(metadata, "metadata")
    _require_nonempty_content(semantics, "semantics")
    observed_raster_hashes = _verify_raster_checksums(
        raster_paths,
        expected_raster_sha256,
    )
    reviewer_cell_hashes = _require_agreement_gates(
        agreement_evidence,
        pairs=pairs,
        grid_contract_sha256=str(
            raster_lineage.get("grid_contract_sha256", "")
        ),
    )
    derived_label_content = _validate_raster_lineage(
        raster_lineage,
        raster_paths=raster_paths,
        observed_raster_hashes=observed_raster_hashes,
        pairs=pairs,
        resolutions_by_query=resolutions_by_query,
        queue_items=queue_items,
        reviewer_cell_hashes=reviewer_cell_hashes,
        consensus_source_artifact_paths=consensus_source_artifact_paths,
    )
    if label_content != derived_label_content:
        raise ReviewWorkflowError(
            "label_content must exactly match canonical cell labels derived from the "
            "validated raster-lineage artifacts."
        )
    _require_qa_evidence_manifest(
        qa_evidence_manifest,
        qa_report=qa_report,
        pairs=pairs,
        agreement_evidence=agreement_evidence,
        raster_lineage=raster_lineage,
        raster_hashes=observed_raster_hashes,
        reviewer_cell_hashes=reviewer_cell_hashes,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
    )
    _require_raw_release_qa_evidence(
        qa_report=qa_report,
        qa_evidence_manifest=qa_evidence_manifest,
        qa_report_path=qa_report_path,
        qa_raw_input_paths=qa_raw_input_paths,
        consensus_source_artifact_paths=consensus_source_artifact_paths,
    )
    release_metadata = build_release_metadata(
        metadata,
        adjudications=adjudications,
        qa_report=qa_report,
        qa_evidence_manifest=qa_evidence_manifest,
        agreement_evidence=agreement_evidence,
        raster_lineage=raster_lineage,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
    )
    try:
        manifest = build_labelset_manifest(
            labelset_name=labelset_name,
            version=version,
            change_kind=change_kind,
            label_content=label_content,
            metadata=release_metadata,
            semantics=semantics,
            source_annotation_ids=tuple(sorted(supplied_ids)),
            raster_sha256_by_name=observed_raster_hashes,
            created_at_utc=_as_utc(created_at_utc, "created_at_utc"),
            parent=parent,
        )
        freeze_labelset_manifest(manifest, output_path)
    except LabelsetVersionError as exc:
        raise ReviewWorkflowError(f"Could not freeze labelset: {exc}") from exc
    return manifest


def validate_frozen_labelset(
    *,
    manifest_path: str | Path,
    label_content: Any,
    metadata: Mapping[str, Any],
    semantics: Mapping[str, Any],
    queue_items: Sequence[AdjudicationQueueItem],
    adjudications: Sequence[AdjudicationRecord],
    qa_report: QAReport,
    qa_evidence_manifest: Mapping[str, Any],
    qa_report_path: str | Path,
    qa_raw_input_paths: Mapping[str, str | Path],
    reviewer_calibration_receipt: ReviewerCalibrationReceipt,
    agreement_evidence: Mapping[str, Any],
    raster_lineage: Mapping[str, Any],
    raster_paths: Mapping[str, str | Path],
    expected_raster_sha256: Mapping[str, str],
    consensus_source_artifact_paths: Mapping[str, str | Path],
    annotation_records: Sequence[AnnotationRecord],
    reviewer_a_id: str,
    reviewer_b_id: str,
    parent: LabelsetManifest | None = None,
) -> LabelsetValidationReceipt:
    """Recheck a frozen manifest, source files, QA, and adjudication closure."""

    try:
        manifest = load_labelset_manifest(manifest_path)
    except LabelsetVersionError as exc:
        raise ReviewWorkflowError(f"Could not load frozen labelset: {exc}") from exc
    try:
        verify_reviewer_calibration_receipt(reviewer_calibration_receipt)
    except ReviewerCalibrationError as exc:
        raise ReviewWorkflowError(
            f"Reviewer calibration evidence failed: {exc}"
        ) from exc
    formal_annotation_records = tuple(
        record
        for record in annotation_records
        if record.query_region_id
        not in set(reviewer_calibration_receipt.query_region_ids)
    )
    pairs = pair_locked_annotations(
        formal_annotation_records,
        reviewer_a_id=reviewer_a_id,
        reviewer_b_id=reviewer_b_id,
    )
    try:
        require_formal_review_calibration(
            reviewer_calibration_receipt,
            annotation_records=[
                record
                for pair in pairs
                for record in (pair.reviewer_a, pair.reviewer_b)
            ],
            reviewer_ids=(reviewer_a_id, reviewer_b_id),
            semantics=semantics,
        )
    except ReviewerCalibrationError as exc:
        raise ReviewWorkflowError(
            f"Formal review is not covered by reviewer calibration: {exc}"
        ) from exc
    _validate_queue_completeness(pairs, queue_items)
    latest_ids = {
        record.annotation_id
        for pair in pairs
        for record in (pair.reviewer_a, pair.reviewer_b)
    }
    if set(manifest.source_annotation_ids) != latest_ids:
        raise ReviewWorkflowError(
            "Frozen manifest source_annotation_ids do not match the latest locked A/B reviews."
        )
    resolutions_by_query = _validate_adjudication_closure(
        pairs, queue_items, adjudications
    )
    _require_passing_qa(
        qa_report,
        required_check_ids=REQUIRED_RELEASE_QA_CHECK_IDS,
    )
    observed = _verify_raster_checksums(raster_paths, expected_raster_sha256)
    if observed != dict(manifest.raster_sha256_by_name):
        raise ReviewWorkflowError(
            "Observed raster checksums do not match the frozen labelset manifest."
        )
    reviewer_cell_hashes = _require_agreement_gates(
        agreement_evidence,
        pairs=pairs,
        grid_contract_sha256=str(
            raster_lineage.get("grid_contract_sha256", "")
        ),
    )
    derived_label_content = _validate_raster_lineage(
        raster_lineage,
        raster_paths=raster_paths,
        observed_raster_hashes=observed,
        pairs=pairs,
        resolutions_by_query=resolutions_by_query,
        queue_items=queue_items,
        reviewer_cell_hashes=reviewer_cell_hashes,
        consensus_source_artifact_paths=consensus_source_artifact_paths,
    )
    if label_content != derived_label_content:
        raise ReviewWorkflowError(
            "Supplied label_content does not match validated canonical cell labels."
        )
    _require_qa_evidence_manifest(
        qa_evidence_manifest,
        qa_report=qa_report,
        pairs=pairs,
        agreement_evidence=agreement_evidence,
        raster_lineage=raster_lineage,
        raster_hashes=observed,
        reviewer_cell_hashes=reviewer_cell_hashes,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
    )
    _require_raw_release_qa_evidence(
        qa_report=qa_report,
        qa_evidence_manifest=qa_evidence_manifest,
        qa_report_path=qa_report_path,
        qa_raw_input_paths=qa_raw_input_paths,
        consensus_source_artifact_paths=consensus_source_artifact_paths,
    )
    release_metadata = build_release_metadata(
        metadata,
        adjudications=adjudications,
        qa_report=qa_report,
        qa_evidence_manifest=qa_evidence_manifest,
        agreement_evidence=agreement_evidence,
        raster_lineage=raster_lineage,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
    )
    try:
        verify_labelset_content(
            manifest,
            label_content=label_content,
            metadata=release_metadata,
            semantics=semantics,
        )
        if parent is not None:
            verify_manifest_lineage(manifest, parent)
    except LabelsetVersionError as exc:
        raise ReviewWorkflowError(f"Frozen labelset content failed validation: {exc}") from exc
    return _build_validation_receipt(
        labelset_id=manifest.labelset_id,
        labelset_manifest_sha256=manifest.manifest_sha256,
        raster_sha256_by_name=manifest.raster_sha256_by_name,
        qa_report=qa_report,
        qa_evidence_manifest=qa_evidence_manifest,
        agreement_evidence=agreement_evidence,
        raster_lineage=raster_lineage,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
        query_region_ids=tuple(sorted(derived_label_content)),
    )


def build_release_metadata(
    metadata: Mapping[str, Any],
    *,
    adjudications: Sequence[AdjudicationRecord],
    qa_report: QAReport,
    qa_evidence_manifest: Mapping[str, Any],
    agreement_evidence: Mapping[str, Any],
    raster_lineage: Mapping[str, Any],
    reviewer_calibration_receipt: ReviewerCalibrationReceipt,
) -> dict[str, Any]:
    """Attach derived, fail-closed release lineage without hiding conflicts."""

    if not isinstance(metadata, Mapping):
        raise ReviewWorkflowError("metadata must be a JSON object.")
    derived: dict[str, Any] = {
        "source_adjudication_ids": sorted(
            record.adjudication_id for record in adjudications
        ),
        "qa_ready": qa_report.ready,
        "qa_finding_count": len(qa_report.findings),
        "qa_evidence_manifest_sha256": _canonical_json_sha256(
            qa_evidence_manifest
        ),
        "reviewer_calibration_receipt_sha256": (
            reviewer_calibration_receipt.receipt_sha256
        ),
        "open_adjudication_count": 0,
        "agreement_evidence_sha256": _canonical_json_sha256(agreement_evidence),
        "raster_lineage_sha256": _canonical_json_sha256(raster_lineage),
        "eligible_for_query_model_training": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    conflicts = {
        key: (metadata[key], value)
        for key, value in derived.items()
        if key in metadata and metadata[key] != value
    }
    if conflicts:
        raise ReviewWorkflowError(
            "Supplied metadata conflicts with derived release evidence: "
            + ", ".join(sorted(conflicts))
        )
    return {**dict(metadata), **derived}


def _build_validation_receipt(
    *,
    labelset_id: str,
    labelset_manifest_sha256: str,
    raster_sha256_by_name: Sequence[tuple[str, str]],
    qa_report: QAReport,
    qa_evidence_manifest: Mapping[str, Any],
    agreement_evidence: Mapping[str, Any],
    raster_lineage: Mapping[str, Any],
    reviewer_calibration_receipt: ReviewerCalibrationReceipt,
    query_region_ids: tuple[str, ...],
) -> LabelsetValidationReceipt:
    validated = datetime.now(timezone.utc).replace(microsecond=0)
    values = {
        "labelset_id": labelset_id,
        "labelset_manifest_sha256": labelset_manifest_sha256,
        "validated_at_utc": validated,
        "qa_report_sha256": qa_report_content_sha256(qa_report),
        "qa_evidence_manifest_sha256": _canonical_json_sha256(
            qa_evidence_manifest
        ),
        "reviewer_calibration_receipt_sha256": (
            reviewer_calibration_receipt.receipt_sha256
        ),
        "agreement_evidence_sha256": _canonical_json_sha256(agreement_evidence),
        "raster_lineage_sha256": _canonical_json_sha256(raster_lineage),
        "raster_sha256_by_name": tuple(sorted(raster_sha256_by_name)),
        "grid_contract_sha256": _required_sha256_text(
            raster_lineage.get("grid_contract_sha256"),
            "validation receipt grid_contract_sha256",
        ),
        "query_region_ids": query_region_ids,
        "qa_ready": True,
        "open_adjudication_count": 0,
    }
    provisional = LabelsetValidationReceipt(**values, receipt_sha256="")
    return LabelsetValidationReceipt(
        **values,
        receipt_sha256=_canonical_json_sha256(
            provisional.to_dict(include_self_hash=False)
        ),
    )


def write_labelset_validation_receipt(
    receipt: LabelsetValidationReceipt,
    path: str | Path,
) -> Path:
    """Write one immutable, self-hashed release validation receipt."""

    _verify_validation_receipt(receipt)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(receipt.to_dict(), handle, sort_keys=True, indent=2)
        handle.write("\n")
    return target


def load_labelset_validation_receipt(
    path: str | Path,
) -> LabelsetValidationReceipt:
    """Load and cryptographically verify a validation receipt for downstream gates."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewWorkflowError(
            f"Could not load labelset validation receipt: {source}"
        ) from exc
    expected_keys = {
        "artifact_schema",
        "labelset_id",
        "labelset_manifest_sha256",
        "validated_at_utc",
        "qa_report_sha256",
        "qa_evidence_manifest_sha256",
        "reviewer_calibration_receipt_sha256",
        "agreement_evidence_sha256",
        "raster_lineage_sha256",
        "raster_sha256_by_name",
        "grid_contract_sha256",
        "query_region_ids",
        "qa_ready",
        "open_adjudication_count",
        "eligible_for_query_model_training",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "receipt_sha256",
    }
    if not isinstance(payload, Mapping) or set(payload) != expected_keys:
        raise ReviewWorkflowError(
            "Validation receipt has unexpected or missing fields."
        )
    if payload["artifact_schema"] != LABELSET_VALIDATION_RECEIPT_SCHEMA:
        raise ReviewWorkflowError("Unsupported labelset validation receipt schema.")
    if (
        payload["qa_ready"] is not True
        or payload["open_adjudication_count"] != 0
        or payload["eligible_for_query_model_training"] is not True
        or payload["eligible_for_decision_layer"] is not False
        or payload["eligible_for_fpps"] is not False
        or payload["eligible_for_warning"] is not False
    ):
        raise ReviewWorkflowError("Validation receipt contains unsafe release flags.")
    raster_hashes = _sha256_mapping(
        payload["raster_sha256_by_name"],
        label="validation receipt raster hashes",
    )
    query_ids = tuple(sorted(_string_set(
        payload["query_region_ids"], "validation receipt query_region_ids"
    )))
    receipt = LabelsetValidationReceipt(
        labelset_id=_required_text(payload["labelset_id"], "labelset_id"),
        labelset_manifest_sha256=_required_sha256_text(
            payload["labelset_manifest_sha256"], "labelset_manifest_sha256"
        ),
        validated_at_utc=_parse_timestamp(
            payload["validated_at_utc"], "validated_at_utc"
        ),
        qa_report_sha256=_required_sha256_text(
            payload["qa_report_sha256"], "qa_report_sha256"
        ),
        qa_evidence_manifest_sha256=_required_sha256_text(
            payload["qa_evidence_manifest_sha256"],
            "qa_evidence_manifest_sha256",
        ),
        reviewer_calibration_receipt_sha256=_required_sha256_text(
            payload["reviewer_calibration_receipt_sha256"],
            "reviewer_calibration_receipt_sha256",
        ),
        agreement_evidence_sha256=_required_sha256_text(
            payload["agreement_evidence_sha256"], "agreement_evidence_sha256"
        ),
        raster_lineage_sha256=_required_sha256_text(
            payload["raster_lineage_sha256"], "raster_lineage_sha256"
        ),
        raster_sha256_by_name=tuple(sorted(raster_hashes.items())),
        grid_contract_sha256=_required_sha256_text(
            payload["grid_contract_sha256"], "grid_contract_sha256"
        ),
        query_region_ids=query_ids,
        qa_ready=True,
        open_adjudication_count=0,
        receipt_sha256=_required_sha256_text(
            payload["receipt_sha256"], "receipt_sha256"
        ),
    )
    _verify_validation_receipt(receipt)
    return receipt


def _verify_validation_receipt(receipt: LabelsetValidationReceipt) -> None:
    if not isinstance(receipt, LabelsetValidationReceipt):
        raise ReviewWorkflowError("receipt must be a LabelsetValidationReceipt.")
    if not receipt.qa_ready or receipt.open_adjudication_count != 0:
        raise ReviewWorkflowError("Labelset validation receipt is not release-ready.")
    for field_name in (
        "labelset_manifest_sha256",
        "qa_report_sha256",
        "qa_evidence_manifest_sha256",
        "reviewer_calibration_receipt_sha256",
        "agreement_evidence_sha256",
        "raster_lineage_sha256",
        "grid_contract_sha256",
        "receipt_sha256",
    ):
        _required_sha256_text(getattr(receipt, field_name), field_name)
    if not receipt.query_region_ids or len(receipt.query_region_ids) != len(
        set(receipt.query_region_ids)
    ):
        raise ReviewWorkflowError(
            "Labelset validation receipt query ids must be non-empty and unique."
        )
    observed = _canonical_json_sha256(receipt.to_dict(include_self_hash=False))
    if observed != receipt.receipt_sha256:
        raise ReviewWorkflowError("Labelset validation receipt self-hash mismatch.")


def load_json_object(path: str | Path, *, label: str) -> Mapping[str, Any]:
    """Load a non-empty JSON object for metadata or semantics."""

    value = load_json_value(path, label=label)
    if not isinstance(value, Mapping) or not value:
        raise ReviewWorkflowError(f"{label} must be a non-empty JSON object.")
    return value


def load_json_value(path: str | Path, *, label: str) -> Any:
    """Load explicit JSON content without creating fallback values."""

    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewWorkflowError(f"Could not load {label} JSON: {source}") from exc
    _require_nonempty_content(value, label)
    return value


def parse_name_path(values: Sequence[str], *, label: str) -> dict[str, Path]:
    """Parse repeated ``NAME=PATH`` command-line values."""

    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ReviewWorkflowError(f"{label} must use NAME=PATH: {value!r}")
        name, raw_path = value.split("=", 1)
        normalized_name = _required_text(name, f"{label} name")
        normalized_path = _required_text(raw_path, f"{label} path")
        if normalized_name in result:
            raise ReviewWorkflowError(f"Duplicate {label} name: {normalized_name}")
        result[normalized_name] = Path(normalized_path)
    return result


def parse_name_sha256(values: Sequence[str], *, label: str) -> dict[str, str]:
    """Parse repeated ``NAME=SHA256`` command-line values."""

    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ReviewWorkflowError(f"{label} must use NAME=SHA256: {value!r}")
        name, digest = value.split("=", 1)
        normalized_name = _required_text(name, f"{label} name")
        normalized_digest = _required_text(digest, f"{label} digest").lower()
        if normalized_name in result:
            raise ReviewWorkflowError(f"Duplicate {label} name: {normalized_name}")
        if len(normalized_digest) != 64 or any(
            character not in "0123456789abcdef" for character in normalized_digest
        ):
            raise ReviewWorkflowError(f"Invalid SHA-256 for {normalized_name}.")
        result[normalized_name] = normalized_digest
    return result


def _validate_batch_append(
    existing: Sequence[AnnotationRecord],
    incoming: Sequence[AnnotationRecord],
    *,
    supersedes_by_id: Mapping[str, str],
) -> None:
    existing_ids = {record.annotation_id for record in existing}
    incoming_ids = [record.annotation_id for record in incoming]
    duplicates = sorted(existing_ids.intersection(incoming_ids))
    if duplicates:
        raise ReviewWorkflowError(
            "Annotation ids already exist and cannot be overwritten: "
            + ", ".join(duplicates)
        )
    if len(incoming_ids) != len(set(incoming_ids)):
        raise ReviewWorkflowError("Incoming annotation ids are not unique.")
    all_seen = list(existing)
    for record in incoming:
        same_series = [
            item
            for item in all_seen
            if (
                item.event_id,
                item.query_region_id,
                item.reviewer_id,
                item.review_stage,
            )
            == (
                record.event_id,
                record.query_region_id,
                record.reviewer_id,
                record.review_stage,
            )
        ]
        expected_revision = 1 + max(
            (item.reviewer_revision for item in same_series),
            default=0,
        )
        if record.reviewer_revision != expected_revision:
            raise ReviewWorkflowError(
                f"Annotation {record.annotation_id} has reviewer_revision "
                f"{record.reviewer_revision}; expected {expected_revision}."
            )
        supplied_parent = supersedes_by_id.get(record.annotation_id, "")
        if expected_revision == 1:
            if supplied_parent:
                raise ReviewWorkflowError(
                    f"First revision {record.annotation_id} must not supersede another annotation."
                )
        else:
            expected_parent = max(
                same_series,
                key=lambda item: item.reviewer_revision,
            ).annotation_id
            if supplied_parent != expected_parent:
                raise ReviewWorkflowError(
                    f"Annotation {record.annotation_id} must supersede {expected_parent}; "
                    f"received {supplied_parent or 'blank'}."
                )
        all_seen.append(record)


def _validate_queue_completeness(
    pairs: Sequence[ReviewerPair],
    queue_items: Sequence[AdjudicationQueueItem],
) -> None:
    """Prevent a disagreement from disappearing through an omitted queue row."""

    pair_by_query = {
        (pair.event_id, pair.query_region_id): pair
        for pair in pairs
    }
    if len(pair_by_query) != len(pairs):
        raise ReviewWorkflowError("Reviewer pairs contain duplicate event/query ids.")
    queue_by_query: dict[tuple[str, str], AdjudicationQueueItem] = {}
    for item in queue_items:
        key = (item.event_id, item.query_region_id)
        if key in queue_by_query:
            raise ReviewWorkflowError(
                f"Adjudication queue contains duplicate event/query row: {key}."
            )
        queue_by_query[key] = item
    required = {
        key: adjudication_reasons(pair)
        for key, pair in pair_by_query.items()
        if adjudication_reasons(pair)
    }
    missing = sorted(set(required) - set(queue_by_query))
    extra = sorted(set(queue_by_query) - set(required))
    if missing or extra:
        raise ReviewWorkflowError(
            "Adjudication queue does not exactly cover the latest review triggers; "
            f"missing={missing}, extra={extra}."
        )
    for key, reasons in required.items():
        item = queue_by_query[key]
        pair = pair_by_query[key]
        try:
            validate_queue_item_sources(item, pair)
        except AdjudicationError as exc:
            raise ReviewWorkflowError(str(exc)) from exc
        if set(item.reason_codes) != set(reasons):
            raise ReviewWorkflowError(
                f"Queue item {item.queue_id} reason codes do not match the latest reviews."
            )


def _cells_for_annotation(
    frame: pd.DataFrame,
    annotation: AnnotationRecord,
    *,
    use_grid: bool,
) -> pd.DataFrame:
    rows = frame.loc[frame["annotation_id"].astype(str) == annotation.annotation_id].copy()
    if rows.empty:
        raise ReviewWorkflowError(
            f"No canonical cell labels were supplied for {annotation.annotation_id}."
        )
    if (rows["query_region_id"].astype(str) != annotation.query_region_id).any():
        raise ReviewWorkflowError(
            f"Cell labels for {annotation.annotation_id} have the wrong query_region_id."
        )
    for value in rows["label_code"]:
        try:
            coerce_label_class(value)
        except ValueError as exc:
            raise ReviewWorkflowError(
                f"Unknown cell label for {annotation.annotation_id}: {value!r}"
            ) from exc
    if use_grid:
        for column in ("row_index", "column_index"):
            numeric = pd.to_numeric(rows[column], errors="coerce")
            if numeric.isna().any() or (numeric % 1 != 0).any() or (numeric < 0).any():
                raise ReviewWorkflowError(
                    f"{column} must contain non-negative integers for {annotation.annotation_id}."
                )
            rows[column] = numeric.astype(int)
    return rows


def _rectangular_grids(
    a_by_id: pd.DataFrame,
    b_by_id: pd.DataFrame,
    ordered_ids: Sequence[str],
) -> tuple[list[list[int]], list[list[int]]]:
    coordinates: list[tuple[int, int]] = []
    a_values: dict[tuple[int, int], int] = {}
    b_values: dict[tuple[int, int], int] = {}
    for cell_id in ordered_ids:
        a_coordinate = (
            int(a_by_id.at[cell_id, "row_index"]),
            int(a_by_id.at[cell_id, "column_index"]),
        )
        b_coordinate = (
            int(b_by_id.at[cell_id, "row_index"]),
            int(b_by_id.at[cell_id, "column_index"]),
        )
        if a_coordinate != b_coordinate:
            raise ReviewWorkflowError(
                f"Cell coordinate differs between reviewers for cell_id={cell_id}."
            )
        if a_coordinate in a_values:
            raise ReviewWorkflowError(
                f"Duplicate row/column coordinate in cell labels: {a_coordinate}."
            )
        coordinates.append(a_coordinate)
        a_values[a_coordinate] = int(coerce_label_class(a_by_id.at[cell_id, "label_code"]))
        b_values[a_coordinate] = int(coerce_label_class(b_by_id.at[cell_id, "label_code"]))
    rows = sorted({row for row, _ in coordinates})
    columns = sorted({column for _, column in coordinates})
    expected = {(row, column) for row in rows for column in columns}
    if set(coordinates) != expected:
        raise ReviewWorkflowError(
            "row_index/column_index cells must form a complete rectangular query grid."
        )
    return (
        [[a_values[(row, column)] for column in columns] for row in rows],
        [[b_values[(row, column)] for column in columns] for row in rows],
    )


def _verify_raster_checksums(
    raster_paths: Mapping[str, str | Path],
    expected: Mapping[str, str],
) -> dict[str, str]:
    if not raster_paths:
        raise ReviewWorkflowError(
            "At least one label raster and expected SHA-256 are required."
        )
    path_names = set(raster_paths)
    expected_names = set(expected)
    if path_names != expected_names:
        raise ReviewWorkflowError(
            "Raster paths and expected checksum names differ; "
            f"paths_only={sorted(path_names - expected_names)}, "
            f"checksums_only={sorted(expected_names - path_names)}."
        )
    observed: dict[str, str] = {}
    for name in sorted(path_names):
        source = Path(raster_paths[name])
        if not source.is_file():
            raise ReviewWorkflowError(f"Label raster does not exist: {source}")
        try:
            digest = file_sha256(source)
        except LabelsetVersionError as exc:
            raise ReviewWorkflowError(f"Could not hash label raster {source}: {exc}") from exc
        expected_digest = str(expected[name]).strip().lower()
        if digest != expected_digest:
            raise ReviewWorkflowError(
                f"Raster checksum mismatch for {name}: expected {expected_digest}, observed {digest}."
            )
        observed[name] = digest
    return observed


def _require_passing_qa(
    report: QAReport,
    *,
    required_check_ids: frozenset[str],
) -> None:
    if not isinstance(report, QAReport) or not report.findings:
        raise ReviewWorkflowError("A non-empty structured QA report is required.")
    if not report.ready:
        details = "; ".join(
            f"{finding.check_id}[{finding.entity_id}]"
            for finding in report.blocking_failures
        )
        raise ReviewWorkflowError(f"Label-factory QA has blocking failures: {details}")
    by_id: dict[str, list[QAFinding]] = {}
    for finding in report.findings:
        by_id.setdefault(finding.check_id, []).append(finding)
    missing = sorted(required_check_ids - set(by_id))
    failed_required = sorted(
        check_id
        for check_id in required_check_ids.intersection(by_id)
        if not all(finding.passed for finding in by_id[check_id])
    )
    if missing or failed_required:
        raise ReviewWorkflowError(
            "QA report does not satisfy the versioned release gate set; "
            f"missing={missing}, failed={failed_required}."
        )


def _require_raw_release_qa_evidence(
    *,
    qa_report: QAReport,
    qa_evidence_manifest: Mapping[str, Any],
    qa_report_path: str | Path,
    qa_raw_input_paths: Mapping[str, str | Path],
    consensus_source_artifact_paths: Mapping[str, str | Path],
) -> None:
    """Re-run release QA from the exact content-addressed source files."""

    if not isinstance(qa_raw_input_paths, Mapping):
        raise ReviewWorkflowError(
            "qa_raw_input_paths must map every canonical QA role to a file."
        )
    annotation_path = qa_raw_input_paths.get("annotations")
    consensus_annotation_path = consensus_source_artifact_paths.get(
        "annotation_log"
    )
    if annotation_path is None or consensus_annotation_path is None:
        raise ReviewWorkflowError(
            "Raw QA and consensus evidence must both name the annotation log."
        )
    try:
        same_annotation_source = (
            Path(annotation_path).resolve()
            == Path(consensus_annotation_path).resolve()
        )
    except OSError as exc:
        raise ReviewWorkflowError(
            "Could not resolve raw-QA annotation provenance."
        ) from exc
    if not same_annotation_source:
        raise ReviewWorkflowError(
            "Raw QA annotations must use the exact consensus annotation-log path."
        )
    try:
        verify_release_qa_artifacts(
            qa_report=qa_report,
            qa_receipt=qa_evidence_manifest,
            qa_report_path=qa_report_path,
            raw_input_paths=qa_raw_input_paths,
        )
    except ReleaseQAError as exc:
        raise ReviewWorkflowError(
            f"Raw release-QA evidence failed reproduction: {exc}"
        ) from exc


def _validate_adjudication_closure(
    pairs: Sequence[ReviewerPair],
    queue_items: Sequence[AdjudicationQueueItem],
    adjudications: Sequence[AdjudicationRecord],
) -> dict[tuple[str, str], AdjudicationRecord]:
    """Return the exact resolution for every queued query or fail closed."""

    try:
        open_items = unresolved_queue_items(queue_items, adjudications)
    except AdjudicationError as exc:
        raise ReviewWorkflowError(f"Invalid adjudication closure: {exc}") from exc
    if open_items:
        raise ReviewWorkflowError(
            f"{len(open_items)} adjudication item(s) remain open: "
            + ", ".join(item.queue_id for item in open_items)
        )
    adjudication_ids = [record.adjudication_id for record in adjudications]
    if len(adjudication_ids) != len(set(adjudication_ids)):
        raise ReviewWorkflowError("Adjudication ids must be unique across the release.")
    pair_keys = {(pair.event_id, pair.query_region_id) for pair in pairs}
    result: dict[tuple[str, str], AdjudicationRecord] = {}
    for record in adjudications:
        key = (record.event_id, record.query_region_id)
        if key not in pair_keys:
            raise ReviewWorkflowError(
                f"Adjudication {record.adjudication_id} belongs to an unknown review query."
            )
        if key in result:
            raise ReviewWorkflowError(
                f"Review query {key} has more than one adjudication resolution."
            )
        result[key] = record
    return result


def _require_agreement_gates(
    evidence: Mapping[str, Any],
    *,
    pairs: Sequence[ReviewerPair],
    grid_contract_sha256: str,
) -> dict[str, str]:
    """Validate metrics and bind them to exact reviews and cell artifacts."""

    if not isinstance(evidence, Mapping):
        raise ReviewWorkflowError("agreement_evidence must be a JSON object.")
    if evidence.get("artifact_schema") != AGREEMENT_EVIDENCE_SCHEMA:
        raise ReviewWorkflowError(
            f"agreement_evidence must use artifact_schema={AGREEMENT_EVIDENCE_SCHEMA!r}."
        )
    if evidence.get("measurement_unit") != "canonical_cell_labels":
        raise ReviewWorkflowError(
            "agreement_evidence measurement_unit must be canonical_cell_labels."
        )
    if not _is_sha256(grid_contract_sha256):
        raise ReviewWorkflowError("Agreement grid_contract_sha256 is invalid.")
    if evidence.get("grid_contract_sha256") != grid_contract_sha256:
        raise ReviewWorkflowError(
            "Agreement evidence is bound to a different canonical grid contract."
        )
    if not pairs:
        raise ReviewWorkflowError("Agreement evidence requires at least one reviewer pair.")
    reviewer_a_id = pairs[0].reviewer_a.reviewer_id
    reviewer_b_id = pairs[0].reviewer_b.reviewer_id
    if (
        evidence.get("reviewer_a_id") != reviewer_a_id
        or evidence.get("reviewer_b_id") != reviewer_b_id
    ):
        raise ReviewWorkflowError(
            "Agreement reviewer A/B identities do not match the release reviewers."
        )
    annotations = [
        record
        for pair in pairs
        for record in (pair.reviewer_a, pair.reviewer_b)
    ]
    expected_annotation_hashes = {
        record.annotation_id: annotation_content_sha256(record)
        for record in annotations
    }
    expected_import_provenance: dict[str, dict[str, str]] = {}
    for record in annotations:
        provenance = {
            field_name: getattr(record, field_name)
            for field_name in (
                "bundle_manifest_sha256",
                "context_manifest_sha256",
                "grid_contract_sha256",
                "source_registry_sha256",
            )
        }
        if any(not _is_sha256(value) for value in provenance.values()):
            raise ReviewWorkflowError(
                f"Latest annotation {record.annotation_id} lacks formal immutable bundle provenance."
            )
        if provenance["grid_contract_sha256"] != grid_contract_sha256:
            raise ReviewWorkflowError(
                f"Latest annotation {record.annotation_id} is bound to a different grid contract."
            )
        expected_import_provenance[record.annotation_id] = {
            key: str(value) for key, value in provenance.items()
        }
    observed_import_provenance = evidence.get(
        "review_import_provenance_by_annotation_id"
    )
    if observed_import_provenance != expected_import_provenance:
        raise ReviewWorkflowError(
            "Agreement evidence review-import provenance does not match exact bundle-bound annotations."
        )
    observed_annotation_hashes = _sha256_mapping(
        evidence.get("annotation_sha256_by_id"),
        label="agreement annotation_sha256_by_id",
    )
    if observed_annotation_hashes != expected_annotation_hashes:
        raise ReviewWorkflowError(
            "Agreement evidence annotation ids or hashes do not match the exact latest reviews."
        )
    reviewer_cell_hashes = _sha256_mapping(
        evidence.get("reviewer_cell_artifact_sha256_by_annotation_id"),
        label="reviewer-cell artifact hashes",
    )
    if set(reviewer_cell_hashes) != set(expected_annotation_hashes):
        raise ReviewWorkflowError(
            "Agreement reviewer-cell artifact hashes must exactly cover the latest reviews."
        )
    expected_query_ids = {pair.query_region_id for pair in pairs}
    if len(expected_query_ids) != len(pairs):
        raise ReviewWorkflowError(
            "query_region_id must be globally unique for release evidence binding."
        )
    if _string_set(evidence.get("query_region_ids"), "agreement query_region_ids") != expected_query_ids:
        raise ReviewWorkflowError(
            "Agreement evidence query_region_ids do not exactly match reviewer pairs."
        )
    try:
        aggregate = evidence["aggregate"]
        flood = aggregate["per_class"]["1"]
        dice = float(flood["dice_f1"])
        iou = float(flood["iou"])
        kappa = float(aggregate["cohen_kappa"])
        query_count = int(evidence["query_count"])
        total_cell_count = int(evidence["total_cell_count"])
        boundary_count = int(evidence["boundary_metric_query_count"])
        per_query = evidence["per_query"]
        critical_strata = evidence["critical_strata"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ReviewWorkflowError(
            "agreement_evidence is missing required aggregate, boundary, or lineage fields."
        ) from exc
    if query_count != len(pairs) or boundary_count != query_count:
        raise ReviewWorkflowError(
            "Agreement query counts must exactly cover every formal query and boundary metric."
        )
    if not isinstance(per_query, Sequence) or isinstance(per_query, (str, bytes)):
        raise ReviewWorkflowError("Agreement per_query must be a JSON array.")
    expected_by_query = {pair.query_region_id: pair for pair in pairs}
    seen_queries: set[str] = set()
    boundary_values: list[float] = []
    observed_cell_count = 0
    try:
        for row in per_query:
            if not isinstance(row, Mapping):
                raise TypeError("per-query row is not an object")
            query_id = _required_text(row["query_region_id"], "query_region_id")
            if query_id in seen_queries or query_id not in expected_by_query:
                raise ReviewWorkflowError(
                    f"Agreement contains duplicate or unknown query_region_id: {query_id}"
                )
            seen_queries.add(query_id)
            pair = expected_by_query[query_id]
            exact_identity = (
                row.get("event_id"),
                row.get("tile_id"),
                row.get("reviewer_a_annotation_id"),
                row.get("reviewer_b_annotation_id"),
                row.get("reviewer_a_annotation_sha256"),
                row.get("reviewer_b_annotation_sha256"),
                row.get("reviewer_a_cell_artifact_sha256"),
                row.get("reviewer_b_cell_artifact_sha256"),
            )
            expected_identity = (
                pair.event_id,
                pair.tile_id,
                pair.reviewer_a.annotation_id,
                pair.reviewer_b.annotation_id,
                expected_annotation_hashes[pair.reviewer_a.annotation_id],
                expected_annotation_hashes[pair.reviewer_b.annotation_id],
                reviewer_cell_hashes[pair.reviewer_a.annotation_id],
                reviewer_cell_hashes[pair.reviewer_b.annotation_id],
            )
            if exact_identity != expected_identity:
                raise ReviewWorkflowError(
                    f"Agreement lineage for {query_id} does not match its exact A/B artifacts."
                )
            cell_count = int(row["cell_count"])
            if cell_count <= 0:
                raise ValueError("cell_count must be positive")
            observed_cell_count += cell_count
            boundary_values.append(float(row["agreement"]["boundary"]["f1"]))
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ReviewWorkflowError):
            raise
        raise ReviewWorkflowError(
            "Per-query agreement evidence lacks exact artifact lineage, cell count, or boundary F1."
        ) from exc
    if seen_queries != expected_query_ids or total_cell_count != observed_cell_count:
        raise ReviewWorkflowError(
            "Agreement per-query coverage or total_cell_count does not match the release."
        )
    if not boundary_values or sum(boundary_values) / len(boundary_values) < 0.75:
        raise ReviewWorkflowError("Mean reviewer boundary F1 is below 0.75.")
    if dice < 0.80 or iou < 0.67 or kappa < 0.80:
        raise ReviewWorkflowError(
            "Reviewer agreement is below the provisional Dice/IoU/kappa release gates."
        )
    if not all(math.isfinite(value) for value in (dice, iou, kappa, *boundary_values)):
        raise ReviewWorkflowError("Agreement metrics must be finite numeric values.")
    if not isinstance(critical_strata, Mapping) or not critical_strata:
        raise ReviewWorkflowError(
            "Agreement evidence must report at least one critical-stratum Dice slice."
        )
    try:
        stratum_values = {str(name): float(value) for name, value in critical_strata.items()}
        if not all(math.isfinite(value) for value in stratum_values.values()):
            raise ValueError("non-finite stratum metric")
        bad_strata = sorted(
            str(name)
            for name, value in stratum_values.items()
            if value < 0.70
        )
    except (TypeError, ValueError) as exc:
        raise ReviewWorkflowError(
            "Critical-stratum agreement values must be numeric."
        ) from exc
    if bad_strata:
        raise ReviewWorkflowError(
            "Critical-stratum reviewer Dice is below 0.70 for: "
            + ", ".join(bad_strata)
        )
    return reviewer_cell_hashes


def qa_report_content_sha256(report: QAReport) -> str:
    """Return the stable content digest used by versioned QA receipts."""

    if not isinstance(report, QAReport):
        raise ReviewWorkflowError("qa_report must be a QAReport.")
    rows = sorted(
        report.to_rows(),
        key=lambda row: (
            str(row["check_id"]),
            str(row["entity_id"]),
            str(row["severity"]),
        ),
    )
    return _canonical_json_sha256(rows)


def build_release_qa_evidence_manifest(
    *,
    qa_report: QAReport,
    pairs: Sequence[ReviewerPair],
    agreement_evidence: Mapping[str, Any],
    raster_lineage: Mapping[str, Any],
    raster_hashes: Mapping[str, str],
    reviewer_calibration_receipt: ReviewerCalibrationReceipt,
    qa_protocol_version: str,
) -> dict[str, Any]:
    """Assemble reviewer/raster bindings for the code-owned QA receipt.

    This is an internal base receipt, not a releasable artifact by itself.
    :func:`release_qa.write_release_qa_artifacts_from_raw` must extend it with
    exact raw-input hashes, validator/schema versions, deterministic QA-report
    bytes, decision-safety fields, and a receipt self-hash before freeze.
    """

    _require_passing_qa(
        qa_report,
        required_check_ids=REQUIRED_RELEASE_QA_CHECK_IDS,
    )
    protocol = _required_text(qa_protocol_version, "qa_protocol_version")
    try:
        verify_reviewer_calibration_receipt(reviewer_calibration_receipt)
    except ReviewerCalibrationError as exc:
        raise ReviewWorkflowError(
            f"Reviewer calibration evidence failed: {exc}"
        ) from exc
    grid_hash = _required_sha256_text(
        raster_lineage.get("grid_contract_sha256"),
        "raster_lineage grid_contract_sha256",
    )
    reviewer_cell_hashes = _require_agreement_gates(
        agreement_evidence,
        pairs=pairs,
        grid_contract_sha256=grid_hash,
    )
    report_entities_by_check: dict[str, set[str]] = {}
    for finding in qa_report.findings:
        report_entities_by_check.setdefault(finding.check_id, set()).add(
            finding.entity_id
        )
    source_product_ids = report_entities_by_check.get("source_product_id", set())
    annotations = [
        record
        for pair in pairs
        for record in (pair.reviewer_a, pair.reviewer_b)
    ]
    evidence: dict[str, Any] = {
        "artifact_schema": QA_EVIDENCE_SCHEMA,
        "qa_protocol_version": protocol,
        "qa_report_sha256": qa_report_content_sha256(qa_report),
        "grid_contract_sha256": grid_hash,
        "event_ids": sorted({pair.event_id for pair in pairs}),
        "query_region_ids": sorted({pair.query_region_id for pair in pairs}),
        "source_annotation_ids": sorted(
            record.annotation_id for record in annotations
        ),
        "source_annotation_sha256_by_id": {
            record.annotation_id: annotation_content_sha256(record)
            for record in sorted(annotations, key=lambda item: item.annotation_id)
        },
        "source_product_ids": sorted(source_product_ids),
        "check_entity_ids": {
            check_id: sorted(entity_ids)
            for check_id, entity_ids in sorted(report_entities_by_check.items())
        },
        "audited_entity_ids": sorted(
            {finding.entity_id for finding in qa_report.findings}
        ),
        "audited_artifact_sha256": {
            "reviewer_calibration_receipt": (
                reviewer_calibration_receipt.receipt_sha256
            ),
            "agreement_evidence": _canonical_json_sha256(agreement_evidence),
            "raster_lineage": _canonical_json_sha256(raster_lineage),
            **{
                f"label_raster:{name}": _required_sha256_text(
                    digest, f"raster hash {name}"
                )
                for name, digest in sorted(raster_hashes.items())
            },
            **{
                f"reviewer_cell:{annotation_id}": digest
                for annotation_id, digest in sorted(reviewer_cell_hashes.items())
            },
        },
    }
    _require_qa_evidence_manifest(
        evidence,
        qa_report=qa_report,
        pairs=pairs,
        agreement_evidence=agreement_evidence,
        raster_lineage=raster_lineage,
        raster_hashes=raster_hashes,
        reviewer_cell_hashes=reviewer_cell_hashes,
        reviewer_calibration_receipt=reviewer_calibration_receipt,
    )
    return evidence


def _require_qa_evidence_manifest(
    evidence: Mapping[str, Any],
    *,
    qa_report: QAReport,
    pairs: Sequence[ReviewerPair],
    agreement_evidence: Mapping[str, Any],
    raster_lineage: Mapping[str, Any],
    raster_hashes: Mapping[str, str],
    reviewer_cell_hashes: Mapping[str, str],
    reviewer_calibration_receipt: ReviewerCalibrationReceipt,
) -> None:
    """Require a versioned receipt binding QA rows to exact audited artifacts."""

    if not isinstance(evidence, Mapping) or evidence.get("artifact_schema") != QA_EVIDENCE_SCHEMA:
        raise ReviewWorkflowError(
            f"qa_evidence_manifest must use artifact_schema={QA_EVIDENCE_SCHEMA!r}."
        )
    if not str(evidence.get("qa_protocol_version", "")).strip():
        raise ReviewWorkflowError("qa_evidence_manifest qa_protocol_version is required.")
    if evidence.get("qa_report_sha256") != qa_report_content_sha256(qa_report):
        raise ReviewWorkflowError("QA evidence is bound to a different QA report.")
    grid_hash = str(raster_lineage.get("grid_contract_sha256", ""))
    if evidence.get("grid_contract_sha256") != grid_hash:
        raise ReviewWorkflowError("QA evidence is bound to a different grid contract.")
    event_ids = {pair.event_id for pair in pairs}
    query_ids = {pair.query_region_id for pair in pairs}
    annotations = [
        record
        for pair in pairs
        for record in (pair.reviewer_a, pair.reviewer_b)
    ]
    annotation_ids = {record.annotation_id for record in annotations}
    annotation_hashes = {
        record.annotation_id: annotation_content_sha256(record)
        for record in annotations
    }
    exact_sets = (
        ("event_ids", event_ids),
        ("query_region_ids", query_ids),
        ("source_annotation_ids", annotation_ids),
    )
    for field_name, expected in exact_sets:
        if _string_set(evidence.get(field_name), f"QA {field_name}") != expected:
            raise ReviewWorkflowError(
                f"QA evidence {field_name} does not exactly match release entities."
            )
    if _sha256_mapping(
        evidence.get("source_annotation_sha256_by_id"),
        label="QA source annotation hashes",
    ) != annotation_hashes:
        raise ReviewWorkflowError(
            "QA evidence source annotation ids or hashes do not match latest reviews."
        )
    source_product_ids = _string_set(
        evidence.get("source_product_ids"), "QA source_product_ids"
    )
    if len(source_product_ids) < 2:
        raise ReviewWorkflowError(
            "QA evidence requires at least the explicit pre- and event-time source products."
        )
    finding_keys = [(finding.check_id, finding.entity_id) for finding in qa_report.findings]
    if len(finding_keys) != len(set(finding_keys)):
        raise ReviewWorkflowError("QA report contains duplicate check/entity findings.")
    report_entities_by_check: dict[str, set[str]] = {}
    for finding in qa_report.findings:
        report_entities_by_check.setdefault(finding.check_id, set()).add(
            finding.entity_id
        )
    coverage = evidence.get("check_entity_ids")
    if not isinstance(coverage, Mapping) or set(coverage) != set(report_entities_by_check):
        raise ReviewWorkflowError(
            "QA check_entity_ids must name every and only QA report check."
        )
    for check_id, observed in report_entities_by_check.items():
        declared = _string_set(coverage.get(check_id), f"QA entities for {check_id}")
        if declared != observed:
            raise ReviewWorkflowError(
                f"QA entity coverage for {check_id} does not match report findings."
            )
    for check_id in (
        "source_product_id",
        "source_acquisition_time",
        "rights_processing",
        "rights_label_derivation",
    ):
        if report_entities_by_check.get(check_id) != source_product_ids:
            raise ReviewWorkflowError(
                f"QA check {check_id} must cover every exact source product."
            )
    for check_id in ("pre_post_pair_present", "pre_before_post"):
        if report_entities_by_check.get(check_id) != event_ids:
            raise ReviewWorkflowError(
                f"QA check {check_id} must cover every exact event."
            )
    all_report_entities = {entity for _, entity in finding_keys}
    if _string_set(
        evidence.get("audited_entity_ids"), "QA audited_entity_ids"
    ) != all_report_entities:
        raise ReviewWorkflowError(
            "QA audited_entity_ids do not exactly cover report entities."
        )
    expected_artifacts = {
        "reviewer_calibration_receipt": (
            reviewer_calibration_receipt.receipt_sha256
        ),
        "agreement_evidence": _canonical_json_sha256(agreement_evidence),
        "raster_lineage": _canonical_json_sha256(raster_lineage),
        **{f"label_raster:{name}": digest for name, digest in raster_hashes.items()},
        **{
            f"reviewer_cell:{annotation_id}": digest
            for annotation_id, digest in reviewer_cell_hashes.items()
        },
    }
    observed_artifacts = _sha256_mapping(
        evidence.get("audited_artifact_sha256"),
        label="QA audited artifact hashes",
    )
    if observed_artifacts != expected_artifacts:
        raise ReviewWorkflowError(
            "QA audited artifact hashes do not exactly match calibration, agreement, lineage, cells, and rasters."
        )


def _validate_raster_lineage(
    lineage: Mapping[str, Any],
    *,
    raster_paths: Mapping[str, str | Path],
    observed_raster_hashes: Mapping[str, str],
    pairs: Sequence[ReviewerPair],
    resolutions_by_query: Mapping[tuple[str, str], AdjudicationRecord],
    queue_items: Sequence[AdjudicationQueueItem],
    reviewer_cell_hashes: Mapping[str, str],
    consensus_source_artifact_paths: Mapping[str, str | Path],
) -> dict[str, list[int]]:
    if not isinstance(lineage, Mapping) or lineage.get("artifact_schema") != LABEL_RASTER_LINEAGE_SCHEMA:
        raise ReviewWorkflowError(
            f"raster_lineage must use artifact_schema={LABEL_RASTER_LINEAGE_SCHEMA!r}."
        )
    source_annotation_ids = {
        record.annotation_id
        for pair in pairs
        for record in (pair.reviewer_a, pair.reviewer_b)
    }
    source_adjudication_ids = {
        record.adjudication_id for record in resolutions_by_query.values()
    }
    if set(lineage.get("source_annotation_ids", ())) != source_annotation_ids:
        raise ReviewWorkflowError("raster_lineage source_annotation_ids do not match release sources.")
    if set(lineage.get("source_adjudication_ids", ())) != source_adjudication_ids:
        raise ReviewWorkflowError("raster_lineage source_adjudication_ids do not match release sources.")
    grid_hash = str(lineage.get("grid_contract_sha256", ""))
    if len(grid_hash) != 64 or any(character not in "0123456789abcdefABCDEF" for character in grid_hash):
        raise ReviewWorkflowError("raster_lineage grid_contract_sha256 is invalid.")
    if not str(lineage.get("rasterizer_version", "")).strip():
        raise ReviewWorkflowError("raster_lineage rasterizer_version is required.")
    raster_contracts = lineage.get("rasters")
    if not isinstance(raster_contracts, Mapping) or set(raster_contracts) != set(raster_paths):
        raise ReviewWorkflowError("raster_lineage raster names do not match supplied rasters.")
    pair_by_query = {pair.query_region_id: pair for pair in pairs}
    if len(pair_by_query) != len(pairs):
        raise ReviewWorkflowError("query_region_id must be globally unique in raster lineage.")
    expected_registry_by_query: dict[str, str] = {}
    for pair in pairs:
        source_registries = {
            pair.reviewer_a.source_registry_sha256,
            pair.reviewer_b.source_registry_sha256,
        }
        if len(source_registries) != 1 or not _is_sha256(next(iter(source_registries))):
            raise ReviewWorkflowError(
                f"Reviewer pair {pair.query_region_id} does not share one source registry hash."
            )
        expected_registry_by_query[pair.query_region_id] = str(
            next(iter(source_registries))
        )
    if lineage.get("source_registry_sha256_by_query") != expected_registry_by_query:
        raise ReviewWorkflowError(
            "Raster lineage source registry mapping does not exactly cover reviewer queries."
        )
    resolution_by_query_id = {
        query_id: record
        for (_event_id, query_id), record in resolutions_by_query.items()
    }
    combined: dict[str, list[tuple[str, int]]] = {}
    raster_by_query: dict[str, str] = {}
    seen_cells: set[tuple[str, str]] = set()
    used_adjudication_ids: set[str] = set()
    for name, path_value in raster_paths.items():
        contract = raster_contracts[name]
        if not isinstance(contract, Mapping):
            raise ReviewWorkflowError(f"Raster lineage contract for {name} must be an object.")
        if contract.get("format") != "canonical_cell_csv_v1":
            raise ReviewWorkflowError(
                f"Raster {name} must use canonical_cell_csv_v1 until a GeoTIFF validator is implemented."
            )
        if str(contract.get("sha256", "")).lower() != observed_raster_hashes[name]:
            raise ReviewWorkflowError(f"Raster lineage SHA-256 mismatch for {name}.")
        try:
            cells = pd.read_csv(path_value, dtype=str, keep_default_na=False)
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            raise ReviewWorkflowError(f"Could not read canonical label cells {name}.") from exc
        required = (
            "event_id",
            "tile_id",
            "query_region_id",
            "cell_id",
            "row_index",
            "column_index",
            "label_code",
            "source_annotation_id",
            "source_adjudication_id",
            "grid_contract_sha256",
            "source_registry_sha256",
        )
        _require_columns(cells, required, f"canonical label cells {name}")
        if cells.empty or cells.duplicated(["query_region_id", "cell_id"]).any():
            raise ReviewWorkflowError(f"Canonical label cells {name} are empty or duplicated.")
        if not cells["grid_contract_sha256"].eq(grid_hash).all():
            raise ReviewWorkflowError(f"Canonical label cells {name} use a different grid hash.")
        labels = pd.to_numeric(cells["label_code"], errors="coerce")
        if (
            labels.isna().any()
            or (labels % 1 != 0).any()
            or not set(labels.astype(int)).issubset(ALLOWED_LABEL_CODES)
        ):
            raise ReviewWorkflowError(f"Canonical label cells {name} contain invalid label codes.")
        for coordinate_column in ("row_index", "column_index"):
            coordinates = pd.to_numeric(cells[coordinate_column], errors="coerce")
            if (
                coordinates.isna().any()
                or (coordinates % 1 != 0).any()
                or (coordinates < 0).any()
            ):
                raise ReviewWorkflowError(
                    f"Canonical label cells {name} contain invalid {coordinate_column}."
                )
        if cells.duplicated(
            ["query_region_id", "row_index", "column_index"]
        ).any():
            raise ReviewWorkflowError(
                f"Canonical label cells {name} duplicate a query row/column coordinate."
            )
        if len(cells) != int(contract.get("cell_count", -1)):
            raise ReviewWorkflowError(f"Raster lineage cell_count mismatch for {name}.")
        observed_counts = {
            str(code): int(count)
            for code, count in labels.astype(int).value_counts().sort_index().items()
        }
        declared_counts = {
            str(key): int(value)
            for key, value in dict(contract.get("class_counts", {})).items()
        }
        if observed_counts != declared_counts:
            raise ReviewWorkflowError(f"Raster lineage class_counts mismatch for {name}.")
        for row in cells.to_dict("records"):
            query_id = str(row["query_region_id"]).strip()
            cell_id = str(row["cell_id"]).strip()
            if query_id not in pair_by_query:
                raise ReviewWorkflowError(
                    f"Canonical raster {name} contains unknown query_region_id {query_id}."
                )
            cell_key = (query_id, cell_id)
            if cell_key in seen_cells:
                raise ReviewWorkflowError(
                    f"Canonical cell is duplicated across release rasters: {cell_key}."
                )
            seen_cells.add(cell_key)
            previous_raster = raster_by_query.setdefault(query_id, name)
            if previous_raster != name:
                raise ReviewWorkflowError(
                    f"Query {query_id} is split across multiple canonical raster artifacts."
                )
            annotation_id = str(row["source_annotation_id"]).strip()
            adjudication_id = str(row["source_adjudication_id"]).strip()
            if bool(annotation_id) == bool(adjudication_id):
                raise ReviewWorkflowError(
                    "Each canonical label cell must reference exactly one source annotation or adjudication."
                )
            resolution = resolution_by_query_id.get(query_id)
            pair = pair_by_query[query_id]
            if (
                str(row["event_id"]).strip() != pair.event_id
                or str(row["tile_id"]).strip() != pair.tile_id
                or str(row["source_registry_sha256"]).strip()
                != expected_registry_by_query[query_id]
            ):
                raise ReviewWorkflowError(
                    f"Canonical cell lineage does not match event/tile/source registry for {query_id}."
                )
            label_code = int(row["label_code"])
            if resolution is None:
                allowed_annotations = {
                    pair.reviewer_a.annotation_id,
                    pair.reviewer_b.annotation_id,
                }
                if annotation_id not in allowed_annotations or adjudication_id:
                    raise ReviewWorkflowError(
                        f"Non-adjudicated query {query_id} must use only its paired annotation ids."
                    )
            else:
                if resolution.outcome is AdjudicationOutcome.REJECT:
                    raise ReviewWorkflowError(
                        f"Rejected adjudication {resolution.adjudication_id} must contribute no cells."
                    )
                if annotation_id or adjudication_id != resolution.adjudication_id:
                    raise ReviewWorkflowError(
                        f"Queued query {query_id} must use its exact adjudication id on every cell."
                    )
                used_adjudication_ids.add(adjudication_id)
                if (
                    resolution.outcome is AdjudicationOutcome.UNCERTAIN
                    and label_code not in {3, 255}
                ):
                    raise ReviewWorkflowError(
                        f"Uncertain adjudication {adjudication_id} may emit only "
                        "label_code=3 or explicitly unreviewed label_code=255."
                    )
                if (
                    resolution.outcome is AdjudicationOutcome.UNOBSERVABLE
                    and label_code not in {4, 255}
                ):
                    raise ReviewWorkflowError(
                        f"Unobservable adjudication {adjudication_id} may emit only "
                        "label_code=4 or explicitly unreviewed label_code=255."
                    )
            combined.setdefault(query_id, []).append(
                (cell_id, label_code)
            )
    expected_queries = {
        pair.query_region_id
        for pair in pairs
        if resolution_by_query_id.get(pair.query_region_id) is None
        or resolution_by_query_id[pair.query_region_id].outcome
        is not AdjudicationOutcome.REJECT
    }
    if set(combined) != expected_queries:
        raise ReviewWorkflowError(
            "Canonical raster query coverage does not match non-rejected review queries; "
            f"missing={sorted(expected_queries - set(combined))}, "
            f"extra={sorted(set(combined) - expected_queries)}."
        )
    expected_used_adjudications = {
        record.adjudication_id
        for record in resolutions_by_query.values()
        if record.outcome is not AdjudicationOutcome.REJECT
    }
    if used_adjudication_ids != expected_used_adjudications:
        raise ReviewWorkflowError(
            "Every non-reject adjudication must be used and reject outcomes must be unused."
        )
    for query_id, resolution in resolution_by_query_id.items():
        if resolution.outcome is AdjudicationOutcome.REJECT:
            continue
        labels = [label for _cell_id, label in combined.get(query_id, ())]
        if not any(label != 255 for label in labels):
            raise ReviewWorkflowError(
                f"Non-rejected adjudication {resolution.adjudication_id} must retain at "
                "least one reviewed non-255 cell."
            )
    _validate_consensus_builder_receipt(
        lineage.get("consensus_builder_receipt"),
        resolutions_by_query=resolutions_by_query,
        pairs=pairs,
        queue_items=queue_items,
        reviewer_cell_hashes=reviewer_cell_hashes,
        lineage=lineage,
        consensus_source_artifact_paths=consensus_source_artifact_paths,
        combined=combined,
        raster_by_query=raster_by_query,
        grid_contract_sha256=grid_hash,
        observed_raster_hashes=observed_raster_hashes,
    )
    return {
        query_id: [label for _cell_id, label in sorted(values)]
        for query_id, values in sorted(combined.items())
    }


def _validate_consensus_builder_receipt(
    receipt: Any,
    *,
    resolutions_by_query: Mapping[tuple[str, str], AdjudicationRecord],
    pairs: Sequence[ReviewerPair],
    queue_items: Sequence[AdjudicationQueueItem],
    reviewer_cell_hashes: Mapping[str, str],
    lineage: Mapping[str, Any],
    consensus_source_artifact_paths: Mapping[str, str | Path],
    combined: Mapping[str, list[tuple[str, int]]],
    raster_by_query: Mapping[str, str],
    grid_contract_sha256: str,
    observed_raster_hashes: Mapping[str, str],
) -> None:
    """Rebuild and bind every consensus branch to its exact source artifacts."""

    geometry_resolutions = {
        record.adjudication_id: record
        for record in resolutions_by_query.values()
        if record.outcome
        in {
            AdjudicationOutcome.ACCEPT_A,
            AdjudicationOutcome.ACCEPT_B,
            AdjudicationOutcome.REDRAW,
        }
    }
    if not isinstance(receipt, Mapping) or receipt.get("artifact_schema") != CONSENSUS_BUILDER_RECEIPT_SCHEMA:
        raise ReviewWorkflowError(
            "Every consensus release requires a versioned consensus-builder receipt."
        )
    if not str(receipt.get("builder_version", "")).strip():
        raise ReviewWorkflowError("Consensus-builder receipt builder_version is required.")
    declared_self_hash = _required_sha256_text(
        receipt.get("receipt_sha256"), "consensus receipt_sha256"
    )
    unsigned_receipt = dict(receipt)
    unsigned_receipt.pop("receipt_sha256", None)
    if _canonical_json_sha256(unsigned_receipt) != declared_self_hash:
        raise ReviewWorkflowError("Consensus-builder receipt self-hash mismatch.")
    if receipt.get("grid_contract_sha256") != grid_contract_sha256:
        raise ReviewWorkflowError("Consensus-builder receipt grid contract mismatch.")
    raw_geometry_ids = receipt.get("source_adjudication_ids")
    if not isinstance(raw_geometry_ids, Sequence) or isinstance(
        raw_geometry_ids, (str, bytes)
    ):
        raise ReviewWorkflowError(
            "consensus source_adjudication_ids must be an array."
        )
    normalized_geometry_ids = [
        _required_text(value, "consensus source_adjudication_id")
        for value in raw_geometry_ids
    ]
    if len(normalized_geometry_ids) != len(set(normalized_geometry_ids)) or set(
        normalized_geometry_ids
    ) != set(geometry_resolutions):
        raise ReviewWorkflowError(
            "Consensus-builder receipt must exactly cover accept/redraw adjudications."
        )
    if _sha256_mapping(
        receipt.get("output_raster_sha256_by_name"),
        label="consensus output raster hashes",
    ) != dict(observed_raster_hashes):
        raise ReviewWorkflowError(
            "Consensus-builder receipt output raster hashes do not match release rasters."
        )
    if len(observed_raster_hashes) != 1 or len(set(raster_by_query.values())) != 1:
        raise ReviewWorkflowError(
            "A deterministic consensus release must use one logical final-cell raster."
        )

    expected_roles = {
        "annotation_log",
        "reviewer_a_cells",
        "reviewer_a_manifest",
        "reviewer_b_cells",
        "reviewer_b_manifest",
        "adjudication_queue",
        "adjudication_log",
        "query_manifest",
    }
    has_redraw = any(
        record.outcome is AdjudicationOutcome.REDRAW
        for record in resolutions_by_query.values()
    )
    if has_redraw:
        expected_roles.update({"redraw_cells", "redraw_manifest"})
    if not isinstance(consensus_source_artifact_paths, Mapping) or set(
        consensus_source_artifact_paths
    ) != expected_roles:
        raise ReviewWorkflowError(
            "Consensus source artifact paths must exactly cover the builder inputs; "
            f"expected={sorted(expected_roles)}."
        )
    declared_input_hashes = _sha256_mapping(
        receipt.get("input_artifact_sha256"),
        label="consensus input artifact hashes",
    )
    if set(declared_input_hashes) != expected_roles:
        raise ReviewWorkflowError(
            "Consensus receipt input artifacts do not exactly cover builder inputs."
        )
    observed_input_hashes: dict[str, str] = {}
    source_paths: dict[str, Path] = {}
    for role, raw_path in consensus_source_artifact_paths.items():
        path = Path(raw_path)
        missing_empty_adjudication_log = (
            role == "adjudication_log" and not queue_items and not path.exists()
        )
        if not path.is_file() and not missing_empty_adjudication_log:
            raise ReviewWorkflowError(
                f"Consensus source artifact does not exist for {role}: {path}"
            )
        source_paths[role] = path
        observed_input_hashes[role] = (
            hashlib.sha256(b"").hexdigest()
            if missing_empty_adjudication_log
            else file_sha256(path)
        )
    if observed_input_hashes != declared_input_hashes:
        raise ReviewWorkflowError(
            "Consensus source artifact hashes do not match the builder receipt."
        )
    if lineage.get("input_artifact_sha256") != declared_input_hashes:
        raise ReviewWorkflowError(
            "Raster lineage input artifacts do not match the consensus receipt."
        )

    annotations = [
        record for pair in pairs for record in (pair.reviewer_a, pair.reviewer_b)
    ]
    expected_annotation_hashes = {
        record.annotation_id: annotation_content_sha256(record)
        for record in annotations
    }
    if receipt.get("source_annotation_content_sha256") != expected_annotation_hashes:
        raise ReviewWorkflowError(
            "Consensus receipt source annotations do not match the locked reviewer pairs."
        )
    resolutions = sorted(
        resolutions_by_query.values(), key=lambda record: record.adjudication_id
    )
    expected_adjudication_hashes = {
        record.adjudication_id: _canonical_json_sha256(record.to_dict())
        for record in resolutions
    }
    if receipt.get("source_adjudication_content_sha256") != expected_adjudication_hashes:
        raise ReviewWorkflowError(
            "Consensus receipt adjudication content does not match locked outcomes."
        )
    reviewer_a_hash = observed_input_hashes["reviewer_a_cells"]
    reviewer_b_hash = observed_input_hashes["reviewer_b_cells"]
    for pair in pairs:
        if reviewer_cell_hashes.get(pair.reviewer_a.annotation_id) != reviewer_a_hash:
            raise ReviewWorkflowError(
                "Consensus reviewer A cell artifact is not the agreement source artifact."
            )
        if reviewer_cell_hashes.get(pair.reviewer_b.annotation_id) != reviewer_b_hash:
            raise ReviewWorkflowError(
                "Consensus reviewer B cell artifact is not the agreement source artifact."
            )

    try:
        from floodguard.label_factory.consensus_builder import (
            ConsensusBuilderError,
            build_consensus_artifacts,
        )

        query_manifest = pd.read_csv(source_paths["query_manifest"]).fillna("")
        reviewer_a_cells = pd.read_csv(
            source_paths["reviewer_a_cells"], dtype=str, keep_default_na=False
        )
        reviewer_b_cells = pd.read_csv(
            source_paths["reviewer_b_cells"], dtype=str, keep_default_na=False
        )
        reviewer_a_manifest = json.loads(
            source_paths["reviewer_a_manifest"].read_text(encoding="utf-8")
        )
        reviewer_b_manifest = json.loads(
            source_paths["reviewer_b_manifest"].read_text(encoding="utf-8")
        )
        redraw_cells = None
        redraw_manifest = None
        if has_redraw:
            redraw_cells = pd.read_csv(
                source_paths["redraw_cells"], dtype=str, keep_default_na=False
            )
            redraw_manifest = json.loads(
                source_paths["redraw_manifest"].read_text(encoding="utf-8")
            )
        raster_name = next(iter(observed_raster_hashes))
        rebuilt = build_consensus_artifacts(
            annotation_records=annotations,
            reviewer_a_id=pairs[0].reviewer_a.reviewer_id,
            reviewer_b_id=pairs[0].reviewer_b.reviewer_id,
            reviewer_a_cells=reviewer_a_cells,
            reviewer_a_manifest=reviewer_a_manifest,
            reviewer_a_cell_name=source_paths["reviewer_a_cells"].name,
            reviewer_a_cell_sha256=reviewer_a_hash,
            reviewer_b_cells=reviewer_b_cells,
            reviewer_b_manifest=reviewer_b_manifest,
            reviewer_b_cell_name=source_paths["reviewer_b_cells"].name,
            reviewer_b_cell_sha256=reviewer_b_hash,
            queue_items=queue_items,
            adjudications=resolutions,
            query_manifest=query_manifest,
            output_raster_name=raster_name,
            source_artifact_sha256=observed_input_hashes,
            redraw_cells=redraw_cells,
            redraw_manifest=redraw_manifest,
            redraw_cell_name=(
                source_paths["redraw_cells"].name if has_redraw else None
            ),
            redraw_cell_sha256=(
                observed_input_hashes["redraw_cells"] if has_redraw else None
            ),
            builder_version=str(receipt["builder_version"]),
        )
    except (OSError, ValueError, json.JSONDecodeError, ConsensusBuilderError) as exc:
        raise ReviewWorkflowError(
            f"Consensus source artifacts cannot reproduce the release: {exc}"
        ) from exc
    if rebuilt.consensus_receipt != dict(receipt):
        raise ReviewWorkflowError(
            "Consensus receipt sections do not exactly reproduce from locked sources and outcomes."
        )
    if rebuilt.raster_lineage != dict(lineage):
        raise ReviewWorkflowError(
            "Raster lineage does not exactly match the independently rebuilt consensus lineage."
        )


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _required_sha256_text(value: Any, field_name: str) -> str:
    if not _is_sha256(value):
        raise ReviewWorkflowError(
            f"{field_name} must be a lowercase SHA-256 digest."
        )
    return str(value)


def _sha256_mapping(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ReviewWorkflowError(f"{label} must be a non-empty JSON object.")
    result: dict[str, str] = {}
    for raw_name, raw_digest in value.items():
        name = _required_text(raw_name, f"{label} key")
        if name in result:
            raise ReviewWorkflowError(f"{label} contains duplicate key {name}.")
        result[name] = _required_sha256_text(raw_digest, f"{label}[{name}]")
    return result


def _string_set(value: Any, label: str) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ReviewWorkflowError(f"{label} must be a JSON array of strings.")
    normalized = [_required_text(item, label) for item in value]
    if not normalized or len(normalized) != len(set(normalized)):
        raise ReviewWorkflowError(f"{label} must be non-empty and contain no duplicates.")
    return set(normalized)


def _require_nonempty_content(value: Any, label: str) -> None:
    if value is None or value == "" or value == [] or value == {}:
        raise ReviewWorkflowError(f"{label} must be supplied and non-empty.")


def _load_expected_regions(
    source: str | Path | pd.DataFrame,
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    frame = _coerce_frame(source)
    required = ("event_id", "tile_id", "query_region_id")
    _require_columns(frame, required, "blinded review manifest")
    if frame.empty:
        raise ReviewWorkflowError("Blinded review manifest contains no regions.")
    keys = {
        (
            _required_text(row["event_id"], "event_id"),
            _required_text(row["tile_id"], "tile_id"),
            _required_text(row["query_region_id"], "query_region_id"),
        ): row
        for row in frame.to_dict(orient="records")
    }
    if len(keys) != len(frame):
        raise ReviewWorkflowError("Blinded review manifest contains duplicate regions.")
    return keys


def _validate_formal_bundle_binding(
    *,
    review_regions: str | Path | pd.DataFrame | None,
    bundle_manifest: str | Path | pd.DataFrame | None,
    context_layers: str | Path | pd.DataFrame | None,
    governance_package: str | Path | None,
    grid_validation_receipt: str | Path | None,
    canonical_tile_manifest: str | Path | None,
    canonical_query_manifest: str | Path | None,
    supported_query_derivation: str | Path | None,
    allow_ungoverned_fixture: bool,
) -> dict[str, Any]:
    """Verify formal reviewer artifacts against their immutable bundle manifest."""

    named_sources = {
        "review_regions": review_regions,
        "bundle_manifest": bundle_manifest,
        "context_layers": context_layers,
    }
    missing = [name for name, value in named_sources.items() if value is None]
    if missing:
        raise ReviewWorkflowError(
            "Formal review import requires original bundle artifacts: "
            + ", ".join(missing)
        )
    if any(isinstance(value, pd.DataFrame) for value in named_sources.values()):
        raise ReviewWorkflowError(
            "Formal review bundle binding requires original files, not reconstructed dataframes."
        )
    region_path = Path(review_regions)  # type: ignore[arg-type]
    manifest_path = Path(bundle_manifest)  # type: ignore[arg-type]
    context_path = Path(context_layers)  # type: ignore[arg-type]
    for path in (region_path, manifest_path, context_path):
        if not path.is_file():
            raise ReviewWorkflowError(f"Formal review bundle artifact does not exist: {path}")
    manifest = _coerce_frame(manifest_path)
    _require_columns(
        manifest,
        (
            "file_name",
            "bundle_role",
            "sha256",
            "model_predictions_visible",
            "review_stage",
            "review_purpose",
            "governance_package_id",
            "governance_package_manifest_sha256",
            "governance_package_seal_sha256",
            "aligned_context_inventory_sha256",
            "grid_validation_receipt_sha256",
            "grid_validation_receipt_file_sha256",
            "canonical_tile_manifest_file_sha256",
            "canonical_query_manifest_file_sha256",
            "supported_query_derivation_file_sha256",
            "supported_query_derivation_sha256",
            "supported_query_csv_sha256",
            "governance_binding_status",
            "production_review_eligible",
            "processing_alignment_receipt_sha256",
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
        ),
        "bundle manifest",
    )
    if manifest.empty or manifest["bundle_role"].astype(str).duplicated().any():
        raise ReviewWorkflowError("Bundle manifest roles must be non-empty and unique.")
    expected_roles = {
        "reviewer_visible_regions": region_path,
        "approved_context_source_evidence": context_path,
    }
    rows_by_role = {
        str(row["bundle_role"]).strip(): row
        for row in manifest.to_dict(orient="records")
    }
    for role, row in rows_by_role.items():
        file_name = str(row["file_name"]).strip()
        if (
            not file_name
            or Path(file_name).name != file_name
            or "/" in file_name
            or "\\" in file_name
        ):
            raise ReviewWorkflowError(
                f"Bundle manifest role {role!r} has an unsafe file name."
            )
        artifact_path = manifest_path.parent / file_name
        if not artifact_path.is_file():
            raise ReviewWorkflowError(
                f"Bundle manifest artifact does not exist for role {role}: "
                f"{artifact_path}"
            )
        expected_hash = _required_sha256_text(row["sha256"], f"{role} sha256")
        if file_sha256(artifact_path) != expected_hash:
            raise ReviewWorkflowError(f"Bundle file checksum mismatch for role {role}.")
        for flag in (
            "model_predictions_visible",
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
        ):
            if _strict_bool(row[flag], flag):
                raise ReviewWorkflowError(
                    f"Formal bundle role {role} has unsafe {flag}=true."
                )
    for role, path in expected_roles.items():
        row = rows_by_role.get(role)
        if row is None:
            raise ReviewWorkflowError(f"Bundle manifest is missing required role {role}.")
        if str(row["file_name"]).strip() != path.name:
            raise ReviewWorkflowError(
                f"Bundle role {role} names a different file than the supplied artifact."
            )
    processing_row = rows_by_role.get("processing_alignment_provenance")
    if processing_row is None:
        raise ReviewWorkflowError(
            "Bundle manifest is missing required role "
            "processing_alignment_provenance."
        )
    processing_path = manifest_path.parent / str(processing_row["file_name"])

    binding_fields = (
        "governance_package_id",
        "governance_package_manifest_sha256",
        "governance_package_seal_sha256",
        "aligned_context_inventory_sha256",
        "grid_validation_receipt_sha256",
        "grid_validation_receipt_file_sha256",
        "canonical_tile_manifest_file_sha256",
        "canonical_query_manifest_file_sha256",
        "supported_query_derivation_file_sha256",
        "supported_query_derivation_sha256",
        "supported_query_csv_sha256",
        "governance_binding_status",
        "processing_alignment_receipt_sha256",
    )
    binding: dict[str, str] = {}
    for field in binding_fields:
        values = {str(value).strip() for value in manifest[field]}
        if len(values) != 1:
            raise ReviewWorkflowError(
                f"Bundle manifest rows disagree on governance field {field}."
            )
        binding[field] = next(iter(values))
    production_values = {
        _strict_bool(value, "production_review_eligible")
        for value in manifest["production_review_eligible"]
    }
    if len(production_values) != 1:
        raise ReviewWorkflowError(
            "Bundle manifest rows disagree on production_review_eligible."
        )
    production_eligible = next(iter(production_values))
    review_stage_values = {
        str(value).strip() for value in manifest["review_stage"]
    }
    review_purpose_values = {
        str(value).strip() for value in manifest["review_purpose"]
    }
    if len(review_stage_values) != 1 or next(iter(review_stage_values)) not in {
        "primary",
        "secondary",
    }:
        raise ReviewWorkflowError(
            "Bundle manifest must declare one primary or secondary review stage."
        )
    if len(review_purpose_values) != 1:
        raise ReviewWorkflowError(
            "Bundle manifest must declare one review purpose."
        )
    bundle_review_stage = next(iter(review_stage_values))
    try:
        bundle_review_purpose = ReviewPurpose(next(iter(review_purpose_values)))
    except ValueError as exc:
        raise ReviewWorkflowError(
            "Bundle manifest declares an unsupported review purpose."
        ) from exc
    receipt_self_hash = _required_sha256_text(
        binding["processing_alignment_receipt_sha256"],
        "processing_alignment_receipt_sha256",
    )

    processing_receipt: Mapping[str, Any] | None = None
    if allow_ungoverned_fixture:
        if (
            binding["governance_binding_status"] != "synthetic_fixture_only"
            or production_eligible
            or any(
                binding[field]
                for field in (
                    "governance_package_id",
                    "governance_package_manifest_sha256",
                    "governance_package_seal_sha256",
                    "aligned_context_inventory_sha256",
                    "grid_validation_receipt_sha256",
                    "grid_validation_receipt_file_sha256",
                    "canonical_tile_manifest_file_sha256",
                    "canonical_query_manifest_file_sha256",
                    "supported_query_derivation_file_sha256",
                    "supported_query_derivation_sha256",
                    "supported_query_csv_sha256",
                )
            )
        ):
            raise ReviewWorkflowError(
                "Fixture formal imports require an explicitly synthetic, "
                "production-ineligible bundle manifest."
            )
    else:
        if governance_package is None:
            raise ReviewWorkflowError(
                "Formal review import requires the matching governance package."
            )
        required_grid_inputs = {
            "grid_validation_receipt": grid_validation_receipt,
            "canonical_tile_manifest": canonical_tile_manifest,
            "canonical_query_manifest": canonical_query_manifest,
        }
        missing_grid_inputs = [
            name for name, value in required_grid_inputs.items() if value is None
        ]
        if missing_grid_inputs:
            raise ReviewWorkflowError(
                "Formal review import requires canonical grid evidence: "
                + ", ".join(missing_grid_inputs)
            )
        if (
            binding["governance_binding_status"] != "validated"
            or not production_eligible
        ):
            raise ReviewWorkflowError(
                "Formal review import rejects synthetic or production-ineligible "
                "bundle governance."
            )
        governance_root = Path(governance_package)
        try:
            seal = validate_rights_clearance_package(governance_root)
            processing_receipt = validate_processing_alignment_receipt(
                processing_path,
                governance_root / "events.csv",
                governance_root / "source_assets.csv",
                governance_package=governance_root,
            )
            validate_static_review_context_against_governance(
                context_path,
                governance_root,
            )
            grid_binding = validate_review_queries_against_canonical_grid(
                region_path,
                _coerce_frame(region_path),
                governance_package=governance_root,
                processing_alignment_receipt=processing_path,
                grid_validation_receipt=grid_validation_receipt,  # type: ignore[arg-type]
                canonical_tile_manifest=canonical_tile_manifest,  # type: ignore[arg-type]
                canonical_query_manifest=canonical_query_manifest,  # type: ignore[arg-type]
                supported_query_derivation=supported_query_derivation,
            )
        except (
            ProcessingAlignmentError,
            RightsClearanceError,
            ReviewBundleError,
            OSError,
            ValueError,
        ) as exc:
            raise ReviewWorkflowError(
                f"Formal review governance binding failed: {exc}"
            ) from exc
        expected_binding = {
            "governance_package_id": str(seal["package_id"]),
            "governance_package_manifest_sha256": str(
                seal["package_manifest_sha256"]
            ),
            "governance_package_seal_sha256": str(seal["seal_sha256"]),
            "aligned_context_inventory_sha256": file_sha256(
                governance_root / "aligned_context_inventory.csv"
            ),
            "grid_validation_receipt_sha256": str(
                grid_binding["grid_receipt"]["receipt_sha256"]
            ),
            "grid_validation_receipt_file_sha256": file_sha256(
                Path(grid_validation_receipt)  # type: ignore[arg-type]
            ),
            "canonical_tile_manifest_file_sha256": file_sha256(
                Path(canonical_tile_manifest)  # type: ignore[arg-type]
            ),
            "canonical_query_manifest_file_sha256": file_sha256(
                Path(canonical_query_manifest)  # type: ignore[arg-type]
            ),
            "supported_query_derivation_file_sha256": (
                file_sha256(Path(supported_query_derivation))
                if supported_query_derivation is not None
                else ""
            ),
            "supported_query_derivation_sha256": str(
                grid_binding["grid_receipt"][
                    "supported_query_derivation_sha256"
                ]
            ),
            "supported_query_csv_sha256": str(
                grid_binding["supported_query_csv_sha256"]
            ),
        }
        mismatches = [
            field
            for field, expected_value in expected_binding.items()
            if binding[field] != expected_value
        ]
        if mismatches:
            raise ReviewWorkflowError(
                "Bundle governance identity does not match the supplied package: "
                + ", ".join(mismatches)
                + "."
            )
        if str(processing_receipt["receipt_sha256"]) != receipt_self_hash:
            raise ReviewWorkflowError(
                "Bundle manifest processing receipt hash does not match the copied "
                "validated receipt."
            )
    context = _coerce_frame(context_path)
    _require_columns(
        context,
        (
            "context_layer_id",
            "event_id",
            "layer_role",
            "source_registry_sha256",
            "source_sha256",
            "processed_layer_sha256",
            "allowed_for_blinded_review",
        ),
        "context-layer manifest",
    )
    if context.empty:
        raise ReviewWorkflowError("Context-layer manifest contains no approved evidence.")
    layer_ids = context["context_layer_id"].astype(str).str.strip()
    if layer_ids.eq("").any() or layer_ids.duplicated().any():
        raise ReviewWorkflowError("Context-layer ids must be non-blank and unique.")
    for row in context.to_dict(orient="records"):
        _required_text(str(row["event_id"]), "context event_id")
        _required_text(str(row["layer_role"]), "context layer_role")
        _required_sha256_text(row["source_sha256"], "context source_sha256")
        _required_sha256_text(
            row["processed_layer_sha256"], "context processed_layer_sha256"
        )
        if not _strict_bool(
            row["allowed_for_blinded_review"], "allowed_for_blinded_review"
        ):
            raise ReviewWorkflowError(
                f"Context layer {row['context_layer_id']} is not approved for blinded review."
            )
    regions = _coerce_frame(region_path)
    _require_columns(
        regions,
        (
            "event_id",
            "grid_contract_sha256",
            "source_registry_sha256",
            "processing_alignment_receipt_sha256",
            "dataset_role",
        ),
        "review-regions artifact",
    )
    region_events = {str(value).strip() for value in regions["event_id"]}
    context_events = {str(value).strip() for value in context["event_id"]}
    if region_events != context_events:
        raise ReviewWorkflowError(
            "Context-layer events do not exactly match formal review-region events."
        )
    try:
        region_roles = {
            DatasetRole(str(value).strip()) for value in regions["dataset_role"]
        }
    except ValueError as exc:
        raise ReviewWorkflowError(
            "Review regions contain an unsupported dataset role."
        ) from exc
    if not region_roles or not region_roles.issubset(
        REVIEW_PURPOSE_ALLOWED_ROLES[bundle_review_purpose]
    ):
        raise ReviewWorkflowError(
            "Bundle review purpose is incompatible with its canonical dataset role."
        )
    derivative_rows_present = context["layer_role"].astype(str).isin(
        DERIVATIVE_CONTEXT_LAYER_ROLES
    ).any()
    derivative_manifest_fields = (
        "review_derivative_lineage_receipt_sha256",
        "review_derivative_lineage_receipt_file_sha256",
        "governed_derivative_layers_included",
    )
    present_derivative_fields = [
        field for field in derivative_manifest_fields if field in manifest.columns
    ]
    derivative_row = rows_by_role.get("review_derivative_lineage_provenance")
    derivative_receipt_path: Path | None = None
    formal_review_evidence_not_before_utc: datetime | None = None
    if derivative_rows_present:
        missing_derivative_fields = sorted(
            set(derivative_manifest_fields) - set(manifest.columns)
        )
        if missing_derivative_fields:
            raise ReviewWorkflowError(
                "A derivative-bearing bundle manifest lacks lineage fields: "
                + ", ".join(missing_derivative_fields)
            )
        if derivative_row is None:
            raise ReviewWorkflowError(
                "A derivative-bearing bundle lacks review_derivative_lineage_provenance."
            )
        derivative_receipt_path = manifest_path.parent / str(
            derivative_row["file_name"]
        )
        derivative_binding: dict[str, str] = {}
        for field in derivative_manifest_fields[:2]:
            values = {str(value).strip() for value in manifest[field]}
            if len(values) != 1:
                raise ReviewWorkflowError(
                    f"Bundle manifest rows disagree on derivative field {field}."
                )
            derivative_binding[field] = next(iter(values))
        included_values = {
            _strict_bool(value, "governed_derivative_layers_included")
            for value in manifest["governed_derivative_layers_included"]
        }
        if included_values != {True}:
            raise ReviewWorkflowError(
                "Derivative-bearing bundles must declare governed derivatives included."
            )
        expected_file_hash = _required_sha256_text(
            derivative_binding[
                "review_derivative_lineage_receipt_file_sha256"
            ],
            "review_derivative_lineage_receipt_file_sha256",
        )
        if file_sha256(derivative_receipt_path) != expected_file_hash:
            raise ReviewWorkflowError(
                "Copied review-derivative receipt file hash does not match the "
                "bundle manifest."
            )
        try:
            derivative_receipt = validate_review_derivative_lineage_receipt(
                derivative_receipt_path,
                processing_alignment_receipt=processing_path,
                review_manifest=regions,
                context_manifest=context,
                governance_package=governance_package,
                allow_ungoverned_fixture=allow_ungoverned_fixture,
            )
        except ReviewDerivativeLineageError as exc:
            raise ReviewWorkflowError(
                f"Formal review derivative-lineage binding failed: {exc}"
            ) from exc
        expected_self_hash = _required_sha256_text(
            derivative_binding["review_derivative_lineage_receipt_sha256"],
            "review_derivative_lineage_receipt_sha256",
        )
        if derivative_receipt["receipt_sha256"] != expected_self_hash:
            raise ReviewWorkflowError(
                "Review-derivative receipt self-hash does not match the bundle manifest."
            )
        if "created_at_utc" not in manifest.columns:
            raise ReviewWorkflowError(
                "A derivative-bearing bundle must record artifact creation times."
            )
        bundle_created_values = {
            _parse_timestamp(value, "bundle created_at_utc")
            for value in manifest["created_at_utc"]
        }
        if len(bundle_created_values) != 1:
            raise ReviewWorkflowError(
                "Derivative-bearing bundle rows disagree on creation time."
            )
        derivative_validated_at = _parse_timestamp(
            derivative_receipt["validated_at_utc"],
            "derivative validated_at_utc",
        )
        formal_review_evidence_not_before_utc = max(
            derivative_validated_at,
            next(iter(bundle_created_values)),
        )
    else:
        if derivative_row is not None:
            raise ReviewWorkflowError(
                "Bundle carries derivative-lineage provenance without derivative context."
            )
        if present_derivative_fields and len(present_derivative_fields) != len(
            derivative_manifest_fields
        ):
            raise ReviewWorkflowError(
                "Bundle manifest contains partial derivative-lineage fields."
            )
        if present_derivative_fields:
            for field in derivative_manifest_fields[:2]:
                if any(str(value).strip() for value in manifest[field]):
                    raise ReviewWorkflowError(
                        "Non-derivative bundle contains a derivative receipt identity."
                    )
            included_values = {
                _strict_bool(value, "governed_derivative_layers_included")
                for value in manifest["governed_derivative_layers_included"]
            }
            if included_values != {False}:
                raise ReviewWorkflowError(
                    "Non-derivative bundle cannot declare governed derivatives included."
                )
    if not allow_ungoverned_fixture:
        assert processing_receipt is not None
        for event_id, event_regions in regions.groupby("event_id", sort=False):
            event_context = context.loc[
                context["event_id"].astype(str).eq(str(event_id))
            ]
            region_hashes = set(
                event_regions["source_registry_sha256"].astype(str)
            )
            context_hashes = set(
                event_context["source_registry_sha256"].astype(str)
            )
            if len(region_hashes) != 1 or context_hashes != region_hashes:
                raise ReviewWorkflowError(
                    "Context layers do not bind the same event-scoped source "
                    f"lineage as review regions for {event_id!r}."
                )
        if set(
            regions["processing_alignment_receipt_sha256"].astype(str)
        ) != {receipt_self_hash}:
            raise ReviewWorkflowError(
                "Review regions do not bind the governed processing receipt."
            )
        try:
            rebuilt_context = build_blinded_context_manifest(
                context,
                regions,
                derivative_lineage_receipt=derivative_receipt_path,
            )
            validate_processing_receipt_for_review_bundle(
                dict(processing_receipt),
                review_manifest=regions,
                context_manifest=rebuilt_context,
            )
        except ReviewBundleError as exc:
            raise ReviewWorkflowError(
                f"Formal review source-lineage binding failed: {exc}"
            ) from exc
    return {
        "bundle_manifest_sha256": file_sha256(manifest_path),
        "context_manifest_sha256": file_sha256(context_path),
        "review_regions_sha256": file_sha256(region_path),
        "context_frame": context,
        "review_stage": bundle_review_stage,
        "review_purpose": bundle_review_purpose.value,
        "formal_review_evidence_not_before_utc": (
            formal_review_evidence_not_before_utc
        ),
    }


def _validate_used_context_layers(
    evidence_layers: Sequence[str],
    *,
    event_id: str,
    context_frame: pd.DataFrame,
) -> None:
    event_rows = context_frame.loc[
        context_frame["event_id"].astype(str).eq(event_id)
    ]
    approved_tokens = {
        str(value).strip()
        for column in ("context_layer_id", "layer_role")
        for value in event_rows[column]
        if str(value).strip()
    }
    unknown = sorted(set(evidence_layers) - approved_tokens)
    if unknown:
        raise ReviewWorkflowError(
            f"Annotation uses context evidence not approved by its exact bundle: {unknown}."
        )


def _optional_source_sha256(
    source: str | Path | pd.DataFrame | None,
) -> str | None:
    if source is None or isinstance(source, pd.DataFrame):
        return None
    return file_sha256(source)


def _validate_legacy_geometry_echo(
    annotation_id: str,
    legacy_geometry: str | None,
    parts: pd.DataFrame,
) -> None:
    """Reject a stale single-WKT echo while binding the multipart artifact."""

    nonblank_parts = [
        str(value).strip()
        for value in parts["geometry_wkt"]
        if str(value).strip()
    ]
    if legacy_geometry is None:
        return
    if len(nonblank_parts) != 1:
        raise ReviewWorkflowError(
            f"Annotation {annotation_id} supplies legacy geometry_wkt but its formal "
            "geometry-parts artifact does not contain exactly one drawable part."
        )
    normalize = lambda value: " ".join(value.strip().split()).upper()
    if normalize(legacy_geometry) != normalize(nonblank_parts[0]):
        raise ReviewWorkflowError(
            f"Annotation {annotation_id} geometry_wkt does not match its bound geometry part."
        )


def _coerce_frame(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    try:
        return pd.read_csv(source, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ReviewWorkflowError(f"Could not read CSV: {source}") from exc


def _require_columns(frame: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ReviewWorkflowError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewWorkflowError(f"{field_name} must not be blank.")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _split_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    text = str(value).strip()
    if not text:
        return ()
    normalized = text.replace(",", ";")
    return tuple(part.strip() for part in normalized.split(";") if part.strip())


def _strict_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    raise ReviewWorkflowError(f"{field_name} must be literal true or false.")


def _strict_positive_integer(value: Any, field_name: str) -> int:
    text = str(value).strip()
    if not text.isdigit() or int(text) < 1:
        raise ReviewWorkflowError(f"{field_name} must be a positive integer.")
    return int(text)


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    text = _required_text(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewWorkflowError(f"{field_name} is not a valid timestamp: {text!r}") from exc
    return _as_utc(parsed, field_name)


def _as_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ReviewWorkflowError(f"{field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _positive_pixel_size(value: float | None) -> float:
    if value is None or value <= 0:
        raise ReviewWorkflowError(
            "A positive pixel_size_m is required when row/column grids are supplied."
        )
    return float(value)


def _require_distinct_new_paths(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if len(resolved) != len(set(resolved)):
        raise ReviewWorkflowError("Output paths must be distinct.")
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise ReviewWorkflowError(
            "Immutable output already exists and cannot be overwritten: "
            + ", ".join(existing)
        )
