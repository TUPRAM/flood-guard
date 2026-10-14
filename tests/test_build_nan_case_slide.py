"""The pitch slide of the Nan case, drawn from invented inputs: a five-tambon unit raster, result and test record.

Nothing here is a place or a result of the Nan case. The unit raster lies in the open sea (an invented grid in
EPSG:32647), the rows are the invented N1 rows of tests/test_build_n1_brief.py, and no JAXA, GFM or THEOS-2 file is
read or drawn.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pytest

pytest.importorskip("PIL")
rasterio = pytest.importorskip("rasterio")
from PIL import Image  # noqa: E402

from floodguard.wording_lint import find_violations, load_rules, python_strings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
WEST, NORTH, ROWS, COLS = 300_000.0, 801_200.0, 60, 80


def load(name: str, path: Path) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


slide = load("build_nan_case_slide", ROOT / "scripts" / "build_nan_case_slide.py")
fixtures = load("n1_brief_fixtures_for_the_slide", ROOT / "tests" / "test_build_n1_brief.py")
brief = slide.brief


def invented_units() -> np.ndarray:
    """Five invented tambons on a 60 by 80 grid: four quarters and a small one in the middle; 0 around them."""

    values = np.zeros((ROWS, COLS), dtype=np.uint8)
    values[5:30, 5:40] = 1
    values[5:30, 40:75] = 2
    values[30:55, 5:40] = 3
    values[30:55, 40:75] = 4
    values[24:36, 34:46] = 5
    return values


def invented_frame(folder: Path, values: np.ndarray | None = None) -> tuple[Path, Path]:
    """The unit raster in a work folder of the external root, and a frame record naming it (fixture, not a place)."""

    from rasterio.transform import Affine

    raster = folder / "external" / "proposal_execution" / "nan_case_v1" / "frame" / "fx_units_20m.tif"
    raster.parent.mkdir(parents=True, exist_ok=True)
    data = invented_units() if values is None else values
    with rasterio.open(raster, "w", driver="GTiff", width=COLS, height=ROWS, count=1, dtype="uint8", crs="EPSG:32647",
                       transform=Affine(20.0, 0.0, WEST, 0.0, -20.0, NORTH), compress="deflate") as target:
        target.write(data, 1)
    frame = {
        "schema": "floodguard.nan_case_frame.v1", "case_id": "N1", "official_warning": False,
        "operational_status": "non_operational",
        "protocol": {"frame_rules": {"district_names": ["Invented district (fixture, not a place)"]}},
        "units": [{"adm3_pcode": f"FX-N-0{value}", "adm3_name": f"Fixture {value}", "raster_value": value} for value in range(1, 6)],
        "unit_raster": {"path": "<external_data_workspace>/proposal_execution/nan_case_v1/frame/fx_units_20m.tif",
                        "grid": {"west": WEST, "north": NORTH, "rows": ROWS, "cols": COLS, "epsg": 32647, "cell_m": 20},
                        "sha256": hashlib.sha256(raster.read_bytes()).hexdigest()},
    }
    record = folder / "frame_v1.json"
    record.write_text(json.dumps(frame, indent=1) + "\n", encoding="utf-8")
    return record, raster


def inputs(folder: Path, **options: Any) -> tuple[Path, Path, Path, Path]:
    result, test, _record = fixtures.written_inputs(folder / "in", **options)
    frame, raster = invented_frame(folder)
    return result, test, frame, raster


def lookup_and_classes() -> tuple[dict[int, str], dict[str, Any]]:
    frame = {"units": [{"adm3_pcode": f"FX-N-0{value}", "raster_value": value} for value in range(1, 6)]}
    return slide.unit_lookup(frame), slide.classes_of(fixtures.invented_result())


# ---------------------------------------------------------------------------
# The map
# ---------------------------------------------------------------------------


def test_the_map_draws_a_binding_class_solid_and_a_would_be_class_striped() -> None:
    lookup, classes = lookup_and_classes()
    image, info = slide.render_map(invented_units(), lookup, classes, max_size=(350, 300))
    pixels = np.asarray(image)
    assert image.size == (350, 250), "the crop of 50 by 70 cells is scaled to fit the box"
    scale = 350 / 70
    def at(row: int, col: int) -> tuple[int, ...]:
        return tuple(int(value) for value in pixels[int((row - 5) * scale), int((col - 5) * scale)])
    # FX-N-01 is binding B: solid; FX-N-04 is binding E: solid.
    region = pixels[int(2 * scale):int(10 * scale), int(2 * scale):int(10 * scale)].reshape(-1, 3)
    assert {tuple(int(v) for v in pixel) for pixel in region} == {slide.CLASS_RGB["B"]}
    assert at(50, 70) == slide.CLASS_RGB["E"]
    # FX-N-02 is would-be A (class in effect E): stripes of A on a tint of A, never the solid E.
    stripes = {tuple(int(v) for v in pixel) for pixel in pixels[int(2 * scale):int(10 * scale), int(45 * scale):int(55 * scale)].reshape(-1, 3)}
    tint = tuple(int(value * 0.35 + 255 * 0.65) for value in slide.CLASS_RGB["A"])
    assert stripes == {slide.CLASS_RGB["A"], tint}
    # FX-N-05 has no class (fewer residents than the minimum): grey.
    assert at(26, 36) == slide.NO_CLASS_RGB
    # The tambons are outlined, the cells around them stay paper, and each tambon is labelled.
    assert (pixels == np.array(slide.BORDER, dtype=np.uint8)).all(axis=2).sum() > 0
    assert info["units_drawn"] == {"FX-N-01": "binding", "FX-N-02": "would_be", "FX-N-03": "would_be", "FX-N-04": "binding",
                                   "FX-N-05": "no_class"}
    assert info["units_labelled"] == 4 and info["metres_per_pixel"] == pytest.approx(20.0 * 70 / 350)


def test_a_unit_without_a_row_or_a_raster_without_units_is_refused() -> None:
    lookup, classes = lookup_and_classes()
    del classes["FX-N-03"]
    with pytest.raises(slide.SlideError, match="no row for FX-N-03"):
        slide.render_map(invented_units(), lookup, classes)
    with pytest.raises(slide.SlideError, match="holds no unit"):
        slide.render_map(np.zeros((10, 10), dtype=np.uint8), lookup, classes)
    with pytest.raises(slide.SlideError, match="reserved or used twice"):
        slide.unit_lookup({"units": [{"adm3_pcode": "X", "raster_value": 1}, {"adm3_pcode": "Y", "raster_value": 1}]})
    with pytest.raises(slide.SlideError, match="reserved"):
        slide.unit_lookup({"units": [{"adm3_pcode": "X", "raster_value": 255}]})


def test_the_unit_raster_is_found_where_the_frame_record_names_it(tmp_path: Path) -> None:
    record, raster = invented_frame(tmp_path)
    frame = json.loads(record.read_text(encoding="utf-8"))
    assert slide.unit_raster_path(frame, tmp_path / "external") == raster
    assert slide.read_unit_raster(raster, frame).shape == (ROWS, COLS)
    with pytest.raises(slide.SlideError, match="work folder"):
        slide.unit_raster_path({"unit_raster": {"path": "C:/somewhere/units.tif"}}, tmp_path)


# ---------------------------------------------------------------------------
# The words
# ---------------------------------------------------------------------------


def outcome(**options: Any) -> dict[str, Any]:
    return brief.outcome_of_the_test(fixtures.invented_test(**options))


def test_the_words_follow_the_outcome_of_the_test() -> None:
    rows = list(slide.classes_of(fixtures.invented_result()).values())
    passed = outcome()
    assert slide.headline_of(passed) == "Our own radar map met the bar we fixed before the test"
    meaning = slide.meaning_of(passed, rows)
    assert "against another satellite's map" in meaning and "flagged 1.2% of dry hills" in meaning
    assert "2 of 5 tambons here" in meaning and "in town it flagged 33% of the water THEOS-2 shows" in meaning
    cards = slide.cards_of(passed)
    assert cards[0]["big"] == "0.47" and cards[0]["line_1"] == "IoU with JAXA ALOS-2 Flood Proxy Map of 2025-07-28"
    assert cards[0]["tag"].endswith("PASSES") and "95% interval 0.41 to 0.52" in cards[0]["small"]
    assert cards[1]["big"] == "1.2%" and "20,000 answered cells" in cards[1]["small"] and "31 July 2025" in cards[1]["line_2"]
    assert cards[2]["big"] == "33%" and "78% of our flags are THEOS-2 water" in cards[2]["line_2"]
    assert "81% of 118 labelled points" in cards[2]["small"] and "NOT BINDING" in cards[2]["tag"]
    sources, caution = slide.footer_of(passed, "planning_result_n1_nan_v1.json")
    assert "Provided by JAXA" in sources and "no map drawn" in sources
    assert caution.startswith("Agreement with another map, not accuracy.") and "not an official warning" in caution

    failed = outcome(passed=False)
    assert slide.headline_of(failed).startswith("Our own radar map fell short")
    assert slide.meaning_of(failed, rows).startswith("Our map reached IoU 0.31 against another satellite's map, under the bar of 0.40")
    assert slide.cards_of(failed)[0]["tag"].endswith("DOES NOT PASS")
    dry = outcome(dry_passes=False)
    assert slide.meaning_of(dry, rows).startswith("Our map flagged 12% of dry hills, over the bar of 5%")
    not_run = outcome(run=False)
    assert slide.headline_of(not_run).endswith("could not be tested against another map")
    assert slide.cards_of(not_run)[0]["big"] == "n/a"
    fallback = outcome(fallback=True)
    assert "a same-pass map (not independent)" in slide.meaning_of(fallback, rows)
    assert "not independent of our map" in slide.cards_of(fallback)[0]["line_2"]
    assert "Global Flood Monitoring (GFM)" in slide.footer_of(fallback, "x.json")[0]
    assert "Provided by JAXA" not in slide.footer_of(fallback, "x.json")[0]


def test_the_wording_passes_the_shared_lint() -> None:
    def lint(text: str, source: str) -> list[str]:
        # "agreement with another map, not accuracy" is the wording the case asks for; the replay page's rules have
        # no allowance for it, so it is taken out before the rest is checked (as in tests/test_nan_case_m1z.py).
        return [finding.describe() for finding in find_violations(text.replace("not accuracy", ""), RULES, source)]

    strings = python_strings((ROOT / "scripts" / "build_nan_case_slide.py").read_text(encoding="utf-8"))
    assert [finding for text in strings for finding in lint(text, "build_nan_case_slide.py")] == []
    rows = list(slide.classes_of(fixtures.invented_result()).values())
    for options in ({}, {"passed": False}, {"dry_passes": False}, {"run": False}, {"fallback": True}):
        found = outcome(**options)
        texts = [slide.headline_of(found), slide.meaning_of(found, rows), *slide.footer_of(found, "x.json")]
        texts += [value for card in slide.cards_of(found) for value in card.values()]
        assert [finding for text in texts for finding in lint(text, str(options))] == []
        for text in texts:
            for word in ("accurate", "validated", "precision", "recall", "forecast"):
                assert word not in text.lower()


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def test_the_slide_is_one_16_9_png_that_carries_its_record(tmp_path: Path) -> None:
    result, test, frame, raster = inputs(tmp_path)
    out = tmp_path / "out" / "nan_case_slide.png"
    summary = slide.build(result, test, frame, raster, out, generated_at="2026-10-21T00:00:00Z")
    with Image.open(out) as image:
        assert image.size == (1600, 900) and image.mode == "RGB"
        text = dict(image.text)
        pixels = np.asarray(image.convert("RGB"))
    assert text["generated_at_utc"] == "2026-10-21T00:00:00Z" and text["source_timestamp"] == "2025-07-28T11:21:00Z"
    assert text["confidence_class"] == "low" and text["official_warning"] == "false" and text["operational_status"] == "non_operational"
    assert any("not accuracy" in item for item in json.loads(text["assumptions"]))
    made_from = json.loads(text["made_from"])
    assert made_from["unit_raster"]["sha256"] == hashlib.sha256(raster.read_bytes()).hexdigest()
    assert made_from["result_file"]["sha256"] == hashlib.sha256(result.read_bytes()).hexdigest()
    assert made_from["test_record"]["sha256"] == hashlib.sha256(test.read_bytes()).hexdigest()
    assert text["Description"].startswith("Our map met the bar fixed before the test")
    assert summary["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    # The map stands on the left: the binding B and the striped would-be A are drawn there.
    left = pixels[:, :760].reshape(-1, 3)
    colours = {tuple(int(v) for v in pixel) for pixel in left[::7]}
    assert slide.CLASS_RGB["B"] in colours and slide.CLASS_RGB["A"] in colours
    assert slide.CLASS_RGB["B"] not in {tuple(int(v) for v in pixel) for pixel in pixels[150:600, 800:1500].reshape(-1, 3)[::11]}


def test_the_command_line_draws_from_the_external_root_and_refuses_with_code_2(tmp_path: Path,
                                                                                 capsys: pytest.CaptureFixture[str]) -> None:
    result, test, frame, _raster = inputs(tmp_path)
    out = tmp_path / "slide.png"
    arguments = ["--result", str(result), "--test-result", str(test), "--frame-record", str(frame)]
    assert slide.main([*arguments, "--external-root", str(tmp_path / "external"), "--out", str(out)]) == 0 and out.is_file()
    assert slide.main([*arguments, "--out", str(tmp_path / "other.png")]) == 2
    assert "--external-root" in capsys.readouterr().err
    # A fixture is never drawn over the slide of the repository.
    committed = ROOT / slide.SLIDE
    before = committed.read_bytes() if committed.exists() else None
    assert slide.main([*arguments, "--external-root", str(tmp_path / "external")]) == 2
    assert "never drawn over the slide of the repository" in capsys.readouterr().err
    assert (committed.read_bytes() if committed.exists() else None) == before


def test_inputs_that_do_not_belong_together_are_refused(tmp_path: Path) -> None:
    result, test, frame, raster = inputs(tmp_path)
    out = tmp_path / "out.png"
    # Another unit raster than the frame record names.
    other = invented_units()
    other[0, 0] = 3
    _record, moved = invented_frame(tmp_path / "other", other)
    with pytest.raises(slide.SlideError, match="SHA-256 differs"):
        slide.build(result, test, frame, moved, out)
    # A frame of other tambons.
    record = json.loads(frame.read_text(encoding="utf-8"))
    record["units"][4]["adm3_pcode"] = "FX-N-99"
    wrong = tmp_path / "wrong_frame.json"
    wrong.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(slide.SlideError, match="same tambons"):
        slide.build(result, test, wrong, raster, out)
    # A result of case N2, and a path behind the firewall.
    overlay = json.loads(result.read_text(encoding="utf-8"))
    n2 = copy.deepcopy(overlay)
    n2["case"]["case_id"] = "N2"
    n2_path = tmp_path / "n2.json"
    n2_path.write_text(json.dumps(n2), encoding="utf-8")
    with pytest.raises(brief.N1BriefError, match="case N2"):
        slide.build(n2_path, test, frame, raster, out)
    with pytest.raises(brief.N1BriefError, match="never opens it"):
        slide.build(result, test, frame, tmp_path / "jaxa_sealed" / "units.tif", out)
    assert not out.exists()


def test_the_slide_never_names_a_reference_file() -> None:
    source = (ROOT / "scripts" / "build_nan_case_slide.py").read_text(encoding="utf-8")
    for marker in ("jaxa_sealed", "JAXA_2025", "eodc", "water_v2_chip", "chip_00", "IMG_T2V", "held_chip"):
        assert marker not in source
