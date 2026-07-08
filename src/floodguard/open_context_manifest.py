"""Planned open-source context data manifest."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

OPEN_CONTEXT_COLUMNS: tuple[str, ...] = (
    "source_name",
    "source_group",
    "study_area",
    "source_url",
    "candidate_use",
    "data_type",
    "license_status",
    "local_path",
    "sha256",
    "processing_scope",
    "processing_allowed",
    "reason_blocked",
    "next_action",
    "retrieved_at_utc",
)


def default_open_context_rows(retrieved_at_utc: str | None = None) -> pd.DataFrame:
    """Return planned open context source rows."""

    timestamp = retrieved_at_utc or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rows = [
        {
            "source_name": "WorldPop Thailand 100m",
            "source_group": "worldpop_population",
            "study_area": "Thailand",
            "source_url": "https://hub.worldpop.org/geodata/summary?id=6439",
            "candidate_use": "population exposure and reachable-demand denominator",
            "data_type": "population_raster",
            "license_status": "dataset_specific_terms_need_file_level_record",
            "local_path": "not_acquired",
            "sha256": "not_acquired",
            "processing_scope": "exposure_context_only_not_flood_label",
            "processing_allowed": False,
            "reason_blocked": "source file not downloaded outside Git and checksum not recorded",
            "next_action": "select year/version, download outside Git, record license text and SHA-256",
            "retrieved_at_utc": timestamp,
        },
        {
            "source_name": "HDX Thailand COD-AB",
            "source_group": "hdx_cod_ab",
            "study_area": "Thailand",
            "source_url": "https://data.humdata.org/dataset/cod-ab-tha",
            "candidate_use": "administrative boundary aggregation geometry",
            "data_type": "admin_boundary_vector",
            "license_status": "dataset_specific_hdx_terms_need_file_level_record",
            "local_path": "not_acquired",
            "sha256": "not_acquired",
            "processing_scope": "admin_join_context_only_not_flood_label",
            "processing_allowed": False,
            "reason_blocked": "source file not downloaded outside Git and checksum not recorded",
            "next_action": "select admin level/version, download outside Git, record SHA-256",
            "retrieved_at_utc": timestamp,
        },
        {
            "source_name": "OpenStreetMap Thailand via Geofabrik",
            "source_group": "osm_geofabrik",
            "study_area": "Thailand",
            "source_url": "https://download.geofabrik.de/asia/thailand.html",
            "candidate_use": "roads, bridges, facilities, and routing graph candidate",
            "data_type": "osm_pbf_or_shapefile_extract",
            "license_status": "odbl_1_0_obligations_apply",
            "local_path": "not_acquired",
            "sha256": "not_acquired",
            "processing_scope": "road_facility_context_only_not_flood_label",
            "processing_allowed": False,
            "reason_blocked": "source file not downloaded outside Git and checksum not recorded",
            "next_action": "download extract outside Git and record ODbL attribution/share-alike notes",
            "retrieved_at_utc": timestamp,
        },
        {
            "source_name": "Copernicus DEM GLO-30",
            "source_group": "copernicus_dem_glo30",
            "study_area": "Thailand",
            "source_url": (
                "https://dataspace.copernicus.eu/explore-data/data-collections/"
                "copernicus-contributing-missions/collections-description/COP-DEM"
            ),
            "candidate_use": "terrain, slope, and false-positive review context",
            "data_type": "dem_raster",
            "license_status": "free_license_with_citation_source_obligations",
            "local_path": "not_acquired",
            "sha256": "not_acquired",
            "processing_scope": "terrain_context_only_not_flood_observation_or_label",
            "processing_allowed": False,
            "reason_blocked": "source file not downloaded outside Git and checksum not recorded",
            "next_action": "select tiles, download outside Git, record checksum and citation text",
            "retrieved_at_utc": timestamp,
        },
    ]
    return pd.DataFrame(rows, columns=OPEN_CONTEXT_COLUMNS)


def write_open_context_manifest(
    output_path: str | Path,
    retrieved_at_utc: str | None = None,
) -> Path:
    """Write the open-source context acquisition manifest."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise ValueError("Open context manifest must be CSV.")
    target.parent.mkdir(parents=True, exist_ok=True)
    default_open_context_rows(retrieved_at_utc=retrieved_at_utc).to_csv(
        target,
        index=False,
    )
    return target
