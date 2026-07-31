"""Fail-closed aggregation bridge for external flood-probability outputs.

The module intentionally depends only on the Python standard library. GeoAI or
another isolated runner may produce the probability cells, but FloodGuard owns
the gate checks and the area-summary contract before downstream decision use.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any


DATASET_MODES = frozenset({"fixture_demo", "candidate", "official_input"})
CONFIDENCE_CLASSES = frozenset({"low", "medium", "high"})
OPERATIONAL_STATUSES = frozenset(
    {"non_operational", "planning_only", "agency_operational"}
)
RUN_STATUSES = frozenset({"blocked", "prepared", "running", "completed", "failed"})
VALIDATION_METRICS = (
    "iou",
    "f1_dice",
    "precision",
    "recall",
    "area_error_ratio",
    "brier_score",
    "expected_calibration_error",
)
MODEL_FAMILIES = frozenset(
    {"deterministic_sar_baseline", "weak_label_logistic", "geoai"}
)
EXPECTED_GEOAI_VERSION = "0.41.1"
EXPECTED_GEOAI_COMMIT = "6833c8b71fb18f5b8ea17d5d9f8e0745157643c2"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
EPSG_RE = re.compile(r"^EPSG:\d+$", re.IGNORECASE)
PRIVATE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\|file://|/(?:Users|home|root|tmp|var|private)/)",
    re.IGNORECASE,
)
MODEL_RUN_FIELDS = frozenset(
    {
        "schema_version",
        "dataset_mode",
        "operational_status",
        "source_timestamp",
        "generated_at",
        "confidence_class",
        "source_name",
        "assumptions",
        "official_warning",
        "data_version",
        "git_commit",
        "run_id",
        "study_area",
        "model_family",
        "run_status",
        "geoai_version",
        "geoai_commit",
        "model_id",
        "model_revision",
        "model_sha256",
        "architecture",
        "encoder",
        "encoder_weights",
        "num_channels",
        "channel_names",
        "preprocessing",
        "input_manifest_rows",
        "encoded_feature_sha256",
        "reference_mask_sha256",
        "prepared_tile_manifest_sha256",
        "spatial_holdout_ids",
        "spatial_partitions",
        "reference_mask_id",
        "reference_mask_status",
        "target_crs",
        "resolution",
        "bounds",
        "tile_size",
        "overlap",
        "stride",
        "batch_size",
        "device",
        "flood_class_index",
        "probability_threshold",
        "external_output_workspace",
        "processing_scope",
        "processing_allowed",
        "can_feed_decision_layer",
        "reason_blocked",
        "validation_metrics",
        "error_categories",
    }
)
INPUT_MANIFEST_FIELDS = frozenset(
    {"product_id", "role", "sha256", "source_timestamp", "processing_allowed"}
)
PREPROCESSING_FIELDS = frozenset(
    {"method", "value_domain", "sidecar_sha256", "transforms"}
)
TRANSFORM_FIELDS = frozenset(
    {"name", "physical_min", "physical_max", "units", "description"}
)
SPATIAL_PARTITION_FIELDS = frozenset({"spatial_group_id", "split", "bounds"})
PROBABILITY_RECEIPT_FIELDS = frozenset(
    {
        "run_id",
        "model_run_manifest_sha256",
        "probability_raster_sha256",
        "grid",
    }
)
PROBABILITY_GRID_FIELDS = frozenset(
    {
        "crs",
        "transform",
        "width",
        "height",
        "bounds",
        "count",
        "dtypes",
        "descriptions",
        "nodata",
    }
)


class ProbabilityAggregationError(ValueError):
    """Raised when probabilities, provenance, or promotion gates are invalid."""


@dataclass(frozen=True, slots=True)
class _SourceMetadata:
    dataset_mode: str
    operational_status: str
    run_status: str
    source_name: str
    source_timestamp: str
    confidence_class: str
    assumptions: tuple[str, ...]
    processing_scope: str
    reference_mask_status: str
    processing_allowed: bool
    can_feed_decision_layer: bool
    reason_blocked: str
    validation_metrics: tuple[tuple[str, float | None], ...]


@dataclass(frozen=True, slots=True)
class _DecisionReceipt:
    run_id: str
    model_run_manifest_sha256: str
    probability_raster_sha256: str
    probability_grid: dict[str, Any]
    git_commit: str
    model_id: str
    model_revision: str
    geoai_version: str | None
    geoai_commit: str | None


def aggregate_probability_cells(
    probabilities: Iterable[object],
    *,
    subdistrict_id: str,
    subdistrict_name: str,
    nodata: object,
    probability_threshold: object,
    source_metadata: Mapping[str, object],
    probability_raster_receipt: Mapping[str, object] | None = None,
    allow_report_only: bool = False,
) -> dict[str, Any]:
    """Aggregate one reporting unit's probability cells into FloodGuard fields.

    Valid probability cells must be finite values in ``[0, 1]``. ``nodata`` is
    mandatory, finite, and outside that interval. The P90 uses linear
    interpolation, matching the existing NumPy-based area summarizer.

    Raw caller-supplied cell iterables are report-only. Even a complete
    ``official_input`` manifest and raster receipt are rejected after receipt
    validation because this function cannot independently re-hash a raster or
    prove that the supplied cells came from the named area's zonal mask. A
    trusted raster-and-zonal extraction adapter in
    ``floodguard.trusted_zonal_adapter`` owns that filesystem and signing
    boundary. Fixture, candidate, or otherwise blocked runs raise by default;
    they may be summarized only with ``allow_report_only=True`` and then carry
    false eligibility flags.
    """

    area_id = _nonempty_text(subdistrict_id, "subdistrict_id")
    area_name = _nonempty_text(subdistrict_name, "subdistrict_name")
    if type(allow_report_only) is not bool:
        raise ProbabilityAggregationError("allow_report_only must be a boolean.")

    metadata = _validate_source_metadata(source_metadata)
    nodata_value = _numeric_value(nodata, "nodata")
    if not math.isfinite(nodata_value):
        raise ProbabilityAggregationError("nodata must be finite.")
    if 0.0 <= nodata_value <= 1.0:
        raise ProbabilityAggregationError(
            "nodata must be separate from and outside the [0, 1] probability range."
        )
    threshold = _numeric_value(probability_threshold, "probability_threshold")
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ProbabilityAggregationError(
            "probability_threshold must be finite and between 0 and 1."
        )

    decision_eligible = (
        metadata.dataset_mode == "official_input"
        and metadata.operational_status != "non_operational"
        and metadata.run_status == "completed"
        and metadata.confidence_class != "low"
        and metadata.reference_mask_status == "confirmed_for_model_purpose"
        and metadata.processing_allowed
        and metadata.can_feed_decision_layer
        and all(value is not None for _, value in metadata.validation_metrics)
    )
    if not decision_eligible and not allow_report_only:
        reasons = _promotion_blockers(metadata)
        raise ProbabilityAggregationError(
            "Probability source is not decision-eligible: "
            + "; ".join(reasons)
            + ". Pass allow_report_only=True only for an explicitly labelled "
            "research/demo summary."
        )
    if not decision_eligible and not metadata.reason_blocked:
        raise ProbabilityAggregationError(
            "reason_blocked is required for report-only probability sources."
        )

    valid: list[float] = []
    for index, raw_value in enumerate(probabilities):
        value = _numeric_value(raw_value, f"probabilities[{index}]")
        if value == nodata_value:
            continue
        if not math.isfinite(value):
            raise ProbabilityAggregationError(
                f"probabilities[{index}] must be finite or equal nodata."
            )
        if not 0.0 <= value <= 1.0:
            raise ProbabilityAggregationError(
                f"probabilities[{index}] must be between 0 and 1 or equal nodata."
            )
        valid.append(value)
    if not valid:
        raise ProbabilityAggregationError(
            "probabilities must contain at least one valid, non-nodata cell."
        )

    # Validate ordinary scalar inputs before evaluating the promotion receipt so
    # callers still receive precise errors for malformed cells. A schema-complete
    # receipt is then checked for internal consistency, but it cannot establish
    # that this caller-supplied iterable came from the named raster and area mask.
    if decision_eligible:
        _validate_decision_feed_evidence(
            source_metadata,
            probability_raster_receipt,
            nodata=nodata_value,
            probability_threshold=threshold,
        )
        raise ProbabilityAggregationError(
            "Decision feed is disabled for caller-supplied probability cells: "
            "use the trusted raster-and-zonal extraction adapter in "
            "floodguard.trusted_zonal_adapter to independently verify the raster "
            "bytes and bind the selected cells to the area."
        )

    ordered = sorted(valid)
    mean_probability = sum(ordered) / len(ordered)
    binary_share = sum(value >= threshold for value in ordered) / len(ordered)
    effective_reason = "" if decision_eligible else metadata.reason_blocked

    return {
        "subdistrict_id": area_id,
        "subdistrict_name": area_name,
        "mean_flood_probability_0_1": round(mean_probability, 6),
        "p90_flood_probability_0_1": round(
            _linear_quantile(ordered, 0.90),
            6,
        ),
        "binary_flood_share_0_1": round(binary_share, 6),
        "sample_pixel_count": len(ordered),
        "probability_threshold": threshold,
        "dataset_mode": metadata.dataset_mode,
        "operational_status": metadata.operational_status,
        "run_status": metadata.run_status,
        "source_name": metadata.source_name,
        "source_timestamp": metadata.source_timestamp,
        "confidence_class": metadata.confidence_class,
        "assumptions": list(metadata.assumptions),
        "processing_scope": metadata.processing_scope,
        "reference_mask_status": metadata.reference_mask_status,
        "validation_metrics": dict(metadata.validation_metrics),
        "processing_allowed": metadata.processing_allowed,
        "can_feed_decision_layer": decision_eligible,
        "eligible_for_decision_layer": decision_eligible,
        "eligible_for_fpps": decision_eligible,
        "aggregation_status": (
            "decision_eligible" if decision_eligible else "report_only"
        ),
        "reason_blocked": effective_reason,
        "run_id": None,
        "model_run_manifest_sha256": None,
        "probability_raster_sha256": None,
        "probability_grid": None,
        "git_commit": None,
        "model_id": None,
        "model_revision": None,
        "geoai_version": None,
        "geoai_commit": None,
    }


def _validate_decision_feed_evidence(
    manifest: Mapping[str, object],
    raster_receipt: Mapping[str, object] | None,
    *,
    nodata: float,
    probability_threshold: float,
) -> _DecisionReceipt:
    """Validate the complete public model-run and its bound raster receipt."""

    _require_exact_fields(manifest, MODEL_RUN_FIELDS, "model-run manifest")
    if manifest["schema_version"] != "1.0":
        raise ProbabilityAggregationError(
            "model-run manifest schema_version must be 1.0."
        )
    if type(manifest["official_warning"]) is not bool:
        raise ProbabilityAggregationError(
            "model-run manifest official_warning must be a boolean."
        )

    source_time = _parsed_timestamp(
        manifest["source_timestamp"],
        "model-run manifest source_timestamp",
    )
    generated_time = _parsed_timestamp(
        manifest["generated_at"],
        "model-run manifest generated_at",
    )
    if generated_time < source_time:
        raise ProbabilityAggregationError(
            "model-run manifest generated_at cannot predate source_timestamp."
        )

    _nonempty_text(manifest["source_name"], "model-run manifest source_name")
    _nonempty_text(manifest["data_version"], "model-run manifest data_version")
    git_commit = _commit_sha(manifest["git_commit"], "model-run manifest git_commit")
    run_id = _nonempty_text(manifest["run_id"], "model-run manifest run_id")
    _nonempty_text(manifest["study_area"], "model-run manifest study_area")
    assumptions = _json_string_array(
        manifest["assumptions"],
        "model-run manifest assumptions",
        minimum=1,
    )
    if len(set(assumptions)) != len(assumptions):
        raise ProbabilityAggregationError(
            "model-run manifest assumptions must be unique."
        )
    error_categories = _json_string_array(
        manifest["error_categories"],
        "model-run manifest error_categories",
    )
    if len(set(error_categories)) != len(error_categories):
        raise ProbabilityAggregationError(
            "model-run manifest error_categories must be unique."
        )

    model_family = _nonempty_text(
        manifest["model_family"], "model-run manifest model_family"
    )
    if model_family not in MODEL_FAMILIES:
        raise ProbabilityAggregationError("model-run manifest model_family is invalid.")
    model_id = _nonempty_text(manifest["model_id"], "model-run manifest model_id")
    model_revision = _nonempty_text(
        manifest["model_revision"], "model-run manifest model_revision"
    )
    _sha256(manifest["model_sha256"], "model-run manifest model_sha256")
    _nonempty_text(manifest["architecture"], "model-run manifest architecture")
    _nonempty_text(manifest["encoder"], "model-run manifest encoder")
    encoder_weights = manifest["encoder_weights"]
    if encoder_weights is not None:
        _nonempty_text(
            encoder_weights,
            "model-run manifest encoder_weights",
        )

    geoai_version: str | None
    geoai_commit: str | None
    if model_family == "geoai":
        geoai_version = _nonempty_text(
            manifest["geoai_version"], "model-run manifest geoai_version"
        )
        if geoai_version != EXPECTED_GEOAI_VERSION:
            raise ProbabilityAggregationError(
                "model-run manifest must pin geoai_version=0.41.1."
            )
        geoai_commit = _commit_sha(
            manifest["geoai_commit"], "model-run manifest geoai_commit"
        )
        if geoai_commit != EXPECTED_GEOAI_COMMIT:
            raise ProbabilityAggregationError(
                "model-run manifest geoai_commit does not match the reviewed source."
            )
    else:
        geoai_version = _nullable_text(
            manifest["geoai_version"], "model-run manifest geoai_version"
        )
        geoai_commit = _nullable_commit(
            manifest["geoai_commit"], "model-run manifest geoai_commit"
        )

    channel_count = _positive_int(
        manifest["num_channels"], "model-run manifest num_channels"
    )
    if not 6 <= channel_count <= 8:
        raise ProbabilityAggregationError(
            "model-run manifest num_channels must be between 6 and 8."
        )
    channel_names = _json_string_array(
        manifest["channel_names"],
        "model-run manifest channel_names",
        minimum=6,
        maximum=8,
    )
    if len(channel_names) != channel_count or len(set(channel_names)) != len(
        channel_names
    ):
        raise ProbabilityAggregationError(
            "model-run manifest channel_names must be unique and match num_channels."
        )
    _validate_preprocessing(manifest["preprocessing"], channel_names)

    input_rows = _validate_input_manifest(
        manifest["input_manifest_rows"],
        channel_names=channel_names,
        source_time=source_time,
    )
    encoded_feature_sha = _sha256(
        manifest["encoded_feature_sha256"],
        "model-run manifest encoded_feature_sha256",
    )
    reference_mask_sha = _sha256(
        manifest["reference_mask_sha256"],
        "model-run manifest reference_mask_sha256",
    )
    prepared_tile_sha = _sha256(
        manifest["prepared_tile_manifest_sha256"],
        "model-run manifest prepared_tile_manifest_sha256",
    )
    if len({encoded_feature_sha, reference_mask_sha, prepared_tile_sha}) != 3:
        raise ProbabilityAggregationError(
            "Feature, reference-mask, and prepared-tile checksums must be distinct."
        )
    reference_mask_id = _nonempty_text(
        manifest["reference_mask_id"],
        "model-run manifest reference_mask_id",
    )
    reference_row = input_rows["reference_mask"]
    if (
        reference_row["product_id"] != reference_mask_id
        or reference_row["sha256"] != reference_mask_sha
    ):
        raise ProbabilityAggregationError(
            "Reference-mask ID and checksum must match its input receipt."
        )

    holdout_ids = _json_string_array(
        manifest["spatial_holdout_ids"],
        "model-run manifest spatial_holdout_ids",
        minimum=1,
    )
    if len(set(holdout_ids)) != len(holdout_ids):
        raise ProbabilityAggregationError(
            "model-run manifest spatial_holdout_ids must be unique."
        )
    target_crs = _nonempty_text(manifest["target_crs"], "model-run manifest target_crs")
    if not EPSG_RE.fullmatch(target_crs):
        raise ProbabilityAggregationError(
            "model-run manifest target_crs must be an explicit EPSG identifier."
        )
    resolution = _number_array(
        manifest["resolution"],
        "model-run manifest resolution",
        length=2,
        positive=True,
    )
    bounds = _bounds(
        manifest["bounds"],
        "model-run manifest bounds",
    )
    _validate_spatial_partitions(
        manifest["spatial_partitions"],
        holdout_ids=holdout_ids,
        run_bounds=bounds,
    )

    tile_size = _positive_int(manifest["tile_size"], "model-run manifest tile_size")
    overlap = _nonnegative_int(manifest["overlap"], "model-run manifest overlap")
    stride = _positive_int(manifest["stride"], "model-run manifest stride")
    if overlap >= tile_size or stride != tile_size - overlap:
        raise ProbabilityAggregationError(
            "model-run tile receipt requires overlap < tile_size and "
            "stride = tile_size - overlap."
        )
    _positive_int(manifest["batch_size"], "model-run manifest batch_size")
    _nonempty_text(manifest["device"], "model-run manifest device")
    flood_class_index = _nonnegative_int(
        manifest["flood_class_index"],
        "model-run manifest flood_class_index",
    )
    if flood_class_index != 1:
        raise ProbabilityAggregationError(
            "Decision feed requires explicit binary flood_class_index=1."
        )
    manifest_threshold = _finite_number(
        manifest["probability_threshold"],
        "model-run manifest probability_threshold",
    )
    if not 0.0 < manifest_threshold < 1.0 or not _same_number(
        manifest_threshold, probability_threshold
    ):
        raise ProbabilityAggregationError(
            "Aggregation probability_threshold must match the bounded model-run receipt."
        )
    public_workspace = _nonempty_text(
        manifest["external_output_workspace"],
        "model-run manifest external_output_workspace",
    )
    if PRIVATE_PATH_RE.search(public_workspace) or public_workspace.startswith(
        ("/", "\\")
    ):
        raise ProbabilityAggregationError(
            "model-run manifest external_output_workspace must be a redacted relative path."
        )
    _nonempty_text(manifest["processing_scope"], "model-run manifest processing_scope")
    metrics = manifest["validation_metrics"]
    _require_exact_fields(
        metrics,
        frozenset(VALIDATION_METRICS),
        "model-run manifest validation_metrics",
    )

    if raster_receipt is None:
        raise ProbabilityAggregationError(
            "Decision feed requires a probability_raster_receipt."
        )
    _require_exact_fields(
        raster_receipt,
        PROBABILITY_RECEIPT_FIELDS,
        "probability_raster_receipt",
    )
    receipt_run_id = _nonempty_text(
        raster_receipt["run_id"], "probability_raster_receipt.run_id"
    )
    if receipt_run_id != run_id:
        raise ProbabilityAggregationError(
            "Probability raster receipt run_id does not match the model-run manifest."
        )
    manifest_sha = _canonical_sha256(manifest, "model-run manifest")
    receipt_manifest_sha = _sha256(
        raster_receipt["model_run_manifest_sha256"],
        "probability_raster_receipt.model_run_manifest_sha256",
    )
    if receipt_manifest_sha != manifest_sha:
        raise ProbabilityAggregationError(
            "Probability raster receipt is not bound to the exact model-run manifest."
        )
    raster_sha = _sha256(
        raster_receipt["probability_raster_sha256"],
        "probability_raster_receipt.probability_raster_sha256",
    )
    probability_grid = _validate_probability_grid(
        raster_receipt["grid"],
        target_crs=target_crs,
        resolution=resolution,
        bounds=bounds,
        nodata=nodata,
    )
    return _DecisionReceipt(
        run_id=run_id,
        model_run_manifest_sha256=manifest_sha,
        probability_raster_sha256=raster_sha,
        probability_grid=probability_grid,
        git_commit=git_commit,
        model_id=model_id,
        model_revision=model_revision,
        geoai_version=geoai_version,
        geoai_commit=geoai_commit,
    )


def _validate_preprocessing(value: object, channel_names: list[str]) -> None:
    preprocessing = _require_exact_fields(
        value,
        PREPROCESSING_FIELDS,
        "model-run manifest preprocessing",
    )
    if preprocessing["method"] != "fixed_clip_scale_to_uint8":
        raise ProbabilityAggregationError(
            "Decision feed requires preprocessing method fixed_clip_scale_to_uint8."
        )
    if preprocessing["value_domain"] != "uint8_0_255":
        raise ProbabilityAggregationError(
            "Decision feed rejects raw physical SAR/terrain values; "
            "preprocessing value_domain must be uint8_0_255."
        )
    _sha256(
        preprocessing["sidecar_sha256"],
        "model-run manifest preprocessing.sidecar_sha256",
    )
    transforms = _json_array(
        preprocessing["transforms"],
        "model-run manifest preprocessing.transforms",
        minimum=len(channel_names),
        maximum=len(channel_names),
    )
    transform_names: list[str] = []
    for index, raw_transform in enumerate(transforms):
        label = f"model-run manifest preprocessing.transforms[{index}]"
        transform = _require_exact_fields(raw_transform, TRANSFORM_FIELDS, label)
        transform_names.append(_nonempty_text(transform["name"], f"{label}.name"))
        physical_min = _finite_number(
            transform["physical_min"], f"{label}.physical_min"
        )
        physical_max = _finite_number(
            transform["physical_max"], f"{label}.physical_max"
        )
        if physical_min >= physical_max:
            raise ProbabilityAggregationError(
                f"{label} must have physical_min < physical_max."
            )
        _nonempty_text(transform["units"], f"{label}.units")
        _nonempty_text(transform["description"], f"{label}.description")
    if transform_names != channel_names:
        raise ProbabilityAggregationError(
            "Preprocessing transform names and order must match channel_names."
        )


def _validate_input_manifest(
    value: object,
    *,
    channel_names: list[str],
    source_time: datetime,
) -> dict[str, Mapping[str, object]]:
    rows = _json_array(value, "model-run manifest input_manifest_rows", minimum=1)
    rows_by_role: dict[str, Mapping[str, object]] = {}
    product_ids: set[str] = set()
    row_times: dict[str, datetime] = {}
    for index, raw_row in enumerate(rows):
        label = f"model-run manifest input_manifest_rows[{index}]"
        row = _require_exact_fields(raw_row, INPUT_MANIFEST_FIELDS, label)
        product_id = _nonempty_text(row["product_id"], f"{label}.product_id")
        role = _nonempty_text(row["role"], f"{label}.role")
        _sha256(row["sha256"], f"{label}.sha256")
        timestamp = _parsed_timestamp(
            row["source_timestamp"], f"{label}.source_timestamp"
        )
        if timestamp > source_time:
            raise ProbabilityAggregationError(
                f"{label}.source_timestamp cannot be later than the run source_timestamp."
            )
        if row["processing_allowed"] is not True:
            raise ProbabilityAggregationError(
                f"{label}.processing_allowed must be true; the input licensing "
                "or provenance gate remains blocked."
            )
        if role in rows_by_role:
            raise ProbabilityAggregationError(
                "Input manifest roles must be unique within a decision-feed run."
            )
        if product_id in product_ids:
            raise ProbabilityAggregationError(
                "Input manifest product IDs must be unique within a decision-feed run."
            )
        rows_by_role[role] = row
        row_times[role] = timestamp
        product_ids.add(product_id)

    required_roles = _required_input_roles(channel_names)
    missing_roles = sorted(required_roles - set(rows_by_role))
    if missing_roles:
        raise ProbabilityAggregationError(
            "Decision feed is missing required input receipt role(s): "
            + ", ".join(missing_roles)
        )
    if not row_times["pre_event_sar"] < row_times["post_event_sar"] <= source_time:
        raise ProbabilityAggregationError(
            "Input receipt timing must satisfy pre_event_sar < post_event_sar "
            "<= run source_timestamp."
        )
    return rows_by_role


def _required_input_roles(channel_names: list[str]) -> set[str]:
    required = {"pre_event_sar", "post_event_sar", "reference_mask"}
    sar_channels = {
        "pre_vv_db",
        "post_vv_db",
        "pre_vh_db",
        "post_vh_db",
        "vv_change_db",
        "vh_change_db",
    }
    for raw_name in channel_names:
        name = raw_name.casefold()
        if name in sar_channels:
            continue
        if "slope" in name:
            required.add("terrain_slope")
        elif "hand" in name:
            required.add("hand")
        elif "permanent_water" in name:
            required.add("permanent_water")
        else:
            raise ProbabilityAggregationError(
                f"No explicit input receipt role is defined for channel {raw_name!r}."
            )
    return required


def _validate_spatial_partitions(
    value: object,
    *,
    holdout_ids: list[str],
    run_bounds: tuple[float, float, float, float],
) -> None:
    partitions = _json_array(
        value,
        "model-run manifest spatial_partitions",
        minimum=2,
    )
    seen_ids: set[str] = set()
    partition_bounds: list[tuple[str, tuple[float, float, float, float]]] = []
    actual_holdouts: set[str] = set()
    has_train = False
    for index, raw_partition in enumerate(partitions):
        label = f"model-run manifest spatial_partitions[{index}]"
        partition = _require_exact_fields(
            raw_partition,
            SPATIAL_PARTITION_FIELDS,
            label,
        )
        group_id = _nonempty_text(
            partition["spatial_group_id"], f"{label}.spatial_group_id"
        )
        if group_id in seen_ids:
            raise ProbabilityAggregationError("Spatial partition IDs must be unique.")
        split = _nonempty_text(partition["split"], f"{label}.split")
        if split not in {"train", "holdout"}:
            raise ProbabilityAggregationError(
                f"{label}.split must be train or holdout."
            )
        current_bounds = _bounds(partition["bounds"], f"{label}.bounds")
        if not _bounds_within(current_bounds, run_bounds):
            raise ProbabilityAggregationError(
                f"{label}.bounds must lie within the model-run bounds."
            )
        if split == "holdout":
            actual_holdouts.add(group_id)
        else:
            has_train = True
        seen_ids.add(group_id)
        partition_bounds.append((group_id, current_bounds))
    if not has_train or actual_holdouts != set(holdout_ids):
        raise ProbabilityAggregationError(
            "Spatial partitions require train coverage and exact holdout-ID agreement."
        )
    for index, (first_id, first_bounds) in enumerate(partition_bounds):
        for second_id, second_bounds in partition_bounds[index + 1 :]:
            if _bounds_have_interior_overlap(first_bounds, second_bounds):
                raise ProbabilityAggregationError(
                    f"Spatial partitions {first_id!r} and {second_id!r} overlap."
                )


def _validate_probability_grid(
    value: object,
    *,
    target_crs: str,
    resolution: list[float],
    bounds: tuple[float, float, float, float],
    nodata: float,
) -> dict[str, Any]:
    grid = _require_exact_fields(
        value,
        PROBABILITY_GRID_FIELDS,
        "probability_raster_receipt.grid",
    )
    crs = _nonempty_text(grid["crs"], "probability_raster_receipt.grid.crs")
    if crs.casefold() != target_crs.casefold():
        raise ProbabilityAggregationError(
            "Probability raster CRS does not match the model-run grid."
        )
    grid_bounds = _bounds(grid["bounds"], "probability_raster_receipt.grid.bounds")
    if not _same_numbers(grid_bounds, bounds):
        raise ProbabilityAggregationError(
            "Probability raster bounds do not match the model-run grid."
        )
    width = _positive_int(grid["width"], "probability_raster_receipt.grid.width")
    height = _positive_int(grid["height"], "probability_raster_receipt.grid.height")
    left, bottom, right, top = bounds
    expected_width = (right - left) / resolution[0]
    expected_height = (top - bottom) / resolution[1]
    if (
        not _same_number(expected_width, round(expected_width))
        or not _same_number(expected_height, round(expected_height))
        or width != round(expected_width)
        or height != round(expected_height)
    ):
        raise ProbabilityAggregationError(
            "Probability raster dimensions do not match bounds and resolution."
        )
    transform = _number_array(
        grid["transform"],
        "probability_raster_receipt.grid.transform",
        length=9,
    )
    expected_transform = [
        resolution[0],
        0.0,
        left,
        0.0,
        -resolution[1],
        top,
        0.0,
        0.0,
        1.0,
    ]
    if not _same_numbers(transform, expected_transform):
        raise ProbabilityAggregationError(
            "Probability raster transform does not match the model-run grid."
        )
    if _positive_int(grid["count"], "probability_raster_receipt.grid.count") != 1:
        raise ProbabilityAggregationError(
            "Probability raster must contain exactly one class-1 probability band."
        )
    dtypes = _json_string_array(
        grid["dtypes"], "probability_raster_receipt.grid.dtypes", minimum=1
    )
    descriptions = _json_string_array(
        grid["descriptions"],
        "probability_raster_receipt.grid.descriptions",
        minimum=1,
    )
    if dtypes != ["float32"] or descriptions != ["flood_probability_0_1"]:
        raise ProbabilityAggregationError(
            "Probability raster must be one float32 band named flood_probability_0_1."
        )
    receipt_nodata = _finite_number(
        grid["nodata"], "probability_raster_receipt.grid.nodata"
    )
    if not _same_number(receipt_nodata, nodata):
        raise ProbabilityAggregationError(
            "Probability raster nodata does not match the aggregation request."
        )
    return {
        "crs": crs,
        "transform": transform,
        "width": width,
        "height": height,
        "bounds": list(grid_bounds),
        "count": 1,
        "dtypes": dtypes,
        "descriptions": descriptions,
        "nodata": receipt_nodata,
    }


def _validate_source_metadata(source: Mapping[str, object]) -> _SourceMetadata:
    if not isinstance(source, Mapping):
        raise ProbabilityAggregationError("source_metadata must be a mapping.")
    required = (
        "dataset_mode",
        "operational_status",
        "run_status",
        "source_name",
        "source_timestamp",
        "confidence_class",
        "assumptions",
        "processing_scope",
        "reference_mask_status",
        "processing_allowed",
        "can_feed_decision_layer",
        "reason_blocked",
        "validation_metrics",
    )
    missing = [field for field in required if field not in source]
    if missing:
        raise ProbabilityAggregationError(
            "source_metadata is missing required fields: " + ", ".join(missing)
        )

    dataset_mode = _nonempty_text(source["dataset_mode"], "dataset_mode")
    if dataset_mode not in DATASET_MODES:
        raise ProbabilityAggregationError(
            "dataset_mode must be fixture_demo, candidate, or official_input."
        )
    confidence = _nonempty_text(source["confidence_class"], "confidence_class")
    if confidence not in CONFIDENCE_CLASSES:
        raise ProbabilityAggregationError(
            "confidence_class must be low, medium, or high."
        )
    source_timestamp = _timestamp(source["source_timestamp"])
    operational_status = _nonempty_text(
        source["operational_status"], "operational_status"
    )
    if operational_status not in OPERATIONAL_STATUSES:
        raise ProbabilityAggregationError(
            "operational_status must be non_operational, planning_only, or "
            "agency_operational."
        )
    run_status = _nonempty_text(source["run_status"], "run_status")
    if run_status not in RUN_STATUSES:
        raise ProbabilityAggregationError(
            "run_status must be blocked, prepared, running, completed, or failed."
        )

    assumptions_value = source["assumptions"]
    if isinstance(assumptions_value, (str, bytes)) or not isinstance(
        assumptions_value, Sequence
    ):
        raise ProbabilityAggregationError(
            "assumptions must be a non-empty sequence of strings."
        )
    assumptions = tuple(
        _nonempty_text(value, f"assumptions[{index}]")
        for index, value in enumerate(assumptions_value)
    )
    if not assumptions:
        raise ProbabilityAggregationError("assumptions must not be empty.")

    processing_allowed = source["processing_allowed"]
    can_feed = source["can_feed_decision_layer"]
    if type(processing_allowed) is not bool:
        raise ProbabilityAggregationError("processing_allowed must be a boolean.")
    if type(can_feed) is not bool:
        raise ProbabilityAggregationError("can_feed_decision_layer must be a boolean.")
    if dataset_mode != "official_input" and can_feed:
        raise ProbabilityAggregationError(
            "fixture_demo and candidate sources must set can_feed_decision_layer=false."
        )
    if can_feed and not processing_allowed:
        raise ProbabilityAggregationError(
            "can_feed_decision_layer=true requires processing_allowed=true."
        )

    reference_mask_status = _nonempty_text(
        source["reference_mask_status"], "reference_mask_status"
    )
    metrics_value = source["validation_metrics"]
    if not isinstance(metrics_value, Mapping):
        raise ProbabilityAggregationError("validation_metrics must be a mapping.")
    missing_metrics = [name for name in VALIDATION_METRICS if name not in metrics_value]
    if missing_metrics:
        raise ProbabilityAggregationError(
            "validation_metrics is missing required fields: "
            + ", ".join(missing_metrics)
        )
    metrics: list[tuple[str, float | None]] = []
    for name in VALIDATION_METRICS:
        raw_metric = metrics_value[name]
        if raw_metric is None:
            metrics.append((name, None))
            continue
        metric = _numeric_value(raw_metric, f"validation_metrics.{name}")
        if not math.isfinite(metric) or metric < 0:
            raise ProbabilityAggregationError(
                f"validation_metrics.{name} must be finite and non-negative."
            )
        if name != "area_error_ratio" and metric > 1:
            raise ProbabilityAggregationError(
                f"validation_metrics.{name} must be between 0 and 1."
            )
        metrics.append((name, metric))

    reason_value = source["reason_blocked"]
    if not isinstance(reason_value, str):
        raise ProbabilityAggregationError("reason_blocked must be a string.")
    reason_blocked = reason_value.strip()
    if can_feed:
        blockers: list[str] = []
        if operational_status == "non_operational":
            blockers.append("operational_status=non_operational")
        if run_status != "completed":
            blockers.append(f"run_status={run_status}")
        if confidence == "low":
            blockers.append("confidence_class=low")
        if reference_mask_status != "confirmed_for_model_purpose":
            blockers.append(f"reference_mask_status={reference_mask_status}")
        if any(value is None for _, value in metrics):
            blockers.append("validation_metrics=incomplete")
        if reason_blocked:
            blockers.append("reason_blocked is non-empty")
        if blockers:
            raise ProbabilityAggregationError(
                "can_feed_decision_layer=true requires complete promotion evidence: "
                + "; ".join(blockers)
            )

    return _SourceMetadata(
        dataset_mode=dataset_mode,
        operational_status=operational_status,
        run_status=run_status,
        source_name=_nonempty_text(source["source_name"], "source_name"),
        source_timestamp=source_timestamp,
        confidence_class=confidence,
        assumptions=assumptions,
        processing_scope=_nonempty_text(
            source["processing_scope"],
            "processing_scope",
        ),
        reference_mask_status=reference_mask_status,
        processing_allowed=processing_allowed,
        can_feed_decision_layer=can_feed,
        reason_blocked=reason_blocked,
        validation_metrics=tuple(metrics),
    )


def _promotion_blockers(metadata: _SourceMetadata) -> list[str]:
    blockers: list[str] = []
    if metadata.dataset_mode != "official_input":
        blockers.append(f"dataset_mode={metadata.dataset_mode}")
    if metadata.operational_status == "non_operational":
        blockers.append("operational_status=non_operational")
    if metadata.run_status != "completed":
        blockers.append(f"run_status={metadata.run_status}")
    if metadata.confidence_class == "low":
        blockers.append("confidence_class=low")
    if metadata.reference_mask_status != "confirmed_for_model_purpose":
        blockers.append(f"reference_mask_status={metadata.reference_mask_status}")
    if not metadata.processing_allowed:
        blockers.append("processing_allowed=false")
    if not metadata.can_feed_decision_layer:
        blockers.append("can_feed_decision_layer=false")
    if any(value is None for _, value in metadata.validation_metrics):
        blockers.append("validation_metrics=incomplete")
    return blockers or ["promotion contract unresolved"]


def _require_exact_fields(
    value: object,
    expected: frozenset[str],
    field: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ProbabilityAggregationError(f"{field} must be a mapping.")
    actual = set(value)
    missing = sorted(expected - actual)
    unexpected = sorted((actual - expected), key=repr)
    problems: list[str] = []
    if missing:
        problems.append("missing required fields: " + ", ".join(missing))
    if unexpected:
        problems.append(
            "contains unsupported fields: "
            + ", ".join(repr(item) for item in unexpected)
        )
    if problems:
        raise ProbabilityAggregationError(
            f"{field} is not schema-complete: " + "; ".join(problems)
        )
    return value


def _json_array(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> list[object]:
    if not isinstance(value, list):
        raise ProbabilityAggregationError(f"{field} must be a JSON array.")
    if len(value) < minimum or (maximum is not None and len(value) > maximum):
        if maximum is None:
            expected = f"at least {minimum} item(s)"
        elif minimum == maximum:
            expected = f"exactly {minimum} item(s)"
        else:
            expected = f"between {minimum} and {maximum} item(s)"
        raise ProbabilityAggregationError(f"{field} must contain {expected}.")
    return value


def _json_string_array(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> list[str]:
    raw_items = _json_array(
        value,
        field,
        minimum=minimum,
        maximum=maximum,
    )
    return [
        _nonempty_text(item, f"{field}[{index}]")
        for index, item in enumerate(raw_items)
    ]


def _number_array(
    value: object,
    field: str,
    *,
    length: int,
    positive: bool = False,
) -> list[float]:
    raw_values = _json_array(value, field, minimum=length, maximum=length)
    values = [
        _finite_number(item, f"{field}[{index}]")
        for index, item in enumerate(raw_values)
    ]
    if positive and any(item <= 0 for item in values):
        raise ProbabilityAggregationError(f"{field} values must be positive.")
    return values


def _bounds(value: object, field: str) -> tuple[float, float, float, float]:
    left, bottom, right, top = _number_array(value, field, length=4)
    if not left < right or not bottom < top:
        raise ProbabilityAggregationError(
            f"{field} must be ordered left, bottom, right, top."
        )
    return left, bottom, right, top


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ProbabilityAggregationError(
            f"{field} must be a lowercase 64-character SHA-256."
        )
    return value


def _commit_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise ProbabilityAggregationError(
            f"{field} must be a lowercase 40-character Git commit."
        )
    return value


def _nullable_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _nonempty_text(value, field)


def _nullable_commit(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _commit_sha(value, field)


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise ProbabilityAggregationError(f"{field} must be a positive integer.")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ProbabilityAggregationError(f"{field} must be a non-negative integer.")
    return value


def _finite_number(value: object, field: str) -> float:
    number = _numeric_value(value, field)
    if not math.isfinite(number):
        raise ProbabilityAggregationError(f"{field} must be finite.")
    return number


def _parsed_timestamp(value: object, field: str) -> datetime:
    text = _nonempty_text(value, field)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ProbabilityAggregationError(
            f"{field} must be an RFC 3339 timestamp."
        ) from exc
    if "T" not in text or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProbabilityAggregationError(
            f"{field} must include a time and UTC offset or Z suffix."
        )
    return parsed


def _canonical_sha256(value: object, field: str) -> str:
    try:
        encoded = json.dumps(
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
    return hashlib.sha256(encoded).hexdigest()


def _same_number(first: float, second: float | int) -> bool:
    return math.isclose(first, float(second), rel_tol=0.0, abs_tol=1e-9)


def _same_numbers(
    first: Sequence[float],
    second: Sequence[float],
) -> bool:
    return len(first) == len(second) and all(
        _same_number(left, right) for left, right in zip(first, second, strict=True)
    )


def _bounds_within(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
) -> bool:
    return (
        inner[0] >= outer[0]
        and inner[1] >= outer[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )


def _bounds_have_interior_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return max(first[0], second[0]) < min(first[2], second[2]) and max(
        first[1], second[1]
    ) < min(first[3], second[3])


def _timestamp(value: object) -> str:
    text = _nonempty_text(value, "source_timestamp")
    _parsed_timestamp(text, "source_timestamp")
    return text


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProbabilityAggregationError(f"{field} must be a non-empty string.")
    return value.strip()


def _numeric_value(value: object, field: str) -> float:
    if isinstance(value, (bool, str, bytes)):
        raise ProbabilityAggregationError(f"{field} must be numeric.")
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProbabilityAggregationError(f"{field} must be numeric.") from exc


def _linear_quantile(ordered: Sequence[float], quantile: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] * (1.0 - fraction) + ordered[upper_index] * fraction
