"""The layer handling of the abstention diagnosis (plan task A1), on invented rasters and polygons only.

No file of the external data workspace is read here.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
shapely = pytest.importorskip("shapely")

from rasterio.transform import from_origin  # noqa: E402
from shapely.geometry import box  # noqa: E402

from floodguard import diagnosis_layers as layers  # noqa: E402
from floodguard import diagnosis_run, flood_inputs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = layers.Grid(left=583680.0, top=2273280.0, cell_m=10.0, width=3072, height=4096)


def _write_raster(path: Path, bands: np.ndarray, *, left: float, top: float, cell: float, crs: str, nodata: float | None = None) -> None:
    profile = {"driver": "GTiff", "height": bands.shape[1], "width": bands.shape[2], "count": bands.shape[0], "dtype": str(bands.dtype),
               "crs": crs, "transform": from_origin(left, top, cell, cell)}
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as target:
        target.write(bands)


def test_the_comparison_grid_is_aligned_to_the_source_lattice_and_holds_the_margin() -> None:
    grid = layers.analysis_grid((587443.0, 2252715.0, 598478.0, 2262277.0), SOURCE, cell_m=20.0, margin_m=1000.0)
    west, south, east, north = grid.bounds
    assert (west, south, east, north) == (586440.0, 2251700.0, 599480.0, 2263280.0)
    for edge, origin in ((west, SOURCE.left), (east, SOURCE.left), (south, SOURCE.top), (north, SOURCE.top)):
        assert (edge - origin) % 20.0 == 0.0
    assert west <= 587443.0 - 1000.0 and east >= 598478.0 + 1000.0 and south <= 2252715.0 - 1000.0 and north >= 2262277.0 + 1000.0
    assert grid.shape == (grid.height, grid.width) == (579, 652)
    assert grid.record() == {"crs": "EPSG:32647", "cell_m": 20.0, "width": 652, "height": 579,
                             "bounds": [586440.0, 2251700.0, 599480.0, 2263280.0]}
    with pytest.raises(layers.DiagnosisLayerError, match="whole multiple"):
        layers.analysis_grid((587443.0, 2252715.0, 598478.0, 2262277.0), SOURCE, cell_m=15.0, margin_m=0.0)
    with pytest.raises(layers.DiagnosisLayerError, match="not inside the source grid"):
        layers.analysis_grid((583000.0, 2252715.0, 598478.0, 2262277.0), SOURCE, cell_m=20.0, margin_m=1000.0)


def test_a_cell_belongs_to_a_polygon_by_its_centre() -> None:
    grid = layers.Grid(left=0.0, top=100.0, cell_m=20.0, width=5, height=5)
    # The box reaches 11 m into the second column: its centres at x = 30 are outside, those at x = 10 inside.
    mask = layers.cell_centre_mask(box(0.0, 40.0, 31.0, 100.0), grid)
    assert mask.sum() == 6 and mask[:3, :2].all() and not mask[:, 2:].any() and not mask[3:, :].any()
    assert not layers.cell_centre_mask(box(0, 0, 0, 0), grid).any()
    assert not layers.cell_centre_mask(None, grid).any()


def test_a_stored_raster_is_read_over_the_grid_and_averaged_into_its_cells(tmp_path: Path) -> None:
    rng = np.random.default_rng(2)
    vv = rng.uniform(0.05, 0.5, (8, 12)).astype("float32")
    vh = rng.uniform(0.01, 0.1, (8, 12)).astype("float32")
    vh[0, 0] = np.nan  # No value.
    vh[0, 1] = 0.0  # Not a backscatter value.
    vh[2:4, 2:4] = np.nan  # A whole 20 m cell without a value.
    path = tmp_path / "sigma0.tif"
    _write_raster(path, np.stack([vv, vh]), left=1000.0, top=5000.0, cell=10.0, crs="EPSG:32647", nodata=float("nan"))
    assert layers.source_grid(path) == layers.Grid(1000.0, 5000.0, 10.0, 12, 8)
    grid = layers.Grid(left=1000.0, top=5000.0, cell_m=20.0, width=3, height=2)
    block = layers.read_block_mean(path, grid, band=layers.VH_BAND)
    assert block.shape == (2, 3)
    assert block[0, 0] == pytest.approx(np.mean([vh[1, 0], vh[1, 1]]))  # The two cells without a value are left out.
    assert block[0, 2] == pytest.approx(vh[0:2, 4:6].mean())
    assert np.isnan(block[1, 1])
    shifted = layers.Grid(left=1020.0, top=4980.0, cell_m=20.0, width=2, height=2)
    assert layers.read_block_mean(path, shifted, band=1)[0, 0] == pytest.approx(vv[2:4, 2:4].mean())
    with pytest.raises(layers.DiagnosisLayerError, match="not aligned"):
        layers.read_block_mean(path, layers.Grid(left=1005.0, top=5000.0, cell_m=20.0, width=2, height=2), band=1)
    geographic = tmp_path / "geographic.tif"
    _write_raster(geographic, np.ones((1, 4, 4), dtype="float32"), left=99.0, top=21.0, cell=0.01, crs="EPSG:4326")
    with pytest.raises(layers.DiagnosisLayerError, match="north-up raster in EPSG:32647"):
        layers.source_grid(geographic)


def test_a_raster_in_another_coordinate_system_is_warped_onto_the_grid(tmp_path: Path) -> None:
    # A geographic raster whose west half is 1 and whose east half is 80, split at 99.9 E.
    values = np.ones((1, 200, 200), dtype="uint8")
    values[:, :, 100:] = 80
    path = tmp_path / "classes.tif"
    _write_raster(path, values, left=99.8, top=20.5, cell=0.001, crs="EPSG:4326")
    grid = layers.Grid(left=590000.0, top=2262000.0, cell_m=20.0, width=200, height=50)  # About 99.862 E to 99.900 E.
    nearest = layers.warp_to_grid(path, grid, resampling="nearest")
    assert nearest.shape == grid.shape and set(np.unique(nearest)) <= {1.0, 80.0}
    assert (nearest[:, :150] == 1.0).all()  # Well west of 99.9 E.
    bilinear = layers.warp_to_grid(path, grid, resampling="bilinear")
    assert np.isfinite(bilinear).all() and bilinear.min() >= 1.0 and bilinear.max() <= 80.0
    with pytest.raises(layers.DiagnosisLayerError, match="nearest or bilinear"):
        layers.warp_to_grid(path, grid, resampling="cubic")
    far = layers.Grid(left=100000.0, top=2262000.0, cell_m=20.0, width=4, height=4)
    assert np.isnan(layers.warp_to_grid(path, far, resampling="nearest")).all()  # Outside the raster: no value.


def _register(root: Path, relative: Path, receipt: dict) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(diagnosis_run.encode(receipt))
    register = root / diagnosis_run.REGISTER_DIR
    register.mkdir(parents=True, exist_ok=True)
    (register / f"entry_{relative.stem}.json").write_bytes(
        diagnosis_run.encode({"path": relative.as_posix(), "sha256": diagnosis_run.sha256_file(path)}))


def test_a_radar_receipt_is_read_only_as_the_bytes_the_register_names(tmp_path: Path) -> None:
    root, external = tmp_path / "repo", tmp_path / "data"
    folder = external / "proposal_execution" / "planning_v1" / "o1_mae_sai" / "radar_o1_v1"
    folder.mkdir(parents=True)
    raster = folder / "sigma0_pre_20240903.tif"
    raster.write_bytes(b"not a raster, but bytes with a hash")
    dem = external / "open_context" / "dem.tif"
    dem.parent.mkdir(parents=True)
    dem.write_bytes(b"a height model")
    relative = Path("outputs") / "planning_v1" / "radar_receipt.json"
    receipt = {
        "parameters": {"grid": {"crs": "EPSG:32647", "cell_m": 10.0, "width": 3072, "height": 4096,
                                "bounds": [583680.0, 2232320.0, 614400.0, 2273280.0]}},
        "inputs": {"dem_west": {"path": "<external_data_workspace>/open_context/dem.tif", "sha256": diagnosis_run.sha256_file(dem), "bytes": 14}},
        "outputs": {"rasters": [{"path": "<external_data_workspace>/proposal_execution/planning_v1/o1_mae_sai/radar_o1_v1/sigma0_pre_20240903.tif",
                                 "sha256": diagnosis_run.sha256_file(raster), "bytes": raster.stat().st_size}]},
    }
    _register(root, relative, receipt)
    read, record = layers.registered_receipt(root, relative)
    assert read == receipt and record == {"path": relative.as_posix(), "sha256": diagnosis_run.sha256_file(root / relative)}
    assert layers.receipt_grid(read) == SOURCE
    path, bound = layers.bound_file(read, "sigma0_pre_20240903.tif", external)
    assert path == raster and bound["sha256"] == diagnosis_run.sha256_file(raster)
    assert layers.bound_input(read, "dem_west", external)[0] == dem
    with pytest.raises(layers.DiagnosisLayerError, match="binds no raster"):
        layers.bound_file(read, "sigma0_post_20240915.tif", external)

    # A raster or an input whose bytes changed is refused, and so is a receipt the register does not name.
    raster.write_bytes(b"other bytes")
    with pytest.raises(layers.DiagnosisLayerError, match="not the file its receipt binds"):
        layers.bound_file(read, "sigma0_pre_20240903.tif", external)
    dem.write_bytes(b"another height model")
    with pytest.raises(layers.DiagnosisLayerError, match="not the file the radar receipt names"):
        layers.bound_input(read, "dem_west", external)
    (root / relative).write_bytes((root / relative).read_bytes() + b"\n")
    with pytest.raises(layers.DiagnosisLayerError, match="not the receipt the run register names"):
        layers.registered_receipt(root, relative)
    other = dict(receipt, parameters={"grid": {**receipt["parameters"]["grid"], "crs": "EPSG:4326"}})
    with pytest.raises(layers.DiagnosisLayerError, match="not in EPSG:32647"):
        layers.receipt_grid(other)


def test_the_thai_side_of_a_frame_comes_from_the_boundary_units_that_meet_it(tmp_path: Path) -> None:
    geopandas = pytest.importorskip("geopandas")
    # Two units inside Thailand and one far away; the frame straddles the first two and reaches past them to the north.
    units = geopandas.GeoDataFrame(
        {"adm3_pcode": ["TH570901", "TH570906", "TH999999"]},
        geometry=[box(99.85, 20.40, 99.90, 20.44), box(99.90, 20.40, 99.95, 20.44), box(101.0, 15.0, 101.1, 15.1)], crs="EPSG:4326")
    boundaries = tmp_path / "boundaries.gpkg"
    units.to_file(boundaries, layer=layers.BOUNDARY_LAYER, driver="GPKG")
    frame = flood_inputs.frame_from_wgs84("aoi", "an invented frame", box(99.86, 20.41, 99.94, 20.46), {"path": "invented"})
    inside, record = layers.thailand_side(boundaries, frame, ("TH570901", "TH570906", "TH570903"))
    assert record["units_meeting_the_frame"] == ["TH570901", "TH570906"]
    assert record["all_units_are_in_the_reporting_frame_of_protocol_v1a"] is True
    assert record["share_of_frame"] == pytest.approx(0.6, abs=0.01)  # 0.03 of the 0.05 degrees of latitude are covered.
    assert inside.area == pytest.approx(frame.area_m2 * record["share_of_frame"], rel=1e-4)
    assert layers.thailand_side(boundaries, frame, ("TH570901",))[1]["all_units_are_in_the_reporting_frame_of_protocol_v1a"] is False
    elsewhere = flood_inputs.frame_from_wgs84("far", "far away", box(95.0, 10.0, 95.1, 10.1), {"path": "invented"})
    with pytest.raises(layers.DiagnosisLayerError, match="no tha_admin3 unit"):
        layers.thailand_side(boundaries, elsewhere, ("TH570901",))


def test_the_change_notice_follows_the_order_of_the_rights_record() -> None:
    notice = layers.change_notice(repair_count=2, credit="UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009",
                                  licence_name="CC BY-SA 4.0", raster_cell_m=20.0, then="a statistic was then computed")
    assert notice == (
        "Changed by FloodGuard: clipped to AOI-01 (resources/aoi/aoi-01_mae_sai_core.geojson); geometry repaired (make_valid; 2 "
        "parts repaired); reprojected from EPSG:4326 to EPSG:32647; rasterised to 20 m cells by cell centre; a statistic was then "
        "computed. Source: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009, CC BY-SA 4.0."
    )
    steps = [notice.index(word) for word in ("clipped", "repaired", "reprojected", "rasterised")]
    assert steps == sorted(steps)
    assert "not rasterised" in layers.change_notice(repair_count=0, credit="c", licence_name="l", raster_cell_m=None, then="areas were measured")


def test_the_reporting_units_and_the_boundary_file_come_from_the_signed_protocols(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    units = layers.reporting_units(root)
    assert len(units) == 8 and units[0] == "TH570901" and "TH570907" not in units
    wrong = tmp_path / "boundaries.gdb.zip"
    wrong.write_bytes(b"not the boundary file")
    with pytest.raises(layers.DiagnosisLayerError, match="not the one protocol v1b names"):
        layers.boundary_file(root, tmp_path, wrong)
    assert layers.WATER_READINGS == ("jrc_surface_water", "worldcover_class_80", "nothing_left_out")
    parameters = layers.comparison_parameters()
    assert parameters["cell_m"] == 20.0 and parameters["footprint_layer_read"] is False
    assert json.dumps(parameters)  # Plain JSON values.


def test_the_second_set_of_cells_keeps_the_cells_with_a_slope_under_the_limit() -> None:
    slope = np.array([[0.0, 4.99, 5.0], [12.0, np.nan, 1.0]])
    assert layers.flat_cells(slope).tolist() == [[True, True, False], [False, False, True]], "a cell with no slope value is not flat"
    assert layers.flat_cells(slope, 13.0).tolist() == [[True, True, True], [True, False, True]]
    assert layers.FLAT_SLOPE_DEGREES == 5.0 and layers.CELL_SETS == ("all_cells", "slope_under_5_degrees")
    grid = layers.Grid(0.0, 40.0, 20.0, 3, 2)
    base = np.array([[True, True, True], [True, True, False]])
    water = {layers.WATER_JRC: np.array([[True, False, False], [False, False, False]]), layers.WATER_NONE: np.zeros((2, 3), dtype=bool)}
    domain = layers.ComparisonDomain(grid, np.zeros((2, 3), dtype=bool), base, water, {}, {}, np.zeros((2, 3)), slope)
    assert domain.cells(layers.WATER_NONE).tolist() == base.tolist()
    assert domain.cells(layers.WATER_JRC).tolist() == [[False, True, True], [True, True, False]]
    assert domain.cells(layers.WATER_JRC, layers.CELLS_FLAT).tolist() == [[False, True, False], [False, False, False]]
    assert domain.cells(layers.WATER_NONE, layers.CELLS_FLAT).tolist() == [[True, True, False], [False, False, False]]
    with pytest.raises(layers.DiagnosisLayerError, match="unknown set of cells"):
        domain.cells(layers.WATER_NONE, "hills")
    with pytest.raises(layers.DiagnosisLayerError, match="no slope"):
        layers.ComparisonDomain(grid, base, base, water, {}, {}).cells(layers.WATER_NONE, layers.CELLS_FLAT)
    parameters = layers.comparison_parameters()
    assert parameters["sets_of_cells"] == ["all_cells", "slope_under_5_degrees"] and parameters["flat_slope_limit_degrees"] == 5.0
    assert parameters["footprint_layer_read"] is False


# --- The two rank-statistic scripts, on invented layers ---------------------------------------------------------


def _script(name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"diagnostics_{name}_invented", ROOT / "scripts" / "diagnostics" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def invented_layers(monkeypatch: pytest.MonkeyPatch):
    """Replace the readers of the layers with invented arrays: a wet, flat south and a dry, hilly north."""

    rng = np.random.default_rng(4)
    shape = (80, 60)
    grid = layers.Grid(0.0, 1600.0, 20.0, shape[1], shape[0])
    rows = np.arange(shape[0])[:, None] * np.ones(shape[1])[None, :]
    inside = rows >= 60                                     # The envelope: the southern quarter.
    base = np.ones(shape, dtype=bool)
    base[:, :5] = False                                     # Outside the frame.
    elevation = 400.0 + np.where(rows < 30, (30 - rows) * 8.0, 0.0) + rng.normal(0.0, 0.2, shape)
    from floodguard import abstention_diagnosis

    slope = abstention_diagnosis.slope_degrees(elevation, 20.0)
    water = {layers.WATER_JRC: (rows >= 78) & base, layers.WATER_WORLDCOVER: (rows >= 79) & base, layers.WATER_NONE: np.zeros(shape, dtype=bool)}
    record = {"grid": grid.record(), "by_permanent_water_reading": {}}
    inputs = {"dem_glo30_n20_e099": {"path": "<external_data_workspace>/dem.tif", "sha256": "1" * 64, "bytes": 1}}
    domain = layers.ComparisonDomain(grid, inside, base, water, record, inputs, elevation, slope)
    grant = {"licence": {"name": "CC BY-SA 4.0", "url": "https://creativecommons.org/licenses/by-sa/4.0/"}, "share_alike": "invented",
             "record_path": "docs/invented.json", "record_sha256": "2" * 64}
    envelope = layers.Envelope(frame=None, geometry=None, repair_count=2, inputs={}, rights={"grant": grant}, credit="an invented credit",
                               licence_name="CC BY-SA 4.0", standard_sentence="invented", layer="invented", source_timestamp="invented")
    # Before: noise around one level. After: the envelope is darker in VH, by 3 dB.
    before = 10 ** (rng.normal(-15.0, 1.0, shape) / 10)
    after = 10 ** ((rng.normal(-15.0, 1.0, shape) - np.where(inside, 3.0, 0.0)) / 10)

    def registered_receipt(root: Path, relative: Path):
        geocoding = next(name for name, path in layers.RADAR_RECEIPTS.items() if path == relative)
        return {"parameters": {"geocoding": geocoding}, "run_role": f"invented {geocoding}"}, {"path": relative.as_posix(), "sha256": "3" * 64}

    monkeypatch.setattr(layers, "load_envelope", lambda root, external: envelope)
    monkeypatch.setattr(layers, "comparison_domain", lambda root, external, loaded: domain)
    monkeypatch.setattr(layers, "registered_receipt", registered_receipt)
    monkeypatch.setattr(layers, "receipt_grid", lambda receipt: grid)
    monkeypatch.setattr(layers, "source_grid", lambda path: grid)
    monkeypatch.setattr(layers, "bound_file", lambda receipt, name, external: (Path(name), {"path": name, "sha256": "4" * 64, "bytes": 1}))
    monkeypatch.setattr(layers, "read_block_mean", lambda path, target, band: before if "pre" in path.name else after)
    return domain


def test_the_darkening_script_gives_every_reading_on_invented_layers(invented_layers: layers.ComparisonDomain, tmp_path: Path) -> None:
    module = _script("darkening_auc_vs_envelope")
    result = module.make_compute(ROOT, tmp_path)()
    figures = result.figures
    readings, by_window = figures["readings"], figures["readings_by_smoothing_window"]
    # Two geocodings, three ways of leaving out water and two sets of cells at the 5 by 5 window; six windows on two sets.
    assert len(readings) == 12 and {row["window_cells"] for row in readings} == {5}
    assert {(row["geocoding"], row["permanent_water"], row["cells"]) for row in readings} == {
        (geocoding, water, cells) for geocoding in layers.RADAR_RECEIPTS for water in layers.WATER_READINGS for cells in layers.CELL_SETS}
    assert len(by_window) == 24 and figures["windows_cells"] == [1, 3, 5, 9, 15, 25] == sorted({row["window_cells"] for row in by_window})
    assert {row["permanent_water"] for row in by_window} == {layers.WATER_JRC}
    for row in readings + by_window:
        assert row["auc"] > 0.9, "the invented envelope is 3 dB darker after: darkening separates it"
        assert row["auc_of_brightening"] == pytest.approx(1 - row["auc"], abs=1e-6)
        assert row["cells_inside_the_layer"] > 0 and row["cells_outside_the_layer"] > 0
    # The 5 by 5 rows of the window table repeat the readings above.
    for row in by_window:
        if row["window_cells"] == 5:
            assert row in readings
    # The flat set leaves the hilly north out, so it holds fewer cells outside the envelope.
    everything = next(row for row in readings if row["cells"] == layers.CELLS_ALL and row["permanent_water"] == layers.WATER_NONE)
    flat = next(row for row in readings if row["cells"] == layers.CELLS_FLAT and row["permanent_water"] == layers.WATER_NONE)
    assert flat["cells_outside_the_layer"] < everything["cells_outside_the_layer"] and flat["geocoding"] == everything["geocoding"]
    assert figures["reading_that_follows_the_exploratory_definition"] == {
        "geocoding": "gcp_polynomial", "permanent_water": layers.WATER_JRC, "cells": layers.CELLS_ALL, "window_cells": 5,
        "auc": next(row["auc"] for row in readings if row["geocoding"] == "gcp_polynomial" and row["permanent_water"] == layers.WATER_JRC
                    and row["cells"] == layers.CELLS_ALL)}
    assert figures["every_reading_is_below_one_half"] is False and result.plan_figure["reproduced"] is False
    assert set(figures["the_value_falls_at_every_step_as_the_window_grows"]) == set(layers.RADAR_RECEIPTS)
    assert [point["id"] for point in result.open_points] == ["A1-OP2", "A1-OP3", "A1-OP4", "A1-OP5", "A1-OP6", "A1-OP10"]
    assert result.parameters["boxcar_windows_cells"] == [1, 3, 5, 9, 15, 25] and result.parameters["boxcar_cells"] == 5
    assert "dem_glo30_n20_e099" in result.inputs and layers.ATTRIBUTION_DEM in result.attributions
    assert result.licence["change_notice"].startswith("Changed by FloodGuard: clipped to AOI-01")
    # The peak is not stated as a fact: the replay's keyframe is named as what it is.
    text = " ".join(list(result.assumptions) + list(result.limits))
    assert "after the flood peak" not in text and "keyframe" in text and "illustrative" in text
    diagnosis_run.encode({"figures": dict(figures), "inputs": dict(result.inputs), "parameters": dict(result.parameters)})


def test_the_terrain_script_gives_every_reading_on_invented_layers(invented_layers: layers.ComparisonDomain, tmp_path: Path) -> None:
    module = _script("terrain_auc_vs_envelope")
    result = module.make_compute(ROOT, tmp_path)()
    readings = result.figures["readings"]
    assert len(readings) == 12
    assert {(row["feature"], row["permanent_water"], row["cells"]) for row in readings} == {
        (feature, water, cells) for feature in ("low_elevation", "low_slope") for water in layers.WATER_READINGS for cells in layers.CELL_SETS}
    by_key = {(row["feature"], row["permanent_water"], row["cells"]): row for row in readings}
    # On all cells both features tell the hilly north from the flat south, where the envelope lies. On the flat cells
    # alone that is gone: the plain is level, so neither feature separates the envelope there.
    for feature in ("low_elevation", "low_slope"):
        assert by_key[(feature, layers.WATER_NONE, layers.CELLS_ALL)]["auc"] > 0.65
        assert abs(by_key[(feature, layers.WATER_NONE, layers.CELLS_FLAT)]["auc"] - 0.5) < 0.05
    assert set(result.figures["smallest_and_largest_auc_by_feature"]) == set(layers.CELL_SETS)
    assert [point["id"] for point in result.open_points] == ["A1-OP1", "A1-OP4", "A1-OP6", "A1-OP10"]
    note = result.plan_figure["note"]
    assert "first computation from cleared files and the first recorded value" in note and "not the first time the figure was seen" in note
    assert result.plan_figure["plan_value"] is None and result.plan_figure["reproduced"] is None
    assert "radar" not in result.inputs and "HAND (height above the nearest drainage)" in result.not_computed
    diagnosis_run.encode({"figures": dict(result.figures), "inputs": dict(result.inputs), "parameters": dict(result.parameters)})
