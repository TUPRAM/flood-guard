from __future__ import annotations

import pytest
import pandas as pd

from floodguard.flood_aggregation import (
    WEAK_REFERENCE_REVIEW_SUBDISTRICT_ID,
    FloodAggregationError,
    build_mae_sai_review_area_admin_geojson,
    build_mae_sai_weak_decision_inputs,
)
from floodguard.scoring import score_subdistricts


def weak_feature_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "mean_flood_probability_0_1": "0.046621",
                "source_timestamp": "2024-09-15T23:16:01Z",
                "confidence_class": "low",
                "processing_scope": "weak_reference_real_sentinel1_non_ml_candidate",
                "reference_status": "weak_reference_candidate",
                "sample_pixel_count": "65536",
                "reference_positive_pixel_count": "12557",
            }
        ]
    )


def manual_reference_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "reference_id": "MANUAL-QGIS-MAE-SAI-2024",
                "reference_mask_status": "weak_reference_candidate",
                "candidate_readiness_status": "ready_for_candidate_metrics",
                "bbox_lon_min": "99.81417084",
                "bbox_lat_min": "20.48330307",
                "bbox_lon_max": "99.82511139",
                "bbox_lat_max": "20.49144745",
            }
        ]
    )


def test_build_mae_sai_weak_decision_inputs_feeds_fpps() -> None:
    inputs = build_mae_sai_weak_decision_inputs(
        weak_feature_manifest(),
        manual_reference_manifest(),
    )
    scored = score_subdistricts(inputs)

    row = scored.iloc[0]
    assert row["subdistrict_id"] == WEAK_REFERENCE_REVIEW_SUBDISTRICT_ID
    assert row["mean_flood_probability_0_1"] == pytest.approx(0.046621)
    assert row["flood_likelihood_0_100"] == pytest.approx(4.66)
    assert row["exposure_0_100"] == pytest.approx(19.16)
    assert row["access_gap_0_100"] == pytest.approx(0.0)
    assert row["road_criticality_0_100"] == pytest.approx(0.0)
    assert row["vulnerability_context_0_100"] == pytest.approx(0.0)
    assert row["confidence_class"] == "low"
    assert row["action_class"] == "E"
    assert row["fpps_0_100"] == pytest.approx(6.19)
    assert "Weak-reference Sentinel-1 non-ML candidate" in row["assumptions"]
    assert "Not official validation" in row["assumptions"]


def test_build_mae_sai_review_area_admin_geojson_uses_manual_bbox() -> None:
    geojson = build_mae_sai_review_area_admin_geojson(manual_reference_manifest())

    feature = geojson["features"][0]
    assert geojson["type"] == "FeatureCollection"
    assert feature["properties"]["subdistrict_id"] == WEAK_REFERENCE_REVIEW_SUBDISTRICT_ID
    assert feature["properties"]["reference_id"] == "MANUAL-QGIS-MAE-SAI-2024"
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["geometry"]["coordinates"][0][0] == [99.81417084, 20.48330307]
    assert feature["geometry"]["coordinates"][0][2] == [99.82511139, 20.49144745]


def test_build_mae_sai_weak_decision_inputs_rejects_unready_manual_reference() -> None:
    manual = manual_reference_manifest()
    manual.loc[0, "candidate_readiness_status"] = "missing_source_file"

    with pytest.raises(FloodAggregationError, match="ready_for_candidate_metrics"):
        build_mae_sai_weak_decision_inputs(weak_feature_manifest(), manual)


def test_build_mae_sai_weak_decision_inputs_rejects_missing_columns() -> None:
    features = weak_feature_manifest().drop(columns=["mean_flood_probability_0_1"])

    with pytest.raises(FloodAggregationError, match="mean_flood_probability_0_1"):
        build_mae_sai_weak_decision_inputs(features, manual_reference_manifest())


def test_build_mae_sai_weak_decision_inputs_rejects_invalid_probability() -> None:
    features = weak_feature_manifest()
    features.loc[0, "mean_flood_probability_0_1"] = "1.5"

    with pytest.raises(FloodAggregationError, match="between 0 and 1"):
        build_mae_sai_weak_decision_inputs(features, manual_reference_manifest())
