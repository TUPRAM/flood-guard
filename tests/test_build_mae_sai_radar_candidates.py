"""End-to-end test of the radar candidate builder on synthetic inputs (no external data).

A scratch folder gets two small SAFE archives, eight unit polygons with the
unit codes of protocol v1a, a land-cover raster, two DEM tiles and a JRC
raster. The builder is run on them with the protocol files and the frozen
M1-v2 of this repository. Nothing here is a real place.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
geopandas = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
pytest.importorskip("scipy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_mae_sai_radar_candidates as builder  # noqa: E402

from floodguard import geoid_m1_review as review  # noqa: E402
from floodguard import radar_candidates as rc  # noqa: E402
from floodguard import sentinel1_sigma0 as s1  # noqa: E402

# One lattice tile of UTM zone 47N: E058N220.
TILE = (593920.0, 2252800.0, 604160.0, 2263040.0)
LON0, LAT0, STEP = 99.88, 20.48, 0.0001
ROWS, COLS = 1300, 1400
GAIN = 500.0
UNIT_IDS = ["TH570901", "TH570902", "TH570903", "TH570904", "TH570905", "TH570906", "TH570908", "TH570909"]
PRE_NAME = "S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_055507_06C5C9_TEST.SAFE"
POST_NAME = "S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_055682_06CCBA_TEST.SAFE"


def _calibration_xml() -> str:
    vectors = "".join(
        f"<calibrationVector><line>{line}</line><pixel count=\"2\">0 {COLS}</pixel>"
        f"<sigmaNought count=\"2\">{GAIN} {GAIN}</sigmaNought></calibrationVector>"
        for line in (0, ROWS)
    )
    return f"<calibration><calibrationVectorList>{vectors}</calibrationVectorList></calibration>"


def _annotation_xml() -> str:
    # The annotation counts samples: line and pixel name the centre of a sample. The control points of the
    # GeoTIFF use the same numbers for its corner, as in a real product, which is half a cell away.
    points = "".join(
        f"<geolocationGridPoint><line>{line}</line><pixel>{pixel}</pixel>"
        f"<latitude>{LAT0 - (line + 0.5) * STEP!r}</latitude>"
        f"<longitude>{LON0 + (pixel + 0.5) * STEP!r}</longitude>"
        "<height>400.0</height><incidenceAngle>37.0</incidenceAngle></geolocationGridPoint>"
        for line in (0, ROWS // 2, ROWS)
        for pixel in (0, COLS // 2, COLS)
    )
    return (
        "<product><imageAnnotation><imageInformation><rangePixelSpacing>1.0e+01</rangePixelSpacing>"
        "<azimuthPixelSpacing>1.0e+01</azimuthPixelSpacing></imageInformation></imageAnnotation>"
        "<productInformation><projection>Ground Range</projection></productInformation>"
        f"<geolocationGrid><geolocationGridPointList>{points}</geolocationGridPointList></geolocationGrid>"
        "</product>"
    )


def _manifest(start: str, stop: str) -> str:
    return (
        '<xfdu:XFDU xmlns:safe="x" xmlns:s1="y">'
        f"<safe:startTime>{start}</safe:startTime><safe:stopTime>{stop}</safe:stopTime>"
        '<safe:relativeOrbitNumber type="start">135</safe:relativeOrbitNumber><s1:pass>DESCENDING</s1:pass>'
        '<safe:software name="Sentinel-1 IPF" version="003.80"/></xfdu:XFDU>'
    )


def _write_safe(folder: Path, product: str, sigma0: dict[str, np.ndarray], start: str, stop: str) -> Path:
    from rasterio.control import GroundControlPoint

    gcps = [
        GroundControlPoint(row=row, col=col, x=LON0 + col * STEP, y=LAT0 - row * STEP, z=400.0)
        for row in (0, ROWS // 2, ROWS)
        for col in (0, COLS // 2, COLS)
    ]
    archive = folder / f"{product}.zip"
    stamp = product[17:32].lower()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for number, pol in ((1, "vv"), (2, "vh")):
            stem = f"s1a-iw-grd-{pol}-{stamp}-00{number}"
            tiff = folder / f"{product}-{stem}.tiff"
            with rasterio.open(
                tiff, "w", driver="GTiff", width=COLS, height=ROWS, count=1, dtype="uint16", gcps=gcps,
                crs="EPSG:4326",
            ) as target:
                target.write(np.clip(np.round(np.sqrt(sigma0[pol]) * GAIN), 1, 65535).astype("uint16"), 1)
            bundle.write(tiff, f"{product}/measurement/{stem}.tiff")
            tiff.unlink()
            bundle.writestr(f"{product}/annotation/calibration/calibration-{stem}.xml", _calibration_xml())
            bundle.writestr(f"{product}/annotation/{stem}.xml", _annotation_xml())
        bundle.writestr(f"{product}/manifest.safe", _manifest(start, stop))
    return archive


def _geotiff(path: Path, array: np.ndarray, west: float, north: float, step: float) -> Path:
    from rasterio.transform import from_origin

    with rasterio.open(
        path, "w", driver="GTiff", width=array.shape[1], height=array.shape[0], count=1, dtype=str(array.dtype),
        crs="EPSG:4326", transform=from_origin(west, north, step, step),
    ) as target:
        target.write(array, 1)
    return path


@pytest.fixture(scope="module")
def inputs(tmp_path_factory: pytest.TempPathFactory) -> builder.BuildInputs:
    from pyproj import Transformer
    from shapely.geometry import box
    from shapely.ops import transform

    folder = tmp_path_factory.mktemp("radar_inputs")
    rng = np.random.default_rng(42)
    rows, cols = np.mgrid[0:ROWS, 0:COLS]
    water = (rows > 900) & (rows < 990) & (cols > 300) & (cols < 420)  # A pond: dark on both dates.
    flooded = (rows > 420) & (rows < 620) & (cols > 520) & (cols < 820)  # Darkens by 8 dB after the event.

    def speckle(mean: np.ndarray) -> np.ndarray:
        return mean * rng.gamma(4.4, 1.0 / 4.4, size=mean.shape)

    base = {"vv": np.where(water, 0.006, 0.1), "vh": np.where(water, 0.0015, 0.025)}
    factor = np.where(flooded, 10.0 ** -0.8, 1.0)
    pre = _write_safe(folder, PRE_NAME, {pol: speckle(base[pol]) for pol in base},
                      "2024-09-03T23:16:00.776136", "2024-09-03T23:16:25.773465")
    post = _write_safe(folder, POST_NAME, {pol: speckle(base[pol] * factor) for pol in base},
                       "2024-09-15T23:16:01.675690", "2024-09-15T23:16:26.674888")

    # Eight unit polygons: a two by four block of rectangles inside the tile.
    to_geographic = Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True).transform
    west, south = TILE[0] + 1500.0, TILE[1] + 1500.0
    polygons = [
        transform(to_geographic, box(west + column * 1750.0, south + row * 3500.0,
                                     west + (column + 1) * 1750.0, south + (row + 1) * 3500.0))
        for row in range(2) for column in range(4)
    ]
    boundaries = folder / "boundaries.gpkg"
    geopandas.GeoDataFrame(
        {"adm3_pcode": UNIT_IDS, "adm3_name": [f"Unit {index}" for index in range(1, 9)]},
        geometry=polygons, crs="EPSG:4326",
    ).to_file(boundaries, layer="tha_admin3", driver="GPKG")

    cover = np.full((1400, 1500), 40, dtype="uint8")
    cover[:, :300] = 10
    cover[:ROWS, :COLS][water] = 80
    worldcover = _geotiff(folder / "worldcover.tif", cover, LON0, LAT0, STEP)

    arcsec = 1.0 / 3600.0
    dem_rows, dem_cols = int(0.2 / arcsec), int(0.11 / arcsec)
    hill = np.full((dem_rows, dem_cols), 400.0, dtype="float32")
    hill[:, :40] += np.linspace(600.0, 0.0, 40, dtype="float32")[None, :]  # A steep western edge.
    dem_west = _geotiff(folder / "dem_west.tif", hill, 99.84, 20.56, arcsec)
    dem_east = _geotiff(folder / "dem_east.tif", np.full((dem_rows, dem_cols), 400.0, dtype="float32"),
                        99.84 + dem_cols * arcsec, 20.56, arcsec)

    seasonality = np.zeros((560, 400), dtype="uint8")
    jrc_water = _geotiff(folder / "jrc.tif", seasonality, LON0, LAT0, 0.00025)  # Ends at 99.98 E.

    return builder.BuildInputs(
        pre_safe=pre, post_safe=post, boundaries=boundaries, worldcover=worldcover,
        dem_tiles=(dem_west, dem_east), jrc_seasonality=jrc_water, acquisition_manifest=None,
        raster_dir=folder / "rasters",
        labels={**{key: builder.external_label(f"synthetic/{key}") for key in builder.INPUT_FILES},
                "raster_dir": builder.external_label("synthetic/rasters")},
    )


@pytest.fixture(scope="module")
def run(inputs: builder.BuildInputs, tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    output = tmp_path_factory.mktemp("radar_outputs")
    built: dict[str, object] = {}
    original = builder.build

    def remembering(*args: object, **kwargs: object) -> object:
        built["result"] = original(*args, **kwargs)
        return built["result"]

    builder.build = remembering  # Kept for the replacement test, which then does not compute a second time.
    try:
        summary = builder.run(inputs, output, notes=["synthetic test run"])
    finally:
        builder.build = original
    table = json.loads((output / builder.TABLE_NAME).read_bytes().decode("ascii"))
    receipt = json.loads((output / builder.RECEIPT_NAME).read_bytes().decode("ascii"))
    return {"output": output, "summary": summary, "table": table, "receipt": receipt, "built": built["result"]}


def test_the_run_writes_a_table_and_a_receipt_that_say_what_they_are(run: dict[str, object]) -> None:
    table, receipt = run["table"], run["receipt"]
    for document in (table, receipt):
        assert document["official_warning"] is False and document["operational_status"] == "non_operational"
        assert document["confidence_class"] == "low" and document["confidence_basis"].strip()
        assert document["source_timestamp"] == "2024-09-15T23:16:01Z"
        assert document["assumptions"] and all(line.strip() for line in document["assumptions"])
        assert set(document["protocol_sha256"]) == {"planning_protocol_v1a", "planning_protocol_v1b"}
        assert "No FPPS" in document["computes"]
        assert "FPPS" in document["not_computed"] and "A-E class" in document["not_computed"]
    raw = (run["output"] / builder.TABLE_NAME).read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert table["schema_version"] == builder.TABLE_SCHEMA and receipt["status"] == "run_receipt"
    assert table["case"] == {
        "id": "O1", "lane": "OBS", "tier": "T2", "frame": "Mae Sai, 8 tambons",
        "case_reference_date": "2024-09-15",
        "input_acquisition_in_protocol_v1a": "Sentinel-1, 16 Sep 2024 06:16 ICT",
    }
    assert table["source_timestamps"]["post_event_image_in_thailand"] == "2024-09-16 06:16 ICT"
    assert table["geocoding"]["label"] == "approximate geocoding: GCP affine, no DEM terrain correction"
    assert table["geocoding"]["method"] == "gcp_polynomial" and table["geocoding"]["height_datum_reading"] is None
    assert table["run_role"] == receipt["run_role"] == "run_of_record_plan_fallback"
    assert table["t2_skill_bar"]["evaluation_of_record"] is True
    assert [unit["unit_id"] for unit in table["units"]] == UNIT_IDS
    assert receipt["operator_notes"] == ["synthetic test run"]
    assert receipt["timestamps"]["run_started_at_utc"] <= receipt["generated_at_utc"]
    text = json.dumps(table) + json.dumps(receipt)
    assert str(run["output"]) not in text and "fg-tmp" not in text  # No local path is written.


def test_the_receipt_binds_inputs_outputs_and_the_frozen_method(
    run: dict[str, object], inputs: builder.BuildInputs
) -> None:
    receipt = run["receipt"]
    table_bytes = (run["output"] / builder.TABLE_NAME).read_bytes()
    assert receipt["outputs"]["table"]["sha256"] == builder.hashlib.sha256(table_bytes).hexdigest()
    names = {Path(item["path"]).name for item in receipt["outputs"]["rasters"]}
    assert names == {
        "frame_units.tif", "context_worldcover_2021.tif", "context_slope_degrees.tif",
        "sigma0_pre_20240903.tif", "sigma0_post_20240915.tif",
        *(f"{method}_{layer}.tif" for method in rc.METHODS for layer in ("candidate", "reason", "score")),
        "m1_literal_threshold_levels.tif", "m1_v2_threshold_levels.tif",
    }
    for item in receipt["outputs"]["rasters"]:
        assert item["path"].startswith("<external_data_workspace>/") and item["kept_outside_git"] is True
        assert builder.sha256_file(inputs.raster_dir / Path(item["path"]).name) == item["sha256"]
    assert receipt["inputs"]["pre_event_safe"]["sha256"] == builder.sha256_file(inputs.pre_safe)
    assert receipt["inputs"]["post_event_safe"]["bytes"] == inputs.post_safe.stat().st_size
    binding = review.require_frozen_m1_v2(ROOT)
    assert receipt["m1_v2_frozen_binding"]["frozen_config_sha256"] == binding["frozen_config_sha256"]
    assert receipt["m1_v2_frozen_binding"]["code_sha256"] == binding["code_sha256"]
    assert receipt["parameters"]["m1_v2"] == binding["parameters"]
    assert receipt["parameters"]["un_spider"]["difference_threshold"] == 1.25
    assert receipt["parameters"]["grid"]["tiles_holding_part_of_the_frame"] == ["E058N220"]
    assert receipt["parameters"]["geocoding_label"] == s1.PLAN_FALLBACK_LABEL


def test_every_method_finds_the_darkened_block_and_counts_it_per_unit(run: dict[str, object]) -> None:
    table = run["table"]
    assert set(table["methods"]) == set(rc.METHODS)
    # The darkened block is about 200 by 300 image cells of 11.1 m by 10.4 m: near 6.9 km2 on the ground,
    # of which the part inside the eight units is counted.
    areas = {name: method["frame"]["candidate_area_km2"] for name, method in table["methods"].items()}
    assert 3.0 < areas["m1_v2"] < 7.5 and 3.0 < areas["un_spider"] < 7.5
    assert areas["m1_literal"] >= areas["m1_v2"] * 0.8
    for name, method in table["methods"].items():
        frame, rows = method["frame"], method["units"]
        assert method["flood_input"] == rc.FLOOD_INPUT_NAMES[name] and method["tier"] == "T2"
        assert method["label"].endswith("(approximate geocoding: GCP affine, no DEM terrain correction)")
        assert method["display"] == "Own model candidate: verify before action"
        assert [row["unit_id"] for row in rows] == UNIT_IDS
        assert frame["cells"] == sum(row["cells"] for row in rows) == sum(unit["cells"] for unit in table["units"])
        assert frame["candidate_cells"] == sum(row["candidate_cells"] for row in rows)
        assert frame["candidate_area_km2"] == pytest.approx(frame["candidate_cells"] * 1e-4)
        for row in rows:
            assert row["answer_coverage"] + row["abstention_fraction"] == pytest.approx(1.0, abs=1e-6)
            assert row["input_coverage"] == 1.0 and row["abstention_fraction"] == 0.0
            assert row["low_confidence_reason_codes"] == []
        strata = method["strata"]["by_land_cover_worldcover_2021"]
        assert sum(row["frame_cells"] for row in strata) == frame["cells"]
        assert sum(row["candidate_cells"] for row in strata) == frame["candidate_cells"]
        slopes = method["strata"]["by_slope_class"]
        assert sum(row["candidate_cells"] for row in slopes) == frame["candidate_cells"]
    assert table["methods"]["un_spider"]["statement"] == (
        f"Reproduces UN-SPIDER practice; {areas['un_spider']:.2f} km2 of residual water at 16 Sep 06:16 ICT; "
        "the published 93.38% OA does not transfer"
    )
    assert table["methods"]["m1_v2"]["tiles_declined"] == []
    assert "not a cell that was seen under water" in table["methods"]["un_spider"]["area_note"]
    levels = table["methods"]["m1_v2"]["threshold_levels"]["frame_km2"]
    assert levels["strictest"] <= levels["central"] <= levels["loosest"]
    assert levels["central"] == areas["m1_v2"]
    tile = table["methods"]["m1_v2"]["tiles"][0]
    assert tile["tile"] == "E058N220" and tile["whole_tile"]["abstained"] is False
    assert tile["declined"] is False and tile["declined_because"] is None
    assert tile["frame_cells_by_unit"] == {unit["unit_id"]: unit["cells"] for unit in table["units"]}
    assert tile["whole_tile"]["sides"]["darkening"]["threshold_db"] > 0
    assert "jrc_sensitivity_note" in table["methods"]["un_spider"]
    assert 0 < table["methods"]["un_spider"]["jrc_sensitivity_note"]["share_of_frame_covered_by_the_jrc_tile"] <= 1


def test_the_t2_skill_bar_is_evaluated_with_the_signed_rule(run: dict[str, object]) -> None:
    skill = run["table"]["t2_skill_bar"]
    assert skill["thresholds"] == {
        "geoid_held_out_test_iou_min": 0.4, "mae_sai_abstention_fraction_max": 0.2,
        "mae_sai_unit_coverage_min": 0.8, "recency_window_days": 3.0,
    }
    assert skill["recency"]["acquisition_date_in_thailand"] == "2024-09-16"
    assert skill["recency"]["days_by_the_thai_date"] == 1 and skill["recency"]["days_by_the_utc_date"] == 0
    assert skill["recency"]["passes"] is True
    geoid = skill["geoid_condition"]
    assert geoid["m1_v2_test_iou_strict"] == 0.411164 and geoid["m1_v2_test_cells_without_an_answer"] == 0.678737
    assert geoid["holds_for_every_tile_left_out"] is False
    assert geoid["said_beside_the_result_every_time"] == builder.R15_CAVEATS
    assert skill["methods"]["m1_literal"]["status_in_protocol_v1a"] == "declared_unable_to_meet"
    assert skill["methods"]["un_spider"]["status_in_protocol_v1a"] == "declared_unable_to_meet"
    assert "declared unable" in skill["methods"]["m1_literal"]["result"]
    v2 = skill["methods"]["m1_v2"]
    assert v2["status_in_protocol_v1a"] == "evaluated" and v2["geoid_held_out_test_iou_used"] == 0.411164
    # On the synthetic tile the frozen method answers everywhere, so the Mae Sai conditions pass there.
    assert v2["units_passing_all_four_conditions"]["answer_coverage"] == UNIT_IDS
    assert "meets the three Mae Sai conditions in every tambon" in v2["result"]
    assert v2["units"][0]["coverage_reading"]["input_coverage"]["conditions"] == {
        "geoid_held_out_test_iou_min": "pass", "mae_sai_abstention_fraction_max": "pass",
        "mae_sai_unit_coverage_min": "pass", "recency_window_days": "pass",
    }
    # The declared-unable methods never pass, whatever their numbers.
    assert skill["methods"]["m1_literal"]["units_passing_all_four_conditions"]["answer_coverage"] == []


def test_the_displacement_check_finds_none_on_an_exact_geometry(run: dict[str, object]) -> None:
    check = run["table"]["geolocation_check"]
    record = check["control_point_warp"]
    assert (record["whole_grid"]["east_m"], record["whole_grid"]["north_m"]) == (0.0, 0.0)
    assert record["tiles"]["E058N220"]["measured"] is True
    assert check["pre_against_post"]["east_m"] == 0.0 and check["pre_against_post"]["north_m"] == 0.0
    same = check["height_aware_mapping"]["readings"]["annotation_heights_and_dem_share_one_datum"]
    assert (same["whole_grid"]["east_m"], same["whole_grid"]["north_m"]) == (0.0, 0.0)
    expected = check["expected_from_geometry"]["readings"]["annotation_heights_and_dem_share_one_datum"]
    assert abs(expected["frame"]["along_range_m"]["median"]) < 1.0
    assert abs(expected["frame"]["along_azimuth_m"]["median"]) < 1.0
    other = check["expected_from_geometry"]["readings"]["annotation_heights_are_ellipsoidal_and_dem_is_above_the_geoid"]
    # Cells 35 m lower than the control points lie 35 / tan(37 degrees) = 46 m from them along the range. The
    # synthetic samples are 10.4 m wide and the figure counts them as 10 m, as the annotation states.
    assert abs(abs(other["frame"]["along_range_m"]["median"]) - 35.0 / np.tan(np.radians(37.0))) < 3.0
    assert "Not the plan's fallback path" in check["height_aware_mapping"]["status"]


def test_rasters_carry_their_provenance(run: dict[str, object], inputs: builder.BuildInputs) -> None:
    with rasterio.open(inputs.raster_dir / "m1_v2_candidate.tif") as source:
        tags = source.tags()
        codes = np.unique(source.read(1))
        assert source.crs.to_epsg() == 32647 and source.res == (10.0, 10.0)
        assert (source.width, source.height) == (1024, 1024) and source.nodata == 255
        assert tuple(source.bounds) == TILE
    assert set(codes.tolist()) <= {0, 1, 255}
    assert tags["source_timestamp"] == "2024-09-15T23:16:01Z" and tags["official_warning"] == "false"
    assert tags["geocoding"] == s1.PLAN_FALLBACK_LABEL and "verify before action" in tags["evidence"]
    assert tags["planning_protocol_v1a_sha256"] == run["table"]["protocol_sha256"]["planning_protocol_v1a"]
    assert tags["assumptions"].strip() and tags["confidence"].startswith("low")
    with rasterio.open(inputs.raster_dir / "frame_units.tif") as source:
        units = source.read(1)
    with rasterio.open(inputs.raster_dir / "m1_v2_reason.tif") as source:
        reason = source.read(1)
    assert set(np.unique(units).tolist()) == set(range(9))
    assert ((reason == rc.REASON_OUTSIDE_FRAME) == (units == 0)).all()
    with rasterio.open(inputs.raster_dir / "sigma0_post_20240915.tif") as source:
        assert source.count == 2 and source.descriptions == ("VV linear sigma0", "VH linear sigma0")
        assert 0.05 < float(np.nanmedian(source.read(1))) < 0.15  # Sigma0, not the digital number.


def test_a_second_run_needs_a_reason_and_names_what_it_replaces(
    run: dict[str, object], inputs: builder.BuildInputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = run["output"]
    monkeypatch.setattr(builder, "build", lambda *args, **kwargs: copy.deepcopy(run["built"]))
    with pytest.raises(FileExistsError):
        builder.run(inputs, output)
    with pytest.raises(FileNotFoundError):
        builder.run(inputs, output / "elsewhere", replace_reason="no table there")
    first_receipt = builder.sha256_file(output / builder.RECEIPT_NAME)
    first_table = builder.sha256_file(output / builder.TABLE_NAME)
    stamp = run["table"]["generated_at_utc"].replace(":", "").replace("-", "")
    summary = builder.run(inputs, output, replace_reason="repeat for the test", register_dir=output / "register")
    receipt = json.loads((output / builder.RECEIPT_NAME).read_text(encoding="ascii"))
    assert receipt["supersedes"]["table_sha256"] == first_table
    assert receipt["supersedes"]["receipt_sha256"] == first_receipt
    assert receipt["supersedes"]["reason"] == "repeat for the test"
    assert receipt["supersedes"]["same_frame_and_unit_figures"] is True
    # The superseded files are copied outside Git under the time of the run they belong to.
    archive = inputs.raster_dir.parent / builder.SUPERSEDED_FOLDER.name
    assert builder.sha256_file(archive / f"{stamp}_{builder.TABLE_NAME}") == first_table
    assert builder.sha256_file(archive / f"{stamp}_{builder.RECEIPT_NAME}") == first_receipt
    assert receipt["supersedes"]["copies_kept_outside_git"] == [
        f"<external_data_workspace>/synthetic/radar_o1_superseded_runs/{stamp}_{builder.TABLE_NAME}",
        f"<external_data_workspace>/synthetic/radar_o1_superseded_runs/{stamp}_{builder.RECEIPT_NAME}",
    ]
    # The run registers its table and its receipt: one small file each, with the bytes as written.
    assert summary["registered"] == [f"a2_a4_{builder.TABLE_NAME}", f"a2_a4_{builder.RECEIPT_NAME}"]
    for name in (builder.TABLE_NAME, builder.RECEIPT_NAME):
        raw = (output / "register" / f"a2_a4_{name}").read_bytes()
        assert raw.endswith(b"\n") and b"\r" not in raw
        assert json.loads(raw.decode("ascii")) == {"path": name, "sha256": builder.sha256_file(output / name)}


def test_the_sensitivity_run_has_its_own_files_and_replaces_nothing(
    run: dict[str, object], inputs: builder.BuildInputs, tmp_path: Path
) -> None:
    output = run["output"]
    record_table = builder.sha256_file(output / builder.TABLE_NAME)
    record_receipt = builder.sha256_file(output / builder.RECEIPT_NAME)
    names = builder.GEOCODINGS[s1.GEOCODING_HEIGHT_AWARE]
    assert names["table"] != builder.TABLE_NAME and names["receipt"] != builder.RECEIPT_NAME
    assert names["raster_folder"] != builder.GEOCODINGS[s1.GEOCODING_GCP_POLYNOMIAL]["raster_folder"]
    sensitivity_inputs = builder.BuildInputs(**{**inputs.__dict__, "raster_dir": tmp_path / "sensitivity_rasters"})
    builder.run(sensitivity_inputs, output, geocoding=s1.GEOCODING_HEIGHT_AWARE)
    assert builder.sha256_file(output / builder.TABLE_NAME) == record_table
    assert builder.sha256_file(output / builder.RECEIPT_NAME) == record_receipt
    table = json.loads((output / names["table"]).read_text(encoding="ascii"))
    receipt = json.loads((output / names["receipt"]).read_text(encoding="ascii"))
    assert table["run_role"] == receipt["run_role"] == "sensitivity_run_not_in_the_plan"
    assert "replaces nothing" in table["run_role_note"]
    assert table["geocoding"]["method"] == "annotation_grid_with_cell_height"
    assert table["geocoding"]["label"].startswith("sensitivity geocoding, not in the plan")
    assert table["geocoding"]["height_datum_reading"] == builder.HEIGHT_AWARE_DATUM_READING
    assert table["t2_skill_bar"]["evaluation_of_record"] is False
    assert "Not the evaluation of record" in table["t2_skill_bar"]["evaluation_note"]
    assert "Not a flood input of case O1 unless the owners decide so" in table["o1_flood_input_interface"]["use_restriction"]
    assert receipt["run_of_record"] == {
        "table": builder.TABLE_NAME, "receipt": builder.RECEIPT_NAME, "table_sha256": record_table,
        "receipt_sha256": record_receipt,
        "note": "This sensitivity run replaces nothing. The run of record is the fallback of plan row A4.",
    }
    for method in table["methods"].values():
        assert method["label"].endswith("(sensitivity geocoding, not in the plan: annotation grid with a DEM "
                                        "height for every cell)")
    # The synthetic DEM is 35 m above the heights of the annotation grid once the datum reading is applied, so
    # the block moves by about 46 m; its area stays.
    record = run["table"]["methods"]["m1_v2"]["frame"]["candidate_area_km2"]
    assert table["methods"]["m1_v2"]["frame"]["candidate_area_km2"] == pytest.approx(record, rel=0.05)
    with rasterio.open(sensitivity_inputs.raster_dir / "m1_v2_candidate.tif") as source:
        assert source.tags()["run_role"] == "sensitivity_run_not_in_the_plan"
    with pytest.raises(ValueError, match="unknown geocoding"):
        builder.run(inputs, output, geocoding="snap_terrain_correction")


def test_the_builder_refuses_a_changed_frozen_method_and_a_frame_it_does_not_know(
    inputs: builder.BuildInputs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def changed(root: Path) -> dict[str, object]:
        raise review.GeoidReviewError("Code changed after the freeze: src/floodguard/sar_change_v2.py")

    monkeypatch.setattr(builder.review, "require_frozen_m1_v2", changed)
    with pytest.raises(ValueError, match="frozen M1-v2 is not intact"):
        builder.build(inputs)
    monkeypatch.undo()
    missing = geopandas.read_file(inputs.boundaries, layer="tha_admin3").iloc[:7]
    short = tmp_path / "short.gpkg"
    missing.to_file(short, layer="tha_admin3", driver="GPKG")
    broken = builder.BuildInputs(**{**inputs.__dict__, "boundaries": short})
    with pytest.raises(ValueError, match="exactly the units of the frame"):
        builder.build(broken)


def test_file_names_and_reasons_for_a_declined_tile() -> None:
    # tests/test_planning_v1_outputs.py reserves the word "candidate" in a file name for the E0 corridor files.
    for names in builder.GEOCODINGS.values():
        assert "candidate" not in names["table"] and "candidate" not in names["receipt"]
    assert builder.declined_because({"abstained": False}) is None
    assert builder.declined_because({"abstained": True}) == "no Otsu threshold"
    assert builder.declined_because(
        {"abstained": True, "sides": {"darkening": {"selected_blocks": 0}}}) == "no bimodal block in the tile"
    assert "no threshold that the frozen rule accepts" in builder.declined_because(
        {"abstained": True, "sides": {"darkening": {"selected_blocks": 33}}})


def test_the_skill_sentence_says_frame_and_tambons_apart() -> None:
    rule = builder.confidence.load_confidence_rule(
        builder.DOCS / "planning_protocol_v1a.json", builder.DOCS / "RECEIPTS.jsonl")

    def entry(passing: list[str], frame_share: float, status: str = "evaluated") -> dict[str, object]:
        return {
            "status_in_protocol_v1a": status,
            "mae_sai_conditions": {
                "abstention": {"units_at_most_max": len(passing), "units": 8,
                               "frame_abstention_fraction": frame_share, "frame_at_most_max": frame_share <= 0.2,
                               "passes_for_every_unit": len(passing) == 8},
                "coverage": {"units_with_input_coverage_at_least_min": 8,
                             "units_with_answer_coverage_at_least_min": len(passing), "units": 8,
                             "passes_for_every_unit_by_input_coverage": True,
                             "passes_for_every_unit_by_answer_coverage": len(passing) == 8},
                "recency_passes": True,
            },
            "units_passing_all_four_conditions": {"input_coverage": passing, "answer_coverage": passing},
        }

    mixed = builder.skill_sentence("m1_v2", entry(["TH570908"], 0.7726), rule)
    assert mixed.startswith("M1-v2 does not meet the Mae Sai conditions for the frame, nor in 7 of 8 tambons")
    assert "0.773 of the cells have no answer, above the maximum of 0.2" in mixed
    assert "pass in 1 of 8 (TH570908)" in mixed and "open point A4-OP3" in mixed
    none = builder.skill_sentence("m1_v2", entry([], 0.9), rule)
    assert "does not meet the Mae Sai conditions in any tambon" in none and "above the maximum" in none
    partly = builder.skill_sentence("m1_v2", entry(["A", "B", "C", "D", "E", "F", "G"], 0.1), rule)
    assert "does not meet the Mae Sai conditions in 1 of 8 tambons" in partly and "within the maximum" in partly
    every = builder.skill_sentence("m1_v2", entry(list("ABCDEFGH"), 0.0), rule)
    assert "in every tambon and for the frame" in every
    unable = builder.skill_sentence("m1_literal", entry(list("ABCDEFGH"), 0.0, "declared_unable_to_meet"), rule)
    assert unable.startswith("M1-literal is declared unable to meet the T2 skill bar")


def test_the_builder_reads_its_locations_from_arguments_only() -> None:
    source = (ROOT / "scripts" / "build_mae_sai_radar_candidates.py").read_text(encoding="utf-8")
    assert "C:/" not in source and "C:\\" not in source and "Users" not in source
    assert builder.EXTERNAL_DATA_VARIABLE == "FLOODGUARD_EXTERNAL_DATA"
    with pytest.raises(SystemExit):
        builder.main(["--replace"])
