"""Build one immutable qualified-reference compatibility release.

The default path emits a fail-closed projection of the current controlled
acquisition assessment.  A qualified release is possible only when the
existing signed acquisition gate is ready and all exact reference/grid inputs
match that authority. Qualified output also requires a distinct scientific
Reference Authority decision with a detached Ed25519 signature verified
against runtime-trusted key material. Synthetic fixtures are explicitly
isolated from real Thai-event evidence.
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
)
from floodguard.label_factory.qualified_reference_release import (
    BLOCKED_STATUS,
    PURPOSES,
    QUALIFIED_STATUS,
    REFERENCE_AUTHORITY_CLASSES,
    RELEASE_STATUSES,
    SYNTHETIC_STATUS,
    QualifiedReferenceReleaseError,
    build_qualified_reference_release,
    write_qualified_reference_release,
)


def _timestamp(value: str, option: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{option} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{option} must include a timezone")
    return parsed.astimezone(UTC)


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
        key_id = key_id.strip()
        variable = variable.strip()
        if not separator or not key_id or not variable:
            raise ValueError(
                "--trusted-key entries must use KEY_ID=ENVIRONMENT_VARIABLE"
            )
        if key_id in keys:
            raise ValueError(f"duplicate trusted signing key ID: {key_id}")
        keys[key_id] = _environment_key(variable)
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
    return keys


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-status",
        choices=sorted(RELEASE_STATUSES),
        default=BLOCKED_STATUS,
    )
    parser.add_argument("--acquisition-manifest", type=Path)
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="ROLE=PATH",
        help="Private runtime artifact; never serialized as a path.",
    )
    parser.add_argument("--acquisition-authority-receipt", type=Path)
    parser.add_argument("--reference-authority-decision", type=Path)
    parser.add_argument("--reference-authority-signature", type=Path)
    parser.add_argument(
        "--trusted-key",
        action="append",
        default=[],
        metavar="KEY_ID=ENVIRONMENT_VARIABLE",
    )
    parser.add_argument(
        "--trusted-external-authority-key",
        action="append",
        default=[],
        metavar="KEY_ID=PATH",
    )
    parser.add_argument(
        "--trusted-reference-authority-key",
        action="append",
        default=[],
        metavar="KEY_ID=PATH",
        help=(
            "Runtime-trusted Reference Authority Ed25519 public key; the key "
            "must be distinct from acquisition/legal authority credentials."
        ),
    )
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--study-area-id", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--experiment-id")
    parser.add_argument("--source-timestamp", required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--source-name", required=True)
    parser.add_argument(
        "--assumption",
        action="append",
        required=True,
        help="Repeat for each explicit release assumption.",
    )
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument(
        "--purpose",
        choices=sorted(PURPOSES),
        help=(
            "Exact authorized purpose. Required for synthetic and qualified "
            "releases; blocked projections default safely to derived_metrics_only."
        ),
    )
    parser.add_argument(
        "--reference-authority-class",
        choices=sorted(REFERENCE_AUTHORITY_CLASSES),
        default="contextual_evidence",
    )
    parser.add_argument(
        "--confidence-class",
        choices=("low", "medium", "high"),
        default="low",
    )
    parser.add_argument("--reference-product-id")
    parser.add_argument("--reference-artifact", type=Path)
    parser.add_argument("--analysis-grid-contract", type=Path)
    parser.add_argument("--observation-start")
    parser.add_argument("--observation-end")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _validate_mode_inputs(args: argparse.Namespace) -> None:
    if args.release_status != BLOCKED_STATUS and args.purpose is None:
        raise ValueError("--purpose is required for synthetic and qualified releases")
    if args.release_status == SYNTHETIC_STATUS:
        forbidden = {
            "--acquisition-manifest": args.acquisition_manifest,
            "--artifact": args.artifact,
            "--acquisition-authority-receipt": (args.acquisition_authority_receipt),
            "--trusted-key": args.trusted_key,
            "--trusted-external-authority-key": (args.trusted_external_authority_key),
            "--reference-authority-decision": args.reference_authority_decision,
            "--reference-authority-signature": (args.reference_authority_signature),
            "--trusted-reference-authority-key": (args.trusted_reference_authority_key),
        }
        present = sorted(option for option, value in forbidden.items() if value)
        if present:
            raise ValueError(
                "synthetic_fixture_only cannot carry acquisition authority inputs: "
                + ", ".join(present)
            )
        return

    if args.acquisition_manifest is None:
        raise ValueError(
            "--acquisition-manifest is required for blocked and qualified releases"
        )
    if args.acquisition_authority_receipt is not None and (
        not args.trusted_key or not args.trusted_external_authority_key
    ):
        raise ValueError(
            "An acquisition-authority receipt requires both trusted internal and "
            "external authority keys."
        )
    if args.release_status == QUALIFIED_STATUS:
        missing = []
        if set(_artifact_mapping(args.artifact)) != set(REQUIRED_INPUT_ROLES):
            missing.append("--artifact for all three required roles")
        for option, value in (
            ("--acquisition-authority-receipt", args.acquisition_authority_receipt),
            ("--analysis-grid-contract", args.analysis_grid_contract),
            ("--observation-start", args.observation_start),
            ("--observation-end", args.observation_end),
            ("--reference-authority-decision", args.reference_authority_decision),
            (
                "--reference-authority-signature",
                args.reference_authority_signature,
            ),
        ):
            if value is None:
                missing.append(option)
        if not args.trusted_reference_authority_key:
            missing.append("--trusted-reference-authority-key")
        if missing:
            raise ValueError(
                "qualified release is missing required input(s): " + ", ".join(missing)
            )


def main() -> int:
    args = _parser().parse_args()
    try:
        _validate_mode_inputs(args)
        generated_at = _timestamp(args.generated_at, "--generated-at")
        source_timestamp = _timestamp(args.source_timestamp, "--source-timestamp")
        artifacts = _artifact_mapping(args.artifact)
        acquisition = None
        if args.release_status != SYNTHETIC_STATUS:
            acquisition = assess_acquisition_manifest(
                args.acquisition_manifest,
                artifact_paths=artifacts,
                authority_receipt_path=args.acquisition_authority_receipt,
                signing_keys=_trusted_keys(args.trusted_key),
                external_authority_public_keys=_external_public_keys(
                    args.trusted_external_authority_key
                ),
                verified_at_utc=generated_at,
            )
        reference_artifact = args.reference_artifact
        if reference_artifact is None:
            reference_artifact = artifacts.get("reference_mask")
        release = build_qualified_reference_release(
            acquisition,
            release_id=args.release_id,
            study_area_id=args.study_area_id,
            event_id=args.event_id,
            experiment_id=args.experiment_id,
            source_timestamp=source_timestamp,
            generated_at=generated_at,
            source_name=args.source_name,
            assumptions=args.assumption,
            data_version=args.data_version,
            git_commit=args.git_commit,
            purpose=args.purpose,
            release_status=args.release_status,
            reference_authority_class=args.reference_authority_class,
            confidence_class=args.confidence_class,
            reference_product_id=args.reference_product_id,
            reference_artifact_path=reference_artifact,
            analysis_grid_contract_path=args.analysis_grid_contract,
            acquisition_authority_receipt_path=(
                args.acquisition_authority_receipt
                if args.release_status == QUALIFIED_STATUS
                else None
            ),
            reference_authority_decision_path=(
                args.reference_authority_decision
                if args.release_status == QUALIFIED_STATUS
                else None
            ),
            reference_authority_signature_path=(
                args.reference_authority_signature
                if args.release_status == QUALIFIED_STATUS
                else None
            ),
            reference_authority_public_keys=(
                _external_public_keys(args.trusted_reference_authority_key)
                if args.release_status == QUALIFIED_STATUS
                else None
            ),
            observation_start=args.observation_start,
            observation_end=args.observation_end,
        )
        output = write_qualified_reference_release(release, args.output)
    except (
        ControlledExperimentError,
        OSError,
        QualifiedReferenceReleaseError,
        ValueError,
    ) as exc:
        print(f"BLOCKED: {exc}")
        return 2

    print(f"release={output.name}")
    print(f"release_status={release['release_status']}")
    print(f"purpose={release['purpose']}")
    print(f"release_sha256={release['release_sha256']}")
    print(f"processing_allowed={str(release['processing_allowed']).lower()}")
    print("can_feed_decision_layer=false")
    print("can_feed_fpps=false")
    print("can_assign_action_class=false")
    print("official_warning=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
