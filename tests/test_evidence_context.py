"""Synthetic spatial fixtures for the checksum-bound context builder."""

import hashlib
import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from floodguard import evidence_context as context


def road(osm_id, coordinates, **tags):
    return {
        "type": "Feature",
        "properties": {"osm_id": osm_id, "highway": "residential", **tags},
        "geometry": {"type": "LineString", "coordinates": coordinates},
    }


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def test_osm_service_roles_and_polygon_identity_are_not_interchangeable():
    site = {
        "type": "Feature",
        "properties": {
            "osm_way_id": "10",
            "amenity": "hospital",
            "name": "Test hospital",
        },
        "geometry": mapping(box(100, 15, 100.001, 15.001)),
    }
    relation = {
        "type": "Feature",
        "properties": {"osm_id": "20", "amenity": "clinic"},
        "geometry": mapping(box(100.002, 15, 100.003, 15.001)),
    }
    pharmacy = {
        "type": "Feature",
        "properties": {"osm_id": "30", "other_tags": '"amenity"=>"pharmacy"'},
        "geometry": {"type": "Point", "coordinates": [100, 15]},
    }
    rows = context._osm_facilities(collection(site, relation, pharmacy, site))
    assert (
        len(rows) == 3
    )  # Only duplicate representations of the same OSM object deduplicate.
    by_id = {row["facility_id"]: row for row in rows}
    assert by_id["OSM-way-10"]["service_type"] == "hospital"
    assert by_id["OSM-relation-20"]["service_type"] == "primary_care"
    assert by_id["OSM-node-30"]["service_type"] == "pharmacy"
    assert by_id["OSM-way-10"]["source_url"] == "https://www.openstreetmap.org/way/10"
    assert (
        by_id["OSM-way-10"]["geometry_role"]
        == "derived_site_interior_representative_not_entrance"
    )
    assert all(
        row["capacity"] is None and row["event_available_capacity"] is None
        for row in rows
    )
    assert all(row["event_operation_status"] == "unknown" for row in rows)


def test_osm_unique_boundary_entrance_is_explicit_and_duplicate_sites_are_reviewed():
    hospital = {
        "type": "Feature",
        "properties": {
            "osm_way_id": "10",
            "amenity": "hospital",
            "name": "Same hospital",
        },
        "geometry": mapping(box(100, 15, 100.001, 15.001)),
    }
    entrance = {
        "type": "Feature",
        "properties": {"osm_id": "11", "other_tags": '"entrance"=>"main"'},
        "geometry": {"type": "Point", "coordinates": [100, 15.0005]},
    }
    point = {
        "type": "Feature",
        "properties": {
            "osm_id": "12",
            "other_tags": '"amenity"=>"hospital"',
            "name": "Same hospital",
        },
        "geometry": {"type": "Point", "coordinates": [100.0005, 15.0005]},
    }
    rows = context._osm_facilities(collection(hospital, entrance, point))
    site = next(row for row in rows if row["facility_id"] == "OSM-way-10")
    assert site["geometry"]["coordinates"] == (100.0, 15.0005)
    assert (
        site["geometry_role"]
        == "osm_tagged_site_boundary_entrance_not_independently_verified"
    )
    assert site["possible_duplicate_source_ids"] == ["OSM-node-12"]
    assert len(rows) == 2  # Distinct identities are never silently merged.


def test_public_origins_are_named_scoped_map_records_not_destinations():
    features = collection(
        *[
            {
                "type": "Feature",
                "properties": {
                    "osm_id": str(index),
                    "name": name,
                    "other_tags": f'"amenity"=>"{amenity}"',
                },
                "geometry": {"type": "Point", "coordinates": coordinate},
            }
            for index, (name, amenity, coordinate) in enumerate(
                [
                    ("Market", "marketplace", [100, 15]),
                    ("School", "school", [100, 15]),
                    ("Clinic", "clinic", [100, 15]),
                    ("Outside", "school", [101, 15]),
                    (None, "police", [100, 15]),
                ],
                1,
            )
        ]
    )
    scope = box(99.99, 14.99, 100.01, 15.01)
    rows = context._osm_public_origins(
        features, scope, scope, context._NodeIndex({"node": [100, 15]})
    )
    assert {row["name"] for row in rows} == {"Market", "School"}
    assert all(row["node_id"] == "node" and "capacity" not in row for row in rows)
    assert all(
        "facility_id" not in row and row["origin_id"].startswith("OSM-node-")
        for row in rows
    )


def test_walking_mode_uses_paths_and_honours_foot_access():
    lines = collection(
        road("path", [[100, 15], [100.001, 15]], highway="footway"),
        road("prohibited", [[100.001, 15], [100.002, 15]], foot="no"),
        road("motorway", [[100.002, 15], [100.003, 15]], highway="motorway"),
        road(
            "motor_forbidden_foot_allowed",
            [[100.003, 15], [100.004, 15]],
            motor_vehicle="no",
            foot="yes",
        ),
    )
    edges, _, _, _ = context._road_graph(
        lines, box(99, 14, 101, 16), travel_mode="walking"
    )
    assert {row["osm_way_id"] for row in edges} == {
        "path",
        "motor_forbidden_foot_allowed",
    }
    assert all(
        row["normal_minutes"] == pytest.approx(row["length_m"] / 1000 / 5 * 60)
        for row in edges
    )


def test_reporting_scope_rejects_cross_border_segments_and_connectors():
    # A narrow excluded strip cannot be crossed by road or connector proximity.
    scope = box(99.99, 14.99, 100, 15.01).union(box(100.0001, 14.99, 100.01, 15.01))
    roads = collection(road("cross", [[99.9999, 15], [100.0002, 15]]))
    assert context._road_graph(roads, scope)[0] == []
    index = context._NodeIndex({"across": [100.0002, 15]}, allowed_geometry=scope)
    assert index.snap(99.9999, 15, 100)[0] is None
    index = context._NodeIndex(
        {"across": [100.0002, 15], "same_side": [99.9994, 15]}, allowed_geometry=scope
    )
    assert index.snap(99.9999, 15, 100)[0] == "same_side"


def test_original_shared_osm_endpoint_receipt_connects_but_coordinate_alone_does_not():
    lines = collection(
        road("1", [[99.999, 15], [100, 15]]),
        road("2", [[100, 15], [100.001, 15]], bridge="yes", layer="1"),
    )
    receipt = {
        "status": "verified_shared_osm_node_endpoints",
        "evidence_method": "pyosmium_original_way_node_references_v1",
        "osm_node_id": "123",
        "coordinates": [100.0, 15.0],
        "members": [
            {"osm_way_id": "1", "vertex_index": 1, "osm_node_id": "123"},
            {"osm_way_id": "2", "vertex_index": 0, "osm_node_id": "123"},
        ],
    }
    assert (
        context._road_graph(lines, box(99, 14, 101, 16))[3]["connected_components"] == 2
    )
    edges, nodes, geojson, qc = context._road_graph(
        lines, box(99, 14, 101, 16), reviewed_junctions=[receipt]
    )
    assert qc["connected_components"] == 1
    assert "osm-original-node-123" in nodes
    assert edges[0]["to_node"] == edges[1]["from_node"]
    assert geojson["features"][0]["properties"]["to_node"] == edges[0]["to_node"]
    bad = {
        **receipt,
        "members": [
            receipt["members"][0],
            {**receipt["members"][1], "osm_node_id": "456"},
        ],
    }
    with pytest.raises(context.EvidenceContextError, match="share one"):
        context._road_graph(lines, box(99, 14, 101, 16), reviewed_junctions=[bad])


def test_reviewed_grade_join_never_accepts_an_interior_crossing():
    lines = collection(
        road("1", [[99.999, 15], [100, 15], [100.001, 15]]),
        road("2", [[100, 15], [100, 15.001]], bridge="yes"),
    )
    receipt = {
        "status": "verified_shared_osm_node_endpoints",
        "evidence_method": "pyosmium_original_way_node_references_v1",
        "osm_node_id": "123",
        "coordinates": [100.0, 15.0],
        "members": [
            {"osm_way_id": "1", "vertex_index": 1, "osm_node_id": "123"},
            {"osm_way_id": "2", "vertex_index": 0, "osm_node_id": "123"},
        ],
    }
    with pytest.raises(context.EvidenceContextError, match="original way endpoint"):
        context._road_graph(lines, box(99, 14, 101, 16), reviewed_junctions=[receipt])


def test_crossing_geometry_does_not_create_a_junction():
    geometry = collection(
        road("horizontal", [[99.999, 15], [100.001, 15]]),
        road("vertical", [[100, 14.999], [100, 15.001]]),
    )
    edges, nodes, _, coverage = context._road_graph(
        geometry, box(99.99, 14.99, 100.01, 15.01)
    )
    assert len(edges) == 2
    assert len(nodes) == 4
    assert coverage["connected_components"] == 2


def test_shared_vertex_connects_only_compatible_grade():
    same = collection(
        road("a", [[99.999, 15], [100, 15]]), road("b", [[100, 15], [100.001, 15]])
    )
    edges, nodes, _, coverage = context._road_graph(
        same, box(99.99, 14.99, 100.01, 15.01)
    )
    assert len(nodes) == 3
    assert coverage["connected_components"] == 1
    separate = collection(
        same["features"][0],
        road(
            "b", [[100, 15], [100.001, 15]], other_tags='"bridge"=>"yes","layer"=>"1"'
        ),
    )
    _, nodes, _, coverage = context._road_graph(
        separate, box(99.99, 14.99, 100.01, 15.01)
    )
    assert len(nodes) == 4
    assert coverage["connected_components"] == 2
    assert edges[0]["length_m"] > 100


def test_no_boundary_clipping_invented_nodes_and_no_private_roads():
    roads = collection(
        road("boundary", [[99.9, 15], [100, 15]]),
        road("private", [[100, 15], [100.001, 15]], other_tags='"access"=>"private"'),
    )
    edges, _, _, coverage = context._road_graph(
        roads, box(99.999, 14.99, 100.01, 15.01)
    )
    assert edges == []
    assert coverage["segments_omitted_at_routing_boundary_or_degenerate"] == 1


def test_projection_snaps_have_explicit_limits_and_do_not_connect_nodes():
    index = context._NodeIndex({"node": [100, 15]})
    assert index.snap(100, 15, 100) == ("node", 0)
    nearby = index.snap(100.0005, 15, 100)
    assert nearby[0] == "node" and 50 < nearby[1] < 60
    far = index.snap(100.002, 15, 100)
    assert far[0] is None and far[1] > 200
    assert context._NodeIndex({}).snap(100, 15, 100) == (None, None)


def test_facility_source_identity_and_out_of_context_status():
    index = context._NodeIndex({"node": [100, 15]})
    rows = context._snap_facilities(
        [
            {
                "facility_id": "official",
                "longitude": 100,
                "latitude": 15,
                "capacity": None,
            },
            {
                "facility_id": "outside",
                "geometry": {"type": "Point", "coordinates": [101, 15]},
            },
        ],
        box(99.99, 14.99, 100.01, 15.01),
        index,
    )
    assert rows[0]["node_id"] == "node"
    assert rows[0]["identity_reconciled"] is False
    assert rows[1]["node_id"] is None
    assert rows[1]["within_routing_context"] is False
    with pytest.raises(context.EvidenceContextError, match="unique"):
        context._snap_facilities([rows[0], rows[0]], box(99, 14, 101, 16), index)


@pytest.fixture
def fixture_sources(tmp_path, monkeypatch):
    raster = tmp_path / "worldpop.tif"
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(100, 15.002, 0.001, 0.001),
        nodata=-9999,
    ) as dataset:
        dataset.write(np.array([[1.5, 2.5], [0, -9999]], dtype="float32"), 1)
    pbf = tmp_path / "fixture.osm.pbf"
    pbf.write_bytes(b"invented fixture, not a real OSM PBF")
    paths = {"osm": pbf, "worldpop": raster}
    metadata = {
        key: {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_name": "Synthetic fixture",
        }
        for key, path in paths.items()
    }
    roads = collection(road("1", [[100.0005, 15.0015], [100.0015, 15.0015]]))
    points = collection(
        {
            "type": "Feature",
            "properties": {"osm_id": "9", "other_tags": '"amenity"=>"shelter"'},
            "geometry": {"type": "Point", "coordinates": [100.0015, 15.0015]},
        }
    )
    monkeypatch.setattr(context, "_load_sources", lambda root: (paths, metadata))
    monkeypatch.setattr(context, "_extract_osm", lambda *args: (roads, points))
    return paths, metadata


def test_full_builder_preserves_population_mass_and_source_separation(
    tmp_path, fixture_sources
):
    aoi = mapping(box(100, 15, 100.002, 15.002))
    result = context.build_context_inputs(
        tmp_path,
        aoi,
        aoi,
        [
            {
                "facility_id": "official",
                "lon": 100.0005,
                "lat": 15.0015,
                "capacity": 100,
                "identity_reconciled": True,
                "facility_type": "shelter_candidate",
            }
        ],
        tmp_path / "derived",
    )
    assert sum(row["total_population"] for row in result["population"]) == 4
    assert result["coverage"]["missing_or_invalid_population_cells"] == 1
    assert result["coverage"]["valid_population_cells_including_zero"] == 3
    assert result["coverage"]["population_snap_coverage_fraction"] == 1
    assert result["facilities"][0]["facility_id"] == "official"
    assert result["osm_facilities"][0]["facility_id"] == "OSM-node-9"
    assert result["osm_facilities"][0]["capacity"] is None
    assert result["osm_facilities"][0]["facility_type"] == "shelter_context"
    assert result["osm_facilities"][0]["candidate_destination_eligible"] is False
    assert result["analysis_crs"] == "EPSG:32647"
    later = {**result, "generated_at": "2099-01-01T00:00:00Z"}
    assert context._context_content_hash(later) == result["canonical_sha256"]
    changed = {
        **later,
        "coverage": {**later["coverage"], "modelled_population_2020": 99},
    }
    assert context._context_content_hash(changed) != result["canonical_sha256"]
    assert (tmp_path / "derived" / "context_inputs.json").is_file()
    assert (
        json.loads((tmp_path / "derived" / "context_inputs.json").read_text())[
            "canonical_sha256"
        ]
        == result["canonical_sha256"]
    )
    scenario = context.build_context_scenarios(
        result, "test", facility_source="supplied"
    )
    assert len(scenario["access_scenarios"]) == 4
    assert [item["scenario_id"] for item in scenario["capacity_scenarios"]] == [
        "assumed_50_per_candidate",
        "assumed_100_per_candidate",
        "assumed_200_per_candidate",
        "planned_capacity_25pct",
        "planned_capacity_50pct",
        "planned_capacity_100pct",
    ]
    osm = context.build_context_scenarios(result, "test", facility_source="osm")
    assert len(osm["capacity_scenarios"]) == 3
    assert osm["hypothetical_capacity_site"]["synthetic"] is True
    assert (
        osm["access_scenarios"]["baseline"]["totals"][
            "people_already_without_30_min_access"
        ]
        == 4
    )
    assert (
        osm["planned_capacity_status"]
        == "unavailable_no_reconciled_numeric_planned_capacity"
    )
    assert osm["assessment"]["fpps_0_100"] is None


def test_checksum_failure_and_insufficient_routing_context_block(
    tmp_path, fixture_sources
):
    paths, _metadata = fixture_sources
    aoi = mapping(box(100, 15, 100.002, 15.002))
    with pytest.raises(context.EvidenceContextError, match="contain"):
        context.build_context_inputs(
            tmp_path, aoi, mapping(box(100, 15, 100.001, 15.001)), [], tmp_path / "bad"
        )
    paths["osm"].write_bytes(b"changed source")
    with pytest.raises(context.EvidenceContextError, match="checksum"):
        context.build_context_inputs(tmp_path, aoi, aoi, [], tmp_path / "bad")


def test_reporting_scope_conserves_original_demand_and_retains_origin_exclusions(
    tmp_path, fixture_sources
):
    aoi = mapping(box(100, 15, 100.002, 15.002))
    result = context.build_context_inputs(
        tmp_path,
        aoi,
        aoi,
        [],
        tmp_path / "scoped",
        reporting_geometry=mapping(box(100, 15, 100.001, 15.002)),
        public_origin_records=[
            {
                "facility_id": "public-map-marker",
                "name": "Municipal public marker",
                "longitude": 100.0005,
                "latitude": 15.0015,
                "geometry_role": "official_site_marker_not_entrance",
                "source_url": "https://example.test/municipality",
            },
            {
                "facility_id": "out-of-scope-origin",
                "longitude": 100.0015,
                "latitude": 15.0015,
            },
        ],
    )
    assert result["coverage"]["modelled_population_in_original_aoi"] == 4
    assert result["coverage"]["modelled_population_2020"] == 1.5
    assert result["coverage"]["population_excluded_outside_reporting_scope"] == 2.5
    assert len(result["population_excluded_outside_reporting_scope"]) == 1
    origins = {row["origin_id"]: row for row in result["public_origins"]}
    assert (
        origins["public-map-marker"]["geometry_role"]
        == "official_site_marker_not_entrance"
    )
    assert origins["out-of-scope-origin"]["within_demand_scope"] is False
    assert origins["out-of-scope-origin"]["node_id"] is None


def test_reviewed_junction_source_hash_must_match_inputs(tmp_path, fixture_sources):
    aoi = mapping(box(100, 15, 100.002, 15.002))
    with pytest.raises(context.EvidenceContextError, match="source hash"):
        context.build_context_inputs(
            tmp_path,
            aoi,
            aoi,
            [],
            tmp_path / "bad-junction",
            reviewed_junctions=[{"pbf_sha256": "0" * 64}],
        )


def test_healthcare_is_not_shelter_capacity_and_no_sites_remain_explicit():
    data = {
        "population": [],
        "edges": [],
        "facilities": [],
        "osm_facilities": [],
        "assumptions": [],
    }
    result = context.build_context_scenarios(data, "empty")
    assert result["capacity_status"] == "unavailable_no_candidate_shelters"
    assert result["access_scenarios"]["close_edge"]["status"] == "unavailable"
    with pytest.raises(context.EvidenceContextError, match="facility_source"):
        context.build_context_scenarios(data, "empty", facility_source="mixed")


def test_capacity_fallback_is_hypothetical_and_never_counts_healthcare_beds():
    data = {
        "population": [
            {
                "population_id": "p",
                "node_id": "a",
                "snap_distance_m": 0,
                "subdistrict_id": "area",
                "total_population": 250,
            }
        ],
        "edges": [
            {"edge_id": "ab", "from_node": "a", "to_node": "b", "normal_minutes": 2}
        ],
        "facilities": [],
        "osm_facilities": [
            {
                "facility_id": "hospital",
                "node_id": "b",
                "snap_distance_m": 0,
                "facility_type": "healthcare",
                "capacity": 1000,
            }
        ],
        "node_coordinates": {"a": [100, 15]},
        "assumptions": [],
    }
    result = context.build_context_scenarios(data, "area", facility_source="osm")
    assert result["hypothetical_capacity_site"]["synthetic"] is True
    assert result["hypothetical_capacity_site"]["coordinates"] == [100, 15]
    assert [row["served_population"] for row in result["capacity_scenarios"]] == [
        25,
        25,
        25,
    ]
    assert all(
        row["facility_results"][0]["facility_id"] == "scenario-temporary-shelter"
        for row in result["capacity_scenarios"]
    )
    assert result["planned_capacity_status"].startswith("unavailable")
    assert (
        result["scenario_assessments"]["baseline"]["components"]["access_gap_0_100"]
        == 0
    )
    assert (
        result["scenario_assessments"]["close_edge"]["components"]["access_gap_0_100"]
        == 100
    )
    for assessment in result["scenario_assessments"].values():
        assert assessment["fpps_0_100"] is None
        assert {row["action_class"] for row in assessment["scenario_completions"]} == {
            "E"
        }
    assert all(value is None for value in result["assessment"]["components"].values())


def test_access_score_transform_excludes_missing_coverage_and_preserves_real_zero():
    result = {
        "totals": {
            "total_population": 100,
            "unconnected_population": 20,
            "people_already_without_30_min_access": 50,
            "people_losing_30_min_access": 10,
            "people_gaining_30_min_access": 20,
        }
    }
    assessment = context._access_assessment(result, "area", [])
    assert assessment["components"]["access_gap_0_100"] == 25
    assert assessment["component_derivation"]["included_population"] == 80
    assert assessment["component_derivation"]["scenario_inaccessible_population"] == 20
    result["totals"]["unconnected_population"] = 100
    assert (
        context._access_assessment(result, "area", [])["assessment_status"]
        == "unavailable"
    )
    assert (
        context._access_assessment({}, "area", [])["assessment_status"] == "unavailable"
    )


def test_unreviewed_duplicate_shelter_rows_never_multiply_assumed_capacity():
    data = {
        "population": [
            {
                "population_id": "p",
                "node_id": "a",
                "snap_distance_m": 0,
                "subdistrict_id": "area",
                "total_population": 500,
            }
        ],
        "edges": [
            {"edge_id": "ab", "from_node": "a", "to_node": "b", "normal_minutes": 2}
        ],
        "facilities": [
            {
                "facility_id": key,
                "node_id": "b",
                "snap_distance_m": 0,
                "facility_type": "shelter_candidate",
                "capacity": 100,
                "identity_reconciled": False,
            }
            for key in ("source-row-1", "source-row-2")
        ],
        "osm_facilities": [],
        "node_coordinates": {"a": [100, 15]},
        "assumptions": [],
    }
    result = context.build_context_scenarios(data, "area")
    assert result["hypothetical_capacity_site"]["synthetic"] is True
    assert [row["served_population"] for row in result["capacity_scenarios"]] == [
        50,
        50,
        50,
    ]
    assert len(result["capacity_scenarios"]) == 3
    assert all(
        len(row["facility_results"]) == 1 for row in result["capacity_scenarios"]
    )


def test_grade_endpoint_diagnostics_do_not_invent_connections():
    roads = collection(
        road("approach", [[100, 15], [100.001, 15]]),
        road(
            "bridge",
            [[100.001, 15], [100.002, 15]],
            other_tags='"bridge"=>"yes","layer"=>"1"',
        ),
        road("crossing", [[100.0015, 14.999], [100.0015, 15.001]]),
    )
    _, _, _, topology = context._road_graph(roads, box(99.99, 14.99, 100.01, 15.01))
    review = topology["grade_connection_review"]
    assert topology["connected_components"] == 3
    assert review["possible_endpoint_transition_count"] == 1
    assert review["connections_added"] == 0
    assert review["review_candidates"][0]["distinct_components"] == 2
    assert review["review_candidates"][0]["automatic_connection"] is False
    assert (
        review
        == context._road_graph(
            collection(*roads["features"][::-1]), box(99.99, 14.99, 100.01, 15.01)
        )[3]["grade_connection_review"]
    )


def test_context_capacity_participation_and_compact_pairs_are_explicit():
    data = {
        "population": [
            {
                "population_id": "p",
                "node_id": "a",
                "snap_distance_m": 0,
                "subdistrict_id": "area",
                "total_population": 1000,
            }
        ],
        "edges": [
            {"edge_id": "ab", "from_node": "a", "to_node": "b", "normal_minutes": 2}
        ],
        "facilities": [],
        "osm_facilities": [],
        "node_coordinates": {"a": [100, 15]},
        "assumptions": [],
    }
    result = context.build_context_scenarios(data, "area")
    assert result["capacity_demand_assumptions"]["actual_evacuation_demand"] is None
    assert result["capacity_demand_assumptions"]["scenario_demand_population"] == 100
    assert [
        row["demand_assumptions"]["participation_fraction"]
        for row in result["capacity_participation_sensitivity"]
    ] == [0.05, 0.10, 0.25]
    assert [
        row["served_population"] for row in result["capacity_participation_sensitivity"]
    ] == [50, 100, 100]
    assert all(
        "baseline_reachable_pairs" not in row and "scenario_reachable_pairs" not in row
        for row in result["access_scenarios"].values()
    )
    assert result["access_scenarios"]["baseline"]["totals"]["total_population"] == 1000
