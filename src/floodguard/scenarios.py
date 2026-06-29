"""Fixture-backed access scenario helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd

from floodguard.access import calculate_access_loss
from floodguard.equity import compute_equity_gap, equity_input_from_access_loss

SCENARIO_COMPARISON_COLUMNS: tuple[str, ...] = (
    "baseline_people_losing_30_min_access",
    "baseline_equity_gap_ratio",
    "temporary_shelter_people_losing_30_min_access",
    "temporary_shelter_change_people_losing_30_min_access",
    "temporary_shelter_equity_gap_ratio",
    "temporary_shelter_change_equity_gap_ratio",
    "road_closure_people_losing_30_min_access",
    "road_closure_change_people_losing_30_min_access",
    "road_closure_equity_gap_ratio",
    "road_closure_change_equity_gap_ratio",
)


class ScenarioError(ValueError):
    """Raised when a scenario request is invalid."""


def run_access_scenario(
    population: pd.DataFrame,
    edges: pd.DataFrame,
    facilities: pd.DataFrame,
    scenario_name: str,
    **kwargs: Any,
) -> dict[str, pd.DataFrame]:
    """Run a fixture-backed access scenario and return outputs."""

    if scenario_name == "add_temporary_shelter":
        scenario_edges = edges.copy()
        scenario_facilities = _add_temporary_shelter(facilities, **kwargs)
    elif scenario_name == "close_road":
        scenario_edges = _close_road(edges, **kwargs)
        scenario_facilities = facilities.copy()
    else:
        raise ScenarioError(f"Unknown access scenario: {scenario_name}")

    access_loss = calculate_access_loss(population, scenario_edges, scenario_facilities)
    equity_gap = compute_equity_gap(equity_input_from_access_loss(access_loss, threshold=30))
    scenario_summary = _build_scenario_summary(
        scenario_name=scenario_name,
        baseline_access=kwargs.get("baseline_access"),
        scenario_access=access_loss,
        baseline_equity=kwargs.get("baseline_equity"),
        scenario_equity=equity_gap,
    )
    return {
        "access_loss": access_loss,
        "equity_gap": equity_gap,
        "scenario_summary": scenario_summary,
    }


def build_scenario_comparison(
    baseline_access: pd.DataFrame,
    baseline_equity: pd.DataFrame,
    temporary_shelter_access: pd.DataFrame,
    temporary_shelter_equity: pd.DataFrame,
    road_closure_access: pd.DataFrame,
    road_closure_equity: pd.DataFrame,
) -> pd.DataFrame:
    """Build one scenario-comparison row per baseline access subdistrict."""

    baseline = _access_equity_frame(
        baseline_access,
        baseline_equity,
        "baseline",
        include_change=False,
    )
    temporary_shelter = _access_equity_frame(
        temporary_shelter_access,
        temporary_shelter_equity,
        "temporary_shelter",
        baseline=baseline,
    )
    road_closure = _access_equity_frame(
        road_closure_access,
        road_closure_equity,
        "road_closure",
        baseline=baseline,
    )

    result = baseline.merge(
        temporary_shelter,
        on="subdistrict_id",
        how="left",
        validate="one_to_one",
    ).merge(
        road_closure,
        on="subdistrict_id",
        how="left",
        validate="one_to_one",
    )

    missing_columns = [
        column
        for column in SCENARIO_COMPARISON_COLUMNS
        if column not in result.columns or result[column].isna().all()
    ]
    if missing_columns:
        raise ScenarioError(
            "Scenario comparison could not build required column(s): "
            + ", ".join(missing_columns)
        )
    return result.loc[:, ("subdistrict_id", *SCENARIO_COMPARISON_COLUMNS)]


def merge_scenario_comparison(
    priority_frame: pd.DataFrame,
    scenario_comparison: pd.DataFrame,
) -> pd.DataFrame:
    """Merge scenario-comparison fields into priority rows before GeoJSON export."""

    _validate_required(priority_frame, ("subdistrict_id",), "priority")
    _validate_required(
        scenario_comparison,
        ("subdistrict_id", *SCENARIO_COMPARISON_COLUMNS),
        "scenario_comparison",
    )
    _validate_unique(priority_frame, "subdistrict_id", "priority")
    _validate_unique(scenario_comparison, "subdistrict_id", "scenario_comparison")

    priority_ids = set(priority_frame["subdistrict_id"].astype(str))
    comparison_ids = set(scenario_comparison["subdistrict_id"].astype(str))
    missing = sorted(priority_ids - comparison_ids)
    if missing:
        raise ScenarioError(
            "Missing scenario comparison row(s) for subdistrict_id: "
            + ", ".join(missing)
        )

    merged = priority_frame.merge(
        scenario_comparison,
        on="subdistrict_id",
        how="left",
        validate="one_to_one",
    )
    return merged


def _add_temporary_shelter(
    facilities: pd.DataFrame,
    facility_id: str = "TEMP-SHELTER-001",
    facility_type: str = "shelter",
    node_id: str = "P2A",
    **_: Any,
) -> pd.DataFrame:
    if "facility_id" not in facilities.columns:
        raise ScenarioError("facilities must include facility_id.")
    if facility_id in set(facilities["facility_id"].astype(str)):
        raise ScenarioError(f"Temporary shelter already exists: {facility_id}")
    new_facility = pd.DataFrame(
        [
            {
                "facility_id": facility_id,
                "facility_type": facility_type,
                "node_id": node_id,
            }
        ]
    )
    return pd.concat([facilities, new_facility], ignore_index=True)


def _close_road(
    edges: pd.DataFrame,
    from_node: str = "P2B",
    to_node: str = "F1",
    **_: Any,
) -> pd.DataFrame:
    required = {"from_node", "to_node", "disrupted_minutes"}
    missing = sorted(required - set(edges.columns))
    if missing:
        raise ScenarioError(f"edges missing required column(s): {', '.join(missing)}")
    result = edges.copy()
    forward = (result["from_node"].astype(str) == from_node) & (
        result["to_node"].astype(str) == to_node
    )
    backward = (result["from_node"].astype(str) == to_node) & (
        result["to_node"].astype(str) == from_node
    )
    match = forward | backward
    if not match.any():
        raise ScenarioError(f"No edge found between {from_node} and {to_node}.")
    result.loc[match, "disrupted_minutes"] = pd.NA
    return result


def _build_scenario_summary(
    scenario_name: str,
    baseline_access: pd.DataFrame | None,
    scenario_access: pd.DataFrame,
    baseline_equity: pd.DataFrame | None,
    scenario_equity: pd.DataFrame,
) -> pd.DataFrame:
    baseline_30 = _sum_column(baseline_access, "people_losing_30_min_access")
    scenario_30 = _sum_column(scenario_access, "people_losing_30_min_access")
    baseline_equity_ratio = _max_equity_ratio(baseline_equity)
    scenario_equity_ratio = _max_equity_ratio(scenario_equity)
    return pd.DataFrame(
        [
            {
                "scenario_name": scenario_name,
                "baseline_people_losing_30_min_access": baseline_30,
                "scenario_people_losing_30_min_access": scenario_30,
                "change_people_losing_30_min_access": scenario_30 - baseline_30,
                "baseline_max_equity_gap_ratio": baseline_equity_ratio,
                "scenario_max_equity_gap_ratio": scenario_equity_ratio,
                "change_max_equity_gap_ratio": (
                    scenario_equity_ratio - baseline_equity_ratio
                    if pd.notna(baseline_equity_ratio)
                    and pd.notna(scenario_equity_ratio)
                    else pd.NA
                ),
            }
        ]
    )


def _sum_column(frame: pd.DataFrame | None, column: str) -> float:
    if frame is None or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def _max_equity_ratio(frame: pd.DataFrame | None) -> float | object:
    if frame is None or "equity_gap_ratio" not in frame.columns:
        return pd.NA
    numeric = pd.to_numeric(frame["equity_gap_ratio"], errors="coerce")
    if numeric.notna().any():
        return float(numeric.max())
    return pd.NA


def _access_equity_frame(
    access: pd.DataFrame,
    equity: pd.DataFrame,
    prefix: str,
    include_change: bool = True,
    baseline: pd.DataFrame | None = None,
) -> pd.DataFrame:
    _validate_required(
        access,
        ("subdistrict_id", "people_losing_30_min_access"),
        f"{prefix}_access",
    )
    _validate_required(equity, ("subdistrict_id", "equity_gap_ratio"), f"{prefix}_equity")
    _validate_unique(access, "subdistrict_id", f"{prefix}_access")
    _validate_unique(equity, "subdistrict_id", f"{prefix}_equity")

    result = access.loc[:, ["subdistrict_id", "people_losing_30_min_access"]].copy()
    result["subdistrict_id"] = result["subdistrict_id"].astype(str)
    result["people_losing_30_min_access"] = pd.to_numeric(
        result["people_losing_30_min_access"],
        errors="coerce",
    )
    if result["people_losing_30_min_access"].isna().any():
        raise ScenarioError(f"{prefix}_access people_losing_30_min_access must be numeric.")

    equity_values = equity.loc[:, ["subdistrict_id", "equity_gap_ratio"]].copy()
    equity_values["subdistrict_id"] = equity_values["subdistrict_id"].astype(str)
    equity_values["equity_gap_ratio"] = pd.to_numeric(
        equity_values["equity_gap_ratio"],
        errors="coerce",
    )
    result = result.merge(equity_values, on="subdistrict_id", how="left", validate="one_to_one")

    result = result.rename(
        columns={
            "people_losing_30_min_access": f"{prefix}_people_losing_30_min_access",
            "equity_gap_ratio": f"{prefix}_equity_gap_ratio",
        }
    )

    if include_change:
        if baseline is None:
            raise ScenarioError("Baseline comparison is required for scenario deltas.")
        baseline_ids = set(baseline["subdistrict_id"].astype(str))
        scenario_ids = set(result["subdistrict_id"].astype(str))
        missing = sorted(baseline_ids - scenario_ids)
        if missing:
            raise ScenarioError(
                f"{prefix}_access missing scenario row(s) for subdistrict_id: "
                + ", ".join(missing)
            )
        result = result.merge(
            baseline.loc[
                :,
                [
                    "subdistrict_id",
                    "baseline_people_losing_30_min_access",
                    "baseline_equity_gap_ratio",
                ],
            ],
            on="subdistrict_id",
            how="left",
            validate="one_to_one",
        )
        result[f"{prefix}_change_people_losing_30_min_access"] = (
            result[f"{prefix}_people_losing_30_min_access"]
            - result["baseline_people_losing_30_min_access"]
        )
        result[f"{prefix}_change_equity_gap_ratio"] = _numeric_delta(
            result[f"{prefix}_equity_gap_ratio"],
            result["baseline_equity_gap_ratio"],
        )
        result = result.drop(
            columns=[
                "baseline_people_losing_30_min_access",
                "baseline_equity_gap_ratio",
            ]
        )

    return result


def _numeric_delta(values: pd.Series, baseline: pd.Series) -> pd.Series:
    result = values - baseline
    result[values.isna() | baseline.isna()] = pd.NA
    return result


def _validate_required(
    frame: pd.DataFrame,
    required_columns: tuple[str, ...],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ScenarioError(
            f"Missing required {frame_name} column(s): {', '.join(missing)}"
        )


def _validate_unique(frame: pd.DataFrame, column: str, frame_name: str) -> None:
    duplicated = frame[column].astype(str).duplicated(keep=False)
    if duplicated.any():
        values = sorted(set(frame.loc[duplicated, column].astype(str)))
        raise ScenarioError(
            f"{frame_name} has duplicate {column} value(s): {', '.join(values)}"
        )
