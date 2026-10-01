"""The committed equity/access parity fixture must be what the Python code computes today.

The web tests check ``flood-timeline-evacuation.ts`` against
``apps/web/src/lib/__fixtures__/mae-sai-equity-access-parity.json``. That only proves parity with Python if
the fixture is current, so this test regenerates it in memory and compares. When it fails, a rule changed in
``floodguard.equity`` or in ``scripts/mae_sai_timeline_evacuation.py`` (or the served manifest changed): run
``python apps/web/scripts/equity-access-parity-fixture.py`` and let the web tests judge the TypeScript side.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "apps" / "web" / "scripts" / "equity-access-parity-fixture.py"
FIXTURE = ROOT / "apps" / "web" / "src" / "lib" / "__fixtures__" / "mae-sai-equity-access-parity.json"


@pytest.fixture(scope="module")
def generator():
    pytest.importorskip("rasterio")  # The builder stage the generator loads imports it.
    spec = importlib.util.spec_from_file_location("equity_access_parity_fixture", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_fixture_equals_a_fresh_python_computation(generator) -> None:
    committed = FIXTURE.read_bytes()
    assert b"\r" not in committed
    assert generator.fixture_text() == committed.decode("utf-8")


def test_fixture_is_labelled_as_a_scenario_with_a_vulnerability_proxy() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["scenario_tier"].startswith("T1 scenario (model)")
    assert "vulnerable = terrain/remoteness proxy" in fixture["vulnerable_definition"]
    assert fixture["confidence"] == "low" and fixture["source_timestamp"] and len(fixture["assumptions"]) >= 3
    assert fixture["official_warning"] is False
    # Access and equity figures only: no priority score and no action class.
    assert not any("fpps" in key.lower() or "action_class" in key.lower() for key in fixture)


def test_edge_cases_pin_both_band_limits_and_every_undefined_result(generator) -> None:
    rows = {name: row for (name, *_), row in zip(generator.EQUITY_EDGE_INPUTS, generator.equity_rows([row[1:] for row in generator.EQUITY_EDGE_INPUTS]))}
    band = lambda name: rows[name][7]  # noqa: E731
    assert band("ratio exactly 1.2 (upper limit of similar)") == "similar" and band("ratio 1.201 (just above 1.2)") == "higher"
    assert band("ratio exactly 0.8 (lower limit of similar)") == "similar" and band("ratio 0.799 (just below 0.8)") == "lower"
    assert rows["only vulnerable loss"][6:8] == [None, None]
    assert rows["no vulnerable residents"][4:8] == [None, 0.1, None, None]
    assert rows["no other residents"][4:8] == [0.1, None, None, None]
    assert rows["no loss in either group"][4:8] == [0.0, 0.0, 1.0, "similar"]
    assert generator.band_of("anything else") is None
