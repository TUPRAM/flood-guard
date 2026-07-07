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
from floodguard.ingestion import (
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
    assert "Processing allowed: false" in report
    assert "Real IoU, F1/Dice, precision, recall, and area error are pending" in report
    assert "Log UNOSAT/UNITAR or GISTDA provider response" in report


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
