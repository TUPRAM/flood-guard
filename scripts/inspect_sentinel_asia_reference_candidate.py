"""Download and inspect the selected Sentinel Asia shapefile candidate outside Git."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.public_reference_files import (  # noqa: E402
    DEFAULT_EXTERNAL_DATA_DIR,
    DEFAULT_SENTINEL_ASIA_SHAPEFILE_URL,
    download_public_reference_candidate,
    write_public_reference_file_inspection_manifest,
)


def main(argv: list[str] | None = None) -> int:
    """Run the selected Sentinel Asia public reference inspection workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_SENTINEL_ASIA_SHAPEFILE_URL)
    parser.add_argument(
        "--external-data-dir",
        type=Path,
        default=DEFAULT_EXTERNAL_DATA_DIR,
        help="External workspace outside the Git repository.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "public_reference_file_inspection_manifest.csv",
    )
    parser.add_argument(
        "--existing-zip",
        type=Path,
        default=None,
        help="Inspect an already-downloaded ZIP instead of downloading.",
    )
    parser.add_argument(
        "--retrieved-at",
        default=None,
        help="Optional fixed UTC timestamp for reproducible tests.",
    )
    args = parser.parse_args(argv)

    zip_path = args.existing_zip or download_public_reference_candidate(
        args.url,
        args.external_data_dir,
    )
    local_path_hint = f"<external_data_workspace>/sentinel_asia/{zip_path.name}"
    written = write_public_reference_file_inspection_manifest(
        zip_path,
        args.output,
        source_url=args.url,
        local_path_hint=local_path_hint,
        retrieved_at_utc=args.retrieved_at,
    )
    print(f"Inspected {local_path_hint}")
    print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
