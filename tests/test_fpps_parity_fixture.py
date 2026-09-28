"""The stored FPPS parity fixture must match the Python scoring engine.

The web port (apps/web/src/lib/fpps.ts) is tested against this fixture, so a drift
here would let the replay's scenario FPPS silently disagree with ``floodguard.scoring``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_fpps_parity_fixture", ROOT / "scripts" / "build_fpps_parity_fixture.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fixture_matches_python_engine() -> None:
    builder = _builder()
    stored = json.loads(builder.FIXTURE_PATH.read_text(encoding="utf-8"))
    assert stored == json.loads(json.dumps(builder.build_fixture())), (
        "tests/fixtures/fpps_parity_cases.json is stale; rerun scripts/build_fpps_parity_fixture.py"
    )


def test_fixture_covers_every_action_class_and_reason() -> None:
    stored = json.loads(_builder().FIXTURE_PATH.read_text(encoding="utf-8"))
    classes = {row["action_class"] for row in stored["default_outputs"]}
    reasons = {row["action_reason_code"] for row in stored["default_outputs"]}
    assert classes == {"A", "B", "C", "D", "E"}
    assert {"low_confidence", "low_priority_score"} <= reasons
