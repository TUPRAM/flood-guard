"""Derive provisional, fully observed query cores from aligned pilot rasters.

This bridge sits *before* canonical grid-manifest construction.  It proves
which 256-cell storage tiles and 32-cell query cores are supported by all four
Sentinel-1 observations and wholly contained by an explicitly approved WGS84
AOI.  It never imputes nodata and deliberately does not consume or replace the
processing/alignment receipt and source-rights gates required by
``build_grid_manifests``.

The emitted tile-assignment rows are therefore inputs awaiting downstream
rights/processing validation, not canonical tiles.  Parent tiles with at least
one supported/AOI-contained core are emitted with their observed joint-valid
fraction.  They are safe only when the canonical builder is also given this
self-hashed derivation as its explicit query allowlist; callers without an
allowlist retain the older whole-tile semantics.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping

import numpy as np
import pandas as pd

from floodguard.label_factory.context_alignment import (
    CONTEXT_ALIGNMENT_MANIFEST_SCHEMA,
    ContextAlignmentError,
    load_context_alignment_manifest,
)
from floodguard.label_factory.contracts import DatasetRole
from floodguard.label_factory.event_registry import (
    EventRecord,
    EventRegistryError,
    format_utc_datetime,
    load_events,
    parse_utc_datetime,
)
from floodguard.label_factory.tiling import Bounds, QueryCore, TileCore


ARTIFACT_SCHEMA = "floodguard.supported_query_pool_derivation.v1"
BUILDER_ID = "floodguard.label_factory.supported_query_pool@v1"
TILE_SUPPORT_FILENAME = "tile_support_evidence.csv"
TILE_ASSIGNMENTS_FILENAME = "provisional_tile_assignments.csv"
SUPPORTED_QUERIES_FILENAME = "supported_query_evidence.csv"
DERIVATION_FILENAME = "supported_query_derivation.json"

APPROVED_TILE_SIZE = 256
APPROVED_QUERY_SIZE = 32
FEATURE_SCHEMA_VERSION = "sar_change_v2"
GRID_CONTRACT_TAG = "grid_contract_sha256"
AOI_TOLERANCE_DEGREES = 1e-10
CONTEXT_DOMINANCE_THRESHOLD = 0.25
STEEP_SLOPE_THRESHOLD_DEGREES = 15.0

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_RASTER_ROLES: tuple[str, ...] = (
    "pre_vv_db",
    "event_vv_db",
    "pre_vh_db",
    "event_vh_db",
)
_CONTEXT_ROLES: tuple[str, ...] = (
    "land_cover",
    "permanent_water_context",
    "slope",
)


class SupportedQueryPoolError(ValueError):
    """Raised when support evidence cannot be derived without guessing."""


@dataclass(frozen=True, slots=True)
class ApprovedAoiWgs84:
    """Closed longitude/latitude rectangle approved for one pilot build."""

    min_longitude: float
    min_latitude: float
    max_longitude: float
    max_latitude: float
    cross_border_context_included: bool

    def __post_init__(self) -> None:
        values = (
            self.min_longitude,
            self.min_latitude,
            self.max_longitude,
            self.max_latitude,
        )
        if any(isinstance(value, bool) for value in values):
            raise SupportedQueryPoolError("AOI bounds must be finite numbers.")
        numeric = tuple(float(value) for value in values)
        if not all(math.isfinite(value) for value in numeric):
            raise SupportedQueryPoolError("AOI bounds must be finite numbers.")
        min_lon, min_lat, max_lon, max_lat = numeric
        if not -180 <= min_lon < max_lon <= 180:
            raise SupportedQueryPoolError(
                "AOI longitude bounds require -180 <= min < max <= 180."
            )
        if not -90 <= min_lat < max_lat <= 90:
            raise SupportedQueryPoolError(
                "AOI latitude bounds require -90 <= min < max <= 90."
            )
        if not isinstance(self.cross_border_context_included, bool):
            raise SupportedQueryPoolError(
                "cross_border_context_included must be an explicit boolean."
            )
        object.__setattr__(self, "min_longitude", min_lon)
        object.__setattr__(self, "min_latitude", min_lat)
        object.__setattr__(self, "max_longitude", max_lon)
        object.__setattr__(self, "max_latitude", max_lat)

    def as_dict(self) -> dict[str, object]:
        """Return the exact AOI declaration stored in derivation evidence."""

        return {
            "crs": "EPSG:4326",
            "min_longitude": self.min_longitude,
            "min_latitude": self.min_latitude,
            "max_longitude": self.max_longitude,
            "max_latitude": self.max_latitude,
            "cross_border_context_included": self.cross_border_context_included,
        }


@dataclass(frozen=True, slots=True)
class SupportedQueryPoolPaths:
    """Files written by one immutable provisional support build."""

    tile_support: Path
    provisional_tile_assignments: Path
    supported_queries: Path
    derivation: Path

    def as_dict(self) -> dict[str, Path]:
        return {
            "tile_support": self.tile_support,
            "provisional_tile_assignments": self.provisional_tile_assignments,
            "supported_queries": self.supported_queries,
            "derivation": self.derivation,
        }


@dataclass(frozen=True, slots=True)
class _RasterSignature:
    crs_wkt: str
    transform: tuple[float, ...]
    width: int
    height: int
    dtype: str
    nodata: float | int | None
    grid_contract_sha256: str

    @property
    def left(self) -> float:
        return self.transform[2]

    @property
    def top(self) -> float:
        return self.transform[5]


@dataclass(frozen=True, slots=True)
class _RasterGridIndex:
    column_start: int
    row_top: int
    row_bottom: int


def build_and_write_supported_query_pool(
    *,
    event_registry_path: str | Path,
    event_id: str,
    pre_vv_path: str | Path,
    event_vv_path: str | Path,
    pre_vh_path: str | Path,
    event_vh_path: str | Path,
    approved_aoi: ApprovedAoiWgs84,
    output_directory: str | Path,
    pre_layover_shadow_path: str | Path | None = None,
    event_layover_shadow_path: str | Path | None = None,
    context_alignment_manifest_path: str | Path | None = None,
    created_at_utc: str | datetime | None = None,
) -> SupportedQueryPoolPaths:
    """Write deterministic support evidence and provisional assignment input.

    All four dB rasters must carry the event grid-contract tag and share one
    exact north-up grid.  Paired layover/shadow masks are optional because the
    FloodGuard SNAP exporter already burns them into dB nodata; if either mask
    is supplied, both are required and non-zero/nodata mask cells are excluded.

    An optional, self-hashed context-alignment manifest enables transparent
    Round-0 context strata.  Without it, strata remain explicitly unassigned.
    No weak/reference label is read by this function.
    """

    event_registry = _required_file(event_registry_path, "event registry")
    event = _select_event(event_registry, event_id)
    _require_pilot_grid_contract(event)
    created_at = _created_at(created_at_utc)
    if created_at < event.source_timestamp:
        raise SupportedQueryPoolError(
            "created_at_utc cannot predate the selected event registry metadata."
        )

    raster_paths = {
        "pre_vv_db": _required_geotiff(pre_vv_path, "pre_vv_db"),
        "event_vv_db": _required_geotiff(event_vv_path, "event_vv_db"),
        "pre_vh_db": _required_geotiff(pre_vh_path, "pre_vh_db"),
        "event_vh_db": _required_geotiff(event_vh_path, "event_vh_db"),
    }
    mask_paths = _coerce_paired_masks(
        pre_layover_shadow_path,
        event_layover_shadow_path,
    )
    context_manifest_path = (
        None
        if context_alignment_manifest_path is None
        else _required_file(
            context_alignment_manifest_path, "context alignment manifest"
        )
    )
    output = Path(output_directory)
    if output.exists():
        raise SupportedQueryPoolError(
            f"Output directory is immutable and already exists: {output}"
        )

    rasterio = _require_rasterio()
    input_hashes = {
        "event_registry": _file_sha256(event_registry),
        **{role: _file_sha256(path) for role, path in raster_paths.items()},
        **{role: _file_sha256(path) for role, path in mask_paths.items()},
    }
    input_names = {
        "event_registry": event_registry.name,
        **{role: path.name for role, path in raster_paths.items()},
        **{role: path.name for role, path in mask_paths.items()},
    }
    with ExitStack() as stack:
        datasets = {
            role: stack.enter_context(rasterio.open(path))
            for role, path in raster_paths.items()
        }
        signature, source_evidence = _validate_sar_rasters(datasets, event)
        joint_valid = _joint_valid_support(datasets)
        if mask_paths:
            mask_datasets = {
                role: stack.enter_context(rasterio.open(path))
                for role, path in mask_paths.items()
            }
            mask_evidence = _validate_masks(mask_datasets, signature, event)
            joint_valid &= _mask_support(mask_datasets)
            source_evidence.update(mask_evidence)

    context_arrays: dict[str, np.ndarray] | None = None
    context_evidence: dict[str, object]
    if context_manifest_path is not None:
        context_arrays, context_evidence, context_hashes = _load_context_layers(
            context_manifest_path,
            signature=signature,
        )
        input_hashes.update(context_hashes)
        input_names["context_alignment_manifest"] = context_manifest_path.name
        context_layers = context_evidence.get("layers", {})
        if isinstance(context_layers, dict):
            for role, record in context_layers.items():
                if isinstance(record, dict):
                    input_names[f"context_{role}"] = str(record["file_name"])
    else:
        context_evidence = {
            "status": "unassigned_context_not_provided",
            "round0_strata_assigned": False,
            "uses_weak_or_reference_labels": False,
        }

    tile_support, assignments, supported_queries = _derive_frames(
        event=event,
        signature=signature,
        joint_valid=joint_valid,
        approved_aoi=approved_aoi,
        source_timestamp=format_utc_datetime(created_at),
        rasterio=rasterio,
        context_arrays=context_arrays,
    )

    parent_existed = output.parent.exists()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    )
    try:
        artifact_frames = {
            "tile_support": (TILE_SUPPORT_FILENAME, tile_support),
            "provisional_tile_assignments": (
                TILE_ASSIGNMENTS_FILENAME,
                assignments,
            ),
            "supported_queries": (SUPPORTED_QUERIES_FILENAME, supported_queries),
        }
        output_evidence: dict[str, object] = {}
        for role, (file_name, frame) in artifact_frames.items():
            path = temporary / file_name
            frame.to_csv(
                path,
                index=False,
                lineterminator="\n",
                float_format="%.12g",
            )
            output_evidence[role] = {
                "file_name": file_name,
                "sha256": _file_sha256(path),
                "row_count": len(frame),
            }

        payload: dict[str, object] = {
            "artifact_schema": ARTIFACT_SCHEMA,
            "builder": BUILDER_ID,
            "created_at_utc": format_utc_datetime(created_at),
            "event": {
                "event_id": event.event_id,
                "dataset_role": event.dataset_role.value,
                "analysis_crs": event.analysis_crs,
                "analysis_resolution_m": event.analysis_resolution_m,
                "grid_origin_x": event.grid_origin_x,
                "grid_origin_y": event.grid_origin_y,
                "tile_size_pixels": event.tile_size_pixels,
                "query_size_pixels": event.query_size_pixels,
                "grid_id": event.grid.grid_id,
                "grid_contract_sha256": event.grid.contract_sha256,
                # Informational only.  This builder does not adjudicate rights.
                "declared_source_rights_status": event.source_rights_status,
            },
            "approved_aoi_wgs84": approved_aoi.as_dict(),
            "input_files": {
                role: {
                    "file_name": input_names[role],
                    "sha256": digest,
                }
                for role, digest in sorted(input_hashes.items())
            },
            "sar_support": {
                "required_raster_roles": list(_RASTER_ROLES),
                "source_evidence": source_evidence,
                "mask_policy": (
                    "paired_masks_required_zero_in_addition_to_four_valid_db_cells"
                    if mask_paths
                    else "four_db_nodata_masks_only_exporter_already_applied_geometry_mask"
                ),
                "no_imputation": True,
            },
            "aoi_containment_method": {
                "name": "cell_edge_densified_inverse_transform_v1",
                "source_crs": event.analysis_crs,
                "target_crs": "EPSG:4326",
                "maximum_projected_segment_length_m": event.analysis_resolution_m,
                "closed_interval_tolerance_degrees": AOI_TOLERANCE_DEGREES,
                "core_clipping_allowed": False,
            },
            "context_strata": context_evidence,
            "counts": {
                "storage_tiles_examined": len(tile_support),
                "parent_tiles_eligible_with_supported_query_allowlist": len(
                    assignments
                ),
                "whole_tiles_eligible_without_allowlist": int(
                    tile_support[
                        "eligible_for_whole_tile_manifest_without_allowlist"
                    ].sum()
                    if not tile_support.empty
                    else 0
                ),
                "fully_supported_aoi_contained_query_cores": len(supported_queries),
                "supported_queries_on_allowlisted_parent_tiles": int(
                    supported_queries[
                        "eligible_for_supported_query_allowlist_bridge"
                    ].sum()
                    if not supported_queries.empty
                    else 0
                ),
            },
            "outputs": output_evidence,
            "processing_alignment_receipt_consumed": False,
            "source_rights_gate_evaluated": False,
            "canonical_manifest_status": "not_canonical_provisional_support_only",
            "requires_downstream_processing_receipt_and_rights_gates": True,
            "query_model_only": True,
            "eligible_for_human_annotation": False,
            "eligible_for_active_selection": False,
            "eligible_for_review_queue": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "assumptions": (
                "Support means all four calibrated dB observations are present, "
                "optional paired geometry masks are clear, and the complete core "
                "is inside the approved AOI. It is not a flood label, a rights "
                "decision, a processing/alignment receipt, or operational evidence."
            ),
        }
        manifest = {**payload, "manifest_sha256": _canonical_sha256(payload)}
        (temporary / DERIVATION_FILENAME).write_text(
            json.dumps(
                manifest,
                ensure_ascii=True,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        _validate_manifest(manifest)
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if not parent_existed:
            try:
                output.parent.rmdir()
            except OSError:
                pass
        raise

    paths = SupportedQueryPoolPaths(
        tile_support=output / TILE_SUPPORT_FILENAME,
        provisional_tile_assignments=output / TILE_ASSIGNMENTS_FILENAME,
        supported_queries=output / SUPPORTED_QUERIES_FILENAME,
        derivation=output / DERIVATION_FILENAME,
    )
    load_supported_query_derivation(paths.derivation, verify_outputs=True)
    return paths


def load_supported_query_derivation(
    path: str | Path,
    *,
    verify_outputs: bool = True,
) -> dict[str, Any]:
    """Load a derivation, verify its self-hash, and optionally verify outputs."""

    manifest_path = Path(path)
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SupportedQueryPoolError(
            f"Could not read supported-query derivation: {manifest_path}"
        ) from exc
    if not isinstance(value, dict):
        raise SupportedQueryPoolError("Supported-query derivation must be an object.")
    _validate_manifest(value)
    if verify_outputs:
        outputs = value.get("outputs")
        if not isinstance(outputs, dict):
            raise SupportedQueryPoolError("Derivation outputs must be an object.")
        for role, raw_record in outputs.items():
            if not isinstance(raw_record, dict):
                raise SupportedQueryPoolError(f"Output {role!r} is malformed.")
            file_name = str(raw_record.get("file_name", ""))
            if not file_name or Path(file_name).name != file_name:
                raise SupportedQueryPoolError(
                    f"Output {role!r} must use a local file name."
                )
            expected = str(raw_record.get("sha256", "")).lower()
            if _SHA256_PATTERN.fullmatch(expected) is None:
                raise SupportedQueryPoolError(
                    f"Output {role!r} has an invalid SHA-256."
                )
            output_path = manifest_path.parent / file_name
            if not output_path.is_file() or _file_sha256(output_path) != expected:
                raise SupportedQueryPoolError(
                    f"Output {role!r} is missing or does not match its SHA-256."
                )
    return value


def _select_event(path: Path, event_id: str) -> EventRecord:
    try:
        events = load_events(path)
    except EventRegistryError as exc:
        raise SupportedQueryPoolError(str(exc)) from exc
    matches = [event for event in events if event.event_id == event_id]
    if len(matches) != 1:
        raise SupportedQueryPoolError(
            f"Expected exactly one event_id={event_id!r}; found {len(matches)}."
        )
    return matches[0]


def _require_pilot_grid_contract(event: EventRecord) -> None:
    if event.tile_size_pixels != APPROVED_TILE_SIZE:
        raise SupportedQueryPoolError(
            f"Pilot bridge requires tile_size_pixels={APPROVED_TILE_SIZE}."
        )
    if event.query_size_pixels != APPROVED_QUERY_SIZE:
        raise SupportedQueryPoolError(
            f"Pilot bridge requires query_size_pixels={APPROVED_QUERY_SIZE}."
        )
    if event.dataset_role is not DatasetRole.TRAINING_AND_QUERY_POOL:
        raise SupportedQueryPoolError(
            "Pilot support derivation is limited to training_and_query_pool; "
            "it must not open calibration, development, or untouched-test roles."
        )


def _validate_sar_rasters(
    datasets: Mapping[str, Any],
    event: EventRecord,
) -> tuple[_RasterSignature, dict[str, object]]:
    signatures: dict[str, _RasterSignature] = {}
    evidence: dict[str, object] = {}
    for role in _RASTER_ROLES:
        dataset = datasets[role]
        signature = _inspect_raster(dataset, role, event)
        signatures[role] = signature
        masked = dataset.read(1, masked=True)
        values = np.asarray(masked.data)
        valid = ~np.ma.getmaskarray(masked) & np.isfinite(values)
        evidence[role] = {
            "file_role": dataset.tags().get("floodguard_role"),
            "source_product_id": dataset.tags().get("source_product_id"),
            "valid_cell_count_before_joint_intersection": int(valid.sum()),
            "cell_count": int(valid.size),
            "valid_data_fraction_before_joint_intersection": _fraction(valid),
        }
    reference = signatures[_RASTER_ROLES[0]]
    for role, signature in signatures.items():
        if signature != reference:
            raise SupportedQueryPoolError(
                f"{role} does not share the exact four-raster grid/dtype/nodata contract."
            )
    _validate_signature_against_event(reference, event)
    return reference, evidence


def _inspect_raster(dataset: Any, role: str, event: EventRecord) -> _RasterSignature:
    if dataset.driver != "GTiff" or dataset.count != 1 or dataset.crs is None:
        raise SupportedQueryPoolError(
            f"{role} must be one single-band georeferenced GeoTIFF."
        )
    transform = dataset.transform
    tolerance = max(event.analysis_resolution_m, 1.0) * 1e-9
    if (
        not math.isclose(transform.a, event.analysis_resolution_m, abs_tol=tolerance)
        or not math.isclose(transform.e, -event.analysis_resolution_m, abs_tol=tolerance)
        or abs(transform.b) > tolerance
        or abs(transform.d) > tolerance
    ):
        raise SupportedQueryPoolError(
            f"{role} must be north-up at the event analysis resolution."
        )
    tags = dataset.tags()
    contract_hash = tags.get(GRID_CONTRACT_TAG, "").lower()
    if contract_hash != event.grid.contract_sha256:
        raise SupportedQueryPoolError(
            f"{role} grid_contract_sha256 does not match the event grid."
        )
    safety_expectations = {
        "query_model_only": "true",
        "eligible_for_decision_layer": "false",
        "eligible_for_fpps": "false",
        "eligible_for_warning": "false",
    }
    for field, expected in safety_expectations.items():
        if tags.get(field, "").lower() != expected:
            raise SupportedQueryPoolError(
                f"{role} is missing required fail-closed raster tag {field}={expected}."
            )
    declared_role = tags.get("floodguard_role", "").lower()
    expected_suffix = "vv_db" if "vv" in role else "vh_db"
    if not declared_role.endswith(expected_suffix):
        raise SupportedQueryPoolError(
            f"{role} floodguard_role must end with {expected_suffix!r}."
        )
    if not tags.get("source_product_id", "").strip():
        raise SupportedQueryPoolError(f"{role} has no source_product_id tag.")
    return _RasterSignature(
        crs_wkt=dataset.crs.to_wkt(),
        transform=tuple(float(value) for value in transform[:6]),
        width=dataset.width,
        height=dataset.height,
        dtype=dataset.dtypes[0],
        nodata=dataset.nodata,
        grid_contract_sha256=contract_hash,
    )


def _validate_signature_against_event(
    signature: _RasterSignature,
    event: EventRecord,
) -> None:
    rasterio = _require_rasterio()
    if rasterio.crs.CRS.from_wkt(signature.crs_wkt) != rasterio.crs.CRS.from_string(
        event.analysis_crs
    ):
        raise SupportedQueryPoolError("SAR CRS does not match the event analysis CRS.")
    resolution = event.analysis_resolution_m
    left = signature.left
    top = signature.top
    bottom = top - resolution * signature.height
    for value, origin, label in (
        (left, event.grid_origin_x, "left"),
        (top, event.grid_origin_y, "top"),
        (bottom, event.grid_origin_y, "bottom"),
    ):
        offset = (value - origin) / resolution
        if not math.isclose(offset, round(offset), abs_tol=1e-8):
            raise SupportedQueryPoolError(
                f"SAR raster {label} edge is not aligned to the event pixel grid."
            )


def _joint_valid_support(datasets: Mapping[str, Any]) -> np.ndarray:
    joint: np.ndarray | None = None
    for role in _RASTER_ROLES:
        masked = datasets[role].read(1, masked=True)
        values = np.asarray(masked.data)
        valid = ~np.ma.getmaskarray(masked) & np.isfinite(values)
        joint = valid if joint is None else joint & valid
    assert joint is not None
    if not bool(joint.any()):
        raise SupportedQueryPoolError(
            "The four SAR rasters have no jointly supported cells."
        )
    return joint


def _coerce_paired_masks(
    pre_path: str | Path | None,
    event_path: str | Path | None,
) -> dict[str, Path]:
    if (pre_path is None) != (event_path is None):
        raise SupportedQueryPoolError(
            "Layover/shadow masks are paired: provide both pre and event masks or neither."
        )
    if pre_path is None or event_path is None:
        return {}
    return {
        "pre_layover_shadow_mask": _required_geotiff(
            pre_path, "pre_layover_shadow_mask"
        ),
        "event_layover_shadow_mask": _required_geotiff(
            event_path, "event_layover_shadow_mask"
        ),
    }


def _validate_masks(
    datasets: Mapping[str, Any],
    reference: _RasterSignature,
    event: EventRecord,
) -> dict[str, object]:
    evidence: dict[str, object] = {}
    for role, dataset in datasets.items():
        if dataset.driver != "GTiff" or dataset.count != 1 or dataset.crs is None:
            raise SupportedQueryPoolError(f"{role} must be a single-band GeoTIFF.")
        same_grid = (
            dataset.crs.to_wkt() == reference.crs_wkt
            and tuple(float(value) for value in dataset.transform[:6])
            == reference.transform
            and dataset.width == reference.width
            and dataset.height == reference.height
        )
        if not same_grid:
            raise SupportedQueryPoolError(f"{role} does not share the SAR grid.")
        tags = dataset.tags()
        if tags.get(GRID_CONTRACT_TAG, "").lower() != event.grid.contract_sha256:
            raise SupportedQueryPoolError(f"{role} has the wrong grid contract tag.")
        if not tags.get("floodguard_role", "").lower().endswith(
            "layover_shadow_mask"
        ):
            raise SupportedQueryPoolError(
                f"{role} is not tagged as a layover/shadow mask."
            )
        masked = dataset.read(1, masked=True)
        values = np.asarray(masked.data)
        clear = ~np.ma.getmaskarray(masked) & np.isfinite(values) & (values == 0)
        evidence[role] = {
            "clear_cell_count": int(clear.sum()),
            "cell_count": int(clear.size),
            "clear_fraction": _fraction(clear),
        }
    return evidence


def _mask_support(datasets: Mapping[str, Any]) -> np.ndarray:
    support: np.ndarray | None = None
    for dataset in datasets.values():
        masked = dataset.read(1, masked=True)
        values = np.asarray(masked.data)
        clear = ~np.ma.getmaskarray(masked) & np.isfinite(values) & (values == 0)
        support = clear if support is None else support & clear
    assert support is not None
    return support


def _load_context_layers(
    manifest_path: Path,
    *,
    signature: _RasterSignature,
) -> tuple[dict[str, np.ndarray], dict[str, object], dict[str, str]]:
    try:
        manifest = load_context_alignment_manifest(manifest_path)
    except ContextAlignmentError as exc:
        raise SupportedQueryPoolError(str(exc)) from exc
    if manifest.get("artifact_schema") != CONTEXT_ALIGNMENT_MANIFEST_SCHEMA:
        raise SupportedQueryPoolError("Unsupported context alignment schema.")
    for field, expected in (
        ("query_model_only", True),
        ("eligible_for_decision_layer", False),
        ("eligible_for_fpps", False),
        ("eligible_for_warning", False),
    ):
        if manifest.get(field) is not expected:
            raise SupportedQueryPoolError(
                f"Context alignment manifest violates safety field {field}."
            )
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise SupportedQueryPoolError("Context alignment layers must be a list.")
    source_inputs = manifest.get("source_inputs")
    if not isinstance(source_inputs, list) or not source_inputs:
        raise SupportedQueryPoolError(
            "Context alignment manifest has no source-backed input records."
        )
    by_role = {
        str(row.get("layer_role")): row
        for row in layers
        if isinstance(row, dict)
    }
    missing = [role for role in _CONTEXT_ROLES if role not in by_role]
    if missing:
        raise SupportedQueryPoolError(
            "Context alignment manifest is missing layers: " + ", ".join(missing)
        )
    rasterio = _require_rasterio()
    arrays: dict[str, np.ndarray] = {}
    hashes = {"context_alignment_manifest": _file_sha256(manifest_path)}
    layer_evidence: dict[str, object] = {}
    with ExitStack() as stack:
        for role in _CONTEXT_ROLES:
            record = by_role[role]
            source_roles = record.get("source_roles")
            source_sha256s = record.get("source_sha256s")
            if (
                not isinstance(source_roles, list)
                or not source_roles
                or not isinstance(source_sha256s, dict)
                or set(map(str, source_roles)) != set(map(str, source_sha256s))
            ):
                raise SupportedQueryPoolError(
                    f"Context layer {role} lacks source-backed lineage fields."
                )
            path_hint = str(record.get("path_hint", ""))
            if not path_hint or Path(path_hint).name != path_hint:
                raise SupportedQueryPoolError(
                    f"Context layer {role} must use a local path_hint."
                )
            path = _required_geotiff(manifest_path.parent / path_hint, role)
            expected_hash = str(record.get("processed_layer_sha256", "")).lower()
            observed_hash = _file_sha256(path)
            if observed_hash != expected_hash:
                raise SupportedQueryPoolError(
                    f"Context layer {role} does not match its manifest SHA-256."
                )
            dataset = stack.enter_context(rasterio.open(path))
            if (
                dataset.count != 1
                or dataset.crs is None
                or dataset.crs.to_wkt() != signature.crs_wkt
                or tuple(float(value) for value in dataset.transform[:6])
                != signature.transform
                or dataset.width != signature.width
                or dataset.height != signature.height
            ):
                raise SupportedQueryPoolError(
                    f"Context layer {role} does not share the exact SAR grid."
                )
            masked = dataset.read(1, masked=True)
            values = np.asarray(masked.data)
            invalid = np.ma.getmaskarray(masked) | ~np.isfinite(values)
            if bool(invalid.any()):
                raise SupportedQueryPoolError(
                    f"Context layer {role} contains nodata/non-finite cells; no "
                    "context imputation is allowed."
                )
            if role == "land_cover" and not np.isin(
                values, [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
            ).all():
                raise SupportedQueryPoolError("land_cover contains unknown codes.")
            if role == "permanent_water_context" and not np.isin(
                values, [0, 1]
            ).all():
                raise SupportedQueryPoolError(
                    "permanent_water_context must contain only 0/1."
                )
            if role == "slope" and bool((values < 0).any()):
                raise SupportedQueryPoolError("slope cannot contain negative values.")
            arrays[role] = values.copy()
            hashes[f"context_{role}"] = observed_hash
            layer_evidence[role] = {
                "file_name": path.name,
                "sha256": observed_hash,
                "source_roles": record.get("source_roles"),
                "source_sha256s": record.get("source_sha256s"),
                "derivation_method": record.get("derivation_method"),
            }
    evidence: dict[str, object] = {
        "status": "assigned_from_self_hashed_aligned_context",
        "round0_strata_assigned": True,
        "context_alignment_manifest_sha256": manifest.get("manifest_sha256"),
        "context_derivation_parameters": manifest.get("derivation_parameters"),
        "layers": layer_evidence,
        "uses_weak_or_reference_labels": False,
        "rules": {
            "priority": [
                "permanent_water_edge",
                "permanent_water_interior",
                "urban",
                "steep_terrain",
                "forest",
                "cropland",
                "worldcover_water_edge",
                "worldcover_water_interior",
                "other_context",
            ],
            "permanent_water_edge": "0 < permanent_water_fraction < 1",
            "permanent_water_interior": "permanent_water_fraction == 1",
            "worldcover_water_edge": "0 < worldcover_water_fraction < 1",
            "worldcover_water_interior": "worldcover_water_fraction == 1",
            "urban": f"urban_fraction >= {CONTEXT_DOMINANCE_THRESHOLD}",
            "steep_terrain": (
                f"fraction(slope >= {STEEP_SLOPE_THRESHOLD_DEGREES}) >= "
                f"{CONTEXT_DOMINANCE_THRESHOLD}"
            ),
            "forest": f"forest_fraction >= {CONTEXT_DOMINANCE_THRESHOLD}",
            "cropland": f"cropland_fraction >= {CONTEXT_DOMINANCE_THRESHOLD}",
            "worldcover_codes": {
                "forest": [10],
                "cropland": [40],
                "urban": [50],
                "worldcover_water_context": [80],
            },
        },
    }
    return arrays, evidence, hashes


def _derive_frames(
    *,
    event: EventRecord,
    signature: _RasterSignature,
    joint_valid: np.ndarray,
    approved_aoi: ApprovedAoiWgs84,
    source_timestamp: str,
    rasterio: Any,
    context_arrays: Mapping[str, np.ndarray] | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    index = _raster_grid_index(signature, event)
    tile_size = event.tile_size_pixels
    x_first = math.floor(index.column_start / tile_size)
    x_last = math.floor((index.column_start + signature.width - 1) / tile_size)
    y_first = math.floor(index.row_bottom / tile_size)
    y_last = math.floor((index.row_top - 1) / tile_size)
    tile_rows: list[dict[str, object]] = []
    query_rows: list[dict[str, object]] = []
    assignment_rows: list[dict[str, object]] = []
    query_count = tile_size // event.query_size_pixels

    for y_index in range(y_first, y_last + 1):
        for x_index in range(x_first, x_last + 1):
            tile = TileCore(
                event_id=event.event_id,
                grid=event.grid,
                x_index=x_index,
                y_index=y_index,
                dataset_role=event.dataset_role,
            )
            tile_support, tile_covered = _extract_core_array(
                joint_valid,
                index=index,
                x_cell_start=x_index * tile_size,
                y_cell_top=(y_index + 1) * tile_size,
                size_cells=tile_size,
            )
            valid_count = int(tile_support.sum())
            tile_aoi, tile_wgs84_bounds = _bounds_within_aoi(
                tile.bounds,
                crs=event.analysis_crs,
                resolution_m=event.analysis_resolution_m,
                approved_aoi=approved_aoi,
                rasterio=rasterio,
            )
            supported_count = 0
            aoi_count = 0
            eligible_count = 0
            current_tile_queries: list[dict[str, object]] = []
            for row_index in range(query_count):
                for column_index in range(query_count):
                    query = QueryCore(
                        tile=tile,
                        row_index=row_index,
                        column_index=column_index,
                        size_cells=event.query_size_pixels,
                    )
                    row_start = row_index * event.query_size_pixels
                    column_start = column_index * event.query_size_pixels
                    query_support = tile_support[
                        row_start : row_start + event.query_size_pixels,
                        column_start : column_start + event.query_size_pixels,
                    ]
                    fully_supported = bool(query_support.all())
                    query_aoi, wgs84_bounds = _bounds_within_aoi(
                        query.bounds,
                        crs=event.analysis_crs,
                        resolution_m=event.analysis_resolution_m,
                        approved_aoi=approved_aoi,
                        rasterio=rasterio,
                    )
                    supported_count += int(fully_supported)
                    aoi_count += int(query_aoi)
                    if not fully_supported or not query_aoi:
                        continue
                    eligible_count += 1
                    context = _query_context_fields(
                        context_arrays,
                        index=index,
                        query=query,
                    )
                    current_tile_queries.append(
                        {
                            "query_region_id": query.query_region_id,
                            "tile_id": tile.tile_id,
                            "event_id": event.event_id,
                            "grid_id": event.grid.grid_id,
                            "grid_contract_sha256": event.grid.contract_sha256,
                            "query_row": row_index,
                            "query_col": column_index,
                            "query_size_pixels": event.query_size_pixels,
                            "bbox_min_x": query.bounds.min_x,
                            "bbox_min_y": query.bounds.min_y,
                            "bbox_max_x": query.bounds.max_x,
                            "bbox_max_y": query.bounds.max_y,
                            "wgs84_min_longitude": wgs84_bounds[0],
                            "wgs84_min_latitude": wgs84_bounds[1],
                            "wgs84_max_longitude": wgs84_bounds[2],
                            "wgs84_max_latitude": wgs84_bounds[3],
                            "crs": event.analysis_crs,
                            "resolution_m": event.analysis_resolution_m,
                            "dataset_role": event.dataset_role.value,
                            "overlap_group_id": f"{tile.tile_id}:BLOCK",
                            "feature_schema_version": FEATURE_SCHEMA_VERSION,
                            "joint_valid_cell_count": int(query_support.sum()),
                            "query_cell_count": int(query_support.size),
                            "valid_data_fraction": 1.0,
                            "fully_within_approved_aoi": True,
                            "core_clipped": False,
                            **context,
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
                            "source_timestamp": source_timestamp,
                            "confidence_class": "medium",
                            "assumptions": (
                                "Complete four-raster support and AOI containment only; "
                                "downstream receipt and rights gates remain mandatory."
                            ),
                        }
                    )

            whole_tile_eligible = (
                tile_covered
                and valid_count == tile_size * tile_size
                and tile_aoi
                and eligible_count == query_count * query_count
            )
            allowlist_parent_eligible = (
                tile_covered and valid_count > 0 and eligible_count > 0
            )
            for row in current_tile_queries:
                row["eligible_for_current_full_tile_manifest_bridge"] = (
                    whole_tile_eligible
                )
                row["eligible_for_supported_query_allowlist_bridge"] = (
                    allowlist_parent_eligible
                )
            query_rows.extend(current_tile_queries)
            tile_rows.append(
                {
                    "tile_id": tile.tile_id,
                    "event_id": event.event_id,
                    "grid_id": event.grid.grid_id,
                    "grid_contract_sha256": event.grid.contract_sha256,
                    "x_index": x_index,
                    "y_index": y_index,
                    "bbox_min_x": tile.bounds.min_x,
                    "bbox_min_y": tile.bounds.min_y,
                    "bbox_max_x": tile.bounds.max_x,
                    "bbox_max_y": tile.bounds.max_y,
                    "wgs84_min_longitude": tile_wgs84_bounds[0],
                    "wgs84_min_latitude": tile_wgs84_bounds[1],
                    "wgs84_max_longitude": tile_wgs84_bounds[2],
                    "wgs84_max_latitude": tile_wgs84_bounds[3],
                    "tile_cell_count": tile_size * tile_size,
                    "joint_valid_cell_count": valid_count,
                    "joint_valid_fraction": round(
                        valid_count / (tile_size * tile_size), 12
                    ),
                    "tile_fully_covered_by_raster": tile_covered,
                    "tile_fully_within_approved_aoi": tile_aoi,
                    "query_core_count": query_count * query_count,
                    "fully_supported_query_core_count": supported_count,
                    "aoi_contained_query_core_count": aoi_count,
                    "supported_and_aoi_contained_query_core_count": eligible_count,
                    "eligible_for_tile_assignments_input": allowlist_parent_eligible,
                    "eligible_for_whole_tile_manifest_without_allowlist": (
                        whole_tile_eligible
                    ),
                    "provisional_support_evidence": True,
                    "processing_alignment_receipt_validated": False,
                    "source_rights_gate_validated": False,
                    "query_model_only": True,
                    "eligible_for_decision_layer": False,
                    "eligible_for_fpps": False,
                    "eligible_for_warning": False,
                }
            )
            if allowlist_parent_eligible:
                assignment_rows.append(
                    {
                        "event_id": event.event_id,
                        "x_index": x_index,
                        "y_index": y_index,
                        "dataset_role": event.dataset_role.value,
                        "overlap_group_id": f"{tile.tile_id}:BLOCK",
                        "valid_data_fraction": round(
                            valid_count / (tile_size * tile_size), 12
                        ),
                        "feature_schema_version": FEATURE_SCHEMA_VERSION,
                        "source_timestamp": source_timestamp,
                        "confidence_class": "medium",
                        "assumptions": (
                            "Provisional parent-tile support evidence only; canonical "
                            "grid construction must validate the source registry, "
                            "processing/alignment receipt, and self-hashed supported-"
                            "query allowlist."
                        ),
                        "provisional_support_evidence": True,
                        "processing_alignment_receipt_validated": False,
                        "source_rights_gate_validated": False,
                        "supported_query_allowlist_required": True,
                        "eligible_for_canonical_manifest_without_downstream_gates": False,
                        "query_model_only": True,
                        "eligible_for_decision_layer": False,
                        "eligible_for_fpps": False,
                        "eligible_for_warning": False,
                    }
                )

    tile_frame = pd.DataFrame(tile_rows).sort_values(
        ["event_id", "y_index", "x_index"], kind="stable"
    ).reset_index(drop=True)
    assignment_frame = pd.DataFrame(assignment_rows, columns=_assignment_columns())
    if not assignment_frame.empty:
        assignment_frame = assignment_frame.sort_values(
            ["event_id", "y_index", "x_index"], kind="stable"
        ).reset_index(drop=True)
    query_frame = pd.DataFrame(query_rows, columns=_query_columns())
    if not query_frame.empty:
        query_frame = query_frame.sort_values(
            ["event_id", "tile_id", "query_row", "query_col"], kind="stable"
        ).reset_index(drop=True)
    return tile_frame, assignment_frame, query_frame


def _raster_grid_index(
    signature: _RasterSignature,
    event: EventRecord,
) -> _RasterGridIndex:
    resolution = event.analysis_resolution_m
    column_start = round((signature.left - event.grid_origin_x) / resolution)
    row_top = round((signature.top - event.grid_origin_y) / resolution)
    row_bottom = row_top - signature.height
    return _RasterGridIndex(
        column_start=column_start,
        row_top=row_top,
        row_bottom=row_bottom,
    )


def _extract_core_array(
    source: np.ndarray,
    *,
    index: _RasterGridIndex,
    x_cell_start: int,
    y_cell_top: int,
    size_cells: int,
) -> tuple[np.ndarray, bool]:
    row_offset = index.row_top - y_cell_top
    column_offset = x_cell_start - index.column_start
    output = np.zeros((size_cells, size_cells), dtype=bool)
    source_row_start = max(row_offset, 0)
    source_column_start = max(column_offset, 0)
    source_row_end = min(row_offset + size_cells, source.shape[0])
    source_column_end = min(column_offset + size_cells, source.shape[1])
    if source_row_start < source_row_end and source_column_start < source_column_end:
        output_row_start = source_row_start - row_offset
        output_column_start = source_column_start - column_offset
        output[
            output_row_start : output_row_start + source_row_end - source_row_start,
            output_column_start : (
                output_column_start + source_column_end - source_column_start
            ),
        ] = source[
            source_row_start:source_row_end,
            source_column_start:source_column_end,
        ]
    fully_covered = (
        row_offset >= 0
        and column_offset >= 0
        and row_offset + size_cells <= source.shape[0]
        and column_offset + size_cells <= source.shape[1]
    )
    return output, fully_covered


def _bounds_within_aoi(
    bounds: Bounds,
    *,
    crs: str,
    resolution_m: float,
    approved_aoi: ApprovedAoiWgs84,
    rasterio: Any,
) -> tuple[bool, tuple[float, float, float, float]]:
    width_steps = max(1, math.ceil((bounds.max_x - bounds.min_x) / resolution_m))
    height_steps = max(1, math.ceil((bounds.max_y - bounds.min_y) / resolution_m))
    xs: list[float] = []
    ys: list[float] = []
    for index in range(width_steps + 1):
        x = bounds.min_x + (bounds.max_x - bounds.min_x) * index / width_steps
        xs.extend((x, x))
        ys.extend((bounds.min_y, bounds.max_y))
    for index in range(1, height_steps):
        y = bounds.min_y + (bounds.max_y - bounds.min_y) * index / height_steps
        xs.extend((bounds.min_x, bounds.max_x))
        ys.extend((y, y))
    longitudes, latitudes = rasterio.warp.transform(crs, "EPSG:4326", xs, ys)
    envelope = (
        float(min(longitudes)),
        float(min(latitudes)),
        float(max(longitudes)),
        float(max(latitudes)),
    )
    contained = (
        envelope[0] >= approved_aoi.min_longitude - AOI_TOLERANCE_DEGREES
        and envelope[1] >= approved_aoi.min_latitude - AOI_TOLERANCE_DEGREES
        and envelope[2] <= approved_aoi.max_longitude + AOI_TOLERANCE_DEGREES
        and envelope[3] <= approved_aoi.max_latitude + AOI_TOLERANCE_DEGREES
    )
    return contained, envelope


def _query_context_fields(
    context_arrays: Mapping[str, np.ndarray] | None,
    *,
    index: _RasterGridIndex,
    query: QueryCore,
) -> dict[str, object]:
    if context_arrays is None:
        return {
            "permanent_water_fraction": "",
            "worldcover_water_fraction": "",
            "urban_fraction": "",
            "forest_fraction": "",
            "cropland_fraction": "",
            "steep_terrain_fraction": "",
            "slope_p90_degrees": "",
            "round0_stratum": "unassigned",
            "round0_stratum_assignment_status": "unassigned_context_not_provided",
            "round0_stratum_source": "none",
            "round0_stratum_basis": "context_not_provided",
            "eligible_for_round0_stratified_selection": False,
        }
    x_start = round(
        (query.bounds.min_x - query.grid.origin_x) / query.grid.resolution_m
    )
    y_top = round(
        (query.bounds.max_y - query.grid.origin_y) / query.grid.resolution_m
    )
    windows: dict[str, np.ndarray] = {}
    for role, values in context_arrays.items():
        extracted, covered = _extract_core_array(
            values,
            index=index,
            x_cell_start=x_start,
            y_cell_top=y_top,
            size_cells=query.size_cells,
        )
        if not covered:
            raise SupportedQueryPoolError(
                f"Context layer {role} does not cover supported query {query.core_id}."
            )
        # _extract_core_array is boolean-oriented; slice values directly after
        # its coverage check so categorical and floating values are preserved.
        row_offset = index.row_top - y_top
        column_offset = x_start - index.column_start
        windows[role] = values[
            row_offset : row_offset + query.size_cells,
            column_offset : column_offset + query.size_cells,
        ]
    land_cover = windows["land_cover"]
    permanent = windows["permanent_water_context"]
    slope = windows["slope"]
    permanent_fraction = float(np.mean(permanent == 1))
    worldcover_water_fraction = float(np.mean(land_cover == 80))
    urban_fraction = float(np.mean(land_cover == 50))
    forest_fraction = float(np.mean(land_cover == 10))
    cropland_fraction = float(np.mean(land_cover == 40))
    steep_fraction = float(np.mean(slope >= STEEP_SLOPE_THRESHOLD_DEGREES))
    if 0 < permanent_fraction < 1:
        stratum = "permanent_water_edge"
        basis = "0<permanent_water_fraction<1"
    elif permanent_fraction == 1:
        stratum = "permanent_water_interior"
        basis = "permanent_water_fraction=1"
    elif urban_fraction >= CONTEXT_DOMINANCE_THRESHOLD:
        stratum = "urban"
        basis = "urban_fraction>=0.25"
    elif steep_fraction >= CONTEXT_DOMINANCE_THRESHOLD:
        stratum = "steep_terrain"
        basis = "steep_terrain_fraction>=0.25"
    elif forest_fraction >= CONTEXT_DOMINANCE_THRESHOLD:
        stratum = "forest"
        basis = "forest_fraction>=0.25"
    elif cropland_fraction >= CONTEXT_DOMINANCE_THRESHOLD:
        stratum = "cropland"
        basis = "cropland_fraction>=0.25"
    elif 0 < worldcover_water_fraction < 1:
        stratum = "worldcover_water_edge"
        basis = "0<worldcover_water_fraction<1"
    elif worldcover_water_fraction == 1:
        stratum = "worldcover_water_interior"
        basis = "worldcover_water_fraction=1"
    else:
        stratum = "other_context"
        basis = "no_priority_context_rule_matched"
    return {
        "permanent_water_fraction": round(permanent_fraction, 12),
        "worldcover_water_fraction": round(worldcover_water_fraction, 12),
        "urban_fraction": round(urban_fraction, 12),
        "forest_fraction": round(forest_fraction, 12),
        "cropland_fraction": round(cropland_fraction, 12),
        "steep_terrain_fraction": round(steep_fraction, 12),
        "slope_p90_degrees": round(float(np.percentile(slope, 90)), 12),
        "round0_stratum": stratum,
        "round0_stratum_assignment_status": "assigned_context_only",
        "round0_stratum_source": "aligned_static_context_no_weak_labels",
        "round0_stratum_basis": basis,
        "eligible_for_round0_stratified_selection": False,
    }


def _query_columns() -> list[str]:
    return [
        "query_region_id", "tile_id", "event_id", "grid_id",
        "grid_contract_sha256", "query_row", "query_col", "query_size_pixels",
        "bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y",
        "wgs84_min_longitude", "wgs84_min_latitude", "wgs84_max_longitude",
        "wgs84_max_latitude", "crs", "resolution_m", "dataset_role",
        "overlap_group_id", "feature_schema_version", "joint_valid_cell_count",
        "query_cell_count", "valid_data_fraction", "fully_within_approved_aoi",
        "core_clipped", "permanent_water_fraction", "worldcover_water_fraction",
        "urban_fraction",
        "forest_fraction", "cropland_fraction", "steep_terrain_fraction",
        "slope_p90_degrees", "round0_stratum",
        "round0_stratum_assignment_status", "round0_stratum_source",
        "round0_stratum_basis", "eligible_for_round0_stratified_selection",
        "provisional_support_evidence", "processing_alignment_receipt_validated",
        "source_rights_gate_validated", "canonical_manifest_status",
        "eligible_for_human_annotation", "eligible_for_active_selection",
        "eligible_for_review_queue", "eligible_for_query_model_training",
        "query_model_only", "eligible_for_decision_layer", "eligible_for_fpps",
        "eligible_for_warning", "source_timestamp", "confidence_class",
        "assumptions", "eligible_for_current_full_tile_manifest_bridge",
        "eligible_for_supported_query_allowlist_bridge",
    ]


def _assignment_columns() -> list[str]:
    return [
        "event_id", "x_index", "y_index", "dataset_role", "overlap_group_id",
        "valid_data_fraction", "feature_schema_version", "source_timestamp",
        "confidence_class", "assumptions", "provisional_support_evidence",
        "processing_alignment_receipt_validated", "source_rights_gate_validated",
        "supported_query_allowlist_required",
        "eligible_for_canonical_manifest_without_downstream_gates",
        "query_model_only", "eligible_for_decision_layer", "eligible_for_fpps",
        "eligible_for_warning",
    ]


def _required_file(path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_file():
        raise SupportedQueryPoolError(f"{label} does not exist: {candidate}")
    return candidate


def _required_geotiff(path: str | Path, label: str) -> Path:
    candidate = _required_file(path, label)
    if candidate.suffix.lower() not in {".tif", ".tiff"}:
        raise SupportedQueryPoolError(f"{label} must be a GeoTIFF.")
    return candidate


def _created_at(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    try:
        return parse_utc_datetime(value, "created_at_utc")
    except EventRegistryError as exc:
        raise SupportedQueryPoolError(str(exc)) from exc


def _fraction(mask: np.ndarray) -> float:
    return round(float(np.asarray(mask, dtype=bool).mean()), 12)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_manifest(manifest: Mapping[str, object]) -> None:
    if manifest.get("artifact_schema") != ARTIFACT_SCHEMA:
        raise SupportedQueryPoolError("Unsupported supported-query artifact schema.")
    observed = str(manifest.get("manifest_sha256", "")).lower()
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if _SHA256_PATTERN.fullmatch(observed) is None or observed != _canonical_sha256(
        payload
    ):
        raise SupportedQueryPoolError("Supported-query derivation self-hash mismatch.")
    safety = {
        "processing_alignment_receipt_consumed": False,
        "source_rights_gate_evaluated": False,
        "requires_downstream_processing_receipt_and_rights_gates": True,
        "query_model_only": True,
        "eligible_for_human_annotation": False,
        "eligible_for_active_selection": False,
        "eligible_for_review_queue": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    for field, expected in safety.items():
        if manifest.get(field) is not expected:
            raise SupportedQueryPoolError(
                f"Supported-query derivation violates safety field {field}."
            )


def _require_rasterio() -> Any:
    try:
        import rasterio
        import rasterio.crs
        import rasterio.warp
    except ImportError as exc:
        raise SupportedQueryPoolError(
            "Supported-query derivation requires NumPy and rasterio."
        ) from exc
    return rasterio
