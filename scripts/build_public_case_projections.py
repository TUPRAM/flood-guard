"""Export a small, allowlisted candidate case view for the Public surface.

The source EvidenceLibrary remains the analytical record. This exporter verifies
its bytes and publication rights before copying selected identity and modelled
access numbers into a separate same-origin, non-operational projection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

CATALOG_SCHEMA = "floodguard.public_case_catalog.v1"
CASE_SCHEMA = "floodguard.public_case.v1"
BASE_DATASETS = frozenset({"context-worldpop", "context-osm", "context-admin", "project-scenarios"})
SERVICES = frozenset({"hospital", "primary_care", "pharmacy", "shelter", "main_road"})
MODES = frozenset({"walking", "modelled_vehicle"})
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,100}$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_TEXT = re.compile(r"[A-Za-z]:[\\/]|(?:/Users/|/home/|/root/)|file://|[\w.+-]+@[\w.-]+", re.IGNORECASE)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field} must be an object")
    return value


def _text(value: object, field: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 400 or PRIVATE_TEXT.search(value):
        raise ValueError(f"{field} is unavailable or unsafe for public export")
    return value


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value) or ".." in value:
        raise ValueError(f"{field} is not a safe identifier")
    return value


def _number(value: object, field: str, *, nullable: bool = False, fraction: bool = False) -> float | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    if fraction and value > 1:
        raise ValueError(f"{field} must be at most one")
    return float(value)


def _source_package(public_dir: Path, ref: dict[str, Any], version: str) -> tuple[dict[str, Any], str]:
    package_id = _id(ref.get("id"), "package.id")
    expected_url = f"/evidence-library/packages/{package_id}.json"
    digest = ref.get("sha256")
    if ref.get("url") != expected_url or not isinstance(digest, str) or not HEX_SHA256.fullmatch(digest):
        raise ValueError(f"Unsafe or unpinned package reference: {package_id}")
    path = public_dir / expected_url.lstrip("/")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Package is missing or linked: {package_id}")
    data = path.read_bytes()
    if _sha256(data) != digest:
        raise ValueError(f"Package checksum mismatch: {package_id}")
    package = _object(json.loads(data), "package")
    if (package.get("schema_version") != "1.0" or package.get("package_version") != version
        or package.get("id") != package_id or package.get("aoi_id") != ref.get("aoi_id")
        or package.get("event_id") != ref.get("event_id") or package.get("dataset_mode") != "candidate"
        or package.get("operational_status") != "non_operational" or package.get("official_warning") is not False
        or package.get("confidence_class") != "low"):
        raise ValueError(f"Package identity or safety boundary failed: {package_id}")
    assessment = _object(package.get("assessment"), "assessment")
    brief = _object(package.get("decision_brief"), "decision_brief")
    priority = _object(brief.get("priority"), "priority")
    if (assessment.get("fpps") is not None or assessment.get("action_class") is not None
        or brief.get("affected_population") is not None or priority.get("fpps") is not None
        or priority.get("action_class") is not None or brief.get("demographic_equity_status") != "unavailable"
        or brief.get("aoi_id") != ref.get("aoi_id") or brief.get("event_id") != ref.get("event_id")):
        raise ValueError(f"Candidate package contains accepted-looking decision fields: {package_id}")
    return package, digest


def _rights(catalog: dict[str, Any], *, flood: bool) -> None:
    datasets = {
        _id(row.get("id"), "dataset.id"): _object(row.get("rights"), "dataset.rights")
        for row in catalog.get("datasets", [])
    }
    needed = BASE_DATASETS | ({"context-sar-candidate"} if flood else set())
    for dataset_id in sorted(needed):
        if datasets.get(dataset_id, {}).get("public_derivatives") is not True:
            raise ValueError(f"Public derivative permission unresolved: {dataset_id}")


def _access(value: object, field: str) -> dict[str, float]:
    raw = _object(value, field)
    return {
        key: _number(raw.get(key), f"{field}.{key}")  # type: ignore[dict-item]
        for key in (
            "modelled_population", "within_30_minutes_population",
            "connected_without_route_population", "unknown_access_population",
        )
    }


def _case_projection(package: dict[str, Any], source_sha256: str, catalog: dict[str, Any]) -> dict[str, Any]:
    brief = _object(package["decision_brief"], "decision_brief")
    assessment = _object(package.get("assessment"), "assessment")
    if (package.get("dataset_mode") != "candidate" or package.get("official_warning") is not False
        or assessment.get("fpps") is not None or assessment.get("action_class") is not None
        or brief.get("affected_population") is not None):
        raise ValueError("Candidate projection rejects accepted-looking decision fields")
    analysis = _object(brief.get("finals_analysis") or {}, "finals_analysis")
    analysis_time = analysis.get("generated_at")
    if analysis_time is not None:
        analysis_time = _text(analysis_time, "finals_analysis.generated_at")
        try:
            release_dt = datetime.fromisoformat(package["generated_at"].replace("Z", "+00:00"))
            analysis_dt = datetime.fromisoformat(analysis_time.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Invalid release or analysis generation time") from error
        if not release_dt.tzinfo or not analysis_dt.tzinfo or analysis_dt > release_dt:
            raise ValueError("Analysis generation time must precede package release")
    reporting = _object(brief.get("reporting"), "reporting")
    flood_scenarios = _object(analysis.get("flood_scenarios", {}), "flood_scenarios")
    _rights(catalog, flood=bool(flood_scenarios))
    services = []
    for row in analysis.get("services", []):
        service = _object(row, "service")
        service_id = _id(service.get("id"), "service.id")
        if service_id not in SERVICES or service.get("status") not in {"available", "unavailable"}:
            raise ValueError("Unrecognized service or status")
        if service_id == "main_road":
            raise ValueError("Main-road access has no qualified source service result")
        variants = []
        for item in service.get("variants", []):
            variant = _object(item, "variant")
            variant_id = _id(variant.get("id"), "variant.id")
            mode = variant.get("travel_mode")
            if mode not in MODES or variant_id != f"{service_id}-{mode}-1":
                continue  # The public projection exposes the declared primary speed only.
            projected: dict[str, Any] = {"id": variant_id, "travel_mode": mode, **_access(variant.get("baseline"), "baseline")}
            flood = flood_scenarios.get(mode) if service_id == analysis.get("primary_service") else None
            if flood is not None:
                scenario = _object(flood, "flood_scenario")
                impact = _object(scenario.get("impact"), "flood_scenario.impact")
                if scenario.get("accepted_fpps") is not None or scenario.get("accepted_action_class") is not None:
                    raise ValueError("Candidate flood scenario contains accepted decision")
                projected["candidate_flood_scenario_id"] = _id(impact.get("id"), "flood_scenario.id")
                projected["candidate_flood_losing_30_min_access"] = _number(impact.get("losing_30_min_access"), "flood_scenario.losing_30_min_access")
                projected["candidate_flood_newly_unreachable_population"] = _number(impact.get("newly_unreachable_population"), "flood_scenario.newly_unreachable_population")
                projected["candidate_flood_source_timestamp"] = _text(scenario.get("source_timestamp"), "flood_scenario.source_timestamp", nullable=True)
            else:
                projected.update(candidate_flood_scenario_id=None, candidate_flood_losing_30_min_access=None,
                    candidate_flood_newly_unreachable_population=None, candidate_flood_source_timestamp=None)
            variants.append(projected)
        services.append({
            "id": service_id,
            "status": service["status"],
            "reason": _text(service.get("reason"), "service.reason", nullable=True),
            "facilities": _number(service.get("facilities"), "service.facilities", nullable=True),
            "variants": variants,
        })
    services.append({
        "id": "main_road",
        "status": "unavailable",
        "reason": "Main-road access has no separately qualified result; road connectivity does not establish passability.",
        "facilities": None,
        "variants": [],
    })
    population_year = brief.get("population_reference_year")
    if population_year is not None and (not isinstance(population_year, int) or isinstance(population_year, bool)
        or not 1900 <= population_year <= 2100):
        raise ValueError("Missing population reference year")
    return {
        "schema_version": CASE_SCHEMA,
        "package_version": _text(package.get("package_version"), "package_version"),
        "id": _id(package.get("id"), "package.id"),
        "aoi_id": _id(package.get("aoi_id"), "aoi_id"),
        "event_id": _id(package.get("event_id"), "event_id"),
        "source_package_sha256": source_sha256,
        "generated_at": _text(package.get("generated_at"), "generated_at"),
        "source_analysis_generated_at": analysis_time,
        "source_timestamp": _text(package.get("source_timestamp"), "source_timestamp", nullable=True),
        "dataset_mode": "candidate", "operational_status": "non_operational", "official_warning": False,
        "confidence_class": "low", "fpps": None, "action_class": None, "affected_population": None,
        "demographic_equity_status": "unavailable",
        "population_reference_year": population_year,
        "population_role": "modelled_residential_context",
        # The generic brief access uses a legacy mixed candidate vehicle basis.
        # It is not interchangeable with the precomputed service/mode variants.
        "access": None,
        "reporting_coverage_fraction": _number(reporting.get("coverage_fraction"), "reporting.coverage_fraction", fraction=True),
        "reporting_scope": _text(reporting.get("scope"), "reporting.scope"),
        "services": services,
        "limitations": [
            "Historical candidate and imposed road scenarios only; not current route guidance or an official warning.",
            "Residential population is modelled, not a measured event casualty, and reporting units are AOI intersections.",
            "Accepted flood likelihood, FPPS, action class and age equity are unavailable.",
            "Generic legacy vehicle access is omitted; select a service and travel mode for a comparable modelled result.",
        ],
    }


def build(public_dir: Path, output_dir: Path, catalog_sha256: str) -> dict[str, Any]:
    """Verify the source catalog/packages and write deterministic public projections."""
    if not HEX_SHA256.fullmatch(catalog_sha256):
        raise ValueError("A pinned catalog SHA-256 is required")
    catalog_path = public_dir / "evidence-library/catalog.json"
    if catalog_path.is_symlink() or not catalog_path.is_file():
        raise ValueError("Source catalog is missing or linked")
    source = catalog_path.read_bytes()
    if _sha256(source) != catalog_sha256:
        raise ValueError("Source catalog checksum mismatch")
    catalog = _object(json.loads(source), "catalog")
    if catalog.get("schema_version") != "1.0" or catalog.get("non_operational") is not True:
        raise ValueError("Source catalog is not the non-operational EvidenceLibrary v1")
    version = _text(catalog.get("package_version"), "catalog.package_version")
    refs = catalog.get("packages")
    if not isinstance(refs, list) or not refs:
        raise ValueError("Catalog has no packages")
    cases: dict[str, bytes] = {}
    projected_refs = []
    seen_pairs: set[tuple[str, str]] = set()
    for item in refs:
        ref = _object(item, "package reference")
        pair = (_id(ref.get("aoi_id"), "aoi_id"), _id(ref.get("event_id"), "event_id"))
        if pair in seen_pairs:
            raise ValueError("Duplicate case pair")
        seen_pairs.add(pair)
        package, digest = _source_package(public_dir, ref, version)
        projected = _case_projection(package, digest, catalog)
        data = _json_bytes(projected)
        url = f"/public-case-projections/cases/{projected['id']}.json"
        cases[projected["id"]] = data
        projected_refs.append({"id": projected["id"], "aoi_id": pair[0], "event_id": pair[1], "url": url,
            "sha256": _sha256(data), "source_package_sha256": digest})
    aois = []
    for item in catalog.get("aois", []):
        aoi = _object(item, "aoi")
        if any(ref["aoi_id"] == aoi.get("id") for ref in projected_refs):
            aois.append({"id": _id(aoi.get("id"), "aoi.id"), "name": _text(aoi.get("name"), "aoi.name"),
                "name_th": _text(aoi.get("name_th"), "aoi.name_th", nullable=True)})
    events = []
    for item in catalog.get("events", []):
        event = _object(item, "event")
        if any(ref["event_id"] == event.get("id") for ref in projected_refs):
            events.append({"id": _id(event.get("id"), "event.id"), "name": _text(event.get("name"), "event.name"),
                "name_th": _text(event.get("name_th"), "event.name_th", nullable=True),
                "start": _text(event.get("start"), "event.start"), "end": _text(event.get("end"), "event.end")})
    output_catalog = {"schema_version": CATALOG_SCHEMA, "package_version": version,
        "source_catalog_sha256": catalog_sha256, "aois": aois, "events": events, "packages": projected_refs}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cases").mkdir(exist_ok=True)
    for case_id, data in cases.items():
        (output_dir / "cases" / f"{case_id}.json").write_bytes(data)
    (output_dir / "catalog.json").write_bytes(_json_bytes(output_catalog))
    return {"cases": len(cases), "source_catalog_sha256": catalog_sha256,
        "output_catalog_sha256": _sha256(_json_bytes(output_catalog))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--catalog-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.public_dir, args.output_dir, args.catalog_sha256), sort_keys=True))


if __name__ == "__main__":
    main()
