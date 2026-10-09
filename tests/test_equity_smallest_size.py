"""The smallest size of a stated age gap (decision log R41), and the check with registered age counts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from floodguard import equity_by_age as eba

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "outputs" / "equity_by_age"
ENSEMBLE = FOLDER / "se1_mae_sai_ensemble_v1.json"
RESTATED = FOLDER / "se1_mae_sai_ensemble_smallest_size_v1.json"
REGISTRATION = FOLDER / "se1_mae_sai_registration_check_v1.json"


def test_the_rule_of_the_protocol_alone_is_unchanged() -> None:
    statement = eba.gap_statement([0.000001, 0.000002, 0.000003])
    assert statement["may_state_a_gap"] is True and "smallest_size_asked" not in statement, "protocol v1a sets no smallest size"


def test_a_gap_under_one_point_is_not_stated() -> None:
    small = eba.gap_statement([0.004, 0.02, 0.03], min_abs_difference=eba.MIN_GAP_SHARE)
    assert small["rule_of_the_protocol_met"] is True and small["may_state_a_gap"] is False
    assert small["smallest_difference"] == 0.004 and small["sentence"] == eba.SMALL_GAP_SENTENCE
    enough = eba.gap_statement([-0.011, -0.03, -0.059], min_abs_difference=eba.MIN_GAP_SHARE)
    assert enough["may_state_a_gap"] is True and enough["smallest_difference"] == 0.011 and enough["sentence"] is None
    at_the_line = eba.gap_statement([0.01, 0.02], min_abs_difference=eba.MIN_GAP_SHARE)
    assert at_the_line["may_state_a_gap"] is True, "one point is enough"


def test_where_the_protocol_rule_is_not_met_the_fixed_sentence_stays() -> None:
    mixed = eba.gap_statement([-0.02, 0.03, 0.04], min_abs_difference=eba.MIN_GAP_SHARE)
    assert mixed["rule_of_the_protocol_met"] is False and mixed["may_state_a_gap"] is False and mixed["sentence"] == eba.FIXED_SENTENCE
    with pytest.raises(eba.EquityByAgeError):
        eba.with_smallest_size(eba.gap_statement([0.02]), minimum=0.0)


def test_the_restated_record_is_made_from_the_ensemble_record_and_states_one_gap() -> None:
    if not RESTATED.exists():
        pytest.skip("the restated record has not been written")
    restated = json.loads(RESTATED.read_text(encoding="utf-8"))
    ensemble = json.loads(ENSEMBLE.read_text(encoding="utf-8"))
    assert restated["official_warning"] is False and restated["confidence_class"] == "low" and restated["source_timestamp"]
    assert restated["made_from"]["sha256"] == hashlib.sha256(ENSEMBLE.read_bytes()).hexdigest()
    assert restated["rule"]["smallest_size_share"] == eba.MIN_GAP_SHARE and "not edited" in restated["rule"]["decided"]
    for outcome, block in restated["whole_frame"].items():
        for comparison, statement in block.items():
            assert statement == eba.with_smallest_size(ensemble["whole_frame"][outcome][comparison]["rule"])
            assert statement["may_state_a_gap"] is False and statement["sentence"] == eba.SMALL_GAP_SENTENCE
    assert restated["where_a_gap_may_be_stated"] == ["TH570901:loses_a_hospital_within_30_minutes:60_plus_vs_under_60"]
    assert set(restated["where_a_gap_may_be_stated"]) <= set(restated["where_the_protocol_rule_alone_was_met"])
    assert b"\r" not in RESTATED.read_bytes()


def test_the_registration_check_says_what_its_ages_leave_out() -> None:
    if not REGISTRATION.exists():
        pytest.skip("the registration check has not been written")
    record = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False and record["confidence_class"] == "low"
    assert record["source"]["url"].startswith("https://stat.bora.dopa.go.th/") and len(record["source"]["source_file_sha256"]) == 64
    assert "Thai nationals" in record["source"]["ages_cover"] and "none stated" in record["source"]["licence"]
    district = record["registered_in_the_district"]
    assert district["with_an_age"] + district["not_thai_nationals_and_without_an_age"] <= district["all_registered"]
    assert sum(entry["registered"] for entry in record["age_mix_by_tambon"].values()) == district["all_registered"]
    assert len(record["age_mix_by_tambon"]) == 8 and len(record["loses_a_hospital_within_30_minutes"]) == 3
    table = ROOT / record["access_counts_from"]["path"]
    assert hashlib.sha256(table.read_bytes()).hexdigest() == record["access_counts_from"]["sha256"]
    for comparison in eba.COMPARISONS:
        differences = [level[comparison]["difference_of_rates"] for level in record["loses_a_hospital_within_30_minutes"].values()]
        assert record["rule_with_the_smallest_size_of_decision_log_r41"][comparison] == eba.gap_statement(
            differences, min_abs_difference=eba.MIN_GAP_SHARE)
    assert any("Registered is not resident" in limit for limit in record["limits"]) and b"\r" not in REGISTRATION.read_bytes()
