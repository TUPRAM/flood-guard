"""Build a blocked file-level Mae Sai real-data planning manifest."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.ingestion import (  # noqa: E402
    default_mae_sai_file_manifest_sources,
    write_ingestion_manifest,
)


def main() -> None:
    """Write the blocked Mae Sai file-level ingestion manifest."""

    output_path = REPO_ROOT / "outputs" / "mae_sai_real_data_file_manifest.csv"
    written = write_ingestion_manifest(
        default_mae_sai_file_manifest_sources(),
        output_path,
    )
    print(f"Wrote {written}")


if __name__ == "__main__":
    main()

