"""Validation report helpers for FloodGuard outputs."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from floodguard.ingestion import (
    IngestionPlanError,
    validate_mae_sai_file_manifest_ready,
)
from floodguard.sar_baseline import MASK_METRIC_COLUMNS

ACTION_PRIORITY: dict[str, int] = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
ACCESS_THRESHOLDS: tuple[int, ...] = (15, 30, 60)

PRIORITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "fpps_0_100",
    "action_class",
    "confidence_class",
)

ROAD_RISK_REQUIRED_COLUMNS: tuple[str, ...] = (
    "road_id",
    "subdistrict_id",
    "road_disruption_probability_0_1",
)

ACCESS_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "people_losing_15_min_access",
    "people_losing_30_min_access",
    "people_losing_60_min_access",
)

EQUITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "equity_gap_ratio",
)

RANK_INSTABILITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "default_rank",
    "best_rank",
    "worst_rank",
    "rank_range",
    "default_action_class",
    "confidence_class",
    "ranking_unstable",
)

FUTURE_METRIC_PLACEHOLDERS: tuple[str, ...] = (
    "IoU",
    "F1/Dice",
    "precision",
    "recall",
    "area error",
    "Brier score",
    "calibration",
    "road closure precision/recall",
    "score sensitivity",
)


class ValidationReportError(ValueError):
    """Raised when validation-report inputs violate the report contract."""


def build_validation_summary(
    priority: pd.DataFrame,
    road_risk: pd.DataFrame,
    access_loss: pd.DataFrame,
    equity_gap: pd.DataFrame,
    rank_instability: pd.DataFrame | None = None,
) -> str:
    """Build a Markdown validation summary from fixture-backed outputs."""

    _validate_columns(priority, PRIORITY_REQUIRED_COLUMNS, "priority")
    _validate_columns(road_risk, ROAD_RISK_REQUIRED_COLUMNS, "road_risk")
    _validate_columns(access_loss, ACCESS_REQUIRED_COLUMNS, "access_loss")
    _validate_columns(equity_gap, EQUITY_REQUIRED_COLUMNS, "equity_gap")

    priority_frame = priority.copy()
    priority_frame["fpps_0_100"] = pd.to_numeric(
        priority_frame["fpps_0_100"],
        errors="coerce",
    )
    if priority_frame["fpps_0_100"].isna().any():
        raise ValidationReportError("priority fpps_0_100 must be numeric.")

    top_actionable = _select_top_actionable(priority_frame)
    action_counts = _ordered_counts(priority_frame["action_class"], ("A", "B", "C", "D", "E"))
    confidence_counts = _ordered_counts(
        priority_frame["confidence_class"],
        ("high", "medium", "low"),
    )

    road_probability = pd.to_numeric(
        road_risk["road_disruption_probability_0_1"],
        errors="coerce",
    )
    if road_probability.isna().any():
        raise ValidationReportError(
            "road_risk road_disruption_probability_0_1 must be numeric."
        )
    high_risk_road_count = int((road_probability >= 0.7).sum())

    access_totals = {
        threshold: float(access_loss[f"people_losing_{threshold}_min_access"].sum())
        for threshold in ACCESS_THRESHOLDS
    }
    worst_access = access_loss.sort_values(
        ["people_losing_30_min_access", "subdistrict_id"],
        ascending=[False, True],
    ).iloc[0]

    numeric_equity = pd.to_numeric(equity_gap["equity_gap_ratio"], errors="coerce")
    if numeric_equity.notna().any():
        strongest_equity = equity_gap.loc[numeric_equity.idxmax()]
        max_equity_ratio = float(numeric_equity.max())
        strongest_equity_label = (
            f"{strongest_equity['subdistrict_id']} / "
            f"{strongest_equity['subdistrict_name']}"
        )
    else:
        max_equity_ratio = float("nan")
        strongest_equity_label = "unavailable"

    sensitivity_lines = _build_sensitivity_lines(priority_frame, rank_instability)

    lines = [
        "# FloodGuard Validation Summary",
        "",
        "Generated from fixture-backed outputs. This is not a real flood validation report.",
        "",
        "## Decision Narrative",
        "",
        (
            "- Current status: fixture-backed decision demo for prioritization, "
            "scenario comparison, access loss, equity gap, road risk, and action briefs."
        ),
        (
            "- The dashboard and this report show the decision layer working end to end, "
            "but they do not prove real flood-detection accuracy."
        ),
        "- This output is non-operational, not an official warning, and not a real-time sensor.",
        "",
        "## What The Fixture Proves",
        "",
        "- FPPS scoring, A-E action class assignment, and top-reason generation are deterministic.",
        "- Road-risk, access-loss, equity-gap, scenario, and sensitivity outputs can be joined into dashboard-ready GeoJSON.",
        "- Actionable brief selection favors A/B/C decision classes over a low-confidence numeric score leader.",
        "",
        "## Data Readiness Narrative",
        "",
        (
            "- Local THEOS-2, Sentinel-1, and DEM assets are cataloged as context/readiness "
            "lanes with checksums or blocker states where available."
        ),
        (
            "- Sentinel-1 and DEM context quicklooks are not flood labels, not reference masks, "
            "and not agency flood products."
        ),
        (
            "- Real Mae Sai validation is blocked because provider response pending items still "
            "control reference-mask use, local processing, and redistribution/reference-only terms."
        ),
        "",
        "## What Remains Blocked",
        "",
        "- Real IoU, F1/Dice, precision, recall, and area error remain blocked until a legal reference mask exists.",
        "- Real Sentinel-1 baseline processing remains blocked until local paths, checksums, timing, provenance, and reference-mask gates pass.",
        "- Real-data ML remains blocked until the non-ML baseline and legal label gates pass.",
        "",
        "## Real Mae Sai Gate Update",
        "",
        "- Required before real validation: geometry access, local validation permission, derived metrics permission, screenshots/demo permission, redistribution or reference-only status, ML-label use status, citation, and disclaimers.",
        "- Provider response pending: update `docs/reference_mask_licensing_log.md` and `docs/licensing_outreach_status.md` when UNOSAT/UNITAR or GISTDA replies arrive.",
        "",
        "## Fixture Coverage",
        "",
        f"- Priority rows: {len(priority_frame)}",
        f"- Road-risk rows: {len(road_risk)}",
        f"- Access-loss rows: {len(access_loss)}",
        f"- Equity-gap rows: {len(equity_gap)}",
        "",
        "## Priority Score Summary",
        "",
        (
            f"- Top actionable subdistrict: {top_actionable['subdistrict_id']} / "
            f"{top_actionable['subdistrict_name']}"
        ),
        f"- Top actionable class: {top_actionable['action_class']}",
        f"- Top actionable FPPS: {float(top_actionable['fpps_0_100']):.2f}",
        f"- Max FPPS: {float(priority_frame['fpps_0_100'].max()):.2f}",
        f"- Mean FPPS: {float(priority_frame['fpps_0_100'].mean()):.2f}",
        f"- Action-class counts: {_format_counts(action_counts)}",
        f"- Confidence counts: {_format_counts(confidence_counts)}",
        "",
        "## Road Risk Summary",
        "",
        f"- High-risk road count (>= 0.70): {high_risk_road_count}",
        f"- Max road risk: {float(road_probability.max()):.3f}",
        f"- Mean road risk: {float(road_probability.mean()):.3f}",
        "",
        "## Access Loss Summary",
        "",
        f"- People losing 15-minute access: {access_totals[15]:.0f}",
        f"- People losing 30-minute access: {access_totals[30]:.0f}",
        f"- People losing 60-minute access: {access_totals[60]:.0f}",
        (
            "- Worst 30-minute access-loss subdistrict: "
            f"{worst_access['subdistrict_id']} / {worst_access['subdistrict_name']} "
            f"({float(worst_access['people_losing_30_min_access']):.0f} people)"
        ),
        "",
        "## Equity Gap Summary",
        "",
        f"- Max numeric equity-gap ratio: {_format_float(max_equity_ratio, 3)}",
        f"- Strongest equity-gap subdistrict: {strongest_equity_label}",
        "",
        "## Sensitivity Summary",
        "",
        *sensitivity_lines,
        "",
        "## Future Validation Metrics",
        "",
    ]
    for placeholder in FUTURE_METRIC_PLACEHOLDERS:
        if placeholder == "score sensitivity":
            lines.append(
                "- score sensitivity: implemented for fixtures; real calibration remains pending."
            )
        else:
            lines.append(f"- {placeholder}: pending real reference data.")
    lines.extend(
        [
            "",
            "## Assumptions",
            "",
            "- Current metrics are generated from synthetic fixtures only.",
            "- Road-risk outputs are heuristic probabilities, not observed closures.",
            "- Flood extent metrics remain placeholders until real reference masks exist.",
            "",
        ]
    )
    return "\n".join(lines)


def write_validation_summary(
    priority: pd.DataFrame,
    road_risk: pd.DataFrame,
    access_loss: pd.DataFrame,
    equity_gap: pd.DataFrame,
    output_path: str | Path,
    rank_instability: pd.DataFrame | None = None,
) -> Path:
    """Write a Markdown validation summary and return the output path."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        build_validation_summary(
            priority,
            road_risk,
            access_loss,
            equity_gap,
            rank_instability=rank_instability,
        ),
        encoding="utf-8",
    )
    return target


def build_real_data_validation_summary(
    file_manifest: pd.DataFrame,
    sar_metrics: pd.DataFrame | None = None,
    title: str = "Mae Sai Real-Data Validation Summary",
) -> str:
    """Build a real-data validation report or a blocked status report."""

    lines = [
        f"# {title}",
        "",
        "Status: blocked until reference-mask and file-level ingestion gates pass.",
        "",
        "This report is non-operational and must not be used as an official warning.",
        "",
        "## Ingestion Gate",
        "",
    ]
    try:
        ready_rows = validate_mae_sai_file_manifest_ready(file_manifest)
    except IngestionPlanError as exc:
        lines.extend(
            [
                "- Processing allowed: false",
                f"- Blocking reason: {exc}",
                "- Real IoU, F1/Dice, precision, recall, and area error are pending.",
                "",
                "## Required Next Action",
                "",
                "- Log UNOSAT/UNITAR or GISTDA provider response.",
                "- Record legal reference-mask status.",
                "- Record local paths and SHA-256 checksums outside Git.",
                "- Rebuild `outputs/mae_sai_real_data_file_manifest.csv`.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "- Processing allowed: true",
            f"- Ready source rows: {len(ready_rows)}",
            "- Reference mask and Sentinel-1 source rows passed file-level gates.",
            "",
            "## Source Rows",
            "",
        ]
    )
    for _, row in ready_rows.iterrows():
        lines.append(
            f"- {row['source_name']}: product_id `{row['product_id']}`, "
            f"local_path `{row['local_path']}`"
        )
    lines.extend(["", "## Flood-Mask Metrics", ""])
    if sar_metrics is None:
        lines.extend(
            [
                "- IoU: pending gated baseline run.",
                "- F1/Dice: pending gated baseline run.",
                "- precision: pending gated baseline run.",
                "- recall: pending gated baseline run.",
                "- area error: pending gated baseline run.",
                "",
            ]
        )
        return "\n".join(lines)

    _validate_columns(sar_metrics, MASK_METRIC_COLUMNS, "sar_metrics")
    if sar_metrics.empty:
        raise ValidationReportError("sar_metrics must contain at least one row.")
    metrics = sar_metrics.iloc[0]
    lines.extend(
        [
            f"- IoU: {float(metrics['iou']):.6f}",
            f"- F1/Dice: {float(metrics['f1_dice']):.6f}",
            f"- precision: {float(metrics['precision']):.6f}",
            f"- recall: {float(metrics['recall']):.6f}",
            f"- area error ratio: {float(metrics['area_error_ratio']):.6f}",
            "",
            "## Assumptions",
            "",
            "- Metrics are valid only for the logged reference-mask and source-product versions.",
            "- Output remains non-operational and not an official warning.",
            "",
        ]
    )
    return "\n".join(lines)


def write_real_data_validation_summary(
    file_manifest: pd.DataFrame,
    output_path: str | Path,
    sar_metrics: pd.DataFrame | None = None,
    title: str = "Mae Sai Real-Data Validation Summary",
) -> Path:
    """Write the real-data validation status/metric report."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        build_real_data_validation_summary(
            file_manifest,
            sar_metrics=sar_metrics,
            title=title,
        ),
        encoding="utf-8",
    )
    return target


def _select_top_actionable(priority: pd.DataFrame) -> pd.Series:
    unknown_actions = sorted(set(priority["action_class"].astype(str)) - set(ACTION_PRIORITY))
    if unknown_actions:
        raise ValidationReportError(
            f"Unknown action_class value(s): {', '.join(unknown_actions)}"
        )
    ranked = priority.copy()
    ranked["action_rank"] = ranked["action_class"].map(ACTION_PRIORITY)
    return ranked.sort_values(
        ["action_rank", "fpps_0_100", "subdistrict_id"],
        ascending=[True, False, True],
    ).iloc[0]


def _build_sensitivity_lines(
    priority_frame: pd.DataFrame,
    rank_instability: pd.DataFrame | None,
) -> list[str]:
    numeric_top = priority_frame.sort_values(
        ["fpps_0_100", "subdistrict_id"],
        ascending=[False, True],
    ).iloc[0]
    top_actionable = _select_top_actionable(priority_frame)
    disclosure = (
        f"- Top numeric FPPS row: {numeric_top['subdistrict_id']} / "
        f"{numeric_top['subdistrict_name']} "
        f"(class {numeric_top['action_class']}, confidence {numeric_top['confidence_class']})."
    )
    if str(numeric_top["subdistrict_id"]) != str(top_actionable["subdistrict_id"]):
        disclosure += " It is not used as the top actionable brief target."

    if rank_instability is None:
        return [
            "- Rank-instability rows: unavailable.",
            "- Fixture sensitivity CSV was not supplied to this report run.",
            disclosure,
        ]

    _validate_columns(rank_instability, RANK_INSTABILITY_REQUIRED_COLUMNS, "rank_instability")
    rank_frame = rank_instability.copy()
    rank_frame["rank_range"] = pd.to_numeric(rank_frame["rank_range"], errors="coerce")
    if rank_frame["rank_range"].isna().any():
        raise ValidationReportError("rank_instability rank_range must be numeric.")
    unstable_flags = rank_frame["ranking_unstable"].map(_as_bool)
    if unstable_flags.isna().any():
        raise ValidationReportError(
            "rank_instability ranking_unstable must be boolean-like."
        )
    unstable_bool = unstable_flags.astype(bool)

    unstable_count = int(unstable_bool.sum())
    stable_count = int((~unstable_bool).sum())
    max_rank_range = int(rank_frame["rank_range"].max())
    lines = [
        f"- Stable rank count: {stable_count}",
        f"- Unstable rank count: {unstable_count}",
        f"- Max rank range: {max_rank_range}",
    ]
    if max_rank_range == 0:
        lines.append("- All fixture ranks are stable because every rank_range is 0.")
    else:
        most_variable = rank_frame.sort_values(
            ["rank_range", "subdistrict_id"],
            ascending=[False, True],
        ).iloc[0]
        lines.append(
            "- Most variable rank: "
            f"{most_variable['subdistrict_id']} / "
            f"{most_variable['subdistrict_name']} "
            f"(rank_range {int(most_variable['rank_range'])})."
        )
    lines.append(disclosure)
    return lines


def _as_bool(value: object) -> bool | object:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return pd.NA
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return pd.NA


def _validate_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValidationReportError(
            f"Missing required {frame_name} column(s): {', '.join(missing)}"
        )


def _ordered_counts(values: pd.Series, order: Sequence[str]) -> dict[str, int]:
    counts = values.astype(str).str.lower().value_counts().to_dict()
    result: dict[str, int] = {}
    for label in order:
        result[label] = int(counts.get(label.lower(), 0))
    return result


def _format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in counts.items())


def _format_float(value: float, places: int) -> str:
    if pd.isna(value):
        return "unavailable"
    return f"{value:.{places}f}"
