from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.mae_sai_brief import (
    MAE_SAI_WEAK_REFERENCE_WARNING,
    MaeSaiActionBriefError,
    build_mae_sai_action_brief,
    write_mae_sai_action_brief,
)
from floodguard.scoring import score_subdistricts


OUTPUTS = Path(__file__).parents[1] / "outputs"


def load_evidence() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    decision_inputs = pd.read_csv(
        OUTPUTS / "mae_sai_subdistrict_flood_inputs.csv", dtype=str
    ).fillna("")
    return (
        score_subdistricts(decision_inputs),
        pd.read_csv(OUTPUTS / "mae_sai_weak_sar_feature_manifest.csv", dtype=str).fillna(""),
        pd.read_csv(OUTPUTS / "mae_sai_weak_baseline_metrics.csv", dtype=str).fillna(""),
        pd.read_csv(OUTPUTS / "manual_reference_mask_manifest.csv", dtype=str).fillna(""),
        pd.read_csv(OUTPUTS / "mae_sai_weak_label_ml_metrics.csv", dtype=str).fillna(""),
    )


def test_build_mae_sai_action_brief_contains_real_evidence_and_warnings() -> None:
    priority, features, baseline, manual, ml = load_evidence()

    brief = build_mae_sai_action_brief(
        priority,
        features,
        baseline,
        manual,
        weak_label_ml_metrics=ml,
    )

    assert "# Mae Sai Weak-Reference Action Brief" in brief
    assert "MS-WR-001" in brief
    assert MAE_SAI_WEAK_REFERENCE_WARNING in brief
    assert "Executive Summary / บทสรุปสำหรับผู้ตัดสินใจ" in brief
    assert "FPPS: 6.19/100" in brief
    assert "Action class: E" in brief
    assert "mean non-ML flood-probability proxy of 4.7%" in brief
    assert "Source: CDSE Sentinel-1 weak-reference SAR baseline" in brief
    assert "b09f96ca-4a60-43e7-9b8d-158022f0e5bf" in brief
    assert "20a9c3b8-37df-46d5-81d8-d63c7e460225" in brief
    assert "IoU 0.006" in brief
    assert "| IoU | 0.005 | 0.223 |" in brief
    assert "severe overprediction" in brief
    assert "not official validation truth" in brief
    assert "not field validated" in brief


def test_missing_real_context_is_explicit_not_reported_as_zero_impact() -> None:
    priority, features, baseline, manual, ml = load_evidence()

    brief = build_mae_sai_action_brief(
        priority,
        features,
        baseline,
        manual,
        weak_label_ml_metrics=ml,
    )

    assert "no real Mae Sai road segments have been joined" in brief
    assert "not evidence that roads are safe" in brief
    assert "no real Mae Sai routing graph" in brief
    assert "not evidence of uninterrupted access" in brief
    assert "vulnerable and non-vulnerable access-loss denominators are not yet joined" in brief
    assert "not evidence of no equity gap" in brief


def test_brief_includes_bilingual_recommended_actions() -> None:
    priority, features, baseline, manual, ml = load_evidence()

    brief = build_mae_sai_action_brief(
        priority,
        features,
        baseline,
        manual,
        weak_label_ml_metrics=ml,
    )

    assert "Recommended Local Actions / ข้อเสนอการปฏิบัติในพื้นที่" in brief
    assert "Monitor conditions, verify field data" in brief
    assert "ติดตามสถานการณ์" in brief
    assert "ห้ามใช้เอกสารฉบับนี้เพียงอย่างเดียว" in brief


def test_ml_candidate_is_not_misrepresented_as_current_fpps_input() -> None:
    priority, features, baseline, manual, ml = load_evidence()

    brief = build_mae_sai_action_brief(
        priority,
        features,
        baseline,
        manual,
        weak_label_ml_metrics=ml,
    )

    assert "Decision-layer eligibility flag: true" in brief
    assert "current FPPS still uses the non-ML mean probability proxy" in brief
    assert "Not official labels. Not field validation." in brief


def test_brief_rejects_reference_status_promotion() -> None:
    priority, features, baseline, manual, ml = load_evidence()
    manual.loc[0, "reference_mask_status"] = "official_validation_truth"

    with pytest.raises(MaeSaiActionBriefError, match="weak_reference_candidate"):
        build_mae_sai_action_brief(
            priority,
            features,
            baseline,
            manual,
            weak_label_ml_metrics=ml,
        )


def test_brief_rejects_mismatched_evidence_counts() -> None:
    priority, features, baseline, manual, ml = load_evidence()
    baseline.loc[0, "sample_pixel_count"] = "65535"

    with pytest.raises(MaeSaiActionBriefError, match="do not reconcile"):
        build_mae_sai_action_brief(
            priority,
            features,
            baseline,
            manual,
            weak_label_ml_metrics=ml,
        )


def test_write_mae_sai_action_brief_uses_expected_name(tmp_path: Path) -> None:
    priority, features, baseline, manual, ml = load_evidence()

    target = write_mae_sai_action_brief(
        priority,
        features,
        baseline,
        manual,
        tmp_path,
        weak_label_ml_metrics=ml,
    )

    assert target.name == "mae_sai_action_brief_MS-WR-001.md"
    assert target.read_text(encoding="utf-8").startswith(
        "# Mae Sai Weak-Reference Action Brief"
    )
