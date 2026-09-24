"""Apply explicit, source-bound site connector reviews without changing road topology."""

from __future__ import annotations

import hashlib
from copy import deepcopy

from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform

from .evidence_catalog import canonical_bytes


def apply_facility_connections(context: dict, review: dict) -> dict:
    """Check reviewed OSM nodes, radius and site containment before adding snaps.

    A geometry-reviewed connector remains a scenario assumption, not an entrance
    survey or confirmation of historical operation. No road edges are added.
    """
    if review["osm_source_sha256"] != context["input_hashes"]["osm"]:
        raise ValueError("Facility connection review uses a different OSM snapshot")
    output = deepcopy(context)
    by_id = {r["facility_id"]: r for r in output["osm_facilities"]}
    project = Transformer.from_crs(4326, 32647, always_xy=True).transform
    seen = set()
    for item in review["facilities"]:
        key = item["facility_id"]
        if key in seen or key not in by_id:
            raise ValueError("Unknown or duplicate reviewed facility")
        seen.add(key)
        site = by_id[key]
        if item["status"] != "osm_geometry_reviewed_scenario_only":
            raise ValueError("Unsupported facility review status")
        polygon = shape(site["source_geometry"])
        if (
            hashlib.sha256(canonical_bytes(site["source_geometry"])).hexdigest()
            != item["site_geometry_sha256"]
        ):
            raise ValueError("Reviewed site geometry changed")
        point = Point(site["longitude"], site["latitude"])
        connections = []
        for record in item["connectors"]:
            coordinate = record["coordinates"]
            nodes = [
                n for n, xy in context["node_coordinates"].items() if xy == coordinate
            ]
            if len(nodes) != 1:
                raise ValueError(
                    "Reviewed OSM coordinate is missing or grade-ambiguous"
                )
            node = nodes[0]
            if not any(
                e.get("osm_way_id") == record["osm_way_id"]
                and node in (e["from_node"], e["to_node"])
                for e in context["edges"]
            ):
                raise ValueError("Reviewed connector is not on its documented OSM way")
            line = LineString([point.coords[0], coordinate])
            distance = transform(project, line).length
            if distance > 100 or not polygon.covers(line):
                raise ValueError(
                    "Reviewed connector exceeds 100 m or leaves the site polygon"
                )
            connections.append({"node_id": node, "snap_distance_m": distance})
        if not 1 <= len(connections) <= 2 or len(
            {r["node_id"] for r in connections}
        ) != len(connections):
            raise ValueError(
                "Review must specify one or two distinct checked connectors"
            )
        site["connectors"] = sorted(connections, key=lambda r: r["node_id"])
        site["connector_review_id"] = item["review_id"]
        site["connector_count"] = len(connections)
        site["connector_walkability"] = (
            "site_geometry_checked_walkability_and_entrances_unverified"
        )
    output["input_hashes"]["facility_connection_review"] = hashlib.sha256(
        canonical_bytes(review)
    ).hexdigest()
    output["facility_connection_review"] = review
    output["canonical_sha256"] = hashlib.sha256(
        canonical_bytes(
            {
                k: v
                for k, v in output.items()
                if k not in ("canonical_sha256", "generated_at")
            }
        )
    ).hexdigest()
    return output
