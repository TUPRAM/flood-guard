"""Rasterise a legacy polygon as a positive-unlabeled label-factory seed."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.rasterization import (  # noqa: E402
    RasterizationError,
    load_geojson_polygons,
    rasterize_positive_unlabeled_seed,
    write_weak_seed_outputs,
)
from floodguard.label_factory.tiling import Bounds  # noqa: E402


def main() -> None:
    """Build a weak seed while preserving exterior-as-unreviewed semantics."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-geojson", type=Path, required=True)
    parser.add_argument("--query-manifest", type=Path, required=True)
    parser.add_argument("--query-region-id", required=True)
    parser.add_argument("--seed-id", required=True)
    parser.add_argument("--boundary-buffer-cells", type=int, default=0)
    parser.add_argument("--source-timestamp", required=True)
    parser.add_argument("--assumptions", required=True)
    parser.add_argument("--raster-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        query_bytes = args.query_manifest.read_bytes()
        queries = pd.read_csv(args.query_manifest).fillna("")
        matches = queries[
            queries["query_region_id"].astype(str).eq(args.query_region_id)
        ]
        if len(matches) != 1:
            raise RasterizationError(
                "--query-region-id must match exactly one canonical query row."
            )
        query = matches.iloc[0]
        polygons = load_geojson_polygons(args.source_geojson)
        raster = rasterize_positive_unlabeled_seed(
            polygons,
            bounds=Bounds(
                float(query["bbox_min_x"]),
                float(query["bbox_min_y"]),
                float(query["bbox_max_x"]),
                float(query["bbox_max_y"]),
            ),
            width_cells=int(query["query_size_pixels"]),
            height_cells=int(query["query_size_pixels"]),
            crs=str(query["crs"]),
            boundary_buffer_cells=args.boundary_buffer_cells,
        )
        written = write_weak_seed_outputs(
            args.source_geojson,
            raster,
            raster_output_path=args.raster_output,
            manifest_output_path=args.manifest_output,
            seed_id=args.seed_id,
            event_id=str(query["event_id"]),
            grid_id=str(query["grid_id"]),
            query_region_id=str(query["query_region_id"]),
            tile_id=str(query["tile_id"]),
            grid_contract_sha256=str(query["grid_contract_sha256"]),
            query_manifest_sha256=hashlib.sha256(query_bytes).hexdigest(),
            source_timestamp=args.source_timestamp,
            assumptions=args.assumptions,
        )
    except RasterizationError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for label, path in written.items():
        print(f"Wrote {label}: {path}")


if __name__ == "__main__":
    main()
