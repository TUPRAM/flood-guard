"""FPPS weight sensitivity helpers."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from floodguard.scoring import DEFAULT_WEIGHTS, SCORE_COMPONENTS, score_subdistricts

WEIGHT_SCENARIOS: dict[str, dict[str, float]] = {
    "default": dict(DEFAULT_WEIGHTS),
    "access_heavy": {
        **DEFAULT_WEIGHTS,
        "access_gap_0_100": 0.35,
    },
    "exposure_heavy": {
        **DEFAULT_WEIGHTS,
        "exposure_0_100": 0.40,
    },
    "road_heavy": {
        **DEFAULT_WEIGHTS,
        "road_criticality_0_100": 0.30,
    },
    "vulnerability_heavy": {
        **DEFAULT_WEIGHTS,
        "vulnerability_context_0_100": 0.25,
    },
}


class SensitivityError(ValueError):
    """Raised when sensitivity inputs violate the sensitivity contract."""


def run_weight_sensitivity(
    input_frame: pd.DataFrame,
    scenarios: Mapping[str, Mapping[str, float]] | None = None,
) -> pd.DataFrame:
    """Score subdistricts under deterministic FPPS weight scenarios."""

    active_scenarios = scenarios or WEIGHT_SCENARIOS
    records: list[pd.DataFrame] = []
    for scenario_name, weights in active_scenarios.items():
        normalized = _normalize_weights(weights)
        scored = score_subdistricts(input_frame, weights=normalized)
        scored = scored.sort_values(
            ["fpps_0_100", "subdistrict_id"],
            ascending=[False, True],
        ).reset_index(drop=True)
        scored["rank"] = scored.index + 1
        scored["weight_scenario"] = scenario_name
        for component in SCORE_COMPONENTS:
            scored[f"weight_{component}"] = normalized[component]
        records.append(
            scored.loc[
                :,
                [
                    "weight_scenario",
                    "subdistrict_id",
                    "subdistrict_name",
                    "fpps_0_100",
                    "rank",
                    "action_class",
                    "confidence_class",
                    *[f"weight_{component}" for component in SCORE_COMPONENTS],
                ],
            ]
        )
    return pd.concat(records, ignore_index=True)


def summarize_rank_instability(sensitivity_frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize rank instability by subdistrict across weight scenarios."""

    required = {
        "weight_scenario",
        "subdistrict_id",
        "subdistrict_name",
        "rank",
        "action_class",
        "confidence_class",
    }
    missing = sorted(required - set(sensitivity_frame.columns))
    if missing:
        raise SensitivityError(
            f"Missing required sensitivity column(s): {', '.join(missing)}"
        )

    default_rows = sensitivity_frame[
        sensitivity_frame["weight_scenario"].astype(str) == "default"
    ]
    if default_rows.empty:
        raise SensitivityError("Sensitivity frame must include a default scenario.")

    grouped = sensitivity_frame.groupby(
        ["subdistrict_id", "subdistrict_name"],
        sort=True,
        dropna=False,
    )
    summary = grouped["rank"].agg(best_rank="min", worst_rank="max").reset_index()
    summary["rank_range"] = summary["worst_rank"] - summary["best_rank"]
    summary["ranking_unstable"] = summary["rank_range"] >= 2

    defaults = default_rows.loc[
        :,
        [
            "subdistrict_id",
            "rank",
            "action_class",
            "confidence_class",
        ],
    ].rename(
        columns={
            "rank": "default_rank",
            "action_class": "default_action_class",
        }
    )
    result = summary.merge(defaults, on="subdistrict_id", how="left", validate="one_to_one")
    return result.loc[
        :,
        [
            "subdistrict_id",
            "subdistrict_name",
            "default_rank",
            "best_rank",
            "worst_rank",
            "rank_range",
            "default_action_class",
            "confidence_class",
            "ranking_unstable",
        ],
    ].sort_values(["ranking_unstable", "rank_range", "default_rank"], ascending=[False, False, True])


def _normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    missing = sorted(set(SCORE_COMPONENTS) - set(weights))
    unknown = sorted(set(weights) - set(SCORE_COMPONENTS))
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing weights: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown weights: {', '.join(unknown)}")
        raise SensitivityError("; ".join(details))
    parsed = {component: float(weights[component]) for component in SCORE_COMPONENTS}
    if any(weight < 0 for weight in parsed.values()):
        raise SensitivityError("Sensitivity weights must be non-negative.")
    total = sum(parsed.values())
    if total <= 0:
        raise SensitivityError("At least one sensitivity weight must be greater than zero.")
    return {component: weight / total for component, weight in parsed.items()}
