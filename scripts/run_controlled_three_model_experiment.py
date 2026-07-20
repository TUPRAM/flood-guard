"""Run the three-model comparison only after every immutable gate passes."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path

from floodguard.controlled_experiment import (
    ControlledExperimentError,
    load_ed25519_public_key,
    run_controlled_three_model_experiment,
)


def _mapping(values: list[str], label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        key, separator, raw_path = value.partition("=")
        key = key.strip()
        raw_path = raw_path.strip()
        if not separator or not key or not raw_path:
            raise ValueError(f"{label} entries must use MODEL_FAMILY=PATH")
        if key in result:
            raise ValueError(f"duplicate {label} key: {key}")
        result[key] = Path(raw_path)
    return result


def _environment_key(variable: str) -> bytes:
    value = os.environ.get(variable)
    if value is None:
        raise ValueError(
            f"Required signing-key environment variable is missing: {variable}"
        )
    return value.encode("utf-8")


def _trusted_keys(values: list[str]) -> dict[str, bytes]:
    keys: dict[str, bytes] = {}
    for value in values:
        key_id, separator, variable = value.partition("=")
        if not separator or not key_id.strip() or not variable.strip():
            raise ValueError(
                "--trusted-key entries must use KEY_ID=ENVIRONMENT_VARIABLE"
            )
        key_id = key_id.strip()
        variable = variable.strip()
        if key_id in keys:
            raise ValueError(f"duplicate trusted signing key ID: {key_id}")
        keys[key_id] = _environment_key(variable)
    if not keys:
        raise ValueError("At least one trusted upstream signing key is required.")
    return keys


def _external_public_keys(values: list[str]) -> dict[str, bytes]:
    keys: dict[str, bytes] = {}
    for value in values:
        key_id, separator, raw_path = value.partition("=")
        key_id = key_id.strip()
        raw_path = raw_path.strip()
        if not separator or not key_id or not raw_path or key_id in keys:
            raise ValueError(
                "--trusted-external-authority-key entries must use unique KEY_ID=PATH"
            )
        keys[key_id] = load_ed25519_public_key(Path(raw_path))
    if not keys:
        raise ValueError("A trusted external authority public key is required.")
    return keys


def _utc_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument("--acquisition-authority-receipt", type=Path, required=True)
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        help="Private external artifact as role=path; repeat for pre, post, and mask.",
    )
    parser.add_argument("--reviewer-qualification-receipt", type=Path, required=True)
    parser.add_argument("--holdout-receipt", type=Path, required=True)
    parser.add_argument("--holdout-geometry", type=Path, required=True)
    parser.add_argument("--holdout-grid-contract", type=Path, required=True)
    parser.add_argument("--holdout-membership", type=Path, required=True)
    parser.add_argument("--reference-cell-receipt", type=Path, required=True)
    parser.add_argument("--reference-cell-evidence", type=Path, required=True)
    parser.add_argument("--calibration-reference", type=Path, required=True)
    parser.add_argument("--error-strata", type=Path, required=True)
    parser.add_argument("--promotion-policy", type=Path, required=True)
    parser.add_argument("--execution-authorization-receipt", type=Path, required=True)
    parser.add_argument("--model-evidence-manifest", type=Path, required=True)
    parser.add_argument(
        "--prediction",
        action="append",
        required=True,
        help="Final-holdout prediction CSV as model_family=path; repeat three times.",
    )
    parser.add_argument(
        "--calibration-prediction",
        action="append",
        required=True,
        help="Calibration-only prediction CSV as model_family=path; repeat three times.",
    )
    parser.add_argument(
        "--threshold-selection-receipt",
        action="append",
        required=True,
        help="Signed threshold receipt as model_family=path; repeat three times.",
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
        "--trusted-key",
        action="append",
        required=True,
        metavar="KEY_ID=ENVIRONMENT_VARIABLE",
    )
    parser.add_argument(
        "--trusted-external-authority-key",
        action="append",
        required=True,
        metavar="KEY_ID=PATH",
    )
    parser.add_argument("--result-signing-key-id", required=True)
    parser.add_argument("--result-signing-key-env", required=True)
    parser.add_argument(
        "--result-expires-at-utc",
        type=_utc_timestamp,
        required=True,
        help="Expiry for the signed report-only comparison receipt.",
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        signing_keys = _trusted_keys(args.trusted_key)
        external_public_keys = _external_public_keys(
            args.trusted_external_authority_key
        )
        result_key = _environment_key(args.result_signing_key_env)
        existing = signing_keys.get(args.result_signing_key_id)
        if existing is not None and existing != result_key:
            raise ValueError(
                "Result signing key conflicts with the trusted key declaration."
            )
        signing_keys[args.result_signing_key_id] = result_key
        outputs = run_controlled_three_model_experiment(
            acquisition_manifest_path=args.acquisition_manifest,
            acquisition_artifact_paths=_mapping(args.artifact, "artifact"),
            acquisition_authority_receipt_path=args.acquisition_authority_receipt,
            reviewer_qualification_receipt_path=(args.reviewer_qualification_receipt),
            holdout_receipt_path=args.holdout_receipt,
            holdout_geometry_path=args.holdout_geometry,
            holdout_grid_contract_path=args.holdout_grid_contract,
            holdout_membership_path=args.holdout_membership,
            reference_cell_receipt_path=args.reference_cell_receipt,
            reference_cell_evidence_path=args.reference_cell_evidence,
            calibration_reference_path=args.calibration_reference,
            error_strata_path=args.error_strata,
            promotion_policy_path=args.promotion_policy,
            execution_authorization_receipt_path=(args.execution_authorization_receipt),
            model_evidence_manifest_path=args.model_evidence_manifest,
            prediction_paths=_mapping(args.prediction, "prediction"),
            calibration_prediction_paths=_mapping(
                args.calibration_prediction, "calibration-prediction"
            ),
            threshold_selection_receipt_paths=_mapping(
                args.threshold_selection_receipt,
                "threshold-selection-receipt",
            ),
            model_artifact_paths=_mapping(args.model_artifact, "model-artifact"),
            model_contract_paths=_mapping(args.model_contract, "model-contract"),
            model_run_manifest_paths=_mapping(
                args.model_run_manifest, "model-run-manifest"
            ),
            signing_keys=signing_keys,
            external_authority_public_keys=external_public_keys,
            result_signing_key_id=args.result_signing_key_id,
            output_directory=args.output_directory,
            result_expires_at_utc=args.result_expires_at_utc,
        )
    except (ControlledExperimentError, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        print("comparison_status=not_executed")
        print("can_feed_decision_layer=false")
        print("official_warning=false")
        return 2
    for name, path in outputs.items():
        print(f"{name}={path.name}")
    print("comparison_status=completed_report_only")
    print("can_feed_decision_layer=false")
    print("official_warning=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
