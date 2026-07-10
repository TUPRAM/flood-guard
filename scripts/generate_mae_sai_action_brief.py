"""Generate the Mae Sai weak-reference bilingual action brief."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.mae_sai_brief import (  # noqa: E402
    MaeSaiActionBriefError,
    write_mae_sai_action_brief,
)
from floodguard.scoring import score_subdistricts  # noqa: E402


def main() -> None:
    """Read derived outputs and write one action brief without raw-data access."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--decision-inputs",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_subdistrict_flood_inputs.csv",
    )
    parser.add_argument(
        "--sar-feature-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_sar_feature_manifest.csv",
    )
    parser.add_argument(
        "--baseline-metrics",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_baseline_metrics.csv",
    )
    parser.add_argument(
        "--manual-reference-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "manual_reference_mask_manifest.csv",
    )
    parser.add_argument(
        "--weak-label-ml-metrics",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_label_ml_metrics.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs",
    )
    args = parser.parse_args()

    try:
        decision_inputs = _read_csv(args.decision_inputs)
        priority = score_subdistricts(decision_inputs)
        sar_feature = _read_csv(args.sar_feature_manifest)
        baseline = _read_csv(args.baseline_metrics)
        manual = _read_csv(args.manual_reference_manifest)
        ml_metrics = (
            _read_csv(args.weak_label_ml_metrics)
            if args.weak_label_ml_metrics.exists()
            else None
        )
        target = write_mae_sai_action_brief(
            priority,
            sar_feature,
            baseline,
            manual,
            args.output_dir,
            weak_label_ml_metrics=ml_metrics,
        )
    except (FileNotFoundError, MaeSaiActionBriefError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"Wrote {target}")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required derived input does not exist: {path.name}")
    return pd.read_csv(path, dtype=str).fillna("")


if __name__ == "__main__":
    main()
