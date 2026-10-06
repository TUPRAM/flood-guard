"""Delivered data do not self-authorize processing, shelter operation or capacity."""

import csv
import hashlib
import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from floodguard.evidence_facility_verification import validate_facility_verification
from floodguard.theos2_delivery import write_delivery_manifest


def test_unverified_shelter_remains_disabled():
    row = validate_facility_verification(
        {"facility_id": "source-1", "verified_role": "shelter"}, event_date="2024-09-15"
    )
    assert row["verification_status"] == "unverified"
    assert row["shelter_access_eligible"] is False
    assert row["event_available_capacity"] is None


def verified_facility():
    return {
        "facility_id": "source-1",
        "verified_role": "shelter",
        "coordinates": [99.8, 20.4],
        "entrance": [99.8001, 20.4],
        "capacity": 0,
        "effective_from": "2024-09-13",
        "effective_to": "2024-09-19",
        "verification_method": "dated_official_plan_and_entrance_review",
        "verification_status": "verified",
        "event_activation_verified": True,
        "capacity_verified": True,
        "evidence": [
            {
                "url": "https://example.org/report",
                "sha256": "a" * 64,
                "supports": claim,
                "observation_date": "2024-09-15",
            }
            for claim in ("role", "location", "entrance", "activation", "capacity")
        ],
    }


def test_capacity_zero_is_distinct_from_unknown_and_historical_date_matters():
    assert (
        validate_facility_verification(verified_facility(), event_date="2024-09-15")[
            "event_available_capacity"
        ]
        == 0
    )
    assert (
        validate_facility_verification(verified_facility(), event_date="2025-09-15")[
            "shelter_access_eligible"
        ]
        is False
    )
    record = verified_facility() | {"capacity": None, "capacity_verified": False}
    assert (
        validate_facility_verification(record, event_date="2024-09-15")[
            "event_available_capacity"
        ]
        is None
    )


@pytest.mark.parametrize(
    "change",
    [
        {"verification_method": "theos2"},
        {"phone": "private"},
        {"entrance": None},
        {"capacity": -1},
    ],
)
def test_invalid_or_personal_facility_fields_rejected(change):
    with pytest.raises(ValueError):
        validate_facility_verification(
            verified_facility() | change, event_date="2024-09-15"
        )


def delivery_fixture(tmp_path):
    raster = tmp_path / "scene.tif"
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(99, 21, 0.01, 0.01),
    ) as dst:
        dst.write(np.ones((10, 10), dtype="uint8"), 1)
    aois = tmp_path / "aois"
    aois.mkdir()
    for name, geometry in (
        ("inside", box(99.02, 20.92, 99.08, 20.98)),
        ("partial", box(99.05, 20.92, 99.15, 20.98)),
    ):
        (aois / (name + ".geojson")).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": mapping(geometry),
                            "properties": {},
                        }
                    ],
                }
            )
        )
    scene = {
        "scene_id": "T2-1",
        "file": "scene.tif",
        "acquisition_datetime": "2024-09-15T03:00:00Z",
        "product_level": "ORTHO",
        "band_order": ["PAN"],
    }
    metadata = tmp_path / "metadata.json"
    return scene, metadata, aois


def run_delivery(tmp_path, scene, metadata, aois):
    metadata.write_text(
        json.dumps(
            {"schema_version": "floodguard.theos2_delivery.v1", "scenes": [scene]}
        )
    )
    result = write_delivery_manifest(tmp_path, metadata, aois, tmp_path / "result.csv")
    return list(csv.DictReader(result.open()))


def test_theos_geometry_coverage_and_default_permission(tmp_path):
    scene, metadata, aois = delivery_fixture(tmp_path)
    rows = run_delivery(
        tmp_path, scene | {"permissions": {"local_processing": True}}, metadata, aois
    )
    assert all(r["processing_allowed"] == "False" for r in rows)
    assert rows[0]["aoi_fully_covered"] == "True"
    assert rows[1]["aoi_fully_covered"] == "False"
    assert float(rows[1]["aoi_coverage_fraction"]) == pytest.approx(0.5, abs=0.001)


def test_written_terms_and_band_count_are_bound(tmp_path):
    scene, metadata, aois = delivery_fixture(tmp_path)
    terms = tmp_path / "terms.txt"
    terms.write_bytes(b"fixture-only written terms")
    scene |= {
        "written_terms": {
            "file": "terms.txt",
            "sha256": hashlib.sha256(terms.read_bytes()).hexdigest(),
        },
        "permissions": {"local_processing": True},
    }
    assert (
        run_delivery(tmp_path, scene, metadata, aois)[0]["processing_allowed"] == "True"
    )
    terms.write_bytes(b"changed")
    with pytest.raises(ValueError, match="licence evidence"):
        run_delivery(tmp_path, scene, metadata, aois)
    with pytest.raises(ValueError, match="band order"):
        run_delivery(tmp_path, scene | {"band_order": ["red", "blue"]}, metadata, aois)


def test_unsafe_theos_path_rejected(tmp_path):
    scene, metadata, aois = delivery_fixture(tmp_path)
    with pytest.raises(ValueError):
        run_delivery(tmp_path, scene | {"file": "../elsewhere.tif"}, metadata, aois)
