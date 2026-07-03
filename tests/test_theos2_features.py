from __future__ import annotations

import pandas as pd
import pytest

from floodguard.theos2_features import (
    THEOS2FeatureError,
    build_theos2_landcover_exposure_features,
)


def test_build_theos2_landcover_exposure_features_from_selected_manifest() -> None:
    features = build_theos2_landcover_exposure_features(_selected_manifest())

    assert len(features) == 2
    disaster = features.loc[features["file_name"].str.endswith("004.tif")].iloc[0]
    lulc = features.loc[features["file_name"].str.endswith("001.tif")].iloc[0]
    assert bool(disaster["has_disaster_context"]) is True
    assert bool(disaster["has_lulc_context"]) is False
    assert bool(lulc["has_lulc_context"]) is True
    assert disaster["rough_bbox_area_sq_km"] > 0
    assert "not flood validation or labels" in disaster["assumptions"]
    assert "method-development context" in lulc["floodguard_use"]


def test_theos2_features_skip_rows_not_processing_allowed() -> None:
    manifest = _selected_manifest()
    manifest.loc[0, "processing_allowed"] = False

    features = build_theos2_landcover_exposure_features(manifest)

    assert len(features) == 1
    assert features.iloc[0]["file_name"].endswith("001.tif")


def test_theos2_features_reject_reference_mask_status() -> None:
    manifest = _selected_manifest()
    manifest.loc[0, "reference_mask_status"] = "confirmed"

    with pytest.raises(THEOS2FeatureError, match="not be treated as reference mask"):
        build_theos2_landcover_exposure_features(manifest)


def _selected_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "file_name": "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif",
                "source_timestamp": "2025-07-30T03:33:31Z",
                "category": "Disaster",
                "bbox_lon_min": "99.734272",
                "bbox_lat_min": "16.961463",
                "bbox_lon_max": "99.883844",
                "bbox_lat_max": "17.104638",
                "mvp_overlap": "none_of_current_mvp_points",
                "processing_allowed": True,
                "reference_mask_status": "not_reference_mask",
            },
            {
                "file_name": "IMG_T2V_20250731035100_ORTHO_PMS_32-001.tif",
                "source_timestamp": "2025-07-31T03:51:00Z",
                "category": "Disaster|LULC",
                "bbox_lon_min": "100.675272",
                "bbox_lat_min": "18.447708",
                "bbox_lon_max": "100.81192",
                "bbox_lat_max": "18.577633",
                "mvp_overlap": "none_of_current_mvp_points",
                "processing_allowed": True,
                "reference_mask_status": "not_reference_mask",
            },
        ]
    )
