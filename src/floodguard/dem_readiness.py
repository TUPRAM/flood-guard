"""Package-level readiness helpers for local Copernicus DEM ZIP assets."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Iterable

import pandas as pd

DEFAULT_DEM_PACKAGES: tuple[str, ...] = (
    "drive-download-20260705T104354Z-3-001.zip",
    "drive-download-20260705T104354Z-3-002.zip",
)

DEM_SELECTED_COLUMNS: tuple[str, ...] = (
    "source_name",
    "package_name",
    "member_name",
    "local_package_path_hint",
    "member_path_hint",
    "package_sha256",
    "package_sha256_status",
    "package_file_size_bytes",
    "package_file_size_gb",
    "zip_member_count",
    "member_size_bytes",
    "member_size_gb",
    "member_kind",
    "checksum_strategy",
    "candidate_use",
    "source_license_status",
    "reference_mask_status",
    "flood_observation_status",
    "flood_label_status",
    "processing_scope",
    "processing_status",
    "processing_allowed",
    "reason_blocked",
    "assumptions",
)

REQUIRED_LIBRARY_COLUMNS: tuple[str, ...] = (
    "source_name",
    "file_name",
    "local_path_hint",
    "entry_kind",
    "library_group",
    "candidate_use",
    "file_size_bytes",
    "file_size_gb",
    "zip_member_count",
    "license_status",
)

REQUIRED_MEMBER_COLUMNS: tuple[str, ...] = (
    "container_name",
    "member_name",
    "member_path_hint",
    "member_kind",
    "library_group",
    "member_size_bytes",
    "member_size_gb",
    "candidate_use",
)


class DEMReadinessError(ValueError):
    """Raised when DEM readiness inputs are invalid."""


def build_dem_selected_file_manifest(
    input_dir: str | Path,
    local_library: str | Path | pd.DataFrame,
    zip_members: str | Path | pd.DataFrame,
    selected_packages: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Build a package-checksum manifest for selected local DEM ZIP packages."""

    root = Path(input_dir)
    if not root.exists():
        raise DEMReadinessError(f"DEM input directory does not exist: {root}")
    library = _coerce_frame(local_library)
    members = _coerce_frame(zip_members)
    _require_columns(library, REQUIRED_LIBRARY_COLUMNS, "local data library")
    _require_columns(members, REQUIRED_MEMBER_COLUMNS, "ZIP member catalog")

    packages = tuple(selected_packages or DEFAULT_DEM_PACKAGES)
    if not packages:
        raise DEMReadinessError("At least one DEM package must be selected.")

    rows: list[dict[str, object]] = []
    for package_name in packages:
        package_rows = library.loc[library["file_name"] == package_name]
        if package_rows.empty:
            raise DEMReadinessError(
                f"Selected DEM package is missing from local data library: {package_name}"
            )
        if len(package_rows) > 1:
            raise DEMReadinessError(
                f"Selected DEM package has duplicate library rows: {package_name}"
            )
        package_row = package_rows.iloc[0].to_dict()
        _validate_dem_package_row(package_row)
        package_path = root / package_name
        if not package_path.exists():
            raise DEMReadinessError(
                f"Selected DEM package is missing from input directory: {package_name}"
            )
        sha256 = compute_sha256(package_path)
        checksum_ok = bool(re.fullmatch(r"[0-9a-f]{64}", sha256))
        dem_members = members[
            (members["container_name"] == package_name)
            & (members["library_group"] == "copernicus_dem")
            & (members["member_kind"] == "image_tiff")
        ]
        if dem_members.empty:
            raise DEMReadinessError(
                f"Selected DEM package has no Copernicus DEM TIFF members: {package_name}"
            )
        for member_row in dem_members.to_dict(orient="records"):
            rows.append(
                _selected_row(
                    package_row=package_row,
                    member_row=member_row,
                    package_sha256=sha256,
                    checksum_ok=checksum_ok,
                )
            )
    return pd.DataFrame(rows, columns=DEM_SELECTED_COLUMNS)


def write_dem_selected_file_manifest(
    input_dir: str | Path,
    local_library_path: str | Path,
    zip_members_path: str | Path,
    output_path: str | Path,
    selected_packages: Iterable[str] | None = None,
) -> Path:
    """Write the selected DEM package-readiness manifest."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise DEMReadinessError("DEM selected manifest output must be CSV.")
    frame = build_dem_selected_file_manifest(
        input_dir=input_dir,
        local_library=local_library_path,
        zip_members=zip_members_path,
        selected_packages=selected_packages,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


def compute_sha256(path: str | Path, chunk_size: int = 16 * 1024 * 1024) -> str:
    """Compute SHA-256 for a selected local DEM package."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _selected_row(
    package_row: dict[str, object],
    member_row: dict[str, object],
    package_sha256: str,
    checksum_ok: bool,
) -> dict[str, object]:
    source_license_status = (
        "user_reported_hackathon_free_use"
        if str(package_row["license_status"]) == "user_reported_hackathon_free_use"
        else "unresolved"
    )
    reason_blocked = _reason_blocked(
        checksum_ok=checksum_ok,
        source_license_status=source_license_status,
    )
    return {
        "source_name": package_row["source_name"],
        "package_name": package_row["file_name"],
        "member_name": member_row["member_name"],
        "local_package_path_hint": package_row["local_path_hint"],
        "member_path_hint": member_row["member_path_hint"],
        "package_sha256": package_sha256,
        "package_sha256_status": "recorded" if checksum_ok else "not_recorded",
        "package_file_size_bytes": package_row["file_size_bytes"],
        "package_file_size_gb": package_row["file_size_gb"],
        "zip_member_count": package_row["zip_member_count"],
        "member_size_bytes": member_row["member_size_bytes"],
        "member_size_gb": member_row["member_size_gb"],
        "member_kind": member_row["member_kind"],
        "checksum_strategy": (
            "package-level checksum recorded first; member-level checksum only if "
            "extracted into a controlled local data workspace later"
        ),
        "candidate_use": "terrain/slope context for false-positive review and exposure explanation",
        "source_license_status": source_license_status,
        "reference_mask_status": "not_reference_mask",
        "flood_observation_status": "not_flood_observation",
        "flood_label_status": "not_flood_label",
        "processing_scope": "dem_terrain_context_readiness_only",
        "processing_status": "blocked_until_member_extraction_and_scope_review",
        "processing_allowed": False,
        "reason_blocked": reason_blocked,
        "assumptions": (
            "DEM/elevation-slope package is terrain context only; no ZIP extraction "
            "was performed; source package remains outside Git; not flood observation, "
            "not flood label, and not an official warning product."
        ),
    }


def _reason_blocked(*, checksum_ok: bool, source_license_status: str) -> str:
    reasons = [
        "DEM is context only, not flood observation",
        "DEM is not a flood label or reference mask",
        "member-level checksum not recorded because ZIP was not extracted",
        "source ZIP remains outside Git",
    ]
    if not checksum_ok:
        reasons.insert(0, "package-level sha256 checksum not recorded")
    if source_license_status != "user_reported_hackathon_free_use":
        reasons.append("source license status unresolved")
    return "; ".join(reasons)


def _validate_dem_package_row(row: dict[str, object]) -> None:
    if row["entry_kind"] != "zip_package":
        raise DEMReadinessError(
            f"Selected DEM asset must be a ZIP package: {row['file_name']}"
        )
    if row["library_group"] != "copernicus_dem":
        raise DEMReadinessError(
            f"Selected file is not cataloged as Copernicus DEM: {row['file_name']}"
        )
    if str(row["local_path_hint"]).startswith(("/", "C:", "D:")):
        raise DEMReadinessError(
            f"Local package path hint must be redacted for DEM package: {row['file_name']}"
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
        raise DEMReadinessError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )
