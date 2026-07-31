"""Write the current fail-closed three-model experiment gate decision."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path

from floodguard.controlled_experiment import (
    assess_acquisition_manifest,
    build_gate_receipt,
    load_ed25519_public_key,
    write_gate_report,
)


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
    return keys


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/validation/controlled_three_model_acquisition_manifest.csv"),
    )
    parser.add_argument(
        "--external-workspace",
        type=Path,
        default=Path.home() / "Documents" / "FloodGuard_external_data",
    )
    parser.add_argument(
        "--receipt-output",
        type=Path,
        default=Path("docs/validation/controlled_three_model_gate_receipt.json"),
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path(
            "docs/validation/controlled_three_model_experiment_gate_status.md"
        ),
    )
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--acquisition-authority-receipt", type=Path)
    parser.add_argument("--reviewer-qualification-receipt", type=Path)
    parser.add_argument("--holdout-receipt", type=Path)
    parser.add_argument("--holdout-geometry", type=Path)
    parser.add_argument("--holdout-grid-contract", type=Path)
    parser.add_argument("--holdout-membership", type=Path)
    parser.add_argument("--reference-cell-receipt", type=Path)
    parser.add_argument("--reference-cell-evidence", type=Path)
    parser.add_argument("--calibration-reference", type=Path)
    parser.add_argument("--error-strata", type=Path)
    parser.add_argument("--promotion-policy", type=Path)
    parser.add_argument("--model-evidence-manifest", type=Path)
    parser.add_argument(
        "--trusted-key",
        action="append",
        default=[],
        metavar="KEY_ID=ENVIRONMENT_VARIABLE",
        help="Trusted upstream signing credential; repeat for every supplied receipt.",
    )
    parser.add_argument(
        "--trusted-external-authority-key",
        action="append",
        default=[],
        metavar="KEY_ID=PATH",
    )
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Write the durable blocked receipt instead of returning an error.",
    )
    return parser.parse_args()


def _timestamp(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--generated-at must include a timezone")
    return parsed.astimezone(UTC)


def main() -> int:
    args = _parse_args()
    try:
        generated_at = _timestamp(args.generated_at)
        signing_keys = _trusted_keys(args.trusted_key)
        external_public_keys = _external_public_keys(
            args.trusted_external_authority_key
        )
    except ValueError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    workspace = args.external_workspace
    artifact_paths = {
        "pre_event_sar": workspace
        / "sentinel1_original_safe"
        / "S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_055507_06C5C9_72F7.SAFE.zip",
        "post_event_sar": workspace
        / "sentinel1_original_safe"
        / "S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_055682_06CCBA_08DA.SAFE.zip",
        "reference_mask": workspace
        / "qualified_reference"
        / "mae_sai_event_reference_mask.tif",
    }
    acquisition = assess_acquisition_manifest(
        args.manifest,
        artifact_paths=artifact_paths,
        authority_receipt_path=args.acquisition_authority_receipt,
        signing_keys=signing_keys,
        external_authority_public_keys=external_public_keys,
        verified_at_utc=generated_at,
    )
    receipt = build_gate_receipt(
        acquisition,
        generated_at_utc=generated_at,
        reviewer_qualification_receipt_path=args.reviewer_qualification_receipt,
        holdout_receipt_path=args.holdout_receipt,
        holdout_geometry_path=args.holdout_geometry,
        holdout_grid_contract_path=args.holdout_grid_contract,
        holdout_membership_path=args.holdout_membership,
        reference_cell_receipt_path=args.reference_cell_receipt,
        reference_cell_evidence_path=args.reference_cell_evidence,
        calibration_reference_path=args.calibration_reference,
        error_strata_path=args.error_strata,
        promotion_policy_path=args.promotion_policy,
        signing_keys=signing_keys,
        model_evidence_manifest_path=args.model_evidence_manifest,
    )
    outputs = write_gate_report(
        receipt,
        args.manifest,
        json_output_path=args.receipt_output,
        markdown_output_path=args.report_output,
    )
    print(f"gate_status={receipt['gate_status']}")
    print(f"receipt={outputs['receipt'].name}")
    print(f"report={outputs['report'].name}")
    if receipt["gate_status"] == "blocked" and not args.allow_blocked:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
