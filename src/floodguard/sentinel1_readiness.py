"""Checksum-backed readiness helpers for selected local Sentinel-1 files."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Iterable

import pandas as pd

DEFAULT_SELECTED_SENTINEL1_FILES: tuple[str, ...] = (
    "Sentinel1_Thailand-0000000000-0000000000-002.tif",
)

SENTINEL1_SELECTED_COLUMNS: tuple[str, ...] = (
    "source_name",
    "file_name",
    "local_path_hint",
    "sha256",
    "sha256_status",
    "file_size_bytes",
    "file_size_gb",
    "raster_width",
    "raster_height",
    "raster_count",
    "raster_dtypes",
    "band_descriptions",
    "crs",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "mvp_overlap",
    "candidate_use",
    "source_license_status",
    "provenance_status",
    "event_timing_status",
    "reference_mask_status",
    "processing_scope",
    "processing_allowed",
    "reason_blocked",
    "assumptions",
)

REQUIRED_LIBRARY_COLUMNS: tuple[str, ...] = (
    "source_name",
    "file_name",
    "local_path_hint",
    "library_group",
    "candidate_use",
    "file_size_bytes",
    "file_size_gb",
    "raster_width",
    "raster_height",
    "raster_count",
    "raster_dtypes",
    "band_descriptions",
    "crs",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "mvp_overlap",
    "license_status",
)


class Sentinel1ReadinessError(ValueError):
    """Raised when selected Sentinel-1 readiness inputs are invalid."""


def build_sentinel1_selected_file_manifest(
    input_dir: str | Path,
    local_library: str | Path | pd.DataFrame,
    selected_files: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Build a checksum-backed manifest for selected local Sentinel-1 files."""

    root = Path(input_dir)
    if not root.exists():
        raise Sentinel1ReadinessError(f"Sentinel-1 input directory does not exist: {root}")
    library = _coerce_frame(local_library)
    _require_columns(library, REQUIRED_LIBRARY_COLUMNS, "local data library")

    selected = tuple(selected_files or DEFAULT_SELECTED_SENTINEL1_FILES)
    if not selected:
        raise Sentinel1ReadinessError("At least one Sentinel-1 file must be selected.")

    rows: list[dict[str, object]] = []
    for file_name in selected:
        matches = library.loc[library["file_name"] == file_name]
        if matches.empty:
            raise Sentinel1ReadinessError(
                f"Selected Sentinel-1 file is missing from local data library: {file_name}"
            )
        if len(matches) > 1:
            raise Sentinel1ReadinessError(
                f"Selected Sentinel-1 file has duplicate library rows: {file_name}"
            )
        source_path = root / file_name
        if not source_path.exists():
            raise Sentinel1ReadinessError(
                f"Selected Sentinel-1 file is missing from input directory: {file_name}"
            )
        local_row = matches.iloc[0].to_dict()
        _validate_sentinel1_library_row(local_row)
        sha256 = compute_sha256(source_path)
        checksum_ok = bool(re.fullmatch(r"[0-9a-f]{64}", sha256))
        rows.append(_selected_row(local_row, sha256=sha256, checksum_ok=checksum_ok))
    return pd.DataFrame(rows, columns=SENTINEL1_SELECTED_COLUMNS)


def write_sentinel1_selected_file_manifest(
    input_dir: str | Path,
    local_library_path: str | Path,
    output_path: str | Path,
    selected_files: Iterable[str] | None = None,
) -> Path:
    """Write the selected Sentinel-1 checksum manifest."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise Sentinel1ReadinessError("Sentinel-1 selected manifest output must be CSV.")
    frame = build_sentinel1_selected_file_manifest(
        input_dir=input_dir,
        local_library=local_library_path,
        selected_files=selected_files,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


def compute_sha256(path: str | Path, chunk_size: int = 16 * 1024 * 1024) -> str:
    """Compute SHA-256 for a selected local source file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _selected_row(
    local_row: dict[str, object],
    sha256: str,
    checksum_ok: bool,
) -> dict[str, object]:
    license_status = str(local_row.get("license_status", ""))
    source_license_status = (
        "user_reported_hackathon_free_use"
        if license_status == "user_reported_hackathon_free_use"
        else "unresolved"
    )
    provenance_status = "unresolved_placeholder_filename"
    event_timing_status = "unresolved_no_acquisition_date"
    reference_mask_status = "unresolved"
    blockers = _reason_blocked(
        checksum_ok=checksum_ok,
        source_license_status=source_license_status,
        provenance_status=provenance_status,
        event_timing_status=event_timing_status,
        reference_mask_status=reference_mask_status,
    )
    return {
        "source_name": local_row["source_name"],
        "file_name": local_row["file_name"],
        "local_path_hint": local_row["local_path_hint"],
        "sha256": sha256,
        "sha256_status": "recorded" if checksum_ok else "not_recorded",
        "file_size_bytes": local_row["file_size_bytes"],
        "file_size_gb": local_row["file_size_gb"],
        "raster_width": local_row["raster_width"],
        "raster_height": local_row["raster_height"],
        "raster_count": local_row["raster_count"],
        "raster_dtypes": local_row["raster_dtypes"],
        "band_descriptions": local_row["band_descriptions"],
        "crs": local_row["crs"],
        "bbox_lon_min": local_row["bbox_lon_min"],
        "bbox_lat_min": local_row["bbox_lat_min"],
        "bbox_lon_max": local_row["bbox_lon_max"],
        "bbox_lat_max": local_row["bbox_lat_max"],
        "mvp_overlap": local_row["mvp_overlap"],
        "candidate_use": local_row["candidate_use"],
        "source_license_status": source_license_status,
        "provenance_status": provenance_status,
        "event_timing_status": event_timing_status,
        "reference_mask_status": reference_mask_status,
        "processing_scope": "sentinel1_sar_context_readiness_only",
        "processing_allowed": False,
        "reason_blocked": blockers,
        "assumptions": (
            "Selected local Sentinel-1 SAR file; checksum recorded; source TIFF "
            "remains outside Git; processing remains blocked until provenance, "
            "event timing, and reference-mask gates are clear."
        ),
    }


def _reason_blocked(
    *,
    checksum_ok: bool,
    source_license_status: str,
    provenance_status: str,
    event_timing_status: str,
    reference_mask_status: str,
) -> str:
    reasons: list[str] = []
    if not checksum_ok:
        reasons.append("sha256 checksum not recorded")
    if source_license_status != "user_reported_hackathon_free_use":
        reasons.append("source license status unresolved")
    if provenance_status != "confirmed":
        reasons.append("Sentinel-1 provenance unresolved")
    if event_timing_status != "confirmed":
        reasons.append("event timing unresolved")
    if reference_mask_status != "confirmed":
        reasons.append("reference mask not confirmed")
    return "; ".join(reasons)


def _validate_sentinel1_library_row(row: dict[str, object]) -> None:
    if row["library_group"] != "sentinel1_sar":
        raise Sentinel1ReadinessError(
            f"Selected file is not cataloged as Sentinel-1 SAR: {row['file_name']}"
        )
    if str(row["local_path_hint"]).startswith(("/", "C:", "D:")):
        raise Sentinel1ReadinessError(
            f"Local path hint must be redacted for selected Sentinel-1 file: {row['file_name']}"
        )
    if str(row.get("band_descriptions", "")) != "VV|VH":
        raise Sentinel1ReadinessError(
            f"Selected Sentinel-1 file must expose VV|VH bands: {row['file_name']}"
        )
    if str(row.get("mvp_overlap", "")) != "mae_sai_2024_point":
        raise Sentinel1ReadinessError(
            f"Selected Sentinel-1 file must overlap Mae Sai MVP point: {row['file_name']}"
        )


def _coerce_frame(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    return pd.read_csv(source, dtype=str).fillna("")


def _require_columns(
    frame: pd.DataFrame,
    required_columns: tuple[str, ...],
    label: str,
) -> None:
    missing = sorted(set(required_columns) - set(frame.columns))
    if missing:
        raise Sentinel1ReadinessError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )
