"""Concise, explicitly conditional briefs from traceable evidence packages.

Reporting units describe only the intersected study area. Modelled residential
population and access experiments never become observed flood exposure or FPPS.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from shapely.geometry import Point, shape
from shapely.strtree import STRtree


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("Brief quantities must be finite and nonnegative")
    return number


def _sum(rows: Sequence[Mapping[str, Any]], predicate=lambda row: True) -> float:
    return round(
        math.fsum(float(row["total_population"]) for row in rows if predicate(row)), 2
    )


def _access_counts(rows: Sequence[Mapping[str, Any]]) -> dict:
    connected = [row for row in rows if row.get("snap_status") == "connected"]
    return {
        "modelled_population": _sum(rows),
        "unknown_access_population": _sum(
            rows, lambda row: row.get("snap_status") != "connected"
        ),
        "connected_without_route_population": _sum(
            connected, lambda row: row.get("normal_access_minutes") is None
        ),
        "over_30_minutes_population": _sum(
            connected,
            lambda row: (
                row.get("normal_access_minutes") is not None
                and row["normal_access_minutes"] > 30
            ),
        ),
        "within_30_minutes_population": _sum(
            connected,
            lambda row: (
                row.get("normal_access_minutes") is not None
                and row["normal_access_minutes"] <= 30
            ),
        ),
    }


def _intervention(
    key: str, result: Mapping[str, Any], rows: Sequence[Mapping[str, Any]] | None = None
) -> dict:
    selected = list(result.get("node_results", [])) if rows is None else list(rows)
    lost = _sum(selected, lambda row: bool(row.get("loses_30_min_access")))
    gained = _sum(selected, lambda row: bool(row.get("gains_30_min_access")))
    comparable = [
        row
        for row in selected
        if row.get("snap_status") == "connected"
        and row.get("normal_access_minutes") is not None
        and row.get("scenario_access_minutes") is not None
    ]
    slower = _sum(
        comparable,
        lambda row: (
            row["scenario_access_minutes"] > row["normal_access_minutes"] + 1e-6
        ),
    )
    faster = _sum(
        comparable,
        lambda row: (
            row["scenario_access_minutes"] < row["normal_access_minutes"] - 1e-6
        ),
    )
    delta = math.fsum(
        float(row["total_population"])
        * (row["scenario_access_minutes"] - row["normal_access_minutes"])
        for row in comparable
    )
    population = math.fsum(float(row["total_population"]) for row in comparable)
    return {
        "id": key,
        "scenario_id": f"access-{key}",
        "kind": key,
        "gaining_30_min_access": gained,
        "losing_30_min_access": lost,
        "slower_population": slower,
        "faster_population": faster,
        "comparable_population": round(population, 2),
        "mean_travel_time_delta_minutes": round(delta / population, 4)
        if population
        else None,
        "result": "threshold_change"
        if any(
            row["total_population"] > 0
            and (row.get("gains_30_min_access") or row.get("loses_30_min_access"))
            for row in selected
        )
        else "travel_time_only"
        if any(
            row["total_population"] > 0
            and abs(row["scenario_access_minutes"] - row["normal_access_minutes"])
            > 1e-6
            for row in comparable
        )
        else "no_measured_change",
        "observed": False,
    }


def _reporting_rows(
    aoi_id: str,
    context: Mapping[str, Any] | None,
    details: Mapping[str, Any],
    review: Mapping[str, Any],
    features: Mapping[str, Any],
) -> dict:
    crosswalk = next(
        (
            row
            for row in review.get("crosswalk", {}).get("aois", [])
            if row["aoi_id"] == aoi_id
        ),
        None,
    )
    source = review.get("boundary_source", {})
    output = {
        "status": "unavailable",
        "source_url": source.get("source_url"),
        "reference_date": review.get("source_timestamp"),
        "coverage_fraction": None,
        "unassigned_modelled_population": None,
        "ambiguous_population_cells": 0,
        "units": [],
        "scope": "Only the intersection of each subdistrict with this AOI is reported; full-subdistrict totals and rankings are not inferred.",
    }
    if not crosswalk or source.get("public_derivatives") is not True:
        return output
    unit_info = {row["adm3_pcode"]: row for row in crosswalk["units"]}
    if len(unit_info) != len(crosswalk["units"]):
        raise ValueError("Duplicate reporting crosswalk code")
    geometries = {}
    for feature in features.get("features", []):
        props = feature.get("properties") or {}
        code = props.get("adm3_pcode", props.get("ADM3_PCODE"))
        if code in unit_info:
            if code in geometries:
                raise ValueError("Duplicate reporting-unit code")
            geometries[code] = shape(feature["geometry"])
    if set(geometries) != set(unit_info):
        raise ValueError("Reporting geometry and AOI crosswalk disagree")
    codes = sorted(geometries)
    tree = STRtree([geometries[code] for code in codes])
    baseline = (
        details.get("access_scenarios", {}).get("baseline", {}).get("node_results", [])
    )
    has_baseline = "node_results" in details.get("access_scenarios", {}).get(
        "baseline", {}
    )
    rows_by_id = {row["population_id"]: row for row in baseline}
    if len(rows_by_id) != len(baseline):
        raise ValueError("Duplicate modelled population identifier")
    population = (
        list(context.get("population", []))
        if context is not None and has_baseline
        else []
    )
    if len({row["population_id"] for row in population}) != len(population):
        raise ValueError("Duplicate population cell in reporting join")
    if context is not None and has_baseline:
        if set(rows_by_id) != {row["population_id"] for row in population}:
            raise ValueError("Context and baseline population identifiers disagree")
        if any(
            not math.isclose(
                float(row["total_population"]),
                float(rows_by_id[row["population_id"]]["total_population"]),
                rel_tol=1e-10,
                abs_tol=1e-9,
            )
            for row in population
        ):
            raise ValueError("Context and baseline population quantities disagree")
    groups: dict[str, list[dict]] = {code: [] for code in codes}
    unmatched = []
    ambiguous = 0
    for cell in population:
        _number(cell["total_population"])
        point = Point(float(cell["longitude"]), float(cell["latitude"]))
        hits = [
            codes[int(index)]
            for index in tree.query(point)
            if geometries[codes[int(index)]].covers(point)
        ]
        if len(hits) != 1:
            unmatched.append(cell)
            ambiguous += int(len(hits) > 1)
            continue
        if cell["population_id"] not in rows_by_id:
            raise ValueError("Population cell missing from baseline access result")
        groups[hits[0]].append(rows_by_id[cell["population_id"]])
    for code in codes:
        info = unit_info[code]
        population_ids = {row["population_id"] for row in groups[code]}
        interventions = [
            _intervention(
                key,
                value,
                [
                    row
                    for row in value.get("node_results", [])
                    if row["population_id"] in population_ids
                ],
            )
            for key, value in sorted(details.get("access_scenarios", {}).items())
            if key != "baseline" and "node_results" in value
        ]
        output["units"].append(
            {
                "id": code,
                "name": info.get("name") or code,
                "name_th": info.get("name_th") or info.get("name") or code,
                "scope": info["scope"],
                "unit_coverage_fraction": info["unit_coverage_fraction"],
                "intersection_area_km2": info["intersection_area_km2"],
                "population_context": _access_counts(groups[code])
                if context is not None and has_baseline
                else None,
                "affected_population": None,
                "fpps": None,
                "action_class": None,
                "interventions": interventions,
            }
        )
    output.update(
        status="available",
        coverage_fraction=crosswalk["coverage_fraction"],
        unassigned_modelled_population=_sum(unmatched)
        if context is not None and has_baseline
        else None,
        ambiguous_population_cells=ambiguous,
    )
    return output


def build_decision_brief(
    *,
    aoi_id: str,
    event_id: str,
    generated_at: str,
    context: Mapping[str, Any] | None,
    details: Mapping[str, Any],
    reporting_review: Mapping[str, Any] | None = None,
    reporting_units: Mapping[str, Any] | None = None,
    event_evidence: Mapping[str, Any] | None = None,
    population_review: Mapping[str, Any] | None = None,
) -> dict:
    """Project an explainable brief without inventing event impact or priority.

    Boundary/centroid joins require unique official reporting codes. Cells with
    no unique unit remain unassigned. Scenario comparisons and their population
    denominators stay separate from event observations and demographic equity.
    """
    baseline = details.get("access_scenarios", {}).get("baseline", {})
    rows = baseline.get("node_results", [])
    access = _access_counts(rows) if context and baseline else None
    reporting = _reporting_rows(
        aoi_id, context, details, reporting_review or {}, reporting_units or {}
    )
    interventions = [
        _intervention(key, value)
        for key, value in sorted(details.get("access_scenarios", {}).items())
        if key != "baseline" and "node_results" in value
    ]
    selection = details.get("stress_selection", {})
    for intervention in interventions:
        intervention["selection_method"] = selection.get("selection_reason", {}).get(
            intervention["kind"],
            "Deterministic model-based selection; inspect the scenario assumptions.",
        )
    coverage = context.get("coverage", {}) if context else {}
    population = (population_review or {}).get("population", {})
    destinations = (
        (population_review or {})
        .get("destinations", {})
        .get("aois", {})
        .get(aoi_id, {})
    )
    connections = context.get("connectivity_review", {}) if context else {}
    notes = [
        {
            "topic": "population",
            "status": "context_only" if population else "unavailable",
            "summary": f"{population.get('arithmetic_mismatches', 0)} source arithmetic mismatches remain recorded. Numerical children/working-age definitions and local demographic joins are not accepted. Chiang Rai 2024 age data remain missing; Pathum Thani age bands support provincial context only."
            if population
            else "Population-group definitions and arithmetic have not been reviewed in this package.",
            "source_urls": ["https://chiangrai.gdcatalog.go.th/dataset/dataset_50_01"],
        },
        {
            "topic": "destinations",
            "status": "review_only" if destinations else "unavailable",
            "summary": f"This AOI: {destinations.get('supported_name_address_matches', 0)} supported public name/address matches and {destinations.get('dated_venue_activity_reports', 0)} dated venue-activity reports. Neither establishes a verified routing point, continuous event operation or available capacity."
            if destinations
            else "Destination identities have not been reviewed for this AOI.",
            "source_urls": [],
        },
        {
            "topic": "connections",
            "status": "review_only" if connections else "unavailable",
            "summary": f"{connections.get('shared_coordinate_grade_split_count', 0)} coincident road-grade splits; {connections.get('possible_endpoint_transition_count', 0)} possible endpoint transitions require original-node/grade review. No new crossing has been inferred from proximity."
            if connections
            else "Road-grade connections have not been reviewed for this AOI.",
            "source_urls": ["https://www.openstreetmap.org/copyright"],
        },
    ]
    products = {row["id"]: row for row in (event_evidence or {}).get("products", [])}
    for venue in (
        (population_review or {})
        .get("destinations", {})
        .get("documentary_venue_evidence", [])
    ):
        if aoi_id in venue["aois"]:
            notes.append(
                {
                    "topic": "dated_venue_report",
                    "status": "point_link_unresolved",
                    "summary": venue["source_date"]
                    + ": "
                    + venue["summary"]
                    + " Reported use does not establish routing coordinates or available capacity.",
                    "source_urls": [venue["source_url"]],
                }
            )
    for row in (event_evidence or {}).get("aois", []):
        if row["aoi_id"] != aoi_id or row["event_id"] != event_id:
            continue
        product = products.get(row["product_id"], {})
        notes.insert(
            0,
            {
                "topic": "flood_evidence",
                "status": row["event_context_status"],
                "summary": (product.get("title") or "No reviewed dated flood extent")
                + ": "
                + "; ".join(row["blocking_reasons"])
                + ". "
                + " ".join(product.get("review_notes", [])),
                "source_urls": [product["source_url"]]
                if product.get("source_url")
                else [],
            },
        )
    capacity = []
    for result in [
        *details.get("capacity_scenarios", []),
        *details.get("capacity_participation_sensitivity", []),
    ]:
        demand = result.get("demand_assumptions", {})
        capacity.append(
            {
                "id": result["scenario_id"],
                "title": result.get("title", result["scenario_id"]),
                "participation_fraction": demand.get("participation_fraction"),
                "residential_population": demand.get("total_residential_population"),
                "demand_basis": demand.get("demand_basis"),
                "actual_evacuation_demand": None,
                "actual_available_capacity": None,
                "unknown_capacity": result.get(
                    "unmet_population_with_unknown_capacity"
                ),
                "assumed_demand": result.get("total_population"),
                "assigned": result.get("served_population"),
                "capacity_limited": result.get("capacity_limited_unmet_population"),
                "unreachable": result.get("unreachable_population"),
                "coverage_excluded": result.get("excluded_coverage_population"),
            }
        )
    return {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "aoi_id": aoi_id,
        "event_id": event_id,
        "status": "scenario_only" if context and baseline else "coverage_only",
        "priority": {
            "status": "unavailable",
            "fpps": None,
            "action_class": None,
            "reason": "Event-matched evidence and complete score inputs have not been accepted. Scenario comparisons do not establish response priority.",
        },
        "affected_population": None,
        "population_reference_year": 2020 if context else None,
        "population_role": "modelled_residential_context",
        "access": access,
        "reporting": reporting,
        "interventions": interventions,
        "evidence_notes": notes,
        "capacity_experiments": capacity,
        "capacity_status": "assumed_demand_and_capacity_only",
        "demographic_equity_status": "unavailable",
        "coverage": {
            "connected_components": coverage.get("connected_components"),
            "connected_destinations": sum(
                row.get("snap_status") == "connected"
                for row in baseline.get("facility_snap_review", [])
            )
            if baseline
            else None,
            "candidate_destinations": len(baseline.get("facility_snap_review", []))
            if baseline
            else None,
        },
        "drivers": [
            "A dated flood footprint and appropriate exposure calculation are required before affected population can be reported.",
            "Historical roads and candidate destinations support modelled access comparisons; road condition and event-time destination operation remain unverified.",
            "Missing graph coverage is reported separately from modelled lack of access; it is not observed isolation.",
        ],
        "next_actions": [
            {
                "id": "event_reference",
                "order": 1,
                "action": "Verify dated flood coverage",
                "reason": "Tie public flood evidence to the event, footprint and reporting units before making exposure or priority claims.",
            },
            {
                "id": "access_review",
                "order": 2,
                "action": "Review consequential connections and destinations",
                "reason": "Use the intervention comparisons and connection review to target verification; modelled changes are not observed closures.",
            },
            {
                "id": "demand_capacity",
                "order": 3,
                "action": "Confirm population groups and capacity assumptions",
                "reason": "Use explicit participation scenarios until affected demand, age definitions and available shelter capacity are supported.",
            },
        ],
        "limitations": [
            "No accepted FPPS, action class, flood-affected population or demographic equity result is claimed.",
            "WorldPop 2020 residential estimates are not an event-year census, evacuation count or flood exposure measure.",
            "Subdistrict quantities describe the AOI intersection using a historical boundary vintage; boundaries at the event date remain unverified.",
            "Scenario experiments are independent; they do not describe simultaneous observed disruptions.",
        ],
    }
