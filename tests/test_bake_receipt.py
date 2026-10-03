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

import numpy as np
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
    sha256_text_file,
    source_differences,
    source_hashes,
    version_differences,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
COMMITTED_RECEIPT = ROOT / "docs" / "mae_sai_timeline_r4_input_receipt.json"
COMMITTED_FOLDER = ROOT / "apps" / "web" / "public" / "studies" / "mae-sai-2024-timeline" / "r4"
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
    # Names are sorted as text, the same on every platform: an upper-case name comes first, whatever the file system does.
    mixed = write_tree(tmp_path / "mixed", {"folder/envelope.png": b"p", "folder/LICENSE": b"l", "folder/envelope.json": b"j", "README.txt": b"r", "a.bin": b"a"})
    assert [row["name"] for row in directory_listing(mixed)] == ["README.txt", "a.bin", "folder/LICENSE", "folder/envelope.json", "folder/envelope.png"]


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


def test_receipt_hashes_a_file_again_only_when_it_changed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import floodguard.bake_receipt as module

    path = tmp_path / "big.tif"
    path.write_bytes(b"first")
    receipt = InputReceipt({"external": tmp_path})
    receipt.track(path)
    calls: list[str] = []
    real = module.sha256_file
    monkeypatch.setattr(module, "sha256_file", lambda target: calls.append(Path(target).name) or real(target))
    first = receipt.entries()
    assert receipt.entries() == first and calls == ["big.tif"]  # The second call reuses the hash.
    path.write_bytes(b"second, longer")
    changed = receipt.entries()
    assert calls == ["big.tif", "big.tif"]
    assert changed[0]["sha256"] == hashlib.sha256(b"second, longer").hexdigest() != first[0]["sha256"]


def test_source_hashes_ignore_windows_line_endings_and_explain_changes(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    unix, windows = tmp_path / "scripts" / "a.py", tmp_path / "scripts" / "b.py"
    unix.write_bytes(b"x = 1\ny = 2\n")
    windows.write_bytes(b"x = 1\r\ny = 2\r\n")
    assert sha256_text_file(unix) == sha256_text_file(windows) == hashlib.sha256(b"x = 1\ny = 2\n").hexdigest()
    rows = source_hashes([windows, unix], tmp_path)
    assert [row["path"] for row in rows] == ["scripts/a.py", "scripts/b.py"]  # Relative POSIX paths, sorted.
    assert rows[0]["sha256"] == rows[1]["sha256"]
    with pytest.raises(ReceiptError, match="outside the repository"):
        source_hashes([tmp_path / "scripts" / "a.py"], tmp_path / "scripts" / "nested")
    assert source_differences(rows, rows) == []
    edited = [{"path": "scripts/a.py", "sha256": "c" * 64}, {"path": "scripts/new.py", "sha256": "d" * 64}]
    assert source_differences(edited, rows) == [
        f"scripts/a.py changed since the recorded bake (cccccccccccc now, {rows[0]['sha256'][:12]} recorded)",
        "scripts/b.py is in the recorded receipt but is not used now",
        "scripts/new.py is used now but is not in the recorded receipt",
    ]


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
    def compose_manifest(result: dict, inputs: list[dict] | None = None, generated_at: str | None = None) -> dict:
        basis = "declared" if generated_at else "newest_input_timestamp"
        return {"study_id": "fake-study", "revision": "r4", "source_timestamp": "2024-09-09/2024-09-19", "confidence": "low",
                "generated_at": generated_at or "2024-09-19T17:00:00Z", "generated_at_basis": basis,
                "input_sha256": inputs or [], "s1_anchor": {}, "size": result["size"]}

    monkeypatch.setattr(bake, "compose_manifest", compose_manifest)
    monkeypatch.setattr(bake, "manifest_problems", lambda manifest: [])  # The fake manifest is not a replay manifest.
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(work))  # Keep the verify bake's temporary folder inside tmp_path.
    return bake, external, tmp_path / "published" / "r4", work


def snapshot(folder: Path) -> dict[str, tuple[bytes, int]]:
    return {path.relative_to(folder).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns) for path in sorted(folder.rglob("*")) if path.is_file()}


def test_bake_writes_outputs_and_a_receipt_of_what_it_opened(fake_bake) -> None:
    bake, external, committed, _ = fake_bake
    assert bake.main(["--external-root", str(external), "--out", str(committed)]) == 0
    assert sorted(path.name for path in committed.iterdir()) == ["layer.bin", "timeline.json"]
    # A bake outside the repository's revision folder never touches the committed receipt.
    receipt_path = committed.parent / "r4_input_receipt.json"
    assert bake.default_receipt_path(committed) == receipt_path
    assert bake.default_receipt_path(ROOT / bake.OUT_REL) == ROOT / bake.RECEIPT_REL
    document = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert document["schema"] == RECEIPT_SCHEMA and document["revision"] == "r4"
    assert document["inputs"] == [{"root": "external", "path": "input.bin", "bytes": 10, "sha256": sha256_file(external / "input.bin")}]
    assert (document["input_count"], document["input_bytes"]) == (1, 10)
    assert [row["name"] for row in document["outputs"]["files"]] == ["layer.bin", "timeline.json"]
    assert document["outputs"]["file_count"] == 2
    assert document["libraries"]["python"] and document["libraries"]["numpy"]
    assert document["source_timestamp"] and document["confidence"] == "low" and document["assumptions"]
    assert document["official_warning"] is False and document["operational_status"] == "non_operational"
    assert b"\r" not in receipt_path.read_bytes()
    assert str(external) not in receipt_path.read_text(encoding="utf-8")
    # The manifest carries the same input hashes as the receipt, and the receipt names the bake sources by content.
    manifest = json.loads((committed / "timeline.json").read_text(encoding="utf-8"))
    assert manifest["input_sha256"] == document["inputs"]
    assert document["generated_at"] == {"value": "2024-09-19T17:00:00Z", "basis": "newest_input_timestamp"}
    assert [row["path"] for row in document["code"]] == sorted(bake.BAKE_SOURCES)
    assert all(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) for row in document["code"])


def test_generated_at_is_declared_once_then_carried_and_never_read_from_the_clock(fake_bake, capsys: pytest.CaptureFixture[str]) -> None:
    bake, external, committed, _ = fake_bake
    receipt_path = committed.parent / "r4_input_receipt.json"
    base = ["--external-root", str(external), "--out", str(committed)]

    def manifest() -> dict:
        return json.loads((committed / "timeline.json").read_text(encoding="utf-8"))

    # Declared: recorded in the manifest and in the receipt, normalised with its offset.
    assert bake.main([*base, "--generated-at", "2026-10-01T16:10:00+07:00"]) == 0
    assert (manifest()["generated_at"], manifest()["generated_at_basis"]) == ("2026-10-01T16:10:00+07:00", "declared")
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["generated_at"] == {"value": "2026-10-01T16:10:00+07:00", "basis": "declared"}
    first = (committed / "timeline.json").read_bytes()
    # A later bake without the argument reproduces the recorded files, so it may carry the value: the bytes do not move.
    capsys.readouterr()
    assert bake.main(base) == 0
    assert (committed / "timeline.json").read_bytes() == first
    assert "carried from the recorded receipt" in capsys.readouterr().out
    # --verify also carries it and passes; a different declared time is a real difference.
    assert bake.main([*base, "--verify"]) == 0
    assert "verify: generated_at 2026-10-01T16:10:00+07:00" in capsys.readouterr().out
    assert bake.main([*base, "--verify", "--generated-at", "2026-10-02T09:00:00+07:00"]) == 1
    assert "verify: different bytes: timeline.json" in capsys.readouterr().out
    # A time without an offset is refused: the reader could not tell which clock it is on.
    with pytest.raises(ValueError, match="UTC offset"):
        bake.main([*base, "--generated-at", "2026-10-01T16:10:00"])

    assert bake.resolve_generated_at("2026-10-01T09:10:00Z", {}) == ("2026-10-01T09:10:00Z", "declared with --generated-at")
    assert bake.resolve_generated_at(None, {})[0] is None
    assert bake.resolve_generated_at(None, {"generated_at": {"value": "2024-09-19T17:00:00Z", "basis": "newest_input_timestamp"}})[0] is None
    source = (SCRIPTS / "build_mae_sai_flood_timeline.py").read_text(encoding="utf-8")
    assert not re.search(r"datetime\.now|utcnow|time\.time\(|date\.today", source)


def test_a_bake_that_changes_the_files_may_not_carry_the_recorded_time(fake_bake, capsys: pytest.CaptureFixture[str]) -> None:
    bake, external, committed, work = fake_bake
    receipt_path = committed.parent / "r4_input_receipt.json"
    base = ["--external-root", str(external), "--out", str(committed)]
    assert bake.main([*base, "--generated-at", "2026-10-01T20:28:00+07:00"]) == 0
    before, receipt_before = snapshot(committed), (receipt_path.read_bytes(), receipt_path.stat().st_mtime_ns)

    (external / "input.bin").write_bytes(b"0123456780")  # One byte of one input changes: the baked files change with it.
    capsys.readouterr()
    assert bake.main(base) == 2
    captured = capsys.readouterr()
    assert "the recorded time 2026-10-01T20:28:00+07:00 cannot be carried" in captured.err
    assert "different bytes: layer.bin" in captured.err and "different bytes: timeline.json" in captured.err
    assert "input note: external:input.bin has different bytes" in captured.err
    assert "--generated-at" in captured.err and "Nothing was written" in captured.err
    assert "carried from the recorded receipt" not in captured.out
    # Refused means untouched: the published folder and the receipt keep their bytes and their modification times.
    assert snapshot(committed) == before
    assert (receipt_path.read_bytes(), receipt_path.stat().st_mtime_ns) == receipt_before
    assert list(work.iterdir()) == []  # The bake that was set aside is removed.

    # Declaring a new time is the way through, and the receipt then records it.
    assert bake.main([*base, "--generated-at", "2026-10-08T09:00:00+07:00"]) == 0
    assert json.loads((committed / "timeline.json").read_text(encoding="utf-8"))["generated_at"] == "2026-10-08T09:00:00+07:00"
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["generated_at"] == {"value": "2026-10-08T09:00:00+07:00", "basis": "declared"}
    assert (committed / "layer.bin").read_bytes() == b"0123456780"[::-1]
    # With the input restored the files differ from that recorded bake again, so a plain bake is refused again.
    (external / "input.bin").write_bytes(b"0123456789")
    assert bake.main(base) == 2
    # --verify still carries the recorded time: it writes nothing, and the byte comparison reports the difference.
    capsys.readouterr()
    assert bake.main([*base, "--verify"]) == 1
    assert "verify: generated_at 2026-10-08T09:00:00+07:00" in capsys.readouterr().out


def test_carry_blockers_name_every_output_file_that_differs_from_the_recorded_bake() -> None:
    bake = load_bake()
    files = lambda **hashes: {"outputs": {"files": [{"name": name, "sha256": value} for name, value in hashes.items()]}}  # noqa: E731
    recorded = files(**{"a.png": "1" * 64, "timeline.json": "2" * 64, "old.bin": "3" * 64})
    assert bake.carry_blockers(recorded, recorded) == []
    fresh = files(**{"a.png": "1" * 64, "timeline.json": "9" * 64, "new.bin": "4" * 64})
    assert bake.carry_blockers(fresh, recorded) == ["new file: new.bin", "no longer written: old.bin", "different bytes: timeline.json"]
    # A receipt without an output list (or no receipt) cannot vouch for anything.
    assert bake.carry_blockers(fresh, {}) == ["the recorded receipt lists no output files"]
    assert bake.carry_blockers(fresh, {"outputs": {"files": []}}) == ["the recorded receipt lists no output files"]


def test_verify_reports_changed_bake_sources_without_failing_identical_bytes(fake_bake, capsys: pytest.CaptureFixture[str]) -> None:
    bake, external, committed, _ = fake_bake
    base = ["--external-root", str(external), "--out", str(committed)]
    assert bake.main(base) == 0
    receipt_path = committed.parent / "r4_input_receipt.json"
    document = json.loads(receipt_path.read_text(encoding="utf-8"))
    document["code"][0]["sha256"] = "0" * 64  # As if a bake source had been edited since the recorded bake.
    receipt_path.write_text(json.dumps(document), encoding="utf-8")
    capsys.readouterr()
    assert bake.main([*base, "--verify"]) == 0
    out = capsys.readouterr().out
    assert f"verify: code note: {document['code'][0]['path']} changed since the recorded bake" in out and "verify: PASS" in out


def test_bake_sources_cover_every_repository_module_the_bake_imports() -> None:
    import ast

    bake = load_bake()
    listed = set(bake.BAKE_SOURCES)
    assert all((ROOT / path).is_file() for path in listed)
    assert bake.GENERATED_BY in listed and bake.SCHEMA_REL.as_posix() in listed
    seen: set[str] = set()
    queue = [bake.GENERATED_BY]
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        for node in ast.walk(ast.parse((ROOT / path).read_text(encoding="utf-8"))):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                if name.startswith("floodguard."):
                    queue.append(f"src/{name.replace('.', '/')}.py")
                elif name.startswith("mae_sai_timeline_"):
                    queue.append(f"scripts/{name}.py")
    assert seen <= listed, f"imported by the bake but not hashed in the receipt: {sorted(seen - listed)}"


def test_bake_refuses_a_manifest_that_breaks_the_evidence_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bake = load_bake()
    external = tmp_path / "external"
    external.mkdir()
    monkeypatch.setattr(bake, "build", lambda external_root, out_dir, track=bake.untracked: out_dir.mkdir(parents=True) or {})
    monkeypatch.setattr(bake, "compose_manifest", lambda result, inputs=None, generated_at=None: {"study_id": "fake", "accepted_fpps": 81.2})
    out = tmp_path / "out" / "r4"
    with pytest.raises(ValueError, match="accepted_fpps must be null"):
        bake.bake(external, out)
    assert not (out / "timeline.json").exists()  # Nothing is written when the contract is broken.


def test_verify_passes_on_identical_bytes_and_never_writes_to_the_committed_folder(fake_bake, capsys: pytest.CaptureFixture[str]) -> None:
    bake, external, committed, work = fake_bake
    assert bake.main(["--external-root", str(external), "--out", str(committed)]) == 0
    receipt_path = committed.parent / "r4_input_receipt.json"
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
    # The derived layer changes, and so does the manifest, which carries the input hashes.
    assert "verify: 0/2 identical" in out and "verify: different bytes: layer.bin" in out and "verify: FAIL" in out
    assert "verify: different bytes: timeline.json" in out
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
    for needle in ("tha_ppp_2020.tif", "viirs_flood", "hii_rain", "mae_sai_access_edges.csv", "--verify", "input receipt",
                   "thailand-latest.osm.pbf", "rights_basis_4009_v1.json", "{red,green,blue,swir16,scl}.tif",
                   "unosat/unosat_4009_chiang_rai_2024/FL20240912THA_GDB.zip", "CHIANGRAI_20240801_20241012_AccumulatedFlood",
                   "mae_sai_timeline_unosat4009.py", "unosat4009/"):
        assert needle in docstring, needle
    assert not LOCAL_PATH.search(source)  # No machine path in the script.


def test_product_4009_wording_follows_the_rights_record() -> None:
    """The manifest's sentences about product 4009 come from the rights record, and exist only for a confirmed one.

    The sentences are the ones ``flood-timeline-copy.test.ts`` renders in Thai; keep the two in step.
    """
    from floodguard.rights_basis import load_rights_basis, owner_confirmed

    bake = load_bake()
    assert bake.short_date("2026-09-30") == "30 Sep 2026" and bake.short_date("2026-10-01") == "1 Oct 2026"
    record = load_rights_basis(ROOT / "docs" / "proposal_execution" / "rights_basis_4009_v1.json")
    status = bake.rights_status(record)
    assert status["confirmed"] is owner_confirmed(record)
    assert (status["signed_on"], status["reply_quote"], status["reply_relayed_on"], status["licence"]) == ("2026-09-30", "we approve the use", "2026-10-01", "CC BY-SA 4.0")
    assert status["record"] == "docs/proposal_execution/rights_basis_4009_v1.json"
    assert (status["credit"], status["licence_url"]) == ("UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009", "https://creativecommons.org/licenses/by-sa/4.0/")
    reply = 'The CC BY-SA 4.0 rights decision (D2) was signed on 30 Sep 2026 and UNOSAT replied "we approve the use" (relayed by a project owner on 1 Oct 2026)'
    confirmed = bake.rights_wording({**status, "confirmed": True, "confirmed_on": "2026-10-09"})
    assert confirmed == {
        "status": "Shown as a season envelope scenario layer; the owners confirmed the rights record on 9 Oct 2026.",
        "condition": ("UNOSAT/GISTDA product 4009 (CC BY-SA 4.0) is shown as a season envelope scenario layer: its derived files keep their own "
                      "folder, credit, licence and change notice; the owners confirmed the rights record on 9 Oct 2026."),
        "block_note": ("Never an observation for a replay day. Shown as a scenario layer with its own toggle, credit and change notice; "
                       "the owners confirmed the rights record on 9 Oct 2026."),
        "rights_note": f"Season envelope (scenario per decision D3). {reply}; the owners confirmed the rights record on 9 Oct 2026. Shown from this revision as a scenario layer.",
    }
    # The wording does not say when UNOSAT wrote its reply (the original message is not filed).
    assert not re.search(r'approve the use" on \d', confirmed["rights_note"])
    assert bake.publication_eligibility(None, {**status, "confirmed": True, "confirmed_on": "2026-10-09"})["inputs"][-1]["shown"] is True
    # There is no wording for an unconfirmed record: the product is shown only when the owners have confirmed it.
    with pytest.raises(ValueError, match="shown only when the owners have confirmed its rights record"):
        bake.rights_wording({**status, "confirmed": False, "confirmed_on": None})
    with pytest.raises(ValueError, match="shown only when the owners have confirmed its rights record"):
        bake.publication_eligibility(None, {**status, "confirmed": False, "confirmed_on": None})


def test_bake_stops_before_anything_else_when_the_rights_record_is_not_confirmed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GATE: the product 4009 files are baked only because the rights record says confirmed.

    With the record seeded as pending in a test copy, the bake refuses at once: it opens no external input, creates
    no output folder and writes no file.
    """
    from floodguard.rights_basis import RightsNotConfirmedError, load_rights_basis

    bake = load_bake()
    record = json.loads((ROOT / "docs" / "proposal_execution" / "rights_basis_4009_v1.json").read_text(encoding="utf-8"))
    record["owner_confirmation"].update(status="pending", confirmed_by=[], confirmed_on=None)
    record.update(record_status="draft_pending_owner_confirmation", signed_by_human=False, human_rights_clearance=False)
    pending = tmp_path / "rights_basis_4009_v1.json"
    pending.write_text(json.dumps(record), encoding="utf-8")
    load_rights_basis(pending)  # A valid record, only not confirmed.
    monkeypatch.setattr(bake, "RIGHTS_RECORD", pending)
    external = tmp_path / "external"  # Empty: the bake must stop before it looks for any input.
    external.mkdir()
    out = tmp_path / "out" / "r4"
    with recorded_opens() as opened:
        with pytest.raises(RightsNotConfirmedError, match="not confirmed by the owners.*must stay out of public files"):
            bake.build(external, out)
    assert not out.exists() and not (tmp_path / "out").exists()
    assert under(opened, external) == set()
    # The manifest check refuses the committed manifest beside that record too: it names the product's files and shows it.
    manifest = json.loads((COMMITTED_FOLDER / "timeline.json").read_text(encoding="utf-8"))
    problems = bake.manifest_problems(manifest)
    assert any("cites product 4009 and names a file" in line for line in problems)
    assert any("must carry shown: false while the rights record is unconfirmed" in line for line in problems)
    # With the confirmed record back in place the same manifest holds.
    monkeypatch.setattr(bake, "RIGHTS_RECORD", ROOT / "docs" / "proposal_execution" / "rights_basis_4009_v1.json")
    assert bake.manifest_problems(manifest) == []


def s2_check_figures() -> dict:
    """Figures of a Sentinel-2 water check as the observation stage returns them (made-up values)."""
    scene = {"clear_km2": 10.0, "clear_share": 0.5, "water_km2": 2.0, "scl_class_km2": {"vegetation": 10.0, "cloud_high_probability": 10.0}}
    return {
        "resolution_m": 20.0, "threshold": 0.0, "district_km2": 20.0, "permanent_water_km2": 0.1,
        "scenes": {"pre_event": dict(scene, water_km2=1.0), "event": dict(scene)},
        "change": {"both_clear_km2": 8.0, "event_water_km2": 1.8, "pre_event_water_km2": 0.9, "new_water_km2": 1.0, "no_longer_water_km2": 0.1},
        "model_at_event_scene": {"model_t": 6.4571, "model_stage_m": 0.278, "model_flood_km2_district": 1.5, "model_flood_km2_clear": 1.0,
                                 "model_flood_km2_both_clear": 0.9, "model_overlap_km2": 0.5, "model_union_km2": 2.5, "model_agreement_iou": 0.2,
                                 "model_share_of_observed_water_reached": 0.25, "model_share_inside_observed_water": 0.5},
        "sensitivity": [{"id": "strict_clear", "rule": "stricter", "event_clear_share": 0.4, "event_water_km2": 1.9, "pre_event_clear_share": 0.4,
                         "pre_event_water_km2": 0.9, "new_water_km2": 0.9, "model_agreement_iou": 0.2}],
    }


def test_sentinel2_block_dates_each_scene_and_refuses_an_unnamed_model_field() -> None:
    """Model output inside the observed block sits only where the evidence block names it as scenario fields."""
    bake = load_bake()
    block = bake.s2_crosscheck_block(s2_check_figures())
    assert [(scene["id"], scene["role"], scene["source_timestamp"], scene["local_time"]) for scene in block["scenes"]] == [
        ("s2-20240905", "pre_event", "2024-09-05T03:58:19Z", "2024-09-05T10:58:19+07:00"),
        ("s2-20240915", "event", "2024-09-15T03:58:15Z", "2024-09-15T10:58:15+07:00")]
    assert block["source_timestamp"] == bake.S2_CHECK_PAIR == "2024-09-05T03:58:19Z/2024-09-15T03:58:15Z"
    assert block["model_at_event_scene"]["model_local_time"] == "2024-09-15T10:58:15+07:00"
    assert (block["label"], block["comparison"], block["confidence"]) == ("water or saturated mud", "indicative", "low")
    assert "consistent with" in block["reading"] and "explain" not in block["reading"].lower()
    # No land-cover map is an input, so the reading names no land cover; without VIIRS rows it says nothing about the next day.
    assert "on fields" not in block["reading"] and "following_day" not in block
    assert any("No land-cover map is an input" in line for line in block["assumptions"])
    assert bake.model_key_paths(block) == sorted([
        "model_at_event_scene", "model_fields", "sensitivity[].model_agreement_iou",
        *(f"model_at_event_scene.{key}" for key in block["model_at_event_scene"])])
    assert bake.S2_MODEL_PATHS == ("model_at_event_scene", "sensitivity[].model_agreement_iou")
    # The replay's acquisition time of the 15 Sep scene, in days since 9 Sep 00:00 ICT.
    assert bake.replay_days("2024-09-15T03:58:15Z") == pytest.approx(6 + (10 + 58 / 60 + 15 / 3600) / 24)
    assert bake.replay_days(bake.EVENT_START) == 0.0
    # A model figure placed among the observed figures stops the bake: the evidence block would file it as observed.
    for part in ("change", "scenes"):
        figures = s2_check_figures()
        target = figures[part] if part == "change" else figures[part]["event"]
        target["model_flood_km2"] = 1.0
        with pytest.raises(ValueError, match="model fields the evidence block does not name"):
            bake.s2_crosscheck_block(figures)
    figures = s2_check_figures()
    figures["sensitivity"][0]["model_flood_km2_clear"] = 1.0
    with pytest.raises(ValueError, match=r"sensitivity\[\]\.model_flood_km2_clear"):
        bake.s2_crosscheck_block(figures)
    # And an observed figure may not hide inside the model part.
    figures = s2_check_figures()
    figures["model_at_event_scene"]["water_km2"] = 2.0
    with pytest.raises(ValueError, match="not named as model output"):
        bake.s2_crosscheck_block(figures)


def test_sentinel2_block_adds_the_next_clear_viirs_day_only_when_it_shows_less_than_the_model() -> None:
    bake = load_bake()

    def day(date: str, clear: float, viirs: float, model: float) -> dict:
        return {"date": date, "nominal_local_time": f"{date}T13:30:00+07:00", "clear_km2": clear, "viirs_flood_km2_clear": viirs,
                "model_flood_km2_clear": model}

    event = "2024-09-15T10:58:15+07:00"
    days = [day("2024-09-14", 5.9, 0.0, 0.18), day("2024-09-15", 292.2, 46.17, 19.5), day("2024-09-16", 234.9, 3.28, 7.7), day("2024-09-17", 202.5, 3.68, 0.0)]
    # The day after the scene, not the scene's own day and not an earlier one.
    assert bake.following_viirs_day(days, event)["date"] == "2024-09-16"
    assert bake.following_viirs_day(list(reversed(days)), event)["date"] == "2024-09-16"  # Whatever the order of the rows.
    block = bake.s2_crosscheck_block(s2_check_figures(), days)
    assert block["following_day"] == {"viirs_date": "2024-09-16", "reading": bake.S2_FOLLOWING_DAY_READING}
    reading = block["following_day"]["reading"]
    assert "consistent with" in reading and "rather than lasting ponding" in reading and "explain" not in reading.lower()
    assert bake.model_key_paths(block["following_day"]) == []  # It holds no model figure: those stay in viirs_daily.
    # A wholly cloudy next day is skipped: the first day that saw the district decides.
    cloudy = [day("2024-09-16", 0.0, 0.0, 0.0), day("2024-09-17", 202.5, 3.68, 0.0)]
    assert bake.following_viirs_day(cloudy, event)["date"] == "2024-09-17"
    assert "following_day" not in bake.s2_crosscheck_block(s2_check_figures(), cloudy)  # VIIRS shows more than the model there.
    assert "following_day" not in bake.s2_crosscheck_block(s2_check_figures(), [day("2024-09-16", 234.9, 7.7, 7.7)])  # Not less.
    assert bake.following_viirs_day(days[:2], event) is None and "following_day" not in bake.s2_crosscheck_block(s2_check_figures(), days[:2])


def test_bake_reads_openstreetmap_from_the_pbf_and_keeps_no_derived_cache() -> None:
    # A cached cut can outlive a change of the replay area and cannot be rebuilt byte for byte (a GeoPackage carries
    # its write time), so the bake reads the extract itself on every run and writes nothing outside its output folder.
    source = (SCRIPTS / "build_mae_sai_flood_timeline.py").read_text(encoding="utf-8")
    assert 'OSM_PBF_REL = "open_context/osm_geofabrik/thailand-latest.osm.pbf"' in source
    assert "track(external / OSM_PBF_REL)" in source
    for needle in ("derived_context", ".gpkg", ".to_file(", "write_dataframe"):
        assert needle not in source, needle


# --- Radar size comparison, the replay's last day and the per-subdistrict peak figures (roadmap P2-10, C-3, P3-2) ---------


def test_radar_size_comparison_needs_a_same_track_pair_and_keeps_the_cross_track_pair_as_a_sensitivity() -> None:
    bake = load_bake()
    codes = np.full((40, 40), 2, dtype=np.uint8)  # HAND 0.10 m: wet from the 0.15 m stage on (HAND < stage).
    codes[:, :20] = 100  # 5 m: never in the 0.05-2.0 m stages, but inside the low-HAND zone (< 6 m).
    rng = np.random.default_rng(7)
    pre = rng.normal(45.0, 1.0, codes.shape)
    post = pre.copy()
    post[:, 20:] = 30.0  # Newly dark where the HAND is low.
    water = {bake.S1_ANCHOR_PRE["id"]: pre, "s1-20240906": pre + 0.5, "s1-20240915": post}
    meta = {bake.S1_ANCHOR_PRE["id"]: {"pass": "descending", "relative_orbit": 135, "ipf_version": "003.80"},
            "s1-20240906": {"pass": "ascending", "relative_orbit": 172, "ipf_version": "003.80"},
            "s1-20240915": {"pass": "descending", "relative_orbit": 135, "ipf_version": "003.80"}}
    anchor = bake.s1_size_comparison(codes, water, meta, 0.01)
    assert (anchor["pair"], anchor["best_fit_stage_m"]) == ("same_track", 0.15) and 7.0 < anchor["newly_dark_km2"] <= 8.0
    assert [(image["id"], image["role"], image["pass"], image["relative_orbit"], image["published_as_layer"]) for image in anchor["images"]] == [
        ("s1-20240903", "pre_event", "descending", 135, False), ("s1-20240915", "event", "descending", 135, True)]
    assert [(image["utc"], image["local"]) for image in anchor["images"]] == [
        ("2024-09-03T23:16:00Z", "2024-09-04T06:16:00+07:00"), ("2024-09-15T23:16:01Z", "2024-09-16T06:16:01+07:00")]
    assert "processing_allowed False" in anchor["images"][0]["note"] and "R14" in anchor["images"][0]["note"]
    assert anchor["images"][0]["processor"] == "Sentinel-1 IPF 003.80"
    [cross] = anchor["sensitivity"]
    assert (cross["pair"], cross["source_timestamp"]) == ("cross_track", bake.S1_PAIR)
    assert [(image["id"], image["pass"], image["relative_orbit"]) for image in cross["images"]] == [("s1-20240906", "ascending", 172), ("s1-20240915", "descending", 135)]
    assert set(bake.S1_FIT_FIELDS) <= set(cross)
    assert bake.S1_ANCHOR_PAIR == "2024-09-03T23:16:00Z/2024-09-15T23:16:01Z"
    # A primary pair that is not on one track, or a "cross-track" pair that is, stops the bake: the labels would be untrue.
    for image, change in (("s1-20240903", {"pass": "ascending"}), ("s1-20240903", {"relative_orbit": 62}), ("s1-20240906", {"pass": "descending", "relative_orbit": 135})):
        broken = {key: dict(value) for key, value in meta.items()}
        broken[image].update(change)
        with pytest.raises(ValueError, match="track"):
            bake.s1_size_comparison(codes, water, broken, 0.01)
    # The bake reads the same-track pass from its own SAFE archive and writes no image layer from it.
    source = (SCRIPTS / "build_mae_sai_flood_timeline.py").read_text(encoding="utf-8")
    assert 'track(external / S1_ANCHOR_PRE["folder"] / S1_ANCHOR_PRE["file"])' in source
    assert "s1-20240903" not in {item["id"] for item in bake.OBSERVATIONS}


def test_nothing_is_dated_after_the_replays_last_day() -> None:
    bake = load_bake()
    manifest = {
        "layers": [{"id": "hillshade", "date": None}, {"id": "s1-change", "date": bake.S1_PAIR}],
        "observations": [{"id": "s1-20240915", "local": "2024-09-16T06:16:01+07:00"}],
        "days": [{"date": "2024-09-19"}], "viirs_daily": {"days": [{"date": "2024-09-18", "nominal_local_time": "2024-09-18T13:30:00+07:00"}]},
        "s2_crosscheck": {"scenes": [{"id": "s2-20240915", "local_time": "2024-09-15T10:58:15+07:00"}]},
        "s1_anchor": {"images": [{"id": "s1-20240903", "local": "2024-09-04T06:16:00+07:00"}], "sensitivity": []},
        "stage_anchors": [{"t": 0.0, "stage_m": 0.0}, {"t": 11.0, "stage_m": 0.0}],
        "external_references": [dict(bake.O2_REFERENCE)],  # A cited separate case is not a dated replay entry.
    }
    assert bake.dated_after_replay(manifest) == []
    assert len(bake.replay_dates(manifest)) == 9
    # The end of the last hour (20 Sep 00:00 ICT) is the end of 19 Sep; anything later is refused, wherever it sits.
    assert bake.local_day("2024-09-19T17:00:00Z") == "2024-09-20" and bake.local_day("2024-09-19") == "2024-09-19"
    late = {
        "layers": [{"id": "o2", "date": "2024-10-22T00:00:00Z"}], "observations": [{"id": "o2", "local": "2024-10-22T10:00:00+07:00"}],
        "days": [{"date": "2024-09-20"}], "viirs_daily": {"days": [{"date": "2024-09-20", "nominal_local_time": "2024-09-20T13:30:00+07:00"}]},
        "s2_crosscheck": {"scenes": [{"id": "s2", "local_time": "2024-09-25T10:58:15+07:00"}]},
        "s1_anchor": {"images": [], "sensitivity": [{"images": [{"id": "s1", "local": "2024-09-28T06:16:00+07:00"}]}]},
        "stage_anchors": [{"t": 11.5, "stage_m": 0.0}],
    }
    problems = bake.dated_after_replay(late)
    assert len(problems) == 7 and all("after the replay's last day (2024-09-19)" in problem for problem in problems)
    assert bake.O2_REFERENCE["dated"] == "2024-10-22" and bake.O2_REFERENCE["case"] == "O2"
    assert "not on this map" in bake.O2_REFERENCE["note"] and "no position on the replay slider" in bake.O2_REFERENCE["note"]


def test_per_subdistrict_peak_figures_come_from_the_peak_day_and_the_drawn_road_pieces() -> None:
    bake = load_bake()
    days = [{"index": 0, "stage_m": 0.0, "stats": {"tambon_flooded_km2": {"T1": 0.0, "T2": 0.0}, "tambon_people_in_water": {"T1": 0.0, "T2": 0.0}}},
            {"index": 3, "stage_m": 3.5, "stats": {"tambon_flooded_km2": {"T1": 5.0, "T2": 2.5}, "tambon_people_in_water": {"T1": 60.8, "T2": 5.5}}},
            {"index": 4, "stage_m": 3.5, "stats": {"tambon_flooded_km2": {"T1": 9.0, "T2": 9.0}, "tambon_people_in_water": {"T1": 1.0, "T2": 1.0}}}]
    coverage = {"T1": {"total_km2": 20.0, "modelled_km2": 20.0}, "T2": {"total_km2": 40.0, "modelled_km2": 30.0}}
    road = lambda t, h, length, m=True, k=1.0: {"properties": {"t": t, "h": h, "len": length, "m": m, "k": k}}  # noqa: E731
    roads = [road("T1", 3.0, 120), road("T1", 3.3, 120), road("T1", 3.21, 120), road("T1", 2.0, 120, m=False), road("T1", None, 120),
             road("T2", 1.0, 100, k=0.5), road("T2", 3.4, 100), road("T9", 0.0, 500)]
    rows, local_time = bake.tambon_peak_figures(days, coverage, roads, ["T1", "T2"])
    # The first day at the highest stage is the peak, at local noon; 3.3 m and 3.21 m of HAND are only 0.2 m and 0.29 m deep.
    assert local_time == "2024-09-12T12:00:00+07:00"
    assert rows == [
        {"tambon_id": "T1", "area_km2": 20.0, "modelled_km2": 20.0, "flooded_km2": 5.0, "residents_in_water": 60.8, "road_km_impassable": 0.12},
        {"tambon_id": "T2", "area_km2": 40.0, "modelled_km2": 30.0, "flooded_km2": 2.5, "residents_in_water": 5.5, "road_km_impassable": 0.1}]


# --- The committed r4 receipt ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def committed_receipt() -> dict:
    return json.loads(COMMITTED_RECEIPT.read_text(encoding="utf-8"))


def test_committed_receipt_carries_provenance_fields_and_no_machine_path(committed_receipt: dict) -> None:
    raw = COMMITTED_RECEIPT.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert not LOCAL_PATH.search(raw.decode("utf-8"))
    assert committed_receipt["schema"] == RECEIPT_SCHEMA
    assert committed_receipt["study_id"] == "mae-sai-2024-flood-timeline" and committed_receipt["revision"] == "r4"
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


def test_committed_receipt_and_manifest_agree_on_inputs_generation_time_and_bake_sources(committed_receipt: dict) -> None:
    manifest = json.loads((COMMITTED_FOLDER / "timeline.json").read_text(encoding="utf-8"))
    assert manifest["input_sha256"] == committed_receipt["inputs"]
    assert committed_receipt["generated_at"] == {"value": manifest["generated_at"], "basis": manifest["generated_at_basis"]}
    # The committed revision was baked with a declared time: --verify carries it, and so does a plain re-bake that
    # reproduces the recorded files.
    assert manifest["generated_at_basis"] == "declared"
    bake = load_bake()
    assert bake.resolve_generated_at(None, committed_receipt)[0] == manifest["generated_at"]
    # The receipt names every bake source by content. The hashes are a record of the bake, not a gate: --verify
    # reports a source that changed since, and only the byte comparison decides.
    assert [row["path"] for row in committed_receipt["code"]] == sorted(bake.BAKE_SOURCES)
    assert all(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) for row in committed_receipt["code"])


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
    # The Sentinel-2 water check also reads the short-wave infrared band and the scene classification of both scenes.
    assert count(r"S2B_47QNC_202409(05|15)_0_L2A/(swir16|scl)\.tif$") == 4
    assert count(r"S2B_47QNC_") == 10
    # No land-cover map is an input. Of the UNOSAT products the bake opens one file, the product 4009 archive (it reads one
    # layer of it, the season envelope), beside the product's rights record.
    assert count(r"worldcover|land.?cover") == 0
    assert [path for path in paths if path.startswith("unosat/")] == ["unosat/unosat_4009_chiang_rai_2024/FL20240912THA_GDB.zip"]
    assert sorted(path for path in paths if "4009" in path) == ["docs/proposal_execution/rights_basis_4009_v1.json",
                                                               "unosat/unosat_4009_chiang_rai_2024/FL20240912THA_GDB.zip"]
    archive = next(row for row in inputs if row["path"].startswith("unosat/"))
    record = json.loads((ROOT / "docs" / "proposal_execution" / "rights_basis_4009_v1.json").read_text(encoding="utf-8"))
    assert (archive["bytes"], archive["sha256"]) == (record["archive"]["bytes"], record["archive"]["sha256"])
    assert count(r"cdse/mae_sai_2024/S1A_IW_GRDH_1SDV_.*\.SAFE\.zip$") == 2
    # The same-track pre-event pass for the radar size comparison (owner decision R14): one original SAFE, never a layer.
    assert [path for path in paths if path.startswith("sentinel1_original_safe/")] == [
        "sentinel1_original_safe/S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_055507_06C5C9_72F7.SAFE.zip"]
    assert count(r"worldpop_population/tha_ppp_2020\.tif$") == 1
    # OpenStreetMap is identified by the extract itself, never by a derived cache.
    assert count(r"^open_context/osm_geofabrik/thailand-latest\.osm\.pbf$") == 1
    assert count(r"\.gpkg$") == 0 and count(r"derived_context") == 0
    assert count(r"viirs_flood/2024_09/WATER_COM_VIIRS_.*_001day_090\.tif\.zip$") == 9
    assert count(r"hii_rain/2024_09/(MOU189|DIWO|mou_0all_stn_metadata|main_0all_stn_metadata)\.csv$") == 4
    repo_inputs = sorted(path for root, path in keys if root == "repo")
    assert repo_inputs == ["docs/proposal_execution/rights_basis_4009_v1.json",
                           "outputs/mae_sai_access_edges.csv", "outputs/mae_sai_admin_context.geojson", "outputs/mae_sai_facilities.geojson",
                           "outputs/mae_sai_population_nodes.csv", "outputs/mae_sai_reported_depths_2024.json",
                           "outputs/mae_sai_reported_shelters_2024.json", "outputs/mae_sai_road_risk.geojson"]
    # The reported depths (news, not surveyed; roadmap C-2) are an in-repo input like the reported shelters.
    assert len(inputs) == 39


def test_committed_receipt_matches_the_in_repo_inputs_and_the_committed_revision(committed_receipt: dict) -> None:
    for row in committed_receipt["inputs"]:
        if row["root"] == "repo":
            path = ROOT / row["path"]
            assert (path.stat().st_size, sha256_file(path)) == (row["bytes"], row["sha256"]), row["path"]
    outputs = committed_receipt["outputs"]
    assert outputs["folder"] == COMMITTED_FOLDER.relative_to(ROOT).as_posix()
    listing = directory_listing(COMMITTED_FOLDER)
    assert outputs["files"] == listing  # The receipt describes exactly the committed revision, byte for byte.
    assert outputs["file_count"] == len(listing) == 34
    # 22 files the page loads, the 9 download files of the export pack (the per-subdistrict summary among them) and the 3
    # files of the season envelope (its raster, its statistics and its licence notice), listed like any other output.
    exported = [row["name"] for row in listing if row["name"].startswith("exports/")]
    assert len(exported) == 9 and all(name.count("/") == 1 for name in exported)
    assert "exports/tambon_replay_summary.json" in exported
    assert [row["name"] for row in listing if row["name"].startswith("unosat4009/")] == ["unosat4009/LICENSE", "unosat4009/envelope.json", "unosat4009/envelope.png"]
    assert outputs["bytes"] == sum(row["bytes"] for row in listing)


def test_committed_receipt_matches_the_external_inputs(committed_receipt: dict) -> None:
    external = os.environ.get("FLOODGUARD_EXTERNAL_DATA")
    if not external:
        pytest.skip("FLOODGUARD_EXTERNAL_DATA is not set; the external inputs stay outside Git")
    for row in committed_receipt["inputs"]:  # Every external input, the OSM extract included: none is machine-specific.
        if row["root"] != "external":
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

    out = tmp_path_factory.mktemp("mae-sai-bake") / "r4"
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
        # generated_at is a declared value: the rebuild uses the one recorded in the committed receipt.
        recorded = json.loads(COMMITTED_RECEIPT.read_text(encoding="utf-8"))
        stamp, _ = bake.resolve_generated_at(None, recorded)
        manifest, _, receipt = bake.bake(Path(external), out, generated_at=stamp)
        observed = under(opened + native, Path(external), ROOT / "outputs", ROOT / "docs" / "proposal_execution")
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
    assert comparison.summary() == "34/34 identical"  # The export pack and the season envelope's files are rebuilt byte for byte too.
