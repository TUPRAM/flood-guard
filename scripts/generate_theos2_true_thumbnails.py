"""Generate optional true PNG thumbnails from selected THEOS-2 files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.theos2_thumbnails import (  # noqa: E402
    THEOS2ThumbnailError,
    detect_raster_reader,
    write_theos2_thumbnail_manifest,
)


def main() -> None:
    """Generate true thumbnails or report the missing optional raster reader."""

    parser = argparse.ArgumentParser(
        description="Generate small PNG thumbnails from checksum-backed THEOS-2 files."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="Directory containing local THEOS-2 sample files.",
    )
    parser.add_argument(
        "--selected-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_selected_file_manifest.csv",
        help="Checksum-backed selected THEOS-2 manifest.",
    )
    parser.add_argument(
        "--thumbnail-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_thumbnails",
        help="Directory for generated small PNG thumbnails.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_thumbnail_manifest.csv",
        help="Output thumbnail manifest CSV.",
    )
    parser.add_argument(
        "--reader",
        choices=("auto", "rasterio", "gdal"),
        default="auto",
        help="Optional raster reader to use.",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=512,
        help="Maximum thumbnail width or height in pixels.",
    )
    parser.add_argument(
        "--verify-checksum",
        action="store_true",
        help="Recompute SHA-256 before reading the source file.",
    )
    parser.add_argument(
        "--check-reader",
        action="store_true",
        help="Only print optional raster reader availability and exit.",
    )
    args = parser.parse_args()

    reader_status = detect_raster_reader(args.reader)
    if args.check_reader:
        print(reader_status.message)
        raise SystemExit(0 if reader_status.available else 2)

    try:
        written = write_theos2_thumbnail_manifest(
            input_dir=args.input_dir,
            selected_manifest_path=args.selected_manifest,
            thumbnail_dir=args.thumbnail_dir,
            output_path=args.output,
            preferred_reader=args.reader,
            max_size=args.max_size,
            verify_checksum=args.verify_checksum,
        )
    except THEOS2ThumbnailError as exc:
        print(f"THEOS-2 thumbnail generation blocked: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()
