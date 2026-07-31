"""Rasterize a locked authority decision into calibration reference-cell input."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.annotation_rasterization import (  # noqa: E402
    AnnotationRasterizationDependencyError,
    AnnotationRasterizationError,
)
from floodguard.label_factory.annotations import (  # noqa: E402
    AnnotationRecord,
    AnnotationValidationError,
    load_annotation_log,
)
from floodguard.label_factory.calibration_reference_rasterization import (  # noqa: E402
    write_calibration_reference_cell_input,
)


def main() -> None:
    """Write complete cells and lineage; do not freeze or claim reference truth."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-annotation-log", type=Path, required=True)
    parser.add_argument("--authority-id", required=True)
    parser.add_argument(
        "--authority-role-evidence",
        type=Path,
        required=True,
        help="Attributable acceptance/qualification evidence bound by checksum.",
    )
    parser.add_argument("--calibration-query-manifest", type=Path, required=True)
    parser.add_argument("--geometry-parts", type=Path, required=True)
    parser.add_argument("--assumptions", required=True)
    parser.add_argument("--reference-cells-input-output", type=Path, required=True)
    parser.add_argument("--lineage-manifest-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        query_ids = set(
            pd.read_csv(args.calibration_query_manifest)["query_region_id"].astype(str)
        )
        annotations = _latest_locked_authority_annotations(
            load_annotation_log(args.authority_annotation_log),
            authority_id=args.authority_id,
            query_ids=query_ids,
        )
        outputs = write_calibration_reference_cell_input(
            annotations,
            args.calibration_query_manifest,
            args.geometry_parts,
            authority_id=args.authority_id,
            authority_role_evidence=args.authority_role_evidence,
            assumptions=args.assumptions,
            cell_output_path=args.reference_cells_input_output,
            manifest_output_path=args.lineage_manifest_output,
        )
    except (
        AnnotationValidationError,
        AnnotationRasterizationError,
        AnnotationRasterizationDependencyError,
        KeyError,
        OSError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote calibration reference-cell input: {outputs.cells.name}")
    print(f"Wrote self-hashed confidential lineage manifest: {outputs.manifest.name}")
    print("Reference frozen: false")
    print("Training/decision/FPPS/warning eligibility: false")


def _latest_locked_authority_annotations(
    records: tuple[AnnotationRecord, ...],
    *,
    authority_id: str,
    query_ids: set[str],
) -> tuple[AnnotationRecord, ...]:
    authority = authority_id.strip()
    if not authority:
        raise AnnotationRasterizationError("authority_id must not be blank.")
    if not query_ids:
        raise AnnotationRasterizationError(
            "Calibration query manifest must not be empty."
        )
    matching = [
        record
        for record in records
        if record.reviewer_id == authority and record.query_region_id in query_ids
    ]
    selected: list[AnnotationRecord] = []
    for query_id in sorted(query_ids):
        revisions = [
            record for record in matching if record.query_region_id == query_id
        ]
        if not revisions:
            raise AnnotationRasterizationError(
                f"Authority {authority!r} has no annotation for {query_id}."
            )
        latest_revision = max(record.reviewer_revision for record in revisions)
        latest = [
            record
            for record in revisions
            if record.reviewer_revision == latest_revision
        ]
        if len(latest) != 1:
            raise AnnotationRasterizationError(
                f"Authority {authority!r} has duplicate latest revisions for {query_id}."
            )
        record = latest[0]
        if not record.is_locked or not record.review_complete:
            raise AnnotationRasterizationError(
                f"Authority {authority!r} latest record for {query_id} is not locked and complete."
            )
        selected.append(record)
    return tuple(selected)


if __name__ == "__main__":
    main()
