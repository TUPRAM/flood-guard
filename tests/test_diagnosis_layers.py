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
