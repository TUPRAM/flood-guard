"""One candidate must drive closures, exposure and explicit incomplete scoring."""

import pytest
from shapely.geometry import box, mapping

from floodguard.evidence_flood_scenario import candidate_flood_scenario


def collection(geometry):
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": mapping(geometry), "properties": {}}
        ],
    }


def inputs():
    context = {
        "canonical_sha256": "a" * 64,
        "node_coordinates": {"a": [99, 20], "b": [99.001, 20], "c": [99.002, 20]},
        "edges": [
            {"edge_id": "ab", "from_node": "a", "to_node": "b", "normal_minutes": 10},
            {"edge_id": "bc", "from_node": "b", "to_node": "c", "normal_minutes": 10},
        ],
        "population": [
            {
                "population_id": "p",
                "subdistrict_id": "TH570901",
                "total_population": 100,
                "node_id": "a",
                "snap_distance_m": 0,
                "longitude": 99,
                "latitude": 20,
            }
        ],
        "osm_facilities": [
            {
                "facility_id": "hospital",
                "service_type": "hospital",
                "candidate_destination_eligible": True,
                "within_routing_context": True,
                "node_id": "c",
                "snap_distance_m": 0,
            }
        ],
    }
    provenance = {
        "event_id": "mae_sai_2024",
        "official_warning": False,
        "eligible_for_validation": False,
        "source_timestamp": "2024-09-15T23:16:01Z",
    }
    return context, provenance


def test_candidate_drives_access_and_exposure_but_does_not_invent_likelihood():
    context, provenance = inputs()
    result = candidate_flood_scenario(
        context,
        collection(box(98.9999, 19.9999, 99.0001, 20.0001)),
        collection(box(98.99, 19.99, 99.01, 20.01)),
        provenance,
    )
    assert [r["edge_id"] for r in result["closed_edges"]] == ["ab"]
    assert result["candidate_affected_population"] == 100
    assert result["impact"]["newly_unreachable_population"] == 100
    assessment = result["subdistricts"][0]["assessment"]
    assert assessment["fpps_0_100"] is None
    assert assessment["missing_components"] == [
        "flood_likelihood_0_100",
        "vulnerability_context_0_100",
    ]
    assert assessment["fixed_weight_bounds"] == {
        "lower": 60,
        "upper": 100,
        "meaning": "arithmetic_bounds_not_confidence_interval",
    }
    assert [s["action_class"] for s in assessment["scenario_completions"]] == [
        "E",
        "E",
        "E",
    ]


def test_missing_observation_is_not_dry_and_empty_candidate_is_distinct():
    context, provenance = inputs()
    result = candidate_flood_scenario(
        context,
        {"type": "FeatureCollection", "features": []},
        collection(box(99.001, 19.99, 99.01, 20.01)),
        provenance,
    )
    assert result["candidate_affected_population"] == 0
    assert result["unobserved_population"] == 100
    assert (
        result["subdistricts"][0]["assessment"]["components"]["exposure_0_100"] is None
    )
    assert result["closed_edges"] == []


def test_extent_outside_observation_is_rejected():
    context, provenance = inputs()
    with pytest.raises(ValueError, match="exceeds"):
        candidate_flood_scenario(
            context,
            collection(box(99, 20, 99.1, 20.1)),
            collection(box(99, 20, 99.01, 20.01)),
            provenance,
        )


def test_candidate_preserves_hat_yai_event_identity():
    context, provenance = inputs()
    provenance["event_id"] = "hat_yai_2025"
    result = candidate_flood_scenario(
        context, collection(box(98.9999, 19.9999, 99.0001, 20.0001)),
        collection(box(98.99, 19.99, 99.01, 20.01)), provenance,
    )
    assert result["event_id"] == "hat_yai_2025"
