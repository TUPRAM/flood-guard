"""Freeze a reviewed labelset after QA, checksum, and adjudication gates pass."""

from __future__ import annotations

import argparse
from datetime import datetime
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.adjudication import (  # noqa: E402
    AdjudicationError,
    load_adjudication_log,
)
from floodguard.label_factory.annotations import (  # noqa: E402
    AnnotationValidationError,
    load_annotation_log,
)
from floodguard.label_factory.calibration import (  # noqa: E402
    ReviewerCalibrationError,
    load_reviewer_calibration_receipt,
)
from floodguard.label_factory.review_workflow import (  # noqa: E402
    ReviewWorkflowError,
    freeze_reviewed_labelset,
    load_adjudication_queue_csv,
    load_json_object,
    load_json_value,
    load_qa_report_csv,
    parse_name_path,
    parse_name_sha256,
)
from floodguard.label_factory.versioning import (  # noqa: E402
    LabelsetVersionError,
    load_labelset_manifest,
)


def main() -> None:
    """Create a manifest exactly once; never overwrite an existing release id."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation-log", type=Path, required=True)
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument("--adjudication-queue", type=Path, required=True)
    parser.add_argument("--adjudication-log", type=Path, required=True)
    parser.add_argument("--qa-report", type=Path, required=True)
    parser.add_argument("--qa-evidence-manifest", type=Path, required=True)
    parser.add_argument("--qa-source-assets", type=Path, required=True)
    parser.add_argument("--qa-dataset-assignments", type=Path, required=True)
    parser.add_argument("--qa-usage-records", type=Path, required=True)
    parser.add_argument("--qa-binary-training-rows", type=Path, required=True)
    parser.add_argument("--qa-query-models", type=Path)
    parser.add_argument("--qa-query-records", type=Path)
    parser.add_argument("--reviewer-calibration-receipt", type=Path, required=True)
    parser.add_argument("--agreement-json", type=Path, required=True)
    parser.add_argument("--raster-lineage-json", type=Path, required=True)
    parser.add_argument("--reviewer-a-cells", type=Path, required=True)
    parser.add_argument("--reviewer-a-raster-manifest", type=Path, required=True)
    parser.add_argument("--reviewer-b-cells", type=Path, required=True)
    parser.add_argument("--reviewer-b-raster-manifest", type=Path, required=True)
    parser.add_argument("--query-manifest", type=Path, required=True)
    parser.add_argument("--redraw-cells", type=Path)
    parser.add_argument("--redraw-raster-manifest", type=Path)
    parser.add_argument("--labelset-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--change-kind",
        required=True,
        choices=("initial", "major", "minor", "patch"),
    )
    parser.add_argument("--label-content-json", type=Path, required=True)
    parser.add_argument("--metadata-json", type=Path, required=True)
    parser.add_argument("--semantics-json", type=Path, required=True)
    parser.add_argument(
        "--source-annotation-id",
        action="append",
        required=True,
        help="Repeat for every latest locked reviewer A/B annotation.",
    )
    parser.add_argument(
        "--raster",
        action="append",
        required=True,
        metavar="NAME=PATH",
    )
    parser.add_argument(
        "--expected-raster-sha256",
        action="append",
        required=True,
        metavar="NAME=SHA256",
    )
    parser.add_argument("--created-at-utc", required=True)
    parser.add_argument("--parent-manifest", type=Path)
    parser.add_argument("--output-manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        annotations = load_annotation_log(args.annotation_log)
        queue = load_adjudication_queue_csv(args.adjudication_queue)
        adjudications = load_adjudication_log(args.adjudication_log)
        qa_report = load_qa_report_csv(args.qa_report)
        qa_evidence_manifest = load_json_object(
            args.qa_evidence_manifest, label="QA evidence manifest"
        )
        reviewer_calibration_receipt = load_reviewer_calibration_receipt(
            args.reviewer_calibration_receipt
        )
        agreement_evidence = load_json_object(
            args.agreement_json, label="agreement evidence"
        )
        raster_lineage = load_json_object(
            args.raster_lineage_json, label="raster lineage"
        )
        label_content = load_json_value(args.label_content_json, label="label content")
        metadata = load_json_object(args.metadata_json, label="metadata")
        semantics = load_json_object(args.semantics_json, label="semantics")
        raster_paths = parse_name_path(args.raster, label="raster")
        raster_hashes = parse_name_sha256(
            args.expected_raster_sha256,
            label="expected raster checksum",
        )
        created_at = datetime.fromisoformat(args.created_at_utc.replace("Z", "+00:00"))
        parent = (
            load_labelset_manifest(args.parent_manifest)
            if args.parent_manifest is not None
            else None
        )
        consensus_sources = {
            "annotation_log": args.annotation_log,
            "reviewer_a_cells": args.reviewer_a_cells,
            "reviewer_a_manifest": args.reviewer_a_raster_manifest,
            "reviewer_b_cells": args.reviewer_b_cells,
            "reviewer_b_manifest": args.reviewer_b_raster_manifest,
            "adjudication_queue": args.adjudication_queue,
            "adjudication_log": args.adjudication_log,
            "query_manifest": args.query_manifest,
        }
        if (args.redraw_cells is None) != (args.redraw_raster_manifest is None):
            raise ReviewWorkflowError(
                "--redraw-cells and --redraw-raster-manifest must be supplied together."
            )
        if args.redraw_cells is not None:
            consensus_sources["redraw_cells"] = args.redraw_cells
            consensus_sources["redraw_manifest"] = args.redraw_raster_manifest
        qa_raw_inputs = {
            "source_assets": args.qa_source_assets,
            "dataset_assignments": args.qa_dataset_assignments,
            "usage_records": args.qa_usage_records,
            "annotations": args.annotation_log,
            "binary_training_rows": args.qa_binary_training_rows,
        }
        if args.qa_query_models is not None:
            qa_raw_inputs["query_models"] = args.qa_query_models
        if args.qa_query_records is not None:
            qa_raw_inputs["query_records"] = args.qa_query_records
        manifest = freeze_reviewed_labelset(
            annotation_records=annotations,
            reviewer_a_id=args.reviewer_a_id,
            reviewer_b_id=args.reviewer_b_id,
            queue_items=queue,
            adjudications=adjudications,
            qa_report=qa_report,
            qa_evidence_manifest=qa_evidence_manifest,
            qa_report_path=args.qa_report,
            qa_raw_input_paths=qa_raw_inputs,
            reviewer_calibration_receipt=reviewer_calibration_receipt,
            agreement_evidence=agreement_evidence,
            raster_lineage=raster_lineage,
            labelset_name=args.labelset_name,
            version=args.version,
            change_kind=args.change_kind,
            label_content=label_content,
            metadata=metadata,
            semantics=semantics,
            source_annotation_ids=args.source_annotation_id,
            raster_paths=raster_paths,
            expected_raster_sha256=raster_hashes,
            consensus_source_artifact_paths=consensus_sources,
            output_path=args.output_manifest,
            created_at_utc=created_at,
            parent=parent,
        )
    except (
        ReviewWorkflowError,
        ReviewerCalibrationError,
        AnnotationValidationError,
        AdjudicationError,
        LabelsetVersionError,
        OSError,
        ValueError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Frozen labelset: {manifest.labelset_id}")
    print(f"Manifest SHA-256: {manifest.manifest_sha256}")
    print(f"Wrote manifest: {args.output_manifest}")


if __name__ == "__main__":
    main()
