"""Inspect the external Sentinel Asia AIT-VAP001-TH reference candidate."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.ait_reference_candidate import (  # noqa: E402
    inspect_ait_reference_candidate,
    write_ait_reference_candidate,
)


def main(argv: list[str] | None = None) -> int:
    """Build the sanitized, non-authoritative AIT candidate receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument(
        "--catalog-evidence",
        type=Path,
        required=True,
        help="Saved Sentinel Asia event-page bytes used for product identity.",
    )
    parser.add_argument(
        "--terms-evidence",
        type=Path,
        required=True,
        help="Saved Sentinel Asia site-policy bytes used for terms review.",
    )
    parser.add_argument(
        "--study-area",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_admin_context.geojson",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "ait_vap001_reference_candidate.json",
    )
    parser.add_argument(
        "--inspected-at",
        default=None,
        help="Optional timezone-aware timestamp for deterministic regeneration.",
    )
    args = parser.parse_args(argv)
    inspected_at = (
        datetime.fromisoformat(args.inspected_at.replace("Z", "+00:00"))
        if args.inspected_at
        else None
    )
    receipt = inspect_ait_reference_candidate(
        args.archive,
        args.study_area,
        catalog_evidence_path=args.catalog_evidence,
        terms_evidence_path=args.terms_evidence,
        inspected_at_utc=inspected_at,
    )
    written = write_ait_reference_candidate(receipt, args.output)
    print(f"Wrote {written}")
    print(
        "Status: blocked_external_permission_and_scientific_review; "
        "processing_allowed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
