"""Explain frozen v1 optical-method disagreement without changing the reference."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from floodguard.automated_optical_diagnostics import build_diagnostics


def main() -> None:
    """Verify the v1 inputs and write small exploratory diagnostic artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-data-root", type=Path, default=Path.home() / "Documents" / "FloodGuard_external_data")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--result", type=Path, default=REPO_ROOT / "outputs" / "automated_optical_v1_diagnostics.json")
    parser.add_argument("--quicklook", type=Path, default=REPO_ROOT / "outputs" / "automated_optical_v1_disagreement.png")
    parser.add_argument("--chips", type=Path, default=REPO_ROOT / "outputs" / "automated_optical_v1_chips.png")
    args = parser.parse_args()
    result = build_diagnostics(
        repo_root=REPO_ROOT,
        external_data_root=args.external_data_root,
        output_dir=args.output_dir or args.external_data_root / "proposal_execution" / "automated_track",
        result_path=args.result,
        quicklook_path=args.quicklook,
        chips_path=args.chips,
    )
    print(f"Diagnostic: {args.result}")
    print(f"Quicklook: {args.quicklook}")
    print(f"Chips: {args.chips}")
    print(f"Comparable pair counts: {result['pair_counts']}")


if __name__ == "__main__":
    main()
