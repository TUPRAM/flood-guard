"""Explicit publication projection and integrity checks for the finals experiment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .evidence_catalog import (
    assert_public_safe,
    canonical_bytes,
    safe_asset_path,
    sha256_file,
)

SITE_EXTRA_KEYS = {
    "connectors",
    "connector_count",
    "connector_review_id",
    "service_type",
    "geometry_role",
    "source_url",
    "source_geometry_type",
    "location_review_status",
    "identity_review_status",
    "current_operation_status",
    "event_operation_status",
    "event_available_capacity",
    "source_record_ids",
    "possible_duplicate_source_ids",
    "osm_healthcare",
    "wikidata",
    "entrance_candidates",
    "source_geometry",
}
ORIGIN_KEYS = {
    "origin_id",
    "public_place_type",
    "evidence_role",
    "name",
    "source_url",
    "geometry_role",
    "source_geometry_type",
    "longitude",
    "latitude",
    "node_id",
    "snap_distance_m",
    "within_routing_context",
    "within_demand_scope",
    "location_review_status",
    "possible_duplicate_source_ids",
    "connector_walkability",
}


def load_finals(directory: Path, *, aoi_sha256: str) -> tuple[dict, dict]:
    """Reject corrupt, stale, unsafe or geographically mismatched local finals inputs."""
    receipt = json.loads((directory / "build_receipt.json").read_text(encoding="utf-8"))
    if receipt["aoi_sha256"] != aoi_sha256:
        raise ValueError("Finals AOI hash differs")
    builder_name = receipt.get("builder_name", "build_mae_sai_finals.py")
    if builder_name not in {"build_mae_sai_finals.py", "build_study_area_finals.py"}:
        raise ValueError("Unknown finals builder")
    builder = Path(__file__).resolve().parents[2] / "scripts" / builder_name
    if receipt.get("builder_sha256") != sha256_file(builder):
        raise ValueError(
            "Finals builder identity is missing or changed; recompute the experiments"
        )
    for relative, expected in receipt["files"].items():
        if sha256_file(safe_asset_path(directory, relative)) != expected:
            raise ValueError("Finals input checksum changed: " + relative)
    for name, expected in receipt["implementation"].items():
        if (
            Path(name).name != name
            or sha256_file(Path(__file__).parent / name) != expected
        ):
            raise ValueError("Finals implementation changed; recompute the experiments")
    analysis = json.loads((directory / "analysis.json").read_text(encoding="utf-8"))
    if analysis.get("generated_at") != receipt.get("generated_at"):
        raise ValueError("Finals analysis generation time differs from build receipt")
    if "case_identity" in analysis and analysis["case_identity"].get("aoi_sha256") != aoi_sha256:
        raise ValueError("Finals analysis AOI hash differs")
    if sha256_file(directory / "analysis.json") != receipt["analysis_sha256"]:
        raise ValueError("Finals analysis file differs from receipt")
    verify_finals_analysis(analysis)
    contexts = {}
    for mode in ("walking", "modelled_vehicle"):
        context = json.loads(
            (directory / "contexts" / mode / "context_inputs.json").read_text(
                encoding="utf-8"
            )
        )
        actual = hashlib.sha256(
            canonical_bytes(
                {
                    key: value
                    for key, value in context.items()
                    if key not in ("canonical_sha256", "generated_at")
                }
            )
        ).hexdigest()
        if (
            actual != context["canonical_sha256"]
            or actual != receipt["context_hashes"][mode]
        ):
            raise ValueError("Finals context identity differs")
        contexts[mode] = context
    return analysis, contexts


def verify_finals_analysis(analysis: dict) -> None:
    """Check identity, service isolation, fixed shortlist and explicit capacity linkage."""
    from math import isclose, isfinite

    digest = hashlib.sha256(
        canonical_bytes(
            {key: value for key, value in analysis.items() if key != "analysis_sha256"}
        )
    ).hexdigest()
    if digest != analysis.get("analysis_sha256"):
        raise ValueError("Finals analysis identity differs")
    assert_public_safe(analysis)
    identity = analysis.get("case_identity")
    if identity and (identity.get("flood_basis") == "unvalidated_satellite_candidate") != bool(analysis.get("flood_scenarios")):
        raise ValueError("Case flood identity differs from available scenarios")
    scope = analysis["scope"]
    if not isclose(
        scope["study_population"],
        scope["in_scope_population"] + scope["excluded_population"],
        abs_tol=1e-6,
    ):
        raise ValueError("Finals jurisdiction population does not conserve demand")
    services = {row["id"]: row for row in analysis["services"]}
    if len(services) != len(analysis["services"]) or set(services) != {
        "hospital",
        "primary_care",
        "pharmacy",
        "shelter",
    }:
        raise ValueError("Finals services must be separate and unique")
    variants, variant_services = {}, {}
    for service in services.values():
        if service["status"] == "unavailable" and (
            service["facilities"] or service["variants"]
        ):
            raise ValueError("Unavailable service contains computed access")
        shortlists = {}
        for variant in service["variants"]:
            if variant["id"] in variants:
                raise ValueError("Duplicate finals variant")
            variants[variant["id"]] = variant
            variant_services[variant["id"]] = service["id"]
            if not isclose(
                variant["baseline"]["modelled_population"],
                scope["in_scope_population"],
                abs_tol=1e-3,
            ):
                raise ValueError("Finals variant uses another population")
            shortlist = [
                (row["id"], row["kind"], row["target_id"])
                for row in variant["interventions"]
            ]
            mode = variant["travel_mode"]
            if mode in shortlists and shortlists[mode] != shortlist:
                raise ValueError("Finals sensitivity changed the candidate shortlist")
            shortlists[mode] = shortlist
    capacity = analysis["capacity"]
    if (
        capacity["actual_evacuation_demand"] is not None
        or capacity["actual_available_capacity"] is not None
    ):
        raise ValueError("Hypothetical capacity promoted to actual")
    if capacity["status"] == "scenario_only":
        variant = variants.get(capacity["linked_variant_id"])
        candidate = (
            next(
                (
                    row
                    for row in variant["interventions"]
                    if row["id"] == capacity["linked_access_intervention_id"]
                ),
                None,
            )
            if variant
            else None
        )
        if (
            not candidate
            or candidate["kind"] != "add_destination"
            or capacity["site_id"] != "hypothetical-" + candidate["target_id"]
        ):
            raise ValueError("Capacity location does not match its access experiment")
        if (
            capacity["linked_service"]
            != variant_services[capacity["linked_variant_id"]]
        ):
            raise ValueError("Capacity service does not match its access experiment")
        for row in capacity["experiments"]:
            quantities = (
                "participation_fraction",
                "places",
                "assumed_demand",
                "assigned",
                "capacity_limited",
                "unreachable",
                "coverage_excluded",
            )
            if any(
                isinstance(row[key], bool)
                or not isinstance(row[key], (int, float))
                or not isfinite(row[key])
                or row[key] < 0
                for key in quantities
            ):
                raise ValueError(
                    "Finals capacity quantities must be finite nonnegative numbers"
                )
            if row["participation_fraction"] > 1 or not isclose(
                row["assumed_demand"],
                scope["in_scope_population"] * row["participation_fraction"],
                abs_tol=1e-6,
            ):
                raise ValueError(
                    "Finals capacity demand differs from its participation assumption"
                )
            if row["assigned"] > row["places"] + 1e-6:
                raise ValueError("Finals assigned demand exceeds scenario capacity")
            if not isclose(
                row["assumed_demand"],
                sum(
                    row[key]
                    for key in (
                        "assigned",
                        "capacity_limited",
                        "unreachable",
                        "coverage_excluded",
                    )
                ),
                abs_tol=1e-6,
            ):
                raise ValueError("Finals capacity does not conserve demand")


def public_finals_database(analysis: dict, contexts: dict) -> dict:
    """Publish only allowlisted derived OSM/WorldPop data and named public pins."""
    from .evidence_pipeline import _public_context

    projected = {}
    for mode, context in contexts.items():
        value = _public_context(context)
        value["public_origins"] = [
            {key: item for key, item in row.items() if key in ORIGIN_KEYS}
            for row in context["public_origins"]
        ]
        value["reviewed_junctions"] = context.get("reviewed_junctions", [])
        value["context_sha256"] = context["canonical_sha256"]
        projected[mode] = value
    result = {
        "schema_version": "floodguard.finals_database.v1",
        "analysis": analysis,
        "contexts": projected,
    }
    if analysis.get("connectivity_audits"):
        from .evidence_connectivity import audit_connectivity

        result["connectivity_audits"] = {
            mode: audit_connectivity(value["population"], value["edges"], [r for r in value["osm_facilities"] if r.get("service_type") == "hospital" and r.get("candidate_destination_eligible") and r.get("within_routing_context")], source_timestamp=value["source_metadata"]["osm"]["retrieved_at_utc"])
            for mode, value in projected.items()
        }
    assert_public_safe(result)
    return result
