"""Synthetic tests for the Sentinel-1 sigma0 reader (no external data).

The SAFE archive used here is built in a scratch folder: a small measurement
GeoTIFF with ground control points, a calibration annotation, a product
annotation with a geolocation grid and a manifest.
"""

from __future__ import annotations

from pathlib import Path
import zipfile

import numpy as np
import pytest

from floodguard import sentinel1_sigma0 as s1

rasterio = pytest.importorskip("rasterio")
pytest.importorskip("pyproj")
pytest.importorskip("scipy")

PRODUCT = "S1A_IW_GRDH_1SDV_20240101T000000_20240101T000025_000001_000001_TEST.SAFE"
STEM = "s1a-iw-grd-{pol}-20240101t000000-20240101t000025-000001-000001-00{number}"
ROWS, COLS = 120, 160
LON0, LAT0 = 99.90, 20.42
STEP = 0.0001  # About 10.4 m east-west and 11.1 m north-south at this latitude.
GAIN = 500.0


def _calibration_xml(lines: list[int], pixels: list[int], values: list[list[float]]) -> str:
    vectors = "".join(
        "<calibrationVector>"
        f"<azimuthTime>2024-01-01T00:00:00.000000</azimuthTime><line>{line}</line>"
        f'<pixel count="{len(pixels)}">{" ".join(str(pixel) for pixel in pixels)}</pixel>'
        f'<sigmaNought count="{len(pixels)}">{" ".join(repr(value) for value in row)}</sigmaNought>'
        f'<betaNought count="{len(pixels)}">{" ".join("1.0" for _ in pixels)}</betaNought>'
        "</calibrationVector>"
        for line, row in zip(lines, values)
    )
    return (
        "<calibration><calibrationInformation><absoluteCalibrationConstant>1.0"
        "</absoluteCalibrationConstant></calibrationInformation>"
        f'<calibrationVectorList count="{len(lines)}">{vectors}</calibrationVectorList></calibration>'
    )


def _annotation_xml(points: list[tuple[float, float, float, float, float, float]]) -> str:
    grid = "".join(
        "<geolocationGridPoint>"
        f"<line>{line:g}</line><pixel>{pixel:g}</pixel><latitude>{lat!r}</latitude>"
        f"<longitude>{lon!r}</longitude><height>{height!r}</height><incidenceAngle>{angle!r}</incidenceAngle>"
        "</geolocationGridPoint>"
        for line, pixel, lat, lon, height, angle in points
    )
    return (
        "<product><generalAnnotation/><imageAnnotation><imageInformation>"
        "<rangePixelSpacing>1.000000e+01</rangePixelSpacing>"
        "<azimuthPixelSpacing>1.000000e+01</azimuthPixelSpacing></imageInformation></imageAnnotation>"
        "<coordinateConversion/><productInformation><projection>Ground Range</projection></productInformation>"
        f'<geolocationGrid><geolocationGridPointList count="{len(points)}">{grid}'
        "</geolocationGridPointList></geolocationGrid></product>"
    )


MANIFEST = (
    '<xfdu:XFDU xmlns:safe="x" xmlns:s1="y"><safe:acquisitionPeriod>'
    "<safe:startTime>2024-01-01T00:00:00.000000</safe:startTime>"
    "<safe:stopTime>2024-01-01T00:00:25.000000</safe:stopTime></safe:acquisitionPeriod>"
    '<safe:relativeOrbitNumber type="start">135</safe:relativeOrbitNumber>'
    "<s1:pass>DESCENDING</s1:pass>"
    '<safe:software name="Sentinel-1 IPF" version="003.80"/></xfdu:XFDU>'
)


def _dn_field() -> np.ndarray:
    """A bright block on a darker ground, with a fill border of zeros."""

    dn = np.full((ROWS, COLS), 200, dtype="uint16")
    dn[40:80, 60:110] = 400
    dn[:, :3] = 0
    return dn


@pytest.fixture()
def safe_archive(tmp_path: Path) -> Path:
    """Write a small SAFE archive whose control points are a plain north-up grid."""

    from rasterio.control import GroundControlPoint

    gcps = [
        GroundControlPoint(row=row, col=col, x=LON0 + col * STEP, y=LAT0 - row * STEP, z=400.0)
        for row in (0, ROWS // 2, ROWS)
        for col in (0, COLS // 2, COLS)
    ]
    calibration = _calibration_xml([0, ROWS], [0, COLS], [[GAIN, GAIN], [GAIN, GAIN]])
    points = [
        (line, pixel, LAT0 - line * STEP, LON0 + pixel * STEP, 400.0, 37.0)
        for line in (0.0, float(ROWS))
        for pixel in (0.0, COLS / 2, float(COLS))
    ]
    archive = tmp_path / f"{PRODUCT}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for number, pol in ((1, "vv"), (2, "vh")):
            stem = STEM.format(pol=pol, number=number)
            tiff = tmp_path / f"{stem}.tiff"
            with rasterio.open(
                tiff, "w", driver="GTiff", width=COLS, height=ROWS, count=1, dtype="uint16",
                gcps=gcps, crs="EPSG:4326",
            ) as target:
                target.write(_dn_field() if pol == "vh" else (_dn_field() // 2).astype("uint16"), 1)
            bundle.write(tiff, f"{PRODUCT}/measurement/{stem}.tiff")
            bundle.writestr(f"{PRODUCT}/annotation/calibration/calibration-{stem}.xml", calibration)
            bundle.writestr(f"{PRODUCT}/annotation/calibration/noise-{stem}.xml", "<noise/>")
            bundle.writestr(f"{PRODUCT}/annotation/{stem}.xml", _annotation_xml(points))
        bundle.writestr(f"{PRODUCT}/manifest.safe", MANIFEST)
    return archive


def _grid() -> s1.RasterGrid:
    """A 10 m UTM 47N grid inside the synthetic image."""

    from pyproj import Transformer

    x, y = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform(
        LON0 + 20 * STEP, LAT0 - 15 * STEP
    )
    return s1.RasterGrid(
        crs="EPSG:32647", west=round(x, -1), north=round(y, -1), cell_m=10.0, width=120, height=80
    )


# --- grid -----------------------------------------------------------------


def test_grid_bounds_and_cell_centres() -> None:
    grid = s1.RasterGrid(crs="EPSG:32647", west=1000.0, north=2000.0, cell_m=10.0, width=3, height=2)
    assert grid.shape == (2, 3)
    assert grid.bounds == (1000.0, 1980.0, 1030.0, 2000.0)
    x, y = grid.cell_centres()
    assert x.tolist() == [1005.0, 1015.0, 1025.0] and y.tolist() == [1995.0, 1985.0]
    with pytest.raises(s1.Sentinel1Error):
        s1.RasterGrid(crs="EPSG:32647", west=0.0, north=0.0, cell_m=0.0, width=1, height=1)


# --- calibration ----------------------------------------------------------


def test_calibration_lut_is_read_and_interpolated_bilinearly() -> None:
    lut = s1.parse_calibration_lut(_calibration_xml([0, 10], [0, 4], [[100.0, 200.0], [300.0, 400.0]]))
    assert lut.lines.tolist() == [0.0, 10.0]
    assert lut.sigma_nought.shape == (2, 2)
    gain = s1.calibration_gain(lut, 0, 0, 11, 5)
    assert gain[0, 0] == 100.0 and gain[0, 4] == 200.0 and gain[10, 0] == 300.0 and gain[10, 4] == 400.0
    assert gain[5, 2] == pytest.approx(250.0)
    assert gain[0, 1] == pytest.approx(125.0) and gain[2, 0] == pytest.approx(140.0)
    # A window is the same table read at an offset; lines past the last vector take the last vector.
    assert np.allclose(s1.calibration_gain(lut, 3, 1, 4, 3), gain[3:7, 1:4])
    assert np.allclose(s1.calibration_gain(lut, 10, 0, 3, 5), np.broadcast_to(gain[10], (3, 5)))


@pytest.mark.parametrize(
    ("lines", "pixels", "values", "message"),
    [
        ([0], [0, 4], [[1.0, 1.0]], "at least two vectors"),
        ([0, 10], [0, 4], [[1.0, 0.0], [1.0, 1.0]], "positive"),
        ([10, 0], [0, 4], [[1.0, 1.0], [1.0, 1.0]], "lines"),
        ([0, 10], [4, 0], [[1.0, 1.0], [1.0, 1.0]], "pixels"),
    ],
)
def test_calibration_lut_refuses_a_table_it_cannot_use(
    lines: list[int], pixels: list[int], values: list[list[float]], message: str
) -> None:
    with pytest.raises(s1.Sentinel1Error, match=message):
        s1.parse_calibration_lut(_calibration_xml(lines, pixels, values))


def test_calibration_lut_refuses_text_that_is_not_xml() -> None:
    with pytest.raises(s1.Sentinel1Error, match="not XML"):
        s1.parse_calibration_lut("sigmaNought 1 2 3")


def test_sigma0_is_dn_squared_over_gain_squared_and_fill_is_nan() -> None:
    dn = np.array([[0, 500], [250, 1000]], dtype="uint16")
    sigma0 = s1.sigma0_from_dn(dn, np.full((2, 2), 500.0))
    assert np.isnan(sigma0[0, 0])
    assert sigma0[0, 1] == pytest.approx(1.0) and sigma0[1, 0] == pytest.approx(0.25)
    assert sigma0[1, 1] == pytest.approx(4.0)
    assert sigma0.dtype == np.float32
    with pytest.raises(s1.Sentinel1Error, match="share a shape"):
        s1.sigma0_from_dn(dn, np.ones((3, 2)))


# --- annotation -----------------------------------------------------------


def test_geolocation_grid_is_read_as_a_rectangle() -> None:
    points = [
        (line, pixel, 20.0 - line / 1000.0, 99.0 + pixel / 1000.0, 100.0 + line + pixel, 30.0 + pixel / 100.0)
        for pixel in (0.0, 50.0, 100.0)
        for line in (40.0, 0.0)
    ]
    grid = s1.parse_geolocation_grid(_annotation_xml(points))
    assert grid.lines.tolist() == [0.0, 40.0] and grid.pixels.tolist() == [0.0, 50.0, 100.0]
    assert grid.height.tolist() == [[100.0, 150.0, 200.0], [140.0, 190.0, 240.0]]
    assert grid.longitude[1, 2] == pytest.approx(99.1) and grid.incidence_deg[0, 1] == pytest.approx(30.5)
    with pytest.raises(s1.Sentinel1Error, match="rectangle"):
        s1.parse_geolocation_grid(_annotation_xml(points[:-1]))
    with pytest.raises(s1.Sentinel1Error, match="no geolocation grid"):
        s1.parse_geolocation_grid("<product/>")


def test_archive_members_and_product_description(safe_archive: Path) -> None:
    with zipfile.ZipFile(safe_archive) as bundle:
        names = bundle.namelist()
    assert s1.measurement_member(names, "vh").endswith("-002.tiff")
    assert "calibration-" in s1.calibration_member(names, "vv")
    assert "/annotation/s1a-iw-grd-vh" in s1.annotation_member(names, "vh")
    with pytest.raises(s1.Sentinel1Error, match="unknown polarisation"):
        s1.measurement_member(names, "hh")
    with pytest.raises(s1.Sentinel1Error, match="0 files"):
        s1.measurement_member([name for name in names if "-vh-" not in name], "vh")
    metadata = s1.read_product_metadata(safe_archive)
    assert metadata["product"] == PRODUCT
    assert metadata["pass"] == "descending" and metadata["relative_orbit"] == 135
    assert metadata["acquisition_start_utc"] == "2024-01-01T00:00:00.000000"
    assert metadata["processor"] == "Sentinel-1 IPF 003.80"
    assert metadata["projection"] == "Ground Range" and metadata["range_pixel_spacing_m"] == 10.0
    grid = s1.read_geolocation_grid(safe_archive)
    assert grid.height.shape == (2, 3)


# --- reading and warping --------------------------------------------------


def test_window_is_calibrated_and_warped_with_the_control_points(safe_archive: Path) -> None:
    from pyproj import Transformer

    grid = _grid()
    window = s1.read_sigma0_window(safe_archive, "vh", grid)
    assert window.image_shape == (ROWS, COLS)
    assert window.gain_range == pytest.approx((GAIN, GAIN))
    assert window.values.dtype == np.float32
    dn = _dn_field()[
        window.row_offset : window.row_offset + window.values.shape[0],
        window.col_offset : window.col_offset + window.values.shape[1],
    ]
    expected = np.where(dn > 0, (dn / GAIN) ** 2, np.nan)
    assert np.allclose(window.values, expected, equal_nan=True)
    # Never the uncalibrated amplitude: the values are sigma0, far below the digital numbers.
    assert np.nanmax(window.values) == pytest.approx((400 / GAIN) ** 2)

    warped = s1.warp_gcp_polynomial(window, grid)
    assert warped.shape == grid.shape
    to_geographic = Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True)
    x, y = grid.cell_centres()
    mesh_x, mesh_y = np.meshgrid(x, y)
    lon, lat = to_geographic.transform(mesh_x, mesh_y)
    col = (lon - LON0) / STEP
    row = (LAT0 - lat) / STEP
    inside_block = (row > 42) & (row < 78) & (col > 62) & (col < 108)
    outside_block = ((row < 38) | (row > 82) | (col < 58) | (col > 112)) & (col > 6)
    assert inside_block.sum() > 500 and outside_block.sum() > 500
    assert np.allclose(warped[inside_block], (400 / GAIN) ** 2, rtol=1e-4)
    assert np.allclose(warped[outside_block], (200 / GAIN) ** 2, rtol=1e-4)

    vv = s1.warp_gcp_polynomial(s1.read_sigma0_window(safe_archive, "vv", grid), grid)
    assert np.allclose(vv[inside_block], (200 / GAIN) ** 2, rtol=1e-4)


def test_window_reader_refuses_a_grid_outside_the_image(safe_archive: Path) -> None:
    far = s1.RasterGrid(crs="EPSG:32647", west=300000.0, north=1500000.0, cell_m=10.0, width=10, height=10)
    with pytest.raises(s1.Sentinel1Error, match="outside the image"):
        s1.read_sigma0_window(safe_archive, "vh", far, margin_degrees=0.0)


# --- the mapping that uses a height for every cell ------------------------

X_EDGE, Y_EDGE, TAN = 620000.0, 2270000.0, np.tan(np.radians(37.0))


def _true_image_coordinates(x: np.ndarray, y: np.ndarray, height: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A flat-earth radar looking west: a higher target appears nearer, at a smaller sample."""

    return (Y_EDGE - y) / 10.0, (X_EDGE - x - height / TAN) / 10.0


def _synthetic_mapping() -> s1.HeightAwareMapping:
    lines = np.linspace(0.0, 4000.0, 5)
    pixels = np.linspace(0.0, 5000.0, 6)
    mesh_pixel, mesh_line = np.meshgrid(pixels, lines)
    rng = np.random.default_rng(3)
    height = rng.uniform(300.0, 1500.0, size=mesh_line.shape)  # A coarse terrain model, wrong for most cells.
    x = X_EDGE - 10.0 * mesh_pixel - height / TAN
    y = Y_EDGE - 10.0 * mesh_line
    return s1.HeightAwareMapping.from_projected_grid(lines, pixels, x, y, height, np.full(x.shape, 37.0))


def test_height_aware_mapping_recovers_a_known_geometry() -> None:
    mapping = _synthetic_mapping()
    grid = s1.RasterGrid(crs="EPSG:32647", west=590000.0, north=2255000.0, cell_m=10.0, width=96, height=64)
    x, y = grid.cell_centres()
    mesh_x, mesh_y = np.meshgrid(x, y)
    height = 400.0 + 0.02 * (mesh_x - x[0]) + 300.0 * (np.sin(mesh_y / 150.0) > 0)
    rows, cols = mapping.image_coordinates(grid, height)
    true_rows, true_cols = _true_image_coordinates(mesh_x, mesh_y, height)
    assert np.abs(rows - true_rows).max() < 0.05
    assert np.abs(cols - true_cols).max() < 0.05
    # The control points alone, read at their own heights, are off by (their height - the true height) / tan.
    assert np.abs(cols - (X_EDGE - mesh_x) / 10.0).max() > 30.0


def test_height_aware_mapping_refuses_bad_input() -> None:
    mapping = _synthetic_mapping()
    grid = s1.RasterGrid(crs="EPSG:32647", west=590000.0, north=2255000.0, cell_m=10.0, width=8, height=8)
    with pytest.raises(s1.Sentinel1Error, match="shape of the grid"):
        mapping.image_coordinates(grid, np.zeros((4, 4)))
    with pytest.raises(s1.Sentinel1Error, match="finite height"):
        mapping.image_coordinates(grid, np.full((8, 8), np.nan))
    with pytest.raises(s1.Sentinel1Error, match="rectangles"):
        s1.HeightAwareMapping.from_projected_grid(
            np.array([0.0, 1.0]), np.array([0.0, 1.0]), np.zeros((2, 3)), np.zeros((2, 2)),
            np.zeros((2, 2)), np.full((2, 2), 30.0),
        )


def test_sample_window_reads_bilinearly_at_image_coordinates() -> None:
    values = np.arange(20, dtype="float32").reshape(4, 5)
    window = s1.Sigma0Window(
        values=values, row_offset=10, col_offset=100, gcps=(), gcp_crs=None, image_shape=(50, 500),
        gain_range=(1.0, 1.0),
    )
    rows = np.array([[10.0, 11.5], [13.0, 30.0]])
    cols = np.array([[100.0, 102.5], [104.0, 101.0]])
    sampled = s1.sample_window(window, rows, cols)
    assert sampled[0, 0] == 0.0 and sampled[1, 0] == 19.0
    assert sampled[0, 1] == pytest.approx(10.0)  # Halfway between rows 1 and 2, columns 2 and 3.
    assert np.isnan(sampled[1, 1])


# --- displacement ---------------------------------------------------------


def test_displacement_of_a_shifted_image_is_measured() -> None:
    rng = np.random.default_rng(11)
    reference = np.zeros((160, 200))
    for _ in range(25):
        row, col = rng.integers(20, 130), rng.integers(20, 170)
        reference[row : row + rng.integers(3, 12), col : col + rng.integers(3, 12)] = 1.0
    # The image content lies 5 cells west and 3 cells south of the reference content.
    image = np.roll(reference, shift=(3, -5), axis=(0, 1)) + rng.normal(0.0, 0.2, size=reference.shape)
    valid = np.ones(reference.shape, dtype=bool)
    result = s1.estimate_displacement(reference, image, valid, max_shift_cells=12)
    assert (result["east_cells"], result["north_cells"]) == (-5, -3)
    assert result["correlation"] > 0.5 and result["at_search_edge"] is False
    aligned = s1.estimate_displacement(reference, reference, valid, max_shift_cells=12)
    assert (aligned["east_cells"], aligned["north_cells"]) == (0, 0)
    assert aligned["correlation"] == pytest.approx(1.0)
    # A shift larger than the search window ends on its edge and says so.
    far = s1.estimate_displacement(reference, np.roll(reference, 30, axis=1), valid, max_shift_cells=8)
    assert far["at_search_edge"] is True or far["correlation"] < 0.5


def test_displacement_refuses_layers_it_cannot_compare() -> None:
    layer = np.zeros((40, 40))
    valid = np.ones(layer.shape, dtype=bool)
    with pytest.raises(s1.Sentinel1Error, match="constant"):
        s1.estimate_displacement(layer, layer, valid, max_shift_cells=4)
    with pytest.raises(s1.Sentinel1Error, match="max_shift_cells"):
        s1.estimate_displacement(layer, layer, valid, max_shift_cells=20)
    with pytest.raises(s1.Sentinel1Error, match="too few"):
        s1.estimate_displacement(layer, layer, np.zeros(layer.shape, dtype=bool), max_shift_cells=4)
