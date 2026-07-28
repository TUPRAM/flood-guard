"""Shared fixtures for the GeoAI runner test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

# services/geoai-runner/tests/conftest.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[3]

_REQUIRED_CONTEXT = (
    REPO_ROOT / "outputs" / "mae_sai_subdistrict_flood_inputs.csv",
    REPO_ROOT / "outputs" / "mae_sai_admin_context.geojson",
)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root, skipping when the committed decision-layer context is absent.

    A handful of tests assert against the real Mae Sai context artifacts rather
    than fixtures, because the point of those tests is that the runner consumes
    the decision layer's genuine outputs. They skip rather than fail in a checkout
    where ``outputs/`` has been cleaned, so the suite stays runnable standalone.
    """

    missing = [path.name for path in _REQUIRED_CONTEXT if not path.exists()]
    if missing:
        pytest.skip(f"committed decision-layer context not present: {missing}")
    return REPO_ROOT
