"""Bind one explicit flood candidate to population, road closures and score bounds."""

from __future__ import annotations

import math
from collections import defaultdict

from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform, unary_union

from .evidence_finals import baseline_summary, intervention_summary
from .evidence_scenarios import calculate_total_access, evidence_assessment


def candidate_flood_scenario(
    context: dict, extent: dict, footprint: dict, provenance: dict
) -> dict:
    """Apply positive-length candidate intersections, retaining unknown coverage.

    Population uses existing WorldPop cell centres and full cell counts. Flood
    likelihood and vulnerability remain null; complete scores are explicit fixed
    0/50/100 missing-component scenarios and retain the Class E confidence rule.
    """
    if (
        provenance.get("official_warning") is not False
        or provenance.get("eligible_for_validation") is not False
    ):
        raise ValueError("Flood scenario input must remain an unvalidated candidate")
    candidate = unary_union([shape(f["geometry"]) for f in extent["features"]])
    coverage = unary_union([shape(f["geometry"]) for f in footprint["features"]])
    if coverage.is_empty or not candidate.is_valid or not coverage.is_valid:
        raise ValueError("Valid nonempty observation coverage is required")
    if not candidate.is_empty and not coverage.buffer(1e-9).covers(candidate):
        raise ValueError("Candidate extent exceeds its observation footprint")
    projection = Transformer.from_crs(4326, 32647, always_xy=True).transform
    projected = transform(projection, candidate)
    closed = []
    for edge in sorted(context["edges"], key=lambda row: row["edge_id"]):
        line = transform(
            projection,
            LineString(
                [
                    context["node_coordinates"][edge["from_node"]],
                    context["node_coordinates"][edge["to_node"]],
                ]
            ),
        )
        length = line.intersection(projected).length
        if length > 1e-6:
            closed.append(
                {
                    "edge_id": edge["edge_id"],
                    "intersection_length_m": length,
                    "intersection_fraction": min(1.0, length / line.length),
                }
            )
    sites = [
        r
        for r in context["osm_facilities"]
        if r.get("service_type") == "hospital"
        and r.get("candidate_destination_eligible") is True
        and r.get("within_routing_context") is True
    ]
    baseline = calculate_total_access(context["population"], context["edges"], sites)
    change = {"closed_edge_ids": [r["edge_id"] for r in closed]}
    result = calculate_total_access(
        context["population"],
        context["edges"],
        sites,
        scenario=change,
        baseline_result=baseline,
    )
    by_id = {r["population_id"]: r for r in context["population"]}
    areas = defaultdict(list)
    for row in result["node_results"]:
        point = Point(
            by_id[row["population_id"]]["longitude"],
            by_id[row["population_id"]]["latitude"],
        )
        areas[row["subdistrict_id"]].append(
            {
                **row,
                "candidate_overlap": candidate.covers(point),
                "observed": coverage.covers(point),
            }
        )
    assessments = []
    for area, rows in sorted(areas.items()):
        total = math.fsum(r["total_population"] for r in rows)
        observed = math.fsum(r["total_population"] for r in rows if r["observed"])
        exposed = math.fsum(
            r["total_population"] for r in rows if r["candidate_overlap"]
        )
        connected = math.fsum(
            r["total_population"] for r in rows if r["snap_status"] == "connected"
        )
        beyond = math.fsum(
            r["total_population"]
            for r in rows
            if r["snap_status"] == "connected"
            and (
                r["scenario_access_minutes"] is None
                or r["scenario_access_minutes"] > 30
            )
        )
        before_routes = math.fsum(
            r["total_population"]
            for r in rows
            if r["normal_access_minutes"] is not None
        )
        lost_routes = math.fsum(
            r["total_population"]
            for r in rows
            if r["normal_access_minutes"] is not None
            and r["scenario_access_minutes"] is None
        )
        components = {
            "flood_likelihood_0_100": None,
            "exposure_0_100": 100 * exposed / total
            if total and math.isclose(total, observed, abs_tol=1e-6)
            else None,
            "access_gap_0_100": 100 * beyond / connected if connected else None,
            "road_criticality_0_100": 100 * lost_routes / before_routes
            if before_routes
            else None,
            "vulnerability_context_0_100": None,
        }
        reasons = {
            "flood_likelihood_0_100": "Missing calibrated flood likelihood: a fixed SAR amplitude-drop threshold is not a probability.",
            "vulnerability_context_0_100": "Missing compatible observed age counts or a reconciled, versioned vulnerability/context input.",
            "exposure_0_100": "Candidate observation footprint does not cover all modelled demand, or demand is zero.",
            "access_gap_0_100": "No population with an accepted road connector.",
            "road_criticality_0_100": "No baseline population with any hospital route; relative route loss is undefined.",
        }
        assessment = evidence_assessment(
            components,
            area_id=area,
            confidence_class="low",
            source_timestamp=provenance["source_timestamp"],
        )
        assessments.append(
            {
                "subdistrict_id": area,
                "scope": "AOI_intersection_only",
                "modelled_residents": total,
                "candidate_affected_population": exposed,
                "unobserved_population": max(0.0, total - observed),
                "assessment": assessment,
                "missing_input_reasons": {
                    k: reasons[k] for k, v in components.items() if v is None
                },
            }
        )
    definition = {
        "id": "candidate-flood-closure",
        "kind": "close_edge",
        "target_id": "candidate-flood-closure-set",
        "target_label": "SAR candidate intersection closure set",
        "selection_method": "All road centrelines with positive-length intersection of the fixed >=2.25 dB candidate; selected before computing access effects.",
    }
    return {
        "schema_version": "1.0",
        "status": "candidate_scenario_only",
        "event_id": provenance["event_id"],
        "official_warning": False,
        "accepted_fpps": None,
        "accepted_action_class": None,
        "source_timestamp": provenance["source_timestamp"],
        "confidence_class": "low",
        "context_sha256": context["canonical_sha256"],
        "candidate_provenance": provenance,
        "closed_edges": closed,
        "baseline": baseline_summary(baseline),
        "impact": intervention_summary(result, definition),
        "subdistricts": assessments,
        "candidate_affected_population": math.fsum(
            r["candidate_affected_population"] for r in assessments
        ),
        "unobserved_population": math.fsum(
            r["unobserved_population"] for r in assessments
        ),
        "normalization": {
            "exposure_0_100": "100 * candidate-overlapping cell-centre residents / in-scope residents; null unless population coverage is complete.",
            "access_gap_0_100": "100 * connected residents beyond 30 minutes or without a scenario route / connected residents.",
            "road_criticality_0_100": "100 * residents losing all routes / residents with a baseline route.",
        },
        "limitations": [
            "Counts are modelled residents, not flood victims; whole WorldPop cell counts use cell-centre intersection, not building-level exposure.",
            "Intersection imposes a closure assumption, including mapped bridges; it does not establish actual road passability.",
            "Roads outside the candidate footprint remain unchanged by assumption, not because they were observed dry or open.",
            "Geometry errors, permanent water, urban effects and uncalibrated amplitude can change these results.",
            "Accepted FPPS remains null. Fixed 0/50/100 completions are low-confidence Class E scenarios, not accepted event scores.",
        ],
    }
