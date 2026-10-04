"""One reading of owner choice 22 ("a distinct named hospital") for every caller.

The E0 context spike and the planning-frame build count hospitals through
floodguard.hospital_counts. These tests use invented names only; they compute
no FPPS, no A-E class and no ensemble.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from floodguard import planning_frames
from floodguard.hospital_counts import UNNAMED_FACILITY, count_hospitals, hospital_name_key

ROOT = Path(__file__).resolve().parents[1]


def _spike_module():
    spec = importlib.util.spec_from_file_location("run_planning_context_spike", ROOT / "scripts" / "run_planning_context_spike.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_names_that_differ_only_in_whitespace_or_case_are_one_hospital_for_every_caller() -> None:
    rows = [
        {"name": "Hospital A"},
        {"name": "hospital  a"},
        {"name": "Hospital\nA "},
        {"name": "Hospital B"},
        {"name": UNNAMED_FACILITY},
        {"name": ""},
        {"name": None},
    ]
    expected = {
        "osm_objects": 7,
        "distinct_named_hospitals": 2,
        "unnamed_objects": 3,
        "objects_that_repeat_a_named_hospital": 2,
    }
    assert count_hospitals(rows) == expected
    assert expected["distinct_named_hospitals"] + expected["unnamed_objects"] + expected[
        "objects_that_repeat_a_named_hospital"] == expected["osm_objects"]
    assert hospital_name_key(" Hospital\tA\n") == hospital_name_key("hospital a") == "hospital a"
    assert hospital_name_key(UNNAMED_FACILITY) is None and hospital_name_key("  ") is None

    # The planning-frame build and the E0 spike give the same counts on the same rows.
    assert planning_frames.hospital_counts(rows) == expected
    spike = _spike_module()
    breakdown = spike.hospital_breakdown(rows)
    assert {key: breakdown[key] for key in expected} == expected
    assert spike.UNNAMED_FACILITY == UNNAMED_FACILITY
