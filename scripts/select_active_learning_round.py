"""Select a deterministic query-only active-learning review batch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.acquisition import (  # noqa: E402
    AcquisitionManifestError,
    write_active_learning_selection,
    write_round_zero_selection,
)


def main() -> None:
    """Write an internal score manifest; use the separate blinded-bundle CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument(
        "--round-zero",
        action="store_true",
        help="Use model-independent round0_stratum selection; ignore model scores.",
    )
    parser.add_argument(
        "--diversity-columns",
        default="",
        help="Comma-separated region features; required after round zero.",
    )
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--random-seed", type=int, default=0)
    parser.add_argument(
        "--disagreement-metric",
        choices=("absolute", "jensen_shannon"),
        default="absolute",
    )
    parser.add_argument("--minimum-center-distance-m", type=float, default=0.0)
    parser.add_argument(
        "--near-duplicate-feature-distance",
        type=float,
        default=1e-9,
    )
    parser.add_argument("--maximum-per-event", type=int)
    parser.add_argument("--maximum-per-land-cover-stratum", type=int)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    diversity_columns = tuple(
        value.strip() for value in args.diversity_columns.split(",") if value.strip()
    )
    try:
        if args.round_zero:
            written = write_round_zero_selection(
                args.candidates,
                round_id=args.round_id,
                batch_size=args.batch_size,
                random_seed=args.random_seed,
                minimum_center_distance_m=args.minimum_center_distance_m,
                manifest_output_path=args.manifest_output,
                summary_output_path=args.summary_output,
            )
        else:
            if not diversity_columns:
                raise AcquisitionManifestError(
                    "--diversity-columns is required after round zero."
                )
            written = write_active_learning_selection(
                args.candidates,
                round_id=args.round_id,
                diversity_columns=diversity_columns,
                batch_size=args.batch_size,
                random_seed=args.random_seed,
                disagreement_metric=args.disagreement_metric,
                minimum_center_distance_m=args.minimum_center_distance_m,
                near_duplicate_feature_distance=args.near_duplicate_feature_distance,
                maximum_per_event=args.maximum_per_event,
                maximum_per_land_cover_stratum=(
                    args.maximum_per_land_cover_stratum
                ),
                manifest_output_path=args.manifest_output,
                summary_output_path=args.summary_output,
            )
    except (AcquisitionManifestError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for label, path in written.items():
        print(f"Wrote {label}: {path}")


if __name__ == "__main__":
    main()
