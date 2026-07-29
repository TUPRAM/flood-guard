"""Session-wide test configuration — test-suite hermeticity (D-06).

The problem
-----------
``pyproject.toml`` sets ``[tool.pytest.ini_options] pythonpath = ["src"]``, so
*in-process* tests import ``floodguard`` from **this checkout**. Tests that
spawn a CLI via ``subprocess.run([sys.executable, ...])`` do not inherit that
setting: the child interpreter resolves ``floodguard`` through the editable
install (``__editable__.floodguard_thailand-0.1.0.pth``), which points at
whichever checkout was installed -- typically the main working copy, not the
worktree under test.

The result is a test suite that silently validates the wrong source tree. When
the two checkouts are on different branches it fails outright: 16 subprocess
CLI tests raised ``ModuleNotFoundError: No module named
'floodguard.controlled_experiment'`` because the installed checkout was on a
branch predating that module.

This is not a Windows or worktree quirk. It reproduces for anyone with two
clones, a stale editable install, or an editable install pointing at a
different branch. CI passes only because a fresh clone happens to install the
same tree it tests.

The fix
-------
Make the subprocess environment agree with the in-process one by exporting
``PYTHONPATH`` for the whole session. ``subprocess.run`` inherits
``os.environ`` by default, and the call sites that build their own environment
all do so as ``{**os.environ, ...}``, so both styles are covered without
touching 39 individual spawn sites.

Prepending (rather than replacing) keeps any ``PYTHONPATH`` the developer or CI
already set. Tests that need to be explicit can call :func:`hermetic_env`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _prepend_pythonpath(env: dict[str, str]) -> dict[str, str]:
    """Return ``env`` with this checkout's ``src/`` first on ``PYTHONPATH``."""

    src = str(SRC_ROOT)
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if parts and Path(parts[0]) == SRC_ROOT:
        return env
    parts = [src] + [p for p in parts if Path(p) != SRC_ROOT]
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def hermetic_env(**overrides: str) -> dict[str, str]:
    """A subprocess environment pinned to this checkout.

    Use for subprocess tests that need extra variables::

        subprocess.run(cmd, env=hermetic_env(FLOODGUARD_TEST_KEY=key))
    """

    env = _prepend_pythonpath(dict(os.environ))
    env.update(overrides)
    return env


# Applied at conftest import, before collection, so every subprocess spawned
# during the session inherits it.
_prepend_pythonpath(os.environ)  # type: ignore[arg-type]

# Keep the in-process path consistent with the subprocess one. pytest's
# `pythonpath` ini setting already does this, but conftest is imported first
# and an explicit prepend makes the two agree unconditionally.
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
