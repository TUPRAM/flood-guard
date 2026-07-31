"""Align static label-factory reviewer context to an explicit raster grid."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.context_alignment import (  # noqa: E402
    CONTEXT_ALIGNMENT_MANIFEST_NAME,
    ContextAlignmentError,
    TargetRasterGrid,
    build_context_alignment,
)


def main() -> None:
    """Parse explicit source/grid inputs and write one immutable context package."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worldcover", type=Path, required=True)
    parser.add_argument("--jrc-occurrence", type=Path, required=True)
    parser.add_argument("--jrc-seasonality", type=Path, required=True)
    parser.add_argument("--dem", type=Path, required=True)
    parser.add_argument("--target-crs", required=True)
    parser.add_argument(
        "--affine",
        type=float,
        nargs=6,
        required=True,
        metavar=("A", "B", "C", "D", "E", "F"),
        help="Six rasterio affine coefficients in a,b,c,d,e,f order.",
    )
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--permanent-occurrence-threshold-pct", type=float, default=90.0)
    parser.add_argument(
        "--permanent-seasonality-threshold-months", type=int, default=10
    )
    parser.add_argument("--hillshade-azimuth-deg", type=float, default=315.0)
    parser.add_argument("--hillshade-altitude-deg", type=float, default=45.0)
    args = parser.parse_args()

    try:
        target_grid = TargetRasterGrid(
            crs=args.target_crs,
            affine=tuple(args.affine),
            width=args.width,
            height=args.height,
        )
        manifest = build_context_alignment(
            worldcover_path=args.worldcover,
            jrc_occurrence_path=args.jrc_occurrence,
            jrc_seasonality_path=args.jrc_seasonality,
            dem_path=args.dem,
            output_directory=args.output_directory,
            target_grid=target_grid,
            permanent_occurrence_threshold_pct=(
                args.permanent_occurrence_threshold_pct
            ),
            permanent_seasonality_threshold_months=(
                args.permanent_seasonality_threshold_months
            ),
            hillshade_azimuth_deg=args.hillshade_azimuth_deg,
            hillshade_altitude_deg=args.hillshade_altitude_deg,
        )
    except (ContextAlignmentError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(
        f"Wrote {manifest['layer_count']} aligned context rasters: "
        f"{args.output_directory}"
    )
    print(
        "Wrote checksum/derivation manifest: "
        f"{args.output_directory / CONTEXT_ALIGNMENT_MANIFEST_NAME}"
    )
    print("Safety: reviewer context only; decision layer=false; FPPS=false; warning=false")


if __name__ == "__main__":
    main()
