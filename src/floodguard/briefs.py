"""One-page Markdown action brief helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

ACTION_PRIORITY: dict[str, int] = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}

RECOMMENDED_ACTIONS: dict[str, str] = {
    "A": "Pre-position rescue assets, open shelters, issue targeted warnings, and coordinate medical continuity.",
    "B": "Plan closures, detours, pumps, temporary crossings, or road-elevation priorities.",
    "C": "Floodproof facilities, secure backup access, and activate mobile services.",
    "D": "Prioritize drainage, canal maintenance, retention areas, green-blue infrastructure, and local drills.",
    "E": "Monitor conditions, verify field data, and improve source confidence before escalation.",
}

THAI_RECOMMENDED_ACTIONS: dict[str, str] = {
    "A": "จัดเตรียมกำลังช่วยเหลือ เปิดศูนย์พักพิง ส่งคำเตือนเฉพาะพื้นที่ และประสานความต่อเนื่องทางการแพทย์",
    "B": "วางแผนปิดถนน ทางเบี่ยง เครื่องสูบน้ำ จุดข้ามชั่วคราว หรือการยกระดับถนนจุดสำคัญ",
    "C": "ป้องกันสถานบริการสำคัญจากน้ำท่วม จัดทางเข้าถึงสำรอง และเปิดบริการเคลื่อนที่",
    "D": "ให้ความสำคัญกับการระบายน้ำ การบำรุงรักษาคลอง พื้นที่รับน้ำ โครงสร้างพื้นฐานสีเขียว-น้ำเงิน และการซ้อมแผนในพื้นที่",
    "E": "ติดตามสถานการณ์ ตรวจสอบข้อมูลภาคสนาม และปรับปรุงความเชื่อมั่นของแหล่งข้อมูลก่อนยกระดับการดำเนินการ",
}

DEFAULT_ACTIONABLE_BRIEF_CLASSES: tuple[str, ...] = ("A", "B", "C")

PRIORITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "fpps_0_100",
    "action_class",
    "top_reason",
    "confidence_class",
    "assumptions",
)

ROAD_REQUIRED_COLUMNS: tuple[str, ...] = (
    "road_id",
    "subdistrict_id",
    "road_disruption_probability_0_1",
    "top_risk_reason",
)

ACCESS_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "people_losing_15_min_access",
    "people_losing_30_min_access",
    "people_losing_60_min_access",
)

EQUITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "equity_gap_ratio",
    "interpretation_text",
)


class BriefError(ValueError):
    """Raised when action-brief inputs violate the brief contract."""


def select_highest_actionable(priority_frame: pd.DataFrame) -> pd.Series:
    """Select the highest actionable subdistrict by class priority then FPPS."""

    _validate_columns(priority_frame, PRIORITY_REQUIRED_COLUMNS, "priority")
    frame = priority_frame.copy()
    frame["action_class"] = frame["action_class"].astype(str)
    unknown_actions = sorted(set(frame["action_class"]) - set(ACTION_PRIORITY))
    if unknown_actions:
        raise BriefError(f"Unknown action_class value(s): {', '.join(unknown_actions)}")
    frame["fpps_0_100"] = pd.to_numeric(frame["fpps_0_100"], errors="coerce")
    if frame["fpps_0_100"].isna().any():
        raise BriefError("priority fpps_0_100 must be numeric.")
    frame["action_rank"] = frame["action_class"].map(ACTION_PRIORITY)
    return frame.sort_values(
        ["action_rank", "fpps_0_100", "subdistrict_id"],
        ascending=[True, False, True],
    ).iloc[0]


def build_action_brief(
    priority: pd.DataFrame,
    road_risk: pd.DataFrame,
    access_loss: pd.DataFrame,
    equity_gap: pd.DataFrame,
    subdistrict_id: str | None = None,
) -> str:
    """Build a one-page Markdown action brief."""

    _validate_columns(priority, PRIORITY_REQUIRED_COLUMNS, "priority")
    _validate_columns(road_risk, ROAD_REQUIRED_COLUMNS, "road_risk")
    _validate_columns(access_loss, ACCESS_REQUIRED_COLUMNS, "access_loss")
    _validate_columns(equity_gap, EQUITY_REQUIRED_COLUMNS, "equity_gap")

    if subdistrict_id is None:
        selected = select_highest_actionable(priority)
    else:
        matches = priority[priority["subdistrict_id"].astype(str) == subdistrict_id]
        if matches.empty:
            raise BriefError(f"No priority row found for subdistrict_id: {subdistrict_id}")
        selected = matches.iloc[0]

    selected_id = str(selected["subdistrict_id"])
    access_matches = access_loss[access_loss["subdistrict_id"].astype(str) == selected_id]
    if access_matches.empty:
        raise BriefError(f"No access-loss row found for subdistrict_id: {selected_id}")
    equity_matches = equity_gap[equity_gap["subdistrict_id"].astype(str) == selected_id]
    if equity_matches.empty:
        raise BriefError(f"No equity-gap row found for subdistrict_id: {selected_id}")

    access_row = access_matches.iloc[0]
    equity_row = equity_matches.iloc[0]
    roads = road_risk[road_risk["subdistrict_id"].astype(str) == selected_id].copy()
    if not roads.empty:
        roads["road_disruption_probability_0_1"] = pd.to_numeric(
            roads["road_disruption_probability_0_1"],
            errors="coerce",
        )
        roads = roads.sort_values(
            ["road_disruption_probability_0_1", "road_id"],
            ascending=[False, True],
        )

    action_class = str(selected["action_class"])
    recommended_action = RECOMMENDED_ACTIONS.get(action_class)
    if recommended_action is None:
        raise BriefError(f"Unknown action_class value: {action_class}")
    thai_recommended_action = THAI_RECOMMENDED_ACTIONS[action_class]

    title = f"# Action Brief - {selected['subdistrict_name']} ({selected_id})"
    road_lines = _format_road_lines(roads)
    lines = [
        title,
        "",
        "## Priority / ลำดับความสำคัญ",
        "",
        f"- Immediate local action focus: {selected['subdistrict_name']} ({selected_id}).",
        f"- FPPS: {float(selected['fpps_0_100']):.2f}",
        f"- Action class: {action_class}",
        f"- Confidence: {selected['confidence_class']}",
        f"- Top reason: {selected['top_reason']}",
        "",
        "## Access Loss / การสูญเสียการเข้าถึง",
        "",
        f"- People losing 15-minute access: {float(access_row['people_losing_15_min_access']):.0f}",
        f"- People losing 30-minute access: {float(access_row['people_losing_30_min_access']):.0f}",
        f"- People losing 60-minute access: {float(access_row['people_losing_60_min_access']):.0f}",
        "",
        "## Equity Gap / ช่องว่างความเสมอภาคในการอพยพ",
        "",
        f"- Equity gap ratio: {_format_value(equity_row['equity_gap_ratio'])}",
        f"- Interpretation: {equity_row['interpretation_text']}",
        "",
        "## Likely Road Risks / ความเสี่ยงถนนที่อาจถูกตัดขาด",
        "",
        "- Routes likely to need verification:",
        *road_lines,
        "",
        "## Recommended Action / ข้อเสนอการปฏิบัติ",
        "",
        f"- {recommended_action}",
        f"- {thai_recommended_action}",
        "",
        "## Assumptions / สมมติฐาน",
        "",
        f"- {selected['assumptions']}",
        "- Fixture-backed analysis only; this is not an official warning.",
        "",
    ]
    return "\n".join(lines)


def write_action_brief(
    priority: pd.DataFrame,
    road_risk: pd.DataFrame,
    access_loss: pd.DataFrame,
    equity_gap: pd.DataFrame,
    output_dir: str | Path,
    subdistrict_id: str | None = None,
) -> Path:
    """Write an action brief and return the generated path."""

    if subdistrict_id is None:
        selected = select_highest_actionable(priority)
        output_id = str(selected["subdistrict_id"])
    else:
        output_id = subdistrict_id
    target = Path(output_dir) / f"action_brief_{output_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        build_action_brief(priority, road_risk, access_loss, equity_gap, output_id),
        encoding="utf-8",
    )
    return target


def write_action_briefs(
    priority: pd.DataFrame,
    road_risk: pd.DataFrame,
    access_loss: pd.DataFrame,
    equity_gap: pd.DataFrame,
    output_dir: str | Path,
    action_classes: Sequence[str] = DEFAULT_ACTIONABLE_BRIEF_CLASSES,
) -> list[Path]:
    """Write action briefs for all requested action classes and return paths."""

    _validate_columns(priority, PRIORITY_REQUIRED_COLUMNS, "priority")
    requested_classes = tuple(str(action_class) for action_class in action_classes)
    unknown_requested = sorted(set(requested_classes) - set(ACTION_PRIORITY))
    if unknown_requested:
        raise BriefError(
            f"Unknown requested action_class value(s): {', '.join(unknown_requested)}"
        )

    frame = priority.copy()
    frame["action_class"] = frame["action_class"].astype(str)
    unknown_actions = sorted(set(frame["action_class"]) - set(ACTION_PRIORITY))
    if unknown_actions:
        raise BriefError(f"Unknown action_class value(s): {', '.join(unknown_actions)}")
    frame["fpps_0_100"] = pd.to_numeric(frame["fpps_0_100"], errors="coerce")
    if frame["fpps_0_100"].isna().any():
        raise BriefError("priority fpps_0_100 must be numeric.")

    selected = frame[frame["action_class"].isin(requested_classes)].copy()
    selected["action_rank"] = selected["action_class"].map(ACTION_PRIORITY)
    selected = selected.sort_values(
        ["action_rank", "fpps_0_100", "subdistrict_id"],
        ascending=[True, False, True],
    )

    paths: list[Path] = []
    for _, row in selected.iterrows():
        paths.append(
            write_action_brief(
                priority,
                road_risk,
                access_loss,
                equity_gap,
                output_dir,
                subdistrict_id=str(row["subdistrict_id"]),
            )
        )
    return paths


def _validate_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise BriefError(
            f"Missing required {frame_name} column(s): {', '.join(missing)}"
        )


def _format_road_lines(roads: pd.DataFrame) -> list[str]:
    if roads.empty:
        return ["- No road-risk segment is linked to this subdistrict in the fixture."]
    return [
        (
            f"- {row['road_id']}: "
            f"{float(row['road_disruption_probability_0_1']):.3f} "
            f"({row['top_risk_reason']})"
        )
        for _, row in roads.iterrows()
    ]


def _format_value(value: object) -> str:
    if pd.isna(value):
        return "unavailable"
    return f"{float(value):.3f}"
