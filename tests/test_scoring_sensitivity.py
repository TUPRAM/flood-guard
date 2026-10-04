"""Scenario-only FPPS sensitivity and unchanged class-policy boundaries."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

from floodguard.scoring import DEFAULT_WEIGHTS, score_subdistricts

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "scoring_sensitivity.py"
)
_SPEC = importlib.util.spec_from_file_location("scoring_sensitivity", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
ScoringSensitivityError = _MODULE.ScoringSensitivityError
analyze_candidate_scoring_sensitivity = _MODULE.analyze_candidate_scoring_sensitivity


def _components(exposure=80.0, access=60.0, road=40.0):
    return {
        "flood_likelihood_0_100": None,
        "exposure_0_100": exposure,
        "access_gap_0_100": access,
        "road_criticality_0_100": road,
        "vulnerability_context_0_100": None,
    }


def _area(area_id, components):
    return {
        "subdistrict_id": area_id,
        "scope": "AOI_intersection_only",
        "assessment": {
            "area_id": area_id,
            "confidence_class": "low",
            "components": components,
            "missing_components": [
                key for key, value in components.items() if value is None
            ],
            "fpps_0_100": None,
            "action_class": None,
        },
    }


def _package():
    return {
        "status": "candidate_scenario_only",
        "official_warning": False,
        "accepted_fpps": None,
        "accepted_action_class": None,
        "confidence_class": "low",
        "event_id": "synthetic-event",
        "source_timestamp": "2026-09-23T00:00:00Z",
        "context_sha256": "a" * 64,
        "candidate_provenance": {
            "event_id": "synthetic-event",
            "source_timestamp": "2026-09-23T00:00:00Z",
            "official_warning": False,
            "eligible_for_validation": False,
        },
        "subdistricts": [_area("area-1", _components())],
    }


def _write(tmp_path, value):
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_explicit_missing_completions_keep_accepted_score_null(tmp_path):
    path = _write(tmp_path, _package())
    result = analyze_candidate_scoring_sensitivity(path)
    assert result["input_file_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["accepted_fpps"] is None
    assert result["accepted_action_class"] is None
    assert result["official_warning"] is False
    assert result["fixed_default_weights"] == DEFAULT_WEIGHTS
    area = result["areas"][0]
    assert area["accepted_fpps"] is None
    assert area["accepted_action_class"] is None
    assert area["baseline_scenario"]["fpps_0_100"] == 58
    assert area["baseline_scenario"]["action_class"] == "E"
    assert area["baseline_scenario"]["action_reason_code"] == "low_confidence"
    variants = {row["scenario_id"]: row for row in area["scenarios"]}
    assert variants["oat_flood_likelihood_0_100_low"]["fpps_0_100"] == 43
    assert variants["oat_flood_likelihood_0_100_high"]["fpps_0_100"] == 73
    assert variants["oat_exposure_0_100_low"]["fpps_0_100"] == 53
    assert variants["oat_exposure_0_100_high"]["fpps_0_100"] == 63
    assert variants["joint_flood_high_network_low"]["action_class"] == "E"
    assert area["class_retention_fraction"] == 1
    assert area["dominant_one_at_a_time_change"]["absolute_score_delta"] == 15
    weight = next(
        item
        for item in result["variants"]
        if item["id"] == "oat_weight_exposure_0_100_1.5"
    )
    assert weight["requested_weights"]["exposure_0_100"] == 0.375
    assert sum(weight["normalized_weights"].values()) == pytest.approx(1)


def test_rank_range_shows_policy_weight_reversal(tmp_path):
    package = _package()
    package["subdistricts"] = [
        _area("area-a", _components(exposure=90, access=40, road=20)),
        _area("area-b", _components(exposure=50, access=70, road=60)),
    ]
    result = analyze_candidate_scoring_sensitivity(_write(tmp_path, package))
    by_area = {row["area_id"]: row for row in result["areas"]}
    assert by_area["area-a"]["baseline_scenario"]["scenario_rank"] == 2
    assert by_area["area-b"]["baseline_scenario"]["scenario_rank"] == 1
    assert by_area["area-a"]["rank_range_across_scenarios"] == [1, 2]
    assert by_area["area-b"]["rank_range_across_scenarios"] == [1, 2]
    assert all(row["class_retention_fraction"] == 1 for row in result["areas"])


def test_finals_wrapper_requires_hash_and_explicit_mode(tmp_path):
    wrapped = {"flood_scenarios": {"walking": _package()}, "analysis_sha256": None}
    canonical = (
        json.dumps(
            {"flood_scenarios": wrapped["flood_scenarios"]},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode()
    wrapped["analysis_sha256"] = hashlib.sha256(canonical).hexdigest()
    path = _write(tmp_path, wrapped)
    with pytest.raises(ScoringSensitivityError, match="explicit mode"):
        analyze_candidate_scoring_sensitivity(path)
    result = analyze_candidate_scoring_sensitivity(path, mode="walking")
    assert result["selected_mode"] == "walking"
    assert result["finals_analysis_sha256"] == wrapped["analysis_sha256"]
    with pytest.raises(ScoringSensitivityError, match="mode is unavailable"):
        analyze_candidate_scoring_sensitivity(path, mode="vehicle")
    wrapped["flood_scenarios"]["walking"]["event_id"] = "tampered"
    with pytest.raises(ScoringSensitivityError, match="self-hash changed"):
        analyze_candidate_scoring_sensitivity(_write(tmp_path, wrapped), mode="walking")


@pytest.mark.parametrize(
    "change",
    [
        lambda package: package.update(accepted_fpps=55),
        lambda package: package.update(official_warning=True),
        lambda package: package["candidate_provenance"].update(
            eligible_for_validation=True
        ),
        lambda package: package["subdistricts"][0]["assessment"]["components"].update(
            exposure_0_100=float("nan")
        ),
        lambda package: package["subdistricts"][0]["assessment"].update(
            missing_components=[]
        ),
        lambda package: package["subdistricts"][0].update(scope="full_tambon"),
    ],
)
def test_accepted_looking_or_ambiguous_candidate_is_rejected(tmp_path, change):
    package = deepcopy(_package())
    change(package)
    with pytest.raises(ScoringSensitivityError):
        analyze_candidate_scoring_sensitivity(_write(tmp_path, package))


@pytest.mark.parametrize(
    ("components", "confidence", "expected_class", "expected_reason"),
    [
        ((99, 70, 70, 80, 50), "low", "E", "low_confidence"),
        ((100, 70, 70, 80, 50), "medium", "A", "life_safety_exposure"),
        ((100, 69.99, 70, 75, 50), "medium", "B", "critical_route_access"),
        ((100, 65, 50, 10, 50), "medium", "C", "essential_service_access"),
        ((0, 0, 0, 0, 0), "medium", "E", "low_priority_score"),
    ],
)
def test_locked_class_order_and_low_confidence_override(
    components, confidence, expected_class, expected_reason
):
    keys = list(DEFAULT_WEIGHTS)
    frame = pd.DataFrame(
        [
            {
                "subdistrict_id": "synthetic",
                "subdistrict_name": "synthetic",
                "confidence_class": confidence,
                **dict(zip(keys, components, strict=True)),
            }
        ]
    )
    result = score_subdistricts(frame).iloc[0]
    assert result["action_class"] == expected_class
    assert result["action_reason_code"] == expected_reason
