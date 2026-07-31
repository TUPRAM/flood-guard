from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from floodguard.ait_reference_candidate import (
    AIT_SYNTHETIC_FIXTURE_VERSION,
    AitReferenceCandidateError,
    inspect_ait_reference_candidate,
    validate_ait_reference_candidate,
    write_ait_reference_candidate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


gpd = pytest.importorskip("geopandas")
pytest.importorskip("shapely")
from shapely.geometry import Polygon  # noqa: E402


def test_ait_inspection_records_real_geometry_facts_but_stays_blocked(
    tmp_path: Path,
) -> None:
    archive = _candidate_archive(tmp_path)
    study_area = _study_area(tmp_path)

    receipt = inspect_ait_reference_candidate(
        archive,
        study_area,
        catalog_evidence_path=_catalog_evidence(tmp_path),
        terms_evidence_path=_terms_evidence(tmp_path),
        inspected_at_utc=datetime(2026, 7, 23, tzinfo=UTC),
        reference_version=AIT_SYNTHETIC_FIXTURE_VERSION,
    )

    assert receipt["reference_evidence_class"] == "expert_interpretation"
    assert receipt["native_spatial_contract"]["feature_count"] == 2
    assert receipt["native_spatial_contract"]["invalid_feature_count"] == 1
    assert receipt["study_area_relationship"]["intersecting_feature_count"] == 2
    assert receipt["study_area_relationship"]["invalid_intersecting_feature_count"] == 1
    assert receipt["processing_allowed"] is False
    assert receipt["permission_status"]["ml_label_use_allowed"] is False
    assert receipt["permission_status"]["model_evaluation_use_allowed"] is False
    assert all(value is False for value in receipt["safety"].values())
    assert receipt["canonical_sha256"]
    assert str(tmp_path) not in json.dumps(receipt)

    output = write_ait_reference_candidate(receipt, tmp_path / "receipt.json")
    assert json.loads(output.read_text(encoding="utf-8")) == receipt
    assert output.read_bytes().endswith(b"\n")
    assert b"\r\n" not in output.read_bytes()


def test_ait_candidate_rejects_tampering_and_unsafe_claims(tmp_path: Path) -> None:
    receipt = inspect_ait_reference_candidate(
        _candidate_archive(tmp_path),
        _study_area(tmp_path),
        catalog_evidence_path=_catalog_evidence(tmp_path),
        terms_evidence_path=_terms_evidence(tmp_path),
        inspected_at_utc=datetime(2026, 7, 23, tzinfo=UTC),
        reference_version=AIT_SYNTHETIC_FIXTURE_VERSION,
    )

    tampered = deepcopy(receipt)
    tampered["study_area_relationship"]["intersecting_feature_count"] = 999
    with pytest.raises(AitReferenceCandidateError, match="relationship"):
        validate_ait_reference_candidate(tampered)

    unsafe = deepcopy(receipt)
    unsafe["processing_allowed"] = True
    with pytest.raises(AitReferenceCandidateError, match="processing_allowed"):
        validate_ait_reference_candidate(unsafe)

    authority_claim = deepcopy(receipt)
    authority_claim["safety"]["eligible_for_fpps"] = True
    with pytest.raises(AitReferenceCandidateError, match="downstream"):
        validate_ait_reference_candidate(authority_claim)


def test_ait_candidate_rejects_incomplete_shapefile_package(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("AIT-VAP001-TH/AIT-VAP001-TH.shp", b"not-enough")

    with pytest.raises(AitReferenceCandidateError, match="component is missing"):
        inspect_ait_reference_candidate(
            archive,
            _study_area(tmp_path),
            catalog_evidence_path=_catalog_evidence(tmp_path),
            terms_evidence_path=_terms_evidence(tmp_path),
            inspected_at_utc=datetime(2026, 7, 23, tzinfo=UTC),
        )


def test_committed_ait_candidate_receipt_is_sanitized_and_blocked() -> None:
    payload = json.loads(
        (REPO_ROOT / "outputs" / "ait_vap001_reference_candidate.json").read_text(
            encoding="utf-8"
        )
    )

    validate_ait_reference_candidate(payload)
    assert payload["asset_inventory"]["archive"]["sha256"] == (
        "762153fe3fd22350070bb788c22f2d4e083866b5d20b1294e8ca27b97367d5d5"
    )
    assert payload["study_area_relationship"] == {
        "study_area_feature_count": 8,
        "study_area_area_km2": 305.554,
        "intersecting_feature_count": 371,
        "invalid_intersecting_feature_count": 24,
        "diagnostic_repair_applied": True,
        "diagnostic_intersection_area_km2": 36.173,
        "diagnostic_intersection_fraction": 0.118385,
        "complete_study_area_coverage_claimed": False,
    }
    assert payload["processing_allowed"] is False
    assert "C:\\Users" not in json.dumps(payload)


@pytest.mark.parametrize(
    ("section", "field", "replacement", "message"),
    [
        (
            "permission_status",
            "redistribution_status",
            "allowed",
            "legal and permission semantics",
        ),
        (
            "provider.terms_evidence",
            "no_modification_clause_present",
            False,
            "no-modification clauses",
        ),
        (
            "temporal_identity",
            "observation_end_utc",
            "2024-09-16T23:59:59Z",
            "temporal observation_end_utc",
        ),
    ],
)
def test_ait_candidate_rejects_rehashed_legal_and_temporal_mutations(
    section: str,
    field: str,
    replacement: object,
    message: str,
) -> None:
    payload = json.loads(
        (REPO_ROOT / "outputs" / "ait_vap001_reference_candidate.json").read_text(
            encoding="utf-8"
        )
    )
    target = payload
    for part in section.split("."):
        target = target[part]
    target[field] = replacement
    _resign(payload)

    with pytest.raises(AitReferenceCandidateError, match=message):
        validate_ait_reference_candidate(payload)


@pytest.mark.parametrize(
    ("section", "field", "replacement", "message"),
    [
        (
            "asset_inventory.members.5",
            "sha256",
            "0" * 64,
            "archive-member identity changed",
        ),
        (
            "asset_inventory.archive",
            "sha256",
            "1" * 64,
            "source-archive identity changed",
        ),
        (
            "native_spatial_contract",
            "feature_count",
            33_203,
            "native spatial facts changed",
        ),
    ],
)
def test_ait_candidate_rejects_rehashed_reviewed_native_fact_substitution(
    section: str,
    field: str,
    replacement: object,
    message: str,
) -> None:
    payload = json.loads(
        (REPO_ROOT / "outputs" / "ait_vap001_reference_candidate.json").read_text(
            encoding="utf-8"
        )
    )
    target: object = payload
    for part in section.split("."):
        if isinstance(target, list):
            target = target[int(part)]
        else:
            assert isinstance(target, dict)
            target = target[part]
    assert isinstance(target, dict)
    target[field] = replacement
    if section == "native_spatial_contract":
        target["valid_feature_count"] = 32_094
    _resign(payload)

    with pytest.raises(AitReferenceCandidateError, match=message):
        validate_ait_reference_candidate(payload)


def test_ait_candidate_rejects_excessive_archive_member_count(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "too-many-members.zip"
    required = {
        f"AIT-VAP001-TH/AIT-VAP001-TH{suffix}": b"x"
        for suffix in (".shp", ".shx", ".dbf", ".prj")
    }
    with zipfile.ZipFile(archive, "w") as package:
        for name, content in required.items():
            package.writestr(name, content)
        for index in range(61):
            package.writestr(f"AIT-VAP001-TH/bounded-extra-{index:02d}.txt", b"x")

    with pytest.raises(AitReferenceCandidateError, match="unique, and bounded"):
        inspect_ait_reference_candidate(
            archive,
            _study_area(tmp_path),
            catalog_evidence_path=_catalog_evidence(tmp_path),
            terms_evidence_path=_terms_evidence(tmp_path),
            inspected_at_utc=datetime(2026, 7, 23, tzinfo=UTC),
        )


def _resign(payload: dict) -> None:
    unsigned = {
        key: value for key, value in payload.items() if key != "canonical_sha256"
    }
    payload["canonical_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _candidate_archive(tmp_path: Path) -> Path:
    source = tmp_path / "candidate"
    source.mkdir(exist_ok=True)
    valid = Polygon(
        [
            (600000, 2250000),
            (601000, 2250000),
            (601000, 2251000),
            (600000, 2251000),
            (600000, 2250000),
        ]
    )
    invalid = Polygon(
        [
            (600250, 2250250),
            (600750, 2250750),
            (600250, 2250750),
            (600750, 2250250),
            (600250, 2250250),
        ]
    )
    frame = gpd.GeoDataFrame(
        {"Id": [1, 1], "gridcode": [1, 1]},
        geometry=[valid, invalid],
        crs="EPSG:32647",
    )
    shape_path = source / "AIT-VAP001-TH.shp"
    frame.to_file(shape_path)
    (source / "AIT-VAP001-TH.shp.xml").write_text(
        "<metadata>C:\\Users\\provider\\source.tif</metadata>",
        encoding="utf-8",
    )
    archive = tmp_path / "AIT-VAP001-TH.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for file_path in sorted(source.iterdir()):
            package.write(file_path, f"AIT-VAP001-TH/{file_path.name}")
    return archive


def _study_area(tmp_path: Path) -> Path:
    path = tmp_path / "study-area.geojson"
    area = gpd.GeoDataFrame(
        {"area_id": ["mae-sai-test"]},
        geometry=[
            Polygon(
                [
                    (599500, 2249500),
                    (601500, 2249500),
                    (601500, 2251500),
                    (599500, 2251500),
                    (599500, 2249500),
                ]
            )
        ],
        crs="EPSG:32647",
    )
    area.to_file(path, driver="GeoJSON")
    return path


def _catalog_evidence(tmp_path: Path) -> Path:
    path = tmp_path / "sentinel-asia-event.html"
    path.write_text(
        "<a href='AIT-VAP001-TH.zip'>AIT-VAP001-TH</a>"
        "<p>As observed by ALOS-2 images on 14 September 2024</p>",
        encoding="utf-8",
    )
    return path


def _terms_evidence(tmp_path: Path) -> Path:
    path = tmp_path / "sentinel-asia-terms.html"
    path.write_text(
        "<p>scientific/educational use</p><p>No modification is allowed</p>",
        encoding="utf-8",
    )
    return path
