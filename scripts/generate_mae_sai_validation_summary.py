"""Generate the Mae Sai real-data validation status report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.validation import write_real_data_validation_summary  # noqa: E402


def main() -> None:
    """Write the blocked or metric-backed Mae Sai validation summary."""

    parser = argparse.ArgumentParser(
        description="Generate Mae Sai real-data validation status from a file manifest."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_real_data_file_manifest.csv",
        help="Mae Sai file-level manifest CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_validation_summary.md",
        help="Output Markdown validation summary.",
    )
    parser.add_argument(
        "--weak-metrics",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_baseline_metrics.csv",
        help="Optional weak-reference candidate metric CSV.",
    )
    parser.add_argument(
        "--weak-feature-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_sar_feature_manifest.csv",
        help="Optional weak-reference SAR feature manifest CSV.",
    )
    parser.add_argument(
        "--manual-reference-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "manual_reference_mask_manifest.csv",
        help="Optional manual weak-reference manifest CSV.",
    )
    parser.add_argument(
        "--context-quality-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_context_quality_summary.csv",
        help="Optional real-context quality manifest with ADM3 overlap status.",
    )
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest, dtype=str).fillna("")
    weak_metrics = _read_optional_csv(args.weak_metrics)
    weak_feature_manifest = _read_optional_csv(args.weak_feature_manifest)
    manual_reference_manifest = _read_optional_csv(args.manual_reference_manifest)
    context_quality_manifest = _read_optional_csv(args.context_quality_manifest)
    written = write_real_data_validation_summary(
        manifest,
        args.output,
        weak_reference_metrics=weak_metrics,
        weak_reference_feature_manifest=weak_feature_manifest,
        manual_reference_manifest=manual_reference_manifest,
        context_quality_manifest=context_quality_manifest,
    )
    print(f"Wrote {written}")


def _read_optional_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=str).fillna("")


if __name__ == "__main__":
    main()
