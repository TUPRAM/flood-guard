"""Freeze an expert/adjudicated reviewer-calibration reference exactly once."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.calibration import (  # noqa: E402
    ReviewerCalibrationError,
    write_calibration_reference_artifacts,
)


def main() -> None:
    """Validate canonical cells and write their self-hashed reference manifest."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-cells-input", type=Path, required=True)
    parser.add_argument("--calibration-query-manifest", type=Path, required=True)
    parser.add_argument("--reference-id", required=True)
    parser.add_argument(
        "--authority-type",
        required=True,
        choices=("expert_consensus", "adjudicated"),
    )
    parser.add_argument("--authority-id", required=True)
    parser.add_argument("--protocol-version", required=True)
    parser.add_argument("--taxonomy-version", default="flood_label_v1")
    parser.add_argument("--created-at-utc", required=True)
    parser.add_argument("--assumptions", required=True)
    parser.add_argument("--cells-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        created_at = datetime.fromisoformat(
            args.created_at_utc.replace("Z", "+00:00")
        )
        outputs = write_calibration_reference_artifacts(
            args.reference_cells_input,
            args.calibration_query_manifest,
            reference_id=args.reference_id,
            authority_type=args.authority_type,
            authority_id=args.authority_id,
            protocol_version=args.protocol_version,
            taxonomy_version=args.taxonomy_version,
            created_at_utc=created_at,
            assumptions=args.assumptions,
            cells_output_path=args.cells_output,
            manifest_output_path=args.manifest_output,
        )
    except (ReviewerCalibrationError, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote immutable calibration reference cells: {outputs.cells}")
    print(f"Wrote self-hashed calibration reference manifest: {outputs.manifest}")
    print("Training/decision/FPPS/warning eligibility: false")


if __name__ == "__main__":
    main()
