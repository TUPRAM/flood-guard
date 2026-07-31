"""Immutable, leakage-resistant multi-event partition manifests.

The contract in this module is intentionally separate from the older
three-way controlled-experiment partition receipt.  It freezes four model
development roles across complete event, hydrologic-episode, spatial, and
overlap groups:

* ``training``;
* ``model_probability_calibration``;
* ``development``; and
* ``final_holdout``.

Version 1 accepts only synthetic fixture projections so its leakage checks can
be exercised without pretending caller-authored projections prove a qualified
release source chain. Candidate and production sealing remain unavailable
until they can consume canonical validated release bundles plus an attributable
signed holdout-custody receipt.

Fixture manifests are explicitly non-authoritative. They never claim a truly
sealed holdout and never authorize a decision layer, FPPS, an A-E action class,
or an official warning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
import re


MANIFEST_SCHEMA = "floodguard.multi_event_partition_manifest.v1"
QUALIFIED_RELEASE_PROJECTION_SCHEMA = (
    "floodguard.validated_qualified_label_release_projection.v1"
)
QUALIFIED_LABEL_RELEASE_SCHEMA = "floodguard.qualified_label_release.v1"

PARTITION_ROLES = (
    "training",
    "model_probability_calibration",
    "development",
    "final_holdout",
)
PARTITION_MODES = frozenset({"fixture_demo", "candidate", "production"})
RELEASE_MODE_BY_PARTITION_MODE = {
    "fixture_demo": "fixture_demo",
    "candidate": "candidate",
    "production": "official_input",
}
RELEASE_PURPOSES = frozenset({"flood_model_training_labels", "model_final_evaluation"})

STRATIFICATION_VALUES = {
    "settlement_stratum": frozenset({"urban", "rural", "mixed"}),
    "terrain_stratum": frozenset({"flat", "steep", "rolling", "mixed"}),
    "flood_mechanism_stratum": frozenset(
        {"riverine", "flash", "urban_pluvial", "coastal", "mixed"}
    ),
    "permanent_water_stratum": frozenset({"present", "absent", "mixed"}),
    "vegetation_stratum": frozenset({"dense", "sparse", "mixed"}),
    "radar_quality_stratum": frozenset({"high", "medium", "low", "mixed"}),
}

SOURCE_DEPENDENCY_KINDS = frozenset({"event_predictor", "static_non_target_context"})
PROHIBITED_FEATURE_TOKENS = (
    "reviewer",
    "label",
    "ground_truth",
    "reference_mask",
    "qualified_reference",
    "adjudicat",
    "consensus",
    "target_class",
    "target_value",
    "fpps",
    "action_class",
    "official_warning",
)
DOWNSTREAM_SAFETY_FIELDS = (
    "eligible_for_decision_layer",
    "eligible_for_access_analysis",
    "eligible_for_equity_analysis",
    "eligible_for_fpps",
    "eligible_for_action_class",
    "eligible_for_warning",
    "official_warning",
    "agency_operational_authority",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_FEATURE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,127}$")
_CRS_RE = re.compile(r"^EPSG:[1-9][0-9]{2,6}$", re.IGNORECASE)
_PRIVATE_PATH_RE = re.compile(
    r"(?:^|[\s\"'=])(?:[A-Za-z]:[\\/]|file://|"
    r"\\\\[^\\/\s]+[\\/][^\\/\s]+|"
    r"/(?:home|Users|private|tmp|var|opt|mnt|srv|root|Volumes|data|"
    r"workspace|usr|run)(?:[\\/]|$))",
    re.IGNORECASE,
)

_RAW_UNIT_FIELDS = {
    "partition_unit_id",
    "role",
    "event_id",
    "hydrologic_episode_id",
    "study_area_id",
    "qualified_label_release_sha256",
    "spatial_group_id",
    "overlap_group_id",
    "core_bounds",
    "buffered_bounds",
    "bounds_crs",
    "bounds_units",
    "source_dependencies",
    "target_dependencies",
    "strata",
}
_STORED_UNIT_FIELDS = {
    *_RAW_UNIT_FIELDS,
    "grid_schema_sha256",
    "feature_schema_sha256",
    "context_halo_m",
    "source_dependency_set_sha256",
    "target_dependency_set_sha256",
    "unit_sha256",
}

_PROJECTION_FIELDS = {
    "artifact_schema",
    "projection_id",
    "validation_status",
    "validation_method",
    "validator_code_sha256",
    "source_artifact_schema",
    "release_id",
    "dataset_mode",
    "synthetic_fixture_only",
    "confers_authority",
    "event_id",
    "hydrologic_episode_id",
    "study_area_id",
    "purpose",
    "qualified_label_release_sha256",
    "qualified_reference_receipt_sha256",
    "human_role_package_sha256",
    "reviewer_calibration_receipt_sha256",
    "labelset_manifest_sha256",
    "labelset_validation_receipt_sha256",
    "label_content_sha256",
    "labelset_purpose_binding_sha256",
    "raster_lineage_sha256",
    "query_region_ids",
    "agreement_evidence_sha256",
    "consensus_receipt_sha256",
    "adjudication_import_receipt_sha256",
    "release_created_at_utc",
    "validated_at_utc",
    "processing_allowed",
    "eligible_for_flood_model_training",
    "eligible_for_model_evaluation",
    *DOWNSTREAM_SAFETY_FIELDS,
    "assumptions",
    "projection_sha256",
}

_MANIFEST_FIELDS = {
    "artifact_schema",
    "manifest_id",
    "manifest_status",
    "dataset_mode",
    "synthetic_fixture_only",
    "confers_authority",
    "qualified_label_release_bindings",
    "qualified_release_set_sha256",
    "grid_schema",
    "feature_schema",
    "partition_algorithm",
    "preprocessing_contract",
    "context_halo_m",
    "static_context_exemptions",
    "partition_units",
    "partition_unit_count_by_role",
    "event_ids_by_role",
    "event_count_by_role",
    "role_partition_sha256",
    "final_holdout_contract",
    "created_at_utc",
    "fitting_not_before_utc",
    *DOWNSTREAM_SAFETY_FIELDS,
    "assumptions",
    "manifest_sha256",
}


class MultiEventPartitionError(ValueError):
    """Raised when a multi-event partition contract fails closed."""


def canonical_sha256(value: object) -> str:
    """Return the SHA-256 digest of strict canonical JSON content."""

    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MultiEventPartitionError(
            "Partition evidence must contain finite strict-JSON values."
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def build_multi_event_partition_manifest(
    *,
    manifest_id: str,
    dataset_mode: str,
    partition_units: Sequence[Mapping[str, object]],
    qualified_release_projections: Sequence[Mapping[str, object]],
    static_context_exemptions: Sequence[Mapping[str, object]],
    grid_schema_id: str,
    grid_schema_sha256: str,
    feature_schema_id: str,
    feature_schema_sha256: str,
    feature_names: Sequence[str],
    partition_algorithm_id: str,
    partition_algorithm_version: str,
    algorithm_code_sha256: str,
    random_seed: int,
    seed_declared_at_utc: str | datetime,
    preprocessing_plan_sha256: str,
    context_halo_m: int | float,
    holdout_custodian_receipt_sha256: str,
    created_at_utc: str | datetime,
    fitting_not_before_utc: str | datetime,
    assumptions: Sequence[str],
) -> dict[str, object]:
    """Build a sealed four-role partition manifest from verified projections.

    ``qualified_release_projections`` must be produced only after the exact
    source release has passed the qualified-label-release validator.  The
    projection binds that validation claim, its validator-code hash, and the
    protected label/reference/reviewer/adjudication lineage.
    """

    mode = _partition_mode(dataset_mode)
    _require_fixture_only_partition_mode(mode)
    projections = _validated_projections(
        qualified_release_projections, partition_mode=mode
    )
    created = _timestamp(created_at_utc, "created_at_utc")
    fitting_not_before = _timestamp(fitting_not_before_utc, "fitting_not_before_utc")
    if created >= fitting_not_before:
        raise MultiEventPartitionError(
            "The partition manifest must be sealed before any fitting begins."
        )
    for projection in projections:
        if (
            _timestamp(projection["validated_at_utc"], "projection validated_at_utc")
            > created
        ):
            raise MultiEventPartitionError(
                "A partition cannot bind a release validated after manifest seal."
            )

    seed_declared = _timestamp(seed_declared_at_utc, "seed_declared_at_utc")
    earliest_release = min(
        _timestamp(
            projection["release_created_at_utc"],
            "projection release_created_at_utc",
        )
        for projection in projections
    )
    if seed_declared >= earliest_release or seed_declared > created:
        raise MultiEventPartitionError(
            "Partition seed must be predeclared before any qualified label release."
        )
    seed = _seed(random_seed)
    halo = _positive_number(context_halo_m, "context_halo_m")

    grid_schema = {
        "schema_id": _safe_id(grid_schema_id, "grid_schema_id"),
        "schema_sha256": _sha256(grid_schema_sha256, "grid_schema_sha256"),
    }
    normalized_feature_names = _feature_names(feature_names)
    feature_schema = {
        "schema_id": _safe_id(feature_schema_id, "feature_schema_id"),
        "schema_sha256": _sha256(feature_schema_sha256, "feature_schema_sha256"),
        "feature_names": normalized_feature_names,
    }
    algorithm = {
        "algorithm_id": _safe_id(partition_algorithm_id, "partition_algorithm_id"),
        "algorithm_version": _text(
            partition_algorithm_version, "partition_algorithm_version"
        ),
        "implementation_code_sha256": _sha256(
            algorithm_code_sha256, "algorithm_code_sha256"
        ),
        "random_seed": seed,
        "seed_declared_at_utc": _iso_utc(seed_declared),
        "target_statistics_used": False,
        "labels_inspected_before_freeze": False,
        "post_label_seed_selection": False,
        "algorithm_locked": True,
    }
    preprocessing = {
        "plan_sha256": _sha256(preprocessing_plan_sha256, "preprocessing_plan_sha256"),
        "fit_scope": "training_only",
        "fit_partition_roles": ["training"],
        "full_corpus_fitted": False,
        "model_probability_calibration_used_for_fit": False,
        "development_used_for_fit": False,
        "final_holdout_used_for_fit": False,
        "fitting_not_before_utc": _iso_utc(fitting_not_before),
    }
    holdout = {
        "status": "synthetic_fixture_closed_non_authoritative",
        "synthetic_fixture_only": True,
        "custody_authority_verified": False,
        "confers_custody_authority": False,
        "holdout_closed": True,
        "holdout_opened": False,
        "reference_opened": False,
        "used_for_partition_selection": False,
        "used_for_feature_selection": False,
        "used_for_preprocessing_fit": False,
        "used_for_probability_calibration": False,
        "used_for_threshold_selection": False,
        "used_for_model_selection": False,
        "evaluation_count": 0,
        "opened_at_utc": None,
        "custodian_receipt_sha256": _sha256(
            holdout_custodian_receipt_sha256,
            "holdout_custodian_receipt_sha256",
        ),
    }

    exemptions = _normalize_static_exemptions(static_context_exemptions)
    projection_index = _projection_index(projections)
    units = [
        _build_partition_unit(
            raw,
            projection_index=projection_index,
            exemptions=exemptions,
            grid_schema_sha256=str(grid_schema["schema_sha256"]),
            feature_schema_sha256=str(feature_schema["schema_sha256"]),
            context_halo_m=halo,
        )
        for raw in partition_units
    ]
    units.sort(key=lambda item: str(item["partition_unit_id"]))
    metadata = _partition_metadata(
        units,
        projections=projections,
        exemptions=exemptions,
        partition_mode=mode,
    )
    bindings = _qualified_release_bindings(projections)

    payload: dict[str, object] = {
        "artifact_schema": MANIFEST_SCHEMA,
        "manifest_id": _safe_id(manifest_id, "manifest_id"),
        "manifest_status": "sealed",
        "dataset_mode": mode,
        "synthetic_fixture_only": mode == "fixture_demo",
        "confers_authority": False,
        "qualified_label_release_bindings": bindings,
        "qualified_release_set_sha256": canonical_sha256(bindings),
        "grid_schema": grid_schema,
        "feature_schema": feature_schema,
        "partition_algorithm": algorithm,
        "preprocessing_contract": preprocessing,
        "context_halo_m": halo,
        "static_context_exemptions": exemptions,
        "partition_units": units,
        "partition_unit_count_by_role": metadata["unit_counts"],
        "event_ids_by_role": metadata["event_ids"],
        "event_count_by_role": metadata["event_counts"],
        "role_partition_sha256": metadata["role_hashes"],
        "final_holdout_contract": holdout,
        "created_at_utc": _iso_utc(created),
        "fitting_not_before_utc": _iso_utc(fitting_not_before),
        **_false_safety_fields(),
        "assumptions": _assumptions(assumptions),
    }
    payload["manifest_sha256"] = canonical_sha256(payload)
    return validate_multi_event_partition_manifest(
        payload, qualified_release_projections=projections
    )


def validate_multi_event_partition_manifest(
    manifest: Mapping[str, object],
    *,
    qualified_release_projections: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Validate a manifest, its self-hash, and exact release projections."""

    value = _mapping_copy(manifest, "multi-event partition manifest")
    _exact_fields(value, _MANIFEST_FIELDS, "multi-event partition manifest")
    if value["artifact_schema"] != MANIFEST_SCHEMA:
        raise MultiEventPartitionError("Unsupported partition artifact_schema.")
    _verify_self_hash(value, "manifest_sha256", "multi-event partition manifest")
    _safe_id(value["manifest_id"], "manifest_id")
    if value["manifest_status"] != "sealed":
        raise MultiEventPartitionError("Partition manifest is not sealed.")
    mode = _partition_mode(value["dataset_mode"])
    _require_fixture_only_partition_mode(mode)
    if (
        value["synthetic_fixture_only"] is not (mode == "fixture_demo")
        or value["confers_authority"] is not False
    ):
        raise MultiEventPartitionError(
            "Partition fixture or authority disclosure is inconsistent."
        )

    projections = _validated_projections(
        qualified_release_projections, partition_mode=mode
    )
    bindings = _qualified_release_bindings(projections)
    if value["qualified_label_release_bindings"] != bindings or value[
        "qualified_release_set_sha256"
    ] != canonical_sha256(bindings):
        raise MultiEventPartitionError(
            "Qualified-label-release projection bindings were substituted."
        )

    grid_schema = _validate_schema_binding(
        value["grid_schema"], "grid schema", include_features=False
    )
    feature_schema = _validate_schema_binding(
        value["feature_schema"], "feature schema", include_features=True
    )
    algorithm = _validate_algorithm(value["partition_algorithm"])
    preprocessing = _validate_preprocessing(value["preprocessing_contract"])
    halo = _positive_number(value["context_halo_m"], "context_halo_m")
    exemptions = _normalize_static_exemptions(
        _sequence(value["static_context_exemptions"], "static_context_exemptions")
    )

    created = _timestamp(value["created_at_utc"], "created_at_utc")
    fitting_not_before = _timestamp(
        value["fitting_not_before_utc"], "fitting_not_before_utc"
    )
    if created >= fitting_not_before or preprocessing[
        "fitting_not_before_utc"
    ] != _iso_utc(fitting_not_before):
        raise MultiEventPartitionError(
            "Manifest or preprocessing chronology permits pre-freeze fitting."
        )
    seed_declared = _timestamp(
        algorithm["seed_declared_at_utc"], "seed_declared_at_utc"
    )
    earliest_release = min(
        _timestamp(
            projection["release_created_at_utc"],
            "projection release_created_at_utc",
        )
        for projection in projections
    )
    if seed_declared >= earliest_release or seed_declared > created:
        raise MultiEventPartitionError(
            "Partition seed was selected after qualified labels became available."
        )
    if any(
        _timestamp(projection["validated_at_utc"], "projection validated_at_utc")
        > created
        for projection in projections
    ):
        raise MultiEventPartitionError(
            "Manifest predates a bound qualified-release validation."
        )

    raw_units = _sequence(value["partition_units"], "partition_units")
    projection_index = _projection_index(projections)
    units = [
        _validate_stored_partition_unit(
            raw,
            projection_index=projection_index,
            exemptions=exemptions,
            grid_schema_sha256=str(grid_schema["schema_sha256"]),
            feature_schema_sha256=str(feature_schema["schema_sha256"]),
            context_halo_m=halo,
        )
        for raw in raw_units
    ]
    if units != sorted(units, key=lambda item: str(item["partition_unit_id"])):
        raise MultiEventPartitionError(
            "Partition units must use deterministic partition_unit_id order."
        )
    metadata = _partition_metadata(
        units,
        projections=projections,
        exemptions=exemptions,
        partition_mode=mode,
    )
    if (
        value["partition_unit_count_by_role"] != metadata["unit_counts"]
        or value["event_ids_by_role"] != metadata["event_ids"]
        or value["event_count_by_role"] != metadata["event_counts"]
        or value["role_partition_sha256"] != metadata["role_hashes"]
    ):
        raise MultiEventPartitionError(
            "Derived per-role partition metadata or hashes were substituted."
        )

    _validate_holdout_contract(value["final_holdout_contract"])
    _require_false_safety(value, "multi-event partition manifest")
    _assumptions(value["assumptions"])
    return value


def _validated_projections(
    values: Sequence[Mapping[str, object]],
    *,
    partition_mode: str,
) -> list[dict[str, object]]:
    raw_values = _sequence(values, "qualified_release_projections")
    if not raw_values:
        raise MultiEventPartitionError(
            "At least one validated qualified-label release is required."
        )
    projections = [_validate_projection(value) for value in raw_values]
    projections.sort(
        key=lambda item: (
            str(item["event_id"]),
            str(item["hydrologic_episode_id"]),
            str(item["study_area_id"]),
        )
    )
    identities: set[tuple[str, str, str]] = set()
    event_ids: set[str] = set()
    projection_ids: set[str] = set()
    release_hashes: set[str] = set()
    expected_release_mode = RELEASE_MODE_BY_PARTITION_MODE[partition_mode]
    for projection in projections:
        identity = _projection_identity(projection)
        if (
            identity in identities
            or str(projection["event_id"]) in event_ids
            or str(projection["projection_id"]) in projection_ids
            or str(projection["qualified_label_release_sha256"]) in release_hashes
        ):
            raise MultiEventPartitionError(
                "Qualified-release projections contain duplicate identity or hashes."
            )
        identities.add(identity)
        event_ids.add(str(projection["event_id"]))
        projection_ids.add(str(projection["projection_id"]))
        release_hashes.add(str(projection["qualified_label_release_sha256"]))
        if projection["dataset_mode"] != expected_release_mode:
            raise MultiEventPartitionError(
                "Qualified-release mode does not match the partition mode."
            )
        expected_synthetic = partition_mode == "fixture_demo"
        if projection["synthetic_fixture_only"] is not expected_synthetic:
            raise MultiEventPartitionError(
                "Fixture projections cannot enter candidate or production partitions."
            )
    return projections


def _validate_projection(value: object) -> dict[str, object]:
    projection = _mapping_copy(value, "validated qualified-label-release projection")
    _exact_fields(
        projection,
        _PROJECTION_FIELDS,
        "validated qualified-label-release projection",
    )
    if (
        projection["artifact_schema"] != QUALIFIED_RELEASE_PROJECTION_SCHEMA
        or projection["source_artifact_schema"] != QUALIFIED_LABEL_RELEASE_SCHEMA
    ):
        raise MultiEventPartitionError(
            "Qualified-release projection has an unsupported schema."
        )
    _verify_self_hash(
        projection,
        "projection_sha256",
        "validated qualified-label-release projection",
    )
    for field in (
        "projection_id",
        "release_id",
        "event_id",
        "hydrologic_episode_id",
        "study_area_id",
    ):
        _safe_id(projection[field], field)
    if (
        projection["validation_status"] != "passed"
        or projection["validation_method"]
        != (
            "floodguard.label_factory.qualified_label_release."
            "validate_qualified_label_release"
        )
        or projection["processing_allowed"] is not True
        or projection["confers_authority"] is not False
    ):
        raise MultiEventPartitionError(
            "Qualified-release projection does not prove a passed validation."
        )
    _sha256(projection["validator_code_sha256"], "validator_code_sha256")
    release_mode = _release_mode(projection["dataset_mode"])
    if projection["synthetic_fixture_only"] is not (release_mode == "fixture_demo"):
        raise MultiEventPartitionError(
            "Qualified-release projection fixture disclosure is inconsistent."
        )
    if projection["purpose"] not in RELEASE_PURPOSES:
        raise MultiEventPartitionError(
            "Qualified-release projection has an unsupported purpose."
        )
    expected_training = projection["purpose"] == "flood_model_training_labels"
    if projection[
        "eligible_for_flood_model_training"
    ] is not expected_training or projection["eligible_for_model_evaluation"] is not (
        not expected_training
    ):
        raise MultiEventPartitionError(
            "Qualified-release projection purpose eligibility is inconsistent."
        )
    for field in (
        "qualified_label_release_sha256",
        "qualified_reference_receipt_sha256",
        "human_role_package_sha256",
        "reviewer_calibration_receipt_sha256",
        "labelset_manifest_sha256",
        "labelset_validation_receipt_sha256",
        "label_content_sha256",
        "labelset_purpose_binding_sha256",
        "raster_lineage_sha256",
        "agreement_evidence_sha256",
        "consensus_receipt_sha256",
        "adjudication_import_receipt_sha256",
    ):
        _sha256(projection[field], field)
    query_region_ids = _text_array(
        projection["query_region_ids"],
        "projection query_region_ids",
        minimum=1,
    )
    if query_region_ids != sorted(query_region_ids):
        raise MultiEventPartitionError(
            "Projection query_region_ids must use deterministic sorted order."
        )
    created = _timestamp(projection["release_created_at_utc"], "release_created_at_utc")
    validated = _timestamp(projection["validated_at_utc"], "validated_at_utc")
    if validated < created:
        raise MultiEventPartitionError(
            "Qualified-release projection validation predates the release."
        )
    _require_false_safety(projection, "validated qualified-label-release projection")
    _assumptions(projection["assumptions"])
    return projection


def _qualified_release_bindings(
    projections: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            "event_id": projection["event_id"],
            "hydrologic_episode_id": projection["hydrologic_episode_id"],
            "study_area_id": projection["study_area_id"],
            "release_id": projection["release_id"],
            "purpose": projection["purpose"],
            "qualified_label_release_sha256": projection[
                "qualified_label_release_sha256"
            ],
            "projection_sha256": projection["projection_sha256"],
        }
        for projection in projections
    ]


def _projection_identity(
    projection: Mapping[str, object],
) -> tuple[str, str, str]:
    return (
        str(projection["event_id"]),
        str(projection["hydrologic_episode_id"]),
        str(projection["study_area_id"]),
    )


def _projection_index(
    projections: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, str], Mapping[str, object]]:
    return {_projection_identity(projection): projection for projection in projections}


def _normalize_static_exemptions(
    values: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    raw_values = _sequence(values, "static_context_exemptions")
    exemptions: list[dict[str, object]] = []
    for raw in raw_values:
        value = _mapping_copy(raw, "static context exemption")
        _exact_fields(
            value,
            {
                "exemption_id",
                "dependency_id",
                "artifact_sha256",
                "rationale",
                "target_independent",
                "temporal_scope",
                "fitted_from_partition_data",
            },
            "static context exemption",
        )
        exemption = {
            "exemption_id": _safe_id(value["exemption_id"], "static exemption_id"),
            "dependency_id": _safe_id(value["dependency_id"], "static dependency_id"),
            "artifact_sha256": _sha256(
                value["artifact_sha256"], "static artifact_sha256"
            ),
            "rationale": _text(value["rationale"], "static exemption rationale"),
            "target_independent": value["target_independent"],
            "temporal_scope": value["temporal_scope"],
            "fitted_from_partition_data": value["fitted_from_partition_data"],
        }
        if (
            exemption["target_independent"] is not True
            or exemption["temporal_scope"] != "static"
            or exemption["fitted_from_partition_data"] is not False
        ):
            raise MultiEventPartitionError(
                "Static context exemptions must be target-independent, "
                "temporally static, and unfitted."
            )
        _reject_prohibited_feature_identifier(
            str(exemption["dependency_id"]), "static dependency_id"
        )
        exemptions.append(exemption)
    exemptions.sort(key=lambda item: str(item["exemption_id"]))
    if len({str(item["exemption_id"]) for item in exemptions}) != len(exemptions):
        raise MultiEventPartitionError("Static context exemption IDs must be unique.")
    if len({str(item["artifact_sha256"]) for item in exemptions}) != len(exemptions):
        raise MultiEventPartitionError(
            "One static artifact hash cannot use multiple exemptions."
        )
    return exemptions


def _build_partition_unit(
    raw: Mapping[str, object],
    *,
    projection_index: Mapping[tuple[str, str, str], Mapping[str, object]],
    exemptions: Sequence[Mapping[str, object]],
    grid_schema_sha256: str,
    feature_schema_sha256: str,
    context_halo_m: float,
) -> dict[str, object]:
    value = _mapping_copy(raw, "partition unit")
    _exact_fields(value, _RAW_UNIT_FIELDS, "partition unit input")
    unit = _normalize_partition_unit_core(
        value,
        projection_index=projection_index,
        exemptions=exemptions,
        grid_schema_sha256=grid_schema_sha256,
        feature_schema_sha256=feature_schema_sha256,
        context_halo_m=context_halo_m,
    )
    unit["unit_sha256"] = canonical_sha256(unit)
    return unit


def _validate_stored_partition_unit(
    raw: Mapping[str, object],
    *,
    projection_index: Mapping[tuple[str, str, str], Mapping[str, object]],
    exemptions: Sequence[Mapping[str, object]],
    grid_schema_sha256: str,
    feature_schema_sha256: str,
    context_halo_m: float,
) -> dict[str, object]:
    value = _mapping_copy(raw, "stored partition unit")
    _exact_fields(value, _STORED_UNIT_FIELDS, "stored partition unit")
    _verify_self_hash(value, "unit_sha256", "stored partition unit")
    core = {field: value[field] for field in _RAW_UNIT_FIELDS}
    expected = _normalize_partition_unit_core(
        core,
        projection_index=projection_index,
        exemptions=exemptions,
        grid_schema_sha256=grid_schema_sha256,
        feature_schema_sha256=feature_schema_sha256,
        context_halo_m=context_halo_m,
    )
    expected["unit_sha256"] = canonical_sha256(expected)
    if value != expected:
        raise MultiEventPartitionError(
            "Stored partition unit differs from its normalized dependencies."
        )
    return value


def _normalize_partition_unit_core(
    value: Mapping[str, object],
    *,
    projection_index: Mapping[tuple[str, str, str], Mapping[str, object]],
    exemptions: Sequence[Mapping[str, object]],
    grid_schema_sha256: str,
    feature_schema_sha256: str,
    context_halo_m: float,
) -> dict[str, object]:
    role = _role(value["role"])
    event_id = _safe_id(value["event_id"], "event_id")
    episode_id = _safe_id(value["hydrologic_episode_id"], "hydrologic_episode_id")
    study_area_id = _safe_id(value["study_area_id"], "study_area_id")
    identity = (event_id, episode_id, study_area_id)
    projection = projection_index.get(identity)
    if projection is None:
        raise MultiEventPartitionError(
            "Partition unit lacks an exact qualified-release projection."
        )
    release_sha = _sha256(
        value["qualified_label_release_sha256"],
        "qualified_label_release_sha256",
    )
    if release_sha != projection["qualified_label_release_sha256"]:
        raise MultiEventPartitionError(
            "Partition unit qualified-label-release hash was substituted."
        )
    expected_purpose = (
        "model_final_evaluation"
        if role == "final_holdout"
        else "flood_model_training_labels"
    )
    if projection["purpose"] != expected_purpose:
        raise MultiEventPartitionError(
            f"{role} uses the wrong purpose-qualified label release."
        )

    crs = _projected_crs(value["bounds_crs"])
    if value["bounds_units"] != "metre":
        raise MultiEventPartitionError(
            "Partition buffered bounds must declare metre units."
        )
    core_bounds = _bounds(value["core_bounds"], "core_bounds")
    buffered_bounds = _bounds(value["buffered_bounds"], "buffered_bounds")
    _validate_halo_bounds(core_bounds, buffered_bounds, context_halo_m=context_halo_m)

    exemption_index = {str(item["exemption_id"]): item for item in exemptions}
    source_dependencies = _normalize_source_dependencies(
        value["source_dependencies"],
        event_id=event_id,
        exemption_index=exemption_index,
    )
    target_dependencies = _normalize_target_dependencies(
        value["target_dependencies"], projection=projection
    )
    strata = _strata(value["strata"])
    return {
        "partition_unit_id": _safe_id(value["partition_unit_id"], "partition_unit_id"),
        "role": role,
        "event_id": event_id,
        "hydrologic_episode_id": episode_id,
        "study_area_id": study_area_id,
        "qualified_label_release_sha256": release_sha,
        "spatial_group_id": _safe_id(value["spatial_group_id"], "spatial_group_id"),
        "overlap_group_id": _safe_id(value["overlap_group_id"], "overlap_group_id"),
        "core_bounds": core_bounds,
        "buffered_bounds": buffered_bounds,
        "bounds_crs": crs,
        "bounds_units": "metre",
        "source_dependencies": source_dependencies,
        "target_dependencies": target_dependencies,
        "strata": strata,
        "grid_schema_sha256": grid_schema_sha256,
        "feature_schema_sha256": feature_schema_sha256,
        "context_halo_m": context_halo_m,
        "source_dependency_set_sha256": canonical_sha256(source_dependencies),
        "target_dependency_set_sha256": canonical_sha256(target_dependencies),
    }


def _normalize_source_dependencies(
    value: object,
    *,
    event_id: str,
    exemption_index: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    raw_dependencies = _sequence(value, "source_dependencies")
    if not raw_dependencies:
        raise MultiEventPartitionError(
            "Every partition unit requires source dependencies."
        )
    dependencies: list[dict[str, object]] = []
    for raw in raw_dependencies:
        dependency = _mapping_copy(raw, "source dependency")
        _exact_fields(
            dependency,
            {
                "dependency_id",
                "artifact_sha256",
                "dependency_kind",
                "event_id",
                "target_independent",
                "temporal_scope",
                "static_context_exemption_id",
            },
            "source dependency",
        )
        dependency_id = _safe_id(dependency["dependency_id"], "source dependency_id")
        _reject_prohibited_feature_identifier(dependency_id, "source dependency_id")
        kind = _text(dependency["dependency_kind"], "dependency_kind")
        if kind not in SOURCE_DEPENDENCY_KINDS:
            raise MultiEventPartitionError(
                "Source dependency kind is not an allowed predictor/context kind."
            )
        artifact_sha = _sha256(dependency["artifact_sha256"], "source artifact_sha256")
        if dependency["target_independent"] is not True:
            raise MultiEventPartitionError(
                "Every feature dependency must be explicitly target-independent."
            )
        if kind == "event_predictor":
            if (
                dependency["event_id"] != event_id
                or dependency["temporal_scope"] != "event_specific"
                or dependency["static_context_exemption_id"] is not None
            ):
                raise MultiEventPartitionError(
                    "Event predictors must bind their own event without an exemption."
                )
            normalized_event_id: str | None = event_id
            exemption_id: str | None = None
        else:
            if (
                dependency["event_id"] is not None
                or dependency["temporal_scope"] != "static"
            ):
                raise MultiEventPartitionError(
                    "Static non-target context cannot bind an event."
                )
            exemption_id = _safe_id(
                dependency["static_context_exemption_id"],
                "static_context_exemption_id",
            )
            exemption = exemption_index.get(exemption_id)
            if (
                exemption is None
                or exemption["dependency_id"] != dependency_id
                or exemption["artifact_sha256"] != artifact_sha
            ):
                raise MultiEventPartitionError(
                    "Static context dependency lacks its exact declared exemption."
                )
            normalized_event_id = None
        dependencies.append(
            {
                "dependency_id": dependency_id,
                "artifact_sha256": artifact_sha,
                "dependency_kind": kind,
                "event_id": normalized_event_id,
                "target_independent": True,
                "temporal_scope": dependency["temporal_scope"],
                "static_context_exemption_id": exemption_id,
            }
        )
    dependencies.sort(key=lambda item: str(item["dependency_id"]))
    if len({str(item["dependency_id"]) for item in dependencies}) != len(dependencies):
        raise MultiEventPartitionError(
            "Source dependency IDs must be unique within a partition unit."
        )
    if not any(item["dependency_kind"] == "event_predictor" for item in dependencies):
        raise MultiEventPartitionError(
            "Every partition unit requires an event-specific predictor."
        )
    return dependencies


def _normalize_target_dependencies(
    value: object,
    *,
    projection: Mapping[str, object],
) -> dict[str, str]:
    target = _mapping_copy(value, "target_dependencies")
    _exact_fields(
        target,
        {
            "qualified_label_release_sha256",
            "label_content_sha256",
        },
        "target_dependencies",
    )
    normalized = {
        "qualified_label_release_sha256": _sha256(
            target["qualified_label_release_sha256"],
            "target qualified_label_release_sha256",
        ),
        "label_content_sha256": _sha256(
            target["label_content_sha256"],
            "target label_content_sha256",
        ),
    }
    if (
        normalized["qualified_label_release_sha256"]
        != projection["qualified_label_release_sha256"]
        or normalized["label_content_sha256"] != projection["label_content_sha256"]
    ):
        raise MultiEventPartitionError(
            "Partition target dependencies differ from the qualified release."
        )
    return normalized


def _partition_metadata(
    units: Sequence[Mapping[str, object]],
    *,
    projections: Sequence[Mapping[str, object]],
    exemptions: Sequence[Mapping[str, object]],
    partition_mode: str,
) -> dict[str, dict[str, object]]:
    if not units:
        raise MultiEventPartitionError("Partition manifest has no units.")
    unit_ids = [str(unit["partition_unit_id"]) for unit in units]
    if len(unit_ids) != len(set(unit_ids)):
        raise MultiEventPartitionError("Partition unit IDs contain duplicates.")
    identities = [
        (
            str(unit["event_id"]),
            str(unit["hydrologic_episode_id"]),
            str(unit["study_area_id"]),
            str(unit["spatial_group_id"]),
            tuple(float(item) for item in unit["core_bounds"]),
        )
        for unit in units
    ]
    if len(identities) != len(set(identities)):
        raise MultiEventPartitionError(
            "Partition manifest contains duplicate event/group/bounds units."
        )

    units_by_role: dict[str, list[Mapping[str, object]]] = {
        role: [] for role in PARTITION_ROLES
    }
    for unit in units:
        units_by_role[str(unit["role"])].append(unit)
    empty_roles = [role for role, role_units in units_by_role.items() if not role_units]
    if empty_roles:
        raise MultiEventPartitionError(
            "Every partition role must be nonempty: " + ", ".join(empty_roles)
        )

    _reject_cross_role_identifier_leakage(units)
    _reject_cross_role_buffer_leakage(units)
    _reject_cross_role_target_lineage_reuse(
        units,
        projections=projections,
    )
    _reject_source_dependency_leakage(
        units, projections=projections, exemptions=exemptions
    )
    _validate_projection_coverage(units, projections=projections)
    _validate_heterogeneity(units, partition_mode=partition_mode)

    event_ids = {
        role: sorted({str(unit["event_id"]) for unit in units_by_role[role]})
        for role in PARTITION_ROLES
    }
    unit_counts = {role: len(units_by_role[role]) for role in PARTITION_ROLES}
    event_counts = {role: len(event_ids[role]) for role in PARTITION_ROLES}
    role_hashes = {
        role: canonical_sha256(
            {
                "role": role,
                "partition_units": sorted(
                    units_by_role[role],
                    key=lambda item: str(item["partition_unit_id"]),
                ),
            }
        )
        for role in PARTITION_ROLES
    }
    if len(set(role_hashes.values())) != len(PARTITION_ROLES):
        raise MultiEventPartitionError("Per-role partition hashes must be distinct.")
    return {
        "unit_counts": unit_counts,
        "event_ids": event_ids,
        "event_counts": event_counts,
        "role_hashes": role_hashes,
    }


def _reject_cross_role_identifier_leakage(
    units: Sequence[Mapping[str, object]],
) -> None:
    fields = (
        "event_id",
        "hydrologic_episode_id",
        "spatial_group_id",
        "overlap_group_id",
    )
    for field in fields:
        roles_by_value: dict[str, set[str]] = {}
        for unit in units:
            roles_by_value.setdefault(str(unit[field]), set()).add(str(unit["role"]))
        leaked = sorted(
            value for value, roles in roles_by_value.items() if len(roles) > 1
        )
        if leaked:
            raise MultiEventPartitionError(
                f"{field} leakage crosses partition roles: " + ", ".join(leaked)
            )

    crs_by_study_area: dict[str, set[str]] = {}
    for unit in units:
        crs_by_study_area.setdefault(str(unit["study_area_id"]), set()).add(
            str(unit["bounds_crs"])
        )
    inconsistent = sorted(
        study_area
        for study_area, crs_values in crs_by_study_area.items()
        if len(crs_values) != 1
    )
    if inconsistent:
        raise MultiEventPartitionError(
            "A study area cannot change buffered-bounds CRS across units: "
            + ", ".join(inconsistent)
        )


def _reject_cross_role_buffer_leakage(
    units: Sequence[Mapping[str, object]],
) -> None:
    crs_values = {str(unit["bounds_crs"]) for unit in units}
    if len(crs_values) != 1:
        raise MultiEventPartitionError(
            "Mixed bounds CRS is unsupported in partition v1; normalize every "
            "unit to one canonical projected CRS before leakage checks."
        )
    for index, left in enumerate(units):
        for right in units[index + 1 :]:
            if left["role"] == right["role"]:
                continue
            if _bounds_overlap_or_touch(
                left["buffered_bounds"], right["buffered_bounds"]
            ):
                raise MultiEventPartitionError(
                    "Buffered bounds/context halos overlap across partition "
                    f"roles: {left['partition_unit_id']} and "
                    f"{right['partition_unit_id']}."
                )


def _reject_cross_role_target_lineage_reuse(
    units: Sequence[Mapping[str, object]],
    *,
    projections: Sequence[Mapping[str, object]],
) -> None:
    projection_by_release = {
        str(projection["qualified_label_release_sha256"]): projection
        for projection in projections
    }
    roles_by_identity: dict[str, set[str]] = {}
    fields = (
        "qualified_label_release_sha256",
        "qualified_reference_receipt_sha256",
        "labelset_manifest_sha256",
        "labelset_validation_receipt_sha256",
        "label_content_sha256",
        "labelset_purpose_binding_sha256",
        "raster_lineage_sha256",
        "agreement_evidence_sha256",
        "consensus_receipt_sha256",
        "adjudication_import_receipt_sha256",
    )
    for unit in units:
        release_sha = str(unit["qualified_label_release_sha256"])
        projection = projection_by_release[release_sha]
        role = str(unit["role"])
        for field in fields:
            identity = f"{field}:{projection[field]}"
            roles_by_identity.setdefault(identity, set()).add(role)
        for query_region_id in projection["query_region_ids"]:
            identity = f"query_region_id:{query_region_id}"
            roles_by_identity.setdefault(identity, set()).add(role)
    leaked = sorted(
        identity for identity, roles in roles_by_identity.items() if len(roles) > 1
    )
    if leaked:
        raise MultiEventPartitionError(
            "Protected label/query/reference/review lineage crosses partition "
            "roles: " + ", ".join(leaked)
        )


def _reject_source_dependency_leakage(
    units: Sequence[Mapping[str, object]],
    *,
    projections: Sequence[Mapping[str, object]],
    exemptions: Sequence[Mapping[str, object]],
) -> None:
    protected_hashes: set[str] = set()
    for projection in projections:
        protected_hashes.update(
            str(projection[field])
            for field in (
                "qualified_label_release_sha256",
                "qualified_reference_receipt_sha256",
                "human_role_package_sha256",
                "reviewer_calibration_receipt_sha256",
                "labelset_manifest_sha256",
                "labelset_validation_receipt_sha256",
                "label_content_sha256",
                "labelset_purpose_binding_sha256",
                "raster_lineage_sha256",
                "agreement_evidence_sha256",
                "consensus_receipt_sha256",
                "adjudication_import_receipt_sha256",
            )
        )
    exemption_by_id = {str(item["exemption_id"]): item for item in exemptions}
    occurrences: dict[str, list[tuple[str, Mapping[str, object]]]] = {}
    used_exemptions: set[str] = set()
    for unit in units:
        role = str(unit["role"])
        for dependency in unit["source_dependencies"]:
            artifact_sha = str(dependency["artifact_sha256"])
            if artifact_sha in protected_hashes:
                raise MultiEventPartitionError(
                    "A protected label/reference/reviewer/adjudication artifact "
                    "was supplied as a model feature dependency."
                )
            occurrences.setdefault(artifact_sha, []).append((role, dependency))
            exemption_id = dependency["static_context_exemption_id"]
            if exemption_id is not None:
                used_exemptions.add(str(exemption_id))
    if used_exemptions != set(exemption_by_id):
        raise MultiEventPartitionError(
            "Static context exemptions must be used exactly by manifest sources."
        )

    for artifact_sha, rows in occurrences.items():
        roles = {role for role, _ in rows}
        if len(roles) <= 1:
            continue
        exemption_ids = {
            str(dependency["static_context_exemption_id"])
            for _, dependency in rows
            if dependency["static_context_exemption_id"] is not None
        }
        allowed = len(exemption_ids) == 1 and all(
            dependency["dependency_kind"] == "static_non_target_context"
            and dependency["target_independent"] is True
            and dependency["temporal_scope"] == "static"
            for _, dependency in rows
        )
        if not allowed:
            raise MultiEventPartitionError(
                "A non-exempt source artifact crosses partition roles: " + artifact_sha
            )
        exemption_id = next(iter(exemption_ids))
        exemption = exemption_by_id.get(exemption_id)
        if (
            exemption is None
            or exemption["artifact_sha256"] != artifact_sha
            or exemption["target_independent"] is not True
            or exemption["fitted_from_partition_data"] is not False
        ):
            raise MultiEventPartitionError(
                "Shared static context does not match its non-target exemption."
            )


def _validate_projection_coverage(
    units: Sequence[Mapping[str, object]],
    *,
    projections: Sequence[Mapping[str, object]],
) -> None:
    unit_identities = {
        (
            str(unit["event_id"]),
            str(unit["hydrologic_episode_id"]),
            str(unit["study_area_id"]),
        )
        for unit in units
    }
    projection_identities = {
        _projection_identity(projection) for projection in projections
    }
    if unit_identities != projection_identities:
        raise MultiEventPartitionError(
            "Partition units must use every and only supplied release projection."
        )
    role_by_event: dict[str, str] = {}
    role_by_episode: dict[str, str] = {}
    for unit in units:
        role = str(unit["role"])
        event_id = str(unit["event_id"])
        episode_id = str(unit["hydrologic_episode_id"])
        if event_id in role_by_event and role_by_event[event_id] != role:
            raise MultiEventPartitionError(
                "An entire event must remain in exactly one partition role."
            )
        if episode_id in role_by_episode and role_by_episode[episode_id] != role:
            raise MultiEventPartitionError(
                "An entire hydrologic episode must remain in one partition role."
            )
        role_by_event[event_id] = role
        role_by_episode[episode_id] = role


def _validate_heterogeneity(
    units: Sequence[Mapping[str, object]],
    *,
    partition_mode: str,
) -> None:
    if partition_mode == "fixture_demo":
        return
    event_ids = {str(unit["event_id"]) for unit in units}
    if len(event_ids) < 5:
        raise MultiEventPartitionError(
            "Candidate/production partition requires at least five events."
        )
    for field in STRATIFICATION_VALUES:
        observed = {str(unit["strata"][field]) for unit in units}
        if len(observed) < 2:
            raise MultiEventPartitionError(
                f"Candidate/production events lack heterogeneity for {field}."
            )
    signatures_by_event: dict[str, set[tuple[str, ...]]] = {}
    for unit in units:
        signature = tuple(str(unit["strata"][field]) for field in STRATIFICATION_VALUES)
        signatures_by_event.setdefault(str(unit["event_id"]), set()).add(signature)
    event_signatures = {
        tuple(sorted(signatures)) for signatures in signatures_by_event.values()
    }
    if len(event_signatures) < 5:
        raise MultiEventPartitionError(
            "Five events must not collapse to duplicate stratification profiles."
        )


def _validate_schema_binding(
    value: object,
    label: str,
    *,
    include_features: bool,
) -> dict[str, object]:
    schema = _mapping_copy(value, label)
    expected = {"schema_id", "schema_sha256"}
    if include_features:
        expected.add("feature_names")
    _exact_fields(schema, expected, label)
    normalized: dict[str, object] = {
        "schema_id": _safe_id(schema["schema_id"], f"{label} schema_id"),
        "schema_sha256": _sha256(schema["schema_sha256"], f"{label} schema_sha256"),
    }
    if include_features:
        normalized["feature_names"] = _feature_names(schema["feature_names"])
    if schema != normalized:
        raise MultiEventPartitionError(f"{label} is not canonical.")
    return schema


def _validate_algorithm(value: object) -> dict[str, object]:
    algorithm = _mapping_copy(value, "partition_algorithm")
    _exact_fields(
        algorithm,
        {
            "algorithm_id",
            "algorithm_version",
            "implementation_code_sha256",
            "random_seed",
            "seed_declared_at_utc",
            "target_statistics_used",
            "labels_inspected_before_freeze",
            "post_label_seed_selection",
            "algorithm_locked",
        },
        "partition_algorithm",
    )
    _safe_id(algorithm["algorithm_id"], "partition algorithm_id")
    _text(algorithm["algorithm_version"], "partition algorithm_version")
    _sha256(
        algorithm["implementation_code_sha256"],
        "partition implementation_code_sha256",
    )
    _seed(algorithm["random_seed"])
    _timestamp(algorithm["seed_declared_at_utc"], "seed_declared_at_utc")
    if (
        algorithm["target_statistics_used"] is not False
        or algorithm["labels_inspected_before_freeze"] is not False
        or algorithm["post_label_seed_selection"] is not False
        or algorithm["algorithm_locked"] is not True
    ):
        raise MultiEventPartitionError(
            "Partition algorithm was not predeclared independently of labels."
        )
    return algorithm


def _validate_preprocessing(value: object) -> dict[str, object]:
    preprocessing = _mapping_copy(value, "preprocessing_contract")
    _exact_fields(
        preprocessing,
        {
            "plan_sha256",
            "fit_scope",
            "fit_partition_roles",
            "full_corpus_fitted",
            "model_probability_calibration_used_for_fit",
            "development_used_for_fit",
            "final_holdout_used_for_fit",
            "fitting_not_before_utc",
        },
        "preprocessing_contract",
    )
    _sha256(preprocessing["plan_sha256"], "preprocessing plan_sha256")
    _timestamp(
        preprocessing["fitting_not_before_utc"],
        "preprocessing fitting_not_before_utc",
    )
    if (
        preprocessing["fit_scope"] != "training_only"
        or preprocessing["fit_partition_roles"] != ["training"]
        or preprocessing["full_corpus_fitted"] is not False
        or preprocessing["model_probability_calibration_used_for_fit"] is not False
        or preprocessing["development_used_for_fit"] is not False
        or preprocessing["final_holdout_used_for_fit"] is not False
    ):
        raise MultiEventPartitionError(
            "Preprocessing must be unfitted at seal and fit on training only."
        )
    return preprocessing


def _validate_holdout_contract(value: object) -> None:
    holdout = _mapping_copy(value, "final_holdout_contract")
    _exact_fields(
        holdout,
        {
            "status",
            "synthetic_fixture_only",
            "custody_authority_verified",
            "confers_custody_authority",
            "holdout_closed",
            "holdout_opened",
            "reference_opened",
            "used_for_partition_selection",
            "used_for_feature_selection",
            "used_for_preprocessing_fit",
            "used_for_probability_calibration",
            "used_for_threshold_selection",
            "used_for_model_selection",
            "evaluation_count",
            "opened_at_utc",
            "custodian_receipt_sha256",
        },
        "final_holdout_contract",
    )
    _sha256(
        holdout["custodian_receipt_sha256"],
        "holdout custodian_receipt_sha256",
    )
    if (
        holdout["status"] != "synthetic_fixture_closed_non_authoritative"
        or holdout["synthetic_fixture_only"] is not True
        or holdout["custody_authority_verified"] is not False
        or holdout["confers_custody_authority"] is not False
        or holdout["holdout_closed"] is not True
        or holdout["holdout_opened"] is not False
        or holdout["reference_opened"] is not False
        or holdout["used_for_partition_selection"] is not False
        or holdout["used_for_feature_selection"] is not False
        or holdout["used_for_preprocessing_fit"] is not False
        or holdout["used_for_probability_calibration"] is not False
        or holdout["used_for_threshold_selection"] is not False
        or holdout["used_for_model_selection"] is not False
        or holdout["evaluation_count"] != 0
        or holdout["opened_at_utc"] is not None
    ):
        raise MultiEventPartitionError(
            "Final holdout fixture must remain explicitly non-authoritative, "
            "closed, unused, and unopened."
        )


def _strata(value: object) -> dict[str, str]:
    raw = _mapping_copy(value, "strata")
    _exact_fields(raw, set(STRATIFICATION_VALUES), "strata")
    normalized: dict[str, str] = {}
    for field, allowed in STRATIFICATION_VALUES.items():
        stratum = _text(raw[field], field)
        if stratum not in allowed:
            raise MultiEventPartitionError(
                f"{field} must be one of: {', '.join(sorted(allowed))}."
            )
        normalized[field] = stratum
    return normalized


def _feature_names(value: object) -> list[str]:
    names = _text_array(value, "feature_names", minimum=1)
    if names != sorted(names):
        raise MultiEventPartitionError(
            "Feature names must be sorted deterministically."
        )
    for name in names:
        if _FEATURE_RE.fullmatch(name) is None:
            raise MultiEventPartitionError(
                f"Feature name is not a stable identifier: {name!r}."
            )
        _reject_prohibited_feature_identifier(name, "feature name")
    return names


def _reject_prohibited_feature_identifier(value: str, label: str) -> None:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if any(token in normalized for token in PROHIBITED_FEATURE_TOKENS):
        raise MultiEventPartitionError(
            f"{label} appears to contain target/reviewer/reference evidence."
        )


def _bounds(value: object, label: str) -> list[float]:
    raw = _sequence(value, label)
    if len(raw) != 4:
        raise MultiEventPartitionError(
            f"{label} must contain [min_x, min_y, max_x, max_y]."
        )
    result = [
        _finite_number(item, f"{label}[{index}]") for index, item in enumerate(raw)
    ]
    if result[0] >= result[2] or result[1] >= result[3]:
        raise MultiEventPartitionError(f"{label} must have strictly increasing axes.")
    return result


def _validate_halo_bounds(
    core: Sequence[float],
    buffered: Sequence[float],
    *,
    context_halo_m: float,
) -> None:
    if (
        buffered[0] > core[0] - context_halo_m
        or buffered[1] > core[1] - context_halo_m
        or buffered[2] < core[2] + context_halo_m
        or buffered[3] < core[3] + context_halo_m
    ):
        raise MultiEventPartitionError(
            "Buffered bounds do not cover the declared context halo."
        )


def _bounds_overlap_or_touch(
    left: object,
    right: object,
) -> bool:
    left_box = _bounds(left, "left buffered_bounds")
    right_box = _bounds(right, "right buffered_bounds")
    return not (
        left_box[2] < right_box[0]
        or right_box[2] < left_box[0]
        or left_box[3] < right_box[1]
        or right_box[3] < left_box[1]
    )


def _projected_crs(value: object) -> str:
    crs = _text(value, "bounds_crs").upper()
    if _CRS_RE.fullmatch(crs) is None or crs in {
        "EPSG:4326",
        "EPSG:4269",
    }:
        raise MultiEventPartitionError(
            "Buffered bounds require a projected EPSG CRS, not degrees."
        )
    return crs


def _partition_mode(value: object) -> str:
    mode = _text(value, "dataset_mode")
    if mode not in PARTITION_MODES:
        raise MultiEventPartitionError("Unsupported partition dataset_mode.")
    return mode


def _require_fixture_only_partition_mode(mode: str) -> None:
    if mode != "fixture_demo":
        raise MultiEventPartitionError(
            "Candidate/production partition v1 is unavailable until actual "
            "qualified-label release bundles and an attributable signed "
            "holdout-custody receipt are canonically validated."
        )


def _release_mode(value: object) -> str:
    mode = _text(value, "qualified release dataset_mode")
    if mode not in {"fixture_demo", "candidate", "official_input"}:
        raise MultiEventPartitionError("Unsupported qualified-release dataset_mode.")
    return mode


def _role(value: object) -> str:
    role = _text(value, "partition role")
    if role not in PARTITION_ROLES:
        raise MultiEventPartitionError("Unsupported partition role.")
    return role


def _seed(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 2**63 - 1
    ):
        raise MultiEventPartitionError(
            "random_seed must be a non-negative signed 64-bit integer."
        )
    return value


def _false_safety_fields() -> dict[str, bool]:
    return {field: False for field in DOWNSTREAM_SAFETY_FIELDS}


def _require_false_safety(
    value: Mapping[str, object],
    label: str,
) -> None:
    unsafe = [
        field for field in DOWNSTREAM_SAFETY_FIELDS if value.get(field) is not False
    ]
    if unsafe:
        raise MultiEventPartitionError(
            f"{label} safety fields must remain false: " + ", ".join(unsafe)
        )


def _verify_self_hash(
    value: Mapping[str, object],
    field: str,
    label: str,
) -> str:
    digest = _sha256(value.get(field), f"{label} {field}")
    unsigned = dict(value)
    unsigned.pop(field, None)
    if canonical_sha256(unsigned) != digest:
        raise MultiEventPartitionError(
            f"{label} {field} does not match canonical content."
        )
    return digest


def _mapping_copy(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise MultiEventPartitionError(f"{label} must be a JSON object.")
    try:
        copied = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise MultiEventPartitionError(
            f"{label} must contain finite strict-JSON values."
        ) from exc
    if not isinstance(copied, dict):
        raise MultiEventPartitionError(f"{label} must be a JSON object.")
    _reject_private_paths(copied, field=label)
    return copied


def _reject_private_paths(value: object, *, field: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_private_paths(item, field=f"{field}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_private_paths(item, field=f"{field}[{index}]")
        return
    if isinstance(value, str) and _PRIVATE_PATH_RE.search(value):
        raise MultiEventPartitionError(f"{field} contains a private absolute path.")


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise MultiEventPartitionError(f"{label} must be an array.")
    return list(value)


def _exact_fields(
    value: Mapping[str, object],
    expected: set[str],
    label: str,
) -> None:
    actual = set(value)
    if actual != expected:
        raise MultiEventPartitionError(
            f"{label} fields differ; "
            f"missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}."
        )


def _safe_id(value: object, label: str) -> str:
    text = _text(value, label)
    if _SAFE_ID_RE.fullmatch(text) is None:
        raise MultiEventPartitionError(f"{label} must be a stable safe identifier.")
    return text


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MultiEventPartitionError(f"{label} must be nonblank text.")
    return value.strip()


def _text_array(
    value: object,
    label: str,
    *,
    minimum: int = 0,
) -> list[str]:
    raw = _sequence(value, label)
    result = [_text(item, label) for item in raw]
    if len(result) < minimum:
        raise MultiEventPartitionError(f"{label} requires at least {minimum} item(s).")
    if len(result) != len(set(result)):
        raise MultiEventPartitionError(f"{label} contains duplicates.")
    return result


def _assumptions(value: object) -> list[str]:
    return _text_array(value, "assumptions", minimum=1)


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise MultiEventPartitionError(f"{label} must be a SHA-256 string.")
    digest = value.strip().lower()
    if _SHA256_RE.fullmatch(digest) is None:
        raise MultiEventPartitionError(f"{label} must contain 64 hexadecimal digits.")
    return digest


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MultiEventPartitionError(f"{label} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise MultiEventPartitionError(f"{label} must be finite.")
    return result


def _positive_number(value: object, label: str) -> float:
    result = _finite_number(value, label)
    if result <= 0:
        raise MultiEventPartitionError(f"{label} must be positive.")
    return result


def _timestamp(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise MultiEventPartitionError(
                f"{label} must be an ISO-8601 timestamp."
            ) from exc
    else:
        raise MultiEventPartitionError(f"{label} must be an ISO-8601 timestamp.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MultiEventPartitionError(f"{label} must include a UTC offset.")
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
