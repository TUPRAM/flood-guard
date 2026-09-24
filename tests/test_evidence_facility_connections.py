"""Extra destination connectors require explicit, source-bound site geometry."""

import hashlib
from copy import deepcopy

import pytest
from shapely.geometry import box, mapping

from floodguard.evidence_catalog import canonical_bytes
from floodguard.evidence_facility_connections import apply_facility_connections


def inputs():
    geometry = mapping(box(99, 20, 99.001, 20.001))
    context = {
        "input_hashes": {"osm": "a" * 64},
        "node_coordinates": {"a": [99.0004, 20.0005], "b": [99.0006, 20.0005]},
        "edges": [{"osm_way_id": "1", "from_node": "a", "to_node": "b"}],
        "osm_facilities": [
            {
                "facility_id": "site",
                "source_geometry": geometry,
                "longitude": 99.0005,
                "latitude": 20.0005,
            }
        ],
    }
    review = {
        "osm_source_sha256": "a" * 64,
        "facilities": [
            {
                "facility_id": "site",
                "review_id": "review-1",
                "status": "osm_geometry_reviewed_scenario_only",
                "site_geometry_sha256": hashlib.sha256(
                    canonical_bytes(geometry)
                ).hexdigest(),
                "connectors": [
                    {"coordinates": context["node_coordinates"][n], "osm_way_id": "1"}
                    for n in ("a", "b")
                ],
            }
        ],
    }
    return context, review


def test_two_connectors_preserve_one_destination_and_original_topology():
    context, review = inputs()
    original = deepcopy(context)
    result = apply_facility_connections(context, review)
    assert context == original
    assert result["edges"] == context["edges"]
    assert len(result["osm_facilities"]) == 1
    assert result["osm_facilities"][0]["connector_count"] == 2


@pytest.mark.parametrize(
    "change", ["source", "polygon", "way", "ambiguous", "duplicate"]
)
def test_unjustified_connections_are_rejected(change):
    context, review = inputs()
    item = review["facilities"][0]
    if change == "source":
        review["osm_source_sha256"] = "b" * 64
    elif change == "polygon":
        item["site_geometry_sha256"] = "b" * 64
    elif change == "way":
        item["connectors"][0]["osm_way_id"] = "other"
    elif change == "ambiguous":
        context["node_coordinates"]["c"] = context["node_coordinates"]["a"]
    else:
        item["connectors"][1] = item["connectors"][0]
    with pytest.raises(ValueError):
        apply_facility_connections(context, review)
