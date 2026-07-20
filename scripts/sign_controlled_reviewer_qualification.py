"""Dual-sign reviewer calibration and adjudication qualification evidence."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path

from floodguard.controlled_experiment import (
    REQUIRED_INPUT_ROLES,
    ControlledExperimentError,
    assess_acquisition_manifest,
    load_ed25519_public_key,
    write_signed_reviewer_qualification_receipt,
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


def _reviewer_cell_mapping(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        reviewer_id, separator, raw_path = value.partition("=")
        reviewer_id = reviewer_id.strip()
        raw_path = raw_path.strip()
        if not separator or not reviewer_id or not raw_path:
            raise ValueError("--reviewer-cell entries must use REVIEWER_ID=PATH")
        if reviewer_id in result:
            raise ValueError(f"duplicate reviewer-cell identity: {reviewer_id}")
        result[reviewer_id] = Path(raw_path)
    if len(result) < 2:
        raise ValueError("At least two reviewer-cell artifacts are required.")
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
        raise ValueError("At least one acquisition authority key is required.")
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
    parser.add_argument("--calibration-release-package", type=Path, required=True)
    parser.add_argument("--reviewer-calibration-receipt", type=Path, required=True)
    parser.add_argument(
        "--reviewer-cell",
        action="append",
        required=True,
        metavar="REVIEWER_ID=PATH",
    )
    parser.add_argument(
        "--calibration-attempt", choices=("initial", "fresh_retest"), required=True
    )
    parser.add_argument("--adjudication-evidence", type=Path, required=True)
    parser.add_argument("--error-strata", type=Path, required=True)
    parser.add_argument("--qualified-at-utc", required=True)
    parser.add_argument("--expires-at-utc", required=True)
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
    parser.add_argument("--reviewer-signing-key-id", required=True)
    parser.add_argument("--reviewer-signing-key-env", required=True)
    parser.add_argument("--adjudicator-signing-key-id", required=True)
    parser.add_argument("--adjudicator-signing-key-env", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        signing_keys = _trusted_keys(args.trusted_key)
        external_public_keys = _external_public_keys(
            args.trusted_external_authority_key
        )
        reviewer_key = _environment_key(args.reviewer_signing_key_env)
        adjudicator_key = _environment_key(args.adjudicator_signing_key_env)
        if args.reviewer_signing_key_id == args.adjudicator_signing_key_id:
            raise ValueError("Reviewer and adjudicator signing key IDs must differ.")
        if reviewer_key == adjudicator_key:
            raise ValueError(
                "Reviewer and adjudicator signing credentials must differ."
            )
        if (
            args.reviewer_signing_key_id in signing_keys
            or args.adjudicator_signing_key_id in signing_keys
            or reviewer_key in signing_keys.values()
            or adjudicator_key in signing_keys.values()
        ):
            raise ValueError(
                "Reviewer and adjudicator signing identities and credentials must "
                "differ from acquisition authority."
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
        receipt = write_signed_reviewer_qualification_receipt(
            acquisition=acquisition,
            calibration_release_package_path=args.calibration_release_package,
            reviewer_calibration_receipt_path=args.reviewer_calibration_receipt,
            reviewer_cell_paths_by_reviewer=_reviewer_cell_mapping(args.reviewer_cell),
            calibration_attempt=args.calibration_attempt,
            adjudication_evidence_path=args.adjudication_evidence,
            error_strata_path=args.error_strata,
            qualified_at_utc=_timestamp(args.qualified_at_utc, "--qualified-at-utc"),
            expires_at_utc=_timestamp(args.expires_at_utc, "--expires-at-utc"),
            reviewer_signing_key_id=args.reviewer_signing_key_id,
            reviewer_signing_key=reviewer_key,
            adjudicator_signing_key_id=args.adjudicator_signing_key_id,
            adjudicator_signing_key=adjudicator_key,
            output_path=args.output,
        )
    except (ControlledExperimentError, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(f"receipt={Path(args.output).name}")
    print(f"manifest_sha256={receipt['manifest_sha256']}")
    print("processing_allowed=true")
    print("can_feed_decision_layer=false")
    print("official_warning=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
