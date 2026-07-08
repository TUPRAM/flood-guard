"""Acquire selected Mae Sai CDSE Sentinel-1 products outside Git when credentials exist."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.cdse_download import (  # noqa: E402
    DEFAULT_EXTERNAL_DATA_DIR,
    write_cdse_mae_sai_acquisition_manifest,
)


def main(argv: list[str] | None = None) -> int:
    """Run credential-gated CDSE Sentinel-1 acquisition."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metadata",
        type=Path,
        default=REPO_ROOT / "outputs" / "cdse_mae_sai_2024_metadata.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "cdse_mae_sai_acquisition_manifest.csv",
    )
    parser.add_argument(
        "--external-data-dir",
        type=Path,
        default=DEFAULT_EXTERNAL_DATA_DIR,
        help="External data workspace outside the Git repository.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retrieved-at", default=None)
    args = parser.parse_args(argv)

    written = write_cdse_mae_sai_acquisition_manifest(
        args.metadata,
        args.output,
        external_data_dir=args.external_data_dir,
        access_token=os.environ.get("CDSE_ACCESS_TOKEN"),
        username=os.environ.get("CDSE_USERNAME"),
        password=os.environ.get("CDSE_PASSWORD"),
        dry_run=args.dry_run,
        retrieved_at_utc=args.retrieved_at,
    )
    print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
