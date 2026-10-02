"""Grade-join policy for the planning context (decision D13, protocol v1b).

``build_context_inputs`` keeps road vertices at the same coordinate apart when
their grade tags differ (layer, bridge, tunnel), so a bridge is cut off from
its approach roads unless a reviewed junction joins them. D13 lets the planning
overlay join such vertices under one narrow rule, and requires every join to be
logged:

* a join is made only where two graph nodes share the same coordinate and each
  of them is the end of at least one OSM way (an endpoint, never a vertex in
  the middle of a way, and never a geometric crossing);
* the coincidence tolerance is 0 m: the coordinates must be identical;
* each join is logged with the two node IDs, the two source way IDs, the
  coordinate and the rule version.

The join is a zero-length, zero-minute connector edge marked
``edge_kind = "grade_join"``. Nothing in the context is edited in place, the
finals contract is unchanged, and the finals rule that proximity never creates
a join still holds on the finals path. A join shows that two ways share an OSM
end point; it does not show that the transition can be driven.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from typing import Any

GRADE_JOIN_RULE_VERSION = "grade_join_endpoint_coincident_v1"
COINCIDENCE_TOLERANCE_M = 0.0
JOIN_EDGE_KIND = "grade_join"


class GradeJoinError(ValueError):
    """Raised when a connectivity review cannot support the join rule."""


def endpoint_coincident_joins(review_candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Derive the joins that D13 allows from a context's grade-split review.

    Args:
        review_candidates: ``connectivity_review["review_candidates"]`` of a
            context built by ``build_context_inputs``: one row per coordinate
            that holds two or more graph nodes of different grade, each node
            with its ``way_ids`` and ``endpoint_way_ids``.

    Returns:
        The join log, sorted by ``join_id``. At a coordinate with ``k`` nodes
        that are way endpoints, ``k - 1`` joins link the first node (lowest
        node ID) to each of the others. Nodes that are not the end of any way
        are never joined.

    Raises:
        GradeJoinError: for a row without coordinates or with repeated nodes.
    """

    joins: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    for row in review_candidates:
        coordinates = row.get("coordinates")
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 2:
            raise GradeJoinError("a grade-split row needs a longitude and a latitude")
        nodes = sorted(row.get("nodes", []), key=lambda node: node["node_id"])
        identifiers = [node["node_id"] for node in nodes]
        if len(set(identifiers)) != len(identifiers) or seen_nodes & set(identifiers):
            raise GradeJoinError("a graph node appears twice in the grade-split review")
        seen_nodes.update(identifiers)
        endpoints = [node for node in nodes if node.get("endpoint_way_ids")]
        if len(endpoints) < 2:
            continue
        first = endpoints[0]
        for other in endpoints[1:]:
            node_ids = [first["node_id"], other["node_id"]]
            digest = hashlib.sha256(json.dumps(node_ids, separators=(",", ":")).encode("ascii")).hexdigest()[:16]
            joins.append({
                "join_id": f"grade-join-{digest}",
                "rule_version": GRADE_JOIN_RULE_VERSION,
                "coincidence_tolerance_m": COINCIDENCE_TOLERANCE_M,
                "coordinates": [float(coordinates[0]), float(coordinates[1])],
                "node_ids": node_ids,
                "grades": [list(first["grade"]), list(other["grade"])],
                "source_way_ids": [sorted(first["endpoint_way_ids"])[0], sorted(other["endpoint_way_ids"])[0]],
                "endpoint_way_ids": [sorted(first["endpoint_way_ids"]), sorted(other["endpoint_way_ids"])],
                "all_nodes_at_coordinate_are_endpoints": len(endpoints) == len(nodes),
                "passability": "unknown",
            })
    joins.sort(key=lambda join: join["join_id"])
    if len({join["join_id"] for join in joins}) != len(joins):
        raise GradeJoinError("join IDs must be unique")
    return joins


def join_edges(joins: Sequence[Mapping[str, Any]], *, travel_mode: str) -> list[dict[str, Any]]:
    """Return one zero-length connector edge per join."""

    return [
        {
            "edge_id": join["join_id"],
            "from_node": join["node_ids"][0],
            "to_node": join["node_ids"][1],
            "length_m": 0.0,
            "road_class": "local",
            "normal_minutes": 0.0,
            "osm_way_id": None,
            "bridge": "no",
            "layer": "0",
            "tunnel": "no",
            "travel_mode": travel_mode,
            "edge_kind": JOIN_EDGE_KIND,
            "grade_join_rule_version": GRADE_JOIN_RULE_VERSION,
        }
        for join in joins
    ]


def apply_grade_joins(context: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the context's edges plus the join connectors, and the join log.

    The context is not changed. Every join must link two nodes of the graph.

    Raises:
        GradeJoinError: when a join names a node that no edge uses, or a join
            ID collides with an edge ID.
    """

    edges = [dict(edge) for edge in context["edges"]]
    joins = endpoint_coincident_joins(context["connectivity_review"]["review_candidates"])
    graph_nodes = {edge["from_node"] for edge in edges} | {edge["to_node"] for edge in edges}
    edge_ids = {edge["edge_id"] for edge in edges}
    for join in joins:
        if not set(join["node_ids"]) <= graph_nodes:
            raise GradeJoinError("a join names a node that is not in the road graph")
        if join["join_id"] in edge_ids:
            raise GradeJoinError("a join ID collides with a road edge ID")
    return [*edges, *join_edges(joins, travel_mode=str(context.get("travel_mode", "")))], joins


def join_log(joins: Sequence[Mapping[str, Any]], *, context_canonical_sha256: str) -> dict[str, Any]:
    """Wrap the joins in the log document that protocol v1b records by SHA-256."""

    return {
        "schema_version": "floodguard.grade_join_log.v1",
        "rule_version": GRADE_JOIN_RULE_VERSION,
        "coincidence_tolerance_m": COINCIDENCE_TOLERANCE_M,
        "rule": "Join two graph nodes only when they share an identical coordinate and each is the end of at least "
                "one OSM way. No join at a vertex in the middle of a way and none at a geometric crossing.",
        "context_canonical_sha256": context_canonical_sha256,
        "join_count": len(joins),
        "joins": list(joins),
    }
