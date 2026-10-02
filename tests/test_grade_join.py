"""Grade-join policy (D13) on an invented bridge. No real place is routed here."""

from __future__ import annotations

import pytest

from floodguard.evidence_context import _road_graph
from floodguard.evidence_scenarios import calculate_total_access
from floodguard.grade_join import (
    COINCIDENCE_TOLERANCE_M,
    GRADE_JOIN_RULE_VERSION,
    JOIN_EDGE_KIND,
    GradeJoinError,
    apply_grade_joins,
    endpoint_coincident_joins,
    join_edges,
    join_log,
)
from shapely.geometry import box


def _way(osm_id: str, coordinates: list[list[float]], **tags: str) -> dict:
    other = ",".join(f'"{key}"=>"{value}"' for key, value in tags.items() if key != "highway")
    return {
        "type": "Feature",
        "properties": {"osm_id": osm_id, "highway": tags.get("highway", "primary"), "other_tags": other or None},
        "geometry": {"type": "LineString", "coordinates": coordinates},
    }


def _bridge_context() -> dict:
    """West road, a bridge, east road in a line; a ground road passes under the bridge end without ending there."""

    roads = {"type": "FeatureCollection", "features": [
        _way("1", [[99.000, 20.0], [99.001, 20.0]]),
        _way("2", [[99.001, 20.0], [99.002, 20.0]], bridge="yes", layer="1"),
        _way("3", [[99.002, 20.0], [99.003, 20.0]]),
        # A road whose middle vertex shares the coordinate of the bridge's east end, at tunnel grade.
        _way("4", [[99.002, 19.999], [99.002, 20.0], [99.002, 20.001]], tunnel="yes", layer="-1"),
    ]}
    edges, nodes, _geojson, topology = _road_graph(roads, box(98.9, 19.9, 99.1, 20.1))
    return {
        "edges": edges,
        "node_coordinates": nodes,
        "travel_mode": "legacy_vehicle",
        "connectivity_review": topology["grade_connection_review"],
        "canonical_sha256": "c" * 64,
    }


def test_joins_link_only_nodes_that_end_a_way_at_the_same_coordinate() -> None:
    context = _bridge_context()
    review = context["connectivity_review"]
    assert review["shared_coordinate_grade_split_count"] == 2
    joins = endpoint_coincident_joins(review["review_candidates"])
    assert len(joins) == 2
    for join in joins:
        assert join["rule_version"] == GRADE_JOIN_RULE_VERSION
        assert join["coincidence_tolerance_m"] == COINCIDENCE_TOLERANCE_M == 0.0
        assert len(join["node_ids"]) == 2 and len(join["source_way_ids"]) == 2
        assert set(join["source_way_ids"]) <= {"1", "2", "3"}  # never way 4: it does not end there
        assert join["passability"] == "unknown"
    east = next(join for join in joins if join["coordinates"] == [99.002, 20.0])
    assert sorted(east["source_way_ids"]) == ["2", "3"]
    assert east["all_nodes_at_coordinate_are_endpoints"] is False
    west = next(join for join in joins if join["coordinates"] == [99.001, 20.0])
    assert west["all_nodes_at_coordinate_are_endpoints"] is True
    assert joins == sorted(joins, key=lambda join: join["join_id"])


def test_joined_edges_connect_the_bridge_without_changing_the_context() -> None:
    context = _bridge_context()
    before = [dict(edge) for edge in context["edges"]]
    edges, joins = apply_grade_joins(context)
    assert context["edges"] == before
    connectors = [edge for edge in edges if edge.get("edge_kind") == JOIN_EDGE_KIND]
    assert len(connectors) == len(joins) == 2 and len(edges) == len(before) + 2
    assert all(edge["length_m"] == 0.0 and edge["normal_minutes"] == 0.0 for edge in connectors)

    west_node = next(edge for edge in before if edge["osm_way_id"] == "1")["from_node"]
    east_node = next(edge for edge in before if edge["osm_way_id"] == "3")["to_node"]
    population = [{"population_id": "p", "subdistrict_id": "synthetic-unit", "total_population": 10.0,
                   "node_id": west_node, "snap_distance_m": 0.0}]
    site = [{"facility_id": "h", "node_id": east_node, "snap_distance_m": 0.0}]
    apart = calculate_total_access(population, before, site)["node_results"][0]
    joined = calculate_total_access(population, edges, site)["node_results"][0]
    assert apart["normal_access_minutes"] is None
    assert joined["normal_access_minutes"] is not None and joined["normal_access_minutes"] > 0


def test_a_coordinate_with_one_endpoint_node_gets_no_join() -> None:
    rows = [{
        "coordinates": [99.5, 20.5],
        "nodes": [
            {"node_id": "a", "grade": ["0", "no", "no"], "way_ids": ["10"], "endpoint_way_ids": []},
            {"node_id": "b", "grade": ["1", "yes", "no"], "way_ids": ["11"], "endpoint_way_ids": ["11"]},
        ],
    }]
    assert endpoint_coincident_joins(rows) == []


def test_three_endpoint_nodes_are_chained_from_the_lowest_node_id() -> None:
    rows = [{
        "coordinates": [99.5, 20.5],
        "nodes": [
            {"node_id": "c", "grade": ["2", "yes", "no"], "way_ids": ["12"], "endpoint_way_ids": ["12"]},
            {"node_id": "a", "grade": ["0", "no", "no"], "way_ids": ["10", "9"], "endpoint_way_ids": ["9", "10"]},
            {"node_id": "b", "grade": ["1", "yes", "no"], "way_ids": ["11"], "endpoint_way_ids": ["11"]},
        ],
    }]
    joins = endpoint_coincident_joins(rows)
    assert sorted(join["node_ids"] for join in joins) == [["a", "b"], ["a", "c"]]
    assert {tuple(join["source_way_ids"]) for join in joins} == {("10", "11"), ("10", "12")}
    edges = join_edges(joins, travel_mode="legacy_vehicle")
    assert [edge["edge_id"] for edge in edges] == [join["join_id"] for join in joins]


def test_bad_review_rows_and_unknown_nodes_are_refused() -> None:
    node = {"node_id": "a", "grade": ["0", "no", "no"], "way_ids": ["1"], "endpoint_way_ids": ["1"]}
    with pytest.raises(GradeJoinError, match="longitude"):
        endpoint_coincident_joins([{"coordinates": None, "nodes": [node, {**node, "node_id": "b"}]}])
    with pytest.raises(GradeJoinError, match="twice"):
        endpoint_coincident_joins([{"coordinates": [1.0, 2.0], "nodes": [node, node]}])
    context = _bridge_context()
    context["edges"] = context["edges"][:1]
    with pytest.raises(GradeJoinError, match="not in the road graph"):
        apply_grade_joins(context)


def test_join_log_states_the_rule_and_binds_the_context() -> None:
    context = _bridge_context()
    _edges, joins = apply_grade_joins(context)
    log = join_log(joins, context_canonical_sha256=context["canonical_sha256"])
    assert log["join_count"] == 2 and log["joins"] == joins
    assert log["coincidence_tolerance_m"] == 0.0 and log["rule_version"] == GRADE_JOIN_RULE_VERSION
    assert log["context_canonical_sha256"] == "c" * 64
    assert "middle of a way" in log["rule"] and "crossing" in log["rule"]
