from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.briefs import (
    BriefError,
    build_action_brief,
    select_highest_actionable,
    write_action_brief,
)

OUTPUTS = Path(__file__).parents[1] / "outputs"


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv(OUTPUTS / "sample_priority_scores.csv"),
        pd.read_csv(OUTPUTS / "sample_road_risk.csv"),
        pd.read_csv(OUTPUTS / "sample_access_loss.csv"),
        pd.read_csv(OUTPUTS / "sample_equity_gap.csv"),
    )


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
