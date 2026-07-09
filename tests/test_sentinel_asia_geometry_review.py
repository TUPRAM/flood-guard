from __future__ import annotations

from pathlib import Path

import pandas as pd

from floodguard.sentinel_asia_geometry_review import build_geometry_quality_notes
from floodguard.sentinel_asia_geometry_review import _parse_ogr_feature_values


def test_parse_ogr_feature_values_extracts_sql_stats() -> None:
    text = """
OGRFeature(SELECT):0
  feature_count (Integer) = 514
  area_sum (Real) = 47164056.46
  area_min (Real) = 9003.47
  area_max (Real) = 8380040
"""

    values = _parse_ogr_feature_values(text)

    assert values["feature_count"] == "514"
    assert values["area_sum"] == "47164056.46"
    assert values["area_max"] == "8380040"


def test_generated_geometry_review_notes_keep_reference_candidate_boundary() -> None:
    manifest = Path("outputs/sentinel_asia_geometry_quality_review.csv")
    if manifest.exists():
        row = pd.read_csv(manifest).iloc[0]
    else:
        row = pd.Series(
            {
                "qgis_gdal_version": "GDAL 3.13.0",
                "layer_name": "Thailand_flood",
                "geometry_type": "Polygon",
                "crs": "4326",
                "attribute_fields": "Id|gridcode|Area",
                "dbf_update_date": "2024-09-16",
                "feature_count": 6506,
                "area_field_sum_km2": 464.234,
                "mae_sai_review_bbox": "99.72,20.3,100.03,20.56",
                "mae_sai_review_feature_count": 514,
                "mae_sai_review_area_sum_km2": 47.164,
                "gridcode_values": "1",
            }
        )

    notes = build_geometry_quality_notes(row)

    assert "reference candidate, not validation truth and not ML labels" in notes
    assert "QGIS/GDAL Inspection" in notes
    assert "Do not run the real non-ML SAR baseline" in notes


def test_visual_qa_review_records_reference_candidate_boundary() -> None:
    manifest = Path("outputs/sentinel_asia_mbrsc_visual_qa_review.csv")

    row = pd.read_csv(manifest).iloc[0]

    assert row["mae_sai_point_intersects_polygon"] == "no"
    assert int(row["east_southeast_floodplain_feature_count"]) == 477
    assert "not a single broad event boundary" in row["broad_event_noise_assessment"]
    assert row["validation_status"] == "reference_candidate_only_not_validation_truth"
    assert row["ml_label_status"] == "not_cleared_for_ml_labels"
