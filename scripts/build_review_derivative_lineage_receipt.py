"""Build the governed reviewer-visible VV/VH change derivative receipt."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.review_derivatives import (  # noqa: E402
    ReviewDerivativeLineageError,
    build_review_derivative_lineage_receipt,
    write_review_derivative_lineage_receipt,
)


def main() -> None:
    """Re-hash exact source/output bytes and write one immutable receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-spec",
        type=Path,
        required=True,
        help=(
            "Exact JSON build spec for VV change, VH change, and the fixed-stretch "
            "RGB composite, including local source/output paths and hashes."
        ),
    )
    parser.add_argument(
        "--processing-alignment-receipt",
        type=Path,
        required=True,
        help="Self-hashed processing receipt for the exact pre/event source rasters.",
    )
    parser.add_argument(
        "--governance-package",
        type=Path,
        required=True,
        help=(
            "Sealed governance_cleared_vN package whose event/source registries "
            "bind the processing receipt."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New write-once .json derivative-lineage receipt path.",
    )
    parser.add_argument(
        "--validated-at-utc",
        help="Optional timezone-aware validation timestamp for reproducible runs.",
    )
    args = parser.parse_args()
    try:
        receipt = build_review_derivative_lineage_receipt(
            args.build_spec,
            processing_alignment_receipt=args.processing_alignment_receipt,
            governance_package=args.governance_package,
            validated_at_utc=args.validated_at_utc,
        )
        output = write_review_derivative_lineage_receipt(receipt, args.output)
    except (ReviewDerivativeLineageError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote review-derivative lineage receipt: {output}")
    print(
        "Safety: formal-review-display-only; decision layer=false; "
        "FPPS=false; warning=false"
    )
    print(
        "Authority: not asserted by this lineage receipt; check the candidate "
        "generation manifest and attributable authority decision."
    )


if __name__ == "__main__":
    main()
