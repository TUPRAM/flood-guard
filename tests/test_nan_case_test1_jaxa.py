"""Test 1 of record of the Nan case (amendment 2), on invented data only.

The reading of JAXA's two layers from a sealed zip held in memory, the refusal of a missing or doubled layer and of an
observation area that covers less than half of the frame's land, the compared cells, and the run of
``scripts/nan_case_test1_jaxa.py`` on an invented world in a throwaway git repository with a throwaway remote,
including its refusals. No real JAXA file, radar pass or reference is read.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
import zipfile

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nan_case_test1_jaxa.py"
RULES = ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json"


def load_script() -> Any:
    """Load the script as a module, without running it."""

    spec = importlib.util.spec_from_file_location("nan_case_test1_jaxa_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


t1 = load_script()

# ---------------------------------------------------------------------------------------------------------------------
# The invented world: 120 by 120 cells of 20 m from x 600,000 and y 2,000,000 (EPSG:32647)
# ---------------------------------------------------------------------------------------------------------------------

FRAME = {"west": 600000.0, "north": 2000000.0, "rows": 120, "cols": 120}
GRID = (FRAME["west"], FRAME["north"], FRAME["rows"], FRAME["cols"])
DRY_HILLS = {"west": 600202.0, "south": 1997802.0, "east": 600602.0, "north": 1998178.0}
UNITS = (slice(5, 115), slice(5, 108))           # the one unit of district TH5501
RIVER = (slice(0, 120), slice(60, 62))           # WorldCover class 80: never compared
HILLS = (slice(90, 112), slice(5, 35))           # answered by terrain
BUILT = (slice(40, 45), slice(40, 45))           # built-up at low HAND: no answer
FLOOD = (slice(62, 76), slice(72, 88))           # water on 2025-07-28, half inside REGION
FLOOD_OUTSIDE_REGION = (slice(100, 104), slice(100, 104))
STRIP = (slice(20, 30), slice(20, 50))           # flagged only without the 0.79 dB offset
FLOOD_0719 = (slice(62, 66), slice(72, 76))
REGION_0728 = (slice(0, 120), slice(0, 80))
WHOLE = (slice(0, 120), slice(0, 120))
SELECTED = {"z_vh_max": -1.0, "vh_after_max_db": -18.0, "hand_max_m": 5.0, "dry_spread_max_db": None}
LEVELS = {"lower": {**SELECTED, "z_vh_max": -1.5}, "central": SELECTED, "upper": {**SELECTED, "z_vh_max": -0.5}}
MAIN_MAP = "m1z_20250728T1120_o99_S1C.tif"
CASE = Path("proposal_execution") / "nan_case_v1"

LAND_INSIDE_REGION = 110 * (75 - 2)              # unit rows 5-114, columns 5-79 without the two river columns
FRAME_LAND = 110 * (103 - 2)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def box_of(rows: slice, cols: slice) -> Any:
    from shapely.geometry import box

    west, north = FRAME["west"], FRAME["north"]
    return box(west + cols.start * 20, north - rows.stop * 20, west + cols.stop * 20, north - rows.start * 20)


def geojson(geometries: list[Any]) -> bytes:
    """GeoJSON text (longitude and latitude, no crs member) of invented geometries given in EPSG:32647."""

    gpd = pytest.importorskip("geopandas")
    frame = gpd.GeoDataFrame({"polygon": list(range(1, len(geometries) + 1))}, geometry=list(geometries), crs="EPSG:32647").to_crs(4326)
    return frame.to_json().encode("utf-8")


def jaxa_zip(path: Path, date: str, stamp: str, layers: dict[str, list[Any]], extra: dict[str, bytes] | None = None) -> str:
    """A zip laid out as JAXA's Flood Proxy Map zips are (one folder, layers named ..._<stamp>_<KIND>.geojson); its SHA-256."""

    folder = f"JAXA_{date}_FPM_ALOS2_Thailand_geojson"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for suffix, geometries in layers.items():
            archive.writestr(f"{folder}/2025-00032-WLD_{stamp}{suffix}", geojson(geometries))
        for name, raw in (extra or {}).items():
            archive.writestr(f"{folder}/{name}", raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())
    return sha(path)


def write_tif(path: Path, bands: list[np.ndarray], *, names: list[str] | None = None, nodata: float | None = None) -> None:
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=FRAME["rows"], width=FRAME["cols"], count=len(bands), dtype=bands[0].dtype,
                       nodata=nodata, crs="EPSG:32647", transform=from_origin(FRAME["west"], FRAME["north"], 20.0, 20.0)) as target:
        for index, band in enumerate(bands, start=1):
            target.write(band, index)
            if names:
                target.set_band_description(index, names[index - 1])


def write_pass(radar: Path, key: str, time_utc: str, orbit: int, platform: str, after_db: np.ndarray) -> None:
    vh = np.power(10.0, after_db / 10.0).astype("float32")
    write_tif(radar / f"event_{key}.tif", [(vh * 4).astype("float32"), vh], names=["VV", "VH"], nodata=float("nan"))
    (radar / f"event_{key}.json").write_text(json.dumps({"datetime": time_utc, "relative_orbit": orbit, "platform": platform}) + "\n", encoding="utf-8")


def write_dry(radar: Path, orbit: int, mean: np.ndarray) -> None:
    one = np.ones_like(mean)
    write_tif(radar / f"dry_o{orbit}.tif", [mean, one, mean + 6, one, np.full_like(mean, 8.0)],
              names=["vh_mean_db", "vh_std_db", "vv_mean_db", "vv_std_db", "n_valid"], nodata=float("nan"))


def git(repo: Path, *args: str) -> str:
    env = {key: value for key, value in os.environ.items() if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=1) + "\n").encode("utf-8"))


def main_layers(region: tuple[slice, slice] = REGION_0728) -> dict[str, list[Any]]:
    from shapely.geometry import MultiPolygon

    return {"_FLDEXT.geojson": [MultiPolygon([box_of(*FLOOD), box_of(*FLOOD_OUTSIDE_REGION)])], "_REGION.geojson": [box_of(*region)]}


def build_world(tmp_path: Path, *, main: dict[str, list[Any]] | None = None, second: dict[str, list[Any]] | None = None) -> SimpleNamespace:
    """A throwaway repository (frozen code, invented protocol, freeze and first test record, both amendments) and an
    invented external root (two Nan passes, their dry seasons, terrain, units and the two sealed JAXA zips)."""

    pytest.importorskip("rasterio")
    gpd = pytest.importorskip("geopandas")
    pytest.importorskip("pyogrio")
    if shutil.which("git") is None:  # pragma: no cover - git is part of the development setup
        pytest.skip("git is needed for the order checks")
    repo, external, remote = tmp_path / "repo", tmp_path / "external", tmp_path / "remote.git"
    for relative in ("src/floodguard/m1z.py", "scripts/nan_case_method.py", "scripts/nan_case_test1_jaxa.py",
                     "docs/proposal_execution/nan_case_protocol_v1_amendment_1.json", "docs/proposal_execution/nan_case_protocol_v1_amendment_2.json"):
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, repo / relative)
    (repo / ".gitattributes").write_text("* text=auto eol=lf\n*.tif binary\n*.zip binary\n", encoding="utf-8")

    # --- terrain ------------------------------------------------------------------------------------------------
    shape = (FRAME["rows"], FRAME["cols"])
    hand, slope, cover = np.ones(shape, dtype="float32"), np.zeros(shape, dtype="float32"), np.full(shape, 40, dtype="uint8")
    hand[HILLS], slope[HILLS], cover[HILLS] = 40.0, 9.0, 10
    cover[BUILT] = 50
    cover[RIVER] = 80
    terrain = external / CASE / "terrain" / "nan_frame"
    write_tif(terrain / "hand_m.tif", [hand], nodata=-9999.0)
    write_tif(terrain / "slope_deg.tif", [slope], nodata=-9999.0)
    write_tif(terrain / "worldcover.tif", [cover], nodata=0)
    write_tif(terrain / "permanent_water.tif", [(cover == 80).astype("uint8")])

    # --- radar: the Sentinel-1C pass of 2025-07-28 (orbit 99) and the Sentinel-1A pass of 2025-07-19 (orbit 62) ---
    noise = np.random.default_rng(7).normal(0.0, 0.4, shape).astype("float32")
    radar = external / CASE / "radar" / "nan_frame"
    after = (-15.0 + noise).astype("float32")
    after[FLOOD], after[STRIP], after[RIVER] = -22.0, -18.5, -24.0
    write_pass(radar, "20250728T1120Z_s1c_o99", "2025-07-28T11:20:49Z", 99, "sentinel-1c", after)
    mean_o99 = np.full(shape, -15.0, dtype="float32")
    mean_o99[STRIP] = -17.0
    write_dry(radar, 99, mean_o99)
    after_0719 = (-15.0 + noise).astype("float32")
    after_0719[FLOOD_0719], after_0719[RIVER] = -22.0, -24.0
    write_pass(radar, "20250719T2308Z_s1a_o62", "2025-07-19T23:08:07Z", 62, "sentinel-1a", after_0719)
    write_dry(radar, 62, np.full(shape, -15.0, dtype="float32"))

    # --- units of the frame -------------------------------------------------------------------------------------
    units = gpd.GeoDataFrame({"adm3_pcode": ["TH550101", "TH559901"], "adm2_pcode": ["TH5501", "TH5599"]},
                             geometry=[box_of(*UNITS), box_of(slice(0, 5), slice(0, 120))], crs="EPSG:32647").to_crs(4326)
    boundaries = external / "boundaries.gpkg"
    units.to_file(boundaries, layer="tha_admin3", driver="GPKG")

    # --- the sealed JAXA zips -----------------------------------------------------------------------------------
    sealed = external / CASE / "jaxa_sealed"
    seals = {
        t1.JAXA_MAIN: jaxa_zip(sealed / t1.JAXA_MAIN, "20250728", "202507281720", main if main is not None else main_layers()),
        t1.JAXA_SECOND: jaxa_zip(sealed / t1.JAXA_SECOND, "20250719", "202507191727", second if second is not None else
                                 {"_FLDEXT.geojson": [box_of(*FLOOD_0719)], "_REGION.geojson": [box_of(*WHOLE)]}),
    }

    # --- the records of Git -------------------------------------------------------------------------------------
    protocol = {"schema": "floodguard.nan_case_protocol.v1 (invented for the test)",
                "frame": {"district_pcodes": ["TH5501"], "units": "every unit of TH5501 (1 units)"},
                "grid": {"frame": FRAME, "chips": {"nan_chip_001": DRY_HILLS}}, "sealed_references": {"files": seals}}
    write_json(repo / "docs/proposal_execution/nan_case_protocol_v1.json", protocol)
    write_json(repo / "outputs/nan_case/areas_v1.json", {"areas": {"nan_frame": {"grid": FRAME}}})
    write_json(repo / "outputs/nan_case/tuning_v1.json", {"schema": "invented tuning record"})
    write_json(repo / "outputs/nan_case/freeze_v1.json", {
        "schema": "floodguard.nan_case_freeze.v1 (invented for the test)",
        "protocol": {"path": "docs/proposal_execution/nan_case_protocol_v1.json", "sha256": sha(repo / "docs/proposal_execution/nan_case_protocol_v1.json")},
        "tuning_record": {"path": "outputs/nan_case/tuning_v1.json", "sha256": sha(repo / "outputs/nan_case/tuning_v1.json")},
        "code_sha256": {name: sha(repo / name) for name in ("src/floodguard/m1z.py", "scripts/nan_case_method.py")},
        "selected": SELECTED, "flood_levels": LEVELS})
    write_json(repo / "outputs/nan_case/test_result_v1.json", {
        "schema": "floodguard.nan_case_test_result.v1 (invented for the test)", "generated_at_utc": "2026-10-14T18:10:18Z",
        "test_1": {"reference": "GFM ensemble flood extent of the Sentinel-1A pass of 2025-07-31 (fallback)", "pass": {"label": "20250731T2308_o62_S1A"},
                   "central": {"iou_no_answer_as_not_flagged": 0.068102, "no_answer_share": 0.072106}, "passes": False},
        "test_2": {"pass": {"label": "20250731T2308_o62_S1A"}, "central": {"iou_no_answer_as_not_flagged": 0.065172}},
        "dry_control": {"pass": {"label": "20250731T2308_o62_S1A"}, "central": {"flagged_share_of_answered": 0.000374}, "passes": True},
        "binding": {"test_1_passes": False, "dry_control_passes": True, "case_reference_date": "2025-07-31",
                    "flood_input_of_case_N1": {"label": "20250731T2308_o62_S1A"},
                    "reference_of_case_N2": {"name": "reference_test_1_gfm_20250731T2308.tif"}}})

    git(tmp_path, "init", "-q", "--bare", "--template=", str(remote))
    git(repo.parent, "init", "-q", "--template=", "-b", "main", str(repo))
    for key, value in (("user.name", "test"), ("user.email", "test@example.org"), ("core.autocrlf", "false")):
        git(repo, "config", key, value)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "invented case")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "-u", "origin", "main")
    return SimpleNamespace(repo=repo, external=external, boundaries=boundaries, sealed=sealed, seals=seals)


@pytest.fixture()
def world(tmp_path: Path) -> SimpleNamespace:
    return build_world(tmp_path)


def no_gfm(*_args: object) -> None:
    return None


def run_stage(world: SimpleNamespace, *extra: str, gfm: Any = no_gfm) -> dict[str, Any]:
    return t1.run(["--external-root", str(world.external), "--boundaries", str(world.boundaries), *extra], root=world.repo,
                  hooks={"gfm_fetch": gfm})


def refused(world: SimpleNamespace, *extra: str, match: str) -> None:
    with pytest.raises(t1.StageError, match=match):
        run_stage(world, *extra)


def listing(folder: Path) -> dict[str, str]:
    return {path.name: sha(path) for path in sorted(Path(folder).iterdir())}


def wording_findings(texts: list[tuple[str, str]]) -> list[str]:
    from floodguard.wording_lint import lint_texts, load_rules

    return [finding.describe() for finding in lint_texts(texts, load_rules(RULES))]


# ---------------------------------------------------------------------------------------------------------------------
# The two layers
# ---------------------------------------------------------------------------------------------------------------------


def test_the_two_layers_are_read_from_the_sealed_zip_in_memory(tmp_path: Path) -> None:
    pytest.importorskip("pyogrio")
    from shapely.geometry import MultiPolygon

    sealed = tmp_path / "jaxa_sealed"
    path = sealed / t1.JAXA_MAIN
    digest = jaxa_zip(path, "20250728", "202507281720",
                      {"_FLDEXT.geojson": [MultiPolygon([box_of(*FLOOD), box_of(*FLOOD_OUTSIDE_REGION)])], "_REGION.geojson": [box_of(*REGION_0728)],
                       "_OTHER.geojson": [box_of(*WHOLE)]},
                      extra={"readme.txt": b"Observation 2025-07-28T03:20:00Z; product stamp 202507281720"})
    before = listing(sealed)

    data = t1.read_sealed(path, digest)
    found = t1.jaxa_layers(data, t1.JAXA_MAIN)
    record = found["record"]
    assert record["flood_layer"]["member"].endswith("2025-00032-WLD_202507281720_FLDEXT.geojson")
    assert record["observation_area_layer"]["member"].endswith("2025-00032-WLD_202507281720_REGION.geojson")
    assert record["flood_layer"]["polygon_features"] == 1 and record["flood_layer"]["geometry_types"] == ["MultiPolygon"]
    assert record["observation_area_layer"]["polygon_features"] == 1 and record["observation_area_layer"]["crs"] == "EPSG:4326"
    assert sorted(Path(name).name for name in record["members_not_used"]) == ["2025-00032-WLD_202507281720_OTHER.geojson", "readme.txt"]
    assert record["times_with_a_zone_utc"] == ["2025-07-28T03:20:00Z"]   # read only where a zone is given
    assert found["flood"].crs.to_epsg() == 32647 and found["region"].crs.to_epsg() == 32647
    # The other layer is not merged into the water: on the grid, the water is the two flood boxes only.
    on_grid = t1.jaxa_on_grid(found, GRID, np.ones((FRAME["rows"], FRAME["cols"]), dtype=bool))
    assert on_grid["counts"]["fldext_cells_on_the_grid"] == 14 * 16 + 16 and on_grid["counts"]["region_cells_on_the_grid"] == 120 * 80
    # Read in memory: nothing extracted, nothing changed.
    assert listing(sealed) == before and t1.verify_seal(path, digest) == digest

    with pytest.raises(t1.StageError, match="not the file the protocol sealed"):
        t1.read_sealed(path, "0" * 64)
    path.write_bytes(path.read_bytes() + b"\0")
    with pytest.raises(t1.StageError, match="changed during the run"):
        t1.verify_seal(path, digest)


def test_a_missing_doubled_or_empty_layer_is_refused(tmp_path: Path) -> None:
    pytest.importorskip("pyogrio")
    from shapely.geometry import Point

    flood, region = [box_of(*FLOOD)], [box_of(*REGION_0728)]
    cases = {
        "no_region": ({"_FLDEXT.geojson": flood}, "no layer whose name ends with _REGION.geojson"),
        "no_flood": ({"_REGION.geojson": region}, "no layer whose name ends with _FLDEXT.geojson"),
        "empty_region": ({"_FLDEXT.geojson": flood, "_REGION.geojson": [Point(FRAME["west"] + 10, FRAME["north"] - 10)]}, "holds no polygon"),
    }
    for name, (layers, match) in cases.items():
        path = tmp_path / name / t1.JAXA_MAIN
        jaxa_zip(path, "20250728", "202507281720", layers)
        with pytest.raises(t1.JaxaLayerError, match=match):
            t1.jaxa_layers(path.read_bytes(), t1.JAXA_MAIN)
    doubled = tmp_path / "doubled" / t1.JAXA_MAIN
    jaxa_zip(doubled, "20250728", "202507281720", {"_FLDEXT.geojson": flood, "_REGION.geojson": region},
             extra={"second_REGION.geojson": geojson(region)})
    with pytest.raises(t1.JaxaLayerError, match="more than one layer whose name ends with _REGION.geojson"):
        t1.jaxa_layers(doubled.read_bytes(), t1.JAXA_MAIN)
    # A layer error is a refusal of the stage.
    assert issubclass(t1.JaxaLayerError, t1.StageError)


def test_the_compared_cells_are_frame_land_inside_region_by_cell_centre() -> None:
    gpd = pytest.importorskip("geopandas")
    pytest.importorskip("rasterio")
    from shapely.geometry import box

    grid = (1000.0, 2000.0, 10, 10)
    units = np.zeros((10, 10), dtype=bool)
    units[1:9, 1:9] = True
    water = np.zeros((10, 10), dtype=bool)
    water[:, 5] = True                                   # permanent water
    # REGION's west edge at x = 1055: a quarter of column 2 lies inside, but its centre (1050) does not.
    region_frame = gpd.GeoDataFrame(geometry=[box(1055.0, 1800.0, 1200.0, 2000.0)], crs="EPSG:32647")
    region = t1.method.rasterize_polygons(region_frame, grid)
    assert region[:, :3].sum() == 0 and region[:, 3:].all()
    land = units & ~water
    compared = t1.compared_cells(land, region)
    expected = np.zeros((10, 10), dtype=bool)
    expected[1:9, 3:9] = True
    expected[:, 5] = False
    assert np.array_equal(compared, expected) and int(compared.sum()) == 8 * 5
    share = t1.region_cover(region, land)
    assert share == pytest.approx(40 / 56)
    t1.require_cover(share, "invented.zip")
    with pytest.raises(t1.StageError, match="less than half"):
        t1.require_cover(0.499, "invented.zip")
    t1.require_cover(0.5, "invented.zip")               # at least half is enough
    with pytest.raises(t1.StageError, match="share one grid"):
        t1.compared_cells(land, region[:5])


def test_the_pass_rule_and_the_comparators_reported_above_ours() -> None:
    assert t1.verdict({"iou_no_answer_as_not_flagged": 0.40, "no_answer_share": 0.20}) is True
    assert t1.verdict({"iou_no_answer_as_not_flagged": 0.399, "no_answer_share": 0.0}) is False
    assert t1.verdict({"iou_no_answer_as_not_flagged": 0.9, "no_answer_share": 0.21}) is False
    assert t1.verdict({"iou_no_answer_as_not_flagged": None, "no_answer_share": 0.0}) is False
    better = t1.better_than_ours({"a": {"iou_no_answer_as_not_flagged": 0.5}, "b": {"iou_no_answer_as_not_flagged": 0.2}, "c": {"not_run": "x"}},
                                 {"iou_no_answer_as_not_flagged": 0.3})
    assert better == {"a": 0.5}


# ---------------------------------------------------------------------------------------------------------------------
# The run on an invented world
# ---------------------------------------------------------------------------------------------------------------------


def test_test_1_of_record_scores_the_offset_map_against_jaxa_and_writes_figures_only(world: SimpleNamespace) -> None:
    rasterio = pytest.importorskip("rasterio")
    asked: list[tuple[Any, Any]] = []

    def fake_gfm(grid: tuple, start: Any, end: Any) -> dict:
        asked.append((start, end))
        flood = np.zeros((grid[2], grid[3]), dtype="uint8")
        flood[FLOOD] = 1
        return {"flood": flood, "exclusion": np.zeros_like(flood), "items": [{"id": "invented", "datetime": "2025-07-28T11:20:49Z"}]}

    sealed_before = listing(world.sealed)
    record = run_stage(world, gfm=fake_gfm)
    test_1 = record["test_1"]

    # The pass amendment 2 names, raised by the 0.79 dB of amendment 1.
    assert test_1["pass"]["label"] == "20250728T1120_o99_S1C" and test_1["platform_offset_db"] == pytest.approx(0.79)
    assert "amendment 2 names" in test_1["pass_choice"]
    # Compared cells: frame land inside REGION by cell centre; JAXA water outside REGION is not compared.
    central = test_1["central"]
    assert central["compared_cells"] == LAND_INSIDE_REGION and test_1["jaxa"]["frame_land_cells_inside_region"] == LAND_INSIDE_REGION
    assert test_1["jaxa"]["share_of_frame_land_inside_region"] == pytest.approx(LAND_INSIDE_REGION / FRAME_LAND, abs=1e-6)
    assert test_1["jaxa"]["fldext_cells_on_the_grid"] == 14 * 16 + 16 and test_1["jaxa"]["fldext_cells_inside_region"] == 14 * 8
    assert central["reference_water_cells"] == 14 * 8 and central["true_positive"] == 14 * 8 and central["false_positive"] == 0
    assert central["no_answer_cells"] == 25 and central["no_answer_share"] == pytest.approx(25 / LAND_INSIDE_REGION, abs=1e-6)
    assert central["iou_no_answer_as_not_flagged"] == pytest.approx(1.0) and test_1["passes"] is True and test_1["verdict"] == "passes"
    assert set(test_1["central_by_worldcover_group"]) == {"built_up", "cropland", "tree_cover", "other"}
    assert test_1["central_by_worldcover_group"]["built_up"]["no_answer_cells"] == 25
    assert test_1["central_interval_95"]["resamples"] == 1000 and test_1["central_interval_95"]["tiles"] == 2
    assert test_1["central_reasons_on_compared_cells"]["no_answer_built_up_at_low_hand"] == 25
    for level in ("lower", "upper"):
        assert test_1[level]["compared_cells"] == LAND_INSIDE_REGION
    # Without the offset the strip of darker Sentinel-1C cells is flagged: reported, not binding.
    raw = test_1["central_without_platform_offset_report_only"]
    assert raw["false_positive"] == 10 * 30 and raw["iou_no_answer_as_not_flagged"] == pytest.approx(112 / 412, abs=1e-6)
    # The comparators of the frozen code ran on the same pass and cells; GFM of the same pass was asked once.
    comparators = test_1["comparators"]
    assert set(comparators) == {"r37_frozen_detector", "r37_simple_threshold", "un_spider_dry_mean_before", "m1_literal_dry_mean_before", "m1_v2_dry_mean_before"}
    assert comparators["r37_simple_threshold"]["compared_cells"] == LAND_INSIDE_REGION
    assert len(asked) == 1 and str(asked[0][0]).startswith("2025-07-28 10:50:49") and str(asked[0][1]).startswith("2025-07-28 11:50:49")
    assert test_1["external_comparator_gfm_same_pass"]["iou_no_answer_as_not_flagged"] == pytest.approx(1.0)

    # Test 1b: the map of 2025-07-19 against the pass nearest to 2025-07-19 12:00 Thai time, report only.
    test_1b = record["test_1b_report_only"]
    assert test_1b["report_only"] is True and test_1b["pass"]["label"] == "20250719T2308_o62_S1A"
    assert test_1b["pass_target"]["hours_from_the_target"] == pytest.approx(18.14, abs=0.01) and test_1b["platform_offset_db"] == 0.0
    assert test_1b["central"]["compared_cells"] == FRAME_LAND and test_1b["central"]["iou_no_answer_as_not_flagged"] == pytest.approx(1.0)
    assert test_1b["jaxa"]["region_covers_at_least_half_of_the_frame_land"] is True
    assert record["dry_chip_report_only_on_the_test_1_pass"]["central"]["flagged_cells"] == 0

    # The binding block: this test 1 with the dry control of the first run.
    binding = record["binding"]
    assert binding["test_1_passes"] is True and binding["dry_control_passes"] is True and binding["case_reference_date"] == "2025-07-28"
    assert binding["dry_control_taken_from"] == {"path": "outputs/nan_case/test_result_v1.json", "sha256": sha(world.repo / "outputs/nan_case/test_result_v1.json")}
    flood_input = binding["flood_input_of_case_N1"]
    maps = world.external / CASE / "method" / "maps"
    assert flood_input["label"] == "20250728T1120_o99_S1C" and flood_input["days_from_the_case_reference_date_thai_calendar"] == 0
    assert flood_input["map"] == {"name": MAIN_MAP, "sha256": sha(maps / MAIN_MAP), "record": "m1z_20250728T1120_o99_S1C.json"}
    assert record["map_files"]["test_1_pass"]["status"].startswith("written by this run")
    with rasterio.open(maps / MAIN_MAP) as source:
        assert source.count == 4 and list(source.descriptions) == ["code_lower", "code_central", "code_upper", "reason_central"]
        central_band = source.read(2)
    assert (central_band[FLOOD] == 1).all() and (central_band[STRIP] == 0).all() and (central_band[BUILT] == 255).all()

    # The case N2 reference: FLDEXT by cell centre inside REGION, 255 outside; in the work folder only.
    n2 = binding["reference_of_case_N2"]
    n2_path = world.external / CASE / "method" / "case_n2_reference" / "reference_test_1_jaxa_20250728.tif"
    assert n2["name"] == n2_path.name and n2["sha256"] == sha(n2_path)
    assert n2["cells_by_code"] == {"1": 112, "0": 120 * 80 - 112, "255": 120 * 40}
    with rasterio.open(n2_path) as source:
        n2_code = source.read(1)
    assert (n2_code[:, 80:] == 255).all() and (n2_code[62:76, 72:80] == 1).all() and int((n2_code == 1).sum()) == 112

    # Hashes of every record and file it read; the seals checked before and after; the sealed folder untouched.
    repo = world.repo
    assert record["freeze_record"]["sha256"] == sha(repo / "outputs/nan_case/freeze_v1.json")
    assert record["protocol"]["sha256"] == sha(repo / "docs/proposal_execution/nan_case_protocol_v1.json")
    assert record["amendment_1"]["sha256"] == sha(repo / "docs/proposal_execution/nan_case_protocol_v1_amendment_1.json")
    assert record["amendment_2"]["sha256"] == sha(repo / "docs/proposal_execution/nan_case_protocol_v1_amendment_2.json")
    assert record["code_sha256"] == {name: sha(repo / name) for name in ("scripts/nan_case_test1_jaxa.py", "src/floodguard/m1z.py", "scripts/nan_case_method.py")}
    for name, digest in world.seals.items():
        entry = record["jaxa_files"][name]
        assert entry["sha256_in_the_protocol"] == entry["sha256_of_the_bytes_read"] == entry["sha256_after_the_scoring"] == digest
    assert listing(world.sealed) == sealed_before
    assert record["map_files"]["inputs_of_the_test_1_pass"]["event"]["name"] == "event_20250728T1120Z_s1c_o99.tif"
    assert record["first_run"]["kept_as_written"] is True and record["first_run"]["test_1_gfm_fallback_reported_beside"]["passes"] is False
    for field in ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions"):
        assert record[field]
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False and record["supersedes"] is None

    raw_bytes = (repo / t1.OUTPUT).read_bytes()
    assert b"\r" not in raw_bytes and raw_bytes.endswith(b"\n")
    assert b'"coordinates"' not in raw_bytes and b"Polygon\", \"coordinates" not in raw_bytes   # figures only, no geometry
    from floodguard.wording_lint import json_strings

    assert wording_findings(list(json_strings(json.loads(raw_bytes)))) == []


def test_the_run_refuses_out_of_order_and_runs_once(tmp_path: Path) -> None:
    # The map of 2025-07-19 lacks its REGION layer: test 1b is then not scored, and the run is not refused for it.
    world = build_world(tmp_path, second={"_FLDEXT.geojson": [box_of(*FLOOD_0719)]})
    repo = world.repo

    for relative, match in (("outputs/nan_case/test_result_v1.json", "test_result_v1.json does not exist"),
                            ("outputs/nan_case/freeze_v1.json", "no freeze record")):
        kept = (repo / relative).read_bytes()
        (repo / relative).unlink()
        refused(world, match=match)
        (repo / relative).write_bytes(kept)
    script_copy = repo / "scripts/nan_case_test1_jaxa.py"
    original = script_copy.read_bytes()
    script_copy.write_bytes(original + b"# changed\n")
    refused(world, match="commit this script first")
    script_copy.write_bytes(original)
    first_run = repo / "outputs/nan_case/test_result_v1.json"
    kept = first_run.read_bytes()
    first_run.write_bytes(kept.replace(b'"passes": true', b'"passes": false', 1))
    refused(world, match="test_result_v1.json is not in the HEAD commit")
    first_run.write_bytes(kept)

    record = run_stage(world)
    assert record["test_1b_report_only"]["jaxa"]["not_scored"].endswith("holds no layer whose name ends with _REGION.geojson")
    assert "pass" not in record["test_1b_report_only"]
    assert record["test_1"]["external_comparator_gfm_same_pass"] == {"not_run": "GFM holds no item of this pass over the frame"}
    written = (repo / t1.OUTPUT).read_bytes()

    refused(world, match="runs once")
    refused(world, "--replace", match="--replace needs --reason")
    again = run_stage(world, "--replace", "--reason", "invented: a second run in the test")
    assert again["supersedes"]["reason"] == "invented: a second run in the test" and again["supersedes"]["sha256"] == hashlib.sha256(written).hexdigest()
    # The second run found the map of the first in the maps folder, read it and did not write it again.
    assert again["map_files"]["test_1_pass"]["status"].startswith("found in the maps folder")
    assert again["binding"]["flood_input_of_case_N1"]["map"]["sha256"] == record["binding"]["flood_input_of_case_N1"]["map"]["sha256"]


def test_a_region_that_covers_less_than_half_of_the_frame_land_is_refused(tmp_path: Path) -> None:
    world = build_world(tmp_path, main=main_layers(region=(slice(0, 120), slice(0, 40))))
    refused(world, match="REGION covers 0.347 of the frame's land outside permanent water, less than half")
    assert not (world.repo / t1.OUTPUT).exists()
    assert not (world.external / CASE / "method" / "case_n2_reference").exists()
    assert not (world.external / CASE / "method" / "maps").exists()


def test_a_missing_layer_or_a_broken_seal_refuses_the_run(tmp_path: Path) -> None:
    world = build_world(tmp_path / "no_region", main={"_FLDEXT.geojson": [box_of(*FLOOD)]})
    refused(world, match="no layer whose name ends with _REGION.geojson")
    assert not (world.repo / t1.OUTPUT).exists()

    world = build_world(tmp_path / "broken_seal")
    path = world.sealed / t1.JAXA_SECOND
    path.write_bytes(path.read_bytes() + b"\0")
    refused(world, match="is not the file the protocol sealed")
    assert not (world.repo / t1.OUTPUT).exists()


def test_a_map_of_the_maps_stage_must_hold_the_values_of_this_run(world: SimpleNamespace) -> None:
    rasterio = pytest.importorskip("rasterio")
    first = run_stage(world)
    maps = world.external / CASE / "method" / "maps"
    path = maps / MAIN_MAP
    original = path.read_bytes()
    kept_record = (world.repo / t1.OUTPUT).read_bytes()

    with rasterio.open(path) as source:
        profile, bands = source.profile, source.read()
        descriptions = source.descriptions
    changed = bands.copy()
    changed[1, 0, 0] = 1 if changed[1, 0, 0] != 1 else 0
    with rasterio.open(path, "w", **profile) as target:
        target.write(changed)
        for index, name in enumerate(descriptions, start=1):
            target.set_band_description(index, name)
    refused(world, "--replace", "--reason", "invented", match="differs from the map this run makes in code_central")
    assert (world.repo / t1.OUTPUT).read_bytes() == kept_record    # nothing written on a refusal

    path.write_bytes(original)
    map_record = path.with_suffix(".json")
    kept_map_record = map_record.read_bytes()
    map_record.write_bytes(kept_map_record.replace(first["freeze_record"]["sha256"].encode(), b"0" * 64))
    refused(world, "--replace", "--reason", "invented", match="another freeze record")
    map_record.write_bytes(kept_map_record)

    again = run_stage(world, "--replace", "--reason", "invented: the map is the maps stage's")
    assert path.read_bytes() == original and again["map_files"]["test_1_pass"]["sha256"] == hashlib.sha256(original).hexdigest()


def test_the_wording_of_the_script_passes_the_shared_lint() -> None:
    from floodguard.wording_lint import python_strings

    texts = python_strings(SCRIPT.read_text(encoding="utf-8"))
    assert wording_findings([(SCRIPT.name, text) for text in texts]) == []
    for sentence in (*t1.ASSUMPTIONS, *t1.LIMITS, *t1.MEASURES_NAMED.values()):
        for word in ("accura", "validat", "precision", "recall", "real-time", "forecast"):
            assert word not in sentence.lower()
    raw = SCRIPT.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"\n")
