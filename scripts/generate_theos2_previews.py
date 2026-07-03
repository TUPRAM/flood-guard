"""Generate non-operational THEOS-2 optical context preview cards."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.theos2_readiness import write_theos2_preview_svgs  # noqa: E402


def main() -> None:
    """Write SVG preview cards from a selected THEOS-2 manifest."""

    parser = argparse.ArgumentParser(
        description="Write small SVG THEOS-2 optical context preview cards."
    )
    parser.add_argument(
        "--selected-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_selected_file_manifest.csv",
        help="Checksum-backed selected THEOS-2 manifest.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_previews",
        help="Directory for small SVG preview cards.",
    )
    args = parser.parse_args()

    written = write_theos2_preview_svgs(args.selected_manifest, args.output_dir)
    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
