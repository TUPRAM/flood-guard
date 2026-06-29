from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.validation import (
    FUTURE_METRIC_PLACEHOLDERS,
    ValidationReportError,
    build_validation_summary,
    write_validation_summary,
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
