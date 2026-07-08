"""Build planned file manifests for open context data sources."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.open_context_manifest import write_open_context_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "open_context_data_file_manifest.csv",
    )
    parser.add_argument("--retrieved-at", default=None)
    args = parser.parse_args(argv)
    written = write_open_context_manifest(args.output, retrieved_at_utc=args.retrieved_at)
    print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
