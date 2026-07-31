"""Import completed, blinded reviewer CSV rows into an immutable annotation log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.annotations import AnnotationValidationError  # noqa: E402
from floodguard.label_factory.review_workflow import (  # noqa: E402
    ReviewWorkflowError,
    import_reviewer_annotations,
)


def main() -> None:
    """Validate every row before appending the completed review batch."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed-annotations", type=Path, required=True)
    parser.add_argument("--annotation-log", type=Path, required=True)
    parser.add_argument(
        "--review-regions",
        type=Path,
        required=True,
        help="Original blinded review_regions.csv for id and geometry containment validation.",
    )
    parser.add_argument(
        "--geometry-parts",
        type=Path,
        required=True,
        help="Completed canonical multipart annotation geometry CSV.",
    )
    parser.add_argument(
        "--bundle-manifest",
        type=Path,
        required=True,
        help="Original bundle_manifest.csv shipped to this reviewer.",
    )
    parser.add_argument(
        "--context-layers",
        type=Path,
        required=True,
        help="Original checksum-tracked context_layers.csv from the same bundle.",
    )
    parser.add_argument(
        "--governance-package",
        type=Path,
        required=True,
        help=(
            "Matching semantically validated governance_cleared_vN package; "
            "synthetic fixture bundles are never accepted by this CLI."
        ),
    )
    parser.add_argument(
        "--grid-validation-receipt",
        type=Path,
        required=True,
        help="Original governance-bearing v3 canonical-grid receipt.",
    )
    parser.add_argument(
        "--canonical-tile-manifest",
        type=Path,
        required=True,
        help="Complete canonical tile manifest bound by the grid receipt.",
    )
    parser.add_argument(
        "--canonical-query-manifest",
        type=Path,
        required=True,
        help="Complete canonical query manifest containing every review region.",
    )
    parser.add_argument(
        "--supported-query-derivation",
        type=Path,
        help="Required when the canonical grid uses a supported-query allowlist.",
    )
    parser.add_argument(
        "--receipt-json",
        type=Path,
        help="Optional new receipt path; existing files are never overwritten.",
    )
    args = parser.parse_args()
    try:
        receipt = import_reviewer_annotations(
            args.completed_annotations,
            args.annotation_log,
            expected_review_regions=args.review_regions,
            geometry_parts=args.geometry_parts,
            bundle_manifest=args.bundle_manifest,
            context_layers=args.context_layers,
            governance_package=args.governance_package,
            grid_validation_receipt=args.grid_validation_receipt,
            canonical_tile_manifest=args.canonical_tile_manifest,
            canonical_query_manifest=args.canonical_query_manifest,
            supported_query_derivation=args.supported_query_derivation,
        )
        if args.receipt_json is not None:
            args.receipt_json.parent.mkdir(parents=True, exist_ok=True)
            with args.receipt_json.open("x", encoding="utf-8") as handle:
                json.dump(receipt.to_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
    except (ReviewWorkflowError, AnnotationValidationError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(
        f"Imported {receipt.imported_count} locked annotation(s) into "
        f"{receipt.annotation_log_path}"
    )


if __name__ == "__main__":
    main()
