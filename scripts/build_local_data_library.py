"""Build a metadata-only local data library for provided hackathon files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.local_data_library import write_local_data_library  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Write metadata-only local data library outputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="Directory containing local hackathon-provided data files.",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=REPO_ROOT / "outputs" / "local_data_library_manifest.csv",
        help="Top-level local file manifest CSV.",
    )
    parser.add_argument(
        "--zip-members-output",
        type=Path,
        default=REPO_ROOT / "outputs" / "local_data_library_zip_members.csv",
        help="ZIP member catalog CSV.",
    )
    args = parser.parse_args(argv)

    manifest_path, members_path = write_local_data_library(
        input_dir=args.input_dir,
        manifest_output_path=args.manifest_output,
        zip_members_output_path=args.zip_members_output,
    )
    print(f"Wrote {manifest_path}")
    print(f"Wrote {members_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
