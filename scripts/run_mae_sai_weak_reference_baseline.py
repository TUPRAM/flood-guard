"""Run Mae Sai weak-reference real Sentinel-1 non-ML baseline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.weak_reference_baseline import (  # noqa: E402
    WeakReferenceBaselineError,
    write_weak_reference_baseline_outputs,
)


def main() -> None:
    """Run the weak-reference baseline and write derived outputs only."""

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
        "--feature-manifest-output",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_sar_feature_manifest.csv",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_baseline_metrics.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_baseline_summary.md",
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
        written = write_weak_reference_baseline_outputs(
            file_manifest,
            manual_manifest,
            metrics_output_path=args.metrics_output,
            feature_manifest_output_path=args.feature_manifest_output,
            summary_output_path=args.summary_output,
            output_shape=(args.sample_size, args.sample_size),
        )
    except WeakReferenceBaselineError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for label, path in written.items():
        print(f"Wrote {label}: {path}")


if __name__ == "__main__":
    main()
