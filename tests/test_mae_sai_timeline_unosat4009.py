"""Season-envelope stage of the Mae Sai bake (``scripts/mae_sai_timeline_unosat4009.py``) and the files it publishes.

UNOSAT/GISTDA product 4009 is shown as a scenario layer (SCN-ENV): accumulated water from August to October 2024,
never an observation for a replay day. The tests cover the stage on synthetic geometry, its rights gate, the three
committed files (raster, statistics, licence notice), the figures against the scouts' earlier values, and that nothing
derived from the product reaches ``timeline.json`` or the export pack. The tests that read the product archive are
skipped unless ``FLOODGUARD_EXTERNAL_DATA`` points at the external data root.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys

import pytest

np = pytest.importorskip("numpy")
shapely = pytest.importorskip("shapely")
rasterio = pytest.importorskip("rasterio")
pytest.importorskip("pyproj")
PIL_Image = pytest.importorskip("PIL.Image")

from pyproj import Transformer  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape  # noqa: E402

import floodguard.replay_exports as replay_exports  # noqa: E402
from floodguard.rights_basis import RIGHTS_BASIS_4009_PATH, RightsNotConfirmedError, file_sha256, load_rights_basis  # noqa: E402
from floodguard.season_envelope import COMPARISON_ROLE, credit_holders, document_problems, fill_change_notice, mask_agreement  # noqa: E402
from floodguard.wording_lint import find_violations, json_strings, load_rules  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WEB = ROOT / "apps" / "web"
RECORD_PATH = ROOT / RIGHTS_BASIS_4009_PATH
CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
UTM = "EPSG:32647"
PRECACHE_BUDGET_BYTES = 6_500_000
SOURCES = [
    {"id": "copernicus-dem", "name": "Copernicus DEM GLO-30", "licence": "Copernicus DEM licence (free, attribution)", "timestamp": "2021 release",
     "attribution": "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA"},
    {"id": "osm", "name": "OpenStreetMap", "licence": "ODbL 1.0", "timestamp": "2026-07-09", "attribution": "© OpenStreetMap contributors"},
    {"id": "worldpop", "name": "WorldPop Thailand 100 m population 2020", "licence": "CC BY 4.0", "timestamp": "2020 estimate",
     "attribution": "WorldPop (www.worldpop.org), University of Southampton"},
    {"id": "cod-ab", "name": "HDX Thailand COD-AB subdistrict boundaries v01", "licence": "CC BY-IGO", "timestamp": "valid from 2022-01-22",
     "attribution": "OCHA / HDX Thailand COD-AB"},
]
"""Source lines as the bake passes them to the stage (its own list also holds inputs the envelope file does not use)."""
TAMBON_NAMES = {"TH570901": "Mae Sai", "TH570902": "Huai Khrai", "TH570903": "Ko Chang", "TH570904": "Pong Pha", "TH570905": "Si Mueang Chum",
                "TH570906": "Wiang Phang Kham", "TH570908": "Ban Dai", "TH570909": "Pong Ngam"}


def load_script(name: str):
    """Import a bake script by file, with ``scripts/`` importable for its sibling stage modules."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS))
    return module


@pytest.fixture(scope="module")
def stage():
    return load_script("mae_sai_timeline_unosat4009")


@pytest.fixture(scope="module")
def record() -> dict:
    return load_rights_basis(RECORD_PATH)


def pending_copy(record: dict) -> dict:
    """The rights record as it was before the owners confirmed it (test-only; never written to the repository)."""
    pending = copy.deepcopy(record)
    pending["owner_confirmation"].update(status="pending", confirmed_by=[], confirmed_on=None)
    pending.update(record_status="draft_pending_owner_confirmation", signed_by_human=False, human_rights_clearance=False)
    return pending


def manifest_path() -> Path:
    source = (WEB / "src" / "lib" / "flood-timeline.ts").read_text(encoding="utf-8")
    href = re.search(r'TIMELINE_MANIFEST_URL = "([^"]+)"', source).group(1)
    return WEB / "public" / href.lstrip("/")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(manifest_path().read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def folder() -> Path:
    return manifest_path().parent / "unosat4009"


@pytest.fixture(scope="module")
def document(folder: Path) -> dict:
    return json.loads((folder / "envelope.json").read_text(encoding="utf-8"))


class Grid:
    """A north-up test grid with the attributes the stage reads."""

    def __init__(self, crs: str, west: float, north: float, res: float, width: int, height: int) -> None:
        self.crs, self.res, self.width, self.height = crs, res, width, height
        self.transform = from_origin(west, north, res, res)
        self.shape = (height, width)


def to_lonlat(geometry):
    transformer = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True)
    return shapely.transform(geometry, lambda xy: np.column_stack(transformer.transform(xy[:, 0], xy[:, 1])))


# --- Geometry helpers on synthetic shapes ----------------------------------------------------------------------


def test_only_the_accumulated_chiang_rai_layer_is_named(stage, record: dict) -> None:
    # One layer of the archive: no Phayao, Chiang Mai or Doi Tao layer (decision D11) and not the 22 October extent (D3b).
    assert stage.LAYER == "CHIANGRAI_20240801_20241012_AccumulatedFlood" == record["product"]["layer_in_scope"]
    source = (SCRIPTS / "mae_sai_timeline_unosat4009.py").read_text(encoding="utf-8")
    code = source.split('"""', 2)[2]  # The module docstring names the layers it leaves out; the code names only one.
    assert not re.search(r"PHAYAO|Doitao|GF1_|20241022_FloodExtent|AnalysisExtent|list_layers", code)
    assert code.count("layer=LAYER") == 1 and "/vsizip/" in code
    assert (stage.FOLDER, stage.FILE_NAMES) == ("unosat4009", ("envelope.png", "envelope.json", "LICENSE"))
    assert stage.map_credit("CC BY-SA 4.0") == "UNOSAT and GISTDA · CC BY-SA 4.0"
    assert stage.LABEL == "Scenario (SCN-ENV): 2024 season envelope"
    assert stage.COMPARISON_TITLE == "Season envelope comparison (scenario; plausibility, not validation)"


def test_district_clip_repairs_invalid_parts_and_counts_them(stage) -> None:
    district = [box(0, 0, 10, 10), box(10, 0, 20, 10)]
    bow_tie = Polygon([(2, 2), (6, 6), (6, 2), (2, 6)])  # Self-intersecting: two triangles of 4 square units each.
    inside = box(8, 1, 14, 3)  # Straddles the two subdistricts.
    half_out = box(18, 8, 24, 12)  # Only 2 x 2 of it is inside the district.
    far_valid = box(100, 100, 110, 110)
    far_bow_tie = Polygon([(200, 200), (204, 204), (204, 200), (200, 204)])
    layer = MultiPolygon([bow_tie, inside, half_out, far_valid, far_bow_tie])
    assert not layer.is_valid
    clip, repair = stage.district_clip(layer, district)
    assert clip.is_valid and not clip.is_empty
    assert clip.area == pytest.approx(8 + 12 + 4)
    assert repair == {"method": "make_valid", "source_parts": 5, "source_parts_invalid": 2, "parts_meeting_district": 3, "parts_repaired": 1,
                      "note": repair["note"]}
    assert "parts_repaired counts the invalid ones among them" in repair["note"]
    assert clip.intersection(district[0]).area == pytest.approx(8 + 4) and clip.intersection(district[1]).area == pytest.approx(8 + 4)
    # A layer that does not meet the district gives an empty clip, and an empty raster.
    empty, nothing = stage.district_clip(MultiPolygon([far_valid]), district)
    assert empty.is_empty and (nothing["parts_meeting_district"], nothing["parts_repaired"]) == (0, 0)
    assert not stage.rasterise(empty, from_origin(0, 10, 1, 1), (10, 20)).any()


def test_rasterise_counts_a_cell_when_its_centre_is_inside_and_the_png_is_one_bit(stage) -> None:
    transform = from_origin(0, 10, 1, 1)
    mask = stage.rasterise(box(2.4, 2.6, 6.6, 7.4), transform, (10, 12))
    assert mask.dtype == bool and mask.shape == (10, 12)
    # Columns whose centres 2.5 .. 6.5 lie inside: 2 to 6. Rows whose centres 2.5 .. 7.5 lie inside (north-up): y 3.5 .. 6.5 -> rows 3 to 6.
    assert mask.sum() == 5 * 4 and mask[3:7, 2:7].all()
    data = stage.bitmask_png(mask)
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and (data[24], data[25]) == (1, 0)  # Bit depth 1, greyscale.
    assert int.from_bytes(data[16:20], "big") == 12 and int.from_bytes(data[20:24], "big") == 10
    decoded = np.asarray(PIL_Image.open(io.BytesIO(data)))
    assert decoded.dtype == bool and (decoded == mask).all()
    assert stage.bitmask_png(mask) == data  # The same mask gives the same bytes.


# --- The stage on a synthetic district ----------------------------------------------------------------------------


@pytest.fixture()
def synthetic(stage, record: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """A 2 km x 2 km district of two subdistricts on a 10 m grid, with an envelope of three parts (one invalid)."""
    west, north = 590_000.0, 2_252_000.0
    statistics = Grid(UTM, west, north, 10.0, 200, 200)
    extent = Transformer.from_crs(UTM, "EPSG:3857", always_xy=True).transform_bounds(west, north - 2000, west + 2000, north, densify_pts=21)
    raster = Grid("EPSG:3857", extent[0], extent[3], (extent[2] - extent[0]) / 130, 130, 130)
    tambons_utm = {"A": box(west, north - 2000, west + 1000, north), "B": box(west + 1000, north - 2000, west + 2000, north)}
    admin = [{"type": "Feature", "properties": {"subdistrict_id": tid}, "geometry": mapping(to_lonlat(geom))} for tid, geom in tambons_utm.items()]
    zones = rasterize(((geom, index + 1) for index, geom in enumerate(tambons_utm.values())), out_shape=statistics.shape, transform=statistics.transform, fill=0, dtype="uint8")
    # Envelope: a bow tie in A (two triangles), a rectangle across both subdistricts, one part half outside, one far away.
    x0, y0 = west, north - 2000
    parts_utm = [
        # Shifted 3 m east, so no cell centre lies exactly on one of its diagonals.
        Polygon([(x0 + 103, y0 + 100), (x0 + 503, y0 + 500), (x0 + 503, y0 + 100), (x0 + 103, y0 + 500)]),
        box(x0 + 600, y0 + 1000, x0 + 1400, y0 + 1600),
        box(x0 + 1800, y0 + 1800, x0 + 2400, y0 + 2400),
        box(x0 + 50_000, y0, x0 + 51_000, y0 + 1000),
    ]
    layer = MultiPolygon([to_lonlat(part) for part in parts_utm])
    # Model: codes rise from west to east (code = column / 2), with a channel column and a strip that is never wet.
    codes = np.tile((np.arange(200) // 2).astype(np.uint8), (200, 1))
    codes[:, 60] = 0  # A mapped channel, running north to south through the envelope's rectangle.
    codes[:20, :] = 255
    low_confidence = np.zeros(statistics.shape, dtype=bool)
    low_confidence[80:120, 0:40] = True
    residents = np.full(statistics.shape, 0.25)
    # A population raster on its own lon/lat grid (cells of 1/1200 degree, as WorldPop's): two residents per cell,
    # no data in its first row, and a negative value in one cell.
    lon0, lat0, cell = 99.85, 20.38, 1 / 1200
    cells = np.full((60, 60), 2.0, dtype=np.float32)
    cells[0, :] = -99999.0
    population = tmp_path / "population.tif"
    with rasterio.open(population, "w", driver="GTiff", width=60, height=60, count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(lon0, lat0, cell, cell), nodata=-99999.0) as target:
        target.write(cells, 1)
    tracked: list[Path] = []
    monkeypatch.setattr(stage, "read_layer", lambda archive, expected: layer)
    monkeypatch.setattr(stage, "verify_archive", lambda rights, external: Path(external) / rights["archive"]["relative_path"])
    stages = [{"id": "modelled_peak", "model_stage_m": 3.5, "model_extent": "The modelled peak"},
              {"id": "lower", "model_stage_m": 1.0, "model_extent": "A lower stage"}]
    data = stage.season_envelope(
        tmp_path / "external", record, admin, statistics_grid=statistics, raster_grid=raster, codes=codes, zones=zones, tambon_ids=["A", "B"],
        low_confidence=low_confidence, residents=residents, population=population, channel_code=0, never_code=255, hand_step_m=0.05, stages=stages,
        clip_source="two test subdistricts", track=lambda path: tracked.append(Path(path)) or path)
    clip_utm = shapely.union_all([shapely.make_valid(part) for part in parts_utm[:3]]).intersection(shapely.union_all(list(tambons_utm.values())))
    return {"data": data, "tracked": tracked, "zones": zones, "codes": codes, "clip_utm": clip_utm, "tambons_utm": tambons_utm,
            "statistics": statistics, "raster": raster, "low_confidence": low_confidence, "residents": residents, "external": tmp_path / "external",
            "population": population, "population_grid": (lon0, lat0, cell, cells)}


def test_stage_clips_rasterises_and_tabulates_the_envelope_per_subdistrict(stage, record: dict, synthetic: dict) -> None:
    data = synthetic["data"]
    # The archive is the one input, recorded before it is opened.
    assert synthetic["tracked"] == [synthetic["external"] / record["archive"]["relative_path"]]
    assert data["repair"] | {"note": ""} == {"method": "make_valid", "source_parts": 4, "source_parts_invalid": 1, "parts_meeting_district": 3,
                                             "parts_repaired": 1, "note": ""}
    # Per-subdistrict km2 on the 10 m grid agree with the vector clip (the test's own, in UTM) to well within 0.05 km2.
    vector = {tid: synthetic["clip_utm"].intersection(geom).area / 1e6 for tid, geom in synthetic["tambons_utm"].items()}
    assert vector == pytest.approx({"A": 0.08 + 0.24, "B": 0.24 + 0.04}, abs=1e-6)
    table = data["area"]["by_tambon"]
    for tid, area in vector.items():
        assert abs(table[tid]["envelope_km2"] - area) < 0.005, tid
        assert table[tid]["tambon_km2"] == 2.0 and table[tid]["share_of_tambon"] == pytest.approx(area / 2.0, abs=0.003)
    assert data["area"]["district_km2"] == pytest.approx(sum(vector.values()), abs=0.005)
    assert data["area"]["district_vector_km2"] == pytest.approx(sum(vector.values()), abs=0.005)
    # The channel column crosses the rectangle: 60 cells of 100 m2 are envelope water on a mapped channel.
    assert data["area"]["on_mapped_channels_km2"] == pytest.approx(0.006, abs=0.005)  # Published to two decimals.
    # The published raster is 1-bit, on the raster grid, and holds about the same area there.
    image = np.asarray(PIL_Image.open(io.BytesIO(data["raster_png"])))
    assert image.shape == synthetic["raster"].shape and image.dtype == bool
    assert data["raster"] == {"width": 130, "height": 130, "crs": "EPSG:3857"}
    assert image.sum() / image.size == pytest.approx(sum(vector.values()) / 4.0, abs=0.01)


def test_stage_compares_the_model_with_the_envelope_outside_channels(stage, synthetic: dict) -> None:
    data, zones, codes = synthetic["data"], synthetic["zones"], synthetic["codes"]
    envelope = rasterize([(synthetic["clip_utm"], 1)], out_shape=codes.shape, transform=synthetic["statistics"].transform, fill=0, dtype="uint8").astype(bool)
    channel = codes == 0
    out_of_channel = envelope & ~channel
    assert [row["id"] for row in data["district"]] == ["modelled_peak", "lower"]
    for row, stage_m in zip(data["district"], (3.5, 1.0)):
        wet = ~channel & (codes != 255) & (codes.astype(int) * 0.05 < stage_m)
        expected = mask_agreement(wet, out_of_channel, 1e-4, zones > 0)
        assert {key: row[key] for key in expected} == expected, row["id"]
        assert row["model_stage_m"] == stage_m
        # The envelope side of every row leaves the channel cells out, like every flooded area of the replay.
        assert row["envelope_km2"] == pytest.approx(data["area"]["district_km2"] - data["area"]["on_mapped_channels_km2"], abs=0.011)
    peak, lower = data["district"]
    assert lower["model_km2"] < peak["model_km2"] and lower["containment_envelope_in_model"] < peak["containment_envelope_in_model"]
    # Per subdistrict at the first stage, and the two lists of largest differences (each at least 0.5 km2: none here).
    assert data["by_tambon_stage"] == "modelled_peak" and [row["tambon_id"] for row in data["by_tambon"]] == ["A", "B"]
    wet = ~channel & (codes != 255) & (codes.astype(int) * 0.05 < 3.5)
    for index, row in enumerate(data["by_tambon"]):
        expected = mask_agreement(wet, out_of_channel, 1e-4, zones == index + 1)
        assert {key: row[key] for key in expected} == expected
    assert sum(row["overlap_km2"] for row in data["by_tambon"]) == pytest.approx(peak["overlap_km2"], abs=0.011)
    assert data["disagreement"] == {"minimum_km2": 0.5, "envelope_water_the_model_lacks": [], "modelled_water_outside_the_envelope": ["A"]}
    # Low-confidence water against the other modelled water, and residents as one district total.
    low = synthetic["low_confidence"]
    assert data["low_confidence"]["share_inside_envelope_low_confidence"] == round(float((wet & low & out_of_channel).sum()) / float((wet & low).sum()), 3)
    assert data["low_confidence"]["share_inside_envelope_other"] == round(float((wet & ~low & out_of_channel).sum()) / float((wet & ~low).sum()), 3)
    # Residents inside the envelope by two rules: the population raster's own cells by their centre (the overlay's stated
    # exposure definition), and the replay's 10 m cells outside mapped channels. The model's figure follows the second.
    lon0, lat0, cell, cells = synthetic["population_grid"]
    clip_lonlat = to_lonlat(synthetic["clip_utm"])
    rows, cols = np.indices(cells.shape)
    centre_inside = shapely.contains_xy(clip_lonlat, lon0 + (cols + 0.5) * cell, lat0 - (rows + 0.5) * cell)
    by_centre = round(float(np.where(cells < 0, 0.0, cells)[centre_inside].sum()))
    assert centre_inside.sum() > 40 and by_centre == 2 * int((centre_inside & (cells > 0)).sum())
    assert data["residents"] == {"residents_in_envelope": by_centre, "residents_in_envelope_replay_rule": round(float(out_of_channel.sum()) * 0.25),
                                 "model_residents_in_water": round(float(wet.sum()) * 0.25), "model_stage": "modelled_peak"}
    assert data["residents"]["residents_in_envelope"] != data["residents"]["residents_in_envelope_replay_rule"]
    assert not any("resident" in key for row in data["by_tambon"] for key in row)


def test_cell_centre_residents_counts_whole_population_cells_and_treats_missing_cells_as_empty(stage, synthetic: dict, tmp_path: Path) -> None:
    lon0, lat0, cell, _ = synthetic["population_grid"]
    # Three whole cells and a sliver of a fourth, whose centre is outside: three cells of two residents count.
    three = box(lon0 + 10 * cell, lat0 - 6 * cell, lon0 + 13.4 * cell, lat0 - 5 * cell)
    assert stage.cell_centre_residents(synthetic["population"], three) == 6
    # The raster's first row holds no data: a clip over it counts nobody there, and a clip beyond the raster counts nobody at all.
    assert stage.cell_centre_residents(synthetic["population"], box(lon0, lat0 - 2 * cell, lon0 + 4 * cell, lat0 + 3 * cell)) == 2 * 4
    assert stage.cell_centre_residents(synthetic["population"], box(lon0 - 1, lat0 + 1, lon0 - 0.9, lat0 + 1.1)) == 0
    assert stage.cell_centre_residents(synthetic["population"], Polygon()) == 0


def test_stage_states_the_replays_own_residents_figure_or_stops(stage) -> None:
    assert stage.model_residents({"id": "modelled_peak"}, 16_061) == 16_061
    assert stage.model_residents({"id": "modelled_peak", "model_residents_in_water": 16_060}, 16_061) == 16_060
    with pytest.raises(ValueError, match="the replay states 15000 residents in water at modelled_peak, but the mask holds 16061"):
        stage.model_residents({"id": "modelled_peak", "model_residents_in_water": 15_000}, 16_061)


def test_stage_writes_three_files_with_licence_credit_and_change_notice(stage, record: dict, synthetic: dict, tmp_path: Path) -> None:
    out = tmp_path / "out" / "r4"
    arguments = dict(rights=record, rights_record={"path": RIGHTS_BASIS_4009_PATH.as_posix(), "sha256": file_sha256(RECORD_PATH), "confirmed_on": "2026-10-02"},
                     study_id="mae-sai-2024-flood-timeline", revision="r4", generated_at="2026-10-02T18:00:00+07:00",
                     href_prefix="/studies/mae-sai-2024-timeline/r4/", bounds=[[20.25, 99.8], [20.49, 100.04]], raster_cell_m=14.9968,
                     worldpop_source="WorldPop 2020", sources=SOURCES, clip_geometry_thai="ตำบลทดสอบสองตำบล")
    references = stage.write_files(synthetic["data"], out, **arguments)
    assert sorted(path.name for path in (out / "unosat4009").iterdir()) == ["LICENSE", "envelope.json", "envelope.png"]
    assert list(out.iterdir()) == [out / "unosat4009"]  # Nothing is written beside the product's own folder.
    for key, name in (("raster", "envelope.png"), ("statistics", "envelope.json"), ("licence", "LICENSE")):
        data = (out / "unosat4009" / name).read_bytes()
        # The manifest gets the address, the hash and the size of each file and nothing else.
        assert references[key] == {"href": f"/studies/mae-sai-2024-timeline/r4/unosat4009/{name}", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        assert b"\r" not in data or name == "envelope.png"
    document = json.loads((out / "unosat4009" / "envelope.json").read_text(encoding="utf-8"))
    assert document_problems(document, licence_name="CC BY-SA 4.0", credit=CREDIT) == []
    template = record["change_notice"]["template"]
    assert document["change_notice"] == fill_change_notice(template, clip_geometry="two test subdistricts", repair_method="make_valid", repair_count=1,
                                                           source_crs="EPSG:4326", target_crs="EPSG:3857", cell_size_m="about 15")
    assert document["comparison"]["change_notice"].startswith(fill_change_notice(
        template, clip_geometry="two test subdistricts", repair_method="make_valid", repair_count=1, source_crs="EPSG:4326", target_crs=UTM, cell_size_m="10"))
    assert (document["generated_at"], document["source_timestamp"], document["confidence"]) == ("2026-10-02T18:00:00+07:00", "2024-08-01/2024-10-22", "low")
    assert document["licence"]["name"] == "CC BY-SA 4.0" and document["credit"] == CREDIT and document["map_credit"] == "UNOSAT and GISTDA · CC BY-SA 4.0"
    assert document["raster"]["sha256"] == references["raster"]["sha256"] and document["raster"]["cell_size_m"] == 15.0
    assert document["standard_sentence"] == stage.STANDARD_SENTENCE and "FloodGuard did not validate it" in document["standard_sentence"]
    # The other inputs of the statistics file keep their own licences and credits; a source the bake does not list stops the stage.
    assert [(item["id"], item["licence"], item["attribution"]) for item in document["other_inputs"]] == [
        (source["id"], source["licence"], source["attribution"]) for source in (SOURCES[0], SOURCES[2], SOURCES[3])]
    assert all(item["used_for"] == stage.OTHER_INPUT_USE[item["id"]]["en"] and item["name"] and item["timestamp"] for item in document["other_inputs"])
    assert "osm" not in [item["id"] for item in document["other_inputs"]] and "not legal advice" in document["other_inputs_note"]
    with pytest.raises(ValueError, match=r"the bake lists no source line for: \['worldpop'\]"):
        stage.write_files(synthetic["data"], tmp_path / "no-credit" / "r4", **{**arguments, "sources": [SOURCES[0], SOURCES[1], SOURCES[3]]})
    assert not (tmp_path / "no-credit").exists()
    # Two counts of residents, each with its rule.
    residents = document["comparison"]["residents"]
    assert residents["rule"] == stage.RESIDENTS_RULE and "whose centre lies inside" in residents["rule"] and "planning overlay" in residents["rule"]
    assert residents["replay_rule"] == stage.RESIDENTS_REPLAY_RULE and "outside mapped channels" in residents["replay_rule"]
    assert "residents_in_envelope_replay_rule, not residents_in_envelope, beside model_residents_in_water" in residents["rules_note"]
    licence = (out / "unosat4009" / "LICENSE").read_text(encoding="utf-8")
    for needle in (CREDIT, "Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)", record["licence"]["legal_code_url"],
                   document["change_notice"], document["comparison"]["change_notice"], record["archive"]["sha256"], "not legal advice and not an official warning",
                   *(source["attribution"] for source in (SOURCES[0], SOURCES[2], SOURCES[3])), "CC BY 4.0", "CC BY-IGO", "Copernicus DEM licence"):
        assert needle in licence, needle
    assert SOURCES[1]["attribution"] not in licence
    # The Thai half says what was changed in Thai, with this file's own values, before the English notice as published.
    thai = licence.split("-" * 80)[1]
    for needle in ("FloodGuard เปลี่ยนแปลงดังนี้: ตัดตามขอบเขตอำเภอแม่สาย (ตำบลทดสอบสองตำบล) ซ่อมแซมรูปทรงเรขาคณิต (make_valid ซ่อมแซม 1 ส่วน) "
                   "แปลงระบบพิกัดจาก EPSG:4326 เป็น EPSG:3857 และแปลงเป็นราสเตอร์ขนาดเซลล์ ประมาณ 15 ม. แหล่งข้อมูล: " + CREDIT + ", CC BY-SA 4.0",
                   "แปลงระบบพิกัดจาก EPSG:4326 เป็น EPSG:32647 และแปลงเป็นราสเตอร์ขนาดเซลล์ 10 ม. แหล่งข้อมูล: " + CREDIT + ", CC BY-SA 4.0 จากนั้นนับจำนวนเซลล์"):
        assert needle in thai and needle not in licence.split("-" * 80)[0], needle
    assert "{" not in licence
    # Written again from the same data, the three files are byte for byte the same.
    again = stage.write_files(synthetic["data"], tmp_path / "again" / "r4", **arguments)
    assert again == references


def test_thai_change_notice_template_fills_the_same_placeholders_as_the_rights_record(stage, record: dict) -> None:
    placeholders = lambda text: sorted(re.findall(r"\{([a-z_]+)\}", text))  # noqa: E731
    assert placeholders(stage.CHANGE_NOTICE_THAI) == placeholders(record["change_notice"]["template"])
    assert len(placeholders(stage.CHANGE_NOTICE_THAI)) == 6
    # The English template ends with the credit and the licence; the Thai one gets them appended as published.
    assert record["change_notice"]["template"].endswith(f"Source: {CREDIT}, CC BY-SA 4.0.") and stage.CHANGE_NOTICE_THAI.endswith("แหล่งข้อมูล: ")
    assert set(stage.OTHER_INPUT_USE) == {"copernicus-dem", "worldpop", "cod-ab"}
    assert all(use["en"].strip() and re.search(r"[\u0e00-\u0e7f]", use["th"]) for use in stage.OTHER_INPUT_USE.values())
    assert stage.LICENCE_THAI["other_inputs_used_for"] == {key: use["th"] for key, use in stage.OTHER_INPUT_USE.items()}


# --- Rights gate ------------------------------------------------------------------------------------------------


def test_stage_refuses_an_unconfirmed_rights_record_before_it_reads_or_writes_anything(stage, record: dict, synthetic: dict, tmp_path: Path) -> None:
    """GATE: the files are allowed only because the record says confirmed. Seeded as pending, the stage refuses."""
    pending = pending_copy(record)
    tracked: list[Path] = []
    grid_ = synthetic["statistics"]
    with pytest.raises(RightsNotConfirmedError, match="not confirmed by the owners"):
        stage.season_envelope(tmp_path / "no-such-root", pending, [], statistics_grid=grid_, raster_grid=synthetic["raster"], codes=synthetic["codes"],
                              zones=synthetic["zones"], tambon_ids=["A", "B"], low_confidence=synthetic["low_confidence"], residents=synthetic["residents"],
                              population=synthetic["population"], channel_code=0, never_code=255, hand_step_m=0.05,
                              stages=[{"id": "modelled_peak", "model_stage_m": 3.5, "model_extent": "x"}],
                              clip_source="x", track=lambda path: tracked.append(Path(path)) or path)
    assert tracked == []  # The archive was not even looked for.
    out = tmp_path / "pending-out" / "r4"
    with pytest.raises(RightsNotConfirmedError, match="must stay out of public files"):
        stage.write_files(synthetic["data"], out, rights=pending, rights_record={"path": "x", "sha256": "0" * 64, "confirmed_on": None},
                          study_id="s", revision="r4", generated_at="2026-10-02T18:00:00+07:00", href_prefix="/studies/x/r4/", bounds=[[0, 0], [1, 1]],
                          raster_cell_m=15.0, worldpop_source="WorldPop 2020", sources=SOURCES, clip_geometry_thai="x")
    assert not out.exists()
    # A record that covers another layer, or another licence, stops the stage too.
    other_layer = copy.deepcopy(record)
    other_layer["product"]["layer_in_scope"] = "CHIANGRAI_20241022_FloodExtent"
    with pytest.raises(ValueError, match="the rights record covers CHIANGRAI_20241022_FloodExtent"):
        stage.season_envelope(tmp_path / "no-such-root", other_layer, [], statistics_grid=grid_, raster_grid=synthetic["raster"], codes=synthetic["codes"],
                              zones=synthetic["zones"], tambon_ids=["A", "B"], low_confidence=synthetic["low_confidence"], residents=synthetic["residents"],
                              population=synthetic["population"], channel_code=0, never_code=255, hand_step_m=0.05,
                              stages=[{"id": "modelled_peak", "model_stage_m": 3.5, "model_extent": "x"}], clip_source="x")
    other_licence = copy.deepcopy(record)
    other_licence["licence"]["name"] = "CC BY 4.0"
    with pytest.raises(ValueError, match="cannot be published"):
        stage.write_files(synthetic["data"], out, rights=other_licence, rights_record={"path": "x", "sha256": "0" * 64, "confirmed_on": "2026-10-02"},
                          study_id="s", revision="r4", generated_at="2026-10-02T18:00:00+07:00", href_prefix="/studies/x/r4/", bounds=[[0, 0], [1, 1]],
                          raster_cell_m=15.0, worldpop_source="WorldPop 2020", sources=SOURCES, clip_geometry_thai="x")
    assert not out.exists()


# --- The committed files --------------------------------------------------------------------------------------------


def test_committed_files_carry_licence_credit_change_notice_timestamps_confidence_and_assumptions(stage, record: dict, manifest: dict, document: dict, folder: Path) -> None:
    assert sorted(path.name for path in folder.iterdir()) == ["LICENSE", "envelope.json", "envelope.png"]
    assert document_problems(document, licence_name=record["licence"]["name"], credit=record["required_attribution_text"]) == []
    assert (document["schema"], document["id"], document["lane"], document["revision"]) == ("floodguard.season_envelope.v1", "unosat-4009", "SCN-ENV", manifest["revision"])
    assert document["label"] == "Scenario (SCN-ENV): 2024 season envelope" == manifest["season_envelope"]["label"]
    assert document["caption"] == manifest["season_envelope"]["caption"] and "not an observation for any replay day" in document["caption"]
    assert document["not_an_observation_for_any_replay_day"] is True
    # Licence, credit and a change notice built from the rights record's template with this file's own values.
    assert document["licence"] == {key: record["licence"][key] for key in ("name", "full_name", "spdx_id", "url", "legal_code_url")}
    assert document["licence"]["name"] == "CC BY-SA 4.0" and document["credit"] == CREDIT == record["required_attribution_text"]
    assert document["map_credit"] == "UNOSAT and GISTDA · CC BY-SA 4.0" == manifest["season_envelope"]["map_credit"]
    assert credit_holders(document["credit"]) == "UNOSAT and GISTDA" and document["map_credit"].startswith(credit_holders(document["credit"]))
    # The standard sentence ships in both files: the caption under the map shows it whenever the layer is visible.
    assert document["standard_sentence"] == manifest["season_envelope"]["standard_sentence"] == (
        "Unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; Field_Validation=0), used as provided under CC BY-SA 4.0. "
        "FloodGuard did not validate it.")
    # The statistics file names its other inputs with the licences and credits the manifest gives them.
    by_id = {source["id"]: source for source in manifest["sources"]}
    assert [item["id"] for item in document["other_inputs"]] == ["copernicus-dem", "worldpop", "cod-ab"]
    for item in document["other_inputs"]:
        assert {key: item[key] for key in ("name", "licence", "attribution", "timestamp")} == {key: by_id[item["id"]][key] for key in ("name", "licence", "attribution", "timestamp")}
        assert item["used_for"] == stage.OTHER_INPUT_USE[item["id"]]["en"]
    assert {item["licence"] for item in document["other_inputs"]} == {"Copernicus DEM licence (free, attribution)", "CC BY 4.0", "CC BY-IGO"}
    assert document["other_inputs_note"] == stage.OTHER_INPUTS_NOTE
    repair = document["changes"]["repair"]
    assert document["change_notice"] == fill_change_notice(
        record["change_notice"]["template"], clip_geometry=document["changes"]["clip_geometry"], repair_method=repair["method"],
        repair_count=repair["parts_repaired"], source_crs="EPSG:4326", target_crs="EPSG:3857", cell_size_m="about 15")
    assert document["comparison"]["change_notice"].startswith(fill_change_notice(
        record["change_notice"]["template"], clip_geometry=document["changes"]["clip_geometry"], repair_method=repair["method"],
        repair_count=repair["parts_repaired"], source_crs="EPSG:4326", target_crs=UTM, cell_size_m="10"))
    assert document["changes"]["clip_geometry"] == "the eight subdistricts of HDX Thailand COD-AB v01"
    # make_valid was run and the repair count recorded: the layer holds invalid parts, a few of them in the district.
    assert (repair["method"], repair["source_parts"], repair["source_parts_invalid"], repair["parts_meeting_district"], repair["parts_repaired"]) == (
        "make_valid", 896, 42, 86, 3)
    # Timestamps, confidence and assumptions (AGENTS.md), and the non-operational flags.
    assert document["generated_at"] == manifest["generated_at"] and document["source_timestamp"] == "2024-08-01/2024-10-22" == document["season_window"]
    assert document["confidence"] == "low" and document["confidence_reason"]
    assert any("30 m surface model raises the ground in built-up areas, so modelled water and residents in town are likely underestimated" in line
               for line in document["assumptions"])
    assert any("Field_Validation=0" in line for line in document["assumptions"]) and any("not the water of 9 to 19 September" in line for line in document["assumptions"])
    assert (document["official_warning"], document["operational_status"], document["can_feed_decision_layer"]) == (False, "non_operational", False)
    # The source is the archive the rights record names, and the record is named by path and by hash.
    assert document["source"]["archive"] == {key: record["archive"][key] for key in ("file_name", "sha256", "bytes")}
    assert (document["source"]["layer"], document["source"]["field_validation"]) == (stage.LAYER, 0)
    assert (document["source"]["layer_name_ends"], document["source"]["product_described_to"]) == ("2024-10-12", "2024-10-22")
    assert document["rights_record"] == {"path": RIGHTS_BASIS_4009_PATH.as_posix(), "sha256": file_sha256(RECORD_PATH), "confirmed_on": "2026-10-02"}
    # No score and no action class anywhere in the file.
    assert not re.search(r"fpps|action_class|priority_score", json.dumps(document), re.IGNORECASE)


def test_committed_raster_is_a_one_bit_png_on_the_water_grid(manifest: dict, document: dict, folder: Path) -> None:
    data = (folder / "envelope.png").read_bytes()
    assert (hashlib.sha256(data).hexdigest(), len(data)) == (document["raster"]["sha256"], document["raster"]["bytes"])
    assert manifest["season_envelope"]["files"]["raster"] == {"href": manifest["season_envelope"]["files"]["raster"]["href"], "sha256": document["raster"]["sha256"], "bytes": len(data)}
    assert (data[24], data[25]) == (1, 0)
    size = (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))
    assert size == (manifest["hand"]["width"], manifest["hand"]["height"]) == (document["raster"]["width"], document["raster"]["height"])
    assert document["raster"]["bounds"] == manifest["bounds"] and document["raster"]["bit_depth"] == 1
    mask = np.asarray(PIL_Image.open(io.BytesIO(data)))
    assert mask.dtype == bool
    # About 15 m cells: the raster holds the district's envelope (the statistics count it on the 10 m grid).
    assert mask.sum() * document["raster"]["cell_size_m"] ** 2 / 1e6 == pytest.approx(document["area"]["district_km2"], abs=0.5)
    assert len(data) < 25_000


def test_committed_licence_notice_is_bilingual_and_names_what_was_changed(record: dict, document: dict, folder: Path) -> None:
    data = (folder / "LICENSE").read_bytes()
    assert b"\r" not in data and data.endswith(b"\n")
    english, thai = data.decode("utf-8").split("-" * 80)
    for half in (english, thai):
        for needle in ("envelope.png", "envelope.json", "LICENSE", CREDIT, "Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)",
                       record["licence"]["url"], record["licence"]["legal_code_url"], document["change_notice"], document["comparison"]["change_notice"],
                       record["archive"]["sha256"], "CHIANGRAI_20240801_20241012_AccumulatedFlood",
                       *(f"- {item['name']}" for item in document["other_inputs"]), *(item["attribution"] for item in document["other_inputs"]),
                       "CC BY 4.0", "CC BY-IGO", "Copernicus DEM licence (free, attribution)"):
            assert needle in half, needle
    # What FloodGuard changed is stated in Thai in the Thai half (before the English notice as published), with the file's own values.
    repair = document["changes"]["repair"]["parts_repaired"]
    thai_raster = (f"FloodGuard เปลี่ยนแปลงดังนี้: ตัดตามขอบเขตอำเภอแม่สาย (ตำบลทั้งแปดตาม HDX Thailand COD-AB v01) ซ่อมแซมรูปทรงเรขาคณิต (make_valid ซ่อมแซม {repair} ส่วน) "
                   f"แปลงระบบพิกัดจาก EPSG:4326 เป็น EPSG:3857 และแปลงเป็นราสเตอร์ขนาดเซลล์ ประมาณ 15 ม. แหล่งข้อมูล: {CREDIT}, CC BY-SA 4.0")
    assert thai_raster in thai and thai.index(thai_raster) < thai.index(document["change_notice"]) and thai_raster not in english
    assert "เป็น EPSG:32647 และแปลงเป็นราสเตอร์ขนาดเซลล์ 10 ม." in thai and "จากนั้นนับจำนวนเซลล์และเทียบกับน้ำจากแบบจำลองของการย้อนดู เพื่อจัดทำตารางนี้" in thai
    # Each input besides the product is listed with what it gave the statistics file, in both languages.
    assert "7. Other inputs (their own credits and licences)" in english and "8. Limits" in english
    assert "7. ข้อมูลนำเข้าอื่น (มีเครดิตและสัญญาอนุญาตของตนเอง)" in thai and "8. ข้อจำกัด" in thai
    assert all(f"Used for: {item['used_for']}" in english for item in document["other_inputs"])
    assert thai.count("ใช้สำหรับ: ") == len(document["other_inputs"]) == 3 and document["other_inputs_note"] in english
    assert "ShareAlike" in english and "not legal advice and not an official warning" in english and "plausibility comparison, not a validation" in english
    assert re.search(r"[฀-๿]", thai) and "ไม่ใช่การเตือนภัยอย่างเป็นทางการ" in thai
    # A Buddhist-era year always carries its CE year.
    assert not re.search(r"25[67]\d(?! \(20\d\d\))", thai)
    assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/](?!/)|/Users/|\\Users\\|%20", data.decode("utf-8"))


def test_committed_statistics_reproduce_the_scouts_values(manifest: dict, document: dict) -> None:
    comparison = document["comparison"]
    assert comparison["role"] == COMPARISON_ROLE == "season_envelope_plausibility"
    assert comparison["title"] == "Season envelope comparison (scenario; plausibility, not validation)"
    assert comparison["use"].startswith("Plausibility against a season envelope, not a validation.")
    peak, window = comparison["district"]
    # District, at the 3.5 m peak: the scouts measured 0.483, 0.605 and 0.704.
    assert (peak["id"], peak["model_stage_m"]) == ("modelled_peak", 3.5)
    assert (peak["agreement_iou"], peak["containment_model_in_envelope"], peak["containment_envelope_in_model"]) == (0.483, 0.605, 0.704)
    # At the largest modelled extent inside 13-19 Sep (2.65 m): the scouts measured an IoU of 0.458.
    assert (window["id"], window["model_stage_m"]) == ("largest_extent_13_19_sep", 2.65)
    assert window["agreement_iou"] == pytest.approx(0.458, abs=0.002)
    # The model side is the replay's own water: the peak day and the size check's window.
    assert peak["model_km2"] == pytest.approx(max(day["stats"]["flooded_km2"] for day in manifest["days"]), abs=0.01)
    unosat_3991 = next(check for check in manifest["external_checks"] if check["id"] == "unosat-3991")
    assert (window["model_stage_m"], round(window["model_km2"], 1)) == (unosat_3991["model_stage_m"], unosat_3991["model_km2"])
    # Per subdistrict: the scouts' range across the six with envelope water was 0.38 to 0.74.
    by_tambon = {TAMBON_NAMES[row["tambon_id"]]: row for row in comparison["by_tambon"]}
    assert len(by_tambon) == 8
    assert {name: round(by_tambon[name]["agreement_iou"], 2) for name in ("Pong Ngam", "Si Mueang Chum", "Ban Dai", "Mae Sai", "Pong Pha", "Ko Chang")} == {
        "Pong Ngam": 0.74, "Si Mueang Chum": 0.65, "Ban Dai": 0.48, "Mae Sai": 0.43, "Pong Pha": 0.4, "Ko Chang": 0.38}
    assert by_tambon["Huai Khrai"]["envelope_km2"] == 0.0 and by_tambon["Huai Khrai"]["containment_envelope_in_model"] is None
    # Where the two differ most: envelope water the model lacks in Ko Chang and the town; modelled water outside it in Ban Dai and Pong Pha.
    lacks = [TAMBON_NAMES[tid] for tid in comparison["disagreement"]["envelope_water_the_model_lacks"]]
    outside = [TAMBON_NAMES[tid] for tid in comparison["disagreement"]["modelled_water_outside_the_envelope"]]
    assert (lacks[:2], outside[:2]) == (["Ko Chang", "Mae Sai"], ["Ban Dai", "Pong Pha"])
    # Low-confidence modelled water: the scouts measured 59.4% inside the envelope, against 60.5% for all modelled water.
    low = comparison["low_confidence"]
    assert low["share_inside_envelope_low_confidence"] == pytest.approx(0.594, abs=0.002)
    assert low["share_inside_envelope_other"] == pytest.approx(0.608, abs=0.002)
    assert low["low_confidence_model_km2"] + low["other_model_km2"] == pytest.approx(peak["model_km2"], abs=0.02)
    assert low["low_confidence_model_km2"] == pytest.approx(manifest["hand"]["low_confidence_share"]["low_confidence_km2"], abs=0.06)
    # The figures add up: the rows of the subdistricts give the district row, and the envelope side leaves channel cells out.
    for key in ("model_km2", "envelope_km2", "overlap_km2"):
        assert sum(row[key] for row in comparison["by_tambon"]) == pytest.approx(peak[key], abs=0.05), key
    area = document["area"]
    assert peak["envelope_km2"] == pytest.approx(area["district_km2"] - area["on_mapped_channels_km2"], abs=0.011)
    assert sum(row["envelope_km2"] for row in area["by_tambon"].values()) == pytest.approx(area["district_km2"], abs=0.01)
    # The scouts' two clips gave 77.73 and 77.61 km2 with two geometries; the declared geometry (COD-AB) gives 77.73.
    assert area["district_vector_km2"] == 77.73 and area["district_km2"] == pytest.approx(77.73, abs=0.02)
    for row in (peak, window, *comparison["by_tambon"]):
        assert row["overlap_km2"] <= min(row["model_km2"], row["envelope_km2"]) + 1e-9
        assert row["union_km2"] == pytest.approx(row["model_km2"] + row["envelope_km2"] - row["overlap_km2"], abs=0.011)


def test_committed_statistics_give_residents_as_a_district_total_and_no_land_cover_split(manifest: dict, document: dict) -> None:
    residents = document["comparison"]["residents"]
    assert residents["scope"] == "District total only." and "WorldPop" in residents["source"] and "not a census count" in residents["rule"]
    # The model's figure is the replay's own peak. The envelope's residents are counted twice, each count with its rule:
    # by the planning overlay's stated exposure definition (WorldPop 2020 cells of about 100 m, by their centre), which
    # the scouts measured at about 17,960, and by the replay's own rule, to set beside the model's figure.
    assert residents["model_residents_in_water"] == max(day["stats"]["people_in_water"] for day in manifest["days"])
    assert (residents["residents_in_envelope"], residents["residents_in_envelope_replay_rule"]) == (17_927, 17_344)
    assert residents["residents_in_envelope"] == pytest.approx(17_960, abs=50)
    assert "WorldPop 2020 cells (about 100 m) whose centre lies inside the clipped envelope" in residents["rule"] and "planning overlay" in residents["rule"]
    assert "the replay's exposure rule" in residents["replay_rule"] and "outside mapped channels" in residents["replay_rule"]
    assert "not a census count" in residents["replay_rule"] and residents["rules_note"]
    assert not re.search(r"resident", json.dumps(document["comparison"]["by_tambon"]) + json.dumps(document["area"]))
    # No land-cover map is among the bake's inputs, so the built-up against cropland split is left out, and the file says so.
    assert document["comparison"]["land_cover"] == {"computed": False, "reason": ("Not computed: no land-cover map is among the replay's inputs, so the share of "
                                                                               "the envelope reached is not split by built-up land and cropland.")}
    assert not [row["path"] for row in manifest["input_sha256"] if re.search(r"worldcover|land.?cover", row["path"], re.IGNORECASE)]
    assert not re.search(r"built_up|cropland_share|worldcover", json.dumps(document["comparison"]), re.IGNORECASE)
    # The recorded rule on tuning.
    assert document["comparison"]["tuning"] == {
        "relation": "computed_after_keyframes_final",
        "statement": "The comparison was computed after the stage keyframes were final and was not used for tuning.",
        "rule": "No keyframe or elevation change is tuned to product 4009 afterwards; if one is, this comparison is relabelled as calibration."}


def test_committed_4009_text_says_plausibility_and_never_the_words_it_must_not(document: dict, folder: Path) -> None:
    rules = load_rules(WEB / "src" / "lib" / "replay-wording-rules.json")
    texts = [*json_strings(document), ("LICENSE", (folder / "LICENSE").read_text(encoding="utf-8"))]
    assert [finding.describe() for source, text in texts for finding in find_violations(text, rules, source)] == []
    flat = " ".join(text for _, text in texts)
    assert "Plausibility against a season envelope, not a validation." in flat
    assert "(scenario; plausibility, not validation)" in flat
    for banned in (r"\bprecision\b", r"\brecall\b", r"\baccuracy\b", r"\bvalidated\b", r"corroborat", r"September extent", r"GISTDA's map", r"too (low|high)"):
        assert not re.search(banned, flat.replace("Unvalidated", "").replace("unvalidated", ""), re.IGNORECASE), banned
    # The keys follow the same rule: the three ratios are named for what they are.
    keys = set(re.findall(r'"([A-Za-z_]+)":', json.dumps(document)))
    assert {"agreement_iou", "containment_model_in_envelope", "containment_envelope_in_model"} <= keys
    assert not [key for key in keys if re.search(r"precision|recall|accura|corroborat", key)]


def test_no_4009_figure_is_in_the_manifest_or_the_export_pack(manifest: dict, document: dict, folder: Path) -> None:
    # timeline.json names the three files by address, hash and size, and repeats no figure of theirs.
    files = manifest["season_envelope"]["files"]
    assert {key: sorted(value) for key, value in files.items()} == {"raster": ["bytes", "href", "sha256"], "statistics": ["bytes", "href", "sha256"],
                                                                    "licence": ["bytes", "href", "sha256"]}
    text = json.dumps({key: value for key, value in manifest.items() if key not in ("input_sha256", "tambon_histograms", "population", "rainfall")}, ensure_ascii=False)
    comparison = document["comparison"]
    figures = [document["area"]["district_km2"], document["area"]["district_vector_km2"], comparison["district"][0]["envelope_km2"],
               comparison["district"][0]["overlap_km2"], comparison["district"][0]["agreement_iou"], comparison["district"][0]["containment_model_in_envelope"],
               comparison["district"][0]["containment_envelope_in_model"], comparison["district"][1]["agreement_iou"], comparison["residents"]["residents_in_envelope"],
               comparison["low_confidence"]["share_inside_envelope_low_confidence"], *(row["envelope_km2"] for row in document["area"]["by_tambon"].values() if row["envelope_km2"] > 1)]
    for figure in figures:
        assert not re.search(rf"(?<![0-9.]){re.escape(str(figure))}(?![0-9])", text), figure
    # Nor does the manifest carry the comparison's field names where it speaks of the envelope ("model_agreement_iou"
    # elsewhere belongs to the Sentinel-2 water check).
    check = next(item for item in manifest["external_checks"] if item["role"] == COMPARISON_ROLE)
    assert not re.search(r"agreement_iou|containment_|km2|residents_in", json.dumps([manifest["season_envelope"], check]))
    assert "containment_" not in text and "residents_in_envelope" not in text
    # No file of the export pack comes from the product, names it as a source or repeats one of its figures.
    pack = manifest["exports"]
    assert not [file["name"] for file in pack["files"] if re.search(r"unosat|4009|envelope", file["name"] + file["href"], re.IGNORECASE)]
    assert not [file["name"] for file in pack["files"] if "unosat-4009" in file["source_ids"] or file["licence"] != "ODbL 1.0"]
    exports = manifest_path().parent / "exports"
    for path in sorted(exports.iterdir()):
        body = path.read_text(encoding="utf-8-sig")
        if path.name == replay_exports.SUMMARY_NAME:
            # The per-subdistrict summary says, in one sentence, where its subdistrict's envelope comparison is and why it is not
            # copied (another licence). It names no figure and no field of that comparison: the checks below still apply.
            assert body.count(replay_exports.ENVELOPE_POINTER_WHY["en"]) >= 1
            body = body.replace(replay_exports.ENVELOPE_POINTER_WHY["en"], "")
            summary = json.loads(path.read_text(encoding="utf-8"))
            assert {key for record in summary["records"] for key in record["season_envelope_comparison"]} == {"lane", "stage", "file", "entry"}
        assert not re.search(r"unosat4009|season envelope|agreement_iou|containment_", body, re.IGNORECASE), path.name
        assert "nothing from UNOSAT/GISTDA product 4009 is in this file" in body or path.name == "README_licences.txt", path.name
    assert "Nothing from UNOSAT/GISTDA product 4009." in (exports / "README_licences.txt").read_text(encoding="utf-8")
    assert not (exports / "unosat4009").exists() and sorted(path.name for path in folder.iterdir()) == ["LICENSE", "envelope.json", "envelope.png"]


def test_licence_file_is_in_the_offline_list_within_the_precache_budget(manifest: dict, folder: Path) -> None:
    """The offline copy is the manifest plus every ``{href, sha256, bytes}`` record outside the export pack
    (``manifestAssets`` in ``flood-timeline.ts`` and ``timelineManifestAssets`` in ``case-replay-inventory.mjs``)."""
    found: dict[str, dict] = {}

    def visit(value) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if isinstance(value.get("href"), str) and re.fullmatch(r"[a-f0-9]{64}", str(value.get("sha256", ""))) and isinstance(value.get("bytes"), int):
                found.setdefault(value["href"], value)
            for item in value.values():
                visit(item)

    visit({key: value for key, value in manifest.items() if key != "exports"})
    base = f"/studies/mae-sai-2024-timeline/{manifest['revision']}/"
    envelope = sorted(href[len(base):] for href in found if href.startswith(f"{base}unosat4009/"))
    assert envelope == ["unosat4009/LICENSE", "unosat4009/envelope.json", "unosat4009/envelope.png"]
    for href in (f"{base}unosat4009/{name}" for name in ("LICENSE", "envelope.json", "envelope.png")):
        data = (WEB / "public" / href.lstrip("/")).read_bytes()
        assert (found[href]["sha256"], found[href]["bytes"]) == (hashlib.sha256(data).hexdigest(), len(data))
    # Within the 6.5 MB precache budget, manifest included; the export pack is counted apart.
    total = manifest_path().stat().st_size + sum(record["bytes"] for record in found.values())
    assert total <= PRECACHE_BUDGET_BYTES
    assert f"CASE_REPLAY_BUDGET_BYTES = {PRECACHE_BUDGET_BYTES:_}" in (WEB / "scripts" / "case-replay-inventory.mjs").read_text(encoding="utf-8")
    assert 'CASE_REPLAY_ENVELOPE_FOLDER = "unosat4009"' in (WEB / "scripts" / "case-replay-inventory.mjs").read_text(encoding="utf-8")
    assert not [href for href in found if "/exports/" in href]


# --- The product archive (external data) ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def archive_clip(stage, record: dict) -> dict:
    external = os.environ.get("FLOODGUARD_EXTERNAL_DATA")
    if not external:
        pytest.skip("FLOODGUARD_EXTERNAL_DATA is not set; the product 4009 archive stays outside Git")
    pyogrio = pytest.importorskip("pyogrio")
    layers: list[str] = []
    real = pyogrio.read_dataframe

    def read_dataframe(path, *args, **kwargs):
        layers.append(str(kwargs.get("layer")))
        return real(path, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pyogrio, "read_dataframe", read_dataframe)
        geometry = stage.read_layer(Path(external) / record["archive"]["relative_path"], record["product"]["layer_attributes_checked"])
    admin = json.loads((ROOT / "outputs" / "mae_sai_admin_context.geojson").read_text(encoding="utf-8"))
    tambons = {feature["properties"]["subdistrict_id"]: shape(feature["geometry"]) for feature in admin["features"]}
    clip, repair = stage.district_clip(geometry, list(tambons.values()))
    return {"layers": layers, "clip": clip, "repair": repair, "tambons": tambons}


def test_archive_layer_is_read_alone_and_its_attributes_match_the_record(stage, record: dict, archive_clip: dict) -> None:
    assert archive_clip["layers"] == ["CHIANGRAI_20240801_20241012_AccumulatedFlood"]
    external = Path(os.environ["FLOODGUARD_EXTERNAL_DATA"])
    with pytest.raises(ValueError, match="attributes differ from the rights record"):
        stage.read_layer(external / record["archive"]["relative_path"], {**record["product"]["layer_attributes_checked"], "Field_Validation": 1})


def test_per_tambon_km2_are_within_005_of_a_vector_clip(stage, document: dict, archive_clip: dict) -> None:
    clip, tambons = archive_clip["clip"], archive_clip["tambons"]
    assert archive_clip["repair"] == document["changes"]["repair"]
    table = document["area"]["by_tambon"]
    assert sorted(table) == sorted(tambons)
    largest = 0.0
    for tid, tambon in tambons.items():
        vector_km2 = stage.reproject(clip.intersection(tambon), UTM).area / 1e6
        largest = max(largest, abs(table[tid]["envelope_km2"] - vector_km2))
        assert abs(table[tid]["envelope_km2"] - vector_km2) < 0.05, (tid, table[tid]["envelope_km2"], vector_km2)
        assert table[tid]["tambon_km2"] == pytest.approx(stage.reproject(tambon, UTM).area / 1e6, abs=0.05)
    assert largest < 0.02  # In practice the 10 m grid is within a hundredth of a square kilometre of the vector clip.
    assert document["area"]["district_vector_km2"] == round(stage.reproject(clip, UTM).area / 1e6, 2) == 77.73
