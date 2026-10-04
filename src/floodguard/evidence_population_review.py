"""Bounded population definitions, destination review and capacity assumptions.

These reviews never allocate district age totals to local residents. Current
facility identity does not establish historical operation or usable capacity.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _number(value: Any, field: str, *, optional: bool = False) -> float | None:
    if optional and value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite nonnegative number")  # noqa: TRY004 -- numeric-input validation has one exception contract
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite nonnegative number") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return result


def build_capacity_demand(
    population_rows: Sequence[Mapping[str, Any]],
    *,
    demand_basis: str,
    participation_fraction: float,
    assumption_id: str,
) -> dict:
    """Create explicit hypothetical demand without changing resident inputs.

    ``total_population`` in returned rows is the scenario demand accepted by
    the existing capacity allocator. ``residential_population`` preserves the
    original resident quantity. Risk-based demand requires an explicit
    ``population_at_risk`` and a nonempty ``population_at_risk_basis`` per row.
    Missing risk remains null and blocks allocation of the incomplete set.
    """
    bases = {
        "residential_participation",
        "population_at_risk_participation",
        "full_residential_diagnostic",
    }
    if demand_basis not in bases:
        raise ValueError("Unrecognized capacity demand basis")
    fraction = _number(participation_fraction, "participation_fraction")
    if fraction > 1:
        raise ValueError("participation_fraction must be between zero and one")
    if not isinstance(assumption_id, str) or not assumption_id.strip():
        raise ValueError("A named participation assumption is required")
    if demand_basis == "full_residential_diagnostic" and fraction != 1:
        raise ValueError("Full residential diagnostic requires fraction one")
    rows, seen, unresolved = [], set(), []
    for original in population_rows:
        row = dict(original)
        key = row.get("population_id")
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError("Population IDs must be nonempty and unique")
        seen.add(key)
        residents = _number(row.get("total_population"), "total_population")
        eligible = residents
        if demand_basis == "population_at_risk_participation":
            eligible = _number(
                row.get("population_at_risk"), "population_at_risk", optional=True
            )
            if eligible is not None and eligible > residents:
                raise ValueError("Population at risk exceeds residential population")
            if (
                eligible is not None
                and not str(row.get("population_at_risk_basis") or "").strip()
            ):
                raise ValueError(
                    "Population at risk requires its evidence/scenario basis"
                )
        if eligible is None:
            unresolved.append(key)
        row.update(
            residential_population=residents,
            eligible_population=eligible,
            total_population=None if eligible is None else eligible * fraction,
            participation_fraction=fraction,
            demand_basis=demand_basis,
            demand_assumption_id=assumption_id,
            actual_evacuation_demand=None,
        )
        rows.append(row)
    rows.sort(key=lambda row: row["population_id"])
    known_demand = math.fsum(
        row["total_population"] for row in rows if row["total_population"] is not None
    )
    return {
        "schema_version": "floodguard.capacity_demand_assumption.v1",
        "population_rows": rows,
        "total_residential_population": math.fsum(
            row["residential_population"] for row in rows
        ),
        "known_eligible_population": math.fsum(
            row["eligible_population"]
            for row in rows
            if row["eligible_population"] is not None
        ),
        "scenario_demand_population": None if unresolved else known_demand,
        "known_scenario_demand_population": known_demand,
        "unresolved_population_ids": sorted(unresolved),
        "allocation_eligible": bool(rows) and not unresolved,
        "demand_basis": demand_basis,
        "participation_fraction": fraction,
        "assumption_id": assumption_id,
        "actual_evacuation_demand": None,
        "confidence": "assumed_sensitivity_scenario",
        "is_full_residential_diagnostic": demand_basis == "full_residential_diagnostic",
        "interpretation": "Assumed shelter participation; not observed evacuation need or an evacuation instruction.",
    }


def _read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ("qc_flags", "raw_values"):
            row[key] = (
                json.loads(row[key])
                if row.get(key)
                else ([] if key == "qc_flags" else {})
            )
        row["year_ce"] = int(row["year_ce"]) if row.get("year_ce") else None
        for key in ("reported_total", "computed_sex_sum", "male", "female"):
            row[key] = _number(row.get(key), key, optional=True)
    return rows


def _explicit_bounds(label: str) -> tuple[int, int | None] | None:
    interval = re.fullmatch(r"(\d+)\s*-\s*(\d+)\s*ปี", label.strip())
    if interval:
        low, high = map(int, interval.groups())
        return (low, high) if low <= high else None
    above = re.search(r"(?:\(|^)(\d+)\s*ปีขึ้นไป\)?$", label.strip())
    return (int(above.group(1)), None) if above else None


def review_population_groups(
    normalized_dir: str | Path,
    *,
    source_evidence: Sequence[Mapping[str, Any]] = (),
    generated_at: str,
) -> dict:
    """Review literal age bounds and same-year denominators at source grain.

    Source labels alone establish explicit numeric intervals. Generic agency
    definitions never fill a missing age boundary in another published table.
    Context eligibility does not accept an administrative-to-spatial crosswalk.
    """
    rows = _read_rows(Path(normalized_dir) / "population_context.csv")
    ages = [row for row in rows if row["category"] == "age"]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in ages:
        groups[(row["province_source"], row["age_label_raw"].strip())].append(row)
    definitions = []
    for (province, label), members in sorted(groups.items()):
        bounds = _explicit_bounds(label)
        definitions.append(
            {
                "province": province,
                "source_label": label,
                "age_min_inclusive": bounds[0] if bounds else None,
                "age_max_inclusive": bounds[1] if bounds else None,
                "open_ended": bool(bounds and bounds[1] is None),
                "definition_status": "explicit_source_label"
                if bounds
                else "numeric_bounds_unresolved",
                "source_urls": sorted(
                    {r["source_url"] for r in members if r.get("source_url")}
                ),
                "source_years_ce": sorted(
                    {r["year_ce"] for r in members if r["year_ce"]}
                ),
                "geographic_levels": sorted({r["geography_level"] for r in members}),
                "row_count": len(members),
                "arithmetic_mismatches": sum(
                    "sex_total_mismatch" in r["qc_flags"] for r in members
                ),
                "local_population_eligible": False,
            }
        )
    strata: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        key = (
            row["province_source"],
            row["geography_level"],
            row.get("district_name_raw"),
            row["year_ce"],
        )
        strata[key].append(row)
    denominators = []
    for (province, level, district, year), members in sorted(
        strata.items(), key=lambda item: str(item[0])
    ):
        age_rows = [r for r in members if r["category"] == "age"]
        if not age_rows:
            continue
        intervals = [(r, _explicit_bounds(r["age_label_raw"])) for r in age_rows]
        explicit = [pair for pair in intervals if pair[1] is not None]
        overlaps = []
        for index, (a, ab) in enumerate(explicit):
            for b, bb in explicit[index + 1 :]:
                if ab[0] <= (bb[1] if bb[1] is not None else math.inf) and bb[0] <= (
                    ab[1] if ab[1] is not None else math.inf
                ):
                    overlaps.append([a["age_label_raw"], b["age_label_raw"]])
        ordered = sorted((b for _, b in explicit), key=lambda b: b[0])
        contiguous = (
            bool(ordered)
            and len(explicit) == len(age_rows)
            and not overlaps
            and ordered[0][0] == 0
            and ordered[-1][1] is None
        )
        if contiguous:
            contiguous = all(
                a[1] is not None and a[1] + 1 == b[0] for a, b in pairwise(ordered)
            )
        arithmetic = any("sex_total_mismatch" in r["qc_flags"] for r in age_rows)
        complete_counts = all(r["reported_total"] is not None for r in age_rows)
        total_rows = [
            r
            for r in members
            if r["category"] == "total" and r["reported_total"] is not None
        ]
        registered_total = (
            total_rows[0]["reported_total"] if len(total_rows) == 1 else None
        )
        age_sum = (
            math.fsum(r["reported_total"] for r in age_rows)
            if contiguous and complete_counts
            else None
        )
        reasons = []
        if len(explicit) != len(age_rows):
            reasons.append("unresolved_numeric_age_definitions")
        if overlaps:
            reasons.append("overlapping_age_categories_must_not_be_summed")
        if len(explicit) == len(age_rows) and not overlaps and not contiguous:
            reasons.append("incomplete_age_partition")
        if arithmetic:
            reasons.append("sex_total_mismatch")
        if not complete_counts:
            reasons.append("missing_age_count")
        if registered_total is None:
            reasons.append("independent_same_year_total_unavailable")
        if age_sum == 0:
            reasons.append("zero_classified_denominator")
        if (
            age_sum is not None
            and registered_total is not None
            and age_sum != registered_total
        ):
            reasons.append("classified_sum_does_not_equal_registered_total")
        denominators.append(
            {
                "province": province,
                "geographic_level": level,
                "district_name": district,
                "year_ce": year,
                "age_rows": len(age_rows),
                "explicitly_defined_rows": len(explicit),
                "complete_disjoint_age_partition": contiguous,
                "overlapping_labels": overlaps,
                "classified_age_sum": age_sum,
                "independent_registered_total": registered_total,
                "denominator_type": "classified_age_table_sum"
                if contiguous
                else "unresolved",
                "context_distribution_eligible": contiguous
                and complete_counts
                and not arithmetic
                and age_sum is not None
                and age_sum > 0
                and (registered_total is None or registered_total == age_sum),
                "event_local_group_counts_eligible": False,
                "administrative_spatial_crosswalk": "unresolved",
                "reason_codes": reasons,
                "interpretation": "Source-grain registered population context; no local age allocation or event-day presence inference.",
            }
        )
    chiang_years = sorted(
        {r["year_ce"] for r in ages if r["province_source"] == "chiang_rai"}
    )
    source_qc = Path(normalized_dir) / "population_qc.json"
    qc = json.loads(source_qc.read_text(encoding="utf-8")) if source_qc.exists() else {}
    code_checks = []
    for year in sorted(
        {r["year_ce"] for r in rows if r["geography_level"] == "village"}
    ):
        members = [
            r
            for r in rows
            if r["geography_level"] == "village" and r["year_ce"] == year
        ]
        pairs = [
            (r.get("subdistrict_code_raw", ""), r.get("village_code_raw", ""))
            for r in members
        ]
        valid = [
            len(sub) == len(village) == 8
            and sub.isdigit()
            and village.isdigit()
            and sub[:6] == village[:6]
            for sub, village in pairs
        ]
        code_checks.append(
            {
                "year_ce": year,
                "row_count": len(members),
                "unique_subdistrict_village_code_pairs": len(set(pairs)),
                "repeated_code_pair_rows": len(pairs) - len(set(pairs)),
                "invalid_code_prefix_rows": sum(not value for value in valid),
                "spatial_join_eligible": False,
                "reason_codes": [
                    "registration_office_and_municipality_coverage_unresolved",
                    "no_boundary_version_crosswalk",
                ],
                "interpretation": "Well-formed source codes are not a verified same-year spatial crosswalk; repeated village keys are not silently summed or dropped.",
            }
        )
    return {
        "schema_version": "floodguard.population_group_review.v1",
        "generated_at": generated_at,
        "confidence": "source_label_and_arithmetic_review",
        "definitions": definitions,
        "denominator_checks": denominators,
        "chiang_rai_age_years": chiang_years,
        "chiang_rai_2024_age_missing": 2024 not in chiang_years,
        "arithmetic_mismatches": sum(
            "sex_total_mismatch" in r["qc_flags"] for r in rows
        ),
        "published_mae_sai_reconciliation": qc.get("mae_sai_comparisons", []),
        "administrative_code_checks": code_checks,
        "event_year_checks": [
            {
                "province": province,
                "event_year": year,
                "same_year_age_rows_available": any(
                    r["year_ce"] == year and r["province_source"] == province
                    for r in ages
                ),
                "local_group_counts_eligible": False,
                "reason_codes": ["no_accepted_local_demographic_crosswalk"]
                + (
                    []
                    if any(
                        r["year_ce"] == year and r["province_source"] == province
                        for r in ages
                    )
                    else ["same_year_age_data_unavailable"]
                ),
            }
            for province, year in (
                ("chiang_rai", 2024),
                ("songkhla", 2025),
                ("pathum_thani", 2024),
                ("pathum_thani", 2025),
                ("ayutthaya", 2024),
                ("ayutthaya", 2025),
            )
        ],
        "source_evidence": [dict(row) for row in source_evidence],
        "accepted_local_demographic_groups": [],
        "demographic_equity_eligible": False,
        "imputation_performed": False,
    }


def review_destination_identities(
    normalized_dir: str | Path,
    review_records: Sequence[Mapping[str, Any]],
    *,
    generated_at: str,
) -> dict:
    """Separate current identity, point accuracy and dated documentary activity.

    A dated public report remains a report about a named venue. It does not
    promote a matching historical source point into a verified shelter, or
    prove continuous activation and usable capacity across an event interval.
    """
    reviews = {}
    for record in review_records:
        key = record.get("source_record_id")
        if not key or key in reviews:
            raise ValueError("Destination review IDs must be nonempty and unique")
        url = record.get("source_url", "")
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith((".go.th", ".ac.th"))
        ):
            raise ValueError(
                "Destination identity evidence must identify an official public source"
            )
        if not record.get("retrieved_at_utc") or not record.get("evidence_basis"):
            raise ValueError(
                "Identity review requires retrieval time and evidence basis"
            )
        reviews[key] = record
    rows = []
    for filename, kind in (
        ("shelter_candidates.geojson", "shelter"),
        ("healthcare_candidates.geojson", "healthcare"),
    ):
        path = Path(normalized_dir) / filename
        if not path.exists():
            continue
        for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
            p = feature["properties"]
            aois = [
                a
                for a in p.get("aoi_matches", [])
                if a.endswith("_core") or a.startswith(("aoi-05_", "aoi-06_"))
            ]
            if not aois:
                continue
            key = p["record_id"]
            review = reviews.get(key, {})
            supported = (
                review.get("name_match") is True and review.get("address_match") is True
            )
            activity = review.get("reported_event_activity")
            if activity and (not activity.get("date") or not activity.get("summary")):
                raise ValueError(
                    "Reported event activity requires a date and bounded summary"
                )
            rows.append(
                {
                    "source_record_id": key,
                    "kind": kind,
                    "aois": sorted(aois),
                    "identity_status": "public_name_address_match_supported"
                    if supported
                    else "public_name_match_only"
                    if review.get("name_match") is True
                    else "unresolved",
                    "official_facility_id": review.get("official_facility_id")
                    if supported
                    else None,
                    "evidence_url": review.get("source_url"),
                    "evidence_retrieved_at_utc": review.get("retrieved_at_utc"),
                    "evidence_basis": review.get("evidence_basis"),
                    "evidence_snapshot_status": review.get("snapshot_status"),
                    "evidence_sha256": review.get("sha256"),
                    "review_note": review.get("note"),
                    "coordinate_status": "unverified_source_point",
                    "coordinate_verified": False,
                    "shared_coordinate_records": p.get("records_sharing_coordinate", 1),
                    "identity_merge_approved": False,
                    "reported_event_activity": dict(activity) if activity else None,
                    "reported_activity_to_point_link": "unresolved"
                    if activity
                    else "not_applicable",
                    "event_availability": "unknown",
                    "event_available_capacity": None,
                    "operational_destination_eligible": False,
                }
            )
    unknown = set(reviews) - {row["source_record_id"] for row in rows}
    if unknown:
        raise ValueError("Review refers to an absent analytical-AOI source record")
    rows.sort(key=lambda row: row["source_record_id"])
    return {
        "schema_version": "floodguard.destination_identity_review.v1",
        "generated_at": generated_at,
        "confidence": "bounded_public_source_review",
        "rows": rows,
        "records": len(rows),
        "supported_name_address_matches": sum(
            r["identity_status"] == "public_name_address_match_supported" for r in rows
        ),
        "name_only_matches": sum(
            r["identity_status"] == "public_name_match_only" for r in rows
        ),
        "dated_venue_activity_reports": sum(
            r["reported_event_activity"] is not None for r in rows
        ),
        "verified_coordinates": 0,
        "known_event_capacities": 0,
        "operational_destination_eligible": False,
    }


def build_population_review(
    normalized_dir: str | Path,
    output_dir: str | Path,
    *,
    source_evidence: Sequence[Mapping[str, Any]] = (),
    identity_reviews: Sequence[Mapping[str, Any]] = (),
    generated_at: str,
) -> dict:
    """Write local reviews and return a public-safe summary without source rows."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    population = review_population_groups(
        normalized_dir, source_evidence=source_evidence, generated_at=generated_at
    )
    destinations = review_destination_identities(
        normalized_dir, identity_reviews, generated_at=generated_at
    )
    capacity = {
        "schema_version": "floodguard.capacity_assumptions.v1",
        "generated_at": generated_at,
        "confidence": "explicit_hypothetical_sensitivity",
        "demand_basis": "residential_participation",
        "participation_fractions": [0.05, 0.10, 0.25],
        "default_participation_fraction": 0.10,
        "eligibility": "All modelled residential population in covered units; no age or clinical eligibility claim.",
        "population_at_risk_demand_requires": [
            "explicit_per_unit_population_at_risk",
            "risk_evidence_or_scenario_basis",
            "participation_fraction",
        ],
        "full_residential_population_role": "diagnostic_only_not_observed_evacuation_need",
        "hypothetical_site_capacities": [50, 100, 200],
        "actual_evacuation_demand": None,
        "actual_available_shelter_capacity": None,
        "assumptions": [
            "Fractions and capacities are analyst-selected sensitivity parameters, not calibrated estimates.",
            "Only reviewed scenario site selections enter allocation; repeated source records are not independent capacity.",
            "Healthcare beds are not shelter places; missing capacity remains unknown.",
        ],
    }
    for name, value in (
        ("population_group_review.json", population),
        ("destination_identity_review.json", destinations),
        ("capacity_assumptions.json", capacity),
    ):
        (output / name).write_text(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
            )
            + "\n",
            encoding="utf-8",
        )
    aois = sorted({aoi for row in destinations["rows"] for aoi in row["aois"]})
    summary = {
        "schema_version": "floodguard.population_review_summary.v1",
        "generated_at": generated_at,
        "confidence": "source_definition_and_assumption_review",
        "population": {
            "definitions": population["definitions"],
            "event_year_checks": population["event_year_checks"],
            "accepted_local_demographic_groups": [],
            "demographic_equity_eligible": False,
            "chiang_rai_2024_age_missing": population["chiang_rai_2024_age_missing"],
            "arithmetic_mismatches": population["arithmetic_mismatches"],
            "administrative_code_checks": population["administrative_code_checks"],
            "eligible_context_distributions": [
                {
                    key: row[key]
                    for key in (
                        "province",
                        "geographic_level",
                        "year_ce",
                        "denominator_type",
                        "reason_codes",
                    )
                }
                for row in population["denominator_checks"]
                if row["context_distribution_eligible"]
            ],
            "limitations": [
                "Source age bands are context at their published geography.",
                "No age imputation, local allocation or demographic equity calculation is accepted.",
            ],
            "definition_evidence": [
                {
                    key: row[key]
                    for key in ("source_url", "finding", "scope", "retrieved_at_utc")
                    if key in row
                }
                for row in source_evidence
            ],
        },
        "capacity": capacity,
        "destinations": {
            "records": destinations["records"],
            "supported_name_address_matches": destinations[
                "supported_name_address_matches"
            ],
            "name_only_matches": destinations["name_only_matches"],
            "dated_venue_activity_reports": destinations[
                "dated_venue_activity_reports"
            ],
            "verified_coordinates": 0,
            "known_event_capacities": 0,
            "documentary_venue_evidence": [
                {
                    "aois": row["aois"],
                    "source_url": row["evidence_url"],
                    "source_date": row["reported_event_activity"]["date"],
                    "summary": row["reported_event_activity"]["summary"],
                    "point_link_status": "unresolved",
                    "available_capacity": None,
                }
                for row in destinations["rows"]
                if row["reported_event_activity"] is not None
            ],
            "aois": {
                aoi: {
                    "candidate_records": sum(
                        aoi in row["aois"] for row in destinations["rows"]
                    ),
                    "supported_name_address_matches": sum(
                        aoi in row["aois"]
                        and row["identity_status"]
                        == "public_name_address_match_supported"
                        for row in destinations["rows"]
                    ),
                    "dated_venue_activity_reports": sum(
                        aoi in row["aois"]
                        and row["reported_event_activity"] is not None
                        for row in destinations["rows"]
                    ),
                    "operational_destination_eligible": False,
                }
                for aoi in aois
            },
            "limitations": [
                "Current identity and dated venue reports do not verify historical point accuracy, continuous operation or usable capacity."
            ],
        },
        "local_review_files": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.glob("*.json"))
            if path.name
            in {
                "population_group_review.json",
                "destination_identity_review.json",
                "capacity_assumptions.json",
            }
        },
        "non_operational": True,
    }
    (output / "population_review_summary.json").write_text(
        json.dumps(
            summary, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n",
        encoding="utf-8",
    )
    return summary
