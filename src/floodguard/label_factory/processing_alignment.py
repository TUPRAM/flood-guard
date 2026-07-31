"""Evidence-backed SAR processing and common-grid alignment receipts.

The event/source registry declares what should exist.  This module records
what was actually processed and re-hashes the processed raster plus its
coverage, valid-data, and registration evidence before a canonical grid can
be built.  The receipt is self-hashed, immutable when written, and remains
categorically ineligible for FloodGuard's decision layer, FPPS, or warnings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, TypeAlias

import pandas as pd

from floodguard.label_factory.event_registry import (
    CONFIDENCE_CLASSES,
    MAX_GEOREGISTRATION_ERROR_PIXELS,
    EventRecord,
    EventRegistryError,
    SourceAssetRecord,
    format_utc_datetime,
    load_events,
    load_source_assets,
    parse_utc_datetime,
    strict_bool,
    validate_event_source_registry,
)
from floodguard.label_factory.rights_clearance import (
    RightsClearanceError,
    validate_cleared_registry_binding,
)
from floodguard.label_factory.tiling import (
    GridContractError,
    validate_projected_metre_crs,
)


PROCESSING_ALIGNMENT_RECEIPT_SCHEMA = (
    "floodguard.processing_alignment_receipt.v1"
)
PROCESSING_ALIGNMENT_VALIDATOR_ID = (
    "hash_processed_and_alignment_evidence+validate_common_grid@label_factory_v1"
)

PROCESSING_EVIDENCE_COLUMNS: tuple[str, ...] = (
    "asset_id",
    "processed_artifact_id",
    "processed_file_path",
    "processed_file_sha256",
    "processing_software",
    "processing_software_version",
    "rtc_terrain_correction_method",
    "output_crs",
    "affine_a",
    "affine_b",
    "affine_c",
    "affine_d",
    "affine_e",
    "affine_f",
    "width_pixels",
    "height_pixels",
    "pixel_size_x_m",
    "pixel_size_y_m",
    "nodata_convention",
    "resampling_method",
    "coverage_fraction",
    "valid_data_fraction",
    "coverage_evidence_path",
    "coverage_evidence_sha256",
    "valid_data_evidence_path",
    "valid_data_evidence_sha256",
    "registration_method",
    "registration_error_pixels",
    "registration_evidence_path",
    "registration_evidence_sha256",
    "grid_contract_sha256",
    "source_timestamp",
    "confidence_class",
    "assumptions",
    "query_model_only",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)

_RECEIPT_KEYS = frozenset(
    {
        "artifact_schema",
        "validator",
        "validated_at_utc",
        "event_registry_sha256",
        "source_registry_sha256",
        "processing_evidence_sha256",
        "event_count",
        "source_asset_count",
        "assets",
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "assumptions",
        "receipt_sha256",
    }
)

_ASSET_KEYS = frozenset(
    {
        "asset_id",
        "event_id",
        "source_sha256",
        "source_sha256_status",
        "product_id",
        "acquisition_time_utc",
        "event_relative_role",
        "source_license_status",
        "source_processing_allowed",
        "source_ml_label_derivation_allowed",
        "source_redistribution_status",
        "processed_artifact_id",
        "processed_file_name",
        "processed_file_sha256",
        "processing_software",
        "processing_software_version",
        "rtc_terrain_correction_method",
        "output_crs",
        "affine_transform",
        "width_pixels",
        "height_pixels",
        "pixel_size_x_m",
        "pixel_size_y_m",
        "nodata_convention",
        "resampling_method",
        "coverage_fraction",
        "valid_data_fraction",
        "coverage_evidence_file_name",
        "coverage_evidence_sha256",
        "valid_data_evidence_file_name",
        "valid_data_evidence_sha256",
        "registration_method",
        "registration_error_pixels",
        "registration_evidence_file_name",
        "registration_evidence_sha256",
        "grid_contract_sha256",
        "source_timestamp",
        "confidence_class",
        "assumptions",
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    }
)

_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_BLOCKING_RIGHTS_STATUSES = frozenset(
    {
        "blocked",
        "denied",
        "expired",
        "not_allowed",
        "not_cleared",
        "prohibited",
        "unknown",
        "unresolved",
    }
)

ReceiptInput: TypeAlias = Mapping[str, Any] | str | Path
TabularInput: TypeAlias = pd.DataFrame | str | Path


class ProcessingAlignmentError(ValueError):
    """Raised when processed-raster evidence cannot clear the grid gate."""


def _validate_governance_gate(
    events: Sequence[EventRecord],
    source_assets: Sequence[SourceAssetRecord],
    *,
    governance_package: str | Path | None,
    allow_ungoverned_fixture: bool,
) -> None:
    conditional_status = "approved_with_provider_conditions"
    conditionally_cleared = any(
        event.source_rights_status.lower() == conditional_status for event in events
    ) or any(
        asset.license_status.lower() == conditional_status for asset in source_assets
    )
    if governance_package is None:
        if conditionally_cleared:
            raise ProcessingAlignmentError(
                "approved_with_provider_conditions registries require their exact "
                "validated governance clearance package."
            )
        if not allow_ungoverned_fixture:
            raise ProcessingAlignmentError(
                "A validated governance clearance package is required. Synthetic "
                "unit fixtures must opt in with allow_ungoverned_fixture=True."
            )
        return
    try:
        validate_cleared_registry_binding(
            governance_package,
            events,
            source_assets,
        )
    except RightsClearanceError as exc:
        raise ProcessingAlignmentError(
            f"Governance clearance package binding failed: {exc}"
        ) from exc


def build_processing_alignment_receipt(
    events: Sequence[EventRecord] | TabularInput,
    source_assets: Sequence[SourceAssetRecord] | TabularInput,
    processing_evidence: TabularInput,
    *,
    validated_at_utc: datetime | None = None,
    governance_package: str | Path | None = None,
    allow_ungoverned_fixture: bool = False,
) -> dict[str, Any]:
    """Hash files and build one exact source-to-common-grid processing receipt.

    Real receipts require a semantically validated clearance package whose
    cleared registries exactly match ``events`` and ``source_assets``.  The
    explicit fixture escape hatch is limited to synthetic test registries and
    can never bypass ``approved_with_provider_conditions`` rights statuses.
    """

    event_records = _coerce_events(events)
    source_records = _coerce_sources(source_assets)
    try:
        validate_event_source_registry(event_records, source_records)
    except EventRegistryError as exc:
        raise ProcessingAlignmentError(str(exc)) from exc
    _validate_governance_gate(
        event_records,
        source_records,
        governance_package=governance_package,
        allow_ungoverned_fixture=allow_ungoverned_fixture,
    )

    evidence = _load_processing_evidence(processing_evidence)
    required_assets = tuple(
        sorted(
            (
                asset
                for asset in source_records
                if asset.event_relative_role != "static_context"
            ),
            key=lambda asset: asset.asset_id,
        )
    )
    required_ids = {asset.asset_id for asset in required_assets}
    supplied_ids = set(evidence["asset_id"].astype(str))
    if supplied_ids != required_ids:
        missing = sorted(required_ids - supplied_ids)
        extra = sorted(supplied_ids - required_ids)
        raise ProcessingAlignmentError(
            "Processing evidence must exactly cover every non-static source asset; "
            f"missing={missing or 'none'}; extra={extra or 'none'}."
        )

    event_by_id = {event.event_id: event for event in event_records}
    asset_by_id = {asset.asset_id: asset for asset in required_assets}
    rows: list[dict[str, Any]] = []
    normalized_evidence_rows: list[dict[str, Any]] = []
    for raw in evidence.sort_values("asset_id").to_dict(orient="records"):
        asset = asset_by_id[str(raw["asset_id"])]
        event = event_by_id[asset.event_id]
        normalized, receipt_row = _validate_and_hash_evidence_row(
            raw,
            asset=asset,
            event=event,
        )
        normalized_evidence_rows.append(normalized)
        rows.append(receipt_row)
    _require_common_event_grids(rows)

    validated_at = _as_utc(validated_at_utc or datetime.now(UTC))
    event_frame = pd.DataFrame(
        [record.as_manifest_row() for record in event_records]
    )
    source_frame = pd.DataFrame(
        [record.as_manifest_row() for record in source_records]
    )
    normalized_frame = pd.DataFrame(
        normalized_evidence_rows,
        columns=PROCESSING_EVIDENCE_COLUMNS,
    )
    payload: dict[str, Any] = {
        "artifact_schema": PROCESSING_ALIGNMENT_RECEIPT_SCHEMA,
        "validator": PROCESSING_ALIGNMENT_VALIDATOR_ID,
        "validated_at_utc": format_utc_datetime(validated_at),
        "event_registry_sha256": _frame_sha256(event_frame),
        "source_registry_sha256": _frame_sha256(source_frame),
        "processing_evidence_sha256": _frame_sha256(normalized_frame),
        "event_count": len(event_records),
        "source_asset_count": len(rows),
        "assets": rows,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "assumptions": (
            "Receipt proves byte-hash binding and declared common-grid checks only; "
            "it is not flood truth, field validation, an official warning, or FPPS input."
        ),
    }
    return {**payload, "receipt_sha256": _canonical_json_sha256(payload)}


def write_processing_alignment_receipt(
    receipt: ReceiptInput,
    path: str | Path,
) -> Path:
    """Verify and immutably write one processing/alignment receipt."""

    normalized = load_processing_alignment_receipt(receipt)
    target = Path(path)
    if target.suffix.lower() != ".json":
        raise ProcessingAlignmentError(
            "Processing/alignment receipt output must use a .json suffix."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as handle:
            json.dump(
                normalized,
                handle,
                ensure_ascii=True,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")
    except FileExistsError as exc:
        raise ProcessingAlignmentError(
            f"Processing/alignment receipt is immutable and already exists: {target}"
        ) from exc
    return target


def load_processing_alignment_receipt(source: ReceiptInput) -> dict[str, Any]:
    """Load and self-hash-verify a processing/alignment receipt."""

    if isinstance(source, Mapping):
        payload: Any = dict(source)
    else:
        path = Path(source)
        if path.suffix.lower() != ".json":
            raise ProcessingAlignmentError(
                "Processing/alignment receipt input must be a .json file."
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProcessingAlignmentError(
                f"Could not load processing/alignment receipt: {path}"
            ) from exc
    return _verify_receipt_payload(payload)


def validate_processing_alignment_receipt(
    receipt: ReceiptInput,
    events: Sequence[EventRecord] | TabularInput,
    source_assets: Sequence[SourceAssetRecord] | TabularInput,
    *,
    governance_package: str | Path | None = None,
    allow_ungoverned_fixture: bool = False,
) -> dict[str, Any]:
    """Cross-check a verified receipt against the exact event/source registry."""

    normalized = load_processing_alignment_receipt(receipt)
    event_records = _coerce_events(events)
    source_records = _coerce_sources(source_assets)
    try:
        validate_event_source_registry(event_records, source_records)
    except EventRegistryError as exc:
        raise ProcessingAlignmentError(str(exc)) from exc
    _validate_governance_gate(
        event_records,
        source_records,
        governance_package=governance_package,
        allow_ungoverned_fixture=allow_ungoverned_fixture,
    )
    expected_event_hash = _frame_sha256(
        pd.DataFrame([record.as_manifest_row() for record in event_records])
    )
    expected_source_hash = _frame_sha256(
        pd.DataFrame([record.as_manifest_row() for record in source_records])
    )
    if normalized["event_registry_sha256"] != expected_event_hash:
        raise ProcessingAlignmentError(
            "Processing receipt event-registry hash does not match the supplied registry."
        )
    if normalized["source_registry_sha256"] != expected_source_hash:
        raise ProcessingAlignmentError(
            "Processing receipt source-registry hash does not match the supplied registry."
        )

    event_by_id = {event.event_id: event for event in event_records}
    required_assets = {
        asset.asset_id: asset
        for asset in source_records
        if asset.event_relative_role != "static_context"
    }
    receipt_assets = {row["asset_id"]: row for row in normalized["assets"]}
    if set(receipt_assets) != set(required_assets):
        raise ProcessingAlignmentError(
            "Processing receipt no longer exactly covers the non-static source registry."
        )
    for asset_id, asset in required_assets.items():
        row = receipt_assets[asset_id]
        event = event_by_id[asset.event_id]
        expected = {
            "event_id": asset.event_id,
            "source_sha256": asset.sha256,
            "source_sha256_status": asset.sha256_status,
            "product_id": asset.product_id,
            "acquisition_time_utc": format_utc_datetime(asset.acquisition_time_utc),
            "event_relative_role": asset.event_relative_role,
            "source_license_status": asset.license_status,
            "source_processing_allowed": asset.processing_allowed,
            "source_ml_label_derivation_allowed": asset.ml_label_derivation_allowed,
            "source_redistribution_status": asset.redistribution_status,
            "output_crs": event.analysis_crs,
            "grid_contract_sha256": event.grid.contract_sha256,
        }
        mismatches = [field for field, value in expected.items() if row[field] != value]
        if mismatches:
            raise ProcessingAlignmentError(
                f"Processing receipt source binding changed for {asset_id}: "
                + ", ".join(mismatches)
            )
        _validate_grid_values(row, event=event, label=f"receipt asset {asset_id}")
    if normalized["event_count"] != len(event_records):
        raise ProcessingAlignmentError("Processing receipt event_count is stale.")
    if normalized["source_asset_count"] != len(required_assets):
        raise ProcessingAlignmentError("Processing receipt source_asset_count is stale.")
    return normalized


def require_processed_coverage_for_tiles(
    receipt: ReceiptInput,
    tiles: pd.DataFrame,
) -> None:
    """Require every canonical tile to fall inside every event source raster."""

    normalized = load_processing_alignment_receipt(receipt)
    required = {
        "event_id",
        "bbox_min_x",
        "bbox_min_y",
        "bbox_max_x",
        "bbox_max_y",
    }
    missing = sorted(required - set(tiles.columns))
    if missing:
        raise ProcessingAlignmentError(
            "Tile coverage validation is missing columns: " + ", ".join(missing)
        )
    assets_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for asset in normalized["assets"]:
        assets_by_event.setdefault(str(asset["event_id"]), []).append(asset)
    for raw in tiles.to_dict(orient="records"):
        event_id = str(raw["event_id"])
        event_assets = assets_by_event.get(event_id, [])
        if not event_assets:
            raise ProcessingAlignmentError(
                f"No processed source coverage exists for tile event {event_id!r}."
            )
        tile_bounds = tuple(
            _finite_float(raw[field], field)
            for field in (
                "bbox_min_x",
                "bbox_min_y",
                "bbox_max_x",
                "bbox_max_y",
            )
        )
        for asset in event_assets:
            bounds = processed_bounds(asset)
            if not _bounds_contain(bounds, tile_bounds):
                raise ProcessingAlignmentError(
                    f"Processed asset {asset['asset_id']!r} does not cover a "
                    f"canonical tile for event {event_id!r}."
                )


def processed_bounds(asset: Mapping[str, Any]) -> tuple[float, float, float, float]:
    """Return min-x, min-y, max-x, max-y for one north-up receipt asset."""

    affine = asset["affine_transform"]
    a, _b, c, _d, e, f = (float(value) for value in affine)
    width = int(asset["width_pixels"])
    height = int(asset["height_pixels"])
    x0, x1 = c, c + a * width
    y0, y1 = f, f + e * height
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def processing_assets_by_id(receipt: ReceiptInput) -> dict[str, dict[str, Any]]:
    """Return a defensive asset-id index from a verified receipt."""

    normalized = load_processing_alignment_receipt(receipt)
    return {str(row["asset_id"]): dict(row) for row in normalized["assets"]}


def _validate_and_hash_evidence_row(
    raw: Mapping[str, Any],
    *,
    asset: SourceAssetRecord,
    event: EventRecord,
) -> tuple[dict[str, Any], dict[str, Any]]:
    asset_id = _canonical_text(raw["asset_id"], "asset_id")
    artifact_id = _canonical_text(raw["processed_artifact_id"], "processed_artifact_id")
    if _ID_PATTERN.fullmatch(artifact_id) is None:
        raise ProcessingAlignmentError(
            "processed_artifact_id must use letters, digits, dot, underscore, colon, or hyphen."
        )
    processed_path, processed_sha = _verify_file(
        raw["processed_file_path"],
        raw["processed_file_sha256"],
        label=f"processed file for {asset_id}",
    )
    coverage_path, coverage_sha = _verify_file(
        raw["coverage_evidence_path"],
        raw["coverage_evidence_sha256"],
        label=f"coverage evidence for {asset_id}",
    )
    valid_path, valid_sha = _verify_file(
        raw["valid_data_evidence_path"],
        raw["valid_data_evidence_sha256"],
        label=f"valid-data evidence for {asset_id}",
    )
    registration_path, registration_sha = _verify_file(
        raw["registration_evidence_path"],
        raw["registration_evidence_sha256"],
        label=f"registration evidence for {asset_id}",
    )
    affine = [
        _finite_float(raw[field], field)
        for field in (
            "affine_a",
            "affine_b",
            "affine_c",
            "affine_d",
            "affine_e",
            "affine_f",
        )
    ]
    width = _positive_int(raw["width_pixels"], "width_pixels")
    height = _positive_int(raw["height_pixels"], "height_pixels")
    pixel_x = _positive_float(raw["pixel_size_x_m"], "pixel_size_x_m")
    pixel_y = _positive_float(raw["pixel_size_y_m"], "pixel_size_y_m")
    coverage_fraction = _fraction(raw["coverage_fraction"], "coverage_fraction")
    valid_fraction = _fraction(raw["valid_data_fraction"], "valid_data_fraction")
    if not math.isclose(coverage_fraction, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ProcessingAlignmentError(
            f"Processing evidence for {asset_id} must document full coverage_fraction=1."
        )
    registration_error = _nonnegative_float(
        raw["registration_error_pixels"], "registration_error_pixels"
    )
    if registration_error > MAX_GEOREGISTRATION_ERROR_PIXELS:
        raise ProcessingAlignmentError(
            f"Processing evidence for {asset_id} registration error "
            f"{registration_error:g} pixels exceeds the canonical maximum of "
            f"{MAX_GEOREGISTRATION_ERROR_PIXELS:g} pixels."
        )
    output_crs = _canonical_text(raw["output_crs"], "output_crs")
    grid_hash = _sha256_text(raw["grid_contract_sha256"], "grid_contract_sha256")
    timestamp = parse_utc_datetime(raw["source_timestamp"], "source_timestamp")
    if timestamp < max(asset.source_timestamp, asset.acquisition_time_utc):
        raise ProcessingAlignmentError(
            f"Processing evidence source_timestamp for {asset_id} predates its source metadata."
        )
    confidence = _canonical_text(raw["confidence_class"], "confidence_class").lower()
    if confidence not in CONFIDENCE_CLASSES:
        raise ProcessingAlignmentError(
            "confidence_class must be high, medium, or low."
        )
    methods = {
        field: _meaningful_text(raw[field], field)
        for field in (
            "processing_software",
            "processing_software_version",
            "rtc_terrain_correction_method",
            "nodata_convention",
            "resampling_method",
            "registration_method",
            "assumptions",
        )
    }
    safety = {
        "query_model_only": strict_bool(raw["query_model_only"], "query_model_only"),
        "eligible_for_decision_layer": strict_bool(
            raw["eligible_for_decision_layer"], "eligible_for_decision_layer"
        ),
        "eligible_for_fpps": strict_bool(raw["eligible_for_fpps"], "eligible_for_fpps"),
        "eligible_for_warning": strict_bool(
            raw["eligible_for_warning"], "eligible_for_warning"
        ),
    }
    _require_safe_flags(safety, label=f"processing evidence for {asset_id}")

    spatial = {
        "output_crs": output_crs,
        "affine_transform": affine,
        "width_pixels": width,
        "height_pixels": height,
        "pixel_size_x_m": pixel_x,
        "pixel_size_y_m": pixel_y,
        "grid_contract_sha256": grid_hash,
    }
    _validate_grid_values(spatial, event=event, label=f"processing evidence for {asset_id}")

    normalized = {
        **{key: raw[key] for key in PROCESSING_EVIDENCE_COLUMNS},
        "asset_id": asset_id,
        "processed_artifact_id": artifact_id,
        "processed_file_path": processed_path.name,
        "processed_file_sha256": processed_sha,
        "output_crs": output_crs,
        "affine_a": affine[0],
        "affine_b": affine[1],
        "affine_c": affine[2],
        "affine_d": affine[3],
        "affine_e": affine[4],
        "affine_f": affine[5],
        "width_pixels": width,
        "height_pixels": height,
        "pixel_size_x_m": pixel_x,
        "pixel_size_y_m": pixel_y,
        "coverage_fraction": coverage_fraction,
        "valid_data_fraction": valid_fraction,
        "coverage_evidence_path": coverage_path.name,
        "coverage_evidence_sha256": coverage_sha,
        "valid_data_evidence_path": valid_path.name,
        "valid_data_evidence_sha256": valid_sha,
        "registration_error_pixels": registration_error,
        "registration_evidence_path": registration_path.name,
        "registration_evidence_sha256": registration_sha,
        "grid_contract_sha256": grid_hash,
        "source_timestamp": format_utc_datetime(timestamp),
        "confidence_class": confidence,
        **methods,
        **safety,
    }
    receipt_row: dict[str, Any] = {
        "asset_id": asset.asset_id,
        "event_id": asset.event_id,
        "source_sha256": asset.sha256,
        "source_sha256_status": asset.sha256_status,
        "product_id": asset.product_id,
        "acquisition_time_utc": format_utc_datetime(asset.acquisition_time_utc),
        "event_relative_role": asset.event_relative_role,
        "source_license_status": asset.license_status,
        "source_processing_allowed": asset.processing_allowed,
        "source_ml_label_derivation_allowed": asset.ml_label_derivation_allowed,
        "source_redistribution_status": asset.redistribution_status,
        "processed_artifact_id": artifact_id,
        "processed_file_name": processed_path.name,
        "processed_file_sha256": processed_sha,
        "processing_software": methods["processing_software"],
        "processing_software_version": methods["processing_software_version"],
        "rtc_terrain_correction_method": methods["rtc_terrain_correction_method"],
        **spatial,
        "nodata_convention": methods["nodata_convention"],
        "resampling_method": methods["resampling_method"],
        "coverage_fraction": coverage_fraction,
        "valid_data_fraction": valid_fraction,
        "coverage_evidence_file_name": coverage_path.name,
        "coverage_evidence_sha256": coverage_sha,
        "valid_data_evidence_file_name": valid_path.name,
        "valid_data_evidence_sha256": valid_sha,
        "registration_method": methods["registration_method"],
        "registration_error_pixels": registration_error,
        "registration_evidence_file_name": registration_path.name,
        "registration_evidence_sha256": registration_sha,
        "source_timestamp": format_utc_datetime(timestamp),
        "confidence_class": confidence,
        "assumptions": methods["assumptions"],
        **safety,
    }
    return normalized, receipt_row


def _verify_receipt_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != _RECEIPT_KEYS:
        raise ProcessingAlignmentError(
            "Processing/alignment receipt has unexpected or missing fields."
        )
    normalized = dict(payload)
    if normalized["artifact_schema"] != PROCESSING_ALIGNMENT_RECEIPT_SCHEMA:
        raise ProcessingAlignmentError("Unsupported processing/alignment receipt schema.")
    if normalized["validator"] != PROCESSING_ALIGNMENT_VALIDATOR_ID:
        raise ProcessingAlignmentError("Unsupported processing/alignment validator.")
    _parse_utc(normalized["validated_at_utc"], "validated_at_utc")
    for field in (
        "event_registry_sha256",
        "source_registry_sha256",
        "processing_evidence_sha256",
        "receipt_sha256",
    ):
        _sha256_text(normalized[field], field)
    if not isinstance(normalized["event_count"], int) or isinstance(
        normalized["event_count"], bool
    ) or normalized["event_count"] <= 0:
        raise ProcessingAlignmentError("event_count must be a positive integer.")
    if not isinstance(normalized["source_asset_count"], int) or isinstance(
        normalized["source_asset_count"], bool
    ) or normalized["source_asset_count"] <= 0:
        raise ProcessingAlignmentError("source_asset_count must be a positive integer.")
    assets = normalized["assets"]
    if not isinstance(assets, list) or not assets:
        raise ProcessingAlignmentError("Processing receipt assets must be a non-empty list.")
    if len(assets) != normalized["source_asset_count"]:
        raise ProcessingAlignmentError("Processing receipt asset count does not match assets.")
    ids: list[str] = []
    for index, row in enumerate(assets):
        if not isinstance(row, Mapping) or set(row) != _ASSET_KEYS:
            raise ProcessingAlignmentError(
                f"Processing receipt asset {index} has unexpected or missing fields."
            )
        _verify_receipt_asset(row)
        ids.append(str(row["asset_id"]))
    if ids != sorted(set(ids)):
        raise ProcessingAlignmentError(
            "Processing receipt assets must be unique and sorted by asset_id."
        )
    if normalized["event_count"] != len(
        {str(row["event_id"]) for row in assets}
    ):
        raise ProcessingAlignmentError(
            "Processing receipt event_count does not match its asset events."
        )
    _require_common_event_grids(assets)
    _require_safe_flags(normalized, label="processing receipt")
    _meaningful_text(normalized["assumptions"], "assumptions")
    unsigned = {key: value for key, value in normalized.items() if key != "receipt_sha256"}
    if _canonical_json_sha256(unsigned) != normalized["receipt_sha256"]:
        raise ProcessingAlignmentError("Processing/alignment receipt self-hash mismatch.")
    return normalized


def _verify_receipt_asset(row: Mapping[str, Any]) -> None:
    asset_id = _canonical_text(row["asset_id"], "asset_id")
    if _ID_PATTERN.fullmatch(asset_id) is None:
        raise ProcessingAlignmentError("Receipt asset_id has invalid characters.")
    for field in (
        "event_id",
        "product_id",
        "event_relative_role",
        "source_sha256_status",
        "source_license_status",
        "source_redistribution_status",
        "processed_artifact_id",
        "processed_file_name",
        "processing_software",
        "processing_software_version",
        "rtc_terrain_correction_method",
        "output_crs",
        "nodata_convention",
        "resampling_method",
        "coverage_evidence_file_name",
        "valid_data_evidence_file_name",
        "registration_method",
        "registration_evidence_file_name",
        "confidence_class",
        "assumptions",
    ):
        _meaningful_text(row[field], field)
    if row["event_relative_role"] not in {"pre_event", "event_time", "post_event"}:
        raise ProcessingAlignmentError(
            f"Processing receipt asset {asset_id} must have a non-static acquisition role."
        )
    if row["source_sha256_status"] not in {"recorded", "verified"}:
        raise ProcessingAlignmentError(
            f"Processing receipt asset {asset_id} has invalid source_sha256_status."
        )
    if str(row["source_license_status"]).lower() in _BLOCKING_RIGHTS_STATUSES:
        raise ProcessingAlignmentError(
            f"Processing receipt asset {asset_id} has blocked source license status."
        )
    artifact_id = str(row["processed_artifact_id"])
    if _ID_PATTERN.fullmatch(artifact_id) is None:
        raise ProcessingAlignmentError(
            "Receipt processed_artifact_id has invalid characters."
        )
    for field in (
        "processed_file_name",
        "coverage_evidence_file_name",
        "valid_data_evidence_file_name",
        "registration_evidence_file_name",
    ):
        name = str(row[field])
        if Path(name).name != name or "/" in name or "\\" in name:
            raise ProcessingAlignmentError(
                f"Receipt {field} must be a path-free file name."
            )
    for field in (
        "source_sha256",
        "processed_file_sha256",
        "coverage_evidence_sha256",
        "valid_data_evidence_sha256",
        "registration_evidence_sha256",
        "grid_contract_sha256",
    ):
        _sha256_text(row[field], field)
    acquisition = _parse_utc(row["acquisition_time_utc"], "acquisition_time_utc")
    source_timestamp = _parse_utc(row["source_timestamp"], "source_timestamp")
    if source_timestamp < acquisition:
        raise ProcessingAlignmentError(
            f"Processing receipt asset {asset_id} source_timestamp predates acquisition."
        )
    try:
        validate_projected_metre_crs(str(row["output_crs"]))
    except GridContractError as exc:
        raise ProcessingAlignmentError(str(exc)) from exc
    affine = row["affine_transform"]
    if not isinstance(affine, list) or len(affine) != 6:
        raise ProcessingAlignmentError("affine_transform must contain exactly six terms.")
    for value in affine:
        _finite_float(value, "affine_transform")
    a, b, _c, d, e, _f = (float(value) for value in affine)
    _positive_int(row["width_pixels"], "width_pixels")
    _positive_int(row["height_pixels"], "height_pixels")
    _positive_float(row["pixel_size_x_m"], "pixel_size_x_m")
    _positive_float(row["pixel_size_y_m"], "pixel_size_y_m")
    if not (
        a > 0
        and e < 0
        and math.isclose(b, 0.0, rel_tol=0.0, abs_tol=1e-12)
        and math.isclose(d, 0.0, rel_tol=0.0, abs_tol=1e-12)
        and math.isclose(
            a,
            float(row["pixel_size_x_m"]),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        and math.isclose(
            -e,
            float(row["pixel_size_y_m"]),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        raise ProcessingAlignmentError(
            "Receipt affine must be north-up, unrotated, and match declared pixel sizes."
        )
    coverage = _fraction(row["coverage_fraction"], "coverage_fraction")
    if not math.isclose(coverage, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ProcessingAlignmentError("Receipt coverage_fraction must equal 1.")
    _fraction(row["valid_data_fraction"], "valid_data_fraction")
    error = _nonnegative_float(
        row["registration_error_pixels"], "registration_error_pixels"
    )
    if error > MAX_GEOREGISTRATION_ERROR_PIXELS:
        raise ProcessingAlignmentError(
            "Receipt registration error exceeds the canonical 0.5-pixel maximum."
        )
    confidence = str(row["confidence_class"]).lower()
    if confidence not in CONFIDENCE_CLASSES:
        raise ProcessingAlignmentError("Receipt confidence_class is invalid.")
    rights_flags = {
        "source_processing_allowed": True,
        "source_ml_label_derivation_allowed": True,
    }
    for field, expected in rights_flags.items():
        if row[field] is not expected:
            raise ProcessingAlignmentError(
                f"Receipt asset {asset_id} has unsafe {field}."
            )
    _require_safe_flags(row, label=f"processing receipt asset {asset_id}")


def _validate_grid_values(
    row: Mapping[str, Any],
    *,
    event: EventRecord,
    label: str,
) -> None:
    if row["output_crs"] != event.analysis_crs:
        raise ProcessingAlignmentError(
            f"{label} output CRS does not match event analysis_crs."
        )
    if row["grid_contract_sha256"] != event.grid.contract_sha256:
        raise ProcessingAlignmentError(
            f"{label} grid-contract hash does not match the event grid."
        )
    affine = tuple(float(value) for value in row["affine_transform"])
    a, b, c, d, e, f = affine
    resolution = event.analysis_resolution_m
    if not (
        math.isclose(a, resolution, rel_tol=0.0, abs_tol=1e-9)
        and math.isclose(e, -resolution, rel_tol=0.0, abs_tol=1e-9)
        and math.isclose(b, 0.0, rel_tol=0.0, abs_tol=1e-12)
        and math.isclose(d, 0.0, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise ProcessingAlignmentError(
            f"{label} must use a north-up, unrotated affine at analysis resolution."
        )
    if not (
        math.isclose(float(row["pixel_size_x_m"]), resolution, rel_tol=0.0, abs_tol=1e-9)
        and math.isclose(float(row["pixel_size_y_m"]), resolution, rel_tol=0.0, abs_tol=1e-9)
    ):
        raise ProcessingAlignmentError(
            f"{label} pixel size does not match analysis_resolution_m."
        )
    for value, origin, name in (
        (c, event.grid_origin_x, "affine_c"),
        (f, event.grid_origin_y, "affine_f"),
    ):
        offset_cells = (value - origin) / resolution
        if not math.isclose(offset_cells, round(offset_cells), rel_tol=0.0, abs_tol=1e-9):
            raise ProcessingAlignmentError(
                f"{label} {name} is not aligned to the canonical grid origin."
            )


def _require_common_event_grids(rows: Sequence[Mapping[str, Any]]) -> None:
    by_event: dict[str, set[str]] = {}
    for row in rows:
        spatial = {
            "output_crs": row["output_crs"],
            "affine_transform": row["affine_transform"],
            "width_pixels": row["width_pixels"],
            "height_pixels": row["height_pixels"],
            "pixel_size_x_m": row["pixel_size_x_m"],
            "pixel_size_y_m": row["pixel_size_y_m"],
            "nodata_convention": row["nodata_convention"],
            "grid_contract_sha256": row["grid_contract_sha256"],
        }
        by_event.setdefault(str(row["event_id"]), set()).add(
            json.dumps(spatial, sort_keys=True, separators=(",", ":"), allow_nan=False)
        )
    mismatched = sorted(event_id for event_id, values in by_event.items() if len(values) != 1)
    if mismatched:
        raise ProcessingAlignmentError(
            "All non-static processed assets for each event must share one affine, "
            "dimension, pixel-size, nodata, CRS, and grid contract; mismatched events: "
            + ", ".join(mismatched)
        )


def _load_processing_evidence(source: TabularInput) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        frame = source.copy().fillna("")
    else:
        path = Path(source)
        if path.suffix.lower() != ".csv" or not path.is_file():
            raise ProcessingAlignmentError(
                f"Processing evidence must be an existing CSV file: {path}"
            )
        try:
            frame = pd.read_csv(path, dtype=str).fillna("")
        except (OSError, pd.errors.ParserError, UnicodeError) as exc:
            raise ProcessingAlignmentError(
                f"Could not read processing evidence CSV: {exc}"
            ) from exc
    missing = sorted(set(PROCESSING_EVIDENCE_COLUMNS) - set(frame.columns))
    unexpected = sorted(set(frame.columns) - set(PROCESSING_EVIDENCE_COLUMNS))
    if missing or unexpected:
        raise ProcessingAlignmentError(
            "Processing evidence columns must match the v1 contract exactly; "
            f"missing={missing or 'none'}; unexpected={unexpected or 'none'}."
        )
    if frame.empty:
        raise ProcessingAlignmentError("Processing evidence must not be empty.")
    ids = frame["asset_id"].astype(str)
    if ids.duplicated().any():
        raise ProcessingAlignmentError("Processing evidence asset_id values must be unique.")
    artifact_ids = frame["processed_artifact_id"].astype(str)
    if artifact_ids.duplicated().any():
        raise ProcessingAlignmentError(
            "Processing evidence processed_artifact_id values must be unique."
        )
    return frame


def _coerce_events(
    value: Sequence[EventRecord] | TabularInput,
) -> tuple[EventRecord, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, pd.DataFrame)) and all(
        isinstance(item, EventRecord) for item in value
    ):
        records = tuple(value)
    else:
        try:
            records = load_events(value)  # type: ignore[arg-type]
        except EventRegistryError as exc:
            raise ProcessingAlignmentError(str(exc)) from exc
    if not records:
        raise ProcessingAlignmentError("events must not be empty.")
    return records


def _coerce_sources(
    value: Sequence[SourceAssetRecord] | TabularInput,
) -> tuple[SourceAssetRecord, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, pd.DataFrame)) and all(
        isinstance(item, SourceAssetRecord) for item in value
    ):
        records = tuple(value)
    else:
        try:
            records = load_source_assets(value)  # type: ignore[arg-type]
        except EventRegistryError as exc:
            raise ProcessingAlignmentError(str(exc)) from exc
    if not records:
        raise ProcessingAlignmentError("source assets must not be empty.")
    return records


def _verify_file(path_value: object, sha_value: object, *, label: str) -> tuple[Path, str]:
    path_text = str(path_value).strip()
    if not path_text:
        raise ProcessingAlignmentError(f"{label} path must not be blank.")
    path = Path(path_text)
    if not path.is_file():
        raise ProcessingAlignmentError(f"{label} does not exist: {path}")
    expected = _sha256_text(sha_value, f"{label} sha256")
    actual = _file_sha256(path)
    if actual != expected:
        raise ProcessingAlignmentError(
            f"{label} SHA-256 mismatch: expected={expected}; actual={actual}."
        )
    return path, actual


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_sha256(frame: pd.DataFrame) -> str:
    encoded = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_safe_flags(row: Mapping[str, Any], *, label: str) -> None:
    expected = {
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    bad = [field for field, value in expected.items() if row.get(field) is not value]
    if bad:
        raise ProcessingAlignmentError(
            f"{label} contains unsafe or non-boolean safety fields: {', '.join(bad)}."
        )


def _parse_utc(value: object, field: str) -> datetime:
    try:
        return parse_utc_datetime(value, field)
    except EventRegistryError as exc:
        raise ProcessingAlignmentError(str(exc)) from exc


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ProcessingAlignmentError(
            "validated_at_utc must be a timezone-aware datetime."
        )
    return value.astimezone(UTC).replace(microsecond=0)


def _canonical_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProcessingAlignmentError(
            f"{field} must be non-blank canonical text without edge whitespace."
        )
    return value


def _meaningful_text(value: object, field: str) -> str:
    text = _canonical_text(value, field)
    if text.lower() in {"none", "n/a", "na", "unknown", "unresolved", "not_applicable"}:
        raise ProcessingAlignmentError(f"{field} must contain specific evidence, not {text!r}.")
    return text


def _sha256_text(value: object, field: str) -> str:
    text = _canonical_text(value, field)
    if _SHA256_PATTERN.fullmatch(text) is None:
        raise ProcessingAlignmentError(
            f"{field} must be a lowercase complete SHA-256."
        )
    return text


def _finite_float(value: object, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ProcessingAlignmentError(f"{field} must be numeric.") from exc
    if not math.isfinite(result):
        raise ProcessingAlignmentError(f"{field} must be finite.")
    return result


def _positive_float(value: object, field: str) -> float:
    result = _finite_float(value, field)
    if result <= 0:
        raise ProcessingAlignmentError(f"{field} must be positive.")
    return result


def _nonnegative_float(value: object, field: str) -> float:
    result = _finite_float(value, field)
    if result < 0:
        raise ProcessingAlignmentError(f"{field} must be nonnegative.")
    return result


def _fraction(value: object, field: str) -> float:
    result = _finite_float(value, field)
    if not 0 < result <= 1:
        raise ProcessingAlignmentError(f"{field} must be greater than 0 and at most 1.")
    return result


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ProcessingAlignmentError(f"{field} must be a positive integer.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ProcessingAlignmentError(f"{field} must be a positive integer.") from exc
    if not math.isfinite(numeric) or not numeric.is_integer() or numeric <= 0:
        raise ProcessingAlignmentError(f"{field} must be a positive integer.")
    return int(numeric)


def _bounds_contain(
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
) -> bool:
    tolerance = 1e-7
    return (
        outer[0] <= inner[0] + tolerance
        and outer[1] <= inner[1] + tolerance
        and outer[2] + tolerance >= inner[2]
        and outer[3] + tolerance >= inner[3]
    )
