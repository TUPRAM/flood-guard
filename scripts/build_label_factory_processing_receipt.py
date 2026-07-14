"""Build an immutable, evidence-backed SAR processing/alignment receipt."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.processing_alignment import (  # noqa: E402
    ProcessingAlignmentError,
    build_processing_alignment_receipt,
    write_processing_alignment_receipt,
)
from floodguard.label_factory.rights_clearance import (  # noqa: E402
    RightsClearanceError,
    validate_cleared_registry_binding,
)


def main() -> None:
    """Hash processed artifacts, validate the common grid, and write once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--source-assets", type=Path, required=True)
    parser.add_argument(
        "--governance-package",
        type=Path,
        required=True,
        help=(
            "Semantically validated governance_cleared_vN directory whose event "
            "and source registries exactly match --events and --source-assets."
        ),
    )
    parser.add_argument(
        "--processing-evidence",
        type=Path,
        required=True,
        help=(
            "Exact v1 CSV mapping every non-static source asset to local processed, "
            "coverage, valid-data, and registration evidence files and expected hashes."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate_cleared_registry_binding(
            args.governance_package,
            args.events,
            args.source_assets,
        )
        receipt = build_processing_alignment_receipt(
            args.events,
            args.source_assets,
            args.processing_evidence,
            governance_package=args.governance_package,
        )
        written = write_processing_alignment_receipt(receipt, args.output)
    except (ProcessingAlignmentError, RightsClearanceError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote processing/alignment receipt: {written}")
    print(
        "Scope: byte-hash and common-grid evidence only; synthetic fixtures do not "
        "prove real raster processing or flood truth."
    )
    print("Safety: query-model-only; decision layer=false; FPPS=false; warning=false")


if __name__ == "__main__":
    main()
