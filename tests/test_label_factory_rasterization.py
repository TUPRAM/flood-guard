from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.contracts import WeakSeedLabel
from floodguard.label_factory.rasterization import (
    RasterizationError,
    load_geojson_polygons,
    rasterize_positive_unlabeled_seed,
    write_weak_seed_outputs,
)
from floodguard.label_factory.tiling import Bounds


def _square(min_x: float, min_y: float, max_x: float, max_y: float):
    return (
        (
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
            (min_x, min_y),
        ),
    )


def test_polygon_interior_is_weak_positive_and_exterior_is_unreviewed() -> None:
    raster = rasterize_positive_unlabeled_seed(
        [_square(0, 0, 2, 2)],
        bounds=Bounds(0, 0, 4, 4),
        width_cells=4,
        height_cells=4,
        crs="EPSG:32647",
    )

    assert raster.values == (
        (WeakSeedLabel.UNREVIEWED,) * 4,
        (WeakSeedLabel.UNREVIEWED,) * 4,
        (WeakSeedLabel.WEAK_POSITIVE, WeakSeedLabel.WEAK_POSITIVE, WeakSeedLabel.UNREVIEWED, WeakSeedLabel.UNREVIEWED),
        (WeakSeedLabel.WEAK_POSITIVE, WeakSeedLabel.WEAK_POSITIVE, WeakSeedLabel.UNREVIEWED, WeakSeedLabel.UNREVIEWED),
    )
    assert all(value is not WeakSeedLabel.WEAK_POSITIVE for value in raster.values[0])


def test_hole_and_boundary_buffer_are_deterministic() -> None:
    outer = _square(0, 0, 4, 4)[0]
    hole = _square(1, 1, 3, 3)[0]
    first = rasterize_positive_unlabeled_seed(
        [(outer, hole)],
        bounds=Bounds(0, 0, 4, 4),
        width_cells=4,
        height_cells=4,
        crs="EPSG:32647",
        boundary_buffer_cells=1,
    )
    second = rasterize_positive_unlabeled_seed(
        [(outer, hole)],
        bounds=Bounds(0, 0, 4, 4),
        width_cells=4,
        height_cells=4,
        crs="EPSG:32647",
        boundary_buffer_cells=1,
    )

    assert first.values == second.values
    assert any(
        value is WeakSeedLabel.WEAK_UNCERTAIN
        for row in first.values
        for value in row
    )


def test_geojson_loader_accepts_multipolygon_and_rejects_lines(tmp_path: Path) -> None:
    good = tmp_path / "seed.geojson"
    good.write_text(
        json.dumps(
            {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                    [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]],
                ],
            }
        ),
        encoding="utf-8",
    )
    assert len(load_geojson_polygons(good)) == 2

    bad = tmp_path / "line.geojson"
    bad.write_text(
        json.dumps({"type": "LineString", "coordinates": [[0, 0], [1, 1]]}),
        encoding="utf-8",
    )
    with pytest.raises(RasterizationError, match="Polygon or MultiPolygon"):
        load_geojson_polygons(bad)


def test_written_manifest_retains_weak_provenance_and_no_absolute_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "Polygon",
                "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
            }
        ),
        encoding="utf-8",
    )
    raster = rasterize_positive_unlabeled_seed(
        load_geojson_polygons(source),
        bounds=Bounds(0, 0, 4, 4),
        width_cells=4,
        height_cells=4,
        crs="EPSG:32647",
    )
    written = write_weak_seed_outputs(
        source,
        raster,
        raster_output_path=tmp_path / "seed.csv",
        manifest_output_path=tmp_path / "manifest.csv",
        seed_id="MAESAI-WEAK-SEED-V1",
        event_id="TH-MAESAI-2024-09",
        grid_id="UTM47N_10M",
        query_region_id="QUERY-1",
        tile_id="TILE-1",
        grid_contract_sha256="c" * 64,
        query_manifest_sha256="d" * 64,
        source_timestamp="2024-09-15T23:16:01Z",
        assumptions="Legacy polygon; exterior is unreviewed.",
    )

    manifest = pd.read_csv(written["manifest"])
    cells = pd.read_csv(written["raster"])
    assert manifest.loc[0, "source_type"] == "positive_unlabeled_weak_seed"
    assert manifest.loc[0, "query_manifest_sha256"] == "d" * 64
    assert manifest.loc[0, "source_file_hint"] == "source.geojson"
    assert str(tmp_path) not in manifest.to_csv(index=False)
    assert manifest.loc[0, "eligible_for_fpps"] == False
    assert set(cells["weak_seed_code"]) == {1, 255}
