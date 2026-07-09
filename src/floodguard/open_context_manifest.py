"""Open-source context data file manifest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import urllib.error
import urllib.request

import pandas as pd

OPEN_CONTEXT_COLUMNS: tuple[str, ...] = (
    "source_name",
    "source_group",
    "study_area",
    "source_url",
    "download_url",
    "file_name",
    "candidate_use",
    "data_type",
    "license_status",
    "local_path",
    "sha256",
    "sha256_status",
    "file_size_bytes",
    "acquisition_status",
    "processing_scope",
    "processing_allowed",
    "reason_blocked",
    "next_action",
    "retrieved_at_utc",
)

DEFAULT_EXTERNAL_DATA_ROOT = Path.home() / "Documents" / "FloodGuard_external_data"
DEFAULT_DEM_FILE_NAME = "CopernicusDEM_Elevation_Slope_Thailand-0000046592-0000023296.tif"
DEFAULT_DEM_PATH = (
    DEFAULT_EXTERNAL_DATA_ROOT
    / "open_context"
    / "copernicus_dem_glo30"
    / DEFAULT_DEM_FILE_NAME
)
FALLBACK_DEM_PATH = (
    Path.home()
    / "Downloads"
    / "FloodGuardLocalExtracts"
    / "dem"
    / DEFAULT_DEM_FILE_NAME
)


@dataclass(frozen=True)
class OpenContextSource:
    """Download or local-file specification for one open context source."""

    source_name: str
    source_group: str
    study_area: str
    source_url: str
    download_url: str
    file_name: str
    candidate_use: str
    data_type: str
    license_status: str
    processing_scope: str
    ready_next_action: str
    blocked_next_action: str
    blocked_reason: str


def open_context_sources() -> tuple[OpenContextSource, ...]:
    """Return the selected context sources for the first real-data lane."""

    return (
        OpenContextSource(
            source_name="WorldPop Thailand 100m",
            source_group="worldpop_population",
            study_area="Thailand",
            source_url="https://hub.worldpop.org/geodata/summary?id=6439",
            download_url=(
                "https://data.worldpop.org/GIS/Population/Global_2000_2020/"
                "2020/THA/tha_ppp_2020.tif"
            ),
            file_name="tha_ppp_2020.tif",
            candidate_use="population exposure and reachable-demand denominator",
            data_type="population_raster_geotiff",
            license_status="worldpop_open_data_citation_required",
            processing_scope="exposure_context_only_not_flood_label",
            ready_next_action=(
                "clip to study area and aggregate population to admin/review polygons"
            ),
            blocked_next_action=(
                "download WorldPop GeoTIFF outside Git and record SHA-256"
            ),
            blocked_reason="source file not downloaded outside Git and checksum not recorded",
        ),
        OpenContextSource(
            source_name="HDX Thailand COD-AB",
            source_group="hdx_cod_ab",
            study_area="Thailand",
            source_url="https://data.humdata.org/dataset/cod-ab-tha",
            download_url=(
                "https://data.humdata.org/dataset/"
                "d24bdc45-eb4c-4e3d-8b16-44db02667c27/resource/"
                "ccbf3740-0638-48ea-b612-cdb61ef5462c/download/"
                "tha_admin_boundaries.gdb.zip"
            ),
            file_name="tha_admin_boundaries.gdb.zip",
            candidate_use="administrative boundary aggregation geometry",
            data_type="admin_boundary_geodatabase_zip",
            license_status="hdx_cod_ab_dataset_terms_and_attribution_required",
            processing_scope="admin_join_context_only_not_flood_label",
            ready_next_action=(
                "select admin level, verify boundary vintage, and join scored outputs"
            ),
            blocked_next_action=(
                "download HDX COD-AB boundary package outside Git and record SHA-256"
            ),
            blocked_reason="source file not downloaded outside Git and checksum not recorded",
        ),
        OpenContextSource(
            source_name="OpenStreetMap Thailand via Geofabrik",
            source_group="osm_geofabrik",
            study_area="Thailand",
            source_url="https://download.geofabrik.de/asia/thailand.html",
            download_url="http://download.geofabrik.de/asia/thailand-latest.osm.pbf",
            file_name="thailand-latest.osm.pbf",
            candidate_use="roads, bridges, facilities, and routing graph candidate",
            data_type="osm_pbf_extract",
            license_status="odbl_1_0_attribution_and_share_alike_obligations_apply",
            processing_scope="road_facility_context_only_not_flood_label",
            ready_next_action=(
                "extract roads, bridge tags, facilities, and candidate routing graph"
            ),
            blocked_next_action=(
                "download Geofabrik Thailand OSM PBF outside Git and record SHA-256"
            ),
            blocked_reason="source file not downloaded outside Git and checksum not recorded",
        ),
        OpenContextSource(
            source_name="Current local Copernicus DEM Thailand tile",
            source_group="copernicus_dem_glo30",
            study_area="Thailand",
            source_url=(
                "https://dataspace.copernicus.eu/explore-data/data-collections/"
                "copernicus-contributing-missions/collections-description/COP-DEM"
            ),
            download_url="local_current_dem_package",
            file_name=DEFAULT_DEM_FILE_NAME,
            candidate_use="terrain, slope, and false-positive review context",
            data_type="dem_raster_geotiff",
            license_status=(
                "current_local_dem_package_user_reported_hackathon_free_use"
            ),
            processing_scope="terrain_context_only_not_flood_observation_or_label",
            ready_next_action=(
                "sample elevation/slope for false-positive review and context notes"
            ),
            blocked_next_action=(
                "provide extracted DEM TIFF outside Git or select Copernicus DEM tiles"
            ),
            blocked_reason="local DEM TIFF not found and checksum not recorded",
        ),
    )


def default_open_context_rows(retrieved_at_utc: str | None = None) -> pd.DataFrame:
    """Return planned open context source rows."""

    timestamp = retrieved_at_utc or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rows = []
    for source in open_context_sources():
        rows.append(
            {
                "source_name": source.source_name,
                "source_group": source.source_group,
                "study_area": source.study_area,
                "source_url": source.source_url,
                "download_url": source.download_url,
                "file_name": source.file_name,
                "candidate_use": source.candidate_use,
                "data_type": source.data_type,
                "license_status": source.license_status,
                "local_path": "not_acquired",
                "sha256": "not_acquired",
                "sha256_status": "not_recorded",
                "file_size_bytes": "not_acquired",
                "acquisition_status": "not_acquired",
                "processing_scope": source.processing_scope,
                "processing_allowed": False,
                "reason_blocked": source.blocked_reason,
                "next_action": source.blocked_next_action,
                "retrieved_at_utc": timestamp,
            }
        )
    return pd.DataFrame(rows, columns=OPEN_CONTEXT_COLUMNS)


def build_open_context_rows(
    *,
    external_data_root: str | Path = DEFAULT_EXTERNAL_DATA_ROOT,
    download: bool = False,
    dem_path: str | Path | None = None,
    retrieved_at_utc: str | None = None,
) -> pd.DataFrame:
    """Build file-level context rows, optionally downloading remote sources."""

    root = Path(external_data_root)
    timestamp = (
        retrieved_at_utc
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    if dem_path is not None:
        selected_dem_path = Path(dem_path)
    elif DEFAULT_DEM_PATH.exists():
        selected_dem_path = DEFAULT_DEM_PATH
    else:
        selected_dem_path = FALLBACK_DEM_PATH
    rows = []
    for source in open_context_sources():
        download_error = ""
        if source.download_url == "local_current_dem_package":
            local_path = selected_dem_path
        else:
            local_path = root / "open_context" / source.source_group / source.file_name
            if download and not local_path.exists():
                try:
                    _download_to_path(source.download_url, local_path)
                except RuntimeError as exc:
                    download_error = str(exc)

        row = _build_context_row(
            source=source,
            local_path=local_path,
            external_data_root=root,
            retrieved_at_utc=timestamp,
        )
        if download_error and not local_path.exists():
            row["acquisition_status"] = "download_failed"
            row["reason_blocked"] = download_error
        rows.append(row)
    return pd.DataFrame(rows, columns=OPEN_CONTEXT_COLUMNS)


def write_open_context_manifest(
    output_path: str | Path,
    retrieved_at_utc: str | None = None,
    *,
    external_data_root: str | Path = DEFAULT_EXTERNAL_DATA_ROOT,
    download: bool = False,
    dem_path: str | Path | None = None,
) -> Path:
    """Write the open-source context acquisition manifest."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise ValueError("Open context manifest must be CSV.")
    target.parent.mkdir(parents=True, exist_ok=True)
    build_open_context_rows(
        external_data_root=external_data_root,
        download=download,
        dem_path=dem_path,
        retrieved_at_utc=retrieved_at_utc,
    ).to_csv(target, index=False)
    return target


def _build_context_row(
    *,
    source: OpenContextSource,
    local_path: Path,
    external_data_root: Path,
    retrieved_at_utc: str,
) -> dict[str, object]:
    if local_path.exists() and local_path.is_file():
        checksum = _sha256_file(local_path)
        return {
            "source_name": source.source_name,
            "source_group": source.source_group,
            "study_area": source.study_area,
            "source_url": source.source_url,
            "download_url": source.download_url,
            "file_name": local_path.name,
            "candidate_use": source.candidate_use,
            "data_type": source.data_type,
            "license_status": source.license_status,
            "local_path": _redact_external_path(local_path, external_data_root),
            "sha256": checksum,
            "sha256_status": "recorded",
            "file_size_bytes": local_path.stat().st_size,
            "acquisition_status": "available_outside_git",
            "processing_scope": source.processing_scope,
            "processing_allowed": True,
            "reason_blocked": "",
            "next_action": source.ready_next_action,
            "retrieved_at_utc": retrieved_at_utc,
        }
    return {
        "source_name": source.source_name,
        "source_group": source.source_group,
        "study_area": source.study_area,
        "source_url": source.source_url,
        "download_url": source.download_url,
        "file_name": source.file_name,
        "candidate_use": source.candidate_use,
        "data_type": source.data_type,
        "license_status": source.license_status,
        "local_path": _redact_external_path(local_path, external_data_root),
        "sha256": "not_acquired",
        "sha256_status": "not_recorded",
        "file_size_bytes": "not_acquired",
        "acquisition_status": "missing_external_file",
        "processing_scope": source.processing_scope,
        "processing_allowed": False,
        "reason_blocked": source.blocked_reason,
        "next_action": source.blocked_next_action,
        "retrieved_at_utc": retrieved_at_utc,
    }


def _download_to_path(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "FloodGuard-open-context-manifest/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open(
            "wb"
        ) as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        partial.replace(target)
    except (OSError, urllib.error.URLError) as exc:
        if partial.exists():
            partial.unlink()
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redact_external_path(path: Path, external_data_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(external_data_root.resolve())
        return f"<external_data_workspace>/{relative.as_posix()}"
    except ValueError:
        if path.name:
            return f"<external_data_workspace>/external_existing/{path.name}"
        return "<external_data_workspace>/unavailable"
