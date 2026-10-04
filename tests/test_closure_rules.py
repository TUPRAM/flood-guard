"""Closure rule v1 on invented edges, and its agreement with the finals code.

The edges and extents here are synthetic. No test computes an access result for
a real place, an FPPS, a class or an ensemble.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, box, mapping
from shapely.ops import transform

from floodguard.closure_rules import (
    BRIDGE_CULVERT_CLOSED_FRACTION_MIN,
    CLOSED_FRACTION_MIN,
    CLOSURE_RULE_VERSION,
    DELAY_FACTOR_K,
    DELAY_MIN_INTERSECTED_LENGTH_M,
    LEVELS,
    MIN_INTERSECTION_M,
    PLAN_LENGTH_THRESHOLD_M,
    ClosureRuleError,
    apply_closure_rule,
    edge_intersections,
    edge_state,
    is_bridge_or_culvert,
    modified_edges,
)
from floodguard.evidence_flood_scenario import candidate_flood_scenario

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
RECEIPT = ROOT / "outputs" / "planning_v1" / "closure_rule_v1_regression.json"
SCRIPT = ROOT / "scripts" / "check_closure_rule_regression.py"
DATABASE = ROOT / "apps" / "web" / "public" / "evidence-library" / "databases" / "aoi-01_mae_sai_core-finals.json.gz"
# Every class the context builder can emit; OI-05 has to cover the three the plan leaves out.
ALL_CLASS_THRESHOLDS = {**PLAN_LENGTH_THRESHOLD_M, "motorway": 50.0, "residential": 30.0, "unclassified": 30.0}

TO_WGS84 = Transformer.from_crs(32647, 4326, always_xy=True).transform
ORIGIN_X, ORIGIN_Y = 590000.0, 2255000.0


def _lonlat(x: float, y: float) -> list[float]:
    lon, lat = TO_WGS84(ORIGIN_X + x, ORIGIN_Y + y)
    return [lon, lat]


def _extent(*boxes: tuple[float, float, float, float]):
    """A flood extent in WGS84 built from metre boxes around the test origin."""

    parts = [
        transform(TO_WGS84, box(ORIGIN_X + x0, ORIGIN_Y + y0, ORIGIN_X + x1, ORIGIN_Y + y1))
        for x0, y0, x1, y1 in boxes
    ]
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)


def _network() -> tuple[list[dict], dict[str, list[float]]]:
    """Five 100 m edges in a row, west to east, plus one edge far to the north."""

    nodes = {f"n{index}": _lonlat(100.0 * index, 0.0) for index in range(6)}
    nodes["far_a"], nodes["far_b"] = _lonlat(0.0, 5000.0), _lonlat(100.0, 5000.0)
    classes = ["primary", "tertiary", "residential", "local", "secondary"]
    edges = [
        {"edge_id": f"e{index}", "from_node": f"n{index}", "to_node": f"n{index + 1}",
         "road_class": classes[index], "bridge": "no", "tunnel": "no", "normal_minutes": 1.0}
        for index in range(5)
    ]
    edges.append({"edge_id": "far", "from_node": "far_a", "to_node": "far_b", "road_class": "local",
                  "bridge": "no", "tunnel": "no", "normal_minutes": 1.0})
    return edges, nodes


def test_intersection_is_measured_on_the_straight_segment_in_metres() -> None:
    edges, nodes = _network()
    # Covers the last 40 m of e0, all of e1 and the first 10 m of e2.
    rows = edge_intersections(edges, nodes, _extent((60.0, -5.0, 210.0, 5.0)))
    assert [row["edge_id"] for row in rows] == ["e0", "e1", "e2"]
    by_id = {row["edge_id"]: row for row in rows}
    assert by_id["e0"]["intersection_length_m"] == pytest.approx(40.0, abs=0.01)
    assert by_id["e0"]["intersection_fraction"] == pytest.approx(0.4, abs=1e-3)
    assert by_id["e1"]["intersection_fraction"] == pytest.approx(1.0, abs=1e-6)
    assert by_id["e2"]["intersection_length_m"] == pytest.approx(10.0, abs=0.01)
    assert all(row["intersection_fraction"] <= 1.0 for row in rows)


def test_touching_at_a_point_and_an_empty_extent_close_nothing() -> None:
    edges, nodes = _network()
    assert edge_intersections(edges, nodes, Polygon()) == []
    assert edge_intersections([], nodes, _extent((0.0, -5.0, 50.0, 5.0))) == []
    # The box corner sits on the edge line: a point contact has no length.
    rows = edge_intersections(edges, nodes, _extent((150.0, 0.0, 160.0, 10.0)))
    assert all(row["intersection_length_m"] > MIN_INTERSECTION_M for row in rows)
    result = apply_closure_rule("strict", edges, rows, flood_input_id="synthetic", strict_delays=False)
    assert result["closed_edge_ids"] == []


def test_intersections_refuse_bad_inputs() -> None:
    edges, nodes = _network()
    with pytest.raises(ClosureRuleError, match="unique"):
        edge_intersections([*edges, edges[0]], nodes, _extent((0.0, -5.0, 50.0, 5.0)))
    with pytest.raises(ClosureRuleError, match="unknown node"):
        edge_intersections(edges, {key: value for key, value in nodes.items() if key != "n3"},
                           _extent((0.0, -5.0, 50.0, 5.0)))
    bowtie = Polygon([(99.0, 20.0), (99.1, 20.1), (99.1, 20.0), (99.0, 20.1)])
    with pytest.raises(ClosureRuleError, match="valid"):
        edge_intersections(edges, nodes, bowtie)


def test_permissive_closes_on_any_intersection() -> None:
    assert edge_state("permissive", intersection_length_m=2e-6, intersection_fraction=0.0,
                      road_class="primary", bridge_or_culvert=False) == "closed"
    assert edge_state("permissive", intersection_length_m=1e-6, intersection_fraction=0.0,
                      road_class="primary", bridge_or_culvert=False) == "open"
    assert edge_state("permissive", intersection_length_m=0.0, intersection_fraction=0.0,
                      road_class="made_up_class", bridge_or_culvert=False) == "open"


def test_strict_closes_at_half_and_needs_the_delay_decision_only_when_it_matters() -> None:
    def strict(length: float, fraction: float, **extra) -> str:
        return edge_state("strict", intersection_length_m=length, intersection_fraction=fraction,
                          road_class="primary", bridge_or_culvert=True, **extra)

    assert strict(60.0, CLOSED_FRACTION_MIN) == "closed"
    assert strict(500.0, 0.49, strict_delays=False) == "open"  # no length or bridge rule under strict
    assert strict(500.0, 0.49, strict_delays=True) == "delayed"
    assert strict(DELAY_MIN_INTERSECTED_LENGTH_M - 0.01, 0.1) == "open"
    with pytest.raises(ClosureRuleError, match="OI-05"):
        strict(DELAY_MIN_INTERSECTED_LENGTH_M, 0.1)


@pytest.mark.parametrize("road_class, length, fraction, bridge, expected", [
    ("primary", 50.0, 0.1, False, "closed"),
    ("primary", 49.99, 0.1, False, "delayed"),
    ("secondary", 19.99, 0.1, False, "open"),
    ("tertiary", 30.0, 0.05, False, "closed"),
    ("tertiary", 29.99, 0.05, False, "delayed"),
    ("local", 20.0, 0.05, False, "delayed"),
    ("local", 5.0, 0.5, False, "closed"),
    ("local", 5.0, BRIDGE_CULVERT_CLOSED_FRACTION_MIN, True, "closed"),
    ("local", 5.0, 0.24, True, "open"),
    ("local", 5.0, 0.3, False, "open"),
])
def test_central_uses_fraction_length_by_class_and_the_bridge_rule(
    road_class: str, length: float, fraction: float, bridge: bool, expected: str
) -> None:
    assert edge_state("central", intersection_length_m=length, intersection_fraction=fraction,
                      road_class=road_class, bridge_or_culvert=bridge,
                      length_thresholds_m=PLAN_LENGTH_THRESHOLD_M) == expected


def test_central_refuses_a_road_class_the_plan_leaves_out() -> None:
    for road_class in ("motorway", "residential", "unclassified"):
        with pytest.raises(ClosureRuleError, match="OI-05"):
            edge_state("central", intersection_length_m=25.0, intersection_fraction=0.1, road_class=road_class,
                       bridge_or_culvert=False, length_thresholds_m=PLAN_LENGTH_THRESHOLD_M)
        assert edge_state("central", intersection_length_m=25.0, intersection_fraction=0.6, road_class=road_class,
                          bridge_or_culvert=False, length_thresholds_m=PLAN_LENGTH_THRESHOLD_M) == "closed"
    with pytest.raises(ClosureRuleError, match="positive"):
        edge_state("central", intersection_length_m=25.0, intersection_fraction=0.1, road_class="local",
                   bridge_or_culvert=False, length_thresholds_m={"local": 0})


def test_edge_state_refuses_unknown_levels_and_bad_numbers() -> None:
    common = {"road_class": "local", "bridge_or_culvert": False}
    with pytest.raises(ClosureRuleError, match="unknown closure level"):
        edge_state("medium", intersection_length_m=1.0, intersection_fraction=0.1, **common)
    with pytest.raises(ClosureRuleError):
        edge_state("strict", intersection_length_m=-1.0, intersection_fraction=0.1, **common)
    with pytest.raises(ClosureRuleError):
        edge_state("strict", intersection_length_m=1.0, intersection_fraction=1.2, **common)


def test_bridge_and_culvert_tags_are_the_plan_tags() -> None:
    assert is_bridge_or_culvert({"bridge": "yes", "tunnel": "no"})
    assert is_bridge_or_culvert({"bridge": "no", "tunnel": "culvert"})
    assert is_bridge_or_culvert({"bridge": "no", "tunnel": "no", "culvert": "pipe"})
    assert not is_bridge_or_culvert({"bridge": "no", "tunnel": "yes"})
    assert not is_bridge_or_culvert({"bridge": "viaduct", "tunnel": "no", "culvert": "no"})


def test_levels_are_nested_and_the_delay_factor_is_one_plus_k_times_f() -> None:
    edges, nodes = _network()
    rows = edge_intersections(edges, nodes, _extent((60.0, -5.0, 210.0, 5.0), (330.0, -5.0, 355.0, 5.0)))
    results = {
        level: apply_closure_rule(level, edges, rows, flood_input_id="synthetic",
                                  length_thresholds_m=ALL_CLASS_THRESHOLDS, strict_delays=True)
        for level in LEVELS
    }
    strict, central, permissive = (set(results[level]["closed_edge_ids"]) for level in LEVELS)
    assert strict <= central <= permissive
    assert strict == {"e1"}
    assert permissive == {"e0", "e1", "e2", "e3"}
    assert central == {"e1"}  # e0: 40 m of a primary road (L = 50 m); e3: 25 m of a local road (L = 30 m)
    delayed = {row["edge_id"]: row["travel_time_factor"] for row in results["central"]["delayed_edges"]}
    assert set(delayed) == {"e0", "e3"}
    assert delayed["e0"] == pytest.approx(1 + DELAY_FACTOR_K["central"] * 0.4, abs=1e-3)
    assert {row["edge_id"] for row in results["strict"]["delayed_edges"]} == {"e0", "e3"}
    assert results["permissive"]["delayed_edges"] == []
    for level in LEVELS:
        assert results[level]["closure_basis"] == "modelled_from_synthetic"
        assert results[level]["closure_rule_version"] == CLOSURE_RULE_VERSION


def test_modified_edge_list_drops_closed_edges_and_slows_delayed_ones() -> None:
    edges, nodes = _network()
    rows = edge_intersections(edges, nodes, _extent((60.0, -5.0, 210.0, 5.0)))
    result = apply_closure_rule("central", edges, rows, flood_input_id="synthetic",
                                length_thresholds_m=ALL_CLASS_THRESHOLDS)
    changed = {row["edge_id"]: row for row in modified_edges(edges, result)}
    assert "e1" not in changed and len(changed) == len(edges) - 1
    assert changed["e0"]["normal_minutes"] == pytest.approx(1 + 4 * 0.4, abs=1e-3)
    assert changed["e0"]["closure_state"] == "delayed"
    assert changed["far"] == next(edge for edge in edges if edge["edge_id"] == "far")
    assert edges[0]["normal_minutes"] == 1.0  # the input is not changed


def test_apply_refuses_unknown_or_repeated_edges_and_a_missing_input_name() -> None:
    edges, _nodes = _network()
    row = {"edge_id": "e0", "intersection_length_m": 10.0, "intersection_fraction": 0.1}
    with pytest.raises(ClosureRuleError):
        apply_closure_rule("permissive", edges, [row, row], flood_input_id="synthetic")
    with pytest.raises(ClosureRuleError):
        apply_closure_rule("permissive", edges, [{**row, "edge_id": "nope"}], flood_input_id="synthetic")
    with pytest.raises(ClosureRuleError, match="flood input"):
        apply_closure_rule("permissive", edges, [row], flood_input_id="")


def test_permissive_equals_the_finals_code_on_a_synthetic_context() -> None:
    """The finals function and the new module give the same closed edges and lengths."""

    edges, nodes = _network()
    extent = _extent((60.0, -5.0, 210.0, 5.0), (330.0, -5.0, 355.0, 5.0), (499.9999995, -1.0, 600.0, 1.0))
    collection = {"type": "FeatureCollection",
                  "features": [{"type": "Feature", "geometry": mapping(extent), "properties": {}}]}
    footprint = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {},
        "geometry": mapping(transform(TO_WGS84, box(ORIGIN_X - 1000, ORIGIN_Y - 1000, ORIGIN_X + 2000, ORIGIN_Y + 6000))),
    }]}
    context = {
        "canonical_sha256": "a" * 64,
        "node_coordinates": nodes,
        "edges": edges,
        "population": [{"population_id": "p", "subdistrict_id": "synthetic-unit", "total_population": 10,
                        "node_id": "n0", "snap_distance_m": 0, "longitude": nodes["n0"][0], "latitude": nodes["n0"][1]}],
        "osm_facilities": [{"facility_id": "h", "service_type": "hospital", "candidate_destination_eligible": True,
                            "within_routing_context": True, "node_id": "n5", "snap_distance_m": 0}],
    }
    provenance = {"event_id": "synthetic", "official_warning": False, "eligible_for_validation": False,
                  "source_timestamp": "2024-09-15T23:16:01Z"}
    finals = candidate_flood_scenario(context, collection, footprint, provenance)["closed_edges"]
    rows = edge_intersections(edges, nodes, extent)
    result = apply_closure_rule("permissive", edges, rows, flood_input_id="synthetic")
    assert result["closed_edge_ids"] == [row["edge_id"] for row in finals]
    assert rows == finals


def test_committed_regression_receipt_matches_the_protocol_and_the_finals_database() -> None:
    if not RECEIPT.exists():
        pytest.skip("the regression has not been run on this checkout")
    raw = RECEIPT.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    receipt = json.loads(raw.decode("ascii"))
    assert receipt["official_warning"] is False and receipt["confidence_class"] == "low"
    assert receipt["source_timestamp"] and receipt["assumptions"]
    assert receipt["input_hashes"]["committed_finals_database_sha256"] == hashlib.sha256(DATABASE.read_bytes()).hexdigest()

    spec = importlib.util.spec_from_file_location("check_closure_rule_regression", SCRIPT)
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    with gzip.open(DATABASE) as stream:
        scenarios = json.load(stream)["analysis"]["flood_scenarios"]
    for mode, expected in script.EXPECTED.items():
        identifiers = [row["edge_id"] for row in scenarios[mode]["closed_edges"]]
        assert len(identifiers) == expected
        assert receipt["modes"][mode]["finals_closed_edge_ids_sha256"] == script.id_list_sha256(identifiers)
        if receipt["closed_edge_ids_match_exactly"]:
            assert receipt["modes"][mode]["computed_closed_edge_ids_sha256"] == script.id_list_sha256(identifiers)

    regression = json.loads(PROTOCOL.read_text(encoding="utf-8"))["closure_rule_v1"]["regression"]
    assert regression["expected_closed_edges"] == {"walking": script.EXPECTED["walking"],
                                                   "vehicle": script.EXPECTED["modelled_vehicle"]}
    if regression["result"] is None:
        pytest.skip("the regression result is not recorded in protocol v1b yet")
    assert regression["result"] == {
        "walking_closed_edges": receipt["walking_closed_edges"],
        "vehicle_closed_edges": receipt["vehicle_closed_edges"],
        "closed_edge_ids_match_exactly": receipt["closed_edge_ids_match_exactly"],
        "evidence_sha256": hashlib.sha256(raw).hexdigest(),
    }
