"""Build a package-checksum manifest for selected local DEM ZIP packages."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.dem_readiness import (  # noqa: E402
    DEFAULT_DEM_PACKAGES,
    write_dem_selected_file_manifest,
)


def main(argv: list[str] | None = None) -> int:
    """Write the selected DEM package-readiness manifest."""

    parser = argparse.ArgumentParser(
        description="Checksum selected local DEM ZIP packages without extraction."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="Directory containing local DEM package(s).",
    )
    parser.add_argument(
        "--local-library",
        type=Path,
        default=REPO_ROOT / "outputs" / "local_data_library_manifest.csv",
        help="Metadata-only local data library manifest.",
    )
    parser.add_argument(
        "--zip-members",
        type=Path,
        default=REPO_ROOT / "outputs" / "local_data_library_zip_members.csv",
        help="Metadata-only ZIP member catalog.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "dem_selected_file_manifest.csv",
        help="Output selected DEM readiness CSV.",
    )
    parser.add_argument(
        "--selected-package",
        action="append",
        default=None,
        help=(
            "Selected DEM ZIP package to checksum. Repeat for multiple packages. "
            "Defaults to the two local Copernicus DEM/elevation-slope packages."
        ),
    )
    args = parser.parse_args(argv)

    selected_packages = args.selected_package or list(DEFAULT_DEM_PACKAGES)
    written = write_dem_selected_file_manifest(
        input_dir=args.input_dir,
        local_library_path=args.local_library,
        zip_members_path=args.zip_members,
        output_path=args.output,
        selected_packages=selected_packages,
    )
    print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
