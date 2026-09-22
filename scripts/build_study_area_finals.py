"""Build service-specific, explicitly hypothetical access cases outside Mae Sai."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import networkx as nx
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

from floodguard.evidence_catalog import assert_public_safe, canonical_bytes, load_aois, sha256_file
from floodguard.evidence_connectivity import audit_connectivity
from floodguard.evidence_case_review import apply_destination_review
from floodguard.evidence_context import build_context_inputs
from floodguard.evidence_finals import build_finals_analysis
from floodguard.evidence_pipeline import build_runtime_identity, write_json
from floodguard.evidence_routes import build_pin_comparisons


def component_review(context: dict, sites: list[dict]) -> list[dict]:
    """Account for connected demand and destinations without inventing junctions."""
    graph = nx.Graph((e["from_node"], e["to_node"]) for e in context["edges"])
    components = sorted(nx.connected_components(graph), key=lambda nodes: min(nodes))
    owners = {node: index for index, nodes in enumerate(components) for node in nodes}
    rows = [{"id": min(nodes), "nodes": len(nodes), "population": 0.0,
             "destination_ids": []} for nodes in components]
    for person in context["population"]:
        if person.get("node_id") in owners:
            rows[owners[person["node_id"]]]["population"] += person["total_population"]
    for site in sites:
        if site.get("node_id") in owners and site.get("snap_distance_m", float("inf")) <= 100:
            rows[owners[site["node_id"]]]["destination_ids"].append(site["facility_id"])
    return sorted(rows, key=lambda row: (-row["population"], row["id"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("context-root", "reporting-dir", "output-dir", "timeline"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--aoi-id", required=True, choices=(
        "aoi-03_hat_yai_core", "aoi-05_chao_phraya_bang_ban_sena", "aoi-06_chao_phraya_rangsit"))
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--destination-review", type=Path)
    parser.add_argument("--flood-candidate", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output_dir.resolve().is_relative_to(root):
        parser.error("Research outputs must remain outside Git")
    modules = ("evidence_finals.py", "evidence_routes.py", "evidence_context.py",
               "evidence_scenarios.py", "evidence_interventions.py",
               "evidence_population_review.py", "evidence_connectivity.py", "evidence_case_review.py", "evidence_flood_scenario.py")
    implementation = {name: sha256_file(root / "src/floodguard" / name) for name in modules}
    builder_hash = sha256_file(Path(__file__))
    aois = {row["id"]: row for row in load_aois(root / "resources/aoi/upload")}
    aoi = aois[args.aoi_id]
    routing = aois["aoi-04_hat_yai_basin"] if args.aoi_id.startswith("aoi-03") else aoi
    units = json.loads((args.reporting_dir / "reporting_units.geojson").read_bytes())
    jurisdiction = unary_union([shape(f["geometry"]) for f in units["features"]])
    geometries = [(f["properties"]["adm3_pcode"], shape(f["geometry"])) for f in units["features"]]
    contexts = {}
    review = json.loads(args.destination_review.read_bytes()) if args.destination_review else None
    for mode in ("walking", "modelled_vehicle"):
        print(f"Building {args.aoi_id}: {mode}", flush=True)
        context = build_context_inputs(args.context_root, aoi["geometry"], routing["geometry"], [],
            args.output_dir / "contexts" / mode, reporting_geometry=mapping(jurisdiction),
            travel_mode="walking" if mode == "walking" else "legacy_vehicle")
        if review:
            context = apply_destination_review(context, review)
            context["input_hashes"]["destination_review"] = sha256_file(args.destination_review)
        for row in context["population"]:
            matches = [code for code, geometry in geometries if geometry.covers(Point(row["longitude"], row["latitude"]))]
            row["subdistrict_id"] = matches[0] if len(matches) == 1 else "unassigned"
        context["input_hashes"]["reporting_units"] = sha256_file(args.reporting_dir / "reporting_units.geojson")
        context["canonical_sha256"] = hashlib.sha256(canonical_bytes({k: v for k, v in context.items()
            if k not in ("canonical_sha256", "generated_at")})).hexdigest()
        contexts[mode] = context
    walking = contexts["walking"]
    population = sum(row["total_population"] for row in walking["population"])
    excluded = walking["coverage"]["population_excluded_outside_reporting_scope"]
    scope = {"jurisdiction": "Thai reporting-boundary intersections; routes limited to the recorded context polygon",
        "population_year": 2020, "boundary_reference_date": "2022-01-22",
        "osm_retrieved_at": walking["source_metadata"]["osm"]["retrieved_at_utc"],
        "study_population": population + excluded, "in_scope_population": population, "excluded_population": excluded}
    print("Computing service, capacity and speed sensitivity scenarios", flush=True)
    summary, detailed = build_finals_analysis(contexts, scope=scope,
        timeline=json.loads(args.timeline.read_bytes()), generated_at=args.generated_at)
    summary["question"] = f"How does access to distinct services change under explicit disruptions in {args.aoi_id}?"
    summary["case_identity"] = {"aoi_id": args.aoi_id, "aoi_sha256": aoi["sha256"],
        "routing_aoi_id": routing["id"], "flood_basis": "unavailable_explicit_disruptions_only"}
    if review:
        summary["destination_review"] = review
        summary["limitations"].insert(0, review["service_definition"])
    summary["limitations"].insert(0, "No accepted event flood extent is bound to this case. Any candidate-driven closures remain hypothetical; accepted flood exposure and FPPS remain unavailable.")
    if args.aoi_id.startswith(("aoi-05", "aoi-06")):
        summary["limitations"].insert(1, "The 2024 and 2025 event contexts share this same access baseline and scenario analysis. Identical values are not evidence of unchanged flood impacts. Routing stops at the AOI boundary; outside destinations and paths are not evaluated.")
    summary["connectivity_audits"], detailed["connectivity_audits"] = {}, {}
    summary["dependency_review"] = {}
    for mode, context in contexts.items():
        sites = [row for row in context["osm_facilities"] if row.get("service_type") == "hospital"
                 and row.get("candidate_destination_eligible") and row.get("within_routing_context")]
        audit = audit_connectivity(context["population"], context["edges"], sites,
            source_timestamp=context["source_metadata"]["osm"]["retrieved_at_utc"])
        detailed["connectivity_audits"][mode] = audit
        summary["connectivity_audits"][mode] = {k: v for k, v in audit.items()
            if k not in ("edge_impacts", "articulation_impacts")}
        summary["connectivity_audits"][mode]["highest_edge_impacts"] = sorted(audit["edge_impacts"],
            key=lambda row: (-row["residents_losing_all_routes"], row["edge_id"]))[:10]
        components = component_review(context, sites)
        detailed.setdefault("component_review", {})[mode] = components
        summary["dependency_review"][mode] = {"service": "hospital", "routing_boundary": routing["id"],
            "components_without_hospital": sum(not r["destination_ids"] for r in components),
            "largest_populated_components": components[:10],
            "unreviewed_grade_candidates": context["connectivity_review"]["shared_coordinate_grade_split_count"],
            "connection_policy": "Existing nearest eligible node within 100 m; no extra connector or junction inferred from proximity."}
    summary["topology_review"] = {"reviewed_candidates": 0, "accepted_connections": 0,
        "summary": "Graph dependency audit completed. Road grade transitions, facility entrances and event passability remain unverified; no automatic topology repairs."}
    crosswalk = json.loads((args.reporting_dir / "reporting_crosswalk.json").read_bytes())
    selected = next(row for row in crosswalk["aois"] if row["aoi_id"] == args.aoi_id)
    baseline = detailed.get(f"{summary['primary_service']}-walking-1", {}).get("baseline", {})
    briefs = []
    for unit in selected["units"]:
        rows = [r for r in baseline.get("node_results", []) if r["subdistrict_id"] == unit["adm3_pcode"]]
        total = sum(r["total_population"] for r in rows)
        if total < 100:
            continue
        unknown = sum(r["total_population"] for r in rows if r["snap_status"] != "connected")
        no_route = sum(r["total_population"] for r in rows if r["snap_status"] == "connected" and r["normal_access_minutes"] is None)
        briefs.append({"id": unit["adm3_pcode"], "name": unit.get("name", unit.get("adm3_name", unit["adm3_pcode"])),
            "name_th": unit.get("name_th", unit.get("adm3_name_th", unit["adm3_pcode"])),
            "unit_coverage_fraction": unit.get("unit_coverage_fraction", unit.get("fraction_of_unit", 0)),
            "modelled_population": total, "priority": "verification", "service_type": summary["primary_service"],
            "travel_mode": "walking", "main_drivers": [f"{unknown:,.0f} modelled residents have no accepted connector.",
                f"{no_route:,.0f} graph-connected residents have no route to the selected service."],
            "useful_intervention": "Inspect the highest-demand disconnected components and destination entrances before acting on disruption or temporary-site experiments.",
            "uncertainty": ["Partial AOI intersection, not a whole-subdistrict priority.", "No accepted event flood extent; residential scenario counts, not observed flood impact."]})
    summary["focus_briefs"] = sorted(briefs, key=lambda r: (-r["modelled_population"], r["id"]))[:2]
    flood_closures = None
    if args.flood_candidate:
        from floodguard.evidence_flood_scenario import candidate_flood_scenario

        provenance = json.loads((args.flood_candidate / "manifest.json").read_bytes())
        if provenance["aoi_sha256"] != aoi["sha256"] or provenance["event_id"] != "hat_yai_2025" or args.aoi_id != "aoi-03_hat_yai_core":
            raise ValueError("Candidate flood belongs to a different AOI or event")
        candidate = {}
        for name in ("candidate_extent", "observation_footprint"):
            path = args.flood_candidate / (name + ".geojson")
            if sha256_file(path) != provenance["products"][name]["sha256"]:
                raise ValueError("Candidate geometry differs from manifest")
            candidate[name] = json.loads(path.read_bytes())
        summary["flood_scenarios"], flood_closures = {}, {}
        for mode, context in contexts.items():
            result = candidate_flood_scenario(context, candidate["candidate_extent"], candidate["observation_footprint"], provenance)
            summary["flood_scenarios"][mode] = result
            flood_closures[mode] = [r["edge_id"] for r in result["closed_edges"]]
        summary["case_identity"]["flood_basis"] = "unvalidated_satellite_candidate"
    summary["routes"] = build_pin_comparisons(contexts, flood_closures=flood_closures)
    if flood_closures is not None:
        summary["routes"]["closure_basis"] = "candidate_flood"
    summary["analysis_sha256"] = hashlib.sha256(canonical_bytes({k: v for k, v in summary.items() if k != "analysis_sha256"})).hexdigest()
    assert_public_safe(summary)
    write_json(args.output_dir / "analysis.json", summary)
    write_json(args.output_dir / "scenario_details.json", detailed)
    for mode, context in contexts.items():
        write_json(args.output_dir / "contexts" / mode / "context_inputs.json", context)
    if builder_hash != sha256_file(Path(__file__)) or implementation != {name: sha256_file(root / "src/floodguard" / name) for name in modules}:
        raise ValueError("Implementation changed during computation")
    write_json(args.output_dir / "build_receipt.json", {"builder_name": Path(__file__).name,
        "builder_sha256": builder_hash, "aoi_sha256": aoi["sha256"], "generated_at": args.generated_at,
        "build_runtime": build_runtime_identity(context_enabled=True), "implementation": implementation,
        "analysis_sha256": sha256_file(args.output_dir / "analysis.json"), "timeline_sha256": sha256_file(args.timeline),
        "reporting_units_sha256": sha256_file(args.reporting_dir / "reporting_units.geojson"),
        "reporting_crosswalk_sha256": sha256_file(args.reporting_dir / "reporting_crosswalk.json"),
        "context_hashes": {mode: ctx["canonical_sha256"] for mode, ctx in contexts.items()},
        "files": {p.relative_to(args.output_dir).as_posix(): sha256_file(p) for p in sorted(args.output_dir.rglob("*.json")) if p.name != "build_receipt.json"}})
    print(json.dumps({"analysis": summary["analysis_sha256"], "services": {s["id"]: s["facilities"] for s in summary["services"]}}))


if __name__ == "__main__":
    main()
