"""Hand-calculated tests for scenario-only binary 2SFCA."""

from __future__ import annotations

import pytest

from floodguard.two_step_access import (
    DemandOrigin,
    ServiceSite,
    TravelPair,
    TwoStepAccessError,
    TwoStepContext,
    calculate_binary_2sfca,
)


def _context(**changes: object) -> TwoStepContext:
    values = {
        "case_id": "illustrative-case",
        "event_id": "illustrative-event",
        "scenario_id": "capacity-sensitivity",
        "service_type": "shelter",
        "travel_mode": "modelled_vehicle",
        "effective_at_utc": "2026-09-23T00:00:00Z",
        "supply_unit": "scenario_places",
        "demand_unit": "modelled_people",
        "assumptions": ("All places and travel times are hypothetical.",),
    }
    values.update(changes)
    return TwoStepContext(**values)


def _example():
    origins = [
        DemandOrigin("o1", 100, "modelled_people"),
        DemandOrigin("o2", 200, "modelled_people"),
        DemandOrigin("o3", 50, "modelled_people"),
    ]
    sites = [
        ServiceSite("s1", 300, "shelter", "scenario_places"),
        ServiceSite("s2", 600, "shelter", "scenario_places"),
    ]
    pairs = [
        TravelPair("o1", "s1", "reachable", 10),
        TravelPair("o1", "s2", "reachable", 40),
        TravelPair("o2", "s1", "reachable", 20),
        TravelPair("o2", "s2", "reachable", 25),
        TravelPair("o3", "s1", "reachable", 50),
        TravelPair("o3", "s2", "reachable", 55),
    ]
    return origins, sites, pairs


def _indexed(result, threshold):
    rows = result["thresholds"][str(threshold)]
    return (
        {site["site_id"]: site for site in rows["sites"]},
        {origin["origin_id"]: origin for origin in rows["origins"]},
        rows["coverage"],
    )


def test_hand_calculated_primary_and_sensitivity_catchments():
    origins, sites, pairs = _example()
    result = calculate_binary_2sfca(_context(), origins, sites, pairs)

    sites15, origins15, _ = _indexed(result, 15)
    assert sites15["s1"]["ratio"] == 3
    assert sites15["s2"]["ratio"] is None
    assert sites15["s2"]["reasons"] == ["zero_catchment_demand"]
    assert origins15["o1"]["accessibility_ratio"] == 3
    assert origins15["o2"]["accessibility_ratio"] == 0

    sites30, origins30, coverage30 = _indexed(result, 30)
    assert sites30["s1"]["known_catchment_demand"] == 300
    assert sites30["s1"]["ratio"] == 1
    assert sites30["s2"]["ratio"] == 3
    assert origins30["o1"]["accessibility_ratio"] == 1
    assert origins30["o2"]["accessibility_ratio"] == 4
    assert origins30["o3"]["accessibility_ratio"] == 0
    assert coverage30["evaluable_known_demand_fraction"] == 1

    sites60, origins60, _ = _indexed(result, 60)
    assert sites60["s1"]["ratio"] == pytest.approx(300 / 350)
    assert sites60["s2"]["ratio"] == pytest.approx(600 / 350)
    assert origins60["o1"]["accessibility_ratio"] == pytest.approx(
        300 / 350 + 600 / 350
    )
    assert (
        origins60["o3"]["accessibility_ratio"] == origins60["o1"]["accessibility_ratio"]
    )

    assert result["evidence_status"] == "scenario_only"
    assert result["operational"] is False
    assert result["official_warning"] is False
    assert result["allocation"] is False
    assert result["ratio_unit"] == "scenario_places/modelled_people"
    assert "allocated_people" not in result


def test_unknown_supply_differs_from_explicit_zero():
    origin = [DemandOrigin("o", 10, "modelled_people")]
    pair = [TravelPair("o", "s", "reachable", 5)]
    unknown = calculate_binary_2sfca(
        _context(), origin, [ServiceSite("s", None, "shelter", "scenario_places")], pair
    )
    known_zero = calculate_binary_2sfca(
        _context(), origin, [ServiceSite("s", 0, "shelter", "scenario_places")], pair
    )
    unknown_site, unknown_origin, _ = _indexed(unknown, 30)
    zero_site, zero_origin, _ = _indexed(known_zero, 30)
    assert unknown_site["s"]["reasons"] == ["unknown_supply"]
    assert unknown_site["s"]["ratio"] is None
    assert unknown_origin["o"]["accessibility_ratio"] is None
    assert zero_site["s"]["ratio"] == 0
    assert zero_origin["o"]["accessibility_ratio"] == 0


def test_zero_demand_catchment_keeps_ratio_null():
    result = calculate_binary_2sfca(
        _context(),
        [DemandOrigin("o", 0, "modelled_people")],
        [ServiceSite("s", 50, "shelter", "scenario_places")],
        [TravelPair("o", "s", "reachable", 1)],
    )
    site, origin, coverage = _indexed(result, 30)
    assert site["s"]["reasons"] == ["zero_catchment_demand"]
    assert origin["o"]["accessibility_ratio"] is None
    assert coverage["evaluable_known_demand_fraction"] is None


def test_unknown_travel_and_demand_limit_ratio_and_coverage():
    origins = [
        DemandOrigin("known", 20, "modelled_people"),
        DemandOrigin("unknown", None, "modelled_people"),
    ]
    sites = [ServiceSite("s", 50, "shelter", "scenario_places")]
    pairs = [
        TravelPair("known", "s", "reachable", 10),
        TravelPair("unknown", "s", "unknown", None),
    ]
    result = calculate_binary_2sfca(_context(), origins, sites, pairs)
    site, origin, coverage = _indexed(result, 30)
    assert site["s"]["ratio"] is None
    assert site["s"]["known_catchment_demand"] == 20
    assert site["s"]["unknown_catchment_origin_ids"] == ["unknown"]
    assert site["s"]["reasons"] == ["unknown_catchment_demand"]
    assert origin["known"]["reasons"] == ["site_ratio_unavailable"]
    assert origin["unknown"]["reasons"] == ["unknown_travel_coverage"]
    assert coverage["travel_pair_fraction"] == 0.5
    assert coverage["unknown_demand_origins"] == 1
    assert coverage["evaluable_known_demand_fraction"] == 0


def test_unknown_zero_demand_travel_keeps_denominator_known_but_origin_unknown():
    result = calculate_binary_2sfca(
        _context(),
        [
            DemandOrigin("o1", 10, "modelled_people"),
            DemandOrigin("o2", 0, "modelled_people"),
        ],
        [ServiceSite("s", 20, "shelter", "scenario_places")],
        [
            TravelPair("o1", "s", "reachable", 10),
            TravelPair("o2", "s", "unknown", None),
        ],
    )
    site, origin, coverage = _indexed(result, 30)
    assert site["s"]["ratio"] == 2
    assert origin["o1"]["accessibility_ratio"] == 2
    assert origin["o2"]["accessibility_ratio"] is None
    assert coverage["evaluable_known_demand_fraction"] == 1
    assert coverage["evaluable_origin_fraction"] == 0.5


def test_complete_matrix_and_units_are_required():
    origins, sites, pairs = _example()
    with pytest.raises(TwoStepAccessError, match="complete travel matrix"):
        calculate_binary_2sfca(_context(), origins, sites, pairs[:-1])
    with pytest.raises(TwoStepAccessError, match="service type"):
        calculate_binary_2sfca(
            _context(),
            origins,
            [ServiceSite("s1", 3, "hospital", "scenario_places")],
            [TravelPair(origin.origin_id, "s1", "reachable", 5) for origin in origins],
        )
    with pytest.raises(TwoStepAccessError, match="demand unit"):
        calculate_binary_2sfca(
            _context(),
            [DemandOrigin("o", 1, "households")],
            [ServiceSite("s", 3, "shelter", "scenario_places")],
            [TravelPair("o", "s", "reachable", 5)],
        )


@pytest.mark.parametrize(
    "bad_pair",
    [
        TravelPair("o", "s", "reachable", None),
        TravelPair("o", "s", "reachable", -1),
        TravelPair("o", "s", "reachable", float("nan")),
        TravelPair("o", "s", "unknown", 5),
        TravelPair("o", "s", "unreachable", 5),
    ],
)
def test_invalid_travel_values_are_rejected(bad_pair):
    with pytest.raises(TwoStepAccessError):
        calculate_binary_2sfca(
            _context(),
            [DemandOrigin("o", 1, "modelled_people")],
            [ServiceSite("s", 1, "shelter", "scenario_places")],
            [bad_pair],
        )


def test_duplicate_pairs_and_naive_effective_date_are_rejected():
    origin = [DemandOrigin("o", 1, "modelled_people")]
    sites = [ServiceSite("s", 1, "shelter", "scenario_places")]
    pair = TravelPair("o", "s", "reachable", 5)
    with pytest.raises(TwoStepAccessError, match="duplicate travel pair"):
        calculate_binary_2sfca(_context(), origin, sites, [pair, pair])
    with pytest.raises(TwoStepAccessError, match="UTC timestamp"):
        calculate_binary_2sfca(
            _context(effective_at_utc="2026-09-23"), origin, sites, [pair]
        )


def test_hash_is_independent_of_input_row_order():
    origins, sites, pairs = _example()
    first = calculate_binary_2sfca(_context(), origins, sites, pairs)
    reversed_rows = calculate_binary_2sfca(
        _context(),
        list(reversed(origins)),
        list(reversed(sites)),
        list(reversed(pairs)),
    )
    assert first == reversed_rows
