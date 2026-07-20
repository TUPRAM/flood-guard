from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.validation import (
    FUTURE_METRIC_PLACEHOLDERS,
    ValidationReportError,
    build_real_data_validation_summary,
    build_validation_summary,
    write_real_data_validation_summary,
    write_validation_summary,
)
from floodguard.sar_raster_extract import (
    SAR_LOG_TRANSFORM,
    SAR_MEASUREMENT_DOMAIN,
    SAR_RADIOMETRIC_CALIBRATION_STATUS,
)
from floodguard.ingestion import (
    MAE_SAI_BASELINE_POST_PRODUCT_ID,
    MAE_SAI_BASELINE_PRE_PRODUCT_ID,
    build_ingestion_manifest,
    default_mae_sai_file_manifest_sources,
)

OUTPUTS = Path(__file__).parents[1] / "outputs"


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv(OUTPUTS / "sample_priority_scores.csv"),
        pd.read_csv(OUTPUTS / "sample_road_risk.csv"),
        pd.read_csv(OUTPUTS / "sample_access_loss.csv"),
        pd.read_csv(OUTPUTS / "sample_equity_gap.csv"),
    )


def load_rank_instability() -> pd.DataFrame:
    return pd.read_csv(OUTPUTS / "sample_fpps_rank_instability.csv")


def test_build_validation_summary_includes_fixture_metrics() -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()

    report = build_validation_summary(
        priority,
        road_risk,
        access_loss,
        equity_gap,
        rank_instability=load_rank_instability(),
    )

    assert "# FloodGuard Validation Summary" in report
    assert "## Decision Narrative" in report
    assert "fixture-backed decision demo" in report
    assert "not an official warning" in report
    assert "## What The Fixture Proves" in report
    assert "## Data Readiness Narrative" in report
    assert "not agency flood products" in report
    assert "provider response pending" in report
    assert "## What Remains Blocked" in report
    assert "Real-data ML remains blocked" in report
    assert "## Real Mae Sai Gate Update" in report
    assert "geometry access" in report
    assert "ML-label use status" in report
    assert "Priority rows: 5" in report
    assert "Road-risk rows: 3" in report
    assert "Top actionable subdistrict: FG-TB-001 / River Market" in report
    assert "Action-class counts: A=1, B=1, C=1, D=1, E=1" in report
    assert "High-risk road count (>= 0.70): 2" in report
    assert "People losing 30-minute access: 190" in report
    assert "Strongest equity-gap subdistrict: FG-TB-002 / Bridge Junction" in report


def test_build_validation_summary_includes_sensitivity_summary() -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()

    report = build_validation_summary(
        priority,
        road_risk,
        access_loss,
        equity_gap,
        rank_instability=load_rank_instability(),
    )

    assert "## Sensitivity Summary" in report
    assert "Stable rank count: 5" in report
    assert "Unstable rank count: 0" in report
    assert "Max rank range: 0" in report
    assert "All fixture ranks are stable because every rank_range is 0." in report
    assert "FG-TB-005 / Unverified Hillside (class E, confidence low)" in report
    assert "not used as the top actionable brief target" in report


def test_build_validation_summary_includes_future_metric_placeholders() -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()

    report = build_validation_summary(priority, road_risk, access_loss, equity_gap)

    for placeholder in FUTURE_METRIC_PLACEHOLDERS:
        if placeholder == "score sensitivity":
            assert (
                "score sensitivity: implemented for fixtures; "
                "real calibration remains pending"
            ) in report
        else:
            assert f"{placeholder}: pending real reference data" in report


def test_write_validation_summary_writes_markdown(tmp_path: Path) -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()
    output_path = tmp_path / "validation_summary.md"

    written = write_validation_summary(
        priority,
        road_risk,
        access_loss,
        equity_gap,
        output_path,
    )

    assert written == output_path
    assert output_path.read_text(encoding="utf-8").startswith(
        "# FloodGuard Validation Summary"
    )


def test_build_validation_summary_rejects_missing_columns() -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()
    bad_priority = priority.drop(columns=["action_class"])

    with pytest.raises(ValidationReportError, match="action_class"):
        build_validation_summary(bad_priority, road_risk, access_loss, equity_gap)


def test_real_data_validation_summary_reports_blocked_manifest() -> None:
    manifest = build_ingestion_manifest(default_mae_sai_file_manifest_sources())

    report = build_real_data_validation_summary(manifest)

    assert "# Mae Sai Real-Data Validation Summary" in report
    assert "## Data Status" in report
    assert "## Sentinel-1 Product IDs" in report
    assert "## Integrity And Spatial Scope" in report
    assert "## Manual Reference Mask Metadata" in report
    assert "## Method Assumptions" in report
    assert "## Candidate Metrics" in report
    assert "## Failure Modes" in report
    assert "## Safety Note" in report
    assert "Processing allowed: false" in report
    assert "Real IoU, F1/Dice, precision, recall, and area error are pending" in report
    assert "Log UNOSAT/UNITAR or GISTDA provider response" in report
    assert "No weak-reference candidate metrics were supplied" in report


def test_real_data_validation_summary_reports_weak_reference_metrics_while_blocked() -> None:
    (
        manifest,
        weak_metrics,
        weak_feature_manifest,
        manual_manifest,
    ) = _bound_weak_reference_evidence()
    context_quality_manifest = pd.DataFrame(
        [
            {
                "manual_reference_overlaps_thailand_adm3_candidate": False,
                "assumptions": (
                    "Manual weak-reference bbox is north of the COD-AB Thailand "
                    "boundary and is retained only as nearby cross-border evidence."
                ),
            }
        ]
    )

    report = build_real_data_validation_summary(
        manifest,
        weak_reference_metrics=weak_metrics,
        weak_reference_feature_manifest=weak_feature_manifest,
        manual_reference_manifest=manual_manifest,
        context_quality_manifest=context_quality_manifest,
    )

    assert "Processing allowed: false" in report
    assert "cross-border calibration metrics generated against a manually digitized weak-reference mask" in report
    assert "## Sentinel-1 Product IDs" in report
    assert "## Integrity And Spatial Scope" in report
    assert "## Manual Reference Mask Metadata" in report
    assert "## Method Assumptions" in report
    assert "## Candidate Metrics" in report
    assert "## Failure Modes" in report
    assert "## Safety Note" in report
    assert "IoU: 0.500000" in report
    assert "F1/Dice: 0.666667" in report
    assert (
        f"Pre-event Sentinel-1 product id: `{MAE_SAI_BASELINE_PRE_PRODUCT_ID}`"
        in report
    )
    assert "Not-official status: confirmed_true" in report
    assert "Confidence: medium" in report
    assert "Source basis: Sentinel-1 visual interpretation" in report
    assert "Digitized by: [blank]" in report
    assert "Digitized at: 2026-07-09" in report
    assert "Notes: uncertain areas excluded" in report
    assert "it is not reviewer qualification" in report
    assert "Weak-reference source integrity verified: true" in report
    assert "Source integrity status: verified_sha256_before_raster_read" in report
    assert "Manual-mask attribute integrity: valid" in report
    assert "Thailand ADM3 candidate overlap: false" in report
    assert "nearby cross-border calibration evidence only" in report
    assert "do not validate flood extent inside Mae Sai Thailand ADM3" in report
    assert "Not an emergency warning" in report


def test_real_data_validation_summary_rejects_unbound_metrics() -> None:
    manifest = build_ingestion_manifest(default_mae_sai_file_manifest_sources())
    metrics = pd.DataFrame(
        [
            {
                "true_positive": 1,
                "false_positive": 0,
                "false_negative": 0,
                "true_negative": 1,
                "iou": 1.0,
                "f1_dice": 1.0,
                "precision": 1.0,
                "recall": 1.0,
                "area_error_ratio": 0.0,
            }
        ]
    )

    with pytest.raises(ValidationReportError, match="require exactly one"):
        build_real_data_validation_summary(
            manifest,
            weak_reference_metrics=metrics,
            weak_reference_feature_manifest=pd.DataFrame([{"pre_product_id": "pre"}]),
        )


def test_real_data_validation_summary_rejects_fabricated_metric_values() -> None:
    manifest, metrics, feature, manual = _bound_weak_reference_evidence()
    metrics.loc[0, "iou"] = 1.0

    with pytest.raises(
        ValidationReportError,
        match="iou does not match its confusion-matrix counts",
    ):
        build_real_data_validation_summary(
            manifest,
            weak_reference_metrics=metrics,
            weak_reference_feature_manifest=feature,
            manual_reference_manifest=manual,
        )


def test_real_data_validation_summary_rejects_substituted_source_checksum() -> None:
    manifest, metrics, feature, manual = _bound_weak_reference_evidence()
    manifest.loc[
        manifest["product_id"] == MAE_SAI_BASELINE_PRE_PRODUCT_ID,
        "sha256",
    ] = "f" * 64

    with pytest.raises(ValidationReportError, match="checksum or study area was substituted"):
        build_real_data_validation_summary(
            manifest,
            weak_reference_metrics=metrics,
            weak_reference_feature_manifest=feature,
            manual_reference_manifest=manual,
        )


def test_real_data_validation_summary_rejects_official_metrics_when_gate_blocked() -> None:
    manifest = build_ingestion_manifest(default_mae_sai_file_manifest_sources())
    metrics = pd.DataFrame(
        [
            {
                "true_positive": 2,
                "false_positive": 1,
                "false_negative": 1,
                "true_negative": 1,
                "iou": 0.5,
                "f1_dice": 0.666667,
                "precision": 0.666667,
                "recall": 0.666667,
                "area_error_ratio": 0.0,
            }
        ]
    )

    with pytest.raises(ValidationReportError, match="official ingestion gate is blocked"):
        build_real_data_validation_summary(manifest, sar_metrics=metrics)


def test_real_data_validation_summary_reports_metrics_when_ready() -> None:
    source = default_mae_sai_file_manifest_sources().iloc[[0, 1, 2]].copy()
    source.loc[:, "geometry_access_status"] = "confirmed"
    source.loc[:, "license_status"] = "confirmed"
    source.loc[:, "redistribution_status"] = "reference_only"
    source.loc[:, "local_path"] = [
        "D:/FloodGuardData/mae_sai/reference_mask.geojson",
        "D:/FloodGuardData/mae_sai/pre_s1.tif",
        "D:/FloodGuardData/mae_sai/post_s1.tif",
    ]
    source.loc[:, "sha256"] = ["a" * 64, "b" * 64, "c" * 64]
    source.loc[:, "source_license_status"] = "confirmed"
    source.loc[:, "reference_mask_status"] = "confirmed"
    manifest = build_ingestion_manifest(source)
    metrics = pd.DataFrame(
        [
            {
                "true_positive": 2,
                "false_positive": 1,
                "false_negative": 1,
                "true_negative": 1,
                "iou": 0.5,
                "f1_dice": 0.666667,
                "precision": 0.666667,
                "recall": 0.666667,
                "area_error_ratio": 0.0,
            }
        ]
    )

    report = build_real_data_validation_summary(manifest, sar_metrics=metrics)

    assert "Processing allowed: true" in report
    assert "IoU: 0.500000" in report
    assert "F1/Dice: 0.666667" in report
    assert "area error ratio: 0.000000" in report


def test_write_real_data_validation_summary_writes_markdown(tmp_path: Path) -> None:
    manifest = build_ingestion_manifest(default_mae_sai_file_manifest_sources())
    output_path = tmp_path / "mae_sai_validation_summary.md"

    written = write_real_data_validation_summary(manifest, output_path)

    assert written == output_path
    assert output_path.read_text(encoding="utf-8").startswith(
        "# Mae Sai Real-Data Validation Summary"
    )


def _bound_weak_reference_evidence(
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    study_area = "Chiang Rai / Mae Sai 2024"
    reference_id = "MS-MANUAL-CROSSBORDER-001"
    pre_sha = "a" * 64
    post_sha = "b" * 64
    reference_sha = "c" * 64
    manifest = build_ingestion_manifest(default_mae_sai_file_manifest_sources())
    manifest.loc[
        manifest["product_id"] == MAE_SAI_BASELINE_PRE_PRODUCT_ID,
        "sha256",
    ] = pre_sha
    manifest.loc[
        manifest["product_id"] == MAE_SAI_BASELINE_POST_PRODUCT_ID,
        "sha256",
    ] = post_sha
    reference_row = {column: "" for column in manifest.columns}
    reference_row.update(
        {
            "source_name": "Manual cross-border weak-reference candidate",
            "study_area": study_area,
            "product_id": reference_id,
            "sha256": reference_sha,
            "processing_allowed": False,
        }
    )
    manifest = pd.concat([manifest, pd.DataFrame([reference_row])], ignore_index=True)

    metrics = pd.DataFrame(
        [
            {
                "study_area": study_area,
                "processing_scope": "weak_reference_real_sentinel1_non_ml_candidate",
                "reference_status": "weak_reference_candidate",
                "metric_status": "candidate_cross_border_calibration_metrics",
                "pre_source_sha256": pre_sha,
                "post_source_sha256": post_sha,
                "reference_sha256": reference_sha,
                "source_integrity_status": "verified_sha256_before_raster_read",
                "measurement_domain": SAR_MEASUREMENT_DOMAIN,
                "log_transform": SAR_LOG_TRANSFORM,
                "radiometric_calibration_status": SAR_RADIOMETRIC_CALIBRATION_STATUS,
                "reference_spatial_relation": "cross_border_calibration_only",
                "reference_in_study_area_overlap": False,
                "reference_distance_to_study_area_km": 5.965378,
                "true_positive": 2,
                "false_positive": 1,
                "false_negative": 1,
                "true_negative": 1,
                "iou": 0.5,
                "f1_dice": 0.666667,
                "precision": 0.666667,
                "recall": 0.666667,
                "area_error_ratio": 0.0,
                "sample_pixel_count": 5,
                "reference_positive_pixel_count": 3,
                "predicted_positive_pixel_count": 3,
                "probability_threshold": 0.5,
                "source_timestamp": "2024-09-15T23:16:01Z",
                "confidence_class": "low",
                "warning_text": (
                    "Cross-border calibration metrics. Non-operational. "
                    "Not official validation. Not field validated."
                ),
                "assumptions": "Synthetic bound test evidence.",
            }
        ]
    )
    feature = pd.DataFrame(
        [
            {
                "study_area": study_area,
                "processing_scope": "weak_reference_real_sentinel1_non_ml_candidate",
                "pre_product_id": MAE_SAI_BASELINE_PRE_PRODUCT_ID,
                "post_product_id": MAE_SAI_BASELINE_POST_PRODUCT_ID,
                "reference_product_id": reference_id,
                "reference_status": "weak_reference_candidate",
                "pre_source_sha256": pre_sha,
                "post_source_sha256": post_sha,
                "reference_sha256": reference_sha,
                "source_integrity_status": "verified_sha256_before_raster_read",
                "measurement_domain": SAR_MEASUREMENT_DOMAIN,
                "log_transform": SAR_LOG_TRANSFORM,
                "radiometric_calibration_status": SAR_RADIOMETRIC_CALIBRATION_STATUS,
                "reference_spatial_relation": "cross_border_calibration_only",
                "reference_in_study_area_overlap": False,
                "reference_distance_to_study_area_km": 5.965378,
                "sample_pixel_count": 5,
                "reference_positive_pixel_count": 3,
                "predicted_positive_pixel_count": 3,
                "sample_width": 5,
                "sample_height": 1,
                "georeferencing_method": "sentinel1_safe_gcps_affine_fit",
                "probability_threshold": 0.5,
                "source_timestamp": "2024-09-15T23:16:01Z",
                "confidence_class": "low",
            }
        ]
    )
    manual = pd.DataFrame(
        [
            {
                "study_area": study_area,
                "reference_id": reference_id,
                "confidence": "medium",
                "source_basis": "Sentinel-1 visual interpretation",
                "digitized_by": "[blank]",
                "digitized_at": "2026-07-09",
                "notes": "uncertain areas excluded",
                "sha256": reference_sha,
                "sha256_status": "recorded",
                "reference_mask_status": "weak_reference_candidate",
                "candidate_readiness_status": "ready_for_candidate_metrics",
                "candidate_validation_metrics_allowed": True,
                "not_official_status": "confirmed_true",
                "attribute_values_status": "valid",
                "attribute_value_blockers": "",
                "spatial_relation": "cross_border_calibration_only",
                "in_study_area_overlap": False,
                "distance_to_study_area_km": 5.965378,
                "spatial_relation_status": "verified_geometry_intersection",
            }
        ]
    )
    return manifest, metrics, feature, manual
