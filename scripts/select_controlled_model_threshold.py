"""Select and sign one model threshold from calibration cells only."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path

from floodguard.controlled_experiment import (
    REQUIRED_INPUT_ROLES,
    REQUIRED_MODEL_FAMILIES,
    ControlledExperimentError,
    assess_acquisition_manifest,
    load_ed25519_public_key,
    load_signed_calibration_reference_evidence,
    load_signed_execution_authorization_receipt,
    load_signed_reviewer_qualification_receipt,
    load_spatial_holdout,
)
from floodguard.controlled_threshold import write_signed_threshold_selection_receipt


def _artifact_mapping(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        role, separator, raw_path = value.partition("=")
        role = role.strip()
        raw_path = raw_path.strip()
        if not separator or role not in REQUIRED_INPUT_ROLES or not raw_path:
            raise ValueError("--artifact entries must use a required ROLE=PATH")
        if role in result:
            raise ValueError(f"duplicate artifact role: {role}")
        result[role] = Path(raw_path)
    if set(result) != set(REQUIRED_INPUT_ROLES):
        missing = sorted(set(REQUIRED_INPUT_ROLES) - set(result))
        raise ValueError(f"artifact mapping is missing: {', '.join(missing)}")
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


def _timestamp(value: str, option: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{option} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{option} must include a timezone")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument("--acquisition-authority-receipt", type=Path, required=True)
    parser.add_argument(
        "--artifact", action="append", required=True, metavar="ROLE=PATH"
    )
    parser.add_argument("--reviewer-qualification-receipt", type=Path, required=True)
    parser.add_argument("--holdout-receipt", type=Path, required=True)
    parser.add_argument("--holdout-geometry", type=Path, required=True)
    parser.add_argument("--holdout-grid-contract", type=Path, required=True)
    parser.add_argument("--holdout-membership", type=Path, required=True)
    parser.add_argument("--reference-cell-receipt", type=Path, required=True)
    parser.add_argument("--calibration-reference", type=Path, required=True)
    parser.add_argument("--promotion-policy", type=Path, required=True)
    parser.add_argument("--execution-authorization-receipt", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument(
        "--model-family", choices=REQUIRED_MODEL_FAMILIES, required=True
    )
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--model-contract", type=Path, required=True)
    parser.add_argument("--calibration-prediction", type=Path, required=True)
    parser.add_argument("--execution-started-at-utc", required=True)
    parser.add_argument("--training-started-at-utc", required=True)
    parser.add_argument("--training-completed-at-utc", required=True)
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
    parser.add_argument("--signing-key-id", required=True)
    parser.add_argument("--signing-key-env", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        signing_keys = _trusted_keys(args.trusted_key)
        external_public_keys = _external_public_keys(
            args.trusted_external_authority_key
        )
        signing_key = _environment_key(args.signing_key_env)
        if args.signing_key_id in signing_keys or signing_key in signing_keys.values():
            raise ValueError(
                "Model executor must use a signing identity and credential distinct "
                "from every upstream role."
            )
        acquisition = assess_acquisition_manifest(
            args.acquisition_manifest,
            artifact_paths=_artifact_mapping(args.artifact),
            authority_receipt_path=args.acquisition_authority_receipt,
            signing_keys=signing_keys,
            external_authority_public_keys=external_public_keys,
            verified_at_utc=datetime.now(UTC),
        )
        if not acquisition.ready:
            raise ControlledExperimentError(
                "Acquisition gate is blocked: " + "; ".join(acquisition.blockers)
            )
        reviewer = load_signed_reviewer_qualification_receipt(
            args.reviewer_qualification_receipt,
            acquisition=acquisition,
            signing_keys=signing_keys,
            verified_at_utc=datetime.now(UTC),
        )
        holdout = load_spatial_holdout(
            args.holdout_receipt,
            args.holdout_geometry,
            args.holdout_grid_contract,
            args.holdout_membership,
            acquisition=acquisition,
            signing_keys=signing_keys,
        )
        calibration = load_signed_calibration_reference_evidence(
            args.reference_cell_receipt,
            args.calibration_reference,
            acquisition=acquisition,
            reviewer_qualification=reviewer,
            holdout=holdout,
            signing_keys=signing_keys,
        )
        execution = load_signed_execution_authorization_receipt(
            args.execution_authorization_receipt,
            acquisition=acquisition,
            reviewer_qualification=reviewer,
            holdout=holdout,
            calibration_reference=calibration,
            promotion_policy_path=args.promotion_policy,
            signing_keys=signing_keys,
            verified_at_utc=datetime.now(UTC),
        )
        receipt = write_signed_threshold_selection_receipt(
            model_id=args.model_id,
            model_family=args.model_family,
            model_artifact_path=args.model_artifact,
            model_contract_path=args.model_contract,
            calibration_prediction_path=args.calibration_prediction,
            acquisition=acquisition,
            reviewer_qualification=reviewer,
            holdout=holdout,
            calibration_reference=calibration,
            execution_authorization=execution,
            execution_started_at_utc=_timestamp(
                args.execution_started_at_utc, "--execution-started-at-utc"
            ),
            training_started_at_utc=_timestamp(
                args.training_started_at_utc, "--training-started-at-utc"
            ),
            training_completed_at_utc=_timestamp(
                args.training_completed_at_utc, "--training-completed-at-utc"
            ),
            signing_key_id=args.signing_key_id,
            signing_key=signing_key,
            output_path=args.output,
        )
    except (ControlledExperimentError, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(f"receipt={Path(args.output).name}")
    print(f"manifest_sha256={receipt['manifest_sha256']}")
    print(f"selected_threshold={receipt['selected_threshold']}")
    print("threshold_selection_scope=verified_calibration_projection_only")
    print("final_holdout_reference_opened=false")
    print("can_feed_decision_layer=false")
    print("official_warning=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
