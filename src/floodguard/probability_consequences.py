"""Trusted probability-raster consequences for roads and facilities.

The existing trusted zonal adapter binds probability pixels to authoritative
reporting polygons.  This module provides the deliberately separate
pixel-to-feature bridge needed for road corridors and facility locations.  It
hashes immutable raster and GeoJSON bytes, validates their CRS/grid/lineage,
derives modeled probability evidence, and signs a canonical receipt.

The output never claims an observed road closure, a safe route, or a verified
shelter.  Provenance-tracked candidate geometry may be processed only with
``allow_report_only=True`` and always produces ``can_feed_decision_layer=false``.
Decision eligibility requires an already eligible ``official_input`` model run
and authoritative road and facility geometry receipts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import hmac
import json
import math
from pathlib import Path
from typing import Any

from floodguard.probability_aggregation import (
    MODEL_RUN_FIELDS,
    PRIVATE_PATH_RE,
    PROBABILITY_RECEIPT_FIELDS,
    ProbabilityAggregationError,
    _canonical_sha256,
    _linear_quantile,
    _parsed_timestamp,
    _require_exact_fields,
    _same_number,
    _sha256,
    _validate_decision_feed_evidence,
    _validate_probability_grid,
    _validate_source_metadata,
)
from floodguard.trusted_zonal_adapter import (
    _key_id,
    _probability_raster_snapshot,
    _read_bound_bytes,
    _read_probability_raster,
    _regular_local_file,
    _signing_key,
)


RECEIPT_TYPE = "floodguard.trusted_probability_consequences"
SCHEMA_VERSION = "1.0"
SIGNATURE_ALGORITHM = "HMAC-SHA256"

GEOMETRY_RECEIPT_FIELDS = frozenset(
    {
        "dataset_id",
        "study_area",
        "data_version",
        "sha256",
        "source_name",
        "source_timestamp",
        "crs",
        "feature_kind",
        "feature_id_field",
        "area_id_field",
        "feature_count",
        "authority_status",
        "processing_allowed",
        "assumptions",
    }
)
RECEIPT_FIELDS = frozenset(
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
        "aggregation_status",
        "reason_blocked",
        "study_area",
        "run_id",
        "model_id",
        "model_revision",
        "git_commit",
        "model_run_manifest_sha256",
        "probability_raster_receipt_sha256",
        "probability_raster_sha256",
        "probability_grid",
        "probability_threshold",
        "road_geometry_receipt_sha256",
        "road_geometry_sha256",
        "facility_geometry_receipt_sha256",
        "facility_geometry_sha256",
        "method",
        "roads",
        "facilities",
        "signature",
    }
)
METHOD_FIELDS = frozenset(
    {
        "statistics_version",
        "sampling_rule",
        "all_touched",
        "quantile_method",
        "road_buffer_distance_m",
        "facility_buffer_distance_m",
        "pixel_area_m2",
        "road_semantics",
        "facility_semantics",
    }
)
SIGNATURE_FIELDS = frozenset({"algorithm", "key_id", "value"})
ROAD_RESULT_FIELDS = frozenset(
    {
        "road_id",
        "subdistrict_id",
        "road_class",
        "bridge_flag",
        "mean_flood_probability_0_1",
        "p90_flood_probability_0_1",
        "max_flood_probability_0_1",
        "binary_flood_share_0_1",
        "sample_pixel_count",
        "flood_pixel_count",
        "sampled_corridor_area_m2",
        "modeled_exposure_status",
        "bridge_probability_evidence_status",
        "observed_closure_status",
        "eligible_for_decision_layer",
    }
)
FACILITY_RESULT_FIELDS = frozenset(
    {
        "facility_id",
        "subdistrict_id",
        "facility_type",
        "verification_status",
        "emergency_role",
        "point_flood_probability_0_1",
        "mean_flood_probability_0_1",
        "p90_flood_probability_0_1",
        "max_flood_probability_0_1",
        "binary_flood_share_0_1",
        "sample_pixel_count",
        "flood_pixel_count",
        "sampled_buffer_area_m2",
        "modeled_exposure_status",
        "safe_destination_status",
        "eligible_for_decision_layer",
        "agency_verified_designated_role",
    }
)

AUTHORITY_STATUSES = frozenset(
    {"authoritative_for_study_area", "provenance_tracked_candidate"}
)
FACILITY_VERIFICATION_STATUSES = frozenset(
    {
        "agency_verified",
        "official_registry_unverified",
        "open_context_candidate",
        "community_report_pending",
        "rejected",
    }
)
EMERGENCY_ROLES = frozenset(
    {
        "designated_evacuation",
        "healthcare",
        "temporary_shelter_candidate",
        "logistics",
        "community_support",
        "no_confirmed_emergency_role",
    }
)


class ProbabilityConsequenceError(ProbabilityAggregationError):
    """Raised when probability-consequence evidence is unsafe or malformed."""


def create_signed_consequence_receipt(
    *,
    probability_raster_path: str | Path,
    road_geometry_path: str | Path,
    facility_geometry_path: str | Path,
    source_metadata: Mapping[str, object],
    probability_raster_receipt: Mapping[str, object],
    road_geometry_receipt: Mapping[str, object],
    facility_geometry_receipt: Mapping[str, object],
    road_buffer_distance_m: float,
    facility_buffer_distance_m: float,
    signing_key: bytes,
    key_id: str,
    generated_at: str,
    allow_report_only: bool = False,
) -> dict[str, Any]:
    """Create a signed, checksum-bound road/facility consequence receipt.

    Pixel inclusion uses the center rule against explicit road/facility buffers.
    The probability at a facility's exact point is reported separately.  The
    adapter does not alter FloodGuard road-risk, access, equity, or FPPS rules.
    """

    if type(allow_report_only) is not bool:
        raise ProbabilityConsequenceError("allow_report_only must be a boolean.")
    road_buffer = _positive_distance(road_buffer_distance_m, "road buffer")
    facility_buffer = _positive_distance(
        facility_buffer_distance_m, "facility buffer"
    )
    secret = _signing_key(signing_key)
    signing_key_id = _key_id(key_id)
    generated_time = _parsed_timestamp(generated_at, "generated_at")

    raster_path = _regular_local_file(probability_raster_path, "probability raster")
    road_path = _regular_local_file(road_geometry_path, "road geometry")
    facility_path = _regular_local_file(facility_geometry_path, "facility geometry")
    _reject_private_paths(source_metadata)
    _reject_private_paths(probability_raster_receipt)
    _reject_private_paths(road_geometry_receipt)
    _reject_private_paths(facility_geometry_receipt)

    source = _validate_probability_lineage(
        source_metadata, probability_raster_receipt
    )
    road_lineage = _validate_geometry_receipt(
        road_geometry_receipt, expected_kind="road_segments"
    )
    facility_lineage = _validate_geometry_receipt(
        facility_geometry_receipt, expected_kind="facilities"
    )
    _require_study_area_binding(source, road_lineage, "road geometry")
    _require_study_area_binding(source, facility_lineage, "facility geometry")
    latest_source_time = max(
        _parsed_timestamp(source_metadata["generated_at"], "source generated_at"),
        _parsed_timestamp(road_lineage["source_timestamp"], "road source timestamp"),
        _parsed_timestamp(
            facility_lineage["source_timestamp"], "facility source timestamp"
        ),
    )
    if generated_time < latest_source_time:
        raise ProbabilityConsequenceError(
            "generated_at cannot predate the model, road, or facility evidence."
        )

    road_bytes, road_sha = _read_bound_bytes(road_path, "road geometry")
    facility_bytes, facility_sha = _read_bound_bytes(
        facility_path, "facility geometry"
    )
    if not hmac.compare_digest(road_sha, road_lineage["sha256"]):
        raise ProbabilityConsequenceError(
            "Road geometry checksum does not match its lineage receipt."
        )
    if not hmac.compare_digest(facility_sha, facility_lineage["sha256"]):
        raise ProbabilityConsequenceError(
            "Facility geometry checksum does not match its lineage receipt."
        )

    with _probability_raster_snapshot(raster_path) as (snapshot, raster_sha):
        if not hmac.compare_digest(raster_sha, source["probability_raster_sha256"]):
            raise ProbabilityConsequenceError(
                "Probability raster checksum does not match its lineage receipt."
            )
        raster = _read_probability_raster(
            snapshot, expected_grid=source["probability_grid"]
        )
    _require_metre_projected_crs(source["probability_grid"]["crs"])

    roads = _read_feature_geometry(
        road_bytes,
        lineage=road_lineage,
        probability_crs=source["probability_grid"]["crs"],
        probability_bounds=source["probability_grid"]["bounds"],
    )
    facilities = _read_feature_geometry(
        facility_bytes,
        lineage=facility_lineage,
        probability_crs=source["probability_grid"]["crs"],
        probability_bounds=source["probability_grid"]["bounds"],
    )

    blockers: list[str] = []
    if not source["decision_eligible"]:
        blockers.append(str(source_metadata["reason_blocked"]))
    for label, lineage in (
        ("road_geometry", road_lineage),
        ("facility_geometry", facility_lineage),
    ):
        if lineage["authority_status"] != "authoritative_for_study_area":
            blockers.append(
                f"{label}: authority_status is provenance_tracked_candidate"
            )
    blockers = sorted({item.strip() for item in blockers if item.strip()})
    decision_eligible = source["decision_eligible"] and not blockers
    if not decision_eligible and not allow_report_only:
        raise ProbabilityConsequenceError(
            "Probability consequences are not decision-eligible: "
            + "; ".join(blockers)
            + ". Pass allow_report_only=True only for explicitly labelled candidate output."
        )

    threshold = source["probability_threshold"]
    road_results = _road_consequences(
        roads,
        raster=raster,
        threshold=threshold,
        buffer_distance=road_buffer,
        decision_eligible=decision_eligible,
    )
    facility_results = _facility_consequences(
        facilities,
        raster=raster,
        threshold=threshold,
        buffer_distance=facility_buffer,
        decision_eligible=decision_eligible,
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": RECEIPT_TYPE,
        "key_id": signing_key_id,
        "generated_at": generated_at.strip(),
        "source_timestamp": source_metadata["source_timestamp"],
        "dataset_mode": source_metadata["dataset_mode"],
        "operational_status": source_metadata["operational_status"],
        "confidence_class": source_metadata["confidence_class"],
        "official_warning": source_metadata["official_warning"],
        "processing_allowed": True,
        "can_feed_decision_layer": decision_eligible,
        "eligible_for_decision_layer": decision_eligible,
        "aggregation_status": (
            "decision_eligible" if decision_eligible else "report_only"
        ),
        "reason_blocked": "" if decision_eligible else "; ".join(blockers),
        "study_area": source["study_area"],
        "run_id": source_metadata["run_id"],
        "model_id": source_metadata["model_id"],
        "model_revision": source_metadata["model_revision"],
        "git_commit": source_metadata["git_commit"],
        "model_run_manifest_sha256": source["model_run_manifest_sha256"],
        "probability_raster_receipt_sha256": _canonical_sha256(
            probability_raster_receipt, "probability raster receipt"
        ),
        "probability_raster_sha256": raster_sha,
        "probability_grid": deepcopy(source["probability_grid"]),
        "probability_threshold": threshold,
        "road_geometry_receipt_sha256": _canonical_sha256(
            road_geometry_receipt, "road geometry receipt"
        ),
        "road_geometry_sha256": road_sha,
        "facility_geometry_receipt_sha256": _canonical_sha256(
            facility_geometry_receipt, "facility geometry receipt"
        ),
        "facility_geometry_sha256": facility_sha,
        "method": {
            "statistics_version": "1.0",
            "sampling_rule": "pixel_center_with_explicit_metric_buffer",
            "all_touched": False,
            "quantile_method": "linear",
            "road_buffer_distance_m": road_buffer,
            "facility_buffer_distance_m": facility_buffer,
            "pixel_area_m2": round(float(raster["pixel_area"]), 9),
            "road_semantics": "modeled probability evidence; not an observed closure",
            "facility_semantics": (
                "modeled exposure evidence; not facility suitability or safe-route proof"
            ),
        },
        "roads": road_results,
        "facilities": facility_results,
        "signature": {
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": signing_key_id,
            "value": "",
        },
    }
    payload["signature"]["value"] = _signature_value(payload, secret)
    verify_signed_consequence_receipt(
        payload,
        probability_raster_path=raster_path,
        road_geometry_path=road_path,
        facility_geometry_path=facility_path,
        source_metadata=source_metadata,
        probability_raster_receipt=probability_raster_receipt,
        road_geometry_receipt=road_geometry_receipt,
        facility_geometry_receipt=facility_geometry_receipt,
        signing_key=secret,
        expected_key_id=signing_key_id,
    )
    return payload


def verify_signed_consequence_receipt(
    receipt: Mapping[str, object],
    *,
    probability_raster_path: str | Path,
    road_geometry_path: str | Path,
    facility_geometry_path: str | Path,
    source_metadata: Mapping[str, object],
    probability_raster_receipt: Mapping[str, object],
    road_geometry_receipt: Mapping[str, object],
    facility_geometry_receipt: Mapping[str, object],
    signing_key: bytes,
    expected_key_id: str,
) -> dict[str, Any]:
    """Verify signature, current artifact bytes, lineage, and result semantics."""

    secret = _signing_key(signing_key)
    key_id = _key_id(expected_key_id)
    signed = _require_exact_fields(receipt, RECEIPT_FIELDS, "consequence receipt")
    signature = _require_exact_fields(
        signed["signature"], SIGNATURE_FIELDS, "consequence receipt signature"
    )
    if signature["algorithm"] != SIGNATURE_ALGORITHM:
        raise ProbabilityConsequenceError(
            f"Consequence receipt signature algorithm must be {SIGNATURE_ALGORITHM}."
        )
    if signed["key_id"] != key_id or signature["key_id"] != key_id:
        raise ProbabilityConsequenceError(
            "Consequence receipt signing key ID is not trusted."
        )
    if not hmac.compare_digest(
        _sha256(signature["value"], "consequence signature"),
        _signature_value(signed, secret),
    ):
        raise ProbabilityConsequenceError("Consequence receipt signature is invalid.")
    if signed["schema_version"] != SCHEMA_VERSION or signed["receipt_type"] != RECEIPT_TYPE:
        raise ProbabilityConsequenceError("Consequence receipt schema or type is invalid.")

    source = _validate_probability_lineage(source_metadata, probability_raster_receipt)
    road_lineage = _validate_geometry_receipt(
        road_geometry_receipt, expected_kind="road_segments"
    )
    facility_lineage = _validate_geometry_receipt(
        facility_geometry_receipt, expected_kind="facilities"
    )
    _require_study_area_binding(source, road_lineage, "road geometry")
    _require_study_area_binding(source, facility_lineage, "facility geometry")
    generated_time = _parsed_timestamp(signed["generated_at"], "receipt generated_at")
    latest_source_time = max(
        _parsed_timestamp(source_metadata["generated_at"], "source generated_at"),
        _parsed_timestamp(road_lineage["source_timestamp"], "road source timestamp"),
        _parsed_timestamp(
            facility_lineage["source_timestamp"], "facility source timestamp"
        ),
    )
    if generated_time < latest_source_time:
        raise ProbabilityConsequenceError(
            "Consequence receipt generated_at predates trusted lineage."
        )
    raster_path = _regular_local_file(probability_raster_path, "probability raster")
    road_path = _regular_local_file(road_geometry_path, "road geometry")
    facility_path = _regular_local_file(facility_geometry_path, "facility geometry")
    with _probability_raster_snapshot(raster_path) as (_snapshot, raster_sha):
        pass
    _, road_sha = _read_bound_bytes(road_path, "road geometry")
    _, facility_sha = _read_bound_bytes(facility_path, "facility geometry")

    expected = {
        "source_timestamp": source_metadata["source_timestamp"],
        "dataset_mode": source_metadata["dataset_mode"],
        "operational_status": source_metadata["operational_status"],
        "confidence_class": source_metadata["confidence_class"],
        "official_warning": source_metadata["official_warning"],
        "processing_allowed": True,
        "study_area": source["study_area"],
        "run_id": source_metadata["run_id"],
        "model_id": source_metadata["model_id"],
        "model_revision": source_metadata["model_revision"],
        "git_commit": source_metadata["git_commit"],
        "model_run_manifest_sha256": source["model_run_manifest_sha256"],
        "probability_raster_receipt_sha256": _canonical_sha256(
            probability_raster_receipt, "probability raster receipt"
        ),
        "probability_raster_sha256": raster_sha,
        "probability_threshold": source["probability_threshold"],
        "road_geometry_receipt_sha256": _canonical_sha256(
            road_geometry_receipt, "road geometry receipt"
        ),
        "road_geometry_sha256": road_sha,
        "facility_geometry_receipt_sha256": _canonical_sha256(
            facility_geometry_receipt, "facility geometry receipt"
        ),
        "facility_geometry_sha256": facility_sha,
    }
    for field, expected_value in expected.items():
        if signed[field] != expected_value:
            raise ProbabilityConsequenceError(
                f"Consequence receipt {field} does not match trusted lineage."
            )
    if signed["probability_grid"] != source["probability_grid"]:
        raise ProbabilityConsequenceError(
            "Consequence receipt probability_grid does not match trusted lineage."
        )
    if road_sha != road_lineage["sha256"] or facility_sha != facility_lineage["sha256"]:
        raise ProbabilityConsequenceError(
            "Current feature geometry bytes do not match their lineage receipts."
        )
    if raster_sha != source["probability_raster_sha256"]:
        raise ProbabilityConsequenceError(
            "Current probability raster bytes do not match their lineage receipt."
        )

    method = _validate_method(signed["method"])
    threshold = _unit_interval(
        signed["probability_threshold"], "consequence probability_threshold"
    )
    roads = _validate_road_results(
        signed["roads"],
        pixel_area=method["pixel_area_m2"],
        threshold=threshold,
        decision_eligible=bool(signed["eligible_for_decision_layer"]),
    )
    facilities = _validate_facility_results(
        signed["facilities"],
        pixel_area=method["pixel_area_m2"],
        threshold=threshold,
        decision_eligible=bool(signed["eligible_for_decision_layer"]),
    )
    if len(roads) != road_lineage["feature_count"]:
        raise ProbabilityConsequenceError(
            "Consequence road count does not match the geometry receipt."
        )
    if len(facilities) != facility_lineage["feature_count"]:
        raise ProbabilityConsequenceError(
            "Consequence facility count does not match the geometry receipt."
        )

    expected_eligible = (
        source["decision_eligible"]
        and road_lineage["authority_status"] == "authoritative_for_study_area"
        and facility_lineage["authority_status"] == "authoritative_for_study_area"
    )
    for field in ("can_feed_decision_layer", "eligible_for_decision_layer"):
        if type(signed[field]) is not bool or signed[field] is not expected_eligible:
            raise ProbabilityConsequenceError(
                f"Consequence receipt {field} is inconsistent with trusted gates."
            )
    if expected_eligible:
        if signed["aggregation_status"] != "decision_eligible" or signed["reason_blocked"] != "":
            raise ProbabilityConsequenceError(
                "Eligible consequence receipt has inconsistent status or blocker text."
            )
    elif signed["aggregation_status"] != "report_only" or not _text(
        signed["reason_blocked"], "reason_blocked"
    ):
        raise ProbabilityConsequenceError(
            "Report-only consequence receipt requires an exact blocked reason."
        )
    return deepcopy(dict(signed))


def _validate_probability_lineage(
    source_metadata: Mapping[str, object],
    raster_receipt: Mapping[str, object],
) -> dict[str, Any]:
    source = _require_exact_fields(source_metadata, MODEL_RUN_FIELDS, "model run")
    metadata = _validate_source_metadata(source)
    if metadata.dataset_mode == "fixture_demo":
        raise ProbabilityConsequenceError(
            "Trusted real-feature consequences reject fixture_demo model runs."
        )
    if metadata.run_status != "completed":
        raise ProbabilityConsequenceError(
            "Probability consequences require run_status=completed."
        )
    if not metadata.processing_allowed:
        raise ProbabilityConsequenceError(
            "Probability consequences require processing_allowed=true."
        )
    if metadata.dataset_mode == "candidate" and source["official_warning"] is not False:
        raise ProbabilityConsequenceError(
            "Candidate probability runs must set official_warning=false."
        )
    source_time = _parsed_timestamp(source["source_timestamp"], "model source timestamp")
    model_generated_time = _parsed_timestamp(
        source["generated_at"], "model run generated_at"
    )
    if model_generated_time < source_time:
        raise ProbabilityConsequenceError(
            "Model run generated_at cannot predate source_timestamp."
        )
    receipt = _require_exact_fields(
        raster_receipt, PROBABILITY_RECEIPT_FIELDS, "probability raster receipt"
    )
    run_id = _text(source["run_id"], "model run run_id")
    if receipt["run_id"] != run_id:
        raise ProbabilityConsequenceError(
            "Probability raster receipt run_id does not match the model run."
        )
    manifest_sha = _canonical_sha256(source, "model run")
    if _sha256(
        receipt["model_run_manifest_sha256"],
        "probability raster model manifest sha256",
    ) != manifest_sha:
        raise ProbabilityConsequenceError(
            "Probability raster receipt is not bound to the exact model run."
        )
    grid = receipt["grid"]
    if not isinstance(grid, Mapping):
        raise ProbabilityConsequenceError(
            "Probability raster receipt grid must be an object."
        )
    nodata = _number(grid.get("nodata"), "probability raster nodata")
    if 0.0 <= nodata <= 1.0:
        raise ProbabilityConsequenceError(
            "Probability raster nodata must be outside [0, 1]."
        )
    target_crs = _text(source["target_crs"], "model run target_crs")
    resolution = _positive_pair(source["resolution"], "model run resolution")
    bounds = _ordered_bounds(source["bounds"], "model run bounds")
    threshold = _unit_interval(
        source["probability_threshold"], "model run probability_threshold"
    )
    if threshold in {0.0, 1.0}:
        raise ProbabilityConsequenceError(
            "Model run probability_threshold must be strictly between 0 and 1."
        )
    probability_grid = _validate_probability_grid(
        receipt["grid"],
        target_crs=target_crs,
        resolution=resolution,
        bounds=bounds,
        nodata=nodata,
    )
    decision_eligible = (
        metadata.dataset_mode == "official_input"
        and metadata.operational_status != "non_operational"
        and metadata.confidence_class != "low"
        and metadata.reference_mask_status == "confirmed_for_model_purpose"
        and metadata.can_feed_decision_layer
        and all(value is not None for _, value in metadata.validation_metrics)
    )
    if decision_eligible:
        decision = _validate_decision_feed_evidence(
            source,
            receipt,
            nodata=nodata,
            probability_threshold=threshold,
        )
        probability_grid = decision.probability_grid
    elif metadata.can_feed_decision_layer:
        raise ProbabilityConsequenceError(
            "Model run claims can_feed_decision_layer=true but fails promotion gates."
        )
    if not decision_eligible and not str(source["reason_blocked"]).strip():
        raise ProbabilityConsequenceError(
            "A report-only model run requires a non-empty reason_blocked."
        )
    return {
        "decision_eligible": decision_eligible,
        "study_area": _text(source["study_area"], "model run study_area"),
        "model_run_manifest_sha256": manifest_sha,
        "probability_raster_sha256": _sha256(
            receipt["probability_raster_sha256"], "probability raster sha256"
        ),
        "probability_grid": probability_grid,
        "probability_threshold": threshold,
    }


def _validate_geometry_receipt(
    receipt: Mapping[str, object], *, expected_kind: str
) -> dict[str, Any]:
    value = _require_exact_fields(
        receipt, GEOMETRY_RECEIPT_FIELDS, f"{expected_kind} geometry receipt"
    )
    kind = _text(value["feature_kind"], "geometry feature_kind")
    if kind != expected_kind:
        raise ProbabilityConsequenceError(
            f"Geometry feature_kind must be {expected_kind}."
        )
    status = _text(value["authority_status"], "geometry authority_status")
    if status not in AUTHORITY_STATUSES:
        raise ProbabilityConsequenceError(
            "Geometry authority_status is unsupported."
        )
    if value["processing_allowed"] is not True:
        raise ProbabilityConsequenceError(
            "Feature geometry requires processing_allowed=true."
        )
    assumptions = value["assumptions"]
    if (
        isinstance(assumptions, (str, bytes))
        or not isinstance(assumptions, Sequence)
        or not assumptions
    ):
        raise ProbabilityConsequenceError(
            "Geometry assumptions must be a non-empty array."
        )
    result = {
        "dataset_id": _text(value["dataset_id"], "geometry dataset_id"),
        "study_area": _text(value["study_area"], "geometry study_area"),
        "data_version": _text(value["data_version"], "geometry data_version"),
        "sha256": _sha256(value["sha256"], "geometry sha256"),
        "source_name": _text(value["source_name"], "geometry source_name"),
        "source_timestamp": value["source_timestamp"],
        "crs": _text(value["crs"], "geometry crs"),
        "feature_kind": kind,
        "feature_id_field": _text(
            value["feature_id_field"], "geometry feature_id_field"
        ),
        "area_id_field": _text(value["area_id_field"], "geometry area_id_field"),
        "feature_count": value["feature_count"],
        "authority_status": status,
    }
    _parsed_timestamp(result["source_timestamp"], "geometry source_timestamp")
    if (
        type(result["feature_count"]) is not int
        or result["feature_count"] <= 0
    ):
        raise ProbabilityConsequenceError(
            "Geometry feature_count must be a positive integer."
        )
    if result["feature_id_field"] == result["area_id_field"]:
        raise ProbabilityConsequenceError(
            "Geometry feature and area ID fields must be distinct."
        )
    for index, assumption in enumerate(assumptions):
        _text(assumption, f"geometry assumptions[{index}]")
    return result


def _require_study_area_binding(
    source: Mapping[str, Any],
    geometry_lineage: Mapping[str, Any],
    label: str,
) -> None:
    """Reject geometry receipts issued for a different study area."""

    if geometry_lineage["study_area"] != source["study_area"]:
        raise ProbabilityConsequenceError(
            f"{label.capitalize()} study_area does not match the model run."
        )


def _read_feature_geometry(
    document_bytes: bytes,
    *,
    lineage: Mapping[str, Any],
    probability_crs: str,
    probability_bounds: Sequence[float],
) -> list[dict[str, Any]]:
    try:
        document = json.loads(document_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProbabilityConsequenceError(
            "Feature geometry must be UTF-8 GeoJSON."
        ) from exc
    if not isinstance(document, Mapping) or document.get("type") != "FeatureCollection":
        raise ProbabilityConsequenceError(
            "Feature geometry must be a GeoJSON FeatureCollection."
        )
    document_crs = _geojson_crs(document.get("crs"))
    if document_crs.casefold() != str(lineage["crs"]).casefold():
        raise ProbabilityConsequenceError(
            "GeoJSON CRS does not match its geometry receipt."
        )
    raw_features = document.get("features")
    if isinstance(raw_features, (str, bytes)) or not isinstance(raw_features, Sequence):
        raise ProbabilityConsequenceError("GeoJSON features must be an array.")
    if len(raw_features) != lineage["feature_count"]:
        raise ProbabilityConsequenceError(
            "GeoJSON feature count does not match its geometry receipt."
        )
    try:
        from rasterio.crs import CRS
        from rasterio.warp import transform_geom
        from shapely.geometry import box, shape
    except ImportError as exc:  # pragma: no cover
        raise ProbabilityConsequenceError(
            "Probability consequences require rasterio and Shapely."
        ) from exc
    try:
        source_crs = CRS.from_user_input(document_crs)
        target_crs = CRS.from_user_input(probability_crs)
    except Exception as exc:
        raise ProbabilityConsequenceError("Feature or raster CRS is invalid.") from exc
    probability_box = box(*probability_bounds)
    features: list[dict[str, Any]] = []
    seen: set[str] = set()
    expected_geometry = (
        {"LineString", "MultiLineString"}
        if lineage["feature_kind"] == "road_segments"
        else {"Point"}
    )
    for index, raw_feature in enumerate(raw_features):
        if not isinstance(raw_feature, Mapping) or raw_feature.get("type") != "Feature":
            raise ProbabilityConsequenceError(f"GeoJSON feature {index} is invalid.")
        properties = raw_feature.get("properties")
        geometry = raw_feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            raise ProbabilityConsequenceError(
                f"GeoJSON feature {index} requires properties and geometry."
            )
        feature_id = _text(
            properties.get(lineage["feature_id_field"]),
            f"GeoJSON feature {index} ID",
        )
        area_id = _text(
            properties.get(lineage["area_id_field"]),
            f"GeoJSON feature {index} area ID",
        )
        if feature_id in seen:
            raise ProbabilityConsequenceError("Feature IDs must be unique.")
        seen.add(feature_id)
        try:
            transformed = (
                geometry
                if source_crs == target_crs
                else transform_geom(source_crs, target_crs, geometry, precision=12)
            )
            feature_shape = shape(transformed)
        except Exception as exc:
            raise ProbabilityConsequenceError(
                f"GeoJSON feature {index} could not be transformed."
            ) from exc
        if (
            feature_shape.geom_type not in expected_geometry
            or feature_shape.is_empty
            or not feature_shape.is_valid
        ):
            raise ProbabilityConsequenceError(
                f"GeoJSON feature {index} has an invalid geometry type or shape."
            )
        if lineage["feature_kind"] == "road_segments":
            if feature_shape.length <= 0 or not feature_shape.intersects(probability_box):
                raise ProbabilityConsequenceError(
                    f"Road feature {feature_id!r} does not intersect the probability raster."
                )
            feature = {
                "road_id": feature_id,
                "subdistrict_id": area_id,
                "road_class": _text(
                    properties.get("road_class"), f"road {feature_id} road_class"
                ),
                "bridge_flag": _strict_bool(
                    properties.get("bridge_flag"), f"road {feature_id} bridge_flag"
                ),
                "geometry": feature_shape,
            }
        else:
            if not probability_box.contains(feature_shape):
                raise ProbabilityConsequenceError(
                    f"Facility {feature_id!r} must lie strictly inside the probability raster."
                )
            verification = _text(
                properties.get("verification_status"),
                f"facility {feature_id} verification_status",
            )
            if verification not in FACILITY_VERIFICATION_STATUSES:
                raise ProbabilityConsequenceError(
                    f"Facility {feature_id!r} has an unsupported verification_status."
                )
            emergency_role = _text(
                properties.get("emergency_role"),
                f"facility {feature_id} emergency_role",
            )
            if emergency_role not in EMERGENCY_ROLES:
                raise ProbabilityConsequenceError(
                    f"Facility {feature_id!r} has an unsupported emergency_role."
                )
            feature = {
                "facility_id": feature_id,
                "subdistrict_id": area_id,
                "facility_type": _text(
                    properties.get("facility_type"),
                    f"facility {feature_id} facility_type",
                ),
                "verification_status": verification,
                "emergency_role": emergency_role,
                "geometry": feature_shape,
            }
        features.append(feature)
    id_field = "road_id" if lineage["feature_kind"] == "road_segments" else "facility_id"
    return sorted(features, key=lambda row: row[id_field])


def _road_consequences(
    features: Sequence[Mapping[str, Any]],
    *,
    raster: Mapping[str, Any],
    threshold: float,
    buffer_distance: float,
    decision_eligible: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for feature in features:
        statistics = _buffer_statistics(
            feature["geometry"].buffer(buffer_distance),
            raster=raster,
            threshold=threshold,
            feature_label=f"Road {feature['road_id']}",
        )
        above = statistics["flood_pixel_count"] > 0
        bridge_status = "not_a_bridge"
        if feature["bridge_flag"]:
            bridge_status = (
                "modeled_bridge_probability_above_threshold"
                if above
                else "modeled_bridge_probability_below_threshold"
            )
        sampled_area = statistics.pop("sampled_area_m2")
        results.append(
            {
                "road_id": feature["road_id"],
                "subdistrict_id": feature["subdistrict_id"],
                "road_class": feature["road_class"],
                "bridge_flag": feature["bridge_flag"],
                **statistics,
                "sampled_corridor_area_m2": sampled_area,
                "modeled_exposure_status": (
                    "modeled_probability_above_threshold"
                    if above
                    else "modeled_probability_below_threshold"
                ),
                "bridge_probability_evidence_status": bridge_status,
                "observed_closure_status": "not_observed",
                "eligible_for_decision_layer": decision_eligible,
            }
        )
    return results


def _facility_consequences(
    features: Sequence[Mapping[str, Any]],
    *,
    raster: Mapping[str, Any],
    threshold: float,
    buffer_distance: float,
    decision_eligible: bool,
) -> list[dict[str, Any]]:
    try:
        from rasterio.transform import rowcol
    except ImportError as exc:  # pragma: no cover
        raise ProbabilityConsequenceError(
            "Probability consequences require rasterio."
        ) from exc
    results: list[dict[str, Any]] = []
    values = raster["values"]
    valid_mask = raster["valid_mask"]
    transform = raster["transform_object"]
    for feature in features:
        point = feature["geometry"]
        row, column = rowcol(transform, point.x, point.y)
        if (
            row < 0
            or column < 0
            or row >= values.shape[0]
            or column >= values.shape[1]
            or not bool(valid_mask[row, column])
        ):
            raise ProbabilityConsequenceError(
                f"Facility {feature['facility_id']!r} has no valid probability at its point."
            )
        point_probability = round(float(values[row, column]), 6)
        statistics = _buffer_statistics(
            point.buffer(buffer_distance),
            raster=raster,
            threshold=threshold,
            feature_label=f"Facility {feature['facility_id']}",
        )
        above = point_probability >= threshold or statistics["flood_pixel_count"] > 0
        verified_designated_role = (
            feature["verification_status"] == "agency_verified"
            and feature["emergency_role"] == "designated_evacuation"
        )
        sampled_area = statistics.pop("sampled_area_m2")
        results.append(
            {
                "facility_id": feature["facility_id"],
                "subdistrict_id": feature["subdistrict_id"],
                "facility_type": feature["facility_type"],
                "verification_status": feature["verification_status"],
                "emergency_role": feature["emergency_role"],
                "point_flood_probability_0_1": point_probability,
                **statistics,
                "sampled_buffer_area_m2": sampled_area,
                "modeled_exposure_status": (
                    "modeled_probability_above_threshold"
                    if above
                    else "modeled_probability_below_threshold"
                ),
                "safe_destination_status": "not_determined_by_probability_model",
                "eligible_for_decision_layer": decision_eligible,
                "agency_verified_designated_role": verified_designated_role,
            }
        )
    return results


def _buffer_statistics(
    geometry: Any,
    *,
    raster: Mapping[str, Any],
    threshold: float,
    feature_label: str,
) -> dict[str, Any]:
    try:
        from rasterio.features import geometry_mask
        from shapely.geometry import mapping
    except ImportError as exc:  # pragma: no cover
        raise ProbabilityConsequenceError(
            "Probability consequences require rasterio and Shapely."
        ) from exc
    inside = geometry_mask(
        [mapping(geometry)],
        out_shape=raster["values"].shape,
        transform=raster["transform_object"],
        invert=True,
        all_touched=False,
    )
    selected = inside & raster["valid_mask"]
    values = sorted(float(value) for value in raster["values"][selected].tolist())
    if not values:
        raise ProbabilityConsequenceError(
            f"{feature_label} buffer contains no valid probability pixel centers."
        )
    sample_count = len(values)
    flood_count = sum(value >= threshold for value in values)
    return {
        "mean_flood_probability_0_1": round(math.fsum(values) / sample_count, 6),
        "p90_flood_probability_0_1": round(_linear_quantile(values, 0.90), 6),
        "max_flood_probability_0_1": round(max(values), 6),
        "binary_flood_share_0_1": round(flood_count / sample_count, 6),
        "sample_pixel_count": sample_count,
        "flood_pixel_count": flood_count,
        "sampled_area_m2": round(sample_count * float(raster["pixel_area"]), 6),
    }


def _validate_method(value: object) -> dict[str, float]:
    method = _require_exact_fields(value, METHOD_FIELDS, "consequence method")
    if (
        method["statistics_version"] != "1.0"
        or method["sampling_rule"] != "pixel_center_with_explicit_metric_buffer"
        or method["all_touched"] is not False
        or method["quantile_method"] != "linear"
        or method["road_semantics"]
        != "modeled probability evidence; not an observed closure"
        or method["facility_semantics"]
        != "modeled exposure evidence; not facility suitability or safe-route proof"
    ):
        raise ProbabilityConsequenceError(
            "Consequence receipt sampling or safety semantics are unsupported."
        )
    return {
        "road_buffer_distance_m": _positive_distance(
            method["road_buffer_distance_m"], "road buffer"
        ),
        "facility_buffer_distance_m": _positive_distance(
            method["facility_buffer_distance_m"], "facility buffer"
        ),
        "pixel_area_m2": _positive_distance(method["pixel_area_m2"], "pixel area"),
    }


def _validate_road_results(
    value: object, *, pixel_area: float, threshold: float, decision_eligible: bool
) -> list[dict[str, Any]]:
    rows = _result_array(value, "roads")
    previous: str | None = None
    for index, raw in enumerate(rows):
        row = _require_exact_fields(raw, ROAD_RESULT_FIELDS, f"roads[{index}]")
        road_id = _text(row["road_id"], f"roads[{index}].road_id")
        if previous is not None and road_id <= previous:
            raise ProbabilityConsequenceError(
                "Consequence roads must have unique IDs in ascending order."
            )
        previous = road_id
        _text(row["subdistrict_id"], f"roads[{index}].subdistrict_id")
        _text(row["road_class"], f"roads[{index}].road_class")
        _validate_probability_statistics(
            row,
            pixel_area=pixel_area,
            threshold=threshold,
            area_field="sampled_corridor_area_m2",
        )
        if row["observed_closure_status"] != "not_observed":
            raise ProbabilityConsequenceError(
                "Road consequences must not claim an observed closure."
            )
        if type(row["bridge_flag"]) is not bool:
            raise ProbabilityConsequenceError("Road bridge_flag must be boolean.")
        expected_bridge_status = "not_a_bridge"
        if row["bridge_flag"]:
            expected_bridge_status = (
                "modeled_bridge_probability_above_threshold"
                if row["flood_pixel_count"] > 0
                else "modeled_bridge_probability_below_threshold"
            )
        if row["bridge_probability_evidence_status"] != expected_bridge_status:
            raise ProbabilityConsequenceError(
                "Road bridge probability evidence is internally inconsistent."
            )
        if row["eligible_for_decision_layer"] is not decision_eligible:
            raise ProbabilityConsequenceError(
                "Road eligibility is inconsistent with the receipt."
            )
    return [dict(row) for row in rows]


def _validate_facility_results(
    value: object, *, pixel_area: float, threshold: float, decision_eligible: bool
) -> list[dict[str, Any]]:
    rows = _result_array(value, "facilities")
    previous: str | None = None
    for index, raw in enumerate(rows):
        row = _require_exact_fields(
            raw, FACILITY_RESULT_FIELDS, f"facilities[{index}]"
        )
        facility_id = _text(row["facility_id"], f"facilities[{index}].facility_id")
        if previous is not None and facility_id <= previous:
            raise ProbabilityConsequenceError(
                "Consequence facilities must have unique IDs in ascending order."
            )
        previous = facility_id
        _text(row["subdistrict_id"], f"facilities[{index}].subdistrict_id")
        _text(row["facility_type"], f"facilities[{index}].facility_type")
        if row["verification_status"] not in FACILITY_VERIFICATION_STATUSES:
            raise ProbabilityConsequenceError(
                "Facility consequence verification_status is unsupported."
            )
        if row["emergency_role"] not in EMERGENCY_ROLES:
            raise ProbabilityConsequenceError(
                "Facility consequence emergency_role is unsupported."
            )
        _unit_interval(
            row["point_flood_probability_0_1"],
            f"facilities[{index}].point_probability",
        )
        _validate_probability_statistics(
            row,
            pixel_area=pixel_area,
            threshold=threshold,
            area_field="sampled_buffer_area_m2",
        )
        if row["safe_destination_status"] != "not_determined_by_probability_model":
            raise ProbabilityConsequenceError(
                "Facility probability evidence cannot determine a safe destination."
            )
        if row["eligible_for_decision_layer"] is not decision_eligible:
            raise ProbabilityConsequenceError(
                "Facility eligibility is inconsistent with the receipt."
            )
        expected_designated_role = (
            row["verification_status"] == "agency_verified"
            and row["emergency_role"] == "designated_evacuation"
        )
        if (
            type(row["agency_verified_designated_role"]) is not bool
            or row["agency_verified_designated_role"] is not expected_designated_role
        ):
            raise ProbabilityConsequenceError(
                "Facility designated-role evidence is inconsistent with verification."
            )
        expected_exposure = (
            "modeled_probability_above_threshold"
            if row["point_flood_probability_0_1"] >= threshold
            or row["flood_pixel_count"] > 0
            else "modeled_probability_below_threshold"
        )
        if row["modeled_exposure_status"] != expected_exposure:
            raise ProbabilityConsequenceError(
                "Facility modeled exposure is inconsistent with point and buffer evidence."
            )
    return [dict(row) for row in rows]


def _validate_probability_statistics(
    row: Mapping[str, object],
    *,
    pixel_area: float,
    threshold: float,
    area_field: str,
) -> None:
    mean = _unit_interval(row["mean_flood_probability_0_1"], "mean probability")
    p90 = _unit_interval(row["p90_flood_probability_0_1"], "p90 probability")
    maximum = _unit_interval(row["max_flood_probability_0_1"], "max probability")
    if p90 > maximum or mean > maximum:
        raise ProbabilityConsequenceError(
            "Probability statistics are internally inconsistent."
        )
    share = _unit_interval(row["binary_flood_share_0_1"], "binary flood share")
    sample_count = _positive_int(row["sample_pixel_count"], "sample pixel count")
    flood_count = _nonnegative_int(row["flood_pixel_count"], "flood pixel count")
    if flood_count > sample_count or not _same_number(
        share, round(flood_count / sample_count, 6)
    ):
        raise ProbabilityConsequenceError(
            "Probability pixel counts and binary share are inconsistent."
        )
    if not _same_number(
        _number(row[area_field], area_field), round(sample_count * pixel_area, 6)
    ):
        raise ProbabilityConsequenceError(
            "Sampled feature area is inconsistent with pixel count and grid area."
        )
    expected_status = (
        "modeled_probability_above_threshold"
        if flood_count > 0
        else "modeled_probability_below_threshold"
    )
    if row["modeled_exposure_status"] != expected_status:
        # A facility's exact point can exceed threshold even when no buffered
        # pixel center does; the facility-specific validator checks that case.
        if (
            "point_flood_probability_0_1" not in row
            or _unit_interval(
                row["point_flood_probability_0_1"], "facility point probability"
            )
            < threshold
        ):
            raise ProbabilityConsequenceError(
                "Modeled exposure status is inconsistent with sampled pixels."
            )


def _require_metre_projected_crs(value: object) -> None:
    try:
        from rasterio.crs import CRS

        crs = CRS.from_user_input(value)
        unit_name, unit_factor = crs.linear_units_factor
    except Exception as exc:
        raise ProbabilityConsequenceError(
            "Probability CRS must be a valid projected metre-based CRS."
        ) from exc
    if not crs.is_projected or "met" not in unit_name.casefold() or not math.isclose(
        float(unit_factor), 1.0, rel_tol=0.0, abs_tol=1e-12
    ):
        raise ProbabilityConsequenceError(
            "Probability CRS must use projected metre units for feature buffers."
        )


def _signature_value(payload: Mapping[str, object], key: bytes) -> str:
    unsigned = deepcopy(dict(payload))
    signature = unsigned.get("signature")
    if signature is not None:
        if not isinstance(signature, Mapping):
            raise ProbabilityConsequenceError("Receipt signature must be an object.")
        unsigned["signature"] = {
            field: value for field, value in signature.items() if field != "value"
        }
    try:
        encoded = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProbabilityConsequenceError(
            "Consequence receipt must contain canonical JSON values."
        ) from exc
    return hmac.new(key, encoded, hashlib.sha256).hexdigest()


def _reject_private_paths(value: object) -> None:
    if isinstance(value, Mapping):
        for child in value.values():
            _reject_private_paths(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            _reject_private_paths(child)
    elif isinstance(value, str) and PRIVATE_PATH_RE.search(value):
        raise ProbabilityConsequenceError(
            "Published consequence lineage must not contain private absolute paths."
        )


def _geojson_crs(value: object) -> str:
    if not isinstance(value, Mapping) or value.get("type") != "name":
        raise ProbabilityConsequenceError(
            "GeoJSON must declare an explicit named CRS."
        )
    properties = value.get("properties")
    if not isinstance(properties, Mapping):
        raise ProbabilityConsequenceError("GeoJSON CRS properties are invalid.")
    return _text(properties.get("name"), "GeoJSON CRS name")


def _result_array(value: object, label: str) -> list[Mapping[str, object]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ProbabilityConsequenceError(f"Consequence {label} must be non-empty.")
    if any(not isinstance(row, Mapping) for row in value):
        raise ProbabilityConsequenceError(f"Consequence {label} rows must be objects.")
    return list(value)


def _positive_pair(value: object, label: str) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        raise ProbabilityConsequenceError(f"{label} must contain two numbers.")
    result = [_number(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if any(item <= 0 for item in result):
        raise ProbabilityConsequenceError(f"{label} values must be positive.")
    return result


def _ordered_bounds(value: object, label: str) -> tuple[float, float, float, float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 4:
        raise ProbabilityConsequenceError(f"{label} must contain four numbers.")
    result = tuple(_number(item, f"{label}[{index}]") for index, item in enumerate(value))
    if result[0] >= result[2] or result[1] >= result[3]:
        raise ProbabilityConsequenceError(f"{label} must be ordered.")
    return result


def _positive_distance(value: object, label: str) -> float:
    result = _number(value, label)
    if result <= 0 or result > 5000:
        raise ProbabilityConsequenceError(
            f"{label} must be greater than zero and no more than 5000 metres."
        )
    return result


def _unit_interval(value: object, label: str) -> float:
    result = _number(value, label)
    if not 0.0 <= result <= 1.0:
        raise ProbabilityConsequenceError(f"{label} must be within [0, 1].")
    return result


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProbabilityConsequenceError(f"{label} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise ProbabilityConsequenceError(f"{label} must be finite.")
    return result


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ProbabilityConsequenceError(f"{label} must be a positive integer.")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ProbabilityConsequenceError(
            f"{label} must be a non-negative integer."
        )
    return value


def _strict_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ProbabilityConsequenceError(f"{label} must be a boolean.")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProbabilityConsequenceError(f"{label} must not be blank.")
    if PRIVATE_PATH_RE.search(value):
        raise ProbabilityConsequenceError(f"{label} must not contain a private path.")
    return value.strip()
