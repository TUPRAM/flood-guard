"""Tests for the reproducible-bake helpers and the Mae Sai timeline ``--verify`` mode and input receipt.

The helper tests and the committed-receipt tests need no external data. The tests that run the real bake are
skipped unless ``FLOODGUARD_EXTERNAL_DATA`` points at the external data root.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import pytest

from floodguard.bake_receipt import (
    RECEIPT_SCHEMA,
    InputReceipt,
    ReceiptError,
    compare_directories,
    directory_listing,
    input_differences,
    library_versions,
    sha256_file,
    version_differences,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
COMMITTED_RECEIPT = ROOT / "docs" / "mae_sai_timeline_r3_input_receipt.json"
COMMITTED_FOLDER = ROOT / "apps" / "web" / "public" / "studies" / "mae-sai-2024-timeline" / "r3"
LOCAL_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/](?!/)|/Users/|\\Users\\|/home/|%20")

# --- Recording which files Python opens --------------------------------------------------------------

_opened: list[str] | None = None
_hook_installed = False


def _audit(event: str, args: tuple) -> None:
    if _opened is not None and event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        _opened.append(os.fsdecode(args[0]))


@contextmanager
def recorded_opens() -> Iterator[list[str]]:
    """Collect the path of every file Python opens inside the block (``open`` audit events)."""
    global _opened, _hook_installed
    if not _hook_installed:
        sys.addaudithook(_audit)  # Audit hooks cannot be removed; this one is inert outside the block.
        _hook_installed = True
    _opened = []
    try:
        yield _opened
    finally:
        _opened = None


def under(paths: list[str], *roots: Path) -> set[Path]:
    """The opened paths that lie under one of ``roots`` (resolved)."""
    resolved_roots = [root.resolve() for root in roots]
    found = set()
    for raw in paths:
        text = raw[len("/vsizip/"):] if raw.startswith("/vsizip/") else raw
        if ".zip/" in text:  # A GDAL virtual path into an archive: the input is the archive itself.
            text = text[:text.index(".zip/") + 4]
        path = Path(text).resolve()
        if any(path.is_relative_to(root) for root in resolved_roots) and path.is_file():
            found.add(path)
    return found


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


def load_bake():
    for dependency in ("PIL", "pyproj", "rasterio", "scipy", "shapely"):
        pytest.importorskip(dependency)
    return load_script("build_mae_sai_flood_timeline")


# --- InputReceipt -------------------------------------------------------------------------------------


def test_receipt_records_relative_paths_sizes_and_hashes(tmp_path: Path) -> None:
    external, repo = tmp_path / "external data", tmp_path / "repo"
    (external / "dem").mkdir(parents=True)
    (repo / "outputs").mkdir(parents=True)
    (external / "dem" / "tile b.tif").write_bytes(b"bbbb")
    (external / "dem" / "tile a.tif").write_bytes(b"a")
    (repo / "outputs" / "roads.geojson").write_bytes(b"{}")
    receipt = InputReceipt({"external": external, "repo": repo})
    tile = external / "dem" / "tile b.tif"
    assert receipt.track(tile) is tile  # Returned unchanged, so it can wrap the path where the file is opened.
    receipt.track(str(external / "dem" / "tile a.tif"))
    receipt.track(repo / "outputs" / "roads.geojson")
    receipt.track(external / "dem" / ".." / "dem" / "tile b.tif")  # The same file again: recorded once.
    assert receipt.tracked() == [("external", "dem/tile a.tif"), ("external", "dem/tile b.tif"), ("repo", "outputs/roads.geojson")]
    assert tile in receipt and (external / "dem" / "absent.tif") not in receipt and 3 not in receipt
    entries = receipt.entries()
    assert entries == [
        {"root": "external", "path": "dem/tile a.tif", "bytes": 1, "sha256": sha256_file(external / "dem" / "tile a.tif")},
        {"root": "external", "path": "dem/tile b.tif", "bytes": 4, "sha256": sha256_file(tile)},
        {"root": "repo", "path": "outputs/roads.geojson", "bytes": 2, "sha256": sha256_file(repo / "outputs" / "roads.geojson")},
    ]
    assert entries[0]["sha256"] == hashlib.sha256(b"a").hexdigest()
    # Nothing in the receipt names the machine: no absolute path, no drive letter, no backslash.
    assert str(tmp_path) not in json.dumps(entries) and "\\\\" not in json.dumps(entries)


def test_receipt_refuses_inputs_outside_its_roots_and_missing_files(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "elsewhere.tif").write_bytes(b"x")
    receipt = InputReceipt({"external": root})
    with pytest.raises(ReceiptError, match="outside the receipt roots"):
        receipt.track(tmp_path / "elsewhere.tif")
    receipt.track(root / "vanished.tif")
    with pytest.raises(ReceiptError, match="not a file"):
        receipt.entries()
    with pytest.raises(ReceiptError, match="at least one root"):
        InputReceipt({})


def test_receipt_prefers_the_innermost_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    (repo / "data" / "a.bin").write_bytes(b"a")
    (repo / "b.bin").write_bytes(b"b")
    receipt = InputReceipt({"repo": repo, "external": repo / "data"})
    receipt.track(repo / "data" / "a.bin")
    receipt.track(repo / "b.bin")
    assert receipt.tracked() == [("external", "a.bin"), ("repo", "b.bin")]


def test_library_versions_name_the_interpreter_and_tolerate_missing_distributions() -> None:
    versions = library_versions(("pandas", "floodguard-no-such-distribution"))
    assert re.fullmatch(r"\d+\.\d+\.\d+.*", versions["python"])
    assert versions["pandas"]
    assert versions["floodguard-no-such-distribution"] is None
    assert list(versions) == sorted(versions)


# --- Byte comparison ----------------------------------------------------------------------------------


def write_tree(folder: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return folder


def test_compare_directories_reports_identical_different_missing_and_extra_files(tmp_path: Path) -> None:
    committed = write_tree(tmp_path / "committed", {"a.png": b"aaa", "b.json": b"{}", "sub/c.bin": b"c"})
    same = write_tree(tmp_path / "same", {"a.png": b"aaa", "b.json": b"{}", "sub/c.bin": b"c"})
    result = compare_directories(same, committed)
    assert result.matches and result.summary() == "3/3 identical"
    assert result.identical == ["a.png", "b.json", "sub/c.bin"]

    changed = write_tree(tmp_path / "changed", {"a.png": b"aab", "b.json": b"{}", "sub/c.bin": b"cc", "new.bin": b"n"})
    (committed / "only-committed.txt").write_bytes(b"x")
    result = compare_directories(changed, committed)
    assert not result.matches and result.summary() == "1/4 identical"
    assert result.different == ["a.png", "sub/c.bin"]  # Same size or not, any byte difference counts.
    assert result.missing_from_fresh == ["only-committed.txt"]
    assert result.extra_in_fresh == ["new.bin"]
    # An empty committed folder never "matches".
    assert not compare_directories(write_tree(tmp_path / "e1", {}), write_tree(tmp_path / "e2", {})).matches
    listing = directory_listing(committed)
    assert [row["name"] for row in listing] == ["a.png", "b.json", "only-committed.txt", "sub/c.bin"]
    assert listing[0] == {"name": "a.png", "bytes": 3, "sha256": sha256_file(committed / "a.png")}


def test_input_and_version_differences_explain_a_mismatch() -> None:
    recorded = [{"root": "external", "path": "dem.tif", "sha256": "a" * 64}, {"root": "repo", "path": "outputs/x.csv", "sha256": "b" * 64}]
    assert input_differences(recorded, recorded) == []
    fresh = [{"root": "external", "path": "dem.tif", "sha256": "c" * 64}, {"root": "external", "path": "new.tif", "sha256": "d" * 64}]
    notes = input_differences(fresh, recorded)
    assert notes == [
        "external:dem.tif has different bytes (cccccccccccc now, aaaaaaaaaaaa recorded)",
        "external:new.tif was opened now but is not in the recorded receipt",
        "repo:outputs/x.csv is in the recorded receipt but was not opened now",
    ]
    assert version_differences({"numpy": "2.2.6", "gdal": "3.10"}, {"numpy": "2.2.6", "gdal": "3.9"}) == ["gdal: 3.10 now, 3.9 recorded"]
    assert version_differences({"numpy": "2.2.6"}, {"numpy": "2.2.6"}) == []


# --- Stage functions report every file they open --------------------------------------------------------


def test_rainfall_stage_tracks_every_file_it_opens(tmp_path: Path) -> None:
    obs = load_script("mae_sai_timeline_observations")
    folder = tmp_path / "hii_rain"
    folder.mkdir()
    (folder / "MOU189.csv").write_text("station_code,measure_datetime,rainfall_1h\nMOU189,2024-09-09 00:00:00,1.5\n", encoding="utf-8")
    (folder / "DIWO.csv").write_text("station_code,measure_datetime,rainfall_1h\nDIWO,2024-09-09 01:00:00,2\n", encoding="utf-8")
    (folder / "mou_0all_stn_metadata.csv").write_text("Station_Code,Latitude,Longitude\nMOU189,20.38,99.87\n", encoding="utf-8")
    (folder / "unused.csv").write_text("x\n", encoding="utf-8")  # Present but never opened: must stay out of the receipt.
    receipt = InputReceipt({"external": tmp_path})
    with recorded_opens() as opened:
        rain = obs.rainfall(folder, 24, receipt.track)
    assert [station["code"] for station in rain["stations"]] == ["MOU189", "DIWO"]
    opened_inputs = under(opened, tmp_path)
    assert {path.name for path in opened_inputs} == {"MOU189.csv", "DIWO.csv", "mou_0all_stn_metadata.csv"}
    assert all(path in receipt for path in opened_inputs)
    assert receipt.tracked() == [("external", "hii_rain/DIWO.csv"), ("external", "hii_rain/MOU189.csv"),
                                 ("external", "hii_rain/mou_0all_stn_metadata.csv")]
    # Without the callback the stage still runs (older call sites and the unit tests).
    assert obs.rainfall(folder, 24)["hourly_mm"]["MOU189"][0] == 1.5


# --- The --verify mode, on a small fake bake -------------------------------------------------------------


@pytest.fixture()
def fake_bake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The real script with its heavy ``build`` swapped for one that derives two files from one input."""
    bake = load_bake()
    external = tmp_path / "external"
    external.mkdir()
    (external / "input.bin").write_bytes(b"0123456789")
    (external / "not-opened.bin").write_bytes(b"never read")

    def build(external_root: Path, out_dir: Path, track=bake.untracked) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        data = track(external_root / "input.bin").read_bytes()
        (out_dir / "layer.bin").write_bytes(data[::-1])
        return {"days": [], "size": len(data)}

    monkeypatch.setattr(bake, "build", build)
    monkeypatch.setattr(bake, "compose_manifest", lambda result: {
        "study_id": "fake-study", "revision": "r3", "source_timestamp": "2024-09-09/2024-09-19", "confidence": "low",
        "s1_anchor": {}, "size": result["size"]})
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(work))  # Keep the verify bake's temporary folder inside tmp_path.
    return bake, external, tmp_path / "published" / "r3", work


def snapshot(folder: Path) -> dict[str, tuple[bytes, int]]:
    return {path.relative_to(folder).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns) for path in sorted(folder.rglob("*")) if path.is_file()}


def test_bake_writes_outputs_and_a_receipt_of_what_it_opened(fake_bake) -> None:
    bake, external, committed, _ = fake_bake
    assert bake.main(["--external-root", str(external), "--out", str(committed)]) == 0
    assert sorted(path.name for path in committed.iterdir()) == ["layer.bin", "timeline.json"]
    # A bake outside the repository's revision folder never touches the committed receipt.
    receipt_path = committed.parent / "r3_input_receipt.json"
    assert bake.default_receipt_path(committed) == receipt_path
    assert bake.default_receipt_path(ROOT / bake.OUT_REL) == ROOT / bake.RECEIPT_REL
    document = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert document["schema"] == RECEIPT_SCHEMA and document["revision"] == "r3"
    assert document["inputs"] == [{"root": "external", "path": "input.bin", "bytes": 10, "sha256": sha256_file(external / "input.bin")}]
    assert (document["input_count"], document["input_bytes"]) == (1, 10)
    assert [row["name"] for row in document["outputs"]["files"]] == ["layer.bin", "timeline.json"]
    assert document["outputs"]["file_count"] == 2
    assert document["libraries"]["python"] and document["libraries"]["numpy"]
    assert document["source_timestamp"] and document["confidence"] == "low" and document["assumptions"]
    assert document["official_warning"] is False and document["operational_status"] == "non_operational"
    assert b"\r" not in receipt_path.read_bytes()
    assert str(external) not in receipt_path.read_text(encoding="utf-8")


def test_verify_passes_on_identical_bytes_and_never_writes_to_the_committed_folder(fake_bake, capsys: pytest.CaptureFixture[str]) -> None:
    bake, external, committed, work = fake_bake
    assert bake.main(["--external-root", str(external), "--out", str(committed)]) == 0
    receipt_path = committed.parent / "r3_input_receipt.json"
    before, receipt_before = snapshot(committed), (receipt_path.read_bytes(), receipt_path.stat().st_mtime_ns)
    capsys.readouterr()
    assert bake.main(["--external-root", str(external), "--out", str(committed), "--verify"]) == 0
    out = capsys.readouterr().out
    assert "verify: 2/2 identical" in out and "verify: PASS" in out
    assert "input note" not in out and "library note" not in out
    assert snapshot(committed) == before  # Same bytes and same modification times: nothing was rewritten.
    assert (receipt_path.read_bytes(), receipt_path.stat().st_mtime_ns) == receipt_before
    assert list(work.iterdir()) == []  # The temporary bake is removed.


def test_verify_exits_non_zero_on_any_difference_and_still_leaves_the_folder_alone(fake_bake, capsys: pytest.CaptureFixture[str]) -> None:
    bake, external, committed, work = fake_bake
    assert bake.main(["--external-root", str(external), "--out", str(committed)]) == 0
    args = ["--external-root", str(external), "--out", str(committed), "--verify"]

    (external / "input.bin").write_bytes(b"0123456780")  # One byte of one input changes.
    before = snapshot(committed)
    capsys.readouterr()
    assert bake.main(args) == 1
    out = capsys.readouterr().out
    assert "verify: 1/2 identical" in out and "verify: different bytes: layer.bin" in out and "verify: FAIL" in out
    assert "verify: input note: external:input.bin has different bytes" in out
    assert snapshot(committed) == before
    (external / "input.bin").write_bytes(b"0123456789")
    assert bake.main(args) == 0

    (committed / "stale-layer.png").write_bytes(b"left over")  # A committed file the bake no longer writes.
    capsys.readouterr()
    assert bake.main(args) == 1
    assert "verify: committed but not baked: stale-layer.png" in capsys.readouterr().out
    (committed / "stale-layer.png").unlink()

    (committed / "layer.bin").unlink()  # A baked file that is not committed.
    capsys.readouterr()
    assert bake.main(args) == 1
    assert "verify: baked but not committed: layer.bin" in capsys.readouterr().out
    assert not (committed / "layer.bin").exists()  # Verify did not put it back.

    assert bake.main(["--external-root", str(external), "--out", str(committed.parent / "absent"), "--verify"]) == 1
    assert not (committed.parent / "absent").exists()
    assert list(work.iterdir()) == []


def test_bake_docstring_names_both_dem_tiles_and_the_verify_mode() -> None:
    source = (SCRIPTS / "build_mae_sai_flood_timeline.py").read_text(encoding="utf-8")
    docstring = source.split('"""')[1]
    assert "N20_00_E099_00_DEM.tif" in docstring and "N20_00_E100_00_DEM.tif" in docstring
    for needle in ("tha_ppp_2020.tif", "viirs_flood", "hii_rain", "mae_sai_access_edges.csv", "--verify", "input receipt"):
        assert needle in docstring, needle
    assert not LOCAL_PATH.search(source)  # No machine path in the script.


# --- The committed r3 receipt ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def committed_receipt() -> dict:
    return json.loads(COMMITTED_RECEIPT.read_text(encoding="utf-8"))


def test_committed_receipt_carries_provenance_fields_and_no_machine_path(committed_receipt: dict) -> None:
    raw = COMMITTED_RECEIPT.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert not LOCAL_PATH.search(raw.decode("utf-8"))
    assert committed_receipt["schema"] == RECEIPT_SCHEMA
    assert committed_receipt["study_id"] == "mae-sai-2024-flood-timeline" and committed_receipt["revision"] == "r3"
    assert committed_receipt["generated_by"] == "scripts/build_mae_sai_flood_timeline.py"
    assert committed_receipt["source_timestamp"] and committed_receipt["confidence"] == "low" and committed_receipt["assumptions"]
    assert committed_receipt["official_warning"] is False
    assert committed_receipt["operational_status"] == "non_operational"
    assert committed_receipt["can_feed_decision_layer"] is False
    for name in ("python", "numpy", "scipy", "rasterio", "pillow", "pyproj", "shapely", "pysheds", "pyogrio", "pandas",
                 "gdal (rasterio)", "proj (pyproj)", "geos (shapely)", "webp (pillow)"):
        assert committed_receipt["libraries"].get(name), name
    # A receipt is provenance only: it carries no score and no action class.
    assert not re.search(r"fpps|action_class", raw.decode("utf-8"), re.IGNORECASE)


def test_committed_receipt_lists_every_input_kind_the_bake_opens(committed_receipt: dict) -> None:
    inputs = committed_receipt["inputs"]
    keys = [(row["root"], row["path"]) for row in inputs]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert committed_receipt["input_count"] == len(inputs)
    assert committed_receipt["input_bytes"] == sum(row["bytes"] for row in inputs)
    for row in inputs:
        assert row["root"] in ("external", "repo")
        assert re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) and row["bytes"] > 0
        assert not row["path"].startswith("/") and ".." not in row["path"].split("/") and "\\" not in row["path"]
    paths = [path for _, path in keys]
    count = lambda pattern: sum(1 for path in paths if re.search(pattern, path))  # noqa: E731
    assert count(r"copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E(099|100)_00_DEM\.tif$") == 2  # Both DEM tiles.
    assert count(r"S2B_47QNC_202409(05|15)_0_L2A/(red|green|blue)\.tif$") == 6
    assert count(r"cdse/mae_sai_2024/S1A_IW_GRDH_1SDV_.*\.SAFE\.zip$") == 2
    assert count(r"worldpop_population/tha_ppp_2020\.tif$") == 1
    assert count(r"mae_sai_osm_(multipolygons|points_full)\.gpkg$") == 2
    assert count(r"viirs_flood/2024_09/WATER_COM_VIIRS_.*_001day_090\.tif\.zip$") == 9
    assert count(r"hii_rain/2024_09/(MOU189|DIWO|mou_0all_stn_metadata|main_0all_stn_metadata)\.csv$") == 4
    repo_inputs = sorted(path for root, path in keys if root == "repo")
    assert repo_inputs == ["outputs/mae_sai_access_edges.csv", "outputs/mae_sai_admin_context.geojson", "outputs/mae_sai_facilities.geojson",
                           "outputs/mae_sai_population_nodes.csv", "outputs/mae_sai_reported_shelters_2024.json",
                           "outputs/mae_sai_road_risk.geojson"]
    assert len(inputs) == 32


def test_committed_receipt_matches_the_in_repo_inputs_and_the_committed_revision(committed_receipt: dict) -> None:
    for row in committed_receipt["inputs"]:
        if row["root"] == "repo":
            path = ROOT / row["path"]
            assert (path.stat().st_size, sha256_file(path)) == (row["bytes"], row["sha256"]), row["path"]
    outputs = committed_receipt["outputs"]
    assert outputs["folder"] == COMMITTED_FOLDER.relative_to(ROOT).as_posix()
    listing = directory_listing(COMMITTED_FOLDER)
    assert outputs["files"] == listing  # The receipt describes exactly the committed revision, byte for byte.
    assert outputs["file_count"] == len(listing) == 22
    assert outputs["bytes"] == sum(row["bytes"] for row in listing)


def test_committed_receipt_matches_the_external_inputs(committed_receipt: dict) -> None:
    external = os.environ.get("FLOODGUARD_EXTERNAL_DATA")
    if not external:
        pytest.skip("FLOODGUARD_EXTERNAL_DATA is not set; the external inputs stay outside Git")
    regenerable = re.compile(r"derived_context/.*\.gpkg$")  # Cut from the OSM PBF by the bake; may differ per machine.
    for row in committed_receipt["inputs"]:
        if row["root"] != "external" or regenerable.search(row["path"]):
            continue
        path = Path(external) / row["path"]
        assert path.is_file(), row["path"]
        assert (path.stat().st_size, sha256_file(path)) == (row["bytes"], row["sha256"]), row["path"]


# --- The real bake: every opened input is in the receipt -------------------------------------------------


@pytest.fixture(scope="module")
def real_bake(tmp_path_factory: pytest.TempPathFactory) -> dict:
    external = os.environ.get("FLOODGUARD_EXTERNAL_DATA")
    if not external:
        pytest.skip("FLOODGUARD_EXTERNAL_DATA is not set; the real bake needs the external inputs")
    pytest.importorskip("pysheds")
    pyogrio = pytest.importorskip("pyogrio")
    bake = load_bake()
    import rasterio

    out = tmp_path_factory.mktemp("mae-sai-bake") / "r3"
    committed_before = directory_listing(COMMITTED_FOLDER)
    native: list[str] = []
    real_raster_open, real_read_dataframe = rasterio.open, pyogrio.read_dataframe

    def raster_open(fp, *args, **kwargs):
        native.append(str(fp))
        return real_raster_open(fp, *args, **kwargs)

    def read_dataframe(path, *args, **kwargs):
        native.append(str(path))
        return real_read_dataframe(path, *args, **kwargs)

    # GDAL opens rasters and vector files without a Python "open" event, so those two entry points are wrapped.
    with pytest.MonkeyPatch.context() as patch, recorded_opens() as opened:
        patch.setattr(rasterio, "open", raster_open)
        patch.setattr(pyogrio, "read_dataframe", read_dataframe)
        manifest, _, receipt = bake.bake(Path(external), out)
        observed = under(opened + native, Path(external), ROOT / "outputs")
    return {"bake": bake, "external": Path(external), "out": out, "manifest": manifest, "receipt": receipt,
            "observed": observed, "committed_before": committed_before}


def test_every_input_the_real_bake_opens_is_in_the_receipt(real_bake: dict) -> None:
    receipt, observed = real_bake["receipt"], real_bake["observed"]
    assert len(observed) >= 30
    missing = sorted(path.name for path in observed if path not in receipt)
    assert missing == [], f"opened but not in the receipt: {missing}"
    # And the receipt lists nothing the bake did not open.
    recorded = {real_bake["external"].resolve() / path if root == "external" else ROOT / path for root, path in receipt.tracked()}
    assert sorted(path.name for path in recorded - observed) == []
    document = real_bake["bake"].receipt_document(real_bake["manifest"], receipt, real_bake["out"])
    assert not LOCAL_PATH.search(json.dumps(document))
    assert document["input_count"] == len(observed)


def test_the_real_bake_leaves_the_committed_revision_untouched(real_bake: dict) -> None:
    assert directory_listing(COMMITTED_FOLDER) == real_bake["committed_before"]
    assert real_bake["out"].resolve() != COMMITTED_FOLDER.resolve()


def test_the_real_bake_reproduces_the_committed_bytes_with_the_recorded_libraries(real_bake: dict, committed_receipt: dict) -> None:
    drift = version_differences(library_versions(), committed_receipt["libraries"])
    if drift:
        pytest.skip(f"library versions differ from the recorded receipt, so bytes may differ: {drift}")
    comparison = compare_directories(real_bake["out"], COMMITTED_FOLDER)
    assert comparison.matches, (comparison.summary(), comparison.different, comparison.missing_from_fresh, comparison.extra_in_fresh)
    assert comparison.summary() == "22/22 identical"
