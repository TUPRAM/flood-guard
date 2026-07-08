"""Dry-run validator for the Mae Sai real-data file manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.ingestion import (  # noqa: E402
    IngestionPlanError,
    validate_mae_sai_file_manifest_ready,
)


def main() -> None:
    """Validate the Mae Sai file manifest and print the blocking reason."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate that the Mae Sai reference mask and Sentinel-1 pair rows "
            "are legally and file-level ready. This script never downloads data."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_real_data_file_manifest.csv",
        help="Mae Sai file-level manifest CSV.",
    )
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 after printing blockers. Useful for current dry-run status checks.",
    )
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest, dtype=str).fillna("")
    try:
        ready = validate_mae_sai_file_manifest_ready(manifest)
    except IngestionPlanError as exc:
        print("BLOCKED: Mae Sai real non-ML baseline cannot start.")
        print(str(exc))
        _print_row_summary(manifest)
        raise SystemExit(0 if args.allow_blocked else 1) from exc

    print("READY: Mae Sai real non-ML baseline gates passed.")
    print(ready.loc[:, ["source_name", "candidate_use", "product_id", "local_path"]].to_string(index=False))


def _print_row_summary(manifest: pd.DataFrame) -> None:
    columns = [
        column
        for column in (
            "source_name",
            "candidate_use",
            "product_id",
            "processing_allowed",
            "reason_blocked",
        )
        if column in manifest.columns
    ]
    if columns:
        print(manifest.loc[:, columns].to_string(index=False))


if __name__ == "__main__":
    main()
