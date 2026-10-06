"""Original-scene intake rejects corrupt bytes and incompatible acquisition pairs."""

import csv
import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest
from shapely.geometry import box, mapping


@pytest.mark.parametrize("damage", [None, "checksum", "coverage", "orbit", "size"])
def test_hat_yai_original_intake(tmp_path, monkeypatch, damage):
    script = Path(__file__).resolve().parents[1] / "scripts/register_hat_yai_safe.py"
    spec = importlib.util.spec_from_file_location("hat_yai_intake", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "repo"
    for directory in (root / "resources/aoi/upload", root / "outputs", tmp_path / "downloads", tmp_path / "catalog"):
        directory.mkdir(parents=True)
    monkeypatch.setattr(module, "__file__", str(root / "scripts/register_hat_yai_safe.py"))
    (root / "resources/aoi/upload/aoi-03_hat_yai_core.geojson").write_text(json.dumps({"features": [{"geometry": mapping(box(100, 7, 101, 8))}]}))
    for phase in ("before", "after"):
        name = "S1A_IW_GRDH_1SDV_202511" + ("11" if phase == "before" else "23") + ".SAFE"
        source = tmp_path / "downloads" / (name + ".zip")
        orbit = "2" if damage == "orbit" and phase == "after" else "1"
        xml = f"<root><relativeOrbitNumber>{orbit}</relativeOrbitNumber><pass>ASCENDING</pass><mode>IW</mode><transmitterReceiverPolarisation>VV</transmitterReceiverPolarisation><transmitterReceiverPolarisation>VH</transmitterReceiverPolarisation></root>"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr(name + "/manifest.safe", xml)
        product = {"Id": phase, "Name": name, "ContentLength": source.stat().st_size + (1 if damage == "size" else 0), "Checksum": [{"Algorithm": "MD5", "Value": "0" * 32 if damage == "checksum" else hashlib.md5(source.read_bytes(), usedforsecurity=False).hexdigest()}], "GeoFootprint": mapping(box(0, 0, 1, 1) if damage == "coverage" else box(99, 6, 102, 9)), "ContentDate": {"Start": "2025-11-11T23:00:00Z"}}
        (tmp_path / "catalog" / ("cdse_" + phase + ".txt")).write_text(json.dumps(product))
    monkeypatch.setattr(sys, "argv", [str(script), "--downloads", str(tmp_path / "downloads"), "--external-data-root", str(tmp_path / "external"), "--catalog-dir", str(tmp_path / "catalog"), "--receipt", str(tmp_path / "receipt.json")])
    if damage:
        with pytest.raises(ValueError):
            module.main()
        assert not (root / "outputs/cdse_hat_yai_acquisition_manifest.csv").exists()
    else:
        module.main()
        with (root / "outputs/cdse_hat_yai_acquisition_manifest.csv").open() as stream:
            records = list(csv.DictReader(stream))
        assert len(records) == 2
        assert all(row["processing_allowed"] == "False" for row in records)
        assert all(len(row["sha256"]) == 64 for row in records)
        assert json.loads((tmp_path / "receipt.json").read_bytes())["qualified_for_validation"] is False
        manifest = root / "outputs/cdse_hat_yai_acquisition_manifest.csv"
        original = manifest.read_bytes()
        assert b"\r\n" not in original
        module.main()
        assert manifest.read_bytes() == original
