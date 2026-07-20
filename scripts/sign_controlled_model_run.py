"""Issue one signed, report-only controlled model-run manifest.

This command verifies the complete pre-execution lineage and a reproducible
calibration-only threshold receipt before binding final-holdout inference. It
never trains a model and never imports GeoAI or PyTorch.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

from floodguard.controlled_experiment import (
    REQUIRED_INPUT_ROLES,
    REQUIRED_MODEL_FAMILIES,
    RUNTIME_PROFILE_FIELDS,
    ControlledExperimentError,
    assess_acquisition_manifest,
    load_ed25519_public_key,
    load_signed_calibration_reference_evidence,
    load_signed_execution_authorization_receipt,
    load_signed_reference_cell_evidence,
    load_signed_reviewer_qualification_receipt,
    load_spatial_holdout,
    write_signed_model_run_manifest,
)


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


def _add_output_signer(
    signing_keys: dict[str, bytes], key_id: str, signing_key: bytes
) -> None:
    existing = signing_keys.get(key_id)
    if existing is not None and existing != signing_key:
        raise ValueError(
            "Output signing key conflicts with the trusted key declaration."
        )
    signing_keys[key_id] = signing_key


def _timestamp(value: str, option: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{option} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{option} must include a timezone")
    return parsed.astimezone(UTC)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"runtime profile contains duplicate key: {key}")
        result[key] = value
    return result


def _load_runtime_profile(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("runtime profile must be a readable JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("runtime profile must be a JSON object")
    expected = set(RUNTIME_PROFILE_FIELDS)
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unexpected:
            details.append(f"unexpected={','.join(unexpected)}")
        raise ValueError("runtime profile keys must be exact: " + "; ".join(details))
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument("--acquisition-authority-receipt", type=Path, required=True)
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        metavar="ROLE=PATH",
        help="Private external artifact; repeat for pre, post, and reference mask.",
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
    parser.add_argument("--model-id", required=True)
    parser.add_argument(
        "--model-family", choices=REQUIRED_MODEL_FAMILIES, required=True
    )
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--model-contract", type=Path, required=True)
    parser.add_argument("--calibration-prediction", type=Path, required=True)
    parser.add_argument("--threshold-selection-receipt", type=Path, required=True)
    parser.add_argument("--prediction", type=Path, required=True)
    parser.add_argument(
        "--runtime-profile",
        type=Path,
        required=True,
        help="Strict seven-field JSON runtime/resource profile.",
    )
    parser.add_argument("--inference-started-at-utc", required=True)
    parser.add_argument("--completed-at-utc", required=True)
    parser.add_argument("--assumptions", required=True)
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
        runtime_profile = _load_runtime_profile(args.runtime_profile)
        signing_keys = _trusted_keys(args.trusted_key)
        external_public_keys = _external_public_keys(
            args.trusted_external_authority_key
        )
        signing_key = _environment_key(args.signing_key_env)
        _add_output_signer(signing_keys, args.signing_key_id, signing_key)
        checked_at = datetime.now(UTC)
        acquisition = assess_acquisition_manifest(
            args.acquisition_manifest,
            artifact_paths=_artifact_mapping(args.artifact),
            authority_receipt_path=args.acquisition_authority_receipt,
            signing_keys=signing_keys,
            external_authority_public_keys=external_public_keys,
            verified_at_utc=checked_at,
        )
        if not acquisition.ready:
            raise ControlledExperimentError(
                "Acquisition gate is blocked: " + "; ".join(acquisition.blockers)
            )
        reviewer = load_signed_reviewer_qualification_receipt(
            args.reviewer_qualification_receipt,
            acquisition=acquisition,
            signing_keys=signing_keys,
            verified_at_utc=checked_at,
        )
        holdout = load_spatial_holdout(
            args.holdout_receipt,
            args.holdout_geometry,
            args.holdout_grid_contract,
            args.holdout_membership,
            acquisition=acquisition,
            signing_keys=signing_keys,
        )
        reference = load_signed_reference_cell_evidence(
            args.reference_cell_receipt,
            args.reference_cell_evidence,
            acquisition=acquisition,
            reviewer_qualification=reviewer,
            holdout=holdout,
            calibration_reference_path=args.calibration_reference,
            error_strata_path=args.error_strata,
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
            reference_cells=reference,
            promotion_policy_path=args.promotion_policy,
            signing_keys=signing_keys,
            verified_at_utc=checked_at,
        )
        receipt = write_signed_model_run_manifest(
            model_id=args.model_id,
            model_family=args.model_family,
            model_artifact_path=args.model_artifact,
            model_contract_path=args.model_contract,
            prediction_path=args.prediction,
            acquisition=acquisition,
            reviewer_qualification=reviewer,
            holdout=holdout,
            reference_cells=reference,
            calibration_reference=calibration,
            execution_authorization=execution,
            threshold_selection_receipt_path=args.threshold_selection_receipt,
            calibration_prediction_path=args.calibration_prediction,
            runtime_profile=runtime_profile,
            inference_started_at_utc=_timestamp(
                args.inference_started_at_utc, "--inference-started-at-utc"
            ),
            completed_at_utc=_timestamp(args.completed_at_utc, "--completed-at-utc"),
            assumptions=args.assumptions,
            signing_keys=signing_keys,
            signing_key_id=args.signing_key_id,
            signing_key=signing_key,
            output_path=args.output,
        )
    except (ControlledExperimentError, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        print("delivery_scope=report_only")
        print("operational_status=non_operational")
        print("can_feed_decision_layer=false")
        print("official_warning=false")
        return 2
    print(f"manifest={Path(args.output).name}")
    print(f"manifest_sha256={receipt['manifest_sha256']}")
    print("delivery_scope=report_only")
    print("operational_status=non_operational")
    print("can_feed_decision_layer=false")
    print("official_warning=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
