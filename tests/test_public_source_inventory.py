"""Integrity and path checks for the external public-data inventory."""

import csv
import hashlib
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_public_source_inventory.py"
SPEC = importlib.util.spec_from_file_location("verify_public_source_inventory", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _manifest(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["path", "bytes", "sha256"])
        writer.writerows(rows)


def test_inventory_reopens_bytes_and_rejects_tamper(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    source = root / "source.csv"
    source.write_bytes(b"source-1")
    manifest = tmp_path / "manifest.csv"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    _manifest(manifest, [["source.csv", "8", digest]])
    receipt = MODULE.verify(root, manifest)
    assert receipt["status"] == "PASS" and receipt["files_checked"] == 1
    source.write_bytes(b"source-2")
    result = MODULE.verify(root, manifest)
    assert result["status"] == "FAIL"
    assert result["failures"] == [{"path": "source.csv", "reason": "sha256_mismatch"}]


def test_inventory_never_reads_parent_or_absolute_paths(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    manifest = tmp_path / "manifest.csv"
    digest = "0" * 64
    _manifest(manifest, [["../secret.txt", "1", digest], ["C:/secret.txt", "1", digest],
        ["sub/../../secret.txt", "1", digest]])
    receipt = MODULE.verify(root, manifest)
    assert receipt["status"] == "FAIL" and receipt["files_checked"] == 0
    assert all(item["reason"] == "unsafe_or_duplicate_path" for item in receipt["failures"])
