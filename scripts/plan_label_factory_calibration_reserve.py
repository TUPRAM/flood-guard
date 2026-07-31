"""Plan an authority-pending parent-tile reserve for reviewer calibration."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.calibration_reserve import (  # noqa: E402
    CalibrationReserveError,
    build_calibration_reserve_design,
)


def main() -> None:
    """Parse explicit governed inputs and write one immutable design package."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-grid-directory", type=Path, required=True)
    parser.add_argument("--context-alignment-manifest", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--design-id", required=True)
    parser.add_argument("--calibration-query-count", type=int, default=12)
    parser.add_argument("--retest-query-count", type=int, default=12)
    parser.add_argument("--reserve-tile-count", type=int, default=2)
    parser.add_argument("--candidate-limit", type=int, default=20)
    parser.add_argument("--minimum-remaining-pool-queries", type=int, default=20)
    parser.add_argument(
        "--created-at-utc",
        help="Optional timezone-aware ISO timestamp for a reproducible build.",
    )
    args = parser.parse_args()

    try:
        paths = build_calibration_reserve_design(
            canonical_grid_directory=args.canonical_grid_directory,
            context_alignment_manifest_path=args.context_alignment_manifest,
            output_directory=args.output_directory,
            design_id=args.design_id,
            calibration_query_count=args.calibration_query_count,
            retest_query_count=args.retest_query_count,
            reserve_tile_count=args.reserve_tile_count,
            candidate_limit=args.candidate_limit,
            minimum_remaining_pool_queries=args.minimum_remaining_pool_queries,
            created_at_utc=args.created_at_utc,
        )
    except (CalibrationReserveError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    for role, path in paths.as_dict().items():
        print(f"Wrote {role}: {path.name}")
    print("Status: PROVISIONAL - Reference Authority approval pending")
    print("No calibration/retest query IDs selected; no review bundle created")
    print(
        "Safety: human annotation=false; training=false; decision layer=false; "
        "FPPS=false; warning=false"
    )


if __name__ == "__main__":
    main()
