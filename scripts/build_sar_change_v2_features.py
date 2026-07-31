"""Build immutable cell-level sar_change_v2 features from aligned dB GeoTIFFs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.sar_change_features import (  # noqa: E402
    SarChangeFeatureError,
    build_and_write_sar_change_v2_features,
)


def main() -> None:
    """Validate grid identity, extract features, and publish new artifacts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pre-vv",
        type=Path,
        required=True,
        help="Calibrated pre-event VV dB single-band GeoTIFF.",
    )
    parser.add_argument(
        "--event-vv",
        type=Path,
        required=True,
        help="Calibrated event-time VV dB single-band GeoTIFF.",
    )
    parser.add_argument(
        "--pre-vh",
        type=Path,
        required=True,
        help="Calibrated pre-event VH dB single-band GeoTIFF.",
    )
    parser.add_argument(
        "--event-vh",
        type=Path,
        required=True,
        help="Calibrated event-time VH dB single-band GeoTIFF.",
    )
    parser.add_argument(
        "--query-manifest",
        type=Path,
        required=True,
        help="Canonical query-region CSV produced by the label-factory grid builder.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="New output directory; existing paths are never overwritten.",
    )
    parser.add_argument(
        "--created-at-utc",
        help="Optional timezone-aware ISO timestamp for reproducible test runs.",
    )
    args = parser.parse_args()
    try:
        written = build_and_write_sar_change_v2_features(
            pre_vv_path=args.pre_vv,
            event_vv_path=args.event_vv,
            pre_vh_path=args.pre_vh,
            event_vh_path=args.event_vh,
            query_manifest_path=args.query_manifest,
            output_directory=args.output_directory,
            created_at_utc=args.created_at_utc,
        )
    except (SarChangeFeatureError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for label, path in written.as_dict().items():
        print(f"Wrote {label}: {path}")
    print("Safety: query-model-only; decision layer=false; FPPS=false; warning=false")


if __name__ == "__main__":
    main()
