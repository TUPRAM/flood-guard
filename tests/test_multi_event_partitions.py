from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any

import pytest

from floodguard.multi_event_partitions import (
    DOWNSTREAM_SAFETY_FIELDS,
    MANIFEST_SCHEMA,
    PARTITION_ROLES,
    QUALIFIED_RELEASE_PROJECTION_SCHEMA,
    MultiEventPartitionError,
    build_multi_event_partition_manifest,
    canonical_sha256,
    validate_multi_event_partition_manifest,
)


ROLES = [
    "training",
    "training",
    "model_probability_calibration",
    "development",
    "final_holdout",
]
STRATA = [
    {
        "settlement_stratum": "urban",
        "terrain_stratum": "flat",
        "flood_mechanism_stratum": "riverine",
        "permanent_water_stratum": "present",
        "vegetation_stratum": "dense",
        "radar_quality_stratum": "high",
    },
    {
        "settlement_stratum": "rural",
        "terrain_stratum": "steep",
        "flood_mechanism_stratum": "flash",
        "permanent_water_stratum": "absent",
        "vegetation_stratum": "sparse",
        "radar_quality_stratum": "medium",
    },
    {
        "settlement_stratum": "mixed",
        "terrain_stratum": "rolling",
        "flood_mechanism_stratum": "urban_pluvial",
        "permanent_water_stratum": "mixed",
        "vegetation_stratum": "mixed",
        "radar_quality_stratum": "low",
    },
    {
        "settlement_stratum": "urban",
        "terrain_stratum": "steep",
        "flood_mechanism_stratum": "coastal",
        "permanent_water_stratum": "absent",
        "vegetation_stratum": "dense",
        "radar_quality_stratum": "mixed",
    },
    {
        "settlement_stratum": "rural",
        "terrain_stratum": "flat",
        "flood_mechanism_stratum": "mixed",
        "permanent_water_stratum": "present",
        "vegetation_stratum": "sparse",
        "radar_quality_stratum": "high",
    },
]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = deepcopy(value)
    result.pop(field, None)
    result[field] = canonical_sha256(result)
    return result


def _projection(
    index: int,
    role: str,
    *,
    partition_mode: str = "fixture_demo",
) -> dict[str, Any]:
    release_mode = {
        "fixture_demo": "fixture_demo",
        "candidate": "candidate",
        "production": "official_input",
    }[partition_mode]
    return _seal(
        {
            "artifact_schema": QUALIFIED_RELEASE_PROJECTION_SCHEMA,
            "projection_id": f"PROJECTION-{index:03d}",
            "validation_status": "passed",
            "validation_method": (
                "floodguard.label_factory.qualified_label_release."
                "validate_qualified_label_release"
            ),
            "validator_code_sha256": _digest("validator-code"),
            "source_artifact_schema": "floodguard.qualified_label_release.v1",
            "release_id": f"RELEASE-{index:03d}",
            "dataset_mode": release_mode,
            "synthetic_fixture_only": partition_mode == "fixture_demo",
            "confers_authority": False,
            "event_id": f"TEST-EVENT-{index:03d}",
            "hydrologic_episode_id": f"TEST-EPISODE-{index:03d}",
            "study_area_id": f"TEST-STUDY-{index:03d}",
            "purpose": (
                "model_final_evaluation"
                if role == "final_holdout"
                else "flood_model_training_labels"
            ),
            "qualified_label_release_sha256": _digest(
                f"qualified-label-release-{index}"
            ),
            "qualified_reference_receipt_sha256": _digest(
                f"qualified-reference-{index}"
            ),
            "human_role_package_sha256": _digest(f"human-role-package-{index}"),
            "reviewer_calibration_receipt_sha256": _digest(
                f"reviewer-calibration-{index}"
            ),
            "labelset_manifest_sha256": _digest(f"labelset-manifest-{index}"),
            "labelset_validation_receipt_sha256": _digest(
                f"labelset-validation-{index}"
            ),
            "label_content_sha256": _digest(f"label-content-{index}"),
            "labelset_purpose_binding_sha256": _digest(
                f"labelset-purpose-binding-{index}"
            ),
            "raster_lineage_sha256": _digest(f"raster-lineage-{index}"),
            "query_region_ids": [f"QUERY-{index:03d}"],
            "agreement_evidence_sha256": _digest(f"agreement-{index}"),
            "consensus_receipt_sha256": _digest(f"consensus-{index}"),
            "adjudication_import_receipt_sha256": _digest(
                f"adjudication-import-{index}"
            ),
            "release_created_at_utc": f"2024-02-{10 + index:02d}T00:00:00Z",
            "validated_at_utc": f"2024-02-{20 + index:02d}T00:00:00Z",
            "processing_allowed": True,
            "eligible_for_flood_model_training": role != "final_holdout",
            "eligible_for_model_evaluation": role == "final_holdout",
            **{field: False for field in DOWNSTREAM_SAFETY_FIELDS},
            "assumptions": [
                "Synthetic test projection; it is not real event evidence."
            ],
        },
        "projection_sha256",
    )


def _exemption() -> dict[str, Any]:
    return {
        "exemption_id": "STATIC-DEM-EXEMPTION",
        "dependency_id": "STATIC-DEM-CONTEXT",
        "artifact_sha256": _digest("static-dem"),
        "rationale": (
            "A versioned terrain raster is target-independent static context."
        ),
        "target_independent": True,
        "temporal_scope": "static",
        "fitted_from_partition_data": False,
    }


def _unit(
    index: int,
    role: str,
    projection: dict[str, Any],
) -> dict[str, Any]:
    minimum_x = float(index * 1000)
    core = [minimum_x, 0.0, minimum_x + 100.0, 100.0]
    buffered = [minimum_x - 50.0, -50.0, minimum_x + 150.0, 150.0]
    return {
        "partition_unit_id": f"UNIT-{index:03d}",
        "role": role,
        "event_id": projection["event_id"],
        "hydrologic_episode_id": projection["hydrologic_episode_id"],
        "study_area_id": projection["study_area_id"],
        "qualified_label_release_sha256": projection["qualified_label_release_sha256"],
        "spatial_group_id": f"SPATIAL-{index:03d}",
        "overlap_group_id": f"OVERLAP-{index:03d}",
        "core_bounds": core,
        "buffered_bounds": buffered,
        "bounds_crs": "EPSG:32647",
        "bounds_units": "metre",
        "source_dependencies": [
            {
                "dependency_id": f"SAR-SOURCE-{index:03d}",
                "artifact_sha256": _digest(f"event-source-{index}"),
                "dependency_kind": "event_predictor",
                "event_id": projection["event_id"],
                "target_independent": True,
                "temporal_scope": "event_specific",
                "static_context_exemption_id": None,
            },
            {
                "dependency_id": "STATIC-DEM-CONTEXT",
                "artifact_sha256": _digest("static-dem"),
                "dependency_kind": "static_non_target_context",
                "event_id": None,
                "target_independent": True,
                "temporal_scope": "static",
                "static_context_exemption_id": "STATIC-DEM-EXEMPTION",
            },
        ],
        "target_dependencies": {
            "qualified_label_release_sha256": projection[
                "qualified_label_release_sha256"
            ],
            "label_content_sha256": projection["label_content_sha256"],
        },
        "strata": deepcopy(STRATA[index]),
    }


def _inputs(
    *,
    partition_mode: str = "fixture_demo",
    event_count: int = 4,
) -> dict[str, Any]:
    roles = ROLES[:event_count]
    if event_count == 4:
        roles = [
            "training",
            "model_probability_calibration",
            "development",
            "final_holdout",
        ]
    projections = [
        _projection(index, role, partition_mode=partition_mode)
        for index, role in enumerate(roles)
    ]
    units = [_unit(index, role, projections[index]) for index, role in enumerate(roles)]
    return {
        "manifest_id": "MULTI-EVENT-PARTITION-001",
        "dataset_mode": partition_mode,
        "partition_units": units,
        "qualified_release_projections": projections,
        "static_context_exemptions": [_exemption()],
        "grid_schema_id": "CANONICAL-GRID-V1",
        "grid_schema_sha256": _digest("grid-schema"),
        "feature_schema_id": "SAR-FEATURES-V1",
        "feature_schema_sha256": _digest("feature-schema"),
        "feature_names": [
            "dem_slope",
            "permanent_water_context",
            "sar_vh_delta",
            "sar_vv_delta",
        ],
        "partition_algorithm_id": "GROUPED-EVENT-BLOCK-V1",
        "partition_algorithm_version": "1.0.0",
        "algorithm_code_sha256": _digest("partition-code"),
        "random_seed": 20240723,
        "seed_declared_at_utc": "2024-01-01T00:00:00Z",
        "preprocessing_plan_sha256": _digest("preprocessing-plan"),
        "context_halo_m": 50.0,
        "holdout_custodian_receipt_sha256": _digest("holdout-custodian"),
        "created_at_utc": "2024-03-01T00:00:00Z",
        "fitting_not_before_utc": "2024-04-01T00:00:00Z",
        "assumptions": [
            "Unit-test identities are synthetic and make no Mae Sai claim."
        ],
    }


def _build(inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_multi_event_partition_manifest(**(inputs or _inputs()))


def _validate(
    manifest: dict[str, Any],
    projections: list[dict[str, Any]],
) -> dict[str, Any]:
    return validate_multi_event_partition_manifest(
        manifest,
        qualified_release_projections=projections,
    )


def test_fixture_manifest_seals_four_roles_without_claiming_authority() -> None:
    manifest = _build()

    assert manifest["artifact_schema"] == MANIFEST_SCHEMA
    assert manifest["manifest_status"] == "sealed"
    assert manifest["synthetic_fixture_only"] is True
    assert manifest["confers_authority"] is False
    assert set(manifest["role_partition_sha256"]) == set(PARTITION_ROLES)
    assert manifest["partition_unit_count_by_role"] == {
        "training": 1,
        "model_probability_calibration": 1,
        "development": 1,
        "final_holdout": 1,
    }
    assert manifest["final_holdout_contract"]["holdout_closed"] is True
    assert (
        manifest["final_holdout_contract"]["status"]
        == "synthetic_fixture_closed_non_authoritative"
    )
    assert manifest["final_holdout_contract"]["custody_authority_verified"] is False
    assert manifest["final_holdout_contract"]["evaluation_count"] == 0
    assert all(manifest[field] is False for field in DOWNSTREAM_SAFETY_FIELDS)


def test_fixture_manifest_is_explicitly_synthetic_and_non_authoritative() -> None:
    manifest = _build(_inputs(partition_mode="fixture_demo", event_count=4))

    assert manifest["dataset_mode"] == "fixture_demo"
    assert manifest["synthetic_fixture_only"] is True
    assert manifest["confers_authority"] is False
    assert len(manifest["qualified_label_release_bindings"]) == 4


@pytest.mark.parametrize("mode", ["candidate", "production"])
def test_nonfixture_partition_sealing_is_explicitly_unavailable(mode: str) -> None:
    with pytest.raises(
        MultiEventPartitionError,
        match="signed holdout-custody",
    ):
        _build(_inputs(partition_mode=mode, event_count=5))


def test_static_non_target_context_can_be_shared_with_exact_exemption() -> None:
    manifest = _build()
    static_hashes = {
        dependency["artifact_sha256"]
        for unit in manifest["partition_units"]
        for dependency in unit["source_dependencies"]
        if dependency["dependency_kind"] == "static_non_target_context"
    }

    assert static_hashes == {_digest("static-dem")}


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("spatial_group_id", "spatial_group_id leakage"),
        ("overlap_group_id", "overlap_group_id leakage"),
    ],
)
def test_cross_role_group_leakage_is_rejected(
    field: str,
    expected: str,
) -> None:
    inputs = _inputs()
    inputs["partition_units"][3][field] = inputs["partition_units"][0][field]

    with pytest.raises(MultiEventPartitionError, match=expected):
        _build(inputs)


def test_event_leakage_is_rejected_even_with_matching_release_lineage() -> None:
    inputs = _inputs()
    source = inputs["partition_units"][0]
    leaked = inputs["partition_units"][2]
    for field in (
        "event_id",
        "hydrologic_episode_id",
        "study_area_id",
        "qualified_label_release_sha256",
    ):
        leaked[field] = source[field]
    leaked["target_dependencies"] = deepcopy(source["target_dependencies"])
    leaked["source_dependencies"][0]["event_id"] = source["event_id"]

    with pytest.raises(MultiEventPartitionError, match="event_id leakage"):
        _build(inputs)


def test_hydrologic_episode_leakage_is_rejected() -> None:
    inputs = _inputs()
    episode = inputs["qualified_release_projections"][0]["hydrologic_episode_id"]
    inputs["qualified_release_projections"][3]["hydrologic_episode_id"] = episode
    inputs["qualified_release_projections"][3] = _seal(
        inputs["qualified_release_projections"][3], "projection_sha256"
    )
    inputs["partition_units"][3]["hydrologic_episode_id"] = episode

    with pytest.raises(MultiEventPartitionError, match="hydrologic_episode_id leakage"):
        _build(inputs)


def test_buffer_and_context_halo_leakage_is_rejected() -> None:
    inputs = _inputs()
    inputs["partition_units"][3]["core_bounds"] = [25.0, 0.0, 125.0, 100.0]
    inputs["partition_units"][3]["buffered_bounds"] = [
        -25.0,
        -50.0,
        175.0,
        150.0,
    ]

    with pytest.raises(MultiEventPartitionError, match="Buffered bounds"):
        _build(inputs)


def test_insufficient_buffer_for_context_halo_is_rejected() -> None:
    inputs = _inputs()
    inputs["partition_units"][0]["buffered_bounds"] = deepcopy(
        inputs["partition_units"][0]["core_bounds"]
    )

    with pytest.raises(MultiEventPartitionError, match="context halo"):
        _build(inputs)


def test_geographic_degree_crs_is_rejected_for_metre_halo() -> None:
    inputs = _inputs()
    inputs["partition_units"][0]["bounds_crs"] = "EPSG:4326"

    with pytest.raises(MultiEventPartitionError, match="projected"):
        _build(inputs)


def test_mixed_projected_crs_is_rejected_before_overlap_comparison() -> None:
    inputs = _inputs()
    inputs["partition_units"][3]["bounds_crs"] = "EPSG:32648"

    with pytest.raises(MultiEventPartitionError, match="Mixed bounds CRS"):
        _build(inputs)


def test_non_exempt_event_source_cannot_cross_roles() -> None:
    inputs = _inputs()
    inputs["partition_units"][3]["source_dependencies"][0]["artifact_sha256"] = inputs[
        "partition_units"
    ][0]["source_dependencies"][0]["artifact_sha256"]

    with pytest.raises(MultiEventPartitionError, match="non-exempt source"):
        _build(inputs)


@pytest.mark.parametrize(
    "field",
    [
        "label_content_sha256",
        "qualified_reference_receipt_sha256",
        "raster_lineage_sha256",
        "agreement_evidence_sha256",
    ],
)
def test_protected_target_lineage_cannot_be_reused_across_roles(
    field: str,
) -> None:
    inputs = _inputs()
    source = inputs["qualified_release_projections"][0]
    target = inputs["qualified_release_projections"][2]
    target[field] = source[field]
    inputs["qualified_release_projections"][2] = _seal(
        target,
        "projection_sha256",
    )
    if field == "label_content_sha256":
        inputs["partition_units"][2]["target_dependencies"]["label_content_sha256"] = (
            source[field]
        )

    with pytest.raises(MultiEventPartitionError, match="lineage crosses"):
        _build(inputs)


def test_query_region_cannot_be_reused_across_roles() -> None:
    inputs = _inputs()
    target = inputs["qualified_release_projections"][2]
    target["query_region_ids"] = deepcopy(
        inputs["qualified_release_projections"][0]["query_region_ids"]
    )
    inputs["qualified_release_projections"][2] = _seal(
        target,
        "projection_sha256",
    )

    with pytest.raises(MultiEventPartitionError, match="query_region_id"):
        _build(inputs)


@pytest.mark.parametrize(
    "protected_field",
    [
        "reviewer_calibration_receipt_sha256",
        "label_content_sha256",
        "qualified_reference_receipt_sha256",
        "adjudication_import_receipt_sha256",
    ],
)
def test_protected_human_or_target_artifacts_cannot_be_features(
    protected_field: str,
) -> None:
    inputs = _inputs()
    inputs["partition_units"][0]["source_dependencies"][0]["artifact_sha256"] = inputs[
        "qualified_release_projections"
    ][0][protected_field]

    with pytest.raises(MultiEventPartitionError, match="protected"):
        _build(inputs)


@pytest.mark.parametrize(
    "identifier",
    [
        "REVIEWER-CALIBRATION-ARTIFACT",
        "ADJUDICATION-OUTCOME",
        "QUALIFIED-REFERENCE-MASK",
        "TARGET-CLASS-CACHE",
    ],
)
def test_feature_dependency_ids_cannot_disguise_protected_evidence(
    identifier: str,
) -> None:
    inputs = _inputs()
    inputs["partition_units"][0]["source_dependencies"][0]["dependency_id"] = identifier

    with pytest.raises(MultiEventPartitionError, match="target/reviewer"):
        _build(inputs)


def test_feature_schema_cannot_name_a_target_label() -> None:
    inputs = _inputs()
    inputs["feature_names"] = [
        "dem_slope",
        "sar_vv_delta",
        "target_label",
    ]

    with pytest.raises(MultiEventPartitionError, match="target/reviewer"):
        _build(inputs)


def test_candidate_manifest_cannot_be_unblocked_by_fabricated_projections() -> None:
    inputs = _inputs(partition_mode="candidate", event_count=5)
    assert all(
        projection["validation_status"] == "passed"
        for projection in inputs["qualified_release_projections"]
    )
    with pytest.raises(MultiEventPartitionError, match="unavailable"):
        _build(inputs)


def test_all_four_roles_must_be_nonempty() -> None:
    inputs = _inputs()
    inputs["partition_units"] = [
        unit
        for unit in inputs["partition_units"]
        if unit["role"] != "model_probability_calibration"
    ]

    with pytest.raises(MultiEventPartitionError, match="nonempty"):
        _build(inputs)


def test_duplicate_partition_units_are_rejected() -> None:
    inputs = _inputs()
    inputs["partition_units"][3]["partition_unit_id"] = inputs["partition_units"][0][
        "partition_unit_id"
    ]

    with pytest.raises(MultiEventPartitionError, match="duplicates"):
        _build(inputs)


def test_final_holdout_requires_evaluation_purpose_release() -> None:
    inputs = _inputs()
    projection = inputs["qualified_release_projections"][3]
    projection["purpose"] = "flood_model_training_labels"
    projection["eligible_for_flood_model_training"] = True
    projection["eligible_for_model_evaluation"] = False
    inputs["qualified_release_projections"][3] = _seal(projection, "projection_sha256")

    with pytest.raises(MultiEventPartitionError, match="wrong purpose"):
        _build(inputs)


def test_release_hash_substitution_is_rejected() -> None:
    inputs = _inputs()
    inputs["partition_units"][0]["qualified_label_release_sha256"] = _digest(
        "substituted-release"
    )

    with pytest.raises(MultiEventPartitionError, match="substituted"):
        _build(inputs)


def test_candidate_rejects_even_validly_hashed_caller_authored_projections() -> None:
    inputs = _inputs(partition_mode="candidate", event_count=5)
    with pytest.raises(MultiEventPartitionError, match="unavailable"):
        _build(inputs)


def test_fixture_holdout_hash_never_claims_signed_custody_authority() -> None:
    inputs = _inputs()
    inputs["holdout_custodian_receipt_sha256"] = _digest("caller-invented-hash")
    manifest = _build(inputs)
    contract = manifest["final_holdout_contract"]

    assert contract["status"] == "synthetic_fixture_closed_non_authoritative"
    assert contract["custody_authority_verified"] is False
    assert contract["confers_custody_authority"] is False


def test_private_absolute_paths_are_rejected_recursively() -> None:
    inputs = _inputs()
    inputs["qualified_release_projections"][0]["assumptions"].append(
        r"C:\Users\reviewer\private\receipt.json"
    )
    inputs["qualified_release_projections"][0] = _seal(
        inputs["qualified_release_projections"][0],
        "projection_sha256",
    )

    with pytest.raises(MultiEventPartitionError, match="private absolute path"):
        _build(inputs)


def test_failed_projection_cannot_enter_partition() -> None:
    inputs = _inputs()
    projection = inputs["qualified_release_projections"][0]
    projection["validation_status"] = "failed"
    inputs["qualified_release_projections"][0] = _seal(projection, "projection_sha256")

    with pytest.raises(MultiEventPartitionError, match="passed validation"):
        _build(inputs)


def test_seed_must_be_declared_before_label_release() -> None:
    inputs = _inputs()
    inputs["seed_declared_at_utc"] = "2024-02-15T00:00:00Z"

    with pytest.raises(MultiEventPartitionError, match="predeclared"):
        _build(inputs)


def test_manifest_must_be_created_before_fitting() -> None:
    inputs = _inputs()
    inputs["fitting_not_before_utc"] = inputs["created_at_utc"]

    with pytest.raises(MultiEventPartitionError, match="before any fitting"):
        _build(inputs)


@pytest.mark.parametrize(
    "field",
    [
        "holdout_opened",
        "reference_opened",
        "used_for_partition_selection",
        "used_for_feature_selection",
        "used_for_preprocessing_fit",
        "used_for_probability_calibration",
        "used_for_threshold_selection",
        "used_for_model_selection",
    ],
)
def test_rehashed_manifest_cannot_open_or_use_final_holdout(
    field: str,
) -> None:
    inputs = _inputs()
    manifest = _build(inputs)
    manifest["final_holdout_contract"][field] = True
    if field == "holdout_opened":
        manifest["final_holdout_contract"]["holdout_closed"] = False
    manifest = _seal(manifest, "manifest_sha256")

    with pytest.raises(MultiEventPartitionError, match="Final holdout"):
        _validate(manifest, inputs["qualified_release_projections"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fit_scope", "full_corpus"),
        ("full_corpus_fitted", True),
        ("model_probability_calibration_used_for_fit", True),
        ("development_used_for_fit", True),
        ("final_holdout_used_for_fit", True),
    ],
)
def test_rehashed_manifest_rejects_full_corpus_or_nontraining_preprocessing(
    field: str,
    value: Any,
) -> None:
    inputs = _inputs()
    manifest = _build(inputs)
    manifest["preprocessing_contract"][field] = value
    manifest = _seal(manifest, "manifest_sha256")

    with pytest.raises(MultiEventPartitionError, match="training only"):
        _validate(manifest, inputs["qualified_release_projections"])


def test_rehashed_manifest_cannot_enable_fpps_or_decision_authority() -> None:
    inputs = _inputs()
    manifest = _build(inputs)
    manifest["eligible_for_fpps"] = True
    manifest = _seal(manifest, "manifest_sha256")

    with pytest.raises(MultiEventPartitionError, match="safety fields"):
        _validate(manifest, inputs["qualified_release_projections"])


def test_per_role_hash_substitution_is_detected_after_manifest_rehash() -> None:
    inputs = _inputs()
    manifest = _build(inputs)
    manifest["role_partition_sha256"]["development"] = _digest("substituted-role-hash")
    manifest = _seal(manifest, "manifest_sha256")

    with pytest.raises(MultiEventPartitionError, match="per-role"):
        _validate(manifest, inputs["qualified_release_projections"])


def test_plain_manifest_tampering_fails_self_hash() -> None:
    inputs = _inputs()
    manifest = _build(inputs)
    manifest["partition_units"][0]["spatial_group_id"] = "TAMPERED-GROUP"

    with pytest.raises(MultiEventPartitionError, match="canonical content"):
        _validate(manifest, inputs["qualified_release_projections"])
