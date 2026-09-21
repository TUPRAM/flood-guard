"""Build a separate, source-bound Mae Sai finals scenario package from existing data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

from floodguard.evidence_catalog import (
    assert_public_safe,
    canonical_bytes,
    load_aois,
    sha256_file,
)
from floodguard.evidence_context import build_context_inputs
from floodguard.evidence_finals import build_finals_analysis
from floodguard.evidence_pipeline import build_runtime_identity, write_json
from floodguard.evidence_routes import build_pin_comparisons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-root", type=Path, required=True)
    parser.add_argument("--reporting-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--aoi-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "resources/aoi/upload",
    )
    parser.add_argument(
        "--timeline",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "resources/finals/mae_sai_timeline.json",
    )
    parser.add_argument("--reviewed-junctions", type=Path)
    parser.add_argument("--public-origins", type=Path)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    modules = (
        "evidence_finals.py",
        "evidence_routes.py",
        "evidence_context.py",
        "evidence_scenarios.py",
        "evidence_interventions.py",
        "evidence_population_review.py",
    )
    implementation = {
        name: sha256_file(root / "src/floodguard" / name) for name in modules
    }
    builder_hash = sha256_file(Path(__file__))
    if args.output_dir.resolve().is_relative_to(root):
        parser.error("Full derived research outputs must remain outside Git")
    units = json.loads(
        (args.reporting_dir / "reporting_units.geojson").read_text(encoding="utf-8")
    )
    crosswalk = json.loads(
        (args.reporting_dir / "reporting_crosswalk.json").read_text(encoding="utf-8")
    )
    aois = {row["id"]: row for row in load_aois(args.aoi_dir)}
    aoi_id = "aoi-01_mae_sai_core"
    aoi = aois[aoi_id]
    jurisdiction = unary_union(
        [shape(feature["geometry"]) for feature in units["features"]]
    )
    reviewed = (
        json.loads(args.reviewed_junctions.read_text(encoding="utf-8"))
        if args.reviewed_junctions
        else []
    )
    if isinstance(reviewed, dict):
        reviewed = reviewed["reviewed_junctions"]
    origins = (
        json.loads(args.public_origins.read_text(encoding="utf-8"))
        if args.public_origins
        else []
    )
    contexts = {}
    for mode in ("walking", "modelled_vehicle"):
        print(f"Building {mode} context", flush=True)
        contexts[mode] = build_context_inputs(
            args.context_root,
            aoi["geometry"],
            aois["aoi-02_mae_sai_district"]["geometry"],
            [],
            args.output_dir / "contexts" / mode,
            reporting_geometry=mapping(jurisdiction),
            travel_mode="legacy_vehicle" if mode == "modelled_vehicle" else "walking",
            reviewed_junctions=reviewed,
            public_origin_records=origins,
        )
    population = contexts["walking"]["population"]
    # Resolve only unique point-in-polygon matches. Shared boundary cells remain unassigned.
    geometries = [
        (
            feature["properties"].get(
                "adm3_pcode", feature["properties"].get("ADM3_PCODE")
            ),
            shape(feature["geometry"]),
        )
        for feature in units["features"]
    ]
    for context in contexts.values():
        context["reviewed_junctions"] = reviewed
        for row in context["population"]:
            point = Point(row["longitude"], row["latitude"])
            matches = [code for code, geometry in geometries if geometry.covers(point)]
            row["subdistrict_id"] = matches[0] if len(matches) == 1 else "unassigned"
        # Joining geography is itself a versioned derived transformation.
        context["input_hashes"]["reporting_units"] = sha256_file(
            args.reporting_dir / "reporting_units.geojson"
        )
        context["canonical_sha256"] = hashlib.sha256(
            canonical_bytes(
                {
                    k: v
                    for k, v in context.items()
                    if k not in ("canonical_sha256", "generated_at")
                }
            )
        ).hexdigest()
    in_scope = sum(row["total_population"] for row in population)
    coverage = contexts["walking"]["coverage"]
    excluded = coverage.get("population_excluded_outside_reporting_scope", 0)
    if not isinstance(excluded, (float, int)):
        raise TypeError(
            "Excluded population must be a documented numeric coverage quantity"
        )
    scope = {
        "jurisdiction": "Thai reporting-boundary coverage; cross-border routes excluded",
        "population_year": 2020,
        "boundary_reference_date": "2022-01-22",
        "osm_retrieved_at": contexts["walking"]["source_metadata"]["osm"][
            "retrieved_at_utc"
        ],
        "study_population": in_scope + excluded,
        "in_scope_population": in_scope,
        "excluded_population": excluded,
    }
    timeline = json.loads(args.timeline.read_text(encoding="utf-8"))
    print("Computing fixed-shortlist service and speed comparisons", flush=True)
    summary, detailed = build_finals_analysis(
        contexts, scope=scope, timeline=timeline, generated_at=args.generated_at
    )
    summary["topology_review"] = {
        "reviewed_candidates": len(reviewed),
        "accepted_connections": contexts["walking"]["connectivity_review"].get(
            "connections_added", 0
        ),
        "summary": "Original OSM shared-node evidence is required for a correction. Unreviewed transitions stay disconnected; current topology does not establish event passability.",
    }
    primary_variant = f"{summary['primary_service']}-walking-1"
    baseline = detailed.get(primary_variant, {}).get("baseline", {})
    aoi_crosswalk = next(row for row in crosswalk["aois"] if row["aoi_id"] == aoi_id)
    summaries = []
    for unit in aoi_crosswalk["units"]:
        code = unit["adm3_pcode"]
        rows = [
            row
            for row in baseline.get("node_results", [])
            if row["subdistrict_id"] == code
        ]
        residents = sum(row["total_population"] for row in rows)
        unknown = sum(
            row["total_population"] for row in rows if row["snap_status"] != "connected"
        )
        no_route = sum(
            row["total_population"]
            for row in rows
            if row["snap_status"] == "connected"
            and row["normal_access_minutes"] is None
        )
        fraction = unit.get("unit_coverage_fraction", unit.get("fraction_of_unit", 0))
        if residents < 100 or fraction < 0.2:
            continue
        summaries.append(
            {
                "id": code,
                "name": unit.get("name", unit.get("adm3_name", code)),
                "name_th": unit.get("name_th", unit.get("adm3_name_th", code)),
                "unit_coverage_fraction": fraction,
                "modelled_population": residents,
                "priority": "verification",
                "service_type": summary["primary_service"],
                "travel_mode": "walking",
                "main_drivers": [
                    f"{unknown:,.0f} modelled residents have no accepted graph connector.",
                    f"{no_route:,.0f} graph-connected residents have no modelled route to the selected service.",
                ],
                "useful_intervention": "Review the consequential connections and destination entrance before comparing the fixed hypothetical additions and disruptions.",
                "uncertainty": [
                    "AOI intersection only; no full-subdistrict priority inferred.",
                    "Modelled residential access, not observed flood impact or safe evacuation advice.",
                ],
            }
        )
    summary["focus_briefs"] = sorted(
        summaries, key=lambda row: (-row["modelled_population"], row["id"])
    )[:2]
    summary["routes"] = build_pin_comparisons(contexts)
    summary["analysis_sha256"] = hashlib.sha256(
        canonical_bytes({k: v for k, v in summary.items() if k != "analysis_sha256"})
    ).hexdigest()
    assert_public_safe(summary)
    write_json(args.output_dir / "analysis.json", summary)
    write_json(args.output_dir / "scenario_details.json", detailed)
    for mode, context in contexts.items():
        write_json(args.output_dir / "contexts" / mode / "context_inputs.json", context)
    runtime = build_runtime_identity(context_enabled=True)
    if implementation != {
        name: sha256_file(root / "src/floodguard" / name) for name in modules
    } or builder_hash != sha256_file(Path(__file__)):
        raise ValueError(
            "Implementation changed during computation; rebuild with stable source"
        )
    receipt = {
        "generated_at": args.generated_at,
        "build_runtime": runtime,
        "aoi_sha256": aoi["sha256"],
        "analysis_sha256": sha256_file(args.output_dir / "analysis.json"),
        "reporting_units_sha256": sha256_file(
            args.reporting_dir / "reporting_units.geojson"
        ),
        "reporting_crosswalk_sha256": sha256_file(
            args.reporting_dir / "reporting_crosswalk.json"
        ),
        "builder_sha256": builder_hash,
        "timeline_sha256": sha256_file(args.timeline),
        "context_hashes": {
            mode: value["canonical_sha256"] for mode, value in contexts.items()
        },
        "implementation": implementation,
        "files": {
            path.relative_to(args.output_dir).as_posix(): sha256_file(path)
            for path in sorted(args.output_dir.rglob("*.json"))
            if path.name != "build_receipt.json"
        },
    }
    write_json(args.output_dir / "build_receipt.json", receipt)
    print(
        json.dumps(
            {
                "analysis": summary["analysis_sha256"],
                "services": {
                    row["id"]: row["facilities"] for row in summary["services"]
                },
                "focus_briefs": len(summary["focus_briefs"]),
            }
        )
    )


if __name__ == "__main__":
    main()
