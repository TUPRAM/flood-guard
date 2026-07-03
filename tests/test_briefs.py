from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.briefs import (
    BriefError,
    THAI_RECOMMENDED_ACTIONS,
    build_action_brief,
    select_highest_actionable,
    write_action_brief,
    write_action_briefs,
)

OUTPUTS = Path(__file__).parents[1] / "outputs"


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv(OUTPUTS / "sample_priority_scores.csv"),
        pd.read_csv(OUTPUTS / "sample_road_risk.csv"),
        pd.read_csv(OUTPUTS / "sample_access_loss.csv"),
        pd.read_csv(OUTPUTS / "sample_equity_gap.csv"),
    )


def load_theos2_context() -> pd.DataFrame:
    return pd.read_csv(OUTPUTS / "theos2_selected_file_manifest.csv", dtype=str).fillna("")


def test_select_highest_actionable_uses_class_before_raw_fpps() -> None:
    priority, _, _, _ = load_frames()

    selected = select_highest_actionable(priority)

    assert selected["subdistrict_id"] == "FG-TB-001"
    assert selected["action_class"] == "A"
    assert priority.loc[priority["subdistrict_id"] == "FG-TB-005", "fpps_0_100"].item() > selected["fpps_0_100"]


def test_build_action_brief_includes_priority_access_equity_and_roads() -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()

    brief = build_action_brief(priority, road_risk, access_loss, equity_gap)

    assert "# Action Brief - River Market (FG-TB-001)" in brief
    assert "Priority / ลำดับความสำคัญ" in brief
    assert "Access Loss / การสูญเสียการเข้าถึง" in brief
    assert "Equity Gap / ช่องว่างความเสมอภาคในการอพยพ" in brief
    assert "Likely Road Risks / ความเสี่ยงถนนที่อาจถูกตัดขาด" in brief
    assert "Recommended Action / ข้อเสนอการปฏิบัติ" in brief
    assert "Assumptions / สมมติฐาน" in brief
    assert "Immediate local action focus" in brief
    assert "Routes likely to need verification" in brief
    assert "FPPS: 81.60" in brief
    assert "Action class: A" in brief
    assert "People losing 30-minute access: 100" in brief
    assert "Equity gap ratio: 1.000" in brief
    assert "FG-RD-001: 0.832" in brief
    assert "Pre-position rescue assets" in brief
    assert THAI_RECOMMENDED_ACTIONS["A"] in brief
    assert "Fixture-backed analysis only" in brief
    assert "not an official warning" in brief


def test_build_action_brief_supports_manual_subdistrict_id() -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()

    brief = build_action_brief(
        priority,
        road_risk,
        access_loss,
        equity_gap,
        subdistrict_id="FG-TB-002",
    )

    assert "# Action Brief - Bridge Junction (FG-TB-002)" in brief
    assert "Plan closures, detours" in brief
    assert THAI_RECOMMENDED_ACTIONS["B"] in brief


def test_build_action_brief_can_include_theos2_optical_context() -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()

    brief = build_action_brief(
        priority,
        road_risk,
        access_loss,
        equity_gap,
        theos2_context=load_theos2_context(),
    )

    assert "## Optical Context" in brief
    assert "THEOS-2 previews are local optical context only" in brief
    assert "not flood validation" in brief
    assert "not reference masks" in brief
    assert "theos2_previews/theos2_preview_" in brief


def test_write_action_brief_uses_selected_id_in_filename(tmp_path: Path) -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()

    written = write_action_brief(
        priority,
        road_risk,
        access_loss,
        equity_gap,
        tmp_path,
    )

    assert written.name == "action_brief_FG-TB-001.md"
    assert written.exists()


def test_write_action_briefs_generates_default_actionable_batch(tmp_path: Path) -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()

    written = write_action_briefs(
        priority,
        road_risk,
        access_loss,
        equity_gap,
        tmp_path,
    )

    assert [path.name for path in written] == [
        "action_brief_FG-TB-001.md",
        "action_brief_FG-TB-002.md",
        "action_brief_FG-TB-003.md",
    ]
    assert not (tmp_path / "action_brief_FG-TB-004.md").exists()
    assert not (tmp_path / "action_brief_FG-TB-005.md").exists()
    clinic_brief = (tmp_path / "action_brief_FG-TB-003.md").read_text(encoding="utf-8")
    assert THAI_RECOMMENDED_ACTIONS["C"] in clinic_brief
    assert "Recommended Action / ข้อเสนอการปฏิบัติ" in clinic_brief


def test_build_action_brief_rejects_missing_subdistrict() -> None:
    priority, road_risk, access_loss, equity_gap = load_frames()

    with pytest.raises(BriefError, match="No priority row"):
        build_action_brief(
            priority,
            road_risk,
            access_loss,
            equity_gap,
            subdistrict_id="MISSING",
        )
