from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from floodguard.cdse import (
    CDSE_OUTPUT_COLUMNS,
    build_cdse_products_url,
    get_cdse_profile,
    parse_cdse_products,
)

REPO_ROOT = Path(__file__).parents[1]


def test_build_cdse_products_url_encodes_profile_filters() -> None:
    profile = get_cdse_profile("hat_yai_2025", top=10)

    url = build_cdse_products_url(profile)

    assert "https://catalogue.dataspace.copernicus.eu/odata/v1/Products?" in url
    assert "Collection/Name+eq+'SENTINEL-1'" in url
    assert "contains(Name,'IW_GRDH_1SDV')" in url
    assert "2025-11-17T00:00:00.000Z" in url
    assert "2025-12-05T23:59:59.999Z" in url
    assert "POINT(100.47+7.01)" in url
    assert "$orderby=ContentDate/Start+asc" in url
    assert "$top=10" in url


def test_parse_cdse_products_handles_cog_and_safe_rows() -> None:
    profile = get_cdse_profile("hat_yai_2025")
    rows = parse_cdse_products(
        {
            "value": [
                {
                    "ContentDate": {"Start": "2025-11-23T23:03:09.290537Z"},
                    "Name": (
                        "S1A_IW_GRDH_1SDV_20251123T230309_20251123T230334_"
                        "062011_07C1DB_9231_COG.SAFE"
                    ),
                    "Id": "325e23d5-9ba6-439e-bac9-8d7efac83cac",
                    "Online": True,
                },
                {
                    "ContentDate": {"Start": "2025-11-23T23:03:09.290537Z"},
                    "Name": (
                        "S1A_IW_GRDH_1SDV_20251123T230309_20251123T230334_"
                        "062011_07C1DB_15C6.SAFE"
                    ),
                    "Id": "d80b81cb-c4aa-4dbb-a7de-8a1d01fca2dc",
                    "Online": True,
                },
            ]
        },
        profile,
        source_url="https://example.test/products",
    )

    assert list(rows[0]) == list(CDSE_OUTPUT_COLUMNS)
    assert rows[0]["product_storage_type"] == "COG"
    assert rows[0]["candidate_role"] == "event-window COG candidate"
    assert rows[0]["mission_platform_prefix"] == "S1A"
    assert rows[1]["product_storage_type"] == "SAFE"
    assert rows[1]["candidate_role"] == "event-window SAFE alternative"
    assert rows[1]["online_status"] is True
    assert rows[0]["source_url"] == "https://example.test/products"


def test_cdse_cli_dry_run_prints_url_without_network() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "query_cdse_metadata.py"),
            "--profile",
            "mae_sai_2024",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "catalogue.dataspace.copernicus.eu/odata/v1/Products" in result.stdout
    assert "POINT(99.88+20.43)" in result.stdout
    assert "2024-09-01T00:00:00.000Z" in result.stdout
