"""Bridge weak-reference flood outputs into FloodGuard decision inputs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd


WEAK_REFERENCE_REVIEW_SUBDISTRICT_ID = "MS-WR-001"
WEAK_REFERENCE_REVIEW_SUBDISTRICT_NAME = "Mae Sai Weak-Reference Review Area"
WEAK_REFERENCE_SOURCE_NAME = "CDSE Sentinel-1 weak-reference SAR baseline"
WEAK_REFERENCE_ASSUMPTIONS = (
    "Weak-reference Sentinel-1 non-ML candidate. Non-operational. "
    "Not official validation. Not field validated. Flood likelihood comes from "
    "the weak SAR probability proxy; exposure is a sampled inundation-share "
    "proxy; real population, road, access, and vulnerability context are not "
    "joined yet."
)

WEAK_DECISION_INPUT_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "mean_flood_probability_0_1",
    "flood_likelihood_0_100",
    "exposure_0_100",
    "access_gap_0_100",
    "road_criticality_0_100",
    "vulnerability_context_0_100",
    "confidence_class",
    "source_name",
    "source_timestamp",
    "assumptions",
    "processing_scope",
    "reference_status",
    "context_status",
)

WEAK_FEATURE_REQUIRED_COLUMNS: tuple[str, ...] = (
    "mean_flood_probability_0_1",
    "source_timestamp",
    "confidence_class",
    "processing_scope",
    "reference_status",
    "sample_pixel_count",
    "reference_positive_pixel_count",
)

MANUAL_REFERENCE_REQUIRED_COLUMNS: tuple[str, ...] = (
    "reference_id",
    "reference_mask_status",
    "candidate_readiness_status",
    "spatial_relation",
    "spatial_relation_status",
    "in_study_area_overlap",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
)


class FloodAggregationError(ValueError):
    """Raised when weak-reference aggregation inputs violate the contract."""


def build_mae_sai_weak_decision_inputs(
    weak_feature_manifest: pd.DataFrame,
    manual_reference_manifest: pd.DataFrame,
    *,
    subdistrict_id: str = WEAK_REFERENCE_REVIEW_SUBDISTRICT_ID,
    subdistrict_name: str = WEAK_REFERENCE_REVIEW_SUBDISTRICT_NAME,
) -> pd.DataFrame:
    """Build one Mae Sai weak-reference decision input row for FPPS scoring.

    The current bridge intentionally does not pretend real population, road,
    access, or vulnerability context has been joined. It converts the weak SAR
    mean flood probability into `flood_likelihood_0_100`, uses sampled manual
    reference inundation share as a conservative exposure proxy, and sets
    missing context components to zero with explicit assumptions.
    """

    _require_columns(
        weak_feature_manifest,
        WEAK_FEATURE_REQUIRED_COLUMNS,
        "weak feature manifest",
    )
    _require_columns(
        manual_reference_manifest,
        MANUAL_REFERENCE_REQUIRED_COLUMNS,
        "manual reference manifest",
    )
    if weak_feature_manifest.empty:
        raise FloodAggregationError("weak feature manifest must contain at least one row.")
    if manual_reference_manifest.empty:
        raise FloodAggregationError(
            "manual reference manifest must contain at least one row."
        )

    feature = weak_feature_manifest.iloc[0]
    manual = manual_reference_manifest.iloc[0]
    _validate_manual_reference_ready(manual)

    mean_probability = _bounded_number(
        feature["mean_flood_probability_0_1"],
        0.0,
        1.0,
        "mean_flood_probability_0_1",
    )
    sample_pixels = _positive_number(feature["sample_pixel_count"], "sample_pixel_count")
    reference_pixels = _bounded_number(
        feature["reference_positive_pixel_count"],
        0.0,
        sample_pixels,
        "reference_positive_pixel_count",
    )

    row = {
        "subdistrict_id": subdistrict_id,
        "subdistrict_name": subdistrict_name,
        "mean_flood_probability_0_1": round(mean_probability, 6),
        "flood_likelihood_0_100": round(mean_probability * 100.0, 2),
        "exposure_0_100": round((reference_pixels / sample_pixels) * 100.0, 2),
        "access_gap_0_100": 0.0,
        "road_criticality_0_100": 0.0,
        "vulnerability_context_0_100": 0.0,
        "confidence_class": "low",
        "source_name": WEAK_REFERENCE_SOURCE_NAME,
        "source_timestamp": str(feature["source_timestamp"]),
        "assumptions": WEAK_REFERENCE_ASSUMPTIONS,
        "processing_scope": str(feature["processing_scope"]),
        "reference_status": str(feature["reference_status"]),
        "context_status": "weak_sar_only_real_context_not_joined",
    }
    if str(feature["confidence_class"]).lower() != "low":
        row["assumptions"] = (
            f"{row['assumptions']} Source confidence was "
            f"{feature['confidence_class']}; decision bridge keeps low confidence "
            "until real context layers are joined."
        )
    return pd.DataFrame([row], columns=WEAK_DECISION_INPUT_COLUMNS)


def build_mae_sai_review_area_admin_geojson(
    manual_reference_manifest: pd.DataFrame,
    *,
    subdistrict_id: str = WEAK_REFERENCE_REVIEW_SUBDISTRICT_ID,
    subdistrict_name: str = WEAK_REFERENCE_REVIEW_SUBDISTRICT_NAME,
) -> dict[str, Any]:
    """Build a minimal WGS84 review-area polygon from manual-reference bbox."""

    _require_columns(
        manual_reference_manifest,
        MANUAL_REFERENCE_REQUIRED_COLUMNS,
        "manual reference manifest",
    )
    if manual_reference_manifest.empty:
        raise FloodAggregationError(
            "manual reference manifest must contain at least one row."
        )
    manual = manual_reference_manifest.iloc[0]
    _validate_manual_reference_ready(manual)
    lon_min = _number(manual["bbox_lon_min"], "bbox_lon_min")
    lat_min = _number(manual["bbox_lat_min"], "bbox_lat_min")
    lon_max = _number(manual["bbox_lon_max"], "bbox_lon_max")
    lat_max = _number(manual["bbox_lat_max"], "bbox_lat_max")
    if lon_max <= lon_min or lat_max <= lat_min:
        raise FloodAggregationError("manual reference bbox must have positive area.")

    return {
        "type": "FeatureCollection",
        "name": "mae_sai_weak_reference_review_area",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "subdistrict_id": subdistrict_id,
                    "subdistrict_name": subdistrict_name,
                    "geometry_status": "manual_reference_bbox_review_area",
                    "reference_id": str(manual["reference_id"]),
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [lon_min, lat_min],
                            [lon_max, lat_min],
                            [lon_max, lat_max],
                            [lon_min, lat_max],
                            [lon_min, lat_min],
                        ]
                    ],
                },
            }
        ],
    }


def _validate_manual_reference_ready(row: pd.Series) -> None:
    if str(row["reference_mask_status"]) != "weak_reference_candidate":
        raise FloodAggregationError(
            "manual reference status must be weak_reference_candidate."
        )
    if str(row["candidate_readiness_status"]) != "ready_for_candidate_metrics":
        raise FloodAggregationError(
            "manual reference must be ready_for_candidate_metrics."
        )
    if str(row["spatial_relation_status"]) != "verified_geometry_intersection":
        raise FloodAggregationError(
            "manual reference spatial relation must be verified before aggregation."
        )
    relation = str(row["spatial_relation"])
    if relation not in {
        "in_study_area_weak_reference",
        "cross_border_calibration_only",
    }:
        raise FloodAggregationError(
            "manual reference has an unsupported spatial relation."
        )
    overlap = _strict_bool(row["in_study_area_overlap"], "in_study_area_overlap")
    if relation == "cross_border_calibration_only" and overlap:
        raise FloodAggregationError(
            "cross-border manual reference cannot claim in-study-area overlap."
        )


def _bounded_number(value: object, lower: float, upper: float, column: str) -> float:
    numeric = _number(value, column)
    if numeric < lower or numeric > upper:
        raise FloodAggregationError(
            f"{column} must be between {lower:g} and {upper:g}."
        )
    return numeric


def _positive_number(value: object, column: str) -> float:
    numeric = _number(value, column)
    if numeric <= 0:
        raise FloodAggregationError(f"{column} must be greater than zero.")
    return numeric


def _number(value: object, column: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise FloodAggregationError(f"{column} must be numeric.") from exc
    if pd.isna(numeric):
        raise FloodAggregationError(f"{column} must be numeric.")
    return numeric


def _strict_bool(value: object, column: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise FloodAggregationError(f"{column} must be explicit true or false.")


def _require_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    label: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise FloodAggregationError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )
