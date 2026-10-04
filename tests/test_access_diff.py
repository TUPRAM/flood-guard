"""Access difference between a baseline run and a flooded run (plan task E5).

Every graph, cell, unit and flood extent here is invented. The protocol files are read for their rules only.
No FPPS, no A-E class and no ensemble is computed; the two component functions of frame v1 are called on
invented units, to show that the rows of this task fit them as they are.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import random
from typing import Any

import pytest
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform

from floodguard import access_diff, closure_rules, normalisation
from floodguard.evidence_scenarios import calculate_total_access

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
V1A = json.loads((DOCS / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
V1B = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
TO_WGS84 = Transformer.from_crs(32647, 4326, always_xy=True).transform
ORIGIN_X, ORIGIN_Y = 590_000.0, 2_258_000.0


def lonlat(x_m: float, y_m: float) -> list[float]:
    """Return longitude and latitude of a point given in metres from an invented origin in EPSG:32647."""

    longitude, latitude = TO_WGS84(ORIGIN_X + x_m, ORIGIN_Y + y_m)
    return [longitude, latitude]


def edge(edge_id: str, start: str, end: str, minutes: float, road_class: str = "residential", **tags: Any) -> dict[str, Any]:
    return {"edge_id": edge_id, "from_node": start, "to_node": end, "normal_minutes": minutes, "road_class": road_class,
            "bridge": "no", "tunnel": "no", **tags}


def cell(identifier: str, node: str | None, residents: float, snap: float | None = 0.0) -> dict[str, Any]:
    return {"population_id": identifier, "subdistrict_id": "invented", "total_population": residents, "node_id": node,
            "snap_distance_m": snap}


def site(identifier: str, node: str | None, snap: float | None = 0.0) -> dict[str, Any]:
    return {"facility_id": identifier, "node_id": node, "snap_distance_m": snap}


def cells_of(population: list[dict[str, Any]], unit: str | None = "U1") -> list[dict[str, Any]]:
    return [{"population_id": row["population_id"], "unit_id": unit, "residents": float(row["total_population"])}
            for row in population]


# A line a - b - c - d with the hospital at a. Ten minutes per edge.
LINE = [edge("ab", "a", "b", 10.0), edge("bc", "b", "c", 10.0), edge("cd", "c", "d", 10.0)]
LINE_NODES = {"a", "b", "c", "d"}
HOSPITAL = [site("H", "a")]


def test_services_and_thresholds_are_read_from_the_two_protocols() -> None:
    rules = {rule.service: rule for rule in access_diff.service_rules(V1A, V1B)}

    assert set(rules) == {"hospital", "main_road_entry", "ddpm_located_shelter"}
    assert (rules["hospital"].mode, rules["hospital"].access_gap_threshold_minutes, rules["hospital"].publication_level) == (
        "vehicle", 30, "public")
    assert (rules["main_road_entry"].mode, rules["main_road_entry"].access_gap_threshold_minutes) == ("vehicle", 15)
    shelter = rules["ddpm_located_shelter"]
    assert (shelter.mode, shelter.access_gap_threshold_minutes, shelter.publication_level) == ("walking", 30, "pitch")
    assert all(rule.thresholds_minutes == (15, 30, 60) for rule in rules.values())
    assert rules["hospital"].as_record()["thresholds_minutes"] == [15, 30, 60]


def test_services_are_refused_when_the_two_protocols_disagree() -> None:
    other = copy.deepcopy(V1B)
    other["facility_sets"]["services"]["hospital"]["access_gap_threshold_minutes"] = 60
    with pytest.raises(access_diff.AccessDiffError, match="another mode or threshold"):
        access_diff.service_rules(V1A, other)

    missing = copy.deepcopy(V1B)
    del missing["facility_sets"]["services"]["main_road_entry"]
    with pytest.raises(access_diff.AccessDiffError, match="names no service"):
        access_diff.service_rules(V1A, missing)

    public_shelter = copy.deepcopy(V1B)
    public_shelter["facility_sets"]["services"]["ddpm_located_shelter"]["publication_level"] = "public"
    with pytest.raises(access_diff.AccessDiffError, match="pitch level"):
        access_diff.service_rules(V1A, public_shelter)


def test_closure_arguments_are_the_signed_thresholds_and_the_strict_delay_rule() -> None:
    arguments = access_diff.closure_arguments(V1B)

    assert arguments["length_thresholds_m"] == {
        "trunk": 50.0, "primary": 50.0, "secondary": 50.0, "tertiary": 30.0, "local": 30.0,
        "motorway": 50.0, "residential": 30.0, "unclassified": 30.0}
    assert arguments["strict_delays"] is True and arguments["delay_factor_k"] == {"strict": 2, "central": 4, "permissive": 6}
    assert "culvert=* is not read" in arguments["culvert_tag_handling"]


def test_closure_arguments_refuse_a_protocol_the_code_does_not_apply() -> None:
    changed = copy.deepcopy(V1B)
    changed["closure_rule_v1"]["parameters"]["closed_fraction_min"] = 0.6
    with pytest.raises(access_diff.AccessDiffError, match="not the ones"):
        access_diff.closure_arguments(changed)

    reworded = copy.deepcopy(V1B)
    reworded["closure_rule_v1"]["delay_under_strict"]["rule"] = "Under strict, no edge is delayed."
    with pytest.raises(access_diff.AccessDiffError, match="other words"):
        access_diff.closure_arguments(reworded)

    with pytest.raises(access_diff.AccessDiffError, match="does not hold"):
        access_diff.closure_arguments({})


def test_newly_lost_is_counted_only_for_residents_with_baseline_access() -> None:
    """EQ-04: a resident who had no access before the flood is never counted as losing it."""

    population = [
        cell("near", "b", 100.0),       # 10 minutes before; no route after
        cell("far", "d", 40.0),         # 30 minutes before: no access within 15 before or after
        cell("unconnected", None, 7.0, None),
    ]
    baseline = access_diff.cell_minutes(population, LINE, HOSPITAL, baseline_nodes=LINE_NODES)
    flooded = access_diff.cell_minutes(population, [LINE[1], LINE[2]], HOSPITAL, baseline_nodes=LINE_NODES)
    assert baseline == {"near": 10.0, "far": 30.0} and flooded == {"near": None, "far": None}

    diff = access_diff.service_diff(cells_of(population), baseline, flooded, [15, 30, 60])

    at_15 = diff["thresholds_minutes"]["15"]
    assert at_15["baseline_access_residents"] == 100.0 and at_15["newly_lost_residents"] == 100.0
    assert at_15["newly_lost_share"] == 1.0, "the 40 residents without baseline access are not in the denominator"
    at_30 = diff["thresholds_minutes"]["30"]
    assert at_30["baseline_access_residents"] == 140.0 and at_30["newly_lost_residents"] == 140.0
    assert diff["residents"] == 147.0 and diff["residents_not_connected_to_the_graph"] == 7.0
    assert diff["residents_connected_to_the_graph"] == 140.0
    assert diff["residents_with_a_baseline_route"] == 140.0 and diff["residents_with_a_route_in_the_flooded_run"] == 0.0


def test_a_resident_without_baseline_access_who_gets_worse_is_in_neither_count() -> None:
    population = [cell("kept", "b", 50.0), cell("already_out", "d", 30.0)]
    baseline = access_diff.cell_minutes(population, LINE, HOSPITAL, baseline_nodes=LINE_NODES)
    slower = [LINE[0], LINE[1], {**LINE[2], "normal_minutes": 40.0}]
    flooded = access_diff.cell_minutes(population, slower, HOSPITAL, baseline_nodes=LINE_NODES)

    at_15 = access_diff.service_diff(cells_of(population), baseline, flooded, [15])["thresholds_minutes"]["15"]

    assert (at_15["baseline_access_residents"], at_15["newly_lost_residents"], at_15["newly_lost_share"]) == (50.0, 0.0, 0.0)


def test_diff_logic_separates_delay_loss_route_loss_and_no_change() -> None:
    """One delayed edge and one closed edge: each cell falls in the count its two travel times give."""

    edges = [
        edge("ab", "a", "b", 10.0), edge("bc", "b", "c", 10.0), edge("cd", "c", "d", 10.0),
        edge("be", "b", "e", 4.0), edge("ef", "e", "f", 4.0),
    ]
    nodes = access_diff.graph_nodes(edges)
    population = [
        cell("stays", "b", 10.0),          # 10 -> 10
        cell("delayed_out", "c", 20.0),    # 20 -> 40: loses 30-minute access, keeps a route
        cell("delayed_far", "d", 5.0),     # 30 -> 50: loses 30-minute access, keeps a route
        cell("cut_off", "f", 8.0),         # 18 -> no route
        cell("with_snap", "e", 3.0, 250.0),  # 14 + 3 minutes of connector -> 17 both times
        cell("too_far", "e", 2.0, 251.0),  # not connected
    ]
    result = {"closure_rule_version": "closure_rule_v1", "level": "central", "closure_basis": "modelled_from_invented",
              "closed_edge_ids": ["ef"], "delayed_edges": [{"edge_id": "bc", "travel_time_factor": 3.0}],
              "intersected_edge_count": 2}
    changed = closure_rules.modified_edges(edges, result)

    baseline = access_diff.cell_minutes(population, edges, HOSPITAL, baseline_nodes=nodes)
    flooded = access_diff.cell_minutes(population, changed, HOSPITAL, baseline_nodes=nodes)
    diff = access_diff.service_diff(cells_of(population), baseline, flooded, [15, 30, 60])

    assert baseline == {"stays": 10.0, "delayed_out": 20.0, "delayed_far": 30.0, "cut_off": 18.0, "with_snap": 17.0}
    assert flooded == {"stays": 10.0, "delayed_out": 40.0, "delayed_far": 50.0, "cut_off": None, "with_snap": 17.0}
    at_30 = diff["thresholds_minutes"]["30"]
    assert at_30["baseline_access_residents"] == 46.0
    assert at_30["flooded_access_residents"] == 13.0
    assert at_30["newly_lost_residents"] == 33.0 and at_30["newly_gained_residents"] == 0.0
    assert at_30["newly_lost_share"] == pytest.approx(33.0 / 46.0)
    at_60 = diff["thresholds_minutes"]["60"]
    assert at_60["newly_lost_residents"] == 8.0, "a longer route within the threshold is not a lost access"
    assert diff["thresholds_minutes"]["15"]["baseline_access_residents"] == 10.0
    assert diff["residents_not_connected_to_the_graph"] == 2.0

    routes = access_diff.route_diff(cells_of(population), {"hospital": baseline}, {"hospital": flooded})
    assert routes["residents_with_baseline_route"] == 46.0 and routes["residents_losing_all_routes"] == 8.0
    assert routes["share_losing_all_routes"] == pytest.approx(8.0 / 46.0)


def test_a_zero_denominator_is_reported_with_a_reason_and_no_value() -> None:
    population = [cell("island", "x", 60.0)]
    edges = [*LINE, edge("xy", "x", "y", 1.0)]
    nodes = access_diff.graph_nodes(edges)
    baseline = access_diff.cell_minutes(population, edges, HOSPITAL, baseline_nodes=nodes)
    flooded = access_diff.cell_minutes(population, edges[1:], HOSPITAL, baseline_nodes=nodes)

    diff = access_diff.service_diff(cells_of(population), baseline, flooded, [30])
    at_30 = diff["thresholds_minutes"]["30"]
    assert at_30["baseline_access_residents"] == 0.0 and at_30["newly_lost_residents"] == 0.0
    assert at_30["newly_lost_share"] is None
    assert at_30["newly_lost_share_unavailable_reason"] == access_diff.NO_BASELINE_ACCESS

    routes = access_diff.route_diff(cells_of(population), {"hospital": baseline}, {"hospital": flooded})
    assert routes["residents_with_baseline_route"] == 0.0 and routes["share_losing_all_routes"] is None
    assert routes["share_unavailable_reason"] == access_diff.NO_BASELINE_ROUTE
    assert routes["connected_residents_without_a_baseline_route"] == 60.0

    assert access_diff.newly_lost_share(0.0, 0.0) == (None, access_diff.NO_BASELINE_ACCESS)
    assert access_diff.all_routes_lost_share(0.0, 0.0) == (None, access_diff.NO_BASELINE_ROUTE)
    assert access_diff.newly_lost_share(1.0, 4.0) == (0.25, None)
    with pytest.raises(access_diff.AccessDiffError, match="only for residents who had access"):
        access_diff.newly_lost_share(5.0, 4.0)
    with pytest.raises(access_diff.AccessDiffError, match="finite number"):
        access_diff.newly_lost_share(float("nan"), 4.0)


def test_an_empty_unit_gets_a_row_with_reasons_and_no_share() -> None:
    rules = [rule for rule in access_diff.service_rules(V1A, V1B) if rule.publication_level == "public"]
    population = [cell("p1", "b", 10.0)]
    baseline = access_diff.cell_minutes(population, LINE, HOSPITAL, baseline_nodes=LINE_NODES)
    runs = {"hospital": baseline, "main_road_entry": baseline}

    table = access_diff.unit_rows(cells_of(population, "U1"), ["U1", "U2"], rules, runs, runs)

    empty = next(row for row in table["units"] if row["unit_id"] == "U2")
    assert empty["residents"] == 0.0 and empty["demand_cells"] == 0
    assert empty["access_gap_inputs_unavailable_reason"] == access_diff.NO_BASELINE_ACCESS
    assert empty["routes"]["share_unavailable_reason"] == access_diff.NO_BASELINE_ROUTE
    assert empty["access"]["hospital"]["thresholds_minutes"]["30"]["newly_lost_share"] is None


def test_a_cell_whose_node_loses_every_edge_has_lost_its_routes_and_is_still_connected() -> None:
    population = [cell("at_b", "b", 12.0), cell("at_hospital", "a", 4.0)]
    baseline = access_diff.cell_minutes(population, LINE, HOSPITAL, baseline_nodes=LINE_NODES)
    flooded = access_diff.cell_minutes(population, [LINE[2]], HOSPITAL, baseline_nodes=LINE_NODES)

    assert flooded == {"at_b": None, "at_hospital": 0.0}, "the hospital's own node keeps its zero-length trip"
    diff = access_diff.service_diff(cells_of(population), baseline, flooded, [30])
    assert diff["residents_not_connected_to_the_graph"] == 0.0
    assert diff["thresholds_minutes"]["30"]["newly_lost_residents"] == 12.0

    with pytest.raises(access_diff.AccessDiffError, match="baseline graph does not have"):
        access_diff.cell_minutes(population, [edge("zz", "y", "z", 1.0)], HOSPITAL, baseline_nodes=LINE_NODES)


def test_the_two_runs_must_cover_the_same_cells() -> None:
    cells = cells_of([cell("p1", "a", 1.0), cell("p2", "b", 1.0)])

    with pytest.raises(access_diff.AccessDiffError, match="same connected cells"):
        access_diff.service_diff(cells, {"p1": 1.0, "p2": 2.0}, {"p1": 1.0}, [30])
    assert access_diff.service_diff(cells[:1], {"p1": 1.0, "p2": 2.0}, {"p1": 1.0, "p2": 2.0}, [30])["residents"] == 1.0, (
        "a group is compared against runs that cover the whole frame")
    with pytest.raises(access_diff.AccessDiffError, match="unique"):
        access_diff.service_diff([cells[0], cells[0]], {"p1": 1.0}, {"p1": 1.0}, [30])
    with pytest.raises(access_diff.AccessDiffError, match="travel time"):
        access_diff.service_diff(cells, {"p1": -1.0}, {"p1": 1.0}, [30])
    with pytest.raises(access_diff.AccessDiffError, match="thresholds"):
        access_diff.service_diff(cells, {"p1": 1.0}, {"p1": 1.0}, [30, 30])
    with pytest.raises(access_diff.AccessDiffError, match="thresholds"):
        access_diff.service_diff(cells, {"p1": 1.0}, {"p1": 1.0}, [0])
    with pytest.raises(access_diff.AccessDiffError, match="same services"):
        access_diff.route_diff(cells, {"hospital": {"p1": 1.0}}, {"main_road_entry": {"p1": 1.0}})
    with pytest.raises(access_diff.AccessDiffError, match="cover the same connected cells"):
        access_diff.route_diff(cells, {"a": {"p1": 1.0}, "b": {"p2": 1.0}}, {"a": {"p1": 1.0}, "b": {"p2": 1.0}})
    with pytest.raises(access_diff.AccessDiffError, match="unique"):
        access_diff.cell_minutes([cell("p1", "a", 1.0), cell("p1", "b", 1.0)], LINE, HOSPITAL, baseline_nodes=LINE_NODES)


def test_a_gain_is_reported_and_never_set_against_a_loss() -> None:
    cells = cells_of([cell("loses", "a", 10.0), cell("gains", "b", 6.0)])

    at_30 = access_diff.service_diff(cells, {"loses": 20.0, "gains": 45.0}, {"loses": 31.0, "gains": 29.0}, [30])[
        "thresholds_minutes"]["30"]

    assert at_30["newly_lost_residents"] == 10.0 and at_30["newly_gained_residents"] == 6.0
    assert at_30["baseline_access_residents"] == 10.0 and at_30["flooded_access_residents"] == 6.0
    assert at_30["newly_lost_share"] == 1.0


def test_losing_all_routes_needs_every_service_to_be_out_of_reach() -> None:
    cells = cells_of([cell("keeps_main_road", "a", 30.0), cell("loses_both", "b", 20.0), cell("had_none", "c", 9.0),
                      cell("only_slower", "d", 5.0)])
    baseline = {
        "hospital": {"keeps_main_road": 12.0, "loses_both": 12.0, "had_none": None, "only_slower": 10.0},
        "main_road_entry": {"keeps_main_road": 3.0, "loses_both": None, "had_none": None, "only_slower": 2.0},
    }
    flooded = {
        "hospital": {"keeps_main_road": None, "loses_both": None, "had_none": None, "only_slower": 500.0},
        "main_road_entry": {"keeps_main_road": 9.0, "loses_both": None, "had_none": None, "only_slower": None},
    }

    routes = access_diff.route_diff(cells, baseline, flooded)

    assert routes["services"] == ["hospital", "main_road_entry"]
    assert routes["residents_with_baseline_route"] == 55.0
    assert routes["residents_losing_all_routes"] == 20.0, "a route to a main road, or a much longer one, is still a route"
    assert routes["connected_residents_without_a_baseline_route"] == 9.0
    assert routes["share_losing_all_routes"] == pytest.approx(20.0 / 55.0)


def _random_case(seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """A 6 x 6 grid of streets with random times, cells at random nodes and three destinations."""

    rng = random.Random(seed)
    edges = []
    for row in range(6):
        for column in range(6):
            if column < 5:
                edges.append(edge(f"h-{row}-{column}", f"n{row}{column}", f"n{row}{column + 1}", rng.uniform(1.0, 9.0)))
            if row < 5:
                edges.append(edge(f"v-{row}-{column}", f"n{row}{column}", f"n{row + 1}{column}", rng.uniform(1.0, 9.0)))
    nodes = sorted(access_diff.graph_nodes(edges))
    population = [cell(f"cell-{index:03d}", rng.choice(nodes), rng.uniform(0.5, 30.0), rng.choice([0.0, 40.0, 120.0, 249.0, 260.0]))
                  for index in range(80)]
    population.append(cell("cell-no-node", None, 5.0, None))
    sites = [site("site-a", "n00", 0.0), site("site-b", "n35", 60.0), site("site-c", "n52", 101.0)]
    return edges, population, sites


@pytest.mark.parametrize("seed", [3, 11, 29])
def test_cell_minutes_gives_the_travel_times_of_calculate_total_access(seed: int) -> None:
    """Baseline and closed-edge runs: the same route flags, access flags and (to rounding) minutes."""

    edges, population, sites = _random_case(seed)
    closed = random.Random(seed + 1).sample([row["edge_id"] for row in edges], 22)
    nodes = access_diff.graph_nodes(edges)
    reference = calculate_total_access(population, edges, sites, scenario={"closed_edge_ids": closed})
    expected_before = {row["population_id"]: row["normal_access_minutes"] for row in reference["node_results"]
                       if row["snap_status"] == "connected"}
    expected_after = {row["population_id"]: row["scenario_access_minutes"] for row in reference["node_results"]
                      if row["snap_status"] == "connected"}

    baseline = access_diff.cell_minutes(population, edges, sites, baseline_nodes=nodes)
    flooded = access_diff.cell_minutes(population, [row for row in edges if row["edge_id"] not in closed], sites,
                                       baseline_nodes=nodes)

    for ours, theirs in ((baseline, expected_before), (flooded, expected_after)):
        check = access_diff.access_flags_differ(ours, theirs, [15, 30, 60])
        assert check["cells_that_differ"] == 0 and check["largest_difference_minutes"] < 1e-9
        assert check["cells_compared"] == len(theirs) > 0
    assert any(value is None for value in flooded.values()), "the closures cut some cell off, so that case is compared"
    diff = access_diff.service_diff(cells_of(population), baseline, flooded, [15, 30, 60])
    for limit in (15, 30, 60):
        assert diff["thresholds_minutes"][str(limit)]["newly_lost_residents"] == pytest.approx(
            reference["totals"][f"people_losing_{limit}_min_access"])
    assert diff["residents_not_connected_to_the_graph"] == pytest.approx(reference["totals"]["unconnected_population"])


def test_a_delayed_run_gives_the_travel_times_of_calculate_total_access_on_the_modified_edges() -> None:
    edges, population, sites = _random_case(5)
    result = {"closure_rule_version": "closure_rule_v1", "level": "central", "closure_basis": "modelled_from_invented",
              "closed_edge_ids": [], "intersected_edge_count": 12,
              "delayed_edges": [{"edge_id": row["edge_id"], "travel_time_factor": 1 + 4 * 0.3} for row in edges[::5]]}
    changed = closure_rules.modified_edges(edges, result)
    reference = calculate_total_access(population, changed, sites)
    expected = {row["population_id"]: row["normal_access_minutes"] for row in reference["node_results"]
                if row["snap_status"] == "connected"}

    flooded = access_diff.cell_minutes(population, changed, sites, baseline_nodes=access_diff.graph_nodes(edges))

    check = access_diff.access_flags_differ(flooded, expected, [15, 30, 60])
    assert check["cells_that_differ"] == 0 and check["largest_difference_minutes"] < 1e-9
    baseline = access_diff.cell_minutes(population, edges, sites, baseline_nodes=access_diff.graph_nodes(edges))
    assert all(flooded[key] >= baseline[key] for key in baseline), "a delay never shortens a route"
    assert any(flooded[key] > baseline[key] for key in baseline)


def test_access_flags_differ_counts_a_route_and_a_threshold_difference() -> None:
    check = access_diff.access_flags_differ({"a": 10.0, "b": None, "c": 29.0, "d": 12.0},
                                            {"a": 10.5, "b": 3.0, "c": 31.0, "d": 12.0}, [30])

    assert check == {"cells_compared": 4, "cells_that_differ": 2, "largest_difference_minutes": 2.0}
    with pytest.raises(access_diff.AccessDiffError, match="same connected cells"):
        access_diff.access_flags_differ({"a": 1.0}, {"b": 1.0}, [30])


def test_a_cell_counts_for_the_unit_that_holds_its_centre() -> None:
    units = [("U1", box(0.0, 0.0, 1.0, 1.0)), ("U2", box(1.0, 0.0, 2.0, 1.0))]
    population = [
        {"population_id": "inside_1", "longitude": 0.5, "latitude": 0.5, "total_population": 3.0},
        {"population_id": "inside_2", "longitude": 1.5, "latitude": 0.2, "total_population": 4.0},
        {"population_id": "on_the_shared_edge", "longitude": 1.0, "latitude": 0.5, "total_population": 5.0},
        {"population_id": "outside", "longitude": 5.0, "latitude": 5.0, "total_population": 6.0},
    ]

    assignment = access_diff.assign_cells(population, units)

    assert assignment["inside_1"] == {"unit_id": "U1", "unit_assignment": access_diff.CELL_IN_ONE_UNIT}
    assert assignment["inside_2"]["unit_id"] == "U2"
    assert assignment["on_the_shared_edge"] == {"unit_id": None, "unit_assignment": access_diff.CELL_IN_SEVERAL_UNITS}
    assert assignment["outside"] == {"unit_id": None, "unit_assignment": access_diff.CELL_IN_NO_UNIT}
    cells = access_diff.demand_cells(population, assignment)
    assert [row["population_id"] for row in cells] == sorted(row["population_id"] for row in population)
    assert {row["population_id"]: row["unit_id"] for row in cells}["on_the_shared_edge"] is None

    with pytest.raises(access_diff.AccessDiffError, match="unit IDs must be unique"):
        access_diff.assign_cells(population, [("U1", box(0, 0, 1, 1)), ("U1", box(1, 0, 2, 1))])
    with pytest.raises(access_diff.AccessDiffError, match="population IDs must be unique"):
        access_diff.assign_cells([population[0], population[0]], units)
    with pytest.raises(access_diff.AccessDiffError, match="unit assignment"):
        access_diff.demand_cells(population, {})
    with pytest.raises(access_diff.AccessDiffError, match="finite number"):
        access_diff.demand_cells([{**population[0], "total_population": -1.0}], assignment)


def _two_service_table() -> tuple[dict[str, Any], tuple[access_diff.ServiceRule, ...]]:
    rules = tuple(rule for rule in access_diff.service_rules(V1A, V1B) if rule.publication_level == "public")
    cells = [
        {"population_id": "u1-a", "unit_id": "U1", "residents": 100.0},
        {"population_id": "u1-b", "unit_id": "U1", "residents": 50.0},
        {"population_id": "u2-a", "unit_id": "U2", "residents": 30.0},
        {"population_id": "u2-off-graph", "unit_id": "U2", "residents": 8.0},
        {"population_id": "nowhere", "unit_id": None, "residents": 2.0},
    ]
    baseline = {
        "hospital": {"u1-a": 20.0, "u1-b": 28.0, "u2-a": 45.0, "nowhere": 10.0},
        "main_road_entry": {"u1-a": 5.0, "u1-b": 14.0, "u2-a": 16.0, "nowhere": 1.0},
    }
    flooded = {
        "hospital": {"u1-a": 22.0, "u1-b": 33.0, "u2-a": None, "nowhere": 10.0},
        "main_road_entry": {"u1-a": 5.0, "u1-b": 15.5, "u2-a": None, "nowhere": 1.0},
    }
    return access_diff.unit_rows(cells, ["U2", "U1"], rules, baseline, flooded), rules


def test_unit_rows_hold_every_threshold_and_the_inputs_of_the_two_components() -> None:
    table, _rules = _two_service_table()

    assert [row["unit_id"] for row in table["units"]] == ["U1", "U2"]
    first, second = table["units"]
    assert first["residents"] == 150.0 and first["demand_cells"] == 2
    assert first["access_gap_inputs"] == {
        "hospital": {"mode": "vehicle", "threshold_minutes": 30, "baseline_access_residents": 150.0, "newly_lost_residents": 50.0},
        "main_road_entry": {"mode": "vehicle", "threshold_minutes": 15, "baseline_access_residents": 150.0,
                            "newly_lost_residents": 50.0},
    }
    assert first["access_gap_inputs_unavailable_reason"] is None
    assert first["road_criticality_inputs"] == {"residents_losing_all_routes": 0.0, "residents_with_baseline_route": 150.0}
    assert set(first["access"]["hospital"]["thresholds_minutes"]) == {"15", "30", "60"}
    assert first["access"]["hospital"]["thresholds_minutes"]["60"]["newly_lost_residents"] == 0.0
    assert first["access"]["hospital"]["access_gap_threshold_minutes"] == 30

    assert second["residents"] == 38.0
    assert second["access"]["hospital"]["residents_not_connected_to_the_graph"] == 8.0
    assert second["access_gap_inputs"]["hospital"]["baseline_access_residents"] == 0.0, "45 minutes is over the threshold"
    assert second["access_gap_inputs"]["main_road_entry"]["baseline_access_residents"] == 0.0
    assert second["access_gap_inputs_unavailable_reason"] == access_diff.NO_BASELINE_ACCESS
    assert second["road_criticality_inputs"] == {"residents_losing_all_routes": 30.0, "residents_with_baseline_route": 30.0}
    assert second["routes"]["share_losing_all_routes"] == 1.0

    assert table["cells_in_no_unit"]["demand_cells"] == 1 and table["cells_in_no_unit"]["residents"] == 2.0
    assert table["whole_frame"]["residents"] == 190.0
    assert table["whole_frame"]["road_criticality_inputs"]["residents_with_baseline_route"] == 182.0


def test_no_component_value_is_in_a_row_and_the_rows_fit_frame_v1_as_they_are() -> None:
    """The rows are inputs. The component functions of plan task E2 take them unchanged, here on invented units."""

    table, _rules = _two_service_table()

    def keys(value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for child in value.values() for key in keys(child)}
        if isinstance(value, list):
            return {key for child in value for key in keys(child)}
        return set()

    assert not {key for key in keys(table) if key.endswith("_0_100") or "fpps" in key or "action_class" in key}

    frame = normalisation.load_planning_frame(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json",
                                              DOCS / "RECEIPTS.jsonl")
    first, second = table["units"]
    gap = normalisation.access_gap(frame, services=first["access_gap_inputs"])
    assert gap["publication_level"] == "public" and gap["value_0_100"] == pytest.approx(100.0 * 100.0 / 300.0)
    criticality = normalisation.road_criticality(frame, **second["road_criticality_inputs"])
    assert criticality["value_0_100"] == 100.0
    with pytest.raises(normalisation.NormalisationError, match="no resident had baseline access"):
        normalisation.access_gap(frame, services=second["access_gap_inputs"])


def test_unit_rows_refuse_a_cell_of_an_unlisted_unit_and_a_missing_service() -> None:
    rules = tuple(rule for rule in access_diff.service_rules(V1A, V1B) if rule.publication_level == "public")
    cells = [{"population_id": "p", "unit_id": "U9", "residents": 1.0}]
    runs = {"hospital": {"p": 1.0}, "main_road_entry": {"p": 1.0}}

    with pytest.raises(access_diff.AccessDiffError, match="not a unit of the table"):
        access_diff.unit_rows(cells, ["U1"], rules, runs, runs)
    with pytest.raises(access_diff.AccessDiffError, match="no run was made"):
        access_diff.unit_rows(cells, ["U9"], rules, {"hospital": {"p": 1.0}}, runs)
    with pytest.raises(access_diff.AccessDiffError, match="unit IDs must be unique"):
        access_diff.unit_rows(cells, ["U9", "U9"], rules, runs, runs)
    with pytest.raises(access_diff.AccessDiffError, match="services of the table"):
        access_diff.unit_rows(cells, ["U9"], rules[:1], runs, runs)
    stray = {"hospital": {"p": 1.0, "q": 2.0}, "main_road_entry": {"p": 1.0}}
    with pytest.raises(access_diff.AccessDiffError, match="not a demand cell"):
        access_diff.unit_rows(cells, ["U9"], rules, stray, stray)


def _flooded_street() -> tuple[list[dict[str, Any]], dict[str, list[float]], Any]:
    """Five streets of 100 m in a row, a hospital at the west end, and a flood over parts of three of them.

    Inside the extent: 10 m of s1, 26 m of s2 (a bridge), 40 m of s3, all of s4.
    """

    coordinates = {f"n{index}": lonlat(index * 100.0, 0.0) for index in range(6)}
    edges = [
        edge("s0", "n0", "n1", 1.0), edge("s1", "n1", "n2", 1.0),
        edge("s2", "n2", "n3", 1.0, bridge="yes"), edge("s3", "n3", "n4", 1.0), edge("s4", "n4", "n5", 1.0),
    ]
    patches = [box(190.0, -5.0, 200.0, 5.0), box(200.0, -5.0, 226.0, 5.0), box(300.0, -5.0, 340.0, 5.0), box(400.0, -5.0, 500.0, 5.0)]
    extent = transform(lambda x, y: TO_WGS84(x + ORIGIN_X, y + ORIGIN_Y), patches[0].union(patches[1]).union(patches[2]).union(patches[3]))
    return edges, coordinates, extent


def test_the_three_closure_levels_give_three_flooded_runs() -> None:
    edges, coordinates, extent = _flooded_street()
    arguments = access_diff.closure_arguments(V1B)
    intersections = closure_rules.edge_intersections(edges, coordinates, extent)
    lengths = {row["edge_id"]: round(row["intersection_length_m"], 3) for row in intersections}
    assert lengths == {"s1": 10.0, "s2": 26.0, "s3": 40.0, "s4": 100.0}

    closed: dict[str, list[str]] = {}
    delayed: dict[str, dict[str, float]] = {}
    summaries = {}
    for level in closure_rules.LEVELS:
        changed, result = access_diff.flooded_edges(level, edges, intersections, flood_input_id="invented", arguments=arguments)
        closed[level] = result["closed_edge_ids"]
        delayed[level] = {row["edge_id"]: round(row["travel_time_factor"], 6) for row in result["delayed_edges"]}
        summaries[level] = access_diff.closure_summary(result, edges)
        assert {row["edge_id"] for row in changed} == {row["edge_id"] for row in edges} - set(closed[level])

    assert closed["permissive"] == ["s1", "s2", "s3", "s4"] and delayed["permissive"] == {}
    # Strict: closed at half the edge; an open edge with at least 20 m inside is delayed with k = 2.
    assert closed["strict"] == ["s4"] and delayed["strict"] == {"s2": 1.52, "s3": 1.8}
    # Central: the bridge closes at a quarter; a residential edge closes at 30 m; 10 m is neither closed nor delayed.
    assert closed["central"] == ["s2", "s3", "s4"] and delayed["central"] == {}
    assert summaries["central"]["closed_bridge_tagged_edges"] == 1
    assert summaries["central"]["intersected_edges_left_open"] == 1
    assert summaries["strict"]["delayed_edges"] == 2 and summaries["strict"]["largest_travel_time_factor"] == pytest.approx(1.8)
    assert summaries["strict"]["closure_basis"] == "modelled_from_invented"
    assert len({summary["closure_result_sha256"] for summary in summaries.values()}) == 3

    with pytest.raises(access_diff.AccessDiffError, match="unknown closure level"):
        access_diff.flooded_edges("lenient", edges, intersections, flood_input_id="invented", arguments=arguments)


def test_a_road_class_without_a_signed_threshold_is_refused_not_guessed() -> None:
    edges, coordinates, extent = _flooded_street()
    edges[1]["road_class"] = "track"
    intersections = closure_rules.edge_intersections(edges, coordinates, extent)

    with pytest.raises(access_diff.AccessDiffError, match="no length threshold for road class 'track'"):
        access_diff.flooded_edges("central", edges, intersections, flood_input_id="invented",
                                  arguments=access_diff.closure_arguments(V1B))


def test_open_points_are_reported_with_what_the_signed_files_say() -> None:
    identifiers = [point["id"] for point in access_diff.OPEN_POINTS]

    assert identifiers == [f"E5-OP{index}" for index in range(1, len(identifiers) + 1)]
    for point in access_diff.OPEN_POINTS:
        assert set(point) == {"id", "point", "signed_files_say", "what_this_task_does", "for_the_owners"}
        assert all(isinstance(value, str) and value.strip() for value in point.values())
