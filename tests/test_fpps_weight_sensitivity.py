"""The weight test of the planning score: the arithmetic, and the committed report of case SE1."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from floodguard import fpps_weight_sensitivity as ws
from floodguard.scoring import DEFAULT_WEIGHTS

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "outputs" / "fpps_weight_sensitivity" / "se1_mae_sai_v1.json"
PAGE_COPY = ROOT / "apps" / "web" / "src" / "lib" / "policy-weight-sensitivity.json"
CASE = ROOT / "apps" / "web" / "public" / "planning-overlays" / "mae-sai-2024" / "se1.json"


def unit(flood: float, exposure: float, access: float, road: float, age: float) -> dict[str, float]:
    return dict(zip(ws.COMPONENTS, (flood, exposure, access, road, age)))


VALUES = {
    "wet_town": unit(100, 80, 20, 10, 30),     # most of it floods, few lose access
    "cut_off": unit(60, 20, 100, 100, 40),     # little of it floods, every route is lost
    "quiet": unit(5, 2, 1, 0, 50),
}


def test_the_components_and_weights_are_those_of_the_scoring_module() -> None:
    assert ws.COMPONENTS == tuple(DEFAULT_WEIGHTS)
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
    for name, weights in ws.named_weightings().items():
        assert set(weights) == set(ws.COMPONENTS) and sum(weights.values()) == pytest.approx(1.0), name
    assert ws.named_weightings()["without_access"]["access_gap_0_100"] == 0 and ws.named_weightings()["without_access"]["road_criticality_0_100"] == 0
    for factor in ws.FACTORS:
        for name, weights in ws.one_at_a_time(factor).items():
            assert sum(weights.values()) == pytest.approx(1.0)
            # The changed weight moves in the direction of the factor; the others keep their ratios to each other.
            assert (weights[name] > DEFAULT_WEIGHTS[name]) == (factor > 1)
            others = [key for key in ws.COMPONENTS if key != name]
            assert weights[others[0]] / weights[others[1]] == pytest.approx(DEFAULT_WEIGHTS[others[0]] / DEFAULT_WEIGHTS[others[1]])


def test_the_order_follows_the_weights_and_the_report_says_when_it_turns() -> None:
    report = ws.assess(VALUES, draws=20_000, seed=7)
    # Published weights: 30 + 20 + 4 + 1.5 + 3 = 58.5 against 18 + 5 + 20 + 15 + 4 = 62; the quiet unit 1.5 + 0.5 + 0.2 + 0 + 5 = 7.2.
    assert report["published"]["scores"] == {"wet_town": 58.5, "cut_off": 62.0, "quiet": 7.2}
    assert report["published"]["order"] == ["cut_off", "wet_town", "quiet"]
    named = {entry["id"]: entry for entry in report["named"]}
    assert named["flood_and_exposure_only"]["first"] == "wet_town" and named["flood_and_exposure_only"]["same_order"] is False
    assert named["without_access"]["first"] == "wet_town"
    assert named["equal"]["first"] == "cut_off" and named["equal"]["same_order"] is True
    assert len(report["one_at_a_time"]) == len(ws.COMPONENTS) * len(ws.FACTORS)
    random = report["random"]
    assert random["draws"] == 20_000 and sum(random["share_first"].values()) == pytest.approx(1.0, abs=2e-4)
    assert "quiet" not in random["share_first"] or random["share_first"]["quiet"] < 0.01
    assert 0 < random["share_same_order"] < 1
    assert random["share_same_first_three"] == 1.0  # Three units: the first three are always the same three.
    assert -1 <= random["rank_correlation"]["lowest"] <= random["rank_correlation"]["p05"] <= random["rank_correlation"]["median"] <= 1
    # The same seed gives the same report; another seed gives nearly the same shares.
    assert ws.assess(VALUES, draws=20_000, seed=7) == report
    other = ws.assess(VALUES, draws=20_000, seed=8)["random"]["share_first"]["cut_off"]
    assert other == pytest.approx(random["share_first"]["cut_off"], abs=0.02)


def test_bad_inputs_are_refused() -> None:
    with pytest.raises(ws.WeightSensitivityError):
        ws.assess({"only": VALUES["quiet"]})
    with pytest.raises(ws.WeightSensitivityError):
        ws.assess({**VALUES, "broken": {**VALUES["quiet"], "exposure_0_100": 120}})
    with pytest.raises(ws.WeightSensitivityError):
        ws.assess({**VALUES, "short": {"exposure_0_100": 1.0}})
    with pytest.raises(ws.WeightSensitivityError):
        ws.assess(VALUES, draws=0)
    with pytest.raises(ws.WeightSensitivityError):
        ws.one_at_a_time(0)
    assert ws.order_of([1.0, 3.0, 3.0], ["a", "b", "c"]) == ["b", "c", "a"]


# --- the committed report of case SE1 -----------------------------------------------------------------------------------


def test_the_committed_report_is_what_the_script_writes_from_the_published_case() -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_fpps_weight_sensitivity.py"), "--check"], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert REPORT.read_bytes() == PAGE_COPY.read_bytes() and b"\r" not in REPORT.read_bytes()


def test_the_report_of_case_se1_carries_its_labels_and_says_what_holds() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    case = json.loads(CASE.read_text(encoding="utf-8"))
    assert report["label"] == ws.LABEL and report["case"]["official_warning"] is False
    assert report["case"]["source_timestamp"] == case["source_timestamp"] and "confidence" in report["case"] and report["assumptions"]
    published = {row["unit_id"]: row["fpps_0_100"] for row in case["rows"]}
    assert report["published"]["scores"] == pytest.approx(published, abs=0.005)
    assert report["published"]["weights"] == pytest.approx(DEFAULT_WEIGHTS)
    names = {unit_id: names["en"] for unit_id, names in report["units"].items()}
    first = report["published"]["order"][0]
    assert names[first] == "Ko Chang" and names[report["published"]["order"][1]] == "Mae Sai"
    named = {entry["id"]: entry for entry in report["named"]}
    # What holds: Ko Chang is first with equal weights, with three equal groups and with every one-at-a-time change.
    assert named["equal"]["first"] == first and named["three_groups"]["first"] == first
    assert all(entry["first"] == first for entry in report["one_at_a_time"])
    assert report["random"]["share_first"][first] > 0.85
    assert report["random"]["share_same_first_four"] > 0.99
    # What does not: with the access components left out, or with flood and exposure only, Mae Sai town is first.
    assert names[named["without_access"]["first"]] == "Mae Sai" and names[named["flood_and_exposure_only"]["first"]] == "Mae Sai"
    assert any("says nothing about classes" in line for line in report["limits"])
    flat = json.dumps(report).lower()
    assert "action_class" not in flat and "accepted_fpps" not in flat
