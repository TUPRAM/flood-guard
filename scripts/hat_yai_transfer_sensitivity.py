"""Test Hat Yai candidate road-closure assumptions without accepting the event.

The unchanged September-derived 2.25 dB rule supplies a November 2025 candidate
geometry. This script tests the consequence of declaring every positive road
overlap closed versus one- and 2.5-pixel minimum overlaps. It never treats a
candidate intersection, bridge tag, or route loss as observed passability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from floodguard.evidence_catalog import canonical_bytes, sha256_file
from floodguard.evidence_scenarios import calculate_total_access

SCENARIOS = (
    ("any_positive_overlap", 0.0, False),
    ("at_least_20m_overlap", 20.0, False),
    ("at_least_50m_overlap", 50.0, False),
    ("at_least_20m_excluding_mapped_grade_separation", 20.0, True),
)


def select_candidate_closures(
    overlaps: list[dict], edges: list[dict], minimum_overlap_m: float,
    *, exclude_mapped_grade_separation: bool = False,
) -> tuple[list[str], dict[str, int]]:
    """Select source-bound edge IDs using a declared scenario threshold."""

    if not math.isfinite(minimum_overlap_m) or minimum_overlap_m < 0:
        raise ValueError("minimum overlap must be finite and non-negative")
    by_id = {edge["edge_id"]: edge for edge in edges}
    if len(by_id) != len(edges):
        raise ValueError("road graph has duplicate edge IDs")
    closed, seen = [], set()
    tagged_bridge_or_tunnel = 0
    excluded_grade = 0
    for row in overlaps:
        identifier = row["edge_id"]
        if identifier in seen or identifier not in by_id:
            raise ValueError("candidate overlap has duplicate or unknown edge ID")
        seen.add(identifier)
        length = float(row["intersection_length_m"])
        fraction = float(row["intersection_fraction"])
        edge_length = float(by_id[identifier]["length_m"])
        if (
            not math.isfinite(length) or length <= 0 or not math.isfinite(fraction)
            or fraction <= 0 or fraction > 1 or not math.isfinite(edge_length)
            or edge_length <= 0 or length > edge_length + 0.01
            or not math.isclose(fraction, min(1.0, length / edge_length), abs_tol=0.01)
        ):
            raise ValueError(f"invalid centerline intersection for {identifier}")
        edge = by_id[identifier]
        grade_tagged = any(str(edge.get(key, "no")).lower() not in {"no", "", "0", "none"}
                           for key in ("bridge", "tunnel"))
        tagged_bridge_or_tunnel += grade_tagged
        selected = length > 1e-6 if minimum_overlap_m == 0 else length >= minimum_overlap_m
        if selected and exclude_mapped_grade_separation and grade_tagged:
            excluded_grade += 1
        elif selected:
            closed.append(identifier)
    return sorted(closed), {
        "source_intersections": len(overlaps),
        "tagged_bridge_or_tunnel_intersections": tagged_bridge_or_tunnel,
        "excluded_mapped_grade_edges": excluded_grade,
    }


def access_effect(result: dict) -> dict:
    """Summarize disjoint routing states and overlapping threshold crossings."""

    rows = result["node_results"]
    comparable = [
        row for row in rows
        if row["normal_access_minutes"] is not None and row["scenario_access_minutes"] is not None
    ]
    comparable_population = math.fsum(row["total_population"] for row in comparable)
    weighted_delay = math.fsum(
        (row["scenario_access_minutes"] - row["normal_access_minutes"]) * row["total_population"]
        for row in comparable
    )
    return {
        "modelled_residents_2020": math.fsum(row["total_population"] for row in rows),
        "unknown_connector_population": math.fsum(
            row["total_population"] for row in rows if row["snap_status"] != "connected"
        ),
        "baseline_no_hospital_route_population": math.fsum(
            row["total_population"] for row in rows
            if row["snap_status"] == "connected" and row["normal_access_minutes"] is None
        ),
        "new_all_route_loss_population": math.fsum(
            row["total_population"] for row in rows
            if row["normal_access_minutes"] is not None and row["scenario_access_minutes"] is None
        ),
        "new_threshold_loss_population": {
            str(limit): math.fsum(
                row["total_population"] for row in rows if row[f"loses_{limit}_min_access"]
            )
            for limit in (15, 30, 60)
        },
        "comparable_finite_route_population": comparable_population,
        "mean_delay_minutes_among_comparable_finite_routes": (
            weighted_delay / comparable_population if comparable_population else None
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finals-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.output_dir.resolve().is_relative_to(repo):
        parser.error("Research output must remain outside Git")
    if args.output_dir.exists():
        parser.error("Output directory already exists; immutable run cannot be overwritten")
    candidate_file = args.candidate_dir / "manifest.json"
    candidate = json.loads(candidate_file.read_text(encoding="utf-8"))
    if (
        candidate["event_id"] != "hat_yai_2025"
        or candidate["evidence_role"] != "candidate"
        or candidate["confidence_class"] != "low"
        or candidate["official_warning"] is not False
        or candidate["eligible_for_validation"] is not False
        or candidate["eligible_for_accepted_fpps"] is not False
        or candidate["rights"]["local_processing"] is not True
    ):
        parser.error("Candidate lacks the required Hat Yai research-only contract")
    for name, product in candidate["products"].items():
        if sha256_file(args.candidate_dir / product["file"]) != product["sha256"]:
            parser.error(f"Candidate {name} differs from its manifest")
    if sha256_file(args.candidate_dir / "candidate_mask.tif") != candidate["mask_sha256"]:
        parser.error("Candidate raster differs from its manifest")
    if sha256_file(repo / "outputs/cdse_hat_yai_acquisition_manifest.csv") != candidate["source_manifest_sha256"]:
        parser.error("Tracked original-SAFE acquisition manifest differs")
    receipt = json.loads((args.finals_dir / "build_receipt.json").read_text(encoding="utf-8"))
    if receipt["aoi_sha256"] != candidate["aoi_sha256"]:
        parser.error("Finals analysis uses another AOI")
    analysis_file = args.finals_dir / "analysis.json"
    if sha256_file(analysis_file) != receipt["files"]["analysis.json"]:
        parser.error("Finals analysis differs from build receipt")
    analysis = json.loads(analysis_file.read_text(encoding="utf-8"))
    if analysis["case_identity"]["flood_basis"] != "unvalidated_satellite_candidate":
        parser.error("Finals analysis no longer identifies this candidate lane")
    args.output_dir.mkdir(parents=True)
    outputs = {
        "schema_version": "floodguard.hat_yai_transfer_closure_sensitivity.v1",
        "aoi_id": "aoi-03_hat_yai_core",
        "event_id": "hat_yai_2025",
        "source_timestamp": candidate["source_timestamp"],
        "candidate_manifest_sha256": sha256_file(candidate_file),
        "analysis_sha256": sha256_file(analysis_file),
        "candidate_method": candidate["method"],
        "candidate_threshold_db": candidate["threshold_db"],
        "pixel_size_m": candidate["grid"]["resolution_m"],
        "candidate_area_m2": candidate["products"]["candidate_extent"]["area_m2"],
        "confidence_class": "low",
        "evidence_role": "candidate_scenario_sensitivity",
        "official_warning": False,
        "operational_status": "non_operational",
        "accepted_fpps": None,
        "accepted_action_class": None,
        "method": "fixed_candidate_centerline_overlap_minimum_length_and_mapped_grade_sensitivity_v1",
        "results": {},
    }
    for mode in ("walking", "modelled_vehicle"):
        context_file = args.finals_dir / "contexts" / mode / "context_inputs.json"
        if sha256_file(context_file) != receipt["files"][f"contexts/{mode}/context_inputs.json"]:
            parser.error(f"{mode} context differs from build receipt")
        context = json.loads(context_file.read_text(encoding="utf-8"))
        saved = analysis["flood_scenarios"][mode]
        if saved["context_sha256"] != context["canonical_sha256"] or saved["candidate_provenance"] != candidate:
            parser.error(f"{mode} candidate or context identity differs")
        sites = [
            row for row in context["osm_facilities"]
            if row.get("service_type") == "hospital"
            and row.get("candidate_destination_eligible") is True
            and row.get("within_routing_context") is True
        ]
        baseline = calculate_total_access(context["population"], context["edges"], sites)
        rows = []
        for name, minimum, exclude_grade in SCENARIOS:
            closed, diagnostics = select_candidate_closures(
                saved["closed_edges"], context["edges"], minimum,
                exclude_mapped_grade_separation=exclude_grade,
            )
            result = calculate_total_access(
                context["population"], context["edges"], sites,
                scenario={"closed_edge_ids": closed}, baseline_result=baseline,
            )
            effect = access_effect(result)
            row = {
                "scenario_id": name,
                "minimum_overlap_m": minimum,
                "exclude_mapped_grade_separation": exclude_grade,
                "closed_segment_count": len(closed),
                "closed_edge_ids_sha256": hashlib.sha256(canonical_bytes(closed)).hexdigest(),
                "intersection_review": diagnostics,
                **effect,
            }
            rows.append(row)
            print(json.dumps({"mode": mode, "scenario": name,
                              "closed": len(closed), "loss_30": effect["new_threshold_loss_population"]["30"],
                              "all_route_loss": effect["new_all_route_loss_population"]}), flush=True)
        original = rows[0]
        previous = saved["impact"]
        if (
            original["closed_segment_count"] != len(saved["closed_edges"])
            or not math.isclose(original["new_threshold_loss_population"]["30"], previous["losing_30_min_access"], abs_tol=0.0001)
            or not math.isclose(original["new_all_route_loss_population"], previous["newly_unreachable_population"], abs_tol=0.0001)
        ):
            parser.error(f"{mode} original closure effect did not reproduce")
        outputs["results"][mode] = {
            "context_sha256": context["canonical_sha256"],
            "context_file_sha256": sha256_file(context_file),
            "hospital_candidate_destinations": len(sites),
            "candidate_affected_population": saved["candidate_affected_population"],
            "unobserved_population": saved["unobserved_population"],
            "scenarios": rows,
        }
    outputs["assumptions"] = [
        "The flood candidate and OSM road graph stay fixed; only the hypothetical closure rule changes.",
        "Zero threshold means every positive-length candidate intersection. The 20 m and 50 m alternatives equal one and 2.5 candidate grid cells; they are sensitivity values, not calibrated physical closure criteria.",
        "The mapped-grade alternative leaves OSM-tagged bridges and tunnels open by assumption; their event passability is not established.",
        "Hospital candidates are the existing reviewed civilian comparison set; entrance and 2025 operating status remain unverified.",
        "New threshold losses overlap all-route losses and cannot be added together. Mean delay denominator is comparable finite-route population.",
    ]
    outputs["limitations"] = [
        "Uncalibrated GCP-warped amplitude-drop candidate lacks independent Hat Yai reference, terrain correction, speckle and permanent-water review, and local alignment residuals.",
        "November 11/23 UTC acquisitions (November 12/24 Thailand) do not reconstruct peak flooding.",
        "Road-centerline intersection is candidate exposure; closure and bridge-passability rules are assumptions, not dated observations.",
        "WorldPop 2020 cell-centre residents are residential context, not flood victims or observed service users.",
        "No Mae Sai accuracy, accepted FPPS or event qualification transfers to Hat Yai.",
    ]
    outputs["builder_sha256"] = sha256_file(Path(__file__))
    outputs["result_sha256"] = hashlib.sha256(canonical_bytes(outputs)).hexdigest()
    (args.output_dir / "transfer_sensitivity.json").write_bytes(canonical_bytes(outputs))


if __name__ == "__main__":
    main()
