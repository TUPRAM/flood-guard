"""Fail-fast evaluation and stopping rules for active-learning rounds.

Active acquisition must be compared with stratified random review at comparable
human cost.  This module turns those comparisons into an explicit continue or
pause decision; it never promotes a flood model or estimates operational skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


ROUND_EVALUATION_COLUMNS = (
    "round_id",
    "event_id",
    "round_order",
    "acquisition_policy",
    "review_minutes",
    "iou",
    "dice",
    "reviewer_dice",
    "reviewer_kappa",
    "area_bias_ratio",
    "uncovered_critical_strata_count",
    "source_timestamp",
    "assumptions",
)

COMPARISON_COLUMNS = (
    "round_id",
    "event_id",
    "round_order",
    "active_review_minutes",
    "random_review_minutes",
    "relative_cost_difference",
    "equal_cost_comparable",
    "active_iou",
    "random_iou",
    "iou_gain_active_minus_random",
    "active_dice",
    "random_dice",
    "dice_gain_active_minus_random",
    "reviewer_dice",
    "reviewer_kappa",
    "active_area_bias_ratio",
    "uncovered_critical_strata_count",
    "active_beats_random",
    "source_timestamp",
    "assumptions",
)


class ActiveLearningEvaluationError(ValueError):
    """Raised when round evidence is incomplete or not comparable."""


@dataclass(frozen=True)
class ActiveLearningDecision:
    """One explicit stopping-rule result for the current evidence history."""

    status: str
    continue_active_acquisition: bool
    reasons: tuple[str, ...]
    evaluated_rounds: int
    comparable_rounds: int
    trailing_nonwins: int

    def to_dict(self) -> dict[str, object]:
        """Return stable report fields."""

        return {
            "status": self.status,
            "continue_active_acquisition": self.continue_active_acquisition,
            "reasons": list(self.reasons),
            "evaluated_rounds": self.evaluated_rounds,
            "comparable_rounds": self.comparable_rounds,
            "trailing_nonwins": self.trailing_nonwins,
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }


def compare_active_and_random_rounds(
    evidence: pd.DataFrame,
    *,
    equal_cost_relative_tolerance: float = 0.10,
    minimum_iou_gain: float = 0.0,
) -> pd.DataFrame:
    """Build one comparable active-versus-random row per evaluated round."""

    _require_columns(evidence, ROUND_EVALUATION_COLUMNS)
    if evidence.empty:
        raise ActiveLearningEvaluationError("Round evidence must not be empty.")
    tolerance = _bounded(
        equal_cost_relative_tolerance,
        "equal_cost_relative_tolerance",
        lower=0.0,
        upper=1.0,
    )
    minimum_gain = _finite(minimum_iou_gain, "minimum_iou_gain")
    rows: list[dict[str, object]] = []
    grouped = evidence.groupby("round_id", sort=False, dropna=False)
    seen_orders: set[int] = set()
    for round_id, group in grouped:
        if not str(round_id).strip():
            raise ActiveLearningEvaluationError("round_id must not be blank.")
        if group["acquisition_policy"].astype(str).duplicated().any():
            raise ActiveLearningEvaluationError(
                f"Round {round_id!r} has duplicate acquisition_policy rows."
            )
        policies = set(group["acquisition_policy"].astype(str))
        expected = {"active", "stratified_random"}
        if policies != expected:
            raise ActiveLearningEvaluationError(
                f"Round {round_id!r} must contain exactly active and stratified_random."
            )
        events = set(group["event_id"].astype(str))
        if len(events) != 1 or not next(iter(events)).strip():
            raise ActiveLearningEvaluationError(
                f"Round {round_id!r} must refer to one nonblank event_id."
            )
        order_values = pd.to_numeric(group["round_order"], errors="coerce")
        if order_values.isna().any() or len(set(order_values)) != 1:
            raise ActiveLearningEvaluationError(
                f"Round {round_id!r} must have one numeric round_order."
            )
        order = int(order_values.iloc[0])
        if order < 0 or order in seen_orders:
            raise ActiveLearningEvaluationError(
                "round_order must be unique non-negative integers."
            )
        seen_orders.add(order)
        active = group[group["acquisition_policy"].astype(str).eq("active")].iloc[0]
        random = group[
            group["acquisition_policy"].astype(str).eq("stratified_random")
        ].iloc[0]
        active_minutes = _positive(active["review_minutes"], "active review_minutes")
        random_minutes = _positive(random["review_minutes"], "random review_minutes")
        relative_cost_difference = abs(active_minutes - random_minutes) / max(
            active_minutes,
            random_minutes,
        )
        active_iou = _bounded(active["iou"], "active iou", lower=0.0, upper=1.0)
        random_iou = _bounded(random["iou"], "random iou", lower=0.0, upper=1.0)
        active_dice = _bounded(active["dice"], "active dice", lower=0.0, upper=1.0)
        random_dice = _bounded(random["dice"], "random dice", lower=0.0, upper=1.0)
        reviewer_dice = min(
            _bounded(value, "reviewer_dice", lower=0.0, upper=1.0)
            for value in group["reviewer_dice"]
        )
        reviewer_kappa = min(
            _bounded(value, "reviewer_kappa", lower=-1.0, upper=1.0)
            for value in group["reviewer_kappa"]
        )
        uncovered = _nonnegative_integer(
            max(
                _nonnegative_integer(value, "uncovered_critical_strata_count")
                for value in group["uncovered_critical_strata_count"]
            ),
            "uncovered_critical_strata_count",
        )
        source_timestamps = set(group["source_timestamp"].astype(str).str.strip())
        assumptions = " | ".join(
            sorted(set(group["assumptions"].astype(str).str.strip()))
        )
        if "" in source_timestamps or not assumptions:
            raise ActiveLearningEvaluationError(
                f"Round {round_id!r} requires source_timestamp and assumptions."
            )
        comparable = relative_cost_difference <= tolerance
        rows.append(
            {
                "round_id": str(round_id),
                "event_id": next(iter(events)),
                "round_order": order,
                "active_review_minutes": active_minutes,
                "random_review_minutes": random_minutes,
                "relative_cost_difference": relative_cost_difference,
                "equal_cost_comparable": comparable,
                "active_iou": active_iou,
                "random_iou": random_iou,
                "iou_gain_active_minus_random": active_iou - random_iou,
                "active_dice": active_dice,
                "random_dice": random_dice,
                "dice_gain_active_minus_random": active_dice - random_dice,
                "reviewer_dice": reviewer_dice,
                "reviewer_kappa": reviewer_kappa,
                "active_area_bias_ratio": _finite(
                    active["area_bias_ratio"], "active area_bias_ratio"
                ),
                "uncovered_critical_strata_count": uncovered,
                "active_beats_random": comparable
                and active_iou - random_iou > minimum_gain,
                "source_timestamp": sorted(source_timestamps)[-1],
                "assumptions": assumptions,
            }
        )
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS).sort_values(
        "round_order"
    ).reset_index(drop=True)


def evaluate_active_learning_stopping_rule(
    comparisons: pd.DataFrame,
    *,
    consecutive_nonwins_to_pause: int = 3,
    minimum_reviewer_dice: float = 0.80,
    minimum_reviewer_kappa: float = 0.80,
    maximum_absolute_area_bias: float = 0.25,
    area_bias_rounds_to_pause: int = 2,
) -> ActiveLearningDecision:
    """Evaluate fail-fast conditions in safety-first priority order."""

    _require_columns(comparisons, COMPARISON_COLUMNS)
    if comparisons.empty:
        raise ActiveLearningEvaluationError("Comparisons must not be empty.")
    nonwin_limit = _positive_integer(
        consecutive_nonwins_to_pause,
        "consecutive_nonwins_to_pause",
    )
    bias_limit = _positive_integer(area_bias_rounds_to_pause, "area_bias_rounds_to_pause")
    dice_gate = _bounded(minimum_reviewer_dice, "minimum_reviewer_dice", 0.0, 1.0)
    kappa_gate = _bounded(minimum_reviewer_kappa, "minimum_reviewer_kappa", -1.0, 1.0)
    area_gate = _bounded(maximum_absolute_area_bias, "maximum_absolute_area_bias", 0.0, 10.0)
    ordered = comparisons.sort_values("round_order").reset_index(drop=True)
    comparable = ordered[ordered["equal_cost_comparable"].map(_strict_bool)]
    trailing_nonwins = 0
    for value in reversed(comparable["active_beats_random"].tolist()):
        if _strict_bool(value):
            break
        trailing_nonwins += 1
    latest = ordered.iloc[-1]
    reasons: list[str] = []

    if not _strict_bool(latest["equal_cost_comparable"]):
        reasons.append(
            "Latest active and random lanes are not comparable at equal reviewer cost."
        )
        status = "pause_incomparable_cost"
    elif float(latest["reviewer_dice"]) < dice_gate or float(
        latest["reviewer_kappa"]
    ) < kappa_gate:
        reasons.append(
            "Reviewer agreement is below the protocol gate; repair review evidence first."
        )
        status = "pause_reviewer_agreement"
    elif int(latest["uncovered_critical_strata_count"]) > 0:
        reasons.append(
            "Critical strata remain uncovered; fill the hard-stratum lane before acquisition continues."
        )
        status = "pause_critical_strata_coverage"
    elif (
        len(ordered) >= bias_limit
        and ordered.tail(bias_limit)["active_area_bias_ratio"]
        .astype(float)
        .abs()
        .gt(area_gate)
        .all()
    ):
        reasons.append(
            f"Absolute area bias exceeded {area_gate:.3f} for {bias_limit} consecutive rounds."
        )
        status = "pause_persistent_area_bias"
    elif trailing_nonwins >= nonwin_limit:
        reasons.append(
            f"Active selection failed to beat stratified random for {trailing_nonwins} comparable rounds."
        )
        status = "pause_active_nonwins"
    else:
        reasons.append(
            "No configured fail-fast condition is currently triggered; continue only with the same audit lanes."
        )
        status = "continue_query_only_collection"

    return ActiveLearningDecision(
        status=status,
        continue_active_acquisition=status == "continue_query_only_collection",
        reasons=tuple(reasons),
        evaluated_rounds=len(ordered),
        comparable_rounds=len(comparable),
        trailing_nonwins=trailing_nonwins,
    )


def build_active_learning_evaluation_summary(
    comparisons: pd.DataFrame,
    decision: ActiveLearningDecision,
) -> str:
    """Render a compact non-operational Markdown readout."""

    lines = [
        "# Active-learning round evaluation",
        "",
        "Status: query-selection evidence only; not flood-model promotion or FPPS evidence.",
        "",
        f"Decision: `{decision.status}`",
        f"Continue active acquisition: `{str(decision.continue_active_acquisition).lower()}`",
        f"Evaluated rounds: {decision.evaluated_rounds}",
        f"Comparable equal-cost rounds: {decision.comparable_rounds}",
        f"Trailing active non-wins: {decision.trailing_nonwins}",
        "",
        "Reasons:",
        "",
        *[f"- {reason}" for reason in decision.reasons],
        "",
        "| Round | Active IoU | Random IoU | Gain | Comparable |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in comparisons.sort_values("round_order").to_dict("records"):
        lines.append(
            f"| {row['round_id']} | {float(row['active_iou']):.3f} | "
            f"{float(row['random_iou']):.3f} | "
            f"{float(row['iou_gain_active_minus_random']):+.3f} | "
            f"{str(_strict_bool(row['equal_cost_comparable'])).lower()} |"
        )
    return "\n".join(lines) + "\n"


def write_active_learning_evaluation(
    evidence: pd.DataFrame | str | Path,
    *,
    comparison_output_path: str | Path,
    summary_output_path: str | Path,
    equal_cost_relative_tolerance: float = 0.10,
    minimum_iou_gain: float = 0.0,
) -> tuple[pd.DataFrame, ActiveLearningDecision, dict[str, Path]]:
    """Compare rounds, evaluate stopping, and write CSV/Markdown evidence."""

    frame = evidence.copy() if isinstance(evidence, pd.DataFrame) else pd.read_csv(evidence)
    comparisons = compare_active_and_random_rounds(
        frame,
        equal_cost_relative_tolerance=equal_cost_relative_tolerance,
        minimum_iou_gain=minimum_iou_gain,
    )
    decision = evaluate_active_learning_stopping_rule(comparisons)
    csv_path = Path(comparison_output_path)
    summary_path = Path(summary_output_path)
    if csv_path.suffix.lower() != ".csv":
        raise ActiveLearningEvaluationError("Comparison output must be CSV.")
    if summary_path.suffix.lower() not in {".md", ".markdown"}:
        raise ActiveLearningEvaluationError("Summary output must be Markdown.")
    if csv_path.resolve() == summary_path.resolve():
        raise ActiveLearningEvaluationError("Evaluation output paths must be distinct.")
    existing = [str(path) for path in (csv_path, summary_path) if path.exists()]
    if existing:
        raise ActiveLearningEvaluationError(
            "Evaluation outputs are immutable and cannot be overwritten: "
            + ", ".join(existing)
        )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    comparisons.to_csv(csv_path, index=False)
    summary_path.write_text(
        build_active_learning_evaluation_summary(comparisons, decision),
        encoding="utf-8",
    )
    return comparisons, decision, {"comparisons": csv_path, "summary": summary_path}


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...]) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ActiveLearningEvaluationError(
            f"Round evidence is missing columns: {', '.join(missing)}"
        )


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ActiveLearningEvaluationError(f"{label} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ActiveLearningEvaluationError(f"{label} must be numeric.") from exc
    if not pd.notna(number) or number in {float("inf"), float("-inf")}:
        raise ActiveLearningEvaluationError(f"{label} must be finite.")
    return number


def _positive(value: object, label: str) -> float:
    number = _finite(value, label)
    if number <= 0:
        raise ActiveLearningEvaluationError(f"{label} must be positive.")
    return number


def _bounded(
    value: object,
    label: str,
    lower: float,
    upper: float,
) -> float:
    number = _finite(value, label)
    if not lower <= number <= upper:
        raise ActiveLearningEvaluationError(
            f"{label} must be in [{lower}, {upper}]."
        )
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ActiveLearningEvaluationError(f"{label} must be a positive integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ActiveLearningEvaluationError(
            f"{label} must be a positive integer."
        ) from exc
    if number <= 0 or float(value) != number:
        raise ActiveLearningEvaluationError(f"{label} must be a positive integer.")
    return number


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ActiveLearningEvaluationError(f"{label} must be a non-negative integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ActiveLearningEvaluationError(
            f"{label} must be a non-negative integer."
        ) from exc
    if number < 0 or float(value) != number:
        raise ActiveLearningEvaluationError(
            f"{label} must be a non-negative integer."
        )
    return number


def _strict_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise ActiveLearningEvaluationError("Comparison boolean field is invalid.")
