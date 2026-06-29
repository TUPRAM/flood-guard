"""Metadata-first real-data ingestion planning helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

INGESTION_REQUIRED_COLUMNS: tuple[str, ...] = (
    "source_name",
    "study_area",
    "source_url",
    "candidate_use",
    "geometry_access_status",
    "license_status",
    "redistribution_status",
    "next_action",
)

INGESTION_OUTPUT_COLUMNS: tuple[str, ...] = (
    *INGESTION_REQUIRED_COLUMNS,
    "ingestion_stage",
    "download_permitted_by_skeleton",
    "ready_for_processing",
    "blocked_reason",
)


class IngestionPlanError(ValueError):
    """Raised when metadata-first ingestion planning inputs are invalid."""


def default_reference_mask_sources() -> pd.DataFrame:
    """Return the initial reference-mask source rows for metadata-only planning."""

    return pd.DataFrame(
        [
            {
                "source_name": "UNOSAT/UNITAR Mae Sai reference target",
                "study_area": "Chiang Rai / Mae Sai 2024",
                "source_url": "https://unosat.org/products/3991",
                "candidate_use": "reference flood mask target",
                "geometry_access_status": "unresolved",
                "license_status": "unresolved",
                "redistribution_status": "unresolved",
                "next_action": "confirm GIS geometry access and redistribution terms",
            },
            {
                "source_name": "GISTDA official flood product candidate",
                "study_area": "Chiang Rai / Mae Sai 2024",
                "source_url": "https://www.gistda.or.th/",
                "candidate_use": "official flood reference candidate",
                "geometry_access_status": "unresolved",
                "license_status": "unresolved",
                "redistribution_status": "unresolved",
                "next_action": "identify event-specific product and license terms",
            },
            {
                "source_name": "International Charter Activation 1004",
                "study_area": "Hat Yai / Songkhla 2025",
                "source_url": (
                    "https://disasterscharter.org/activations/"
                    "flood-in-thailand-activation-1004-"
                ),
                "candidate_use": "event-specific crisis mapping candidate",
                "geometry_access_status": "unresolved",
                "license_status": "unresolved",
                "redistribution_status": "unresolved",
                "next_action": "confirm product geometry access and attribution terms",
            },
            {
                "source_name": "Sentinel Asia Southern Thailand 2025",
                "study_area": "Hat Yai / Songkhla 2025",
                "source_url": "https://sentinel-asia.org/EO/2025/article20251119TH.html",
                "candidate_use": "event detected-water or flood-proxy context",
                "geometry_access_status": "unresolved",
                "license_status": "unresolved",
                "redistribution_status": "unresolved",
                "next_action": "confirm product file access and redistribution terms",
            },
            {
                "source_name": "Academic or manual reference mask",
                "study_area": "Chiang Rai / Mae Sai 2024; Hat Yai / Songkhla 2025",
                "source_url": "to be identified",
                "candidate_use": "fallback validation or manual reference candidate",
                "geometry_access_status": "not_identified",
                "license_status": "unresolved",
                "redistribution_status": "unresolved",
                "next_action": "search only after official/event sources are logged",
            },
        ]
    )


def build_ingestion_manifest(source_frame: pd.DataFrame) -> pd.DataFrame:
    """Build a metadata-only ingestion manifest without permitting downloads."""

    _validate_columns(source_frame, INGESTION_REQUIRED_COLUMNS, "source")
    frame = source_frame.copy()
    for column in INGESTION_REQUIRED_COLUMNS:
        frame[column] = frame[column].astype(str).str.strip()
        if frame[column].eq("").any():
            raise IngestionPlanError(f"Column {column} must not contain blank values.")

    frame["ingestion_stage"] = "metadata_only"
    frame["download_permitted_by_skeleton"] = False
    frame["ready_for_processing"] = False
    frame["blocked_reason"] = frame.apply(_blocked_reason, axis=1)
    return frame.loc[:, INGESTION_OUTPUT_COLUMNS]


def write_ingestion_manifest(
    source_frame: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Write a metadata-only ingestion manifest CSV and return its path."""

    manifest = build_ingestion_manifest(source_frame)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(target, index=False)
    return target


def _blocked_reason(row: pd.Series) -> str:
    blockers: list[str] = []
    if row["geometry_access_status"] not in {"confirmed", "available"}:
        blockers.append("geometry access not confirmed")
    if row["license_status"] != "confirmed":
        blockers.append("license not confirmed")
    if row["redistribution_status"] not in {"redistributable", "reference_only"}:
        blockers.append("redistribution status unresolved")
    blockers.append("metadata-only skeleton does not permit downloads")
    return "; ".join(blockers)


def _validate_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise IngestionPlanError(
            f"Missing required {frame_name} column(s): {', '.join(missing)}"
        )
