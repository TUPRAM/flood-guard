"""Tests of the Ko Chang road sheet: the connected-parts logic on an invented graph, and the committed record."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "ko_chang_road_check"
RESULT = OUTPUTS / "ko_chang_roads_se1_v1.json"
MAP = OUTPUTS / "ko_chang_roads_se1_v1_map.png"


def load_sheet_script():
    name = "build_ko_chang_road_sheet"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def edge(edge_id: str, start: str, end: str) -> dict[str, str]:
    return {"edge_id": edge_id, "from_node": start, "to_node": end}


def test_a_node_has_a_route_only_through_open_edges_to_a_destination() -> None:
    pytest.importorskip("scipy")
    sheet = load_sheet_script()
    # hospital - a - b - c, and a village pair d - e that never reaches the hospital
    edges = [edge("e1", "hospital", "a"), edge("e2", "a", "b"), edge("e3", "b", "c"), edge("e4", "d", "e")]
    network = sheet.Network(edges, {"hospital", "not_in_the_graph"})
    everything = np.ones(len(edges), dtype=bool)

    def reached(open_edges: np.ndarray) -> set[str]:
        flags = network.with_a_route(open_edges)
        return {node for node, position in network.index.items() if flags[position]}

    assert reached(everything) == {"hospital", "a", "b", "c"}
    closed = everything.copy()
    closed[network.position["e2"]] = False
    assert reached(closed) == {"hospital", "a"}  # b and c are cut off behind one closed piece
    closed[network.position["e2"]] = True
    assert reached(closed) == reached(everything)  # kept passable, they get the route back


def record() -> dict:
    if not RESULT.exists():
        pytest.skip("the sheet has not been written")
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_committed_sheet_carries_the_required_fields() -> None:
    sheet = record()
    assert sheet["official_warning"] is False and sheet["operational_status"] == "non_operational"
    assert sheet["can_feed_decision_layer"] is False and sheet["confidence_class"] == "low"
    assert sheet["generated_at_utc"].endswith("Z") and sheet["source_timestamp"]
    assert sheet["assumptions"] and sheet["limits"] and sheet["credits"]
    assert "scenario" in " ".join(sheet["assumptions"]) and "not" in sheet["confidence_basis"]
    assert b"\r" not in RESULT.read_bytes()
    assert hashlib.sha256(MAP.read_bytes()).hexdigest() == sheet["map_sha256"]


def test_committed_sheet_reproduces_the_case_and_binds_it() -> None:
    sheet = record()
    again = sheet["reproduction_of_case_se1"]
    assert again["same"] is True
    assert again["with_a_route_before"]["this_sheet"] == again["with_a_route_before"]["case_se1"]
    assert again["losing_every_route"]["this_sheet"] == again["losing_every_route"]["case_se1"]
    table = sheet["inputs"]["case_se1_table"]
    assert hashlib.sha256((ROOT / table["path"]).read_bytes()).hexdigest() == table["sha256"]
    extent = sheet["inputs"]["season_extent"]
    assert extent["sha256"] in (ROOT / extent["bound_by"]).read_text(encoding="utf-8")


def test_the_what_if_adds_up_and_feeds_no_score() -> None:
    sheet = record()
    what_if = sheet["what_if_roads_stay_passable_one_after_another"]
    before = what_if["residents_with_a_route_before_the_flood"]
    reached = what_if["residents_with_a_route_in_the_scenario"]
    for number, step in enumerate(what_if["steps"], start=1):
        assert step["step"] == number and step["residents_who_get_a_route_back_at_this_step"] > 0
        reached += step["residents_who_get_a_route_back_at_this_step"]
        assert step["residents_with_a_route_after_this_step"] == pytest.approx(reached, abs=0.2)
        assert step["share_of_residents_with_a_route_before"] == pytest.approx(reached / before, abs=1e-3)
        assert step["look_at"].endswith(step["osm_way_id"]) and len(step["centre_of_the_closed_pieces_lonlat"]) == 2
    assert reached <= before
    best_alone = sheet["what_if_one_road_stays_passable"]["best"][0]
    assert best_alone["osm_way_id"] == what_if["steps"][0]["osm_way_id"]
    roads = sheet["roads_in_the_tambon"]
    assert roads["closed_road_pieces"] <= roads["road_pieces"]
    assert roads["closed_bridge_tagged_pieces"] <= roads["bridge_tagged_pieces"]

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for item in value.values() for key in keys(item)}
        if isinstance(value, list):
            return {key for item in value for key in keys(item)}
        return set()

    assert not {key for key in keys(sheet) if "fpps" in key.lower() or "action_class" in key.lower()}
