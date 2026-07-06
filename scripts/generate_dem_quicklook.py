"""Generate an optional small DEM terrain-context quicklook."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.dem_quicklook import (  # noqa: E402
    DEMQuicklookError,
    detect_raster_reader,
    write_dem_quicklook,
)


def main() -> None:
    """Generate a DEM quicklook or report the blocking condition."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate a small non-operational DEM terrain-context quicklook from "
            "an extracted checksum-tracked DEM TIFF outside Git."
        )
    )
    parser.add_argument(
        "--selected-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "dem_selected_file_manifest.csv",
        help="Package-level selected DEM readiness manifest.",
    )
    parser.add_argument(
        "--extracted-dem-path",
        type=Path,
        help="Local extracted DEM TIFF path outside the Git repository.",
    )
    parser.add_argument(
        "--member-name",
        help="DEM member name from the selected manifest.",
    )
    parser.add_argument(
        "--member-sha256",
        help="SHA-256 checksum of the extracted DEM TIFF member.",
    )
    parser.add_argument(
        "--local-path-hint",
        help="Redacted path hint for the extracted DEM TIFF.",
    )
    parser.add_argument(
        "--quicklook-path",
        type=Path,
        default=REPO_ROOT / "outputs" / "dem_quicklook.png",
        help="Output small PNG quicklook path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "dem_quicklook_manifest.csv",
        help="Output DEM quicklook manifest CSV.",
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
        "--no-verify-checksum",
        action="store_true",
        help="Skip recomputing the extracted member SHA-256.",
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

    if args.extracted_dem_path is None:
        print(
            "DEM quicklook generation blocked: extracted DEM TIFF path is required.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    try:
        written = write_dem_quicklook(
            selected_manifest=args.selected_manifest,
            extracted_dem_path=args.extracted_dem_path,
            output_path=args.output,
            quicklook_path=args.quicklook_path,
            member_name=args.member_name,
            member_sha256=args.member_sha256,
            local_extracted_path_hint=args.local_path_hint,
            repo_root=REPO_ROOT,
            preferred_reader=args.reader,
            max_size=args.max_size,
            verify_checksum=not args.no_verify_checksum,
        )
    except DEMQuicklookError as exc:
        print(f"DEM quicklook generation blocked: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()
