"""Shared fixtures for the GeoAI runner test suite.

Also pins ``floodguard`` to this checkout -- see the hermeticity note below
(D-06). The root suite has the same problem and solves it the same way in
``tests/conftest.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# services/geoai-runner/tests/conftest.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"

# ---------------------------------------------------------------------------
# Test-suite hermeticity (D-06).
#
# `pyproject.toml` installs the decision package as
# `floodguard-thailand = { path = "../..", editable = true }`. That path is
# resolved when the environment is *created*, so a virtualenv built from the
# main working copy keeps importing the main working copy's `src/` even when
# pytest runs from a different worktree or branch.
#
# The suite then silently validates the wrong source tree, and fails outright
# when the two trees differ: collection of test_wrappers_integration.py and
# test_geoai_smoke.py aborted with `ModuleNotFoundError: No module named
# 'floodguard.probability_aggregation'` because the installed checkout predated
# that module.
#
# Prepending this checkout's `src/` to both `sys.path` (for in-process imports)
# and `PYTHONPATH` (inherited by any subprocess) makes the runner suite test the
# tree it was invoked against.
# ---------------------------------------------------------------------------
if SRC_ROOT.is_dir():
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    _parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if not _parts or Path(_parts[0]) != SRC_ROOT:
        os.environ["PYTHONPATH"] = os.pathsep.join(
            [str(SRC_ROOT)] + [p for p in _parts if Path(p) != SRC_ROOT]
        )

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
