"""Rasterize a locked calibration authority decision into reference-cell input.

This module deliberately stops one step before the calibration reference is
frozen.  It converts one named authority's immutable multipart geometry into
the complete canonical cell table consumed by
``freeze_label_factory_calibration_reference.py`` and writes a self-hashed
lineage manifest.  The output remains confidential calibration evidence and
is never training, decision, FPPS, or warning data.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from floodguard.label_factory.annotation_rasterization import (
    GEOMETRY_PART_COLUMNS,
    QUERY_GRID_COLUMNS,
    AnnotationRasterizationError,
    rasterize_annotation_geometries,
)
from floodguard.label_factory.annotations import (
    AnnotationRecord,
    annotation_content_sha256,
)
from floodguard.label_factory.calibration import MINIMUM_CALIBRATION_QUERY_COUNT
from floodguard.label_factory.contracts import DatasetRole, FloodLabel


REFERENCE_INPUT_RASTER_SCHEMA = (
    "floodguard.calibration_reference_geometry_raster.v1"
)

REFERENCE_INPUT_COLUMNS = (
    "event_id",
    "tile_id",
    "query_region_id",
    "cell_id",
    "row_index",
    "column_index",
    "label_code",
)

CALIBRATION_QUERY_COLUMNS = (
    "dataset_role",
    "eligible_for_human_annotation",
    "eligible_for_active_selection",
    "eligible_for_query_model_training",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)


@dataclass(frozen=True, slots=True)
class CalibrationReferenceInputOutputs:
    """Paths for immutable reference-cell input and its lineage manifest."""

    cells: Path
    manifest: Path


def build_calibration_reference_cell_input(
    authority_annotations: Sequence[AnnotationRecord],
    query_manifest: pd.DataFrame,
    geometry_parts: pd.DataFrame,
    *,
    authority_id: str,
) -> pd.DataFrame:
    """Return complete canonical reference input from one locked authority.

    Codes 0--4 are produced only by explicit geometry or the explicit
    primary-class fill policy.  Code 255 is retained only for cells outside a
    partial reviewed extent.  The shared reviewer rasterizer enforces polygon
    validity, containment, cross-class non-overlap, exact locked-payload
    binding, complete grid generation, and explicit fill semantics.
    """

    authority = _required_text(authority_id, "authority_id")
    queries = query_manifest.copy().fillna("")
    parts = geometry_parts.copy().fillna("")
    _require_columns(
        queries,
        (*QUERY_GRID_COLUMNS, *CALIBRATION_QUERY_COLUMNS),
        "calibration query manifest",
    )
    _require_columns(parts, GEOMETRY_PART_COLUMNS, "authority geometry parts")
    _validate_calibration_queries(queries)
    _validate_authority_annotations(authority_annotations, queries, authority)

    raster = rasterize_annotation_geometries(
        authority_annotations,
        queries,
        parts,
    )
    output = raster.loc[:, REFERENCE_INPUT_COLUMNS].copy()
    output = output.sort_values(
        ["query_region_id", "row_index", "column_index"], kind="stable"
    ).reset_index(drop=True)
    _validate_reference_input(output, queries)
    return output


def write_calibration_reference_cell_input(
    authority_annotations: Sequence[AnnotationRecord],
    query_manifest: pd.DataFrame | str | Path,
    geometry_parts: pd.DataFrame | str | Path,
    *,
    authority_id: str,
    authority_role_evidence: str | Path,
    assumptions: str,
    cell_output_path: str | Path,
    manifest_output_path: str | Path,
) -> CalibrationReferenceInputOutputs:
    """Exclusively write reference input plus self-hashed source lineage."""

    queries = _coerce_frame(query_manifest, "calibration query manifest")
    parts = _coerce_frame(geometry_parts, "authority geometry parts")
    authority = _required_text(authority_id, "authority_id")
    note = _required_text(assumptions, "assumptions")
    evidence_path = Path(authority_role_evidence)
    if not evidence_path.is_file():
        raise AnnotationRasterizationError(
            "Authority role/qualification evidence file is missing."
        )
    evidence_sha = _file_sha256(evidence_path)
    cells = build_calibration_reference_cell_input(
        authority_annotations,
        queries,
        parts,
        authority_id=authority,
    )

    cell_path = Path(cell_output_path)
    manifest_path = Path(manifest_output_path)
    if cell_path.suffix.lower() != ".csv":
        raise AnnotationRasterizationError("Reference-cell input must be CSV.")
    if manifest_path.suffix.lower() != ".json":
        raise AnnotationRasterizationError(
            "Reference-input lineage manifest must be JSON."
        )
    if cell_path.resolve() == manifest_path.resolve():
        raise AnnotationRasterizationError(
            "Reference-cell input and lineage manifest paths must differ."
        )
    if cell_path.exists() or manifest_path.exists():
        raise AnnotationRasterizationError(
            "Calibration reference-input outputs are immutable and must not be overwritten."
        )

    cell_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    cell_created = False
    manifest_created = False
    try:
        with cell_path.open("x", encoding="utf-8", newline="") as handle:
            cell_created = True
            cells.to_csv(handle, index=False, lineterminator="\n")
        query_rows = queries.fillna("").to_dict("records")
        values: dict[str, Any] = {
            "artifact_schema": REFERENCE_INPUT_RASTER_SCHEMA,
            "authority_id": authority,
            "authority_role_evidence_file": evidence_path.name,
            "authority_role_evidence_sha256": evidence_sha,
            "annotation_ids": sorted(
                annotation.annotation_id for annotation in authority_annotations
            ),
            "source_annotation_content_sha256": {
                annotation.annotation_id: annotation_content_sha256(annotation)
                for annotation in sorted(
                    authority_annotations, key=lambda item: item.annotation_id
                )
            },
            "query_manifest_sha256": _artifact_sha256(query_manifest, queries),
            "geometry_parts_sha256": _artifact_sha256(geometry_parts, parts),
            "reference_cell_input_file": cell_path.name,
            "reference_cell_input_sha256": _file_sha256(cell_path),
            "query_region_ids": sorted(
                str(value) for value in queries["query_region_id"]
            ),
            "cell_count": len(cells),
            "label_code_counts": {
                str(code): int(count)
                for code, count in sorted(
                    cells["label_code"].astype(int).value_counts().items()
                )
            },
            "grid_contract_sha256_by_query": {
                str(row["query_region_id"]): str(
                    row["grid_contract_sha256"]
                ).strip().lower()
                for row in query_rows
            },
            "source_registry_sha256_by_query": {
                str(row["query_region_id"]): str(
                    row["source_registry_sha256"]
                ).strip().lower()
                for row in query_rows
            },
            "confidential": True,
            "calibration_reference_frozen": False,
            "dataset_role": DatasetRole.REVIEWER_CALIBRATION.value,
            "eligible_for_reviewer_calibration": True,
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "assumptions": note,
        }
        values["manifest_sha256"] = _canonical_json_sha256(values)
        with manifest_path.open("x", encoding="utf-8") as handle:
            manifest_created = True
            json.dump(values, handle, sort_keys=True, indent=2)
            handle.write("\n")
    except Exception:
        if manifest_created:
            manifest_path.unlink(missing_ok=True)
        if cell_created:
            cell_path.unlink(missing_ok=True)
        raise
    return CalibrationReferenceInputOutputs(cells=cell_path, manifest=manifest_path)


def verify_calibration_reference_input_manifest(
    manifest_path: str | Path,
    *,
    cell_path: str | Path | None = None,
) -> dict[str, Any]:
    """Verify the self-hash, output checksum, and fail-closed safety fields."""

    path = Path(manifest_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnnotationRasterizationError(
            "Could not load reference-input lineage manifest."
        ) from exc
    if not isinstance(payload, dict):
        raise AnnotationRasterizationError(
            "Reference-input lineage manifest must be a JSON object."
        )
    if payload.get("artifact_schema") != REFERENCE_INPUT_RASTER_SCHEMA:
        raise AnnotationRasterizationError(
            "Reference-input lineage manifest uses the wrong schema."
        )
    observed_self_hash = str(payload.get("manifest_sha256", "")).strip().lower()
    unsigned = dict(payload)
    unsigned.pop("manifest_sha256", None)
    if observed_self_hash != _canonical_json_sha256(unsigned):
        raise AnnotationRasterizationError(
            "Reference-input lineage manifest self-hash does not match."
        )
    expected_safety = {
        "confidential": True,
        "calibration_reference_frozen": False,
        "dataset_role": DatasetRole.REVIEWER_CALIBRATION.value,
        "eligible_for_reviewer_calibration": True,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for field, expected in expected_safety.items():
        if payload.get(field) != expected:
            raise AnnotationRasterizationError(
                f"Reference-input lineage manifest has unsafe {field}."
            )
    _required_text(payload.get("authority_id", ""), "authority_id")
    _required_text(payload.get("assumptions", ""), "assumptions")
    for field in (
        "authority_role_evidence_sha256",
        "query_manifest_sha256",
        "geometry_parts_sha256",
        "reference_cell_input_sha256",
        "manifest_sha256",
    ):
        if not _is_sha256(payload.get(field, "")):
            raise AnnotationRasterizationError(
                f"Reference-input lineage manifest has invalid {field}."
            )
    annotation_ids = payload.get("annotation_ids")
    annotation_hashes = payload.get("source_annotation_content_sha256")
    query_ids = payload.get("query_region_ids")
    if (
        not isinstance(annotation_ids, list)
        or not annotation_ids
        or any(not isinstance(value, str) or not value for value in annotation_ids)
        or annotation_ids != sorted(set(annotation_ids))
        or not isinstance(annotation_hashes, dict)
        or set(annotation_hashes) != set(annotation_ids)
        or any(not _is_sha256(value) for value in annotation_hashes.values())
    ):
        raise AnnotationRasterizationError(
            "Reference-input lineage annotation coverage is invalid."
        )
    if (
        not isinstance(query_ids, list)
        or len(query_ids) < MINIMUM_CALIBRATION_QUERY_COUNT
        or any(not isinstance(value, str) or not value for value in query_ids)
        or query_ids != sorted(set(query_ids))
    ):
        raise AnnotationRasterizationError(
            "Reference-input lineage query coverage is invalid."
        )
    for field in (
        "grid_contract_sha256_by_query",
        "source_registry_sha256_by_query",
    ):
        mapping = payload.get(field)
        if (
            not isinstance(mapping, dict)
            or set(mapping) != set(query_ids)
            or any(not _is_sha256(value) for value in mapping.values())
        ):
            raise AnnotationRasterizationError(
                f"Reference-input lineage manifest has invalid {field}."
            )
    cells = Path(cell_path) if cell_path is not None else path.with_name(
        str(payload.get("reference_cell_input_file", ""))
    )
    if not cells.is_file():
        raise AnnotationRasterizationError("Reference-cell input file is missing.")
    if cells.name != payload.get("reference_cell_input_file"):
        raise AnnotationRasterizationError(
            "Reference-cell input filename does not match its lineage manifest."
        )
    if _file_sha256(cells) != payload.get("reference_cell_input_sha256"):
        raise AnnotationRasterizationError(
            "Reference-cell input failed checksum validation."
        )
    try:
        frame = pd.read_csv(cells).fillna("")
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise AnnotationRasterizationError(
            "Could not load reference-cell input."
        ) from exc
    if tuple(frame.columns) != REFERENCE_INPUT_COLUMNS:
        raise AnnotationRasterizationError(
            "Reference-cell input columns do not match the freezer contract."
        )
    if len(frame) != payload.get("cell_count"):
        raise AnnotationRasterizationError(
            "Reference-cell input count does not match its lineage manifest."
        )
    if set(frame["query_region_id"].astype(str)) != set(query_ids):
        raise AnnotationRasterizationError(
            "Reference-cell input query coverage does not match its lineage manifest."
        )
    if frame.duplicated(subset=["query_region_id", "cell_id"]).any() or frame.duplicated(
        subset=["query_region_id", "row_index", "column_index"]
    ).any():
        raise AnnotationRasterizationError(
            "Reference-cell input has duplicate canonical cells."
        )
    try:
        label_codes = frame["label_code"].astype(int)
    except (TypeError, ValueError) as exc:
        raise AnnotationRasterizationError(
            "Reference-cell input contains a non-integer label code."
        ) from exc
    observed_counts = {
        str(code): int(count)
        for code, count in sorted(label_codes.value_counts().items())
    }
    if observed_counts != payload.get("label_code_counts"):
        raise AnnotationRasterizationError(
            "Reference-cell input label counts do not match its lineage manifest."
        )
    valid_codes = {int(label) for label in FloodLabel}
    if not set(label_codes).issubset(valid_codes):
        raise AnnotationRasterizationError(
            "Reference-cell input contains an invalid label code."
        )
    return payload


def _validate_authority_annotations(
    annotations: Sequence[AnnotationRecord],
    queries: pd.DataFrame,
    authority_id: str,
) -> None:
    if not annotations:
        raise AnnotationRasterizationError(
            "At least one locked authority annotation is required."
        )
    if {record.reviewer_id for record in annotations} != {authority_id}:
        raise AnnotationRasterizationError(
            "Authority annotations must belong exclusively to authority_id."
        )
    annotation_queries = [record.query_region_id for record in annotations]
    if len(annotation_queries) != len(set(annotation_queries)):
        raise AnnotationRasterizationError(
            "Authority annotations must contain exactly one locked record per query."
        )
    expected_queries = set(queries["query_region_id"].astype(str))
    if set(annotation_queries) != expected_queries:
        raise AnnotationRasterizationError(
            "Authority annotations must exactly cover the calibration query manifest."
        )
    query_by_id = {
        str(row["query_region_id"]): row for row in queries.to_dict("records")
    }
    protocol_versions = {record.protocol_version for record in annotations}
    if len(protocol_versions) != 1:
        raise AnnotationRasterizationError(
            "Authority annotations must use one protocol version."
        )
    for record in annotations:
        query = query_by_id[record.query_region_id]
        if record.event_id != str(query["event_id"]) or record.tile_id != str(
            query["tile_id"]
        ):
            raise AnnotationRasterizationError(
                f"Authority annotation {record.annotation_id} has wrong event/tile lineage."
            )
        expected_grid = str(query["grid_contract_sha256"]).strip().lower()
        expected_source = str(query["source_registry_sha256"]).strip().lower()
        if record.grid_contract_sha256 != expected_grid:
            raise AnnotationRasterizationError(
                f"Authority annotation {record.annotation_id} has wrong grid hash."
            )
        if record.source_registry_sha256 != expected_source:
            raise AnnotationRasterizationError(
                f"Authority annotation {record.annotation_id} has wrong source hash."
            )
        if record.source_timestamp is None or _iso_utc(
            record.source_timestamp
        ) != _normalized_timestamp_text(query["source_timestamp"]):
            raise AnnotationRasterizationError(
                f"Authority annotation {record.annotation_id} has wrong source timestamp."
            )
        for field in ("bundle_manifest_sha256", "context_manifest_sha256"):
            value = getattr(record, field)
            if value is None or not _is_sha256(value):
                raise AnnotationRasterizationError(
                    f"Authority annotation {record.annotation_id} lacks {field}."
                )
        _required_text(record.assumptions, f"{record.annotation_id} assumptions")


def _validate_calibration_queries(queries: pd.DataFrame) -> None:
    if len(queries) < MINIMUM_CALIBRATION_QUERY_COUNT:
        raise AnnotationRasterizationError(
            "Calibration reference input requires at least "
            f"{MINIMUM_CALIBRATION_QUERY_COUNT} queries."
        )
    if queries["query_region_id"].astype(str).duplicated().any():
        raise AnnotationRasterizationError(
            "Calibration query manifest query_region_id values must be unique."
        )
    expected_flags = {
        "eligible_for_human_annotation": True,
        "eligible_for_active_selection": False,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for row in queries.to_dict("records"):
        query_id = _required_text(row["query_region_id"], "query_region_id")
        if str(row["dataset_role"]).strip() != DatasetRole.REVIEWER_CALIBRATION.value:
            raise AnnotationRasterizationError(
                f"Calibration query {query_id} has the wrong dataset_role."
            )
        for field, expected in expected_flags.items():
            if _strict_bool(row[field], field) is not expected:
                raise AnnotationRasterizationError(
                    f"Calibration query {query_id} has unsafe {field}."
                )
        if "eligible_for_training_after_human_review" in row and str(
            row["eligible_for_training_after_human_review"]
        ).strip().lower() not in {"", "no"}:
            raise AnnotationRasterizationError(
                f"Calibration query {query_id} cannot become training data."
            )


def _validate_reference_input(cells: pd.DataFrame, queries: pd.DataFrame) -> None:
    expected_queries = set(queries["query_region_id"].astype(str))
    if set(cells["query_region_id"].astype(str)) != expected_queries:
        raise AnnotationRasterizationError(
            "Reference-cell input does not exactly cover calibration queries."
        )
    query_by_id = {
        str(row["query_region_id"]): row for row in queries.to_dict("records")
    }
    for query_id, rows in cells.groupby(cells["query_region_id"].astype(str)):
        size = int(query_by_id[query_id]["query_size_pixels"])
        if len(rows) != size * size:
            raise AnnotationRasterizationError(
                f"Reference-cell input is not a complete grid for {query_id}."
            )
        labels = {int(value) for value in rows["label_code"]}
        if not labels.issubset({int(label) for label in FloodLabel}):
            raise AnnotationRasterizationError(
                f"Reference-cell input has an invalid label for {query_id}."
            )
        if labels == {int(FloodLabel.UNREVIEWED)}:
            raise AnnotationRasterizationError(
                f"Reference-cell input query {query_id} is 255-only."
            )


def _coerce_frame(source: pd.DataFrame | str | Path, label: str) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    try:
        return pd.read_csv(Path(source)).fillna("")
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise AnnotationRasterizationError(f"Could not load {label}.") from exc


def _require_columns(
    frame: pd.DataFrame, required: Sequence[str], label: str
) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise AnnotationRasterizationError(f"{label} missing columns: {missing}.")


def _required_text(value: object, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise AnnotationRasterizationError(f"{field} must not be blank.")
    return text


def _strict_bool(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise AnnotationRasterizationError(f"{field} must be boolean.")


def _artifact_sha256(
    source: pd.DataFrame | str | Path, frame: pd.DataFrame
) -> str:
    if isinstance(source, (str, Path)):
        return _file_sha256(Path(source))
    ordered = frame.copy().fillna("").reindex(sorted(frame.columns), axis=1)
    return hashlib.sha256(
        ordered.to_csv(index=False, lineterminator="\n").encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _is_sha256(value: object) -> bool:
    text = str(value).strip().lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _normalized_timestamp_text(value: object) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise AnnotationRasterizationError("source_timestamp must be ISO-8601.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AnnotationRasterizationError("source_timestamp must include a timezone.")
    return _iso_utc(parsed)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
