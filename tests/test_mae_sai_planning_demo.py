"""Acceptance checks for the static historical planning rehearsal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from floodguard.access import calculate_access_loss
from floodguard.equity import compute_equity_gap, equity_input_from_access_loss
from floodguard.scenarios import run_access_scenario

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apps/web/src/data/mae-sai-planning-demo.json"


@pytest.fixture(scope="module")
def case() -> dict:
    return json.loads(PACKAGE.read_text(encoding="utf-8"))


def test_package_and_every_input_match_their_content_digest(case: dict) -> None:
    unsigned = {**case, "meta": dict(case["meta"])}
    declared = unsigned["meta"].pop("package_sha256")
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert hashlib.sha256(canonical.encode()).hexdigest() == declared
    for source in case["sources"]:
        assert (
            hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest()
            == source["sha256"]
        )


def test_historical_scope_and_priority_are_not_promoted(case: dict) -> None:
    assert case["meta"]["operational_status"] == "non_operational"
    assert case["meta"]["can_feed_decision_layer"] is False
    assert case["meta"]["official_warning"] is False
    assert case["meta"]["fpps_recalculated"] is False
    assert case["meta"]["local_accuracy_status"] == "unqualified_local_accuracy"
    assert case["meta"]["source_timestamp"].startswith("2024-09-")
    assert case["meta"]["source_processing_timestamp"].startswith("2026-")
    original = json.loads(
        (ROOT / "outputs/mae_sai_priority_subdistricts.geojson").read_text()
    )
    priorities = {
        f["properties"]["subdistrict_id"]: f["properties"] for f in original["features"]
    }
    assert set(priorities) == {a["area_id"] for a in case["areas"]}
    for area in case["areas"]:
        source = priorities[area["area_id"]]
        assert area["existing_priority"]["fpps"] == source["fpps_0_100"]
        assert area["existing_priority"]["action_class"] == source["action_class"]
        assert area["baseline"]["baseline_underserved_30_min"] >= 0
        assert (
            abs(
                area["baseline"]["people_losing_30_min_access"]
                - float(source["people_losing_30_min_access"])
            )
            <= 0.5
        )
        assert (
            area["baseline"]["baseline_underserved_30_min"]
            + area["baseline"]["people_losing_30_min_access"]
            <= area["baseline"]["total_population"] + 0.5
        )
        assert (
            area["baseline"]["total_population"]
            >= area["baseline"]["people_losing_30_min_access"]
        )


def test_registered_scenarios_have_expected_direction_and_consistent_deltas(
    case: dict,
) -> None:
    scenarios = {s["scenario_id"]: s for s in case["scenarios"]}
    assert set(scenarios) == {"baseline", "close_road", "add_temporary_shelter"}
    assert scenarios["baseline"]["overall"]["change_people_losing_30_min_access"] == 0
    assert scenarios["close_road"]["overall"]["change_people_losing_30_min_access"] > 0
    assert all(
        row["change_people_losing_30_min_access"] >= 0
        for row in scenarios["close_road"]["areas"]
    )
    assert (
        scenarios["add_temporary_shelter"]["overall"][
            "change_people_losing_30_min_access"
        ]
        < 0
    )
    for scenario in scenarios.values():
        for row in scenario["areas"]:
            assert (
                row["change_people_losing_30_min_access"]
                == row["scenario_people_losing_30_min_access"]
                - row["baseline_people_losing_30_min_access"]
            )
            if row["change_equity_gap_ratio"] is not None:
                assert row["change_equity_gap_ratio"] == pytest.approx(
                    row["scenario_equity_gap_ratio"] - row["baseline_equity_gap_ratio"]
                )


def test_preexisting_underservice_is_not_counted_as_new_loss() -> None:
    # The 40-minute settlement already lacks 30-minute access. A cut connection
    # newly removes access from only the 10-minute settlement (20 people).
    population = pd.DataFrame(
        [
            {
                "node_id": "near",
                "subdistrict_id": "A",
                "subdistrict_name": "A",
                "total_population": 20,
                "vulnerable_population": 10,
                "non_vulnerable_population": 10,
            },
            {
                "node_id": "far",
                "subdistrict_id": "A",
                "subdistrict_name": "A",
                "total_population": 80,
                "vulnerable_population": 40,
                "non_vulnerable_population": 40,
            },
        ]
    )
    edges = pd.DataFrame(
        [
            {
                "from_node": "near",
                "to_node": "facility",
                "normal_minutes": 10,
                "disrupted_minutes": 10,
            },
            {
                "from_node": "far",
                "to_node": "near",
                "normal_minutes": 30,
                "disrupted_minutes": 30,
            },
        ]
    )
    facilities = pd.DataFrame(
        [{"facility_id": "F", "facility_type": "clinic", "node_id": "facility"}]
    )
    baseline = calculate_access_loss(population, edges, facilities)
    equity = compute_equity_gap(equity_input_from_access_loss(baseline))
    scenario = run_access_scenario(
        population,
        edges,
        facilities,
        "close_road",
        from_node="near",
        to_node="facility",
        baseline_access=baseline,
        baseline_equity=equity,
    )
    assert baseline.iloc[0]["people_losing_30_min_access"] == 0
    assert scenario["access_loss"].iloc[0]["people_losing_30_min_access"] == 20
    assert scenario["equity_gap"].iloc[0]["equity_gap_ratio"] == 1
    # A 15-minute alternate connection means nobody newly loses access.
    alternative = pd.concat(
        [
            edges,
            pd.DataFrame(
                [
                    {
                        "from_node": "near",
                        "to_node": "alternative",
                        "normal_minutes": 5,
                        "disrupted_minutes": 5,
                    },
                    {
                        "from_node": "alternative",
                        "to_node": "facility",
                        "normal_minutes": 10,
                        "disrupted_minutes": 10,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    with_alternative = run_access_scenario(
        population,
        alternative,
        facilities,
        "close_road",
        from_node="near",
        to_node="facility",
        baseline_access=baseline,
        baseline_equity=equity,
    )
    assert with_alternative["access_loss"].iloc[0]["people_losing_30_min_access"] == 0
