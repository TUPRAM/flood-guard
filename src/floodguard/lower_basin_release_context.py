"""Versioned lower Chao routing context with fixed demand and source review.

This module selects candidate routing geometry only. It never establishes an
event flood, road closure, operating hospital or accepted access result.
"""

from __future__ import annotations

import copy
import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

from floodguard.evidence_catalog import canonical_bytes

AOI_IDS = frozenset({"aoi-05_chao_phraya_bang_ban_sena", "aoi-06_chao_phraya_rangsit"})
POLICY_VERSION = "lower_basin_10km_epsg32647_v1"
REVIEW_METHOD = "contained_point_matching_name_or_wikidata_v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROJECT = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
_UNPROJECT = Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True).transform


class LowerBasinContextError(ValueError):
    """Raised when a routing context would change fixed demand or source identity."""


def select_lower_basin_context(
    *,
    aoi_id: str,
    demand_geometry: Mapping[str, Any],
    reporting_geometry: Mapping[str, Any],
    aoi_sha256: str,
    reporting_units_sha256: str,
) -> dict[str, Any]:
    """Return a full 10 km routing buffer and unchanged demand/reporting shapes.

    `builder_reporting_geometry` is intentionally null: the current context
    builder clips both routes and demand when that argument is supplied.
    Reporting assignment must instead be applied to the fixed AOI population
    after extraction, with `bind_fixed_demand_roster` checking the identity.
    """

    if aoi_id not in AOI_IDS:
        raise LowerBasinContextError("10 km policy is limited to AOI-05/06")
    _sha(aoi_sha256, "AOI hash")
    _sha(reporting_units_sha256, "reporting-units hash")
    demand = _polygon(demand_geometry, "demand")
    reporting = _polygon(reporting_geometry, "reporting")
    if not reporting.covers(demand):
        raise LowerBasinContextError(
            "reporting units do not cover the fixed demand AOI"
        )
    projected = transform(_PROJECT, demand)
    routing = transform(_UNPROJECT, projected.buffer(10_000))
    if not routing.is_valid or not routing.covers(demand):
        raise LowerBasinContextError("10 km routing buffer is invalid")
    output = {
        "schema_version": "floodguard.lower_basin_context_selection.v1",
        "policy_version": POLICY_VERSION,
        "aoi_id": aoi_id,
        "aoi_sha256": aoi_sha256,
        "reporting_units_sha256": reporting_units_sha256,
        "routing_crs": "EPSG:4326",
        "buffer_calculation_crs": "EPSG:32647",
        "routing_buffer_m": 10_000,
        "demand_geometry": copy.deepcopy(dict(demand_geometry)),
        "reporting_geometry": copy.deepcopy(dict(reporting_geometry)),
        "routing_geometry": mapping(routing),
        "builder_reporting_geometry": None,
        "demand_geometry_sha256": _digest(demand_geometry),
        "reporting_geometry_sha256": _digest(reporting_geometry),
        "routing_geometry_sha256": _digest(mapping(routing)),
        "demand_area_km2": projected.area / 1_000_000,
        "routing_area_km2": transform(_PROJECT, routing).area / 1_000_000,
        "status": "candidate_routing_context_only",
        "event_flood_layer": None,
        "official_warning": False,
        "operating_hospital_verified": False,
    }
    output["selection_sha256"] = _digest(output)
    return output


def bind_fixed_demand_roster(
    baseline: Sequence[Mapping[str, Any]], expanded: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], str]:
    """Copy expanded demand with identical cells and baseline reporting IDs.

    Node IDs, snap states and routes may change with context. Resident counts,
    geographic cell centres and reporting assignments may not.
    """

    old = _unique_population(baseline, "baseline")
    new = _unique_population(expanded, "expanded")
    if old.keys() != new.keys():
        raise LowerBasinContextError("expanded context changed fixed demand cell IDs")
    fixed = []
    roster = []
    for identifier in sorted(old):
        original = old[identifier]
        current = copy.deepcopy(new[identifier])
        for field in ("longitude", "latitude", "total_population"):
            original_value = (
                _finite_nonnegative(original[field], field)
                if field == "total_population"
                else _finite(original[field], field)
            )
            current_value = (
                _finite_nonnegative(current[field], field)
                if field == "total_population"
                else _finite(current[field], field)
            )
            if not math.isclose(original_value, current_value, rel_tol=0, abs_tol=1e-9):
                raise LowerBasinContextError(
                    f"expanded context changed demand cell {identifier}"
                )
        unit_id = original.get("subdistrict_id")
        if not isinstance(unit_id, str) or not unit_id:
            raise LowerBasinContextError("baseline reporting assignment is missing")
        current["subdistrict_id"] = unit_id
        fixed.append(current)
        roster.append(
            {
                "population_id": identifier,
                "longitude": original["longitude"],
                "latitude": original["latitude"],
                "total_population": original["total_population"],
                "subdistrict_id": unit_id,
            }
        )
    return fixed, _digest(roster)


def review_hospital_source_duplicates(context: Mapping[str, Any]) -> dict[str, Any]:
    """Find only contained same-name/Wikidata OSM point/site duplicates."""

    osm_sha = _sha(context["input_hashes"]["osm"], "OSM hash")
    hospitals = [
        row
        for row in context["osm_facilities"]
        if row.get("service_type") == "hospital"
    ]
    ids = [row.get("facility_id") for row in hospitals]
    if any(
        not isinstance(identifier, str) or not identifier for identifier in ids
    ) or len(ids) != len(set(ids)):
        raise LowerBasinContextError(
            "hospital source-object IDs are missing or duplicated"
        )
    exclusions = []
    ambiguous = []
    for point in hospitals:
        if point.get("source_geometry_type") != "Point":
            continue
        point_geometry = shape(point["source_geometry"])
        if point_geometry.geom_type != "Point" or not point_geometry.is_valid:
            raise LowerBasinContextError("hospital point source geometry is invalid")
        parents = []
        for site in hospitals:
            if site.get("source_geometry_type") == "Point" or site is point:
                continue
            site_geometry = shape(site["source_geometry"])
            if (
                site_geometry.geom_type not in {"Polygon", "MultiPolygon"}
                or not site_geometry.is_valid
            ):
                raise LowerBasinContextError("hospital site source geometry is invalid")
            if not site_geometry.covers(point_geometry):
                continue
            shared_wikidata = bool(
                point.get("wikidata") and point["wikidata"] == site.get("wikidata")
            )
            point_name = " ".join(str(point.get("name", "")).split()).casefold()
            site_name = " ".join(str(site.get("name", "")).split()).casefold()
            same_name = (
                point_name not in {"", "unnamed osm candidate"}
                and point_name == site_name
            )
            if shared_wikidata or same_name:
                parents.append(
                    (
                        site,
                        "shared_wikidata_and_containment"
                        if shared_wikidata
                        else "same_name_and_containment",
                    )
                )
        if len(parents) == 1:
            parent, reason = parents[0]
            exclusions.append(
                {
                    "facility_id": point["facility_id"],
                    "duplicate_of": parent["facility_id"],
                    "reason": reason,
                    "source_url": point["source_url"],
                    "parent_source_url": parent["source_url"],
                }
            )
        elif len(parents) > 1:
            ambiguous.append(
                {
                    "facility_id": point["facility_id"],
                    "possible_parents": sorted(
                        parent["facility_id"] for parent, _ in parents
                    ),
                }
            )
    return {
        "osm_sha256": osm_sha,
        "method": REVIEW_METHOD,
        "exclusions": sorted(exclusions, key=lambda row: row["facility_id"]),
        "ambiguous": sorted(ambiguous, key=lambda row: row["facility_id"]),
        "identity_scope": "OSM source-object duplication only; operation and entrance unverified",
    }


def validate_documented_hospital_review(
    context: Mapping[str, Any], documented_review: Mapping[str, Any]
) -> set[str]:
    """Require exact source-backed review before excluding candidate objects."""

    derived = review_hospital_source_duplicates(context)
    if dict(documented_review) != derived:
        raise LowerBasinContextError("documented hospital source-object review changed")
    return {row["facility_id"] for row in derived["exclusions"]}


def _polygon(value: Mapping[str, Any], label: str):
    try:
        geometry = shape(value)
    except (TypeError, ValueError) as error:
        raise LowerBasinContextError(f"{label} geometry is invalid") from error
    if (
        geometry.geom_type not in {"Polygon", "MultiPolygon"}
        or geometry.is_empty
        or not geometry.is_valid
    ):
        raise LowerBasinContextError(f"{label} must be a valid polygon")
    minimum_x, minimum_y, maximum_x, maximum_y = geometry.bounds
    if not (
        -180 <= minimum_x < maximum_x <= 180 and -90 <= minimum_y < maximum_y <= 90
    ):
        raise LowerBasinContextError(f"{label} must be WGS84 longitude/latitude")
    return geometry


def _unique_population(
    rows: Sequence[Mapping[str, Any]], label: str
) -> dict[str, Mapping[str, Any]]:
    values = {}
    for row in rows:
        identifier = row.get("population_id")
        if not isinstance(identifier, str) or not identifier or identifier in values:
            raise LowerBasinContextError(
                f"{label} demand IDs are missing or duplicated"
            )
        values[identifier] = row
    if not values:
        raise LowerBasinContextError(f"{label} demand roster is empty")
    return values


def _finite(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise LowerBasinContextError(f"{label} must be finite")
    return float(value)


def _finite_nonnegative(value: object, label: str) -> float:
    number = _finite(value, label)
    if number < 0:
        raise LowerBasinContextError(f"{label} must be nonnegative")
    return number


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise LowerBasinContextError(f"{label} must be SHA-256")
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
