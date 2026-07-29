"""Shared fixtures for the API test suite.

Pins ``floodguard`` to this checkout before importing the app -- see the
hermeticity note below (D-06). The root and runner suites have the same problem
and solve it the same way.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

# ---------------------------------------------------------------------------
# Test-suite hermeticity (D-06) -- MUST run before `floodguard_api` is imported.
#
# `pyproject.toml` installs the decision package as
# `floodguard-thailand = { path = "../..", editable = true }`, resolved when the
# virtualenv is created. A virtualenv built from the main working copy keeps
# importing that copy's `src/` even when pytest runs from another worktree or
# branch.
#
# `floodguard_api.dataset_registry` imports `floodguard.scoring`, so a stale
# editable install fails at collection with
# `ImportError: cannot import name 'assign_action_reason_code'` -- the API is
# then untested against the decision engine it actually ships with.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"

if SRC_ROOT.is_dir():
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    _parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if not _parts or Path(_parts[0]) != SRC_ROOT:
        os.environ["PYTHONPATH"] = os.pathsep.join(
            [str(SRC_ROOT)] + [p for p in _parts if Path(p) != SRC_ROOT]
        )

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from floodguard_api.app import create_app  # noqa: E402
from floodguard_api.repository import ArtifactRepository  # noqa: E402


@pytest.fixture
def repository() -> ArtifactRepository:
    return ArtifactRepository()


@pytest.fixture
def client(repository: ArtifactRepository) -> Iterator[TestClient]:
    with TestClient(create_app(repository)) as test_client:
        yield test_client
