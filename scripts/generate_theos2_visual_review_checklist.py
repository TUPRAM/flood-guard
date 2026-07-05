"""Generate a pending manual visual-review checklist for THEOS-2 context."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.theos2_review import write_theos2_visual_review_checklist  # noqa: E402


def main() -> None:
    """Write a manual-review checklist initialized with pending fields."""

    parser = argparse.ArgumentParser(
        description="Generate THEOS-2 optical-context manual-review checklist."
    )
    parser.add_argument(
        "--selected-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_selected_file_manifest.csv",
        help="Checksum-backed selected THEOS-2 manifest.",
    )
    parser.add_argument(
        "--thumbnail-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_thumbnail_manifest.csv",
        help="Optional true-thumbnail manifest. Used when present.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_visual_review_checklist.csv",
        help="Output CSV path.",
    )
    args = parser.parse_args()

    written = write_theos2_visual_review_checklist(
        selected_manifest_path=args.selected_manifest,
        thumbnail_manifest_path=args.thumbnail_manifest,
        output_path=args.output,
    )
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()
