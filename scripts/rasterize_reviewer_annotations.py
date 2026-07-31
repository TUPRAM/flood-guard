"""Rasterise locked blinded reviewer geometry onto canonical query cells."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.annotation_rasterization import (  # noqa: E402
    AnnotationRasterizationDependencyError,
    AnnotationRasterizationError,
    write_rasterized_annotation_outputs,
)
from floodguard.label_factory.annotations import (  # noqa: E402
    AnnotationRecord,
    AnnotationValidationError,
    load_annotation_log,
)


def main() -> None:
    """Write agreement-only cell labels; this does not freeze training truth."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation-log", type=Path, required=True)
    parser.add_argument(
        "--reviewer-id",
        required=True,
        help=(
            "Exact reviewer identity. Only that reviewer's latest locked revision "
            "per query is rasterized, enabling independent A/B artifacts."
        ),
    )
    parser.add_argument("--query-manifest", type=Path, required=True)
    parser.add_argument(
        "--geometry-parts",
        type=Path,
        required=True,
        help=(
            "CSV whose complete canonical part set must exactly match the versioned "
            "geometry payload locked into each annotation record"
        ),
    )
    parser.add_argument("--cell-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        annotations = _latest_locked_reviewer_annotations(
            load_annotation_log(args.annotation_log), args.reviewer_id
        )
        written = write_rasterized_annotation_outputs(
            annotations,
            args.query_manifest,
            args.geometry_parts,
            cell_output_path=args.cell_output,
            manifest_output_path=args.manifest_output,
        )
    except (
        AnnotationValidationError,
        AnnotationRasterizationError,
        AnnotationRasterizationDependencyError,
        OSError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote cell labels: {written.cell_labels}")
    print(f"Wrote rasterization manifest: {written.manifest}")


def _latest_locked_reviewer_annotations(
    records: tuple[AnnotationRecord, ...], reviewer_id: str
) -> tuple[AnnotationRecord, ...]:
    reviewer = reviewer_id.strip()
    if not reviewer:
        raise AnnotationRasterizationError("reviewer_id must not be blank.")
    matching = [record for record in records if record.reviewer_id == reviewer]
    if not matching:
        raise AnnotationRasterizationError(
            f"Annotation log contains no records for reviewer {reviewer!r}."
        )
    by_query: dict[str, list[AnnotationRecord]] = {}
    for record in matching:
        by_query.setdefault(record.query_region_id, []).append(record)
    selected: list[AnnotationRecord] = []
    for query_id, revisions in sorted(by_query.items()):
        latest_revision = max(record.reviewer_revision for record in revisions)
        latest = [
            record
            for record in revisions
            if record.reviewer_revision == latest_revision
        ]
        if len(latest) != 1:
            raise AnnotationRasterizationError(
                f"Reviewer {reviewer!r} has duplicate latest revisions for {query_id}."
            )
        record = latest[0]
        if not record.is_locked or not record.review_complete:
            raise AnnotationRasterizationError(
                f"Reviewer {reviewer!r} latest record for {query_id} is not locked and complete."
            )
        selected.append(record)
    return tuple(selected)


if __name__ == "__main__":
    main()
