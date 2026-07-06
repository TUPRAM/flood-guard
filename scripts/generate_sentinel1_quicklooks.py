"""Generate optional small Sentinel-1 SAR context quicklooks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.sentinel1_quicklook import (  # noqa: E402
    Sentinel1QuicklookError,
    detect_raster_reader,
    write_sentinel1_quicklook_manifest,
)


def main() -> None:
    """Generate Sentinel-1 quicklooks or report the blocking condition."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate small non-operational Sentinel-1 SAR context quicklooks "
            "from checksum-backed selected files."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="Directory containing the selected local Sentinel-1 TIFF.",
    )
    parser.add_argument(
        "--selected-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "sentinel1_selected_file_manifest.csv",
        help="Checksum-backed selected Sentinel-1 manifest.",
    )
    parser.add_argument(
        "--provenance-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "sentinel1_provenance_resolved_manifest.csv",
        help="Optional Sentinel-1 provenance manifest for timing/provenance labels.",
    )
    parser.add_argument(
        "--quicklook-dir",
        type=Path,
        default=REPO_ROOT / "outputs",
        help="Directory for generated small PNG quicklooks.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "sentinel1_quicklook_manifest.csv",
        help="Output quicklook manifest CSV.",
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
        help="Maximum quicklook width or height in pixels.",
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
        written = write_sentinel1_quicklook_manifest(
            input_dir=args.input_dir,
            selected_manifest_path=args.selected_manifest,
            provenance_manifest_path=args.provenance_manifest,
            quicklook_dir=args.quicklook_dir,
            output_path=args.output,
            preferred_reader=args.reader,
            max_size=args.max_size,
            verify_checksum=args.verify_checksum,
        )
    except Sentinel1QuicklookError as exc:
        print(f"Sentinel-1 quicklook generation blocked: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()
