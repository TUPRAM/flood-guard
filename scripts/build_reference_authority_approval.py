"""Build or validate a fail-closed Reference Authority design decision."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.reference_authority_approval import (  # noqa: E402
    ReferenceAuthorityApprovalError,
    build_reference_authority_approval_package,
    validate_reference_authority_approval_package,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser(
        "build", help="Validate exact inputs and freeze a new decision package."
    )
    build.add_argument("--request-json", type=Path, required=True)
    build.add_argument("--evidence-root", type=Path, required=True)
    build.add_argument("--human-role-package", type=Path, required=True)
    build.add_argument("--calibration-reserve-design-package", type=Path, required=True)
    build.add_argument("--reference-procedure", type=Path, required=True)
    build.add_argument("--review-derivative-lineage-receipt", type=Path)
    build.add_argument("--output", type=Path, required=True)

    validate = commands.add_parser(
        "validate", help="Revalidate every copied byte and binding in a package."
    )
    validate.add_argument("--package", type=Path, required=True)
    return parser


def main() -> None:
    """Execute one immutable build or fail-closed validation."""

    args = _parser().parse_args()
    try:
        if args.command == "build":
            package = build_reference_authority_approval_package(
                args.request_json,
                evidence_root=args.evidence_root,
                human_role_package=args.human_role_package,
                calibration_reserve_design_package=(
                    args.calibration_reserve_design_package
                ),
                reference_procedure_path=args.reference_procedure,
                review_derivative_lineage_receipt_path=(
                    args.review_derivative_lineage_receipt
                ),
                output_directory=args.output,
            )
            manifest = validate_reference_authority_approval_package(package)
            print(f"Wrote immutable Reference Authority package: {package.name}")
        else:
            manifest = validate_reference_authority_approval_package(args.package)
            print(
                f"Validated immutable Reference Authority package: {args.package.name}"
            )
    except (ReferenceAuthorityApprovalError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    scope = manifest["authorization_scope"]
    print(f"Package id: {manifest['package_id']}")
    print(f"Approval status: {manifest['approval_status']}")
    print(f"Manifest SHA-256: {manifest['manifest_sha256']}")
    print(
        "Separate reserve/reference construction: "
        + str(scope["may_start_separate_canonical_reserve_construction"]).lower()
    )
    print(
        "Safety: bundle=false; calibration=false; formal-review=false; "
        "training=false; decision=false; FPPS=false; warning=false"
    )
    print(
        "Limitation: local bytes and declared attribution are not independent "
        "identity, expertise, signature, or semantic verification"
    )


if __name__ == "__main__":
    main()
