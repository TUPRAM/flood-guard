"""Lineage enrichment cannot promote rights or event-time facility claims."""

import csv
import hashlib
import json

import pytest

from floodguard.evidence_review import build_facility_crosswalk, enrich_registry


def test_enrichment_adds_verified_parent_and_preserves_temporal_rights(tmp_path):
    folder = tmp_path / "shelters"
    folder.mkdir()
    source = folder / "dpm-gd002_final2.csv"
    source.write_text("name\nHall\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    derived = folder / "core_shelters.geojson"
    derived.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    with (tmp_path / "FILES_SHA256.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "bytes", "sha256"])
        writer.writeheader()
        writer.writerow(
            {
                "path": "shelters/dpm-gd002_final2.csv",
                "bytes": source.stat().st_size,
                "sha256": digest,
            }
        )
    (folder / "provenance.json").write_text(
        json.dumps(
            [
                {
                    "file": source.name,
                    "source_url": "https://catalog.disaster.go.th/source.csv",
                    "retrieved_at_utc": "2026-09-21T14:00:00+08:00",
                    "sha256": digest,
                }
            ]
        )
    )
    registry = {
        "assets": [
            {
                "id": "clip",
                "relative_path": "shelters/core_shelters.geojson",
                "sha256": "cliphash",
                "family": "shelters",
                "role": "derivative",
            }
        ],
        "datasets": [
            {
                "number": 12,
                "family": "shelters",
                "asset_ids": ["clip"],
                "source_urls": [],
                "rights": {"public_derivatives": False},
                "temporal": {"activation_date": None},
            }
        ],
    }
    updated = enrich_registry(
        registry, tmp_path, {"datasets": {"shelters": {"status": "normalized"}}}
    )
    assert len(updated["assets"]) == 2
    clip = next(a for a in updated["assets"] if a["id"] == "clip")
    assert clip["parent_hashes"] == [digest]
    assert clip["crs"] == "EPSG:4326"
    assert clip["parent_retrieval_times_utc"] == ["2026-09-21T06:00:00+00:00"]
    assert updated["datasets"][0]["temporal"] == {"activation_date": None}
    assert updated["datasets"][0]["rights"] == {"public_derivatives": False}
    assert len(registry["assets"]) == 1  # Input is not mutated.
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity failure"):
        enrich_registry(registry, tmp_path, {})


def test_crosswalk_current_identity_does_not_accept_historical_availability(tmp_path):
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [99, 20]},
        "properties": {
            "record_id": "health:hash:1",
            "source_feature_index": 1,
            "aoi_matches": ["aoi-01_mae_sai_core"],
            "source_properties": {"Agency": "Test hospital"},
        },
    }
    (tmp_path / "healthcare_candidates.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": [feature]})
    )
    review = [
        {
            "source_record_id": "health:hash:1",
            "official_facility_id": "EA0011111",
            "source_url": "https://hcode.moph.go.th/code/1/",
            "name_match": True,
            "address_match": True,
        }
    ]
    result = build_facility_crosswalk(tmp_path, tmp_path / "review", review)
    assert result["supported_identity_matches"] == 1
    row = result["rows"][0]
    assert row["coordinate_verified"] is False
    assert row["identity_merge_approved"] is False
    assert row["event_available_capacity"] is None
    assert row["event_availability"] == "unknown"
    review[0]["address_match"] = False
    assert (
        build_facility_crosswalk(tmp_path, tmp_path / "review", review)[
            "unresolved_identities"
        ]
        == 1
    )


def test_crosswalk_rejects_wrong_source_record(tmp_path):
    with pytest.raises(ValueError, match="absent core source records"):
        build_facility_crosswalk(
            tmp_path, tmp_path / "review", [{"source_record_id": "not-in-source"}]
        )
