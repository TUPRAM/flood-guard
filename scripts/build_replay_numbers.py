"""Write (or check) ``docs/demo/replay_numbers.md``: every figure a deck or a speaker may quote about the Mae Sai replay.

The figures come from the replay files the page serves (``timeline.json``, the season envelope's ``envelope.json``,
``access-nodes.bin`` and ``tambons.geojson``), each checked against the SHA-256 the manifest lists; the rules are in
``floodguard.replay_numbers``. Run it after every re-bake and re-read the figures the deck quotes:

    .venv/Scripts/python.exe scripts/build_replay_numbers.py           # rewrite the document
    .venv/Scripts/python.exe scripts/build_replay_numbers.py --check   # exit 1 if the committed document is stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard.replay_numbers import build  # noqa: E402

DOCUMENT = ROOT / "docs" / "demo" / "replay_numbers.md"


def main(argv: list[str] | None = None) -> int:
    """Write the document, or with ``--check`` report whether the committed one matches the replay files."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed document instead of writing it")
    args = parser.parse_args(argv)
    text = build(ROOT)
    if args.check:
        current = DOCUMENT.read_text(encoding="utf-8") if DOCUMENT.is_file() else ""
        if current != text:
            print(f"{DOCUMENT.relative_to(ROOT).as_posix()} is stale: run scripts/build_replay_numbers.py and re-read the deck's figures.")
            return 1
        print(f"{DOCUMENT.relative_to(ROOT).as_posix()} matches the replay files.")
        return 0
    DOCUMENT.parent.mkdir(parents=True, exist_ok=True)
    with DOCUMENT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {DOCUMENT.relative_to(ROOT).as_posix()} ({len(text.encode('utf-8')):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
