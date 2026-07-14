from __future__ import annotations

from datetime import datetime, timezone
import math

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from floodguard.optical_features import (
    MASKED_SCL_CLASSES,
    OPTICAL_CONTEXT_WARNING,
    OPTICAL_FEATURE_SCHEMA_VERSION,
    OPTICAL_PROCESSING_SCOPE,
    OpticalFeatureError,
    SENTINEL2_BANDS,
    build_optical_features,
    build_sentinel2_optical_features,
    evaluate_theos2_pixel_eligibility,
)


def _valid_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pixel_id": "PX-001",
                "grid_id": "EPSG32647-10M-V1",
                "source_name": "Copernicus Sentinel-2 Level-2A",
                "pre_source_timestamp": "2024-09-03T03:21:00Z",
                "post_source_timestamp": "2024-09-15T03:21:00+00:00",
                "confidence_class": "medium",
                "assumptions": (
                    "Already co-registered surface reflectance; fixture pixels only."
                ),
                "pre_B02": 0.10,
                "pre_B03": 0.20,
                "pre_B04": 0.15,
                "pre_B05": 0.18,
                "pre_B06": 0.22,
                "pre_B07": 0.25,
                "pre_B08": 0.30,
                "pre_B8A": 0.28,
                "pre_B11": 0.25,
                "pre_B12": 0.20,
                "post_B02": 0.08,
                "post_B03": 0.35,
                "post_B04": 0.10,
                "post_B05": 0.12,
                "post_B06": 0.14,
                "post_B07": 0.16,
                "post_B08": 0.15,
                "post_B8A": 0.16,
                "post_B11": 0.10,
                "post_B12": 0.08,
                "pre_SCL": 4,
                "post_SCL": 6,
                "pre_cloud_distance_m": 1000.0,
                "post_cloud_distance_m": 900.0,
            }
        ]
    )


def test_build_optical_features_computes_indices_and_spectral_changes() -> None:
    result = build_sentinel2_optical_features(
        _valid_rows(),
        minimum_cloud_distance_m=250.0,
    )
    row = result.iloc[0]

    assert bool(row["pre_optical_valid"])
    assert bool(row["post_optical_valid"])
    assert bool(row["optical_valid"])
    assert row["pre_mask_reason"] == ""
    assert row["post_mask_reason"] == ""
    assert row["optical_invalid_reason"] == ""
    assert row["pre_ndwi"] == pytest.approx(-0.2)
    assert row["post_ndwi"] == pytest.approx(0.4)
    assert row["ndwi_change"] == pytest.approx(0.6)
    assert row["pre_mndwi"] == pytest.approx(-1.0 / 9.0)
    assert row["post_mndwi"] == pytest.approx(5.0 / 9.0)
    assert row["mndwi_change"] == pytest.approx(2.0 / 3.0)
    assert row["pre_ndvi"] == pytest.approx(1.0 / 3.0)
    assert row["post_ndvi"] == pytest.approx(0.2)
    assert row["ndvi_change"] == pytest.approx(-2.0 / 15.0)
    assert row["pre_awei"] == pytest.approx(-0.275)
    assert row["post_awei"] == pytest.approx(0.56)
    assert row["awei_change"] == pytest.approx(0.835)
    assert row["B05_change"] == pytest.approx(-0.06)
    assert row["B8A_change"] == pytest.approx(-0.12)
    assert all(f"{band}_change" in result for band in SENTINEL2_BANDS)
    assert all(f"pre_{band}_masked" in result for band in SENTINEL2_BANDS)
    assert all(f"post_{band}_masked" in result for band in SENTINEL2_BANDS)
    assert row["pre_B03_masked"] == pytest.approx(row["pre_B03"])
    assert row["post_B11_masked"] == pytest.approx(row["post_B11"])
    assert row["minimum_cloud_distance_m"] == pytest.approx(900.0)
    assert row["cloud_distance_threshold_m"] == pytest.approx(250.0)
    assert row["awei_variant"] == "AWEIsh"


def test_output_preserves_lineage_and_strict_not_flood_truth_semantics() -> None:
    result = build_optical_features(_valid_rows())
    row = result.iloc[0]

    assert row["source_timestamp"] == "2024-09-15T03:21:00Z"
    assert row["pre_source_timestamp"] == "2024-09-03T03:21:00Z"
    assert row["confidence_class"] == "medium"
    assert "co-registered" in row["assumptions"]
    assert row["feature_schema_version"] == OPTICAL_FEATURE_SCHEMA_VERSION
    assert row["processing_scope"] == OPTICAL_PROCESSING_SCOPE
    assert row["flood_truth_status"] == "not_flood_truth"
    assert not bool(row["eligible_for_flood_truth"])
    assert row["warning_text"] == OPTICAL_CONTEXT_WARNING
    assert "not flood truth" in row["warning_text"]
    assert "not a flood label" in row["warning_text"]
    assert "not validation" in row["warning_text"]
    assert "not an official warning" in row["warning_text"]


@pytest.mark.parametrize("masked_scl", sorted(MASKED_SCL_CLASSES))
def test_scl_cloud_shadow_snow_nodata_and_defective_classes_are_masked(
    masked_scl: int,
) -> None:
    rows = _valid_rows()
    rows.loc[0, "post_SCL"] = masked_scl

    row = build_sentinel2_optical_features(rows).iloc[0]

    assert bool(row["pre_optical_valid"])
    assert not bool(row["post_optical_valid"])
    assert not bool(row["optical_valid"])
    assert str(row["post_mask_reason"]).startswith("scl_")
    assert str(row["optical_invalid_reason"]).startswith("post:scl_")
    assert math.isnan(float(row["post_ndwi"]))
    assert math.isnan(float(row["post_B03_masked"]))
    assert math.isnan(float(row["post_B11_masked"]))
    assert math.isnan(float(row["ndwi_change"]))
    assert math.isnan(float(row["B03_change"]))


def test_cloud_distance_threshold_masks_adjacent_pixels() -> None:
    rows = _valid_rows()
    rows.loc[0, "post_cloud_distance_m"] = 99.0

    row = build_sentinel2_optical_features(
        rows,
        minimum_cloud_distance_m=100.0,
    ).iloc[0]

    assert not bool(row["post_optical_valid"])
    assert row["post_mask_reason"] == "cloud_distance_below_threshold"
    assert row["optical_invalid_reason"] == (
        "post:cloud_distance_below_threshold"
    )


def test_zero_index_denominator_fails_safe_without_infinity() -> None:
    rows = _valid_rows()
    rows.loc[0, ["pre_B03", "pre_B08"]] = 0.0

    row = build_sentinel2_optical_features(rows).iloc[0]

    assert not bool(row["pre_optical_valid"])
    assert not bool(row["optical_valid"])
    assert "zero_or_near_zero_index_denominator" in row["pre_mask_reason"]
    assert math.isnan(float(row["pre_ndwi"]))
    assert math.isnan(float(row["ndwi_change"]))


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("pre_B02", -0.001, "reflectance must be within 0..1"),
        ("post_B12", 1.001, "reflectance must be within 0..1"),
        ("pre_B05", None, "must contain finite numeric values"),
        ("post_B06", float("inf"), "must contain finite numeric values"),
        ("pre_SCL", 12, "integer Sentinel-2 SCL values from 0 to 11"),
        ("post_SCL", 4.5, "integer Sentinel-2 SCL values from 0 to 11"),
        ("pre_cloud_distance_m", -1, "must be non-negative"),
        ("confidence_class", "candidate", "must be one of high, medium, or low"),
        ("assumptions", "", "must contain non-blank strings"),
        ("grid_id", " ", "must contain non-blank strings"),
    ],
)
def test_strict_input_ranges_and_metadata_validation(
    column: str,
    value: object,
    message: str,
) -> None:
    rows = _valid_rows()
    rows[column] = pd.Series([value], dtype="object")

    with pytest.raises(OpticalFeatureError, match=message):
        build_sentinel2_optical_features(rows)


@pytest.mark.parametrize("column", ["pre_B07", "post_B8A", "post_source_timestamp"])
def test_required_band_and_lineage_columns_fail_closed(column: str) -> None:
    rows = _valid_rows().drop(columns=column)

    with pytest.raises(OpticalFeatureError, match=column):
        build_sentinel2_optical_features(rows)


def test_duplicate_grid_pixel_pair_is_rejected() -> None:
    rows = pd.concat([_valid_rows(), _valid_rows()], ignore_index=True)

    with pytest.raises(OpticalFeatureError, match="pairs must be unique"):
        build_sentinel2_optical_features(rows)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        (
            "pre_source_timestamp",
            "2024-09-03T03:21:00",
            "explicit UTC offset or Z suffix",
        ),
        (
            "post_source_timestamp",
            "not-a-time",
            "timezone-aware ISO-8601 timestamp",
        ),
        (
            "post_source_timestamp",
            "2024-09-03T03:21:00Z",
            "must be earlier than",
        ),
    ],
)
def test_timestamp_contract_requires_timezone_and_strict_pre_post_order(
    column: str,
    value: str,
    message: str,
) -> None:
    rows = _valid_rows()
    rows.loc[0, column] = value

    with pytest.raises(OpticalFeatureError, match=message):
        build_sentinel2_optical_features(rows)


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("minimum_cloud_distance_m", -0.1),
        ("minimum_cloud_distance_m", True),
        ("denominator_epsilon", 0.0),
        ("denominator_epsilon", float("nan")),
    ],
)
def test_feature_parameters_are_strict(keyword: str, value: object) -> None:
    kwargs = {keyword: value}

    with pytest.raises(OpticalFeatureError):
        build_sentinel2_optical_features(_valid_rows(), **kwargs)


def test_feature_builder_does_not_mutate_input() -> None:
    rows = _valid_rows()
    original = rows.copy(deep=True)

    build_sentinel2_optical_features(rows, minimum_cloud_distance_m=300.0)

    assert_frame_equal(rows, original)


def test_numpy_boolean_reflectance_is_not_coerced_to_one() -> None:
    rows = _valid_rows()
    rows["pre_B02"] = rows["pre_B02"].astype(object)
    rows.loc[0, "pre_B02"] = pd.Series([True]).iloc[0]

    with pytest.raises(OpticalFeatureError, match="finite numeric values"):
        build_sentinel2_optical_features(rows)


def test_theos2_pixel_eligibility_passes_only_with_complete_evidence() -> None:
    result = evaluate_theos2_pixel_eligibility(
        pixel_data_available=True,
        metadata_only=False,
        radiometric_calibration_complete=True,
        georeferencing_complete=True,
        grid_alignment_complete=True,
        acquisition_timestamp=datetime(2024, 9, 15, 3, 21, tzinfo=timezone.utc),
        event_start_timestamp="2024-09-10T00:00:00Z",
        event_end_timestamp="2024-09-20T23:59:59Z",
        label_start_timestamp="2024-09-14T00:00:00Z",
        label_end_timestamp="2024-09-16T23:59:59Z",
        training_permission_granted=True,
    )

    assert result.eligible
    assert result.status == "eligible_for_pixel_level_research_input"
    assert result.reasons == ()
    assert result.event_date_overlap
    assert result.label_date_overlap
    assert result.acquisition_timestamp == "2024-09-15T03:21:00Z"
    assert "fail-closed" in result.warning_text
    assert "not flood truth" in result.warning_text


def test_theos2_metadata_only_and_unresolved_inputs_fail_closed() -> None:
    result = evaluate_theos2_pixel_eligibility(
        pixel_data_available=False,
        metadata_only=True,
        radiometric_calibration_complete=False,
        georeferencing_complete=False,
        grid_alignment_complete=False,
        acquisition_timestamp="2025-07-30T03:33:31Z",
        event_start_timestamp="2024-09-10T00:00:00Z",
        event_end_timestamp="2024-09-20T23:59:59Z",
        label_start_timestamp="2024-09-14T00:00:00Z",
        label_end_timestamp="2024-09-16T23:59:59Z",
        training_permission_granted=False,
    )

    assert not result.eligible
    assert result.status == "ineligible_for_pixel_level_research_input"
    assert result.reasons == (
        "metadata_only_input",
        "pixel_data_unavailable",
        "radiometric_calibration_incomplete",
        "georeferencing_incomplete",
        "grid_alignment_incomplete",
        "outside_event_window",
        "outside_label_window",
        "training_permission_not_granted",
    )


def test_theos2_date_overlap_and_permission_each_block_eligibility() -> None:
    result = evaluate_theos2_pixel_eligibility(
        pixel_data_available=True,
        metadata_only=False,
        radiometric_calibration_complete=True,
        georeferencing_complete=True,
        grid_alignment_complete=True,
        acquisition_timestamp="2024-09-15T03:21:00Z",
        event_start_timestamp="2024-09-01T00:00:00Z",
        event_end_timestamp="2024-09-30T23:59:59Z",
        label_start_timestamp="2024-09-16T00:00:00Z",
        label_end_timestamp="2024-09-17T23:59:59Z",
        training_permission_granted=False,
    )

    assert not result.eligible
    assert result.event_date_overlap
    assert not result.label_date_overlap
    assert result.reasons == (
        "outside_label_window",
        "training_permission_not_granted",
    )


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("metadata_only", "False", "must be a boolean"),
        (
            "event_start_timestamp",
            "2024-09-21T00:00:00Z",
            "event_start_timestamp must not be later",
        ),
        (
            "label_start_timestamp",
            "2024-09-17T00:00:00Z",
            "label_start_timestamp must not be later",
        ),
    ],
)
def test_theos2_eligibility_rejects_malformed_contracts(
    keyword: str,
    value: object,
    message: str,
) -> None:
    kwargs: dict[str, object] = {
        "pixel_data_available": True,
        "metadata_only": False,
        "radiometric_calibration_complete": True,
        "georeferencing_complete": True,
        "grid_alignment_complete": True,
        "acquisition_timestamp": "2024-09-15T03:21:00Z",
        "event_start_timestamp": "2024-09-10T00:00:00Z",
        "event_end_timestamp": "2024-09-20T23:59:59Z",
        "label_start_timestamp": "2024-09-14T00:00:00Z",
        "label_end_timestamp": "2024-09-16T23:59:59Z",
        "training_permission_granted": True,
    }
    kwargs[keyword] = value

    with pytest.raises(OpticalFeatureError, match=message):
        evaluate_theos2_pixel_eligibility(**kwargs)
