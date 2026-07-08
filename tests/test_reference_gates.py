from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.reference_gates import (
    REFERENCE_GATE_OUTPUT_COLUMNS,
    ReferenceGateError,
    build_reference_gate_report,
    default_reference_gate_rows,
    write_reference_gate_report,
)

REPO_ROOT = Path(__file__).parents[1]


def test_default_reference_gate_rows_remain_blocked() -> None:
    report = build_reference_gate_report(default_reference_gate_rows())

    assert list(report.columns) == list(REFERENCE_GATE_OUTPUT_COLUMNS)
    assert set(report["reference_validation_allowed"]) == {False}
    assert set(report["ml_label_allowed"]) == {False}
    assert set(report["gate_status"]) == {"blocked"}
    assert (
        report["source_name"]
        == "Sentinel Asia / MBRSC Northern Thailand 2024 public shapefile"
    ).any()
    assert report["reason_blocked"].str.contains("geometry access not confirmed").any()
    assert report["reason_blocked"].str.contains(
        "blocking_decision is not cleared for local validation"
    ).all()


def test_reference_gate_can_clear_validation_without_ml_label_use() -> None:
    frame = pd.DataFrame(
        [
            {
                "source_name": "UNOSAT/UNITAR Mae Sai reference target",
                "study_area": "Chiang Rai / Mae Sai 2024",
                "request_status": "response_received",
                "request_sent_date": "2026-07-03",
                "response_date": "2026-07-08",
                "geometry_access": "confirmed",
                "local_analysis_allowed": "yes",
                "derived_metrics_allowed": "yes",
                "screenshots_demo_allowed": "yes",
                "redistribution_allowed": "reference_only",
                "citation_required": "required",
                "ml_label_use_allowed": "no",
                "blocking_decision": "cleared_for_local_validation",
            }
        ]
    )

    report = build_reference_gate_report(frame)

    assert bool(report.loc[0, "reference_validation_allowed"]) is True
    assert bool(report.loc[0, "ml_label_allowed"]) is False
    assert report.loc[0, "gate_status"] == "cleared_for_local_validation"
    assert report.loc[0, "reason_blocked"] == "none"


def test_reference_gate_clears_ml_label_only_when_explicitly_allowed() -> None:
    frame = default_reference_gate_rows().iloc[[0]].copy()
    frame.loc[:, "request_status"] = "response_received"
    frame.loc[:, "response_date"] = "2026-07-08"
    frame.loc[:, "geometry_access"] = "granted"
    frame.loc[:, "local_analysis_allowed"] = "allowed"
    frame.loc[:, "derived_metrics_allowed"] = "allowed"
    frame.loc[:, "screenshots_demo_allowed"] = "allowed"
    frame.loc[:, "redistribution_allowed"] = "reference_only"
    frame.loc[:, "citation_required"] = "yes"
    frame.loc[:, "ml_label_use_allowed"] = "yes"
    frame.loc[:, "blocking_decision"] = "cleared_reference_only"

    report = build_reference_gate_report(frame)

    assert bool(report.loc[0, "reference_validation_allowed"]) is True
    assert bool(report.loc[0, "ml_label_allowed"]) is True


def test_reference_gate_filter_by_study_area() -> None:
    report = build_reference_gate_report(
        default_reference_gate_rows(),
        study_area_contains="Chiang Rai",
    )

    assert len(report) == 3
    assert report["study_area"].str.contains("Chiang Rai").all()


def test_reference_gate_rejects_missing_columns() -> None:
    frame = default_reference_gate_rows().drop(columns=["geometry_access"])

    with pytest.raises(ReferenceGateError, match="geometry_access"):
        build_reference_gate_report(frame)


def test_write_reference_gate_report_writes_csv(tmp_path: Path) -> None:
    output = tmp_path / "reference_gate_report.csv"

    written = write_reference_gate_report(default_reference_gate_rows(), output)

    assert written == output
    report = pd.read_csv(output)
    assert "reason_blocked" in report.columns
    assert len(report) == len(default_reference_gate_rows())


def test_gate_scripts_do_not_download_or_read_imagery() -> None:
    for path in (
        REPO_ROOT / "scripts" / "check_real_data_gates.py",
        REPO_ROOT / "scripts" / "validate_mae_sai_file_manifest.py",
        REPO_ROOT / "src" / "floodguard" / "reference_gates.py",
    ):
        source = path.read_text(encoding="utf-8")
        for token in ("urlopen(", "requests.", "urlretrieve(", "rasterio.open", "gdal."):
            assert token not in source
