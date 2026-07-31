"""Build or validate an immutable FloodGuard human-role evidence package."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.human_roles import (  # noqa: E402
    HumanRolePackageError,
    build_human_role_package,
    validate_human_role_package,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="Validate inputs and freeze a new package.")
    build.add_argument("--request-json", type=Path, required=True)
    build.add_argument("--evidence-root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--parent-package", type=Path)
    build.add_argument("--calibration-receipt", type=Path)

    validate = commands.add_parser("validate", help="Revalidate a frozen package.")
    validate.add_argument("--package", type=Path, required=True)
    return parser


def main() -> None:
    """Execute the fail-closed package build or validation command."""

    args = _parser().parse_args()
    try:
        if args.command == "build":
            package = build_human_role_package(
                args.request_json,
                evidence_root=args.evidence_root,
                output_dir=args.output,
                calibration_receipt_path=args.calibration_receipt,
                parent_package=args.parent_package,
            )
            manifest = validate_human_role_package(package)
            print(f"Wrote immutable human-role package: {package}")
        else:
            manifest = validate_human_role_package(args.package)
            print(f"Validated immutable human-role package: {args.package}")
    except (HumanRolePackageError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"Package id: {manifest['package_id']}")
    print(f"Manifest SHA-256: {manifest['manifest_sha256']}")
    print(f"Formal review authorized: {str(manifest['formal_review_authorized']).lower()}")
    print(
        "Genuinely blinded double review: "
        f"{str(manifest['genuinely_blinded_double_review']).lower()}"
    )
    print("Safety: training=false; decision=false; FPPS=false; warning=false")
    print("Limitation: evidence consistency is not identity or expertise certification")


if __name__ == "__main__":
    main()
