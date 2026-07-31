"""GeoAI must stay an optional extra, never a base dependency (D-33 / ADR-0001).

The root decision package, the API, and the normal runner test environment are
deliberately unable to import ``geoai`` or ``torch``. CI job ``geoai-normal``
asserts this at runtime, and the audit calls the resulting isolation one of the
project's genuine architectural strengths: it keeps a ~292-package ML stack out
of the decision engine entirely.

That runtime assertion only covers the environment CI happens to build. Once a
developer installs the extra locally -- which D-33 now requires them to do --
the easiest way to "fix" an ImportError is to move ``geoai-py`` into the base
``dependencies`` list, and nothing in the suite would object. The runtime check
would keep passing right up until CI rebuilt its environment.

These tests assert the *manifest* instead, so they hold regardless of which
environment pytest is running in -- including the .venv-geoai environment where
``import geoai`` legitimately succeeds.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

RUNNER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = RUNNER_ROOT.parents[1]

# Packages that must never become non-optional anywhere in the repository.
HEAVY = {"geoai-py", "torch", "torchvision", "segmentation-models-pytorch", "samgeo"}


def _manifest(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _base_dependencies(manifest: dict) -> list[str]:
    return list(manifest.get("project", {}).get("dependencies", []))


def _name_of(requirement: str) -> str:
    for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", ";"):
        requirement = requirement.split(sep)[0]
    return requirement.strip().lower()


def test_runner_base_dependencies_exclude_the_geoai_stack() -> None:
    manifest = _manifest(RUNNER_ROOT / "pyproject.toml")
    base = {_name_of(dep) for dep in _base_dependencies(manifest)}
    leaked = base & HEAVY
    assert not leaked, (
        f"{sorted(leaked)} moved into the runner's base dependencies. GeoAI must "
        "stay in an optional extra or the dependency-light environment -- and "
        "the isolation CI job asserts -- is destroyed."
    )


def test_geoai_stack_is_reachable_only_through_extras() -> None:
    manifest = _manifest(RUNNER_ROOT / "pyproject.toml")
    extras = manifest.get("project", {}).get("optional-dependencies", {})
    declared = {_name_of(dep) for deps in extras.values() for dep in deps}
    assert "geoai-py" in declared, (
        "geoai-py is no longer declared in any extra; the runner could not "
        "install the GeoAI stack at all."
    )


def test_root_and_api_manifests_never_depend_on_the_geoai_stack() -> None:
    offenders: dict[str, list[str]] = {}
    for label, path in (
        ("root", REPO_ROOT / "pyproject.toml"),
        ("api", REPO_ROOT / "services" / "api" / "pyproject.toml"),
    ):
        if not path.is_file():
            continue
        manifest = _manifest(path)
        found = {_name_of(dep) for dep in _base_dependencies(manifest)} & HEAVY
        extras = manifest.get("project", {}).get("optional-dependencies", {})
        found |= {_name_of(dep) for deps in extras.values() for dep in deps} & HEAVY
        if found:
            offenders[label] = sorted(found)
    assert not offenders, (
        "The decision engine and API must never depend on the GeoAI stack, in "
        f"base dependencies or extras: {offenders}"
    )


def test_ci_still_asserts_the_runtime_isolation() -> None:
    """The manifest check complements the runtime one; keep both."""

    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "find_spec('geoai') is None" in workflow, (
        "CI no longer asserts that the dependency-light environment cannot "
        "import geoai."
    )
