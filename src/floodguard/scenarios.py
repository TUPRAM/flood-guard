"""Fixture-backed access scenario helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd

from floodguard.access import calculate_access_loss
from floodguard.equity import compute_equity_gap, equity_input_from_access_loss


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
