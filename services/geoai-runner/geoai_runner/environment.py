"""Runtime checks kept behind explicit calls so root imports stay dependency-free."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import version

EXPECTED_GEOAI_VERSION = "0.41.1"
# Source reference supplied by the architecture package; callers must retain the
# independent source receipt because a PyPI wheel cannot prove its Git commit.
EXPECTED_GEOAI_COMMIT = "6833c8b71fb18f5b8ea17d5d9f8e0745157643c2"


class EnvironmentError(RuntimeError):
    """Raised when the isolated runtime does not match its frozen contract."""


@dataclass(frozen=True, slots=True)
class EnvironmentReceipt:
    python_version: str
    geoai_version: str
    declared_geoai_commit: str
    platform: str


def inspect_environment(*, declared_geoai_commit: str) -> EnvironmentReceipt:
    """Import GeoAI lazily and verify Python, package version, and source receipt."""

    if sys.version_info[:2] != (3, 12):
        raise EnvironmentError("The GeoAI runner requires Python 3.12 exactly.")
    if declared_geoai_commit != EXPECTED_GEOAI_COMMIT:
        raise EnvironmentError(
            "The declared GeoAI commit does not match the reviewed source reference."
        )
    geoai = import_module("geoai")
    installed = getattr(geoai, "__version__", None)
    if installed is None:
        installed = version("geoai-py")
    if installed != EXPECTED_GEOAI_VERSION:
        raise EnvironmentError(f"Expected geoai-py {EXPECTED_GEOAI_VERSION}, found {installed}.")
    return EnvironmentReceipt(
        python_version=platform.python_version(),
        geoai_version=installed,
        declared_geoai_commit=declared_geoai_commit,
        platform=platform.platform(),
    )
