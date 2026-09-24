"""Offline tests for exact-product Earth Search acquisition and resumable COGs."""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "acquire_earth_search_mae_sai_reference.py"
_SPEC = importlib.util.spec_from_file_location("acquire_earth_search_mae_sai_reference", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
acquisition = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(acquisition)


class _Response(io.BytesIO):
    def __init__(self, body: bytes, *, status: int = 200, headers: dict[str, str] | None = None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


def test_item_refuses_a_different_product_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    item_id, product_uri = acquisition.SCENES["event"]
    assets = {name: {"href": f"https://example.test/{name}.tif", "type": "image/tiff; profile=cloud-optimized"}
              for name in acquisition.ASSETS}
    item = {"id": item_id, "properties": {"s2:product_uri": "other-product.SAFE"}, "assets": assets}
    monkeypatch.setattr(acquisition, "_urlopen", lambda url: _Response(json.dumps(item).encode()))

    with pytest.raises(ValueError, match="product URI differs"):
        acquisition._item(item_id, product_uri)

    item["properties"]["s2:product_uri"] = product_uri
    assert acquisition._item(item_id, product_uri)["id"] == item_id


def test_download_resumes_only_at_the_verified_range(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "blue.tif"
    target.with_suffix(".tif.part").write_bytes(b"abc")
    requests: list[dict[str, str] | None] = []

    def serve(url: str, *, headers: dict[str, str] | None = None) -> _Response:
        requests.append(headers)
        return _Response(b"def", status=206, headers={"Content-Range": "bytes 3-5/6"})

    monkeypatch.setattr(acquisition, "_urlopen", serve)
    acquisition._download("https://example.test/blue.tif", target, 6, attempts=1)
    assert requests == [{"Range": "bytes=3-"}]
    assert target.read_bytes() == b"abcdef"
    assert not target.with_suffix(".tif.part").exists()


def test_acquire_records_each_asset_and_refuses_changed_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "assets.csv"
    assets = {name: {"href": f"https://example.test/{name}.tif", "type": "image/tiff; profile=cloud-optimized"}
              for name in acquisition.ASSETS}
    monkeypatch.setattr(acquisition, "_item", lambda item_id, product_uri: {"assets": assets})
    monkeypatch.setattr(acquisition, "_head", lambda url: (6, "etag"))

    def write_cog(url: str, target: Path, expected_size: int) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"abcdef")

    monkeypatch.setattr(acquisition, "_download", write_cog)
    acquisition.acquire(scene="event", external_dir=tmp_path, manifest=manifest, workers=2)
    with manifest.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(acquisition.ASSETS)
    assert {row["asset"] for row in rows} == set(acquisition.ASSETS)
    assert {row["source_edition"] for row in rows} == {"element84_cog_of_l2a"}
    assert {row["original_safe_sha256"] for row in rows} == {"not_recorded"}
    assert all(len(row["sha256"]) == 64 and row["file_size_bytes"] == "6" for row in rows)

    rows[0]["sha256"] = "0" * 64
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=acquisition.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="Existing manifest disagrees"):
        acquisition.acquire(scene="event", external_dir=tmp_path, manifest=manifest, workers=2)
