"""Generate the current FloodGuard flood-label factory readiness report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.readiness import (  # noqa: E402
    LabelFactoryReadinessError,
    build_grid_validation_receipt,
    write_grid_validation_receipt,
    write_label_factory_readiness_outputs,
)


def main() -> None:
    """Write compact readiness evidence while preserving missing human/data gates."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manual-reference-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "manual_reference_mask_manifest.csv",
    )
    parser.add_argument(
        "--weak-feature-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_sar_feature_manifest.csv",
    )
    parser.add_argument(
        "--weak-ml-metrics",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_weak_label_ml_metrics.csv",
    )
    parser.add_argument(
        "--events",
        type=Path,
        help="Complete event registry CSV used with source, tile, and query manifests.",
    )
    parser.add_argument(
        "--source-assets",
        type=Path,
        help="Complete source-asset registry CSV used with events, tiles, and queries.",
    )
    parser.add_argument(
        "--processing-alignment-receipt",
        type=Path,
        help=(
            "Self-hashed receipt proving processed-file byte hashes, RTC/terrain "
            "correction, coverage, and common-grid registration."
        ),
    )
    parser.add_argument(
        "--governance-package",
        type=Path,
        help=(
            "Semantically validated governance_cleared_vN package binding the "
            "exact event/source registries used for raw grid evidence."
        ),
    )
    parser.add_argument(
        "--canonical-tile-manifest",
        type=Path,
        help="Canonical tile CSV; never sufficient without events, sources, and queries.",
    )
    parser.add_argument(
        "--canonical-query-manifest",
        type=Path,
        help="Canonical query CSV used with events, sources, and tiles.",
    )
    parser.add_argument(
        "--supported-query-derivation",
        type=Path,
        help=(
            "Self-hashed supported-query derivation required when canonical "
            "manifests contain allowlist lineage columns."
        ),
    )
    parser.add_argument(
        "--grid-validation-receipt",
        type=Path,
        help="Previously generated, self-hashed canonical-grid validation JSON.",
    )
    parser.add_argument(
        "--grid-validation-receipt-output",
        type=Path,
        help=(
            "Immutably write a grid receipt after validating --events, --source-assets, "
            "--processing-alignment-receipt, --canonical-tile-manifest, and "
            "--canonical-query-manifest."
        ),
    )
    parser.add_argument(
        "--annotation-log",
        "--annotation-manifest",
        dest="annotation_log",
        type=Path,
        help="Hash-chained canonical annotation JSONL (legacy flag name is an alias).",
    )
    parser.add_argument(
        "--agreement-evidence",
        type=Path,
        help="Agreement JSON bound to exact locked reviews and cell artifacts.",
    )
    parser.add_argument(
        "--reviewer-calibration-receipt",
        type=Path,
        help=(
            "Passing self-hashed calibration receipt for the named formal reviewers; "
            "calibration cells remain training-ineligible."
        ),
    )
    parser.add_argument(
        "--labelset-validation-receipt",
        "--labelset-manifest",
        dest="labelset_validation_receipt",
        type=Path,
        help="Self-hashed labelset validation JSON (legacy flag name is an alias).",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=REPO_ROOT / "outputs" / "label_factory_readiness.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPO_ROOT / "outputs" / "label_factory_readiness.md",
    )
    args = parser.parse_args()
    try:
        if (
            args.grid_validation_receipt is not None
            and args.governance_package is None
        ):
            raise LabelFactoryReadinessError(
                "--grid-validation-receipt requires --governance-package so the "
                "receipt's recorded governance identity can be revalidated."
            )
        grid_receipt = args.grid_validation_receipt
        event_manifest = args.events
        source_asset_manifest = args.source_assets
        processing_alignment_receipt = args.processing_alignment_receipt
        tile_manifest = args.canonical_tile_manifest
        query_manifest = args.canonical_query_manifest
        if args.grid_validation_receipt_output is not None:
            if args.grid_validation_receipt is not None:
                raise LabelFactoryReadinessError(
                    "Cannot combine --grid-validation-receipt with "
                    "--grid-validation-receipt-output."
                )
            missing = [
                name
                for name, value in (
                    ("--events", event_manifest),
                    ("--source-assets", source_asset_manifest),
                    (
                        "--governance-package",
                        args.governance_package,
                    ),
                    (
                        "--processing-alignment-receipt",
                        processing_alignment_receipt,
                    ),
                    ("--canonical-tile-manifest", tile_manifest),
                    ("--canonical-query-manifest", query_manifest),
                )
                if value is None
            ]
            if missing:
                raise LabelFactoryReadinessError(
                    "Grid receipt generation requires: " + ", ".join(missing)
                )
            receipt = build_grid_validation_receipt(
                event_manifest,
                source_asset_manifest,
                processing_alignment_receipt,
                tile_manifest,
                query_manifest,
                governance_package=args.governance_package,
                supported_query_derivation=args.supported_query_derivation,
            )
            grid_receipt = write_grid_validation_receipt(
                receipt, args.grid_validation_receipt_output
            )
            # Readiness consumes the newly verified receipt through its strict
            # loader, avoiding an ambiguous mixture of receipt and raw inputs.
            event_manifest = None
            source_asset_manifest = None
            processing_alignment_receipt = None
            tile_manifest = None
            query_manifest = None
            args.supported_query_derivation = None
        written = write_label_factory_readiness_outputs(
            args.manual_reference_manifest,
            args.weak_feature_manifest,
            args.weak_ml_metrics,
            csv_output_path=args.csv_output,
            summary_output_path=args.summary_output,
            event_manifest=event_manifest,
            source_asset_manifest=source_asset_manifest,
            processing_alignment_receipt=processing_alignment_receipt,
            supported_query_derivation=args.supported_query_derivation,
            governance_package=args.governance_package,
            canonical_tile_manifest=tile_manifest,
            canonical_query_manifest=query_manifest,
            grid_validation_receipt=grid_receipt,
            annotation_log=args.annotation_log,
            agreement_evidence=args.agreement_evidence,
            reviewer_calibration_receipt=args.reviewer_calibration_receipt,
            labelset_validation_receipt=args.labelset_validation_receipt,
        )
    except LabelFactoryReadinessError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for label, path in written.items():
        print(f"Wrote {label}: {path}")
if __name__ == "__main__":
    main()
