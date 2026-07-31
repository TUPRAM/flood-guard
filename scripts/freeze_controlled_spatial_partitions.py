"""Freeze signed train, calibration, and final-holdout spatial partitions."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path

from floodguard.controlled_experiment import (
    REQUIRED_INPUT_ROLES,
    ControlledExperimentError,
    assess_acquisition_manifest,
    freeze_spatial_holdout,
    load_ed25519_public_key,
)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--frozen-at-utc must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--frozen-at-utc must include a timezone")
    return parsed.astimezone(UTC)


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"required input is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        if key_id in keys:
            raise ValueError(f"duplicate trusted signing key ID: {key_id}")
        keys[key_id] = _environment_key(variable.strip())
    if not keys:
        raise ValueError("At least one acquisition authority key is required.")
    return keys


def _external_public_keys(values: list[str]) -> dict[str, bytes]:
    keys: dict[str, bytes] = {}
    for value in values:
        key_id, separator, raw_path = value.partition("=")
        key_id = key_id.strip()
        raw_path = raw_path.strip()
        if not separator or not key_id or not raw_path:
            raise ValueError(
                "--trusted-external-authority-key entries must use KEY_ID=PATH"
            )
        if key_id in keys:
            raise ValueError(f"duplicate external authority key ID: {key_id}")
        keys[key_id] = load_ed25519_public_key(Path(raw_path))
    if not keys:
        raise ValueError("At least one external authority public key is required.")
    return keys


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument("--acquisition-authority-receipt", type=Path, required=True)
    parser.add_argument(
        "--artifact", action="append", required=True, metavar="ROLE=PATH"
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
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--grid-contract", type=Path, required=True)
    parser.add_argument("--cell-grid", type=Path, required=True)
    parser.add_argument("--membership-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--target-crs", required=True)
    parser.add_argument("--frozen-at-utc", required=True)
    parser.add_argument("--assumptions", required=True)
    parser.add_argument("--signing-key-id", required=True)
    parser.add_argument("--signing-key-env", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        frozen_at = _timestamp(args.frozen_at_utc)
        signing_keys = _trusted_keys(args.trusted_key)
        external_public_keys = _external_public_keys(
            args.trusted_external_authority_key
        )
        signing_key = _environment_key(args.signing_key_env)
        if args.signing_key_id in signing_keys or signing_key in signing_keys.values():
            raise ValueError(
                "Holdout authority must use a signing identity and credential "
                "distinct from acquisition authority."
            )
        acquisition = assess_acquisition_manifest(
            args.acquisition_manifest,
            artifact_paths=_artifact_mapping(args.artifact),
            authority_receipt_path=args.acquisition_authority_receipt,
            signing_keys=signing_keys,
            external_authority_public_keys=external_public_keys,
            verified_at_utc=frozen_at,
        )
        if not acquisition.ready:
            raise ControlledExperimentError(
                "Acquisition gate is blocked: " + "; ".join(acquisition.blockers)
            )
        frozen = freeze_spatial_holdout(
            args.geometry,
            acquisition=acquisition,
            grid_contract_path=args.grid_contract,
            cell_grid_path=args.cell_grid,
            membership_output_path=args.membership_output,
            target_crs=args.target_crs,
            grid_contract_sha256=_sha256(args.grid_contract),
            frozen_at_utc=frozen_at,
            assumptions=args.assumptions,
            signing_key_id=args.signing_key_id,
            signing_key=signing_key,
            output_path=args.receipt_output,
        )
    except (ControlledExperimentError, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(f"receipt={Path(args.receipt_output).name}")
    print(f"membership={Path(args.membership_output).name}")
    print(f"manifest_sha256={frozen.manifest_sha256}")
    print(f"membership_sha256={frozen.membership_sha256}")
    print("can_feed_decision_layer=false")
    print("official_warning=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
