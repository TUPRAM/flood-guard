"""Bounded scenario-only FPPS sensitivity for an existing candidate package.

This diagnostic never produces an accepted score, class or warning. It keeps
the fixed scorer and default weights unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

from floodguard.scoring import (
    DEFAULT_WEIGHTS,
    SCORE_COMPONENTS,
    score_subdistricts,
    validate_weights,
)

SCHEMA_VERSION = "floodguard.candidate_scoring_sensitivity.v1"
COMPONENT_STRESS_PP = 20.0
WEIGHT_MULTIPLIERS = (0.5, 1.5)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ScoringSensitivityError(ValueError):
    """Raised when candidate evidence or a scenario diagnostic is ambiguous."""


def analyze_candidate_scoring_sensitivity(
    input_file: Path, *, mode: str | None = None
) -> dict[str, Any]:
    """Analyze one source-bound candidate package under a fixed scenario plan."""

    source = Path(input_file)
    if source.is_symlink() or not source.is_file():
        raise ScoringSensitivityError("input must be a regular candidate JSON file")
    if source.stat().st_size > 32 * 1024 * 1024:
        raise ScoringSensitivityError("candidate JSON exceeds 32 MiB")
    raw = source.read_bytes()
    try:
        source_package = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise ScoringSensitivityError("candidate JSON is invalid") from error
    analysis_sha256 = None
    if isinstance(source_package, dict) and "flood_scenarios" in source_package:
        if mode is None:
            raise ScoringSensitivityError("finals analysis requires an explicit mode")
        digest = source_package.get("analysis_sha256")
        try:
            canonical = (
                json.dumps(
                    {
                        key: value
                        for key, value in source_package.items()
                        if key != "analysis_sha256"
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        except ValueError as error:
            raise ScoringSensitivityError(
                "finals analysis contains nonfinite values"
            ) from error
        if digest != hashlib.sha256(canonical).hexdigest():
            raise ScoringSensitivityError("finals analysis self-hash changed")
        scenarios = source_package["flood_scenarios"]
        if not isinstance(scenarios, dict) or mode not in scenarios:
            raise ScoringSensitivityError("requested finals mode is unavailable")
        package = scenarios[mode]
        analysis_sha256 = digest
    else:
        if mode is not None:
            raise ScoringSensitivityError("mode is only valid for a finals analysis")
        package = source_package
    areas = _validate_candidate(package)
    variants = _variants()
    baseline_by_area = {}
    scored_by_variant = {}
    for variant in variants:
        frames = []
        for area in areas:
            components, assumed = _scenario_components(
                area["components"], variant["component_changes"]
            )
            row = {
                "subdistrict_id": area["area_id"],
                "subdistrict_name": area["area_id"],
                "confidence_class": "low",
                **components,
            }
            scored = score_subdistricts(
                pd.DataFrame([row]), weights=variant["requested_weights"]
            ).iloc[0]
            frames.append(
                {
                    "area_id": area["area_id"],
                    "fpps_0_100": float(scored["fpps_0_100"]),
                    "action_class": str(scored["action_class"]),
                    "action_reason_code": str(scored["action_reason_code"]),
                    "assumed_components": assumed,
                }
            )
        ordered = sorted(
            frames, key=lambda item: (-item["fpps_0_100"], item["area_id"])
        )
        for rank, row in enumerate(ordered, start=1):
            row["scenario_rank"] = rank
        scored_by_variant[variant["id"]] = {row["area_id"]: row for row in ordered}
        if variant["id"] == "baseline_missing_50":
            baseline_by_area = scored_by_variant[variant["id"]]

    area_results = []
    for area in areas:
        area_id = area["area_id"]
        baseline = baseline_by_area[area_id]
        comparisons = []
        for variant in variants:
            row = scored_by_variant[variant["id"]][area_id]
            comparisons.append(
                {
                    "scenario_id": variant["id"],
                    "fpps_0_100": row["fpps_0_100"],
                    "delta_from_baseline": round(
                        row["fpps_0_100"] - baseline["fpps_0_100"], 2
                    ),
                    "scenario_rank": row["scenario_rank"],
                    "action_class": row["action_class"],
                    "action_reason_code": row["action_reason_code"],
                    "assumed_components": row["assumed_components"],
                }
            )
        one_at_a_time = [
            row for row in comparisons if row["scenario_id"].startswith("oat_")
        ]
        dominant = min(
            one_at_a_time,
            key=lambda row: (-abs(row["delta_from_baseline"]), row["scenario_id"]),
        )
        area_results.append(
            {
                "area_id": area_id,
                "source_components": area["components"],
                "source_missing_components": area["missing_components"],
                "accepted_fpps": None,
                "accepted_action_class": None,
                "baseline_scenario": baseline,
                "score_range_across_scenarios": [
                    min(row["fpps_0_100"] for row in comparisons),
                    max(row["fpps_0_100"] for row in comparisons),
                ],
                "rank_range_across_scenarios": [
                    min(row["scenario_rank"] for row in comparisons),
                    max(row["scenario_rank"] for row in comparisons),
                ],
                "class_retention_fraction": sum(
                    row["action_class"] == baseline["action_class"]
                    for row in comparisons
                )
                / len(comparisons),
                "dominant_one_at_a_time_change": {
                    "scenario_id": dominant["scenario_id"],
                    "absolute_score_delta": abs(dominant["delta_from_baseline"]),
                },
                "scenarios": comparisons,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "candidate_scenario_diagnostic_only",
        "official_warning": False,
        "operational": False,
        "accepted_fpps": None,
        "accepted_action_class": None,
        "input_file_sha256": hashlib.sha256(raw).hexdigest(),
        "finals_analysis_sha256": analysis_sha256,
        "selected_mode": mode,
        "event_id": package["event_id"],
        "context_sha256": package["context_sha256"],
        "candidate_provenance_sha256": hashlib.sha256(
            json.dumps(
                package["candidate_provenance"],
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest(),
        "source_timestamp": package["source_timestamp"],
        "fixed_default_weights": dict(DEFAULT_WEIGHTS),
        "plan": {
            "plan_version": "one_at_a_time_and_joint_v1",
            "baseline_missing_component_assumption": 50,
            "known_component_stress_pp": COMPONENT_STRESS_PP,
            "missing_component_endpoints": [0, 100],
            "one_at_a_time_weight_multipliers": list(WEIGHT_MULTIPLIERS),
            "joint_scenarios": [
                "joint_low",
                "joint_high",
                "joint_flood_high_network_low",
                "joint_flood_low_network_high",
            ],
            "meaning": "explicit_scenario_stress_not_confidence_interval",
        },
        "variants": variants,
        "areas": area_results,
        "limitations": [
            "All component completions and stress shifts are assumptions, not observed inputs.",
            "The candidate flood threshold and imposed road closure are not validated flood or passability evidence.",
            "Class E follows low candidate confidence and does not mean safe.",
            "Rank and score ranges describe only this finite scenario design, not statistical intervals.",
        ],
    }


def _validate_candidate(package: object) -> list[dict[str, Any]]:
    if not isinstance(package, dict):
        raise ScoringSensitivityError("candidate root must be an object")
    if (
        package.get("status") != "candidate_scenario_only"
        or package.get("official_warning") is not False
        or package.get("accepted_fpps") is not None
        or package.get("accepted_action_class") is not None
        or package.get("confidence_class") != "low"
    ):
        raise ScoringSensitivityError(
            "input is not a low-confidence candidate scenario"
        )
    if not isinstance(package.get("event_id"), str) or not package["event_id"]:
        raise ScoringSensitivityError("event_id is missing")
    if (
        not isinstance(package.get("source_timestamp"), str)
        or not package["source_timestamp"]
    ):
        raise ScoringSensitivityError("source timestamp is missing")
    if not isinstance(package.get("context_sha256"), str) or not _SHA256.fullmatch(
        package["context_sha256"]
    ):
        raise ScoringSensitivityError("context hash is invalid")
    provenance = package.get("candidate_provenance")
    if (
        not isinstance(provenance, dict)
        or provenance.get("official_warning") is not False
        or provenance.get("eligible_for_validation") is not False
        or provenance.get("event_id") != package["event_id"]
        or provenance.get("source_timestamp") != package["source_timestamp"]
    ):
        raise ScoringSensitivityError("candidate provenance is missing or unsafe")
    rows = package.get("subdistricts")
    if not isinstance(rows, list) or not rows:
        raise ScoringSensitivityError("subdistrict assessments are missing")
    areas = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("scope") != "AOI_intersection_only":
            raise ScoringSensitivityError("subdistrict scope is invalid")
        assessment = row.get("assessment")
        if not isinstance(assessment, dict):
            raise ScoringSensitivityError("subdistrict assessment is missing")
        area_id = row.get("subdistrict_id")
        if (
            not isinstance(area_id, str)
            or not area_id
            or area_id in seen
            or assessment.get("area_id") != area_id
            or assessment.get("confidence_class") != "low"
            or assessment.get("fpps_0_100") is not None
            or assessment.get("action_class") is not None
        ):
            raise ScoringSensitivityError("candidate area identity or score is unsafe")
        seen.add(area_id)
        components = assessment.get("components")
        if not isinstance(components, dict) or set(components) != set(SCORE_COMPONENTS):
            raise ScoringSensitivityError("component set differs from scoring contract")
        parsed = {}
        for key in SCORE_COMPONENTS:
            value = components[key]
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 100
            ):
                raise ScoringSensitivityError(f"{key} is not in 0..100 or null")
            parsed[key] = None if value is None else float(value)
        missing = [key for key in SCORE_COMPONENTS if parsed[key] is None]
        if assessment.get("missing_components") != missing:
            raise ScoringSensitivityError("missing component reasons were substituted")
        areas.append(
            {"area_id": area_id, "components": parsed, "missing_components": missing}
        )
    return sorted(areas, key=lambda row: row["area_id"])


def _variants() -> list[dict[str, Any]]:
    variants = []

    def add(
        identifier: str, changes: dict[str, str | float], weights: dict[str, float]
    ):
        variants.append(
            {
                "id": identifier,
                "component_changes": changes,
                "requested_weights": weights,
                "normalized_weights": validate_weights(weights),
            }
        )

    add("baseline_missing_50", {}, dict(DEFAULT_WEIGHTS))
    for component in SCORE_COMPONENTS:
        for direction in ("low", "high"):
            add(
                f"oat_{component}_{direction}",
                {component: direction},
                dict(DEFAULT_WEIGHTS),
            )
        for multiplier in WEIGHT_MULTIPLIERS:
            weights = dict(DEFAULT_WEIGHTS)
            weights[component] *= multiplier
            add(
                f"oat_weight_{component}_{multiplier:g}",
                {},
                weights,
            )
    add("joint_low", {key: "low" for key in SCORE_COMPONENTS}, dict(DEFAULT_WEIGHTS))
    add("joint_high", {key: "high" for key in SCORE_COMPONENTS}, dict(DEFAULT_WEIGHTS))
    add(
        "joint_flood_high_network_low",
        {
            "flood_likelihood_0_100": "high",
            "access_gap_0_100": "low",
            "road_criticality_0_100": "low",
        },
        dict(DEFAULT_WEIGHTS),
    )
    add(
        "joint_flood_low_network_high",
        {
            "flood_likelihood_0_100": "low",
            "access_gap_0_100": "high",
            "road_criticality_0_100": "high",
        },
        dict(DEFAULT_WEIGHTS),
    )
    return variants


def _scenario_components(
    source: dict[str, float | None], changes: dict[str, str | float]
) -> tuple[dict[str, float], dict[str, float]]:
    components = {}
    assumed = {}
    for key in SCORE_COMPONENTS:
        original = source[key]
        change = changes.get(key)
        if original is None:
            value = 50.0 if change is None else (0.0 if change == "low" else 100.0)
            assumed[key] = value
        elif change == "low":
            value = max(0.0, original - COMPONENT_STRESS_PP)
        elif change == "high":
            value = min(100.0, original + COMPONENT_STRESS_PP)
        else:
            value = original
        components[key] = value
    return components, assumed


def main() -> None:
    """Write one immutable local diagnostic JSON from a candidate package."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode", help="required for a finals analysis with flood_scenarios"
    )
    args = parser.parse_args()
    result = analyze_candidate_scoring_sensitivity(args.input, mode=args.mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(args.output)


if __name__ == "__main__":
    main()
