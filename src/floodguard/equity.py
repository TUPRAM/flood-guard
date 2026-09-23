"""Evacuation Equity Gap helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

EQUITY_METRIC_VERSION = "2.0"
EQUITY_UNKNOWN_COLUMNS = (
    "vulnerable_population_access_unknown",
    "non_vulnerable_population_access_unknown",
)

EQUITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "total_vulnerable_population",
    "vulnerable_population_losing_access",
    "total_non_vulnerable_population",
    "non_vulnerable_population_losing_access",
    "confidence_class",
)
EQUITY_BOUND_COLUMNS = (
    "vulnerable_access_loss_rate_lower_bound",
    "vulnerable_access_loss_rate_upper_bound",
    "non_vulnerable_access_loss_rate_lower_bound",
    "non_vulnerable_access_loss_rate_upper_bound",
    "vulnerable_access_unknown_share",
    "non_vulnerable_access_unknown_share",
    "equity_difference_pp_lower_bound",
    "equity_difference_pp_upper_bound",
    "equity_ratio_lower_bound",
    "equity_ratio_upper_bound",
)
EQUITY_OUTPUT_COLUMNS = (
    "equity_metric_version",
    "vulnerable_access_loss_rate",
    "non_vulnerable_access_loss_rate",
    "equity_difference_pp",
    "equity_gap_ratio",
    "equity_ratio_unavailable_reason",
    *EQUITY_BOUND_COLUMNS,
    "equity_ratio_bound_unavailable_reason",
    "interpretation_text",
)


class EquityError(ValueError):
    """Raised when equity inputs violate the equity contract."""


def compute_equity_gap(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute full-precision group loss rates, difference and ratio.

    Optional access-unknown populations yield missing-coverage sensitivity
    bounds, not confidence intervals. Their absence never implies zero unknown.
    """

    _validate_columns(frame, EQUITY_REQUIRED_COLUMNS, "equity")
    result = frame.copy()
    for column in (
        "total_vulnerable_population",
        "vulnerable_population_losing_access",
        "total_non_vulnerable_population",
        "non_vulnerable_population_losing_access",
    ):
        result[column] = _non_negative_numeric(result[column], column)

    has_unknown = [column in result.columns for column in EQUITY_UNKNOWN_COLUMNS]
    if any(has_unknown) and not all(has_unknown):
        raise EquityError("Both group access-unknown columns must be supplied together.")
    if all(has_unknown):
        for column in EQUITY_UNKNOWN_COLUMNS:
            result[column] = _non_negative_numeric(result[column], column)
    if "total_population" in result.columns:
        result["total_population"] = _non_negative_numeric(
            result["total_population"], "total_population"
        )

    records: list[dict[str, object]] = []
    for index, row in result.iterrows():
        _validate_row_counts(row, index, all(has_unknown))
        record = row.to_dict()
        equity = _compute_row_equity(row, all(has_unknown))
        record.update(equity)
        records.append(record)
    columns = list(dict.fromkeys((*result.columns, *EQUITY_OUTPUT_COLUMNS)))
    return pd.DataFrame(records, columns=columns)


def equity_input_from_access_loss(
    access_loss: pd.DataFrame,
    threshold: int = 30,
    confidence_class: str = "medium",
) -> pd.DataFrame:
    """Build equity input rows from access-loss output for one threshold."""

    required = (
        "subdistrict_id",
        "subdistrict_name",
        "total_vulnerable_population",
        "total_non_vulnerable_population",
        f"vulnerable_population_losing_{threshold}_min_access",
        f"non_vulnerable_population_losing_{threshold}_min_access",
    )
    _validate_columns(access_loss, required, "access_loss")
    values: dict[str, object] = {
        "subdistrict_id": access_loss["subdistrict_id"],
        "subdistrict_name": access_loss["subdistrict_name"],
        "total_vulnerable_population": access_loss["total_vulnerable_population"],
        "vulnerable_population_losing_access": access_loss[
            f"vulnerable_population_losing_{threshold}_min_access"
        ],
        "total_non_vulnerable_population": access_loss[
            "total_non_vulnerable_population"
        ],
        "non_vulnerable_population_losing_access": access_loss[
            f"non_vulnerable_population_losing_{threshold}_min_access"
        ],
        "confidence_class": confidence_class,
    }
    for column in EQUITY_UNKNOWN_COLUMNS:
        if column in access_loss.columns:
            values[column] = access_loss[column]
    return pd.DataFrame(values)


def equity_loss_sensitivity_bounds(
    vulnerable_population: float,
    vulnerable_known_loss: float,
    vulnerable_access_unknown: float,
    comparison_population: float,
    comparison_known_loss: float,
    comparison_access_unknown: float,
) -> dict[str, float | str | None]:
    """Return conservative missing-coverage bounds for declared group losses.

    Unknown population may all or none newly lose access. This is a sensitivity
    interval, not a statistical confidence interval. A finite ratio interval
    requires a strictly positive comparison-rate lower bound.
    """

    counts = {
        "vulnerable_population": vulnerable_population,
        "vulnerable_known_loss": vulnerable_known_loss,
        "vulnerable_access_unknown": vulnerable_access_unknown,
        "comparison_population": comparison_population,
        "comparison_known_loss": comparison_known_loss,
        "comparison_access_unknown": comparison_access_unknown,
    }
    for name, value in counts.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise EquityError(f"{name} must be a finite non-negative number.")
    if vulnerable_known_loss + vulnerable_access_unknown > vulnerable_population:
        raise EquityError("Vulnerable loss plus unknown exceeds group population.")
    if comparison_known_loss + comparison_access_unknown > comparison_population:
        raise EquityError("Comparison loss plus unknown exceeds group population.")

    v_low = (
        vulnerable_known_loss / vulnerable_population if vulnerable_population else None
    )
    v_high = (
        min(
            1.0,
            (vulnerable_known_loss + vulnerable_access_unknown) / vulnerable_population,
        )
        if vulnerable_population else None
    )
    c_low = (
        comparison_known_loss / comparison_population if comparison_population else None
    )
    c_high = (
        min(
            1.0,
            (comparison_known_loss + comparison_access_unknown) / comparison_population,
        )
        if comparison_population else None
    )
    if v_low is None:
        ratio_reason = "group_population_zero"
    elif c_low is None:
        ratio_reason = "comparison_population_zero"
    elif c_low == 0:
        ratio_reason = "comparison_loss_rate_interval_includes_zero"
    else:
        ratio_reason = None
    return {
        "vulnerable_access_loss_rate_lower_bound": v_low,
        "vulnerable_access_loss_rate_upper_bound": v_high,
        "non_vulnerable_access_loss_rate_lower_bound": c_low,
        "non_vulnerable_access_loss_rate_upper_bound": c_high,
        "vulnerable_access_unknown_share": (
            vulnerable_access_unknown / vulnerable_population
            if vulnerable_population else None
        ),
        "non_vulnerable_access_unknown_share": (
            comparison_access_unknown / comparison_population
            if comparison_population else None
        ),
        "equity_difference_pp_lower_bound": (
            100 * (v_low - c_high) if v_low is not None and c_high is not None else None
        ),
        "equity_difference_pp_upper_bound": (
            100 * (v_high - c_low) if v_high is not None and c_low is not None else None
        ),
        "equity_ratio_lower_bound": v_low / c_high if ratio_reason is None else None,
        "equity_ratio_upper_bound": v_high / c_low if ratio_reason is None else None,
        "equity_ratio_bound_unavailable_reason": ratio_reason,
    }


def _validate_row_counts(row: pd.Series, index: object, has_unknown: bool) -> None:
    for prefix in ("vulnerable", "non_vulnerable"):
        total = float(row[f"total_{prefix}_population"])
        loss = float(row[f"{prefix}_population_losing_access"])
        if loss > total:
            raise EquityError(f"Row {index}: {prefix} loss exceeds group population.")
        if has_unknown and loss + float(row[f"{prefix}_population_access_unknown"]) > total:
            raise EquityError(
                f"Row {index}: {prefix} loss plus unknown exceeds group population."
            )
    if "total_population" in row:
        groups = float(row["total_vulnerable_population"]) + float(
            row["total_non_vulnerable_population"]
        )
        if not math.isclose(
            groups, float(row["total_population"]), rel_tol=1e-9, abs_tol=1e-6
        ):
            raise EquityError(
                f"Row {index}: group populations do not reconcile to total_population."
            )


def _compute_row_equity(row: pd.Series, has_unknown: bool) -> dict[str, object]:
    vulnerable_population = float(row["total_vulnerable_population"])
    vulnerable_loss = float(row["vulnerable_population_losing_access"])
    comparison_population = float(row["total_non_vulnerable_population"])
    comparison_loss = float(row["non_vulnerable_population_losing_access"])
    v_rate = _rate(vulnerable_loss, vulnerable_population)
    c_rate = _rate(comparison_loss, comparison_population)
    if v_rate is None:
        ratio: float | object = pd.NA
        reason: str | object = "group_population_zero"
        interpretation = "Equity gap unavailable: no vulnerable population denominator."
    elif c_rate is None:
        ratio = pd.NA
        reason = "comparison_population_zero"
        interpretation = "Equity gap unavailable: no non-vulnerable population denominator."
    elif c_rate == 0:
        ratio = pd.NA
        reason = "comparison_loss_rate_zero"
        if v_rate == 0:
            interpretation = (
                "Both modeled loss rates are zero; difference is zero percentage "
                "points and ratio is undefined."
            )
        else:
            interpretation = "Equity gap ratio undefined because comparison loss rate is zero."
    else:
        ratio = v_rate / c_rate
        reason = pd.NA
        interpretation = (
            f"Modeled vulnerable-group loss rate is {ratio:.3g} times the comparison rate."
            if ratio < 0.8 or ratio > 1.2
            else "Modeled access-loss rates are broadly similar between groups."
        )
    if has_unknown and any(float(row[column]) > 0 for column in EQUITY_UNKNOWN_COLUMNS):
        interpretation += (
            " Rates count known model-evaluable loss only; "
            "unknown coverage is bounded separately."
        )
    result: dict[str, object] = {
        "equity_metric_version": EQUITY_METRIC_VERSION,
        "vulnerable_access_loss_rate": v_rate if v_rate is not None else pd.NA,
        "non_vulnerable_access_loss_rate": c_rate if c_rate is not None else pd.NA,
        "equity_difference_pp": (
            100 * (v_rate - c_rate) if v_rate is not None and c_rate is not None else pd.NA
        ),
        "equity_gap_ratio": ratio,
        "equity_ratio_unavailable_reason": reason,
        "interpretation_text": interpretation,
    }
    result.update({name: pd.NA for name in EQUITY_BOUND_COLUMNS})
    result["equity_ratio_bound_unavailable_reason"] = "unknown_coverage_not_supplied"
    if has_unknown:
        bounds = equity_loss_sensitivity_bounds(
            vulnerable_population,
            vulnerable_loss,
            float(row["vulnerable_population_access_unknown"]),
            comparison_population,
            comparison_loss,
            float(row["non_vulnerable_population_access_unknown"]),
        )
        result.update(
            {name: value if value is not None else pd.NA for name, value in bounds.items()}
        )
    return result


def _validate_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise EquityError(
            f"Missing required {frame_name} column(s): {', '.join(missing)}"
        )


def _non_negative_numeric(values: pd.Series, column: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    invalid = numeric.isna() | (numeric < 0) | (numeric == math.inf)
    if invalid.any():
        bad_rows = values.index[invalid].tolist()
        raise EquityError(
            f"Column {column} must contain finite non-negative numeric values; "
            f"invalid row index(es): {bad_rows}"
        )
    return numeric


def _rate(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
