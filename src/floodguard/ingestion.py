"""Metadata-first real-data ingestion planning helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import re

import pandas as pd

METADATA_ONLY_ALLOWED_SUFFIXES: tuple[str, ...] = (
    ".csv",
    ".json",
    ".md",
    ".txt",
)

PROHIBITED_REAL_DATA_SUFFIXES: tuple[str, ...] = (
    ".safe",
    ".tif",
    ".tiff",
    ".jp2",
    ".zip",
    ".tar",
    ".gz",
    ".nc",
    ".grib",
    ".h5",
    ".hdf",
    ".img",
)

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

FILE_LEVEL_COLUMNS: tuple[str, ...] = (
    "product_id",
    "local_path",
    "sha256",
    "source_license_status",
    "reference_mask_status",
)

INGESTION_OUTPUT_COLUMNS: tuple[str, ...] = (
    *INGESTION_REQUIRED_COLUMNS,
    *FILE_LEVEL_COLUMNS,
    "ingestion_stage",
    "download_permitted_by_skeleton",
    "ready_for_processing",
    "processing_allowed",
    "blocked_reason",
    "reason_blocked",
)

MAE_SAI_REQUIRED_BASELINE_ROLES: tuple[str, ...] = (
    "reference flood mask for validation",
    "pre-event SAR source for non-ML baseline",
    "post-event SAR source for non-ML baseline",
)

MAE_SAI_BASELINE_PRE_PRODUCT_ID = "aaaef3af-fa49-4115-bf0f-f54175e7aedf"
MAE_SAI_BASELINE_POST_PRODUCT_ID = "5251b74b-0bbd-4365-9eb4-fa33292e175a"
MAE_SAI_BASELINE_PRODUCT_IDS: tuple[str, str] = (
    MAE_SAI_BASELINE_PRE_PRODUCT_ID,
    MAE_SAI_BASELINE_POST_PRODUCT_ID,
)

MAE_SAI_BASELINE_PRE_PRODUCT_NAME = (
    "S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_"
    "055507_06C5C9_72F7.SAFE"
)
MAE_SAI_BASELINE_POST_PRODUCT_NAME = (
    "S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_"
    "055682_06CCBA_08DA.SAFE"
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
                "product_id": "not_selected",
                "local_path": "not_acquired",
                "sha256": "not_acquired",
                "source_license_status": "unresolved",
                "reference_mask_status": "unresolved",
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
                "product_id": "not_selected",
                "local_path": "not_acquired",
                "sha256": "not_acquired",
                "source_license_status": "unresolved",
                "reference_mask_status": "unresolved",
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
                "product_id": "not_selected",
                "local_path": "not_acquired",
                "sha256": "not_acquired",
                "source_license_status": "unresolved",
                "reference_mask_status": "unresolved",
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
                "product_id": "not_selected",
                "local_path": "not_acquired",
                "sha256": "not_acquired",
                "source_license_status": "unresolved",
                "reference_mask_status": "unresolved",
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
                "product_id": "not_selected",
                "local_path": "not_acquired",
                "sha256": "not_acquired",
                "source_license_status": "unresolved",
                "reference_mask_status": "unresolved",
                "next_action": "search only after official/event sources are logged",
            },
        ]
    )


def default_mae_sai_file_manifest_sources() -> pd.DataFrame:
    """Return the approved original-SAFE rows for the Mae Sai first baseline.

    The previously selected September 6 COG / September 15 COG pair is not
    returned here. Its acquisitions are retained in the study-area inventory
    as retired exploratory metadata, but the pair mixes acquisition tracks and
    the local COG archives no longer match their recorded checksums after GDAL
    PAM mutation. Only the independently registered same-track original SAFE
    pair may occupy the active baseline roles.
    """

    return pd.DataFrame(
        [
            {
                "source_name": "UNOSAT/UNITAR Mae Sai reference mask file candidate",
                "study_area": "Chiang Rai / Mae Sai 2024",
                "source_url": "https://unosat.org/products/3991",
                "candidate_use": "reference flood mask for validation",
                "geometry_access_status": "unresolved",
                "license_status": "unresolved",
                "redistribution_status": "unresolved",
                "product_id": "UNOSAT-3991",
                "local_path": "not_acquired",
                "sha256": "not_acquired",
                "source_license_status": "unresolved",
                "reference_mask_status": "unresolved",
                "next_action": "send licensing request and acquire usable geometry terms",
            },
            {
                "source_name": "CDSE Sentinel-1 Mae Sai pre-event original SAFE",
                "study_area": "Chiang Rai / Mae Sai 2024",
                "source_url": (
                    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products("
                    f"{MAE_SAI_BASELINE_PRE_PRODUCT_ID})"
                ),
                "candidate_use": "pre-event SAR source for non-ML baseline",
                "geometry_access_status": "available",
                "license_status": "confirmed",
                "redistribution_status": "reference_only",
                "product_id": MAE_SAI_BASELINE_PRE_PRODUCT_ID,
                "local_path": "not_acquired",
                "sha256": "not_acquired",
                "source_license_status": "confirmed",
                "reference_mask_status": "unresolved",
                "next_action": (
                    "register the approved original SAFE archive and checksum outside Git; "
                    "reject COG or cross-track substitution"
                ),
            },
            {
                "source_name": "CDSE Sentinel-1 Mae Sai post-event original SAFE",
                "study_area": "Chiang Rai / Mae Sai 2024",
                "source_url": (
                    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products("
                    f"{MAE_SAI_BASELINE_POST_PRODUCT_ID})"
                ),
                "candidate_use": "post-event SAR source for non-ML baseline",
                "geometry_access_status": "available",
                "license_status": "confirmed",
                "redistribution_status": "reference_only",
                "product_id": MAE_SAI_BASELINE_POST_PRODUCT_ID,
                "local_path": "not_acquired",
                "sha256": "not_acquired",
                "source_license_status": "confirmed",
                "reference_mask_status": "unresolved",
                "next_action": (
                    "register the approved original SAFE archive and checksum outside Git; "
                    "reject COG or cross-track substitution"
                ),
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

    for column in FILE_LEVEL_COLUMNS:
        if column not in frame.columns:
            frame[column] = _file_level_default(column, frame)
        frame[column] = frame[column].astype(str).str.strip()
        if frame[column].eq("").any():
            raise IngestionPlanError(f"Column {column} must not contain blank values.")

    processing_allowed = frame.apply(_processing_allowed, axis=1)
    _reject_forced_processing_override(source_frame, processing_allowed)

    frame["processing_allowed"] = processing_allowed
    frame["ingestion_stage"] = processing_allowed.map(
        {True: "file_ready_metadata", False: "metadata_only"}
    )
    frame["download_permitted_by_skeleton"] = False
    frame["ready_for_processing"] = processing_allowed
    frame["blocked_reason"] = frame.apply(_blocked_reason, axis=1)
    frame["reason_blocked"] = frame["blocked_reason"]
    return frame.loc[:, INGESTION_OUTPUT_COLUMNS]


def write_ingestion_manifest(
    source_frame: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Write a metadata-only ingestion manifest CSV and return its path."""

    manifest = build_ingestion_manifest(source_frame)
    target = assert_metadata_only_output_path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(target, index=False, lineterminator="\n")
    return target


def assert_metadata_only_output_path(output_path: str | Path) -> Path:
    """Reject output paths that look like imagery, product, or binary data."""

    target = Path(output_path)
    suffixes = tuple(suffix.lower() for suffix in target.suffixes)
    if not suffixes:
        raise IngestionPlanError(
            "Metadata-only ingestion outputs must use an explicit metadata suffix: "
            f"{', '.join(METADATA_ONLY_ALLOWED_SUFFIXES)}."
        )
    prohibited = [suffix for suffix in suffixes if suffix in PROHIBITED_REAL_DATA_SUFFIXES]
    if prohibited:
        raise IngestionPlanError(
            "Metadata-only ingestion skeleton refuses imagery/product output paths: "
            f"{target}"
        )
    if suffixes[-1] not in METADATA_ONLY_ALLOWED_SUFFIXES:
        raise IngestionPlanError(
            "Metadata-only ingestion skeleton can only write metadata outputs "
            f"({', '.join(METADATA_ONLY_ALLOWED_SUFFIXES)}): {target}"
        )
    return target


def validate_mae_sai_file_manifest_ready(manifest: pd.DataFrame) -> pd.DataFrame:
    """Return the required Mae Sai baseline rows only when all gates pass."""

    _validate_columns(manifest, INGESTION_OUTPUT_COLUMNS, "Mae Sai manifest")
    frame = manifest.copy()
    selected_rows: list[pd.Series] = []
    blockers: list[str] = []
    for role in MAE_SAI_REQUIRED_BASELINE_ROLES:
        matches = frame[frame["candidate_use"].astype(str) == role]
        if role == "post-event SAR source for non-ML baseline":
            primary = matches[
                matches["source_name"].astype(str).str.contains(
                    "primary",
                    case=False,
                    regex=False,
                )
            ]
            if not primary.empty:
                matches = primary
        if matches.empty:
            blockers.append(f"missing required Mae Sai role: {role}")
            continue
        row = matches.iloc[0]
        row_blockers = _mae_sai_readiness_blockers(row)
        if row_blockers:
            blockers.append(f"{row['source_name']}: {', '.join(row_blockers)}")
        selected_rows.append(row)
    if blockers:
        raise IngestionPlanError("; ".join(blockers))
    return pd.DataFrame(selected_rows).reset_index(drop=True)


def _mae_sai_readiness_blockers(row: pd.Series) -> list[str]:
    blockers: list[str] = []
    if not _truthy(row["processing_allowed"]):
        blockers.append("processing_allowed is not true")
    if row["license_status"] != "confirmed":
        blockers.append("license_status is not confirmed")
    if row["source_license_status"] != "confirmed":
        blockers.append("source_license_status is not confirmed")
    if row["reference_mask_status"] != "confirmed":
        blockers.append("reference_mask_status is not confirmed")
    if row["product_id"] in {"not_selected", "not_acquired", "unknown"}:
        blockers.append("product_id is not selected")
    if row["local_path"] in {"not_acquired", "not_selected", "unknown"}:
        blockers.append("local_path is not recorded")
    if not _is_valid_sha256(row["sha256"]):
        blockers.append("sha256 is not recorded")
    return blockers


def _blocked_reason(row: pd.Series) -> str:
    blockers: list[str] = []
    if row["geometry_access_status"] not in {"confirmed", "available"}:
        blockers.append("geometry access not confirmed")
    if row["license_status"] != "confirmed":
        blockers.append("license not confirmed")
    if row["redistribution_status"] not in {"redistributable", "reference_only"}:
        blockers.append("redistribution status unresolved")
    if row["product_id"] in {"not_selected", "not_acquired", "unknown"}:
        blockers.append("product id not selected")
    if row["local_path"] in {"not_acquired", "not_selected", "unknown"}:
        blockers.append("local path not recorded")
    if not _is_valid_sha256(row["sha256"]):
        blockers.append("sha256 checksum not recorded")
    if row["source_license_status"] != "confirmed":
        blockers.append("source license not confirmed")
    if row["reference_mask_status"] != "confirmed":
        blockers.append("reference mask not confirmed")
    blockers.append("metadata-only skeleton does not permit downloads")
    return "; ".join(blockers)


def _file_level_default(column: str, frame: pd.DataFrame) -> object:
    if column == "source_license_status" and "license_status" in frame.columns:
        return frame["license_status"]
    if column in {"product_id", "local_path", "sha256"}:
        return "not_acquired" if column != "product_id" else "not_selected"
    if column == "reference_mask_status":
        return "unresolved"
    raise IngestionPlanError(f"Unknown file-level ingestion column: {column}")


def _processing_allowed(row: pd.Series) -> bool:
    return all(
        [
            row["geometry_access_status"] in {"confirmed", "available"},
            row["license_status"] == "confirmed",
            row["redistribution_status"] in {"redistributable", "reference_only"},
            row["product_id"] not in {"not_selected", "not_acquired", "unknown"},
            row["local_path"] not in {"not_acquired", "not_selected", "unknown"},
            _is_valid_sha256(row["sha256"]),
            row["source_license_status"] == "confirmed",
            row["reference_mask_status"] == "confirmed",
        ]
    )


def _is_valid_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", str(value).strip()))


def _reject_forced_processing_override(
    source_frame: pd.DataFrame,
    computed_processing_allowed: pd.Series,
) -> None:
    if "processing_allowed" not in source_frame.columns:
        return
    requested = source_frame["processing_allowed"].map(_truthy)
    invalid = requested & ~computed_processing_allowed
    if bool(invalid.any()):
        raise IngestionPlanError(
            "processing_allowed cannot be forced true until license, reference "
            "mask, local_path, and sha256 gates pass."
        )


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


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
