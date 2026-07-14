"""Aggregate cell-level committee scores into query-region candidates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.candidate_builder import (  # noqa: E402
    CandidateBuilderError,
    write_region_candidate_manifest,
)


def main() -> None:
    """Write one transparent acquisition-candidate row per query core."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-scores", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--diversity-columns",
        required=True,
        help="Comma-separated, precomputed region summaries repeated per cell.",
    )
    parser.add_argument("--boundary-impurity-column", default="boundary_impurity")
    parser.add_argument("--hard-stratum-column", default="hard_stratum")
    parser.add_argument(
        "--land-cover-stratum-column", default="major_land_cover_stratum"
    )
    parser.add_argument("--top-tail-fraction", type=float, default=0.20)
    args = parser.parse_args()
    diversity_columns = tuple(
        value.strip() for value in args.diversity_columns.split(",") if value.strip()
    )
    try:
        written = write_region_candidate_manifest(
            args.cell_scores,
            diversity_columns=diversity_columns,
            output_path=args.output,
            boundary_impurity_column=args.boundary_impurity_column,
            hard_stratum_column=args.hard_stratum_column,
            land_cover_stratum_column=args.land_cover_stratum_column,
            top_tail_fraction=args.top_tail_fraction,
        )
    except (CandidateBuilderError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote query-region candidates: {written}")


if __name__ == "__main__":
    main()
