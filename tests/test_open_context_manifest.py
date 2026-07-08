from __future__ import annotations

from pathlib import Path

import pandas as pd

from floodguard.open_context_manifest import (
    OPEN_CONTEXT_COLUMNS,
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
