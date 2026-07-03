"""Build a metadata-only inventory for local THEOS-2 hackathon samples."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.theos2_inventory import write_theos2_local_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Write the THEOS-2 local metadata manifest."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="Directory containing local THEOS-2 sample files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_local_metadata_manifest.csv",
        help="Metadata-only CSV output path.",
    )
    args = parser.parse_args(argv)
    written = write_theos2_local_manifest(args.input_dir, args.output)
    print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

