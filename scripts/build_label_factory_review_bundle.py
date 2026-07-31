"""Build a model-blinded QGIS-compatible flood-label review bundle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.review_bundle import (  # noqa: E402
    ReviewBundleError,
    ReviewPurpose,
    write_blinded_review_bundle,
)


def main() -> None:
    """Write reviewer-visible regions without model, weak-label, or rank fields."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queries",
        type=Path,
        required=True,
        help=(
            "Canonical query-region CSV. Acquisition uses selected rows; "
            "calibration/evaluation use fixed dataset-role membership."
        ),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="New write-once directory for reviewer-visible artifacts only.",
    )
    parser.add_argument(
        "--context-layers",
        type=Path,
        required=True,
        help=(
            "Required source-evidence CSV with approved reviewer context, exact "
            "product/timestamp provenance, and source/processed SHA-256 checksums."
        ),
    )
    parser.add_argument(
        "--processing-alignment-receipt",
        type=Path,
        required=True,
        help=(
            "Self-hashed receipt binding raw pre/event context to the processed "
            "common-grid files and their source assets."
        ),
    )
    parser.add_argument(
        "--derivative-lineage-receipt",
        type=Path,
        help=(
            "Required only when context includes VV change, VH change, or the "
            "fixed-stretch composite; copied into and hash-bound by the bundle."
        ),
    )
    parser.add_argument(
        "--governance-package",
        type=Path,
        required=True,
        help=(
            "Semantically validated governance_cleared_vN package whose exact "
            "event/source registries bind the processing receipt."
        ),
    )
    parser.add_argument(
        "--grid-validation-receipt",
        type=Path,
        required=True,
        help="Governance-bearing v3 receipt for the complete canonical grid.",
    )
    parser.add_argument(
        "--canonical-tile-manifest",
        type=Path,
        required=True,
        help="Complete canonical tile CSV bound by the grid receipt.",
    )
    parser.add_argument(
        "--canonical-query-manifest",
        type=Path,
        required=True,
        help="Complete canonical query CSV from which review rows were selected.",
    )
    parser.add_argument(
        "--supported-query-derivation",
        type=Path,
        help=(
            "Required when the canonical grid uses a supported-query allowlist; "
            "its output hashes are revalidated before bundling."
        ),
    )
    parser.add_argument(
        "--human-role-package",
        type=Path,
        required=True,
        help=(
            "Frozen, versioned human-role package. Calibration requires its "
            "evidence-complete pre-calibration version; acquisition/evaluation "
            "require a post-calibration version with formal_review_authorized=true."
        ),
    )
    parser.add_argument(
        "--target-reviewer-id",
        required=True,
        help=(
            "Stable appointed role id: the package's reviewer_a id for primary "
            "or reviewer_b id for secondary."
        ),
    )
    parser.add_argument(
        "--planned-review-start-utc",
        required=True,
        help=(
            "Earliest intended review start, as an ISO-8601 UTC timestamp ending "
            "in Z; it must not predate the applicable frozen-package/formal gate."
        ),
    )
    parser.add_argument(
        "--review-purpose",
        choices=tuple(purpose.value for purpose in ReviewPurpose),
        required=True,
        help=(
            "Role isolation contract: acquisition_primary, reviewer_calibration, "
            "or fixed_evaluation."
        ),
    )
    parser.add_argument(
        "--selected-column",
        default="selected",
        help="Explicit acquisition flag column; ignored as a filter in fixed review modes.",
    )
    parser.add_argument("--protocol-version", default="label_factory_protocol_v1")
    parser.add_argument("--taxonomy-version", default="flood_label_v1")
    parser.add_argument("--tool-version", default="qgis_manual_review_v1")
    parser.add_argument(
        "--review-stage",
        choices=("primary", "secondary"),
        default="primary",
        help="Independent reviewer stage encoded in the blank annotation form.",
    )
    args = parser.parse_args()
    try:
        written = write_blinded_review_bundle(
            args.queries,
            args.output_directory,
            review_purpose=args.review_purpose,
            processing_alignment_receipt=args.processing_alignment_receipt,
            derivative_lineage_receipt=args.derivative_lineage_receipt,
            governance_package=args.governance_package,
            grid_validation_receipt=args.grid_validation_receipt,
            canonical_tile_manifest=args.canonical_tile_manifest,
            canonical_query_manifest=args.canonical_query_manifest,
            supported_query_derivation=args.supported_query_derivation,
            selected_column=args.selected_column,
            protocol_version=args.protocol_version,
            taxonomy_version=args.taxonomy_version,
            tool_version=args.tool_version,
            review_stage=args.review_stage,
            human_role_package=args.human_role_package,
            target_reviewer_id=args.target_reviewer_id,
            planned_review_start_utc=args.planned_review_start_utc,
            context_layers=args.context_layers,
        )
    except ReviewBundleError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for label, path in written.items():
        print(f"Wrote {label}: {path}")


if __name__ == "__main__":
    main()
