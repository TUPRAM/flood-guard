from __future__ import annotations

import base64
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

import floodguard.label_factory.qualified_reference_release as release_module
import floodguard.controlled_experiment as controlled
from floodguard.controlled_experiment import assess_acquisition_manifest
from floodguard.label_factory.qualified_reference_release import (
    BLOCKED_STATUS,
    QUALIFIED_STATUS,
    SYNTHETIC_LIMITATION,
    SYNTHETIC_STATUS,
    QualifiedReferenceReleaseError,
    build_qualified_reference_release,
    load_qualified_reference_release,
    validate_qualified_reference_release,
    write_qualified_reference_release,
)


ROOT = Path(__file__).resolve().parents[1]
ACQUISITION_MANIFEST = (
    ROOT / "docs" / "validation" / "controlled_three_model_acquisition_manifest.csv"
)
SCHEMA_PATH = (
    ROOT
    / "packages"
    / "contracts"
    / "schemas"
    / "qualified-reference-release-v1.schema.json"
)
SCRIPT_PATH = ROOT / "scripts" / "build_qualified_reference_release.py"
TEST_AUTHORITY_KEY_ID = "qualified-release-test-authority-v1"
TEST_AUTHORITY_KEY = b"qualified-release-test-authority-key-material"
TEST_EXTERNAL_KEY_ID = "qualified-release-external-ed25519-v1"
TEST_EXTERNAL_SEED = bytes(range(32))
TEST_REFERENCE_AUTHORITY_KEY_ID = "qualified-release-scientific-ed25519-v1"
TEST_REFERENCE_AUTHORITY_SEED = bytes(range(32, 64))


def _ed25519_public_key(seed: bytes) -> bytes:
    digest = hashlib.sha512(seed).digest()
    scalar_bytes = bytearray(digest[:32])
    scalar_bytes[0] &= 248
    scalar_bytes[31] &= 63
    scalar_bytes[31] |= 64
    scalar = int.from_bytes(scalar_bytes, "little")
    point = controlled._ed25519_scalarmult(controlled._ED25519_B, scalar)
    x, y = point
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _ed25519_sign(seed: bytes, message: bytes) -> bytes:
    digest = hashlib.sha512(seed).digest()
    scalar_bytes = bytearray(digest[:32])
    scalar_bytes[0] &= 248
    scalar_bytes[31] &= 63
    scalar_bytes[31] |= 64
    scalar = int.from_bytes(scalar_bytes, "little")
    public_key = _ed25519_public_key(seed)
    nonce = int.from_bytes(hashlib.sha512(digest[32:] + message).digest(), "little")
    nonce %= controlled._ED25519_ORDER
    r_point = controlled._ed25519_scalarmult(controlled._ED25519_B, nonce)
    r_encoded = (r_point[1] | ((r_point[0] & 1) << 255)).to_bytes(32, "little")
    challenge = (
        int.from_bytes(
            hashlib.sha512(r_encoded + public_key + message).digest(),
            "little",
        )
        % controlled._ED25519_ORDER
    )
    scalar_signature = (nonce + challenge * scalar) % controlled._ED25519_ORDER
    return r_encoded + scalar_signature.to_bytes(32, "little")


TEST_EXTERNAL_PUBLIC_KEY = _ed25519_public_key(TEST_EXTERNAL_SEED)
TEST_REFERENCE_AUTHORITY_PUBLIC_KEY = _ed25519_public_key(TEST_REFERENCE_AUTHORITY_SEED)
TEST_SIGNING_KEYS = {TEST_AUTHORITY_KEY_ID: TEST_AUTHORITY_KEY}
TEST_EXTERNAL_PUBLIC_KEYS = {
    TEST_EXTERNAL_KEY_ID: TEST_EXTERNAL_PUBLIC_KEY,
}
TEST_REFERENCE_AUTHORITY_PUBLIC_KEYS = {
    TEST_REFERENCE_AUTHORITY_KEY_ID: TEST_REFERENCE_AUTHORITY_PUBLIC_KEY,
}


def _write_reference_authority_decision(
    fixture_dir: Path,
    *,
    purpose: str,
    artifact_sha256: str,
) -> tuple[Path, Path]:
    decision = {
        "schema_version": (release_module.REFERENCE_AUTHORITY_DECISION_SCHEMA),
        "decision_id": f"RA-SCIENTIFIC-{purpose}",
        "decision_status": "approved_for_exact_purpose",
        "event_id": "synthetic-test-event",
        "study_area_id": "synthetic-test-area",
        "experiment_id": "QUALIFIED-RELEASE-TEST-EXP-1",
        "source_name": "Source reference_mask",
        "product_id": "PRODUCT-reference_mask",
        "artifact_sha256": artifact_sha256,
        "source_timestamp": "2024-01-02T23:59:59Z",
        "observation_start": "2024-01-02T00:00:00Z",
        "observation_end": "2024-01-02T23:59:59Z",
        "reference_authority_class": "expert_interpretation",
        "purpose": purpose,
        "independent_of_model_inputs": True,
        "scientific_method": (
            "Independent purpose-specific scientific assessment of the "
            "checksum-bound synthetic reference."
        ),
        "known_uncertainty_and_error_categories": (
            "Synthetic boundary, permanent-water, and radar-shadow cases."
        ),
        "issued_at_utc": "2024-01-03T00:00:00Z",
        "expires_at_utc": "2030-01-01T00:00:00Z",
        "signer": {
            "name": "Independent Scientific Reference Reviewer",
            "organization": "FloodGuard Scientific Test Authority",
            "title_or_role": "Reference Authority",
            "authority_basis": ("Independent scientific qualification test fixture."),
            "identity_evidence_type": "test fixture identity record",
            "identity_evidence_sha256": "8" * 64,
            "signing_key_id": TEST_REFERENCE_AUTHORITY_KEY_ID,
            "public_key_sha256": hashlib.sha256(
                TEST_REFERENCE_AUTHORITY_PUBLIC_KEY
            ).hexdigest(),
        },
        "official_warning": False,
        "can_feed_decision_layer": False,
        "can_feed_fpps": False,
        "can_assign_action_class": False,
    }
    decision_path = fixture_dir / f"reference-authority-{purpose}.json"
    decision_path.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    signature_path = fixture_dir / f"reference-authority-{purpose}.sig"
    signature_path.write_text(
        _ed25519_sign(
            TEST_REFERENCE_AUTHORITY_SEED,
            controlled._canonical_json_bytes(decision),
        ).hex()
        + "\n",
        encoding="ascii",
    )
    return decision_path, signature_path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_signed_test_authority(
    fixture_dir: Path,
    manifest: Path,
    base_assessment,
) -> Path:
    frame = pd.read_csv(manifest, dtype=str, keep_default_na=False)
    catalog_paths: dict[str, Path] = {}
    license_paths: dict[str, Path] = {}
    for role in controlled.REQUIRED_INPUT_ROLES:
        catalog_path = fixture_dir / f"{role}-catalog.json"
        catalog_path.write_text(
            json.dumps({"role": role, "record": "synthetic test catalog"}),
            encoding="utf-8",
        )
        license_path = fixture_dir / f"{role}-license.txt"
        license_path.write_text(
            f"Synthetic test-only license evidence for {role}.",
            encoding="utf-8",
        )
        catalog_paths[role] = catalog_path
        license_paths[role] = license_path

    products: list[dict[str, Any]] = []
    for raw in frame.sort_values("role").to_dict("records"):
        role = str(raw["role"])
        redistribution = str(raw["redistribution_status"])
        products.append(
            {
                "role": role,
                "source_name": str(raw["source_name"]),
                "source_url": str(raw["source_url"]),
                "product_id": str(raw["product_id"]),
                "acquisition_start_utc": str(raw["acquisition_start_utc"]),
                "acquisition_end_utc": str(raw["acquisition_end_utc"]),
                "source_timestamp": str(raw["source_timestamp"]),
                "artifact_sha256": str(raw["sha256"]),
                "catalog_evidence_sha256": _sha256_file(catalog_paths[role]),
                "license_evidence_sha256": _sha256_file(license_paths[role]),
                "terms_url": f"https://example.test/terms/{role}",
                "license_status": str(raw["license_status"]),
                "redistribution_status": redistribution,
                "reference_mask_status": str(raw["reference_mask_status"]),
                "temporal_alignment_status": str(raw["temporal_alignment_status"]),
                "assumptions": str(raw["assumptions"]),
                "authority_decision": "approved_for_controlled_experiment",
                "permissions": {
                    "local_analysis": True,
                    "model_input_or_feature_use": True,
                    "ml_label_use": True,
                    "validation_metrics": True,
                    "derived_reporting": True,
                    "screenshots_and_demo_display": True,
                    "source_redistribution": redistribution == "redistributable",
                    "derived_geometry_redistribution": True,
                    "reference_only_storage_if_not_redistributable": True,
                },
                "reference_qualification": (
                    {
                        "status": "qualified_expert_or_adjudicated",
                        "qualification_method": (
                            "Independent blind synthetic review and adjudication."
                        ),
                        "known_uncertainty_and_error_categories": (
                            "Synthetic boundary, permanent-water, and shadow cases."
                        ),
                        "independent_of_model_inputs": True,
                    }
                    if role == "reference_mask"
                    else None
                ),
            }
        )

    decision = {
        "schema_version": controlled.EXTERNAL_AUTHORITY_DECISION_SCHEMA,
        "decision_id": "QUALIFIED-RELEASE-TEST-DECISION-1",
        "request_id": "QUALIFIED-RELEASE-TEST-REQUEST-1",
        "experiment_id": base_assessment.experiment_id,
        "study_area": base_assessment.study_area,
        "acquisition_manifest_sha256": base_assessment.manifest_sha256,
        "decision_status": "approved_for_controlled_experiment",
        "products": products,
        "required_attribution_and_conditions": {
            "unmodified_source_notice": "Retain synthetic fixture attribution.",
            "modified_or_derived_notice": "Label every derived output synthetic.",
            "citation": "Deterministic qualified-release test fixture.",
            "disclaimer": "No operational or official-warning endorsement.",
            "additional_conditions": "Automated tests only.",
        },
        "authorized_signer": {
            "name": "Synthetic Test Custodian",
            "organization": "FloodGuard Test Authority",
            "title_or_role": "Test-only data custodian",
            "authority_basis": "Deterministic automated-test fixture authority.",
            "identity_evidence_type": "test fixture identity record",
            "identity_evidence_sha256": "7" * 64,
            "decision_issued_at_utc": "2024-01-03T00:00:00Z",
            "decision_expires_at_utc": "2030-01-01T00:00:00Z",
            "signing_key_id": TEST_EXTERNAL_KEY_ID,
            "signature_algorithm": "Ed25519",
            "public_key_sha256": hashlib.sha256(TEST_EXTERNAL_PUBLIC_KEY).hexdigest(),
        },
        "signer_attestations": {
            field: True for field in controlled.EXTERNAL_SIGNER_ATTESTATIONS
        },
        "official_warning": False,
    }
    decision_path = fixture_dir / "external-authority-decision.json"
    decision_path.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    signature_path = fixture_dir / "external-authority-decision.sig"
    signature_path.write_text(
        _ed25519_sign(
            TEST_EXTERNAL_SEED,
            controlled._canonical_json_bytes(decision),
        ).hex()
        + "\n",
        encoding="ascii",
    )
    receipt = fixture_dir / "acquisition-authority.json"
    controlled.write_acquisition_authority_receipt(
        base_assessment,
        manifest,
        external_authority_decision_path=decision_path,
        external_authority_signature_path=signature_path,
        external_authority_public_keys=TEST_EXTERNAL_PUBLIC_KEYS,
        catalog_evidence_paths_by_role=catalog_paths,
        license_evidence_paths_by_role=license_paths,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
        receipt_signing_key_id=TEST_AUTHORITY_KEY_ID,
        receipt_signing_key=TEST_AUTHORITY_KEY,
        output_path=receipt,
    )
    return receipt


def _authorized_test_acquisition(
    fixture_dir: Path,
) -> tuple[Path, dict[str, Path], Path, Any]:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "pre_event_sar": fixture_dir / "pre_event_sar.bin",
        "post_event_sar": fixture_dir / "post_event_sar.bin",
        "reference_mask": fixture_dir / "reference_mask.tif",
    }
    artifacts["pre_event_sar"].write_bytes(b"synthetic-pre-event-sar")
    artifacts["post_event_sar"].write_bytes(b"synthetic-post-event-sar")
    with rasterio.open(
        artifacts["reference_mask"],
        "w",
        driver="GTiff",
        width=6,
        height=1,
        count=1,
        dtype="uint8",
        crs="EPSG:6933",
        transform=from_origin(0.0, 75.0, 50.0, 50.0),
        nodata=255,
    ) as dataset:
        dataset.write(
            np.array([[0, 1, 0, 1, 0, 1]], dtype=np.uint8),
            1,
        )
    times = {
        "pre_event_sar": (
            "2023-12-31T00:00:00Z",
            "2023-12-31T00:01:00Z",
        ),
        "post_event_sar": (
            "2024-01-02T00:00:00Z",
            "2024-01-02T00:01:00Z",
        ),
        "reference_mask": (
            "2024-01-02T00:00:00Z",
            "2024-01-02T23:59:59Z",
        ),
    }
    rows: list[dict[str, Any]] = []
    for role in controlled.REQUIRED_INPUT_ROLES:
        start, end = times[role]
        is_reference = role == "reference_mask"
        rows.append(
            {
                "schema_version": controlled.ACQUISITION_SCHEMA,
                "experiment_id": "QUALIFIED-RELEASE-TEST-EXP-1",
                "study_area": "Synthetic qualified-release test area",
                "role": role,
                "source_name": f"Source {role}",
                "source_url": f"https://example.test/{role}",
                "product_id": f"PRODUCT-{role}",
                "acquisition_start_utc": start,
                "acquisition_end_utc": end,
                "local_path_hint": (
                    f"<external_data_workspace>/{artifacts[role].name}"
                ),
                "sha256": _sha256_file(artifacts[role]),
                "sha256_status": "verified",
                "license_status": "confirmed_for_experiment",
                "local_analysis_allowed": True,
                "derived_metrics_allowed": True,
                "ml_label_use_allowed": True,
                "redistribution_status": "reference_only",
                "reference_mask_status": (
                    "qualified_expert_or_adjudicated"
                    if is_reference
                    else "not_applicable"
                ),
                "temporal_alignment_status": "confirmed",
                "processing_allowed": True,
                "source_timestamp": end,
                "assumptions": "Deterministic synthetic test fixture only.",
            }
        )
    manifest = fixture_dir / "acquisition.csv"
    pd.DataFrame(rows, columns=controlled.ACQUISITION_COLUMNS).to_csv(
        manifest,
        index=False,
        lineterminator="\n",
    )
    base = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
    )
    receipt = _write_signed_test_authority(
        fixture_dir,
        manifest,
        base,
    )
    assessment = assess_acquisition_manifest(
        manifest,
        artifact_paths=artifacts,
        authority_receipt_path=receipt,
        signing_keys=TEST_SIGNING_KEYS,
        external_authority_public_keys=TEST_EXTERNAL_PUBLIC_KEYS,
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )
    return manifest, artifacts, receipt, assessment


def _write_qualified_grid(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "target_crs": "EPSG:6933",
                "transform": [50.0, 0.0, 0.0, 0.0, -50.0, 75.0],
                "width": 6,
                "height": 1,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _rewrite_test_authority_receipt(
    authority: Path,
    mutate,
) -> None:
    payload = json.loads(authority.read_text(encoding="utf-8"))
    decision = payload["external_authority_decision"]
    mutate(decision, payload)
    payload["authorizations"] = decision["products"]
    payload["external_authority_signature_base64"] = base64.b64encode(
        _ed25519_sign(
            TEST_EXTERNAL_SEED,
            controlled._canonical_json_bytes(decision),
        )
    ).decode("ascii")
    unsigned = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "signing_key_id",
            "signature_algorithm",
            "manifest_sha256",
            "signature",
        }
    }
    resealed = controlled._seal_signed_payload(
        unsigned,
        signing_key_id=TEST_AUTHORITY_KEY_ID,
        signing_key=TEST_AUTHORITY_KEY,
        self_hash_field="manifest_sha256",
    )
    authority.write_text(json.dumps(resealed), encoding="utf-8")


def _blocked_assessment():
    manifest = pd.read_csv(ACQUISITION_MANIFEST, dtype=str, keep_default_na=False)
    manifest["processing_allowed"] = "false"
    assessment = assess_acquisition_manifest(manifest)
    assert assessment.ready is False
    assert assessment.blockers
    return assessment


def _blocked_release() -> dict[str, object]:
    return build_qualified_reference_release(
        _blocked_assessment(),
        release_id="mae-sai-reference-release-v1",
        study_area_id="mae-sai-thailand",
        event_id="mae-sai-2024-flood",
        source_timestamp="2024-09-15T23:59:59Z",
        generated_at="2026-07-23T05:00:00.123456Z",
        source_name="Pending qualified Mae Sai reference",
        assumptions=[
            "No qualified event-reference raster is available.",
            "Every acquisition blocker remains fail-closed.",
        ],
        data_version="reference-gate-v1",
        git_commit="6833c8b71fb18f5b8ea17d5d9f8e0745157643c2",
    )


def _write_grid(path: Path, *, crs: str = "EPSG:6933") -> Path:
    payload = {
        "target_crs": crs,
        "transform": [10.0, 0.0, 0.0, 0.0, -10.0, 20.0],
        "width": 2,
        "height": 2,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_raster(
    path: Path,
    *,
    data: np.ndarray | None = None,
    crs: str = "EPSG:6933",
    nodata: int | None = 255,
    count: int = 1,
) -> Path:
    values = (
        np.array([[0, 1], [1, 0]], dtype=np.uint8)
        if data is None
        else np.asarray(data, dtype=np.uint8)
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=count,
        dtype="uint8",
        crs=crs,
        transform=from_origin(0.0, 20.0, 10.0, 10.0),
        nodata=nodata,
    ) as dataset:
        for band in range(1, count + 1):
            dataset.write(values, band)
    return path


def _synthetic_release(tmp_path: Path) -> dict[str, object]:
    raster = _write_raster(tmp_path / "synthetic_reference.tif")
    grid = _write_grid(tmp_path / "analysis_grid.json")
    return build_qualified_reference_release(
        None,
        release_id="synthetic-reference-release-v1",
        study_area_id="fixture-mae-sai",
        event_id="synthetic-event-v1",
        experiment_id="synthetic-integration-v1",
        source_timestamp="2024-09-15T12:00:00.123456Z",
        generated_at="2026-07-23T05:00:00.654321Z",
        source_name="Project-owned synthetic binary fixture",
        assumptions=[
            "Synthetic fixture exercises compatibility plumbing only.",
            "It is not Thai-event evidence.",
        ],
        data_version="synthetic-v1",
        git_commit="6833c8b71fb18f5b8ea17d5d9f8e0745157643c2",
        purpose="flood_model_training_labels",
        release_status=SYNTHETIC_STATUS,
        reference_authority_class="synthetic_fixture",
        reference_product_id="synthetic-binary-mask-v1",
        reference_artifact_path=raster,
        analysis_grid_contract_path=grid,
        observation_start="2024-09-15T00:00:00Z",
        observation_end="2024-09-15T23:59:59.999999Z",
    )


def _reseal(payload: dict[str, object]) -> dict[str, object]:
    value = deepcopy(payload)
    value.pop("release_sha256", None)
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    value["release_sha256"] = hashlib.sha256(encoded).hexdigest()
    return value


def _refresh_evidence_and_reseal(
    payload: dict[str, object],
) -> dict[str, object]:
    value = deepcopy(payload)
    evidence = {
        "reference_artifact": value["reference_artifact"],
        "analysis_grid": value["analysis_grid"],
        "acquisition_lineage": value["acquisition_lineage"],
        "source_permissions": value["source_permissions"],
        "evidence_classification": value["evidence_classification"],
        "purpose": value["purpose"],
    }
    evidence_sha256 = hashlib.sha256(
        json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    value["evidence_bundle_sha256"] = evidence_sha256
    value["purpose_authorizations"][0]["evidence_sha256"] = evidence_sha256
    return _reseal(value)


def _schema_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )


@pytest.fixture(scope="module")
def qualified_authority_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Any]:
    """Create deterministic signed authority over synthetic test bytes only."""

    fixture_dir = tmp_path_factory.mktemp("qualified-reference-authority")
    manifest, artifacts, receipt, assessment = _authorized_test_acquisition(fixture_dir)
    assert assessment.ready is True
    reference_authorities = {
        purpose: _write_reference_authority_decision(
            fixture_dir,
            purpose=purpose,
            artifact_sha256=_sha256_file(artifacts["reference_mask"]),
        )
        for purpose in release_module.PURPOSES
    }
    return {
        "manifest": manifest,
        "artifacts": artifacts,
        "receipt": receipt,
        "assessment": assessment,
        "grid": _write_qualified_grid(fixture_dir / "grid-contract.json"),
        "reference_authorities": reference_authorities,
    }


def _build_qualified_release(
    fixture: dict[str, Any],
    **overrides: Any,
) -> dict[str, object]:
    requested_purpose = overrides.get(
        "purpose",
        "flood_model_training_labels",
    )
    authority_decision, authority_signature = fixture["reference_authorities"][
        requested_purpose
    ]
    values: dict[str, Any] = {
        "release_id": "qualified-reference-release-v1",
        "study_area_id": "synthetic-test-area",
        "event_id": "synthetic-test-event",
        "source_timestamp": "2024-01-02T23:59:59Z",
        "generated_at": "2024-01-05T00:00:00Z",
        "source_name": "Source reference_mask",
        "assumptions": [
            "Signed deterministic synthetic authority fixture only.",
            "This fixture is not real Thai-event evidence.",
        ],
        "data_version": "qualified-fixture-v1",
        "git_commit": "6833c8b71fb18f5b8ea17d5d9f8e0745157643c2",
        "purpose": "flood_model_training_labels",
        "release_status": QUALIFIED_STATUS,
        "reference_authority_class": "expert_interpretation",
        "confidence_class": "high",
        "reference_product_id": "PRODUCT-reference_mask",
        "reference_artifact_path": fixture["artifacts"]["reference_mask"],
        "analysis_grid_contract_path": fixture["grid"],
        "acquisition_authority_receipt_path": fixture["receipt"],
        "reference_authority_decision_path": authority_decision,
        "reference_authority_signature_path": authority_signature,
        "reference_authority_public_keys": (TEST_REFERENCE_AUTHORITY_PUBLIC_KEYS),
    }
    values.update(overrides)
    return build_qualified_reference_release(
        fixture["assessment"],
        **values,
    )


def _copy_qualified_evidence(
    fixture: dict[str, Any],
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    receipt = tmp_path / "acquisition-authority.json"
    raster = tmp_path / "reference_mask.tif"
    grid = tmp_path / "grid-contract.json"
    shutil.copyfile(fixture["receipt"], receipt)
    shutil.copyfile(fixture["artifacts"]["reference_mask"], raster)
    shutil.copyfile(fixture["grid"], grid)
    return receipt, raster, grid


def _reassess_with_receipt(
    fixture: dict[str, Any],
    receipt: Path,
    *,
    signing_keys: dict[str, bytes] | None = None,
    external_keys: dict[str, bytes] | None = None,
):
    return assess_acquisition_manifest(
        fixture["manifest"],
        artifact_paths=fixture["artifacts"],
        authority_receipt_path=receipt,
        signing_keys=(TEST_SIGNING_KEYS if signing_keys is None else signing_keys),
        external_authority_public_keys=(
            TEST_EXTERNAL_PUBLIC_KEYS if external_keys is None else external_keys
        ),
        verified_at_utc=datetime(2024, 1, 5, tzinfo=UTC),
    )


def test_blocked_projection_preserves_verified_acquisition_blockers() -> None:
    assessment = _blocked_assessment()
    release = _blocked_release()

    assert release["release_status"] == BLOCKED_STATUS
    assert release["processing_allowed"] is False
    assert release["eligible_for_controlled_model_development"] is False
    assert release["eligible_for_controlled_model_evaluation"] is False
    assert release["official_warning"] is False
    assert release["can_feed_decision_layer"] is False
    assert release["can_feed_fpps"] is False
    assert release["can_assign_action_class"] is False
    assert release["agency_operational_authorized"] is False
    assert release["reference_artifact"] is None
    assert release["analysis_grid"] is None
    assert release["evidence_bundle_sha256"] is None
    assert release["blockers"] == sorted(set(assessment.blockers))
    assert release["acquisition_lineage"]["assessment_blockers"] == release["blockers"]
    assert not any(release["source_permissions"].values())
    assert all(
        item["status"] == BLOCKED_STATUS and item["evidence_sha256"] is None
        for item in release["purpose_authorizations"]
    )
    assert release["generated_at"] == "2026-07-23T05:00:00.123456Z"
    assert validate_qualified_reference_release(release) == release


def test_blocked_projection_is_deterministic() -> None:
    first = _blocked_release()
    second = _blocked_release()

    assert first == second
    assert first["release_sha256"] == second["release_sha256"]


def test_blocked_projection_rejects_evidence_smuggling(tmp_path: Path) -> None:
    artifact = _write_raster(tmp_path / "reference.tif")

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="must not carry unverified evidence inputs",
    ):
        build_qualified_reference_release(
            _blocked_assessment(),
            release_id="blocked-release-v1",
            study_area_id="mae-sai-thailand",
            event_id="mae-sai-2024",
            source_timestamp="2024-09-15T12:00:00Z",
            generated_at="2026-07-23T05:00:00Z",
            source_name="Pending reference",
            assumptions=["Reference remains blocked."],
            data_version="blocked-v1",
            git_commit="6833c8b71fb18f5b8ea17d5d9f8e0745157643c2",
            reference_artifact_path=artifact,
        )


def test_qualified_state_is_impossible_from_non_ready_assessment() -> None:
    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="impossible without a ready signed acquisition assessment",
    ):
        build_qualified_reference_release(
            _blocked_assessment(),
            release_id="qualified-release-v1",
            study_area_id="mae-sai-thailand",
            event_id="mae-sai-2024",
            source_timestamp="2024-09-15T12:00:00Z",
            generated_at="2026-07-23T05:00:00Z",
            source_name="Unqualified reference",
            assumptions=["No authority has approved this reference."],
            data_version="candidate-v1",
            git_commit="6833c8b71fb18f5b8ea17d5d9f8e0745157643c2",
            purpose="flood_model_training_labels",
            release_status=QUALIFIED_STATUS,
            reference_authority_class="expert_interpretation",
            confidence_class="high",
        )


def test_signed_synthetic_authority_reaches_qualified_compatibility_state(
    qualified_authority_fixture: dict[str, Any],
) -> None:
    release = _build_qualified_release(qualified_authority_fixture)

    assert release["release_status"] == QUALIFIED_STATUS
    assert release["processing_allowed"] is True
    assert release["eligible_for_controlled_model_development"] is True
    assert release["eligible_for_controlled_model_evaluation"] is False
    assert release["synthetic_fixture_processing_allowed"] is False
    assert release["official_warning"] is False
    assert release["can_feed_decision_layer"] is False
    assert release["can_feed_fpps"] is False
    assert release["can_assign_action_class"] is False
    assert release["agency_operational_authorized"] is False
    assert release["blockers"] == []
    assert release["purpose"] == "flood_model_training_labels"
    assert len(release["purpose_authorizations"]) == 1
    assert release["source_permissions"]["source_redistribution"] is False
    assert all(
        purpose["status"] == "reference_gate_passed_downstream_gates_required"
        and purpose["evidence_sha256"] == release["evidence_bundle_sha256"]
        for purpose in release["purpose_authorizations"]
    )
    lineage = release["acquisition_lineage"]
    assert lineage["assessment_status"] == "ready"
    assert lineage["reference_product_id"] == "PRODUCT-reference_mask"
    assert lineage["reference_source_name"] == "Source reference_mask"
    assert lineage["reference_source_timestamp"] == "2024-01-02T23:59:59Z"
    assert lineage["reference_observation_start"] == "2024-01-02T00:00:00Z"
    assert lineage["reference_observation_end"] == "2024-01-02T23:59:59Z"
    assert lineage["reference_authorization_sha256"]
    assert lineage["reference_permissions_sha256"]
    assert lineage["reference_authority_purpose"] == "flood_model_training_labels"
    assert lineage["reference_authority_class"] == "expert_interpretation"
    assert lineage["reference_authority_decision_sha256"]
    assert lineage["reference_authority_signature_sha256"]
    assert lineage["reference_authority_receipt_sha256"]
    assert validate_qualified_reference_release(release) == release
    assert list(_schema_validator().iter_errors(release)) == []


@pytest.mark.parametrize(
    ("purpose", "eligible_for_development", "eligible_for_evaluation"),
    [
        ("human_reviewer_calibration", False, False),
        ("human_annotation_reference", False, False),
        ("flood_model_training_labels", True, False),
        ("model_probability_calibration", True, False),
        ("model_final_evaluation", False, True),
        ("derived_metrics_only", False, False),
    ],
)
def test_qualified_receipt_authorizes_exactly_one_canonical_purpose(
    qualified_authority_fixture: dict[str, Any],
    purpose: str,
    eligible_for_development: bool,
    eligible_for_evaluation: bool,
) -> None:
    release = _build_qualified_release(
        qualified_authority_fixture,
        purpose=purpose,
    )

    assert release["purpose"] == purpose
    assert [row["purpose"] for row in release["purpose_authorizations"]] == [purpose]
    assert (
        release["eligible_for_controlled_model_development"] is eligible_for_development
    )
    assert (
        release["eligible_for_controlled_model_evaluation"] is eligible_for_evaluation
    )
    assert release["acquisition_lineage"]["reference_authority_purpose"] == purpose
    assert validate_qualified_reference_release(release) == release
    assert list(_schema_validator().iter_errors(release)) == []


def test_rehashed_purpose_substitution_cannot_reuse_scientific_receipt(
    qualified_authority_fixture: dict[str, Any],
) -> None:
    release = _build_qualified_release(qualified_authority_fixture)
    release["purpose"] = "model_final_evaluation"
    release["purpose_authorizations"][0]["purpose"] = "model_final_evaluation"
    release = _refresh_evidence_and_reseal(release)

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="ready signed authority|required scope",
    ):
        validate_qualified_reference_release(release)


def test_resigned_reference_authority_purpose_substitution_is_rejected(
    qualified_authority_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    source_decision, _source_signature = qualified_authority_fixture[
        "reference_authorities"
    ]["flood_model_training_labels"]
    decision = json.loads(source_decision.read_text(encoding="utf-8"))
    decision["purpose"] = "model_final_evaluation"
    decision_path = tmp_path / "substituted-reference-authority.json"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    signature_path = tmp_path / "substituted-reference-authority.sig"
    signature_path.write_text(
        _ed25519_sign(
            TEST_REFERENCE_AUTHORITY_SEED,
            controlled._canonical_json_bytes(decision),
        ).hex(),
        encoding="ascii",
    )

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="purpose was substituted",
    ):
        _build_qualified_release(
            qualified_authority_fixture,
            reference_authority_decision_path=decision_path,
            reference_authority_signature_path=signature_path,
        )


def test_reference_authority_cannot_self_authorize_from_payload_key(
    qualified_authority_fixture: dict[str, Any],
) -> None:
    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="runtime trust configuration",
    ):
        _build_qualified_release(
            qualified_authority_fixture,
            reference_authority_public_keys={},
        )


def test_qualified_release_requires_separate_reference_authority_files(
    qualified_authority_fixture: dict[str, Any],
) -> None:
    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="file-backed Reference Authority decision",
    ):
        _build_qualified_release(
            qualified_authority_fixture,
            reference_authority_decision_path=None,
        )


def test_reference_authority_detached_signature_tampering_is_rejected(
    qualified_authority_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    source_decision, source_signature = qualified_authority_fixture[
        "reference_authorities"
    ]["flood_model_training_labels"]
    decision_path = tmp_path / "reference-authority.json"
    signature_path = tmp_path / "reference-authority.sig"
    shutil.copyfile(source_decision, decision_path)
    signature = source_signature.read_text(encoding="ascii").strip()
    signature_path.write_text(
        ("0" if signature[0] != "0" else "1") + signature[1:],
        encoding="ascii",
    )

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="signature is invalid",
    ):
        _build_qualified_release(
            qualified_authority_fixture,
            reference_authority_decision_path=decision_path,
            reference_authority_signature_path=signature_path,
        )


def test_reference_authority_must_be_distinct_from_legal_authority(
    qualified_authority_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    source_decision, _source_signature = qualified_authority_fixture[
        "reference_authorities"
    ]["flood_model_training_labels"]
    decision = json.loads(source_decision.read_text(encoding="utf-8"))
    decision["signer"] = {
        "name": "Synthetic Test Custodian",
        "organization": "FloodGuard Test Authority",
        "title_or_role": "Reference Authority",
        "authority_basis": "Invalid reused legal-authority identity.",
        "identity_evidence_type": "test fixture identity record",
        "identity_evidence_sha256": "8" * 64,
        "signing_key_id": TEST_REFERENCE_AUTHORITY_KEY_ID,
        "public_key_sha256": hashlib.sha256(
            TEST_REFERENCE_AUTHORITY_PUBLIC_KEY
        ).hexdigest(),
    }
    decision_path = tmp_path / "reused-identity-reference-authority.json"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    signature_path = tmp_path / "reused-identity-reference-authority.sig"
    signature_path.write_text(
        _ed25519_sign(
            TEST_REFERENCE_AUTHORITY_SEED,
            controlled._canonical_json_bytes(decision),
        ).hex(),
        encoding="ascii",
    )

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="distinct from acquisition/legal authority",
    ):
        _build_qualified_release(
            qualified_authority_fixture,
            reference_authority_decision_path=decision_path,
            reference_authority_signature_path=signature_path,
        )


def test_substituted_authority_signature_cannot_reach_qualified_state(
    qualified_authority_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    receipt, _raster, _grid = _copy_qualified_evidence(
        qualified_authority_fixture,
        tmp_path,
    )
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    signature = payload["signature"]
    payload["signature"] = ("0" if signature[0] != "0" else "1") + signature[1:]
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    assessment = _reassess_with_receipt(
        qualified_authority_fixture,
        receipt,
    )

    assert assessment.ready is False
    assert any("HMAC signature is invalid" in item for item in assessment.blockers)
    substituted = {
        **qualified_authority_fixture,
        "assessment": assessment,
        "receipt": receipt,
    }
    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="impossible without a ready signed acquisition assessment",
    ):
        _build_qualified_release(substituted)


@pytest.mark.parametrize(
    ("signing_keys", "external_keys", "blocker"),
    [
        (
            {"substituted-internal-key": TEST_AUTHORITY_KEY},
            TEST_EXTERNAL_PUBLIC_KEYS,
            "not trusted at runtime",
        ),
        (
            TEST_SIGNING_KEYS,
            {},
            "public key is not trusted at runtime",
        ),
    ],
)
def test_substituted_runtime_key_trust_cannot_reach_qualified_state(
    qualified_authority_fixture: dict[str, Any],
    signing_keys: dict[str, bytes],
    external_keys: dict[str, bytes],
    blocker: str,
) -> None:
    assessment = _reassess_with_receipt(
        qualified_authority_fixture,
        qualified_authority_fixture["receipt"],
        signing_keys=signing_keys,
        external_keys=external_keys,
    )

    assert assessment.ready is False
    assert any(blocker in item for item in assessment.blockers)
    substituted = {
        **qualified_authority_fixture,
        "assessment": assessment,
    }
    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="impossible without a ready signed acquisition assessment",
    ):
        _build_qualified_release(substituted)


@pytest.mark.parametrize(
    ("substitution", "blocker"),
    [
        ("permission", "every required external permission"),
        ("product", "product_id was substituted"),
        ("timestamp", "source_timestamp was substituted"),
    ],
)
def test_resigned_authority_scope_substitution_still_fails_closed(
    qualified_authority_fixture: dict[str, Any],
    tmp_path: Path,
    substitution: str,
    blocker: str,
) -> None:
    receipt, _raster, _grid = _copy_qualified_evidence(
        qualified_authority_fixture,
        tmp_path,
    )

    def mutate(decision: dict[str, Any], _receipt: dict[str, Any]) -> None:
        reference = next(
            product
            for product in decision["products"]
            if product["role"] == "reference_mask"
        )
        if substitution == "permission":
            reference["permissions"]["validation_metrics"] = False
        elif substitution == "product":
            reference["product_id"] = "SUBSTITUTED-REFERENCE-PRODUCT"
        else:
            reference["source_timestamp"] = "2024-01-02T23:59:58Z"

    _rewrite_test_authority_receipt(
        receipt,
        mutate,
    )
    assessment = _reassess_with_receipt(
        qualified_authority_fixture,
        receipt,
    )

    assert assessment.ready is False
    assert any(blocker in item for item in assessment.blockers)
    substituted = {
        **qualified_authority_fixture,
        "assessment": assessment,
        "receipt": receipt,
    }
    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="impossible without a ready signed acquisition assessment",
    ):
        _build_qualified_release(substituted)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (
            {"reference_product_id": "SUBSTITUTED-REFERENCE-PRODUCT"},
            "reference_product_id differs from the signed authorization",
        ),
        (
            {"source_timestamp": "2024-01-02T23:59:58Z"},
            "source_timestamp differs from the signed reference authorization",
        ),
    ],
)
def test_qualified_builder_rejects_product_and_timestamp_substitution(
    qualified_authority_fixture: dict[str, Any],
    override: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(QualifiedReferenceReleaseError, match=message):
        _build_qualified_release(
            qualified_authority_fixture,
            **override,
        )


def test_qualified_builder_rejects_raster_byte_substitution(
    qualified_authority_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    _receipt, raster, _grid = _copy_qualified_evidence(
        qualified_authority_fixture,
        tmp_path,
    )
    with rasterio.open(raster, "r+") as dataset:
        values = dataset.read(1)
        values[0, 0] = 1
        dataset.write(values, 1)

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="Reference artifact bytes differ from the signed authorization",
    ):
        _build_qualified_release(
            qualified_authority_fixture,
            reference_artifact_path=raster,
        )


def test_qualified_builder_rejects_grid_substitution(
    qualified_authority_fixture: dict[str, Any],
    tmp_path: Path,
) -> None:
    _receipt, _raster, grid = _copy_qualified_evidence(
        qualified_authority_fixture,
        tmp_path,
    )
    payload = json.loads(grid.read_text(encoding="utf-8"))
    payload["transform"][2] = 1.0
    grid.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="transform differs from the analysis grid",
    ):
        _build_qualified_release(
            qualified_authority_fixture,
            analysis_grid_contract_path=grid,
        )


def test_receipt_drift_between_snapshot_and_seal_is_rejected(
    qualified_authority_fixture: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, raster, grid = _copy_qualified_evidence(
        qualified_authority_fixture,
        tmp_path,
    )
    original = release_module._qualified_authority_binding

    def drifting_binding(
        acquisition,
        receipt_path,
        *,
        generated_at,
    ):
        result = original(
            acquisition,
            receipt_path,
            generated_at=generated_at,
        )
        receipt.write_bytes(receipt.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(
        release_module,
        "_qualified_authority_binding",
        drifting_binding,
    )
    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="Acquisition-authority receipt changed after verification",
    ):
        _build_qualified_release(
            qualified_authority_fixture,
            acquisition_authority_receipt_path=receipt,
            reference_artifact_path=raster,
            analysis_grid_contract_path=grid,
        )


def test_raster_drift_between_inspection_and_seal_is_rejected(
    qualified_authority_fixture: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, raster, grid = _copy_qualified_evidence(
        qualified_authority_fixture,
        tmp_path,
    )
    original = release_module._inspect_reference_raster

    def drifting_raster(path, **kwargs):
        result = original(path, **kwargs)
        with path.open("ab") as stream:
            stream.write(b"post-inspection-drift")
        return result

    monkeypatch.setattr(
        release_module,
        "_inspect_reference_raster",
        drifting_raster,
    )
    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="Reference artifact changed after verification",
    ):
        _build_qualified_release(
            qualified_authority_fixture,
            acquisition_authority_receipt_path=receipt,
            reference_artifact_path=raster,
            analysis_grid_contract_path=grid,
        )


def test_grid_drift_between_snapshot_and_seal_is_rejected(
    qualified_authority_fixture: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, raster, grid = _copy_qualified_evidence(
        qualified_authority_fixture,
        tmp_path,
    )
    original = release_module._load_analysis_grid

    def drifting_grid(path):
        result = original(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["grid_id"] = "SUBSTITUTED-GRID"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return result

    monkeypatch.setattr(
        release_module,
        "_load_analysis_grid",
        drifting_grid,
    )
    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="Analysis-grid contract changed after verification",
    ):
        _build_qualified_release(
            qualified_authority_fixture,
            acquisition_authority_receipt_path=receipt,
            reference_artifact_path=raster,
            analysis_grid_contract_path=grid,
        )


@pytest.mark.parametrize(
    "substitution",
    ["product", "timestamp", "permission", "purpose"],
)
def test_qualified_validator_rejects_resealed_scope_substitution(
    qualified_authority_fixture: dict[str, Any],
    substitution: str,
) -> None:
    release = _build_qualified_release(qualified_authority_fixture)
    if substitution == "product":
        release["reference_artifact"]["product_id"] = "SUBSTITUTED-PRODUCT"
        release = _refresh_evidence_and_reseal(release)
    elif substitution == "timestamp":
        release["source_timestamp"] = "2024-01-02T23:59:58Z"
        release = _reseal(release)
    elif substitution == "permission":
        release["source_permissions"]["source_redistribution"] = True
        release = _refresh_evidence_and_reseal(release)
    else:
        release["purpose_authorizations"][0]["status"] = BLOCKED_STATUS
        release = _reseal(release)

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="Qualified release lacks ready signed authority|required scope",
    ):
        validate_qualified_reference_release(release)


def test_synthetic_release_is_byte_and_grid_bound_but_never_qualified(
    tmp_path: Path,
) -> None:
    release = _synthetic_release(tmp_path)

    assert release["release_status"] == SYNTHETIC_STATUS
    assert release["dataset_mode"] == "fixture_demo"
    assert release["processing_allowed"] is False
    assert release["synthetic_fixture_processing_allowed"] is True
    assert release["eligible_for_controlled_model_development"] is False
    assert release["eligible_for_controlled_model_evaluation"] is False
    assert release["blockers"] == [SYNTHETIC_LIMITATION]
    assert release["reference_artifact"]["valid_values"] == [0, 1]
    assert release["reference_artifact"]["nodata"] == 255.0
    assert release["reference_artifact"]["crs"] == "EPSG:6933"
    assert release["analysis_grid"]["crs"] == "EPSG:6933"
    assert release["acquisition_lineage"]["assessment_status"] == (
        "not_applicable_synthetic_fixture"
    )
    assert all(release["source_permissions"].values())
    assert all(
        item["status"] == SYNTHETIC_STATUS
        and item["evidence_sha256"] == release["evidence_bundle_sha256"]
        for item in release["purpose_authorizations"]
    )
    assert release["source_timestamp"] == "2024-09-15T12:00:00.123456Z"
    assert validate_qualified_reference_release(release) == release


@pytest.mark.parametrize(
    ("data", "nodata", "error"),
    [
        (np.array([[0, 1], [1, 0]], dtype=np.uint8), None, "explicit nodata"),
        (np.array([[0, 1], [1, 0]], dtype=np.uint8), 1, "distinct from classes"),
        (np.array([[0, 2], [1, 0]], dtype=np.uint8), 255, "only classes 0 and 1"),
        (np.array([[0, 0], [0, 0]], dtype=np.uint8), 255, "both non-flood"),
    ],
)
def test_synthetic_builder_rejects_invalid_reference_pixels(
    tmp_path: Path,
    data: np.ndarray,
    nodata: int | None,
    error: str,
) -> None:
    raster = _write_raster(tmp_path / "invalid.tif", data=data, nodata=nodata)
    grid = _write_grid(tmp_path / "grid.json")

    with pytest.raises(QualifiedReferenceReleaseError, match=error):
        build_qualified_reference_release(
            None,
            release_id="synthetic-reference-v1",
            study_area_id="fixture-area-v1",
            event_id="fixture-event-v1",
            experiment_id="fixture-experiment-v1",
            source_timestamp="2024-09-15T12:00:00Z",
            generated_at="2026-07-23T05:00:00Z",
            source_name="Synthetic fixture",
            assumptions=["Fixture only."],
            data_version="fixture-v1",
            git_commit="6833c8b71fb18f5b8ea17d5d9f8e0745157643c2",
            purpose="derived_metrics_only",
            release_status=SYNTHETIC_STATUS,
            reference_authority_class="synthetic_fixture",
            reference_product_id="synthetic-product-v1",
            reference_artifact_path=raster,
            analysis_grid_contract_path=grid,
            observation_start="2024-09-15T00:00:00Z",
            observation_end="2024-09-15T23:59:59Z",
        )


def test_synthetic_builder_rejects_non_equal_area_grid(tmp_path: Path) -> None:
    raster = _write_raster(tmp_path / "geographic.tif", crs="EPSG:4326")
    grid = _write_grid(tmp_path / "grid.json", crs="EPSG:4326")

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="projected, metre-based, and equal-area",
    ):
        build_qualified_reference_release(
            None,
            release_id="synthetic-reference-v1",
            study_area_id="fixture-area-v1",
            event_id="fixture-event-v1",
            experiment_id="fixture-experiment-v1",
            source_timestamp="2024-09-15T12:00:00Z",
            generated_at="2026-07-23T05:00:00Z",
            source_name="Synthetic fixture",
            assumptions=["Fixture only."],
            data_version="fixture-v1",
            git_commit="6833c8b71fb18f5b8ea17d5d9f8e0745157643c2",
            purpose="derived_metrics_only",
            release_status=SYNTHETIC_STATUS,
            reference_authority_class="synthetic_fixture",
            reference_product_id="synthetic-product-v1",
            reference_artifact_path=raster,
            analysis_grid_contract_path=grid,
            observation_start="2024-09-15T00:00:00Z",
            observation_end="2024-09-15T23:59:59Z",
        )


def test_synthetic_builder_rejects_source_time_outside_observation(
    tmp_path: Path,
) -> None:
    raster = _write_raster(tmp_path / "reference.tif")
    grid = _write_grid(tmp_path / "grid.json")

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="outside the reference observation interval",
    ):
        build_qualified_reference_release(
            None,
            release_id="synthetic-reference-v1",
            study_area_id="fixture-area-v1",
            event_id="fixture-event-v1",
            experiment_id="fixture-experiment-v1",
            source_timestamp="2024-09-16T00:00:00Z",
            generated_at="2026-07-23T05:00:00Z",
            source_name="Synthetic fixture",
            assumptions=["Fixture only."],
            data_version="fixture-v1",
            git_commit="6833c8b71fb18f5b8ea17d5d9f8e0745157643c2",
            purpose="derived_metrics_only",
            release_status=SYNTHETIC_STATUS,
            reference_authority_class="synthetic_fixture",
            reference_product_id="synthetic-product-v1",
            reference_artifact_path=raster,
            analysis_grid_contract_path=grid,
            observation_start="2024-09-15T00:00:00Z",
            observation_end="2024-09-15T23:59:59Z",
        )


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda payload: payload.__setitem__("can_feed_fpps", True),
            "unsafe authority flags",
        ),
        (
            lambda payload: payload.__setitem__(
                "source_name",
                r"C:\Users\analyst\private-mask.tif",
            ),
            "private absolute path",
        ),
        (
            lambda payload: payload["source_permissions"].__setitem__(
                "ml_label_use",
                False,
            ),
            "Evidence-bundle hash mismatch",
        ),
        (
            lambda payload: payload["purpose_authorizations"][0].__setitem__(
                "purpose",
                "derived_metrics_only",
            ),
            "differs from the selected receipt purpose",
        ),
    ],
)
def test_validator_rejects_resealed_adversarial_mutations(
    tmp_path: Path,
    mutate,
    error: str,
) -> None:
    release = _synthetic_release(tmp_path)
    mutate(release)

    with pytest.raises(QualifiedReferenceReleaseError, match=error):
        validate_qualified_reference_release(_reseal(release))


def test_validator_rejects_evidence_bundle_substitution(tmp_path: Path) -> None:
    release = _synthetic_release(tmp_path)
    substituted = "0" * 64
    release["evidence_bundle_sha256"] = substituted
    for purpose in release["purpose_authorizations"]:
        purpose["evidence_sha256"] = substituted

    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="Evidence-bundle hash mismatch",
    ):
        validate_qualified_reference_release(_reseal(release))


def test_validator_rejects_unsealed_mutation() -> None:
    release = _blocked_release()
    release["source_name"] = "Tampered pending source"

    with pytest.raises(QualifiedReferenceReleaseError, match="self-hash mismatch"):
        validate_qualified_reference_release(release)


def test_immutable_writer_round_trip_and_refuses_overwrite(tmp_path: Path) -> None:
    release = _blocked_release()
    output = tmp_path / "qualified-reference-release.json"

    assert write_qualified_reference_release(release, output) == output
    assert load_qualified_reference_release(output) == release
    with pytest.raises(
        QualifiedReferenceReleaseError,
        match="already exists and is immutable",
    ):
        write_qualified_reference_release(release, output)


def test_json_schema_accepts_built_blocked_and_synthetic_releases(
    tmp_path: Path,
) -> None:
    validator = _schema_validator()

    assert list(validator.iter_errors(_blocked_release())) == []
    assert list(validator.iter_errors(_synthetic_release(tmp_path))) == []


def test_json_schema_rejects_authority_overclaim() -> None:
    validator = _schema_validator()
    release = _blocked_release()
    release["official_warning"] = True

    assert list(validator.iter_errors(release))


def test_cli_writes_current_blocked_projection(tmp_path: Path) -> None:
    output = tmp_path / "current-blocked-release.json"
    blocked_manifest = tmp_path / "blocked-acquisition-manifest.csv"
    manifest = pd.read_csv(ACQUISITION_MANIFEST, dtype=str, keep_default_na=False)
    manifest["processing_allowed"] = "false"
    manifest.to_csv(blocked_manifest, index=False)
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--acquisition-manifest",
        str(blocked_manifest),
        "--release-id",
        "mae-sai-reference-release-v1",
        "--study-area-id",
        "mae-sai-thailand",
        "--event-id",
        "mae-sai-2024-flood",
        "--source-timestamp",
        "2024-09-15T23:59:59Z",
        "--generated-at",
        "2026-07-23T05:00:00Z",
        "--source-name",
        "Pending qualified Mae Sai reference",
        "--assumption",
        "No qualified event-reference raster is available.",
        "--data-version",
        "reference-gate-v1",
        "--git-commit",
        "6833c8b71fb18f5b8ea17d5d9f8e0745157643c2",
        "--output",
        str(output),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "release_status=blocked" in result.stdout
    assert "purpose=derived_metrics_only" in result.stdout
    assert "processing_allowed=false" in result.stdout
    assert "official_warning=false" in result.stdout
    release = load_qualified_reference_release(output)
    assert release["release_status"] == BLOCKED_STATUS
    assert release["purpose"] == "derived_metrics_only"
