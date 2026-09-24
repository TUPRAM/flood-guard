"""The age-access bridge preserves source mass and unknown routing coverage."""

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from floodguard.evidence_age_surface import AGE_BANDS

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/bridge_worldpop_age_access.py"
SPEC = importlib.util.spec_from_file_location("bridge_worldpop_age_access", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _cell(unit, col, groups):
    return {"unit_id": unit, "raster_row": 0, "raster_col": col,
            "fractional_source_cell": 1.0, "covered_m2": 10000.0,
            "band_counts": {}, "groups": groups}


def _pop(pid, lon, count):
    return {"population_id": pid, "subdistrict_id": "A", "longitude": lon,
            "latitude": 0.5, "total_population": count}


def test_allocation_conserves_each_source_cell_and_keeps_no_support_unknown():
    transform = from_origin(0, 1, 1, 1)
    cells = [
        _cell("A", 0, {"children_0_14": 8.0, "older_60_plus": 4.0,
                       "other_15_59": 12.0}),
        _cell("A", 1, {"children_0_14": 2.0, "older_60_plus": 1.0,
                       "other_15_59": 3.0}),
        _cell("A", 2, {"children_0_14": 0.0, "older_60_plus": 0.0,
                       "other_15_59": 0.0}),
    ]
    nodes, unknown, ledger, coverage = MODULE.allocate_cell_masses(
        cells, [_pop("one", 0.1, 1), _pop("three", 0.2, 3),
                _pop("zero-source", 2.1, 1)], transform)
    assert nodes["one"] == pytest.approx({"children_0_14": 2, "older_60_plus": 1,
                                           "other_15_59": 3})
    assert nodes["three"] == pytest.approx({"children_0_14": 6, "older_60_plus": 3,
                                             "other_15_59": 9})
    assert nodes["zero-source"]["children_0_14"] == 0
    assert unknown["A"] == {"children_0_14": 2, "older_60_plus": 1,
                            "other_15_59": 3}
    assert ledger[1]["unknown_no_2020_support"]["children_0_14"] == 2
    assert coverage["2020_demand_population_without_age_source_support"] == 0


def test_invalid_age_source_never_becomes_zero_and_duplicate_demand_fails():
    transform = from_origin(0, 1, 1, 1)
    cells = [_cell("A", 0, None)]
    nodes, unknown, ledger, coverage = MODULE.allocate_cell_masses(
        cells, [_pop("p", 0.1, 5)], transform)
    assert nodes == {} and unknown == {}
    assert ledger[0]["source_supported"] is False
    assert coverage["2020_demand_population_without_age_source_support"] == 5
    with pytest.raises(ValueError, match="IDs and positive counts"):
        MODULE.allocate_cell_masses(cells, [_pop("p", 0.1, 5), _pop("p", 0.2, 2)], transform)


def test_missing_connector_is_bounded_and_zero_zero_ratio_is_null():
    source = {"units": {"A": {
        "source_supported_population": 40.0,
        "source_supported_area_km2": 1.0,
        "source_unsupported_area_km2": 0.0,
        "groups": {"children_0_14": 15.0, "older_60_plus": 8.0,
                   "other_15_59": 17.0},
    }}}
    nodes = {
        "connected": {"children_0_14": 5.0, "older_60_plus": 2.0,
                      "other_15_59": 8.0},
        "unsnapped": {"children_0_14": 5.0, "older_60_plus": 3.0,
                      "other_15_59": 7.0},
    }
    result = {"node_results": [
        {"population_id": "connected", "subdistrict_id": "A",
         "snap_status": "connected", "normal_access_minutes": 20,
         "scenario_access_minutes": 40},
        {"population_id": "unsnapped", "subdistrict_id": "A",
         "snap_status": "no_nearby_graph_node", "normal_access_minutes": None,
         "scenario_access_minutes": None},
    ]}
    by_unit, aoi, equity = MODULE._access_summary(
        source, nodes,
        {"A": {"children_0_14": 5, "older_60_plus": 3,
               "other_15_59": 2}}, result)
    child = by_unit["A"]["groups"]["children_0_14"]
    assert child["new_threshold_loss"]["30"] == 5
    assert child["new_threshold_loss"]["15"] == 0
    assert child["access_unknown"] == 10
    assert aoi["groups"]["children_0_14"]["denominator"] == 15
    thirty = next(row for row in equity if row["unit_id"] == "A"
                  and row["contrast"] == "children_vs_15_plus"
                  and row["threshold_minutes"] == 30)
    assert thirty["vulnerable_access_loss_rate_lower_bound"] == pytest.approx(1 / 3)
    assert thirty["vulnerable_access_loss_rate_upper_bound"] == 1
    fifteen = next(row for row in equity if row["unit_id"] == "A"
                   and row["contrast"] == "children_vs_15_plus"
                   and row["threshold_minutes"] == 15)
    assert fifteen["equity_gap_ratio"] is None
    assert fifteen["equity_ratio_unavailable_reason"] == "comparison_loss_rate_zero"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_byte_bound_age_source_rejects_tampered_band(tmp_path):
    source = tmp_path / "age"
    source.mkdir()
    files = []
    for band in AGE_BANDS:
        name = f"tha_t_{band}_2024_CN_1km_R2025A_UA_v1.tif"
        path = source / name
        with rasterio.open(path, "w", driver="GTiff", width=1, height=1,
                           count=1, dtype="float32", crs="EPSG:4326",
                           transform=from_origin(99, 21, 1, 1)) as target:
            target.write(np.array([[1]], dtype="float32"), 1)
        files.append({"band": band, "file": name, "bytes": path.stat().st_size,
                      "sha256": _sha(path), "url":
                      "https://data.worldpop.org/GIS/AgeSex_structures/"
                      f"Global_2015_2030/R2025A/2024/THA/v1/1km_ua/constrained/{name}"})
    manifest = source / "acquisition_manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "floodguard.worldpop_age_acquisition.v1",
        "status": "PASS", "year_represented": 2024, "resolution_code": "1km",
        "product": "Global2 R2025A v1", "files": files,
    }), encoding="utf-8")
    aoi = tmp_path / "aoi.geojson"
    units = tmp_path / "units.geojson"
    aoi.write_text("{}", encoding="utf-8")
    units.write_text("{}", encoding="utf-8")
    review = tmp_path / "age_review.json"
    review.write_text(json.dumps({
        "schema_version": "floodguard.worldpop_age_review.v1",
        "status": "modelled_research_candidate", "year_represented": 2024,
        "source_resolution": "1km", "source_acquisition_manifest_sha256": _sha(manifest),
        "aoi_geometry_sha256": _sha(aoi), "unit_geometry_sha256": _sha(units),
        "official_warning": False, "accepted_exposure": None,
        "accepted_equity": None, "accepted_fpps": None,
        "age_groups": {"children": "0-14 inclusive", "older_adults": "60+ inclusive",
                       "other": "15-59 inclusive"},
    }), encoding="utf-8")
    (tmp_path / "receipt.json").write_text(json.dumps({
        "output_sha256": _sha(review),
        "source_acquisition_manifest_sha256": _sha(manifest),
    }), encoding="utf-8")
    assert len(MODULE._check_age_sources(manifest, review, units, aoi)[2]) == 20
    (source / files[0]["file"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="byte identity failed"):
        MODULE._check_age_sources(manifest, review, units, aoi)
