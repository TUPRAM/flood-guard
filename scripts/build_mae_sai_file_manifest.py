"""Build a blocked file-level Mae Sai real-data planning manifest."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

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
    sources = _with_public_reference_candidate(default_mae_sai_file_manifest_sources())
    written = write_ingestion_manifest(
        sources,
        output_path,
    )
    print(f"Wrote {written}")


def _with_public_reference_candidate(source_frame: pd.DataFrame) -> pd.DataFrame:
    inspection_path = REPO_ROOT / "outputs" / "public_reference_file_inspection_manifest.csv"
    if not inspection_path.exists():
        return source_frame
    inspection = pd.read_csv(inspection_path, dtype=str).fillna("")
    if inspection.empty:
        return source_frame
    row = inspection.iloc[0]
    if row.get("mae_sai_point_in_bbox", "").lower() != "true":
        return source_frame
    candidate = {
        "source_name": "Sentinel Asia MBRSC Mae Sai public shapefile candidate",
        "study_area": "Chiang Rai / Mae Sai 2024",
        "source_url": row.get("source_url", ""),
        "candidate_use": "reference flood mask for validation",
        "geometry_access_status": "available",
        "license_status": "unresolved",
        "redistribution_status": "unresolved",
        "product_id": "SENTINEL-ASIA-MBRSC-THAILAND-FLOOD-MAP-SHP",
        "local_path": row.get("local_path_hint", "not_acquired"),
        "sha256": row.get("sha256", "not_acquired"),
        "source_license_status": "unresolved",
        "reference_mask_status": "candidate_geometry_inspected_not_cleared",
        "next_action": (
            "confirm Sentinel Asia product terms and geometry quality before real "
            "validation or ML-label use"
        ),
    }
    remaining = source_frame[
        source_frame["candidate_use"].astype(str) != "reference flood mask for validation"
    ]
    return pd.concat([pd.DataFrame([candidate]), remaining], ignore_index=True)


if __name__ == "__main__":
    main()
