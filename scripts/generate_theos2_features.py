"""Generate non-ML THEOS-2 land-cover/exposure feature prototypes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.theos2_features import write_theos2_landcover_exposure_features  # noqa: E402


def main() -> None:
    """Write THEOS-2 non-ML optical-context feature rows."""

    parser = argparse.ArgumentParser(
        description="Generate non-ML THEOS-2 land-cover/exposure feature rows."
    )
    parser.add_argument(
        "--selected-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_selected_file_manifest.csv",
        help="Checksum-backed selected THEOS-2 manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "theos2_landcover_exposure_features.csv",
        help="Output feature CSV.",
    )
    args = parser.parse_args()

    written = write_theos2_landcover_exposure_features(args.selected_manifest, args.output)
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()
