"""Routes must conserve travel costs and reflect explicit changes without fabrication."""

import pytest

from floodguard.evidence_routes import calculate_pin_route


@pytest.fixture
def network():
    return {
        "node_coordinates": {
            "a": [99.0, 20.0],
            "b": [99.01, 20.0],
            "c": [99.01, 20.01],
        },
        "edges": [
            {
                "edge_id": "ab",
                "from_node": "a",
                "to_node": "b",
                "normal_minutes": 2.0,
                "length_m": 100.0,
            },
            {
                "edge_id": "ac",
                "from_node": "a",
                "to_node": "c",
                "normal_minutes": 3.0,
                "length_m": 150.0,
            },
            {
                "edge_id": "cb",
                "from_node": "c",
                "to_node": "b",
                "normal_minutes": 4.0,
                "length_m": 200.0,
            },
        ],
    }


ORIGIN = {
    "node_id": "a",
    "snap_distance_m": 50.0,
    "longitude": 99.0,
    "latitude": 19.999,
}
SITE = {
    "facility_id": "hospital",
    "node_id": "b",
    "snap_distance_m": 25.0,
    "longitude": 99.01,
    "latitude": 20.001,
    "candidate_destination_eligible": True,
    "name": "Hospital",
}


def test_route_geometry_cost_and_alternative(network):
    before = calculate_pin_route(network, ORIGIN, [SITE])
    after = calculate_pin_route(network, ORIGIN, [SITE], closed_edge_ids=["ab"])
    assert before["edge_ids"] == ["ab"]
    assert before["distance_m"] == 175
    assert before["total_minutes"] == 2.9
    assert after["edge_ids"] == ["ac", "cb"]
    assert after["total_minutes"] == 7.9
    assert after["coordinates"] == [[99.0, 20.0], [99.01, 20.01], [99.01, 20.0]]
    assert after["connectors"][0][0] == [99.0, 19.999]


def test_unknown_connector_differs_from_no_destination_and_no_route(network):
    assert (
        "unknown"
        in calculate_pin_route(network, {**ORIGIN, "snap_distance_m": 251}, [SITE])[
            "reason"
        ]
    )
    assert (
        "No eligible"
        in calculate_pin_route(
            network, ORIGIN, [SITE], removed_facility_ids=["hospital"]
        )["reason"]
    )
    route = calculate_pin_route(network, ORIGIN, [SITE], closed_edge_ids=["ab", "ac"])
    assert route["total_minutes"] is None
    assert route["coordinates"] == []
    assert "graph-connected" in route["reason"]


def test_unknown_change_and_negative_time_rejected(network):
    with pytest.raises(ValueError, match="road-edge"):
        calculate_pin_route(network, ORIGIN, [SITE], closed_edge_ids=["fake"])
    network["edges"][0]["normal_minutes"] = -1
    with pytest.raises(ValueError, match="nonnegative"):
        calculate_pin_route(network, ORIGIN, [SITE])


def test_same_node_zero_network_route_keeps_connectors(network):
    result = calculate_pin_route(network, ORIGIN, [{**SITE, "node_id": "a"}])
    assert result["network_minutes"] == 0
    assert result["total_minutes"] == 0.9
    assert result["edge_ids"] == []
    assert len(result["coordinates"]) == 1
