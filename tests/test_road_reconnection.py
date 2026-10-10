"""The district-wide road what-if of case SE1: the counting by joined parts, and the committed record."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "outputs" / "road_reconnection" / "se1_mae_sai_v1.json"
ACCESS_TABLE = ROOT / "outputs" / "planning_v1" / "e5_access_diff_se1_mae_sai_public_services.json"
KO_CHANG = ROOT / "outputs" / "ko_chang_road_check" / "ko_chang_roads_se1_v1.json"


def load() -> object:
    name = "build_road_reconnection"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_joining_a_part_to_one_with_a_destination_gives_its_residents_a_route() -> None:
    runner = load()
    served = np.array([True, False, False, False])
    waiting = np.array([[0.0, 0.0], [10.0, 5.0], [7.0, 0.0], [3.0, 3.0]])
    # part 1 joins part 0 (a destination); part 2 joins part 1; part 3 joins nothing with a destination
    assert runner.gain_of([(0, 1), (1, 2)], served, waiting).tolist() == [17.0, 5.0]
    assert runner.gain_of([(2, 3)], served, waiting).tolist() == [0.0, 0.0], "two cut-off parts joined to each other gain nothing"
    assert runner.gain_of([(0, 0)], served, waiting).tolist() == [0.0, 0.0]
    assert runner.gain_of([], served, waiting).tolist() == [0.0, 0.0]


@pytest.fixture(scope="module")
def record() -> dict:
    if not RESULT.exists():
        pytest.skip("the road what-if has not been written")
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_the_record_says_what_it_is_and_stands_on_the_access_table(record: dict) -> None:
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False and record["confidence_class"] == "low"
    assert record["source_timestamp"] and record["assumptions"] and record["limits"] and "what-if" in record["what_this_is"]
    assert record["made_from"]["access_table"]["sha256"] == hashlib.sha256(ACCESS_TABLE.read_bytes()).hexdigest()
    table = json.loads(ACCESS_TABLE.read_text(encoding="utf-8"))
    run = next(entry for entry in table["runs"] if entry["closure_level"] == "central" and entry["flood_level"] == "as_provided")
    for row in run["units"]:
        stated = record["cut_off_in_the_scenario"]["by_tambon"][row["unit_id"]]["residents"]
        assert stated == pytest.approx(row["road_criticality_inputs"]["residents_losing_all_routes"], abs=0.06)
    assert sum(item["residents"] for item in record["cut_off_in_the_scenario"]["by_tambon"].values()) == pytest.approx(
        record["cut_off_in_the_scenario"]["residents"], abs=0.5)
    assert b"\r" not in RESULT.read_bytes()


def test_each_step_adds_less_than_the_one_before_and_the_counts_add_up(record: dict) -> None:
    steps = record["one_road_after_another"]["steps"]
    gains = [step["residents_who_get_a_route_back_at_this_step"] for step in steps]
    assert len(steps) == 10 and gains == sorted(gains, reverse=True), "greedy: no later step helps more than an earlier one"
    cut_off = record["cut_off_in_the_scenario"]["residents"]
    left = record["one_road_after_another"]["still_cut_off_after_the_last_step"]["residents"]
    assert cut_off - sum(gains) == pytest.approx(left, abs=1.0)
    assert steps[-1]["share_of_the_cut_off_residents_with_a_route_back"] == pytest.approx(1 - left / cut_off, abs=1e-3)
    for step in steps:
        assert sum(step["by_tambon_at_this_step"].values()) == pytest.approx(step["residents_who_get_a_route_back_at_this_step"], abs=0.3)
        assert step["look_at"].endswith(step["osm_way_id"]) and step["closed_pieces"] > 0 and step["closed_length_m"] > 0
    alone = record["one_road_on_its_own"]["best"]
    assert alone[0]["osm_way_id"] == steps[0]["osm_way_id"], "the first step is the road that helps most on its own"


def test_the_first_road_is_the_first_road_of_the_ko_chang_sheet(record: dict) -> None:
    sheet = json.loads(KO_CHANG.read_text(encoding="utf-8"))
    first = sheet["what_if_one_road_stays_passable"]["best"][0]
    step = record["one_road_after_another"]["steps"][0]
    assert step["osm_way_id"] == str(first["osm_way_id"])
    assert step["by_tambon_at_this_step"][sheet["unit"]["unit_id"]] == pytest.approx(first["residents_who_get_a_route_back"], abs=0.06)
    assert record["made_from"]["ko_chang_sheet"]["sha256"] == hashlib.sha256(KO_CHANG.read_bytes()).hexdigest()
