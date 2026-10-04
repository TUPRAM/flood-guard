import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_optical_reference_candidates.py"
SPEC = importlib.util.spec_from_file_location("probe_optical_reference_candidates", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE  # dataclasses resolve their module by name
SPEC.loader.exec_module(MODULE)


def test_summarize_scl_splits_unobservable_from_clear():
    # 2 no-data, 1 shadow, 3 cloud (8, 9, 10), 2 vegetation, 1 water, 1 not-vegetated
    values = np.array([0, 0, 3, 8, 9, 10, 4, 4, 6, 5])
    summary = MODULE.summarize_scl(values)
    assert summary["pixels"] == 10
    assert summary["unobservable_fraction"] == 0.6
    assert summary["clear_observable_fraction"] == 0.4
    assert summary["scl_fractions"]["water"] == 0.1
    assert summary["scl_fractions"]["no_data"] == 0.2


def test_summarize_scl_rejects_empty_area():
    with pytest.raises(ValueError):
        MODULE.summarize_scl(np.array([], dtype=np.uint8))


def test_match_coincident_is_inclusive_signed_and_sorted():
    t0 = datetime(2024, 9, 15, 23, 16, tzinfo=timezone.utc)
    sar = [("s1", t0)]
    optical = [
        ("before_19h", t0 - timedelta(hours=19, minutes=12)),
        ("after_48h", t0 + timedelta(hours=48)),
        ("after_49h", t0 + timedelta(hours=49)),
    ]
    pairs = MODULE.match_coincident(sar, optical, 48)
    assert [p["optical_item"] for p in pairs] == ["before_19h", "after_48h"]
    assert pairs[0]["hours_optical_minus_sar"] == -19.2
    assert pairs[1]["hours_optical_minus_sar"] == 48.0


def test_match_coincident_rejects_negative_tolerance():
    with pytest.raises(ValueError):
        MODULE.match_coincident([], [], -1)


def test_envelope_never_grants_authority_or_warning():
    env = MODULE._envelope({"probe": "x"}, ["b", "a", "a"])
    assert env["official_warning"] is False
    assert env["can_feed_decision_layer"] is False
    assert env["grants_reference_authority"] is False
    assert env["sources"] == ["a", "b"]
    assert env["assumptions"]
