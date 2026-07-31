from __future__ import annotations

import pytest

from floodguard.label_factory.contracts import (
    QUERY_MODEL_ELIGIBILITY,
    DatasetRole,
    FloodLabel,
    HumanReviewedTrainingEligibility,
    LabelContractError,
    ModelEligibility,
    ModelPurpose,
    WeakSeedLabel,
    binary_temporary_flood_target,
    convert_weak_binary_mask_to_positive_unlabeled,
    require_binary_training_labels,
)
from floodguard.label_factory.feature_schema import (
    LEGACY_REAL_RASTER_V1,
    LEGACY_SYNTHETIC_BASELINE_V1,
    SAR_CHANGE_V2,
    FeatureSchemaError,
    get_feature_schema,
)


def test_five_review_states_and_unreviewed_have_fixed_codes() -> None:
    assert FloodLabel.DRY_LAND.value == 0
    assert FloodLabel.TEMPORARY_FLOOD.value == 1
    assert FloodLabel.PERMANENT_OR_PREEXISTING_WATER.value == 2
    assert FloodLabel.UNCERTAIN_WATER_CHANGE.value == 3
    assert FloodLabel.UNOBSERVABLE_OR_ARTIFACT.value == 4
    assert FloodLabel.UNREVIEWED.value == 255

    reviewed = [label for label in FloodLabel if label.is_explicit_review_outcome]
    assert len(reviewed) == 5
    assert FloodLabel.UNREVIEWED not in reviewed


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        (FloodLabel.DRY_LAND, 0),
        (FloodLabel.TEMPORARY_FLOOD, 1),
        (FloodLabel.PERMANENT_OR_PREEXISTING_WATER, 0),
        (FloodLabel.UNCERTAIN_WATER_CHANGE, None),
        (FloodLabel.UNOBSERVABLE_OR_ARTIFACT, None),
        (FloodLabel.UNREVIEWED, None),
    ],
)
def test_binary_target_excludes_unknown_or_unsupported_classes(
    label: FloodLabel,
    expected: int | None,
) -> None:
    assert binary_temporary_flood_target(label) == expected
    assert label.is_binary_trainable is (expected is not None)


def test_binary_training_helper_fails_closed_instead_of_silently_filtering() -> None:
    assert require_binary_training_labels([0, 1, 2]) == (0, 1, 0)

    with pytest.raises(LabelContractError, match="excluded label classes"):
        require_binary_training_labels([0, 3, 1, 255])


def test_only_training_query_pool_allows_active_selection_and_query_training() -> None:
    for role in DatasetRole:
        expected = role is DatasetRole.TRAINING_AND_QUERY_POOL
        assert role.allows_active_selection is expected
        assert role.allows_query_model_training is expected

    assert (
        DatasetRole.FIXED_WITHIN_EVENT_DEVELOPMENT
        .allows_threshold_or_model_selection
        is True
    )
    assert DatasetRole.UNTOUCHED_GEOGRAPHIC_TEST.is_untouched_test is True
    assert (
        DatasetRole.UNTOUCHED_GEOGRAPHIC_TEST.allows_threshold_or_model_selection
        is False
    )


def test_query_model_eligibility_is_hard_blocked_from_operational_consumers() -> None:
    fields = QUERY_MODEL_ELIGIBILITY.as_manifest_fields()

    assert fields == {
        "model_purpose": "query_ranking",
        "eligible_for_review_queue": True,
        "eligible_for_training_after_human_review": "conditional",
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }

    with pytest.raises(LabelContractError, match="eligibility is fixed"):
        ModelEligibility(
            purpose=ModelPurpose.QUERY_RANKING,
            eligible_for_review_queue=True,
            eligible_for_training_after_human_review=(
                HumanReviewedTrainingEligibility.CONDITIONAL
            ),
            query_model_only=True,
            eligible_for_decision_layer=True,
            eligible_for_fpps=False,
            eligible_for_warning=False,
        )

    with pytest.raises(LabelContractError, match="ModelPurpose"):
        ModelEligibility(
            purpose="query_ranking",  # type: ignore[arg-type]
            eligible_for_review_queue=True,
            eligible_for_training_after_human_review=(
                HumanReviewedTrainingEligibility.CONDITIONAL
            ),
            query_model_only=True,
            eligible_for_decision_layer=True,
            eligible_for_fpps=True,
            eligible_for_warning=True,
        )


def test_boolean_cannot_be_mistaken_for_integer_flood_label() -> None:
    with pytest.raises(LabelContractError, match="Unknown flood-label code"):
        binary_temporary_flood_target(True)


def test_weak_binary_exterior_becomes_unreviewed_never_dry() -> None:
    converted = convert_weak_binary_mask_to_positive_unlabeled(
        [
            [0, 0, 0],
            [0, 1, 0],
            [0, 0, 0],
        ]
    )

    assert converted[1][1] == WeakSeedLabel.WEAK_POSITIVE
    assert converted[0][0] == WeakSeedLabel.UNREVIEWED
    assert FloodLabel.DRY_LAND.value not in {
        value for row in converted for value in row
    }
    with pytest.raises(LabelContractError, match="not reviewed truth"):
        require_binary_training_labels([converted[1][1]])


def test_optional_weak_boundary_buffer_marks_both_sides_uncertain() -> None:
    converted = convert_weak_binary_mask_to_positive_unlabeled(
        [
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 1, 1, 0, 0],
            [0, 0, 1, 1, 1, 0, 0],
            [0, 0, 1, 1, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0],
        ],
        boundary_buffer_cells=1,
    )

    assert converted[3][3] == WeakSeedLabel.WEAK_POSITIVE
    assert converted[2][2] == WeakSeedLabel.WEAK_UNCERTAIN
    assert converted[1][3] == WeakSeedLabel.WEAK_UNCERTAIN
    assert converted[0][0] == WeakSeedLabel.UNREVIEWED


@pytest.mark.parametrize(
    "mask, buffer, message",
    [
        ([], 0, "at least one row"),
        ([[0], [0, 1]], 0, "rectangular"),
        ([[0, 2]], 0, "binary integers"),
        ([[0, 1]], -1, "non-negative"),
    ],
)
def test_weak_seed_conversion_rejects_ambiguous_inputs(
    mask: list[list[int]],
    buffer: int,
    message: str,
) -> None:
    with pytest.raises(LabelContractError, match=message):
        convert_weak_binary_mask_to_positive_unlabeled(
            mask,
            boundary_buffer_cells=buffer,
        )


def test_legacy_feature_schemas_preserve_both_formula_versions_explicitly() -> None:
    synthetic = LEGACY_SYNTHETIC_BASELINE_V1.get("combined_drop_db")
    real = LEGACY_REAL_RASTER_V1.get("combined_sar_change_score")

    assert synthetic.formula == "0.6 * vv_drop_db + 0.4 * vh_drop_db"
    assert real.formula == "0.4 * vv_drop + 0.6 * vh_drop"
    assert LEGACY_SYNTHETIC_BASELINE_V1.version != LEGACY_REAL_RASTER_V1.version
    assert LEGACY_SYNTHETIC_BASELINE_V1.version == "legacy_synthetic_sar_v1"
    assert LEGACY_REAL_RASTER_V1.version == "legacy_real_weak_sar_v1"
    assert LEGACY_SYNTHETIC_BASELINE_V1.legacy is True
    assert LEGACY_REAL_RASTER_V1.legacy is True


def test_canonical_v2_excludes_redundant_ratios_and_legacy_combined_scores() -> None:
    forbidden = {
        "vv_ratio",
        "vh_ratio",
        "combined_drop_db",
        "combined_sar_change_score",
    }

    assert SAR_CHANGE_V2.version == "sar_change_v2"
    assert SAR_CHANGE_V2.legacy is False
    assert forbidden.isdisjoint(SAR_CHANGE_V2.feature_names)
    assert {
        "pre_vv_db",
        "event_vv_db",
        "pre_vh_db",
        "event_vh_db",
        "vv_change_db",
        "vh_change_db",
        "valid_data_fraction",
    }.issubset(SAR_CHANGE_V2.required_feature_names)


def test_feature_schema_validates_required_columns_in_frozen_order() -> None:
    record = {
        "event_vh_db": -20.0,
        "valid_data_fraction": 1.0,
        "vv_change_db": 4.0,
        "event_vv_db": -15.0,
        "pre_vv_db": -11.0,
        "vh_change_db": 3.0,
        "pre_vh_db": -17.0,
        "tile_id": "metadata-is-allowed",
    }

    ordered = SAR_CHANGE_V2.validate_columns(record)

    assert ordered == SAR_CHANGE_V2.required_feature_names
    assert get_feature_schema("sar_change_v2") is SAR_CHANGE_V2
    with pytest.raises(FeatureSchemaError, match="missing required columns"):
        SAR_CHANGE_V2.validate_columns({"pre_vv_db": -11.0})
