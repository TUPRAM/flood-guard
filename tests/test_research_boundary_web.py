"""The web app must never read ungoverned research output (D-35).

Companion to `services/api/tests/test_research_boundary.py`. The API is one of
two ways data reaches a user; the other is the web app reading committed JSON
directly (`apps/web/public/`, build-time bundle imports, and the GeoAI panel's
runtime fetch of `/geoai/mae-sai-real.json`).

That second path bypasses the API and the contract layer entirely, so guarding
only the API would leave the larger hole open.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOTS = ("apps/web/src", "apps/web/public", "apps/web/scripts")
SUFFIXES = {".ts", ".tsx", ".mjs", ".js", ".json", ".css"}

# `research` appears legitimately in prose (e.g. "research tier", "researcher"
# as a role name). Only flag it when used as a path segment.
PATH_LIKE = re.compile(r"""["'`/.]research/|/research["'`]|\bresearch/[A-Za-z0-9_.-]+""")


def test_web_sources_do_not_reference_research_paths() -> None:
    offenders: list[str] = []
    for root in WEB_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix not in SUFFIXES or not path.is_file():
                continue
            if "node_modules" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if PATH_LIKE.search(line):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()[:120]}"
                    )
    assert not offenders, (
        "The web app references a research/ path. Research output is "
        "ungoverned and must never reach a user surface:\n" + "\n".join(offenders)
    )


def test_research_manifest_exists_and_states_the_rule() -> None:
    manifest = REPO_ROOT / "research" / "MANIFEST.md"
    assert manifest.is_file(), "research/MANIFEST.md is missing"
    text = manifest.read_text(encoding="utf-8")
    assert "never a file copy" in text, (
        "The manifest must state that promotion is a re-run, not a copy."
    )
