"""Build the candidate-only v1 adaptive Otsu baseline from canonical RTC rasters."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.sentinel1_processing import (
    Sentinel1ProcessingError,
    build_adaptive_otsu_candidate,
)


def main(argv: list[str] | None = None) -> int:
    """Write an immutable candidate bundle and print its receipt path."""

    parser = argparse.ArgumentParser(description=__doc__)
    for role in (
        "pre-vv-db",
        "pre-vh-db",
        "post-vv-db",
        "post-vh-db",
        "pre-layover-shadow",
        "post-layover-shadow",
        "permanent-water",
        "terrain-slope-degrees",
        "pre-processing-manifest",
        "post-processing-manifest",
        "context-alignment-manifest",
    ):
        parser.add_argument(f"--{role}", required=True, type=Path)
    parser.add_argument("--pre-observed-at-utc", required=True)
    parser.add_argument("--post-observed-at-utc", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--study-area-id", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = build_adaptive_otsu_candidate(
            pre_vv_db=args.pre_vv_db,
            pre_vh_db=args.pre_vh_db,
            post_vv_db=args.post_vv_db,
            post_vh_db=args.post_vh_db,
            pre_layover_shadow=args.pre_layover_shadow,
            post_layover_shadow=args.post_layover_shadow,
            permanent_water=args.permanent_water,
            terrain_slope_degrees=args.terrain_slope_degrees,
            pre_processing_manifest=args.pre_processing_manifest,
            post_processing_manifest=args.post_processing_manifest,
            context_alignment_manifest=args.context_alignment_manifest,
            pre_observed_at_utc=args.pre_observed_at_utc,
            post_observed_at_utc=args.post_observed_at_utc,
            event_id=args.event_id,
            study_area_id=args.study_area_id,
            output_directory=args.output_directory,
        )
    except Sentinel1ProcessingError as exc:
        parser.error(str(exc))
    print(json.dumps({"candidate_receipt": str(receipt)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
