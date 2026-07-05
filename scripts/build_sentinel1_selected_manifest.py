"""Build a checksum-backed manifest for selected local Sentinel-1 files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.sentinel1_readiness import (  # noqa: E402
    DEFAULT_SELECTED_SENTINEL1_FILES,
    write_sentinel1_selected_file_manifest,
)


def main() -> None:
    """Write the selected Sentinel-1 checksum manifest."""

    parser = argparse.ArgumentParser(
        description="Checksum selected local Sentinel-1 files without processing pixels."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="Directory containing local Sentinel-1 file(s).",
    )
    parser.add_argument(
        "--local-library",
        type=Path,
        default=REPO_ROOT / "outputs" / "local_data_library_manifest.csv",
        help="Metadata-only local data library manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "sentinel1_selected_file_manifest.csv",
        help="Output selected-file checksum manifest CSV.",
    )
    parser.add_argument(
        "--selected-file",
        action="append",
        default=None,
        help=(
            "Selected Sentinel-1 file name to checksum. Repeat for multiple files. "
            "Defaults to the standalone Mae Sai-overlapping candidate."
        ),
    )
    args = parser.parse_args()

    selected_files = args.selected_file or list(DEFAULT_SELECTED_SENTINEL1_FILES)
    written = write_sentinel1_selected_file_manifest(
        input_dir=args.input_dir,
        local_library_path=args.local_library,
        output_path=args.output,
        selected_files=selected_files,
    )
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()
