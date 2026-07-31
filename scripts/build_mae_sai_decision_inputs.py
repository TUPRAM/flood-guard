"""Build Mae Sai weak-reference decision inputs and priority GeoJSON.

This script consumes derived weak-reference CSV outputs only. It does not read
or copy source Sentinel-1 ZIPs, SAFE packages, TIFFs, or manual GeoPackages.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.exports import write_priority_geojson  # noqa: E402
from floodguard.flood_aggregation import (  # noqa: E402
    FloodAggregationError,
    build_mae_sai_review_area_admin_geojson,
    build_mae_sai_weak_decision_inputs,
)
from floodguard.scoring import score_subdistricts  # noqa: E402


def main() -> None:
    """Write weak-reference decision input CSV and priority GeoJSON."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--real-context-inputs",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_real_context_decision_inputs.csv",
        help="Preferred ADM3 real-context FPPS input CSV when available.",
    )
    parser.add_argument(
        "--real-admin-geojson",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_admin_context.geojson",
        help="Preferred COD-AB ADM3 GeoJSON when real-context inputs are available.",
    )
    parser.add_argument(
        "--weak-feature-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_sar_feature_manifest.csv",
        help="Weak-reference SAR feature manifest CSV.",
    )
    parser.add_argument(
        "--manual-reference-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "manual_reference_mask_manifest.csv",
        help="Manual reference mask manifest CSV.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_subdistrict_flood_inputs.csv",
        help="Output FPPS input CSV.",
    )
    parser.add_argument(
        "--output-geojson",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_priority_subdistricts.geojson",
        help="Output dashboard-ready priority GeoJSON.",
    )
    args = parser.parse_args()

    try:
        if args.real_context_inputs.exists() and args.real_admin_geojson.exists():
            decision_inputs = pd.read_csv(
                args.real_context_inputs, dtype=str
            ).fillna("")
            priority = score_subdistricts(decision_inputs)
            admin_geojson = json.loads(
                args.real_admin_geojson.read_text(encoding="utf-8")
            )
        else:
            weak_feature_manifest = pd.read_csv(
                args.weak_feature_manifest, dtype=str
            ).fillna("")
            manual_reference_manifest = pd.read_csv(
                args.manual_reference_manifest,
                dtype=str,
            ).fillna("")
            decision_inputs = build_mae_sai_weak_decision_inputs(
                weak_feature_manifest,
                manual_reference_manifest,
            )
            priority = score_subdistricts(decision_inputs)
            admin_geojson = build_mae_sai_review_area_admin_geojson(
                manual_reference_manifest,
            )
    except (FloodAggregationError, ValueError, json.JSONDecodeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    decision_inputs.to_csv(args.output_csv, index=False, lineterminator="\n")

    with tempfile.TemporaryDirectory(prefix="floodguard_mae_sai_admin_") as tmpdir:
        admin_path = Path(tmpdir) / "mae_sai_review_area_admin.geojson"
        admin_path.write_text(json.dumps(admin_geojson), encoding="utf-8")
        write_priority_geojson(admin_path, priority, args.output_geojson)

    print(f"Wrote {args.output_csv}")
    print(f"Wrote {args.output_geojson}")


if __name__ == "__main__":
    main()
