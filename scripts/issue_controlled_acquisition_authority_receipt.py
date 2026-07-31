"""Bind a completed externally signed acquisition decision into FloodGuard.

The detached Ed25519 signature and trusted public key establish external data
authority. The separate HMAC key creates only an internal immutable receipt; it
cannot grant licensing or scientific qualification by itself.
"""

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
    write_acquisition_authority_receipt,
)


def _mapping(values: list[str], label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        role, separator, raw_path = value.partition("=")
        role = role.strip()
        raw_path = raw_path.strip()
        if not separator or role not in REQUIRED_INPUT_ROLES or not raw_path:
            expected = ", ".join(REQUIRED_INPUT_ROLES)
            raise ValueError(f"{label} entries must use one of {expected} as ROLE=PATH")
        if role in result:
            raise ValueError(f"duplicate {label} role: {role}")
        result[role] = Path(raw_path)
    if set(result) != set(REQUIRED_INPUT_ROLES):
        missing = sorted(set(REQUIRED_INPUT_ROLES) - set(result))
        raise ValueError(f"{label} is missing required roles: {', '.join(missing)}")
    return result


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
        raise ValueError(
            "At least one trusted external authority public key is required."
        )
    return keys


def _environment_key(variable: str) -> bytes:
    value = os.environ.get(variable)
    if value is None:
        raise ValueError(
            f"Required receipt-integrity environment variable is missing: {variable}"
        )
    return value.encode("utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        metavar="ROLE=PATH",
        help="Exact pre-event, post-event, or reference-mask artifact; repeat three times.",
    )
    parser.add_argument(
        "--catalog-evidence",
        action="append",
        required=True,
        metavar="ROLE=PATH",
        help="Exact catalog evidence bytes bound by the external decision.",
    )
    parser.add_argument(
        "--license-evidence",
        action="append",
        required=True,
        metavar="ROLE=PATH",
        help="Exact licence evidence bytes bound by the external decision.",
    )
    parser.add_argument("--external-authority-decision", type=Path, required=True)
    parser.add_argument("--external-authority-signature", type=Path, required=True)
    parser.add_argument(
        "--trusted-external-authority-key",
        action="append",
        required=True,
        metavar="KEY_ID=PATH",
        help="Trusted raw, hexadecimal, or base64 Ed25519 public key file.",
    )
    parser.add_argument("--receipt-signing-key-id", required=True)
    parser.add_argument("--receipt-signing-key-env", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        artifacts = _mapping(args.artifact, "artifact")
        catalog = _mapping(args.catalog_evidence, "catalog evidence")
        licences = _mapping(args.license_evidence, "licence evidence")
        external_keys = _external_public_keys(args.trusted_external_authority_key)
        receipt_key = _environment_key(args.receipt_signing_key_env)
        acquisition = assess_acquisition_manifest(
            args.manifest,
            artifact_paths=artifacts,
        )
        receipt = write_acquisition_authority_receipt(
            acquisition,
            args.manifest,
            external_authority_decision_path=args.external_authority_decision,
            external_authority_signature_path=args.external_authority_signature,
            external_authority_public_keys=external_keys,
            catalog_evidence_paths_by_role=catalog,
            license_evidence_paths_by_role=licences,
            verified_at_utc=datetime.now(UTC),
            receipt_signing_key_id=args.receipt_signing_key_id,
            receipt_signing_key=receipt_key,
            output_path=args.output,
        )
    except (ControlledExperimentError, OSError, UnicodeError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        print("processing_authorized=false")
        print("can_feed_decision_layer=false")
        print("official_warning=false")
        return 2
    # Do not echo an operator's private external-workspace path into logs or
    # evidence bundles.  The immutable receipt carries only basenames too.
    print(f"receipt={args.output.name}")
    print(f"manifest_sha256={receipt['manifest_sha256']}")
    print(
        "external_authority_decision_sha256="
        f"{receipt['external_authority_decision_sha256']}"
    )
    print(
        "external_authority_signing_key_id="
        f"{receipt['external_authority_signing_key_id']}"
    )
    print("internal_hmac_scope=receipt_integrity_only")
    print("processing_authorized=true")
    print("can_feed_decision_layer=false")
    print("official_warning=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
