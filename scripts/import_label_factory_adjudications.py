"""Import real completed adjudications with exact queue coverage and lineage."""

from __future__ import annotations

import argparse
from datetime import datetime
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.adjudication import AdjudicationError  # noqa: E402
from floodguard.label_factory.adjudication_import import (  # noqa: E402
    AdjudicationImportError,
    import_completed_adjudications,
)
from floodguard.label_factory.annotations import AnnotationValidationError  # noqa: E402
from floodguard.label_factory.review_workflow import ReviewWorkflowError  # noqa: E402


def main() -> None:
    """Validate the full submitted batch before appending any resolution."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed-adjudications", type=Path, required=True)
    parser.add_argument("--adjudication-queue", type=Path, required=True)
    parser.add_argument("--annotation-log", type=Path, required=True)
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument("--adjudication-log", type=Path, required=True)
    parser.add_argument(
        "--receipt-json",
        type=Path,
        required=True,
        help="New immutable import receipt; existing files are never overwritten.",
    )
    parser.add_argument(
        "--imported-at-utc",
        required=True,
        help="Explicit timezone-aware import timestamp (for example 2024-09-18T03:00:00Z).",
    )
    args = parser.parse_args()
    try:
        imported_at = datetime.fromisoformat(
            args.imported_at_utc.replace("Z", "+00:00")
        )
        receipt = import_completed_adjudications(
            args.completed_adjudications,
            adjudication_queue=args.adjudication_queue,
            annotation_log=args.annotation_log,
            adjudication_log=args.adjudication_log,
            receipt_json=args.receipt_json,
            reviewer_a_id=args.reviewer_a_id,
            reviewer_b_id=args.reviewer_b_id,
            imported_at_utc=imported_at,
        )
    except (
        AdjudicationImportError,
        AdjudicationError,
        AnnotationValidationError,
        ReviewWorkflowError,
        OSError,
        ValueError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(
        f"Imported {receipt.imported_count} human adjudication(s) with exact queue "
        f"coverage into {receipt.adjudication_log_path}"
    )
    print(f"Receipt SHA-256: {receipt.receipt_sha256}")
    print(f"Wrote receipt: {args.receipt_json}")


if __name__ == "__main__":
    main()
