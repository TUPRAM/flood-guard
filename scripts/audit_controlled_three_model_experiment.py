"""Write the current fail-closed three-model experiment gate decision."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path

from floodguard.controlled_experiment import (
    assess_acquisition_manifest,
    build_gate_receipt,
    write_gate_report,
)


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
    parser.add_argument("--reviewer-calibration-receipt", type=Path)
    parser.add_argument("--holdout-receipt", type=Path)
    parser.add_argument("--holdout-geometry", type=Path)
    parser.add_argument("--holdout-grid-contract", type=Path)
    parser.add_argument("--holdout-membership", type=Path)
    parser.add_argument("--reference-cell-receipt", type=Path)
    parser.add_argument("--reference-cell-evidence", type=Path)
    parser.add_argument("--model-evidence-manifest", type=Path)
    parser.add_argument(
        "--signing-key-id",
        default=os.environ.get(
            "FLOODGUARD_EXPERIMENT_SIGNING_KEY_ID",
            "experiment-authority-v1",
        ),
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
    generated_at = _timestamp(args.generated_at)
    signing_key = os.environ.get("FLOODGUARD_EXPERIMENT_SIGNING_KEY")
    signing_keys = (
        {args.signing_key_id: signing_key.encode("utf-8")}
        if signing_key is not None
        else {}
    )
    workspace = args.external_workspace
    artifact_paths = {
        "pre_event_sar": workspace
        / "sentinel1_original_safe"
        / "S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_055507_06C5C9_72F7.SAFE.zip",
        "post_event_sar": workspace
        / "sentinel1_original_safe"
        / "S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_055682_06CCBA_08DA.SAFE.zip",
        "reference_mask": workspace
        / "sentinel_asia"
        / "MBRSC_THAILAND_FLOOD-MAP-SHP.zip",
    }
    acquisition = assess_acquisition_manifest(
        args.manifest,
        artifact_paths=artifact_paths,
        authority_receipt_path=args.acquisition_authority_receipt,
        signing_keys=signing_keys,
        verified_at_utc=generated_at,
    )
    receipt = build_gate_receipt(
        acquisition,
        generated_at_utc=generated_at,
        reviewer_calibration_receipt_path=args.reviewer_calibration_receipt,
        holdout_receipt_path=args.holdout_receipt,
        holdout_geometry_path=args.holdout_geometry,
        holdout_grid_contract_path=args.holdout_grid_contract,
        holdout_membership_path=args.holdout_membership,
        reference_cell_receipt_path=args.reference_cell_receipt,
        reference_cell_evidence_path=args.reference_cell_evidence,
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
    print(f"receipt={outputs['receipt'].as_posix()}")
    print(f"report={outputs['report'].as_posix()}")
    if receipt["gate_status"] == "blocked" and not args.allow_blocked:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
