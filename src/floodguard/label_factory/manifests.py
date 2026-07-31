"""Canonical tile/query manifest construction and leakage validation.

Only immutable projected-grid cores are built here.  These records may support
a human review queue; their safety fields categorically prohibit use in the
FloodGuard decision layer, FPPS, or warnings.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from numbers import Integral, Real
from pathlib import Path
import math
import re
from typing import TypeAlias

import pandas as pd

from floodguard.label_factory.contracts import DatasetRole
from floodguard.label_factory.event_registry import (
    CONFIDENCE_CLASSES,
    EventRecord,
    EventRegistryError,
    SourceAssetRecord,
    TabularInput,
    format_utc_datetime,
    load_events,
    load_source_assets,
    parse_utc_datetime,
    strict_bool,
    validate_event_source_registry,
)
from floodguard.label_factory.feature_schema import (
    FeatureSchemaError,
    get_feature_schema,
)
from floodguard.label_factory.processing_alignment import (
    ProcessingAlignmentError,
    ReceiptInput,
    require_processed_coverage_for_tiles,
    validate_processing_alignment_receipt,
)
from floodguard.label_factory.tiling import (
    GridContractError,
    QueryCore,
    TileCore,
    validate_non_overlapping_cores,
)


class ManifestContractError(ValueError):
    """Raised when tile/query manifests violate grid or role isolation."""


TILE_ASSIGNMENT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "event_id",
    "x_index",
    "y_index",
    "dataset_role",
    "overlap_group_id",
    "valid_data_fraction",
    "feature_schema_version",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

TILE_MANIFEST_COLUMNS: tuple[str, ...] = (
    "tile_id",
    "event_id",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "processing_alignment_receipt_sha256",
    "pre_source_asset_ids",
    "event_source_asset_ids",
    "pre_product_ids",
    "event_product_ids",
    "pre_acquisition_utc",
    "event_acquisition_utc",
    "pre_source_sha256s",
    "event_source_sha256s",
    "x_index",
    "y_index",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
    "crs",
    "resolution_m",
    "grid_origin_x",
    "grid_origin_y",
    "width_pixels",
    "height_pixels",
    "query_size_pixels",
    "valid_data_fraction",
    "overlap_group_id",
    "dataset_role",
    "feature_schema_version",
    "eligible_for_human_annotation",
    "eligible_for_active_selection",
    "eligible_for_review_queue",
    "eligible_for_query_model_training",
    "query_model_only",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

QUERY_MANIFEST_COLUMNS: tuple[str, ...] = (
    "query_region_id",
    "tile_id",
    "event_id",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "processing_alignment_receipt_sha256",
    "pre_source_asset_ids",
    "event_source_asset_ids",
    "pre_product_ids",
    "event_product_ids",
    "pre_acquisition_utc",
    "event_acquisition_utc",
    "pre_source_sha256s",
    "event_source_sha256s",
    "query_row",
    "query_col",
    "query_size_pixels",
    "resolution_m",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
    "crs",
    "dataset_role",
    "overlap_group_id",
    "feature_schema_version",
    "review_status",
    "selected",
    "eligible_for_human_annotation",
    "eligible_for_active_selection",
    "eligible_for_review_queue",
    "eligible_for_query_model_training",
    "eligible_for_training_after_human_review",
    "query_model_only",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

# These columns appear only when the caller explicitly supplies a verified
# supported-query derivation.  Keeping them out of the baseline constants
# preserves byte/schema compatibility for existing whole-tile callers.
SUPPORTED_QUERY_LINEAGE_COLUMNS: tuple[str, ...] = (
    "supported_query_allowlist_applied",
    "supported_query_derivation_sha256",
    "supported_query_csv_sha256",
)
SUPPORTED_TILE_LINEAGE_COLUMNS: tuple[str, ...] = (
    *SUPPORTED_QUERY_LINEAGE_COLUMNS,
    "allowlisted_query_count",
)

_GROUP_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
ManifestInput: TypeAlias = TabularInput


@dataclass(frozen=True)
class TileAssignment:
    """One explicit spatial-block role assignment on an event grid."""

    event_id: str
    x_index: int
    y_index: int
    dataset_role: DatasetRole
    overlap_group_id: str
    valid_data_fraction: float
    feature_schema_version: str
    source_timestamp: object
    confidence_class: str
    assumptions: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> TileAssignment:
        """Validate one mapping used to instantiate a storage tile."""

        _require_mapping_columns(
            row, TILE_ASSIGNMENT_REQUIRED_COLUMNS, "tile assignment"
        )
        event_id = _required_text(row["event_id"], "event_id")
        role = _dataset_role(row["dataset_role"])
        overlap_group_id = _required_text(
            row["overlap_group_id"], "overlap_group_id"
        )
        if _GROUP_ID_PATTERN.fullmatch(overlap_group_id) is None:
            raise ManifestContractError(
                "overlap_group_id must use letters, digits, dot, underscore, "
                "colon, or hyphen."
            )
        valid_fraction = _finite_float(
            row["valid_data_fraction"], "valid_data_fraction"
        )
        if not 0 < valid_fraction <= 1:
            raise ManifestContractError(
                "valid_data_fraction must be greater than 0 and at most 1."
            )
        feature_version = _required_text(
            row["feature_schema_version"], "feature_schema_version"
        )
        try:
            schema = get_feature_schema(feature_version)
        except FeatureSchemaError as exc:
            raise ManifestContractError(str(exc)) from exc
        if schema.version != "sar_change_v2":
            raise ManifestContractError(
                "Canonical label-factory grids require feature_schema_version="
                "sar_change_v2; legacy schemas remain reproduction-only."
            )
        timestamp = parse_utc_datetime(row["source_timestamp"], "source_timestamp")
        confidence = _required_text(
            row["confidence_class"], "confidence_class"
        ).lower()
        if confidence not in CONFIDENCE_CLASSES:
            raise ManifestContractError(
                "confidence_class must be high, medium, or low."
            )
        return cls(
            event_id=event_id,
            x_index=_integer(row["x_index"], "x_index"),
            y_index=_integer(row["y_index"], "y_index"),
            dataset_role=role,
            overlap_group_id=overlap_group_id,
            valid_data_fraction=valid_fraction,
            feature_schema_version=feature_version,
            source_timestamp=timestamp,
            confidence_class=confidence,
            assumptions=_required_text(row["assumptions"], "assumptions"),
        )


@dataclass(frozen=True)
class GridManifests:
    """A validated pair of deterministic tile and query-region DataFrames."""

    tiles: pd.DataFrame
    query_regions: pd.DataFrame


@dataclass(frozen=True)
class _SupportedQueryAllowlist:
    """Receipt-bound query allowlist loaded from one self-hashed derivation."""

    rows_by_query_id: Mapping[str, Mapping[str, object]]
    query_ids_by_tile_id: Mapping[str, frozenset[str]]
    derivation_sha256: str
    query_csv_sha256: str


def load_tile_assignments(
    source: ManifestInput,
    *,
    supported_query_derivation_provided: bool = False,
) -> tuple[TileAssignment, ...]:
    """Load tile assignments from mappings, a DataFrame, or a CSV."""

    frame = load_manifest_frame(source, "tile assignments")
    _require_frame_columns(
        frame, TILE_ASSIGNMENT_REQUIRED_COLUMNS, "tile assignments"
    )
    if "supported_query_allowlist_required" in frame.columns:
        try:
            allowlist_required = tuple(
                strict_bool(value, "supported_query_allowlist_required")
                for value in frame["supported_query_allowlist_required"]
            )
        except EventRegistryError as exc:
            raise ManifestContractError(str(exc)) from exc
        if any(allowlist_required) and not supported_query_derivation_provided:
            raise ManifestContractError(
                "These provisional tile assignments require "
                "supported_query_derivation; refusing to emit unsupported child "
                "cores under the historical whole-tile contract."
            )
    records = tuple(
        TileAssignment.from_mapping(row) for row in frame.to_dict("records")
    )
    if not records:
        raise ManifestContractError(
            "tile assignments must contain at least one row."
        )
    return records


def build_grid_manifests(
    events: Sequence[EventRecord] | ManifestInput,
    tile_assignments: Sequence[TileAssignment] | ManifestInput,
    source_assets: Sequence[SourceAssetRecord] | ManifestInput,
    processing_alignment_receipt: ReceiptInput,
    *,
    governance_package: str | Path | None = None,
    allow_ungoverned_fixture: bool = False,
    supported_query_derivation: str | Path | None = None,
) -> GridManifests:
    """Build stable, non-overlapping tile and query manifests.

    Without ``supported_query_derivation`` the historical whole-tile contract
    is unchanged: every lattice query inside every assigned tile is emitted.
    With it, source-rights and processing-receipt validation still run first,
    parent tiles remain as lineage containers, and only receipt-bound,
    fully-supported/AOI-contained allowlisted query cores are emitted.
    """

    event_records = _coerce_events(events)
    source_records = _coerce_sources(source_assets)
    try:
        validate_event_source_registry(event_records, source_records)
        processing_receipt = validate_processing_alignment_receipt(
            processing_alignment_receipt,
            event_records,
            source_records,
            governance_package=governance_package,
            allow_ungoverned_fixture=allow_ungoverned_fixture,
        )
    except (EventRegistryError, ProcessingAlignmentError) as exc:
        raise ManifestContractError(str(exc)) from exc
    assignment_records = _coerce_assignments(
        tile_assignments,
        supported_query_derivation_provided=(
            supported_query_derivation is not None
        ),
    )
    event_by_id = {event.event_id: event for event in event_records}
    if len(event_by_id) != len(event_records):
        raise ManifestContractError("events contains duplicate event_id values.")

    source_lineage_by_event = {
        event.event_id: _event_source_lineage(event, source_records)
        for event in event_records
    }
    tiles_with_metadata: list[tuple[TileCore, TileAssignment, EventRecord]] = []
    for assignment in assignment_records:
        event = event_by_id.get(assignment.event_id)
        if event is None:
            raise ManifestContractError(
                f"Tile assignment references unknown event {assignment.event_id!r}."
            )
        _validate_tile_role(event, assignment.dataset_role)
        if assignment.source_timestamp < event.source_timestamp:
            raise ManifestContractError(
                f"Tile ({assignment.x_index}, {assignment.y_index}) source_timestamp "
                f"predates event registry metadata for {event.event_id}."
            )
        try:
            tile = TileCore(
                event_id=event.event_id,
                grid=event.grid,
                x_index=assignment.x_index,
                y_index=assignment.y_index,
                dataset_role=assignment.dataset_role,
            )
        except GridContractError as exc:
            raise ManifestContractError(str(exc)) from exc
        tiles_with_metadata.append((tile, assignment, event))

    try:
        validate_non_overlapping_cores(
            [tile for tile, _, _ in tiles_with_metadata]
        )
    except GridContractError as exc:
        raise ManifestContractError(str(exc)) from exc
    _validate_overlap_group_roles(
        (
            assignment.overlap_group_id,
            assignment.dataset_role,
        )
        for _, assignment, _ in tiles_with_metadata
    )
    _validate_feature_schema_consistency(assignment_records)

    ordered = sorted(
        tiles_with_metadata,
        key=lambda item: (
            item[0].event_id,
            item[0].y_index,
            item[0].x_index,
        ),
    )
    base_tile_rows = [
        _tile_row(
            tile,
            assignment,
            event,
            source_lineage_by_event[event.event_id],
            processing_receipt_sha256=processing_receipt["receipt_sha256"],
        )
        for tile, assignment, event in ordered
    ]
    base_tiles = pd.DataFrame(base_tile_rows, columns=TILE_MANIFEST_COLUMNS)
    try:
        require_processed_coverage_for_tiles(processing_receipt, base_tiles)
    except ProcessingAlignmentError as exc:
        raise ManifestContractError(str(exc)) from exc
    allowlist = (
        _load_supported_query_allowlist(
            supported_query_derivation,
            event_records=event_records,
            source_records=source_records,
            processing_receipt=processing_receipt,
            tiles_with_metadata=ordered,
        )
        if supported_query_derivation is not None
        else None
    )
    tile_rows: list[dict[str, object]] = []
    query_rows: list[dict[str, object]] = []
    all_queries: list[QueryCore] = []
    for (tile, assignment, event), base_tile_row in zip(
        ordered, base_tile_rows, strict=True
    ):
        source_lineage = source_lineage_by_event[event.event_id]
        tile_row = dict(base_tile_row)
        if allowlist is not None:
            tile_query_ids = allowlist.query_ids_by_tile_id.get(
                tile.tile_id, frozenset()
            )
            tile_row.update(
                _supported_query_lineage_fields(allowlist),
                allowlisted_query_count=len(tile_query_ids),
            )
        tile_rows.append(tile_row)
        query_count = event.tile_size_pixels // event.query_size_pixels
        for row_index in range(query_count):
            for column_index in range(query_count):
                try:
                    query = QueryCore(
                        tile=tile,
                        row_index=row_index,
                        column_index=column_index,
                        size_cells=event.query_size_pixels,
                    )
                except GridContractError as exc:
                    raise ManifestContractError(str(exc)) from exc
                if (
                    allowlist is not None
                    and query.query_region_id not in allowlist.rows_by_query_id
                ):
                    continue
                all_queries.append(query)
                query_row = _query_row(
                    query,
                    assignment,
                    source_lineage,
                    processing_receipt_sha256=processing_receipt["receipt_sha256"],
                )
                if allowlist is not None:
                    query_row.update(_supported_query_lineage_fields(allowlist))
                query_rows.append(query_row)
    try:
        validate_non_overlapping_cores(all_queries)
    except GridContractError as exc:
        raise ManifestContractError(str(exc)) from exc

    tile_columns = (
        (*TILE_MANIFEST_COLUMNS, *SUPPORTED_TILE_LINEAGE_COLUMNS)
        if allowlist is not None
        else TILE_MANIFEST_COLUMNS
    )
    query_columns = (
        (*QUERY_MANIFEST_COLUMNS, *SUPPORTED_QUERY_LINEAGE_COLUMNS)
        if allowlist is not None
        else QUERY_MANIFEST_COLUMNS
    )
    tiles = pd.DataFrame(tile_rows, columns=tile_columns)
    queries = pd.DataFrame(query_rows, columns=query_columns)
    return GridManifests(tiles=tiles, query_regions=queries)


def validate_grid_manifests(
    events: Sequence[EventRecord] | ManifestInput,
    source_assets: Sequence[SourceAssetRecord] | ManifestInput,
    tile_manifest: ManifestInput,
    query_manifest: ManifestInput,
    processing_alignment_receipt: ReceiptInput,
    *,
    governance_package: str | Path | None = None,
    allow_ungoverned_fixture: bool = False,
    supported_query_derivation: str | Path | None = None,
) -> GridManifests:
    """Rebuild expected records and reject altered, missing, or leaked rows."""

    event_records = _coerce_events(events)
    source_records = _coerce_sources(source_assets)
    actual_tiles = load_manifest_frame(tile_manifest, "tile manifest")
    actual_queries = load_manifest_frame(query_manifest, "query manifest")
    _require_frame_columns(actual_tiles, TILE_MANIFEST_COLUMNS, "tile manifest")
    _require_frame_columns(
        actual_queries, QUERY_MANIFEST_COLUMNS, "query manifest"
    )
    if supported_query_derivation is None and (
        any(column in actual_tiles for column in SUPPORTED_TILE_LINEAGE_COLUMNS)
        or any(
            column in actual_queries for column in SUPPORTED_QUERY_LINEAGE_COLUMNS
        )
    ):
        raise ManifestContractError(
            "Allowlist lineage columns require supported_query_derivation during "
            "validation."
        )
    if supported_query_derivation is not None:
        _require_frame_columns(
            actual_tiles,
            SUPPORTED_TILE_LINEAGE_COLUMNS,
            "allowlisted tile manifest",
        )
        _require_frame_columns(
            actual_queries,
            SUPPORTED_QUERY_LINEAGE_COLUMNS,
            "allowlisted query manifest",
        )
    expected = build_grid_manifests(
        event_records,
        actual_tiles,
        source_records,
        processing_alignment_receipt,
        governance_package=governance_package,
        allow_ungoverned_fixture=allow_ungoverned_fixture,
        supported_query_derivation=supported_query_derivation,
    )
    _compare_manifest(
        actual_tiles,
        expected.tiles,
        key="tile_id",
        columns=(
            (*TILE_MANIFEST_COLUMNS, *SUPPORTED_TILE_LINEAGE_COLUMNS)
            if supported_query_derivation is not None
            else TILE_MANIFEST_COLUMNS
        ),
        label="tile manifest",
    )
    _compare_manifest(
        actual_queries,
        expected.query_regions,
        key="query_region_id",
        columns=(
            (*QUERY_MANIFEST_COLUMNS, *SUPPORTED_QUERY_LINEAGE_COLUMNS)
            if supported_query_derivation is not None
            else QUERY_MANIFEST_COLUMNS
        ),
        label="query manifest",
    )
    _validate_overlap_group_roles(
        (
            _required_text(row["overlap_group_id"], "overlap_group_id"),
            _dataset_role(row["dataset_role"]),
        )
        for row in actual_queries.to_dict("records")
    )
    _validate_geographic_test_isolation(actual_queries)
    return expected


def load_manifest_frame(source: ManifestInput, label: str) -> pd.DataFrame:
    """Read a manifest-like source while converting failures to one error type."""

    if isinstance(source, pd.DataFrame):
        return source.copy()
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix.lower() != ".csv":
            raise ManifestContractError(f"{label} input must be a CSV file.")
        if not path.is_file():
            raise ManifestContractError(f"{label} CSV does not exist: {path}")
        try:
            return pd.read_csv(path)
        except (OSError, pd.errors.ParserError, UnicodeError) as exc:
            raise ManifestContractError(f"Could not read {label} CSV: {exc}") from exc
    if isinstance(source, Mapping):
        return pd.DataFrame([dict(source)])
    try:
        return pd.DataFrame(list(source))
    except (TypeError, ValueError) as exc:
        raise ManifestContractError(f"Could not convert {label} input to rows.") from exc


def _tile_row(
    tile: TileCore,
    assignment: TileAssignment,
    event: EventRecord,
    source_lineage: Mapping[str, object],
    *,
    processing_receipt_sha256: str,
) -> dict[str, object]:
    bounds = tile.bounds
    can_query = tile.dataset_role is DatasetRole.TRAINING_AND_QUERY_POOL
    return {
        "tile_id": tile.tile_id,
        "event_id": tile.event_id,
        "grid_id": tile.grid.grid_id,
        "grid_contract_sha256": tile.grid.contract_sha256,
        **source_lineage,
        "processing_alignment_receipt_sha256": processing_receipt_sha256,
        "x_index": tile.x_index,
        "y_index": tile.y_index,
        "bbox_min_x": bounds.min_x,
        "bbox_min_y": bounds.min_y,
        "bbox_max_x": bounds.max_x,
        "bbox_max_y": bounds.max_y,
        "crs": tile.grid.crs,
        "resolution_m": tile.grid.resolution_m,
        "grid_origin_x": tile.grid.origin_x,
        "grid_origin_y": tile.grid.origin_y,
        "width_pixels": tile.grid.tile_size_cells,
        "height_pixels": tile.grid.tile_size_cells,
        "query_size_pixels": event.query_size_pixels,
        "valid_data_fraction": assignment.valid_data_fraction,
        "overlap_group_id": assignment.overlap_group_id,
        "dataset_role": tile.dataset_role.value,
        "feature_schema_version": assignment.feature_schema_version,
        "eligible_for_human_annotation": True,
        "eligible_for_active_selection": can_query,
        "eligible_for_review_queue": can_query,
        "eligible_for_query_model_training": False,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "source_timestamp": format_utc_datetime(assignment.source_timestamp),
        "confidence_class": assignment.confidence_class,
        "assumptions": assignment.assumptions,
    }


def _query_row(
    query: QueryCore,
    assignment: TileAssignment,
    source_lineage: Mapping[str, object],
    *,
    processing_receipt_sha256: str,
) -> dict[str, object]:
    bounds = query.bounds
    can_query = query.dataset_role is DatasetRole.TRAINING_AND_QUERY_POOL
    return {
        "query_region_id": query.query_region_id,
        "tile_id": query.tile.tile_id,
        "event_id": query.event_id,
        "grid_id": query.grid.grid_id,
        "grid_contract_sha256": query.grid.contract_sha256,
        **source_lineage,
        "processing_alignment_receipt_sha256": processing_receipt_sha256,
        "query_row": query.row_index,
        "query_col": query.column_index,
        "query_size_pixels": query.size_cells,
        "resolution_m": query.grid.resolution_m,
        "bbox_min_x": bounds.min_x,
        "bbox_min_y": bounds.min_y,
        "bbox_max_x": bounds.max_x,
        "bbox_max_y": bounds.max_y,
        "crs": query.grid.crs,
        "dataset_role": query.dataset_role.value,
        "overlap_group_id": assignment.overlap_group_id,
        "feature_schema_version": assignment.feature_schema_version,
        "review_status": "unreviewed",
        "selected": False,
        "eligible_for_human_annotation": True,
        "eligible_for_active_selection": can_query,
        "eligible_for_review_queue": can_query,
        "eligible_for_query_model_training": False,
        "eligible_for_training_after_human_review": (
            "conditional" if can_query else "no"
        ),
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "source_timestamp": format_utc_datetime(assignment.source_timestamp),
        "confidence_class": assignment.confidence_class,
        "assumptions": assignment.assumptions,
    }


_SUPPORTED_QUERY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "query_region_id",
    "tile_id",
    "event_id",
    "grid_id",
    "grid_contract_sha256",
    "query_row",
    "query_col",
    "query_size_pixels",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
    "wgs84_min_longitude",
    "wgs84_min_latitude",
    "wgs84_max_longitude",
    "wgs84_max_latitude",
    "crs",
    "resolution_m",
    "dataset_role",
    "feature_schema_version",
    "joint_valid_cell_count",
    "query_cell_count",
    "valid_data_fraction",
    "fully_within_approved_aoi",
    "core_clipped",
    "provisional_support_evidence",
    "processing_alignment_receipt_validated",
    "source_rights_gate_validated",
    "canonical_manifest_status",
    "eligible_for_human_annotation",
    "eligible_for_active_selection",
    "eligible_for_review_queue",
    "eligible_for_query_model_training",
    "query_model_only",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
    "eligible_for_supported_query_allowlist_bridge",
)


def _load_supported_query_allowlist(
    derivation_path: str | Path,
    *,
    event_records: Sequence[EventRecord],
    source_records: Sequence[SourceAssetRecord],
    processing_receipt: Mapping[str, object],
    tiles_with_metadata: Sequence[tuple[TileCore, TileAssignment, EventRecord]],
) -> _SupportedQueryAllowlist:
    """Verify one provisional derivation against receipt-bound canonical inputs."""

    # Import lazily so existing non-geospatial/whole-tile callers do not gain a
    # NumPy/raster dependency merely by importing this manifest module.
    try:
        from floodguard.label_factory.supported_query_pool import (
            ApprovedAoiWgs84,
            SupportedQueryPoolError,
            _bounds_within_aoi,
            _require_rasterio,
            load_supported_query_derivation,
        )

        path = Path(derivation_path)
        manifest = load_supported_query_derivation(path, verify_outputs=True)
    except (SupportedQueryPoolError, OSError) as exc:
        raise ManifestContractError(str(exc)) from exc

    raw_event = manifest.get("event")
    if manifest.get("builder") != "floodguard.label_factory.supported_query_pool@v1":
        raise ManifestContractError("Unsupported supported-query derivation builder.")
    if not isinstance(raw_event, Mapping):
        raise ManifestContractError("Supported-query derivation has no event binding.")
    target_event_id = _required_text(raw_event.get("event_id"), "event.event_id")
    event_by_id = {event.event_id: event for event in event_records}
    event = event_by_id.get(target_event_id)
    if event is None:
        raise ManifestContractError(
            f"Supported-query derivation references unknown event {target_event_id!r}."
        )
    assigned_event_ids = {tile.event_id for tile, _, _ in tiles_with_metadata}
    if assigned_event_ids != {target_event_id}:
        raise ManifestContractError(
            "Allowlist mode requires every assigned tile to belong to the one "
            "event bound by the supported-query derivation."
        )
    expected_event_fields: dict[str, object] = {
        "dataset_role": event.dataset_role.value,
        "analysis_crs": event.analysis_crs,
        "analysis_resolution_m": event.analysis_resolution_m,
        "grid_origin_x": event.grid_origin_x,
        "grid_origin_y": event.grid_origin_y,
        "tile_size_pixels": event.tile_size_pixels,
        "query_size_pixels": event.query_size_pixels,
        "grid_id": event.grid.grid_id,
        "grid_contract_sha256": event.grid.contract_sha256,
    }
    for field, expected in expected_event_fields.items():
        actual = raw_event.get(field)
        if not _scalar_equal(actual, expected):
            raise ManifestContractError(
                f"Supported-query derivation event field {field} does not match "
                "the canonical event registry."
            )

    _require_allowlist_receipt_binding(
        manifest,
        event=event,
        source_records=source_records,
        processing_receipt=processing_receipt,
    )
    raw_outputs = manifest.get("outputs")
    if not isinstance(raw_outputs, Mapping):
        raise ManifestContractError("Supported-query derivation outputs are missing.")
    raw_query_output = raw_outputs.get("supported_queries")
    if not isinstance(raw_query_output, Mapping):
        raise ManifestContractError(
            "Supported-query derivation has no supported_queries output."
        )
    file_name = _required_text(
        raw_query_output.get("file_name"), "supported_queries.file_name"
    )
    if Path(file_name).name != file_name:
        raise ManifestContractError(
            "Supported-query output must resolve beside its derivation manifest."
        )
    query_csv_sha256 = _required_sha256(
        raw_query_output.get("sha256"), "supported_queries.sha256"
    )
    query_path = path.parent / file_name
    try:
        frame = pd.read_csv(query_path)
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        raise ManifestContractError(
            f"Could not read supported-query CSV: {query_path}"
        ) from exc
    _require_frame_columns(
        frame, _SUPPORTED_QUERY_REQUIRED_COLUMNS, "supported-query allowlist"
    )
    if frame.empty:
        raise ManifestContractError("Supported-query allowlist must not be empty.")
    declared_rows = _integer(raw_query_output.get("row_count"), "row_count")
    if declared_rows != len(frame):
        raise ManifestContractError(
            "Supported-query allowlist row count differs from its derivation."
        )
    counts = manifest.get("counts")
    if not isinstance(counts, Mapping) or _integer(
        counts.get("fully_supported_aoi_contained_query_cores"),
        "fully_supported_aoi_contained_query_cores",
    ) != len(frame):
        raise ManifestContractError(
            "Supported-query derivation count does not match its query allowlist."
        )
    if frame["query_region_id"].astype(str).duplicated().any():
        raise ManifestContractError(
            "Supported-query allowlist contains duplicate query_region_id values."
        )
    duplicate_lattice = frame.duplicated(
        subset=["tile_id", "query_row", "query_col", "query_size_pixels"]
    )
    if duplicate_lattice.any():
        raise ManifestContractError(
            "Supported-query allowlist contains duplicate child-core geometry."
        )

    raw_aoi = manifest.get("approved_aoi_wgs84")
    if not isinstance(raw_aoi, Mapping) or raw_aoi.get("crs") != "EPSG:4326":
        raise ManifestContractError(
            "Supported-query derivation has no explicit EPSG:4326 AOI."
        )
    aoi = tuple(
        _finite_float(raw_aoi.get(field), f"approved_aoi_wgs84.{field}")
        for field in (
            "min_longitude",
            "min_latitude",
            "max_longitude",
            "max_latitude",
        )
    )
    if not aoi[0] < aoi[2] or not aoi[1] < aoi[3]:
        raise ManifestContractError("Supported-query derivation AOI is invalid.")
    cross_border_context_included = raw_aoi.get("cross_border_context_included")
    if not isinstance(cross_border_context_included, bool):
        raise ManifestContractError(
            "approved_aoi_wgs84.cross_border_context_included must be an "
            "explicit JSON boolean."
        )
    try:
        approved_aoi = ApprovedAoiWgs84(
            min_longitude=aoi[0],
            min_latitude=aoi[1],
            max_longitude=aoi[2],
            max_latitude=aoi[3],
            cross_border_context_included=cross_border_context_included,
        )
        rasterio = _require_rasterio()
    except SupportedQueryPoolError as exc:
        raise ManifestContractError(str(exc)) from exc

    tile_by_id = {tile.tile_id: tile for tile, _, _ in tiles_with_metadata}
    rows_by_id: dict[str, Mapping[str, object]] = {}
    ids_by_tile: dict[str, set[str]] = {}
    tolerance = event.analysis_resolution_m * 1e-9
    for row_number, row in enumerate(frame.to_dict("records")):
        query_id = _required_text(row["query_region_id"], "query_region_id")
        tile_id = _required_text(row["tile_id"], "tile_id")
        tile = tile_by_id.get(tile_id)
        if tile is None:
            raise ManifestContractError(
                f"Supported query {query_id!r} is not a child of an assigned tile."
            )
        row_index = _integer(row["query_row"], "query_row")
        column_index = _integer(row["query_col"], "query_col")
        size = _integer(row["query_size_pixels"], "query_size_pixels")
        try:
            query = QueryCore(
                tile=tile,
                row_index=row_index,
                column_index=column_index,
                size_cells=size,
            )
        except GridContractError as exc:
            raise ManifestContractError(str(exc)) from exc
        if query.query_region_id != query_id:
            raise ManifestContractError(
                f"Supported query {query_id!r} does not match its canonical child ID."
            )
        scalar_expectations: dict[str, object] = {
            "event_id": event.event_id,
            "grid_id": event.grid.grid_id,
            "grid_contract_sha256": event.grid.contract_sha256,
            "query_size_pixels": event.query_size_pixels,
            "crs": event.analysis_crs,
            "resolution_m": event.analysis_resolution_m,
            # This is the event role at derivation time. The tile assignment may
            # legitimately reserve a subset as reviewer_calibration later.
            "dataset_role": event.dataset_role.value,
            "feature_schema_version": "sar_change_v2",
            "joint_valid_cell_count": size * size,
            "query_cell_count": size * size,
            "valid_data_fraction": 1.0,
            "fully_within_approved_aoi": True,
            "core_clipped": False,
            "provisional_support_evidence": True,
            "processing_alignment_receipt_validated": False,
            "source_rights_gate_validated": False,
            "canonical_manifest_status": (
                "not_canonical_provisional_support_only"
            ),
            "eligible_for_human_annotation": False,
            "eligible_for_active_selection": False,
            "eligible_for_review_queue": False,
            "eligible_for_query_model_training": False,
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "eligible_for_supported_query_allowlist_bridge": True,
        }
        for field, expected in scalar_expectations.items():
            if not _scalar_equal(row[field], expected):
                raise ManifestContractError(
                    f"Supported query {query_id!r} has invalid {field}."
                )
        bounds_expectations = {
            "bbox_min_x": query.bounds.min_x,
            "bbox_min_y": query.bounds.min_y,
            "bbox_max_x": query.bounds.max_x,
            "bbox_max_y": query.bounds.max_y,
        }
        for field, expected in bounds_expectations.items():
            actual = _finite_float(row[field], field)
            if not math.isclose(actual, expected, abs_tol=tolerance):
                raise ManifestContractError(
                    f"Supported query {query_id!r} has non-canonical {field}."
                )
        wgs84 = tuple(
            _finite_float(row[field], field)
            for field in (
                "wgs84_min_longitude",
                "wgs84_min_latitude",
                "wgs84_max_longitude",
                "wgs84_max_latitude",
            )
        )
        canonical_contained, canonical_wgs84 = _bounds_within_aoi(
            query.bounds,
            crs=event.analysis_crs,
            resolution_m=event.analysis_resolution_m,
            approved_aoi=approved_aoi,
            rasterio=rasterio,
        )
        if not canonical_contained:
            raise ManifestContractError(
                f"Supported query {query_id!r} is not contained by the bound AOI."
            )
        for actual, expected, field in zip(
            wgs84,
            canonical_wgs84,
            (
                "wgs84_min_longitude",
                "wgs84_min_latitude",
                "wgs84_max_longitude",
                "wgs84_max_latitude",
            ),
            strict=True,
        ):
            if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-10):
                raise ManifestContractError(
                    f"Supported query {query_id!r} has non-canonical {field}."
                )
        rows_by_id[query_id] = row
        ids_by_tile.setdefault(tile_id, set()).add(query_id)

    missing_parent_queries = sorted(set(tile_by_id) - set(ids_by_tile))
    if missing_parent_queries:
        raise ManifestContractError(
            "Every assigned parent tile must have at least one supported query; "
            f"missing for {missing_parent_queries[:3]}."
        )
    return _SupportedQueryAllowlist(
        rows_by_query_id=rows_by_id,
        query_ids_by_tile_id={
            tile_id: frozenset(query_ids)
            for tile_id, query_ids in ids_by_tile.items()
        },
        derivation_sha256=_required_sha256(
            manifest.get("manifest_sha256"), "manifest_sha256"
        ),
        query_csv_sha256=query_csv_sha256,
    )


def _require_allowlist_receipt_binding(
    manifest: Mapping[str, object],
    *,
    event: EventRecord,
    source_records: Sequence[SourceAssetRecord],
    processing_receipt: Mapping[str, object],
) -> None:
    """Bind the four derivation rasters to the four validated receipt assets."""

    raw_inputs = manifest.get("input_files")
    if not isinstance(raw_inputs, Mapping):
        raise ManifestContractError("Supported-query derivation input hashes are missing.")
    raw_sar_support = manifest.get("sar_support")
    raw_source_evidence = (
        raw_sar_support.get("source_evidence")
        if isinstance(raw_sar_support, Mapping)
        else None
    )
    if not isinstance(raw_source_evidence, Mapping):
        raise ManifestContractError(
            "Supported-query derivation SAR source evidence is missing."
        )
    receipt_assets_raw = processing_receipt.get("assets")
    if not isinstance(receipt_assets_raw, list):
        raise ManifestContractError("Processing receipt assets are malformed.")
    receipt_by_id = {
        str(row.get("asset_id")): row
        for row in receipt_assets_raw
        if isinstance(row, Mapping)
    }
    bound_roles: dict[str, str] = {}
    for source in source_records:
        if source.event_id != event.event_id or source.event_relative_role == "static_context":
            continue
        polarization = source.polarizations.strip().upper()
        if polarization not in {"VV", "VH"}:
            raise ManifestContractError(
                "Allowlist receipt binding requires one logical VV or VH source "
                f"asset per processed band; {source.asset_id!r} declares "
                f"{source.polarizations!r}."
            )
        if source.event_relative_role == "pre_event":
            prefix = "pre"
        elif source.event_relative_role == "event_time":
            prefix = "event"
        else:
            raise ManifestContractError(
                f"Unsupported event_relative_role for {source.asset_id!r}."
            )
        role = f"{prefix}_{polarization.lower()}_db"
        if role in bound_roles:
            raise ManifestContractError(
                f"More than one source asset maps to allowlist raster role {role}."
            )
        receipt_row = receipt_by_id.get(source.asset_id)
        if receipt_row is None:
            raise ManifestContractError(
                f"Processing receipt lacks allowlist source asset {source.asset_id!r}."
            )
        raw_input = raw_inputs.get(role)
        if not isinstance(raw_input, Mapping):
            raise ManifestContractError(
                f"Supported-query derivation lacks input raster role {role}."
            )
        derivation_hash = _required_sha256(raw_input.get("sha256"), f"{role}.sha256")
        receipt_hash = _required_sha256(
            receipt_row.get("processed_file_sha256"),
            f"receipt.{source.asset_id}.processed_file_sha256",
        )
        if derivation_hash != receipt_hash:
            raise ManifestContractError(
                f"Supported-query raster {role} is not the processed file bound "
                "by the validated receipt."
            )
        role_evidence = raw_source_evidence.get(role)
        if (
            not isinstance(role_evidence, Mapping)
            or _required_text(
                role_evidence.get("source_product_id"),
                f"sar_support.{role}.source_product_id",
            )
            != source.product_id
        ):
            raise ManifestContractError(
                f"Supported-query raster {role} product ID does not match the "
                "source registry."
            )
        bound_roles[role] = source.asset_id
    expected_roles = {"pre_vv_db", "pre_vh_db", "event_vv_db", "event_vh_db"}
    if set(bound_roles) != expected_roles:
        raise ManifestContractError(
            "Allowlist receipt binding requires exactly pre/event VV/VH processed assets."
        )


def _supported_query_lineage_fields(
    allowlist: _SupportedQueryAllowlist,
) -> dict[str, object]:
    return {
        "supported_query_allowlist_applied": True,
        "supported_query_derivation_sha256": allowlist.derivation_sha256,
        "supported_query_csv_sha256": allowlist.query_csv_sha256,
    }


def _required_sha256(value: object, field_name: str) -> str:
    text = _required_text(value, field_name).lower()
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise ManifestContractError(f"{field_name} must be a lowercase SHA-256.")
    return text


def _coerce_events(
    events: Sequence[EventRecord] | ManifestInput,
) -> tuple[EventRecord, ...]:
    if isinstance(events, Sequence) and not isinstance(
        events, (str, bytes, pd.DataFrame)
    ) and all(isinstance(event, EventRecord) for event in events):
        records = tuple(events)
        if not records:
            raise ManifestContractError("events must contain at least one row.")
        return records
    try:
        return load_events(events)  # type: ignore[arg-type]
    except EventRegistryError as exc:
        raise ManifestContractError(str(exc)) from exc


def _coerce_sources(
    source_assets: Sequence[SourceAssetRecord] | ManifestInput,
) -> tuple[SourceAssetRecord, ...]:
    if isinstance(source_assets, Sequence) and not isinstance(
        source_assets, (str, bytes, pd.DataFrame)
    ) and all(isinstance(asset, SourceAssetRecord) for asset in source_assets):
        records = tuple(source_assets)
        if not records:
            raise ManifestContractError("source_assets must contain at least one row.")
        return records
    try:
        return load_source_assets(source_assets)  # type: ignore[arg-type]
    except EventRegistryError as exc:
        raise ManifestContractError(str(exc)) from exc


def _event_source_lineage(
    event: EventRecord,
    source_assets: Sequence[SourceAssetRecord],
) -> dict[str, object]:
    event_assets = sorted(
        (asset for asset in source_assets if asset.event_id == event.event_id),
        key=lambda asset: asset.asset_id,
    )
    pre_assets = [
        asset
        for asset in event_assets
        if asset.event_relative_role != "static_context"
        and asset.acquisition_time_utc == event.pre_acquisition_utc
    ]
    event_time_assets = [
        asset
        for asset in event_assets
        if asset.event_relative_role != "static_context"
        and asset.acquisition_time_utc == event.post_acquisition_utc
    ]
    if not pre_assets or not event_time_assets:
        raise ManifestContractError(
            f"Event {event.event_id!r} lacks its declared pre/event source pair."
        )
    encoded = json.dumps(
        [asset.as_manifest_row() for asset in event_assets],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {
        "source_registry_sha256": hashlib.sha256(encoded).hexdigest(),
        "pre_source_asset_ids": _joined_source_values(pre_assets, "asset_id"),
        "event_source_asset_ids": _joined_source_values(
            event_time_assets, "asset_id"
        ),
        "pre_product_ids": _joined_source_values(pre_assets, "product_id"),
        "event_product_ids": _joined_source_values(
            event_time_assets, "product_id"
        ),
        "pre_acquisition_utc": format_utc_datetime(event.pre_acquisition_utc),
        "event_acquisition_utc": format_utc_datetime(event.post_acquisition_utc),
        "pre_source_sha256s": _joined_source_values(pre_assets, "sha256"),
        "event_source_sha256s": _joined_source_values(
            event_time_assets, "sha256"
        ),
    }


def _joined_source_values(
    assets: Sequence[SourceAssetRecord], field_name: str
) -> str:
    values = sorted({str(getattr(asset, field_name)).strip() for asset in assets})
    if not values or any(not value for value in values):
        raise ManifestContractError(
            f"Source lineage field {field_name} must be complete."
        )
    return "|".join(values)


def _coerce_assignments(
    assignments: Sequence[TileAssignment] | ManifestInput,
    *,
    supported_query_derivation_provided: bool = False,
) -> tuple[TileAssignment, ...]:
    if isinstance(assignments, Sequence) and not isinstance(
        assignments, (str, bytes, pd.DataFrame)
    ) and all(isinstance(record, TileAssignment) for record in assignments):
        records = tuple(assignments)
        if not records:
            raise ManifestContractError(
                "tile assignments must contain at least one row."
            )
        return records
    return load_tile_assignments(
        assignments,  # type: ignore[arg-type]
        supported_query_derivation_provided=supported_query_derivation_provided,
    )


def _validate_tile_role(event: EventRecord, tile_role: DatasetRole) -> None:
    event_role = event.dataset_role
    if event_role is DatasetRole.UNTOUCHED_GEOGRAPHIC_TEST:
        if tile_role is not DatasetRole.UNTOUCHED_GEOGRAPHIC_TEST:
            raise ManifestContractError(
                f"Geographic-test event {event.event_id!r} cannot contain "
                f"{tile_role.value!r} tiles."
            )
        return
    if tile_role is DatasetRole.UNTOUCHED_GEOGRAPHIC_TEST:
        raise ManifestContractError(
            "An untouched_geographic_test tile requires an event registered "
            "entirely as untouched_geographic_test."
        )
    if (
        event_role is not DatasetRole.TRAINING_AND_QUERY_POOL
        and tile_role is not event_role
    ):
        raise ManifestContractError(
            f"Event {event.event_id!r} role {event_role.value!r} cannot be "
            f"escalated or reassigned to tile role {tile_role.value!r}."
        )


def _validate_overlap_group_roles(
    pairs: Iterable[tuple[str, DatasetRole]],
) -> None:
    group_roles: dict[str, DatasetRole] = {}
    for group_id, role in pairs:
        previous = group_roles.setdefault(group_id, role)
        if previous is not role:
            raise ManifestContractError(
                f"overlap_group_id {group_id!r} crosses dataset roles "
                f"{previous.value!r} and {role.value!r}."
            )


def _validate_feature_schema_consistency(
    assignments: Sequence[TileAssignment],
) -> None:
    versions = {assignment.feature_schema_version for assignment in assignments}
    if len(versions) != 1:
        raise ManifestContractError(
            "One grid-manifest build cannot mix feature_schema_version values."
        )


def _validate_geographic_test_isolation(query_frame: pd.DataFrame) -> None:
    for row in query_frame.to_dict("records"):
        role = _dataset_role(row["dataset_role"])
        if role is not DatasetRole.UNTOUCHED_GEOGRAPHIC_TEST:
            continue
        forbidden_true = [
            field
            for field in (
                "selected",
                "eligible_for_active_selection",
                "eligible_for_review_queue",
                "eligible_for_query_model_training",
            )
            if strict_bool(row[field], field)
        ]
        if forbidden_true:
            raise ManifestContractError(
                "untouched_geographic_test query "
                f"{row['query_region_id']!r} is active/training eligible via: "
                + ", ".join(forbidden_true)
                + "."
            )


def _compare_manifest(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
    *,
    key: str,
    columns: Sequence[str],
    label: str,
) -> None:
    if actual[key].duplicated().any():
        duplicate = str(actual.loc[actual[key].duplicated(), key].iloc[0])
        raise ManifestContractError(f"{label} has duplicate {key}: {duplicate!r}.")
    actual_by_key = {str(row[key]): row for row in actual.to_dict("records")}
    expected_by_key = {str(row[key]): row for row in expected.to_dict("records")}
    missing = sorted(set(expected_by_key) - set(actual_by_key))
    extra = sorted(set(actual_by_key) - set(expected_by_key))
    if missing or extra:
        raise ManifestContractError(
            f"{label} key set differs from canonical grid; missing={missing[:3]}, "
            f"extra={extra[:3]}."
        )
    for identifier, expected_row in expected_by_key.items():
        actual_row = actual_by_key[identifier]
        for column in columns:
            if not _scalar_equal(actual_row[column], expected_row[column]):
                raise ManifestContractError(
                    f"{label} row {identifier!r} has non-canonical {column}: "
                    f"{actual_row[column]!r}; expected {expected_row[column]!r}."
                )


def _scalar_equal(actual: object, expected: object) -> bool:
    if isinstance(expected, bool):
        try:
            return strict_bool(actual, "boolean manifest field") is expected
        except EventRegistryError:
            return False
    if isinstance(expected, int) and not isinstance(expected, bool):
        try:
            return _integer(actual, "integer manifest field") == expected
        except ManifestContractError:
            return False
    if isinstance(expected, float):
        try:
            parsed = _finite_float(actual, "numeric manifest field")
        except ManifestContractError:
            return False
        return math.isclose(parsed, expected, rel_tol=1e-12, abs_tol=1e-9)
    return str(actual).strip() == str(expected)


def _require_frame_columns(
    frame: pd.DataFrame, required: Sequence[str], label: str
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ManifestContractError(
            f"{label} is missing required columns: {', '.join(missing)}."
        )


def _require_mapping_columns(
    row: Mapping[str, object], required: Sequence[str], label: str
) -> None:
    missing = [column for column in required if column not in row]
    if missing:
        raise ManifestContractError(
            f"{label} row is missing required fields: {', '.join(missing)}."
        )


def _required_text(value: object, field_name: str) -> str:
    if value is None or pd.isna(value):
        raise ManifestContractError(f"{field_name} must not be blank.")
    text = str(value).strip()
    if not text:
        raise ManifestContractError(f"{field_name} must not be blank.")
    return text


def _dataset_role(value: object) -> DatasetRole:
    text = _required_text(value, "dataset_role")
    try:
        return DatasetRole(text)
    except ValueError as exc:
        raise ManifestContractError(
            "dataset_role must use one of: "
            + ", ".join(role.value for role in DatasetRole)
            + "."
        ) from exc


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or value is None or pd.isna(value):
        raise ManifestContractError(f"{field_name} must be an integer.")
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real) and float(value).is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ManifestContractError(f"{field_name} must be an integer.") from exc
    raise ManifestContractError(f"{field_name} must be an integer.")


def _finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or value is None or pd.isna(value):
        raise ManifestContractError(f"{field_name} must be a finite number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ManifestContractError(f"{field_name} must be a finite number.") from exc
    if not math.isfinite(parsed):
        raise ManifestContractError(f"{field_name} must be a finite number.")
    return parsed
