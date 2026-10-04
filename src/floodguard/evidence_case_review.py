"""Explicit, source-bound destination exclusions for study-case scenarios."""

from __future__ import annotations

from copy import deepcopy

from shapely.geometry import shape


def apply_destination_review(context: dict, review: dict) -> dict:
    """Apply reviewed exclusions without merging coordinates or claiming entrances.

    Duplicate exclusions must prove point-in-site containment. Other exclusions
    retain the original mapped service and explain why it is unsuitable for this
    comparison. Unknown event availability and capacities are never filled here.
    """
    if review["osm_sha256"] != context["input_hashes"]["osm"]:
        raise ValueError("Destination review uses another OSM snapshot")
    result = deepcopy(context)
    sites = {r["facility_id"]: r for r in result["osm_facilities"]}
    seen = set()
    for row in review["exclusions"]:
        identifier = row["facility_id"]
        if identifier in seen or identifier not in sites or not row.get("reason") or not row.get("source_url"):
            raise ValueError("Invalid or duplicate destination exclusion")
        seen.add(identifier)
        site = sites[identifier]
        if row.get("duplicate_of"):
            parent = sites.get(row["duplicate_of"])
            if not parent or not shape(parent["source_geometry"]).covers(shape(site["source_geometry"])):
                raise ValueError("Duplicate point is not contained in its reviewed site")
        site["candidate_destination_eligible"] = False
        site["identity_review_status"] = row["reason"]
    if any(row.get("duplicate_of") in seen for row in review["exclusions"]):
        raise ValueError("Duplicate representative is also excluded")
    return result
