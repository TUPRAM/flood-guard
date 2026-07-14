"""Audit FloodGuard Reviewer A synthetic-practice exports."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.practice_audit import (  # noqa: E402
    PracticeAuditError,
    audit_reviewer_practice_exports,
)


def main() -> None:
    """Run the fail-closed practice audit and report its learning-only status."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-json", type=Path, required=True)
    parser.add_argument("--draft-json", type=Path, required=True)
    parser.add_argument("--cells-csv", type=Path, required=True)
    parser.add_argument(
        "--synthetic-package",
        type=Path,
        required=True,
        help=(
            "Checksum-governed synthetic learning or synthetic remediation "
            "package directory."
        ),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="New or empty directory for practice-only audit artifacts.",
    )
    parser.add_argument(
        "--audited-at-utc",
        required=True,
        help="Timezone-aware ISO-8601 audit timestamp, normally ending in Z.",
    )
    args = parser.parse_args()
    try:
        audited_at = datetime.fromisoformat(
            args.audited_at_utc.replace("Z", "+00:00")
        )
        output = audit_reviewer_practice_exports(
            args.session_json,
            args.draft_json,
            args.cells_csv,
            args.synthetic_package,
            args.output_directory,
            audited_at_utc=audited_at,
        )
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, PracticeAuditError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"Wrote practice audit: {output}")
    print(f"Validation status: {summary['validation_status']}")
    print(f"Next step: {summary['next_step_status']}")
    print(f"Summary SHA-256: {summary['summary_sha256']}")
    print("Formal calibration / training / FPPS / warning eligibility: false")


if __name__ == "__main__":
    main()
