from __future__ import annotations

import importlib.util
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from floodguard.ingestion import build_ingestion_manifest, default_mae_sai_file_manifest_sources
from floodguard.manual_reference import (
    MANUAL_REFERENCE_COLUMNS,
    ManualReferenceError,
    _classify_spatial_relation,
    inspect_manual_reference_mask,
    write_manual_reference_manifest,
)

REPO_ROOT = Path(__file__).parents[1]
_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "build_mae_sai_file_manifest",
    REPO_ROOT / "scripts" / "build_mae_sai_file_manifest.py",
)
assert _SCRIPT_SPEC is not None
assert _SCRIPT_SPEC.loader is not None
build_mae_sai_file_manifest = importlib.util.module_from_spec(_SCRIPT_SPEC)
_SCRIPT_SPEC.loader.exec_module(build_mae_sai_file_manifest)


def test_missing_manual_reference_writes_blocked_skeleton(tmp_path: Path) -> None:
    missing = tmp_path / "mae_sai_manual_flood_reference.gpkg"

    frame = inspect_manual_reference_mask(
        missing,
        local_path_hint="<external_data_workspace>/manual_reference/mae_sai_2024/missing.gpkg",
        inspected_at_utc="2026-07-09T00:00:00Z",
    )

    assert list(frame.columns) == list(MANUAL_REFERENCE_COLUMNS)
    row = frame.iloc[0]
    assert bool(row["file_found"]) is False
    assert row["sha256_status"] == "missing_source_file"
    assert row["reference_mask_status"] == "weak_reference_candidate"
    assert bool(row["candidate_validation_metrics_allowed"]) is False
    assert bool(row["processing_allowed"]) is False
    assert "not found outside Git" in row["reason_blocked"]


def test_valid_manual_reference_metadata_stays_blocked_without_spatial_check(
    tmp_path: Path,
) -> None:
    gpkg = tmp_path / "mae_sai_manual_flood_reference.gpkg"
    _write_minimal_manual_gpkg(gpkg)

    frame = inspect_manual_reference_mask(
        gpkg,
        local_path_hint="<external_data_workspace>/manual_reference/mae_sai_2024/manual.gpkg",
        inspected_at_utc="2026-07-09T00:00:00Z",
    )

    row = frame.iloc[0]
    assert row["reference_id"] == "MS-MANUAL-001"
    assert row["confidence"] == "medium"
    assert row["source_basis"] == "Sentinel-1 visual interpretation"
    assert row["digitized_by"] == "[blank]"
    assert row["digitized_at"] == "2026-07-09"
    assert row["notes"] == "uncertain areas excluded"
    assert row["sha256_status"] == "recorded"
    assert len(row["sha256"]) == 64
    assert row["source_type"] == "manual_qgis_weak_reference"
    assert row["geometry_type"] == "MULTIPOLYGON"
    assert row["crs"] == "EPSG:4326"
    assert row["feature_count"] == 1
    assert bool(row["required_fields_present"]) is True
    assert row["missing_fields"] == ""
    assert row["not_official_status"] == "confirmed_true"
    assert row["candidate_readiness_status"] == "spatially_unqualified"
    assert bool(row["candidate_validation_metrics_allowed"]) is False
    assert bool(row["official_validation_truth_allowed"]) is False
    assert bool(row["unqualified_ml_label_allowed"]) is False
    assert bool(row["processing_allowed"]) is False
    assert "spatial relation is not verified" in row["reason_blocked"]


def test_manual_reference_requires_required_fields_and_not_official_true(
    tmp_path: Path,
) -> None:
    gpkg = tmp_path / "bad_manual_reference.gpkg"
    _write_minimal_manual_gpkg(gpkg, include_notes=False, not_official=0)

    frame = inspect_manual_reference_mask(gpkg)

    row = frame.iloc[0]
    assert bool(row["required_fields_present"]) is False
    assert "notes" in row["missing_fields"]
    assert row["not_official_status"] == "contains_false"
    assert bool(row["candidate_validation_metrics_allowed"]) is False
    assert "missing required fields" in row["reason_blocked"]
    assert "not_official status is contains_false" in row["reason_blocked"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reference_id", ""),
        ("reference_id", None),
        ("confidence", " "),
        ("source_basis", None),
        ("digitized_by", ""),
        ("digitized_at", None),
        ("notes", "  "),
    ],
)
def test_manual_reference_rejects_blank_required_attribute_values(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    gpkg = tmp_path / f"blank_{field}.gpkg"
    _write_minimal_manual_gpkg(gpkg)
    _update_manual_attributes(gpkg, **{field: value})

    row = inspect_manual_reference_mask(gpkg).iloc[0]

    assert row["attribute_values_status"] == "invalid"
    assert f"feature_1:{field}:blank" in row["attribute_value_blockers"]
    assert bool(row["candidate_validation_metrics_allowed"]) is False
    assert "invalid feature attributes" in row["reason_blocked"]
    if field == "reference_id":
        assert row["reference_id"] == ""
        assert row["reference_id"] != "MANUAL-QGIS-MAE-SAI-2024"


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    [
        ("confidence", "certain", "confidence:invalid_certain"),
        ("digitized_at", "09/07/2026", "digitized_at:invalid_iso_date"),
    ],
)
def test_manual_reference_rejects_invalid_confidence_and_date(
    tmp_path: Path,
    field: str,
    value: str,
    blocker: str,
) -> None:
    gpkg = tmp_path / f"invalid_{field}.gpkg"
    _write_minimal_manual_gpkg(gpkg)
    _update_manual_attributes(gpkg, **{field: value})

    row = inspect_manual_reference_mask(gpkg).iloc[0]

    assert row["attribute_values_status"] == "invalid"
    assert blocker in row["attribute_value_blockers"]
    assert bool(row["candidate_validation_metrics_allowed"]) is False


def test_manual_reference_accepts_explicit_blank_digitizer_placeholder(
    tmp_path: Path,
) -> None:
    gpkg = tmp_path / "explicit_blank_digitizer.gpkg"
    _write_minimal_manual_gpkg(gpkg)

    row = inspect_manual_reference_mask(gpkg).iloc[0]

    assert row["attribute_values_status"] == "valid"
    assert row["attribute_value_blockers"] == ""
    assert row["candidate_readiness_status"] == "spatially_unqualified"
    assert bool(row["candidate_validation_metrics_allowed"]) is False


def test_manual_reference_classifies_cross_border_non_overlap() -> None:
    manual = {
        "type": "Polygon",
        "coordinates": [[(99.8, 20.5), (99.9, 20.5), (99.9, 20.6), (99.8, 20.5)]],
    }
    study_area = {
        "type": "Polygon",
        "coordinates": [[(99.8, 20.2), (99.9, 20.2), (99.9, 20.4), (99.8, 20.2)]],
    }

    spatial = _classify_spatial_relation([manual], [study_area])

    assert spatial["spatial_relation"] == "cross_border_calibration_only"
    assert spatial["in_study_area_overlap"] is False
    assert float(spatial["distance_to_study_area_km"]) > 0
    assert spatial["spatial_relation_status"] == "verified_geometry_intersection"


@pytest.mark.parametrize(
    "manual",
    [
        {
            "type": "Polygon",
            "coordinates": [
                [
                    (99.8, 20.5),
                    (99.9, 20.6),
                    (99.8, 20.6),
                    (99.9, 20.5),
                    (99.8, 20.5),
                ]
            ],
        },
        {
            "type": "Polygon",
            "coordinates": [[(99.8, 20.5), (99.9, 20.5), (99.8, 20.5)]],
        },
        {"type": "Point", "coordinates": (99.8, 20.5)},
    ],
)
def test_manual_reference_spatial_relation_rejects_invalid_geometry(
    manual: dict[str, object],
) -> None:
    study_area = {
        "type": "Polygon",
        "coordinates": [
            [(99.8, 20.2), (99.9, 20.2), (99.9, 20.4), (99.8, 20.2)]
        ],
    }

    with pytest.raises(ManualReferenceError, match="must be"):
        _classify_spatial_relation([manual], [study_area])


def test_manual_reference_rejects_ambiguous_digitizer_placeholder(
    tmp_path: Path,
) -> None:
    gpkg = tmp_path / "ambiguous_digitizer.gpkg"
    _write_minimal_manual_gpkg(gpkg)
    _update_manual_attributes(gpkg, digitized_by="blank")

    row = inspect_manual_reference_mask(gpkg).iloc[0]

    assert row["attribute_values_status"] == "invalid"
    assert "digitized_by:explicit_placeholder_required" in row[
        "attribute_value_blockers"
    ]
    assert bool(row["candidate_validation_metrics_allowed"]) is False


def test_manual_reference_rejects_non_geopackage(tmp_path: Path) -> None:
    path = tmp_path / "manual_reference.geojson"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ManualReferenceError, match="GeoPackage"):
        inspect_manual_reference_mask(path)


def test_write_manual_reference_manifest_writes_csv(tmp_path: Path) -> None:
    gpkg = tmp_path / "mae_sai_manual_flood_reference.gpkg"
    _write_minimal_manual_gpkg(gpkg)
    output = tmp_path / "manual_reference_mask_manifest.csv"

    written = write_manual_reference_manifest(output, reference_path=gpkg)

    assert written == output
    rows = pd.read_csv(output)
    assert len(rows) == 1
    assert rows.loc[0, "reference_mask_status"] == "weak_reference_candidate"


def test_mae_sai_manifest_absorbs_manual_weak_reference_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    pd.DataFrame(
        [
            {
                "source_name": "FloodGuard manual QGIS Mae Sai weak-reference candidate",
                "study_area": "Chiang Rai / Mae Sai 2024",
                "reference_id": "MS-MANUAL-001",
                "file_name": "mae_sai_manual_flood_reference.gpkg",
                "local_path_hint": "<external_data_workspace>/manual_reference/mae_sai_2024/manual.gpkg",
                "sha256": "d" * 64,
                "sha256_status": "recorded",
                "file_size_bytes": "1234",
                "file_found": "True",
                "source_type": "manual_qgis_weak_reference",
                "layer_name": "manual_flood_extent",
                "geometry_type": "MULTIPOLYGON",
                "crs": "EPSG:4326",
                "bbox_lon_min": "99.8",
                "bbox_lat_min": "20.3",
                "bbox_lon_max": "100.0",
                "bbox_lat_max": "20.5",
                "feature_count": "1",
                "required_fields": "reference_id|confidence|source_basis|digitized_by|digitized_at|notes|not_official",
                "required_fields_present": "True",
                "missing_fields": "",
                "not_official_status": "confirmed_true",
                "reference_mask_status": "weak_reference_candidate",
                "candidate_readiness_status": "ready_for_candidate_metrics",
                "allowed_use": "candidate validation metrics; visual QA; non-operational demo reporting",
                "not_allowed_use": "official validation truth; official warning; redistributed source data claim; unqualified ML labels",
                "candidate_validation_metrics_allowed": "True",
                "visual_qa_allowed": "True",
                "non_operational_demo_reporting_allowed": "True",
                "official_validation_truth_allowed": "False",
                "official_warning_allowed": "False",
                "redistributable_source_claim_allowed": "False",
                "unqualified_ml_label_allowed": "False",
                "processing_allowed": "False",
                "reason_blocked": "manual weak-reference candidate is complete for candidate metrics only",
                "next_action": "use only for weak/candidate baseline metrics",
                "inspected_at_utc": "2026-07-09T00:00:00Z",
            }
        ]
    ).to_csv(outputs_dir / "manual_reference_mask_manifest.csv", index=False)
    monkeypatch.setattr(build_mae_sai_file_manifest, "REPO_ROOT", tmp_path)

    sources = build_mae_sai_file_manifest._with_manual_reference_candidate(
        default_mae_sai_file_manifest_sources()
    )
    manifest = build_ingestion_manifest(sources)
    row = manifest[
        manifest["source_name"]
        == "FloodGuard manual QGIS Mae Sai weak-reference candidate"
    ].iloc[0]

    assert row["product_id"] == "MS-MANUAL-001"
    assert row["local_path"] == "<external_data_workspace>/manual_reference/mae_sai_2024/manual.gpkg"
    assert row["sha256"] == "d" * 64
    assert row["reference_mask_status"] == "weak_reference_candidate"
    assert bool(row["processing_allowed"]) is False
    assert "reference mask not confirmed" in row["reason_blocked"]


def test_manual_reference_scripts_do_not_download_or_read_rasters() -> None:
    for path in (
        REPO_ROOT / "scripts" / "inspect_manual_reference_mask.py",
        REPO_ROOT / "src" / "floodguard" / "manual_reference.py",
    ):
        source = path.read_text(encoding="utf-8")
        for token in ("urlopen(", "requests.", "urlretrieve(", "rasterio.open", "gdal."):
            assert token not in source


def _write_minimal_manual_gpkg(
    path: Path,
    *,
    include_notes: bool = True,
    not_official: int = 1,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE gpkg_contents (
                table_name TEXT PRIMARY KEY,
                data_type TEXT NOT NULL,
                identifier TEXT,
                description TEXT,
                last_change TEXT,
                min_x DOUBLE,
                min_y DOUBLE,
                max_x DOUBLE,
                max_y DOUBLE,
                srs_id INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE gpkg_geometry_columns (
                table_name TEXT,
                column_name TEXT,
                geometry_type_name TEXT,
                srs_id INTEGER,
                z TINYINT,
                m TINYINT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE gpkg_spatial_ref_sys (
                srs_name TEXT,
                srs_id INTEGER PRIMARY KEY,
                organization TEXT,
                organization_coordsys_id INTEGER,
                definition TEXT,
                description TEXT
            )
            """
        )
        fields = """
            fid INTEGER PRIMARY KEY,
            geom BLOB,
            reference_id TEXT,
            confidence TEXT,
            source_basis TEXT,
            digitized_by TEXT,
            digitized_at TEXT,
            {notes_field}
            not_official INTEGER
        """.format(notes_field="notes TEXT," if include_notes else "")
        connection.execute(f"CREATE TABLE manual_flood_extent ({fields})")
        connection.execute(
            """
            INSERT INTO gpkg_contents
            VALUES (
                'manual_flood_extent',
                'features',
                'manual_flood_extent',
                'FloodGuard manual weak reference',
                '2026-07-09T00:00:00Z',
                99.8,
                20.3,
                100.0,
                20.5,
                4326
            )
            """
        )
        connection.execute(
            """
            INSERT INTO gpkg_geometry_columns
            VALUES ('manual_flood_extent', 'geom', 'MULTIPOLYGON', 4326, 0, 0)
            """
        )
        connection.execute(
            """
            INSERT INTO gpkg_spatial_ref_sys
            VALUES ('WGS 84', 4326, 'EPSG', 4326, 'definition', 'WGS 84')
            """
        )
        if include_notes:
            connection.execute(
                """
                INSERT INTO manual_flood_extent (
                    fid,
                    geom,
                    reference_id,
                    confidence,
                    source_basis,
                    digitized_by,
                    digitized_at,
                    notes,
                    not_official
                )
                VALUES (
                    1,
                    X'00',
                    'MS-MANUAL-001',
                    'medium',
                    'Sentinel-1 visual interpretation',
                    '[blank]',
                    '2026-07-09',
                    'uncertain areas excluded',
                    ?
                )
                """,
                (not_official,),
            )
        else:
            connection.execute(
                """
                INSERT INTO manual_flood_extent (
                    fid,
                    geom,
                    reference_id,
                    confidence,
                    source_basis,
                    digitized_by,
                    digitized_at,
                    not_official
                )
                VALUES (
                    1,
                    X'00',
                    'MS-MANUAL-001',
                    'medium',
                    'Sentinel-1 visual interpretation',
                    '[blank]',
                    '2026-07-09',
                    ?
                )
                """,
                (not_official,),
            )


def _update_manual_attributes(path: Path, **values: object) -> None:
    allowed = {
        "reference_id",
        "confidence",
        "source_basis",
        "digitized_by",
        "digitized_at",
        "notes",
    }
    if not set(values).issubset(allowed):
        raise AssertionError("Test attempted to update an unsupported attribute.")
    with sqlite3.connect(path) as connection:
        for field, value in values.items():
            connection.execute(
                f'UPDATE manual_flood_extent SET "{field}" = ? WHERE fid = 1',
                (value,),
            )
