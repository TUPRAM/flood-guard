"""Fail-closed, reviewer-safe orientation over the real Mae Sai SAR pool.

This module deliberately stops before supervised learning.  It validates the
governed ``sar_change_v2`` cell pool in chunks, reduces it to bounded aggregate
tables, and demonstrates PCA/k-means on query-level summaries.  Clusters are
descriptive patterns in backscatter and context; they are never flood classes,
labels, probabilities, priorities, or operational evidence.

The public artifact contains no query, tile, bounding-box, weak-reference,
model-score, queue, priority, or label fields.  Source identities are used only
in memory to prove grain and joins, then discarded before writing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from floodguard.label_factory.feature_schema import get_feature_schema


ARTIFACT_SCHEMA = "floodguard.reviewer_a_safe_real_data_orientation.v1"
EXPOSURE_LANE = "reviewer_a_safe"
TRAINING_GATE_STATUS = "blocked_missing_released_training_labels"
FEATURE_SCHEMA_VERSION = "sar_change_v2"

SUMMARY_FILENAME = "summary.json"
FEATURE_QUANTILES_FILENAME = "feature_quantiles.csv"
CHANGE_HISTOGRAMS_FILENAME = "change_histograms.csv"
CONTEXT_SUMMARY_FILENAME = "context_summary.csv"
PCA_SUMMARY_FILENAME = "pca_summary.csv"
CLUSTER_SENSITIVITY_FILENAME = "cluster_sensitivity.csv"
CLUSTER_SUMMARY_FILENAME = "cluster_summary.csv"

OUTPUT_FILENAMES: tuple[str, ...] = (
    FEATURE_QUANTILES_FILENAME,
    CHANGE_HISTOGRAMS_FILENAME,
    CONTEXT_SUMMARY_FILENAME,
    PCA_SUMMARY_FILENAME,
    CLUSTER_SENSITIVITY_FILENAME,
    CLUSTER_SUMMARY_FILENAME,
)

MODEL_FEATURES: tuple[str, ...] = tuple(
    get_feature_schema(FEATURE_SCHEMA_VERSION).required_feature_names
)
ML_SOURCE_FEATURES: tuple[str, ...] = tuple(
    feature for feature in MODEL_FEATURES if feature != "valid_data_fraction"
)
QUERY_AGGREGATE_FEATURES: tuple[str, ...] = tuple(
    [f"mean_{feature}" for feature in ML_SOURCE_FEATURES]
    + [f"std_{feature}" for feature in ML_SOURCE_FEATURES]
)
CONTEXT_NUMERIC_COLUMNS: tuple[str, ...] = (
    "permanent_water_fraction",
    "worldcover_water_fraction",
    "urban_fraction",
    "forest_fraction",
    "cropland_fraction",
    "steep_terrain_fraction",
    "slope_p90_degrees",
)
REQUIRED_FEATURE_COLUMNS: tuple[str, ...] = (
    "sample_id",
    "query_region_id",
    "cell_id",
    "grid_contract_sha256",
    "event_id",
    "tile_id",
    "source_registry_sha256",
    "processing_alignment_receipt_sha256",
    "row_index",
    "column_index",
    "spatial_group_id",
    "dataset_role",
    "feature_schema_version",
    *MODEL_FEATURES,
)
REQUIRED_QUERY_COLUMNS: tuple[str, ...] = (
    "query_region_id",
    "tile_id",
    "event_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "processing_alignment_receipt_sha256",
    "query_size_pixels",
    "dataset_role",
    "overlap_group_id",
    "feature_schema_version",
    "review_status",
    "selected",
    "query_model_only",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)
REQUIRED_CONTEXT_COLUMNS: tuple[str, ...] = (
    "query_region_id",
    "event_id",
    "grid_contract_sha256",
    "query_size_pixels",
    "dataset_role",
    "overlap_group_id",
    "feature_schema_version",
    "valid_data_fraction",
    *CONTEXT_NUMERIC_COLUMNS,
    "round0_stratum",
    "query_model_only",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_FORBIDDEN_OUTPUT_COLUMNS = {
    "query_region_id",
    "tile_id",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
    "weak_overlap",
    "weak_positive_fraction",
    "model_score",
    "committee_score",
    "queue",
    "priority",
    "label",
    "target",
}


class RealDataOrientationError(ValueError):
    """Raised when governed input or output evidence cannot be trusted."""


@dataclass(frozen=True, slots=True)
class RealDataOrientationPaths:
    """Paths written by one immutable reviewer-safe orientation build."""

    directory: Path
    summary: Path
    feature_quantiles: Path
    change_histograms: Path
    context_summary: Path
    pca_summary: Path
    cluster_sensitivity: Path
    cluster_summary: Path


def build_real_data_orientation(
    *,
    feature_csv: str | Path,
    derivation_manifest_path: str | Path,
    canonical_query_csv: str | Path,
    context_evidence_csv: str | Path,
    grid_validation_receipt_path: str | Path,
    release_seal_path: str | Path,
    output_directory: str | Path,
    expected_cell_count: int = 874_496,
    expected_query_count: int = 854,
    expected_cells_per_query: int = 1_024,
    expected_spatial_group_count: int = 20,
    chunk_size: int = 100_000,
    random_seed: int = 20_260_713,
    created_at_utc: str | datetime | None = None,
) -> RealDataOrientationPaths:
    """Validate real inputs and write aggregate reviewer-safe learning outputs.

    The large cell table is parsed and validated in chunks.  Only numeric
    feature arrays and query-level running moments are retained; source IDs are
    never written.  The output directory must be new or empty and is published
    by one final rename after all checks and hashes pass.
    """

    feature_path = _required_file(feature_csv, "sar_change_v2 feature CSV")
    derivation_path = _required_file(
        derivation_manifest_path, "sar_change_v2 derivation manifest"
    )
    query_path = _required_file(canonical_query_csv, "canonical query CSV")
    context_path = _required_file(context_evidence_csv, "context evidence CSV")
    receipt_path = _required_file(
        grid_validation_receipt_path, "grid validation receipt"
    )
    seal_path = _required_file(release_seal_path, "canonical release seal")
    output = Path(output_directory)
    _validate_output_target(output)
    _positive_int(expected_cell_count, "expected_cell_count")
    _positive_int(expected_query_count, "expected_query_count")
    _positive_int(expected_cells_per_query, "expected_cells_per_query")
    _positive_int(expected_spatial_group_count, "expected_spatial_group_count")
    _positive_int(chunk_size, "chunk_size")
    if expected_cells_per_query != 32 * 32:
        raise RealDataOrientationError(
            "reviewer_a_safe orientation requires the approved 32 x 32 query grain."
        )
    if expected_cell_count != expected_query_count * expected_cells_per_query:
        raise RealDataOrientationError(
            "Expected cell count must equal query count times cells per query."
        )
    timestamp = _normalise_timestamp(created_at_utc)

    input_hashes = {
        "feature_csv": _file_sha256(feature_path),
        "derivation_manifest": _file_sha256(derivation_path),
        "canonical_query_csv": _file_sha256(query_path),
        "context_evidence_csv": _file_sha256(context_path),
        "grid_validation_receipt": _file_sha256(receipt_path),
        "release_seal": _file_sha256(seal_path),
    }

    derivation = _load_json(derivation_path, "sar_change_v2 derivation manifest")
    derivation_logical_hash = _verify_feature_derivation(
        derivation,
        feature_hash=input_hashes["feature_csv"],
        query_hash=input_hashes["canonical_query_csv"],
        expected_cell_count=expected_cell_count,
        expected_query_count=expected_query_count,
    )
    queries = _load_queries(
        query_path,
        expected_query_count=expected_query_count,
        expected_spatial_group_count=expected_spatial_group_count,
    )
    query_meta = _query_metadata(queries)
    grid_hash = _one_value(queries["grid_contract_sha256"], "grid contract")
    event_id = _one_value(queries["event_id"], "event ID")
    processing_hash = _one_value(
        queries["processing_alignment_receipt_sha256"],
        "processing alignment receipt hash",
    )
    source_registry_hash = _one_value(
        queries["source_registry_sha256"], "source registry hash"
    )

    receipt = _load_json(receipt_path, "grid validation receipt")
    receipt_logical_hash = _verify_grid_receipt(
        receipt,
        file_hash=input_hashes["grid_validation_receipt"],
        grid_hash=grid_hash,
        processing_hash=processing_hash,
        source_registry_hash=source_registry_hash,
        expected_query_count=expected_query_count,
        expected_spatial_group_count=expected_spatial_group_count,
    )
    seal = _load_json(seal_path, "canonical release seal")
    seal_logical_hash, release_manifest_hash = _verify_release_seal(
        seal,
        seal_path=seal_path,
        receipt_file_hash=input_hashes["grid_validation_receipt"],
        receipt_logical_hash=receipt_logical_hash,
        processing_hash=processing_hash,
        query_path=query_path,
        expected_query_count=expected_query_count,
        expected_spatial_group_count=expected_spatial_group_count,
    )
    input_hashes["release_manifest"] = release_manifest_hash

    context, context_manifest_logical_hash = _load_and_verify_context(
        context_path,
        queries=queries,
        expected_query_count=expected_query_count,
    )
    input_hashes["context_derivation_manifest"] = _file_sha256(
        context_path.parent / "supported_query_derivation.json"
    )

    numeric_values, query_aggregates, validation = _read_validate_feature_chunks(
        feature_path,
        query_meta=query_meta,
        expected_cell_count=expected_cell_count,
        expected_query_count=expected_query_count,
        expected_cells_per_query=expected_cells_per_query,
        chunk_size=chunk_size,
    )

    feature_quantiles = _build_feature_quantiles(numeric_values)
    histograms = _build_change_histograms(numeric_values)
    context_summary = _build_context_summary(context)
    pca_summary, cluster_sensitivity, cluster_summary = _build_unsupervised_tables(
        query_aggregates,
        random_seed=random_seed,
    )
    tables = {
        FEATURE_QUANTILES_FILENAME: feature_quantiles,
        CHANGE_HISTOGRAMS_FILENAME: histograms,
        CONTEXT_SUMMARY_FILENAME: context_summary,
        PCA_SUMMARY_FILENAME: pca_summary,
        CLUSTER_SENSITIVITY_FILENAME: cluster_sensitivity,
        CLUSTER_SUMMARY_FILENAME: cluster_summary,
    }
    for name, frame in tables.items():
        _validate_safe_output_frame(frame, name)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        artifacts: dict[str, dict[str, object]] = {}
        for name in OUTPUT_FILENAMES:
            path = temporary / name
            tables[name].to_csv(path, index=False, lineterminator="\n")
            artifacts[name] = {
                "sha256": _file_sha256(path),
                "row_count": len(tables[name]),
                "columns": list(tables[name].columns),
            }
        summary: dict[str, object] = {
            "artifact_schema": ARTIFACT_SCHEMA,
            "created_at_utc": timestamp,
            "exposure_lane": EXPOSURE_LANE,
            "analysis_kind": "aggregate_unlabelled_sar_orientation",
            "training_gate_status": TRAINING_GATE_STATUS,
            "unsupervised_learning": {
                "method": "standardized query aggregates -> PCA and k-means",
                "k_values": [3, 4, 5, 6],
                "random_seed": int(random_seed),
                "interpretation": (
                    "Clusters are descriptive backscatter patterns, not flood "
                    "classes, truth, probabilities, or review priorities."
                ),
            },
            "counts": {
                "cell_count": expected_cell_count,
                "query_count": expected_query_count,
                "cells_per_query": expected_cells_per_query,
                "spatial_group_count": expected_spatial_group_count,
            },
            "validation": {
                **validation,
                "feature_derivation_logical_sha256": derivation_logical_hash,
                "context_derivation_logical_sha256": context_manifest_logical_hash,
                "grid_receipt_logical_sha256": receipt_logical_hash,
                "release_seal_logical_sha256": seal_logical_hash,
                "formula_tolerance": 1e-9,
                "one_to_one_context_join": True,
                "all_source_safety_checks_passed": True,
            },
            "lineage": {
                key: {"file": _safe_source_name(key), "sha256": value}
                for key, value in sorted(input_hashes.items())
            },
            "artifacts": artifacts,
            "safety": {
                "report_only": True,
                "formal_review_authorized": False,
                "eligible_for_query_model_training": False,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "contains_row_level_records": False,
                "contains_location_identifiers": False,
                "contains_weak_reference_evidence": False,
                "contains_model_outputs": False,
                "contains_review_queue": False,
                "contains_released_training_labels": False,
            },
            "event_scope": {
                "event_count": 1,
                "event_reference": hashlib.sha256(event_id.encode("utf-8")).hexdigest()[
                    :12
                ],
                "grid_contract_sha256": grid_hash,
            },
        }
        summary["summary_sha256"] = _canonical_sha256(summary)
        _write_json(temporary / SUMMARY_FILENAME, summary)
        verify_real_data_orientation_artifact(temporary)

        if output.exists():
            if any(output.iterdir()):
                raise RealDataOrientationError(
                    f"Output directory became non-empty and will not be overwritten: {output}"
                )
            output.rmdir()
        temporary.rename(output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    return _paths(output)


def verify_real_data_orientation_artifact(
    output_directory: str | Path,
) -> Mapping[str, object]:
    """Verify self-hash, immutable table hashes, schemas, and safety fields."""

    directory = Path(output_directory)
    summary_path = _required_file(directory / SUMMARY_FILENAME, "orientation summary")
    summary = _load_json(summary_path, "orientation summary")
    if summary.get("artifact_schema") != ARTIFACT_SCHEMA:
        raise RealDataOrientationError("Unknown real-data orientation schema.")
    declared = _sha256(summary.get("summary_sha256"), "summary_sha256")
    unsigned = dict(summary)
    unsigned.pop("summary_sha256", None)
    if _canonical_sha256(unsigned) != declared:
        raise RealDataOrientationError("Orientation summary self-hash mismatch.")
    if summary.get("exposure_lane") != EXPOSURE_LANE:
        raise RealDataOrientationError(
            "Orientation exposure lane is not reviewer_a_safe."
        )
    if summary.get("training_gate_status") != TRAINING_GATE_STATUS:
        raise RealDataOrientationError("Orientation training gate is not blocked.")
    safety = summary.get("safety")
    required_safety = {
        "report_only": True,
        "formal_review_authorized": False,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "contains_row_level_records": False,
        "contains_location_identifiers": False,
        "contains_weak_reference_evidence": False,
        "contains_model_outputs": False,
        "contains_review_queue": False,
        "contains_released_training_labels": False,
    }
    if not isinstance(safety, Mapping) or any(
        safety.get(key) is not value for key, value in required_safety.items()
    ):
        raise RealDataOrientationError("Orientation safety contract is invalid.")
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(OUTPUT_FILENAMES):
        raise RealDataOrientationError("Orientation artifact inventory is incomplete.")
    for name in OUTPUT_FILENAMES:
        evidence = artifacts.get(name)
        if not isinstance(evidence, Mapping):
            raise RealDataOrientationError(f"Missing artifact evidence for {name}.")
        path = _required_file(directory / name, f"orientation artifact {name}")
        if _file_sha256(path) != evidence.get("sha256"):
            raise RealDataOrientationError(
                f"Orientation artifact hash mismatch: {name}"
            )
        try:
            frame = pd.read_csv(path)
        except (OSError, UnicodeError, pd.errors.ParserError) as exc:
            raise RealDataOrientationError(f"Could not read {name}: {exc}") from exc
        if len(frame) != int(evidence.get("row_count", -1)):
            raise RealDataOrientationError(
                f"Orientation artifact row-count mismatch: {name}"
            )
        if list(frame.columns) != evidence.get("columns"):
            raise RealDataOrientationError(
                f"Orientation artifact columns mismatch: {name}"
            )
        _validate_safe_output_frame(frame, name)
    return summary


def _load_queries(
    path: Path,
    *,
    expected_query_count: int,
    expected_spatial_group_count: int,
) -> pd.DataFrame:
    frame = _read_csv(path, "canonical query CSV")
    _require_columns(frame, REQUIRED_QUERY_COLUMNS, "canonical query CSV")
    if len(frame) != expected_query_count:
        raise RealDataOrientationError(
            "Canonical query count is not the expected count."
        )
    if frame["query_region_id"].astype(str).duplicated().any():
        raise RealDataOrientationError("Canonical query IDs must be unique.")
    if frame["overlap_group_id"].astype(str).nunique() != expected_spatial_group_count:
        raise RealDataOrientationError("Canonical spatial-group count is invalid.")
    if not pd.to_numeric(frame["query_size_pixels"], errors="raise").eq(32).all():
        raise RealDataOrientationError("Canonical queries must be 32 x 32 cells.")
    _require_constant(frame, "feature_schema_version", FEATURE_SCHEMA_VERSION)
    _require_constant(frame, "dataset_role", "training_and_query_pool")
    _require_constant(frame, "review_status", "unreviewed")
    _require_bool(frame, "selected", False)
    _require_bool(frame, "query_model_only", True)
    for field in (
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    ):
        _require_bool(frame, field, False)
    for field in (
        "grid_contract_sha256",
        "source_registry_sha256",
        "processing_alignment_receipt_sha256",
    ):
        _sha256(_one_value(frame[field], field), field)
    return frame


def _query_metadata(
    frame: pd.DataFrame,
) -> dict[str, tuple[str, str, str, str, str, str, str]]:
    result: dict[str, tuple[str, str, str, str, str, str, str]] = {}
    for row in frame.to_dict("records"):
        result[str(row["query_region_id"])] = (
            str(row["tile_id"]),
            str(row["event_id"]),
            str(row["grid_contract_sha256"]),
            str(row["overlap_group_id"]),
            str(row["dataset_role"]),
            str(row["source_registry_sha256"]),
            str(row["processing_alignment_receipt_sha256"]),
        )
    return result


def _load_and_verify_context(
    path: Path,
    *,
    queries: pd.DataFrame,
    expected_query_count: int,
) -> tuple[pd.DataFrame, str]:
    derivation_path = path.parent / "supported_query_derivation.json"
    derivation = _load_json(
        _required_file(derivation_path, "supported-query derivation"),
        "supported-query derivation",
    )
    if (
        derivation.get("artifact_schema")
        != "floodguard.supported_query_pool_derivation.v1"
    ):
        raise RealDataOrientationError("Unknown supported-query derivation schema.")
    logical_hash = _verify_self_hash(derivation, "manifest_sha256", "supported-query")
    outputs = derivation.get("outputs")
    evidence = (
        outputs.get("supported_queries") if isinstance(outputs, Mapping) else None
    )
    if not isinstance(evidence, Mapping):
        raise RealDataOrientationError("Supported-query output evidence is missing.")
    if (
        evidence.get("sha256") != _file_sha256(path)
        or int(evidence.get("row_count", -1)) != expected_query_count
    ):
        raise RealDataOrientationError(
            "Context evidence does not match its derivation."
        )
    for field, expected in {
        "query_model_only": True,
        "eligible_for_human_annotation": False,
        "eligible_for_active_selection": False,
        "eligible_for_review_queue": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }.items():
        if derivation.get(field) is not expected:
            raise RealDataOrientationError(
                f"Supported-query derivation violates safety field {field}."
            )
    context = _read_csv(path, "context evidence CSV")
    _require_columns(context, REQUIRED_CONTEXT_COLUMNS, "context evidence CSV")
    if (
        len(context) != expected_query_count
        or context["query_region_id"].astype(str).duplicated().any()
    ):
        raise RealDataOrientationError("Context evidence must have one row per query.")
    query_ids = set(queries["query_region_id"].astype(str))
    if set(context["query_region_id"].astype(str)) != query_ids:
        raise RealDataOrientationError("Context and canonical query coverage differ.")
    query_join = queries.set_index("query_region_id")
    context_join = context.set_index("query_region_id")
    for context_field, query_field in (
        ("event_id", "event_id"),
        ("grid_contract_sha256", "grid_contract_sha256"),
        ("query_size_pixels", "query_size_pixels"),
        ("dataset_role", "dataset_role"),
        ("overlap_group_id", "overlap_group_id"),
        ("feature_schema_version", "feature_schema_version"),
    ):
        left = context_join.loc[query_join.index, context_field].astype(str)
        right = query_join[query_field].astype(str)
        if not left.equals(right):
            raise RealDataOrientationError(
                f"Context/canonical join disagrees on {context_field}."
            )
    _require_bool(context, "query_model_only", True)
    for field in (
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    ):
        _require_bool(context, field, False)
    valid = _numeric(context, "valid_data_fraction")
    if not np.equal(valid, 1.0).all():
        raise RealDataOrientationError("Context valid_data_fraction must be 1.0.")
    for field in CONTEXT_NUMERIC_COLUMNS:
        values = _numeric(context, field)
        if field.endswith("_fraction") and ((values < 0) | (values > 1)).any():
            raise RealDataOrientationError(
                f"Context fraction {field} is outside [0, 1]."
            )
        if field == "slope_p90_degrees" and (values < 0).any():
            raise RealDataOrientationError("Context slope must be non-negative.")
    if context["round0_stratum"].astype(str).str.strip().eq("").any():
        raise RealDataOrientationError("Context stratum must not be empty.")
    return context, logical_hash


def _read_validate_feature_chunks(
    path: Path,
    *,
    query_meta: Mapping[str, tuple[str, str, str, str, str, str, str]],
    expected_cell_count: int,
    expected_query_count: int,
    expected_cells_per_query: int,
    chunk_size: int,
) -> tuple[dict[str, np.ndarray], pd.DataFrame, dict[str, object]]:
    try:
        header = pd.read_csv(path, nrows=0)
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise RealDataOrientationError(
            f"Could not read feature CSV header: {exc}"
        ) from exc
    if list(header.columns) != list(REQUIRED_FEATURE_COLUMNS):
        raise RealDataOrientationError("Feature CSV column order is not canonical.")
    arrays = {
        feature: np.empty(expected_cell_count, dtype=np.float64)
        for feature in MODEL_FEATURES
    }
    query_ids = sorted(query_meta)
    query_position = {query_id: index for index, query_id in enumerate(query_ids)}
    metadata_maps = {
        field: {query_id: metadata[index] for query_id, metadata in query_meta.items()}
        for field, index in {
            "tile_id": 0,
            "event_id": 1,
            "grid_contract_sha256": 2,
            "spatial_group_id": 3,
            "dataset_role": 4,
            "source_registry_sha256": 5,
            "processing_alignment_receipt_sha256": 6,
        }.items()
    }
    seen_cells = np.zeros((expected_query_count, expected_cells_per_query), dtype=bool)
    counts = np.zeros(expected_query_count, dtype=np.int64)
    sums = np.zeros((expected_query_count, len(ML_SOURCE_FEATURES)), dtype=np.float64)
    sum_squares = np.zeros_like(sums)
    maximum_vv_residual = 0.0
    maximum_vh_residual = 0.0
    offset = 0
    try:
        iterator = pd.read_csv(path, chunksize=chunk_size)
        for chunk in iterator:
            if list(chunk.columns) != list(REQUIRED_FEATURE_COLUMNS):
                raise RealDataOrientationError(
                    "Feature CSV columns changed between chunks."
                )
            length = len(chunk)
            if offset + length > expected_cell_count:
                raise RealDataOrientationError(
                    "Feature CSV exceeds the expected cell count."
                )
            numeric_chunk: dict[str, np.ndarray] = {}
            for feature in MODEL_FEATURES:
                values = _numeric(chunk, feature)
                arrays[feature][offset : offset + length] = values
                numeric_chunk[feature] = values
            valid = numeric_chunk["valid_data_fraction"]
            if ((valid < 0) | (valid > 1)).any() or not np.equal(valid, 1.0).all():
                raise RealDataOrientationError(
                    "Feature valid_data_fraction must be finite and exactly 1.0."
                )
            vv_residual = np.abs(
                numeric_chunk["vv_change_db"]
                - (numeric_chunk["pre_vv_db"] - numeric_chunk["event_vv_db"])
            )
            vh_residual = np.abs(
                numeric_chunk["vh_change_db"]
                - (numeric_chunk["pre_vh_db"] - numeric_chunk["event_vh_db"])
            )
            maximum_vv_residual = max(maximum_vv_residual, float(vv_residual.max()))
            maximum_vh_residual = max(maximum_vh_residual, float(vh_residual.max()))
            if maximum_vv_residual > 1e-9 or maximum_vh_residual > 1e-9:
                raise RealDataOrientationError(
                    "Feature change formula validation failed."
                )

            rows = pd.to_numeric(chunk["row_index"], errors="raise").to_numpy()
            columns = pd.to_numeric(chunk["column_index"], errors="raise").to_numpy()
            if (
                not np.equal(rows, np.floor(rows)).all()
                or not np.equal(columns, np.floor(columns)).all()
            ):
                raise RealDataOrientationError(
                    "Cell row/column indexes must be integers."
                )
            rows = rows.astype(np.int64)
            columns = columns.astype(np.int64)
            if ((rows < 0) | (rows >= 32) | (columns < 0) | (columns >= 32)).any():
                raise RealDataOrientationError(
                    "Cell row/column indexes are outside 32 x 32."
                )

            query_values = chunk["query_region_id"].astype(str).to_numpy()
            cell_values = chunk["cell_id"].astype(str).to_numpy()
            sample_values = chunk["sample_id"].astype(str).to_numpy()
            if not np.array_equal(cell_values, sample_values):
                raise RealDataOrientationError("sample_id must equal cell_id.")
            feature_matrix = np.column_stack(
                [numeric_chunk[name] for name in ML_SOURCE_FEATURES]
            )
            positions_series = chunk["query_region_id"].astype(str).map(query_position)
            if positions_series.isna().any():
                raise RealDataOrientationError(
                    "Feature CSV contains a non-canonical query."
                )
            positions = positions_series.to_numpy(dtype=np.int64)
            for field, mapping in metadata_maps.items():
                expected = chunk["query_region_id"].astype(str).map(mapping).astype(str)
                if not chunk[field].astype(str).equals(expected):
                    raise RealDataOrientationError(
                        "Feature/canonical metadata join validation failed."
                    )
            if (
                not chunk["feature_schema_version"]
                .astype(str)
                .eq(FEATURE_SCHEMA_VERSION)
                .all()
            ):
                raise RealDataOrientationError(
                    "Feature/canonical metadata join validation failed."
                )
            coordinates = rows * 32 + columns
            flat_keys = positions * expected_cells_per_query + coordinates
            if (
                len(np.unique(flat_keys)) != length
                or seen_cells[positions, coordinates].any()
            ):
                raise RealDataOrientationError(
                    "Feature query contains a duplicate cell."
                )
            expected_cell_ids = np.fromiter(
                (
                    f"{query_id}_R{row:04d}_C{column:04d}"
                    for query_id, row, column in zip(
                        query_values, rows, columns, strict=True
                    )
                ),
                dtype=object,
                count=length,
            )
            if not np.array_equal(cell_values, expected_cell_ids):
                raise RealDataOrientationError("Feature cell_id is not canonical.")
            seen_cells[positions, coordinates] = True
            np.add.at(counts, positions, 1)
            np.add.at(sums, positions, feature_matrix)
            np.add.at(sum_squares, positions, feature_matrix**2)
            offset += length
    except (OSError, UnicodeError, pd.errors.ParserError, ValueError) as exc:
        if isinstance(exc, RealDataOrientationError):
            raise
        raise RealDataOrientationError(
            f"Could not validate feature CSV: {exc}"
        ) from exc

    if offset != expected_cell_count:
        raise RealDataOrientationError(
            "Feature CSV row count is not the expected count."
        )
    if not np.equal(counts, expected_cells_per_query).all() or not seen_cells.all():
        raise RealDataOrientationError(
            "Feature CSV does not have exact 32 x 32 query grain."
        )
    means = sums / counts[:, None]
    variance = np.maximum(sum_squares / counts[:, None] - means**2, 0.0)
    stds = np.sqrt(variance)
    aggregates = pd.DataFrame(
        np.column_stack([means, stds]), columns=QUERY_AGGREGATE_FEATURES
    )
    return (
        arrays,
        aggregates,
        {
            "chunk_safe_cell_validation": True,
            "feature_column_order_valid": True,
            "exact_query_grain_valid": True,
            "all_numeric_features_finite": True,
            "all_valid_data_fraction_equal_one": True,
            "maximum_absolute_vv_formula_residual": maximum_vv_residual,
            "maximum_absolute_vh_formula_residual": maximum_vh_residual,
        },
    )


def _build_feature_quantiles(values: Mapping[str, np.ndarray]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    statistics = (
        ("minimum", 0.0),
        ("p05", 0.05),
        ("p25", 0.25),
        ("median", 0.50),
        ("p75", 0.75),
        ("p95", 0.95),
        ("maximum", 1.0),
    )
    for feature in MODEL_FEATURES:
        vector = values[feature]
        for statistic, quantile in statistics:
            rows.append(
                {
                    "feature": feature,
                    "statistic": statistic,
                    "value": float(np.quantile(vector, quantile)),
                }
            )
        rows.extend(
            [
                {
                    "feature": feature,
                    "statistic": "mean",
                    "value": float(vector.mean()),
                },
                {
                    "feature": feature,
                    "statistic": "standard_deviation",
                    "value": float(vector.std()),
                },
            ]
        )
    return pd.DataFrame(rows, columns=("feature", "statistic", "value"))


def _build_change_histograms(values: Mapping[str, np.ndarray]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for feature in ("vv_change_db", "vh_change_db"):
        counts, edges = np.histogram(values[feature], bins=50)
        for index, count in enumerate(counts):
            rows.append(
                {
                    "feature": feature,
                    "bin_index": index,
                    "bin_left": float(edges[index]),
                    "bin_right": float(edges[index + 1]),
                    "cell_count": int(count),
                }
            )
    return pd.DataFrame(
        rows,
        columns=("feature", "bin_index", "bin_left", "bin_right", "cell_count"),
    )


def _build_context_summary(context: pd.DataFrame) -> pd.DataFrame:
    grouped = context.groupby("round0_stratum", sort=True, observed=True)
    rows: list[dict[str, object]] = []
    for stratum, group in grouped:
        row: dict[str, object] = {
            "context_stratum": str(stratum),
            "query_count": int(len(group)),
            "spatial_group_count": int(group["overlap_group_id"].astype(str).nunique()),
        }
        for field in CONTEXT_NUMERIC_COLUMNS:
            row[f"mean_{field}"] = float(_numeric(group, field).mean())
        row["descriptive_only_small_slice"] = bool(
            row["query_count"] < 20 or row["spatial_group_count"] < 2
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _build_unsupervised_tables(
    query_aggregates: pd.DataFrame,
    *,
    random_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    try:
        from sklearn.cluster import KMeans
        from sklearn.decomposition import PCA
        from sklearn.metrics import silhouette_score
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:  # pragma: no cover - dependency/environment guard
        raise RealDataOrientationError(
            "Real-data ML orientation requires the project ml extra (scikit-learn)."
        ) from exc
    if len(query_aggregates) <= 6:
        raise RealDataOrientationError(
            "PCA/k-means sensitivity requires at least 7 queries."
        )
    matrix = query_aggregates.to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise RealDataOrientationError("Query aggregates contain non-finite values.")
    scaled = StandardScaler().fit_transform(matrix)
    pca = PCA(n_components=min(6, scaled.shape[1]), svd_solver="full")
    pca.fit(scaled)
    pca_rows: list[dict[str, object]] = []
    for index, component in enumerate(pca.components_):
        row: dict[str, object] = {
            "component": f"PC{index + 1}",
            "explained_variance_ratio": float(pca.explained_variance_ratio_[index]),
        }
        for feature, loading in zip(QUERY_AGGREGATE_FEATURES, component, strict=True):
            row[f"loading_{feature}"] = float(loading)
        pca_rows.append(row)

    sensitivity_rows: list[dict[str, object]] = []
    cluster_rows: list[dict[str, object]] = []
    for k in (3, 4, 5, 6):
        model = KMeans(
            n_clusters=k,
            random_state=int(random_seed),
            n_init=20,
            algorithm="lloyd",
        )
        membership = model.fit_predict(scaled)
        counts = np.bincount(membership, minlength=k)
        sensitivity_rows.append(
            {
                "k": k,
                "silhouette": float(silhouette_score(scaled, membership)),
                "inertia": float(model.inertia_),
                "minimum_cluster_query_count": int(counts.min()),
                "maximum_cluster_query_count": int(counts.max()),
            }
        )
        for cluster_id in range(k):
            mask = membership == cluster_id
            row: dict[str, object] = {
                "k": k,
                "cluster_id": cluster_id,
                "query_count": int(mask.sum()),
                "interpretation": "descriptive_backscatter_pattern_not_flood_class",
            }
            for feature in QUERY_AGGREGATE_FEATURES:
                row[f"centroid_{feature}"] = float(
                    query_aggregates.loc[mask, feature].mean()
                )
            cluster_rows.append(row)
    return (
        pd.DataFrame(pca_rows),
        pd.DataFrame(sensitivity_rows),
        pd.DataFrame(cluster_rows),
    )


def _verify_feature_derivation(
    payload: Mapping[str, object],
    *,
    feature_hash: str,
    query_hash: str,
    expected_cell_count: int,
    expected_query_count: int,
) -> str:
    if payload.get("artifact_schema") != "floodguard.sar_change_v2_features.v1":
        raise RealDataOrientationError("Unknown sar_change_v2 derivation schema.")
    logical_hash = _verify_self_hash(payload, "manifest_sha256", "feature derivation")
    if payload.get("feature_schema_version") != FEATURE_SCHEMA_VERSION or payload.get(
        "feature_order"
    ) != list(MODEL_FEATURES):
        raise RealDataOrientationError("Feature derivation schema/order is invalid.")
    if payload.get("formulas") != {
        "vv_change_db": "pre_vv_db - event_vv_db",
        "vh_change_db": "pre_vh_db - event_vh_db",
        "valid_data_fraction": (
            "1.0 only after all four source observations are valid; otherwise extraction blocks"
        ),
    }:
        raise RealDataOrientationError("Feature derivation formulas are not canonical.")
    output = payload.get("output")
    sources = payload.get("sources")
    query_source = (
        sources.get("query_manifest") if isinstance(sources, Mapping) else None
    )
    if not isinstance(output, Mapping) or not isinstance(query_source, Mapping):
        raise RealDataOrientationError("Feature derivation lineage is incomplete.")
    if (
        output.get("feature_csv_sha256") != feature_hash
        or int(output.get("row_count", -1)) != expected_cell_count
    ):
        raise RealDataOrientationError("Feature CSV does not match its derivation.")
    if output.get("columns") != list(REQUIRED_FEATURE_COLUMNS):
        raise RealDataOrientationError("Feature derivation output columns are invalid.")
    if (
        query_source.get("file_sha256") != query_hash
        or int(query_source.get("row_count", -1)) != expected_query_count
    ):
        raise RealDataOrientationError(
            "Canonical queries do not match feature lineage."
        )
    if len(output.get("query_region_ids", [])) != expected_query_count:
        raise RealDataOrientationError("Feature derivation query coverage is invalid.")
    safety = payload.get("safety")
    if not isinstance(safety, Mapping) or safety != {
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "allowed_output_use": "query_committee_features_only",
    }:
        raise RealDataOrientationError("Feature derivation safety contract is invalid.")
    return logical_hash


def _verify_grid_receipt(
    payload: Mapping[str, object],
    *,
    file_hash: str,
    grid_hash: str,
    processing_hash: str,
    source_registry_hash: str,
    expected_query_count: int,
    expected_spatial_group_count: int,
) -> str:
    del file_hash  # file bytes are bound by the release seal below
    if payload.get("artifact_schema") != "floodguard.grid_validation_receipt.v3":
        raise RealDataOrientationError("Unknown grid validation receipt schema.")
    logical_hash = _verify_self_hash(payload, "receipt_sha256", "grid receipt")
    if payload.get("grid_contract_sha256s") != [grid_hash]:
        raise RealDataOrientationError("Grid receipt contract hash is inconsistent.")
    _sha256(payload.get("source_registry_sha256"), "receipt source_registry_sha256")
    _sha256(source_registry_hash, "canonical source_registry_sha256")
    expectations = {
        "processing_alignment_receipt_sha256": processing_hash,
        "query_count": expected_query_count,
        "tile_count": expected_spatial_group_count,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    if any(payload.get(field) != expected for field, expected in expectations.items()):
        raise RealDataOrientationError("Grid validation receipt contract is invalid.")
    return logical_hash


def _verify_release_seal(
    payload: Mapping[str, object],
    *,
    seal_path: Path,
    receipt_file_hash: str,
    receipt_logical_hash: str,
    processing_hash: str,
    query_path: Path,
    expected_query_count: int,
    expected_spatial_group_count: int,
) -> tuple[str, str]:
    if payload.get("artifact_schema") != "floodguard.canonical_grid_release.v1":
        raise RealDataOrientationError("Unknown canonical release seal schema.")
    logical_hash = _verify_self_hash(payload, "seal_sha256", "release seal")
    expectations = {
        "grid_validation_receipt_file_sha256": receipt_file_hash,
        "grid_validation_receipt_sha256": receipt_logical_hash,
        "processing_alignment_receipt_sha256": processing_hash,
        "query_count": expected_query_count,
        "tile_count": expected_spatial_group_count,
        "overall_training_ready": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    if any(payload.get(field) != expected for field, expected in expectations.items()):
        raise RealDataOrientationError("Canonical release seal contract is invalid.")
    manifest_path = _required_file(
        seal_path.parent / "release_manifest.csv", "canonical release manifest"
    )
    manifest_hash = _file_sha256(manifest_path)
    if payload.get("release_manifest_sha256") != manifest_hash:
        raise RealDataOrientationError("Release manifest does not match its seal.")
    manifest = _read_csv(manifest_path, "canonical release manifest")
    _require_columns(
        manifest,
        ("file_name", "file_size_bytes", "sha256", "immutable_status"),
        "canonical release manifest",
    )
    seen_names: set[str] = set()
    for row in manifest.to_dict("records"):
        name = str(row["file_name"]).strip()
        if not name or Path(name).name != name or name in seen_names:
            raise RealDataOrientationError(
                "Canonical release manifest contains an unsafe or duplicate file name."
            )
        seen_names.add(name)
        artifact_path = _required_file(
            seal_path.parent / name, f"canonical release artifact {name}"
        )
        if artifact_path.stat().st_size != _positive_int(
            row["file_size_bytes"], "release file_size_bytes"
        ):
            raise RealDataOrientationError(
                f"Canonical release artifact size mismatch: {name}"
            )
        if _file_sha256(artifact_path) != str(row["sha256"]).strip():
            raise RealDataOrientationError(
                f"Canonical release artifact hash mismatch: {name}"
            )
        if not str(row["immutable_status"]).strip().startswith("frozen_"):
            raise RealDataOrientationError(
                f"Canonical release artifact is not frozen: {name}"
            )
    query_rows = manifest.loc[manifest["file_name"].astype(str).eq(query_path.name)]
    if len(query_rows) != 1 or str(query_rows.iloc[0]["sha256"]) != _file_sha256(
        query_path
    ):
        raise RealDataOrientationError(
            "Canonical query CSV is not the sealed release file."
        )
    if not str(query_rows.iloc[0]["immutable_status"]).startswith("frozen_"):
        raise RealDataOrientationError("Canonical query CSV is not frozen.")
    return logical_hash, manifest_hash


def _validate_safe_output_frame(frame: pd.DataFrame, name: str) -> None:
    lowered = {str(column).strip().lower() for column in frame.columns}
    forbidden = lowered & _FORBIDDEN_OUTPUT_COLUMNS
    forbidden.update(
        column
        for column in lowered
        if column.startswith("bbox_")
        or column.startswith("weak_")
        or column.endswith("_priority")
        or column.endswith("_label")
        or column.endswith("_score")
        or column in {"spatial_group_id", "overlap_group_id"}
    )
    if forbidden:
        raise RealDataOrientationError(
            f"Reviewer-safe output {name} exposes forbidden columns: {sorted(forbidden)}"
        )
    if frame.empty:
        raise RealDataOrientationError(
            f"Reviewer-safe output {name} must not be empty."
        )


def _validate_output_target(path: Path) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise RealDataOrientationError(
            f"Output directory must be new or empty and will not be overwritten: {path}"
        )


def _paths(directory: Path) -> RealDataOrientationPaths:
    return RealDataOrientationPaths(
        directory=directory,
        summary=directory / SUMMARY_FILENAME,
        feature_quantiles=directory / FEATURE_QUANTILES_FILENAME,
        change_histograms=directory / CHANGE_HISTOGRAMS_FILENAME,
        context_summary=directory / CONTEXT_SUMMARY_FILENAME,
        pca_summary=directory / PCA_SUMMARY_FILENAME,
        cluster_sensitivity=directory / CLUSTER_SENSITIVITY_FILENAME,
        cluster_summary=directory / CLUSTER_SUMMARY_FILENAME,
    )


def _safe_source_name(key: str) -> str:
    names = {
        "feature_csv": "sar_change_v2_cells.csv",
        "derivation_manifest": "sar_change_v2_derivation.json",
        "canonical_query_csv": "canonical_query_regions.csv",
        "context_evidence_csv": "supported_query_evidence.csv",
        "context_derivation_manifest": "supported_query_derivation.json",
        "grid_validation_receipt": "grid_validation_receipt_v3.json",
        "release_manifest": "release_manifest.csv",
        "release_seal": "release_seal.json",
    }
    return names[key]


def _normalise_timestamp(value: str | datetime | None) -> str:
    if value is None:
        parsed = datetime.now(UTC)
    elif isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise RealDataOrientationError("created_at_utc must be ISO-8601.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RealDataOrientationError("created_at_utc must include a UTC offset.")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _verify_self_hash(payload: Mapping[str, object], field: str, label: str) -> str:
    declared = _sha256(payload.get(field), field)
    unsigned = dict(payload)
    unsigned.pop(field, None)
    if _canonical_sha256(unsigned) != declared:
        raise RealDataOrientationError(f"{label} self-hash mismatch.")
    return declared


def _canonical_sha256(payload: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RealDataOrientationError(f"Could not canonicalize JSON: {exc}") from exc
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(
            payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False
        )
        + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path, label: str) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RealDataOrientationError(f"Could not read {label}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RealDataOrientationError(f"{label} must contain a JSON object.")
    return payload


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise RealDataOrientationError(f"Could not read {label}: {exc}") from exc


def _required_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise RealDataOrientationError(
            f"{label} does not exist or is not a file: {path}"
        )
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise RealDataOrientationError(f"Could not hash {path.name}: {exc}") from exc
    return digest.hexdigest()


def _sha256(value: object, label: str) -> str:
    text = str(value).strip().lower()
    if _SHA256_RE.fullmatch(text) is None:
        raise RealDataOrientationError(f"{label} must be a complete lowercase SHA-256.")
    return text


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise RealDataOrientationError(
            f"{label} is missing columns: {', '.join(missing)}."
        )


def _require_constant(frame: pd.DataFrame, column: str, expected: str) -> None:
    if not frame[column].astype(str).eq(expected).all():
        raise RealDataOrientationError(f"Every {column} must equal {expected!r}.")


def _require_bool(frame: pd.DataFrame, column: str, expected: bool) -> None:
    values = frame[column].map(_coerce_bool)
    if values.isna().any() or not values.eq(expected).all():
        raise RealDataOrientationError(f"Every {column} must be {expected}.")


def _coerce_bool(value: object) -> bool | None:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    try:
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise RealDataOrientationError(f"{column} must be numeric.") from exc
    if not np.isfinite(values).all():
        raise RealDataOrientationError(f"{column} contains non-finite values.")
    return values


def _one_value(series: pd.Series, label: str) -> str:
    values = tuple(sorted(set(series.astype(str))))
    if len(values) != 1 or not values[0]:
        raise RealDataOrientationError(
            f"{label} must have exactly one non-empty value."
        )
    return values[0]


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise RealDataOrientationError(f"{label} must be a positive integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise RealDataOrientationError(f"{label} must be a positive integer.") from exc
    if number <= 0 or number != value:
        raise RealDataOrientationError(f"{label} must be a positive integer.")
    return number
