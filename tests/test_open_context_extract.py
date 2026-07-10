from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from floodguard.open_context_extract import (
    OpenContextExtractError,
    standardize_mae_sai_admin,
    validate_open_context_files,
)


GROUP_FILES = {
    "worldpop_population": "open_context/worldpop_population/pop.tif",
    "hdx_cod_ab": "open_context/hdx_cod_ab/admin.zip",
    "osm_geofabrik": "open_context/osm_geofabrik/roads.pbf",
    "copernicus_dem_glo30": "open_context/copernicus_dem_glo30/dem.tif",
}


def context_manifest(root: Path) -> pd.DataFrame:
    rows = []
    for group, relative in GROUP_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"fixture-{group}".encode()
        path.write_bytes(content)
        rows.append(
            {
                "source_name": group,
                "source_group": group,
                "local_path": f"<external_data_workspace>/{relative}",
                "sha256": hashlib.sha256(content).hexdigest(),
                "sha256_status": "recorded",
                "acquisition_status": "available_outside_git",
                "processing_scope": "candidate_context_only_not_flood_label",
                "processing_allowed": True,
                "license_status": "fixture",
                "retrieved_at_utc": "2026-07-10T00:00:00Z",
            }
        )
    return pd.DataFrame(rows)


def test_validate_open_context_files_checks_all_source_hashes(tmp_path: Path) -> None:
    manifest = context_manifest(tmp_path)

    paths = validate_open_context_files(
        manifest,
        external_data_root=tmp_path,
    )

    assert set(paths) == set(GROUP_FILES)
    assert all(path.exists() for path in paths.values())


def test_validate_open_context_files_rejects_checksum_mismatch(tmp_path: Path) -> None:
    manifest = context_manifest(tmp_path)
    manifest.loc[manifest["source_group"] == "worldpop_population", "sha256"] = "0" * 64

    with pytest.raises(OpenContextExtractError, match="checksum mismatch"):
        validate_open_context_files(manifest, external_data_root=tmp_path)


def test_standardize_mae_sai_admin_requires_eight_unique_adm3_rows() -> None:
    features = []
    for index in range(8):
        x0 = 99.8 + index * 0.01
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "adm3_pcode": f"TH57{index:04d}",
                    "adm3_name": f"Area {index}",
                    "adm3_name1": f"พื้นที่ {index}",
                    "adm2_pcode": "TH5709",
                    "adm2_name": "Mae Sai",
                    "adm1_pcode": "TH57",
                    "adm1_name": "Chiang Rai",
                    "area_sqkm": 10.0,
                    "valid_on": "2022-01-22",
                    "version": "v01",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [x0, 20.4],
                            [x0 + 0.01, 20.4],
                            [x0 + 0.01, 20.41],
                            [x0, 20.41],
                            [x0, 20.4],
                        ]
                    ],
                },
            }
        )

    result = standardize_mae_sai_admin(
        {"type": "FeatureCollection", "features": features}
    )

    assert len(result["features"]) == 8
    assert result["features"][0]["properties"]["district_name"] == "Mae Sai"
    assert result["features"][0]["properties"]["source_name"] == "HDX Thailand COD-AB"
