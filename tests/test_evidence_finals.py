"""Open miniature networks test service and scenario meaning, not real-world accuracy."""

import copy
import hashlib

import pytest

from floodguard.evidence_catalog import canonical_bytes
from floodguard.evidence_finals import build_finals_analysis


def contexts():
    value = {
        "canonical_sha256": "a" * 64,
        "input_hashes": {"osm": "b" * 64},
        "official_warning": False,
        "population": [
            {
                "population_id": "p1",
                "subdistrict_id": "one",
                "total_population": 100,
                "node_id": "a",
                "snap_distance_m": 0,
            },
            {
                "population_id": "p2",
                "subdistrict_id": "one",
                "total_population": 20,
                "node_id": "c",
                "snap_distance_m": 0,
            },
            {
                "population_id": "p3",
                "subdistrict_id": "one",
                "total_population": 10,
                "node_id": None,
                "snap_distance_m": None,
            },
        ],
        "edges": [
            {"edge_id": "ab", "from_node": "a", "to_node": "b", "normal_minutes": 20},
            {"edge_id": "cd", "from_node": "c", "to_node": "d", "normal_minutes": 2},
        ],
        "osm_facilities": [
            {
                "facility_id": "clinic",
                "name": "Clinic",
                "service_type": "primary_care",
                "candidate_destination_eligible": True,
                "within_routing_context": True,
                "node_id": "b",
                "snap_distance_m": 0,
            },
            {
                "facility_id": "pharmacy",
                "service_type": "pharmacy",
                "candidate_destination_eligible": True,
                "within_routing_context": True,
                "node_id": "a",
                "snap_distance_m": 0,
            },
            {
                "facility_id": "bus-roof",
                "service_type": "shelter_context",
                "candidate_destination_eligible": False,
                "node_id": "a",
                "snap_distance_m": 0,
            },
        ],
    }
    return {mode: copy.deepcopy(value) for mode in ("walking", "modelled_vehicle")}


def build(inputs=None):
    inputs = inputs or contexts()
    for context in inputs.values():
        context["canonical_sha256"] = hashlib.sha256(
            canonical_bytes(
                {k: v for k, v in context.items() if k != "canonical_sha256"}
            )
        ).hexdigest()
    return build_finals_analysis(
        inputs, scope={}, timeline=[], generated_at="2026-09-21T00:00:00Z"
    )


def test_services_do_not_substitute_and_unknown_coverage_is_not_no_route():
    result, _ = build()
    services = {item["id"]: item for item in result["services"]}
    assert services["hospital"]["status"] == "unavailable"
    assert services["shelter"]["status"] == "unavailable"
    care = next(
        v for v in services["primary_care"]["variants"] if v["speed_factor"] == 1
    )
    assert care["baseline"]["within_15_minutes_population"] == 0
    assert care["baseline"]["within_30_minutes_population"] == 100
    assert care["baseline"]["unknown_access_population"] == 10
    assert care["baseline"]["connected_without_route_population"] == 20
    assert care["baseline"]["median_minutes"] == 20
    assert all(
        row["target_id"] != "pharmacy"
        for row in care["interventions"]
        if row["kind"] == "remove_destination"
    )


def test_shortlist_is_fixed_across_speed_cases_and_zero_effects_retained():
    result, _ = build()
    care = next(item for item in result["services"] if item["id"] == "primary_care")
    variants = [v for v in care["variants"] if v["travel_mode"] == "walking"]
    assert len(variants) == 3
    assert (
        len(
            {
                tuple((r["id"], r["target_id"]) for r in v["interventions"])
                for v in variants
            }
        )
        == 1
    )
    addition = next(
        r for r in variants[1]["interventions"] if r["kind"] == "add_destination"
    )
    assert addition["gaining_30_min_access"] == 20
    assert addition["newly_reachable_population"] == 20
    assert addition["mean_travel_time_delta_minutes"] == 0


def test_capacity_uses_linked_location_and_conserves_each_assumed_demand():
    result, _ = build()
    capacity = result["capacity"]
    assert capacity["site_id"] == "hypothetical-c"
    assert capacity["linked_access_intervention_id"] == "add_destination-1"
    assert capacity["actual_evacuation_demand"] is None
    assert capacity["actual_available_capacity"] is None
    assert len(capacity["experiments"]) == 9
    for row in capacity["experiments"]:
        assert row["assumed_demand"] == pytest.approx(
            130 * row["participation_fraction"]
        )
        assert sum(
            row[key]
            for key in (
                "assigned",
                "capacity_limited",
                "unreachable",
                "coverage_excluded",
            )
        ) == pytest.approx(row["assumed_demand"])
        assert row["assigned"] <= row["places"]


def test_empty_services_and_empty_routes_are_explicit():
    inputs = contexts()
    for ctx in inputs.values():
        ctx["osm_facilities"] = []
    result, _ = build(inputs)
    assert all(row["status"] == "unavailable" for row in result["services"])
    assert result["capacity"]["status"] == "unavailable"
    assert result["capacity"]["experiments"] == []


def test_reproducible_and_different_population_between_modes_rejected():
    assert build() == build()
    inputs = contexts()
    inputs["walking"]["population"][0]["total_population"] += 1
    with pytest.raises(ValueError, match="identical demand"):
        build(inputs)
