"""Tests of the terrain lane of the Nan case (scripts/nan_case_terrain.py), on invented data only.

The grid tests build an invented world in a temporary folder: a small V-shaped valley as a Copernicus DEM tile and
an invented WorldCover tile with a river along the valley floor, and run the whole build of one area on them with
fetching switched off. The other tests check the pieces: the most-common-class aggregation, the slope of a plane,
HAND of a synthetic valley, the hydrology window and the tile names. Nothing here reads a radar image, a flood
reference or a real tile.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import re

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nan_case_terrain.py"
_SPEC = importlib.util.spec_from_file_location("nan_case_terrain", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
terrain = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(terrain)

rasterio = pytest.importorskip("rasterio")


# ---------------------------------------------------------------------------
# Most common class
# ---------------------------------------------------------------------------


def test_most_common_class_takes_the_majority_of_the_four_ten_metre_cells() -> None:
    fine = np.array([
        [40, 40, 50, 80, 0, 0],
        [40, 10, 80, 50, 0, 0],
        [10, 20, 30, 30, 0, 80],
        [30, 40, 30, 10, 0, 0],
    ], dtype="uint8")
    coarse = terrain.most_common_class(fine, 2, 0)
    assert coarse.dtype == np.uint8
    assert coarse.shape == (2, 3)
    assert coarse[0, 0] == 40  # three of four
    assert coarse[0, 1] == 50  # a tie of two and two goes to the smaller code
    assert coarse[0, 2] == 0  # only no-data cells
    assert coarse[1, 0] == 10  # four classes once each: the smallest code
    assert coarse[1, 1] == 30
    assert coarse[1, 2] == 80  # no-data cells are not counted


def test_most_common_class_refuses_a_grid_that_is_not_whole_blocks() -> None:
    with pytest.raises(terrain.TerrainError):
        terrain.most_common_class(np.zeros((3, 4), dtype="uint8"), 2, 0)


# ---------------------------------------------------------------------------
# Slope
# ---------------------------------------------------------------------------


def test_slope_of_a_synthetic_plane_is_its_angle_everywhere_on_the_grid() -> None:
    cell = 20.0
    rows, columns = 12, 9
    east = (np.arange(columns + 2) * cell)[None, :]
    north = ((rows + 1 - np.arange(rows + 2)) * cell)[:, None]
    plane = 50.0 + 0.10 * east + 0.05 * north  # read with a margin of one cell
    slope = terrain.slope_on_grid(plane, cell)
    assert slope.shape == (rows, columns)
    assert np.isfinite(slope).all()  # border cells of the grid have a slope thanks to the margin
    assert np.allclose(slope, math.degrees(math.atan(math.hypot(0.10, 0.05))), atol=1e-4)
    flat = terrain.slope_on_grid(np.full((5, 5), 7.0), cell)
    assert np.allclose(flat, 0.0)


# ---------------------------------------------------------------------------
# DEM mosaic
# ---------------------------------------------------------------------------


def test_the_mosaic_keeps_the_tile_values_on_their_own_lattice(tmp_path: Path) -> None:
    from rasterio.transform import from_origin

    step = 1 / 3600
    paths = []
    for index, west in enumerate((99.0, 100.0)):
        # Pixel edges half a pixel off whole arc-seconds, as in the GLO-30 tiles (pixel-is-point).
        transform = from_origin(west - step / 2, 21.0 + step / 2, step, step)
        values = (np.arange(40 * 3600).reshape(40, 3600) % 997 + 1000 * index).astype("float32")
        path = tmp_path / f"tile_{index}.tif"
        with rasterio.open(path, "w", driver="GTiff", height=40, width=3600, count=1, dtype="float32", crs="EPSG:4326",
                           transform=transform) as target:
            target.write(values, 1)
        paths.append(path)
    box = (99.9871, 20.9912, 100.0133, 20.9973)  # edges between pixel edges
    mosaic, transform, _crs = terrain.mosaic_dem(paths, box)
    column = (transform.c - (99.0 - step / 2)) / step
    row = ((21.0 + step / 2) - transform.f) / step
    assert abs(column - round(column)) < 1e-6 and abs(row - round(row)) < 1e-6  # on the tiles' lattice
    with rasterio.open(paths[0]) as source:
        first = source.read(1)
        col0 = int(round((transform.c - source.transform.c) / step))
        row0 = int(round((source.transform.f - transform.f) / step))
    width_in_first = 3600 - col0
    assert np.array_equal(mosaic[:, :width_in_first], first[row0:row0 + mosaic.shape[0], col0:])
    with rasterio.open(paths[1]) as source:
        second = source.read(1)
    assert np.array_equal(mosaic[:, width_in_first:], second[row0:row0 + mosaic.shape[0], :mosaic.shape[1] - width_in_first])
    snapped = terrain.snap_to_lattice(box, from_origin(99.0 - step / 2, 21.0 + step / 2, step, step))
    assert snapped[0] <= box[0] and snapped[1] <= box[1] and snapped[2] >= box[2] and snapped[3] >= box[3]


# ---------------------------------------------------------------------------
# HAND
# ---------------------------------------------------------------------------


def write_dem(path: Path, dem: np.ndarray, cell: float, west: float = 600000.0, north: float = 2000000.0) -> None:
    from rasterio.transform import from_origin

    with rasterio.open(path, "w", driver="GTiff", height=dem.shape[0], width=dem.shape[1], count=1, dtype="float32",
                       nodata=terrain.DEM_NODATA, crs="EPSG:32647", transform=from_origin(west, north, cell, cell)) as target:
        target.write(dem.astype("float32"), 1)


def valley(rows: int = 60, columns: int = 41) -> np.ndarray:
    """A V-shaped valley with its floor on column 20, falling 0.5 m per row towards the south edge."""

    column = np.arange(columns)[None, :]
    row = np.arange(rows)[:, None]
    return (100.0 + 2.0 * np.abs(column - 20) + 0.5 * (rows - row)).astype("float32")


def test_hand_of_a_synthetic_valley_is_zero_on_its_stream(tmp_path: Path) -> None:
    pytest.importorskip("pysheds")
    dem = valley()
    path = tmp_path / "valley.tif"
    write_dem(path, dem, 30.0)
    water = np.zeros(dem.shape, dtype=bool)
    layers, counts, straight_line = terrain.hand_wp4(path, water, 30.0, {"main": 0.02})
    hand = layers["main"]
    # pysheds leaves the window's border without a flow path; those cells take the straight-line rule.
    assert straight_line["main"][0].all() and straight_line["main"][:, 0].all()
    assert not straight_line["main"][1:-1, 1:-1].any()
    assert counts["main_cells_without_a_flow_path"] == int(straight_line["main"].sum())
    assert hand.dtype == np.float32
    assert np.isfinite(hand).all()  # the border cells get the straight-line rule of work package 4
    assert np.all(hand[:, 20] == 0.0)  # the valley floor is the stream
    assert counts["main_stream_cells"] == dem.shape[0]
    inner = hand[5:-5, 2:-2]
    expected = 2.0 * np.abs(np.arange(2, 39) - 20)[None, :]  # each side cell drains sideways to the floor
    assert np.allclose(inner, np.broadcast_to(expected, inner.shape), atol=1e-4)
    assert (hand >= 0).all()


def test_permanent_water_counts_as_a_stream(tmp_path: Path) -> None:
    pytest.importorskip("pysheds")
    dem = valley()
    path = tmp_path / "valley.tif"
    write_dem(path, dem, 30.0)
    water = np.zeros(dem.shape, dtype=bool)
    water[10:50, 8] = True  # a mapped lake on the western slope
    # A threshold too large for any cell of this window: only the water is a stream.
    layers, counts, _straight_line = terrain.hand_wp4(path, water, 30.0, {"main": 25.0})
    hand = layers["main"]
    assert counts["main_stream_cells"] == int(water.sum())
    assert np.all(hand[water] == 0.0)
    assert (hand[12:48, 1:8] > 0).all()  # the slope west of the lake drains into it


def test_hand_code_is_the_code_of_work_package_4() -> None:
    import inspect

    ours = re.sub(r"\s+", " ", inspect.getsource(terrain.hand_wp4)).lower()
    theirs = re.sub(r"\s+", " ", (ROOT / terrain.WP4_SCRIPT).read_text(encoding="utf-8")).lower()
    for statement in (
        "shed = shedgrid.from_raster(str(dem_path))",
        "raw = shed.read_raster(str(dem_path))",
        "conditioned = shed.resolve_flats(shed.fill_depressions(shed.fill_pits(raw)))",
        "direction = shed.flowdir(conditioned)",
        "accumulation = shed.accumulation(direction)",
        'surface = np.asarray(conditioned, dtype="float32")',
        "stream_raster = accumulation * (cell_m ** 2) / 1e6 >= threshold",
        "stream_raster[water] = true",
        "streams = np.asarray(stream_raster, dtype=bool)",
        'hand = np.asarray(shed.compute_hand(direction, conditioned, stream_raster), dtype="float32")',
        "distance, indices = ndimage.distance_transform_edt(~streams, return_indices=true)",
        "missing = ~np.isfinite(hand)",
        "hand[missing] = surface[missing] - surface[indices[0], indices[1]][missing]",
        "np.clip(hand, 0, none)",
    ):
        assert statement in ours, statement
        assert statement in theirs, statement
    constants = (ROOT / terrain.WP4_SCRIPT).read_text(encoding="utf-8")
    assert re.search(r"^MAIN_STREAM_KM2, SMALL_STREAM_KM2 = 25\.0, 1\.0$", constants, re.M)
    assert re.search(r"^CELL_M = 30\.0$", constants, re.M)
    assert (terrain.MAIN_STREAM_KM2, terrain.SMALL_STREAM_KM2, terrain.HYDRO_CELL_M) == (25.0, 1.0, 30.0)


# ---------------------------------------------------------------------------
# Windows and tiles
# ---------------------------------------------------------------------------


def test_hydrology_window_holds_the_area_with_the_buffer_on_every_side() -> None:
    grid = (639520.0, 2111500.0, 4303, 4280)
    window = terrain.hydrology_grid(grid, 20.0, 10_000.0)
    west, south, east, north = terrain.grid_bounds(grid, 20.0)
    w_west, w_south, w_east, w_north = terrain.grid_bounds(window, 30.0)
    assert w_west % 30 == 0 and w_north % 30 == 0 and w_south % 30 == 0 and w_east % 30 == 0
    assert west - w_west >= 10_000 and w_east - east >= 10_000
    assert w_north - north >= 10_000 and south - w_south >= 10_000
    assert west - w_west < 10_030 and w_north - north < 10_030


def test_tile_names_follow_the_providers() -> None:
    nan = terrain.dem_tiles((100.22, 18.21, 101.24, 19.19))
    assert [name for name, _url in nan] == [
        "Copernicus_DSM_COG_10_N18_00_E100_00_DEM.tif", "Copernicus_DSM_COG_10_N18_00_E101_00_DEM.tif",
        "Copernicus_DSM_COG_10_N19_00_E100_00_DEM.tif", "Copernicus_DSM_COG_10_N19_00_E101_00_DEM.tif"]
    assert nan[0][1] == ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N18_00_E100_00_DEM/"
                         "Copernicus_DSM_COG_10_N18_00_E100_00_DEM.tif")
    cover = [name for name, _url in terrain.worldcover_tiles((101.89, 15.67, 102.18, 15.95))]
    assert cover == ["ESA_WorldCover_10m_2021_v200_N15E099_Map.tif", "ESA_WorldCover_10m_2021_v200_N15E102_Map.tif"]
    jrc = [name for name, _url in terrain.jrc_tiles((99.79, 20.17, 100.11, 20.57))]
    assert jrc == ["occurrence_90E_30Nv1_4_2021.tif", "occurrence_100E_30Nv1_4_2021.tif"]
    assert [name for name, _url in terrain.jrc_tiles((100.31, 18.29, 101.15, 19.10))] == ["occurrence_100E_20Nv1_4_2021.tif"]


def test_the_sealed_folder_is_refused() -> None:
    with pytest.raises(terrain.TerrainError):
        terrain.refuse_sealed(Path("x") / "proposal_execution" / "nan_case_v1" / "jaxa_sealed" / "a.zip")
    assert terrain.refuse_sealed(Path("x") / "terrain" / "a.tif") == Path("x") / "terrain" / "a.tif"


def test_tuning_areas_come_first() -> None:
    areas = {"nan_frame": {}, "chaiyaphum_20210928": {}, "sukhothai_chip": {}, "mae_sai_20241022": {}}
    assert terrain.ordered_areas(areas, None) == ["sukhothai_chip", "mae_sai_20241022", "chaiyaphum_20210928", "nan_frame"]
    assert terrain.ordered_areas(areas, ["nan_frame"]) == ["nan_frame"]
    with pytest.raises(terrain.TerrainError):
        terrain.ordered_areas(areas, ["ubon"])


# ---------------------------------------------------------------------------
# The whole build of one area on an invented world
# ---------------------------------------------------------------------------


GRID = {"west": 660000, "north": 2050020, "rows": 31, "cols": 27}


def invented_world(external: Path, buffer_m: float) -> tuple[float, float]:
    """An invented DEM tile and WorldCover tile around ``GRID``; returns the longitude of the valley floor and the latitude."""

    from rasterio.transform import from_origin

    grid = terrain.area_grid({"grid": GRID})
    window = terrain.hydrology_grid(grid, 20.0, buffer_m)
    box = terrain.lonlat_bounds(terrain.grid_bounds(window, 30.0), margin_deg=terrain.LONLAT_MARGIN_DEG + 0.01)
    centre = terrain.lonlat_bounds(terrain.grid_bounds(grid, 20.0))
    lon0, lat0 = (centre[0] + centre[2]) / 2, (centre[1] + centre[3]) / 2
    metres_per_degree = 111_320.0 * math.cos(math.radians(lat0))

    (name, _url), = terrain.dem_tiles(terrain.lonlat_bounds(terrain.grid_bounds(window, 30.0),
                                                            margin_deg=terrain.LONLAT_MARGIN_DEG))
    step = 1 / 3600
    columns, rows = int((box[2] - box[0]) / step) + 1, int((box[3] - box[1]) / step) + 1
    lon = box[0] + (np.arange(columns) + 0.5) * step
    lat = box[3] - (np.arange(rows) + 0.5) * step
    across = np.abs(lon - lon0)[None, :] * metres_per_degree
    along = (lat - box[1])[:, None] * 111_000.0
    dem = (150.0 + 0.08 * across + 0.004 * along).astype("float32")
    folder = external / "open_context" / "copernicus_dem_glo30"
    folder.mkdir(parents=True)
    with rasterio.open(folder / name, "w", driver="GTiff", height=rows, width=columns, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(box[0], box[3], step, step)) as target:
        target.write(dem, 1)

    (cover_name, _url), = terrain.worldcover_tiles(box)
    step = 1 / 12000
    columns, rows = int((box[2] - box[0]) / step) + 1, int((box[3] - box[1]) / step) + 1
    lon = box[0] + (np.arange(columns) + 0.5) * step
    lat = box[3] - (np.arange(rows) + 0.5) * step
    across = (lon - lon0)[None, :] * metres_per_degree
    cover = np.full((rows, columns), 40, dtype="uint8")
    cover[:, np.abs(across[0]) < 20] = 80  # a river about 40 m wide on the valley floor
    cover[(lat > lat0)[:, None] & (across > 150) & (across < 300)] = 50
    cover[(lat < lat0)[:, None] & (across < -150)] = 10
    folder = external / "open_context" / "esa_worldcover"
    folder.mkdir(parents=True)
    with rasterio.open(folder / cover_name, "w", driver="GTiff", height=rows, width=columns, count=1, dtype="uint8",
                       nodata=0, crs="EPSG:4326", transform=from_origin(box[0], box[3], step, step)) as target:
        target.write(cover, 1)
    return lon0, lat0


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    pytest.importorskip("pysheds")
    external = tmp_path_factory.mktemp("external")
    invented_world(external, 1_200.0)
    provenance = {"protocol": {"path": "invented", "sha256": "0" * 64}}
    record = terrain.build_area(external, "invented_area", {"role": "test", "grid": GRID}, provenance=provenance,
                                buffer_m=1_200.0, check_buffers_m=(600.0,), allow_download=False,
                                main_threshold_km2=0.05, small_threshold_km2=0.01)
    return external, record


LAYERS = {"dem_m.tif": "float32", "slope_deg.tif": "float32", "hand_m.tif": "float32",
          "hand_1km2_context_m.tif": "float32", "worldcover.tif": "uint8", "permanent_water.tif": "uint8",
          "hand_straight_line_rule.tif": "uint8"}


def test_every_output_is_on_the_area_grid_exactly(built: tuple[Path, dict]) -> None:
    from rasterio.transform import from_origin

    external, record = built
    folder = external / record["folder_under_external_root"]
    for name, dtype in LAYERS.items():
        with rasterio.open(folder / name) as source:
            assert source.crs.to_epsg() == 32647, name
            assert (source.height, source.width) == (GRID["rows"], GRID["cols"]), name
            assert source.transform.almost_equals(from_origin(GRID["west"], GRID["north"], 20.0, 20.0)), name
            assert source.dtypes[0] == dtype, name
            assert source.profile["tiled"] and source.profile["compress"] == "deflate", name
            values = source.read(1)
        if dtype == "float32":
            assert np.isfinite(values).all(), name
        terrain.check_alignment(folder / name, terrain.area_grid({"grid": GRID}), 20.0)
        assert record["files"][name]["sha256"] == terrain.sha256_file(folder / name)
    assert record["grid"] == {**record["grid"], "epsg": 32647, "cell_m": 20.0, "west": 660000.0, "north": 2050020.0,
                              "rows": 31, "cols": 27}


def test_layers_agree_with_each_other_and_with_the_invented_world(built: tuple[Path, dict]) -> None:
    external, record = built
    folder = external / record["folder_under_external_root"]
    read = {name: rasterio.open(folder / name).read(1) for name in LAYERS}
    assert np.array_equal(read["permanent_water.tif"], (read["worldcover.tif"] == 80).astype("uint8"))
    assert set(np.unique(read["worldcover.tif"])) <= {10, 40, 50, 80}
    assert set(np.unique(read["hand_straight_line_rule.tif"])) <= {0, 1}
    assert read["permanent_water.tif"].any()
    hand = read["hand_m.tif"]
    water = read["permanent_water.tif"] == 1
    assert (hand >= 0).all()
    assert np.median(hand[water]) < np.median(hand[~water])  # the river is the lowest ground
    assert float(np.median(read["slope_deg.tif"])) == pytest.approx(math.degrees(math.atan(0.08)), abs=0.6)


def test_the_record_carries_the_envelope_the_method_and_the_skipped_context(built: tuple[Path, dict]) -> None:
    external, record = built
    for key in ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions"):
        assert record[key]
    assert record["official_warning"] is False
    assert record["operational_status"] == "non_operational"
    assert record["hand"]["permanent_water_counts_as_stream"] is True
    assert record["hand"]["resampling_to_20m"] == "bilinear"
    assert record["hand"]["hydrology_window"]["buffer_m"] == 1_200.0
    (edge,) = record["hand"]["edge_checks"]
    assert edge["cells_compared"] == GRID["rows"] * GRID["cols"]
    assert edge["other_window"]["buffer_m"] == 600.0
    assert set(edge["share_on_different_sides_of"]) == {"5", "10", "15", "20"}
    jrc = record["sources"]["jrc_global_surface_water_v1_4_occurrence"]
    assert "skipped" in jrc and jrc["missing"]
    assert not (external / record["folder_under_external_root"] / "jrc_occurrence.tif").exists()
    assert record["sources"]["copernicus_dem_glo30"]["tiles"][0]["origin"] == "on disk under open_context"
    path = external / record["folder_under_external_root"] / "terrain_record.json"
    assert b"\r\n" not in path.read_bytes()
    assert json.loads(path.read_text(encoding="utf-8"))["area"] == "invented_area"
    text = path.read_text(encoding="utf-8").lower()
    for word in ("accurate", "validated", "real-time", "forecast"):
        assert word not in text
