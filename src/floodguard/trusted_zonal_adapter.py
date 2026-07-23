"""Trusted raster-to-area aggregation for decision-eligible probabilities.

This module owns the filesystem boundary that
``aggregate_probability_cells`` intentionally cannot trust.  It copies and
hashes the named GeoAI raster from one verified descriptor, parses only that
private snapshot, and parses authoritative geometry from the exact hashed byte
buffer.  It validates lineage and spatial metadata, derives the selected
pixels itself, and signs a canonical receipt.  The signing secret is supplied
by the caller and is never serialized.

Only schema-complete ``official_input`` model runs that already pass the
FloodGuard promotion gates may use this adapter.  Fixture and candidate runs
remain report-only and are rejected here.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any

from floodguard.probability_aggregation import (
    PRIVATE_PATH_RE,
    ProbabilityAggregationError,
    _canonical_sha256,
    _linear_quantile,
    _parsed_timestamp,
    _require_exact_fields,
    _same_number,
    _same_numbers,
    _sha256,
    _validate_decision_feed_evidence,
    _validate_source_metadata,
)


RECEIPT_TYPE = "floodguard.trusted_probability_zonal"
# Version 2 binds the authoritative geometry to the exact model-run study area.
# Version 1 receipts predate that field and are intentionally not accepted for
# decision use because their geometry can be replayed across study areas.
RECEIPT_SCHEMA_VERSION = "2.0"
SIGNATURE_ALGORITHM = "HMAC-SHA256"
AREA_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")

AUTHORITATIVE_GEOMETRY_FIELDS = frozenset(
    {
        "dataset_id",
        "study_area",
        "data_version",
        "sha256",
        "source_name",
        "source_timestamp",
        "crs",
        "area_id_field",
        "area_name_field",
        "feature_count",
        "authority_status",
        "processing_allowed",
    }
)
SIGNED_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_type",
        "key_id",
        "generated_at",
        "source_timestamp",
        "dataset_mode",
        "operational_status",
        "confidence_class",
        "official_warning",
        "processing_allowed",
        "can_feed_decision_layer",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "run_id",
        "git_commit",
        "model_id",
        "model_revision",
        "geoai_version",
        "geoai_commit",
        "model_run_manifest_sha256",
        "probability_raster_receipt_sha256",
        "probability_raster_sha256",
        "authoritative_geometry_receipt_sha256",
        "authoritative_geometry_sha256",
        "probability_grid",
        "authoritative_geometry",
        "probability_threshold",
        "aggregation_method",
        "areas",
        "signature",
    }
)
PUBLIC_GEOMETRY_FIELDS = frozenset(
    {
        "dataset_id",
        "study_area",
        "data_version",
        "source_name",
        "source_timestamp",
        "crs",
        "area_id_field",
        "area_name_field",
        "feature_count",
        "authority_status",
        "processing_allowed",
        "bounds_in_probability_crs",
    }
)
AGGREGATION_METHOD_FIELDS = frozenset(
    {
        "name",
        "all_touched",
        "quantile_method",
        "statistics_version",
        "pixel_area_square_map_units",
    }
)
AREA_RESULT_FIELDS = frozenset(
    {
        "subdistrict_id",
        "subdistrict_name",
        "mean_flood_probability_0_1",
        "p90_flood_probability_0_1",
        "binary_flood_share_0_1",
        "sample_pixel_count",
        "flood_pixel_count",
        "sampled_area_square_map_units",
        "estimated_flood_area_square_map_units",
        "probability_threshold",
        "aggregation_status",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
    }
)
SIGNATURE_FIELDS = frozenset({"algorithm", "key_id", "value"})


def create_signed_zonal_receipt(
    *,
    probability_raster_path: str | Path,
    authoritative_geometry_path: str | Path,
    source_metadata: Mapping[str, object],
    probability_raster_receipt: Mapping[str, object],
    authoritative_geometry_receipt: Mapping[str, object],
    signing_key: bytes,
    key_id: str,
    generated_at: str,
) -> dict[str, Any]:
    """Aggregate an immutable probability raster by authoritative polygons.

    The raster is hashed while one verified source descriptor is copied into a
    private temporary snapshot; rasterio parses that snapshot descriptor rather
    than reopening the source path.  Geometry is parsed from the exact byte
    buffer used for its hash.  Both hashes must match the supplied lineage
    receipts.  Pixel inclusion uses the pixel-center rule
    (``all_touched=False``), and areas are sorted by their stable ID before
    canonical signing.

    Parameters
    ----------
    signing_key:
        An external HMAC key of at least 32 bytes.  The key is used in memory
        only and never appears in the returned receipt.
    generated_at:
        A caller-supplied RFC 3339 timestamp.  Requiring it explicitly keeps
        receipt generation reproducible and prevents hidden wall-clock state.
    """

    raster_path = _regular_local_file(probability_raster_path, "probability raster")
    geometry_path = _regular_local_file(
        authoritative_geometry_path, "authoritative geometry"
    )
    secret = _signing_key(signing_key)
    signing_key_id = _key_id(key_id)
    generated_time = _parsed_timestamp(generated_at, "generated_at")
    generated_at_text = generated_at.strip()

    metadata = _validate_source_metadata(source_metadata)
    if metadata.dataset_mode != "official_input":
        raise ProbabilityAggregationError(
            "Trusted zonal aggregation requires dataset_mode=official_input; "
            "fixture_demo and candidate inputs remain report-only."
        )
    if not metadata.can_feed_decision_layer:
        raise ProbabilityAggregationError(
            "Trusted zonal aggregation requires can_feed_decision_layer=true."
        )

    geometry_lineage = _validate_authoritative_geometry_receipt(
        authoritative_geometry_receipt
    )
    _require_matching_study_area(source_metadata, geometry_lineage)
    source_time = _parsed_timestamp(
        source_metadata["source_timestamp"], "source_metadata.source_timestamp"
    )
    model_manifest_time = _parsed_timestamp(
        source_metadata["generated_at"], "source_metadata.generated_at"
    )
    geometry_source_time = _parsed_timestamp(
        geometry_lineage["source_timestamp"],
        "authoritative_geometry_receipt.source_timestamp",
    )
    if generated_time < max(source_time, model_manifest_time, geometry_source_time):
        raise ProbabilityAggregationError(
            "generated_at cannot predate the probability source, model manifest, "
            "or authoritative geometry timestamp."
        )

    receipt_raster_sha = _sha256(
        probability_raster_receipt.get("probability_raster_sha256"),
        "probability_raster_receipt.probability_raster_sha256",
    )
    geometry_bytes, geometry_sha = _read_bound_bytes(
        geometry_path, "authoritative geometry"
    )
    if not hmac.compare_digest(geometry_sha, geometry_lineage["sha256"]):
        raise ProbabilityAggregationError(
            "Authoritative geometry checksum does not match its lineage receipt."
        )

    nodata = _finite_number_from_mapping(
        probability_raster_receipt.get("grid"), "nodata", "probability raster grid"
    )
    if 0.0 <= nodata <= 1.0:
        raise ProbabilityAggregationError(
            "Probability raster nodata must be outside the [0, 1] probability range."
        )
    threshold = _finite_number(
        source_metadata.get("probability_threshold"),
        "source_metadata.probability_threshold",
    )
    decision_receipt = _validate_decision_feed_evidence(
        source_metadata,
        probability_raster_receipt,
        nodata=nodata,
        probability_threshold=threshold,
    )

    with _probability_raster_snapshot(raster_path) as (
        raster_snapshot,
        raster_sha,
    ):
        if not hmac.compare_digest(raster_sha, receipt_raster_sha):
            raise ProbabilityAggregationError(
                "Probability raster checksum does not match its lineage receipt."
            )
        raster = _read_probability_raster(
            raster_snapshot,
            expected_grid=decision_receipt.probability_grid,
        )
    geometry = _read_authoritative_geojson_snapshot(
        geometry_bytes,
        source_suffix=geometry_path.suffix,
        geometry_lineage=geometry_lineage,
        probability_crs=decision_receipt.probability_grid["crs"],
        probability_bounds=decision_receipt.probability_grid["bounds"],
    )

    areas = _zonal_statistics(
        probability_values=raster["values"],
        valid_mask=raster["valid_mask"],
        transform=raster["transform_object"],
        features=geometry["features"],
        threshold=threshold,
        pixel_area=raster["pixel_area"],
    )
    geometry_public = {
        key: deepcopy(geometry_lineage[key])
        for key in (
            "dataset_id",
            "study_area",
            "data_version",
            "source_name",
            "source_timestamp",
            "crs",
            "area_id_field",
            "area_name_field",
            "feature_count",
            "authority_status",
            "processing_allowed",
        )
    }
    geometry_public["bounds_in_probability_crs"] = geometry["bounds"]

    payload: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_type": RECEIPT_TYPE,
        "key_id": signing_key_id,
        "generated_at": generated_at_text,
        "source_timestamp": metadata.source_timestamp,
        "dataset_mode": metadata.dataset_mode,
        "operational_status": metadata.operational_status,
        "confidence_class": metadata.confidence_class,
        "official_warning": bool(source_metadata["official_warning"]),
        "processing_allowed": metadata.processing_allowed,
        "can_feed_decision_layer": True,
        "eligible_for_decision_layer": True,
        "eligible_for_fpps": True,
        "run_id": decision_receipt.run_id,
        "git_commit": decision_receipt.git_commit,
        "model_id": decision_receipt.model_id,
        "model_revision": decision_receipt.model_revision,
        "geoai_version": decision_receipt.geoai_version,
        "geoai_commit": decision_receipt.geoai_commit,
        "model_run_manifest_sha256": decision_receipt.model_run_manifest_sha256,
        "probability_raster_receipt_sha256": _canonical_sha256(
            probability_raster_receipt, "probability_raster_receipt"
        ),
        "probability_raster_sha256": raster_sha,
        "authoritative_geometry_receipt_sha256": _canonical_sha256(
            authoritative_geometry_receipt, "authoritative_geometry_receipt"
        ),
        "authoritative_geometry_sha256": geometry_sha,
        "probability_grid": deepcopy(decision_receipt.probability_grid),
        "authoritative_geometry": geometry_public,
        "probability_threshold": threshold,
        "aggregation_method": {
            "name": "pixel_center_mask",
            "all_touched": False,
            "quantile_method": "linear",
            "statistics_version": "1.0",
            "pixel_area_square_map_units": round(raster["pixel_area"], 9),
        },
        "areas": areas,
    }
    payload["signature"] = {
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": signing_key_id,
        "value": "",
    }
    payload["signature"]["value"] = _signature_value(payload, secret)
    # Verify the just-created receipt through the same downstream path.  This
    # catches accidental schema or canonicalization drift at the producer edge.
    verify_signed_zonal_receipt(
        payload,
        signing_key=secret,
        expected_key_id=signing_key_id,
        source_metadata=source_metadata,
        probability_raster_receipt=probability_raster_receipt,
        authoritative_geometry_receipt=authoritative_geometry_receipt,
    )
    return payload


def verify_signed_zonal_receipt(
    receipt: Mapping[str, object],
    *,
    signing_key: bytes,
    expected_key_id: str,
    source_metadata: Mapping[str, object],
    probability_raster_receipt: Mapping[str, object],
    authoritative_geometry_receipt: Mapping[str, object],
) -> list[dict[str, Any]]:
    """Verify a trusted receipt and return decision-eligible area summaries.

    Verification is fail-closed: it checks the canonical HMAC using
    ``hmac.compare_digest``, revalidates the complete model-run/raster lineage,
    binds the authoritative geometry receipt, and validates every signed zonal
    statistic.  The returned list is a deep copy and does not expose the input
    receipt for mutation.
    """

    secret = _signing_key(signing_key)
    key_id = _key_id(expected_key_id)
    signed = _require_exact_fields(receipt, SIGNED_RECEIPT_FIELDS, "zonal receipt")
    signature = _require_exact_fields(
        signed["signature"], SIGNATURE_FIELDS, "zonal receipt.signature"
    )
    if signature["algorithm"] != SIGNATURE_ALGORITHM:
        raise ProbabilityAggregationError(
            f"zonal receipt signature algorithm must be {SIGNATURE_ALGORITHM}."
        )
    actual_key_id = _key_id_value(signature["key_id"], "zonal receipt.signature.key_id")
    signed_key_id = _key_id_value(signed["key_id"], "zonal receipt.key_id")
    if not hmac.compare_digest(actual_key_id, signed_key_id):
        raise ProbabilityAggregationError(
            "Zonal receipt signature key ID does not match its signed key ID."
        )
    if not hmac.compare_digest(signed_key_id, key_id):
        raise ProbabilityAggregationError(
            "Zonal receipt signing key ID is not trusted."
        )
    signature_value = _sha256(signature["value"], "zonal receipt.signature.value")
    expected_signature = _signature_value(signed, secret)
    if not hmac.compare_digest(signature_value, expected_signature):
        raise ProbabilityAggregationError("Zonal receipt signature is invalid.")

    if signed["schema_version"] != RECEIPT_SCHEMA_VERSION:
        raise ProbabilityAggregationError(
            "zonal receipt schema_version must be "
            f"{RECEIPT_SCHEMA_VERSION}; legacy 1.0 receipts are not study-area bound."
        )
    if signed["receipt_type"] != RECEIPT_TYPE:
        raise ProbabilityAggregationError("zonal receipt receipt_type is invalid.")
    generated_time = _parsed_timestamp(
        signed["generated_at"], "zonal receipt.generated_at"
    )
    signed_source_time = _parsed_timestamp(
        signed["source_timestamp"], "zonal receipt.source_timestamp"
    )
    if generated_time < signed_source_time:
        raise ProbabilityAggregationError(
            "zonal receipt generated_at cannot predate source_timestamp."
        )

    metadata = _validate_source_metadata(source_metadata)
    if (
        metadata.dataset_mode != "official_input"
        or not metadata.can_feed_decision_layer
    ):
        raise ProbabilityAggregationError(
            "Trusted zonal receipt verification requires an eligible official_input run."
        )
    model_manifest_time = _parsed_timestamp(
        source_metadata["generated_at"], "source_metadata.generated_at"
    )
    threshold = _finite_number(
        signed["probability_threshold"], "zonal receipt.probability_threshold"
    )
    grid = signed["probability_grid"]
    nodata = _finite_number_from_mapping(
        grid, "nodata", "zonal receipt probability_grid"
    )
    if 0.0 <= nodata <= 1.0:
        raise ProbabilityAggregationError(
            "Zonal receipt probability nodata must be outside [0, 1]."
        )
    decision_receipt = _validate_decision_feed_evidence(
        source_metadata,
        probability_raster_receipt,
        nodata=nodata,
        probability_threshold=threshold,
    )
    geometry_lineage = _validate_authoritative_geometry_receipt(
        authoritative_geometry_receipt
    )
    _require_matching_study_area(source_metadata, geometry_lineage)
    geometry_source_time = _parsed_timestamp(
        geometry_lineage["source_timestamp"],
        "authoritative_geometry_receipt.source_timestamp",
    )
    if generated_time < max(model_manifest_time, geometry_source_time):
        raise ProbabilityAggregationError(
            "zonal receipt generated_at predates trusted lineage."
        )

    _bind_receipt_lineage(
        signed,
        metadata=metadata,
        source_metadata=source_metadata,
        decision_receipt=decision_receipt,
        probability_raster_receipt=probability_raster_receipt,
        geometry_lineage=geometry_lineage,
        authoritative_geometry_receipt=authoritative_geometry_receipt,
    )
    pixel_area = _validate_aggregation_method(signed["aggregation_method"])
    areas = _validate_area_results(
        signed["areas"], threshold=threshold, pixel_area=pixel_area
    )
    return deepcopy(areas)


def _bind_receipt_lineage(
    signed: Mapping[str, object],
    *,
    metadata: Any,
    source_metadata: Mapping[str, object],
    decision_receipt: Any,
    probability_raster_receipt: Mapping[str, object],
    geometry_lineage: Mapping[str, Any],
    authoritative_geometry_receipt: Mapping[str, object],
) -> None:
    expected_scalars = {
        "source_timestamp": metadata.source_timestamp,
        "dataset_mode": metadata.dataset_mode,
        "operational_status": metadata.operational_status,
        "confidence_class": metadata.confidence_class,
        "official_warning": source_metadata["official_warning"],
        "processing_allowed": True,
        "can_feed_decision_layer": True,
        "eligible_for_decision_layer": True,
        "eligible_for_fpps": True,
        "run_id": decision_receipt.run_id,
        "git_commit": decision_receipt.git_commit,
        "model_id": decision_receipt.model_id,
        "model_revision": decision_receipt.model_revision,
        "geoai_version": decision_receipt.geoai_version,
        "geoai_commit": decision_receipt.geoai_commit,
        "model_run_manifest_sha256": decision_receipt.model_run_manifest_sha256,
        "probability_raster_receipt_sha256": _canonical_sha256(
            probability_raster_receipt, "probability_raster_receipt"
        ),
        "probability_raster_sha256": decision_receipt.probability_raster_sha256,
        "authoritative_geometry_receipt_sha256": _canonical_sha256(
            authoritative_geometry_receipt, "authoritative_geometry_receipt"
        ),
        "authoritative_geometry_sha256": geometry_lineage["sha256"],
    }
    for field, expected in expected_scalars.items():
        actual = signed[field]
        if type(expected) in {bool, type(None)}:
            matches = type(actual) is type(expected) and actual == expected
        else:
            matches = actual == expected
        if not matches:
            raise ProbabilityAggregationError(
                f"Zonal receipt {field} does not match trusted lineage."
            )
    if signed["probability_grid"] != decision_receipt.probability_grid:
        raise ProbabilityAggregationError(
            "Zonal receipt probability_grid does not match trusted lineage."
        )

    public_geometry = _require_exact_fields(
        signed["authoritative_geometry"],
        PUBLIC_GEOMETRY_FIELDS,
        "zonal receipt.authoritative_geometry",
    )
    for field in AUTHORITATIVE_GEOMETRY_FIELDS - {"sha256"}:
        if public_geometry[field] != geometry_lineage[field]:
            raise ProbabilityAggregationError(
                f"Zonal receipt authoritative geometry {field} does not match lineage."
            )
    bounds = public_geometry["bounds_in_probability_crs"]
    if (
        isinstance(bounds, (str, bytes))
        or not isinstance(bounds, Sequence)
        or len(bounds) != 4
    ):
        raise ProbabilityAggregationError(
            "zonal receipt authoritative geometry bounds must contain four numbers."
        )
    numeric_bounds = [
        _finite_number(value, f"authoritative geometry bounds[{index}]")
        for index, value in enumerate(bounds)
    ]
    if (
        not numeric_bounds[0] < numeric_bounds[2]
        or not numeric_bounds[1] < numeric_bounds[3]
    ):
        raise ProbabilityAggregationError(
            "zonal receipt authoritative geometry bounds must be ordered."
        )
    raster_bounds = decision_receipt.probability_grid["bounds"]
    if not _bounds_have_area_overlap(numeric_bounds, raster_bounds):
        raise ProbabilityAggregationError(
            "Zonal receipt authoritative geometry does not overlap the probability grid."
        )


def _validate_authoritative_geometry_receipt(
    value: Mapping[str, object],
) -> dict[str, Any]:
    receipt = _require_exact_fields(
        value, AUTHORITATIVE_GEOMETRY_FIELDS, "authoritative_geometry_receipt"
    )
    result: dict[str, Any] = {}
    for field in ("dataset_id", "study_area", "data_version", "source_name"):
        result[field] = _public_text(receipt[field], f"authoritative geometry {field}")
    result["source_timestamp"] = _timestamp_text(
        receipt["source_timestamp"], "authoritative geometry source_timestamp"
    )
    result["sha256"] = _sha256(receipt["sha256"], "authoritative geometry sha256")
    result["crs"] = _epsg_text(receipt["crs"], "authoritative geometry crs")
    result["area_id_field"] = _field_name(
        receipt["area_id_field"], "authoritative geometry area_id_field"
    )
    result["area_name_field"] = _field_name(
        receipt["area_name_field"], "authoritative geometry area_name_field"
    )
    if result["area_id_field"] == result["area_name_field"]:
        raise ProbabilityAggregationError(
            "Authoritative geometry ID and name fields must be distinct."
        )
    feature_count = receipt["feature_count"]
    if type(feature_count) is not int or feature_count <= 0:
        raise ProbabilityAggregationError(
            "authoritative geometry feature_count must be a positive integer."
        )
    result["feature_count"] = feature_count
    if receipt["authority_status"] != "authoritative_for_study_area":
        raise ProbabilityAggregationError(
            "Authoritative geometry authority_status must be "
            "authoritative_for_study_area."
        )
    result["authority_status"] = receipt["authority_status"]
    if (
        type(receipt["processing_allowed"]) is not bool
        or not receipt["processing_allowed"]
    ):
        raise ProbabilityAggregationError(
            "Authoritative geometry requires processing_allowed=true."
        )
    result["processing_allowed"] = True
    return result


def _require_matching_study_area(
    source_metadata: Mapping[str, object],
    geometry_lineage: Mapping[str, Any],
) -> None:
    """Reject authoritative geometry from a different model study area."""

    model_study_area = _public_text(
        source_metadata.get("study_area"),
        "model run study_area",
    )
    if geometry_lineage["study_area"] != model_study_area:
        raise ProbabilityAggregationError(
            "Authoritative geometry study_area does not match the model run."
        )


def _read_probability_raster(
    source: Any,
    *,
    expected_grid: Mapping[str, object],
) -> dict[str, Any]:
    try:
        import numpy as np
        import rasterio
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise ProbabilityAggregationError(
            "Trusted zonal aggregation requires NumPy and rasterio."
        ) from exc

    try:
        with rasterio.open(source) as dataset:
            if dataset.crs is None or not dataset.crs.is_projected:
                raise ProbabilityAggregationError(
                    "Probability raster must use an explicit projected CRS for "
                    "auditable pixel-area statistics."
                )
            actual_grid = {
                "crs": dataset.crs.to_string() if dataset.crs else None,
                "transform": [float(value) for value in dataset.transform],
                "width": dataset.width,
                "height": dataset.height,
                "bounds": [float(value) for value in dataset.bounds],
                "count": dataset.count,
                "dtypes": list(dataset.dtypes),
                "descriptions": list(dataset.descriptions),
                "nodata": dataset.nodata,
            }
            _compare_actual_grid(actual_grid, expected_grid)
            values = dataset.read(1)
            band_mask = dataset.read_masks(1)
            transform = dataset.transform
    except ProbabilityAggregationError:
        raise
    except Exception as exc:
        raise ProbabilityAggregationError(
            "Probability raster could not be read as a GeoTIFF."
        ) from exc

    nodata = float(expected_grid["nodata"])
    value_valid = values != nodata
    mask_valid = band_mask > 0
    if not np.array_equal(value_valid, mask_valid):
        raise ProbabilityAggregationError(
            "Probability raster internal mask must match its declared nodata cells."
        )
    if not bool(value_valid.any()):
        raise ProbabilityAggregationError(
            "Probability raster must contain at least one valid cell."
        )
    valid_values = values[value_valid]
    if not bool(np.isfinite(valid_values).all()):
        raise ProbabilityAggregationError(
            "Probability raster contains non-finite valid values."
        )
    if bool(((valid_values < 0.0) | (valid_values > 1.0)).any()):
        raise ProbabilityAggregationError(
            "Probability raster valid values must be within [0, 1]."
        )
    pixel_area = abs(transform.a * transform.e - transform.b * transform.d)
    if not math.isfinite(pixel_area) or pixel_area <= 0:
        raise ProbabilityAggregationError(
            "Probability raster transform must define a positive pixel area."
        )
    return {
        "values": values,
        "valid_mask": value_valid,
        "transform_object": transform,
        "pixel_area": float(pixel_area),
    }


def _compare_actual_grid(
    actual: Mapping[str, object], expected: Mapping[str, object]
) -> None:
    if (
        not isinstance(actual["crs"], str)
        or actual["crs"].casefold() != str(expected["crs"]).casefold()
    ):
        raise ProbabilityAggregationError(
            "Probability raster file CRS does not match its lineage receipt."
        )
    for field in ("width", "height", "count", "dtypes", "descriptions"):
        if actual[field] != expected[field]:
            raise ProbabilityAggregationError(
                f"Probability raster file {field} does not match its lineage receipt."
            )
    if not _same_numbers(actual["transform"], expected["transform"]):
        raise ProbabilityAggregationError(
            "Probability raster file transform does not match its lineage receipt."
        )
    if not _same_numbers(actual["bounds"], expected["bounds"]):
        raise ProbabilityAggregationError(
            "Probability raster file bounds do not match its lineage receipt."
        )
    actual_nodata = actual["nodata"]
    if not isinstance(actual_nodata, (int, float)) or isinstance(actual_nodata, bool):
        raise ProbabilityAggregationError(
            "Probability raster file must declare finite nodata."
        )
    if not math.isfinite(float(actual_nodata)) or not _same_number(
        float(actual_nodata), float(expected["nodata"])
    ):
        raise ProbabilityAggregationError(
            "Probability raster file nodata does not match its lineage receipt."
        )


def _read_authoritative_geojson_snapshot(
    document_bytes: bytes,
    *,
    source_suffix: str,
    geometry_lineage: Mapping[str, Any],
    probability_crs: str,
    probability_bounds: Sequence[float],
) -> dict[str, Any]:
    if source_suffix.casefold() not in {".geojson", ".json"}:
        raise ProbabilityAggregationError(
            "Authoritative geometry must be GeoJSON in this dependency profile."
        )
    try:
        document = json.loads(document_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProbabilityAggregationError(
            "Authoritative geometry could not be read as UTF-8 GeoJSON."
        ) from exc
    if not isinstance(document, Mapping) or document.get("type") != "FeatureCollection":
        raise ProbabilityAggregationError(
            "Authoritative geometry must be a GeoJSON FeatureCollection."
        )
    document_crs = _geojson_crs(document.get("crs"))
    if document_crs.casefold() != geometry_lineage["crs"].casefold():
        raise ProbabilityAggregationError(
            "GeoJSON CRS does not match the authoritative geometry receipt."
        )
    raw_features = document.get("features")
    if isinstance(raw_features, (str, bytes)) or not isinstance(raw_features, Sequence):
        raise ProbabilityAggregationError(
            "Authoritative GeoJSON features must be an array."
        )
    if len(raw_features) != geometry_lineage["feature_count"]:
        raise ProbabilityAggregationError(
            "GeoJSON feature count does not match the authoritative geometry receipt."
        )

    try:
        from rasterio.crs import CRS
        from rasterio.warp import transform_geom
        from shapely.geometry import box, mapping, shape
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise ProbabilityAggregationError(
            "Trusted zonal aggregation requires rasterio and Shapely."
        ) from exc

    try:
        source_crs = CRS.from_user_input(document_crs)
        target_crs = CRS.from_user_input(probability_crs)
    except Exception as exc:
        raise ProbabilityAggregationError(
            "Authoritative or probability CRS is not a valid EPSG definition."
        ) from exc

    probability_box = box(*probability_bounds)
    features: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    geometries: list[Any] = []
    for index, raw_feature in enumerate(raw_features):
        if not isinstance(raw_feature, Mapping) or raw_feature.get("type") != "Feature":
            raise ProbabilityAggregationError(f"GeoJSON feature {index} is invalid.")
        properties = raw_feature.get("properties")
        if not isinstance(properties, Mapping):
            raise ProbabilityAggregationError(
                f"GeoJSON feature {index} properties must be an object."
            )
        area_id = _area_id(
            properties.get(geometry_lineage["area_id_field"]),
            f"GeoJSON feature {index} area ID",
        )
        area_name = _public_text(
            properties.get(geometry_lineage["area_name_field"]),
            f"GeoJSON feature {index} area name",
        )
        if area_id in seen_ids:
            raise ProbabilityAggregationError(
                "Authoritative geometry area IDs must be unique."
            )
        seen_ids.add(area_id)
        raw_geometry = raw_feature.get("geometry")
        if not isinstance(raw_geometry, Mapping):
            raise ProbabilityAggregationError(
                f"GeoJSON feature {index} geometry must be an object."
            )
        try:
            source_shape = shape(raw_geometry)
        except Exception as exc:
            raise ProbabilityAggregationError(
                f"GeoJSON feature {index} geometry cannot be parsed."
            ) from exc
        if (
            source_shape.geom_type not in {"Polygon", "MultiPolygon"}
            or source_shape.is_empty
            or not source_shape.is_valid
            or source_shape.area <= 0
        ):
            raise ProbabilityAggregationError(
                f"GeoJSON feature {index} must be a valid non-empty polygon."
            )
        try:
            transformed_mapping = (
                raw_geometry
                if source_crs == target_crs
                else transform_geom(source_crs, target_crs, raw_geometry, precision=12)
            )
            transformed_shape = shape(transformed_mapping)
        except Exception as exc:
            raise ProbabilityAggregationError(
                f"GeoJSON feature {index} could not be transformed to the probability CRS."
            ) from exc
        if transformed_shape.is_empty or not transformed_shape.is_valid:
            raise ProbabilityAggregationError(
                f"GeoJSON feature {index} is invalid after CRS transformation."
            )
        if transformed_shape.intersection(probability_box).area <= 0:
            raise ProbabilityAggregationError(
                f"GeoJSON feature {index} has no areal overlap with the probability raster."
            )
        geometries.append(transformed_shape)
        features.append(
            {
                "area_id": area_id,
                "area_name": area_name,
                "geometry": mapping(transformed_shape),
            }
        )

    _reject_overlapping_areas(geometries)
    features.sort(key=lambda feature: feature["area_id"])
    union_bounds = [
        min(geometry.bounds[0] for geometry in geometries),
        min(geometry.bounds[1] for geometry in geometries),
        max(geometry.bounds[2] for geometry in geometries),
        max(geometry.bounds[3] for geometry in geometries),
    ]
    return {"features": features, "bounds": [round(value, 9) for value in union_bounds]}


def _reject_overlapping_areas(geometries: Sequence[Any]) -> None:
    from shapely.strtree import STRtree

    tree = STRtree(geometries)
    for first_index, first in enumerate(geometries):
        for raw_second_index in tree.query(first, predicate="intersects"):
            second_index = int(raw_second_index)
            if second_index <= first_index:
                continue
            if first.intersection(geometries[second_index]).area > 1e-9:
                raise ProbabilityAggregationError(
                    "Authoritative geometry polygons must not overlap in area."
                )


def _zonal_statistics(
    *,
    probability_values: Any,
    valid_mask: Any,
    transform: Any,
    features: Sequence[Mapping[str, Any]],
    threshold: float,
    pixel_area: float,
) -> list[dict[str, Any]]:
    try:
        from rasterio.features import geometry_mask
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise ProbabilityAggregationError(
            "Trusted zonal aggregation requires rasterio."
        ) from exc

    results: list[dict[str, Any]] = []
    for feature in features:
        inside = geometry_mask(
            [feature["geometry"]],
            out_shape=probability_values.shape,
            transform=transform,
            invert=True,
            all_touched=False,
        )
        selected = inside & valid_mask
        values = sorted(float(value) for value in probability_values[selected].tolist())
        if not values:
            raise ProbabilityAggregationError(
                f"Area {feature['area_id']!r} contains no valid probability pixel centers."
            )
        sample_count = len(values)
        flood_count = sum(value >= threshold for value in values)
        mean_probability = math.fsum(values) / sample_count
        sampled_area = sample_count * pixel_area
        flood_area = flood_count * pixel_area
        results.append(
            {
                "subdistrict_id": feature["area_id"],
                "subdistrict_name": feature["area_name"],
                "mean_flood_probability_0_1": round(mean_probability, 6),
                "p90_flood_probability_0_1": round(_linear_quantile(values, 0.90), 6),
                "binary_flood_share_0_1": round(flood_count / sample_count, 6),
                "sample_pixel_count": sample_count,
                "flood_pixel_count": flood_count,
                "sampled_area_square_map_units": round(sampled_area, 6),
                "estimated_flood_area_square_map_units": round(flood_area, 6),
                "probability_threshold": threshold,
                "aggregation_status": "decision_eligible",
                "eligible_for_decision_layer": True,
                "eligible_for_fpps": True,
            }
        )
    return results


def _validate_aggregation_method(value: object) -> float:
    method = _require_exact_fields(
        value, AGGREGATION_METHOD_FIELDS, "zonal receipt.aggregation_method"
    )
    if (
        method["name"] != "pixel_center_mask"
        or type(method["all_touched"]) is not bool
        or method["all_touched"] is not False
        or method["quantile_method"] != "linear"
        or method["statistics_version"] != "1.0"
    ):
        raise ProbabilityAggregationError(
            "Zonal receipt aggregation method is unsupported."
        )
    pixel_area = _finite_number(
        method["pixel_area_square_map_units"],
        "zonal receipt pixel_area_square_map_units",
    )
    if pixel_area <= 0:
        raise ProbabilityAggregationError("Zonal receipt pixel area must be positive.")
    return pixel_area


def _validate_area_results(
    value: object, *, threshold: float, pixel_area: float
) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ProbabilityAggregationError(
            "zonal receipt areas must be a non-empty array."
        )
    areas: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_id: str | None = None
    for index, raw_area in enumerate(value):
        area = _require_exact_fields(
            raw_area, AREA_RESULT_FIELDS, f"zonal receipt.areas[{index}]"
        )
        area_id = _area_id(area["subdistrict_id"], f"areas[{index}].subdistrict_id")
        area_name = _public_text(
            area["subdistrict_name"], f"areas[{index}].subdistrict_name"
        )
        if area_id in seen or (previous_id is not None and area_id <= previous_id):
            raise ProbabilityAggregationError(
                "Zonal receipt areas must have unique IDs in ascending order."
            )
        seen.add(area_id)
        previous_id = area_id
        mean = _unit_interval(
            area["mean_flood_probability_0_1"], f"areas[{index}].mean"
        )
        p90 = _unit_interval(area["p90_flood_probability_0_1"], f"areas[{index}].p90")
        binary_share = _unit_interval(
            area["binary_flood_share_0_1"], f"areas[{index}].binary_share"
        )
        sample_count = _positive_integer(
            area["sample_pixel_count"], f"areas[{index}].sample_pixel_count"
        )
        flood_count = _nonnegative_integer(
            area["flood_pixel_count"], f"areas[{index}].flood_pixel_count"
        )
        if flood_count > sample_count:
            raise ProbabilityAggregationError(
                f"areas[{index}] flood_pixel_count cannot exceed sample_pixel_count."
            )
        if not _same_number(binary_share, round(flood_count / sample_count, 6)):
            raise ProbabilityAggregationError(
                f"areas[{index}] binary share is inconsistent with its pixel counts."
            )
        sampled_area = _finite_number(
            area["sampled_area_square_map_units"], f"areas[{index}].sampled_area"
        )
        flood_area = _finite_number(
            area["estimated_flood_area_square_map_units"],
            f"areas[{index}].estimated_flood_area",
        )
        if not _same_number(sampled_area, round(sample_count * pixel_area, 6)):
            raise ProbabilityAggregationError(
                f"areas[{index}] sampled area is inconsistent with its pixel count."
            )
        if not _same_number(flood_area, round(flood_count * pixel_area, 6)):
            raise ProbabilityAggregationError(
                f"areas[{index}] estimated flood area is inconsistent with its pixel count."
            )
        if not _same_number(
            _finite_number(
                area["probability_threshold"], f"areas[{index}].probability_threshold"
            ),
            threshold,
        ):
            raise ProbabilityAggregationError(
                f"areas[{index}] probability threshold does not match the receipt."
            )
        if (
            area["aggregation_status"] != "decision_eligible"
            or type(area["eligible_for_decision_layer"]) is not bool
            or area["eligible_for_decision_layer"] is not True
            or type(area["eligible_for_fpps"]) is not bool
            or area["eligible_for_fpps"] is not True
        ):
            raise ProbabilityAggregationError(
                f"areas[{index}] is not marked as a trusted decision-eligible aggregate."
            )
        areas.append(
            {
                **dict(area),
                "subdistrict_id": area_id,
                "subdistrict_name": area_name,
                "mean_flood_probability_0_1": mean,
                "p90_flood_probability_0_1": p90,
            }
        )
    return areas


def _signature_value(payload: Mapping[str, object], signing_key: bytes) -> str:
    unsigned = deepcopy(dict(payload))
    signature = unsigned.get("signature")
    if signature is not None:
        if not isinstance(signature, Mapping):
            raise ProbabilityAggregationError(
                "zonal receipt signature must be a mapping."
            )
        unsigned["signature"] = {
            key: value for key, value in signature.items() if key != "value"
        }
    encoded = _canonical_json_bytes(unsigned, "zonal receipt")
    return hmac.new(signing_key, encoded, hashlib.sha256).hexdigest()


def _canonical_json_bytes(value: object, field: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProbabilityAggregationError(
            f"{field} must contain only canonical JSON values."
        ) from exc


def _read_bound_bytes(path: Path, label: str) -> tuple[bytes, str]:
    with _open_stable_binary(path, label) as stream:
        state_before = _descriptor_state(stream)
        try:
            content = stream.read()
        except OSError as exc:
            raise ProbabilityAggregationError(
                f"{label.capitalize()} cannot be read."
            ) from exc
        if state_before != _descriptor_state(stream):
            raise ProbabilityAggregationError(
                f"{label.capitalize()} changed while its byte snapshot was read."
            )
    return content, hashlib.sha256(content).hexdigest()


@contextmanager
def _probability_raster_snapshot(path: Path) -> Iterator[tuple[Any, str]]:
    """Copy and hash one open source descriptor, then yield its private snapshot."""

    digest = hashlib.sha256()
    with tempfile.TemporaryFile(mode="w+b", suffix=".tif") as snapshot:
        with _open_stable_binary(path, "probability raster") as source:
            state_before = _descriptor_state(source)
            try:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    snapshot.write(chunk)
                snapshot.flush()
                os.fsync(snapshot.fileno())
            except OSError as exc:
                raise ProbabilityAggregationError(
                    "Probability raster could not be copied into a private snapshot."
                ) from exc
            if state_before != _descriptor_state(source):
                raise ProbabilityAggregationError(
                    "Probability raster changed while its private snapshot was copied."
                )
        source_sha = digest.hexdigest()
        snapshot_sha = _stream_sha256(snapshot)
        if not hmac.compare_digest(source_sha, snapshot_sha):
            raise ProbabilityAggregationError(
                "Probability raster private snapshot checksum is inconsistent."
            )
        snapshot.seek(0)
        yield snapshot, source_sha
        if snapshot.closed:
            raise ProbabilityAggregationError(
                "Probability raster private snapshot was closed unexpectedly."
            )
        after_parse_sha = _stream_sha256(snapshot)
        if not hmac.compare_digest(source_sha, after_parse_sha):
            raise ProbabilityAggregationError(
                "Probability raster private snapshot changed during parsing."
            )


def _stream_sha256(stream: Any) -> str:
    digest = hashlib.sha256()
    try:
        stream.seek(0)
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    except OSError as exc:
        raise ProbabilityAggregationError(
            "Private artifact snapshot cannot be verified."
        ) from exc
    return digest.hexdigest()


def _descriptor_state(stream: Any) -> tuple[int, int, int, int, int]:
    """Return mutation-sensitive descriptor metadata, excluding access time."""

    try:
        value = os.fstat(stream.fileno())
    except (OSError, ValueError) as exc:
        raise ProbabilityAggregationError(
            "Artifact descriptor state cannot be verified."
        ) from exc
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_size),
        int(value.st_mtime_ns),
        int(value.st_ctime_ns),
    )


@contextmanager
def _open_stable_binary(path: Path, label: str) -> Iterator[Any]:
    """Open a regular non-symlink file and bind the descriptor to its lstat."""

    try:
        path_stat = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ProbabilityAggregationError(
            f"{label.capitalize()} path cannot be inspected."
        ) from exc
    if not stat.S_ISREG(path_stat.st_mode):
        raise ProbabilityAggregationError(
            f"{label.capitalize()} must be a regular, non-symlink file."
        )

    flags = os.O_RDONLY
    for flag_name in ("O_BINARY", "O_NOINHERIT", "O_NOFOLLOW"):
        flags |= int(getattr(os, flag_name, 0))
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ProbabilityAggregationError(
            f"{label.capitalize()} cannot be opened safely."
        ) from exc
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
            raise ProbabilityAggregationError(
                f"{label.capitalize()} changed before its immutable snapshot was opened."
            )
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            yield stream
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _regular_local_file(value: str | Path, label: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ProbabilityAggregationError(f"{label.capitalize()} path is required.")
    path = Path(value)
    try:
        if path.is_symlink() or not path.is_file():
            raise ProbabilityAggregationError(
                f"{label.capitalize()} must be a regular, non-symlink file."
            )
    except OSError as exc:
        raise ProbabilityAggregationError(
            f"{label.capitalize()} path cannot be inspected."
        ) from exc
    return path


def _geojson_crs(value: object) -> str:
    if not isinstance(value, Mapping) or value.get("type") != "name":
        raise ProbabilityAggregationError(
            "Authoritative GeoJSON must declare an explicit named CRS."
        )
    properties = value.get("properties")
    if not isinstance(properties, Mapping):
        raise ProbabilityAggregationError(
            "Authoritative GeoJSON named CRS properties are invalid."
        )
    return _epsg_text(properties.get("name"), "authoritative GeoJSON CRS")


def _epsg_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ProbabilityAggregationError(f"{field} must be an EPSG identifier.")
    text = value.strip().upper()
    if not re.fullmatch(r"EPSG:[1-9][0-9]*", text):
        raise ProbabilityAggregationError(f"{field} must be an EPSG identifier.")
    return text


def _field_name(value: object, field: str) -> str:
    text = _public_text(value, field)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", text):
        raise ProbabilityAggregationError(
            f"{field} must be a simple property field name."
        )
    return text


def _area_id(value: object, field: str) -> str:
    text = _public_text(value, field)
    if not AREA_ID_RE.fullmatch(text):
        raise ProbabilityAggregationError(
            f"{field} must be a stable identifier without whitespace."
        )
    return text


def _public_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProbabilityAggregationError(f"{field} must be a non-empty string.")
    text = value.strip()
    if text.startswith(("/", "\\")) or PRIVATE_PATH_RE.search(text):
        raise ProbabilityAggregationError(f"{field} must not expose a private path.")
    return text


def _key_id(value: object) -> str:
    return _key_id_value(value, "key_id")


def _key_id_value(value: object, field: str) -> str:
    text = _public_text(value, field)
    if not KEY_ID_RE.fullmatch(text):
        raise ProbabilityAggregationError(
            f"{field} must be a stable public key identifier."
        )
    return text


def _signing_key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ProbabilityAggregationError(
            "signing_key must be external bytes containing at least 32 bytes."
        )
    return value


def _timestamp_text(value: object, field: str) -> str:
    _parsed_timestamp(value, field)
    return str(value).strip()


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProbabilityAggregationError(f"{field} must be numeric.")
    number = float(value)
    if not math.isfinite(number):
        raise ProbabilityAggregationError(f"{field} must be finite.")
    return number


def _finite_number_from_mapping(value: object, key: str, field: str) -> float:
    if not isinstance(value, Mapping):
        raise ProbabilityAggregationError(f"{field} must be a mapping.")
    return _finite_number(value.get(key), f"{field}.{key}")


def _unit_interval(value: object, field: str) -> float:
    number = _finite_number(value, field)
    if not 0.0 <= number <= 1.0:
        raise ProbabilityAggregationError(f"{field} must be within [0, 1].")
    return number


def _positive_integer(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise ProbabilityAggregationError(f"{field} must be a positive integer.")
    return value


def _nonnegative_integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ProbabilityAggregationError(f"{field} must be a non-negative integer.")
    return value


def _bounds_have_area_overlap(first: Sequence[float], second: Sequence[float]) -> bool:
    return min(first[2], second[2]) > max(first[0], second[0]) and min(
        first[3], second[3]
    ) > max(first[1], second[1])
