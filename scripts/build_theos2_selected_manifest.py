"""Build a checksum-backed manifest for selected THEOS-2 sample files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.theos2_readiness import (
    DEFAULT_SELECTED_THEOS2_FILES,
    write_theos2_selected_file_manifest,
)


def main() -> None:
    """Write the selected THEOS-2 checksum manifest."""

    parser = argparse.ArgumentParser(
        description="Checksum only selected local THEOS-2 files."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="Directory containing local THEOS-2 sample files.",
    )
    parser.add_argument(
        "--local-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_local_metadata_manifest.csv",
        help="Metadata-only THEOS-2 local manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_selected_file_manifest.csv",
        help="Output selected-file checksum manifest CSV.",
    )
    parser.add_argument(
        "--selected-file",
        action="append",
        default=None,
        help=(
            "Selected THEOS-2 file name to checksum. Repeat for multiple files. "
            "Defaults to the curated disaster-context candidates."
        ),
    )
    parser.add_argument(
        "--delivery-metadata",
        type=Path,
        help="Use the strict written-terms delivery intake, separate from legacy sample inventory.",
    )
    parser.add_argument(
        "--aoi-dir", type=Path, default=REPO_ROOT / "resources/aoi/upload"
    )
    args = parser.parse_args()
    if args.delivery_metadata:
        from floodguard.theos2_delivery import write_delivery_manifest

        print(
            f"Wrote {write_delivery_manifest(args.input_dir, args.delivery_metadata, args.aoi_dir, args.output)}"
        )
        return

    selected_files = args.selected_file or list(DEFAULT_SELECTED_THEOS2_FILES)
    written = write_theos2_selected_file_manifest(
        input_dir=args.input_dir,
        local_manifest_path=args.local_manifest,
        output_path=args.output,
        selected_files=selected_files,
    )
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()
