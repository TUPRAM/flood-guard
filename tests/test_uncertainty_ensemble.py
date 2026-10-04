"""Uncertainty ensemble (plan task E10): the grid, retention and the headline rule, from invented measurements only.

Every unit, count, date and input in this file is invented. Nothing here reads a flood layer, a table of a real
case or a real unit, and no component of a real unit is computed. What is real is what every ensemble carries
unchanged from the two signed protocol files: the axes and their levels, the default cell, the weight presets,
the anchors, the class rules and the retention minimum of the headline rule.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date
import json
import math
from pathlib import Path
import shutil
from typing import Any

import pytest

from floodguard import planning_assessment as pa
from floodguard import uncertainty_ensemble as ue
from floodguard.normalisation import NormalisationError, frame_record
from floodguard.scoring import SCORE_COMPONENTS
from floodguard.wording_lint import lint_texts, load_rules, python_strings

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
V1A, V1B, RECEIPTS = DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json", DOCS / "RECEIPTS.jsonl"
FLOOD_NAME = "Fixture agency extent (invented, not a product)"
ROUTING_ID = "fx_routing_context"
PUBLIC_KEYS = [(flood, passability, "public", "worldpop_2020")
               for flood in ("minus", "as_provided", "plus") for passability in ("strict", "central", "permissive")]
SHELTER = {"mode": "walking", "threshold_minutes": 30, "baseline_access_residents": 900.0, "newly_lost_residents": 300.0}


@pytest.fixture(scope="module")
def grid() -> ue.EnsembleGrid:
    return ue.load_grid(V1A, V1B, RECEIPTS)


@pytest.fixture(scope="module")
def rules() -> pa.AssessmentRules:
    return pa.load_assessment_rules(V1A, V1B, RECEIPTS)


@pytest.fixture(scope="module")
def protocols() -> tuple[dict[str, Any], dict[str, Any]]:
    return json.loads(V1A.read_text(encoding="utf-8")), json.loads(V1B.read_text(encoding="utf-8"))


def case() -> pa.CaseSpec:
    return pa.CaseSpec(
        case_id="FX-E10", kind="fixture", title_en="Invented case (fixture, not a place)",
        title_th="กรณีทดสอบ (ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)", frame="Invented units (fixture, not a place)",
        case_reference_date=date(2030, 1, 10), lane="OBS", tier="T3",
        fixture_notice="Fixture, not a place: every unit, input and date is invented.")


def flood() -> pa.FloodInputSpec:
    return pa.FloodInputSpec("fx_agency.invented_layer", FLOOD_NAME, date(2030, 1, 11), "2030-01-11T00:00:00Z")


def unit(number: int = 1, **changes: Any) -> pa.UnitMeasurements:
    """An invented unit of class D: flood likelihood 100, exposure 40, access gap about 29, road criticality about 17."""

    base: dict[str, Any] = dict(
        unit_id=f"FX-U{number:02d}", unit_name_en=f"Invented unit {number:02d} (fixture, not a place)",
        unit_name_th=f"หน่วยทดสอบ {number:02d} (ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)",
        flooded_non_permanent_water_land_area=10.0, non_permanent_water_land_area=40.0,
        unit_residents=1200.0, residents_inside_flood_extent={"minus": 450.0, "as_provided": 480.0, "plus": 510.0},
        access_gap_inputs={
            "hospital": {"mode": "vehicle", "threshold_minutes": 30, "baseline_access_residents": 1100.0, "newly_lost_residents": 300.0},
            "main_road_entry": {"mode": "vehicle", "threshold_minutes": 15, "baseline_access_residents": 1150.0, "newly_lost_residents": 350.0},
        },
        residents_losing_all_routes=200.0, residents_with_baseline_route=1150.0,
        children_0_14=200.0, older_60_plus=330.0, age_residents=1200.0,
        unit_valid_coverage=0.95, coverage_by_construction=False,
        residents_connected_to_the_graph=1150.0, connected_residents_without_a_hospital_route=46.0,
        hospitals_reachable_at_baseline=2,
        v2=pa.V2TriggerInputs(link_isolation=False, serving_facility=False, recurrence_flag=False),
    )
    base.update(changes)
    return pa.UnitMeasurements(**base)


def dry(measured: pa.UnitMeasurements) -> pa.UnitMeasurements:
    """The same invented unit with no flood in it and nobody losing anything: an FPPS under 35, class E."""

    return ue.cell_measurements(
        measured, flooded_non_permanent_water_land_area=0.0, residents_inside_flood_extent=0.0,
        access_gap_inputs={service: {**counts, "newly_lost_residents": 0.0} for service, counts in measured.access_gap_inputs.items()},
        residents_losing_all_routes=0.0, residents_with_baseline_route=measured.residents_with_baseline_route)


def with_shelter(measured: pa.UnitMeasurements) -> pa.UnitMeasurements:
    return replace(measured, access_gap_inputs={**measured.access_gap_inputs, "ddpm_located_shelter": dict(SHELTER)})


def moving_with_the_anchors(number: int = 1) -> pa.UnitMeasurements:
    """An invented unit that is class E on the P10 / P90 anchors and class D on P5 / P95 under the default weights.

    Flood likelihood 50 (4 of 40 flooded, anchor 0.20), exposure 40, and a dependent share of 0.36: just above the
    national P10, so the vulnerability value is about 7 on P10 / P90 and about 26 on P5 / P95. The FPPS is about
    34.1 on the first pair and about 36.0 on the second.
    """

    return unit(number, flooded_non_permanent_water_land_area=4.0, children_0_14=200.0, older_60_plus=232.0)


def by_hand_fpps(values: dict[str, float], raw: dict[str, float], dropped: str | None = None) -> float:
    """The FPPS under raw weights, with one component left out if named: the weighted sum over the sum of the weights.

    Written out here, without ``preset_header`` or ``leave_one_component_out_weights``: protocol v1a normalises a
    preset to sum to 1, and leave-one-component-out sets one weight to 0 and renormalises the other four.
    """

    weights = {name: 0.0 if name == dropped else raw[name] for name in SCORE_COMPONENTS}
    return math.fsum(weights[name] * values[name] for name in SCORE_COMPONENTS) / math.fsum(weights.values())


def by_hand_class(values: dict[str, float], fpps: float) -> str:
    """Class rule v1 for a medium-confidence row, written out from protocol v1a ``class_rules.v1``."""

    if fpps < 35:
        return "E"
    if values["exposure_0_100"] >= 70 and values["access_gap_0_100"] >= 70:
        return "A"
    if values["road_criticality_0_100"] >= 75 and values["access_gap_0_100"] >= 55:
        return "B"
    if values["exposure_0_100"] >= 65 and values["access_gap_0_100"] >= 50:
        return "C"
    return "D"


NOT_RUN_TODAY = [
    ue.LevelNotRun("facilities", "corroborated", "invented_reason_shelters", "An invented reason for a test.", ("FX-OP1",)),
    ue.LevelNotRun("facilities", "all_listed", "invented_reason_shelters", "An invented reason for a test.", ("FX-OP1",)),
    ue.LevelNotRun("population_vintage", "rescaled_2024", "invented_reason_vintage", "An invented reason for a test.", ("FX-OP2",)),
]


def run_public(grid: ue.EnsembleGrid, rules: pa.AssessmentRules, measurements: dict[Any, Any], **arguments: Any) -> dict[str, Any]:
    return ue.run_ensemble(grid, rules, case(), flood(), measurements, routing_context_id=ROUTING_ID,
                           not_run=arguments.pop("not_run", NOT_RUN_TODAY), **arguments)


# ---------------------------------------------------------------------------
# The grid is the one protocol v1b states
# ---------------------------------------------------------------------------


def test_the_grid_has_exactly_the_axes_levels_and_cells_protocol_v1b_states(grid: ue.EnsembleGrid, protocols: Any) -> None:
    v1a, v1b = protocols
    section = v1b["ensemble_grid"]
    assert [axis.name for axis in grid.axes] == [axis["axis"] for axis in section["core_axes"]] == list(ue.AXES)
    for axis, stated in zip(grid.axes, section["core_axes"]):
        assert list(axis.protocol_levels) == stated["levels"], "the words of the protocol, level by level"
        assert len(axis.levels) == stated["count"] == len(set(axis.levels))
    assert [len(axis.levels) for axis in grid.axes] == [3, 3, 3, 2, 2, 5]
    assert grid.axis("flood_input_single_state").levels == ("minus", "as_provided", "plus")
    assert grid.axis("passability").levels == ("strict", "central", "permissive")
    assert grid.axis("facilities").levels == ("public", "corroborated", "all_listed")
    assert grid.axis("population_vintage").levels == ("worldpop_2020", "rescaled_2024")
    assert grid.axis("vulnerability_anchors").levels == ("P10_P90", "P5_P95")
    assert grid.axis("weights").levels == ("default", "access_heavy", "exposure_heavy", "road_heavy", "vulnerability_heavy")
    listed = ue.cells(grid)
    assert len(listed) == grid.core_cells_per_lane == section["core_cells_per_lane"] == 540
    assert len({ue.cell_id(cell) for cell in listed}) == 540
    routing = {tuple(cell[name] for name in ue.ROUTING_AXES) for cell in listed}
    assert len(routing) == grid.routing_combinations_per_lane == section["routing_combinations_per_lane"] == 27
    assert len(ue.routing_keys(grid)) == 54, "27 routing combinations for each of the two population vintages"
    assert grid.reference_cell == {"flood_input_single_state": "as_provided", "passability": "central", "facilities": "public",
                                   "population_vintage": "worldpop_2020", "vulnerability_anchors": "P10_P90", "weights": "default"}
    assert grid.reference_cell_text == section["headline_rule"]["reference_cell"]
    assert grid.class_retention_min == section["headline_rule"]["class_retention_min"] == 0.6
    assert grid.fallback_text == "no class met the stability rule; shown as unstable: verify"
    assert grid.weight_presets_raw == v1a["scoring_frame"]["weight_presets"]["raw_values_before_normalisation"]
    assert list(grid.one_at_a_time) == section["one_at_a_time"] and list(grid.per_tambon_outputs) == section["per_tambon_outputs"]
    # For a public overlay the protocol takes retention over the cells of the public facility set only.
    assert grid.public_cells == 180 and len(ue.scope_cell_ids(grid, "public")) == 180 and len(ue.scope_cell_ids(grid, "pitch")) == 540
    assert "180 cells of the public facility set only" in grid.retention_for_public_overlays
    assert grid.cells_after_cut_line_6 == 135
    # The distance of the minus and the plus level is the one protocol v1b states, not a number of this module.
    pixel = section["core_axes"][0]["one_pixel_m"]
    assert grid.one_pixel_m == pixel["minus"] == pixel["plus"] == pixel["vector_products"] == 20
    assert ue.grid_record(grid)["one_pixel_m"] == 20.0
    record = ue.grid_record(grid)
    assert [axis["levels_as_protocol_v1b_states_them"] for axis in record["axes"]] == [axis["levels"] for axis in section["core_axes"]]
    assert record["headline_rule"]["class_retention_min"] == 0.6 and record["reporting"] == "All cells of every lane are reported."
    with pytest.raises(ue.EnsembleError, match="public or pitch"):
        ue.scope_cell_ids(grid, "local")


def test_a_protocol_that_states_another_grid_is_refused(protocols: Any) -> None:
    v1a, v1b = protocols

    def changed(edit: Any, which: str = "v1b") -> tuple[dict[str, Any], dict[str, Any]]:
        first, second = copy.deepcopy(v1a), copy.deepcopy(v1b)
        edit(first if which == "v1a" else second)
        return first, second

    def grid_of(document: dict[str, Any]) -> dict[str, Any]:
        return document["ensemble_grid"]

    edits = [
        (lambda d: grid_of(d).update(status="open"), "v1b", "not fixed"),
        (lambda d: grid_of(d)["core_axes"].pop(), "v1b", "core axes"),
        (lambda d: grid_of(d)["core_axes"][0]["levels"].pop(), "v1b", "number of distinct levels"),
        (lambda d: grid_of(d)["core_axes"][0]["levels"].__setitem__(0, "half (10 m erosion)"), "v1b", "flood level"),
        (lambda d: grid_of(d)["core_axes"][0]["levels"].__setitem__(0, "minus (one pixel / 10 m erosion)"), "v1b",
         "another one-pixel distance"),
        (lambda d: grid_of(d)["core_axes"][0]["one_pixel_m"].update(plus=10), "v1b", "one positive one-pixel distance"),
        (lambda d: grid_of(d)["core_axes"][0]["one_pixel_m"].update(minus=0, plus=0, vector_products=0), "v1b",
         "one positive one-pixel distance"),
        (lambda d: grid_of(d)["core_axes"][1]["levels"].__setitem__(1, "central (k = 5)"), "v1b", "delay factor"),
        (lambda d: grid_of(d)["core_axes"][2]["levels"].__setitem__(1, "confirmed"), "v1b", "facility sets"),
        (lambda d: grid_of(d)["core_axes"][3]["levels"].__setitem__(1, "2030 projection"), "v1b", "population vintage"),
        (lambda d: grid_of(d)["core_axes"][4]["levels"].__setitem__(1, "national P1 / P99"), "v1b", "anchor levels"),
        (lambda d: grid_of(d)["core_axes"][5]["levels"].__setitem__(4, "age_heavy"), "v1b", "weight presets"),
        (lambda d: grid_of(d).update(core_cells_per_lane=541), "v1b", "do not multiply"),
        (lambda d: grid_of(d).update(routing_combinations_per_lane=9), "v1b", "do not multiply"),
        (lambda d: grid_of(d)["headline_rule"].update(class_retention_min=0.5), "v1b", "GR8"),
        (lambda d: grid_of(d)["headline_rule"].update(
            reference_cell=grid_of(d)["headline_rule"]["reference_cell"].replace("central passability", "lenient passability")),
         "v1b", "default cell"),
        (lambda d: d["facility_sets"]["shelters_in_the_ensemble"].update(
            retention_for_public_overlays="For a public overlay, class retention is computed over the 90 cells of the public facility set only."),
         "v1b", "public facility set"),
        (lambda d: grid_of(d)["declared_cuts"].update(cut_line_6="Population-vintage and vulnerability-anchor axes (540 to 270 cells)."),
         "v1b", "cut line 6"),
        (lambda d: d["scoring_frame"]["weight_presets"]["raw_values_before_normalisation"]["access_heavy"].update(access_gap_0_100=0.5),
         "v1a", "floodguard.sensitivity"),
        (lambda d: d["guardrails"][7]["parameters"].update(class_retention_min=0.7), "v1a", "GR8"),
    ]
    for edit, which, words in edits:
        with pytest.raises(ue.EnsembleError, match=words):
            ue.grid_from_protocols(*changed(edit, which))
    assert ue.grid_from_protocols(v1a, v1b).core_cells_per_lane == 540, "the files as signed are read"

    # A protocol that states another distance for both levels, in the words of the level and in one_pixel_m, is read
    # with that distance: nothing in this module holds the 20 m of the files in force.
    def ten_metres(document: dict[str, Any]) -> None:
        grid_of(document)["core_axes"][0]["levels"][0] = "minus (one pixel / 10 m erosion)"
        grid_of(document)["core_axes"][0]["one_pixel_m"].update(minus=10, plus=10, vector_products=10)

    other = ue.grid_from_protocols(*changed(ten_metres))
    assert other.one_pixel_m == 10.0 and ue.grid_record(other)["one_pixel_m"] == 10.0


def test_nothing_is_read_from_a_protocol_that_is_not_in_force(tmp_path: Path, grid: ue.EnsembleGrid, rules: pa.AssessmentRules,
                                                              protocols: Any) -> None:
    """Guardrail GR5: no grid computes for a unit unless both files are signed and recorded in RECEIPTS.jsonl."""

    for name in ("planning_protocol_v1a.json", "planning_protocol_v1b.json", "RECEIPTS.jsonl"):
        shutil.copy(DOCS / name, tmp_path / name)
    edited = (tmp_path / "planning_protocol_v1b.json").read_bytes().replace(b'"status": "signed"', b'"status": "signed" ', 1)
    (tmp_path / "planning_protocol_v1b.json").write_bytes(edited)
    with pytest.raises(NormalisationError, match="not in force"):
        ue.load_grid(tmp_path / "planning_protocol_v1a.json", tmp_path / "planning_protocol_v1b.json", tmp_path / "RECEIPTS.jsonl")
    # A grid read from parsed files carries no hash of a file in force, and no ensemble runs on it.
    unbound = ue.grid_from_protocols(*protocols)
    assert dict(unbound.protocol_sha256) == {"v1a": None, "v1b": None}
    with pytest.raises(ue.EnsembleError, match="same two protocol files in force"):
        ue.run_ensemble(unbound, rules, case(), flood(), {key: [unit()] for key in PUBLIC_KEYS}, routing_context_id=ROUTING_ID,
                        not_run=NOT_RUN_TODAY)
    assert dict(grid.protocol_sha256) == dict(rules.binding.frame.protocol_sha256)


# ---------------------------------------------------------------------------
# Every cell is reported: run, or not run with its reason
# ---------------------------------------------------------------------------


def test_every_cell_of_the_lane_is_reported_as_run_or_as_not_run_with_its_reason(grid: ue.EnsembleGrid) -> None:
    table = ue.cell_table(grid, PUBLIC_KEYS, NOT_RUN_TODAY)
    assert len(table) == 540 and [cell["cell_id"] for cell in table] == [ue.cell_id(cell) for cell in ue.cells(grid)]
    run = [cell for cell in table if cell["status"] == "run"]
    assert len(run) == 90 and all(cell["facilities"] == "public" and cell["population_vintage"] == "worldpop_2020" for cell in run)
    reasons: dict[str, int] = {}
    for cell in table:
        if cell["status"] == "not_run":
            assert cell["not_run_because"], "a cell that is not run says why"
            reasons["+".join(cell["not_run_because"])] = reasons.get("+".join(cell["not_run_because"]), 0) + 1
    assert reasons == {"invented_reason_shelters": 180, "invented_reason_shelters+invented_reason_vintage": 180,
                       "invented_reason_vintage": 90}
    # A cell that is neither run nor reported is refused: no cell is dropped silently.
    with pytest.raises(ue.EnsembleError, match="neither run nor reported as not run"):
        ue.cell_table(grid, PUBLIC_KEYS, NOT_RUN_TODAY[:2])
    with pytest.raises(ue.EnsembleError, match="neither run nor reported as not run"):
        ue.cell_table(grid, PUBLIC_KEYS[:-1], NOT_RUN_TODAY)
    with pytest.raises(ue.EnsembleError, match="measured and reported as not run"):
        ue.cell_table(grid, [*PUBLIC_KEYS, ("minus", "strict", "public", "rescaled_2024")], NOT_RUN_TODAY)
    with pytest.raises(ue.EnsembleError, match="not of the grid"):
        ue.cell_table(grid, [*PUBLIC_KEYS, ("minus", "strict", "public", "worldpop_1990")], NOT_RUN_TODAY)
    with pytest.raises(ue.EnsembleError, match="not a level of the grid"):
        ue.cell_table(grid, PUBLIC_KEYS, [*NOT_RUN_TODAY, ue.LevelNotRun("weights", "age_heavy", "x", "x")])
    with pytest.raises(ue.EnsembleError, match="not run twice"):
        ue.cell_table(grid, PUBLIC_KEYS, [*NOT_RUN_TODAY, NOT_RUN_TODAY[0]])


# ---------------------------------------------------------------------------
# Retention and the headline rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kept, cells, status, retention", [
    (59, 100, "unstable_verify", 0.59), (60, 100, "headline_eligible", 0.60), (61, 100, "headline_eligible", 0.61),
    (107, 180, "unstable_verify", 107 / 180), (108, 180, "headline_eligible", 0.6),
    (323, 540, "unstable_verify", 323 / 540), (324, 540, "headline_eligible", 0.6), (540, 540, "headline_eligible", 1.0),
    (0, 540, "unstable_verify", 0.0),
])
def test_the_headline_rule_at_0_59_0_60_and_0_61(grid: ue.EnsembleGrid, kept: int, cells: int, status: str, retention: float) -> None:
    """Guardrail GR8: a class is headlined only at a retention of at least 0.6; exactly 0.6 is enough."""

    record = ue.headline_record(grid, reference_class="D", kept=kept, with_a_class=cells, protocol_cells=cells, over="invented cells")
    assert record["status"] == status and record["class_retention"] == pytest.approx(retention)
    assert record["class_retention_min"] == 0.6 and record["guardrail"] == "GR8_headline_stability"
    assert record["fallback_text"] == (None if status == "headline_eligible" else "no class met the stability rule; shown as unstable: verify")
    assert record["bounds_over_the_protocol_set"] is None and record["not_evaluated_because"] is None
    assert record["retention_over_the_cells_run"] == pytest.approx(retention)


def test_the_headline_stays_not_evaluated_while_cells_of_the_protocol_set_have_no_class(grid: ue.EnsembleGrid) -> None:
    """The protocols state no retention over a part of the cells (open point E10-OP1): nothing is headlined."""

    half = ue.headline_record(grid, reference_class="B", kept=90, with_a_class=90, protocol_cells=180, over="invented cells")
    assert half["status"] == "not_evaluated" and half["class_retention"] is None and half["fallback_text"] is None
    assert half["retention_over_the_cells_run"] == 1.0, "a share of the cells run, which is not the retention of the rule"
    assert half["bounds_over_the_protocol_set"] == {"lower": 0.5, "upper": 1.0, "cells_without_a_class": 90}
    assert half["outcome_fixed_by_the_bounds"] is None and "E10-OP1" in half["not_evaluated_because"]
    # 17 of 90 kept: even if every missing cell kept the class, 107 of 180 stays under 0.6. The status is still not set.
    low = ue.headline_record(grid, reference_class="B", kept=17, with_a_class=90, protocol_cells=180, over="invented cells")
    assert low["status"] == "not_evaluated" and low["outcome_fixed_by_the_bounds"] == "below_the_minimum"
    assert low["bounds_over_the_protocol_set"]["upper"] == pytest.approx(107 / 180)
    edge = ue.headline_record(grid, reference_class="B", kept=18, with_a_class=90, protocol_cells=180, over="invented cells")
    assert edge["outcome_fixed_by_the_bounds"] is None, "108 of 180 is exactly 0.6, so the minimum can still be reached"
    high = ue.headline_record(grid, reference_class="B", kept=108, with_a_class=170, protocol_cells=180, over="invented cells")
    assert high["status"] == "not_evaluated" and high["outcome_fixed_by_the_bounds"] == "at_or_above_the_minimum"
    # A unit with no class in the default cell has no class to retain.
    none = ue.headline_record(grid, reference_class=None, kept=0, with_a_class=0, protocol_cells=180, over="invented cells")
    assert none["status"] == "not_evaluated" and none["retention_over_the_cells_run"] is None and "GR1" in none["not_evaluated_because"]
    # The share over the cells declared cut line 6 would leave is reported beside the record, never as the headline.
    after_cut = {"cells": 45, "cells_keeping_the_reference_class": 40, "retention": 40 / 45, "at_or_above_the_minimum": True}
    cut = ue.headline_record(grid, reference_class="B", kept=80, with_a_class=90, protocol_cells=180, over="invented cells",
                             after_declared_cut_line_6=after_cut)
    assert cut["status"] == "not_evaluated" and cut["after_declared_cut_line_6"] == after_cut
    for kept, classed, cells in ((5, 4, 10), (-1, 4, 10), (3, 11, 10), (0, 0, 0)):
        with pytest.raises(ue.EnsembleError, match="whole cells"):
            ue.headline_record(grid, reference_class="D", kept=kept, with_a_class=classed, protocol_cells=cells, over="invented cells")
    with pytest.raises(ue.EnsembleError, match="whole cells"):
        ue.headline_record(grid, reference_class="D", kept=3, with_a_class=5, cells_run=4, protocol_cells=10, over="invented cells")
    with pytest.raises(ue.EnsembleError, match="whole cells"):
        ue.headline_record(grid, reference_class="D", kept=3, with_a_class=5, cells_run=11, protocol_cells=10, over="invented cells")


def test_a_cell_that_was_run_and_failed_stays_in_the_denominator_of_the_share_over_the_cells_run(grid: ue.EnsembleGrid) -> None:
    """90 cells were run, 10 of them failed and 80 keep the class: the share over the cells run is 80 of 90, not 1."""

    record = ue.headline_record(grid, reference_class="D", kept=80, with_a_class=80, cells_run=90, protocol_cells=180,
                                over="invented cells")
    assert (record["cells_run"], record["cells_with_a_class"], record["cells_run_without_a_class"]) == (90, 80, 10)
    assert record["retention_over_the_cells_run"] == pytest.approx(80 / 90) != 1.0
    # For the bounds a failed cell is a cell without a class, like a cell that was not run.
    assert record["bounds_over_the_protocol_set"] == {"lower": 80 / 180, "upper": 1.0, "cells_without_a_class": 100}
    assert "failed cells included in the denominator" in record["not_evaluated_because"]
    # With every cell of the set run and ten of them failed, the rule is still not evaluated: ten cells have no class.
    whole = ue.headline_record(grid, reference_class="D", kept=170, with_a_class=170, cells_run=180, protocol_cells=180,
                               over="invented cells")
    assert whole["status"] == "not_evaluated" and whole["retention_over_the_cells_run"] == pytest.approx(170 / 180)
    assert whole["outcome_fixed_by_the_bounds"] == "at_or_above_the_minimum"


def test_the_other_reading_of_the_protocol_set_and_the_levels_cut_line_6_could_keep(grid: ue.EnsembleGrid) -> None:
    """Two readings the protocols leave open (E10-OP11, E10-OP12): both are reported and no status is set from them."""

    reading = ue.protocol_set_reading(grid, kept=90, with_a_class=90, cells=540, over="the 540 core cells")
    assert reading["class_retention"] is None and reading["at_or_above_the_minimum"] is None
    assert reading["bounds"] == {"lower": 90 / 540, "upper": 1.0, "cells_without_a_class": 450}
    assert reading["outcome_fixed_by_the_bounds"] is None
    assert ue.protocol_set_reading(grid, kept=9, with_a_class=450, cells=540, over="x")["outcome_fixed_by_the_bounds"] == "below_the_minimum"
    assert ue.protocol_set_reading(grid, kept=324, with_a_class=400, cells=540, over="x")["outcome_fixed_by_the_bounds"] == "at_or_above_the_minimum"
    whole = ue.protocol_set_reading(grid, kept=324, with_a_class=540, cells=540, over="x")
    assert whole["class_retention"] == pytest.approx(0.6) and whole["at_or_above_the_minimum"] is True and whole["bounds"] is None
    with pytest.raises(ue.EnsembleError, match="whole cells"):
        ue.protocol_set_reading(grid, kept=5, with_a_class=4, cells=540, over="x")
    record = ue.headline_record(grid, reference_class="B", kept=90, with_a_class=90, protocol_cells=180, over="invented cells",
                                other_reading=reading)
    assert record["status"] == "not_evaluated", "no status is set from the other reading"
    assert record["other_reading_of_the_protocol_set"]["bounds"]["lower"] == pytest.approx(1 / 6)
    assert "E10-OP11" in record["other_reading_of_the_protocol_set"]["note"]

    # Cut line 6: 45 cells for each of the four pairs of levels it could keep, among the 180 cells of the public set.
    public = [cell for cell in ue.cells(grid) if cell["facilities"] == "public"]
    run = [cell for cell in public if cell["population_vintage"] == "worldpop_2020"]
    classed = {ue.cell_id(cell): "E" if cell["vulnerability_anchors"] == "P10_P90" or cell["weights"] != "vulnerability_heavy" else "D"
               for cell in run}
    cut = ue.cut_line_6_record(grid, reference_class="E", classed=classed, cells_of_the_set=public)
    assert cut["levels_kept"] == {"population_vintage": "worldpop_2020", "vulnerability_anchors": "P10_P90"}
    assert cut["levels_kept_are"] == "the levels of the default cell"
    assert (cut["cells"], cut["cells_with_a_class"], cut["cells_keeping_the_reference_class"], cut["retention"]) == (45, 45, 45, 1.0)
    others = cut["other_levels_the_cut_could_keep"]
    assert [item["levels_kept"] for item in others] == [
        {"population_vintage": "worldpop_2020", "vulnerability_anchors": "P5_P95"},
        {"population_vintage": "rescaled_2024", "vulnerability_anchors": "P10_P90"},
        {"population_vintage": "rescaled_2024", "vulnerability_anchors": "P5_P95"}]
    # With the P5 / P95 anchors kept, the nine cells of the vulnerability-heavy weights are class D: 36 of 45.
    assert (others[0]["cells"], others[0]["cells_keeping_the_reference_class"]) == (45, 36)
    assert others[0]["retention"] == pytest.approx(36 / 45) and others[0]["at_or_above_the_minimum"] is True
    # A pair whose cells were not run has no share.
    assert all((item["cells"], item["cells_with_a_class"], item["retention"], item["at_or_above_the_minimum"]) == (45, 0, None, None)
               for item in others[1:])
    assert "E10-OP12" in cut["note"] and "not the headline" in cut["note"]
    assert ue.cut_line_6_record(grid, reference_class=None, classed=classed, cells_of_the_set=public) is None
    with pytest.raises(ue.EnsembleError, match="cut line 6"):
        ue.cut_line_6_record(grid, reference_class="E", classed=classed, cells_of_the_set=public[:-1])


# ---------------------------------------------------------------------------
# The cells of invented units
# ---------------------------------------------------------------------------


def test_the_default_cell_and_its_leave_one_component_out_are_the_row_of_task_e8(grid: ue.EnsembleGrid, rules: pa.AssessmentRules) -> None:
    measured = unit()
    row = pa.assess_unit(rules, case(), flood(), pa.ClosureSpec("closure_rule_v1", rules.reference_closure_level), measured,
                         routing_context_id=ROUTING_ID)
    result = run_public(grid, rules, {key: [measured] for key in PUBLIC_KEYS})
    assert result["reference_rows"] == [row], "the default cell is assembled exactly as task E8 assembles the row"
    found = result["units"][0]
    assert found["reference_cell"]["cell_id"] == "as_provided|central|public|worldpop_2020|P10_P90|default"
    for field in ("fpps_0_100", "action_class", "action_reason_code", "would_be_class", "leave_one_component_out"):
        assert found["reference_cell"][field] == row[field], field
    assert found["reference_cell"]["action_class"] == "D" and set(found["reference_cell"]["leave_one_component_out"]) == set(SCORE_COMPONENTS)
    assert found["confidence"]["confidence_class"] == row["confidence"]["confidence_class"] == "medium"
    # Every other cell: the scoring block of task E8 under the anchors and the weight preset of the cell.
    header = frame_record(rules.binding.frame)
    values = {name: row["components"][name]["value_0_100"] for name in SCORE_COMPONENTS}
    on_p5_p95 = {**values, "vulnerability_context_0_100": row["components"]["vulnerability_context_0_100"]["anchor_sensitivity"]["value_0_100"]}
    cells = {cell["cell_id"]: cell for cell in found["cells"]}
    assert len(cells) == 90 and all(cell["status"] == "computed" for cell in cells.values())
    assert on_p5_p95["vulnerability_context_0_100"] != values["vulnerability_context_0_100"]
    by_hand_loo: dict[str, list[float]] = {name: [] for name in SCORE_COMPONENTS}
    for preset, raw in grid.weight_presets_raw.items():
        for anchors, numbers in (("P10_P90", values), ("P5_P95", on_p5_p95)):
            cell = cells[f"as_provided|central|public|worldpop_2020|{anchors}|{preset}"]
            # The FPPS and the class of the cell, and of each leave-one-component-out, written out by hand from the raw
            # weights of protocol v1a: nothing of the expectation comes from the module under test.
            fpps = by_hand_fpps(numbers, raw)
            assert cell["fpps_0_100"] == pytest.approx(fpps, abs=0.006), (preset, anchors)
            assert cell["action_class"] == by_hand_class(numbers, cell["fpps_0_100"]), (preset, anchors)
            assert set(cell["leave_one_component_out"]) == set(SCORE_COMPONENTS)
            for dropped in SCORE_COMPONENTS:
                without = by_hand_fpps(numbers, raw, dropped)
                entry = cell["leave_one_component_out"][dropped]
                assert entry["fpps_0_100"] == pytest.approx(without, abs=0.006), (preset, anchors, dropped)
                assert entry["action_class"] == by_hand_class(numbers, entry["fpps_0_100"]), (preset, anchors, dropped)
                by_hand_loo[dropped].append(entry["fpps_0_100"])
            # The same cell through the scoring block of task E8, for every other field of the block.
            expected = pa.scoring_block(numbers, "medium", False, ue.preset_header(header, raw))
            assert {key: cell[key] for key in expected} == expected, (preset, anchors)
    # One leave-one-component-out of a preset that is not the default, in full. access_heavy has the raw weights 0.30,
    # 0.25, 0.35, 0.15 and 0.10; without the flood likelihood the other four are divided by their sum, 0.85.
    without_flood = (0.25 * values["exposure_0_100"] + 0.35 * values["access_gap_0_100"] + 0.15 * values["road_criticality_0_100"]
                     + 0.10 * values["vulnerability_context_0_100"]) / 0.85
    under_default = (0.25 * values["exposure_0_100"] + 0.20 * values["access_gap_0_100"] + 0.15 * values["road_criticality_0_100"]
                     + 0.10 * values["vulnerability_context_0_100"]) / 0.70
    assert abs(without_flood - under_default) > 0.5, "the two presets give another value, so the check below tells them apart"
    heavy = cells["as_provided|central|public|worldpop_2020|P10_P90|access_heavy"]["leave_one_component_out"]["flood_likelihood_0_100"]
    assert heavy["fpps_0_100"] == pytest.approx(round(without_flood, 2), abs=0.006)
    assert found["reference_cell"]["leave_one_component_out"]["flood_likelihood_0_100"]["fpps_0_100"] == pytest.approx(
        round(under_default, 2), abs=0.006)
    # Leave-one-component-out over the cells: this unit has the same measurements in every combination, so the ten
    # values by hand (five presets by two pairs of anchors) are all there is.
    for dropped, entry in found["leave_one_component_out_over_the_cells"].items():
        assert entry["fpps_0_100"]["min"] == min(by_hand_loo[dropped]) and entry["fpps_0_100"]["max"] == max(by_hand_loo[dropped])
        assert len(set(by_hand_loo[dropped])) > 1, "the presets give more than one value"
    # One preset by hand: access_heavy raises the access weight to 0.35 and the scorer divides every weight by 1.15.
    by_hand = (0.30 * values["flood_likelihood_0_100"] + 0.25 * values["exposure_0_100"] + 0.35 * values["access_gap_0_100"]
               + 0.15 * values["road_criticality_0_100"] + 0.10 * values["vulnerability_context_0_100"]) / 1.15
    assert cells["as_provided|central|public|worldpop_2020|P10_P90|access_heavy"]["fpps_0_100"] == pytest.approx(round(by_hand, 2))
    # The summary of leave-one-component-out over the cells holds every cell that was run.
    assert all(entry["cells"] == 90 for entry in found["leave_one_component_out_over_the_cells"].values())
    # The one-at-a-time flood anchors are applied to the default cell alone: the P10 / P90 anchors and the default
    # weights. A quarter of the land is flooded, so the flood likelihood is 100 at the anchor 0.10 and 83.33 at 0.30.
    anchors = found["one_at_a_time"]["flood_likelihood_anchor"]
    assert [item["flood_anchor"] for item in anchors] == [0.1, 0.3] and all(item["action_class"] == "D" for item in anchors)
    default_raw = grid.weight_presets_raw["default"]
    for item, likelihood in zip(anchors, (100.0, 100 * 0.25 / 0.30)):
        assert item["flood_likelihood_0_100"] == pytest.approx(likelihood)
        on_default = by_hand_fpps({**values, "flood_likelihood_0_100": likelihood}, default_raw)
        on_other_anchors = by_hand_fpps({**on_p5_p95, "flood_likelihood_0_100": likelihood}, default_raw)
        assert abs(on_default - on_other_anchors) > 0.03, "the two pairs of anchors give another FPPS"
        assert item["fpps_0_100"] == pytest.approx(on_default, abs=0.006)
    assert found["one_at_a_time"]["terrain_remoteness_proxy"]["status"] == "not_run"
    assert found["one_at_a_time"]["class_rule_v1_and_v2"]["v1_class"] == "D"
    assert found["equity_eed_and_eer"]["status"] == "not_computed"


def test_a_public_run_today_reports_the_share_over_the_cells_run_and_headlines_nothing(grid: ue.EnsembleGrid, rules: pa.AssessmentRules) -> None:
    """One unit keeps its class in every cell; one is class D only where the closure level is not strict."""

    steady, moving = unit(1), unit(2)
    measurements = {key: [steady, dry(moving) if key[1] == "strict" else moving] for key in PUBLIC_KEYS}
    losing = {key: {"FX-U01": {"hospital": 300.0, "main_road_entry": 100.0},
                    "FX-U02": {"hospital": 0.0 if key[1] == "strict" else 300.0, "main_road_entry": 0.0}} for key in PUBLIC_KEYS}
    result = run_public(grid, rules, measurements, people_losing_access=losing)
    first, second = result["units"]
    assert first["class_counts"] == {"A": 0, "B": 0, "C": 0, "D": 90, "E": 0, "no_class": 0} and first["class_shares"]["D"] == 1.0
    assert second["class_counts"] == {"A": 0, "B": 0, "C": 0, "D": 60, "E": 30, "no_class": 0}
    assert second["class_shares"]["E"] == pytest.approx(1 / 3)
    for found, kept in ((first, 90), (second, 60)):
        headline = found["headline_stability"]
        assert headline["status"] == "not_evaluated" and headline["class_retention"] is None
        assert headline["cells_of_the_protocol_set"] == 180 and headline["cells_with_a_class"] == 90
        assert headline["cells_keeping_the_reference_class"] == kept and headline["retention_over_the_cells_run"] == kept / 90
        assert headline["bounds_over_the_protocol_set"] == {"lower": kept / 180, "upper": (kept + 90) / 180, "cells_without_a_class": 90}
        assert "public facility set" in headline["over"]
    assert second["headline_stability"]["after_declared_cut_line_6"]["cells"] == 45
    assert second["headline_stability"]["after_declared_cut_line_6"]["retention"] == pytest.approx(30 / 45)
    assert second["headline_stability"]["after_declared_cut_line_6"]["levels_kept"] == {
        "population_vintage": "worldpop_2020", "vulnerability_anchors": "P10_P90"}
    # The other reading of the protocol's set (E10-OP11): the same counts over the 540 core cells, and no status.
    other = second["headline_stability"]["other_reading_of_the_protocol_set"]
    assert (other["cells"], other["cells_with_a_class"], other["cells_keeping_the_reference_class"]) == (540, 90, 60)
    assert other["bounds"] == {"lower": 60 / 540, "upper": 510 / 540, "cells_without_a_class": 450} and other["class_retention"] is None
    assert "540 core cells" in other["over"] and "E10-OP11" in second["headline_stability"]["over"]
    # The range of the FPPS, the rank and the people losing 30-minute access over the access runs.
    assert second["fpps_0_100"]["count"] == 90 and second["fpps_0_100"]["min"] < 35 <= second["fpps_0_100"]["max"]
    assert first["rank"] == {"best": 1, "worst": 1, "cells_ranked": 90, "among_units": 2, "rule": first["rank"]["rule"]}
    assert (second["rank"]["best"], second["rank"]["worst"]) == (2, 2), "the two units tie where both are wet: the lower identifier ranks first"
    assert second["people_losing_30_minute_access"]["hospital"]["min"] == 0.0
    assert second["people_losing_30_minute_access"]["hospital"]["median"] == 300.0 and second["people_losing_30_minute_access"]["hospital"]["count"] == 9
    # The swing: the passability axis moves the second unit, the flood axis does not; two axes have one level run.
    swing = second["fpps_swing"]
    assert swing["axis_with_the_largest_swing"] is None and "E10-OP6" in swing["axis_with_the_largest_swing_status"]
    assert swing["by_axis"]["passability"]["measured"] is True and swing["by_axis"]["passability"]["largest_fpps_swing"] > 30
    assert swing["by_axis"]["flood_input_single_state"]["largest_fpps_swing"] == 0.0
    assert swing["by_axis"]["facilities"]["measured"] is False and swing["by_axis"]["population_vintage"]["measured"] is False
    assert swing["largest_by_the_largest_fpps_swing"] == swing["largest_by_the_mean_fpps_swing"] == "passability"
    # The whole case: counts only, every cell of the lane, and no value beside a unit.
    summary = result["summary"]
    assert (summary["core_cells_per_lane"], summary["cells_run"], summary["cells_not_run"]) == (540, 90, 450)
    assert sum(summary["cells_not_run_by_reason"].values()) == 450 and summary["unit_cells_with_a_result"] == 180
    assert summary["unit_cells_failed"] == 0 and summary["cells_ranked"] == 90
    assert summary["headline_status_counts"] == {"not_evaluated": 2, "headline_eligible": 0, "unstable_verify": 0}
    kept = summary["retention_over_the_cells_run"]
    assert kept["units_keeping_the_class_in_every_cell_run"] == 1 and kept["units_keeping_the_class_in_at_least_the_minimum_share"] == 2
    assert kept["units_keeping_the_class_in_less_than_the_minimum_share"] == 0
    assert summary["outcome_fixed_by_the_bounds_counts"] == {"at_or_above_the_minimum": 0, "below_the_minimum": 0, "not_fixed": 2}
    kept_levels = {"population_vintage": "worldpop_2020", "vulnerability_anchors": "P10_P90"}
    counted = {"cells": 45, "units_at_or_above_the_minimum": 2, "units_below_the_minimum": 0,
               "units_keeping_the_class_in_every_one_of_those_cells": 1, "units_without_a_class_in_every_one_of_those_cells": 0}
    not_run = {"cells": 45, "units_at_or_above_the_minimum": 0, "units_below_the_minimum": 0,
               "units_keeping_the_class_in_every_one_of_those_cells": 0, "units_without_a_class_in_every_one_of_those_cells": 2}
    assert summary["after_declared_cut_line_6"] == {
        "levels_kept": kept_levels, **counted, "levels_kept_are": "the levels of the default cell",
        "other_levels_the_cut_could_keep": [
            {"levels_kept": {**kept_levels, "vulnerability_anchors": "P5_P95"}, **counted},
            {"levels_kept": {"population_vintage": "rescaled_2024", "vulnerability_anchors": "P10_P90"}, **not_run},
            {"levels_kept": {"population_vintage": "rescaled_2024", "vulnerability_anchors": "P5_P95"}, **not_run}],
        "note": summary["after_declared_cut_line_6"]["note"]}
    assert "E10-OP12" in summary["after_declared_cut_line_6"]["note"]
    assert summary["other_reading_of_the_protocol_set"]["cells"] == 540
    assert summary["other_reading_of_the_protocol_set"]["outcome_fixed_by_the_bounds_counts"] == {
        "at_or_above_the_minimum": 0, "below_the_minimum": 0, "not_fixed": 2}
    # What the counts state about single units (E10-OP10): where both units are class D, the count says so of each.
    single = summary["counts_that_state_a_value_of_a_single_unit"]
    assert single["cells_in_which_every_unit_has_one_class"] == 60 and single["classes_one_unit_alone_holds_in_the_default_cell"] == []
    assert single["cells_whose_class_counts_differ_from_the_default_cell"] == 30
    assert single["units_with_more_than_one_class_over_the_cells_run"] == 1 and single["states_a_value_of_a_single_unit"] is True
    assert summary["units_whose_fpps_lies_on_both_sides_of_the_class_e_threshold"] == 1
    assert summary["class_counts_by_cell"]["minus|strict|public|worldpop_2020|P10_P90|default"] == {"D": 1, "E": 1}
    assert summary["class_counts_by_cell"]["plus|central|public|worldpop_2020|P5_P95|road_heavy"] == {"D": 2}
    assert summary["class_counts_over_every_unit_cell"]["D"] == 150 and summary["reference_class_counts"]["D"] == 2
    assert "FX-U0" not in json.dumps(summary)
    assert len(result["cells"]) == 540 and [item["level"] for item in result["levels_not_run"]] == ["corroborated", "all_listed", "rescaled_2024"]


def test_a_whole_grid_on_invented_units_is_headlined_by_the_rule(grid: ue.EnsembleGrid, rules: pa.AssessmentRules) -> None:
    """With every one of the 540 cells run, retention is the share of all of them and the rule gives a status."""

    def measured(number: int, key: Any, wet: bool) -> pa.UnitMeasurements:
        found = unit(number) if wet else dry(unit(number))
        return with_shelter(found) if key[2] != "public" else found

    keys = ue.routing_keys(grid)
    assert len(keys) == 54
    measurements = {key: [measured(1, key, True),                    # class D in every cell
                          measured(2, key, key[1] != "strict"),      # class D in two cells of three
                          measured(3, key, key[0] == "as_provided")]  # class D in one cell of three
                    for key in keys}
    result = ue.run_ensemble(grid, rules, case(), flood(), measurements, routing_context_id=ROUTING_ID, level="pitch")
    assert result["summary"]["cells_run"] == 540 and result["summary"]["cells_not_run"] == 0
    first, second, third = (item["headline_stability"] for item in result["units"])
    assert all("540 core cells" in item["over"] and item["cells_with_a_class"] == 540 for item in (first, second, third))
    assert (first["status"], first["class_retention"]) == ("headline_eligible", 1.0)
    assert (second["status"], second["class_retention"]) == ("headline_eligible", pytest.approx(360 / 540))
    assert (third["status"], third["class_retention"]) == ("unstable_verify", pytest.approx(180 / 540))
    assert third["fallback_text"] == grid.fallback_text and second["fallback_text"] is None
    assert third["reference_class"] == "D" and third["bounds_over_the_protocol_set"] is None
    assert third["other_reading_of_the_protocol_set"] is None and result["summary"]["other_reading_of_the_protocol_set"] is None
    assert third["after_declared_cut_line_6"]["cells"] == 135 and len(third["after_declared_cut_line_6"]["other_levels_the_cut_could_keep"]) == 3
    assert all(item["retention"] is not None for item in third["after_declared_cut_line_6"]["other_levels_the_cut_could_keep"])
    assert result["summary"]["headline_status_counts"] == {"not_evaluated": 0, "headline_eligible": 2, "unstable_verify": 1}
    # The retention is the share of the cells whose class equals the class of the default cell, counted by hand.
    cells = result["units"][1]["cells"]
    assert sum(1 for cell in cells if cell["action_class"] == "D") == 360 and len(cells) == 540
    # A pitch-level cell carries the shelter service in its access gap; a public cell does not.
    assert result["units"][0]["fpps_swing"]["by_axis"]["facilities"]["measured"] is True
    # At the public level the same measurements of the public facility set give a retention over its 180 cells.
    public = {key: value for key, value in measurements.items() if key[2] == "public"}
    assert len(public) == 18
    at_public = ue.run_ensemble(grid, rules, case(), flood(), public, routing_context_id=ROUTING_ID, not_run=NOT_RUN_TODAY[:2])
    headline = at_public["units"][2]["headline_stability"]
    assert headline["cells_of_the_protocol_set"] == 180 and "public facility set" in headline["over"]
    assert (headline["status"], headline["class_retention"]) == ("unstable_verify", pytest.approx(60 / 180))
    # The status above follows the 180 cells. Over the 540 core cells the same unit has bounds and no retention.
    assert headline["other_reading_of_the_protocol_set"]["bounds"] == {"lower": 60 / 540, "upper": 420 / 540, "cells_without_a_class": 360}
    assert headline["other_reading_of_the_protocol_set"]["outcome_fixed_by_the_bounds"] is None
    with pytest.raises(ue.EnsembleError, match="public facility set only"):
        ue.run_ensemble(grid, rules, case(), flood(), measurements, routing_context_id=ROUTING_ID)


def test_a_cell_that_fails_is_reported_and_never_dropped(grid: ue.EnsembleGrid, rules: pa.AssessmentRules) -> None:
    failed_key, refused_key = ("plus", "permissive", "public", "worldpop_2020"), ("minus", "strict", "public", "worldpop_2020")
    measurements: dict[Any, Any] = {key: [unit(1), unit(2)] for key in PUBLIC_KEYS}
    # One access run failed as a whole; and in another combination the row of one unit is refused by a guardrail.
    measurements[failed_key] = ue.MeasurementFailure("access_runs", "AccessDiffError", "an invented failure of an access run")
    measurements[refused_key] = [unit(1), unit(2, coverage_by_construction=True)]
    result = run_public(grid, rules, measurements)
    first, second = result["units"]
    assert (first["cells_run"], first["cells_with_a_result"], first["cells_failed"]) == (90, 80, 10)
    assert (second["cells_run"], second["cells_with_a_result"], second["cells_failed"]) == (90, 70, 20)
    failed = [cell for cell in second["cells"] if cell["status"] == "failed"]
    assert len(failed) == 20 and {(cell["stage"], cell["error"]) for cell in failed} == {
        ("access_runs", "AccessDiffError"), ("row_assembly", "PlanningAssessmentError")}
    assert all("fpps_0_100" not in cell and cell["message"] for cell in failed)
    assert len(second["cells"]) == 90, "a failed cell stays in the table of the unit"
    summary = result["summary"]
    assert summary["cells_run"] == 90 and summary["cells_run_with_a_failed_unit"] == 20
    assert summary["unit_cells_failed"] == 30 and summary["unit_cells_with_a_result"] == 150
    assert summary["unit_cells_failed_by_stage_and_error"] == {"access_runs:AccessDiffError": 20, "row_assembly:PlanningAssessmentError": 10}
    assert summary["cells_ranked"] == 70, "a cell in which a unit has no FPPS is not ranked"
    assert second["headline_stability"]["cells_with_a_class"] == 70 and second["headline_stability"]["status"] == "not_evaluated"
    # The first unit is class D in every cell that has a result, and ten of its 90 cells failed. Every share that is
    # labelled as taken over the cells run keeps those ten in its denominator: 80 of 90, not 80 of 80.
    kept = first["headline_stability"]
    assert (kept["cells_run"], kept["cells_with_a_class"], kept["cells_run_without_a_class"]) == (90, 80, 10)
    assert kept["cells_keeping_the_reference_class"] == 80 and kept["retention_over_the_cells_run"] == pytest.approx(80 / 90)
    assert kept["bounds_over_the_protocol_set"] == {"lower": 80 / 180, "upper": 1.0, "cells_without_a_class": 100}
    assert first["class_shares"]["D"] == pytest.approx(80 / 90) and first["share_of_the_cells_run_that_failed"] == pytest.approx(10 / 90)
    assert sum(first["class_shares"].values()) == pytest.approx(80 / 90) and "failed cells included" in first["class_shares_over"]
    assert second["headline_stability"]["retention_over_the_cells_run"] == pytest.approx(70 / 90)
    counted = summary["retention_over_the_cells_run"]
    assert counted["units_keeping_the_class_in_every_cell_run"] == 0, "a unit with a failed cell does not keep its class in every cell run"
    assert counted["units_keeping_the_class_in_at_least_the_minimum_share"] == 2 and counted["units_without_a_class_to_keep"] == 0
    # Cut line 6 with the levels of the default cell: the failed combinations leave cells without a class, so no share.
    assert first["headline_stability"]["after_declared_cut_line_6"]["retention"] is None
    assert first["headline_stability"]["after_declared_cut_line_6"]["cells_with_a_class"] == 40
    assert summary["after_declared_cut_line_6"]["units_without_a_class_in_every_one_of_those_cells"] == 2
    assert [item["status"] for item in second["routing_combinations"]].count("failed") == 2
    # A component that is not computed is not a failure: the cell is low confidence and class E, and it is counted.
    nobody = {service: {**counts, "baseline_access_residents": 0.0, "newly_lost_residents": 0.0}
              for service, counts in unit().access_gap_inputs.items()}
    without_access = run_public(grid, rules, {key: [replace(unit(), access_gap_inputs=nobody)] if key == refused_key else [unit()]
                                              for key in PUBLIC_KEYS})
    only = without_access["units"][0]
    assert only["cells_with_a_component_not_computed"] == 10 and only["cells_failed"] == 0
    blank = [cell for cell in only["cells"] if cell["components_not_computed"]]
    assert {(cell["fpps_0_100"], cell["action_class"], cell["action_reason_code"]) for cell in blank} == {(None, "E", "low_confidence")}
    assert only["class_counts"]["E"] == 10 and only["fpps_0_100"]["count"] == 80
    # The default cell failing leaves no class to retain.
    measurements[("as_provided", "central", "public", "worldpop_2020")] = ue.MeasurementFailure("access_runs", "X", "invented")
    without_default = run_public(grid, rules, measurements)
    assert without_default["units"][0]["reference_cell"] is None and without_default["summary"]["units_without_a_default_cell_result"] == 2
    assert without_default["units"][0]["headline_stability"]["reference_class"] is None
    with pytest.raises(ue.EnsembleError, match="nothing was run"):
        run_public(grid, rules, {key: ue.MeasurementFailure("access_runs", "X", "invented") for key in PUBLIC_KEYS})
    with pytest.raises(ue.EnsembleError, match="same units in the same order"):
        run_public(grid, rules, {key: [unit(1), unit(2)] if key != failed_key else [unit(2), unit(1)] for key in PUBLIC_KEYS})


def test_one_at_a_time_and_cut_line_6_keep_the_anchors_of_the_default_cell(grid: ue.EnsembleGrid, rules: pa.AssessmentRules) -> None:
    """A unit whose class differs between the two pairs of anchors: E on P10 / P90 (the default cell), D on P5 / P95."""

    measured = moving_with_the_anchors()
    row = pa.assess_unit(rules, case(), flood(), pa.ClosureSpec("closure_rule_v1", rules.reference_closure_level), measured,
                         routing_context_id=ROUTING_ID)
    values = {name: row["components"][name]["value_0_100"] for name in SCORE_COMPONENTS}
    on_p5_p95 = {**values, "vulnerability_context_0_100": row["components"]["vulnerability_context_0_100"]["anchor_sensitivity"]["value_0_100"]}
    default_raw = grid.weight_presets_raw["default"]
    assert values["flood_likelihood_0_100"] == pytest.approx(50.0)
    assert by_hand_fpps(values, default_raw) < 35 <= by_hand_fpps(on_p5_p95, default_raw), "the unit this test needs"
    found = run_public(grid, rules, {key: [measured] for key in PUBLIC_KEYS})["units"][0]
    cells = {cell["cell_id"]: cell for cell in found["cells"]}
    assert found["reference_cell"]["action_class"] == "E" and found["reference_cell"]["action_reason_code"] == "low_priority_score"
    assert cells["as_provided|central|public|worldpop_2020|P5_P95|default"]["action_class"] == "D"
    # One at a time: a tenth of the land is flooded, so the flood likelihood is 100 at the anchor 0.10 and 33.33 at
    # 0.30. Each is scored on the P10 / P90 anchors of the default cell; on P5 / P95 the FPPS would be about 1.9 higher.
    anchors = found["one_at_a_time"]["flood_likelihood_anchor"]
    for item, likelihood in zip(anchors, (100.0, 100 * 0.10 / 0.30)):
        expected = by_hand_fpps({**values, "flood_likelihood_0_100": likelihood}, default_raw)
        other = by_hand_fpps({**on_p5_p95, "flood_likelihood_0_100": likelihood}, default_raw)
        assert other - expected > 1.5 and item["fpps_0_100"] == pytest.approx(expected, abs=0.006)
        assert item["action_class"] == by_hand_class(values, item["fpps_0_100"])
    assert [item["action_class"] for item in anchors] == ["D", "E"]
    # Cut line 6: the classes are counted here from the cells, pair by pair, and compared with the record.
    def kept_with(anchors_level: str) -> int:
        return sum(1 for identifier, cell in cells.items()
                   if identifier.split("|")[3:5] == ["worldpop_2020", anchors_level] and cell["action_class"] == "E")

    cut = found["headline_stability"]["after_declared_cut_line_6"]
    assert kept_with("P10_P90") != kept_with("P5_P95"), "the two pairs of anchors keep the class in another number of cells"
    assert cut["levels_kept"] == {"population_vintage": "worldpop_2020", "vulnerability_anchors": "P10_P90"}
    assert (cut["cells"], cut["cells_keeping_the_reference_class"]) == (45, kept_with("P10_P90"))
    assert cut["retention"] == pytest.approx(kept_with("P10_P90") / 45)
    other_pair = cut["other_levels_the_cut_could_keep"][0]
    assert other_pair["levels_kept"]["vulnerability_anchors"] == "P5_P95"
    assert (other_pair["cells"], other_pair["cells_keeping_the_reference_class"]) == (45, kept_with("P5_P95"))
    assert found["headline_stability"]["cells_keeping_the_reference_class"] == kept_with("P10_P90") + kept_with("P5_P95")


def test_the_counts_that_state_a_value_of_a_single_unit_are_counted() -> None:
    """Open point E10-OP10, on invented counts: a count names no unit and can state the class of one all the same."""

    default = {"B": 1, "D": 3, "E": 4}
    summary = {"units": 8, "reference_class_counts": {"A": 0, **default, "C": 0, "no_class": 0},
               "units_by_number_of_classes_over_the_cells_run": {"1": 6, "2": 2},
               "class_counts_by_cell": {"first": dict(default), "second": {"D": 4, "E": 4}, "third": {"B": 1, "D": 4, "E": 3},
                                        "fourth": dict(default)}}
    counted = ue.counts_that_state_single_units(summary)
    assert counted["classes_one_unit_alone_holds_in_the_default_cell"] == ["B"]
    assert counted["cells_in_which_such_a_class_has_another_count"] == 1, "the cell in which no unit is class B"
    assert counted["cells_whose_class_counts_differ_from_the_default_cell"] == 2
    assert counted["cells_in_which_every_unit_has_one_class"] == 0 and counted["units_with_more_than_one_class_over_the_cells_run"] == 2
    assert counted["states_a_value_of_a_single_unit"] is True and "names no unit" in counted["what"]
    # Every unit in one class in every cell: each count states the class of each unit.
    every = ue.counts_that_state_single_units({
        "units": 8, "reference_class_counts": {"E": 8, "no_class": 0}, "units_by_number_of_classes_over_the_cells_run": {"1": 8},
        "class_counts_by_cell": {"first": {"E": 8}, "second": {"E": 8}}})
    assert every["cells_in_which_every_unit_has_one_class"] == 2 and every["states_a_value_of_a_single_unit"] is True
    assert every["classes_one_unit_alone_holds_in_the_default_cell"] == [] and every["cells_whose_class_counts_differ_from_the_default_cell"] == 0
    # Two classes with two units each, the same in every cell: no count states the class of a single unit.
    none = ue.counts_that_state_single_units({
        "units": 4, "reference_class_counts": {"D": 2, "E": 2}, "units_by_number_of_classes_over_the_cells_run": {"1": 4},
        "class_counts_by_cell": {"first": {"D": 2, "E": 2}, "second": {"D": 2, "E": 2}}})
    assert none["states_a_value_of_a_single_unit"] is False
    # A unit under guardrail GR1 has no class: the one unit without a class is not a class one unit holds.
    gr1 = ue.counts_that_state_single_units({
        "units": 3, "reference_class_counts": {"D": 2, "no_class": 1}, "units_by_number_of_classes_over_the_cells_run": {"1": 3},
        "class_counts_by_cell": {"first": {"D": 2, "no_class": 1}}})
    assert gr1["classes_one_unit_alone_holds_in_the_default_cell"] == [] and gr1["states_a_value_of_a_single_unit"] is False


def test_a_unit_under_gr1_has_no_class_to_retain(grid: ue.EnsembleGrid, rules: pa.AssessmentRules) -> None:
    small = unit(
        unit_residents=60.0, residents_inside_flood_extent={"minus": 20.0, "as_provided": 24.0, "plus": 26.0},
        access_gap_inputs={"hospital": {"mode": "vehicle", "threshold_minutes": 30, "baseline_access_residents": 55.0, "newly_lost_residents": 15.0},
                           "main_road_entry": {"mode": "vehicle", "threshold_minutes": 15, "baseline_access_residents": 57.0, "newly_lost_residents": 17.0}},
        residents_losing_all_routes=10.0, residents_with_baseline_route=57.0, residents_connected_to_the_graph=57.0,
        connected_residents_without_a_hospital_route=2.0)
    found = run_public(grid, rules, {key: [small] for key in PUBLIC_KEYS})["units"][0]
    assert found["confidence"]["guardrail_gr1_applies"] is True and found["class_counts"]["no_class"] == 90
    assert found["reference_cell"]["action_class"] is None and found["reference_cell"]["action_reason_code"] == "insufficient_denominator"
    assert found["headline_stability"]["status"] == "not_evaluated" and found["headline_stability"]["reference_class"] is None
    assert found["fpps_0_100"]["count"] == 90, "a unit under GR1 keeps its FPPS"


def test_cell_measurements_change_the_flood_level_and_the_access_counts_and_nothing_else() -> None:
    base = unit()
    changed = ue.cell_measurements(
        base, flooded_non_permanent_water_land_area=4.0, residents_inside_flood_extent=450.0,
        access_gap_inputs={service: {**counts, "newly_lost_residents": 10.0} for service, counts in base.access_gap_inputs.items()},
        residents_losing_all_routes=5.0, residents_with_baseline_route=1150.0)
    assert changed.flooded_non_permanent_water_land_area == 4.0 and changed.residents_losing_all_routes == 5.0
    # The plus and minus counts that condition C4 compares stay those of the flood input as provided.
    assert changed.residents_inside_flood_extent == {"minus": 450.0, "as_provided": 450.0, "plus": 510.0}
    assert changed.access_gap_inputs["hospital"]["newly_lost_residents"] == 10.0
    same = {"unit_id", "unit_residents", "children_0_14", "older_60_plus", "age_residents", "unit_valid_coverage",
            "residents_connected_to_the_graph", "hospitals_reachable_at_baseline", "non_permanent_water_land_area"}
    assert all(getattr(changed, name) == getattr(base, name) for name in same)
    assert base.residents_inside_flood_extent["as_provided"] == 480.0, "the measurements of task E8 are not edited"


def test_the_open_points_are_listed_and_the_wording_passes_the_shared_lint() -> None:
    assert [point["id"] for point in ue.OPEN_POINTS] == [f"E10-OP{number}" for number in range(1, 13)]
    assert all(point["for_the_owners"].strip() and point["signed_files_say"].strip() and point["what_this_task_does"].strip()
               for point in ue.OPEN_POINTS)
    by_id = {point["id"]: point for point in ue.OPEN_POINTS}
    assert "stays not_evaluated" in by_id["E10-OP1"]["what_this_task_does"]
    assert "not run and not approximated" in by_id["E10-OP2"]["what_this_task_does"]
    assert "E5-OP5" in by_id["E10-OP3"]["signed_files_say"]
    assert "uses_ensemble_output" in by_id["E10-OP4"]["signed_files_say"]
    assert "No axis is named" in by_id["E10-OP6"]["what_this_task_does"]
    # The display of a class that is not headlined is put to the owners with the words of guardrail GR8.
    assert "Otherwise it is shown as unstable: verify." in by_id["E10-OP1"]["signed_files_say"]
    assert "sets no display" in by_id["E10-OP1"]["for_the_owners"]
    # The precedent the owners' answered choice 12 names is quoted, and the level still waits for their answer.
    assert "bridge_worldpop_age_access.py" in by_id["E10-OP2"]["signed_files_say"]
    assert "Confirm or reject it" in by_id["E10-OP2"]["for_the_owners"] and "stays not run until then" in by_id["E10-OP2"]["for_the_owners"]
    assert (ROOT / "scripts" / "bridge_worldpop_age_access.py").is_file()
    choices = (DOCS / "planning_protocol_v1b_owner_choices.md").read_text(encoding="utf-8")
    assert "the way `bridge_worldpop_age_access.py` already spreads 2024 counts over 2020 cells" in choices
    assert "class_counts_by_cell" in by_id["E10-OP10"]["what_this_task_does"] and "Git history" in by_id["E10-OP10"]["what_this_task_does"]
    assert "'For a public overlay" in by_id["E10-OP11"]["signed_files_say"] and "540 core cells" in by_id["E10-OP11"]["for_the_owners"]
    assert "(540 to 135 cells)" in by_id["E10-OP12"]["signed_files_say"]
    lint = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    sources = ["src/floodguard/uncertainty_ensemble.py", "scripts/build_uncertainty_ensemble.py"]
    items = [(name, "\n".join(python_strings((ROOT / name).read_text(encoding="utf-8")))) for name in sources]
    assert lint_texts(items, lint) == []
