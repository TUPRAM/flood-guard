"""Age exposure: dependent share per unit, on invented rasters and polygons.

No test here reads a real raster or boundary, and none computes a
vulnerability component, an FPPS, a class or an ensemble. The tests of the
committed Mae Sai table read that table and its receipt only: they recompute
nothing.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any, Iterator

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from floodguard.age_exposure import (
    ALLOCATION_RULES,
    ALLOCATION_STATEMENT,
    CELLS_ANY_TOUCHING,
    CELLS_WHOLLY_INSIDE,
    PROJECTED_AREA_FRACTION,
    AgeCell,
    AgeExposureError,
    age_exposure_table,
    allocate_cells,
    allocation_range,
    read_unit_cells,
    rescale_2020_counts_to_2024,
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
    assert spread["extremes_available"] == 2 and spread["value_of_record_between_the_two_extremes"] is True


def test_the_range_always_holds_the_value_of_record() -> None:
    """Uneven edge cells can put the area-weighted share outside both extremes; the range widens to hold it."""

    def cell(col: int, fraction: float, dependants: float) -> AgeCell:
        return AgeCell(0, col, fraction, fraction * 1e6, 100.0, dependants, 0.0)

    cells = [cell(0, 1.0, 50.0), cell(1, 0.9, 90.0), cell(2, 0.1, 10.0)]
    spread = allocation_range(cells)
    assert spread[CELLS_WHOLLY_INSIDE]["dependent_share"] == pytest.approx(0.5)
    assert spread[CELLS_ANY_TOUCHING]["dependent_share"] == pytest.approx(0.5)
    assert spread[PROJECTED_AREA_FRACTION] == pytest.approx(132 / 200)
    assert spread["low"] == pytest.approx(0.5) and spread["high"] == pytest.approx(0.66)
    assert spread["value_of_record_between_the_two_extremes"] is False


def test_a_unit_with_no_cell_wholly_inside_has_one_extreme_only(open_rasters) -> None:
    small = box(99.8125, 20.4125, 99.8175, 20.4175)  # inside one west cell (row 2, column 2)
    record = unit_age_exposure(small, open_rasters())
    spread = record["allocation_range"]
    assert record["age_cells"]["with_valid_counts"] == 1 and record["age_cells"]["wholly_inside"] == 0
    assert spread[CELLS_WHOLLY_INSIDE] == {"cells": 0, "residents": 0.0, "dependent_share": None}
    assert spread["extremes_available"] == 1 and spread["value_of_record_between_the_two_extremes"] is None
    assert spread["low"] == pytest.approx(0.55) and spread["high"] == pytest.approx(0.55)
    assert record["dependent_share"] == pytest.approx(0.55)


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


CODE_FILES = (
    "src/floodguard/age_exposure.py", "src/floodguard/evidence_age_surface.py", "src/floodguard/normalisation.py",
    "scripts/build_national_vulnerability_anchors.py",
)
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
    for relative in CODE_FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, root / relative)
    input_hashes = {
        "age_acquisition_manifest_sha256": _sha256(age_dir / "acquisition_manifest.json"),
        "age_rasters_sha256": {path.name: _sha256(path) for path in sorted(paths.values())},
        "tambon_boundaries_sha256": _sha256(boundaries),
    }
    anchor = root / "outputs" / "planning_v1" / "national_vulnerability_anchors_v1.json"
    _write_json(anchor, {
        "input_hashes": input_hashes,
        "implementation": {
            "allocation_module_sha256": allocation_module_sha256 or _sha256(ROOT / "src/floodguard/evidence_age_surface.py"),
            "normalisation_module_sha256": _sha256(ROOT / "src/floodguard/normalisation.py"),
            "builder_sha256": _sha256(ROOT / "scripts/build_national_vulnerability_anchors.py"),
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
    assert receipt["consistency_with_national_anchors"]["all_same"] is True
    assert receipt["implementation"]["age_exposure_module_sha256"] == _sha256(MODULE)
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
    assert receipt["outputs"][0]["sha256"] == _sha256(space["output"])


def test_the_builder_refuses_to_run_outside_the_protocol(tmp_path: Path) -> None:
    module = _script()
    not_in_force = _invented_workspace(tmp_path / "a", in_force=False)
    with pytest.raises(ValueError, match="not in force"):
        _run(module, not_in_force)
    other_code = _invented_workspace(tmp_path / "b", allocation_module_sha256="0" * 64)
    with pytest.raises(ValueError, match="national-anchor run"):
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

    # Same input bytes and same code as the national-anchor run.
    anchor = json.loads(ANCHOR_RECEIPT.read_text(encoding="ascii"))
    assert table["input_hashes"] == anchor["input_hashes"]
    assert receipt["inputs"]["national_anchor_receipt"]["sha256"] == _sha256(ANCHOR_RECEIPT)
    consistency = receipt["consistency_with_national_anchors"]
    assert consistency["all_same"] is True and all(consistency["same_code_bytes_as_the_anchor_run"].values())
    implementation = receipt["implementation"]
    assert implementation["allocation_module_sha256"] == anchor["implementation"]["allocation_module_sha256"]
    assert implementation["normalisation_module_sha256"] == anchor["implementation"]["normalisation_module_sha256"]
    assert implementation["anchors_builder_sha256"] == anchor["implementation"]["builder_sha256"]
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
