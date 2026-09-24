"""Diagnose Mae Sai optical v2 development outputs without touching the holdout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from floodguard.automated_optical_v2_diagnostics import build_v2_development_diagnostics


def main() -> None:
    """Write a separate, exploratory Mae Sai development diagnostic."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-data-root", type=Path, default=Path.home() / "Documents" / "FloodGuard_external_data")
    parser.add_argument("--result", type=Path, default=REPO_ROOT / "outputs" / "automated_optical_v2_development_diagnostics.json")
    parser.add_argument("--quicklook", type=Path, default=REPO_ROOT / "outputs" / "automated_optical_v2_development_disagreement.png")
    parser.add_argument("--chips", type=Path, default=REPO_ROOT / "outputs" / "automated_optical_v2_development_chips.png")
    args = parser.parse_args()
    result = build_v2_development_diagnostics(
        repo_root=REPO_ROOT, external_data_root=args.external_data_root,
        result_path=args.result, quicklook_path=args.quicklook, chips_path=args.chips,
    )
    print(f"Development diagnostic: {args.result}")
    print(f"Pair counts: {result['pair_counts']}")


if __name__ == "__main__":
    main()
