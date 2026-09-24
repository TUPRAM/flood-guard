"""Acquire or register the Mae Sai Sentinel-2 reference-candidate SAFE outside Git."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.cdse_download import DEFAULT_EXTERNAL_DATA_DIR  # noqa: E402
from floodguard.cdse_sentinel2_reference import (  # noqa: E402
    build_sentinel2_reference_acquisition_manifest,
)


def main(argv: list[str] | None = None) -> int:
    """Run credential-gated acquisition and write the manifest CSV."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "cdse_mae_sai_sentinel2_reference_acquisition_manifest.csv",
    )
    parser.add_argument("--external-data-dir", type=Path, default=DEFAULT_EXTERNAL_DATA_DIR)
    parser.add_argument("--register-existing", action="store_true",
                        help="Validate and hash an existing SAFE ZIP without credentials or download.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retrieved-at", default=None)
    args = parser.parse_args(argv)

    frame = build_sentinel2_reference_acquisition_manifest(
        external_data_dir=args.external_data_dir,
        dry_run=args.dry_run,
        register_existing=args.register_existing,
        retrieved_at_utc=args.retrieved_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False, lineterminator="\n")
    print(f"Wrote {args.output}: {frame.iloc[0]['download_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
