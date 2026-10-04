"""Local plots preserve source gaps and do not expose contact fields."""

import csv
import json

import pytest

from floodguard.evidence_local_report import render_local_report


def fixture(tmp_path):
    normalized = tmp_path / "normalized"
    normalized.mkdir()
    series = {
        "station_code": "TEST",
        "month": "202511",
        "source_sha256": "a" * 64,
        "missing_slots": 4315,
        "segments": [
            [["2025-11-01T00:00:00", 1], ["2025-11-01T00:10:00", 2]],
            [["2025-11-01T00:30:00", 9]],
            [["2025-11-01T00:50:00", 3], ["2025-11-01T01:00:00", 4]],
        ],
    }
    (normalized / "gauge_hydrograph_segments.json").write_text(
        json.dumps({"units": "m above MSL", "series": [series]})
    )
    registry = {
        "generated_at": "2026-09-21T00:00:00Z",
        "source_inventory_sha256": "b" * 64,
        "verified_asset_count": 175,
    }
    summary = {
        "datasets": {
            "gauges": {
                "station_month_files": 1,
                "stations": 1,
                "rows": 4320,
                "numeric_slots": 5,
                "station_months": [
                    {
                        "station_code": "TEST",
                        "month": "202511",
                        "numeric_slots": 5,
                        "expected_slots": 4320,
                    }
                ],
            }
        },
        "aois": {},
    }
    return normalized, registry, summary


def test_local_report_plots_separate_segments_and_singleton_without_interpolation(
    tmp_path,
):
    _, registry, summary = fixture(tmp_path)
    path = render_local_report(tmp_path, registry, summary)
    document = path.read_text(encoding="utf-8")
    assert path.name == "local_evidence_report.html"
    assert document.count('data-observed-segment="true"') == 2
    assert document.count('data-observed-singleton="true"') == 1
    assert "Maximum observed: 9.000" in document
    assert "not a verified event peak" in document
    assert "timezone unconfirmed" in document
    assert "LOCAL RESEARCH ONLY" in document
    assert 'href="normalized/gauge_hydrograph_segments.json"' in document
    assert str(tmp_path) not in document
    assert "<script" not in document


def test_missing_station_month_is_not_a_zero_line(tmp_path):
    normalized, registry, summary = fixture(tmp_path)
    doc = json.loads((normalized / "gauge_hydrograph_segments.json").read_text())
    doc["series"][0]["segments"] = []
    (normalized / "gauge_hydrograph_segments.json").write_text(json.dumps(doc))
    html = render_local_report(tmp_path, registry, summary).read_text()
    assert "No usable numeric observations" in html
    assert "data-observed-segment" not in html


def test_segment_crossing_missing_slot_is_rejected(tmp_path):
    normalized, registry, summary = fixture(tmp_path)
    doc = json.loads((normalized / "gauge_hydrograph_segments.json").read_text())
    doc["series"][0]["segments"] = [
        [["2025-11-01T00:00:00", 1], ["2025-11-01T00:30:00", 2]]
    ]
    (normalized / "gauge_hydrograph_segments.json").write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="crosses a missing"):
        render_local_report(tmp_path, registry, summary)


def test_contact_fields_are_not_rendered_and_display_text_is_escaped(tmp_path):
    normalized, registry, summary = fixture(tmp_path)
    with (normalized / "shelter_records.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "place_name",
                "phone",
                "ชื่อผู้ประสานงาน",
                "aoi_matches",
                "planning_capacity",
                "site_identity_status",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "place_name": '<script>alert("x")</script>',
                "phone": "PRIVATE_PHONE",
                "ชื่อผู้ประสานงาน": "PRIVATE_PERSON",
                "aoi_matches": '["aoi-01_test"]',
                "planning_capacity": "50",
                "site_identity_status": "unresolved",
            }
        )
    html = render_local_report(tmp_path, registry, summary).read_text(encoding="utf-8")
    assert "PRIVATE_PHONE" not in html and "PRIVATE_PERSON" not in html
    assert "&lt;script&gt;" in html and "<script>alert" not in html
    assert "Unverified planned capacity" in html


def test_report_requires_every_inventory_series(tmp_path):
    _, registry, summary = fixture(tmp_path)
    summary["datasets"]["gauges"]["station_month_files"] = 106
    with pytest.raises(ValueError, match="count differs"):
        render_local_report(tmp_path, registry, summary)


def test_report_does_not_replace_a_station_with_another_series(tmp_path):
    _, registry, summary = fixture(tmp_path)
    summary["datasets"]["gauges"]["station_months"][0]["station_code"] = "DIFFERENT"
    with pytest.raises(ValueError, match="identities differ"):
        render_local_report(tmp_path, registry, summary)


def test_report_cannot_be_written_inside_hosted_assets(tmp_path):
    with pytest.raises(ValueError, match="hosted public"):
        render_local_report(tmp_path / "apps" / "web" / "public", {}, {})
