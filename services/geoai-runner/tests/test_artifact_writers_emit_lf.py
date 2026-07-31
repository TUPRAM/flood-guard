"""Pipeline writers must emit LF, not the platform line ending (D-41).

`Path.write_text` and `DataFrame.to_csv` default to `newline=None`, which
translates "\\n" to `os.linesep` — CRLF on Windows. Every text artifact the
pipeline writes then differs from its own committed blob, because
`.gitattributes` normalises to LF on the way in.

That is not cosmetic in this project. Artifacts are verified by exact SHA-256,
so a checksum taken from a freshly written file does not match the checksum of
the committed bytes. It bit the 2026-07-30 baseline: `CHECKSUMS` was computed on
CRLF working-tree files and failed against the LF blobs for 5 of 8 entries.

`.gitattributes` fixes the *repository* side (D-41). This fixes the *writer*
side, so the working tree and the blob agree the moment a run finishes.
"""

from __future__ import annotations

import ast
from pathlib import Path

REALPIPELINE = Path(__file__).resolve().parents[1] / "geoai_runner" / "realpipeline"


def _text_writers_without_explicit_newline(path: Path) -> list[str]:
    """Find write_text / to_csv calls that do not pin the line ending."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offences: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        name = node.func.attr
        if name not in {"write_text", "to_csv"}:
            continue
        kwargs = {kw.arg for kw in node.keywords if kw.arg}
        required = "newline" if name == "write_text" else "lineterminator"
        if required not in kwargs:
            offences.append(f"{path.name}:{node.lineno}: {name}() without {required}=")
    return offences


def test_every_text_writer_pins_lf() -> None:
    offences: list[str] = []
    for path in sorted(REALPIPELINE.rglob("*.py")):
        offences.extend(_text_writers_without_explicit_newline(path))

    assert not offences, (
        "These writers will emit CRLF on Windows, so the artifact will not "
        'match its committed blob. Pass newline="\\n" (write_text) or '
        'lineterminator="\\n" (to_csv):\n  ' + "\n  ".join(offences)
    )


def test_the_check_actually_finds_writers() -> None:
    """Guard against the AST walk silently matching nothing."""

    total = 0
    for path in sorted(REALPIPELINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        total += sum(
            1
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in {"write_text", "to_csv"}
        )
    assert total >= 8, f"expected to find the pipeline's text writers, found {total}"
