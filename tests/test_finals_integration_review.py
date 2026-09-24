"""Independent invariants for the prepared-pin and finals sensitivity workflow."""

from copy import deepcopy

import pytest

from floodguard.evidence_routes import build_pin_comparisons, calculate_pin_route
from floodguard.evidence_scenarios import calculate_total_access


def route_context():
    return {
        "canonical_sha256": "a" * 64,
        "node_coordinates": {
            "origin": [100, 20],
            "near": [100.001, 20],
            "far": [100.002, 20],
        },
        "edges": [
            {
                "edge_id": "fast",
                "from_node": "origin",
                "to_node": "near",
                "normal_minutes": 1.0,
                "length_m": 100,
            },
            {
                "edge_id": "parallel",
                "from_node": "origin",
                "to_node": "near",
                "normal_minutes": 2.0,
                "length_m": 110,
            },
            {
                "edge_id": "second",
                "from_node": "near",
                "to_node": "far",
                "normal_minutes": 1.0,
                "length_m": 100,
            },
        ],
        "osm_facilities": [
            {
                "facility_id": "near-hospital",
                "service_type": "hospital",
                "candidate_destination_eligible": True,
                "within_routing_context": True,
                "name": "Near hospital",
                "node_id": "near",
                "snap_distance_m": 100.0,
                "longitude": 100.001,
                "latitude": 20.001,
            },
            {
                "facility_id": "far-hospital",
                "service_type": "hospital",
                "candidate_destination_eligible": True,
                "within_routing_context": True,
                "name": "Far hospital",
                "node_id": "far",
                "snap_distance_m": 0.0,
                "longitude": 100.002,
                "latitude": 20,
            },
            {
                "facility_id": "pharmacy",
                "service_type": "pharmacy",
                "candidate_destination_eligible": True,
                "within_routing_context": True,
                "name": "Pharmacy",
                "node_id": "origin",
                "snap_distance_m": 0.0,
                "longitude": 100,
                "latitude": 20,
            },
        ],
        "public_origins": [
            {
                "origin_id": "official-mae-sai-municipality",
                "name": "Municipal marker",
                "node_id": "origin",
                "snap_distance_m": 25.0,
                "longitude": 100,
                "latitude": 20.0001,
                "source_url": "https://example.test/public-marker",
                "geometry_role": "official_site_marker_not_entrance",
            },
        ],
    }


def test_pin_route_and_population_route_agree_including_both_connectors():
    context = route_context()
    origin = context["public_origins"][0]
    hospitals = [
        row for row in context["osm_facilities"] if row["service_type"] == "hospital"
    ]
    pin = calculate_pin_route(context, origin, hospitals)
    population = [
        {
            **origin,
            "population_id": "population-cell",
            "subdistrict_id": "test",
            "total_population": 1,
        }
    ]
    aggregate = calculate_total_access(population, context["edges"], hospitals)
    # The farther road node wins because the near hospital has a longer connector.
    assert pin["destination_id"] == "far-hospital"
    assert pin["total_minutes"] == pytest.approx(
        aggregate["node_results"][0]["normal_access_minutes"]
    )
    assert pin["total_minutes"] == 2.3
    assert pin["distance_m"] == 225.0


def test_closing_one_parallel_edge_preserves_the_other_identity_and_cost():
    context = route_context()
    origin = context["public_origins"][0]
    hospital = [context["osm_facilities"][1]]
    result = calculate_pin_route(context, origin, hospital, closed_edge_ids=["fast"])
    assert result["edge_ids"] == ["parallel", "second"]
    assert result["total_minutes"] == 3.3
    assert result["distance_m"] == 235.0


def test_route_matrix_preserves_service_boundaries_and_source_pin_identity():
    contexts = {
        key: deepcopy(route_context()) for key in ("walking", "modelled_vehicle")
    }
    result = build_pin_comparisons(contexts)
    assert result["origins"][0]["id"] == "official-mae-sai-municipality"
    for row in result["comparisons"]:
        assert row["context_sha256"] == "a" * 64
        if row["service_type"] in {"shelter", "primary_care"}:
            assert row["baseline"]["status"] == "unavailable"
            assert row["after"]["status"] == "unavailable"
            assert row["changed_ids"] == []
        if row["service_type"] == "hospital":
            assert row["baseline"]["destination_id"] != "pharmacy"
            assert row["after"]["destination_id"] != "pharmacy"
            if row["scenario_kind"] == "close_edge":
                assert not set(row["changed_ids"]) & set(row["after"]["edge_ids"])
            else:
                assert row["baseline"]["destination_id"] in row["changed_ids"]
                assert row["after"]["destination_id"] not in row["changed_ids"]
