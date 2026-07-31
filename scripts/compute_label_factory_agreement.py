"""Compute cell-level agreement for explicit locked reviewer A/B pairs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.adjudication import (  # noqa: E402
    AdjudicationError,
    pair_locked_annotations,
)
from floodguard.label_factory.agreement import AgreementError  # noqa: E402
from floodguard.label_factory.annotations import (  # noqa: E402
    AnnotationValidationError,
    load_annotation_log,
)
from floodguard.label_factory.review_workflow import (  # noqa: E402
    ReviewWorkflowError,
    compute_cell_level_agreement,
    write_agreement_outputs,
)


def main() -> None:
    """Require canonical cell labels; primary_class alone is not an agreement raster."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation-log", type=Path, required=True)
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument(
        "--cell-labels",
        type=Path,
        required=True,
        help=(
            "CSV with annotation_id, query_region_id, cell_id, label_code; add "
            "row_index and column_index for boundary F1."
        ),
    )
    parser.add_argument("--pixel-size-m", type=float)
    parser.add_argument("--boundary-tolerance-m", type=float, default=20.0)
    parser.add_argument(
        "--query-strata",
        type=Path,
        required=True,
        help="CSV mapping every query_region_id to one or more critical strata.",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--per-query-output-csv", type=Path, required=True)
    args = parser.parse_args()
    try:
        records = load_annotation_log(args.annotation_log)
        pairs = pair_locked_annotations(
            records,
            reviewer_a_id=args.reviewer_a_id,
            reviewer_b_id=args.reviewer_b_id,
        )
        result = compute_cell_level_agreement(
            pairs,
            args.cell_labels,
            pixel_size_m=args.pixel_size_m,
            boundary_tolerance_m=args.boundary_tolerance_m,
            query_strata=args.query_strata,
        )
        written = write_agreement_outputs(
            result,
            json_path=args.output_json,
            per_query_csv_path=args.per_query_output_csv,
            pairs=pairs,
            cell_labels=args.cell_labels,
            query_strata=args.query_strata,
        )
    except (
        ReviewWorkflowError,
        AnnotationValidationError,
        AdjudicationError,
        AgreementError,
        OSError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(
        f"Measured {result.total_cell_count} canonical cells across "
        f"{result.query_count} query pair(s)."
    )
    print(f"Wrote agreement JSON: {written[0]}")
    print(f"Wrote per-query CSV: {written[1]}")


if __name__ == "__main__":
    main()
