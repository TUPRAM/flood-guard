"""Tests of the committed record of the September 2024 re-read: its labels, its binding and its arithmetic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "outputs" / "september_reread" / "mae_sai_20240915_v1.json"
KO_CHANG = "TH570903"


def test_the_re_read_is_labelled_unchecked_and_bound_to_the_frozen_detector() -> None:
    if not RESULT.exists():
        pytest.skip("the re-read has not been run")
    record = json.loads(RESULT.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False
    assert record["confidence_class"] == "low" and record["source_timestamp"] and record["assumptions"] and record["limits"]
    assert record["label"].startswith("Unchecked") and "no dated reference" in record["confidence_basis"].lower()
    assert b"\r" not in RESULT.read_bytes()
    freeze = ROOT / record["freeze_record"]["path"]
    assert hashlib.sha256(freeze.read_bytes()).hexdigest() == record["freeze_record"]["sha256"]
    assert record["frozen_detector"] == json.loads(freeze.read_text(encoding="utf-8"))["frozen_detector"]
    earlier = ROOT / record["table_of_flood_inputs_of_work_package_2"]["path"]
    assert hashlib.sha256(earlier.read_bytes()).hexdigest() == record["table_of_flood_inputs_of_work_package_2"]["sha256"]
    assert set(record["readings"]) == {"frozen_detector", "simple_threshold", "un_spider_with_the_dry_baseline"}
    for reading in record["readings"].values():
        assert set(reading["by_closure_level"]) == {"strict", "central", "permissive"}
        for level in reading["by_closure_level"].values():
            units = level["units"]
            assert len(units) == 8 and KO_CHANG in units
            lost = sum(unit["residents_losing_every_route"] for unit in units.values())
            assert lost == pytest.approx(level["frame"]["residents_losing_every_route"], abs=0.05)
            for unit in units.values():
                assert unit["residents_losing_every_route"] <= unit["residents_with_a_route_before"] + 1e-6
        assert reading["flagged_km2_in_the_district"] >= reading["frame"]["flooded_land_km2"] - 0.5
    text = json.dumps(record).lower()
    assert "fpps" not in text and "action_class" not in text
