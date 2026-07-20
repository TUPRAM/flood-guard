"""Build or validate an immutable reviewer-calibration membership release."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.calibration_release import (  # noqa: E402
    CalibrationReleaseError,
    build_calibration_release,
    validate_calibration_release_package,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser(
        "build", help="Validate approved inputs and freeze one new release."
    )
    build.add_argument(
        "--reference-authority-approval-package", type=Path, required=True
    )
    build.add_argument("--canonical-grid-directory", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--release-id", required=True)
    build.add_argument(
        "--created-at-utc",
        help="Optional exact YYYY-MM-DDTHH:MM:SSZ for a reproducible build.",
    )

    validate = commands.add_parser(
        "validate", help="Revalidate every copied byte, role, and membership."
    )
    validate.add_argument("--package", type=Path, required=True)
    return parser


def main() -> None:
    """Execute one immutable build or fail-closed validation."""

    args = _parser().parse_args()
    try:
        if args.command == "build":
            paths = build_calibration_release(
                reference_authority_approval_package=(
                    args.reference_authority_approval_package
                ),
                canonical_grid_directory=args.canonical_grid_directory,
                output_directory=args.output,
                release_id=args.release_id,
                created_at_utc=args.created_at_utc,
            )
            receipt = validate_calibration_release_package(paths.directory)
            print(f"Wrote immutable calibration release: {paths.directory.name}")
        else:
            receipt = validate_calibration_release_package(args.package)
            print(f"Validated immutable calibration release: {args.package.name}")
    except (CalibrationReleaseError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    selection = receipt["selection_contract"]
    print(f"Release id: {receipt['release_id']}")
    print(f"Receipt SHA-256: {receipt['receipt_sha256']}")
    print(
        "Membership: calibration="
        f"{selection['calibration_query_count']}; "
        f"fresh-retest={selection['fresh_retest_query_count']}; disjoint=true"
    )
    print(
        "Safety: bundle=false; calibration-execution=false; formal-review=false; "
        "training=false; evaluation=false; decision=false; FPPS=false; warning=false"
    )


if __name__ == "__main__":
    main()
