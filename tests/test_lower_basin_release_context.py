"""Fixed demand and documented OSM source-object context selection."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pyproj import Transformer
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import transform

from floodguard.lower_basin_release_context import (
    LowerBasinContextError,
    bind_fixed_demand_roster,
    review_hospital_source_duplicates,
    select_lower_basin_context,
    validate_documented_hospital_review,
)


def _selection(**changes):
    values = {
        "aoi_id": "aoi-06_chao_phraya_rangsit",
        "demand_geometry": mapping(box(100.5, 14.0, 100.55, 14.05)),
        "reporting_geometry": mapping(box(100.49, 13.99, 100.56, 14.06)),
        "aoi_sha256": "a" * 64,
        "reporting_units_sha256": "b" * 64,
    }
    values.update(changes)
    return select_lower_basin_context(**values)


def test_10km_metric_buffer_retains_raw_demand_and_reporting_shapes():
    demand = mapping(box(100.5, 14.0, 100.55, 14.05))
    reporting = mapping(box(100.49, 13.99, 100.56, 14.06))
    result = _selection(demand_geometry=demand, reporting_geometry=reporting)
    assert result["policy_version"] == "lower_basin_10km_epsg32647_v1"
    assert result["routing_buffer_m"] == 10_000
    assert result["buffer_calculation_crs"] == "EPSG:32647"
    assert result["demand_geometry"] == demand
    assert result["reporting_geometry"] == reporting
    assert result["demand_geometry"] is not demand
    assert result["reporting_geometry"] is not reporting
    assert result["builder_reporting_geometry"] is None
    assert result["event_flood_layer"] is None
    assert result["official_warning"] is False
    project = Transformer.from_crs(4326, 32647, always_xy=True).transform
    original = transform(project, shape(demand))
    routing = transform(project, shape(result["routing_geometry"]))
    expected = original.buffer(10_000)
    assert routing.area == pytest.approx(expected.area, rel=1e-8)
    assert routing.symmetric_difference(expected).area < 0.1
    assert routing.covers(original)


def test_only_lower_basin_ids_and_full_reporting_coverage_are_allowed():
    for aoi in ("aoi-05_chao_phraya_bang_ban_sena", "aoi-06_chao_phraya_rangsit"):
        assert _selection(aoi_id=aoi)["aoi_id"] == aoi
    with pytest.raises(LowerBasinContextError, match="limited to AOI-05/06"):
        _selection(aoi_id="aoi-01_mae_sai_core")
    with pytest.raises(LowerBasinContextError, match="do not cover"):
        _selection(reporting_geometry=mapping(box(101.0, 15.0, 101.1, 15.1)))
    with pytest.raises(LowerBasinContextError, match="WGS84"):
        _selection(demand_geometry=mapping(box(500_000, 1_550_000, 501_000, 1_551_000)))


def test_fixed_demand_roster_copies_reporting_ids_without_changing_routes():
    baseline = [
        {
            "population_id": "cell-1",
            "longitude": 100.5,
            "latitude": 14.0,
            "total_population": 10.25,
            "subdistrict_id": "TH-01",
            "node_id": "old-node",
        }
    ]
    expanded = deepcopy(baseline)
    expanded[0]["subdistrict_id"] = "unassigned"
    expanded[0]["node_id"] = "new-node"
    fixed, digest = bind_fixed_demand_roster(baseline, expanded)
    assert fixed[0]["subdistrict_id"] == "TH-01"
    assert fixed[0]["node_id"] == "new-node"
    assert expanded[0]["subdistrict_id"] == "unassigned"
    assert len(digest) == 64
    expanded[0]["total_population"] = 10.26
    with pytest.raises(LowerBasinContextError, match="changed demand cell"):
        bind_fixed_demand_roster(baseline, expanded)
    with pytest.raises(LowerBasinContextError, match="expanded demand roster is empty"):
        bind_fixed_demand_roster(baseline, [])


def _facility(identifier, geometry, name, *, wikidata=None):
    return {
        "facility_id": identifier,
        "service_type": "hospital",
        "source_geometry_type": geometry.geom_type,
        "source_geometry": mapping(geometry),
        "name": name,
        "wikidata": wikidata,
        "source_url": f"https://www.openstreetmap.org/{identifier}",
        "candidate_destination_eligible": True,
    }


def test_contained_name_or_wikidata_dedup_only_with_exact_review():
    site = _facility("way-1", box(0, 0, 2, 2), "District Hospital")
    same_name = _facility("node-1", Point(1, 1), " district   hospital ")
    same_id = _facility("node-2", Point(1.5, 1.5), "Different", wikidata="Q123")
    site["wikidata"] = "Q123"
    outside = _facility("node-3", Point(3, 3), "District Hospital")
    unnamed = _facility("node-4", Point(1, 1.8), "Unnamed OSM candidate")
    context = {
        "input_hashes": {"osm": "a" * 64},
        "osm_facilities": [site, same_name, same_id, outside, unnamed],
    }
    review = review_hospital_source_duplicates(context)
    assert {row["facility_id"] for row in review["exclusions"]} == {"node-1", "node-2"}
    assert {row["reason"] for row in review["exclusions"]} == {
        "same_name_and_containment",
        "shared_wikidata_and_containment",
    }
    assert validate_documented_hospital_review(context, review) == {"node-1", "node-2"}
    changed = deepcopy(review)
    changed["osm_sha256"] = "b" * 64
    with pytest.raises(LowerBasinContextError, match="review changed"):
        validate_documented_hospital_review(context, changed)


def test_multiple_containing_sites_are_ambiguous_not_excluded():
    context = {
        "input_hashes": {"osm": "a" * 64},
        "osm_facilities": [
            _facility("way-1", box(0, 0, 2, 2), "Clinic"),
            _facility("way-2", box(0.5, 0.5, 1.5, 1.5), "Clinic"),
            _facility("node-1", Point(1, 1), "Clinic"),
        ],
    }
    review = review_hospital_source_duplicates(context)
    assert review["exclusions"] == []
    assert review["ambiguous"] == [
        {"facility_id": "node-1", "possible_parents": ["way-1", "way-2"]}
    ]


def test_duplicate_ids_fail_instead_of_silently_dropping_one():
    point = _facility("node-1", Point(1, 1), "Clinic")
    context = {
        "input_hashes": {"osm": "a" * 64},
        "osm_facilities": [point, deepcopy(point)],
    }
    with pytest.raises(LowerBasinContextError, match="duplicated"):
        review_hospital_source_duplicates(context)
