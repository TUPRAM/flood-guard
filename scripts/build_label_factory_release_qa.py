"""Recompute release QA from raw files and write an immutable QA receipt."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.adjudication import (  # noqa: E402
    AdjudicationError,
    pair_locked_annotations,
)
from floodguard.label_factory.annotations import (  # noqa: E402
    AnnotationRecord,
    AnnotationValidationError,
)
from floodguard.label_factory.calibration import (  # noqa: E402
    ReviewerCalibrationError,
    load_reviewer_calibration_receipt,
)
from floodguard.label_factory.release_qa import (  # noqa: E402
    ReleaseQAError,
    run_release_qa_from_raw_inputs,
    write_release_qa_artifacts_from_raw,
)
from floodguard.label_factory.review_workflow import (  # noqa: E402
    ReviewWorkflowError,
    build_release_qa_evidence_manifest,
    load_json_object,
    parse_name_path,
)
from floodguard.label_factory.versioning import (  # noqa: E402
    LabelsetVersionError,
    file_sha256,
)


def main() -> None:
    """Build the only raw-input-bound QA artifact accepted by release gates."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-assets", type=Path, required=True)
    parser.add_argument("--dataset-assignments", type=Path, required=True)
    parser.add_argument("--usage-records", type=Path, required=True)
    parser.add_argument("--annotation-log", type=Path, required=True)
    parser.add_argument("--binary-training-rows", type=Path, required=True)
    parser.add_argument(
        "--query-models",
        type=Path,
        help="Optional flat query-model manifest or score rows in release scope.",
    )
    parser.add_argument(
        "--query-records",
        type=Path,
        help="Optional selected-query manifest in release scope.",
    )
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument("--reviewer-calibration-receipt", type=Path, required=True)
    parser.add_argument("--agreement-json", type=Path, required=True)
    parser.add_argument("--raster-lineage-json", type=Path, required=True)
    parser.add_argument(
        "--raster",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help="Repeat for every canonical final-cell raster named by lineage.",
    )
    parser.add_argument("--qa-protocol-version", required=True)
    parser.add_argument("--qa-report-output", type=Path, required=True)
    parser.add_argument("--qa-receipt-output", type=Path, required=True)
    args = parser.parse_args()

    raw_inputs: dict[str, Path] = {
        "source_assets": args.source_assets,
        "dataset_assignments": args.dataset_assignments,
        "usage_records": args.usage_records,
        "annotations": args.annotation_log,
        "binary_training_rows": args.binary_training_rows,
    }
    if args.query_models is not None:
        raw_inputs["query_models"] = args.query_models
    if args.query_records is not None:
        raw_inputs["query_records"] = args.query_records

    try:
        qa_report, records = run_release_qa_from_raw_inputs(raw_inputs)
        annotations = records["annotations"]
        if not all(isinstance(record, AnnotationRecord) for record in annotations):
            raise ReleaseQAError(
                "Annotation raw input did not load as canonical AnnotationRecord values."
            )
        calibration = load_reviewer_calibration_receipt(
            args.reviewer_calibration_receipt
        )
        formal_annotations = tuple(
            record
            for record in annotations
            if record.query_region_id not in set(calibration.query_region_ids)
        )
        pairs = pair_locked_annotations(
            formal_annotations,
            reviewer_a_id=args.reviewer_a_id,
            reviewer_b_id=args.reviewer_b_id,
        )
        agreement = load_json_object(
            args.agreement_json, label="agreement evidence"
        )
        raster_lineage = load_json_object(
            args.raster_lineage_json, label="raster lineage"
        )
        raster_paths = parse_name_path(args.raster, label="raster")
        raster_hashes = {
            name: file_sha256(path) for name, path in raster_paths.items()
        }
        base_receipt = build_release_qa_evidence_manifest(
            qa_report=qa_report,
            pairs=pairs,
            agreement_evidence=agreement,
            raster_lineage=raster_lineage,
            raster_hashes=raster_hashes,
            reviewer_calibration_receipt=calibration,
            qa_protocol_version=args.qa_protocol_version,
        )
        _, receipt, report_path, receipt_path = (
            write_release_qa_artifacts_from_raw(
                qa_report=qa_report,
                base_receipt=base_receipt,
                raw_input_paths=raw_inputs,
                qa_report_path=args.qa_report_output,
                qa_receipt_path=args.qa_receipt_output,
            )
        )
    except (
        ReleaseQAError,
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

    print(f"Release QA ready: {qa_report.ready}")
    print(f"Raw input roles: {', '.join(receipt['raw_input_roles_in_scope'])}")
    print(f"Receipt SHA-256: {receipt['receipt_sha256']}")
    print(f"Wrote QA report: {report_path}")
    print(f"Wrote QA receipt: {receipt_path}")


if __name__ == "__main__":
    main()
