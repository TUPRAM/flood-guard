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
    sources = _with_cdse_acquisition_rows(sources)
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
            "confirm Sentinel Asia product terms before real validation or ML-label "
            "use; repeat manual QA if provider terms require"
        ),
    }
    remaining = source_frame[
        source_frame["candidate_use"].astype(str) != "reference flood mask for validation"
    ]
    return pd.concat([pd.DataFrame([candidate]), remaining], ignore_index=True)


def _with_cdse_acquisition_rows(source_frame: pd.DataFrame) -> pd.DataFrame:
    acquisition_path = REPO_ROOT / "outputs" / "cdse_mae_sai_acquisition_manifest.csv"
    if not acquisition_path.exists():
        return source_frame
    acquisition = pd.read_csv(acquisition_path, dtype=str).fillna("")
    if acquisition.empty:
        return source_frame

    frame = source_frame.copy()
    for _, row in acquisition.iterrows():
        product_id = row.get("product_id", "")
        if not product_id:
            continue
        matches = frame["product_id"].astype(str) == product_id
        if not matches.any():
            continue
        source_license_status = row.get("source_license_status", "")
        normalized_license = (
            "confirmed"
            if source_license_status == "confirmed_copernicus_sentinel_legal_notice"
            else source_license_status
        )
        frame.loc[matches, "source_license_status"] = normalized_license or "unresolved"
        frame.loc[matches, "reference_mask_status"] = row.get(
            "reference_mask_status",
            "unresolved",
        )
        download_status = row.get("download_status", "unknown")
        if row.get("sha256_status") == "recorded":
            frame.loc[matches, "local_path"] = row.get("local_path_hint", "not_acquired")
            frame.loc[matches, "sha256"] = row.get("sha256", "not_acquired")
            frame.loc[matches, "next_action"] = (
                "reference-mask gate remains required before real non-ML SAR baseline"
            )
        else:
            frame.loc[matches, "local_path"] = "not_acquired"
            frame.loc[matches, "sha256"] = "not_acquired"
            frame.loc[matches, "next_action"] = (
                f"CDSE acquisition row is not file-ready yet: {download_status}"
            )
    return frame


if __name__ == "__main__":
    main()
