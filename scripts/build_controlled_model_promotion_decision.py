"""Create a signed promotion policy or report-only model recommendation."""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys

from floodguard.model_promotion import (
    ModelPromotionError,
    build_model_promotion_recommendation,
    write_signed_model_promotion_policy,
)


def _timestamp(value: str) -> datetime:
    if not value.endswith("Z"):
        raise argparse.ArgumentTypeError("timestamp must end in Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timestamp is invalid") from exc


def _environment_key(variable: str) -> bytes:
    value = os.environ.get(variable)
    if value is None:
        raise ModelPromotionError(
            f"Required signing-key environment variable is missing: {variable}"
        )
    return value.encode("utf-8")


def _trusted_keys(values: list[str]) -> dict[str, bytes]:
    keys: dict[str, bytes] = {}
    for value in values:
        if "=" not in value:
            raise ModelPromotionError(
                "Trusted keys must use KEY_ID=ENVIRONMENT_VARIABLE syntax."
            )
        key_id, variable = value.split("=", 1)
        if not key_id or not variable or key_id in keys:
            raise ModelPromotionError(
                "Trusted key declarations must be non-empty and unique."
            )
        keys[key_id] = _environment_key(variable)
    if not keys:
        raise ModelPromotionError("At least one trusted signing key is required.")
    return keys


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build immutable, HMAC-signed report-only model promotion evidence. "
            "No command grants decision-layer or operational authority."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    policy = subparsers.add_parser("policy", help="write a predeclared signed policy")
    policy.add_argument("--output", type=Path, required=True)
    policy.add_argument("--policy-id", required=True)
    policy.add_argument("--experiment-id", required=True)
    policy.add_argument("--study-area", required=True)
    policy.add_argument("--issued-at-utc", type=_timestamp, required=True)
    policy.add_argument("--expires-at-utc", type=_timestamp, required=True)
    policy.add_argument("--minimum-iou", type=float, required=True)
    policy.add_argument("--minimum-f1-dice", type=float, required=True)
    policy.add_argument("--minimum-precision", type=float, required=True)
    policy.add_argument("--minimum-recall", type=float, required=True)
    policy.add_argument(
        "--maximum-absolute-area-error-ratio", type=float, required=True
    )
    policy.add_argument("--maximum-brier-score", type=float, required=True)
    policy.add_argument(
        "--maximum-expected-calibration-error", type=float, required=True
    )
    policy.add_argument("--required-error-category", action="append", required=True)
    policy.add_argument("--minimum-error-category-cell-count", type=int, required=True)
    policy.add_argument("--tie-break", action="append", required=True)
    policy.add_argument("--metrics-file", required=True)
    policy.add_argument("--calibration-file", required=True)
    policy.add_argument("--error-categories-file", required=True)
    policy.add_argument("--runtime-file", required=True)
    policy.add_argument("--signing-key-id", required=True)
    policy.add_argument("--signing-key-env", required=True)

    recommend = subparsers.add_parser(
        "recommend", help="verify evidence and write a report-only recommendation"
    )
    recommend.add_argument("--policy", type=Path, required=True)
    recommend.add_argument("--result-receipt", type=Path, required=True)
    recommend.add_argument("--metrics", type=Path, required=True)
    recommend.add_argument("--calibration", type=Path, required=True)
    recommend.add_argument("--error-categories", type=Path, required=True)
    recommend.add_argument("--runtime", type=Path, required=True)
    recommend.add_argument("--output", type=Path, required=True)
    recommend.add_argument(
        "--trusted-key",
        action="append",
        required=True,
        metavar="KEY_ID=ENVIRONMENT_VARIABLE",
    )
    recommend.add_argument("--signing-key-id", required=True)
    recommend.add_argument("--signing-key-env", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "policy":
            path = write_signed_model_promotion_policy(
                args.output,
                policy_id=args.policy_id,
                experiment_id=args.experiment_id,
                study_area=args.study_area,
                issued_at_utc=args.issued_at_utc,
                expires_at_utc=args.expires_at_utc,
                thresholds={
                    "minimum_iou": args.minimum_iou,
                    "minimum_f1_dice": args.minimum_f1_dice,
                    "minimum_precision": args.minimum_precision,
                    "minimum_recall": args.minimum_recall,
                    "maximum_absolute_area_error_ratio": (
                        args.maximum_absolute_area_error_ratio
                    ),
                    "maximum_brier_score": args.maximum_brier_score,
                    "maximum_expected_calibration_error": (
                        args.maximum_expected_calibration_error
                    ),
                },
                required_error_categories=args.required_error_category,
                minimum_error_category_cell_count=(
                    args.minimum_error_category_cell_count
                ),
                tie_break_order=args.tie_break,
                expected_artifact_filenames={
                    "metrics": args.metrics_file,
                    "calibration": args.calibration_file,
                    "error_categories": args.error_categories_file,
                    "runtime": args.runtime_file,
                },
                signing_key_id=args.signing_key_id,
                signing_key=_environment_key(args.signing_key_env),
            )
        else:
            path = build_model_promotion_recommendation(
                policy_path=args.policy,
                result_receipt_path=args.result_receipt,
                artifact_paths={
                    "metrics": args.metrics,
                    "calibration": args.calibration,
                    "error_categories": args.error_categories,
                    "runtime": args.runtime,
                },
                signing_keys=_trusted_keys(args.trusted_key),
                output_path=args.output,
                signing_key_id=args.signing_key_id,
                signing_key=_environment_key(args.signing_key_env),
            )
    except ModelPromotionError as exc:
        parser.error(str(exc))
    print(path.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
