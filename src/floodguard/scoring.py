"""Flood Preparedness Priority Score engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from floodguard.config import VALID_CONFIDENCE_CLASSES

SCORE_COMPONENTS: tuple[str, ...] = (
    "flood_likelihood_0_100",
    "exposure_0_100",
    "access_gap_0_100",
    "road_criticality_0_100",
    "vulnerability_context_0_100",
)

IDENTITY_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "confidence_class",
)

REQUIRED_COLUMNS: tuple[str, ...] = IDENTITY_COLUMNS + SCORE_COMPONENTS

DEFAULT_WEIGHTS: dict[str, float] = {
    "flood_likelihood_0_100": 0.30,
    "exposure_0_100": 0.25,
    "access_gap_0_100": 0.20,
    "road_criticality_0_100": 0.15,
    "vulnerability_context_0_100": 0.10,
}

COMPONENT_LABELS: dict[str, str] = {
    "flood_likelihood_0_100": "flood likelihood",
    "exposure_0_100": "exposure",
    "access_gap_0_100": "access gap",
    "road_criticality_0_100": "road criticality",
    "vulnerability_context_0_100": "vulnerability/context",
}


class MissingColumnsError(ValueError):
    """Raised when an FPPS input table does not include required columns."""


def validate_required_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str] = REQUIRED_COLUMNS,
) -> None:
    """Validate that every required column is present.

    Args:
        frame: Input table with one row per subdistrict.
        required_columns: Columns required by the active scoring contract.

    Raises:
        MissingColumnsError: If one or more required columns are absent.
    """

    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        joined = ", ".join(missing)
        raise MissingColumnsError(f"Missing required FPPS column(s): {joined}")


def validate_component_values(frame: pd.DataFrame) -> None:
    """Validate that FPPS score components are numeric values from 0 to 100.

    Args:
        frame: Input table with one row per subdistrict.

    Raises:
        ValueError: If a component contains null, non-numeric, or out-of-range
            values, or if `confidence_class` is outside the accepted vocabulary.
    """

    for column in SCORE_COMPONENTS:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        invalid_mask = numeric.isna() | (numeric < 0) | (numeric > 100)
        if invalid_mask.any():
            bad_rows = frame.index[invalid_mask].tolist()
            raise ValueError(
                f"Column {column} must contain numeric values from 0 to 100; "
                f"invalid row index(es): {bad_rows}"
            )

    confidence = frame["confidence_class"].astype(str).str.lower()
    invalid_confidence = ~confidence.isin(VALID_CONFIDENCE_CLASSES)
    if invalid_confidence.any():
        bad_values = sorted(set(frame.loc[invalid_confidence, "confidence_class"].astype(str)))
        allowed = ", ".join(VALID_CONFIDENCE_CLASSES)
        joined = ", ".join(bad_values)
        raise ValueError(
            f"confidence_class must be one of {allowed}; invalid value(s): {joined}"
        )


def validate_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Validate and normalize FPPS component weights.

    Args:
        weights: Mapping from FPPS component column name to numeric weight.

    Returns:
        Normalized weights whose sum is 1.0.

    Raises:
        ValueError: If weights are missing components, include unknown
            components, are negative, or sum to zero.
    """

    weight_keys = set(weights)
    component_keys = set(SCORE_COMPONENTS)
    missing = sorted(component_keys - weight_keys)
    unknown = sorted(weight_keys - component_keys)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing weights: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown weights: {', '.join(unknown)}")
        raise ValueError("; ".join(details))

    parsed: dict[str, float] = {}
    for column, value in weights.items():
        weight = float(value)
        if weight < 0:
            raise ValueError(f"Weight for {column} must be non-negative.")
        parsed[column] = weight

    total = sum(parsed.values())
    if total <= 0:
        raise ValueError("At least one FPPS weight must be greater than zero.")

    return {column: weight / total for column, weight in parsed.items()}


def score_subdistricts(
    frame: pd.DataFrame,
    weights: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Compute FPPS, action class, and top reason for subdistrict rows.

    Args:
        frame: Input table with one row per subdistrict.
        weights: Optional FPPS component weights. If provided, weights are
            normalized to sum to 1.0 after validation.

    Returns:
        A new dataframe preserving input columns and adding:
        `fpps_0_100`, `action_class`, and `top_reason`.
    """

    validate_required_columns(frame)
    validate_component_values(frame)
    active_weights = validate_weights(weights or DEFAULT_WEIGHTS)

    result = frame.copy()
    result["confidence_class"] = result["confidence_class"].astype(str).str.lower()

    component_values = result.loc[:, SCORE_COMPONENTS].apply(pd.to_numeric)
    weighted_score = sum(
        component_values[column] * weight for column, weight in active_weights.items()
    )
    result["fpps_0_100"] = weighted_score.round(2)

    result["action_class"] = result.apply(assign_action_class, axis=1)
    result["top_reason"] = result.apply(generate_top_reason, axis=1)

    return result


def assign_action_class(row: pd.Series) -> str:
    """Assign the A-E action class for a scored subdistrict row."""

    confidence = str(row["confidence_class"]).lower()
    if confidence == "low" or float(row["fpps_0_100"]) < 35:
        return "E"

    exposure = float(row["exposure_0_100"])
    access_gap = float(row["access_gap_0_100"])
    road_criticality = float(row["road_criticality_0_100"])

    if exposure >= 70 and access_gap >= 70:
        return "A"
    if road_criticality >= 75 and access_gap >= 55:
        return "B"
    if exposure >= 65 and access_gap >= 50:
        return "C"
    return "D"


def generate_top_reason(row: pd.Series) -> str:
    """Generate a short human-readable reason for the action class."""

    action_class = str(row["action_class"])
    if action_class == "E":
        if str(row["confidence_class"]).lower() == "low":
            return "Monitor and verify because confidence is low."
        return "Monitor and verify because the priority score is low."

    if action_class == "A":
        return "High exposure and access loss require life-safety action."
    if action_class == "B":
        return "Critical routes and access loss threaten isolation."
    if action_class == "C":
        return "Exposure and access loss threaten essential services."

    top_component = max(
        SCORE_COMPONENTS,
        key=lambda column: float(row[column]),
    )
    value = float(row[top_component])
    label = COMPONENT_LABELS[top_component]
    return f"Highest driver is {label} ({value:.1f}/100)."
