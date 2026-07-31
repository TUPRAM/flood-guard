from __future__ import annotations

from pathlib import Path

import pandas as pd

from floodguard.open_context_manifest import (
    OPEN_CONTEXT_COLUMNS,
    build_open_context_rows,
    default_open_context_rows,
    write_open_context_manifest,
)


def test_default_open_context_rows_are_blocked_context_only() -> None:
    rows = default_open_context_rows(retrieved_at_utc="2026-07-08T00:00:00Z")

    assert list(rows.columns) == list(OPEN_CONTEXT_COLUMNS)
    assert set(rows["source_group"]) == {
        "worldpop_population",
        "hdx_cod_ab",
        "osm_geofabrik",
        "copernicus_dem_glo30",
    }
    assert set(rows["processing_allowed"]) == {False}
    assert rows["local_path"].eq("not_acquired").all()
    assert rows["sha256"].eq("not_acquired").all()
    assert rows["sha256_status"].eq("not_recorded").all()
    assert rows["acquisition_status"].eq("not_acquired").all()
    assert rows["processing_scope"].str.contains("not_flood").all()


def test_write_open_context_manifest_writes_csv(tmp_path: Path) -> None:
    output = tmp_path / "open_context.csv"

    written = write_open_context_manifest(
        output,
        retrieved_at_utc="2026-07-08T00:00:00Z",
    )

    assert written == output
    frame = pd.read_csv(output)
    assert "WorldPop Thailand 100m" in set(frame["source_name"])
    assert "OpenStreetMap Thailand via Geofabrik" in set(frame["source_name"])
    assert "download_url" in frame.columns
    assert "sha256_status" in frame.columns
    output_bytes = output.read_bytes()
    assert b"\r\n" not in output_bytes
    assert output_bytes.endswith(b"\n")


def test_build_open_context_rows_records_existing_external_files(tmp_path: Path) -> None:
    root = tmp_path / "external"
    worldpop = root / "open_context" / "worldpop_population" / "tha_ppp_2020.tif"
    hdx = root / "open_context" / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
    osm = root / "open_context" / "osm_geofabrik" / "thailand-latest.osm.pbf"
    dem = root / "dem" / "Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif"
    for path, content in (
        (worldpop, b"worldpop"),
        (hdx, b"hdx"),
        (osm, b"osm"),
        (dem, b"dem"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    rows = build_open_context_rows(
        external_data_root=root,
        dem_path=dem,
        retrieved_at_utc="2026-07-09T00:00:00Z",
    )

    assert set(rows["processing_allowed"]) == {True}
    assert rows["sha256_status"].eq("recorded").all()
    assert rows["sha256"].str.len().eq(64).all()
    assert rows["local_path"].str.startswith("<external_data_workspace>/").all()
    assert not rows["local_path"].str.contains(str(tmp_path), regex=False).any()
    assert rows["processing_scope"].str.contains("not_flood").all()


def test_build_open_context_rows_blocks_missing_files(tmp_path: Path) -> None:
    rows = build_open_context_rows(
        external_data_root=tmp_path / "external",
        dem_path=tmp_path / "missing_dem.tif",
        retrieved_at_utc="2026-07-09T00:00:00Z",
    )

    assert set(rows["processing_allowed"]) == {False}
    assert rows["sha256"].eq("not_acquired").all()
    assert rows["sha256_status"].eq("not_recorded").all()
    assert rows["acquisition_status"].eq("missing_external_file").all()
    assert rows["reason_blocked"].str.contains("checksum not recorded").all()


def test_download_failure_is_recorded_without_aborting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import floodguard.open_context_manifest as manifest

    def fail_download(url: str, target: Path) -> None:
        raise RuntimeError(f"mock failed: {url}")

    monkeypatch.setattr(manifest, "_download_to_path", fail_download)

    rows = build_open_context_rows(
        external_data_root=tmp_path / "external",
        dem_path=tmp_path / "missing_dem.tif",
        download=True,
        retrieved_at_utc="2026-07-09T00:00:00Z",
    )

    assert rows["acquisition_status"].eq("download_failed").all()
    assert rows["reason_blocked"].str.contains("mock failed").all()
