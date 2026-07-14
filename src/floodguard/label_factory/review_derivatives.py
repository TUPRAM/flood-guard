"""Govern reviewer-visible SAR change derivatives without creating flood truth.

The processing/alignment receipt proves which terrain-corrected source bytes
share the canonical grid.  This module adds the missing second provenance
layer for reviewer displays derived from *both* acquisitions: VV change, VH
change, and one fixed-stretch RGB composite.  A receipt re-hashes the exact
source and output bytes, records deterministic transformation/display
parameters, binds governance and grid lineage, and is immutable/self-hashed.

The artifacts admitted here are display evidence for blinded human review.
They remain query-model-only and categorically ineligible for FloodGuard's
decision layer, FPPS, or warnings.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, TypeAlias

import pandas as pd

from floodguard.label_factory.event_registry import (
    EventRegistryError,
    format_utc_datetime,
    parse_utc_datetime,
    reject_absolute_local_path,
)
from floodguard.label_factory.processing_alignment import (
    ProcessingAlignmentError,
    ReceiptInput as ProcessingReceiptInput,
    load_processing_alignment_receipt,
    validate_processing_alignment_receipt,
)
from floodguard.label_factory.rights_clearance import (
    RightsClearanceError,
    validate_rights_clearance_package,
)


REVIEW_DERIVATIVE_BUILD_SPEC_SCHEMA = (
    "floodguard.review_derivative_build_spec.v1"
)
REVIEW_DERIVATIVE_LINEAGE_RECEIPT_SCHEMA = (
    "floodguard.review_derivative_lineage_receipt.v1"
)
REVIEW_DERIVATIVE_VALIDATOR_ID = (
    "rehash_dual_date_sar+validate_fixed_review_display@label_factory_v1"
)

DERIVATIVE_CONTEXT_LAYER_ROLES: frozenset[str] = frozenset(
    {"vv_change", "vh_change", "fixed_stretch_change_composite"}
)

_BUILD_SPEC_KEYS = frozenset(
    {
        "artifact_schema",
        "derivative_set_id",
        "event_id",
        "generated_at_utc",
        "processing_software",
        "processing_software_version",
        "source_inputs",
        "layers",
        "assumptions",
        "formal_review_display_only",
        "allowed_for_blinded_review",
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    }
)

_SOURCE_SPEC_KEYS = frozenset(
    {
        "asset_id",
        "processed_file_path",
        "processed_file_sha256",
        "polarizations",
        "band_by_polarization",
    }
)

_LAYER_SPEC_KEYS = frozenset(
    {
        "derivative_id",
        "layer_role",
        "output_file_path",
        "output_file_sha256",
        "display_name",
        "path_hint",
        "output_crs",
        "affine_transform",
        "width_pixels",
        "height_pixels",
        "nodata_convention",
        "output_dtype",
        "transformation_parameters",
        "display_parameters",
        "confidence_class",
        "assumptions",
        "formal_review_display_only",
        "allowed_for_blinded_review",
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    }
)

_CHANGE_TRANSFORM_KEYS = frozenset(
    {
        "operation",
        "expression",
        "polarization",
        "pre_input_asset_id",
        "event_input_asset_id",
        "pre_band",
        "event_band",
        "input_units",
        "output_units",
        "validity_rule",
    }
)

_COMPOSITE_TRANSFORM_KEYS = frozenset(
    {
        "operation",
        "input_derivative_ids",
        "red_expression",
        "green_expression",
        "blue_expression",
        "validity_rule",
        "channel_min",
        "channel_max",
    }
)

_CHANGE_DISPLAY_KEYS = frozenset(
    {
        "renderer",
        "stretch_min",
        "stretch_max",
        "gamma",
        "clamp",
        "color_map_id",
        "color_stops",
        "resampling",
    }
)

_COMPOSITE_DISPLAY_KEYS = frozenset(
    {
        "renderer",
        "red_band",
        "green_band",
        "blue_band",
        "gamma",
        "resampling",
    }
)

_RECEIPT_KEYS = frozenset(
    {
        "artifact_schema",
        "validator",
        "validated_at_utc",
        "derivative_set_id",
        "event_id",
        "generated_at_utc",
        "processing_software",
        "processing_software_version",
        "governance_package_id",
        "governance_package_manifest_sha256",
        "governance_package_seal_sha256",
        "governance_binding_status",
        "production_review_eligible",
        "event_registry_sha256",
        "source_registry_sha256",
        "processing_alignment_receipt_sha256",
        "processing_alignment_receipt_canonical_file_sha256",
        "grid_contract_sha256",
        "source_raster_binding_sha256",
        "source_rasters",
        "layer_count",
        "layers",
        "build_spec_sha256",
        "formal_review_display_only",
        "allowed_for_blinded_review",
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "assumptions",
        "receipt_sha256",
    }
)

_SOURCE_RECEIPT_KEYS = frozenset(
    {
        "asset_id",
        "event_id",
        "event_relative_role",
        "product_id",
        "acquisition_time_utc",
        "source_sha256",
        "processed_file_name",
        "processed_file_sha256",
        "polarizations",
        "band_by_polarization",
    }
)

_LAYER_RECEIPT_KEYS = frozenset(
    {
        "derivative_id",
        "event_id",
        "layer_role",
        "output_file_name",
        "output_file_size_bytes",
        "output_file_sha256",
        "display_name",
        "path_hint",
        "source_binding_sha256",
        "source_product_id",
        "acquisition_time_utc",
        "output_crs",
        "affine_transform",
        "width_pixels",
        "height_pixels",
        "nodata_convention",
        "output_dtype",
        "transformation_parameters",
        "transformation_parameters_sha256",
        "display_parameters",
        "display_parameters_sha256",
        "confidence_class",
        "assumptions",
        "formal_review_display_only",
        "allowed_for_blinded_review",
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    }
)

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_FORBIDDEN_DYNAMIC_DISPLAY_TERMS = (
    "auto",
    "dynamic",
    "histogram",
    "percentile",
    "quantile",
    "data_min",
    "data_max",
)

ReceiptInput: TypeAlias = Mapping[str, Any] | str | Path
BuildSpecInput: TypeAlias = Mapping[str, Any] | str | Path
TabularInput: TypeAlias = pd.DataFrame | str | Path


class ReviewDerivativeLineageError(ValueError):
    """Raised when reviewer-visible derivative provenance fails closed."""


def build_review_derivative_lineage_receipt(
    build_spec: BuildSpecInput,
    *,
    processing_alignment_receipt: ProcessingReceiptInput,
    governance_package: str | Path | None = None,
    validated_at_utc: datetime | str | None = None,
    allow_ungoverned_fixture: bool = False,
) -> dict[str, Any]:
    """Re-hash sources/outputs and build one immutable derivative receipt.

    Production use requires the sealed governance package bound to the exact
    processing receipt.  ``allow_ungoverned_fixture`` exists only for synthetic
    unit tests and always records ``production_review_eligible=false``.
    """

    spec = _load_build_spec(build_spec)
    processing, governance = _validated_processing_and_governance(
        processing_alignment_receipt,
        governance_package=governance_package,
        allow_ungoverned_fixture=allow_ungoverned_fixture,
    )
    _require_safe_flags(spec, label="derivative build spec")
    if spec["formal_review_display_only"] is not True:
        raise ReviewDerivativeLineageError(
            "Derivative build spec must set formal_review_display_only=true."
        )
    if spec["allowed_for_blinded_review"] is not True:
        raise ReviewDerivativeLineageError(
            "Derivative build spec must explicitly allow blinded review."
        )

    derivative_set_id = _identifier(spec["derivative_set_id"], "derivative_set_id")
    event_id = _identifier(spec["event_id"], "event_id")
    generated_at = _utc_text(spec["generated_at_utc"], "generated_at_utc")
    software = _meaningful_text(spec["processing_software"], "processing_software")
    software_version = _meaningful_text(
        spec["processing_software_version"], "processing_software_version"
    )
    assumptions = _meaningful_text(spec["assumptions"], "assumptions")

    receipt_event_assets = [
        dict(row)
        for row in processing["assets"]
        if str(row["event_id"]) == event_id
    ]
    if not receipt_event_assets:
        raise ReviewDerivativeLineageError(
            f"Processing receipt has no assets for derivative event {event_id!r}."
        )
    if (
        not receipt_event_assets
        or {str(row["event_relative_role"]) for row in receipt_event_assets}
        != {"pre_event", "event_time"}
    ):
        raise ReviewDerivativeLineageError(
            "A reviewer derivative set requires pre_event and event_time processed "
            "source rasters only."
        )
    for row in receipt_event_assets:
        if (
            row["source_processing_allowed"] is not True
            or row["source_ml_label_derivation_allowed"] is not True
            or row["query_model_only"] is not True
            or row["eligible_for_decision_layer"] is not False
            or row["eligible_for_fpps"] is not False
            or row["eligible_for_warning"] is not False
        ):
            raise ReviewDerivativeLineageError(
                f"Processed source {row['asset_id']!r} is not safely eligible for "
                "review-derivative generation."
            )

    source_specs = spec["source_inputs"]
    if not isinstance(source_specs, list) or len(source_specs) != len(
        receipt_event_assets
    ):
        raise ReviewDerivativeLineageError(
            "Derivative build spec source_inputs must exactly cover every event "
            "asset in the processing receipt."
        )
    receipt_assets_by_id = {
        str(row["asset_id"]): row for row in receipt_event_assets
    }
    source_rows: list[dict[str, Any]] = []
    supplied_asset_ids: list[str] = []
    for index, raw in enumerate(source_specs):
        if not isinstance(raw, Mapping) or set(raw) != _SOURCE_SPEC_KEYS:
            raise ReviewDerivativeLineageError(
                f"Derivative source input {index} has unexpected or missing fields."
            )
        asset_id = _identifier(raw["asset_id"], f"source_inputs[{index}].asset_id")
        supplied_asset_ids.append(asset_id)
        receipt_asset = receipt_assets_by_id.get(asset_id)
        if receipt_asset is None:
            raise ReviewDerivativeLineageError(
                f"Derivative source {asset_id!r} is absent from the event's "
                "processing receipt."
            )
        processed_path = _file_path(
            raw["processed_file_path"],
            f"source_inputs[{index}].processed_file_path",
        )
        declared_hash = _sha256_text(
            raw["processed_file_sha256"],
            f"source_inputs[{index}].processed_file_sha256",
        )
        actual_hash = _file_sha256(processed_path)
        if actual_hash != declared_hash or actual_hash != receipt_asset["processed_file_sha256"]:
            raise ReviewDerivativeLineageError(
                f"Derivative source {asset_id!r} bytes do not match the declared "
                "hash and processing receipt."
            )
        if processed_path.name != receipt_asset["processed_file_name"]:
            raise ReviewDerivativeLineageError(
                f"Derivative source {asset_id!r} file name does not match the "
                "processing receipt."
            )
        polarizations, bands = _polarization_binding(
            raw["polarizations"],
            raw["band_by_polarization"],
            label=f"source_inputs[{index}]",
        )
        source_rows.append(
            {
                "asset_id": asset_id,
                "event_id": event_id,
                "event_relative_role": str(receipt_asset["event_relative_role"]),
                "product_id": str(receipt_asset["product_id"]),
                "acquisition_time_utc": str(receipt_asset["acquisition_time_utc"]),
                "source_sha256": str(receipt_asset["source_sha256"]),
                "processed_file_name": processed_path.name,
                "processed_file_sha256": actual_hash,
                "polarizations": list(polarizations),
                "band_by_polarization": bands,
            }
        )
    if set(supplied_asset_ids) != set(receipt_assets_by_id) or len(
        supplied_asset_ids
    ) != len(set(supplied_asset_ids)):
        raise ReviewDerivativeLineageError(
            "Derivative source inputs must exactly and uniquely cover the event's "
            "pre/event processing-receipt assets."
        )
    source_rows.sort(key=lambda row: str(row["asset_id"]))
    governed_polarizations = _governed_source_polarizations(governance_package)
    if governed_polarizations is not None:
        for row in source_rows:
            expected = governed_polarizations.get(str(row["asset_id"]))
            if expected is None or tuple(row["polarizations"]) != expected:
                raise ReviewDerivativeLineageError(
                    f"Derivative source {row['asset_id']!r} polarization binding "
                    "does not match the governed source registry."
                )
    source_by_role_polarization = _index_source_polarizations(source_rows)
    source_binding_sha = _canonical_json_sha256(source_rows)

    grid_values = {
        (
            str(row["output_crs"]),
            tuple(float(value) for value in row["affine_transform"]),
            int(row["width_pixels"]),
            int(row["height_pixels"]),
            str(row["grid_contract_sha256"]),
        )
        for row in receipt_event_assets
    }
    if len(grid_values) != 1:
        raise ReviewDerivativeLineageError(
            "Derivative sources do not share one processing-receipt grid."
        )
    output_crs, affine, width, height, grid_hash = next(iter(grid_values))

    layer_specs = spec["layers"]
    if not isinstance(layer_specs, list) or len(layer_specs) != 3:
        raise ReviewDerivativeLineageError(
            "Derivative build spec layers must contain VV change, VH change, and "
            "one fixed-stretch composite."
        )
    structurally_validated: list[dict[str, Any]] = []
    role_to_spec: dict[str, Mapping[str, Any]] = {}
    ids: list[str] = []
    for index, raw in enumerate(layer_specs):
        if not isinstance(raw, Mapping) or set(raw) != _LAYER_SPEC_KEYS:
            raise ReviewDerivativeLineageError(
                f"Derivative layer {index} has unexpected or missing fields."
            )
        _require_safe_flags(raw, label=f"derivative layer {index}")
        if raw["formal_review_display_only"] is not True:
            raise ReviewDerivativeLineageError(
                f"Derivative layer {index} must be formal-review-display-only."
            )
        if raw["allowed_for_blinded_review"] is not True:
            raise ReviewDerivativeLineageError(
                f"Derivative layer {index} is not allowed for blinded review."
            )
        derivative_id = _identifier(raw["derivative_id"], f"layers[{index}].derivative_id")
        layer_role = _canonical_text(raw["layer_role"], f"layers[{index}].layer_role")
        if layer_role not in DERIVATIVE_CONTEXT_LAYER_ROLES:
            raise ReviewDerivativeLineageError(
                f"Unsupported reviewer derivative role: {layer_role!r}."
            )
        if layer_role in role_to_spec:
            raise ReviewDerivativeLineageError(
                f"Duplicate reviewer derivative role: {layer_role}."
            )
        role_to_spec[layer_role] = raw
        ids.append(derivative_id)
        declared_crs = _canonical_text(raw["output_crs"], f"layers[{index}].output_crs")
        declared_affine = _affine(raw["affine_transform"], f"layers[{index}].affine_transform")
        declared_width = _positive_int(raw["width_pixels"], f"layers[{index}].width_pixels")
        declared_height = _positive_int(raw["height_pixels"], f"layers[{index}].height_pixels")
        if (
            declared_crs != output_crs
            or declared_affine != affine
            or declared_width != width
            or declared_height != height
        ):
            raise ReviewDerivativeLineageError(
                f"Derivative layer {derivative_id!r} does not declare the exact "
                "processing-receipt common grid."
            )
        output_path = _file_path(
            raw["output_file_path"], f"layers[{index}].output_file_path"
        )
        declared_output_hash = _sha256_text(
            raw["output_file_sha256"], f"layers[{index}].output_file_sha256"
        )
        actual_output_hash = _file_sha256(output_path)
        if actual_output_hash != declared_output_hash:
            raise ReviewDerivativeLineageError(
                f"Derivative output {derivative_id!r} SHA-256 mismatch."
            )
        path_hint = _safe_path_hint(raw["path_hint"], f"layers[{index}].path_hint")
        confidence = _canonical_text(
            raw["confidence_class"], f"layers[{index}].confidence_class"
        ).lower()
        if confidence not in {"high", "medium", "low"}:
            raise ReviewDerivativeLineageError(
                f"Derivative layer {derivative_id!r} has invalid confidence_class."
            )
        structurally_validated.append(
            {
                "derivative_id": derivative_id,
                "event_id": event_id,
                "layer_role": layer_role,
                "output_file_name": output_path.name,
                "output_file_size_bytes": output_path.stat().st_size,
                "output_file_sha256": actual_output_hash,
                "display_name": _meaningful_text(
                    raw["display_name"], f"layers[{index}].display_name"
                ),
                "path_hint": path_hint,
                "source_binding_sha256": source_binding_sha,
                "source_product_id": derivative_set_id,
                "acquisition_time_utc": _event_time_acquisition(source_rows),
                "output_crs": declared_crs,
                "affine_transform": list(declared_affine),
                "width_pixels": declared_width,
                "height_pixels": declared_height,
                "nodata_convention": _meaningful_text(
                    raw["nodata_convention"], f"layers[{index}].nodata_convention"
                ),
                "output_dtype": _meaningful_text(
                    raw["output_dtype"], f"layers[{index}].output_dtype"
                ),
                "transformation_parameters": raw["transformation_parameters"],
                "display_parameters": raw["display_parameters"],
                "confidence_class": confidence,
                "assumptions": _meaningful_text(
                    raw["assumptions"], f"layers[{index}].assumptions"
                ),
                "formal_review_display_only": True,
                "allowed_for_blinded_review": True,
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
        )
    if set(role_to_spec) != set(DERIVATIVE_CONTEXT_LAYER_ROLES) or len(ids) != len(set(ids)):
        raise ReviewDerivativeLineageError(
            "Derivative layers must uniquely provide VV change, VH change, and the "
            "fixed-stretch composite."
        )

    layer_id_by_role = {
        str(row["layer_role"]): str(row["derivative_id"])
        for row in structurally_validated
    }
    layers: list[dict[str, Any]] = []
    for row in structurally_validated:
        role = str(row["layer_role"])
        raw_transform = row.pop("transformation_parameters")
        raw_display = row.pop("display_parameters")
        transform = _validate_transformation_parameters(
            raw_transform,
            layer_role=role,
            layer_id_by_role=layer_id_by_role,
            source_by_role_polarization=source_by_role_polarization,
        )
        display = _validate_display_parameters(raw_display, layer_role=role)
        row["transformation_parameters"] = transform
        row["transformation_parameters_sha256"] = _canonical_json_sha256(transform)
        row["display_parameters"] = display
        row["display_parameters_sha256"] = _canonical_json_sha256(display)
        layers.append(row)
    layers.sort(key=lambda row: str(row["layer_role"]))

    normalized_spec = {
        "artifact_schema": REVIEW_DERIVATIVE_BUILD_SPEC_SCHEMA,
        "derivative_set_id": derivative_set_id,
        "event_id": event_id,
        "generated_at_utc": generated_at,
        "processing_software": software,
        "processing_software_version": software_version,
        "source_rasters": source_rows,
        "layers": layers,
        "assumptions": assumptions,
        "formal_review_display_only": True,
        "allowed_for_blinded_review": True,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    validated_at = _coerce_validated_at(validated_at_utc)
    generated_timestamp = datetime.fromisoformat(generated_at[:-1] + "+00:00")
    if validated_at < generated_timestamp:
        raise ReviewDerivativeLineageError(
            "validated_at_utc cannot precede derivative generation."
        )
    payload: dict[str, Any] = {
        "artifact_schema": REVIEW_DERIVATIVE_LINEAGE_RECEIPT_SCHEMA,
        "validator": REVIEW_DERIVATIVE_VALIDATOR_ID,
        "validated_at_utc": format_utc_datetime(validated_at),
        "derivative_set_id": derivative_set_id,
        "event_id": event_id,
        "generated_at_utc": generated_at,
        "processing_software": software,
        "processing_software_version": software_version,
        **governance,
        "event_registry_sha256": str(processing["event_registry_sha256"]),
        "source_registry_sha256": str(processing["source_registry_sha256"]),
        "processing_alignment_receipt_sha256": str(processing["receipt_sha256"]),
        "processing_alignment_receipt_canonical_file_sha256": (
            _canonical_pretty_json_file_sha256(processing)
        ),
        "grid_contract_sha256": str(grid_hash),
        "source_raster_binding_sha256": source_binding_sha,
        "source_rasters": source_rows,
        "layer_count": len(layers),
        "layers": layers,
        "build_spec_sha256": _canonical_json_sha256(normalized_spec),
        "formal_review_display_only": True,
        "allowed_for_blinded_review": True,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "assumptions": assumptions,
    }
    receipt = {**payload, "receipt_sha256": _canonical_json_sha256(payload)}
    return _verify_receipt_payload(receipt)


def write_review_derivative_lineage_receipt(
    receipt: ReceiptInput,
    path: str | Path,
) -> Path:
    """Self-verify and write one receipt without overwriting an existing file."""

    normalized = load_review_derivative_lineage_receipt(receipt)
    target = Path(path)
    if target.suffix.lower() != ".json":
        raise ReviewDerivativeLineageError(
            "Review-derivative receipt output must use a .json suffix."
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
        raise ReviewDerivativeLineageError(
            f"Review-derivative receipt is immutable and already exists: {target}"
        ) from exc
    return target


def load_review_derivative_lineage_receipt(
    source: ReceiptInput,
) -> dict[str, Any]:
    """Load and self-hash-verify one review-derivative receipt."""

    if isinstance(source, Mapping):
        payload: Any = dict(source)
    else:
        path = Path(source)
        if path.suffix.lower() != ".json":
            raise ReviewDerivativeLineageError(
                "Review-derivative receipt input must be a .json file."
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReviewDerivativeLineageError(
                f"Could not load review-derivative receipt: {path}"
            ) from exc
    return _verify_receipt_payload(payload)


def validate_review_derivative_lineage_receipt(
    receipt: ReceiptInput,
    *,
    processing_alignment_receipt: ProcessingReceiptInput,
    review_manifest: TabularInput | None = None,
    context_manifest: TabularInput | None = None,
    governance_package: str | Path | None = None,
    allow_ungoverned_fixture: bool = False,
) -> dict[str, Any]:
    """Cross-check a receipt against processing, governance, and review context."""

    normalized = load_review_derivative_lineage_receipt(receipt)
    processing, governance = _validated_processing_and_governance(
        processing_alignment_receipt,
        governance_package=governance_package,
        allow_ungoverned_fixture=allow_ungoverned_fixture,
    )
    expected_top = {
        **governance,
        "event_registry_sha256": str(processing["event_registry_sha256"]),
        "source_registry_sha256": str(processing["source_registry_sha256"]),
        "processing_alignment_receipt_sha256": str(processing["receipt_sha256"]),
        "processing_alignment_receipt_canonical_file_sha256": (
            _canonical_pretty_json_file_sha256(processing)
        ),
    }
    mismatches = [
        field
        for field, expected in expected_top.items()
        if normalized[field] != expected
    ]
    if mismatches:
        raise ReviewDerivativeLineageError(
            "Review-derivative receipt no longer matches governance/processing "
            "lineage: " + ", ".join(mismatches) + "."
        )

    event_assets = sorted(
        (
            row
            for row in processing["assets"]
            if str(row["event_id"]) == normalized["event_id"]
        ),
        key=lambda row: str(row["asset_id"]),
    )
    receipt_sources = normalized["source_rasters"]
    if len(event_assets) != len(receipt_sources):
        raise ReviewDerivativeLineageError(
            "Review-derivative source coverage is stale against the processing receipt."
        )
    for source, asset in zip(receipt_sources, event_assets, strict=True):
        expected = {
            "asset_id": asset["asset_id"],
            "event_id": asset["event_id"],
            "event_relative_role": asset["event_relative_role"],
            "product_id": asset["product_id"],
            "acquisition_time_utc": asset["acquisition_time_utc"],
            "source_sha256": asset["source_sha256"],
            "processed_file_name": asset["processed_file_name"],
            "processed_file_sha256": asset["processed_file_sha256"],
        }
        changed = [field for field, value in expected.items() if source[field] != value]
        if changed:
            raise ReviewDerivativeLineageError(
                f"Review-derivative source binding changed for {source['asset_id']}: "
                + ", ".join(changed)
            )
    governed_polarizations = _governed_source_polarizations(governance_package)
    if governed_polarizations is not None:
        for source in receipt_sources:
            expected = governed_polarizations.get(str(source["asset_id"]))
            if expected is None or tuple(source["polarizations"]) != expected:
                raise ReviewDerivativeLineageError(
                    f"Review-derivative source {source['asset_id']!r} no longer "
                    "matches the governed polarization registry."
                )

    event_grids = {
        (
            str(asset["grid_contract_sha256"]),
            str(asset["output_crs"]),
            tuple(float(value) for value in asset["affine_transform"]),
            int(asset["width_pixels"]),
            int(asset["height_pixels"]),
        )
        for asset in event_assets
    }
    if len(event_grids) != 1:
        raise ReviewDerivativeLineageError(
            "Processing receipt no longer has one derivative source grid."
        )
    grid_hash, output_crs, affine, width, height = next(iter(event_grids))
    if normalized["grid_contract_sha256"] != grid_hash:
        raise ReviewDerivativeLineageError(
            "Review-derivative grid hash no longer matches the processing receipt."
        )
    for layer in normalized["layers"]:
        if (
            layer["output_crs"] != output_crs
            or tuple(float(value) for value in layer["affine_transform"]) != affine
            or layer["width_pixels"] != width
            or layer["height_pixels"] != height
        ):
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {layer['derivative_id']!r} no longer "
                "matches the processing-receipt common grid."
            )

    if review_manifest is not None:
        _validate_review_manifest_binding(normalized, _coerce_frame(review_manifest))
    if context_manifest is not None:
        _validate_context_binding(normalized, _coerce_frame(context_manifest))
    return normalized


def validate_derivative_context_against_receipt(
    receipt: ReceiptInput,
    *,
    review_manifest: TabularInput,
    context_manifest: TabularInput,
) -> dict[str, Any]:
    """Validate reviewer rows against a self-hashed receipt without external I/O."""

    normalized = load_review_derivative_lineage_receipt(receipt)
    _validate_review_manifest_binding(normalized, _coerce_frame(review_manifest))
    _validate_context_binding(normalized, _coerce_frame(context_manifest))
    return normalized


def _validated_processing_and_governance(
    processing_alignment_receipt: ProcessingReceiptInput,
    *,
    governance_package: str | Path | None,
    allow_ungoverned_fixture: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if governance_package is None:
        if not allow_ungoverned_fixture:
            raise ReviewDerivativeLineageError(
                "A validated governance package is required for reviewer derivatives. "
                "Synthetic tests must opt in explicitly."
            )
        try:
            processing = load_processing_alignment_receipt(
                processing_alignment_receipt
            )
        except ProcessingAlignmentError as exc:
            raise ReviewDerivativeLineageError(str(exc)) from exc
        if any(
            row["source_license_status"] == "approved_with_provider_conditions"
            for row in processing["assets"]
        ):
            raise ReviewDerivativeLineageError(
                "Conditionally approved processing evidence cannot use the "
                "ungoverned-fixture escape hatch."
            )
        governance = {
            "governance_package_id": "",
            "governance_package_manifest_sha256": "",
            "governance_package_seal_sha256": "",
            "governance_binding_status": "synthetic_fixture_only",
            "production_review_eligible": False,
        }
        return processing, governance
    root = Path(governance_package)
    try:
        seal = validate_rights_clearance_package(root)
        processing = validate_processing_alignment_receipt(
            processing_alignment_receipt,
            root / "events.csv",
            root / "source_assets.csv",
            governance_package=root,
        )
    except (RightsClearanceError, ProcessingAlignmentError) as exc:
        raise ReviewDerivativeLineageError(str(exc)) from exc
    governance = {
        "governance_package_id": str(seal["package_id"]),
        "governance_package_manifest_sha256": str(
            seal["package_manifest_sha256"]
        ),
        "governance_package_seal_sha256": str(seal["seal_sha256"]),
        "governance_binding_status": "validated",
        "production_review_eligible": True,
    }
    return processing, governance


def _validate_review_manifest_binding(
    receipt: Mapping[str, Any],
    review: pd.DataFrame,
) -> None:
    required = {
        "event_id",
        "grid_contract_sha256",
        "source_registry_sha256",
        "processing_alignment_receipt_sha256",
    }
    missing = sorted(required - set(review.columns))
    if missing or review.empty:
        raise ReviewDerivativeLineageError(
            "Review manifest is empty or lacks derivative-lineage fields: "
            + ", ".join(missing)
        )
    expected = {
        "event_id": str(receipt["event_id"]),
        "grid_contract_sha256": str(receipt["grid_contract_sha256"]),
        "source_registry_sha256": str(receipt["source_registry_sha256"]),
        "processing_alignment_receipt_sha256": str(
            receipt["processing_alignment_receipt_sha256"]
        ),
    }
    changed = [
        field
        for field, value in expected.items()
        if set(review[field].astype(str)) != {value}
    ]
    if changed:
        raise ReviewDerivativeLineageError(
            "Review regions do not match the derivative receipt: "
            + ", ".join(changed)
            + "."
        )


def _validate_context_binding(
    receipt: Mapping[str, Any],
    context: pd.DataFrame,
) -> None:
    required = {
        "context_layer_id",
        "event_id",
        "layer_role",
        "source_registry_sha256",
        "source_asset_id",
        "source_product_id",
        "display_name",
        "path_hint",
        "crs",
        "acquisition_time_utc",
        "source_sha256",
        "processed_layer_sha256",
        "allowed_for_blinded_review",
        "confidence_class",
        "assumptions",
    }
    missing = sorted(required - set(context.columns))
    if missing:
        raise ReviewDerivativeLineageError(
            "Context manifest lacks derivative-lineage fields: " + ", ".join(missing)
        )
    derivative = context.loc[
        context["layer_role"].astype(str).isin(DERIVATIVE_CONTEXT_LAYER_ROLES)
    ].copy()
    expected_layers = {
        str(row["derivative_id"]): row for row in receipt["layers"]
    }
    actual_ids = list(derivative["context_layer_id"].astype(str))
    if set(actual_ids) != set(expected_layers) or len(actual_ids) != len(set(actual_ids)):
        raise ReviewDerivativeLineageError(
            "Context derivatives must exactly and uniquely cover the receipt layers."
        )
    for raw in derivative.to_dict(orient="records"):
        derivative_id = str(raw["context_layer_id"])
        layer = expected_layers[derivative_id]
        expected = {
            "event_id": receipt["event_id"],
            "layer_role": layer["layer_role"],
            "source_registry_sha256": receipt["source_registry_sha256"],
            "source_asset_id": derivative_id,
            "source_product_id": receipt["derivative_set_id"],
            "display_name": layer["display_name"],
            "path_hint": layer["path_hint"],
            "crs": layer["output_crs"],
            "acquisition_time_utc": layer["acquisition_time_utc"],
            "source_sha256": receipt["source_raster_binding_sha256"],
            "processed_layer_sha256": layer["output_file_sha256"],
            "confidence_class": layer["confidence_class"],
            "assumptions": layer["assumptions"],
        }
        changed = [field for field, value in expected.items() if raw[field] != value]
        if changed:
            raise ReviewDerivativeLineageError(
                f"Context derivative {derivative_id!r} does not match its receipt: "
                + ", ".join(changed)
                + "."
            )
        if _strict_bool(
            raw["allowed_for_blinded_review"], "allowed_for_blinded_review"
        ) is not True:
            raise ReviewDerivativeLineageError(
                f"Context derivative {derivative_id!r} is not approved for blinded review."
            )


def _verify_receipt_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != _RECEIPT_KEYS:
        raise ReviewDerivativeLineageError(
            "Review-derivative receipt has unexpected or missing fields."
        )
    receipt = dict(payload)
    if receipt["artifact_schema"] != REVIEW_DERIVATIVE_LINEAGE_RECEIPT_SCHEMA:
        raise ReviewDerivativeLineageError(
            "Unsupported review-derivative receipt schema."
        )
    if receipt["validator"] != REVIEW_DERIVATIVE_VALIDATOR_ID:
        raise ReviewDerivativeLineageError(
            "Unsupported review-derivative validator."
        )
    _utc_text(receipt["validated_at_utc"], "validated_at_utc")
    _utc_text(receipt["generated_at_utc"], "generated_at_utc")
    validated_timestamp = datetime.fromisoformat(
        str(receipt["validated_at_utc"])[:-1] + "+00:00"
    )
    generated_timestamp = datetime.fromisoformat(
        str(receipt["generated_at_utc"])[:-1] + "+00:00"
    )
    if validated_timestamp < generated_timestamp:
        raise ReviewDerivativeLineageError(
            "Review-derivative validation cannot precede generation."
        )
    _identifier(receipt["derivative_set_id"], "derivative_set_id")
    _identifier(receipt["event_id"], "event_id")
    _meaningful_text(receipt["processing_software"], "processing_software")
    _meaningful_text(
        receipt["processing_software_version"], "processing_software_version"
    )
    for field in (
        "event_registry_sha256",
        "source_registry_sha256",
        "processing_alignment_receipt_sha256",
        "processing_alignment_receipt_canonical_file_sha256",
        "grid_contract_sha256",
        "source_raster_binding_sha256",
        "build_spec_sha256",
        "receipt_sha256",
    ):
        _sha256_text(receipt[field], field)
    _verify_governance_binding(receipt)
    _require_safe_flags(receipt, label="review-derivative receipt")
    if receipt["formal_review_display_only"] is not True:
        raise ReviewDerivativeLineageError(
            "Review-derivative receipt is not display-only."
        )
    if receipt["allowed_for_blinded_review"] is not True:
        raise ReviewDerivativeLineageError(
            "Review-derivative receipt is not approved for blinded review."
        )
    _meaningful_text(receipt["assumptions"], "assumptions")

    sources = receipt["source_rasters"]
    if not isinstance(sources, list) or not 2 <= len(sources) <= 4:
        raise ReviewDerivativeLineageError(
            "Review-derivative receipt must bind two to four polarization source rasters."
        )
    source_ids: list[str] = []
    source_roles: list[str] = []
    for index, row in enumerate(sources):
        if not isinstance(row, Mapping) or set(row) != _SOURCE_RECEIPT_KEYS:
            raise ReviewDerivativeLineageError(
                f"Review-derivative source {index} has unexpected or missing fields."
            )
        source_ids.append(_identifier(row["asset_id"], f"source {index} asset_id"))
        if row["event_id"] != receipt["event_id"]:
            raise ReviewDerivativeLineageError(
                f"Review-derivative source {index} event_id mismatch."
            )
        role = _canonical_text(
            row["event_relative_role"], f"source {index} event_relative_role"
        )
        if role not in {"pre_event", "event_time"}:
            raise ReviewDerivativeLineageError(
                f"Review-derivative source {index} has unsupported event role."
            )
        source_roles.append(role)
        for field in ("product_id", "processed_file_name"):
            _meaningful_text(row[field], f"source {index} {field}")
        _safe_file_name(row["processed_file_name"], f"source {index} processed_file_name")
        polarizations, bands = _polarization_binding(
            row["polarizations"],
            row["band_by_polarization"],
            label=f"source {index}",
        )
        if list(polarizations) != row["polarizations"] or bands != row[
            "band_by_polarization"
        ]:
            raise ReviewDerivativeLineageError(
                f"Review-derivative source {index} polarization binding is not canonical."
            )
        _utc_text(row["acquisition_time_utc"], f"source {index} acquisition_time_utc")
        _sha256_text(row["source_sha256"], f"source {index} source_sha256")
        _sha256_text(
            row["processed_file_sha256"], f"source {index} processed_file_sha256"
        )
    if source_ids != sorted(set(source_ids)) or set(source_roles) != {
        "pre_event",
        "event_time",
    }:
        raise ReviewDerivativeLineageError(
            "Review-derivative sources must be unique/sorted and cover pre/event roles."
        )
    if _canonical_json_sha256(sources) != receipt["source_raster_binding_sha256"]:
        raise ReviewDerivativeLineageError(
            "Review-derivative source-raster binding hash mismatch."
        )
    source_by_role_polarization = _index_source_polarizations(sources)

    layers = receipt["layers"]
    if (
        not isinstance(receipt["layer_count"], int)
        or isinstance(receipt["layer_count"], bool)
        or receipt["layer_count"] != 3
        or not isinstance(layers, list)
        or len(layers) != receipt["layer_count"]
    ):
        raise ReviewDerivativeLineageError(
            "Review-derivative receipt layer_count must be exactly three."
        )
    roles: list[str] = []
    ids: list[str] = []
    for index, row in enumerate(layers):
        if not isinstance(row, Mapping) or set(row) != _LAYER_RECEIPT_KEYS:
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {index} has unexpected or missing fields."
            )
        _require_safe_flags(row, label=f"review-derivative layer {index}")
        if row["formal_review_display_only"] is not True or row[
            "allowed_for_blinded_review"
        ] is not True:
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {index} is not approved display-only evidence."
            )
        derivative_id = _identifier(row["derivative_id"], f"layer {index} derivative_id")
        ids.append(derivative_id)
        if row["event_id"] != receipt["event_id"]:
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {derivative_id!r} event mismatch."
            )
        role = _canonical_text(row["layer_role"], f"layer {index} layer_role")
        if role not in DERIVATIVE_CONTEXT_LAYER_ROLES:
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {derivative_id!r} has unsupported role."
            )
        roles.append(role)
        if row["source_binding_sha256"] != receipt["source_raster_binding_sha256"]:
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {derivative_id!r} source binding mismatch."
            )
        if row["source_product_id"] != receipt["derivative_set_id"]:
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {derivative_id!r} product binding mismatch."
            )
        if row["output_crs"] == "" or row["output_crs"] != str(row["output_crs"]).strip():
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {derivative_id!r} has invalid CRS."
            )
        _affine(row["affine_transform"], f"layer {index} affine_transform")
        _positive_int(row["width_pixels"], f"layer {index} width_pixels")
        _positive_int(row["height_pixels"], f"layer {index} height_pixels")
        if not isinstance(row["output_file_size_bytes"], int) or isinstance(
            row["output_file_size_bytes"], bool
        ) or row["output_file_size_bytes"] < 0:
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {derivative_id!r} has invalid file size."
            )
        for field in (
            "output_file_name",
            "display_name",
            "path_hint",
            "nodata_convention",
            "output_dtype",
            "assumptions",
        ):
            _meaningful_text(row[field], f"layer {index} {field}")
        _safe_file_name(row["output_file_name"], f"layer {index} output_file_name")
        _safe_path_hint(row["path_hint"], f"layer {index} path_hint")
        _utc_text(row["acquisition_time_utc"], f"layer {index} acquisition_time_utc")
        for field in (
            "output_file_sha256",
            "source_binding_sha256",
            "transformation_parameters_sha256",
            "display_parameters_sha256",
        ):
            _sha256_text(row[field], f"layer {index} {field}")
        if _canonical_json_sha256(row["transformation_parameters"]) != row[
            "transformation_parameters_sha256"
        ]:
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {derivative_id!r} transformation hash mismatch."
            )
        if _canonical_json_sha256(row["display_parameters"]) != row[
            "display_parameters_sha256"
        ]:
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {derivative_id!r} display hash mismatch."
            )
        confidence = _canonical_text(row["confidence_class"], f"layer {index} confidence_class")
        if confidence not in {"high", "medium", "low"}:
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {derivative_id!r} has invalid confidence."
            )
    if roles != sorted(DERIVATIVE_CONTEXT_LAYER_ROLES) or len(ids) != len(set(ids)):
        raise ReviewDerivativeLineageError(
            "Review-derivative layers must be unique and sorted by layer_role."
        )

    layer_id_by_role = {
        str(row["layer_role"]): str(row["derivative_id"]) for row in layers
    }
    for row in layers:
        role = str(row["layer_role"])
        validated_transform = _validate_transformation_parameters(
            row["transformation_parameters"],
            layer_role=role,
            layer_id_by_role=layer_id_by_role,
            source_by_role_polarization=source_by_role_polarization,
        )
        validated_display = _validate_display_parameters(
            row["display_parameters"], layer_role=role
        )
        if (
            validated_transform != row["transformation_parameters"]
            or validated_display != row["display_parameters"]
        ):
            raise ReviewDerivativeLineageError(
                f"Review-derivative layer {row['derivative_id']!r} parameters "
                "are not canonical."
            )

    normalized_spec = {
        "artifact_schema": REVIEW_DERIVATIVE_BUILD_SPEC_SCHEMA,
        "derivative_set_id": receipt["derivative_set_id"],
        "event_id": receipt["event_id"],
        "generated_at_utc": receipt["generated_at_utc"],
        "processing_software": receipt["processing_software"],
        "processing_software_version": receipt["processing_software_version"],
        "source_rasters": sources,
        "layers": layers,
        "assumptions": receipt["assumptions"],
        "formal_review_display_only": True,
        "allowed_for_blinded_review": True,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    if _canonical_json_sha256(normalized_spec) != receipt["build_spec_sha256"]:
        raise ReviewDerivativeLineageError(
            "Review-derivative normalized build-spec hash mismatch."
        )
    unsigned = dict(receipt)
    supplied_hash = unsigned.pop("receipt_sha256")
    if _canonical_json_sha256(unsigned) != supplied_hash:
        raise ReviewDerivativeLineageError(
            "Review-derivative receipt self-hash mismatch."
        )
    return receipt


def _verify_governance_binding(receipt: Mapping[str, Any]) -> None:
    status = receipt["governance_binding_status"]
    production = receipt["production_review_eligible"]
    if status == "validated":
        if production is not True:
            raise ReviewDerivativeLineageError(
                "Validated derivative governance must be production-review eligible."
            )
        _identifier(receipt["governance_package_id"], "governance_package_id")
        _sha256_text(
            receipt["governance_package_manifest_sha256"],
            "governance_package_manifest_sha256",
        )
        _sha256_text(
            receipt["governance_package_seal_sha256"],
            "governance_package_seal_sha256",
        )
    elif status == "synthetic_fixture_only":
        if production is not False or any(
            receipt[field]
            for field in (
                "governance_package_id",
                "governance_package_manifest_sha256",
                "governance_package_seal_sha256",
            )
        ):
            raise ReviewDerivativeLineageError(
                "Synthetic derivative governance must be blank and production-ineligible."
            )
    else:
        raise ReviewDerivativeLineageError(
            "Unsupported derivative governance_binding_status."
        )


def _validate_transformation_parameters(
    value: object,
    *,
    layer_role: str,
    layer_id_by_role: Mapping[str, str],
    source_by_role_polarization: Mapping[
        tuple[str, str], Mapping[str, Any]
    ],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewDerivativeLineageError(
            f"{layer_role} transformation_parameters must be an object."
        )
    params = dict(value)
    if layer_role in {"vv_change", "vh_change"}:
        if set(params) != _CHANGE_TRANSFORM_KEYS:
            raise ReviewDerivativeLineageError(
                f"{layer_role} transformation_parameters have unexpected or missing fields."
            )
        polarization = "VV" if layer_role == "vv_change" else "VH"
        pre_source = source_by_role_polarization[("pre_event", polarization)]
        event_source = source_by_role_polarization[("event_time", polarization)]
        expected = {
            "operation": "pre_minus_event_db",
            "expression": "pre_db - event_db",
            "polarization": polarization,
            "pre_input_asset_id": pre_source["asset_id"],
            "event_input_asset_id": event_source["asset_id"],
            "pre_band": pre_source["band_by_polarization"][polarization],
            "event_band": event_source["band_by_polarization"][polarization],
            "input_units": "dB",
            "output_units": "dB_change",
            "validity_rule": "valid_where_both_inputs_valid",
        }
        changed = [field for field, expected_value in expected.items() if params[field] != expected_value]
        if changed:
            raise ReviewDerivativeLineageError(
                f"{layer_role} transformation is not the canonical pre-minus-event "
                "dB change: " + ", ".join(changed) + "."
            )
        return params
    if set(params) != _COMPOSITE_TRANSFORM_KEYS:
        raise ReviewDerivativeLineageError(
            "Fixed-stretch composite transformation_parameters have unexpected "
            "or missing fields."
        )
    expected_ids = [
        layer_id_by_role["vv_change"],
        layer_id_by_role["vh_change"],
    ]
    if (
        params["operation"] != "fixed_stretch_rgb_composite"
        or params["input_derivative_ids"] != expected_ids
        or params["validity_rule"] != "valid_where_all_inputs_valid"
        or _finite_number(params["channel_min"], "channel_min") != 0.0
        or _finite_number(params["channel_max"], "channel_max") != 255.0
    ):
        raise ReviewDerivativeLineageError(
            "Fixed-stretch composite must bind VV/VH derivatives, shared valid "
            "support, and explicit 0..255 channels."
        )
    for field in ("red_expression", "green_expression", "blue_expression"):
        _meaningful_text(params[field], field)
    _reject_dynamic_parameters(params, "fixed-stretch composite transformation")
    return params


def _validate_display_parameters(value: object, *, layer_role: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewDerivativeLineageError(
            f"{layer_role} display_parameters must be an object."
        )
    params = dict(value)
    _reject_dynamic_parameters(params, f"{layer_role} display parameters")
    if layer_role in {"vv_change", "vh_change"}:
        if set(params) != _CHANGE_DISPLAY_KEYS:
            raise ReviewDerivativeLineageError(
                f"{layer_role} display_parameters have unexpected or missing fields."
            )
        minimum = _finite_number(params["stretch_min"], "stretch_min")
        maximum = _finite_number(params["stretch_max"], "stretch_max")
        gamma = _finite_number(params["gamma"], "gamma")
        if (
            params["renderer"] != "single_band_fixed_stretch"
            or minimum >= maximum
            or minimum >= 0
            or maximum <= 0
            or gamma <= 0
            or params["clamp"] is not True
        ):
            raise ReviewDerivativeLineageError(
                f"{layer_role} display must use an explicit clamped fixed stretch."
        )
        _identifier(params["color_map_id"], "color_map_id")
        stops = params["color_stops"]
        if not isinstance(stops, list) or len(stops) != 3:
            raise ReviewDerivativeLineageError(
                f"{layer_role} color_stops must contain fixed min/zero/max entries."
            )
        expected_values = (minimum, 0.0, maximum)
        for index, (stop, expected_value) in enumerate(
            zip(stops, expected_values, strict=True)
        ):
            if not isinstance(stop, Mapping) or set(stop) != {"value", "hex"}:
                raise ReviewDerivativeLineageError(
                    f"{layer_role} color stop {index} has an invalid schema."
                )
            if _finite_number(stop["value"], "color stop value") != expected_value:
                raise ReviewDerivativeLineageError(
                    f"{layer_role} color stops must be fixed at min, zero, and max."
                )
            if re.fullmatch(r"#[0-9A-F]{6}", str(stop["hex"])) is None:
                raise ReviewDerivativeLineageError(
                    f"{layer_role} color stop {index} must use uppercase #RRGGBB."
                )
        _validate_resampling(params["resampling"])
        return params
    if set(params) != _COMPOSITE_DISPLAY_KEYS:
        raise ReviewDerivativeLineageError(
            "Fixed-stretch composite display_parameters have unexpected or missing fields."
        )
    if (
        params["renderer"] != "rgb_pre_stretched"
        or params["red_band"] != 1
        or params["green_band"] != 2
        or params["blue_band"] != 3
        or _finite_number(params["gamma"], "gamma") <= 0
    ):
        raise ReviewDerivativeLineageError(
            "Fixed-stretch composite display must use explicit RGB bands and gamma."
        )
    _validate_resampling(params["resampling"])
    return params


def _reject_dynamic_parameters(value: Mapping[str, Any], label: str) -> None:
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=True).lower()
    used = [term for term in _FORBIDDEN_DYNAMIC_DISPLAY_TERMS if term in serialized]
    if used:
        raise ReviewDerivativeLineageError(
            f"{label} cannot depend on scene-derived/dynamic display terms: "
            + ", ".join(used)
            + "."
        )


def _validate_resampling(value: object) -> None:
    if value not in {"nearest", "bilinear"}:
        raise ReviewDerivativeLineageError(
            "Display resampling must be exactly nearest or bilinear."
        )


def _load_build_spec(source: BuildSpecInput) -> dict[str, Any]:
    if isinstance(source, Mapping):
        payload: Any = dict(source)
    else:
        path = Path(source)
        if path.suffix.lower() != ".json":
            raise ReviewDerivativeLineageError(
                "Review-derivative build spec must be a .json file."
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReviewDerivativeLineageError(
                f"Could not load review-derivative build spec: {path}"
            ) from exc
    if not isinstance(payload, Mapping) or set(payload) != _BUILD_SPEC_KEYS:
        raise ReviewDerivativeLineageError(
            "Review-derivative build spec has unexpected or missing fields."
        )
    spec = dict(payload)
    if spec["artifact_schema"] != REVIEW_DERIVATIVE_BUILD_SPEC_SCHEMA:
        raise ReviewDerivativeLineageError(
            "Unsupported review-derivative build-spec schema."
        )
    return spec


def _event_time_acquisition(source_rows: list[dict[str, Any]]) -> str:
    values = sorted({
        str(row["acquisition_time_utc"])
        for row in source_rows
        if row["event_relative_role"] == "event_time"
    })
    if len(values) != 1:
        raise ReviewDerivativeLineageError(
            "Derivative sources do not identify one event-time acquisition."
        )
    return values[0]


def _polarization_binding(
    polarizations_value: object,
    bands_value: object,
    *,
    label: str,
) -> tuple[tuple[str, ...], dict[str, str]]:
    if not isinstance(polarizations_value, list) or not polarizations_value:
        raise ReviewDerivativeLineageError(
            f"{label}.polarizations must be a non-empty JSON list."
        )
    supplied: list[str] = []
    for index, value in enumerate(polarizations_value):
        polarization = _canonical_text(
            value, f"{label}.polarizations[{index}]"
        ).upper()
        if polarization not in {"VV", "VH"}:
            raise ReviewDerivativeLineageError(
                f"{label}.polarizations supports only VV and VH."
            )
        supplied.append(polarization)
    if len(supplied) != len(set(supplied)):
        raise ReviewDerivativeLineageError(
            f"{label}.polarizations contains duplicates."
        )
    canonical = tuple(
        polarization for polarization in ("VV", "VH") if polarization in supplied
    )
    if not isinstance(bands_value, Mapping) or set(bands_value) != set(canonical):
        raise ReviewDerivativeLineageError(
            f"{label}.band_by_polarization must exactly cover its polarizations."
        )
    bands = {
        polarization: _meaningful_text(
            bands_value[polarization],
            f"{label}.band_by_polarization.{polarization}",
        )
        for polarization in canonical
    }
    return canonical, bands


def _index_source_polarizations(
    sources: list[dict[str, Any]] | list[Mapping[str, Any]],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    indexed: dict[tuple[str, str], Mapping[str, Any]] = {}
    for source in sources:
        role = str(source["event_relative_role"])
        for polarization in source["polarizations"]:
            key = (role, str(polarization))
            if key in indexed:
                raise ReviewDerivativeLineageError(
                    "Derivative sources ambiguously duplicate "
                    f"{role}/{polarization}."
                )
            indexed[key] = source
    expected = {
        (role, polarization)
        for role in ("pre_event", "event_time")
        for polarization in ("VV", "VH")
    }
    if set(indexed) != expected:
        raise ReviewDerivativeLineageError(
            "Derivative sources must exactly cover pre/event VV and VH."
        )
    return indexed


def _governed_source_polarizations(
    governance_package: str | Path | None,
) -> dict[str, tuple[str, ...]] | None:
    if governance_package is None:
        return None
    path = Path(governance_package) / "source_assets.csv"
    try:
        frame = pd.read_csv(path, dtype=str).fillna("")
    except (OSError, ValueError) as exc:
        raise ReviewDerivativeLineageError(
            f"Could not load governed source polarizations: {path}"
        ) from exc
    required = {"asset_id", "polarizations"}
    if not required.issubset(frame.columns) or frame.empty:
        raise ReviewDerivativeLineageError(
            "Governed source registry lacks polarization evidence."
        )
    result: dict[str, tuple[str, ...]] = {}
    for row in frame.to_dict(orient="records"):
        asset_id = _identifier(row["asset_id"], "governed asset_id")
        tokens = {
            token.upper()
            for token in re.split(r"[,;/\s]+", str(row["polarizations"]).strip())
            if token
        }
        if not tokens or not tokens.issubset({"VV", "VH"}):
            raise ReviewDerivativeLineageError(
                f"Governed source {asset_id!r} has unsupported polarizations."
            )
        result[asset_id] = tuple(
            polarization for polarization in ("VV", "VH") if polarization in tokens
        )
    return result


def _require_safe_flags(row: Mapping[str, Any], *, label: str) -> None:
    expected = {
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    changed = [field for field, value in expected.items() if row.get(field) is not value]
    if changed:
        raise ReviewDerivativeLineageError(
            f"{label} has unsafe or non-boolean fields: {', '.join(changed)}."
        )


def _coerce_frame(source: TabularInput) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    return pd.read_csv(source, dtype=str).fillna("")


def _coerce_validated_at(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0)
    if isinstance(value, datetime):
        timestamp = value
    else:
        try:
            timestamp = parse_utc_datetime(value, "validated_at_utc")
        except EventRegistryError as exc:
            raise ReviewDerivativeLineageError(str(exc)) from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ReviewDerivativeLineageError(
            "validated_at_utc must be timezone-aware."
        )
    return timestamp.astimezone(UTC).replace(microsecond=0)


def _utc_text(value: object, field: str) -> str:
    text = _canonical_text(value, field)
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z",
        text,
    ):
        raise ReviewDerivativeLineageError(
            f"{field} must be an ISO-8601 UTC timestamp with seconds and optional "
            "fractional seconds ending in Z."
        )
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ReviewDerivativeLineageError(f"{field} is invalid.") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ReviewDerivativeLineageError(f"{field} must be UTC.")
    return text


def _identifier(value: object, field: str) -> str:
    text = _canonical_text(value, field)
    if _IDENTIFIER_PATTERN.fullmatch(text) is None:
        raise ReviewDerivativeLineageError(f"{field} has invalid characters.")
    return text


def _meaningful_text(value: object, field: str) -> str:
    text = _canonical_text(value, field)
    if text.lower() in {"unknown", "n/a", "na", "none", "pending", "tbd"}:
        raise ReviewDerivativeLineageError(f"{field} must not be a placeholder.")
    return text


def _canonical_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReviewDerivativeLineageError(
            f"{field} must be a non-empty canonical string."
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _canonical_text(value, field)
    if _SHA256_PATTERN.fullmatch(text) is None:
        raise ReviewDerivativeLineageError(
            f"{field} must be a lowercase complete SHA-256."
        )
    return text


def _safe_path_hint(value: object, field: str) -> str:
    text = _meaningful_text(value, field)
    try:
        reject_absolute_local_path(text)
    except EventRegistryError as exc:
        raise ReviewDerivativeLineageError(f"Unsafe {field}: {exc}") from exc
    return text


def _file_path(value: object, field: str) -> Path:
    text = _canonical_text(value, field)
    path = Path(text)
    if not path.is_file():
        raise ReviewDerivativeLineageError(f"{field} does not exist: {path}")
    return path


def _safe_file_name(value: object, field: str) -> str:
    text = _meaningful_text(value, field)
    if Path(text).name != text or "/" in text or "\\" in text:
        raise ReviewDerivativeLineageError(
            f"{field} must be a safe base file name."
        )
    return text


def _affine(value: object, field: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != 6:
        raise ReviewDerivativeLineageError(f"{field} must contain six numbers.")
    return tuple(_finite_number(item, field) for item in value)


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise ReviewDerivativeLineageError(f"{field} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ReviewDerivativeLineageError(f"{field} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ReviewDerivativeLineageError(f"{field} must be a finite number.")
    return number


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ReviewDerivativeLineageError(f"{field} must be a positive integer.")
    return value


def _strict_bool(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise ReviewDerivativeLineageError(f"{field} must be an explicit boolean.")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReviewDerivativeLineageError(
            "Derivative evidence must be finite canonical JSON."
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _canonical_pretty_json_file_sha256(value: Mapping[str, Any]) -> str:
    encoded = (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
