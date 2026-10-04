"""The age review accepts only a complete byte-bound source release."""

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from floodguard.evidence_age_surface import AGE_BANDS

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_worldpop_age_review.py"
SPEC = importlib.util.spec_from_file_location("build_worldpop_age_review", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
build_review = MODULE.build_review


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _feature(path, geometry, properties):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": properties, "geometry": mapping(geometry)}
    ]}), encoding="utf-8")


def _fixture(tmp_path):
    acquired = tmp_path / "source"
    acquired.mkdir()
    records = []
    for band in AGE_BANDS:
        name = f"tha_t_{band}_2024_CN_1km_R2025A_UA_v1.tif"
        path = acquired / name
        with rasterio.open(path, "w", driver="GTiff", width=1, height=1, count=1,
                           dtype="float32", crs="EPSG:4326", nodata=-99999,
                           transform=from_origin(99.8, 20.4, 0.001, 0.001)) as target:
            target.write(np.array([[1]], dtype="float32"), 1)
        records.append({
            "band": band, "file": name, "bytes": path.stat().st_size,
            "sha256": _sha(path),
            "url": "https://data.worldpop.org/GIS/AgeSex_structures/"
                   f"Global_2015_2030/R2025A/2024/THA/v1/1km_ua/constrained/{name}",
        })
    manifest = acquired / "acquisition_manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "floodguard.worldpop_age_acquisition.v1",
        "status": "PASS", "year_represented": 2024, "resolution_code": "1km",
        "product": "Global2 R2025A v1, Thailand constrained total-sex age estimates",
        "files": records,
    }), encoding="utf-8")
    units = tmp_path / "units.geojson"
    aoi = tmp_path / "aoi.geojson"
    _feature(units, box(99.8, 20.399, 99.801, 20.4),
             {"subdistrict_id": "TH570901", "boundary_valid_on": "2022-01-22"})
    _feature(aoi, box(99.8, 20.399, 99.8005, 20.4), {"aoi_id": "AOI-TEST"})
    return manifest, units, aoi


def test_build_review_preserves_full_unit_and_partial_aoi_without_acceptance(tmp_path):
    manifest, units, aoi = _fixture(tmp_path)
    output = tmp_path / "output"
    receipt = build_review(manifest, units, aoi, output)
    data = json.loads((output / "age_review.json").read_text(encoding="utf-8"))
    row = data["units"][0]
    assert row["full_unit"]["population_estimate"] == pytest.approx(20)
    assert row["aoi_intersection"]["population_estimate"] == pytest.approx(10, rel=0.001)
    assert row["aoi_intersection"]["children_0_14_estimate"] == pytest.approx(2, rel=0.001)
    assert data["accepted_equity"] is None
    assert data["official_warning"] is False
    assert receipt["output_sha256"] == _sha(output / "age_review.json")


@pytest.mark.parametrize("mutation", ["url", "file", "bytes"])
def test_review_rejects_swapped_source_identity(tmp_path, mutation):
    manifest, units, aoi = _fixture(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if mutation == "url":
        data["files"][0]["url"] = "https://example.org/other.tif"
    elif mutation == "file":
        data["files"][0]["file"] = "../other.tif"
    else:
        source = manifest.parent / data["files"][0]["file"]
        source.write_bytes(source.read_bytes() + b"tampered")
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="source URL|filename|byte identity"):
        build_review(manifest, units, aoi, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_review_rejects_non_wgs84_declared_geometry(tmp_path):
    manifest, units, aoi = _fixture(tmp_path)
    data = json.loads(aoi.read_text(encoding="utf-8"))
    data["crs"] = {"type": "name", "properties": {"name": "EPSG:32647"}}
    aoi.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="WGS84"):
        build_review(manifest, units, aoi, tmp_path / "output")
    assert not (tmp_path / "output").exists()
