"""Fail-closed public-evidence intake for facility roles, entrances and capacity."""

from __future__ import annotations

import math
from datetime import date
from urllib.parse import urlsplit


def validate_facility_verification(record: dict, *, event_date: str) -> dict:
    """Normalize a review; identity, historical availability and capacity differ.

    Imagery or OSM alone cannot verify shelter designation or event activation.
    Unknown capacity remains null and blocks allocation, not a verified route.
    Personal coordinator/contact fields are rejected rather than exported.
    """
    allowed = {
        "facility_id",
        "verified_role",
        "coordinates",
        "entrance",
        "capacity",
        "effective_from",
        "effective_to",
        "verification_method",
        "verification_status",
        "evidence",
        "event_activation_verified",
        "capacity_verified",
    }
    if set(record) - allowed:
        raise ValueError(
            "Unexpected facility fields; personal contact fields are not accepted"
        )
    if (
        not isinstance(record.get("facility_id"), str)
        or not record["facility_id"].strip()
    ):
        raise ValueError("Stable facility_id is required")
    output = {key: record.get(key) for key in allowed}
    output["verification_status"] = record.get("verification_status", "unverified")
    output["evidence"] = record.get("evidence", [])
    for field in ("event_activation_verified", "capacity_verified"):
        value = record.get(field, False)
        if not isinstance(value, bool):
            raise TypeError(f"{field} must be boolean")
        output[field] = value
    if output["verification_status"] not in {"unverified", "verified", "rejected"}:
        raise ValueError("Invalid verification status")
    if output["verified_role"] not in {
        None,
        "shelter",
        "hospital",
        "primary_care",
        "pharmacy",
    }:
        raise ValueError("Invalid facility role")
    for key in ("coordinates", "entrance"):
        point = output[key]
        if point is not None and (
            not isinstance(point, list)
            or len(point) != 2
            or any(
                isinstance(v, bool)
                or not isinstance(v, (float, int))
                or not math.isfinite(v)
                for v in point
            )
            or not -180 <= point[0] <= 180
            or not -90 <= point[1] <= 90
        ):
            raise ValueError(f"{key} must be nullable WGS84 longitude/latitude")
    capacity = output["capacity"]
    if capacity is not None and (
        isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 0
    ):
        raise ValueError("Capacity must be a nonnegative integer or null")
    event = date.fromisoformat(event_date)
    start = (
        date.fromisoformat(output["effective_from"])
        if output["effective_from"]
        else None
    )
    end = date.fromisoformat(output["effective_to"]) if output["effective_to"] else None
    if start and end and start > end:
        raise ValueError("Inverted facility validity interval")
    for item in output["evidence"]:
        if set(item) != {"url", "sha256", "supports", "observation_date"}:
            raise ValueError("Evidence must bind URL, checksum, claim and date")
        if (
            urlsplit(item["url"]).scheme != "https"
            or not urlsplit(item["url"]).hostname
        ):
            raise ValueError("Facility evidence must use a public HTTPS URL")
        if len(item["sha256"]) != 64 or any(
            c not in "0123456789abcdef" for c in item["sha256"]
        ):
            raise ValueError("Evidence checksum is invalid")
        date.fromisoformat(item["observation_date"])
        if item["supports"] not in {
            "role",
            "location",
            "entrance",
            "activation",
            "capacity",
        }:
            raise ValueError("Unknown evidence claim")
    claims = {item["supports"] for item in output["evidence"]}
    if output["verification_status"] == "verified":
        if (
            not output["verified_role"]
            or output["coordinates"] is None
            or output["entrance"] is None
            or not start
            or not end
            or not output["verification_method"]
            or not {"role", "location", "entrance"} <= claims
        ):
            raise ValueError(
                "Verified facility needs dated role, location and entrance evidence"
            )
        if output["verified_role"] == "shelter" and output["verification_method"] in {
            "osm",
            "imagery",
            "theos2",
        }:
            raise ValueError("Imagery/OSM alone cannot establish a shelter role")
    if output["event_activation_verified"] and "activation" not in claims:
        raise ValueError("Activation needs its own dated evidence")
    if output["capacity_verified"] and (capacity is None or "capacity" not in claims):
        raise ValueError("Capacity needs its own numeric value and dated evidence")
    available = (
        output["verification_status"] == "verified"
        and bool(start and end and start <= event <= end)
        and output["event_activation_verified"]
    )
    output["shelter_access_eligible"] = (
        available and output["verified_role"] == "shelter"
    )
    output["event_available_capacity"] = (
        capacity
        if output["shelter_access_eligible"] and output["capacity_verified"]
        else None
    )
    output["official_warning"] = False
    output["event_date"] = event_date
    return output
