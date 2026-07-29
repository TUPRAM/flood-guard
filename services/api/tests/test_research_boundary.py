"""The API must never serve ungoverned research output (D-35).

`research/` holds exploratory artifacts -- geoai-skills output, downloaded
benchmarks, scratch rasters -- with no checksum, no ModelRun, no registry entry
and no `official_warning=false` marker.

If any of that reached the API it would be indistinguishable from governed
evidence at the point where it matters most: a planner reading a priority
table. The whole artifact-lifecycle split (ADR-C) collapses the moment one
`research/` path becomes resolvable here.

Promotion out of `research/` is a re-run under `realpipeline` with a spatial
holdout and a signed receipt -- never a file copy. These tests are the
enforcement; without them the boundary is a convention that survives exactly
until someone is in a hurry.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from floodguard_api.config import RepositoryPaths

REPO_ROOT = Path(__file__).resolve().parents[3]


def _configured_paths() -> list[tuple[str, Path]]:
    """Every location the API can resolve.

    `RepositoryPaths` is a slots dataclass whose artifact locations are exposed
    as properties (`outputs`, `fixtures`, `contracts`), not fields, so `vars()`
    sees nothing useful. Walk the class instead, so a newly added property is
    covered automatically rather than silently escaping this check.
    """

    paths = RepositoryPaths.discover()
    names = [f.name for f in dataclasses.fields(paths)]
    names += [
        name
        for name, attr in vars(type(paths)).items()
        if isinstance(attr, property) and not name.startswith("_")
    ]

    resolved: list[tuple[str, Path]] = []
    for name in names:
        value = getattr(paths, name)
        if isinstance(value, (str, Path)):
            resolved.append((name, Path(value)))
    return resolved


def test_no_configured_path_resolves_into_research() -> None:
    configured = _configured_paths()
    # Guard against the walk silently finding nothing and passing vacuously.
    assert {"outputs", "fixtures"} <= {name for name, _ in configured}, (
        f"path discovery is not seeing the artifact locations: {configured}"
    )

    offenders = [
        (name, str(path)) for name, path in configured if "research" in Path(path).parts
    ]
    assert not offenders, (
        "The API resolves a path inside research/, which holds ungoverned "
        f"exploratory output with no provenance: {offenders}"
    )


def test_api_source_contains_no_research_path_literal() -> None:
    """Guard the string form too, in case a path is built at request time."""

    api_src = REPO_ROOT / "services" / "api" / "src"
    offenders: list[str] = []
    for path in api_src.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if '"research"' in line or "'research'" in line or "research/" in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}")
    assert not offenders, f"API source references research/: {offenders}"


def test_research_directory_is_gitignored_except_its_manifest() -> None:
    """The sandbox must not be able to leak artifacts into the repository."""

    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "research/**" in gitignore, "research/ contents are not gitignored"
    assert "!research/MANIFEST.md" in gitignore, "research/MANIFEST.md must stay tracked"

    research = REPO_ROOT / "research"
    if not research.is_dir():
        return
    tracked = os.popen(f'git -C "{REPO_ROOT}" ls-files research').read().split()
    assert tracked == ["research/MANIFEST.md"], (
        f"Only research/MANIFEST.md may be tracked; found: {tracked}"
    )
