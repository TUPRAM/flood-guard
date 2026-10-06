"""Fixed-demand and source-object checks for lower-basin routing comparisons."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from shapely.geometry import Point, box, mapping, shape

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/compare_lower_basin_context.py"
SPEC = importlib.util.spec_from_file_location("compare_lower_basin_context", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
fixed_demand_roster = MODULE.fixed_demand_roster
hospital_duplicate_review = MODULE.hospital_duplicate_review
route_buffer = MODULE.route_buffer


def test_routing_buffer_expands_aoi_without_changing_it() -> None:
    aoi = mapping(box(100.4, 14.25, 100.52, 14.37))

    routing = shape(route_buffer(aoi, 5))

    assert routing.covers(shape(aoi))
    assert routing.area > shape(aoi).area
    assert routing.contains(Point(100.4, 14.25))


def test_fixed_demand_roster_preserves_reporting_assignment_and_rejects_drift() -> None:
    baseline = [{"population_id": "cell-a", "longitude": 100.5, "latitude": 14.3,
                 "total_population": 10.25, "subdistrict_id": "TH-1"}]
    expanded = [dict(baseline[0], subdistrict_id="unassigned", node_id="new-node")]

    roster_hash = fixed_demand_roster(baseline, expanded)

    assert len(roster_hash) == 64
    assert expanded[0]["subdistrict_id"] == "TH-1"
    expanded[0]["total_population"] = 10.5
    try:
        fixed_demand_roster(baseline, expanded)
    except ValueError as error:
        assert "changed demand cell" in str(error)
    else:
        raise AssertionError("Changed population must fail the fixed-demand check")


def test_hospital_dedup_requires_matching_identity_and_containment() -> None:
    site = {
        "facility_id": "OSM-way-1", "service_type": "hospital", "name": "Same Hospital",
        "source_geometry_type": "Polygon", "source_geometry": mapping(box(100, 14, 100.01, 14.01)),
        "source_url": "https://www.openstreetmap.org/way/1", "wikidata": None,
    }
    matching_point = {
        "facility_id": "OSM-node-2", "service_type": "hospital", "name": "same hospital",
        "source_geometry_type": "Point", "source_geometry": mapping(Point(100.005, 14.005)),
        "source_url": "https://www.openstreetmap.org/node/2", "wikidata": None,
    }
    different_point = {
        **matching_point, "facility_id": "OSM-node-3", "name": "Different Hospital",
        "source_url": "https://www.openstreetmap.org/node/3",
    }
    outside_point = {
        **matching_point, "facility_id": "OSM-node-4", "source_geometry": mapping(Point(100.02, 14.02)),
        "source_url": "https://www.openstreetmap.org/node/4",
    }
    context = {
        "input_hashes": {"osm": "a" * 64},
        "osm_facilities": [site, matching_point, different_point, outside_point],
    }

    review = hospital_duplicate_review(context)

    assert len(review["exclusions"]) == 1
    assert review["exclusions"][0]["facility_id"] == "OSM-node-2"
    assert review["exclusions"][0]["duplicate_of"] == "OSM-way-1"
