from __future__ import annotations

import pytest

from floodguard.label_factory.contracts import DatasetRole
from floodguard.label_factory.tiling import (
    Bounds,
    GridContractError,
    ProjectedGridSpec,
    QueryCore,
    TileCore,
    make_query_region_id,
    make_tile_id,
    require_bounds_within_query_core,
    validate_event_id,
    validate_non_overlapping_cores,
)


def _grid() -> ProjectedGridSpec:
    return ProjectedGridSpec(crs="EPSG:32647", resolution_m=10, tile_size_cells=256)


def _tile(
    *,
    x_index: int = 123,
    y_index: int = 87,
    event_id: str = "TH-MAESAI-2024-09",
    role: DatasetRole = DatasetRole.TRAINING_AND_QUERY_POOL,
    grid: ProjectedGridSpec | None = None,
) -> TileCore:
    return TileCore(
        event_id=event_id,
        grid=grid or _grid(),
        x_index=x_index,
        y_index=y_index,
        dataset_role=role,
    )


def test_projected_grid_normalizes_crs_and_builds_stable_tokens() -> None:
    grid = ProjectedGridSpec(
        crs="epsg:32647",
        resolution_m=10.0,
        tile_size_cells=256,
    )

    assert grid.crs == "EPSG:32647"
    assert grid.crs_token == "UTM47N"
    assert grid.resolution_token == "10M"
    assert grid.grid_id.startswith("UTM47N_10M_G")
    assert len(grid.contract_sha256) == 64
    assert grid.tile_span_m == 2560.0
    assert grid.contract_key == ("EPSG:32647", "10M", 256, "0", "0")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"crs": "EPSG:4326", "resolution_m": 10},
        {"crs": "WGS84", "resolution_m": 10},
        {"crs": "EPSG:32647", "resolution_m": 0},
        {"crs": "EPSG:32647", "resolution_m": float("nan")},
        {"crs": "EPSG:32647", "resolution_m": 10, "tile_size_cells": 0},
    ],
)
def test_grid_rejects_geographic_crs_or_invalid_dimensions(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(GridContractError):
        ProjectedGridSpec(**kwargs)  # type: ignore[arg-type]


def test_tile_identifier_is_derived_from_event_and_projected_grid_indices() -> None:
    tile = _tile()

    assert tile.core_id == (
        f"TH-MAESAI-2024-09_{_grid().grid_id}_X00123_Y00087"
    )
    assert tile.tile_id == tile.core_id
    assert tile.core_id == make_tile_id(
        "TH-MAESAI-2024-09",
        _grid(),
        x_index=123,
        y_index=87,
    )
    assert tile.bounds == Bounds(
        min_x=314_880.0,
        min_y=222_720.0,
        max_x=317_440.0,
        max_y=225_280.0,
    )


def test_negative_global_tile_indices_have_unambiguous_identifiers() -> None:
    tile = _tile(x_index=-1, y_index=-12)

    assert tile.core_id.endswith("_XN00001_YN00012")
    assert tile.bounds.min_x == -2560.0
    assert tile.bounds.max_x == 0.0


def test_registered_grid_origin_changes_bounds_but_not_export_order() -> None:
    grid = ProjectedGridSpec(
        "EPSG:32647",
        resolution_m=10,
        tile_size_cells=256,
        origin_x=320_000,
        origin_y=2_200_000,
    )
    tile = _tile(x_index=1, y_index=2, grid=grid)

    assert tile.bounds == Bounds(
        min_x=322_560.0,
        min_y=2_205_120.0,
        max_x=325_120.0,
        max_y=2_207_680.0,
    )
    assert grid.contract_key[-2:] == ("320000", "2200000")


@pytest.mark.parametrize(
    "event_id",
    ["th-maesai-2024-09", "TH_MAESAI_2024_09", "TH--MAESAI", " TH-MAESAI"],
)
def test_event_identifier_must_already_be_canonical(event_id: str) -> None:
    with pytest.raises(GridContractError, match="event_id"):
        validate_event_id(event_id)


def test_query_identifier_and_bounds_are_stable_on_the_query_lattice() -> None:
    query = QueryCore(
        tile=_tile(),
        row_index=2,
        column_index=1,
        size_cells=64,
    )

    assert query.core_id == (
        f"TH-MAESAI-2024-09_{_grid().grid_id}_X00123_Y00087_R02_C01_S64"
    )
    assert query.query_region_id == query.core_id
    assert query.core_id == make_query_region_id(
        query.tile.core_id,
        row_index=2,
        column_index=1,
        size_cells=64,
    )
    assert query.bounds == Bounds(
        min_x=315_520.0,
        min_y=223_360.0,
        max_x=316_160.0,
        max_y=224_000.0,
    )
    assert query.tile.bounds.contains(query.bounds)


@pytest.mark.parametrize(
    "row, column, size, message",
    [
        (4, 0, 64, "outside"),
        (0, 4, 64, "outside"),
        (-1, 0, 64, "non-negative"),
        (0, 0, 48, "must divide"),
        (0, 0, 0, "positive"),
    ],
)
def test_query_core_must_be_a_complete_square_inside_the_tile(
    row: int,
    column: int,
    size: int,
    message: str,
) -> None:
    with pytest.raises(GridContractError, match=message):
        QueryCore(
            tile=_tile(),
            row_index=row,
            column_index=column,
            size_cells=size,
        )


def test_adjacent_tile_and_query_cores_are_non_overlapping() -> None:
    tiles = [_tile(x_index=123), _tile(x_index=124)]
    queries = [
        QueryCore(tile=tiles[0], row_index=0, column_index=0, size_cells=64),
        QueryCore(tile=tiles[0], row_index=0, column_index=1, size_cells=64),
        QueryCore(tile=tiles[1], row_index=0, column_index=0, size_cells=64),
    ]

    validate_non_overlapping_cores(tiles)
    validate_non_overlapping_cores(queries)


def test_non_overlap_validation_rejects_duplicate_or_mixed_size_overlap() -> None:
    tile = _tile()
    larger = QueryCore(tile=tile, row_index=0, column_index=0, size_cells=64)
    nested = QueryCore(tile=tile, row_index=0, column_index=0, size_cells=32)

    with pytest.raises(GridContractError, match="interiors overlap"):
        validate_non_overlapping_cores([larger, nested])
    with pytest.raises(GridContractError, match="Duplicate core identifier"):
        validate_non_overlapping_cores([larger, larger])


def test_same_event_cannot_silently_change_its_canonical_grid() -> None:
    ten_metre = _tile(x_index=0)
    twenty_metre = _tile(
        x_index=1,
        grid=ProjectedGridSpec("EPSG:32647", resolution_m=20),
    )

    with pytest.raises(GridContractError, match="more than one canonical grid"):
        validate_non_overlapping_cores([ten_metre, twenty_metre])

    shifted_origin = _tile(
        x_index=2,
        grid=ProjectedGridSpec("EPSG:32647", origin_x=10),
    )
    with pytest.raises(GridContractError, match="more than one canonical grid"):
        validate_non_overlapping_cores([ten_metre, shifted_origin])
    assert ten_metre.grid.grid_id != shifted_origin.grid.grid_id
    assert ten_metre.tile_id != shifted_origin.tile_id


def test_different_events_may_cover_the_same_geography() -> None:
    mae_sai = _tile(event_id="TH-MAESAI-2024-09")
    other_event = _tile(event_id="TH-HATYAI-2025-11")

    validate_non_overlapping_cores([mae_sai, other_event])


def test_annotation_bounds_must_remain_inside_query_core() -> None:
    query = QueryCore(
        tile=_tile(),
        row_index=0,
        column_index=0,
        size_cells=64,
    )
    inside = Bounds(
        min_x=query.bounds.min_x + 10,
        min_y=query.bounds.min_y + 10,
        max_x=query.bounds.max_x - 10,
        max_y=query.bounds.max_y - 10,
    )
    outside = Bounds(
        min_x=query.bounds.min_x - 10,
        min_y=query.bounds.min_y,
        max_x=query.bounds.max_x,
        max_y=query.bounds.max_y,
    )

    require_bounds_within_query_core(inside, query)
    with pytest.raises(GridContractError, match="outside query core"):
        require_bounds_within_query_core(outside, query)
