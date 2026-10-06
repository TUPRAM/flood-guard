"""Bounded Mae Sai service-specific experiments, never accepted event decisions."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any

from .evidence_catalog import canonical_bytes
from .evidence_interventions import select_interventions
from .evidence_population_review import build_capacity_demand
from .evidence_scenarios import allocate_shelter_capacity, calculate_total_access

SERVICES = ("hospital", "primary_care", "pharmacy", "shelter")
SPEED_FACTORS = (0.75, 1.0, 1.25)
SHORTLIST = 2


def _quantile(values: Sequence[tuple[float, float]], fraction: float) -> float | None:
    rows = sorted((value, weight) for value, weight in values if weight > 0)
    total = math.fsum(weight for _, weight in rows)
    if not total:
        return None
    cumulative = 0.0
    for value, weight in rows:
        cumulative += weight
        if cumulative >= total * fraction:
            return round(value, 4)
    return round(rows[-1][0], 4)


def baseline_summary(result: Mapping[str, Any]) -> dict:
    """Preserve mutually exclusive coverage categories and finite-route distribution."""
    coverage = result["coverage_review"]
    finite = [
        (row["normal_access_minutes"], row["total_population"])
        for row in result["node_results"]
        if row["normal_access_minutes"] is not None
    ]
    return {
        "modelled_population": round(result["totals"]["total_population"], 4),
        "unknown_access_population": round(
            coverage["missing_graph_coverage_population"], 4
        ),
        "connected_without_route_population": round(
            coverage["baseline"]["graph_connected_no_modelled_route_population"], 4
        ),
        **{
            f"within_{limit}_minutes_population": round(
                coverage["baseline"]["thresholds"][str(limit)][
                    "modelled_reachable_population"
                ],
                4,
            )
            for limit in (15, 30, 60)
        },
        "median_minutes": _quantile(finite, 0.5),
        "p90_minutes": _quantile(finite, 0.9),
        "max_minutes": max(
            (round(value, 4) for value, weight in finite if weight > 0), default=None
        ),
    }


def intervention_summary(
    result: Mapping[str, Any], definition: Mapping[str, Any]
) -> dict:
    """Report route gains separately from finite-trip delays, including zero effects."""
    times = result["travel_time_summary"]
    deltas = [
        (row["travel_time_delta_minutes"], row["total_population"])
        for row in result["node_results"]
        if row["travel_time_delta_minutes"] is not None
    ]
    return {
        **{
            key: definition[key]
            for key in ("id", "kind", "target_id", "target_label", "selection_method")
        },
        **{
            f"{direction}_{limit}_min_access": round(
                result["totals"][f"people_{direction}_{limit}_min_access"], 4
            )
            for direction in ("gaining", "losing")
            for limit in (15, 30, 60)
        },
        "slower_population": round(times["slower_population"], 4),
        "faster_population": round(times["faster_population"], 4),
        "newly_reachable_population": round(
            times["newly_with_modelled_route_population"], 4
        ),
        "newly_unreachable_population": round(
            times["newly_without_modelled_route_population"], 4
        ),
        "comparable_population": round(times["comparison_population"], 4),
        "mean_travel_time_delta_minutes": round(
            times["population_weighted_mean_delta_minutes"], 4
        )
        if times["population_weighted_mean_delta_minutes"] is not None
        else None,
        "p90_delta_minutes": _quantile(deltas, 0.9),
        "max_delta_minutes": max(
            (round(value, 4) for value, weight in deltas if weight > 0), default=None
        ),
        "net_person_minutes": round(times["net_change_person_minutes"], 4),
    }


def _sites(context: Mapping[str, Any], service: str) -> list[dict]:
    # No inferred shelter membership, no pharmacy-to-hospital substitution.
    return sorted(
        [
            dict(row)
            for row in context["osm_facilities"]
            if row.get("service_type") == service
            and row.get("candidate_destination_eligible") is True
            and row.get("within_routing_context") is True
        ],
        key=lambda row: row["facility_id"],
    )


def _definitions(
    context: Mapping[str, Any], sites: list[dict], baseline: dict
) -> list[dict]:
    selection = select_interventions(
        context["population"], context["edges"], sites, baseline
    )
    names = {
        site["facility_id"]: site.get("name") or site["facility_id"] for site in sites
    }
    definitions = []
    for family, rows in selection["candidates"].items():
        if family not in ("close_edge", "remove_destination", "add_destination"):
            continue
        for rank, row in enumerate(rows[:SHORTLIST], 1):
            target = row.get("edge_id", row.get("facility_id", row.get("node_id")))
            identifier = f"{family}-{rank}"
            change = (
                {"closed_edge_ids": [target]}
                if family == "close_edge"
                else {"removed_facility_ids": [target]}
                if family == "remove_destination"
                else {
                    "added_facilities": [
                        {
                            "facility_id": "hypothetical-" + target,
                            "node_id": target,
                            "snap_distance_m": 0.0,
                        }
                    ]
                }
            )
            definitions.append(
                {
                    "id": identifier,
                    "kind": family,
                    "target_id": target,
                    "target_label": names.get(target, target),
                    "selection_method": selection["selection_reason"][family],
                    "scenario": change,
                }
            )
    return definitions


def _reduced(result: dict) -> dict:
    return {
        key: value
        for key, value in result.items()
        if key not in ("baseline_reachable_pairs", "scenario_reachable_pairs")
    }


def _capacity(context: dict, definition: dict | None) -> dict:
    output = {
        "status": "unavailable",
        "site_id": None,
        "linked_access_intervention_id": None,
        "linked_service": None,
        "linked_variant_id": None,
        "demand_basis": "residential_participation",
        "actual_evacuation_demand": None,
        "actual_available_capacity": None,
        "experiments": [],
        "assumptions": [
            "Residential participation is hypothetical, not flood-affected or observed shelter demand.",
            "The same location as the first hypothetical walking access addition is assigned a separate hypothetical shelter service; healthcare sites are not counted as shelters.",
            "No land ownership, safe entrance, flood safety, activation or actual capacity is established.",
        ],
    }
    if definition is None:
        return output
    site = dict(definition["scenario"]["added_facilities"][0])
    access = calculate_total_access(context["population"], context["edges"], [site])
    output.update(
        status="scenario_only",
        site_id=site["facility_id"],
        linked_access_intervention_id=definition["id"],
    )
    for participation in (0.05, 0.10, 0.25):
        demand = build_capacity_demand(
            context["population"],
            demand_basis="residential_participation",
            participation_fraction=participation,
            assumption_id="finals_residential_participation_v1",
        )
        for places in (50, 100, 200):
            result = allocate_shelter_capacity(
                demand["population_rows"],
                [{**site, "capacity": places}],
                access["baseline_reachable_pairs"],
            )
            output["experiments"].append(
                {
                    "participation_fraction": participation,
                    "places": places,
                    "assumed_demand": demand["known_scenario_demand_population"],
                    "assigned": result["served_population"],
                    "capacity_limited": result["capacity_limited_unmet_population"],
                    "unreachable": result["unreachable_population"],
                    "coverage_excluded": result["excluded_coverage_population"],
                }
            )
    return output


def build_finals_analysis(
    contexts: Mapping[str, dict],
    *,
    scope: dict,
    timeline: list[dict],
    generated_at: str,
) -> tuple[dict, dict]:
    """Compute a fixed shortlist across services and network-speed sensitivities.

    Each mode selects two baseline-demand candidates per family before any
    intervention outcome is evaluated. The shortlist is frozen across speed
    factors. Connector limits/times stay fixed. All results remain scenarios.
    """
    if set(contexts) != {"walking", "modelled_vehicle"}:
        raise ValueError("Both explicit travel modes are required")
    for mode, context in contexts.items():
        if not context.get("canonical_sha256") or not context.get("input_hashes"):
            raise ValueError("Context identity is required")
        if context.get("official_warning") is not False:
            raise ValueError("Finals analysis must be non-operational")
        actual = hashlib.sha256(
            canonical_bytes(
                {
                    key: value
                    for key, value in context.items()
                    if key not in ("canonical_sha256", "generated_at")
                }
            )
        ).hexdigest()
        if actual != context["canonical_sha256"]:
            raise ValueError("Finals context hash does not match its content")
    common_hashes = (
        "osm",
        "worldpop",
        "aoi_geometry",
        "routing_geometry",
        "reporting_geometry",
        "reporting_units",
        "reviewed_junctions",
        "public_origin_records",
    )
    if any(
        contexts["walking"]["input_hashes"].get(key)
        != contexts["modelled_vehicle"]["input_hashes"].get(key)
        for key in common_hashes
    ):
        raise ValueError("Travel modes have different source or reporting identities")
    population_by_mode = [
        {row["population_id"]: row["total_population"] for row in ctx["population"]}
        for ctx in contexts.values()
    ]
    if population_by_mode[0] != population_by_mode[1]:
        raise ValueError("Travel modes must use identical demand cells")
    services, detailed = [], {}
    primary = "hospital" if _sites(contexts["walking"], "hospital") else "primary_care"
    capacity_definition = None
    for service in SERVICES:
        count = len(_sites(contexts["walking"], service))
        item = {
            "id": service,
            "status": "available" if count else "unavailable",
            "facilities": count,
            "reason": "Candidate service locations; event-time operation and entrance suitability unverified."
            if count
            else "No eligible destination of this service type; other services are not substituted.",
            "variants": [],
        }
        for mode, context in sorted(contexts.items()):
            sites = _sites(context, service)
            if not sites:
                continue
            selection_baseline = calculate_total_access(
                context["population"], context["edges"], sites
            )
            definitions = _definitions(context, sites, selection_baseline)
            if mode == "walking" and service == primary:
                capacity_definition = next(
                    (row for row in definitions if row["kind"] == "add_destination"),
                    None,
                )
            for factor in SPEED_FACTORS:
                edges = (
                    context["edges"]
                    if factor == 1
                    else [
                        {**row, "normal_minutes": row["normal_minutes"] / factor}
                        for row in context["edges"]
                    ]
                )
                baseline = (
                    selection_baseline
                    if factor == 1
                    else calculate_total_access(context["population"], edges, sites)
                )
                variant_id = f"{service}-{mode}-{factor:g}"
                variant = {
                    "id": variant_id,
                    "travel_mode": mode,
                    "speed_factor": factor,
                    "context_sha256": context["canonical_sha256"],
                    "baseline": baseline_summary(baseline),
                    "interventions": [],
                }
                full = {
                    "baseline": _reduced(baseline),
                    "definitions": definitions,
                    "interventions": {},
                }
                for definition in definitions:
                    result = calculate_total_access(
                        context["population"],
                        edges,
                        sites,
                        scenario=definition["scenario"],
                        baseline_result=baseline,
                    )
                    variant["interventions"].append(
                        intervention_summary(result, definition)
                    )
                    full["interventions"][definition["id"]] = {
                        key: value
                        for key, value in _reduced(result).items()
                        if key != "node_results"
                    }
                item["variants"].append(variant)
                detailed[variant_id] = full
        services.append(item)
    facilities = []
    for row in contexts["walking"]["osm_facilities"]:
        facilities.append(
            {
                "id": row["facility_id"],
                "name": row.get("name") or row["facility_id"],
                "service_type": row.get("service_type", "unclassified"),
                "geometry_role": row.get("geometry_role", "unreviewed_coordinate"),
                "eligible": bool(row.get("candidate_destination_eligible"))
                and row.get("within_routing_context") is True,
                "event_availability": "unknown",
                "actual_capacity": None,
                "source_url": row.get(
                    "source_url", "https://www.openstreetmap.org/copyright"
                ),
            }
        )
    result = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "status": "scenario_only",
        "question": "How do service-specific access and explicit disruptions change within the Thai part of Mae Sai core?",
        "primary_service": primary,
        "scope": scope,
        "timeline": timeline,
        "services": services,
        "facility_review": facilities,
        "capacity": _capacity(contexts["walking"], capacity_definition),
        "limitations": [
            "This combines population from 2020, 2022 boundaries and an OSM snapshot acquired in 2026; it is not a reconstruction of event-day access.",
            "Primary care, hospital care, pharmacies and shelters are distinct services. No available service substitutes for an unavailable one.",
            "Walking uses an assumed 5 km/h on eligible network segments; vehicle scenarios use undirected road-class speeds. Event passability, safe connectors and turn restrictions are unverified.",
            "Network speeds are varied by 0.75/1/1.25; connector times remain 5 km/h. These are sensitivity cases, not demographic mobility estimates.",
            "Two baseline-demand candidates per intervention family are fixed before scenario evaluation; this is not an exhaustive optimization or a site recommendation.",
            "Accepted flood-affected population, FPPS, action class, actual shelter capacity/demand and age equity remain unavailable.",
        ],
    }
    if result["capacity"]["status"] == "scenario_only":
        result["capacity"].update(
            linked_service=primary, linked_variant_id=f"{primary}-walking-1"
        )
    result["analysis_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    return result, detailed
