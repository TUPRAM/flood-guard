"""Build the offline, synthetic-only FloodGuard Reviewer A practice workspace."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.reviewer_workspace import (  # noqa: E402
    ReviewerWorkspaceError,
    build_reviewer_practice_workspace,
)


def main() -> None:
    """Validate the synthetic package and create a write-once local workbench."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-directory",
        type=Path,
        required=True,
        help="Verified synthetic_cases_v1 directory.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="New or empty directory for the practice workspace.",
    )
    parser.add_argument(
        "--reviewer-display-name",
        required=True,
        help="Display name shown locally; this is not a formal reviewer role id.",
    )
    parser.add_argument(
        "--created-at-utc",
        required=True,
        help="Timezone-aware ISO-8601 creation timestamp, normally ending in Z.",
    )
    parser.add_argument(
        "--formal-hold-path",
        "--formal-hold",
        dest="formal_hold_path",
        type=Path,
        help="Optional immutable floodguard.formal_review_hold.v1 JSON file.",
    )
    args = parser.parse_args()
    try:
        created_at = datetime.fromisoformat(
            args.created_at_utc.replace("Z", "+00:00")
        )
        root = build_reviewer_practice_workspace(
            args.source_directory,
            args.output_directory,
            reviewer_display_name=args.reviewer_display_name,
            created_at_utc=created_at,
            formal_hold_path=args.formal_hold_path,
        )
    except (OSError, ValueError, ReviewerWorkspaceError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"Wrote Reviewer A practice workspace: {root}")
    print(f"Open locally: {root / 'index.html'}")
    print("Practice-only / formal-review / training / FPPS / warning eligibility: false")


if __name__ == "__main__":
    main()
