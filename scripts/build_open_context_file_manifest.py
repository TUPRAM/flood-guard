"""Build the file-level open context data manifest.

This script may download public context files to an external data workspace when
`--download` is supplied. It never writes source rasters, OSM extracts, or
boundary packages into the repository.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.open_context_manifest import (  # noqa: E402
    DEFAULT_EXTERNAL_DATA_ROOT,
    write_open_context_manifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "open_context_data_file_manifest.csv",
    )
    parser.add_argument(
        "--external-data-root",
        type=Path,
        default=DEFAULT_EXTERNAL_DATA_ROOT,
        help="External workspace for downloaded context files.",
    )
    parser.add_argument(
        "--dem-path",
        type=Path,
        default=None,
        help=(
            "Optional existing outside-Git DEM TIFF to record as terrain context. "
            "Defaults to the external workspace DEM tile when present."
        ),
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download remote WorldPop, HDX, and Geofabrik files outside Git.",
    )
    parser.add_argument("--retrieved-at", default=None)
    args = parser.parse_args(argv)

    written = write_open_context_manifest(
        args.output,
        retrieved_at_utc=args.retrieved_at,
        external_data_root=args.external_data_root,
        download=args.download,
        dem_path=args.dem_path,
    )
    print(f"Wrote {written}")
    print(f"External data root: {args.external_data_root}")
    print("Source files remain outside Git; commit only the manifest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
