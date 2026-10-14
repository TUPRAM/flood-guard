"""The replay's river fit: the evidence of a flood, the level of a stretch, the held-back squares, and the record of revision r5."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import replay_river_fit as rf

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "apps/web/public/studies/mae-sai-2024-timeline/r5/timeline.json").read_text(encoding="utf-8"))
ARCHIVE = json.loads((ROOT / "apps/web/public/studies/mae-sai-2024-timeline/r4/timeline.json").read_text(encoding="utf-8"))


def scenes() -> tuple[dict, dict]:
    """Five cells: turned to mud, stayed wet, stayed green, was bare before, under cloud afterwards."""

    before = {"red": np.array([[0.04, 0.04, 0.04, 0.20, 0.04]]), "nir": np.array([[0.40, 0.40, 0.40, 0.25, 0.40]]),
              "scl": np.array([[4, 4, 4, 5, 4]])}
    after = {"red": np.array([[0.20, 0.05, 0.04, 0.20, 0.20]]), "green": np.array([[0.15, 0.08, 0.06, 0.15, 0.15]]),
             "blue": np.array([[0.10, 0.07, 0.04, 0.10, 0.10]]), "nir": np.array([[0.24, 0.04, 0.40, 0.24, 0.24]]),
             "swir16": np.array([[0.30, 0.02, 0.20, 0.30, 0.30]]), "scl": np.array([[5, 6, 4, 5, 9]])}
    return before, after


def test_evidence_is_ground_that_was_green_and_turned_to_mud_or_stayed_wet() -> None:
    judged, evidence = rf.flood_evidence(*scenes())
    assert judged.tolist() == [[True, True, True, False, False]]
    assert evidence.tolist() == [[True, True, False, False, False]]
    before, after = scenes()
    with pytest.raises(rf.RiverFitError):
        rf.flood_evidence(before, {**after, "nir": after["nir"][:, :3]})


def test_the_chessboard_alternates_by_square() -> None:
    held = rf.chessboard(8, 8, 500.0, 1000.0)
    assert not held[0, 0] and not held[1, 1] and held[0, 2] and held[2, 0] and not held[2, 2]
    assert held.mean() == 0.5
    with pytest.raises(rf.RiverFitError):
        rf.chessboard(4, 4, 100.0, 50.0)


def valley(evidence_up_to: float) -> dict:
    """One straight channel down the middle of a valley whose sides rise by 0.5 m a cell; mud up to a height on both sides."""

    rows, columns = 60, 41
    channel = np.zeros((rows, columns), dtype=bool)
    channel[:, 20] = True
    hand = np.abs(np.arange(columns) - 20)[None, :].repeat(rows, axis=0) * 0.5
    drain = (np.arange(rows)[:, None] * columns + 20).repeat(columns, axis=1)
    evidence = (hand <= evidence_up_to) & ~channel
    return {"hand": hand, "drain": drain, "channel": channel, "evidence": evidence, "fallback": np.where(channel, 1.0, 0.0)}


FIT = {"radius_m": 150.0, "min_cells": 20, "smooth_radius_m": 30.0}


def test_a_stretch_gets_the_level_most_of_its_evidence_lies_below() -> None:
    v = valley(4.0)
    fit = rf.fit_levels(v["hand"], v["drain"], v["channel"], v["evidence"], v["fallback"], 30.0, **FIT)
    middle = fit["channel_level"][30, 20]
    # Evidence lies at eight heights from 0.5 to 4.0 m in equal numbers, so nine tenths of it are reached only at the
    # highest of them: the level is the upper edge of that 0.1 m step.
    assert middle == pytest.approx(4.1) and fit["fitted"][30, 20]
    assert np.isnan(fit["channel_level"][30, 5]) and fit["level"][30, 5] == pytest.approx(middle, abs=0.3)
    wet = v["hand"] < fit["level"]
    covered = (wet & v["evidence"]).sum() / v["evidence"].sum()
    assert 0.8 <= covered <= 1.0


def test_a_stretch_with_too_little_evidence_keeps_its_rule_and_a_level_is_capped() -> None:
    v = valley(4.0)
    v["evidence"][:, :] = False
    v["evidence"][10, 21] = True
    fit = rf.fit_levels(v["hand"], v["drain"], v["channel"], v["evidence"], v["fallback"], 30.0, **FIT)
    assert not fit["fitted"].any() and fit["channel_level"][30, 20] == pytest.approx(1.0)
    high = valley(9.5)
    capped = rf.fit_levels(high["hand"], high["drain"], high["channel"], high["evidence"], high["fallback"], 30.0, **FIT)
    assert capped["channel_level"][30, 20] == pytest.approx(rf.MAX_LEVEL_M)
    with pytest.raises(rf.RiverFitError):
        rf.fit_levels(v["hand"], v["drain"][:-1], v["channel"], v["evidence"], v["fallback"], 30.0)


def test_held_back_channel_cells_give_no_evidence_but_still_get_a_level() -> None:
    v = valley(4.0)
    use = np.ones(v["hand"].shape, dtype=bool)
    use[30:, :] = False
    fit = rf.fit_levels(v["hand"], v["drain"], v["channel"], v["evidence"], v["fallback"], 30.0, use=use, **FIT)
    assert fit["fitted"][10, 20] and not fit["fitted"][55, 20]
    assert fit["channel_level"][55, 20] == pytest.approx(1.0) and fit["channel_level"][10, 20] > 3.0


def test_shares_of_a_peak_against_the_evidence() -> None:
    evidence = np.array([[True, True, False, False]])
    judged = np.array([[True, True, True, False]])
    wet = np.array([[True, False, True, True]])
    result = rf.shares(evidence, judged, wet, cell_km2=2.0)
    assert result == {"evidence_km2": 4.0, "peak_km2": 6.0, "share_of_the_evidence_inside_the_peak": 0.5,
                      "share_of_the_judged_peak_with_evidence": 0.5}
    assert rf.shares(evidence, judged, wet, np.array([[False, False, False, True]]))["share_of_the_evidence_inside_the_peak"] is None


# --- the record of revision r5 --------------------------------------------------------------------------------------


def test_the_manifest_says_the_peak_is_fitted_and_where_the_fit_did_worse() -> None:
    fit = MANIFEST["river_fit"]
    assert MANIFEST["revision"] == "r5" and ARCHIVE["revision"] == "r4" and "river_fit" not in ARCHIVE
    assert fit["label"] == "fitted to the image; not an independent check, not a forecast"
    assert fit["plan"] == "docs/proposal_execution/replay_river_fit_plan_v1.md" and (ROOT / fit["plan"]).exists()
    area, held = fit["replay_area"], fit["held_back_squares"]
    assert area["fitted_model"]["share_of_the_evidence_inside_the_peak"] > area["model_before_the_fit"]["share_of_the_evidence_inside_the_peak"]
    # The failure is in the record: on the held-back squares the fit covers less than the model before it.
    assert held["fitted_on_the_other_squares"]["share_of_the_evidence_inside_the_peak"] < held["model_before_the_fit"]["share_of_the_evidence_inside_the_peak"]
    assert "do not carry over" in held["reading"] and "the owner chose" in held["reading"]
    assert 0 < fit["channel_cells_fitted"] < fit["channel_cells"]
    assert fit["fitted_level_m"]["p95"] <= rf.MAX_LEVEL_M


def test_the_images_the_fit_used_are_no_longer_called_independent() -> None:
    items = {item["id"]: item for item in MANIFEST["exploratory_knowledge"]["items"]}
    for name in ("sentinel-2-mud-line", "sentinel-2-water-check"):
        assert items[name]["relation"] == "used_for_tuning" and items[name]["known_during_tuning"] is True
    assert items["unosat-4009"]["relation"] == "known_during_tuning" and "not an independent check" in items["unosat-4009"]["statement"]
    assert "can exceed 1" in MANIFEST["exploratory_knowledge"]["depth_factor"]
    block = next(item for item in MANIFEST["evidence_blocks"] if "river_fit" in item["covers"])
    assert block["lane"] == "SCN" and "did not carry over" in block["note"]
    assert MANIFEST["official_warning"] is False and MANIFEST["can_feed_decision_layer"] is False and MANIFEST["operational_status"] == "non_operational"


def test_the_factor_of_a_fitted_stretch_fits_in_a_byte() -> None:
    factor = MANIFEST["hand"]["depth_factor"]
    assert factor["byte_scale"] == 2.5 and factor["max"] == pytest.approx(rf.MAX_LEVEL_M / 3.5, abs=1e-3) and factor["max"] <= factor["byte_scale"]
    assert "byte_scale" not in ARCHIVE["hand"]["depth_factor"]
