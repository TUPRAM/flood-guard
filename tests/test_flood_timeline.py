"""Tests for the Mae Sai day-by-day flood reconstruction helpers and baked manifest."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from floodguard.flood_timeline import (
    CHANNEL_CODE,
    HAND_STEP_M,
    IMPASSABLE_DEPTH_M,
    KEYFRAMES,
    NEVER_CODE,
    decode_hand,
    depth_at_stage,
    depth_factor,
    encode_hand,
    flooded_area_km2,
    road_state,
    stage_at,
)

MANIFEST = Path(__file__).resolve().parents[1] / "apps/web/public/studies/mae-sai-2024-timeline/r3/timeline.json"


def test_stage_hits_keyframes_at_local_noon_and_clamps() -> None:
    for index, keyframe in enumerate(KEYFRAMES):
        assert stage_at(index + 0.5) == pytest.approx(keyframe.stage_m)
    assert stage_at(-5) == KEYFRAMES[0].stage_m
    assert stage_at(99) == KEYFRAMES[-1].stage_m
    assert stage_at(1.0 + 18.25 / 24) == pytest.approx(0.1)
    assert stage_at(2.0 + 2 / 24) == pytest.approx(2.5)


def test_dry_day_stays_dry_all_day() -> None:
    for hour in range(25):
        assert stage_at(hour / 24) == 0.0
    assert stage_at(1.25) > 0.0


def test_keyframes_follow_the_chronology() -> None:
    phases = [k.phase for k in KEYFRAMES]
    assert phases[0] == "dry" and phases[-1] == "gone"
    peak = max(KEYFRAMES, key=lambda k: k.stage_m)
    assert peak.phase == "peak"
    assert KEYFRAMES[0].stage_m == 0 and KEYFRAMES[-1].stage_m == 0
    assert all(b.day.toordinal() - a.day.toordinal() == 1 for a, b in zip(KEYFRAMES, KEYFRAMES[1:]))


def test_encode_decode_round_trip_and_reserved_codes() -> None:
    hand = np.array([0.0, 0.049, 1.0, 2.5, 20.0, 3.0])
    channel = np.array([True, False, False, False, False, False])
    valid = np.array([True, True, True, True, True, False])
    codes = encode_hand(hand, channel, valid)
    assert codes[0] == CHANNEL_CODE
    assert codes[1] == 1  # Non-channel cells never collide with the channel code.
    assert decode_hand(codes)[2] == pytest.approx(1.0)
    assert decode_hand(codes)[3] == pytest.approx(2.5)
    assert codes[4] == NEVER_CODE and codes[5] == NEVER_CODE
    assert np.isinf(decode_hand(codes)[4])


def test_depth_at_stage() -> None:
    codes = np.array([CHANNEL_CODE, 20, 60, NEVER_CODE], dtype=np.uint8)  # channel, 1.0 m, 3.0 m, never
    depth = depth_at_stage(codes, 2.0)
    assert depth.tolist() == pytest.approx([2.0, 1.0, 0.0, 0.0])


def test_flooded_area_excludes_channel_and_never_codes() -> None:
    hist = [0] * 256
    hist[CHANNEL_CODE] = 1000
    hist[NEVER_CODE] = 1000
    hist[10] = 50  # 0.5 m
    hist[40] = 30  # 2.0 m
    assert flooded_area_km2(hist, 0.0, 100) == 0
    assert flooded_area_km2(hist, 1.0, 100) == pytest.approx(50 * 100 / 1e6)
    assert flooded_area_km2(hist, 2.01, 100) == pytest.approx(80 * 100 / 1e6)
    with pytest.raises(ValueError):
        flooded_area_km2([1, 2, 3], 1.0, 100)


def test_road_state_thresholds() -> None:
    assert road_state(1.0, 1.0) == "dry"
    assert road_state(1.0, 1.0 + IMPASSABLE_DEPTH_M / 2) == "wet"
    assert road_state(1.0, 1.0 + IMPASSABLE_DEPTH_M) == "impassable"
    assert road_state(3.2, 3.5) == "impassable"  # Float subtraction gives 0.2999999999999998.
    assert road_state(1.0, 1.4, depth_factor=0.5) == "wet"  # 0.5 * 0.4 = 0.2 m on a tributary.


def test_depth_factor_and_scaled_depth() -> None:
    k = depth_factor(np.array([1000.0, 500.0, 1.0]), 500.0)
    assert k[0] == 1.0 and k[1] == 1.0  # Capped at the main stem.
    assert k[2] == pytest.approx(0.35)  # Floored for tiny catchments.
    assert depth_factor(np.array([62.5]), 500.0)[0] == pytest.approx(0.125 ** 0.3)
    codes = np.array([CHANNEL_CODE, 20], dtype=np.uint8)
    assert depth_at_stage(codes, 2.0, np.array([0.5, 0.5])).tolist() == pytest.approx([1.0, 0.5])


@pytest.mark.skipif(not MANIFEST.exists(), reason="baked manifest not present")
def test_baked_manifest_is_honest_and_consistent() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["official_warning"] is False and manifest["real_time"] is False
    assert manifest["can_feed_decision_layer"] is False
    assert manifest["confidence"] == "low" and manifest["confidence_reason"]
    assert manifest["source_timestamp"] and manifest["assumptions"] and manifest["sources"]
    assert manifest["hand"]["step_m"] == HAND_STEP_M
    assert [d["stage_m"] for d in manifest["days"]] == [k.stage_m for k in KEYFRAMES]
    for day in manifest["days"]:
        expected = sum(flooded_area_km2(h, day["stage_m"], manifest["pixel_area_m2"]) for h in manifest["tambon_histograms"].values())
        assert day["stats"]["flooded_km2"] == pytest.approx(expected, abs=0.005)
    dry, peak = manifest["days"][0]["stats"], max(manifest["days"], key=lambda d: d["stage_m"])["stats"]
    assert dry["flooded_km2"] == 0 and dry["road_km_impassable"] == 0
    assert peak["flooded_km2"] > 0 and peak["road_km_impassable"] > 0
    knots = manifest["stage_anchors"]
    assert all(stage_at(k["t"]) == pytest.approx(k["stage_m"]) for k in knots)
    assert all(0 < c["modelled_km2"] <= c["total_km2"] + 0.05 for c in manifest["tambon_coverage"].values())  # 10 m rasterisation
    assert manifest["hand"]["depth_factor_channel"] == "G"
    assert manifest["population"]["licence"] == "CC BY 4.0"
    assert 70_000 < sum(manifest["population"]["tambon_totals"].values()) < 95_000  # WorldPop 2020 for the 8 tambons.
    shelters = manifest["shelters"]
    plan_ids = [p["candidate_id"] for p in shelters["plan"]]
    candidates = {c["id"]: c for c in shelters["candidates"]}
    assert plan_ids and all(candidates[i]["eligible"] for i in plan_ids)
    shares = [p["cumulative_share"] for p in shelters["plan"]]
    assert shares == sorted(shares) and 1 <= shelters["knee_k"] <= len(plan_ids)
    assert all(c["kind"] != "shelter" for c in shelters["candidates"])
    assert manifest["access"]["sets"][-1] == f"plan_{len(plan_ids)}"
    checks = {c["id"]: c for c in manifest["external_checks"]}
    assert {"gistda-radarsat2-20240910", "unosat-3991"} <= set(checks)
    reported = manifest["shelters"]["reported"]
    assert reported and all(r["sources"] for r in reported)
    assert all((r["lat"] is None) == (r["model_check"] is None) for r in reported)
    anchor = manifest["s1_anchor"]
    assert abs(anchor["reconstruction_stage_at_pass_m"] - anchor["best_fit_stage_m"]) <= 0.05
