"""Age exposure: dependent share per unit, on invented rasters and polygons.

No test here reads a real raster or boundary, and none computes a
vulnerability component, an FPPS, a class or an ensemble. The tests of the
committed Mae Sai table read that table and its receipt only: they recompute
nothing. The tests of the builder's code check read source files, the signed
protocol and the committed anchor receipt.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Iterator

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.windows import Window
from shapely.geometry import box
from shapely.ops import transform

from floodguard.age_exposure import (
    ALLOCATION_RULES,
    ALLOCATION_STATEMENT,
    CELLS_ANY_TOUCHING,
    CELLS_WHOLLY_INSIDE,
    IN_LAYER_MIN_FRACTION,
    PROJECTED_AREA_FRACTION,
    RANGE_STATEMENT,
    AgeCell,
    AgeExposureError,
    UnitLayer,
    age_exposure_frame,
    age_exposure_table,
    age_grid_reading,
    allocate_cells,
    allocation_range,
    border_cell_summary,
    composition_reading,
    frame_border_cells,
    frame_window,
    read_grid_counts,
    read_unit_cells,
    rescale_2020_counts_to_2024,
    share_clusters,
    support_summary,
    unit_age_exposure,
)
from floodguard.evidence_age_surface import AGE_BANDS, CHILD_BANDS, OLDER_BANDS, summarize_geometry
from floodguard.normalisation import dependent_share

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
MODULE = ROOT / "src" / "floodguard" / "age_exposure.py"
SCRIPT = ROOT / "scripts" / "build_age_exposure.py"
TABLE = ROOT / "outputs" / "planning_v1" / "age_exposure_mae_sai_v1.json"
RECEIPT = ROOT / "outputs" / "planning_v1" / "age_exposure_mae_sai_v1_receipt.json"
ANCHOR_RECEIPT = ROOT / "outputs" / "planning_v1" / "national_vulnerability_anchors_v1.json"

NODATA = -99999.0
# An invented grid of 6 columns by 5 rows of 0.01 degree cells. The three west
# columns hold 100 residents a cell with a dependent share of 0.55; the three
# east columns hold 120 residents a cell with a share of 0.625.
ORIGIN = (99.79, 20.44)
CELL = 0.01
ROWS, COLS = 5, 6
WEST = {"children": 5.0, "older": 5.0, "other": 5.0}
EAST = {"children": 10.0, "older": 5.0, "other": 5.0}


def _band_grid(band: str) -> np.ndarray:
    kind = "children" if band in CHILD_BANDS else "older" if band in OLDER_BANDS else "other"
    grid = np.empty((ROWS, COLS), dtype="float32")
    grid[:, :3] = WEST[kind]
    grid[:, 3:] = EAST[kind]
    return grid


def _write_rasters(folder: Path, *, missing: dict[str, list[tuple[int, int]]] | None = None,
                   value: float | None = None) -> dict[str, Path]:
    """Write the 20 invented age rasters and return their paths by band."""

    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for band in AGE_BANDS:
        grid = _band_grid(band) if value is None else np.full((ROWS, COLS), value, dtype="float32")
        for row, col in (missing or {}).get(band, []) + (missing or {}).get("all", []):
            grid[row, col] = NODATA
        path = folder / f"tha_t_{band}_2024_CN_1km_R2025A_UA_v1.tif"
        with rasterio.open(path, "w", driver="GTiff", width=COLS, height=ROWS, count=1, dtype="float32",
                           crs="EPSG:4326", transform=from_origin(*ORIGIN, CELL, CELL), nodata=NODATA) as target:
            target.write(grid, 1)
        paths[band] = path
    return paths


@pytest.fixture()
def open_rasters(tmp_path: Path) -> Iterator[Any]:
    """Return a function that writes invented rasters and opens them; everything is closed afterwards."""

    opened: list[rasterio.io.DatasetReader] = []

    def _open(**arguments: Any) -> dict[str, rasterio.io.DatasetReader]:
        paths = _write_rasters(tmp_path / f"rasters_{len(opened)}", **arguments)
        datasets = {band: rasterio.open(path) for band, path in paths.items()}
        opened.extend(datasets.values())
        return datasets

    yield _open
    for dataset in opened:
        dataset.close()


# The unit's edges run through the middle of cells: nine cells (two west columns and one east column, three
# rows) lie wholly inside, twelve are half inside and the four corner cells a quarter. That is 10 cells' worth
# of west counts and 6 of east counts.
UNIT = box(99.795, 20.395, 99.835, 20.435)
UNIT_RESIDENTS = 10 * 100 + 6 * 120
UNIT_DEPENDANTS = 10 * 55 + 6 * 75
# Two units that lie in west cells only and in east cells only.
WEST_UNIT = box(99.802, 20.402, 99.818, 20.428)
EAST_UNIT = box(99.832, 20.402, 99.848, 20.428)


def test_the_counts_of_record_are_those_of_the_function_behind_the_anchors(open_rasters) -> None:
    rasters = open_rasters()
    record = unit_age_exposure(UNIT, rasters)
    summary = summarize_geometry(UNIT, rasters)
    assert record["status"] == "modelled_research_estimate"
    assert record["residents"] == summary["population_estimate"]
    assert record["children_0_14"] == summary["children_0_14_estimate"]
    assert record["older_60_plus"] == summary["older_60_plus_estimate"]
    assert record["other_15_59"] == summary["other_15_59_estimate"]
    assert record["dependent_share"] == dependent_share(
        summary["children_0_14_estimate"], summary["older_60_plus_estimate"], summary["population_estimate"])
    assert record["residents"] == pytest.approx(UNIT_RESIDENTS, rel=1e-3)
    assert record["dependent_share"] == pytest.approx(UNIT_DEPENDANTS / UNIT_RESIDENTS, rel=1e-4)
    assert record["dependent_share_unavailable_reason"] is None
    assert record["allocation_range"][PROJECTED_AREA_FRACTION] == record["dependent_share"]


def test_age_cells_and_supported_area_are_reported(open_rasters) -> None:
    record = unit_age_exposure(UNIT, open_rasters())
    cells = record["age_cells"]
    assert cells == {
        "with_valid_counts": 25, "wholly_inside": 9, "partly_inside": 16, "without_valid_counts": 0,
        "cell_equivalents": pytest.approx(16.0, rel=1e-3),
    }
    area = record["area"]
    assert area["supported_km2"] == pytest.approx(area["unit_km2"], rel=1e-4)
    assert area["supported_fraction"] == pytest.approx(1.0, abs=1e-4)
    assert area["unsupported_km2"] == 0.0 and area["unsupported_fraction"] == 0.0
    assert abs(area["reconciliation_residual_km2"]) < 1e-3
    assert record["band_mask_mismatch"] is False


def test_the_range_spans_cells_wholly_inside_and_any_touching(open_rasters) -> None:
    record = unit_age_exposure(UNIT, open_rasters())
    spread = record["allocation_range"]
    inside, touching = spread[CELLS_WHOLLY_INSIDE], spread[CELLS_ANY_TOUCHING]
    assert inside["cells"] == 9 and inside["residents"] == pytest.approx(960.0)
    assert inside["dependent_share"] == pytest.approx((6 * 55 + 3 * 75) / 960)
    assert touching["cells"] == 25 and touching["residents"] == pytest.approx(15 * 100 + 10 * 120)
    assert touching["dependent_share"] == pytest.approx((15 * 55 + 10 * 75) / 2700)
    assert spread["low"] == inside["dependent_share"] and spread["high"] == touching["dependent_share"]
    assert spread["low"] < record["dependent_share"] < spread["high"]
    assert spread["other_allocations_available"] == 2
    assert spread["value_of_record_between_the_two_other_allocations"] is True


def test_low_and_high_are_three_allocations_and_not_a_bound() -> None:
    """The value of record can lie outside both other allocations, and a fourth allocation outside low and high."""

    def cell(col: int, fraction: float, dependants: float) -> AgeCell:
        return AgeCell(0, col, fraction, fraction * 1e6, 100.0, dependants, 0.0)

    cells = [cell(0, 1.0, 50.0), cell(1, 0.9, 90.0), cell(2, 0.1, 10.0)]
    spread = allocation_range(cells)
    assert spread[CELLS_WHOLLY_INSIDE]["dependent_share"] == pytest.approx(0.5)
    assert spread[CELLS_ANY_TOUCHING]["dependent_share"] == pytest.approx(0.5)
    assert spread[PROJECTED_AREA_FRACTION] == pytest.approx(132 / 200)
    # Low and high are the smallest and the largest of the three, so they hold the value of record.
    assert spread["low"] == pytest.approx(0.5) and spread["high"] == pytest.approx(0.66)
    assert spread["value_of_record_between_the_two_other_allocations"] is False
    # A fourth allocation of the same cells (the one cell that is nine tenths inside, counted alone) gives 0.9.
    assert 90.0 / 100.0 > spread["high"]
    # The text written into every table says so, and makes no claim of a bound.
    assert "not a bound on the allocation error" in RANGE_STATEMENT
    assert "a narrow range does not show that the share is precise" in RANGE_STATEMENT
    assert "extreme" not in RANGE_STATEMENT and "how far" not in RANGE_STATEMENT


def test_a_unit_with_no_cell_wholly_inside_has_one_other_allocation_only(open_rasters) -> None:
    small = box(99.8125, 20.4125, 99.8175, 20.4175)  # inside one west cell (row 2, column 2)
    record = unit_age_exposure(small, open_rasters())
    spread = record["allocation_range"]
    assert record["age_cells"]["with_valid_counts"] == 1 and record["age_cells"]["wholly_inside"] == 0
    assert spread[CELLS_WHOLLY_INSIDE] == {"cells": 0, "residents": 0.0, "dependent_share": None}
    assert spread["other_allocations_available"] == 1
    assert spread["value_of_record_between_the_two_other_allocations"] is None
    assert spread["low"] == pytest.approx(0.55) and spread["high"] == pytest.approx(0.55)
    assert record["dependent_share"] == pytest.approx(0.55)


# --- Cells that lie partly outside every unit of the boundary layer --------------------------------------------------

# Every edge of these units runs through the middle of cells, as the edges of UNIT do, so no cell is "almost"
# covered. LAYER_A and LAYER_B share an edge through the middle of column 3. Together they cover the middle of
# the grid: rows 1-3 in full and half of rows 0 and 4; half of column 0, columns 1-4 and half of column 5.
LAYER_A = box(99.795, 20.395, 99.825, 20.435)
LAYER_B = box(99.825, 20.395, 99.845, 20.435)
# One unit alone, over west cells (column 1 by half, column 2) and east cells (columns 3-4, column 5 by half).
LONE_UNIT = box(99.805, 20.395, 99.845, 20.435)


def _projected_km2(geometry: Any) -> float:
    projector = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
    return transform(projector, geometry).area / 1e6


def _cell_box(row: int, col: int) -> Any:
    west, north = ORIGIN[0] + col * CELL, ORIGIN[1] - row * CELL
    return box(west, north - CELL, west + CELL, north)


def test_a_cell_shared_by_two_units_is_not_a_border_cell_and_a_cell_no_unit_covers_is(open_rasters) -> None:
    rasters = open_rasters()
    layer = UnitLayer([LAYER_A, LAYER_B])
    assert len(layer) == 2
    west = unit_age_exposure(LAYER_A, rasters, layer=layer)
    east = unit_age_exposure(LAYER_B, rasters, layer=layer)
    # The west unit overlaps columns 0-3. Six cells lie wholly inside it. In rows 1-3 the cells of column 3 are
    # split between the two units, so the layer covers them in full: they are edge cells, not border cells.
    assert west["age_cells"] == {
        "with_valid_counts": 20, "wholly_inside": 6, "partly_inside": 14, "without_valid_counts": 0,
        "cell_equivalents": pytest.approx(12.0, rel=1e-3),
    }
    border = west["cells_partly_outside_every_unit"]
    assert border["measured"] is True and border["cells"] == 11  # column 0, and rows 0 and 4 of columns 1-3
    assert border["residents_the_unit_takes_from_them"] == pytest.approx(200 + 200 + 60, rel=1e-3)
    assert border["dependent_share_of_what_the_unit_takes_from_them"] == pytest.approx(257.5 / 460, rel=1e-3)
    assert border["residents_from_the_other_cells"] == pytest.approx(600 + 180, rel=1e-3)
    assert border["dependent_share_from_the_other_cells"] == pytest.approx(442.5 / 780, rel=1e-3)
    assert border["residents_of_those_cells_in_no_unit"] == pytest.approx(300 + 200 + 120, rel=1e-3)

    # The east unit: the cells of column 5 and of rows 0 and 4 are partly in no unit; column 3 in rows 1-3 is not.
    border = east["cells_partly_outside_every_unit"]
    assert border["cells"] == 9
    assert border["residents_the_unit_takes_from_them"] == pytest.approx(420.0, rel=1e-3)
    assert border["residents_from_the_other_cells"] == pytest.approx(540.0, rel=1e-3)
    assert border["share_of_the_units_residents"] == pytest.approx(420 / 960, rel=1e-3)
    assert border["dependent_share_of_what_the_unit_takes_from_them"] == pytest.approx(0.625)
    assert border["residents_of_those_cells_in_no_unit"] == pytest.approx(600.0, rel=1e-3)
    cells = [_cell_box(row, col) for row, col in
             [(0, 3), (4, 3), (0, 4), (4, 4), (0, 5), (1, 5), (2, 5), (3, 5), (4, 5)]]
    in_no_unit = sum(_projected_km2(cell.difference(LAYER_A.union(LAYER_B))) for cell in cells)
    assert border["area_of_those_cells_in_no_unit_km2"] == pytest.approx(in_no_unit, rel=1e-3)
    # The split describes the counts of record; it changes none of them.
    assert east["residents"] == pytest.approx(
        border["residents_the_unit_takes_from_them"] + border["residents_from_the_other_cells"])
    assert east == {**unit_age_exposure(LAYER_B, rasters), "cells_partly_outside_every_unit": border}


def test_border_cells_split_the_share_of_record_into_two_parts(open_rasters) -> None:
    rasters = open_rasters()
    record = unit_age_exposure(LONE_UNIT, rasters, layer=UnitLayer([LONE_UNIT]))
    border = record["cells_partly_outside_every_unit"]
    # Every cell on the unit's edge lies partly in no unit: 16 of its 25 cells.
    assert border["cells"] == 16 == record["age_cells"]["partly_inside"]
    assert border["residents_the_unit_takes_from_them"] == pytest.approx(200 + 240 + 100 + 240, rel=1e-3)
    assert border["dependent_share_of_what_the_unit_takes_from_them"] == pytest.approx(465 / 780, rel=1e-3)
    assert border["residents_from_the_other_cells"] == pytest.approx(300 + 720, rel=1e-6)
    assert border["dependent_share_from_the_other_cells"] == pytest.approx(615 / 1020)
    assert border["residents_of_those_cells_in_no_unit"] == pytest.approx(1000.0, rel=1e-3)
    # The two parts add up to the share of record.
    parts = (border["residents_the_unit_takes_from_them"] * border["dependent_share_of_what_the_unit_takes_from_them"]
             + border["residents_from_the_other_cells"] * border["dependent_share_from_the_other_cells"])
    assert parts / record["residents"] == pytest.approx(record["dependent_share"])
    assert record["dependent_share"] == pytest.approx(1080 / 1800, rel=1e-3)

    # Without a layer the cells are not measured, and nothing is guessed.
    unmeasured = unit_age_exposure(LONE_UNIT, rasters)["cells_partly_outside_every_unit"]
    assert unmeasured["measured"] is False and all(value is None for key, value in unmeasured.items() if key != "measured")
    assert all(cell.layer_fraction is None and cell.partly_outside_every_unit is None
               for cell in read_unit_cells(LONE_UNIT, rasters))


def test_a_cell_counts_as_inside_the_layer_within_a_stated_tolerance() -> None:
    def cell(col: int, in_layer: float | None, residents: float | None = 100.0) -> AgeCell:
        counts = (residents, 30.0, 20.0) if residents is not None else (None, None, None)
        return AgeCell(0, col, 0.5, 5e5, *counts, layer_fraction=in_layer)

    inside, just_inside, outside = cell(0, 1.0), cell(1, IN_LAYER_MIN_FRACTION), cell(2, 0.75)
    assert [item.partly_outside_every_unit for item in (inside, just_inside, outside)] == [False, False, True]
    assert outside.cell_m2 == pytest.approx(1e6)
    summary = border_cell_summary([inside, just_inside, outside, cell(3, None, residents=None)])
    assert summary["cells"] == 1 and summary["residents_the_unit_takes_from_them"] == 50.0
    assert summary["residents_of_those_cells_in_no_unit"] == 25.0
    assert summary["area_of_those_cells_in_no_unit_km2"] == pytest.approx(0.25)
    assert summary["residents_from_the_other_cells"] == 100.0
    # A cell with no valid count is no border cell: it has no count to allocate.
    assert border_cell_summary([cell(3, None, residents=None)])["cells"] == 0
    with pytest.raises(AgeExposureError, match="at least one unit"):
        UnitLayer([])


def test_the_frame_counts_a_border_cell_once(tmp_path: Path) -> None:
    paths = _write_rasters(tmp_path / "rasters")
    # LAYER_B cut in two through the middle of row 2: both halves overlap the cell of row 2 in column 5.
    north = box(99.825, 20.415, 99.845, 20.435)
    south = box(99.825, 20.395, 99.845, 20.415)
    frame = age_exposure_frame([("N", north), ("S", south)], paths, layer_units=[LAYER_A, north, south])
    by_unit = {row["unit_id"]: row["cells_partly_outside_every_unit"] for row in frame["units"]}
    # Each half has five border cells; the cell of row 2 in column 5 is one of them in both, so the frame has nine.
    assert by_unit["N"]["cells"] == by_unit["S"]["cells"] == 5
    assert frame["border_cells"]["measured"] is True and frame["border_cells"]["distinct_cells"] == 9
    assert frame["border_cells"]["residents_in_those_cells"] == pytest.approx(9 * 120.0)
    assert frame["border_cells"]["residents_of_those_cells_in_no_unit"] == pytest.approx(600.0, rel=1e-3)
    assert frame["border_cells"]["residents_the_frames_units_take_from_them"] == pytest.approx(
        by_unit["N"]["residents_the_unit_takes_from_them"] + by_unit["S"]["residents_the_unit_takes_from_them"])
    assert frame["border_cells"]["residents_the_frames_units_take_from_them"] == pytest.approx(420.0, rel=1e-3)
    # The per-unit figures count the shared cell twice; the frame's figure does not.
    assert (by_unit["N"]["residents_of_those_cells_in_no_unit"] + by_unit["S"]["residents_of_those_cells_in_no_unit"]
            == pytest.approx(660.0, rel=1e-3))
    # Without a layer nothing is measured, and the rows are those of age_exposure_table.
    plain = age_exposure_frame([("N", north), ("S", south)], paths, grid_reading=False)
    assert plain["border_cells"]["measured"] is False and plain["border_cells"]["distinct_cells"] is None
    assert plain["age_grid_reading"] is None
    assert plain["units"] == age_exposure_table([("S", south), ("N", north)], paths)
    assert all(row["cells_partly_outside_every_unit"]["measured"] is False for row in plain["units"])
    assert frame_border_cells({})["distinct_cells"] == 0


# --- The reading of the age grid -------------------------------------------------------------------------------------


def test_composition_reading_counts_the_cells_that_share_a_dependent_share() -> None:
    residents = np.array([[100.0, 100.0, 100.0, 50.0], [200.0, 0.0, 7.0, 40.0]])
    dependants = np.array([[40.0, 40.0, 40.0, 30.0], [80.0, 0.0, 7.0, 16.0000001]])
    valid = np.array([[True, True, True, True], [True, True, False, True]])
    reading = composition_reading(residents, dependants, valid, min_cells=3)
    assert reading["cells"] == 8 and reading["cells_with_valid_counts"] == 7
    assert reading["cells_without_valid_counts"] == 1 and reading["valid_cells_with_zero_residents"] == 1
    assert reading["populated_cells"] == 6 and reading["residents"] == 590.0
    assert reading["dependent_share_of_all_residents"] == pytest.approx(246.0000001 / 590.0)
    # Five cells have a share of 0.4 to six decimal places (one of them only after rounding); one has 0.6.
    assert reading["same_share_groups"] == {
        "decimals": 6, "min_cells": 3, "groups": 1, "cells": 5, "residents": 540.0,
        "share_of_populated_cells": pytest.approx(5 / 6),
    }
    assert composition_reading(residents, dependants, valid, decimals=9, min_cells=3)["same_share_groups"]["cells"] == 4
    assert composition_reading(residents, dependants, valid, min_cells=6)["same_share_groups"]["groups"] == 0
    empty = composition_reading(np.zeros((2, 2)), np.zeros((2, 2)), np.zeros((2, 2), dtype=bool))
    assert empty["populated_cells"] == 0 and empty["dependent_share_of_all_residents"] is None
    assert empty["same_share_groups"]["share_of_populated_cells"] is None
    for arguments in ({"decimals": -1}, {"decimals": True}, {"min_cells": 0}, {"min_cells": 2.5}):
        with pytest.raises(AgeExposureError):
            composition_reading(residents, dependants, valid, **arguments)
    with pytest.raises(AgeExposureError, match="same shape"):
        composition_reading(residents, dependants[:1], valid)


def test_share_clusters_cut_where_neighbouring_shares_are_further_apart_than_the_gap() -> None:
    shares = [0.40555, 0.40551, 0.40560, 0.44091, 0.3516, 0.40678, 0.40679]
    residents = [10.0, 20.0, 30.0, 5.0, 7000.0, 1.0, 2.0]
    result = share_clusters(shares, residents, gap=1e-4, min_cells=2)
    assert result["gap"] == 1e-4 and result["min_cells"] == 2
    assert result["clusters"] == [
        {"lowest_share": 0.40551, "highest_share": 0.40560, "cells": 3, "residents": 60.0},
        {"lowest_share": 0.40678, "highest_share": 0.40679, "cells": 2, "residents": 3.0},
    ]
    assert result["smaller_clusters"] == {
        "clusters": 2, "cells": 2, "residents": 7005.0, "lowest_share": 0.3516, "highest_share": 0.44091,
    }
    # A wider gap chains the neighbours together.
    assert [cluster["cells"] for cluster in share_clusters(shares, residents, gap=0.002, min_cells=2)["clusters"]] == [5]
    nothing = share_clusters([], [])
    assert nothing["clusters"] == [] and nothing["smaller_clusters"]["clusters"] == 0
    assert nothing["smaller_clusters"]["lowest_share"] is None
    for arguments in ({"gap": 0.0}, {"gap": float("nan")}, {"min_cells": 0}):
        with pytest.raises(AgeExposureError):
            share_clusters(shares, residents, **arguments)
    with pytest.raises(AgeExposureError, match="same length"):
        share_clusters(shares, residents[:2])


def test_the_grid_reading_describes_a_window_and_the_whole_grid(open_rasters) -> None:
    # One cell has no count in one band, and one has no count at all.
    rasters = open_rasters(missing={"35": [(0, 0)], "all": [(4, 5)]})
    residents, dependants, valid = read_grid_counts(rasters)
    assert residents.shape == (ROWS, COLS) and int(valid.sum()) == 28
    assert residents[0, 0] == 0.0 and dependants[4, 5] == 0.0  # no count where a band is missing
    assert residents[1, 1] == 100.0 and dependants[1, 1] == 55.0 and dependants[1, 4] == 75.0
    window = Window(1, 1, 5, 3)  # columns 1-5, rows 1-3
    reading = age_grid_reading(rasters, window)
    part = reading["frame_window"]
    assert (part["row_off"], part["col_off"], part["height"], part["width"]) == (1, 1, 3, 5)
    assert part["bounds_west_south_east_north"] == pytest.approx([99.80, 20.40, 99.85, 20.43])
    assert part["cells"] == 15 and part["populated_cells"] == 15 and part["residents"] == pytest.approx(6 * 100 + 9 * 120)
    # Neither composition reaches the 20 cells of the default rule; the clusters show both.
    assert part["same_share_groups"]["groups"] == 0 and part["same_share_groups"]["min_cells"] == 20
    assert part["share_clusters"]["clusters"] == []
    assert part["share_clusters"]["smaller_clusters"] == {
        "clusters": 2, "cells": 15, "residents": pytest.approx(1680.0),
        "lowest_share": pytest.approx(0.55), "highest_share": pytest.approx(0.625),
    }
    whole = reading["whole_grid"]
    assert (whole["height"], whole["width"], whole["cells"]) == (ROWS, COLS, 30)
    assert whole["cells_with_valid_counts"] == 28 and whole["cells_without_valid_counts"] == 2
    assert whole["residents"] == pytest.approx(14 * 100 + 14 * 120)
    assert whole["dependent_share_of_all_residents"] == pytest.approx((14 * 55 + 14 * 75) / 3080)
    with pytest.raises(AgeExposureError, match="20 age bands"):
        read_grid_counts({band: source for band, source in rasters.items() if band != "10"})


def test_the_frame_window_is_the_smallest_window_that_holds_the_units_cells(tmp_path: Path) -> None:
    paths = _write_rasters(tmp_path / "rasters")
    frame = age_exposure_frame([("W", WEST_UNIT), ("E", EAST_UNIT)], paths)
    window = frame["age_grid_reading"]["frame_window"]
    assert (window["row_off"], window["col_off"], window["height"], window["width"]) == (1, 1, 3, 5)
    assert frame["age_grid_reading"]["whole_grid"]["populated_cells"] == 30
    assert frame_window({"A": [AgeCell(7, 3, 1.0, 1e6, None, None, None)],
                         "B": [AgeCell(2, 9, 0.5, 5e5, 1.0, 0.0, 0.0)]}) == Window(3, 2, 7, 6)
    with pytest.raises(AgeExposureError, match="no cell"):
        frame_window({"A": []})


def test_cells_without_a_valid_count_are_unsupported_area_not_zero(open_rasters) -> None:
    full = unit_age_exposure(UNIT, open_rasters())
    # One west cell wholly inside the unit has no count in any band.
    holed = unit_age_exposure(UNIT, open_rasters(missing={"all": [(2, 1)]}))
    assert holed["status"] == "modelled_research_estimate" and holed["band_mask_mismatch"] is False
    assert holed["residents"] == pytest.approx(full["residents"] - 100.0, rel=1e-6)
    assert holed["age_cells"]["with_valid_counts"] == 24 and holed["age_cells"]["without_valid_counts"] == 1
    assert holed["age_cells"]["wholly_inside"] == 8
    area = holed["area"]
    assert area["unsupported_in_cells_without_valid_counts_km2"] == pytest.approx(area["unit_km2"] / 16, rel=1e-3)
    assert area["unsupported_km2"] == area["unsupported_in_cells_without_valid_counts_km2"]
    assert area["unsupported_outside_the_age_grid_km2"] == 0.0
    assert area["supported_fraction"] == pytest.approx(15 / 16, rel=1e-3)
    assert area["supported_fraction"] + area["unsupported_fraction"] == pytest.approx(1.0, abs=1e-4)
    assert holed["allocation_range"][CELLS_ANY_TOUCHING]["cells"] == 24

    # A cell that lacks one band only is unsupported too, and the record says the band masks differ.
    one_band = unit_age_exposure(UNIT, open_rasters(missing={"35": [(2, 1)]}))
    assert one_band["status"] == "partial_band_coverage" and one_band["band_mask_mismatch"] is True
    assert one_band["residents"] == holed["residents"]
    assert one_band["age_cells"] == holed["age_cells"]


def test_area_outside_the_age_grid_is_unsupported(open_rasters) -> None:
    beyond = box(99.78, 20.405, 99.795, 20.425)  # the west two thirds lie outside the grid
    record = unit_age_exposure(beyond, open_rasters())
    area = record["area"]
    assert area["unsupported_outside_the_age_grid_km2"] == pytest.approx(area["unit_km2"] * 2 / 3, rel=1e-3)
    assert area["unsupported_in_cells_without_valid_counts_km2"] == 0.0
    assert area["supported_fraction"] == pytest.approx(1 / 3, rel=1e-3)
    assert area["unsupported_fraction"] == pytest.approx(2 / 3, rel=1e-3)
    assert abs(area["reconciliation_residual_km2"]) < 1e-3
    # Half of one cell and a quarter of two: one west cell's worth of residents.
    assert record["age_cells"]["with_valid_counts"] == 3 and record["residents"] == pytest.approx(100.0, rel=1e-3)


def test_no_valid_cell_and_no_resident_give_no_share(open_rasters) -> None:
    every_cell = [(row, col) for row in range(ROWS) for col in range(COLS)]
    absent = unit_age_exposure(UNIT, open_rasters(missing={"all": every_cell}))
    assert absent["status"] == "unavailable_no_common_raster_support"
    assert absent["residents"] is None and absent["dependent_share"] is None
    assert absent["dependent_share_unavailable_reason"] == "no_valid_age_cell"
    assert absent["allocation_range"]["low"] is None and absent["allocation_range"]["high"] is None
    assert absent["age_cells"]["with_valid_counts"] == 0 and absent["area"]["supported_km2"] == 0.0
    assert absent["area"]["unsupported_fraction"] == pytest.approx(1.0, abs=1e-4)

    empty = unit_age_exposure(UNIT, open_rasters(value=0.0))
    assert empty["residents"] == 0.0 and empty["dependent_share"] is None
    assert empty["dependent_share_unavailable_reason"] == "no_residents"
    assert empty["allocation_range"]["low"] is None
    assert empty["age_cells"]["with_valid_counts"] == 25  # a valid zero is support, not a gap


def test_allocation_rules_weight_the_cells_as_named(open_rasters) -> None:
    cells = read_unit_cells(UNIT, open_rasters())
    assert len(cells) == 25 and all(cell.supported for cell in cells)
    assert sorted({round(cell.fraction, 3) for cell in cells}) == [0.25, 0.5, 1.0]
    assert sum(1 for cell in cells if cell.wholly_inside) == 9
    central = allocate_cells(cells, PROJECTED_AREA_FRACTION)
    assert central["cells_used"] == 25
    assert central["residents"] == pytest.approx(math.fsum(cell.fraction * cell.residents for cell in cells))
    assert central["residents"] == pytest.approx(
        central["children_0_14"] + central["older_60_plus"] + central["other_15_59"])
    assert allocate_cells(cells, CELLS_WHOLLY_INSIDE)["cells_used"] == 9
    assert allocate_cells(cells, CELLS_ANY_TOUCHING)["residents"] == pytest.approx(2700.0)
    assert allocate_cells([], PROJECTED_AREA_FRACTION)["dependent_share"] is None
    assert set(ALLOCATION_RULES) == {PROJECTED_AREA_FRACTION, CELLS_WHOLLY_INSIDE, CELLS_ANY_TOUCHING}
    with pytest.raises(AgeExposureError, match="unknown allocation rule"):
        allocate_cells(cells, "nearest_centroid")


def test_support_summary_refuses_bad_areas() -> None:
    for unit_area, outside in ((0.0, 0.0), (float("nan"), 0.0), (True, 0.0), (5.0, -1.0), (5.0, float("inf"))):
        with pytest.raises(AgeExposureError):
            support_summary([], unit_area, outside)


def test_the_table_is_sorted_and_refuses_bad_input(tmp_path: Path) -> None:
    paths = _write_rasters(tmp_path / "rasters")
    west, east = WEST_UNIT, EAST_UNIT
    rows = age_exposure_table([("U2", east), ("U1", west)], paths)
    assert [row["unit_id"] for row in rows] == ["U1", "U2"]
    assert rows[0]["dependent_share"] == pytest.approx(0.55) and rows[1]["dependent_share"] == pytest.approx(0.625)
    # Each unit is 1.6 cells wide and 2.6 cells high.
    assert rows[0]["residents"] == pytest.approx(416.0, rel=1e-3) and rows[1]["residents"] == pytest.approx(499.2, rel=1e-3)
    spread = rows[0]["allocation_range"]
    assert spread["low"] == pytest.approx(0.55) and spread["high"] == pytest.approx(0.55)
    assert spread["low"] <= rows[0]["dependent_share"] <= spread["high"]
    with pytest.raises(AgeExposureError, match="unique"):
        age_exposure_table([("U1", west), ("U1", east)], paths)
    with pytest.raises(AgeExposureError, match="20 age bands"):
        age_exposure_table([("U1", west)], {band: path for band, path in paths.items() if band != "10"})
    with pytest.raises(ValueError, match="no WorldPop grid intersection"):
        age_exposure_table([("FAR", box(10.0, 10.0, 10.1, 10.1))], paths)


# --- The 2024-rescaled demand rule (protocol v1b, owner choice 12) ---------------------------------------------------


def test_rescale_multiplies_each_count_by_its_cell_ratio() -> None:
    counts = np.array([[10.0, 30.0, 0.0], [5.0, 5.0, 40.0]])
    cells = np.array([[1, 1, 1], [2, 2, 2]])
    result = rescale_2020_counts_to_2024(counts, cells, {1: 60.0, 2: 25.0})
    assert result["ratio_by_cell"] == {1: 1.5, 2: 0.5}
    np.testing.assert_allclose(result["rescaled_counts"], [[15.0, 45.0, 0.0], [2.5, 2.5, 20.0]])
    assert result["rescaled_counts"].shape == counts.shape
    # Each cell now sums to its 2024 total, and shares inside a cell are unchanged.
    assert result["rescaled_counts"][0].sum() == pytest.approx(60.0)
    assert result["rescaled_counts"][1].sum() == pytest.approx(25.0)
    assert result["residents_2020"] == 90.0 and result["residents_2024_rescaled"] == pytest.approx(85.0)
    assert result["unallocated_2024_residents"] == 0.0 and result["cells_with_zero_2020_sum"] == []
    assert result["complete"] is True and result["without_2024_total"]["counts"] == 0


def test_rescale_keeps_zero_cells_at_zero_and_reports_their_2024_residents() -> None:
    result = rescale_2020_counts_to_2024([4.0, 0.0, 0.0], [1, 2, 2], {1: 8.0, 2: 13.0, 3: 7.0, 4: None})
    assert result["rescaled_counts"].tolist() == [8.0, 0.0, 0.0]
    # Cell 2 holds counts that sum to zero; cells 3 and 4 hold no 2020 count at all. Cell 4 has no 2024 total.
    assert result["cells_with_zero_2020_sum"] == [2, 3, 4]
    assert result["unallocated_2024_residents"] == 20.0
    assert result["ratio_by_cell"] == {1: 2.0, 2: None, 3: None, 4: None}
    assert result["residents_2024_rescaled"] + result["unallocated_2024_residents"] == 8.0 + 13.0 + 7.0
    assert result["complete"] is True


def test_rescale_decides_nothing_for_a_cell_with_no_2024_total() -> None:
    result = rescale_2020_counts_to_2024([4.0, 6.0, 0.0, 3.0], [1, 1, 1, 2], {1: None, 2: 6.0})
    rescaled = result["rescaled_counts"]
    assert np.isnan(rescaled[0]) and np.isnan(rescaled[1]) and rescaled[2] == 0.0 and rescaled[3] == 6.0
    assert result["complete"] is False
    assert result["without_2024_total"]["cells"] == [1] and result["without_2024_total"]["counts"] == 2
    assert result["without_2024_total"]["residents_2020"] == 10.0
    assert "no rule" in result["without_2024_total"]["note"]
    assert result["residents_2024_rescaled"] == 6.0 and result["unallocated_2024_residents"] == 0.0


def test_rescale_refuses_bad_input() -> None:
    good = {1: 5.0}
    for counts, cells, totals in (
        ([1.0, -1.0], [1, 1], good),
        ([1.0, float("nan")], [1, 1], good),
        ([1.0, 2.0], [1], good),
        ([1.0], [1.5], good),
        ([1.0], [2], good),
        ([1.0], [1], {1: -5.0}),
        ([1.0], [1], {1: float("inf")}),
        ([1.0], [1], {"1": 5.0}),
    ):
        with pytest.raises(AgeExposureError):
            rescale_2020_counts_to_2024(counts, cells, totals)
    empty = rescale_2020_counts_to_2024([], [], {7: 3.0})
    assert empty["rescaled_counts"].size == 0 and empty["unallocated_2024_residents"] == 3.0


# --- What the signed protocol says ----------------------------------------------------------------------------------


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def test_the_module_follows_the_signed_protocol_text() -> None:
    v1a = json.loads((DOCS / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
    v1b = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    method = v1b["national_vulnerability_anchors"]["method"]
    assert tuple(method["age_groups"]["children_0_14"]) == CHILD_BANDS
    assert tuple(method["age_groups"]["older_adults_60_plus"]) == OLDER_BANDS
    others = tuple(band for band in AGE_BANDS if band not in CHILD_BANDS + OLDER_BANDS)
    assert tuple(method["age_groups"]["other_15_59"]) == others
    assert "projected-area fraction" in method["allocation"] and "DR-B04" in method["allocation_status"]
    assert "DR-B04" in ALLOCATION_STATEMENT and "summarize_geometry" in ALLOCATION_STATEMENT
    component = v1a["scoring_frame"]["components"]["vulnerability_context_0_100"]
    assert "residents aged 0-14 plus residents aged 60 and over, divided by all residents" in component["definition"]
    # Owner choice 12: the function's rule is the protocol's sentence.
    axis = next(axis for axis in v1b["ensemble_grid"]["core_axes"] if axis["axis"] == "population_vintage")
    assert "owner choice 12" in axis["rescale_formula_status"]
    assert _squash(axis["rescale_formula"]) in _squash(rescale_2020_counts_to_2024.__doc__ or "")


def test_the_module_scores_nothing() -> None:
    source = MODULE.read_text(encoding="utf-8")
    imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert not any("scoring" in line or "sensitivity" in line or "equity" in line for line in imports)
    assert "score_subdistricts" not in source and "action_class" not in source
    assert "official warning" in source  # the module says what it is not


# --- The builder, end to end on invented inputs ----------------------------------------------------------------------


def _script() -> Any:
    spec = importlib.util.spec_from_file_location("build_age_exposure", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("ascii"))


INVENTED_UNITS = {"ZZ000002": ("East", EAST_UNIT), "ZZ000001": ("West", WEST_UNIT)}


def _invented_workspace(tmp_path: Path, *, in_force: bool = True, units: list[str] | None = None,
                        allocation_module_sha256: str | None = None) -> dict[str, Path]:
    """Build invented inputs, protocol stubs and an anchor-receipt stub; nothing here is a real unit."""

    import geopandas as gpd

    age_dir = tmp_path / "age"
    paths = _write_rasters(age_dir)
    _write_json(age_dir / "acquisition_manifest.json", {
        "status": "PASS", "year_represented": 2024, "resolution_code": "1km", "publication_date": "2025-09-01",
        "product": "Global2 R2025A v1, invented test grid",
        "files": [{"band": band, "file": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)}
                  for band, path in paths.items()],
    })
    boundaries = tmp_path / "boundaries.gpkg"
    frame = gpd.GeoDataFrame(
        {"adm3_pcode": list(INVENTED_UNITS), "adm3_name": [name for name, _ in INVENTED_UNITS.values()],
         "valid_on": ["2022-01-22"] * len(INVENTED_UNITS)},
        geometry=[geometry for _, geometry in INVENTED_UNITS.values()], crs="EPSG:4326")
    frame.to_file(boundaries, layer="tha_admin3", driver="GPKG")

    root = tmp_path / "repo"
    pins = _script().ANCHOR_RUN_CODE
    input_hashes = {
        "age_acquisition_manifest_sha256": _sha256(age_dir / "acquisition_manifest.json"),
        "age_rasters_sha256": {path.name: _sha256(path) for path in sorted(paths.values())},
        "tambon_boundaries_sha256": _sha256(boundaries),
    }
    anchor = root / "outputs" / "planning_v1" / "national_vulnerability_anchors_v1.json"
    _write_json(anchor, {
        "input_hashes": input_hashes,
        # The stub records the code of the real anchor run, as the committed anchor receipt does.
        "implementation": {
            "allocation_module_sha256": allocation_module_sha256
            or pins["allocation_module"]["file_sha256_in_the_anchor_run"],
            "normalisation_module_sha256": pins["normalisation_module"]["file_sha256_in_the_anchor_run"],
            "builder_sha256": pins["anchors_builder"]["file_sha256_in_the_anchor_run"],
        },
    })
    docs = root / "docs" / "proposal_execution"
    _write_json(docs / "planning_protocol_v1a.json", {
        "status": "signed",
        "case_portfolio": {"mae_sai_reporting_frame": {"units": units or list(INVENTED_UNITS)}},
    })
    v1a_sha256 = _sha256(docs / "planning_protocol_v1a.json")
    _write_json(docs / "planning_protocol_v1b.json", {
        "status": "signed",
        "depends_on": {"v1a_sha256": v1a_sha256},
        "national_vulnerability_anchors": {
            "inputs": {
                "age_rasters": {"manifest_sha256": input_hashes["age_acquisition_manifest_sha256"]},
                "tambon_boundaries": {"sha256": input_hashes["tambon_boundaries_sha256"]},
            },
            "method": {"age_groups": {"children_0_14": list(CHILD_BANDS)}, "allocation": "invented stub"},
            "caveat": "invented stub",
            "output_receipt": {"path": anchor.relative_to(root).as_posix(), "sha256": _sha256(anchor)},
        },
    })
    lines = [
        {"source_commit": "0" * 40, "output_hashes": {"planning_protocol_v1a_sha256": v1a_sha256}},
        {"source_commit": "1" * 40,
         "output_hashes": {"planning_protocol_v1b_sha256": _sha256(docs / "planning_protocol_v1b.json")}},
    ]
    (docs / "RECEIPTS.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in (lines if in_force else lines[:1])), encoding="utf-8")
    return {"age_dir": age_dir, "boundaries": boundaries, "root": root, "docs": docs,
            "output": root / "outputs" / "planning_v1" / "age_exposure_mae_sai_v1.json"}


def _run(module: Any, space: dict[str, Path], **arguments: Any) -> dict[str, Any]:
    return module.run("mae_sai", space["age_dir"], space["boundaries"], space["output"],
                      docs=space["docs"], root=space["root"], **arguments)


def _result_keys(value: Any) -> list[str]:
    """List every key in a JSON value that could hold a score, a class or a component."""

    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if re.search(r"fpps|priority_score|action_class|would_be|_0_100$|vulnerability_context", key, re.IGNORECASE):
                found.append(key)
            found.extend(_result_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_result_keys(child))
    return found


def test_the_builder_writes_a_table_and_a_receipt_that_binds_it(tmp_path: Path) -> None:
    module = _script()
    space = _invented_workspace(tmp_path)
    summary = _run(module, space)
    table_path, receipt_path = space["output"], module.receipt_path_for(space["output"])
    assert receipt_path.name == "age_exposure_mae_sai_v1_receipt.json"
    for path in (table_path, receipt_path):
        raw = path.read_bytes()
        assert b"\r" not in raw and raw.endswith(b"\n") and raw.decode("ascii")
    table = json.loads(table_path.read_text(encoding="ascii"))
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))

    # The table: the units of the signed frame, sorted, with a share, cells, area and a range each.
    assert [row["unit_id"] for row in table["units"]] == sorted(INVENTED_UNITS) and table["unit_count"] == 2
    assert [row["unit_name"] for row in table["units"]] == ["West", "East"]
    assert table["units"][0]["dependent_share"] == pytest.approx(0.55)
    assert table["units"][1]["dependent_share"] == pytest.approx(0.625)
    for row in table["units"]:
        assert row["age_cells"]["with_valid_counts"] == 6 and row["area"]["supported_fraction"] == pytest.approx(1.0, abs=1e-4)
        assert row["allocation_range"]["low"] <= row["dependent_share"] <= row["allocation_range"]["high"]
        # The layer is the two invented units, which cover no cell in full: every cell is partly in no unit.
        border = row["cells_partly_outside_every_unit"]
        assert border["measured"] is True and border["cells"] == 6
        assert border["residents_the_unit_takes_from_them"] == pytest.approx(row["residents"])
        assert border["residents_of_those_cells_in_no_unit"] > 0
    assert table["border_cells"]["measured"] is True and table["border_cells"]["distinct_cells"] == 12
    assert "DR-B04" in table["border_cells_rule"] and "E7-OP1" in table["border_cells_rule_status"]
    reading = table["age_grid_reading"]
    window = reading["frame_window"]
    assert (window["row_off"], window["col_off"], window["height"], window["width"]) == (1, 1, 3, 5)
    assert reading["whole_grid"]["populated_cells"] == 30 and "not of any unit" in reading["what"]
    assert receipt["parameters"]["grid_reading_frame_window"] == {"row_off": 1, "col_off": 1, "height": 3, "width": 5}
    assert receipt["parameters"]["in_layer_min_fraction"] == IN_LAYER_MIN_FRACTION
    assert receipt["parameters"]["boundary_layer_units_for_border_cells"] == 2
    assert [point["id"] for point in table["open_points"]] == ["E7-OP1", "E7-OP2", "E7-OP3"]
    assert table["open_points"] == receipt["open_points"]
    assert "not a bound on the allocation error" in table["range_rule"]
    assert not any("extreme" in line or "how far" in line or "how much" in line
                   for line in [table["range_rule"], table["range_rule_status"], *table["limitations"]])
    for document in (table, receipt):
        assert document["official_warning"] is False and document["operational_status"] == "non_operational"
        assert document["confidence_class"] == "low" and document["confidence_basis"].strip()
        assert document["source_timestamp"] == "2025-09-01" and document["assumptions"]
        assert document["generated_at_utc"] == summary["generated_at_utc"]
        assert _result_keys(document) == []
    assert "not in the plan" in table["range_rule_status"].lower()

    # The receipt: protocol hashes, inputs and outputs by SHA-256, parameters and times.
    assert receipt["protocol_sha256"] == table["protocol_sha256"] == {
        "planning_protocol_v1a": _sha256(space["docs"] / "planning_protocol_v1a.json"),
        "planning_protocol_v1b": _sha256(space["docs"] / "planning_protocol_v1b.json"),
    }
    assert receipt["protocol_state"] == {"v1a": "in_force", "v1b": "in_force"}
    assert receipt["outputs"] == [{
        "path": "outputs/planning_v1/age_exposure_mae_sai_v1.json", "sha256": _sha256(table_path),
        "bytes": table_path.stat().st_size, "unit_count": 2,
    }]
    assert summary["table_sha256"] == _sha256(table_path) and summary["receipt_sha256"] == _sha256(receipt_path)
    assert len(receipt["inputs"]["age_rasters"]) == 20
    assert receipt["inputs"]["tambon_boundaries"]["sha256"] == _sha256(space["boundaries"])
    assert receipt["inputs"]["age_acquisition_manifest"]["sha256"] == table["input_hashes"]["age_acquisition_manifest_sha256"]
    assert receipt["parameters"]["unit_ids"] == sorted(INVENTED_UNITS)
    assert receipt["parameters"]["allocation_of_record"] == PROJECTED_AREA_FRACTION
    times = receipt["timestamps"]
    assert times["run_started_at_utc"] <= times["run_finished_at_utc"] == receipt["generated_at_utc"]
    consistency = receipt["consistency_with_national_anchors"]
    assert consistency["all_same"] is True and consistency["pinned_functions_and_constants_same"] is True
    assert set(consistency["code"]) == set(module.ANCHOR_RUN_CODE)
    for name, state in consistency["code"].items():
        assert state["function_source_sha256"] == module.ANCHOR_RUN_CODE[name]["functions"]
        assert state["whole_file_same"] == (state["file_sha256"] == state["file_sha256_in_the_anchor_run"])
    implementation = receipt["implementation"]
    assert implementation["age_exposure_module_sha256"] == _sha256(MODULE)
    assert implementation["builder_sha256"] == _sha256(SCRIPT)
    assert implementation["normalisation_module_sha256"] == consistency["code"]["normalisation_module"]["file_sha256"]
    assert implementation["allocation_module_sha256"] == consistency["code"]["allocation_module"]["file_sha256"]
    assert implementation["anchors_builder_sha256"] == consistency["code"]["anchors_builder"]["file_sha256"]
    # No local path leaks into either file.
    for path in (table_path, receipt_path):
        assert str(tmp_path).replace("\\", "/") not in path.read_text(encoding="ascii").replace("\\\\", "/")


def test_a_second_run_needs_a_reason_and_names_what_it_supersedes(tmp_path: Path) -> None:
    module = _script()
    space = _invented_workspace(tmp_path)
    _run(module, space)
    first_table = _sha256(space["output"])
    first_receipt = _sha256(module.receipt_path_for(space["output"]))
    with pytest.raises(FileExistsError, match="--replace --reason"):
        _run(module, space)
    assert _sha256(space["output"]) == first_table
    _run(module, space, replace_reason="a test of the replacement path")
    receipt = json.loads(module.receipt_path_for(space["output"]).read_text(encoding="ascii"))
    assert receipt["supersedes"]["table_sha256"] == first_table
    assert receipt["supersedes"]["receipt_sha256"] == first_receipt
    assert receipt["supersedes"]["reason"] == "a test of the replacement path"
    assert receipt["supersedes"]["all_same"] is True and all(receipt["supersedes"]["same_as_superseded"].values())
    assert set(receipt["supersedes"]["same_as_superseded"]) == {
        "figures_of_record", "allocation_figures", "input_hashes", "protocol_sha256", "allocation", "age_groups"}
    assert receipt["supersedes"]["unit_rows_identical"] is True
    assert receipt["supersedes"]["unit_row_keys_added"] == receipt["supersedes"]["unit_row_keys_removed"] == []
    assert receipt["outputs"][0]["sha256"] == _sha256(space["output"])


def test_a_replacement_compares_the_figures_whatever_other_fields_a_row_has(tmp_path: Path) -> None:
    """A row that gains or loses a field has the same figures; a row whose share moved has not."""

    module = _script()
    space = _invented_workspace(tmp_path)
    _run(module, space)
    table = json.loads(space["output"].read_text(encoding="ascii"))
    # An older table: no border cells, the range keyed as before, one more field.
    older = json.loads(json.dumps(table))
    for row in older["units"]:
        del row["cells_partly_outside_every_unit"]
        row["allocation_range"]["extremes_available"] = row["allocation_range"].pop("other_allocations_available")
        row["a_field_since_dropped"] = 1
    del older["border_cells"]
    _write_json(space["output"], older)
    same = module.supersedes(space["output"], table, "fields changed, figures did not")
    assert same["all_same"] is True and same["unit_rows_identical"] is False
    assert same["unit_row_keys_added"] == ["cells_partly_outside_every_unit"]
    assert same["unit_row_keys_removed"] == ["a_field_since_dropped"]
    assert same["allocation_range_keys_added"] == ["other_allocations_available"]
    assert same["allocation_range_keys_removed"] == ["extremes_available"]
    assert "border_cells" in same["table_keys_added"] and same["table_keys_removed"] == []
    # A share that moved is not the same figure, and neither is another allocation that moved.
    older["units"][0]["dependent_share"] += 1e-9
    _write_json(space["output"], older)
    moved = module.supersedes(space["output"], table, "a share moved")
    assert moved["same_as_superseded"]["figures_of_record"] is False and moved["all_same"] is False
    assert moved["same_as_superseded"]["allocation_figures"] is True
    older["units"][0]["dependent_share"] = table["units"][0]["dependent_share"]
    older["units"][1]["allocation_range"]["cells_any_touching"]["residents"] += 1.0
    _write_json(space["output"], older)
    moved = module.supersedes(space["output"], table, "an allocation moved")
    assert moved["same_as_superseded"] == {
        "figures_of_record": True, "allocation_figures": False, "input_hashes": True, "protocol_sha256": True,
        "allocation": True, "age_groups": True}


def test_the_builder_refuses_to_run_outside_the_protocol(tmp_path: Path) -> None:
    module = _script()
    not_in_force = _invented_workspace(tmp_path / "a", in_force=False)
    with pytest.raises(ValueError, match="not in force"):
        _run(module, not_in_force)
    # An anchor receipt that records other code than the code the pins were taken from.
    other_code = _invented_workspace(tmp_path / "b", allocation_module_sha256="0" * 64)
    with pytest.raises(ValueError, match="was not taken from the national-anchor run"):
        _run(module, other_code)
    unknown_unit = _invented_workspace(tmp_path / "c", units=["ZZ000001", "ZZ000009"])
    with pytest.raises(ValueError, match="missing from the boundary layer"):
        _run(module, unknown_unit)
    changed_input = _invented_workspace(tmp_path / "d")
    with (changed_input["age_dir"] / "acquisition_manifest.json").open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(ValueError, match="not the one protocol v1b names"):
        _run(module, changed_input)
    for space in (not_in_force, other_code, unknown_unit, changed_input):
        assert not space["output"].exists() and not module.receipt_path_for(space["output"]).exists()
    with pytest.raises(FileNotFoundError):
        _run(module, changed_input, replace_reason="nothing to replace")


def test_the_command_line_needs_a_boundary_location_and_pairs_replace_with_reason(tmp_path: Path, monkeypatch) -> None:
    module = _script()
    monkeypatch.delenv(module.EXTERNAL_DATA_VARIABLE, raising=False)
    with pytest.raises(SystemExit):
        module.main(["--case", "mae_sai", "--age-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        module.main(["--case", "mae_sai", "--age-dir", str(tmp_path), "--boundaries", str(tmp_path), "--replace"])
    with pytest.raises(SystemExit):
        module.main(["--case", "nowhere", "--age-dir", str(tmp_path), "--boundaries", str(tmp_path)])
    assert module.CASE_FRAMES["mae_sai"]["pointer"] == "/case_portfolio/mae_sai_reporting_frame/units"
    assert module.OUTPUT_DIR == ROOT / "outputs" / "planning_v1"


def test_the_command_line_writes_one_table_per_case_frame_in_one_place(tmp_path: Path, monkeypatch, capsys) -> None:
    """There is no --output: a second run cannot go round --replace by naming another path."""

    module = _script()
    elsewhere = tmp_path / "elsewhere" / "age_exposure_mae_sai_v1.json"
    with pytest.raises(SystemExit):
        module.main(["--case", "mae_sai", "--age-dir", str(tmp_path), "--boundaries", str(tmp_path),
                     "--output", str(elsewhere)])
    assert "unrecognized arguments: --output" in capsys.readouterr().err
    assert module.default_output("mae_sai") == module.OUTPUT_DIR / "age_exposure_mae_sai_v1.json"

    calls: list[dict[str, Any]] = []

    def record(case: str, age_dir: Path, boundaries: Path, output: Path, **arguments: Any) -> dict[str, Any]:
        calls.append({"case": case, "output": output, **arguments})
        raise FileExistsError("the table or its receipt exists; a second run needs --replace --reason")

    monkeypatch.setattr(module, "run", record)
    arguments = ["--case", "mae_sai", "--age-dir", str(tmp_path), "--boundaries", str(tmp_path / "b.gdb.zip")]
    assert module.main(arguments) == 2
    assert "REFUSED" in capsys.readouterr().err
    assert module.main([*arguments, "--replace", "--reason", " a reason "]) == 2
    assert [call["output"] for call in calls] == [module.default_output("mae_sai")] * 2
    assert [call["replace_reason"] for call in calls] == [None, "a reason"]


# --- The code check: the functions the share depends on, as in the national-anchor run -----------------------------


def _real_v1b_and_anchor() -> tuple[dict[str, Any], dict[str, Any]]:
    v1b = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    return v1b, json.loads(ANCHOR_RECEIPT.read_text(encoding="ascii"))


def test_the_checked_out_code_computes_the_share_as_the_anchor_run_did() -> None:
    """The builder's own check, on the signed v1b, the committed anchor receipt and the code on this checkout.

    A merge that changes a function the share depends on fails here, in the suite, and not at run time.
    """

    module = _script()
    v1b, anchor = _real_v1b_and_anchor()
    result = module.anchor_consistency(v1b, ROOT, anchor["input_hashes"])
    assert result["all_same"] is True and result["pinned_functions_and_constants_same"] is True
    assert result["anchor_receipt_sha256"] == _sha256(ANCHOR_RECEIPT)
    assert set(result["code"]) == set(module.ANCHOR_RUN_CODE) == {
        "allocation_module", "normalisation_module", "anchors_builder"}
    files = module.loaded_code_files()
    for name, state in result["code"].items():
        pins = module.ANCHOR_RUN_CODE[name]
        # The modules the builder loaded are the files of this checkout.
        assert files[name] == (ROOT / pins["path"]).resolve()
        assert state["file_sha256"] == _sha256(files[name])
        assert state["file_sha256_in_the_anchor_run"] == anchor["implementation"][pins["anchor_receipt_key"]]
        assert state["function_source_sha256"] == pins["functions"] and all(state["functions_same"].values())
        assert state["constants_found"] == pins["constants"] and all(state["constants_same"].values())
        assert state["whole_file_same"] == (state["file_sha256"] == state["file_sha256_in_the_anchor_run"])
    assert result["whole_files_same"] == all(state["whole_file_same"] for state in result["code"].values())
    # The functions the builder and the module call are the pinned ones, and the constants are the ones in use.
    assert set(module.ANCHOR_RUN_CODE["allocation_module"]["functions"]) == {"_coverage", "summarize_geometry"}
    assert set(module.ANCHOR_RUN_CODE["normalisation_module"]["functions"]) == {"dependent_share"}
    assert set(module.ANCHOR_RUN_CODE["anchors_builder"]["functions"]) == {"check_age_sources", "read_units", "sha256_file"}
    assert module.ANCHOR_RUN_CODE["allocation_module"]["constants"] == {
        "AGE_BANDS": list(AGE_BANDS), "CHILD_BANDS": list(CHILD_BANDS), "OLDER_BANDS": list(OLDER_BANDS)}
    assert module.ANCHOR_RUN_CODE["anchors_builder"]["constants"] == {
        "BOUNDARY_LAYER": module.anchors_builder.BOUNDARY_LAYER, "UNIT_ID_FIELD": module.anchors_builder.UNIT_ID_FIELD}


def _bytes_with_sha256(relative: str, sha256: str) -> bytes | None:
    """Return the bytes a file had when it had this SHA-256: from the checkout, or else from the Git history."""

    path = ROOT / relative
    if _sha256(path) == sha256:
        return path.read_bytes()
    try:
        commits = subprocess.run(["git", "log", "--format=%H", "--", relative], cwd=ROOT, capture_output=True,
                                 text=True, check=True, timeout=120).stdout.split()
        for commit in commits:
            blob = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=ROOT, capture_output=True,
                                  check=False, timeout=120)
            if blob.returncode == 0 and hashlib.sha256(blob.stdout).hexdigest() == sha256:
                return blob.stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return None


@pytest.mark.parametrize("name", ["allocation_module", "normalisation_module", "anchors_builder"])
def test_the_pins_were_taken_from_the_bytes_the_anchor_receipt_records(name: str) -> None:
    """The pinned hashes are those of the functions in the file whose SHA-256 the anchor receipt records."""

    module = _script()
    _v1b, anchor = _real_v1b_and_anchor()
    pins = module.ANCHOR_RUN_CODE[name]
    assert pins["file_sha256_in_the_anchor_run"] == anchor["implementation"][pins["anchor_receipt_key"]]
    data = _bytes_with_sha256(pins["path"], pins["file_sha256_in_the_anchor_run"])
    if data is None:
        pytest.skip("the bytes of the anchor run are neither on this checkout nor in its Git history")
    state = module.pinned_code_state(data.decode("utf-8"), pins)
    assert state["function_source_sha256"] == pins["functions"]
    assert state["constants_found"] == pins["constants"]


def test_a_change_outside_the_pinned_code_is_recorded_and_does_not_refuse(tmp_path: Path) -> None:
    """Protocol v1b builds the rest of frame v1 in normalisation.py: the file grows, the share's function does not."""

    module = _script()
    v1b, anchor = _real_v1b_and_anchor()
    files = module.loaded_code_files()
    grown = tmp_path / "normalisation.py"
    source = files["normalisation_module"].read_text(encoding="utf-8")
    grown.write_text(source.replace("def dependent_share(", "def added_before() -> int:\n    return 1\n\n\ndef dependent_share(")
                     + "\n\ndef added_after() -> int:\n    return 2\n", encoding="utf-8", newline="\r\n")
    result = module.anchor_consistency(v1b, ROOT, anchor["input_hashes"],
                                       code_files={**files, "normalisation_module": grown})
    state = result["code"]["normalisation_module"]
    assert result["all_same"] is True and result["whole_files_same"] is False
    assert state["whole_file_same"] is False and state["file_sha256"] == _sha256(grown)
    assert state["functions_same"] == {"dependent_share": True}
    assert "has changed outside the pinned functions" in result["note"]


def test_a_change_to_the_pinned_code_or_to_the_inputs_refuses_the_run(tmp_path: Path) -> None:
    module = _script()
    v1b, anchor = _real_v1b_and_anchor()
    files = module.loaded_code_files()

    def changed(name: str, old: str, new: str) -> dict[str, Path]:
        source = files[name].read_text(encoding="utf-8")
        assert source.count(old) == 1
        copy = tmp_path / f"{name}_{len(list(tmp_path.iterdir()))}.py"
        copy.write_text(source.replace(old, new), encoding="utf-8", newline="\n")
        return {**files, name: copy}

    cases = (
        ("normalisation_module", "    return min(1.0, dependants / residents)", "    return dependants / residents",
         "normalisation_module.dependent_share"),
        ("allocation_module", "all_touched=True", "all_touched=False", "allocation_module._coverage"),
        ("allocation_module", 'CHILD_BANDS = ("00", "01", "05", "10")', 'CHILD_BANDS = ("00", "01", "05")',
         "allocation_module.CHILD_BANDS"),
        ("allocation_module", "def summarize_geometry(", "def summarize_geometry_renamed(",
         "allocation_module.summarize_geometry"),
        ("anchors_builder", 'UNIT_ID_FIELD = "adm3_pcode"', 'UNIT_ID_FIELD = "adm2_pcode"', "anchors_builder.UNIT_ID_FIELD"),
        ("anchors_builder", "            geometry = make_valid(geometry)", "            pass", "anchors_builder.read_units"),
    )
    for name, old, new, named in cases:
        with pytest.raises(ValueError, match=f"differs from the national-anchor run .*{re.escape(named)}"):
            module.anchor_consistency(v1b, ROOT, anchor["input_hashes"], code_files=changed(name, old, new))
    for key in ("age_acquisition_manifest_sha256", "tambon_boundaries_sha256"):
        with pytest.raises(ValueError, match="the inputs differ from the national-anchor run"):
            module.anchor_consistency(v1b, ROOT, {**anchor["input_hashes"], key: "0" * 64})
    # An anchor receipt other than the one protocol v1b names is refused before anything is compared.
    other = json.loads(json.dumps(v1b))
    other["national_vulnerability_anchors"]["output_receipt"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="not the one protocol v1b names"):
        module.anchor_consistency(other, ROOT, anchor["input_hashes"])


def test_a_function_is_hashed_by_its_own_lines_whatever_the_line_endings() -> None:
    module = _script()
    source = (
        "import math\n\nLIMIT = (1, 2)\nNAME: str = 'x'\n\n\n@decorated\ndef first(value):\n"
        "    # a comment\n    return value + 1\n\n\ndef second():\n    return 2\n"
    )
    first = module.function_source_sha256(source, "first")
    lines = "@decorated\ndef first(value):\n    # a comment\n    return value + 1\n"
    assert first == hashlib.sha256(lines.encode("utf-8")).hexdigest()
    assert module.function_source_sha256(source.replace("\n", "\r\n"), "first") == first
    # A change elsewhere in the file leaves the hash alone; a change inside the function moves it.
    assert module.function_source_sha256(source.replace("return 2", "return 3") + "\nX = 1\n", "first") == first
    assert module.function_source_sha256(source.replace("# a comment", "# another comment"), "first") != first
    assert module.function_source_sha256(source.replace("value + 1", "value + 2"), "first") != first
    with pytest.raises(ValueError, match="no top-level function"):
        module.function_source_sha256(source, "third")
    assert module.module_constant(source, "LIMIT") == [1, 2] and module.module_constant(source, "NAME") == "x"
    for name, text in (("MISSING", source), ("LIMIT", source + "LIMIT = (3,)\n"), ("LIMIT", "LIMIT = len('x')\n")):
        with pytest.raises(ValueError):
            module.module_constant(text, name)
    state = module.pinned_code_state(source, {"functions": {"first": first, "third": "0" * 64},
                                              "constants": {"LIMIT": [1, 2], "MISSING": 1}})
    assert state["functions_same"] == {"first": True, "third": False}
    assert state["constants_same"] == {"LIMIT": True, "MISSING": False}
    assert state["function_source_sha256"]["third"] is None and state["constants_found"]["MISSING"] is None


# --- The committed Mae Sai table: read, never recomputed -------------------------------------------------------------


def _committed() -> tuple[dict[str, Any], dict[str, Any]]:
    if not TABLE.exists() or not RECEIPT.exists():
        pytest.skip("the Mae Sai age exposure has not been computed on this checkout")
    return json.loads(TABLE.read_text(encoding="ascii")), json.loads(RECEIPT.read_text(encoding="ascii"))


def test_the_committed_receipt_binds_the_table_the_inputs_and_the_protocol() -> None:
    table, receipt = _committed()
    assert receipt["outputs"] == [{
        "path": TABLE.relative_to(ROOT).as_posix(), "sha256": _sha256(TABLE), "bytes": TABLE.stat().st_size,
        "unit_count": table["unit_count"],
    }]
    hashes = {
        "planning_protocol_v1a": _sha256(DOCS / "planning_protocol_v1a.json"),
        "planning_protocol_v1b": _sha256(DOCS / "planning_protocol_v1b.json"),
    }
    assert table["protocol_sha256"] == receipt["protocol_sha256"] == hashes
    recorded = [json.loads(line) for line in (DOCS / "RECEIPTS.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    in_force = {key: line["time_utc"] for line in recorded for key in line.get("output_hashes", {})
                if key.startswith("planning_protocol_")}
    for name, digest in hashes.items():
        assert any(line.get("output_hashes", {}).get(f"{name}_sha256") == digest for line in recorded), name
    # The run was made after protocol v1b came into force.
    assert receipt["timestamps"]["run_started_at_utc"] > in_force["planning_protocol_v1b_sha256"]
    assert receipt["generated_at_utc"] == table["generated_at_utc"] == receipt["timestamps"]["run_finished_at_utc"]

    # Same input bytes as the national-anchor run, and the functions the share depends on as in that run.
    anchor = json.loads(ANCHOR_RECEIPT.read_text(encoding="ascii"))
    assert table["input_hashes"] == anchor["input_hashes"]
    assert receipt["inputs"]["national_anchor_receipt"]["sha256"] == _sha256(ANCHOR_RECEIPT)
    consistency = receipt["consistency_with_national_anchors"]
    assert consistency["all_same"] is True and consistency["pinned_functions_and_constants_same"] is True
    assert all(consistency["same_input_bytes_as_the_anchor_run"].values())
    pins = _script().ANCHOR_RUN_CODE
    implementation = receipt["implementation"]
    recorded_as = {"allocation_module": "allocation_module_sha256", "normalisation_module": "normalisation_module_sha256",
                   "anchors_builder": "anchors_builder_sha256"}
    assert set(consistency["code"]) == set(pins)
    for name, state in consistency["code"].items():
        assert state["function_source_sha256"] == pins[name]["functions"] and all(state["functions_same"].values())
        assert state["constants_found"] == pins[name]["constants"] and all(state["constants_same"].values())
        assert state["file_sha256_in_the_anchor_run"] == anchor["implementation"][pins[name]["anchor_receipt_key"]]
        # A whole file may differ from the anchor run; the receipt says so and names the file it loaded.
        assert state["whole_file_same"] == (state["file_sha256"] == state["file_sha256_in_the_anchor_run"])
        assert implementation[recorded_as[name]] == state["file_sha256"]
    assert consistency["whole_files_same"] == all(state["whole_file_same"] for state in consistency["code"].values())
    v1b = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    declared = v1b["national_vulnerability_anchors"]["inputs"]
    assert receipt["inputs"]["age_acquisition_manifest"]["sha256"] == declared["age_rasters"]["manifest_sha256"]
    assert receipt["inputs"]["tambon_boundaries"]["sha256"] == declared["tambon_boundaries"]["sha256"]
    assert sum(entry["bytes"] for entry in receipt["inputs"]["age_rasters"].values()) == declared["age_rasters"]["total_bytes"]
    assert table["caveat"] == v1b["national_vulnerability_anchors"]["caveat"]
    assert table["allocation_in_protocol_v1b"] == v1b["national_vulnerability_anchors"]["method"]["allocation"]


def test_the_committed_table_holds_the_eight_units_and_nothing_scored() -> None:
    table, receipt = _committed()
    v1a = json.loads((DOCS / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
    units = table["units"]
    assert [row["unit_id"] for row in units] == sorted(v1a["case_portfolio"]["mae_sai_reporting_frame"]["units"])
    assert receipt["parameters"]["unit_ids"] == [row["unit_id"] for row in units] and table["unit_count"] == 8
    assert _result_keys(table) == [] and _result_keys(receipt) == []
    assert table["status"] == "unit_inputs" and "E8" in table["status_note"]
    assert [point["id"] for point in table["open_points"]] == ["E7-OP1", "E7-OP2", "E7-OP3"]
    assert table["open_points"] == receipt["open_points"] and table["limitations"] == receipt["limitations"]
    for point in table["open_points"]:
        assert all(point[key].strip() for key in ("point", "protocol_says", "what_this_file_does", "for_the_owners"))
    # The range is worded as three allocations, not as a bound.
    assert table["range_rule"] == RANGE_STATEMENT and "E7-OP2" in table["range_rule_status"]
    assert not any("extreme" in line or "how far" in line or "how much" in line
                   for line in [table["range_rule"], table["range_rule_status"], *table["limitations"]])
    assert any("not a bound on the allocation error" in line for line in table["limitations"])
    assert any("narrow range does not show a precise share" in line for line in table["limitations"])
    assert any("straddle the national border" in line and "DR-B04" in line for line in table["limitations"])
    for row in units:
        assert row["status"] == "modelled_research_estimate" and row["band_mask_mismatch"] is False
        assert row["residents"] == pytest.approx(row["children_0_14"] + row["older_60_plus"] + row["other_15_59"])
        assert row["dependent_share"] == dependent_share(row["children_0_14"], row["older_60_plus"], row["residents"])
        spread = row["allocation_range"]
        assert spread[PROJECTED_AREA_FRACTION] == row["dependent_share"]
        assert 0 < spread["low"] <= row["dependent_share"] <= spread["high"] < 1
        shares = [spread[rule]["dependent_share"] for rule in (CELLS_WHOLLY_INSIDE, CELLS_ANY_TOUCHING)]
        assert spread["low"] == min(*shares, row["dependent_share"]) and spread["high"] == max(*shares, row["dependent_share"])
        cells, area = row["age_cells"], row["area"]
        assert cells["with_valid_counts"] == cells["wholly_inside"] + cells["partly_inside"] > 0
        assert spread[CELLS_ANY_TOUCHING]["cells"] == cells["with_valid_counts"]
        assert spread[CELLS_WHOLLY_INSIDE]["cells"] == cells["wholly_inside"]
        assert 0 < area["supported_fraction"] <= 1 and 0 <= area["unsupported_fraction"] < 1
        assert area["unsupported_km2"] == pytest.approx(
            area["unsupported_in_cells_without_valid_counts_km2"] + area["unsupported_outside_the_age_grid_km2"])
        assert abs(area["reconciliation_residual_km2"]) < 0.01 * area["unit_km2"]


def test_the_committed_table_shows_what_each_share_owes_to_cells_on_the_edge_of_the_layer() -> None:
    """Reading DR-B04 is silent on a cell that no set of units covers: the table shows such cells, unit by unit."""

    table, receipt = _committed()
    assert "DR-B04" in table["border_cells_rule"] and "nothing is adjusted" in table["border_cells_rule"]
    assert "not a rule of the protocol" in table["border_cells_rule_status"]
    assert receipt["parameters"]["in_layer_min_fraction"] == IN_LAYER_MIN_FRACTION
    assert receipt["parameters"]["boundary_layer_units_for_border_cells"] == receipt["inputs"]["tambon_boundaries"]["units_in_layer"]
    with_border_cells = 0
    for row in table["units"]:
        border = row["cells_partly_outside_every_unit"]
        assert border["measured"] is True
        assert 0 <= border["cells"] <= row["age_cells"]["partly_inside"]
        # The two parts are the counts of record, split; nothing is added or taken away.
        assert border["residents_the_unit_takes_from_them"] + border["residents_from_the_other_cells"] == pytest.approx(
            row["residents"], rel=1e-9)
        assert border["share_of_the_units_residents"] == pytest.approx(
            border["residents_the_unit_takes_from_them"] / row["residents"])
        dependants = border["residents_from_the_other_cells"] * border["dependent_share_from_the_other_cells"]
        if border["cells"]:
            with_border_cells += 1
            dependants += (border["residents_the_unit_takes_from_them"]
                           * border["dependent_share_of_what_the_unit_takes_from_them"])
            assert border["residents_of_those_cells_in_no_unit"] > 0 and border["area_of_those_cells_in_no_unit_km2"] > 0
        else:
            assert border["residents_the_unit_takes_from_them"] == border["residents_of_those_cells_in_no_unit"] == 0.0
            assert border["dependent_share_of_what_the_unit_takes_from_them"] is None
        assert dependants / row["residents"] == pytest.approx(row["dependent_share"], rel=1e-9)
    frame = table["border_cells"]
    per_unit = [row["cells_partly_outside_every_unit"] for row in table["units"]]
    assert frame["measured"] is True and with_border_cells > 0
    assert max(border["cells"] for border in per_unit) <= frame["distinct_cells"] <= sum(border["cells"] for border in per_unit)
    assert frame["residents_the_frames_units_take_from_them"] == pytest.approx(
        sum(border["residents_the_unit_takes_from_them"] for border in per_unit))
    assert frame["residents_of_those_cells_in_no_unit"] <= sum(border["residents_of_those_cells_in_no_unit"] for border in per_unit)
    assert (frame["residents_the_frames_units_take_from_them"] + frame["residents_of_those_cells_in_no_unit"]
            <= frame["residents_in_those_cells"] * (1 + 1e-9))


def test_the_committed_grid_reading_names_its_window_and_adds_up() -> None:
    """The reading of the input grid is in the table the receipt binds, with its window in rows and columns."""

    table, receipt = _committed()
    reading = table["age_grid_reading"]
    assert "not of any unit" in reading["what"]
    window, whole = reading["frame_window"], reading["whole_grid"]
    assert receipt["parameters"]["grid_reading_frame_window"] == {
        key: window[key] for key in ("row_off", "col_off", "height", "width")}
    west, south, east, north = window["bounds_west_south_east_north"]
    assert west < east and south < north
    assert window["cells"] == window["height"] * window["width"] and whole["cells"] == whole["height"] * whole["width"]
    for part in (window, whole):
        assert part["cells"] == part["cells_with_valid_counts"] + part["cells_without_valid_counts"]
        assert part["cells_with_valid_counts"] == part["populated_cells"] + part["valid_cells_with_zero_residents"]
        groups = part["same_share_groups"]
        assert groups["decimals"] == receipt["parameters"]["grid_reading_share_group_decimals"] == 6
        assert groups["min_cells"] == receipt["parameters"]["grid_reading_share_group_min_cells"] == 20
        assert groups["groups"] * groups["min_cells"] <= groups["cells"] <= part["populated_cells"]
        assert groups["share_of_populated_cells"] == pytest.approx(groups["cells"] / part["populated_cells"])
        assert groups["residents"] <= part["residents"] * (1 + 1e-9)
        assert 0 < part["dependent_share_of_all_residents"] < 1
    clusters = window["share_clusters"]
    assert clusters["gap"] == receipt["parameters"]["grid_reading_share_cluster_gap"]
    listed, smaller = clusters["clusters"], clusters["smaller_clusters"]
    assert all(cluster["cells"] >= clusters["min_cells"] for cluster in listed)
    assert [cluster["cells"] for cluster in listed] == sorted((cluster["cells"] for cluster in listed), reverse=True)
    assert sum(cluster["cells"] for cluster in listed) + smaller["cells"] == window["populated_cells"]
    assert sum(cluster["residents"] for cluster in listed) + smaller["residents"] == pytest.approx(window["residents"])
    # The frame's window lies inside the grid, and every cell the units rest on lies inside the window.
    assert window["row_off"] + window["height"] <= whole["height"] and window["col_off"] + window["width"] <= whole["width"]
    assert max(row["age_cells"]["with_valid_counts"] for row in table["units"]) <= window["cells_with_valid_counts"]


def test_the_committed_receipt_names_the_run_it_supersedes_and_the_figures_did_not_move() -> None:
    table, receipt = _committed()
    replaced = receipt.get("supersedes")
    if replaced is None:
        pytest.skip("the committed table is a first run")
    assert replaced["reason"].strip() and re.fullmatch(r"[0-9a-f]{64}", replaced["table_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", replaced["receipt_sha256"])
    assert replaced["generated_at_utc"] < receipt["timestamps"]["run_started_at_utc"]
    assert replaced["all_same"] is True and all(replaced["same_as_superseded"].values())
    assert {"figures_of_record", "allocation_figures", "input_hashes", "protocol_sha256"} <= set(replaced["same_as_superseded"])
    # Where Git still holds the superseded table, its figures of record are the ones in the table now.
    relative = TABLE.relative_to(ROOT).as_posix()
    data = _bytes_with_sha256(relative, replaced["table_sha256"])
    if data is None:
        pytest.skip("the superseded table is not in the Git history of this checkout")
    previous = json.loads(data.decode("ascii"))
    assert previous["generated_at_utc"] == replaced["generated_at_utc"]
    keys = _script().RECORD_FIGURE_KEYS
    assert [[row[key] for key in keys] for row in previous["units"]] == [[row[key] for key in keys] for row in table["units"]]
    for before, after in zip(previous["units"], table["units"], strict=True):
        for key in ("low", "high", PROJECTED_AREA_FRACTION, CELLS_WHOLLY_INSIDE, CELLS_ANY_TOUCHING):
            assert before["allocation_range"][key] == after["allocation_range"][key], key
    superseded_receipt = _bytes_with_sha256(RECEIPT.relative_to(ROOT).as_posix(), replaced["receipt_sha256"])
    if superseded_receipt is not None:
        assert json.loads(superseded_receipt.decode("ascii"))["outputs"][0]["sha256"] == replaced["table_sha256"]


# --- Real input, bytes only ------------------------------------------------------------------------------------------

EXTERNAL = os.environ.get("FLOODGUARD_EXTERNAL_DATA")


@pytest.mark.skipif(not EXTERNAL, reason="FLOODGUARD_EXTERNAL_DATA is not set")
def test_the_boundary_file_on_disk_is_the_one_the_receipt_names() -> None:
    """Hashes the boundary file. It opens no polygon and computes nothing for any unit."""

    _table, receipt = _committed()
    boundaries = Path(str(EXTERNAL)) / _script().BOUNDARY_RELATIVE_PATH
    recorded = receipt["inputs"]["tambon_boundaries"]
    assert boundaries.name == recorded["file"] and boundaries.stat().st_size == recorded["bytes"]
    assert _sha256(boundaries) == recorded["sha256"]
