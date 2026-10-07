"""Tests of the THEOS-2 optical cross-check functions, on invented arrays."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import theos2_cross_check as cc

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "theos2_cross_check"


def _scene() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """A 120 by 120 image: vegetation, a road band, a water block, a small roof and a cloud."""

    rng = np.random.default_rng(7)
    shape = (120, 120)
    red = np.full(shape, 380.0)
    green = np.full(shape, 380.0)
    blue = np.full(shape, 450.0)
    nir = np.full(shape, 800.0)  # vegetation: NDWI about -0.36
    red[:, 60:66], green[:, 60:66], blue[:, 60:66], nir[:, 60:66] = 430.0, 420.0, 470.0, 500.0  # road: about -0.09
    red[10:60, 5:55], green[10:60, 5:55], blue[10:60, 5:55], nir[10:60, 5:55] = 670.0, 500.0, 500.0, 420.0  # water
    red[80:86, 20:26], green[80:86, 20:26], blue[80:86, 20:26], nir[80:86, 20:26] = 650.0, 500.0, 560.0, 430.0  # roof
    red[90:115, 85:115], green[90:115, 85:115], blue[90:115, 85:115], nir[90:115, 85:115] = 760.0, 620.0, 680.0, 860.0
    noise = rng.normal(0.0, 4.0, size=(4, *shape))
    return red + noise[0], green + noise[1], blue + noise[2], nir + noise[3]


def test_ndwi_sign_and_missing_values() -> None:
    index = cc.ndwi(np.array([[500.0, 380.0, 0.0]]), np.array([[420.0, 800.0, 0.0]]))
    assert index[0, 0] > 0 > index[0, 1]
    assert np.isnan(index[0, 2])
    with pytest.raises(cc.CrossCheckError):
        cc.ndwi(np.zeros((2, 2)), np.zeros((3, 3)))


def test_three_class_otsu_separates_three_populations() -> None:
    rng = np.random.default_rng(3)
    values = np.concatenate([rng.normal(-0.35, 0.02, 4000), rng.normal(-0.10, 0.02, 2000), rng.normal(0.08, 0.02, 3000)])
    lower, upper = cc.multi_otsu_thresholds(values, low=-0.6, high=0.4, bins=200)
    assert -0.30 < lower < -0.15
    assert -0.06 < upper < 0.04
    two_class = cc.otsu_threshold(values, low=-0.6, high=0.4, bins=200)
    assert two_class < upper  # the two-class split puts the middle population with the water


def test_optical_water_finds_the_block_and_drops_roof_and_cloud() -> None:
    red, green, blue, nir = _scene()
    config = cc.OpticalWaterConfig(min_object_px=100, bright_min_width_px=11, bright_margin_px=3)
    water, summary = cc.optical_water(red, green, blue, nir, np.ones(red.shape, dtype=bool), config)
    assert (water[15:55, 10:50] == cc.WATER_YES).all()  # the water block
    assert (water[80:86, 20:26] != cc.WATER_YES).all()  # the roof is too small an object
    assert (water[95:110, 90:110] == cc.WATER_UNOBSERVABLE).all()  # the cloud
    assert (water[:, 61:65] == cc.WATER_NO).all()  # the road is not water under the three-class threshold
    assert summary["ndwi_threshold_source"] == "three_class_otsu_upper"
    assert summary["ndwi_two_class_otsu"] < summary["ndwi_threshold_applied"]
    assert summary["pixels_dropped_by_object_rule"] >= 36


def test_optical_water_boxes_and_bad_shapes() -> None:
    red, green, blue, nir = _scene()
    config = cc.OpticalWaterConfig(min_object_px=100, unobservable_boxes=((0, 30, 0, 30),))
    water, summary = cc.optical_water(red, green, blue, nir, np.ones(red.shape, dtype=bool), config)
    assert (water[:30, :30] == cc.WATER_UNOBSERVABLE).all()
    assert summary["unobservable_boxed_pixels"] == 900
    with pytest.raises(cc.CrossCheckError):
        cc.optical_water(red, green, blue, nir, np.ones(red.shape, dtype=bool),
                         cc.OpticalWaterConfig(unobservable_boxes=((0, 500, 0, 10),)))
    with pytest.raises(cc.CrossCheckError):
        cc.optical_water(red[:10], green, blue, nir, np.ones(red.shape, dtype=bool))


def test_reference_cells_rules() -> None:
    share = np.array([[0.0, 0.5, 0.95, 0.3, np.nan]])
    seen = np.array([[1.0, 0.95, 0.9, 0.89, 1.0]])
    cells = cc.reference_cells(share, seen)
    assert cells["compared"].tolist() == [[True, True, True, False, False]]
    assert cells["wet"].tolist() == [[False, True, True, False, False]]
    assert cells["dry"].tolist() == [[True, False, False, False, False]]
    assert cells["mixed"].tolist() == [[False, True, False, False, False]]


def test_agreement_counts_two_readings() -> None:
    candidate = np.array([[1, 1, 0, 0, 255, 255, 1]], dtype="uint8")
    wet = np.array([[True, False, True, False, True, False, False]])
    compared = np.array([[True, True, True, True, True, True, False]])
    result = cc.agreement(candidate, wet, compared, cell_area_km2=0.0001)
    answered = result["on_answered_cells"]
    strict = result["strict_no_answer_counts_as_not_a_candidate"]
    assert (answered["tp"], answered["fp"], answered["fn"], answered["tn"]) == (1, 1, 1, 1)
    assert (strict["tp"], strict["fp"], strict["fn"], strict["tn"]) == (1, 1, 2, 2)
    assert result["answered_cells"] == 4 and result["compared_cells"] == 6
    assert answered["iou"] == pytest.approx(1 / 3, abs=1e-6)
    assert strict["recall"] == pytest.approx(1 / 3, abs=1e-6)
    with pytest.raises(cc.CrossCheckError):
        cc.agreement(candidate, np.ones((1, 7), dtype=bool), compared, cell_area_km2=0.0001)


def test_scores_are_none_without_a_denominator() -> None:
    assert cc.scores(0, 0, 0, 5) == {"iou": None, "precision": None, "recall": None, "f1": None}


def test_agreement_by_class_covers_every_cell_once() -> None:
    candidate = np.array([[1, 0, 1, 0]], dtype="uint8")
    wet = np.array([[True, True, False, False]])
    compared = np.ones((1, 4), dtype=bool)
    classes = np.array([[40, 40, 50, 10]])
    result = cc.agreement_by_class(candidate, wet, compared, classes, {"cropland": (40,), "built_up": (50,)},
                                   cell_area_km2=0.0001)
    assert sum(block["compared_cells"] for block in result.values()) == 4
    assert result["cropland"]["on_answered_cells"]["tp"] == 1
    assert result["built_up"]["on_answered_cells"]["fp"] == 1
    assert result["other"]["compared_cells"] == 1


def test_centreline_water_lengths_and_seen_under_water() -> None:
    water = np.zeros((50, 50), dtype="uint8")
    water[:, 10:25] = cc.WATER_YES  # x from 20 m to 50 m at 2 m cells
    water[:, 40:] = cc.WATER_UNOBSERVABLE  # x from 80 m
    segments = np.array([
        [[0.0, 50.0], [60.0, 50.0]],   # crosses 30 m of water
        [[0.0, 50.0], [10.0, 50.0]],   # dry
        [[20.0, 50.0], [35.0, 50.0]],  # 15 m, all on water: short edge
        [[60.0, 50.0], [100.0, 50.0]],  # half unobservable
    ])
    rows = cc.centreline_water_lengths(segments, water, west=0.0, north=100.0, cell_m=2.0)
    assert rows[0]["on_water_m"] == pytest.approx(30.0, abs=1.0)
    assert rows[1]["on_water_m"] == 0.0
    assert rows[2]["on_water_m"] == pytest.approx(15.0, abs=1.0)
    assert rows[3]["observable_share"] == pytest.approx(0.5, abs=0.03)
    assert [cc.seen_under_water(row) for row in rows] == [True, False, True, False]


def test_road_agreement_shares() -> None:
    result = cc.road_agreement([True, True, False, False], [True, False, True, False], [100.0, 300.0, 100.0, 500.0])
    assert result["closed_by_rule_and_seen_under_water"] == {"edges": 1, "km": 0.1}
    assert result["share_of_rule_closed_that_is_seen_under_water"] == {"by_edges": 0.5, "by_km": 0.25}
    assert result["share_of_seen_under_water_that_the_rule_closes"] == {"by_edges": 0.5, "by_km": 0.5}
    empty = cc.road_agreement([False], [False], [10.0])
    assert empty["share_of_rule_closed_that_is_seen_under_water"] == {"by_edges": None, "by_km": None}


@pytest.mark.parametrize("name", sorted(path.name for path in OUTPUTS.glob("*.json")))
def test_committed_outputs_carry_the_required_fields(name: str) -> None:
    """AGENTS.md: every output carries its source time, its confidence and its assumptions."""

    record = json.loads((OUTPUTS / name).read_text(encoding="utf-8"))
    assert record["official_warning"] is False
    assert record["operational_status"] == "non_operational"
    assert record["confidence_class"] == "low"
    assert record["source_timestamp"] == "2025-07-30T03:33:31Z"
    assert record["generated_at_utc"].endswith("Z")
    assert record["plan"]["path"] == "docs/proposal_execution/theos2_cross_check_plan_v1.md"
    if "receipt" not in name:
        assert record["assumptions"] and record["limits"]


def test_result_is_labelled_as_agreement_and_holds_no_score() -> None:
    path = OUTPUTS / "sukhothai_20250730_v1.json"
    if not path.exists():
        pytest.skip("the comparison has not been run")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert "not accuracy" in record["label"]
    assert record["can_feed_decision_layer"] is False
    assert set(record["methods"]) == {"un_spider", "m1_literal", "m1_v2"}

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for item in value.values() for key in keys(item)}
        if isinstance(value, list):
            return {key for item in value for key in keys(item)}
        return set()

    assert not {key for key in keys(record) if "fpps" in key.lower() or "action_class" in key.lower()}
    receipt = json.loads((OUTPUTS / "sukhothai_20250730_v1_receipt.json").read_text(encoding="utf-8"))
    import hashlib

    recorded = receipt["outputs"]["outputs/theos2_cross_check/sukhothai_20250730_v1.json"]["sha256"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == recorded
