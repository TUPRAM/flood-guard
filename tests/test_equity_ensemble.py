"""The committed record of access loss by age over the cells of the uncertainty ensemble (decision log R40)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from floodguard import equity_by_age as eba

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "outputs" / "equity_by_age" / "se1_mae_sai_ensemble_v1.json"
OUTCOMES = ("loses_a_hospital_within_30_minutes", "loses_every_road_route")


@pytest.fixture(scope="module")
def record() -> dict:
    if not RESULT.exists():
        pytest.skip("the ensemble run of the age comparison has not been written")
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_the_record_says_what_it_is(record: dict) -> None:
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False
    assert record["confidence_class"] == "low" and record["source_timestamp"] and record["assumptions"] and record["limits"]
    assert "Modelled, not observed" in record["label"] and b"\r" not in RESULT.read_bytes()
    assert record["rule"]["otherwise"] == eba.FIXED_SENTENCE
    assert record["checks"]["runs_as_provided_reproduce_the_committed_access_table_for_every_tambon"] is True


def test_the_180_cells_are_18_counts_of_ten_cells_each(record: dict) -> None:
    counts = record["counts"]
    assert record["ensemble"] == {**record["ensemble"], "cells": 180, "different_counts": 18}
    assert len(counts) == 18 and all(count["stands_for_cells"] == 10 for count in counts)
    assert len({(count["flood_input_single_state"], count["passability"], count["population_vintage"]) for count in counts}) == 18
    assert sum(1 for count in counts if count["reproduces_the_committed_access_table"]) == 3


def test_the_rule_of_the_protocol_is_applied_to_the_differences_of_the_counts(record: dict) -> None:
    for outcome in OUTCOMES:
        for comparison in eba.COMPARISONS:
            differences = [count["whole_frame"][outcome][comparison]["difference_of_rates"] for count in record["counts"]]
            expected = eba.gap_statement([value for value in differences for _cell in range(10)])
            block = record["whole_frame"][outcome][comparison]
            assert block["rule"] == expected and block["rule"]["runs"] == 180
            if not expected["may_state_a_gap"]:
                assert block["rule"]["sentence"] == eba.FIXED_SENTENCE
            spread = block["difference_of_rates"]
            assert spread["lowest"] == pytest.approx(min(differences), abs=1e-6) and spread["highest"] == pytest.approx(max(differences), abs=1e-6)


def test_every_tambon_has_both_outcomes_and_none_is_ranked_by_age(record: dict) -> None:
    assert len(record["by_tambon"]) == 8
    for block in record["by_tambon"].values():
        assert block["unit_name_en"] and all(set(block[outcome]) == set(eba.COMPARISONS) for outcome in OUTCOMES)
    stated = set(record["tambons_where_a_gap_may_be_stated"])
    for unit_id, block in record["by_tambon"].items():
        for outcome in OUTCOMES:
            for comparison in eba.COMPARISONS:
                assert (f"{unit_id}:{outcome}:{comparison}" in stated) == block[outcome][comparison]["rule"]["may_state_a_gap"]
    assert any("No tambon is ranked by its age mix" in limit for limit in record["limits"])
