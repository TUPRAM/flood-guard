"""Review selected Sentinel Asia geometry quality with QGIS/GDAL ogrinfo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.sentinel_asia_geometry_review import (  # noqa: E402
    DEFAULT_SENTINEL_ASIA_ZIP,
    write_sentinel_asia_geometry_review,
)


def main(argv: list[str] | None = None) -> int:
    """Run QGIS/GDAL Sentinel Asia geometry quality review."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inspection",
        type=Path,
        default=REPO_ROOT / "outputs" / "public_reference_file_inspection_manifest.csv",
    )
    parser.add_argument("--zip-path", type=Path, default=DEFAULT_SENTINEL_ASIA_ZIP)
    parser.add_argument("--ogrinfo-path", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "sentinel_asia_geometry_quality_review.csv",
    )
    parser.add_argument(
        "--notes-output",
        type=Path,
        default=REPO_ROOT / "docs" / "sentinel_asia_geometry_quality_notes.md",
    )
    parser.add_argument("--reviewed-at", default=None)
    args = parser.parse_args(argv)

    csv_path, notes_path = write_sentinel_asia_geometry_review(
        args.inspection,
        args.output,
        args.notes_output,
        zip_path=args.zip_path,
        ogrinfo_path=args.ogrinfo_path,
        reviewed_at_utc=args.reviewed_at,
    )
    print(f"Wrote {csv_path}")
    print(f"Wrote {notes_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
