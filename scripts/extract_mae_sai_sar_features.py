"""Extract Mae Sai weak-reference Sentinel-1 feature metadata.

This script reads external Sentinel-1 rasters and the external manual
GeoPackage, but writes only a compact derived feature manifest into the repo.
No source raster, SAFE, ZIP, or GeoPackage assets are copied or committed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.sar_raster_extract import (  # noqa: E402
    SARRasterExtractError,
    build_sar_feature_manifest,
    build_sentinel1_inputs_from_manifests,
    extract_sar_change_features,
)


def main() -> None:
    """Run the feature-extraction metadata workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_real_data_file_manifest.csv",
    )
    parser.add_argument(
        "--manual-reference-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "manual_reference_mask_manifest.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_sar_feature_manifest.csv",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=256,
        help="Output sample width/height in pixels.",
    )
    args = parser.parse_args()

    file_manifest = pd.read_csv(args.file_manifest, dtype=str).fillna("")
    manual_manifest = pd.read_csv(args.manual_reference_manifest, dtype=str).fillna("")
    try:
        inputs = build_sentinel1_inputs_from_manifests(file_manifest, manual_manifest)
        features = extract_sar_change_features(
            inputs,
            output_shape=(args.sample_size, args.sample_size),
        )
        manifest = build_sar_feature_manifest(
            features,
            file_manifest=file_manifest,
            manual_reference_manifest=manual_manifest,
            verified_inputs=inputs,
        )
    except SARRasterExtractError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(args.output, index=False, lineterminator="\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
