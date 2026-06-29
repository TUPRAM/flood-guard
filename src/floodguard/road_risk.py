"""Road-disruption probability helpers."""

from __future__ import annotations

from collections.abc import Sequence
import math

import pandas as pd

ROAD_REQUIRED_COLUMNS: tuple[str, ...] = (
    "road_id",
    "road_class",
    "bridge_flag",
    "subdistrict_id",
    "surrounding_inundation_0_1",
)

FLOOD_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "mean_flood_probability_0_1",
    "confidence_class",
    "source_name",
    "source_timestamp",
)

ROAD_CLASS_FACTORS: dict[str, float] = {
    "motorway": 1.0,
    "trunk": 1.0,
    "primary": 1.0,
    "secondary": 0.75,
    "tertiary": 0.55,
    "local": 0.35,
    "residential": 0.35,
    "unclassified": 0.35,
}

ROAD_RISK_OUTPUT_COLUMNS: tuple[str, ...] = (
    "road_id",
    "subdistrict_id",
    "road_disruption_probability_0_1",
    "confidence_class",
    "top_risk_reason",
    "source_name",
    "source_timestamp",
    "assumptions",
)


class RoadRiskError(ValueError):
    """Raised when road-risk inputs violate the road-risk contract."""


def score_road_disruption(
    roads: pd.DataFrame,
    flood_probability: pd.DataFrame,
) -> pd.DataFrame:
    """Estimate segment-level road-disruption probability.

    Args:
        roads: Road segment rows with `road_id`, `road_class`, `bridge_flag`,
            `subdistrict_id`, and `surrounding_inundation_0_1`.
        flood_probability: Subdistrict flood-probability rows keyed by
            `subdistrict_id`.

    Returns:
        A dataframe with one row per road segment and the output columns
        required by the road-risk contract.
    """

    _validate_columns(roads, ROAD_REQUIRED_COLUMNS, "roads")
    _validate_columns(flood_probability, FLOOD_REQUIRED_COLUMNS, "flood_probability")
    _validate_unique(flood_probability, "subdistrict_id", "flood_probability")

    road_frame = roads.copy()
    flood_frame = flood_probability.copy()

    road_frame["road_class"] = road_frame["road_class"].astype(str).str.lower()
    unknown_classes = sorted(set(road_frame["road_class"]) - set(ROAD_CLASS_FACTORS))
    if unknown_classes:
        raise RoadRiskError(f"Unknown road_class value(s): {', '.join(unknown_classes)}")

    road_frame["surrounding_inundation_0_1"] = _numeric_0_1(
        road_frame["surrounding_inundation_0_1"],
        "surrounding_inundation_0_1",
    )
    flood_frame["mean_flood_probability_0_1"] = _numeric_0_1(
        flood_frame["mean_flood_probability_0_1"],
        "mean_flood_probability_0_1",
    )

    road_frame["road_class_factor"] = road_frame["road_class"].map(ROAD_CLASS_FACTORS)
    road_frame["bridge_factor"] = road_frame["bridge_flag"].map(_bridge_to_factor)

    merged = road_frame.merge(
        flood_frame.loc[:, FLOOD_REQUIRED_COLUMNS],
        on="subdistrict_id",
        how="left",
        validate="many_to_one",
    )
    missing_flood = merged["mean_flood_probability_0_1"].isna()
    if missing_flood.any():
        missing_ids = sorted(set(merged.loc[missing_flood, "subdistrict_id"].astype(str)))
        raise RoadRiskError(
            "Missing flood probability for subdistrict_id value(s): "
            + ", ".join(missing_ids)
        )

    raw_probability = (
        0.65 * merged["mean_flood_probability_0_1"]
        + 0.20 * merged["surrounding_inundation_0_1"]
        + 0.10 * merged["road_class_factor"]
        + 0.05 * merged["bridge_factor"]
    )
    merged["road_disruption_probability_0_1"] = raw_probability.clip(0.0, 1.0).map(
        _round_probability
    )
    merged["top_risk_reason"] = merged.apply(_top_risk_reason, axis=1)
    merged["assumptions"] = (
        "Heuristic road-risk score from flood probability, surrounding inundation, "
        "road class, and bridge flag; not an observed closure."
    )

    return merged.loc[:, ROAD_RISK_OUTPUT_COLUMNS].copy()


def _validate_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise RoadRiskError(
            f"Missing required {frame_name} column(s): {', '.join(missing)}"
        )


def _validate_unique(frame: pd.DataFrame, column: str, frame_name: str) -> None:
    duplicated = frame[column].duplicated(keep=False)
    if duplicated.any():
        values = sorted(set(frame.loc[duplicated, column].astype(str)))
        raise RoadRiskError(
            f"{frame_name} has duplicate {column} value(s): {', '.join(values)}"
        )


def _numeric_0_1(values: pd.Series, column: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    invalid = numeric.isna() | (numeric < 0) | (numeric > 1)
    if invalid.any():
        bad_rows = values.index[invalid].tolist()
        raise RoadRiskError(
            f"Column {column} must contain numeric values from 0 to 1; "
            f"invalid row index(es): {bad_rows}"
        )
    return numeric


def _bridge_to_factor(value: object) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes", "y"}:
        return 1.0
    if lowered in {"false", "0", "no", "n"}:
        return 0.0
    raise RoadRiskError(f"bridge_flag must be boolean-like; invalid value: {value}")


def _round_probability(value: float) -> float:
    return math.floor(float(value) * 1000 + 0.500000001) / 1000


def _top_risk_reason(row: pd.Series) -> str:
    drivers = {
        "flood probability": 0.65 * float(row["mean_flood_probability_0_1"]),
        "surrounding inundation": 0.20 * float(row["surrounding_inundation_0_1"]),
        "road class": 0.10 * float(row["road_class_factor"]),
        "bridge exposure": 0.05 * float(row["bridge_factor"]),
    }
    reason = max(drivers, key=drivers.get)
    return f"Highest road-risk driver is {reason}."
