"""Prepare and score the separately preregistered automated optical v2 study."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from floodguard.automated_optical_v2 import (
    prepare_episode,
    run_native_model,
    score_episode,
)


def main() -> None:
    """Run model-only, preparation or single-use scoring from frozen inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("development", "final_holdout"))
    parser.add_argument("--stage", choices=("prepare", "score"))
    parser.add_argument("--model-only", nargs=2, metavar=("INPUT", "OUTPUT"))
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--external-data-root", type=Path, default=Path.home() / "Documents" / "FloodGuard_external_data")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--research-python", type=Path, default=REPO_ROOT / ".venv-research" / "Scripts" / "python.exe")
    args = parser.parse_args()
    if args.model_only:
        if args.model_dir is None or args.cache_dir is None:
            parser.error("--model-only requires --model-dir and --cache-dir")
        run_native_model(Path(args.model_only[0]), Path(args.model_only[1]), model_dir=args.model_dir, cache_dir=args.cache_dir)
        return
    if args.role is None or args.stage is None:
        parser.error("--role and --stage are required")
    suffix = "development" if args.role == "development" else "holdout"
    manifest = args.manifest or REPO_ROOT / "outputs" / f"earth_search_automated_optical_v2_{suffix}_assets.csv"
    output_dir = args.external_data_root / "proposal_execution" / "automated_track" / "v2" / args.role
    preparation = REPO_ROOT / "outputs" / f"automated_optical_v2_{suffix}_preparation.json"
    result = REPO_ROOT / "outputs" / f"automated_optical_v2_{suffix}.json"
    quicklook = REPO_ROOT / "outputs" / f"automated_optical_v2_{suffix}.png"
    if args.stage == "prepare":
        receipt = prepare_episode(
            role=args.role, manifest=manifest, external_root=args.external_data_root,
            output_dir=output_dir, prepare_receipt=preparation, research_python=args.research_python,
        )
        print(f"Preparation: {preparation} ({receipt['receipt_sha256']})")
    else:
        receipt = score_episode(
            role=args.role, manifest=manifest, external_root=args.external_data_root,
            output_dir=output_dir, prepare_receipt=preparation,
            result_path=result, quicklook_path=quicklook,
            development_receipt=REPO_ROOT / "outputs" / "automated_optical_v2_development.json",
        )
        print(f"Cross-review: {result}")
        print(f"A/B agreement: {receipt['ab_agreement']}")
        print(f"All limits passed: {receipt['passes_all_limits']}")


if __name__ == "__main__":
    main()
