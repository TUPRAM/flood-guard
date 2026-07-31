"""Build residual-registration and receipt-compatible SAR processing evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.registration_evidence import (  # noqa: E402
    RegistrationEvidenceError,
    RegistrationParameters,
    build_and_write_processing_evidence,
)


def main(argv: list[str] | None = None) -> int:
    """Build immutable evidence; return 3 when the measured gate does not pass."""

    parser = argparse.ArgumentParser(description=__doc__)
    for role in ("pre-vv", "pre-vh", "event-vv", "event-vh"):
        parser.add_argument(f"--{role}", required=True, type=Path)
        parser.add_argument(f"--{role}-asset-id", required=True)
    parser.add_argument("--pre-layover-shadow-mask", type=Path)
    parser.add_argument("--event-layover-shadow-mask", type=Path)
    parser.add_argument("--source-timestamp-utc", required=True)
    parser.add_argument("--processing-software", default="ESA SNAP GPT")
    parser.add_argument("--processing-software-version", required=True)
    parser.add_argument(
        "--rtc-terrain-correction-method",
        required=True,
        help="Specific pinned graph/operator description; 'unknown' is rejected.",
    )
    parser.add_argument(
        "--resampling-method",
        default="bilinear reprojection of linear Gamma0 followed by dB conversion",
    )
    parser.add_argument("--window-size-pixels", type=int, default=256)
    parser.add_argument("--minimum-valid-fraction", type=float, default=0.80)
    parser.add_argument("--maximum-search-shift-pixels", type=int, default=3)
    parser.add_argument("--minimum-psr", type=float, default=6.0)
    parser.add_argument("--minimum-windows-per-polarization", type=int, default=3)
    parser.add_argument(
        "--maximum-polarization-disagreement-pixels", type=float, default=0.35
    )
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        outputs = build_and_write_processing_evidence(
            pre_vv_path=args.pre_vv,
            pre_vh_path=args.pre_vh,
            event_vv_path=args.event_vv,
            event_vh_path=args.event_vh,
            asset_ids={
                "pre_vv": args.pre_vv_asset_id,
                "pre_vh": args.pre_vh_asset_id,
                "event_vv": args.event_vv_asset_id,
                "event_vh": args.event_vh_asset_id,
            },
            pre_layover_shadow_mask_path=args.pre_layover_shadow_mask,
            event_layover_shadow_mask_path=args.event_layover_shadow_mask,
            output_directory=args.output_directory,
            source_timestamp_utc=args.source_timestamp_utc,
            processing_software=args.processing_software,
            processing_software_version=args.processing_software_version,
            rtc_terrain_correction_method=args.rtc_terrain_correction_method,
            resampling_method=args.resampling_method,
            parameters=RegistrationParameters(
                window_size_pixels=args.window_size_pixels,
                minimum_valid_fraction=args.minimum_valid_fraction,
                maximum_search_shift_pixels=args.maximum_search_shift_pixels,
                minimum_peak_to_sidelobe_ratio=args.minimum_psr,
                minimum_windows_per_polarization=(
                    args.minimum_windows_per_polarization
                ),
                maximum_polarization_disagreement_pixels=(
                    args.maximum_polarization_disagreement_pixels
                ),
            ),
        )
    except (RegistrationEvidenceError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    registration = json.loads(outputs.registration_evidence.read_text(encoding="utf-8"))
    result = {
        "processing_evidence_csv": str(outputs.processing_evidence_csv),
        "registration_evidence": str(outputs.registration_evidence),
        "build_manifest": str(outputs.build_manifest),
        "registration_error_pixels": registration["registration_error_pixels"],
        "registration_gate_passed": registration["registration_gate_passed"],
        "query_model_only": True,
        "eligible_for_fpps": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if bool(registration["registration_gate_passed"]) else 3


if __name__ == "__main__":
    raise SystemExit(main())
