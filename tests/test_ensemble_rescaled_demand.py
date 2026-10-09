"""The committed record of the report-only ensemble run with the 2024-rescaled demand (decision log R38)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from floodguard import demand_rescale

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "outputs" / "uncertainty_ensemble_rescaled" / "se1_mae_sai_v1.json"
REGISTERED = ROOT / "outputs" / "planning_v1" / "e10_uncertainty_ensemble_se1_mae_sai.json"
CLASSES = ("A", "B", "C", "D", "E")


@pytest.fixture(scope="module")
def record() -> dict:
    if not RESULT.exists():
        pytest.skip("the report-only run has not been written")
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_the_record_says_what_it_is_and_what_it_is_not(record: dict) -> None:
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False
    assert record["operational_status"] == "non_operational"
    assert record["confidence_class"] == "low" and record["source_timestamp"] and record["assumptions"] and record["limits"]
    assert "not the registered run" in record["not_of_record"] and "unchanged" in record["not_of_record"]
    assert list(demand_rescale.RULES) == record["rescaled_demand"]["rules"] == record["assumptions"][:2]
    assert b"\r" not in RESULT.read_bytes()


def test_the_run_of_record_is_the_file_the_record_was_checked_against(record: dict) -> None:
    checks = record["checks"]
    assert all(checks[name]["result"] == "PASS" for name in (
        "default_cell_against_the_e8_rows", "cells_of_the_2020_demand_against_the_registered_run",
        "as_provided_runs_against_the_e5_table"))
    bound = checks["cells_of_the_2020_demand_against_the_registered_run"]["registered_receipt"]
    assert ROOT / bound["path"] == REGISTERED
    assert hashlib.sha256(REGISTERED.read_bytes()).hexdigest() == bound["sha256"], "the registered receipt is unchanged"
    registered = json.loads(REGISTERED.read_text(encoding="utf-8"))
    assert checks["default_cell_against_the_e8_rows"]["rows_sha256"] == registered["result"]["default_cell_against_the_e8_rows"]["rows_sha256"]
    assert checks["cells_of_the_2020_demand_against_the_registered_run"]["unit_cells_compared"] == registered["result"]["summary"]["unit_cells_run"]


def test_every_cell_of_the_public_set_is_run_and_only_the_shelter_sets_are_left(record: dict) -> None:
    summary = record["summary"]
    assert summary["core_cells_per_lane"] == 540 and summary["cells_run"] == 180 and summary["cells_not_run"] == 360
    assert summary["cells_of_the_protocol_set_for_retention"] == 180
    assert summary["unit_cells_run"] == 180 * summary["units"] and summary["unit_cells_failed"] == 0
    assert {item["axis"] for item in record["levels_not_run"]} == {"facilities"}


def test_each_unit_has_a_headline_status_read_from_all_180_cells(record: dict) -> None:
    statuses = record["summary"]["headline_status_counts"]
    assert sum(statuses.values()) == len(record["units"]) == record["summary"]["units"]
    for unit in record["units"]:
        headline = unit["headline_stability"]
        assert unit["cells_run"] == 180 and sum(unit["class_counts"].values()) == 180
        by_demand = unit["class_counts_by_demand"]
        assert set(by_demand) == {"worldpop_2020", demand_rescale.RESCALED_LEVEL}
        assert all(sum(counts.values()) == 90 for counts in by_demand.values())
        for letter in CLASSES:
            assert unit["class_counts"][letter] == sum(counts[letter] for counts in by_demand.values())
        reference = unit["reference_cell"]["action_class"]
        assert headline["class_retention"] == pytest.approx(unit["class_counts"][reference] / 180)
        assert (headline["class_retention"] >= 0.6) == (headline["status"] == "headline_eligible")


def test_the_rescaled_demand_is_accounted_for(record: dict) -> None:
    demand = record["rescaled_demand"]
    by_unit = demand["residents_by_unit"]
    assert sum(row["worldpop_2020"] for row in by_unit.values()) == pytest.approx(demand["demand_residents_2020"], abs=0.01)
    assert sum(row[demand_rescale.RESCALED_LEVEL] for row in by_unit.values()) == pytest.approx(demand["demand_residents_rescaled"], abs=0.01)
    assert 0 < demand["demand_residents_kept_at_2020"] < 0.05 * demand["demand_residents_2020"]
