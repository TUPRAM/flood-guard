"""Fail-closed model-registry binding for GeoAI v2 artifacts.

The registry is deliberately separate from model execution.  It verifies one
signed registry payload against the exact model-run, evaluation, and product
manifests supplied by the caller.  Candidate and shadow entries remain
report-only.  No frontend flag, environment variable, model score, or artifact
field can bypass the signed evidence chain.

This module uses only the Python standard library and does not import GeoAI,
PyTorch, rasterio, or the API service.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import math
from pathlib import PurePosixPath
import re
from typing import Literal


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
PRIVATE_PATH_RE = re.compile(
    r"(?:^[A-Za-z]:[\\/]|^\\\\|^/|file://|"
    r"(?:^|[\\/])\.\.(?:[\\/]|$)|/(?:Users|home|root|tmp|var|private)/)",
    re.IGNORECASE,
)

CORE_PRODUCT_ASSET_ROLES = frozenset(
    {
        "flood_probability",
        "validity_mask",
        "sensor_quality_mask",
        "model_uncertainty",
        "abstention_mask",
    }
)
REGISTRY_STATUSES = frozenset(
    {"candidate", "shadow", "approved", "revoked", "expired", "blocked"}
)
PERMITTED_USES = frozenset({"report_only", "shadow_only", "decision_input"})
EVIDENCE_KINDS = frozenset(
    {
        "satellite_observed_extent",
        "optical_corroboration",
        "susceptibility_forecast",
        "scenario_assumption",
        "external_algorithmic_baseline",
        "human_field_observation",
    }
)

REGISTRY_ENTRY_FIELDS = frozenset({"payload", "signature"})
REGISTRY_SIGNATURE_FIELDS = frozenset(
    {"algorithm", "key_id", "payload_sha256", "value"}
)
REGISTRY_PAYLOAD_FIELDS = frozenset(
    {
        "schema_version",
        "registry_entry_id",
        "study_area_id",
        "event_id",
        "evidence_kind",
        "source_bundle_sha256",
        "model_run_id",
        "model_id",
        "model_sha256",
        "model_run_manifest_sha256",
        "evaluation_id",
        "evaluation_manifest_sha256",
        "controlled_result_receipt_sha256",
        "product_id",
        "product_manifest_sha256",
        "promotion_acceptance_receipt_sha256",
        "field_validation_receipt_sha256",
        "agency_acceptance_receipt_sha256",
        "dataset_mode",
        "operational_status",
        "registry_status",
        "permitted_use",
        "issued_at",
        "valid_from",
        "expires_at",
        "official_warning",
        "can_feed_decision_layer",
        "reason_blocked",
    }
)
MODEL_RUN_V2_FIELDS = frozenset(
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
        "study_area_id",
        "event_id",
        "evidence_kind",
        "run_status",
        "model",
        "input_manifest_rows",
        "feature_contract",
        "target_contract",
        "training_lineage",
        "partition_contract",
        "inference_contract",
        "processing_allowed",
        "can_feed_decision_layer",
        "reason_blocked",
    }
)
MODEL_FIELDS = frozenset(
    {
        "model_id",
        "model_revision",
        "model_family",
        "backend",
        "architecture",
        "encoder",
        "encoder_weights",
        "framework",
        "framework_version",
        "framework_commit",
        "model_sha256",
    }
)
FEATURE_CONTRACT_FIELDS = frozenset(
    {
        "feature_schema_id",
        "value_domain",
        "dtype",
        "channel_count",
        "channel_names",
        "preprocessing_sidecar_sha256",
        "feature_stack_sha256",
    }
)
TARGET_CONTRACT_FIELDS = frozenset(
    {
        "task",
        "class_schema_id",
        "classes",
        "positive_class_index",
        "ignore_index",
        "reference_mask_status",
        "label_release_sha256",
    }
)
TRAINING_LINEAGE_FIELDS = frozenset(
    {
        "input_manifest_sha256",
        "training_dataset_manifest_sha256",
        "label_release_sha256",
        "prepared_tile_manifest_sha256",
        "controlled_model_run_receipt_sha256",
        "threshold_selection_receipt_sha256",
        "calibration_receipt_sha256",
    }
)
PARTITION_CONTRACT_FIELDS = frozenset(
    {
        "partition_manifest_sha256",
        "training_partition_sha256",
        "calibration_partition_sha256",
        "final_holdout_partition_sha256",
        "train_ids",
        "calibration_ids",
        "final_holdout_ids",
    }
)
INFERENCE_CONTRACT_FIELDS = frozenset(
    {
        "target_crs",
        "resolution",
        "bounds",
        "tile_size",
        "overlap",
        "stride",
        "batch_size",
        "device",
        "probability_threshold",
    }
)
INPUT_ROW_FIELDS = frozenset(
    {
        "role",
        "modality",
        "product_id",
        "sha256",
        "source_timestamp",
        "processing_allowed",
    }
)
MODEL_EVALUATION_V2_FIELDS = frozenset(
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
        "evaluation_id",
        "experiment_id",
        "study_area_id",
        "event_ids",
        "model_run_id",
        "model_id",
        "model_sha256",
        "model_run_manifest_sha256",
        "controlled_result_receipt_sha256",
        "evaluation_status",
        "evaluation_scope",
        "reference_evidence",
        "partition_evidence",
        "threshold_evidence",
        "overall_metrics",
        "event_metrics",
        "error_strata",
        "calibration",
        "selective_prediction",
        "ood_evaluation",
        "downstream_impact",
        "runtime",
        "processing_allowed",
        "can_feed_decision_layer",
        "reason_blocked",
    }
)
FLOOD_PRODUCT_V2_FIELDS = frozenset(
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
        "product_id",
        "run_id",
        "study_area_id",
        "event_id",
        "evidence_kind",
        "source_manifest_sha256",
        "model_run_manifest_sha256",
        "model_sha256",
        "evaluation_manifest_sha256",
        "grid",
        "assets",
        "valid_coverage_fraction",
        "abstained_fraction",
        "sensor_quality_status",
        "ood_status",
        "review_required_reasons",
        "unknown_cell_policy",
        "counts_as_observed_evidence",
        "processing_allowed",
        "can_feed_decision_layer",
        "reason_blocked",
    }
)
PRODUCT_GRID_FIELDS = frozenset(
    {
        "crs",
        "resolution",
        "bounds",
        "width",
        "height",
        "transform",
        "nodata",
        "grid_sha256",
    }
)
PRODUCT_ASSET_FIELDS = frozenset(
    {
        "role",
        "relative_path",
        "media_type",
        "sha256",
        "dtype",
        "band_name",
        "nodata",
        "minimum",
        "maximum",
    }
)


class ModelRegistryError(ValueError):
    """Raised when registry evidence is malformed, expired, or substituted."""


@dataclass(frozen=True, slots=True)
class RegistryResolution:
    """Immutable result of resolving a signed registry entry."""

    registry_entry_id: str
    study_area_id: str
    event_id: str
    model_run_id: str
    evaluation_id: str
    product_id: str
    registry_status: str
    permitted_use: Literal["report_only", "shadow_only", "decision_input"]
    can_feed_decision_layer: bool
    effective_use: Literal["report_only", "shadow_only", "decision_input"]
    reason_blocked: str


def canonical_sha256(value: Mapping[str, object]) -> str:
    """Return a deterministic SHA-256 for one JSON-compatible mapping."""

    return hashlib.sha256(_canonical_json_bytes(value, "manifest")).hexdigest()


def sign_registry_payload(
    payload: Mapping[str, object],
    *,
    key_id: str,
    signing_key: bytes,
) -> dict[str, object]:
    """Create a deterministic HMAC envelope for a registry payload.

    This helper is suitable for controlled tooling and deterministic tests.  It
    does not write files or derive decision eligibility.
    """

    normalized = _mapping(payload, "registry payload")
    _require_exact_fields(normalized, REGISTRY_PAYLOAD_FIELDS, "registry payload")
    _validate_registry_payload(normalized)
    identity = _safe_id(key_id, "registry signature key_id")
    key = _signing_key(signing_key)
    encoded = _canonical_json_bytes(normalized, "registry payload")
    digest = hashlib.sha256(encoded).hexdigest()
    return {
        "payload": dict(normalized),
        "signature": {
            "algorithm": "HMAC-SHA256",
            "key_id": identity,
            "payload_sha256": digest,
            "value": hmac.new(key, encoded, hashlib.sha256).hexdigest(),
        },
    }


def validate_observation_product(product: Mapping[str, object]) -> None:
    """Validate product structure and preserve unknown/abstained-cell semantics."""

    value = _mapping(product, "flood observation product")
    _require_exact_fields(value, FLOOD_PRODUCT_V2_FIELDS, "flood observation product")
    if value["schema_version"] != "2.0":
        raise ModelRegistryError("Flood observation product schema_version must be 2.0.")
    _require_false(value["official_warning"], "product official_warning")
    _require_false(
        value["can_feed_decision_layer"],
        "product can_feed_decision_layer",
    )
    _validate_common_identity(value, label="product")
    _safe_id(value["product_id"], "product_id")
    _safe_id(value["run_id"], "product run_id")
    _safe_id(value["study_area_id"], "product study_area_id")
    _safe_id(value["event_id"], "product event_id")
    _evidence_kind(value["evidence_kind"], "product evidence_kind")
    for field in (
        "source_manifest_sha256",
        "model_run_manifest_sha256",
        "model_sha256",
        "evaluation_manifest_sha256",
    ):
        _sha256(value[field], f"product {field}")

    if value["unknown_cell_policy"] != (
        "preserve_nodata_and_abstention_never_fill_as_dry"
    ):
        raise ModelRegistryError(
            "Product must preserve nodata and abstention rather than fill unknown cells as dry."
        )
    valid_coverage = _unit_interval(
        value["valid_coverage_fraction"], "product valid_coverage_fraction"
    )
    abstained = _unit_interval(
        value["abstained_fraction"], "product abstained_fraction"
    )
    _strict_bool(
        value["counts_as_observed_evidence"],
        "product counts_as_observed_evidence",
    )
    processing_allowed = _strict_bool(
        value["processing_allowed"], "product processing_allowed"
    )
    if value["dataset_mode"] in {"fixture_demo", "candidate"} and (
        value["counts_as_observed_evidence"] is not False
        or value["operational_status"] != "non_operational"
    ):
        raise ModelRegistryError(
            "Fixture and candidate products are non-operational and cannot count as observed evidence."
        )
    if (
        value["sensor_quality_status"] == "failed"
        or value["ood_status"] == "out_of_distribution"
        or valid_coverage == 0.0
        or not processing_allowed
    ) and value["counts_as_observed_evidence"] is not False:
        raise ModelRegistryError(
            "Failed, OOD, uncovered, or processing-blocked products cannot count as observed evidence."
        )
    if abstained > 0 and not _string_array(
        value["review_required_reasons"],
        "product review_required_reasons",
        minimum=1,
    ):
        raise ModelRegistryError("Abstained products require a review reason.")
    _nonempty_text(value["reason_blocked"], "product reason_blocked")

    grid = _mapping(value["grid"], "product grid")
    _require_exact_fields(grid, PRODUCT_GRID_FIELDS, "product grid")
    nodata = _finite_number(grid["nodata"], "product grid nodata")
    if 0.0 <= nodata <= 1.0:
        raise ModelRegistryError(
            "Product probability nodata must remain outside the [0,1] range."
        )
    _sha256(grid["grid_sha256"], "product grid_sha256")
    _positive_pair(grid["resolution"], "product grid resolution")
    _ordered_bounds(grid["bounds"], "product grid bounds")
    _number_array(grid["transform"], "product grid transform", length=6)
    _positive_int(grid["width"], "product grid width")
    _positive_int(grid["height"], "product grid height")

    raw_assets = _sequence(value["assets"], "product assets")
    assets: dict[str, Mapping[str, object]] = {}
    for index, raw in enumerate(raw_assets):
        asset = _mapping(raw, f"product assets[{index}]")
        _require_exact_fields(asset, PRODUCT_ASSET_FIELDS, f"product assets[{index}]")
        role = _nonempty_text(asset["role"], f"product assets[{index}].role")
        if role in assets:
            raise ModelRegistryError(f"Product asset role {role!r} is duplicated.")
        relative_path = _nonempty_text(
            asset["relative_path"], f"product assets[{index}].relative_path"
        )
        if PRIVATE_PATH_RE.search(relative_path) or PurePosixPath(relative_path).is_absolute():
            raise ModelRegistryError("Product asset paths must be safe relative paths.")
        _sha256(asset["sha256"], f"product assets[{index}].sha256")
        assets[role] = asset
    missing_roles = sorted(CORE_PRODUCT_ASSET_ROLES - set(assets))
    if missing_roles:
        raise ModelRegistryError(
            "Product is missing required validity/uncertainty assets: "
            + ", ".join(missing_roles)
        )

    probability = assets["flood_probability"]
    if (
        probability["dtype"] != "float32"
        or probability["band_name"] != "flood_probability_0_1"
        or _finite_number(probability["nodata"], "probability nodata") != nodata
        or _finite_number(probability["minimum"], "probability minimum") != 0.0
        or _finite_number(probability["maximum"], "probability maximum") != 1.0
    ):
        raise ModelRegistryError(
            "Flood probability must be float32 [0,1] with the declared external nodata."
        )
    uncertainty = assets["model_uncertainty"]
    if (
        uncertainty["dtype"] != "float32"
        or _finite_number(uncertainty["nodata"], "uncertainty nodata") != nodata
        or _finite_number(uncertainty["minimum"], "uncertainty minimum") != 0.0
        or _finite_number(uncertainty["maximum"], "uncertainty maximum") != 1.0
    ):
        raise ModelRegistryError(
            "Model uncertainty must preserve float32 [0,1] values and external nodata."
        )
    for role in ("validity_mask", "sensor_quality_mask", "abstention_mask"):
        mask = assets[role]
        if mask["dtype"] != "uint8" or mask["nodata"] != 255:
            raise ModelRegistryError(
                f"{role} must be uint8 with nodata=255 so unknown is not class zero."
            )


def validate_model_evaluation(evaluation: Mapping[str, object]) -> None:
    """Validate a Model Evaluation v2 document against the core safety gates."""

    _validate_evaluation(evaluation)


def resolve_model_registry_entry(
    entry: Mapping[str, object],
    *,
    model_run: Mapping[str, object],
    evaluation: Mapping[str, object],
    product: Mapping[str, object],
    source_bundle_sha256: str,
    known_study_area_ids: Collection[str],
    signing_keys: Mapping[str, bytes],
    evaluated_at: datetime,
) -> RegistryResolution:
    """Verify and resolve one signed registry association.

    The return value is report-only for candidate entries even when all
    candidate artifacts are internally consistent.  This v1 resolver never
    authorizes decision input from self-asserted receipt digests: the actual
    promotion, field-validation, and agency-acceptance receipt documents must
    be supplied and signature-verified by a future authority integration.
    """

    registry = _mapping(entry, "model registry entry")
    _require_exact_fields(registry, REGISTRY_ENTRY_FIELDS, "model registry entry")
    payload = _mapping(registry["payload"], "registry payload")
    signature = _mapping(registry["signature"], "registry signature")
    _require_exact_fields(payload, REGISTRY_PAYLOAD_FIELDS, "registry payload")
    _require_exact_fields(signature, REGISTRY_SIGNATURE_FIELDS, "registry signature")
    _verify_registry_signature(payload, signature, signing_keys)
    times = _validate_registry_payload(payload)

    as_of = _aware_datetime(evaluated_at, "evaluated_at")
    if as_of < times["valid_from"]:
        raise ModelRegistryError("Registry entry is not valid yet.")
    if as_of >= times["expires_at"]:
        raise ModelRegistryError("Registry entry has expired.")
    study_area = _safe_id(payload["study_area_id"], "registry study_area_id")
    known = {_safe_id(value, "known study area ID") for value in known_study_area_ids}
    if study_area not in known:
        raise ModelRegistryError(f"Unknown registry study area: {study_area}")
    if _sha256(source_bundle_sha256, "source_bundle_sha256") != payload[
        "source_bundle_sha256"
    ]:
        raise ModelRegistryError("Source bundle checksum was substituted.")

    run = _validate_model_run(model_run)
    evaluation_value = _validate_evaluation(evaluation)
    validate_observation_product(product)
    product_value = _mapping(product, "flood observation product")

    run_sha = canonical_sha256(run)
    evaluation_sha = canonical_sha256(evaluation_value)
    product_sha = canonical_sha256(product_value)
    expected_hashes = {
        "model_run_manifest_sha256": run_sha,
        "evaluation_manifest_sha256": evaluation_sha,
        "product_manifest_sha256": product_sha,
    }
    for field, expected in expected_hashes.items():
        if not hmac.compare_digest(_sha256(payload[field], field), expected):
            raise ModelRegistryError(f"Registry {field} does not match the exact artifact.")

    run_model = _mapping(run["model"], "model run model")
    identity_checks = (
        ("study_area_id", payload["study_area_id"], run["study_area_id"]),
        ("event_id", payload["event_id"], run["event_id"]),
        ("evidence_kind", payload["evidence_kind"], run["evidence_kind"]),
        ("model_run_id", payload["model_run_id"], run["run_id"]),
        ("model_id", payload["model_id"], run_model["model_id"]),
        ("model_sha256", payload["model_sha256"], run_model["model_sha256"]),
        ("evaluation_id", payload["evaluation_id"], evaluation_value["evaluation_id"]),
        ("product_id", payload["product_id"], product_value["product_id"]),
    )
    for label, registered, actual in identity_checks:
        if registered != actual:
            raise ModelRegistryError(f"Registry {label} does not match its bound artifact.")

    status = str(payload["registry_status"])
    permitted_use = str(payload["permitted_use"])
    declared_feed = _strict_bool(
        payload["can_feed_decision_layer"],
        "registry can_feed_decision_layer",
    )
    if declared_feed:
        _validate_decision_artifact_state(
            payload=payload,
            run=run,
            evaluation=evaluation_value,
            product=product_value,
        )

    _require_cross_document_binding(
        payload=payload,
        run=run,
        run_sha=run_sha,
        evaluation=evaluation_value,
        evaluation_sha=evaluation_sha,
        product=product_value,
    )

    if status == "approved" and declared_feed:
        raise ModelRegistryError(
            "Decision-input resolution requires the actual signed promotion, "
            "field-validation, and agency-acceptance receipts; digest strings "
            "alone cannot authorize decision use."
        )
    if status == "shadow":
        effective_use: Literal["report_only", "shadow_only", "decision_input"] = (
            "shadow_only"
        )
        resolved_feed = False
        reason = _nonempty_text(payload["reason_blocked"], "registry reason_blocked")
    else:
        effective_use = "report_only"
        resolved_feed = False
        reason = _nonempty_text(payload["reason_blocked"], "registry reason_blocked")
    if permitted_use != effective_use:
        raise ModelRegistryError("Registry permitted_use is inconsistent with its status.")

    return RegistryResolution(
        registry_entry_id=str(payload["registry_entry_id"]),
        study_area_id=study_area,
        event_id=str(payload["event_id"]),
        model_run_id=str(payload["model_run_id"]),
        evaluation_id=str(payload["evaluation_id"]),
        product_id=str(payload["product_id"]),
        registry_status=status,
        permitted_use=effective_use,
        can_feed_decision_layer=resolved_feed,
        effective_use=effective_use,
        reason_blocked=reason,
    )


def _validate_model_run(value: Mapping[str, object]) -> Mapping[str, object]:
    run = _mapping(value, "model run v2")
    _require_exact_fields(run, MODEL_RUN_V2_FIELDS, "model run v2")
    if run["schema_version"] != "2.0":
        raise ModelRegistryError("Model run schema_version must be 2.0.")
    _require_false(run["official_warning"], "model run official_warning")
    _require_false(
        run["can_feed_decision_layer"], "model run can_feed_decision_layer"
    )
    _validate_common_identity(run, label="model run")
    _safe_id(run["run_id"], "model run_id")
    _safe_id(run["study_area_id"], "model study_area_id")
    _safe_id(run["event_id"], "model event_id")
    _evidence_kind(run["evidence_kind"], "model evidence_kind")
    _strict_bool(run["processing_allowed"], "model run processing_allowed")
    _nonempty_text(run["reason_blocked"], "model reason_blocked")

    model = _mapping(run["model"], "model run model")
    _require_exact_fields(model, MODEL_FIELDS, "model run model")
    if run["run_status"] == "completed":
        _safe_id(model["model_id"], "model model_id")
        _nonempty_text(model["model_revision"], "model revision")
        _nonempty_text(model["architecture"], "model architecture")
        _nonempty_text(model["framework"], "model framework")
        _nonempty_text(model["framework_version"], "model framework_version")
        _sha256(model["model_sha256"], "model SHA-256")

    inputs = _sequence(run["input_manifest_rows"], "model input_manifest_rows")
    roles: list[str] = []
    product_ids: list[str] = []
    input_times: dict[str, datetime] = {}
    for index, raw in enumerate(inputs):
        row = _mapping(raw, f"input_manifest_rows[{index}]")
        _require_exact_fields(row, INPUT_ROW_FIELDS, f"input_manifest_rows[{index}]")
        role = _safe_id(row["role"], f"input_manifest_rows[{index}].role")
        roles.append(role)
        product_ids.append(
            _safe_id(row["product_id"], f"input_manifest_rows[{index}].product_id")
        )
        _sha256(row["sha256"], f"input_manifest_rows[{index}].sha256")
        input_times[role] = _timestamp(
            row["source_timestamp"], f"input_manifest_rows[{index}].source_timestamp"
        )
        allowed = _strict_bool(
            row["processing_allowed"], f"input_manifest_rows[{index}].processing_allowed"
        )
        if run["processing_allowed"] is True and not allowed:
            raise ModelRegistryError("Processing cannot override a blocked input row.")
    if len(roles) != len(set(roles)) or len(product_ids) != len(set(product_ids)):
        raise ModelRegistryError("Model input roles and product IDs must be unique.")
    if run["evidence_kind"] == "satellite_observed_extent":
        missing = {"pre_event_sar", "post_event_sar", "reference_mask"} - set(roles)
        if missing:
            raise ModelRegistryError(
                "Satellite observation run is missing source role(s): "
                + ", ".join(sorted(missing))
            )
        if not input_times["pre_event_sar"] < input_times["post_event_sar"]:
            raise ModelRegistryError("Pre-event SAR must precede post-event SAR.")

    feature = _mapping(run["feature_contract"], "feature contract")
    _require_exact_fields(feature, FEATURE_CONTRACT_FIELDS, "feature contract")
    names = _string_array(feature["channel_names"], "feature channel_names", minimum=1)
    if len(names) != len(set(names)) or _positive_int(
        feature["channel_count"], "feature channel_count"
    ) != len(names):
        raise ModelRegistryError("Feature channel count and unique ordered names differ.")
    _sha256(feature["preprocessing_sidecar_sha256"], "preprocessing sidecar SHA-256")
    _sha256(feature["feature_stack_sha256"], "feature stack SHA-256")

    target = _mapping(run["target_contract"], "target contract")
    _require_exact_fields(target, TARGET_CONTRACT_FIELDS, "target contract")
    if (
        target["task"] != "semantic_segmentation"
        or target["positive_class_index"] != 1
        or type(target["positive_class_index"]) is not int
        or target["ignore_index"] != 255
        or type(target["ignore_index"]) is not int
    ):
        raise ModelRegistryError("Flood target must preserve class 1 and ignore index 255.")
    classes = _sequence(target["classes"], "target classes")
    by_index: dict[int, Mapping[str, object]] = {}
    for index, raw in enumerate(classes):
        item = _mapping(raw, f"target classes[{index}]")
        _require_exact_fields(
            item,
            frozenset({"index", "name", "training_role"}),
            f"target classes[{index}]",
        )
        class_index = _nonnegative_int(item["index"], f"target classes[{index}].index")
        if class_index in by_index:
            raise ModelRegistryError("Target class indexes must be unique.")
        by_index[class_index] = item
    positive = by_index.get(1)
    ignored = by_index.get(255)
    if (
        positive is None
        or positive["name"] != "temporary_flood"
        or positive["training_role"] != "positive"
        or ignored is None
        or ignored["training_role"] != "ignore"
    ):
        raise ModelRegistryError(
            "Target classes must preserve temporary_flood=1 and ignored/unreviewed=255."
        )
    for unsafe_negative in (3, 4):
        if unsafe_negative in by_index and by_index[unsafe_negative]["training_role"] != "ignore":
            raise ModelRegistryError(
                "Uncertain or unobservable labels cannot be negative training truth."
            )

    lineage = _mapping(run["training_lineage"], "training lineage")
    _require_exact_fields(lineage, TRAINING_LINEAGE_FIELDS, "training lineage")
    _sha256(lineage["input_manifest_sha256"], "input manifest SHA-256")
    for field in TRAINING_LINEAGE_FIELDS - {"input_manifest_sha256"}:
        _nullable_sha256(lineage[field], f"training lineage {field}")
    if (
        target["label_release_sha256"] is not None
        and lineage["label_release_sha256"] != target["label_release_sha256"]
    ):
        raise ModelRegistryError("Target and training label-release hashes differ.")

    partitions = _mapping(run["partition_contract"], "partition contract")
    _require_exact_fields(partitions, PARTITION_CONTRACT_FIELDS, "partition contract")
    partition_ids: dict[str, set[str]] = {}
    for field in ("train_ids", "calibration_ids", "final_holdout_ids"):
        ids = set(_string_array(partitions[field], f"partition {field}"))
        if len(ids) != len(_sequence(partitions[field], f"partition {field}")):
            raise ModelRegistryError(f"Partition {field} contains duplicate IDs.")
        partition_ids[field] = ids
    if any(
        first.intersection(second)
        for index, first in enumerate(partition_ids.values())
        for second in list(partition_ids.values())[index + 1 :]
    ):
        raise ModelRegistryError("Train, calibration, and final holdout IDs must be disjoint.")
    if run["run_status"] == "completed":
        for field in (
            "training_dataset_manifest_sha256",
            "prepared_tile_manifest_sha256",
        ):
            _sha256(lineage[field], f"completed run {field}")
        for field in (
            "partition_manifest_sha256",
            "training_partition_sha256",
            "calibration_partition_sha256",
            "final_holdout_partition_sha256",
        ):
            _sha256(partitions[field], f"completed run {field}")
        if any(not ids for ids in partition_ids.values()):
            raise ModelRegistryError(
                "Completed runs require train, calibration, and final holdout partitions."
            )

    inference = _mapping(run["inference_contract"], "inference contract")
    _require_exact_fields(inference, INFERENCE_CONTRACT_FIELDS, "inference contract")
    tile_size = _positive_int(inference["tile_size"], "inference tile_size")
    overlap = _nonnegative_int(inference["overlap"], "inference overlap")
    stride = _positive_int(inference["stride"], "inference stride")
    if overlap >= tile_size or stride != tile_size - overlap:
        raise ModelRegistryError(
            "Inference requires overlap < tile_size and stride = tile_size - overlap."
        )
    threshold = _finite_number(
        inference["probability_threshold"], "inference probability_threshold"
    )
    if not 0 < threshold < 1:
        raise ModelRegistryError("Inference probability threshold must be inside (0,1).")
    _positive_pair(inference["resolution"], "inference resolution")
    _ordered_bounds(inference["bounds"], "inference bounds")
    return run


def _validate_evaluation(value: Mapping[str, object]) -> Mapping[str, object]:
    evaluation = _mapping(value, "model evaluation v2")
    _require_exact_fields(
        evaluation, MODEL_EVALUATION_V2_FIELDS, "model evaluation v2"
    )
    if evaluation["schema_version"] != "2.0":
        raise ModelRegistryError("Model evaluation schema_version must be 2.0.")
    _require_false(evaluation["official_warning"], "evaluation official_warning")
    _require_false(
        evaluation["can_feed_decision_layer"],
        "evaluation can_feed_decision_layer",
    )
    _validate_common_identity(evaluation, label="evaluation")
    _safe_id(evaluation["evaluation_id"], "evaluation_id")
    _safe_id(evaluation["model_run_id"], "evaluation model_run_id")
    _safe_id(evaluation["model_id"], "evaluation model_id")
    _sha256(evaluation["model_sha256"], "evaluation model_sha256")
    _sha256(
        evaluation["model_run_manifest_sha256"],
        "evaluation model_run_manifest_sha256",
    )
    _nullable_sha256(
        evaluation["controlled_result_receipt_sha256"],
        "evaluation controlled_result_receipt_sha256",
    )
    _strict_bool(
        evaluation["processing_allowed"],
        "evaluation processing_allowed",
    )
    events = _string_array(evaluation["event_ids"], "evaluation event_ids", minimum=1)
    if len(events) != len(set(events)):
        raise ModelRegistryError("Evaluation event IDs must be unique.")
    threshold = _mapping(evaluation["threshold_evidence"], "threshold evidence")
    if threshold.get("final_holdout_evaluated_during_selection") is not False:
        raise ModelRegistryError(
            "Final holdout cannot be evaluated during threshold selection."
        )
    if evaluation["evaluation_status"] == "completed_report_only":
        reference = _mapping(
            evaluation["reference_evidence"], "evaluation reference evidence"
        )
        partitions = _mapping(
            evaluation["partition_evidence"], "evaluation partition evidence"
        )
        calibration = _mapping(evaluation["calibration"], "evaluation calibration")
        selective = _mapping(
            evaluation["selective_prediction"],
            "evaluation selective prediction",
        )
        ood = _mapping(evaluation["ood_evaluation"], "evaluation OOD evidence")
        downstream = _mapping(
            evaluation["downstream_impact"], "evaluation downstream impact"
        )
        required_hashes = (
            (
                evaluation["controlled_result_receipt_sha256"],
                "controlled result receipt",
            ),
            (reference.get("reference_mask_sha256"), "reference mask"),
            (reference.get("label_release_sha256"), "label release"),
            (
                reference.get("reviewer_qualification_receipt_sha256"),
                "reviewer qualification receipt",
            ),
            (partitions.get("partition_manifest_sha256"), "partition manifest"),
            (partitions.get("training_partition_sha256"), "training partition"),
            (
                partitions.get("calibration_partition_sha256"),
                "calibration partition",
            ),
            (
                partitions.get("final_holdout_partition_sha256"),
                "final holdout partition",
            ),
            (
                threshold.get("threshold_selection_receipt_sha256"),
                "threshold-selection receipt",
            ),
            (
                calibration.get("reliability_asset_sha256"),
                "calibration reliability asset",
            ),
            (
                selective.get("risk_coverage_asset_sha256"),
                "selective-prediction risk/coverage asset",
            ),
            (ood.get("score_asset_sha256"), "OOD score asset"),
            (downstream.get("artifact_sha256"), "downstream-impact artifact"),
        )
        for digest, label in required_hashes:
            _sha256(digest, f"completed evaluation {label}")
        downstream_metrics = (
            "population_absolute_error",
            "critical_road_false_negative_count",
            "access_classification_flip_count",
            "equity_gap_absolute_error",
            "fpps_mean_absolute_error",
            "fpps_rank_correlation",
            "action_class_flip_count",
        )
        for field in downstream_metrics:
            _finite_number(
                downstream.get(field),
                f"completed evaluation downstream_impact.{field}",
            )
        overall_metrics = _mapping(
            evaluation["overall_metrics"], "evaluation overall metrics"
        )
        for field, metric in overall_metrics.items():
            _finite_number(metric, f"completed evaluation overall_metrics.{field}")
        if (
            evaluation["evaluation_scope"] != "final_holdout"
            or evaluation["controlled_result_receipt_sha256"] is None
            or threshold.get("selection_scope")
            != "verified_calibration_projection_only"
            or threshold.get("threshold") is None
            or calibration.get("status") != "evaluated"
            or not calibration.get("method")
            or selective.get("status") != "evaluated"
            or ood.get("status") != "passed"
            or not ood.get("method")
            or ood.get("threshold") is None
            or downstream.get("status") != "evaluated"
            or not _sequence(
                evaluation["event_metrics"], "evaluation event metrics"
            )
            or not _sequence(
                evaluation["error_strata"], "evaluation error strata"
            )
        ):
            raise ModelRegistryError(
                "Completed evaluation requires signed final-holdout, calibration, "
                "selective-prediction, OOD, and downstream-impact evidence."
            )
    _nonempty_text(evaluation["reason_blocked"], "evaluation reason_blocked")
    return evaluation


def _validate_decision_artifact_state(
    *,
    payload: Mapping[str, object],
    run: Mapping[str, object],
    evaluation: Mapping[str, object],
    product: Mapping[str, object],
) -> None:
    """Reject attempts to elevate candidate, blocked, or unqualified artifacts."""

    artifacts = {
        "model run": run,
        "evaluation": evaluation,
        "observation product": product,
    }
    for label, artifact in artifacts.items():
        if artifact["dataset_mode"] != "official_input":
            raise ModelRegistryError(
                f"Decision use requires {label} dataset_mode=official_input."
            )
        if artifact["operational_status"] != payload["operational_status"]:
            raise ModelRegistryError(
                f"Decision use requires {label} operational_status to match the registry."
            )
        if _strict_bool(
            artifact["processing_allowed"],
            f"{label} processing_allowed",
        ) is not True:
            raise ModelRegistryError(
                f"Decision use requires {label} processing_allowed=true."
            )

    if run["run_status"] != "completed":
        raise ModelRegistryError("Decision use requires a completed model run.")
    if (
        evaluation["evaluation_status"] != "completed_report_only"
        or evaluation["evaluation_scope"] != "final_holdout"
    ):
        raise ModelRegistryError(
            "Decision use requires a completed report-only final-holdout evaluation."
        )
    if product["counts_as_observed_evidence"] is not True:
        raise ModelRegistryError(
            "Decision use requires a product qualified as observed evidence."
        )
    if product["sensor_quality_status"] != "passed":
        raise ModelRegistryError(
            "Decision use requires a passed sensor-quality assessment."
        )
    if product["ood_status"] != "in_domain":
        raise ModelRegistryError(
            "Decision use requires an in-domain product assessment."
        )
    if _unit_interval(
        product["valid_coverage_fraction"],
        "product valid_coverage_fraction",
    ) == 0.0:
        raise ModelRegistryError(
            "Decision use requires non-zero valid observation coverage."
        )


def _require_cross_document_binding(
    *,
    payload: Mapping[str, object],
    run: Mapping[str, object],
    run_sha: str,
    evaluation: Mapping[str, object],
    evaluation_sha: str,
    product: Mapping[str, object],
) -> None:
    if (
        evaluation["study_area_id"] != run["study_area_id"]
        or run["event_id"] not in evaluation["event_ids"]
        or evaluation["model_run_id"] != run["run_id"]
        or evaluation["model_run_manifest_sha256"] != run_sha
    ):
        raise ModelRegistryError("Evaluation does not bind the exact model run and event.")
    model = _mapping(run["model"], "model run model")
    if (
        evaluation["model_id"] != model["model_id"]
        or evaluation["model_sha256"] != model["model_sha256"]
    ):
        raise ModelRegistryError("Evaluation model identity or checksum was substituted.")
    if (
        product["study_area_id"] != run["study_area_id"]
        or product["event_id"] != run["event_id"]
        or product["evidence_kind"] != run["evidence_kind"]
        or product["run_id"] != run["run_id"]
        or product["model_run_manifest_sha256"] != run_sha
        or product["model_sha256"] != model["model_sha256"]
        or product["evaluation_manifest_sha256"] != evaluation_sha
        or product["source_manifest_sha256"] != payload["source_bundle_sha256"]
    ):
        raise ModelRegistryError(
            "Observation product lineage does not match source, run, evaluation, and model."
        )
    controlled = evaluation["controlled_result_receipt_sha256"]
    if payload["controlled_result_receipt_sha256"] != controlled:
        raise ModelRegistryError(
            "Registry controlled-result receipt does not match the evaluation."
        )


def _verify_registry_signature(
    payload: Mapping[str, object],
    signature: Mapping[str, object],
    signing_keys: Mapping[str, bytes],
) -> None:
    if signature["algorithm"] != "HMAC-SHA256":
        raise ModelRegistryError("Registry signature algorithm must be HMAC-SHA256.")
    key_id = _safe_id(signature["key_id"], "registry signature key_id")
    key = signing_keys.get(key_id)
    if key is None:
        raise ModelRegistryError("Registry signature key is not trusted.")
    secret = _signing_key(key)
    encoded = _canonical_json_bytes(payload, "registry payload")
    expected_payload_hash = hashlib.sha256(encoded).hexdigest()
    payload_hash = _sha256(signature["payload_sha256"], "registry payload_sha256")
    if not hmac.compare_digest(payload_hash, expected_payload_hash):
        raise ModelRegistryError("Registry payload hash does not match its exact payload.")
    supplied = _sha256(signature["value"], "registry signature value")
    expected = hmac.new(secret, encoded, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise ModelRegistryError("Registry signature verification failed.")


def _validate_registry_payload(
    payload: Mapping[str, object],
) -> dict[str, datetime]:
    if payload["schema_version"] != "1.0":
        raise ModelRegistryError("Registry schema_version must be 1.0.")
    for field in (
        "registry_entry_id",
        "study_area_id",
        "event_id",
        "model_run_id",
        "model_id",
        "evaluation_id",
        "product_id",
    ):
        _safe_id(payload[field], f"registry {field}")
    _evidence_kind(payload["evidence_kind"], "registry evidence_kind")
    for field in (
        "source_bundle_sha256",
        "model_sha256",
        "model_run_manifest_sha256",
        "evaluation_manifest_sha256",
        "product_manifest_sha256",
    ):
        _sha256(payload[field], f"registry {field}")
    for field in (
        "controlled_result_receipt_sha256",
        "promotion_acceptance_receipt_sha256",
        "field_validation_receipt_sha256",
        "agency_acceptance_receipt_sha256",
    ):
        _nullable_sha256(payload[field], f"registry {field}")
    _require_false(payload["official_warning"], "registry official_warning")
    declared_feed = _strict_bool(
        payload["can_feed_decision_layer"], "registry can_feed_decision_layer"
    )
    status = _nonempty_text(payload["registry_status"], "registry status")
    use = _nonempty_text(payload["permitted_use"], "registry permitted_use")
    if status not in REGISTRY_STATUSES or use not in PERMITTED_USES:
        raise ModelRegistryError("Registry status or permitted use is invalid.")
    reason = payload["reason_blocked"]
    if not isinstance(reason, str):
        raise ModelRegistryError("Registry reason_blocked must be a string.")
    if declared_feed:
        required = (
            payload["dataset_mode"] == "official_input"
            and payload["operational_status"] in {"planning_only", "agency_operational"}
            and status == "approved"
            and use == "decision_input"
            and not reason
            and all(
                payload[field] is not None
                for field in (
                    "controlled_result_receipt_sha256",
                    "promotion_acceptance_receipt_sha256",
                    "field_validation_receipt_sha256",
                    "agency_acceptance_receipt_sha256",
                )
            )
        )
        if not required:
            raise ModelRegistryError(
                "Decision use requires an approved official-input entry and all acceptance receipts."
            )
    elif not reason.strip():
        raise ModelRegistryError("Non-feedable registry entries require reason_blocked.")
    if status == "candidate" and (
        payload["dataset_mode"] not in {"fixture_demo", "candidate"}
        or payload["operational_status"] != "non_operational"
        or use != "report_only"
        or declared_feed
        or any(
            payload[field] is not None
            for field in (
                "promotion_acceptance_receipt_sha256",
                "field_validation_receipt_sha256",
                "agency_acceptance_receipt_sha256",
            )
        )
    ):
        raise ModelRegistryError("Candidate entries are report-only and unaccepted.")
    if status == "shadow" and (use != "shadow_only" or declared_feed):
        raise ModelRegistryError("Shadow entries are shadow-only and non-feedable.")
    if status in {"revoked", "expired", "blocked"} and declared_feed:
        raise ModelRegistryError(f"{status.capitalize()} entries cannot feed decisions.")

    issued = _timestamp(payload["issued_at"], "registry issued_at")
    valid_from = _timestamp(payload["valid_from"], "registry valid_from")
    expires_at = _timestamp(payload["expires_at"], "registry expires_at")
    if not issued <= valid_from < expires_at:
        raise ModelRegistryError(
            "Registry times must satisfy issued_at <= valid_from < expires_at."
        )
    return {
        "issued_at": issued,
        "valid_from": valid_from,
        "expires_at": expires_at,
    }


def _validate_common_identity(value: Mapping[str, object], *, label: str) -> None:
    if value["dataset_mode"] not in {"fixture_demo", "candidate", "official_input"}:
        raise ModelRegistryError(f"{label} dataset_mode is invalid.")
    if value["operational_status"] not in {
        "non_operational",
        "planning_only",
        "agency_operational",
    }:
        raise ModelRegistryError(f"{label} operational_status is invalid.")
    source = _timestamp(value["source_timestamp"], f"{label} source_timestamp")
    generated = _timestamp(value["generated_at"], f"{label} generated_at")
    if generated < source:
        raise ModelRegistryError(f"{label} generated_at cannot predate source_timestamp.")
    _nonempty_text(value["source_name"], f"{label} source_name")
    assumptions = _string_array(value["assumptions"], f"{label} assumptions", minimum=1)
    if len(assumptions) != len(set(assumptions)):
        raise ModelRegistryError(f"{label} assumptions must be unique.")
    if value["dataset_mode"] in {"fixture_demo", "candidate"} and value[
        "operational_status"
    ] != "non_operational":
        raise ModelRegistryError(
            f"{label} fixture/candidate evidence must remain non-operational."
        )


def _canonical_json_bytes(value: object, label: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ModelRegistryError(f"{label} is not canonical JSON: {exc}") from exc


def _require_exact_fields(
    value: Mapping[str, object], expected: frozenset[str], label: str
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise ModelRegistryError(f"{label} fields are invalid: {'; '.join(details)}.")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ModelRegistryError(f"{label} must be an object with string keys.")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise ModelRegistryError(f"{label} must be an array.")
    return value


def _string_array(value: object, label: str, *, minimum: int = 0) -> list[str]:
    values = _sequence(value, label)
    result = [_nonempty_text(item, f"{label} item") for item in values]
    if len(result) < minimum:
        raise ModelRegistryError(f"{label} requires at least {minimum} item(s).")
    return result


def _safe_id(value: object, label: str) -> str:
    text = _nonempty_text(value, label)
    if not SAFE_ID_RE.fullmatch(text):
        raise ModelRegistryError(f"{label} is not a safe identifier.")
    return text


def _evidence_kind(value: object, label: str) -> str:
    text = _nonempty_text(value, label)
    if text not in EVIDENCE_KINDS:
        raise ModelRegistryError(f"{label} is invalid.")
    return text


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelRegistryError(f"{label} must be a non-empty string.")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ModelRegistryError(f"{label} must be a lowercase SHA-256.")
    return value


def _nullable_sha256(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _sha256(value, label)


def _strict_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ModelRegistryError(f"{label} must be a strict boolean.")
    return value


def _require_false(value: object, label: str) -> None:
    if value is not False:
        raise ModelRegistryError(f"{label} must remain false.")


def _finite_number(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
    ):
        raise ModelRegistryError(f"{label} must be finite.")
    return float(value)


def _unit_interval(value: object, label: str) -> float:
    number = _finite_number(value, label)
    if not 0 <= number <= 1:
        raise ModelRegistryError(f"{label} must be between 0 and 1.")
    return number


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ModelRegistryError(f"{label} must be a positive integer.")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ModelRegistryError(f"{label} must be a non-negative integer.")
    return value


def _number_array(value: object, label: str, *, length: int) -> list[float]:
    raw = _sequence(value, label)
    if len(raw) != length:
        raise ModelRegistryError(f"{label} requires exactly {length} numbers.")
    return [_finite_number(item, f"{label} item") for item in raw]


def _positive_pair(value: object, label: str) -> tuple[float, float]:
    numbers = _number_array(value, label, length=2)
    if any(number <= 0 for number in numbers):
        raise ModelRegistryError(f"{label} values must be positive.")
    return numbers[0], numbers[1]


def _ordered_bounds(value: object, label: str) -> tuple[float, float, float, float]:
    numbers = _number_array(value, label, length=4)
    left, bottom, right, top = numbers
    if not left < right or not bottom < top:
        raise ModelRegistryError(f"{label} must be ordered left, bottom, right, top.")
    return left, bottom, right, top


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ModelRegistryError(f"{label} must be an RFC 3339 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ModelRegistryError(f"{label} must be an RFC 3339 timestamp.") from exc
    return _aware_datetime(parsed, label)


def _aware_datetime(value: datetime, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ModelRegistryError(f"{label} must include a timezone.")
    return value


def _signing_key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ModelRegistryError("Registry signing keys must contain at least 32 bytes.")
    return value
