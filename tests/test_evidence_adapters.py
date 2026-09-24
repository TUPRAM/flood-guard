"""Synthetic source fixtures exercise unknowns, provenance and geometry semantics."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from floodguard.evidence_adapters import (
    _facilities,
    _gauges,
    _population,
    _roads,
    _utc,
    normalize_bundle,
)
from floodguard.evidence_adapters_geo import normalize_geospatial


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def paths(tmp_path):
    root, out = tmp_path / "source", tmp_path / "output"
    root.mkdir()
    out.mkdir()
    return root, out


@pytest.fixture
def aois():
    return {
        "core": {
            "type": "Polygon",
            "coordinates": [[[99, 19], [100, 19], [100, 20], [99, 20], [99, 19]]],
        }
    }


def gauge_fixture(root):
    path = root / "thaiwater/202409/TEST.csv"
    write_csv(
        path,
        ["station_code", "measure_datetime", "water_level", "quality_flag"],
        [
            {
                "station_code": "TEST",
                "measure_datetime": "2024-09-01 00:00:00",
                "water_level": "2.1",
                "quality_flag": "N",
            },
            {
                "station_code": "TEST",
                "measure_datetime": "2024-09-01 00:10:00",
                "water_level": "null",
                "quality_flag": "null",
            },
            {
                "station_code": "TEST",
                "measure_datetime": "2024-09-01 00:20:00",
                "water_level": "2.2",
                "quality_flag": "N",
            },
            {
                "station_code": "TEST",
                "measure_datetime": "2024-09-01 00:30:00",
                "water_level": "2.3",
                "quality_flag": "N",
            },
            {
                "station_code": "TEST",
                "measure_datetime": "2024-09-01 00:30:00",
                "water_level": "9.9",
                "quality_flag": "N",
            },
            {
                "station_code": "TEST",
                "measure_datetime": "bad",
                "water_level": "999999",
                "quality_flag": "N",
            },
            {
                "station_code": "OTHER",
                "measure_datetime": "2024-09-01 00:50:00",
                "water_level": "3",
                "quality_flag": "N",
            },
        ],
    )
    meta = root / "thaiwater/202409/0station_metadata.csv"
    meta.write_text(
        ",".join(f"h{i}" for i in range(12))
        + "\n"
        + ",".join(str(i) for i in range(15))
        + "\n",
        encoding="utf-8",
    )
    write_json(
        root / "thaiwater/manifest.json",
        [
            {
                "kind": "water_level_observations",
                "path": "202409/TEST.csv",
                "station_code": "TEST",
                "source_period": "202409",
                "longitude": 99.5,
                "latitude": 19.5,
                "retrieved_utc": "2026-09-21T14:40:00+08:00",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            {
                "kind": "monthly_station_metadata",
                "path": "202409/0station_metadata.csv",
            },
        ],
    )


def test_gauge_gaps_duplicates_timezone_and_schema(paths, aois):
    pytest.importorskip("shapely")
    root, out = paths
    gauge_fixture(root)
    summary = _gauges(root, out, aois)
    row = summary["station_months"][0]
    assert row["retrieved_at_utc"] == "2026-09-21T06:40:00+00:00"
    assert row["observation_timezone"] == "unconfirmed"
    assert row["expected_slots"] == 4320
    assert row["numeric_slots"] == 2
    assert row["conflicting_slots"] == 1
    assert row["duplicate_timestamp_rows"] == 1
    assert row["invalid_timestamp_rows"] == 1
    assert row["station_code_mismatches"] == 1
    assert row["aoi_matches"] == ["core"]
    assert summary["schema_mismatches"] == 1
    segments = json.loads((out / "gauge_hydrograph_segments.json").read_text())[
        "series"
    ][0]["segments"]
    assert len(segments) == 2
    assert [len(s) for s in segments] == [1, 1]
    normalized = list(
        csv.DictReader((out / "gauge_observations.csv").open(encoding="utf-8-sig"))
    )
    assert all(r["timestamp_utc"] == "" for r in normalized)
    assert normalized[1]["water_level_m_msl"] == ""
    assert row["event_peak_verified"] is False


def test_source_hash_mismatch_fails_closed(paths, aois):
    root, out = paths
    gauge_fixture(root)
    with (root / "thaiwater/202409/TEST.csv").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="Source hash mismatch"):
        _gauges(root, out, aois)


def test_population_preserves_year_gaps_arithmetic_and_overlapping_labels(paths):
    root, out = paths
    path = root / "dopa/chiang_rai/test.csv"
    fields = ["ปี", "รายการ", "อำเภอ", " ชาย ", " หญิง ", " รวม "]
    rows = [
        ["2568", "วัยเด็ก", "แม่สาย", "10", "10", "20"],
        ["2568", "วัยแรงงาน", "แม่สาย", "40", "40", "80"],
        ["2568", "ผู้สูงอายุ (60 ปีขึ้นไป)", "แม่สาย", "10", "10", "20"],
        ["2568", "ผู้สูงอายุ (65 ปีขึ้นไป)", "แม่สาย", "5", "5", "10"],
        ["2568", "จำนวนประชากร", "แม่สาย", "80", "77", "157"],
        ["2563", "ผู้สูงอายุ (60 ปีขึ้นไป)", "แม่สาย", "10", "10", "99"],
    ]
    write_csv(path, fields, [dict(zip(fields, r)) for r in rows])
    write_json(
        root / "dopa/manifest.json",
        [{"kind": "population_csv", "path": "chiang_rai/test.csv"}],
    )
    result = _population(root, out)
    assert result["chiang_rai_2024_age_available"] is False
    assert result["arithmetic_mismatches"] == 1
    comparison = next(r for r in result["mae_sai_comparisons"] if r["year_ce"] == 2025)
    assert comparison["age_category_sum"] == 120  # 65+ subset is not added.
    assert comparison["difference_total_minus_categories"] == 37
    assert result["administrative_crosswalk"] == "unresolved"
    content = (out / "population_context.csv").read_text(encoding="utf-8-sig")
    assert "2568" in content and "2025" in content


def test_facility_identity_unknowns_and_privacy(paths, aois):
    pytest.importorskip("shapely")
    root, out = paths
    fields = [
        "จังหวัด",
        "อำเภอ",
        "ตำบล",
        "หมู่บ้าน/ชุมชน",
        "สถานที่",
        "รองรับ",
        "ละติจูด",
        "ลองจิจูด",
        "โทรศัพท์",
    ]
    rows = [
        [
            "เชียงราย",
            "แม่สาย",
            "test",
            "1",
            "Shared hall",
            "50",
            "19.5",
            "99.5",
            "PRIVATE",
        ],
        [
            "เชียงราย",
            "แม่สาย",
            "test",
            "2",
            "Shared hall",
            "50",
            "19.5",
            "99.5",
            "PRIVATE",
        ],
        ["เชียงราย", "แม่สาย", "test", "3", "Unlocated", "unknown", "", "", "PRIVATE"],
    ]
    write_csv(
        root / "shelters/dpm-gd002_final2.csv",
        fields,
        [dict(zip(fields, r)) for r in rows],
    )
    write_json(
        root / "healthcare/thailand_health_facilities_th.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "ID": 1,
                        "Agency": "Hospital",
                        "Telephone": "PRIVATE",
                    },
                    "geometry": {"type": "Point", "coordinates": [99.5, 19.5]},
                },
                {
                    "type": "Feature",
                    "properties": {"ID": 1, "Agency": "Other"},
                    "geometry": {"type": "Point", "coordinates": [99.6, 19.6]},
                },
            ],
        },
    )
    shelters, health = _facilities(root, out, aois)
    assert shelters["records"] == 3
    assert shelters["invalid_coordinate_records"] == 1
    assert shelters["unknown_planning_capacity_records"] == 1
    assert shelters["distinct_coordinates"] == 1
    assert shelters["aoi_counts"]["core"] == 2
    assert health["distinct_source_ids"] == 1
    doc = json.loads((out / "shelter_candidates.geojson").read_text(encoding="utf-8"))
    assert len({f["id"] for f in doc["features"]}) == 2
    assert all(
        f["properties"]["event_available_capacity"] is None for f in doc["features"]
    )
    assert all(
        f["properties"]["records_sharing_coordinate"] == 2 for f in doc["features"]
    )
    assert "PRIVATE" not in (out / "shelter_records.csv").read_text(
        encoding="utf-8-sig"
    )
    assert "PRIVATE" not in (out / "healthcare_candidates.geojson").read_text(
        encoding="utf-8"
    )


def test_polygon_hole_is_not_aoi_membership(paths):
    pytest.importorskip("shapely")
    from floodguard.evidence_adapters import _point_membership

    aoi = {
        "hole": {
            "type": "Polygon",
            "coordinates": [
                [[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]],
                [[1, 1], [1, 2], [2, 2], [2, 1], [1, 1]],
            ],
        }
    }
    assert _point_membership(1.5, 1.5, aoi) == []
    assert _point_membership(0, 1, aoi) == ["hole"]


def test_flood_footprint_keeps_unobserved_not_dry(paths, aois):
    pytest.importorskip("shapely")
    pytest.importorskip("pyproj")
    root, out = paths
    filename = "half.geojson"
    write_json(
        root / "flood_reference" / filename,
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[99, 19], [99.5, 19], [99.5, 20], [99, 20], [99, 19]]
                        ],
                    },
                }
            ],
        },
    )
    write_json(
        root / "flood_reference/manifest.json",
        {
            "clips": [
                {
                    "path": filename,
                    "aoi": "core",
                    "layer": "CHIANGRAI_20240801_20241022_AnalysisExtent",
                }
            ]
        },
    )
    result = normalize_geospatial(root, out, aois)["flood_reference"]
    assert 0.49 < result["aois"]["core"]["analysis_coverage_fraction"] < 0.51
    assert result["aois"]["core"]["event_reference_accepted"] is False
    mask = json.loads((out / "flood_core_unobserved.geojson").read_text())
    assert mask["features"][0]["properties"]["role"] == "unobserved_not_dry"
    assert result["aois"]["core"]["unobserved_area_km2"] > 0


def test_projected_slope_keeps_negative_source_values(paths, aois):
    rasterio = pytest.importorskip("rasterio")
    np = pytest.importorskip("numpy")
    root, out = paths
    path = root / "terrain_drainage/core_copdem_glo30.tif"
    path.parent.mkdir()
    values = np.arange(100, dtype="float32").reshape(10, 10) - 10
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=rasterio.transform.from_origin(99.5, 19.5, 0.0003, 0.0003),
    ) as dst:
        dst.write(values, 1)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = normalize_geospatial(root, out, aois)["terrain"]
    row = result["rasters"][0]
    assert row["negative_pixels"] == 10
    assert row["min_m"] == -10
    assert row["analysis_crs"] == "EPSG:32647"
    assert row["event_observation_interval"] is None
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    with rasterio.open(out / row["slope_output"]) as slope:
        assert str(slope.crs) == "EPSG:32647"
        assert slope.res == (30, 30)


def test_road_status_does_not_become_closure_geometry(paths):
    root, out = paths
    rows = [
        {
            "km_start": "7+000",
            "km_end": "8+000",
            "traffic_status_original_th": "การจราจรผ่านได้ไม่สะดวก",
            "quality_note": "chainage conflict",
            "source_date": "2024-09-11",
        },
        {
            "km_start": "9+650",
            "km_end": "9+650",
            "traffic_status_original_th": "การจราจรผ่านไม่ได้",
            "quality_note": "",
            "source_date": "2024-09-11",
        },
    ]
    write_csv(
        root / "roads/official_reports/test_incidents_transcribed.csv",
        list(rows[0]),
        rows,
    )
    result = _roads(root, out)
    assert result["states"] == {
        "reported_passable_with_difficulty": 1,
        "reported_impassable": 1,
    }
    assert result["spatially_accepted_closures"] == 0
    records = list(
        csv.DictReader(
            (out / "road_documentary_evidence.csv").open(encoding="utf-8-sig")
        )
    )
    assert records[0]["chainage_start_m"] == "7000"
    assert records[0]["closure_geometry"] == ""


def test_output_cannot_overwrite_source_and_utc_is_never_assumed(paths):
    root, _ = paths
    with pytest.raises(ValueError, match="outside the immutable"):
        normalize_bundle(root, root / "processed", {})
    assert _utc("2024-09-01 00:00:00") is None


def test_empty_bundle_is_explicit_and_deterministic(paths):
    root, out = paths
    result = normalize_bundle(root, out, {})
    first = (out / "adapter_summary.json").read_bytes()
    assert result["datasets"]["gauges"]["status"] == "unavailable"
    assert result["datasets"]["population"]["status"] == "unavailable"
    normalize_bundle(root, out, {})
    assert (out / "adapter_summary.json").read_bytes() == first
