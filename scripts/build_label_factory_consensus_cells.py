"""Build immutable final consensus cells from locked blinded human review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.adjudication import AdjudicationError  # noqa: E402
from floodguard.label_factory.annotation_rasterization import (  # noqa: E402
    AnnotationRasterizationDependencyError,
    AnnotationRasterizationError,
)
from floodguard.label_factory.annotations import (  # noqa: E402
    AnnotationValidationError,
)
from floodguard.label_factory.consensus_builder import (  # noqa: E402
    BUILDER_VERSION,
    ConsensusBuilderError,
    write_consensus_outputs,
)
from floodguard.label_factory.review_workflow import ReviewWorkflowError  # noqa: E402


def main() -> None:
    """Validate exact lineage and write the four freeze inputs once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation-log", type=Path, required=True)
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument("--reviewer-a-cells", type=Path, required=True)
    parser.add_argument("--reviewer-a-raster-manifest", type=Path, required=True)
    parser.add_argument("--reviewer-b-cells", type=Path, required=True)
    parser.add_argument("--reviewer-b-raster-manifest", type=Path, required=True)
    parser.add_argument("--query-manifest", type=Path, required=True)
    parser.add_argument("--adjudication-queue", type=Path, required=True)
    parser.add_argument(
        "--adjudication-log",
        type=Path,
        required=True,
        help=(
            "Hash-chained resolution log. The path may be absent only when the "
            "validated queue is empty; that absence is bound as canonical empty bytes."
        ),
    )
    parser.add_argument(
        "--redraw-cells",
        type=Path,
        help="Required only when the adjudication log contains a redraw outcome.",
    )
    parser.add_argument(
        "--redraw-raster-manifest",
        type=Path,
        help="Manifest binding redraw cells to exact locked adjudication geometry.",
    )
    parser.add_argument("--output-cells", type=Path, required=True)
    parser.add_argument("--output-raster-lineage", type=Path, required=True)
    parser.add_argument("--output-label-content", type=Path, required=True)
    parser.add_argument("--output-consensus-receipt", type=Path, required=True)
    parser.add_argument("--builder-version", default=BUILDER_VERSION)
    args = parser.parse_args()

    try:
        outputs = write_consensus_outputs(
            annotation_log_path=args.annotation_log,
            reviewer_a_id=args.reviewer_a_id,
            reviewer_b_id=args.reviewer_b_id,
            reviewer_a_cells_path=args.reviewer_a_cells,
            reviewer_a_manifest_path=args.reviewer_a_raster_manifest,
            reviewer_b_cells_path=args.reviewer_b_cells,
            reviewer_b_manifest_path=args.reviewer_b_raster_manifest,
            adjudication_queue_path=args.adjudication_queue,
            adjudication_log_path=args.adjudication_log,
            query_manifest_path=args.query_manifest,
            redraw_cells_path=args.redraw_cells,
            redraw_manifest_path=args.redraw_raster_manifest,
            final_cells_path=args.output_cells,
            raster_lineage_path=args.output_raster_lineage,
            label_content_path=args.output_label_content,
            consensus_receipt_path=args.output_consensus_receipt,
            builder_version=args.builder_version,
        )
    except (
        ConsensusBuilderError,
        AnnotationValidationError,
        AnnotationRasterizationError,
        AnnotationRasterizationDependencyError,
        AdjudicationError,
        ReviewWorkflowError,
        OSError,
        ValueError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"Wrote final consensus cells: {outputs.final_cells}")
    print(f"Wrote raster lineage: {outputs.raster_lineage}")
    print(f"Wrote label content: {outputs.label_content}")
    print(f"Wrote self-hashed consensus receipt: {outputs.consensus_receipt}")


if __name__ == "__main__":
    main()
