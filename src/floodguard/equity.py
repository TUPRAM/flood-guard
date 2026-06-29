"""Evacuation Equity Gap helpers."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

EQUITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "total_vulnerable_population",
    "vulnerable_population_losing_access",
    "total_non_vulnerable_population",
    "non_vulnerable_population_losing_access",
    "confidence_class",
)


class EquityError(ValueError):
    """Raised when equity inputs violate the equity contract."""


def compute_equity_gap(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute vulnerable versus non-vulnerable access-loss rates and ratio."""

    _validate_columns(frame, EQUITY_REQUIRED_COLUMNS, "equity")
    result = frame.copy()
    for column in (
        "total_vulnerable_population",
        "vulnerable_population_losing_access",
        "total_non_vulnerable_population",
        "non_vulnerable_population_losing_access",
    ):
        result[column] = _non_negative_numeric(result[column], column)

    records: list[dict[str, object]] = []
    for _, row in result.iterrows():
        record = row.to_dict()
        equity = _compute_row_equity(row)
        record.update(equity)
        records.append(record)
    return pd.DataFrame(records)


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
    return pd.DataFrame(
        {
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
    )


def _compute_row_equity(row: pd.Series) -> dict[str, object]:
    total_vulnerable = float(row["total_vulnerable_population"])
    vulnerable_losing = float(row["vulnerable_population_losing_access"])
    total_non_vulnerable = float(row["total_non_vulnerable_population"])
    non_vulnerable_losing = float(row["non_vulnerable_population_losing_access"])

    if total_vulnerable == 0:
        return {
            "vulnerable_access_loss_rate": pd.NA,
            "non_vulnerable_access_loss_rate": _rate(
                non_vulnerable_losing,
                total_non_vulnerable,
            ),
            "equity_gap_ratio": pd.NA,
            "interpretation_text": (
                "Equity gap unavailable: no vulnerable population denominator."
            ),
        }

    if total_non_vulnerable == 0:
        return {
            "vulnerable_access_loss_rate": _rate(vulnerable_losing, total_vulnerable),
            "non_vulnerable_access_loss_rate": pd.NA,
            "equity_gap_ratio": pd.NA,
            "interpretation_text": (
                "Equity gap unavailable: no non-vulnerable population denominator."
            ),
        }

    vulnerable_rate = _rate(vulnerable_losing, total_vulnerable)
    non_vulnerable_rate = _rate(non_vulnerable_losing, total_non_vulnerable)

    if vulnerable_rate == 0 and non_vulnerable_rate == 0:
        return {
            "vulnerable_access_loss_rate": vulnerable_rate,
            "non_vulnerable_access_loss_rate": non_vulnerable_rate,
            "equity_gap_ratio": 1.0,
            "interpretation_text": (
                "No measured access-loss gap; both groups have zero loss."
            ),
        }

    if non_vulnerable_rate == 0 and vulnerable_rate > 0:
        return {
            "vulnerable_access_loss_rate": vulnerable_rate,
            "non_vulnerable_access_loss_rate": non_vulnerable_rate,
            "equity_gap_ratio": pd.NA,
            "interpretation_text": (
                "Equity gap ratio undefined because vulnerable loss exists "
                "while non-vulnerable loss is zero."
            ),
        }

    ratio = round(vulnerable_rate / non_vulnerable_rate, 3)
    if ratio > 1.2:
        interpretation = (
            f"Vulnerable residents are {ratio:.3g} times more likely to lose access."
        )
    elif ratio < 0.8:
        interpretation = (
            f"Vulnerable residents are {ratio:.3g} times as likely to lose access."
        )
    else:
        interpretation = "Access-loss rates are broadly similar between groups."

    return {
        "vulnerable_access_loss_rate": vulnerable_rate,
        "non_vulnerable_access_loss_rate": non_vulnerable_rate,
        "equity_gap_ratio": ratio,
        "interpretation_text": interpretation,
    }


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
    invalid = numeric.isna() | (numeric < 0)
    if invalid.any():
        bad_rows = values.index[invalid].tolist()
        raise EquityError(
            f"Column {column} must contain non-negative numeric values; "
            f"invalid row index(es): {bad_rows}"
        )
    return numeric


def _rate(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return pd.NA
    return round(numerator / denominator, 4)
