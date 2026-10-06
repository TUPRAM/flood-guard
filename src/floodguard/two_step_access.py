"""Scenario-only binary two-step floating catchment accessibility.

This measure estimates service supply relative to demand in a travel-time
catchment. It does not allocate places or people to destinations.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Literal

THRESHOLDS_MINUTES = (15, 30, 60)
TravelStatus = Literal["reachable", "unreachable", "unknown"]


class TwoStepAccessError(ValueError):
    """Raised when a scenario cannot be evaluated without silent assumptions."""


@dataclass(frozen=True)
class TwoStepContext:
    """Identity, units, timing and assumptions for one service scenario."""

    case_id: str
    event_id: str
    scenario_id: str
    service_type: str
    travel_mode: str
    effective_at_utc: str
    supply_unit: str
    demand_unit: str
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class DemandOrigin:
    """One nonoverlapping origin with modelled demand, or unknown demand."""

    origin_id: str
    demand: float | None
    demand_unit: str


@dataclass(frozen=True)
class ServiceSite:
    """One eligible destination with modelled supply, or unknown supply."""

    site_id: str
    supply: float | None
    service_type: str
    supply_unit: str


@dataclass(frozen=True)
class TravelPair:
    """Modelled route state; unknown is distinct from graph disconnection."""

    origin_id: str
    site_id: str
    status: TravelStatus
    minutes: float | None


def calculate_binary_2sfca(
    context: TwoStepContext,
    origins: list[DemandOrigin],
    sites: list[ServiceSite],
    travel_pairs: list[TravelPair],
) -> dict[str, object]:
    """Calculate binary 15/30/60-minute 2SFCA for a complete travel matrix.

    For site j, R_j is site supply divided by all origin demand reachable
    within the threshold. For origin i, A_i is the sum of reachable R_j.
    Unknown demand, supply or route coverage makes affected results null.
    A_i is an accessibility ratio, never a count of allocated people.
    """

    _validate_context(context)
    if not origins or not sites:
        raise TwoStepAccessError(
            "at least one origin and one service site are required"
        )
    origin_by_id = _origins(origins, context)
    site_by_id = _sites(sites, context)
    pair_by_key = _pairs(travel_pairs, origin_by_id, site_by_id)

    canonical_inputs = {
        "context": asdict(context),
        "origins": [asdict(origin_by_id[key]) for key in sorted(origin_by_id)],
        "sites": [asdict(site_by_id[key]) for key in sorted(site_by_id)],
        "travel_pairs": [asdict(pair_by_key[key]) for key in sorted(pair_by_key)],
    }
    input_hash = hashlib.sha256(
        json.dumps(canonical_inputs, sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()

    threshold_results: dict[str, object] = {}
    for threshold in THRESHOLDS_MINUTES:
        site_results: list[dict[str, object]] = []
        ratios: dict[str, float | None] = {}
        for site_id, site in site_by_id.items():
            catchment_demand = 0.0
            unknown_origins: list[str] = []
            for origin_id, origin in origin_by_id.items():
                pair = pair_by_key[(origin_id, site_id)]
                if pair.status == "unknown":
                    if origin.demand is None or origin.demand > 0:
                        unknown_origins.append(origin_id)
                elif pair.status == "reachable" and pair.minutes <= threshold:
                    if origin.demand is None:
                        unknown_origins.append(origin_id)
                    else:
                        catchment_demand += origin.demand

            reasons = []
            if site.supply is None:
                reasons.append("unknown_supply")
            if unknown_origins:
                reasons.append("unknown_catchment_demand")
            elif catchment_demand == 0:
                reasons.append("zero_catchment_demand")
            ratio = (
                site.supply / catchment_demand
                if not reasons and site.supply is not None
                else None
            )
            ratios[site_id] = ratio
            site_results.append(
                {
                    "site_id": site_id,
                    "supply": site.supply,
                    "known_catchment_demand": catchment_demand,
                    "unknown_catchment_origin_ids": sorted(unknown_origins),
                    "ratio": ratio,
                    "status": "evaluable" if ratio is not None else "unavailable",
                    "reasons": reasons,
                }
            )

        origin_results: list[dict[str, object]] = []
        known_demand = 0.0
        evaluable_known_demand = 0.0
        evaluable_origin_count = 0
        for origin_id, origin in origin_by_id.items():
            reachable_sites: list[str] = []
            unknown_travel_sites: list[str] = []
            unavailable_ratio_sites: list[str] = []
            for site_id in site_by_id:
                pair = pair_by_key[(origin_id, site_id)]
                if pair.status == "unknown":
                    unknown_travel_sites.append(site_id)
                elif pair.status == "reachable" and pair.minutes <= threshold:
                    reachable_sites.append(site_id)
                    if ratios[site_id] is None:
                        unavailable_ratio_sites.append(site_id)

            reasons = []
            if unknown_travel_sites:
                reasons.append("unknown_travel_coverage")
            if unavailable_ratio_sites:
                reasons.append("site_ratio_unavailable")
            accessibility = (
                None if reasons else sum(ratios[site_id] for site_id in reachable_sites)
            )
            if origin.demand is not None:
                known_demand += origin.demand
                if accessibility is not None:
                    evaluable_known_demand += origin.demand
            if accessibility is not None:
                evaluable_origin_count += 1
            origin_results.append(
                {
                    "origin_id": origin_id,
                    "demand": origin.demand,
                    "accessibility_ratio": accessibility,
                    "status": "evaluable"
                    if accessibility is not None
                    else "unavailable",
                    "reasons": reasons,
                    "reachable_site_ids": reachable_sites,
                    "unknown_travel_site_ids": unknown_travel_sites,
                    "unavailable_ratio_site_ids": unavailable_ratio_sites,
                }
            )

        known_pair_count = sum(
            pair.status != "unknown" for pair in pair_by_key.values()
        )
        threshold_results[str(threshold)] = {
            "threshold_minutes": threshold,
            "sites": site_results,
            "origins": origin_results,
            "coverage": {
                "known_travel_pairs": known_pair_count,
                "total_travel_pairs": len(pair_by_key),
                "travel_pair_fraction": known_pair_count / len(pair_by_key),
                "evaluable_origins": evaluable_origin_count,
                "total_origins": len(origin_by_id),
                "evaluable_origin_fraction": evaluable_origin_count / len(origin_by_id),
                "known_demand": known_demand,
                "unknown_demand_origins": sum(
                    origin.demand is None for origin in origin_by_id.values()
                ),
                "demand_coverage_status": (
                    "incomplete_unknown_demand"
                    if any(origin.demand is None for origin in origin_by_id.values())
                    else "all_demand_known"
                ),
                "evaluable_known_demand": evaluable_known_demand,
                "evaluable_known_demand_fraction": (
                    evaluable_known_demand / known_demand if known_demand > 0 else None
                ),
            },
        }

    return {
        "schema_version": "binary_2sfca_scenario_v1",
        "evidence_status": "scenario_only",
        "operational": False,
        "official_warning": False,
        "measure_type": "two_step_floating_catchment_accessibility",
        "allocation": False,
        "input_sha256": input_hash,
        "context": asdict(context),
        "primary_threshold_minutes": 30,
        "sensitivity_threshold_minutes": [15, 60],
        "ratio_unit": f"{context.supply_unit}/{context.demand_unit}",
        "thresholds": threshold_results,
    }


def _validate_context(context: TwoStepContext) -> None:
    for field in (
        "case_id",
        "event_id",
        "scenario_id",
        "service_type",
        "travel_mode",
        "supply_unit",
        "demand_unit",
    ):
        value = getattr(context, field)
        if not isinstance(value, str) or not value.strip():
            raise TwoStepAccessError(f"{field} must be a nonempty string")
    try:
        timestamp = datetime.fromisoformat(
            context.effective_at_utc.replace("Z", "+00:00")
        )
    except (AttributeError, ValueError) as error:
        raise TwoStepAccessError("effective_at_utc must be a UTC timestamp") from error
    if timestamp.utcoffset() != timedelta(0):
        raise TwoStepAccessError("effective_at_utc must be a UTC timestamp")
    if (
        not isinstance(context.assumptions, tuple)
        or not context.assumptions
        or not all(
            isinstance(item, str) and item.strip() for item in context.assumptions
        )
    ):
        raise TwoStepAccessError("assumptions must be a tuple of nonempty strings")


def _number(value: float | None, field: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TwoStepAccessError(f"{field} must be a finite nonnegative number or null")
    if not math.isfinite(value) or value < 0:
        raise TwoStepAccessError(f"{field} must be a finite nonnegative number or null")


def _origins(
    origins: list[DemandOrigin], context: TwoStepContext
) -> dict[str, DemandOrigin]:
    by_id = {}
    for origin in origins:
        if (
            not isinstance(origin.origin_id, str)
            or not origin.origin_id.strip()
            or origin.origin_id in by_id
        ):
            raise TwoStepAccessError("origin IDs must be nonempty and unique")
        if origin.demand_unit != context.demand_unit:
            raise TwoStepAccessError("origin demand unit differs from context")
        _number(origin.demand, "demand")
        by_id[origin.origin_id] = origin
    return dict(sorted(by_id.items()))


def _sites(sites: list[ServiceSite], context: TwoStepContext) -> dict[str, ServiceSite]:
    by_id = {}
    for site in sites:
        if (
            not isinstance(site.site_id, str)
            or not site.site_id.strip()
            or site.site_id in by_id
        ):
            raise TwoStepAccessError("site IDs must be nonempty and unique")
        if site.service_type != context.service_type:
            raise TwoStepAccessError("site service type differs from context")
        if site.supply_unit != context.supply_unit:
            raise TwoStepAccessError("site supply unit differs from context")
        _number(site.supply, "supply")
        by_id[site.site_id] = site
    return dict(sorted(by_id.items()))


def _pairs(
    pairs: list[TravelPair],
    origins: dict[str, DemandOrigin],
    sites: dict[str, ServiceSite],
) -> dict[tuple[str, str], TravelPair]:
    by_key = {}
    for pair in pairs:
        key = (pair.origin_id, pair.site_id)
        if pair.origin_id not in origins or pair.site_id not in sites:
            raise TwoStepAccessError("travel pair references an unknown origin or site")
        if key in by_key:
            raise TwoStepAccessError("duplicate travel pair")
        if pair.status not in ("reachable", "unreachable", "unknown"):
            raise TwoStepAccessError(
                "travel status must be reachable/unreachable/unknown"
            )
        if pair.status == "reachable":
            if pair.minutes is None:
                raise TwoStepAccessError("reachable travel pair requires minutes")
            _number(pair.minutes, "minutes")
        elif pair.minutes is not None:
            raise TwoStepAccessError(
                "unreachable/unknown travel pair requires null minutes"
            )
        by_key[key] = pair
    expected = {(origin_id, site_id) for origin_id in origins for site_id in sites}
    if by_key.keys() != expected:
        missing = sorted(expected - by_key.keys())
        raise TwoStepAccessError(f"complete travel matrix required; missing {missing}")
    return dict(sorted(by_key.items()))
