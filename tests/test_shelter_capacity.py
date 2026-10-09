"""Listed shelter places against the residents in reach: the matrix 2SFCA, its reference, and the committed receipt."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import shelter_capacity as capacity
from floodguard import two_step_access

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "outputs" / "shelter_capacity" / "se1_mae_sai_v1_receipt.json"
INF = np.inf
MINUTES = np.array([[5.0, 40.0, INF],
                    [20.0, 10.0, INF],
                    [70.0, 25.0, 28.0],
                    [INF, INF, INF]])
DEMAND = np.array([100.0, 50.0, 30.0, 20.0])
SUPPLY = np.array([60.0, 40.0, 15.0])


def reference(minutes: np.ndarray, demand: np.ndarray, supply: np.ndarray) -> dict:
    context = two_step_access.TwoStepContext(
        case_id="INVENTED", event_id="invented", scenario_id="invented", service_type="shelter", travel_mode="walking",
        effective_at_utc="2026-01-01T00:00:00Z", supply_unit="places", demand_unit="people", assumptions=("invented",))
    origins = [two_step_access.DemandOrigin(f"o{i}", float(value), "people") for i, value in enumerate(demand)]
    sites = [two_step_access.ServiceSite(f"s{j}", float(value), "shelter", "places") for j, value in enumerate(supply)]
    pairs = [two_step_access.TravelPair(f"o{i}", f"s{j}", *(("reachable", float(minutes[i, j])) if np.isfinite(minutes[i, j]) else ("unreachable", None)))
             for i in range(len(demand)) for j in range(len(supply))]
    return two_step_access.calculate_binary_2sfca(context, origins, sites, pairs)


@pytest.mark.parametrize("threshold", capacity.THRESHOLDS_MINUTES)
def test_the_matrix_form_gives_what_the_reference_module_gives(threshold: int) -> None:
    mine = capacity.two_step(MINUTES, DEMAND, SUPPLY, threshold)
    theirs = reference(MINUTES, DEMAND, SUPPLY)["thresholds"][str(threshold)]
    for column, site in enumerate(sorted(theirs["sites"], key=lambda row: row["site_id"])):
        assert mine["site_catchment_demand"][column] == pytest.approx(site["known_catchment_demand"])
        if site["ratio"] is None:
            assert np.isnan(mine["site_ratio"][column])
        else:
            assert mine["site_ratio"][column] == pytest.approx(site["ratio"])
    for row, origin in enumerate(sorted(theirs["origins"], key=lambda item: item["origin_id"])):
        assert bool(mine["origin_reaches_a_site"][row]) == bool(origin["reachable_site_ids"])
        if origin["accessibility_ratio"] is None:
            assert np.isnan(mine["origin_accessibility"][row])
        else:
            assert mine["origin_accessibility"][row] == pytest.approx(origin["accessibility_ratio"])


def test_two_step_by_hand_at_30_minutes() -> None:
    run = capacity.two_step(MINUTES, DEMAND, SUPPLY, 30)
    assert run["site_catchment_demand"].tolist() == [150.0, 80.0, 30.0]
    assert run["site_ratio"].tolist() == pytest.approx([0.4, 0.5, 0.5])
    assert run["origin_accessibility"].tolist() == pytest.approx([0.4, 0.9, 1.0, 0.0])
    assert run["origin_reaches_a_site"].tolist() == [True, True, True, False]


def test_a_site_nobody_reaches_has_no_ratio() -> None:
    run = capacity.two_step(MINUTES, DEMAND, SUPPLY, 15)
    assert run["site_catchment_demand"].tolist() == [100.0, 50.0, 0.0]
    assert np.isnan(run["site_ratio"][2]) and run["origin_accessibility"][2] == 0.0


def test_the_nearest_site_counts_each_resident_once() -> None:
    nearest = capacity.nearest_site(MINUTES, 30)
    assert nearest.tolist() == [0, 1, 1, -1]
    assert capacity.assigned_demand(nearest, DEMAND, 3).tolist() == [100.0, 80.0, 0.0]
    assert capacity.nearest_site(np.array([[10.0, 10.0]]), 30).tolist() == [0], "a tie goes to the lower column"


def test_participation_divides_the_ratio_and_names_who_is_short() -> None:
    run = capacity.two_step(MINUTES, DEMAND, SUPPLY, 30)
    reading = capacity.reading(run["origin_accessibility"], run["origin_reaches_a_site"], DEMAND, participation_percent=(25, 50, 100))
    assert reading["residents"] == 200.0 and reading["residents_in_reach_of_a_shelter"] == 180.0
    full = reading["participation"]["100"]
    assert full["residents_in_reach_with_under_one_listed_place_per_person_seeking"] == 150.0, "ratios 0.4 and 0.9 are under one; 1.0 is not"
    half = reading["participation"]["50"]
    assert half["residents_in_reach_with_under_one_listed_place_per_person_seeking"] == 100.0, "0.4 / 0.5 = 0.8 is under one; 0.9 / 0.5 is not"
    assert reading["participation"]["25"]["residents_in_reach_with_under_one_listed_place_per_person_seeking"] == 0.0
    assert half["people_seeking_a_place"] == 90.0 and half["median_listed_places_per_person_seeking"] == pytest.approx(0.8)
    inside = capacity.reading(run["origin_accessibility"], run["origin_reaches_a_site"], DEMAND, where=np.array([False, False, True, True]))
    assert inside["residents"] == 50.0 and inside["residents_in_reach_of_a_shelter"] == 30.0


def test_inputs_that_do_not_fit_are_refused() -> None:
    with pytest.raises(capacity.ShelterCapacityError):
        capacity.two_step(MINUTES, DEMAND[:3], SUPPLY, 30)
    with pytest.raises(capacity.ShelterCapacityError):
        capacity.two_step(np.where(np.isinf(MINUTES), np.nan, MINUTES), DEMAND, SUPPLY, 30)
    with pytest.raises(capacity.ShelterCapacityError):
        capacity.two_step(MINUTES, DEMAND, -SUPPLY, 30)
    with pytest.raises(capacity.ShelterCapacityError):
        capacity.reading(np.zeros(4), np.ones(4, dtype=bool), DEMAND, participation_percent=(0,))


def test_the_protocol_states_the_sweep_and_the_label_the_module_applies() -> None:
    v1b = json.loads((ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    stated = v1b["facility_sets"]["two_step_access"]
    assert tuple(stated["participation_percent"]) == capacity.PARTICIPATION_PERCENT and stated["label"] == capacity.LABEL
    assert stated["fpps_input"] is False and stated["publication_level"] == "pitch"


def _numbers(value: object) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        return [number for item in value.values() for number in _numbers(item)]
    if isinstance(value, list):
        return [number for item in value for number in _numbers(item)]
    return []


def test_the_committed_receipt_holds_no_figure_of_the_shelter_service() -> None:
    if not RECEIPT.exists():
        pytest.skip("the shelter run has not been made")
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert receipt["official_warning"] is False and receipt["can_feed_decision_layer"] is False and receipt["fpps_input"] is False
    assert receipt["publication_level_of_the_result"] == "pitch" and receipt["label_of_the_result"] == capacity.LABEL
    assert receipt["confidence_class"] == "low" and receipt["source_timestamp"] and receipt["assumptions"] and receipt["limits"]
    assert all(len(item["sha256"]) == 64 and item["path"].startswith("<") for item in receipt["outputs_outside_git"])
    allowed = {15.0, 30.0, 60.0, 5.0, 10.0, 25.0}
    figures = [number for key, value in receipt.items() if key not in ("outputs_outside_git", "checks") for number in _numbers(value)]
    assert set(figures) <= allowed, "only the thresholds and the participation shares of the protocol are numbers here"
    assert b"\r" not in RECEIPT.read_bytes()
