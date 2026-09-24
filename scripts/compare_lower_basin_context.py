"""Compare lower Chao Phraya walking access across bounded routing radii.

This is a research-only context test. The AOI demand raster, reporting-unit
assignment, OSM snapshot and WorldPop vintage stay fixed. No event flood layer
or historical road passability is inferred from the comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

from floodguard.evidence_catalog import canonical_bytes, load_aois, sha256_file
from floodguard.evidence_context import _canonical_hash, build_context_inputs
from floodguard.evidence_scenarios import calculate_total_access

AOI_IDS = (
    "aoi-05_chao_phraya_bang_ban_sena",
    "aoi-06_chao_phraya_rangsit",
)
PROJECT = Transformer.from_crs(4326, 32647, always_xy=True).transform
UNPROJECT = Transformer.from_crs(32647, 4326, always_xy=True).transform


def route_buffer(aoi_geometry: dict, radius_km: int) -> dict:
    """Buffer the fixed WGS84 demand AOI in local metres for road extraction."""

    if radius_km <= 0 or radius_km > 30:
        raise ValueError("routing radius must be between 1 and 30 km")
    aoi = shape(aoi_geometry)
    return mapping(transform(UNPROJECT, transform(PROJECT, aoi).buffer(radius_km * 1000)))


def fixed_demand_roster(baseline: list[dict], expanded: list[dict]) -> str:
    """Reject any changed residential cells and carry over reporting IDs."""

    fields = ("longitude", "latitude", "total_population")
    old = {row["population_id"]: row for row in baseline}
    new = {row["population_id"]: row for row in expanded}
    if len(old) != len(baseline) or len(new) != len(expanded) or old.keys() != new.keys():
        raise ValueError("routing comparison changed the fixed demand population IDs")
    for identifier, row in new.items():
        original = old[identifier]
        if any(not math.isclose(row[key], original[key], rel_tol=0, abs_tol=1e-9) for key in fields):
            raise ValueError(f"routing comparison changed demand cell {identifier}")
        row["subdistrict_id"] = original["subdistrict_id"]
    roster = [
        {"population_id": key, **{field: old[key][field] for field in fields},
         "subdistrict_id": old[key]["subdistrict_id"]}
        for key in sorted(old)
    ]
    return hashlib.sha256(canonical_bytes(roster)).hexdigest()


def hospital_duplicate_review(context: dict) -> dict:
    """Exclude only a point contained in a matching named or Wikidata site.

    A spatially close point alone never proves a duplicate. The review is
    limited to OSM source-object deduplication, not operating-facility approval.
    """

    hospitals = [row for row in context["osm_facilities"] if row["service_type"] == "hospital"]
    exclusions = []
    ambiguous = []
    for point in hospitals:
        if point["source_geometry_type"] != "Point":
            continue
        parents = []
        for site in hospitals:
            if site["source_geometry_type"] == "Point" or site["facility_id"] == point["facility_id"]:
                continue
            if not shape(site["source_geometry"]).covers(shape(point["source_geometry"])):
                continue
            same_id = bool(point.get("wikidata") and point["wikidata"] == site.get("wikidata"))
            point_name = " ".join(point.get("name", "").split()).casefold()
            site_name = " ".join(site.get("name", "").split()).casefold()
            same_name = point_name not in {"", "unnamed osm candidate"} and point_name == site_name
            if same_id or same_name:
                parents.append((site, "shared_wikidata_and_containment" if same_id else "same_name_and_containment"))
        if len(parents) == 1:
            site, reason = parents[0]
            exclusions.append({
                "facility_id": point["facility_id"],
                "duplicate_of": site["facility_id"],
                "reason": reason,
                "source_url": point["source_url"],
                "parent_source_url": site["source_url"],
            })
        elif len(parents) > 1:
            ambiguous.append({"facility_id": point["facility_id"],
                              "possible_parents": sorted(site["facility_id"] for site, _ in parents)})
    return {
        "osm_sha256": context["input_hashes"]["osm"],
        "method": "contained_point_matching_name_or_wikidata_v1",
        "exclusions": sorted(exclusions, key=lambda row: row["facility_id"]),
        "ambiguous": sorted(ambiguous, key=lambda row: row["facility_id"]),
        "identity_scope": "OSM source-object duplication only; operation and entrance unverified",
    }


def summarize_context(context: dict, duplicate_review: dict) -> dict:
    """Report graph/access coverage for eligible hospital candidates only."""

    if duplicate_review["osm_sha256"] != context["input_hashes"]["osm"]:
        raise ValueError("Destination review uses another OSM snapshot")
    excluded = {row["facility_id"] for row in duplicate_review["exclusions"]}
    hospitals = [row for row in context["osm_facilities"] if row["service_type"] == "hospital"]
    eligible = [
        row for row in hospitals
        if row["facility_id"] not in excluded
        and row.get("candidate_destination_eligible")
        and row.get("within_routing_context")
        and row.get("node_id") is not None
        and row.get("snap_distance_m") is not None
        and row["snap_distance_m"] <= 100
    ]
    baseline = calculate_total_access(
        context["population"], context["edges"], eligible,
        source_timestamp=context["source_metadata"]["osm"]["retrieved_at_utc"],
    )
    rows = baseline["node_results"]
    connected = [row for row in rows if row["snap_status"] == "connected"]
    total = math.fsum(row["total_population"] for row in rows)
    no_connector = math.fsum(row["total_population"] for row in rows if row["snap_status"] != "connected")
    no_route = math.fsum(row["total_population"] for row in connected if row["normal_access_minutes"] is None)
    thresholds = {
        str(limit): math.fsum(
            row["total_population"] for row in connected
            if row["normal_access_minutes"] is not None and row["normal_access_minutes"] <= limit
        )
        for limit in (15, 30, 60)
    }
    return {
        "modelled_residents_2020": total,
        "population_cells": len(rows),
        "residents_without_accepted_connector": no_connector,
        "graph_connected_residents_without_hospital_route": no_route,
        "within_minutes": thresholds,
        "hospital_source_objects": len(hospitals),
        "hospital_candidate_destinations": len(eligible),
        "hospital_destination_ids": sorted(row["facility_id"] for row in eligible),
        "deduplicated_point_objects": len(duplicate_review["exclusions"]),
        "ambiguous_duplicate_objects": len(duplicate_review["ambiguous"]),
        "graph_nodes": len(context["node_coordinates"]),
        "graph_edges": len(context["edges"]),
        "graph_components": context["coverage"].get("connected_components"),
        "context_sha256": context["canonical_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-root", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--reporting-units", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--aoi-id", choices=AOI_IDS, required=True)
    parser.add_argument("--radii-km", nargs="+", type=int, default=[5, 10, 15])
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.output_dir.resolve().is_relative_to(repo):
        parser.error("Research output must remain outside Git")
    if args.output_dir.exists():
        parser.error("Output directory already exists; immutable runs cannot be overwritten")
    radii = sorted(set(args.radii_km))
    if radii != args.radii_km or any(value <= 0 or value > 30 for value in radii):
        parser.error("Use strictly increasing unique radii between 1 and 30 km")
    aois = {row["id"]: row for row in load_aois(repo / "resources/aoi/upload")}
    aoi = aois[args.aoi_id]
    legacy_file = args.baseline_root / "study_finals" / args.aoi_id / "contexts/walking/context_inputs.json"
    legacy = json.loads(legacy_file.read_text(encoding="utf-8"))
    units = json.loads(args.reporting_units.read_text(encoding="utf-8"))
    reporting = unary_union([shape(row["geometry"]) for row in units["features"]])
    demand = shape(aoi["geometry"])
    if not reporting.covers(demand):
        parser.error("Reporting units do not fully cover the fixed demand AOI")
    if legacy["input_hashes"]["aoi_geometry"] != _canonical_hash(mapping(demand)):
        parser.error("Baseline demand geometry differs from current AOI")
    args.output_dir.mkdir(parents=True)
    comparison = {
        "schema_version": "floodguard.lower_basin_routing_context_comparison.v1",
        "aoi_id": args.aoi_id,
        "aoi_sha256": aoi["sha256"],
        "source_hashes": {key: legacy["input_hashes"][key] for key in ("osm", "worldpop")},
        "reporting_units_sha256": sha256_file(args.reporting_units),
        "legacy_context_sha256": sha256_file(legacy_file),
        "events_sharing_static_context": ["chao_phraya_2024", "chao_phraya_2025"],
        "event_flood_layer": None,
        "confidence_class": "low",
        "official_warning": False,
        "operational_status": "non_operational",
        "service": "hospital_osm_candidates",
        "travel_mode": "walking_5_km_h_assumed",
        "results": [],
    }
    roster_hash = fixed_demand_roster(legacy["population"], legacy["population"])
    comparison["fixed_demand_roster_sha256"] = roster_hash
    for radius in (0, *radii):
        if radius == 0:
            context = legacy
        else:
            print(f"Building {args.aoi_id} routing radius {radius} km", flush=True)
            context = build_context_inputs(
                args.context_root, aoi["geometry"], route_buffer(aoi["geometry"], radius),
                [], args.output_dir / f"radius_{radius:02d}km", travel_mode="walking",
            )
            if any(context["input_hashes"][key] != comparison["source_hashes"][key] for key in ("osm", "worldpop")):
                raise ValueError("Expanded routing uses changed source files")
            if fixed_demand_roster(legacy["population"], context["population"]) != roster_hash:
                raise ValueError("Expanded routing changed the demand roster")
        review = hospital_duplicate_review(context)
        metrics = summarize_context(context, review)
        row = {"radius_km": radius, "routing_geometry_sha256": context["input_hashes"]["routing_geometry"],
               **metrics}
        comparison["results"].append(row)
        target = args.output_dir / ("legacy" if radius == 0 else f"radius_{radius:02d}km")
        target.mkdir(exist_ok=True)
        (target / "hospital_duplicate_review.json").write_bytes(canonical_bytes(review))
        (target / "metrics.json").write_bytes(canonical_bytes(row))
        print(json.dumps({"radius_km": radius, "within_30_min": metrics["within_minutes"]["30"],
                          "no_route": metrics["graph_connected_residents_without_hospital_route"],
                          "hospital_candidates": metrics["hospital_candidate_destinations"]}), flush=True)
    for previous, current in zip(comparison["results"], comparison["results"][1:]):
        current["delta_from_previous"] = {
            "within_30_min_residents": current["within_minutes"]["30"] - previous["within_minutes"]["30"],
            "no_route_residents": current["graph_connected_residents_without_hospital_route"] - previous["graph_connected_residents_without_hospital_route"],
        }
    comparison["interpretation"] = (
        "Static 2020 population and 2026 OSM walking scenario. Context-radius stability is a "
        "bounded sensitivity check, not proof of complete routes, verified hospital operation, "
        "event flood impact or safe navigation. The 2024 and 2025 events have no separate flood layers."
    )
    comparison["builder_sha256"] = sha256_file(Path(__file__))
    comparison["comparison_sha256"] = hashlib.sha256(canonical_bytes(comparison)).hexdigest()
    (args.output_dir / "comparison.json").write_bytes(canonical_bytes(comparison))


if __name__ == "__main__":
    main()
