"""Run the three-model comparison only after every immutable gate passes."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path

from floodguard.controlled_experiment import run_controlled_three_model_experiment


def _mapping(values: list[str], label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        key, separator, raw_path = value.partition("=")
        if not separator or not key.strip() or not raw_path.strip():
            raise ValueError(f"{label} entries must use role=path")
        if key in result:
            raise ValueError(f"duplicate {label} key: {key}")
        result[key] = Path(raw_path)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument(
        "--acquisition-authority-receipt",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        help="Private external artifact as role=path; repeat for pre, post, and mask.",
    )
    parser.add_argument("--reviewer-calibration-receipt", type=Path, required=True)
    parser.add_argument("--holdout-receipt", type=Path, required=True)
    parser.add_argument("--holdout-geometry", type=Path, required=True)
    parser.add_argument("--holdout-grid-contract", type=Path, required=True)
    parser.add_argument("--holdout-membership", type=Path, required=True)
    parser.add_argument("--reference-cell-receipt", type=Path, required=True)
    parser.add_argument("--reference-cell-evidence", type=Path, required=True)
    parser.add_argument("--model-evidence-manifest", type=Path, required=True)
    parser.add_argument(
        "--prediction",
        action="append",
        required=True,
        help="Prediction CSV as model_family=path; repeat for all three families.",
    )
    parser.add_argument(
        "--model-artifact",
        action="append",
        required=True,
        help="Immutable model artifact as model_family=path; repeat three times.",
    )
    parser.add_argument(
        "--model-contract",
        action="append",
        required=True,
        help="Immutable lane contract as model_family=path; repeat three times.",
    )
    parser.add_argument(
        "--model-run-manifest",
        action="append",
        required=True,
        help="Signed model run manifest as model_family=path; repeat three times.",
    )
    parser.add_argument(
        "--signing-key-id",
        default=os.environ.get(
            "FLOODGUARD_EXPERIMENT_SIGNING_KEY_ID",
            "experiment-authority-v1",
        ),
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    signing_key = os.environ.get("FLOODGUARD_EXPERIMENT_SIGNING_KEY")
    if signing_key is None:
        raise ValueError(
            "FLOODGUARD_EXPERIMENT_SIGNING_KEY is required and must remain external."
        )
    outputs = run_controlled_three_model_experiment(
        acquisition_manifest_path=args.acquisition_manifest,
        acquisition_artifact_paths=_mapping(args.artifact, "artifact"),
        acquisition_authority_receipt_path=args.acquisition_authority_receipt,
        reviewer_calibration_receipt_path=args.reviewer_calibration_receipt,
        holdout_receipt_path=args.holdout_receipt,
        holdout_geometry_path=args.holdout_geometry,
        holdout_grid_contract_path=args.holdout_grid_contract,
        holdout_membership_path=args.holdout_membership,
        reference_cell_receipt_path=args.reference_cell_receipt,
        reference_cell_evidence_path=args.reference_cell_evidence,
        model_evidence_manifest_path=args.model_evidence_manifest,
        prediction_paths=_mapping(args.prediction, "prediction"),
        model_artifact_paths=_mapping(args.model_artifact, "model-artifact"),
        model_contract_paths=_mapping(args.model_contract, "model-contract"),
        model_run_manifest_paths=_mapping(
            args.model_run_manifest,
            "model-run-manifest",
        ),
        signing_keys={args.signing_key_id: signing_key.encode("utf-8")},
        output_directory=args.output_directory,
        generated_at_utc=datetime.now(UTC).replace(microsecond=0),
    )
    for name, path in outputs.items():
        print(f"{name}={path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
