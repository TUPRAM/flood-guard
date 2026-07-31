"""Score named reviewers on fixed calibration truth and write a passing receipt."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.annotations import (  # noqa: E402
    AnnotationValidationError,
    load_annotation_log,
)
from floodguard.label_factory.calibration import (  # noqa: E402
    DEFAULT_CALIBRATION_THRESHOLDS,
    ReviewerCalibrationError,
    build_reviewer_calibration_receipt,
    write_reviewer_calibration_receipt,
)


def main() -> None:
    """Bind exact files, calculate metrics, fail on gates, and write once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation-log", type=Path, required=True)
    parser.add_argument("--calibration-query-manifest", type=Path, required=True)
    parser.add_argument(
        "--reviewer-cells",
        action="append",
        required=True,
        metavar="REVIEWER_ID=PATH",
    )
    parser.add_argument(
        "--reviewer-cell-manifest",
        action="append",
        required=True,
        metavar="REVIEWER_ID=PATH",
    )
    parser.add_argument("--reference-cells", type=Path, required=True)
    parser.add_argument("--reference-manifest", type=Path, required=True)
    parser.add_argument("--query-strata", type=Path, required=True)
    parser.add_argument("--protocol-version", required=True)
    parser.add_argument("--taxonomy-version", default="flood_label_v1")
    parser.add_argument("--formal-review-not-before-utc", required=True)
    parser.add_argument("--assumptions", required=True)
    parser.add_argument("--boundary-tolerance-m", type=float, default=20.0)
    parser.add_argument(
        "--temporary-flood-dice-threshold",
        type=float,
        default=DEFAULT_CALIBRATION_THRESHOLDS["temporary_flood_dice"],
    )
    parser.add_argument(
        "--kappa-threshold",
        type=float,
        default=DEFAULT_CALIBRATION_THRESHOLDS["cohen_kappa"],
    )
    parser.add_argument(
        "--boundary-f1-threshold",
        type=float,
        default=DEFAULT_CALIBRATION_THRESHOLDS["mean_boundary_f1"],
    )
    parser.add_argument(
        "--critical-stratum-dice-threshold",
        type=float,
        default=DEFAULT_CALIBRATION_THRESHOLDS["critical_stratum_dice"],
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        formal_not_before = datetime.fromisoformat(
            args.formal_review_not_before_utc.replace("Z", "+00:00")
        )
        receipt = build_reviewer_calibration_receipt(
            load_annotation_log(args.annotation_log),
            args.calibration_query_manifest,
            reviewer_cell_paths=_parse_name_path(args.reviewer_cells, "reviewer cells"),
            reviewer_cell_manifest_paths=_parse_name_path(
                args.reviewer_cell_manifest, "reviewer cell manifest"
            ),
            reference_cell_path=args.reference_cells,
            reference_manifest_path=args.reference_manifest,
            query_strata=args.query_strata,
            protocol_version=args.protocol_version,
            taxonomy_version=args.taxonomy_version,
            formal_review_not_before_utc=formal_not_before,
            assumptions=args.assumptions,
            thresholds={
                "temporary_flood_dice": args.temporary_flood_dice_threshold,
                "cohen_kappa": args.kappa_threshold,
                "mean_boundary_f1": args.boundary_f1_threshold,
                "critical_stratum_dice": args.critical_stratum_dice_threshold,
            },
            boundary_tolerance_m=args.boundary_tolerance_m,
        )
        write_reviewer_calibration_receipt(receipt, args.output)
    except (
        ReviewerCalibrationError,
        AnnotationValidationError,
        OSError,
        ValueError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Calibration passed for: {', '.join(receipt.reviewer_ids)}")
    print(f"Calibration queries: {len(receipt.query_region_ids)}")
    print(
        "Formal review not before: "
        + receipt.formal_review_not_before_utc.isoformat().replace("+00:00", "Z")
    )
    print(f"Wrote self-hashed receipt: {args.output.name}")


def _parse_name_path(values: list[str], label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        name = name.strip()
        raw_path = raw_path.strip()
        if not separator or not name or not raw_path or name in result:
            raise ReviewerCalibrationError(
                f"Each {label} must be unique REVIEWER_ID=PATH."
            )
        result[name] = Path(raw_path)
    return result


if __name__ == "__main__":
    main()
