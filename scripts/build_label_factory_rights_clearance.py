"""Build a fail-closed, immutable label-factory rights-clearance package."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.rights_clearance import (  # noqa: E402
    RightsClearanceError,
    build_rights_clearance_package,
    load_rights_owner_decision,
    validate_rights_clearance_package,
)


def main() -> None:
    """Validate the parent package and write a new clearance package once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending-package", type=Path, required=True)
    parser.add_argument(
        "--decision-json",
        type=Path,
        required=True,
        help="Strict floodguard_rights_owner_decision_v1 JSON; no credentials.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        decision = load_rights_owner_decision(args.decision_json)
        output = build_rights_clearance_package(
            args.pending_package,
            args.output,
            decision,
        )
        seal = validate_rights_clearance_package(output)
    except (RightsClearanceError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote immutable rights-clearance package: {output}")
    print(f"Package seal SHA-256: {seal['seal_sha256']}")
    print("Redistribution: YES_WITH_CONDITIONS; provider notices remain mandatory")
    print("Still blocked: reference authority, reviewers, adjudicator, validation")
    print("Safety: query/reviewer workflow only; FPPS=false; warning=false")


if __name__ == "__main__":
    main()
