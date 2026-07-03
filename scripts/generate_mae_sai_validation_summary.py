"""Generate the Mae Sai real-data validation status report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.validation import write_real_data_validation_summary  # noqa: E402


def main() -> None:
    """Write the blocked or metric-backed Mae Sai validation summary."""

    parser = argparse.ArgumentParser(
        description="Generate Mae Sai real-data validation status from a file manifest."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_real_data_file_manifest.csv",
        help="Mae Sai file-level manifest CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_validation_summary.md",
        help="Output Markdown validation summary.",
    )
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest, dtype=str).fillna("")
    written = write_real_data_validation_summary(manifest, args.output)
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()
