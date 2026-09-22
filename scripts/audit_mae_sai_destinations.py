"""Audit the existing national OSM snapshot beyond the rectangular demand AOI."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import networkx as nx
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

from floodguard.evidence_catalog import canonical_bytes, sha256_file
from floodguard.evidence_context import _extract_osm, _osm_facilities
from floodguard.evidence_interventions import select_interventions
from floodguard.evidence_scenarios import calculate_total_access


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, required=True)
    parser.add_argument("--finals-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output_dir.resolve().is_relative_to(root):
        parser.error("Research extraction stays outside Git")
    context = json.loads(
        (args.finals_dir / "contexts/walking/context_inputs.json").read_bytes()
    )
    source_hash = sha256_file(args.pbf)
    if source_hash != context["input_hashes"]["osm"]:
        raise ValueError("Destination audit and routing use different OSM snapshots")
    aoi_path = root / "resources/aoi/upload/aoi-01_mae_sai_core.geojson"
    aoi = unary_union(
        [shape(f["geometry"]) for f in json.loads(aoi_path.read_bytes())["features"]]
    )
    project = Transformer.from_crs(4326, 32647, always_xy=True).transform
    inverse = Transformer.from_crs(32647, 4326, always_xy=True).transform
    aoi_m = transform(project, aoi)
    search = transform(inverse, aoi_m.buffer(10000))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _, features = _extract_osm(
        args.pbf,
        search.bounds,
        args.output_dir,
        source_hash,
        hashlib.sha256(canonical_bytes(mapping(search))).hexdigest(),
    )
    existing = {r["facility_id"]: r for r in context["osm_facilities"]}
    records = []
    for site in _osm_facilities(features):
        geometry = shape(site["source_geometry"])
        distance = transform(project, geometry).distance(aoi_m)
        if distance > 10000:
            continue
        matched = existing.get(site["facility_id"])
        eligible = bool(
            matched
            and matched.get("candidate_destination_eligible")
            and matched.get("within_routing_context")
        )
        records.append(
            {
                "id": site["facility_id"],
                "name": site.get("name"),
                "service_type": site["service_type"],
                "source_url": site["source_url"],
                "distance_to_demand_aoi_m": distance,
                "present_in_current_inventory": matched is not None,
                "eligible_in_current_model": eligible,
                "exclusion_reason": None
                if eligible
                else "Outside eligible jurisdiction/routing coverage or without an accepted connector; no automatic inclusion.",
                "event_availability": "unknown",
            }
        )
    placements = {}
    for mode in ("walking", "modelled_vehicle"):
        ctx = json.loads(
            (args.finals_dir / f"contexts/{mode}/context_inputs.json").read_bytes()
        )
        sites = [
            r
            for r in ctx["osm_facilities"]
            if r.get("service_type") == "hospital"
            and r.get("candidate_destination_eligible")
            and r.get("within_routing_context")
        ]
        baseline = calculate_total_access(ctx["population"], ctx["edges"], sites)
        selection = select_interventions(
            ctx["population"], ctx["edges"], sites, baseline
        )
        graph = nx.Graph((r["from_node"], r["to_node"]) for r in ctx["edges"])
        rows = []
        for item in selection["candidates"]["add_destination"][:2]:
            component = nx.node_connected_component(graph, item["node_id"])
            demand = sum(
                r["total_population"]
                for r in ctx["population"]
                if r["node_id"] in component
                and r["snap_distance_m"] is not None
                and r["snap_distance_m"] <= 250
            )
            rows.append(
                {
                    **item,
                    "component_nodes": len(component),
                    "component_residents": demand,
                }
            )
        placements[mode] = rows
    result = {
        "schema_version": "1.0",
        "confidence_class": "low",
        "official_warning": False,
        "source_sha256": source_hash,
        "source_timestamp": context["source_metadata"]["osm"]["retrieved_at_utc"],
        "aoi_sha256": sha256_file(aoi_path),
        "search_radius_outside_core_m": 10000,
        "search_method": "existing_national_OSM_snapshot_points_buildings_sites_geometric_buffer",
        "hospital_count": sum(r["service_type"] == "hospital" for r in records),
        "records": sorted(records, key=lambda r: r["id"]),
        "hypothetical_placement_review": placements,
        "limitations": [
            "Bounded OSM inventory, not proof that only one real hospital serves Mae Sai.",
            "Current OSM identity does not establish event operation.",
            "Addition sites rank demand at a single snapped node, not regional accessibility improvement. Small isolated components cap their benefits; no claim of optimal hospital siting.",
        ],
    }
    if sha256_file(args.pbf) != source_hash:
        raise ValueError("OSM snapshot changed during audit")
    (args.output_dir / "destination_audit.json").write_bytes(canonical_bytes(result))
    print(
        json.dumps(
            {
                "facilities": len(records),
                "hospitals": result["hospital_count"],
                "placements": placements,
            }
        )
    )


if __name__ == "__main__":
    main()
