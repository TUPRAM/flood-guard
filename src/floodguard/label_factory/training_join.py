"""Content-addressed reviewed-cell to ``sar_change_v2`` training joins.

This is the only repository-owned path that promotes a frozen reviewed label
release into query-committee training rows.  It deliberately derives label
semantics and safety fields from validated release lineage; caller-provided
``binary_target`` or eligibility flags are rejected rather than trusted.

The resulting table remains query-model-only.  It cannot feed FloodGuard's
decision layer, FPPS, action classes, or warnings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import pandas as pd

from floodguard.label_factory.contracts import DatasetRole, FloodLabel
from floodguard.label_factory.feature_schema import get_feature_schema
from floodguard.label_factory.review_workflow import (
    ReviewWorkflowError,
    load_labelset_validation_receipt,
)
from floodguard.label_factory.versioning import (
    LabelsetManifest,
    LabelsetVersionError,
    load_labelset_manifest,
)


TRAINING_DERIVATION_SCHEMA = "floodguard.query_training_derivation.v1"
RELEASE_VALIDATION_RECEIPT_SCHEMA = "floodguard.labelset_validation_receipt.v1"
TRAINING_TABLE_FILENAME = "query_model_training_cells.csv"
DERIVATION_MANIFEST_FILENAME = "query_model_training_derivation.json"
FEATURE_SCHEMA_VERSION = "sar_change_v2"
QUERY_POOL_ROLE = DatasetRole.TRAINING_AND_QUERY_POOL.value

JOIN_KEYS: tuple[str, ...] = (
    "query_region_id",
    "cell_id",
    "grid_contract_sha256",
)
FINAL_CELL_COLUMNS: tuple[str, ...] = (
    *JOIN_KEYS,
    "event_id",
    "tile_id",
    "source_registry_sha256",
    "row_index",
    "column_index",
    "label_code",
    "source_annotation_id",
    "source_adjudication_id",
)
FEATURE_METADATA_COLUMNS: tuple[str, ...] = (
    *JOIN_KEYS,
    "spatial_group_id",
    "dataset_role",
    "feature_schema_version",
)
DERIVED_SEMANTIC_COLUMNS = frozenset(
    {
        "binary_target",
        "label_source_type",
        "eligible_for_query_model_training",
        "labelset_version",
        "labelset_manifest_sha256",
        "release_validation_receipt_sha256",
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    }
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")


class TrainingJoinError(ValueError):
    """Raised when release, feature, join, or derivation evidence fails closed."""


@dataclass(frozen=True, slots=True)
class TrainingTablePaths:
    """Immutable artifacts produced by one reviewed-label derivation."""

    training_csv: Path
    derivation_manifest: Path

    def as_dict(self) -> dict[str, Path]:
        return {
            "training_csv": self.training_csv,
            "derivation_manifest": self.derivation_manifest,
        }


@dataclass(frozen=True, slots=True)
class VerifiedTrainingDerivation:
    """Provenance returned after rechecking a training CSV byte-for-byte."""

    labelset_id: str
    labelset_manifest_sha256: str
    release_validation_receipt_sha256: str
    training_csv_sha256: str
    derivation_manifest_sha256: str
    grid_contract_sha256: str
    query_region_ids: tuple[str, ...]
    row_count: int


@dataclass(frozen=True, slots=True)
class _VerifiedReleaseReceipt:
    payload: Mapping[str, Any]
    path: Path
    file_sha256: str
    receipt_sha256: str
    grid_contract_sha256: str
    query_region_ids: tuple[str, ...]
    raster_sha256_by_name: tuple[tuple[str, str], ...]


def build_and_write_training_table(
    *,
    labelset_manifest_path: str | Path,
    release_validation_receipt_path: str | Path,
    final_cell_csv: str | Path,
    feature_csv: str | Path,
    output_directory: str | Path,
    created_at_utc: datetime | str | None = None,
) -> TrainingTablePaths:
    """Build and atomically persist an immutable query-model training table."""

    output = Path(output_directory)
    if output.exists():
        raise TrainingJoinError(
            f"Output directory already exists and cannot be overwritten: {output}"
        )
    labelset_path = _existing_file(labelset_manifest_path, "labelset manifest")
    receipt_path = _existing_file(
        release_validation_receipt_path, "release validation receipt"
    )
    cells_path = _existing_csv(final_cell_csv, "canonical final-cell")
    features_path = _existing_csv(feature_csv, "sar_change_v2 feature")
    try:
        labelset = load_labelset_manifest(labelset_path)
    except LabelsetVersionError as exc:
        raise TrainingJoinError(f"Frozen labelset manifest is invalid: {exc}") from exc
    receipt = _load_verified_release_receipt(receipt_path, labelset=labelset)

    source_hashes = {
        "labelset_file": _file_sha256(labelset_path),
        "receipt_file": receipt.file_sha256,
        "final_cells": _file_sha256(cells_path),
        "features": _file_sha256(features_path),
    }
    raster_names = _matching_raster_names(
        labelset,
        receipt=receipt,
        final_cell_sha256=source_hashes["final_cells"],
    )
    cells = _read_csv(cells_path, "canonical final-cell")
    features = _read_csv(features_path, "sar_change_v2 feature")
    training, exclusion_counts = _derive_training_rows(
        cells,
        features,
        labelset=labelset,
        receipt=receipt,
    )
    timestamp = _utc_timestamp(created_at_utc)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent))
    )
    try:
        training_path = temporary / TRAINING_TABLE_FILENAME
        manifest_path = temporary / DERIVATION_MANIFEST_FILENAME
        training.to_csv(training_path, index=False, lineterminator="\n")
        training_sha256 = _file_sha256(training_path)
        manifest = _build_derivation_manifest(
            training,
            labelset=labelset,
            receipt=receipt,
            timestamp=timestamp,
            source_hashes=source_hashes,
            cells_path=cells_path,
            features_path=features_path,
            labelset_path=labelset_path,
            raster_names=raster_names,
            exclusion_counts=exclusion_counts,
            training_sha256=training_sha256,
        )
        manifest_path.write_text(_json_text(manifest), encoding="utf-8")
        # Recheck both source and generated bytes before publishing the directory.
        observed_sources = {
            "labelset_file": _file_sha256(labelset_path),
            "receipt_file": _file_sha256(receipt_path),
            "final_cells": _file_sha256(cells_path),
            "features": _file_sha256(features_path),
        }
        if observed_sources != source_hashes:
            raise TrainingJoinError("A source artifact changed during the training join.")
        _verify_derivation_manifest_payload(manifest)
        if output.exists():
            raise TrainingJoinError(
                f"Output directory appeared during the join and will not be overwritten: {output}"
            )
        temporary.rename(output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    return TrainingTablePaths(
        training_csv=output / TRAINING_TABLE_FILENAME,
        derivation_manifest=output / DERIVATION_MANIFEST_FILENAME,
    )


def verify_training_derivation(
    training_csv: str | Path,
    derivation_manifest_path: str | Path,
    release_validation_receipt_path: str | Path,
    labelset_manifest_path: str | Path,
) -> VerifiedTrainingDerivation:
    """Verify the exact training bytes and every authoritative upstream binding."""

    training_path = _existing_csv(training_csv, "query-model training")
    derivation_path = _existing_file(
        derivation_manifest_path, "training derivation manifest"
    )
    receipt_path = _existing_file(
        release_validation_receipt_path, "release validation receipt"
    )
    labelset_path = _existing_file(labelset_manifest_path, "labelset manifest")
    try:
        labelset = load_labelset_manifest(labelset_path)
    except LabelsetVersionError as exc:
        raise TrainingJoinError(f"Frozen labelset manifest is invalid: {exc}") from exc
    receipt = _load_verified_release_receipt(receipt_path, labelset=labelset)
    manifest = _load_json_object(derivation_path, "training derivation manifest")
    manifest_sha256 = _verify_derivation_manifest_payload(manifest)

    _require_equal(
        manifest.get("labelset_id"), labelset.labelset_id, "derivation labelset_id"
    )
    _require_equal(
        manifest.get("labelset_manifest_sha256"),
        labelset.manifest_sha256,
        "derivation labelset_manifest_sha256",
    )
    _require_equal(
        manifest.get("release_validation_receipt_sha256"),
        receipt.receipt_sha256,
        "derivation release_validation_receipt_sha256",
    )
    _require_equal(
        manifest.get("grid_contract_sha256"),
        receipt.grid_contract_sha256,
        "derivation grid_contract_sha256",
    )
    sources = _mapping(manifest.get("sources"), "derivation sources")
    expected_source_names = {
        "labelset_manifest",
        "release_validation_receipt",
        "canonical_final_cells",
        "sar_change_v2_features",
    }
    if set(sources) != expected_source_names:
        raise TrainingJoinError(
            "Derivation source set is incomplete or contains undeclared inputs."
        )
    _verify_source_contract(
        sources,
        "labelset_manifest",
        path=labelset_path,
        expected_logical_sha256=labelset.manifest_sha256,
    )
    _verify_source_contract(
        sources,
        "release_validation_receipt",
        path=receipt_path,
        expected_logical_sha256=receipt.receipt_sha256,
    )
    final_cells_source = _mapping(
        sources.get("canonical_final_cells"), "sources.canonical_final_cells"
    )
    final_cells_hash = _sha256(
        final_cells_source.get("file_sha256"),
        "sources.canonical_final_cells.file_sha256",
    )
    expected_raster_names = sorted(
        name
        for name, digest in receipt.raster_sha256_by_name
        if digest == final_cells_hash
    )
    declared_raster_names = final_cells_source.get("labelset_raster_names")
    if not expected_raster_names or declared_raster_names != expected_raster_names:
        raise TrainingJoinError(
            "Derivation final-cell hash/raster names do not match the validated release."
        )
    feature_source = _mapping(
        sources.get("sar_change_v2_features"), "sources.sar_change_v2_features"
    )
    _sha256(
        feature_source.get("file_sha256"),
        "sources.sar_change_v2_features.file_sha256",
    )

    output = _mapping(manifest.get("output"), "derivation output")
    expected_training_hash = _sha256(
        output.get("training_csv_sha256"), "output.training_csv_sha256"
    )
    observed_training_hash = _file_sha256(training_path)
    if observed_training_hash != expected_training_hash:
        raise TrainingJoinError(
            "Training CSV SHA-256 does not match the derivation manifest."
        )
    frame = _read_csv(training_path, "query-model training")
    _validate_derived_training_frame(
        frame,
        labelset=labelset,
        receipt=receipt,
    )
    if len(frame) != _nonnegative_integer(output.get("row_count"), "output.row_count"):
        raise TrainingJoinError("Training CSV row count differs from the derivation manifest.")
    query_ids = tuple(sorted(set(frame["query_region_id"].astype(str))))
    declared_query_ids = _identifier_list(
        output.get("query_region_ids"), "output.query_region_ids"
    )
    if query_ids != declared_query_ids:
        raise TrainingJoinError(
            "Training CSV query ids differ from the derivation manifest."
        )
    source_counts = {
        str(key): int(value)
        for key, value in frame["label_source_type"].value_counts().sort_index().items()
    }
    if source_counts != _count_mapping(
        output.get("label_source_counts"), "output.label_source_counts"
    ):
        raise TrainingJoinError(
            "Training CSV label-source counts differ from the derivation manifest."
        )
    class_counts = {
        str(key): int(value)
        for key, value in frame["binary_target"].astype(int).value_counts().sort_index().items()
    }
    if class_counts != _count_mapping(
        output.get("binary_target_counts"), "output.binary_target_counts"
    ):
        raise TrainingJoinError(
            "Training CSV target counts differ from the derivation manifest."
        )
    return VerifiedTrainingDerivation(
        labelset_id=labelset.labelset_id,
        labelset_manifest_sha256=labelset.manifest_sha256,
        release_validation_receipt_sha256=receipt.receipt_sha256,
        training_csv_sha256=observed_training_hash,
        derivation_manifest_sha256=manifest_sha256,
        grid_contract_sha256=receipt.grid_contract_sha256,
        query_region_ids=query_ids,
        row_count=len(frame),
    )


def _derive_training_rows(
    cells: pd.DataFrame,
    features: pd.DataFrame,
    *,
    labelset: LabelsetManifest,
    receipt: _VerifiedReleaseReceipt,
) -> tuple[pd.DataFrame, dict[str, int]]:
    _require_columns(cells, FINAL_CELL_COLUMNS, "canonical final-cell CSV")
    forged_cell_columns = sorted(DERIVED_SEMANTIC_COLUMNS.intersection(cells.columns))
    if forged_cell_columns:
        raise TrainingJoinError(
            "Canonical final-cell CSV contains caller-supplied derived semantics: "
            + ", ".join(forged_cell_columns)
            + "."
        )
    cell_frame = cells.copy()
    _validate_join_identifiers(cell_frame, "canonical final-cell CSV")
    _validate_cell_lineage_context(cell_frame, "canonical final-cell CSV")
    if cell_frame.duplicated(list(JOIN_KEYS)).any():
        raise TrainingJoinError("Canonical final-cell join keys must be unique.")
    if cell_frame["cell_id"].duplicated().any():
        raise TrainingJoinError("Canonical cell_id values must be globally unique.")
    _require_single_grid_and_queries(cell_frame, receipt=receipt, label="final cells")
    labels = _integer_series(cell_frame["label_code"], "label_code")
    allowed_codes = {int(label) for label in FloodLabel}
    invalid_codes = sorted(set(labels) - allowed_codes)
    if invalid_codes:
        raise TrainingJoinError(f"Canonical final cells contain unknown labels: {invalid_codes}.")
    cell_frame["label_code"] = labels
    cell_frame["label_source_type"] = _derive_label_sources(cell_frame)

    schema = get_feature_schema(FEATURE_SCHEMA_VERSION)
    feature_order = schema.required_feature_names
    _require_columns(
        features,
        (*FEATURE_METADATA_COLUMNS, *feature_order),
        "sar_change_v2 feature CSV",
    )
    forged_feature_columns = sorted(DERIVED_SEMANTIC_COLUMNS.intersection(features.columns))
    if forged_feature_columns:
        raise TrainingJoinError(
            "Feature CSV contains caller-supplied label or eligibility semantics: "
            + ", ".join(forged_feature_columns)
            + "."
        )
    feature_frame = features.copy()
    _validate_join_identifiers(feature_frame, "sar_change_v2 feature CSV")
    if feature_frame.duplicated(list(JOIN_KEYS)).any():
        raise TrainingJoinError("Feature CSV join keys must be unique.")
    if not feature_frame["feature_schema_version"].astype(str).eq(
        FEATURE_SCHEMA_VERSION
    ).all():
        raise TrainingJoinError(
            f"Every feature row must use feature_schema_version={FEATURE_SCHEMA_VERSION!r}."
        )
    roles = feature_frame["dataset_role"].astype(str)
    known_roles = {role.value for role in DatasetRole}
    unknown_roles = sorted(set(roles) - known_roles)
    if unknown_roles:
        raise TrainingJoinError(f"Feature CSV contains unknown dataset roles: {unknown_roles}.")
    forbidden_roles = sorted(set(roles) - {QUERY_POOL_ROLE})
    if forbidden_roles:
        raise TrainingJoinError(
            "Training join accepts only dataset_role="
            f"{QUERY_POOL_ROLE!r}; rejected calibration/development/test roles: "
            f"{forbidden_roles}."
        )
    feature_frame["spatial_group_id"] = _identifier_series(
        feature_frame["spatial_group_id"], "spatial_group_id"
    )
    _require_single_value_per_query(
        feature_frame, "spatial_group_id", "Feature CSV"
    )
    _require_single_value_per_query(feature_frame, "dataset_role", "Feature CSV")
    _validate_finite_features(feature_frame, feature_order)

    # A feature source may cover additional unreviewed pool cells.  Every
    # released cell, however, must have exactly one aligned feature row.
    selected_feature_columns = [
        *JOIN_KEYS,
        "spatial_group_id",
        "dataset_role",
        "feature_schema_version",
        *feature_order,
    ]
    if "sample_id" in feature_frame.columns:
        feature_frame["sample_id"] = _identifier_series(
            feature_frame["sample_id"], "sample_id"
        )
        selected_feature_columns.append("sample_id")
    joined = cell_frame.merge(
        feature_frame.loc[:, selected_feature_columns],
        on=list(JOIN_KEYS),
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    missing = joined.loc[joined["_merge"] != "both", ["query_region_id", "cell_id"]]
    if not missing.empty:
        preview = ", ".join(
            f"{row.query_region_id}/{row.cell_id}"
            for row in missing.head(5).itertuples(index=False)
        )
        raise TrainingJoinError(
            "Released cells are missing exact query/cell/grid feature matches: " + preview
        )
    joined = joined.drop(columns="_merge")
    if "sample_id" in joined.columns:
        mismatched_sample = joined["sample_id"].astype(str) != joined["cell_id"].astype(str)
        if mismatched_sample.any():
            raise TrainingJoinError(
                "Feature sample_id must equal the canonical cell_id; sample identity "
                "cannot be caller-remapped."
            )
    joined["sample_id"] = joined["cell_id"].astype(str)

    excluded_codes = (3, 4, 255)
    exclusion_counts = {
        str(code): int((joined["label_code"] == code).sum()) for code in excluded_codes
    }
    included = joined.loc[joined["label_code"].isin((0, 1, 2))].copy()
    if included.empty:
        raise TrainingJoinError("No reviewed codes 0/1/2 remain for binary training.")
    included["binary_target"] = included["label_code"].map({0: 0, 1: 1, 2: 0})
    if set(included["binary_target"].astype(int)) != {0, 1}:
        raise TrainingJoinError(
            "Derived training cells must contain both temporary-flood and reviewed-negative targets."
        )
    included["eligible_for_query_model_training"] = True
    included["labelset_version"] = labelset.labelset_id
    included["labelset_manifest_sha256"] = labelset.manifest_sha256
    included["release_validation_receipt_sha256"] = receipt.receipt_sha256
    included["query_model_only"] = True
    included["eligible_for_decision_layer"] = False
    included["eligible_for_fpps"] = False
    included["eligible_for_warning"] = False

    ordered_columns = [
        "sample_id",
        "query_region_id",
        "cell_id",
        "grid_contract_sha256",
        "event_id",
        "tile_id",
        "source_registry_sha256",
        "row_index",
        "column_index",
        "spatial_group_id",
        "dataset_role",
        "label_code",
        "binary_target",
        "label_source_type",
        "source_annotation_id",
        "source_adjudication_id",
        "eligible_for_query_model_training",
        "labelset_version",
        "labelset_manifest_sha256",
        "release_validation_receipt_sha256",
        "feature_schema_version",
        *feature_order,
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    ]
    result = included.loc[:, ordered_columns].sort_values(
        ["query_region_id", "cell_id"], kind="stable"
    ).reset_index(drop=True)
    _validate_derived_training_frame(result, labelset=labelset, receipt=receipt)
    return result, exclusion_counts


def _validate_derived_training_frame(
    frame: pd.DataFrame,
    *,
    labelset: LabelsetManifest,
    receipt: _VerifiedReleaseReceipt,
) -> None:
    schema = get_feature_schema(FEATURE_SCHEMA_VERSION)
    feature_order = schema.required_feature_names
    required = (
        "sample_id",
        *FINAL_CELL_COLUMNS,
        "spatial_group_id",
        "dataset_role",
        "binary_target",
        "label_source_type",
        "eligible_for_query_model_training",
        "labelset_version",
        "labelset_manifest_sha256",
        "release_validation_receipt_sha256",
        "feature_schema_version",
        *feature_order,
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    )
    _require_columns(frame, required, "derived training CSV")
    if frame.empty:
        raise TrainingJoinError("Derived training CSV must not be empty.")
    _validate_join_identifiers(frame, "derived training CSV")
    _validate_cell_lineage_context(frame, "derived training CSV")
    frame_ids = _identifier_series(frame["sample_id"], "sample_id")
    if len(set(frame_ids)) != len(frame_ids):
        raise TrainingJoinError("Derived training sample_id values must be unique.")
    if frame_ids != frame["cell_id"].astype(str).tolist():
        raise TrainingJoinError("Derived sample_id must equal canonical cell_id.")
    if frame.duplicated(list(JOIN_KEYS)).any():
        raise TrainingJoinError("Derived training join keys must be unique.")
    _require_single_grid_and_queries(
        frame,
        receipt=receipt,
        label="derived training",
        exact_queries=False,
    )
    labels = _integer_series(frame["label_code"], "label_code")
    if not set(labels).issubset({0, 1, 2}):
        raise TrainingJoinError("Derived training CSV contains excluded label codes.")
    targets = _integer_series(frame["binary_target"], "binary_target")
    expected_targets = [{0: 0, 1: 1, 2: 0}[label] for label in labels]
    if targets != expected_targets:
        raise TrainingJoinError("binary_target does not match the fixed 0/1/2 mapping.")
    derived_sources = _derive_label_sources(frame)
    if frame["label_source_type"].astype(str).tolist() != derived_sources:
        raise TrainingJoinError(
            "label_source_type does not match annotation/adjudication lineage."
        )
    annotation_ids = {
        str(value).strip()
        for value in frame["source_annotation_id"]
        if str(value).strip()
    }
    unknown_annotations = sorted(annotation_ids - set(labelset.source_annotation_ids))
    if unknown_annotations:
        raise TrainingJoinError(
            "Derived training references annotations absent from the frozen labelset: "
            f"{unknown_annotations}."
        )
    _require_literal_column(frame, "eligible_for_query_model_training", True)
    _require_literal_column(frame, "query_model_only", True)
    _require_literal_column(frame, "eligible_for_decision_layer", False)
    _require_literal_column(frame, "eligible_for_fpps", False)
    _require_literal_column(frame, "eligible_for_warning", False)
    _require_constant(frame, "dataset_role", QUERY_POOL_ROLE)
    _require_constant(frame, "feature_schema_version", FEATURE_SCHEMA_VERSION)
    _require_constant(frame, "labelset_version", labelset.labelset_id)
    _require_constant(
        frame, "labelset_manifest_sha256", labelset.manifest_sha256
    )
    _require_constant(
        frame,
        "release_validation_receipt_sha256",
        receipt.receipt_sha256,
    )
    _require_single_value_per_query(frame, "spatial_group_id", "Derived training CSV")
    _require_single_value_per_query(frame, "dataset_role", "Derived training CSV")
    _validate_finite_features(frame, feature_order)


def _build_derivation_manifest(
    training: pd.DataFrame,
    *,
    labelset: LabelsetManifest,
    receipt: _VerifiedReleaseReceipt,
    timestamp: str,
    source_hashes: Mapping[str, str],
    cells_path: Path,
    features_path: Path,
    labelset_path: Path,
    raster_names: Sequence[str],
    exclusion_counts: Mapping[str, int],
    training_sha256: str,
) -> dict[str, Any]:
    source_counts = {
        str(key): int(value)
        for key, value in training["label_source_type"].value_counts().sort_index().items()
    }
    target_counts = {
        str(key): int(value)
        for key, value in training["binary_target"].astype(int).value_counts().sort_index().items()
    }
    unsigned: dict[str, Any] = {
        "artifact_schema": TRAINING_DERIVATION_SCHEMA,
        "created_at_utc": timestamp,
        "labelset_id": labelset.labelset_id,
        "labelset_manifest_sha256": labelset.manifest_sha256,
        "release_validation_receipt_sha256": receipt.receipt_sha256,
        "grid_contract_sha256": receipt.grid_contract_sha256,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_order": list(get_feature_schema(FEATURE_SCHEMA_VERSION).required_feature_names),
        "join_keys": list(JOIN_KEYS),
        "target_mapping": {"0": 0, "1": 1, "2": 0},
        "excluded_label_codes": {str(key): int(value) for key, value in exclusion_counts.items()},
        "sources": {
            "labelset_manifest": {
                "file": labelset_path.name,
                "file_sha256": source_hashes["labelset_file"],
                "logical_sha256": labelset.manifest_sha256,
            },
            "release_validation_receipt": {
                "file": receipt.path.name,
                "file_sha256": source_hashes["receipt_file"],
                "logical_sha256": receipt.receipt_sha256,
            },
            "canonical_final_cells": {
                "file": cells_path.name,
                "file_sha256": source_hashes["final_cells"],
                "labelset_raster_names": list(raster_names),
            },
            "sar_change_v2_features": {
                "file": features_path.name,
                "file_sha256": source_hashes["features"],
            },
        },
        "output": {
            "file": TRAINING_TABLE_FILENAME,
            "training_csv_sha256": training_sha256,
            "row_count": len(training),
            "query_region_ids": sorted(set(training["query_region_id"].astype(str))),
            "binary_target_counts": target_counts,
            "label_source_counts": source_counts,
        },
        "safety": {
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "allowed_output_use": "query_committee_training_only",
        },
        "warning": (
            "This table trains review-priority query models only. It is not flood "
            "truth for FPPS, decisions, action classes, or warnings."
        ),
    }
    return {**unsigned, "manifest_sha256": _canonical_sha256(unsigned)}


def _load_verified_release_receipt(
    path: Path,
    *,
    labelset: LabelsetManifest,
) -> _VerifiedReleaseReceipt:
    """Narrow adapter for the code-generated release-validation receipt.

    The receipt producer is owned by ``review_workflow``.  This adapter avoids
    importing that orchestration module (and its optional geospatial runtime)
    while enforcing the serialized hand-off contract.
    """

    try:
        loaded_receipt = load_labelset_validation_receipt(path)
    except ReviewWorkflowError as exc:
        raise TrainingJoinError(
            f"Release validation receipt is invalid: {exc}"
        ) from exc
    payload = loaded_receipt.to_dict()
    if payload.get("artifact_schema") != RELEASE_VALIDATION_RECEIPT_SCHEMA:
        raise TrainingJoinError(
            "Release validation receipt must use artifact_schema="
            f"{RELEASE_VALIDATION_RECEIPT_SCHEMA!r}."
        )
    declared_hash = _sha256(
        payload.get("receipt_sha256"), "release receipt receipt_sha256"
    )
    unsigned = dict(payload)
    unsigned.pop("receipt_sha256", None)
    observed_hash = _canonical_sha256(unsigned)
    if declared_hash != observed_hash:
        raise TrainingJoinError(
            "Release validation receipt SHA-256 does not match canonical content."
        )
    _require_equal(payload.get("labelset_id"), labelset.labelset_id, "receipt labelset_id")
    _require_equal(
        payload.get("labelset_manifest_sha256"),
        labelset.manifest_sha256,
        "receipt labelset_manifest_sha256",
    )
    if payload.get("qa_ready") is not True:
        raise TrainingJoinError("Release validation receipt is not a passing QA release.")
    if _nonnegative_integer(
        payload.get("open_adjudication_count"), "open_adjudication_count"
    ) != 0:
        raise TrainingJoinError("Release validation receipt has open adjudications.")
    expected_safety = {
        "eligible_for_query_model_training": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for field, expected in expected_safety.items():
        if payload.get(field) is not expected:
            raise TrainingJoinError(
                f"Release receipt safety field {field} must be literal {expected}."
            )
    grid_hash = _sha256(
        payload.get("grid_contract_sha256"), "receipt grid_contract_sha256"
    )
    query_ids = _identifier_list(
        payload.get("query_region_ids"), "receipt query_region_ids"
    )
    if not query_ids:
        raise TrainingJoinError("Release validation receipt has no query ids.")
    rasters_raw = _mapping(
        payload.get("raster_sha256_by_name"), "receipt raster_sha256_by_name"
    )
    rasters = tuple(
        sorted((str(name), _sha256(value, f"receipt raster {name}")) for name, value in rasters_raw.items())
    )
    if rasters != tuple(sorted(labelset.raster_sha256_by_name)):
        raise TrainingJoinError(
            "Release receipt raster set does not exactly match the frozen labelset."
        )
    return _VerifiedReleaseReceipt(
        payload=payload,
        path=path,
        file_sha256=_file_sha256(path),
        receipt_sha256=declared_hash,
        grid_contract_sha256=grid_hash,
        query_region_ids=query_ids,
        raster_sha256_by_name=rasters,
    )


def _matching_raster_names(
    labelset: LabelsetManifest,
    *,
    receipt: _VerifiedReleaseReceipt,
    final_cell_sha256: str,
) -> tuple[str, ...]:
    labelset_names = {
        name for name, digest in labelset.raster_sha256_by_name if digest == final_cell_sha256
    }
    receipt_names = {
        name for name, digest in receipt.raster_sha256_by_name if digest == final_cell_sha256
    }
    names = tuple(sorted(labelset_names.intersection(receipt_names)))
    if not names:
        raise TrainingJoinError(
            "Canonical final-cell CSV hash is absent from the frozen labelset/receipt raster set."
        )
    return names


def _verify_derivation_manifest_payload(payload: Mapping[str, Any]) -> str:
    if payload.get("artifact_schema") != TRAINING_DERIVATION_SCHEMA:
        raise TrainingJoinError(
            f"Derivation manifest must use artifact_schema={TRAINING_DERIVATION_SCHEMA!r}."
        )
    declared = _sha256(payload.get("manifest_sha256"), "derivation manifest_sha256")
    unsigned = dict(payload)
    unsigned.pop("manifest_sha256", None)
    observed = _canonical_sha256(unsigned)
    if declared != observed:
        raise TrainingJoinError(
            "Training derivation manifest SHA-256 does not match canonical content."
        )
    if payload.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise TrainingJoinError("Training derivation is not sar_change_v2.")
    expected_order = list(get_feature_schema(FEATURE_SCHEMA_VERSION).required_feature_names)
    if payload.get("feature_order") != expected_order:
        raise TrainingJoinError("Training derivation feature order is not canonical.")
    if payload.get("join_keys") != list(JOIN_KEYS):
        raise TrainingJoinError("Training derivation join keys are not canonical.")
    if payload.get("target_mapping") != {"0": 0, "1": 1, "2": 0}:
        raise TrainingJoinError("Training derivation target mapping was changed.")
    exclusions = _count_mapping(
        payload.get("excluded_label_codes"), "excluded_label_codes"
    )
    if set(exclusions) != {"3", "4", "255"}:
        raise TrainingJoinError(
            "Training derivation must report explicit exclusions for codes 3, 4, and 255."
        )
    safety = _mapping(payload.get("safety"), "derivation safety")
    expected_safety = {
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for field, expected in expected_safety.items():
        if safety.get(field) is not expected:
            raise TrainingJoinError(
                f"Derivation safety field {field} must be literal {expected}."
            )
    return declared


def _verify_source_contract(
    sources: Mapping[str, Any],
    name: str,
    *,
    path: Path,
    expected_logical_sha256: str,
) -> None:
    contract = _mapping(sources.get(name), f"sources.{name}")
    expected_file_hash = _sha256(
        contract.get("file_sha256"), f"sources.{name}.file_sha256"
    )
    if _file_sha256(path) != expected_file_hash:
        raise TrainingJoinError(f"{name} file SHA-256 differs from the derivation.")
    _require_equal(
        contract.get("logical_sha256"),
        expected_logical_sha256,
        f"sources.{name}.logical_sha256",
    )


def _derive_label_sources(frame: pd.DataFrame) -> list[str]:
    annotation_ids = frame["source_annotation_id"].fillna("").astype(str).str.strip()
    adjudication_ids = frame["source_adjudication_id"].fillna("").astype(str).str.strip()
    exactly_one = annotation_ids.ne("") ^ adjudication_ids.ne("")
    if not exactly_one.all():
        raise TrainingJoinError(
            "Every final cell must reference exactly one annotation or adjudication lineage id."
        )
    for label, values in (
        ("source_annotation_id", annotation_ids[annotation_ids.ne("")]),
        ("source_adjudication_id", adjudication_ids[adjudication_ids.ne("")]),
    ):
        _identifier_series(values, label)
    return [
        "human_adjudicated" if adjudication_id else "human_reviewed"
        for adjudication_id in adjudication_ids
    ]


def _require_single_grid_and_queries(
    frame: pd.DataFrame,
    *,
    receipt: _VerifiedReleaseReceipt,
    label: str,
    exact_queries: bool = True,
) -> None:
    grids = set(frame["grid_contract_sha256"].astype(str))
    if grids != {receipt.grid_contract_sha256}:
        raise TrainingJoinError(
            f"{label} grid hash does not match the validated release receipt."
        )
    queries = tuple(sorted(set(frame["query_region_id"].astype(str))))
    receipt_queries = set(receipt.query_region_ids)
    query_set = set(queries)
    invalid = queries != receipt.query_region_ids if exact_queries else not query_set.issubset(receipt_queries)
    if invalid:
        raise TrainingJoinError(
            f"{label} query ids do not satisfy the validated release receipt."
        )


def _require_single_value_per_query(
    frame: pd.DataFrame, column: str, label: str
) -> None:
    counts = frame.groupby("query_region_id", sort=False)[column].nunique(dropna=False)
    bad = sorted(str(value) for value in counts[counts != 1].index)
    if bad:
        raise TrainingJoinError(
            f"{label} assigns multiple {column} values within queries: {bad}."
        )


def _validate_join_identifiers(frame: pd.DataFrame, label: str) -> None:
    for column in ("query_region_id", "cell_id"):
        frame[column] = _identifier_series(frame[column], column)
    hashes = frame["grid_contract_sha256"].astype(str).str.strip().str.lower()
    if not hashes.map(lambda value: bool(_SHA256_PATTERN.fullmatch(value))).all():
        raise TrainingJoinError(f"{label} grid_contract_sha256 values are invalid.")
    frame["grid_contract_sha256"] = hashes


def _validate_cell_lineage_context(frame: pd.DataFrame, label: str) -> None:
    for column in ("event_id", "tile_id"):
        frame[column] = _identifier_series(frame[column], column)
        _require_single_value_per_query(frame, column, label)
    registries = (
        frame["source_registry_sha256"].astype(str).str.strip().str.lower()
    )
    if not registries.map(
        lambda value: bool(_SHA256_PATTERN.fullmatch(value))
    ).all():
        raise TrainingJoinError(
            f"{label} source_registry_sha256 values are invalid."
        )
    frame["source_registry_sha256"] = registries
    _require_single_value_per_query(frame, "source_registry_sha256", label)


def _validate_finite_features(frame: pd.DataFrame, columns: Sequence[str]) -> None:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or not values.map(lambda value: math.isfinite(float(value))).all():
            raise TrainingJoinError(f"Feature column {column} must contain finite numbers.")
        frame[column] = values.astype(float)


def _require_literal_column(
    frame: pd.DataFrame, column: str, expected: bool
) -> None:
    expected_text = "True" if expected else "False"
    if not all(
        (isinstance(value, bool) and value is expected)
        or (isinstance(value, str) and value == expected_text)
        for value in frame[column]
    ):
        raise TrainingJoinError(
            f"Derived training safety field {column} must be literal {expected}."
        )


def _require_constant(frame: pd.DataFrame, column: str, expected: str) -> None:
    if not frame[column].map(lambda value: isinstance(value, str) and value == expected).all():
        raise TrainingJoinError(f"Derived training {column} does not match {expected!r}.")


def _require_columns(frame: pd.DataFrame, required: Sequence[str], label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise TrainingJoinError(f"{label} is missing required columns: {', '.join(missing)}.")


def _identifier_series(series: pd.Series, label: str) -> list[str]:
    result: list[str] = []
    for value in series:
        if not isinstance(value, str):
            value = str(value)
        normalized = value.strip()
        if not _IDENTIFIER_PATTERN.fullmatch(normalized):
            raise TrainingJoinError(f"{label} contains an invalid stable identifier: {value!r}.")
        result.append(normalized)
    return result


def _identifier_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise TrainingJoinError(f"{label} must be a non-empty JSON array.")
    normalized = tuple(_identifier_series(pd.Series(value, dtype=object), label))
    if len(normalized) != len(set(normalized)) or normalized != tuple(sorted(normalized)):
        raise TrainingJoinError(f"{label} must be unique and sorted.")
    return normalized


def _integer_series(series: pd.Series, label: str) -> list[int]:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any() or (numeric % 1 != 0).any():
        raise TrainingJoinError(f"{label} must contain integer codes.")
    return numeric.astype(int).tolist()


def _count_mapping(value: Any, label: str) -> dict[str, int]:
    raw = _mapping(value, label)
    result: dict[str, int] = {}
    for key, count in raw.items():
        result[str(key)] = _nonnegative_integer(count, f"{label}.{key}")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TrainingJoinError(f"{label} must be a JSON object.")
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TrainingJoinError(f"{label} must be a non-negative integer.")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value.lower()):
        raise TrainingJoinError(f"{label} must be a complete lowercase SHA-256.")
    return value.lower()


def _require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise TrainingJoinError(f"{label} does not match the authoritative release.")


def _existing_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise TrainingJoinError(f"{label} does not exist: {path}")
    return path


def _existing_csv(value: str | Path, label: str) -> Path:
    path = _existing_file(value, label)
    if path.suffix.lower() != ".csv":
        raise TrainingJoinError(f"{label} must be a CSV file: {path}")
    return path


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, dtype=object, keep_default_na=False)
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise TrainingJoinError(f"Could not read {label}: {exc}") from exc
    if frame.empty:
        raise TrainingJoinError(f"{label} must not be empty.")
    return frame


def _load_json_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TrainingJoinError(f"Could not load {label}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise TrainingJoinError(f"{label} root must be a JSON object.")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise TrainingJoinError(f"Could not hash {path}: {exc}") from exc
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TrainingJoinError(f"Artifact is not canonical JSON: {exc}") from exc
    return hashlib.sha256(encoded).hexdigest()


def _json_text(value: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def _utc_timestamp(value: datetime | str | None) -> str:
    if value is None:
        parsed = datetime.now(UTC)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TrainingJoinError("created_at_utc is not a valid timestamp.") from exc
    else:
        raise TrainingJoinError("created_at_utc must be a datetime or ISO timestamp.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrainingJoinError("created_at_utc must be timezone-aware.")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
