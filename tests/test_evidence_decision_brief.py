"""Decision briefs retain population accounting and scenario evidence limits."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from shapely.geometry import box, mapping

from floodguard.evidence_decision_brief import build_decision_brief
from floodguard.evidence_population_review import build_capacity_demand
from floodguard.evidence_scenarios import (
    allocate_shelter_capacity,
    calculate_total_access,
)

AOI = "aoi-01_mae_sai_core"
STAMP = "2026-09-21T11:00:00+00:00"
SCHEMA = json.loads(
    (
        Path(__file__).parents[1]
        / "packages/contracts/schemas/decision-brief.schema.json"
    ).read_text(encoding="utf-8")
)


def person(key, amount, longitude=0.5, node="a", snap=0):
    return {
        "population_id": key,
        "total_population": amount,
        "longitude": longitude,
        "latitude": 0.5,
        "node_id": node,
        "snap_distance_m": snap,
        "subdistrict_id": "unassigned",
    }


def edge(key="ab", start="a", end="b", minutes=10):
    return {
        "edge_id": key,
        "from_node": start,
        "to_node": end,
        "normal_minutes": minutes,
    }


def site(capacity=100):
    return {
        "facility_id": "s",
        "node_id": "b",
        "snap_distance_m": 0,
        "capacity": capacity,
    }


def boundaries():
    review = {
        "boundary_source": {
            "source_url": "https://official.go.th/boundaries",
            "public_derivatives": True,
        },
        "source_timestamp": "2020-01-01",
        "crosswalk": {
            "aois": [
                {
                    "aoi_id": AOI,
                    "coverage_fraction": 0.8,
                    "units": [
                        {
                            "adm3_pcode": code,
                            "name": code,
                            "name_th": code,
                            "scope": "partial_unit",
                            "unit_coverage_fraction": 0.5,
                            "intersection_area_km2": 10,
                        }
                        for code in ("U1", "U2")
                    ],
                }
            ]
        },
    }
    features = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"adm3_pcode": "U1"},
                "geometry": mapping(box(0, 0, 1, 1)),
            },
            {
                "type": "Feature",
                "properties": {"adm3_pcode": "U2"},
                "geometry": mapping(box(1, 0, 2, 1)),
            },
        ],
    }
    return review, features


def brief(population=None, details=None, *, reporting=False, context_missing=False):
    context = (
        None
        if context_missing
        else {"population": population or [], "coverage": {"connected_components": 2}}
    )
    if details is None:
        details = {
            "access_scenarios": {
                "baseline": calculate_total_access(population or [], [edge()], [site()])
            }
        }
    review, units = boundaries() if reporting else ({}, {})
    result = build_decision_brief(
        aoi_id=AOI,
        event_id="mae_sai_2024",
        generated_at=STAMP,
        context=context,
        details=details,
        reporting_review=review,
        reporting_units=units,
    )
    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(result)
    return result


def test_centroid_boundary_ambiguity_and_outside_population_conserve_mass():
    population = [
        person("left", 10),
        person("right", 20, 1.5),
        person("shared", 30, 1),
        person("outside", 40, 3),
    ]
    result = brief(population, reporting=True)
    reporting = result["reporting"]
    assert reporting["ambiguous_population_cells"] == 1
    assert reporting["unassigned_modelled_population"] == 70
    unit_mass = {
        row["id"]: row["population_context"]["modelled_population"]
        for row in reporting["units"]
    }
    assert unit_mass == {"U1": 10, "U2": 20}
    assert (
        sum(unit_mass.values()) + reporting["unassigned_modelled_population"]
        == result["access"]["modelled_population"]
        == 100
    )
    assert all(
        row["affected_population"] is None
        and row["fpps"] is None
        and row["action_class"] is None
        for row in reporting["units"]
    )


def test_zero_residents_is_measured_zero_but_missing_event_impact_stays_null():
    result = brief([person("empty", 0)], reporting=True)
    assert result["access"]["modelled_population"] == 0
    assert (
        result["reporting"]["units"][0]["population_context"]["modelled_population"]
        == 0
    )
    assert result["affected_population"] is None
    assert result["priority"]["fpps"] is None
    assert result["priority"]["action_class"] is None


def test_missing_context_and_missing_baseline_do_not_become_population_zero():
    missing = brief(details={}, context_missing=True, reporting=True)
    assert missing["status"] == "coverage_only"
    assert missing["access"] is None
    assert missing["reporting"]["unassigned_modelled_population"] is None
    assert all(
        row["population_context"] is None for row in missing["reporting"]["units"]
    )
    incomplete = brief([person("p", 100)], details={}, reporting=True)
    assert incomplete["access"] is None
    assert incomplete["reporting"]["unassigned_modelled_population"] is None
    assert all(
        row["population_context"] is None for row in incomplete["reporting"]["units"]
    )


def test_graph_gap_no_route_over_threshold_and_zero_minute_trip_are_distinct():
    population = [
        person("near", 10, node="b"),
        person("far", 20),
        person("no-route", 30, node="c"),
        person("coverage-gap", 40, node=None, snap=None),
    ]
    baseline = calculate_total_access(
        population, [edge(minutes=40), edge("cd", "c", "d")], [site()]
    )
    result = brief(population, {"access_scenarios": {"baseline": baseline}})
    counts = result["access"]
    assert counts["within_30_minutes_population"] == 10
    assert counts["over_30_minutes_population"] == 20
    assert counts["connected_without_route_population"] == 30
    assert counts["unknown_access_population"] == 40
    assert (
        sum(
            counts[k]
            for k in (
                "within_30_minutes_population",
                "over_30_minutes_population",
                "connected_without_route_population",
                "unknown_access_population",
            )
        )
        == counts["modelled_population"]
        == 100
    )
    assert result["affected_population"] is None
    assert result["demographic_equity_status"] == "unavailable"


def test_actual_calculator_results_distinguish_time_only_and_threshold_loss():
    population = [person("p", 100)]
    roads = [edge(), edge("ac", "a", "c", 11), edge("cb", "c", "b", 1)]
    baseline = calculate_total_access(population, roads, [site()])
    detour = calculate_total_access(
        population, roads, [site()], scenario={"closed_edge_ids": ["ab"]}
    )
    outage = calculate_total_access(
        population, roads, [site()], scenario={"removed_facility_ids": ["s"]}
    )
    result = brief(
        population,
        {
            "access_scenarios": {
                "baseline": baseline,
                "close_edge": detour,
                "remove_destination": outage,
            }
        },
    )
    changes = {r["kind"]: r for r in result["interventions"]}
    assert changes["close_edge"]["result"] == "travel_time_only"
    assert changes["close_edge"]["slower_population"] == 100
    assert changes["close_edge"]["mean_travel_time_delta_minutes"] == 2
    assert changes["close_edge"]["losing_30_min_access"] == 0
    assert changes["remove_destination"]["result"] == "threshold_change"
    assert changes["remove_destination"]["losing_30_min_access"] == 100
    assert changes["remove_destination"]["mean_travel_time_delta_minutes"] is None
    assert all(r["observed"] is False for r in changes.values())


def test_fractional_positive_effect_is_not_erased_by_display_rounding():
    population = [person("fractional-cell", 0.001)]
    baseline = calculate_total_access(population, [edge()], [site()])
    outage = calculate_total_access(
        population, [edge()], [site()], scenario={"removed_facility_ids": ["s"]}
    )
    result = brief(
        population,
        {"access_scenarios": {"baseline": baseline, "remove_destination": outage}},
    )
    assert result["interventions"][0]["result"] == "threshold_change"


def test_reporting_population_and_baseline_quantities_cannot_disagree():
    population = [person("p", 100)]
    baseline = calculate_total_access([person("p", 500)], [edge()], [site()])
    with pytest.raises(ValueError, match="[Pp]opulation|denominator|quantity"):
        brief(population, {"access_scenarios": {"baseline": baseline}}, reporting=True)


def test_extra_baseline_population_cannot_disappear_from_reporting_mass():
    population = [person("p", 100)]
    baseline = calculate_total_access(
        [*population, person("extra", 10)], [edge()], [site()]
    )
    with pytest.raises(ValueError, match="[Pp]opulation|identif|denominator"):
        brief(population, {"access_scenarios": {"baseline": baseline}}, reporting=True)


def test_missing_baseline_cell_is_rejected_even_when_outside_boundaries():
    population = [person("p", 100), person("outside", 20, 3)]
    baseline = calculate_total_access(population[:1], [edge()], [site()])
    with pytest.raises(ValueError, match="[Pp]opulation|identif|denominator"):
        brief(population, {"access_scenarios": {"baseline": baseline}}, reporting=True)


def test_duplicate_boundary_code_and_unapproved_derivatives_fail_closed():
    population = [person("p", 100)]
    review, units = boundaries()
    units["features"].append(deepcopy(units["features"][0]))
    details = {
        "access_scenarios": {
            "baseline": calculate_total_access(population, [edge()], [site()])
        }
    }
    kwargs = {
        "aoi_id": AOI,
        "event_id": "mae_sai_2024",
        "generated_at": STAMP,
        "context": {"population": population},
        "details": details,
        "reporting_review": review,
        "reporting_units": units,
    }
    with pytest.raises(ValueError, match="Duplicate"):
        build_decision_brief(**kwargs)
    review["boundary_source"]["public_derivatives"] = False
    result = build_decision_brief(**kwargs)
    assert result["reporting"]["status"] == "unavailable"
    assert result["reporting"]["units"] == []


@pytest.mark.parametrize("capacity", [25, None])
def test_capacity_view_conserves_assumed_demand_and_retains_resident_denominator(
    capacity,
):
    population = [person("p", 500)]
    demand = build_capacity_demand(
        population,
        demand_basis="residential_participation",
        participation_fraction=0.1,
        assumption_id="residents-10pct",
    )
    result = allocate_shelter_capacity(
        demand["population_rows"],
        [site(capacity)],
        [{"population_id": "p", "facility_id": "s", "travel_minutes": 10}],
    )
    result.update(
        scenario_id="assumed-site",
        demand_assumptions={k: v for k, v in demand.items() if k != "population_rows"},
    )
    output = brief(population, {"capacity_scenarios": [result]})[
        "capacity_experiments"
    ][0]
    assert output["assumed_demand"] == 50
    assert output["residential_population"] == 500
    assert output["participation_fraction"] == 0.1
    assert output["demand_basis"] == "residential_participation"
    assert output["actual_evacuation_demand"] is None
    assert output["actual_available_capacity"] is None
    assert (
        sum(
            output[k]
            for k in (
                "assigned",
                "capacity_limited",
                "unreachable",
                "coverage_excluded",
                "unknown_capacity",
            )
        )
        == output["assumed_demand"]
    )
    assert output["unknown_capacity"] == (50 if capacity is None else 0)


def test_duplicate_crosswalk_code_is_not_silently_overwritten():
    review, units = boundaries()
    review["crosswalk"]["aois"][0]["units"].append(
        {**review["crosswalk"]["aois"][0]["units"][0], "name": "conflicting name"}
    )
    with pytest.raises(ValueError, match="Duplicate|duplicate"):
        build_decision_brief(
            aoi_id=AOI,
            event_id="mae_sai_2024",
            generated_at=STAMP,
            context=None,
            details={},
            reporting_review=review,
            reporting_units=units,
        )


def test_missing_review_evidence_is_unavailable_not_a_zero_findings_claim():
    result = brief(details={}, context_missing=True)
    notes = {row["topic"]: row for row in result["evidence_notes"]}
    for topic in ("population", "destinations", "connections"):
        assert notes[topic]["status"] == "unavailable"


def test_no_resident_cells_with_explicit_baseline_is_zero_context():
    result = brief([], reporting=True)
    assert result["access"]["modelled_population"] == 0
    assert result["reporting"]["unassigned_modelled_population"] == 0
    assert all(
        row["population_context"]["modelled_population"] == 0
        for row in result["reporting"]["units"]
    )


def test_unavailable_intervention_does_not_masquerade_as_computed_no_change():
    population = [person("p", 100)]
    baseline = calculate_total_access(population, [edge()], [site()])
    result = brief(
        population,
        {
            "access_scenarios": {
                "baseline": baseline,
                "close_edge": {"status": "unavailable", "reason": "No eligible edge."},
                "remove_destination": baseline,
            }
        },
        reporting=True,
    )
    assert [r["kind"] for r in result["interventions"]] == ["remove_destination"]
    assert result["interventions"][0]["result"] == "no_measured_change"
    assert all(
        "close_edge" not in [r["kind"] for r in unit["interventions"]]
        for unit in result["reporting"]["units"]
    )
