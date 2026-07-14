"""Build an immutable query-model training table from a validated label release."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.training_join import (  # noqa: E402
    TrainingJoinError,
    build_and_write_training_table,
)


def main() -> None:
    """Validate authoritative inputs and publish one content-addressed join."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labelset-manifest",
        type=Path,
        required=True,
        help="Authoritative frozen labelset JSON.",
    )
    parser.add_argument(
        "--release-validation-receipt",
        type=Path,
        required=True,
        help="Code-generated passing release-validation receipt JSON.",
    )
    parser.add_argument(
        "--final-cell-csv",
        type=Path,
        required=True,
        help="Canonical final-cell CSV whose hash is in the frozen raster set.",
    )
    parser.add_argument(
        "--feature-csv",
        type=Path,
        required=True,
        help="Aligned cell-level sar_change_v2 feature CSV.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="A new directory; existing paths are never overwritten.",
    )
    parser.add_argument(
        "--created-at-utc",
        help="Optional timezone-aware ISO timestamp for reproducible test runs.",
    )
    args = parser.parse_args()
    try:
        written = build_and_write_training_table(
            labelset_manifest_path=args.labelset_manifest,
            release_validation_receipt_path=args.release_validation_receipt,
            final_cell_csv=args.final_cell_csv,
            feature_csv=args.feature_csv,
            output_directory=args.output_directory,
            created_at_utc=args.created_at_utc,
        )
    except TrainingJoinError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for label, path in written.as_dict().items():
        print(f"Wrote {label}: {path}")


if __name__ == "__main__":
    main()

