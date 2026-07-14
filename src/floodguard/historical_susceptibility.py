"""Historical flood susceptibility context with strict evidence boundaries.

The functions in this module operate on normalized, provenance-bearing context
features.  They do not observe current flooding and they do not forecast an
event.  The transparent additive score is a tested baseline and plausibility
check; production calibration still requires rights-cleared historical targets
with complete basin and event holdouts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from types import MappingProxyType

import pandas as pd


FEATURE_SCHEMA_VERSION = "floodguard.historical_susceptibility_features.v1"
OUTPUT_SCHEMA_VERSION = "floodguard.historical_susceptibility_context.v1"
CONTEXT_LABEL = "Historical susceptibility/context"
CONTEXT_BOUNDARY = "Not observed current flooding. Not a forecast."

AGGREGATE_FEATURE_SCHEMA: tuple[str, ...] = (
    "global_flood_history_0_1",
    "jrc_water_occurrence_0_1",
    "jrc_water_seasonality_0_1",
    "jrc_water_change_0_1",
    "elevation_susceptibility_0_1",
    "slope_susceptibility_0_1",
    "worldcover_flood_proneness_0_1",
    "river_proximity_0_1",
    "drainage_density_0_1",
    "catchment_wetness_0_1",
    "soil_runoff_potential_0_1",
    "rainfall_climatology_0_1",
)

DEFAULT_FEATURE_WEIGHTS: dict[str, float] = {
    "global_flood_history_0_1": 0.18,
    "jrc_water_occurrence_0_1": 0.14,
    "jrc_water_seasonality_0_1": 0.06,
    "jrc_water_change_0_1": 0.04,
    "elevation_susceptibility_0_1": 0.11,
    "slope_susceptibility_0_1": 0.11,
    "worldcover_flood_proneness_0_1": 0.08,
    "river_proximity_0_1": 0.08,
    "drainage_density_0_1": 0.05,
    "catchment_wetness_0_1": 0.06,
    "soil_runoff_potential_0_1": 0.04,
    "rainfall_climatology_0_1": 0.05,
}

FEATURE_LABELS: dict[str, str] = {
    "global_flood_history_0_1": "Global flood history",
    "jrc_water_occurrence_0_1": "JRC water occurrence",
    "jrc_water_seasonality_0_1": "JRC water seasonality",
    "jrc_water_change_0_1": "JRC water change",
    "elevation_susceptibility_0_1": "Low-elevation terrain",
    "slope_susceptibility_0_1": "Low-slope terrain",
    "worldcover_flood_proneness_0_1": "WorldCover flood-prone land cover",
    "river_proximity_0_1": "River proximity",
    "drainage_density_0_1": "Drainage density",
    "catchment_wetness_0_1": "Catchment wetness",
    "soil_runoff_potential_0_1": "Soil runoff potential",
    "rainfall_climatology_0_1": "Rainfall climatology",
}

REQUIRED_INPUT_COLUMNS: tuple[str, ...] = (
    "unit_id",
    *AGGREGATE_FEATURE_SCHEMA,
    "current_sar_probability_0_1",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

VALID_CONFIDENCE_CLASSES = frozenset({"low", "medium", "high"})


class HistoricalSusceptibilityError(ValueError):
    """Raised when susceptibility inputs or validation groups are invalid."""


@dataclass(frozen=True)
class HistoricalSusceptibilityPolicy:
    """Versioned scoring and conflict policy for historical context."""

    feature_weights: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_FEATURE_WEIGHTS)
    )
    minimum_available_weight_0_1: float = 0.60
    high_sar_threshold_0_1: float = 0.75
    low_sar_threshold_0_1: float = 0.25
    high_susceptibility_threshold_0_100: float = 70.0
    low_susceptibility_threshold_0_100: float = 35.0
    model_method: str = "transparent_monotonic_additive_baseline"
    calibration_status: str = "uncalibrated_requires_basin_event_target_corpus"
    schema_version: str = FEATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        weights = dict(self.feature_weights)
        if set(weights) != set(AGGREGATE_FEATURE_SCHEMA):
            raise HistoricalSusceptibilityError(
                "feature_weights must contain every aggregate feature exactly once."
            )
        for feature_name, weight in weights.items():
            _finite_range(weight, f"feature_weights[{feature_name}]", 0.0, 1.0)
            if float(weight) <= 0.0:
                raise HistoricalSusceptibilityError("Every feature weight must be positive.")
        if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12):
            raise HistoricalSusceptibilityError("feature_weights must sum to 1.0.")
        _finite_range(
            self.minimum_available_weight_0_1,
            "minimum_available_weight_0_1",
            0.0,
            1.0,
        )
        if float(self.minimum_available_weight_0_1) <= 0.0:
            raise HistoricalSusceptibilityError(
                "minimum_available_weight_0_1 must be greater than zero."
            )
        _finite_range(
            self.high_sar_threshold_0_1,
            "high_sar_threshold_0_1",
            0.0,
            1.0,
        )
        _finite_range(
            self.low_sar_threshold_0_1,
            "low_sar_threshold_0_1",
            0.0,
            1.0,
        )
        _finite_range(
            self.high_susceptibility_threshold_0_100,
            "high_susceptibility_threshold_0_100",
            0.0,
            100.0,
        )
        _finite_range(
            self.low_susceptibility_threshold_0_100,
            "low_susceptibility_threshold_0_100",
            0.0,
            100.0,
        )
        if self.low_sar_threshold_0_1 >= self.high_sar_threshold_0_1:
            raise HistoricalSusceptibilityError(
                "low_sar_threshold_0_1 must be below high_sar_threshold_0_1."
            )
        if (
            self.low_susceptibility_threshold_0_100
            >= self.high_susceptibility_threshold_0_100
        ):
            raise HistoricalSusceptibilityError(
                "Low susceptibility threshold must be below the high threshold."
            )
        if not self.model_method.strip() or not self.calibration_status.strip():
            raise HistoricalSusceptibilityError(
                "model_method and calibration_status must not be blank."
            )
        object.__setattr__(self, "feature_weights", MappingProxyType(weights))


def validate_historical_susceptibility_features(features: pd.DataFrame) -> pd.DataFrame:
    """Return a validated copy of normalized historical-context features.

    Feature columns are required but may contain missing values.  Missingness is
    made explicit during scoring; it is never converted to zero.
    """

    if not isinstance(features, pd.DataFrame):
        raise HistoricalSusceptibilityError("features must be a pandas DataFrame.")
    if features.empty:
        raise HistoricalSusceptibilityError("features must contain at least one row.")
    missing = [column for column in REQUIRED_INPUT_COLUMNS if column not in features]
    if missing:
        raise HistoricalSusceptibilityError(
            "Missing historical susceptibility columns: " + ", ".join(missing)
        )
    frame = features.copy(deep=True)
    for column in ("unit_id", "source_timestamp", "confidence_class", "assumptions"):
        blank = frame[column].isna() | frame[column].astype(str).str.strip().eq("")
        if blank.any():
            raise HistoricalSusceptibilityError(f"{column} must not be blank.")
    if frame["unit_id"].astype(str).duplicated().any():
        raise HistoricalSusceptibilityError("unit_id values must be unique.")
    invalid_confidence = sorted(
        set(frame["confidence_class"].astype(str)) - VALID_CONFIDENCE_CLASSES
    )
    if invalid_confidence:
        raise HistoricalSusceptibilityError(
            "Unsupported confidence_class value(s): " + ", ".join(invalid_confidence)
        )
    frame["source_timestamp"] = frame["source_timestamp"].map(_normalized_timestamp)

    for column in AGGREGATE_FEATURE_SCHEMA:
        if frame[column].map(_is_boolean).any():
            raise HistoricalSusceptibilityError(
                f"{column} must be numeric, not boolean."
            )
        converted = pd.to_numeric(frame[column], errors="coerce")
        invalid_nonmissing = frame[column].notna() & converted.isna()
        if invalid_nonmissing.any():
            raise HistoricalSusceptibilityError(
                f"{column} must contain numbers or missing values."
            )
        finite = converted.dropna().map(lambda value: math.isfinite(float(value)))
        if not finite.all() or ((converted.dropna() < 0) | (converted.dropna() > 1)).any():
            raise HistoricalSusceptibilityError(f"{column} must be within 0..1 when present.")
        frame[column] = converted.astype(float)

    if frame["current_sar_probability_0_1"].map(_is_boolean).any():
        raise HistoricalSusceptibilityError(
            "current_sar_probability_0_1 must be numeric, not boolean."
        )
    sar = pd.to_numeric(frame["current_sar_probability_0_1"], errors="coerce")
    invalid_sar = frame["current_sar_probability_0_1"].notna() & sar.isna()
    if invalid_sar.any():
        raise HistoricalSusceptibilityError(
            "current_sar_probability_0_1 must contain numbers or missing values."
        )
    finite_sar = sar.dropna().map(lambda value: math.isfinite(float(value)))
    if not finite_sar.all() or ((sar.dropna() < 0) | (sar.dropna() > 1)).any():
        raise HistoricalSusceptibilityError(
            "current_sar_probability_0_1 must be within 0..1 when present."
        )
    frame["current_sar_probability_0_1"] = sar.astype(float)
    return frame


def score_historical_susceptibility(
    features: pd.DataFrame,
    *,
    policy: HistoricalSusceptibilityPolicy | None = None,
) -> pd.DataFrame:
    """Score historical susceptibility and compare it with current SAR evidence.

    Available positive weights are renormalized per row.  Rows below the
    declared coverage floor are retained with a missing score and an explicit
    low-confidence warning instead of silently imputing missing context.
    """

    active_policy = policy or HistoricalSusceptibilityPolicy()
    frame = validate_historical_susceptibility_features(features)
    rows: list[dict[str, object]] = []
    for record in frame.to_dict(orient="records"):
        available = {
            feature_name: float(record[feature_name])
            for feature_name in AGGREGATE_FEATURE_SCHEMA
            if pd.notna(record[feature_name])
        }
        missing_features = [
            feature_name
            for feature_name in AGGREGATE_FEATURE_SCHEMA
            if feature_name not in available
        ]
        available_weight = sum(
            float(active_policy.feature_weights[name]) for name in available
        )
        contributions: dict[str, float] = {}
        if available and available_weight >= active_policy.minimum_available_weight_0_1:
            contributions = {
                name: round(
                    100.0
                    * float(active_policy.feature_weights[name])
                    * value
                    / available_weight,
                    6,
                )
                for name, value in available.items()
            }
            susceptibility: float | None = round(sum(contributions.values()), 6)
            susceptibility_class = _susceptibility_class(susceptibility)
            top_driver = max(contributions, key=lambda name: (contributions[name], name))
            explanation = (
                f"Top contribution: {FEATURE_LABELS[top_driver]} "
                f"({contributions[top_driver]:.1f} points); "
                f"available feature-weight coverage {available_weight:.0%}."
            )
        else:
            susceptibility = None
            susceptibility_class = "unavailable"
            top_driver = "unavailable"
            explanation = (
                "Historical susceptibility withheld because available feature-weight "
                f"coverage {available_weight:.0%} is below the declared "
                f"{active_policy.minimum_available_weight_0_1:.0%} minimum."
            )
        output_confidence = _context_confidence(
            str(record["confidence_class"]),
            available_weight,
            active_policy.minimum_available_weight_0_1,
        )
        conflict_status, conflict_warning = classify_context_conflict(
            record["current_sar_probability_0_1"],
            susceptibility,
            policy=active_policy,
        )
        rows.append(
            {
                "unit_id": str(record["unit_id"]),
                "historical_susceptibility_0_100": susceptibility,
                "historical_susceptibility_class": susceptibility_class,
                "historical_explanation": explanation,
                "historical_top_driver": top_driver,
                "historical_feature_contributions_json": json.dumps(
                    contributions,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "historical_available_weight_0_1": round(available_weight, 6),
                "historical_missing_features": "|".join(missing_features),
                "historical_conflict_status": conflict_status,
                "historical_conflict_warning": conflict_warning,
                "current_sar_probability_0_1": record[
                    "current_sar_probability_0_1"
                ],
                "context_label": CONTEXT_LABEL,
                "context_boundary": CONTEXT_BOUNDARY,
                "eligible_as_current_flood": False,
                "eligible_as_forecast": False,
                "eligible_to_replace_event_sar": False,
                "model_method": active_policy.model_method,
                "calibration_status": active_policy.calibration_status,
                "source_timestamp": str(record["source_timestamp"]),
                "confidence_class": output_confidence,
                "assumptions": (
                    f"{record['assumptions']} Historical context is auxiliary only; "
                    "it does not replace event-time SAR evidence."
                ),
                "feature_schema_version": active_policy.schema_version,
                "output_schema_version": OUTPUT_SCHEMA_VERSION,
            }
        )
    return pd.DataFrame(rows)


def classify_context_conflict(
    current_sar_probability_0_1: object,
    historical_susceptibility_0_100: float | None,
    *,
    policy: HistoricalSusceptibilityPolicy | None = None,
) -> tuple[str, str]:
    """Return a warning when current SAR and historical plausibility diverge."""

    active_policy = policy or HistoricalSusceptibilityPolicy()
    if pd.isna(current_sar_probability_0_1) or historical_susceptibility_0_100 is None:
        return (
            "not_evaluated",
            "Plausibility comparison unavailable; missing current SAR or historical context.",
        )
    sar = float(current_sar_probability_0_1)
    susceptibility = float(historical_susceptibility_0_100)
    _finite_range(sar, "current_sar_probability_0_1", 0.0, 1.0)
    _finite_range(susceptibility, "historical_susceptibility_0_100", 0.0, 100.0)
    if (
        sar >= active_policy.high_sar_threshold_0_1
        and susceptibility <= active_policy.low_susceptibility_threshold_0_100
    ):
        return (
            "current_sar_high_historical_low",
            "Current SAR is high while historical susceptibility is low. Verify "
            "terrain, radar shadow, urban artefacts, timing, and provenance; do not "
            "discard the current observation automatically.",
        )
    if (
        sar <= active_policy.low_sar_threshold_0_1
        and susceptibility >= active_policy.high_susceptibility_threshold_0_100
    ):
        return (
            "current_sar_low_historical_high",
            "Historical susceptibility is high while current SAR is low. Susceptibility "
            "does not establish current flooding; verify acquisition timing and coverage.",
        )
    return (
        "none",
        "No strong current-SAR versus historical-context conflict under the declared policy.",
    )


def run_monotonicity_checks(
    features: pd.DataFrame,
    *,
    policy: HistoricalSusceptibilityPolicy | None = None,
    increment: float = 0.01,
) -> pd.DataFrame:
    """Check that increasing each available susceptibility feature never lowers score."""

    active_policy = policy or HistoricalSusceptibilityPolicy()
    _finite_range(increment, "increment", 0.0, 1.0)
    if float(increment) <= 0:
        raise HistoricalSusceptibilityError("increment must be greater than zero.")
    frame = validate_historical_susceptibility_features(features)
    baseline = score_historical_susceptibility(frame, policy=active_policy).set_index(
        "unit_id"
    )
    checks: list[dict[str, object]] = []
    for row_index, record in frame.iterrows():
        unit_id = str(record["unit_id"])
        baseline_score = baseline.at[unit_id, "historical_susceptibility_0_100"]
        for feature_name in AGGREGATE_FEATURE_SCHEMA:
            value = record[feature_name]
            if pd.isna(value) or float(value) >= 1.0 or pd.isna(baseline_score):
                continue
            perturbed = frame.loc[[row_index]].copy()
            perturbed.at[row_index, feature_name] = min(1.0, float(value) + increment)
            perturbed_score = score_historical_susceptibility(
                perturbed,
                policy=active_policy,
            ).iloc[0]["historical_susceptibility_0_100"]
            delta = float(perturbed_score) - float(baseline_score)
            checks.append(
                {
                    "unit_id": unit_id,
                    "feature_name": feature_name,
                    "baseline_score_0_100": baseline_score,
                    "perturbed_score_0_100": perturbed_score,
                    "score_delta": round(delta, 9),
                    "monotonicity_passed": delta >= -1e-9,
                    "source_timestamp": str(record["source_timestamp"]),
                    "confidence_class": str(record["confidence_class"]),
                    "assumptions": (
                        f"{record['assumptions']} One-feature positive perturbation "
                        "checks score monotonicity only."
                    ),
                }
            )
    return pd.DataFrame(
        checks,
        columns=(
            "unit_id",
            "feature_name",
            "baseline_score_0_100",
            "perturbed_score_0_100",
            "score_delta",
            "monotonicity_passed",
            "source_timestamp",
            "confidence_class",
            "assumptions",
        ),
    )


def partition_basin_event_groups(
    rows: pd.DataFrame,
    *,
    test_basins: Iterable[str],
    test_events: Iterable[str],
    calibration_basins: Iterable[str] = (),
    calibration_events: Iterable[str] = (),
    basin_column: str = "basin_id",
    event_column: str = "event_id",
) -> pd.DataFrame:
    """Assign complete connected basin/event groups to train/calibration/test.

    Basin and event identifiers form a bipartite graph.  A seeded test or
    calibration identifier assigns its entire connected component, preventing a
    basin or event from leaking across partitions.  Conflicting seeds fail.
    """

    if not isinstance(rows, pd.DataFrame) or rows.empty:
        raise HistoricalSusceptibilityError("rows must be a non-empty DataFrame.")
    for column in (
        basin_column,
        event_column,
        "source_timestamp",
        "confidence_class",
        "assumptions",
    ):
        if column not in rows:
            raise HistoricalSusceptibilityError(f"Missing grouping column: {column}")
        if rows[column].isna().any() or rows[column].astype(str).str.strip().eq("").any():
            raise HistoricalSusceptibilityError(f"{column} must not be blank.")
    invalid_confidence = sorted(
        set(rows["confidence_class"].astype(str)) - VALID_CONFIDENCE_CLASSES
    )
    if invalid_confidence:
        raise HistoricalSusceptibilityError(
            "Unsupported confidence_class value(s): " + ", ".join(invalid_confidence)
        )

    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        if parent[node] != node:
            parent[node] = find(parent[node])
        return parent[node]

    def union(first: str, second: str) -> None:
        root_first = find(first)
        root_second = find(second)
        if root_first != root_second:
            parent[root_second] = root_first

    for record in rows.loc[:, [basin_column, event_column]].itertuples(index=False):
        union(f"basin:{record[0]}", f"event:{record[1]}")

    seeds = [
        *((f"basin:{value}", "test") for value in test_basins),
        *((f"event:{value}", "test") for value in test_events),
        *((f"basin:{value}", "calibration") for value in calibration_basins),
        *((f"event:{value}", "calibration") for value in calibration_events),
    ]
    component_partitions: dict[str, set[str]] = {}
    for node, partition in seeds:
        if node not in parent:
            raise HistoricalSusceptibilityError(f"Unknown holdout identifier: {node}")
        component_partitions.setdefault(find(node), set()).add(partition)
    conflicts = [
        root
        for root, partitions in component_partitions.items()
        if len(partitions) > 1
    ]
    if conflicts:
        raise HistoricalSusceptibilityError(
            "Basin/event graph component received conflicting holdout assignments."
        )

    result = rows.copy(deep=True)
    result["source_timestamp"] = result["source_timestamp"].map(_normalized_timestamp)
    result["partition"] = [
        next(
            iter(component_partitions.get(find(f"basin:{basin}"), {"train"}))
        )
        for basin in result[basin_column].astype(str)
    ]
    validate_basin_event_partition(
        result,
        basin_column=basin_column,
        event_column=event_column,
    )
    return result


def validate_basin_event_partition(
    rows: pd.DataFrame,
    *,
    basin_column: str = "basin_id",
    event_column: str = "event_id",
    partition_column: str = "partition",
) -> bool:
    """Raise if any basin or event appears in more than one data partition."""

    required = (basin_column, event_column, partition_column)
    missing = [column for column in required if column not in rows]
    if missing:
        raise HistoricalSusceptibilityError(
            "Missing partition columns: " + ", ".join(missing)
        )
    invalid = sorted(
        set(rows[partition_column].astype(str)) - {"train", "calibration", "test"}
    )
    if invalid:
        raise HistoricalSusceptibilityError(
            "Unsupported partition value(s): " + ", ".join(invalid)
        )
    for column in (basin_column, event_column):
        leakage = rows.groupby(column, dropna=False)[partition_column].nunique()
        if (leakage > 1).any():
            leaked = ", ".join(str(value) for value in leakage[leakage > 1].index)
            raise HistoricalSusceptibilityError(
                f"{column} leaks across partitions: {leaked}"
            )
    return True


def _susceptibility_class(score: float) -> str:
    if score < 33.333333:
        return "low"
    if score < 66.666667:
        return "moderate"
    return "high"


def _context_confidence(
    input_confidence: str,
    available_weight: float,
    minimum_weight: float,
) -> str:
    if available_weight < minimum_weight or input_confidence == "low":
        return "low"
    if available_weight < 1.0 - 1e-12 or input_confidence == "medium":
        return "medium"
    return "high"


def _finite_range(value: object, label: str, minimum: float, maximum: float) -> None:
    if isinstance(value, bool):
        raise HistoricalSusceptibilityError(f"{label} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalSusceptibilityError(f"{label} must be numeric.") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise HistoricalSusceptibilityError(
            f"{label} must be finite and within {minimum}..{maximum}."
        )


def _is_boolean(value: object) -> bool:
    value_type = type(value)
    return isinstance(value, bool) or (
        value_type.__module__ == "numpy" and value_type.__name__ in {"bool", "bool_"}
    )


def _normalized_timestamp(value: object) -> str:
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoricalSusceptibilityError(
            "source_timestamp must be an ISO-8601 timestamp."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HistoricalSusceptibilityError(
            "source_timestamp must include an explicit timezone."
        )
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
