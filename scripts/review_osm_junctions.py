"""Review bounded grade splits against original PBF node identities.

Run with the optional, pinned review runtime: uv run --with osmium==4.3.1
python scripts/review_osm_junctions.py --help. No production dependency on
pyosmium is introduced. Sources remain unchanged; the result is a review receipt,
not evidence of event-time road passability.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

from floodguard.evidence_context import (
    EvidenceContextError,
    _polygon,
    _rank_connection_review,
    _road_graph,
    _sha256,
)


def review_junctions(pbf: Path, context_dir: Path, routing: Path, limit: int) -> dict:
    """Verify original node references and coordinates for ranked transitions."""
    import osmium

    context_path = context_dir / "context_inputs.json"
    roads_path = context_dir / "osm_roads.geojson"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    roads = json.loads(roads_path.read_text(encoding="utf-8"))
    source_hash = _sha256(pbf)
    if source_hash != context["input_hashes"]["osm"]:
        raise EvidenceContextError("PBF checksum differs from reviewed context")
    edges, nodes, _, topology = _road_graph(
        roads, _polygon(json.loads(routing.read_text(encoding="utf-8")))
    )
    review = topology["grade_connection_review"]
    _rank_connection_review(review, nodes, edges, context["population"])
    candidates = [
        row
        for row in review["review_candidates"]
        if row["review_class"] == "possible_shared_endpoint_grade_transition"
    ][:limit]
    wanted = {
        way
        for row in candidates
        for node in row["nodes"]
        for way in node["endpoint_way_ids"]
    }
    references = {}

    class Ways(osmium.SimpleHandler):
        def way(self, obj):
            if str(obj.id) in wanted:
                references[str(obj.id)] = [node.ref for node in obj.nodes]

    Ways().apply_file(str(pbf))
    source_coordinates = {}
    node_ids = {refs[index] for refs in references.values() for index in (0, -1)}

    class Nodes(osmium.SimpleHandler):
        def node(self, obj):
            if obj.id in node_ids and obj.location.valid():
                source_coordinates[obj.id] = [obj.location.lon, obj.location.lat]

    Nodes().apply_file(str(pbf))
    geometries = {
        str(feature["properties"]["osm_id"]): feature["geometry"]["coordinates"]
        for feature in roads["features"]
    }
    results, accepted = [], []
    for index, candidate in enumerate(candidates, 1):
        members, errors = [], []
        coordinate = candidate["coordinates"]
        for way in sorted(
            {way for node in candidate["nodes"] for way in node["endpoint_way_ids"]}
        ):
            refs, positions = references.get(way, []), geometries[way]
            if len(refs) != len(positions):
                errors.append(
                    f"Original node count and GDAL vertex count differ for way {way}."
                )
                continue
            offsets = [
                offset
                for offset in (0, len(positions) - 1)
                if positions[offset][:2] == coordinate
            ]
            if len(offsets) != 1:
                errors.append(
                    f"Way {way} does not have one unambiguous matching endpoint."
                )
                continue
            offset = offsets[0]
            osm_node = refs[offset]
            if source_coordinates.get(osm_node) != coordinate:
                errors.append(
                    f"Original node coordinate does not match GDAL endpoint for way {way}."
                )
            members.append(
                {
                    "osm_way_id": way,
                    "vertex_index": offset,
                    "osm_node_id": str(osm_node),
                }
            )
        identities = {row["osm_node_id"] for row in members}
        verified = not errors and len(members) >= 2 and len(identities) == 1
        result = {
            "review_id": f"mae-sai-shared-node-{index:02d}",
            "pbf_sha256": source_hash,
            "evidence_method": "pyosmium_original_way_node_references_v1",
            "status": "verified_shared_osm_node_endpoints"
            if verified
            else "unresolved_no_supported_join",
            "osm_node_id": next(iter(identities)) if verified else None,
            "coordinates": coordinate,
            "members": members,
            "original_grade_variants": candidate["nodes"],
            "smaller_component_population": candidate["smaller_component_population"],
            "errors": errors,
            "event_passability": "unknown",
            "interpretation": "Source topology verifies one shared OSM endpoint. It does not establish a safe connector, usable road condition, or 2024 passability.",
        }
        results.append(result)
        if verified:
            accepted.append(result)
    return {
        "schema_version": "floodguard.osm_junction_review.v1",
        "source_hashes": {
            "pbf": source_hash,
            "context": _sha256(context_path),
            "extracted_roads": _sha256(roads_path),
            "routing_geometry": _sha256(routing),
        },
        "review_runtime": {"osmium": importlib.metadata.version("osmium")},
        "selection": "Top endpoint transitions by smaller-component modelled residential demand; outcomes do not select joins.",
        "candidate_count": review["possible_endpoint_transition_count"],
        "reviewed_count": len(results),
        "supported_join_count": len(accepted),
        "reviews": results,
        "reviewed_junctions": accepted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, required=True)
    parser.add_argument("--context-dir", type=Path, required=True)
    parser.add_argument("--routing-geometry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    result = review_junctions(
        args.pbf, args.context_dir, args.routing_geometry, args.limit
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {key: result[key] for key in ("reviewed_count", "supported_join_count")}
        )
    )


if __name__ == "__main__":
    main()
