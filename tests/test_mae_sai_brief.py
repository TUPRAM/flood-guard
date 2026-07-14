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
from floodguard.flood_aggregation import build_mae_sai_weak_decision_inputs
from floodguard.scoring import score_subdistricts


OUTPUTS = Path(__file__).parents[1] / "outputs"


def load_evidence() -> tuple[pd.DataFrame, ...]:
    decision_inputs = pd.read_csv(
        OUTPUTS / "mae_sai_subdistrict_flood_inputs.csv", dtype=str
    ).fillna("")
    return (
        score_subdistricts(decision_inputs),
        pd.read_csv(OUTPUTS / "mae_sai_weak_sar_feature_manifest.csv", dtype=str).fillna(""),
        pd.read_csv(OUTPUTS / "mae_sai_weak_baseline_metrics.csv", dtype=str).fillna(""),
        pd.read_csv(OUTPUTS / "manual_reference_mask_manifest.csv", dtype=str).fillna(""),
        pd.read_csv(OUTPUTS / "mae_sai_weak_label_ml_metrics.csv", dtype=str).fillna(""),
        pd.read_csv(OUTPUTS / "mae_sai_adm3_sar_context.csv", dtype=str).fillna(""),
        pd.read_csv(OUTPUTS / "mae_sai_road_risk.csv", dtype=str).fillna(""),
        pd.read_csv(OUTPUTS / "mae_sai_access_loss.csv", dtype=str).fillna(""),
        pd.read_csv(OUTPUTS / "mae_sai_equity_gap.csv", dtype=str).fillna(""),
    )


def build_current_brief() -> str:
    priority, features, baseline, manual, ml, adm3, roads, access, equity = load_evidence()
    return build_mae_sai_action_brief(
        priority,
        features,
        baseline,
        manual,
        weak_label_ml_metrics=ml,
        adm3_sar_context=adm3,
        road_risk=roads,
        access_loss=access,
        equity_gap=equity,
    )


def test_build_mae_sai_action_brief_contains_real_evidence_and_warnings() -> None:
    brief = build_current_brief()

    assert "# Mae Sai Weak-Reference Action Brief" in brief
    assert "TH570906" in brief
    assert "Wiang Phang Kham" in brief
    assert MAE_SAI_WEAK_REFERENCE_WARNING in brief
    assert "Executive Summary / บทสรุปสำหรับผู้ตัดสินใจ" in brief
    assert "FPPS: 31.74/100" in brief
    assert "Action class: E" in brief
    assert "mean non-ML flood-probability proxy of 7.1%" in brief
    assert "WorldPop 2020" in brief
    assert "b09f96ca-4a60-43e7-9b8d-158022f0e5bf" in brief
    assert "20a9c3b8-37df-46d5-81d8-d63c7e460225" in brief
    assert "IoU 0.006" in brief
    assert "| IoU | 0.005 | 0.223 |" in brief
    assert "severe overprediction" in brief
    assert "does not overlap the official Thailand ADM3 geometry" in brief
    assert "not field validated" in brief.lower()
    assert "Ko Chang has the highest modeled 30-minute access loss" in brief
    assert "bridge-tagged" in brief
    assert "terrain/remoteness proxy" in brief


def test_missing_real_context_is_explicit_not_reported_as_zero_impact() -> None:
    _, features, baseline, manual, ml, *_ = load_evidence()
    weak_priority = score_subdistricts(
        build_mae_sai_weak_decision_inputs(features, manual)
    )

    brief = build_mae_sai_action_brief(
        weak_priority,
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
    brief = build_current_brief()

    assert "Recommended Local Actions / ข้อเสนอการปฏิบัติในพื้นที่" in brief
    assert "Monitor conditions, verify field data" in brief
    assert "ติดตามสถานการณ์" in brief
    assert "ห้ามใช้เอกสารฉบับนี้เพียงอย่างเดียว" in brief


def test_ml_candidate_is_not_misrepresented_as_current_fpps_input() -> None:
    brief = build_current_brief()

    assert "Decision-layer eligibility flag: false" in brief
    assert "current FPPS still uses the non-ML mean probability proxy" in brief
    assert "Not official labels. Not field validation." in brief


def test_brief_rejects_reference_status_promotion() -> None:
    priority, features, baseline, manual, ml, adm3, roads, access, equity = load_evidence()
    manual.loc[0, "reference_mask_status"] = "official_validation_truth"

    with pytest.raises(MaeSaiActionBriefError, match="weak_reference_candidate"):
        build_mae_sai_action_brief(
            priority,
            features,
            baseline,
            manual,
            weak_label_ml_metrics=ml,
            adm3_sar_context=adm3,
            road_risk=roads,
            access_loss=access,
            equity_gap=equity,
        )


def test_brief_rejects_legacy_weak_ml_decision_eligibility() -> None:
    priority, features, baseline, manual, ml, adm3, roads, access, equity = load_evidence()
    ml.loc[0, "can_feed_decision_layer"] = "True"

    with pytest.raises(MaeSaiActionBriefError, match="must remain false"):
        build_mae_sai_action_brief(
            priority,
            features,
            baseline,
            manual,
            weak_label_ml_metrics=ml,
            adm3_sar_context=adm3,
            road_risk=roads,
            access_loss=access,
            equity_gap=equity,
        )


def test_brief_rejects_mismatched_evidence_counts() -> None:
    priority, features, baseline, manual, ml, adm3, roads, access, equity = load_evidence()
    baseline.loc[0, "sample_pixel_count"] = "65535"

    with pytest.raises(MaeSaiActionBriefError, match="do not reconcile"):
        build_mae_sai_action_brief(
            priority,
            features,
            baseline,
            manual,
            weak_label_ml_metrics=ml,
            adm3_sar_context=adm3,
            road_risk=roads,
            access_loss=access,
            equity_gap=equity,
        )


def test_write_mae_sai_action_brief_uses_expected_name(tmp_path: Path) -> None:
    priority, features, baseline, manual, ml, adm3, roads, access, equity = load_evidence()

    target = write_mae_sai_action_brief(
        priority,
        features,
        baseline,
        manual,
        tmp_path,
        weak_label_ml_metrics=ml,
        adm3_sar_context=adm3,
        road_risk=roads,
        access_loss=access,
        equity_gap=equity,
    )

    assert target.name == "mae_sai_action_brief_TH570906.md"
    assert target.read_text(encoding="utf-8").startswith(
        "# Mae Sai Weak-Reference Action Brief"
    )
