"""Offline guards for the frozen optical v2 source acquisition."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "acquire_earth_search_automated_optical_v2.py"
_SPEC = importlib.util.spec_from_file_location("acquire_earth_search_automated_optical_v2", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
sys.path.insert(0, str(_SCRIPT.parent))
acquisition = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(acquisition)


def _item(*, item_id: str = "pinned", uri: str = "S2B_MSIL2A_x_N0500_x.SAFE") -> dict:
    return {
        "id": item_id,
        "properties": {
            "s2:product_uri": uri,
            "s2:processing_baseline": "05.00",
            "datetime": "2021-09-28T03:53:49.285000Z",
        },
        "assets": {
            name: {
                "href": f"https://example.test/{name}.tif",
                "raster:bands": [{"scale": 0.0001, "offset": -0.1}]
                if name != "scl" else [{"nodata": 0}],
            }
            for name in acquisition.ASSETS
        },
    }


def test_plan_refuses_changed_frozen_content(tmp_path: Path) -> None:
    plan = acquisition.load_plan()
    changed = {**plan, "purpose": "changed after pre-registration"}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="self-hash mismatch"):
        acquisition.load_plan(path)

    changed["preregistration_sha256"] = acquisition._canonical_sha256(
        {key: value for key, value in changed.items() if key != "preregistration_sha256"}
    )
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from the frozen Git commit"):
        acquisition.load_plan(path)


def test_stac_transform_requires_explicit_reflectance_parameters() -> None:
    assert acquisition._stac_scale_offset(
        {"raster:bands": [{"scale": 0.0001, "offset": -0.1}]}, "blue"
    ) == ("0.0001", "-0.1")
    assert acquisition._stac_scale_offset({"raster:bands": [{"nodata": 0}]}, "scl") == ("", "")
    with pytest.raises(ValueError, match="scale/offset"):
        acquisition._stac_scale_offset({"raster:bands": [{"scale": 0.0001}]}, "blue")


def test_stac_item_checks_exact_instant_and_processing_edition(monkeypatch: pytest.MonkeyPatch) -> None:
    item = _item()
    monkeypatch.setattr(acquisition, "_item", lambda item_id, product_uri: item)
    assert acquisition._stac_item(item["id"], item["properties"]["s2:product_uri"],
                                  "2021-09-28T03:53:49.285Z") == item
    with pytest.raises(ValueError, match="sensing time differs"):
        acquisition._stac_item(item["id"], item["properties"]["s2:product_uri"],
                               "2021-09-28T03:53:50Z")
    item["properties"]["s2:processing_baseline"] = "03.01"
    with pytest.raises(ValueError, match="processing baseline differs"):
        acquisition._stac_item(item["id"], item["properties"]["s2:product_uri"], None)


def test_development_reuses_only_v1_hashed_file(tmp_path: Path) -> None:
    item = _item()
    path = tmp_path / acquisition.EXTERNAL_SUBDIRS["development"] / item["id"] / "blue.tif"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"sixbit")
    prior = {
        "scene_role": "event", "item_id": item["id"],
        "product_uri": item["properties"]["s2:product_uri"],
        "asset": "blue", "asset_url": item["assets"]["blue"]["href"],
        "file_size_bytes": "6", "sha256": hashlib.sha256(b"sixbit").hexdigest(),
        "source_edition": "element84_cog_of_l2a", "etag": "etag",
    }
    plan = acquisition.load_plan()
    row = acquisition._verify_development_asset(plan, "event", item, "blue", tmp_path, prior, None)
    assert row["sha256"] == prior["sha256"]
    assert row["scale"] == "0.0001" and row["offset"] == "-0.1"
    assert row["source_edition"] == "element84_cog_of_sentinel2_l2a"
    assert acquisition._verify_development_asset(plan, "event", item, "blue", tmp_path, prior, row) == row

    path.write_bytes(b"broken")
    with pytest.raises(ValueError, match="SHA-256 differs"):
        acquisition._verify_development_asset(plan, "event", item, "blue", tmp_path, prior, row)


def test_holdout_row_records_asset_transform_and_refuses_changed_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item()
    monkeypatch.setattr(acquisition, "_head", lambda url: (6, "etag"))

    def write_file(
        url: str, target: Path, size: int, etag: str, *, trusted_sha256: str | None = None,
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"sixbit")

    monkeypatch.setattr(acquisition, "_download_ranged", write_file)
    plan = acquisition.load_plan()
    row = acquisition._acquire_holdout_asset(plan, "event", item, "blue", tmp_path, None)
    assert row["source_edition"] == plan["source_edition"]
    assert row["scale"] == "0.0001" and row["offset"] == "-0.1"
    assert row["local_path_hint"].endswith("/earth_search/chaiyaphum_2021_v2/pinned/blue.tif")
    assert acquisition._acquire_holdout_asset(plan, "event", item, "blue", tmp_path, row) == row
    with pytest.raises(ValueError, match="manifest disagrees"):
        acquisition._acquire_holdout_asset(plan, "event", item, "blue", tmp_path,
                                           {**row, "asset_url": "https://different.test/blue.tif"})


def test_download_requires_verified_ranges_and_reuses_bound_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response(io.BytesIO):
        def __init__(self, body: bytes, content_range: str):
            super().__init__(body)
            self.status = 206
            self.headers = {"Content-Range": content_range, "ETag": "etag"}

    target = tmp_path / "blue.tif"
    monkeypatch.setattr(acquisition, "_RANGE_BYTES", 3)
    ranges: list[str] = []

    def serve(url: str, *, headers: dict[str, str]) -> Response:
        ranges.append(headers["Range"])
        return Response(b"abc" if len(ranges) == 1 else b"def",
                        "bytes 0-2/6" if len(ranges) == 1 else "bytes 3-5/6")

    monkeypatch.setattr(acquisition, "_urlopen", serve)
    acquisition._download_ranged("https://example.test/blue.tif", target, 6, "etag", trusted_sha256=None)
    assert target.read_bytes() == b"abcdef"
    assert ranges == ["bytes=0-2", "bytes=3-5"]
    assert target.with_suffix(".tif.part.json").exists()
    acquisition._download_ranged("https://example.test/blue.tif", target, 6, "etag", trusted_sha256=None)
    assert ranges == ["bytes=0-2", "bytes=3-5"]

    target.unlink()
    target.with_suffix(".tif.part").write_bytes(b"abc")
    target.with_suffix(".tif.part.json").write_text(
        json.dumps({"url": "https://different.test/blue.tif", "size": 6, "etag": "etag"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="different source"):
        acquisition._download_ranged("https://example.test/blue.tif", target, 6, "etag", trusted_sha256=None)


def test_manifest_refuses_duplicate_asset_rows(tmp_path: Path) -> None:
    path = tmp_path / "assets.csv"
    row = dict.fromkeys(acquisition.COLUMNS, "")
    row.update(item_id="same", asset="blue")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=acquisition.COLUMNS)
        writer.writeheader()
        writer.writerows((row, row))
    with pytest.raises(ValueError, match="duplicate item/asset"):
        acquisition._read_rows(path, acquisition.COLUMNS)
