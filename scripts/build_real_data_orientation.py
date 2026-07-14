"""Build reviewer-safe aggregate orientation artifacts from real Mae Sai data."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from floodguard.label_factory.real_data_orientation import (
    RealDataOrientationError,
    build_real_data_orientation,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the governed sar_change_v2 pool and write aggregate-only "
            "PCA/k-means learning outputs. This never trains a flood classifier."
        )
    )
    parser.add_argument("--feature-csv", required=True)
    parser.add_argument("--derivation-manifest", required=True)
    parser.add_argument("--canonical-query-csv", required=True)
    parser.add_argument("--context-evidence-csv", required=True)
    parser.add_argument("--grid-validation-receipt", required=True)
    parser.add_argument("--release-seal", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--expected-cell-count", type=int, default=874_496)
    parser.add_argument("--expected-query-count", type=int, default=854)
    parser.add_argument("--expected-cells-per-query", type=int, default=1_024)
    parser.add_argument("--expected-spatial-group-count", type=int, default=20)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--random-seed", type=int, default=20_260_713)
    parser.add_argument("--created-at-utc")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        paths = build_real_data_orientation(
            feature_csv=args.feature_csv,
            derivation_manifest_path=args.derivation_manifest,
            canonical_query_csv=args.canonical_query_csv,
            context_evidence_csv=args.context_evidence_csv,
            grid_validation_receipt_path=args.grid_validation_receipt,
            release_seal_path=args.release_seal,
            output_directory=args.output_directory,
            expected_cell_count=args.expected_cell_count,
            expected_query_count=args.expected_query_count,
            expected_cells_per_query=args.expected_cells_per_query,
            expected_spatial_group_count=args.expected_spatial_group_count,
            chunk_size=args.chunk_size,
            random_seed=args.random_seed,
            created_at_utc=args.created_at_utc,
        )
    except RealDataOrientationError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(f"Wrote reviewer-safe real-data orientation: {paths.directory}")
    print("Training gate: blocked_missing_released_training_labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
