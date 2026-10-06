"""Build the separately named automated Sentinel-2 optical reference and receipt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from floodguard.automated_reference import (
    build_automated_optical_reference,
    run_omniwatermask_model,
)


def main() -> None:
    """Run either the full optical build or its pinned research-model subprocess."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-only", nargs=2, metavar=("INPUT", "OUTPUT"))
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "outputs" / "earth_search_mae_sai_sentinel2_reference_assets.csv")
    parser.add_argument("--external-data-root", type=Path, default=Path.home() / "Documents" / "FloodGuard_external_data")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--receipt", type=Path, default=REPO_ROOT / "outputs" / "automated_optical_reference_v1.json")
    parser.add_argument("--quicklook", type=Path, default=REPO_ROOT / "outputs" / "automated_optical_reference_v1.png")
    parser.add_argument("--research-python", type=Path, default=REPO_ROOT / ".venv-research" / "Scripts" / "python.exe")
    args = parser.parse_args()
    if args.model_only:
        if args.model_dir is None or args.cache_dir is None:
            parser.error("--model-only needs --model-dir and --cache-dir")
        run_omniwatermask_model(
            Path(args.model_only[0]), Path(args.model_only[1]),
            model_dir=args.model_dir, cache_dir=args.cache_dir,
        )
        return
    output_dir = args.output_dir or args.external_data_root / "proposal_execution" / "automated_track"
    receipt = build_automated_optical_reference(
        manifest=args.manifest, external_data_root=args.external_data_root,
        output_dir=output_dir, receipt_path=args.receipt,
        quicklook_path=args.quicklook, research_python=args.research_python,
    )
    print(f"Optical reference receipt: {args.receipt}")
    print(f"AOI class counts: {receipt['class_counts']}")
    print(f"A/B agreement: {receipt['ab_agreement']}")


if __name__ == "__main__":
    main()
