"""Generate fixed Mae Sai VV/VH change displays for authority review."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.review_derivative_generator import (  # noqa: E402
    ReviewDerivativeGenerationError,
    build_and_write_review_derivative_candidates,
    validate_review_derivative_candidate_outputs,
)


def main() -> None:
    """Write a new authority-pending candidate directory without overwrite."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--derivative-set-id", required=True)
    for relative, polarization in (
        ("pre", "vv"),
        ("event", "vv"),
        ("pre", "vh"),
        ("event", "vh"),
    ):
        parser.add_argument(f"--{relative}-{polarization}-asset-id", required=True)
        parser.add_argument(
            f"--{relative}-{polarization}",
            type=Path,
            required=True,
            help=f"Governed {relative} {polarization.upper()} dB GeoTIFF.",
        )
    parser.add_argument(
        "--processing-alignment-receipt", type=Path, required=True
    )
    parser.add_argument("--governance-package", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--generated-at-utc")
    parser.add_argument("--fixed-stretch-min-db", type=float, default=-10.0)
    parser.add_argument("--fixed-stretch-max-db", type=float, default=10.0)
    args = parser.parse_args()
    try:
        written = build_and_write_review_derivative_candidates(
            event_id=args.event_id,
            derivative_set_id=args.derivative_set_id,
            pre_vv_asset_id=args.pre_vv_asset_id,
            pre_vv_path=args.pre_vv,
            event_vv_asset_id=args.event_vv_asset_id,
            event_vv_path=args.event_vv,
            pre_vh_asset_id=args.pre_vh_asset_id,
            pre_vh_path=args.pre_vh,
            event_vh_asset_id=args.event_vh_asset_id,
            event_vh_path=args.event_vh,
            processing_alignment_receipt=args.processing_alignment_receipt,
            governance_package=args.governance_package,
            output_directory=args.output_directory,
            generated_at_utc=args.generated_at_utc,
            fixed_stretch_min_db=args.fixed_stretch_min_db,
            fixed_stretch_max_db=args.fixed_stretch_max_db,
        )
        validate_review_derivative_candidate_outputs(args.output_directory)
    except (ReviewDerivativeGenerationError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for label, path in written.as_dict().items():
        print(f"Wrote {label}: {path}")
    print("Status: authority_approval_pending")
    print("Delivery gate: do not create a reviewer bundle until attributable authority approval.")
    print("Safety: decision layer=false; FPPS=false; warning=false")


if __name__ == "__main__":
    main()
