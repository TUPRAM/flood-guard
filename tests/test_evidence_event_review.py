"""Open, synthetic fixtures for administrative scope and event eligibility."""

import json

import pytest
from shapely.geometry import Polygon, box, mapping

from floodguard import evidence_event_review as review


def unit(code, geometry, **properties):
    return {
        "type": "Feature",
        "properties": {"adm3_pcode": code, **properties},
        "geometry": mapping(geometry),
    }


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def event():
    return {"id": "event", "start": "2024-09-01", "end": "2024-09-30"}


def product(**overrides):
    return {
        "id": "candidate",
        "start": "2024-09-13",
        "end": "2024-09-19",
        "vector_or_raster_available": True,
        "public_derivatives": True,
        "source_snapshot_verified": True,
        **overrides,
    }


@pytest.mark.parametrize(
    "raw,expected",
    [(570901, "TH570901"), (" th570901 ", "TH570901"), ("010101", "TH010101")],
)
def test_codes_are_exact_and_keep_leading_zero(raw, expected):
    assert review.normalize_adm3_code(raw) == expected


@pytest.mark.parametrize(
    "raw", ["5709", "57090101", "Mae Sai", "570901.0", "THTH570901", "57090X"]
)
def test_names_districts_villages_and_decimal_codes_do_not_join(raw):
    with pytest.raises(ValueError, match="Not an ADM3 code"):
        review.normalize_adm3_code(raw)


def test_partial_units_use_distinct_denominators_and_retained_full_geometry():
    first = unit("570901", box(99, 15, 101, 16), name="One")
    second = unit("570902", box(101, 15, 102, 16), name="Two")
    source = collection(first, second)
    result = review.build_reporting_crosswalk(
        {"aoi": mapping(box(100, 15, 102, 16))}, source
    )["aois"][0]
    assert result["coverage_fraction"] == pytest.approx(1)
    assert result["uncovered_area_km2"] == pytest.approx(0, abs=1e-8)
    a, b = result["units"]
    assert a["scope"] == "partial_unit" and b["scope"] == "full_unit"
    assert a["unit_coverage_fraction"] == pytest.approx(0.5)
    assert a["aoi_share"] == pytest.approx(0.5)
    assert a["unit_area_km2"] == pytest.approx(2 * a["intersection_area_km2"])
    assert source["features"][0]["geometry"] == mapping(box(99, 15, 101, 16))


def test_holes_touching_and_bbox_candidates_are_not_covered():
    donut = Polygon(
        box(99, 14, 103, 18).exterior.coords, [box(100, 15, 102, 17).exterior.coords]
    )
    units = collection(unit("570901", donut), unit("570902", box(102, 15, 103, 17)))
    row = review.build_reporting_crosswalk(
        {"hole": mapping(box(100, 15, 102, 17))}, units
    )["aois"][0]
    assert row["units"] == [] and row["status"] == "no_intersection"
    assert row["coverage_fraction"] == 0
    assert row["uncovered_area_km2"] == row["area_km2"]


def test_union_coverage_does_not_double_count_overlapping_units():
    units = collection(
        unit("570901", box(99, 15, 101, 16)), unit("570902", box(100, 15, 102, 16))
    )
    row = review.build_reporting_crosswalk(
        {"aoi": mapping(box(99, 15, 102, 16))}, units
    )["aois"][0]
    assert row["coverage_fraction"] == pytest.approx(1)
    assert sum(x["aoi_share"] for x in row["units"]) > 1
    assert row["overlapping_unit_area_km2"] == pytest.approx(row["area_km2"] / 3)


def test_duplicate_codes_and_invalid_geometries_fail_explicitly():
    units = collection(
        unit("570901", box(99, 15, 101, 16)), unit("TH570901", box(101, 15, 102, 16))
    )
    with pytest.raises(ValueError, match="Duplicate"):
        review.build_reporting_crosswalk({"aoi": mapping(box(99, 15, 102, 16))}, units)
    invalid = Polygon([(99, 15), (101, 17), (99, 17), (101, 15), (99, 15)])
    with pytest.raises(ValueError, match="Invalid polygon"):
        review.build_reporting_crosswalk({"aoi": mapping(invalid)}, collection())


def test_multipart_and_empty_unit_source_retain_unknown_coverage():
    aoi = collection(
        unit("570901", box(99, 15, 100, 16)), unit("570902", box(101, 15, 102, 16))
    )
    row = review.build_reporting_crosswalk(
        {"aoi": aoi}, collection(unit("570901", box(99, 15, 100, 16)))
    )["aois"][0]
    assert row["coverage_fraction"] == pytest.approx(0.5)
    assert row["status"] == "partial_coverage"
    empty = review.build_reporting_crosswalk({"aoi": aoi}, collection())["aois"][0]
    assert empty["coverage_fraction"] == 0 and empty["units"] == []


def test_good_event_extent_is_not_automatically_independent_validation():
    aoi = mapping(box(99, 15, 101, 16))
    result = review.assess_event_evidence(
        event(), product(), aoi, analysis_footprint=aoi
    )
    assert result["event_context_eligible"] is True
    assert result["validation_eligible"] is False
    assert result["observation_coverage_fraction"] == 1
    assert result["validation_blocking_reasons"] == [
        "independent_validation_not_accepted",
        "validation_use_rights_unconfirmed",
    ]


@pytest.mark.parametrize(
    "start,end,conflict",
    [
        ("2024-08-01", "2024-10-22", True),
        ("2024-10-22", "2024-10-22", False),
        ("2024-09-13", "2024-09-19", True),
    ],
)
def test_cumulative_outside_dates_and_conflict_cannot_be_september_labels(
    start, end, conflict
):
    aoi = mapping(box(99, 15, 101, 16))
    result = review.assess_event_evidence(
        event(),
        product(start=start, end=end, date_conflict=conflict),
        aoi,
        analysis_footprint=aoi,
    )
    assert result["event_context_eligible"] is False
    assert result["temporal_match"] is False
    if conflict:
        assert "conflicting_observation_dates" in result["blocking_reasons"]


def test_missing_footprint_is_unknown_not_inferred_from_flood_extent():
    result = review.assess_event_evidence(
        event(), product(), mapping(box(99, 15, 101, 16))
    )
    assert result["observation_coverage_fraction"] is None
    assert result["event_context_eligible"] is False
    assert "observation_footprint_unavailable" in result["blocking_reasons"]


def test_partial_footprint_is_explicit_and_disjoint_is_ineligible():
    aoi = mapping(box(99, 15, 101, 16))
    partial = review.assess_event_evidence(
        event(), product(), aoi, analysis_footprint=mapping(box(99, 15, 100, 16))
    )
    assert partial["observation_coverage_fraction"] == pytest.approx(0.5)
    assert partial["event_context_eligible"] is True
    disjoint = review.assess_event_evidence(
        event(), product(), aoi, analysis_footprint=mapping(box(102, 15, 103, 16))
    )
    assert disjoint["event_context_eligible"] is False
    assert "no_observed_aoi_intersection" in disjoint["blocking_reasons"]


@pytest.mark.parametrize(
    "gate,reason",
    [
        ("public_derivatives", "public_derivative_rights_unconfirmed"),
        ("vector_or_raster_available", "analysis_extent_asset_unavailable"),
        ("source_snapshot_verified", "reviewed_source_snapshot_unavailable_or_changed"),
    ],
)
def test_public_url_or_dated_map_does_not_open_missing_gates(gate, reason):
    aoi = mapping(box(99, 15, 101, 16))
    result = review.assess_event_evidence(
        event(), product(**{gate: False}), aoi, analysis_footprint=aoi
    )
    assert reason in result["blocking_reasons"] and not result["event_context_eligible"]


def test_missing_dates_and_invalid_order_are_not_silently_repaired():
    aoi = mapping(box(99, 15, 101, 16))
    result = review.assess_event_evidence(event(), {"id": "missing"}, aoi)
    assert result["temporal_match"] is False
    assert "observation_dates_unavailable" in result["blocking_reasons"]
    with pytest.raises(ValueError, match="Product start"):
        review.assess_event_evidence(
            event(), product(start="2024-09-20", end="2024-09-01"), aoi
        )


def test_unknown_archive_hash_is_rejected_before_geometry_export(tmp_path):
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"unreviewed fixture")
    with pytest.raises(ValueError, match="checksum"):
        review.build_event_review(
            aoi_dir=tmp_path,
            acquisition_dir=tmp_path,
            output_dir=tmp_path / "output",
            existing_boundary_zip=archive,
            prior_evidence_dir=tmp_path,
            open_data_dir=tmp_path,
        )
    assert not (tmp_path / "output").exists()


def test_missing_source_snapshots_leave_real_product_gates_closed(tmp_path):
    products = {p["id"]: p for p in review._review_products(tmp_path)}
    assert not products["eos_hat_yai_20251123"]["vector_or_raster_available"]
    assert not products["unosat_3991_sep13_19"]["source_snapshot_verified"]
    assert all(not p["public_derivatives"] for p in products.values())
    assert products["unosat_4009_accumulated"]["layer_name_end_date"] == "2024-10-12"


def test_local_wrapper_writes_only_relative_paths_and_distinguishes_missing_events(
    tmp_path, monkeypatch
):
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"fixture")
    monkeypatch.setitem(
        review.BOUNDARY_SOURCE, "source_sha256", review.sha256_file(archive)
    )
    acquisition = tmp_path / "acquisition"
    acquisition.mkdir()
    (acquisition / "hdx_cod_ab_metadata.json").write_text(
        json.dumps(
            {
                "result": {
                    "id": "d24bdc45-eb4c-4e3d-8b16-44db02667c27",
                    "license_id": "cc-by-igo",
                    "license_url": review.BOUNDARY_SOURCE["license_url"],
                    "dataset_source": "Royal Thai Survey Department",
                }
            }
        ),
        encoding="utf-8",
    )
    (acquisition / "cc_by_igo_3_legalcode.html").write_text(
        "fixture license snapshot", encoding="utf-8"
    )
    monkeypatch.setitem(
        review.BOUNDARY_SOURCE,
        "license_snapshot_sha256",
        review.sha256_file(acquisition / "cc_by_igo_3_legalcode.html"),
    )
    aois = tmp_path / "aois"
    aois.mkdir()
    for index, name in enumerate(
        [
            "mae_sai_core",
            "mae_sai_district",
            "hat_yai_core",
            "hat_yai_basin",
            "chao_phraya_bang_ban_sena",
            "chao_phraya_rangsit",
        ],
        1,
    ):
        (aois / f"aoi-{index:02}_{name}.geojson").write_text(
            json.dumps(collection(unit("570901", box(99, 15, 101, 16)))),
            encoding="utf-8",
        )
    monkeypatch.setattr(
        review,
        "_read_boundary_units",
        lambda *_: collection(unit("570901", box(99, 15, 101, 16))),
    )
    summary = review.build_event_review(
        aoi_dir=aois,
        acquisition_dir=acquisition,
        output_dir=tmp_path / "output",
        existing_boundary_zip=archive,
        prior_evidence_dir=tmp_path / "prior",
        open_data_dir=tmp_path / "open",
    )
    assert summary["boundary_source"]["public_derivatives"] is True
    assert summary["reporting_units"]["path"] == "reporting_units.geojson"
    assert summary["event_evidence"]["eligible_count"] == 0
    evidence = json.loads(
        (tmp_path / "output" / summary["event_evidence"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    missing = [
        r
        for r in evidence["aois"]
        if r["event_context_status"] == "source_not_acquired"
    ]
    assert len(missing) == 4
    assert all(r["observation_coverage_fraction"] is None for r in missing)


def test_changed_legal_snapshot_is_not_treated_as_reviewed(tmp_path):
    path = tmp_path / "license.html"
    path.write_bytes(b"reviewed terms")
    expected = review.sha256_file(path)
    assert review._verified_snapshot(tmp_path, path.name, expected)
    path.write_bytes(b"changed terms")
    assert not review._verified_snapshot(tmp_path, path.name, expected)
