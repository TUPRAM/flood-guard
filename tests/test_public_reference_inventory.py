from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from floodguard.public_reference_inventory import (
    PUBLIC_REFERENCE_COLUMNS,
    build_public_reference_manifest,
    extract_sentinel_asia_product_links,
    sentinel_asia_product_rows,
)

REPO_ROOT = Path(__file__).parents[1]


def test_default_public_reference_rows_cover_requested_sources() -> None:
    manifest = build_public_reference_manifest(retrieved_at_utc="2026-07-08T00:00:00Z")

    assert list(manifest.columns) == list(PUBLIC_REFERENCE_COLUMNS)
    source_names = set(manifest["source_name"])
    for expected in (
        "Copernicus Sentinel-1 via CDSE",
        "Copernicus Sentinel-2 via CDSE",
        "Copernicus EMS Rapid Mapping EMSR754",
        "Copernicus EMS Rapid Mapping EMSR756",
        "Sentinel Asia Northern Thailand 2024 event page",
        "UN Thailand Mae Sai public report page",
        "UNOSAT product 3991",
        "NASA MODIS/VIIRS NRT Global Flood Products",
        "WorldPop Thailand 100m",
        "OpenStreetMap Thailand via Geofabrik",
        "Copernicus DEM GLO-30",
        "HDX Thailand COD-AB",
        "THEOS-2 local hackathon samples",
        "Local hackathon Sentinel-1 TIFF",
        "Local hackathon Copernicus DEM packages",
    ):
        assert expected in source_names

    assert manifest["repo_storage"].str.contains("metadata").all()
    assert not manifest["repo_storage"].str.contains(".SAFE", regex=False).any()


def test_sentinel_asia_product_parser_extracts_public_product_links() -> None:
    html = """
    <a href="/EO/2024/article20240910TH/AIT/AIT-VAP001-TH.jpg">Download</a>
    <a href="/EO/2024/article20240910TH/AIT/AIT-VAP001-TH_sml.jpg">View</a>
    <a href="/EO/2024/article20240910TH/MBRSC/MBRSC_THAILAND_FLOOD-MAP-SHP.zip">
      Download
    </a>
    <a href="/not-this/file.zip">Other</a>
    """

    links = extract_sentinel_asia_product_links(html)
    rows = sentinel_asia_product_rows(links, retrieved_at_utc="2026-07-08T00:00:00Z")

    assert len(links) == 3
    assert any(row["data_or_product_type"] == "shapefile_zip" for row in rows)
    shp_row = next(row for row in rows if row["data_or_product_type"] == "shapefile_zip")
    assert shp_row["can_use_for_validation"] == "possible_after_geometry_and_license_review"
    assert shp_row["can_use_for_ml_labels"] == "not_cleared_for_ml_labels"
    jpg_row = next(row for row in rows if row["data_or_product_type"] == "map_or_quicklook_jpg")
    assert jpg_row["can_use_for_validation"] == "no_map_level_context_only"


def test_public_reference_manifest_includes_sentinel_asia_products_from_html() -> None:
    html = """
    <a href="/EO/2024/article20240910TH/AIT/AIT-VAP001-TH.zip">Download</a>
    <a href="/EO/2024/article20240910TH/AIT/AIT-VAP001-TH.zip">Duplicate</a>
    """

    manifest = build_public_reference_manifest(
        include_sentinel_asia_products=True,
        sentinel_asia_html=html,
        retrieved_at_utc="2026-07-08T00:00:00Z",
    )

    product_rows = manifest[manifest["source_group"] == "sentinel_asia_product"]
    assert len(product_rows) == 1
    assert product_rows.iloc[0]["source_url"].endswith("AIT/AIT-VAP001-TH.zip")
    assert product_rows.iloc[0]["repo_storage"] == "metadata_csv_only_no_product_zip_or_image_assets"


def test_public_reference_cli_offline_writes_seed_manifest(tmp_path: Path) -> None:
    output = tmp_path / "public_reference_candidate_manifest.csv"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_public_reference_manifest.py"),
            "--offline",
            "--retrieved-at",
            "2026-07-08T00:00:00Z",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Wrote" in result.stdout
    assert "Skipped live Sentinel Asia product scrape" in result.stdout
    frame = pd.read_csv(output)
    assert "Copernicus Sentinel-1 via CDSE" in set(frame["source_name"])
    assert "metadata_csv_only_no_SAFE_or_TIFF_assets" in set(frame["repo_storage"])
