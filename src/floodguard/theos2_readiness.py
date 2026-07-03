"""Readiness and preview helpers for selected THEOS-2 sample files."""

from __future__ import annotations

import csv
import hashlib
import html
from pathlib import Path
import re
from typing import Iterable

import pandas as pd

DEFAULT_SELECTED_THEOS2_FILES: tuple[str, ...] = (
    "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif",
    "IMG_T2V_20250731035100_ORTHO_PMS_32-001.tif",
    "IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif",
)

THEOS2_SELECTED_COLUMNS: tuple[str, ...] = (
    "source_name",
    "file_name",
    "local_path_hint",
    "entry_kind",
    "category",
    "file_size_bytes",
    "file_size_gb",
    "acquisition_date",
    "acquisition_time_utc",
    "source_timestamp",
    "processing_level",
    "sensor_product",
    "tile_id",
    "sequence_id",
    "image_width",
    "image_height",
    "samples_per_pixel",
    "bits_per_sample",
    "pixel_size_m",
    "crs_hint",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "mvp_overlap",
    "floodguard_relevance",
    "license_status",
    "checksum_algorithm",
    "sha256",
    "sha256_status",
    "processing_scope",
    "reference_mask_status",
    "processing_allowed",
    "preview_path",
    "assumptions",
    "reason_blocked",
)

REQUIRED_LOCAL_MANIFEST_COLUMNS: tuple[str, ...] = (
    "file_name",
    "local_path_hint",
    "entry_kind",
    "category",
    "file_size_bytes",
    "file_size_gb",
    "acquisition_date",
    "acquisition_time_utc",
    "processing_level",
    "sensor_product",
    "tile_id",
    "sequence_id",
    "image_width",
    "image_height",
    "samples_per_pixel",
    "bits_per_sample",
    "pixel_size_m",
    "crs_hint",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "mvp_overlap",
    "floodguard_relevance",
    "license_status",
)


class THEOS2ReadinessError(ValueError):
    """Raised when selected THEOS-2 files are not ready for guarded use."""


def build_theos2_selected_file_manifest(
    input_dir: str | Path,
    local_manifest: str | Path | pd.DataFrame,
    selected_files: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Build a checksum-backed manifest for selected local THEOS-2 files.

    This function hashes only the explicitly selected file names. It does not
    read image pixels semantically, create raster derivatives, or copy source
    imagery into the repository.
    """

    root = Path(input_dir)
    if not root.exists():
        raise THEOS2ReadinessError(f"THEOS-2 input directory does not exist: {root}")
    manifest = _coerce_frame(local_manifest)
    _require_columns(manifest, REQUIRED_LOCAL_MANIFEST_COLUMNS, "local manifest")

    selected = tuple(selected_files or DEFAULT_SELECTED_THEOS2_FILES)
    if not selected:
        raise THEOS2ReadinessError("At least one THEOS-2 file must be selected.")

    rows: list[dict[str, object]] = []
    for file_name in selected:
        matches = manifest.loc[manifest["file_name"] == file_name]
        if matches.empty:
            raise THEOS2ReadinessError(
                f"Selected THEOS-2 file is missing from local manifest: {file_name}"
            )
        if len(matches) > 1:
            raise THEOS2ReadinessError(
                f"Selected THEOS-2 file has duplicate manifest rows: {file_name}"
            )
        source_path = root / file_name
        if not source_path.exists():
            raise THEOS2ReadinessError(
                f"Selected THEOS-2 file is missing from input directory: {file_name}"
            )
        local_row = matches.iloc[0].to_dict()
        sha256 = compute_sha256(source_path)
        license_ok = local_row.get("license_status") == "user_reported_hackathon_free_use"
        checksum_ok = bool(re.fullmatch(r"[0-9a-f]{64}", sha256))
        processing_allowed = license_ok and checksum_ok
        rows.append(
            _selected_row(
                local_row,
                sha256=sha256,
                processing_allowed=processing_allowed,
                reason_blocked=_reason_blocked(license_ok, checksum_ok),
            )
        )
    return pd.DataFrame(rows, columns=THEOS2_SELECTED_COLUMNS)


def write_theos2_selected_file_manifest(
    input_dir: str | Path,
    local_manifest_path: str | Path,
    output_path: str | Path,
    selected_files: Iterable[str] | None = None,
) -> Path:
    """Write the selected THEOS-2 checksum manifest."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise THEOS2ReadinessError("THEOS-2 selected manifest output must be CSV.")
    frame = build_theos2_selected_file_manifest(
        input_dir=input_dir,
        local_manifest=local_manifest_path,
        selected_files=selected_files,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


def write_theos2_preview_svgs(
    selected_manifest: str | Path | pd.DataFrame,
    output_dir: str | Path,
) -> list[Path]:
    """Write small non-operational SVG preview cards for checksum-ready rows."""

    frame = _coerce_frame(selected_manifest)
    _require_columns(
        frame,
        (
            "file_name",
            "category",
            "acquisition_date",
            "source_timestamp",
            "bbox_lon_min",
            "bbox_lat_min",
            "bbox_lon_max",
            "bbox_lat_max",
            "sha256",
            "processing_allowed",
            "preview_path",
            "assumptions",
        ),
        "selected manifest",
    )
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for row in frame.to_dict(orient="records"):
        if not _truthy(row["processing_allowed"]):
            raise THEOS2ReadinessError(
                f"Cannot write THEOS-2 preview before checksum gate passes: "
                f"{row['file_name']}"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", str(row["sha256"])):
            raise THEOS2ReadinessError(
                f"Cannot write THEOS-2 preview without SHA-256: {row['file_name']}"
            )
        preview_name = Path(str(row["preview_path"])).name
        if Path(preview_name).suffix.lower() != ".svg":
            raise THEOS2ReadinessError("THEOS-2 preview path must end in .svg.")
        target = target_dir / preview_name
        target.write_text(build_theos2_preview_svg(row), encoding="utf-8")
        written.append(target)
    return written


def compute_sha256(path: str | Path, chunk_size: int = 16 * 1024 * 1024) -> str:
    """Compute a SHA-256 checksum for a selected local source file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_theos2_preview_rows(path: str | Path | None) -> list[dict[str, str]]:
    """Read preview rows for dashboard embedding."""

    if path is None:
        return []
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_theos2_preview_svg(row: dict[str, object]) -> str:
    """Build a compact SVG metadata card for a selected THEOS-2 file."""

    file_name = _escape(row.get("file_name"))
    category = _escape(row.get("category"))
    timestamp = _escape(row.get("source_timestamp"))
    bbox = _escape(_bbox_text(row))
    sha = _escape(str(row.get("sha256", ""))[:12])
    assumptions = _escape(row.get("assumptions"))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360" role="img" aria-label="THEOS-2 optical context preview">
  <rect width="640" height="360" fill="#f7f8f4"/>
  <rect x="24" y="24" width="592" height="312" rx="8" fill="#ffffff" stroke="#d8ded4"/>
  <rect x="48" y="72" width="544" height="108" rx="6" fill="#dceee7" stroke="#21835f"/>
  <path d="M72 152 L142 108 L205 138 L272 94 L336 132 L402 102 L512 152 Z" fill="#21835f" opacity="0.35"/>
  <path d="M64 168 C150 136 242 194 330 156 C408 123 482 144 576 112" fill="none" stroke="#2b6c9f" stroke-width="10" opacity="0.55"/>
  <text x="48" y="54" fill="#202722" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="700">THEOS-2 Optical Context</text>
  <text x="48" y="214" fill="#202722" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="700">{file_name}</text>
  <text x="48" y="242" fill="#5b665f" font-family="Arial, Helvetica, sans-serif" font-size="14">Category: {category}</text>
  <text x="48" y="266" fill="#5b665f" font-family="Arial, Helvetica, sans-serif" font-size="14">Acquisition: {timestamp}</text>
  <text x="48" y="290" fill="#5b665f" font-family="Arial, Helvetica, sans-serif" font-size="14">BBox: {bbox}</text>
  <text x="48" y="314" fill="#5b665f" font-family="Arial, Helvetica, sans-serif" font-size="14">SHA-256 prefix: {sha}</text>
  <text x="48" y="334" fill="#b73c3c" font-family="Arial, Helvetica, sans-serif" font-size="12">{assumptions}</text>
</svg>
"""


def _selected_row(
    local_row: dict[str, object],
    sha256: str,
    processing_allowed: bool,
    reason_blocked: str,
) -> dict[str, object]:
    source_timestamp = _source_timestamp(
        str(local_row.get("acquisition_date", "")),
        str(local_row.get("acquisition_time_utc", "")),
    )
    file_name = str(local_row["file_name"])
    return {
        **{column: local_row.get(column, "") for column in THEOS2_SELECTED_COLUMNS},
        "source_timestamp": source_timestamp,
        "license_status": local_row.get("license_status", ""),
        "checksum_algorithm": "sha256",
        "sha256": sha256,
        "sha256_status": "recorded" if sha256 else "not_recorded",
        "processing_scope": "theos2_optical_context_preview_only",
        "reference_mask_status": "not_reference_mask",
        "processing_allowed": processing_allowed,
        "preview_path": f"theos2_previews/theos2_preview_{_safe_stem(file_name)}.svg",
        "assumptions": (
            "Non-operational THEOS-2 optical context only; not flood validation; "
            "source imagery remains outside Git"
        ),
        "reason_blocked": reason_blocked,
    }


def _coerce_frame(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    return pd.read_csv(source, dtype=str).fillna("")


def _require_columns(
    frame: pd.DataFrame,
    required_columns: Iterable[str],
    label: str,
) -> None:
    missing = sorted(set(required_columns) - set(frame.columns))
    if missing:
        raise THEOS2ReadinessError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def _reason_blocked(license_ok: bool, checksum_ok: bool) -> str:
    reasons: list[str] = []
    if not license_ok:
        reasons.append("THEOS-2 usage permission not logged")
    if not checksum_ok:
        reasons.append("sha256 checksum not recorded")
    return "; ".join(reasons)


def _source_timestamp(date_value: str, time_value: str) -> str:
    date_value = _normalize_digits(date_value)
    time_value = _normalize_digits(time_value).zfill(6)
    if not re.fullmatch(r"\d{8}", date_value) or not re.fullmatch(r"\d{6}", time_value):
        return ""
    return (
        f"{date_value[:4]}-{date_value[4:6]}-{date_value[6:8]}T"
        f"{time_value[:2]}:{time_value[2:4]}:{time_value[4:6]}Z"
    )


def _normalize_digits(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"\d+\.0", value):
        return value[:-2]
    return value


def _safe_stem(file_name: str) -> str:
    stem = Path(file_name).stem
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _bbox_text(row: dict[str, object]) -> str:
    values = [
        row.get("bbox_lon_min"),
        row.get("bbox_lat_min"),
        row.get("bbox_lon_max"),
        row.get("bbox_lat_max"),
    ]
    if any(value in ("", None) for value in values):
        return "unavailable"
    return ", ".join(str(value) for value in values)
