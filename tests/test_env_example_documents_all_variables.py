"""Every project-owned environment variable must be documented (D-05).

A deployer cannot discover `NEXT_PUBLIC_FLOODGUARD_API_URL` by reading the
code, and leaving it unset does not fail loudly -- the web app silently falls
back to committed offline bundles and shows stale data. Undocumented
configuration is therefore a crisis-safety problem here, not just a
convenience one.

This test keeps `.env.example` honest as the codebase changes: adding a new
`FLOODGUARD_*` variable without documenting it fails the suite.

Only project-owned prefixes are checked. Standard variables (PATH, HOME,
NODE_ENV, GDAL/AWS/AZURE tuning) are deliberately out of scope -- documenting
them would be noise.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Project-owned namespaces. Anything matching these must appear in .env.example.
OWNED = r"(?:NEXT_PUBLIC_)?FLOODGUARD_[A-Z0-9_]+|GEOAI_[A-Z0-9_]+|RUN_GEOAI_SMOKE"

# Direct access: process.env.X, process.env["X"], os.environ["X"],
# os.environ.get("X"), os.getenv("X"), monkeypatch.setenv("X", ...).
DIRECT_ACCESS = re.compile(
    r"""process\.env(?:\.|\[\s*["'])\s*(OWNED)          # JS/TS
      | (?:os\.)?environ(?:\.get)?\(?\s*\[?\s*["'](OWNED)  # python mapping
      | (?:os\.)?getenv\(\s*["'](OWNED)                 # python getenv
      | setenv\(\s*["'](OWNED)                          # monkeypatch/tests
    """.replace("OWNED", OWNED),
    re.VERBOSE,
)

# Indirect: a name held in a constant or passed as a CLI argument, e.g.
#   DEFAULT_SIGNING_KEY_ENV = "FLOODGUARD_ZONAL_SIGNING_KEY_HEX"
#   "--signing-key-env", "FLOODGUARD_TEST_PROMOTION_KEY"
# Requiring "env" on the same line keeps plain constants such as
# `GEOAI_DIR = REPO_ROOT / ...` and postMessage type strings out.
INDIRECT = re.compile(rf"""["']({OWNED})["']""")


SEARCH_ROOTS = ("apps/web/src", "apps/web/scripts", "src", "services", "scripts", ".github")
SUFFIXES = {".ts", ".tsx", ".mjs", ".js", ".py", ".yml", ".yaml"}

# Referenced only as a literal inside .env.example's own prose, or defined by
# the CI provider rather than by us.
EXEMPT: frozenset[str] = frozenset()


def _names_in(text: str) -> set[str]:
    names: set[str] = set()
    for match in DIRECT_ACCESS.finditer(text):
        names.update(g for g in match.groups() if g)
    for line in text.splitlines():
        if "env" not in line.lower():
            continue
        names.update(INDIRECT.findall(line))
    return names


def _referenced_variables() -> dict[str, set[str]]:
    """Map variable name -> set of files referencing it."""

    found: dict[str, set[str]] = {}
    for root in SEARCH_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix not in SUFFIXES or not path.is_file():
                continue
            if "node_modules" in path.parts or ".venv" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for name in _names_in(text):
                found.setdefault(name, set()).add(str(path.relative_to(REPO_ROOT)))
    return found


def _documented_variables() -> set[str]:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    return {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


def test_env_example_exists() -> None:
    assert ENV_EXAMPLE.is_file(), ".env.example is missing"


def test_every_referenced_variable_is_documented() -> None:
    referenced = _referenced_variables()
    documented = _documented_variables()

    undocumented = {
        name: sorted(files)
        for name, files in referenced.items()
        if name not in documented and name not in EXEMPT
    }

    assert not undocumented, (
        "Environment variables are referenced in code but absent from "
        ".env.example. Add them, with a note on what happens when they are "
        f"unset:\n{undocumented}"
    )


def test_no_secret_values_are_committed() -> None:
    """`.env.example` must carry names and prose only, never real values."""

    offenders = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        name, value = (part.strip() for part in line.split("=", 1))
        # `competition` is a documented non-secret default; everything else
        # bearing a value in a file named *.example is suspicious.
        if value and value != "competition":
            offenders.append(name)

    assert not offenders, f".env.example contains non-placeholder values for: {offenders}"
