"""Tests of the tuning references of the Nan case: the three aggregation rules on invented rasters, the label points,
the firewall, the drop rule, and the committed record."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard.wording_lint import find_violations, json_strings, load_rules, python_strings  # noqa: E402

SCRIPT = ROOT / "scripts" / "nan_case_tuning_references.py"
RECORD = ROOT / "outputs" / "nan_case" / "tuning_references_v1.json"
WORDING_RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")


def load_script() -> Any:
    """Load the script as a module, without running it."""

    spec = importlib.util.spec_from_file_location("nan_case_tuning_references", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ref = load_script()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------------------------------
# Placement and counting
# ---------------------------------------------------------------------------------------------------------------------

def test_a_fine_raster_that_nests_gets_its_factor_and_offsets() -> None:
    grid = (583660.0, 1883820.0, 151, 151)
    # The Sukhothai chip: 2 m pixels from (583664, 1883818), one pixel row and two pixel columns into the grid.
    assert ref.fine_placement(583664.0, 1883818.0, 2.0, grid) == (10, 1, 2)
    # Chaiyaphum: 10 m cells from (820260, 1754770) on a 20 m grid whose north edge is 1754780.
    assert ref.fine_placement(820260.0, 1754770.0, 10.0, (820260.0, 1754780.0, 451, 490)) == (2, 1, 0)
    # A raster that starts before the grid gets negative offsets.
    assert ref.fine_placement(583650.0, 1883830.0, 10.0, grid) == (2, -1, -1)


def test_a_fine_raster_that_does_not_share_cell_edges_is_refused() -> None:
    grid = (0.0, 100.0, 5, 5)
    with pytest.raises(ref.TuningReferenceError):
        ref.fine_placement(5.0, 100.0, 10.0, grid)      # half a 10 m cell off
    with pytest.raises(ref.TuningReferenceError):
        ref.fine_placement(0.0, 100.0, 3.0, grid)       # 20 m is not a whole number of 3 m pixels
    with pytest.raises(ref.TuningReferenceError):
        ref.fine_placement(0.0, 100.0, 40.0, grid)      # coarser than the grid


def test_block_counts_place_the_mask_at_its_offset_and_ignore_what_falls_outside() -> None:
    mask = np.ones((3, 3), dtype=bool)
    # Grid of 2 by 2 cells of 2 by 2 pixels; the mask starts one pixel down and one pixel right.
    counts = ref.block_counts(mask, (2, 2), 2, 1, 1)
    assert counts.tolist() == [[1, 2], [2, 4]]
    # Starting one pixel before the grid: the first row and column of the mask fall outside and are ignored.
    counts = ref.block_counts(mask, (2, 2), 2, -1, -1)
    assert counts.tolist() == [[4, 0], [0, 0]]
    # A mask larger than the grid is cut at the grid's edge.
    assert ref.block_counts(np.ones((9, 9), dtype=bool), (2, 2), 2).tolist() == [[4, 4], [4, 4]]


def test_cell_centres_inside_a_rectangle() -> None:
    inside = ref.centres_inside((0.0, 60.0, 3, 3), {"west": 4.0, "south": 0.0, "east": 49.0, "north": 52.0})
    # Centres at x = 10, 30, 50 and y = 50, 30, 10: x = 50 lies east of 49.
    assert inside.tolist() == [[True, True, False]] * 3


# ---------------------------------------------------------------------------------------------------------------------
# Rule 1: THEOS-2 rule v2 at 2 m onto 20 m (Sukhothai)
# ---------------------------------------------------------------------------------------------------------------------

def invented_theos2() -> tuple[np.ndarray, tuple[float, float, int, int], dict[str, float]]:
    """A 2 m raster of 2 by 4 cells of 20 m, each cell painted to sit on one side of a limit of the rule.

    Codes as rule v2: 0 not water, 1 water, 255 unobservable.
    """

    raster = np.zeros((20, 40), dtype="uint8")

    def paint(row: int, column: int, *runs: tuple[int, int]) -> None:
        """Fill the 100 pixels of one cell, in reading order, with (count, code) runs; the rest stay 0."""

        flat = np.zeros(100, dtype="uint8")
        start = 0
        for count, code in runs:
            flat[start:start + count] = code
            start += count
        raster[row * 10:(row + 1) * 10, column * 10:(column + 1) * 10] = flat.reshape(10, 10)

    paint(0, 0, (50, 1))                 # exactly half water: water
    paint(0, 1, (49, 1))                 # 49 water, 100 with a value: dry
    paint(0, 2, (51, 255), (49, 1))      # 49 with a value: not compared, although all of them are water
    paint(0, 3, (50, 255), (49, 1))      # exactly half with a value, of them 49 water: dry
    paint(1, 0, (100, 1))                # all water, but its centre lies outside the chip: not compared
    paint(1, 1, (60, 255), (40, 1))      # 40 with a value, all water: not compared
    paint(1, 2, (30, 255), (50, 1))      # 70 with a value, 50 water: water
    paint(1, 3)                          # all dry: dry
    grid = (0.0, 40.0, 2, 4)
    rectangle = {"west": 0.0, "south": 0.0, "east": 80.0, "north": 40.0}
    return raster, grid, rectangle


def theos2_reference(raster: np.ndarray, grid: tuple[float, float, int, int], rectangle: dict[str, float],
                     row_offset: int = 0, column_offset: int = 0) -> np.ndarray:
    shape = (grid[2], grid[3])
    water = ref.block_counts(raster == 1, shape, 10, row_offset, column_offset)
    valued = ref.block_counts(raster != 255, shape, 10, row_offset, column_offset)
    inside = ref.centres_inside(grid, rectangle)
    return ref.theos2_cells(water, valued, inside, 100)


def test_theos2_rule_water_at_half_water_dry_at_half_valued_else_not_compared() -> None:
    raster, grid, rectangle = invented_theos2()
    rectangle = dict(rectangle, west=20.0)     # the centre of column 0 (x = 10) lies outside the chip
    reference = theos2_reference(raster, grid, rectangle)
    W, D, N = ref.WATER, ref.DRY, ref.NOT_COMPARED
    assert reference.tolist() == [[N, D, N, D], [N, N, W, D]]
    # With the whole grid inside the chip, cell (0, 0) is water and cell (1, 0) is water too.
    assert theos2_reference(raster, grid, {"west": 0.0, "south": 0.0, "east": 80.0, "north": 40.0}).tolist() == \
        [[W, D, N, D], [W, N, W, D]]


def test_theos2_rule_counts_pixels_outside_the_chip_as_holding_no_value() -> None:
    # A chip of all-water pixels that starts 6 pixels (12 m) into the first column of 20 m cells:
    # the first column has 4 of 10 pixel columns, 40 of 100 pixels: not compared; the second is water.
    raster = np.ones((10, 14), dtype="uint8")
    grid = (0.0, 20.0, 1, 2)
    reference = theos2_reference(raster, grid, {"west": 12.0, "south": 0.0, "east": 40.0, "north": 20.0},
                                 row_offset=0, column_offset=6)
    assert reference.tolist() == [[ref.NOT_COMPARED, ref.WATER]]


def test_theos2_rule_refuses_more_water_than_value() -> None:
    with pytest.raises(ValueError):
        ref.theos2_cells(np.array([[60]]), np.array([[50]]), np.array([[True]]), 100)


# ---------------------------------------------------------------------------------------------------------------------
# Rule 2: the agency layer at 10 m onto 20 m, where the earlier check compared (Mae Sai)
# ---------------------------------------------------------------------------------------------------------------------

def test_agency_rule_water_when_half_of_the_compared_cells_are_water() -> None:
    # Six 20 m cells of 2 by 2 cells of 10 m each.
    water = np.array([[1, 1, 0, 0, 1, 0, 1, 1, 0, 0, 1, 0],
                      [1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0]], dtype=bool)
    compared = np.array([[1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0],
                         [1, 1, 1, 1, 1, 0, 1, 1, 0, 0, 0, 0]], dtype=bool)
    agency = water & compared
    counts_compared = ref.block_counts(compared, (1, 6), 2)
    counts_water = ref.block_counts(agency, (1, 6), 2)
    assert counts_compared.tolist() == [[4, 4, 3, 4, 1, 1]]
    assert counts_water.tolist() == [[3, 1, 1, 3, 0, 1]]
    reference = ref.agency_cells(counts_water, counts_compared, 4)
    W, D, N = ref.WATER, ref.DRY, ref.NOT_COMPARED
    # 3 of 4: water; 1 of 4: dry; 1 of 3: dry; 3 of 4: water; one compared cell (dry, then water): not compared.
    assert reference.tolist() == [[W, D, D, W, N, N]]


def test_agency_rule_two_compared_cells_and_one_of_them_water_is_water() -> None:
    reference = ref.agency_cells(np.array([[1, 0, 2, 0]]), np.array([[2, 2, 2, 0]]), 4)
    assert reference.tolist() == [[ref.WATER, ref.DRY, ref.WATER, ref.NOT_COMPARED]]


def test_agency_rule_refuses_water_outside_the_compared_cells() -> None:
    with pytest.raises(ValueError):
        ref.agency_cells(np.array([[3]]), np.array([[2]]), 4)


# ---------------------------------------------------------------------------------------------------------------------
# Rule 3: the automated optical reference at 10 m onto 20 m (Chaiyaphum)
# ---------------------------------------------------------------------------------------------------------------------

def optical_reference(codes: np.ndarray, shape: tuple[int, int], row_offset: int = 0) -> np.ndarray:
    code_1 = ref.block_counts(codes == 1, shape, 2, row_offset, 0)
    code_0 = ref.block_counts(codes == 0, shape, 2, row_offset, 0)
    return ref.optical_cells(code_1, code_0, 4)


def test_optical_rule_water_at_two_code_1_dry_at_two_code_0_without_code_1() -> None:
    cells = [
        [1, 1, 0, 0],      # two code 1: water
        [1, 0, 0, 0],      # one code 1: not compared, however much is dry
        [0, 0, 3, 4],      # two code 0, no code 1: dry
        [0, 3, 4, 255],    # one code 0: not compared
        [2, 2, 0, 0],      # water on both dates beside two dry cells: dry
        [1, 1, 1, 1],      # all code 1: water
        [3, 3, 4, 4],      # no water and no dry: not compared
        [2, 2, 2, 2],      # water on both dates only: not compared
    ]
    codes = np.zeros((2, 2 * len(cells)), dtype="uint8")
    for index, values in enumerate(cells):
        codes[:, 2 * index:2 * index + 2] = np.array(values, dtype="uint8").reshape(2, 2)
    W, D, N = ref.WATER, ref.DRY, ref.NOT_COMPARED
    assert optical_reference(codes, (1, len(cells))).tolist() == [[W, N, D, N, D, W, N, N]]


def test_optical_rule_counts_cells_outside_the_raster_as_neither_water_nor_dry() -> None:
    # The raster starts one 10 m row below the 20 m grid, as at Chaiyaphum: the top 20 m row sees only two of its
    # four 10 m cells. Two code 0 there still make it dry; one code 1 and one code 0 leave it not compared.
    codes = np.array([[0, 0, 1, 0, 1, 1],
                      [0, 0, 0, 0, 0, 4],
                      [1, 1, 0, 0, 3, 3]], dtype="uint8")
    reference = optical_reference(codes, (2, 3), row_offset=1)
    W, D, N = ref.WATER, ref.DRY, ref.NOT_COMPARED
    assert reference.tolist() == [[D, N, W], [W, D, N]]


# ---------------------------------------------------------------------------------------------------------------------
# Counts, labels and points
# ---------------------------------------------------------------------------------------------------------------------

def test_reference_counts() -> None:
    counts = ref.reference_counts(np.array([[1, 0, 255], [1, 0, 0]], dtype="uint8"))
    assert counts["cells"] == 6 and counts["compared_cells"] == 5 and counts["water_cells"] == 2
    assert counts["dry_cells"] == 3 and counts["not_compared_cells"] == 1
    assert counts["water_share_of_compared"] == 0.4
    assert counts["compared_km2"] == 0.002 and counts["water_km2"] == 0.0008
    assert ref.reference_counts(np.full((2, 2), 255, dtype="uint8"))["water_share_of_compared"] is None
    with pytest.raises(ValueError):
        ref.reference_counts(np.array([[2]], dtype="uint8"))


def test_the_label_at_least_two_of_three_gave() -> None:
    assert ref.label_two_of_three(["water", "water", "not_water"]) == "water"
    assert ref.label_two_of_three(["not_water", "cannot_tell", "not_water"]) == "not_water"
    assert ref.label_two_of_three(["cannot_tell", "water", "cannot_tell"]) == "cannot_tell"
    assert ref.label_two_of_three(["water", "not_water", "cannot_tell"]) is None
    with pytest.raises(ValueError):
        ref.label_two_of_three(["water", "water"])
    with pytest.raises(ValueError):
        ref.label_two_of_three(["water", "wet", "water"])


def test_cell_of_a_point() -> None:
    grid = (583660.0, 1883820.0, 151, 151)
    assert ref.cell_of(584501.0, 1881043.0, grid) == (138, 42)
    assert ref.cell_of(583660.0, 1883820.0, grid) == (0, 0)
    assert ref.cell_of(583659.0, 1883819.0, grid) is None
    assert ref.cell_of(586680.0, 1883000.0, grid) is None


def test_sukhothai_points_skip_every_other_chip_without_looking_at_it() -> None:
    grid = (0.0, 40.0, 2, 2)
    reference = np.array([[1, 0], [255, 1]], dtype="uint8")
    points = [
        {"id": "p1", "chip": "sukhothai", "group": "water_inside", "row": 1, "column": 2, "x": 5.0, "y": 35.0},
        {"id": "p2", "chip": "sukhothai", "group": "land_inside", "row": 15, "column": 1, "x": 3.0, "y": 9.0},
        # A point of another chip: it has no labels in the mapping and must be skipped before they are looked up.
        {"id": "p3", "chip": "chip_003"},
    ]
    labels = {
        "a": {"p1": "water", "p2": "not_water"},
        "b": {"p1": "water", "p2": "cannot_tell"},
        "c": {"p1": "not_water", "p2": "water"},
    }
    kept = ref.sukhothai_points(points, labels, grid, reference)
    assert [point["id"] for point in kept] == ["p1", "p2"]
    assert (kept[0]["row_20m"], kept[0]["column_20m"], kept[0]["label_two_of_three"], kept[0]["reference_20m"]) == \
        (0, 0, "water", 1)
    assert (kept[1]["row_20m"], kept[1]["column_20m"], kept[1]["label_two_of_three"], kept[1]["reference_20m"]) == \
        (1, 0, None, 255)
    table = ref.points_crosstab(kept)
    assert table["water"]["water"] == 1 and table["no_two_alike"]["not_compared"] == 1
    assert sum(sum(row.values()) for row in table.values()) == 2


# ---------------------------------------------------------------------------------------------------------------------
# The firewall, the raster file and the drop rule
# ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "X:/data/proposal_execution/nan_case_v1/jaxa_sealed/JAXA_20250728_FPM_ALOS2_Thailand_geojson.zip",
    "X:/data/theos2/IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif",
    "X:/data/proposal_execution/theos2_water_rule_v2/water_v2_chip_003_2m.tif",
    "X:/data/proposal_execution/theos2_water_rule_v2/chip_001_2m.npz",
    "X:/data/held_chip_001_reference_10m.tif",
    "X:/data/gfm/ensemble_flood_extent.tif",
])
def test_the_firewall_refuses_every_file_of_the_nan_frame(path: str) -> None:
    with pytest.raises(ref.BuildError):
        ref.refuse_firewalled(path)


def test_the_firewall_lets_the_tuning_references_through() -> None:
    for path in (ref.SUKHOTHAI_RASTER, ref.MAE_SAI_RASTER, ref.MAE_SAI_POST, ref.CHAIYAPHUM_RASTER, ref.BOUNDARIES):
        assert ref.refuse_firewalled(Path("X:/external") / path) == Path("X:/external") / path
    for relative in (ref.RULE_V2_FREEZE, ref.CROSS_CHECK_REFERENCE, ref.LABEL_KEY, ref.LABEL_SAMPLE, *ref.LABEL_FILES,
                     ref.DATED_REFERENCE, ref.DATED_RESULT, ref.DATED_RECEIPT, ref.HOLDOUT_RECORD):
        ref.refuse_firewalled(ROOT / relative)


def test_the_reference_raster_is_tiled_deflate_uint8_with_255_as_no_data(tmp_path: Path) -> None:
    import rasterio

    reference = np.array([[1, 0, 255]] * 3, dtype="uint8")
    digest = ref.write_reference(tmp_path / "reference_20m.tif", reference, (100.0, 200.0, 3, 3))
    assert digest == sha256(tmp_path / "reference_20m.tif")
    with rasterio.open(tmp_path / "reference_20m.tif") as source:
        assert source.profile["tiled"] and source.profile["compress"] == "deflate"
        assert source.dtypes == ("uint8",) and source.nodata == 255 and source.crs.to_epsg() == 32647
        assert (source.transform.c, source.transform.f, source.transform.a) == (100.0, 200.0, 20.0)
        assert source.read(1).tolist() == reference.tolist()


def fake_root(tmp_path: Path) -> Path:
    """A copy of the files the run reads from the repository, outside the repository."""

    root = tmp_path / "repo"
    for relative in (ref.PROTOCOL, ref.PLAN, ref.AREAS, ref.SCRIPT):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, root / relative)
    return root


def test_a_reference_that_cannot_be_read_as_recorded_is_dropped_with_its_reason(tmp_path: Path,
                                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    root = fake_root(tmp_path)
    external = tmp_path / "external"
    external.mkdir()

    def unreadable(_external: Path, _grid: Any) -> Any:
        raise ref.TuningReferenceError("invented: the raster is not the one its record binds")

    def readable(_external: Path, grid: Any) -> Any:
        reference = np.full((grid[2], grid[3]), ref.NOT_COMPARED, dtype="uint8")
        reference[:10, :10] = ref.DRY
        reference[:2, :5] = ref.WATER
        return reference, {"source": {"what": "invented"}, "checks": {}, "not_compared_by_reason": {}}

    monkeypatch.setattr(ref, "ROOT", root)
    monkeypatch.setattr(ref, "rights_of", lambda area: {"rights_level": "invented"})
    monkeypatch.setattr(ref, "BUILDERS", {ref.SUKHOTHAI: unreadable, ref.MAE_SAI: unreadable,
                                          ref.CHAIYAPHUM: readable})
    arguments = argparse.Namespace(external_root=str(external), replace=False, reason="")
    record = ref.run(arguments)
    assert record["sets_dropped"] == [ref.SUKHOTHAI, ref.MAE_SAI]
    assert record["sets_built"] == [ref.CHAIYAPHUM]
    assert record["sets"][ref.SUKHOTHAI]["status"] == "dropped"
    assert record["sets"][ref.SUKHOTHAI]["dropped_reason"] == "invented: the raster is not the one its record binds"
    assert "counts" not in record["sets"][ref.SUKHOTHAI]
    assert "drop_rule" in record["sets"][ref.MAE_SAI]
    assert record["sets"][ref.CHAIYAPHUM]["status"] == "built"
    assert record["sets"][ref.CHAIYAPHUM]["counts"]["water_cells"] == 10
    assert record["sets"][ref.CHAIYAPHUM]["counts"]["compared_cells"] == 100
    assert (external / ref.WORK / ref.CHAIYAPHUM / ref.RASTER_NAME).exists()
    assert not (external / ref.WORK / ref.SUKHOTHAI).exists()
    written = root / ref.RECORD
    assert b"\r" not in written.read_bytes()
    # A second run without --replace is refused, and so is any run once the method is frozen.
    with pytest.raises(ref.BuildError):
        ref.run(arguments)
    (root / ref.FREEZE).write_text("{}\n", encoding="utf-8")
    with pytest.raises(ref.BuildError):
        ref.run(argparse.Namespace(external_root=str(external), replace=True, reason="invented"))


# ---------------------------------------------------------------------------------------------------------------------
# The committed record
# ---------------------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def record() -> dict[str, Any]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_the_record_carries_the_fields_of_every_output(record: dict[str, Any]) -> None:
    for key in ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions"):
        assert record[key]
    assert isinstance(record["assumptions"], list) and all(isinstance(line, str) for line in record["assumptions"])
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    assert record["can_feed_decision_layer"] is False
    assert record["value_codes"] == {"1": "water", "0": "dry", "255": "not compared"}
    assert b"\r" not in RECORD.read_bytes()


def test_the_record_binds_the_protocol_the_areas_and_the_code(record: dict[str, Any]) -> None:
    for key, relative in (("protocol", ref.PROTOCOL), ("plan", ref.PLAN), ("areas", ref.AREAS), ("code", ref.SCRIPT)):
        assert record[key] == {"path": relative, "sha256": sha256(ROOT / relative)}, key


def test_every_set_is_built_with_consistent_counts(record: dict[str, Any]) -> None:
    assert record["sets_built"] == [ref.SUKHOTHAI, ref.MAE_SAI, ref.CHAIYAPHUM]
    assert record["sets_dropped"] == []
    areas = json.loads((ROOT / ref.AREAS).read_text(encoding="utf-8"))["areas"]
    for area, entry in record["sets"].items():
        counts = entry["counts"]
        grid = areas[area]["grid"]
        assert entry["grid_20m"]["rows"] == grid["rows"] and entry["grid_20m"]["cols"] == grid["cols"]
        assert counts["cells"] == grid["rows"] * grid["cols"]
        assert counts["compared_cells"] == counts["water_cells"] + counts["dry_cells"]
        assert counts["cells"] == counts["compared_cells"] + counts["not_compared_cells"]
        assert counts["water_share_of_compared"] == round(counts["water_cells"] / counts["compared_cells"], 6)
        assert entry["rule"] == ref.RULES[area]
        assert entry["rights"]["rights_level"] in ("local", "pitch", "public", "unassigned")
        assert len(entry["source"]["sha256"]) == 64 and len(entry["files_outside_git"]["reference_20m.tif"]["sha256"]) == 64


def test_the_references_are_the_recorded_files(record: dict[str, Any]) -> None:
    freeze = json.loads((ROOT / ref.RULE_V2_FREEZE).read_text(encoding="utf-8"))
    assert record["sets"][ref.SUKHOTHAI]["source"]["sha256"] == \
        freeze["frozen_rule"]["chips"]["sukhothai"]["raster_outside_git"]["sha256"]
    dated = json.loads((ROOT / ref.DATED_REFERENCE).read_text(encoding="utf-8"))
    assert record["sets"][ref.MAE_SAI]["source"]["sha256"] == dated["rasters_outside_git"]["dated_reference_10m.tif"]["sha256"]
    holdout = json.loads((ROOT / ref.HOLDOUT_RECORD).read_text(encoding="utf-8"))
    assert record["sets"][ref.CHAIYAPHUM]["source"]["sha256"] == holdout["label_raster_sha256"]


def test_mae_sai_is_held_at_the_local_level_with_whole_district_figures_only(record: dict[str, Any]) -> None:
    entry = record["sets"][ref.MAE_SAI]
    assert entry["rights"]["rights_level"] == "local"
    text = json.dumps(entry)
    for word in ("tambon_", "adm3_pcode", "TH570901", "per_unit"):
        assert word not in text
    assert entry["checks"]["compared_10m_cells"] == entry["checks"]["compared_10m_cells_recorded"]
    assert entry["checks"]["district_redrawn_from_cod_ab_equals_band_2"] is True


def test_the_sukhothai_points_are_the_120_of_that_chip_only(record: dict[str, Any]) -> None:
    points = record["sets"][ref.SUKHOTHAI]["points"]
    assert points["points"] == 120
    assert sum(sum(row.values()) for row in points["points_by_label_and_reference_cell"].values()) == 120
    assert "chip_003" not in json.dumps(points) and "chip_001" not in json.dumps(points)


def test_the_text_passes_the_shared_wording_lint() -> None:
    # The phrase the case prescribes ("agreement with a reference, not accuracy") is a negation the shared rules do
    # not list yet; it is taken out before the lint, and nothing else may match.
    items = [("script", text) for text in python_strings(SCRIPT.read_text(encoding="utf-8"))]
    items += [(f"record {path}", text) for path, text in json_strings(json.loads(RECORD.read_text(encoding="utf-8")))]
    findings = [finding.describe() for source, text in items
                for finding in find_violations(text.replace("not accuracy", ""), WORDING_RULES, source)]
    assert findings == []
