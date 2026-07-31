"""Run pinned SNAP RTC processing and extract exact label-factory SAR rasters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.sentinel1_processing import (  # noqa: E402
    Sentinel1ProcessingError,
    TargetRasterGrid,
    extract_canonical_rtc_layers,
    run_snap_rtc_graph,
    write_processing_run_manifest,
)


def main(argv: list[str] | None = None) -> int:
    """Run one acquisition through SNAP and canonical raster extraction."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpt", required=True, type=Path)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--source-product", required=True, type=Path)
    parser.add_argument("--source-product-id", required=True)
    parser.add_argument("--external-dem", required=True, type=Path)
    parser.add_argument(
        "--snap-auxdata-directory",
        type=Path,
        default=Path.home() / ".snap" / "auxdata",
    )
    parser.add_argument("--subset-wkt", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--acquisition-prefix", required=True)
    parser.add_argument("--target-crs", default="EPSG:32647")
    parser.add_argument("--left", required=True, type=float)
    parser.add_argument("--bottom", required=True, type=float)
    parser.add_argument("--right", required=True, type=float)
    parser.add_argument("--top", required=True, type=float)
    parser.add_argument("--resolution-m", default=10.0, type=float)
    parser.add_argument("--grid-contract-sha256", required=True)
    args = parser.parse_args(argv)

    acquisition_prefix = args.acquisition_prefix.strip().lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", acquisition_prefix) is None:
        parser.error("--acquisition-prefix must be a canonical identifier.")
    source_product_id = args.source_product_id.strip()
    if not source_product_id:
        parser.error("--source-product-id must not be blank.")
    try:
        grid = TargetRasterGrid(
            crs=args.target_crs,
            left=args.left,
            bottom=args.bottom,
            right=args.right,
            top=args.top,
            resolution_m=args.resolution_m,
            grid_contract_sha256=args.grid_contract_sha256,
        )
    except Sentinel1ProcessingError as exc:
        parser.error(str(exc))

    output_directory = args.output_directory
    output_directory.mkdir(parents=True, exist_ok=True)
    dim_path = output_directory / f"{acquisition_prefix}_rtc_linear.dim"
    try:
        snap = run_snap_rtc_graph(
            gpt_path=args.gpt,
            graph_path=args.graph,
            source_product=args.source_product,
            external_dem=args.external_dem,
            subset_wkt=args.subset_wkt,
            output_dim=dim_path,
            snap_auxdata_directory=args.snap_auxdata_directory,
        )
        layers = extract_canonical_rtc_layers(
            snap_dim=dim_path,
            output_directory=output_directory,
            acquisition_prefix=acquisition_prefix,
            grid=grid,
            source_product_id=source_product_id,
        )
        manifest_path = write_processing_run_manifest(
            {
                "artifact_schema": "floodguard.sentinel1_processing_run.v1",
                "snap_execution": snap,
                "canonical_layers": layers,
            },
            output_directory / f"{acquisition_prefix}_processing_run.json",
        )
    except Sentinel1ProcessingError as exc:
        parser.error(str(exc))
    print(json.dumps({"manifest": str(manifest_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
